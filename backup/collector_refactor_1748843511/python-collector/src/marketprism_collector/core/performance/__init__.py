"""
🚀 Performance Optimization Module

MarketPrism高性能优化模块
提供缓存、连接池、负载均衡、异步处理、内存和IO优化功能
"""

from .cache_optimizer import (
    CacheOptimizer,
    CacheConfig,
    CacheStrategy,
    CacheLevel,
    CacheEntry,
    CacheStats,
    create_cache_key,
    cache_decorator
)

from .connection_pool_manager import (
    ConnectionPoolManager,
    ConnectionPool,
    Connection,
    ConnectionConfig,
    ConnectionType,
    ConnectionState,
    ConnectionInfo,
    PoolStats,
    create_http_connection,
    with_connection
)

from .load_balancing_optimizer import (
    LoadBalancingOptimizer,
    LoadBalancingConfig,
    LoadBalancingAlgorithm,
    ServerConfig,
    ServerMetrics,
    ServerStatus,
    Server
)

from .async_processing_engine import (
    AsyncProcessingEngine,
    ProcessingConfig,
    TaskConfig,
    Task,
    TaskQueue,
    WorkerPool,
    TaskPriority,
    TaskStatus,
    BackpressureStrategy,
    async_task,
    batch_process
)

from .memory_optimizer import (
    MemoryOptimizer,
    MemoryConfig,
    MemoryStats,
    MemoryStrategy,
    ObjectPool,
    ObjectPoolType,
    MemoryTracker,
    MemoryPoolManager,
    memory_tracked,
    with_object_pool
)

from .io_optimizer import (
    IOOptimizer,
    IOConfig,
    IOStats,
    CompressionManager,
    NetworkOptimizer,
    DiskOptimizer,
    CompressionType,
    IOMode,
    NetworkProtocol,
    bulk_download,
    io_performance_monitor
)

from .performance_optimization_manager import (
    PerformanceOptimizationManager,
    PerformanceConfig,
    PerformanceMetrics,
    OptimizationLevel,
    OptimizationTarget
)

__all__ = [
    # Cache Optimizer
    'CacheOptimizer',
    'CacheConfig',
    'CacheStrategy', 
    'CacheLevel',
    'CacheEntry',
    'CacheStats',
    'create_cache_key',
    'cache_decorator',
    
    # Connection Pool Manager
    'ConnectionPoolManager',
    'ConnectionPool',
    'Connection',
    'ConnectionConfig',
    'ConnectionType',
    'ConnectionState',
    'ConnectionInfo',
    'PoolStats',
    'create_http_connection',
    'with_connection',
    
    # Load Balancing Optimizer
    'LoadBalancingOptimizer',
    'LoadBalancingConfig',
    'LoadBalancingAlgorithm',
    'ServerConfig',
    'ServerMetrics',
    'ServerStatus',
    'Server',
    
    # Async Processing Engine
    'AsyncProcessingEngine',
    'ProcessingConfig',
    'TaskConfig',
    'Task',
    'TaskQueue',
    'WorkerPool',
    'TaskPriority',
    'TaskStatus',
    'BackpressureStrategy',
    'async_task',
    'batch_process',
    
    # Memory Optimizer
    'MemoryOptimizer',
    'MemoryConfig',
    'MemoryStats',
    'MemoryStrategy',
    'ObjectPool',
    'ObjectPoolType',
    'MemoryTracker',
    'MemoryPoolManager',
    'memory_tracked',
    'with_object_pool',
    
    # IO Optimizer
    'IOOptimizer',
    'IOConfig',
    'IOStats',
    'CompressionManager',
    'NetworkOptimizer',
    'DiskOptimizer',
    'CompressionType',
    'IOMode',
    'NetworkProtocol',
    'bulk_download',
    'io_performance_monitor',
    
    # Performance Optimization Manager
    'PerformanceOptimizationManager',
    'PerformanceConfig',
    'PerformanceMetrics',
    'OptimizationLevel',
    'OptimizationTarget'
]

# 版本信息
__version__ = '1.0.0'
__author__ = 'MarketPrism Team'
__description__ = 'High-performance optimization module for MarketPrism'