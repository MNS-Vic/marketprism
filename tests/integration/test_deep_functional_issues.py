#!/usr/bin/env python3
"""
深度功能问题检查 - 检查实际功能层面的问题
基础设施虽然就绪，但功能层面可能还有问题
"""

from datetime import datetime, timezone
import asyncio
import aiohttp
import logging
import sys
import os
import importlib.util
import yaml
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)

class DeepFunctionalIssuesTest:
    """深度功能问题检查"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.core_dir = self.project_root / "core"
        self.services_dir = self.project_root / "services"
        self.config_dir = self.project_root / "config"
        self.issues_found = []
        
    async def test_core_components_actual_functionality(self):
        """测试核心组件的实际功能可用性"""
        logger.info("🔍 深度检查核心组件实际功能...")
        
        component_issues = []
        
        # 1. 检查统一存储管理器的实际导入问题
        try:
            storage_manager_path = self.core_dir / 'storage' / 'unified_storage_manager.py'
            if storage_manager_path.exists():
                # 尝试实际导入
                spec = importlib.util.spec_from_file_location("unified_storage_manager", storage_manager_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                logger.info("✅ 统一存储管理器可以正常导入")
            else:
                component_issues.append("统一存储管理器文件不存在")
        except Exception as e:
            component_issues.append(f"统一存储管理器导入失败: {e}")
            logger.error(f"❌ 统一存储管理器导入失败: {e}")
        
        # 2. 检查网络组件的导入问题
        try:
            networking_dir = self.core_dir / 'networking'
            if networking_dir.exists():
                session_manager_path = networking_dir / 'unified_session_manager.py'
                if session_manager_path.exists():
                    spec = importlib.util.spec_from_file_location("unified_session_manager", session_manager_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    logger.info("✅ 统一会话管理器可以正常导入")
                else:
                    component_issues.append("统一会话管理器文件不存在")
            else:
                component_issues.append("networking目录不存在")
        except Exception as e:
            component_issues.append(f"统一会话管理器导入失败: {e}")
            logger.error(f"❌ 统一会话管理器导入失败: {e}")
        
        # 3. 检查监控组件
        try:
            monitoring_dir = self.core_dir / 'monitoring'
            if monitoring_dir.exists():
                # 检查是否有主要的监控模块
                monitoring_files = list(monitoring_dir.glob('*.py'))
                if len(monitoring_files) > 0:
                    logger.info(f"✅ 监控组件包含 {len(monitoring_files)} 个Python文件")
                else:
                    component_issues.append("监控组件缺少Python实现文件")
            else:
                component_issues.append("监控目录不存在")
        except Exception as e:
            component_issues.append(f"监控组件检查失败: {e}")
        
        if component_issues:
            self.issues_found.extend([f"核心组件问题: {issue}" for issue in component_issues])
            return False
        return True
    
    async def test_services_actual_functionality(self):
        """测试服务的实际功能可用性"""
        logger.info("🔍 深度检查服务实际功能...")
        
        service_issues = []
        
        # 检查每个服务是否有可执行的入口
        services = [
            'data-storage-service',
            'api-gateway-service', 
            'scheduler-service',
            'monitoring-service',
            'message-broker-service',
            'market-data-collector'
        ]
        
        for service in services:
            service_path = self.services_dir / service
            if service_path.exists():
                # 检查是否有主入口文件
                main_files = ['main.py', 'app.py', 'run.py', '__main__.py']
                has_main = any((service_path / main_file).exists() for main_file in main_files)
                
                if has_main:
                    # 尝试语法检查
                    for main_file in main_files:
                        main_path = service_path / main_file
                        if main_path.exists():
                            try:
                                with open(main_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    # 基本的语法检查
                                    compile(content, str(main_path), 'exec')
                                logger.info(f"✅ 服务 {service} 语法正确")
                                break
                            except SyntaxError as e:
                                service_issues.append(f"服务 {service} 语法错误: {e}")
                                logger.error(f"❌ 服务 {service} 语法错误: {e}")
                            except Exception as e:
                                service_issues.append(f"服务 {service} 检查失败: {e}")
                else:
                    service_issues.append(f"服务 {service} 缺少主入口文件")
                    logger.warning(f"⚠️ 服务 {service} 缺少主入口文件")
            else:
                service_issues.append(f"服务 {service} 目录不存在")
        
        if service_issues:
            self.issues_found.extend([f"服务问题: {issue}" for issue in service_issues])
            return False
        return True
    
    async def test_configuration_actual_validity(self):
        """测试配置的实际有效性"""
        logger.info("🔍 深度检查配置实际有效性...")
        
        config_issues = []
        
        # 检查关键配置文件的内容有效性
        critical_configs = {
            'services.yaml': ['services'],
            'collector_config.yaml': ['exchanges', 'proxy'],
            'hot_storage_config.yaml': ['hot_storage']
        }
        
        for config_file, required_keys in critical_configs.items():
            config_path = self.config_dir / config_file
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_data = yaml.safe_load(f)
                    
                    if config_data:
                        # 检查必需的键是否存在
                        missing_keys = [key for key in required_keys if key not in config_data]
                        if missing_keys:
                            config_issues.append(f"{config_file} 缺少必需配置: {missing_keys}")
                        else:
                            logger.info(f"✅ 配置文件 {config_file} 结构有效")
                    else:
                        config_issues.append(f"{config_file} 配置为空")
                        
                except yaml.YAMLError as e:
                    config_issues.append(f"{config_file} YAML格式错误: {e}")
                except Exception as e:
                    config_issues.append(f"{config_file} 读取失败: {e}")
            else:
                config_issues.append(f"关键配置文件 {config_file} 不存在")
        
        if config_issues:
            self.issues_found.extend([f"配置问题: {issue}" for issue in config_issues])
            return False
        return True
    
    async def test_real_exchange_api_functionality(self):
        """测试真实交易所API功能"""
        logger.info("🔍 深度检查真实交易所API功能...")
        
        api_issues = []
        
        # 更严格的交易所API测试
        exchanges_detailed_test = [
            {
                'name': 'Binance',
                'ping_url': 'https://api.binance.com/api/v3/ping',
                'time_url': 'https://api.binance.com/api/v3/time',
                'info_url': 'https://api.binance.com/api/v3/exchangeInfo'
            },
            {
                'name': 'OKX', 
                'time_url': 'https://www.okx.com/api/v5/public/time',
                'instruments_url': 'https://www.okx.com/api/v5/public/instruments?instType=SPOT'
            }
        ]
        
        # 设置代理
        proxy = None
        for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
            if os.environ.get(proxy_var):
                proxy = os.environ.get(proxy_var)
                break
        
        if not proxy:
            api_issues.append("未发现代理配置，可能无法访问外部API")
            logger.warning("⚠️ 未发现代理配置")
        
        successful_exchanges = 0
        
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                for exchange in exchanges_detailed_test:
                    exchange_success = 0
                    exchange_total = 0
                    
                    for key, url in exchange.items():
                        if key == 'name':
                            continue
                        
                        exchange_total += 1
                        try:
                            logger.info(f"🔗 测试 {exchange['name']} {key}...")
                            start_time = time.time()
                            
                            async with session.get(url, proxy=proxy) as response:
                                response_time = (time.time() - start_time) * 1000
                                
                                if response.status == 200:
                                    # 尝试解析JSON响应
                                    try:
                                        data = await response.json()
                                        if data:
                                            exchange_success += 1
                                            logger.info(f"✅ {exchange['name']} {key} 成功 ({response_time:.0f}ms)")
                                        else:
                                            logger.warning(f"⚠️ {exchange['name']} {key} 响应为空")
                                    except Exception as e:
                                        logger.warning(f"⚠️ {exchange['name']} {key} JSON解析失败: {e}")
                                else:
                                    logger.warning(f"⚠️ {exchange['name']} {key} HTTP状态: {response.status}")
                                    
                        except Exception as e:
                            logger.warning(f"⚠️ {exchange['name']} {key} 连接失败: {e}")
                    
                    # 计算交易所成功率
                    exchange_success_rate = exchange_success / exchange_total if exchange_total > 0 else 0
                    if exchange_success_rate >= 0.5:  # 至少50%接口成功
                        successful_exchanges += 1
                        logger.info(f"✅ {exchange['name']} 整体可用 ({exchange_success_rate:.1%})")
                    else:
                        api_issues.append(f"{exchange['name']} API功能不完整 ({exchange_success_rate:.1%})")
                        logger.warning(f"⚠️ {exchange['name']} API功能不完整")
                        
        except Exception as e:
            api_issues.append(f"交易所API测试框架失败: {e}")
            logger.error(f"❌ 交易所API测试框架失败: {e}")
        
        # 评估结果
        if successful_exchanges == 0:
            api_issues.append("所有交易所API均不可用")
        elif successful_exchanges < len(exchanges_detailed_test):
            api_issues.append(f"仅有 {successful_exchanges}/{len(exchanges_detailed_test)} 个交易所API可用")
        
        if api_issues:
            self.issues_found.extend([f"API问题: {issue}" for issue in api_issues])
            return successful_exchanges > 0  # 至少一个交易所可用就算部分成功
        
        return True
    
    async def test_dependency_completeness(self):
        """测试依赖完整性"""
        logger.info("🔍 深度检查依赖完整性...")
        
        dependency_issues = []
        
        # 检查requirements.txt中的依赖是否都已安装
        requirements_file = self.project_root / 'requirements.txt'
        if requirements_file.exists():
            try:
                with open(requirements_file, 'r', encoding='utf-8') as f:
                    requirements = f.read().strip().split('\n')
                
                missing_deps = []
                for req in requirements:
                    if req.strip() and not req.strip().startswith('#'):
                        # 提取包名（忽略版本号）
                        package_name = req.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                        try:
                            __import__(package_name)
                        except ImportError:
                            try:
                                # 尝试一些常见的包名映射
                                name_mappings = {
                                    'pyyaml': 'yaml',
                                    'pillow': 'PIL',
                                    'beautifulsoup4': 'bs4',
                                    'aiohttp-socks': 'aiohttp_socks',
                                    'python-socks': 'python_socks',
                                    'nats-py': 'nats',
                                    'clickhouse-driver': 'clickhouse_driver',
                                    'prometheus-client': 'prometheus_client',
                                    'python-dotenv': 'dotenv'
                                }
                                mapped_name = name_mappings.get(package_name.lower(), package_name)
                                __import__(mapped_name)
                            except ImportError:
                                missing_deps.append(package_name)
                
                if missing_deps:
                    dependency_issues.append(f"缺少依赖包: {missing_deps}")
                    logger.warning(f"⚠️ 缺少依赖包: {missing_deps}")
                else:
                    logger.info("✅ 所有requirements.txt中的依赖都已安装")
                    
            except Exception as e:
                dependency_issues.append(f"requirements.txt检查失败: {e}")
        else:
            dependency_issues.append("requirements.txt文件不存在")
        
        # 检查特定的关键依赖
        critical_deps = [
            'redis',
            'aiohttp', 
            'yaml',
            'psutil',
            'docker'
        ]
        
        missing_critical = []
        for dep in critical_deps:
            try:
                if dep == 'yaml':
                    import yaml
                else:
                    __import__(dep)
            except ImportError:
                missing_critical.append(dep)
        
        if missing_critical:
            dependency_issues.append(f"缺少关键依赖: {missing_critical}")
            logger.error(f"❌ 缺少关键依赖: {missing_critical}")
        else:
            logger.info("✅ 所有关键依赖都可用")
        
        if dependency_issues:
            self.issues_found.extend([f"依赖问题: {issue}" for issue in dependency_issues])
            return False
        return True
    
    async def test_docker_services_health(self):
        """测试Docker服务健康状态"""
        logger.info("🔍 深度检查Docker服务健康状态...")
        
        docker_issues = []
        
        # 检查Docker容器的详细健康状态
        try:
            # 检查ClickHouse健康状态
            result = subprocess.run([
                'docker', 'exec', 'clickhouse-server', 
                'clickhouse-client', '--query', 'SELECT 1'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and '1' in result.stdout:
                logger.info("✅ ClickHouse数据库查询功能正常")
            else:
                docker_issues.append(f"ClickHouse查询功能异常: {result.stderr}")
                logger.error(f"❌ ClickHouse查询功能异常: {result.stderr}")
                
        except Exception as e:
            docker_issues.append(f"ClickHouse健康检查失败: {e}")
        
        # 检查NATS健康状态（简单的连接测试）
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', 4222))
            sock.close()
            
            if result == 0:
                logger.info("✅ NATS端口连接正常")
            else:
                docker_issues.append("NATS端口连接失败")
        except Exception as e:
            docker_issues.append(f"NATS健康检查失败: {e}")
        
        if docker_issues:
            self.issues_found.extend([f"Docker服务问题: {issue}" for issue in docker_issues])
            return False
        return True

class DeepIssuesTestRunner:
    """深度问题测试执行器"""
    
    def __init__(self):
        self.test_instance = DeepFunctionalIssuesTest()
        self.results = {}
    
    async def run_deep_functional_tests(self):
        """运行深度功能测试"""
        logger.info("🔧 开始深度功能问题检查...")
        
        test_methods = [
            ('核心组件功能', self.test_instance.test_core_components_actual_functionality),
            ('服务功能', self.test_instance.test_services_actual_functionality),
            ('配置有效性', self.test_instance.test_configuration_actual_validity),
            ('交易所API功能', self.test_instance.test_real_exchange_api_functionality),
            ('依赖完整性', self.test_instance.test_dependency_completeness),
            ('Docker服务健康', self.test_instance.test_docker_services_health)
        ]
        
        total_tests = len(test_methods)
        passed_tests = 0
        
        for test_name, test_method in test_methods:
            logger.info(f"\n{'='*60}")
            logger.info(f"🧪 深度检查: {test_name}")
            logger.info(f"{'='*60}")
            
            try:
                result = await test_method()
                self.results[test_name] = result
                
                if result:
                    passed_tests += 1
                    logger.info(f"✅ {test_name} 深度检查通过")
                else:
                    logger.warning(f"⚠️ {test_name} 深度检查发现问题")
                    
            except Exception as e:
                logger.error(f"❌ {test_name} 深度检查异常: {e}")
                self.results[test_name] = False
        
        # 深度检查总结
        deep_success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        logger.info(f"\n{'='*70}")
        logger.info(f"🎯 MarketPrism 深度功能问题检查总结")
        logger.info(f"{'='*70}")
        logger.info(f"深度检查项目: {total_tests}")
        logger.info(f"通过项目: {passed_tests}")
        logger.info(f"发现问题项目: {total_tests - passed_tests}")
        logger.info(f"功能健康度: {deep_success_rate:.1f}%")
        
        # 展示发现的具体问题
        if self.test_instance.issues_found:
            logger.info(f"\n🚨 发现的具体问题:")
            for i, issue in enumerate(self.test_instance.issues_found, 1):
                logger.info(f"   {i}. {issue}")
        
        # 深度评估
        if deep_success_rate == 100:
            logger.info("🎉 深度功能检查完美通过，系统完全就绪")
        elif deep_success_rate >= 80:
            logger.info("👍 深度功能检查良好，少量问题需要修复")
        elif deep_success_rate >= 60:
            logger.info("⚠️ 深度功能检查发现重要问题，需要修复")
        else:
            logger.info("🚨 深度功能检查发现严重问题，需要大量修复工作")
        
        return self.results, self.test_instance.issues_found

# 如果直接运行此脚本
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        runner = DeepIssuesTestRunner()
        results, issues = await runner.run_deep_functional_tests()
        return results, issues
    
    # 运行深度功能测试
    asyncio.run(main())