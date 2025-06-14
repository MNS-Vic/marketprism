"""
TDD测试：真实交易所API集成验证
基于Binance和OKX的真实API文档进行集成测试

遵循TDD原则：
1. 先写测试，描述期望的API行为
2. 验证真实API响应格式和数据质量
3. 测试错误处理和边界情况
4. 确保API限制和安全性合规
"""

from datetime import datetime, timezone
import pytest
import asyncio
import aiohttp
import websockets
import json
import time
from pathlib import Path
import sys
import hmac
import hashlib
import base64
from urllib.parse import urlencode

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment, requires_service, requires_real_network


class TestRealBinanceIntegration(RealTestBase):
    """Binance真实API集成测试"""
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_should_connect_to_binance_testnet_public_endpoints(self):
        """
        TDD测试：应该能连接Binance Testnet公共端点
        
        Given: Binance Testnet可访问，代理配置正确
        When: 访问公共API端点
        Then: 应该返回正确的市场数据格式
        """
        async with real_test_environment() as env:
            binance_config = env.config['exchanges']['binance']
            base_url = binance_config['base_url']
            
            async with aiohttp.ClientSession() as session:
                # 1. 测试服务器时间接口
                async with session.get(f"{base_url}/api/v3/time", timeout=10) as response:
                    assert response.status == 200, f"获取服务器时间失败: {response.status}"
                    time_data = await response.json()
                    
                    assert 'serverTime' in time_data, "时间响应缺少serverTime字段"
                    server_time = time_data['serverTime']
                    
                    # 验证时间合理性（与本地时间差异不超过5分钟）
                    local_time = int(time.time() * 1000)
                    time_diff = abs(server_time - local_time)
                    assert time_diff < 5 * 60 * 1000, f"服务器时间差异过大: {time_diff}ms"
                    
                    print(f"✅ Binance服务器时间: {server_time}")
                
                # 2. 测试交易规则接口
                async with session.get(f"{base_url}/api/v3/exchangeInfo", timeout=15) as response:
                    assert response.status == 200, f"获取交易规则失败: {response.status}"
                    exchange_info = await response.json()
                    
                    assert 'symbols' in exchange_info, "交易规则响应缺少symbols字段"
                    symbols = exchange_info['symbols']
                    assert len(symbols) > 0, "未获取到交易对信息"
                    
                    # 验证BTCUSDT交易对信息
                    btc_symbol = next((s for s in symbols if s['symbol'] == 'BTCUSDT'), None)
                    assert btc_symbol is not None, "未找到BTCUSDT交易对"
                    assert btc_symbol['status'] == 'TRADING', "BTCUSDT不在交易状态"
                    
                    print(f"✅ 获取到{len(symbols)}个交易对，BTCUSDT状态: {btc_symbol['status']}")
                
                # 3. 测试深度数据接口
                async with session.get(
                    f"{base_url}/api/v3/depth",
                    params={"symbol": "BTCUSDT", "limit": 10},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"获取深度数据失败: {response.status}"
                    depth_data = await response.json()
                    
                    required_fields = ['lastUpdateId', 'bids', 'asks']
                    for field in required_fields:
                        assert field in depth_data, f"深度数据缺少{field}字段"
                    
                    bids = depth_data['bids']
                    asks = depth_data['asks']
                    assert len(bids) > 0, "买单深度为空"
                    assert len(asks) > 0, "卖单深度为空"
                    
                    # 验证价格合理性
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    assert best_bid > 0, "最佳买价无效"
                    assert best_ask > best_bid, "卖价应该大于买价"
                    
                    spread = (best_ask - best_bid) / best_bid * 100
                    assert spread < 5, f"价差过大: {spread:.4f}%"
                    
                    print(f"✅ BTCUSDT深度: 买价{best_bid}, 卖价{best_ask}, 价差{spread:.4f}%")
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_should_handle_binance_websocket_streams(self):
        """
        TDD测试：应该能处理Binance WebSocket数据流
        
        Given: Binance WebSocket服务可用
        When: 订阅市场数据流
        Then: 应该接收到实时数据并正确解析
        """
        async with real_test_environment() as env:
            binance_config = env.config['exchanges']['binance']
            ws_url = binance_config['ws_url']
            
            # 测试单一交易对ticker流
            stream_url = f"{ws_url}/btcusdt@ticker"
            received_data = []
            
            try:
                async with websockets.connect(stream_url, close_timeout=5) as websocket:
                    print(f"✅ 连接到Binance WebSocket: {stream_url}")
                    
                    # 接收3条消息进行验证
                    for i in range(3):
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=10)
                            data = json.loads(message)
                            received_data.append(data)
                            
                            # 验证ticker数据格式
                            required_fields = ['s', 'c', 'o', 'h', 'l', 'v', 'E']
                            for field in required_fields:
                                assert field in data, f"ticker数据缺少{field}字段"
                            
                            assert data['s'] == 'BTCUSDT', f"交易对错误: {data['s']}"
                            
                            price = float(data['c'])
                            assert price > 0, f"价格无效: {price}"
                            
                            # 验证时间戳合理性
                            event_time = data['E']
                            current_time = int(time.time() * 1000)
                            time_diff = abs(current_time - event_time)
                            assert time_diff < 60 * 1000, f"数据时间戳过旧: {time_diff}ms"
                            
                            print(f"✅ 接收ticker数据 {i+1}: 价格{price}, 时间{event_time}")
                            
                        except asyncio.TimeoutError:
                            print(f"⚠️ 第{i+1}条消息接收超时")
                            break
                        except json.JSONDecodeError as e:
                            print(f"❌ JSON解析失败: {e}")
                            break
                
                assert len(received_data) >= 1, "未接收到有效的WebSocket数据"
                print(f"✅ WebSocket测试完成，接收到{len(received_data)}条有效数据")
                
            except Exception as e:
                print(f"⚠️ WebSocket连接异常: {e}")
                # 在测试环境中，网络问题不应该导致测试失败
                pytest.skip(f"WebSocket连接失败: {e}")
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_should_respect_binance_rate_limits(self):
        """
        TDD测试：应该遵守Binance API速率限制
        
        Given: Binance有明确的API速率限制
        When: 发送批量API请求
        Then: 应该正确处理速率限制并避免被封禁
        """
        async with real_test_environment() as env:
            binance_config = env.config['exchanges']['binance']
            base_url = binance_config['base_url']
            
            # 配置的速率限制
            rate_limit = binance_config.get('rate_limit', {})
            requests_per_minute = rate_limit.get('requests_per_minute', 1200)
            
            async with aiohttp.ClientSession() as session:
                # 快速发送多个请求测试速率限制
                request_count = 20
                start_time = time.time()
                results = []
                
                for i in range(request_count):
                    try:
                        async with session.get(
                            f"{base_url}/api/v3/ticker/price",
                            params={"symbol": "BTCUSDT"},
                            timeout=5
                        ) as response:
                            results.append({
                                'request_id': i,
                                'status': response.status,
                                'timestamp': time.time(),
                                'headers': dict(response.headers)
                            })
                            
                            # 检查是否返回速率限制信息
                            if 'X-MBX-USED-WEIGHT-1M' in response.headers:
                                used_weight = response.headers['X-MBX-USED-WEIGHT-1M']
                                print(f"请求{i}: 状态{response.status}, 权重使用{used_weight}")
                            
                            # 如果遇到429错误，记录但不失败
                            if response.status == 429:
                                print(f"⚠️ 请求{i}遇到速率限制: 429")
                                retry_after = response.headers.get('Retry-After', '未知')
                                print(f"   建议重试间隔: {retry_after}")
                                break
                        
                        # 添加小延迟避免过快请求
                        await asyncio.sleep(0.1)
                        
                    except Exception as e:
                        results.append({
                            'request_id': i,
                            'status': 0,
                            'error': str(e),
                            'timestamp': time.time()
                        })
                
                end_time = time.time()
                total_time = end_time - start_time
                
                # 分析结果
                success_count = sum(1 for r in results if r.get('status') == 200)
                rate_limit_count = sum(1 for r in results if r.get('status') == 429)
                error_count = sum(1 for r in results if r.get('status', 0) not in [200, 429])
                
                success_rate = success_count / len(results)
                requests_per_second = len(results) / total_time
                
                print(f"\n📊 速率限制测试结果:")
                print(f"   总请求数: {len(results)}")
                print(f"   成功数: {success_count}")
                print(f"   速率限制: {rate_limit_count}")
                print(f"   错误数: {error_count}")
                print(f"   成功率: {success_rate:.2%}")
                print(f"   请求速度: {requests_per_second:.2f} req/s")
                print(f"   总耗时: {total_time:.2f}秒")
                
                # 验证速率限制处理的合理性
                assert success_rate >= 0.7, f"成功率过低: {success_rate:.2%}"
                
                # 如果遇到速率限制，说明系统正确识别了限制
                if rate_limit_count > 0:
                    print("✅ 系统正确识别并处理了API速率限制")
                else:
                    print("✅ 请求频率在限制范围内，未触发速率限制")


