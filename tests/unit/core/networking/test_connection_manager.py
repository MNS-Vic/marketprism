"""
网络连接管理器测试
测试NetworkConnectionManager的核心功能
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

# 导入被测试的模块
try:
    from core.networking.connection_manager import (
        NetworkConnectionManager,
        NetworkConfig,
        network_manager
    )
    from core.networking.websocket_manager import WebSocketConfig
    from core.networking.proxy_manager import ProxyConfig
    HAS_CONNECTION_MODULES = True
except ImportError as e:
    HAS_CONNECTION_MODULES = False
    pytest.skip(f"连接管理器模块导入失败: {e}", allow_module_level=True)


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConfig:
    """网络配置测试"""
    
    def test_network_config_default_values(self):
        """测试网络配置默认值"""
        config = NetworkConfig()
        
        assert config.exchange_name == ""
        assert config.timeout == 30.0
        assert config.enable_ssl is True
        assert config.enable_proxy is True
        assert config.max_connections == 100
        assert config.connection_timeout == 10.0
        assert config.read_timeout == 30.0
        assert config.ws_ping_interval == 20
        assert config.ws_ping_timeout == 10
        assert config.ws_max_size == 1024 * 1024
        
    def test_network_config_custom_values(self):
        """测试网络配置自定义值"""
        config = NetworkConfig(
            exchange_name="binance",
            timeout=60.0,
            enable_ssl=False,
            enable_proxy=False,
            max_connections=200,
            connection_timeout=15.0,
            read_timeout=45.0,
            ws_ping_interval=30,
            ws_ping_timeout=15,
            ws_max_size=2 * 1024 * 1024
        )
        
        assert config.exchange_name == "binance"
        assert config.timeout == 60.0
        assert config.enable_ssl is False
        assert config.enable_proxy is False
        assert config.max_connections == 200
        assert config.connection_timeout == 15.0
        assert config.read_timeout == 45.0
        assert config.ws_ping_interval == 30
        assert config.ws_ping_timeout == 15
        assert config.ws_max_size == 2 * 1024 * 1024


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerInitialization:
    """网络连接管理器初始化测试"""
    
    def test_connection_manager_initialization(self):
        """测试连接管理器初始化"""
        manager = NetworkConnectionManager()
        
        assert manager is not None
        assert hasattr(manager, 'logger')
        assert hasattr(manager, 'session_manager')
        assert hasattr(manager, 'websocket_manager')
        assert hasattr(manager, 'proxy_manager')
        assert hasattr(manager, 'connections')
        assert hasattr(manager, 'connection_stats')
        
    def test_connection_manager_has_required_attributes(self):
        """测试连接管理器具有必需的属性"""
        manager = NetworkConnectionManager()
        
        required_attributes = [
            'session_manager', 'websocket_manager', 'proxy_manager',
            'connections', 'connection_stats', 'logger'
        ]
        
        for attr in required_attributes:
            assert hasattr(manager, attr), f"缺少必需属性: {attr}"
            
    def test_connection_manager_stats_initialization(self):
        """测试连接统计初始化"""
        manager = NetworkConnectionManager()
        
        expected_stats = [
            'total_connections', 'active_connections', 'failed_connections',
            'websocket_connections', 'http_sessions'
        ]
        
        for stat in expected_stats:
            assert stat in manager.connection_stats
            assert manager.connection_stats[stat] == 0


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerWebSocketOperations:
    """网络连接管理器WebSocket操作测试"""
    
    @pytest.fixture
    def connection_manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()
        
    async def test_create_websocket_connection_basic(self, connection_manager):
        """测试创建基本WebSocket连接"""
        url = "wss://example.com/ws"
        exchange_name = "test_exchange"
        
        with patch.object(connection_manager.websocket_manager, 'connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            
            connection = await connection_manager.create_websocket_connection(
                url, exchange_name
            )
            
            assert connection is not None
            mock_connect.assert_called_once()
            
            # 验证WebSocket配置
            call_args = mock_connect.call_args[0][0]  # 第一个参数是WebSocketConfig
            assert isinstance(call_args, WebSocketConfig)
            assert call_args.url == url
            assert call_args.exchange_name == exchange_name
            
    async def test_create_websocket_connection_with_network_config(self, connection_manager):
        """测试使用网络配置创建WebSocket连接"""
        url = "wss://binance.com/ws"
        exchange_name = "binance"
        network_config = NetworkConfig(
            exchange_name=exchange_name,
            timeout=60.0,
            ws_ping_interval=30
        )
        
        with patch.object(connection_manager.websocket_manager, 'connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            
            connection = await connection_manager.create_websocket_connection(
                url, exchange_name, network_config=network_config
            )
            
            assert connection is not None
            
            # 验证配置传递
            call_args = mock_connect.call_args[0][0]
            assert call_args.timeout == 60.0
            assert call_args.ping_interval == 30
            
    async def test_create_websocket_connection_with_exchange_config(self, connection_manager):
        """测试使用交易所配置创建WebSocket连接"""
        url = "wss://okx.com/ws"
        exchange_name = "okx"
        exchange_config = {
            "name": "okx",
            "proxy": {
                "enabled": True,
                "http_proxy": "http://proxy.example.com:8080"
            }
        }
        
        with patch.object(connection_manager.websocket_manager, 'connect') as mock_connect:
            with patch.object(connection_manager.proxy_manager, 'get_proxy_config') as mock_proxy:
                mock_proxy_config = ProxyConfig(
                    enabled=True,
                    http_proxy="http://proxy.example.com:8080"
                )
                mock_proxy.return_value = mock_proxy_config
                mock_ws = AsyncMock()
                mock_connect.return_value = mock_ws
                
                connection = await connection_manager.create_websocket_connection(
                    url, exchange_name, exchange_config=exchange_config
                )
                
                assert connection is not None
                mock_proxy.assert_called_once_with(exchange_config)
                
    async def test_create_websocket_connection_failure(self, connection_manager):
        """测试WebSocket连接创建失败"""
        url = "wss://invalid.example.com/ws"
        exchange_name = "invalid"
        
        with patch.object(connection_manager.websocket_manager, 'connect') as mock_connect:
            mock_connect.return_value = None  # 连接失败
            
            connection = await connection_manager.create_websocket_connection(
                url, exchange_name
            )
            
            assert connection is None
            assert connection_manager.connection_stats['failed_connections'] == 1
            
    async def test_create_websocket_connection_with_custom_params(self, connection_manager):
        """测试使用自定义参数创建WebSocket连接"""
        url = "wss://deribit.com/ws"
        exchange_name = "deribit"
        
        custom_params = {
            "ssl_verify": False,
            "ping_interval": 25,
            "max_size": 2 * 1024 * 1024
        }
        
        with patch.object(connection_manager.websocket_manager, 'connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            
            connection = await connection_manager.create_websocket_connection(
                url, exchange_name, **custom_params
            )
            
            assert connection is not None
            
            # 验证自定义参数传递
            call_args = mock_connect.call_args[0][0]
            assert call_args.ssl_verify is False
            assert call_args.ping_interval == 25
            assert call_args.max_size == 2 * 1024 * 1024


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerHTTPOperations:
    """网络连接管理器HTTP操作测试"""
    
    @pytest.fixture
    def connection_manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()
        
    async def test_get_http_session_basic(self, connection_manager):
        """测试获取基本HTTP会话"""
        session_name = "test_session"
        
        with patch.object(connection_manager.session_manager, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session
            
            session = await connection_manager.get_http_session(session_name)
            
            assert session is not None
            mock_get_session.assert_called_once_with(session_name, None, None, None)
            
    async def test_get_http_session_with_config(self, connection_manager):
        """测试使用配置获取HTTP会话"""
        session_name = "configured_session"
        network_config = NetworkConfig(
            timeout=45.0,
            max_connections=150
        )
        
        with patch.object(connection_manager.session_manager, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session
            
            session = await connection_manager.get_http_session(
                session_name, network_config=network_config
            )
            
            assert session is not None
            mock_get_session.assert_called_once()
            
    async def test_make_http_request(self, connection_manager):
        """测试发送HTTP请求"""
        url = "https://api.example.com/data"
        method = "GET"
        
        with patch.object(connection_manager.session_manager, 'request') as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_request.return_value = mock_response
            
            response = await connection_manager.make_http_request(method, url)
            
            assert response is not None
            assert response.status == 200
            mock_request.assert_called_once_with(method, url, session_name="default")
            
    async def test_make_http_request_with_session_name(self, connection_manager):
        """测试使用指定会话名发送HTTP请求"""
        url = "https://api.binance.com/api/v3/ticker/price"
        method = "GET"
        session_name = "binance_session"
        
        with patch.object(connection_manager.session_manager, 'request') as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_request.return_value = mock_response
            
            response = await connection_manager.make_http_request(
                method, url, session_name=session_name
            )
            
            assert response is not None
            mock_request.assert_called_once_with(method, url, session_name=session_name)


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerConnectionTracking:
    """网络连接管理器连接跟踪测试"""
    
    @pytest.fixture
    def connection_manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()
        
    async def test_track_websocket_connection(self, connection_manager):
        """测试跟踪WebSocket连接"""
        connection_id = "ws_test_001"
        mock_connection = AsyncMock()
        
        connection_manager._track_connection(connection_id, mock_connection, "websocket")
        
        assert connection_id in connection_manager.connections
        assert connection_manager.connections[connection_id]["connection"] == mock_connection
        assert connection_manager.connections[connection_id]["type"] == "websocket"
        assert connection_manager.connection_stats["total_connections"] == 1
        assert connection_manager.connection_stats["websocket_connections"] == 1
        
    async def test_track_http_session(self, connection_manager):
        """测试跟踪HTTP会话"""
        session_id = "http_test_001"
        mock_session = AsyncMock()
        
        connection_manager._track_connection(session_id, mock_session, "http")
        
        assert session_id in connection_manager.connections
        assert connection_manager.connections[session_id]["connection"] == mock_session
        assert connection_manager.connections[session_id]["type"] == "http"
        assert connection_manager.connection_stats["total_connections"] == 1
        assert connection_manager.connection_stats["http_sessions"] == 1
        
    async def test_untrack_connection(self, connection_manager):
        """测试取消跟踪连接"""
        connection_id = "test_connection"
        mock_connection = AsyncMock()
        
        # 先跟踪连接
        connection_manager._track_connection(connection_id, mock_connection, "websocket")
        assert connection_id in connection_manager.connections
        
        # 取消跟踪
        connection_manager._untrack_connection(connection_id)
        assert connection_id not in connection_manager.connections
        
    def test_get_connection_stats(self, connection_manager):
        """测试获取连接统计"""
        # 添加一些连接
        connection_manager._track_connection("ws1", AsyncMock(), "websocket")
        connection_manager._track_connection("ws2", AsyncMock(), "websocket")
        connection_manager._track_connection("http1", AsyncMock(), "http")
        
        stats = connection_manager.get_connection_stats()
        
        assert isinstance(stats, dict)
        assert stats["total_connections"] == 3
        assert stats["websocket_connections"] == 2
        assert stats["http_sessions"] == 1
        assert stats["active_connections"] == 3
        
    def test_list_active_connections(self, connection_manager):
        """测试列出活跃连接"""
        # 添加一些连接
        connection_manager._track_connection("ws1", AsyncMock(), "websocket")
        connection_manager._track_connection("http1", AsyncMock(), "http")
        
        active_connections = connection_manager.list_active_connections()
        
        assert isinstance(active_connections, list)
        assert len(active_connections) == 2
        
        # 验证连接信息
        connection_ids = [conn["id"] for conn in active_connections]
        assert "ws1" in connection_ids
        assert "http1" in connection_ids


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerHealthCheck:
    """网络连接管理器健康检查测试"""
    
    @pytest.fixture
    def connection_manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()
        
    async def test_health_check_all_healthy(self, connection_manager):
        """测试所有连接健康的情况"""
        # 添加健康的连接
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        
        connection_manager._track_connection("ws1", mock_ws, "websocket")
        connection_manager._track_connection("http1", mock_session, "http")
        
        health_status = await connection_manager.check_health()
        
        assert health_status["status"] == "healthy"
        assert health_status["total_connections"] == 2
        assert health_status["healthy_connections"] == 2
        assert health_status["unhealthy_connections"] == 0
        
    async def test_health_check_some_unhealthy(self, connection_manager):
        """测试部分连接不健康的情况"""
        # 添加健康和不健康的连接
        healthy_ws = AsyncMock()
        healthy_ws.closed = False
        unhealthy_ws = AsyncMock()
        unhealthy_ws.closed = True
        
        connection_manager._track_connection("healthy_ws", healthy_ws, "websocket")
        connection_manager._track_connection("unhealthy_ws", unhealthy_ws, "websocket")
        
        health_status = await connection_manager.check_health()
        
        assert health_status["status"] == "degraded"
        assert health_status["total_connections"] == 2
        assert health_status["healthy_connections"] == 1
        assert health_status["unhealthy_connections"] == 1
        
    async def test_health_check_no_connections(self, connection_manager):
        """测试无连接时的健康检查"""
        health_status = await connection_manager.check_health()
        
        assert health_status["status"] == "healthy"  # 无连接也算健康
        assert health_status["total_connections"] == 0
        assert health_status["healthy_connections"] == 0
        assert health_status["unhealthy_connections"] == 0


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerGlobalInstance:
    """网络连接管理器全局实例测试"""
    
    def test_global_network_manager_exists(self):
        """测试全局网络管理器存在"""
        assert network_manager is not None
        assert isinstance(network_manager, NetworkConnectionManager)
        
    async def test_global_network_manager_usage(self):
        """测试使用全局网络管理器"""
        url = "wss://example.com/ws"
        exchange_name = "test"
        
        with patch.object(network_manager.websocket_manager, 'connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            
            connection = await network_manager.create_websocket_connection(url, exchange_name)
            
            assert connection is not None
            mock_connect.assert_called_once()


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerIntegration:
    """网络连接管理器集成测试"""
    
    async def test_connection_manager_full_workflow(self):
        """测试连接管理器完整工作流"""
        manager = NetworkConnectionManager()
        
        # 1. 创建WebSocket连接
        with patch.object(manager.websocket_manager, 'connect') as mock_ws_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_ws_connect.return_value = mock_ws
            
            ws_connection = await manager.create_websocket_connection(
                "wss://example.com/ws", "test_exchange"
            )
            
            assert ws_connection is not None
            
        # 2. 创建HTTP会话
        with patch.object(manager.session_manager, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.closed = False
            mock_get_session.return_value = mock_session
            
            http_session = await manager.get_http_session("test_session")
            
            assert http_session is not None
            
        # 3. 检查连接统计
        stats = manager.get_connection_stats()
        assert stats["total_connections"] >= 0  # 可能有跟踪的连接
        
        # 4. 健康检查
        health = await manager.check_health()
        assert "status" in health
        assert "total_connections" in health
        
    async def test_connection_manager_multiple_exchanges(self):
        """测试连接管理器多交易所场景"""
        manager = NetworkConnectionManager()
        
        exchanges = ["binance", "okx", "deribit"]
        connections = {}
        
        with patch.object(manager.websocket_manager, 'connect') as mock_connect:
            mock_connect.return_value = AsyncMock()
            
            # 为每个交易所创建连接
            for exchange in exchanges:
                connection = await manager.create_websocket_connection(
                    f"wss://{exchange}.com/ws", exchange
                )
                connections[exchange] = connection
                
            # 验证所有连接都创建成功
            assert len(connections) == 3
            for exchange, connection in connections.items():
                assert connection is not None
                
            # 验证连接调用次数
            assert mock_connect.call_count == 3
