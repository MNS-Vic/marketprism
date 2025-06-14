"""
真实交易所连接测试模块
测试与实际交易所WebSocket的连接和数据接收
"""

from datetime import datetime, timezone
import pytest
import asyncio
import websocket
import ssl
import json
import time
import logging
from typing import Dict, List, Optional, Any
import aiohttp
from unittest.mock import AsyncMock
import threading
from queue import Queue, Empty

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExchangeConnectionTester:
    """交易所连接测试器"""
    
    def __init__(self):
        self.connections = {}
        self.message_queues = {}
        self.connection_status = {}
        
    def setup_test_environment(self):
        """设置测试环境"""
        # 初始化各交易所连接状态
        self.exchanges = ['binance', 'okx', 'deribit']
        for exchange in self.exchanges:
            self.connections[exchange] = None
            self.message_queues[exchange] = Queue()
            self.connection_status[exchange] = False

@pytest.fixture(scope="class")
def exchange_tester():
    """交易所测试器fixture"""
    tester = ExchangeConnectionTester()
    tester.setup_test_environment()
    yield tester

class TestBinanceConnection:
    """Binance连接测试"""
    
    @pytest.mark.asyncio
    async def test_binance_rest_api_connectivity(self):
        """测试Binance REST API连接"""
        base_url = "https://api.binance.com"
        endpoints = [
            "/api/v3/ping",
            "/api/v3/time",
            "/api/v3/exchangeInfo"
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints:
                url = base_url + endpoint
                try:
                    async with session.get(url, timeout=10) as response:
                        assert response.status == 200, f"Binance API {endpoint} 响应异常: {response.status}"
                        data = await response.json()
                        assert data is not None, f"Binance API {endpoint} 返回空数据"
                        logger.info(f"✅ Binance REST API测试通过: {endpoint}")
                except Exception as e:
                    pytest.fail(f"Binance REST API测试失败 {endpoint}: {e}")
    
    @pytest.mark.asyncio
    async def test_binance_websocket_connection(self, exchange_tester):
        """测试Binance WebSocket连接"""
        ws_url = "wss://stream.binance.com:9443/ws/btcusdt@ticker"
        
        try:
            # 使用异步WebSocket客户端
            import websockets
            
            async with websockets.connect(ws_url, ssl=ssl.create_default_context()) as websocket:
                # 等待接收数据
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(message)
                    
                    # 验证数据格式
                    assert 'e' in data, "Binance WebSocket数据格式异常：缺少事件类型"
                    assert data['e'] == '24hrTicker', f"期望事件类型为24hrTicker，实际为: {data['e']}"
                    assert 's' in data, "Binance WebSocket数据格式异常：缺少交易对"
                    assert data['s'] == 'BTCUSDT', f"期望交易对为BTCUSDT，实际为: {data['s']}"
                    
                    exchange_tester.connection_status['binance'] = True
                    logger.info("✅ Binance WebSocket连接测试成功")
                    logger.info(f"接收到数据: {data['s']} 价格: {data.get('c', 'N/A')}")
                    
                except asyncio.TimeoutError:
                    pytest.fail("Binance WebSocket连接超时，未收到数据")
                    
        except Exception as e:
            pytest.fail(f"Binance WebSocket连接失败: {e}")
    
    @pytest.mark.asyncio
    async def test_binance_trade_stream(self):
        """测试Binance交易流数据"""
        ws_url = "wss://stream.binance.com:9443/ws/btcusdt@trade"
        
        try:
            import websockets
            
            async with websockets.connect(ws_url, ssl=ssl.create_default_context()) as websocket:
                # 收集多个交易数据来验证流的稳定性
                trades_received = 0
                timeout_seconds = 15
                
                while trades_received < 3 and timeout_seconds > 0:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        # 验证交易数据格式
                        required_fields = ['e', 's', 't', 'p', 'q', 'T', 'm']
                        for field in required_fields:
                            assert field in data, f"交易数据缺少字段: {field}"
                        
                        assert data['e'] == 'trade', f"期望事件类型为trade，实际为: {data['e']}"
                        assert data['s'] == 'BTCUSDT', f"期望交易对为BTCUSDT，实际为: {data['s']}"
                        
                        trades_received += 1
                        logger.info(f"收到Binance交易数据 #{trades_received}: 价格={data['p']}, 数量={data['q']}")
                        
                    except asyncio.TimeoutError:
                        timeout_seconds -= 1
                        continue
                
                assert trades_received >= 1, f"未收到足够的交易数据，仅收到{trades_received}条"
                logger.info(f"✅ Binance交易流测试成功，共收到{trades_received}条交易数据")
                
        except Exception as e:
            pytest.fail(f"Binance交易流测试失败: {e}")

class TestOKXConnection:
    """OKX连接测试"""
    
    @pytest.mark.asyncio
    async def test_okx_rest_api_connectivity(self):
        """测试OKX REST API连接"""
        base_url = "https://www.okx.com"
        endpoints = [
            "/api/v5/public/time",
            "/api/v5/public/instruments?instType=SPOT&instId=BTC-USDT"
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints:
                url = base_url + endpoint
                try:
                    async with session.get(url, timeout=10) as response:
                        assert response.status == 200, f"OKX API {endpoint} 响应异常: {response.status}"
                        data = await response.json()
                        assert data is not None, f"OKX API {endpoint} 返回空数据"
                        assert 'code' in data, "OKX API响应缺少code字段"
                        assert data['code'] == '0', f"OKX API错误码: {data.get('code')} - {data.get('msg')}"
                        logger.info(f"✅ OKX REST API测试通过: {endpoint}")
                except Exception as e:
                    pytest.fail(f"OKX REST API测试失败 {endpoint}: {e}")
    
    @pytest.mark.asyncio
    async def test_okx_websocket_connection(self, exchange_tester):
        """测试OKX WebSocket连接"""
        ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        
        try:
            import websockets
            
            async with websockets.connect(ws_url, ssl=ssl.create_default_context()) as websocket:
                # 发送订阅消息
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        {
                            "channel": "tickers",
                            "instId": "BTC-USDT"
                        }
                    ]
                }
                
                await websocket.send(json.dumps(subscribe_msg))
                logger.info("已发送OKX订阅请求")
                
                # 等待订阅确认和数据
                messages_received = 0
                timeout_seconds = 15
                
                while messages_received < 2 and timeout_seconds > 0:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if 'event' in data and data['event'] == 'subscribe':
                            logger.info("✅ OKX订阅确认收到")
                            messages_received += 1
                        elif 'data' in data and len(data['data']) > 0:
                            ticker_data = data['data'][0]
                            assert 'instId' in ticker_data, "OKX ticker数据缺少instId"
                            assert ticker_data['instId'] == 'BTC-USDT', f"期望instId为BTC-USDT，实际为: {ticker_data['instId']}"
                            logger.info(f"✅ 收到OKX ticker数据: {ticker_data['instId']} 价格: {ticker_data.get('last', 'N/A')}")
                            messages_received += 1
                            exchange_tester.connection_status['okx'] = True
                        
                    except asyncio.TimeoutError:
                        timeout_seconds -= 1
                        continue
                
                assert messages_received >= 2, f"未收到足够的OKX消息，仅收到{messages_received}条"
                logger.info("✅ OKX WebSocket连接测试成功")
                
        except Exception as e:
            pytest.fail(f"OKX WebSocket连接失败: {e}")
    
    @pytest.mark.asyncio
    async def test_okx_trade_stream(self):
        """测试OKX交易流数据"""
        ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        
        try:
            import websockets
            
            async with websockets.connect(ws_url, ssl=ssl.create_default_context()) as websocket:
                # 订阅交易数据
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        {
                            "channel": "trades",
                            "instId": "BTC-USDT"
                        }
                    ]
                }
                
                await websocket.send(json.dumps(subscribe_msg))
                
                trades_received = 0
                timeout_seconds = 20
                
                while trades_received < 2 and timeout_seconds > 0:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if 'data' in data and len(data['data']) > 0:
                            for trade in data['data']:
                                if 'instId' in trade and trade['instId'] == 'BTC-USDT':
                                    required_fields = ['tradeId', 'px', 'sz', 'side', 'ts']
                                    for field in required_fields:
                                        assert field in trade, f"OKX交易数据缺少字段: {field}"
                                    
                                    trades_received += 1
                                    logger.info(f"收到OKX交易数据 #{trades_received}: 价格={trade['px']}, 数量={trade['sz']}, 方向={trade['side']}")
                        
                    except asyncio.TimeoutError:
                        timeout_seconds -= 1
                        continue
                
                assert trades_received >= 1, f"未收到足够的OKX交易数据，仅收到{trades_received}条"
                logger.info(f"✅ OKX交易流测试成功，共收到{trades_received}条交易数据")
                
        except Exception as e:
            pytest.fail(f"OKX交易流测试失败: {e}")

