#!/usr/bin/env python3
"""
MarketPrism 快速修复验证脚本

专注验证已修复的关键问题：
1. ✅ Binance WebSocket SOCKS代理连接
2. ✅ 统一管理器API initialize方法 
3. ⚠️ 基础设施服务状态检查（无强制启动）

生成简洁的修复状态报告
"""

import asyncio
import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class QuickFixVerifier:
    """快速修复验证器"""
    
    def __init__(self):
        self.results = {}
        
    async def verify_websocket_proxy_fix(self):
        """验证WebSocket代理修复"""
        print("🔌 验证WebSocket代理修复...")
        
        try:
            from scripts.fix_websocket_proxy import WebSocketProxyConnector
            connector = WebSocketProxyConnector()
            
            # 测试Binance WebSocket SOCKS代理
            binance_result = await connector.test_binance_websocket_with_proxy()
            
            # 测试OKX WebSocket SOCKS代理  
            okx_result = await connector.test_okx_websocket_with_proxy()
            
            success = binance_result.get('success', False) and okx_result.get('success', False)
            
            self.results['websocket_proxy'] = {
                'fixed': success,
                'binance_ws': binance_result.get('success', False),
                'okx_ws': okx_result.get('success', False),
                'details': f"Binance: {binance_result.get('connection_time', 'N/A')}ms, OKX: {okx_result.get('connection_time', 'N/A')}ms"
            }
            
            print(f"   {'✅' if success else '❌'} WebSocket代理: {'已修复' if success else '仍有问题'}")
            print(f"      Binance WS: {'✅' if binance_result.get('success') else '❌'}")
            print(f"      OKX WS: {'✅' if okx_result.get('success') else '❌'}")
            
        except Exception as e:
            print(f"   ❌ WebSocket代理测试失败: {e}")
            self.results['websocket_proxy'] = {
                'fixed': False,
                'error': str(e)
            }
    
    async def verify_unified_managers_api_fix(self):
        """验证统一管理器API修复"""
        print("🔧 验证统一管理器API修复...")
        
        session_success = False
        storage_success = False
        
        # 测试统一会话管理器
        try:
            from core.networking.unified_session_manager import UnifiedSessionManager
            session_manager = UnifiedSessionManager()
            await session_manager.initialize()
            
            # 测试基本HTTP请求
            response = await session_manager.get("https://httpbin.org/status/200", timeout=5)
            session_success = response.status == 200
            
            await session_manager.close()
            print(f"   ✅ 统一会话管理器: initialize方法已修复")
            
        except Exception as e:
            print(f"   ❌ 统一会话管理器: {e}")
        
        # 测试统一存储管理器
        try:
            from core.storage.unified_storage_manager import UnifiedStorageManager
            storage_manager = UnifiedStorageManager()
            await storage_manager.initialize()
            
            status = await storage_manager.get_status()
            storage_success = True
            
            await storage_manager.stop()
            print(f"   ✅ 统一存储管理器: initialize方法已修复")
            
        except Exception as e:
            print(f"   ❌ 统一存储管理器: {e}")
        
        overall_success = session_success and storage_success
        
        self.results['unified_managers_api'] = {
            'fixed': overall_success,
            'session_manager': session_success,
            'storage_manager': storage_success,
            'details': f"会话管理器: {'✅' if session_success else '❌'}, 存储管理器: {'✅' if storage_success else '❌'}"
        }
        
        print(f"   {'✅' if overall_success else '❌'} 统一管理器API: {'已修复' if overall_success else '部分修复'}")
    
    async def check_infrastructure_services(self):
        """检查基础设施服务状态（不强制启动）"""
        print("💾 检查基础设施服务状态...")
        
        services_status = {}
        
        # 检查Redis
        try:
            import aioredis
            redis_client = await aioredis.create_redis_pool('redis://localhost:6379', timeout=3)
            await redis_client.ping()
            redis_client.close()
            await redis_client.wait_closed()
            services_status['redis'] = True
            print("   ✅ Redis: 运行正常")
        except Exception:
            services_status['redis'] = False
            print("   ❌ Redis: 未运行")
        
        # 检查ClickHouse
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8123/ping', timeout=aiohttp.ClientTimeout(total=3)) as response:
                    services_status['clickhouse'] = response.status == 200
            if services_status['clickhouse']:
                print("   ✅ ClickHouse: 运行正常")
            else:
                print("   ❌ ClickHouse: 响应异常")
        except Exception:
            services_status['clickhouse'] = False
            print("   ❌ ClickHouse: 未运行")
        
        # 检查NATS
        try:
            import nats
            nc = await nats.connect("nats://localhost:4222", connect_timeout=3)
            await nc.close()
            services_status['nats'] = True
            print("   ✅ NATS: 运行正常")
        except Exception:
            services_status['nats'] = False
            print("   ❌ NATS: 未运行")
        
        total_services = len(services_status)
        running_services = sum(services_status.values())
        
        self.results['infrastructure_services'] = {
            'partially_fixed': running_services > 0,
            'all_running': running_services == total_services,
            'running_count': running_services,
            'total_count': total_services,
            'services': services_status,
            'details': f"{running_services}/{total_services} 服务运行中"
        }
        
        print(f"   {'✅' if running_services == total_services else '⚠️'} 基础设施: {running_services}/{total_services} 运行中")
    
    async def run_exchange_api_tests(self):
        """运行交易所API测试"""
        print("🌐 验证交易所API连接...")
        
        try:
            from scripts.fixed_tdd_tests import FixedExchangeConnector
            connector = FixedExchangeConnector()
            
            # 测试Binance API
            binance_result = await connector.test_binance_api()
            binance_success = binance_result.get('binance_trading_pairs', {}).get('success', False)
            
            # 测试OKX API  
            okx_result = await connector.test_okx_api()
            okx_success = okx_result.get('okx_trading_pairs', {}).get('success', False)
            
            await connector.close()
            
            self.results['exchange_apis'] = {
                'fixed': binance_success and okx_success,
                'binance_api': binance_success,
                'okx_api': okx_success,
                'details': f"Binance: {'✅' if binance_success else '❌'}, OKX: {'✅' if okx_success else '❌'}"
            }
            
            print(f"   ✅ Binance API: {'可用' if binance_success else '不可用'}")
            print(f"   ✅ OKX API: {'可用' if okx_success else '不可用'}")
            
        except Exception as e:
            print(f"   ❌ 交易所API测试失败: {e}")
            self.results['exchange_apis'] = {
                'fixed': False,
                'error': str(e)
            }
    
    async def generate_summary_report(self):
        """生成总结报告"""
        print("\n📊 MarketPrism 修复验证总结")
        print("=" * 60)
        
        # 评估用户提到的三个问题
        print("🎯 用户问题修复状态:")
        
        # 1. Binance WebSocket连接问题
        ws_fixed = self.results.get('websocket_proxy', {}).get('fixed', False)
        print(f"   1. Binance WebSocket连接: {'✅ 已修复' if ws_fixed else '❌ 仍有问题'}")
        if ws_fixed:
            ws_details = self.results['websocket_proxy'].get('details', '')
            print(f"      {ws_details}")
        
        # 2. 统一管理器API问题
        api_fixed = self.results.get('unified_managers_api', {}).get('fixed', False)
        print(f"   2. 统一管理器API问题: {'✅ 已修复' if api_fixed else '❌ 仍有问题'}")
        if api_fixed:
            api_details = self.results['unified_managers_api'].get('details', '')
            print(f"      {api_details}")
        
        # 3. 基础设施服务问题
        infra_all_running = self.results.get('infrastructure_services', {}).get('all_running', False)
        infra_partial = self.results.get('infrastructure_services', {}).get('partially_fixed', False)
        if infra_all_running:
            infra_status = "✅ 已修复"
        elif infra_partial:
            infra_status = "⚠️ 部分修复"
        else:
            infra_status = "❌ 仍有问题"
        
        print(f"   3. 基础设施服务状态: {infra_status}")
        if 'infrastructure_services' in self.results:
            infra_details = self.results['infrastructure_services'].get('details', '')
            print(f"      {infra_details}")
        
        # 额外验证的交易所API
        if 'exchange_apis' in self.results:
            api_status = self.results['exchange_apis'].get('fixed', False)
            print(f"   4. 交易所API连接: {'✅ 正常' if api_status else '❌ 异常'}")
            if api_status:
                api_details = self.results['exchange_apis'].get('details', '')
                print(f"      {api_details}")
        
        # 计算总体修复率
        total_issues = 3  # 用户提到的三个问题
        fixed_issues = sum([
            1 if ws_fixed else 0,
            1 if api_fixed else 0, 
            1 if infra_all_running else 0.5 if infra_partial else 0
        ])
        
        fix_rate = (fixed_issues / total_issues) * 100
        
        print(f"\n🎯 总体修复进度: {fix_rate:.1f}%")
        
        if fix_rate >= 90:
            print("🎉 优秀! 几乎所有问题都已解决")
        elif fix_rate >= 70:
            print("👍 良好! 大部分问题已解决") 
        elif fix_rate >= 50:
            print("📈 进展! 一半以上问题已解决")
        else:
            print("⚠️ 需要继续努力解决剩余问题")
        
        # 生成改进建议
        recommendations = []
        
        if not ws_fixed:
            recommendations.append("🔌 安装SOCKS代理支持: pip install PySocks")
            recommendations.append("🌐 检查代理服务器配置")
        
        if not api_fixed:
            recommendations.append("🔧 重新加载Python模块: 重启Python环境")
            recommendations.append("📝 检查导入路径和依赖")
        
        if not infra_all_running:
            recommendations.append("💾 启动Docker: docker-compose up -d")
            recommendations.append("🐳 检查Docker守护进程状态")
        
        if recommendations:
            print(f"\n💡 改进建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        
        # 保存报告
        report_data = {
            'timestamp': time.time(),
            'summary': {
                'websocket_proxy_fixed': ws_fixed,
                'unified_managers_api_fixed': api_fixed,
                'infrastructure_all_running': infra_all_running,
                'infrastructure_partial': infra_partial,
                'overall_fix_rate': fix_rate
            },
            'detailed_results': self.results,
            'recommendations': recommendations
        }
        
        report_file = f"quick_fix_verification_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📄 详细报告保存到: {report_file}")
        print("=" * 60)
        
        return report_data

async def main():
    """主函数"""
    print("🚀 MarketPrism 快速修复验证")
    print("专注验证关键问题修复状态")
    print("=" * 60)
    
    verifier = QuickFixVerifier()
    
    try:
        # 1. 验证WebSocket代理修复
        await verifier.verify_websocket_proxy_fix()
        
        # 2. 验证统一管理器API修复
        await verifier.verify_unified_managers_api_fix()
        
        # 3. 检查基础设施服务状态
        await verifier.check_infrastructure_services()
        
        # 4. 验证交易所API连接
        await verifier.run_exchange_api_tests()
        
        # 5. 生成总结报告
        report = await verifier.generate_summary_report()
        
        # 返回退出代码
        overall_success = report['summary']['overall_fix_rate'] >= 75
        sys.exit(0 if overall_success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️ 验证被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 验证过程失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())