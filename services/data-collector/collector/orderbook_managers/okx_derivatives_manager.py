"""
OKX衍生品订单簿管理器
处理OKX永续合约和期货的订单簿数据
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
import time

from .base_orderbook_manager import BaseOrderBookManager
from ..data_types import OrderBookState, NormalizedOrderBook, EnhancedOrderBook, PriceLevel, OrderBookUpdateType

# 🔧 迁移到统一日志系统
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    ComponentType
)

from exchanges.common.ws_message_utils import unwrap_combined_stream_message


class OKXDerivativesOrderBookManager(BaseOrderBookManager):
    """OKX衍生品订单簿管理器"""

    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        super().__init__(
            exchange="okx_derivatives",
            market_type="perpetual",
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(
            ComponentType.ORDERBOOK_MANAGER,
            exchange="okx",
            market_type="derivatives"
        )

        # OKX衍生品特定配置
        self.checksum_validation = config.get('checksum_validation', True)
        self.sequence_validation = config.get('sequence_validation', True)
        self.max_depth = config.get('depth_limit', 400)  # OKX最大400档

        # 🔧 修复内存泄漏：使用deque替代list，自动限制大小
        from collections import deque
        self.message_buffers: Dict[str, deque] = {}
        self.buffer_max_size = config.get('buffer_max_size', 100)  # 缓冲区最大大小
        self.buffer_timeout = config.get('buffer_timeout', 5.0)    # 缓冲超时时间(秒)

        # NATS推送配置
        self.enable_nats_push = config.get('enable_nats_push', True)

        # 🔧 修复：继承基类统计信息并添加OKX特定字段
        # 不要重新定义stats，而是扩展基类的stats
        self.stats.update({
            'snapshots_received': 0,
            'checksum_validations': 0,
            'checksum_failures': 0,
            'sequence_errors': 0,
            'maintenance_resets': 0
        })

        # 🔧 迁移到统一日志系统 - 标准化启动日志
        self.logger.startup(
            "OKX derivatives orderbook manager initialized",
            symbols=symbols,
            max_depth=self.max_depth,
            checksum_validation=self.checksum_validation
        )

    def _get_unique_key(self, symbol: str) -> str:
        """生成唯一键"""
        return f"okx_derivatives_perpetual_{symbol}"

    async def initialize_orderbook_states(self):
        """初始化订单簿状态"""
        # 🔧 迁移到统一日志系统 - 标准化初始化日志
        self.logger.startup("Initializing OKX derivatives orderbook states")

        # 初始化等待快照计时字典
        if not hasattr(self, 'waiting_for_snapshot_since'):
            self.waiting_for_snapshot_since = {}

        for symbol in self.symbols:
            unique_key = self._get_unique_key(symbol)
            self.orderbook_states[unique_key] = OrderBookState(
                symbol=symbol,
                exchange="okx_derivatives"
            )
            # 初始化等待时间标记
            self.waiting_for_snapshot_since[symbol] = None
            # 🔧 迁移到统一日志系统 - 数据处理日志会被自动去重
            self.logger.data_processed(
                "Orderbook state initialized",
                symbol=symbol,
                unique_key=unique_key,
                operation="state_initialization"
            )

    async def process_websocket_message(self, symbol: str, message: dict):
        """处理OKX衍生品WebSocket消息"""
        try:
            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if not state:
                self.logger.warning(f"⚠️ {symbol}状态不存在，执行惰性初始化")
                self.orderbook_states[unique_key] = OrderBookState(symbol=symbol, exchange="okx_derivatives")
                state = self.orderbook_states[unique_key]
            # 统一预解包（兼容未来可能出现的外层包裹结构）
            message = unwrap_combined_stream_message(message)

            # 根据OKX官方文档解析action字段
            action = message.get('action')
            if action is None:
                self.logger.error(f"❌ OKX衍生品消息缺少action字段: {symbol}")
                return

            # 获取序列号信息
            seq_id = message.get('seqId')
            prev_seq_id = message.get('prevSeqId')

            # 🔧 迁移到统一日志系统 - 数据处理日志会被自动去重和频率控制
            self.logger.data_processed(
                "Processing OKX derivatives message",
                symbol=symbol,
                action=action,
                seq_id=seq_id,
                prev_seq_id=prev_seq_id
            )

            # 先进行序列验证
            is_valid = await self._validate_message_sequence(symbol, message, state)
            if not is_valid:
                await self._handle_error(symbol, 'sequence', f'序列验证失败: prevSeqId={prev_seq_id}, last_seq={getattr(state, "last_seq_id", None)}')
                # 触发重新同步，等待新快照
                await self._exchange_specific_resync(symbol, reason='sequence_mismatch')
                return

            # 根据action类型处理消息
            if action == 'snapshot':
                await self._apply_snapshot(symbol, message, state)
                self.stats['snapshots_applied'] += 1
                # 快照后尝试回放缓冲区
                for buffered in self._process_buffered_messages(symbol, state):
                    try:
                        # 回放缓冲只更新本地状态，不逐条发布，避免发布过期事件
                        await self._apply_update(symbol, buffered, state, publish=False)
                        self.stats['updates_applied'] += 1
                    except Exception as e:
                        await self._handle_error(symbol, 'processing', f'回放缓冲消息失败: {e}')
                # 回放完成后仅发布一次最终最新状态
                if state and state.local_orderbook:
                    await self.publish_orderbook(symbol, state.local_orderbook)
            elif action == 'update':
                # 如果未同步，先缓冲，并在超时未等到快照时触发单symbol重订阅（自愈）
                if not state.local_orderbook:
                    # 记录首次等待快照的时间
                    if not getattr(self, 'waiting_for_snapshot_since', None):
                        self.waiting_for_snapshot_since = {}
                    if not self.waiting_for_snapshot_since.get(symbol):
                        self.waiting_for_snapshot_since[symbol] = time.time()

                    self._buffer_message(symbol, message)

                    # 计算已等待时间并在超时后触发重订阅
                    waited = time.time() - (self.waiting_for_snapshot_since.get(symbol) or time.time())
                    if waited >= max(2.0 * float(self.buffer_timeout), 5.0):
                        try:
                            self.logger.warning(f"⏰ {symbol}等待快照超时，触发重订阅")
                            await self._resubscribe_symbol(symbol)
                        except Exception as re:
                            self.logger.error("❌ OKX衍生品重订阅失败", symbol=symbol, error=str(re))
                        finally:
                            # 重置起始时间，避免频繁重订阅
                            self.waiting_for_snapshot_since[symbol] = time.time()
                    return
                await self._apply_update(symbol, message, state)
                self.stats['updates_applied'] += 1
            else:
                # 🔧 迁移到统一日志系统 - 标准化错误处理
                self.logger.error(
                    "Invalid OKX derivatives action type",
                    error=ValueError(f"Invalid action: {action}"),
                    symbol=symbol,
                    action=action
                )
                await self._handle_error(symbol, 'processing', f"无效action: {action}")
                return

        except Exception as e:
            # 🔧 迁移到统一日志系统 - 标准化错误处理
            self.logger.error(
                "OKX derivatives message processing failed",
                error=e,
                symbol=symbol,
                operation="message_processing"
            )
            self.stats['errors'] += 1

    async def _apply_snapshot(self, symbol: str, message: dict, state: OrderBookState):
        """应用快照数据 - 统一使用EnhancedOrderBook格式"""
        try:
            self.logger.debug(f"📊 应用OKX衍生品快照: {symbol}")

            # 解析快照数据
            bids_data = message.get('bids', [])
            asks_data = message.get('asks', [])
            timestamp_ms = message.get('ts', str(int(time.time() * 1000)))
            seq_id = message.get('seqId')

            # 🔧 修复：先用原始数据验证checksum
            if self.checksum_validation:
                calculated_checksum = self._calculate_okx_checksum_from_raw_data(bids_data, asks_data)
                expected_checksum = str(message.get('checksum', ''))

                if calculated_checksum == expected_checksum:
                    self.logger.debug(f"✅ OKX衍生品快照checksum验证成功: {symbol}, checksum={expected_checksum}")
                else:
                    self.logger.warning(f"⚠️ OKX衍生品快照checksum验证失败: {symbol}, 期望={expected_checksum}, 计算={calculated_checksum}")

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
            # 使用事件时间(ts, ms)作为timestamp
            from datetime import timezone
            event_dt = datetime.utcfromtimestamp(int(timestamp_ms) / 1000).replace(tzinfo=timezone.utc)
            snapshot = EnhancedOrderBook(
                exchange_name="okx_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                bids=bids,
                asks=asks,
                timestamp=event_dt,
                update_type=OrderBookUpdateType.SNAPSHOT,
                first_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                prev_update_id=int(message.get('prevSeqId', -1)) if isinstance(message.get('prevSeqId', -1), (int, str)) else -1,
                depth_levels=len(bids) + len(asks)
            )

            # 更新状态
            state.local_orderbook = snapshot
            state.last_seq_id = seq_id
            state.last_update_id = int(seq_id or 0)
            state.last_snapshot_time = datetime.now()
            state.is_synced = True
            # 清除等待标记（已收到快照）
            try:
                if hasattr(self, 'waiting_for_snapshot_since'):
                    self.waiting_for_snapshot_since[symbol] = None
            except Exception:
                pass






            self.logger.debug(f"✅ OKX衍生品快照应用成功: {symbol}, bids={len(bids)}, asks={len(asks)}, seqId={seq_id}")

            # 发布到NATS
            await self.publish_orderbook(symbol, snapshot)

        except Exception as e:
            self.logger.error(f"❌ 应用OKX衍生品快照失败: {symbol}, error={e}")
            state.is_synced = False
            raise

    async def _apply_update(self, symbol: str, message: dict, state: OrderBookState, publish: bool = True):
        """应用增量更新 - 统一使用EnhancedOrderBook格式"""
        try:
            if not state.is_synced or not state.local_orderbook:
                # 未同步时，不丢弃，进入缓冲，等待快照后回放
                self._buffer_message(symbol, message)
                return

            # 解析更新数据
            bids_data = message.get('bids', [])
            asks_data = message.get('asks', [])
            timestamp_ms = message.get('ts', str(int(time.time() * 1000)))
            seq_id = message.get('seqId')

            # 获取当前订单簿的副本
            current_bids = {bid.price: bid.quantity for bid in state.local_orderbook.bids}
            current_asks = {ask.price: ask.quantity for ask in state.local_orderbook.asks}

            # 应用买单更新
            for bid_data in bids_data:
                price = Decimal(str(bid_data[0]))
                quantity = Decimal(str(bid_data[1]))

                if quantity == 0:
                    # 删除价格档位
                    current_bids.pop(price, None)
                else:
                    # 更新价格档位
                    current_bids[price] = quantity

            # 应用卖单更新
            for ask_data in asks_data:
                price = Decimal(str(ask_data[0]))
                quantity = Decimal(str(ask_data[1]))

                if quantity == 0:
                    # 删除价格档位
                    current_asks.pop(price, None)
                else:
                    # 更新价格档位
                    current_asks[price] = quantity

            # 🔧 修复：先验证checksum，然后再转换数据格式
            if self.checksum_validation:
                # 构建更新后的原始数据格式用于checksum验证（严格按OKX十进制字符串格式，避免科学计数法与尾随0差异）
                updated_bids_raw = [[self._to_okx_decimal_str(price), self._to_okx_decimal_str(quantity)] for price, quantity in current_bids.items()]
                updated_asks_raw = [[self._to_okx_decimal_str(price), self._to_okx_decimal_str(quantity)] for price, quantity in current_asks.items()]

                # 排序原始数据（按价格数值）
                updated_bids_raw.sort(key=lambda x: float(x[0]), reverse=True)
                updated_asks_raw.sort(key=lambda x: float(x[0]))

                calculated_checksum = self._calculate_okx_checksum_from_raw_data(updated_bids_raw, updated_asks_raw)
                expected_checksum = str(message.get('checksum', ''))

                if calculated_checksum != expected_checksum:
                    await self._handle_error(symbol, 'checksum', f"Checksum验证失败: expected={expected_checksum}, calc={calculated_checksum}")
                    # 触发重新同步，等待新快照
                    await self._exchange_specific_resync(symbol, reason='checksum_mismatch')
                    return
                else:
                    self.logger.debug(f"✅ OKX衍生品更新checksum验证成功: {symbol}, checksum={expected_checksum}")

            # 转换为PriceLevel列表并排序
            new_bids = [PriceLevel(price=price, quantity=quantity) for price, quantity in current_bids.items()]
            new_asks = [PriceLevel(price=price, quantity=quantity) for price, quantity in current_asks.items()]

            new_bids.sort(key=lambda x: x.price, reverse=True)
            new_asks.sort(key=lambda x: x.price)

            # 创建更新后的订单簿
            # 使用事件时间(ts, ms)作为timestamp
            from datetime import timezone
            event_dt = datetime.utcfromtimestamp(int(timestamp_ms) / 1000).replace(tzinfo=timezone.utc)
            updated_orderbook = EnhancedOrderBook(
                exchange_name="okx_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                bids=new_bids,
                asks=new_asks,
                timestamp=event_dt,
                update_type=OrderBookUpdateType.UPDATE,
                first_update_id=int(seq_id) if seq_id is not None else int(timestamp_ms),
                prev_update_id=int(message.get('prevSeqId', state.last_seq_id if state.last_seq_id is not None else -1)),
                depth_levels=len(new_bids) + len(new_asks)
            )

            # 更新状态
            state.local_orderbook = updated_orderbook
            state.last_seq_id = seq_id
            state.last_update_id = int(seq_id or 0)

            self.logger.debug(f"✅ OKX衍生品更新应用成功: {symbol}, seqId={seq_id}")

            # 发布到NATS（可控）
            if publish:
                await self.publish_orderbook(symbol, updated_orderbook)

        except Exception as e:
            self.logger.error(f"❌ 应用OKX衍生品更新失败: {symbol}, error={e}")
            state.is_synced = False



    def _calculate_checksum(self, orderbook: dict) -> str:
        """计算OKX订单簿校验和 - 使用统一的基类方法"""
        return self._calculate_okx_checksum(orderbook)

    def _validate_checksum_with_enhanced_orderbook(self, data: dict, bids: List[PriceLevel], asks: List[PriceLevel]) -> bool:
        """验证OKX checksum - 🔧 修复：使用原始数据格式"""
        try:
            expected_checksum = data.get('checksum')
            if not expected_checksum:
                return True  # 如果没有checksum字段，跳过验证

            # 🔧 修复：使用原始数据而不是转换后的PriceLevel
            bids_data = data.get('bids', [])
            asks_data = data.get('asks', [])

            # 使用修复后的checksum计算方法
            calculated_checksum = self._calculate_okx_checksum_from_raw_data(bids_data, asks_data)

            if not calculated_checksum:
                return False

            is_match = calculated_checksum == str(expected_checksum)

            if not is_match:
                self.logger.debug(f"🔍 Checksum不匹配: 期望={expected_checksum}, 计算={calculated_checksum}")

            return is_match

        except Exception as e:
            self.logger.error(f"❌ checksum验证异常: {e}")
            return False


    def _to_okx_decimal_str(self, d: Decimal) -> str:
        """
        
        OKX 
        https://www.okx.com/docs-v5/zh/#websocket-api-checks
        """
        try:
            s = format(d, 'f')
            if '.' in s:
                s = s.rstrip('0').rstrip('.')
            return s if s != '' else '0'
        except Exception:
            return str(d)



    def _calculate_okx_checksum_from_raw_data(self, bids_data: list, asks_data: list) -> str:
        """
        🔧 修复：使用原始数据计算OKX checksum
        避免数据转换导致的格式问题
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



    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.stats.copy()

    async def _exchange_specific_initialization(self):
        """OKX衍生品特定的初始化逻辑"""
        try:
            # 🔧 修复：启动OKX WebSocket连接
            from exchanges.okx_websocket import OKXWebSocketManager

            # 创建OKX WebSocket管理器，传递配置以启用观测性功能
            self.okx_ws_client = OKXWebSocketManager(
                symbols=self.symbols,
                on_orderbook_update=self._handle_okx_websocket_update,
                market_type='derivatives',
                config=self.config  # 传递配置以启用ping_pong_verbose等观测性功能
            )

            self.logger.info("🌐 启动OKX衍生品WebSocket连接",
                           symbols=self.symbols,
                           ws_url=self.okx_ws_client.ws_url)

            # 启动WebSocket客户端
            self.okx_websocket_task = asyncio.create_task(self.okx_ws_client.start())

            self.logger.info("🔧 OKX衍生品特定初始化完成")

        except Exception as e:
            self.logger.error("❌ OKX衍生品特定初始化失败", error=str(e), exc_info=True)
            raise

    async def _handle_okx_websocket_update(self, symbol: str, update_data):
        """处理OKX WebSocket订单簿更新"""
        try:
            # 🔧 使用基类提供的标准接口
            await self.handle_websocket_message(symbol, update_data)

        except Exception as e:
            self.logger.error(f"❌ OKX WebSocket回调失败: {symbol}, error={e}")

    async def _exchange_specific_cleanup(self):
        """OKX衍生品特定的清理逻辑"""
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

            self.logger.info("🧹 OKX衍生品特定清理完成")

        except Exception as e:
            self.logger.error("❌ OKX衍生品特定清理失败", error=str(e), exc_info=True)

    def _get_snapshot_depth(self) -> int:
        """OKX衍生品快照深度：400档"""
        return 400

    def _get_websocket_depth(self) -> int:
        """OKX衍生品WebSocket深度：400档"""
        return 400

    async def _fetch_initial_snapshot(self, symbol: str) -> dict:
        """获取初始快照 - OKX通过WebSocket自动推送，无需主动获取"""
        self.logger.info(f"📡 OKX衍生品依赖WebSocket推送快照: {symbol}")
        # OKX会在订阅后自动推送快照，无需主动获取
        return {}

    async def _perform_reconnection(self) -> bool:
        """
        执行OKX衍生品WebSocket重连操作

        Returns:
            bool: 重连是否成功
        """
        try:
            self.logger.info("🔄 开始OKX衍生品WebSocket重连")

            # OKX衍生品重连逻辑：
            # 1. 重连由WebSocket客户端自动处理
            # 2. 管理器只需要重置订单簿状态
            # 3. 等待新的快照数据

            # 重置所有订单簿状态
            for symbol, state in self.orderbook_states.items():
                state.is_synced = False
                state.local_orderbook = None
                state.last_seq_id = None
                self.logger.debug(f"🔄 重置OKX衍生品订单簿状态: {symbol}")

            # 重置错误计数器
            self._reset_error_counters()

            self.logger.info("✅ OKX衍生品重连准备完成，等待WebSocket重新连接和快照推送")
            return True

        except Exception as e:
            self.logger.error(f"❌ OKX衍生品重连失败: {e}")
            return False

    async def _resubscribe_symbol(self, symbol: str):
        """为单个symbol执行OKX衍生品订单簿重订阅（先退订再订阅，强制下发新快照）"""
        try:
            client = getattr(self, 'okx_ws_client', None)
            if client:
                await client.unsubscribe_orderbook([symbol])
                await asyncio.sleep(0.2)
                await client.subscribe_orderbook([symbol])
                self.logger.info("📡 已重订阅OKX衍生品订单簿", symbol=symbol)
            else:
                self.logger.warning("⚠️ okx_ws_client 未初始化，无法执行重订阅", symbol=symbol)
        except Exception as e:
            self.logger.error("❌ OKX衍生品重订阅失败", symbol=symbol, error=str(e))

    async def _exchange_specific_resync(self, symbol: str, reason: str):
        """
        OKX衍生品特定的重新同步逻辑

        Args:
            symbol: 交易对
            reason: 重新同步原因
        """
        try:
            self.logger.info(f"🔄 OKX衍生品重新同步: {symbol}, 原因: {reason}")

            # OKX衍生品重新同步策略：
            # 1. 重置订单簿状态，等待WebSocket重新推送快照
            # 2. 如果长时间没有收到快照，可能需要重新订阅

            unique_key = self._get_unique_key(symbol)
            state = self.orderbook_states.get(unique_key)
            if state:
                state.is_synced = False
                state.local_orderbook = None
                state.last_seq_id = None
                self.logger.debug(f"🔄 重置OKX衍生品订单簿状态: {symbol}")

            self.logger.info(f"✅ OKX衍生品重新同步完成: {symbol}，等待WebSocket推送新快照")

        except Exception as e:
            self.logger.error(f"❌ OKX衍生品重新同步失败: {symbol}, error={e}")

    async def _validate_message_sequence(self, symbol: str, message: dict, state) -> bool:
        """
        验证OKX消息序列

        根据OKX官方文档：
        1. 快照消息的prevSeqId为-1
        2. 增量消息的prevSeqId应该等于上一条消息的seqId
        3. 维护重启时可能出现seqId < prevSeqId的情况，需要重置验证
        """
        try:
            if not self.sequence_validation:
                return True

            seq_id = message.get('seqId')
            prev_seq_id = message.get('prevSeqId')
            action = message.get('action')

            # 快照消息的prevSeqId为-1，直接通过验证
            if action == 'snapshot':
                self.logger.debug(f"📊 {symbol}收到快照消息，重置序列验证")
                state.last_seq_id = seq_id
                return True

            # 处理维护重启情况：seqId < prevSeqId
            if seq_id is not None and prev_seq_id is not None and seq_id < prev_seq_id:
                self.logger.warning(f"🔄 {symbol}检测到维护重启，重置序列验证: seqId={seq_id}, prevSeqId={prev_seq_id}")
                state.last_seq_id = None
                self.stats.setdefault('maintenance_resets', 0)
                self.stats['maintenance_resets'] += 1
                return True

            # 正常序列验证 - 🚀 智能恢复机制
            if state.last_seq_id is not None and prev_seq_id != state.last_seq_id:
                gap = abs(prev_seq_id - state.last_seq_id) if isinstance(prev_seq_id, int) and isinstance(state.last_seq_id, int) else 0
                self.logger.error(f"❌ {symbol}序列号不连续: expected={state.last_seq_id}, got={prev_seq_id}, seqId={seq_id}, gap={gap}")
                self.stats.setdefault('sequence_errors', 0)
                self.stats['sequence_errors'] += 1

                # 🚀 智能恢复：序列号跳跃时主动触发重新同步，而不是简单拒绝
                # 这样可以保证数据质量，同时不会陷入死循环
                state.is_synced = False

                # 记录连续序列错误次数
                if not hasattr(state, 'consecutive_sequence_errors'):
                    state.consecutive_sequence_errors = 0
                state.consecutive_sequence_errors += 1

                # 如果连续序列错误超过阈值，触发完整重新同步
                if state.consecutive_sequence_errors >= 3:
                    self.logger.warning(f"⚠️ {symbol}序列错误次数过多({state.consecutive_sequence_errors})，触发重新同步")
                    # 异步触发重新同步
                    try:
                        import asyncio
                        asyncio.create_task(self._exchange_specific_resync(symbol, reason=f'sequence_gap_{gap}'))
                    except Exception:
                        self.logger.warning(f"⚠️ {symbol}重同步调度失败，等待后续路径触发")

                return False

            # 更新最后的序列号
            if seq_id is not None:
                state.last_seq_id = seq_id

            return True

        except Exception as e:
            self.logger.error(f"❌ 验证消息序列失败: {symbol}, error={e}")
            self.stats.setdefault('sequence_validation_errors', 0)
            self.stats['sequence_validation_errors'] += 1
            return False

    def _buffer_message(self, symbol: str, message: dict) -> None:
        """将消息添加到缓冲区"""
        # 🔧 修复内存泄漏：使用deque自动限制大小
        if symbol not in self.message_buffers:
            from collections import deque
            self.message_buffers[symbol] = deque(maxlen=self.buffer_max_size)

        buffer = self.message_buffers[symbol]
        buffer.append({
            'message': message,
            'timestamp': time.time()
        })

        # 注意：deque不支持sort，但会自动移除最旧元素
        # 对于OKX的prevSeqId排序，我们依赖WebSocket的顺序保证

        # deque会自动移除最旧的元素，当达到maxlen时触发重同步
        if len(buffer) >= self.buffer_max_size:
            # 🔧 修复：降低日志级别（WARNING→INFO），缓冲区溢出触发重同步是正常的流控机制
            self.logger.info(f"📦 {symbol} 缓冲区已满，触发重同步以防止数据丢失与序列断裂",
                           buffer_size=len(buffer), max_size=self.buffer_max_size)
            # 清空缓冲，避免回放过期/不连续数据
            self.message_buffers[symbol].clear()
            # 异步触发重新同步
            try:
                import asyncio
                asyncio.create_task(self._exchange_specific_resync(symbol, reason='buffer_overflow'))
            except Exception:
                # 若当前无事件循环，则记录并忽略（调用方会在后续路径触发resync）
                self.logger.warning(f"⚠️ {symbol} 重同步调度失败（无事件循环），已清空缓冲，等待后续路径触发")

    def _process_buffered_messages(self, symbol: str, state) -> List[dict]:
        """处理缓冲区中的连续消息"""
        if symbol not in self.message_buffers:
            return []

        buffer = self.message_buffers[symbol]
        processed_messages = []
        current_time = time.time()

        # 🔧 修复：移除过期消息 - deque不支持切片赋值，需要手动清理
        # 从左侧移除过期消息（deque的popleft是O(1)操作）
        expired_count = 0
        while buffer and (current_time - buffer[0]['timestamp'] >= self.buffer_timeout):
            buffer.popleft()
            expired_count += 1

        if expired_count > 0:
            self.logger.debug(f"🧹 {symbol} 清理过期消息", expired_count=expired_count)

        # 查找连续的消息
        while buffer:
            item = buffer[0]
            message = item['message']
            prev_seq_id = message.get('prevSeqId')

            # 检查是否是期望的下一个消息
            if hasattr(state, 'last_seq_id') and prev_seq_id == state.last_seq_id:
                processed_messages.append(message)
                state.last_seq_id = message.get('seqId')
                buffer.popleft()  # 使用popleft而不是pop(0)
                self.logger.debug(f"🔄 {symbol} 从缓冲区处理消息: prevSeqId={prev_seq_id}, seqId={message.get('seqId')}")
            else:
                break  # 不连续，停止处理

        return processed_messages
