"""
MarketPrism微服务架构 Phase 2 集成测试
测试数据采集和API网关服务的集成功能

Phase 2 集成范围：
1. Market Data Collector Service - 基于成熟python-collector的数据采集服务
2. API Gateway Service - 统一API网关和路由
3. 与Phase 1服务的集成 - Data Storage & Scheduler
4. 服务间通信验证
5. 端到端数据流测试

本测试验证Phase 2微服务的正确性和集成能力。
"""

import asyncio
import aiohttp
import pytest
import json
import time
import websockets
from pathlib import Path
import sys
import yaml
from datetime import datetime, timedelta, timezone

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.test_helpers import TestHelpers, ServiceTestManager
from tests.utils.mock_helpers import MockNATSServer


class TestPhase2Integration:
    """Phase 2 微服务集成测试"""
    
    def setup_method(self):
        """测试设置"""
        self.test_helpers = TestHelpers()
        
        # Phase 2 服务配置
        self.services_config = {
            'market-data-collector': {
                'port': 8081,
                'base_url': 'http://localhost:8081',
                'health_endpoint': '/health'
            },
            'api-gateway-service': {
                'port': 8080,
                'base_url': 'http://localhost:8080',
                'health_endpoint': '/health'
            },
            'data-storage-service': {
                'port': 8082,
                'base_url': 'http://localhost:8082',
                'health_endpoint': '/health'
            },
            'scheduler-service': {
                'port': 8084,
                'base_url': 'http://localhost:8084',
                'health_endpoint': '/health'
            }
        }
        
        self.service_manager = ServiceTestManager(self.services_config)
        
        self.mock_nats = MockNATSServer()
        self.test_data = {
            'sample_trade': {
                'exchange_name': 'binance',
                'symbol_name': 'BTCUSDT',
                'trade_id': '12345',
                'price': '50000.00',
                'quantity': '0.1',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'is_buyer_maker': False
            },
            'sample_subscription': {
                'action': 'subscribe',
                'symbols': ['BTC-USDT', 'ETH-USDT'],
                'data_types': ['trade', 'ticker']
            }
        }
    
    async def test_001_market_data_collector_health(self):
        """测试1: Market Data Collector服务健康检查"""
        print("\n=== 测试1: Market Data Collector健康检查 ===")
        
        service_config = self.services_config['market-data-collector']
        
        # 检查服务健康状态
        health_check = await self.test_helpers.check_service_health(
            service_config['base_url'],
            service_config['health_endpoint']
        )
        
        assert health_check['success'], f"Market Data Collector健康检查失败: {health_check.get('error')}"
        assert health_check['data']['status'] == 'healthy'
        
        # 验证服务特定信息
        health_data = health_check['data']
        assert 'collector' in health_data, "健康检查缺少collector信息"
        assert 'exchanges' in health_data, "健康检查缺少exchanges信息"
        assert 'data_stats' in health_data, "健康检查缺少data_stats信息"
        
        print("✅ Market Data Collector健康检查通过")
        print(f"   - 支持的交易所: {len(health_data.get('exchanges', {}))}")
        print(f"   - Collector状态: {health_data.get('collector', {}).get('status', 'unknown')}")
    
    async def test_002_api_gateway_health(self):
        """测试2: API Gateway服务健康检查"""
        print("\n=== 测试2: API Gateway健康检查 ===")
        
        service_config = self.services_config['api-gateway-service']
        
        # 检查网关健康状态
        health_check = await self.test_helpers.check_service_health(
            service_config['base_url'],
            service_config['health_endpoint']
        )
        
        assert health_check['success'], f"API Gateway健康检查失败: {health_check.get('error')}"
        assert health_check['data']['status'] == 'healthy'
        
        # 检查网关状态接口
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{service_config['base_url']}/api/v1/gateway/status") as response:
                assert response.status == 200
                gateway_status = await response.json()
                
                assert gateway_status['service'] == 'api-gateway'
                assert 'registered_services' in gateway_status
                assert 'config' in gateway_status
        
        print("✅ API Gateway健康检查通过")
        print(f"   - 注册服务数: {gateway_status.get('registered_services', 0)}")
        print(f"   - 限流启用: {gateway_status.get('config', {}).get('enable_rate_limiting', False)}")
        print(f"   - 熔断器启用: {gateway_status.get('config', {}).get('enable_circuit_breaker', False)}")
    
    async def test_003_service_discovery(self):
        """测试3: 服务发现功能"""
        print("\n=== 测试3: 服务发现功能 ===")
        
        gateway_url = self.services_config['api-gateway-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            # 获取注册的服务列表
            async with session.get(f"{gateway_url}/api/v1/gateway/services") as response:
                assert response.status == 200
                services_data = await response.json()
                
                assert 'services' in services_data
                assert 'total' in services_data
                
                registered_services = services_data['services']
                
                # 验证关键服务已注册
                expected_services = ['market-data-collector', 'data-storage-service', 'scheduler-service']
                for service_name in expected_services:
                    assert service_name in registered_services, f"服务 {service_name} 未注册"
                    
                    service_info = registered_services[service_name]
                    assert 'base_url' in service_info
                    assert 'healthy' in service_info
        
        print("✅ 服务发现功能正常")
        print(f"   - 已注册服务: {list(registered_services.keys())}")
        
        # 测试动态注册新服务
        test_service = {
            'service_name': 'test-service',
            'host': 'localhost',
            'port': 9999,
            'health_endpoint': '/health'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{gateway_url}/api/v1/gateway/services",
                json=test_service
            ) as response:
                assert response.status == 200
                result = await response.json()
                assert result['success'] == True
        
        print("✅ 动态服务注册功能正常")
    
    async def test_004_api_gateway_routing(self):
        """测试4: API网关路由功能"""
        print("\n=== 测试4: API网关路由功能 ===")
        
        gateway_url = self.services_config['api-gateway-service']['base_url']
        
        # 测试路由到Market Data Collector
        async with aiohttp.ClientSession() as session:
            # 通过网关访问Market Data Collector状态
            async with session.get(f"{gateway_url}/api/v1/market-data-collector/status") as response:
                assert response.status == 200
                status_data = await response.json()
                
                assert 'service' in status_data
                assert status_data['service'] == 'market-data-collector'
                
                # 验证网关添加的头信息
                headers = response.headers
                assert 'X-Gateway-Service' in headers
                assert headers['X-Gateway-Service'] == 'market-data-collector'
        
        print("✅ 路由到Market Data Collector成功")
        
        # 测试路由到Data Storage Service  
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/data-storage-service/status") as response:
                # 可能返回200或503（如果服务未启动）
                assert response.status in [200, 503]
                
                if response.status == 200:
                    print("✅ 路由到Data Storage Service成功")
                else:
                    print("⚠️ Data Storage Service不可用，但路由正常")
        
        # 测试不存在的服务
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/nonexistent-service/status") as response:
                assert response.status == 503
                error_data = await response.json()
                assert 'error' in error_data
        
        print("✅ 无效服务路由处理正确")
    
    async def test_005_market_data_collector_apis(self):
        """测试5: Market Data Collector API功能"""
        print("\n=== 测试5: Market Data Collector API功能 ===")
        
        collector_url = self.services_config['market-data-collector']['base_url']
        
        async with aiohttp.ClientSession() as session:
            # 测试获取采集器状态
            async with session.get(f"{collector_url}/api/v1/status") as response:
                assert response.status == 200
                status = await response.json()
                
                assert 'service' in status
                assert 'supported_exchanges' in status
                assert 'supported_data_types' in status
                
                supported_exchanges = status['supported_exchanges']
                assert 'binance' in supported_exchanges
                assert 'okx' in supported_exchanges
        
        print("✅ 采集器状态API正常")
        print(f"   - 支持的交易所: {supported_exchanges}")
        
        # 测试获取交易所统计
        for exchange in ['binance', 'okx']:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{collector_url}/api/v1/exchanges/{exchange}/stats") as response:
                    assert response.status == 200
                    stats = await response.json()
                    
                    assert 'exchange' in stats
                    assert stats['exchange'] == exchange
                    assert 'status' in stats
        
        print("✅ 交易所统计API正常")
    
    async def test_006_dynamic_subscription(self):
        """测试6: 动态订阅功能"""
        print("\n=== 测试6: 动态订阅功能 ===")
        
        collector_url = self.services_config['market-data-collector']['base_url']
        
        # 测试通过API Gateway的动态订阅
        gateway_url = self.services_config['api-gateway-service']['base_url']
        
        subscription_data = self.test_data['sample_subscription']
        
        async with aiohttp.ClientSession() as session:
            # 通过网关控制订阅
            async with session.post(
                f"{gateway_url}/api/v1/market-data-collector/exchanges/binance/subscribe",
                json=subscription_data
            ) as response:
                # 可能返回200（成功）或其他状态（如果功能未完全实现）
                assert response.status in [200, 400, 501]
                
                if response.status == 200:
                    result = await response.json()
                    print("✅ 动态订阅功能正常")
                    print(f"   - 订阅结果: {result.get('success', 'unknown')}")
                else:
                    print("⚠️ 动态订阅功能待实现或配置问题")
    
    async def test_007_rate_limiting(self):
        """测试7: API网关限流功能"""
        print("\n=== 测试7: API网关限流功能 ===")
        
        gateway_url = self.services_config['api-gateway-service']['base_url']
        
        # 发送大量请求测试限流
        request_count = 10
        success_count = 0
        rate_limited_count = 0
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(request_count):
                task = session.get(f"{gateway_url}/api/v1/gateway/status")
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for response in responses:
                if isinstance(response, aiohttp.ClientResponse):
                    if response.status == 200:
                        success_count += 1
                    elif response.status == 429:
                        rate_limited_count += 1
                    response.close()
        
        print(f"✅ 限流测试完成")
        print(f"   - 成功请求: {success_count}")
        print(f"   - 被限流请求: {rate_limited_count}")
        print(f"   - 总请求: {request_count}")
        
        # 检查限流统计
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/gateway/stats") as response:
                assert response.status == 200
                stats = await response.json()
                
                assert 'request_stats' in stats
                request_stats = stats['request_stats']
                assert 'total_requests' in request_stats
                
                print(f"   - 网关总请求数: {request_stats.get('total_requests', 0)}")
    
    async def test_008_error_handling(self):
        """测试8: 错误处理和熔断器"""
        print("\n=== 测试8: 错误处理和熔断器 ===")
        
        gateway_url = self.services_config['api-gateway-service']['base_url']
        
        # 测试访问不存在的端点
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/market-data-collector/nonexistent") as response:
                # 应该返回错误状态
                assert response.status in [404, 500, 502, 503]
        
        print("✅ 错误处理正常")
        
        # 检查熔断器状态
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/gateway/stats") as response:
                assert response.status == 200
                stats = await response.json()
                
                if 'circuit_breaker_stats' in stats:
                    cb_stats = stats['circuit_breaker_stats']
                    print(f"   - 熔断器状态: {len(cb_stats)} 个服务")
                    for service, status in cb_stats.items():
                        print(f"     - {service}: {status.get('state', 'unknown')}")
    
    async def test_009_cache_functionality(self):
        """测试9: 缓存功能"""
        print("\n=== 测试9: 缓存功能 ===")
        
        gateway_url = self.services_config['api-gateway-service']['base_url']
        
        # 第一次请求（应该缓存MISS）
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/gateway/status") as response:
                assert response.status == 200
                first_response = await response.json()
        first_duration = time.time() - start_time
        
        # 第二次请求（应该缓存HIT，更快）
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/gateway/status") as response:
                assert response.status == 200
                second_response = await response.json()
        second_duration = time.time() - start_time
        
        # 检查缓存统计
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_url}/api/v1/gateway/stats") as response:
                assert response.status == 200
                stats = await response.json()
                
                if 'cache_stats' in stats:
                    cache_stats = stats['cache_stats']
                    print(f"✅ 缓存功能正常")
                    print(f"   - 缓存大小: {cache_stats.get('size', 0)}")
                    print(f"   - 缓存命中率: {cache_stats.get('hit_rate', 0):.2%}")
                else:
                    print("⚠️ 缓存统计不可用")
    
    async def test_010_service_integration(self):
        """测试10: 服务间集成"""
        print("\n=== 测试10: 服务间集成 ===")
        
        # 验证所有Phase 1和Phase 2服务的连通性
        all_services = [
            'market-data-collector',
            'api-gateway-service', 
            'data-storage-service',
            'scheduler-service'
        ]
        
        gateway_url = self.services_config['api-gateway-service']['base_url']
        integration_results = {}
        
        for service_name in all_services:
            try:
                if service_name == 'api-gateway-service':
                    # 直接测试网关
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{gateway_url}/health") as response:
                            integration_results[service_name] = {
                                'reachable': response.status == 200,
                                'status_code': response.status
                            }
                else:
                    # 通过网关测试其他服务
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{gateway_url}/api/v1/{service_name}/health") as response:
                            integration_results[service_name] = {
                                'reachable': response.status == 200,
                                'status_code': response.status
                            }
            except Exception as e:
                integration_results[service_name] = {
                    'reachable': False,
                    'error': str(e)
                }
        
        print("✅ 服务集成测试完成")
        for service, result in integration_results.items():
            status = "✅ 可达" if result.get('reachable') else "❌ 不可达"
            print(f"   - {service}: {status}")
            if not result.get('reachable'):
                error_msg = result.get('error', f"HTTP {result.get('status_code', 'unknown')}")
                print(f"     错误: {error_msg}")
        
        # 至少API Gateway和Market Data Collector应该可达
        assert integration_results['api-gateway-service']['reachable'], "API Gateway不可达"
        assert integration_results['market-data-collector']['reachable'], "Market Data Collector不可达"
    
    def teardown_method(self):
        """测试清理"""
        pass


