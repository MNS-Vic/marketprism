"""
内存缓存TDD测试
专门用于提升memory_cache.py模块的测试覆盖率

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

# 导入内存缓存模块
from core.caching.cache_interface import (
    CacheKey, CacheValue, CacheLevel, CacheEvictionPolicy
)
from core.caching.memory_cache import MemoryCache, MemoryCacheConfig


class TestMemoryCacheConfig:
    """测试内存缓存配置"""
    
    def test_memory_cache_config_defaults(self):
        """测试：内存缓存配置默认值"""
        config = MemoryCacheConfig(name="test_cache")
        
        assert config.name == "test_cache"
        assert config.level == CacheLevel.MEMORY
        assert config.thread_safe is True
        assert config.auto_cleanup_interval == 60
        assert config.enable_warmup is False
        assert config.warmup_data is None
        
    def test_memory_cache_config_custom(self):
        """测试：自定义内存缓存配置"""
        warmup_data = {"test:key1": "value1", "test:key2": "value2"}
        
        config = MemoryCacheConfig(
            name="custom_cache",
            max_size=2000,
            thread_safe=False,
            auto_cleanup_interval=30,
            enable_warmup=True,
            warmup_data=warmup_data
        )
        
        assert config.name == "custom_cache"
        assert config.max_size == 2000
        assert config.thread_safe is False
        assert config.auto_cleanup_interval == 30
        assert config.enable_warmup is True
        assert config.warmup_data == warmup_data


class TestMemoryCacheInitialization:
    """测试内存缓存初始化"""
    
    def test_memory_cache_basic_initialization(self):
        """测试：基本初始化"""
        config = MemoryCacheConfig(name="test_cache")
        cache = MemoryCache(config)
        
        assert cache.config == config
        assert isinstance(cache._storage, dict)
        assert len(cache._storage) == 0
        assert cache._enabled is True
        assert cache.stats is not None
        
    def test_memory_cache_thread_safe_initialization(self):
        """测试：线程安全初始化"""
        # 线程安全模式
        config_safe = MemoryCacheConfig(name="safe_cache", thread_safe=True)
        cache_safe = MemoryCache(config_safe)
        assert cache_safe._lock is not None
        
        # 非线程安全模式
        config_unsafe = MemoryCacheConfig(name="unsafe_cache", thread_safe=False)
        cache_unsafe = MemoryCache(config_unsafe)
        assert cache_unsafe._lock is None
        
    def test_memory_cache_strategy_initialization(self):
        """测试：策略初始化"""
        config = MemoryCacheConfig(
            name="test_cache",
            eviction_policy=CacheEvictionPolicy.LRU,
            max_size=1000
        )
        
        with patch('core.caching.memory_cache.create_strategy') as mock_create:
            mock_strategy = Mock()
            mock_create.return_value = mock_strategy
            
            cache = MemoryCache(config)
            
            mock_create.assert_called_once_with(
                CacheEvictionPolicy.LRU,
                1000,
                default_ttl=config.default_ttl
            )
            assert cache.strategy == mock_strategy
            
    def test_memory_cache_cleanup_task_initialization(self):
        """测试：清理任务初始化"""
        # 启用后台清理
        config_with_cleanup = MemoryCacheConfig(
            name="cleanup_cache",
            background_cleanup=True
        )
        
        with patch.object(MemoryCache, '_start_cleanup_task') as mock_start:
            cache = MemoryCache(config_with_cleanup)
            mock_start.assert_called_once()
            
        # 禁用后台清理
        config_without_cleanup = MemoryCacheConfig(
            name="no_cleanup_cache",
            background_cleanup=False
        )
        
        with patch.object(MemoryCache, '_start_cleanup_task') as mock_start:
            cache = MemoryCache(config_without_cleanup)
            mock_start.assert_not_called()


class TestMemoryCacheBasicOperations:
    """测试内存缓存基本操作"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = MemoryCacheConfig(
            name="test_cache",
            max_size=100,
            background_cleanup=False  # 禁用后台清理以简化测试
        )
        self.cache = MemoryCache(self.config)
        
    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """测试：设置和获取缓存"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user", "id": 123})
        
        # 设置缓存
        result = await self.cache.set(key, value)
        assert result is True
        assert self.cache.stats.sets == 1
        
        # 获取缓存
        retrieved = await self.cache.get(key)
        assert retrieved is not None
        assert retrieved.data == value.data
        assert self.cache.stats.hits == 1
        
    @pytest.mark.asyncio
    async def test_cache_get_nonexistent(self):
        """测试：获取不存在的缓存"""
        key = CacheKey(namespace="test", key="nonexistent")
        
        result = await self.cache.get(key)
        assert result is None
        assert self.cache.stats.misses == 1
        
    @pytest.mark.asyncio
    async def test_cache_delete(self):
        """测试：删除缓存"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data="test_data")
        
        # 先设置
        await self.cache.set(key, value)
        assert await self.cache.exists(key) is True
        
        # 删除
        result = await self.cache.delete(key)
        assert result is True
        assert self.cache.stats.deletes == 1
        
        # 验证删除
        assert await self.cache.exists(key) is False
        assert await self.cache.get(key) is None
        
    @pytest.mark.asyncio
    async def test_cache_delete_nonexistent(self):
        """测试：删除不存在的缓存"""
        key = CacheKey(namespace="test", key="nonexistent")
        
        result = await self.cache.delete(key)
        assert result is False
        
    @pytest.mark.asyncio
    async def test_cache_exists(self):
        """测试：检查缓存存在性"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data="test_data")
        
        # 不存在
        assert await self.cache.exists(key) is False
        
        # 设置后存在
        await self.cache.set(key, value)
        assert await self.cache.exists(key) is True
        
        # 删除后不存在
        await self.cache.delete(key)
        assert await self.cache.exists(key) is False
        
    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """测试：清空缓存"""
        # 设置多个缓存项
        for i in range(5):
            key = CacheKey(namespace="test", key=f"item:{i}")
            value = CacheValue(data=f"data_{i}")
            await self.cache.set(key, value)
            
        assert await self.cache.size() == 5
        
        # 清空
        result = await self.cache.clear()
        assert result is True
        assert await self.cache.size() == 0
        assert self.cache.stats.current_size == 0
        
    @pytest.mark.asyncio
    async def test_cache_size(self):
        """测试：获取缓存大小"""
        assert await self.cache.size() == 0
        
        # 添加项目
        for i in range(3):
            key = CacheKey(namespace="test", key=f"item:{i}")
            value = CacheValue(data=f"data_{i}")
            await self.cache.set(key, value)
            
        assert await self.cache.size() == 3
        
    @pytest.mark.asyncio
    async def test_cache_keys(self):
        """测试：获取所有键"""
        # 添加一些键
        keys_data = [
            ("test", "user:1"),
            ("test", "user:2"),
            ("api", "session:1")
        ]
        
        for namespace, key_name in keys_data:
            key = CacheKey(namespace=namespace, key=key_name)
            value = CacheValue(data=f"data_{key_name}")
            await self.cache.set(key, value)
            
        # 获取所有键
        all_keys = await self.cache.keys()
        assert len(all_keys) == 3
        
        # 验证键的内容
        key_strings = [str(k) for k in all_keys]
        assert "test:user:1" in key_strings
        assert "test:user:2" in key_strings
        assert "api:session:1" in key_strings


class TestMemoryCacheExpiration:
    """测试内存缓存过期机制"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = MemoryCacheConfig(
            name="test_cache",
            background_cleanup=False
        )
        self.cache = MemoryCache(self.config)
        
    @pytest.mark.asyncio
    async def test_cache_ttl_setting(self):
        """测试：TTL设置"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data="test_data")
        ttl = timedelta(seconds=1)
        
        # 设置带TTL的缓存
        await self.cache.set(key, value, ttl)
        
        # 立即获取应该成功
        retrieved = await self.cache.get(key)
        assert retrieved is not None
        assert retrieved.expires_at is not None
        
    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """测试：缓存过期"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data="test_data")
        
        # 设置已过期的缓存
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        value.expires_at = past_time
        
        await self.cache.set(key, value)
        
        # 获取应该返回None（因为已过期）
        retrieved = await self.cache.get(key)
        assert retrieved is None
        assert self.cache.stats.misses == 1
        assert self.cache.stats.evictions == 1
        
    @pytest.mark.asyncio
    async def test_cache_default_ttl(self):
        """测试：默认TTL"""
        config = MemoryCacheConfig(
            name="ttl_cache",
            default_ttl=timedelta(hours=1),
            background_cleanup=False
        )
        cache = MemoryCache(config)
        
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data="test_data")
        
        # 设置缓存（应该使用默认TTL）
        await cache.set(key, value)
        
        # 获取并检查TTL
        retrieved = await cache.get(key)
        assert retrieved is not None
        assert retrieved.expires_at is not None
        
        # TTL应该大约是1小时
        ttl = retrieved.time_to_live()
        assert ttl is not None
        assert ttl.total_seconds() > 3500  # 略小于1小时（考虑执行时间）
        
    @pytest.mark.asyncio
    async def test_cache_cleanup_expired(self):
        """测试：清理过期项"""
        # 设置一些过期和未过期的项
        now = datetime.now(timezone.utc)
        
        # 未过期项
        key1 = CacheKey(namespace="test", key="valid:1")
        value1 = CacheValue(data="data1", expires_at=now + timedelta(hours=1))
        await self.cache.set(key1, value1)
        
        # 过期项
        key2 = CacheKey(namespace="test", key="expired:1")
        value2 = CacheValue(data="data2", expires_at=now - timedelta(hours=1))
        await self.cache.set(key2, value2)
        
        # 手动清理过期项
        expired_count = await self.cache._cleanup_expired()
        
        # 验证清理结果
        assert expired_count == 1
        assert await self.cache.exists(key1) is True
        assert await self.cache.exists(key2) is False


