"""
MarketPrism 热端数据存储服务
从NATS JetStream订阅数据并实时写入热端ClickHouse数据库
"""

import asyncio
import json
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import structlog
import nats
from nats.js import JetStreamContext

from core.storage.tiered_storage_manager import TieredStorageManager, TierConfig, StorageTier
from core.observability.logging.unified_logger import UnifiedLogger


class HotStorageService:
    """热端数据存储服务"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化热端存储服务
        
        Args:
            config: 服务配置
        """
        # 初始化日志
        self.logger = structlog.get_logger("services.data_storage.hot_storage")
        
        # 配置
        self.config = config
        self.nats_config = config.get('nats', {})
        self.hot_storage_config = config.get('hot_storage', {})
        
        # NATS连接
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None
        
        # 分层存储管理器
        self.storage_manager: Optional[TieredStorageManager] = None
        
        # 订阅管理
        self.subscriptions: Dict[str, Any] = {}
        
        # 运行状态
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
        # 统计信息
        self.stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "last_message_time": None,
            "data_types": {
                "orderbook": {"received": 0, "processed": 0, "failed": 0},
                "trade": {"received": 0, "processed": 0, "failed": 0},
                "funding_rate": {"received": 0, "processed": 0, "failed": 0},
                "open_interest": {"received": 0, "processed": 0, "failed": 0},
                "liquidation": {"received": 0, "processed": 0, "failed": 0},
                "lsr": {"received": 0, "processed": 0, "failed": 0},
                "volatility_index": {"received": 0, "processed": 0, "failed": 0}
            }
        }
    
    async def initialize(self):
        """初始化热端存储服务"""
        try:
            self.logger.info("🚀 初始化热端数据存储服务")
            
            # 初始化分层存储管理器
            await self._initialize_storage_manager()
            
            # 连接NATS
            await self._connect_nats()
            
            # 设置订阅
            await self._setup_subscriptions()
            
            self.logger.info("✅ 热端数据存储服务初始化完成")
            
        except Exception as e:
            self.logger.error("❌ 热端数据存储服务初始化失败", error=str(e))
            raise
    
    async def _initialize_storage_manager(self):
        """初始化分层存储管理器"""
        try:
            # 创建热端配置
            hot_config = TierConfig(
                tier=StorageTier.HOT,
                clickhouse_host=self.hot_storage_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=self.hot_storage_config.get('clickhouse_port', 9000),
                clickhouse_user=self.hot_storage_config.get('clickhouse_user', 'default'),
                clickhouse_password=self.hot_storage_config.get('clickhouse_password', ''),
                clickhouse_database=self.hot_storage_config.get('clickhouse_database', 'marketprism_hot'),
                retention_days=self.hot_storage_config.get('retention_days', 3),
                batch_size=self.hot_storage_config.get('batch_size', 1000),
                flush_interval=self.hot_storage_config.get('flush_interval', 5)
            )
            
            # 创建冷端配置（用于数据传输）
            cold_storage_config = self.config.get('cold_storage', {})
            cold_config = TierConfig(
                tier=StorageTier.COLD,
                clickhouse_host=cold_storage_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=cold_storage_config.get('clickhouse_port', 9000),
                clickhouse_user=cold_storage_config.get('clickhouse_user', 'default'),
                clickhouse_password=cold_storage_config.get('clickhouse_password', ''),
                clickhouse_database=cold_storage_config.get('clickhouse_database', 'marketprism_cold'),
                retention_days=cold_storage_config.get('retention_days', 365),
                batch_size=cold_storage_config.get('batch_size', 5000),
                flush_interval=cold_storage_config.get('flush_interval', 30)
            )
            
            # 初始化分层存储管理器
            self.storage_manager = TieredStorageManager(hot_config, cold_config)
            await self.storage_manager.initialize()
            
            self.logger.info("✅ 分层存储管理器初始化完成")
            
        except Exception as e:
            self.logger.error("❌ 分层存储管理器初始化失败", error=str(e))
            raise
    
    async def _connect_nats(self):
        """连接NATS服务器"""
        try:
            nats_url = self.nats_config.get('url', 'nats://localhost:4222')
            
            self.nats_client = await nats.connect(
                servers=[nats_url],
                max_reconnect_attempts=self.nats_config.get('max_reconnect_attempts', 10),
                reconnect_time_wait=self.nats_config.get('reconnect_time_wait', 2)
            )
            
            # 获取JetStream上下文
            self.jetstream = self.nats_client.jetstream()
            
            self.logger.info("✅ NATS连接建立成功", url=nats_url)
            
        except Exception as e:
            self.logger.error("❌ NATS连接失败", error=str(e))
            raise
    
    async def _setup_subscriptions(self):
        """设置NATS订阅"""
        try:
            # 订阅配置
            subscription_config = self.config.get('subscriptions', {})
            
            # 订阅各种数据类型
            data_types = ["orderbook", "trade", "funding_rate", "open_interest", 
                         "liquidation", "lsr", "volatility_index"]
            
            for data_type in data_types:
                if subscription_config.get(f'{data_type}_enabled', True):
                    await self._subscribe_to_data_type(data_type)
            
            self.logger.info("✅ NATS订阅设置完成", 
                           subscriptions=len(self.subscriptions))
            
        except Exception as e:
            self.logger.error("❌ NATS订阅设置失败", error=str(e))
            raise
    
    async def _subscribe_to_data_type(self, data_type: str):
        """订阅特定数据类型"""
        try:
            # 构建主题模式
            subject_pattern = f"{data_type}-data.>"
            
            # 创建订阅
            subscription = await self.jetstream.subscribe(
                subject=subject_pattern,
                cb=lambda msg, dt=data_type: asyncio.create_task(
                    self._handle_message(msg, dt)
                ),
                durable=f"hot_storage_{data_type}",
                config=nats.js.api.ConsumerConfig(
                    deliver_policy=nats.js.api.DeliverPolicy.NEW,
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                    max_deliver=3,
                    ack_wait=30
                )
            )
            
            self.subscriptions[data_type] = subscription
            
            self.logger.info("✅ 数据类型订阅成功", 
                           data_type=data_type,
                           subject=subject_pattern)
            
        except Exception as e:
            self.logger.error("❌ 数据类型订阅失败", 
                            data_type=data_type, error=str(e))
            raise
    
    async def _handle_message(self, msg, data_type: str):
        """处理NATS消息"""
        try:
            # 更新统计
            self.stats["messages_received"] += 1
            self.stats["data_types"][data_type]["received"] += 1
            self.stats["last_message_time"] = datetime.now(timezone.utc)
            
            # 解析消息
            try:
                data = json.loads(msg.data.decode())
            except json.JSONDecodeError as e:
                self.logger.error("❌ 消息JSON解析失败", 
                                data_type=data_type, error=str(e))
                await msg.nak()
                self.stats["messages_failed"] += 1
                self.stats["data_types"][data_type]["failed"] += 1
                return
            
            # 存储到热端
            success = await self.storage_manager.store_to_hot(data_type, data)
            
            if success:
                # 确认消息
                await msg.ack()
                self.stats["messages_processed"] += 1
                self.stats["data_types"][data_type]["processed"] += 1
                
                self.logger.debug("✅ 消息处理成功", 
                                data_type=data_type,
                                subject=msg.subject)
            else:
                # 拒绝消息，触发重试
                await msg.nak()
                self.stats["messages_failed"] += 1
                self.stats["data_types"][data_type]["failed"] += 1
                
                self.logger.error("❌ 消息存储失败", 
                                data_type=data_type,
                                subject=msg.subject)
            
        except Exception as e:
            # 处理异常，拒绝消息
            try:
                await msg.nak()
            except:
                pass
            
            self.stats["messages_failed"] += 1
            self.stats["data_types"][data_type]["failed"] += 1
            
            self.logger.error("❌ 消息处理异常", 
                            data_type=data_type,
                            subject=msg.subject,
                            error=str(e))
    
    async def start(self):
        """启动热端存储服务"""
        try:
            self.logger.info("🚀 启动热端数据存储服务")
            
            self.is_running = True
            
            # 设置信号处理
            self._setup_signal_handlers()
            
            self.logger.info("✅ 热端数据存储服务已启动")
            
            # 等待关闭信号
            await self.shutdown_event.wait()
            
        except Exception as e:
            self.logger.error("❌ 热端数据存储服务启动失败", error=str(e))
            raise
    
    async def stop(self):
        """停止热端存储服务"""
        try:
            self.logger.info("🛑 停止热端数据存储服务")
            
            self.is_running = False
            
            # 关闭订阅
            for data_type, subscription in self.subscriptions.items():
                try:
                    await subscription.unsubscribe()
                    self.logger.info("✅ 订阅已关闭", data_type=data_type)
                except Exception as e:
                    self.logger.error("❌ 关闭订阅失败", 
                                    data_type=data_type, error=str(e))
            
            # 关闭NATS连接
            if self.nats_client:
                await self.nats_client.close()
                self.logger.info("✅ NATS连接已关闭")
            
            # 关闭存储管理器
            if self.storage_manager:
                await self.storage_manager.close()
                self.logger.info("✅ 存储管理器已关闭")
            
            # 设置关闭事件
            self.shutdown_event.set()
            
            self.logger.info("✅ 热端数据存储服务已停止")
            
        except Exception as e:
            self.logger.error("❌ 停止热端数据存储服务失败", error=str(e))
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info("📡 收到停止信号", signal=signum)
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service_status": {
                "is_running": self.is_running,
                "subscriptions_count": len(self.subscriptions),
                "nats_connected": self.nats_client is not None and not self.nats_client.is_closed
            },
            "message_stats": self.stats,
            "storage_stats": self.storage_manager.get_storage_stats() if self.storage_manager else None
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }
        
        # 检查NATS连接
        if self.nats_client and not self.nats_client.is_closed:
            health_status["components"]["nats"] = {"status": "healthy"}
        else:
            health_status["components"]["nats"] = {"status": "disconnected"}
            health_status["status"] = "unhealthy"
        
        # 检查存储管理器
        if self.storage_manager:
            storage_health = await self.storage_manager.health_check()
            health_status["components"]["storage"] = storage_health
            if storage_health["status"] != "healthy":
                health_status["status"] = "degraded"
        else:
            health_status["components"]["storage"] = {"status": "not_initialized"}
            health_status["status"] = "unhealthy"
        
        return health_status
