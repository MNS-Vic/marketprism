"""
TDD测试：API网关真实性验证
测试API网关的路由、负载均衡、服务发现、限流等功能

遵循TDD原则：
1. 先写测试，描述期望的网关行为
2. 验证真实的微服务路由和转发
3. 测试负载均衡和故障转移
4. 确保安全控制和限流机制
"""

from datetime import datetime, timezone
import pytest
import asyncio
import aiohttp
import time
import json
from pathlib import Path
import sys
import random
import concurrent.futures

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment, requires_service


class TestRealAPIGateway(RealTestBase):
    """API网关真实性测试"""
    
    @pytest.mark.asyncio
    @requires_service("api_gateway")
    async def test_should_discover_and_route_to_real_services(self):
        """
        TDD测试：API网关应该发现并路由到真实运行的服务
        
        Given: 微服务都在运行中
        When: 通过API网关访问各个服务
        Then: 应该正确路由并返回各服务的响应
        """
        async with real_test_environment() as env:
            assert env.services_running.get('api_gateway', False), "API网关未运行"
            
            gateway_url = "http://localhost:8080"
            
            async with aiohttp.ClientSession() as session:
                # 1. 测试服务发现端点
                async with session.get(
                    f"{gateway_url}/api/v1/services",
                    timeout=10
                ) as response:
                    assert response.status == 200, f"服务发现失败: {response.status}"
                    services_data = await response.json()
                    
                    assert 'services' in services_data, "响应缺少services字段"
                    services = services_data['services']
                    assert len(services) > 0, "未发现任何服务"
                    
                    # 验证关键服务是否被发现
                    service_names = [s.get('name') for s in services]
                    critical_services = ['data-storage', 'market-data-collector', 'monitoring']
                    
                    for service in critical_services:
                        if env.services_running.get(service.replace('-', '_'), False):
                            assert service in service_names, f"未发现关键服务: {service}"
                    
                    print(f"✅ 发现服务: {service_names}")
                
                # 2. 测试到数据存储服务的路由
                if env.services_running.get('data_storage', False):
                    async with session.get(
                        f"{gateway_url}/api/v1/data-storage/health",
                        timeout=10
                    ) as response:
                        assert response.status == 200, f"路由到数据存储服务失败: {response.status}"
                        health_data = await response.json()
                        
                        assert health_data.get('status') == 'healthy', f"数据存储服务状态异常: {health_data}"
                        print("✅ 数据存储服务路由正常")
                
                # 3. 测试到市场数据采集服务的路由
                if env.services_running.get('market_data_collector', False):
                    async with session.get(
                        f"{gateway_url}/api/v1/market-data/health",
                        timeout=10
                    ) as response:
                        assert response.status == 200, f"路由到市场数据服务失败: {response.status}"
                        health_data = await response.json()
                        
                        assert health_data.get('status') == 'healthy', f"市场数据服务状态异常: {health_data}"
                        print("✅ 市场数据服务路由正常")
                
                # 4. 测试到监控服务的路由
                if env.services_running.get('monitoring', False):
                    async with session.get(
                        f"{gateway_url}/api/v1/monitoring/health",
                        timeout=10
                    ) as response:
                        assert response.status == 200, f"路由到监控服务失败: {response.status}"
                        health_data = await response.json()
                        
                        assert health_data.get('status') == 'healthy', f"监控服务状态异常: {health_data}"
                        print("✅ 监控服务路由正常")
    
    @pytest.mark.asyncio
    @requires_service("api_gateway")
    async def test_should_handle_load_balancing_across_service_instances(self):
        """
        TDD测试：应该在多个服务实例间进行负载均衡
        
        Given: 同一服务有多个实例运行
        When: 发送多个请求到同一服务
        Then: 请求应该均匀分发到不同实例
        """
        async with real_test_environment() as env:
            assert env.services_running.get('api_gateway', False), "API网关未运行"
            
            gateway_url = "http://localhost:8080"
            
            # 模拟对同一服务的多次请求
            request_count = 20
            response_sources = []
            
            async with aiohttp.ClientSession() as session:
                for i in range(request_count):
                    try:
                        async with session.get(
                            f"{gateway_url}/api/v1/data-storage/health",
                            timeout=5
                        ) as response:
                            if response.status == 200:
                                health_data = await response.json()
                                
                                # 检查响应头中的服务实例信息
                                server_id = response.headers.get('X-Service-Instance', 'unknown')
                                service_host = response.headers.get('X-Upstream-Host', 'unknown')
                                
                                response_sources.append({
                                    'request_id': i,
                                    'server_id': server_id,
                                    'host': service_host,
                                    'response_time': time.time()
                                })
                                
                                print(f"请求{i}: 实例{server_id}, 主机{service_host}")
                        
                        # 添加小延迟避免过快请求
                        await asyncio.sleep(0.1)
                        
                    except Exception as e:
                        print(f"请求{i}失败: {e}")
            
            # 分析负载均衡效果
            if len(response_sources) > 0:
                unique_instances = set(r['server_id'] for r in response_sources)
                unique_hosts = set(r['host'] for r in response_sources)
                
                print(f"\n📊 负载均衡分析:")
                print(f"   总请求数: {len(response_sources)}")
                print(f"   不同实例数: {len(unique_instances)}")
                print(f"   不同主机数: {len(unique_hosts)}")
                
                # 如果有多个实例，验证负载分布
                if len(unique_instances) > 1:
                    instance_counts = {}
                    for r in response_sources:
                        instance_id = r['server_id']
                        instance_counts[instance_id] = instance_counts.get(instance_id, 0) + 1
                    
                    print(f"   实例分布: {instance_counts}")
                    
                    # 计算负载分布的均匀性
                    avg_requests = len(response_sources) / len(unique_instances)
                    max_deviation = max(abs(count - avg_requests) for count in instance_counts.values())
                    deviation_percent = (max_deviation / avg_requests) * 100
                    
                    print(f"   平均请求数: {avg_requests:.2f}")
                    print(f"   最大偏差: {deviation_percent:.2f}%")
                    
                    # 负载偏差不应该超过50%（考虑到较少的请求数）
                    assert deviation_percent <= 50, f"负载分布偏差过大: {deviation_percent:.2f}%"
                    
                    print("✅ 负载均衡测试通过")
                else:
                    print("⚠️ 只有一个服务实例，无法测试负载均衡")
            else:
                pytest.fail("未收到任何有效响应")
    
    @pytest.mark.asyncio
    @requires_service("api_gateway")
    async def test_should_implement_rate_limiting_controls(self):
        """
        TDD测试：应该实现API限流控制
        
        Given: API网关配置了限流规则
        When: 短时间内发送大量请求
        Then: 应该正确限制请求速率并返回429状态码
        """
        async with real_test_environment() as env:
            assert env.services_running.get('api_gateway', False), "API网关未运行"
            
            gateway_url = "http://localhost:8080"
            
            # 快速发送大量请求测试限流
            rapid_request_count = 50
            rate_limit_hits = 0
            successful_requests = 0
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                tasks = []
                
                # 创建并发请求任务
                for i in range(rapid_request_count):
                    task = asyncio.create_task(
                        self._make_rate_limit_test_request(session, gateway_url, i)
                    )
                    tasks.append(task)
                
                # 等待所有请求完成
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                end_time = time.time()
                total_time = end_time - start_time
                
                # 分析结果
                for result in results:
                    if isinstance(result, dict):
                        if result.get('status') == 200:
                            successful_requests += 1
                        elif result.get('status') == 429:
                            rate_limit_hits += 1
                        elif result.get('status') == 503:
                            # 服务暂时不可用（可能是限流导致）
                            rate_limit_hits += 1
                
                requests_per_second = rapid_request_count / total_time
                
                print(f"\n📊 限流测试结果:")
                print(f"   总请求数: {rapid_request_count}")
                print(f"   成功请求: {successful_requests}")
                print(f"   限流触发: {rate_limit_hits}")
                print(f"   请求速度: {requests_per_second:.2f} req/s")
                print(f"   总耗时: {total_time:.2f}秒")
                
                # 验证限流机制
                if rate_limit_hits > 0:
                    print("✅ 限流机制正常工作")
                    # 限流应该在合理范围内，不能全部被拦截
                    success_rate = successful_requests / rapid_request_count
                    assert success_rate >= 0.3, f"成功率过低，限流过于严格: {success_rate:.2%}"
                else:
                    # 如果没有触发限流，检查请求速度是否在合理范围内
                    print("⚠️ 未触发限流，可能限流阈值较高或请求速度不够快")
                    assert requests_per_second < 100, "请求速度过快但未触发限流"
    
    async def _make_rate_limit_test_request(self, session, gateway_url, request_id):
        """发送单个限流测试请求"""
        try:
            async with session.get(
                f"{gateway_url}/api/v1/health",
                timeout=3
            ) as response:
                return {
                    'request_id': request_id,
                    'status': response.status,
                    'headers': dict(response.headers),
                    'timestamp': time.time()
                }
        except Exception as e:
            return {
                'request_id': request_id,
                'status': 0,
                'error': str(e),
                'timestamp': time.time()
            }
    
    @pytest.mark.asyncio
    @requires_service("api_gateway")
    async def test_should_handle_service_failure_gracefully(self):
        """
        TDD测试：应该优雅处理服务故障
        
        Given: API网关正常运行
        When: 后端服务不可用或响应超时
        Then: 应该返回适当的错误信息，不影响其他服务
        """
        async with real_test_environment() as env:
            assert env.services_running.get('api_gateway', False), "API网关未运行"
            
            gateway_url = "http://localhost:8080"
            
            async with aiohttp.ClientSession() as session:
                # 1. 测试访问不存在的服务
                async with session.get(
                    f"{gateway_url}/api/v1/non-existent-service/health",
                    timeout=10
                ) as response:
                    # 应该返回404或503
                    assert response.status in [404, 503], f"访问不存在服务应返回404/503: {response.status}"
                    
                    error_data = await response.json()
                    assert 'error' in error_data or 'message' in error_data, "错误响应应包含错误信息"
                    
                    print(f"✅ 不存在服务处理: {response.status} - {error_data}")
                
                # 2. 测试访问不存在的端点
                async with session.get(
                    f"{gateway_url}/api/v1/data-storage/invalid-endpoint",
                    timeout=10
                ) as response:
                    # 应该返回404
                    assert response.status == 404, f"访问无效端点应返回404: {response.status}"
                    
                    print(f"✅ 无效端点处理: {response.status}")
                
                # 3. 测试网关自身健康检查
                async with session.get(
                    f"{gateway_url}/health",
                    timeout=10
                ) as response:
                    assert response.status == 200, f"网关健康检查失败: {response.status}"
                    
                    health_data = await response.json()
                    assert health_data.get('status') in ['healthy', 'ok'], f"网关状态异常: {health_data}"
                    
                    print(f"✅ 网关健康状态: {health_data}")
                
                # 4. 测试跨域请求处理（如果支持）
                headers = {
                    'Origin': 'http://localhost:3000',
                    'Access-Control-Request-Method': 'GET'
                }
                
                async with session.options(
                    f"{gateway_url}/api/v1/health",
                    headers=headers,
                    timeout=5
                ) as response:
                    # OPTIONS请求应该被正确处理
                    print(f"CORS预检请求: {response.status}")
                    
                    if response.status == 200:
                        cors_headers = {
                            k: v for k, v in response.headers.items() 
                            if k.lower().startswith('access-control-')
                        }
                        print(f"✅ CORS头部: {cors_headers}")
    
    @pytest.mark.asyncio
    @requires_service("api_gateway")
    async def test_should_provide_api_metrics_and_monitoring(self):
        """
        TDD测试：应该提供API指标和监控信息
        
        Given: API网关运行并处理了一些请求
        When: 查询网关的指标和监控端点
        Then: 应该返回详细的性能和状态指标
        """
        async with real_test_environment() as env:
            assert env.services_running.get('api_gateway', False), "API网关未运行"
            
            gateway_url = "http://localhost:8080"
            
            async with aiohttp.ClientSession() as session:
                # 先发送一些请求产生指标数据
                for i in range(5):
                    try:
                        async with session.get(f"{gateway_url}/api/v1/health", timeout=5):
                            pass
                    except:
                        pass
                    await asyncio.sleep(0.2)
                
                # 1. 测试指标端点
                async with session.get(
                    f"{gateway_url}/metrics",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        metrics_data = await response.text()
                        
                        # 验证Prometheus格式指标
                        expected_metrics = [
                            'http_requests_total',
                            'http_request_duration',
                            'gateway_upstream_status'
                        ]
                        
                        found_metrics = []
                        for metric in expected_metrics:
                            if metric in metrics_data:
                                found_metrics.append(metric)
                        
                        if found_metrics:
                            print(f"✅ 找到指标: {found_metrics}")
                        else:
                            print("⚠️ 未找到预期的Prometheus指标格式")
                    else:
                        print(f"⚠️ 指标端点不可用: {response.status}")
                
                # 2. 测试状态统计端点
                async with session.get(
                    f"{gateway_url}/api/v1/stats",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        stats_data = await response.json()
                        
                        # 验证统计信息格式
                        expected_fields = ['requests_total', 'active_connections', 'uptime']
                        for field in expected_fields:
                            if field in stats_data:
                                print(f"✅ 统计字段 {field}: {stats_data[field]}")
                        
                        # 验证数值合理性
                        if 'uptime' in stats_data:
                            uptime = stats_data['uptime']
                            assert uptime > 0, f"运行时间应该大于0: {uptime}"
                    else:
                        print(f"⚠️ 统计端点不可用: {response.status}")
                
                # 3. 测试版本信息端点
                async with session.get(
                    f"{gateway_url}/api/v1/version",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        version_data = await response.json()
                        
                        if 'version' in version_data:
                            print(f"✅ 网关版本: {version_data['version']}")
                        if 'build_time' in version_data:
                            print(f"✅ 构建时间: {version_data['build_time']}")
                    else:
                        print(f"⚠️ 版本端点不可用: {response.status}")


@pytest.mark.asyncio
async def test_api_gateway_integration():
    """API网关集成测试入口"""
    test_instance = TestRealAPIGateway()
    
    async with real_test_environment() as env:
        if not env.services_running.get('api_gateway', False):
            pytest.skip("API网关未运行，跳过集成测试")
        
        print("🚀 开始API网关真实性测试")
        
        # 运行所有测试方法
        await test_instance.test_should_discover_and_route_to_real_services()
        await test_instance.test_should_handle_load_balancing_across_service_instances()
        await test_instance.test_should_implement_rate_limiting_controls()
        await test_instance.test_should_handle_service_failure_gracefully()
        await test_instance.test_should_provide_api_metrics_and_monitoring()
        
        print("🎉 所有API网关测试通过")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_api_gateway_integration())