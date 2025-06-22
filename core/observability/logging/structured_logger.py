"""
结构化日志记录器

提供结构化日志记录功能，支持上下文管理和多格式输出。
"""

from datetime import datetime, timezone
import os
import sys
import json
import time
import uuid
import threading
import traceback
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from contextlib import contextmanager

from .log_config import LogConfig, LogLevel, LogFormat, LogOutput
from .log_formatters import JSONFormatter, ColoredFormatter, StructuredFormatter


@dataclass
class LogContext:
    """日志上下文"""
    correlation_id: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    component: Optional[str] = None
    operation: Optional[str] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        context = {}
        
        if self.correlation_id:
            context['correlation_id'] = self.correlation_id
        if self.request_id:
            context['request_id'] = self.request_id
        if self.user_id:
            context['user_id'] = self.user_id
        if self.session_id:
            context['session_id'] = self.session_id
        if self.component:
            context['component'] = self.component
        if self.operation:
            context['operation'] = self.operation
        if self.exchange:
            context['exchange'] = self.exchange
        if self.symbol:
            context['symbol'] = self.symbol
        
        context.update(self.custom_fields)
        return context
    
    def merge(self, other: 'LogContext') -> 'LogContext':
        """合并上下文"""
        merged = LogContext(
            correlation_id=other.correlation_id or self.correlation_id,
            request_id=other.request_id or self.request_id,
            user_id=other.user_id or self.user_id,
            session_id=other.session_id or self.session_id,
            component=other.component or self.component,
            operation=other.operation or self.operation,
            exchange=other.exchange or self.exchange,
            symbol=other.symbol or self.symbol,
            custom_fields={**self.custom_fields, **other.custom_fields}
        )
        return merged


