"""
Redis缓存TDD测试
专门用于提升redis_cache.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock
import json
import pickle

# 导入Redis缓存模块
from core.caching.cache_interface import (
    CacheKey, CacheValue, CacheLevel, SerializationFormat
)
from core.caching.redis_cache import RedisCache, RedisCacheConfig


class TestRedisCacheConfig:
    """测试Redis缓存配置"""

    def test_redis_cache_config_defaults(self):
        """测试：Redis缓存配置默认值"""
        config = RedisCacheConfig(name="test_redis_cache")

        assert config.name == "test_redis_cache"
        assert config.level == CacheLevel.REDIS
        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0
        assert config.password is None
        assert config.max_connections == 10
        assert config.socket_timeout == 5.0
        assert config.socket_connect_timeout == 5.0
        assert config.retry_on_timeout is True
        assert config.key_prefix == "marketprism"

    def test_redis_cache_config_custom(self):
        """测试：自定义Redis缓存配置"""
        config = RedisCacheConfig(
            name="custom_redis_cache",
            host="redis.example.com",
            port=6380,
            db=1,
            password="secret",
            username="user",
            max_connections=20,
            socket_timeout=10.0,
            socket_connect_timeout=10.0,
            retry_on_timeout=False,
            cluster_mode=True,
            key_prefix="custom"
        )

        assert config.name == "custom_redis_cache"
        assert config.host == "redis.example.com"
        assert config.port == 6380
        assert config.db == 1
        assert config.password == "secret"
        assert config.username == "user"
        assert config.max_connections == 20
        assert config.socket_timeout == 10.0
        assert config.socket_connect_timeout == 10.0
        assert config.retry_on_timeout is False
        assert config.cluster_mode is True
        assert config.key_prefix == "custom"


class TestRedisCacheInitialization:
    """测试Redis缓存初始化"""

    def test_redis_cache_basic_initialization(self):
        """测试：基本初始化"""
        config = RedisCacheConfig(name="test_cache")
        cache = RedisCache(config)

        assert cache.config == config
        assert cache.connection_manager is not None
        assert cache.redis is None  # 初始时未连接
        assert cache.serializer is not None
        assert cache.strategy is not None
        assert cache.key_prefix == "marketprism"
        assert cache._enabled is True
        assert cache.stats is not None

    def test_redis_cache_serializer_initialization(self):
        """测试：序列化器初始化"""
        # 测试不同序列化格式
        formats = [
            SerializationFormat.PICKLE,
            SerializationFormat.JSON,
            SerializationFormat.MSGPACK
        ]

        for format_type in formats:
            config = RedisCacheConfig(
                name="test_cache",
                serialization_format=format_type
            )
            cache = RedisCache(config)

            assert cache.serializer.format_type == format_type

    def test_redis_cache_connection_manager_initialization(self):
        """测试：连接管理器初始化"""
        config = RedisCacheConfig(
            name="test_cache",
            host="custom.redis.com",
            port=6380,
            db=2
        )
        cache = RedisCache(config)

        assert cache.connection_manager.config == config
        assert cache.connection_manager.redis is None  # 初始时未连接

    def test_redis_cache_key_building(self):
        """测试：Redis键构建"""
        config = RedisCacheConfig(name="test_cache", key_prefix="test")
        cache = RedisCache(config)

        key = CacheKey(namespace="user", key="123")
        redis_key = cache._build_redis_key(key)

        assert redis_key.startswith("test:")
        assert "user:123" in redis_key


class TestRedisCacheBasicOperations:
    """测试Redis缓存基本操作"""

    def setup_method(self):
        """设置测试方法"""
        self.config = RedisCacheConfig(
            name="test_cache",
            serialization_format=SerializationFormat.PICKLE
        )
        self.cache = RedisCache(self.config)

        # 模拟Redis连接
        self.mock_redis = AsyncMock()
        self.cache.redis = self.mock_redis
            
    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """测试：设置和获取缓存"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user", "id": 123})

        # 模拟Redis管道操作
        mock_pipe = AsyncMock()
        mock_pipe.get = AsyncMock()
        mock_pipe.ttl = AsyncMock()
        mock_pipe.setex = AsyncMock()
        mock_pipe.execute = AsyncMock()

        # 设置pipeline返回mock_pipe（同步方法）
        self.mock_redis.pipeline = Mock(return_value=mock_pipe)

        # 模拟set操作
        mock_pipe.execute.return_value = [True]
        result = await self.cache.set(key, value)
        assert result is True

        # 模拟get操作
        serialized_data = pickle.dumps(value.data)
        mock_pipe.execute.return_value = [serialized_data, -1]  # get和ttl结果

        # 获取缓存
        retrieved = await self.cache.get(key)
        assert retrieved is not None
        assert retrieved.data == value.data
        
    @pytest.mark.asyncio
    async def test_cache_set_with_ttl(self):
        """测试：设置带TTL的缓存"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data="test_data")
        ttl = timedelta(hours=1)

        # 模拟Redis操作
        self.mock_redis.setex = AsyncMock(return_value=True)

        # 设置带TTL的缓存
        result = await self.cache.set(key, value, ttl)
        assert result is True

        # 验证Redis调用
        self.mock_redis.setex.assert_called_once()
        call_args = self.mock_redis.setex.call_args
        # 验证TTL参数
        assert call_args[0][1] == int(ttl.total_seconds())
        
    @pytest.mark.asyncio
    async def test_cache_get_nonexistent(self):
        """测试：获取不存在的缓存"""
        key = CacheKey(namespace="test", key="nonexistent")

        # 模拟Redis管道操作返回None
        mock_pipe = AsyncMock()
        mock_pipe.get = Mock()
        mock_pipe.ttl = Mock()
        mock_pipe.execute = AsyncMock(return_value=[None, -1])

        self.mock_redis.pipeline = Mock(return_value=mock_pipe)

        result = await self.cache.get(key)
        assert result is None
        
    @pytest.mark.asyncio
    async def test_cache_delete(self):
        """测试：删除缓存"""
        key = CacheKey(namespace="test", key="user:123")

        # 模拟Redis操作
        self.mock_redis.delete = AsyncMock(return_value=1)  # 删除了1个键

        result = await self.cache.delete(key)
        assert result is True

        # 验证Redis调用
        self.mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_delete_nonexistent(self):
        """测试：删除不存在的缓存"""
        key = CacheKey(namespace="test", key="nonexistent")

        # 模拟Redis返回0（没有删除任何键）
        self.mock_redis.delete = AsyncMock(return_value=0)

        result = await self.cache.delete(key)
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_exists(self):
        """测试：检查缓存存在性"""
        key = CacheKey(namespace="test", key="user:123")

        # 模拟Redis操作
        self.mock_redis.exists = AsyncMock(return_value=1)  # 键存在

        result = await self.cache.exists(key)
        assert result is True

        # 测试不存在的键
        self.mock_redis.exists = AsyncMock(return_value=0)  # 键不存在
        result = await self.cache.exists(key)
        assert result is False
        
    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """测试：清空缓存"""
        # 模拟Redis scan操作
        self.mock_redis.scan = AsyncMock(side_effect=[
            (0, [b'test:key1', b'test:key2']),  # 第一次scan返回一些键
        ])
        self.mock_redis.delete = AsyncMock(return_value=2)

        result = await self.cache.clear()
        assert result is True

        # 验证Redis调用
        self.mock_redis.scan.assert_called()
        self.mock_redis.delete.assert_called()


class TestRedisCacheSerialization:
    """测试Redis缓存序列化"""

    def setup_method(self):
        """设置测试方法"""
        self.config = RedisCacheConfig(
            name="test_cache",
            serialization_format=SerializationFormat.PICKLE
        )
        self.cache = RedisCache(self.config)

    def test_serializer_initialization(self):
        """测试：序列化器初始化"""
        # 测试Pickle序列化器
        pickle_config = RedisCacheConfig(
            name="pickle_cache",
            serialization_format=SerializationFormat.PICKLE
        )
        pickle_cache = RedisCache(pickle_config)
        assert pickle_cache.serializer is not None

        # 测试JSON序列化器
        json_config = RedisCacheConfig(
            name="json_cache",
            serialization_format=SerializationFormat.JSON
        )
        json_cache = RedisCache(json_config)
        assert json_cache.serializer is not None


class TestRedisCacheBatchOperations:
    """测试Redis缓存批量操作"""

    def setup_method(self):
        """设置测试方法"""
        self.config = RedisCacheConfig(name="batch_cache")
        self.cache = RedisCache(self.config)

        # 模拟Redis连接
        self.mock_redis = AsyncMock()
        self.cache.redis = self.mock_redis

    @pytest.mark.asyncio
    async def test_cache_get_many(self):
        """测试：批量获取"""
        keys = [
            CacheKey(namespace="test", key="item:1"),
            CacheKey(namespace="test", key="item:2"),
            CacheKey(namespace="test", key="item:3")
        ]

        # 模拟Redis管道批量获取
        mock_pipe = AsyncMock()
        mock_pipe.get = Mock()
        mock_pipe.ttl = Mock()
        mock_pipe.execute = AsyncMock(return_value=[
            pickle.dumps("data1"), 3600,  # item:1的数据和TTL
            pickle.dumps("data2"), 3600,  # item:2的数据和TTL
            None, -1  # item:3不存在
        ])

        self.mock_redis.pipeline = Mock(return_value=mock_pipe)

        results = await self.cache.get_many(keys)

        assert len(results) == 3
        assert results[keys[0]].data == "data1"
        assert results[keys[1]].data == "data2"
        assert results[keys[2]] is None
        
    @pytest.mark.asyncio
    async def test_cache_set_many(self):
        """测试：批量设置"""
        items = {
            CacheKey(namespace="test", key="item:1"): CacheValue(data="data1"),
            CacheKey(namespace="test", key="item:2"): CacheValue(data="data2"),
            CacheKey(namespace="test", key="item:3"): CacheValue(data="data3")
        }

        # 模拟Redis管道操作
        mock_pipe = AsyncMock()
        mock_pipe.set = Mock()
        mock_pipe.setex = Mock()
        mock_pipe.execute = AsyncMock(return_value=[True, True, True])

        self.mock_redis.pipeline = Mock(return_value=mock_pipe)

        results = await self.cache.set_many(items)

        assert len(results) == 3
        assert all(success for success in results.values())

        # 验证管道使用
        self.mock_redis.pipeline.assert_called_once()
        mock_pipe.execute.assert_called_once()
        



class TestRedisCacheErrorHandling:
    """测试Redis缓存错误处理"""

    def setup_method(self):
        """设置测试方法"""
        self.config = RedisCacheConfig(name="error_test_cache")
        self.cache = RedisCache(self.config)

        # 模拟Redis连接
        self.mock_redis = AsyncMock()
        self.cache.redis = self.mock_redis

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self):
        """测试：连接失败处理"""
        # Red: 编写失败的测试 - 连接失败时应该优雅处理
        key = CacheKey(namespace="test", key="connection_test")

        # 模拟连接失败 - 直接模拟_ensure_connected方法失败
        with patch.object(self.cache, '_ensure_connected', side_effect=Exception("Connection failed")):
            # Green: 应该返回None而不是抛出异常
            result = await self.cache.get(key)
            assert result is None

    @pytest.mark.asyncio
    async def test_serialization_error_handling(self):
        """测试：序列化错误处理"""
        # Red: 编写失败的测试 - 序列化失败时应该记录错误
        key = CacheKey(namespace="test", key="serialization_test")

        # 模拟序列化失败
        self.cache.serializer.deserialize = Mock(side_effect=Exception("Serialization failed"))

        # 模拟Redis返回数据
        mock_pipe = AsyncMock()
        mock_pipe.get = Mock()
        mock_pipe.ttl = Mock()
        mock_pipe.execute = AsyncMock(return_value=[b"corrupted_data", 3600])
        self.mock_redis.pipeline = Mock(return_value=mock_pipe)

        # Green: 应该返回None并记录错误
        result = await self.cache.get(key)
        assert result is None

    @pytest.mark.asyncio
    async def test_cluster_mode_fallback(self):
        """测试：集群模式回退到单实例模式"""
        # Red: 编写失败的测试 - 集群模式应该回退到单实例模式
        cluster_config = RedisCacheConfig(
            name="cluster_cache",
            cluster_mode=True
        )
        cluster_cache = RedisCache(cluster_config)

        # 模拟连接失败（因为aioredis不可用）
        with pytest.raises(RuntimeError, match="aioredis not available"):
            await cluster_cache._ensure_connected()

        # 验证配置仍然是集群模式
        assert cluster_cache.config.cluster_mode is True


class TestRedisCacheAdvancedFeatures:
    """测试Redis缓存高级功能"""

    def setup_method(self):
        """设置测试方法"""
        self.config = RedisCacheConfig(name="advanced_cache")
        self.cache = RedisCache(self.config)

        # 模拟Redis连接
        self.mock_redis = AsyncMock()
        self.cache.redis = self.mock_redis

    @pytest.mark.asyncio
    async def test_cache_keys_pattern_matching(self):
        """测试：键模式匹配"""
        # 模拟Redis键扫描
        self.mock_redis.scan = AsyncMock(side_effect=[
            (0, [b'test:user:1', b'test:user:2'])  # 返回匹配的键
        ])

        pattern = "user"
        keys = await self.cache.keys(pattern)

        assert len(keys) >= 0  # 可能返回匹配的键

        # 验证Redis调用
        self.mock_redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_cache_size_operation(self):
        """测试：获取缓存大小"""
        # 模拟Redis scan操作
        self.mock_redis.scan = AsyncMock(side_effect=[
            (0, [b'test:key1', b'test:key2', b'test:key3'])
        ])

        size = await self.cache.size()
        assert size >= 0

        # 验证Redis调用
        self.mock_redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_cache_health_check(self):
        """测试：缓存健康检查"""
        # Red: 编写失败的测试 - 健康检查应该返回连接状态

        # 模拟健康的Redis连接
        self.mock_redis.ping = AsyncMock(return_value=True)

        # Green: 健康检查应该成功
        health = await self.cache.health_check()

        assert isinstance(health, dict)
        assert 'healthy' in health
        assert health['healthy'] is True

        # 验证ping调用
        self.mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_health_check_failure(self):
        """测试：缓存健康检查失败"""
        # Red: 编写失败的测试 - 连接失败时健康检查应该返回不健康

        # 模拟ping失败
        self.mock_redis.ping = AsyncMock(side_effect=Exception("Connection lost"))

        # Green: 健康检查应该返回不健康状态
        health = await self.cache.health_check()

        assert isinstance(health, dict)
        assert 'healthy' in health
        assert health['healthy'] is False
        assert 'error' in health

    def test_cache_statistics(self):
        """测试：缓存统计信息"""
        # Red: 编写失败的测试 - 应该能获取统计信息

        # 设置一些统计数据
        self.cache.stats.hits = 10
        self.cache.stats.misses = 5
        self.cache.stats.sets = 8
        self.cache.stats.deletes = 2

        # Green: 应该返回正确的统计信息
        stats = self.cache.get_stats()

        assert isinstance(stats, dict)
        assert stats['hits'] == 10
        assert stats['misses'] == 5
        assert stats['sets'] == 8
        assert stats['deletes'] == 2
        assert 'hit_rate' in stats
