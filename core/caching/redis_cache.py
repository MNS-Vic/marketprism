"""
Redis分布式缓存实现

提供高性能的Redis分布式缓存，支持集群、连接池和多种序列化格式。
"""

import pickle
import json
import time
import asyncio
from typing import Any, Optional, Dict, List, Union
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import logging

try:
    import aioredis
    from aioredis import Redis
    from aioredis.exceptions import RedisError, ConnectionError, TimeoutError
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    Redis = None
    RedisError = Exception
    ConnectionError = Exception
    TimeoutError = Exception
    REDIS_AVAILABLE = False

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    msgpack = None
    MSGPACK_AVAILABLE = False

from .cache_interface import (
    Cache, CacheKey, CacheValue, CacheConfig, CacheLevel, 
    SerializationFormat, CacheStatistics
)
from .cache_strategies import CacheStrategy, create_strategy


@dataclass
class RedisCacheConfig(CacheConfig):
    """Redis缓存配置"""
    level: CacheLevel = CacheLevel.REDIS
    
    # Redis连接配置
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    username: Optional[str] = None
    
    # 连接池配置
    max_connections: int = 10
    retry_on_timeout: bool = True
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    
    # 集群配置
    cluster_mode: bool = False
    cluster_nodes: List[Dict[str, Any]] = None
    
    # 性能配置
    pipeline_batch_size: int = 100
    enable_pipeline: bool = True
    connection_pool_kwargs: Dict[str, Any] = None
    
    # 序列化配置
    key_prefix: str = "marketprism"
    
    def __post_init__(self):
        super().__post_init__()
        if self.cluster_nodes is None:
            self.cluster_nodes = []
        if self.connection_pool_kwargs is None:
            self.connection_pool_kwargs = {}


class RedisSerializer:
    """Redis序列化器"""
    
    def __init__(self, format_type: SerializationFormat = SerializationFormat.PICKLE):
        self.format_type = format_type
    
    def serialize(self, data: Any) -> bytes:
        """序列化数据"""
        try:
            if self.format_type == SerializationFormat.PICKLE:
                return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            elif self.format_type == SerializationFormat.JSON:
                return json.dumps(data, ensure_ascii=False).encode('utf-8')
            elif self.format_type == SerializationFormat.MSGPACK:
                if not MSGPACK_AVAILABLE:
                    raise ValueError("msgpack not available")
                return msgpack.packb(data)
            else:
                raise ValueError(f"不支持的序列化格式: {self.format_type}")
        except Exception as e:
            raise ValueError(f"序列化失败: {e}")
    
    def deserialize(self, data: bytes) -> Any:
        """反序列化数据"""
        try:
            if self.format_type == SerializationFormat.PICKLE:
                return pickle.loads(data)
            elif self.format_type == SerializationFormat.JSON:
                return json.loads(data.decode('utf-8'))
            elif self.format_type == SerializationFormat.MSGPACK:
                if not MSGPACK_AVAILABLE:
                    raise ValueError("msgpack not available")
                return msgpack.unpackb(data, raw=False)
            else:
                raise ValueError(f"不支持的序列化格式: {self.format_type}")
        except Exception as e:
            raise ValueError(f"反序列化失败: {e}")