class TestDeribitConnection:
    """Deribit连接测试"""
    
    @pytest.mark.asyncio
    async def test_deribit_rest_api_connectivity(self):
        """测试Deribit REST API连接"""
        base_url = "https://www.deribit.com"
        endpoints = [
            "/api/v2/public/get_time",
            "/api/v2/public/get_instruments?currency=BTC&kind=future&expired=false"
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints:
                url = base_url + endpoint
                try:
                    async with session.get(url, timeout=10) as response:
                        assert response.status == 200, f"Deribit API {endpoint} 响应异常: {response.status}"
                        data = await response.json()
                        assert data is not None, f"Deribit API {endpoint} 返回空数据"
                        assert 'result' in data, "Deribit API响应缺少result字段"
                        logger.info(f"✅ Deribit REST API测试通过: {endpoint}")
                except Exception as e:
                    pytest.fail(f"Deribit REST API测试失败 {endpoint}: {e}")
    
    @pytest.mark.asyncio
    async def test_deribit_websocket_connection(self, exchange_tester):
        """测试Deribit WebSocket连接"""
        ws_url = "wss://www.deribit.com/ws/api/v2"
        
        try:
            import websockets
            
            async with websockets.connect(ws_url, ssl=ssl.create_default_context()) as websocket:
                # 发送订阅消息
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "public/subscribe",
                    "params": {
                        "channels": ["ticker.BTC-PERPETUAL.raw"]
                    }
                }
                
                await websocket.send(json.dumps(subscribe_msg))
                logger.info("已发送Deribit订阅请求")
                
                # 等待订阅确认和数据
                messages_received = 0
                timeout_seconds = 15
                
                while messages_received < 2 and timeout_seconds > 0:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if 'id' in data and data['id'] == 1 and 'result' in data:
                            logger.info("✅ Deribit订阅确认收到")
                            messages_received += 1
                        elif 'params' in data and 'data' in data['params']:
                            ticker_data = data['params']['data']
                            assert 'instrument_name' in ticker_data, "Deribit ticker数据缺少instrument_name"
                            assert ticker_data['instrument_name'] == 'BTC-PERPETUAL', \
                                f"期望instrument_name为BTC-PERPETUAL，实际为: {ticker_data['instrument_name']}"
                            logger.info(f"✅ 收到Deribit ticker数据: {ticker_data['instrument_name']} 价格: {ticker_data.get('last_price', 'N/A')}")
                            messages_received += 1
                            exchange_tester.connection_status['deribit'] = True
                        
                    except asyncio.TimeoutError:
                        timeout_seconds -= 1
                        continue
                
                assert messages_received >= 2, f"未收到足够的Deribit消息，仅收到{messages_received}条"
                logger.info("✅ Deribit WebSocket连接测试成功")
                
        except Exception as e:
            pytest.fail(f"Deribit WebSocket连接失败: {e}")
    
    @pytest.mark.asyncio
    async def test_deribit_trade_stream(self):
        """测试Deribit交易流数据"""
        ws_url = "wss://www.deribit.com/ws/api/v2"
        
        try:
            import websockets
            
            async with websockets.connect(ws_url, ssl=ssl.create_default_context()) as websocket:
                # 订阅交易数据
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "public/subscribe",
                    "params": {
                        "channels": ["trades.BTC-PERPETUAL.raw"]
                    }
                }
                
                await websocket.send(json.dumps(subscribe_msg))
                
                trades_received = 0
                timeout_seconds = 20
                
                while trades_received < 2 and timeout_seconds > 0:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        
                        if 'params' in data and 'data' in data['params']:
                            trades_data = data['params']['data']
                            if isinstance(trades_data, list):
                                for trade in trades_data:
                                    if 'instrument_name' in trade and trade['instrument_name'] == 'BTC-PERPETUAL':
                                        required_fields = ['trade_id', 'price', 'amount', 'direction', 'timestamp']
                                        for field in required_fields:
                                            assert field in trade, f"Deribit交易数据缺少字段: {field}"
                                        
                                        trades_received += 1
                                        logger.info(f"收到Deribit交易数据 #{trades_received}: 价格={trade['price']}, 数量={trade['amount']}, 方向={trade['direction']}")
                        
                    except asyncio.TimeoutError:
                        timeout_seconds -= 1
                        continue
                
                assert trades_received >= 1, f"未收到足够的Deribit交易数据，仅收到{trades_received}条"
                logger.info(f"✅ Deribit交易流测试成功，共收到{trades_received}条交易数据")
                
        except Exception as e:
            pytest.fail(f"Deribit交易流测试失败: {e}")

