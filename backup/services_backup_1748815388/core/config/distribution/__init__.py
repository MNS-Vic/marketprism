"""
MarketPrism 分布式配置管理系统
提供企业级的配置分发、同步和订阅功能
"""

from .config_server import ConfigServer, ServerStatus, ServerMetrics
from .config_client import ConfigClient, ClientStatus, CacheLevel, ConfigChangeEvent, ClientMetrics
from .config_sync import ConfigSync, SyncStatus, SyncStrategy, ConflictResolution, SyncResult, SyncConflict, SyncMetrics
from .config_subscription import ConfigSubscription, SubscriptionStatus, EventType, FilterType, ConfigEvent, Subscription, SubscriptionFilter, SubscriptionMetrics

__all__ = [
    # 配置服务器
    'ConfigServer',
    'ServerStatus', 
    'ServerMetrics',
    
    # 配置客户端
    'ConfigClient',
    'ClientStatus',
    'CacheLevel',
    'ConfigChangeEvent',
    'ClientMetrics',
    
    # 配置同步
    'ConfigSync',
    'SyncStatus',
    'SyncStrategy', 
    'ConflictResolution',
    'SyncResult',
    'SyncConflict',
    'SyncMetrics',
    
    # 配置订阅
    'ConfigSubscription',
    'SubscriptionStatus',
    'EventType',
    'FilterType', 
    'ConfigEvent',
    'Subscription',
    'SubscriptionFilter',
    'SubscriptionMetrics'
]

# 版本信息
__version__ = '1.0.0'
__author__ = 'MarketPrism Team'
__description__ = '企业级分布式配置管理系统'

# 默认配置
DEFAULT_SERVER_CONFIG = {
    'host': 'localhost',
    'port': 8080,
    'websocket_port': 8081,
    'enable_auth': True,
    'max_connections': 10000,
    'secret_key': 'marketprism-config-server'
}

DEFAULT_CLIENT_CONFIG = {
    'server_url': 'http://localhost:8080',
    'websocket_url': 'ws://localhost:8081', 
    'cache_level': CacheLevel.MEMORY_AND_DISK,
    'auto_reconnect': True,
    'reconnect_interval': 5,
    'request_timeout': 30,
    'heartbeat_interval': 30
}

DEFAULT_SYNC_CONFIG = {
    'sync_interval': 300,  # 5分钟
    'max_concurrent_syncs': 10,
    'enable_auto_sync': True,
    'default_conflict_resolution': ConflictResolution.SERVER_WINS
}

DEFAULT_SUBSCRIPTION_CONFIG = {
    'max_subscriptions': 10000,
    'max_events_per_second': 10000,
    'event_retention_hours': 24,
    'enable_batch_delivery': True,
    'worker_threads': 5
}


def create_config_server(
    config_repository,
    version_control=None,
    **kwargs
) -> ConfigServer:
    """
    创建配置服务器实例
    
    Args:
        config_repository: 配置仓库
        version_control: 版本控制系统
        **kwargs: 额外配置参数
        
    Returns:
        ConfigServer实例
    """
    config = DEFAULT_SERVER_CONFIG.copy()
    config.update(kwargs)
    
    return ConfigServer(
        config_repository=config_repository,
        version_control=version_control,
        **config
    )


def create_config_client(**kwargs) -> ConfigClient:
    """
    创建配置客户端实例
    
    Args:
        **kwargs: 配置参数
        
    Returns:
        ConfigClient实例
    """
    config = DEFAULT_CLIENT_CONFIG.copy()
    config.update(kwargs)
    
    return ConfigClient(**config)


def create_config_sync(
    local_repository,
    remote_repository,
    version_control=None,
    **kwargs
) -> ConfigSync:
    """
    创建配置同步器实例
    
    Args:
        local_repository: 本地配置仓库
        remote_repository: 远程配置仓库
        version_control: 版本控制系统
        **kwargs: 额外配置参数
        
    Returns:
        ConfigSync实例
    """
    config = DEFAULT_SYNC_CONFIG.copy()
    config.update(kwargs)
    
    return ConfigSync(
        local_repository=local_repository,
        remote_repository=remote_repository,
        version_control=version_control,
        **config
    )


def create_config_subscription(
    config_repository=None,
    **kwargs
) -> ConfigSubscription:
    """
    创建配置订阅系统实例
    
    Args:
        config_repository: 配置仓库
        **kwargs: 额外配置参数
        
    Returns:
        ConfigSubscription实例
    """
    config = DEFAULT_SUBSCRIPTION_CONFIG.copy()
    config.update(kwargs)
    
    return ConfigSubscription(
        config_repository=config_repository,
        **config
    )