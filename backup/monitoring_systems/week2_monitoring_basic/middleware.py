"""
监控中间件模块

提供性能监控、请求追踪等中间件功能
"""

import time
import asyncio
from typing import Callable, Any, Dict, Optional
from functools import wraps
import structlog
from contextlib import asynccontextmanager
from datetime import datetime

from .metrics import get_metrics

logger = structlog.get_logger(__name__)


class MonitoringMiddleware:
    """监控中间件类"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.request_start_times: Dict[str, float] = {}
    
    async def __call__(self, request, handler):
        """HTTP请求中间件"""
        start_time = time.time()
        request_id = str(id(request))
        
        try:
            # 记录请求开始
            self.logger.debug(
                "HTTP请求开始",
                path=request.path,
                method=request.method,
                remote=request.remote,
                request_id=request_id
            )
            
            # 处理请求
            response = await handler(request)
            
            # 记录成功响应
            duration = (time.time() - start_time) * 1000
            self.logger.info(
                "HTTP请求完成",
                path=request.path,
                method=request.method,
                status=response.status,
                duration_ms=round(duration, 2),
                request_id=request_id
            )
            
            return response
            
        except Exception as e:
            # 记录错误响应
            duration = (time.time() - start_time) * 1000
            self.logger.error(
                "HTTP请求失败",
                path=request.path,
                method=request.method,
                error=str(e),
                duration_ms=round(duration, 2),
                request_id=request_id
            )
            raise


def monitor_async_function(
    metric_name: str,
    exchange: Optional[str] = None,
    data_type: Optional[str] = None
):
    """异步函数性能监控装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            logger = structlog.get_logger(func.__module__)
            
            try:
                # 记录函数开始执行
                logger.debug(
                    f"{metric_name}开始",
                    function=func.__name__,
                    exchange=exchange,
                    data_type=data_type
                )
                
                # 执行函数
                result = await func(*args, **kwargs)
                
                # 记录成功
                duration = time.time() - start_time
                logger.debug(
                    f"{metric_name}完成", 
                    function=func.__name__,
                    duration_ms=round(duration * 1000, 2),
                    exchange=exchange,
                    data_type=data_type
                )
                
                # 更新Prometheus指标
                try:
                    metrics = get_metrics()
                    if exchange and data_type:
                        metrics.record_processing_time(exchange, data_type, duration)
                except ImportError:
                    pass
                
                return result
                
            except Exception as e:
                # 记录错误
                duration = time.time() - start_time
                logger.error(
                    f"{metric_name}失败",
                    function=func.__name__,
                    error=str(e),
                    duration_ms=round(duration * 1000, 2),
                    exchange=exchange,
                    data_type=data_type
                )
                
                # 更新错误指标
                try:
                    metrics = get_metrics()
                    if exchange:
                        metrics.record_error(exchange, type(e).__name__)
                except ImportError:
                    pass
                
                raise
        
        return wrapper
    return decorator


