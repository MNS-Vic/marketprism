"""
统一错误处理器

提供统一的错误处理、记录、恢复和告警机制。
与监控系统集成，实现错误指标自动收集和实时告警。
"""

from datetime import datetime, timezone
import uuid
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from .exceptions import MarketPrismError, ErrorCollection
from .error_categories import ErrorCategory, ErrorSeverity, ErrorType, get_global_category_manager
from .error_context import ErrorContext, ErrorMetadata, get_global_context_manager
from .recovery_manager import ErrorRecoveryManager, RecoveryResult


@dataclass
class ErrorHandlerConfig:
    """错误处理器配置"""
    enable_monitoring_integration: bool = True
    enable_automatic_recovery: bool = True
    enable_error_aggregation: bool = True
    max_error_history: int = 10000
    error_retention_days: int = 30
    async_processing: bool = False
    thread_pool_size: int = 4
    enable_detailed_context: bool = True
    enable_stack_capture: bool = True
    
    # 告警配置
    enable_alerting: bool = True
    critical_error_immediate_alert: bool = True
    error_rate_threshold: float = 10.0  # 每分钟错误数阈值
    alert_cooldown_seconds: int = 300   # 告警冷却期
    
    # 日志配置
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    enable_structured_logging: bool = True


class ErrorHandler:
    """错误处理器
    
    处理单个错误的记录、分析和恢复。
    """
    
    def __init__(self, config: ErrorHandlerConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.context_manager = get_global_context_manager()
        self.category_manager = get_global_category_manager()
        self.recovery_manager = ErrorRecoveryManager()
        
        # 监控集成
        self.metrics_manager = None
        if config.enable_monitoring_integration:
            try:
                from ..monitoring import get_global_manager
                self.metrics_manager = get_global_manager()
                self._register_error_metrics()
            except ImportError:
                self.logger.warning("监控系统未启用，跳过监控集成")
    
    def _register_error_metrics(self):
        """注册错误相关指标"""
        if not self.metrics_manager:
            return
        
        from ..monitoring import MetricType, MetricCategory
        
        # 错误计数指标
        self.metrics_manager.registry.register_custom_metric(
            "errors_total",
            MetricType.COUNTER,
            MetricCategory.ERROR,
            "系统错误总数",
            labels=["category", "severity", "error_type", "component"]
        )
        
        # 错误处理时间指标
        self.metrics_manager.registry.register_custom_metric(
            "error_handling_duration_seconds",
            MetricType.HISTOGRAM,
            MetricCategory.PERFORMANCE,
            "错误处理耗时",
            labels=["category", "recovery_strategy"]
        )
        
        # 恢复成功率指标
        self.metrics_manager.registry.register_custom_metric(
            "error_recovery_success_rate",
            MetricType.GAUGE,
            MetricCategory.RELIABILITY,
            "错误恢复成功率",
            labels=["category", "recovery_strategy"]
        )
    
    def handle_error(self, 
                    error: Union[Exception, MarketPrismError],
                    capture_context: bool = True) -> str:
        """处理错误
        
        Args:
            error: 要处理的错误
            capture_context: 是否捕获上下文信息
            
        Returns:
            错误ID
        """
        start_time = datetime.now(timezone.utc)
        
        # 转换为MarketPrismError
        if not isinstance(error, MarketPrismError):
            error = self._convert_to_marketprism_error(error)
        
        # 生成错误ID
        error_id = str(uuid.uuid4())
        
        # 创建错误元数据
        metadata = ErrorMetadata(
            error_id=error_id,
            first_occurrence=start_time,
            last_occurrence=start_time
        )
        
        # 捕获错误上下文
        error_context = None
        if capture_context and self.config.enable_detailed_context:
            error_context = self.context_manager.create_error_context(
                capture_system=True,
                tb=error.__traceback__
            )
            error_context.set_error_metadata(metadata)
        
        # 记录错误指标
        self._record_error_metrics(error, error_context)
        
        # 记录日志
        self._log_error(error, error_context)
        
        # 尝试错误恢复
        recovery_result = None
        if self.config.enable_automatic_recovery:
            recovery_result = self._attempt_recovery(error)
        
        # 发送告警
        if self.config.enable_alerting:
            self._send_alert(error, error_context, recovery_result)
        
        # 计算处理时间
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        self._record_processing_metrics(error, processing_time)
        
        return error_id
    
    def _convert_to_marketprism_error(self, error: Exception) -> MarketPrismError:
        """将普通异常转换为MarketPrismError"""
        error_message = str(error)
        error_type = type(error).__name__
        
        # 根据异常类型映射到MarketPrismError
        if isinstance(error, ConnectionError):
            from .exceptions import NetworkError
            return NetworkError(
                message=error_message,
                cause=error
            )
        elif isinstance(error, ValueError):
            from .exceptions import ValidationError
            return ValidationError(
                message=error_message,
                cause=error
            )
        elif isinstance(error, FileNotFoundError):
            from .exceptions import ConfigurationError
            return ConfigurationError(
                message=error_message,
                cause=error
            )
        else:
            # 默认转换
            return MarketPrismError(
                message=error_message,
                error_type=ErrorType.UNKNOWN_ERROR,
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.MEDIUM,
                cause=error
            )
    
    def _record_error_metrics(self, error: MarketPrismError, context: Optional[ErrorContext]):
        """记录错误指标"""
        if not self.metrics_manager:
            return
        
        try:
            # 获取组件信息
            component = "unknown"
            if context and context.business_context:
                component = context.business_context.component or "unknown"
            
            # 记录错误计数
            self.metrics_manager.increment(
                "errors_total",
                1,
                {
                    "category": error.category.value,
                    "severity": error.severity.value,
                    "error_type": error.error_type.name,
                    "component": component
                }
            )
            
        except Exception as e:
            self.logger.error(f"记录错误指标失败: {e}")
    
    def _log_error(self, error: MarketPrismError, context: Optional[ErrorContext]):
        """记录错误日志"""
        try:
            log_data = {
                "error_id": context.error_metadata.error_id if context and context.error_metadata else "unknown",
                "message": error.message,
                "category": error.category.value,
                "severity": error.severity.value,
                "error_type": error.error_type.name,
                "recovery_strategy": error.recovery_strategy.value
            }
            
            if context:
                log_data["context_summary"] = context.get_summary()
            
            if self.config.enable_structured_logging:
                extra = {"error_data": log_data}
            else:
                extra = {}
            
            # 根据严重程度选择日志级别
            if error.severity == ErrorSeverity.CRITICAL:
                self.logger.critical(f"严重错误: {error.message}", extra=extra)
            elif error.severity == ErrorSeverity.HIGH:
                self.logger.error(f"高级错误: {error.message}", extra=extra)
            elif error.severity == ErrorSeverity.MEDIUM:
                pass  # 暂时静默中级错误
            else:
                self.logger.info(f"低级错误: {error.message}", extra=extra)
                
        except Exception as e:
            # 确保日志记录不会导致额外错误
            self.logger.error(f"记录错误日志失败: {e}")
    
    def _attempt_recovery(self, error: MarketPrismError) -> Optional[RecoveryResult]:
        """尝试错误恢复"""
        try:
            return self.recovery_manager.attempt_recovery(error)
        except Exception as e:
            self.logger.error(f"错误恢复失败: {e}")
            return None
    
    def _send_alert(self, 
                   error: MarketPrismError,
                   context: Optional[ErrorContext],
                   recovery_result: Optional[RecoveryResult]):
        """发送告警"""
        if not self._should_send_alert(error):
            return
        
        try:
            alert_data = {
                "error_id": context.error_metadata.error_id if context and context.error_metadata else "unknown",
                "severity": error.severity.value,
                "category": error.category.value,
                "message": error.message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "recovery_attempted": recovery_result is not None,
                "recovery_successful": recovery_result.success if recovery_result else False
            }
            
            if context:
                alert_data["context"] = context.get_summary()
            
            # 这里可以集成各种告警渠道（邮件、短信、钉钉等）
            self.logger.info(f"发送告警: {alert_data}")
            
        except Exception as e:
            self.logger.error(f"发送告警失败: {e}")
    
    def _should_send_alert(self, error: MarketPrismError) -> bool:
        """判断是否应该发送告警"""
        # 严重错误立即告警
        if error.severity == ErrorSeverity.CRITICAL and self.config.critical_error_immediate_alert:
            return True
        
        # 可以根据错误频率、冷却期等条件判断
        # 这里简化处理
        return error.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]
    
    def _record_processing_metrics(self, error: MarketPrismError, processing_time: float):
        """记录处理时间指标"""
        if not self.metrics_manager:
            return
        
        try:
            self.metrics_manager.observe_histogram(
                "error_handling_duration_seconds",
                processing_time,
                {
                    "category": error.category.value,
                    "recovery_strategy": error.recovery_strategy.value
                }
            )
        except Exception as e:
            self.logger.error(f"记录处理时间指标失败: {e}")


