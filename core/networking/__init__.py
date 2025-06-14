"""
MarketPrism 核心网络模块

提供统一的网络连接管理：
- 统一HTTP会话管理（整合重复功能）
- WebSocket连接管理
- 代理配置管理
- 连接池管理
- SSL/TLS配置
- 重试和重连机制
- 增强的交易所连接器
"""

from datetime import datetime, timezone
import warnings

# 主要导入 - 统一会话管理器（整合重复功能）
from .unified_session_manager import (
    UnifiedSessionManager,
    UnifiedSessionManager as AioHTTPSessionManager, # 向后兼容
    UnifiedSessionConfig
)

# 其他网络组件
from .proxy_manager import ProxyConfigManager, ProxyConfig, proxy_manager
from .websocket_manager import WebSocketConnectionManager, WebSocketConfig, websocket_manager, BaseWebSocketClient
from .connection_manager import NetworkConnectionManager, NetworkConfig, network_manager
from .enhanced_exchange_connector import (
    EnhancedExchangeConnector,
    ExchangeConfig,
    create_exchange_connector,
    EXCHANGE_CONFIGS,
    BinanceErrorHandler
)

# 向后兼容函数
def get_session_manager(*args, **kwargs):
    """废弃：请使用 unified_session_manager"""
    warnings.warn(
        "get_session_manager 已废弃，请使用 unified_session_manager",
        DeprecationWarning,
        stacklevel=2
    )
    return unified_session_manager

async def close_global_session_manager():
    """废弃：请使用 unified_session_manager.close()"""
    warnings.warn(
        "close_global_session_manager 已废弃，请使用 unified_session_manager.close()",
        DeprecationWarning,
        stacklevel=2
    )
    await unified_session_manager.close()

# 全局实例
unified_session_manager = UnifiedSessionManager()

__all__ = [
    # 统一会话管理（推荐使用）
    'UnifiedSessionManager',
    'AioHTTPSessionManager',
    'UnifiedSessionConfig', 
    'unified_session_manager',
    
    # 向后兼容（已废弃但保留）
    'HTTPSessionManager',
    'SessionManager',
    'SessionConfig',
    'session_manager',
    'get_session_manager',
    'close_global_session_manager',
    
    # 网络组件
    'NetworkConnectionManager',
    'NetworkConfig',
    'network_manager',
    'ProxyConfigManager', 
    'ProxyConfig',
    'proxy_manager',
    'WebSocketConnectionManager',
    'WebSocketConfig',
    'websocket_manager',
    'BaseWebSocketClient',
    
    # 交易所连接器
    'EnhancedExchangeConnector',
    'ExchangeConfig',
    'create_exchange_connector',
    'EXCHANGE_CONFIGS',
    'BinanceErrorHandler'
]