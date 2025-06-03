"""
MarketPrism 日志中间件

这个模块实现了企业级日志中间件，支持结构化日志、JSON格式、
多种日志级别和灵活的日志配置。

核心功能:
1. 结构化日志：支持结构化日志记录
2. 多种格式：JSON、文本等多种日志格式
3. 日志级别：完整的日志级别支持
4. 请求追踪：请求的完整生命周期日志
5. 性能监控：请求处理时间和性能指标
6. 错误记录：详细的错误日志和堆栈跟踪
"""

import asyncio
import time
import json
import logging
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any, Union
import threading
from datetime import datetime
import sys
import os

from .middleware_framework import (
    BaseMiddleware, MiddlewareConfig, MiddlewareContext, MiddlewareResult,
    MiddlewareType, MiddlewarePriority
)


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogType(Enum):
    """日志类型枚举"""
    REQUEST = "request"                   # 请求日志
    RESPONSE = "response"                 # 响应日志
    ERROR = "error"                       # 错误日志
    PERFORMANCE = "performance"           # 性能日志
    SECURITY = "security"                 # 安全日志
    ACCESS = "access"                     # 访问日志
    SYSTEM = "system"                     # 系统日志


@dataclass
class LogEvent:
    """日志事件"""
    timestamp: float
    level: LogLevel
    type: LogType
    message: str
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    ip_address: str = ""
    method: str = ""
    path: str = ""
    status_code: Optional[int] = None
    processing_time: Optional[float] = None
    user_agent: str = ""
    referer: str = ""
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = datetime.fromtimestamp(self.timestamp).isoformat()
        data['level'] = self.level.value
        data['type'] = self.type.value
        return data


class LogFormatter(ABC):
    """日志格式化器抽象基类"""
    
    @abstractmethod
    def format_log(self, event: LogEvent) -> str:
        """格式化日志"""
        pass


class JSONLogFormatter(LogFormatter):
    """JSON日志格式化器"""
    
    def __init__(self, include_metadata: bool = True, pretty: bool = False):
        self.include_metadata = include_metadata
        self.pretty = pretty
    
    def format_log(self, event: LogEvent) -> str:
        """格式化为JSON"""
        data = event.to_dict()
        
        if not self.include_metadata and 'metadata' in data:
            del data['metadata']
        
        if self.pretty:
            return json.dumps(data, indent=2, ensure_ascii=False)
        else:
            return json.dumps(data, ensure_ascii=False)


class TextLogFormatter(LogFormatter):
    """文本日志格式化器"""
    
    def __init__(self, template: Optional[str] = None):
        self.template = template or (
            "{timestamp} [{level}] {type} - {message} "
            "| request_id={request_id} user_id={user_id} "
            "ip={ip_address} method={method} path={path} "
            "status={status_code} time={processing_time}ms"
        )
    
    def format_log(self, event: LogEvent) -> str:
        """格式化为文本"""
        data = event.to_dict()
        
        # 处理None值
        for key, value in data.items():
            if value is None:
                data[key] = "-"
        
        # 处理时间格式
        if event.processing_time is not None:
            data['processing_time'] = f"{event.processing_time:.2f}"
        
        try:
            return self.template.format(**data)
        except KeyError as e:
            return f"Log format error: missing key {e} in template"


class StructuredLogFormatter(LogFormatter):
    """结构化日志格式化器"""
    
    def __init__(self, key_value_separator: str = "=", pair_separator: str = " "):
        self.kv_sep = key_value_separator
        self.pair_sep = pair_separator
    
    def format_log(self, event: LogEvent) -> str:
        """格式化为结构化文本"""
        data = event.to_dict()
        pairs = []
        
        # 固定字段顺序
        fixed_fields = ['timestamp', 'level', 'type', 'message', 'request_id']
        
        for field in fixed_fields:
            if field in data and data[field] is not None:
                value = data[field]
                if isinstance(value, str) and ' ' in value:
                    value = f'"{value}"'
                pairs.append(f"{field}{self.kv_sep}{value}")
        
        # 其他字段
        for key, value in data.items():
            if key not in fixed_fields and value is not None:
                if isinstance(value, str) and ' ' in value:
                    value = f'"{value}"'
                pairs.append(f"{key}{self.kv_sep}{value}")
        
        return self.pair_sep.join(pairs)


