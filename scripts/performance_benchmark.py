"""
MarketPrism 性能基准测试
Phase 4: 优化与部署 - 性能测试组件

提供全面的性能基准测试，包括：
1. 单服务性能测试
2. 整体系统压力测试  
3. 瓶颈识别和分析
4. 性能指标基线建立
5. 负载测试和稳定性验证
"""

import asyncio
import aiohttp
import time
import statistics
import json
import psutil
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import yaml
import concurrent.futures
from dataclasses import dataclass

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    service_name: str
    test_type: str
    start_time: float
    end_time: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    response_times: List[float]
    errors: List[str]
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def requests_per_second(self) -> float:
        if self.duration == 0:
            return 0.0
        return self.total_requests / self.duration
    
    @property
    def avg_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)
    
    @property
    def p95_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return statistics.quantiles(self.response_times, n=20)[18]  # 95th percentile
    
    @property
    def p99_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return statistics.quantiles(self.response_times, n=100)[98]  # 99th percentile


class SystemResourceMonitor:
    """系统资源监控器"""
    
    def __init__(self):
        self.monitoring = False
        self.resource_data = []
    
    async def start_monitoring(self, interval: float = 1.0):
        """开始监控系统资源"""
        self.monitoring = True
        self.resource_data = []
        
        while self.monitoring:
            try:
                resource_info = {
                    'timestamp': time.time(),
                    'cpu_percent': psutil.cpu_percent(interval=None),
                    'memory_percent': psutil.virtual_memory().percent,
                    'memory_available_mb': psutil.virtual_memory().available / (1024**2),
                    'disk_io_read_mb': psutil.disk_io_counters().read_bytes / (1024**2),
                    'disk_io_write_mb': psutil.disk_io_counters().write_bytes / (1024**2),
                    'network_sent_mb': psutil.net_io_counters().bytes_sent / (1024**2),
                    'network_recv_mb': psutil.net_io_counters().bytes_recv / (1024**2),
                }
                self.resource_data.append(resource_info)
                await asyncio.sleep(interval)
            except Exception as e:
                print(f"资源监控错误: {e}")
                await asyncio.sleep(interval)
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
    
    def get_summary(self) -> Dict[str, Any]:
        """获取资源使用总结"""
        if not self.resource_data:
            return {}
        
        cpu_values = [d['cpu_percent'] for d in self.resource_data]
        memory_values = [d['memory_percent'] for d in self.resource_data]
        
        return {
            'duration_seconds': len(self.resource_data),
            'cpu_usage': {
                'avg': statistics.mean(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values)
            },
            'memory_usage': {
                'avg': statistics.mean(memory_values),
                'max': max(memory_values),
                'min': min(memory_values)
            },
            'peak_memory_available_mb': min(d['memory_available_mb'] for d in self.resource_data)
        }


class ServiceBenchmark:
    """单服务性能基准测试"""
    
    def __init__(self, service_name: str, base_url: str):
        self.service_name = service_name
        self.base_url = base_url
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def health_check_test(self, num_requests: int = 100) -> PerformanceMetrics:
        """健康检查性能测试"""
        print(f"🔍 {self.service_name} 健康检查测试 ({num_requests} 请求)")
        
        start_time = time.time()
        response_times = []
        successful_requests = 0
        failed_requests = 0
        errors = []
        
        tasks = []
        for i in range(num_requests):
            task = self._single_health_check()
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                failed_requests += 1
                errors.append(str(result))
            else:
                successful_requests += 1
                response_times.append(result)
        
        end_time = time.time()
        
        return PerformanceMetrics(
            service_name=self.service_name,
            test_type="health_check",
            start_time=start_time,
            end_time=end_time,
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            response_times=response_times,
            errors=errors
        )
    
    async def _single_health_check(self) -> float:
        """单次健康检查"""
        start = time.time()
        async with self.session.get(f"{self.base_url}/health") as response:
            await response.read()
            if response.status != 200:
                raise Exception(f"Health check failed: {response.status}")
        return time.time() - start
    
    async def api_stress_test(self, endpoint: str, num_requests: int = 500, 
                             concurrent_requests: int = 50) -> PerformanceMetrics:
        """API压力测试"""
        print(f"⚡ {self.service_name} API压力测试 ({endpoint}, {num_requests} 请求, {concurrent_requests} 并发)")
        
        start_time = time.time()
        response_times = []
        successful_requests = 0
        failed_requests = 0
        errors = []
        
        # 分批执行请求
        semaphore = asyncio.Semaphore(concurrent_requests)
        
        async def single_request():
            async with semaphore:
                try:
                    start = time.time()
                    async with self.session.get(f"{self.base_url}{endpoint}") as response:
                        await response.read()
                        response_time = time.time() - start
                        if response.status == 200:
                            return True, response_time, None
                        else:
                            return False, response_time, f"HTTP {response.status}"
                except Exception as e:
                    return False, 0, str(e)
        
        tasks = [single_request() for _ in range(num_requests)]
        results = await asyncio.gather(*tasks)
        
        for success, response_time, error in results:
            if success:
                successful_requests += 1
                response_times.append(response_time)
            else:
                failed_requests += 1
                if error:
                    errors.append(error)
        
        end_time = time.time()
        
        return PerformanceMetrics(
            service_name=self.service_name,
            test_type=f"api_stress_{endpoint.replace('/', '_')}",
            start_time=start_time,
            end_time=end_time,
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            response_times=response_times,
            errors=errors
        )


