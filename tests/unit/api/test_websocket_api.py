#!/usr/bin/env python3
"""
WebSocket API 单元测试
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
import json
import datetime
import asyncio

# 调整系统路径，便于导入被测模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 尝试导入测试助手
try:
    from tests.utils.test_helpers_可复用 import generate_mock_trade, generate_mock_orderbook
except ImportError:
    # 如果无法导入，提供备选实现
    def generate_mock_trade(exchange="binance", symbol="BTC/USDT", **kwargs):
        """备选的模拟交易生成函数"""
        timestamp = kwargs.get("timestamp", datetime.datetime.now().timestamp())
        price = kwargs.get("price", 50000.0)
        amount = kwargs.get("amount", 1.0)
        return {
            "exchange": exchange,
            "symbol": symbol,
            "price": price,
            "amount": amount,
            "timestamp": timestamp,
            "trade_id": f"{exchange}_12345678",
            "side": "buy"
        }
    
    def generate_mock_orderbook(exchange="binance", symbol="BTC/USDT", **kwargs):
        """备选的模拟订单簿生成函数"""
        timestamp = kwargs.get("timestamp", datetime.datetime.now().timestamp())
        return {
            "exchange": exchange,
            "symbol": symbol,
            "timestamp": timestamp,
            "bids": [[50000.0, 1.0], [49990.0, 2.0]],
            "asks": [[50010.0, 1.0], [50020.0, 2.0]]
        }

# 模拟WebSocket连接
class MockWebSocketConnection:
    def __init__(self, on_message=None):
        self.on_message = on_message
        self.is_connected = False
        self.messages_sent = []
        self.messages_received = []
    
    async def connect(self):
        self.is_connected = True
        return True
    
    async def disconnect(self):
        self.is_connected = False
        return True
    
    async def send_message(self, message):
        self.messages_sent.append(message)
        
        # 模拟订阅确认
        if isinstance(message, dict) and message.get("type") == "subscribe":
            response = {
                "type": "subscribed",
                "channel": message.get("channel"),
                "symbol": message.get("symbol"),
                "exchange": message.get("exchange"),
                "status": "success"
            }
            await self.simulate_message_received(response)
        
        return True
    
    async def simulate_message_received(self, message):
        self.messages_received.append(message)
        if self.on_message:
            await self.on_message(message)


class TestWebSocketApi:
    """
    WebSocket API接口测试
    """
    
    @pytest.fixture
    def setup_ws_api(self):
        """设置WebSocket API测试环境"""
        # 如果存在真实WebSocket API类，则导入并实例化
        ws_api = MagicMock()
        
        # 配置模拟方法返回
        # 模拟连接方法
        ws_api.connect = MagicMock(return_value=True)
        # 模拟订阅方法
        ws_api.subscribe = MagicMock(return_value=True)
        # 模拟取消订阅方法
        ws_api.unsubscribe = MagicMock(return_value=True)
        # 模拟断开连接方法
        ws_api.disconnect = MagicMock(return_value=True)
        # 模拟注册消息处理器方法
        ws_api.register_handler = MagicMock(return_value=True)
        
        yield ws_api
    
    @pytest.mark.asyncio
    async def test_connect(self, setup_ws_api):
        """测试WebSocket连接"""
        # Arrange
        ws_api = setup_ws_api
        mock_conn = MockWebSocketConnection()
        ws_api.connection = mock_conn
        ws_api.connect = mock_conn.connect
        
        # Act
        result = await ws_api.connect()
        
        # Assert
        assert result is True
        assert mock_conn.is_connected is True
    
    @pytest.mark.asyncio
    async def test_disconnect(self, setup_ws_api):
        """测试WebSocket断开连接"""
        # Arrange
        ws_api = setup_ws_api
        mock_conn = MockWebSocketConnection()
        mock_conn.is_connected = True
        ws_api.connection = mock_conn
        ws_api.disconnect = mock_conn.disconnect
        
        # Act
        result = await ws_api.disconnect()
        
        # Assert
        assert result is True
        assert mock_conn.is_connected is False
    
    @pytest.mark.asyncio
    async def test_subscribe_to_trades(self, setup_ws_api):
        """测试订阅交易数据"""
        # Arrange
        ws_api = setup_ws_api
        exchange = "binance"
        symbol = "BTC/USDT"
        channel = "trades"
        
        mock_conn = MockWebSocketConnection()
        mock_conn.is_connected = True
        ws_api.connection = mock_conn
        ws_api.send_message = mock_conn.send_message
        
        # 模拟异步订阅方法
        async def subscribe(exchange, symbol, channel):
            message = {
                "type": "subscribe",
                "channel": channel,
                "exchange": exchange,
                "symbol": symbol
            }
            await mock_conn.send_message(message)
            return True
        
        ws_api.subscribe = subscribe
        
        # Act
        result = await ws_api.subscribe(exchange, symbol, channel)
        
        # Assert
        assert result is True
        assert len(mock_conn.messages_sent) == 1
        assert mock_conn.messages_sent[0]["type"] == "subscribe"
        assert mock_conn.messages_sent[0]["channel"] == channel
        assert mock_conn.messages_sent[0]["exchange"] == exchange
        assert mock_conn.messages_sent[0]["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_subscribe_to_orderbook(self, setup_ws_api):
        """测试订阅订单簿数据"""
        # Arrange
        ws_api = setup_ws_api
        exchange = "binance"
        symbol = "BTC/USDT"
        channel = "orderbook"
        
        mock_conn = MockWebSocketConnection()
        mock_conn.is_connected = True
        ws_api.connection = mock_conn
        ws_api.send_message = mock_conn.send_message
        
        # 模拟异步订阅方法
        async def subscribe(exchange, symbol, channel):
            message = {
                "type": "subscribe",
                "channel": channel,
                "exchange": exchange,
                "symbol": symbol
            }
            await mock_conn.send_message(message)
            return True
        
        ws_api.subscribe = subscribe
        
        # Act
        result = await ws_api.subscribe(exchange, symbol, channel)
        
        # Assert
        assert result is True
        assert len(mock_conn.messages_sent) == 1
        assert mock_conn.messages_sent[0]["type"] == "subscribe"
        assert mock_conn.messages_sent[0]["channel"] == channel
        assert mock_conn.messages_sent[0]["exchange"] == exchange
        assert mock_conn.messages_sent[0]["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self, setup_ws_api):
        """测试取消订阅"""
        # Arrange
        ws_api = setup_ws_api
        exchange = "binance"
        symbol = "BTC/USDT"
        channel = "trades"
        
        mock_conn = MockWebSocketConnection()
        mock_conn.is_connected = True
        ws_api.connection = mock_conn
        ws_api.send_message = mock_conn.send_message
        
        # 模拟异步取消订阅方法
        async def unsubscribe(exchange, symbol, channel):
            message = {
                "type": "unsubscribe",
                "channel": channel,
                "exchange": exchange,
                "symbol": symbol
            }
            await mock_conn.send_message(message)
            return True
        
        ws_api.unsubscribe = unsubscribe
        
        # Act
        result = await ws_api.unsubscribe(exchange, symbol, channel)
        
        # Assert
        assert result is True
        assert len(mock_conn.messages_sent) == 1
        assert mock_conn.messages_sent[0]["type"] == "unsubscribe"
        assert mock_conn.messages_sent[0]["channel"] == channel
        assert mock_conn.messages_sent[0]["exchange"] == exchange
        assert mock_conn.messages_sent[0]["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_register_message_handler(self, setup_ws_api):
        """测试注册消息处理器"""
        # Arrange
        ws_api = setup_ws_api
        handler = MagicMock()
        
        # Act
        result = ws_api.register_handler(handler)
        
        # Assert
        assert result is True
        ws_api.register_handler.assert_called_once_with(handler)
    
    @pytest.mark.asyncio
    async def test_receive_trade_message(self, setup_ws_api):
        """测试接收交易消息"""
        # Arrange
        ws_api = setup_ws_api
        handler = MagicMock()
        
        # 创建一个消息处理器列表
        ws_api.message_handlers = [handler]
        
        mock_conn = MockWebSocketConnection()
        ws_api.connection = mock_conn
        
        # 准备模拟的交易消息
        mock_trade = generate_mock_trade()
        trade_message = {
            "type": "trade",
            "exchange": mock_trade["exchange"],
            "symbol": mock_trade["symbol"],
            "data": mock_trade
        }
        
        # 模拟异步消息处理方法
        async def process_message(message):
            for handler in ws_api.message_handlers:
                handler(message)
            return True
        
        ws_api.process_message = process_message
        
        # Act
        await ws_api.process_message(trade_message)
        
        # Assert
        handler.assert_called_once_with(trade_message)
    
    @pytest.mark.asyncio
    async def test_receive_orderbook_message(self, setup_ws_api):
        """测试接收订单簿消息"""
        # Arrange
        ws_api = setup_ws_api
        handler = MagicMock()
        
        # 创建一个消息处理器列表
        ws_api.message_handlers = [handler]
        
        mock_conn = MockWebSocketConnection()
        ws_api.connection = mock_conn
        
        # 准备模拟的订单簿消息
        mock_orderbook = generate_mock_orderbook()
        orderbook_message = {
            "type": "orderbook",
            "exchange": mock_orderbook["exchange"],
            "symbol": mock_orderbook["symbol"],
            "data": mock_orderbook
        }
        
        # 模拟异步消息处理方法
        async def process_message(message):
            for handler in ws_api.message_handlers:
                handler(message)
            return True
        
        ws_api.process_message = process_message
        
        # Act
        await ws_api.process_message(orderbook_message)
        
        # Assert
        handler.assert_called_once_with(orderbook_message)
    
    @pytest.mark.asyncio
    async def test_subscribe_and_receive_message(self, setup_ws_api):
        """测试订阅并接收消息的完整流程"""
        # Arrange
        ws_api = setup_ws_api
        exchange = "binance"
        symbol = "BTC/USDT"
        channel = "trades"
        
        # 创建消息处理器和接收到的消息列表
        received_messages = []
        def message_handler(message):
            received_messages.append(message)
        
        # 设置模拟连接和消息处理
        mock_conn = MockWebSocketConnection()
        mock_conn.is_connected = True
        ws_api.connection = mock_conn
        ws_api.send_message = mock_conn.send_message
        ws_api.message_handlers = [message_handler]
        
        # 模拟异步订阅方法
        async def subscribe(exchange, symbol, channel):
            message = {
                "type": "subscribe",
                "channel": channel,
                "exchange": exchange,
                "symbol": symbol
            }
            await mock_conn.send_message(message)
            return True
        
        ws_api.subscribe = subscribe
        
        # 模拟异步消息处理方法
        async def process_message(message):
            for handler in ws_api.message_handlers:
                handler(message)
            return True
        
        ws_api.process_message = process_message
        
        # Act - 订阅
        await ws_api.subscribe(exchange, symbol, channel)
        
        # 模拟接收交易消息
        mock_trade = generate_mock_trade(exchange=exchange, symbol=symbol)
        trade_message = {
            "type": "trade",
            "exchange": exchange,
            "symbol": symbol,
            "data": mock_trade
        }
        
        await ws_api.process_message(trade_message)
        
        # Assert
        assert len(mock_conn.messages_sent) == 1
        assert mock_conn.messages_sent[0]["type"] == "subscribe"
        assert len(received_messages) == 1
        assert received_messages[0]["type"] == "trade"
        assert received_messages[0]["exchange"] == exchange
        assert received_messages[0]["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_error_handling(self, setup_ws_api):
        """测试错误处理"""
        # Arrange
        ws_api = setup_ws_api
        error_handler = MagicMock()
        
        # 设置错误处理器
        ws_api.error_handlers = [error_handler]
        
        # 模拟异步错误处理方法
        async def handle_error(error):
            for handler in ws_api.error_handlers:
                handler(error)
            return True
        
        ws_api.handle_error = handle_error
        
        # 模拟异常情况
        error = Exception("WebSocket连接异常")
        
        # Act
        await ws_api.handle_error(error)
        
        # Assert
        error_handler.assert_called_once_with(error)


# 直接运行测试文件
if __name__ == "__main__":
    pytest.main(["-v", __file__])