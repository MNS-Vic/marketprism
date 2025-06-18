"""
指数退避重试处理器测试
测试ExponentialBackoffRetry的核心功能
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Optional

# 导入被测试的模块
try:
    from core.reliability.retry_handler import (
        ExponentialBackoffRetry,
        RetryPolicy,
        RetryErrorType,
        RetryableException
    )
    HAS_RETRY_MODULES = True
except ImportError as e:
    HAS_RETRY_MODULES = False
    pytest.skip(f"重试模块导入失败: {e}", allow_module_level=True)


@pytest.mark.skipif(not HAS_RETRY_MODULES, reason="重试模块不可用")
class TestRetryPolicy:
    """重试策略测试"""
    
    def test_retry_policy_default_values(self):
        """测试重试策略默认值"""
        policy = RetryPolicy()
        
        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.exponential_base == 2.0
        assert policy.jitter_factor == 0.1
        assert policy.timeout == 300.0
        
    def test_retry_policy_custom_values(self):
        """测试重试策略自定义值"""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            exponential_base=1.5,
            jitter_factor=0.2,
            timeout=600.0
        )
        
        assert policy.max_attempts == 5
        assert policy.base_delay == 2.0
        assert policy.max_delay == 120.0
        assert policy.exponential_base == 1.5
        assert policy.jitter_factor == 0.2
        assert policy.timeout == 600.0


@pytest.mark.skipif(not HAS_RETRY_MODULES, reason="重试模块不可用")
class TestRetryErrorType:
    """重试错误类型测试"""
    
    def test_retry_error_type_enum_values(self):
        """测试重试错误类型枚举值"""
        assert RetryErrorType.NETWORK_ERROR.value == "network_error"
        assert RetryErrorType.TIMEOUT_ERROR.value == "timeout_error"
        assert RetryErrorType.RATE_LIMIT_ERROR.value == "rate_limit_error"
        assert RetryErrorType.SERVER_ERROR.value == "server_error"
        assert RetryErrorType.AUTHENTICATION_ERROR.value == "authentication_error"
        assert RetryErrorType.UNKNOWN_ERROR.value == "unknown_error"


@pytest.mark.skipif(not HAS_RETRY_MODULES, reason="重试模块不可用")
class TestExponentialBackoffRetryInitialization:
    """指数退避重试处理器初始化测试"""
    
    def test_retry_handler_initialization_default(self):
        """测试使用默认配置初始化重试处理器"""
        handler = ExponentialBackoffRetry("test_handler")
        
        assert handler.name == "test_handler"
        assert handler.total_attempts == 0
        assert handler.successful_operations == 0
        assert handler.failed_operations == 0
        assert isinstance(handler.retry_stats, dict)
        assert isinstance(handler.error_stats, dict)
        
    def test_retry_handler_has_required_attributes(self):
        """测试重试处理器具有必需的属性"""
        handler = ExponentialBackoffRetry("test_handler")
        
        required_attributes = [
            'name', 'total_attempts', 'successful_operations', 'failed_operations',
            'retry_stats', 'error_stats', 'attempt_history'
        ]
        
        for attr in required_attributes:
            assert hasattr(handler, attr), f"缺少必需属性: {attr}"


@pytest.mark.skipif(not HAS_RETRY_MODULES, reason="重试模块不可用")
class TestExponentialBackoffRetryBasicOperations:
    """指数退避重试处理器基本操作测试"""
    
    @pytest.fixture
    def retry_handler(self):
        """创建测试用的重试处理器"""
        return ExponentialBackoffRetry("test_handler")
        
    async def test_retry_handler_successful_operation(self, retry_handler):
        """测试成功操作"""
        async def successful_operation():
            return "success_result"
            
        result = await retry_handler.retry_with_backoff(
            successful_operation,
            "test_exchange",
            "test_operation"
        )
        
        assert result == "success_result"
        assert retry_handler.successful_operations == 1
        assert retry_handler.total_attempts == 1
        
    async def test_retry_handler_failed_operation_with_retry(self, retry_handler):
        """测试失败操作的重试"""
        call_count = 0
        
        async def failing_then_succeeding_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success_after_retry"
            
        policy = RetryPolicy(max_attempts=5, base_delay=0.01)  # 快速重试用于测试
        
        result = await retry_handler.retry_with_backoff(
            failing_then_succeeding_operation,
            "test_exchange",
            "test_operation",
            policy
        )
        
        assert result == "success_after_retry"
        assert call_count == 3
        assert retry_handler.successful_operations == 1
        
    async def test_retry_handler_exhausted_attempts(self, retry_handler):
        """测试重试次数耗尽"""
        async def always_failing_operation():
            raise ValueError("Always fails")
            
        policy = RetryPolicy(max_attempts=2, base_delay=0.01)
        
        with pytest.raises(ValueError):
            await retry_handler.retry_with_backoff(
                always_failing_operation,
                "test_exchange",
                "test_operation",
                policy
            )
            
        assert retry_handler.failed_operations == 1
        assert retry_handler.total_attempts == 2  # 尝试了2次
        
    async def test_retry_handler_error_classification(self, retry_handler):
        """测试错误分类"""
        # 测试不同类型的错误
        test_errors = [
            (ConnectionError("Network error"), RetryErrorType.NETWORK_ERROR),
            (TimeoutError("Timeout"), RetryErrorType.TIMEOUT_ERROR),
            (ValueError("Unknown error"), RetryErrorType.UNKNOWN_ERROR)
        ]
        
        for error, expected_type in test_errors:
            classified_type = retry_handler._classify_error(error)
            assert classified_type == expected_type
            
    async def test_retry_handler_delay_calculation(self, retry_handler):
        """测试延迟计算"""
        policy = RetryPolicy(
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=10.0,
            jitter_factor=0.0  # 禁用抖动以便测试
        )
        
        # 测试指数退避
        delay1 = retry_handler._calculate_delay(1.0, policy)
        delay2 = retry_handler._calculate_delay(delay1, policy)
        delay3 = retry_handler._calculate_delay(delay2, policy)
        
        assert delay1 == 2.0  # 1.0 * 2.0
        assert delay2 == 4.0  # 2.0 * 2.0
        assert delay3 == 8.0  # 4.0 * 2.0
        
        # 测试最大延迟限制
        large_delay = retry_handler._calculate_delay(20.0, policy)
        assert large_delay == policy.max_delay
        
    async def test_retry_handler_should_retry_logic(self, retry_handler):
        """测试重试判断逻辑"""
        policy = RetryPolicy(max_attempts=3)
        
        # 网络错误应该重试
        should_retry = retry_handler._should_retry(
            RetryErrorType.NETWORK_ERROR, 1, policy
        )
        assert should_retry is True
        
        # 认证错误不应该重试
        should_retry = retry_handler._should_retry(
            RetryErrorType.AUTHENTICATION_ERROR, 1, policy
        )
        assert should_retry is False
        
        # 超过最大尝试次数不应该重试
        should_retry = retry_handler._should_retry(
            RetryErrorType.NETWORK_ERROR, 3, policy
        )
        assert should_retry is False
        
    async def test_retry_handler_with_fallback(self, retry_handler):
        """测试带回退的重试"""
        async def failing_operation():
            raise ConnectionError("Always fails")
            
        async def fallback_operation():
            return "fallback_result"
            
        policy = RetryPolicy(max_attempts=2, base_delay=0.01)
        
        result = await retry_handler.retry_with_backoff(
            failing_operation,
            "test_exchange",
            "test_operation",
            policy,
            fallback_operation
        )
        
        assert result == "fallback_result"
        assert retry_handler.failed_operations == 1


@pytest.mark.skipif(not HAS_RETRY_MODULES, reason="重试模块不可用")
class TestExponentialBackoffRetryStatistics:
    """指数退避重试处理器统计测试"""
    
    @pytest.fixture
    def retry_handler(self):
        """创建测试用的重试处理器"""
        return ExponentialBackoffRetry("stats_test")
        
    async def test_retry_handler_get_stats(self, retry_handler):
        """测试获取重试统计"""
        # 执行一些操作
        async def test_operation():
            return "test"
            
        await retry_handler.retry_with_backoff(
            test_operation,
            "test_exchange",
            "test_operation"
        )
        
        stats = retry_handler.get_stats()
        
        assert isinstance(stats, dict)
        expected_keys = [
            'name', 'total_attempts', 'successful_operations', 'failed_operations',
            'retry_stats', 'error_stats', 'success_rate'
        ]
        
        for key in expected_keys:
            assert key in stats
            
        assert stats['total_attempts'] >= 1
        assert stats['successful_operations'] >= 1
        
    async def test_retry_handler_reset_stats(self, retry_handler):
        """测试重置统计信息"""
        # 执行一些操作
        async def test_operation():
            return "test"
            
        await retry_handler.retry_with_backoff(
            test_operation,
            "test_exchange",
            "test_operation"
        )
        
        # 重置统计
        retry_handler.reset_stats()
        
        assert retry_handler.total_attempts == 0
        assert retry_handler.successful_operations == 0
        assert retry_handler.failed_operations == 0
        assert len(retry_handler.retry_stats) == 0
        assert len(retry_handler.error_stats) == 0
        
    async def test_retry_handler_attempt_history(self, retry_handler):
        """测试尝试历史记录"""
        call_count = 0
        
        async def failing_then_succeeding():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Temporary failure")
            return "success"
            
        policy = RetryPolicy(max_attempts=3, base_delay=0.01)
        
        await retry_handler.retry_with_backoff(
            failing_then_succeeding,
            "test_exchange",
            "test_operation",
            policy
        )
        
        # 检查尝试历史
        assert len(retry_handler.attempt_history) >= 2
        
        # 第一次尝试应该失败
        first_attempt = retry_handler.attempt_history[0]
        assert first_attempt['success'] is False
        assert first_attempt['error_type'] == RetryErrorType.NETWORK_ERROR
        
        # 最后一次尝试应该成功
        last_attempt = retry_handler.attempt_history[-1]
        assert last_attempt['success'] is True


@pytest.mark.skipif(not HAS_RETRY_MODULES, reason="重试模块不可用")
class TestRetryableException:
    """可重试异常测试"""
    
    def test_retryable_exception_creation(self):
        """测试创建可重试异常"""
        exception = RetryableException("Test error", RetryErrorType.NETWORK_ERROR)
        
        assert str(exception) == "Test error"
        assert exception.error_type == RetryErrorType.NETWORK_ERROR
        assert exception.retryable is True
        
    def test_retryable_exception_non_retryable(self):
        """测试不可重试异常"""
        exception = RetryableException(
            "Auth error", 
            RetryErrorType.AUTHENTICATION_ERROR,
            retryable=False
        )
        
        assert exception.error_type == RetryErrorType.AUTHENTICATION_ERROR
        assert exception.retryable is False


@pytest.mark.integration
@pytest.mark.skipif(not HAS_RETRY_MODULES, reason="重试模块不可用")
class TestExponentialBackoffRetryIntegration:
    """指数退避重试处理器集成测试"""
    
    async def test_retry_handler_full_workflow(self):
        """测试重试处理器完整工作流"""
        handler = ExponentialBackoffRetry("integration_test")
        
        # 模拟不稳定的操作
        call_count = 0
        
        async def unstable_operation():
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                raise ConnectionError("Network timeout")
            elif call_count == 2:
                raise TimeoutError("Request timeout")
            else:
                return {"status": "success", "data": "test_data"}
                
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=0.01,
            exponential_base=1.5
        )
        
        # 执行重试操作
        result = await handler.retry_with_backoff(
            unstable_operation,
            "test_exchange",
            "get_market_data",
            policy
        )
        
        # 验证结果
        assert result["status"] == "success"
        assert result["data"] == "test_data"
        assert call_count == 3
        
        # 验证统计信息
        stats = handler.get_stats()
        assert stats['successful_operations'] == 1
        assert stats['total_attempts'] == 3
        
        # 验证错误统计
        assert stats['error_stats']['network_error'] == 1
        assert stats['error_stats']['timeout_error'] == 1
        
    async def test_retry_handler_concurrent_operations(self):
        """测试重试处理器并发操作"""
        handler = ExponentialBackoffRetry("concurrent_test")
        
        async def operation_with_id(op_id):
            if op_id % 3 == 0:  # 每3个操作失败一次
                raise ConnectionError(f"Operation {op_id} failed")
            return f"result_{op_id}"
            
        policy = RetryPolicy(max_attempts=2, base_delay=0.01)
        
        # 并发执行多个操作
        tasks = []
        for i in range(10):
            task = asyncio.create_task(
                handler.retry_with_backoff(
                    lambda op_id=i: operation_with_id(op_id),
                    "test_exchange",
                    f"operation_{i}",
                    policy
                )
            )
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        successful_results = [r for r in results if isinstance(r, str)]
        failed_results = [r for r in results if isinstance(r, Exception)]
        
        assert len(successful_results) > 0
        assert len(failed_results) > 0
        
        # 验证统计信息
        stats = handler.get_stats()
        assert stats['total_attempts'] >= 10
        assert stats['successful_operations'] > 0
        assert stats['failed_operations'] > 0
