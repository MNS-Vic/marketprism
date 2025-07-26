"""
MarketPrism日志标准化规范

定义统一的日志消息模板、错误处理模式和性能指标记录标准。
"""

from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass
import time


class LogMessageTemplate:
    """标准化日志消息模板"""
    
    # 启动阶段模板
    STARTUP_TEMPLATES = {
        "component_init": "{component} initialized successfully",
        "component_start": "{component} starting up",
        "component_ready": "{component} ready for operation",
        "connection_established": "Connection established to {target}",
        "configuration_loaded": "Configuration loaded from {source}",
        "resource_allocated": "Resources allocated: {resources}"
    }
    
    # 运行阶段模板
    RUNTIME_TEMPLATES = {
        "data_received": "Data received from {source}",
        "data_processed": "Processed {count} {data_type} records",
        "data_published": "Published {count} records to {destination}",
        "heartbeat": "Heartbeat check passed",
        "status_update": "Status update: {status}",
        "performance_metric": "Performance: {metric_name}={value}{unit}"
    }
    
    # 停止阶段模板
    SHUTDOWN_TEMPLATES = {
        "component_stopping": "{component} shutting down",
        "component_stopped": "{component} stopped successfully",
        "connection_closed": "Connection to {target} closed",
        "resource_released": "Resources released: {resources}",
        "cleanup_completed": "Cleanup completed for {component}"
    }
    
    # 错误处理模板
    ERROR_TEMPLATES = {
        "connection_failed": "Failed to connect to {target}: {reason}",
        "data_processing_error": "Error processing {data_type}: {reason}",
        "configuration_error": "Configuration error in {section}: {reason}",
        "resource_exhausted": "Resource exhausted: {resource_type}",
        "timeout_error": "Operation timed out: {operation}",
        "validation_error": "Data validation failed: {reason}"
    }
    
    @classmethod
    def format_message(cls, template_category: str, template_key: str, **kwargs) -> str:
        """格式化标准消息模板"""
        templates = getattr(cls, f"{template_category.upper()}_TEMPLATES", {})
        template = templates.get(template_key, "Unknown template: {template_key}")
        
        try:
            return template.format(**kwargs)
        except KeyError as e:
            return f"Template formatting error: missing key {e}"


@dataclass
class PerformanceMetric:
    """性能指标数据结构"""
    name: str
    value: float
    unit: str
    timestamp: float = None
    context: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.context is None:
            self.context = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "metric_name": self.name,
            "metric_value": self.value,
            "metric_unit": self.unit,
            "metric_timestamp": self.timestamp,
            **self.context
        }


class StandardizedErrorHandler:
    """标准化错误处理器"""
    
    ERROR_CATEGORIES = {
        "NETWORK": ["connection", "timeout", "dns", "ssl"],
        "DATA": ["parsing", "validation", "format", "corruption"],
        "RESOURCE": ["memory", "disk", "cpu", "file_descriptor"],
        "CONFIGURATION": ["missing", "invalid", "format", "permission"],
        "BUSINESS": ["sequence", "duplicate", "missing_data", "logic"]
    }
    
    @classmethod
    def categorize_error(cls, error: Exception, context: str = "") -> str:
        """错误分类"""
        error_type = type(error).__name__.lower()
        error_message = str(error).lower()
        
        for category, keywords in cls.ERROR_CATEGORIES.items():
            if any(keyword in error_type or keyword in error_message or keyword in context.lower() 
                   for keyword in keywords):
                return category
        
        return "UNKNOWN"
    
    @classmethod
    def format_error_context(cls, 
                           error: Exception,
                           operation: str,
                           component: str,
                           additional_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """格式化错误上下文"""
        context = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_category": cls.categorize_error(error, operation),
            "operation": operation,
            "component": component,
            "timestamp": time.time()
        }
        
        if additional_context:
            context.update(additional_context)
            
        return context


class LogFrequencyController:
    """日志频率控制器 - 防止日志洪水"""
    
    def __init__(self):
        self._message_counts: Dict[str, int] = {}
        self._last_log_times: Dict[str, float] = {}
        self._suppressed_counts: Dict[str, int] = {}
    
    def should_log(self, 
                   message_key: str,
                   max_frequency: float = 1.0,  # 最大频率：每秒1次
                   burst_limit: int = 5) -> tuple[bool, Optional[str]]:
        """判断是否应该记录日志
        
        Args:
            message_key: 消息唯一标识
            max_frequency: 最大频率（次/秒）
            burst_limit: 突发限制（连续次数）
            
        Returns:
            (should_log, suppression_message)
        """
        current_time = time.time()
        
        # 初始化计数器
        if message_key not in self._message_counts:
            self._message_counts[message_key] = 0
            self._last_log_times[message_key] = 0
            self._suppressed_counts[message_key] = 0
        
        # 检查时间间隔
        time_since_last = current_time - self._last_log_times[message_key]
        min_interval = 1.0 / max_frequency
        
        # 重置计数器（如果时间间隔足够长）
        if time_since_last >= min_interval * burst_limit:
            self._message_counts[message_key] = 0
            self._suppressed_counts[message_key] = 0
        
        # 检查是否超过突发限制
        if self._message_counts[message_key] >= burst_limit:
            if time_since_last < min_interval:
                self._suppressed_counts[message_key] += 1
                return False, None
        
        # 允许记录日志
        self._message_counts[message_key] += 1
        self._last_log_times[message_key] = current_time
        
        # 如果之前有被抑制的日志，添加抑制信息
        suppression_message = None
        if self._suppressed_counts[message_key] > 0:
            suppression_message = f"(suppressed {self._suppressed_counts[message_key]} similar messages)"
            self._suppressed_counts[message_key] = 0
        
        return True, suppression_message


