"""
MarketPrism TDD 真实环境测试基础框架
支持真实API连接、代理配置、数据清理等

TDD核心原则：
1. 测试先行 - 先写测试，再写实现
2. 真实环境 - 不使用Mock，连接真实服务
3. 快速反馈 - 小步迭代，立即发现问题
4. 问题导向 - 每个测试对应具体的功能需求
"""

import os
import sys
import asyncio
import aiohttp
import pytest
import yaml
import redis
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
import signal
import subprocess
from dataclasses import dataclass

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TestEnvironment:
    """测试环境状态"""
    config: Dict[str, Any]
    services_running: Dict[str, bool]
    proxy_configured: bool
    databases_ready: Dict[str, bool]
    cleanup_tasks: List[callable]


class ProxyManager:
    """代理管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('proxy', {})
        self.original_env = {}
    
    def setup_proxy(self):
        """设置代理环境变量"""
        if not self.config.get('enabled', False):
            logger.info("代理未启用")
            return
        
        # 保存原始环境变量
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
            self.original_env[key] = os.environ.get(key)
        
        # 设置代理
        if self.config.get('http_proxy'):
            os.environ['HTTP_PROXY'] = self.config['http_proxy']
            logger.info(f"设置HTTP代理: {self.config['http_proxy']}")
        
        if self.config.get('https_proxy'):
            os.environ['HTTPS_PROXY'] = self.config['https_proxy']
            logger.info(f"设置HTTPS代理: {self.config['https_proxy']}")
        
        if self.config.get('no_proxy'):
            os.environ['NO_PROXY'] = self.config['no_proxy']
            logger.info(f"设置NO_PROXY: {self.config['no_proxy']}")
    
    def cleanup_proxy(self):
        """清理代理设置"""
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        logger.info("代理配置已清理")


class RealDatabaseManager:
    """真实数据库管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis_client = None
        self.clickhouse_client = None
    
    async def setup_databases(self) -> Dict[str, bool]:
        """设置测试数据库"""
        status = {}
        
        # 设置Redis
        try:
            redis_config = self.config['databases']['redis']
            self.redis_client = redis.Redis(
                host=redis_config['host'],
                port=redis_config['port'],
                db=redis_config['db'],
                password=redis_config.get('password') or None,
                decode_responses=True
            )
            
            # 测试连接
            self.redis_client.ping()
            
            # 清理测试数据库
            self.redis_client.flushdb()
            
            status['redis'] = True
            logger.info("Redis测试数据库准备完成")
            
        except Exception as e:
            logger.error(f"Redis设置失败: {e}")
            status['redis'] = False
        
        # 设置ClickHouse (这里简化处理，实际项目中需要建立连接)
        try:
            # 这里可以添加ClickHouse连接逻辑
            status['clickhouse'] = True
            logger.info("ClickHouse测试环境模拟准备完成")
        except Exception as e:
            logger.error(f"ClickHouse设置失败: {e}")
            status['clickhouse'] = False
        
        return status
    
    async def cleanup_databases(self):
        """清理测试数据"""
        if self.redis_client:
            try:
                self.redis_client.flushdb()
                logger.info("Redis测试数据已清理")
            except Exception as e:
                logger.error(f"Redis清理失败: {e}")
        
        # 这里可以添加ClickHouse清理逻辑


