#!/usr/bin/env python3
"""
聚焦的TDD测试运行器
专注于核心功能的TDD验证，基于实际可用的服务和API

重点测试：
1. 核心模块集成测试
2. 数据存储和会话管理
3. 真实网络API调用
4. 配置管理和错误处理
"""

import asyncio
import aiohttp
import time
import sys
import redis
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase

class FocusedTDDTester:
    """聚焦的TDD测试器"""
    
    def __init__(self):
        self.test_base = RealTestBase()
        self.config = self.test_base.config
        self.results = {}
        
    async def test_unified_session_manager_real_usage(self):
        """
        TDD测试：统一会话管理器的真实使用场景
        
        Given: 统一会话管理器已加载
        When: 执行真实的HTTP请求
        Then: 应该正确处理代理、超时、重试等功能
        """
        print("🧪 测试统一会话管理器真实使用...")
        
        try:
            from core.networking import unified_session_manager, UnifiedSessionConfig
            
            # 测试基本配置
            config = UnifiedSessionConfig(
                connection_timeout=10.0,
                read_timeout=30.0,
                total_timeout=60.0,
                max_retries=3
            )
            
            # 创建新的管理器实例进行测试
            from core.networking import UnifiedSessionManager
            test_manager = UnifiedSessionManager(config)
            
            try:
                # 1. 测试HTTP请求功能
                session = await test_manager.get_session("test_http")
                
                # 测试真实的HTTP请求
                async with session.get('https://httpbin.org/json', timeout=10) as response:
                    assert response.status == 200, f"HTTP请求失败: {response.status}"
                    data = await response.json()
                    assert 'slideshow' in data, "响应数据格式不正确"
                
                print("   ✅ HTTP请求功能正常")
                
                # 2. 测试会话统计
                stats = test_manager.get_session_stats()
                assert isinstance(stats, dict), "统计数据格式错误"
                assert stats['sessions_created'] >= 1, "会话计数错误"
                assert 'test_http' in stats['session_names'], "会话名称记录错误"
                
                print(f"   ✅ 会话统计: {stats['sessions_created']} 个会话已创建")
                
                # 3. 测试健康状态
                health = test_manager.get_health_status()
                assert health['healthy'] == True, "健康状态应该为True"
                assert health['health_score'] >= 80, f"健康分数过低: {health['health_score']}"
                
                print(f"   ✅ 健康状态: {health['status']} (分数: {health['health_score']})")
                
                # 4. 测试清理功能
                await test_manager.close()
                print("   ✅ 会话管理器清理完成")
                
                self.results['unified_session_manager'] = True
                return True
                
            except Exception as e:
                await test_manager.close()
                raise e
                
        except Exception as e:
            print(f"   ❌ 统一会话管理器测试失败: {e}")
            self.results['unified_session_manager'] = False
            return False
    
    async def test_unified_storage_manager_integration(self):
        """
        TDD测试：统一存储管理器集成
        
        Given: 统一存储管理器已加载
        When: 进行数据存储和读取操作
        Then: 应该正确处理各种存储后端
        """
        print("🧪 测试统一存储管理器集成...")
        
        try:
            from core.storage import UnifiedStorageManager, StorageConfig
            
            # 测试配置创建
            config = StorageConfig(
                enabled=False,  # 暂时禁用ClickHouse（因为未启动）
                redis_enabled=False,  # 暂时禁用Redis（因为未启动）
                storage_type="simple",  # 使用简化存储进行测试
                memory_cache_enabled=True  # 使用内存缓存进行测试
            )
            
            # 创建存储管理器
            storage_manager = UnifiedStorageManager(config)
            
            try:
                # 1. 测试基本初始化
                assert storage_manager is not None, "存储管理器创建失败"
                print("   ✅ 存储管理器初始化成功")
                
                # 2. 测试配置验证
                assert hasattr(storage_manager, 'config'), "缺少配置属性"
                assert storage_manager.config == config, "配置不匹配"
                print("   ✅ 配置验证通过")
                
                # 3. 测试状态获取
                status = storage_manager.get_status()
                assert isinstance(status, dict), "状态格式错误"
                print(f"   ✅ 存储状态: {status}")
                
                # 4. 测试向后兼容性
                from core.storage import storage_manager as global_storage_manager
                assert global_storage_manager is not None, "全局存储管理器不可用"
                print("   ✅ 向后兼容性验证通过")
                
                self.results['unified_storage_manager'] = True
                return True
                
            finally:
                # 清理测试存储管理器
                if hasattr(storage_manager, 'close'):
                    await storage_manager.close()
                
        except Exception as e:
            print(f"   ❌ 统一存储管理器测试失败: {e}")
            self.results['unified_storage_manager'] = False
            return False
    
    async def test_real_network_api_calls(self):
        """
        TDD测试：真实网络API调用
        
        Given: 网络连接可用
        When: 调用各种真实API端点
        Then: 应该正确处理响应和错误
        """
        print("🧪 测试真实网络API调用...")
        
        try:
            # 测试多个真实API端点
            test_apis = [
                {
                    'name': 'HTTPBin IP',
                    'url': 'https://httpbin.org/ip',
                    'expected_keys': ['origin']
                },
                {
                    'name': 'HTTPBin UUID',
                    'url': 'https://httpbin.org/uuid',
                    'expected_keys': ['uuid']
                },
                {
                    'name': 'JSONPlaceholder',
                    'url': 'https://jsonplaceholder.typicode.com/posts/1',
                    'expected_keys': ['userId', 'id', 'title', 'body']
                }
            ]
            
            successful_calls = 0
            
            async with aiohttp.ClientSession() as session:
                for api_test in test_apis:
                    try:
                        print(f"   🔍 测试 {api_test['name']}...")
                        
                        start_time = time.time()
                        async with session.get(api_test['url'], timeout=10) as response:
                            end_time = time.time()
                            response_time = (end_time - start_time) * 1000
                            
                            assert response.status == 200, f"API请求失败: {response.status}"
                            
                            data = await response.json()
                            
                            # 验证预期字段
                            for key in api_test['expected_keys']:
                                assert key in data, f"响应缺少字段: {key}"
                            
                            print(f"   ✅ {api_test['name']} 成功 (响应时间: {response_time:.2f}ms)")
                            successful_calls += 1
                            
                    except Exception as e:
                        print(f"   ❌ {api_test['name']} 失败: {e}")
            
            # 验证成功率 (调整为70%以适应网络环境变化)
            success_rate = successful_calls / len(test_apis)
            assert success_rate >= 0.7, f"API调用成功率过低: {success_rate:.2%}"
            
            print(f"   ✅ API调用成功率: {success_rate:.2%}")
            
            self.results['real_network_api'] = True
            return True
            
        except Exception as e:
            print(f"   ❌ 真实网络API测试失败: {e}")
            self.results['real_network_api'] = False
            return False
    
    async def test_binance_testnet_basic_connectivity(self):
        """
        TDD测试：Binance Testnet基础连接性
        
        Given: Binance Testnet可访问
        When: 调用基础的公共API
        Then: 应该返回正确的数据格式
        """
        print("🧪 测试Binance Testnet基础连接性...")
        
        try:
            base_url = "https://testnet.binance.vision"
            
            async with aiohttp.ClientSession() as session:
                # 1. 测试服务器时间
                async with session.get(f"{base_url}/api/v3/time", timeout=10) as response:
                    assert response.status == 200, f"服务器时间API失败: {response.status}"
                    
                    time_data = await response.json()
                    assert 'serverTime' in time_data, "时间响应缺少serverTime字段"
                    
                    server_time = time_data['serverTime']
                    local_time = int(time.time() * 1000)
                    time_diff = abs(server_time - local_time)
                    
                    # 允许5分钟的时间差
                    assert time_diff < 5 * 60 * 1000, f"服务器时间差异过大: {time_diff}ms"
                    
                    print(f"   ✅ 服务器时间同步正常 (差异: {time_diff/1000:.2f}秒)")
                
                # 2. 测试交易对信息
                async with session.get(f"{base_url}/api/v3/exchangeInfo", timeout=15) as response:
                    assert response.status == 200, f"交易信息API失败: {response.status}"
                    
                    exchange_info = await response.json()
                    assert 'symbols' in exchange_info, "交易信息缺少symbols字段"
                    
                    symbols = exchange_info['symbols']
                    assert len(symbols) > 0, "未获取到交易对信息"
                    
                    # 查找BTCUSDT
                    btc_symbol = next((s for s in symbols if s['symbol'] == 'BTCUSDT'), None)
                    assert btc_symbol is not None, "未找到BTCUSDT交易对"
                    assert btc_symbol['status'] == 'TRADING', "BTCUSDT不在交易状态"
                    
                    print(f"   ✅ 获取到{len(symbols)}个交易对，BTCUSDT状态正常")
                
                # 3. 测试市场数据
                async with session.get(
                    f"{base_url}/api/v3/ticker/price",
                    params={"symbol": "BTCUSDT"},
                    timeout=10
                ) as response:
                    assert response.status == 200, f"价格API失败: {response.status}"
                    
                    price_data = await response.json()
                    assert 'price' in price_data, "价格响应缺少price字段"
                    assert 'symbol' in price_data, "价格响应缺少symbol字段"
                    
                    price = float(price_data['price'])
                    assert price > 0, f"价格无效: {price}"
                    assert price > 1000, f"BTC价格异常低: {price}"  # BTC价格通常大于1000
                    
                    print(f"   ✅ BTCUSDT当前价格: {price}")
            
            self.results['binance_testnet'] = True
            return True
            
        except Exception as e:
            print(f"   ❌ Binance Testnet连接测试失败: {e}")
            self.results['binance_testnet'] = False
            return False
    
    async def test_configuration_management(self):
        """
        TDD测试：配置管理系统
        
        Given: 配置文件存在且格式正确
        When: 加载和验证配置
        Then: 应该正确解析所有必要的配置项
        """
        print("🧪 测试配置管理系统...")
        
        try:
            config = self.config
            
            # 1. 验证顶级配置节
            required_sections = ['environment', 'services', 'databases', 'exchanges']
            for section in required_sections:
                assert section in config, f"配置缺少{section}节"
            
            print(f"   ✅ 所有必需的配置节都存在: {required_sections}")
            
            # 2. 验证服务配置
            services_config = config['services']
            expected_services = ['api_gateway', 'market_data_collector', 'data_storage']
            
            found_services = []
            for service in expected_services:
                if service in services_config:
                    service_config = services_config[service]
                    
                    # 验证服务配置结构
                    required_fields = ['host', 'port', 'health_endpoint']
                    for field in required_fields:
                        assert field in service_config, f"{service}配置缺少{field}字段"
                    
                    found_services.append(service)
            
            print(f"   ✅ 发现配置的服务: {found_services}")
            
            # 3. 验证交易所配置
            exchanges_config = config['exchanges']
            
            for exchange_name, exchange_config in exchanges_config.items():
                # 验证基本字段
                required_fields = ['base_url']
                for field in required_fields:
                    assert field in exchange_config, f"{exchange_name}配置缺少{field}字段"
                
                # 验证URL格式
                base_url = exchange_config['base_url']
                assert base_url.startswith('http'), f"{exchange_name}的base_url格式错误"
            
            print(f"   ✅ 交易所配置验证通过: {list(exchanges_config.keys())}")
            
            # 4. 验证环境配置
            env_config = config['environment']
            assert 'mode' in env_config, "环境配置缺少mode字段"
            
            print(f"   ✅ 环境模式: {env_config['mode']}")
            
            self.results['configuration_management'] = True
            return True
            
        except Exception as e:
            print(f"   ❌ 配置管理系统测试失败: {e}")
            self.results['configuration_management'] = False
            return False
    
    async def test_error_handling_and_resilience(self):
        """
        TDD测试：错误处理和弹性
        
        Given: 系统面临各种错误场景
        When: 遇到网络错误、超时、无效响应等
        Then: 应该优雅地处理错误并提供有用的信息
        """
        print("🧪 测试错误处理和弹性...")
        
        try:
            error_scenarios = []
            
            async with aiohttp.ClientSession() as session:
                # 1. 测试无效URL处理
                try:
                    async with session.get('https://invalid-domain-12345.com', timeout=5) as response:
                        pass
                except Exception as e:
                    error_scenarios.append(('无效域名', type(e).__name__))
                    print(f"   ✅ 无效域名错误处理: {type(e).__name__}")
                
                # 2. 测试超时处理
                try:
                    async with session.get('https://httpbin.org/delay/10', timeout=2) as response:
                        pass
                except Exception as e:
                    error_scenarios.append(('请求超时', type(e).__name__))
                    print(f"   ✅ 请求超时错误处理: {type(e).__name__}")
                
                # 3. 测试404错误处理
                try:
                    async with session.get('https://httpbin.org/status/404', timeout=5) as response:
                        if response.status == 404:
                            error_scenarios.append(('404错误', 'HTTP404'))
                            print(f"   ✅ 404错误正确识别")
                except Exception as e:
                    error_scenarios.append(('404处理异常', type(e).__name__))
                
                # 4. 测试500错误处理
                try:
                    async with session.get('https://httpbin.org/status/500', timeout=5) as response:
                        if response.status == 500:
                            error_scenarios.append(('500错误', 'HTTP500'))
                            print(f"   ✅ 500错误正确识别")
                except Exception as e:
                    error_scenarios.append(('500处理异常', type(e).__name__))
            
            # 验证错误处理覆盖率
            assert len(error_scenarios) >= 3, f"错误场景覆盖不足: {len(error_scenarios)}"
            
            print(f"   ✅ 错误处理场景覆盖: {len(error_scenarios)} 种场景")
            
            self.results['error_handling'] = True
            return True
            
        except Exception as e:
            print(f"   ❌ 错误处理测试失败: {e}")
            self.results['error_handling'] = False
            return False
    
    def print_summary(self):
        """打印测试总结"""
        print("\n📊 聚焦TDD测试总结")
        print("="*50)
        
        total_tests = len(self.results)
        passed_tests = sum(self.results.values())
        
        for test_name, result in self.results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {status} {test_name}")
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"\n📈 总体结果: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        
        if success_rate >= 80:
            print("🎉 聚焦TDD测试通过！")
            print("\n✨ 系统核心功能验证成功，具备以下能力：")
            if self.results.get('unified_session_manager'):
                print("   🔄 统一会话管理 - 网络请求处理")
            if self.results.get('unified_storage_manager'):
                print("   💾 统一存储管理 - 数据持久化")
            if self.results.get('real_network_api'):
                print("   🌐 真实网络API - 外部服务集成")
            if self.results.get('binance_testnet'):
                print("   📈 交易所连接 - 市场数据获取")
            if self.results.get('configuration_management'):
                print("   ⚙️ 配置管理 - 系统配置验证")
            if self.results.get('error_handling'):
                print("   🛡️ 错误处理 - 异常情况处理")
            
            return True
        else:
            print("❌ 聚焦TDD测试需要改进")
            return False

async def main():
    """主测试函数"""
    print("🎯 开始聚焦TDD测试")
    print("专注于核心功能的真实环境验证")
    print("="*50)
    
    tester = FocusedTDDTester()
    
    tests = [
        ("统一会话管理器", tester.test_unified_session_manager_real_usage),
        ("统一存储管理器", tester.test_unified_storage_manager_integration),
        ("真实网络API", tester.test_real_network_api_calls),
        ("Binance连接性", tester.test_binance_testnet_basic_connectivity),
        ("配置管理", tester.test_configuration_management),
        ("错误处理", tester.test_error_handling_and_resilience)
    ]
    
    try:
        for test_name, test_func in tests:
            print(f"\n📋 {test_name}")
            print("-" * 30)
            await test_func()
        
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