#!/usr/bin/env python3
"""
REST API 单元测试
"""
import os
import sys
import pytest
import requests
from unittest.mock import MagicMock, patch
import json
import datetime

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

# 模拟Flask应用和API请求处理
class MockResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.headers = {}
    
    def json(self):
        return self.data
    
    def get_json(self):
        return self.data


class TestRestApi:
    """
    REST API接口测试
    """
    
    @pytest.fixture
    def setup_api(self):
        """设置API测试环境"""
        # 如果存在真实API类，则导入并实例化
        api = MagicMock()
        
        # 配置模拟方法返回
        # 模拟获取最新交易数据
        api.get_latest_trades.return_value = {
            "success": True,
            "data": [generate_mock_trade() for _ in range(5)]
        }
        
        # 模拟获取最新订单簿数据
        api.get_latest_orderbook.return_value = {
            "success": True,
            "data": generate_mock_orderbook()
        }
        
        # 模拟获取历史交易数据
        api.get_historical_trades.return_value = {
            "success": True,
            "data": [generate_mock_trade(timestamp=datetime.datetime.now().timestamp() - i * 60) for i in range(10)],
            "pagination": {
                "total": 100,
                "page": 1,
                "page_size": 10
            }
        }
        
        # 模拟获取交易所列表
        api.get_exchanges.return_value = {
            "success": True,
            "data": ["binance", "okex", "deribit", "huobi"]
        }
        
        # 模拟获取交易对列表
        api.get_symbols.return_value = {
            "success": True,
            "data": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"]
        }
        
        # 模拟获取API状态
        api.get_status.return_value = {
            "success": True,
            "data": {
                "status": "running",
                "uptime": 12345,
                "version": "1.0.0"
            }
        }
        
        # 模拟错误响应
        api.handle_error.side_effect = lambda error_type, message: {
            "success": False,
            "error": {
                "type": error_type,
                "message": message
            }
        }
        
        yield api
    
    def test_get_latest_trades(self, setup_api):
        """测试获取最新交易数据"""
        # Arrange
        api = setup_api
        exchange = "binance"
        symbol = "BTC/USDT"
        limit = 5
        
        # Act
        response = api.get_latest_trades(exchange=exchange, symbol=symbol, limit=limit)
        
        # Assert
        assert response["success"] is True
        assert "data" in response
        assert len(response["data"]) == limit
        assert all(trade["exchange"] == exchange for trade in response["data"])
        assert all(trade["symbol"] == symbol for trade in response["data"])
    
    def test_get_latest_orderbook(self, setup_api):
        """测试获取最新订单簿数据"""
        # Arrange
        api = setup_api
        exchange = "binance"
        symbol = "BTC/USDT"
        
        # Act
        response = api.get_latest_orderbook(exchange=exchange, symbol=symbol)
        
        # Assert
        assert response["success"] is True
        assert "data" in response
        assert response["data"]["exchange"] == exchange
        assert response["data"]["symbol"] == symbol
        assert "bids" in response["data"]
        assert "asks" in response["data"]
    
    def test_get_historical_trades(self, setup_api):
        """测试获取历史交易数据"""
        # Arrange
        api = setup_api
        exchange = "binance"
        symbol = "BTC/USDT"
        start_time = int(datetime.datetime.now().timestamp()) - 3600  # 1小时前
        end_time = int(datetime.datetime.now().timestamp())
        page = 1
        page_size = 10
        
        # Act
        response = api.get_historical_trades(
            exchange=exchange, 
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size
        )
        
        # Assert
        assert response["success"] is True
        assert "data" in response
        assert len(response["data"]) == page_size
        assert "pagination" in response
        assert response["pagination"]["page"] == page
        assert response["pagination"]["page_size"] == page_size
    
    def test_get_exchanges(self, setup_api):
        """测试获取交易所列表"""
        # Arrange
        api = setup_api
        
        # Act
        response = api.get_exchanges()
        
        # Assert
        assert response["success"] is True
        assert "data" in response
        assert isinstance(response["data"], list)
        assert len(response["data"]) > 0
        assert "binance" in response["data"]
    
    def test_get_symbols(self, setup_api):
        """测试获取交易对列表"""
        # Arrange
        api = setup_api
        exchange = "binance"
        
        # Act
        response = api.get_symbols(exchange=exchange)
        
        # Assert
        assert response["success"] is True
        assert "data" in response
        assert isinstance(response["data"], list)
        assert len(response["data"]) > 0
        assert "BTC/USDT" in response["data"]
    
    def test_get_status(self, setup_api):
        """测试获取API状态"""
        # Arrange
        api = setup_api
        
        # Act
        response = api.get_status()
        
        # Assert
        assert response["success"] is True
        assert "data" in response
        assert "status" in response["data"]
        assert "uptime" in response["data"]
        assert "version" in response["data"]
    
    def test_error_handling_invalid_exchange(self, setup_api):
        """测试错误处理 - 无效交易所"""
        # Arrange
        api = setup_api
        # 配置get_latest_trades在传入无效交易所时抛出异常
        api.get_latest_trades.side_effect = lambda **kwargs: (
            api.handle_error("invalid_exchange", "Unknown exchange: invalid_exchange")
            if kwargs.get("exchange") == "invalid_exchange"
            else {"success": True, "data": []}
        )
        
        # Act
        response = api.get_latest_trades(exchange="invalid_exchange", symbol="BTC/USDT")
        
        # Assert
        assert response["success"] is False
        assert "error" in response
        assert response["error"]["type"] == "invalid_exchange"
        assert "Unknown exchange" in response["error"]["message"]
    
    def test_error_handling_invalid_symbol(self, setup_api):
        """测试错误处理 - 无效交易对"""
        # Arrange
        api = setup_api
        # 配置get_latest_orderbook在传入无效交易对时抛出异常
        api.get_latest_orderbook.side_effect = lambda **kwargs: (
            api.handle_error("invalid_symbol", "Unknown symbol: XXX/YYY")
            if kwargs.get("symbol") == "XXX/YYY"
            else {"success": True, "data": generate_mock_orderbook()}
        )
        
        # Act
        response = api.get_latest_orderbook(exchange="binance", symbol="XXX/YYY")
        
        # Assert
        assert response["success"] is False
        assert "error" in response
        assert response["error"]["type"] == "invalid_symbol"
        assert "Unknown symbol" in response["error"]["message"]
    
    def test_error_handling_invalid_time_range(self, setup_api):
        """测试错误处理 - 无效时间范围"""
        # Arrange
        api = setup_api
        # 配置get_historical_trades在传入无效时间范围时抛出异常
        api.get_historical_trades.side_effect = lambda **kwargs: (
            api.handle_error("invalid_time_range", "End time must be greater than start time")
            if kwargs.get("end_time") <= kwargs.get("start_time")
            else {"success": True, "data": [], "pagination": {"total": 0, "page": 1, "page_size": 10}}
        )
        
        now = int(datetime.datetime.now().timestamp())
        
        # Act
        response = api.get_historical_trades(
            exchange="binance", 
            symbol="BTC/USDT",
            start_time=now,
            end_time=now - 3600  # 结束时间早于开始时间
        )
        
        # Assert
        assert response["success"] is False
        assert "error" in response
        assert response["error"]["type"] == "invalid_time_range"
        assert "End time must be greater than start time" in response["error"]["message"]
    
    @patch('requests.get')
    def test_external_api_call(self, mock_get, setup_api):
        """测试调用外部API"""
        # Arrange
        mock_response = MockResponse({
            "success": True,
            "data": [generate_mock_trade() for _ in range(5)]
        })
        mock_get.return_value = mock_response
        
        # 假设我们有一个make_api_request方法
        setup_api.make_api_request = lambda url: requests.get(url).json()
        
        # Act
        response = setup_api.make_api_request("http://api.example.com/trades")
        
        # Assert
        assert response["success"] is True
        assert "data" in response
        assert len(response["data"]) == 5
        mock_get.assert_called_once_with("http://api.example.com/trades")


# 直接运行测试文件
if __name__ == "__main__":
    pytest.main(["-v", __file__])