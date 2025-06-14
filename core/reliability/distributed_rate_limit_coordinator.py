"""
MarketPrism 分布式速率限制协调器

解决多进程/多服务共享API速率限制的问题，确保整个系统不会超过交易所的速率限制。

核心功能：
1. 集中式速率限制管理
2. 分布式令牌桶算法
3. 公平资源分配
4. 动态配额调整
5. 故障恢复机制
6. 实时监控和告警

主要组件：
- DistributedRateLimitCoordinator: 分布式速率限制协调器
- TokenBucketManager: 分布式令牌桶管理器
- QuotaAllocator: 配额分配器
- ClientRegistrar: 客户端注册器
- MonitoringAgent: 监控代理
"""

import asyncio
import time
import json
import uuid
import hashlib
import os
from typing import Dict, List, Optional, Any, Union, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta, timezone
import logging
from abc import ABC, abstractmethod

try:
    import aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False


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


@dataclass
class ExchangeRateLimit:
    """交易所速率限制配置"""
    exchange: ExchangeType
    # REST API限制
    rest_requests_per_minute: int = 1200    # 每分钟REST请求数
    rest_weight_per_minute: int = 6000      # 每分钟权重限制
    order_requests_per_second: int = 10     # 每秒订单请求数
    order_requests_per_day: int = 200000    # 每日订单请求数
    
    # WebSocket限制
    websocket_connections_per_ip: int = 5   # 每IP WebSocket连接数
    websocket_subscriptions_per_connection: int = 1024  # 每连接订阅数
    
    # 特殊端点限制
    endpoint_limits: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # 惩罚机制
    ban_duration_seconds: int = 3600        # 被ban时长
    warning_threshold: float = 0.8          # 警告阈值
    
    @classmethod
    def get_binance_limits(cls) -> 'ExchangeRateLimit':
        """获取Binance限制配置"""
        return cls(
            exchange=ExchangeType.BINANCE,
            rest_requests_per_minute=1200,
            rest_weight_per_minute=6000,
            order_requests_per_second=10,
            order_requests_per_day=200000,
            websocket_connections_per_ip=5,
            endpoint_limits={
                "/api/v3/order": {"requests_per_second": 10, "weight": 1},
                "/api/v3/ticker/24hr": {"requests_per_minute": 40, "weight": 1},
                "/api/v3/depth": {"requests_per_minute": 6000, "weight": 1}
            }
        )
    
    @classmethod
    def get_okx_limits(cls) -> 'ExchangeRateLimit':
        """获取OKX限制配置"""
        return cls(
            exchange=ExchangeType.OKX,
            rest_requests_per_minute=600,
            rest_weight_per_minute=3000,
            order_requests_per_second=5,
            order_requests_per_day=100000,
            websocket_connections_per_ip=5
        )
    
    @classmethod
    def get_deribit_limits(cls) -> 'ExchangeRateLimit':
        """获取Deribit限制配置"""
        return cls(
            exchange=ExchangeType.DERIBIT,
            rest_requests_per_minute=300,
            rest_weight_per_minute=1500,
            order_requests_per_second=20,
            order_requests_per_day=500000,
            websocket_connections_per_ip=100
        )


@dataclass
class ClientInfo:
    """客户端信息"""
    client_id: str
    process_id: str
    service_name: str
    priority: int = 1                       # 优先级 1-10
    allocated_quota: Dict[str, float] = field(default_factory=dict)
    last_heartbeat: float = field(default_factory=time.time)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimitRequest:
    """速率限制请求"""
    client_id: str
    exchange: ExchangeType
    request_type: RequestType
    endpoint: Optional[str] = None
    weight: int = 1
    priority: int = 1
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)


@dataclass
class RateLimitResponse:
    """速率限制响应"""
    granted: bool
    client_id: str
    request_id: str
    wait_time: float = 0.0
    remaining_quota: float = 0.0
    total_quota: float = 0.0
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


