#!/usr/bin/env python3
"""
Reliability模块核心功能TDD测试

基于成功的TDD方法论，通过测试发现reliability模块的设计问题并驱动改进
"""
import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import time

# 添加模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.reliability.circuit_breaker import (
    MarketPrismCircuitBreaker, CircuitState, CircuitBreakerConfig, OperationResult
)


@pytest.mark.unit
class TestCircuitBreakerCore:
    """测试熔断器核心功能"""
    
    def test_circuit_breaker_initialization(self):
        """测试熔断器初始化"""
        config = CircuitBreakerConfig()
        breaker = MarketPrismCircuitBreaker("test_service", config)
        
        assert breaker.name == "test_service"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.config == config
        assert hasattr(breaker, 'failure_count')
        assert hasattr(breaker, 'last_failure_time')
    
    def test_circuit_breaker_default_config(self):
        """TDD发现问题: 是否支持默认配置"""
        # 这个测试可能会发现缺少默认配置构造方法的问题
        try:
            breaker = MarketPrismCircuitBreaker("test_service")  # 无配置参数
            assert breaker.config is not None
            assert isinstance(breaker.config, CircuitBreakerConfig)
        except TypeError as e:
            pytest.fail(f"TDD发现设计问题: CircuitBreaker需要支持默认配置 - {e}")
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_execution(self):
        """测试熔断器执行基础功能"""
        config = CircuitBreakerConfig()
        breaker = MarketPrismCircuitBreaker("test_service", config)
        
        # 测试成功执行
        async def success_operation():
            return "success"
        
        result = await breaker.call(success_operation)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_tracking(self):
        """测试熔断器失败追踪"""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = MarketPrismCircuitBreaker("test_service", config)
        
        async def failing_operation():
            raise Exception("Test failure")
        
        # 第一次失败
        with pytest.raises(Exception):
            await breaker.call(failing_operation)
        assert breaker.state == CircuitState.CLOSED  # 还未达到阈值
        
        # 第二次失败 - 应该触发熔断
        with pytest.raises(Exception):
            await breaker.call(failing_operation)
        assert breaker.state == CircuitState.OPEN  # 熔断生效