class RedisConnectionManager:
    """Redis连接管理器"""
    
    def __init__(self, config: RedisCacheConfig):
        self.config = config
        self.redis: Optional[Redis] = None
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger(__name__)
    
    async def connect(self) -> Redis:
        """建立Redis连接"""
        if not REDIS_AVAILABLE:
            raise RuntimeError("aioredis not available")
        
        async with self._lock:
            if self.redis is not None:
                return self.redis
            
            try:
                if self.config.cluster_mode:
                    # TODO: 实现集群模式连接
                    raise NotImplementedError("Redis集群模式暂未实现")
                else:
                    # 单实例模式
                    connection_kwargs = {
                        'host': self.config.host,
                        'port': self.config.port,
                        'db': self.config.db,
                        'password': self.config.password,
                        'username': self.config.username,
                        'socket_timeout': self.config.socket_timeout,
                        'socket_connect_timeout': self.config.socket_connect_timeout,
                        'retry_on_timeout': self.config.retry_on_timeout,
                        'max_connections': self.config.max_connections,
                        **self.config.connection_pool_kwargs
                    }
                    
                    # 过滤None值
                    connection_kwargs = {k: v for k, v in connection_kwargs.items() if v is not None}
                    
                    self.redis = aioredis.from_url(
                        f"redis://{self.config.host}:{self.config.port}/{self.config.db}",
                        **connection_kwargs
                    )
                
                # 测试连接
                await self.redis.ping()
                self._logger.info(f"Redis连接建立成功: {self.config.host}:{self.config.port}")
                return self.redis
                
            except Exception as e:
                self._logger.error(f"Redis连接失败: {e}")
                raise ConnectionError(f"Redis连接失败: {e}")
    
    async def disconnect(self):
        """断开Redis连接"""
        if self.redis:
            await self.redis.close()
            self.redis = None
            self._logger.info("Redis连接已断开")
    
    async def is_connected(self) -> bool:
        """检查连接状态"""
        if not self.redis:
            return False
        
        try:
            await self.redis.ping()
            return True
        except Exception:
            return False


