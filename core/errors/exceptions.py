"""
MarketPrism统一异常定义

定义系统中所有自定义异常类，提供结构化的异常信息和错误上下文。
所有异常都继承自MarketPrismError基类，便于统一处理和分析。
"""

from datetime import datetime, timezone
import traceback
from typing import Dict, Any, Optional, List

from .error_categories import ErrorCategory, ErrorSeverity, ErrorType, RecoveryStrategy


class MarketPrismError(Exception):
    """MarketPrism基础异常类
    
    所有MarketPrism自定义异常的基类，提供统一的异常信息结构。
    包含错误分类、严重程度、恢复策略等元信息。
    """
    
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recovery_strategy: RecoveryStrategy = RecoveryStrategy.LOG_ONLY,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        error_code: Optional[str] = None,
        user_message: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message)
        
        self.message = message
        self.error_type = error_type
        self.category = category
        self.severity = severity
        self.recovery_strategy = recovery_strategy
        self.context = context or {}
        self.cause = cause
        self.error_code = error_code
        self.user_message = user_message or message
        self.timestamp = datetime.now(timezone.utc)
        self.additional_data = kwargs
        
        # 捕获堆栈信息
        self.stack_trace = traceback.format_exc()
        self.stack_frames = traceback.extract_tb(self.__traceback__)
    
    def to_dict(self) -> Dict[str, Any]:
        """将异常信息转换为字典格式"""
        return {
            "message": self.message,
            "error_type": self.error_type.name,
            "category": self.category.value,
            "severity": self.severity.value,
            "recovery_strategy": self.recovery_strategy.value,
            "context": self.context,
            "error_code": self.error_code,
            "user_message": self.user_message,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace,
            "cause": str(self.cause) if self.cause else None,
            "additional_data": self.additional_data
        }
    
    def get_context_value(self, key: str, default: Any = None) -> Any:
        """获取上下文信息"""
        return self.context.get(key, default)
    
    def add_context(self, key: str, value: Any):
        """添加上下文信息"""
        self.context[key] = value
    
    def is_retryable(self) -> bool:
        """判断是否可重试"""
        retryable_strategies = {
            RecoveryStrategy.RETRY,
            RecoveryStrategy.EXPONENTIAL_BACKOFF,
            RecoveryStrategy.CIRCUIT_BREAKER
        }
        return self.recovery_strategy in retryable_strategies
    
    def is_critical(self) -> bool:
        """判断是否为严重错误"""
        return self.severity == ErrorSeverity.CRITICAL


class ConfigurationError(MarketPrismError):
    """配置相关错误"""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        expected_type: Optional[str] = None,
        **kwargs
    ):
        context = {
            "config_key": config_key,
            "config_value": config_value,
            "expected_type": expected_type
        }
        if "context" in kwargs:
            context.update(kwargs.pop("context"))
        
        super().__init__(
            message=message,
            error_type=ErrorType.INVALID_CONFIG,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.HIGH,
            recovery_strategy=RecoveryStrategy.MANUAL_INTERVENTION,
            context=context,
            **kwargs
        )


class ValidationError(MarketPrismError):
    """数据验证错误"""
    
    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        field_value: Optional[Any] = None,
        validation_rule: Optional[str] = None,
        field: Optional[str] = None,
        expected_type: Optional[str] = None,
        **kwargs
    ):
        context = {
            "field_name": field_name,
            "field_value": field_value,
            "validation_rule": validation_rule
        }
        context.update(kwargs.get("context", {}))
        
        self.field = field or field_name
        self.expected_type = expected_type
        self.actual_value = field_value  # 添加actual_value属性
        
        super().__init__(
            message=message,
            error_type=ErrorType.CONFIG_VALIDATION_FAILED,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.LOG_ONLY,
            context=context,
            **kwargs
        )


class NetworkError(MarketPrismError):
    """网络相关错误"""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs
    ):
        context = {
            "url": url,
            "status_code": status_code,
            "timeout": timeout
        }
        if "context" in kwargs:
            context.update(kwargs.pop("context"))
        
        # 根据具体情况确定错误类型
        error_type = ErrorType.CONNECTION_TIMEOUT
        if status_code == 403:
            error_type = ErrorType.API_KEY_INVALID
        elif status_code == 429:
            error_type = ErrorType.API_RATE_LIMITED
        
        # 设置url属性
        self.url = url
        self.status_code = status_code  # 添加status_code属性
        
        super().__init__(
            message=message,
            error_type=error_type,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            context=context,
            **kwargs
        )


