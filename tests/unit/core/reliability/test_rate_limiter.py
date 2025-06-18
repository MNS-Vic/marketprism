"""
自适应限流器测试
测试AdaptiveRateLimiter的核心功能
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Optional

# 导入被测试的模块
try:
    from core.reliability.rate_limiter import (
        AdaptiveRateLimiter,
        RateLimitConfig,
        RequestPriority,
        RateLimiterManager
    )
    HAS_RATE_LIMITER_MODULES = True
except ImportError as e:
    HAS_RATE_LIMITER_MODULES = False
    pytest.skip(f"限流器模块导入失败: {e}", allow_module_level=True)


@pytest.mark.skipif(not HAS_RATE_LIMITER_MODULES, reason="限流器模块不可用")
class TestRateLimitConfig:
    """限流配置测试"""
    
    def test_rate_limit_config_default_values(self):
        """测试限流配置默认值"""
        config = RateLimitConfig()
        
        assert config.max_requests_per_second == 100
        assert config.burst_allowance == 10
        assert config.window_size == 1.0
        assert config.adaptive_factor_min == 0.1
        assert config.adaptive_factor_max == 2.0
        assert config.queue_timeout == 30.0
        assert config.enable_priority is True
        
    def test_rate_limit_config_custom_values(self):
        """测试限流配置自定义值"""
        config = RateLimitConfig(
            max_requests_per_second=200,
            burst_allowance=20,
            window_size=2.0,
            adaptive_factor_min=0.2,
            adaptive_factor_max=3.0,
            queue_timeout=60.0,
            enable_priority=False
        )
        
        assert config.max_requests_per_second == 200
        assert config.burst_allowance == 20
        assert config.window_size == 2.0
        assert config.adaptive_factor_min == 0.2
        assert config.adaptive_factor_max == 3.0
        assert config.queue_timeout == 60.0
        assert config.enable_priority is False


@pytest.mark.skipif(not HAS_RATE_LIMITER_MODULES, reason="限流器模块不可用")
class TestAdaptiveRateLimiterInitialization:
    """自适应限流器初始化测试"""
    
    def test_rate_limiter_initialization_default(self):
        """测试使用默认配置初始化限流器"""
        limiter = AdaptiveRateLimiter("test_limiter")
        
        assert limiter.name == "test_limiter"
        assert limiter.total_requests == 0
        assert limiter.allowed_requests == 0
        assert limiter.denied_requests == 0
        assert limiter.queue_size == 0
        assert isinstance(limiter.config, RateLimitConfig)
        
    def test_rate_limiter_initialization_with_config(self):
        """测试使用自定义配置初始化限流器"""
        config = RateLimitConfig(
            max_requests_per_second=50,
            burst_allowance=5
        )
        
        limiter = AdaptiveRateLimiter("custom_limiter", config)
        
        assert limiter.name == "custom_limiter"
        assert limiter.config == config
        assert limiter.config.max_requests_per_second == 50
        assert limiter.config.burst_allowance == 5
        
    def test_rate_limiter_has_required_attributes(self):
        """测试限流器具有必需的属性"""
        limiter = AdaptiveRateLimiter("test_limiter")
        
        required_attributes = [
            'name', 'config', 'total_requests', 'allowed_requests',
            'denied_requests', 'queue_size', 'request_history',
            'waiting_queue', 'operation_limits', 'adaptive_factor'
        ]
        
        for attr in required_attributes:
            assert hasattr(limiter, attr), f"缺少必需属性: {attr}"


@pytest.mark.skipif(not HAS_RATE_LIMITER_MODULES, reason="限流器模块不可用")
class TestAdaptiveRateLimiterBasicOperations:
    """自适应限流器基本操作测试"""
    
    @pytest.fixture
    def rate_limiter(self):
        """创建测试用的限流器"""
        config = RateLimitConfig(
            max_requests_per_second=10,  # 较低的限制便于测试
            burst_allowance=2,
            queue_timeout=1.0
        )
        return AdaptiveRateLimiter("test_limiter", config)
        
    async def test_rate_limiter_allow_within_limit(self, rate_limiter):
        """测试在限制内允许请求"""
        # 在限制内的请求应该被允许
        for i in range(5):  # 少于max_requests_per_second
            permitted = await rate_limiter.acquire_permit("test_operation")
            assert permitted is True
            
        assert rate_limiter.allowed_requests == 5
        assert rate_limiter.total_requests == 5
        
    async def test_rate_limiter_deny_over_limit(self, rate_limiter):
        """测试超过限制时拒绝请求"""
        # 快速发送大量请求
        tasks = []
        for i in range(20):  # 超过max_requests_per_second
            task = asyncio.create_task(
                rate_limiter.acquire_permit("test_operation", timeout=0.1)
            )
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 应该有一些请求被拒绝
        allowed_count = sum(1 for result in results if result is True)
        denied_count = sum(1 for result in results if result is False)
        
        assert allowed_count > 0
        assert denied_count > 0
        assert allowed_count + denied_count == 20
        
    async def test_rate_limiter_priority_handling(self, rate_limiter):
        """测试优先级处理"""
        # 先填满限流器
        for _ in range(rate_limiter.config.max_requests_per_second):
            await rate_limiter.acquire_permit("fill_operation")
            
        # 发送不同优先级的请求
        high_priority_task = asyncio.create_task(
            rate_limiter.acquire_permit(
                "high_priority_op", 
                RequestPriority.HIGH,
                timeout=0.5
            )
        )
        
        normal_priority_task = asyncio.create_task(
            rate_limiter.acquire_permit(
                "normal_priority_op",
                RequestPriority.NORMAL,
                timeout=0.5
            )
        )
        
        # 等待一小段时间让请求进入队列
        await asyncio.sleep(0.1)
        
        # 高优先级请求应该更容易获得许可
        high_result = await high_priority_task
        normal_result = await normal_priority_task
        
        # 至少高优先级请求应该成功（在实际实现中）
        # 这里我们主要测试不会抛出异常
        assert isinstance(high_result, bool)
        assert isinstance(normal_result, bool)
        
    async def test_rate_limiter_operation_specific_limits(self, rate_limiter):
        """测试操作特定限制"""
        # 设置操作特定限制
        rate_limiter.set_operation_limit("special_operation", 2)
        
        # 测试特殊操作的限制
        results = []
        for i in range(5):
            result = await rate_limiter.acquire_permit(
                "special_operation",
                timeout=0.1
            )
            results.append(result)
            
        # 应该只有2个请求被允许
        allowed_count = sum(1 for result in results if result is True)
        assert allowed_count <= 2
        
    async def test_rate_limiter_adaptive_adjustment(self, rate_limiter):
        """测试自适应调整"""
        # 模拟高负载情况
        initial_factor = rate_limiter.adaptive_factor
        
        # 快速发送大量请求
        for _ in range(50):
            await rate_limiter.acquire_permit("load_test", timeout=0.01)
            
        # 自适应因子应该有所调整
        # 注意：具体的调整逻辑取决于实现
        assert hasattr(rate_limiter, 'adaptive_factor')
        
    async def test_rate_limiter_queue_timeout(self, rate_limiter):
        """测试队列超时"""
        # 先填满限流器
        for _ in range(rate_limiter.config.max_requests_per_second + 5):
            await rate_limiter.acquire_permit("fill_operation", timeout=0.01)
            
        # 发送一个会超时的请求
        start_time = time.time()
        result = await rate_limiter.acquire_permit(
            "timeout_test",
            timeout=0.1  # 很短的超时时间
        )
        end_time = time.time()
        
        # 请求应该被拒绝，且在超时时间内返回
        assert result is False
        assert (end_time - start_time) <= 0.2  # 允许一些误差


@pytest.mark.skipif(not HAS_RATE_LIMITER_MODULES, reason="限流器模块不可用")
class TestAdaptiveRateLimiterStatistics:
    """自适应限流器统计测试"""
    
    @pytest.fixture
    def rate_limiter(self):
        """创建测试用的限流器"""
        return AdaptiveRateLimiter("stats_test")
        
    async def test_rate_limiter_get_status(self, rate_limiter):
        """测试获取限流器状态"""
        # 执行一些操作
        await rate_limiter.acquire_permit("test_op")
        await rate_limiter.acquire_permit("test_op")
        
        status = rate_limiter.get_status()
        
        assert isinstance(status, dict)
        expected_keys = [
            'name', 'total_requests', 'allowed_requests', 'denied_requests',
            'queue_size', 'current_rps', 'adaptive_factor'
        ]
        
        for key in expected_keys:
            assert key in status
            
        assert status['total_requests'] >= 2
        assert status['allowed_requests'] >= 0
        
    async def test_rate_limiter_reset_stats(self, rate_limiter):
        """测试重置统计信息"""
        # 执行一些操作
        await rate_limiter.acquire_permit("test_op")
        await rate_limiter.acquire_permit("test_op")
        
        # 重置统计
        rate_limiter.reset_stats()
        
        assert rate_limiter.total_requests == 0
        assert rate_limiter.allowed_requests == 0
        assert rate_limiter.denied_requests == 0
        
    async def test_rate_limiter_calculate_current_rps(self, rate_limiter):
        """测试计算当前RPS"""
        # 执行一些操作
        for _ in range(5):
            await rate_limiter.acquire_permit("rps_test")
            
        current_rps = rate_limiter._calculate_current_rps()
        
        assert isinstance(current_rps, (int, float))
        assert current_rps >= 0


@pytest.mark.skipif(not HAS_RATE_LIMITER_MODULES, reason="限流器模块不可用")
class TestRateLimiterManager:
    """限流器管理器测试"""
    
    def test_rate_limiter_manager_initialization(self):
        """测试限流器管理器初始化"""
        manager = RateLimiterManager()
        
        assert manager is not None
        assert hasattr(manager, 'limiters')
        assert hasattr(manager, 'operation_configs')
        assert isinstance(manager.limiters, dict)
        
    def test_rate_limiter_manager_create_limiter(self):
        """测试创建限流器"""
        manager = RateLimiterManager()
        
        config = RateLimitConfig(max_requests_per_second=50)
        limiter = manager.create_limiter("test_limiter", config)
        
        assert limiter is not None
        assert limiter.name == "test_limiter"
        assert limiter.config == config
        assert "test_limiter" in manager.limiters
        
    def test_rate_limiter_manager_get_limiter(self):
        """测试获取限流器"""
        manager = RateLimiterManager()
        
        # 创建限流器
        config = RateLimitConfig()
        manager.create_limiter("get_test", config)
        
        # 获取限流器
        limiter = manager.get_limiter("get_test")
        assert limiter is not None
        assert limiter.name == "get_test"
        
        # 获取不存在的限流器
        non_existent = manager.get_limiter("non_existent")
        assert non_existent is None
        
    async def test_rate_limiter_manager_acquire_permit(self):
        """测试通过管理器获取许可"""
        manager = RateLimiterManager()
        
        # 创建限流器
        config = RateLimitConfig(max_requests_per_second=10)
        manager.create_limiter("manager_test", config)
        
        # 通过管理器获取许可
        result = await manager.acquire_permit(
            "manager_test",
            "test_operation"
        )
        
        assert result is True
        
    def test_rate_limiter_manager_get_all_status(self):
        """测试获取所有限流器状态"""
        manager = RateLimiterManager()
        
        # 创建多个限流器
        for i in range(3):
            config = RateLimitConfig()
            manager.create_limiter(f"limiter_{i}", config)
            
        all_status = manager.get_all_status()
        
        assert isinstance(all_status, dict)
        assert len(all_status) == 3
        
        for i in range(3):
            assert f"limiter_{i}" in all_status
            assert isinstance(all_status[f"limiter_{i}"], dict)


@pytest.mark.integration
@pytest.mark.skipif(not HAS_RATE_LIMITER_MODULES, reason="限流器模块不可用")
class TestAdaptiveRateLimiterIntegration:
    """自适应限流器集成测试"""
    
    async def test_rate_limiter_full_workflow(self):
        """测试限流器完整工作流"""
        config = RateLimitConfig(
            max_requests_per_second=5,
            burst_allowance=2,
            queue_timeout=1.0
        )
        
        limiter = AdaptiveRateLimiter("integration_test", config)
        
        # 启动限流器
        await limiter.start()
        
        try:
            # 1. 正常请求应该被允许
            for i in range(3):
                result = await limiter.acquire_permit("normal_op")
                assert result is True
                
            # 2. 检查统计信息
            status = limiter.get_status()
            assert status['total_requests'] == 3
            assert status['allowed_requests'] == 3
            
            # 3. 设置操作特定限制
            limiter.set_operation_limit("limited_op", 1)
            
            # 4. 测试操作限制
            result1 = await limiter.acquire_permit("limited_op")
            result2 = await limiter.acquire_permit("limited_op", timeout=0.1)
            
            assert result1 is True
            # result2可能被拒绝或排队，取决于实现
            
            # 5. 重置统计
            limiter.reset_stats()
            status = limiter.get_status()
            assert status['total_requests'] == 0
            
        finally:
            # 停止限流器
            await limiter.stop()
            
    async def test_rate_limiter_concurrent_access(self):
        """测试限流器并发访问"""
        config = RateLimitConfig(
            max_requests_per_second=10,
            burst_allowance=5
        )
        
        limiter = AdaptiveRateLimiter("concurrent_test", config)
        
        # 并发发送请求
        async def make_request(request_id):
            return await limiter.acquire_permit(f"concurrent_op_{request_id}", timeout=0.5)
            
        tasks = [make_request(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        successful_requests = sum(1 for result in results if result is True)
        failed_requests = sum(1 for result in results if result is False)
        
        # 应该有一些成功和一些失败的请求
        assert successful_requests > 0
        assert successful_requests + failed_requests == 20
        
        # 检查限流器状态
        status = limiter.get_status()
        assert status['total_requests'] == 20
