"""
OKX现货订单簿管理器

基于OKX官方WebSocket API文档的精确实现：
- WebSocket订阅时自动接收快照（prevSeqId=-1）
- 严格区分snapshot和update消息
- 使用seqId/prevSeqId进行序列验证
- 支持CRC32 checksum验证（可选）
"""

from typing import Dict, List, Optional, Any
import asyncio
import time
from datetime import datetime
from decimal import Decimal
import aiohttp
from structlog import get_logger

from .base_orderbook_manager import BaseOrderBookManager
from ..data_types import EnhancedOrderBook, OrderBookState, PriceLevel, OrderBookUpdateType


from exchanges.common.ws_message_utils import unwrap_combined_stream_message

class OKXSpotOrderBookManager(BaseOrderBookManager):
    """OKX现货订单簿管理器"""

    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        super().__init__(
            exchange="okx_spot",
            market_type="spot",
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # OKX特定配置
        self.base_url = "https://www.okx.com"
        self.checksum_validation_enabled = True  # 启用checksum验证

        # 🔧 新增：消息缓冲区用于处理乱序消息
        # 校验失败阈值与计数（用于降噪）
        self.checksum_warning_threshold = config.get('checksum_warning_threshold', 3)
        self._checksum_fail_counts: Dict[str, int] = {}

        self.message_buffers: Dict[str, List[dict]] = {}
        self.buffer_max_size = config.get('buffer_max_size', 100)  # 缓冲区最大大小
        self.buffer_timeout = config.get('buffer_timeout', 5.0)    # 缓冲超时时间(秒)

        self.logger.info("🏗️ OKX现货订单簿管理器初始化完成")

    def _get_snapshot_depth(self) -> int:
        """OKX现货快照深度：400档"""
        return 400

    def _get_websocket_depth(self) -> int:
        """OKX现货WebSocket深度：400档"""
        return 400

    async def initialize_orderbook_states(self):
        """初始化订单簿状态"""
        self.logger.info("🔧 初始化OKX现货订单簿状态")

        for symbol in self.symbols:
            unique_key = self._get_unique_key(symbol)
            self.orderbook_states[unique_key] = OrderBookState(
                symbol=symbol,
                exchange="okx_spot"
            )
            # 初始化缓冲区与等待快照时间
            self.message_buffers[symbol] = []
            # 记录等待快照起始时间，用于超时重订阅
            if not hasattr(self, 'waiting_for_snapshot_since'):
                self.waiting_for_snapshot_since = {}
            self.waiting_for_snapshot_since[symbol] = None
            self.logger.info(f"✅ 初始化状态: {symbol} -> {unique_key}")

    async def process_websocket_message(self, symbol: str, message: dict):
        """处理OKX WebSocket消息"""
        try:
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if not state:
                self.logger.warning(f"⚠️ {symbol}状态不存在，执行惰性初始化")
                self.orderbook_states[unique_key] = OrderBookState(symbol=symbol, exchange="okx_spot")
                state = self.orderbook_states[unique_key]
            # 统一预解包（若未来OKX也采用外层包裹结构）
            message = unwrap_combined_stream_message(message)

            # 根据OKX官方文档解析action字段
            action = message.get('action')
            if action is None:
                self.logger.error(f"❌ OKX消息缺少action字段: {symbol}")
                return

            seq_id = message.get('seqId')
            prev_seq_id = message.get('prevSeqId')

            self.logger.debug(f"🔍 OKX现货消息: {symbol}, action={action}, seqId={seq_id}, prevSeqId={prev_seq_id}")

            # 验证消息序列
            is_valid, error_msg = self._validate_message_sequence(symbol, message, state)
            if not is_valid:
                await self._handle_error(symbol, 'sequence', error_msg)
                return
            else:
                # 序列验证成功
                await self._on_successful_operation(symbol, 'sequence')

            # 快照/更新处理逻辑
            if action == 'snapshot':
                await self._apply_snapshot(symbol, message, state)
                self.stats['snapshots_applied'] += 1
                await self._on_successful_operation(symbol, 'snapshot')

                # 快照应用后，尝试从缓冲区回放连续更新
                buffered = self._process_buffered_messages(symbol, state)
                for buffered_msg in buffered:
                    try:
                        # 回放缓冲时不发布，避免发布过期事件造成延迟超阈
                        await self._apply_update(symbol, buffered_msg, state, publish=False)
                        self.stats['updates_applied'] += 1
                    except Exception as e:
                        await self._handle_error(symbol, 'processing', f"回放缓冲消息失败: {e}")

                # 回放完成后仅发布最终状态，确保事件时间接近当前
                if state and state.local_orderbook:
                    await self.publish_orderbook(symbol, state.local_orderbook)

                # 清除等待标记
                self.waiting_for_snapshot_since[symbol] = None

            elif action == 'update':
                # 若本地订单簿尚未初始化，则先缓冲并在必要时触发重订阅
                if not state.local_orderbook:
                    # 记录首次等待快照的时间
                    if not self.waiting_for_snapshot_since.get(symbol):
                        self.waiting_for_snapshot_since[symbol] = time.time()
                    self._buffer_message(symbol, message)

                    # 如超过缓冲超时仍未等到快照，尝试重订阅该symbol
                    waited = time.time() - (self.waiting_for_snapshot_since.get(symbol) or time.time())
                    # 采用较保守的阈值：buffer_timeout 的 2 倍
                    if waited >= max(2.0 * self.buffer_timeout, 5.0):
                        self.logger.warning(f"⏰ {symbol}等待快照超时，触发重订阅")
                        await self._resubscribe_symbol(symbol)
                        # 重置等待时间，避免频繁重订阅
                        self.waiting_for_snapshot_since[symbol] = time.time()
                    return

                # 已有本地订单簿，正常应用更新
                await self._apply_update(symbol, message, state)
                self.stats['updates_applied'] += 1
                await self._on_successful_operation(symbol, 'update')
            else:
                self.logger.error(f"❌ 无效的OKX action类型: {symbol}, action={action}")
                self.logger.error(f"❌ 根据OKX官方文档，有效的action类型只有: snapshot, update")
                await self._handle_error(symbol, 'processing', f"无效的action类型: {action}")
                return

        except Exception as e:
            await self._handle_error(symbol, 'processing', f"处理OKX现货消息失败: {e}", e)

    def _validate_message_sequence(self, symbol: str, message: dict, state: OrderBookState) -> tuple[bool, str]:
        """
        验证OKX消息序列

        根据OKX官方文档：
        1. 快照消息的prevSeqId为-1
        2. 增量消息的prevSeqId应该等于上一条消息的seqId
        3. 维护重启时可能出现seqId < prevSeqId的情况，需要重置验证
        """
        try:
            seq_id = message.get('seqId')
            prev_seq_id = message.get('prevSeqId')
            action = message.get('action')

            if seq_id is None:
                return False, "缺少seqId字段"

            if prev_seq_id is None:
                return False, "缺少prevSeqId字段"

            # 快照消息的prevSeqId为-1，直接通过验证
            if action == 'snapshot':
                if prev_seq_id != -1:
                    return False, f"快照消息prevSeqId应为-1，实际为{prev_seq_id}"
                self.logger.debug(f"📊 {symbol}收到快照消息，重置序列验证")
                return True, "快照消息验证通过"

            elif action == 'update':
                # 处理维护重启情况：seqId < prevSeqId
                if seq_id < prev_seq_id:
                    self.logger.warning(f"🔄 {symbol}检测到维护重启，重置序列验证: seqId={seq_id}, prevSeqId={prev_seq_id}")
                    # 重置状态，允许这次更新通过
                    state.last_update_id = 0
                    state.last_seq_id = None
                    return True, "维护重启，重置序列验证"

                # 第一条更新消息或重置后的消息
                if state.last_seq_id is None or state.last_update_id == 0:
                    return True, "首条更新消息"

                # 正常序列验证
                if prev_seq_id != (state.last_seq_id if state.last_seq_id is not None else state.last_update_id):
                    return False, f"序列不连续: 期望prevSeqId={(state.last_seq_id if state.last_seq_id is not None else state.last_update_id)}, 实际={prev_seq_id}"

                return True, "更新消息验证通过"

            else:
                return False, f"未知action类型: {action}"

        except Exception as e:
            return False, f"序列验证异常: {str(e)}"

    def _buffer_message(self, symbol: str, message: dict) -> None:
        """将消息添加到缓冲区"""
        if symbol not in self.message_buffers:
            self.message_buffers[symbol] = []

        buffer = self.message_buffers[symbol]
        buffer.append({
            'message': message,
            'timestamp': time.time()
        })

        # 按prevSeqId字段排序（OKX）
        buffer.sort(key=lambda x: x['message'].get('prevSeqId', 0))

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
            prev_seq_id = message.get('prevSeqId')

            # 检查是否是期望的下一个消息
            if prev_seq_id == (state.last_seq_id if state.last_seq_id is not None else state.last_update_id):
                processed_messages.append(message)
                state.last_seq_id = message.get('seqId')
                state.last_update_id = int(state.last_seq_id or 0)
                buffer.pop(0)
                self.logger.debug(f"🔄 {symbol} 从缓冲区处理消息: prevSeqId={prev_seq_id}, seqId={message.get('seqId')}")
            else:
                break  # 不连续，停止处理

        return processed_messages

    async def _apply_snapshot(self, symbol: str, snapshot_data: dict, state: OrderBookState):
        """应用OKX快照数据"""
        try:
            self.logger.debug(f"📊 应用OKX现货快照: {symbol}")

            # 解析快照数据
            bids_data = snapshot_data.get('bids', [])
            asks_data = snapshot_data.get('asks', [])
            timestamp_ms = snapshot_data.get('ts', str(int(time.time() * 1000)))
            seq_id = snapshot_data.get('seqId')

            # 🔧 统一：先用原始数据验证checksum
            if self.checksum_validation_enabled:
                calculated_checksum = self._calculate_okx_checksum_from_raw_data(bids_data, asks_data)
                expected_checksum = str(snapshot_data.get('checksum', ''))

                if calculated_checksum == expected_checksum:
                    self.logger.debug(f"✅ OKX现货快照checksum验证成功: {symbol}, checksum={expected_checksum}")
                else:
                    self.logger.warning(f"⚠️ OKX现货快照checksum验证失败: {symbol}, 期望={expected_checksum}, 计算={calculated_checksum}")

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

            # 创建快照
            # 使用事件时间(ts, ms)作为timestamp
            from datetime import timezone
            event_dt = datetime.utcfromtimestamp(int(timestamp_ms) / 1000).replace(tzinfo=timezone.utc)
            snapshot = EnhancedOrderBook(
                exchange_name="okx_spot",
                symbol_name=symbol,
                market_type="spot",
                last_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                bids=bids,
                asks=asks,
                timestamp=event_dt,  # 统一使用事件时间
                update_type=OrderBookUpdateType.SNAPSHOT,
                first_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                prev_update_id=int(snapshot_data.get('prevSeqId', -1)) if isinstance(snapshot_data.get('prevSeqId', -1), (int, str)) else -1,
                depth_levels=len(bids) + len(asks)
            )

            # 更新状态
            state.local_orderbook = snapshot
            state.last_seq_id = seq_id
            state.last_update_id = int(seq_id or 0)
            state.last_snapshot_time = datetime.now()
            state.is_synced = True

            self.logger.debug(f"✅ OKX现货快照应用成功: {symbol}, bids={len(bids)}, asks={len(asks)}, seqId={seq_id}")

            # 发布到NATS
            await self.publish_orderbook(symbol, snapshot)

        except Exception as e:
            state.is_synced = False
            await self._handle_error(symbol, 'processing', f"应用OKX现货快照失败: {e}", e)

    async def _apply_update(self, symbol: str, update_data: dict, state: OrderBookState, publish: bool = True):
        """应用OKX增量更新

        Args:
            publish: 是否在本次应用后立刻发布到NATS，回放缓冲时应为False
        """
        try:
            if not state.local_orderbook:
                self.logger.warning(f"⚠️ {symbol}本地订单簿未初始化，忽略更新")
                return

            # 解析更新数据
            bids_data = update_data.get('bids', [])
            asks_data = update_data.get('asks', [])
            timestamp_ms = update_data.get('ts', str(int(time.time() * 1000)))
            seq_id = update_data.get('seqId')

            # 备份当前订单簿（用于回滚）
            backup_bids = {level.price: level.quantity for level in state.local_orderbook.bids}
            backup_asks = {level.price: level.quantity for level in state.local_orderbook.asks}

            # 应用增量更新
            current_bids = {level.price: level.quantity for level in state.local_orderbook.bids}
            current_asks = {level.price: level.quantity for level in state.local_orderbook.asks}

            # 更新买盘
            for bid_data in bids_data:
                price = Decimal(str(bid_data[0]))
                quantity = Decimal(str(bid_data[1]))

                if quantity == 0:
                    # 删除价位
                    current_bids.pop(price, None)
                else:
                    # 更新价位
                    current_bids[price] = quantity

            # 更新卖盘
            for ask_data in asks_data:
                price = Decimal(str(ask_data[0]))
                quantity = Decimal(str(ask_data[1]))

                if quantity == 0:
                    # 删除价位
                    current_asks.pop(price, None)
                else:
                    # 更新价位
                    current_asks[price] = quantity

            # 🔧 统一：先验证checksum，然后再转换数据格式
            if self.checksum_validation_enabled:
                # 构建更新后的原始数据格式用于checksum验证
                updated_bids_raw = [[str(price), str(quantity)] for price, quantity in current_bids.items()]
                updated_asks_raw = [[str(price), str(quantity)] for price, quantity in current_asks.items()]

                # 排序原始数据
                updated_bids_raw.sort(key=lambda x: float(x[0]), reverse=True)
                updated_asks_raw.sort(key=lambda x: float(x[0]))

                calculated_checksum = self._calculate_okx_checksum_from_raw_data(updated_bids_raw, updated_asks_raw)
                expected_checksum = str(update_data.get('checksum', ''))

                if calculated_checksum != expected_checksum:
                    # 记录失败计数并分级告警
                    cnt = self._checksum_fail_counts.get(symbol, 0) + 1
                    self._checksum_fail_counts[symbol] = cnt

                    if cnt >= self.checksum_warning_threshold:
                        # 达到阈值，触发完整重新同步
                        self.logger.warning(f"⚠️ OKX现货更新checksum验证连续失败(第{cnt}次≥阈值{self.checksum_warning_threshold}): {symbol}，触发完整重新同步")
                        await self._handle_error(symbol, 'checksum', f"OKX现货更新checksum验证失败: 期望={expected_checksum}, 计算={calculated_checksum}")
                        await self._trigger_complete_resync(symbol, "checksum连续失败")
                    else:
                        # 降噪：低于阈值时仅 info，且提示自动回滚
                        self.logger.info(f"⚠️ OKX现货更新checksum验证失败(第{cnt}次<阈值{self.checksum_warning_threshold})，已回滚: {symbol}")
                        await self._handle_error(symbol, 'checksum', f"OKX现货更新checksum验证失败: 期望={expected_checksum}, 计算={calculated_checksum}")
                    return
                else:
                    # 清零失败计数
                    self._checksum_fail_counts[symbol] = 0
                    await self._on_successful_operation(symbol, 'checksum')
                    self.logger.debug(f"✅ OKX现货更新checksum验证成功: {symbol}, checksum={expected_checksum}")

            # 转换为PriceLevel列表并排序
            new_bids = [PriceLevel(price=p, quantity=q) for p, q in current_bids.items()]
            new_asks = [PriceLevel(price=p, quantity=q) for p, q in current_asks.items()]

            new_bids.sort(key=lambda x: x.price, reverse=True)
            new_asks.sort(key=lambda x: x.price)

            # 创建更新后的订单簿
            # 使用事件时间(ts, ms)作为timestamp
            from datetime import timezone
            event_dt = datetime.utcfromtimestamp(int(timestamp_ms) / 1000).replace(tzinfo=timezone.utc)
            updated_orderbook = EnhancedOrderBook(
                exchange_name="okx_spot",
                symbol_name=symbol,
                market_type="spot",
                last_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                bids=new_bids,
                asks=new_asks,
                timestamp=event_dt,  # 统一使用事件时间
                update_type=OrderBookUpdateType.UPDATE,
                first_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                prev_update_id=int(update_data.get('prevSeqId')) if update_data.get('prevSeqId') is not None else (state.last_seq_id if state.last_seq_id is not None else state.last_update_id),
                depth_levels=len(new_bids) + len(new_asks)
            )

            # 更新状态
            state.local_orderbook = updated_orderbook
            state.last_seq_id = seq_id
            state.last_update_id = int(seq_id or 0)

            self.logger.debug(f"✅ OKX现货更新应用成功: {symbol}, seqId={seq_id}")

            # 发布到NATS（可控）
            if publish:
                await self.publish_orderbook(symbol, updated_orderbook)

        except Exception as e:
            await self._handle_error(symbol, 'processing', f"应用OKX现货更新失败: {e}", e)

    async def _trigger_complete_resync(self, symbol: str, reason: str):
        """
        触发完整重新同步

        Args:
            symbol: 交易对
            reason: 重新同步原因
        """
        try:
            self.logger.info(f"🔄 开始完整重新同步: {symbol}, 原因: {reason}")

            # 1. 清理所有相关状态
            unique_key = self._get_unique_key(symbol)
            if unique_key in self.orderbook_states:
                state = self.orderbook_states[unique_key]
                # 重置状态
                state.is_synced = False
                state.local_orderbook = None
                state.last_seq_id = None
                state.last_update_id = None
                state.snapshot_received = False

            # 2. 清零错误计数
            self._checksum_fail_counts[symbol] = 0

            # 3. 等待一段时间让WebSocket重新推送快照
            await asyncio.sleep(2.0)

            # 4. 记录重新同步事件
            self.stats['resync_count'] = self.stats.get('resync_count', 0) + 1

            self.logger.info(f"✅ 完整重新同步已触发: {symbol}, 等待新快照数据")

        except Exception as e:
            self.logger.error(f"❌ 触发完整重新同步失败: {symbol}, error={e}")

    def _calculate_okx_checksum_from_raw_data(self, bids_data: list, asks_data: list) -> str:
        """
        🔧 统一：使用原始数据计算OKX checksum
        与衍生品管理器保持完全一致的实现
        """
        try:
            import zlib

            # 取前25档并保持原始字符串格式
            bids = []
            for bid_data in bids_data[:25]:
                price_str = str(bid_data[0])
                quantity_str = str(bid_data[1])
                if float(quantity_str) > 0:
                    bids.append((price_str, quantity_str, float(price_str)))

            asks = []
            for ask_data in asks_data[:25]:
                price_str = str(ask_data[0])
                quantity_str = str(ask_data[1])
                if float(quantity_str) > 0:
                    asks.append((price_str, quantity_str, float(price_str)))

            # 排序
            bids.sort(key=lambda x: x[2], reverse=True)  # 买盘从高到低
            asks.sort(key=lambda x: x[2])  # 卖盘从低到高

            # 构建校验字符串
            checksum_parts = []
            min_len = min(len(bids), len(asks))

            # 交替排列
            for i in range(min_len):
                bid_price_str, bid_quantity_str, _ = bids[i]
                ask_price_str, ask_quantity_str, _ = asks[i]
                checksum_parts.extend([bid_price_str, bid_quantity_str, ask_price_str, ask_quantity_str])

            # 处理剩余部分
            if len(bids) > min_len:
                for i in range(min_len, len(bids)):
                    bid_price_str, bid_quantity_str, _ = bids[i]
                    checksum_parts.extend([bid_price_str, bid_quantity_str])
            elif len(asks) > min_len:
                for i in range(min_len, len(asks)):
                    ask_price_str, ask_quantity_str, _ = asks[i]
                    checksum_parts.extend([ask_price_str, ask_quantity_str])

            # 计算CRC32
            checksum_str = ':'.join(checksum_parts)
            crc32_value = zlib.crc32(checksum_str.encode('utf-8'))

            # 转换为32位有符号整型
            if crc32_value >= 2**31:
                crc32_value -= 2**32

            return str(crc32_value)

        except Exception as e:
            self.logger.error(f"❌ 计算原始数据checksum失败: {e}")
            return ""

    async def _fetch_initial_snapshot(self, symbol: str) -> Optional[EnhancedOrderBook]:
        """OKX现货不需要主动获取快照，WebSocket会自动推送"""
        self.logger.info(f"🔍 OKX现货等待WebSocket快照: {symbol}")
        return None

    async def _trigger_resync(self, symbol: str, reason: str):
        """触发重新同步"""
        try:
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if not state:
                return

            self.logger.info(f"🔄 触发OKX现货重新同步: {symbol}, 原因: {reason}")

            # 重置状态
            state.is_synced = False
            state.local_orderbook = None
            state.last_seq_id = None
            state.last_update_id = 0

            self.stats['resync_count'] += 1

            # OKX需要重新订阅WebSocket来获取新快照
            # 这里应该通知WebSocket客户端重新订阅
            self.logger.info(f"📡 需要重新订阅WebSocket获取快照: {symbol}")

        except Exception as e:
            self.logger.error(f"❌ 触发重新同步失败: {symbol}, error={e}")

    async def _exchange_specific_initialization(self):
        """OKX现货特定初始化"""
        try:
            # 🔧 修复：启动OKX WebSocket连接
            from exchanges.okx_websocket import OKXWebSocketManager

            # 创建OKX WebSocket管理器，传递配置以启用观测性功能
            self.okx_ws_client = OKXWebSocketManager(
                symbols=self.symbols,
                on_orderbook_update=self._handle_okx_websocket_update,
                market_type='spot',
                config=self.config  # 传递配置以启用ping_pong_verbose等观测性功能
            )

            self.logger.info("🌐 启动OKX现货WebSocket连接",
                           symbols=self.symbols,
                           ws_url=self.okx_ws_client.ws_url)

            # 启动WebSocket客户端
            self.okx_websocket_task = asyncio.create_task(self.okx_ws_client.start())

            # 初始化等待快照时间戳
            if not hasattr(self, 'waiting_for_snapshot_since'):
                self.waiting_for_snapshot_since = {s: None for s in self.symbols}

            self.logger.info("🔧 OKX现货特定初始化完成")

        except Exception as e:
            self.logger.error("❌ OKX现货WebSocket初始化失败", error=str(e), exc_info=True)
            raise


    async def _resubscribe_symbol(self, symbol: str):
        """为单个symbol执行OKX现货订单簿重订阅"""
        try:
            if hasattr(self, 'okx_ws_client') and self.okx_ws_client:
                # 先取消后订阅，确保服务端发送新的snapshot
                await self.okx_ws_client.unsubscribe_orderbook([symbol])
                await asyncio.sleep(0.2)
                await self.okx_ws_client.subscribe_orderbook([symbol])
                self.logger.info("📡 已重订阅OKX现货订单簿", symbol=symbol)
        except Exception as e:
            self.logger.error("❌ OKX现货重订阅失败", symbol=symbol, error=str(e))

    async def _handle_okx_websocket_update(self, symbol: str, update_data):
        """处理OKX WebSocket订单簿更新"""
        try:
            # 🔧 使用基类提供的标准接口
            await self.handle_websocket_message(symbol, update_data)

        except Exception as e:
            self.logger.error(f"❌ OKX WebSocket回调失败: {symbol}, error={e}")

    async def _exchange_specific_cleanup(self):
        """OKX现货特定清理"""
        try:
            # 停止OKX WebSocket客户端
            if hasattr(self, 'okx_ws_client') and self.okx_ws_client:
                await self.okx_ws_client.stop()
                self.logger.info("🔌 OKX WebSocket连接已关闭")

            # 取消WebSocket任务
            if hasattr(self, 'okx_websocket_task') and self.okx_websocket_task:
                self.okx_websocket_task.cancel()
                try:
                    await self.okx_websocket_task
                except asyncio.CancelledError:
                    pass

            self.logger.info("🔧 OKX现货特定清理完成")

        except Exception as e:
            self.logger.error("❌ OKX现货清理失败", error=str(e))

    async def _perform_reconnection(self) -> bool:
        """
        执行OKX现货WebSocket重连操作

        Returns:
            bool: 重连是否成功
        """
        try:
            self.logger.info("🔄 开始OKX现货WebSocket重连")

            # OKX现货重连逻辑：
            # 1. 重连由WebSocket客户端自动处理
            # 2. 管理器只需要重置订单簿状态
            # 3. 等待新的快照数据

            # 重置所有订单簿状态
            for symbol, state in self.orderbook_states.items():
                state.is_synced = False
                state.local_orderbook = None
                state.last_update_id = 0
                self.logger.debug(f"🔄 重置OKX现货订单簿状态: {symbol}")

            # 重置错误计数器
            self._reset_error_counters()

            self.logger.info("✅ OKX现货重连准备完成，等待WebSocket重新连接和快照推送")
            return True

        except Exception as e:
            self.logger.error(f"❌ OKX现货重连失败: {e}")
            return False

    async def _exchange_specific_resync(self, symbol: str, reason: str):
        """
        OKX现货特定的重新同步逻辑

        Args:
            symbol: 交易对
            reason: 重新同步原因
        """
        try:
            self.logger.info(f"🔄 OKX现货重新同步: {symbol}, 原因: {reason}")

            # OKX现货重新同步策略：
            # 1. 重置订单簿状态，等待WebSocket重新推送快照
            # 2. 如果长时间没有收到快照，可能需要重新订阅

            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if state:
                state.is_synced = False
                state.local_orderbook = None
                state.last_seq_id = None
                state.last_update_id = 0
                self.logger.debug(f"🔄 重置OKX现货订单簿状态: {symbol}")

            # 清空缓冲并重置等待快照计时
            self.message_buffers[symbol] = []
            self.waiting_for_snapshot_since[symbol] = time.time()

            # 记录重新同步时间，用于后续监控
            state.last_snapshot_time = None

            self.logger.info(f"✅ OKX现货重新同步完成: {symbol}，等待WebSocket推送新快照")

        except Exception as e:
            self.logger.error(f"❌ OKX现货重新同步失败: {symbol}, error={e}")
