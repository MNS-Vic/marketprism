"""
Binance现货订单簿管理器 - WebSocket Stream版本
使用WebSocket Stream实时获取增量深度更新
使用简化的序列号验证逻辑，解决 Binance 交易所序列号不一致问题
"""

import asyncio
import json
import time
from typing import Dict, List, Optional
from datetime import datetime, timezone
from decimal import Decimal
import websockets
import aiohttp
from collections import OrderedDict

from exchanges.common.ws_message_utils import unwrap_combined_stream_message
from .base_orderbook_manager import BaseOrderBookManager
from ..data_types import OrderBookSnapshot, NormalizedOrderBook, EnhancedOrderBook
from ..error_management.error_handler import ErrorHandler, BinanceAPIError, RetryHandler
import structlog


class BinanceSpotOrderBookManager(BaseOrderBookManager):
    """
    Binance现货订单簿管理器 - WebSocket Stream版本

    ## 丢包检测规则（基于Binance现货API文档）

    ### 序列号验证逻辑：
    1. **初始化检查**：如果本地 last_update_id == 0，直接接受并建立序列号链
    2. **过期消息过滤**：如果 event.u <= current_last_update_id，忽略该消息
    3. **丢包检测**：如果 event.U > current_last_update_id + 1，说明出现丢包

    ### 重建流程（简化策略，避免卡住）：
    ```
    检测到丢包 → 记录警告日志 → 重置序列号为0 → 从当前消息重新建立序列号链
    ```

    ### 关键特性：
    - ✅ 不进行复杂的快照获取，避免初始化卡住
    - ✅ 直接使用当前消息作为新序列号链的起点
    - ✅ 保留数据完整性检测，确保及时发现问题
    - ✅ 简化重建策略，提高系统稳定性

    ### 统计字段说明：
    - `sequence_errors`: 检测到的序列号错误次数
    - `orderbook_rebuilds`: 触发的订单簿重建次数
    - `total_processed/total_received`: 消息处理成功率指标
    """

    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化Binance现货订单簿管理器

        Args:
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置字典
        """
        # 先设置必要的属性，因为基类__init__会调用_get_snapshot_depth()等方法
        self.api_base_url = config.get('api_base_url', 'https://api.binance.com')
        # 快照深度：默认1000（发布仍裁剪到400档）
        self.depth_limit = config.get('depth_limit', 1000)

        super().__init__(
            exchange="binance_spot",
            market_type="spot",
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # WebSocket Stream配置
        self.ws_stream_url = "wss://stream.binance.com:9443/stream"
        self.ws_client = None
        self.ws_connected = False

        # 简化的序列号管理
        # 直接使用最新收到的 WebSocket 增量更新事件的 u 值（final update ID）
        # 移除复杂的序列号匹配逻辑，解决 Binance 交易所序列号不一致问题
        self.last_update_ids = {symbol: 0 for symbol in symbols}  # 每个symbol的最后更新ID

        # 消息统计
        self.message_stats = {
            'total_received': 0,
            'total_processed': 0,
            'depth_updates': 0,
            'sequence_errors': 0,  # 现在只记录序列号跳跃，不触发重建
            'orderbook_rebuilds': 0  # 简化逻辑后应该很少发生
        }

        self.running = False

        self.logger = structlog.get_logger("collector.orderbook_managers.binance_spot")

        # 错误处理器（需要logger参数）
        self.error_handler = ErrorHandler(self.logger)
        self.retry_handler = RetryHandler(self.error_handler)

        self.logger.info("🏭 Binance现货订单簿管理器初始化完成（WebSocket Stream）",
                        symbols=symbols,
                        api_base_url=self.api_base_url,
                        depth_limit=self.depth_limit,
                        ws_stream_url=self.ws_stream_url)

        # 本地订单簿（与永续风格一致）：price -> quantity
        self.local_orderbooks = {symbol: {'bids': OrderedDict(), 'asks': OrderedDict()} for symbol in self.symbols}
        self.last_update_ids = {symbol: 0 for symbol in self.symbols}
        self._last_event_time_ms = {symbol: None for symbol in self.symbols}

    async def start(self):
        """启动Binance现货订单簿管理器（本地维护 + 完整快照发布）"""
        self.logger.info("🚀 启动Binance现货订单簿管理器（本地维护 + 完整快照发布）",
                        symbols=self.symbols,
                        ws_stream_url=self.ws_stream_url)

        # 设置运行状态（同时设置基类和本类的状态）
        self.running = True
        self._is_running = True  # 设置基类的运行状态，供健康检查使用

        # 初始化本地订单簿状态（获取REST快照）
        await self.initialize_orderbook_states()

        # 启动WebSocket Stream连接和消息处理
        await self._connect_websocket_stream()

        self.logger.info("✅ Binance现货订单簿管理器启动完成")

    async def _exchange_specific_initialization(self):
        """交易所特定的初始化逻辑"""
        # WebSocket Stream架构不需要复杂的初始化
        pass

    async def _exchange_specific_cleanup(self):
        """交易所特定的清理逻辑"""
        # 关闭WebSocket Stream连接
        await self._close_websocket_stream()
        self.logger.info("🧹 WebSocket Stream连接已清理")

    # 实现基类要求的抽象方法
    def _get_snapshot_depth(self) -> int:
        """获取快照深度"""
        return self.depth_limit

    def _get_websocket_depth(self) -> int:
        """获取WebSocket深度"""
        return self.depth_limit

    async def initialize_orderbook_states(self):
        """初始化订单簿状态：获取REST快照，填充本地订单簿"""
        self.logger.info("🚀 初始化Binance现货订单簿状态（获取快照）")
        # 为每个symbol获取初始快照
        for symbol in self.symbols:
            try:
                snapshot = await self._fetch_initial_snapshot(symbol)
                if snapshot:
                    await self._apply_snapshot_to_local_orderbook(symbol, snapshot)
                    self.logger.info("✅ 初始快照应用成功", symbol=symbol, lastUpdateId=snapshot.get('lastUpdateId'))
                else:
                    self.logger.warning("⚠️ 初始快照为空，稍后将依赖增量建立本地簿", symbol=symbol)
                # 初始化序列号
                self.last_update_ids[symbol] = snapshot.get('lastUpdateId', 0) if snapshot else 0
            except Exception as e:
                self.logger.error("❌ 初始化快照失败", symbol=symbol, error=str(e))
                self.last_update_ids[symbol] = 0

    async def process_websocket_message(self, symbol: str, message: dict):
        """处理WebSocket深度更新消息"""
        try:
            self.message_stats['total_received'] += 1

            # 验证消息格式
            if not self._validate_depth_message(message):
                self.logger.warning("❌ 无效的深度更新消息", symbol=symbol, message=message)
                return

            # 提取序列号
            first_update_id = message.get('U')  # 第一次更新ID
            last_update_id = message.get('u')   # 最后一次更新ID

            # 现货序列号验证逻辑
            if not await self._validate_spot_sequence(symbol, first_update_id, last_update_id):
                return

            # 处理深度更新
            await self._process_depth_update(symbol, message)

            # 更新序列号
            self.last_update_ids[symbol] = last_update_id
            self.message_stats['total_processed'] += 1

        except Exception as e:
            self.logger.error("❌ 处理WebSocket消息异常", symbol=symbol, error=str(e))

    async def _apply_snapshot(self, symbol: str, snapshot_data: dict, state):
        """应用快照（兼容基类接口，不使用）"""
        return

    async def _apply_update(self, symbol: str, update: dict, state):
        """应用更新（兼容基类接口，不使用）"""
        return

    async def _fetch_initial_snapshot(self, symbol: str):
        """获取初始订单簿快照（Binance现货 /api/v3/depth）"""
        url = f"{self.api_base_url}/api/v3/depth"
        params = {
            'symbol': symbol,
            'limit': self.depth_limit
        }
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        self.logger.warning("⚠️ 获取现货快照失败", symbol=symbol, status=resp.status)
                        return None
                    data = await resp.json()
                    # 期待字段: lastUpdateId, bids, asks
                    if 'lastUpdateId' in data and 'bids' in data and 'asks' in data:
                        return data
                    self.logger.warning("⚠️ 快照字段不完整", symbol=symbol)
                    return None
        except Exception as e:
            self.logger.error("❌ 获取现货快照异常", symbol=symbol, error=str(e))
            return None

    async def _apply_snapshot_to_local_orderbook(self, symbol: str, snapshot: dict):
        """将REST快照应用到本地订单簿（OrderedDict）"""
        try:
            self.local_orderbooks[symbol]['bids'].clear()
            self.local_orderbooks[symbol]['asks'].clear()

            for bid in snapshot.get('bids', []):
                price = Decimal(str(bid[0]))
                quantity = Decimal(str(bid[1]))
                if quantity > 0:
                    self.local_orderbooks[symbol]['bids'][price] = quantity

            for ask in snapshot.get('asks', []):
                price = Decimal(str(ask[0]))
                quantity = Decimal(str(ask[1]))
                if quantity > 0:
                    self.local_orderbooks[symbol]['asks'][price] = quantity

            # 排序
            self.local_orderbooks[symbol]['bids'] = OrderedDict(
                sorted(self.local_orderbooks[symbol]['bids'].items(), key=lambda x: x[0], reverse=True)
            )
            self.local_orderbooks[symbol]['asks'] = OrderedDict(
                sorted(self.local_orderbooks[symbol]['asks'].items(), key=lambda x: x[0])
            )

            self.last_update_ids[symbol] = snapshot.get('lastUpdateId', 0)
        except Exception as e:
            self.logger.error("❌ 应用现货快照到本地簿失败", symbol=symbol, error=str(e))

    async def _validate_message_sequence(self, symbol: str, message: dict, state) -> bool:
        """验证消息序列 - 使用现货特有的序列号验证"""
        first_update_id = message.get('U')
        last_update_id = message.get('u')
        return await self._validate_spot_sequence(symbol, first_update_id, last_update_id)

    async def _perform_reconnection(self) -> bool:
        """执行重连 - 重新连接WebSocket Stream"""
        try:
            self.logger.info("🔄 执行WebSocket Stream重连")
            await self._connect_websocket_stream()
            return True
        except Exception as e:
            self.logger.error("❌ WebSocket Stream重连失败", error=str(e))
            return False

    async def stop(self):
        """停止WebSocket Stream订单簿管理器"""
        self.logger.info("🛑 停止Binance现货订单簿管理器（WebSocket Stream）")

        # 设置停止状态（同时设置基类和本类的状态）
        self.running = False
        self._is_running = False  # 设置基类的运行状态

        # 关闭WebSocket Stream连接
        await self._close_websocket_stream()

        # 输出统计信息
        self.logger.info("📊 WebSocket消息处理器结束",
                        total_received=self.message_stats['total_received'],
                        total_processed=self.message_stats['total_processed'],
                        depth_updates=self.message_stats['depth_updates'],
                        sequence_errors=self.message_stats['sequence_errors'],
                        orderbook_rebuilds=self.message_stats['orderbook_rebuilds'])

        self.logger.info("✅ WebSocket Stream订单簿管理器已停止")

    # ==================== WebSocket Stream 相关方法 ====================

    async def _connect_websocket_stream(self):
        """连接WebSocket Stream"""
        try:
            # 构建流订阅URL
            streams = [f"{symbol.lower()}@depth@100ms" for symbol in self.symbols]
            stream_params = "/".join(streams)
            url = f"{self.ws_stream_url}?streams={stream_params}"

            self.logger.info("🔗 建立WebSocket Stream连接", url=url)

            # 连接WebSocket（统一策略：Binance标准心跳 from WSPolicyContext）
            self.ws_client = await websockets.connect(
                url,
                **(self._ws_ctx.ws_connect_kwargs if getattr(self, '_ws_ctx', None) else {})
            )
            self.ws_connected = True

            self.logger.info("✅ WebSocket Stream连接成功")

            # 启动消息处理循环
            asyncio.create_task(self._websocket_message_loop())

        except Exception as e:
            self.logger.error("❌ WebSocket Stream连接失败", error=str(e))
            self.ws_connected = False
            raise

    async def _websocket_message_loop(self):
        """WebSocket消息处理循环"""
        try:
            self.logger.debug("🔄 WebSocket消息处理循环启动")

            async for message in self.ws_client:
                if not self.running:
                    break

                try:
                    # 解析消息
                    data = json.loads(message)

                    # 处理组合流消息格式（统一解包）
                    stream_name = data.get('stream')
                    message_data = unwrap_combined_stream_message(data)

                    if stream_name:
                        # 提取symbol
                        symbol = stream_name.split('@')[0].upper()

                        # 处理深度更新消息
                        if '@depth' in stream_name:
                            await self.process_websocket_message(symbol, message_data)

                except json.JSONDecodeError as e:
                    self.logger.warning("❌ JSON解析失败", error=str(e))
                except Exception as e:
                    self.logger.error("❌ 消息处理异常", error=str(e))

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning("⚠️ WebSocket连接已关闭", close_code=getattr(e, 'code', None), close_reason=getattr(e, 'reason', None))
            self.ws_connected = False
            # 触发重连尝试（使用基类重连框架）
            try:
                await self._on_connection_lost(reason="websocket_connection_closed")
            except Exception:
                pass
        except Exception as e:
            self.logger.error("❌ WebSocket消息循环异常", error=str(e))
            self.ws_connected = False
            try:
                await self._on_connection_lost(reason="websocket_loop_exception")
            except Exception:
                pass

    async def _reinitialize_orderbook(self, symbol: str):
        """重新初始化订单簿：清空本地簿并尝试快速获取快照"""
        try:
            self.logger.info("🔄 重新初始化现货订单簿", symbol=symbol)
            # 清空本地簿
            self.local_orderbooks[symbol]['bids'].clear()
            self.local_orderbooks[symbol]['asks'].clear()
            self.last_update_ids[symbol] = 0

            # 尝试短超时获取快照
            snapshot = None
            try:
                snapshot = await asyncio.wait_for(self._fetch_initial_snapshot(symbol), timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning("⏰ 获取现货快照超时，等待后续消息重建", symbol=symbol)

            if snapshot:
                await self._apply_snapshot_to_local_orderbook(symbol, snapshot)
                self.logger.info("✅ 现货订单簿重新初始化完成", symbol=symbol, lastUpdateId=snapshot.get('lastUpdateId'))
            else:
                self.logger.info("ℹ️ 未获取到快照，将从后续消息开始重建", symbol=symbol)
        except Exception as e:
            self.logger.error("❌ 现货订单簿重新初始化失败", symbol=symbol, error=str(e))
            self.logger.error("❌ WebSocket消息循环异常", error=str(e))
            self.ws_connected = False
            try:
                await self._on_connection_lost(reason="websocket_loop_exception")
            except Exception:
                pass

    async def _close_websocket_stream(self):
        """关闭WebSocket Stream连接"""
        if self.ws_client:
            try:
                await self.ws_client.close()
                self.logger.info("✅ WebSocket Stream连接已关闭")
            except Exception as e:
                self.logger.error("❌ 关闭WebSocket连接异常", error=str(e))
            finally:
                self.ws_client = None
                self.ws_connected = False

    # ==================== 现货特有的序列号验证和数据处理 ====================

    async def _validate_spot_sequence(self, symbol: str, first_update_id: int, last_update_id: int) -> bool:
        """
        现货序列号验证逻辑（简化但保留丢包检测）
        文档参考：如果 event.U > 本地 last_update_id + 1 则说明丢包，应触发重建
        """
        current_update_id = self.last_update_ids.get(symbol, 0)

        # 初始化：如果本地为0，接受并建立序列号链
        if current_update_id == 0:
            self.logger.info(f"🔗 {symbol}初始化序列号链", U=first_update_id, u=last_update_id)
            return True

        # 过期消息
        if last_update_id <= current_update_id:
            self.logger.debug(f"🔄 {symbol}忽略过期消息",
                              current_id=current_update_id,
                              last_update_id=last_update_id)
            return False

        # 丢包检测
        if first_update_id > current_update_id + 1:
            self.logger.warning(f"⚠️ {symbol}检测到丢包，触发重新初始化",
                                current_id=current_update_id,
                                first_update_id=first_update_id,
                                gap=first_update_id - current_update_id - 1)
            self.message_stats['sequence_errors'] += 1
            self.message_stats['orderbook_rebuilds'] += 1
            await self._reinitialize_orderbook(symbol)
            return False  # 丢包后当前消息先丢弃，等待重建

        return True

    def _validate_depth_message(self, message: dict) -> bool:
        """验证深度更新消息格式"""
        required_fields = ['e', 'E', 's', 'U', 'u', 'b', 'a']
        return all(field in message for field in required_fields)

    async def _process_depth_update(self, symbol: str, message: dict):
        """处理深度更新消息：应用到本地簿并发布完整快照（前400档）"""
        try:
            bids_data = message.get('b', [])
            asks_data = message.get('a', [])
            u = message.get('u')
            E_ms = message.get('E', 0)
            self._last_event_time_ms[symbol] = E_ms

            # 应用到本地订单簿
            for price, qty in bids_data:
                p = Decimal(price)
                q = Decimal(qty)
                if q == 0:
                    self.local_orderbooks[symbol]['bids'].pop(p, None)
                else:
                    self.local_orderbooks[symbol]['bids'][p] = q

            for price, qty in asks_data:
                p = Decimal(price)
                q = Decimal(qty)
                if q == 0:
                    self.local_orderbooks[symbol]['asks'].pop(p, None)
                else:
                    self.local_orderbooks[symbol]['asks'][p] = q

            # 重新排序
            self.local_orderbooks[symbol]['bids'] = OrderedDict(
                sorted(self.local_orderbooks[symbol]['bids'].items(), key=lambda x: x[0], reverse=True)
            )
            self.local_orderbooks[symbol]['asks'] = OrderedDict(
                sorted(self.local_orderbooks[symbol]['asks'].items(), key=lambda x: x[0])
            )

            # 更新序列号
            self.last_update_ids[symbol] = u

            # 构建完整快照（前400档）
            from ..data_types import PriceLevel
            bids = [PriceLevel(price=price, quantity=qty) for price, qty in list(self.local_orderbooks[symbol]['bids'].items())[:400]]
            asks = [PriceLevel(price=price, quantity=qty) for price, qty in list(self.local_orderbooks[symbol]['asks'].items())[:400]]

            event_dt = datetime.fromtimestamp(E_ms / 1000, tz=timezone.utc) if E_ms else datetime.now(timezone.utc)

            enhanced_orderbook = EnhancedOrderBook(
                exchange_name="binance_spot",
                market_type="spot",
                symbol_name=symbol,
                update_type="update",
                last_update_id=u,
                bids=bids,
                asks=asks,
                timestamp=event_dt,
                depth_levels=len(bids) + len(asks),
                is_valid=True
            )

            # 标准化并发布
            normalized_data = self.normalizer.normalize_orderbook(
                exchange="binance_spot",
                market_type="spot",
                symbol=symbol,
                orderbook=enhanced_orderbook
            )

            if normalized_data:
                await self._publish_to_nats(symbol, normalized_data)
                self.message_stats['depth_updates'] += 1
                self.logger.debug(f"🔄 {symbol}应用增量并发布本地快照",
                                  u=u,
                                  bids_count=len(bids),
                                  asks_count=len(asks))

        except Exception as e:
            self.logger.error(f"❌ {symbol}深度更新处理失败", error=str(e))

    async def _publish_to_nats(self, symbol: str, normalized_data: dict):
        """推送数据到NATS"""
        try:
            success = await self.nats_publisher.publish_orderbook(
                exchange="binance_spot",
                market_type="spot",
                symbol=symbol,
                orderbook_data=normalized_data
            )

            if success:
                self.logger.debug(f"✅ {symbol}订单簿NATS推送成功")
            else:
                self.logger.warning(f"⚠️ {symbol}订单簿NATS推送失败")

        except Exception as e:
            self.logger.error(f"❌ {symbol}订单簿NATS推送异常", error=str(e))

    def _get_unique_key(self, symbol: str) -> str:
        """生成唯一键"""
        return f"binance_spot_spot_{symbol}"



