"""
服务依赖管理器 - 统一管理测试所需的微服务和外部服务
"""
from datetime import datetime, timezone
import os
import socket
import subprocess
import time
import pytest
from typing import Dict, List, Optional
from pathlib import Path


class ServiceManager:
    """测试服务管理器 - 确保必要服务运行或提供mock"""
    
    def __init__(self):
        self.required_services = {
            # 微服务
            'monitoring-service': 8001,
            'message-broker-service': 8002, 
            'data-storage-service': 8003,
            'api-gateway-service': 8000,
            'scheduler-service': 8004,
            'market-data-collector': 8005,
            
            # 基础设施服务
            'nats': 4222,
            'clickhouse': 8123,
            'redis': 6379,
            'prometheus': 9090,
            'grafana': 3000
        }
        
        self.service_paths = {
            'monitoring-service': 'services/monitoring-service/main.py',
            'message-broker-service': 'services/message-broker-service/main.py',
            'data-storage-service': 'services/data-storage-service/main.py',
            'api-gateway-service': 'services/api-gateway-service/main.py',
            'scheduler-service': 'services/scheduler-service/main.py',
            'market-data-collector': 'services/market-data-collector/main.py'
        }
        
        self.running_processes = {}
        
    def is_service_running(self, service_name: str) -> bool:
        """检查服务是否运行"""
        if service_name not in self.required_services:
            return False
            
        port = self.required_services[service_name]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                result = s.connect_ex(('localhost', port))
                return result == 0
        except Exception:
            return False
    
    def start_microservice(self, service_name: str) -> bool:
        """启动微服务"""
        if service_name not in self.service_paths:
            print(f"❌ 未知的微服务: {service_name}")
            return False
            
        service_path = self.service_paths[service_name]
        full_path = Path(service_path)
        
        if not full_path.exists():
            print(f"❌ 服务文件不存在: {service_path}")
            return False
            
        try:
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONPATH'] = '/Users/yao/Documents/GitHub/marketprism'
            
            # 后台启动服务
            process = subprocess.Popen([
                'python', str(full_path)
            ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.running_processes[service_name] = process
            
            # 等待服务启动
            max_wait = 10  # 最多等待10秒
            for i in range(max_wait):
                time.sleep(1)
                if self.is_service_running(service_name):
                    print(f"✅ {service_name} 启动成功")
                    return True
                    
            print(f"❌ {service_name} 启动超时")
            return False
            
        except Exception as e:
            print(f"❌ 启动 {service_name} 失败: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """停止服务"""
        if service_name in self.running_processes:
            try:
                process = self.running_processes[service_name]
                process.terminate()
                process.wait(timeout=5)
                del self.running_processes[service_name]
                print(f"✅ {service_name} 已停止")
                return True
            except Exception as e:
                print(f"❌ 停止 {service_name} 失败: {e}")
                return False
        return True
    
    def ensure_test_environment(self) -> Dict[str, bool]:
        """确保测试环境就绪"""
        status = {}
        
        # 核心微服务 - 测试时需要的最小集合
        core_services = [
            'monitoring-service',
            'message-broker-service'
        ]
        
        print("🚀 确保核心测试服务运行中...")
        
        for service in core_services:
            if self.is_service_running(service):
                print(f"✅ {service} 已运行")
                status[service] = True
            else:
                print(f"⚡ 启动 {service}...")
                success = self.start_microservice(service)
                status[service] = success
                
        return status
    
    def check_infrastructure_services(self) -> Dict[str, bool]:
        """检查基础设施服务状态"""
        infrastructure = ['nats', 'clickhouse', 'redis']
        status = {}
        
        print("🔧 检查基础设施服务:")
        for service in infrastructure:
            running = self.is_service_running(service)
            status[service] = running
            print(f"  ├─ {service}: {'✅' if running else '❌'}")
            
        return status
    
    def cleanup_test_services(self):
        """清理测试服务"""
        print("🧹 清理测试服务...")
        
        for service_name in list(self.running_processes.keys()):
            self.stop_service(service_name)
    
    def get_service_health_report(self) -> Dict:
        """获取服务健康状态报告"""
        report = {
            'microservices': {},
            'infrastructure': {},
            'summary': {
                'total_services': len(self.required_services),
                'running_services': 0,
                'failed_services': []
            }
        }
        
        # 检查微服务
        for service in self.service_paths.keys():
            running = self.is_service_running(service)
            report['microservices'][service] = running
            if running:
                report['summary']['running_services'] += 1
            else:
                report['summary']['failed_services'].append(service)
        
        # 检查基础设施
        infrastructure = ['nats', 'clickhouse', 'redis', 'prometheus', 'grafana']
        for service in infrastructure:
            running = self.is_service_running(service)
            report['infrastructure'][service] = running
            if running:
                report['summary']['running_services'] += 1
            else:
                report['summary']['failed_services'].append(service)
        
        return report
    
    def get_skip_conditions(self):
        """返回服务相关的跳过条件"""
        return {
            'requires_monitoring': pytest.mark.skipif(
                not self.is_service_running('monitoring-service'),
                reason="监控服务未运行，尝试运行: python services/monitoring-service/main.py"
            ),
            'requires_nats': pytest.mark.skipif(
                not self.is_service_running('nats'),
                reason="NATS服务未运行，请启动NATS服务器"
            ),
            'requires_clickhouse': pytest.mark.skipif(
                not self.is_service_running('clickhouse'),
                reason="ClickHouse未运行，请启动ClickHouse服务"
            ),
            'requires_message_broker': pytest.mark.skipif(
                not self.is_service_running('message-broker-service'),
                reason="消息代理服务未运行"
            ),
            'requires_data_storage': pytest.mark.skipif(
                not self.is_service_running('data-storage-service'),
                reason="数据存储服务未运行"
            ),
            'requires_core_services': pytest.mark.skipif(
                not all([
                    self.is_service_running('monitoring-service'),
                    self.is_service_running('message-broker-service')
                ]),
                reason="核心微服务未完全运行"
            )
        }


# 全局服务管理器
service_manager = ServiceManager()

# 获取跳过条件装饰器
service_decorators = service_manager.get_skip_conditions()

# 导出装饰器
requires_monitoring = service_decorators['requires_monitoring']
requires_nats = service_decorators['requires_nats']
requires_clickhouse = service_decorators['requires_clickhouse']
requires_message_broker = service_decorators['requires_message_broker']
requires_data_storage = service_decorators['requires_data_storage']
requires_core_services = service_decorators['requires_core_services']


def check_service_status():
    """检查服务状态并打印报告"""
    report = service_manager.get_service_health_report()
    
    print("🔧 服务状态检查:")
    print("  ├─ 微服务:")
    for service, status in report['microservices'].items():
        print(f"      ├─ {service}: {'✅' if status else '❌'}")
    
    print("  └─ 基础设施:")
    for service, status in report['infrastructure'].items():
        print(f"      ├─ {service}: {'✅' if status else '❌'}")
    
    print(f"\n📊 总结: {report['summary']['running_services']}/{report['summary']['total_services']} 服务运行中")
    
    if report['summary']['failed_services']:
        print(f"❌ 未运行的服务: {', '.join(report['summary']['failed_services'])}")
    
    return report


if __name__ == "__main__":
    # 测试服务管理器
    check_service_status() 