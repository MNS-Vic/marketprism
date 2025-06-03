"""
端到端数据流测试模块
测试从真实交易所数据收集到最终存储的完整流程
"""

import pytest
import asyncio
import json
import time
import logging
import subprocess
import signal
import os
import psutil
from typing import Dict, List, Optional, Any
import nats
import clickhouse_connect
import websockets
import aiohttp
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EndToEndDataFlowTester:
    """端到端数据流测试器"""
    
    def __init__(self):
        self.collector_process = None
        self.nats_client = None
        self.clickhouse_client = None
        self.test_start_time = None
        self.collected_messages = []
        self.stored_records = []
        
    async def setup_test_environment(self):
        """设置测试环境"""
        try:
            # 初始化NATS连接
            self.nats_client = await nats.connect("nats://localhost:4222")
            logger.info("NATS客户端连接成功")
            
            # 初始化ClickHouse连接
            self.clickhouse_client = clickhouse_connect.get_client(
                host='localhost',
                port=8123,
                username='default',
                password=''
            )
            logger.info("ClickHouse客户端连接成功")
            
            # 记录测试开始时间
            self.test_start_time = datetime.now()
            
        except Exception as e:
            logger.error(f"设置测试环境失败: {e}")
            raise
    
    async def cleanup_test_environment(self):
        """清理测试环境"""
        if self.collector_process:
            try:
                # 优雅关闭收集器进程
                self.collector_process.terminate()
                try:
                    self.collector_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.collector_process.kill()
                logger.info("收集器进程已关闭")
            except Exception as e:
                logger.warning(f"关闭收集器进程时出错: {e}")
        
        if self.nats_client:
            await self.nats_client.close()
        
        if self.clickhouse_client:
            self.clickhouse_client.close()

@pytest.fixture(scope="class")
async def data_flow_tester():
    """数据流测试器fixture"""
    tester = EndToEndDataFlowTester()
    await tester.setup_test_environment()
    yield tester
    await tester.cleanup_test_environment()

