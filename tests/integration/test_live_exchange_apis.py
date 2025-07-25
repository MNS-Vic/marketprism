"""
真实交易所API集成测试
专为CI/CD环境设计，使用公共API端点进行测试，包含适当的频率限制
"""

import pytest
import asyncio
import time
import requests
import websockets
import json
from typing import Dict, Any, List
from unittest.mock import patch
import logging

from tests.utils.api_rate_limiter import rate_limited_request, get_rate_limiter, get_api_stats

logger = logging.getLogger(__name__)

# 测试配置
EXCHANGES_CONFIG = {
    'binance': {
        'rest_base': 'https://api.binance.com',
        'ws_base': 'wss://stream.binance.com:9443',
        'test_symbol': 'BTCUSDT',
        'orderbook_endpoint': '/api/v3/depth',
        'ticker_endpoint': '/api/v3/ticker/24hr',
        'ws_orderbook_stream': '/ws/btcusdt@depth5'
    },
    'okx': {
        'rest_base': 'https://www.okx.com',
        'ws_base': 'wss://ws.okx.com:8443',
        'test_symbol': 'BTC-USDT',
        'orderbook_endpoint': '/api/v5/market/books',
        'ticker_endpoint': '/api/v5/market/ticker',
        'ws_orderbook_stream': '/ws/v5/public'
    }
}