class MiddlewareLogger:
    """中间件日志记录器"""
    
    def __init__(self, formatter: LogFormatter, logger: Optional[logging.Logger] = None):
        self.formatter = formatter
        self.logger = logger or logging.getLogger(__name__)
        self._lock = threading.Lock()
    
    async def log_event(self, event: LogEvent) -> None:
        """记录日志事件"""
        try:
            formatted_log = self.formatter.format_log(event)
            
            # 映射日志级别
            level_map = {
                LogLevel.DEBUG: logging.DEBUG,
                LogLevel.INFO: logging.INFO,
                LogLevel.WARNING: logging.WARNING,
                LogLevel.ERROR: logging.ERROR,
                LogLevel.CRITICAL: logging.CRITICAL,
            }
            
            log_level = level_map.get(event.level, logging.INFO)
            
            with self._lock:
                self.logger.log(log_level, formatted_log)
                
        except Exception as e:
            # 避免日志记录本身出错
            print(f"Logging error: {e}", file=sys.stderr)
    
    def set_formatter(self, formatter: LogFormatter) -> None:
        """设置格式化器"""
        self.formatter = formatter


class RequestLogger:
    """请求日志记录器"""
    
    def __init__(self, middleware_logger: MiddlewareLogger):
        self.logger = middleware_logger
    
    async def log_request_start(self, context: MiddlewareContext) -> None:
        """记录请求开始"""
        event = LogEvent(
            timestamp=context.start_time,
            level=LogLevel.INFO,
            type=LogType.REQUEST,
            message="Request started",
            request_id=context.request.request_id,
            user_id=context.get_user_data('user_id'),
            ip_address=context.request.remote_addr,
            method=context.request.method,
            path=context.request.path,
            user_agent=context.request.user_agent,
            metadata={
                'headers': context.request.headers.to_dict(),
                'query_params': context.request.query_params,
            }
        )
        await self.logger.log_event(event)
    
    async def log_request_end(self, context: MiddlewareContext) -> None:
        """记录请求结束"""
        context.finalize()
        
        event = LogEvent(
            timestamp=context.end_time or time.time(),
            level=LogLevel.INFO,
            type=LogType.RESPONSE,
            message="Request completed",
            request_id=context.request.request_id,
            user_id=context.get_user_data('user_id'),
            ip_address=context.request.remote_addr,
            method=context.request.method,
            path=context.request.path,
            status_code=context.response.status_code if context.response else None,
            processing_time=context.processing_time,
            metadata={
                'response_headers': context.response.headers.to_dict() if context.response else {},
                'middleware_data': context.middleware_data,
            }
        )
        await self.logger.log_event(event)


class ResponseLogger:
    """响应日志记录器"""
    
    def __init__(self, middleware_logger: MiddlewareLogger):
        self.logger = middleware_logger
    
    async def log_response(self, context: MiddlewareContext, status_code: int) -> None:
        """记录响应"""
        level = LogLevel.INFO
        if status_code >= 500:
            level = LogLevel.ERROR
        elif status_code >= 400:
            level = LogLevel.WARNING
        
        event = LogEvent(
            timestamp=time.time(),
            level=level,
            type=LogType.RESPONSE,
            message=f"Response sent with status {status_code}",
            request_id=context.request.request_id,
            user_id=context.get_user_data('user_id'),
            ip_address=context.request.remote_addr,
            method=context.request.method,
            path=context.request.path,
            status_code=status_code,
            processing_time=context.processing_time,
        )
        await self.logger.log_event(event)


