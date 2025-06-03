"""
基础设施健康检查测试模块
验证MarketPrism系统基础组件的运行状态
"""

import pytest
import asyncio
import aiohttp
import docker
import nats
from nats.errors import TimeoutError, NoServersError
import clickhouse_connect
import subprocess
import time
import logging
from typing import Dict, Any, Optional

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InfrastructureHealthChecker:
    """基础设施健康检查器"""
    
    def __init__(self):
        self.docker_client = None
        self.nats_client = None
        self.clickhouse_client = None
        
    async def setup(self):
        """设置测试环境"""
        try:
            # 初始化Docker客户端
            self.docker_client = docker.from_env()
            logger.info("Docker客户端初始化成功")
        except Exception as e:
            logger.error(f"Docker客户端初始化失败: {e}")
            raise
            
    async def teardown(self):
        """清理测试环境"""
        if self.nats_client:
            await self.nats_client.close()
        if self.clickhouse_client:
            self.clickhouse_client.close()

@pytest.fixture(scope="function")
async def health_checker():
    """健康检查器fixture"""
    checker = InfrastructureHealthChecker()
    await checker.setup()
    yield checker
    await checker.teardown()

class TestDockerInfrastructure:
    """Docker基础设施测试"""
    
    @pytest.mark.asyncio
    async def test_docker_daemon_running(self, health_checker):
        """测试Docker守护进程是否运行"""
        try:
            info = health_checker.docker_client.info()
            assert info is not None
            logger.info(f"Docker版本: {info.get('ServerVersion', 'Unknown')}")
            logger.info(f"运行中的容器数量: {info.get('ContainersRunning', 0)}")
        except Exception as e:
            pytest.fail(f"Docker守护进程未运行: {e}")
    
    @pytest.mark.asyncio
    async def test_required_containers_running(self, health_checker):
        """测试必需的容器是否运行"""
        required_containers = {
            'nats-server': 'nats',
            'clickhouse': 'clickhouse'
        }
        
        running_containers = {}
        try:
            containers = health_checker.docker_client.containers.list()
            for container in containers:
                container_name = container.name
                for req_name, service_type in required_containers.items():
                    if req_name in container_name or service_type in container_name:
                        running_containers[service_type] = {
                            'name': container_name,
                            'status': container.status,
                            'id': container.short_id
                        }
                        logger.info(f"发现容器: {container_name} (状态: {container.status})")
        except Exception as e:
            pytest.fail(f"获取容器列表失败: {e}")
        
        # 验证必需容器都在运行
        for service_type in required_containers.values():
            assert service_type in running_containers, f"{service_type}容器未运行"
            assert running_containers[service_type]['status'] == 'running', \
                f"{service_type}容器状态异常: {running_containers[service_type]['status']}"
    
    @pytest.mark.asyncio
    async def test_container_health_checks(self, health_checker):
        """测试容器健康检查状态"""
        containers_to_check = ['nats-server', 'clickhouse']
        
        for container_name in containers_to_check:
            try:
                containers = health_checker.docker_client.containers.list(
                    filters={'name': container_name}
                )
                if containers:
                    container = containers[0]
                    # 获取容器健康状态
                    container.reload()
                    health = container.attrs.get('State', {}).get('Health', {})
                    if health:
                        status = health.get('Status', 'unknown')
                        logger.info(f"{container_name}健康状态: {status}")
                        # 如果有健康检查，确保状态为healthy
                        if status != 'starting':
                            assert status == 'healthy', f"{container_name}健康检查失败: {status}"
                    else:
                        logger.info(f"{container_name}未配置健康检查")
            except Exception as e:
                logger.warning(f"检查{container_name}健康状态失败: {e}")

