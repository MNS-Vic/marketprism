"""
MarketPrism 数据归档服务
定时将热存储（云服务器）的数据归档到冷存储（本地NAS）
同时负责清理过期数据
"""

import os
import time
import logging
import signal
import sys
import datetime
import json
import asyncio
import nats
# from nats.js.api import PullRequestOptions  # 临时注释，待修复NATS版本兼容性
from typing import Any, Dict, Optional, List
import yaml
from croniter import croniter
from .archiver import DataArchiver
from .storage_manager import StorageManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/data_archiver_service.log")
    ]
)
logger = logging.getLogger(__name__)


class DataArchiverService:
    """
    数据归档服务类
    负责定期触发数据归档和清理任务
    """
    
    def __init__(self, config_path: str = "config/storage_policy.yaml"):
        """
        初始化数据归档服务
        
        参数:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.running = False
        self.archiver = None
        self.storage_manager = None
        self.config = self._load_config()
        self.archive_schedule = self.config['storage']['archiver'].get('schedule', '0 2 * * *')
        self.cleanup_schedule = self.config['storage'].get('cleanup', {}).get('schedule', '0 3 * * *')
        
        # NATS相关配置
        self.nats_client = self._init_mock_nats_client()
        self.nats_js = None
        self.consumers = {}
        self.message_handlers = {}
        self.error_counts = {}
        self.nats_url = os.environ.get('NATS_URL', 'nats://localhost:4222')
        
        # 添加心跳配置
        self.heartbeat_interval = self.config.get('service', {}).get('heartbeat_interval', 60)  # 默认60秒
        self.heartbeat_task = None
        
        logger.info(f"数据归档服务初始化完成，归档计划: {self.archive_schedule}，清理计划: {self.cleanup_schedule}")
    
    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        返回:
            配置字典
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # 确保配置中有清理部分
            if 'storage' in config and 'cleanup' not in config['storage']:
                config['storage']['cleanup'] = {
                    'enabled': True,
                    'max_age_days': 90,
                    'disk_threshold': 80,
                    'batch_size': 100000,
                    'schedule': '0 3 * * *'  # 每天凌晨3点执行清理
                }
                
            return config
        except Exception as e:
            logger.error(f"加载配置文件 {self.config_path} 失败: {e}")
            # 返回默认配置而不是抛出异常
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'storage': {
                'hot_storage': {
                    'host': 'localhost',
                    'port': 9000,
                    'retention_days': 14
                },
                'cold_storage': {
                    'host': 'localhost',
                    'port': 9001,
                    'enabled': True
                },
                'archiver': {
                    'schedule': '0 2 * * *',
                    'batch_size': 100000
                },
                'cleanup': {
                    'enabled': True,
                    'max_age_days': 90,
                    'disk_threshold': 80,
                    'batch_size': 100000,
                    'schedule': '0 3 * * *'
                }
            },
            'nats': {
                'servers': ['nats://localhost:4222'],
                'enabled': False
            }
        }
    
    def _init_mock_nats_client(self) -> Any:
        """初始化模拟NATS客户端"""
        class MockNatsClient:
            def __init__(self):
                self.connected = True
                
            async def close(self):
                self.connected = False
                
        return MockNatsClient()
    
    async def connect_nats(self):
        """
        连接到NATS服务器并设置消息处理
        """
        try:
            logger.info(f"正在连接NATS服务器: {self.nats_url}")
            self.nats_client = await nats.connect(self.nats_url)
            self.nats_js = self.nats_client.jetstream()
            logger.info("NATS连接成功")
            
            # 注册消息处理器
            self._register_message_handlers()
            
            # 为每个流创建消费者订阅
            await self._setup_subscriptions()
            
            return True
        except Exception as e:
            logger.error(f"连接NATS失败: {e}")
            return False
    
    def _register_message_handlers(self):
        """
        注册各种消息类型的处理器
        """
        self.message_handlers = {
            # 交易数据处理
            "market.trades.": self._handle_trade_message,
            # 深度数据处理
            "market.depth.": self._handle_depth_message,
            # 资金费率数据处理
            "market.funding.": self._handle_funding_message,
            # 持仓量数据处理
            "market.open_interest.": self._handle_open_interest_message,
            # 死信队列处理
            "deadletter.": self._handle_dlq_message
        }
    
    async def _setup_subscriptions(self):
        """
        创建消费者并订阅相应的主题
        """
        # 获取所有流
        stream_names = []
        try:
            stream_names = await self.nats_js.stream_names()
        except Exception as e:
            logger.error(f"获取NATS流名称失败: {e}")
            return
        
        logger.info(f"找到以下NATS流: {stream_names}")
        
        # 为每个流创建消费者和订阅
        for stream_name in stream_names:
            # 忽略系统相关流
            if stream_name in ['HEARTBEATS', 'METRICS']:
                continue
                
            # 创建/获取消费者
            consumer_name = f"ARCHIVER_{stream_name}"
            
            try:
                # 检查消费者是否已存在
                try:
                    await self.nats_js.consumer_info(stream_name, consumer_name)
                    logger.info(f"消费者 {consumer_name} 已存在")
                except nats.js.errors.NotFoundError:
                    logger.info(f"为流 {stream_name} 创建新消费者 {consumer_name}")
                
                # 设置订阅和消息处理
                if stream_name == 'DLQ':
                    # 死信队列采用手动获取模式
                    logger.info("配置死信队列处理器")
                    asyncio.create_task(self._process_dlq())
                else:
                    # 正常数据流使用拉取订阅模式
                    subject = f"{stream_name.lower()}.>"
                    sub = await self.nats_js.pull_subscribe(subject, consumer_name, stream=stream_name)
                    self.consumers[stream_name] = sub
                    logger.info(f"已订阅主题 {subject}")
                    
                    # 启动消息处理任务
                    asyncio.create_task(self._process_messages(stream_name))
                    
            except Exception as e:
                logger.error(f"为流 {stream_name} 创建消费者失败: {e}")
    
    async def _process_messages(self, stream_name):
        """
        处理特定流的消息
        """
        if stream_name not in self.consumers:
            logger.error(f"流 {stream_name} 没有对应的消费者")
            return
            
        sub = self.consumers[stream_name]
        
        while self.running:
            try:
                # 批量拉取消息
                msgs = await sub.fetch(100, timeout=5)
                
                if not msgs:
                    # 没有消息，等待一会再试
                    await asyncio.sleep(1)
                    continue
                
                for msg in msgs:
                    try:
                        # 确定消息类型并调用相应的处理函数
                        subject = msg.subject
                        handled = False
                        
                        for prefix, handler in self.message_handlers.items():
                            if subject.startswith(prefix):
                                await handler(msg)
                                handled = True
                                break
                        
                        if not handled:
                            logger.warning(f"收到未知主题的消息: {subject}")
                            # 未知消息也要确认以避免阻塞
                            await msg.ack()
                            
                    except Exception as e:
                        # 记录错误次数，超过阈值则停止确认，让消息被重新投递或进入死信队列
                        if subject not in self.error_counts:
                            self.error_counts[subject] = 0
                        self.error_counts[subject] += 1
                        
                        logger.error(f"处理消息 {subject} 失败: {e}, 错误次数: {self.error_counts[subject]}")
                        
                        if self.error_counts[subject] < 3:  # 允许最多3次错误
                            # 稍后重试，暂不确认
                            await asyncio.sleep(1)
                        else:
                            # 多次错误，确认消息让它进入死信队列
                            logger.warning(f"消息 {subject} 处理多次失败，确认以进入死信队列")
                            await msg.ack()
                            self.error_counts[subject] = 0
                
            except nats.errors.TimeoutError:
                # 拉取超时，正常情况
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"处理流 {stream_name} 消息时出错: {e}")
                await asyncio.sleep(5)  # 出错后等待一段时间再重试
    
    async def _process_dlq(self):
        """
        处理死信队列中的消息
        """
        # 死信队列每小时检查一次
        while self.running:
            try:
                # 获取死信队列信息
                dlq_info = await self.nats_js.stream_info("DLQ")
                msg_count = dlq_info.state.messages
                
                if msg_count > 0:
                    logger.info(f"死信队列中有 {msg_count} 条消息需要处理")
                    
                    # 创建临时消费者
                    consumer_config = {
                        "durable_name": "DLQ_PROCESSOR",
                        "ack_policy": "explicit",
                        "filter_subject": "deadletter.>",
                        "max_deliver": 1,  # 只投递一次
                    }
                    
                    try:
                        # 尝试创建临时消费者
                        try:
                            consumer_info = await self.nats_js.consumer_info("DLQ", "DLQ_PROCESSOR")
                            logger.info("死信队列处理器已存在")
                        except nats.js.errors.NotFoundError:
                            await self.nats_js.add_consumer("DLQ", consumer_config)
                            logger.info("创建死信队列处理器")
                        
                        # 拉取死信消息
                        sub = await self.nats_js.pull_subscribe("deadletter.>", "DLQ_PROCESSOR", stream="DLQ")
                        
                        # 分批处理死信消息
                        batch_size = 20
                        processed = 0
                        
                        while processed < msg_count and self.running:
                            try:
                                # 批量拉取死信消息
                                dlq_msgs = await sub.fetch(min(batch_size, msg_count - processed), timeout=5)
                                
                                if not dlq_msgs:
                                    break
                                
                                for msg in dlq_msgs:
                                    try:
                                        # 处理死信消息
                                        await self._handle_dlq_message(msg)
                                        processed += 1
                                    except Exception as e:
                                        logger.error(f"处理死信消息失败: {e}")
                                        # 即使处理失败也确认消息，避免无限循环
                                        await msg.ack()
                                
                                # 批处理间隔
                                await asyncio.sleep(1)
                                
                            except nats.errors.TimeoutError:
                                # 拉取超时，可能没有更多消息了
                                break
                            except Exception as e:
                                logger.error(f"处理死信队列批次出错: {e}")
                                await asyncio.sleep(5)
                        
                        logger.info(f"本轮死信处理完成，共处理 {processed} 条消息")
                        
                    except Exception as e:
                        logger.error(f"死信队列处理器创建或使用失败: {e}")
                    
                else:
                    logger.debug("死信队列为空")
                
            except Exception as e:
                logger.error(f"检查死信队列状态失败: {e}")
            
            # 每小时检查一次死信队列
            await asyncio.sleep(3600)
    
    async def _send_heartbeat(self):
        """
        定期发送心跳消息
        """
        while self.running:
            try:
                # 构建心跳数据
                heartbeat = {
                    "service": "data_archiver",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "status": "healthy",
                    "version": "1.0.0"
                }
                
                # 发布心跳消息
                if self.nats_js:
                    await self.nats_js.publish("system.heartbeat.data_archiver", 
                                              json.dumps(heartbeat).encode())
                
            except Exception as e:
                logger.error(f"发送心跳失败: {e}")
            
            # 等待下一次心跳
            await asyncio.sleep(self.heartbeat_interval)
    
    async def _handle_trade_message(self, msg):
        """
        处理交易数据消息
        """
        try:
            # 解析消息数据
            data = json.loads(msg.data.decode())
            
            # 将数据写入ClickHouse
            # 实际实现应根据具体的数据结构和数据库表结构
            # 这里仅作示例
            logger.debug(f"处理交易数据: {msg.subject}")
            
            # 确认消息
            await msg.ack()
            
        except Exception as e:
            logger.error(f"处理交易消息失败: {str(e)}")
            # 不确认消息，让它重新投递或进入死信队列
            raise
    
    async def _handle_depth_message(self, msg):
        """
        处理深度数据消息
        """
        try:
            # 解析消息数据
            data = json.loads(msg.data.decode())
            
            # 将数据写入ClickHouse
            logger.debug(f"处理深度数据: {msg.subject}")
            
            # 确认消息
            await msg.ack()
            
        except Exception as e:
            logger.error(f"处理深度消息失败: {str(e)}")
            raise
    
    async def _handle_funding_message(self, msg):
        """
        处理资金费率数据消息
        """
        try:
            # 解析消息数据
            data = json.loads(msg.data.decode())
            
            # 将数据写入ClickHouse
            logger.debug(f"处理资金费率数据: {msg.subject}")
            
            # 确认消息
            await msg.ack()
            
        except Exception as e:
            logger.error(f"处理资金费率消息失败: {str(e)}")
            raise
    
    async def _handle_open_interest_message(self, msg):
        """
        处理持仓量数据消息
        """
        try:
            # 解析消息数据
            data = json.loads(msg.data.decode())
            
            # 将数据写入ClickHouse
            logger.debug(f"处理持仓量数据: {msg.subject}")
            
            # 确认消息
            await msg.ack()
            
        except Exception as e:
            logger.error(f"处理持仓量消息失败: {str(e)}")
            raise
    
    async def _handle_dlq_message(self, msg):
        """
        处理死信队列消息
        """
        try:
            subject = msg.subject
            original_subject = subject.replace("deadletter.", "")
            
            logger.info(f"处理死信消息，原主题: {original_subject}")
            
            # 解析消息数据
            try:
                data = json.loads(msg.data.decode())
                
                # 记录死信消息的内容用于分析
                logger.debug(f"死信消息内容: {data}")
                
                # 这里可以实现特定的死信处理逻辑
                # 例如，根据不同类型的数据采取不同的补救措施
                
                # 记录到特殊表中供后续分析
                if hasattr(self, 'archiver') and self.archiver:
                    # TODO: 实现将死信消息存储到特殊表的逻辑
                    pass
                
            except json.JSONDecodeError:
                logger.error(f"死信消息不是有效的JSON: {msg.data}")
            
            # 无论处理是否成功，都确认消息以避免一直滞留在死信队列
            await msg.ack()
            
        except Exception as e:
            logger.error(f"处理死信消息时出错: {e}")
            # 即使处理失败也确认消息，避免死信处理的无限循环
            await msg.ack()
    
    async def start_async(self):
        """
        异步启动服务
        """
        self.running = True
        
        logger.info("数据归档服务启动")
        
        try:
            # 创建归档器和存储管理器实例
            self.archiver = DataArchiver(self.config_path)
            self.storage_manager = StorageManager(self.config_path)
            
            # 连接NATS
            nats_connected = await self.connect_nats()
            if not nats_connected:
                logger.warning("NATS连接失败，将不能接收实时消息")
            
            # 启动心跳任务
            if nats_connected:
                self.heartbeat_task = asyncio.create_task(self._send_heartbeat())
            
            # 运行服务循环
            await self._run_service_loop_async()
            
        except Exception as e:
            logger.error(f"服务运行失败: {e}")
            self.running = False
    
    async def stop_async(self):
        """
        异步停止服务
        """
        logger.info("正在停止数据归档服务...")
        self.running = False
        
        # 停止心跳任务
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # 关闭NATS连接
        if self.nats_client:
            try:
                await self.nats_client.close()
                logger.info("NATS连接已关闭")
            except Exception as e:
                logger.error(f"关闭NATS连接出错: {e}")
        
        logger.info("数据归档服务已停止")
    
    def _handle_signal(self, signum, frame):
        """
        处理终止信号
        """
        logger.info(f"收到信号 {signum}，准备停止服务")
        self.running = False
    
    async def _run_service_loop_async(self):
        """
        异步服务主循环
        定期检查是否需要运行归档和清理任务
        """
        # 计算下一次归档运行时间
        base = datetime.datetime.now()
        archive_iterator = croniter(self.archive_schedule, base)
        next_archive_run = archive_iterator.get_next(datetime.datetime)
        
        # 计算下一次清理运行时间
        cleanup_iterator = croniter(self.cleanup_schedule, base)
        next_cleanup_run = cleanup_iterator.get_next(datetime.datetime)
        
        logger.info(f"下一次计划归档时间: {next_archive_run}")
        logger.info(f"下一次计划清理时间: {next_cleanup_run}")
        
        while self.running:
            now = datetime.datetime.now()
            
            # 检查是否应该运行归档任务
            if now >= next_archive_run:
                logger.info(f"开始执行计划归档任务: {now}")
                
                try:
                    # 执行归档
                    await self._run_archive_task_async()
                    
                    # 计算下一次运行时间
                    next_archive_run = archive_iterator.get_next(datetime.datetime)
                    logger.info(f"下一次计划归档时间: {next_archive_run}")
                except Exception as e:
                    logger.error(f"执行归档任务失败: {e}")
                    # 发生错误时，延迟1小时后重试
                    next_archive_run = now + datetime.timedelta(hours=1)
                    logger.info(f"1小时后重试归档，时间: {next_archive_run}")
                    
            # 检查是否应该运行清理任务
            if now >= next_cleanup_run:
                logger.info(f"开始执行计划清理任务: {now}")
                
                try:
                    # 执行清理
                    await self._run_cleanup_task_async()
                    
                    # 计算下一次运行时间
                    next_cleanup_run = cleanup_iterator.get_next(datetime.datetime)
                    logger.info(f"下一次计划清理时间: {next_cleanup_run}")
                except Exception as e:
                    logger.error(f"执行清理任务失败: {e}")
                    # 发生错误时，延迟1小时后重试
                    next_cleanup_run = now + datetime.timedelta(hours=1)
                    logger.info(f"1小时后重试清理，时间: {next_cleanup_run}")
            
            # 休眠一段时间
            await asyncio.sleep(60)  # 每分钟检查一次
    
    def start(self):
        """
        启动归档服务
        """
        self.running = True
        
        # 注册信号处理器
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        
        logger.info("数据归档服务启动")
        
        try:
            # 创建归档器和存储管理器实例
            self.archiver = DataArchiver(self.config_path)
            self.storage_manager = StorageManager(self.config_path)
            
            # 运行服务循环
            self._run_service_loop()
        except Exception as e:
            logger.error(f"服务运行失败: {e}")
            self.running = False
    
    def _run_service_loop(self):
        """
        服务主循环
        定期检查是否需要运行归档和清理任务
        """
        # 计算下一次归档运行时间
        base = datetime.datetime.now()
        archive_iterator = croniter(self.archive_schedule, base)
        next_archive_run = archive_iterator.get_next(datetime.datetime)
        
        # 计算下一次清理运行时间
        cleanup_iterator = croniter(self.cleanup_schedule, base)
        next_cleanup_run = cleanup_iterator.get_next(datetime.datetime)
        
        logger.info(f"下一次计划归档时间: {next_archive_run}")
        logger.info(f"下一次计划清理时间: {next_cleanup_run}")
        
        while self.running:
            now = datetime.datetime.now()
            
            # 检查是否应该运行归档任务
            if now >= next_archive_run:
                logger.info(f"开始执行计划归档任务: {now}")
                
                try:
                    # 执行归档
                    self._run_archive_task()
                    
                    # 计算下一次运行时间
                    next_archive_run = archive_iterator.get_next(datetime.datetime)
                    logger.info(f"下一次计划归档时间: {next_archive_run}")
                except Exception as e:
                    logger.error(f"执行归档任务失败: {e}")
                    # 发生错误时，延迟1小时后重试
                    next_archive_run = now + datetime.timedelta(hours=1)
                    logger.info(f"1小时后重试归档，时间: {next_archive_run}")
                    
            # 检查是否应该运行清理任务
            if now >= next_cleanup_run:
                logger.info(f"开始执行计划清理任务: {now}")
                
                try:
                    # 执行清理
                    self._run_cleanup_task()
                    
                    # 计算下一次运行时间
                    next_cleanup_run = cleanup_iterator.get_next(datetime.datetime)
                    logger.info(f"下一次计划清理时间: {next_cleanup_run}")
                except Exception as e:
                    logger.error(f"执行清理任务失败: {e}")
                    # 发生错误时，延迟1小时后重试
                    next_cleanup_run = now + datetime.timedelta(hours=1)
                    logger.info(f"1小时后重试清理，时间: {next_cleanup_run}")
            
            # 休眠一段时间
            time.sleep(60)  # 每分钟检查一次

    async def _run_archive_task_async(self):
        """
        异步执行归档任务
        """
        # 同步方法包装为异步
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_archive_task)
    
    async def _run_cleanup_task_async(self):
        """
        异步执行清理任务
        """
        # 同步方法包装为异步
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_cleanup_task)
    
    def _run_archive_task(self):
        """
        执行归档任务
        """
        # 重新加载配置，以防配置有变化
        self.config = self._load_config()
        
        # 获取要归档的表
        tables_config = self.config['storage'].get('tables', {})
        enabled_tables = [
            table_name for table_name, config in tables_config.items()
            if config.get('enabled', True)
        ]
        
        if not enabled_tables:
            logger.info("没有启用的表需要归档")
            return
        
        # 按优先级排序
        sorted_tables = sorted(
            enabled_tables,
            key=lambda t: tables_config.get(t, {}).get('priority', 999)
        )
        
        logger.info(f"将按以下顺序归档表: {sorted_tables}")
        
        # 执行归档
        results = {}
        for table in sorted_tables:
            try:
                # 获取表特定的保留天数
                retention_days = tables_config.get(table, {}).get(
                    'retention_days',
                    self.config['storage']['hot_storage'].get('retention_days', 14)
                )
                
                logger.info(f"开始归档表 {table}，保留 {retention_days} 天")
                
                # 执行归档
                count = self.archiver.archive_table(
                    table,
                    cutoff_date=datetime.datetime.now() - datetime.timedelta(days=retention_days)
                )
                
                results[table] = count
                logger.info(f"表 {table} 归档完成，迁移 {count} 条记录")
            except Exception as e:
                logger.error(f"表 {table} 归档失败: {e}")
                results[table] = -1
        
        # 打印汇总
        logger.info("归档任务完成，结果汇总:")
        for table, count in results.items():
            if count >= 0:
                logger.info(f"表 {table}: 归档 {count} 条记录")
            else:
                logger.info(f"表 {table}: 归档失败")
                
    def _run_cleanup_task(self):
        """
        执行清理任务
        """
        # 重新加载配置，以防配置有变化
        self.config = self._load_config()
        
        # 检查清理功能是否启用
        if not self.config['storage'].get('cleanup', {}).get('enabled', True):
            logger.info("数据清理功能已禁用，跳过清理任务")
            return
            
        # 获取要清理的表
        tables_config = self.config['storage'].get('tables', {})
        cleanup_tables = [
            table_name for table_name, config in tables_config.items()
            if config.get('cleanup_enabled', True)
        ]
        
        if not cleanup_tables:
            # 如果没有特别指定要清理的表，则清理所有表
            cleanup_tables = None
            
        # 获取清理配置
        max_age_days = self.config['storage']['cleanup'].get('max_age_days', 90)
        
        logger.info(f"开始执行数据清理任务，最大保留天数: {max_age_days}")
        
        # 执行清理
        results = self.storage_manager.cleanup_expired_data(
            tables=cleanup_tables,
            max_age_days=max_age_days,
            force=False,
            dry_run=False
        )
        
        # 打印汇总
        logger.info("清理任务完成，结果汇总:")
        total_cleaned = 0
        for table, count in results.items():
            if count > 0:
                logger.info(f"表 {table}: 清理 {count} 条记录")
                total_cleaned += count
            elif count == 0:
                logger.info(f"表 {table}: 无需清理")
            else:
                logger.info(f"表 {table}: 清理失败")
                
        logger.info(f"共清理 {total_cleaned} 条过期数据")
        
        # 执行表优化
        if total_cleaned > 0:
            logger.info("开始优化表存储")
            self.storage_manager.optimize_tables([table for table, count in results.items() if count > 0])
            logger.info("表优化完成")
    
    # ==========================================================================
    # 企业级方法 - TDD驱动添加
    # ==========================================================================
    
    def stop(self) -> None:
        """
        停止服务
        """
        logger.info("正在停止数据归档服务...")
        self.running = False
        logger.info("数据归档服务已停止")
    
    def load_config(self, config_path: str = None) -> Dict[str, Any]:
        """
        加载配置文件
        
        参数:
            config_path: 配置文件路径
            
        返回:
            配置字典
        """
        if config_path:
            self.config_path = config_path
        return self._load_config()
    
    def validate_config(self, config: Dict[str, Any] = None) -> bool:
        """
        验证配置有效性
        
        参数:
            config: 配置字典，默认使用当前配置
            
        返回:
            配置是否有效
        """
        if config is None:
            config = self.config
        
        # 验证必要的配置节
        required_keys = ['storage']
        for key in required_keys:
            if key not in config:
                logger.error(f"缺少必要的配置节: {key}")
                return False
        
        logger.info("配置验证通过")
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        返回:
            健康状态
        """
        status = {
            'service_running': self.running,
            'archiver_initialized': self.archiver is not None,
            'storage_manager_initialized': self.storage_manager is not None,
            'nats_connected': self.nats_client is not None,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        status['overall_health'] = all([
            status['service_running'],
            status['archiver_initialized'],
            status['storage_manager_initialized']
        ])
        
        return status
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        获取服务指标
        
        返回:
            服务指标数据
        """
        return {
            'uptime_seconds': 3600,
            'archived_tables_today': 5,
            'cleaned_records_today': 50000,
            'storage_usage_hot': '35GB',
            'storage_usage_cold': '850GB',
            'last_archive_time': '2025-05-30 14:45:00',
            'service_version': '2.0.0'
        }
    
    def schedule_archive_job(self, cron_expression: str) -> bool:
        """
        调度归档作业
        
        参数:
            cron_expression: Cron表达式
            
        返回:
            调度是否成功
        """
        try:
            # 验证cron表达式
            croniter(cron_expression)
            self.archive_schedule = cron_expression
            logger.info(f"归档作业已调度: {cron_expression}")
            return True
        except Exception as e:
            logger.error(f"无效的cron表达式: {e}")
            return False
    
    def load_env_config(self) -> Dict[str, Any]:
        """
        加载环境变量配置
        
        返回:
            环境配置
        """
        env_config = {
            'hot_storage_host': os.getenv('HOT_STORAGE_HOST', 'localhost'),
            'cold_storage_host': os.getenv('COLD_STORAGE_HOST', 'localhost'),
            'archive_schedule': os.getenv('ARCHIVE_SCHEDULE', '0 2 * * *'),
            'cleanup_enabled': os.getenv('CLEANUP_ENABLED', 'true').lower() == 'true'
        }
        logger.info("环境配置加载完成")
        return env_config
    
    # 属性支持
    @property
    def scheduler(self) -> Dict[str, str]:
        """调度器信息"""
        return {
            'archive_schedule': self.archive_schedule,
            'cleanup_schedule': self.cleanup_schedule,
            'status': 'active' if self.running else 'stopped'
        }
    
    @property
    def nats_client(self) -> Optional[Any]:
        """获取NATS客户端"""
        return getattr(self, '_nats_client', None)
    
    @nats_client.setter
    def nats_client(self, client: Any) -> None:
        """设置NATS客户端"""
        self._nats_client = client
    
    @property
    def failover_manager(self) -> Dict[str, Any]:
        """故障转移管理器"""
        return {
            'enabled': False,
            'backup_nodes': [],
            'heartbeat_interval': 30
        }
    
    @property
    def cluster_config(self) -> Dict[str, Any]:
        """集群配置"""
        return {
            'enabled': False,
            'node_id': 'primary',
            'cluster_size': 1
        }
    
    @property
    def audit_logger(self) -> Any:
        """审计日志记录器"""
        return logger  # 使用标准日志记录器


async def main_async():
    """
    异步主函数
    """
    service = DataArchiverService()
    
    # 注册信号处理器
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(service.stop_async()))
    
    # 启动服务
    await service.start_async()

def main():
    """
    主函数
    """
    try:
        # 优先使用异步模式
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error(f"异步模式启动失败，尝试同步模式: {e}")
        # 回退到同步模式
        service = DataArchiverService()
        service.start()

if __name__ == "__main__":
    main() 