class RedisCache(Cache):
    """Redis分布式缓存
    
    特性：
    - 分布式缓存支持
    - 连接池管理
    - 多种序列化格式
    - 管道批量操作
    - 异步高性能操作
    """
    
    def __init__(self, config: RedisCacheConfig):
        super().__init__(config)
        self.config: RedisCacheConfig = config
        
        # 连接管理
        self.connection_manager = RedisConnectionManager(config)
        self.redis: Optional[Redis] = None
        
        # 序列化
        self.serializer = RedisSerializer(config.serialization_format)
        
        # 策略（用于本地统计）
        self.strategy = create_strategy(
            config.eviction_policy,
            config.max_size,
            default_ttl=config.default_ttl
        )
        
        # 键前缀
        self.key_prefix = config.key_prefix
        
        self._logger = logging.getLogger(__name__)
    
    def _build_redis_key(self, key: CacheKey) -> str:
        """构建Redis键"""
        full_key = key.hash_key()
        return f"{self.key_prefix}:{full_key}"
    
    def _parse_redis_key(self, redis_key: str) -> Optional[CacheKey]:
        """解析Redis键"""
        try:
            if not redis_key.startswith(f"{self.key_prefix}:"):
                return None
            
            key_part = redis_key[len(f"{self.key_prefix}:"):]
            # 简单解析（假设格式为 namespace:key）
            parts = key_part.split(':', 1)
            if len(parts) >= 2:
                return CacheKey(namespace=parts[0], key=parts[1])
            return None
        except Exception:
            return None
    
    async def _ensure_connected(self):
        """确保Redis连接"""
        if not self.redis:
            self.redis = await self.connection_manager.connect()
    
    async def get(self, key: CacheKey) -> Optional[CacheValue]:
        """获取缓存值"""
        start_time = time.time()
        
        try:
            await self._ensure_connected()
            redis_key = self._build_redis_key(key)
            
            # 获取数据和TTL
            pipe = self.redis.pipeline()
            pipe.get(redis_key)
            pipe.ttl(redis_key)
            results = await pipe.execute()
            
            data_bytes, ttl_seconds = results
            
            if data_bytes is None:
                self.stats.misses += 1
                return None
            
            # 反序列化
            data = self.serializer.deserialize(data_bytes)
            
            # 构造CacheValue
            value = CacheValue(data=data)
            
            if ttl_seconds > 0:
                value.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            
            # 更新策略和统计
            self.strategy.on_access(key, value)
            self.stats.hits += 1
            
            return value
            
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Redis get失败: {e}")
            raise
        finally:
            self.stats.total_get_time += time.time() - start_time
    
    async def set(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """设置缓存值"""
        start_time = time.time()
        
        try:
            await self._ensure_connected()
            redis_key = self._build_redis_key(key)
            
            # 序列化数据
            data_bytes = self.serializer.serialize(value.data)
            
            # 计算TTL
            if ttl is not None:
                ttl_seconds = int(ttl.total_seconds())
            elif value.expires_at is not None:
                ttl_delta = value.expires_at - datetime.now(timezone.utc)
                ttl_seconds = int(ttl_delta.total_seconds()) if ttl_delta.total_seconds() > 0 else None
            elif self.config.default_ttl is not None:
                ttl_seconds = int(self.config.default_ttl.total_seconds())
            else:
                ttl_seconds = None
            
            # 设置值
            if ttl_seconds is not None and ttl_seconds > 0:
                await self.redis.setex(redis_key, ttl_seconds, data_bytes)
            else:
                await self.redis.set(redis_key, data_bytes)
            
            # 更新策略和统计
            self.strategy.on_insert(key, value)
            self.stats.sets += 1
            
            return True
            
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Redis set失败: {e}")
            raise
        finally:
            self.stats.total_set_time += time.time() - start_time
    
    async def delete(self, key: CacheKey) -> bool:
        """删除缓存值"""
        start_time = time.time()
        
        try:
            await self._ensure_connected()
            redis_key = self._build_redis_key(key)
            
            result = await self.redis.delete(redis_key)
            
            if result > 0:
                # 创建虚拟value用于策略通知
                dummy_value = CacheValue(data=None)
                self.strategy.on_remove(key, dummy_value)
                self.stats.deletes += 1
                return True
            
            return False
            
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Redis delete失败: {e}")
            raise
        finally:
            self.stats.total_delete_time += time.time() - start_time
    
    async def exists(self, key: CacheKey) -> bool:
        """检查键是否存在"""
        try:
            await self._ensure_connected()
            redis_key = self._build_redis_key(key)
            
            result = await self.redis.exists(redis_key)
            return result > 0
            
        except Exception as e:
            self._logger.error(f"Redis exists失败: {e}")
            return False
    
    async def clear(self) -> bool:
        """清空缓存"""
        try:
            await self._ensure_connected()
            
            # 使用模式删除
            pattern = f"{self.key_prefix}:*"
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=1000)
                if keys:
                    await self.redis.delete(*keys)
                
                if cursor == 0:
                    break
            
            self.strategy.clear()
            return True
            
        except Exception as e:
            self._logger.error(f"Redis clear失败: {e}")
            return False
    
    async def size(self) -> int:
        """获取缓存大小"""
        try:
            await self._ensure_connected()
            
            # 使用SCAN统计键数量
            pattern = f"{self.key_prefix}:*"
            cursor = 0
            count = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=1000)
                count += len(keys)
                
                if cursor == 0:
                    break
            
            return count
            
        except Exception as e:
            self._logger.error(f"Redis size失败: {e}")
            return 0
    
    async def keys(self, pattern: Optional[str] = None) -> List[CacheKey]:
        """获取所有键"""
        try:
            await self._ensure_connected()
            
            # 构建搜索模式
            if pattern:
                search_pattern = f"{self.key_prefix}:*{pattern}*"
            else:
                search_pattern = f"{self.key_prefix}:*"
            
            result = []
            cursor = 0
            
            while True:
                cursor, keys = await self.redis.scan(cursor, match=search_pattern, count=1000)
                
                for redis_key in keys:
                    if isinstance(redis_key, bytes):
                        redis_key = redis_key.decode('utf-8')
                    
                    cache_key = self._parse_redis_key(redis_key)
                    if cache_key:
                        result.append(cache_key)
                
                if cursor == 0:
                    break
            
            return result
            
        except Exception as e:
            self._logger.error(f"Redis keys失败: {e}")
            return []
    
    # 批量操作优化
    async def get_many(self, keys: List[CacheKey]) -> Dict[CacheKey, Optional[CacheValue]]:
        """批量获取（管道优化）"""
        if not keys:
            return {}
        
        try:
            await self._ensure_connected()
            
            # 构建Redis键
            redis_keys = [self._build_redis_key(key) for key in keys]
            
            # 使用管道批量获取
            pipe = self.redis.pipeline()
            for redis_key in redis_keys:
                pipe.get(redis_key)
                pipe.ttl(redis_key)
            
            results = await pipe.execute()
            
            # 解析结果
            result = {}
            for i, key in enumerate(keys):
                data_bytes = results[i * 2]
                ttl_seconds = results[i * 2 + 1]
                
                if data_bytes is None:
                    result[key] = None
                    self.stats.misses += 1
                    continue
                
                try:
                    data = self.serializer.deserialize(data_bytes)
                    value = CacheValue(data=data)
                    
                    if ttl_seconds > 0:
                        value.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                    
                    result[key] = value
                    self.strategy.on_access(key, value)
                    self.stats.hits += 1
                    
                except Exception as e:
                    self._logger.warning(f"反序列化失败: {e}")
                    result[key] = None
                    self.stats.errors += 1
            
            return result
            
        except Exception as e:
            self._logger.error(f"Redis get_many失败: {e}")
            return {key: None for key in keys}
    
    async def set_many(self, items: Dict[CacheKey, CacheValue], ttl: Optional[timedelta] = None) -> Dict[CacheKey, bool]:
        """批量设置（管道优化）"""
        if not items:
            return {}
        
        try:
            await self._ensure_connected()
            
            pipe = self.redis.pipeline()
            
            for key, value in items.items():
                try:
                    redis_key = self._build_redis_key(key)
                    data_bytes = self.serializer.serialize(value.data)
                    
                    # 计算TTL
                    if ttl is not None:
                        ttl_seconds = int(ttl.total_seconds())
                    elif value.expires_at is not None:
                        ttl_delta = value.expires_at - datetime.now(timezone.utc)
                        ttl_seconds = int(ttl_delta.total_seconds()) if ttl_delta.total_seconds() > 0 else None
                    elif self.config.default_ttl is not None:
                        ttl_seconds = int(self.config.default_ttl.total_seconds())
                    else:
                        ttl_seconds = None
                    
                    # 添加到管道
                    if ttl_seconds is not None and ttl_seconds > 0:
                        pipe.setex(redis_key, ttl_seconds, data_bytes)
                    else:
                        pipe.set(redis_key, data_bytes)
                        
                except Exception as e:
                    self._logger.warning(f"序列化失败 {key}: {e}")
            
            # 执行管道
            results = await pipe.execute()
            
            # 处理结果
            result = {}
            for i, (key, value) in enumerate(items.items()):
                try:
                    if i < len(results) and results[i]:
                        result[key] = True
                        self.strategy.on_insert(key, value)
                        self.stats.sets += 1
                    else:
                        result[key] = False
                        self.stats.errors += 1
                except Exception:
                    result[key] = False
                    self.stats.errors += 1
            
            return result
            
        except Exception as e:
            self._logger.error(f"Redis set_many失败: {e}")
            return {key: False for key in items.keys()}
    
    # 生命周期管理
    async def start(self):
        """启动缓存"""
        await super().start()
        await self._ensure_connected()
    
    async def stop(self):
        """停止缓存"""
        await super().stop()
        await self.connection_manager.disconnect()
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            await self._ensure_connected()
            
            # 测试基本操作
            start_time = time.time()
            await self.redis.ping()
            ping_time = time.time() - start_time
            
            # 获取Redis信息
            info = await self.redis.info()
            
            return {
                "healthy": True,
                "ping_time": ping_time,
                "cache_level": self.config.level.value,
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "statistics": self.stats.to_dict()
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "cache_level": self.config.level.value
            }


# 便利函数
def create_redis_cache(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    max_size: int = 10000,
    default_ttl: Optional[timedelta] = None,
    **kwargs
) -> RedisCache:
    """创建Redis缓存的便利函数"""
    config = RedisCacheConfig(
        name=f"redis_cache_{host}_{port}_{db}",
        host=host,
        port=port,
        db=db,
        password=password,
        max_size=max_size,
        default_ttl=default_ttl,
        **kwargs
    )
    return RedisCache(config) 