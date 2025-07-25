"""
统一测试环境管理器 - 集成网络和服务管理功能
"""
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

from .network_manager import NetworkManager, check_network_status
from .service_manager import ServiceManager, check_service_status


class Environment:
    """统一测试环境管理"""
    
    def __init__(self):
        self.network = NetworkManager()
        self.services = ServiceManager()
        self.setup_timestamp = datetime.now()
        
    def setup_test_session(self) -> Dict[str, Any]:
        """设置完整的测试会话环境"""
        print("🚀 初始化MarketPrism测试环境...")
        
        # 1. 配置代理环境变量
        self.network.configure_proxy_env()
        
        # 2. 设置Python路径
        os.environ['PYTHONPATH'] = '/Users/yao/Documents/GitHub/marketprism'
        
        # 3. 检查网络连通性
        print("\n🌐 检查网络连接...")
        network_status = check_network_status()
        
        # 4. 检查和启动核心服务
        print("\n🔧 检查服务状态...")
        service_status = check_service_status()
        
        # 5. 尝试启动核心测试服务
        print("\n⚡ 确保核心测试服务运行...")
        core_services_status = self.services.ensure_test_environment()
        
        # 6. 检查基础设施服务
        print("\n🏗️  检查基础设施服务...")
        infrastructure_status = self.services.check_infrastructure_services()
        
        # 汇总环境状态
        environment_status = {
            'timestamp': self.setup_timestamp.isoformat(),
            'proxy_configured': True,
            'python_path_set': True,
            'network': {
                'basic_connectivity': self.network.is_network_available(),
                'exchanges': network_status
            },
            'services': {
                'microservices': service_status['microservices'],
                'infrastructure': infrastructure_status,
                'core_services_started': core_services_status
            },
            'summary': {
                'ready_for_testing': self._is_ready_for_testing(network_status, core_services_status),
                'total_services_running': service_status['summary']['running_services'],
                'failed_services': service_status['summary']['failed_services']
            }
        }
        
        return environment_status
    
    def _is_ready_for_testing(self, network_status: Dict[str, bool], core_services: Dict[str, bool]) -> bool:
        """判断环境是否准备好进行测试"""
        # 至少要有一个交易所可用
        network_ok = any(network_status.values())
        
        # 核心服务至少要启动monitoring-service
        services_ok = core_services.get('monitoring-service', False)
        
        return network_ok and services_ok
    
    def get_environment_report(self) -> Dict[str, Any]:
        """生成详细的环境报告"""
        status = self.setup_test_session()
        
        print("\n" + "="*60)
        print("📋 MarketPrism 测试环境报告")
        print("="*60)
        
        # 网络状态
        print(f"🌐 网络连接: {'✅' if status['network']['basic_connectivity'] else '❌'}")
        print(f"🔧 代理配置: {'✅' if status['proxy_configured'] else '❌'}")
        
        print("\n📡 交易所连通性:")
        for exchange, available in status['network']['exchanges'].items():
            print(f"  ├─ {exchange}: {'✅' if available else '❌'}")
        
        # 服务状态
        print(f"\n🚀 核心微服务:")
        for service, running in status['services']['microservices'].items():
            print(f"  ├─ {service}: {'✅' if running else '❌'}")
        
        print(f"\n🏗️  基础设施:")
        for service, running in status['services']['infrastructure'].items():
            print(f"  ├─ {service}: {'✅' if running else '❌'}")
        
        # 总结
        print(f"\n📊 环境总结:")
        print(f"  ├─ 测试就绪: {'✅' if status['summary']['ready_for_testing'] else '❌'}")
        print(f"  ├─ 运行服务: {status['summary']['total_services_running']}")
        print(f"  └─ 失败服务: {len(status['summary']['failed_services'])}")
        
        if status['summary']['failed_services']:
            print(f"\n❌ 未运行的服务: {', '.join(status['summary']['failed_services'])}")
        
        if status['summary']['ready_for_testing']:
            print(f"\n✅ 环境准备完成！可以开始运行测试。")
        else:
            print(f"\n⚠️  环境未完全就绪，部分测试可能被跳过。")
            
        print("="*60)
        
        return status
    
    def save_environment_report(self, filename: str = None) -> str:
        """保存环境报告到文件"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tests/reports/environment_report_{timestamp}.json"
        
        # 确保报告目录存在
        os.makedirs("tests/reports", exist_ok=True)
        
        status = self.setup_test_session()
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
        
        print(f"📄 环境报告已保存: {filename}")
        return filename
    
    def cleanup(self):
        """清理测试环境"""
        print("🧹 清理测试环境...")
        self.services.cleanup_test_services()
        print("✅ 清理完成")
    
    def quick_health_check(self) -> bool:
        """快速健康检查"""
        network_ok = self.network.is_network_available()
        monitoring_ok = self.services.is_service_running('monitoring-service')
        
        return network_ok and monitoring_ok
    
    def get_test_recommendations(self) -> Dict[str, List[str]]:
        """获取测试建议"""
        status = self.setup_test_session()
        recommendations = {
            'can_run': [],
            'should_skip': [],
            'need_setup': []
        }
        
        # 网络相关测试建议
        if any(status['network']['exchanges'].values()):
            recommendations['can_run'].extend([
                '网络集成测试',
                '交易所API测试',
                '实时数据收集测试'
            ])
        else:
            recommendations['should_skip'].extend([
                '网络依赖测试',
                '真实API测试'
            ])
            recommendations['need_setup'].append('配置网络代理')
        
        # 服务相关测试建议
        if status['services']['core_services_started'].get('monitoring-service'):
            recommendations['can_run'].extend([
                '微服务集成测试',
                '监控系统测试'
            ])
        else:
            recommendations['need_setup'].append('启动核心微服务')
        
        if status['services']['infrastructure'].get('nats'):
            recommendations['can_run'].append('消息队列测试')
        else:
            recommendations['should_skip'].append('NATS相关测试')
        
        return recommendations


# 全局测试环境实例
test_env = Environment()


def setup_test_environment():
    """便捷函数：设置测试环境"""
    return test_env.setup_test_session()


def quick_check():
    """便捷函数：快速环境检查"""
    return test_env.quick_health_check()


def get_recommendations():
    """便捷函数：获取测试建议"""
    return test_env.get_test_recommendations()


if __name__ == "__main__":
    # 运行完整的环境检查
    test_env.get_environment_report()
    
    # 显示测试建议
    print("\n🎯 测试建议:")
    recs = get_recommendations()
    
    if recs['can_run']:
        print("✅ 可以运行:")
        for item in recs['can_run']:
            print(f"  ├─ {item}")
    
    if recs['should_skip']:
        print("⏭️  建议跳过:")
        for item in recs['should_skip']:
            print(f"  ├─ {item}")
    
    if recs['need_setup']:
        print("⚙️  需要设置:")
        for item in recs['need_setup']:
            print(f"  ├─ {item}") 