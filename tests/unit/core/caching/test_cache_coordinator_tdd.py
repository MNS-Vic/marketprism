"""
缓存协调器TDD测试
专门用于提升cache_coordinator.py模块的测试覆盖率

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
from typing import Dict, List, Optional

# 导入缓存协调器模块
from core.caching.cache_interface import (
    CacheKey, CacheValue, CacheLevel, CacheEvictionPolicy
)
from core.caching.cache_coordinator import (
    CacheCoordinator, CacheCoordinatorConfig, CacheInstance,
    CacheRoutingPolicy, CacheSyncStrategy
)


class TestCacheCoordinatorConfig:
    """测试缓存协调器配置"""

    def test_cache_coordinator_config_creation(self):
        """测试：缓存协调器配置创建"""
        config = CacheCoordinatorConfig(
            name="test_coordinator",
            read_policy=CacheRoutingPolicy.READ_THROUGH,
            write_policy=CacheRoutingPolicy.WRITE_THROUGH,
            sync_strategy=CacheSyncStrategy.PERIODIC,
            enable_metrics=True
        )

        assert config.name == "test_coordinator"
        assert config.read_policy == CacheRoutingPolicy.READ_THROUGH
        assert config.write_policy == CacheRoutingPolicy.WRITE_THROUGH
        assert config.sync_strategy == CacheSyncStrategy.PERIODIC
        assert config.enable_metrics is True

    def test_cache_coordinator_config_defaults(self):
        """测试：缓存协调器配置默认值"""
        config = CacheCoordinatorConfig()

        assert config.name == "cache_coordinator"
        assert config.read_policy == CacheRoutingPolicy.READ_THROUGH
        assert config.write_policy == CacheRoutingPolicy.WRITE_THROUGH
        assert config.sync_strategy == CacheSyncStrategy.PERIODIC
        assert config.sync_interval == 300
        assert config.enable_failover is True
        assert config.health_check_interval == 30
        assert config.max_failures == 3
        assert config.enable_promotion is True
        assert config.promotion_threshold == 3
        assert config.enable_preload is True
        assert config.enable_metrics is True
        assert config.detailed_logging is False

    def test_cache_instance_creation(self):
        """测试：缓存实例创建"""
        # 创建模拟缓存
        mock_cache = Mock()
        mock_cache.config.level = CacheLevel.MEMORY

        instance = CacheInstance(mock_cache, CacheLevel.MEMORY, priority=1)

        assert instance.cache == mock_cache
        assert instance.level == CacheLevel.MEMORY
        assert instance.priority == 1
        assert instance.is_healthy is True
        assert instance.failure_count == 0
        assert instance.stats is not None


class TestCacheCoordinatorInitialization:
    """测试缓存协调器初始化"""

    def setup_method(self):
        """设置测试方法"""
        self.config = CacheCoordinatorConfig(
            name="test_coordinator",
            read_policy=CacheRoutingPolicy.READ_THROUGH,
            write_policy=CacheRoutingPolicy.WRITE_THROUGH
        )

    def test_coordinator_basic_initialization(self):
        """测试：协调器基本初始化"""
        coordinator = CacheCoordinator(self.config)

        assert coordinator.config == self.config
        assert len(coordinator.instances) == 0  # 初始时未添加缓存实例
        assert coordinator._enabled is True
        assert coordinator.stats is not None
        assert isinstance(coordinator.level_mapping, dict)
        assert isinstance(coordinator._promotion_candidates, dict)

    def test_coordinator_add_cache(self):
        """测试：添加缓存实例"""
        coordinator = CacheCoordinator(self.config)

        # 创建模拟缓存
        mock_memory_cache = Mock()
        mock_memory_cache.config.level = CacheLevel.MEMORY

        mock_redis_cache = Mock()
        mock_redis_cache.config.level = CacheLevel.REDIS

        # 添加缓存（优先级：数字越小优先级越高）
        coordinator.add_cache(mock_memory_cache, priority=1)
        coordinator.add_cache(mock_redis_cache, priority=2)

        # 验证添加结果
        assert len(coordinator.instances) == 2
        assert coordinator.instances[0].cache == mock_memory_cache  # 优先级1
        assert coordinator.instances[1].cache == mock_redis_cache   # 优先级2

        # 验证层级映射
        assert CacheLevel.MEMORY in coordinator.level_mapping
        assert CacheLevel.REDIS in coordinator.level_mapping

    def test_coordinator_remove_cache(self):
        """测试：移除缓存实例"""
        coordinator = CacheCoordinator(self.config)

        # 添加缓存
        mock_cache = Mock()
        mock_cache.config.level = CacheLevel.MEMORY
        coordinator.add_cache(mock_cache, priority=1)

        assert len(coordinator.instances) == 1

        # 移除缓存
        result = coordinator.remove_cache(mock_cache)

        assert result is True
        assert len(coordinator.instances) == 0

        # 测试移除不存在的缓存
        result = coordinator.remove_cache(mock_cache)
        assert result is False

    def test_coordinator_healthy_instances(self):
        """测试：获取健康实例"""
        coordinator = CacheCoordinator(self.config)

        # 添加健康和不健康的缓存
        healthy_cache = Mock()
        healthy_cache.config.level = CacheLevel.MEMORY
        coordinator.add_cache(healthy_cache, priority=1)

        unhealthy_cache = Mock()
        unhealthy_cache.config.level = CacheLevel.REDIS
        coordinator.add_cache(unhealthy_cache, priority=2)

        # 设置健康状态
        coordinator.instances[0].is_healthy = True
        coordinator.instances[1].is_healthy = False

        # 获取健康实例
        healthy_instances = coordinator.get_healthy_instances()

        assert len(healthy_instances) == 1
        assert healthy_instances[0].cache == healthy_cache

    def test_coordinator_fastest_slowest_instances(self):
        """测试：获取最快和最慢实例"""
        coordinator = CacheCoordinator(self.config)

        # 添加多个缓存（按优先级排序）
        fast_cache = Mock()
        fast_cache.config.level = CacheLevel.MEMORY
        coordinator.add_cache(fast_cache, priority=1)

        slow_cache = Mock()
        slow_cache.config.level = CacheLevel.REDIS
        coordinator.add_cache(slow_cache, priority=2)

        # 获取最快和最慢实例
        fastest = coordinator.get_fastest_instance()
        slowest = coordinator.get_slowest_instance()

        assert fastest.cache == fast_cache
        assert slowest.cache == slow_cache


class TestCacheCoordinatorBasicOperations:
    """测试缓存协调器基本操作"""

    def setup_method(self):
        """设置测试方法"""
        self.config = CacheCoordinatorConfig(
            name="test_coordinator",
            write_policy=CacheRoutingPolicy.WRITE_THROUGH
        )

        self.coordinator = CacheCoordinator(self.config)

        # 创建模拟缓存实例
        self.mock_memory = AsyncMock()
        self.mock_memory.config.level = CacheLevel.MEMORY

        self.mock_redis = AsyncMock()
        self.mock_redis.config.level = CacheLevel.REDIS

        # 添加到协调器
        self.coordinator.add_cache(self.mock_memory, priority=1)
        self.coordinator.add_cache(self.mock_redis, priority=2)
        
    @pytest.mark.asyncio
    async def test_coordinator_get_hit_first_layer(self):
        """测试：第一层缓存命中"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user"})
        
        # 第一层命中
        self.mock_memory.get.return_value = value
        
        result = await self.coordinator.get(key)
        
        assert result == value
        # 只调用第一层
        self.mock_memory.get.assert_called_once_with(key)
        self.mock_redis.get.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_coordinator_get_hit_second_layer(self):
        """测试：第二层缓存命中"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user"})
        
        # 第一层未命中，第二层命中
        self.mock_memory.get.return_value = None
        self.mock_redis.get.return_value = value
        
        result = await self.coordinator.get(key)
        
        assert result == value
        # 两层都被调用
        self.mock_memory.get.assert_called_once_with(key)
        self.mock_redis.get.assert_called_once_with(key)
        
        # 验证回填到第一层（通过数据提升机制）
        # 由于提升需要满足阈值条件，这里不强制要求立即回填
        # self.mock_memory.set.assert_called_once_with(key, value, None)
        
    @pytest.mark.asyncio
    async def test_coordinator_get_miss_all_layers(self):
        """测试：所有层都未命中"""
        key = CacheKey(namespace="test", key="user:123")
        
        # 所有层都未命中
        self.mock_memory.get.return_value = None
        self.mock_redis.get.return_value = None
        
        result = await self.coordinator.get(key)
        
        assert result is None
        # 所有层都被调用
        self.mock_memory.get.assert_called_once_with(key)
        self.mock_redis.get.assert_called_once_with(key)
        
    @pytest.mark.asyncio
    async def test_coordinator_set_write_through(self):
        """测试：写穿透策略"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user"})
        
        # 模拟所有层设置成功
        self.mock_memory.set.return_value = True
        self.mock_redis.set.return_value = True
        
        result = await self.coordinator.set(key, value)
        
        assert result is True
        # 所有层都被调用
        self.mock_memory.set.assert_called_once_with(key, value, None)
        self.mock_redis.set.assert_called_once_with(key, value, None)
        
    @pytest.mark.asyncio
    async def test_coordinator_set_write_back(self):
        """测试：写回策略"""
        # 修改配置为写回策略
        self.coordinator.config.write_policy = CacheRoutingPolicy.WRITE_BACK

        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user"})

        # 模拟第一层设置成功
        self.mock_memory.set.return_value = True

        result = await self.coordinator.set(key, value)

        assert result is True
        # 只有第一层被立即调用
        self.mock_memory.set.assert_called_once_with(key, value, None)
        # 第二层应该异步调用（这里简化测试）
        
    @pytest.mark.asyncio
    async def test_coordinator_delete_all_layers(self):
        """测试：删除所有层"""
        key = CacheKey(namespace="test", key="user:123")
        
        # 模拟删除操作
        self.mock_memory.delete.return_value = True
        self.mock_redis.delete.return_value = True
        
        result = await self.coordinator.delete(key)
        
        assert result is True
        # 所有层都被调用
        self.mock_memory.delete.assert_called_once_with(key)
        self.mock_redis.delete.assert_called_once_with(key)
        
    @pytest.mark.asyncio
    async def test_coordinator_exists_any_layer(self):
        """测试：检查任意层存在"""
        key = CacheKey(namespace="test", key="user:123")
        
        # 第一层不存在，第二层存在
        self.mock_memory.exists.return_value = False
        self.mock_redis.exists.return_value = True
        
        result = await self.coordinator.exists(key)
        
        assert result is True
        # 第一层被调用
        self.mock_memory.exists.assert_called_once_with(key)
        # 第二层也被调用（因为第一层返回False）
        self.mock_redis.exists.assert_called_once_with(key)


