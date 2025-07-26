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

        # 🔧 新增：消息缓冲区用于处理乱序消息
        self.message_buffers: Dict[str, List[dict]] = {}
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

        for symbol in self.symbols:
            unique_key = self._get_unique_key(symbol)
            self.orderbook_states[unique_key] = OrderBookState(
                symbol=symbol,
                exchange="okx_derivatives"
            )
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
                self.logger.warning(f"⚠️ {symbol}状态不存在")
                return
            
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

            # 根据action类型处理消息
            if action == 'snapshot':
                await self._apply_snapshot(symbol, message, state)
                self.stats['snapshots_applied'] += 1
            elif action == 'update':
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
            snapshot = EnhancedOrderBook(
                exchange_name="okx_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=int(timestamp_ms),
                bids=bids,
                asks=asks,
                timestamp=datetime.now(),
                update_type=OrderBookUpdateType.SNAPSHOT,
                first_update_id=int(timestamp_ms),
                prev_update_id=int(timestamp_ms),
                depth_levels=len(bids) + len(asks)
            )

            # 更新状态
            state.local_orderbook = snapshot
            state.last_seq_id = seq_id
            state.last_snapshot_time = datetime.now()
            state.is_synced = True

            self.logger.debug(f"✅ OKX衍生品快照应用成功: {symbol}, bids={len(bids)}, asks={len(asks)}, seqId={seq_id}")

            # 发布到NATS
            await self.publish_orderbook(symbol, snapshot)

        except Exception as e:
            self.logger.error(f"❌ 应用OKX衍生品快照失败: {symbol}, error={e}")
            state.is_synced = False
            raise
    
    async def _apply_update(self, symbol: str, message: dict, state: OrderBookState):
        """应用增量更新 - 统一使用EnhancedOrderBook格式"""
        try:
            if not state.is_synced or not state.local_orderbook:
                self.logger.warning(f"⚠️ {symbol}未同步，跳过更新")
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
                # 构建更新后的原始数据格式用于checksum验证
                updated_bids_raw = [[str(price), str(quantity)] for price, quantity in current_bids.items()]
                updated_asks_raw = [[str(price), str(quantity)] for price, quantity in current_asks.items()]

                # 排序原始数据
                updated_bids_raw.sort(key=lambda x: float(x[0]), reverse=True)
                updated_asks_raw.sort(key=lambda x: float(x[0]))

                calculated_checksum = self._calculate_okx_checksum_from_raw_data(updated_bids_raw, updated_asks_raw)
                expected_checksum = str(message.get('checksum', ''))

                if calculated_checksum != expected_checksum:
                    self.logger.warning(f"⚠️ OKX衍生品更新checksum验证失败: {symbol}，回滚更新")
                    self.logger.warning(f"🔍 Checksum不匹配: 期望={expected_checksum}, 计算={calculated_checksum}")
                    return
                else:
                    self.logger.debug(f"✅ OKX衍生品更新checksum验证成功: {symbol}, checksum={expected_checksum}")

            # 转换为PriceLevel列表并排序
            new_bids = [PriceLevel(price=price, quantity=quantity) for price, quantity in current_bids.items()]
            new_asks = [PriceLevel(price=price, quantity=quantity) for price, quantity in current_asks.items()]

            new_bids.sort(key=lambda x: x.price, reverse=True)
            new_asks.sort(key=lambda x: x.price)

            # 创建更新后的订单簿
            updated_orderbook = EnhancedOrderBook(
                exchange_name="okx_derivatives",
                symbol_name=symbol,
                market_type="perpetual",
                last_update_id=int(timestamp_ms),
                bids=new_bids,
                asks=new_asks,
                timestamp=datetime.now(),
                update_type=OrderBookUpdateType.UPDATE,
                first_update_id=int(timestamp_ms),
                prev_update_id=state.last_seq_id,
                depth_levels=len(new_bids) + len(new_asks)
            )

            # 更新状态
            state.local_orderbook = updated_orderbook
            state.last_seq_id = seq_id

            self.logger.debug(f"✅ OKX衍生品更新应用成功: {symbol}, seqId={seq_id}")

            # 发布到NATS
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

            # 创建OKX WebSocket管理器
            self.okx_ws_client = OKXWebSocketManager(
                symbols=self.symbols,
                on_orderbook_update=self._handle_okx_websocket_update,
                market_type='derivatives'
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

            # 正常序列验证
            if state.last_seq_id is not None and prev_seq_id != state.last_seq_id:
                self.logger.error(f"❌ {symbol}序列号不连续: expected={state.last_seq_id}, got={prev_seq_id}, seqId={seq_id}")
                self.stats.setdefault('sequence_errors', 0)
                self.stats['sequence_errors'] += 1

                # 序列错误时标记需要重新同步
                state.is_synced = False
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

    def _process_buffered_messages(self, symbol: str, state) -> List[dict]:
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
            if hasattr(state, 'last_seq_id') and prev_seq_id == state.last_seq_id:
                processed_messages.append(message)
                state.last_seq_id = message.get('seqId')
                buffer.pop(0)
                self.logger.debug(f"🔄 {symbol} 从缓冲区处理消息: prevSeqId={prev_seq_id}, seqId={message.get('seqId')}")
            else:
                break  # 不连续，停止处理

        return processed_messages