class ServiceManager:
    """微服务管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.service_processes = {}
        self.service_urls = {}
        
        # 构建服务URL
        for service_name, service_config in config['services'].items():
            self.service_urls[service_name] = f"http://{service_config['host']}:{service_config['port']}"
    
    async def start_services(self) -> Dict[str, bool]:
        """启动所有微服务"""
        logger.info("开始启动微服务...")
        
        # 启动服务的顺序很重要
        service_order = [
            'message_broker',
            'data_storage', 
            'market_data_collector',
            'scheduler',
            'monitoring',
            'api_gateway'
        ]
        
        status = {}
        
        for service_name in service_order:
            try:
                success = await self._start_single_service(service_name)
                status[service_name] = success
                
                if success:
                    # 等待服务启动
                    await asyncio.sleep(2)
                    # 验证服务健康
                    healthy = await self._check_service_health(service_name)
                    status[service_name] = healthy
                    
                    if healthy:
                        logger.info(f"✅ {service_name} 启动成功")
                    else:
                        logger.error(f"❌ {service_name} 健康检查失败")
                        
            except Exception as e:
                logger.error(f"启动服务 {service_name} 失败: {e}")
                status[service_name] = False
        
        return status
    
    async def _start_single_service(self, service_name: str) -> bool:
        """启动单个服务"""
        try:
            service_script = PROJECT_ROOT / "services" / f"{service_name.replace('_', '-')}-service" / "main.py"
            
            if not service_script.exists():
                logger.warning(f"服务脚本不存在: {service_script}")
                return False
            
            # 启动服务进程
            process = subprocess.Popen(
                [sys.executable, str(service_script)],
                cwd=str(PROJECT_ROOT),
                env={**os.environ, 'PYTHONPATH': str(PROJECT_ROOT)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.service_processes[service_name] = process
            logger.info(f"启动服务进程: {service_name} (PID: {process.pid})")
            
            return True
            
        except Exception as e:
            logger.error(f"启动服务 {service_name} 失败: {e}")
            return False
    
    async def _check_service_health(self, service_name: str) -> bool:
        """检查服务健康状态"""
        if service_name not in self.service_urls:
            return False
        
        url = self.service_urls[service_name]
        health_endpoint = self.config['services'][service_name]['health_endpoint']
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}{health_endpoint}", timeout=10) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"健康检查失败 {service_name}: {e}")
            return False
    
    async def stop_services(self):
        """停止所有服务"""
        logger.info("停止所有微服务...")
        
        for service_name, process in self.service_processes.items():
            try:
                # 发送SIGTERM信号
                process.terminate()
                
                # 等待进程结束
                try:
                    process.wait(timeout=10)
                    logger.info(f"✅ {service_name} 已正常停止")
                except subprocess.TimeoutExpired:
                    # 强制杀死进程
                    process.kill()
                    process.wait()
                    logger.warning(f"⚠️ {service_name} 被强制停止")
                    
            except Exception as e:
                logger.error(f"停止服务 {service_name} 失败: {e}")
        
        self.service_processes.clear()


class RealTestBase:
    """真实环境测试基础类"""
    
    def __init__(self):
        self.config = self._load_test_config()
        self.environment = None
        self.proxy_manager = ProxyManager(self.config)
        self.db_manager = RealDatabaseManager(self.config)
        self.service_manager = ServiceManager(self.config)
    
    def _load_test_config(self) -> Dict[str, Any]:
        """加载测试配置"""
        config_path = PROJECT_ROOT / "config" / "test_config.yaml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"加载测试配置: {config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            raise
    
    async def setup_test_environment(self) -> TestEnvironment:
        """设置完整的测试环境"""
        logger.info("🚀 开始设置TDD测试环境")
        
        cleanup_tasks = []
        
        try:
            # 1. 设置代理
            self.proxy_manager.setup_proxy()
            cleanup_tasks.append(self.proxy_manager.cleanup_proxy)
            
            # 2. 设置数据库
            db_status = await self.db_manager.setup_databases()
            cleanup_tasks.append(self.db_manager.cleanup_databases)
            
            # 3. 启动微服务
            service_status = await self.service_manager.start_services()
            cleanup_tasks.append(self.service_manager.stop_services)
            
            # 4. 验证环境
            environment = TestEnvironment(
                config=self.config,
                services_running=service_status,
                proxy_configured=self.config.get('proxy', {}).get('enabled', False),
                databases_ready=db_status,
                cleanup_tasks=cleanup_tasks
            )
            
            self.environment = environment
            
            # 5. 环境状态报告
            self._print_environment_status(environment)
            
            return environment
            
        except Exception as e:
            # 如果设置失败，执行清理
            for cleanup_task in reversed(cleanup_tasks):
                try:
                    if asyncio.iscoroutinefunction(cleanup_task):
                        await cleanup_task()
                    else:
                        cleanup_task()
                except Exception as cleanup_error:
                    logger.error(f"清理任务失败: {cleanup_error}")
            
            raise e
    
    async def cleanup_test_environment(self):
        """清理测试环境"""
        if not self.environment:
            return
        
        logger.info("🧹 开始清理测试环境")
        
        for cleanup_task in reversed(self.environment.cleanup_tasks):
            try:
                if asyncio.iscoroutinefunction(cleanup_task):
                    await cleanup_task()
                else:
                    cleanup_task()
            except Exception as e:
                logger.error(f"清理任务失败: {e}")
        
        logger.info("✅ 测试环境清理完成")
    
    def _print_environment_status(self, env: TestEnvironment):
        """打印环境状态"""
        print("\n" + "="*60)
        print("🔬 TDD测试环境状态报告")
        print("="*60)
        
        print(f"📡 代理配置: {'✅ 已启用' if env.proxy_configured else '❌ 未启用'}")
        
        print(f"\n💾 数据库状态:")
        for db_name, status in env.databases_ready.items():
            status_icon = "✅" if status else "❌"
            print(f"   {status_icon} {db_name}")
        
        print(f"\n🚀 微服务状态:")
        for service_name, status in env.services_running.items():
            status_icon = "✅" if status else "❌"
            print(f"   {status_icon} {service_name}")
        
        # 整体健康度
        total_services = len(env.services_running)
        healthy_services = sum(env.services_running.values())
        health_percentage = (healthy_services / total_services) * 100 if total_services > 0 else 0
        
        print(f"\n📊 整体健康度: {health_percentage:.1f}% ({healthy_services}/{total_services})")
        
        if health_percentage < 100:
            print("⚠️  部分服务未正常启动，可能影响测试结果")
        else:
            print("🎉 所有服务运行正常，可以开始TDD测试")
        
        print("="*60)


@asynccontextmanager
async def real_test_environment():
    """真实测试环境上下文管理器"""
    test_base = RealTestBase()
    
    try:
        environment = await test_base.setup_test_environment()
        yield environment
    finally:
        await test_base.cleanup_test_environment()


# pytest fixtures
@pytest.fixture(scope="session")
async def test_environment():
    """测试环境fixture"""
    async with real_test_environment() as env:
        yield env


@pytest.fixture
def real_test_base():
    """真实测试基础fixture"""
    return RealTestBase()


# 工具函数
def requires_service(service_name: str):
    """装饰器：标记测试需要特定服务"""
    def decorator(test_func):
        def wrapper(*args, **kwargs):
            # 这里可以添加服务依赖检查逻辑
            return test_func(*args, **kwargs)
        return wrapper
    return decorator


def requires_real_network():
    """装饰器：标记测试需要真实网络连接"""
    def decorator(test_func):
        def wrapper(*args, **kwargs):
            # 这里可以添加网络连接检查逻辑
            return test_func(*args, **kwargs)
        return wrapper
    return decorator


if __name__ == "__main__":
    async def test_environment_setup():
        """测试环境设置"""
        async with real_test_environment() as env:
            print("测试环境设置成功！")
            await asyncio.sleep(5)  # 保持5秒观察状态
    
    asyncio.run(test_environment_setup())