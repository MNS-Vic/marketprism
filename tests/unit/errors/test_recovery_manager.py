"""
错误恢复管理器测试
"""

from datetime import datetime, timezone
import sys
import os
import pytest
import time
from unittest.mock import Mock, patch
from pathlib import Path

# Add the project root to the path to allow absolute imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from core.errors.recovery_manager import (
    ErrorRecoveryManager, RecoveryStatus, RecoveryResult,
    RetryAction, CircuitBreakerAction, FailoverAction, GracefulDegradationAction
)
from core.errors import (
    MarketPrismError, NetworkError,
    ErrorType, ErrorCategory, ErrorSeverity, RecoveryStrategy
)


class TestRetryAction:
    """重试动作测试"""
    
    def setup_method(self):
        """设置测试方法"""
        self.action = RetryAction(max_attempts=3, base_delay=0.01)  # 使用很小的延迟加快测试
    
    def test_can_handle_retry_strategy(self):
        """测试是否能处理重试策略"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        assert self.action.can_handle(error) is True
    
    def test_can_handle_exponential_backoff_strategy(self):
        """测试是否能处理指数退避策略"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF
        )
        
        assert self.action.can_handle(error) is True
    
    def test_cannot_handle_other_strategy(self):
        """测试不能处理其他策略"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.CIRCUIT_BREAKER
        )
        
        assert self.action.can_handle(error) is False
    
    def test_successful_retry(self):
        """测试成功重试"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        # 模拟成功的重试函数
        mock_function = Mock(return_value="success")
        context = {'retry_function': mock_function}
        
        result = self.action.execute(error, context)
        
        assert result.status == RecoveryStatus.SUCCESS
        assert result.success is True
        assert result.attempts == 1
        assert mock_function.call_count == 1
    
    def test_retry_with_failures_then_success(self):
        """测试重试失败后成功"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        # 模拟前两次失败，第三次成功的函数
        mock_function = Mock(side_effect=[Exception("失败1"), Exception("失败2"), "success"])
        context = {'retry_function': mock_function}
        
        result = self.action.execute(error, context)
        
        assert result.status == RecoveryStatus.SUCCESS
        assert result.success is True
        assert result.attempts == 3
        assert mock_function.call_count == 3
    
    def test_all_retries_fail(self):
        """测试所有重试都失败"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        # 模拟总是失败的函数
        mock_function = Mock(side_effect=Exception("永远失败"))
        context = {'retry_function': mock_function}
        
        result = self.action.execute(error, context)
        
        assert result.status == RecoveryStatus.FAILED
        assert result.success is False
        assert result.attempts == 3  # max_attempts
        assert mock_function.call_count == 3
    
    def test_no_retry_function(self):
        """测试没有重试函数"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        result = self.action.execute(error, {})
        
        assert result.status == RecoveryStatus.SKIPPED
        assert result.success is False
        assert result.attempts == 0


class TestCircuitBreakerAction:
    """熔断器动作测试"""
    
    def setup_method(self):
        """设置测试方法"""
        self.action = CircuitBreakerAction(
            failure_threshold=2,
            recovery_timeout=1,  # 1秒恢复超时
            success_threshold=2
        )
    
    def test_can_handle_circuit_breaker_strategy(self):
        """测试是否能处理熔断器策略"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.CIRCUIT_BREAKER
        )
        
        assert self.action.can_handle(error) is True
    
    def test_successful_execution(self):
        """测试成功执行"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.CIRCUIT_BREAKER
        )
        
        mock_function = Mock(return_value="success")
        context = {'action_function': mock_function}
        
        result = self.action.execute(error, context)
        
        assert result.status == RecoveryStatus.SUCCESS
        assert result.success is True
        assert result.attempts == 1
    
    def test_circuit_breaker_opens_after_failures(self):
        """测试熔断器在失败后开启"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.CIRCUIT_BREAKER
        )
        
        mock_function = Mock(side_effect=Exception("失败"))
        context = {'action_function': mock_function}
        
        # 第一次失败
        result1 = self.action.execute(error, context)
        assert result1.status == RecoveryStatus.FAILED
        
        # 第二次失败，应该触发熔断器开启
        result2 = self.action.execute(error, context)
        assert result2.status == RecoveryStatus.FAILED
        
        # 第三次应该被熔断器跳过
        result3 = self.action.execute(error, context)
        assert result3.status == RecoveryStatus.SKIPPED
        assert "熔断器开启" in result3.error_message
    
    def test_circuit_breaker_recovery(self):
        """测试熔断器恢复"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.CIRCUIT_BREAKER
        )
        
        mock_function = Mock(side_effect=Exception("失败"))
        context = {'action_function': mock_function}
        
        # 触发熔断器开启
        self.action.execute(error, context)
        self.action.execute(error, context)
        
        # 等待恢复超时
        time.sleep(1.1)
        
        # 现在应该可以重新尝试
        mock_function.side_effect = None
        mock_function.return_value = "success"
        
        result = self.action.execute(error, context)
        assert result.status == RecoveryStatus.SUCCESS


class TestFailoverAction:
    """故障转移动作测试"""
    
    def setup_method(self):
        """设置测试方法"""
        self.action = FailoverAction()
    
    def test_can_handle_failover_strategy(self):
        """测试是否能处理故障转移策略"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.FAILOVER
        )
        
        assert self.action.can_handle(error) is True
    
    def test_successful_failover(self):
        """测试成功故障转移"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.FAILOVER
        )
        
        provider1 = Mock(return_value="provider1_result")
        context = {'fallback_providers': [provider1]}
        
        result = self.action.execute(error, context)
        
        assert result.status == RecoveryStatus.SUCCESS
        assert result.success is True
        assert result.attempts == 1
        assert provider1.call_count == 1
    
    def test_failover_with_multiple_providers(self):
        """测试多个提供者的故障转移"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.FAILOVER
        )
        
        provider1 = Mock(side_effect=Exception("provider1失败"))
        provider2 = Mock(return_value="provider2_success")
        provider3 = Mock(return_value="provider3_success")
        
        context = {'fallback_providers': [provider1, provider2, provider3]}
        
        result = self.action.execute(error, context)
        
        assert result.status == RecoveryStatus.SUCCESS
        assert result.success is True
        assert result.attempts == 2  # provider1失败，provider2成功
        assert provider1.call_count == 1
        assert provider2.call_count == 1
        assert provider3.call_count == 0  # 不应该被调用
    
    def test_all_providers_fail(self):
        """测试所有提供者都失败"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.FAILOVER
        )
        
        provider1 = Mock(side_effect=Exception("provider1失败"))
        provider2 = Mock(side_effect=Exception("provider2失败"))
        
        context = {'fallback_providers': [provider1, provider2]}
        
        result = self.action.execute(error, context)
        
        assert result.status == RecoveryStatus.FAILED
        assert result.success is False
        assert result.attempts == 2
    
    def test_no_providers(self):
        """测试没有提供者"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.FAILOVER
        )
        
        result = self.action.execute(error, {})
        
        assert result.status == RecoveryStatus.SKIPPED
        assert result.success is False
        assert result.attempts == 0


