"""
MarketPrism统一日志系统

提供标准化的日志记录、格式化和配置管理功能。
解决日志格式不一致、emoji滥用、级别混乱等问题。
"""

import os
import sys
import time
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field
import structlog
import logging


class LogLevel(Enum):
    """标准化日志级别"""
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ComponentType(Enum):
    """组件类型枚举 - 用于统一日志标识"""
    MAIN = "main"
    ORDERBOOK_MANAGER = "orderbook"
    TRADES_MANAGER = "trades"
    LIQUIDATION_MANAGER = "liquidation"  # 🔧 新增：强平数据管理器
    WEBSOCKET = "websocket"
    NATS_PUBLISHER = "nats"
    MEMORY_MANAGER = "memory"
    DATA_NORMALIZER = "normalizer"
    ERROR_HANDLER = "error"
    HEALTH_CHECK = "health"
    FACTORY = "factory"  # 🔧 新增：工厂类


class OperationType(Enum):
    """操作类型枚举 - 用于统一日志前缀"""
    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"
    CONNECTION = "CONNECTION"
    DATA_PROCESSING = "DATA_PROC"
    ERROR_HANDLING = "ERROR"
    PERFORMANCE = "PERF"
    HEALTH_CHECK = "HEALTH"
    CONFIGURATION = "CONFIG"


@dataclass
class LogContext:
    """日志上下文信息"""
    component: ComponentType
    operation: OperationType
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    market_type: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        context = {
            "component": self.component.value,
            "operation": self.operation.value
        }
        
        if self.exchange:
            context["exchange"] = self.exchange
        if self.symbol:
            context["symbol"] = self.symbol
        if self.market_type:
            context["market_type"] = self.market_type
        if self.correlation_id:
            context["correlation_id"] = self.correlation_id
            
        return context


class UnifiedLogFormatter:
    """统一日志格式化器"""
    
    # 标准化的操作前缀（替代emoji）
    OPERATION_PREFIXES = {
        OperationType.STARTUP: "[START]",
        OperationType.SHUTDOWN: "[STOP]",
        OperationType.CONNECTION: "[CONN]",
        OperationType.DATA_PROCESSING: "[DATA]",
        OperationType.ERROR_HANDLING: "[ERROR]",
        OperationType.PERFORMANCE: "[PERF]",
        OperationType.HEALTH_CHECK: "[HEALTH]",
        OperationType.CONFIGURATION: "[CONFIG]"
    }
    
    # 生产环境状态指示符（替代emoji）
    STATUS_INDICATORS = {
        "success": "✓",
        "failure": "✗",
        "warning": "!",
        "info": "→",
        "processing": "⟳"
    }
    
    @classmethod
    def format_message(cls, 
                      level: LogLevel,
                      message: str,
                      context: LogContext,
                      status: Optional[str] = None,
                      use_emoji: bool = False) -> str:
        """格式化日志消息
        
        Args:
            level: 日志级别
            message: 原始消息
            context: 日志上下文
            status: 状态指示符
            use_emoji: 是否使用emoji（开发环境）
        """
        # 操作前缀
        prefix = cls.OPERATION_PREFIXES.get(context.operation, "[UNKNOWN]")
        
        # 状态指示符
        if status and not use_emoji:
            indicator = cls.STATUS_INDICATORS.get(status, "")
            if indicator:
                prefix = f"{prefix} {indicator}"
        
        # 组件标识
        component_id = f"{context.component.value}"
        if context.exchange:
            component_id += f".{context.exchange}"
        if context.market_type:
            component_id += f".{context.market_type}"
        
        # 构建格式化消息
        formatted = f"{prefix} {component_id}: {message}"
        
        # 添加符号信息（如果存在）
        if context.symbol:
            formatted += f" [{context.symbol}]"
            
        return formatted


