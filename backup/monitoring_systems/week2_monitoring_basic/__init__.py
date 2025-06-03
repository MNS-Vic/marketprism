"""
MarketPrism Collector 监控模块

提供企业级监控功能，包括：
- Prometheus指标收集
- 健康检查
- 性能监控
- 内存分析 (第二阶段优化第1天)
- 对象池管理 (第二阶段优化第2天)
- 连接池管理 (第二阶段优化第3天)
- 异步处理优化 (第二阶段优化第4天)
"""

from .metrics import CollectorMetrics, MetricsCollector, get_metrics
from .health import HealthChecker
from .memory_profiler import (
    MemoryProfiler, 
    get_memory_profiler,
    start_memory_profiling,
    take_memory_snapshot,
    get_memory_summary,
    export_memory_report
)
from .object_pool import (
    ObjectPool,
    MessageObjectPool,
    PoolStatistics,
    get_message_pool,
    acquire_trade_object,
    release_trade_object,
    acquire_orderbook_object,
    release_orderbook_object,
    get_pool_summary
)
from .connection_pool import (
    ConnectionPool,
    WebSocketConnectionPool,
    HTTPConnectionPool,
    ConnectionPoolManager,
    ConnectionPoolStatistics,
    ConnectionState,
    ConnectionType,
    get_connection_pool_manager,
    create_websocket_pool,
    create_http_pool,
    get_websocket_connection,
    get_http_connection,
    get_connection_pool_summary
)
from .async_pool import (
    CoroutinePool,
    EventLoopOptimizer,
    AsyncPerformanceMonitor,
    AsyncOptimizationManager,
    AsyncPoolStatistics,
    CoroutineState,
    EventLoopPolicy,
    get_async_optimization_manager,
    create_coroutine_pool,
    setup_event_loop_optimizer,
    setup_performance_monitor,
    submit_coroutine,
    get_async_optimization_summary
)

# 健康检查函数
from .health import (
    check_nats_connection,
    check_exchange_connections,
    check_memory_usage,
    monitor_queue_sizes,
    update_system_metrics
)

__all__ = [
    'CollectorMetrics',
    'MetricsCollector',
    'get_metrics', 
    'HealthChecker',
    'MemoryProfiler',
    'get_memory_profiler',
    'start_memory_profiling',
    'take_memory_snapshot',
    'get_memory_summary',
    'export_memory_report',
    'ObjectPool',
    'MessageObjectPool',
    'PoolStatistics',
    'get_message_pool',
    'acquire_trade_object',
    'release_trade_object',
    'acquire_orderbook_object',
    'release_orderbook_object',
    'get_pool_summary',
    'ConnectionPool',
    'WebSocketConnectionPool',
    'HTTPConnectionPool',
    'ConnectionPoolManager',
    'ConnectionPoolStatistics',
    'ConnectionState',
    'ConnectionType',
    'get_connection_pool_manager',
    'create_websocket_pool',
    'create_http_pool',
    'get_websocket_connection',
    'get_http_connection',
    'get_connection_pool_summary',
    'CoroutinePool',
    'EventLoopOptimizer',
    'AsyncPerformanceMonitor',
    'AsyncOptimizationManager',
    'AsyncPoolStatistics',
    'CoroutineState',
    'EventLoopPolicy',
    'get_async_optimization_manager',
    'create_coroutine_pool',
    'setup_event_loop_optimizer',
    'setup_performance_monitor',
    'submit_coroutine',
    'get_async_optimization_summary',
    'check_nats_connection',
    'check_exchange_connections', 
    'check_memory_usage',
    'monitor_queue_sizes',
    'update_system_metrics'
]


# TDD改进：统一监控管理器
class MonitoringManager:
    """统一监控管理器
    
    集成所有监控组件，提供统一的管理接口
    """
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.health_checker = HealthChecker()
        self.memory_profiler = MemoryProfiler()
        self.is_running = False
        
    def start(self):
        """启动所有监控组件"""
        self.health_checker.start()
        if hasattr(self.memory_profiler, 'start_profiling'):
            self.memory_profiler.start_profiling()
        self.is_running = True
        
    def stop(self):
        """停止所有监控组件"""
        self.health_checker.stop()
        if hasattr(self.memory_profiler, 'stop_profiling'):
            self.memory_profiler.stop_profiling()
        self.is_running = False
        
    def get_status(self):
        """获取整体监控状态"""
        return {
            'monitoring_manager': {
                'is_running': self.is_running,
                'components': ['metrics', 'health', 'memory']
            },
            'metrics': self.metrics_collector.get_metrics(),
            'health': self.health_checker.get_status(),
            'memory': self.memory_profiler.get_stats()
        }


# 全局监控管理器实例
_monitoring_manager = None

def get_monitoring_manager() -> MonitoringManager:
    """获取全局监控管理器实例"""
    global _monitoring_manager
    if _monitoring_manager is None:
        _monitoring_manager = MonitoringManager()
    return _monitoring_manager


# 添加到导出列表
__all__.extend(['MonitoringManager', 'get_monitoring_manager']) 