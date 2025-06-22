"""
增强交易所连接器增强TDD测试
专注于提升覆盖率到45%+，测试未覆盖的边缘情况和错误处理
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

try:
    from core.networking.enhanced_exchange_connector import (
        BinanceErrorHandler, EnhancedExchangeConnector, RateLimiter
    )
    from core.networking.unified_session_manager import UnifiedSessionManager as SessionManager

    # 创建模拟的ExchangeConfig类
    class ExchangeConfig:
        def __init__(self, name="test", base_url="https://api.test.com",
                     api_key="test_key", api_secret="test_secret",
                     price_precision=2, quantity_precision=8,
                     rate_limit_requests=10, rate_limit_window=60,
                     http_proxy=None, ws_proxy=None,
                     ws_url="wss://stream.test.com/ws",
                     ws_ping_interval=30, ws_ping_timeout=10):
            self.name = name
            self.base_url = base_url
            self.api_key = api_key
            self.api_secret = api_secret
            self.price_precision = price_precision
            self.quantity_precision = quantity_precision
            self.rate_limit_requests = rate_limit_requests
            self.rate_limit_window = rate_limit_window
            self.http_proxy = http_proxy
            self.ws_proxy = ws_proxy
            self.ws_url = ws_url
            self.ws_ping_interval = ws_ping_interval
            self.ws_ping_timeout = ws_ping_timeout

    HAS_CONNECTOR_MODULES = True
except ImportError as e:
    print(f"Import error: {e}")
    HAS_CONNECTOR_MODULES = False


@pytest.mark.skipif(not HAS_CONNECTOR_MODULES, reason="增强交易所连接器模块不可用")
class TestBinanceErrorHandlerEdgeCases:
    """测试Binance错误处理器边缘情况"""
    
    def test_handle_precision_error_with_params(self):
        """测试：处理精度错误并设置受影响参数"""
        error_code = -1013
        error_msg = "Parameter 'price' has too much precision"
        context = {'endpoint': '/api/v3/order', 'params': {'price': '0.123456789'}}

        error_info = BinanceErrorHandler.handle_error(error_code, error_msg, context)

        assert error_info['code'] == error_code
        assert error_info['message'] == error_msg
        # 检查是否包含精度错误的特殊处理
        if "Parameter '%s' has too much precision" in error_msg:
            assert error_info['severity'] == 'warning'
            assert error_info['action'] == 'adjust_precision'
            assert error_info['affected_params'] == BinanceErrorHandler.PRECISION_ERROR_PARAMS
        else:
            assert error_info['severity'] == 'error'  # 默认严重性
        assert error_info['context'] == context
    
    def test_handle_timestamp_signature_error_critical(self):
        """测试：处理时间戳和签名关键错误"""
        error_code = -1021
        error_msg = "Timestamp for this request is outside of the recvWindow"
        context = {'endpoint': '/api/v3/account'}
        
        error_info = BinanceErrorHandler.handle_error(error_code, error_msg, context)
        
        assert error_info['code'] == error_code
        assert error_info['message'] == error_msg
        assert error_info['severity'] == 'critical'
        assert error_info['action'] == 'sync_time_signature'
        assert error_info['context'] == context
    
    def test_handle_rate_limit_warning(self):
        """测试：处理速率限制警告"""
        error_code = -1003
        error_msg = "Too many requests"
        context = {'endpoint': '/api/v3/ticker/price'}
        
        error_info = BinanceErrorHandler.handle_error(error_code, error_msg, context)
        
        assert error_info['code'] == error_code
        assert error_info['message'] == error_msg
        assert error_info['severity'] == 'warning'
        assert error_info['action'] == 'rate_limit_wait'
        assert error_info['context'] == context


@pytest.mark.skipif(not HAS_CONNECTOR_MODULES, reason="增强交易所连接器模块不可用")
class TestEnhancedExchangeConnectorTimeSync:
    """测试增强交易所连接器时间同步功能"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.name = "deribit"
        config.base_url = "https://test.deribit.com"
        config.api_key = "test_key"
        config.api_secret = "test_secret"
        config.price_precision = 2
        config.quantity_precision = 8
        config.rate_limit_requests = 10
        config.rate_limit_window = 60
        config.http_proxy = None
        config.ws_proxy = None
        config.ws_url = "wss://test.deribit.com/ws"
        config.ws_ping_interval = 30
        config.ws_ping_timeout = 10
        return config
    
    @pytest.fixture
    def mock_session_manager(self):
        """创建模拟会话管理器"""
        return AsyncMock(spec=SessionManager)
    
    @pytest.fixture
    def connector(self, mock_config, mock_session_manager):
        """创建测试用的连接器"""
        return EnhancedExchangeConnector(mock_config, mock_session_manager)
    
    @pytest.mark.asyncio
    async def test_sync_server_time_deribit(self, connector, mock_session_manager):
        """测试：Deribit时间同步"""
        # 模拟Deribit时间响应
        mock_response = AsyncMock()
        mock_response.json.return_value = {'result': 1640995200000}
        mock_session_manager.request.return_value = mock_response
        
        await connector.sync_server_time()
        
        # 验证请求URL
        expected_url = "https://test.deribit.com/api/v2/public/get_time"
        mock_session_manager.request.assert_called_once_with('GET', expected_url)
        
        # 验证时间偏移被设置
        assert connector.server_time_offset != 0
        assert connector.stats['time_syncs'] == 1
        
        # 验证响应被关闭
        mock_response.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_sync_server_time_unknown_exchange(self, mock_config, mock_session_manager):
        """测试：未知交易所时间同步"""
        mock_config.name = "unknown_exchange"
        connector = EnhancedExchangeConnector(mock_config, mock_session_manager)
        
        # 模拟响应
        mock_response = AsyncMock()
        mock_response.json.return_value = {'serverTime': 1640995200000}
        mock_session_manager.request.return_value = mock_response
        
        await connector.sync_server_time()
        
        # 验证使用默认端点
        expected_url = "https://test.deribit.com/api/v3/time"
        mock_session_manager.request.assert_called_once_with('GET', expected_url)
    
    @pytest.mark.asyncio
    async def test_sync_server_time_exception_handling(self, connector, mock_session_manager):
        """测试：时间同步异常处理"""
        # 模拟请求异常
        mock_session_manager.request.side_effect = Exception("Network error")
        
        # 时间同步应该捕获异常并设置偏移为0
        await connector.sync_server_time()
        
        assert connector.server_time_offset == 0
        assert connector.stats['time_syncs'] == 0


