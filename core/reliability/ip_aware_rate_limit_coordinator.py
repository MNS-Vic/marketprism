"""
MarketPrism IP感知分布式速率限制协调器

专门处理基于IP地址的速率限制，完全体现交易所文档中的IP限制特性：
1. Binance: "访问限制是基于IP的，而不是API Key"
2. OKX: "公共未经身份验证的 REST 限速基于 IP 地址"

核心特性：
- IP级别的令牌桶管理
- 支持多IP地址部署
- 实时IP限制监控
- IP封禁检测和处理
- 自动IP轮换支持
"""

import asyncio
import time
import json
import uuid
import hashlib
import socket
import ipaddress
from typing import Dict, List, Optional, Any, Union, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import logging
from abc import ABC, abstractmethod

try:
    import aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class ExchangeType(Enum):
    """交易所类型"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"
    BYBIT = "bybit"
    HUOBI = "huobi"


class RequestType(Enum):
    """请求类型"""
    REST_PUBLIC = "rest_public"
    REST_PRIVATE = "rest_private"
    WEBSOCKET = "websocket"
    ORDER = "order"
    TRADE = "trade"
    MARKET_DATA = "market_data"


class IPStatus(Enum):
    """IP状态"""
    ACTIVE = "active"
    WARNING = "warning"
    BANNED = "banned"
    UNKNOWN = "unknown"


@dataclass
class IPRateLimit:
    """IP级别的速率限制配置"""
    exchange: ExchangeType
    ip_address: str
    
    # IP级别限制（基于交易所文档）
    requests_per_minute: int = 1200      # Binance: 1200/分钟
    weight_per_minute: int = 6000        # Binance: 6000权重/分钟
    order_requests_per_second: int = 10  # Binance: 10订单/秒
    order_requests_per_day: int = 200000 # Binance: 200000订单/天
    
    # 连接限制
    websocket_connections: int = 5       # 每IP的WebSocket连接数
    
    # 当前使用情况
    current_requests: int = 0
    current_weight: int = 0
    current_orders_today: int = 0
    last_reset_time: float = field(default_factory=time.time)
    
    # 状态和惩罚
    status: IPStatus = IPStatus.ACTIVE
    ban_until: Optional[float] = None
    warning_count: int = 0
    last_429_time: Optional[float] = None
    last_418_time: Optional[float] = None
    
    @classmethod
    def create_for_binance(cls, ip_address: str) -> 'IPRateLimit':
        """为Binance创建IP限制"""
        return cls(
            exchange=ExchangeType.BINANCE,
            ip_address=ip_address,
            requests_per_minute=1200,
            weight_per_minute=6000,
            order_requests_per_second=10,
            order_requests_per_day=200000,
            websocket_connections=5
        )
    
    @classmethod 
    def create_for_okx(cls, ip_address: str) -> 'IPRateLimit':
        """为OKX创建IP限制"""
        return cls(
            exchange=ExchangeType.OKX,
            ip_address=ip_address,
            requests_per_minute=600,
            weight_per_minute=3000,
            order_requests_per_second=5,
            order_requests_per_day=100000,
            websocket_connections=5
        )
    
    def is_banned(self) -> bool:
        """检查IP是否被封禁"""
        if self.ban_until is None:
            return False
        return time.time() < self.ban_until
    
    def can_make_request(self, weight: int = 1) -> Tuple[bool, str]:
        """检查是否可以发出请求"""
        if self.is_banned():
            remaining_ban_time = self.ban_until - time.time()
            return False, f"IP被封禁，剩余时间: {remaining_ban_time:.1f}秒"
        
        current_time = time.time()
        
        # 检查分钟级别的请求限制
        if self.current_requests >= self.requests_per_minute:
            return False, f"超过每分钟请求限制: {self.requests_per_minute}"
        
        # 检查权重限制
        if self.current_weight + weight > self.weight_per_minute:
            return False, f"超过每分钟权重限制: {self.weight_per_minute}"
        
        return True, "可以发出请求"
    
    def consume_request(self, weight: int = 1, is_order: bool = False):
        """消费一个请求"""
        self.current_requests += 1
        self.current_weight += weight
        
        if is_order:
            self.current_orders_today += 1
    
    def reset_if_needed(self):
        """如果需要的话重置计数器"""
        current_time = time.time()
        
        # 每分钟重置
        if current_time - self.last_reset_time >= 60:
            self.current_requests = 0
            self.current_weight = 0
            self.last_reset_time = current_time
        
        # 每天重置订单计数
        current_date = datetime.fromtimestamp(current_time).date()
        last_reset_date = datetime.fromtimestamp(self.last_reset_time).date()
        if current_date != last_reset_date:
            self.current_orders_today = 0
    
    def handle_429_response(self, retry_after: Optional[int] = None):
        """处理429响应（速率限制）"""
        self.last_429_time = time.time()
        self.warning_count += 1
        self.status = IPStatus.WARNING
        
        if retry_after:
            # 设置临时暂停，但不是完全封禁
            self.ban_until = time.time() + retry_after
    
    def handle_418_response(self, retry_after: Optional[int] = None):
        """处理418响应（IP封禁）"""
        self.last_418_time = time.time()
        self.status = IPStatus.BANNED
        
        # 默认封禁时间（根据文档：2分钟到3天）
        ban_duration = retry_after if retry_after else (120 * (2 ** min(self.warning_count, 10)))  # 指数退避
        self.ban_until = time.time() + ban_duration
        
        logger.error(f"IP {self.ip_address} 被交易所封禁，封禁时间: {ban_duration}秒")


@dataclass
class IPPoolConfig:
    """IP池配置"""
    primary_ip: str
    backup_ips: List[str] = field(default_factory=list)
    auto_rotation: bool = True
    max_warnings_per_ip: int = 3
    cooldown_period: int = 300  # 5分钟冷却
    health_check_interval: int = 60  # 1分钟健康检查


class IPManager:
    """IP管理器 - 管理多个IP地址的使用和轮换"""
    
    def __init__(self, config: IPPoolConfig, storage):
        self.config = config
        self.storage = storage
        self.ip_limits: Dict[str, IPRateLimit] = {}
        self.current_ip = config.primary_ip
        
        # 初始化所有IP的限制
        all_ips = [config.primary_ip] + config.backup_ips
        for ip in all_ips:
            self.ip_limits[ip] = IPRateLimit.create_for_binance(ip)  # 默认使用Binance限制
    
    async def get_current_ip(self) -> str:
        """获取当前可用的IP地址"""
        # 检查当前IP是否可用
        current_limit = self.ip_limits[self.current_ip]
        current_limit.reset_if_needed()
        
        if not current_limit.is_banned() and current_limit.status != IPStatus.BANNED:
            return self.current_ip
        
        # 寻找可用的备用IP
        for ip in self.config.backup_ips:
            ip_limit = self.ip_limits[ip]
            ip_limit.reset_if_needed()
            
            if not ip_limit.is_banned() and ip_limit.status != IPStatus.BANNED:
                logger.info(f"切换到备用IP: {self.current_ip} -> {ip}")
                self.current_ip = ip
                return ip
        
        # 如果所有IP都不可用，返回主IP（可能需要等待）
        logger.warning("所有IP都不可用，使用主IP")
        return self.config.primary_ip
    
    async def can_make_request(self, weight: int = 1, exchange: ExchangeType = ExchangeType.BINANCE) -> Tuple[bool, str, str]:
        """
        检查是否可以发出请求
        
        Returns:
            Tuple[bool, str, str]: (可以请求, 使用的IP, 原因)
        """
        ip = await self.get_current_ip()
        ip_limit = self.ip_limits[ip]
        
        can_request, reason = ip_limit.can_make_request(weight)
        return can_request, ip, reason
    
    async def consume_request(self, weight: int = 1, is_order: bool = False, ip: Optional[str] = None):
        """消费一个请求"""
        if ip is None:
            ip = await self.get_current_ip()
        
        if ip in self.ip_limits:
            self.ip_limits[ip].consume_request(weight, is_order)
            
            # 保存到存储
            await self._save_ip_status(ip)
    
    async def handle_exchange_response(self, status_code: int, headers: Dict[str, str], ip: str):
        """处理交易所响应，更新IP状态"""
        if ip not in self.ip_limits:
            return
        
        ip_limit = self.ip_limits[ip]
        
        if status_code == 429:
            # 速率限制
            retry_after = None
            if 'Retry-After' in headers:
                try:
                    retry_after = int(headers['Retry-After'])
                except ValueError:
                    pass
            
            ip_limit.handle_429_response(retry_after)
            logger.warning(f"IP {ip} 收到429响应，retry_after: {retry_after}")
            
        elif status_code == 418:
            # IP封禁
            retry_after = None
            if 'Retry-After' in headers:
                try:
                    retry_after = int(headers['Retry-After'])
                except ValueError:
                    pass
            
            ip_limit.handle_418_response(retry_after)
            
            # 触发IP轮换
            if self.config.auto_rotation:
                await self._rotate_ip()
        
        # 更新权重信息（从Binance响应头）
        for header_name, header_value in headers.items():
            if header_name.startswith('X-MBX-USED-WEIGHT-'):
                try:
                    used_weight = int(header_value)
                    # 这里可以更新我们对当前权重使用的估计
                    logger.debug(f"交易所报告的已使用权重: {used_weight}")
                except ValueError:
                    pass
        
        await self._save_ip_status(ip)
    
    async def _rotate_ip(self):
        """轮换到下一个可用IP"""
        current_index = 0
        all_ips = [self.config.primary_ip] + self.config.backup_ips
        
        try:
            current_index = all_ips.index(self.current_ip)
        except ValueError:
            pass
        
        # 寻找下一个可用IP
        for i in range(1, len(all_ips)):
            next_index = (current_index + i) % len(all_ips)
            next_ip = all_ips[next_index]
            next_limit = self.ip_limits[next_ip]
            
            if not next_limit.is_banned() and next_limit.status != IPStatus.BANNED:
                logger.info(f"自动轮换IP: {self.current_ip} -> {next_ip}")
                self.current_ip = next_ip
                return
        
        logger.warning("无法找到可用的备用IP进行轮换")
    
    async def _save_ip_status(self, ip: str):
        """保存IP状态到存储"""
        if ip in self.ip_limits:
            ip_data = {
                "current_requests": self.ip_limits[ip].current_requests,
                "current_weight": self.ip_limits[ip].current_weight,
                "current_orders_today": self.ip_limits[ip].current_orders_today,
                "status": self.ip_limits[ip].status.value,
                "warning_count": self.ip_limits[ip].warning_count,
                "last_reset_time": self.ip_limits[ip].last_reset_time,
                "ban_until": self.ip_limits[ip].ban_until or 0
            }
            
            key = f"rate_limit:ip_status:{ip}"
            await self.storage.set(key, json.dumps(ip_data), ttl=3600)
    
    async def get_ip_status_summary(self) -> Dict[str, Any]:
        """获取所有IP的状态摘要"""
        summary = {
            "current_ip": self.current_ip,
            "total_ips": len(self.ip_limits),
            "active_ips": 0,
            "banned_ips": 0,
            "warning_ips": 0,
            "ip_details": {}
        }
        
        for ip, limit in self.ip_limits.items():
            limit.reset_if_needed()
            
            status_detail = {
                "status": limit.status.value,
                "current_requests": limit.current_requests,
                "max_requests": limit.requests_per_minute,
                "current_weight": limit.current_weight,
                "max_weight": limit.weight_per_minute,
                "utilization_requests": limit.current_requests / limit.requests_per_minute,
                "utilization_weight": limit.current_weight / limit.weight_per_minute,
                "is_banned": limit.is_banned(),
                "warning_count": limit.warning_count,
                "orders_today": limit.current_orders_today
            }
            
            if limit.ban_until:
                status_detail["ban_until"] = limit.ban_until
                status_detail["ban_remaining"] = max(0, limit.ban_until - time.time())
            
            summary["ip_details"][ip] = status_detail
            
            # 统计计数
            if limit.status == IPStatus.ACTIVE:
                summary["active_ips"] += 1
            elif limit.status == IPStatus.BANNED:
                summary["banned_ips"] += 1
            elif limit.status == IPStatus.WARNING:
                summary["warning_ips"] += 1
        
        return summary


class IPAwareRateLimitCoordinator:
    """IP感知的分布式速率限制协调器"""
    
    def __init__(self, storage, ip_config: IPPoolConfig):
        self.storage = storage
        self.ip_manager = IPManager(ip_config, storage)
        self.client_id = str(uuid.uuid4())
        
        # 统计数据
        self.stats = {
            "total_requests": 0,
            "granted_requests": 0,
            "denied_requests": 0,
            "ip_switches": 0,
            "rate_limit_hits": 0,
            "ban_incidents": 0
        }
        
        logger.info(f"IP感知速率限制协调器已初始化，客户端ID: {self.client_id}")
    
    async def acquire_permit(self, exchange: ExchangeType, request_type: RequestType, weight: int = 1, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        获取API请求许可 - 完全基于IP限制
        
        这个方法体现了交易所文档中"访问限制是基于IP的"这一核心特性
        """
        self.stats["total_requests"] += 1
        
        # 检查当前IP是否可以发出请求
        can_request, ip, reason = await self.ip_manager.can_make_request(weight, exchange)
        
        if not can_request:
            self.stats["denied_requests"] += 1
            
            # 如果是因为当前IP限制，尝试轮换IP
            if "超过" in reason and self.ip_manager.config.auto_rotation:
                logger.info(f"当前IP {ip} 达到限制，尝试轮换")
                await self.ip_manager._rotate_ip()
                self.stats["ip_switches"] += 1
                
                # 再次检查新IP
                can_request, ip, reason = await self.ip_manager.can_make_request(weight, exchange)
        
        if can_request:
            # 消费请求
            is_order = request_type == RequestType.ORDER
            await self.ip_manager.consume_request(weight, is_order, ip)
            self.stats["granted_requests"] += 1
            
            return {
                "granted": True,
                "ip_address": ip,
                "exchange": exchange.value,
                "request_type": request_type.value,
                "weight": weight,
                "endpoint": endpoint,
                "reason": "Request permitted",
                "timestamp": time.time(),
                "client_id": self.client_id
            }
        else:
            self.stats["denied_requests"] += 1
            self.stats["rate_limit_hits"] += 1
            
            return {
                "granted": False,
                "ip_address": ip,
                "exchange": exchange.value,
                "request_type": request_type.value,
                "weight": weight,
                "endpoint": endpoint,
                "reason": reason,
                "timestamp": time.time(),
                "client_id": self.client_id
            }
    
    async def report_exchange_response(self, status_code: int, headers: Dict[str, str], ip: str):
        """
        报告交易所响应，用于更新IP状态
        
        这个方法处理交易所返回的速率限制信息，体现了IP级别的限制监控
        """
        await self.ip_manager.handle_exchange_response(status_code, headers, ip)
        
        if status_code == 418:
            self.stats["ban_incidents"] += 1
    
    async def get_current_ip(self) -> str:
        """获取当前使用的IP地址"""
        return await self.ip_manager.get_current_ip()
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态，包含详细的IP级别信息"""
        ip_summary = await self.ip_manager.get_ip_status_summary()
        
        return {
            "coordinator_info": {
                "client_id": self.client_id,
                "mode": "ip_aware",
                "statistics": self.stats.copy()
            },
            "ip_management": ip_summary,
            "current_ip": ip_summary["current_ip"],
            "ip_availability": {
                "total": ip_summary["total_ips"],
                "active": ip_summary["active_ips"],
                "banned": ip_summary["banned_ips"],
                "warnings": ip_summary["warning_ips"]
            },
            "timestamp": time.time()
        }


# 工厂函数
async def create_ip_aware_coordinator(
    primary_ip: str,
    backup_ips: Optional[List[str]] = None,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 3
) -> IPAwareRateLimitCoordinator:
    """
    创建IP感知的速率限制协调器
    
    Args:
        primary_ip: 主要IP地址
        backup_ips: 备用IP地址列表
        redis_host: Redis主机
        redis_port: Redis端口
        redis_db: Redis数据库
    """
    # 创建存储
    try:
        if REDIS_AVAILABLE:
            redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}/{redis_db}")
            await redis_client.ping()
            from .distributed_rate_limit_coordinator import RedisDistributedStorage
            storage = RedisDistributedStorage(redis_client)
        else:
            from .distributed_rate_limit_coordinator import InMemoryDistributedStorage
            storage = InMemoryDistributedStorage()
    except Exception as e:
        logger.error(f"Redis连接失败: {e}, 使用内存存储")
        from .distributed_rate_limit_coordinator import InMemoryDistributedStorage
        storage = InMemoryDistributedStorage()
    
    # 创建IP配置
    ip_config = IPPoolConfig(
        primary_ip=primary_ip,
        backup_ips=backup_ips or [],
        auto_rotation=True
    )
    
    coordinator = IPAwareRateLimitCoordinator(storage, ip_config)
    
    logger.info(f"IP感知协调器已创建，主IP: {primary_ip}, 备用IP: {backup_ips}")
    return coordinator


# 便利函数
async def get_external_ip() -> str:
    """获取当前的外部IP地址"""
    try:
        if REQUESTS_AVAILABLE:
            response = requests.get('https://api.ipify.org', timeout=5)
            return response.text.strip()
        else:
            # 简单的socket方式获取本地IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
    except Exception as e:
        logger.error(f"获取外部IP失败: {e}")
        return "127.0.0.1"


# 全局实例
_global_ip_coordinator: Optional[IPAwareRateLimitCoordinator] = None


async def get_global_ip_coordinator() -> IPAwareRateLimitCoordinator:
    """获取全局IP感知协调器"""
    global _global_ip_coordinator
    if _global_ip_coordinator is None:
        current_ip = await get_external_ip()
        _global_ip_coordinator = await create_ip_aware_coordinator(current_ip)
    return _global_ip_coordinator


# 便利API函数（体现IP限制特性）
async def acquire_ip_aware_permit(exchange: str, request_type: str = "rest_public", weight: int = 1, endpoint: Optional[str] = None) -> Dict[str, Any]:
    """
    获取IP感知的API请求许可
    
    这个函数完全体现了"访问限制是基于IP的"这一特性
    """
    coordinator = await get_global_ip_coordinator()
    
    result = await coordinator.acquire_permit(
        exchange=ExchangeType(exchange.lower()),
        request_type=RequestType(request_type.lower()),
        weight=weight,
        endpoint=endpoint
    )
    
    return result


async def get_ip_status() -> Dict[str, Any]:
    """获取IP状态信息"""
    coordinator = await get_global_ip_coordinator()
    return await coordinator.get_system_status()


if __name__ == "__main__":
    # 演示IP感知速率限制的使用
    async def demo_ip_aware_rate_limiting():
        print("=== IP感知速率限制演示 ===")
        
        # 创建协调器（模拟多IP环境）
        coordinator = await create_ip_aware_coordinator(
            primary_ip="192.168.1.100",
            backup_ips=["192.168.1.101", "192.168.1.102"]
        )
        
        print(f"当前使用IP: {await coordinator.get_current_ip()}")
        
        # 模拟多个请求
        for i in range(10):
            result = await coordinator.acquire_permit(
                ExchangeType.BINANCE,
                RequestType.REST_PUBLIC,
                weight=1
            )
            
            print(f"请求 {i+1}: {'✓' if result['granted'] else '✗'} IP: {result['ip_address']}")
            
            # 模拟收到429响应
            if i == 5:
                await coordinator.report_exchange_response(
                    status_code=429,
                    headers={"Retry-After": "60"},
                    ip=result['ip_address']
                )
                print("  收到429响应，IP状态已更新")
        
        # 显示最终状态
        status = await coordinator.get_system_status()
        print("\n=== 系统状态 ===")
        print(f"当前IP: {status['current_ip']}")
        print(f"IP可用性: {status['ip_availability']}")
        print(f"统计: {status['coordinator_info']['statistics']}")
    
    # 运行演示
    asyncio.run(demo_ip_aware_rate_limiting())