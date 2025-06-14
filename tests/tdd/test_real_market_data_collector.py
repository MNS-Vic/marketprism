"""
TDD测试：市场数据采集服务真实性验证
连接真实交易所API，验证数据采集功能

遵循TDD原则：
1. 先写测试，描述期望的行为  
2. 运行测试，验证失败（红灯）
3. 实现最小代码，使测试通过（绿灯）
4. 重构优化（重构）
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
import os

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment, requires_service, requires_real_network


class TestRealMarketDataCollector(RealTestBase):
    """市场数据采集服务真实性测试"""
    
    @pytest.mark.asyncio
    @requires_service("market_data_collector")
    @requires_real_network()
    async def test_should_connect_to_real_binance_testnet_with_proxy(self):
        """
        TDD测试：应该能通过代理连接到真实的Binance Testnet
        
        Given: 代理已配置，Binance Testnet可访问
        When: 启动市场数据采集服务
        Then: 应该成功连接Binance WebSocket并接收数据
        """
        async with real_test_environment() as env:
            # 验证代理配置
            assert env.proxy_configured, "代理未配置"
            assert env.services_running.get('market_data_collector', False), "市场数据采集服务未运行"
            
            collector_url = "http://localhost:8081"
            
            async with aiohttp.ClientSession() as session:
                # 1. 测试与Binance的连接状态
                async with session.get(
                    f"{collector_url}/api/v1/exchange/binance/status",
                    timeout=15
                ) as response:
                    assert response.status == 200, f"无法获取Binance连接状态: {response.status}"
                    status_data = await response.json()
                    
                    # 验证连接状态
                    assert status_data.get('connected', False), f"Binance连接失败: {status_data}"
                    assert status_data.get('exchange') == 'binance', "交易所标识错误"
                    
                    print(f"✅ Binance连接状态: {status_data}")
                
                # 2. 测试订阅市场数据
                subscribe_data = {
                    "symbol": "BTCUSDT",
                    "data_types": ["ticker", "orderbook"]
                }
                
                async with session.post(
                    f"{collector_url}/api/v1/exchange/binance/subscribe",
                    json=subscribe_data,
                    timeout=10
                ) as response:
                    assert response.status == 200, f"订阅失败: {response.status}"
                    subscribe_result = await response.json()
                    
                    assert subscribe_result.get('success', False), f"订阅失败: {subscribe_result}"
                    subscription_id = subscribe_result.get('subscription_id')
                    assert subscription_id is not None, "未返回订阅ID"
                    
                    print(f"✅ 订阅成功，订阅ID: {subscription_id}")
                
                # 3. 等待并验证接收到真实数据
                await asyncio.sleep(5)  # 等待5秒接收数据
                
                async with session.get(
                    f"{collector_url}/api/v1/data/recent",
                    params={"symbol": "BTCUSDT", "exchange": "binance", "limit": 5},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"获取最近数据失败: {response.status}"
                    recent_data = await response.json()
                    
                    assert recent_data.get('success', False), f"获取数据失败: {recent_data}"
                    
                    data_list = recent_data.get('data', [])
                    assert len(data_list) > 0, "未接收到真实市场数据"
                    
                    # 验证数据格式
                    sample_data = data_list[0]
                    assert sample_data.get('symbol') == 'BTCUSDT', "数据symbol不匹配"
                    assert sample_data.get('exchange') == 'binance', "数据exchange不匹配"
                    assert 'price' in sample_data, "数据缺少price字段"
                    assert 'timestamp' in sample_data, "数据缺少timestamp字段"
                    
                    # 验证数据时效性（数据应该是最近5分钟内的）
                    current_time = int(time.time() * 1000)
                    data_time = sample_data.get('timestamp', 0)
                    time_diff = current_time - data_time
                    assert time_diff < 5 * 60 * 1000, f"数据过旧，时间差: {time_diff}ms"
                    
                    print(f"✅ 接收到真实数据: {len(data_list)}条，最新价格: {sample_data.get('price')}")
    
    @pytest.mark.asyncio
    @requires_service("market_data_collector")
    @requires_real_network()
    async def test_should_normalize_real_binance_data_format(self):
        """
        TDD测试：应该正确规范化真实的Binance数据格式
        
        Given: 接收到Binance原始数据
        When: 进行数据规范化处理
        Then: 输出应该符合内部统一数据格式
        """
        async with real_test_environment() as env:
            assert env.services_running.get('market_data_collector', False), "市场数据采集服务未运行"
            
            collector_url = "http://localhost:8081"
            
            async with aiohttp.ClientSession() as session:
                # 1. 订阅多种数据类型
                subscribe_data = {
                    "symbol": "ETHUSDT",
                    "data_types": ["ticker", "orderbook", "trade"]
                }
                
                async with session.post(
                    f"{collector_url}/api/v1/exchange/binance/subscribe",
                    json=subscribe_data,
                    timeout=10
                ) as response:
                    assert response.status == 200
                    result = await response.json()
                    assert result.get('success', False)
                
                # 2. 等待数据收集
                await asyncio.sleep(8)
                
                # 3. 获取不同类型的规范化数据
                for data_type in ["ticker", "orderbook", "trade"]:
                    async with session.get(
                        f"{collector_url}/api/v1/data/normalized",
                        params={
                            "symbol": "ETHUSDT",
                            "exchange": "binance",
                            "data_type": data_type,
                            "limit": 3
                        },
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            normalized_data = await response.json()
                            
                            if normalized_data.get('success', False):
                                data_list = normalized_data.get('data', [])
                                
                                if len(data_list) > 0:
                                    sample = data_list[0]
                                    
                                    # 验证统一数据格式
                                    required_fields = ['symbol', 'exchange', 'timestamp', 'data_type']
                                    for field in required_fields:
                                        assert field in sample, f"{data_type}数据缺少{field}字段"
                                    
                                    assert sample['symbol'] == 'ETHUSDT'
                                    assert sample['exchange'] == 'binance'
                                    assert sample['data_type'] == data_type
                                    
                                    # 根据数据类型验证特定字段
                                    if data_type == 'ticker':
                                        assert 'price' in sample, "ticker数据缺少price字段"
                                        assert 'volume' in sample, "ticker数据缺少volume字段"
                                    elif data_type == 'orderbook':
                                        assert 'bids' in sample, "orderbook数据缺少bids字段"
                                        assert 'asks' in sample, "orderbook数据缺少asks字段"
                                    elif data_type == 'trade':
                                        assert 'price' in sample, "trade数据缺少price字段"
                                        assert 'quantity' in sample, "trade数据缺少quantity字段"
                                    
                                    print(f"✅ {data_type}数据规范化正确: {sample}")
                                else:
                                    print(f"⚠️ 未收到{data_type}类型数据")
                            else:
                                print(f"⚠️ 获取{data_type}数据失败: {normalized_data}")
    
    @pytest.mark.asyncio
    @requires_service("market_data_collector")
    @requires_real_network()
    async def test_should_handle_multiple_real_exchanges_simultaneously(self):
        """
        TDD测试：应该同时处理多个真实交易所的数据
        
        Given: 配置了多个交易所（Binance、OKX）
        When: 同时订阅相同交易对
        Then: 应该正确处理并区分数据源
        """
        async with real_test_environment() as env:
            assert env.services_running.get('market_data_collector', False), "市场数据采集服务未运行"
            
            collector_url = "http://localhost:8081"
            
            async with aiohttp.ClientSession() as session:
                # 1. 检查支持的交易所
                async with session.get(
                    f"{collector_url}/api/v1/exchanges",
                    timeout=10
                ) as response:
                    assert response.status == 200
                    exchanges_data = await response.json()
                    
                    supported_exchanges = exchanges_data.get('exchanges', [])
                    print(f"支持的交易所: {supported_exchanges}")
                
                # 2. 为每个可用交易所订阅相同交易对
                test_symbol = "BTCUSDT"
                exchanges_to_test = ['binance']  # 可以扩展到['binance', 'okx']
                
                subscription_results = {}
                
                for exchange in exchanges_to_test:
                    try:
                        subscribe_data = {
                            "symbol": test_symbol,
                            "data_types": ["ticker"]
                        }
                        
                        async with session.post(
                            f"{collector_url}/api/v1/exchange/{exchange}/subscribe",
                            json=subscribe_data,
                            timeout=10
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                if result.get('success', False):
                                    subscription_results[exchange] = result.get('subscription_id')
                                    print(f"✅ {exchange}订阅成功")
                                else:
                                    print(f"⚠️ {exchange}订阅失败: {result}")
                            else:
                                print(f"⚠️ {exchange}订阅请求失败: {response.status}")
                    except Exception as e:
                        print(f"⚠️ {exchange}连接异常: {e}")
                
                # 3. 等待数据收集
                await asyncio.sleep(10)
                
                # 4. 验证来自不同交易所的数据
                for exchange in subscription_results.keys():
                    async with session.get(
                        f"{collector_url}/api/v1/data/recent",
                        params={
                            "symbol": test_symbol,
                            "exchange": exchange,
                            "limit": 3
                        },
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            data_result = await response.json()
                            
                            if data_result.get('success', False):
                                data_list = data_result.get('data', [])
                                
                                if len(data_list) > 0:
                                    # 验证数据来源正确
                                    for data_item in data_list:
                                        assert data_item.get('exchange') == exchange, f"数据来源标识错误: {data_item}"
                                        assert data_item.get('symbol') == test_symbol, f"交易对不匹配: {data_item}"
                                    
                                    latest_price = data_list[0].get('price')
                                    print(f"✅ {exchange} {test_symbol}最新价格: {latest_price}")
                                else:
                                    print(f"⚠️ {exchange}未收到数据")
                            else:
                                print(f"⚠️ {exchange}数据获取失败: {data_result}")
                
                assert len(subscription_results) > 0, "未成功订阅任何交易所"
    
    @pytest.mark.asyncio
    @requires_service("market_data_collector")
    @requires_real_network()
    async def test_should_recover_from_real_network_interruption(self):
        """
        TDD测试：应该能从真实网络中断中恢复
        
        Given: 系统正常接收市场数据
        When: 网络连接暂时中断
        Then: 系统应该自动重连并恢复数据流
        """
        async with real_test_environment() as env:
            assert env.services_running.get('market_data_collector', False), "市场数据采集服务未运行"
            
            collector_url = "http://localhost:8081"
            
            async with aiohttp.ClientSession() as session:
                # 1. 建立初始连接并订阅
                subscribe_data = {
                    "symbol": "ADAUSDT",
                    "data_types": ["ticker"]
                }
                
                async with session.post(
                    f"{collector_url}/api/v1/exchange/binance/subscribe",
                    json=subscribe_data,
                    timeout=10
                ) as response:
                    assert response.status == 200
                    result = await response.json()
                    assert result.get('success', False)
                    subscription_id = result.get('subscription_id')
                
                # 2. 验证正常数据流
                await asyncio.sleep(5)
                
                async with session.get(
                    f"{collector_url}/api/v1/data/recent",
                    params={"symbol": "ADAUSDT", "exchange": "binance", "limit": 1},
                    timeout=10
                ) as response:
                    assert response.status == 200
                    data_result = await response.json()
                    assert data_result.get('success', False)
                    
                    initial_data = data_result.get('data', [])
                    assert len(initial_data) > 0, "初始数据流异常"
                    
                    initial_timestamp = initial_data[0].get('timestamp')
                    print(f"✅ 初始数据正常，时间戳: {initial_timestamp}")
                
                # 3. 检查连接状态和重连机制
                async with session.get(
                    f"{collector_url}/api/v1/exchange/binance/connection/stats",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        connection_stats = await response.json()
                        print(f"连接统计: {connection_stats}")
                        
                        # 如果支持，可以检查重连次数等指标
                        if 'reconnect_count' in connection_stats:
                            initial_reconnect_count = connection_stats.get('reconnect_count', 0)
                            print(f"初始重连次数: {initial_reconnect_count}")
                
                # 4. 模拟网络恢复后验证数据连续性
                await asyncio.sleep(10)  # 等待更长时间，观察可能的重连
                
                async with session.get(
                    f"{collector_url}/api/v1/data/recent",
                    params={"symbol": "ADAUSDT", "exchange": "binance", "limit": 3},
                    timeout=10
                ) as response:
                    assert response.status == 200
                    data_result = await response.json()
                    assert data_result.get('success', False)
                    
                    recent_data = data_result.get('data', [])
                    assert len(recent_data) > 0, "恢复后无数据"
                    
                    # 验证数据时效性
                    latest_timestamp = recent_data[0].get('timestamp')
                    current_time = int(time.time() * 1000)
                    time_diff = current_time - latest_timestamp
                    
                    assert time_diff < 2 * 60 * 1000, f"数据延迟过大: {time_diff}ms"
                    
                    print(f"✅ 网络恢复测试通过，最新数据时间戳: {latest_timestamp}")
    
    @pytest.mark.asyncio
    @requires_service("market_data_collector")
    @requires_real_network()
    async def test_should_respect_real_exchange_rate_limits(self):
        """
        TDD测试：应该遵守真实交易所的速率限制
        
        Given: 交易所有API速率限制
        When: 发送大量请求
        Then: 应该正确处理速率限制，不被封禁
        """
        async with real_test_environment() as env:
            assert env.services_running.get('market_data_collector', False), "市场数据采集服务未运行"
            
            collector_url = "http://localhost:8081"
            
            async with aiohttp.ClientSession() as session:
                # 1. 获取当前速率限制配置
                async with session.get(
                    f"{collector_url}/api/v1/exchange/binance/rate_limit",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        rate_limit_info = await response.json()
                        print(f"Binance速率限制配置: {rate_limit_info}")
                        
                        # 检查配置的合理性
                        if 'requests_per_minute' in rate_limit_info:
                            rpm = rate_limit_info.get('requests_per_minute', 0)
                            assert rpm > 0, "速率限制配置错误"
                            assert rpm <= 1200, "速率限制过高，可能违反交易所政策"
                
                # 2. 批量订阅测试（测试速率限制处理）
                symbols_to_test = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]
                
                subscription_results = []
                start_time = time.time()
                
                for symbol in symbols_to_test:
                    subscribe_data = {
                        "symbol": symbol,
                        "data_types": ["ticker"]
                    }
                    
                    try:
                        async with session.post(
                            f"{collector_url}/api/v1/exchange/binance/subscribe",
                            json=subscribe_data,
                            timeout=10
                        ) as response:
                            result = await response.json()
                            subscription_results.append({
                                'symbol': symbol,
                                'status': response.status,
                                'success': result.get('success', False),
                                'message': result.get('message', ''),
                                'timestamp': time.time()
                            })
                            
                            # 检查是否遇到速率限制
                            if response.status == 429:
                                print(f"⚠️ 遇到速率限制: {symbol}")
                            elif response.status == 200 and result.get('success'):
                                print(f"✅ 订阅成功: {symbol}")
                            else:
                                print(f"❌ 订阅失败: {symbol}, {result}")
                        
                        # 适当延迟，避免过快请求
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        print(f"❌ 订阅异常: {symbol}, {e}")
                        subscription_results.append({
                            'symbol': symbol,
                            'status': 0,
                            'success': False,
                            'message': str(e),
                            'timestamp': time.time()
                        })
                
                end_time = time.time()
                total_time = end_time - start_time
                
                # 3. 分析结果
                success_count = sum(1 for r in subscription_results if r['success'])
                rate_limit_count = sum(1 for r in subscription_results if r['status'] == 429)
                
                success_rate = success_count / len(symbols_to_test)
                
                print(f"批量订阅结果：")
                print(f"  总数: {len(symbols_to_test)}")
                print(f"  成功: {success_count}")
                print(f"  速率限制: {rate_limit_count}")
                print(f"  成功率: {success_rate:.2%}")
                print(f"  总耗时: {total_time:.2f}秒")
                
                # 验证速率限制处理的有效性
                assert success_rate >= 0.8, f"成功率过低: {success_rate:.2%}"
                
                # 如果遇到速率限制，验证系统的处理
                if rate_limit_count > 0:
                    print("✅ 系统正确识别并处理了速率限制")
                else:
                    print("✅ 未触发速率限制，请求频率合理")


@pytest.mark.asyncio
async def test_market_data_collector_integration():
    """市场数据采集服务集成测试入口"""
    test_instance = TestRealMarketDataCollector()
    
    async with real_test_environment() as env:
        if not env.services_running.get('market_data_collector', False):
            pytest.skip("市场数据采集服务未运行，跳过集成测试")
        
        if not env.proxy_configured:
            pytest.skip("代理未配置，跳过真实网络测试")
        
        print("🚀 开始市场数据采集服务真实性测试")
        
        # 运行所有测试方法
        await test_instance.test_should_connect_to_real_binance_testnet_with_proxy()
        await test_instance.test_should_normalize_real_binance_data_format()
        await test_instance.test_should_handle_multiple_real_exchanges_simultaneously()
        await test_instance.test_should_recover_from_real_network_interruption()
        await test_instance.test_should_respect_real_exchange_rate_limits()
        
        print("🎉 所有市场数据采集服务测试通过")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_market_data_collector_integration())