"""
MarketPrism 统一日志系统

提供企业级统一日志记录、智能去重、级别优化和性能监控功能。
"""

from datetime import datetime, timezone

# 核心统一日志系统
from .unified_log_manager import (
    UnifiedLogManager,
    ManagedLogger,
    LogConfiguration,
    get_managed_logger,
    configure_global_logging,
    get_global_log_statistics,
    shutdown_global_logging
)

from .unified_logger import (
    UnifiedLogger,
    LoggerFactory,
    ComponentType,
    OperationType,
    LogLevel as UnifiedLogLevel,
    LogContext
)

# 日志优化和管理
from .level_optimizer import (
    log_level_optimizer,
    LogLevel,
    BusinessCriticality,
    Environment,
    optimized_log_level,
    adaptive_log_manager
)

from .deduplication import (
    log_deduplicator,
    LogEntry,
    DeduplicationStrategy,
    with_deduplication
)

from .log_standards import (
    LogMessageTemplate,
    PerformanceMetric,
    BusinessEventLogger,
    StandardizedErrorHandler,
    LogFrequencyController,
    with_frequency_control,
    with_timing
)

# 传统日志系统（向后兼容）
from .log_config import LogConfig, LogFormat, LogOutput
from .structured_logger import StructuredLogger, get_logger, configure_logging, get_structured_logger
from .log_formatters import JSONFormatter, ColoredFormatter, StructuredFormatter

__all__ = [
    # 统一日志系统 - 推荐使用
    "UnifiedLogManager", "ManagedLogger", "LogConfiguration",
    "get_managed_logger", "configure_global_logging", "get_global_log_statistics", "shutdown_global_logging",
    "UnifiedLogger", "LoggerFactory", "ComponentType", "OperationType", "UnifiedLogLevel", "LogContext",

    # 优化和管理工具
    "log_level_optimizer", "LogLevel", "BusinessCriticality", "Environment", "optimized_log_level", "adaptive_log_manager",
    "log_deduplicator", "LogEntry", "DeduplicationStrategy", "with_deduplication",
    "LogMessageTemplate", "PerformanceMetric", "BusinessEventLogger", "StandardizedErrorHandler",
    "LogFrequencyController", "with_frequency_control", "with_timing",

    # 传统系统（向后兼容）
    "LogConfig", "LogFormat", "LogOutput",
    "StructuredLogger", "get_logger", "configure_logging", "get_structured_logger",
    "JSONFormatter", "ColoredFormatter", "StructuredFormatter"
]
# 日志聚合和分析功能
try:
    from .log_aggregator import LogAggregator, LogEntry, LogPattern
    from .log_analyzer import LogAnalyzer
except ImportError:
    # 组件可能未安装
    LogAggregator = None
    LogEntry = None
    LogPattern = None
    LogAnalyzer = None
