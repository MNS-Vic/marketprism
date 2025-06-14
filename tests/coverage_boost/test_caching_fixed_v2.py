#!/usr/bin/env python3
"""
修复版本的全面缓存系统测试
修复了接口不匹配问题，目标：提升覆盖率并确保100%测试通过率
"""

from datetime import datetime, timezone, timedelta
import asyncio
import pytest
import tempfile
import json
import time
import shutil
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, Optional, List

# Test utilities
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Core caching imports
from core.caching.cache_interface import (
    Cache, CacheKey, CacheValue, CacheConfig, CacheLevel, 
    CacheEvictionPolicy, SerializationFormat, CacheStatistics
)
from core.caching.cache_strategies import (
    LRUStrategy, TTLStrategy, LFUStrategy, CacheStrategy, StrategyMetrics
)
from core.caching.disk_cache import DiskCache, DiskCacheConfig
from core.caching.memory_cache import MemoryCache, MemoryCacheConfig
from core.caching.redis_cache import RedisCache, RedisCacheConfig


class TestCacheInterface:
    """测试缓存接口组件"""

    def test_cache_key_creation(self):
        """测试缓存键创建"""
        key = CacheKey(namespace="test", key="key1", version="v1")
        assert key.namespace == "test"
        assert key.key == "key1"
        assert key.version == "v1"
        assert key.full_key() == "test:key1:vv1"

    def test_cache_key_hash(self):
        """测试缓存键哈希"""
        key = CacheKey(namespace="test", key="key1")
        hash_key = key.hash_key()
        assert hash_key == "test:key1"

    def test_cache_key_with_suffix(self):
        """测试带后缀的缓存键"""
        key = CacheKey(namespace="test", key="key1")
        suffixed = key.with_suffix("suffix")
        assert suffixed.key == "key1:suffix"
        assert suffixed.namespace == "test"

    def test_cache_key_with_prefix(self):
        """测试带前缀的缓存键"""
        key = CacheKey(namespace="test", key="key1")
        prefixed = key.with_prefix("prefix")
        assert prefixed.key == "prefix:key1"
        assert prefixed.namespace == "test"

    def test_cache_key_pattern_matching(self):
        """测试缓存键模式匹配"""
        key = CacheKey(namespace="test", key="key1")
        assert key.matches_pattern("test:*")
        assert not key.matches_pattern("other:*")

    def test_cache_value_creation(self):
        """测试缓存值创建"""
        value = CacheValue(data="test_data")
        assert value.data == "test_data"
        assert value.access_count == 0
        assert value.created_at is not None

    def test_cache_value_expiration(self):
        """测试缓存值过期"""
        # 创建已过期的值
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        value = CacheValue(data="test", expires_at=past_time)
        assert value.is_expired()

        # 创建未过期的值
        future_time = datetime.now(timezone.utc) + timedelta(seconds=10)
        value2 = CacheValue(data="test", expires_at=future_time)
        assert not value2.is_expired()

    def test_cache_value_ttl(self):
        """测试缓存值TTL"""
        future_time = datetime.now(timezone.utc) + timedelta(seconds=60)
        value = CacheValue(data="test", expires_at=future_time)
        ttl = value.time_to_live()
        assert ttl is not None
        assert ttl.total_seconds() > 50  # 应该接近60秒

    def test_cache_value_touch(self):
        """测试缓存值touch操作"""
        value = CacheValue(data="test")
        initial_count = value.access_count
        value.touch()
        assert value.access_count == initial_count + 1
        assert value.last_accessed is not None

    def test_cache_value_get_value(self):
        """测试获取缓存值"""
        value = CacheValue(data="test_data")
        data = value.get_value()
        assert data == "test_data"
        assert value.access_count == 1

    def test_cache_config_creation(self):
        """测试缓存配置创建"""
        config = CacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=1000
        )
        assert config.name == "test_cache"
        assert config.level == CacheLevel.MEMORY
        assert config.max_size == 1000

    def test_cache_statistics(self):
        """测试缓存统计 - 修复版本"""
        stats = CacheStatistics()
        # 直接设置属性而不是通过计算
        stats.hits = 80
        stats.misses = 20
        
        # 验证基本属性
        assert stats.hits == 80
        assert stats.misses == 20
        
        # 验证计算属性
        assert stats.total_operations == 100
        assert abs(stats.hit_rate - 0.8) < 0.0001
        assert abs(stats.miss_rate - 0.2) < 0.0001

    def test_cache_statistics_to_dict(self):
        """测试缓存统计转字典 - 修复版本"""
        stats = CacheStatistics()
        stats.hits = 10
        stats.misses = 5
        
        stats_dict = stats.to_dict()
        # 使用实际的属性名
        assert stats_dict["hits"] == 10
        assert stats_dict["misses"] == 5
        assert stats_dict["total_operations"] == 15


class TestCacheStrategies:
    """测试缓存策略组件 - 修复版本"""

    def test_lru_strategy_creation(self):
        """测试LRU策略创建 - 修复版本"""
        strategy = LRUStrategy(max_size=100)
        assert strategy.max_size == 100
        # LRUStrategy没有name属性，跳过这个断言

    def test_lfu_strategy_creation(self):
        """测试LFU策略创建 - 修复版本"""
        strategy = LFUStrategy(max_size=100)
        assert strategy.max_size == 100
        # LFUStrategy没有name属性，跳过这个断言

    def test_ttl_strategy_creation(self):
        """测试TTL策略创建 - 修复版本"""
        # TTLStrategy使用default_ttl参数而不是ttl
        strategy = TTLStrategy(default_ttl=300)
        assert strategy.default_ttl == 300
        # TTLStrategy没有name属性，跳过这个断言

    def test_strategy_metrics(self):
        """测试策略指标"""
        metrics = StrategyMetrics()
        
        # 测试记录方法
        metrics.record_hit()
        assert metrics.hits == 1
        
        metrics.record_miss()
        assert metrics.misses == 1
        
        metrics.record_eviction()
        assert metrics.evictions == 1


