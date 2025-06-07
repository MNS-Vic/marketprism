"""
MarketPrism 交易所API统一代理

优雅的解决方案：
1. 统一收口所有交易所API请求
2. 自动检测IP环境并选择最佳模式
3. 集成动态权重计算和速率限制
4. 智能处理429/418错误和超限响应
5. 零侵入性集成到现有代码

设计原则：简单、优雅、可靠
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import aiohttp
from pathlib import Path

# 导入现有核心组件
try:
    from .unified_session_manager import UnifiedSessionManager
except ImportError:
    # 简化版会话管理器
    class UnifiedSessionManager:
        def get_session(self):
            return aiohttp.ClientSession()

try:
    from ..storage.unified_clickhouse_writer import UnifiedClickHouseWriter
except ImportError:
    UnifiedClickHouseWriter = None

try:
    from config.core.weight_config_loader import get_weight_config
except ImportError:
    def get_weight_config():
        return {}

try:
    from config.core.dynamic_weight_calculator import DynamicWeightCalculator
except ImportError:
    # 简化版权重计算器
    class DynamicWeightCalculator:
        def calculate_weight(self, exchange, endpoint, params):
            # 基础权重映射
            weight_map = {
                '/api/v3/ping': 1,
                '/api/v3/time': 1,
                '/api/v3/ticker/24hr': 1,
                '/api/v3/ticker/price': 1,
                '/api/v3/depth': 1,
                '/api/v3/exchangeInfo': 10
            }
            return weight_map.get(endpoint, 1)

logger = logging.getLogger(__name__)


class ProxyMode(Enum):
    """代理模式"""
    AUTO = "auto"           # 自动检测
    UNIFIED = "unified"     # 统一代理模式（单IP）
    DISTRIBUTED = "distributed"  # 分布式模式（多IP）


@dataclass
class IPResource:
    """IP资源信息"""
    ip: str
    location: Optional[str] = None
    provider: Optional[str] = None
    max_weight_per_minute: int = 6000
    current_weight: int = 0
    last_reset: datetime = field(default_factory=datetime.now)
    banned_until: Optional[datetime] = None
    health_score: float = 1.0  # 0.0-1.0
    
    @property
    def is_available(self) -> bool:
        """检查IP是否可用"""
        now = datetime.now()
        
        # 检查是否被封禁
        if self.banned_until and now < self.banned_until:
            return False
        
        # 检查权重是否超限
        if self.current_weight >= self.max_weight_per_minute * 0.9:  # 90%阈值
            return False
        
        return True
    
    def reset_weight_if_needed(self):
        """如果需要重置权重"""
        now = datetime.now()
        if now - self.last_reset >= timedelta(minutes=1):
            self.current_weight = 0
            self.last_reset = now
    
    def consume_weight(self, weight: int) -> bool:
        """消费权重，返回是否成功"""
        self.reset_weight_if_needed()
        
        if self.current_weight + weight <= self.max_weight_per_minute:
            self.current_weight += weight
            return True
        return False
    
    def handle_rate_limit_response(self, status_code: int, retry_after: Optional[int] = None):
        """处理速率限制响应"""
        now = datetime.now()
        
        if status_code == 429:  # 警告
            self.health_score *= 0.8  # 降低健康分数
            if retry_after:
                # 临时暂停使用
                self.banned_until = now + timedelta(seconds=retry_after)
                
        elif status_code == 418:  # IP封禁
            self.health_score = 0.1  # 严重降低健康分数
            if retry_after:
                self.banned_until = now + timedelta(seconds=retry_after)
            else:
                # 默认封禁2分钟
                self.banned_until = now + timedelta(minutes=2)


@dataclass
class RequestRecord:
    """请求记录"""
    timestamp: datetime
    exchange: str
    endpoint: str
    method: str
    weight: int
    status_code: int
    response_time: float
    ip_used: str
    error: Optional[str] = None


class ExchangeAPIProxy:
    """交易所API统一代理"""
    
    def __init__(self, mode: ProxyMode = ProxyMode.AUTO):
        self.mode = mode
        self.session_manager = UnifiedSessionManager()
        self.weight_calculator = DynamicWeightCalculator()
        
        # IP资源管理
        self.ip_resources: Dict[str, IPResource] = {}
        self.current_ip_index = 0
        
        # 请求统计
        self.request_records: List[RequestRecord] = []
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'rate_limited_requests': 0,
            'banned_ips': 0,
            'average_response_time': 0.0,
            'requests_by_exchange': {},
            'weight_consumed_by_exchange': {}
        }
        
        # 监控配置
        self.max_record_history = 10000
        self.health_check_interval = 60  # 秒
        self._pending_auto_detect = False
        
        # 自动检测IP环境
        if self.mode == ProxyMode.AUTO:
            try:
                asyncio.create_task(self._auto_detect_environment())
            except RuntimeError:
                # 没有运行中的事件循环，延迟执行
                self._pending_auto_detect = True
        
        logger.info(f"ExchangeAPIProxy 初始化完成，模式: {self.mode.value}")
    
    @classmethod
    def auto_configure(cls) -> "ExchangeAPIProxy":
        """自动配置代理（最简单的使用方式）"""
        return cls(ProxyMode.AUTO)
    
    @classmethod
    def unified_mode(cls, ip: Optional[str] = None) -> "ExchangeAPIProxy":
        """统一代理模式"""
        proxy = cls(ProxyMode.UNIFIED)
        if ip:
            proxy.add_ip_resource(ip)
        return proxy
    
    @classmethod
    def distributed_mode(cls, ips: List[str]) -> "ExchangeAPIProxy":
        """分布式代理模式"""
        proxy = cls(ProxyMode.DISTRIBUTED)
        for ip in ips:
            proxy.add_ip_resource(ip)
        return proxy
    
    async def _auto_detect_environment(self):
        """自动检测环境并配置IP资源"""
        try:
            # 检测本机外网IP
            async with aiohttp.ClientSession() as session:
                async with session.get('https://httpbin.org/ip', timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        current_ip = data.get('origin', '').split(',')[0].strip()
                        self.add_ip_resource(current_ip, "auto-detected")
                        logger.info(f"自动检测到IP: {current_ip}")
        except Exception as e:
            logger.warning(f"自动IP检测失败: {e}")
            # 使用默认配置
            self.add_ip_resource("127.0.0.1", "fallback")
    
    def add_ip_resource(self, ip: str, location: Optional[str] = None):
        """添加IP资源"""
        if ip not in self.ip_resources:
            self.ip_resources[ip] = IPResource(ip=ip, location=location)
            logger.info(f"添加IP资源: {ip} ({location})")
    
    def get_best_ip(self, exchange: str) -> Optional[IPResource]:
        """获取最佳IP资源"""
        available_ips = [ip for ip in self.ip_resources.values() if ip.is_available]
        
        if not available_ips:
            logger.error("没有可用的IP资源")
            return None
        
        # 简单策略：选择健康分数最高且权重使用最少的IP
        best_ip = max(available_ips, key=lambda ip: (
            ip.health_score, 
            (ip.max_weight_per_minute - ip.current_weight)
        ))
        
        return best_ip
    
    async def request(self, 
                     exchange: str, 
                     method: str, 
                     endpoint: str, 
                     params: Optional[Dict[str, Any]] = None,
                     **kwargs) -> Dict[str, Any]:
        """
        统一API请求入口
        
        Args:
            exchange: 交易所名称 (binance, okx, deribit)
            method: HTTP方法 (GET, POST, etc.)
            endpoint: API端点 (/api/v3/ticker/24hr)
            params: 请求参数
            **kwargs: 其他参数
        
        Returns:
            API响应数据
        """
        start_time = time.time()
        params = params or {}
        
        # 获取最佳IP
        ip_resource = self.get_best_ip(exchange)
        if not ip_resource:
            raise Exception("没有可用的IP资源")
        
        # 计算请求权重
        weight = self.weight_calculator.calculate_weight(exchange, endpoint, params)
        
        # 检查权重是否可用
        if not ip_resource.consume_weight(weight):
            # 权重不足，等待或切换IP
            if self.mode == ProxyMode.DISTRIBUTED:
                # 尝试其他IP
                for other_ip in self.ip_resources.values():
                    if other_ip != ip_resource and other_ip.is_available and other_ip.consume_weight(weight):
                        ip_resource = other_ip
                        break
                else:
                    raise Exception(f"所有IP权重已耗尽，需要等待重置")
            else:
                raise Exception(f"IP {ip_resource.ip} 权重不足，需要等待重置")
        
        # 发送请求
        try:
            response = await self._send_request(
                exchange, method, endpoint, params, ip_resource, **kwargs
            )
            
            # 处理响应
            response_time = time.time() - start_time
            await self._handle_response(exchange, endpoint, method, weight, 
                                      ip_resource, response, response_time)
            
            return response
            
        except Exception as e:
            # 处理错误
            response_time = time.time() - start_time
            await self._handle_error(exchange, endpoint, method, weight, 
                                   ip_resource, e, response_time)
            raise
    
    async def _send_request(self, 
                          exchange: str, 
                          method: str, 
                          endpoint: str, 
                          params: Dict[str, Any],
                          ip_resource: IPResource,
                          **kwargs) -> Dict[str, Any]:
        """发送HTTP请求"""
        # 构建请求URL
        base_urls = {
            'binance': 'https://api.binance.com',
            'okx': 'https://www.okx.com',
            'deribit': 'https://www.deribit.com'
        }
        
        base_url = base_urls.get(exchange.lower())
        if not base_url:
            raise ValueError(f"不支持的交易所: {exchange}")
        
        url = f"{base_url}{endpoint}"
        
        # 使用统一会话管理器发送请求
        async with self.session_manager.get_session() as session:
            request_kwargs = {
                'params': params if method.upper() == 'GET' else None,
                'json': params if method.upper() != 'GET' else None,
                **kwargs
            }
            
            async with session.request(method, url, **request_kwargs) as response:
                # 检查响应状态
                if response.status in [429, 418]:
                    # 速率限制或IP封禁
                    retry_after = response.headers.get('Retry-After')
                    retry_after = int(retry_after) if retry_after else None
                    
                    ip_resource.handle_rate_limit_response(response.status, retry_after)
                    
                    error_data = {
                        'status': response.status,
                        'retry_after': retry_after,
                        'headers': dict(response.headers),
                        'message': await response.text()
                    }
                    
                    if response.status == 429:
                        raise aiohttp.ClientResponseError(
                            response.request_info, 
                            response.history,
                            message=f"速率限制警告 (429): {error_data['message']}"
                        )
                    else:  # 418
                        raise aiohttp.ClientResponseError(
                            response.request_info, 
                            response.history,
                            message=f"IP被封禁 (418): {error_data['message']}"
                        )
                
                response.raise_for_status()
                return await response.json()
    
    async def _handle_response(self, 
                             exchange: str, 
                             endpoint: str, 
                             method: str, 
                             weight: int,
                             ip_resource: IPResource, 
                             response: Dict[str, Any], 
                             response_time: float):
        """处理成功响应"""
        # 记录请求
        record = RequestRecord(
            timestamp=datetime.now(),
            exchange=exchange,
            endpoint=endpoint,
            method=method,
            weight=weight,
            status_code=200,
            response_time=response_time,
            ip_used=ip_resource.ip
        )
        
        self._add_request_record(record)
        
        # 更新统计
        self.stats['total_requests'] += 1
        self.stats['successful_requests'] += 1
        self.stats['requests_by_exchange'][exchange] = \
            self.stats['requests_by_exchange'].get(exchange, 0) + 1
        self.stats['weight_consumed_by_exchange'][exchange] = \
            self.stats['weight_consumed_by_exchange'].get(exchange, 0) + weight
        
        # 更新平均响应时间
        total_time = self.stats['average_response_time'] * (self.stats['total_requests'] - 1)
        self.stats['average_response_time'] = (total_time + response_time) / self.stats['total_requests']
        
        # 提升IP健康分数
        ip_resource.health_score = min(1.0, ip_resource.health_score + 0.01)
        
        logger.debug(f"请求成功: {exchange} {method} {endpoint}, "
                    f"权重: {weight}, 响应时间: {response_time:.3f}s, IP: {ip_resource.ip}")
    
    async def _handle_error(self, 
                          exchange: str, 
                          endpoint: str, 
                          method: str, 
                          weight: int,
                          ip_resource: IPResource, 
                          error: Exception, 
                          response_time: float):
        """处理请求错误"""
        # 确定状态码
        status_code = 500
        error_str = ""
        try:
            error_str = str(error)
            if hasattr(error, 'status') and error.status:
                status_code = error.status
            elif "429" in error_str:
                status_code = 429
            elif "418" in error_str:
                status_code = 418
        except Exception:
            error_str = f"{type(error).__name__}: {repr(error)}"
        
        # 记录请求
        record = RequestRecord(
            timestamp=datetime.now(),
            exchange=exchange,
            endpoint=endpoint,
            method=method,
            weight=weight,
            status_code=status_code,
            response_time=response_time,
            ip_used=ip_resource.ip,
            error=error_str
        )
        
        self._add_request_record(record)
        
        # 更新统计
        self.stats['total_requests'] += 1
        self.stats['failed_requests'] += 1
        
        if status_code in [429, 418]:
            self.stats['rate_limited_requests'] += 1
            if status_code == 418:
                self.stats['banned_ips'] += 1
        
        logger.error(f"请求失败: {exchange} {method} {endpoint}, "
                    f"错误: {error}, IP: {ip_resource.ip}")
    
    def _add_request_record(self, record: RequestRecord):
        """添加请求记录"""
        self.request_records.append(record)
        
        # 保持记录数量在限制内
        if len(self.request_records) > self.max_record_history:
            self.request_records = self.request_records[-self.max_record_history:]
    
    def get_status(self) -> Dict[str, Any]:
        """获取代理状态"""
        now = datetime.now()
        
        # IP状态
        ip_status = {}
        for ip, resource in self.ip_resources.items():
            ip_status[ip] = {
                'available': resource.is_available,
                'current_weight': resource.current_weight,
                'max_weight': resource.max_weight_per_minute,
                'weight_usage': f"{resource.current_weight / resource.max_weight_per_minute * 100:.1f}%",
                'health_score': f"{resource.health_score:.2f}",
                'banned_until': resource.banned_until.isoformat() if resource.banned_until else None,
                'location': resource.location
            }
        
        # 最近请求统计
        recent_records = [r for r in self.request_records if now - r.timestamp < timedelta(minutes=5)]
        recent_success_rate = 0
        if recent_records:
            recent_success = len([r for r in recent_records if r.status_code == 200])
            recent_success_rate = recent_success / len(recent_records) * 100
        
        return {
            'mode': self.mode.value,
            'total_ips': len(self.ip_resources),
            'available_ips': len([ip for ip in self.ip_resources.values() if ip.is_available]),
            'ip_details': ip_status,
            'statistics': self.stats,
            'recent_success_rate': f"{recent_success_rate:.1f}%",
            'recent_requests_count': len(recent_records),
            'total_weight_consumed': sum(self.stats['weight_consumed_by_exchange'].values()),
            'uptime_seconds': time.time() - getattr(self, '_start_time', time.time())
        }
    
    def get_health_report(self) -> Dict[str, Any]:
        """获取健康报告"""
        now = datetime.now()
        
        # 分析最近的错误
        recent_errors = [r for r in self.request_records 
                        if r.error and now - r.timestamp < timedelta(hours=1)]
        
        error_analysis = {}
        for record in recent_errors:
            key = f"{record.exchange}_{record.status_code}"
            if key not in error_analysis:
                error_analysis[key] = {
                    'count': 0,
                    'latest_time': None,
                    'sample_error': None
                }
            
            error_analysis[key]['count'] += 1
            error_analysis[key]['latest_time'] = record.timestamp
            if not error_analysis[key]['sample_error']:
                error_analysis[key]['sample_error'] = record.error
        
        # 性能分析
        successful_records = [r for r in self.request_records 
                            if r.status_code == 200 and now - r.timestamp < timedelta(hours=1)]
        
        avg_response_time = 0
        if successful_records:
            avg_response_time = sum(r.response_time for r in successful_records) / len(successful_records)
        
        return {
            'overall_health': 'healthy' if self.stats['successful_requests'] > self.stats['failed_requests'] else 'degraded',
            'error_analysis': error_analysis,
            'performance': {
                'average_response_time': f"{avg_response_time:.3f}s",
                'total_requests_last_hour': len([r for r in self.request_records if now - r.timestamp < timedelta(hours=1)]),
                'success_rate_last_hour': f"{len(successful_records) / max(1, len([r for r in self.request_records if now - r.timestamp < timedelta(hours=1)])) * 100:.1f}%"
            },
            'recommendations': self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 检查IP健康状态
        unhealthy_ips = [ip for ip in self.ip_resources.values() if ip.health_score < 0.5]
        if unhealthy_ips:
            recommendations.append(f"发现 {len(unhealthy_ips)} 个IP健康状态较差，建议检查网络连接")
        
        # 检查权重使用
        high_usage_ips = [ip for ip in self.ip_resources.values() 
                         if ip.current_weight / ip.max_weight_per_minute > 0.8]
        if high_usage_ips:
            recommendations.append(f"发现 {len(high_usage_ips)} 个IP权重使用率超过80%，建议添加更多IP资源")
        
        # 检查错误率
        if self.stats['failed_requests'] / max(1, self.stats['total_requests']) > 0.1:
            recommendations.append("错误率超过10%，建议检查API配置和网络状况")
        
        # 检查速率限制
        if self.stats['rate_limited_requests'] > 0:
            recommendations.append("检测到速率限制警告，建议降低请求频率或增加IP资源")
        
        return recommendations or ["系统运行良好，无特殊建议"]


# 便利函数
_global_proxy: Optional[ExchangeAPIProxy] = None

def get_exchange_proxy() -> ExchangeAPIProxy:
    """获取全局交易所代理实例"""
    global _global_proxy
    if _global_proxy is None:
        _global_proxy = ExchangeAPIProxy.auto_configure()
    return _global_proxy

async def proxy_request(exchange: str, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """便利函数：发送代理请求"""
    proxy = get_exchange_proxy()
    return await proxy.request(exchange, method, endpoint, params, **kwargs)


if __name__ == "__main__":
    # 测试代码
    async def test_proxy():
        print("🚀 MarketPrism 交易所API代理测试")
        print("=" * 50)
        
        # 自动配置代理
        proxy = ExchangeAPIProxy.auto_configure()
        
        # 添加测试IP
        proxy.add_ip_resource("192.168.1.100", "测试IP-1")
        proxy.add_ip_resource("192.168.1.101", "测试IP-2")
        
        try:
            # 测试请求
            print("\n📡 测试API请求...")
            
            # 模拟Binance请求
            response = await proxy.request(
                exchange="binance",
                method="GET", 
                endpoint="/api/v3/ping",
                params={}
            )
            print(f"✅ Binance ping成功: {response}")
            
        except Exception as e:
            print(f"❌ 请求失败: {e}")
        
        # 显示状态
        print(f"\n📊 代理状态:")
        status = proxy.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        
        # 健康报告
        print(f"\n🏥 健康报告:")
        health = proxy.get_health_report()
        print(json.dumps(health, indent=2, ensure_ascii=False))
        
        print("\n✅ 测试完成")
    
    # 运行测试
    asyncio.run(test_proxy())