class ErrorLogger:
    """错误日志记录器"""
    
    def __init__(self, middleware_logger: MiddlewareLogger):
        self.logger = middleware_logger
    
    async def log_error(self, context: MiddlewareContext, error: Exception) -> None:
        """记录错误"""
        event = LogEvent(
            timestamp=time.time(),
            level=LogLevel.ERROR,
            type=LogType.ERROR,
            message=f"Error occurred: {str(error)}",
            request_id=context.request.request_id,
            user_id=context.get_user_data('user_id'),
            ip_address=context.request.remote_addr,
            method=context.request.method,
            path=context.request.path,
            error=str(error),
            stack_trace=traceback.format_exc(),
            metadata={
                'error_type': type(error).__name__,
                'error_module': type(error).__module__,
            }
        )
        await self.logger.log_event(event)
    
    async def log_errors(self, context: MiddlewareContext) -> None:
        """记录上下文中的所有错误"""
        for error in context.errors:
            await self.log_error(context, error)


@dataclass
class LoggingResult:
    """日志记录结果"""
    success: bool
    events_logged: int = 0
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoggingContext:
    """日志上下文"""
    enabled: bool = True
    log_requests: bool = True
    log_responses: bool = True
    log_errors: bool = True
    log_performance: bool = True
    include_headers: bool = True
    include_body: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoggingConfig:
    """日志中间件配置"""
    enabled: bool = True
    formatter_type: str = "json"          # json/text/structured
    log_level: LogLevel = LogLevel.INFO
    include_metadata: bool = True
    include_headers: bool = True
    include_body: bool = False
    log_requests: bool = True
    log_responses: bool = True
    log_errors: bool = True
    log_performance: bool = True
    skip_paths: List[str] = field(default_factory=list)
    skip_status_codes: List[int] = field(default_factory=list)
    logger_name: str = "marketprism.middleware.logging"
    log_file: Optional[str] = None
    max_body_size: int = 1024             # 最大记录的body大小
    metadata: Dict[str, Any] = field(default_factory=dict)


