"""
MarketPrism 核心网络模块

提供统一的网络连接管理：
- WebSocket连接管理
- HTTP会话管理  
- 代理配置管理
- 连接池管理
- SSL/TLS配置
- 重试和重连机制
"""

from .proxy_manager import ProxyConfigManager, ProxyConfig, proxy_manager
from .websocket_manager import WebSocketConnectionManager, WebSocketConfig, websocket_manager
from .session_manager import HTTPSessionManager, SessionConfig, session_manager
from .connection_manager import NetworkConnectionManager, NetworkConfig, network_manager

__all__ = [
    'NetworkConnectionManager',
    'NetworkConfig',
    'network_manager',
    'ProxyConfigManager', 
    'ProxyConfig',
    'proxy_manager',
    'WebSocketConnectionManager',
    'WebSocketConfig',
    'websocket_manager',
    'HTTPSessionManager',
    'SessionConfig',
    'session_manager'
]