class DataError(MarketPrismError):
    """数据相关错误"""
    
    def __init__(
        self,
        message: str,
        data_type: Optional[str] = None,
        data_source: Optional[str] = None,
        expected_format: Optional[str] = None,
        validation_errors: Optional[List[str]] = None,  # 添加validation_errors参数
        **kwargs
    ):
        context = {
            "data_type": data_type,
            "data_source": data_source,
            "expected_format": expected_format
        }
        if "context" in kwargs:
            context.update(kwargs.pop("context"))
        
        # 设置data_source属性
        self.data_source = data_source
        self.validation_errors = validation_errors or []  # 添加validation_errors属性
        
        super().__init__(
            message=message,
            error_type=ErrorType.DATA_FORMAT_INVALID,
            category=ErrorCategory.DATA_PROCESSING,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.LOG_ONLY,
            context=context,
            **kwargs
        )


class StorageError(MarketPrismError):
    """存储系统错误"""
    
    def __init__(
        self,
        message: str,
        storage_type: Optional[str] = None,
        operation: Optional[str] = None,
        table_name: Optional[str] = None,
        **kwargs
    ):
        context = {
            "storage_type": storage_type,
            "operation": operation,
            "table_name": table_name
        }
        context.update(kwargs.get("context", {}))
        
        super().__init__(
            message=message,
            error_type=ErrorType.DATABASE_CONNECTION_FAILED,
            category=ErrorCategory.STORAGE,
            severity=ErrorSeverity.HIGH,
            recovery_strategy=RecoveryStrategy.RETRY,
            context=context,
            **kwargs
        )


class ExchangeError(MarketPrismError):
    """交易所接口错误"""
    
    def __init__(
        self,
        message: str,
        exchange_name: Optional[str] = None,
        symbol: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        **kwargs
    ):
        context = {
            "exchange_name": exchange_name,
            "symbol": symbol,
            "api_endpoint": api_endpoint
        }
        context.update(kwargs.get("context", {}))
        
        super().__init__(
            message=message,
            error_type=ErrorType.API_RESPONSE_INVALID,
            category=ErrorCategory.EXCHANGE,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
            context=context,
            **kwargs
        )


class MonitoringError(MarketPrismError):
    """监控系统错误"""
    
    def __init__(
        self,
        message: str,
        metric_name: Optional[str] = None,
        component: Optional[str] = None,
        **kwargs
    ):
        context = {
            "metric_name": metric_name,
            "component": component
        }
        context.update(kwargs.get("context", {}))
        
        super().__init__(
            message=message,
            error_type=ErrorType.UNKNOWN_ERROR,
            category=ErrorCategory.MONITORING,
            severity=ErrorSeverity.LOW,
            recovery_strategy=RecoveryStrategy.LOG_ONLY,
            context=context,
            **kwargs
        )


class SystemError(MarketPrismError):
    """系统级错误"""
    
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        current_usage: Optional[float] = None,
        limit: Optional[float] = None,
        **kwargs
    ):
        context = {
            "resource_type": resource_type,
            "current_usage": current_usage,
            "limit": limit
        }
        context.update(kwargs.get("context", {}))
        
        # 根据资源类型确定错误类型
        error_type = ErrorType.UNKNOWN_ERROR
        if resource_type == "memory":
            error_type = ErrorType.MEMORY_EXHAUSTED
        elif resource_type == "cpu":
            error_type = ErrorType.CPU_OVERLOAD
        
        super().__init__(
            message=message,
            error_type=error_type,
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.CRITICAL,
            recovery_strategy=RecoveryStrategy.RESTART_COMPONENT,
            context=context,
            **kwargs
        )


class ErrorCollection:
    """错误集合类
    
    用于收集和管理一批相关的错误，支持批量处理和分析。
    """
    
    def __init__(self, errors: Optional[List[MarketPrismError]] = None):
        self.errors = errors or []
        self.created_at = datetime.now(timezone.utc)
    
    def add_error(self, error: MarketPrismError):
        """添加错误"""
        self.errors.append(error)
    
    def get_errors_by_category(self, category: ErrorCategory) -> List[MarketPrismError]:
        """按分类获取错误"""
        return [error for error in self.errors if error.category == category]
    
    def get_errors_by_severity(self, severity: ErrorSeverity) -> List[MarketPrismError]:
        """按严重程度获取错误"""
        return [error for error in self.errors if error.severity == severity]
    
    def get_critical_errors(self) -> List[MarketPrismError]:
        """获取严重错误"""
        return self.get_errors_by_severity(ErrorSeverity.CRITICAL)
    
    def has_critical_errors(self) -> bool:
        """是否包含严重错误"""
        return len(self.get_critical_errors()) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """获取错误摘要"""
        total = len(self.errors)
        if total == 0:
            return {"total": 0}
        
        by_category = {}
        by_severity = {}
        
        for error in self.errors:
            # 按分类统计
            category = error.category.value
            by_category[category] = by_category.get(category, 0) + 1
            
            # 按严重程度统计
            severity = error.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        return {
            "total": total,
            "by_category": by_category,
            "by_severity": by_severity,
            "has_critical": self.has_critical_errors(),
            "created_at": self.created_at.isoformat()
        }
    
    def to_dict_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表"""
        return [error.to_dict() for error in self.errors]