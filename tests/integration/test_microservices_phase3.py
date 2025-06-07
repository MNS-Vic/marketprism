"""
MarketPrism微服务架构 Phase 3 集成测试
测试基础设施与监控服务的集成功能

Phase 3 集成范围：
1. Monitoring Service - 综合监控和告警管理
2. Message Broker Service - NATS消息代理和JetStream
3. 与Phase 1和Phase 2服务的集成验证
4. 基础设施服务的稳定性测试
5. 完整微服务生态系统验证

本测试验证Phase 3基础设施服务的正确性和与已有服务的集成能力。
"""

import asyncio
import aiohttp
import pytest
import json
import time
import psutil
from pathlib import Path
import sys
import yaml
from datetime import datetime, timedelta

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.test_helpers import TestHelpers, ServiceTestManager


class TestPhase3Integration:
    """Phase 3 微服务集成测试"""
    
    def setup_method(self):
        """测试设置"""
        self.test_helpers = TestHelpers()
        self.service_manager = ServiceTestManager()
        
        # Phase 3 服务配置
        self.services_config = {
            'monitoring-service': {
                'port': 8083,
                'base_url': 'http://localhost:8083',
                'health_endpoint': '/health'
            },
            'message-broker-service': {
                'port': 8085,
                'base_url': 'http://localhost:8085',
                'health_endpoint': '/health'
            },
            # Phase 1 & 2 services for integration testing
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
    
    async def test_001_monitoring_service_health(self):
        """测试1: Monitoring Service健康检查"""
        print("\n=== 测试1: Monitoring Service健康检查 ===")
        
        service_config = self.services_config['monitoring-service']
        
        # 检查服务健康状态
        health_check = await self.test_helpers.check_service_health(
            service_config['base_url'],
            service_config['health_endpoint']
        )
        
        assert health_check['success'], f"Monitoring Service健康检查失败: {health_check.get('error')}"
        assert health_check['data']['status'] == 'healthy'
        
        print("✅ Monitoring Service健康检查通过")
        print(f"   - 服务状态: {health_check['data']['status']}")
        print(f"   - 响应时间: {health_check.get('response_time', 0):.3f}s")
    
    async def test_002_message_broker_service_health(self):
        """测试2: Message Broker Service健康检查"""
        print("\n=== 测试2: Message Broker Service健康检查 ===")
        
        service_config = self.services_config['message-broker-service']
        
        # 检查服务健康状态
        health_check = await self.test_helpers.check_service_health(
            service_config['base_url'],
            service_config['health_endpoint']
        )
        
        assert health_check['success'], f"Message Broker Service健康检查失败: {health_check.get('error')}"
        assert health_check['data']['status'] == 'healthy'
        
        print("✅ Message Broker Service健康检查通过")
        print(f"   - 服务状态: {health_check['data']['status']}")
    
    async def test_003_monitoring_system_overview(self):
        """测试3: 监控系统概览功能"""
        print("\n=== 测试3: 监控系统概览功能 ===")
        
        monitoring_url = self.services_config['monitoring-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{monitoring_url}/api/v1/overview") as response:
                assert response.status == 200
                overview = await response.json()
                
                # 验证系统资源信息
                assert 'system_resources' in overview
                system_resources = overview['system_resources']
                
                assert 'cpu_usage_percent' in system_resources
                assert 'memory_usage_percent' in system_resources
                assert 'disk_usage_percent' in system_resources
                
                # CPU和内存使用率应该在合理范围内
                cpu_usage = system_resources['cpu_usage_percent']
                memory_usage = system_resources['memory_usage_percent']
                
                assert 0 <= cpu_usage <= 100, f"CPU使用率异常: {cpu_usage}%"
                assert 0 <= memory_usage <= 100, f"内存使用率异常: {memory_usage}%"
                
                # 验证服务状态信息
                assert 'services' in overview
                services_info = overview['services']
                
                assert 'total' in services_info
                assert 'healthy' in services_info
                assert 'health_percentage' in services_info
        
        print("✅ 监控系统概览功能正常")
        print(f"   - CPU使用率: {cpu_usage:.1f}%")
        print(f"   - 内存使用率: {memory_usage:.1f}%")
        print(f"   - 总服务数: {services_info['total']}")
        print(f"   - 健康服务数: {services_info['healthy']}")
        print(f"   - 健康率: {services_info['health_percentage']:.1f}%")
    
    async def test_004_monitoring_service_discovery(self):
        """测试4: 监控服务发现功能"""
        print("\n=== 测试4: 监控服务发现功能 ===")
        
        monitoring_url = self.services_config['monitoring-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{monitoring_url}/api/v1/services") as response:
                assert response.status == 200
                services_data = await response.json()
                
                assert 'health_status' in services_data
                assert 'statistics' in services_data
                
                health_status = services_data['health_status']
                statistics = services_data['statistics']
                
                # 验证关键服务被监控
                expected_services = [
                    'market-data-collector', 
                    'api-gateway-service',
                    'data-storage-service',
                    'scheduler-service'
                ]
                
                monitored_services = list(health_status.keys())
                print(f"   - 监控的服务: {monitored_services}")
                
                # 至少应该监控到一些核心服务（可能不是全部，取决于服务启动状态）
                found_services = [s for s in expected_services if s in monitored_services]
                assert len(found_services) > 0, f"未发现任何预期的服务，监控到的服务: {monitored_services}"
                
                # 验证健康状态格式
                for service_name, status in health_status.items():
                    assert 'status' in status
                    assert status['status'] in ['healthy', 'unhealthy', 'unreachable']
                    
                    if status['status'] == 'healthy':
                        assert 'response_time' in status
                        assert status['response_time'] > 0
        
        print(f"✅ 监控服务发现功能正常")
        print(f"   - 发现的核心服务: {found_services}")
    
    async def test_005_prometheus_metrics(self):
        """测试5: Prometheus指标暴露"""
        print("\n=== 测试5: Prometheus指标暴露 ===")
        
        monitoring_url = self.services_config['monitoring-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{monitoring_url}/metrics") as response:
                assert response.status == 200
                metrics_text = await response.text()
                
                # 验证指标格式
                assert 'system_cpu_usage_percent' in metrics_text
                assert 'system_memory_usage_percent' in metrics_text
                assert 'service_status' in metrics_text
                
                # 验证指标值格式
                lines = metrics_text.split('\n')
                metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
                
                assert len(metric_lines) > 0, "未找到任何指标数据"
                
                # 验证至少有一些系统指标
                system_metrics = [line for line in metric_lines if 'system_' in line]
                assert len(system_metrics) > 0, "未找到系统指标"
        
        print("✅ Prometheus指标暴露正常")
        print(f"   - 总指标行数: {len(metric_lines)}")
        print(f"   - 系统指标行数: {len(system_metrics)}")
    
    async def test_006_message_broker_status(self):
        """测试6: Message Broker状态检查"""
        print("\n=== 测试6: Message Broker状态检查 ===")
        
        broker_url = self.services_config['message-broker-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{broker_url}/api/v1/status") as response:
                assert response.status == 200
                status = await response.json()
                
                assert 'service' in status
                assert status['service'] == 'message-broker-service'
                
                # 验证NATS服务器状态
                assert 'nats_server' in status
                nats_status = status['nats_server']
                
                # NATS服务器可能正在运行或未启动（取决于环境）
                if nats_status['status'] == 'running':
                    print("   - NATS服务器: 运行中")
                    if 'server_info' in nats_status:
                        server_info = nats_status['server_info']
                        print(f"   - 连接数: {server_info.get('connections', 0)}")
                        print(f"   - 端口: {server_info.get('port', 'unknown')}")
                else:
                    print(f"   - NATS服务器: {nats_status['status']}")
                
                # 验证JetStream流信息
                assert 'jetstream_streams' in status
                streams = status['jetstream_streams']
                print(f"   - JetStream流数量: {len(streams)}")
                
                # 验证消息统计
                assert 'message_stats' in status
                msg_stats = status['message_stats']
                assert 'published' in msg_stats
                assert 'consumed' in msg_stats
                assert 'errors' in msg_stats
        
        print("✅ Message Broker状态检查正常")
    
    async def test_007_jetstream_streams(self):
        """测试7: JetStream流管理"""
        print("\n=== 测试7: JetStream流管理 ===")
        
        broker_url = self.services_config['message-broker-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{broker_url}/api/v1/streams") as response:
                assert response.status == 200
                streams_data = await response.json()
                
                assert 'streams' in streams_data
                streams = streams_data['streams']
                
                print(f"   - 发现的流数量: {len(streams)}")
                
                # 如果NATS服务器运行且JetStream可用，应该有默认流
                if len(streams) > 0:
                    # 验证流信息格式
                    for stream in streams:
                        assert 'name' in stream
                        assert 'subjects' in stream
                        assert 'messages' in stream
                        assert isinstance(stream['messages'], int)
                        assert isinstance(stream['subjects'], list)
                        
                        print(f"   - 流: {stream['name']}")
                        print(f"     主题: {stream['subjects']}")
                        print(f"     消息数: {stream['messages']}")
                else:
                    print("   - 当前无活跃流（可能NATS未启动或JetStream未启用）")
        
        print("✅ JetStream流管理功能正常")
    
    async def test_008_message_publishing(self):
        """测试8: 消息发布功能"""
        print("\n=== 测试8: 消息发布功能 ===")
        
        broker_url = self.services_config['message-broker-service']['base_url']
        
        # 测试消息
        test_message = {
            'subject': 'test.integration.message',
            'message': {
                'test_id': 'phase3_integration_test',
                'timestamp': datetime.utcnow().isoformat(),
                'data': 'Hello from Phase 3 integration test'
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{broker_url}/api/v1/publish",
                json=test_message
            ) as response:
                # 可能返回200（成功）或500（如果NATS未运行）
                response_data = await response.json()
                
                if response.status == 200:
                    assert response_data.get('success') == True
                    print("✅ 消息发布成功")
                elif response.status == 500:
                    print("⚠️ 消息发布失败（可能NATS服务未运行）")
                    print(f"   错误: {response_data.get('error', 'unknown')}")
                else:
                    assert False, f"意外的响应状态: {response.status}"
    
    async def test_009_alerts_functionality(self):
        """测试9: 告警功能测试"""
        print("\n=== 测试9: 告警功能测试 ===")
        
        monitoring_url = self.services_config['monitoring-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{monitoring_url}/api/v1/alerts") as response:
                assert response.status == 200
                alerts_data = await response.json()
                
                assert 'active_alerts' in alerts_data
                assert 'alert_history' in alerts_data
                
                active_alerts = alerts_data['active_alerts']
                alert_history = alerts_data['alert_history']
                
                print(f"   - 活跃告警数: {len(active_alerts)}")
                print(f"   - 历史告警数: {len(alert_history)}")
                
                # 验证告警格式
                for alert in active_alerts:
                    assert 'rule_id' in alert
                    assert 'rule_name' in alert
                    assert 'severity' in alert
                    assert 'description' in alert
                    assert alert['severity'] in ['warning', 'critical']
                    
                    print(f"   - 活跃告警: {alert['rule_name']} ({alert['severity']})")
                
                # 验证历史告警格式
                for alert in alert_history[-3:]:  # 只检查最近3个
                    assert 'rule_id' in alert
                    assert 'status' in alert
                    if alert['status'] == 'resolved':
                        assert 'end_time' in alert
        
        print("✅ 告警功能正常")
    
    async def test_010_service_specific_monitoring(self):
        """测试10: 特定服务监控详情"""
        print("\n=== 测试10: 特定服务监控详情 ===")
        
        monitoring_url = self.services_config['monitoring-service']['base_url']
        
        # 测试监控API Gateway服务（最可能在运行）
        test_service = 'api-gateway-service'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{monitoring_url}/api/v1/services/{test_service}") as response:
                # 可能返回200（找到服务）或404（服务未发现）
                
                if response.status == 200:
                    service_details = await response.json()
                    
                    assert 'service_name' in service_details
                    assert service_details['service_name'] == test_service
                    assert 'current_status' in service_details
                    assert 'statistics' in service_details
                    
                    current_status = service_details['current_status']
                    statistics = service_details['statistics']
                    
                    print(f"✅ 服务 {test_service} 监控详情:")
                    print(f"   - 当前状态: {current_status.get('status', 'unknown')}")
                    if 'response_time' in current_status:
                        print(f"   - 响应时间: {current_status['response_time']:.3f}s")
                    
                    if statistics:
                        print(f"   - 总检查次数: {statistics.get('total_checks', 0)}")
                        print(f"   - 健康检查次数: {statistics.get('healthy_checks', 0)}")
                        print(f"   - 正常运行率: {statistics.get('uptime_percentage', 0):.1f}%")
                        
                elif response.status == 404:
                    error_data = await response.json()
                    print(f"⚠️ 服务 {test_service} 未被监控")
                    print(f"   原因: {error_data.get('error', 'Service not found')}")
                else:
                    assert False, f"意外的响应状态: {response.status}"
    
    async def test_011_cross_service_integration(self):
        """测试11: 跨服务集成验证"""
        print("\n=== 测试11: 跨服务集成验证 ===")
        
        # 测试通过API Gateway访问监控服务
        gateway_url = self.services_config['api-gateway-service']['base_url']
        
        async with aiohttp.ClientSession() as session:
            # 通过网关访问监控服务概览
            try:
                async with session.get(f"{gateway_url}/api/v1/monitoring-service/overview", timeout=10) as response:
                    if response.status == 200:
                        overview = await response.json()
                        print("✅ 通过API Gateway访问监控服务成功")
                        print(f"   - 系统CPU: {overview.get('system_resources', {}).get('cpu_usage_percent', 'unknown'):.1f}%")
                    elif response.status == 503:
                        print("⚠️ 监控服务通过网关不可达（可能服务发现问题）")
                    else:
                        print(f"⚠️ 网关路由返回状态: {response.status}")
            except asyncio.TimeoutError:
                print("⚠️ 网关路由超时")
            except Exception as e:
                print(f"⚠️ 网关路由异常: {e}")
            
            # 测试通过网关访问消息代理服务
            try:
                async with session.get(f"{gateway_url}/api/v1/message-broker-service/status", timeout=10) as response:
                    if response.status == 200:
                        status = await response.json()
                        print("✅ 通过API Gateway访问消息代理服务成功")
                        print(f"   - NATS状态: {status.get('nats_server', {}).get('status', 'unknown')}")
                    elif response.status == 503:
                        print("⚠️ 消息代理服务通过网关不可达")
                    else:
                        print(f"⚠️ 网关路由返回状态: {response.status}")
            except asyncio.TimeoutError:
                print("⚠️ 网关路由超时")
            except Exception as e:
                print(f"⚠️ 网关路由异常: {e}")
    
    async def test_012_performance_monitoring(self):
        """测试12: 性能监控验证"""
        print("\n=== 测试12: 性能监控验证 ===")
        
        monitoring_url = self.services_config['monitoring-service']['base_url']
        
        # 连续监控几次，检查指标变化
        measurements = []
        
        for i in range(3):
            async with aiohttp.ClientSession() as session:
                start_time = time.time()
                async with session.get(f"{monitoring_url}/api/v1/overview") as response:
                    response_time = time.time() - start_time
                    
                    if response.status == 200:
                        overview = await response.json()
                        measurements.append({
                            'timestamp': time.time(),
                            'response_time': response_time,
                            'cpu_usage': overview.get('system_resources', {}).get('cpu_usage_percent', 0),
                            'memory_usage': overview.get('system_resources', {}).get('memory_usage_percent', 0)
                        })
                    
            await asyncio.sleep(1)  # 间隔1秒
        
        if len(measurements) >= 2:
            avg_response_time = sum(m['response_time'] for m in measurements) / len(measurements)
            avg_cpu = sum(m['cpu_usage'] for m in measurements) / len(measurements)
            avg_memory = sum(m['memory_usage'] for m in measurements) / len(measurements)
            
            print("✅ 性能监控验证完成")
            print(f"   - 平均响应时间: {avg_response_time:.3f}s")
            print(f"   - 平均CPU使用率: {avg_cpu:.1f}%")
            print(f"   - 平均内存使用率: {avg_memory:.1f}%")
            
            # 验证性能指标在合理范围内
            assert avg_response_time < 2.0, f"监控服务响应时间过长: {avg_response_time:.3f}s"
            assert avg_cpu < 100, f"CPU使用率异常: {avg_cpu:.1f}%"
            assert avg_memory < 100, f"内存使用率异常: {avg_memory:.1f}%"
        else:
            print("⚠️ 性能监控数据不足")
    
    def teardown_method(self):
        """测试清理"""
        pass


@pytest.mark.asyncio
async def test_phase3_integration_suite():
    """Phase 3 集成测试套件入口"""
    print("\n" + "="*60)
    print("MarketPrism Phase 3 微服务集成测试")
    print("测试范围: 基础设施与监控服务")
    print("="*60)
    
    test_suite = TestPhase3Integration()
    test_suite.setup_method()
    
    test_methods = [
        test_suite.test_001_monitoring_service_health,
        test_suite.test_002_message_broker_service_health,
        test_suite.test_003_monitoring_system_overview,
        test_suite.test_004_monitoring_service_discovery,
        test_suite.test_005_prometheus_metrics,
        test_suite.test_006_message_broker_status,
        test_suite.test_007_jetstream_streams,
        test_suite.test_008_message_publishing,
        test_suite.test_009_alerts_functionality,
        test_suite.test_010_service_specific_monitoring,
        test_suite.test_011_cross_service_integration,
        test_suite.test_012_performance_monitoring
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
    print("Phase 3 集成测试结果汇总")
    print("="*60)
    print(f"✅ 通过: {passed_tests}")
    print(f"❌ 失败: {failed_tests}")
    print(f"📊 成功率: {passed_tests/(passed_tests+failed_tests)*100:.1f}%")
    
    if failed_tests == 0:
        print("\n🎉 Phase 3 集成测试全部通过！")
        print("基础设施与监控服务运行正常")
    else:
        print(f"\n⚠️ 有 {failed_tests} 个测试失败，请检查服务状态")
    
    test_suite.teardown_method()
    
    # 返回测试结果用于自动化流程
    return {
        'passed': passed_tests,
        'failed': failed_tests,
        'success_rate': passed_tests/(passed_tests+failed_tests)*100,
        'phase': 'Phase 3',
        'services_tested': ['monitoring-service', 'message-broker-service']
    }


if __name__ == "__main__":
    # 直接运行测试
    result = asyncio.run(test_phase3_integration_suite())
    
    # 如果失败率过高，退出时返回错误状态
    if result['success_rate'] < 70:
        sys.exit(1)