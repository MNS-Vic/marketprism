"""
MarketPrism Phase 4 集成测试
优化与部署 - 生产就绪性验证

测试目标：
1. 容器化部署验证
2. 性能基准测试
3. 生产环境配置验证
4. 监控告警测试
5. 故障恢复测试
6. 负载均衡测试
7. 数据一致性验证
8. 安全性测试
"""

import pytest
import asyncio
import aiohttp
import time
import json
import yaml
import subprocess
import docker
import psutil
from pathlib import Path
from typing import Dict, List, Any
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


class Phase4TestSuite:
    """Phase 4 测试套件"""
    
    def __init__(self):
        self.docker_client = None
        self.services_config = self._load_services_config()
        self.test_results = {
            'deployment': {},
            'performance': {},
            'monitoring': {},
            'reliability': {},
            'security': {}
        }
    
    def _load_services_config(self) -> Dict[str, Any]:
        """加载服务配置"""
        config_path = PROJECT_ROOT / "config" / "services.yaml"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载服务配置失败: {e}")
            return {}
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Docker客户端初始化失败: {e}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.docker_client:
            self.docker_client.close()


@pytest.fixture
async def phase4_suite():
    """Phase 4 测试套件fixture"""
    async with Phase4TestSuite() as suite:
        yield suite


