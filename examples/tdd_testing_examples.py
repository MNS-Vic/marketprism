#!/usr/bin/env python3
"""
MarketPrism TDD测试示例
展示如何使用扩展的TDD测试框架进行真实环境验证

使用方法：
    python examples/tdd_testing_examples.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment


async def demo_basic_tests():
    """演示基础TDD测试"""
    print("🎯 演示基础TDD测试")
    print("="*50)
    
    async with real_test_environment() as env:
        print(f"环境状态: {env.config['environment']}")
        print(f"数据库就绪: {env.databases_ready}")
        print(f"服务运行: {env.services_running}")
        
        # 示例：测试Redis连接
        if env.databases_ready.get('redis', False):
            import redis
            r = redis.Redis(host='localhost', port=6379, db=env.config['databases']['redis']['test_db'])
            
            # TDD测试：应该能存储和读取数据
            test_key = "tdd_test_key"
            test_value = "tdd_test_value"
            
            r.set(test_key, test_value)
            stored_value = r.get(test_key).decode()
            
            assert stored_value == test_value, f"数据不匹配: {stored_value} != {test_value}"
            print("✅ Redis存储测试通过")
            
            # 清理测试数据
            r.delete(test_key)
        else:
            print("❌ Redis未就绪，跳过测试")


async def demo_exchange_integration():
    """演示交易所API集成测试"""
    print("\n🎯 演示交易所API集成测试")
    print("="*50)
    
    async with real_test_environment() as env:
        if not env.proxy_configured:
            print("⚠️ 代理未配置，跳过网络测试")
            return
        
        import aiohttp
        
        # 示例：测试Binance Testnet API
        binance_config = env.config['exchanges']['binance']
        base_url = binance_config['base_url']
        
        async with aiohttp.ClientSession() as session:
            try:
                # TDD测试：应该能获取服务器时间
                async with session.get(f"{base_url}/api/v3/time", timeout=10) as response:
                    assert response.status == 200, f"API请求失败: {response.status}"
                    
                    time_data = await response.json()
                    assert 'serverTime' in time_data, "响应缺少serverTime字段"
                    
                    print(f"✅ Binance服务器时间: {time_data['serverTime']}")
                    
                # TDD测试：应该能获取交易对信息
                async with session.get(f"{base_url}/api/v3/exchangeInfo", timeout=15) as response:
                    assert response.status == 200, f"获取交易信息失败: {response.status}"
                    
                    exchange_info = await response.json()
                    symbols = exchange_info.get('symbols', [])
                    
                    assert len(symbols) > 0, "未获取到交易对信息"
                    print(f"✅ 获取到 {len(symbols)} 个交易对")
                    
            except Exception as e:
                print(f"❌ Binance API测试失败: {e}")


async def demo_microservice_integration():
    """演示微服务集成测试"""
    print("\n🎯 演示微服务集成测试")
    print("="*50)
    
    async with real_test_environment() as env:
        import aiohttp
        
        # 检查API网关状态
        if env.services_running.get('api_gateway', False):
            async with aiohttp.ClientSession() as session:
                try:
                    # TDD测试：API网关应该响应健康检查
                    async with session.get("http://localhost:8080/health", timeout=5) as response:
                        assert response.status == 200, f"API网关健康检查失败: {response.status}"
                        
                        health_data = await response.json()
                        print(f"✅ API网关状态: {health_data}")
                        
                    # TDD测试：应该能发现服务
                    async with session.get("http://localhost:8080/api/v1/services", timeout=10) as response:
                        if response.status == 200:
                            services_data = await response.json()
                            services = services_data.get('services', [])
                            
                            print(f"✅ 发现 {len(services)} 个服务")
                            for service in services:
                                print(f"   - {service.get('name')}: {service.get('status')}")
                        else:
                            print(f"⚠️ 服务发现失败: {response.status}")
                            
                except Exception as e:
                    print(f"❌ 微服务测试失败: {e}")
        else:
            print("⚠️ API网关未运行，跳过测试")


async def demo_end_to_end_flow():
    """演示端到端数据流测试"""
    print("\n🎯 演示端到端数据流测试")
    print("="*50)
    
    async with real_test_environment() as env:
        # 检查必要服务
        required_services = ['api_gateway', 'market_data_collector', 'data_storage']
        missing_services = [s for s in required_services if not env.services_running.get(s, False)]
        
        if missing_services:
            print(f"⚠️ 缺少服务，跳过端到端测试: {missing_services}")
            return
        
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            try:
                # TDD测试：应该能启动数据采集
                subscribe_payload = {
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "data_types": ["ticker"],
                    "test_mode": True
                }
                
                async with session.post(
                    "http://localhost:8080/api/v1/market-data/subscribe",
                    json=subscribe_payload,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('success'):
                            subscription_id = result.get('subscription_id')
                            print(f"✅ 数据采集已启动: {subscription_id}")
                            
                            # 等待数据采集
                            await asyncio.sleep(5)
                            
                            # TDD测试：应该能查询到采集的数据
                            async with session.get(
                                "http://localhost:8080/api/v1/data-storage/query",
                                params={"symbol": "BTCUSDT", "limit": 5},
                                timeout=10
                            ) as query_response:
                                if query_response.status == 200:
                                    query_result = await query_response.json()
                                    if query_result.get('success'):
                                        data = query_result.get('data', [])
                                        print(f"✅ 查询到 {len(data)} 条数据")
                                        
                                        if data:
                                            sample = data[0]
                                            print(f"   示例数据: {sample.get('symbol')} - {sample.get('price')}")
                                    else:
                                        print("❌ 数据查询失败")
                                else:
                                    print(f"❌ 数据查询请求失败: {query_response.status}")
                            
                            # 清理订阅
                            async with session.delete(
                                f"http://localhost:8080/api/v1/market-data/subscription/{subscription_id}",
                                timeout=5
                            ):
                                pass
                        else:
                            print("❌ 数据采集启动失败")
                    else:
                        print(f"❌ 数据采集请求失败: {response.status}")
                        
            except Exception as e:
                print(f"❌ 端到端测试失败: {e}")


async def demo_performance_testing():
    """演示性能测试"""
    print("\n🎯 演示性能测试")
    print("="*50)
    
    async with real_test_environment() as env:
        if not env.services_running.get('api_gateway', False):
            print("⚠️ API网关未运行，跳过性能测试")
            return
        
        import aiohttp
        import time
        
        # TDD测试：API响应时间应该在可接受范围内
        response_times = []
        success_count = 0
        total_requests = 10
        
        async with aiohttp.ClientSession() as session:
            for i in range(total_requests):
                start_time = time.time()
                
                try:
                    async with session.get("http://localhost:8080/health", timeout=5) as response:
                        end_time = time.time()
                        response_time = (end_time - start_time) * 1000  # 转换为毫秒
                        
                        if response.status == 200:
                            success_count += 1
                            response_times.append(response_time)
                            
                        print(f"请求 {i+1}: {response_time:.2f}ms (状态: {response.status})")
                        
                except Exception as e:
                    print(f"请求 {i+1} 失败: {e}")
                
                await asyncio.sleep(0.1)  # 小延迟
        
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
            
            print(f"\n📊 性能统计:")
            print(f"   成功率: {success_count}/{total_requests} ({success_count/total_requests:.1%})")
            print(f"   平均响应时间: {avg_time:.2f}ms")
            print(f"   最快响应时间: {min_time:.2f}ms")
            print(f"   最慢响应时间: {max_time:.2f}ms")
            
            # TDD断言：性能应该满足基准
            assert avg_time < 200, f"平均响应时间过长: {avg_time:.2f}ms"
            assert success_count / total_requests >= 0.9, f"成功率过低: {success_count/total_requests:.1%}"
            
            print("✅ 性能测试通过")


async def main():
    """主演示函数"""
    print("🚀 MarketPrism TDD测试框架演示")
    print("="*60)
    
    try:
        # 运行各种演示
        await demo_basic_tests()
        await demo_exchange_integration()
        await demo_microservice_integration()
        await demo_end_to_end_flow()
        await demo_performance_testing()
        
        print("\n🎉 所有演示完成！")
        print("\n📝 接下来可以尝试：")
        print("   python scripts/tdd_setup.py --test --type basic")
        print("   python scripts/tdd_setup.py --test --type exchange")
        print("   python scripts/tdd_setup.py --test --type gateway")
        print("   python scripts/tdd_setup.py --test --type e2e")
        
    except KeyboardInterrupt:
        print("\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示过程中出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())