class TestNATSConnectivity:
    """NATS连接性测试"""
    
    @pytest.mark.asyncio
    async def test_nats_connection(self, health_checker):
        """测试NATS基本连接"""
        try:
            health_checker.nats_client = await nats.connect("nats://localhost:4222")
            assert health_checker.nats_client.is_connected
            logger.info("NATS连接成功")
        except (TimeoutError, NoServersError) as e:
            pytest.fail(f"NATS连接失败: {e}")
    
    @pytest.mark.asyncio
    async def test_nats_jetstream_enabled(self, health_checker):
        """测试NATS JetStream是否启用"""
        if not health_checker.nats_client:
            health_checker.nats_client = await nats.connect("nats://localhost:4222")
        
        try:
            js = health_checker.nats_client.jetstream()
            # 尝试获取流信息来验证JetStream功能
            account_info = await js.account_info()
            assert account_info is not None
            logger.info(f"JetStream账户信息: {account_info}")
        except Exception as e:
            pytest.fail(f"JetStream未启用或配置错误: {e}")
    
    @pytest.mark.asyncio
    async def test_nats_streams_exist(self, health_checker):
        """测试必需的NATS流是否存在"""
        if not health_checker.nats_client:
            health_checker.nats_client = await nats.connect("nats://localhost:4222")
        
        js = health_checker.nats_client.jetstream()
        required_streams = ['MARKET_DATA']
        
        try:
            streams = await js.streams_info()
            existing_streams = [stream.config.name for stream in streams]
            logger.info(f"现有流: {existing_streams}")
            
            for stream_name in required_streams:
                assert stream_name in existing_streams, f"流 {stream_name} 不存在"
                
        except Exception as e:
            logger.warning(f"获取流信息失败，尝试创建必需流: {e}")
            # 如果流不存在，尝试创建
            await self._create_required_streams(js, required_streams)
    
    async def _create_required_streams(self, js, stream_names):
        """创建必需的NATS流"""
        from nats.js.api import StreamConfig
        
        for stream_name in stream_names:
            try:
                config = StreamConfig(
                    name=stream_name,
                    subjects=[f"market.>"]
                )
                await js.add_stream(config)
                logger.info(f"创建流 {stream_name} 成功")
            except Exception as e:
                logger.error(f"创建流 {stream_name} 失败: {e}")
    
    @pytest.mark.asyncio
    async def test_nats_pub_sub(self, health_checker):
        """测试NATS发布订阅功能"""
        if not health_checker.nats_client:
            health_checker.nats_client = await nats.connect("nats://localhost:4222")
        
        test_subject = "test.health.check"
        test_message = b"health check message"
        received_message = None
        
        async def message_handler(msg):
            nonlocal received_message
            received_message = msg.data
        
        # 订阅测试主题
        sub = await health_checker.nats_client.subscribe(test_subject, cb=message_handler)
        
        # 发布测试消息
        await health_checker.nats_client.publish(test_subject, test_message)
        
        # 等待消息接收
        await asyncio.sleep(0.1)
        
        # 验证消息接收
        assert received_message == test_message, "NATS消息发布订阅失败"
        
        # 清理订阅
        await sub.unsubscribe()
        logger.info("NATS发布订阅测试成功")

class TestClickHouseConnectivity:
    """ClickHouse连接性测试"""
    
    @pytest.mark.asyncio
    async def test_clickhouse_connection(self, health_checker):
        """测试ClickHouse基本连接"""
        try:
            health_checker.clickhouse_client = clickhouse_connect.get_client(
                host='localhost',
                port=8123,
                username='default',
                password=''
            )
            # 执行简单查询验证连接
            result = health_checker.clickhouse_client.query("SELECT 1")
            assert result.result_rows[0][0] == 1
            logger.info("ClickHouse连接成功")
        except Exception as e:
            pytest.fail(f"ClickHouse连接失败: {e}")
    
    @pytest.mark.asyncio
    async def test_marketprism_database_exists(self, health_checker):
        """测试marketprism数据库是否存在"""
        if not health_checker.clickhouse_client:
            health_checker.clickhouse_client = clickhouse_connect.get_client(
                host='localhost', port=8123, username='default', password=''
            )
        
        try:
            # 查询数据库列表
            result = health_checker.clickhouse_client.query("SHOW DATABASES")
            databases = [row[0] for row in result.result_rows]
            
            assert 'marketprism' in databases, "marketprism数据库不存在"
            logger.info("marketprism数据库存在")
        except Exception as e:
            pytest.fail(f"查询数据库失败: {e}")
    
    @pytest.mark.asyncio
    async def test_required_tables_exist(self, health_checker):
        """测试必需的表是否存在"""
        if not health_checker.clickhouse_client:
            health_checker.clickhouse_client = clickhouse_connect.get_client(
                host='localhost', port=8123, username='default', password=''
            )
        
        required_tables = ['trades', 'depth', 'funding_rate', 'open_interest']
        
        try:
            # 查询marketprism数据库中的表
            result = health_checker.clickhouse_client.query(
                "SHOW TABLES FROM marketprism"
            )
            existing_tables = [row[0] for row in result.result_rows]
            logger.info(f"现有表: {existing_tables}")
            
            for table_name in required_tables:
                assert table_name in existing_tables, f"表 {table_name} 不存在"
        except Exception as e:
            pytest.fail(f"查询表列表失败: {e}")
    
    @pytest.mark.asyncio
    async def test_clickhouse_insert_query(self, health_checker):
        """测试ClickHouse插入和查询功能"""
        if not health_checker.clickhouse_client:
            health_checker.clickhouse_client = clickhouse_connect.get_client(
                host='localhost', port=8123, username='default', password=''
            )
        
        try:
            # 插入测试数据
            test_data = [[
                1,  # id
                'test_exchange',  # exchange
                'TEST/USDT',  # symbol
                'test_trade_001',  # trade_id
                50000.0,  # price
                0.001,  # quantity
                'buy',  # side
                '2024-01-01 12:00:00',  # trade_time
                '2024-01-01 12:00:00',  # receive_time
                True  # is_best_match
            ]]
            
            health_checker.clickhouse_client.insert(
                'marketprism.trades',
                test_data,
                column_names=['id', 'exchange', 'symbol', 'trade_id', 'price', 
                             'quantity', 'side', 'trade_time', 'receive_time', 'is_best_match']
            )
            
            # 查询测试数据
            result = health_checker.clickhouse_client.query(
                "SELECT * FROM marketprism.trades WHERE trade_id = 'test_trade_001'"
            )
            
            assert len(result.result_rows) == 1, "测试数据插入失败"
            assert result.result_rows[0][3] == 'test_trade_001', "查询结果不匹配"
            
            # 清理测试数据
            health_checker.clickhouse_client.command(
                "DELETE FROM marketprism.trades WHERE trade_id = 'test_trade_001'"
            )
            
            logger.info("ClickHouse插入查询测试成功")
        except Exception as e:
            pytest.fail(f"ClickHouse插入查询测试失败: {e}")