class DistributedStorage(ABC):
    """分布式存储抽象接口"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """获取值"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """设置值"""
        pass
    
    @abstractmethod
    async def increment(self, key: str, amount: float = 1) -> float:
        """原子递增"""
        pass
    
    @abstractmethod
    async def hash_get(self, key: str, field: str) -> Optional[str]:
        """获取哈希字段"""
        pass
    
    @abstractmethod
    async def hash_set(self, key: str, field: str, value: str) -> bool:
        """设置哈希字段"""
        pass
    
    @abstractmethod
    async def hash_get_all(self, key: str) -> Dict[str, str]:
        """获取所有哈希字段"""
        pass
    
    @abstractmethod
    async def list_append(self, key: str, value: str) -> int:
        """追加到列表"""
        pass
    
    @abstractmethod
    async def list_range(self, key: str, start: int, end: int) -> List[str]:
        """获取列表范围"""
        pass
    
    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        """设置过期时间"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除键"""
        pass


class RedisDistributedStorage(DistributedStorage):
    """Redis分布式存储实现"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get(self, key: str) -> Optional[str]:
        try:
            result = await self.redis.get(key)
            return result.decode() if result else None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        try:
            if ttl:
                await self.redis.setex(key, ttl, value)
            else:
                await self.redis.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    async def increment(self, key: str, amount: float = 1) -> float:
        try:
            if amount == 1:
                return await self.redis.incr(key)
            else:
                return await self.redis.incrbyfloat(key, amount)
        except Exception as e:
            logger.error(f"Redis increment error: {e}")
            return 0
    
    async def hash_get(self, key: str, field: str) -> Optional[str]:
        try:
            result = await self.redis.hget(key, field)
            return result.decode() if result else None
        except Exception as e:
            logger.error(f"Redis hget error: {e}")
            return None
    
    async def hash_set(self, key: str, field: str, value: str) -> bool:
        try:
            await self.redis.hset(key, field, value)
            return True
        except Exception as e:
            logger.error(f"Redis hset error: {e}")
            return False
    
    async def hash_get_all(self, key: str) -> Dict[str, str]:
        try:
            result = await self.redis.hgetall(key)
            return {k.decode(): v.decode() for k, v in result.items()}
        except Exception as e:
            logger.error(f"Redis hgetall error: {e}")
            return {}
    
    async def list_append(self, key: str, value: str) -> int:
        try:
            return await self.redis.rpush(key, value)
        except Exception as e:
            logger.error(f"Redis rpush error: {e}")
            return 0
    
    async def list_range(self, key: str, start: int, end: int) -> List[str]:
        try:
            result = await self.redis.lrange(key, start, end)
            return [item.decode() for item in result]
        except Exception as e:
            logger.error(f"Redis lrange error: {e}")
            return []
    
    async def expire(self, key: str, ttl: int) -> bool:
        try:
            await self.redis.expire(key, ttl)
            return True
        except Exception as e:
            logger.error(f"Redis expire error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False


class InMemoryDistributedStorage(DistributedStorage):
    """内存分布式存储实现（用于测试和降级）"""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.expiry: Dict[str, float] = {}
        self.lock = asyncio.Lock()
    
    async def _cleanup_expired(self):
        """清理过期数据"""
        current_time = time.time()
        expired_keys = [k for k, exp_time in self.expiry.items() if current_time > exp_time]
        for key in expired_keys:
            self.data.pop(key, None)
            self.expiry.pop(key, None)
    
    async def get(self, key: str) -> Optional[str]:
        async with self.lock:
            await self._cleanup_expired()
            return self.data.get(key)
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        async with self.lock:
            self.data[key] = value
            if ttl:
                self.expiry[key] = time.time() + ttl
            return True
    
    async def increment(self, key: str, amount: float = 1) -> float:
        async with self.lock:
            await self._cleanup_expired()
            current = float(self.data.get(key, 0))
            new_value = current + amount
            self.data[key] = str(new_value)
            return new_value
    
    async def hash_get(self, key: str, field: str) -> Optional[str]:
        async with self.lock:
            await self._cleanup_expired()
            hash_data = self.data.get(key, {})
            if isinstance(hash_data, dict):
                return hash_data.get(field)
            return None
    
    async def hash_set(self, key: str, field: str, value: str) -> bool:
        async with self.lock:
            if key not in self.data:
                self.data[key] = {}
            if isinstance(self.data[key], dict):
                self.data[key][field] = value
                return True
            return False
    
    async def hash_get_all(self, key: str) -> Dict[str, str]:
        async with self.lock:
            await self._cleanup_expired()
            hash_data = self.data.get(key, {})
            return hash_data if isinstance(hash_data, dict) else {}
    
    async def list_append(self, key: str, value: str) -> int:
        async with self.lock:
            if key not in self.data:
                self.data[key] = []
            if isinstance(self.data[key], list):
                self.data[key].append(value)
                return len(self.data[key])
            return 0
    
    async def list_range(self, key: str, start: int, end: int) -> List[str]:
        async with self.lock:
            await self._cleanup_expired()
            list_data = self.data.get(key, [])
            if isinstance(list_data, list):
                return list_data[start:end+1] if end >= 0 else list_data[start:]
            return []
    
    async def expire(self, key: str, ttl: int) -> bool:
        async with self.lock:
            if key in self.data:
                self.expiry[key] = time.time() + ttl
                return True
            return False
    
    async def delete(self, key: str) -> bool:
        async with self.lock:
            if key in self.data:
                del self.data[key]
                self.expiry.pop(key, None)
                return True
            return False


class TokenBucketManager:
    """分布式令牌桶管理器"""
    
    def __init__(self, storage: DistributedStorage, exchange_limits: Dict[ExchangeType, ExchangeRateLimit]):
        self.storage = storage
        self.exchange_limits = exchange_limits
        self.bucket_prefix = "rate_limit:bucket:"
        self.last_refill_prefix = "rate_limit:last_refill:"
    
    async def _get_bucket_key(self, exchange: ExchangeType, request_type: RequestType) -> str:
        """获取令牌桶键"""
        return f"{self.bucket_prefix}{exchange.value}:{request_type.value}"
    
    async def _get_last_refill_key(self, exchange: ExchangeType, request_type: RequestType) -> str:
        """获取最后填充时间键"""
        return f"{self.last_refill_prefix}{exchange.value}:{request_type.value}"
    
    async def _get_bucket_capacity(self, exchange: ExchangeType, request_type: RequestType) -> int:
        """获取令牌桶容量"""
        if exchange not in self.exchange_limits:
            return 100  # 默认值
        
        limits = self.exchange_limits[exchange]
        if request_type == RequestType.REST_PUBLIC:
            return limits.rest_requests_per_minute
        elif request_type == RequestType.ORDER:
            return limits.order_requests_per_second * 60  # 转换为每分钟
        else:
            return limits.rest_requests_per_minute
    
    async def _get_refill_rate(self, exchange: ExchangeType, request_type: RequestType) -> float:
        """获取令牌填充速率（每秒）"""
        capacity = await self._get_bucket_capacity(exchange, request_type)
        if request_type == RequestType.ORDER:
            return self.exchange_limits[exchange].order_requests_per_second
        else:
            return capacity / 60.0  # 转换为每秒
    
    async def consume_tokens(self, exchange: ExchangeType, request_type: RequestType, tokens: int = 1) -> Tuple[bool, float]:
        """
        消费令牌
        
        Returns:
            Tuple[bool, float]: (是否成功, 剩余令牌数)
        """
        bucket_key = await self._get_bucket_key(exchange, request_type)
        last_refill_key = await self._get_last_refill_key(exchange, request_type)
        
        current_time = time.time()
        capacity = await self._get_bucket_capacity(exchange, request_type)
        refill_rate = await self._get_refill_rate(exchange, request_type)
        
        # 获取当前令牌数和最后填充时间
        current_tokens_str = await self.storage.get(bucket_key)
        last_refill_str = await self.storage.get(last_refill_key)
        
        current_tokens = float(current_tokens_str) if current_tokens_str else capacity
        last_refill = float(last_refill_str) if last_refill_str else current_time
        
        # 计算需要添加的令牌
        time_passed = current_time - last_refill
        tokens_to_add = time_passed * refill_rate
        current_tokens = min(capacity, current_tokens + tokens_to_add)
        
        # 检查是否有足够的令牌
        if current_tokens >= tokens:
            # 消费令牌
            current_tokens -= tokens
            
            # 更新存储
            await self.storage.set(bucket_key, str(current_tokens), 3600)
            await self.storage.set(last_refill_key, str(current_time), 3600)
            
            return True, current_tokens
        else:
            # 令牌不足，只更新时间
            await self.storage.set(bucket_key, str(current_tokens), 3600)
            await self.storage.set(last_refill_key, str(current_time), 3600)
            
            return False, current_tokens
    
    async def get_bucket_status(self, exchange: ExchangeType, request_type: RequestType) -> Dict[str, Any]:
        """获取令牌桶状态"""
        bucket_key = await self._get_bucket_key(exchange, request_type)
        last_refill_key = await self._get_last_refill_key(exchange, request_type)
        
        current_time = time.time()
        capacity = await self._get_bucket_capacity(exchange, request_type)
        refill_rate = await self._get_refill_rate(exchange, request_type)
        
        current_tokens_str = await self.storage.get(bucket_key)
        last_refill_str = await self.storage.get(last_refill_key)
        
        current_tokens = float(current_tokens_str) if current_tokens_str else capacity
        last_refill = float(last_refill_str) if last_refill_str else current_time
        
        # 计算实时令牌数
        time_passed = current_time - last_refill
        tokens_to_add = time_passed * refill_rate
        real_time_tokens = min(capacity, current_tokens + tokens_to_add)
        
        return {
            "exchange": exchange.value,
            "request_type": request_type.value,
            "capacity": capacity,
            "current_tokens": real_time_tokens,
            "refill_rate": refill_rate,
            "utilization": (capacity - real_time_tokens) / capacity,
            "last_refill": last_refill,
            "time_to_full": max(0, (capacity - real_time_tokens) / refill_rate) if refill_rate > 0 else 0
        }


class QuotaAllocator:
    """配额分配器"""
    
    def __init__(self, storage: DistributedStorage):
        self.storage = storage
        self.client_prefix = "rate_limit:client:"
        self.quota_prefix = "rate_limit:quota:"
    
    async def register_client(self, client_info: ClientInfo) -> bool:
        """注册客户端"""
        client_key = f"{self.client_prefix}{client_info.client_id}"
        client_data = {
            "process_id": client_info.process_id,
            "service_name": client_info.service_name,
            "priority": str(client_info.priority),
            "last_heartbeat": str(time.time()),
            "is_active": "true",
            "metadata": json.dumps(client_info.metadata)
        }
        
        for field, value in client_data.items():
            await self.storage.hash_set(client_key, field, value)
        
        await self.storage.expire(client_key, 300)  # 5分钟过期
        return True
    
    async def update_heartbeat(self, client_id: str) -> bool:
        """更新客户端心跳"""
        client_key = f"{self.client_prefix}{client_id}"
        success = await self.storage.hash_set(client_key, "last_heartbeat", str(time.time()))
        if success:
            await self.storage.expire(client_key, 300)
        return success
    
    async def get_active_clients(self) -> List[ClientInfo]:
        """获取活跃客户端列表"""
        # 简化实现：遍历已知客户端（实际应用中可能需要更复杂的客户端发现机制）
        # 这里假设我们维护一个客户端列表
        clients = []
        current_time = time.time()
        
        # 实际实现中，这里应该从存储中获取所有客户端
        # 为了演示，我们假设有一个客户端列表键
        client_list_key = "rate_limit:clients:list"
        client_ids = await self.storage.list_range(client_list_key, 0, -1)
        
        for client_id in client_ids:
            client_key = f"{self.client_prefix}{client_id}"
            client_data = await self.storage.hash_get_all(client_key)
            
            if client_data:
                last_heartbeat = float(client_data.get("last_heartbeat", 0))
                if current_time - last_heartbeat < 120:  # 2分钟内活跃
                    client_info = ClientInfo(
                        client_id=client_id,
                        process_id=client_data.get("process_id", ""),
                        service_name=client_data.get("service_name", ""),
                        priority=int(client_data.get("priority", 1)),
                        last_heartbeat=last_heartbeat,
                        is_active=client_data.get("is_active", "true") == "true",
                        metadata=json.loads(client_data.get("metadata", "{}"))
                    )
                    clients.append(client_info)
        
        return clients
    
    async def allocate_quotas(self, exchange: ExchangeType, request_type: RequestType, total_quota: float) -> Dict[str, float]:
        """
        分配配额给活跃客户端
        
        使用基于优先级的公平分配算法
        """
        active_clients = await self.get_active_clients()
        
        if not active_clients:
            return {}
        
        # 计算总优先级权重
        total_priority_weight = sum(client.priority for client in active_clients)
        
        # 分配配额
        allocations = {}
        for client in active_clients:
            # 基于优先级的比例分配
            weight_ratio = client.priority / total_priority_weight
            allocated_quota = total_quota * weight_ratio
            allocations[client.client_id] = allocated_quota
            
            # 保存分配结果
            quota_key = f"{self.quota_prefix}{exchange.value}:{request_type.value}:{client.client_id}"
            await self.storage.set(quota_key, str(allocated_quota), 120)  # 2分钟有效
        
        return allocations
    
    async def get_client_quota(self, client_id: str, exchange: ExchangeType, request_type: RequestType) -> float:
        """获取客户端配额"""
        quota_key = f"{self.quota_prefix}{exchange.value}:{request_type.value}:{client_id}"
        quota_str = await self.storage.get(quota_key)
        return float(quota_str) if quota_str else 0.0


class DistributedRateLimitCoordinator:
    """分布式速率限制协调器"""
    
    def __init__(self, storage: DistributedStorage, exchange_limits: Optional[Dict[ExchangeType, ExchangeRateLimit]] = None):
        self.storage = storage
        self.exchange_limits = exchange_limits or self._get_default_exchange_limits()
        self.token_bucket_manager = TokenBucketManager(storage, self.exchange_limits)
        self.quota_allocator = QuotaAllocator(storage)
        
        self.client_id = str(uuid.uuid4())
        self.process_id = str(os.getpid())
        self.service_name = "marketprism_service"
        
        # 监控数据
        self.request_count = 0
        self.granted_count = 0
        self.denied_count = 0
        self.start_time = time.time()
        
        logger.info(f"分布式速率限制协调器已初始化，客户端ID: {self.client_id}")
    
    def _get_default_exchange_limits(self) -> Dict[ExchangeType, ExchangeRateLimit]:
        """获取默认交易所限制"""
        return {
            ExchangeType.BINANCE: ExchangeRateLimit.get_binance_limits(),
            ExchangeType.OKX: ExchangeRateLimit.get_okx_limits(),
            ExchangeType.DERIBIT: ExchangeRateLimit.get_deribit_limits()
        }
    
    async def register_client(self, service_name: str, priority: int = 1, metadata: Optional[Dict[str, Any]] = None) -> str:
        """注册客户端"""
        self.service_name = service_name
        client_info = ClientInfo(
            client_id=self.client_id,
            process_id=self.process_id,
            service_name=service_name,
            priority=priority,
            metadata=metadata or {}
        )
        
        success = await self.quota_allocator.register_client(client_info)
        if success:
            # 添加到客户端列表
            await self.storage.list_append("rate_limit:clients:list", self.client_id)
            logger.info(f"客户端已注册: {self.client_id}, 服务: {service_name}")
        
        return self.client_id
    
    async def heartbeat(self) -> bool:
        """发送心跳"""
        return await self.quota_allocator.update_heartbeat(self.client_id)
    
    async def acquire_permit(self, request: RateLimitRequest) -> RateLimitResponse:
        """获取请求许可"""
        self.request_count += 1
        
        # 更新心跳
        await self.heartbeat()
        
        # 检查是否有足够的全局令牌
        success, remaining_tokens = await self.token_bucket_manager.consume_tokens(
            request.exchange,
            request.request_type,
            request.weight
        )
        
        if success:
            self.granted_count += 1
            response = RateLimitResponse(
                granted=True,
                client_id=self.client_id,
                request_id=request.request_id,
                remaining_quota=remaining_tokens,
                total_quota=await self.token_bucket_manager._get_bucket_capacity(request.exchange, request.request_type),
                reason="success"
            )
        else:
            self.denied_count += 1
            # 计算等待时间
            bucket_status = await self.token_bucket_manager.get_bucket_status(request.exchange, request.request_type)
            wait_time = request.weight / bucket_status["refill_rate"] if bucket_status["refill_rate"] > 0 else 60
            
            response = RateLimitResponse(
                granted=False,
                client_id=self.client_id,
                request_id=request.request_id,
                wait_time=wait_time,
                remaining_quota=remaining_tokens,
                total_quota=bucket_status["capacity"],
                reason=f"Rate limit exceeded, tokens needed: {request.weight}, available: {remaining_tokens}"
            )
        
        logger.debug(f"速率限制请求处理: {request.exchange.value} {request.request_type.value} -> {response.granted}")
        return response
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        active_clients = await self.quota_allocator.get_active_clients()
        
        bucket_statuses = {}
        for exchange in self.exchange_limits:
            bucket_statuses[exchange.value] = {}
            for request_type in RequestType:
                status = await self.token_bucket_manager.get_bucket_status(exchange, request_type)
                bucket_statuses[exchange.value][request_type.value] = status
        
        uptime = time.time() - self.start_time
        success_rate = self.granted_count / self.request_count if self.request_count > 0 else 0
        
        return {
            "coordinator_status": {
                "client_id": self.client_id,
                "service_name": self.service_name,
                "uptime_seconds": uptime,
                "total_requests": self.request_count,
                "granted_requests": self.granted_count,
                "denied_requests": self.denied_count,
                "success_rate": success_rate
            },
            "active_clients": len(active_clients),
            "client_details": [
                {
                    "client_id": client.client_id,
                    "service_name": client.service_name,
                    "priority": client.priority,
                    "last_heartbeat": client.last_heartbeat
                }
                for client in active_clients
            ],
            "bucket_statuses": bucket_statuses,
            "timestamp": time.time()
        }
    
    async def cleanup_inactive_clients(self) -> int:
        """清理非活跃客户端"""
        # 这个方法应该定期运行，清理过期的客户端
        # 实际实现会更复杂，这里简化处理
        return 0


# 便利函数和工厂方法
async def create_redis_coordinator(redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0) -> DistributedRateLimitCoordinator:
    """创建基于Redis的分布式速率限制协调器"""
    if not REDIS_AVAILABLE:
        logger.warning("Redis不可用，使用内存存储降级")
        return DistributedRateLimitCoordinator(InMemoryDistributedStorage())
    
    try:
        redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}/{redis_db}")
        await redis_client.ping()  # 测试连接
        
        storage = RedisDistributedStorage(redis_client)
        coordinator = DistributedRateLimitCoordinator(storage)
        
        logger.info(f"Redis分布式速率限制协调器已创建: {redis_host}:{redis_port}")
        return coordinator
        
    except Exception as e:
        logger.error(f"Redis连接失败: {e}, 使用内存存储降级")
        return DistributedRateLimitCoordinator(InMemoryDistributedStorage())


async def create_memory_coordinator() -> DistributedRateLimitCoordinator:
    """创建基于内存的分布式速率限制协调器（用于测试）"""
    storage = InMemoryDistributedStorage()
    coordinator = DistributedRateLimitCoordinator(storage)
    logger.info("内存分布式速率限制协调器已创建")
    return coordinator


# 全局协调器实例
_global_coordinator: Optional[DistributedRateLimitCoordinator] = None


async def get_global_coordinator() -> DistributedRateLimitCoordinator:
    """获取全局协调器实例"""
    global _global_coordinator
    if _global_coordinator is None:
        _global_coordinator = await create_redis_coordinator()
    return _global_coordinator


async def set_global_coordinator(coordinator: DistributedRateLimitCoordinator):
    """设置全局协调器实例"""
    global _global_coordinator
    _global_coordinator = coordinator


# 便利API函数
async def acquire_permit(exchange: str, request_type: str = "rest_public", weight: int = 1, endpoint: Optional[str] = None) -> bool:
    """便利函数：获取API请求许可"""
    coordinator = await get_global_coordinator()
    
    request = RateLimitRequest(
        client_id=coordinator.client_id,
        exchange=ExchangeType(exchange.lower()),
        request_type=RequestType(request_type.lower()),
        endpoint=endpoint,
        weight=weight
    )
    
    response = await coordinator.acquire_permit(request)
    return response.granted


async def get_rate_limit_status() -> Dict[str, Any]:
    """便利函数：获取速率限制状态"""
    coordinator = await get_global_coordinator()
    return await coordinator.get_system_status()


if __name__ == "__main__":
    # 示例用法
    async def example_usage():
        # 创建协调器
        coordinator = await create_redis_coordinator()
        
        # 注册客户端
        await coordinator.register_client("python_collector", priority=3)
        
        # 请求许可
        request = RateLimitRequest(
            client_id=coordinator.client_id,
            exchange=ExchangeType.BINANCE,
            request_type=RequestType.REST_PUBLIC,
            endpoint="/api/v3/ticker/24hr",
            weight=1
        )
        
        response = await coordinator.acquire_permit(request)
        print(f"Request granted: {response.granted}")
        
        # 获取状态
        status = await coordinator.get_system_status()
        print(f"System status: {json.dumps(status, indent=2)}")
    
    # 运行示例
    asyncio.run(example_usage())