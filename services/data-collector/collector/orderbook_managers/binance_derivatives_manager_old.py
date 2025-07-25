"""
Binance衍生品订单簿管理器
处理Binance永续合约和期货的订单簿数据，实现lastUpdateId验证和API快照初始化
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
import time
import json
from enum import Enum
from collections import deque
import websockets

from .base_orderbook_manager import BaseOrderBookManager
from ..data_types import OrderBookState, NormalizedOrderBook, OrderBookSnapshot, EnhancedOrderBook, PriceLevel, OrderBookUpdateType
from ..error_management.error_handler import ErrorHandler, BinanceAPIError, RetryHandler
import structlog


class InitializationState(Enum):
    """🚀 分阶段初始化状态机"""
    SUBSCRIBING = "subscribing"  # 第一阶段：WebSocket订阅和消息缓存
    SNAPSHOT = "snapshot"        # 第二阶段：API快照获取
    SYNCING = "syncing"         # 第三阶段：消息同步和验证
    RUNNING = "running"         # 第四阶段：正常运行模式
    FAILED = "failed"           # 初始化失败


class CachedMessage:
    """🚀 缓存的WebSocket消息"""
    def __init__(self, message: dict, receive_time: float):
        self.message = message
        self.receive_time = receive_time
        self.U = message.get('U')   # 第一个更新ID（衍生品）
        self.u = message.get('u')   # 最后一个更新ID
        self.pu = message.get('pu') # 上一个更新ID（衍生品特有）


class BinanceDerivativesOrderBookManager(BaseOrderBookManager):
    """Binance衍生品订单簿管理器"""
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        super().__init__(
            exchange="binance_derivatives",
            market_type="perpetual", 
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        self.logger = structlog.get_logger(f"collector.orderbook_managers.binance_derivatives")

        # 🎯 初始化错误处理器
        self.error_handler = ErrorHandler(self.logger)
        self.retry_handler = RetryHandler(self.error_handler)

        # Binance衍生品特定配置
        self.exchange_name = "binance_derivatives"  # 🎯 添加缺失的exchange_name属性
        self.api_base_url = config.get('api_base_url', 'https://fapi.binance.com')
        self.ws_base_url = config.get('ws_base_url', 'wss://fstream.binance.com/ws')
        self.depth_limit = config.get('depth_limit', 1000)  # Binance衍生品最大1000档
        self.lastUpdateId_validation = config.get('lastUpdateId_validation', True)
        
        # WebSocket客户端
        self.binance_ws_client = None  # WebSocket Stream客户端（用于实时数据推送）
        self.binance_ws_api_client = None  # WebSocket API客户端（用于API请求）

        # NATS推送配置
        self.enable_nats_push = config.get('enable_nats_push', True)
        
        # 统计信息
        self.stats = {
            'snapshots_received': 0,
            'snapshots_applied': 0,
            'updates_received': 0,
            'updates_applied': 0,
            'lastUpdateId_validations': 0,
            'lastUpdateId_failures': 0,
            'sequence_errors': 0,
            'sequence_warnings': 0,
            'api_calls': 0,
            'errors': 0
        }

        # 🔧 串行消息处理框架 - 解决异步竞争问题
        self.message_queues: Dict[str, asyncio.Queue] = {}
        self.processing_locks: Dict[str, asyncio.Lock] = {}
        self.processing_tasks: Dict[str, asyncio.Task] = {}
        self.message_processors_running = False

        # 🚀 分阶段初始化状态管理
        self.init_states: Dict[str, InitializationState] = {}
        self.message_cache: Dict[str, deque] = {}  # 消息缓存队列
        self.cache_start_time: Dict[str, float] = {}  # 缓存开始时间
        self.snapshot_data: Dict[str, dict] = {}  # API快照数据
        self.cache_duration = 2.0  # 缓存持续时间（秒）- 应用现货成功经验，快速触发快照

        # 🔒 并发控制：防止多个symbol同时获取快照
        self.snapshot_locks: Dict[str, asyncio.Lock] = {}
        self.snapshot_in_progress: Dict[str, bool] = {}

        # 🆔 WebSocket API配置
        self.ws_api_url = "wss://ws-fapi.binance.com/ws-fapi/v1"  # WebSocket API端点
        self.ws_api_client = None  # 持久WebSocket API连接
        self.ws_api_lock = asyncio.Lock()  # 保护WebSocket API连接的锁
        self.pending_requests: Dict[str, asyncio.Future] = {}  # 待处理的请求
        self.ws_api_connected = False  # 连接状态
        self.ws_api_last_pong = time.time()  # 最后一次pong时间

        # 💾 SYNCING状态下保存的快照信息
        self.syncing_snapshots: Dict[str, dict] = {}  # symbol -> {lastUpdateId, timestamp}

        # 🔧 新增：消息缓冲区用于处理乱序消息（保留兼容性）
        self.message_buffers: Dict[str, List[dict]] = {}
        self.buffer_max_size = config.get('buffer_max_size', 100)  # 缓冲区最大大小
        self.buffer_timeout = config.get('buffer_timeout', 5.0)    # 缓冲超时时间(秒)
        
        self.logger.info("🏭 Binance衍生品订单簿管理器初始化完成", 
                        symbols=symbols, 
                        api_base_url=self.api_base_url,
                        depth_limit=self.depth_limit,
                        lastUpdateId_validation=self.lastUpdateId_validation)
    
    def _get_snapshot_depth(self) -> int:
        """Binance衍生品快照深度：1000档"""
        return 1000

    def _get_websocket_depth(self) -> int:
        """Binance衍生品WebSocket深度：1000档"""
        return 1000

    # 🔧 串行消息处理框架 - 解决异步竞争问题
    async def _start_message_processors(self, symbols: List[str]):
        """启动串行消息处理器 - 解决异步竞争问题"""
        if self.message_processors_running:
            return

        self.message_processors_running = True

        for symbol in symbols:
            # 为每个交易对创建独立的消息队列和处理器
            # 🔧 关键修复：增大队列容量，解决消息积压导致的向后跳跃问题
            self.message_queues[symbol] = asyncio.Queue(maxsize=10000)
            self.processing_locks[symbol] = asyncio.Lock()

            # 启动串行处理任务
            task = asyncio.create_task(self._process_messages_serially(symbol))
            self.processing_tasks[symbol] = task

        self.logger.info(f"🔧 已启动{len(symbols)}个串行消息处理器")

    async def _process_messages_serially(self, symbol: str):
        """串行处理单个交易对的消息 - 确保序列号连续性"""
        queue = self.message_queues[symbol]
        lock = self.processing_locks[symbol]

        self.logger.info(f"🔧 启动{symbol}的串行消息处理器")

        try:
            message_count = 0
            while True:
                # 🔍 调试：等待消息
                self.logger.debug(f"🔍 {symbol}处理器等待消息，队列大小: {queue.qsize()}")

                # 从队列中获取消息
                message_data = await queue.get()
                message_count += 1

                # 🔍 调试：收到消息
                self.logger.debug(f"🔍 {symbol}处理器收到第{message_count}条消息")

                # 检查停止信号
                if message_data is None:
                    self.logger.info(f"🔧 {symbol}处理器收到停止信号")
                    break

                # 串行处理消息（使用锁确保原子性）
                async with lock:
                    try:
                        self.logger.debug(f"🔍 开始处理{symbol}消息: {message_data.get('timestamp', 'N/A')}")

                        # 🚀 激进优化：动态过期时间和队列深度策略
                        message_age = time.time() - message_data.get('timestamp', time.time())
                        queue_size = queue.qsize()

                        # 动态过期时间：衍生品市场更活跃，过期时间更短
                        if queue_size > 5000:  # 队列超过50%
                            max_age = 0.5  # 0.5秒（衍生品更激进）
                        elif queue_size > 2000:  # 队列超过20%
                            max_age = 1.0  # 1秒
                        else:
                            max_age = 2.0  # 2秒

                        if message_age > max_age:
                            self.logger.warning(f"⚠️ 丢弃过期消息: {symbol}, age={message_age:.2f}s, max_age={max_age:.1f}s, queue_size={queue_size}")
                            continue

                        # 🚀 激进优化：批量丢弃策略（衍生品版本）
                        if queue_size > 8000:  # 队列超过80%，批量丢弃
                            dropped_count = 0
                            while queue.qsize() > 4000 and dropped_count < 200:  # 衍生品可以丢弃更多
                                try:
                                    old_msg = queue.get_nowait()
                                    old_age = time.time() - old_msg.get('timestamp', time.time())
                                    if old_age > 0.5:  # 丢弃超过0.5秒的消息
                                        dropped_count += 1
                                        queue.task_done()
                                    else:
                                        queue.put_nowait(old_msg)
                                        break
                                except asyncio.QueueEmpty:
                                    break
                            if dropped_count > 0:
                                self.logger.warning(f"🚀 批量丢弃过期消息: {symbol}, dropped={dropped_count}, remaining_queue={queue.qsize()}")

                        # 🔧 关键修复：直接调用原子性处理，避免双重路径
                        update = message_data['update']
                        await self._process_binance_message_atomic(symbol, update)
                        self.logger.debug(f"✅ 完成处理{symbol}消息")
                    except Exception as e:
                        self.logger.error(f"❌ 处理{symbol}消息失败: {e}", exc_info=True)
                    finally:
                        queue.task_done()

        except asyncio.CancelledError:
            self.logger.info(f"🔧 {symbol}串行处理器已取消")
        except Exception as e:
            self.logger.error(f"❌ {symbol}串行处理器异常: {e}")

    async def _enqueue_message(self, symbol: str, update: dict):
        """将消息加入队列进行串行处理"""
        if symbol not in self.message_queues:
            self.logger.warning(f"⚠️ {symbol}的消息队列不存在")
            return False

        queue = self.message_queues[symbol]

        try:
            # 非阻塞方式加入队列
            message_data = {
                'timestamp': time.time(),
                'symbol': symbol,
                'update': update
            }
            queue.put_nowait(message_data)
            self.logger.debug(f"🔍 {symbol}消息已入队，队列大小: {queue.qsize()}")
            return True
        except asyncio.QueueFull:
            self.logger.warning(f"⚠️ {symbol}消息队列已满，丢弃消息")
            return False

    async def _clear_message_queue(self, symbol: str):
        """清空指定symbol的消息队列，避免初始化完成后处理旧消息"""
        if symbol not in self.message_queues:
            self.logger.warning(f"⚠️ {symbol}的消息队列不存在，无法清空")
            return

        queue = self.message_queues[symbol]
        cleared_count = 0

        try:
            # 清空队列中的所有消息
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                    cleared_count += 1
                except asyncio.QueueEmpty:
                    break

            if cleared_count > 0:
                self.logger.info(f"🧹 {symbol}清空串行队列: 移除{cleared_count}条旧消息")
            else:
                self.logger.debug(f"🧹 {symbol}串行队列已为空")

        except Exception as e:
            self.logger.error(f"❌ {symbol}清空串行队列失败: {e}")

    async def _ensure_ws_api_connection(self):
        """确保WebSocket API连接可用"""
        async with self.ws_api_lock:
            if self.ws_api_connected and self.ws_api_client:
                # 检查连接是否仍然活跃
                if time.time() - self.ws_api_last_pong > 600:  # 10分钟无pong，连接可能断开
                    self.logger.warning("⚠️ WebSocket API连接可能已断开，重新连接")
                    await self._close_ws_api_connection()
                else:
                    return True

            # 建立新连接
            try:
                self.logger.info("🔗 建立WebSocket API连接...")
                self.ws_api_client = await websockets.connect(
                    self.ws_api_url,
                    ping_interval=None,  # 禁用自动ping，使用服务器的ping
                    ping_timeout=None,
                    close_timeout=10
                )

                # 启动消息监听任务
                asyncio.create_task(self._ws_api_message_handler())

                self.ws_api_connected = True
                self.ws_api_last_pong = time.time()
                self.logger.info("✅ WebSocket API连接建立成功")
                return True

            except Exception as e:
                self.logger.error(f"❌ WebSocket API连接失败: {e}")
                self.ws_api_connected = False
                return False

    async def _close_ws_api_connection(self):
        """关闭WebSocket API连接"""
        if self.ws_api_client:
            try:
                await self.ws_api_client.close()
            except Exception as e:
                self.logger.debug(f"关闭WebSocket API连接时出错: {e}")
            finally:
                self.ws_api_client = None
                self.ws_api_connected = False

    async def _ws_api_message_handler(self):
        """WebSocket API消息处理器"""
        try:
            while self.ws_api_connected and self.ws_api_client:
                try:
                    message_str = await asyncio.wait_for(self.ws_api_client.recv(), timeout=30)

                    # 处理ping/pong
                    if isinstance(message_str, bytes):
                        # 这是ping消息，回复pong
                        await self.ws_api_client.pong(message_str)
                        self.ws_api_last_pong = time.time()
                        self.logger.debug("📡 WebSocket API pong sent")
                        continue

                    # 处理JSON响应
                    try:
                        response = json.loads(message_str)
                        request_id = response.get('id')

                        if request_id and request_id in self.pending_requests:
                            # 完成对应的请求
                            future = self.pending_requests.pop(request_id)
                            if not future.done():
                                future.set_result(response)
                        else:
                            self.logger.debug(f"收到未知请求ID的响应: {request_id}")

                    except json.JSONDecodeError as e:
                        self.logger.error(f"WebSocket API响应JSON解析失败: {e}")

                except asyncio.TimeoutError:
                    # 30秒无消息，检查连接状态
                    if time.time() - self.ws_api_last_pong > 600:
                        self.logger.warning("⚠️ WebSocket API长时间无响应，断开连接")
                        break
                except websockets.exceptions.ConnectionClosed:
                    self.logger.warning("⚠️ WebSocket API连接已关闭")
                    break
                except Exception as e:
                    self.logger.error(f"❌ WebSocket API消息处理异常: {e}")
                    break

        except Exception as e:
            self.logger.error(f"❌ WebSocket API消息处理器异常: {e}")
        finally:
            self.ws_api_connected = False
            # 取消所有待处理的请求
            for future in self.pending_requests.values():
                if not future.done():
                    future.set_exception(Exception("WebSocket API连接断开"))
            self.pending_requests.clear()

    async def _process_single_message_atomic(self, symbol: str, message_data: dict):
        """处理单条消息 - 原子性操作"""
        try:
            self.logger.debug(f"🔍 开始处理单个消息: {symbol}")
            update = message_data['update']
            self.logger.debug(f"🔍 消息内容: U={update.get('U')}, u={update.get('u')}, pu={update.get('pu')}")
            await self._process_binance_message_atomic(symbol, update)
            self.logger.debug(f"✅ 单个消息处理完成: {symbol}")
        except Exception as e:
            self.logger.error(f"❌ 处理单个消息时发生异常: {e}", symbol=symbol, exc_info=True)

    async def _process_binance_message_atomic(self, symbol: str, update: dict):
        """原子性处理Binance衍生品消息 - 使用缓冲机制处理乱序"""
        try:
            self.logger.debug(f"🔍 开始处理Binance衍生品消息: {symbol}")

            # 获取状态（原子性）
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)

            # 🔍 添加详细调试日志
            self.logger.debug(f"🔍 处理消息: symbol={symbol}, unique_key={unique_key}, state_exists={state is not None}")
            if state:
                self.logger.debug(f"🔍 状态详情: last_update_id={state.last_update_id}, is_synced={state.is_synced}")

            if not state:
                self.logger.warning(f"⚠️ {symbol}状态不存在, unique_key={unique_key}, available_keys={list(self.orderbook_states.keys())}")
                return

            # 如果还未同步，等待初始化完成
            if not state.is_synced or not state.local_orderbook:
                self.logger.debug(f"⏳ {symbol}等待初始化完成")
                return

            # 🔧 新的序列号验证和缓冲处理逻辑
            is_valid, error_msg = self._validate_message_sequence(symbol, update, state)

            if is_valid:
                # 消息序列号正确，直接处理
                await self._apply_binance_update_atomic(symbol, update, state)

                # 🔄 处理缓冲区中的连续消息
                buffered_messages = self._process_buffered_messages(symbol, state)
                for buffered_msg in buffered_messages:
                    await self._apply_binance_update_atomic(symbol, buffered_msg, state)

            else:
                # 消息序列号不连续，添加到缓冲区
                self._buffer_message(symbol, update)
                self.logger.debug(f"📦 {symbol} 消息已缓冲: {error_msg}")

                # 检查是否需要重新同步（序列号回退或缓冲区过大）
                prev_update_id = update.get('pu', 0)
                if prev_update_id < state.last_update_id:
                    # 序列号回退，触发重新同步
                    self.logger.warning(f"🔄 触发{symbol}重新同步: {error_msg}")
                    await self._trigger_resync(symbol, "序列号回退")
                elif len(self.message_buffers.get(symbol, [])) > self.buffer_max_size * 0.8:
                    # 缓冲区接近满载，可能存在严重的序列号问题
                    self.logger.warning(f"🔄 触发{symbol}重新同步: 缓冲区接近满载")
                    await self._trigger_resync(symbol, "缓冲区过载")

        except Exception as e:
            self.logger.error(f"❌ {symbol}原子性处理失败: {e}")

    async def _apply_binance_update_atomic(self, symbol: str, update: dict, state):
        """原子性应用Binance衍生品更新"""
        try:
            # 应用更新到本地订单簿
            await self._apply_update(symbol, update, state)

            # 检查更新是否成功
            if state.local_orderbook:
                self.logger.info(f"✅ Binance衍生品更新应用成功: {symbol}")

                # 更新统计
                self.stats['updates_applied'] += 1

                # 推送到NATS
                if self.enable_nats_push and self.nats_publisher:
                    try:
                        self.logger.info(f"🔍 准备推送{symbol}到NATS")
                        await self.nats_publisher.publish_enhanced_orderbook(state.local_orderbook)
                        self.logger.info(f"✅ NATS推送成功: {symbol}")
                    except Exception as e:
                        self.logger.error(f"❌ NATS推送失败: {e}")
            else:
                self.logger.warning(f"⚠️ {symbol}更新应用失败")

        except Exception as e:
            self.logger.error(f"❌ 应用Binance衍生品更新失败: {symbol}, error={e}", exc_info=True)

    async def initialize_orderbook_states(self):
        """🚀 分阶段初始化：初始化订单簿状态（衍生品版本）"""
        self.logger.info("🚀 开始Binance衍生品分阶段初始化")

        for symbol in self.symbols:
            # 初始化状态为第一阶段：订阅和缓存
            self.init_states[symbol] = InitializationState.SUBSCRIBING

            unique_key = self._get_unique_key(symbol)
            self.orderbook_states[unique_key] = OrderBookState(
                symbol=symbol,
                exchange="binance_derivatives"
            )

            self.logger.info(f"🚀 {symbol}衍生品初始化为SUBSCRIBING状态，开始消息缓存阶段")
            self.logger.debug(f"🔍 DEBUG unique_key详情: exchange={getattr(self, 'exchange', 'N/A')}, market_type={getattr(self, 'market_type', 'N/A')}, symbol={symbol}")

    async def process_websocket_message(self, symbol: str, message: dict):
        """🚨 已弃用：避免并发处理，统一使用串行队列处理"""
        self.logger.warning(f"⚠️ 调用了已弃用的process_websocket_message方法: {symbol}")
        self.logger.warning("🔧 请使用_handle_websocket_update方法进行串行处理")

        # 🔧 重定向到串行处理队列
        try:
            success = await self._enqueue_message(symbol, message)
            if not success:
                self.logger.error(f"❌ {symbol}消息重定向到串行队列失败")
        except Exception as e:
            self.logger.error(f"❌ {symbol}消息重定向失败: {e}")

    def _validate_message_sequence(self, symbol: str, message: dict, state: OrderBookState) -> tuple[bool, str]:
        """
        🔧 统一：验证Binance衍生品消息序列 - 借鉴OKX成功模式
        使用原始数据进行验证，与OKX保持一致的验证流程
        """
        try:
            if not self.lastUpdateId_validation:
                return True, ""

            first_update_id = message.get('U')  # firstUpdateId
            final_update_id = message.get('u')   # finalUpdateId
            prev_update_id = message.get('pu')   # prevUpdateId (衍生品专用)

            if first_update_id is None or final_update_id is None:
                return False, "缺少必要的序列号字段 U 或 u"

            # 🔧 关键修复：Binance衍生品使用pu字段验证连续性
            if prev_update_id is None:
                return False, "Binance衍生品缺少pu字段"

            # 如果是第一次更新（刚完成初始化）
            if state.last_update_id == 0:
                state.last_update_id = final_update_id
                self.logger.info(f"✅ Binance衍生品首次序列号设置成功: {symbol}, pu={prev_update_id}, u={final_update_id}")
                return True, "首次更新"

            # 🎯 Binance衍生品核心验证：pu必须等于上一个event的u (官方文档规则)
            if prev_update_id == state.last_update_id:
                # 序列号连续，更新状态
                old_update_id = state.last_update_id
                state.last_update_id = final_update_id
                self.logger.debug(f"✅ Binance衍生品序列号验证成功: {symbol}, 从{old_update_id}更新到{final_update_id}")
                return True, "衍生品序列号连续"
            else:
                # 🔍 智能判断：检查event.U与last_update_id的关系
                if first_update_id > state.last_update_id:
                    gap = first_update_id - state.last_update_id
                    if gap == 1:
                        # 预期情况：下一个连续的event
                        old_update_id = state.last_update_id
                        state.last_update_id = final_update_id
                        self.logger.debug(f"✅ {symbol}连续event: gap=1, 从{old_update_id}更新到{final_update_id}")
                        return True, "连续event"
                    else:
                        # 有问题：跳跃超过1，说明丢失了中间的event
                        error_msg = f"检测到event跳跃: last_update_id={state.last_update_id}, event.U={first_update_id}, gap={gap}"
                        self.logger.warning(f"🚨 {symbol}event跳跃，触发重新初始化: {error_msg}")
                        return False, error_msg
                else:
                    # pu不等于last_update_id，且U不大于last_update_id，这是真正的序列问题
                    error_msg = f"序列异常: 期望pu={state.last_update_id}, 实际pu={prev_update_id}, U={first_update_id}, u={final_update_id}"
                    self.logger.warning(f"🚨 {symbol}序列异常，触发重新初始化: {error_msg}")
                    return False, error_msg

        except Exception as e:
            error_msg = f"序列验证异常: {e}"
            self.logger.error(f"❌ Binance衍生品序列号验证异常: {symbol}, {error_msg}")
            return False, error_msg

    def _buffer_message(self, symbol: str, message: dict) -> None:
        """将消息添加到缓冲区"""
        if symbol not in self.message_buffers:
            self.message_buffers[symbol] = []

        buffer = self.message_buffers[symbol]
        buffer.append({
            'message': message,
            'timestamp': time.time()
        })

        # 按pu字段排序（Binance衍生品）
        buffer.sort(key=lambda x: x['message'].get('pu', 0))

        # 限制缓冲区大小
        if len(buffer) > self.buffer_max_size:
            buffer.pop(0)  # 移除最旧的消息
            self.logger.warning(f"📦 {symbol} 缓冲区已满，移除最旧消息")

    def _process_buffered_messages(self, symbol: str, state: OrderBookState) -> List[dict]:
        """处理缓冲区中的连续消息"""
        if symbol not in self.message_buffers:
            return []

        buffer = self.message_buffers[symbol]
        processed_messages = []
        current_time = time.time()

        # 移除过期消息
        buffer[:] = [item for item in buffer
                    if current_time - item['timestamp'] < self.buffer_timeout]

        # 查找连续的消息
        while buffer:
            item = buffer[0]
            message = item['message']
            prev_update_id = message.get('pu')

            # 检查是否是期望的下一个消息
            if prev_update_id == state.last_update_id:
                processed_messages.append(message)
                state.last_update_id = message.get('u')
                buffer.pop(0)
                self.logger.debug(f"🔄 {symbol} 从缓冲区处理消息: pu={prev_update_id}, u={message.get('u')}")
            else:
                break  # 不连续，停止处理

        return processed_messages

    async def _apply_snapshot(self, symbol: str, snapshot_data: dict, state: OrderBookState):
        """应用Binance快照数据 - 统一使用EnhancedOrderBook格式"""
        try:
            self.logger.info(f"📊 应用Binance衍生品快照: {symbol}")

            # 解析快照数据
            bids_data = snapshot_data.get('bids', [])
            asks_data = snapshot_data.get('asks', [])
            last_update_id = snapshot_data.get('lastUpdateId', 0)

            # 构建价位列表 - 与OKX管理器保持一致
            bids = []
            for bid_data in bids_data:
                price = Decimal(str(bid_data[0]))
                quantity = Decimal(str(bid_data[1]))
                if quantity > 0:
                    bids.append(PriceLevel(price=price, quantity=quantity))

            asks = []
            for ask_data in asks_data:
                price = Decimal(str(ask_data[0]))
                quantity = Decimal(str(ask_data[1]))
                if quantity > 0:
                    asks.append(PriceLevel(price=price, quantity=quantity))

            # 排序
            bids.sort(key=lambda x: x.price, reverse=True)  # 买盘从高到低
            asks.sort(key=lambda x: x.price)  # 卖盘从低到高

            # 创建快照 - 使用统一的EnhancedOrderBook格式
            snapshot = EnhancedOrderBook(
                exchange_name="binance_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=last_update_id,
                bids=bids,
                asks=asks,
                timestamp=datetime.now(),
                update_type=OrderBookUpdateType.SNAPSHOT,
                first_update_id=last_update_id,
                prev_update_id=last_update_id,
                depth_levels=len(bids) + len(asks)
            )

            # 更新状态
            state.local_orderbook = snapshot
            state.last_update_id = last_update_id
            state.last_snapshot_time = datetime.now()
            state.is_synced = True

            self.logger.info(f"✅ Binance衍生品快照应用成功: {symbol}, bids={len(bids)}, asks={len(asks)}, lastUpdateId={last_update_id}")

            # 发布到NATS
            await self.publish_orderbook(symbol, snapshot)

        except Exception as e:
            self.logger.error(f"❌ 应用Binance衍生品快照失败: {symbol}, error={e}")
            state.is_synced = False
            raise

    async def start_management(self):
        """启动Binance衍生品订单簿管理"""
        try:
            self.logger.info("🚀 启动Binance衍生品订单簿管理")
            
            # 初始化状态
            await self.initialize_orderbook_states()
            
            # 启动WebSocket连接
            await self._start_websocket_client()
            
            # 等待WebSocket连接稳定
            await asyncio.sleep(2)
            
            # 为每个交易对初始化订单簿
            for symbol in self.symbols:
                await self._initialize_symbol_orderbook(symbol)
            
            self.logger.info("✅ Binance衍生品订单簿管理启动完成")
            
        except Exception as e:
            self.logger.error("❌ 启动Binance衍生品订单簿管理失败", error=str(e), exc_info=True)
            raise
    
    async def _start_websocket_client(self):
        """启动WebSocket客户端"""
        try:
            # 动态导入BinanceWebSocketClient
            import sys
            from pathlib import Path
            exchanges_dir = Path(__file__).parent.parent.parent / "exchanges"
            sys.path.insert(0, str(exchanges_dir))

            from binance_websocket import BinanceWebSocketClient

            # 启动WebSocket Stream客户端（用于实时数据推送）
            self.binance_ws_client = BinanceWebSocketClient(
                symbols=self.symbols,
                on_orderbook_update=self._handle_websocket_update,
                ws_base_url=self.ws_base_url,
                market_type="perpetual"
            )

            # 启动WebSocket Stream客户端（非阻塞）
            self.logger.info("🚀 启动Binance衍生品WebSocket Stream客户端")
            asyncio.create_task(self.binance_ws_client.start())

            # WebSocket API现在使用按需连接，不需要预先建立连接
            self.logger.info("✅ WebSocket API配置完成，将按需创建连接")

        except Exception as e:
            self.logger.error("❌ 启动WebSocket客户端失败", error=str(e), exc_info=True)
            raise

    # WebSocket API启动方法已移除，现在使用按需连接模式

    # 监听方法已移除，现在使用直接请求-响应模式

    # 发送方法已移除，现在直接在_fetch_websocket_api_snapshot中处理
    
    async def _initialize_symbol_orderbook(self, symbol: str):
        """
        初始化单个交易对的订单簿 - 严格按照Binance衍生品官方文档实现

        正确的Binance衍生品订单簿维护流程：
        1. 订阅增量数据，记录第一个event的U（最小），缓存各event
        2. 获取快照（带lastUpdateId）
        3. 使用lastUpdateId与各event的U、u对比：
           - lastUpdateId < 第一个U → 快照太老，重新获取
           - lastUpdateId > 某event的u → event太老，丢弃
           - lastUpdateId > 最后event的u → 等待更多event
           - 找到 U < lastUpdateId < u → 匹配成功！
        4. 使用匹配的event更新快照，设置本地lastUpdateId = u
        5. 持续维护：验证连续性 下一个event的pu == 上一个event的u
        """
        try:
            self.logger.info(f"📸 按币安衍生品官方文档初始化{symbol}订单簿")

            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states[unique_key]

            # 步骤1: 检查缓存的event，记录第一个event的U
            if symbol not in self.message_buffers or not self.message_buffers[symbol]:
                self.logger.warning(f"⚠️ {symbol}没有缓存的event，等待WebSocket数据")
                return False

            # 按U排序缓存的消息
            self.message_buffers[symbol].sort(key=lambda x: x['message'].get('U', 0))
            first_event_u = self.message_buffers[symbol][0]['message'].get('U')
            last_event_u = self.message_buffers[symbol][-1]['message'].get('u')

            self.logger.info(f"🔍 {symbol}缓存event范围: 第一个U={first_event_u}, 最后一个u={last_event_u}, 总数={len(self.message_buffers[symbol])}")

            # 步骤2: 获取或使用保存的快照
            if symbol in self.syncing_snapshots:
                # 使用保存的快照信息
                saved_snapshot_info = self.syncing_snapshots[symbol]
                snapshot = saved_snapshot_info['snapshot']
                last_update_id = saved_snapshot_info['lastUpdateId']
                self.logger.info(f"📋 使用保存的{symbol}快照: lastUpdateId={last_update_id}")
            else:
                # 获取新快照
                self.logger.info(f"🔄 开始通过WebSocket API获取{symbol}快照")
                snapshot = await self._fetch_websocket_api_snapshot(symbol)
                if not snapshot:
                    self.logger.error(f"❌ 获取{symbol}快照失败")
                    return False

                last_update_id = snapshot.last_update_id
                self.logger.info(f"✅ {symbol}获取快照成功: lastUpdateId={last_update_id}")

            # 步骤3: 验证快照与event的关系
            if last_update_id < first_event_u:
                self.logger.warning(f"⚠️ {symbol}快照太老: lastUpdateId={last_update_id} < 第一个U={first_event_u}，需要重新获取快照")
                return False

            if last_update_id > last_event_u:
                self.logger.info(f"💡 {symbol}快照较新，需要等待Stream追上: lastUpdateId={last_update_id} > 最后u={last_event_u}")
                self.logger.info(f"   - 差距: {last_update_id - last_event_u} 个更新ID")
                self.logger.info(f"   - 保存快照信息，等待Stream数据追上...")

                # 保存快照信息，供后续检查使用
                self.syncing_snapshots[symbol] = {
                    'lastUpdateId': last_update_id,
                    'timestamp': time.time(),
                    'snapshot': snapshot
                }

                # 返回特殊值表示需要等待，而不是失败
                return "waiting"

            # 步骤4: 寻找匹配的event（U < lastUpdateId < u）
            matching_event = None
            matching_index = -1

            for i, buffered_msg in enumerate(self.message_buffers[symbol]):
                event = buffered_msg['message']
                event_u = event.get('U')
                event_u_final = event.get('u')

                if event_u < last_update_id < event_u_final:
                    matching_event = event
                    matching_index = i
                    self.logger.info(f"🎯 {symbol}找到匹配event: U={event_u} < lastUpdateId={last_update_id} < u={event_u_final}")
                    break

            if not matching_event:
                self.logger.error(f"❌ {symbol}没有找到匹配的event，初始化失败")
                return False

            # 步骤5: 应用快照 - 使用统一的EnhancedOrderBook格式
            bids = [PriceLevel(price=price, quantity=quantity) for price, quantity in snapshot.bids]
            asks = [PriceLevel(price=price, quantity=quantity) for price, quantity in snapshot.asks]

            bids.sort(key=lambda x: x.price, reverse=True)
            asks.sort(key=lambda x: x.price)

            enhanced_orderbook = EnhancedOrderBook(
                exchange_name="binance_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=last_update_id,
                bids=bids,
                asks=asks,
                timestamp=int(time.time() * 1000),
                update_type=OrderBookUpdateType.SNAPSHOT,
                first_update_id=last_update_id,
                prev_update_id=last_update_id,
                depth_levels=len(bids) + len(asks)
            )

            # 步骤6: 使用匹配event的信息更新快照，设置正确的lastUpdateId
            await self._apply_binance_update_atomic(symbol, matching_event, state)

            # 关键：设置本地lastUpdateId为匹配event的u
            final_update_id = matching_event.get('u')
            state.local_orderbook = enhanced_orderbook
            state.last_update_id = final_update_id  # 使用event的u，不是快照的lastUpdateId！
            state.is_synced = True
            state.last_update_time = datetime.now(timezone.utc)

            self.logger.info(f"✅ {symbol}订单簿初始化成功，本地lastUpdateId={final_update_id}")

            # 🎯 关键修复：清空串行队列中的旧消息，避免序列号跳跃
            await self._clear_message_queue(symbol)

            # 设置为RUNNING状态
            self.init_states[symbol] = InitializationState.RUNNING
            self.logger.info(f"🚀 {symbol}进入正常运行模式")

            # 推送初始快照到NATS
            await self.publish_orderbook(symbol, enhanced_orderbook)

            # 步骤7: 处理匹配event之后的缓存消息
            remaining_events = self.message_buffers[symbol][matching_index + 1:]
            if remaining_events:
                self.logger.info(f"📦 {symbol}准备处理{len(remaining_events)}条后续缓存消息")

                for buffered_msg in remaining_events:
                    try:
                        event = buffered_msg['message']
                        # 验证连续性：event的pu应该等于当前的last_update_id
                        event_pu = event.get('pu')
                        if event_pu == state.last_update_id:
                            await self._apply_binance_update_atomic(symbol, event, state)
                            state.last_update_id = event.get('u')
                            self.logger.debug(f"✅ {symbol}处理缓存event成功: pu={event_pu}, u={event.get('u')}")
                        else:
                            self.logger.warning(f"⚠️ {symbol}缓存event连续性验证失败: pu={event_pu} != last_update_id={state.last_update_id}")
                            break
                    except Exception as e:
                        self.logger.error(f"❌ 处理缓存消息失败: {e}")
                        break

            # 清空缓存和保存的快照信息
            self.message_buffers[symbol].clear()
            if symbol in self.syncing_snapshots:
                del self.syncing_snapshots[symbol]

            self.logger.info(f"✅ {symbol}初始化完成，最终lastUpdateId={state.last_update_id}")

            return True
            
        except Exception as e:
            self.logger.error(f"❌ 初始化{symbol}订单簿失败", error=str(e), exc_info=True)
            return False
    
    async def _fetch_websocket_api_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """通过持久WebSocket API连接获取Binance衍生品快照"""
        try:
            # 确保WebSocket API连接可用
            if not await self._ensure_ws_api_connection():
                self.logger.error(f"❌ WebSocket API连接不可用: {symbol}")
                return None

            # 直接使用unique_key作为request ID，支持多品种识别
            unique_key = self._get_unique_key(symbol)

            # 使用unique_key作为request_id，确保每个品种有唯一标识
            # 如果unique_key太长，进行智能缩短但保持唯一性
            if len(unique_key) <= 36:
                request_id = unique_key
            else:
                # 智能缩短：保留exchange+symbol的核心信息
                # binance_derivatives_perpetual_BTCUSDT -> bd_perp_BTCUSDT
                request_id = unique_key.replace('binance_derivatives_perpetual_', 'bd_perp_')
                if len(request_id) > 36:
                    # 进一步缩短：bd_perp_BTCUSDT -> bd_BTCUSDT
                    request_id = unique_key.replace('binance_derivatives_perpetual_', 'bd_')
                    if len(request_id) > 36:
                        # 最后手段：只保留核心标识
                        request_id = f"bd_{symbol}"[:36]

            # 调整limit参数 - Binance衍生品API只支持: 5, 10, 20, 50, 100, 500, 1000
            limit = self.depth_limit
            if limit not in [5, 10, 20, 50, 100, 500, 1000]:
                valid_limits = [5, 10, 20, 50, 100, 500, 1000]
                limit = min(valid_limits, key=lambda x: abs(x - limit))
                self.logger.info(f"调整{symbol}深度限制: {self.depth_limit} -> {limit}")

            # 记录完整的unique_key用于日志追踪
            self.logger.info(f"📡 通过持久WebSocket API获取{symbol}快照: request_id={request_id}, unique_key={unique_key}, limit={limit}")

            # 构建WebSocket API请求
            depth_request = {
                "id": request_id,
                "method": "depth",
                "params": {
                    "symbol": symbol,
                    "limit": limit
                }
            }

            # 创建Future等待响应
            future = asyncio.Future()
            self.pending_requests[request_id] = future

            try:
                # 发送请求
                request_json = json.dumps(depth_request)
                await self.ws_api_client.send(request_json)
                self.stats['api_calls'] += 1

                self.logger.debug(f"📤 发送WebSocket API请求: {request_id}")

                # 等待响应（10秒超时）
                response_data = await asyncio.wait_for(future, timeout=10.0)

                # 从响应中提取数据来源标识
                response_id = response_data.get('id', '')
                self.logger.debug(f"📥 收到WebSocket API响应: response_id={response_id}")

                # 解析响应数据
                if response_data.get('status') == 200:
                    result = response_data.get('result', {})

                    # 解析数据
                    bids = [(Decimal(price), Decimal(qty)) for price, qty in result.get('bids', [])]
                    asks = [(Decimal(price), Decimal(qty)) for price, qty in result.get('asks', [])]

                    # 从response_id中解析数据来源信息
                    exchange_info = self._parse_unique_key_from_response_id(response_id)

                    snapshot = OrderBookSnapshot(
                        symbol=symbol,
                        exchange=exchange_info.get('exchange', 'binance_derivatives'),
                        bids=bids,
                        asks=asks,
                        last_update_id=result.get('lastUpdateId'),
                        timestamp=datetime.now(timezone.utc)
                    )

                    # 添加unique_key信息到快照对象（如果支持的话）
                    if hasattr(snapshot, 'unique_key'):
                        snapshot.unique_key = response_id

                    # 记录完整的数据来源信息
                    self.logger.info(f"✅ 持久WebSocket API获取{symbol}快照成功, unique_key={response_id}, lastUpdateId={snapshot.last_update_id}")

                    self.stats['snapshots_received'] += 1
                    return snapshot
                else:
                    self.logger.error(f"❌ WebSocket API请求失败: {symbol}, status={response_data.get('status')}, error={response_data.get('error')}")
                    return None

            except asyncio.TimeoutError:
                self.logger.error(f"❌ WebSocket API请求超时: {symbol}")
                return None
            except Exception as e:
                self.logger.error(f"❌ WebSocket API请求异常: {symbol}, error={e}")
                return None
            finally:
                # 清理待处理的请求
                self.pending_requests.pop(request_id, None)

        except Exception as e:
            self.logger.error(f"❌ WebSocket API获取{symbol}快照失败: {e}")
            return None

    async def _exchange_specific_cleanup(self):
        """Binance衍生品特定的清理操作"""
        # 关闭持久WebSocket API连接
        await self._close_ws_api_connection()
        self.logger.info("🧹 WebSocket API连接已清理")

    async def _handle_websocket_update(self, symbol: str, update: dict):
        """🚀 分阶段初始化：处理WebSocket更新（衍生品版本）"""
        try:
            # 检查是否是WebSocket API响应
            if symbol == '__websocket_api_response__':
                await self._handle_websocket_api_response(update)
                return

            receive_time = time.time()
            current_state = self.init_states.get(symbol, InitializationState.SUBSCRIBING)

            self.logger.debug(f"🔍 衍生品WebSocket回调: {symbol}, U={update.get('U')}, u={update.get('u')}, pu={update.get('pu')}, state={current_state.value}")

            if current_state == InitializationState.SUBSCRIBING:
                # 第一阶段：缓存消息
                await self._cache_message(symbol, update, receive_time)
            elif current_state == InitializationState.RUNNING:
                # 第四阶段：正常处理
                success = await self._enqueue_message(symbol, update)
                if not success:
                    self.logger.warning(f"⚠️ {symbol}消息入队失败")
                else:
                    self.stats['updates_received'] += 1
            elif current_state == InitializationState.SYNCING:
                # 第三阶段：只缓存消息，等待Stream追上快照
                await self._cache_message(symbol, update, receive_time)
                # 检查是否需要重新尝试初始化（但不要每个消息都触发）
                await self._check_syncing_progress(symbol)
            else:
                # 第二阶段：继续缓存消息
                await self._cache_message(symbol, update, receive_time)

        except Exception as e:
            self.logger.error(f"❌ 处理{symbol}WebSocket更新失败", error=str(e), exc_info=True)
            self.stats['errors'] += 1

    # 响应处理方法已移除，现在使用直接请求-响应模式

    async def _check_syncing_progress(self, symbol: str):
        """检查SYNCING状态的进度，智能决定是否重新尝试初始化"""
        try:
            # 获取当前状态
            if symbol not in self.syncing_snapshots:
                # 没有保存的快照，需要重新获取
                self.logger.debug(f"🔄 {symbol}没有保存的快照，重新尝试初始化")
                await self._trigger_snapshot_phase(symbol)
                return

            # 获取保存的快照信息
            saved_snapshot = self.syncing_snapshots[symbol]
            target_last_update_id = saved_snapshot['lastUpdateId']
            snapshot_time = saved_snapshot['timestamp']

            # 检查快照是否太老（超过30秒）
            current_time = time.time()
            if current_time - snapshot_time > 30:
                self.logger.info(f"⏰ {symbol}快照已过期({current_time - snapshot_time:.1f}秒)，重新获取")
                await self._trigger_snapshot_phase(symbol)
                return

            # 检查缓存消息是否已经追上快照
            if symbol in self.message_buffers and self.message_buffers[symbol]:
                # 按U排序缓存的消息
                self.message_buffers[symbol].sort(key=lambda x: x['message'].get('U', 0))
                last_event_u = self.message_buffers[symbol][-1]['message'].get('u')

                if last_event_u >= target_last_update_id:
                    # Stream已经追上快照，可以尝试初始化
                    self.logger.info(f"🎯 {symbol}Stream已追上快照: last_u={last_event_u} >= target={target_last_update_id}")
                    await self._initialize_symbol_orderbook(symbol)
                else:
                    # 还没追上，继续等待（每10个消息记录一次进度）
                    message_count = len(self.message_buffers[symbol])
                    if message_count % 50 == 0:  # 每50个消息记录一次进度
                        gap = target_last_update_id - last_event_u
                        self.logger.info(f"⏳ {symbol}等待Stream追上快照: gap={gap}, 缓存消息={message_count}")

        except Exception as e:
            self.logger.error(f"❌ {symbol}检查SYNCING进度失败: {e}")

    def _parse_unique_key_from_response_id(self, response_id: str) -> dict:
        """从response ID中解析数据来源信息"""
        try:
            # response_id就是我们的unique_key或其简化版本
            if response_id.startswith('binance_derivatives_perpetual_'):
                # 完整的unique_key
                parts = response_id.split('_')
                return {
                    'exchange': 'binance_derivatives',
                    'market_type': 'perpetual',
                    'symbol': parts[-1] if len(parts) > 3 else 'unknown'
                }
            elif response_id.startswith('bd_deriv_perp_'):
                # 简化版本1
                symbol = response_id.replace('bd_deriv_perp_', '')
                return {
                    'exchange': 'binance_derivatives',
                    'market_type': 'perpetual',
                    'symbol': symbol
                }
            elif response_id.startswith('bd_dp_'):
                # 简化版本2
                symbol = response_id.replace('bd_dp_', '')
                return {
                    'exchange': 'binance_derivatives',
                    'market_type': 'perpetual',
                    'symbol': symbol
                }
            elif response_id.startswith('bd_'):
                # 最简版本
                symbol = response_id.replace('bd_', '')
                return {
                    'exchange': 'binance_derivatives',
                    'market_type': 'perpetual',
                    'symbol': symbol
                }
            else:
                # 未知格式，使用默认值
                return {
                    'exchange': 'binance_derivatives',
                    'market_type': 'perpetual',
                    'symbol': 'unknown'
                }
        except Exception as e:
            self.logger.warning(f"⚠️ 解析response_id失败: {response_id}, error: {e}")
            return {
                'exchange': 'binance_derivatives',
                'market_type': 'perpetual',
                'symbol': 'unknown'
            }

    # REST API降级方法已移除
    # 系统要求使用WebSocket API以确保数据来源标识正确
    # REST API无法提供unique_key标识，会导致数据混乱

    async def _cache_message(self, symbol: str, update: dict, receive_time: float):
        """🚀 第一阶段：缓存WebSocket消息（衍生品版本）"""
        try:
            if symbol not in self.message_cache:
                self.message_cache[symbol] = deque()
                self.cache_start_time[symbol] = receive_time
                self.logger.info(f"🚀 开始缓存{symbol}衍生品消息")

            # 创建缓存消息对象
            cached_msg = CachedMessage(update, receive_time)
            self.message_cache[symbol].append(cached_msg)

            # 限制缓存大小，避免内存溢出
            max_cache_size = 10000
            if len(self.message_cache[symbol]) > max_cache_size:
                self.message_cache[symbol].popleft()
                self.logger.warning(f"⚠️ {symbol}衍生品消息缓存达到上限，丢弃最旧消息")

            self.logger.debug(f"🔍 缓存衍生品消息: {symbol}, U={update.get('U')}, u={update.get('u')}, pu={update.get('pu')}, cache_size={len(self.message_cache[symbol])}")

            # 🎯 修复：只有在SUBSCRIBING状态时才检查缓存时间，避免重复触发快照
            current_state = self.init_states.get(symbol, InitializationState.SUBSCRIBING)
            if (current_state == InitializationState.SUBSCRIBING and
                receive_time - self.cache_start_time[symbol] >= self.cache_duration):
                await self._trigger_snapshot_phase(symbol)

        except Exception as e:
            self.logger.error(f"❌ 缓存{symbol}衍生品消息失败: {e}", exc_info=True)

    async def _trigger_snapshot_phase(self, symbol: str):
        """🚀 第二阶段：使用新的一体化初始化逻辑"""
        try:
            self.logger.info(f"🚀 {symbol}衍生品开始一体化初始化，缓存消息数量: {len(self.message_cache[symbol])}")

            # 将缓存消息转移到新的格式
            if symbol not in self.message_buffers:
                self.message_buffers[symbol] = []

            # 转换消息格式：从CachedMessage到dict
            for cached_msg in self.message_cache[symbol]:
                # CachedMessage.message已经是完整的字典，直接使用
                self.message_buffers[symbol].append({'message': cached_msg.message})

            # 调用新的一体化初始化方法
            result = await self._initialize_symbol_orderbook(symbol)

            if result == "waiting":
                # 需要等待更多WebSocket消息，保持SYNCING状态
                self.init_states[symbol] = InitializationState.SYNCING
                self.logger.info(f"💡 {symbol}保持SYNCING状态，等待Stream数据追上快照")
                # 不重置，保持当前状态和缓存
            elif result == True:
                # 初始化成功
                self.logger.info(f"✅ {symbol}一体化初始化成功")
            else:
                # 初始化失败，重新开始
                self.logger.error(f"❌ {symbol}衍生品一体化初始化失败，重新开始")
                await self._reset_initialization(symbol)

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品一体化初始化失败: {e}", exc_info=True)
            await self._reset_initialization(symbol)

    async def _get_derivatives_api_snapshot(self, symbol: str) -> bool:
        """🚀 [已废弃] 旧的REST API快照获取方法 - 已被WebSocket API替代"""
        self.logger.warning(f"⚠️ 调用了已废弃的REST API快照方法: {symbol}")
        self.logger.warning("💡 请使用 _fetch_websocket_api_snapshot 方法")
        return False

    async def _trigger_sync_phase(self, symbol: str):
        """🚀 第三阶段：消息同步和验证（衍生品版本）"""
        try:
            self.init_states[symbol] = InitializationState.SYNCING
            self.logger.info(f"🚀 {symbol}衍生品进入消息同步阶段")

            # 🔍 添加详细日志追踪快照数据访问
            self.logger.debug(f"🔍 快照数据访问: symbol={symbol}, available_keys={list(self.snapshot_data.keys())}")

            if symbol not in self.snapshot_data:
                self.logger.error(f"❌ {symbol}快照数据丢失！available_keys={list(self.snapshot_data.keys())}")
                return "failed"

            snapshot_info = self.snapshot_data[symbol]
            last_update_id = snapshot_info['lastUpdateId']

            self.logger.debug(f"🔍 使用快照数据: symbol={symbol}, lastUpdateId={last_update_id}")

            # 从缓存中找到第一条符合条件的消息
            sync_result = await self._sync_cached_messages_derivatives(symbol, last_update_id)

            if sync_result == "success":
                # 同步成功，进入第四阶段
                await self._trigger_running_phase(symbol)
            elif sync_result == "waiting":
                # 等待新消息，保持SYNCING状态，不重置
                self.logger.info(f"💡 {symbol}衍生品保持SYNCING状态，等待新的WebSocket消息")
                # 不做任何操作，保持当前状态
            else:
                # 真正的同步失败，重新开始
                await self._reset_initialization(symbol)

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品消息同步阶段失败: {e}", exc_info=True)
            await self._reset_initialization(symbol)

    async def _sync_cached_messages_derivatives(self, symbol: str, last_update_id: int) -> bool:
        """🚀 按Binance衍生品官方文档同步缓存消息"""
        try:
            cached_messages = self.message_cache[symbol]
            self.logger.info(f"🔍 {symbol}衍生品开始同步，lastUpdateId={last_update_id}, 缓存消息数={len(cached_messages)}")

            # 🔍 详细分析缓存消息的序列号范围
            if cached_messages:
                first_msg = cached_messages[0]
                last_msg = cached_messages[-1]
                self.logger.info(f"🔍 {symbol}衍生品缓存消息范围分析:")
                self.logger.info(f"   - 缓存消息数量: {len(cached_messages)}")
                self.logger.info(f"   - 第一条消息: U={first_msg.U}, u={first_msg.u}, pu={first_msg.pu}")
                self.logger.info(f"   - 最后一条消息: U={last_msg.U}, u={last_msg.u}, pu={last_msg.pu}")
                self.logger.info(f"   - API快照lastUpdateId: {last_update_id}")

            # 🎯 按Binance衍生品官方文档处理：
            # 1. 丢弃 u < lastUpdateId 的所有消息
            # 2. 找到第一条 U <= lastUpdateId 且 u >= lastUpdateId 的消息
            sync_start_index = None
            discarded_count = 0

            for i, cached_msg in enumerate(cached_messages):
                U = cached_msg.U
                u = cached_msg.u
                pu = cached_msg.pu

                if U is None or u is None:
                    continue

                # 步骤1：丢弃过期消息 (u < lastUpdateId)
                if u < last_update_id:
                    discarded_count += 1
                    self.logger.debug(f"🗑️ {symbol}衍生品丢弃过期消息{i}: U={U}, u={u} < lastUpdateId={last_update_id}")
                    continue

                # 步骤2：找到第一条有效消息 (U <= lastUpdateId 且 u >= lastUpdateId)
                if U <= last_update_id <= u:
                    sync_start_index = i
                    self.logger.info(f"✅ {symbol}衍生品找到同步起点: index={i}, U={U}, u={u}, pu={pu}, lastUpdateId={last_update_id}")
                    break

            if sync_start_index is None:
                # 🎯 应用现货成功经验：等待新消息策略
                if discarded_count > 0:
                    self.logger.warning(f"⚠️ {symbol}衍生品未找到有效的同步起点")
                    self.logger.warning(f"   - 丢弃了{discarded_count}条过期消息")

                    # 🎯 简化逻辑：快照较新时等待新的WebSocket消息
                    if cached_messages:
                        last_msg = cached_messages[-1]
                        if last_msg.u < last_update_id:
                            self.logger.info(f"💡 {symbol}快照较新: lastUpdateId={last_update_id} > 最后消息u={last_msg.u}")
                            self.logger.info(f"   - 等待符合条件的event: U <= {last_update_id} <= u")
                            return "waiting"  # 保持SYNCING状态，等待新消息
                        else:
                            # 消息已经超过快照，但没找到同步点，说明数据有问题
                            self.logger.warning(f"⚠️ {symbol}消息超过快照但无法同步，需要重新获取快照")
                            return "failed"
                    else:
                        return "failed"
                else:
                    self.logger.warning(f"⚠️ {symbol}衍生品没有可用的缓存消息")
                    return "failed"

            self.logger.info(f"📊 {symbol}衍生品同步统计: 丢弃{discarded_count}条过期消息，从第{sync_start_index}条开始同步")

            # 初始化订单簿状态
            await self._initialize_orderbook_from_snapshot_derivatives(symbol)

            # 应用从同步起点开始的所有消息
            applied_count = 0
            for i in range(sync_start_index, len(cached_messages)):
                cached_msg = cached_messages[i]
                try:
                    await self._apply_cached_message_derivatives(symbol, cached_msg)
                    applied_count += 1
                except Exception as e:
                    self.logger.error(f"❌ {symbol}衍生品应用缓存消息失败: {e}")
                    return "failed"

            self.logger.info(f"✅ {symbol}衍生品消息同步完成，应用了{applied_count}条消息")
            return "success"

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品消息同步失败: {e}", exc_info=True)
            return "failed"

    async def _trigger_running_phase(self, symbol: str):
        """🚀 第四阶段：进入正常运行模式（衍生品版本）"""
        try:
            self.init_states[symbol] = InitializationState.RUNNING
            self.logger.info(f"🚀 {symbol}衍生品进入正常运行模式")

            # 清理缓存数据，释放内存
            if symbol in self.message_cache:
                del self.message_cache[symbol]
            if symbol in self.cache_start_time:
                del self.cache_start_time[symbol]
            if symbol in self.snapshot_data:
                del self.snapshot_data[symbol]

            # 发布初始订单簿到NATS
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states[unique_key]
            if state.local_orderbook and self.enable_nats_push and self.nats_publisher:
                asyncio.create_task(self._publish_to_nats_async(symbol, state.local_orderbook))

            self.logger.info(f"✅ {symbol}衍生品分阶段初始化完成，进入正常运行模式")

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品进入运行模式失败: {e}", exc_info=True)

    async def _reset_initialization(self, symbol: str):
        """🚀 重置初始化状态，重新开始（衍生品版本）"""
        try:
            self.logger.warning(f"🔄 {symbol}衍生品重置初始化状态")

            # 重置状态
            self.init_states[symbol] = InitializationState.SUBSCRIBING

            # 清理缓存数据
            if symbol in self.message_cache:
                del self.message_cache[symbol]
            if symbol in self.cache_start_time:
                del self.cache_start_time[symbol]
            if symbol in self.snapshot_data:
                del self.snapshot_data[symbol]

            # 重置订单簿状态
            unique_key = self._get_unique_key(symbol)
            if unique_key in self.orderbook_states:
                state = self.orderbook_states[unique_key]
                state.is_synced = False
                state.local_orderbook = None
                state.last_update_id = 0

            self.logger.info(f"🔄 {symbol}衍生品初始化状态已重置，将重新开始分阶段初始化")

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品重置初始化失败: {e}", exc_info=True)

    async def _initialize_orderbook_from_snapshot_derivatives(self, symbol: str):
        """🚀 从快照初始化订单簿（衍生品版本）"""
        try:
            snapshot_info = self.snapshot_data[symbol]
            snapshot_data = snapshot_info['data']

            # 创建订单簿状态
            unique_key = self._get_unique_key(symbol)
            if unique_key not in self.orderbook_states:
                self.orderbook_states[unique_key] = OrderBookState(
                    symbol=symbol,
                    exchange="binance_derivatives"
                )

            state = self.orderbook_states[unique_key]
            state.last_update_id = snapshot_data['lastUpdateId']

            # 构建订单簿
            bids = []
            for price_str, qty_str in snapshot_data.get('bids', []):
                bids.append(PriceLevel(price=Decimal(price_str), quantity=Decimal(qty_str)))

            asks = []
            for price_str, qty_str in snapshot_data.get('asks', []):
                asks.append(PriceLevel(price=Decimal(price_str), quantity=Decimal(qty_str)))

            # 创建订单簿对象
            state.local_orderbook = EnhancedOrderBook(
                symbol_name=symbol,
                exchange_name="binance_derivatives",
                market_type="perpetual",
                bids=bids,
                asks=asks,
                timestamp=datetime.now(timezone.utc)
            )

            state.is_synced = True
            self.logger.info(f"✅ {symbol}衍生品订单簿初始化完成，lastUpdateId={state.last_update_id}")

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品订单簿初始化失败: {e}", exc_info=True)
            raise

    async def _apply_cached_message_derivatives(self, symbol: str, cached_msg: CachedMessage):
        """🚀 应用缓存的消息（衍生品版本）"""
        try:
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states[unique_key]

            # 🎯 衍生品特有验证：pu应该等于上一个event的u
            U = cached_msg.U
            u = cached_msg.u
            pu = cached_msg.pu

            # 第一条消息或者连续性检查
            if state.last_update_id == 0 or pu == state.last_update_id:
                # 序列号连续，应用更新
                await self._apply_update_optimized_derivatives(symbol, cached_msg.message, state)
                state.last_update_id = u
                self.logger.debug(f"✅ {symbol}衍生品应用缓存消息: U={U}, u={u}, pu={pu}")
            else:
                # 序列号不连续
                self.logger.warning(f"⚠️ {symbol}衍生品缓存消息序列号不连续: expected_pu={state.last_update_id}, actual_pu={pu}, U={U}, u={u}")
                raise Exception(f"序列号不连续: expected_pu={state.last_update_id}, actual_pu={pu}")

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品应用缓存消息失败: {e}", exc_info=True)
            raise

    async def _apply_update_optimized_derivatives(self, symbol: str, update: dict, state: OrderBookState):
        """🚀 优化版本的更新应用（衍生品版本）"""
        try:
            if not state.is_synced or not state.local_orderbook:
                self.logger.warning(f"⚠️ {symbol}衍生品未同步，跳过更新")
                return

            # 获取当前订单簿的副本
            current_bids = {bid.price: bid.quantity for bid in state.local_orderbook.bids}
            current_asks = {ask.price: ask.quantity for ask in state.local_orderbook.asks}

            # 🚀 性能优化：批量应用更新，减少循环开销
            # 应用买单更新
            for price_str, qty_str in update.get('b', []):
                price = Decimal(price_str)
                qty = Decimal(qty_str)
                if qty == 0:
                    current_bids.pop(price, None)
                else:
                    current_bids[price] = qty

            # 应用卖单更新
            for price_str, qty_str in update.get('a', []):
                price = Decimal(price_str)
                qty = Decimal(qty_str)
                if qty == 0:
                    current_asks.pop(price, None)
                else:
                    current_asks[price] = qty

            # 🚀 性能优化：批量排序和截取
            max_depth = 400  # 衍生品固定400档
            sorted_bids = sorted(current_bids.items(), key=lambda x: x[0], reverse=True)[:max_depth]
            sorted_asks = sorted(current_asks.items(), key=lambda x: x[0])[:max_depth]

            # 更新订单簿
            state.local_orderbook.bids = [PriceLevel(price=price, quantity=qty) for price, qty in sorted_bids]
            state.local_orderbook.asks = [PriceLevel(price=price, quantity=qty) for price, qty in sorted_asks]
            state.local_orderbook.timestamp = datetime.now(timezone.utc)

        except Exception as e:
            self.logger.error(f"❌ {symbol}衍生品优化版本更新应用失败: {e}", exc_info=True)

    async def _publish_to_nats_async(self, symbol: str, orderbook):
        """🚀 异步NATS发布 - 不阻塞主处理流程（衍生品版本）"""
        try:
            self.logger.debug(f"🔍 异步推送{symbol}衍生品到NATS")
            await self.nats_publisher.publish_enhanced_orderbook(orderbook)
            self.logger.debug(f"✅ NATS异步推送成功: {symbol}衍生品")
        except Exception as e:
            self.logger.error(f"❌ NATS异步推送失败: {symbol}衍生品, error={e}")
    
    async def _apply_update(self, symbol: str, update: dict, state: OrderBookState):
        """应用增量更新 - 🔧 统一：借鉴OKX成功模式"""
        try:
            if not state.is_synced or not state.local_orderbook:
                self.logger.warning(f"⚠️ {symbol}未同步，跳过更新")
                return

            # 🔧 统一：先用原始数据验证序列号
            is_valid, error_msg = self._validate_message_sequence(symbol, update, state)
            if not is_valid:
                self.logger.warning(f"⚠️ Binance衍生品更新序列号验证失败: {symbol}，回滚更新")
                self.logger.warning(f"🔍 序列号验证失败: {error_msg}")
                # 触发重新同步
                await self._trigger_resync(symbol, f"序列号验证失败: {error_msg}")
                return

            # 获取当前订单簿的副本
            current_bids = {bid.price: bid.quantity for bid in state.local_orderbook.bids}
            current_asks = {ask.price: ask.quantity for ask in state.local_orderbook.asks}

            # 更新买单
            for price_str, qty_str in update.get('b', []):
                price = Decimal(price_str)
                qty = Decimal(qty_str)

                if qty == 0:
                    # 删除价格档位
                    current_bids.pop(price, None)
                else:
                    # 更新价格档位
                    current_bids[price] = qty

            # 更新卖单
            for price_str, qty_str in update.get('a', []):
                price = Decimal(price_str)
                qty = Decimal(qty_str)

                if qty == 0:
                    # 删除价格档位
                    current_asks.pop(price, None)
                else:
                    # 更新价格档位
                    current_asks[price] = qty

            # 转换为PriceLevel列表并排序
            new_bids = [PriceLevel(price=p, quantity=q) for p, q in current_bids.items()]
            new_asks = [PriceLevel(price=p, quantity=q) for p, q in current_asks.items()]

            new_bids.sort(key=lambda x: x.price, reverse=True)
            new_asks.sort(key=lambda x: x.price)

            # 创建更新后的订单簿
            updated_orderbook = EnhancedOrderBook(
                symbol_name=symbol,  # 🎯 修复字段名：symbol -> symbol_name
                exchange_name=self.exchange_name,  # 🎯 修复字段名：exchange -> exchange_name
                market_type="perpetual",  # 🔧 修复：添加缺失的market_type字段
                bids=new_bids,
                asks=new_asks,
                timestamp=datetime.now(timezone.utc),
                last_update_id=state.last_update_id
            )

            # 更新状态
            state.local_orderbook = updated_orderbook
            state.last_update_time = datetime.now(timezone.utc)
            state.is_synced = True

            self.logger.debug(f"✅ Binance衍生品更新应用成功: {symbol}, bids={len(new_bids)}, asks={len(new_asks)}")

            # 发布到NATS
            await self.publish_orderbook(symbol, updated_orderbook)

            # 更新状态
            state.last_update_id = update.get('u')
            state.last_update_time = datetime.now(timezone.utc)

            self.stats['updates_applied'] += 1

            # 推送到NATS
            await self._publish_orderbook_update(symbol, state, 'update')

            self.logger.debug(f"✅ {symbol}更新应用成功")

        except Exception as e:
            self.logger.error(f"❌ 应用{symbol}更新失败", error=str(e), exc_info=True)
            state.is_synced = False
            raise

    async def _fetch_initial_snapshot(self, symbol: str) -> Optional['EnhancedOrderBook']:
        """获取初始快照"""
        try:
            snapshot = await self._fetch_websocket_api_snapshot(symbol)
            if not snapshot:
                return None

            # 转换为EnhancedOrderBook格式
            from ..data_types import EnhancedOrderBook, PriceLevel

            enhanced_orderbook = EnhancedOrderBook(
                exchange_name="binance_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=snapshot.last_update_id,
                bids=[PriceLevel(price=p, size=s) for p, s in snapshot.bids],
                asks=[PriceLevel(price=p, size=s) for p, s in snapshot.asks],
                timestamp=snapshot.timestamp,
                collected_at=datetime.now(timezone.utc)
            )

            return enhanced_orderbook

        except Exception as e:
            self.logger.error(f"❌ 获取{symbol}初始快照失败", error=str(e), exc_info=True)
            return None

    async def _exchange_specific_initialization(self):
        """
        Binance衍生品特定的初始化逻辑

        🔧 修复：增强日志和错误处理，确保初始化过程可见
        """
        try:
            self.logger.info("🚀 开始Binance衍生品OrderBook管理器初始化")

            # 步骤1：启动串行消息处理器
            self.logger.info("📋 步骤1：启动串行消息处理器")
            await self._start_message_processors(self.symbols)
            self.logger.info("✅ 串行消息处理器启动成功")

            # 步骤2：启动WebSocket客户端
            self.logger.info("📋 步骤2：启动WebSocket客户端")
            await self._start_websocket_client()
            self.logger.info("✅ WebSocket客户端启动成功")

            # 步骤3：等待WebSocket连接稳定（基于API测试优化）
            self.logger.info("📋 步骤3：等待WebSocket连接稳定（1秒，基于API测试优化）")
            await asyncio.sleep(1)
            self.logger.info("✅ WebSocket连接稳定等待完成")

            # 步骤4：串行初始化所有交易对订单簿（应用现货成功经验，避免快照混淆）
            self.logger.info("📋 步骤4：开始串行初始化订单簿（应用现货成功经验，避免快照混淆）")

            # 🎯 应用现货成功经验：串行初始化避免快照混淆
            # 改为串行初始化，确保每个symbol独立处理
            for symbol in self.symbols:
                try:
                    self.logger.info(f"🔄 开始初始化{symbol}订单簿...")
                    success = await self._initialize_symbol_orderbook(symbol)
                    if success:
                        self.logger.info(f"✅ {symbol}订单簿初始化成功")
                    else:
                        self.logger.error(f"❌ {symbol}订单簿初始化失败")
                        # 串行模式下，如果一个失败，继续处理下一个
                        continue
                except Exception as e:
                    self.logger.error(f"❌ {symbol}订单簿初始化异常: {e}")
                    continue

            self.logger.info("🎉 Binance衍生品OrderBook管理器初始化完成")

        except Exception as e:
            self.logger.error("❌ Binance衍生品特定初始化失败", error=str(e), exc_info=True)
            raise

    async def _exchange_specific_cleanup(self):
        """Binance特定的清理逻辑"""
        try:
            # 🔧 停止串行消息处理器
            self.message_processors_running = False
            for symbol, task in self.processing_tasks.items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # 清空消息队列
            for symbol, queue in self.message_queues.items():
                while not queue.empty():
                    try:
                        queue.get_nowait()
                        queue.task_done()
                    except asyncio.QueueEmpty:
                        break

            if self.binance_ws_client:
                # 停止WebSocket客户端
                await self.binance_ws_client.stop()
                self.binance_ws_client = None

        except Exception as e:
            self.logger.error("❌ Binance特定清理失败", error=str(e), exc_info=True)
    
    async def _trigger_resync(self, symbol: str, reason: str):
        """触发重新同步"""
        try:
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states[unique_key]
            
            self.logger.info(f"🔄 触发{symbol}重新同步: {reason}")
            
            # 标记为未同步
            state.is_synced = False
            state.last_update_id = None
            
            # 重新初始化
            await self._initialize_symbol_orderbook(symbol)
            
        except Exception as e:
            self.logger.error(f"❌ {symbol}重新同步失败", error=str(e), exc_info=True)
    
    async def _publish_orderbook_update(self, symbol: str, state: OrderBookState, update_type: str):
        """
        推送订单簿更新到NATS - 优化：延迟标准化

        🔧 架构优化：保持原始Binance数据格式到NATS发布层
        确保lastUpdateId验证等逻辑使用原始数据
        """
        try:
            if not self.enable_nats_push:
                return

            # 限制深度到400档
            limited_orderbook = self._limit_orderbook_depth(state.local_orderbook)

            # 🔧 优化：构建原始Binance格式数据，不进行标准化
            raw_binance_data = {
                'exchange': self.exchange,
                'market_type': self.market_type,
                'symbol': symbol,  # 保持原始Binance格式 (如BTCUSDT)
                'lastUpdateId': state.last_update_id,
                'bids': [[str(p), str(s)] for p, s in limited_orderbook['bids'].items()],
                'asks': [[str(p), str(s)] for p, s in limited_orderbook['asks'].items()],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'update_type': update_type,
                'raw_data': True,  # 标记为原始数据
                'exchange_specific': {
                    'lastUpdateId_validation': True,
                    'api_initialized': True
                }
            }

            # 🔧 优化：发布原始数据，标准化在NATS Publisher中统一进行
            await self.nats_publisher.publish_orderbook_data(
                self.exchange,
                self.market_type,
                symbol,  # 使用原始symbol
                raw_binance_data
            )

        except Exception as e:
            self.logger.error(f"❌ 推送{symbol}订单簿更新失败", error=str(e), exc_info=True)
    
    def _limit_orderbook_depth(self, orderbook: EnhancedOrderBook) -> dict:
        """限制订单簿深度到400档

        Args:
            orderbook: EnhancedOrderBook对象

        Returns:
            限制深度后的字典格式数据
        """
        # 从EnhancedOrderBook对象中提取bids和asks
        # bids和asks是List[PriceLevel]，需要转换为价格->数量的字典
        bids_dict = {}
        asks_dict = {}

        # 转换bids (买单，按价格从高到低排序)
        for price_level in orderbook.bids[:400]:  # 限制到400档
            bids_dict[price_level.price] = price_level.quantity

        # 转换asks (卖单，按价格从低到高排序)
        for price_level in orderbook.asks[:400]:  # 限制到400档
            asks_dict[price_level.price] = price_level.quantity

        return {
            'bids': bids_dict,
            'asks': asks_dict
        }
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.stats.copy()

    async def _perform_reconnection(self) -> bool:
        """
        执行Binance衍生品WebSocket重连操作

        Returns:
            bool: 重连是否成功
        """
        try:
            self.logger.info("🔄 开始Binance衍生品WebSocket重连")

            # Binance衍生品重连逻辑：
            # 1. 重连由WebSocket客户端自动处理
            # 2. 管理器需要重置订单簿状态
            # 3. 重新获取快照数据

            # 重置所有订单簿状态
            for symbol, state in self.orderbook_states.items():
                state.is_synced = False
                state.local_orderbook = None
                state.last_update_id = 0
                self.logger.debug(f"🔄 重置Binance衍生品订单簿状态: {symbol}")

            # 重置错误计数器
            self._reset_error_counters()

            self.logger.info("✅ Binance衍生品重连准备完成，等待WebSocket重新连接")
            return True

        except Exception as e:
            self.logger.error(f"❌ Binance衍生品重连失败: {e}")
            return False

    async def _exchange_specific_resync(self, symbol: str, reason: str):
        """
        Binance衍生品特定的重新同步逻辑

        Args:
            symbol: 交易对
            reason: 重新同步原因
        """
        try:
            self.logger.info(f"🔄 Binance衍生品重新同步: {symbol}, 原因: {reason}")

            # Binance衍生品重新同步策略：
            # 1. 重置订单簿状态
            # 2. 重新获取API快照
            # 3. 等待WebSocket增量更新

            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if state:
                state.is_synced = False
                state.local_orderbook = None
                state.last_update_id = 0
                self.logger.debug(f"🔄 重置Binance衍生品订单簿状态: {symbol}")

            # 重新获取快照
            try:
                snapshot = await self._fetch_initial_snapshot(symbol)
                if snapshot:
                    state.local_orderbook = snapshot
                    state.last_update_id = snapshot.last_update_id
                    state.is_synced = True
                    self.logger.info(f"✅ Binance衍生品快照重新获取成功: {symbol}")
                else:
                    self.logger.warning(f"⚠️ Binance衍生品快照重新获取失败: {symbol}")
            except Exception as e:
                self.logger.error(f"❌ Binance衍生品快照重新获取异常: {symbol}, error={e}")

            self.logger.info(f"✅ Binance衍生品重新同步完成: {symbol}")

        except Exception as e:
            self.logger.error(f"❌ Binance衍生品重新同步失败: {symbol}, error={e}")