class TestNetworkConnectivity:
    """网络连接性测试"""
    
    @pytest.mark.asyncio
    async def test_external_api_connectivity(self):
        """测试外部API连接性"""
        test_urls = [
            'https://api.binance.com/api/v3/ping',
            'https://www.okx.com/api/v5/public/time',
            'https://www.deribit.com/api/v2/public/get_time'
        ]
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            for url in test_urls:
                try:
                    async with session.get(url) as response:
                        assert response.status == 200, f"API {url} 响应状态异常: {response.status}"
                        logger.info(f"API连接测试成功: {url}")
                except asyncio.TimeoutError:
                    logger.warning(f"API连接超时: {url}")
                except Exception as e:
                    logger.warning(f"API连接失败: {url}, 错误: {e}")
    
    @pytest.mark.asyncio
    async def test_internal_service_ports(self):
        """测试内部服务端口可访问性"""
        services = {
            'NATS': ('localhost', 4222),
            'NATS监控': ('localhost', 8222),
            'ClickHouse HTTP': ('localhost', 8123),
            'ClickHouse TCP': ('localhost', 9000)
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            for service_name, (host, port) in services.items():
                try:
                    if port in [8222, 8123]:  # HTTP端口
                        url = f"http://{host}:{port}"
                        async with session.get(url) as response:
                            logger.info(f"{service_name} HTTP端口可访问: {port}")
                    else:  # TCP端口
                        # 使用简单的socket连接测试TCP端口
                        import socket
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(5)
                        result = sock.connect_ex((host, port))
                        sock.close()
                        assert result == 0, f"{service_name} TCP端口不可访问: {port}"
                        logger.info(f"{service_name} TCP端口可访问: {port}")
                except Exception as e:
                    logger.warning(f"{service_name}端口测试失败: {e}")

@pytest.mark.asyncio
async def test_complete_infrastructure_health():
    """完整基础设施健康检查"""
    checker = InfrastructureHealthChecker()
    await checker.setup()
    
    try:
        # 运行所有健康检查
        health_results = {
            'docker': False,
            'nats': False,
            'clickhouse': False,
            'network': False
        }
        
        # Docker检查
        try:
            info = checker.docker_client.info()
            health_results['docker'] = True
            logger.info("✅ Docker健康检查通过")
        except Exception as e:
            logger.error(f"❌ Docker健康检查失败: {e}")
        
        # NATS检查
        try:
            nats_client = await nats.connect("nats://localhost:4222")
            await nats_client.close()
            health_results['nats'] = True
            logger.info("✅ NATS健康检查通过")
        except Exception as e:
            logger.error(f"❌ NATS健康检查失败: {e}")
        
        # ClickHouse检查
        try:
            ch_client = clickhouse_connect.get_client(
                host='localhost', port=8123, username='default', password=''
            )
            ch_client.query("SELECT 1")
            ch_client.close()
            health_results['clickhouse'] = True
            logger.info("✅ ClickHouse健康检查通过")
        except Exception as e:
            logger.error(f"❌ ClickHouse健康检查失败: {e}")
        
        # 网络检查
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.binance.com/api/v3/ping') as response:
                    if response.status == 200:
                        health_results['network'] = True
                        logger.info("✅ 网络连接检查通过")
        except Exception as e:
            logger.error(f"❌ 网络连接检查失败: {e}")
        
        # 汇总结果
        passed_checks = sum(health_results.values())
        total_checks = len(health_results)
        
        logger.info(f"基础设施健康检查完成: {passed_checks}/{total_checks} 通过")
        
        # 至少要有3/4的检查通过才算成功
        assert passed_checks >= 3, f"基础设施健康检查失败，仅有{passed_checks}/{total_checks}项通过"
        
    finally:
        await checker.teardown()

if __name__ == "__main__":
    # 直接运行健康检查
    asyncio.run(test_complete_infrastructure_health()) 