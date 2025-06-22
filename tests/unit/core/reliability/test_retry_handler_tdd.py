"""
重试处理器TDD测试
专注于提升覆盖率和测试未覆盖的功能
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from collections import defaultdict

try:
    from core.reliability.retry_handler import (
        ExponentialBackoffRetry, RetryPolicy, RetryErrorType, 
        RetryableException, RetryAttempt, retry_on_failure,
        RetryManager, retry_manager
    )
    HAS_RETRY_HANDLER = True
except ImportError:
    HAS_RETRY_HANDLER = False


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestRetryPolicyConfiguration:
    """测试重试策略配置"""
    
    def test_default_retry_policy(self):
        """测试：默认重试策略"""
        policy = RetryPolicy()
        
        assert policy.max_attempts == 5
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.multiplier == 2.0
        assert policy.jitter_range == 0.1
        assert policy.backoff_strategy == "exponential"
        assert RetryErrorType.CONNECTION_ERROR in policy.retryable_errors
        assert RetryErrorType.AUTHENTICATION_ERROR in policy.non_retryable_errors
    
    def test_custom_retry_policy(self):
        """测试：自定义重试策略"""
        policy = RetryPolicy(
            max_attempts=10,
            base_delay=2.0,
            max_delay=120.0,
            multiplier=3.0,
            jitter_range=0.2,
            backoff_strategy="linear",
            retryable_errors=[RetryErrorType.TIMEOUT_ERROR],
            non_retryable_errors=[RetryErrorType.VALIDATION_ERROR]
        )
        
        assert policy.max_attempts == 10
        assert policy.base_delay == 2.0
        assert policy.max_delay == 120.0
        assert policy.multiplier == 3.0
        assert policy.jitter_range == 0.2
        assert policy.backoff_strategy == "linear"
        assert policy.retryable_errors == [RetryErrorType.TIMEOUT_ERROR]
        assert policy.non_retryable_errors == [RetryErrorType.VALIDATION_ERROR]
    
    def test_retry_attempt_creation(self):
        """测试：重试尝试记录创建"""
        attempt = RetryAttempt(
            attempt_number=1,
            error_type=RetryErrorType.CONNECTION_ERROR,
            error_message="Connection failed",
            delay_before=1.5,
            response_time=0.8,
            success=False
        )
        
        assert attempt.attempt_number == 1
        assert attempt.error_type == RetryErrorType.CONNECTION_ERROR
        assert attempt.error_message == "Connection failed"
        assert attempt.delay_before == 1.5
        assert attempt.response_time == 0.8
        assert attempt.success is False
        assert attempt.timestamp > 0
    
    def test_retryable_exception_creation(self):
        """测试：可重试异常创建"""
        original_error = ConnectionError("Original connection error")
        retry_exception = RetryableException(
            "Retry failed",
            RetryErrorType.CONNECTION_ERROR,
            original_error
        )
        
        assert str(retry_exception) == "Retry failed"
        assert retry_exception.error_type == RetryErrorType.CONNECTION_ERROR
        assert retry_exception.original_error is original_error


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestExponentialBackoffRetryCore:
    """测试指数退避重试核心功能"""
    
    @pytest.fixture
    def retry_handler(self):
        """创建测试用的重试处理器"""
        return ExponentialBackoffRetry("test_handler")
    
    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self, retry_handler):
        """测试：成功操作无需重试"""
        async def successful_operation():
            return "success_result"
        
        result = await retry_handler.retry_with_backoff(
            successful_operation,
            "test_exchange",
            "test_operation"
        )
        
        assert result == "success_result"
        assert len(retry_handler.attempt_history) == 1
        assert retry_handler.attempt_history[0].success is True
        assert retry_handler.retry_stats["test_operation_success"] == 1
    
    @pytest.mark.asyncio
    async def test_sync_operation_execution(self, retry_handler):
        """测试：同步操作执行"""
        def sync_operation():
            return "sync_result"
        
        result = await retry_handler.retry_with_backoff(
            sync_operation,
            "test_exchange",
            "sync_test"
        )
        
        assert result == "sync_result"
        assert len(retry_handler.attempt_history) == 1
        assert retry_handler.attempt_history[0].success is True
    
    @pytest.mark.asyncio
    async def test_retry_with_eventual_success(self, retry_handler):
        """测试：重试后最终成功"""
        call_count = 0
        
        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "eventual_success"
        
        policy = RetryPolicy(max_attempts=5, base_delay=0.01, max_delay=0.1)
        
        result = await retry_handler.retry_with_backoff(
            failing_then_success,
            "test_exchange",
            "retry_test",
            policy
        )
        
        assert result == "eventual_success"
        assert call_count == 3
        assert len(retry_handler.attempt_history) == 3
        assert retry_handler.attempt_history[-1].success is True
        assert retry_handler.retry_stats["retry_test_success"] == 1
    
    @pytest.mark.asyncio
    async def test_retry_exhaustion_failure(self, retry_handler):
        """测试：重试次数耗尽失败"""
        async def always_failing():
            raise ConnectionError("Persistent failure")
        
        policy = RetryPolicy(max_attempts=3, base_delay=0.01, max_delay=0.1)
        
        with pytest.raises(RetryableException) as exc_info:
            await retry_handler.retry_with_backoff(
                always_failing,
                "test_exchange",
                "failure_test",
                policy
            )
        
        assert "重试 3 次后仍然失败" in str(exc_info.value)
        assert exc_info.value.error_type == RetryErrorType.CONNECTION_ERROR
        assert len(retry_handler.attempt_history) == 3
        assert all(not attempt.success for attempt in retry_handler.attempt_history)
        assert retry_handler.retry_stats["failure_test_failed"] == 1
    
    @pytest.mark.asyncio
    async def test_non_retryable_error_immediate_failure(self, retry_handler):
        """测试：不可重试错误立即失败"""
        async def auth_error_operation():
            raise ValueError("Authentication failed")  # 会被分类为VALIDATION_ERROR
        
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=0.01,
            non_retryable_errors=[RetryErrorType.VALIDATION_ERROR]
        )
        
        with pytest.raises(RetryableException):
            await retry_handler.retry_with_backoff(
                auth_error_operation,
                "test_exchange",
                "auth_test",
                policy
            )
        
        # 应该只尝试一次
        assert len(retry_handler.attempt_history) == 1
        assert retry_handler.attempt_history[0].success is False
    
    def test_error_classification(self, retry_handler):
        """测试：错误分类功能"""
        # 测试预定义的错误映射
        assert retry_handler._classify_error(ConnectionError()) == RetryErrorType.CONNECTION_ERROR
        assert retry_handler._classify_error(TimeoutError()) == RetryErrorType.TIMEOUT_ERROR
        assert retry_handler._classify_error(asyncio.TimeoutError()) == RetryErrorType.TIMEOUT_ERROR
        assert retry_handler._classify_error(OSError()) == RetryErrorType.CONNECTION_ERROR
        
        # 测试基于消息的分类
        assert retry_handler._classify_error(Exception("rate limit exceeded")) == RetryErrorType.RATE_LIMIT_ERROR
        assert retry_handler._classify_error(Exception("server error 500")) == RetryErrorType.SERVER_ERROR
        assert retry_handler._classify_error(Exception("invalid parameter")) == RetryErrorType.VALIDATION_ERROR
        
        # 测试未知错误
        assert retry_handler._classify_error(Exception("unknown error")) == RetryErrorType.UNKNOWN_ERROR
        
        # 测试已分类的错误
        retry_exception = RetryableException("test", RetryErrorType.RATE_LIMIT_ERROR)
        assert retry_handler._classify_error(retry_exception) == RetryErrorType.RATE_LIMIT_ERROR
    
    def test_should_retry_logic(self, retry_handler):
        """测试：重试判断逻辑"""
        policy = RetryPolicy(
            max_attempts=3,
            retryable_errors=[RetryErrorType.CONNECTION_ERROR],
            non_retryable_errors=[RetryErrorType.AUTHENTICATION_ERROR]
        )
        
        # 可重试错误，未达到最大次数
        assert retry_handler._should_retry(RetryErrorType.CONNECTION_ERROR, 1, policy) is True
        assert retry_handler._should_retry(RetryErrorType.CONNECTION_ERROR, 2, policy) is True
        
        # 达到最大次数
        assert retry_handler._should_retry(RetryErrorType.CONNECTION_ERROR, 3, policy) is False
        
        # 不可重试错误
        assert retry_handler._should_retry(RetryErrorType.AUTHENTICATION_ERROR, 1, policy) is False
        
        # 不在可重试列表中的错误
        assert retry_handler._should_retry(RetryErrorType.UNKNOWN_ERROR, 1, policy) is False


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestBackoffStrategies:
    """测试退避策略"""
    
    @pytest.fixture
    def retry_handler(self):
        """创建测试用的重试处理器"""
        return ExponentialBackoffRetry("backoff_test")
    
    def test_exponential_backoff_delay_calculation(self, retry_handler):
        """测试：指数退避延迟计算"""
        policy = RetryPolicy(
            base_delay=1.0,
            max_delay=10.0,
            multiplier=2.0,
            jitter_range=0.0,  # 无抖动便于测试
            backoff_strategy="exponential"
        )
        
        # 第一次延迟
        delay1 = retry_handler._calculate_delay(1.0, policy)
        assert delay1 == 1.0
        
        # 更新延迟
        delay2 = retry_handler._update_delay(1.0, policy)
        assert delay2 == 2.0
        
        delay3 = retry_handler._update_delay(2.0, policy)
        assert delay3 == 4.0
        
        # 测试最大延迟限制
        delay_max = retry_handler._update_delay(8.0, policy)
        assert delay_max == 10.0  # 受max_delay限制
    
    def test_linear_backoff_delay_calculation(self, retry_handler):
        """测试：线性退避延迟计算"""
        policy = RetryPolicy(
            base_delay=2.0,
            max_delay=10.0,
            backoff_strategy="linear"
        )
        
        delay1 = retry_handler._update_delay(2.0, policy)
        assert delay1 == 4.0  # 2.0 + 2.0
        
        delay2 = retry_handler._update_delay(4.0, policy)
        assert delay2 == 6.0  # 4.0 + 2.0
        
        # 测试最大延迟限制
        delay_max = retry_handler._update_delay(9.0, policy)
        assert delay_max == 10.0  # 受max_delay限制
    
    def test_fixed_backoff_delay_calculation(self, retry_handler):
        """测试：固定退避延迟计算"""
        policy = RetryPolicy(
            base_delay=3.0,
            backoff_strategy="fixed"
        )
        
        # 固定延迟应该始终返回base_delay
        assert retry_handler._update_delay(3.0, policy) == 3.0
        assert retry_handler._update_delay(10.0, policy) == 3.0
        assert retry_handler._update_delay(100.0, policy) == 3.0
    
    def test_jitter_application(self, retry_handler):
        """测试：抖动应用"""
        policy = RetryPolicy(
            base_delay=10.0,
            jitter_range=0.1  # ±10%
        )
        
        # 多次计算延迟，应该有变化（由于抖动）
        delays = [retry_handler._calculate_delay(10.0, policy) for _ in range(10)]
        
        # 所有延迟应该在9.0到11.0之间
        assert all(9.0 <= delay <= 11.0 for delay in delays)
        
        # 应该有一些变化（不是所有值都相同）
        assert len(set(delays)) > 1
    
    def test_unknown_backoff_strategy_defaults_to_exponential(self, retry_handler):
        """测试：未知退避策略默认为指数退避"""
        policy = RetryPolicy(
            base_delay=1.0,
            multiplier=3.0,
            backoff_strategy="unknown_strategy"
        )
        
        # 应该使用指数退避
        delay = retry_handler._update_delay(1.0, policy)
        assert delay == 3.0  # 1.0 * 3.0


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestRetryHandlerConfiguration:
    """测试重试处理器配置功能"""
    
    @pytest.fixture
    def retry_handler(self):
        """创建测试用的重试处理器"""
        return ExponentialBackoffRetry("config_test")
    
    def test_add_error_mapping(self, retry_handler):
        """测试：添加错误映射"""
        class CustomError(Exception):
            pass
        
        retry_handler.add_error_mapping(CustomError, RetryErrorType.RATE_LIMIT_ERROR)
        
        assert CustomError in retry_handler.error_type_mapping
        assert retry_handler.error_type_mapping[CustomError] == RetryErrorType.RATE_LIMIT_ERROR
        
        # 测试分类
        assert retry_handler._classify_error(CustomError()) == RetryErrorType.RATE_LIMIT_ERROR
    
    def test_set_policy_for_operation(self, retry_handler):
        """测试：设置操作策略"""
        custom_policy = RetryPolicy(
            max_attempts=10,
            base_delay=5.0,
            backoff_strategy="linear"
        )
        
        retry_handler.set_policy_for_operation("custom_operation", custom_policy)
        
        assert "custom_operation" in retry_handler.policy_cache
        assert retry_handler.policy_cache["custom_operation"] is custom_policy
        
        # 测试获取策略
        retrieved_policy = retry_handler._get_policy_for_operation("custom_operation")
        assert retrieved_policy is custom_policy
    
    def test_predefined_operation_policies(self, retry_handler):
        """测试：预定义操作策略"""
        # 测试资金费率收集策略
        funding_policy = retry_handler._get_policy_for_operation("funding_rate_collection")
        assert funding_policy.max_attempts == 3
        assert funding_policy.base_delay == 5.0
        assert funding_policy.max_delay == 30.0
        
        # 测试交易数据处理策略
        trade_policy = retry_handler._get_policy_for_operation("trade_data_processing")
        assert trade_policy.max_attempts == 5
        assert trade_policy.base_delay == 1.0
        assert trade_policy.max_delay == 10.0
        
        # 测试健康检查策略
        health_policy = retry_handler._get_policy_for_operation("health_check")
        assert health_policy.max_attempts == 3
        assert health_policy.base_delay == 2.0
        assert health_policy.max_delay == 15.0
        
        # 测试默认策略
        default_policy = retry_handler._get_policy_for_operation("unknown_operation")
        assert default_policy is retry_handler.default_policy
    
    def test_policy_caching(self, retry_handler):
        """测试：策略缓存"""
        # 第一次获取应该创建并缓存
        policy1 = retry_handler._get_policy_for_operation("funding_rate_collection")
        assert "funding_rate_collection" in retry_handler.policy_cache
        
        # 第二次获取应该从缓存返回
        policy2 = retry_handler._get_policy_for_operation("funding_rate_collection")
        assert policy1 is policy2  # 应该是同一个对象
    
    def test_get_status_comprehensive(self, retry_handler):
        """测试：获取完整状态信息"""
        # 添加一些统计数据
        retry_handler.retry_stats["test_success"] = 5
        retry_handler.retry_stats["test_failed"] = 2
        retry_handler.error_stats[RetryErrorType.CONNECTION_ERROR.value] = 3
        
        # 添加一些尝试历史
        for i in range(10):
            attempt = RetryAttempt(
                attempt_number=i+1,
                success=i % 3 != 0  # 每3个失败一个
            )
            retry_handler.attempt_history.append(attempt)
        
        status = retry_handler.get_status()
        
        assert status["name"] == "config_test"
        assert status["total_attempts"] == 10
        assert "recent_success_rate" in status
        assert status["retry_stats"]["test_success"] == 5
        assert status["retry_stats"]["test_failed"] == 2
        assert status["error_stats"][RetryErrorType.CONNECTION_ERROR.value] == 3
        assert "error_mappings" in status
        assert "cached_policies" in status
        assert "default_policy" in status
    
    def test_reset_stats(self, retry_handler):
        """测试：重置统计数据"""
        # 添加一些数据
        retry_handler.retry_stats["test"] = 5
        retry_handler.error_stats["error"] = 3
        retry_handler.attempt_history.append(RetryAttempt(attempt_number=1))
        
        # 重置
        retry_handler.reset_stats()
        
        assert len(retry_handler.retry_stats) == 0
        assert len(retry_handler.error_stats) == 0
        assert len(retry_handler.attempt_history) == 0


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestRetryDecorator:
    """测试重试装饰器"""

    @pytest.mark.asyncio
    async def test_retry_decorator_success(self):
        """测试：重试装饰器成功场景"""
        @retry_on_failure("decorator_test", operation_type="test_op")
        async def decorated_function():
            return "decorated_success"

        result = await decorated_function()
        assert result == "decorated_success"

    @pytest.mark.asyncio
    async def test_retry_decorator_with_custom_policy(self):
        """测试：带自定义策略的重试装饰器"""
        policy = RetryPolicy(max_attempts=2, base_delay=0.01)

        call_count = 0

        @retry_on_failure("decorator_policy_test", policy=policy, operation_type="custom_op")
        async def decorated_failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Decorator test failure")
            return "decorator_retry_success"

        result = await decorated_failing_function()
        assert result == "decorator_retry_success"
        assert call_count == 2


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestRetryManager:
    """测试重试管理器"""

    @pytest.fixture
    def manager(self):
        """创建测试用的重试管理器"""
        return RetryManager()

    def test_get_or_create_handler(self, manager):
        """测试：获取或创建处理器"""
        # 第一次获取应该创建新的处理器
        handler1 = manager.get_handler("test_handler")
        assert isinstance(handler1, ExponentialBackoffRetry)
        assert handler1.name == "test_handler"
        assert "test_handler" in manager.handlers

        # 第二次获取应该返回相同的处理器
        handler2 = manager.get_handler("test_handler")
        assert handler1 is handler2

    def test_get_predefined_policy(self, manager):
        """测试：获取预定义策略"""
        # 连接重试策略
        conn_policy = manager.get_policy("connection_retry")
        assert conn_policy.max_attempts == 5
        assert conn_policy.base_delay == 2.0
        assert RetryErrorType.CONNECTION_ERROR in conn_policy.retryable_errors

        # 限流重试策略
        rate_policy = manager.get_policy("rate_limit_retry")
        assert rate_policy.max_attempts == 3
        assert rate_policy.base_delay == 5.0
        assert RetryErrorType.RATE_LIMIT_ERROR in rate_policy.retryable_errors

        # 服务器错误重试策略
        server_policy = manager.get_policy("server_error_retry")
        assert server_policy.max_attempts == 4
        assert server_policy.base_delay == 1.0
        assert RetryErrorType.SERVER_ERROR in server_policy.retryable_errors

        # 不存在的策略应该返回None
        assert manager.get_policy("nonexistent_policy") is None

    @pytest.mark.asyncio
    async def test_retry_operation_convenience_method(self, manager):
        """测试：便捷重试操作方法"""
        async def test_operation():
            return "manager_test_result"

        result = await manager.retry_operation(
            test_operation,
            handler_name="test_handler",
            exchange_name="test_exchange",
            operation_type="test_operation"
        )

        assert result == "manager_test_result"
        assert "test_handler" in manager.handlers

    @pytest.mark.asyncio
    async def test_retry_operation_with_policy(self, manager):
        """测试：使用指定策略的重试操作"""
        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Manager test failure")
            return "manager_retry_success"

        result = await manager.retry_operation(
            failing_operation,
            handler_name="policy_test_handler",
            exchange_name="test_exchange",
            operation_type="policy_test",
            policy_name="connection_retry"
        )

        assert result == "manager_retry_success"
        assert call_count == 2

    def test_get_all_status(self, manager):
        """测试：获取所有处理器状态"""
        # 创建几个处理器
        handler1 = manager.get_handler("handler1")
        handler2 = manager.get_handler("handler2")

        # 添加一些统计数据
        handler1.retry_stats["test"] = 5
        handler2.retry_stats["test"] = 3

        all_status = manager.get_all_status()

        assert "handler1" in all_status
        assert "handler2" in all_status
        assert all_status["handler1"]["name"] == "handler1"
        assert all_status["handler2"]["name"] == "handler2"
        assert all_status["handler1"]["retry_stats"]["test"] == 5
        assert all_status["handler2"]["retry_stats"]["test"] == 3


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestRetryHandlerAdvancedFeatures:
    """测试重试处理器高级功能"""

    @pytest.fixture
    def retry_handler(self):
        """创建测试用的重试处理器"""
        return ExponentialBackoffRetry("advanced_test")

    @pytest.mark.asyncio
    async def test_attempt_history_size_limit(self, retry_handler):
        """测试：尝试历史大小限制"""
        # 添加大量历史记录
        for i in range(12000):  # 超过10000的限制
            attempt = RetryAttempt(attempt_number=i+1)
            retry_handler.attempt_history.append(attempt)

        # 触发大小限制检查
        retry_handler._record_attempt(1, None, "", 0.0, 0.0, True)

        # 应该被截断到5000（保留最后5000个）
        assert len(retry_handler.attempt_history) == 5000

    @pytest.mark.asyncio
    async def test_trigger_alert_functionality(self, retry_handler):
        """测试：触发警报功能"""
        # 这个方法在当前实现中是空的，但我们测试它不会抛出异常
        await retry_handler._trigger_alert(
            "test_exchange",
            "test_operation",
            Exception("Test error"),
            3
        )
        # 如果没有异常，测试通过

    def test_success_rate_calculation_empty_history(self, retry_handler):
        """测试：空历史记录的成功率计算"""
        status = retry_handler.get_status()
        assert status["recent_success_rate"] == 0.0

    def test_success_rate_calculation_with_data(self, retry_handler):
        """测试：有数据的成功率计算"""
        # 添加一些成功和失败的尝试
        for i in range(10):
            attempt = RetryAttempt(
                attempt_number=i+1,
                success=i % 2 == 0  # 50%成功率
            )
            retry_handler.attempt_history.append(attempt)

        status = retry_handler.get_status()
        assert status["recent_success_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_context_parameter_handling(self, retry_handler):
        """测试：上下文参数处理"""
        context = {"user_id": "test_user", "session_id": "test_session"}

        async def operation_with_context():
            return "context_result"

        # 上下文参数应该被正确传递（即使当前实现中未使用）
        result = await retry_handler.retry_with_backoff(
            operation_with_context,
            "test_exchange",
            "context_test",
            context=context
        )

        assert result == "context_result"

    def test_error_message_classification_edge_cases(self, retry_handler):
        """测试：错误消息分类边界情况"""
        # 测试大小写不敏感
        assert retry_handler._classify_error(Exception("RATE LIMIT EXCEEDED")) == RetryErrorType.RATE_LIMIT_ERROR
        assert retry_handler._classify_error(Exception("Server Error 500")) == RetryErrorType.SERVER_ERROR

        # 测试部分匹配
        assert retry_handler._classify_error(Exception("connection timeout occurred")) == RetryErrorType.TIMEOUT_ERROR
        assert retry_handler._classify_error(Exception("unauthorized access denied")) == RetryErrorType.AUTHENTICATION_ERROR

        # 测试空消息
        assert retry_handler._classify_error(Exception("")) == RetryErrorType.UNKNOWN_ERROR

    def test_default_policy_with_custom_handler(self):
        """测试：带自定义默认策略的处理器"""
        custom_policy = RetryPolicy(
            max_attempts=10,
            base_delay=5.0,
            multiplier=3.0
        )

        handler = ExponentialBackoffRetry("custom_default", custom_policy)

        assert handler.default_policy is custom_policy
        assert handler.default_policy.max_attempts == 10
        assert handler.default_policy.base_delay == 5.0
        assert handler.default_policy.multiplier == 3.0


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestGlobalRetryManager:
    """测试全局重试管理器"""

    def test_global_retry_manager_instance(self):
        """测试：全局重试管理器实例"""
        assert retry_manager is not None
        assert isinstance(retry_manager, RetryManager)

    @pytest.mark.asyncio
    async def test_global_manager_usage(self):
        """测试：全局管理器使用"""
        async def global_test_operation():
            return "global_test_result"

        result = await retry_manager.retry_operation(
            global_test_operation,
            handler_name="global_test_handler",
            exchange_name="global_exchange",
            operation_type="global_test"
        )

        assert result == "global_test_result"
        assert "global_test_handler" in retry_manager.handlers


@pytest.mark.skipif(not HAS_RETRY_HANDLER, reason="重试处理器模块不可用")
class TestRetryHandlerEdgeCases:
    """测试重试处理器边界情况"""

    @pytest.fixture
    def retry_handler(self):
        """创建测试用的重试处理器"""
        return ExponentialBackoffRetry("edge_case_test")

    @pytest.mark.asyncio
    async def test_zero_max_attempts(self, retry_handler):
        """测试：零最大尝试次数"""
        policy = RetryPolicy(max_attempts=0)

        async def any_operation():
            return "should_not_execute"

        with pytest.raises(RetryableException):
            await retry_handler.retry_with_backoff(
                any_operation,
                "test_exchange",
                "zero_attempts",
                policy
            )

        # 应该没有尝试记录
        assert len(retry_handler.attempt_history) == 0

    @pytest.mark.asyncio
    async def test_very_small_delays(self, retry_handler):
        """测试：极小延迟"""
        policy = RetryPolicy(
            max_attempts=3,
            base_delay=0.001,  # 1毫秒
            max_delay=0.005,   # 5毫秒
            jitter_range=0.0
        )

        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Small delay test")
            return "small_delay_success"

        start_time = time.time()
        result = await retry_handler.retry_with_backoff(
            failing_operation,
            "test_exchange",
            "small_delay_test",
            policy
        )
        end_time = time.time()

        assert result == "small_delay_success"
        assert call_count == 3
        # 总时间应该很短（小于1秒）
        assert end_time - start_time < 1.0

    def test_max_delay_smaller_than_base_delay(self, retry_handler):
        """测试：最大延迟小于基础延迟"""
        policy = RetryPolicy(
            base_delay=10.0,
            max_delay=5.0,  # 小于base_delay
            jitter_range=0.0
        )

        # 计算的延迟应该被限制为max_delay
        delay = retry_handler._calculate_delay(10.0, policy)
        assert delay == 5.0

        # 更新的延迟也应该被限制
        updated_delay = retry_handler._update_delay(10.0, policy)
        assert updated_delay == 5.0

    def test_negative_jitter_range(self, retry_handler):
        """测试：负抖动范围"""
        policy = RetryPolicy(
            base_delay=10.0,
            jitter_range=-0.1  # 负值
        )

        # 应该仍然能正常工作
        delay = retry_handler._calculate_delay(10.0, policy)
        assert isinstance(delay, float)
        assert delay > 0