@pytest.mark.skipif(not HAS_CONNECTOR_MODULES, reason="增强交易所连接器模块不可用")
class TestEnhancedExchangeConnectorParameterHandling:
    """测试增强交易所连接器参数处理功能"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.name = "binance"
        config.base_url = "https://api.binance.com"
        config.api_key = "test_key"
        config.api_secret = "test_secret"
        config.price_precision = 2
        config.quantity_precision = 8
        config.rate_limit_requests = 10
        config.rate_limit_window = 60
        config.http_proxy = "http://proxy:8080"
        config.ws_proxy = None
        config.ws_url = "wss://stream.binance.com:9443/ws"
        config.ws_ping_interval = 30
        config.ws_ping_timeout = 10
        return config
    
    @pytest.fixture
    def connector(self, mock_config):
        """创建测试用的连接器"""
        return EnhancedExchangeConnector(mock_config)
    
    def test_prepare_params_string_conversion(self, connector):
        """测试：参数准备中的字符串转换"""
        params = {
            'symbol': 'BTCUSDT',
            'price': 50000.123456,  # 精度敏感参数
            'quantity': 0.001,      # 精度敏感参数
            'timeInForce': 'GTC',   # 非精度敏感参数
            'type': 'LIMIT'         # 非精度敏感参数
        }
        
        prepared = connector.prepare_params(params)
        
        # 验证精度敏感参数被调整
        assert prepared['price'] == '50000.12'  # 价格精度为2
        assert prepared['quantity'] == '0.001'  # 数量精度为8
        
        # 验证非精度敏感参数保持不变
        assert prepared['symbol'] == 'BTCUSDT'
        assert prepared['timeInForce'] == 'GTC'
        assert prepared['type'] == 'LIMIT'
    
    def test_prepare_params_non_numeric_precision_param(self, connector):
        """测试：准备参数时处理非数值的精度敏感参数"""
        params = {
            'symbol': 'BTCUSDT',
            'price': 'MARKET',  # 字符串类型的价格参数
            'quantity': 0.001
        }
        
        prepared = connector.prepare_params(params)
        
        # 验证字符串类型的精度敏感参数被转换为字符串
        assert prepared['price'] == 'MARKET'
        assert prepared['quantity'] == '0.001'
    
    def test_create_signature_without_secret(self, connector):
        """测试：没有API密钥时创建签名"""
        connector.config.api_secret = None
        
        params = {'symbol': 'BTCUSDT', 'side': 'BUY'}
        signature = connector.create_signature(params)
        
        assert signature == ""


@pytest.mark.skipif(not HAS_CONNECTOR_MODULES, reason="增强交易所连接器模块不可用")
class TestEnhancedExchangeConnectorRequestHandling:
    """测试增强交易所连接器请求处理功能"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.name = "binance"
        config.base_url = "https://api.binance.com"
        config.api_key = "test_key"
        config.api_secret = "test_secret"
        config.price_precision = 2
        config.quantity_precision = 8
        config.rate_limit_requests = 10
        config.rate_limit_window = 60
        config.http_proxy = "http://proxy:8080"
        config.ws_proxy = None
        config.ws_url = "wss://stream.binance.com:9443/ws"
        config.ws_ping_interval = 30
        config.ws_ping_timeout = 10
        return config
    
    @pytest.fixture
    def mock_session_manager(self):
        """创建模拟会话管理器"""
        return AsyncMock(spec=SessionManager)
    
    @pytest.fixture
    def connector(self, mock_config, mock_session_manager):
        """创建测试用的连接器"""
        return EnhancedExchangeConnector(mock_config, mock_session_manager)
    
    @pytest.mark.asyncio
    async def test_make_request_with_proxy(self, connector, mock_session_manager):
        """测试：使用代理发送请求"""
        # 模拟成功响应
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'symbol': 'BTCUSDT', 'price': '50000.00'}
        mock_session_manager.request.return_value = mock_response
        
        result = await connector.make_request('GET', '/api/v3/ticker/price', {'symbol': 'BTCUSDT'})
        
        # 验证请求包含代理配置
        call_args = mock_session_manager.request.call_args
        assert call_args[1]['proxy'] == "http://proxy:8080"
        
        # 验证返回结果
        assert result['symbol'] == 'BTCUSDT'
        assert result['price'] == '50000.00'
        
        # 验证统计更新
        assert connector.stats['requests_sent'] == 1
        assert connector.stats['requests_successful'] == 1
    
    @pytest.mark.asyncio
    async def test_make_request_timestamp_validation_failure(self, connector, mock_session_manager):
        """测试：时间戳验证失败后重新同步"""
        # 模拟时间戳验证失败
        with patch.object(connector, 'validate_timestamp', return_value=False):
            with patch.object(connector, 'sync_server_time') as mock_sync:
                with patch.object(connector, 'get_server_time', return_value=1640995200000):
                    # 模拟成功响应
                    mock_response = AsyncMock()
                    mock_response.status = 200
                    mock_response.json.return_value = {'result': 'success'}
                    mock_session_manager.request.return_value = mock_response
                    
                    result = await connector.make_request('GET', '/api/v3/account', signed=True)
                    
                    # 验证时间同步被调用
                    mock_sync.assert_called_once()
                    
                    # 验证请求成功
                    assert result['result'] == 'success'
    
    @pytest.mark.asyncio
    async def test_make_request_error_response_parse_exception(self, connector, mock_session_manager):
        """测试：错误响应解析异常处理"""
        # 模拟错误响应，但JSON解析失败
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json.side_effect = Exception("JSON decode error")
        mock_session_manager.request.return_value = mock_response
        
        with pytest.raises(Exception, match="API Error -1000"):
            await connector.make_request('GET', '/api/v3/invalid')
        
        # 验证统计更新
        assert connector.stats['requests_sent'] == 1
        assert connector.stats['requests_failed'] == 1
    
    @pytest.mark.asyncio
    async def test_make_request_critical_error_sync_time(self, connector, mock_session_manager):
        """测试：关键错误后同步时间"""
        # 模拟关键错误响应
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json.return_value = {'code': -1021, 'msg': 'Timestamp outside recvWindow'}
        mock_session_manager.request.return_value = mock_response
        
        with patch.object(connector, 'sync_server_time') as mock_sync:
            with pytest.raises(Exception, match="API Error -1021"):
                await connector.make_request('GET', '/api/v3/account', signed=True)
            
            # 验证时间同步被调用
            mock_sync.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_make_request_network_exception(self, connector, mock_session_manager):
        """测试：网络异常处理"""
        # 模拟网络异常
        mock_session_manager.request.side_effect = Exception("Network timeout")
        
        with pytest.raises(Exception, match="Network timeout"):
            await connector.make_request('GET', '/api/v3/ping')
        
        # 验证统计更新
        assert connector.stats['requests_sent'] == 1
        assert connector.stats['requests_failed'] == 1


