"""
MarketPrism 统一缓存系统

提供多层缓存、智能策略、一致性管理和性能分析功能。
"""

from .cache_interface import (
    Cache, CacheKey, CacheValue, CacheConfig, CacheLevel, 
    CacheEvictionPolicy, SerializationFormat, CacheStatistics
)
from .cache_strategies import CacheStrategy, LRUStrategy, LFUStrategy, TTLStrategy, AdaptiveStrategy
from .memory_cache import MemoryCache, MemoryCacheConfig
from .redis_cache import RedisCache, RedisCacheConfig, create_redis_cache, REDIS_AVAILABLE
from .disk_cache import DiskCache, DiskCacheConfig, create_disk_cache
from .cache_coordinator import (
    CacheCoordinator, CacheCoordinatorConfig, CacheInstance,
    CacheRoutingPolicy, CacheSyncStrategy, create_multi_level_cache
)
from .performance_optimizer import (
    PerformanceOptimizer, PerformanceOptimizerConfig,
    OptimizationType, PredictionModel, PerformanceMetric,
    OptimizationRecommendation, AccessPattern, create_performance_optimizer
)

__all__ = [
    # 核心接口
    'Cache',
    'CacheKey',
    'CacheValue',
    'CacheConfig',
    'CacheLevel',
    'CacheEvictionPolicy',
    'SerializationFormat',
    'CacheStatistics',
    
    # 缓存策略
    'CacheStrategy',
    'LRUStrategy',
    'LFUStrategy',
    'TTLStrategy',
    'AdaptiveStrategy',
    
    # 缓存实现
    'MemoryCache',
    'MemoryCacheConfig',
    'RedisCache',
    'RedisCacheConfig',
    'DiskCache',
    'DiskCacheConfig',
    
    # 缓存协调器
    'CacheCoordinator',
    'CacheCoordinatorConfig',
    'CacheInstance',
    'CacheRoutingPolicy',
    'CacheSyncStrategy',
    
    # 性能优化器
    'PerformanceOptimizer',
    'PerformanceOptimizerConfig',
    'OptimizationType',
    'PredictionModel',
    'PerformanceMetric',
    'OptimizationRecommendation',
    'AccessPattern',
    
    # 便利函数
    'create_redis_cache',
    'create_disk_cache',
    'create_multi_level_cache',
    'create_performance_optimizer',
    
    # 常量
    'REDIS_AVAILABLE',
]

__version__ = "1.0.0" 