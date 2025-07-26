"""
Binance现货订单簿管理器
处理Binance现货市场的订单簿数据，实现lastUpdateId验证和API快照初始化
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
import time
from enum import Enum
from collections import deque

from .base_orderbook_manager import BaseOrderBookManager
from ..data_types import OrderBookState, NormalizedOrderBook, OrderBookSnapshot, EnhancedOrderBook, PriceLevel, OrderBookUpdateType
from ..error_management.error_handler import ErrorHandler, BinanceAPIError, RetryHandler

# 🔧 迁移到统一日志系统
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    ComponentType
)


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
        self.U = message.get('U')  # 第一个更新ID
        self.u = message.get('u')  # 最后一个更新ID


class BinanceSpotOrderBookManager(BaseOrderBookManager):
    """Binance现货订单簿管理器"""
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        super().__init__(
            exchange="binance_spot",
            market_type="spot", 
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(
            ComponentType.ORDERBOOK_MANAGER,
            exchange="binance",
            market_type="spot"
        )

        # 🎯 初始化错误处理器
        self.error_handler = ErrorHandler(self.logger)
        self.retry_handler = RetryHandler(self.error_handler)

        # Binance现货特定配置
        self.api_base_url = config.get('api_base_url', 'https://api.binance.com')
        self.ws_base_url = config.get('ws_base_url', 'wss://stream.binance.com:9443/ws')
        self.depth_limit = config.get('depth_limit', 5000)  # Binance现货最大5000档
        self.lastUpdateId_validation = config.get('lastUpdateId_validation', True)
        
        # WebSocket客户端
        self.binance_ws_client = None

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

        # 🚀 分阶段初始化状态管理
        self.init_states: Dict[str, InitializationState] = {}
        self.message_cache: Dict[str, deque] = {}  # 消息缓存队列
        self.cache_start_time: Dict[str, float] = {}  # 缓存开始时间
        self.snapshot_data: Dict[str, dict] = {}  # API快照数据
        self.cache_duration = 2.0  # 缓存持续时间（秒）- 优化为2秒快速触发快照

        # 🔒 并发控制：防止多个symbol同时获取快照
        self.snapshot_locks: Dict[str, asyncio.Lock] = {}
        self.snapshot_in_progress: Dict[str, bool] = {}
        self.processing_tasks: Dict[str, asyncio.Task] = {}
        self.message_processors_running = False

        # 🔧 新增：消息缓冲区用于处理乱序消息
        self.message_buffers: Dict[str, List[dict]] = {}
        self.buffer_max_size = config.get('buffer_max_size', 100)  # 缓冲区最大大小
        self.buffer_timeout = config.get('buffer_timeout', 5.0)    # 缓冲超时时间(秒)
        
        self.logger.info("🏭 Binance现货订单簿管理器初始化完成", 
                        symbols=symbols, 
                        api_base_url=self.api_base_url,
                        depth_limit=self.depth_limit,
                        lastUpdateId_validation=self.lastUpdateId_validation)
    
    def _get_snapshot_depth(self) -> int:
        """Binance现货快照深度：5000档"""
        return 5000

    def _get_websocket_depth(self) -> int:
        """Binance现货WebSocket深度：5000档"""
        return 5000

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

        self.logger.debug(f"🔧 启动{symbol}的串行消息处理器")

        try:
            while True:
                # 从队列中获取消息
                message_data = await queue.get()

                # 检查停止信号
                if message_data is None:
                    break

                # 串行处理消息（使用锁确保原子性）
                async with lock:
                    try:
                        # 🚀 激进优化：动态过期时间和队列深度策略
                        message_age = time.time() - message_data.get('timestamp', time.time())
                        queue_size = queue.qsize()

                        # 动态过期时间：队列越满，过期时间越短
                        if queue_size > 5000:  # 队列超过50%
                            max_age = 1.0  # 1秒
                        elif queue_size > 2000:  # 队列超过20%
                            max_age = 2.0  # 2秒
                        else:
                            max_age = 3.0  # 3秒（比原来的5秒更激进）

                        if message_age > max_age:
                            self.logger.warning(f"⚠️ 丢弃过期消息: {symbol}, age={message_age:.2f}s, max_age={max_age:.1f}s, queue_size={queue_size}")
                            continue

                        # 🚀 激进优化：批量丢弃策略
                        if queue_size > 8000:  # 队列超过80%，批量丢弃中间消息
                            dropped_count = 0
                            while queue.qsize() > 5000 and dropped_count < 100:  # 最多丢弃100条
                                try:
                                    old_msg = queue.get_nowait()
                                    old_age = time.time() - old_msg.get('timestamp', time.time())
                                    if old_age > 1.0:  # 丢弃超过1秒的消息
                                        dropped_count += 1
                                        queue.task_done()
                                    else:
                                        # 如果消息还比较新，放回队列
                                        queue.put_nowait(old_msg)
                                        break
                                except asyncio.QueueEmpty:
                                    break
                            if dropped_count > 0:
                                self.logger.warning(f"🚀 批量丢弃过期消息: {symbol}, dropped={dropped_count}, remaining_queue={queue.qsize()}")

                        # 🔧 关键修复：直接调用原子性处理，避免双重路径
                        update = message_data['update']
                        await self._process_binance_message_atomic(symbol, update)
                    except Exception as e:
                        self.logger.error(f"❌ 处理{symbol}消息失败: {e}")
                    finally:
                        queue.task_done()

        except asyncio.CancelledError:
            self.logger.info(f"🔧 {symbol}串行处理器已取消")
        except Exception as e:
            self.logger.error(f"❌ {symbol}串行处理器异常: {e}")

    async def _enqueue_message(self, symbol: str, update: dict):
        """将消息加入队列进行串行处理"""
        # 🔧 修复：检查管理器是否正在停止
        if not self.message_processors_running:
            self.logger.debug(f"🔍 {symbol}管理器正在停止，跳过消息入队")
            return False

        if symbol not in self.message_queues:
            # 🔧 修复：在停止过程中，队列可能已被清理，这是正常情况
            if not self.message_processors_running:
                self.logger.debug(f"🔍 {symbol}队列已清理（管理器停止中）")
            else:
                self.logger.warning(f"⚠️ {symbol}的消息队列不存在")
            return False

        queue = self.message_queues[symbol]

        try:
            # 🔍 时序数据收集：记录消息接收和入队时间
            receive_time = time.time()
            message_data = {
                'timestamp': receive_time,
                'symbol': symbol,
                'update': update,
                'sequence_info': {
                    'U': update.get('U'),
                    'u': update.get('u'),
                    'receive_time': receive_time,
                    'queue_size_before': queue.qsize()
                }
            }

            # 非阻塞方式加入队列
            queue.put_nowait(message_data)

            # 🔍 DEBUG: 记录入队信息
            self.logger.debug(f"🔍 消息入队: {symbol}, U={update.get('U')}, u={update.get('u')}, 队列大小={queue.qsize()}")

            return True
        except asyncio.QueueFull:
            self.logger.warning(f"⚠️ {symbol}消息队列已满，丢弃消息")
            return False

    async def _process_single_message_atomic(self, symbol: str, message_data: dict):
        """处理单条消息 - 原子性操作"""
        try:
            self.logger.debug(f"🔍 开始处理单个消息: {symbol}")
            update = message_data['update']
            self.logger.debug(f"🔍 消息内容: U={update.get('U')}, u={update.get('u')}")
            await self._process_binance_message_atomic(symbol, update)
            self.logger.debug(f"✅ 单个消息处理完成: {symbol}")
        except Exception as e:
            self.logger.error(f"❌ 处理单个消息时发生异常: {e}", symbol=symbol, exc_info=True)

    async def _process_binance_message_atomic(self, symbol: str, update: dict):
        """🎯 按照用户理解的正确逻辑处理实时消息"""
        try:
            # 获取状态
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if not state:
                self.logger.warning(f"⚠️ {symbol}状态不存在")
                return

            # 只处理已同步的订单簿
            if not state.is_synced or not state.local_orderbook:
                self.logger.debug(f"🔍 {symbol}未同步，跳过处理")
                return

            # 提取序列号
            U = update.get('U')
            u = update.get('u')

            if U is None or u is None:
                self.logger.warning(f"⚠️ {symbol}消息缺少序列号: U={U}, u={u}")
                return

            current_last_update_id = state.last_update_id
            self.logger.debug(f"🔍 {symbol}处理实时消息: U={U}, u={u}, 本地lastUpdateId={current_last_update_id}")

            # 🎯 核心逻辑：按照用户理解的逻辑处理

            # 1. 丢弃过期event：u < 本地lastUpdateId
            if u < current_last_update_id:
                self.logger.debug(f"🗑️ {symbol}丢弃过期event: u={u} < 本地lastUpdateId={current_last_update_id}")
                return

            # 2. 检查是否匹配：U <= 本地lastUpdateId <= u
            if U <= current_last_update_id <= u:
                # 匹配，可以应用
                await self._apply_orderbook_update(symbol, update, state)
                # 🎯 核心：更新本地lastUpdateId = event的u
                state.last_update_id = u
                self.logger.debug(f"✅ {symbol}应用实时event: lastUpdateId {current_last_update_id} → {u}")

                # 发布到NATS
                if self.enable_nats_push and self.nats_publisher:
                    asyncio.create_task(self._publish_to_nats_async(symbol, state.local_orderbook))
                return

            # 3. 异常情况：本地lastUpdateId < event的U（快照太早）
            if current_last_update_id < U:
                gap = U - current_last_update_id

                # 🎯 优化：Gap=1是完美连续状态，不应该警告
                if gap == 1:
                    # Gap=1是理想的连续状态，使用DEBUG级别
                    self.logger.debug(f"✅ {symbol}序列号连续: 本地lastUpdateId={current_last_update_id} → U={U}")
                    await self._apply_orderbook_update(symbol, update, state)
                    state.last_update_id = u
                    # 不增加警告统计
                elif gap <= 100:
                    # 小gap，记录警告但继续处理
                    self.logger.warning(f"⚠️ {symbol}检测到小gap: 本地lastUpdateId={current_last_update_id} < U={U}, gap={gap}")
                    self.logger.warning(f"⚠️ {symbol}小gap继续处理: gap={gap}")
                    await self._apply_orderbook_update(symbol, update, state)
                    state.last_update_id = u
                    self.stats['sequence_warnings'] += 1
                elif gap <= 1000:
                    # 中等gap，记录错误但尝试继续
                    self.logger.error(f"🚨 {symbol}检测到中等gap: 本地lastUpdateId={current_last_update_id} < U={U}, gap={gap}")
                    self.logger.error(f"🚨 {symbol}中等gap尝试继续: gap={gap}")
                    await self._apply_orderbook_update(symbol, update, state)
                    state.last_update_id = u
                    self.stats['sequence_errors'] += 1
                else:
                    # 大gap，触发重新同步
                    self.logger.error(f"💥 {symbol}检测到大gap: 本地lastUpdateId={current_last_update_id} < U={U}, gap={gap}")
                    self.logger.error(f"💥 {symbol}大gap触发重新同步: gap={gap}")
                    await self._trigger_resync(symbol, f"大gap: {gap}")
                    self.stats['sequence_errors'] += 1
                return

            # 4. 其他异常情况
            self.logger.warning(f"⚠️ {symbol}未知序列号情况: U={U}, u={u}, 本地lastUpdateId={current_last_update_id}")

        except Exception as e:
            self.logger.error(f"❌ {symbol}处理实时消息失败: {e}")
            self.stats['errors'] += 1

    async def _apply_binance_update_atomic(self, symbol: str, update: dict, state):
        """原子性应用Binance更新 - 🚀 性能优化版本"""
        try:
            # 🚀 性能优化：直接应用更新，避免重复验证
            await self._apply_update_optimized(symbol, update, state)

            # 检查更新是否成功
            if state.local_orderbook:
                # 🚀 性能优化：降级为DEBUG，减少日志开销
                self.logger.debug(f"✅ Binance现货更新应用成功: {symbol}")

                # 🚀 性能优化：异步更新统计，避免阻塞
                self.stats['updates_applied'] += 1

                # 🚀 性能优化：异步NATS发布，避免阻塞主处理流程
                if self.enable_nats_push and self.nats_publisher:
                    # 创建异步任务，不等待完成
                    asyncio.create_task(self._publish_to_nats_async(symbol, state.local_orderbook))
            else:
                self.logger.warning(f"⚠️ {symbol}更新应用失败")

        except Exception as e:
            self.logger.error(f"❌ 应用Binance更新失败: {symbol}, error={e}", exc_info=True)

    async def _publish_to_nats_async(self, symbol: str, orderbook):
        """🚀 异步NATS发布 - 不阻塞主处理流程"""
        try:
            self.logger.debug(f"🔍 异步推送{symbol}到NATS")
            await self.nats_publisher.publish_enhanced_orderbook(orderbook)
            self.logger.debug(f"✅ NATS异步推送成功: {symbol}")
        except Exception as e:
            self.logger.error(f"❌ NATS异步推送失败: {symbol}, error={e}")

    async def _apply_update_optimized(self, symbol: str, update: dict, state: OrderBookState):
        """🚀 优化版本的更新应用 - 减少重复验证"""
        try:
            if not state.is_synced or not state.local_orderbook:
                self.logger.warning(f"⚠️ {symbol}未同步，跳过更新")
                return

            # 🚀 性能优化：跳过重复的序列号验证（已在上层验证）
            # 直接应用更新，提高处理速度

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
            max_depth = 400  # Binance现货固定400档
            sorted_bids = sorted(current_bids.items(), key=lambda x: x[0], reverse=True)[:max_depth]
            sorted_asks = sorted(current_asks.items(), key=lambda x: x[0])[:max_depth]

            # 更新订单簿
            state.local_orderbook.bids = [PriceLevel(price=price, quantity=qty) for price, qty in sorted_bids]
            state.local_orderbook.asks = [PriceLevel(price=price, quantity=qty) for price, qty in sorted_asks]
            state.local_orderbook.timestamp = datetime.now(timezone.utc)

        except Exception as e:
            # 🔧 迁移到统一日志系统 - 标准化错误处理
            self.logger.error(
                "Optimized orderbook update failed",
                error=e,
                symbol=symbol,
                operation="orderbook_update"
            )

    async def initialize_orderbook_states(self):
        """🚀 分阶段初始化：初始化订单簿状态"""
        # 🔧 迁移到统一日志系统 - 标准化启动日志
        self.logger.startup("Starting Binance spot phased initialization")

        for symbol in self.symbols:
            # 初始化状态为第一阶段：订阅和缓存
            self.init_states[symbol] = InitializationState.SUBSCRIBING

            unique_key = self._get_unique_key(symbol)
            self.orderbook_states[unique_key] = OrderBookState(
                symbol=symbol,
                exchange="binance_spot"
            )

            # 🔧 迁移到统一日志系统 - 数据处理日志会被自动去重
            self.logger.data_processed(
                "Symbol initialized to SUBSCRIBING state",
                symbol=symbol,
                state="SUBSCRIBING",
                phase="message_caching"
            )

    async def process_websocket_message(self, symbol: str, message: dict):
        """🚨 已弃用：避免并发处理，统一使用串行队列处理"""
        self.logger.warning(f"⚠️ 调用了已弃用的process_websocket_message方法: {symbol}")
        self.logger.warning("🔧 请使用_handle_websocket_update方法进行串行处理")

        # 🔧 重定向到串行处理队列
        try:
            success = await self._enqueue_message(symbol, message)
            if not success:
                # 🔧 修复：在停止过程中，重定向失败是正常的
                if self.message_processors_running:
                    self.logger.error(f"❌ {symbol}消息重定向到串行队列失败")
                else:
                    self.logger.debug(f"🔍 {symbol}消息重定向失败（管理器停止中）")
        except Exception as e:
            if self.message_processors_running:
                self.logger.error(f"❌ {symbol}消息重定向失败: {e}")
            else:
                self.logger.debug(f"🔍 {symbol}消息重定向异常（管理器停止中）: {e}")

    def _validate_message_sequence(self, symbol: str, message: dict, state: OrderBookState) -> tuple[bool, str]:
        """
        🔧 统一：验证Binance现货消息序列 - 借鉴OKX成功模式
        使用原始数据进行验证，与OKX保持一致的验证流程
        """
        try:
            if not self.lastUpdateId_validation:
                return True, ""

            first_update_id = message.get('U')  # firstUpdateId
            final_update_id = message.get('u')   # finalUpdateId

            if first_update_id is None or final_update_id is None:
                return False, "缺少必要的序列号字段 U 或 u"

            # 如果是第一次更新（刚完成初始化）
            if state.last_update_id == 0:
                state.last_update_id = final_update_id
                self.logger.info(f"✅ Binance现货首次序列号设置成功: {symbol}, U={first_update_id}, u={final_update_id}")
                return True, "首次更新"

            # 🎯 Binance现货核心验证：U <= lastUpdateId + 1 <= u (官方文档规则)
            expected_min_first_id = state.last_update_id + 1

            # 🔍 时序数据收集：记录验证详情
            validation_time = time.time()
            self.logger.debug(f"🔍 序列号验证: {symbol}, lastUpdateId={state.last_update_id}, U={first_update_id}, u={final_update_id}, expected={expected_min_first_id}")

            if first_update_id <= expected_min_first_id <= final_update_id:
                # 序列号连续，更新状态
                old_update_id = state.last_update_id
                state.last_update_id = final_update_id
                self.logger.debug(f"✅ Binance现货序列号验证成功: {symbol}, 从{old_update_id}更新到{final_update_id}")
                return True, "现货序列号连续"
            else:
                # 🔧 智能容错：基于Binance数据流特性优化
                gap = abs(first_update_id - expected_min_first_id)

                # 🔍 时序数据收集：记录gap详情
                self.logger.warning(f"🔍 序列号不连续详情: {symbol}, gap={gap}, direction={'向前' if first_update_id > expected_min_first_id else '向后'}")

                # 检查是否是向前跳跃（正常情况）
                if first_update_id > expected_min_first_id:
                    # 向前跳跃，可能是网络延迟或高频交易
                    if gap <= 1000:  # 适度跳跃，继续处理
                        old_update_id = state.last_update_id
                        state.last_update_id = final_update_id
                        self.logger.debug(f"⚠️ Binance现货序列号向前跳跃但继续处理: {symbol}, gap={gap}")
                        return True, f"向前跳跃容错: gap={gap}"
                    else:
                        # 大幅向前跳跃，可能丢失了重要数据
                        error_msg = f"序列号大幅向前跳跃: lastUpdateId={state.last_update_id}, U={first_update_id}, u={final_update_id}, gap={gap}"
                        self.logger.warning(f"⚠️ Binance现货序列号验证失败: {symbol}, {error_msg}")
                        return False, error_msg
                else:
                    # 向后跳跃，数据乱序，必须重新同步
                    error_msg = f"序列号向后跳跃: lastUpdateId={state.last_update_id}, U={first_update_id}, u={final_update_id}, gap={gap}"
                    self.logger.warning(f"⚠️ Binance现货序列号验证失败: {symbol}, {error_msg}")
                    return False, error_msg

        except Exception as e:
            error_msg = f"序列验证异常: {e}"
            self.logger.error(f"❌ Binance现货序列号验证异常: {symbol}, {error_msg}")
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

        # 按U字段排序（Binance现货）
        buffer.sort(key=lambda x: x['message'].get('U', 0))

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
            first_update_id = message.get('U')

            # 检查是否是期望的下一个消息
            if first_update_id == state.last_update_id + 1:
                processed_messages.append(message)
                state.last_update_id = message.get('u')
                buffer.pop(0)
                self.logger.debug(f"🔄 {symbol} 从缓冲区处理消息: U={first_update_id}, u={message.get('u')}")
            else:
                break  # 不连续，停止处理

        return processed_messages

    async def _apply_snapshot(self, symbol: str, snapshot_data: dict, state: OrderBookState):
        """应用Binance快照数据 - 统一使用EnhancedOrderBook格式"""
        try:
            self.logger.debug(f"📊 应用Binance现货快照: {symbol}")

            # 解析快照数据
            bids_data = snapshot_data.get('bids', [])
            asks_data = snapshot_data.get('asks', [])
            last_update_id = snapshot_data.get('lastUpdateId', 0)

            # 🔧 统一：先验证序列号（如果需要）
            if self.lastUpdateId_validation and state.last_update_id > 0:
                # 快照的lastUpdateId应该大于等于当前的last_update_id
                if last_update_id >= state.last_update_id:
                    self.logger.info(f"✅ Binance现货快照序列号验证成功: {symbol}, lastUpdateId={last_update_id}")
                else:
                    self.logger.warning(f"⚠️ Binance现货快照序列号异常: {symbol}, 快照={last_update_id}, 当前={state.last_update_id}")

            # 然后构建价位列表用于内部处理
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
                exchange_name="binance_spot",
                symbol_name=symbol,
                market_type="spot",
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

            self.logger.info(f"✅ Binance现货快照应用成功: {symbol}, bids={len(bids)}, asks={len(asks)}, lastUpdateId={last_update_id}")

            # 发布到NATS
            await self.publish_orderbook(symbol, snapshot)

        except Exception as e:
            self.logger.error(f"❌ 应用Binance现货快照失败: {symbol}, error={e}")
            state.is_synced = False
            raise

    async def start_management(self):
        """启动Binance现货订单簿管理"""
        try:
            # 🔧 迁移到统一日志系统 - 使用操作上下文管理器
            with self.logger.operation_context("binance_spot_orderbook_management"):
                # 初始化状态
                await self.initialize_orderbook_states()

                # 启动WebSocket连接
                await self._start_websocket_client()

                # 等待WebSocket连接稳定
                await asyncio.sleep(2)

                # 为每个交易对初始化订单簿
                for symbol in self.symbols:
                    await self._initialize_symbol_orderbook(symbol)
            
        except Exception as e:
            # 🔧 迁移到统一日志系统 - 标准化错误处理
            self.logger.error(
                "Binance spot orderbook management startup failed",
                error=e,
                operation="startup"
            )
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
            
            self.binance_ws_client = BinanceWebSocketClient(
                symbols=self.symbols,
                on_orderbook_update=self._handle_websocket_update,
                ws_base_url=self.ws_base_url,
                market_type="spot"
            )
            
            # 启动WebSocket客户端（非阻塞）
            self.logger.info("🚀 启动Binance现货WebSocket客户端")
            asyncio.create_task(self.binance_ws_client.start())
            
        except Exception as e:
            self.logger.error("❌ 启动WebSocket客户端失败", error=str(e), exc_info=True)
            raise
    
    async def _initialize_symbol_orderbook(self, symbol: str):
        """
        初始化单个交易对的订单簿 - 严格按照币安官方文档实现

        币安现货订单簿维护流程：
        1. 开始缓存WebSocket消息（记录第一个event的U值）
        2. 获取API快照
        3. 如果快照lastUpdateId <= 第一个event的U值，重新获取快照
        4. 丢弃所有u <= lastUpdateId的缓存消息
        5. 从第一个有效消息开始应用更新
        """
        try:
            # 🔧 迁移到统一日志系统 - 标准化初始化日志
            self.logger.data_processed(
                "Initializing orderbook per Binance official documentation",
                symbol=symbol,
                operation="orderbook_initialization"
            )

            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states[unique_key]

            # 步骤1: 检查是否有缓存的消息（WebSocket已经开始接收）
            first_event_u = None
            if symbol in self.message_buffers and self.message_buffers[symbol]:
                first_event_u = self.message_buffers[symbol][0]['message'].get('U')
                # 🔧 迁移到统一日志系统 - 数据处理日志
                self.logger.data_processed(
                    "Found cached messages for symbol",
                    symbol=symbol,
                    first_event_u=first_event_u,
                    cached_messages=len(self.message_buffers[symbol])
                )
            else:
                # 🔧 迁移到统一日志系统 - 数据处理日志
                self.logger.data_processed(
                    "No cached messages, using direct snapshot initialization",
                    symbol=symbol,
                    initialization_method="direct_snapshot"
                )

            # 步骤2: 获取API快照（可能需要重试）
            max_retries = 3
            snapshot = None
            self.logger.info(f"🔄 开始获取{symbol}API快照，最大重试次数: {max_retries}")

            for attempt in range(max_retries):
                snapshot = await self._fetch_api_snapshot(symbol)
                if not snapshot:
                    self.logger.error(f"❌ 获取{symbol}快照失败，尝试 {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        # 🔧 指数退避策略：1秒、2秒、4秒
                        delay = 2 ** attempt
                        self.logger.info(f"⏳ 等待{delay}秒后重试...")
                        await asyncio.sleep(delay)
                    continue

                # 步骤3: 验证快照是否有效（币安官方文档要求）
                last_update_id = snapshot.last_update_id
                if first_event_u is not None and last_update_id <= first_event_u:
                    self.logger.warning(f"⚠️ {symbol}快照过旧: lastUpdateId={last_update_id} <= 第一个event U={first_event_u}，重新获取")
                    await asyncio.sleep(0.5)  # 短暂等待后重试
                    continue

                # 快照有效，跳出重试循环
                self.logger.info(f"✅ {symbol}快照符合要求: lastUpdateId={last_update_id}")
                break

            if not snapshot:
                self.logger.error(f"❌ 获取{symbol}有效快照失败，已重试{max_retries}次")
                return False

            last_update_id = snapshot.last_update_id
            self.logger.info(f"✅ {symbol}获取有效快照: lastUpdateId={last_update_id}")

            # 步骤4: 丢弃过期的缓存消息（u <= lastUpdateId）
            if symbol in self.message_buffers:
                original_count = len(self.message_buffers[symbol])
                self.message_buffers[symbol] = [
                    buffered_msg for buffered_msg in self.message_buffers[symbol]
                    if buffered_msg['message'].get('u', 0) > last_update_id
                ]
                discarded_count = original_count - len(self.message_buffers[symbol])
                if discarded_count > 0:
                    self.logger.info(f"🗑️ {symbol}丢弃{discarded_count}条过期消息（u <= {last_update_id}）")

            # 步骤5: 应用快照
            bids = [PriceLevel(price=price, quantity=quantity) for price, quantity in snapshot.bids]
            asks = [PriceLevel(price=price, quantity=quantity) for price, quantity in snapshot.asks]

            bids.sort(key=lambda x: x.price, reverse=True)
            asks.sort(key=lambda x: x.price)

            enhanced_orderbook = EnhancedOrderBook(
                exchange_name="binance_spot",
                symbol_name=symbol,
                market_type="spot",
                last_update_id=last_update_id,
                bids=bids,
                asks=asks,
                timestamp=int(time.time() * 1000),  # 使用当前时间戳
                update_type=OrderBookUpdateType.SNAPSHOT,
                first_update_id=last_update_id,
                prev_update_id=last_update_id,
                depth_levels=len(bids) + len(asks)
            )

            state.local_orderbook = enhanced_orderbook
            state.last_update_id = snapshot.last_update_id
            state.is_synced = True
            state.last_update_time = datetime.now(timezone.utc)

            self.logger.info(f"✅ {symbol}订单簿初始化成功，按币安官方文档流程完成")

            # 推送初始快照到NATS
            await self.publish_orderbook(symbol, enhanced_orderbook)

            # 步骤6: 处理缓存的有效消息
            if symbol in self.message_buffers and self.message_buffers[symbol]:
                valid_messages = len(self.message_buffers[symbol])
                self.logger.info(f"📦 {symbol}准备处理{valid_messages}条缓存的有效消息")

            return True

        except Exception as e:
            self.logger.error(f"❌ 初始化{symbol}订单簿失败", error=str(e), exc_info=True)
            return False
    
    async def _fetch_api_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """获取Binance现货API快照"""
        try:
            url = f"{self.api_base_url}/api/v3/depth?symbol={symbol}&limit={self.depth_limit}"
            self.stats['api_calls'] += 1
            
            self.logger.info(f"📡 获取{symbol}快照: {url}")
            
            # 🔧 优化超时设置：考虑网络波动，增加连接超时到10秒
            timeout = aiohttp.ClientTimeout(total=20.0, connect=10.0)  # 总超时20秒，连接超时10秒
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        # 🎯 使用错误处理器解析API错误
                        response_text = await response.text()
                        api_error = self.error_handler.parse_binance_error(response_text, response.status)
                        error_info = self.error_handler.handle_api_error(api_error, {
                            'symbol': symbol,
                            'url': url,
                            'method': 'GET'
                        })
                        return None

                    data = await response.json()
                    
                    # 解析数据
                    bids = [(Decimal(price), Decimal(qty)) for price, qty in data['bids']]
                    asks = [(Decimal(price), Decimal(qty)) for price, qty in data['asks']]
                    
                    snapshot = OrderBookSnapshot(
                        symbol=symbol,
                        exchange="binance_spot",
                        bids=bids,
                        asks=asks,
                        last_update_id=data['lastUpdateId'],
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    self.stats['snapshots_received'] += 1
                    self.logger.info(f"✅ 获取{symbol}快照成功, lastUpdateId={snapshot.last_update_id}")
                    
                    return snapshot
                    
        except Exception as e:
            self.logger.error(f"❌ 获取{symbol}快照失败", error=str(e), exc_info=True)
            return None
    
    async def _handle_websocket_update(self, symbol: str, update: dict):
        """🎯 分阶段初始化：处理WebSocket更新 - 支持SYNCING状态下的持续检查"""
        try:
            receive_time = time.time()
            current_state = self.init_states.get(symbol, InitializationState.SUBSCRIBING)

            self.logger.debug(f"🔍 WebSocket回调: {symbol}, U={update.get('U')}, u={update.get('u')}, state={current_state.value}")

            if current_state == InitializationState.SUBSCRIBING:
                # 第一阶段：缓存消息
                await self._cache_message(symbol, update, receive_time)
            elif current_state == InitializationState.SYNCING:
                # 🎯 用户建议：第三阶段也要缓存消息，并检查是否可以同步
                await self._cache_message(symbol, update, receive_time)

                # 每收到新消息就检查一次是否可以同步
                if symbol in self.snapshot_data:
                    snapshot_info = self.snapshot_data[symbol]
                    last_update_id = snapshot_info['lastUpdateId']

                    U = update.get('U')
                    u = update.get('u')

                    # 🎯 关键检查：新消息是否符合同步条件
                    if U is not None and u is not None and U <= last_update_id <= u:
                        self.logger.info(f"🎉 {symbol}收到符合条件的新消息: U={U} <= lastUpdateId={last_update_id} <= u={u}")
                        self.logger.info(f"   - 立即尝试同步...")

                        # 立即尝试同步
                        sync_success = await self._sync_cached_messages(symbol, last_update_id)
                        if sync_success:
                            await self._trigger_running_phase(symbol)
            elif current_state == InitializationState.RUNNING:
                # 第四阶段：正常处理
                success = await self._enqueue_message(symbol, update)
                if not success:
                    # 🔧 修复：在停止过程中，入队失败是正常的，不需要警告
                    if self.message_processors_running:
                        self.logger.warning(f"⚠️ {symbol}消息入队失败")
                    else:
                        self.logger.debug(f"🔍 {symbol}消息入队失败（管理器停止中）")
                else:
                    self.stats['updates_received'] += 1
            else:
                # 第二阶段：继续缓存消息
                await self._cache_message(symbol, update, receive_time)

        except Exception as e:
            self.logger.error(f"❌ 处理{symbol}WebSocket更新失败", error=str(e), exc_info=True)
            self.stats['errors'] += 1

    async def _cache_message(self, symbol: str, update: dict, receive_time: float):
        """🚀 第一阶段：缓存WebSocket消息"""
        try:
            if symbol not in self.message_cache:
                self.message_cache[symbol] = deque()
                self.cache_start_time[symbol] = receive_time
                self.logger.info(f"🚀 开始缓存{symbol}消息")

            # 创建缓存消息对象
            cached_msg = CachedMessage(update, receive_time)
            self.message_cache[symbol].append(cached_msg)

            # 限制缓存大小，避免内存溢出
            max_cache_size = 10000
            if len(self.message_cache[symbol]) > max_cache_size:
                self.message_cache[symbol].popleft()
                self.logger.warning(f"⚠️ {symbol}消息缓存达到上限，丢弃最旧消息")

            self.logger.debug(f"🔍 缓存消息: {symbol}, U={update.get('U')}, u={update.get('u')}, cache_size={len(self.message_cache[symbol])}")

            # 🎯 修复：只有在SUBSCRIBING状态时才检查缓存时间，避免重复触发快照
            current_state = self.init_states.get(symbol, InitializationState.SUBSCRIBING)
            if (current_state == InitializationState.SUBSCRIBING and
                receive_time - self.cache_start_time[symbol] >= self.cache_duration):
                await self._trigger_snapshot_phase(symbol)

        except Exception as e:
            self.logger.error(f"❌ 缓存{symbol}消息失败: {e}", exc_info=True)

    async def _trigger_snapshot_phase(self, symbol: str):
        """🚀 第二阶段：触发API快照获取"""
        try:
            self.init_states[symbol] = InitializationState.SNAPSHOT
            self.logger.info(f"🚀 {symbol}进入快照获取阶段，缓存消息数量: {len(self.message_cache[symbol])}")

            # 获取API快照 - 添加重试机制
            max_retries = 3
            retry_delay = 2.0

            for attempt in range(max_retries):
                snapshot_success = await self._get_api_snapshot(symbol)
                if snapshot_success:
                    # 快照获取成功，进入第三阶段
                    await self._trigger_sync_phase(symbol)
                    return
                else:
                    # 快照获取失败
                    if attempt < max_retries - 1:
                        self.logger.warning(f"⚠️ {symbol}快照获取失败，{retry_delay}秒后重试 (第{attempt + 1}/{max_retries}次)")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5  # 指数退避
                    else:
                        self.logger.error(f"❌ {symbol}快照获取失败，已达最大重试次数，重新开始初始化")
                        await self._reset_initialization(symbol)

        except Exception as e:
            self.logger.error(f"❌ {symbol}快照获取阶段失败: {e}", exc_info=True)
            await self._reset_initialization(symbol)

    async def _get_api_snapshot(self, symbol: str) -> bool:
        """🚀 按Binance官方文档获取API快照数据 - 并发安全版本"""
        # 🔒 并发控制：确保每个symbol只有一个快照获取进程
        if symbol not in self.snapshot_locks:
            self.snapshot_locks[symbol] = asyncio.Lock()

        async with self.snapshot_locks[symbol]:
            try:
                # 检查是否已经在获取快照
                if self.snapshot_in_progress.get(symbol, False):
                    self.logger.warning(f"⚠️ {symbol}快照获取已在进行中，跳过重复请求")
                    return False

                self.snapshot_in_progress[symbol] = True
                self.logger.info(f"📸 获取{symbol}API快照 [并发安全]")

                # 🎯 按官方文档：检查缓存的第一个消息的U值
                cached_messages = self.message_cache.get(symbol, deque())
                first_cached_U = None
                if cached_messages:
                    first_msg = cached_messages[0]
                    first_cached_U = first_msg.U
                    self.logger.info(f"🔍 {symbol}第一个缓存消息的U值: {first_cached_U}")

                # 构建API URL
                url = f"{self.api_base_url}/api/v3/depth"
                params = {
                    'symbol': symbol,
                    'limit': min(self.depth_limit, 5000)  # Binance现货最大5000档
                }

                # 🔍 记录API请求信息
                self.logger.info(f"📡 API请求: {url}?symbol={symbol}&limit={params['limit']}")

                # 发起API请求
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        response_time = time.time()

                        if response.status == 200:
                            snapshot_data = await response.json()
                            last_update_id = snapshot_data.get('lastUpdateId')

                            # 🔍 记录响应信息
                            self.logger.info(f"📥 API响应: status=200, lastUpdateId={last_update_id}")

                            # 🎯 按官方文档检查：如果快照的lastUpdateId <= 第一个缓存消息的U值，需要重新获取
                            if first_cached_U is not None and last_update_id <= first_cached_U:
                                self.logger.warning(f"⚠️ {symbol}快照过旧: lastUpdateId={last_update_id} <= 第一个缓存U={first_cached_U}")
                                self.logger.warning(f"   - 按官方文档，需要重新获取快照")
                                return False

                            # 🔒 原子性保存快照数据
                            self.snapshot_data[symbol] = {
                                'data': snapshot_data,
                                'timestamp': response_time,
                                'lastUpdateId': last_update_id
                            }

                            self.logger.info(f"✅ {symbol}快照获取成功, lastUpdateId={last_update_id}")
                            if first_cached_U is not None:
                                self.logger.info(f"   - 快照检查通过: lastUpdateId={last_update_id} > 第一个缓存U={first_cached_U}")
                            return True
                        else:
                            self.logger.error(f"❌ {symbol}快照获取失败: HTTP {response.status}")
                            return False

            except Exception as e:
                self.logger.error(f"❌ {symbol}快照获取异常: {e}", exc_info=True)
                return False
            finally:
                # 🔒 确保清理进行中标志
                self.snapshot_in_progress[symbol] = False

    async def _trigger_sync_phase(self, symbol: str):
        """🎯 第三阶段：消息同步和验证 - 支持持续等待新消息"""
        try:
            self.init_states[symbol] = InitializationState.SYNCING
            self.logger.info(f"🚀 {symbol}进入消息同步阶段")

            snapshot_info = self.snapshot_data[symbol]
            last_update_id = snapshot_info['lastUpdateId']

            # 🎯 用户建议：尝试同步，如果失败就继续等待新消息
            sync_success = await self._sync_cached_messages(symbol, last_update_id)

            if sync_success:
                # 同步成功，进入第四阶段
                await self._trigger_running_phase(symbol)
            else:
                # 🎯 用户建议：同步失败不要重新开始，而是继续等待新消息
                self.logger.info(f"💡 {symbol}同步暂未成功，继续等待新的WebSocket消息...")
                self.logger.info(f"   - 保持SYNCING状态，等待符合条件的event")
                # 不调用 _reset_initialization，保持当前状态继续等待

        except Exception as e:
            self.logger.error(f"❌ {symbol}消息同步阶段失败: {e}", exc_info=True)
            await self._reset_initialization(symbol)

    async def _sync_cached_messages(self, symbol: str, last_update_id: int) -> bool:
        """🎯 按照用户建议的正确逻辑：如果快照太新就等待新消息"""
        try:
            cached_messages = self.message_cache[symbol]
            self.logger.info(f"🔍 {symbol}开始同步，快照lastUpdateId={last_update_id}, 缓存消息数={len(cached_messages)}")

            if not cached_messages:
                self.logger.warning(f"⚠️ {symbol}没有缓存消息，等待新消息...")
                return False

            # 🔍 分析缓存消息范围
            first_msg = cached_messages[0]
            last_msg = cached_messages[-1]
            self.logger.info(f"🔍 {symbol}缓存消息范围:")
            self.logger.info(f"   - 第一条消息: U={first_msg.U}, u={first_msg.u}")
            self.logger.info(f"   - 最后一条消息: U={last_msg.U}, u={last_msg.u}")
            self.logger.info(f"   - 快照lastUpdateId: {last_update_id}")

            # 🎯 用户建议的核心逻辑1：检查快照是否太早
            if last_update_id < first_msg.U:
                self.logger.warning(f"⚠️ {symbol}快照太早: lastUpdateId={last_update_id} < 第一个U={first_msg.U}")
                self.logger.warning(f"   - 无法找到匹配的event，需要重新获取快照")
                return False

            # 🎯 用户建议的核心逻辑2：如果快照太新，就等待新消息！
            if last_update_id > last_msg.u:
                self.logger.info(f"💡 {symbol}快照较新: lastUpdateId={last_update_id} > 最后消息u={last_msg.u}")
                self.logger.info(f"   - 按用户建议：继续等待新的WebSocket消息...")
                self.logger.info(f"   - 等待符合条件的event: U <= {last_update_id} <= u")
                return False  # 返回False让系统继续等待，而不是重新获取快照

            # 🎯 核心逻辑3：在现有消息中查找匹配的event
            sync_start_index = None
            discarded_count = 0

            for i, cached_msg in enumerate(cached_messages):
                U = cached_msg.U
                u = cached_msg.u

                if U is None or u is None:
                    continue

                # 丢弃过期event：lastUpdateId > u
                if last_update_id > u:
                    discarded_count += 1
                    self.logger.debug(f"🗑️ {symbol}丢弃过期event{i}: lastUpdateId={last_update_id} > u={u}")
                    continue

                # 🎯 核心逻辑4：找到匹配的event：U <= lastUpdateId <= u
                if U <= last_update_id <= u:
                    sync_start_index = i
                    self.logger.info(f"✅ {symbol}找到匹配event: index={i}")
                    self.logger.info(f"   - 验证: U={U} <= lastUpdateId={last_update_id} <= u={u} ✅")
                    break

            if sync_start_index is None:
                self.logger.info(f"💡 {symbol}暂未找到匹配的event，继续等待新消息...")
                self.logger.info(f"   - 已丢弃{discarded_count}条过期消息")
                return False  # 继续等待，不重新获取快照

            # 🎯 核心逻辑5：初始化订单簿并应用匹配的event
            await self._initialize_orderbook_from_snapshot(symbol)

            # 获取订单簿状态
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states[unique_key]

            # 应用从匹配event开始的所有消息
            applied_count = 0
            for i in range(sync_start_index, len(cached_messages)):
                cached_msg = cached_messages[i]
                try:
                    # 🎯 核心逻辑6：应用event并更新本地lastUpdateId = event的u
                    await self._apply_event_and_update_id(symbol, cached_msg, state)
                    applied_count += 1
                except Exception as e:
                    self.logger.error(f"❌ {symbol}应用event失败: {e}")
                    return False

            self.logger.info(f"✅ {symbol}同步完成: 丢弃{discarded_count}条，应用{applied_count}条")
            return True

        except Exception as e:
            self.logger.error(f"❌ {symbol}消息同步失败: {e}", exc_info=True)
            return False

    async def _apply_event_and_update_id(self, symbol: str, cached_msg: CachedMessage, state: OrderBookState):
        """🎯 按照用户理解应用event并更新本地lastUpdateId"""
        try:
            update = cached_msg.message
            U = cached_msg.U
            u = cached_msg.u

            self.logger.debug(f"🔄 {symbol}应用event: U={U}, u={u}, 当前lastUpdateId={state.last_update_id}")

            # 应用订单簿更新
            await self._apply_orderbook_update(symbol, update, state)

            # 🎯 核心：更新本地lastUpdateId = event的u
            old_last_update_id = state.last_update_id
            state.last_update_id = u

            self.logger.debug(f"✅ {symbol}event应用成功: lastUpdateId {old_last_update_id} → {u}")

        except Exception as e:
            self.logger.error(f"❌ {symbol}应用event失败: {e}")
            raise

    async def _apply_orderbook_update(self, symbol: str, update: dict, state: OrderBookState):
        """应用订单簿更新数据"""
        try:
            if not state.local_orderbook:
                self.logger.error(f"❌ {symbol}本地订单簿不存在")
                return

            # 获取当前订单簿数据
            current_bids = {bid.price: bid.quantity for bid in state.local_orderbook.bids}
            current_asks = {ask.price: ask.quantity for ask in state.local_orderbook.asks}

            # 应用买单更新
            for price_str, qty_str in update.get('b', []):
                price = Decimal(price_str)
                qty = Decimal(qty_str)
                if qty == 0:
                    current_bids.pop(price, None)  # 删除
                else:
                    current_bids[price] = qty  # 更新

            # 应用卖单更新
            for price_str, qty_str in update.get('a', []):
                price = Decimal(price_str)
                qty = Decimal(qty_str)
                if qty == 0:
                    current_asks.pop(price, None)  # 删除
                else:
                    current_asks[price] = qty  # 更新

            # 排序并限制深度
            max_depth = 400
            sorted_bids = sorted(current_bids.items(), key=lambda x: x[0], reverse=True)[:max_depth]
            sorted_asks = sorted(current_asks.items(), key=lambda x: x[0])[:max_depth]

            # 更新订单簿
            state.local_orderbook.bids = [PriceLevel(price=price, quantity=qty) for price, qty in sorted_bids]
            state.local_orderbook.asks = [PriceLevel(price=price, quantity=qty) for price, qty in sorted_asks]
            state.local_orderbook.timestamp = datetime.now(timezone.utc)

        except Exception as e:
            self.logger.error(f"❌ {symbol}应用订单簿更新失败: {e}")
            raise

    async def _initialize_orderbook_from_snapshot(self, symbol: str):
        """🚀 从快照初始化订单簿"""
        try:
            snapshot_info = self.snapshot_data[symbol]
            snapshot_data = snapshot_info['data']

            # 创建订单簿状态
            unique_key = self._get_unique_key(symbol)
            if unique_key not in self.orderbook_states:
                self.orderbook_states[unique_key] = OrderBookState(
                    symbol=symbol,
                    exchange="binance_spot"
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
                exchange_name="binance_spot",
                market_type="spot",
                bids=bids,
                asks=asks,
                timestamp=datetime.now(timezone.utc)
            )

            state.is_synced = True
            self.logger.info(f"✅ {symbol}订单簿初始化完成，lastUpdateId={state.last_update_id}")

        except Exception as e:
            self.logger.error(f"❌ {symbol}订单簿初始化失败: {e}", exc_info=True)
            raise

    async def _apply_cached_message(self, symbol: str, cached_msg: CachedMessage):
        """🚀 应用缓存的消息"""
        try:
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states[unique_key]

            # 验证序列号
            U = cached_msg.U
            u = cached_msg.u
            expected_first_id = state.last_update_id + 1

            if U <= expected_first_id <= u:
                # 序列号连续，应用更新
                await self._apply_update_optimized(symbol, cached_msg.message, state)
                state.last_update_id = u
                self.logger.debug(f"✅ {symbol}应用缓存消息: U={U}, u={u}")
            else:
                # 序列号不连续
                self.logger.warning(f"⚠️ {symbol}缓存消息序列号不连续: expected={expected_first_id}, U={U}, u={u}")
                raise Exception(f"序列号不连续: expected={expected_first_id}, U={U}, u={u}")

        except Exception as e:
            self.logger.error(f"❌ {symbol}应用缓存消息失败: {e}", exc_info=True)
            raise

    async def _trigger_running_phase(self, symbol: str):
        """🚀 第四阶段：进入正常运行模式"""
        try:
            self.init_states[symbol] = InitializationState.RUNNING
            self.logger.info(f"🚀 {symbol}进入正常运行模式")

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

            self.logger.info(f"✅ {symbol}分阶段初始化完成，进入正常运行模式")

        except Exception as e:
            self.logger.error(f"❌ {symbol}进入运行模式失败: {e}", exc_info=True)

    async def _reset_initialization(self, symbol: str):
        """🚀 重置初始化状态，重新开始"""
        try:
            self.logger.warning(f"🔄 {symbol}重置初始化状态")

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

            self.logger.info(f"🔄 {symbol}初始化状态已重置，将重新开始分阶段初始化")

        except Exception as e:
            self.logger.error(f"❌ {symbol}重置初始化失败: {e}", exc_info=True)
    
    async def _apply_update(self, symbol: str, update: dict, state: OrderBookState):
        """应用增量更新 - 🔧 统一：借鉴OKX成功模式"""
        try:
            if not state.is_synced or not state.local_orderbook:
                self.logger.warning(f"⚠️ {symbol}未同步，跳过更新")
                return

            # 🔧 统一：先用原始数据验证序列号
            is_valid, error_msg = self._validate_message_sequence(symbol, update, state)
            if not is_valid:
                self.logger.warning(f"⚠️ Binance现货更新序列号验证失败: {symbol}，回滚更新")
                self.logger.warning(f"🔍 序列号验证失败: {error_msg}")
                # 触发重新同步
                await self._trigger_resync(symbol, f"序列号验证失败: {error_msg}")
                return

            # 获取当前订单簿的副本
            current_bids = {bid.price: bid.quantity for bid in state.local_orderbook.bids}
            current_asks = {ask.price: ask.quantity for ask in state.local_orderbook.asks}

            # 应用买单更新
            for price_str, qty_str in update.get('b', []):
                price = Decimal(price_str)
                qty = Decimal(qty_str)

                if qty == 0:
                    # 删除价格档位
                    current_bids.pop(price, None)
                else:
                    # 更新价格档位
                    current_bids[price] = qty

            # 应用卖单更新
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
            new_bids = [PriceLevel(price=price, quantity=quantity) for price, quantity in current_bids.items()]
            new_asks = [PriceLevel(price=price, quantity=quantity) for price, quantity in current_asks.items()]

            new_bids.sort(key=lambda x: x.price, reverse=True)
            new_asks.sort(key=lambda x: x.price)

            # 创建更新后的订单簿
            updated_orderbook = EnhancedOrderBook(
                exchange_name="binance_spot",
                symbol_name=symbol,
                market_type="spot",
                last_update_id=update.get('u'),
                bids=new_bids,
                asks=new_asks,
                timestamp=datetime.now(),
                update_type=OrderBookUpdateType.UPDATE,
                first_update_id=update.get('U'),
                prev_update_id=state.last_update_id,
                depth_levels=len(new_bids) + len(new_asks)
            )

            # 更新状态
            state.local_orderbook = updated_orderbook
            state.last_update_id = update.get('u')
            state.last_update_time = datetime.now(timezone.utc)

            self.stats['updates_applied'] += 1

            self.logger.debug(f"✅ {symbol}更新应用成功")

            # 发布到NATS
            await self.publish_orderbook(symbol, updated_orderbook)

        except Exception as e:
            self.logger.error(f"❌ 应用{symbol}更新失败", error=str(e), exc_info=True)
            state.is_synced = False

    async def _fetch_initial_snapshot(self, symbol: str) -> Optional['EnhancedOrderBook']:
        """获取初始快照"""
        try:
            snapshot = await self._fetch_api_snapshot(symbol)
            if not snapshot:
                return None

            # 转换为EnhancedOrderBook格式
            from ..data_types import EnhancedOrderBook, PriceLevel

            enhanced_orderbook = EnhancedOrderBook(
                exchange_name="binance_spot",
                symbol_name=symbol,
                market_type="spot",
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
        Binance现货特定的初始化逻辑

        🔧 修复：增强日志和错误处理，确保初始化过程可见
        """
        try:
            self.logger.info("🚀 开始Binance现货OrderBook管理器初始化")

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

            # 步骤4：串行初始化所有交易对订单簿（避免快照混淆）
            self.logger.info("📋 步骤4：开始串行初始化订单簿（避免快照混淆）")

            # 🎯 用户发现的问题：并发初始化会导致快照混淆
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

            self.logger.info("🎉 Binance现货OrderBook管理器初始化完成")

        except Exception as e:
            self.logger.error("❌ Binance现货特定初始化失败", error=str(e), exc_info=True)
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
        """🚀 分阶段初始化：触发重新同步"""
        try:
            self.logger.info(f"🔄 触发{symbol}重新同步: {reason}")

            # 🚀 使用分阶段初始化重新同步
            await self._reset_initialization(symbol)

            # 🚀 清空消息队列，避免积压的旧消息
            if symbol in self.message_queues:
                queue = self.message_queues[symbol]
                cleared_count = 0
                while not queue.empty():
                    try:
                        queue.get_nowait()
                        queue.task_done()
                        cleared_count += 1
                    except asyncio.QueueEmpty:
                        break
                if cleared_count > 0:
                    self.logger.info(f"🧹 清空{symbol}消息队列: {cleared_count}条消息")

        except Exception as e:
            self.logger.error(f"❌ {symbol}重新同步失败", error=str(e), exc_info=True)
    

    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.stats.copy()

    async def _perform_reconnection(self) -> bool:
        """
        执行Binance现货WebSocket重连操作

        Returns:
            bool: 重连是否成功
        """
        try:
            self.logger.info("🔄 开始Binance现货WebSocket重连")

            # Binance现货重连逻辑：
            # 1. 重连由WebSocket客户端自动处理
            # 2. 管理器需要重置订单簿状态
            # 3. 重新获取快照数据

            # 重置所有订单簿状态
            for symbol, state in self.orderbook_states.items():
                state.is_synced = False
                state.local_orderbook = None
                state.last_update_id = 0
                self.logger.debug(f"🔄 重置Binance现货订单簿状态: {symbol}")

            # 重置错误计数器
            self._reset_error_counters()

            self.logger.info("✅ Binance现货重连准备完成，等待WebSocket重新连接")
            return True

        except Exception as e:
            self.logger.error(f"❌ Binance现货重连失败: {e}")
            return False

    async def _exchange_specific_resync(self, symbol: str, reason: str):
        """
        Binance现货特定的重新同步逻辑

        Args:
            symbol: 交易对
            reason: 重新同步原因
        """
        try:
            self.logger.info(f"🔄 Binance现货重新同步: {symbol}, 原因: {reason}")

            # Binance现货重新同步策略：
            # 1. 重置订单簿状态
            # 2. 重新获取API快照
            # 3. 等待WebSocket增量更新

            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if state:
                state.is_synced = False
                state.local_orderbook = None
                state.last_update_id = 0
                self.logger.debug(f"🔄 重置Binance现货订单簿状态: {symbol}")

            # 重新获取快照
            try:
                snapshot = await self._fetch_initial_snapshot(symbol)
                if snapshot:
                    state.local_orderbook = snapshot
                    state.last_update_id = snapshot.last_update_id
                    state.is_synced = True
                    self.logger.info(f"✅ Binance现货快照重新获取成功: {symbol}")
                else:
                    self.logger.warning(f"⚠️ Binance现货快照重新获取失败: {symbol}")
            except Exception as e:
                self.logger.error(f"❌ Binance现货快照重新获取异常: {symbol}, error={e}")

            self.logger.info(f"✅ Binance现货重新同步完成: {symbol}")

        except Exception as e:
            self.logger.error(f"❌ Binance现货重新同步失败: {symbol}, error={e}")

    async def _exchange_specific_cleanup(self):
        """Binance现货特定清理"""
        self.logger.info("🔧 Binance现货特定清理完成")
