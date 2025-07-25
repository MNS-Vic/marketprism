"""
WebSocket管理器增强TDD测试
专注于提升覆盖率到45%+，测试未覆盖的边缘情况和错误处理
"""

import pytest
import asyncio
import aiohttp
import websockets
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

try:
    from core.networking.websocket_manager import (
        WebSocketConnectionManager, WebSocketConfig, BaseWebSocketClient,
        WebSocketWrapper, websocket_manager
    )
    from core.networking.proxy_manager import ProxyConfig
    HAS_WEBSOCKET_MODULES = True
except ImportError:
    HAS_WEBSOCKET_MODULES = False


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketWrapperEdgeCases:
    """测试WebSocket包装器边缘情况"""
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_close_already_closed(self):
        """测试：关闭已经关闭的连接"""
        mock_ws = AsyncMock()
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        wrapper.closed = True
        
        # 关闭已经关闭的连接应该直接返回
        await wrapper.close()
        
        # 验证底层WebSocket的close方法没有被调用
        mock_ws.close.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_close_with_exception(self):
        """测试：关闭连接时发生异常"""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close.side_effect = Exception("Close failed")

        wrapper = WebSocketWrapper(mock_ws, None, "websockets")

        # 关闭时发生异常应该被捕获，不抛出
        await wrapper.close()

        # 验证连接状态：实际实现中，异常发生时closed不会被设置为True
        # 因为self.closed = True在try块中，异常发生后不会执行
        assert wrapper.closed is False
    
    def test_websocket_wrapper_aiter(self):
        """测试：WebSocket包装器异步迭代器"""
        mock_ws = AsyncMock()
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        
        # __aiter__ 应该返回自身
        result = wrapper.__aiter__()
        assert result is wrapper
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_anext_aiohttp_binary_message(self):
        """测试：aiohttp WebSocket接收二进制消息"""
        mock_ws = AsyncMock()
        mock_msg = Mock()
        mock_msg.type = aiohttp.WSMsgType.BINARY
        mock_msg.data = b"binary message"
        mock_ws.receive.return_value = mock_msg
        
        wrapper = WebSocketWrapper(mock_ws, None, "aiohttp")
        
        message = await wrapper.__anext__()
        
        assert message == "binary message"
        mock_ws.receive.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_anext_aiohttp_close_message(self):
        """测试：aiohttp WebSocket接收关闭消息"""
        mock_ws = AsyncMock()
        mock_msg = Mock()
        mock_msg.type = aiohttp.WSMsgType.CLOSE
        mock_ws.receive.return_value = mock_msg
        
        wrapper = WebSocketWrapper(mock_ws, None, "aiohttp")
        
        with pytest.raises(StopAsyncIteration):
            await wrapper.__anext__()
        
        assert wrapper.closed is True
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_anext_aiohttp_error_message(self):
        """测试：aiohttp WebSocket接收错误消息"""
        mock_ws = AsyncMock()
        mock_msg = Mock()
        mock_msg.type = aiohttp.WSMsgType.ERROR
        mock_ws.receive.return_value = mock_msg
        
        wrapper = WebSocketWrapper(mock_ws, None, "aiohttp")
        
        with pytest.raises(StopAsyncIteration):
            await wrapper.__anext__()
        
        assert wrapper.closed is True
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_anext_aiohttp_other_message_recursive(self):
        """测试：aiohttp WebSocket接收其他类型消息（递归处理）"""
        mock_ws = AsyncMock()
        
        # 第一次返回其他类型消息，第二次返回文本消息
        mock_msg_other = Mock()
        mock_msg_other.type = aiohttp.WSMsgType.PING  # 其他类型
        
        mock_msg_text = Mock()
        mock_msg_text.type = aiohttp.WSMsgType.TEXT
        mock_msg_text.data = "text message"
        
        mock_ws.receive.side_effect = [mock_msg_other, mock_msg_text]
        
        wrapper = WebSocketWrapper(mock_ws, None, "aiohttp")
        
        message = await wrapper.__anext__()
        
        assert message == "text message"
        assert mock_ws.receive.call_count == 2
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_anext_websockets_connection_closed(self):
        """测试：websockets库连接关闭异常"""
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = websockets.exceptions.ConnectionClosed(None, None)
        
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        
        with pytest.raises(StopAsyncIteration):
            await wrapper.__anext__()
        
        assert wrapper.closed is True
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_anext_general_exception(self):
        """测试：接收消息时发生一般异常"""
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = Exception("Receive failed")
        
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        
        with pytest.raises(StopAsyncIteration):
            await wrapper.__anext__()
        
        assert wrapper.closed is True


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManagerEdgeCases:
    """测试WebSocket连接管理器边缘情况"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()
    
    @pytest.mark.asyncio
    async def test_connect_general_exception_in_main_method(self, manager):
        """测试：连接方法中的一般异常处理"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )
        
        # 模拟proxy_manager.get_proxy_config抛出异常
        with patch('core.networking.websocket_manager.proxy_manager') as mock_proxy_manager:
            mock_proxy_manager.get_proxy_config.side_effect = Exception("Proxy config failed")
            
            result = await manager.connect(config)
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_proxy_no_proxy_url(self, manager):
        """测试：aiohttp代理连接但代理URL为空"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )
        
        proxy_config = Mock(spec=ProxyConfig)
        proxy_config.to_aiohttp_proxy.return_value = None  # 返回空代理URL
        
        result = await manager._connect_with_aiohttp_proxy(config, proxy_config)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_proxy_old_version_compatibility(self, manager):
        """测试：aiohttp旧版本兼容性处理"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )
        
        proxy_config = Mock(spec=ProxyConfig)
        proxy_config.to_aiohttp_proxy.return_value = "http://proxy.example.com:8080"
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            # 第一次调用抛出TypeError（模拟旧版本），第二次成功
            mock_session = AsyncMock()
            mock_ws = AsyncMock()
            mock_session.ws_connect.return_value = mock_ws
            
            def session_side_effect(*args, **kwargs):
                if 'trust_env' in kwargs:
                    raise TypeError("trust_env not supported")
                return mock_session
            
            mock_session_class.side_effect = session_side_effect
            
            result = await manager._connect_with_aiohttp_proxy(config, proxy_config)
            
            assert isinstance(result, WebSocketWrapper)
            # 验证调用了两次（第一次失败，第二次成功）
            assert mock_session_class.call_count == 2
    
    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_proxy_with_optional_params(self, manager):
        """测试：aiohttp代理连接包含所有可选参数"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test",
            extra_headers={"Authorization": "Bearer token"},
            subprotocols=["v1", "v2"],
            max_size=4096
        )
        
        proxy_config = Mock(spec=ProxyConfig)
        proxy_config.to_aiohttp_proxy.return_value = "http://proxy.example.com:8080"
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_ws = AsyncMock()
            mock_session.ws_connect.return_value = mock_ws
            mock_session_class.return_value = mock_session
            
            result = await manager._connect_with_aiohttp_proxy(config, proxy_config)
            
            assert isinstance(result, WebSocketWrapper)
            
            # 验证连接参数包含所有可选参数
            call_kwargs = mock_session.ws_connect.call_args.kwargs
            assert call_kwargs['headers'] == {"Authorization": "Bearer token"}
            assert call_kwargs['protocols'] == ["v1", "v2"]
            assert call_kwargs['max_msg_size'] == 4096


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManagerReconnection:
    """测试WebSocket连接管理器重连功能"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()
    
    @pytest.mark.asyncio
    async def test_connection_caching_and_retrieval(self, manager):
        """测试：连接缓存和检索"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test_exchange"
        )
        
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func
            
            # 建立连接
            connection = await manager.connect(config)
            assert connection is not None
            
            # 验证连接被缓存
            connection_key = "test_exchange_wss://api.example.com/ws"
            cached_connection = manager.get_connection(connection_key)
            assert cached_connection is connection
            
            # 验证连接统计
            stats = manager.get_connection_stats()
            assert stats['total_connections'] == 1
            assert stats['active_connections'] == 1
            assert connection_key in stats['connections']
    
    @pytest.mark.asyncio
    async def test_connection_stats_with_closed_connections(self, manager):
        """测试：包含已关闭连接的连接统计"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test_exchange"
        )
        
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func
            
            # 建立连接
            connection = await manager.connect(config)
            assert connection is not None
            
            # 关闭连接
            connection.closed = True
            
            # 验证连接统计
            stats = manager.get_connection_stats()
            assert stats['total_connections'] == 1
            assert stats['active_connections'] == 0  # 已关闭的连接不计入活跃连接


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManagerErrorRecovery:
    """测试WebSocket连接管理器错误恢复"""

    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()

    @pytest.mark.asyncio
    async def test_connect_direct_exception_handling(self, manager):
        """测试：直接连接异常处理"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        with patch.object(manager, '_connect_with_websockets') as mock_websockets:
            with patch('core.networking.websocket_manager.proxy_manager') as mock_proxy_manager:
                # 模拟无代理环境
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = False
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                # 模拟websockets连接抛出异常
                mock_websockets.side_effect = Exception("Connection failed")

                result = await manager._connect_direct(config)

                assert result is None

    @pytest.mark.asyncio
    async def test_aiohttp_proxy_session_cleanup_on_exception(self, manager):
        """测试：aiohttp代理连接异常时会话清理"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        proxy_config = Mock(spec=ProxyConfig)
        proxy_config.to_aiohttp_proxy.return_value = "http://proxy.example.com:8080"

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.ws_connect.side_effect = Exception("Connection failed")
            mock_session_class.return_value = mock_session

            result = await manager._connect_with_aiohttp_proxy(config, proxy_config)

            assert result is None
            # 验证会话被清理
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_aiohttp_direct_session_cleanup_on_exception(self, manager):
        """测试：aiohttp直接连接异常时会话清理"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.ws_connect.side_effect = Exception("Connection failed")
            mock_session_class.return_value = mock_session

            result = await manager._connect_with_aiohttp_direct(config)

            assert result is None
            # 验证会话被清理
            mock_session.close.assert_called_once()


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManagerIntegrationScenarios:
    """测试WebSocket连接管理器集成场景"""

    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()

    @pytest.mark.asyncio
    async def test_connection_with_unknown_exchange_name(self, manager):
        """测试：未知交易所名称的连接"""
        config = WebSocketConfig(
            url="wss://api.unknown.com/ws",
            exchange_name=None  # 无交易所名称
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            connection = await manager.connect(config)

            assert connection is not None
            # 验证连接键使用"unknown"作为默认值
            connection_key = "unknown_wss://api.unknown.com/ws"
            assert connection_key in manager.connections

    @pytest.mark.asyncio
    async def test_multiple_connections_same_exchange_different_urls(self, manager):
        """测试：同一交易所的多个不同URL连接"""
        configs = [
            WebSocketConfig(url="wss://api.binance.com/ws/btcusdt@ticker", exchange_name="binance"),
            WebSocketConfig(url="wss://api.binance.com/ws/ethusdt@ticker", exchange_name="binance"),
            WebSocketConfig(url="wss://api.binance.com/ws/adausdt@ticker", exchange_name="binance")
        ]

        with patch('websockets.connect') as mock_connect:
            mock_connections = []
            for i in range(3):
                mock_ws = AsyncMock()
                mock_connections.append(mock_ws)

            async def mock_connect_func(*args, **kwargs):
                return mock_connections.pop(0) if mock_connections else AsyncMock()
            mock_connect.side_effect = mock_connect_func

            # 建立多个连接
            connections = []
            for config in configs:
                connection = await manager.connect(config)
                assert connection is not None
                connections.append(connection)

            # 验证所有连接都被缓存
            stats = manager.get_connection_stats()
            assert stats['total_connections'] == 3
            assert stats['active_connections'] == 3

            # 验证连接键的唯一性
            expected_keys = [
                "binance_wss://api.binance.com/ws/btcusdt@ticker",
                "binance_wss://api.binance.com/ws/ethusdt@ticker",
                "binance_wss://api.binance.com/ws/adausdt@ticker"
            ]
            for key in expected_keys:
                assert key in stats['connections']

    @pytest.mark.asyncio
    async def test_connection_lifecycle_with_error_recovery(self, manager):
        """测试：包含错误恢复的连接生命周期"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test_exchange"
        )

        # 第一次连接失败，第二次成功
        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()

            call_count = 0
            async def mock_connect_func(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ConnectionError("First attempt failed")
                return mock_ws

            mock_connect.side_effect = mock_connect_func

            # 第一次连接失败
            connection1 = await manager.connect(config)
            assert connection1 is None

            # 第二次连接成功
            connection2 = await manager.connect(config)
            assert connection2 is not None
            assert isinstance(connection2, WebSocketWrapper)

            # 验证连接被缓存
            connection_key = "test_exchange_wss://api.example.com/ws"
            assert connection_key in manager.connections

    @pytest.mark.asyncio
    async def test_global_websocket_manager_isolation(self):
        """测试：全局WebSocket管理器隔离性"""
        # 创建本地管理器
        local_manager = WebSocketConnectionManager()

        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            # 在本地管理器中建立连接
            local_connection = await local_manager.connect(config)
            assert local_connection is not None

            # 验证全局管理器中没有这个连接
            global_stats = websocket_manager.get_connection_stats()
            local_stats = local_manager.get_connection_stats()

            assert local_stats['total_connections'] == 1
            # 全局管理器的连接数可能为0或其他值，但不应该受本地管理器影响
            assert global_stats['total_connections'] != local_stats['total_connections'] or global_stats['total_connections'] == 0
