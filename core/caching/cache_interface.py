"""
缓存系统核心接口

定义统一的缓存操作接口、键值管理和配置系统。
"""

import time
import hashlib
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Union, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta

# 类型变量
T = TypeVar('T')


class CacheLevel(Enum):
    """缓存层级"""
    MEMORY = "memory"
    REDIS = "redis"
    DISK = "disk"
    

class CacheEvictionPolicy(Enum):
    """缓存淘汰策略"""
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    ADAPTIVE = "adaptive"
    FIFO = "fifo"
    RANDOM = "random"


class SerializationFormat(Enum):
    """序列化格式"""
    PICKLE = "pickle"
    JSON = "json"
    MSGPACK = "msgpack"
    PROTOBUF = "protobuf"


@dataclass
class CacheKey:
    """缓存键
    
    提供统一的缓存键管理，支持命名空间、版本和自动哈希。
    """
    namespace: str
    key: str
    version: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """初始化后处理"""
        # 验证键的有效性
        if not self.namespace:
            raise ValueError("命名空间不能为空")
        if not self.key:
            raise ValueError("键不能为空")
    
    def full_key(self) -> str:
        """获取完整的键"""
        parts = [self.namespace, self.key]
        if self.version:
            parts.append(f"v{self.version}")
        return ":".join(parts)
    
    def hash_key(self) -> str:
        """获取哈希键（用于长键的优化）"""
        full = self.full_key()
        if len(full) > 250:  # Redis key length limit
            return f"{self.namespace}:hash:{hashlib.md5(full.encode()).hexdigest()}"
        return full
    
    def with_suffix(self, suffix: str) -> 'CacheKey':
        """创建带后缀的新键"""
        return CacheKey(
            namespace=self.namespace,
            key=f"{self.key}:{suffix}",
            version=self.version,
            tags=self.tags.copy()
        )
    
    def with_prefix(self, prefix: str) -> 'CacheKey':
        """创建带前缀的新键"""
        return CacheKey(
            namespace=self.namespace,
            key=f"{prefix}:{self.key}",
            version=self.version,
            tags=self.tags.copy()
        )
    
    def matches_pattern(self, pattern: str) -> bool:
        """检查是否匹配模式"""
        import fnmatch
        return fnmatch.fnmatch(self.full_key(), pattern)
    
    def __str__(self) -> str:
        return self.hash_key()
    
    def __hash__(self) -> int:
        return hash(self.hash_key())
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, CacheKey):
            return False
        return self.hash_key() == other.hash_key()