class LoggingMiddleware(BaseMiddleware):
    """日志中间件"""
    
    def __init__(self, config: MiddlewareConfig, log_config: LoggingConfig):
        super().__init__(config)
        self.log_config = log_config
        self.logger = self._setup_logger()
        self.formatter = self._create_formatter()
        self.middleware_logger = MiddlewareLogger(self.formatter, self.logger)
        self.request_logger = RequestLogger(self.middleware_logger)
        self.response_logger = ResponseLogger(self.middleware_logger)
        self.error_logger = ErrorLogger(self.middleware_logger)
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger(self.log_config.logger_name)
        
        # 设置日志级别
        level_map = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        logger.setLevel(level_map.get(self.log_config.log_level, logging.INFO))
        
        # 避免重复添加处理器
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logger.level)
            logger.addHandler(console_handler)
            
            # 文件处理器
            if self.log_config.log_file:
                try:
                    # 确保日志目录存在
                    log_dir = os.path.dirname(self.log_config.log_file)
                    if log_dir:
                        os.makedirs(log_dir, exist_ok=True)
                    
                    file_handler = logging.FileHandler(self.log_config.log_file, encoding='utf-8')
                    file_handler.setLevel(logger.level)
                    logger.addHandler(file_handler)
                except Exception as e:
                    print(f"Failed to setup file logging: {e}", file=sys.stderr)
        
        # 防止日志传播到根日志记录器
        logger.propagate = False
        
        return logger
    
    def _create_formatter(self) -> LogFormatter:
        """创建格式化器"""
        if self.log_config.formatter_type == "json":
            return JSONLogFormatter(
                include_metadata=self.log_config.include_metadata,
                pretty=False
            )
        elif self.log_config.formatter_type == "text":
            return TextLogFormatter()
        elif self.log_config.formatter_type == "structured":
            return StructuredLogFormatter()
        else:
            return JSONLogFormatter()
    
    def _should_skip_logging(self, path: str) -> bool:
        """检查是否应该跳过日志"""
        for skip_path in self.log_config.skip_paths:
            if path.startswith(skip_path):
                return True
        return False
    
    def _should_skip_status_code(self, status_code: int) -> bool:
        """检查是否应该跳过状态码"""
        return status_code in self.log_config.skip_status_codes
    
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理请求日志"""
        try:
            # 检查是否跳过日志
            if self._should_skip_logging(context.request.path):
                context.set_data('logging_skipped', True)
                return MiddlewareResult.success_result()
            
            # 记录请求开始
            if self.log_config.log_requests:
                await self.request_logger.log_request_start(context)
            
            # 设置日志上下文
            log_context = LoggingContext(
                enabled=True,
                log_requests=self.log_config.log_requests,
                log_responses=self.log_config.log_responses,
                log_errors=self.log_config.log_errors,
                log_performance=self.log_config.log_performance,
                include_headers=self.log_config.include_headers,
                include_body=self.log_config.include_body,
            )
            context.set_data('logging_context', log_context)
            
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    async def process_response(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理响应日志"""
        try:
            # 检查是否跳过日志
            if context.get_data('logging_skipped'):
                return MiddlewareResult.success_result()
            
            log_context = context.get_data('logging_context')
            if not log_context or not log_context.enabled:
                return MiddlewareResult.success_result()
            
            # 记录错误
            if log_context.log_errors and context.has_errors():
                await self.error_logger.log_errors(context)
            
            # 记录响应
            if log_context.log_responses and context.response:
                status_code = context.response.status_code
                if not self._should_skip_status_code(status_code):
                    await self.response_logger.log_response(context, status_code)
            
            # 记录性能
            if log_context.log_performance and context.processing_time:
                await self._log_performance(context)
            
            # 记录请求结束
            if log_context.log_requests:
                await self.request_logger.log_request_end(context)
            
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    async def _log_performance(self, context: MiddlewareContext) -> None:
        """记录性能日志"""
        processing_time = context.processing_time or 0
        
        # 性能等级判断
        level = LogLevel.INFO
        if processing_time > 5000:  # 5秒
            level = LogLevel.WARNING
        elif processing_time > 10000:  # 10秒
            level = LogLevel.ERROR
        
        event = LogEvent(
            timestamp=time.time(),
            level=level,
            type=LogType.PERFORMANCE,
            message=f"Request processing time: {processing_time:.2f}ms",
            request_id=context.request.request_id,
            user_id=context.get_user_data('user_id'),
            ip_address=context.request.remote_addr,
            method=context.request.method,
            path=context.request.path,
            processing_time=processing_time,
            metadata={
                'performance_category': self._categorize_performance(processing_time),
                'middleware_stats': self._extract_middleware_stats(context),
            }
        )
        await self.middleware_logger.log_event(event)
    
    def _categorize_performance(self, processing_time: float) -> str:
        """分类性能"""
        if processing_time < 100:
            return "excellent"
        elif processing_time < 500:
            return "good"
        elif processing_time < 1000:
            return "acceptable"
        elif processing_time < 5000:
            return "slow"
        else:
            return "very_slow"
    
    def _extract_middleware_stats(self, context: MiddlewareContext) -> Dict[str, Any]:
        """提取中间件统计信息"""
        return {
            'total_processing_time': context.processing_time,
            'start_time': context.start_time,
            'end_time': context.end_time,
            'middleware_data_size': len(context.middleware_data),
            'errors_count': len(context.errors),
        }
    
    def get_logging_context(self, context: MiddlewareContext) -> Optional[LoggingContext]:
        """获取日志上下文"""
        return context.get_data('logging_context')
    
    def set_formatter(self, formatter: LogFormatter) -> None:
        """设置格式化器"""
        self.formatter = formatter
        self.middleware_logger.set_formatter(formatter)
    
    async def log_custom_event(self, context: MiddlewareContext, event_type: LogType, message: str, level: LogLevel = LogLevel.INFO, **kwargs) -> None:
        """记录自定义事件"""
        event = LogEvent(
            timestamp=time.time(),
            level=level,
            type=event_type,
            message=message,
            request_id=context.request.request_id,
            user_id=context.get_user_data('user_id'),
            ip_address=context.request.remote_addr,
            method=context.request.method,
            path=context.request.path,
            metadata=kwargs
        )
        await self.middleware_logger.log_event(event)


# 日志异常类
class LoggingError(Exception):
    """日志基础异常"""
    pass


class LogFormatterError(LoggingError):
    """日志格式化异常"""
    pass


class LoggerConfigError(LoggingError):
    """日志配置异常"""
    pass