class SystemBenchmark:
    """整体系统性能基准测试"""
    
    def __init__(self, services_config: Dict[str, Dict[str, Any]]):
        self.services_config = services_config
        self.resource_monitor = SystemResourceMonitor()
    
    async def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """运行全面的性能基准测试"""
        print("🚀 开始MarketPrism系统性能基准测试")
        print("="*60)
        
        # 启动资源监控
        monitor_task = asyncio.create_task(
            self.resource_monitor.start_monitoring(interval=0.5)
        )
        
        benchmark_results = {
            'test_start_time': datetime.utcnow().isoformat(),
            'service_results': {},
            'system_resources': {},
            'overall_metrics': {}
        }
        
        try:
            # 测试各个服务
            for service_name, config in self.services_config.items():
                print(f"\n📊 测试服务: {service_name}")
                service_results = await self._test_service(service_name, config)
                benchmark_results['service_results'][service_name] = service_results
            
            # 运行整体系统测试
            print(f"\n🔄 系统整体压力测试")
            overall_results = await self._test_system_integration()
            benchmark_results['overall_metrics'] = overall_results
            
        finally:
            # 停止资源监控
            self.resource_monitor.stop_monitoring()
            monitor_task.cancel()
            
            # 获取资源使用总结
            benchmark_results['system_resources'] = self.resource_monitor.get_summary()
        
        benchmark_results['test_end_time'] = datetime.utcnow().isoformat()
        
        return benchmark_results
    
    async def _test_service(self, service_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试单个服务性能"""
        base_url = f"http://{config.get('host', 'localhost')}:{config['port']}"
        
        service_results = {
            'service_name': service_name,
            'base_url': base_url,
            'tests': {}
        }
        
        try:
            async with ServiceBenchmark(service_name, base_url) as benchmark:
                # 健康检查测试
                health_metrics = await benchmark.health_check_test(num_requests=100)
                service_results['tests']['health_check'] = self._metrics_to_dict(health_metrics)
                
                # API测试（根据服务类型）
                if service_name == 'api-gateway-service':
                    # 测试网关路由
                    api_metrics = await benchmark.api_stress_test(
                        "/api/v1/storage/status", num_requests=200, concurrent_requests=20
                    )
                    service_results['tests']['gateway_routing'] = self._metrics_to_dict(api_metrics)
                
                elif service_name == 'monitoring-service':
                    # 测试监控概览
                    api_metrics = await benchmark.api_stress_test(
                        "/api/v1/overview", num_requests=150, concurrent_requests=15
                    )
                    service_results['tests']['monitoring_overview'] = self._metrics_to_dict(api_metrics)
                
                elif service_name == 'data-storage-service':
                    # 测试存储状态
                    api_metrics = await benchmark.api_stress_test(
                        "/api/v1/storage/status", num_requests=200, concurrent_requests=25
                    )
                    service_results['tests']['storage_status'] = self._metrics_to_dict(api_metrics)
                
                elif service_name == 'market-data-collector':
                    # 测试采集器状态
                    api_metrics = await benchmark.api_stress_test(
                        "/api/v1/status", num_requests=100, concurrent_requests=10
                    )
                    service_results['tests']['collector_status'] = self._metrics_to_dict(api_metrics)
                
                elif service_name == 'message-broker-service':
                    # 测试消息代理状态
                    api_metrics = await benchmark.api_stress_test(
                        "/api/v1/status", num_requests=100, concurrent_requests=10
                    )
                    service_results['tests']['broker_status'] = self._metrics_to_dict(api_metrics)
                
                elif service_name == 'scheduler-service':
                    # 测试调度器状态
                    api_metrics = await benchmark.api_stress_test(
                        "/api/v1/status", num_requests=100, concurrent_requests=10
                    )
                    service_results['tests']['scheduler_status'] = self._metrics_to_dict(api_metrics)
        
        except Exception as e:
            service_results['error'] = str(e)
            print(f"❌ 测试 {service_name} 失败: {e}")
        
        return service_results
    
    async def _test_system_integration(self) -> Dict[str, Any]:
        """测试系统整体集成性能"""
        print("  📈 执行跨服务集成测试...")
        
        integration_results = {
            'cross_service_tests': {},
            'concurrent_load_test': {}
        }
        
        # 跨服务调用测试（通过API网关）
        try:
            gateway_url = f"http://localhost:{self.services_config.get('api-gateway-service', {}).get('port', 8080)}"
            
            async with ServiceBenchmark("system_integration", gateway_url) as benchmark:
                # 测试通过网关访问各服务
                cross_service_metrics = await benchmark.api_stress_test(
                    "/api/v1/monitoring-service/overview", 
                    num_requests=100, 
                    concurrent_requests=10
                )
                integration_results['cross_service_tests']['gateway_to_monitoring'] = \
                    self._metrics_to_dict(cross_service_metrics)
        
        except Exception as e:
            integration_results['cross_service_tests']['error'] = str(e)
        
        # 并发负载测试
        try:
            concurrent_results = await self._concurrent_load_test()
            integration_results['concurrent_load_test'] = concurrent_results
        except Exception as e:
            integration_results['concurrent_load_test']['error'] = str(e)
        
        return integration_results
    
    async def _concurrent_load_test(self) -> Dict[str, Any]:
        """并发负载测试"""
        print("  ⚡ 执行并发负载测试...")
        
        # 同时对多个服务施加负载
        load_tasks = []
        
        for service_name, config in self.services_config.items():
            if service_name in ['api-gateway-service', 'monitoring-service', 'data-storage-service']:
                base_url = f"http://{config.get('host', 'localhost')}:{config['port']}"
                
                async def service_load_test(svc_name, url):
                    async with ServiceBenchmark(svc_name, url) as benchmark:
                        return await benchmark.health_check_test(num_requests=50)
                
                load_tasks.append(service_load_test(service_name, base_url))
        
        start_time = time.time()
        results = await asyncio.gather(*load_tasks, return_exceptions=True)
        end_time = time.time()
        
        concurrent_metrics = {
            'total_duration': end_time - start_time,
            'services_tested': len(load_tasks),
            'results': {}
        }
        
        for i, result in enumerate(results):
            service_name = list(self.services_config.keys())[i]
            if isinstance(result, Exception):
                concurrent_metrics['results'][service_name] = {'error': str(result)}
            else:
                concurrent_metrics['results'][service_name] = self._metrics_to_dict(result)
        
        return concurrent_metrics
    
    def _metrics_to_dict(self, metrics: PerformanceMetrics) -> Dict[str, Any]:
        """转换性能指标为字典"""
        return {
            'service_name': metrics.service_name,
            'test_type': metrics.test_type,
            'duration_seconds': metrics.duration,
            'total_requests': metrics.total_requests,
            'successful_requests': metrics.successful_requests,
            'failed_requests': metrics.failed_requests,
            'success_rate_percent': metrics.success_rate,
            'requests_per_second': metrics.requests_per_second,
            'avg_response_time_ms': metrics.avg_response_time * 1000,
            'p95_response_time_ms': metrics.p95_response_time * 1000,
            'p99_response_time_ms': metrics.p99_response_time * 1000,
            'error_count': len(metrics.errors),
            'sample_errors': metrics.errors[:5]  # 只保留前5个错误样例
        }


class BenchmarkReporter:
    """性能基准测试报告生成器"""
    
    def __init__(self, results: Dict[str, Any]):
        self.results = results
    
    def generate_console_report(self):
        """生成控制台报告"""
        print("\n" + "="*80)
        print("📊 MarketPrism 性能基准测试报告")
        print("="*80)
        
        # 测试概览
        print(f"\n🕐 测试时间: {self.results.get('test_start_time', 'Unknown')}")
        print(f"📋 测试服务数: {len(self.results.get('service_results', {}))}")
        
        # 系统资源使用
        resource_summary = self.results.get('system_resources', {})
        if resource_summary:
            print(f"\n💻 系统资源使用:")
            cpu_usage = resource_summary.get('cpu_usage', {})
            memory_usage = resource_summary.get('memory_usage', {})
            print(f"   - CPU: 平均 {cpu_usage.get('avg', 0):.1f}%, 最高 {cpu_usage.get('max', 0):.1f}%")
            print(f"   - 内存: 平均 {memory_usage.get('avg', 0):.1f}%, 最高 {memory_usage.get('max', 0):.1f}%")
        
        # 各服务性能
        print(f"\n📈 各服务性能指标:")
        service_results = self.results.get('service_results', {})
        
        for service_name, service_data in service_results.items():
            print(f"\n🔍 {service_name}:")
            
            if 'error' in service_data:
                print(f"   ❌ 测试失败: {service_data['error']}")
                continue
            
            tests = service_data.get('tests', {})
            for test_name, test_data in tests.items():
                print(f"   📊 {test_name}:")
                print(f"      - 成功率: {test_data.get('success_rate_percent', 0):.1f}%")
                print(f"      - QPS: {test_data.get('requests_per_second', 0):.1f}")
                print(f"      - 平均响应时间: {test_data.get('avg_response_time_ms', 0):.1f}ms")
                print(f"      - P95响应时间: {test_data.get('p95_response_time_ms', 0):.1f}ms")
                
                if test_data.get('error_count', 0) > 0:
                    print(f"      - 错误数: {test_data['error_count']}")
        
        # 整体系统性能
        overall_metrics = self.results.get('overall_metrics', {})
        if overall_metrics:
            print(f"\n🔄 整体系统性能:")
            concurrent_test = overall_metrics.get('concurrent_load_test', {})
            if 'total_duration' in concurrent_test:
                print(f"   - 并发测试时长: {concurrent_test['total_duration']:.2f}s")
                print(f"   - 并发测试服务数: {concurrent_test.get('services_tested', 0)}")
        
        # 性能基线建议
        self._print_performance_baseline()
    
    def _print_performance_baseline(self):
        """打印性能基线建议"""
        print(f"\n🎯 性能基线建议:")
        print(f"   ✅ 健康检查响应时间 < 50ms")
        print(f"   ✅ API响应时间 < 200ms (P95)")
        print(f"   ✅ 成功率 > 99%")
        print(f"   ✅ QPS > 50 (健康检查)")
        print(f"   ✅ 系统CPU使用率 < 80%")
        print(f"   ✅ 系统内存使用率 < 85%")
    
    def save_json_report(self, file_path: str):
        """保存JSON格式报告"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"\n💾 详细报告已保存至: {file_path}")
        except Exception as e:
            print(f"❌ 保存报告失败: {e}")


async def main():
    """主函数"""
    print("🚀 MarketPrism 性能基准测试工具")
    print("Phase 4: 优化与部署 - 性能验证")
    print("-"*50)
    
    # 服务配置
    services_config = {
        'api-gateway-service': {'host': 'localhost', 'port': 8080},
        'monitoring-service': {'host': 'localhost', 'port': 8083},
        'data-storage-service': {'host': 'localhost', 'port': 8082},
        'market-data-collector': {'host': 'localhost', 'port': 8081},
        'message-broker-service': {'host': 'localhost', 'port': 8085},
        'scheduler-service': {'host': 'localhost', 'port': 8084}
    }
    
    # 执行基准测试
    benchmark = SystemBenchmark(services_config)
    
    try:
        print("⏱️  开始性能基准测试（预计需要2-3分钟）...")
        results = await benchmark.run_comprehensive_benchmark()
        
        # 生成报告
        reporter = BenchmarkReporter(results)
        reporter.generate_console_report()
        
        # 保存详细报告
        report_file = project_root / "tests" / "reports" / "performance" / "benchmark_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        reporter.save_json_report(str(report_file))
        
    except KeyboardInterrupt:
        print("\n⏹️  性能测试被用户中断")
    except Exception as e:
        print(f"\n❌ 性能测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())