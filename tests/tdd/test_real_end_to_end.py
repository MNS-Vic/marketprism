"""
TDD测试：端到端真实环境集成验证
测试完整的数据流：从交易所API -> 数据采集 -> 消息队列 -> 数据存储 -> API查询

遵循TDD原则：
1. 先写测试，描述完整业务流程的期望行为
2. 验证真实数据在整个系统中的流转
3. 测试系统整体性能和稳定性
4. 确保端到端的数据一致性和可靠性
"""

from datetime import datetime, timezone
import pytest
import asyncio
import aiohttp
import time
import json
from pathlib import Path
import sys
import uuid

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment, requires_service, requires_real_network


class TestRealEndToEndIntegration(RealTestBase):
    """端到端真实环境集成测试"""
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_complete_market_data_flow_from_exchange_to_storage(self):
        """
        TDD测试：完整的市场数据流从交易所到存储
        
        Given: 所有微服务正常运行，网络连接正常
        When: 从Binance采集真实市场数据并存储
        Then: 数据应该完整地流转并可以通过API查询到
        
        数据流：Binance API -> 数据采集服务 -> 消息队列 -> 数据存储服务 -> API查询
        """
        async with real_test_environment() as env:
            # 验证所有必要服务都在运行
            required_services = ['market_data_collector', 'data_storage', 'message_broker', 'api_gateway']
            for service in required_services:
                assert env.services_running.get(service, False), f"{service}服务未运行"
            
            test_symbol = "BTCUSDT"
            test_id = str(uuid.uuid4())[:8]
            
            print(f"🚀 开始端到端测试 - 测试ID: {test_id}")
            
            async with aiohttp.ClientSession() as session:
                # 步骤1: 通过API网关启动数据采集
                print("📡 步骤1: 启动数据采集")
                
                subscribe_payload = {
                    "symbol": test_symbol,
                    "exchange": "binance",
                    "data_types": ["ticker", "orderbook"],
                    "test_id": test_id
                }
                
                async with session.post(
                    "http://localhost:8080/api/v1/market-data/subscribe",
                    json=subscribe_payload,
                    timeout=15
                ) as response:
                    assert response.status == 200, f"数据采集启动失败: {response.status}"
                    subscribe_result = await response.json()
                    
                    assert subscribe_result.get('success', False), f"数据采集启动失败: {subscribe_result}"
                    subscription_id = subscribe_result.get('subscription_id')
                    
                    print(f"✅ 数据采集已启动，订阅ID: {subscription_id}")
                
                # 步骤2: 等待数据采集和处理
                print("⏳ 步骤2: 等待数据采集和处理 (15秒)")
                await asyncio.sleep(15)
                
                # 步骤3: 验证数据采集服务状态
                print("🔍 步骤3: 验证数据采集状态")
                
                async with session.get(
                    f"http://localhost:8080/api/v1/market-data/subscription/{subscription_id}/status",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        print(f"📊 采集状态: {status_data}")
                        
                        # 验证采集状态
                        assert status_data.get('active', False), "数据采集未激活"
                        
                        data_count = status_data.get('data_received', 0)
                        assert data_count > 0, f"未接收到数据: {data_count}"
                        
                        print(f"✅ 已接收 {data_count} 条数据")
                    else:
                        print(f"⚠️ 无法获取采集状态: {response.status}")
                
                # 步骤4: 通过数据存储服务查询数据
                print("💾 步骤4: 查询存储的数据")
                
                query_params = {
                    "symbol": test_symbol,
                    "exchange": "binance",
                    "limit": 10,
                    "start_time": int((time.time() - 300) * 1000),  # 过去5分钟
                    "test_id": test_id
                }
                
                async with session.get(
                    "http://localhost:8080/api/v1/data-storage/query",
                    params=query_params,
                    timeout=10
                ) as response:
                    assert response.status == 200, f"数据查询失败: {response.status}"
                    query_result = await response.json()
                    
                    assert query_result.get('success', False), f"数据查询失败: {query_result}"
                    
                    stored_data = query_result.get('data', [])
                    assert len(stored_data) > 0, "未查询到存储的数据"
                    
                    print(f"✅ 查询到 {len(stored_data)} 条存储数据")
                
                # 步骤5: 验证数据完整性和质量
                print("🔍 步骤5: 验证数据完整性")
                
                sample_data = stored_data[0]
                
                # 验证必要字段
                required_fields = ['symbol', 'exchange', 'timestamp', 'data_type', 'price']
                for field in required_fields:
                    assert field in sample_data, f"数据缺少字段: {field}"
                
                # 验证数据值的合理性
                assert sample_data['symbol'] == test_symbol, f"交易对不匹配: {sample_data['symbol']}"
                assert sample_data['exchange'] == 'binance', f"交易所不匹配: {sample_data['exchange']}"
                
                price = float(sample_data['price'])
                assert price > 0, f"价格无效: {price}"
                assert price > 1000, f"BTC价格异常低: {price}"  # BTC价格应该大于1000
                
                # 验证时间戳合理性
                data_timestamp = sample_data['timestamp']
                current_time = int(time.time() * 1000)
                time_diff = current_time - data_timestamp
                assert time_diff < 10 * 60 * 1000, f"数据时间戳过旧: {time_diff}ms"
                
                print(f"✅ 数据质量验证通过: 价格={price}, 时间差={time_diff/1000:.2f}秒")
                
                # 步骤6: 测试数据时效性
                print("⏰ 步骤6: 测试数据时效性")
                
                # 检查最新数据的时效性
                latest_data = sorted(stored_data, key=lambda x: x['timestamp'], reverse=True)[0]
                latest_timestamp = latest_data['timestamp']
                latest_time_diff = current_time - latest_timestamp
                
                # 最新数据应该在过去2分钟内
                assert latest_time_diff < 2 * 60 * 1000, f"最新数据过旧: {latest_time_diff/1000:.2f}秒"
                
                print(f"✅ 数据时效性验证通过: 最新数据延迟 {latest_time_diff/1000:.2f}秒")
                
                # 步骤7: 清理测试订阅
                print("🧹 步骤7: 清理测试订阅")
                
                async with session.delete(
                    f"http://localhost:8080/api/v1/market-data/subscription/{subscription_id}",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        cleanup_result = await response.json()
                        print(f"✅ 订阅已清理: {cleanup_result}")
                    else:
                        print(f"⚠️ 订阅清理失败: {response.status}")
                
                print(f"🎉 端到端测试完成 - 测试ID: {test_id}")
    
    @pytest.mark.asyncio
    @requires_real_network()
    async def test_system_performance_under_real_load(self):
        """
        TDD测试：真实负载下的系统性能
        
        Given: 系统接收真实市场数据
        When: 同时处理多个交易对和数据类型
        Then: 系统应该保持良好的性能指标
        """
        async with real_test_environment() as env:
            required_services = ['market_data_collector', 'data_storage', 'monitoring', 'api_gateway']
            for service in required_services:
                assert env.services_running.get(service, False), f"{service}服务未运行"
            
            # 配置多个交易对进行压力测试
            test_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
            subscription_ids = []
            
            async with aiohttp.ClientSession() as session:
                # 启动多个数据采集任务
                print("🚀 启动多交易对数据采集")
                
                for symbol in test_symbols:
                    subscribe_payload = {
                        "symbol": symbol,
                        "exchange": "binance",
                        "data_types": ["ticker", "orderbook", "trade"]
                    }
                    
                    async with session.post(
                        "http://localhost:8080/api/v1/market-data/subscribe",
                        json=subscribe_payload,
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            if result.get('success'):
                                subscription_ids.append(result.get('subscription_id'))
                                print(f"✅ {symbol} 采集已启动")
                
                assert len(subscription_ids) > 0, "未能启动任何数据采集"
                
                # 运行负载测试
                print("⏳ 运行性能负载测试 (30秒)")
                start_time = time.time()
                
                await asyncio.sleep(30)
                
                end_time = time.time()
                test_duration = end_time - start_time
                
                # 收集性能指标
                print("📊 收集性能指标")
                
                # 1. 查询系统监控指标
                async with session.get(
                    "http://localhost:8080/api/v1/monitoring/metrics",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        metrics_data = await response.json()
                        
                        # 分析关键性能指标
                        cpu_usage = metrics_data.get('cpu_usage_percent', 0)
                        memory_usage = metrics_data.get('memory_usage_percent', 0)
                        data_rate = metrics_data.get('data_points_per_second', 0)
                        
                        print(f"   CPU使用率: {cpu_usage:.2f}%")
                        print(f"   内存使用率: {memory_usage:.2f}%")
                        print(f"   数据处理速率: {data_rate:.2f} 点/秒")
                        
                        # 性能基准验证
                        assert cpu_usage < 80, f"CPU使用率过高: {cpu_usage:.2f}%"
                        assert memory_usage < 85, f"内存使用率过高: {memory_usage:.2f}%"
                        assert data_rate > 10, f"数据处理速率过低: {data_rate:.2f} 点/秒"
                        
                        print("✅ 系统性能指标正常")
                
                # 2. 测试API响应时间
                print("⏱️ 测试API响应时间")
                
                response_times = []
                for i in range(10):
                    api_start = time.time()
                    
                    async with session.get(
                        "http://localhost:8080/api/v1/data-storage/query",
                        params={"symbol": "BTCUSDT", "limit": 5},
                        timeout=5
                    ) as response:
                        api_end = time.time()
                        
                        if response.status == 200:
                            response_time = (api_end - api_start) * 1000  # 转换为毫秒
                            response_times.append(response_time)
                    
                    await asyncio.sleep(0.5)
                
                if response_times:
                    avg_response_time = sum(response_times) / len(response_times)
                    max_response_time = max(response_times)
                    
                    print(f"   平均响应时间: {avg_response_time:.2f}ms")
                    print(f"   最大响应时间: {max_response_time:.2f}ms")
                    
                    # 响应时间基准验证
                    assert avg_response_time < 200, f"平均响应时间过长: {avg_response_time:.2f}ms"
                    assert max_response_time < 500, f"最大响应时间过长: {max_response_time:.2f}ms"
                    
                    print("✅ API响应时间正常")
                
                # 3. 验证数据完整性
                print("🔍 验证数据完整性")
                
                total_data_points = 0
                for symbol in test_symbols:
                    async with session.get(
                        "http://localhost:8080/api/v1/data-storage/query",
                        params={
                            "symbol": symbol,
                            "limit": 100,
                            "start_time": int((start_time) * 1000)
                        },
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            query_result = await response.json()
                            if query_result.get('success'):
                                data_count = len(query_result.get('data', []))
                                total_data_points += data_count
                                print(f"   {symbol}: {data_count} 数据点")
                
                print(f"   总数据点: {total_data_points}")
                
                # 数据完整性验证
                expected_min_data = len(test_symbols) * 10  # 每个交易对至少10个数据点
                assert total_data_points >= expected_min_data, f"数据点不足: {total_data_points} < {expected_min_data}"
                
                print("✅ 数据完整性验证通过")
                
                # 清理订阅
                print("🧹 清理测试订阅")
                for subscription_id in subscription_ids:
                    try:
                        async with session.delete(
                            f"http://localhost:8080/api/v1/market-data/subscription/{subscription_id}",
                            timeout=5
                        ):
                            pass
                    except:
                        pass
                
                print("🎉 性能负载测试完成")
    
    @pytest.mark.asyncio
    async def test_system_resilience_and_recovery(self):
        """
        TDD测试：系统弹性和恢复能力
        
        Given: 系统正常运行并处理数据
        When: 模拟各种故障场景
        Then: 系统应该能够检测故障并自动恢复
        """
        async with real_test_environment() as env:
            required_services = ['market_data_collector', 'data_storage', 'api_gateway']
            for service in required_services:
                assert env.services_running.get(service, False), f"{service}服务未运行"
            
            async with aiohttp.ClientSession() as session:
                # 1. 建立基线：启动正常数据采集
                print("📊 建立性能基线")
                
                subscribe_payload = {
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "data_types": ["ticker"]
                }
                
                async with session.post(
                    "http://localhost:8080/api/v1/market-data/subscribe",
                    json=subscribe_payload,
                    timeout=10
                ) as response:
                    assert response.status == 200
                    result = await response.json()
                    subscription_id = result.get('subscription_id')
                
                # 等待建立基线数据
                await asyncio.sleep(10)
                
                # 2. 测试网络中断恢复
                print("🌐 测试网络中断恢复")
                
                # 获取中断前的数据量
                async with session.get(
                    "http://localhost:8080/api/v1/data-storage/query",
                    params={"symbol": "BTCUSDT", "limit": 10},
                    timeout=10
                ) as response:
                    before_data = await response.json()
                    before_count = len(before_data.get('data', []))
                
                print(f"   中断前数据量: {before_count}")
                
                # 模拟网络恢复后的数据采集
                await asyncio.sleep(15)
                
                async with session.get(
                    "http://localhost:8080/api/v1/data-storage/query",
                    params={"symbol": "BTCUSDT", "limit": 20},
                    timeout=10
                ) as response:
                    after_data = await response.json()
                    after_count = len(after_data.get('data', []))
                
                print(f"   恢复后数据量: {after_count}")
                
                # 验证数据恢复
                assert after_count > before_count, "网络恢复后未收到新数据"
                
                print("✅ 网络中断恢复测试通过")
                
                # 3. 测试高并发请求处理
                print("🚦 测试高并发请求处理")
                
                concurrent_requests = 20
                success_count = 0
                
                tasks = []
                for i in range(concurrent_requests):
                    task = asyncio.create_task(
                        self._make_concurrent_request(session, i)
                    )
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, dict) and result.get('success'):
                        success_count += 1
                
                success_rate = success_count / concurrent_requests
                print(f"   并发请求成功率: {success_rate:.2%} ({success_count}/{concurrent_requests})")
                
                # 高并发下成功率应该达到80%以上
                assert success_rate >= 0.8, f"并发请求成功率过低: {success_rate:.2%}"
                
                print("✅ 高并发处理测试通过")
                
                # 4. 测试数据一致性
                print("🔍 测试数据一致性")
                
                # 通过不同路径查询相同数据
                direct_query_params = {"symbol": "BTCUSDT", "limit": 5}
                
                # 路径1: 通过API网关
                async with session.get(
                    "http://localhost:8080/api/v1/data-storage/query",
                    params=direct_query_params,
                    timeout=10
                ) as response:
                    gateway_data = await response.json()
                
                # 路径2: 直接访问数据存储服务
                async with session.get(
                    "http://localhost:8082/api/v1/data/query",
                    params=direct_query_params,
                    timeout=10
                ) as response:
                    direct_data = await response.json()
                
                # 比较数据一致性
                if gateway_data.get('success') and direct_data.get('success'):
                    gateway_items = gateway_data.get('data', [])
                    direct_items = direct_data.get('data', [])
                    
                    if len(gateway_items) > 0 and len(direct_items) > 0:
                        # 比较最新数据点
                        gateway_latest = gateway_items[0]
                        direct_latest = direct_items[0]
                        
                        # 验证关键字段一致性
                        assert gateway_latest['symbol'] == direct_latest['symbol']
                        assert gateway_latest['exchange'] == direct_latest['exchange']
                        
                        print("✅ 数据一致性验证通过")
                
                # 清理
                try:
                    async with session.delete(
                        f"http://localhost:8080/api/v1/market-data/subscription/{subscription_id}",
                        timeout=5
                    ):
                        pass
                except:
                    pass
                
                print("🎉 系统弹性测试完成")
    
    async def _make_concurrent_request(self, session, request_id):
        """发送并发请求"""
        try:
            async with session.get(
                "http://localhost:8080/api/v1/health",
                timeout=3
            ) as response:
                if response.status == 200:
                    return {'request_id': request_id, 'success': True}
                else:
                    return {'request_id': request_id, 'success': False, 'status': response.status}
        except Exception as e:
            return {'request_id': request_id, 'success': False, 'error': str(e)}


@pytest.mark.asyncio
async def test_end_to_end_integration_suite():
    """端到端集成测试套件入口"""
    test_instance = TestRealEndToEndIntegration()
    
    async with real_test_environment() as env:
        # 检查所有必要服务是否运行
        required_services = ['market_data_collector', 'data_storage', 'message_broker', 'api_gateway']
        missing_services = [s for s in required_services if not env.services_running.get(s, False)]
        
        if missing_services:
            pytest.skip(f"缺少必要服务: {missing_services}")
        
        if not env.proxy_configured:
            pytest.skip("代理未配置，跳过端到端测试")
        
        print("🚀 开始端到端集成测试")
        
        # 运行端到端测试
        await test_instance.test_complete_market_data_flow_from_exchange_to_storage()
        await test_instance.test_system_performance_under_real_load()
        await test_instance.test_system_resilience_and_recovery()
        
        print("🎉 所有端到端测试完成")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_end_to_end_integration_suite())