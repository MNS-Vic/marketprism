"""
MarketPrism 市场数据API集成测试

测试市场数据API与后端服务的集成
"""
import sys
import os
import json
import time
import asyncio
import pytest
import aiohttp
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入测试辅助工具    
from tests.utils.data_factory import data_factory
from tests.utils.test_helpers import test_helpers

# API配置
API_CONFIG = {
    "base_url": "http://localhost:8000",
    "endpoints": {
        "trades": "/api/v1/trades",
        "orderbooks": "/api/v1/orderbooks",
        "klines": "/api/v1/klines",
        "funding_rates": "/api/v1/funding_rates",
        "exchanges": "/api/v1/exchanges"
    }
}

# 检测API是否可用
def is_api_available():
    """检测API服务是否可用"""
    import requests
    try:
        response = requests.get(f"{API_CONFIG['base_url']}/api/v1/exchanges", timeout=2)
        return response.status_code == 200
    except:
        return False

# 跳过无法运行的API测试
pytestmark = pytest.mark.skipif(
    not is_api_available(),
    reason="API服务不可用，跳过API集成测试"
)

@pytest.mark.integration
class TestMarketDataApi:
    """测试市场数据API的集成功能"""
    
    @pytest.fixture
    async def api_client(self):
        """创建API客户端"""
        async with aiohttp.ClientSession() as session:
            yield session
    
    @pytest.mark.asyncio
    async def test_exchanges_endpoint(self, api_client):
        """测试交易所列表接口"""
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['exchanges']}"
        
        async with api_client.get(url) as response:
            # 验证状态码
            assert response.status == 200
            
            # 解析响应数据
            data = await response.json()
            
            # 验证响应结构
            assert "exchanges" in data
            assert isinstance(data["exchanges"], list)
            
            # 验证至少有一个交易所
            assert len(data["exchanges"]) > 0
            
            # 验证交易所数据结构
            for exchange in data["exchanges"]:
                assert "name" in exchange
                assert "status" in exchange
                # 可能还有其他字段，根据实际API调整
    
    @pytest.mark.asyncio
    async def test_trades_endpoint(self, api_client):
        """测试交易数据接口"""
        # 准备查询参数
        params = {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "limit": 10
        }
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['trades']}"
        
        async with api_client.get(url, params=params) as response:
            # 验证状态码
            assert response.status == 200
            
            # 解析响应数据
            data = await response.json()
            
            # 验证响应结构
            assert "trades" in data
            assert isinstance(data["trades"], list)
            
            # 如果有交易数据，验证数据结构
            if data["trades"]:
                for trade in data["trades"]:
                    assert "exchange" in trade
                    assert "symbol" in trade
                    assert "price" in trade
                    assert "amount" in trade
                    assert "timestamp" in trade
                    assert "trade_id" in trade
                    assert "side" in trade
    
    @pytest.mark.asyncio
    async def test_orderbooks_endpoint(self, api_client):
        """测试订单簿数据接口"""
        # 准备查询参数
        params = {
            "exchange": "binance",
            "symbol": "BTC/USDT"
        }
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['orderbooks']}"
        
        async with api_client.get(url, params=params) as response:
            # 验证状态码
            assert response.status == 200
            
            # 解析响应数据
            data = await response.json()
            
            # 验证响应结构
            assert "orderbook" in data
            orderbook = data["orderbook"]
            
            if orderbook:  # 如果有订单簿数据
                assert "exchange" in orderbook
                assert "symbol" in orderbook
                assert "timestamp" in orderbook
                assert "bids" in orderbook
                assert "asks" in orderbook
                
                # 验证买单和卖单
                assert isinstance(orderbook["bids"], list)
                assert isinstance(orderbook["asks"], list)
                
                # 如果有买单，验证格式
                if orderbook["bids"]:
                    for bid in orderbook["bids"]:
                        assert len(bid) == 2  # [价格, 数量]
                        
                # 如果有卖单，验证格式
                if orderbook["asks"]:
                    for ask in orderbook["asks"]:
                        assert len(ask) == 2  # [价格, 数量]
    
    @pytest.mark.asyncio
    async def test_klines_endpoint(self, api_client):
        """测试K线数据接口"""
        # 准备查询参数
        params = {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "interval": "1m",
            "limit": 10
        }
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['klines']}"
        
        async with api_client.get(url, params=params) as response:
            # 验证状态码
            assert response.status == 200
            
            # 解析响应数据
            data = await response.json()
            
            # 验证响应结构
            assert "klines" in data
            assert isinstance(data["klines"], list)
            
            # 如果有K线数据，验证数据结构
            if data["klines"]:
                for kline in data["klines"]:
                    assert "exchange" in kline
                    assert "symbol" in kline
                    assert "interval" in kline
                    assert "open_time" in kline
                    assert "close_time" in kline
                    assert "open" in kline
                    assert "high" in kline
                    assert "low" in kline
                    assert "close" in kline
                    assert "volume" in kline
    
    @pytest.mark.asyncio
    async def test_funding_rates_endpoint(self, api_client):
        """测试资金费率数据接口"""
        # 准备查询参数
        params = {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "limit": 10
        }
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['funding_rates']}"
        
        async with api_client.get(url, params=params) as response:
            # 验证状态码
            assert response.status == 200
            
            # 解析响应数据
            data = await response.json()
            
            # 验证响应结构
            assert "funding_rates" in data
            assert isinstance(data["funding_rates"], list)
            
            # 如果有资金费率数据，验证数据结构
            if data["funding_rates"]:
                for rate in data["funding_rates"]:
                    assert "exchange" in rate
                    assert "symbol" in rate
                    assert "timestamp" in rate
                    assert "funding_rate" in rate
                    assert "next_funding_time" in rate
    
    @pytest.mark.asyncio
    async def test_error_handling(self, api_client):
        """测试错误处理"""
        # 测试无效的交易所参数
        params = {
            "exchange": "invalid_exchange",
            "symbol": "BTC/USDT",
            "limit": 10
        }
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['trades']}"
        
        async with api_client.get(url, params=params) as response:
            # 验证是否返回适当的错误状态码
            assert response.status in [400, 404, 422]
            
            # 解析响应数据
            data = await response.json()
            
            # 验证错误响应结构
            assert "error" in data or "detail" in data
    
    @pytest.mark.asyncio
    async def test_parameter_validation(self, api_client):
        """测试参数验证"""
        # 测试各种无效参数
        test_cases = [
            # 缺少必要参数
            {"limit": 10},
            # 无效的limit参数
            {"exchange": "binance", "symbol": "BTC/USDT", "limit": -1},
            # 无效的时间范围
            {"exchange": "binance", "symbol": "BTC/USDT", "start_time": "invalid", "end_time": "invalid"}
        ]
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['trades']}"
        
        for params in test_cases:
            async with api_client.get(url, params=params) as response:
                # 验证是否返回适当的错误状态码
                assert response.status in [400, 422]
                
                # 解析响应数据
                data = await response.json()
                
                # 验证错误响应结构
                assert "error" in data or "detail" in data
    
    @pytest.mark.asyncio
    async def test_performance(self, api_client):
        """测试API性能"""
        # 准备查询参数
        params = {
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "limit": 100  # 较大的数据量
        }
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['trades']}"
        
        # 记录开始时间
        start_time = time.time()
        
        async with api_client.get(url, params=params) as response:
            # 验证状态码
            assert response.status == 200
            
            # 解析响应数据
            data = await response.json()
        
        # 计算响应时间
        response_time = time.time() - start_time
        
        # 验证性能指标
        assert response_time < 2.0, f"API响应时间过长: {response_time:.2f}秒"


