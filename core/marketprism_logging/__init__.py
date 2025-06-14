"""
Logging module - 日志管理模块
提供统一的日志记录、聚合和分析功能
"""
from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional, List

# 导入实际的日志组件
try:
    from core.observability.logging.structured_logger import StructuredLogger
    from core.observability.logging.log_aggregator import LogAggregator
    OBSERVABILITY_LOGGING_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Observability logging不可用: {e}")
    OBSERVABILITY_LOGGING_AVAILABLE = False
    StructuredLogger = None
    LogAggregator = None

logger = logging.getLogger(__name__)

class LogLevel:
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class UnifiedLogAggregator:
    """统一日志聚合器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logs = []
        self.aggregator = None
        self._initialized = False
        
        # 避免递归初始化
        if not self._initialized:
            self._initialized = True
            if OBSERVABILITY_LOGGING_AVAILABLE and LogAggregator:
                try:
                    self.aggregator = LogAggregator()
                    # 避免递归日志
                    if __name__ != 'core.logging':
                        pass  # 避免递归
                except Exception as e:
                    # 避免递归日志  
                    if __name__ != 'core.logging':
                        pass  # 避免递归
    
    def add_log(self, level: str, message: str, **kwargs):
        """添加日志"""
        log_entry = {
            "level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs
        }
        
        self.logs.append(log_entry)
        
        if self.aggregator and hasattr(self.aggregator, 'add_log'):
            try:
                self.aggregator.add_log(level, message, **kwargs)
            except Exception as e:
                self.logger.warning(f"聚合器添加日志失败: {e}")
    
    def get_logs(self, level: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取日志"""
        if self.aggregator and hasattr(self.aggregator, 'get_logs'):
            try:
                return self.aggregator.get_logs(level, limit)
            except Exception:
                pass
        
        # Fallback 实现
        logs = self.logs
        if level:
            logs = [log for log in logs if log.get('level') == level]
        return logs[-limit:]
    
    def clear_logs(self):
        """清除日志"""
        self.logs.clear()
        if self.aggregator and hasattr(self.aggregator, 'clear_logs'):
            try:
                self.aggregator.clear_logs()
            except Exception:
                pass

class UnifiedStructuredLogger:
    """统一结构化日志器"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        self.structured_logger = None
        self._initialized = False
        
        # 避免递归初始化
        if not self._initialized:
            self._initialized = True
            if OBSERVABILITY_LOGGING_AVAILABLE and StructuredLogger:
                try:
                    self.structured_logger = StructuredLogger(name)
                    # 避免递归日志
                    if name != 'core.logging':
                        pass  # 避免递归
                except Exception as e:
                    # 避免递归日志
                    if name != 'core.logging':
                        pass  # 避免递归
    
    def debug(self, message: str, **kwargs):
        """记录debug日志"""
        if self.structured_logger:
            try:
                return self.structured_logger.debug(message, **kwargs)
            except Exception:
                pass
        self.logger.debug(f"{message} {kwargs}")
    
    def info(self, message: str, **kwargs):
        """记录info日志"""
        if self.structured_logger:
            try:
                return self.structured_logger.info(message, **kwargs)
            except Exception:
                pass
        self.logger.info(f"{message} {kwargs}")
    
    def warning(self, message: str, **kwargs):
        """记录warning日志"""
        if self.structured_logger:
            try:
                return self.structured_logger.warning(message, **kwargs)
            except Exception:
                pass
        self.logger.warning(f"{message} {kwargs}")
    
    def error(self, message: str, **kwargs):
        """记录error日志"""
        if self.structured_logger:
            try:
                return self.structured_logger.error(message, **kwargs)
            except Exception:
                pass
        self.logger.error(f"{message} {kwargs}")
    
    def critical(self, message: str, **kwargs):
        """记录critical日志"""
        if self.structured_logger:
            try:
                return self.structured_logger.critical(message, **kwargs)
            except Exception:
                pass
        self.logger.critical(f"{message} {kwargs}")

# 全局实例
_loggers = {}
_global_aggregator = None

def get_structured_logger(name: str) -> UnifiedStructuredLogger:
    """获取结构化日志器"""
    if name not in _loggers:
        _loggers[name] = UnifiedStructuredLogger(name)
    return _loggers[name]

def get_logger(name: str) -> UnifiedStructuredLogger:
    """获取日志器（别名）"""
    return get_structured_logger(name)

def get_log_aggregator() -> UnifiedLogAggregator:
    """获取日志聚合器"""
    global _global_aggregator
    if _global_aggregator is None:
        _global_aggregator = UnifiedLogAggregator()
    return _global_aggregator

# 便捷函数
def log_info(message: str, logger_name: str = "default", **kwargs):
    """记录info日志"""
    logger = get_structured_logger(logger_name)
    logger.info(message, **kwargs)

def log_error(message: str, logger_name: str = "default", **kwargs):
    """记录error日志"""
    logger = get_structured_logger(logger_name)
    logger.error(message, **kwargs)

def log_warning(message: str, logger_name: str = "default", **kwargs):
    """记录warning日志"""
    logger = get_structured_logger(logger_name)
    logger.warning(message, **kwargs)

def log_debug(message: str, logger_name: str = "default", **kwargs):
    """记录debug日志"""
    logger = get_structured_logger(logger_name)
    logger.debug(message, **kwargs)

# 导出所有公共接口
__all__ = [
    'LogLevel',
    'UnifiedLogAggregator',
    'UnifiedStructuredLogger',
    'get_structured_logger',
    'get_logger',
    'get_log_aggregator',
    'log_info',
    'log_error', 
    'log_warning',
    'log_debug',
    'LogAggregator',  # 别名
    'StructuredLogger'  # 别名
]

# 创建别名以保持兼容性
LogAggregator = UnifiedLogAggregator
StructuredLogger = UnifiedStructuredLogger 