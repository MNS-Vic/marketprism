"""
MarketPrism 数据存储服务
基于unified_storage_manager的微服务化存储服务
提供热冷数据管理、查询路由、数据生命周期管理
"""

import asyncio
import json
import signal
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from aiohttp import web
import aiohttp
import yaml
import os
import sys
from pathlib import Path
import traceback
import logging

from collections import defaultdict, deque
import time

# 🔧 新增：NATS订阅支持
import nats
from nats.js import JetStreamContext

# 确保能正确找到项目根目录并添加到sys.path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.service_framework import BaseService
from core.storage.unified_storage_manager import UnifiedStorageManager
from core.storage.types import NormalizedTrade, NormalizedTicker, NormalizedOrderBook

class DataStorageService(BaseService):
    """数据存储微服务 - 整合NATS订阅和HTTP API"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("data-storage-service", config)
        self.storage_manager: Optional[UnifiedStorageManager] = None

        # 🔧 新增：NATS订阅支持
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None
        self.subscriptions = []
        self.nats_enabled = config.get('nats', {}).get('enabled', True)

        # 统计信息
        self.nats_stats = {
            'messages_received': 0,
            'messages_stored': 0,
            'storage_errors': 0,
            'start_time': None
        }

        #     
        #   (production_cached_storage )
        self.batch_config: Dict[str, Dict[str, float]] = {
            # 
            'orderbook': {'batch_size': 1000, 'timeout': 2.0, 'max_queue': 10000},
            'trade': {'batch_size': 500, 'timeout': 1.5, 'max_queue': 5000},
            # 
            'funding_rate': {'batch_size': 10, 'timeout': 2.0, 'max_queue': 500},
            'open_interest': {'batch_size': 50, 'timeout': 10.0, 'max_queue': 500},
            # 
            'liquidation': {'batch_size': 5, 'timeout': 10.0, 'max_queue': 200},
            'volatility_index': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50},
            'lsr_top_position': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50},
            'lsr_all_account': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50},
        }
        # 
        self.data_queues: Dict[str, deque] = defaultdict(deque)
        self.last_flush_time: Dict[str, float] = defaultdict(float)
        self.flush_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._batch_task: Optional[asyncio.Task] = None


    def setup_routes(self):
        """设置API路由"""
        # 添加标准状态API路由
        self.app.router.add_get('/api/v1/storage/status', self.get_storage_status)

        self.app.router.add_post('/api/v1/storage/hot/trades', self.store_hot_trade)
        self.app.router.add_post('/api/v1/storage/hot/tickers', self.store_hot_ticker)
        self.app.router.add_post('/api/v1/storage/hot/orderbooks', self.store_hot_orderbook)
        self.app.router.add_get('/api/v1/storage/hot/trades/{exchange}/{symbol}', self.get_hot_trades)
        self.app.router.add_get('/api/v1/storage/hot/tickers/{exchange}/{symbol}', self.get_hot_ticker)
        self.app.router.add_get('/api/v1/storage/hot/orderbooks/{exchange}/{symbol}', self.get_hot_orderbook)
        self.app.router.add_post('/api/v1/storage/cold/archive', self.archive_to_cold)
        self.app.router.add_get('/api/v1/storage/cold/trades/{exchange}/{symbol}', self.get_cold_trades)
        self.app.router.add_post('/api/v1/storage/lifecycle/cleanup', self.cleanup_expired_data)
        self.app.router.add_get('/api/v1/storage/stats', self.get_storage_stats)

    async def on_startup(self):
        """服务启动初始化"""
        try:
            # 初始化存储管理器（从配置构建）
            ch_cfg = (self.config.get('storage', {}) or {}).get('clickhouse', {}) or {}
            from core.storage.unified_storage_manager import UnifiedStorageConfig, UnifiedStorageManager
            storage_cfg = UnifiedStorageConfig(
                storage_type='hot',
                clickhouse_host=ch_cfg.get('host', 'localhost'),
                clickhouse_port=int(ch_cfg.get('port', 8123)) if str(ch_cfg.get('port', '8123')).isdigit() else 8123,
                clickhouse_user=ch_cfg.get('user', 'default'),
                clickhouse_password=ch_cfg.get('password', ''),
                clickhouse_database=ch_cfg.get('database', 'marketprism_hot'),
                redis_enabled=False,
            )
            self.storage_manager = UnifiedStorageManager(config=storage_cfg)
            await self.storage_manager.initialize()
            self.logger.info("✅ UnifiedStorageManager初始化成功", db=storage_cfg.clickhouse_database, host=storage_cfg.clickhouse_host, port=storage_cfg.clickhouse_port)

            # 🔧 新增：初始化NATS订阅
            if self.nats_enabled:
                await self._initialize_nats_subscription()
            else:
                self.logger.info("📡 NATS订阅已禁用，仅提供HTTP API服务")
            # 启动批处理维护任务
            if self._batch_task is None:
                self._batch_task = asyncio.create_task(self._periodic_batch_maintenance())


        except Exception as e:

            self.logger.warning(f"⚠️ 存储管理器初始化失败，运行在降级模式: {e}")
            self.storage_manager = None


    async def on_shutdown(self):
        """服务停止清理"""
        # 🔧 新增：清理NATS订阅
        if self.subscriptions:
            for sub in self.subscriptions:
                await sub.unsubscribe()
            self.logger.info("📡 NATS订阅已清理")

        if self.nats_client:
            await self.nats_client.close()
            self.logger.info("📡 NATS连接已关闭")

        #    
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass


        if self.storage_manager and hasattr(self.storage_manager, 'close'):
            try:
                await self.storage_manager.close()
                self.logger.info("💾 存储管理器已关闭")
            except Exception as e:
                self.logger.warning(f"⚠️ 存储管理器关闭失败: {e}")
        else:
            self.logger.info("💾 存储服务已停止 (降级模式)")

    # ==================== NATS订阅方法 ====================

    async def _initialize_nats_subscription(self):
        """初始化NATS订阅"""
        try:
            nats_config = self.config.get('nats', {})
            # 环境变量覆盖优先：MARKETPRISM_NATS_URL > NATS_URL > YAML
            env_url = os.getenv('MARKETPRISM_NATS_URL') or os.getenv('NATS_URL')
            servers = [env_url] if env_url else nats_config.get('servers', ['nats://localhost:4222'])

            # 连接NATS
            self.nats_client = await nats.connect(
                servers=servers,
                name="data-storage-service",
                error_cb=self._nats_error_handler,
                closed_cb=self._nats_closed_handler,
                reconnected_cb=self._nats_reconnected_handler
            )

            # 获取JetStream上下文
            self.jetstream = self.nats_client.jetstream()
            self.logger.info("✅ NATS JetStream连接成功", servers=servers)

            # 订阅数据流
            await self._subscribe_to_data_streams()

            self.nats_stats['start_time'] = datetime.now()
            self.logger.info("✅ NATS数据流订阅完成")

        except Exception as e:
            self.logger.error("❌ NATS订阅初始化失败", error=str(e))
            self.nats_enabled = False

    def _load_subjects_from_collector_config(self) -> Tuple[List[str], Dict[str, str]]:
        """
        从 collector 的 unified_data_collection.yaml 加载 streams 映射，并生成订阅主题列表
        返回 (subjects, streams_map)
        subjects 为各模板的前缀加通配符（例如 trade.{exchange}.{market_type}.>）
        """
        try:
            project_root = Path(__file__).resolve().parents[2]
            collector_cfg = project_root / 'services' / 'data-collector' / 'config' / 'collector' / 'unified_data_collection.yaml'
            with open(collector_cfg, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}
            streams_map: Dict[str, str] = (cfg.get('nats') or {}).get('streams') or {}
            subjects: List[str] = []
            for key, template in streams_map.items():
                # 模板如: "trade.{exchange}.{market_type}.{symbol}"
                # 转换为: "trade.{exchange}.{market_type}.>" 作为订阅前缀
                base = template.rsplit('.', 1)[0]
                subjects.append(base + '.>')
            return subjects, streams_map
        except Exception:
            # 回退到内置默认
            default_subjects = [
                'orderbook.>', 'trade.>', 'funding_rate.>', 'open_interest.>',
                'liquidation.>', 'volatility_index.>', 'lsr_top_position.>', 'lsr_all_account.>'
            ]
            return default_subjects, {}


    async def _subscribe_to_data_streams(self):
        """订阅数据流
        对齐collector发布的主题模板，使用“无 -data 后缀”的新命名。
        """
        try:
            # 从 collector 配置动态生成订阅主题（与发布模板严格对齐）
            subjects, streams_map = self._load_subjects_from_collector_config()

            common_cfg = nats.js.api.ConsumerConfig(
                deliver_policy=nats.js.api.DeliverPolicy.LAST,
                ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                max_ack_pending=2000,
                ack_wait=60
            )

            for subject in subjects:
                # 针对不同主题使用不同处理器
                # 生成 durable 名称：允许通过环境变量前缀覆盖
                durable_prefix = os.getenv("STORAGE_DURABLE_PREFIX", "storage-service")

                if subject.startswith("orderbook"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_orderbook_message,
                        durable=f"{durable_prefix}-orderbook-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                elif subject.startswith("trade"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_trade_message,
                        durable=f"{durable_prefix}-trade-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                elif subject.startswith("volatility_index"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_volatility_index_message,
                        durable=f"{durable_prefix}-volatility-index-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                elif subject.startswith("funding_rate"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_funding_rate_message,
                        durable=f"{durable_prefix}-funding-rate-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                elif subject.startswith("open_interest"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_open_interest_message,
                        durable=f"{durable_prefix}-open-interest-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                elif subject.startswith("liquidation"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_liquidation_message,
                        durable=f"{durable_prefix}-liquidation-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                elif subject.startswith("lsr_top_position"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_lsr_top_position_message,
                        durable=f"{durable_prefix}-lsr-top-position-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                elif subject.startswith("lsr_all_account"):
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_lsr_all_account_message,
                        durable=f"{durable_prefix}-lsr-all-account-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                else:
                    sub = await self.jetstream.subscribe(
                        subject,
                        cb=self._handle_generic_message,
                        durable=f"{durable_prefix}-{subject.split('.')[0]}-consumer",
                        stream="MARKET_DATA",
                        config=common_cfg
                    )
                self.subscriptions.append(sub)

            self.logger.info("📡 数据流订阅成功", subscriptions=len(self.subscriptions))

        except Exception as e:
            self.logger.error("❌ 数据流订阅失败", error=str(e))

    async def _handle_orderbook_message(self, msg):
        """处理订单簿消息"""
        try:
            if not self.storage_manager:
                await msg.ack()  # 降级模式下直接确认
                return

            # 解析消息
            data = json.loads(msg.data.decode())

            # 入队等待批处理
            self._enqueue_data('orderbook', data)

            # 确认消息
            await msg.ack()

            # 更新统计（仅计入收到，真正写入在批处理后统计）
            self.nats_stats['messages_received'] += 1

            self.logger.debug("📊 订单簿数据已入队",
                            exchange=data.get('exchange'),
                            symbol=data.get('symbol'))

        except Exception as e:
            self.logger.error("❌ 订单簿消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1
            # 不确认消息，让它重新投递

    async def _handle_trade_message(self, msg):
        """处理交易消息"""
        try:
            if not self.storage_manager:
                await msg.ack()  # 降级模式下直接确认
                return

            # 解析消息
            data = json.loads(msg.data.decode())

            # 入队等待批处理
            self._enqueue_data('trade', data)

            # 确认消息
            await msg.ack()

            # 更新统计（仅计入收到）
            self.nats_stats['messages_received'] += 1

            self.logger.debug("💰 交易数据已入队",
                            exchange=data.get('exchange'),
                            symbol=data.get('symbol'),
                            price=data.get('price'))

        except Exception as e:
            self.logger.error("❌ 交易消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _handle_generic_message(self, msg):
        """处理通用消息"""
        try:
            data = json.loads(msg.data.decode())
            subject = msg.subject

            if "funding_rate" in subject:
                # TODO
                pass
            elif "open_interest" in subject:
                # TODO
                pass
            else:
                # 其他暂未分类的数据类型，先记录日志
                self.logger.debug("📥 收到通用消息", subject=subject)

            await msg.ack()
        except Exception as e:
            self.logger.error("❌ 通用消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    def _enqueue_data(self, data_type: str, data: Dict[str, Any]):
        """入队数据，等待批处理刷新"""
        self.data_queues[data_type].append(data)
        if self.last_flush_time.get(data_type, 0) == 0:
            self.last_flush_time[data_type] = time.time()

    async def _periodic_batch_maintenance(self):
        """批处理维护任务：按批大小/超时策略触发刷新"""
        try:
            while True:
                now = time.time()
                for dt, queue in list(self.data_queues.items()):
                    cfg = self.batch_config.get(dt, {'batch_size': 100, 'timeout': 5.0, 'max_queue': 1000})
                    last = self.last_flush_time.get(dt, 0)
                    should = (len(queue) >= cfg['batch_size']) or (len(queue) > 0 and now - last >= cfg['timeout']) or (len(queue) >= cfg['max_queue'])
                    if should and not self.flush_locks[dt].locked():
                        asyncio.create_task(self._flush_batch(dt))
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            for dt in list(self.data_queues.keys()):
                if self.data_queues[dt]:
                    await self._flush_batch(dt)
            raise
        except Exception as e:
            self.logger.error("批处理维护任务异常", error=str(e))

    async def _flush_batch(self, data_type: str):
        async with self.flush_locks[data_type]:
            queue = self.data_queues[data_type]
            if not queue:
                return
            cfg = self.batch_config.get(data_type, {'batch_size': 100})
            batch = []
            take = min(len(queue), int(cfg.get('batch_size', 100)))
            for _ in range(take):
                if queue:
                    batch.append(queue.popleft())
            if not batch:
                return
            if not self.storage_manager:
                self.nats_stats['messages_stored'] += len(batch)
                self.last_flush_time[data_type] = time.time()
                return
            try:
                for item in batch:
                    if data_type == 'trade':
                        await self.storage_manager.store_trade(item)
                    elif data_type == 'orderbook':
                        await self.storage_manager.store_orderbook(item)
                    elif data_type == 'volatility_index':
                        await self.storage_manager.store_volatility_index(item)
                    elif data_type == 'funding_rate':
                        await self.storage_manager.store_funding_rate(item)
                    elif data_type == 'open_interest':
                        await self.storage_manager.store_open_interest(item)
                    elif data_type == 'liquidation':
                        await self.storage_manager.store_liquidation(item)
                    elif data_type == 'lsr_top_position':
                        await self.storage_manager.store_lsr_top_position(item)
                    elif data_type == 'lsr_all_account':
                        await self.storage_manager.store_lsr_all_account(item)
                self.nats_stats['messages_stored'] += len(batch)
            except Exception as e:
                self.logger.error("批量写入失败", data_type=data_type, error=str(e))
                for item in reversed(batch):
                    queue.appendleft(item)
                self.nats_stats['storage_errors'] += 1
            finally:
                self.last_flush_time[data_type] = time.time()

            self.nats_stats['messages_received'] += 1


    async def _handle_volatility_index_message(self, msg):
        """处理波动率指数消息，写入 ClickHouse"""
        try:
            if not self.storage_manager:
                await msg.ack()
                return

            data = json.loads(msg.data.decode())

            # 统一字段映射：市场类型默认 options
            if 'market_type' not in data:
                data['market_type'] = 'options'
            if 'vol_index' not in data and 'volatility_index' in data:
                data['vol_index'] = data['volatility_index']

            # 入队，低频数据立即触发批处理也可
            self._enqueue_data('volatility_index', data)
            await msg.ack()

            self.nats_stats['messages_received'] += 1
            self.logger.debug("📈 VI 已入队", subject=msg.subject, index_value=str(data.get('vol_index')))

        except Exception as e:
            self.logger.error("❌ 波动率指数消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1


    async def _handle_funding_rate_message(self, msg):
        try:
            data = json.loads(msg.data.decode())
            # 字段兜底：统一字段名
            if 'funding_rate' not in data and 'current_funding_rate' in data:
                data['funding_rate'] = data['current_funding_rate']
            self._enqueue_data('funding_rate', data)
            await msg.ack()
            self.nats_stats['messages_received'] += 1
            self.logger.debug(" 资金费率已入队", subject=msg.subject)
        except Exception as e:
            self.logger.error("❌ 资金费率消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _handle_open_interest_message(self, msg):
        try:
            data = json.loads(msg.data.decode())
            self._enqueue_data('open_interest', data)
            await msg.ack()
            self.nats_stats['messages_received'] += 1
            self.logger.debug(" 未平仓量已入队", subject=msg.subject)
        except Exception as e:
            self.logger.error("❌ 未平仓量消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _handle_liquidation_message(self, msg):
        try:
            data = json.loads(msg.data.decode())
            self._enqueue_data('liquidation', data)
            await msg.ack()
            self.nats_stats['messages_received'] += 1
            self.logger.debug(" 强平已入队", subject=msg.subject)
        except Exception as e:
            self.logger.error("❌ 强平消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _handle_lsr_top_position_message(self, msg):
        try:
            data = json.loads(msg.data.decode())
            self._enqueue_data('lsr_top_position', data)
            await msg.ack()
            self.nats_stats['messages_received'] += 1
            self.logger.debug(" LSR顶级持仓已入队", subject=msg.subject)
        except Exception as e:
            self.logger.error("❌ LSR顶级持仓消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _handle_lsr_all_account_message(self, msg):
        try:
            data = json.loads(msg.data.decode())
            self._enqueue_data('lsr_all_account', data)
            await msg.ack()
            self.nats_stats['messages_received'] += 1
            self.logger.debug(" LSR全账户已入队", subject=msg.subject)
        except Exception as e:
            self.logger.error("❌ LSR全账户消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _nats_error_handler(self, e):
        """NATS错误处理"""
        self.logger.error("📡 NATS错误", error=str(e))

    async def _nats_closed_handler(self):
        """NATS连接关闭处理"""
        self.logger.warning("📡 NATS连接已关闭")

    async def _nats_reconnected_handler(self):
        """NATS重连处理"""
        self.logger.info("📡 NATS重连成功")

    # ==================== API Handlers ====================

    async def store_hot_trade(self, request: web.Request) -> web.Response:
        """存储热交易数据"""
        if not self.storage_manager:
            return web.json_response({"status": "degraded", "message": "Storage service running in degraded mode"}, status=503)
        try:
            data = await request.json()
            trade = NormalizedTrade(**data)
            await self.storage_manager.store_trade(trade)
            return web.json_response({"status": "success", "message": "Trade stored successfully"})
        except Exception as e:
            self.logger.error(f"Failed to store hot trade: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def store_hot_ticker(self, request: web.Request) -> web.Response:
        """存储热行情数据"""
        try:
            data = await request.json()
            ticker = NormalizedTicker(**data)
            await self.storage_manager.store_ticker(ticker)
            return web.json_response({"status": "success", "message": "Ticker stored successfully"})
        except Exception as e:
            self.logger.error(f"Failed to store hot ticker: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def store_hot_orderbook(self, request: web.Request) -> web.Response:
        """存储热订单簿数据"""
        try:
            data = await request.json()
            orderbook = NormalizedOrderBook(**data)
            await self.storage_manager.store_orderbook(orderbook)
            return web.json_response({"status": "success", "message": "Orderbook stored successfully"})
        except Exception as e:
            self.logger.error(f"Failed to store hot orderbook: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_hot_trades(self, request: web.Request) -> web.Response:
        """查询热交易数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            limit = int(request.query.get('limit', '100'))
            trades = await self.storage_manager.get_recent_trades(exchange, symbol, limit)
            return web.json_response([trade.dict() for trade in trades])
        except Exception as e:
            self.logger.error(f"Failed to query hot trades for {exchange}:{symbol}: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_hot_ticker(self, request: web.Request) -> web.Response:
        """查询热行情数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            ticker = await self.storage_manager.get_latest_ticker(exchange, symbol)
            if ticker:
                return web.json_response(ticker.dict())
            return web.json_response({"status": "not_found"}, status=404)
        except Exception as e:
            self.logger.error(f"Failed to query hot ticker for {exchange}:{symbol}: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_hot_orderbook(self, request: web.Request) -> web.Response:
        """查询热订单簿数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            orderbook = await self.storage_manager.get_latest_orderbook(exchange, symbol)
            if orderbook:
                return web.json_response(orderbook.dict())
            return web.json_response({"status": "not_found"}, status=404)
        except Exception as e:
            self.logger.error(f"Failed to query hot orderbook for {exchange}:{symbol}: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def archive_to_cold(self, request: web.Request) -> web.Response:
        """将热数据归档到冷存储"""
        try:
            # 这里的具体逻辑可以根据需求实现，例如按时间范围归档
            cutoff_days = int(request.query.get('days', '30'))
            cutoff_date = datetime.now() - timedelta(days=cutoff_days)
            summary = await self.storage_manager.archive_data(cutoff_date)
            return web.json_response({"status": "success", "summary": summary})
        except Exception as e:
            self.logger.error(f"Failed to archive data: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_cold_trades(self, request: web.Request) -> web.Response:
        # 实际的冷数据查询逻辑会更复杂，这里仅为示例
        return web.json_response({"status": "error", "message": "Not implemented"}, status=501)

    async def cleanup_expired_data(self, request: web.Request) -> web.Response:
        """清理过期数据"""
        try:
            summary = await self.storage_manager.cleanup_data()
            return web.json_response({"status": "success", "summary": summary})
        except Exception as e:
            self.logger.error(f"Failed to cleanup data: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_storage_status(self, request: web.Request) -> web.Response:
        """获取存储服务状态"""
        try:
            status_info = {
                "status": "success",
                "service": "data-storage-service",
                "timestamp": datetime.now().isoformat(),
                "storage_manager": {
                    "initialized": self.storage_manager is not None,
                    "mode": "normal" if self.storage_manager else "degraded"
                },
                # 🔧 新增：NATS订阅状态
                "nats_subscription": {
                    "enabled": self.nats_enabled,
                    "connected": self.nats_client is not None and not self.nats_client.is_closed,
                    "subscriptions": len(self.subscriptions),
                    "stats": self.nats_stats.copy()
                }
            }

            if self.storage_manager:
                try:
                    # 尝试获取基本统计信息
                    stats = await self.storage_manager.get_stats()
                    status_info["storage_stats"] = stats
                except Exception as e:
                    status_info["storage_stats"] = {"error": str(e)}

            return web.json_response(status_info)
        except Exception as e:
            self.logger.error(f"Failed to get storage status: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_storage_stats(self, request: web.Request) -> web.Response:
        """获取存储统计信息"""
        if not self.storage_manager:
            return web.json_response({
                "status": "degraded",
                "mode": "degraded",
                "message": "Storage service running in degraded mode",
                "hot_storage": {"status": "unavailable"},
                "cold_storage": {"status": "unavailable"}
            })
        try:
            stats = await self.storage_manager.get_stats()
            return web.json_response(stats)
        except Exception as e:
            self.logger.error(f"Failed to get storage stats: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)


async def main():
    """服务主入口点"""
    try:
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / 'config' / 'services.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            # 如果文件为空或无效，则视为空字典
            full_config = yaml.safe_load(f) or {}

        # 获取本服务的特定配置, 如果没有则返回空字典
        service_config = full_config.get('services', {}).get('data-storage-service', {})

        service = DataStorageService(config=service_config)
        await service.run()

    except Exception:
        # 强制将完整的堆栈跟踪打印到stderr，以便调试
        logging.basicConfig()
        logging.critical("Data Storage Service failed to start", exc_info=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())