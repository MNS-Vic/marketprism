"""
BinanceDerivativesLiquidationManager - Binance衍生品强平订单数据管理器

重构为全市场模式，基于Binance官方文档：
https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams

WebSocket频道：!forceOrder@arr (全市场强平流)
数据格式：包含所有交易对的强平数据，客户端进行过滤
更新频率：实时推送所有市场的强平事件
优势：持续的数据流，便于区分技术问题和市场现象
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Set

from .base_liquidation_manager import BaseLiquidationManager
from collector.data_types import Exchange, MarketType, NormalizedLiquidation
from exchanges.common.ws_message_utils import unwrap_combined_stream_message


class BinanceDerivativesLiquidationManager(BaseLiquidationManager):
    """
    Binance衍生品强平订单数据管理器 - 全市场模式

    订阅Binance的!forceOrder@arr频道，接收所有交易对的强平数据
    在接收端进行symbol过滤，只处理指定的交易对
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化Binance衍生品强平管理器 - 全市场模式

        Args:
            symbols: 目标交易对列表（如 ['BTCUSDT', 'ETHUSDT']）- 用于过滤
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.BINANCE_DERIVATIVES,
            market_type=MarketType.PERPETUAL,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # Binance WebSocket配置（容错：若给的是域名则自动补 /ws）
        raw_ws_url = config.get('ws_url', "wss://fstream.binance.com/ws")
        if raw_ws_url.endswith('/ws') or raw_ws_url.endswith('/stream'):
            self.ws_url = raw_ws_url
        else:
            # 兼容传入为域名/根路径的情况，例如 wss://fstream.binance.com
            self.ws_url = raw_ws_url.rstrip('/') + '/ws'

        # Binance特定配置
        self.heartbeat_interval = config.get('heartbeat_interval', 180)  # Binance衍生品推荐180秒
        self.connection_timeout = config.get('connection_timeout', 10)

        # 🔧 修复：消息处理配置
        self.message_queue = asyncio.Queue(maxsize=1000)  # 限制队列大小防止内存溢出
        self.message_processor_task = None

        # 全市场模式配置
        self.all_market_stream = "!forceOrder@arr"  # 全市场强平流
        self.target_symbols = set(symbol.upper() for symbol in symbols)  # 目标交易对集合

        # 🔧 修复：统计信息 - 确保与基类字段名称一致
        self.stats = {
            # 基类期望的字段
            'liquidations_received': 0,
            'liquidations_processed': 0,
            'liquidations_published': 0,
            'errors': 0,
            'last_liquidation_time': None,
            'connection_errors': 0,
            'reconnections': 0,
            'data_validation_errors': 0,
            'nats_publish_errors': 0,

            # Binance特有的字段
            'total_received': 0,      # 总接收消息数
            'filtered_messages': 0,   # 过滤后的消息数
            'target_symbols_data': 0, # 目标交易对数据数
            'other_symbols_data': 0,  # 其他交易对数据数
            'json_errors': 0,         # JSON解析错误
            'processing_errors': 0,   # 处理错误
            'queue_full_drops': 0     # 队列满丢弃的消息
        }

        self.logger.startup(
            "Binance衍生品强平管理器初始化完成",
            mode="全市场模式",
            target_symbols=list(self.target_symbols),
            stream=self.all_market_stream,
            ws_url=self.ws_url,
            heartbeat_interval=self.heartbeat_interval
        )

    def _get_connection_duration(self) -> str:
        """获取连接持续时间"""
        if self.last_successful_connection:
            duration = datetime.now(timezone.utc) - self.last_successful_connection
            return f"{duration.total_seconds():.1f}s"
        return "未连接"

    async def _connect_and_listen(self):
        """连接Binance WebSocket并监听强平数据 - 修复为简单可靠模式"""
        try:
            # 使用正确的Binance全市场强平WebSocket URL
            full_url = f"{self.ws_url}/{self.all_market_stream}"

            self.logger.info(
                "连接Binance全市场强平WebSocket",
                url=full_url,
                mode="全市场模式",
                target_symbols=list(self.target_symbols)
            )

            # 🔧 修复：使用 async with 模式，与 trade 管理器保持一致
            async with websockets.connect(
                full_url,
                ping_interval=20,  # 与 trade 管理器一致
                ping_timeout=10,
                close_timeout=10
            ) as websocket:
                self.websocket = websocket
                self.last_successful_connection = datetime.now(timezone.utc)
                self.reconnect_attempts = 0

                self.logger.info(
                    "Binance全市场强平WebSocket连接成功",
                    url=full_url,
                    connection_time=self.last_successful_connection.isoformat()
                )

                # 订阅强平数据（对于Binance全市场流，这是空操作）
                await self._subscribe_liquidation_data()

                # 🔧 修复：直接监听消息，不使用复杂的队列处理
                await self._listen_messages()

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("Binance强平WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"Binance强平WebSocket连接失败: {e}")
            if self.is_running:
                self.logger.info("🔄 5秒后重新连接...")
                await asyncio.sleep(5)

    async def _subscribe_liquidation_data(self):
        """
        订阅Binance强平数据

        对于Binance全市场强平流(!forceOrder@arr)，不需要发送订阅消息，
        连接后会自动接收所有交易对的强平数据
        """
        self.logger.info(
            "Binance全市场强平流已连接",
            stream=self.all_market_stream,
            mode="全市场模式",
            note="无需发送订阅消息，将自动接收所有强平数据"
        )

    async def _listen_messages(self):
        """监听WebSocket消息 - 修复为简单直接处理模式"""
        try:
            async for message in self.websocket:
                if not self.is_running:
                    break

                try:
                    data = json.loads(message)
                    await self._process_liquidation_message(data)

                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ JSON解析失败: {e}")
                except Exception as e:
                    self.logger.error(f"❌ 处理消息失败: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("⚠️ Binance强平WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听消息失败: {e}")

    async def _process_liquidation_message(self, message: dict):
        """处理Binance强平消息 - 修复为简单直接处理"""
        try:
            self.stats['liquidations_received'] = self.stats.get('liquidations_received', 0) + 1

            # 检查是否是强平数据
            if message.get('e') != 'forceOrder':
                self.logger.debug("跳过非forceOrder消息", event_type=message.get('e'))
                return

            # 提取强平数据
            order_data = message.get('o', {})
            symbol = order_data.get('s', '').upper()

            if not symbol:
                self.logger.warning("强平消息缺少symbol字段", message_keys=list(message.keys()))
                return

            # 检查是否是目标交易对
            # 统一使用标准化后的符号在基类过滤，避免与本地预过滤不一致
            if not self.all_symbol_mode:
                normalized = self.normalizer.normalize_symbol_format(symbol, 'binance_derivatives')
                # 基类 _should_process_symbol 会处理 BTCUSDT 与 BTC-USDT 的等价
                if not self._should_process_symbol(normalized):
                    self.logger.debug("跳过非目标交易对", symbol=symbol, normalized=normalized, target_symbols=list(self.target_symbols))
                    return

            # 解析并标准化强平数据
            normalized_liquidation = await self._parse_liquidation_message(message)
            if normalized_liquidation:
                await self._process_liquidation_data(normalized_liquidation)
                self.stats['liquidations_processed'] = self.stats.get('liquidations_processed', 0) + 1

                self.logger.data_processed(
                    "Binance强平数据处理完成",
                    symbol=symbol,
                    side=order_data.get('S'),
                    quantity=order_data.get('q'),
                    price=order_data.get('p')
                )

        except Exception as e:
            self.logger.error(
                "处理Binance强平消息失败",
                error=e,
                message_preview=str(message)[:200]
            )
            self.stats['errors'] = self.stats.get('errors', 0) + 1

    async def _process_message(self, message: str):
        """🔧 修复：处理单个WebSocket消息"""
        try:
            # 🔧 修复：解析JSON消息
            data = json.loads(message)

            # 🔧 修复：验证消息格式
            if not isinstance(data, dict):
                self.logger.warning("收到非字典格式消息", message_type=type(data).__name__)
                return

            # 🔧 修复：处理全市场强平数据
            await self._process_all_market_liquidation(data)

        except json.JSONDecodeError as e:
            self.logger.error(
                "Binance消息JSON解析失败",
                error=e,
                message_preview=message[:200] if len(message) > 200 else message,
                message_length=len(message)
            )
            self.stats['json_errors'] += 1
            self.stats['errors'] += 1  # 基类期望的字段
        except Exception as e:
            self.logger.error(
                "处理Binance消息失败",
                error=e,
                error_type=type(e).__name__,
                message_preview=message[:200] if len(message) > 200 else message
            )
            self.stats['processing_errors'] += 1
            self.stats['errors'] += 1  # 基类期望的字段



    async def _parse_liquidation_message(self, message: dict) -> Optional[NormalizedLiquidation]:
        """
        解析Binance强平消息并返回标准化数据

        注意：在全市场模式下，这个方法主要用于兼容基类接口
        实际的数据处理在_process_all_market_liquidation中进行

        Args:
            message: Binance WebSocket原始消息

        Returns:
            标准化的强平数据对象（全市场模式下可能返回None）
        """
        try:
            # 🔧 修复：Binance 强平消息格式是 message['o']，不是 message['data']['o']
            if 'o' in message:
                liquidation_data = message['o']
                symbol = liquidation_data.get('s', '').upper()

                # 只处理目标交易对（或 all_symbol_mode）
                if self.all_symbol_mode or symbol in self.target_symbols:
                    # 标准化器期望完整的消息格式，包含"o"字段
                    return self.normalizer.normalize_binance_liquidation(message)

            return None

        except Exception as e:
            self.logger.error(
                "解析Binance强平消息失败",
                error=e,
                message_preview=str(message)[:200]
            )
            return None

    async def stop(self):
        """🔧 修复：停止Binance强平管理器"""
        self.logger.info("开始停止Binance强平管理器")

        # 🔧 修复：停止消息处理器
        if hasattr(self, 'message_processor_task') and self.message_processor_task and not self.message_processor_task.done():
            self.logger.info("取消消息处理器任务")
            self.message_processor_task.cancel()
            try:
                await asyncio.wait_for(self.message_processor_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                self.logger.warning("停止消息处理器时发生异常", error=e)

        # 🔧 修复：清空消息队列
        if hasattr(self, 'message_queue'):
            queue_size = self.message_queue.qsize()
            if queue_size > 0:
                self.logger.info(f"清空消息队列，剩余 {queue_size} 条消息")
                while not self.message_queue.empty():
                    try:
                        self.message_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

        # 调用父类停止方法
        await super().stop()

        self.logger.info("Binance强平管理器已停止", final_stats=self.get_stats())

    async def _process_all_market_liquidation(self, data: dict):
        """处理全市场强平数据（兼容 /ws 与 /stream 两种返回结构）"""
        try:
            # 可能的两种结构：
            # 1) /stream?streams=!forceOrder@arr → {"stream":"!forceOrder@arr","data":{...}}
            # 2) /ws/!forceOrder@arr → 直接为事件对象 {"e":"forceOrder", "o": {...}}
            payload = unwrap_combined_stream_message(data)
            if not isinstance(payload, dict):
                return

            # 校验事件类型与字段
            if payload.get('e') != 'forceOrder' or 'o' not in payload:
                return

            liquidation_data = payload['o']
            symbol = str(liquidation_data.get('s', '')).upper()

            # 🔧 修复：支持 all-symbol 模式和筛选模式
            if self.all_symbol_mode:
                # all-symbol 模式：处理所有强平数据
                self.stats['target_symbols_data'] += 1
                self.stats['liquidations_processed'] += 1  # 基类期望的字段
                await self._process_target_liquidation(liquidation_data)

                # 定期记录统计信息
                if self.stats['target_symbols_data'] % 10 == 0:
                    self.logger.debug(
                        "all-symbol模式强平数据统计",
                        symbol=symbol,
                        side=liquidation_data.get('S'),
                        quantity=liquidation_data.get('q'),
                        price=liquidation_data.get('p'),
                        total_processed=self.stats['target_symbols_data']
                    )
            else:
                # 筛选模式：只处理目标交易对
                if symbol in self.target_symbols:
                    self.stats['target_symbols_data'] += 1
                    self.stats['liquidations_processed'] += 1  # 基类期望的字段
                    await self._process_target_liquidation(liquidation_data)
                else:
                    self.stats['other_symbols_data'] += 1
                    # 记录其他交易对的数据（用于监控）
                    if self.stats['other_symbols_data'] % 50 == 0:  # 每50条记录一次
                        self.logger.debug(
                            "接收到其他交易对强平数据",
                            symbol=symbol,
                            side=liquidation_data.get('S'),
                            quantity=liquidation_data.get('q'),
                            price=liquidation_data.get('p')
                        )

        except Exception as e:
            self.logger.error("处理全市场强平数据失败", error=e, data=data)

    async def _process_target_liquidation(self, liquidation_data: dict):
        """处理目标交易对的强平数据"""
        try:
            # 统一改为委托 normalizer（就地完成时间戳统一为UTC毫秒字符串）
            # 构造通用格式数据（从 Binance 的 "o" 字段中提取）
            liquidation_raw = {
                'E': liquidation_data.get('E'),  # 事件时间
                'o': liquidation_data  # 订单数据
            }

            # 使用通用的强平数据标准化方法
            norm = self.normalizer.normalize_liquidation(
                exchange="binance_derivatives",
                market_type="perpetual",
                symbol=liquidation_data.get('s', ''),
                raw_data=liquidation_raw
            )

            # 封装为 NormalizedLiquidation 对象（保持与基类兼容）
            from collector.data_types import LiquidationSide as TradeSide
            from datetime import datetime, timezone
            from decimal import Decimal

            def dec_or_none(x):
                try:
                    return Decimal(str(x)) if x is not None else None
                except Exception:
                    return None

            # 解析交易方向
            side_str = norm.get('side', '').lower()
            trade_side = TradeSide.BUY if side_str == 'buy' else TradeSide.SELL

            normalized_data = NormalizedLiquidation(
                exchange_name="binance_derivatives",
                symbol_name=norm.get('symbol', liquidation_data.get('s', '')),
                product_type="perpetual",
                instrument_id=norm.get('instrument_id', liquidation_data.get('s', '')),
                side=trade_side,
                quantity=dec_or_none(norm.get('quantity')) or Decimal('0'),
                price=dec_or_none(norm.get('price')) or Decimal('0'),
                liquidation_type=norm.get('liquidation_type', 'forced'),
                order_status=norm.get('order_status', 'filled'),
                timestamp=datetime.now(timezone.utc),  # 占位，发布时用 norm 的字符串字段
                raw_data=liquidation_data
            )

            if normalized_data:
                # 🔧 修复：使用基类的处理逻辑，包含 symbol 筛选和 all-symbol 模式支持
                await self._process_liquidation_data(normalized_data)

                # 🔧 修复：更新发布统计
                self.stats['liquidations_published'] += 1  # 基类期望的字段

                self.logger.debug(
                    "Binance强平数据处理完成(委托 normalizer)",
                    symbol=normalized_data.symbol_name,
                    side=normalized_data.side.value,
                    quantity=str(normalized_data.quantity),
                    price=str(normalized_data.price),
                    aggregation_mode='all-symbol' if self.all_symbol_mode else 'filtered'
                )

        except Exception as e:
            self.logger.error("处理目标强平数据失败", error=e, data=liquidation_data)

    def get_stats(self) -> Dict[str, Any]:
        """🔧 修复：获取详细统计信息"""
        total = max(self.stats.get('total_received', 0), 1)
        target_data = self.stats.get('target_symbols_data', 0)

        return {
            **self.stats,
            'filter_rate': f"{(target_data / total * 100):.2f}%",
            'target_symbols': list(self.target_symbols),
            'all_symbol_mode': self.all_symbol_mode,
            'mode': 'all-symbol模式' if self.all_symbol_mode else '筛选模式',
            'ws_url': self.ws_url,
            'stream': self.all_market_stream,
            'heartbeat_interval': self.heartbeat_interval,
            'message_queue_size': self.message_queue.qsize() if hasattr(self, 'message_queue') else 0,
            'message_queue_maxsize': self.message_queue.maxsize if hasattr(self, 'message_queue') else 0,
            'connection_duration': self._get_connection_duration(),
            'last_successful_connection': self.last_successful_connection.isoformat() if self.last_successful_connection else None,
            'is_connected': self.is_connected if hasattr(self, 'websocket') else False,
            'is_running': self.is_running,
            'reconnect_attempts': getattr(self, 'reconnect_attempts', 0),
            'processor_task_running': (
                hasattr(self, 'message_processor_task') and
                self.message_processor_task and
                not self.message_processor_task.done()
            )
        }