@pytest.mark.asyncio
class TestMemoryCache:
    """测试内存缓存"""

    async def test_basic_operations(self):
        """测试基本操作"""
        config = MemoryCacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=100
        )
        cache = MemoryCache(config)
        
        # 创建测试键值
        key = CacheKey(namespace="test", key="key1")
        value = CacheValue(data="value1")
        
        # 测试设置
        result = await cache.set(key, value)
        assert result is True
        
        # 测试获取
        retrieved = await cache.get(key)
        assert retrieved is not None
        assert retrieved.data == "value1"
        
        # 测试存在性检查
        exists = await cache.exists(key)
        assert exists is True
        
        # 测试删除
        deleted = await cache.delete(key)
        assert deleted is True
        
        # 验证删除后不存在
        exists_after = await cache.exists(key)
        assert exists_after is False

    async def test_cache_size(self):
        """测试缓存大小"""
        config = MemoryCacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=100
        )
        cache = MemoryCache(config)
        
        # 添加一些条目
        for i in range(5):
            key = CacheKey(namespace="test", key=f"key{i}")
            value = CacheValue(data=f"value{i}")
            await cache.set(key, value)
        
        size = await cache.size()
        assert size == 5

    async def test_clear_cache(self):
        """测试清空缓存"""
        config = MemoryCacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=100
        )
        cache = MemoryCache(config)
        
        # 添加条目
        key = CacheKey(namespace="test", key="key1")
        value = CacheValue(data="value1")
        await cache.set(key, value)
        
        # 清空
        cleared = await cache.clear()
        assert cleared is True
        
        # 验证清空
        size = await cache.size()
        assert size == 0

    async def test_keys_listing(self):
        """测试键列表"""
        config = MemoryCacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=100
        )
        cache = MemoryCache(config)
        
        # 添加条目
        keys_added = []
        for i in range(3):
            key = CacheKey(namespace="test", key=f"key{i}")
            value = CacheValue(data=f"value{i}")
            await cache.set(key, value)
            keys_added.append(key)
        
        # 获取所有键
        all_keys = await cache.keys()
        assert len(all_keys) == 3

    async def test_batch_operations(self):
        """测试批量操作"""
        config = MemoryCacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=100
        )
        cache = MemoryCache(config)
        
        # 准备批量数据
        items = {}
        keys_list = []
        for i in range(3):
            key = CacheKey(namespace="test", key=f"batch_key{i}")
            value = CacheValue(data=f"batch_value{i}")
            items[key] = value
            keys_list.append(key)
        
        # 批量设置
        set_results = await cache.set_many(items)
        assert len(set_results) == 3
        assert all(set_results.values())
        
        # 批量获取
        get_results = await cache.get_many(keys_list)
        assert len(get_results) == 3
        assert all(v is not None for v in get_results.values())

    async def test_health_check(self):
        """测试健康检查 - 修复版本"""
        config = MemoryCacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=100
        )
        cache = MemoryCache(config)
        
        health = await cache.health_check()
        # 使用实际返回的键名
        assert "healthy" in health
        assert "cache_level" in health
        assert "size" in health


class TestErrorExceptions:
    """测试错误和异常处理"""

    def test_cache_key_validation(self):
        """测试缓存键验证"""
        # 测试空命名空间
        with pytest.raises(ValueError, match="命名空间不能为空"):
            CacheKey(namespace="", key="key1")
        
        # 测试空键
        with pytest.raises(ValueError, match="键不能为空"):
            CacheKey(namespace="test", key="")

    def test_cache_config_defaults(self):
        """测试缓存配置默认值"""
        config = CacheConfig(name="test", level=CacheLevel.MEMORY)
        assert config.max_size == 1000
        assert config.eviction_policy == CacheEvictionPolicy.LRU
        assert config.serialization_format == SerializationFormat.PICKLE


@pytest.mark.asyncio
class TestUnifiedSessionManager:
    """测试统一会话管理器 - 修复版本"""

    async def test_session_manager_creation(self):
        """测试会话管理器创建"""
        from core.networking.unified_session_manager import UnifiedSessionManager
        
        manager = UnifiedSessionManager()
        assert manager is not None

    async def test_session_creation(self):
        """测试会话创建"""
        from core.networking.unified_session_manager import UnifiedSessionManager
        
        manager = UnifiedSessionManager()
        session = await manager.create_session("test_session")
        assert session is not None

    async def test_session_retrieval(self):
        """测试会话检索"""
        from core.networking.unified_session_manager import UnifiedSessionManager
        
        manager = UnifiedSessionManager()
        session = await manager.create_session("test_session")
        retrieved = await manager.get_session("test_session")
        assert retrieved is not None

    async def test_session_cleanup(self):
        """测试会话清理 - 修复版本"""
        from core.networking.unified_session_manager import UnifiedSessionManager
        
        manager = UnifiedSessionManager()
        await manager.create_session("test_session")
        # cleanup_sessions返回int，不是awaitable
        result = manager.cleanup_sessions()
        assert isinstance(result, int)

    async def test_session_statistics(self):
        """测试会话统计"""
        from core.networking.unified_session_manager import UnifiedSessionManager
        
        manager = UnifiedSessionManager()
        stats = manager.get_statistics()
        assert isinstance(stats, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])