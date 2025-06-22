"""
MarketPrism 结构化日志系统

提供企业级结构化日志记录、上下文管理和多格式输出功能。
"""

from datetime import datetime, timezone
from .log_config import LogConfig, LogLevel, LogFormat, LogOutput
from .structured_logger import StructuredLogger, LogContext, get_logger, configure_logging, get_structured_logger
from .log_formatters import JSONFormatter, ColoredFormatter, StructuredFormatter

__all__ = [
    "LogConfig", "LogLevel", "LogFormat", "LogOutput",
    "StructuredLogger", "LogContext", "get_logger", "configure_logging", "get_structured_logger",
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