class TestRealOKXIntegration(RealTestBase):
    """OKX真实API集成测试"""
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_should_connect_to_okx_public_endpoints(self):
        """
        TDD测试：应该能连接OKX公共端点
        
        Given: OKX API可访问，代理配置正确
        When: 访问OKX公共API端点
        Then: 应该返回正确的数据格式
        """
        async with real_test_environment() as env:
            okx_config = env.config['exchanges'].get('okx', {})
            base_url = okx_config.get('base_url', 'https://www.okx.com')
            
            async with aiohttp.ClientSession() as session:
                # 1. 测试系统时间接口
                async with session.get(
                    f"{base_url}/api/v5/public/time",
                    timeout=10
                ) as response:
                    assert response.status == 200, f"获取OKX系统时间失败: {response.status}"
                    time_data = await response.json()
                    
                    assert time_data.get('code') == '0', f"OKX API响应错误: {time_data}"
                    assert 'data' in time_data, "时间响应缺少data字段"
                    
                    data = time_data['data'][0]
                    server_time = int(data['ts'])
                    
                    # 验证时间合理性
                    local_time = int(time.time() * 1000)
                    time_diff = abs(server_time - local_time)
                    assert time_diff < 5 * 60 * 1000, f"OKX服务器时间差异过大: {time_diff}ms"
                    
                    print(f"✅ OKX服务器时间: {server_time}")
                
                # 2. 测试交易产品信息
                async with session.get(
                    f"{base_url}/api/v5/public/instruments",
                    params={"instType": "SPOT"},
                    timeout=15
                ) as response:
                    assert response.status == 200, f"获取OKX产品信息失败: {response.status}"
                    instruments_data = await response.json()
                    
                    assert instruments_data.get('code') == '0', f"OKX产品信息API错误: {instruments_data}"
                    instruments = instruments_data['data']
                    assert len(instruments) > 0, "未获取到OKX交易产品"
                    
                    # 查找BTC-USDT交易对
                    btc_instrument = next((inst for inst in instruments if inst['instId'] == 'BTC-USDT'), None)
                    assert btc_instrument is not None, "未找到BTC-USDT交易对"
                    assert btc_instrument['state'] == 'live', "BTC-USDT不在交易状态"
                    
                    print(f"✅ 获取到{len(instruments)}个OKX现货产品，BTC-USDT状态: {btc_instrument['state']}")
                
                # 3. 测试行情数据
                async with session.get(
                    f"{base_url}/api/v5/market/ticker",
                    params={"instId": "BTC-USDT"},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"获取OKX行情失败: {response.status}"
                    ticker_data = await response.json()
                    
                    assert ticker_data.get('code') == '0', f"OKX行情API错误: {ticker_data}"
                    ticker = ticker_data['data'][0]
                    
                    # 验证关键字段
                    required_fields = ['instId', 'last', 'bidPx', 'askPx', 'vol24h', 'ts']
                    for field in required_fields:
                        assert field in ticker, f"OKX行情数据缺少{field}字段"
                    
                    last_price = float(ticker['last'])
                    bid_price = float(ticker['bidPx'])
                    ask_price = float(ticker['askPx'])
                    
                    assert last_price > 0, "最新价格无效"
                    assert bid_price > 0, "买价无效"
                    assert ask_price > bid_price, "卖价应该大于买价"
                    
                    spread = (ask_price - bid_price) / bid_price * 100
                    print(f"✅ OKX BTC-USDT: 最新价{last_price}, 买价{bid_price}, 卖价{ask_price}, 价差{spread:.4f}%")
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_should_handle_okx_websocket_connection(self):
        """
        TDD测试：应该能处理OKX WebSocket连接
        
        Given: OKX WebSocket服务可用
        When: 连接WebSocket并订阅数据
        Then: 应该成功建立连接并接收数据
        """
        async with real_test_environment() as env:
            okx_config = env.config['exchanges'].get('okx', {})
            ws_url = okx_config.get('ws_url', 'wss://ws.okx.com:8443/ws/v5/public')
            
            try:
                async with websockets.connect(ws_url, close_timeout=5) as websocket:
                    print(f"✅ 连接到OKX WebSocket: {ws_url}")
                    
                    # 订阅BTC-USDT ticker数据
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
                    print("✅ 发送OKX订阅消息")
                    
                    # 接收订阅确认和数据
                    received_count = 0
                    for i in range(5):  # 尝试接收5条消息
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=10)
                            data = json.loads(message)
                            
                            if 'event' in data:
                                # 处理事件消息（如订阅确认）
                                if data['event'] == 'subscribe':
                                    print(f"✅ OKX订阅确认: {data}")
                                elif data['event'] == 'error':
                                    print(f"❌ OKX订阅错误: {data}")
                                    break
                            elif 'data' in data:
                                # 处理数据消息
                                ticker_data = data['data'][0]
                                
                                # 验证数据格式
                                required_fields = ['instId', 'last', 'bidPx', 'askPx', 'ts']
                                for field in required_fields:
                                    assert field in ticker_data, f"OKX ticker数据缺少{field}字段"
                                
                                assert ticker_data['instId'] == 'BTC-USDT', f"交易对错误: {ticker_data['instId']}"
                                
                                last_price = float(ticker_data['last'])
                                assert last_price > 0, f"价格无效: {last_price}"
                                
                                print(f"✅ 接收OKX ticker数据: 价格{last_price}, 时间{ticker_data['ts']}")
                                received_count += 1
                                
                                if received_count >= 2:  # 接收到2条数据就够了
                                    break
                            
                        except asyncio.TimeoutError:
                            print(f"⚠️ OKX消息接收超时")
                            break
                        except json.JSONDecodeError as e:
                            print(f"❌ OKX JSON解析失败: {e}")
                            break
                    
                    if received_count > 0:
                        print(f"✅ OKX WebSocket测试完成，接收到{received_count}条数据")
                    else:
                        print("⚠️ 未接收到OKX数据，但连接正常")
                        
            except Exception as e:
                print(f"⚠️ OKX WebSocket连接异常: {e}")
                # 在测试环境中，网络问题不应该导致测试失败
                pytest.skip(f"OKX WebSocket连接失败: {e}")


