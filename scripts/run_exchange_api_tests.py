#!/usr/bin/env python3
"""
交易所API TDD测试运行器
专门测试真实的Binance和OKX API集成

基于最新的API文档进行测试：
- Binance Testnet API v3
- OKX API v5
- 最新的变更和修复
"""

import asyncio
import aiohttp
import time
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase

class ExchangeAPITester:
    """交易所API测试器"""
    
    def __init__(self):
        self.test_base = RealTestBase()
        self.config = self.test_base.config
        self.results = {}
    
    async def test_binance_api_v3_compatibility(self):
        """
        TDD测试：Binance API v3兼容性
        基于2023-12-04的最新更新进行测试
        """
        print("🧪 测试Binance API v3兼容性...")
        
        binance_config = self.config['exchanges']['binance']
        base_url = binance_config['base_url']
        
        test_results = {}
        
        async with aiohttp.ClientSession() as session:
            try:
                # 1. 测试服务器时间 (基础API)
                print("   🔍 测试服务器时间API...")
                async with session.get(f"{base_url}/api/v3/time", timeout=10) as response:
                    assert response.status == 200, f"时间API失败: {response.status}"
                    time_data = await response.json()
                    assert 'serverTime' in time_data, "时间响应缺少serverTime字段"
                    
                    # 验证时间合理性
                    server_time = time_data['serverTime']
                    local_time = int(time.time() * 1000)
                    time_diff = abs(server_time - local_time)
                    assert time_diff < 5 * 60 * 1000, f"服务器时间差异过大: {time_diff}ms"
                    
                    test_results['server_time'] = True
                    print(f"   ✅ 服务器时间: {server_time}")
                
                # 2. 测试交易规则信息 (exchangeInfo)
                print("   🔍 测试交易规则API...")
                async with session.get(f"{base_url}/api/v3/exchangeInfo", timeout=15) as response:
                    assert response.status == 200, f"交易规则API失败: {response.status}"
                    exchange_info = await response.json()
                    
                    # 验证必要字段
                    required_fields = ['timezone', 'serverTime', 'symbols', 'exchangeFilters']
                    for field in required_fields:
                        assert field in exchange_info, f"交易规则响应缺少{field}字段"
                    
                    symbols = exchange_info['symbols']
                    assert len(symbols) > 0, "未获取到交易对信息"
                    
                    # 验证新的权限格式 (2024-04-02更新)
                    btc_symbol = next((s for s in symbols if s['symbol'] == 'BTCUSDT'), None)
                    if btc_symbol:
                        # 检查新的permissionSets字段
                        if 'permissionSets' in btc_symbol:
                            print(f"   ✅ 发现新的permissionSets格式: {btc_symbol['permissionSets']}")
                        
                        # 检查OTO支持
                        if 'otoAllowed' in btc_symbol:
                            print(f"   ✅ OTO支持状态: {btc_symbol['otoAllowed']}")
                    
                    test_results['exchange_info'] = True
                    print(f"   ✅ 获取到{len(symbols)}个交易对")
                
                # 3. 测试新增的账户佣金API (2023-12-04)
                print("   🔍 测试账户佣金API...")
                try:
                    async with session.get(f"{base_url}/api/v3/account/commission", timeout=10) as response:
                        if response.status == 200:
                            commission_data = await response.json()
                            print(f"   ✅ 账户佣金API: {commission_data}")
                            test_results['account_commission'] = True
                        elif response.status == 401:
                            print("   ⚠️ 账户佣金API需要认证，跳过")
                            test_results['account_commission'] = 'skipped'
                        else:
                            print(f"   ❌ 账户佣金API失败: {response.status}")
                            test_results['account_commission'] = False
                except Exception as e:
                    print(f"   ⚠️ 账户佣金API测试异常: {e}")
                    test_results['account_commission'] = 'error'
                
                # 4. 测试新增的交易日行情API (2023-12-04)
                print("   🔍 测试交易日行情API...")
                try:
                    async with session.get(
                        f"{base_url}/api/v3/ticker/tradingDay",
                        params={"symbol": "BTCUSDT"},
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            trading_day_data = await response.json()
                            print(f"   ✅ 交易日行情: {trading_day_data}")
                            test_results['trading_day'] = True
                        else:
                            print(f"   ❌ 交易日行情API失败: {response.status}")
                            test_results['trading_day'] = False
                except Exception as e:
                    print(f"   ⚠️ 交易日行情API测试异常: {e}")
                    test_results['trading_day'] = 'error'
                
                # 5. 测试平均价格API的新字段 (2023-12-04)
                print("   🔍 测试平均价格API新字段...")
                async with session.get(
                    f"{base_url}/api/v3/avgPrice",
                    params={"symbol": "BTCUSDT"},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"平均价格API失败: {response.status}"
                    avg_price_data = await response.json()
                    
                    # 验证基本字段
                    assert 'price' in avg_price_data, "平均价格缺少price字段"
                    
                    # 验证新增的closeTime字段
                    if 'closeTime' in avg_price_data:
                        print(f"   ✅ 发现新的closeTime字段: {avg_price_data['closeTime']}")
                        test_results['avg_price_close_time'] = True
                    else:
                        print("   ⚠️ 未发现closeTime字段（可能还未推出）")
                        test_results['avg_price_close_time'] = False
                    
                    test_results['avg_price'] = True
                    print(f"   ✅ 平均价格: {avg_price_data['price']}")
                
                # 6. 测试深度数据
                print("   🔍 测试深度数据质量...")
                async with session.get(
                    f"{base_url}/api/v3/depth",
                    params={"symbol": "BTCUSDT", "limit": 20},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"深度数据API失败: {response.status}"
                    depth_data = await response.json()
                    
                    bids = depth_data['bids']
                    asks = depth_data['asks']
                    
                    assert len(bids) > 0 and len(asks) > 0, "深度数据为空"
                    
                    # 验证价格和数量格式
                    best_bid_price = float(bids[0][0])
                    best_bid_qty = float(bids[0][1])
                    best_ask_price = float(asks[0][0])
                    best_ask_qty = float(asks[0][1])
                    
                    assert best_bid_price > 0 and best_bid_qty > 0, "买单数据无效"
                    assert best_ask_price > best_bid_price, "卖价应大于买价"
                    assert best_ask_qty > 0, "卖单数量无效"
                    
                    # 计算价差
                    spread = (best_ask_price - best_bid_price) / best_bid_price * 100
                    assert spread < 1.0, f"价差过大: {spread:.4f}%"
                    
                    test_results['depth_data'] = True
                    print(f"   ✅ 深度数据质量良好，价差: {spread:.4f}%")
                
                # 7. 测试测试下单API
                print("   🔍 测试测试下单API...")
                test_order_payload = {
                    "symbol": "BTCUSDT",
                    "side": "BUY", 
                    "type": "LIMIT",
                    "timeInForce": "GTC",
                    "quantity": "0.001",
                    "price": "20000",  # 远低于市价的测试价格
                    "computeCommissionRates": True  # 新增参数
                }
                
                try:
                    async with session.post(
                        f"{base_url}/api/v3/order/test",
                        data=test_order_payload,
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            test_order_result = await response.json()
                            print(f"   ✅ 测试下单成功: {test_order_result}")
                            
                            # 检查新的佣金计算字段
                            if 'standardCommissionForOrder' in test_order_result:
                                print("   ✅ 发现新的佣金计算功能")
                            
                            test_results['test_order'] = True
                        elif response.status == 401:
                            print("   ⚠️ 测试下单需要认证，跳过")
                            test_results['test_order'] = 'skipped'
                        else:
                            print(f"   ❌ 测试下单失败: {response.status}")
                            test_results['test_order'] = False
                except Exception as e:
                    print(f"   ⚠️ 测试下单异常: {e}")
                    test_results['test_order'] = 'error'
                
                self.results['binance_api_v3'] = test_results
                return True
                
            except AssertionError as e:
                print(f"   ❌ Binance API测试失败: {e}")
                self.results['binance_api_v3'] = {'error': str(e)}
                return False
            except Exception as e:
                print(f"   ❌ Binance API测试异常: {e}")
                self.results['binance_api_v3'] = {'error': str(e)}
                return False
    
    async def test_okx_api_v5_compatibility(self):
        """
        TDD测试：OKX API v5兼容性
        """
        print("🧪 测试OKX API v5兼容性...")
        
        okx_config = self.config['exchanges'].get('okx', {})
        if not okx_config:
            print("   ⚠️ OKX配置未找到，跳过测试")
            self.results['okx_api_v5'] = {'skipped': True}
            return True
        
        base_url = okx_config.get('base_url', 'https://www.okx.com')
        test_results = {}
        
        async with aiohttp.ClientSession() as session:
            try:
                # 1. 测试系统时间
                print("   🔍 测试OKX系统时间...")
                async with session.get(f"{base_url}/api/v5/public/time", timeout=10) as response:
                    assert response.status == 200, f"OKX时间API失败: {response.status}"
                    time_data = await response.json()
                    
                    assert time_data.get('code') == '0', f"OKX API响应错误: {time_data}"
                    assert 'data' in time_data, "时间响应缺少data字段"
                    
                    server_time = int(time_data['data'][0]['ts'])
                    local_time = int(time.time() * 1000)
                    time_diff = abs(server_time - local_time)
                    assert time_diff < 5 * 60 * 1000, f"OKX服务器时间差异过大: {time_diff}ms"
                    
                    test_results['server_time'] = True
                    print(f"   ✅ OKX服务器时间: {server_time}")
                
                # 2. 测试产品信息
                print("   🔍 测试OKX产品信息...")
                async with session.get(
                    f"{base_url}/api/v5/public/instruments",
                    params={"instType": "SPOT"},
                    timeout=15
                ) as response:
                    assert response.status == 200, f"OKX产品信息API失败: {response.status}"
                    instruments_data = await response.json()
                    
                    assert instruments_data.get('code') == '0', f"OKX产品信息API错误: {instruments_data}"
                    instruments = instruments_data['data']
                    assert len(instruments) > 0, "未获取到OKX产品信息"
                    
                    # 查找BTC-USDT
                    btc_instrument = next((inst for inst in instruments if inst['instId'] == 'BTC-USDT'), None)
                    assert btc_instrument is not None, "未找到BTC-USDT产品"
                    assert btc_instrument['state'] == 'live', "BTC-USDT不在交易状态"
                    
                    test_results['instruments'] = True
                    print(f"   ✅ 获取到{len(instruments)}个OKX现货产品")
                
                # 3. 测试行情数据
                print("   🔍 测试OKX行情数据...")
                async with session.get(
                    f"{base_url}/api/v5/market/ticker",
                    params={"instId": "BTC-USDT"},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"OKX行情API失败: {response.status}"
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
                    
                    test_results['ticker'] = True
                    print(f"   ✅ OKX行情: 最新价{last_price}, 价差{spread:.4f}%")
                
                # 4. 测试深度数据
                print("   🔍 测试OKX深度数据...")
                async with session.get(
                    f"{base_url}/api/v5/market/books",
                    params={"instId": "BTC-USDT", "sz": "20"},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"OKX深度API失败: {response.status}"
                    depth_data = await response.json()
                    
                    assert depth_data.get('code') == '0', f"OKX深度API错误: {depth_data}"
                    depth = depth_data['data'][0]
                    
                    bids = depth['bids']
                    asks = depth['asks']
                    
                    assert len(bids) > 0 and len(asks) > 0, "OKX深度数据为空"
                    
                    best_bid_price = float(bids[0][0])
                    best_ask_price = float(asks[0][0])
                    
                    assert best_bid_price > 0, "买价无效"
                    assert best_ask_price > best_bid_price, "卖价应大于买价"
                    
                    test_results['depth'] = True
                    print(f"   ✅ OKX深度数据质量良好")
                
                self.results['okx_api_v5'] = test_results
                return True
                
            except AssertionError as e:
                print(f"   ❌ OKX API测试失败: {e}")
                self.results['okx_api_v5'] = {'error': str(e)}
                return False
            except Exception as e:
                print(f"   ❌ OKX API测试异常: {e}")
                self.results['okx_api_v5'] = {'error': str(e)}
                return False
    
    async def test_websocket_connections(self):
        """
        TDD测试：WebSocket连接测试
        """
        print("🧪 测试WebSocket连接...")
        
        import websockets
        
        # 测试Binance WebSocket
        print("   🔍 测试Binance WebSocket...")
        binance_ws_url = self.config['exchanges']['binance']['ws_url']
        
        try:
            async with websockets.connect(f"{binance_ws_url}/btcusdt@ticker", close_timeout=5) as websocket:
                print("   ✅ Binance WebSocket连接成功")
                
                # 尝试接收一条消息
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                    data = json.loads(message)
                    
                    # 验证ticker数据格式
                    if 's' in data and data['s'] == 'BTCUSDT':
                        print(f"   ✅ 接收到Binance ticker数据: {data['c']}")
                        self.results['binance_websocket'] = True
                    else:
                        print(f"   ⚠️ 收到非预期数据: {data}")
                        self.results['binance_websocket'] = 'unexpected_data'
                        
                except asyncio.TimeoutError:
                    print("   ⚠️ Binance WebSocket数据接收超时")
                    self.results['binance_websocket'] = 'timeout'
                
        except Exception as e:
            print(f"   ❌ Binance WebSocket连接失败: {e}")
            self.results['binance_websocket'] = False
        
        # 测试OKX WebSocket
        print("   🔍 测试OKX WebSocket...")
        okx_config = self.config['exchanges'].get('okx', {})
        
        if okx_config:
            okx_ws_url = okx_config.get('ws_url', 'wss://ws.okx.com:8443/ws/v5/public')
            
            try:
                async with websockets.connect(okx_ws_url, close_timeout=5) as websocket:
                    print("   ✅ OKX WebSocket连接成功")
                    
                    # 发送订阅消息
                    subscribe_msg = {
                        "op": "subscribe",
                        "args": [{"channel": "tickers", "instId": "BTC-USDT"}]
                    }
                    
                    await websocket.send(json.dumps(subscribe_msg))
                    
                    # 接收订阅确认和数据
                    for i in range(3):
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=10)
                            data = json.loads(message)
                            
                            if 'event' in data and data['event'] == 'subscribe':
                                print("   ✅ OKX订阅确认")
                            elif 'data' in data:
                                print(f"   ✅ 接收到OKX数据")
                                self.results['okx_websocket'] = True
                                break
                                
                        except asyncio.TimeoutError:
                            if i == 2:  # 最后一次尝试
                                print("   ⚠️ OKX WebSocket数据接收超时")
                                self.results['okx_websocket'] = 'timeout'
                            continue
                        except json.JSONDecodeError:
                            continue
                            
            except Exception as e:
                print(f"   ❌ OKX WebSocket连接失败: {e}")
                self.results['okx_websocket'] = False
        else:
            print("   ⚠️ OKX配置缺失，跳过WebSocket测试")
            self.results['okx_websocket'] = 'skipped'
    
    def print_summary(self):
        """打印测试总结"""
        print("\n📊 交易所API TDD测试总结")
        print("="*60)
        
        total_tests = 0
        passed_tests = 0
        
        for exchange, results in self.results.items():
            print(f"\n🏪 {exchange.upper()}")
            print("-" * 30)
            
            if isinstance(results, dict):
                for test_name, result in results.items():
                    total_tests += 1
                    
                    if result is True:
                        status = "✅ PASS"
                        passed_tests += 1
                    elif result is False:
                        status = "❌ FAIL"
                    elif result == 'skipped':
                        status = "⚠️ SKIP"
                        passed_tests += 0.5  # 部分计分
                    elif result == 'timeout':
                        status = "⏰ TIMEOUT"
                    elif result == 'error':
                        status = "❌ ERROR"
                    else:
                        status = f"ℹ️ {result}"
                    
                    print(f"   {status} {test_name}")
            else:
                total_tests += 1
                if results:
                    status = "✅ PASS"
                    passed_tests += 1
                else:
                    status = "❌ FAIL"
                print(f"   {status} {exchange}")
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"\n📈 总体结果: {passed_tests:.1f}/{total_tests} ({success_rate:.1f}%)")
        
        if success_rate >= 80:
            print("🎉 交易所API集成测试通过！")
            return True
        else:
            print("❌ 交易所API集成测试需要改进")
            return False

async def main():
    """主测试函数"""
    print("🚀 开始交易所API TDD测试")
    print("基于最新API文档: Binance API v3, OKX API v5")
    print("="*60)
    
    tester = ExchangeAPITester()
    
    try:
        # 运行各项测试
        await tester.test_binance_api_v3_compatibility()
        await tester.test_okx_api_v5_compatibility() 
        await tester.test_websocket_connections()
        
        # 打印总结
        success = tester.print_summary()
        
        return success
        
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        return False
    except Exception as e:
        print(f"\n❌ 测试运行出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)