"""
WebSocket管理器TDD测试
专注于提升覆盖率和测试未覆盖的功能
"""

import pytest
import asyncio
import json
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
class TestWebSocketConfigAdvanced:
    """测试WebSocket配置高级功能"""
    
    def test_websocket_config_creation_with_all_params(self):
        """测试：使用所有参数创建WebSocket配置"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            timeout=30,
            ssl_verify=True,
            ssl_context=None,
            ping_interval=20,
            ping_timeout=10,
            max_size=1024*1024,
            extra_headers={"Authorization": "Bearer token"},
            subprotocols=["chat", "superchat"],
            exchange_name="example_exchange",
            disable_ssl_for_exchanges=["deribit", "bybit"]
        )
        
        assert config.url == "wss://api.example.com/ws"
        assert config.timeout == 30
        assert config.ssl_verify is True
        assert config.ping_interval == 20
        assert config.ping_timeout == 10
        assert config.max_size == 1024*1024
        assert config.extra_headers["Authorization"] == "Bearer token"
        assert config.subprotocols == ["chat", "superchat"]
        assert config.exchange_name == "example_exchange"
        assert "deribit" in config.disable_ssl_for_exchanges
    
    def test_should_disable_ssl_with_ssl_verify_false(self):
        """测试：ssl_verify为False时应该禁用SSL"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            ssl_verify=False
        )
        
        assert config.should_disable_ssl() is True
    
    def test_should_disable_ssl_with_exchange_in_disable_list(self):
        """测试：交易所在禁用列表中时应该禁用SSL"""
        config = WebSocketConfig(
            url="wss://api.deribit.com/ws",
            ssl_verify=True,
            exchange_name="deribit",
            disable_ssl_for_exchanges=["deribit", "bybit"]
        )
        
        assert config.should_disable_ssl() is True
    
    def test_should_disable_ssl_case_insensitive(self):
        """测试：交易所名称大小写不敏感"""
        config = WebSocketConfig(
            url="wss://api.deribit.com/ws",
            ssl_verify=True,
            exchange_name="DERIBIT",
            disable_ssl_for_exchanges=["deribit", "bybit"]
        )
        
        assert config.should_disable_ssl() is True
    
    def test_should_not_disable_ssl_normal_case(self):
        """测试：正常情况下不应该禁用SSL"""
        config = WebSocketConfig(
            url="wss://api.binance.com/ws",
            ssl_verify=True,
            exchange_name="binance",
            disable_ssl_for_exchanges=["deribit", "bybit"]
        )
        
        assert config.should_disable_ssl() is False
    
    def test_should_not_disable_ssl_no_exchange_name(self):
        """测试：没有交易所名称时不应该禁用SSL"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            ssl_verify=True,
            exchange_name=None,
            disable_ssl_for_exchanges=["deribit", "bybit"]
        )
        
        assert config.should_disable_ssl() is False


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketWrapperAdvanced:
    """测试WebSocket包装器高级功能"""
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_aiohttp_send(self):
        """测试：aiohttp WebSocket发送消息"""
        mock_ws = AsyncMock()
        mock_session = AsyncMock()
        
        wrapper = WebSocketWrapper(mock_ws, mock_session, "aiohttp")
        
        await wrapper.send("test message")
        
        mock_ws.send_str.assert_called_once_with("test message")
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_websockets_send(self):
        """测试：websockets库发送消息"""
        mock_ws = AsyncMock()
        
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        
        await wrapper.send("test message")
        
        mock_ws.send.assert_called_once_with("test message")
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_send_when_closed(self):
        """测试：连接关闭时发送消息应该抛出异常"""
        mock_ws = AsyncMock()
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        wrapper.closed = True
        
        with pytest.raises(ConnectionError, match="WebSocket连接已关闭"):
            await wrapper.send("test message")
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_send_exception_handling(self):
        """测试：发送消息异常处理"""
        mock_ws = AsyncMock()
        mock_ws.send.side_effect = Exception("Send failed")
        
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        
        with pytest.raises(Exception, match="Send failed"):
            await wrapper.send("test message")
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_async_iterator_aiohttp(self):
        """测试：aiohttp WebSocket异步迭代器"""
        mock_ws = AsyncMock()
        mock_msg = Mock()
        mock_msg.type = 1  # aiohttp.WSMsgType.TEXT
        mock_msg.data = "received message"
        mock_ws.receive.return_value = mock_msg

        wrapper = WebSocketWrapper(mock_ws, None, "aiohttp")

        message = await wrapper.__anext__()

        assert message == "received message"
        mock_ws.receive.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_wrapper_async_iterator_websockets(self):
        """测试：websockets库异步迭代器"""
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = "received message"

        wrapper = WebSocketWrapper(mock_ws, None, "websockets")

        message = await wrapper.__anext__()

        assert message == "received message"
        mock_ws.recv.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_wrapper_async_iterator_when_closed(self):
        """测试：连接关闭时异步迭代器应该抛出StopAsyncIteration"""
        mock_ws = AsyncMock()
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        wrapper.closed = True

        with pytest.raises(StopAsyncIteration):
            await wrapper.__anext__()
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_close_aiohttp(self):
        """测试：关闭aiohttp WebSocket连接"""
        mock_ws = AsyncMock()
        mock_ws.closed = False  # 模拟连接未关闭
        mock_session = AsyncMock()

        wrapper = WebSocketWrapper(mock_ws, mock_session, "aiohttp")

        await wrapper.close()

        assert wrapper.closed is True
        mock_ws.close.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_wrapper_close_websockets(self):
        """测试：关闭websockets库连接"""
        mock_ws = AsyncMock()
        mock_ws.closed = False  # 模拟连接未关闭

        wrapper = WebSocketWrapper(mock_ws, None, "websockets")

        await wrapper.close()

        assert wrapper.closed is True
        mock_ws.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_close_exception_handling(self):
        """测试：关闭连接异常处理"""
        mock_ws = AsyncMock()
        mock_ws.close.side_effect = Exception("Close failed")
        
        wrapper = WebSocketWrapper(mock_ws, None, "websockets")
        
        # 应该不抛出异常，只记录日志
        await wrapper.close()
        
        assert wrapper.closed is True


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestBaseWebSocketClient:
    """测试基础WebSocket客户端"""
    
    @pytest.mark.asyncio
    async def test_base_websocket_client_not_implemented_methods(self):
        """测试：基础客户端未实现的方法"""
        client = BaseWebSocketClient()
        
        with pytest.raises(NotImplementedError):
            await client.connect("wss://example.com")
        
        with pytest.raises(NotImplementedError):
            await client.send("test")
        
        with pytest.raises(NotImplementedError):
            await client.close()
        
        with pytest.raises(NotImplementedError):
            await client.__anext__()
    
    @pytest.mark.asyncio
    async def test_base_websocket_client_context_manager(self):
        """测试：基础客户端上下文管理器"""
        client = BaseWebSocketClient()
        
        # __aenter__ 应该返回自身
        result = await client.__aenter__()
        assert result is client
        
        # __aexit__ 应该调用close方法
        with pytest.raises(NotImplementedError):
            await client.__aexit__(None, None, None)
    
    def test_base_websocket_client_async_iterator(self):
        """测试：基础客户端异步迭代器"""
        client = BaseWebSocketClient()
        
        # __aiter__ 应该返回自身
        result = client.__aiter__()
        assert result is client


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManagerAdvanced:
    """测试WebSocket连接管理器高级功能"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()
    
    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_proxy_success(self, manager):
        """测试：使用aiohttp代理连接成功"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )
        
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8080"
        )
        
        with patch.object(manager, '_connect_with_aiohttp_proxy') as mock_connect:
            mock_wrapper = Mock(spec=WebSocketWrapper)
            mock_connect.return_value = mock_wrapper
            
            result = await manager.connect(config, proxy_config)
            
            assert result is mock_wrapper
            mock_connect.assert_called_once_with(config, proxy_config)
    
    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_proxy_failure_fallback(self, manager):
        """测试：aiohttp代理连接失败后回退"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )
        
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080"
        )
        
        with patch.object(manager, '_connect_with_aiohttp_proxy') as mock_proxy_connect:
            with patch.object(manager, '_connect_direct') as mock_direct_connect:
                mock_proxy_connect.return_value = None  # 代理连接失败
                mock_wrapper = Mock(spec=WebSocketWrapper)
                mock_direct_connect.return_value = mock_wrapper
                
                result = await manager.connect(config, proxy_config)
                
                assert result is mock_wrapper
                mock_proxy_connect.assert_called_once()
                mock_direct_connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connect_direct_without_proxy(self, manager):
        """测试：无代理直接连接"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )
        
        with patch('core.networking.proxy_manager.proxy_manager') as mock_proxy_manager:
            with patch.object(manager, '_connect_with_websockets') as mock_websockets_connect:
                # 模拟无代理环境
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = False
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config
                
                mock_wrapper = Mock(spec=WebSocketWrapper)
                mock_websockets_connect.return_value = mock_wrapper
                
                result = await manager._connect_direct(config)
                
                assert result is mock_wrapper
                mock_websockets_connect.assert_called_once_with(config)
    
    @pytest.mark.asyncio
    async def test_connect_direct_with_proxy(self, manager):
        """测试：有代理环境的直接连接"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        with patch('core.networking.websocket_manager.proxy_manager') as mock_proxy_manager:
            with patch.object(manager, '_connect_with_aiohttp_direct') as mock_aiohttp_connect:
                # 模拟有代理环境
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = True
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                mock_wrapper = Mock(spec=WebSocketWrapper)
                mock_aiohttp_connect.return_value = mock_wrapper

                result = await manager._connect_direct(config)

                assert result is mock_wrapper
                mock_aiohttp_connect.assert_called_once_with(config)
    
    @pytest.mark.asyncio
    async def test_connect_with_websockets_full_config(self, manager):
        """测试：使用websockets库连接（完整配置）"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test",
            ping_interval=30,
            ping_timeout=10,
            max_size=2048,
            extra_headers={"User-Agent": "TestClient"},
            subprotocols=["v1", "v2"],
            ssl_verify=False
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            # 正确设置异步函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            result = await manager._connect_with_websockets(config)

            assert isinstance(result, WebSocketWrapper)
            assert result.connection_type == "websockets"

            # 验证连接参数
            call_kwargs = mock_connect.call_args.kwargs
            assert call_kwargs['ping_interval'] == 30
            assert call_kwargs['ping_timeout'] == 10
            assert call_kwargs['max_size'] == 2048
            assert call_kwargs['extra_headers'] == {"User-Agent": "TestClient"}
            assert call_kwargs['subprotocols'] == ["v1", "v2"]
            assert call_kwargs['ssl'] is None  # SSL被禁用
    
    @pytest.mark.asyncio
    async def test_connect_with_websockets_ssl_context(self, manager):
        """测试：使用websockets库连接（自定义SSL上下文）"""
        import ssl
        ssl_context = ssl.create_default_context()

        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test",
            ssl_context=ssl_context,
            ssl_verify=True
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            # 正确设置异步函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            result = await manager._connect_with_websockets(config)

            assert isinstance(result, WebSocketWrapper)

            # 验证SSL上下文
            call_kwargs = mock_connect.call_args.kwargs
            assert call_kwargs['ssl'] is ssl_context

    @pytest.mark.asyncio
    async def test_connect_with_websockets_connection_failure(self, manager):
        """测试：websockets库连接失败"""
        config = WebSocketConfig(
            url="wss://invalid.example.com/ws",
            exchange_name="test"
        )

        with patch('websockets.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            result = await manager._connect_with_websockets(config)

            assert result is None

    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_direct_full_config(self, manager):
        """测试：使用aiohttp直接连接（完整配置）"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test",
            timeout=30,
            max_size=4096,
            extra_headers={"Authorization": "Bearer token"},
            subprotocols=["chat"],
            ssl_verify=False
        )

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_ws = AsyncMock()
            mock_session.ws_connect.return_value = mock_ws
            mock_session_class.return_value = mock_session

            result = await manager._connect_with_aiohttp_direct(config)

            assert isinstance(result, WebSocketWrapper)
            assert result.connection_type == "aiohttp"
            assert result.session is mock_session

            # 验证连接参数
            call_kwargs = mock_session.ws_connect.call_args.kwargs
            assert call_kwargs['ssl'] is None  # SSL被禁用
            assert call_kwargs['headers'] == {"Authorization": "Bearer token"}
            assert call_kwargs['protocols'] == ["chat"]
            assert call_kwargs['max_msg_size'] == 4096

    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_direct_connection_failure(self, manager):
        """测试：aiohttp直接连接失败"""
        config = WebSocketConfig(
            url="wss://invalid.example.com/ws",
            exchange_name="test"
        )

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.ws_connect.side_effect = Exception("Connection failed")
            mock_session_class.return_value = mock_session

            result = await manager._connect_with_aiohttp_direct(config)

            assert result is None
            # 验证会话被正确关闭
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_aiohttp_proxy_implementation(self, manager):
        """测试：aiohttp代理连接实现"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8080"
        )

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_ws = AsyncMock()
            mock_session.ws_connect.return_value = mock_ws
            mock_session_class.return_value = mock_session

            result = await manager._connect_with_aiohttp_proxy(config, proxy_config)

            assert isinstance(result, WebSocketWrapper)
            assert result.connection_type == "aiohttp"

            # 验证代理配置被使用
            mock_session.ws_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_connection(self, manager):
        """测试：关闭指定连接"""
        # 添加一个模拟连接
        mock_wrapper = AsyncMock(spec=WebSocketWrapper)
        connection_key = "test_connection"
        manager.connections[connection_key] = mock_wrapper

        await manager.close_connection(connection_key)

        mock_wrapper.close.assert_called_once()
        assert connection_key not in manager.connections

    @pytest.mark.asyncio
    async def test_close_connection_nonexistent(self, manager):
        """测试：关闭不存在的连接"""
        # 应该不抛出异常
        await manager.close_connection("nonexistent_connection")

    @pytest.mark.asyncio
    async def test_close_all_connections(self, manager):
        """测试：关闭所有连接"""
        # 添加多个模拟连接
        mock_wrapper1 = AsyncMock(spec=WebSocketWrapper)
        mock_wrapper2 = AsyncMock(spec=WebSocketWrapper)
        manager.connections["conn1"] = mock_wrapper1
        manager.connections["conn2"] = mock_wrapper2

        await manager.close_all_connections()

        mock_wrapper1.close.assert_called_once()
        mock_wrapper2.close.assert_called_once()
        assert len(manager.connections) == 0

    def test_get_connection_existing(self, manager):
        """测试：获取存在的连接"""
        mock_wrapper = Mock(spec=WebSocketWrapper)
        connection_key = "test_connection"
        manager.connections[connection_key] = mock_wrapper

        result = manager.get_connection(connection_key)

        assert result is mock_wrapper

    def test_get_connection_nonexistent(self, manager):
        """测试：获取不存在的连接"""
        result = manager.get_connection("nonexistent_connection")

        assert result is None

    def test_get_connection_stats(self, manager):
        """测试：获取连接统计"""
        # 添加一些模拟连接
        mock_wrapper1 = Mock(spec=WebSocketWrapper)
        mock_wrapper1.closed = False
        mock_wrapper2 = Mock(spec=WebSocketWrapper)
        mock_wrapper2.closed = True
        mock_wrapper3 = Mock(spec=WebSocketWrapper)
        mock_wrapper3.closed = False

        manager.connections["conn1"] = mock_wrapper1
        manager.connections["conn2"] = mock_wrapper2
        manager.connections["conn3"] = mock_wrapper3

        stats = manager.get_connection_stats()

        assert stats['total_connections'] == 3
        assert stats['active_connections'] == 2  # 2个未关闭的连接
        assert set(stats['connections']) == {"conn1", "conn2", "conn3"}


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManagerErrorHandling:
    """测试WebSocket连接管理器错误处理"""

    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()

    @pytest.mark.asyncio
    async def test_connect_general_exception_handling(self, manager):
        """测试：连接过程中的一般异常处理"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        with patch('core.networking.proxy_manager.proxy_manager') as mock_proxy_manager:
            mock_proxy_manager.get_proxy_config.side_effect = Exception("Proxy config error")

            result = await manager.connect(config)

            assert result is None

    @pytest.mark.asyncio
    async def test_connect_direct_exception_handling(self, manager):
        """测试：直接连接异常处理"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        with patch('core.networking.proxy_manager.proxy_manager') as mock_proxy_manager:
            with patch.object(manager, '_connect_with_websockets') as mock_websockets_connect:
                # 模拟无代理环境
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = False
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                mock_websockets_connect.side_effect = Exception("Websockets error")

                result = await manager._connect_direct(config)

                assert result is None


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketConnectionManagerIntegration:
    """测试WebSocket连接管理器集成功能"""

    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()

    @pytest.mark.asyncio
    async def test_full_connection_workflow_with_caching(self, manager):
        """测试：完整连接工作流程（包含缓存）"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test_exchange"
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            # 正确设置异步函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            # 第一次连接
            result1 = await manager.connect(config)

            assert isinstance(result1, WebSocketWrapper)

            # 验证连接被缓存
            connection_key = "test_exchange_wss://api.example.com/ws"
            assert connection_key in manager.connections
            assert manager.connections[connection_key] is result1

            # 获取缓存的连接
            cached_connection = manager.get_connection(connection_key)
            assert cached_connection is result1

    @pytest.mark.asyncio
    async def test_connection_with_exchange_config_integration(self, manager):
        """测试：使用交易所配置的连接集成"""
        config = WebSocketConfig(
            url="wss://stream.binance.com/ws",
            exchange_name="binance"
        )

        exchange_config = {
            "name": "binance",
            "proxy": {
                "enabled": False
            },
            "ssl": {
                "verify": True
            }
        }

        with patch('core.networking.websocket_manager.proxy_manager') as mock_proxy_manager:
            with patch('websockets.connect') as mock_connect:
                # 模拟代理管理器
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = False
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                mock_ws = AsyncMock()
                # 正确设置异步函数的返回值
                async def mock_connect_func(*args, **kwargs):
                    return mock_ws
                mock_connect.side_effect = mock_connect_func

                result = await manager.connect(config, exchange_config=exchange_config)

                assert isinstance(result, WebSocketWrapper)
                # 验证get_proxy_config被调用，但可能被调用多次
                assert mock_proxy_manager.get_proxy_config.call_count >= 1
                # 验证第一次调用使用了exchange_config
                mock_proxy_manager.get_proxy_config.assert_any_call(exchange_config)


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestGlobalWebSocketManager:
    """测试全局WebSocket管理器"""

    def test_global_websocket_manager_instance(self):
        """测试：全局WebSocket管理器实例"""
        assert websocket_manager is not None
        assert isinstance(websocket_manager, WebSocketConnectionManager)

    @pytest.mark.asyncio
    async def test_global_manager_usage(self):
        """测试：全局管理器使用"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="global_test"
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            # 正确设置异步函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            result = await websocket_manager.connect(config)

            assert isinstance(result, WebSocketWrapper)
            mock_connect.assert_called_once()

    def test_global_manager_connection_stats(self):
        """测试：全局管理器连接统计"""
        stats = websocket_manager.get_connection_stats()

        assert isinstance(stats, dict)
        assert 'total_connections' in stats
        assert 'active_connections' in stats
        assert 'connections' in stats


@pytest.mark.skipif(not HAS_WEBSOCKET_MODULES, reason="WebSocket模块不可用")
class TestWebSocketManagerEdgeCases:
    """测试WebSocket管理器边界情况"""

    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return WebSocketConnectionManager()

    @pytest.mark.asyncio
    async def test_connect_with_none_proxy_config(self, manager):
        """测试：使用None代理配置连接"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name="test"
        )

        with patch('core.networking.websocket_manager.proxy_manager') as mock_proxy_manager:
            with patch('websockets.connect') as mock_connect:
                # 模拟代理管理器返回无代理配置
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = False
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                mock_ws = AsyncMock()
                # 正确设置异步函数的返回值
                async def mock_connect_func(*args, **kwargs):
                    return mock_ws
                mock_connect.side_effect = mock_connect_func

                result = await manager.connect(config, proxy_config=None)

                assert isinstance(result, WebSocketWrapper)
                # 验证get_proxy_config被调用，但可能被调用多次
                assert mock_proxy_manager.get_proxy_config.call_count >= 1

    @pytest.mark.asyncio
    async def test_connect_with_empty_exchange_name(self, manager):
        """测试：使用空交易所名称连接"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name=""
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            # 正确设置异步函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            result = await manager.connect(config)

            assert isinstance(result, WebSocketWrapper)

            # 验证连接键使用"unknown"作为默认值
            connection_key = "unknown_wss://api.example.com/ws"
            assert connection_key in manager.connections

    @pytest.mark.asyncio
    async def test_connect_with_none_exchange_name(self, manager):
        """测试：使用None交易所名称连接"""
        config = WebSocketConfig(
            url="wss://api.example.com/ws",
            exchange_name=None
        )

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            # 正确设置异步函数的返回值
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            result = await manager.connect(config)

            assert isinstance(result, WebSocketWrapper)

            # 验证连接键使用"unknown"作为默认值
            connection_key = "unknown_wss://api.example.com/ws"
            assert connection_key in manager.connections