@pytest.mark.live_api
@pytest.mark.ci
@pytest.mark.rate_limited
class TestLiveExchangeAPIs:
    """真实交易所API测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.rate_limiter = get_rate_limiter()
        logger.info("开始真实API测试，启用频率限制")
    
    def teardown_method(self):
        """测试后清理"""
        # 打印API使用统计
        for exchange in EXCHANGES_CONFIG.keys():
            stats = get_api_stats(exchange)
            logger.info(f"{exchange} API统计: {stats}")
    
    @rate_limited_request('binance', 'orderbook')
    def test_binance_orderbook_api(self):
        """测试Binance订单簿API"""
        config = EXCHANGES_CONFIG['binance']
        url = f"{config['rest_base']}{config['orderbook_endpoint']}"
        
        params = {
            'symbol': config['test_symbol'],
            'limit': 5
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        # 验证响应
        assert response.status_code == 200, f"Binance API返回错误状态码: {response.status_code}"
        
        data = response.json()
        
        # 验证数据结构
        assert 'bids' in data, "响应中缺少bids字段"
        assert 'asks' in data, "响应中缺少asks字段"
        assert 'lastUpdateId' in data, "响应中缺少lastUpdateId字段"
        
        # 验证数据质量
        assert len(data['bids']) > 0, "bids数据为空"
        assert len(data['asks']) > 0, "asks数据为空"
        
        # 验证价格格式
        for bid in data['bids'][:3]:  # 检查前3个
            assert len(bid) == 2, "bid格式错误"
            assert float(bid[0]) > 0, "bid价格无效"
            assert float(bid[1]) > 0, "bid数量无效"
        
        for ask in data['asks'][:3]:  # 检查前3个
            assert len(ask) == 2, "ask格式错误"
            assert float(ask[0]) > 0, "ask价格无效"
            assert float(ask[1]) > 0, "ask数量无效"
        
        # 验证价格逻辑
        best_bid = float(data['bids'][0][0])
        best_ask = float(data['asks'][0][0])
        assert best_bid < best_ask, f"最佳买价({best_bid})应小于最佳卖价({best_ask})"
        
        logger.info(f"Binance订单簿测试通过: {config['test_symbol']}, 买价={best_bid}, 卖价={best_ask}")
    
    @rate_limited_request('okx', 'orderbook')
    def test_okx_orderbook_api(self):
        """测试OKX订单簿API"""
        config = EXCHANGES_CONFIG['okx']
        url = f"{config['rest_base']}{config['orderbook_endpoint']}"
        
        params = {
            'instId': config['test_symbol'],
            'sz': 5
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        # 验证响应
        assert response.status_code == 200, f"OKX API返回错误状态码: {response.status_code}"
        
        data = response.json()
        
        # 验证OKX响应结构
        assert 'code' in data, "响应中缺少code字段"
        assert data['code'] == '0', f"OKX API返回错误代码: {data.get('code')}"
        assert 'data' in data, "响应中缺少data字段"
        
        orderbook_data = data['data'][0]
        
        # 验证数据结构
        assert 'bids' in orderbook_data, "响应中缺少bids字段"
        assert 'asks' in orderbook_data, "响应中缺少asks字段"
        assert 'ts' in orderbook_data, "响应中缺少ts字段"
        
        # 验证数据质量
        assert len(orderbook_data['bids']) > 0, "bids数据为空"
        assert len(orderbook_data['asks']) > 0, "asks数据为空"
        
        # 验证价格格式
        for bid in orderbook_data['bids'][:3]:
            assert len(bid) == 4, "OKX bid格式错误"  # [price, size, liquidated_orders, order_count]
            assert float(bid[0]) > 0, "bid价格无效"
            assert float(bid[1]) > 0, "bid数量无效"
        
        for ask in orderbook_data['asks'][:3]:
            assert len(ask) == 4, "OKX ask格式错误"
            assert float(ask[0]) > 0, "ask价格无效"
            assert float(ask[1]) > 0, "ask数量无效"
        
        # 验证价格逻辑
        best_bid = float(orderbook_data['bids'][0][0])
        best_ask = float(orderbook_data['asks'][0][0])
        assert best_bid < best_ask, f"最佳买价({best_bid})应小于最佳卖价({best_ask})"
        
        logger.info(f"OKX订单簿测试通过: {config['test_symbol']}, 买价={best_bid}, 卖价={best_ask}")
    

        
        # 验证数据有效性
        assert data['symbol'] == config['test_symbol'], "返回的交易对不匹配"
        assert float(data['lastPrice']) > 0, "最新价格无效"
        assert float(data['volume']) >= 0, "成交量无效"
        assert int(data['count']) >= 0, "成交笔数无效"
        
        logger.info(f"Binance行情测试通过: {data['symbol']}, 价格={data['lastPrice']}, 成交量={data['volume']}")
    
    @pytest.mark.asyncio
    @rate_limited_request('binance', 'websocket')
    async def test_binance_websocket_connection(self):
        """测试Binance WebSocket连接"""
        config = EXCHANGES_CONFIG['binance']
        ws_url = f"{config['ws_base']}{config['ws_orderbook_stream']}"
        
        try:
            # 连接WebSocket
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as websocket:
                logger.info(f"成功连接到Binance WebSocket: {ws_url}")
                
                # 等待接收数据
                message = await asyncio.wait_for(websocket.recv(), timeout=10)
                data = json.loads(message)
                
                # 验证数据结构
                assert 'bids' in data, "WebSocket数据中缺少bids字段"
                assert 'asks' in data, "WebSocket数据中缺少asks字段"
                assert 'lastUpdateId' in data, "WebSocket数据中缺少lastUpdateId字段"
                
                # 验证数据质量
                assert len(data['bids']) > 0, "WebSocket bids数据为空"
                assert len(data['asks']) > 0, "WebSocket asks数据为空"
                
                logger.info(f"Binance WebSocket数据验证通过: 收到{len(data['bids'])}个买单, {len(data['asks'])}个卖单")
                
        except asyncio.TimeoutError:
            pytest.fail("Binance WebSocket连接超时")
        except Exception as e:
            pytest.fail(f"Binance WebSocket测试失败: {e}")
    
    def test_data_freshness_and_consistency(self):
        """测试数据新鲜度和一致性"""
        # 获取多个交易所的同一交易对数据
        binance_data = self._get_binance_price()
        time.sleep(1)  # 避免频率限制
        okx_data = self._get_okx_price()
        
        # 验证价格合理性（不同交易所价格差异应在合理范围内）
        binance_price = float(binance_data['lastPrice'])
        okx_price = float(okx_data['data'][0]['last'])
        
        price_diff_percent = abs(binance_price - okx_price) / binance_price * 100
        
        # 价格差异不应超过5%（正常市场条件下）
        assert price_diff_percent < 5.0, f"交易所间价格差异过大: Binance={binance_price}, OKX={okx_price}, 差异={price_diff_percent:.2f}%"
        
        logger.info(f"价格一致性验证通过: Binance={binance_price}, OKX={okx_price}, 差异={price_diff_percent:.2f}%")
    
    @rate_limited_request('binance', 'ticker')
    def _get_binance_price(self) -> Dict[str, Any]:
        """获取Binance价格"""
        config = EXCHANGES_CONFIG['binance']
        url = f"{config['rest_base']}{config['ticker_endpoint']}"
        params = {'symbol': config['test_symbol']}
        
        response = requests.get(url, params=params, timeout=10)
        assert response.status_code == 200
        return response.json()
    
    @rate_limited_request('okx', 'ticker')
    def _get_okx_price(self) -> Dict[str, Any]:
        """获取OKX价格"""
        config = EXCHANGES_CONFIG['okx']
        url = f"{config['rest_base']}{config['ticker_endpoint']}"
        params = {'instId': config['test_symbol']}
        
        response = requests.get(url, params=params, timeout=10)
        assert response.status_code == 200
        return response.json()
    
    def test_api_rate_limiting_effectiveness(self):
        """测试API频率限制的有效性"""
        exchange = 'binance'
        endpoint = 'test_rate_limit'
        
        # 记录开始时间
        start_time = time.time()
        
        # 尝试快速发起多个请求
        request_times = []
        for i in range(5):
            wait_time = self.rate_limiter.wait_if_needed(exchange, endpoint)
            request_times.append(time.time())
            self.rate_limiter.record_request(exchange, endpoint)
        
        # 验证请求间隔
        for i in range(1, len(request_times)):
            interval = request_times[i] - request_times[i-1]
            # 应该有适当的间隔
            assert interval >= 0.5, f"请求间隔过短: {interval:.2f}秒"
        
        total_time = time.time() - start_time
        logger.info(f"频率限制测试完成: 5个请求耗时{total_time:.2f}秒")
        
        # 验证统计信息
        stats = get_api_stats(exchange, endpoint)
        assert stats['total_requests'] == 5, "请求计数不正确"
        assert stats['requests_last_minute'] == 5, "分钟内请求计数不正确"