class TestMemoryCacheBatchOperations:
    """测试内存缓存批量操作"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = MemoryCacheConfig(
            name="test_cache",
            background_cleanup=False
        )
        self.cache = MemoryCache(self.config)
        
    @pytest.mark.asyncio
    async def test_cache_get_many(self):
        """测试：批量获取"""
        # 设置一些缓存项
        keys = []
        for i in range(3):
            key = CacheKey(namespace="test", key=f"item:{i}")
            value = CacheValue(data=f"data_{i}")
            await self.cache.set(key, value)
            keys.append(key)
            
        # 添加一个不存在的键
        nonexistent_key = CacheKey(namespace="test", key="nonexistent")
        keys.append(nonexistent_key)
        
        # 批量获取
        results = await self.cache.get_many(keys)
        
        assert len(results) == 4
        assert results[keys[0]] is not None
        assert results[keys[1]] is not None
        assert results[keys[2]] is not None
        assert results[keys[3]] is None  # 不存在的键
        
    @pytest.mark.asyncio
    async def test_cache_set_many(self):
        """测试：批量设置"""
        items = {}
        for i in range(3):
            key = CacheKey(namespace="test", key=f"item:{i}")
            value = CacheValue(data=f"data_{i}")
            items[key] = value
            
        # 批量设置
        results = await self.cache.set_many(items)
        
        assert len(results) == 3
        assert all(success for success in results.values())
        assert self.cache.stats.sets == 3
        
        # 验证设置成功
        for key in items.keys():
            assert await self.cache.exists(key) is True
            
    @pytest.mark.asyncio
    async def test_cache_delete_many(self):
        """测试：批量删除"""
        # 设置一些缓存项
        keys = []
        for i in range(3):
            key = CacheKey(namespace="test", key=f"item:{i}")
            value = CacheValue(data=f"data_{i}")
            await self.cache.set(key, value)
            keys.append(key)
            
        # 批量删除
        results = await self.cache.delete_many(keys)
        
        assert len(results) == 3
        assert all(success for success in results.values())
        
        # 验证删除成功
        for key in keys:
            assert await self.cache.exists(key) is False


class TestMemoryCacheAdvancedFeatures:
    """测试内存缓存高级功能"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = MemoryCacheConfig(
            name="test_cache",
            background_cleanup=False
        )
        self.cache = MemoryCache(self.config)
        
    @pytest.mark.asyncio
    async def test_cache_memory_stats(self):
        """测试：内存统计"""
        # 添加一些数据
        for i in range(5):
            key = CacheKey(namespace="test", key=f"item:{i}")
            value = CacheValue(data=f"data_{i}" * 100)  # 较大的数据
            await self.cache.set(key, value)
            
        # 获取内存统计
        stats = await self.cache.get_memory_stats()
        
        assert isinstance(stats, dict)
        assert stats['total_items'] == 5
        assert stats['total_size_bytes'] > 0
        assert stats['average_size_bytes'] > 0
        assert 'size_distribution' in stats
        assert 'memory_utilization' in stats
        
    @pytest.mark.asyncio
    async def test_cache_compact(self):
        """测试：缓存压缩"""
        # 添加一些过期项
        now = datetime.now(timezone.utc)
        
        for i in range(3):
            key = CacheKey(namespace="test", key=f"expired:{i}")
            value = CacheValue(data=f"data_{i}", expires_at=now - timedelta(hours=1))
            await self.cache.set(key, value)
            
        # 添加一些有效项
        for i in range(2):
            key = CacheKey(namespace="test", key=f"valid:{i}")
            value = CacheValue(data=f"data_{i}")
            await self.cache.set(key, value)
            
        # 压缩
        expired_count = await self.cache.compact()
        
        assert expired_count == 3
        assert await self.cache.size() == 2
        
    @pytest.mark.asyncio
    async def test_cache_export_import(self):
        """测试：缓存导出导入"""
        # 添加一些数据
        original_data = {}
        for i in range(3):
            key = CacheKey(namespace="test", key=f"item:{i}")
            value = CacheValue(data=f"data_{i}")
            await self.cache.set(key, value)
            original_data[str(key)] = f"data_{i}"
            
        # 导出数据
        exported = await self.cache.export_data()
        
        assert isinstance(exported, dict)
        assert len(exported) == 3
        
        # 清空缓存
        await self.cache.clear()
        assert await self.cache.size() == 0
        
        # 导入数据
        imported_count = await self.cache.import_data(exported)
        
        assert imported_count == 3
        assert await self.cache.size() == 3
        
        # 验证数据正确性
        for key_str, expected_data in original_data.items():
            parts = key_str.split(':', 1)
            key = CacheKey(namespace=parts[0], key=parts[1])
            retrieved = await self.cache.get(key)
            assert retrieved is not None
            assert retrieved.data == expected_data