@pytest.mark.integration
class TestApiToBackendIntegration:
    """测试API到后端服务的集成"""
    
    @pytest.fixture
    async def setup_data(self):
        """准备测试数据并发布到后端服务"""
        # 这里应该实现向后端服务（如NATS和ClickHouse）
        # 发布测试数据的逻辑，具体实现取决于实际部署情况
        
        # 由于这是一个集成测试，可能需要直接使用实际的服务客户端
        # 而不是模拟对象，但这需要确保相关服务可用
        
        # 以下是一个假设的实现，实际中需要调整
        try:
            # 假设的NATS和ClickHouse连接
            import nats
            from clickhouse_driver import Client
            
            # 连接NATS
            nc = await nats.connect("nats://localhost:4222")
            
            # 连接ClickHouse
            ch = Client(host='localhost', port=9000, user='default', password='')
            
            # 准备测试数据
            exchange = "binance"
            symbol = "BTC/USDT"
            test_count = 5
            
            trades = data_factory.create_batch(data_factory.create_trade, test_count, 
                                            exchange=exchange, symbol=symbol)
            
            # 发布交易数据到NATS
            for trade in trades:
                subject = f"MARKET.TRADES.{exchange}.{symbol.replace('/', '_')}"
                await nc.publish(subject, json.dumps(trade).encode())
            
            # 等待数据处理
            await asyncio.sleep(2)
            
            # 关闭连接
            await nc.close()
            
            # 返回测试数据
            return {
                "exchange": exchange,
                "symbol": symbol,
                "trades": trades
            }
        except:
            # 如果服务不可用，则跳过测试
            pytest.skip("无法连接到后端服务")
    
    @pytest.fixture
    async def api_client(self):
        """创建API客户端"""
        async with aiohttp.ClientSession() as session:
            yield session
    
    @pytest.mark.asyncio
    async def test_data_flow_integration(self, setup_data, api_client):
        """测试数据从后端到API的流动"""
        # 获取测试数据
        exchange = setup_data["exchange"]
        symbol = setup_data["symbol"]
        test_trades = setup_data["trades"]
        
        # 准备查询参数
        params = {
            "exchange": exchange,
            "symbol": symbol,
            "limit": len(test_trades) + 5  # 多查询几条以确保包含所有测试数据
        }
        
        url = f"{API_CONFIG['base_url']}{API_CONFIG['endpoints']['trades']}"
        
        # 查询API
        async with api_client.get(url, params=params) as response:
            # 验证状态码
            assert response.status == 200
            
            # 解析响应数据
            data = await response.json()
            
            # 获取交易列表
            api_trades = data["trades"]
            
            # 验证测试数据是否在API返回结果中
            test_trade_ids = [trade["trade_id"] for trade in test_trades]
            api_trade_ids = [trade["trade_id"] for trade in api_trades]
            
            for trade_id in test_trade_ids:
                assert trade_id in api_trade_ids, f"测试交易ID {trade_id} 未在API响应中找到"


if __name__ == "__main__":
    pytest.main(["-v", __file__])