class BusinessEventLogger:
    """业务事件日志记录器"""
    
    @staticmethod
    def log_orderbook_event(logger, event_type: str, symbol: str, 
                          exchange: str, details: Dict[str, Any]):
        """记录订单簿事件"""
        logger.data_processing(
            f"OrderBook {event_type}",
            symbol=symbol,
            exchange=exchange,
            event_type=event_type,
            **details
        )
    
    @staticmethod
    def log_trade_event(logger, symbol: str, exchange: str, 
                       trade_data: Dict[str, Any]):
        """记录成交事件"""
        logger.data_processing(
            f"Trade processed",
            symbol=symbol,
            exchange=exchange,
            trade_id=trade_data.get('id'),
            price=trade_data.get('price'),
            quantity=trade_data.get('quantity'),
            side=trade_data.get('side')
        )
    
    @staticmethod
    def log_connection_event(logger, event_type: str, target: str,
                           success: bool, details: Dict[str, Any] = None):
        """记录连接事件"""
        message = LogMessageTemplate.format_message(
            "startup" if success else "error",
            "connection_established" if success else "connection_failed",
            target=target,
            **(details or {})
        )
        
        logger.connection(message, success=success, target=target, **(details or {}))
    
    @staticmethod
    def log_performance_event(logger, metrics: List[PerformanceMetric]):
        """记录性能事件"""
        for metric in metrics:
            logger.performance(
                LogMessageTemplate.format_message(
                    "runtime", "performance_metric",
                    metric_name=metric.name,
                    value=metric.value,
                    unit=metric.unit
                ),
                metric.to_dict()
            )


class LogAggregator:
    """日志聚合器 - 用于批量处理和统计"""
    
    def __init__(self, flush_interval: int = 60):
        self.flush_interval = flush_interval
        self._counters: Dict[str, int] = {}
        self._timers: Dict[str, List[float]] = {}
        self._last_flush = time.time()
    
    def increment_counter(self, counter_name: str, value: int = 1):
        """增加计数器"""
        self._counters[counter_name] = self._counters.get(counter_name, 0) + value
    
    def record_timing(self, timer_name: str, duration: float):
        """记录时间"""
        if timer_name not in self._timers:
            self._timers[timer_name] = []
        self._timers[timer_name].append(duration)
    
    def should_flush(self) -> bool:
        """检查是否应该刷新统计"""
        return time.time() - self._last_flush >= self.flush_interval
    
    def flush_and_log(self, logger):
        """刷新并记录聚合统计"""
        if not self.should_flush():
            return
        
        current_time = time.time()
        
        # 记录计数器统计
        for counter_name, count in self._counters.items():
            logger.performance(
                f"Counter summary: {counter_name}",
                {
                    "counter_name": counter_name,
                    "count": count,
                    "rate_per_minute": count / (self.flush_interval / 60)
                }
            )
        
        # 记录时间统计
        for timer_name, durations in self._timers.items():
            if durations:
                avg_duration = sum(durations) / len(durations)
                max_duration = max(durations)
                min_duration = min(durations)
                
                logger.performance(
                    f"Timing summary: {timer_name}",
                    {
                        "timer_name": timer_name,
                        "count": len(durations),
                        "avg_duration_ms": avg_duration * 1000,
                        "max_duration_ms": max_duration * 1000,
                        "min_duration_ms": min_duration * 1000
                    }
                )
        
        # 重置统计
        self._counters.clear()
        self._timers.clear()
        self._last_flush = current_time


# 全局实例
frequency_controller = LogFrequencyController()
log_aggregator = LogAggregator()


def with_frequency_control(max_frequency: float = 1.0, burst_limit: int = 5):
    """日志频率控制装饰器"""
    def decorator(log_func):
        def wrapper(*args, **kwargs):
            # 生成消息键
            message_key = f"{log_func.__name__}:{hash(str(args) + str(kwargs)) % 10000}"
            
            should_log, suppression_msg = frequency_controller.should_log(
                message_key, max_frequency, burst_limit
            )
            
            if should_log:
                if suppression_msg and len(args) > 1:
                    # 在消息后添加抑制信息
                    args = list(args)
                    args[1] = f"{args[1]} {suppression_msg}"
                    args = tuple(args)
                
                return log_func(*args, **kwargs)
        
        return wrapper
    return decorator


def with_timing(timer_name: str):
    """性能计时装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                log_aggregator.record_timing(timer_name, duration)
        
        return wrapper
    return decorator