class TestErrorRecoveryManager:
    """错误恢复管理器测试"""
    
    def setup_method(self):
        """设置测试方法"""
        self.manager = ErrorRecoveryManager()
    
    def test_attempt_recovery_with_retry_strategy(self):
        """测试使用重试策略的恢复"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        mock_function = Mock(return_value="success")
        context = {'retry_function': mock_function}
        
        result = self.manager.attempt_recovery(error, context)
        
        assert result is not None
        assert result.status == RecoveryStatus.SUCCESS
        assert result.success is True
    
    def test_attempt_recovery_with_log_only_strategy(self):
        """测试仅记录日志策略"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.LOG_ONLY
        )
        
        result = self.manager.attempt_recovery(error)
        
        assert result is not None
        assert result.status == RecoveryStatus.SKIPPED
        assert result.success is False
        assert "仅记录日志" in result.error_message
    
    def test_attempt_recovery_with_manual_intervention_strategy(self):
        """测试需要人工干预策略"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.MANUAL_INTERVENTION
        )
        
        result = self.manager.attempt_recovery(error)
        
        assert result is not None
        assert result.status == RecoveryStatus.SKIPPED
        assert result.success is False
        assert "人工干预" in result.error_message
    
    def test_attempt_recovery_with_unsupported_strategy(self):
        """测试不支持的恢复策略"""
        # 创建一个新的策略（不在默认注册中）
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.MANUAL_INTERVENTION  # 使用未注册的策略
        )
        
        # 清除所有注册的动作
        self.manager.recovery_actions.clear()
        
        result = self.manager.attempt_recovery(error)
        
        assert result is not None
        assert result.status == RecoveryStatus.SKIPPED
        assert result.success is False
        assert "未找到恢复策略处理器" in result.error_message
    
    def test_recovery_statistics(self):
        """测试恢复统计"""
        # 执行一些恢复操作
        error1 = NetworkError(
            message="连接失败1",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        error2 = NetworkError(
            message="连接失败2",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        # 成功的恢复
        mock_function = Mock(return_value="success")
        context = {'retry_function': mock_function}
        self.manager.attempt_recovery(error1, context)
        
        # 失败的恢复
        mock_function = Mock(side_effect=Exception("失败"))
        context = {'retry_function': mock_function}
        self.manager.attempt_recovery(error2, context)
        
        stats = self.manager.get_recovery_statistics()
        
        assert stats["total_attempts"] == 2
        assert stats["successful_attempts"] == 1
        assert stats["success_rate"] == 0.5
        assert "retry" in stats["by_strategy"]
    
    def test_get_recent_recoveries(self):
        """测试获取最近恢复记录"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        mock_function = Mock(return_value="success")
        context = {'retry_function': mock_function}
        
        # 执行恢复
        self.manager.attempt_recovery(error, context)
        
        recent = self.manager.get_recent_recoveries(limit=5)
        
        assert len(recent) == 1
        assert recent[0].status == RecoveryStatus.SUCCESS
    
    def test_clear_history(self):
        """测试清除历史记录"""
        error = NetworkError(
            message="连接失败",
            error_type=ErrorType.CONNECTION_TIMEOUT,
            recovery_strategy=RecoveryStrategy.RETRY
        )
        
        mock_function = Mock(return_value="success")
        context = {'retry_function': mock_function}
        
        # 执行恢复
        self.manager.attempt_recovery(error, context)
        
        # 确认有历史记录
        assert len(self.manager.get_recent_recoveries()) == 1
        
        # 清除历史
        self.manager.clear_history()
        
        # 确认历史记录被清除
        assert len(self.manager.get_recent_recoveries()) == 0