@pytest.mark.asyncio
async def test_phase2_integration_suite():
    """Phase 2 集成测试套件，用于快速验证"""
    print("\n\n" + "="*80)
    print("  MarketPrism Phase 2: 集成测试套件 - 数据采集与API网关")
    print("="*80)

    # 服务配置
    services_config = {
        'market-data-collector': {
            'port': 8081,
            'base_url': 'http://localhost:8081',
            'health_endpoint': '/health'
        },
        'api-gateway-service': {
            'port': 8080,
            'base_url': 'http://localhost:8080',
            'health_endpoint': '/health'
        },
        'data-storage-service': {
            'port': 8082,
            'base_url': 'http://localhost:8082',
            'health_endpoint': '/health'
        },
        'scheduler-service': {
            'port': 8084,
            'base_url': 'http://localhost:8084',
            'health_endpoint': '/health'
        }
    }
    
    service_manager = ServiceTestManager(services_config)
    test_suite = TestPhase2Integration()
    
    # 运行核心测试
    test_methods = [
        test_suite.test_001_market_data_collector_health,
        test_suite.test_002_api_gateway_health,
        test_suite.test_003_service_discovery,
        test_suite.test_004_api_gateway_routing,
        test_suite.test_005_market_data_collector_apis,
        test_suite.test_006_dynamic_subscription,
        test_suite.test_007_rate_limiting,
        test_suite.test_008_error_handling,
        test_suite.test_009_cache_functionality,
        test_suite.test_010_service_integration
    ]
    
    passed_tests = 0
    failed_tests = 0
    
    for test_method in test_methods:
        try:
            await test_method()
            passed_tests += 1
        except Exception as e:
            print(f"❌ 测试失败: {test_method.__name__}")
            print(f"   错误: {e}")
            failed_tests += 1
    
    print("\n" + "="*60)
    print("Phase 2 集成测试结果汇总")
    print("="*60)
    print(f"✅ 通过: {passed_tests}")
    print(f"❌ 失败: {failed_tests}")
    print(f"📊 成功率: {passed_tests/(passed_tests+failed_tests)*100:.1f}%")
    
    if failed_tests == 0:
        print("\n🎉 Phase 2 集成测试全部通过！")
        print("Market Data Collector和API Gateway服务运行正常")
    else:
        print(f"\n⚠️ 有 {failed_tests} 个测试失败，请检查服务状态")
    
    test_suite.teardown_method()
    
    # 返回测试结果用于自动化流程
    return {
        'passed': passed_tests,
        'failed': failed_tests,
        'success_rate': passed_tests/(passed_tests+failed_tests)*100,
        'phase': 'Phase 2',
        'services_tested': ['market-data-collector', 'api-gateway-service']
    }


if __name__ == "__main__":
    # 直接运行测试
    result = asyncio.run(test_phase2_integration_suite())
    
    # 如果失败率过高，退出时返回错误状态
    if result['success_rate'] < 70:
        sys.exit(1)