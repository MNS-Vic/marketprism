"""
MarketPrism 统一错误处理系统

提供完整的错误处理、恢复、聚合和分析功能。
"""

from .error_categories import (
    ErrorCategory, ErrorSeverity, ErrorType, RecoveryStrategy,
    ErrorDefinition, ErrorCategoryManager
)
from .exceptions import (
    MarketPrismError, ConfigurationError, ValidationError, NetworkError,
    DataError, StorageError, ExchangeError, MonitoringError, SystemError,
    ErrorCollection
)
from .error_context import (
    SystemInfo, RequestContext, BusinessContext, ErrorMetadata
)
from .unified_error_handler import UnifiedErrorHandler
from .recovery_manager import (
    ErrorRecoveryManager, RecoveryResult, RecoveryStatus,
    RetryAction, CircuitBreakerAction, FailoverAction, GracefulDegradationAction
)
from .error_aggregator import (
    ErrorAggregator, ErrorPattern, ErrorStatistics, TimeWindow
)

__all__ = [
    # 错误分类
    'ErrorCategory',
    'ErrorSeverity', 
    'ErrorType',
    'RecoveryStrategy',
    'ErrorDefinition',
    'ErrorCategoryManager',
    
    # 异常定义
    'MarketPrismError',
    'ConfigurationError',
    'ValidationError',
    'NetworkError',
    'DataError',
    'StorageError',
    'ExchangeError',
    'MonitoringError',
    'SystemError',
    'ErrorCollection',
    
    # 上下文管理
    'SystemInfo',
    'RequestContext',
    'BusinessContext',
    'ErrorMetadata',
    
    # 核心处理器
    'UnifiedErrorHandler',
    
    # 恢复管理
    'ErrorRecoveryManager',
    'RecoveryResult',
    'RecoveryStatus',
    'RetryAction',
    'CircuitBreakerAction',
    'FailoverAction',
    'GracefulDegradationAction',
    
    # 错误聚合
    'ErrorAggregator',
    'ErrorPattern',
    'ErrorStatistics',
    'TimeWindow'
]