def monitor_sync_function(
    metric_name: str,
    exchange: Optional[str] = None,
    data_type: Optional[str] = None
):
    """同步函数性能监控装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger = structlog.get_logger(func.__module__)
            
            try:
                # 记录函数开始执行
                logger.debug(
                    f"{metric_name}开始",
                    function=func.__name__,
                    exchange=exchange,
                    data_type=data_type
                )
                
                # 执行函数
                result = func(*args, **kwargs)
                
                # 记录成功
                duration = time.time() - start_time
                logger.debug(
                    f"{metric_name}完成",
                    function=func.__name__,
                    duration_ms=round(duration * 1000, 2),
                    exchange=exchange,
                    data_type=data_type
                )
                
                # 更新Prometheus指标
                try:
                    metrics = get_metrics()
                    if exchange and data_type:
                        metrics.record_processing_time(exchange, data_type, duration)
                except ImportError:
                    pass
                
                return result
                
            except Exception as e:
                # 记录错误
                duration = time.time() - start_time
                logger.error(
                    f"{metric_name}失败",
                    function=func.__name__,
                    error=str(e),
                    duration_ms=round(duration * 1000, 2),
                    exchange=exchange,
                    data_type=data_type
                )
                
                # 更新错误指标
                try:
                    metrics = get_metrics()
                    if exchange:
                        metrics.record_error(exchange, type(e).__name__)
                except ImportError:
                    pass
                
                raise
        
        return wrapper
    return decorator


@asynccontextmanager
async def performance_tracker(
    operation_name: str,
    exchange: Optional[str] = None,
    data_type: Optional[str] = None
):
    """性能追踪上下文管理器"""
    start_time = time.time()
    logger = structlog.get_logger(__name__)
    
    try:
        logger.debug(
            f"{operation_name}开始",
            exchange=exchange,
            data_type=data_type
        )
        
        yield
        
        # 成功完成
        duration = time.time() - start_time
        logger.debug(
            f"{operation_name}完成",
            duration_ms=round(duration * 1000, 2),
            exchange=exchange,
            data_type=data_type
        )
        
        # 更新指标
        try:
            metrics = get_metrics()
            if exchange and data_type:
                metrics.record_processing_time(exchange, data_type, duration)
        except ImportError:
            pass
            
    except Exception as e:
        # 异常情况
        duration = time.time() - start_time
        logger.error(
            f"{operation_name}失败",
            error=str(e),
            duration_ms=round(duration * 1000, 2),
            exchange=exchange,
            data_type=data_type
        )
        
        # 更新错误指标
        try:
            metrics = get_metrics()
            if exchange:
                metrics.record_error(exchange, type(e).__name__)
        except ImportError:
            pass
        
        raise


class PerformanceTracker:
    """性能追踪器类"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = structlog.get_logger(__name__)
        self.start_time: Optional[float] = None
        self.operations: Dict[str, float] = {}
    
    def start(self):
        """开始追踪"""
        self.start_time = time.time()
        self.logger.debug(f"性能追踪开始: {self.name}")
    
    def mark(self, operation: str):
        """标记操作点"""
        if self.start_time is None:
            self.logger.warning("性能追踪未开始，无法标记操作点")
            return
        
        elapsed = time.time() - self.start_time
        self.operations[operation] = elapsed
        self.logger.debug(
            f"性能追踪标记: {operation}",
            elapsed_ms=round(elapsed * 1000, 2)
        )
    
    def finish(self) -> Dict[str, float]:
        """结束追踪并返回性能数据"""
        if self.start_time is None:
            self.logger.warning("性能追踪未开始，无法结束")
            return {}
        
        total_time = time.time() - self.start_time
        self.operations['total'] = total_time
        
        self.logger.info(
            f"性能追踪完成: {self.name}",
            total_ms=round(total_time * 1000, 2),
            operations=self.operations
        )
        
        return self.operations.copy()


class RequestMetrics:
    """请求指标收集器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.request_count = 0
        self.error_count = 0
        self.total_duration = 0.0
        self.last_request_time: Optional[datetime] = None
    
    def record_request(self, duration: float, success: bool = True):
        """记录请求"""
        self.request_count += 1
        self.total_duration += duration
        self.last_request_time = datetime.utcnow()
        
        if not success:
            self.error_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        avg_duration = (
            self.total_duration / self.request_count 
            if self.request_count > 0 else 0
        )
        
        error_rate = (
            (self.error_count / self.request_count) * 100
            if self.request_count > 0 else 0
        )
        
        return {
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "error_rate_percent": round(error_rate, 2),
            "average_duration_ms": round(avg_duration * 1000, 2),
            "total_duration_seconds": round(self.total_duration, 2),
            "last_request_time": (
                self.last_request_time.isoformat() + 'Z'
                if self.last_request_time else None
            )
        }
    
    def reset(self):
        """重置统计"""
        self.request_count = 0
        self.error_count = 0
        self.total_duration = 0.0
        self.last_request_time = None
        self.logger.info("请求指标已重置")


async def monitor_queue_sizes(exchange_adapters: dict, interval: float = 30.0):
    """监控队列大小的后台任务"""
    metrics = get_metrics()
    
    while True:
        try:
            for exchange_name, adapter in exchange_adapters.items():
                # 检查适配器是否有队列大小信息
                if hasattr(adapter, 'get_queue_size'):
                    queue_size = adapter.get_queue_size()
                    metrics.set_queue_size(exchange_name, queue_size)
                elif hasattr(adapter, 'message_queue') and hasattr(adapter.message_queue, 'qsize'):
                    queue_size = adapter.message_queue.qsize()
                    metrics.set_queue_size(exchange_name, queue_size)
                else:
                    # 默认设置为0
                    metrics.set_queue_size(exchange_name, 0)
            
            await asyncio.sleep(interval)
        except Exception as e:
            logger.error("监控队列大小失败", error=str(e))
            await asyncio.sleep(interval)


async def update_system_metrics(interval: float = 60.0):
    """更新系统指标的后台任务"""
    metrics = get_metrics()
    
    while True:
        try:
            # 更新运行时间
            metrics.update_uptime()
            
            # 更新系统信息
            import platform
            import sys
            
            system_info = {
                'python_version': sys.version.split()[0],
                'platform': platform.platform(),
                'hostname': platform.node(),
                'collector_version': '1.0.0'  # 可以从配置或其他地方获取
            }
            metrics.update_system_info(system_info)
            
            await asyncio.sleep(interval)
        except Exception as e:
            logger.error("更新系统指标失败", error=str(e))
            await asyncio.sleep(interval) 