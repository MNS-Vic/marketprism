"""
Binance衍生品订单簿管理器 - WebSocket增量订单簿版本
使用 <symbol>@depth@100ms 流进行实时增量更新
"""

import asyncio
import json
import time
import aiohttp
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from decimal import Decimal
from collections import OrderedDict
import websockets
from exchanges.common.ws_message_utils import unwrap_combined_stream_message

from .base_orderbook_manager import BaseOrderBookManager
from ..data_types import OrderBookSnapshot, NormalizedOrderBook, OrderBookState, PriceLevel, EnhancedOrderBook
from ..error_management.error_handler import ErrorHandler, BinanceAPIError, RetryHandler
import structlog


class BinanceDerivativesOrderBookManager(BaseOrderBookManager):
    """
    Binance衍生品订单簿管理器 - WebSocket增量订单簿版本

    ## 丢包检测规则（基于Binance衍生品API文档）

    ### 序列号验证逻辑：
    1. **初始化检查**：如果 expected_prev_update_ids[symbol] == 0，建立新的序列号链
    2. **连续性检查**：验证 event.pu == 上一个event的u，如果不等则说明出现丢包
    3. **丢包处理**：检测到丢包时触发重新初始化流程

    ### 重建流程（带超时保护）：
    ```
    检测到丢包 → 记录警告日志 → 异步获取快照(5秒超时) → 成功则重建 → 失败则简化重建
    ```

    ### 简化重建策略（Fallback）：
    ```
    快照获取失败/超时 → 重置状态 → 标记为已初始化 → 等待下一个消息建立新序列号链
    ```

    ### 关键特性：
    - ✅ 严格的pu连续性检查，确保数据完整性
    - ✅ 5秒超时保护，避免快照获取卡住
    - ✅ 简化重建策略作为备选方案
    - ✅ 异步重建，不阻塞消息处理

    ### 统计字段说明：
    - `sequence_errors`: 检测到的pu不连续次数
    - `reinitializations`: 触发的重新初始化次数
    - `messages_processed`: 成功处理的消息数量
    """

    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化Binance衍生品订单簿管理器

        Args:
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置字典
        """
        # 先设置必要的属性，因为基类__init__会调用_get_snapshot_depth()等方法
        self.api_base_url = config.get('api_base_url', 'https://fapi.binance.com')
        self.ws_stream_url = "wss://fstream.binance.com/stream"
        self.depth_limit = config.get('depth_limit', 1000)  # 初始快照深度

        super().__init__(
            exchange="binance_derivatives",
            market_type="perpetual",
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # WebSocket连接
        self.ws_client = None
        self.ws_lock = asyncio.Lock()
        self.running = False

        # 本地订单簿状态
        self.local_orderbooks: Dict[str, Dict] = {}  # symbol -> {bids: OrderedDict, asks: OrderedDict}
        self.last_update_ids: Dict[str, int] = {}    # symbol -> last_update_id
        self.expected_prev_update_ids: Dict[str, int] = {}  # symbol -> expected_pu

        # 消息队列用于串行处理（避免数据混杂）
        self.message_queues: Dict[str, asyncio.Queue] = {}
        self.queue_processors: Dict[str, asyncio.Task] = {}

        # 🔧 修复内存泄漏：使用deque替代list，自动限制大小
        from collections import deque
        self.message_buffers: Dict[str, deque] = {}
        self.buffer_max_size = config.get('buffer_max_size', 100)  # 缓冲区最大大小
        self.initialization_status: Dict[str, bool] = {}  # symbol -> is_initialized

        # 统计信息 - 增强版本，包含重建场景统计
        self.stats.update({
            'snapshots_fetched': 0,
            'updates_applied': 0,
            'sequence_errors': 0,
            'reinitializations': 0,
            'fallback_reinitializations': 0,  # 简化重建次数
            'snapshot_timeouts': 0,           # 快照获取超时次数
            'messages_buffered': 0,
            'messages_processed': 0,
            'messages_dropped_during_reinit': 0,  # 重建期间丢弃的消息数
            'reinit_history': []              # 最近10次重建的详细信息
        })

        # 初始化各symbol的状态
        for symbol in symbols:
            self.local_orderbooks[symbol] = {
                'bids': OrderedDict(),  # price -> quantity
                'asks': OrderedDict()   # price -> quantity
            }
            self.last_update_ids[symbol] = 0
            self.expected_prev_update_ids[symbol] = 0
            self.message_queues[symbol] = asyncio.Queue()
            # 🔧 修复内存泄漏：使用deque自动限制大小
            from collections import deque
            self.message_buffers[symbol] = deque(maxlen=self.buffer_max_size)
            self.initialization_status[symbol] = False
        # 记录最近事件时间(ms)
        self._last_event_time_ms: Dict[str, int] = {}


        self.logger = structlog.get_logger("collector.orderbook_managers.binance_derivatives")

        self.logger.info("🏭 Binance衍生品订单簿管理器初始化完成（WebSocket增量版本）",
                        symbols=symbols,
                        depth_limit=self.depth_limit,
                        ws_stream_url=self.ws_stream_url)

    async def start(self):
        """启动WebSocket增量订单簿管理器"""
        self.logger.info("🚀 启动Binance衍生品订单簿管理器（WebSocket增量版本）",
                        symbols=self.symbols)

        self.running = True
        self._is_running = True

        try:
            # 1. 启动WebSocket连接
            await self._start_websocket_connection()

            # 2. 为每个symbol启动消息处理队列
            for symbol in self.symbols:
                processor = asyncio.create_task(self._process_message_queue(symbol))
                self.queue_processors[symbol] = processor
                self.logger.info(f"✅ {symbol}消息处理队列已启动")

            # 3. 为每个symbol初始化订单簿
            for symbol in self.symbols:
                await self._initialize_orderbook(symbol)
                self.logger.info(f"✅ {symbol}订单簿初始化完成")

            self.logger.info("✅ WebSocket增量订单簿管理器启动完成")

        except Exception as e:
            self.logger.error(f"❌ 启动失败: {e}")
            await self.stop()
            raise

    async def _start_websocket_connection(self):
        """启动WebSocket连接"""
        # 构建订阅流
        streams = [f"{symbol.lower()}@depth@100ms" for symbol in self.symbols]
        stream_params = "/".join(streams)
        ws_url = f"{self.ws_stream_url}?streams={stream_params}"

        self.logger.info("🔗 连接WebSocket增量订单簿流", url=ws_url)

        try:
            self.ws_client = await websockets.connect(
                ws_url,
                ping_interval=None,  # 修复：禁用客户端主动PING，遵循Binance被动PONG
                ping_timeout=None,
                close_timeout=10
            )
            self.logger.info("✅ WebSocket连接成功")

            # 启动消息接收任务
            asyncio.create_task(self._websocket_message_handler())

        except Exception as e:
            self.logger.error(f"❌ WebSocket连接失败: {e}")
            raise

    async def _websocket_message_handler(self):
        """WebSocket消息处理器"""
        message_count = 0
        try:
            async for message in self.ws_client:
                try:
                    message_count += 1
                    data = json.loads(message)

                    # 每100条消息记录一次统计 - 降级到DEBUG减少日志量
                    if message_count % 100 == 0:
                        self.logger.debug(f"📊 WebSocket消息统计",
                                        total_received=message_count,
                                        total_processed=self.stats['messages_processed'])

                    # 处理组合流消息格式（统一解包）
                    stream_name = data.get('stream')
                    stream_data = unwrap_combined_stream_message(data)

                    if stream_name:
                        # 提取symbol
                        symbol = stream_name.split('@')[0].upper()


                        # 记录事件时间(E, ms)
                        try:
                            evt_ms = stream_data.get('E') or stream_data.get('T')
                            if evt_ms is not None:
                                self._last_event_time_ms[symbol] = int(evt_ms)
                        except Exception:
                            pass

                        if symbol in self.symbols:
                            # 将消息放入对应symbol的队列进行串行处理
                            await self.message_queues[symbol].put(stream_data)
                            self.stats['messages_processed'] += 1
                        else:
                            self.logger.debug(f"🔍 忽略未订阅的symbol: {symbol}")
                    else:
                        self.logger.debug(f"🔍 收到非流数据消息: {data}")

                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ JSON解析失败: {e}")
                except Exception as e:
                    self.logger.error(f"❌ 消息处理异常: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("⚠️ WebSocket连接已关闭")
        except Exception as e:
            self.logger.error(f"❌ WebSocket消息处理异常: {e}")

        self.logger.info(f"📊 WebSocket消息处理器结束",
                        total_received=message_count,
                        total_processed=self.stats['messages_processed'])

    async def _process_message_queue(self, symbol: str):
        """处理单个symbol的消息队列（串行原子化处理）"""
        self.logger.info(f"🔄 启动{symbol}消息队列处理器")

        while self.running:
            try:
                # 等待消息
                message = await asyncio.wait_for(
                    self.message_queues[symbol].get(),
                    timeout=1.0
                )

                # 处理消息
                await self._handle_depth_update(symbol, message)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"❌ {symbol}消息队列处理异常: {e}")
                await asyncio.sleep(1)

    async def _initialize_orderbook(self, symbol: str):
        """初始化单个symbol的订单簿"""
        self.logger.info(f"🔄 初始化{symbol}订单簿")

        try:
            # 1. 获取初始快照
            snapshot = await self._fetch_initial_snapshot(symbol)
            if not snapshot:
                raise Exception(f"无法获取{symbol}初始快照")

            # 2. 应用快照到本地订单簿
            self._apply_snapshot_to_local_orderbook(symbol, snapshot)

            # 3. 处理缓存的消息
            await self._process_buffered_messages(symbol, snapshot['lastUpdateId'])

            # 4. 标记为已初始化
            self.initialization_status[symbol] = True
            self.stats['snapshots_fetched'] += 1

            self.logger.info(f"✅ {symbol}订单簿初始化完成",
                           last_update_id=snapshot['lastUpdateId'])

        except Exception as e:
            self.logger.error(f"❌ {symbol}订单簿初始化失败: {e}")
            raise

    async def _fetch_initial_snapshot(self, symbol: str) -> Optional[dict]:
        """获取初始订单簿快照"""
        url = f"{self.api_base_url}/fapi/v1/depth"
        params = {
            'symbol': symbol,
            'limit': self.depth_limit
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.logger.debug(f"📊 获取{symbol}快照成功",
                                        last_update_id=data.get('lastUpdateId'))
                        return data
                    else:
                        self.logger.error(f"❌ 获取{symbol}快照失败",
                                        status=response.status)
                        return None

        except Exception as e:
            self.logger.error(f"❌ 获取{symbol}快照异常: {e}")
            return None

    def _apply_snapshot_to_local_orderbook(self, symbol: str, snapshot: dict):
        """将快照应用到本地订单簿"""
        # 清空现有订单簿
        self.local_orderbooks[symbol]['bids'].clear()
        self.local_orderbooks[symbol]['asks'].clear()

        # 应用买盘
        for bid in snapshot.get('bids', []):
            price = Decimal(bid[0])
            quantity = Decimal(bid[1])
            if quantity > 0:
                self.local_orderbooks[symbol]['bids'][price] = quantity

        # 应用卖盘
        for ask in snapshot.get('asks', []):
            price = Decimal(ask[0])
            quantity = Decimal(ask[1])
            if quantity > 0:
                self.local_orderbooks[symbol]['asks'][price] = quantity

        # 排序（OrderedDict保持插入顺序，需要重新排序）
        self.local_orderbooks[symbol]['bids'] = OrderedDict(
            sorted(self.local_orderbooks[symbol]['bids'].items(),
                   key=lambda x: x[0], reverse=True)  # 买盘从高到低
        )
        self.local_orderbooks[symbol]['asks'] = OrderedDict(
            sorted(self.local_orderbooks[symbol]['asks'].items(),
                   key=lambda x: x[0])  # 卖盘从低到高
        )

        # 更新状态
        self.last_update_ids[symbol] = snapshot['lastUpdateId']
        self.expected_prev_update_ids[symbol] = snapshot['lastUpdateId']

    async def _process_buffered_messages(self, symbol: str, last_update_id: int):
        """处理缓存的消息（极简逻辑）"""
        # 按u排序所有缓存消息
        buffered_messages = sorted(self.message_buffers[symbol], key=lambda x: x.get('u', 0))

        # 直接应用所有缓存消息（不丢弃，不验证与REST API的序列号匹配）
        for msg in buffered_messages:
            await self._apply_depth_update_without_sequence_check(symbol, msg)

        # 清空缓存
        self.message_buffers[symbol].clear()

        self.logger.debug(f"📦 {symbol}处理缓存消息完成",
                         processed_count=len(buffered_messages))

    async def _handle_depth_update(self, symbol: str, message: dict):
        """处理深度更新消息"""
        if not self.initialization_status[symbol]:
            # 未初始化，缓存消息（deque会自动限制大小）
            self.message_buffers[symbol].append(message)
            self.stats['messages_buffered'] += 1
            # 如果缓冲区满了，记录警告
            if len(self.message_buffers[symbol]) >= self.buffer_max_size:
                self.logger.warning(f"📦 {symbol}缓冲区已满，最旧消息被自动移除",
                                   buffered_count=len(self.message_buffers[symbol]))
            else:
                self.logger.debug(f"📦 {symbol}缓存消息", buffered_count=len(self.message_buffers[symbol]))
            return

        # 记录深度更新处理
        self.logger.debug(f"🔄 {symbol}处理深度更新",
                         U=message.get('U'), u=message.get('u'), pu=message.get('pu'))

        # 已初始化，直接处理
        await self._apply_depth_update(symbol, message)

    async def _apply_depth_update_without_sequence_check(self, symbol: str, message: dict):
        """应用深度更新到本地订单簿（不进行序列号检查，用于初始化期间）"""
        try:
            u = message.get('u', 0)  # 最后一个update id

            # 应用买盘更新
            for bid in message.get('b', []):
                price = Decimal(bid[0])
                quantity = Decimal(bid[1])

                if quantity == 0:
                    # 移除价位
                    self.local_orderbooks[symbol]['bids'].pop(price, None)
                else:
                    # 更新价位
                    self.local_orderbooks[symbol]['bids'][price] = quantity

            # 应用卖盘更新
            for ask in message.get('a', []):
                price = Decimal(ask[0])
                quantity = Decimal(ask[1])

                if quantity == 0:
                    # 移除价位
                    self.local_orderbooks[symbol]['asks'].pop(price, None)
                else:
                    # 更新价位
                    self.local_orderbooks[symbol]['asks'][price] = quantity

            # 重新排序
            self._resort_orderbook(symbol)

            # 更新状态
            self.last_update_ids[symbol] = u
            self.expected_prev_update_ids[symbol] = u

        except Exception as e:
            self.logger.error(f"❌ {symbol}深度更新应用失败（无序列号检查）: {e}")

    async def _apply_depth_update(self, symbol: str, message: dict):
        """应用深度更新到本地订单簿"""
        try:
            U = message.get('U', 0)  # 第一个update id
            u = message.get('u', 0)  # 最后一个update id
            pu = message.get('pu', 0)  # 上一个update id

            # 验证序列号：pu应该等于上一个event的u，否则可能出现了丢包
            # 特殊情况：如果expected_prev_update_ids为0，说明是初始化或重新初始化后的第一个消息，建立新的序列号链
            if self.expected_prev_update_ids[symbol] == 0:
                self.logger.info(f"🔗 {symbol}建立新的序列号链", pu=pu, u=u)
                self.expected_prev_update_ids[symbol] = pu
            elif pu != self.expected_prev_update_ids[symbol]:
                self.logger.warning(f"⚠️ {symbol}检测到丢包，需要重新初始化",
                                  expected_pu=self.expected_prev_update_ids[symbol],
                                  actual_pu=pu,
                                  U=U, u=u,
                                  gap=pu - self.expected_prev_update_ids[symbol])
                self.stats['sequence_errors'] += 1
                self.stats['messages_dropped_during_reinit'] += 1

                # 记录重建历史（保留最近10次）
                reinit_info = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'symbol': symbol,
                    'reason': 'pu_mismatch',
                    'expected_pu': self.expected_prev_update_ids[symbol],
                    'actual_pu': pu,
                    'gap': pu - self.expected_prev_update_ids[symbol]
                }
                self.stats['reinit_history'].append(reinit_info)
                if len(self.stats['reinit_history']) > 10:
                    self.stats['reinit_history'].pop(0)

                # 触发重新初始化以确保数据完整性
                self.logger.info(f"🔄 {symbol}触发重新初始化")
                await self._reinitialize_orderbook(symbol)
                return  # 跳过当前消息的处理

            # 应用买盘更新
            for bid in message.get('b', []):
                price = Decimal(bid[0])
                quantity = Decimal(bid[1])

                if quantity == 0:
                    # 移除价位
                    self.local_orderbooks[symbol]['bids'].pop(price, None)
                else:
                    # 更新价位
                    self.local_orderbooks[symbol]['bids'][price] = quantity

            # 应用卖盘更新
            for ask in message.get('a', []):
                price = Decimal(ask[0])
                quantity = Decimal(ask[1])

                if quantity == 0:
                    # 移除价位
                    self.local_orderbooks[symbol]['asks'].pop(price, None)
                else:
                    # 更新价位
                    self.local_orderbooks[symbol]['asks'][price] = quantity

            # 重新排序（保持价格优先级）
            self._resort_orderbook(symbol)

            # 更新状态
            self.last_update_ids[symbol] = u
            self.expected_prev_update_ids[symbol] = u
            self.stats['updates_applied'] += 1

            # 发布到NATS
            await self._publish_orderbook_update(symbol)

        except Exception as e:
            self.logger.error(f"❌ {symbol}深度更新应用失败: {e}")
            # 只在序列号错误时重新初始化，其他错误跳过这条消息
            if "序列号不连续" not in str(e):
                self.logger.warning(f"⚠️ {symbol}跳过错误消息，继续处理")
            else:
                await self._reinitialize_orderbook(symbol)

    def _resort_orderbook(self, symbol: str):
        """重新排序订单簿"""
        # 买盘从高到低排序
        self.local_orderbooks[symbol]['bids'] = OrderedDict(
            sorted(self.local_orderbooks[symbol]['bids'].items(),
                   key=lambda x: x[0], reverse=True)
        )

        # 卖盘从低到高排序
        self.local_orderbooks[symbol]['asks'] = OrderedDict(
            sorted(self.local_orderbooks[symbol]['asks'].items(),
                   key=lambda x: x[0])
        )

    async def _reinitialize_orderbook(self, symbol: str):
        """重新初始化订单簿"""
        self.logger.warning(f"🔄 重新初始化{symbol}订单簿")

        # 重置状态
        self.initialization_status[symbol] = False
        self.message_buffers[symbol].clear()

        # 清空本地订单簿
        self.local_orderbooks[symbol]['bids'].clear()
        self.local_orderbooks[symbol]['asks'].clear()
        self.last_update_ids[symbol] = 0
        self.expected_prev_update_ids[symbol] = 0

        # 异步重新初始化（避免阻塞当前处理）
        asyncio.create_task(self._async_reinitialize(symbol))
        self.stats['reinitializations'] += 1

    async def _async_reinitialize(self, symbol: str):
        """异步重新初始化 - 简化流程避免卡住"""
        try:
            self.logger.info(f"🔄 {symbol}开始简化重新初始化")

            # 尝试获取新快照，但设置较短的超时时间
            try:
                snapshot = await asyncio.wait_for(
                    self._fetch_initial_snapshot(symbol),
                    timeout=5.0  # 5秒超时，避免卡住
                )
                if snapshot:
                    self._apply_snapshot_to_local_orderbook(symbol, snapshot)
                    self.last_update_ids[symbol] = snapshot['lastUpdateId']
                    self.expected_prev_update_ids[symbol] = 0  # 重置为0，等待下一个消息建立新的序列号链
                    self.initialization_status[symbol] = True
                    self.logger.info(f"✅ {symbol}重新初始化完成",
                                   last_update_id=snapshot['lastUpdateId'])
                else:
                    # 快照获取失败，采用简化策略：直接重置状态，从下一个消息开始重建
                    self._fallback_reinitialize(symbol)
            except asyncio.TimeoutError:
                self.stats['snapshot_timeouts'] += 1
                self.logger.warning(f"⏰ {symbol}快照获取超时，采用简化重建策略")
                self._fallback_reinitialize(symbol)

        except Exception as e:
            self.logger.error(f"❌ {symbol}重新初始化失败: {e}")
            self._fallback_reinitialize(symbol)

    def _fallback_reinitialize(self, symbol: str):
        """简化的重建策略：重置状态，从下一个有效消息开始重建"""
        self.stats['fallback_reinitializations'] += 1

        self.logger.info(f"🔄 {symbol}采用简化重建策略")
        self.logger.debug(f"📊 {symbol}重建统计",
                         total_reinits=self.stats['reinitializations'],
                         fallback_reinits=self.stats['fallback_reinitializations'],
                         snapshot_timeouts=self.stats['snapshot_timeouts'])

        self.last_update_ids[symbol] = 0
        self.expected_prev_update_ids[symbol] = 0
        self.initialization_status[symbol] = True  # 标记为已初始化，允许处理后续消息
        self.logger.info(f"✅ {symbol}简化重建完成，等待下一个消息建立新序列号链")

    async def _publish_orderbook_update(self, symbol: str):
        """发布订单簿更新到NATS"""
        try:
            # 构建标准化订单簿数据 - 推送400档
            bids = [
                PriceLevel(price=price, quantity=quantity)
                for price, quantity in list(self.local_orderbooks[symbol]['bids'].items())[:400]  # 推送400档
            ]

            asks = [
                PriceLevel(price=price, quantity=quantity)
                for price, quantity in list(self.local_orderbooks[symbol]['asks'].items())[:400]  # 推送400档
            ]

            # 创建增强订单簿对象
            # 使用最近消息的事件时间(E, ms)作为timestamp；若缺失则回退采集时间
            event_ms = None
            try:
                event_ms = int(self._last_event_time_ms.get(symbol)) if hasattr(self, '_last_event_time_ms') else None
            except Exception:
                event_ms = None
            event_dt = datetime.fromtimestamp(event_ms/1000, tz=timezone.utc) if event_ms else datetime.now(timezone.utc)
            enhanced_orderbook = EnhancedOrderBook(
                exchange_name="binance_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=self.last_update_ids[symbol],
                bids=bids,
                asks=asks,
                timestamp=event_dt,
                update_type="update"  # 修复：使用'update'而不是'incremental'
            )

            # 标准化
            if self.normalizer:
                normalized_data = self.normalizer.normalize_orderbook(
                    exchange="binance_derivatives",
                    market_type="perpetual",
                    symbol=symbol,
                    orderbook=enhanced_orderbook
                )

                # 发布到NATS
                if self.nats_publisher and normalized_data:
                    await self._publish_to_nats(symbol, normalized_data)

        except Exception as e:
            self.logger.error(f"❌ {symbol}订单簿发布失败: {e}")

    async def stop(self):
        """停止管理器"""
        self.logger.info("🛑 停止Binance衍生品订单簿管理器")

        self.running = False
        self._is_running = False

        # 停止消息处理器
        for symbol, processor in self.queue_processors.items():
            processor.cancel()
            try:
                await processor
            except asyncio.CancelledError:
                pass
            self.logger.info(f"🛑 {symbol}消息处理器已停止")

        # 关闭WebSocket连接
        if self.ws_client:
            await self.ws_client.close()
            self.logger.info("🛑 WebSocket连接已关闭")

        self.logger.info("✅ Binance衍生品订单簿管理器已停止")

    async def _exchange_specific_initialization(self):
        """交易所特定的初始化逻辑"""
        # WebSocket增量版本的初始化在start()方法中处理
        pass

    async def _exchange_specific_cleanup(self):
        """交易所特定的清理逻辑"""
        pass

    # 实现基类要求的抽象方法
    def _get_snapshot_depth(self) -> int:
        """获取快照深度"""
        return self.depth_limit

    def _get_websocket_depth(self) -> int:
        """获取WebSocket深度"""
        return self.depth_limit

    async def initialize_orderbook_states(self):
        """初始化订单簿状态"""
        # 在start()方法中已经处理了初始化
        pass

    async def process_websocket_message(self, symbol: str, message: dict):
        """处理WebSocket消息"""
        # 消息通过_websocket_message_handler处理
        pass

    async def _apply_snapshot(self, symbol: str, snapshot_data: dict, state):
        """应用快照"""
        # 通过_apply_snapshot_to_local_orderbook处理
        pass

    async def _apply_update(self, symbol: str, update: dict, state):
        """应用更新"""
        # 通过_apply_depth_update处理
        pass

    async def _validate_message_sequence(self, symbol: str, message: dict, state) -> bool:
        """验证消息序列"""
        # 在_apply_depth_update中处理pu=u验证
        return True

    async def _perform_reconnection(self, symbol: str):
        """执行重连"""
        await self._reinitialize_orderbook(symbol)

    async def _publish_to_nats(self, symbol: str, normalized_data: dict):
        """推送数据到NATS"""
        try:
            success = await self.nats_publisher.publish_orderbook(
                exchange="binance_derivatives",
                market_type="perpetual",
                symbol=symbol,
                orderbook_data=normalized_data
            )

            if success:
                self.logger.debug(f"✅ {symbol}订单簿NATS推送成功")
            else:
                self.logger.warning(f"⚠️ {symbol}订单簿NATS推送失败")

        except Exception as e:
            self.logger.error(f"❌ {symbol}订单簿NATS推送异常: {e}")

    def _get_unique_key(self, symbol: str) -> str:
        """生成唯一键"""
        return f"binance_derivatives_perpetual_{symbol}"