@dataclass
class CacheValue(Generic[T]):
    """缓存值
    
    封装缓存的数据，包含元数据和生命周期信息。
    """
    data: T
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    size_bytes: Optional[int] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.size_bytes is None:
            self.size_bytes = self._calculate_size()
    
    def _calculate_size(self) -> int:
        """计算数据大小（估算）"""
        try:
            import sys
            import pickle
            return len(pickle.dumps(self.data, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception:
            # 如果无法序列化，使用sys.getsizeof的估算
            return sys.getsizeof(self.data)
    
    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at
    
    def time_to_live(self) -> Optional[timedelta]:
        """获取剩余生存时间"""
        if self.expires_at is None:
            return None
        now = datetime.now(timezone.utc)
        if now >= self.expires_at:
            return timedelta(0)
        return self.expires_at - now
    
    def age(self) -> timedelta:
        """获取数据年龄"""
        return datetime.now(timezone.utc) - self.created_at
    
    def touch(self) -> None:
        """更新访问时间和计数"""
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1
    
    def extend_ttl(self, ttl: timedelta) -> None:
        """延长生存时间"""
        now = datetime.now(timezone.utc)
        self.expires_at = now + ttl
    
    def get_value(self) -> T:
        """获取值（自动touch）"""
        self.touch()
        return self.data


@dataclass
class CacheConfig:
    """缓存配置"""
    # 基本配置
    name: str
    level: CacheLevel
    max_size: int = 1000
    default_ttl: Optional[timedelta] = None
    
    # 淘汰策略
    eviction_policy: CacheEvictionPolicy = CacheEvictionPolicy.LRU
    
    # 序列化配置
    serialization_format: SerializationFormat = SerializationFormat.PICKLE
    compression_enabled: bool = False
    compression_level: int = 6
    
    # 性能配置
    max_memory_mb: Optional[int] = None
    sync_interval: timedelta = timedelta(seconds=60)
    background_cleanup: bool = True
    
    # 一致性配置
    consistency_level: str = "eventual"  # immediate, strong, eventual
    replication_factor: int = 1
    
    # 监控配置
    enable_metrics: bool = True
    enable_detailed_stats: bool = False
    sample_rate: float = 0.1
    
    # 线程安全配置
    thread_safe: bool = True
    
    # 特定实现配置
    implementation_config: Dict[str, Any] = field(default_factory=dict)


class CacheStatistics:
    """缓存统计信息"""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.evictions = 0
        self.errors = 0
        
        # 性能统计
        self.total_get_time = 0.0
        self.total_set_time = 0.0
        self.total_delete_time = 0.0
        
        # 内存统计
        self.current_size = 0
        self.current_memory_bytes = 0
        self.max_memory_bytes = 0
        
        # 时间统计
        self.created_at = datetime.now(timezone.utc)
        self.last_reset = datetime.now(timezone.utc)
        self.start_time = time.time()  # 添加start_time属性
    
    @property
    def total_operations(self) -> int:
        """总操作数"""
        return self.hits + self.misses + self.sets + self.deletes
    
    @property
    def hit_rate(self) -> float:
        """命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    @property
    def miss_rate(self) -> float:
        """未命中率"""
        return 1.0 - self.hit_rate
    
    @property
    def avg_get_time(self) -> float:
        """平均获取时间"""
        total_ops = self.hits + self.misses
        return self.total_get_time / total_ops if total_ops > 0 else 0.0
    
    @property
    def avg_set_time(self) -> float:
        """平均设置时间"""
        return self.total_set_time / self.sets if self.sets > 0 else 0.0
    
    @property
    def memory_utilization(self) -> float:
        """内存利用率"""
        return self.current_memory_bytes / self.max_memory_bytes if self.max_memory_bytes > 0 else 0.0
    
    def reset(self):
        """重置统计"""
        self.__init__()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "evictions": self.evictions,
            "errors": self.errors,
            "hit_rate": self.hit_rate,
            "miss_rate": self.miss_rate,
            "total_operations": self.total_operations,
            "avg_get_time": self.avg_get_time,
            "avg_set_time": self.avg_set_time,
            "current_size": self.current_size,
            "current_memory_bytes": self.current_memory_bytes,
            "memory_utilization": self.memory_utilization,
            "uptime": time.time() - self.start_time,
            "created_at": self.created_at.isoformat(),
            "last_reset": self.last_reset.isoformat()
        }


class Cache(ABC, Generic[T]):
    """缓存抽象基类
    
    定义统一的缓存操作接口，所有缓存实现都必须继承此类。
    """
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.stats = CacheStatistics()
        self._enabled = True
    
    @abstractmethod
    async def get(self, key: CacheKey) -> Optional[CacheValue[T]]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    async def set(self, key: CacheKey, value: CacheValue[T], ttl: Optional[timedelta] = None) -> bool:
        """设置缓存值"""
        pass
    
    @abstractmethod
    async def delete(self, key: CacheKey) -> bool:
        """删除缓存值"""
        pass
    
    @abstractmethod
    async def exists(self, key: CacheKey) -> bool:
        """检查键是否存在"""
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """清空缓存"""
        pass
    
    @abstractmethod
    async def size(self) -> int:
        """获取缓存大小"""
        pass
    
    @abstractmethod
    async def keys(self, pattern: Optional[str] = None) -> List[CacheKey]:
        """获取所有键"""
        pass
    
    # 批量操作
    async def get_many(self, keys: List[CacheKey]) -> Dict[CacheKey, Optional[CacheValue[T]]]:
        """批量获取"""
        result = {}
        for key in keys:
            result[key] = await self.get(key)
        return result
    
    async def set_many(self, items: Dict[CacheKey, CacheValue[T]], ttl: Optional[timedelta] = None) -> Dict[CacheKey, bool]:
        """批量设置"""
        result = {}
        for key, value in items.items():
            result[key] = await self.set(key, value, ttl)
        return result
    
    async def delete_many(self, keys: List[CacheKey]) -> Dict[CacheKey, bool]:
        """批量删除"""
        result = {}
        for key in keys:
            result[key] = await self.delete(key)
        return result
    
    # 高级操作
    async def get_or_set(self, key: CacheKey, factory_func, ttl: Optional[timedelta] = None) -> T:
        """获取或设置（如果不存在则通过工厂函数创建）"""
        value = await self.get(key)
        if value is not None and not value.is_expired():
            return value.get_value()
        
        # 创建新值
        data = await factory_func() if hasattr(factory_func, '__call__') else factory_func
        new_value = CacheValue(data=data)
        if ttl:
            new_value.expires_at = datetime.now(timezone.utc) + ttl
        
        await self.set(key, new_value, ttl)
        return data
    
    async def increment(self, key: CacheKey, delta: int = 1) -> Optional[int]:
        """递增计数器"""
        value = await self.get(key)
        if value is None:
            new_value = CacheValue(data=delta)
            await self.set(key, new_value)
            return delta
        
        if isinstance(value.data, (int, float)):
            new_data = value.data + delta
            value.data = new_data
            await self.set(key, value)
            return new_data
        
        return None
    
    async def decrement(self, key: CacheKey, delta: int = 1) -> Optional[int]:
        """递减计数器"""
        return await self.increment(key, -delta)
    
    async def expire(self, key: CacheKey, ttl: timedelta) -> bool:
        """设置过期时间"""
        value = await self.get(key)
        if value is None:
            return False
        
        value.expires_at = datetime.now(timezone.utc) + ttl
        return await self.set(key, value)
    
    async def persist(self, key: CacheKey) -> bool:
        """移除过期时间"""
        value = await self.get(key)
        if value is None:
            return False
        
        value.expires_at = None
        return await self.set(key, value)
    
    # 模式操作
    async def delete_pattern(self, pattern: str) -> int:
        """根据模式删除键"""
        keys = await self.keys(pattern)
        results = await self.delete_many(keys)
        return sum(1 for success in results.values() if success)
    
    async def keys_pattern(self, pattern: str) -> List[CacheKey]:
        """根据模式获取键"""
        return await self.keys(pattern)
    
    # 统计和监控
    def get_statistics(self) -> CacheStatistics:
        """获取统计信息"""
        return self.stats
    
    def reset_statistics(self):
        """重置统计信息"""
        self.stats.reset()
    
    # 健康检查
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 测试基本操作
            test_key = CacheKey(namespace="health", key="check")
            test_value = CacheValue(data="test")
            
            start_time = time.time()
            await self.set(test_key, test_value)
            result = await self.get(test_key)
            await self.delete(test_key)
            end_time = time.time()
            
            return {
                "healthy": True,
                "response_time": end_time - start_time,
                "cache_level": self.config.level.value,
                "size": await self.size(),
                "statistics": self.stats.to_dict()
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "cache_level": self.config.level.value
            }
    
    # 生命周期管理
    async def start(self):
        """启动缓存"""
        self._enabled = True
    
    async def stop(self):
        """停止缓存"""
        self._enabled = False
    
    async def flush(self):
        """刷新缓存到持久存储（如果适用）"""
        pass
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enabled
    
    def enable(self):
        """启用缓存"""
        self._enabled = True
    
    def disable(self):
        """禁用缓存"""
        self._enabled = False


# 便利函数
def create_cache_key(namespace: str, key: str, **kwargs) -> CacheKey:
    """创建缓存键的便利函数"""
    return CacheKey(namespace=namespace, key=key, **kwargs)


def create_cache_value(data: T, ttl: Optional[timedelta] = None, **metadata) -> CacheValue[T]:
    """创建缓存值的便利函数"""
    value = CacheValue(data=data, metadata=metadata)
    if ttl:
        value.expires_at = datetime.now(timezone.utc) + ttl
    return value 