class TestExchangeConnectivitySummary:
    """交易所连接性汇总测试"""
    
    @pytest.mark.asyncio
    async def test_all_exchanges_connectivity(self, exchange_tester):
        """测试所有交易所的连接性汇总"""
        
        # 运行基本连接测试
        connectivity_results = {
            'binance': False,
            'okx': False, 
            'deribit': False
        }
        
        # 测试Binance
        try:
            import websockets
            async with websockets.connect("wss://stream.binance.com:9443/ws/btcusdt@ticker") as ws:
                message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                if json.loads(message):
                    connectivity_results['binance'] = True
        except Exception as e:
            logger.warning(f"Binance连接测试失败: {e}")
        
        # 测试OKX
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.okx.com/api/v5/public/time", timeout=5) as response:
                    if response.status == 200:
                        connectivity_results['okx'] = True
        except Exception as e:
            logger.warning(f"OKX连接测试失败: {e}")
        
        # 测试Deribit
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.deribit.com/api/v2/public/get_time", timeout=5) as response:
                    if response.status == 200:
                        connectivity_results['deribit'] = True
        except Exception as e:
            logger.warning(f"Deribit连接测试失败: {e}")
        
        # 汇总结果
        connected_exchanges = sum(connectivity_results.values())
        total_exchanges = len(connectivity_results)
        
        logger.info(f"交易所连接性测试汇总: {connected_exchanges}/{total_exchanges} 交易所连接成功")
        
        for exchange, status in connectivity_results.items():
            status_text = "✅ 连接成功" if status else "❌ 连接失败"
            logger.info(f"{exchange.upper()}: {status_text}")
        
        # 至少要有2个交易所连接成功
        assert connected_exchanges >= 2, f"交易所连接失败，仅有{connected_exchanges}/{total_exchanges}个交易所连接成功"
        
        return connectivity_results

