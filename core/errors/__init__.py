"""
MarketPrism 统一错误处理系统

提供企业级错误处理、恢复、监控和审计功能。
"""

from datetime import datetime, timezone
from .exceptions import (
    MarketPrismError,
    MarketPrismError as BaseMarketPrismError,  # Alias for backward compatibility
    ConfigurationError,
    ValidationError,
    NetworkError,
    StorageError,
    DataError,
    ExchangeError,
    MonitoringError,
    SystemError,
    ErrorCollection
)
from .error_categories import ErrorCategory, ErrorSeverity, ErrorType, RecoveryStrategy
from .unified_error_handler import UnifiedErrorHandler, get_global_error_handler
from .error_context import ErrorContext, ErrorMetadata
from .recovery_manager import ErrorRecoveryManager
from .error_aggregator import (
    ErrorAggregator,
    ErrorPattern,
    ErrorStatistics,
    TimeWindow,
    TimeSeriesData
)


__all__ = [
    # Core Exceptions
    "MarketPrismError",
    "BaseMarketPrismError",
    "ConfigurationError",
    "ValidationError",
    "NetworkError",
    "StorageError",
    "DataError",
    "ExchangeError",
    "MonitoringError",
    "SystemError",
    "ErrorCollection",
    
    # Enums and Categories
    "ErrorCategory",
    "ErrorSeverity",
    "ErrorType",
    "RecoveryStrategy",
    
    # Handlers and Managers
    "UnifiedErrorHandler",
    "get_global_error_handler",
    "ErrorContext",
    "ErrorMetadata",
    "ErrorRecoveryManager",

    # Aggregation
    "ErrorAggregator",
    "ErrorPattern",
    "ErrorStatistics",
    "TimeWindow",
    "TimeSeriesData"
]