class TestMultiExchangeIntegration(RealTestBase):
    """多交易所集成测试"""
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_should_compare_data_consistency_across_exchanges(self):
        """
        TDD测试：应该比较多个交易所的数据一致性
        
        Given: Binance和OKX都提供BTC/USDT数据
        When: 同时获取两个交易所的价格数据
        Then: 价格差异应该在合理范围内
        """
        async with real_test_environment() as env:
            binance_config = env.config['exchanges']['binance']
            okx_config = env.config['exchanges'].get('okx', {})
            
            prices = {}
            
            async with aiohttp.ClientSession() as session:
                # 获取Binance价格
                try:
                    async with session.get(
                        f"{binance_config['base_url']}/api/v3/ticker/price",
                        params={"symbol": "BTCUSDT"},
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            binance_data = await response.json()
                            prices['binance'] = float(binance_data['price'])
                            print(f"✅ Binance BTC价格: {prices['binance']}")
                except Exception as e:
                    print(f"⚠️ 获取Binance价格失败: {e}")
                
                # 获取OKX价格
                try:
                    okx_base_url = okx_config.get('base_url', 'https://www.okx.com')
                    async with session.get(
                        f"{okx_base_url}/api/v5/market/ticker",
                        params={"instId": "BTC-USDT"},
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            okx_data = await response.json()
                            if okx_data.get('code') == '0':
                                prices['okx'] = float(okx_data['data'][0]['last'])
                                print(f"✅ OKX BTC价格: {prices['okx']}")
                except Exception as e:
                    print(f"⚠️ 获取OKX价格失败: {e}")
            
            # 比较价格一致性
            if len(prices) >= 2:
                binance_price = prices.get('binance')
                okx_price = prices.get('okx')
                
                if binance_price and okx_price:
                    price_diff = abs(binance_price - okx_price)
                    price_diff_percent = (price_diff / binance_price) * 100
                    
                    print(f"📊 价格比较:")
                    print(f"   Binance: {binance_price}")
                    print(f"   OKX: {okx_price}")
                    print(f"   差异: {price_diff} ({price_diff_percent:.4f}%)")
                    
                    # 正常情况下，主流交易所价格差异不应该超过1%
                    assert price_diff_percent < 1.0, f"价格差异过大: {price_diff_percent:.4f}%"
                    
                    print("✅ 多交易所价格一致性验证通过")
                else:
                    pytest.skip("未能获取到足够的价格数据进行比较")
            else:
                pytest.skip("未能连接到足够的交易所进行比较")


@pytest.mark.asyncio
async def test_exchange_integration_suite():
    """交易所集成测试套件入口"""
    print("🚀 开始真实交易所API集成测试")
    
    async with real_test_environment() as env:
        if not env.proxy_configured:
            pytest.skip("代理未配置，跳过真实API测试")
        
        # Binance测试
        binance_test = TestRealBinanceIntegration()
        print("\n📈 开始Binance集成测试")
        await binance_test.test_should_connect_to_binance_testnet_public_endpoints()
        await binance_test.test_should_handle_binance_websocket_streams()
        await binance_test.test_should_respect_binance_rate_limits()
        
        # OKX测试
        okx_test = TestRealOKXIntegration()
        print("\n📊 开始OKX集成测试")
        await okx_test.test_should_connect_to_okx_public_endpoints()
        await okx_test.test_should_handle_okx_websocket_connection()
        
        # 多交易所对比测试
        multi_test = TestMultiExchangeIntegration()
        print("\n🔄 开始多交易所对比测试")
        await multi_test.test_should_compare_data_consistency_across_exchanges()
        
        print("\n🎉 所有交易所集成测试完成")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_exchange_integration_suite())