class StructuredLogger:
    """结构化日志记录器
    
    提供结构化日志记录、上下文管理和多格式输出功能。
    """
    
    def __init__(self, name: str, config: LogConfig = None):
        self.name = name
        self.config = config or LogConfig.default_console_config()
        
        # 上下文管理
        self._context_stack: List[LogContext] = []
        self._context_lock = threading.Lock()
        
        # 线程本地存储
        self._local = threading.local()
        
        # 格式化器
        self._formatters = {
            LogFormat.JSON: JSONFormatter(),
            LogFormat.COLORED: ColoredFormatter(),
            LogFormat.STRUCTURED: StructuredFormatter()
        }
        
        # 性能统计
        self._log_count = 0
        self._start_time = time.time()
    
    @property
    def current_context(self) -> LogContext:
        """获取当前上下文"""
        # 首先检查线程本地存储
        if hasattr(self._local, 'context'):
            return self._local.context
        
        # 然后检查上下文栈
        with self._context_lock:
            if self._context_stack:
                return self._context_stack[-1]
        
        return LogContext()
    
    def set_context(self, context: LogContext):
        """设置当前线程的上下文"""
        self._local.context = context
    
    @contextmanager
    def context(self, **kwargs):
        """上下文管理器"""
        # 创建新上下文
        new_context = LogContext(**kwargs)
        
        # 与当前上下文合并
        current = self.current_context
        merged_context = current.merge(new_context)
        
        # 保存旧上下文
        old_context = getattr(self._local, 'context', None)
        
        try:
            # 设置新上下文
            self.set_context(merged_context)
            yield merged_context
        finally:
            # 恢复旧上下文
            if old_context:
                self.set_context(old_context)
            elif hasattr(self._local, 'context'):
                delattr(self._local, 'context')
    
    def push_context(self, context: LogContext):
        """推入上下文到栈"""
        with self._context_lock:
            self._context_stack.append(context)
    
    def pop_context(self) -> Optional[LogContext]:
        """从栈弹出上下文"""
        with self._context_lock:
            if self._context_stack:
                return self._context_stack.pop()
        return None
    
    def _should_log(self, level: LogLevel) -> bool:
        """判断是否应该记录日志"""
        return level.numeric_level >= self.config.global_level.numeric_level
    
    def _create_log_record(self, 
                          level: LogLevel,
                          message: str,
                          extra: Dict[str, Any] = None,
                          exception: Exception = None) -> Dict[str, Any]:
        """创建日志记录"""
        now = datetime.now(timezone.utc)
        
        # 基本记录信息
        record = {
            'timestamp': now.isoformat(),
            'level': level.value,
            'logger': self.name,
            'message': message,
            'thread_id': threading.get_ident()
        }
        
        # 添加进程信息
        if self.config.include_process_id:
            record['process_id'] = os.getpid()
        
        # 添加主机名
        if self.config.include_hostname:
            import socket
            record['hostname'] = socket.gethostname()
        
        # 添加调用者信息
        if self.config.include_caller_info:
            frame = sys._getframe(3)  # 跳过logger内部调用
            record['caller'] = {
                'filename': frame.f_code.co_filename,
                'line_number': frame.f_lineno,
                'function': frame.f_code.co_name
            }
        
        # 添加上下文
        context = self.current_context
        if context:
            record.update(context.to_dict())
        
        # 添加额外字段
        if extra:
            record.update(extra)
        
        # 添加异常信息
        if exception:
            record['exception'] = {
                'type': type(exception).__name__,
                'message': str(exception),
                'traceback': traceback.format_exc()
            }
        
        return record
    
    def _format_record(self, record: Dict[str, Any], format_type: LogFormat) -> str:
        """格式化日志记录"""
        formatter = self._formatters.get(format_type, self._formatters[LogFormat.STRUCTURED])
        return formatter.format(record)
    
    def _output_log(self, record: Dict[str, Any]):
        """输出日志"""
        level = LogLevel(record['level'])
        
        for output_config in self.config.outputs:
            if not output_config.enabled:
                continue
            
            if level.numeric_level < output_config.level.numeric_level:
                continue
            
            # 格式化记录
            formatted = self._format_record(record, output_config.format_type)
            
            # 输出到不同目标
            if output_config.output_type == LogOutput.CONSOLE:
                print(formatted, file=sys.stdout if level.numeric_level < LogLevel.ERROR.numeric_level else sys.stderr)
            
            elif output_config.output_type == LogOutput.FILE:
                if output_config.filename:
                    # 确保目录存在
                    os.makedirs(os.path.dirname(output_config.filename), exist_ok=True)
                    
                    with open(output_config.filename, 'a', encoding='utf-8') as f:
                        f.write(formatted + '\n')
            
            # 其他输出类型（如Elasticsearch、Kafka）可在后续扩展
    
    def log(self, level: LogLevel, message: str, **kwargs):
        """记录日志"""
        if not self._should_log(level):
            return
        
        extra = kwargs.pop('extra', {})
        exception = kwargs.pop('exception', None)
        
        # 将剩余的kwargs作为extra字段
        extra.update(kwargs)
        
        # 创建日志记录
        record = self._create_log_record(level, message, extra, exception)
        
        # 输出日志
        self._output_log(record)
        
        # 更新统计
        self._log_count += 1
    
    def trace(self, message: str, **kwargs):
        """记录TRACE级别日志"""
        self.log(LogLevel.TRACE, message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """记录DEBUG级别日志"""
        self.log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """记录INFO级别日志"""
        self.log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录WARNING级别日志"""
        self.log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """记录ERROR级别日志"""
        self.log(LogLevel.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """记录CRITICAL级别日志"""
        self.log(LogLevel.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, exception: Exception = None, **kwargs):
        """记录异常日志"""
        if exception is None:
            exception = sys.exc_info()[1]
        
        kwargs['exception'] = exception
        self.log(LogLevel.ERROR, message, **kwargs)
    
    def performance(self, operation: str, duration: float, **kwargs):
        """记录性能日志"""
        self.info(
            f"Performance: {operation}",
            operation=operation,
            duration=duration,
            performance=True,
            **kwargs
        )
    
    def audit(self, action: str, resource: str, **kwargs):
        """记录审计日志"""
        self.info(
            f"Audit: {action} on {resource}",
            action=action,
            resource=resource,
            audit=True,
            **kwargs
        )
    
    def security(self, event: str, severity: str = "medium", **kwargs):
        """记录安全日志"""
        level = LogLevel.WARNING if severity == "medium" else LogLevel.ERROR
        self.log(
            level,
            f"Security: {event}",
            event=event,
            severity=severity,
            security=True,
            **kwargs
        )
    
    def business(self, event: str, **kwargs):
        """记录业务日志"""
        self.info(
            f"Business: {event}",
            event=event,
            business=True,
            **kwargs
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取日志统计信息"""
        uptime = time.time() - self._start_time
        
        return {
            "logger_name": self.name,
            "log_count": self._log_count,
            "uptime_seconds": uptime,
            "logs_per_second": self._log_count / uptime if uptime > 0 else 0,
            "current_context": self.current_context.to_dict(),
            "context_stack_depth": len(self._context_stack)
        }


# 全局日志器实例
_loggers: Dict[str, StructuredLogger] = {}
_logger_lock = threading.Lock()


def get_logger(name: str, config: LogConfig = None) -> StructuredLogger:
    """获取或创建日志器实例"""
    with _logger_lock:
        if name not in _loggers:
            _loggers[name] = StructuredLogger(name, config)
        return _loggers[name]


def configure_logging(config: LogConfig):
    """配置全局日志系统"""
    with _logger_lock:
        # 更新所有现有日志器的配置
        for logger in _loggers.values():
            logger.config = config


# 别名函数，保持向后兼容
def get_structured_logger(name: str, config: LogConfig = None) -> StructuredLogger:
    """获取结构化日志器实例（别名函数）"""
    return get_logger(name, config)