@pytest.mark.asyncio
async def test_exchange_websocket_stability():
    """测试交易所WebSocket连接稳定性"""
    
    stability_test_duration = 30  # 30秒稳定性测试
    exchanges_config = [
        {
            'name': 'binance',
            'url': 'wss://stream.binance.com:9443/ws/btcusdt@ticker',
            'expected_field': 'c'
        },
        {
            'name': 'okx', 
            'url': 'wss://ws.okx.com:8443/ws/v5/public',
            'subscribe_msg': {
                "op": "subscribe",
                "args": [{"channel": "tickers", "instId": "BTC-USDT"}]
            },
            'expected_field': 'data'
        }
    ]
    
    async def test_exchange_stability(exchange_config):
        """测试单个交易所的稳定性"""
        name = exchange_config['name']
        url = exchange_config['url']
        messages_received = 0
        start_time = time.time()
        
        try:
            import websockets
            async with websockets.connect(url, ssl=ssl.create_default_context()) as websocket:
                
                # 如果需要发送订阅消息
                if 'subscribe_msg' in exchange_config:
                    await websocket.send(json.dumps(exchange_config['subscribe_msg']))
                
                while time.time() - start_time < stability_test_duration:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        data = json.loads(message)
                        if exchange_config['expected_field'] in str(data):
                            messages_received += 1
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.warning(f"{name} 接收消息时出错: {e}")
                        break
                
                logger.info(f"{name.upper()} 稳定性测试完成: {stability_test_duration}秒内收到{messages_received}条消息")
                return messages_received > 0
                
        except Exception as e:
            logger.error(f"{name.upper()} 稳定性测试失败: {e}")
            return False
    
    # 并发测试多个交易所
    tasks = [test_exchange_stability(config) for config in exchanges_config]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 分析结果
    successful_exchanges = sum(1 for result in results if result is True)
    total_exchanges = len(exchanges_config)
    
    logger.info(f"WebSocket稳定性测试完成: {successful_exchanges}/{total_exchanges} 交易所通过稳定性测试")
    
    # 至少要有1个交易所通过稳定性测试
    assert successful_exchanges >= 1, f"WebSocket稳定性测试失败，无交易所通过稳定性测试"

if __name__ == "__main__":
    # 运行快速连接测试
    async def quick_test():
        result = await test_exchange_websocket_stability()
        print(f"快速连接测试完成")
    
    asyncio.run(quick_test()) 