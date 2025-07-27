#!/usr/bin/env python3
"""
MarketPrism异常定义和错误处理框架
"""

import time
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict
import structlog


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """错误分类"""
    NETWORK = "network"
    DATA_VALIDATION = "data_validation"
    CONFIGURATION = "configuration"
    RESOURCE = "resource"
    BUSINESS_LOGIC = "business_logic"
    EXTERNAL_SERVICE = "external_service"


@dataclass
class ErrorContext:
    """错误上下文信息"""
    timestamp: float
    component: str
    operation: str
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


class MarketPrismException(Exception):
    """MarketPrism基础异常类"""
    
    def __init__(self, message: str, category: ErrorCategory, severity: ErrorSeverity, 
                 context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.context = context or ErrorContext(
            timestamp=time.time(),
            component="unknown",
            operation="unknown"
        )
        self.cause = cause
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于日志记录"""
        return {
            'message': self.message,
            'category': self.category.value,
            'severity': self.severity.value,
            'timestamp': self.context.timestamp,
            'component': self.context.component,
            'operation': self.context.operation,
            'exchange': self.context.exchange,
            'symbol': self.context.symbol,
            'additional_data': self.context.additional_data,
            'cause': str(self.cause) if self.cause else None
        }


class WebSocketConnectionError(MarketPrismException):
    """WebSocket连接异常"""
    
    def __init__(self, message: str, exchange: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        if context:
            context.exchange = exchange
        else:
            context = ErrorContext(
                timestamp=time.time(),
                component="websocket",
                operation="connect",
                exchange=exchange
            )
        super().__init__(message, ErrorCategory.NETWORK, ErrorSeverity.HIGH, context, cause)


class DataValidationError(MarketPrismException):
    """数据验证异常"""
    
    def __init__(self, message: str, symbol: str, exchange: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        if context:
            context.symbol = symbol
            context.exchange = exchange
        else:
            context = ErrorContext(
                timestamp=time.time(),
                component="data_validator",
                operation="validate",
                exchange=exchange,
                symbol=symbol
            )
        super().__init__(message, ErrorCategory.DATA_VALIDATION, ErrorSeverity.MEDIUM, context, cause)


class NATSPublishError(MarketPrismException):
    """NATS发布异常"""
    
    def __init__(self, message: str, subject: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        if context:
            context.additional_data = {'subject': subject}
        else:
            context = ErrorContext(
                timestamp=time.time(),
                component="nats_publisher",
                operation="publish",
                additional_data={'subject': subject}
            )
        super().__init__(message, ErrorCategory.EXTERNAL_SERVICE, ErrorSeverity.HIGH, context, cause)


class OrderBookSyncError(MarketPrismException):
    """订单簿同步异常"""
    
    def __init__(self, message: str, symbol: str, exchange: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        if context:
            context.symbol = symbol
            context.exchange = exchange
        else:
            context = ErrorContext(
                timestamp=time.time(),
                component="orderbook_manager",
                operation="sync",
                exchange=exchange,
                symbol=symbol
            )
        super().__init__(message, ErrorCategory.BUSINESS_LOGIC, ErrorSeverity.HIGH, context, cause)


class ConfigurationError(MarketPrismException):
    """配置异常"""
    
    def __init__(self, message: str, config_key: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        if context:
            context.additional_data = {'config_key': config_key}
        else:
            context = ErrorContext(
                timestamp=time.time(),
                component="configuration",
                operation="load",
                additional_data={'config_key': config_key}
            )
        super().__init__(message, ErrorCategory.CONFIGURATION, ErrorSeverity.CRITICAL, context, cause)


class ResourceExhaustionError(MarketPrismException):
    """资源耗尽异常"""
    
    def __init__(self, message: str, resource_type: str, context: Optional[ErrorContext] = None, cause: Optional[Exception] = None):
        if context:
            context.additional_data = {'resource_type': resource_type}
        else:
            context = ErrorContext(
                timestamp=time.time(),
                component="resource_manager",
                operation="allocate",
                additional_data={'resource_type': resource_type}
            )
        super().__init__(message, ErrorCategory.RESOURCE, ErrorSeverity.CRITICAL, context, cause)


class ErrorMonitor:
    """错误监控器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.error_counts = defaultdict(int)
        self.error_history: List[Dict[str, Any]] = []
        self.error_rates = {}
        self.last_reset_time = time.time()
    
    def record_error(self, error: MarketPrismException):
        """记录错误"""
        error_dict = error.to_dict()
        
        # 更新计数器
        error_key = f"{error.category.value}_{error.severity.value}"
        self.error_counts[error_key] += 1
        
        # 添加到历史记录
        self.error_history.append(error_dict)
        
        # 保持历史记录在合理大小
        if len(self.error_history) > 1000:
            self.error_history = self.error_history[-500:]
        
        # 记录日志
        log_level = self._get_log_level(error.severity)
        self.logger.log(log_level, "MarketPrism错误", **error_dict)
    
    def _get_log_level(self, severity: ErrorSeverity) -> int:
        """根据严重程度获取日志级别"""
        import logging
        mapping = {
            ErrorSeverity.LOW: logging.DEBUG,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }
        return mapping.get(severity, "error")
    
    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误摘要"""
        current_time = time.time()
        time_window = current_time - self.last_reset_time
        
        return {
            'total_errors': sum(self.error_counts.values()),
            'error_breakdown': dict(self.error_counts),
            'time_window_seconds': time_window,
            'error_rate_per_minute': sum(self.error_counts.values()) / (time_window / 60) if time_window > 0 else 0,
            'recent_errors': self.error_history[-10:] if self.error_history else []
        }
    
    def reset_counters(self):
        """重置计数器"""
        self.error_counts.clear()
        self.last_reset_time = time.time()
    
    def get_critical_errors(self) -> List[Dict[str, Any]]:
        """获取关键错误"""
        return [
            error for error in self.error_history
            if error.get('severity') == ErrorSeverity.CRITICAL.value
        ]


# 全局错误监控器实例
error_monitor = ErrorMonitor()


def handle_error(error: Exception, component: str, operation: str, 
                exchange: Optional[str] = None, symbol: Optional[str] = None,
                additional_data: Optional[Dict[str, Any]] = None) -> MarketPrismException:
    """
    统一错误处理函数
    
    Args:
        error: 原始异常
        component: 组件名称
        operation: 操作名称
        exchange: 交易所名称
        symbol: 交易对符号
        additional_data: 额外数据
    
    Returns:
        MarketPrismException: 包装后的异常
    """
    context = ErrorContext(
        timestamp=time.time(),
        component=component,
        operation=operation,
        exchange=exchange,
        symbol=symbol,
        additional_data=additional_data
    )
    
    # 根据异常类型选择合适的包装类
    if isinstance(error, ConnectionError):
        wrapped_error = WebSocketConnectionError(str(error), exchange or "unknown", context, error)
    elif isinstance(error, ValueError):
        wrapped_error = DataValidationError(str(error), symbol or "unknown", exchange or "unknown", context, error)
    else:
        wrapped_error = MarketPrismException(
            str(error), 
            ErrorCategory.BUSINESS_LOGIC, 
            ErrorSeverity.MEDIUM, 
            context, 
            error
        )
    
    # 记录错误
    error_monitor.record_error(wrapped_error)
    
    return wrapped_error
