#!/usr/bin/env python3
"""
MarketPrism TDD 测试环境一键设置脚本
支持代理配置、真实环境搭建、微服务启动

使用方法：
    python scripts/tdd_setup.py --setup        # 设置环境
    python scripts/tdd_setup.py --test         # 运行测试
    python scripts/tdd_setup.py --cleanup      # 清理环境
    python scripts/tdd_setup.py --status       # 查看状态
"""

import asyncio
import argparse
import sys
import os
import time
import signal
from pathlib import Path
import subprocess
import yaml
import aiohttp
import redis

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment


class TDDEnvironmentManager:
    """TDD测试环境管理器"""
    
    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.config_path = self.project_root / "config" / "test_config.yaml"
        self.test_base = RealTestBase()
        self.environment = None
    
    async def setup_environment(self):
        """设置TDD测试环境"""
        print("🚀 开始设置TDD测试环境...")
        
        try:
            # 1. 验证配置文件
            if not self.config_path.exists():
                print(f"❌ 配置文件不存在: {self.config_path}")
                print("请先运行以下命令创建配置文件：")
                print(f"cp {self.project_root}/config/test_config.yaml.example {self.config_path}")
                return False
            
            # 2. 检查基础设施依赖
            print("📋 检查基础设施依赖...")
            
            dependencies = await self._check_dependencies()
            
            for dep_name, status in dependencies.items():
                status_icon = "✅" if status else "❌"
                print(f"   {status_icon} {dep_name}")
            
            missing_deps = [name for name, status in dependencies.items() if not status]
            if missing_deps:
                print(f"\n❌ 缺少依赖: {', '.join(missing_deps)}")
                print("请安装缺少的依赖后重试")
                return False
            
            # 3. 设置完整环境
            print("\n🔧 设置完整测试环境...")
            self.environment = await self.test_base.setup_test_environment()
            
            # 4. 验证环境状态
            success = await self._verify_environment()
            
            if success:
                print("\n🎉 TDD测试环境设置成功！")
                await self._print_quick_start_guide()
                return True
            else:
                print("\n❌ TDD测试环境设置失败")
                return False
                
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断设置过程")
            return False
        except Exception as e:
            print(f"\n❌ 设置环境时出错: {e}")
            return False
    
    async def _check_dependencies(self):
        """检查基础设施依赖"""
        dependencies = {}
        
        # 检查Python依赖
        try:
            import aiohttp, websockets, redis, pytest, yaml
            dependencies["Python依赖"] = True
        except ImportError as e:
            print(f"缺少Python包: {e}")
            dependencies["Python依赖"] = False
        
        # 检查Redis
        try:
            redis_client = redis.Redis(host='localhost', port=6379, socket_timeout=3)
            redis_client.ping()
            dependencies["Redis"] = True
        except Exception:
            dependencies["Redis"] = False
        
        # 检查网络连接（ping百度）
        try:
            proc = await asyncio.create_subprocess_exec(
                'ping', '-c', '1', 'www.baidu.com',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
            dependencies["网络连接"] = proc.returncode == 0
        except Exception:
            dependencies["网络连接"] = False
        
        # 检查代理（如果配置了）
        config = self.test_base.config
        if config.get('proxy', {}).get('enabled', False):
            proxy_url = config['proxy'].get('http_proxy', '')
            if proxy_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            'https://httpbin.org/ip',
                            proxy=proxy_url,
                            timeout=10
                        ) as response:
                            dependencies["代理服务"] = response.status == 200
                except Exception:
                    dependencies["代理服务"] = False
            else:
                dependencies["代理服务"] = False
        else:
            dependencies["代理服务"] = True  # 未配置代理时视为正常
        
        return dependencies
    
    async def _verify_environment(self):
        """验证环境状态"""
        if not self.environment:
            return False
        
        print("🔍 验证环境状态...")
        
        # 检查服务健康度
        total_services = len(self.environment.services_running)
        healthy_services = sum(self.environment.services_running.values())
        health_percentage = (healthy_services / total_services) * 100 if total_services > 0 else 0
        
        print(f"   服务健康度: {health_percentage:.1f}% ({healthy_services}/{total_services})")
        
        # 检查数据库状态
        healthy_dbs = sum(self.environment.databases_ready.values())
        total_dbs = len(self.environment.databases_ready)
        
        print(f"   数据库状态: {healthy_dbs}/{total_dbs} 正常")
        
        # 验证关键服务
        critical_services = ['api_gateway', 'market_data_collector', 'data_storage']
        critical_healthy = all(
            self.environment.services_running.get(service, False) 
            for service in critical_services
        )
        
        if critical_healthy:
            print("   ✅ 关键服务全部正常")
        else:
            print("   ❌ 部分关键服务异常")
            for service in critical_services:
                status = self.environment.services_running.get(service, False)
                status_icon = "✅" if status else "❌"
                print(f"      {status_icon} {service}")
        
        return health_percentage >= 80 and critical_healthy
    
    async def _print_quick_start_guide(self):
        """打印快速开始指南"""
        print("\n" + "="*60)
        print("🎯 TDD测试快速开始指南")
        print("="*60)
        
        print("\n📝 运行基础测试：")
        print("   python -m pytest tests/tdd/test_real_data_storage.py -v")
        print("   python -m pytest tests/tdd/test_real_market_data_collector.py -v")
        
        print("\n📝 运行交易所集成测试：")
        print("   python -m pytest tests/tdd/test_real_exchange_integration.py -v")
        
        print("\n📝 运行API网关测试：")
        print("   python -m pytest tests/tdd/test_real_api_gateway.py -v")
        
        print("\n📝 运行端到端测试：")
        print("   python -m pytest tests/tdd/test_real_end_to_end.py -v")
        
        print("\n📝 运行完整TDD测试套件：")
        print("   python -m pytest tests/tdd/ -v --tb=short")
        
        print("\n📝 运行特定测试类型：")
        print("   python -m pytest tests/tdd/ -m 'not requires_real_network' -v")
        print("   python -m pytest tests/tdd/ -k 'storage' -v")
        print("   python -m pytest tests/tdd/ -k 'exchange' -v")
        print("   python -m pytest tests/tdd/ -k 'gateway' -v")
        print("   python -m pytest tests/tdd/ -k 'end_to_end' -v")
        
        print("\n📝 生成测试报告：")
        print("   python -m pytest tests/tdd/ --html=reports/tdd_report.html")
        
        print("\n📝 查看环境状态：")
        print("   python scripts/tdd_setup.py --status")
        
        print("\n📝 清理环境：")
        print("   python scripts/tdd_setup.py --cleanup")
        
        print("\n🔗 服务端点：")
        if self.environment:
            for service_name, config in self.environment.config['services'].items():
                status = self.environment.services_running.get(service_name, False)
                status_icon = "✅" if status else "❌"
                url = f"http://{config['host']}:{config['port']}"
                print(f"   {status_icon} {service_name}: {url}")
        
        print("="*60)
    
    async def run_tests(self, test_pattern=None, test_type=None):
        """运行TDD测试"""
        print("🧪 开始运行TDD测试...")
        
        # 确保环境已设置
        if not self.environment:
            print("设置测试环境...")
            success = await self.setup_environment()
            if not success:
                print("❌ 环境设置失败，无法运行测试")
                return False
        
        # 智能选择测试
        test_files = self._select_test_files(test_type, test_pattern)
        
        # 构建pytest命令
        cmd = [sys.executable, '-m', 'pytest'] + test_files + ['-v']
        
        if test_pattern:
            cmd.extend(['-k', test_pattern])
        
        # 添加其他有用的选项
        cmd.extend([
            '--tb=short',  # 简短的回溯信息
            '--durations=10',  # 显示最慢的10个测试
            '--color=yes'  # 彩色输出
        ])
        
        print(f"运行命令: {' '.join(cmd)}")
        
        try:
            # 运行测试
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            # 实时输出测试结果
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                print(line.decode().rstrip())
            
            await process.wait()
            
            if process.returncode == 0:
                print("\n🎉 所有测试通过！")
                return True
            else:
                print(f"\n❌ 测试失败，退出码: {process.returncode}")
                return False
                
        except KeyboardInterrupt:
            print("\n⚠️ 测试被用户中断")
            if process:
                process.terminate()
                await process.wait()
            return False
    
    def _select_test_files(self, test_type, test_pattern):
        """智能选择测试文件"""
        test_dir = self.project_root / "tests" / "tdd"
        
        if test_type == "basic":
            return [
                str(test_dir / "test_real_data_storage.py"),
                str(test_dir / "test_real_market_data_collector.py")
            ]
        elif test_type == "exchange":
            return [
                str(test_dir / "test_real_exchange_integration.py")
            ]
        elif test_type == "gateway":
            return [
                str(test_dir / "test_real_api_gateway.py")
            ]
        elif test_type == "e2e":
            return [
                str(test_dir / "test_real_end_to_end.py")
            ]
        elif test_type == "integration":
            return [
                str(test_dir / "test_real_exchange_integration.py"),
                str(test_dir / "test_real_api_gateway.py")
            ]
        else:
            # 默认运行所有TDD测试
            return [str(test_dir)]
    
    async def cleanup_environment(self):
        """清理测试环境"""
        print("🧹 开始清理TDD测试环境...")
        
        try:
            if self.environment:
                await self.test_base.cleanup_test_environment()
            
            print("✅ 环境清理完成")
            return True
            
        except Exception as e:
            print(f"❌ 清理环境时出错: {e}")
            return False
    
    async def show_status(self):
        """显示环境状态"""
        print("📊 TDD测试环境状态")
        print("="*50)
        
        # 检查配置文件
        if self.config_path.exists():
            print("✅ 配置文件存在")
        else:
            print("❌ 配置文件不存在")
            return
        
        # 检查基础设施
        print("\n📋 基础设施状态：")
        dependencies = await self._check_dependencies()
        
        for dep_name, status in dependencies.items():
            status_icon = "✅" if status else "❌"
            print(f"   {status_icon} {dep_name}")
        
        # 检查服务状态
        print("\n🚀 微服务状态：")
        
        config = self.test_base.config
        for service_name, service_config in config['services'].items():
            url = f"http://{service_config['host']}:{service_config['port']}"
            health_endpoint = service_config['health_endpoint']
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{url}{health_endpoint}", timeout=5) as response:
                        if response.status == 200:
                            print(f"   ✅ {service_name}: {url}")
                        else:
                            print(f"   ❌ {service_name}: {url} (状态码: {response.status})")
            except Exception:
                print(f"   ❌ {service_name}: {url} (连接失败)")
        
        print("="*50)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism TDD测试环境管理')
    parser.add_argument('--setup', action='store_true', help='设置测试环境')
    parser.add_argument('--test', action='store_true', help='运行TDD测试')
    parser.add_argument('--cleanup', action='store_true', help='清理测试环境')
    parser.add_argument('--status', action='store_true', help='查看环境状态')
    parser.add_argument('--pattern', type=str, help='测试过滤模式')
    parser.add_argument('--type', type=str, choices=['basic', 'exchange', 'gateway', 'e2e', 'integration'], 
                       help='测试类型: basic(基础), exchange(交易所), gateway(网关), e2e(端到端), integration(集成)')
    
    args = parser.parse_args()
    
    manager = TDDEnvironmentManager()
    
    try:
        if args.setup:
            success = await manager.setup_environment()
            sys.exit(0 if success else 1)
        
        elif args.test:
            success = await manager.run_tests(args.pattern, args.type)
            sys.exit(0 if success else 1)
        
        elif args.cleanup:
            success = await manager.cleanup_environment()
            sys.exit(0 if success else 1)
        
        elif args.status:
            await manager.show_status()
            sys.exit(0)
        
        else:
            # 默认显示帮助和状态
            parser.print_help()
            print("\n🎯 TDD测试类型说明：")
            print("   basic: 基础服务测试（数据存储、数据采集）")
            print("   exchange: 交易所API集成测试（Binance、OKX）")
            print("   gateway: API网关测试（路由、负载均衡、限流）")
            print("   e2e: 端到端测试（完整数据流）")
            print("   integration: 集成测试（综合验证）")
            print("\n当前环境状态：")
            await manager.show_status()
    
    except KeyboardInterrupt:
        print("\n⚠️ 操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 操作失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 处理信号
    def signal_handler(signum, frame):
        print("\n⚠️ 收到中断信号，正在清理...")
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    asyncio.run(main())