class UnifiedLogger:
    """统一日志记录器"""
    
    def __init__(self, 
                 component: ComponentType,
                 exchange: Optional[str] = None,
                 market_type: Optional[str] = None,
                 correlation_id: Optional[str] = None):
        """初始化统一日志记录器
        
        Args:
            component: 组件类型
            exchange: 交易所名称
            market_type: 市场类型
            correlation_id: 关联ID
        """
        self.component = component
        self.exchange = exchange
        self.market_type = market_type
        self.correlation_id = correlation_id
        
        # 构建logger名称
        logger_name = f"marketprism.{component.value}"
        if exchange:
            logger_name += f".{exchange}"
        if market_type:
            logger_name += f".{market_type}"
            
        self._logger = structlog.get_logger(logger_name)
        self._formatter = UnifiedLogFormatter()
        
        # 环境配置
        self.use_emoji = os.getenv("MARKETPRISM_USE_EMOJI", "false").lower() == "true"
        self.enable_debug = os.getenv("MARKETPRISM_DEBUG", "false").lower() == "true"
    
    def _create_context(self, operation: OperationType, **kwargs) -> LogContext:
        """创建日志上下文"""
        return LogContext(
            component=self.component,
            operation=operation,
            exchange=self.exchange or kwargs.get('exchange'),
            symbol=kwargs.get('symbol'),
            market_type=self.market_type or kwargs.get('market_type'),
            correlation_id=self.correlation_id or kwargs.get('correlation_id')
        )
    
    def startup(self, message: str, **kwargs):
        """记录启动日志"""
        context = self._create_context(OperationType.STARTUP, **kwargs)
        formatted_msg = self._formatter.format_message(
            LogLevel.INFO, message, context, "success", self.use_emoji
        )
        # 🔧 修复：避免参数冲突，合并上下文和kwargs
        log_kwargs = {**context.to_dict()}
        log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})
        self._logger.info(formatted_msg, **log_kwargs)
    
    def shutdown(self, message: str, **kwargs):
        """记录停止日志"""
        context = self._create_context(OperationType.SHUTDOWN, **kwargs)
        formatted_msg = self._formatter.format_message(
            LogLevel.INFO, message, context, "success", self.use_emoji
        )
        # 🔧 修复：避免参数冲突
        log_kwargs = {**context.to_dict()}
        log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})
        self._logger.info(formatted_msg, **log_kwargs)
    
    def connection(self, message: str, success: bool = True, **kwargs):
        """记录连接日志"""
        context = self._create_context(OperationType.CONNECTION, **kwargs)
        status = "success" if success else "failure"
        level = LogLevel.INFO if success else LogLevel.ERROR
        
        formatted_msg = self._formatter.format_message(
            level, message, context, status, self.use_emoji
        )
        
        # 🔧 修复：避免参数冲突
        log_kwargs = {**context.to_dict()}
        log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})

        if success:
            self._logger.info(formatted_msg, **log_kwargs)
        else:
            self._logger.error(formatted_msg, **log_kwargs)
    
    def data_processing(self, message: str, **kwargs):
        """记录数据处理日志"""
        context = self._create_context(OperationType.DATA_PROCESSING, **kwargs)
        formatted_msg = self._formatter.format_message(
            LogLevel.DEBUG, message, context, "processing", self.use_emoji
        )
        
        if self.enable_debug:
            # 🔧 修复：避免参数冲突
            log_kwargs = {**context.to_dict()}
            log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})
            self._logger.debug(formatted_msg, **log_kwargs)
    
    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """记录错误日志"""
        context = self._create_context(OperationType.ERROR_HANDLING, **kwargs)
        formatted_msg = self._formatter.format_message(
            LogLevel.ERROR, message, context, "failure", self.use_emoji
        )
        
        # 🔧 修复：避免参数冲突
        log_kwargs = {**context.to_dict()}
        log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})

        if error:
            log_kwargs['error'] = str(error)
            log_kwargs['error_type'] = type(error).__name__
            # 🔧 修复：避免重复的exc_info参数
            if 'exc_info' not in log_kwargs:
                log_kwargs['exc_info'] = True

        self._logger.error(formatted_msg, **log_kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录警告日志"""
        context = self._create_context(OperationType.ERROR_HANDLING, **kwargs)
        formatted_msg = self._formatter.format_message(
            LogLevel.WARNING, message, context, "warning", self.use_emoji
        )
        # 🔧 修复：避免参数冲突
        log_kwargs = {**context.to_dict()}
        log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})
        self._logger.warning(formatted_msg, **log_kwargs)
    
    def performance(self, message: str, metrics: Dict[str, Any], **kwargs):
        """记录性能日志"""
        context = self._create_context(OperationType.PERFORMANCE, **kwargs)
        formatted_msg = self._formatter.format_message(
            LogLevel.INFO, message, context, "info", self.use_emoji
        )
        
        # 🔧 修复：避免参数冲突
        log_kwargs = {**context.to_dict()}
        log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})
        log_kwargs.update({k: v for k, v in metrics.items() if k not in log_kwargs})
        self._logger.info(formatted_msg, **log_kwargs)
    
    def health_check(self, message: str, healthy: bool = True, **kwargs):
        """记录健康检查日志"""
        context = self._create_context(OperationType.HEALTH_CHECK, **kwargs)
        status = "success" if healthy else "warning"
        level = LogLevel.DEBUG if healthy else LogLevel.WARNING
        
        formatted_msg = self._formatter.format_message(
            level, message, context, status, self.use_emoji
        )
        
        if healthy and not self.enable_debug:
            return  # 健康状态在非调试模式下不记录
            
        # 🔧 修复：避免参数冲突
        log_kwargs = {**context.to_dict()}
        log_kwargs.update({k: v for k, v in kwargs.items() if k not in log_kwargs})

        if healthy:
            self._logger.debug(formatted_msg, **log_kwargs)
        else:
            self._logger.warning(formatted_msg, **log_kwargs)


class LoggerFactory:
    """日志记录器工厂"""
    
    _instances: Dict[str, UnifiedLogger] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_logger(cls,
                   component: ComponentType,
                   exchange: Optional[str] = None,
                   market_type: Optional[str] = None,
                   correlation_id: Optional[str] = None) -> UnifiedLogger:
        """获取统一日志记录器实例（单例模式）"""
        
        # 构建实例键
        key_parts = [component.value]
        if exchange:
            key_parts.append(exchange)
        if market_type:
            key_parts.append(market_type)
        instance_key = ".".join(key_parts)
        
        if instance_key not in cls._instances:
            with cls._lock:
                if instance_key not in cls._instances:
                    cls._instances[instance_key] = UnifiedLogger(
                        component=component,
                        exchange=exchange,
                        market_type=market_type,
                        correlation_id=correlation_id
                    )
        
        return cls._instances[instance_key]
    
    @classmethod
    def configure_logging(cls, 
                         level: str = "INFO",
                         use_json: bool = False,
                         enable_file_logging: bool = True,
                         log_file_path: str = "/tmp/marketprism.log"):
        """配置全局日志系统"""
        
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]
        
        if use_json:
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer(colors=True))
        
        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True
        )
        
        # 配置标准库logging
        logging.basicConfig(
            level=getattr(logging, level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_file_path) if enable_file_logging else logging.NullHandler()
            ]
        )


# 便捷函数
def get_logger(component: ComponentType, 
               exchange: Optional[str] = None,
               market_type: Optional[str] = None) -> UnifiedLogger:
    """获取统一日志记录器的便捷函数"""
    return LoggerFactory.get_logger(component, exchange, market_type)