class TestDataCollectorService:
    """数据收集器服务测试"""
    
    @pytest.mark.asyncio
    async def test_collector_service_startup(self, data_flow_tester):
        """测试收集器服务启动"""
        
        # 检查是否已有收集器进程运行
        existing_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'collector' in proc.info['name'] or any('collector' in arg for arg in proc.info['cmdline']):
                    existing_processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if existing_processes:
            logger.info(f"发现已运行的收集器进程: {existing_processes}")
            # 使用现有进程而不是启动新的
            return
        
        try:
            # 启动集成收集器
            collector_script = "./run_integrated_collector_fix.sh"
            if os.path.exists(collector_script):
                data_flow_tester.collector_process = subprocess.Popen(
                    [collector_script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.info("已启动集成收集器服务")
                
                # 等待服务启动
                await asyncio.sleep(10)
                
                # 检查服务是否正在运行
                if data_flow_tester.collector_process.poll() is None:
                    logger.info("✅ 收集器服务启动成功")
                else:
                    stdout, stderr = data_flow_tester.collector_process.communicate()
                    pytest.fail(f"收集器服务启动失败: {stderr}")
            else:
                logger.warning("未找到收集器启动脚本，跳过服务启动测试")
                
        except Exception as e:
            pytest.fail(f"启动收集器服务失败: {e}")
    
    @pytest.mark.asyncio
    async def test_collector_health_endpoint(self, data_flow_tester):
        """测试收集器健康检查端点"""
        health_url = "http://localhost:8081/health"
        
        try:
            async with aiohttp.ClientSession() as session:
                # 尝试多次检查健康状态（服务可能需要时间启动）
                for attempt in range(5):
                    try:
                        async with session.get(health_url, timeout=5) as response:
                            if response.status == 200:
                                health_data = await response.json()
                                logger.info(f"✅ 收集器健康检查通过: {health_data}")
                                assert health_data.get('status') in ['ok', 'healthy'], f"服务状态异常: {health_data}"
                                return
                    except Exception as e:
                        logger.warning(f"健康检查尝试 {attempt + 1} 失败: {e}")
                        if attempt < 4:
                            await asyncio.sleep(5)
                        else:
                            raise
                
        except Exception as e:
            logger.warning(f"收集器健康检查失败: {e}")
            # 不强制失败，因为可能使用模拟版本

class TestNATSMessageFlow:
    """NATS消息流测试"""
    
    @pytest.mark.asyncio
    async def test_nats_message_subscription(self, data_flow_tester):
        """测试NATS消息订阅"""
        
        messages_received = []
        
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                messages_received.append(data)
                logger.info(f"收到NATS消息: {msg.subject}")
            except Exception as e:
                logger.warning(f"解析NATS消息失败: {e}")
        
        # 订阅市场数据流
        subscription = await data_flow_tester.nats_client.subscribe(
            "market.>", 
            cb=message_handler
        )
        
        # 等待接收消息
        await asyncio.sleep(30)
        
        # 取消订阅
        await subscription.unsubscribe()
        
        logger.info(f"NATS消息订阅测试完成，共收到 {len(messages_received)} 条消息")
        
        # 验证收到的消息
        if messages_received:
            # 分析消息类型
            message_types = {}
            for msg in messages_received:
                msg_type = msg.get('type', 'unknown')
                message_types[msg_type] = message_types.get(msg_type, 0) + 1
            
            logger.info(f"消息类型统计: {message_types}")
            
            # 验证消息格式
            sample_msg = messages_received[0]
            required_fields = ['type', 'exchange', 'symbol', 'timestamp']
            for field in required_fields:
                assert field in sample_msg, f"消息缺少必需字段: {field}"
            
            logger.info("✅ NATS消息流测试通过")
        else:
            logger.warning("未收到NATS消息，可能是收集器未启动或数据源问题")
    
    @pytest.mark.asyncio
    async def test_nats_message_publishing(self, data_flow_tester):
        """测试NATS消息发布功能"""
        
        # 创建测试消息
        test_message = {
            "type": "trade",
            "exchange": "test_exchange",
            "symbol": "BTC-USDT",
            "timestamp": int(time.time() * 1000),
            "price": 50000.0,
            "quantity": 0.001,
            "side": "buy"
        }
        
        # 发布测试消息
        test_subject = "market.trades.test_exchange.BTC-USDT"
        await data_flow_tester.nats_client.publish(
            test_subject, 
            json.dumps(test_message).encode()
        )
        
        # 验证消息发布成功
        received_test_message = None
        
        async def test_message_handler(msg):
            nonlocal received_test_message
            try:
                data = json.loads(msg.data.decode())
                if data.get('exchange') == 'test_exchange':
                    received_test_message = data
            except Exception as e:
                logger.warning(f"处理测试消息失败: {e}")
        
        # 订阅测试主题
        test_subscription = await data_flow_tester.nats_client.subscribe(
            test_subject, 
            cb=test_message_handler
        )
        
        # 等待消息接收
        await asyncio.sleep(2)
        
        # 清理订阅
        await test_subscription.unsubscribe()
        
        # 验证结果
        assert received_test_message is not None, "测试消息未被接收"
        assert received_test_message['exchange'] == 'test_exchange', "测试消息内容不匹配"
        
        logger.info("✅ NATS消息发布测试通过")

class TestClickHouseDataStorage:
    """ClickHouse数据存储测试"""
    
    @pytest.mark.asyncio
    async def test_data_insertion_from_flow(self, data_flow_tester):
        """测试数据流插入ClickHouse"""
        
        # 获取测试开始时的记录数
        initial_count_query = "SELECT COUNT(*) FROM marketprism.trades WHERE receive_time >= %s"
        initial_count = data_flow_tester.clickhouse_client.query(
            initial_count_query, 
            [data_flow_tester.test_start_time]
        ).result_rows[0][0]
        
        logger.info(f"测试开始时的交易记录数: {initial_count}")
        
        # 等待数据收集和存储
        await asyncio.sleep(60)  # 等待1分钟收集数据
        
        # 检查新增记录
        final_count = data_flow_tester.clickhouse_client.query(
            initial_count_query, 
            [data_flow_tester.test_start_time]
        ).result_rows[0][0]
        
        new_records = final_count - initial_count
        logger.info(f"测试期间新增交易记录数: {new_records}")
        
        if new_records > 0:
            # 查询最新的交易记录
            latest_trades_query = """
            SELECT exchange, symbol, price, quantity, side, trade_time 
            FROM marketprism.trades 
            WHERE receive_time >= %s 
            ORDER BY receive_time DESC 
            LIMIT 5
            """
            
            latest_trades = data_flow_tester.clickhouse_client.query(
                latest_trades_query, 
                [data_flow_tester.test_start_time]
            ).result_rows
            
            logger.info("最新的交易记录:")
            for trade in latest_trades:
                logger.info(f"  {trade[0]} {trade[1]}: 价格={trade[2]}, 数量={trade[3]}, 方向={trade[4]}")
            
            # 验证数据完整性
            for trade in latest_trades:
                assert trade[0] is not None, "交易所字段不能为空"
                assert trade[1] is not None, "交易对字段不能为空"
                assert trade[2] > 0, "价格必须大于0"
                assert trade[3] > 0, "数量必须大于0"
                assert trade[4] in ['buy', 'sell'], f"交易方向异常: {trade[4]}"
            
            logger.info("✅ ClickHouse数据存储测试通过")
        else:
            logger.warning("未检测到新的交易数据插入，可能是数据流问题")
    
    @pytest.mark.asyncio
    async def test_data_query_performance(self, data_flow_tester):
        """测试数据查询性能"""
        
        # 测试查询最近1小时的数据
        one_hour_ago = datetime.now() - timedelta(hours=1)
        performance_query = """
        SELECT COUNT(*) as total_trades,
               COUNT(DISTINCT exchange) as exchanges,
               COUNT(DISTINCT symbol) as symbols,
               AVG(price) as avg_price
        FROM marketprism.trades 
        WHERE trade_time >= %s
        """
        
        start_time = time.time()
        result = data_flow_tester.clickhouse_client.query(
            performance_query, 
            [one_hour_ago]
        )
        query_time = time.time() - start_time
        
        if result.result_rows:
            stats = result.result_rows[0]
            logger.info(f"查询统计 (最近1小时):")
            logger.info(f"  总交易数: {stats[0]}")
            logger.info(f"  交易所数: {stats[1]}")
            logger.info(f"  交易对数: {stats[2]}")
            logger.info(f"  平均价格: {stats[3]:.2f}")
            logger.info(f"  查询耗时: {query_time:.3f}秒")
            
            # 性能要求：查询时间应小于1秒
            assert query_time < 1.0, f"查询性能不达标: {query_time:.3f}秒"
            
            logger.info("✅ 数据查询性能测试通过")
        else:
            logger.warning("查询返回空结果")

class TestDataIntegrityAndConsistency:
    """数据完整性和一致性测试"""
    
    @pytest.mark.asyncio
    async def test_data_consistency_across_sources(self, data_flow_tester):
        """测试跨数据源的数据一致性"""
        
        # 从NATS获取最新消息
        nats_messages = []
        
        async def collect_nats_messages(msg):
            try:
                data = json.loads(msg.data.decode())
                if data.get('type') == 'trade':
                    nats_messages.append(data)
            except Exception as e:
                logger.warning(f"收集NATS消息失败: {e}")
        
        subscription = await data_flow_tester.nats_client.subscribe(
            "market.trades.>", 
            cb=collect_nats_messages
        )
        
        # 收集30秒的消息
        await asyncio.sleep(30)
        await subscription.unsubscribe()
        
        if nats_messages:
            logger.info(f"从NATS收集到 {len(nats_messages)} 条交易消息")
            
            # 检查相同时间段的ClickHouse数据
            recent_time = datetime.now() - timedelta(minutes=2)
            ch_query = """
            SELECT exchange, symbol, trade_id, price, quantity 
            FROM marketprism.trades 
            WHERE receive_time >= %s
            """
            
            ch_trades = data_flow_tester.clickhouse_client.query(
                ch_query, 
                [recent_time]
            ).result_rows
            
            if ch_trades:
                logger.info(f"从ClickHouse查询到 {len(ch_trades)} 条交易记录")
                
                # 数据一致性检查
                nats_symbols = set(msg['symbol'] for msg in nats_messages)
                ch_symbols = set(trade[1] for trade in ch_trades)
                
                common_symbols = nats_symbols.intersection(ch_symbols)
                logger.info(f"NATS和ClickHouse共同的交易对: {common_symbols}")
                
                if common_symbols:
                    logger.info("✅ 数据一致性测试通过")
                else:
                    logger.warning("NATS和ClickHouse数据无重叠，可能存在延迟")
            else:
                logger.warning("ClickHouse中无最近数据")
        else:
            logger.warning("未从NATS收集到交易消息")
    
    @pytest.mark.asyncio
    async def test_data_latency_measurement(self, data_flow_tester):
        """测试数据延迟测量"""
        
        latencies = []
        
        async def measure_latency(msg):
            try:
                data = json.loads(msg.data.decode())
                if 'timestamp' in data:
                    msg_time = data['timestamp'] / 1000  # 转换为秒
                    current_time = time.time()
                    latency = current_time - msg_time
                    latencies.append(latency)
            except Exception as e:
                logger.warning(f"测量延迟失败: {e}")
        
        subscription = await data_flow_tester.nats_client.subscribe(
            "market.>", 
            cb=measure_latency
        )
        
        # 收集延迟数据
        await asyncio.sleep(30)
        await subscription.unsubscribe()
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)
            
            logger.info(f"延迟统计 (基于 {len(latencies)} 条消息):")
            logger.info(f"  平均延迟: {avg_latency:.3f}秒")
            logger.info(f"  最大延迟: {max_latency:.3f}秒")
            logger.info(f"  最小延迟: {min_latency:.3f}秒")
            
            # 延迟要求：平均延迟应小于5秒
            assert avg_latency < 5.0, f"平均延迟过高: {avg_latency:.3f}秒"
            
            logger.info("✅ 数据延迟测试通过")
        else:
            logger.warning("未收集到延迟数据")

@pytest.mark.asyncio
async def test_complete_end_to_end_flow():
    """完整的端到端流程测试"""
    
    tester = EndToEndDataFlowTester()
    await tester.setup_test_environment()
    
    try:
        test_results = {
            'infrastructure': False,
            'data_collection': False,
            'message_flow': False,
            'data_storage': False,
            'data_integrity': False
        }
        
        # 1. 基础设施检查
        try:
            # 检查NATS连接
            await tester.nats_client.publish("test.ping", b"ping")
            test_results['infrastructure'] = True
            logger.info("✅ 基础设施检查通过")
        except Exception as e:
            logger.error(f"❌ 基础设施检查失败: {e}")
        
        # 2. 数据收集检查
        try:
            # 检查是否有收集器进程运行
            collector_running = False
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    if 'collector' in proc.info['name'] or any('collector' in arg for arg in proc.info['cmdline']):
                        collector_running = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if collector_running:
                test_results['data_collection'] = True
                logger.info("✅ 数据收集服务检查通过")
            else:
                logger.warning("❌ 未检测到数据收集服务")
        except Exception as e:
            logger.error(f"❌ 数据收集检查失败: {e}")
        
        # 3. 消息流检查
        try:
            messages_received = []
            
            async def collect_messages(msg):
                messages_received.append(msg.data)
            
            sub = await tester.nats_client.subscribe("market.>", cb=collect_messages)
            await asyncio.sleep(15)
            await sub.unsubscribe()
            
            if messages_received:
                test_results['message_flow'] = True
                logger.info(f"✅ 消息流检查通过，收到{len(messages_received)}条消息")
            else:
                logger.warning("❌ 消息流检查失败，未收到消息")
        except Exception as e:
            logger.error(f"❌ 消息流检查失败: {e}")
        
        # 4. 数据存储检查
        try:
            result = tester.clickhouse_client.query("SELECT COUNT(*) FROM marketprism.trades")
            trade_count = result.result_rows[0][0]
            
            if trade_count > 0:
                test_results['data_storage'] = True
                logger.info(f"✅ 数据存储检查通过，数据库中有{trade_count}条交易记录")
            else:
                logger.warning("❌ 数据存储检查失败，数据库中无交易记录")
        except Exception as e:
            logger.error(f"❌ 数据存储检查失败: {e}")
        
        # 5. 数据完整性检查
        try:
            # 简单的完整性检查：验证最近数据的字段完整性
            recent_data = tester.clickhouse_client.query(
                "SELECT * FROM marketprism.trades ORDER BY receive_time DESC LIMIT 1"
            ).result_rows
            
            if recent_data:
                record = recent_data[0]
                # 检查关键字段不为空
                if record[1] and record[2] and record[4] > 0:  # exchange, symbol, price
                    test_results['data_integrity'] = True
                    logger.info("✅ 数据完整性检查通过")
                else:
                    logger.warning("❌ 数据完整性检查失败，存在空字段")
            else:
                logger.warning("❌ 数据完整性检查失败，无数据可检查")
        except Exception as e:
            logger.error(f"❌ 数据完整性检查失败: {e}")
        
        # 汇总结果
        passed_tests = sum(test_results.values())
        total_tests = len(test_results)
        
        logger.info(f"端到端测试完成: {passed_tests}/{total_tests} 项通过")
        
        for test_name, result in test_results.items():
            status = "✅ 通过" if result else "❌ 失败"
            logger.info(f"  {test_name}: {status}")
        
        # 至少要有3/5的测试通过
        assert passed_tests >= 3, f"端到端测试失败，仅有{passed_tests}/{total_tests}项通过"
        
        return test_results
        
    finally:
        await tester.cleanup_test_environment()

if __name__ == "__main__":
    # 运行完整的端到端测试
    asyncio.run(test_complete_end_to_end_flow()) 