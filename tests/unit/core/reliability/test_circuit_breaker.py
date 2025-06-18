"""
熔断器测试
测试MarketPrismCircuitBreaker的核心功能
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Optional

# 导入被测试的模块
try:
    from core.reliability.circuit_breaker import (
        MarketPrismCircuitBreaker,
        CircuitBreakerConfig,
        CircuitState,
        OperationResult,
        CircuitBreakerOpenException,
        circuit_breaker
    )
    HAS_CIRCUIT_BREAKER_MODULES = True
except ImportError as e:
    HAS_CIRCUIT_BREAKER_MODULES = False
    pytest.skip(f"熔断器模块导入失败: {e}", allow_module_level=True)


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerConfig:
    """熔断器配置测试"""
    
    def test_circuit_breaker_config_default_values(self):
        """测试熔断器配置默认值"""
        config = CircuitBreakerConfig()
        
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60.0
        assert config.timeout_duration == 30.0
        assert config.failure_rate_threshold == 0.5
        assert config.minimum_requests == 10
        assert config.half_open_limit == 3
        assert config.enable_cache is True
        assert config.cache_ttl == 300.0
        
    def test_circuit_breaker_config_custom_values(self):
        """测试熔断器配置自定义值"""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            recovery_timeout=120.0,
            timeout_duration=60.0,
            failure_rate_threshold=0.7,
            minimum_requests=20,
            half_open_limit=5,
            enable_cache=False,
            cache_ttl=600.0
        )
        
        assert config.failure_threshold == 10
        assert config.recovery_timeout == 120.0
        assert config.timeout_duration == 60.0
        assert config.failure_rate_threshold == 0.7
        assert config.minimum_requests == 20
        assert config.half_open_limit == 5
        assert config.enable_cache is False
        assert config.cache_ttl == 600.0


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerInitialization:
    """熔断器初始化测试"""
    
    def test_circuit_breaker_initialization_default(self):
        """测试使用默认配置初始化熔断器"""
        breaker = MarketPrismCircuitBreaker("test_breaker")
        
        assert breaker.name == "test_breaker"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.total_requests == 0
        assert breaker.total_fallbacks == 0
        assert isinstance(breaker.config, CircuitBreakerConfig)
        
    def test_circuit_breaker_initialization_with_config(self):
        """测试使用自定义配置初始化熔断器"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30.0
        )
        
        breaker = MarketPrismCircuitBreaker("custom_breaker", config)
        
        assert breaker.name == "custom_breaker"
        assert breaker.config == config
        assert breaker.config.failure_threshold == 3
        assert breaker.config.recovery_timeout == 30.0
        
    def test_circuit_breaker_has_required_attributes(self):
        """测试熔断器具有必需的属性"""
        breaker = MarketPrismCircuitBreaker("test_breaker")
        
        required_attributes = [
            'name', 'config', 'state', 'failure_count', 'success_count',
            'total_requests', 'total_fallbacks', 'last_failure_time',
            'last_state_change', 'operation_history', 'cache'
        ]
        
        for attr in required_attributes:
            assert hasattr(breaker, attr), f"缺少必需属性: {attr}"


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerBasicOperations:
    """熔断器基本操作测试"""
    
    @pytest.fixture
    def circuit_breaker(self):
        """创建测试用的熔断器"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=1.0,  # 短恢复时间用于测试
            timeout_duration=0.5
        )
        return MarketPrismCircuitBreaker("test_breaker", config)
        
    async def test_circuit_breaker_successful_operation(self, circuit_breaker):
        """测试成功操作"""
        async def successful_operation():
            return "success"
            
        result = await circuit_breaker.execute_with_breaker(successful_operation)
        
        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
        assert circuit_breaker.success_count == 1
        assert circuit_breaker.total_requests == 1
        
    async def test_circuit_breaker_failed_operation(self, circuit_breaker):
        """测试失败操作"""
        async def failing_operation():
            raise ValueError("Operation failed")
            
        with pytest.raises(ValueError):
            await circuit_breaker.execute_with_breaker(failing_operation)
            
        assert circuit_breaker.state == CircuitState.CLOSED  # 还未达到阈值
        assert circuit_breaker.failure_count == 1
        assert circuit_breaker.success_count == 0
        assert circuit_breaker.total_requests == 1
        
    async def test_circuit_breaker_trip_on_threshold(self, circuit_breaker):
        """测试达到失败阈值时熔断器跳闸"""
        async def failing_operation():
            raise ValueError("Operation failed")
            
        # 执行失败操作直到达到阈值
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
                
        # 熔断器应该跳闸
        assert circuit_breaker.state == CircuitState.OPEN
        assert circuit_breaker.failure_count == circuit_breaker.config.failure_threshold
        
    async def test_circuit_breaker_open_state_behavior(self, circuit_breaker):
        """测试熔断器开放状态行为"""
        # 先让熔断器跳闸
        async def failing_operation():
            raise ValueError("Operation failed")
            
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
                
        assert circuit_breaker.state == CircuitState.OPEN
        
        # 在开放状态下，操作应该立即失败
        async def any_operation():
            return "should not execute"
            
        with pytest.raises(CircuitBreakerOpenException):
            await circuit_breaker.execute_with_breaker(any_operation)
            
        assert circuit_breaker.total_fallbacks == 1
        
    async def test_circuit_breaker_half_open_transition(self, circuit_breaker):
        """测试熔断器半开状态转换"""
        # 先让熔断器跳闸
        async def failing_operation():
            raise ValueError("Operation failed")
            
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
                
        assert circuit_breaker.state == CircuitState.OPEN
        
        # 等待恢复超时
        await asyncio.sleep(circuit_breaker.config.recovery_timeout + 0.1)
        
        # 下一次操作应该转换到半开状态
        async def test_operation():
            return "test"
            
        result = await circuit_breaker.execute_with_breaker(test_operation)
        
        assert result == "test"
        assert circuit_breaker.state == CircuitState.HALF_OPEN
        
    async def test_circuit_breaker_half_open_success_recovery(self, circuit_breaker):
        """测试半开状态成功恢复"""
        # 先让熔断器跳闸并转换到半开状态
        await self._trip_and_transition_to_half_open(circuit_breaker)
        
        # 在半开状态下执行成功操作
        async def successful_operation():
            return "success"
            
        # 执行足够的成功操作以恢复
        for _ in range(circuit_breaker.config.half_open_limit):
            result = await circuit_breaker.execute_with_breaker(successful_operation)
            assert result == "success"
            
        # 熔断器应该恢复到关闭状态
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
        
    async def test_circuit_breaker_half_open_failure_reopen(self, circuit_breaker):
        """测试半开状态失败重新开放"""
        # 先让熔断器跳闸并转换到半开状态
        await self._trip_and_transition_to_half_open(circuit_breaker)
        
        # 在半开状态下执行失败操作
        async def failing_operation():
            raise ValueError("Still failing")
            
        with pytest.raises(ValueError):
            await circuit_breaker.execute_with_breaker(failing_operation)
            
        # 熔断器应该重新开放
        assert circuit_breaker.state == CircuitState.OPEN
        
    async def _trip_and_transition_to_half_open(self, circuit_breaker):
        """辅助方法：让熔断器跳闸并转换到半开状态"""
        async def failing_operation():
            raise ValueError("Operation failed")
            
        # 让熔断器跳闸
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
                
        # 等待恢复超时
        await asyncio.sleep(circuit_breaker.config.recovery_timeout + 0.1)
        
        # 执行一次操作转换到半开状态
        async def test_operation():
            return "test"
            
        await circuit_breaker.execute_with_breaker(test_operation)
        assert circuit_breaker.state == CircuitState.HALF_OPEN


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerFallback:
    """熔断器回退机制测试"""
    
    @pytest.fixture
    def circuit_breaker(self):
        """创建测试用的熔断器"""
        config = CircuitBreakerConfig(failure_threshold=2)
        return MarketPrismCircuitBreaker("fallback_test", config)
        
    async def test_circuit_breaker_fallback_on_failure(self, circuit_breaker):
        """测试失败时的回退机制"""
        async def failing_operation():
            raise ValueError("Operation failed")
            
        async def fallback_operation():
            return "fallback_result"
            
        result = await circuit_breaker.execute_with_breaker(
            failing_operation,
            fallback=fallback_operation
        )
        
        assert result == "fallback_result"
        assert circuit_breaker.failure_count == 1
        
    async def test_circuit_breaker_fallback_on_open_state(self, circuit_breaker):
        """测试开放状态时的回退机制"""
        # 先让熔断器跳闸
        async def failing_operation():
            raise ValueError("Operation failed")
            
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
                
        assert circuit_breaker.state == CircuitState.OPEN
        
        # 在开放状态下使用回退
        async def any_operation():
            return "should not execute"
            
        async def fallback_operation():
            return "fallback_in_open_state"
            
        result = await circuit_breaker.execute_with_breaker(
            any_operation,
            fallback=fallback_operation
        )
        
        assert result == "fallback_in_open_state"
        assert circuit_breaker.total_fallbacks == 1
        
    async def test_circuit_breaker_no_fallback_raises_exception(self, circuit_breaker):
        """测试无回退时抛出异常"""
        # 让熔断器跳闸
        async def failing_operation():
            raise ValueError("Operation failed")
            
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
                
        # 在开放状态下无回退应该抛出异常
        async def any_operation():
            return "should not execute"
            
        with pytest.raises(CircuitBreakerOpenException):
            await circuit_breaker.execute_with_breaker(any_operation)


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerCache:
    """熔断器缓存测试"""
    
    @pytest.fixture
    def circuit_breaker_with_cache(self):
        """创建启用缓存的熔断器"""
        config = CircuitBreakerConfig(
            enable_cache=True,
            cache_ttl=1.0  # 短TTL用于测试
        )
        return MarketPrismCircuitBreaker("cache_test", config)
        
    async def test_circuit_breaker_cache_hit(self, circuit_breaker_with_cache):
        """测试缓存命中"""
        call_count = 0
        
        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"
            
        cache_key = "test_key"
        
        # 第一次调用
        result1 = await circuit_breaker_with_cache.execute_with_breaker(
            expensive_operation,
            cache_key=cache_key
        )
        
        # 第二次调用应该使用缓存
        result2 = await circuit_breaker_with_cache.execute_with_breaker(
            expensive_operation,
            cache_key=cache_key
        )
        
        assert result1 == result2
        assert call_count == 1  # 只调用一次
        
    async def test_circuit_breaker_cache_expiry(self, circuit_breaker_with_cache):
        """测试缓存过期"""
        call_count = 0
        
        async def expensive_operation():
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"
            
        cache_key = "expiry_test"
        
        # 第一次调用
        result1 = await circuit_breaker_with_cache.execute_with_breaker(
            expensive_operation,
            cache_key=cache_key
        )
        
        # 等待缓存过期
        await asyncio.sleep(circuit_breaker_with_cache.config.cache_ttl + 0.1)
        
        # 第二次调用应该重新执行
        result2 = await circuit_breaker_with_cache.execute_with_breaker(
            expensive_operation,
            cache_key=cache_key
        )
        
        assert result1 != result2
        assert call_count == 2  # 调用两次


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerUtilityMethods:
    """熔断器工具方法测试"""
    
    @pytest.fixture
    def circuit_breaker(self):
        """创建测试用的熔断器"""
        return MarketPrismCircuitBreaker("utility_test")
        
    def test_circuit_breaker_get_state(self, circuit_breaker):
        """测试获取熔断器状态"""
        assert circuit_breaker.get_state() == CircuitState.CLOSED
        
    def test_circuit_breaker_get_failure_count(self, circuit_breaker):
        """测试获取失败计数"""
        assert circuit_breaker.get_failure_count() == 0
        
    def test_circuit_breaker_get_success_count(self, circuit_breaker):
        """测试获取成功计数"""
        assert circuit_breaker.get_success_count() == 0
        
    def test_circuit_breaker_reset(self, circuit_breaker):
        """测试重置熔断器"""
        # 修改一些状态
        circuit_breaker.failure_count = 5
        circuit_breaker.success_count = 3
        circuit_breaker.state = CircuitState.OPEN
        
        # 重置
        circuit_breaker.reset()
        
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
        assert circuit_breaker.success_count == 0
        
    def test_circuit_breaker_get_stats(self, circuit_breaker):
        """测试获取统计信息"""
        stats = circuit_breaker.get_stats()
        
        assert isinstance(stats, dict)
        expected_keys = [
            'state', 'failure_count', 'success_count', 'total_requests',
            'total_fallbacks', 'failure_rate', 'uptime_seconds'
        ]
        
        for key in expected_keys:
            assert key in stats


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerDecorator:
    """熔断器装饰器测试"""
    
    async def test_circuit_breaker_decorator_basic(self):
        """测试基本熔断器装饰器"""
        config = CircuitBreakerConfig(failure_threshold=2)
        
        @circuit_breaker("decorator_test", config)
        async def test_function():
            return "decorated_result"
            
        result = await test_function()
        assert result == "decorated_result"
        
    async def test_circuit_breaker_decorator_with_failure(self):
        """测试装饰器处理失败"""
        config = CircuitBreakerConfig(failure_threshold=1)
        
        @circuit_breaker("decorator_fail_test", config)
        async def failing_function():
            raise ValueError("Decorated function failed")
            
        # 第一次失败
        with pytest.raises(ValueError):
            await failing_function()
            
        # 第二次应该触发熔断器
        with pytest.raises(CircuitBreakerOpenException):
            await failing_function()


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER_MODULES, reason="熔断器模块不可用")
class TestCircuitBreakerIntegration:
    """熔断器集成测试"""
    
    async def test_circuit_breaker_full_lifecycle(self):
        """测试熔断器完整生命周期"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.5,
            half_open_limit=2
        )
        
        breaker = MarketPrismCircuitBreaker("lifecycle_test", config)
        
        # 1. 初始状态：关闭
        assert breaker.state == CircuitState.CLOSED
        
        # 2. 成功操作
        async def successful_op():
            return "success"
            
        result = await breaker.execute_with_breaker(successful_op)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        
        # 3. 失败操作导致跳闸
        async def failing_op():
            raise ValueError("Failed")
            
        for _ in range(config.failure_threshold):
            with pytest.raises(ValueError):
                await breaker.execute_with_breaker(failing_op)
                
        assert breaker.state == CircuitState.OPEN
        
        # 4. 开放状态拒绝请求
        with pytest.raises(CircuitBreakerOpenException):
            await breaker.execute_with_breaker(successful_op)
            
        # 5. 等待恢复并转换到半开状态
        await asyncio.sleep(config.recovery_timeout + 0.1)
        
        result = await breaker.execute_with_breaker(successful_op)
        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN
        
        # 6. 半开状态成功恢复
        for _ in range(config.half_open_limit - 1):
            await breaker.execute_with_breaker(successful_op)
            
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
