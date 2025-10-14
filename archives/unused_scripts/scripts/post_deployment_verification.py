#!/usr/bin/env python3
"""
MarketPrism 部署后验证脚本

在新部署或环境中自动验证所有关键功能，确保系统正常工作
"""

import asyncio
import aiohttp
import json
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Any


class PostDeploymentVerifier:
    """部署后验证器"""
    
    def __init__(self):
        self.verification_results = {}
        self.errors = []
        self.warnings = []
    
    async def run_verification(self):
        """运行完整的部署后验证"""
        print("🔍 MarketPrism 部署后验证")
        print("=" * 50)
        
        # 验证步骤
        verification_steps = [
            ("检查Python环境", self._verify_python_environment),
            ("检查依赖版本", self._verify_dependencies),
            ("检查基础设施服务", self._verify_infrastructure_services),
            ("检查Data Collector", self._verify_data_collector),
            ("验证NATS推送功能", self._verify_nats_push_functionality),
            ("检查配置文件", self._verify_configuration_files),
            ("运行端到端测试", self._run_end_to_end_test)
        ]
        
        for step_name, step_func in verification_steps:
            print(f"\n📋 {step_name}...")
            try:
                await step_func()
                print(f"  ✅ {step_name} - 通过")
            except Exception as e:
                self.errors.append(f"{step_name}: {str(e)}")
                print(f"  ❌ {step_name} - 失败: {e}")
        
        # 生成验证报告
        self._generate_verification_report()
    
    async def _verify_python_environment(self):
        """验证Python环境"""
        import sys
        
        # 检查Python版本
        if sys.version_info < (3, 8):
            raise Exception(f"Python版本过低: {sys.version_info}, 需要3.8+")
        
        # 检查虚拟环境
        if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            self.warnings.append("未检测到虚拟环境，建议使用虚拟环境")
    
    async def _verify_dependencies(self):
        """验证依赖版本"""
        try:
            import nats
            # 检查nats-py版本
            if hasattr(nats, '__version__'):
                version = nats.__version__
                if not version.startswith('2.2'):
                    raise Exception(f"nats-py版本不正确: {version}, 需要2.2.x")
        except ImportError:
            raise Exception("nats-py未安装")
        
        # 检查其他关键依赖
        required_packages = ['aiohttp', 'structlog', 'pyyaml']
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                raise Exception(f"缺少依赖包: {package}")
    
    async def _verify_infrastructure_services(self):
        """验证基础设施服务"""
        async with aiohttp.ClientSession() as session:
            # 检查NATS
            try:
                async with session.get('http://localhost:8222/varz') as response:
                    if response.status != 200:
                        raise Exception(f"NATS服务器状态异常: HTTP {response.status}")
                    data = await response.json()
                    if 'version' not in data:
                        raise Exception("NATS服务器响应格式异常")
            except Exception as e:
                raise Exception(f"NATS服务器连接失败: {e}")
            
            # 检查ClickHouse（如果配置了）
            try:
                async with session.get('http://localhost:8123/ping') as response:
                    if response.status == 200:
                        print("  ✅ ClickHouse连接正常")
            except:
                self.warnings.append("ClickHouse连接失败（可能未启动）")
    
    async def _verify_data_collector(self):
        """验证Data Collector"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get('http://localhost:8084/api/v1/status') as response:
                    if response.status != 200:
                        raise Exception(f"Data Collector状态异常: HTTP {response.status}")
                    
                    data = await response.json()
                    service_data = data.get('data', {})
                    
                    if service_data.get('status') != 'running':
                        raise Exception(f"Data Collector状态异常: {service_data.get('status')}")
                    
                    # 检查支持的交易所
                    exchanges = service_data.get('supported_exchanges', [])
                    if not exchanges:
                        self.warnings.append("Data Collector未配置交易所")
                    
                    # 检查收集统计
                    stats = service_data.get('collection_stats', {})
                    collections = stats.get('total_collections', 0)
                    if collections == 0:
                        self.warnings.append("Data Collector尚未开始收集数据")
                    
            except Exception as e:
                raise Exception(f"Data Collector验证失败: {e}")
    
    async def _verify_nats_push_functionality(self):
        """验证NATS推送功能"""
        try:
            import nats
            
            # 连接NATS
            nc = await nats.connect(servers=["nats://localhost:4222"])
            
            received_messages = []
            
            async def message_handler(msg):
                try:
                    data = json.loads(msg.data.decode())
                    received_messages.append({
                        'subject': msg.subject,
                        'data': data
                    })
                except:
                    pass
            
            # 订阅数据主题
            await nc.subscribe("orderbook.>", cb=message_handler)
            await nc.subscribe("trade.>", cb=message_handler)
            await nc.subscribe("volatility_index.>", cb=message_handler)

            # 监听15秒
            await asyncio.sleep(15)
            
            await nc.close()
            
            if len(received_messages) == 0:
                raise Exception("未收到NATS推送消息，自动推送功能可能未激活")
            
            # 验证消息格式
            for msg in received_messages[:3]:  # 检查前3条消息
                subject_parts = msg['subject'].split('.')
                if len(subject_parts) < 3:
                    raise Exception(f"NATS主题格式异常: {msg['subject']}")
                
                data = msg['data']
                if not isinstance(data, dict) or 'exchange' not in data:
                    raise Exception("NATS消息数据格式异常")
            
            print(f"  ✅ 收到 {len(received_messages)} 条NATS消息")
            
        except Exception as e:
            raise Exception(f"NATS推送功能验证失败: {e}")
    
    async def _verify_configuration_files(self):
        """验证配置文件"""
        import os
        import yaml
        
        # 检查关键配置文件
        config_files = [
            'config/data_collection_config.yml',
            'config/public_data_sources.yaml',
            'requirements.txt'
        ]
        
        for config_file in config_files:
            if not os.path.exists(config_file):
                raise Exception(f"配置文件缺失: {config_file}")
        
        # 验证YAML配置文件格式
        try:
            with open('config/data_collection_config.yml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
                # 检查NATS配置
                nats_config = config.get('data_collection', {}).get('nats_streaming', {})
                if not nats_config.get('enabled', False):
                    self.warnings.append("NATS推送在配置中被禁用")
                
        except Exception as e:
            raise Exception(f"配置文件格式错误: {e}")
        
        # 检查requirements.txt中的nats-py版本
        try:
            with open('requirements.txt', 'r') as f:
                content = f.read()
                if 'nats-py==2.2.0' not in content:
                    self.warnings.append("requirements.txt中nats-py版本可能不正确")
        except Exception as e:
            self.warnings.append(f"无法检查requirements.txt: {e}")
    
    async def _run_end_to_end_test(self):
        """运行端到端测试"""
        # 这里可以运行更复杂的端到端测试
        # 目前只做基本的连通性测试
        
        async with aiohttp.ClientSession() as session:
            # 测试Data Collector API
            async with session.get('http://localhost:8084/api/v1/status') as response:
                if response.status != 200:
                    raise Exception("端到端测试失败：Data Collector API不可访问")
        
        # 测试NATS连接
        try:
            import nats
            nc = await nats.connect(servers=["nats://localhost:4222"])
            await nc.close()
        except Exception as e:
            raise Exception(f"端到端测试失败：NATS连接异常: {e}")
    
    def _generate_verification_report(self):
        """生成验证报告"""
        print("\n" + "=" * 50)
        print("📊 部署后验证报告")
        print("=" * 50)
        
        total_checks = 7  # 总验证步骤数
        failed_checks = len(self.errors)
        passed_checks = total_checks - failed_checks
        
        success_rate = (passed_checks / total_checks) * 100
        
        print(f"🎯 验证成功率: {success_rate:.1f}%")
        print(f"📈 验证统计: {passed_checks}/{total_checks} 项通过")
        
        if self.errors:
            print(f"\n❌ 发现 {len(self.errors)} 个错误:")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        
        if self.warnings:
            print(f"\n⚠️ 发现 {len(self.warnings)} 个警告:")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        if not self.errors:
            print("\n🎉 部署验证完全通过！")
            print("✅ 系统已准备好投入使用")
            print("📡 NATS自动推送功能正常工作")
        elif success_rate >= 80:
            print("\n⚠️ 部署基本成功，但有一些问题需要解决")
            print("🔧 建议修复上述错误后重新验证")
        else:
            print("\n❌ 部署验证失败")
            print("🚨 系统可能无法正常工作，请检查错误并重新部署")
            sys.exit(1)
        
        print(f"\n📅 验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


async def main():
    """主函数"""
    verifier = PostDeploymentVerifier()
    await verifier.run_verification()


if __name__ == "__main__":
    asyncio.run(main())
