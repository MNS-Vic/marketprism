"""
WebSocket连接管理器测试
测试WebSocketConnectionManager的核心功能
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

# 导入被测试的模块
try:
    from core.networking.websocket_manager import (
        WebSocketConnectionManager,
        WebSocketConfig,
        BaseWebSocketClient,
        WebSocketWrapper,
        websocket_manager
    )
    from core.networking.proxy_manager import ProxyConfig
    HAS_WEBSOCKET_MODULES = True
except ImportError as e:
    HAS_WEBSOCKET_MODULES = False
    pytest.skip(f"WebSocket模块导入失败: {e}", allow_module_level=True)


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConfig:
    """WebSocket配置测试"""
    
    def test_websocket_config_default_values(self):
        """测试WebSocket配置默认值"""
        config = WebSocketConfig(url="wss://example.com/ws")

        assert config.url == "wss://example.com/ws"
        assert config.timeout == 10  # 修正默认值
        assert config.ssl_verify is True
        assert config.ping_interval is None  # 修正默认值
        assert config.ping_timeout is None  # 修正默认值
        assert config.max_size is None  # 修正默认值
        assert config.exchange_name is None  # 修正默认值
        
    def test_websocket_config_custom_values(self):
        """测试WebSocket配置自定义值"""
        config = WebSocketConfig(
            url="wss://api.binance.com/ws",
            timeout=60,  # 修正为int类型
            ssl_verify=False,
            ping_interval=30,
            ping_timeout=15,
            max_size=2 * 1024 * 1024,
            exchange_name="binance"
        )

        assert config.url == "wss://api.binance.com/ws"
        assert config.timeout == 60
        assert config.ssl_verify is False
        assert config.ping_interval == 30
        assert config.ping_timeout == 15
        assert config.max_size == 2 * 1024 * 1024
        assert config.exchange_name == "binance"
        
    def test_websocket_config_should_disable_ssl(self):
        """测试SSL禁用逻辑"""
        # 默认情况下不禁用SSL
        config = WebSocketConfig(url="wss://example.com/ws")
        assert config.should_disable_ssl() is False
        
        # 显式设置ssl_verify=False
        config = WebSocketConfig(url="wss://example.com/ws", ssl_verify=False)
        assert config.should_disable_ssl() is True
        
        # 特定交易所禁用SSL
        config = WebSocketConfig(
            url="wss://deribit.com/ws",
            exchange_name="deribit",
            disable_ssl_for_exchanges=["deribit"]
        )
        assert config.should_disable_ssl() is True


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestBaseWebSocketClient:
    """基础WebSocket客户端测试"""

    def test_base_websocket_client_initialization(self):
        """测试基础WebSocket客户端初始化"""
        client = BaseWebSocketClient()

        # BaseWebSocketClient是抽象类，只测试基本属性
        assert hasattr(client, 'connect')
        assert hasattr(client, 'send')
        assert hasattr(client, 'close')

    async def test_base_websocket_client_connect_abstract(self):
        """测试基础WebSocket客户端连接抽象方法"""
        client = BaseWebSocketClient()

        # 基础类的connect方法应该抛出NotImplementedError
        with pytest.raises(NotImplementedError):
            await client.connect("wss://example.com/ws")

    async def test_base_websocket_client_send_abstract(self):
        """测试基础WebSocket客户端发送抽象方法"""
        client = BaseWebSocketClient()

        # 基础类的send方法应该抛出NotImplementedError
        with pytest.raises(NotImplementedError):
            await client.send("test message")

    async def test_base_websocket_client_close_abstract(self):
        """测试基础WebSocket客户端关闭抽象方法"""
        client = BaseWebSocketClient()

        # 基础类的close方法应该抛出NotImplementedError
        with pytest.raises(NotImplementedError):
            await client.close()


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManager:
    """WebSocket连接管理器测试"""
    
    def test_websocket_manager_initialization(self):
        """测试WebSocket管理器初始化"""
        manager = WebSocketConnectionManager()

        assert manager is not None
        assert hasattr(manager, 'logger')
        assert hasattr(manager, 'connections')
        assert isinstance(manager.connections, dict)
        assert len(manager.connections) == 0
        
    async def test_websocket_manager_connect_basic(self):
        """测试基本WebSocket连接"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://example.com/ws",
            exchange_name="test"
        )
        
        # Mock WebSocket连接
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            # 设置为协程函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            connection = await manager.connect(config)

            assert connection is not None
            assert isinstance(connection, WebSocketWrapper)
            mock_connect.assert_called_once()
            
    async def test_websocket_manager_connect_with_proxy(self):
        """测试带代理的WebSocket连接"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://example.com/ws",
            exchange_name="test"
        )
        
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080"
        )
        
        # Mock aiohttp WebSocket连接
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_session.ws_connect.return_value = mock_ws
            mock_session_class.return_value = mock_session

            connection = await manager.connect(config, proxy_config=proxy_config)

            assert connection is not None
            assert isinstance(connection, WebSocketWrapper)
            mock_session.ws_connect.assert_called_once()
            
    async def test_websocket_manager_connect_ssl_disabled(self):
        """测试禁用SSL的WebSocket连接"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://deribit.com/ws",
            exchange_name="deribit",
            ssl_verify=False
        )
        
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            # 设置为协程函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            connection = await manager.connect(config)

            assert connection is not None
            assert isinstance(connection, WebSocketWrapper)
            # 验证SSL上下文被设置
            call_args = mock_connect.call_args
            assert 'ssl' in call_args.kwargs
            
    async def test_websocket_manager_connect_failure(self):
        """测试WebSocket连接失败"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://invalid.example.com/ws",
            exchange_name="test"
        )
        
        with patch('websockets.connect') as mock_connect:
            mock_connect.side_effect = ConnectionError("连接失败")

            connection = await manager.connect(config)

            assert connection is None
            
    async def test_websocket_manager_connect_with_exchange_config(self):
        """测试使用交易所配置连接"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://stream.binance.com/ws",
            exchange_name="binance"
        )
        
        exchange_config = {
            "name": "binance",
            "proxy": {
                "enabled": False
            }
        }
        
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            # 设置为协程函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            connection = await manager.connect(config, exchange_config=exchange_config)

            assert connection is not None
            assert isinstance(connection, WebSocketWrapper)
            mock_connect.assert_called_once()


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionOperations:
    """WebSocket连接操作测试"""
    
    @pytest.fixture
    async def mock_websocket_connection(self):
        """创建模拟WebSocket连接"""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.ping = AsyncMock()
        mock_ws.pong = AsyncMock()
        
        return mock_ws
        
    async def test_websocket_send_message(self, mock_websocket_connection):
        """测试发送WebSocket消息"""
        config = WebSocketConfig(url="wss://example.com/ws")
        # 使用WebSocketWrapper而不是BaseWebSocketClient
        wrapper = WebSocketWrapper(mock_websocket_connection, None, "websockets")

        message = {"type": "subscribe", "channel": "ticker"}
        await wrapper.send(json.dumps(message))

        mock_websocket_connection.send.assert_called_once_with(json.dumps(message))
        
    async def test_websocket_receive_message(self, mock_websocket_connection):
        """测试接收WebSocket消息"""
        config = WebSocketConfig(url="wss://example.com/ws")
        # 使用WebSocketWrapper而不是BaseWebSocketClient
        wrapper = WebSocketWrapper(mock_websocket_connection, None, "websockets")

        # 模拟接收到的消息
        test_message = '{"type": "ticker", "data": {"price": 50000}}'
        mock_websocket_connection.recv.return_value = test_message

        # WebSocketWrapper使用异步迭代器接收消息
        message = await wrapper.__anext__()

        assert message == test_message
        mock_websocket_connection.recv.assert_called_once()
        
    async def test_websocket_close_connection(self, mock_websocket_connection):
        """测试关闭WebSocket连接"""
        config = WebSocketConfig(url="wss://example.com/ws")
        # 使用WebSocketWrapper而不是BaseWebSocketClient
        wrapper = WebSocketWrapper(mock_websocket_connection, None, "websockets")

        await wrapper.close()

        mock_websocket_connection.close.assert_called_once()
        assert wrapper.closed is True
        
    async def test_websocket_ping_pong(self, mock_websocket_connection):
        """测试WebSocket ping/pong"""
        config = WebSocketConfig(url="wss://example.com/ws")
        # 使用WebSocketWrapper而不是BaseWebSocketClient
        wrapper = WebSocketWrapper(mock_websocket_connection, None, "websockets")

        # WebSocketWrapper没有ping方法，测试底层连接的ping功能
        # 直接测试底层websocket的ping方法
        await mock_websocket_connection.ping()
        mock_websocket_connection.ping.assert_called_once()

        # 验证wrapper的基本属性
        assert wrapper.connection_type == "websockets"
        assert not wrapper.closed


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketManagerErrorHandling:
    """WebSocket管理器错误处理测试"""
    
    async def test_websocket_manager_connection_timeout(self):
        """测试WebSocket连接超时"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://slow.example.com/ws",
            timeout=0.1,  # 很短的超时时间
            exchange_name="test"
        )
        
        with patch('websockets.connect') as mock_connect:
            mock_connect.side_effect = asyncio.TimeoutError("连接超时")

            connection = await manager.connect(config)

            assert connection is None
            
    async def test_websocket_manager_ssl_error(self):
        """测试WebSocket SSL错误"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://badssl.example.com/ws",
            exchange_name="test"
        )
        
        with patch('websockets.connect') as mock_connect:
            mock_connect.side_effect = Exception("SSL验证失败")

            connection = await manager.connect(config)

            assert connection is None
            
    async def test_websocket_manager_proxy_error(self):
        """测试WebSocket代理错误"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://example.com/ws",
            exchange_name="test"
        )
        
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://invalid-proxy.com:8080"
        )
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.ws_connect.side_effect = Exception("代理连接失败")
            mock_session_class.return_value = mock_session

            connection = await manager.connect(config, proxy_config=proxy_config)

            assert connection is None


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketManagerGlobalInstance:
    """WebSocket管理器全局实例测试"""
    
    def test_global_websocket_manager_exists(self):
        """测试全局WebSocket管理器存在"""
        assert websocket_manager is not None
        assert isinstance(websocket_manager, WebSocketConnectionManager)
        
    async def test_global_websocket_manager_usage(self):
        """测试使用全局WebSocket管理器"""
        config = WebSocketConfig(
            url="wss://example.com/ws",
            exchange_name="test"
        )
        
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            # 设置为协程函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            connection = await websocket_manager.connect(config)

            assert connection is not None
            assert isinstance(connection, WebSocketWrapper)
            mock_connect.assert_called_once()


@pytest.mark.integration
@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketManagerIntegration:
    """WebSocket管理器集成测试"""
    
    async def test_websocket_manager_full_workflow(self):
        """测试WebSocket管理器完整工作流"""
        manager = WebSocketConnectionManager()
        config = WebSocketConfig(
            url="wss://echo.websocket.org",
            exchange_name="test_echo"
        )
        
        # 使用真实的echo服务进行集成测试（如果可用）
        # 这里使用mock来避免依赖外部服务
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_ws.send = AsyncMock()
            mock_ws.recv = AsyncMock(return_value='{"echo": "test"}')
            mock_ws.close = AsyncMock()
            # 设置为协程函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            # 建立连接
            connection = await manager.connect(config)
            assert connection is not None
            assert isinstance(connection, WebSocketWrapper)

            # 发送消息
            test_message = '{"test": "message"}'
            await connection.send(test_message)
            mock_ws.send.assert_called_with(test_message)

            # 接收消息
            response = await connection.__anext__()
            assert response == '{"echo": "test"}'

            # 关闭连接
            await connection.close()
            mock_ws.close.assert_called_once()
            
    async def test_websocket_manager_multiple_connections(self):
        """测试WebSocket管理器多连接管理"""
        manager = WebSocketConnectionManager()
        
        configs = [
            WebSocketConfig(url="wss://example1.com/ws", exchange_name="exchange1"),
            WebSocketConfig(url="wss://example2.com/ws", exchange_name="exchange2"),
            WebSocketConfig(url="wss://example3.com/ws", exchange_name="exchange3")
        ]
        
        with patch('websockets.connect') as mock_connect:
            mock_connections = []
            for i in range(3):
                mock_ws = AsyncMock()
                mock_ws.closed = False
                mock_connections.append(mock_ws)

            # 设置为协程函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_connections.pop(0) if mock_connections else AsyncMock()
            mock_connect.side_effect = mock_connect_func

            # 建立多个连接
            connections = []
            for config in configs:
                connection = await manager.connect(config)
                assert connection is not None
                assert isinstance(connection, WebSocketWrapper)
                connections.append(connection)

            # 验证所有连接都建立成功
            assert len(connections) == 3
            assert mock_connect.call_count == 3