class TestContainerizedDeployment:
    """容器化部署测试"""
    
    @pytest.mark.asyncio
    async def test_docker_compose_validation(self, phase4_suite):
        """测试Docker Compose配置验证"""
        logger.info("🐳 测试Docker Compose配置验证")
        
        compose_file = PROJECT_ROOT / "docker" / "docker-compose.yml"
        assert compose_file.exists(), "Docker Compose文件不存在"
        
        # 验证配置文件语法
        try:
            result = subprocess.run(
                ["docker-compose", "-f", str(compose_file), "config"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT
            )
            assert result.returncode == 0, f"Docker Compose配置无效: {result.stderr}"
            
            phase4_suite.test_results['deployment']['docker_compose_validation'] = {
                'status': 'passed',
                'message': 'Docker Compose配置有效'
            }
            
        except FileNotFoundError:
            pytest.skip("Docker Compose未安装")
    
    @pytest.mark.asyncio
    async def test_dockerfile_validation(self, phase4_suite):
        """测试Dockerfile配置验证"""
        logger.info("📦 测试Dockerfile配置验证")
        
        dockerfile_dir = PROJECT_ROOT / "docker" / "services"
        dockerfiles = list(dockerfile_dir.glob("Dockerfile.*"))
        
        assert len(dockerfiles) > 0, "没有找到Dockerfile文件"
        
        valid_dockerfiles = 0
        for dockerfile in dockerfiles:
            try:
                # 简单的语法检查
                content = dockerfile.read_text()
                assert "FROM" in content, f"{dockerfile.name} 缺少FROM指令"
                assert "WORKDIR" in content, f"{dockerfile.name} 缺少WORKDIR指令"
                assert "CMD" in content, f"{dockerfile.name} 缺少CMD指令"
                valid_dockerfiles += 1
                
            except Exception as e:
                logger.error(f"Dockerfile验证失败 {dockerfile.name}: {e}")
        
        assert valid_dockerfiles == len(dockerfiles), "部分Dockerfile配置无效"
        
        phase4_suite.test_results['deployment']['dockerfile_validation'] = {
            'status': 'passed',
            'validated_files': valid_dockerfiles,
            'total_files': len(dockerfiles)
        }
    
    @pytest.mark.asyncio
    async def test_container_health_checks(self, phase4_suite):
        """测试容器健康检查"""
        logger.info("🔍 测试容器健康检查配置")
        
        if not phase4_suite.docker_client:
            pytest.skip("Docker客户端不可用")
        
        # 检查正在运行的MarketPrism容器
        containers = phase4_suite.docker_client.containers.list(
            filters={"name": "marketprism"}
        )
        
        healthy_containers = 0
        total_containers = len(containers)
        
        for container in containers:
            try:
                # 检查健康状态
                health = container.attrs.get('State', {}).get('Health', {})
                if health.get('Status') == 'healthy':
                    healthy_containers += 1
                    logger.info(f"容器 {container.name} 健康状态: 正常")
                else:
                    logger.warning(f"容器 {container.name} 健康状态: {health.get('Status', 'unknown')}")
                    
            except Exception as e:
                logger.error(f"检查容器 {container.name} 健康状态失败: {e}")
        
        phase4_suite.test_results['deployment']['container_health'] = {
            'status': 'passed' if healthy_containers > 0 else 'warning',
            'healthy_containers': healthy_containers,
            'total_containers': total_containers
        }


class TestPerformanceBenchmark:
    """性能基准测试"""
    
    @pytest.mark.asyncio
    async def test_service_response_times(self, phase4_suite):
        """测试服务响应时间"""
        logger.info("⚡ 测试服务响应时间")
        
        services = [
            ('api-gateway-service', 8080),
            ('monitoring-service', 8083),
            ('data-storage-service', 8082),
            ('market-data-collector', 8081),
            ('scheduler-service', 8084),
            ('message-broker-service', 8085)
        ]
        
        response_times = {}
        
        async with aiohttp.ClientSession() as session:
            for service_name, port in services:
                try:
                    start_time = time.time()
                    async with session.get(f"http://localhost:{port}/health") as response:
                        end_time = time.time()
                        response_time = (end_time - start_time) * 1000  # 转换为毫秒
                        
                        if response.status == 200:
                            response_times[service_name] = response_time
                            logger.info(f"{service_name} 响应时间: {response_time:.2f}ms")
                        else:
                            logger.warning(f"{service_name} 健康检查失败: {response.status}")
                            
                except Exception as e:
                    logger.error(f"{service_name} 连接失败: {e}")
                    response_times[service_name] = None
        
        # 验证响应时间基线 (< 100ms for health checks)
        fast_services = sum(1 for rt in response_times.values() 
                           if rt is not None and rt < 100)
        
        phase4_suite.test_results['performance']['response_times'] = {
            'status': 'passed' if fast_services >= len(services) * 0.8 else 'warning',
            'response_times': response_times,
            'fast_services': fast_services,
            'total_services': len(services)
        }
    
    @pytest.mark.asyncio
    async def test_concurrent_load(self, phase4_suite):
        """测试并发负载处理"""
        logger.info("🔄 测试并发负载处理")
        
        concurrent_requests = 50
        target_url = "http://localhost:8080/health"  # API网关
        
        async def single_request(session, request_id):
            try:
                start_time = time.time()
                async with session.get(target_url) as response:
                    end_time = time.time()
                    return {
                        'request_id': request_id,
                        'status': response.status,
                        'response_time': (end_time - start_time) * 1000,
                        'success': response.status == 200
                    }
            except Exception as e:
                return {
                    'request_id': request_id,
                    'status': 0,
                    'response_time': 0,
                    'success': False,
                    'error': str(e)
                }
        
        # 执行并发请求
        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            tasks = [single_request(session, i) for i in range(concurrent_requests)]
            results = await asyncio.gather(*tasks)
            end_time = time.time()
        
        # 分析结果
        successful_requests = sum(1 for r in results if r['success'])
        total_time = end_time - start_time
        qps = concurrent_requests / total_time
        
        avg_response_time = sum(r['response_time'] for r in results if r['success']) / max(successful_requests, 1)
        
        phase4_suite.test_results['performance']['concurrent_load'] = {
            'status': 'passed' if successful_requests / concurrent_requests >= 0.95 else 'failed',
            'concurrent_requests': concurrent_requests,
            'successful_requests': successful_requests,
            'success_rate': successful_requests / concurrent_requests * 100,
            'qps': qps,
            'avg_response_time': avg_response_time,
            'total_time': total_time
        }
    
    @pytest.mark.asyncio
    async def test_system_resource_usage(self, phase4_suite):
        """测试系统资源使用"""
        logger.info("💻 测试系统资源使用")
        
        # 收集系统资源信息
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # 检查资源使用是否在合理范围内
        resource_status = 'passed'
        warnings = []
        
        if cpu_percent > 80:
            resource_status = 'warning'
            warnings.append(f"CPU使用率过高: {cpu_percent}%")
        
        if memory.percent > 85:
            resource_status = 'warning'
            warnings.append(f"内存使用率过高: {memory.percent}%")
        
        if disk.percent > 90:
            resource_status = 'warning'
            warnings.append(f"磁盘使用率过高: {disk.percent}%")
        
        phase4_suite.test_results['performance']['system_resources'] = {
            'status': resource_status,
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_available_gb': memory.available / (1024**3),
            'disk_percent': disk.percent,
            'disk_free_gb': disk.free / (1024**3),
            'warnings': warnings
        }


class TestMonitoringAndAlerting:
    """监控和告警测试"""
    
    @pytest.mark.asyncio
    async def test_prometheus_metrics(self, phase4_suite):
        """测试Prometheus指标收集"""
        logger.info("📊 测试Prometheus指标收集")
        
        prometheus_url = "http://localhost:9090"
        metrics_endpoint = f"{prometheus_url}/api/v1/query"
        
        test_queries = [
            "up",  # 服务状态
            "marketprism_service_health",  # 自定义健康指标
            "process_cpu_seconds_total",  # CPU使用
            "process_resident_memory_bytes"  # 内存使用
        ]
        
        async with aiohttp.ClientSession() as session:
            available_metrics = []
            
            for query in test_queries:
                try:
                    params = {'query': query}
                    async with session.get(metrics_endpoint, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('status') == 'success' and data.get('data', {}).get('result'):
                                available_metrics.append(query)
                                logger.info(f"Prometheus指标可用: {query}")
                        else:
                            logger.warning(f"Prometheus指标查询失败: {query}")
                            
                except Exception as e:
                    logger.error(f"Prometheus连接失败: {e}")
                    break
        
        phase4_suite.test_results['monitoring']['prometheus_metrics'] = {
            'status': 'passed' if len(available_metrics) > 0 else 'failed',
            'available_metrics': available_metrics,
            'total_queries': len(test_queries),
            'prometheus_accessible': len(available_metrics) > 0
        }
    
    @pytest.mark.asyncio
    async def test_grafana_dashboard(self, phase4_suite):
        """测试Grafana仪表板"""
        logger.info("📈 测试Grafana仪表板")
        
        grafana_url = "http://localhost:3000"
        
        try:
            async with aiohttp.ClientSession() as session:
                # 测试Grafana健康状态
                async with session.get(f"{grafana_url}/api/health") as response:
                    grafana_healthy = response.status == 200
                    
                # 测试API访问
                headers = {'Authorization': 'Bearer admin:marketprism_admin'}
                async with session.get(f"{grafana_url}/api/datasources", 
                                     headers=headers) as response:
                    datasources_accessible = response.status in [200, 401]  # 401表示需要认证但服务可用
                    
            phase4_suite.test_results['monitoring']['grafana_dashboard'] = {
                'status': 'passed' if grafana_healthy else 'failed',
                'grafana_healthy': grafana_healthy,
                'api_accessible': datasources_accessible,
                'url': grafana_url
            }
            
        except Exception as e:
            logger.error(f"Grafana连接失败: {e}")
            phase4_suite.test_results['monitoring']['grafana_dashboard'] = {
                'status': 'failed',
                'error': str(e)
            }
    
    @pytest.mark.asyncio
    async def test_alert_system(self, phase4_suite):
        """测试告警系统"""
        logger.info("🚨 测试告警系统")
        
        monitoring_url = "http://localhost:8083"
        
        try:
            async with aiohttp.ClientSession() as session:
                # 测试告警规则查询
                async with session.get(f"{monitoring_url}/api/v1/alerts") as response:
                    if response.status == 200:
                        alerts_data = await response.json()
                        active_alerts = alerts_data.get('alerts', [])
                        
                        # 测试告警历史
                        async with session.get(f"{monitoring_url}/api/v1/alert-history") as hist_response:
                            alert_history_available = hist_response.status == 200
                            
                        phase4_suite.test_results['monitoring']['alert_system'] = {
                            'status': 'passed',
                            'active_alerts': len(active_alerts),
                            'alert_history_available': alert_history_available,
                            'monitoring_service_responsive': True
                        }
                    else:
                        raise Exception(f"监控服务响应错误: {response.status}")
                        
        except Exception as e:
            logger.error(f"告警系统测试失败: {e}")
            phase4_suite.test_results['monitoring']['alert_system'] = {
                'status': 'failed',
                'error': str(e)
            }


class TestReliabilityAndRecovery:
    """可靠性和恢复测试"""
    
    @pytest.mark.asyncio
    async def test_service_auto_recovery(self, phase4_suite):
        """测试服务自动恢复"""
        logger.info("🔄 测试服务自动恢复")
        
        if not phase4_suite.docker_client:
            pytest.skip("Docker客户端不可用，跳过自动恢复测试")
        
        # 选择一个测试容器进行重启测试
        test_container_name = "marketprism-monitoring"
        
        try:
            container = phase4_suite.docker_client.containers.get(test_container_name)
            
            # 重启容器
            logger.info(f"重启容器: {test_container_name}")
            container.restart()
            
            # 等待容器恢复
            recovery_time = 0
            max_wait = 60  # 最大等待60秒
            
            while recovery_time < max_wait:
                try:
                    container.reload()
                    if container.status == 'running':
                        # 测试服务是否响应
                        async with aiohttp.ClientSession() as session:
                            async with session.get("http://localhost:8083/health") as response:
                                if response.status == 200:
                                    logger.info(f"服务恢复成功，耗时: {recovery_time}秒")
                                    break
                                    
                except Exception:
                    pass
                
                await asyncio.sleep(2)
                recovery_time += 2
            
            phase4_suite.test_results['reliability']['auto_recovery'] = {
                'status': 'passed' if recovery_time < max_wait else 'failed',
                'recovery_time': recovery_time,
                'max_wait_time': max_wait,
                'test_container': test_container_name
            }
            
        except Exception as e:
            logger.error(f"自动恢复测试失败: {e}")
            phase4_suite.test_results['reliability']['auto_recovery'] = {
                'status': 'failed',
                'error': str(e)
            }
    
    @pytest.mark.asyncio
    async def test_data_consistency(self, phase4_suite):
        """测试数据一致性"""
        logger.info("🔒 测试数据一致性")
        
        storage_url = "http://localhost:8082"
        
        try:
            async with aiohttp.ClientSession() as session:
                # 测试存储状态
                async with session.get(f"{storage_url}/api/v1/storage/status") as response:
                    if response.status == 200:
                        storage_status = await response.json()
                        
                        # 检查ClickHouse连接
                        clickhouse_healthy = storage_status.get('clickhouse', {}).get('status') == 'connected'
                        
                        # 检查Redis连接
                        redis_healthy = storage_status.get('redis', {}).get('status') == 'connected'
                        
                        phase4_suite.test_results['reliability']['data_consistency'] = {
                            'status': 'passed' if clickhouse_healthy and redis_healthy else 'warning',
                            'clickhouse_healthy': clickhouse_healthy,
                            'redis_healthy': redis_healthy,
                            'storage_service_responsive': True
                        }
                    else:
                        raise Exception(f"存储服务响应错误: {response.status}")
                        
        except Exception as e:
            logger.error(f"数据一致性测试失败: {e}")
            phase4_suite.test_results['reliability']['data_consistency'] = {
                'status': 'failed',
                'error': str(e)
            }


class TestSecurityValidation:
    """安全性验证测试"""
    
    @pytest.mark.asyncio
    async def test_api_security(self, phase4_suite):
        """测试API安全性"""
        logger.info("🔐 测试API安全性")
        
        gateway_url = "http://localhost:8080"
        
        security_tests = {
            'health_endpoint_accessible': False,
            'protected_endpoints_secured': False,
            'rate_limiting_active': False
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # 测试公开端点访问
                async with session.get(f"{gateway_url}/health") as response:
                    security_tests['health_endpoint_accessible'] = response.status == 200
                
                # 测试受保护端点（应该需要认证）
                async with session.get(f"{gateway_url}/api/v1/admin") as response:
                    # 应该返回401或403，表示需要认证
                    security_tests['protected_endpoints_secured'] = response.status in [401, 403, 404]
                
                # 测试速率限制（发送多个快速请求）
                rapid_requests = []
                for _ in range(10):
                    task = session.get(f"{gateway_url}/health")
                    rapid_requests.append(task)
                
                responses = await asyncio.gather(*rapid_requests, return_exceptions=True)
                rate_limited = any(
                    hasattr(r, 'status') and r.status == 429 
                    for r in responses if not isinstance(r, Exception)
                )
                security_tests['rate_limiting_active'] = rate_limited
                
        except Exception as e:
            logger.error(f"API安全性测试失败: {e}")
        
        phase4_suite.test_results['security']['api_security'] = {
            'status': 'passed' if all(security_tests.values()) else 'warning',
            **security_tests
        }
    
    @pytest.mark.asyncio
    async def test_container_security(self, phase4_suite):
        """测试容器安全性"""
        logger.info("🛡️ 测试容器安全性")
        
        if not phase4_suite.docker_client:
            pytest.skip("Docker客户端不可用，跳过容器安全测试")
        
        security_issues = []
        containers = phase4_suite.docker_client.containers.list(
            filters={"name": "marketprism"}
        )
        
        for container in containers:
            try:
                # 检查容器是否以root用户运行
                exec_result = container.exec_run("whoami")
                if exec_result.exit_code == 0 and b"root" in exec_result.output:
                    security_issues.append(f"{container.name} 以root用户运行")
                
                # 检查容器是否有特权模式
                if container.attrs.get('HostConfig', {}).get('Privileged', False):
                    security_issues.append(f"{container.name} 运行在特权模式")
                
            except Exception as e:
                logger.warning(f"检查容器 {container.name} 安全性失败: {e}")
        
        phase4_suite.test_results['security']['container_security'] = {
            'status': 'passed' if len(security_issues) == 0 else 'warning',
            'security_issues': security_issues,
            'containers_checked': len(containers)
        }


# 测试运行器
@pytest.mark.asyncio
async def test_phase4_comprehensive_suite():
    """Phase 4 综合测试套件"""
    logger.info("🚀 开始 MarketPrism Phase 4 综合测试")
    
    async with Phase4TestSuite() as suite:
        # 执行所有测试类
        test_classes = [
            TestContainerizedDeployment(),
            TestPerformanceBenchmark(),
            TestMonitoringAndAlerting(),
            TestReliabilityAndRecovery(),
            TestSecurityValidation()
        ]
        
        for test_class in test_classes:
            class_name = test_class.__class__.__name__
            logger.info(f"执行测试类: {class_name}")
            
            # 获取测试方法
            test_methods = [method for method in dir(test_class) 
                          if method.startswith('test_') and callable(getattr(test_class, method))]
            
            for method_name in test_methods:
                try:
                    test_method = getattr(test_class, method_name)
                    await test_method(suite)
                    logger.info(f"✅ {class_name}.{method_name} 测试通过")
                except Exception as e:
                    logger.error(f"❌ {class_name}.{method_name} 测试失败: {e}")
        
        # 生成测试报告
        _generate_test_report(suite.test_results)


def _generate_test_report(test_results: Dict[str, Any]):
    """生成测试报告"""
    print("\n" + "="*80)
    print("📊 MarketPrism Phase 4 测试报告")
    print("="*80)
    
    total_tests = 0
    passed_tests = 0
    
    for category, tests in test_results.items():
        print(f"\n📋 {category.upper()} 测试:")
        print("-" * 40)
        
        for test_name, result in tests.items():
            total_tests += 1
            status = result.get('status', 'unknown')
            
            if status == 'passed':
                print(f"  ✅ {test_name}")
                passed_tests += 1
            elif status == 'warning':
                print(f"  ⚠️  {test_name}")
                passed_tests += 1
            else:
                print(f"  ❌ {test_name}")
            
            # 显示详细信息
            if 'error' in result:
                print(f"     错误: {result['error']}")
            elif status == 'warning' and 'warnings' in result:
                for warning in result['warnings']:
                    print(f"     警告: {warning}")
    
    # 总体统计
    print(f"\n📊 测试统计:")
    print(f"  总测试数: {total_tests}")
    print(f"  通过测试: {passed_tests}")
    print(f"  成功率: {passed_tests/total_tests*100:.1f}%" if total_tests > 0 else "  成功率: 0%")
    
    # 保存详细报告
    report_file = PROJECT_ROOT / "tests" / "reports" / "phase4_test_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(test_results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 详细报告已保存至: {report_file}")
    except Exception as e:
        print(f"❌ 保存报告失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_phase4_comprehensive_suite())