class UnifiedErrorHandler:
    """统一错误处理器
    
    系统级别的错误处理协调器，管理错误处理器、错误聚合、统计分析等。
    """
    
    def __init__(self, config: Optional[ErrorHandlerConfig] = None):
        self.config = config or ErrorHandlerConfig()
        self.logger = logging.getLogger(__name__)
        
        # 初始化组件
        self.error_handler = ErrorHandler(self.config)
        self.error_history: List[MarketPrismError] = []
        self.error_statistics: Dict[str, Any] = {}
        
        # 线程安全锁
        self._lock = Lock()
        
        # 异步处理
        if self.config.async_processing:
            self.executor = ThreadPoolExecutor(max_workers=self.config.thread_pool_size)
        else:
            self.executor = None
        
        # 初始化统计
        self._reset_statistics()
    
    def handle_error(self, 
                    error: Union[Exception, MarketPrismError],
                    async_processing: bool = False) -> str:
        """处理错误
        
        Args:
            error: 要处理的错误
            async_processing: 是否异步处理
            
        Returns:
            错误ID
        """
        if async_processing and self.executor:
            # 异步处理
            future = self.executor.submit(self._handle_error_sync, error)
            return f"async_{uuid.uuid4()}"  # 返回临时ID
        else:
            # 同步处理
            return self._handle_error_sync(error)
    
    def _handle_error_sync(self, error: Union[Exception, MarketPrismError]) -> str:
        """同步处理错误"""
        with self._lock:
            # 处理错误
            error_id = self.error_handler.handle_error(error)
            
            # 添加到历史记录
            if isinstance(error, MarketPrismError):
                self._add_to_history(error)
                self._update_statistics(error)
            
            return error_id
    
    def _add_to_history(self, error: MarketPrismError):
        """添加到错误历史"""
        self.error_history.append(error)
        
        # 限制历史记录大小
        if len(self.error_history) > self.config.max_error_history:
            self.error_history = self.error_history[-self.config.max_error_history:]
    
    def _update_statistics(self, error: MarketPrismError):
        """更新错误统计"""
        now = datetime.now(timezone.utc)
        
        # 总错误数
        self.error_statistics["total_errors"] += 1
        
        # 按分类统计
        category_key = f"category_{error.category.value}"
        self.error_statistics[category_key] = self.error_statistics.get(category_key, 0) + 1
        
        # 按严重程度统计
        severity_key = f"severity_{error.severity.value}"
        self.error_statistics[severity_key] = self.error_statistics.get(severity_key, 0) + 1
        
        # 更新最后错误时间
        self.error_statistics["last_error_time"] = now.isoformat()
        
        # 计算错误率（每分钟）
        minute_ago = now.timestamp() - 60
        recent_errors = [
            e for e in self.error_history
            if e.timestamp.timestamp() > minute_ago
        ]
        self.error_statistics["error_rate_per_minute"] = len(recent_errors)
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        with self._lock:
            return self.error_statistics.copy()
    
    def get_recent_errors(self, limit: int = 10) -> List[MarketPrismError]:
        """获取最近的错误"""
        with self._lock:
            return self.error_history[-limit:] if self.error_history else []
    
    def get_errors_by_category(self, category: ErrorCategory) -> List[MarketPrismError]:
        """按分类获取错误"""
        with self._lock:
            return [error for error in self.error_history if error.category == category]
    
    def get_errors_by_severity(self, severity: ErrorSeverity) -> List[MarketPrismError]:
        """按严重程度获取错误"""
        with self._lock:
            return [error for error in self.error_history if error.severity == severity]
    
    def clear_error_history(self):
        """清除错误历史"""
        with self._lock:
            self.error_history.clear()
            self._reset_statistics()
    
    def _reset_statistics(self):
        """重置统计信息"""
        self.error_statistics = {
            "total_errors": 0,
            "error_rate_per_minute": 0,
            "last_error_time": None,
            "statistics_reset_time": datetime.now(timezone.utc).isoformat()
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取错误处理器健康状态"""
        with self._lock:
            recent_errors = self.get_recent_errors(limit=100)
            critical_errors = [e for e in recent_errors if e.severity == ErrorSeverity.CRITICAL]
            
            return {
                "status": "healthy" if len(critical_errors) == 0 else "degraded",
                "total_errors": len(self.error_history),
                "recent_errors": len(recent_errors),
                "critical_errors": len(critical_errors),
                "error_rate": self.error_statistics.get("error_rate_per_minute", 0),
                "last_error": self.error_statistics.get("last_error_time"),
                "config": {
                    "async_processing": self.config.async_processing,
                    "monitoring_enabled": self.config.enable_monitoring_integration,
                    "recovery_enabled": self.config.enable_automatic_recovery
                }
            }
    
    def shutdown(self):
        """关闭错误处理器"""
        if self.executor:
            self.executor.shutdown(wait=True)


# 全局错误处理器实例
_global_error_handler = None


def get_global_error_handler() -> UnifiedErrorHandler:
    """获取全局错误处理器"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = UnifiedErrorHandler()
    return _global_error_handler


def reset_global_error_handler():
    """重置全局错误处理器（主要用于测试）"""
    global _global_error_handler
    if _global_error_handler:
        _global_error_handler.shutdown()
    _global_error_handler = None