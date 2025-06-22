"""
统一错误处理器测试
测试UnifiedErrorHandler的核心功能
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List, Optional
from datetime import datetime

# 导入被测试的模块
try:
    from core.errors.unified_error_handler import UnifiedErrorHandler
    from core.errors.exceptions import (
        MarketPrismError,
        ConfigurationError,
        NetworkError,
        ValidationError,
        ExchangeError
    )

    # 为了兼容性，创建别名
    ConnectionError = NetworkError
    DataValidationError = ValidationError
    from core.errors.error_categories import ErrorCategory, ErrorSeverity
    from core.errors.error_context import ErrorContext
    from core.errors.recovery_manager import ErrorRecoveryManager as RecoveryManager
    from core.errors.error_aggregator import ErrorAggregator
except ImportError as e:
    pytest.skip(f"错误处理模块导入失败: {e}", allow_module_level=True)


class TestUnifiedErrorHandlerInitialization:
    """统一错误处理器初始化测试"""
    
    def test_error_handler_initialization_default(self):
        """测试使用默认配置初始化错误处理器"""
        error_handler = UnifiedErrorHandler()
        
        assert error_handler is not None
        assert hasattr(error_handler, '_error_aggregator')
        assert hasattr(error_handler, '_recovery_manager')
        assert hasattr(error_handler, '_error_handlers')
        assert hasattr(error_handler, '_metrics')
        
    def test_error_handler_initialization_with_config(self):
        """测试使用配置初始化错误处理器"""
        config = {
            "max_retry_attempts": 5,
            "retry_delay": 2.0,
            "enable_recovery": True,
            "log_errors": True
        }
        
        error_handler = UnifiedErrorHandler(config)
        
        assert error_handler.config == config
        assert error_handler.config["max_retry_attempts"] == 5
        
    def test_error_handler_has_required_components(self):
        """测试错误处理器具有必需组件"""
        error_handler = UnifiedErrorHandler()
        
        required_components = [
            '_error_aggregator',
            '_recovery_manager', 
            '_error_handlers',
            '_metrics',
            '_logger'
        ]
        
        for component in required_components:
            assert hasattr(error_handler, component), f"缺少必需组件: {component}"


class TestUnifiedErrorHandlerErrorHandling:
    """统一错误处理器错误处理测试"""
    
    @pytest.fixture
    def error_handler(self):
        """创建测试用的错误处理器"""
        return UnifiedErrorHandler()
        
    def test_error_handler_handles_configuration_error(self, error_handler):
        """测试处理配置错误"""
        config_error = ConfigurationError("配置文件格式错误")
        
        result = error_handler.handle_error(config_error)
        
        assert result is not None
        assert result.error_type == "ConfigurationError"
        assert result.severity == ErrorSeverity.HIGH
        
    def test_error_handler_handles_connection_error(self, error_handler):
        """测试处理连接错误"""
        conn_error = ConnectionError("无法连接到交易所")
        
        result = error_handler.handle_error(conn_error)
        
        assert result is not None
        assert result.error_type == "ConnectionError"
        assert result.category == ErrorCategory.NETWORK
        
    def test_error_handler_handles_data_validation_error(self, error_handler):
        """测试处理数据验证错误"""
        validation_error = DataValidationError("数据格式不正确")
        
        result = error_handler.handle_error(validation_error)
        
        assert result is not None
        assert result.error_type == "DataValidationError"
        assert result.category == ErrorCategory.DATA
        
    def test_error_handler_handles_exchange_error(self, error_handler):
        """测试处理交易所错误"""
        exchange_error = ExchangeError("API限流", exchange="binance")
        
        result = error_handler.handle_error(exchange_error)
        
        assert result is not None
        assert result.error_type == "ExchangeError"
        assert result.context.get("exchange") == "binance"
        
    def test_error_handler_handles_generic_exception(self, error_handler):
        """测试处理通用异常"""
        generic_error = ValueError("通用值错误")
        
        result = error_handler.handle_error(generic_error)
        
        assert result is not None
        assert result.error_type == "ValueError"
        assert result.severity == ErrorSeverity.MEDIUM
        
    def test_error_handler_with_context(self, error_handler):
        """测试带上下文的错误处理"""
        error = ConnectionError("连接失败")
        context = ErrorContext(
            component="data_collector",
            operation="connect_exchange",
            exchange="binance",
            symbol="BTCUSDT"
        )
        
        result = error_handler.handle_error(error, context)
        
        assert result.context.component == "data_collector"
        assert result.context.operation == "connect_exchange"
        assert result.context.exchange == "binance"


class TestUnifiedErrorHandlerRecovery:
    """统一错误处理器恢复测试"""
    
    @pytest.fixture
    def error_handler_with_recovery(self):
        """创建带恢复功能的错误处理器"""
        config = {
            "enable_recovery": True,
            "max_retry_attempts": 3,
            "retry_delay": 1.0
        }
        return UnifiedErrorHandler(config)
        
    async def test_error_handler_attempts_recovery(self, error_handler_with_recovery):
        """测试错误处理器尝试恢复"""
        error_handler = error_handler_with_recovery
        
        # 模拟恢复管理器
        mock_recovery = AsyncMock()
        mock_recovery.attempt_recovery.return_value = True
        error_handler._recovery_manager = mock_recovery
        
        error = ConnectionError("连接失败")
        
        result = await error_handler.handle_error_with_recovery(error)
        
        # 验证恢复尝试
        mock_recovery.attempt_recovery.assert_called_once()
        assert result.recovered is True
        
    async def test_error_handler_recovery_failure(self, error_handler_with_recovery):
        """测试错误恢复失败"""
        error_handler = error_handler_with_recovery
        
        # 模拟恢复失败
        mock_recovery = AsyncMock()
        mock_recovery.attempt_recovery.return_value = False
        error_handler._recovery_manager = mock_recovery
        
        error = ConnectionError("连接失败")
        
        result = await error_handler.handle_error_with_recovery(error)
        
        assert result.recovered is False
        assert result.recovery_attempts > 0
        
    async def test_error_handler_retry_mechanism(self, error_handler_with_recovery):
        """测试重试机制"""
        error_handler = error_handler_with_recovery
        
        # 模拟重试函数
        retry_count = 0
        
        async def failing_function():
            nonlocal retry_count
            retry_count += 1
            if retry_count < 3:
                raise ConnectionError("临时失败")
            return "成功"
            
        result = await error_handler.retry_with_backoff(failing_function)
        
        assert result == "成功"
        assert retry_count == 3
        
    async def test_error_handler_exponential_backoff(self, error_handler_with_recovery):
        """测试指数退避"""
        error_handler = error_handler_with_recovery
        
        delays = []
        
        async def mock_sleep(delay):
            delays.append(delay)
            
        with patch('asyncio.sleep', side_effect=mock_sleep):
            async def always_failing_function():
                raise ConnectionError("持续失败")
                
            with pytest.raises(ConnectionError):
                await error_handler.retry_with_backoff(always_failing_function)
                
        # 验证指数退避
        assert len(delays) == error_handler.config["max_retry_attempts"]
        assert delays[1] > delays[0]  # 延迟递增


class TestUnifiedErrorHandlerAggregation:
    """统一错误处理器聚合测试"""
    
    @pytest.fixture
    def error_handler_with_aggregation(self):
        """创建带聚合功能的错误处理器"""
        return UnifiedErrorHandler()
        
    def test_error_handler_aggregates_errors(self, error_handler_with_aggregation):
        """测试错误聚合"""
        error_handler = error_handler_with_aggregation
        
        # 模拟错误聚合器
        mock_aggregator = Mock()
        error_handler._error_aggregator = mock_aggregator
        
        errors = [
            ConnectionError("连接失败1"),
            ConnectionError("连接失败2"),
            DataValidationError("数据错误")
        ]
        
        for error in errors:
            error_handler.handle_error(error)
            
        # 验证错误被聚合
        assert mock_aggregator.add_error.call_count == 3
        
    def test_error_handler_gets_error_statistics(self, error_handler_with_aggregation):
        """测试获取错误统计"""
        error_handler = error_handler_with_aggregation
        
        # 模拟错误统计
        mock_aggregator = Mock()
        mock_aggregator.get_error_statistics.return_value = {
            "total_errors": 10,
            "error_types": {
                "ConnectionError": 5,
                "DataValidationError": 3,
                "ConfigurationError": 2
            },
            "error_rate": 0.1
        }
        error_handler._error_aggregator = mock_aggregator
        
        stats = error_handler.get_error_statistics()
        
        assert stats["total_errors"] == 10
        assert stats["error_types"]["ConnectionError"] == 5
        assert stats["error_rate"] == 0.1
        
    def test_error_handler_detects_error_patterns(self, error_handler_with_aggregation):
        """测试检测错误模式"""
        error_handler = error_handler_with_aggregation
        
        # 模拟错误模式检测
        mock_aggregator = Mock()
        mock_aggregator.detect_patterns.return_value = [
            {
                "pattern": "frequent_connection_errors",
                "frequency": 5,
                "time_window": "5m",
                "severity": "high"
            }
        ]
        error_handler._error_aggregator = mock_aggregator
        
        patterns = error_handler.detect_error_patterns()
        
        assert len(patterns) == 1
        assert patterns[0]["pattern"] == "frequent_connection_errors"
        assert patterns[0]["severity"] == "high"


class TestUnifiedErrorHandlerMetrics:
    """统一错误处理器指标测试"""
    
    @pytest.fixture
    def error_handler_with_metrics(self):
        """创建带指标的错误处理器"""
        return UnifiedErrorHandler()
        
    def test_error_handler_records_error_metrics(self, error_handler_with_metrics):
        """测试记录错误指标"""
        error_handler = error_handler_with_metrics
        
        # 模拟指标收集器
        mock_metrics = Mock()
        error_handler._metrics = mock_metrics
        
        error = ConnectionError("连接失败")
        error_handler.handle_error(error)
        
        # 验证指标记录
        mock_metrics.increment.assert_called()
        mock_metrics.histogram.assert_called()
        
    def test_error_handler_tracks_recovery_metrics(self, error_handler_with_metrics):
        """测试跟踪恢复指标"""
        error_handler = error_handler_with_metrics
        
        mock_metrics = Mock()
        error_handler._metrics = mock_metrics
        
        # 模拟成功恢复
        error_handler._record_recovery_success("ConnectionError")
        
        mock_metrics.increment.assert_called_with(
            "error_recovery_success",
            tags={"error_type": "ConnectionError"}
        )
        
        # 模拟恢复失败
        error_handler._record_recovery_failure("ConnectionError")
        
        mock_metrics.increment.assert_called_with(
            "error_recovery_failure", 
            tags={"error_type": "ConnectionError"}
        )
        
    def test_error_handler_measures_error_handling_time(self, error_handler_with_metrics):
        """测试测量错误处理时间"""
        error_handler = error_handler_with_metrics
        
        mock_metrics = Mock()
        error_handler._metrics = mock_metrics
        
        error = ConnectionError("连接失败")
        
        with error_handler._measure_handling_time():
            error_handler.handle_error(error)
            
        # 验证时间测量
        mock_metrics.histogram.assert_called()


class TestUnifiedErrorHandlerConfiguration:
    """统一错误处理器配置测试"""
    
    def test_error_handler_custom_error_handlers(self):
        """测试自定义错误处理器"""
        def custom_connection_handler(error, context):
            return {
                "handled": True,
                "action": "reconnect",
                "delay": 5.0
            }
            
        config = {
            "custom_handlers": {
                "ConnectionError": custom_connection_handler
            }
        }
        
        error_handler = UnifiedErrorHandler(config)
        
        error = ConnectionError("连接失败")
        result = error_handler.handle_error(error)
        
        assert result.handled is True
        assert result.action == "reconnect"
        
    def test_error_handler_error_filtering(self):
        """测试错误过滤"""
        config = {
            "ignore_errors": ["DeprecationWarning"],
            "severity_threshold": ErrorSeverity.MEDIUM
        }
        
        error_handler = UnifiedErrorHandler(config)
        
        # 测试被忽略的错误
        ignored_error = DeprecationWarning("已弃用的功能")
        result = error_handler.handle_error(ignored_error)
        
        assert result.ignored is True
        
        # 测试低严重性错误
        low_severity_error = MarketPrismError("低严重性错误", severity=ErrorSeverity.LOW)
        result = error_handler.handle_error(low_severity_error)
        
        assert result.ignored is True
        
    def test_error_handler_notification_config(self):
        """测试通知配置"""
        config = {
            "notifications": {
                "enabled": True,
                "channels": ["email", "slack"],
                "severity_threshold": ErrorSeverity.HIGH
            }
        }
        
        error_handler = UnifiedErrorHandler(config)
        
        # 模拟通知发送器
        mock_notifier = Mock()
        error_handler._notifier = mock_notifier
        
        high_severity_error = MarketPrismError(
            "严重错误", 
            severity=ErrorSeverity.CRITICAL
        )
        
        error_handler.handle_error(high_severity_error)
        
        # 验证通知发送
        mock_notifier.send_notification.assert_called_once()


@pytest.mark.integration
class TestUnifiedErrorHandlerIntegration:
    """统一错误处理器集成测试"""
    
    async def test_error_handler_full_workflow(self):
        """测试错误处理器完整工作流"""
        config = {
            "enable_recovery": True,
            "max_retry_attempts": 2,
            "retry_delay": 0.1,  # 快速测试
            "log_errors": True
        }
        
        error_handler = UnifiedErrorHandler(config)
        
        # 模拟组件
        mock_recovery = AsyncMock()
        mock_aggregator = Mock()
        mock_metrics = Mock()
        
        error_handler._recovery_manager = mock_recovery
        error_handler._error_aggregator = mock_aggregator
        error_handler._metrics = mock_metrics
        
        # 模拟恢复成功
        mock_recovery.attempt_recovery.return_value = True
        
        # 处理错误
        error = ConnectionError("连接失败")
        context = ErrorContext(component="data_collector", operation="connect")
        
        result = await error_handler.handle_error_with_recovery(error, context)
        
        # 验证完整流程
        assert result.handled is True
        assert result.recovered is True
        mock_aggregator.add_error.assert_called_once()
        mock_metrics.increment.assert_called()
        mock_recovery.attempt_recovery.assert_called_once()
        
    async def test_error_handler_cascading_failures(self):
        """测试级联故障处理"""
        error_handler = UnifiedErrorHandler()
        
        # 模拟级联故障
        primary_error = ConnectionError("主要连接失败")
        secondary_error = DataValidationError("数据验证失败")
        
        # 处理级联错误
        primary_result = error_handler.handle_error(primary_error)
        secondary_result = error_handler.handle_error(
            secondary_error, 
            related_error=primary_result.error_id
        )
        
        # 验证级联关系
        assert secondary_result.related_error_id == primary_result.error_id
        
    async def test_error_handler_system_health_impact(self):
        """测试错误对系统健康的影响"""
        error_handler = UnifiedErrorHandler()
        
        # 模拟健康检查器
        mock_health_checker = Mock()
        error_handler._health_checker = mock_health_checker
        
        # 处理多个严重错误
        critical_errors = [
            MarketPrismError("严重错误1", severity=ErrorSeverity.CRITICAL),
            MarketPrismError("严重错误2", severity=ErrorSeverity.CRITICAL),
            MarketPrismError("严重错误3", severity=ErrorSeverity.CRITICAL)
        ]
        
        for error in critical_errors:
            error_handler.handle_error(error)
            
        # 检查系统健康状态
        health_status = error_handler.get_system_health_status()
        
        assert health_status["status"] in ["degraded", "unhealthy"]
        assert health_status["critical_error_count"] == 3