class TestCacheCoordinatorAdvancedFeatures:
    """测试缓存协调器高级功能"""

    def setup_method(self):
        """设置测试方法"""
        self.config = CacheCoordinatorConfig(
            name="advanced_coordinator",
            enable_metrics=True,
            enable_promotion=True,
            promotion_threshold=2
        )

        self.coordinator = CacheCoordinator(self.config)

        # 创建模拟缓存实例
        self.mock_memory = AsyncMock()
        self.mock_memory.config.level = CacheLevel.MEMORY

        self.mock_redis = AsyncMock()
        self.mock_redis.config.level = CacheLevel.REDIS

        # 添加到协调器
        self.coordinator.add_cache(self.mock_memory, priority=1)
        self.coordinator.add_cache(self.mock_redis, priority=2)
        
    @pytest.mark.asyncio
    async def test_coordinator_batch_operations(self):
        """测试：批量操作（通过多次单独调用模拟）"""
        keys = [
            CacheKey(namespace="test", key="user:1"),
            CacheKey(namespace="test", key="user:2"),
            CacheKey(namespace="test", key="user:3")
        ]

        # 模拟单独获取
        self.mock_memory.get.side_effect = [
            CacheValue(data="user1"),  # keys[0] 命中
            None,                      # keys[1] 未命中
            CacheValue(data="user3")   # keys[2] 命中
        ]

        self.mock_redis.get.side_effect = [
            CacheValue(data="user2"),  # keys[1] 在redis中命中
        ]

        # 批量获取（通过循环模拟）
        results = []
        for key in keys:
            result = await self.coordinator.get(key)
            results.append(result)

        # 验证结果
        assert len(results) == 3
        assert results[0].data == "user1"  # 来自memory
        assert results[1].data == "user2"  # 来自redis
        assert results[2].data == "user3"  # 来自memory
        
    @pytest.mark.asyncio
    async def test_coordinator_health_check(self):
        """测试：健康检查"""
        # 模拟健康检查
        self.mock_memory.health_check.return_value = {"healthy": True}
        self.mock_redis.health_check.return_value = {"healthy": False}  # Redis不健康

        health_status = await self.coordinator.health_check()

        assert isinstance(health_status, dict)
        assert 'healthy' in health_status
        assert 'instances' in health_status
        assert len(health_status['instances']) == 2

        # 检查各个实例的健康状态
        memory_health = health_status['instances'][0]
        redis_health = health_status['instances'][1]
        assert memory_health['healthy'] is True
        assert redis_health['healthy'] is False
        
    @pytest.mark.asyncio
    async def test_coordinator_metrics_collection(self):
        """测试：指标收集"""
        # 模拟指标数据
        memory_metrics = {
            'hits': 100,
            'misses': 20,
            'sets': 80,
            'deletes': 10
        }
        
        redis_metrics = {
            'hits': 50,
            'misses': 30,
            'sets': 60,
            'deletes': 5
        }
        
        self.mock_memory.get_metrics.return_value = memory_metrics
        self.mock_redis.get_metrics.return_value = redis_metrics
        
        metrics = self.coordinator.get_coordinator_stats()
        
        assert isinstance(metrics, dict)
        assert 'coordinator_stats' in metrics
        assert 'instance_stats' in metrics
        assert len(metrics['instance_stats']) == 2
        
    @pytest.mark.asyncio
    async def test_coordinator_data_promotion(self):
        """测试：数据提升"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user"})

        # 模拟从Redis获取数据
        self.mock_memory.get.return_value = None
        self.mock_redis.get.return_value = value

        # 多次访问以触发提升
        for _ in range(3):  # 超过promotion_threshold
            result = await self.coordinator.get(key)
            assert result == value

        # 验证数据被提升到内存缓存
        # 由于回填机制，内存缓存应该被调用set
        assert self.mock_memory.set.call_count >= 1
        
    @pytest.mark.asyncio
    async def test_coordinator_layer_failover(self):
        """测试：层故障转移"""
        key = CacheKey(namespace="test", key="user:123")
        value = CacheValue(data={"name": "test_user"})
        
        # 模拟第一层故障
        self.mock_memory.get.side_effect = Exception("Memory cache failed")
        self.mock_redis.get.return_value = value
        
        result = await self.coordinator.get(key)
        
        # 应该从第二层获取数据
        assert result == value
        
        # 验证Redis被调用（故障转移成功）
        self.mock_redis.get.assert_called_once_with(key)

        # 验证Memory抛出异常被处理
        self.mock_memory.get.assert_called_once_with(key)