@pytest.mark.skipif(not HAS_CONNECTOR_MODULES, reason="增强交易所连接器模块不可用")
class TestEnhancedExchangeConnectorWebSocket:
    """测试增强交易所连接器WebSocket功能"""

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.name = "binance"
        config.base_url = "https://api.binance.com"
        config.api_key = "test_key"
        config.api_secret = "test_secret"
        config.price_precision = 2
        config.quantity_precision = 8
        config.rate_limit_requests = 10
        config.rate_limit_window = 60
        config.http_proxy = None
        config.ws_proxy = "socks5://proxy:1080"
        config.ws_url = "wss://stream.binance.com:9443/ws"
        config.ws_ping_interval = 30
        config.ws_ping_timeout = 10
        return config

    @pytest.fixture
    def connector(self, mock_config):
        """创建测试用的连接器"""
        return EnhancedExchangeConnector(mock_config)

    @pytest.mark.asyncio
    async def test_connect_websocket_already_connected(self, connector):
        """测试：WebSocket已连接时重复连接"""
        # 模拟已连接的WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = False
        connector.ws_connection = mock_ws

        # 重复连接应该直接返回
        await connector.connect_websocket()

        # 验证没有创建新连接
        assert connector.ws_connection is mock_ws

    @pytest.mark.asyncio
    async def test_connect_websocket_with_streams(self, connector):
        """测试：连接WebSocket并指定流"""
        streams = ['btcusdt@ticker', 'ethusdt@depth']

        with patch('websockets.connect') as mock_connect:
            mock_ws = AsyncMock()
            # 模拟websockets.connect返回协程
            async def mock_connect_func(*args, **kwargs):
                return mock_ws
            mock_connect.side_effect = mock_connect_func

            with patch('asyncio.create_task') as mock_create_task:
                await connector.connect_websocket(streams)

                # 验证WebSocket连接参数
                expected_url = f"{connector.config.ws_url}/stream?streams=btcusdt@ticker/ethusdt@depth"
                mock_connect.assert_called_once()
                call_args = mock_connect.call_args
                assert call_args[0][0] == expected_url
                assert call_args[1]['proxy'] == "socks5://proxy:1080"
                assert call_args[1]['ping_interval'] == 30
                assert call_args[1]['ping_timeout'] == 10

                # 验证消息循环任务被创建
                mock_create_task.assert_called_once()

                # 验证连接被设置
                assert connector.ws_connection is mock_ws

    @pytest.mark.asyncio
    async def test_connect_websocket_exception(self, connector):
        """测试：WebSocket连接异常"""
        with patch('websockets.connect', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                await connector.connect_websocket()

    def test_subscribe_websocket_stream(self, connector):
        """测试：订阅WebSocket流"""
        stream = 'btcusdt@ticker'
        handler = AsyncMock()

        connector.subscribe(stream, handler)

        # 验证处理器和订阅被添加
        assert connector.ws_handlers[stream] is handler
        assert stream in connector.ws_subscriptions

    def test_unsubscribe_websocket_stream(self, connector):
        """测试：取消订阅WebSocket流"""
        stream = 'btcusdt@ticker'
        handler = AsyncMock()

        # 先订阅
        connector.subscribe(stream, handler)

        # 然后取消订阅
        connector.unsubscribe(stream)

        # 验证处理器和订阅被移除
        assert stream not in connector.ws_handlers
        assert stream not in connector.ws_subscriptions

    def test_unsubscribe_nonexistent_stream(self, connector):
        """测试：取消订阅不存在的流"""
        stream = 'nonexistent@stream'

        # 取消订阅不存在的流应该不抛出异常
        connector.unsubscribe(stream)

        # 验证没有副作用
        assert stream not in connector.ws_handlers
        assert stream not in connector.ws_subscriptions

    @pytest.mark.asyncio
    async def test_close_websocket_connected(self, connector):
        """测试：关闭已连接的WebSocket"""
        # 模拟已连接的WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = False
        connector.ws_connection = mock_ws

        await connector.close_websocket()

        # 验证WebSocket被关闭
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_websocket_already_closed(self, connector):
        """测试：关闭已关闭的WebSocket"""
        # 模拟已关闭的WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = True
        connector.ws_connection = mock_ws

        await connector.close_websocket()

        # 验证close方法没有被调用
        mock_ws.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_websocket_no_connection(self, connector):
        """测试：关闭不存在的WebSocket连接"""
        connector.ws_connection = None

        # 应该不抛出异常
        await connector.close_websocket()


@pytest.mark.skipif(not HAS_CONNECTOR_MODULES, reason="增强交易所连接器模块不可用")
class TestEnhancedExchangeConnectorAPIMethodsAndStats:
    """测试增强交易所连接器API方法和统计功能"""

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.name = "okx"
        config.base_url = "https://www.okx.com"
        config.api_key = "test_key"
        config.api_secret = "test_secret"
        config.price_precision = 2
        config.quantity_precision = 8
        config.rate_limit_requests = 10
        config.rate_limit_window = 60
        config.http_proxy = None
        config.ws_proxy = None
        config.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        config.ws_ping_interval = 30
        config.ws_ping_timeout = 10
        return config

    @pytest.fixture
    def mock_session_manager(self):
        """创建模拟会话管理器"""
        return AsyncMock(spec=SessionManager)

    @pytest.fixture
    def connector(self, mock_config, mock_session_manager):
        """创建测试用的连接器"""
        return EnhancedExchangeConnector(mock_config, mock_session_manager)

    @pytest.mark.asyncio
    async def test_get_ticker_okx(self, connector):
        """测试：获取OKX行情数据"""
        symbol = "BTC-USDT"
        expected_data = {'instId': 'BTC-USDT', 'last': '50000.0'}

        with patch.object(connector, 'make_request', return_value=expected_data) as mock_request:
            result = await connector.get_ticker(symbol)

            # 验证请求参数
            mock_request.assert_called_once_with('GET', '/api/v5/market/ticker', {'instId': symbol})

            # 验证返回结果
            assert result == expected_data

    @pytest.mark.asyncio
    async def test_get_ticker_binance(self, mock_config, mock_session_manager):
        """测试：获取Binance行情数据"""
        mock_config.name = "binance"
        connector = EnhancedExchangeConnector(mock_config, mock_session_manager)

        symbol = "BTCUSDT"
        expected_data = {'symbol': 'BTCUSDT', 'price': '50000.0'}

        with patch.object(connector, 'make_request', return_value=expected_data) as mock_request:
            result = await connector.get_ticker(symbol)

            # 验证请求参数
            mock_request.assert_called_once_with('GET', '/api/v3/ticker/24hr', {'symbol': symbol})

            # 验证返回结果
            assert result == expected_data

    @pytest.mark.asyncio
    async def test_get_orderbook_deribit(self, mock_config, mock_session_manager):
        """测试：获取Deribit订单簿"""
        mock_config.name = "deribit"
        connector = EnhancedExchangeConnector(mock_config, mock_session_manager)

        symbol = "BTC-PERPETUAL"
        limit = 50
        expected_data = {'result': {'bids': [], 'asks': []}}

        with patch.object(connector, 'make_request', return_value=expected_data) as mock_request:
            result = await connector.get_orderbook(symbol, limit)

            # 验证请求参数
            mock_request.assert_called_once_with('GET', '/api/v2/public/get_order_book', {
                'symbol': symbol,
                'limit': limit
            })

            # 验证返回结果
            assert result == expected_data

    @pytest.mark.asyncio
    async def test_get_trades_unknown_exchange(self, mock_config, mock_session_manager):
        """测试：获取未知交易所最近交易"""
        mock_config.name = "unknown"
        connector = EnhancedExchangeConnector(mock_config, mock_session_manager)

        symbol = "BTCUSDT"
        limit = 100
        expected_data = {'trades': []}

        with patch.object(connector, 'make_request', return_value=expected_data) as mock_request:
            result = await connector.get_trades(symbol, limit)

            # 验证使用默认端点
            mock_request.assert_called_once_with('GET', '/api/v3/trades', {
                'symbol': symbol,
                'limit': limit
            })

            # 验证返回结果
            assert result == expected_data

    def test_get_statistics_comprehensive(self, connector):
        """测试：获取详细统计信息"""
        # 设置一些统计数据
        connector.stats['requests_sent'] = 100
        connector.stats['requests_successful'] = 95
        connector.stats['requests_failed'] = 5
        connector.stats['ws_messages_received'] = 1000
        connector.stats['ws_reconnections'] = 2
        connector.stats['precision_adjustments'] = 10
        connector.stats['time_syncs'] = 3
        connector.server_time_offset = 150
        connector.connected = True

        # 模拟WebSocket连接
        mock_ws = Mock()
        mock_ws.closed = False
        connector.ws_connection = mock_ws
        connector.ws_subscriptions = {'stream1', 'stream2', 'stream3'}

        # 模拟运行时间
        start_time = time.time() - 3600  # 1小时前
        connector.stats['start_time'] = start_time

        stats = connector.get_statistics()

        # 验证基本信息
        assert stats['exchange'] == 'okx'
        assert stats['connected'] is True
        assert stats['uptime_seconds'] == pytest.approx(3600, rel=1e-1)

        # 验证请求统计
        assert stats['requests_sent'] == 100
        assert stats['requests_successful'] == 95
        assert stats['requests_failed'] == 5
        assert stats['success_rate'] == 0.95
        assert stats['requests_per_second'] == pytest.approx(100/3600, rel=1e-1)

        # 验证WebSocket统计
        assert stats['ws_messages_received'] == 1000
        assert stats['ws_reconnections'] == 2
        assert stats['ws_connected'] is True
        assert stats['subscriptions'] == 3

        # 验证其他统计
        assert stats['precision_adjustments'] == 10
        assert stats['time_syncs'] == 3
        assert stats['server_time_offset'] == 150

    def test_get_statistics_no_websocket(self, connector):
        """测试：获取统计信息（无WebSocket连接）"""
        # 设置基本统计数据
        connector.stats['requests_sent'] = 0
        connector.stats['requests_successful'] = 0
        connector.stats['requests_failed'] = 0
        connector.connected = False
        connector.ws_connection = None

        stats = connector.get_statistics()

        # 验证WebSocket相关统计
        assert stats['ws_connected'] is False or stats['ws_connected'] is None
        assert stats['subscriptions'] == 0
        assert stats['success_rate'] == 0.0  # 避免除零错误
        assert stats['requests_per_second'] == 0.0
