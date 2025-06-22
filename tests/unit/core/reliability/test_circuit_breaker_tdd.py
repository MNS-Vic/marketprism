"""
熔断器TDD测试
专注于提升覆盖率和测试未覆盖的功能
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

try:
    from core.reliability.circuit_breaker import (
        MarketPrismCircuitBreaker, CircuitBreakerConfig, CircuitState,
        CircuitBreakerOpenException, OperationResult, circuit_breaker
    )
    HAS_CIRCUIT_BREAKER = True
except ImportError:
    HAS_CIRCUIT_BREAKER = False


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="熔断器模块不可用")
class TestCircuitBreakerStateTransitions:
    """测试熔断器状态转换"""
    
    @pytest.fixture
    def breaker_config(self):
        """创建测试用的熔断器配置"""
        return CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=1.0,
            half_open_limit=2,
            success_threshold=2,
            failure_rate_threshold=0.6,
            minimum_requests=5,
            window_size=30
        )
    
    @pytest.fixture
    def circuit_breaker(self, breaker_config):
        """创建测试用的熔断器"""
        return MarketPrismCircuitBreaker("test_breaker", breaker_config)
    
    @pytest.mark.asyncio
    async def test_closed_to_open_transition_by_failure_count(self, circuit_breaker):
        """测试：通过失败次数触发CLOSED到OPEN状态转换"""
        assert circuit_breaker.get_state() == CircuitState.CLOSED
        
        async def failing_operation():
            raise ValueError("Operation failed")
        
        # 执行失败操作直到达到阈值
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
            
            if i < circuit_breaker.config.failure_threshold - 1:
                assert circuit_breaker.get_state() == CircuitState.CLOSED
            else:
                assert circuit_breaker.get_state() == CircuitState.OPEN
        
        assert circuit_breaker.get_failure_count() == circuit_breaker.config.failure_threshold
    
    @pytest.mark.asyncio
    async def test_closed_to_open_transition_by_failure_rate(self, circuit_breaker):
        """测试：通过失败率触发CLOSED到OPEN状态转换"""
        assert circuit_breaker.get_state() == CircuitState.CLOSED

        async def success_operation():
            return "success"

        async def failing_operation():
            raise ValueError("Operation failed")

        async def fallback_operation():
            return "fallback"

        # 先执行一些成功操作
        for _ in range(2):
            await circuit_breaker.execute_with_breaker(success_operation)

        # 然后执行失败操作，使失败率超过阈值
        for _ in range(4):  # 4失败 + 2成功 = 6总数，失败率 = 4/6 = 66.7% > 60%
            result = await circuit_breaker.execute_with_breaker(failing_operation, fallback=fallback_operation)
            assert result == "fallback"

        # 应该触发熔断
        assert circuit_breaker.get_state() == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_open_to_half_open_transition_after_timeout(self, circuit_breaker):
        """测试：超时后OPEN到HALF_OPEN状态转换"""
        # 先触发熔断
        async def failing_operation():
            raise ValueError("Operation failed")
        
        for _ in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(ValueError):
                await circuit_breaker.execute_with_breaker(failing_operation)
        
        assert circuit_breaker.get_state() == CircuitState.OPEN
        
        # 等待恢复超时
        await asyncio.sleep(circuit_breaker.config.recovery_timeout + 0.1)
        
        # 下一次操作应该转换到半开状态
        async def test_operation():
            return "test"
        
        result = await circuit_breaker.execute_with_breaker(test_operation)
        assert result == "test"
        assert circuit_breaker.get_state() == CircuitState.HALF_OPEN
    
    @pytest.mark.asyncio
    async def test_half_open_to_closed_transition_on_success(self, circuit_breaker):
        """测试：成功操作后HALF_OPEN到CLOSED状态转换"""
        # 先进入半开状态
        circuit_breaker.state = CircuitState.HALF_OPEN
        circuit_breaker.success_count = 0
        
        async def success_operation():
            return "success"
        
        # 执行成功操作直到达到成功阈值
        for i in range(circuit_breaker.config.success_threshold):
            result = await circuit_breaker.execute_with_breaker(success_operation)
            assert result == "success"
            
            if i < circuit_breaker.config.success_threshold - 1:
                assert circuit_breaker.get_state() == CircuitState.HALF_OPEN
            else:
                assert circuit_breaker.get_state() == CircuitState.CLOSED
        
        assert circuit_breaker.get_success_count() == 0  # 转换到CLOSED后重置
        assert circuit_breaker.get_failure_count() == 0
    
    @pytest.mark.asyncio
    async def test_half_open_to_open_transition_on_failure(self, circuit_breaker):
        """测试：失败操作后HALF_OPEN到OPEN状态转换"""
        # 先进入半开状态
        circuit_breaker.state = CircuitState.HALF_OPEN
        circuit_breaker.success_count = 0
        circuit_breaker.failure_count = 0  # 重置失败计数

        async def failing_operation():
            raise ValueError("Operation failed")

        async def fallback_operation():
            return "fallback"

        # 执行足够的失败操作以触发熔断
        for _ in range(circuit_breaker.config.failure_threshold):
            result = await circuit_breaker.execute_with_breaker(failing_operation, fallback=fallback_operation)
            assert result == "fallback"

        # 应该转换到OPEN状态
        assert circuit_breaker.get_state() == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_half_open_request_limit(self, circuit_breaker):
        """测试：半开状态请求限制"""
        # 进入半开状态
        circuit_breaker.state = CircuitState.HALF_OPEN
        circuit_breaker.success_count = circuit_breaker.config.half_open_limit

        async def test_operation():
            return "test"

        async def fallback_operation():
            return {"status": "circuit_breaker_open", "fallback": True}

        # 超过半开限制的请求应该被拒绝
        result = await circuit_breaker.execute_with_breaker(test_operation, fallback=fallback_operation)

        # 应该返回降级响应而不是执行操作
        assert isinstance(result, dict)
        assert result["status"] == "circuit_breaker_open"
    
    def test_should_trip_failure_threshold(self, circuit_breaker):
        """测试：失败阈值判断逻辑"""
        # 设置失败计数
        circuit_breaker.failure_count = circuit_breaker.config.failure_threshold - 1
        assert not circuit_breaker._should_trip()
        
        circuit_breaker.failure_count = circuit_breaker.config.failure_threshold
        assert circuit_breaker._should_trip()
    
    def test_should_attempt_reset_timing(self, circuit_breaker):
        """测试：重置尝试时机判断"""
        # 非OPEN状态不应该尝试重置
        circuit_breaker.state = CircuitState.CLOSED
        assert not circuit_breaker._should_attempt_reset()
        
        circuit_breaker.state = CircuitState.HALF_OPEN
        assert not circuit_breaker._should_attempt_reset()
        
        # OPEN状态但未到超时时间
        circuit_breaker.state = CircuitState.OPEN
        circuit_breaker.last_state_change = time.time()
        assert not circuit_breaker._should_attempt_reset()
        
        # OPEN状态且已超时
        circuit_breaker.last_state_change = time.time() - circuit_breaker.config.recovery_timeout - 1
        assert circuit_breaker._should_attempt_reset()


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="熔断器模块不可用")
class TestCircuitBreakerFallbackMechanisms:
    """测试熔断器降级机制"""
    
    @pytest.fixture
    def circuit_breaker(self):
        """创建测试用的熔断器"""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=1.0)
        return MarketPrismCircuitBreaker("fallback_test", config)
    
    @pytest.mark.asyncio
    async def test_async_fallback_execution(self, circuit_breaker):
        """测试：异步降级函数执行"""
        async def failing_operation():
            raise ValueError("Operation failed")
        
        async def async_fallback():
            return "async_fallback_result"
        
        result = await circuit_breaker.execute_with_breaker(
            failing_operation, 
            fallback=async_fallback
        )
        
        assert result == "async_fallback_result"
    
    @pytest.mark.asyncio
    async def test_sync_fallback_execution(self, circuit_breaker):
        """测试：同步降级函数执行"""
        async def failing_operation():
            raise ValueError("Operation failed")
        
        def sync_fallback():
            return "sync_fallback_result"
        
        result = await circuit_breaker.execute_with_breaker(
            failing_operation, 
            fallback=sync_fallback
        )
        
        assert result == "sync_fallback_result"
    
    @pytest.mark.asyncio
    async def test_fallback_function_failure(self, circuit_breaker):
        """测试：降级函数执行失败"""
        async def failing_operation():
            raise ValueError("Operation failed")
        
        async def failing_fallback():
            raise RuntimeError("Fallback failed")
        
        result = await circuit_breaker.execute_with_breaker(
            failing_operation, 
            fallback=failing_fallback
        )
        
        # 应该返回默认响应
        assert isinstance(result, dict)
        assert result["status"] == "circuit_breaker_open"
    
    @pytest.mark.asyncio
    async def test_cache_fallback_mechanism(self, circuit_breaker):
        """测试：缓存降级机制"""
        cache_key = "test_cache_key"
        
        # 先执行成功操作建立缓存
        async def success_operation():
            return "cached_result"
        
        result = await circuit_breaker.execute_with_breaker(
            success_operation, 
            cache_key=cache_key
        )
        assert result == "cached_result"
        
        # 然后执行失败操作，应该返回缓存结果
        async def failing_operation():
            raise ValueError("Operation failed")
        
        result = await circuit_breaker.execute_with_breaker(
            failing_operation, 
            cache_key=cache_key
        )
        assert result == "cached_result"
    
    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, circuit_breaker):
        """测试：缓存TTL过期"""
        cache_key = "test_cache_key"

        # 建立缓存
        async def success_operation():
            return "cached_result"

        await circuit_breaker.execute_with_breaker(success_operation, cache_key=cache_key)

        # 手动过期缓存
        circuit_breaker.cache_ttl[cache_key] = time.time() - 1

        # 失败操作不应该返回过期缓存
        async def failing_operation():
            raise ValueError("Operation failed")

        async def fallback_operation():
            return {"status": "circuit_breaker_open", "fallback": True}

        result = await circuit_breaker.execute_with_breaker(
            failing_operation,
            fallback=fallback_operation,
            cache_key=cache_key
        )

        # 应该返回降级响应而不是过期缓存
        assert isinstance(result, dict)
        assert result["status"] == "circuit_breaker_open"
    
    @pytest.mark.asyncio
    async def test_no_fallback_re_raise_exception(self, circuit_breaker):
        """测试：无降级策略时重新抛出异常"""
        async def failing_operation():
            raise ValueError("Original error")
        
        with pytest.raises(ValueError, match="Original error"):
            await circuit_breaker.execute_with_breaker(failing_operation)
    
    @pytest.mark.asyncio
    async def test_open_state_fallback_execution(self, circuit_breaker):
        """测试：OPEN状态下的降级执行"""
        # 先触发熔断
        circuit_breaker.state = CircuitState.OPEN
        
        async def any_operation():
            return "should_not_execute"
        
        async def fallback_operation():
            return "fallback_executed"
        
        result = await circuit_breaker.execute_with_breaker(
            any_operation, 
            fallback=fallback_operation
        )
        
        assert result == "fallback_executed"
        assert circuit_breaker.total_fallbacks > 0


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="熔断器模块不可用")
class TestCircuitBreakerCallbackMechanisms:
    """测试熔断器回调机制"""
    
    @pytest.fixture
    def circuit_breaker(self):
        """创建测试用的熔断器"""
        config = CircuitBreakerConfig(failure_threshold=2)
        return MarketPrismCircuitBreaker("callback_test", config)
    
    def test_state_change_listener(self, circuit_breaker):
        """测试：状态变更监听器"""
        state_changes = []
        
        def state_change_listener(old_state, new_state):
            state_changes.append((old_state, new_state))
        
        circuit_breaker.add_listener(state_change_listener)
        
        # 触发状态变更
        circuit_breaker._transition_to_open()
        circuit_breaker._transition_to_half_open()
        circuit_breaker._transition_to_closed()
        
        assert len(state_changes) == 3
        assert state_changes[0] == (CircuitState.CLOSED, CircuitState.OPEN)
        assert state_changes[1] == (CircuitState.OPEN, CircuitState.HALF_OPEN)
        assert state_changes[2] == (CircuitState.HALF_OPEN, CircuitState.CLOSED)
    
    def test_on_open_callback(self, circuit_breaker):
        """测试：开启回调"""
        open_called = []
        
        @circuit_breaker.on_open
        def on_open_callback():
            open_called.append(True)
        
        circuit_breaker._transition_to_open()
        
        assert len(open_called) == 1
    
    def test_on_close_callback(self, circuit_breaker):
        """测试：关闭回调"""
        close_called = []
        
        @circuit_breaker.on_close
        def on_close_callback():
            close_called.append(True)
        
        circuit_breaker._transition_to_closed()
        
        assert len(close_called) == 1
    
    def test_on_half_open_callback(self, circuit_breaker):
        """测试：半开回调"""
        half_open_called = []
        
        @circuit_breaker.on_half_open
        def on_half_open_callback():
            half_open_called.append(True)
        
        circuit_breaker._transition_to_half_open()
        
        assert len(half_open_called) == 1
    
    def test_callback_exception_handling(self, circuit_breaker):
        """测试：回调异常处理"""
        def failing_callback(old_state, new_state):
            raise RuntimeError("Callback failed")

        circuit_breaker.add_listener(failing_callback)

        # 回调失败不应该影响状态转换
        circuit_breaker._transition_to_open()
        assert circuit_breaker.get_state() == CircuitState.OPEN


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="熔断器模块不可用")
class TestCircuitBreakerAdvancedFeatures:
    """测试熔断器高级功能"""

    @pytest.fixture
    def circuit_breaker(self):
        """创建测试用的熔断器"""
        return MarketPrismCircuitBreaker("advanced_test")

    @pytest.mark.asyncio
    async def test_call_method_alias(self, circuit_breaker):
        """测试：call方法别名"""
        async def test_operation():
            return "call_result"

        result = await circuit_breaker.call(test_operation)
        assert result == "call_result"

    @pytest.mark.asyncio
    async def test_decorator_pattern_async(self, circuit_breaker):
        """测试：装饰器模式（异步函数）"""
        @circuit_breaker
        async def decorated_async_func():
            return "decorated_async_result"

        result = await decorated_async_func()
        assert result == "decorated_async_result"

    def test_decorator_pattern_sync(self, circuit_breaker):
        """测试：装饰器模式（同步函数）"""
        @circuit_breaker
        def decorated_sync_func():
            return "decorated_sync_result"

        result = decorated_sync_func()
        assert result == "decorated_sync_result"

    @pytest.mark.asyncio
    async def test_context_manager_success(self, circuit_breaker):
        """测试：上下文管理器成功场景"""
        async with circuit_breaker as cb:
            assert cb is circuit_breaker
            # 正常执行，无异常

    @pytest.mark.asyncio
    async def test_context_manager_exception(self, circuit_breaker):
        """测试：上下文管理器异常场景"""
        initial_failure_count = circuit_breaker.get_failure_count()

        with pytest.raises(ValueError):
            async with circuit_breaker:
                raise ValueError("Context exception")

        # 异常应该被记录到熔断器统计中
        assert circuit_breaker.get_failure_count() > initial_failure_count

    def test_get_status_comprehensive(self, circuit_breaker):
        """测试：获取完整状态信息"""
        # 设置一些统计数据
        circuit_breaker.total_requests = 10
        circuit_breaker.total_failures = 3
        circuit_breaker.total_fallbacks = 2
        circuit_breaker.failure_count = 1

        status = circuit_breaker.get_status()

        assert status["name"] == "advanced_test"
        assert status["state"] == CircuitState.CLOSED.value
        assert status["failure_count"] == 1
        assert status["total_requests"] == 10
        assert status["total_failures"] == 3
        assert status["total_fallbacks"] == 2
        assert "config" in status
        assert "failure_rate" in status

    def test_get_stats_method(self, circuit_breaker):
        """测试：获取统计信息"""
        # 设置一些统计数据
        circuit_breaker.total_requests = 15
        circuit_breaker.total_failures = 5
        circuit_breaker.total_fallbacks = 3

        stats = circuit_breaker.get_stats()

        assert stats["total_requests"] == 15
        assert stats["total_failures"] == 5
        assert stats["total_fallbacks"] == 3
        assert "state" in stats
        assert "uptime_seconds" in stats
        assert "last_state_change" in stats

    def test_reset_functionality(self, circuit_breaker):
        """测试：重置功能"""
        # 设置一些状态
        circuit_breaker.state = CircuitState.OPEN
        circuit_breaker.failure_count = 5
        circuit_breaker.success_count = 2
        circuit_breaker.total_requests = 10
        circuit_breaker.operation_history.append(OperationResult(success=False))

        # 重置
        circuit_breaker.reset()

        # 验证重置结果
        assert circuit_breaker.get_state() == CircuitState.CLOSED
        assert circuit_breaker.get_failure_count() == 0
        assert circuit_breaker.get_success_count() == 0
        assert len(circuit_breaker.operation_history) == 0
        # total_requests等统计信息不应该被重置
        assert circuit_breaker.total_requests == 10

    def test_operation_history_management(self, circuit_breaker):
        """测试：操作历史管理"""
        # 添加操作记录
        for i in range(5):
            result = OperationResult(success=i % 2 == 0, response_time=0.1 * i)
            circuit_breaker.operation_history.append(result)

        # 获取最近操作
        recent_ops = circuit_breaker._get_recent_operations()
        assert len(recent_ops) == 5

        # 计算失败率
        failure_rate = circuit_breaker._calculate_failure_rate(recent_ops)
        assert 0.0 <= failure_rate <= 1.0

    def test_cache_management(self, circuit_breaker):
        """测试：缓存管理"""
        cache_key = "test_key"
        cache_value = "test_value"

        # 设置缓存
        circuit_breaker.cached_responses[cache_key] = cache_value
        circuit_breaker.cache_ttl[cache_key] = time.time() + 300

        # 验证缓存存在
        assert cache_key in circuit_breaker.cached_responses
        assert circuit_breaker.cached_responses[cache_key] == cache_value

        # 验证TTL
        assert circuit_breaker.cache_ttl[cache_key] > time.time()


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="熔断器模块不可用")
class TestCircuitBreakerDecorator:
    """测试熔断器装饰器"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator_function(self):
        """测试：熔断器装饰器函数"""
        config = CircuitBreakerConfig(failure_threshold=2)

        @circuit_breaker("decorator_test", config)
        async def decorated_function():
            return "decorated_result"

        result = await decorated_function()
        assert result == "decorated_result"

    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator_with_failure(self):
        """测试：熔断器装饰器失败处理"""
        config = CircuitBreakerConfig(failure_threshold=1)

        @circuit_breaker("decorator_fail_test", config)
        async def failing_function():
            raise ValueError("Decorated function failed")

        # 第一次调用应该失败并触发熔断
        with pytest.raises(ValueError):
            await failing_function()


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="熔断器模块不可用")
class TestCircuitBreakerEdgeCases:
    """测试熔断器边界情况"""

    @pytest.fixture
    def circuit_breaker(self):
        """创建测试用的熔断器"""
        return MarketPrismCircuitBreaker("edge_case_test")

    def test_default_config_values(self):
        """测试：默认配置值"""
        breaker = MarketPrismCircuitBreaker("default_test")

        assert breaker.config.failure_threshold == 5
        assert breaker.config.recovery_timeout == 30.0
        assert breaker.config.half_open_limit == 3
        assert breaker.config.success_threshold == 2
        assert breaker.config.failure_rate_threshold == 0.5
        assert breaker.config.minimum_requests == 10
        assert breaker.config.window_size == 60

    def test_custom_config_values(self):
        """测试：自定义配置值"""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            recovery_timeout=60.0,
            half_open_limit=5,
            success_threshold=3,
            failure_rate_threshold=0.7,
            minimum_requests=20,
            window_size=120
        )

        breaker = MarketPrismCircuitBreaker("custom_test", config)

        assert breaker.config.failure_threshold == 10
        assert breaker.config.recovery_timeout == 60.0
        assert breaker.config.half_open_limit == 5
        assert breaker.config.success_threshold == 3
        assert breaker.config.failure_rate_threshold == 0.7
        assert breaker.config.minimum_requests == 20
        assert breaker.config.window_size == 120

    @pytest.mark.asyncio
    async def test_zero_failure_threshold(self):
        """测试：零失败阈值"""
        config = CircuitBreakerConfig(failure_threshold=0)
        breaker = MarketPrismCircuitBreaker("zero_threshold", config)

        async def failing_operation():
            raise ValueError("Should trip immediately")

        # 任何失败都应该立即触发熔断
        with pytest.raises(ValueError):
            await breaker.execute_with_breaker(failing_operation)

        assert breaker.get_state() == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_very_short_recovery_timeout(self):
        """测试：极短恢复超时"""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01)
        breaker = MarketPrismCircuitBreaker("short_timeout", config)

        # 触发熔断
        async def failing_operation():
            raise ValueError("Trigger circuit breaker")

        with pytest.raises(ValueError):
            await breaker.execute_with_breaker(failing_operation)

        assert breaker.get_state() == CircuitState.OPEN

        # 等待极短时间后应该可以尝试恢复
        await asyncio.sleep(0.02)

        async def success_operation():
            return "recovery_success"

        result = await breaker.execute_with_breaker(success_operation)
        assert result == "recovery_success"
        assert breaker.get_state() == CircuitState.HALF_OPEN

    def test_operation_result_creation(self):
        """测试：操作结果创建"""
        # 成功结果
        success_result = OperationResult(success=True, response_time=0.5)
        assert success_result.success is True
        assert success_result.response_time == 0.5
        assert success_result.error is None
        assert success_result.timestamp > 0

        # 失败结果
        error = ValueError("Test error")
        failure_result = OperationResult(success=False, error=error, response_time=1.0)
        assert failure_result.success is False
        assert failure_result.error is error
        assert failure_result.response_time == 1.0

    def test_circuit_breaker_open_exception(self):
        """测试：熔断器开放异常"""
        exception = CircuitBreakerOpenException("Circuit breaker is open")
        assert str(exception) == "Circuit breaker is open"
        assert isinstance(exception, Exception)
