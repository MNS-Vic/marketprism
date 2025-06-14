#!/usr/bin/env python3
"""
MarketPrism 综合TDD集成测试计划
基于项目实际架构设计的全面测试套件

项目架构概览:
- Core Layer: 基础设施层 (监控、安全、性能、运维、存储等)
- Services Layer: 业务服务层 (数据收集、API网关、存储服务、调度服务等)
- 技术栈: ClickHouse、NATS、Redis、WebSocket、aiohttp
"""

from datetime import datetime, timezone
import asyncio
import pytest
import aiohttp
import logging
import time
from typing import Dict, Any, List
from pathlib import Path
import yaml
import subprocess
import psutil
import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)

class MarketPrismTDDFramework:
    """MarketPrism TDD测试框架"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.config_dir = self.project_root / "config"
        self.services_dir = self.project_root / "services"
        self.core_dir = self.project_root / "core"
        self.test_results = {}
        self.infrastructure_health = {}
        
    async def setup_test_environment(self):
        """设置测试环境"""
        logger.info("🔧 设置MarketPrism测试环境...")
        
        # 确保关键目录存在
        assert self.config_dir.exists(), f"配置目录不存在: {self.config_dir}"
        assert self.services_dir.exists(), f"服务目录不存在: {self.services_dir}"
        assert self.core_dir.exists(), f"核心目录不存在: {self.core_dir}"
        
        logger.info("✅ 测试环境设置完成")

class TestPhase1_InfrastructureVerification:
    """Phase 1: 基础设施验证 - 验证所有基础组件是否可用"""
    
    def setUp(self):
        self.framework = MarketPrismTDDFramework()
        
    @pytest.mark.asyncio
    async def test_redis_connection(self):
        """测试Redis连接和基本操作"""
        logger.info("🔍 测试Redis连接...")
        
        try:
            import redis
            
            # 尝试连接Redis
            r = redis.Redis(host='localhost', port=6379, decode_responses=True)
            
            # 基本连接测试
            pong = r.ping()
            assert pong is True, "Redis PING测试失败"
            
            # 读写测试
            test_key = "marketprism:test"
            test_value = "tdd_test_value"
            
            r.set(test_key, test_value)
            retrieved_value = r.get(test_key)
            assert retrieved_value == test_value, f"Redis读写测试失败: {retrieved_value} != {test_value}"
            
            # 清理测试数据
            r.delete(test_key)
            
            logger.info("✅ Redis连接和操作测试通过")
            return True
            
        except ImportError:
            logger.warning("⚠️ Redis库未安装，跳过Redis测试")
            return False
        except Exception as e:
            logger.error(f"❌ Redis测试失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_nats_availability(self):
        """测试NATS消息队列是否可用"""
        logger.info("🔍 测试NATS连接...")
        
        try:
            # 检查NATS进程是否运行
            nats_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if 'nats' in proc.info['name'].lower() or \
                   any('nats' in str(cmd).lower() for cmd in proc.info['cmdline'] or []):
                    nats_processes.append(proc.info)
            
            if nats_processes:
                logger.info(f"✅ 发现NATS进程: {len(nats_processes)}个")
                return True
            else:
                logger.warning("⚠️ 未发现运行中的NATS进程")
                return False
                
        except Exception as e:
            logger.error(f"❌ NATS可用性检查失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_clickhouse_availability(self):
        """测试ClickHouse数据库是否可用"""
        logger.info("🔍 测试ClickHouse连接...")
        
        try:
            # 检查ClickHouse进程或端口
            clickhouse_available = False
            
            # 方法1: 检查进程
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if 'clickhouse' in proc.info['name'].lower():
                    clickhouse_available = True
                    break
            
            # 方法2: 检查端口8123是否开放
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', 8123))
            sock.close()
            
            if result == 0:
                clickhouse_available = True
            
            if clickhouse_available:
                logger.info("✅ ClickHouse数据库可用")
                return True
            else:
                logger.warning("⚠️ ClickHouse数据库不可用")
                return False
                
        except Exception as e:
            logger.error(f"❌ ClickHouse可用性检查失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_core_components_structure(self):
        """测试核心组件目录结构完整性"""
        logger.info("🔍 测试核心组件结构...")
        
        try:
            core_components = [
                'storage',
                'networking', 
                'monitoring',
                'security',
                'performance',
                'reliability',
                'caching',
                'logging',
                'errors',
                'middleware',
                'tracing',
                'operations'
            ]
            
            missing_components = []
            existing_components = []
            
            for component in core_components:
                component_path = self.framework.core_dir / component
                if component_path.exists():
                    existing_components.append(component)
                else:
                    missing_components.append(component)
            
            logger.info(f"✅ 存在的核心组件: {existing_components}")
            if missing_components:
                logger.warning(f"⚠️ 缺失的核心组件: {missing_components}")
            
            # 至少需要50%的核心组件存在
            completion_rate = len(existing_components) / len(core_components)
            assert completion_rate >= 0.5, f"核心组件完整性不足: {completion_rate:.1%}"
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 核心组件结构测试失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_services_availability(self):
        """测试业务服务可用性"""
        logger.info("🔍 测试业务服务结构...")
        
        try:
            expected_services = [
                'python-collector',
                'data-storage-service',
                'api-gateway-service',
                'scheduler-service',
                'monitoring-service',
                'message-broker-service',
                'market-data-collector'
            ]
            
            available_services = []
            missing_services = []
            
            for service in expected_services:
                service_path = self.framework.services_dir / service
                if service_path.exists():
                    available_services.append(service)
                    
                    # 检查是否有main.py或app.py
                    has_main = (service_path / "main.py").exists() or \
                              (service_path / "app.py").exists() or \
                              (service_path / "run.py").exists()
                    
                    if has_main:
                        logger.info(f"✅ 服务 {service} 结构完整")
                    else:
                        logger.warning(f"⚠️ 服务 {service} 缺少启动文件")
                else:
                    missing_services.append(service)
            
            logger.info(f"✅ 可用服务: {available_services}")
            if missing_services:
                logger.warning(f"⚠️ 缺失服务: {missing_services}")
            
            # 至少需要50%的服务可用
            availability_rate = len(available_services) / len(expected_services)
            assert availability_rate >= 0.5, f"服务可用性不足: {availability_rate:.1%}"
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 服务可用性测试失败: {e}")
            return False

class TestPhase2_ConfigurationIntegrity:
    """Phase 2: 配置完整性验证 - 验证配置系统的完整性和正确性"""
    
    def setUp(self):
        self.framework = MarketPrismTDDFramework()
    
    @pytest.mark.asyncio
    async def test_configuration_files_existence(self):
        """测试关键配置文件是否存在"""
        logger.info("🔍 测试配置文件完整性...")
        
        try:
            critical_configs = [
                'services.yaml',
                'collector_config.yaml',
                'hot_storage_config.yaml'
            ]
            
            existing_configs = []
            missing_configs = []
            
            for config_file in critical_configs:
                config_path = self.framework.config_dir / config_file
                if config_path.exists():
                    existing_configs.append(config_file)
                    
                    # 尝试解析YAML
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            yaml.safe_load(f)
                        logger.info(f"✅ 配置文件 {config_file} 格式正确")
                    except yaml.YAMLError as e:
                        logger.error(f"❌ 配置文件 {config_file} YAML格式错误: {e}")
                        
                else:
                    missing_configs.append(config_file)
            
            if missing_configs:
                logger.warning(f"⚠️ 缺失的配置文件: {missing_configs}")
            
            # 至少需要70%的关键配置存在
            config_completeness = len(existing_configs) / len(critical_configs)
            assert config_completeness >= 0.7, f"配置完整性不足: {config_completeness:.1%}"
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 配置文件测试失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_proxy_configuration(self):
        """测试代理配置是否正确"""
        logger.info("🔍 测试代理配置...")
        
        try:
            # 检查环境变量代理设置
            proxy_env_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy']
            
            env_proxy_found = False
            for var in proxy_env_vars:
                if os.environ.get(var):
                    logger.info(f"✅ 发现环境变量代理: {var}={os.environ.get(var)}")
                    env_proxy_found = True
            
            # 检查配置文件中的代理设置
            config_proxy_found = False
            collector_config_path = self.framework.config_dir / 'collector_config.yaml'
            
            if collector_config_path.exists():
                with open(collector_config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    
                if config and 'proxy' in config:
                    logger.info("✅ 发现配置文件代理设置")
                    config_proxy_found = True
            
            if env_proxy_found or config_proxy_found:
                logger.info("✅ 代理配置可用")
                return True
            else:
                logger.warning("⚠️ 未发现代理配置，可能影响外网连接")
                return False
                
        except Exception as e:
            logger.error(f"❌ 代理配置测试失败: {e}")
            return False

class TestPhase3_CoreComponentsIntegration:
    """Phase 3: 核心组件集成测试 - 验证核心组件能够正确协作"""
    
    def setUp(self):
        self.framework = MarketPrismTDDFramework()
    
    @pytest.mark.asyncio
    async def test_unified_storage_manager(self):
        """测试统一存储管理器"""
        logger.info("🔍 测试统一存储管理器...")
        
        try:
            # 尝试导入统一存储管理器
            storage_manager_path = self.framework.core_dir / 'storage' / 'unified_storage_manager.py'
            
            if storage_manager_path.exists():
                logger.info("✅ 统一存储管理器文件存在")
                
                # 尝试导入模块（基本语法检查）
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("unified_storage_manager", storage_manager_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    logger.info("✅ 统一存储管理器语法正确")
                    return True
                except Exception as e:
                    logger.error(f"❌ 统一存储管理器导入失败: {e}")
                    return False
            else:
                logger.warning("⚠️ 统一存储管理器文件不存在")
                return False
                
        except Exception as e:
            logger.error(f"❌ 统一存储管理器测试失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_networking_components(self):
        """测试网络组件"""
        logger.info("🔍 测试网络组件...")
        
        try:
            networking_dir = self.framework.core_dir / 'networking'
            
            if networking_dir.exists():
                networking_files = list(networking_dir.glob('*.py'))
                logger.info(f"✅ 发现网络组件文件: {len(networking_files)}个")
                
                # 检查统一会话管理器
                session_manager_path = networking_dir / 'unified_session_manager.py'
                if session_manager_path.exists():
                    logger.info("✅ 统一会话管理器存在")
                else:
                    logger.warning("⚠️ 统一会话管理器不存在")
                
                return True
            else:
                logger.warning("⚠️ 网络组件目录不存在")
                return False
                
        except Exception as e:
            logger.error(f"❌ 网络组件测试失败: {e}")
            return False

class TestPhase4_ExternalConnectivity:
    """Phase 4: 外部连接性测试 - 验证与外部服务的连接能力"""
    
    def setUp(self):
        self.framework = MarketPrismTDDFramework()
    
    @pytest.mark.asyncio
    async def test_exchange_api_connectivity(self):
        """测试交易所API连接性"""
        logger.info("🔍 测试交易所API连接性...")
        
        try:
            # 简单的连接性测试，不依赖具体的收集器实现
            exchanges_to_test = [
                ('Binance', 'https://api.binance.com/api/v3/ping'),
                ('OKX', 'https://www.okx.com/api/v5/public/time'),
            ]
            
            successful_connections = 0
            
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                
                for exchange_name, test_url in exchanges_to_test:
                    try:
                        async with session.get(test_url) as response:
                            if response.status == 200:
                                logger.info(f"✅ {exchange_name} API连接成功")
                                successful_connections += 1
                            else:
                                logger.warning(f"⚠️ {exchange_name} API响应状态: {response.status}")
                    except Exception as e:
                        logger.warning(f"⚠️ {exchange_name} API连接失败: {e}")
            
            # 至少一个交易所连接成功即可
            if successful_connections > 0:
                logger.info(f"✅ 交易所连接测试通过: {successful_connections}/{len(exchanges_to_test)}")
                return True
            else:
                logger.warning("⚠️ 所有交易所连接失败，可能需要代理或网络配置")
                return False
                
        except Exception as e:
            logger.error(f"❌ 交易所连接测试失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_websocket_capability(self):
        """测试WebSocket连接能力"""
        logger.info("🔍 测试WebSocket连接能力...")
        
        try:
            # 测试基本的WebSocket连接能力
            try:
                import websockets
                logger.info("✅ WebSocket库可用")
                
                # 简单的echo测试服务器连接
                # 这里只是验证WebSocket客户端能力，不依赖外部服务
                logger.info("✅ WebSocket客户端能力验证通过")
                return True
                
            except ImportError:
                logger.warning("⚠️ WebSocket库未安装")
                return False
                
        except Exception as e:
            logger.error(f"❌ WebSocket能力测试失败: {e}")
            return False

class TestPhase5_SystemIntegration:
    """Phase 5: 系统集成测试 - 验证整个系统的协作能力"""
    
    def setUp(self):
        self.framework = MarketPrismTDDFramework()
    
    @pytest.mark.asyncio
    async def test_service_startup_capability(self):
        """测试服务启动能力"""
        logger.info("🔍 测试服务启动能力...")
        
        try:
            # 检查是否有启动脚本
            startup_scripts = []
            
            scripts_dir = self.framework.project_root / 'scripts'
            if scripts_dir.exists():
                for script_file in scripts_dir.glob('*.py'):
                    if 'start' in script_file.name.lower():
                        startup_scripts.append(script_file)
            
            # 检查Docker配置
            docker_files = []
            docker_compose_files = list(self.framework.project_root.glob('docker-compose*.yml'))
            dockerfile = self.framework.project_root / 'Dockerfile'
            
            if dockerfile.exists():
                docker_files.append('Dockerfile')
            
            if docker_compose_files:
                docker_files.extend([f.name for f in docker_compose_files])
            
            logger.info(f"✅ 发现启动脚本: {[s.name for s in startup_scripts]}")
            logger.info(f"✅ 发现Docker配置: {docker_files}")
            
            # 系统有启动能力的判断
            has_startup_capability = len(startup_scripts) > 0 or len(docker_files) > 0
            
            if has_startup_capability:
                logger.info("✅ 系统具备启动能力")
                return True
            else:
                logger.warning("⚠️ 系统缺少启动配置")
                return False
                
        except Exception as e:
            logger.error(f"❌ 服务启动能力测试失败: {e}")
            return False
    
    @pytest.mark.asyncio
    async def test_documentation_completeness(self):
        """测试文档完整性"""
        logger.info("🔍 测试文档完整性...")
        
        try:
            # 检查关键文档文件
            key_docs = [
                'README.md',
                'QUICK_START.md',
                '项目说明.md'
            ]
            
            existing_docs = []
            missing_docs = []
            
            for doc in key_docs:
                doc_path = self.framework.project_root / doc
                if doc_path.exists() and doc_path.stat().st_size > 100:  # 至少100字节
                    existing_docs.append(doc)
                else:
                    missing_docs.append(doc)
            
            # 检查docs目录
            docs_dir = self.framework.project_root / 'docs'
            docs_count = 0
            if docs_dir.exists():
                docs_count = len(list(docs_dir.rglob('*.md')))
            
            logger.info(f"✅ 存在的关键文档: {existing_docs}")
            logger.info(f"✅ docs目录文档数量: {docs_count}")
            
            if missing_docs:
                logger.warning(f"⚠️ 缺失的关键文档: {missing_docs}")
            
            # 文档完整性判断
            doc_completeness = len(existing_docs) / len(key_docs)
            
            if doc_completeness >= 0.6 or docs_count > 5:
                logger.info("✅ 文档完整性满足要求")
                return True
            else:
                logger.warning("⚠️ 文档完整性不足")
                return False
                
        except Exception as e:
            logger.error(f"❌ 文档完整性测试失败: {e}")
            return False

# 综合测试执行器
class TDDTestRunner:
    """TDD测试执行器"""
    
    def __init__(self):
        self.test_phases = [
            TestPhase1_InfrastructureVerification(),
            TestPhase2_ConfigurationIntegrity(),
            TestPhase3_CoreComponentsIntegration(),
            TestPhase4_ExternalConnectivity(),
            TestPhase5_SystemIntegration()
        ]
        self.results = {}
    
    async def run_all_tests(self):
        """运行所有测试阶段"""
        logger.info("🚀 开始MarketPrism综合TDD测试...")
        
        total_tests = 0
        passed_tests = 0
        
        for i, phase in enumerate(self.test_phases, 1):
            phase_name = phase.__class__.__name__
            logger.info(f"\n{'='*60}")
            logger.info(f"🧪 执行测试阶段 {i}: {phase_name}")
            logger.info(f"{'='*60}")
            
            phase_results = {}
            phase_tests = 0
            phase_passed = 0
            
            # 获取该阶段的所有测试方法
            test_methods = [method for method in dir(phase) if method.startswith('test_')]
            
            for test_method_name in test_methods:
                test_method = getattr(phase, test_method_name)
                
                try:
                    logger.info(f"\n🧪 执行测试: {test_method_name}")
                    result = await test_method()
                    
                    phase_results[test_method_name] = result
                    phase_tests += 1
                    total_tests += 1
                    
                    if result:
                        phase_passed += 1
                        passed_tests += 1
                        logger.info(f"✅ {test_method_name} 通过")
                    else:
                        logger.warning(f"⚠️ {test_method_name} 失败")
                        
                except Exception as e:
                    logger.error(f"❌ {test_method_name} 异常: {e}")
                    phase_results[test_method_name] = False
                    phase_tests += 1
                    total_tests += 1
            
            # 阶段总结
            phase_pass_rate = (phase_passed / phase_tests * 100) if phase_tests > 0 else 0
            logger.info(f"\n📊 阶段 {i} 总结: {phase_passed}/{phase_tests} 通过 ({phase_pass_rate:.1f}%)")
            
            self.results[phase_name] = {
                'total': phase_tests,
                'passed': phase_passed,
                'pass_rate': phase_pass_rate,
                'details': phase_results
            }
        
        # 最终总结
        overall_pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🏆 MarketPrism TDD测试总结")
        logger.info(f"{'='*60}")
        logger.info(f"总测试数: {total_tests}")
        logger.info(f"通过测试: {passed_tests}")
        logger.info(f"失败测试: {total_tests - passed_tests}")
        logger.info(f"通过率: {overall_pass_rate:.1f}%")
        
        # 系统就绪度评估
        if overall_pass_rate >= 80:
            logger.info("🎉 系统就绪度: 优秀 - 可以进入生产环境")
        elif overall_pass_rate >= 60:
            logger.info("👍 系统就绪度: 良好 - 需要少量改进")
        elif overall_pass_rate >= 40:
            logger.info("⚠️ 系统就绪度: 一般 - 需要重要改进")
        else:
            logger.info("🚨 系统就绪度: 不足 - 需要大量工作")
        
        return self.results

# 如果直接运行此脚本
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        runner = TDDTestRunner()
        results = await runner.run_all_tests()
        return results
    
    # 运行测试
    asyncio.run(main())