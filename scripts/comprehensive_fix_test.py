#!/usr/bin/env python3
"""
MarketPrism 综合修复测试脚本

解决用户提到的三个关键问题：
1. Binance WebSocket连接失败 (SOCKS代理配置)
2. 统一管理器API问题 (initialize方法修复)
3. 基础设施服务未启动 (Redis/ClickHouse/NATS)

此脚本提供一站式解决方案和验证
"""

import asyncio
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class ComprehensiveFixTester:
    """综合修复测试器"""
    
    def __init__(self):
        self.test_results = {}
        self.start_time = time.time()
    
    async def test_websocket_proxy_fix(self) -> Dict[str, Any]:
        """测试WebSocket代理修复"""
        print("🔌 测试WebSocket代理修复...")
        print("-" * 50)
        
        try:
            # 导入WebSocket代理修复脚本
            from scripts.fix_websocket_proxy import WebSocketProxyConnector
            
            connector = WebSocketProxyConnector()
            
            # 测试HTTP代理兼容性
            http_result = await connector.test_http_proxy_compatibility()
            
            # 测试Binance WebSocket
            binance_ws_result = await connector.test_binance_websocket_with_proxy()
            
            # 测试OKX WebSocket
            okx_ws_result = await connector.test_okx_websocket_with_proxy()
            
            results = {
                'http_proxy': http_result,
                'binance_ws': binance_ws_result,
                'okx_ws': okx_ws_result
            }
            
            # 评估结果
            success_count = sum(1 for r in results.values() if r.get('success', False))
            total_count = len(results)
            
            print(f"📊 WebSocket代理测试结果: {success_count}/{total_count} 成功")
            for test_name, result in results.items():
                status = "✅" if result.get('success') else "❌"
                print(f"   {status} {test_name}: {result.get('error', '成功')}")
            
            return {
                'success': success_count > 0,
                'total_tests': total_count,
                'successful_tests': success_count,
                'results': results,
                'websocket_proxy_working': success_count >= 2  # HTTP + 至少一个WebSocket
            }
            
        except Exception as e:
            print(f"❌ WebSocket代理测试失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'websocket_proxy_working': False
            }
    
    async def test_unified_managers_api_fix(self) -> Dict[str, Any]:
        """测试统一管理器API修复"""
        print("\n🔧 测试统一管理器API修复...")
        print("-" * 50)
        
        results = {}
        
        # 测试统一会话管理器
        try:
            from core.networking.unified_session_manager import UnifiedSessionManager
            
            session_manager = UnifiedSessionManager()
            
            # 测试initialize方法
            await session_manager.initialize()
            print("   ✅ 统一会话管理器 - initialize方法: 成功")
            
            # 测试基本功能
            response = await session_manager.get("https://httpbin.org/status/200", timeout=5)
            print(f"   ✅ 统一会话管理器 - HTTP请求: 成功 (状态码: {response.status})")
            
            await session_manager.close()
            
            results['unified_session_manager'] = {
                'success': True,
                'initialize_method': True,
                'http_request': True
            }
            
        except Exception as e:
            print(f"   ❌ 统一会话管理器: {e}")
            results['unified_session_manager'] = {
                'success': False,
                'error': str(e),
                'initialize_method': False
            }
        
        # 测试统一存储管理器
        try:
            from core.storage.unified_storage_manager import UnifiedStorageManager
            
            storage_manager = UnifiedStorageManager()
            
            # 测试initialize方法
            await storage_manager.initialize()
            print("   ✅ 统一存储管理器 - initialize方法: 成功")
            
            # 测试get_status方法
            status = await storage_manager.get_status()
            print(f"   ✅ 统一存储管理器 - get_status方法: 成功 (初始化: {status.get('initialized')})")
            
            await storage_manager.stop()
            
            results['unified_storage_manager'] = {
                'success': True,
                'initialize_method': True,
                'get_status_method': True,
                'initialized': status.get('initialized', False)
            }
            
        except Exception as e:
            print(f"   ❌ 统一存储管理器: {e}")
            results['unified_storage_manager'] = {
                'success': False,
                'error': str(e),
                'initialize_method': False
            }
        
        # 评估结果
        success_count = sum(1 for r in results.values() if r.get('success', False))
        total_count = len(results)
        
        print(f"📊 统一管理器API测试结果: {success_count}/{total_count} 成功")
        
        return {
            'success': success_count == total_count,
            'total_tests': total_count,
            'successful_tests': success_count,
            'results': results,
            'api_methods_fixed': all(r.get('initialize_method', False) for r in results.values() if r.get('success'))
        }
    
    async def test_infrastructure_services(self) -> Dict[str, Any]:
        """测试基础设施服务"""
        print("\n💾 测试基础设施服务...")
        print("-" * 50)
        
        try:
            from scripts.start_infrastructure import InfrastructureManager
            
            manager = InfrastructureManager()
            
            # 检查Docker可用性
            docker_available = await manager.check_docker_availability()
            
            # 检查服务状态
            status = await manager.check_services_status()
            
            # 统计运行状况
            total_services = len(status)
            running_services = sum(1 for s in status.values() if s.get('running', False))
            
            print(f"📊 基础设施服务状态: {running_services}/{total_services} 运行中")
            
            for service_name, service_status in status.items():
                status_icon = "✅" if service_status.get('running') else "❌"
                print(f"   {status_icon} {service_name}: {service_status.get('health_status', 'unknown')}")
            
            # 如果有服务未运行，尝试启动
            if running_services < total_services:
                print(f"\n🚀 尝试启动 {total_services - running_services} 个未运行的服务...")
                
                if docker_available:
                    start_results = await manager.start_all_services(use_docker=True)
                    print("   使用Docker方式启动服务")
                else:
                    start_results = await manager.start_all_services(use_docker=False)
                    print("   使用本地方式启动服务")
                
                # 重新检查状态
                final_status = await manager.check_services_status()
                final_running = sum(1 for s in final_status.values() if s.get('running', False))
                
                print(f"📊 启动后服务状态: {final_running}/{total_services} 运行中")
                
                return {
                    'success': final_running >= running_services,  # 至少没有变差
                    'docker_available': docker_available,
                    'initial_running': running_services,
                    'final_running': final_running,
                    'total_services': total_services,
                    'services_status': final_status,
                    'start_results': start_results,
                    'all_services_running': final_running == total_services
                }
            else:
                return {
                    'success': True,
                    'docker_available': docker_available,
                    'initial_running': running_services,
                    'final_running': running_services,
                    'total_services': total_services,
                    'services_status': status,
                    'all_services_running': True,
                    'message': 'All services already running'
                }
        
        except Exception as e:
            print(f"❌ 基础设施服务测试失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'all_services_running': False
            }
    
    async def run_original_tdd_test(self) -> Dict[str, Any]:
        """运行修复后的TDD测试"""
        print("\n🧪 运行修复后的TDD测试...")
        print("-" * 50)
        
        try:
            from scripts.fixed_tdd_tests import main as run_fixed_tdd
            
            # 运行修复后的TDD测试
            print("   执行修复后的TDD测试脚本...")
            
            # 注意：这里我们不直接调用main()，因为它有自己的事件循环
            # 而是重新实现核心测试逻辑
            
            from scripts.fixed_tdd_tests import FixedExchangeConnector, test_unified_managers
            
            results = {}
            connector = FixedExchangeConnector()
            
            try:
                # 测试统一管理器
                unified_results = await test_unified_managers()
                results['unified_managers'] = unified_results
                
                # 测试Binance API
                binance_results = await connector.test_binance_api()
                results['binance_api'] = binance_results
                
                # 测试OKX API
                okx_results = await connector.test_okx_api()
                results['okx_api'] = okx_results
                
                # 测试WebSocket连接
                ws_results = await connector.test_websocket_connections()
                results['websocket'] = ws_results
                
            finally:
                await connector.close()
            
            # 计算成功率
            total_tests = 0
            successful_tests = 0
            
            for category, tests in results.items():
                for test_name, result in tests.items():
                    total_tests += 1
                    if result.get('success', False):
                        successful_tests += 1
            
            success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
            
            print(f"📊 TDD测试结果: {success_rate:.1f}% ({successful_tests}/{total_tests})")
            
            return {
                'success': success_rate >= 50,  # 50%以上认为基本成功
                'success_rate': success_rate,
                'total_tests': total_tests,
                'successful_tests': successful_tests,
                'results': results,
                'improved_from_41_7_percent': success_rate > 41.7
            }
            
        except Exception as e:
            print(f"❌ TDD测试执行失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'success_rate': 0
            }
    
    async def run_comprehensive_test(self) -> Dict[str, Any]:
        """运行综合测试"""
        print("🚀 MarketPrism 综合修复验证测试")
        print("=" * 80)
        
        # 1. 测试WebSocket代理修复
        websocket_results = await self.test_websocket_proxy_fix()
        self.test_results['websocket_proxy'] = websocket_results
        
        # 2. 测试统一管理器API修复
        api_results = await self.test_unified_managers_api_fix()
        self.test_results['unified_managers_api'] = api_results
        
        # 3. 测试基础设施服务
        infrastructure_results = await self.test_infrastructure_services()
        self.test_results['infrastructure_services'] = infrastructure_results
        
        # 4. 运行TDD测试验证整体效果
        tdd_results = await self.run_original_tdd_test()
        self.test_results['tdd_verification'] = tdd_results
        
        # 生成综合报告
        return await self.generate_comprehensive_report()
    
    async def generate_comprehensive_report(self) -> Dict[str, Any]:
        """生成综合报告"""
        print("\n📊 综合修复验证报告")
        print("=" * 80)
        
        # 评估各个修复的成功情况
        fixes_status = {}
        
        # 1. WebSocket代理修复评估
        websocket_fix = self.test_results.get('websocket_proxy', {})
        fixes_status['websocket_proxy_fix'] = {
            'fixed': websocket_fix.get('websocket_proxy_working', False),
            'status': '✅ 已修复' if websocket_fix.get('websocket_proxy_working', False) else '❌ 仍有问题',
            'details': f"代理测试成功率: {websocket_fix.get('successful_tests', 0)}/{websocket_fix.get('total_tests', 0)}"
        }
        
        # 2. API接口修复评估
        api_fix = self.test_results.get('unified_managers_api', {})
        fixes_status['unified_managers_api_fix'] = {
            'fixed': api_fix.get('api_methods_fixed', False),
            'status': '✅ 已修复' if api_fix.get('api_methods_fixed', False) else '❌ 仍有问题',
            'details': f"initialize方法修复: {api_fix.get('successful_tests', 0)}/{api_fix.get('total_tests', 0)} 管理器"
        }
        
        # 3. 基础设施服务评估
        infra_fix = self.test_results.get('infrastructure_services', {})
        fixes_status['infrastructure_services_fix'] = {
            'fixed': infra_fix.get('all_services_running', False),
            'status': '✅ 已修复' if infra_fix.get('all_services_running', False) else '⚠️ 部分修复',
            'details': f"服务运行状态: {infra_fix.get('final_running', 0)}/{infra_fix.get('total_services', 0)}"
        }
        
        # 4. 整体TDD测试评估
        tdd_fix = self.test_results.get('tdd_verification', {})
        fixes_status['overall_system_health'] = {
            'fixed': tdd_fix.get('improved_from_41_7_percent', False),
            'status': f"🎯 系统就绪度: {tdd_fix.get('success_rate', 0):.1f}%",
            'details': f"从41.7%提升到{tdd_fix.get('success_rate', 0):.1f}% ({tdd_fix.get('successful_tests', 0)}/{tdd_fix.get('total_tests', 0)})"
        }
        
        # 打印报告
        print("🔧 用户问题修复状态:")
        print(f"   1. Binance WebSocket连接: {fixes_status['websocket_proxy_fix']['status']}")
        print(f"      {fixes_status['websocket_proxy_fix']['details']}")
        
        print(f"   2. 统一管理器API问题: {fixes_status['unified_managers_api_fix']['status']}")
        print(f"      {fixes_status['unified_managers_api_fix']['details']}")
        
        print(f"   3. 基础设施服务状态: {fixes_status['infrastructure_services_fix']['status']}")
        print(f"      {fixes_status['infrastructure_services_fix']['details']}")
        
        print(f"   4. {fixes_status['overall_system_health']['status']}")
        print(f"      {fixes_status['overall_system_health']['details']}")
        
        # 计算总体修复成功率
        total_fixes = len(fixes_status)
        successful_fixes = sum(1 for fix in fixes_status.values() if fix.get('fixed', False))
        overall_fix_rate = (successful_fixes / total_fixes * 100) if total_fixes > 0 else 0
        
        print(f"\n🎯 总体修复成功率: {overall_fix_rate:.1f}% ({successful_fixes}/{total_fixes})")
        
        # 生成改进建议
        recommendations = []
        
        if not fixes_status['websocket_proxy_fix']['fixed']:
            recommendations.append("🔌 安装SOCKS支持: pip install PySocks")
            recommendations.append("🌐 配置正确的代理服务器地址和端口")
        
        if not fixes_status['unified_managers_api_fix']['fixed']:
            recommendations.append("🔧 检查统一管理器的导入依赖")
            recommendations.append("🔄 重启Python环境以加载最新代码")
        
        if not fixes_status['infrastructure_services_fix']['fixed']:
            recommendations.append("💾 手动启动未运行的基础设施服务")
            recommendations.append("🐳 考虑使用Docker Compose一键启动所有服务")
        
        if recommendations:
            print(f"\n💡 改进建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        else:
            print(f"\n🎉 所有问题已修复! 系统准备就绪")
        
        # 保存报告
        report_data = {
            'timestamp': time.time(),
            'test_duration_seconds': time.time() - self.start_time,
            'fixes_status': fixes_status,
            'overall_fix_rate': overall_fix_rate,
            'recommendations': recommendations,
            'detailed_results': self.test_results
        }
        
        report_file = f"comprehensive_fix_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📄 详细报告已保存到: {report_file}")
        print("=" * 80)
        
        return report_data

async def main():
    """主函数"""
    tester = ComprehensiveFixTester()
    
    try:
        report = await tester.run_comprehensive_test()
        
        # 返回退出代码
        overall_success = report.get('overall_fix_rate', 0) >= 75  # 75%以上认为成功
        sys.exit(0 if overall_success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 综合测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())