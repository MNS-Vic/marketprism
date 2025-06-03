"""
MarketPrism 统一错误处理系统

提供企业级错误处理、恢复、监控和审计功能。
"""

from .exceptions import MarketPrismError, ErrorCollection
from .error_categories import ErrorCategory, ErrorSeverity, ErrorType
from .unified_error_handler import UnifiedErrorHandler, get_global_error_handler
from .error_context import ErrorContext, ErrorMetadata
from .recovery_manager import ErrorRecoveryManager

__all__ = [
    "MarketPrismError", "ErrorCollection", "ErrorCategory", 
    "ErrorSeverity", "ErrorType", "UnifiedErrorHandler", 
    "get_global_error_handler", "ErrorContext", "ErrorMetadata",
    "ErrorRecoveryManager"
]
# 错误聚合功能
from .error_aggregator import (
    ErrorAggregator,
    ErrorPattern,
    ErrorStatistics,
    TimeWindow,
    TimeSeriesData
)