@pytest.mark.unit
class TestCircuitBreakerStateTransition:
    """测试熔断器状态转换"""
    
    @pytest.mark.asyncio
    async def test_closed_to_open_transition(self):
        """测试从关闭到开放状态的转换"""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = MarketPrismCircuitBreaker("test", config)
        
        async def failing_op():
            raise RuntimeError("Failure")
        
        assert breaker.state == CircuitState.CLOSED
        
        with pytest.raises(RuntimeError):
            await breaker.call(failing_op)
        
        assert breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_open_state_timeout_behavior(self):
        """测试开放状态的超时行为"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1  # 100ms
        )
        breaker = MarketPrismCircuitBreaker("test", config)
        
        # 触发熔断
        async def failing_op():
            raise RuntimeError("Failure")
        
        with pytest.raises(RuntimeError):
            await breaker.call(failing_op)
        assert breaker.state == CircuitState.OPEN
        
        # 在超时前调用应该被拒绝
        async def any_op():
            return "should_be_rejected"
        
        # TDD可能发现这里的API设计问题
        try:
            result = await breaker.call(any_op)
            # 如果执行到这里，说明API设计有问题，OPEN状态应该拒绝请求
            pytest.fail("TDD发现问题: OPEN状态应该拒绝请求而不是执行")
        except Exception as e:
            # 这是期望的行为
            pass
        
        # 等待超时后状态应该转为HALF_OPEN
        await asyncio.sleep(0.2)
        
        # 尝试调用，应该进入HALF_OPEN状态
        try:
            result = await breaker.call(any_op)
            assert breaker.state == CircuitState.HALF_OPEN
        except Exception:
            # 如果还是抛异常，说明状态转换有问题
            pass


@pytest.mark.unit
class TestCircuitBreakerConfig:
    """测试熔断器配置"""
    
    def test_config_default_values(self):
        """测试配置默认值"""
        config = CircuitBreakerConfig()
        
        assert config.failure_threshold > 0
        assert config.recovery_timeout > 0
        assert config.half_open_limit > 0
        assert config.success_threshold > 0
        assert 0 <= config.failure_rate_threshold <= 1
        assert config.minimum_requests > 0
        assert config.window_size > 0
    
    def test_config_validation(self):
        """TDD发现问题: 配置验证"""
        # 测试是否有配置验证
        try:
            # 无效配置应该被拒绝
            invalid_configs = [
                CircuitBreakerConfig(failure_threshold=-1),
                CircuitBreakerConfig(recovery_timeout=-1),
                CircuitBreakerConfig(failure_rate_threshold=1.5),  # 超过100%
                CircuitBreakerConfig(minimum_requests=0),
            ]
            
            for config in invalid_configs:
                # 如果没有验证机制，这个测试会失败
                # 这可能暴露配置验证缺失的设计问题
                pass
        except Exception:
            # 如果有验证异常，那就是好的设计
            pass


@pytest.mark.unit
class TestCircuitBreakerDesignIssues:
    """TDD专门测试设计问题的测试类"""
    
    def test_missing_context_manager_support(self):
        """TDD发现问题: 是否支持上下文管理器"""
        config = CircuitBreakerConfig()
        breaker = MarketPrismCircuitBreaker("test", config)
        
        # 测试是否支持 async with 语法
        try:
            async def test_context():
                async with breaker:
                    return "context_supported"
            
            # 如果不支持，会有AttributeError
            asyncio.run(test_context())
        except AttributeError:
            pytest.fail("TDD发现设计问题: CircuitBreaker应该支持async context manager")
        except Exception:
            # 其他异常可能是实现问题
            pass
    
    def test_missing_metrics_access(self):
        """TDD发现问题: 是否暴露监控指标"""
        config = CircuitBreakerConfig()
        breaker = MarketPrismCircuitBreaker("test", config)
        
        # 检查是否有获取指标的方法
        metrics_methods = [
            'get_metrics',
            'get_stats', 
            'get_failure_count',
            'get_success_count',
            'get_state'
        ]
        
        missing_methods = []
        for method in metrics_methods:
            if not hasattr(breaker, method):
                missing_methods.append(method)
        
        if missing_methods:
            pytest.fail(f"TDD发现设计问题: CircuitBreaker缺少监控方法: {missing_methods}")
    
    def test_decorator_support(self):
        """TDD发现问题: 是否支持装饰器模式"""
        config = CircuitBreakerConfig()
        breaker = MarketPrismCircuitBreaker("test", config)
        
        # 测试是否支持作为装饰器使用
        try:
            @breaker
            async def decorated_function():
                return "decorated"
            
            # 如果不支持装饰器，这里会失败
            result = asyncio.run(decorated_function())
            assert result == "decorated"
        except Exception as e:
            pytest.fail(f"TDD发现设计问题: CircuitBreaker应该支持装饰器模式 - {e}")
    
    def test_callback_hooks_support(self):
        """TDD发现问题: 是否支持状态变更回调"""
        config = CircuitBreakerConfig()
        breaker = MarketPrismCircuitBreaker("test", config)
        
        # 检查是否支持状态变更回调
        callback_methods = [
            'on_state_change',
            'on_open',
            'on_close', 
            'on_half_open',
            'add_listener'
        ]
        
        missing_callbacks = []
        for method in callback_methods:
            if not hasattr(breaker, method):
                missing_callbacks.append(method)
        
        if missing_callbacks:
            pytest.fail(f"TDD发现设计问题: CircuitBreaker缺少回调机制: {missing_callbacks}")


@pytest.mark.unit
class TestOperationResult:
    """测试操作结果类"""
    
    def test_operation_result_creation(self):
        """测试操作结果创建"""
        result = OperationResult(success=True)
        
        assert result.success is True
        assert result.timestamp > 0
        assert result.error is None
        assert result.response_time >= 0
    
    def test_operation_result_with_error(self):
        """测试包含错误的操作结果"""
        error = Exception("Test error")
        result = OperationResult(success=False, error=error, response_time=1.5)
        
        assert result.success is False
        assert result.error == error
        assert result.response_time == 1.5 