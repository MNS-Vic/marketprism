"""
OKXDerivativesTradesManager - OKX衍生品逐笔成交数据管理器
借鉴OrderBook Manager的成功架构模式
"""

import asyncio
import orjson  # 🚀 性能优化：使用 orjson 替换标准库 json（2-3x 性能提升）
import websockets
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Any



from .base_trades_manager import BaseTradesManager, TradeData
from collector.data_types import Exchange, MarketType

from exchanges.common.ws_message_utils import unwrap_combined_stream_message


class OKXDerivativesTradesManager(BaseTradesManager):
    """
    OKX衍生品逐笔成交数据管理器
    订阅trades频道，处理衍生品成交数据
    """

    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        super().__init__(
            exchange=Exchange.OKX_DERIVATIVES,
            market_type=MarketType.PERPETUAL,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # OKX衍生品WebSocket配置
        self.ws_url = config.get('ws_url', "wss://ws.okx.com:8443/ws/v5/public")
        self.websocket = None

        # 连接管理配置（统一策略）
        self.ws_connect_kwargs = (self._ws_ctx.ws_connect_kwargs if getattr(self, '_ws_ctx', None) else {})
        self.use_text_ping = (self._ws_ctx.use_text_ping if getattr(self, '_ws_ctx', None) else False)
        self.connection_timeout = config.get('connection_timeout', 10)

        self.logger.info("🏗️ OKX衍生品成交数据管理器初始化完成",
                        symbols=symbols,
                        ws_url=self.ws_url)

    async def start(self) -> bool:
        """启动OKX衍生品成交数据管理器"""
        try:
            self.logger.info("🚀 启动OKX衍生品成交数据管理器")

            self.is_running = True
            self.websocket_task = asyncio.create_task(self._connect_websocket())

            self.logger.info("✅ OKX衍生品成交数据管理器启动成功")
            return True

        except Exception as e:
            self.logger.error(f"❌ OKX衍生品成交数据管理器启动失败: {e}")
            return False

    async def stop(self):
        """停止OKX衍生品成交数据管理器"""
        try:
            self.logger.info("🛑 停止OKX衍生品成交数据管理器")

            self.is_running = False

            if self.websocket:
                await self.websocket.close()

            if self.websocket_task:
                self.websocket_task.cancel()
                try:
                    await self.websocket_task
                except asyncio.CancelledError:
                    pass

            self.logger.info("✅ OKX衍生品成交数据管理器已停止")

        except Exception as e:
            self.logger.error(f"❌ 停止OKX衍生品成交数据管理器失败: {e}")

    async def _connect_websocket(self):
        """连接OKX衍生品WebSocket"""
        while self.is_running:
            try:
                self.logger.info("🔌 连接OKX衍生品成交WebSocket", url=self.ws_url)

                # 统一策略下的连接参数
                async with websockets.connect(
                    self.ws_url,
                    **self.ws_connect_kwargs,
                ) as websocket:
                    self.websocket = websocket
                    self.logger.info("✅ OKX衍生品成交WebSocket连接成功")

                    # 订阅成交数据
                    await self._subscribe_trades()

                    # 启动心跳与消息监听（如使用文本心跳则启动runner）
                    if getattr(self, '_ws_ctx', None) and self._ws_ctx.use_text_ping:
                        self._ws_ctx.bind(self.websocket, lambda: self.is_running)
                        self._ws_ctx.start_heartbeat()
                    # 重连成功后的统一回调
                    try:
                        await self._on_reconnected()
                    except Exception as e:
                        self.logger.warning("_on_reconnected 钩子执行出错", error=str(e))
                    await self._listen_messages()

            except Exception as e:
                self.logger.error(f"❌ OKX衍生品成交WebSocket连接失败: {e}")
                if self.is_running:
                    self.logger.info("🔄 5秒后重新连接...")
                    await asyncio.sleep(5)

    # 心跳循环迁移到 TextHeartbeatRunner，由 _listen_messages 中配合处理 pong

    async def _subscribe_trades(self):
        """订阅OKX衍生品成交数据"""
        try:
            # 构建订阅消息
            subscribe_msg = {
                "op": "subscribe",
                "args": [
                    {
                        "channel": "trades",
                        "instId": symbol
                    } for symbol in self.symbols
                ]
            }

            await self.websocket.send(orjson.dumps(subscribe_msg).decode('utf-8'))
            self.logger.info("📊 已订阅OKX衍生品成交数据", symbols=self.symbols)

        except Exception as e:
            self.logger.error(f"❌ 订阅OKX衍生品成交数据失败: {e}")

    async def _listen_messages(self):
        """监听WebSocket消息"""
        try:
            async for message in self.websocket:
                if not self.is_running:
                    break

                # 心跳：处理pong与更新时间（统一心跳runner）
                if getattr(self, '_ws_ctx', None) and self._ws_ctx.handle_incoming(message):
                    continue
                if getattr(self, '_ws_ctx', None):
                    self._ws_ctx.notify_inbound()

                try:
                    data = orjson.loads(message)
                    await self._process_trade_message(data)

                except (orjson.JSONDecodeError, ValueError) as e:  # orjson 抛出 ValueError
                    self.logger.error(f"❌ JSON解析失败: {e}")
                except Exception as e:
                    self.logger.error(f"❌ 处理消息失败: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("⚠️ OKX衍生品成交WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听消息失败: {e}")

    async def _process_trade_message(self, message: Dict[str, Any]):
        """处理OKX衍生品成交消息"""
        try:
            message = unwrap_combined_stream_message(message)
            # 跳过订阅确认消息
            if 'event' in message:
                if message.get('event') == 'subscribe':
                    self.logger.info("✅ OKX衍生品成交数据订阅确认")
                return

            # 处理成交数据
            if 'data' not in message or 'arg' not in message:
                return

            arg = message.get('arg', {})
            if arg.get('channel') != 'trades':
                return

            symbol = arg.get('instId')
            if not symbol or symbol not in self.symbols:
                return

            self.stats['trades_received'] += 1

            for trade_item in message.get('data', []):
                # OKX 衍生品 trades 消息与现货一致，时间戳为毫秒
                trade_data = TradeData(
                    symbol=symbol,
                    price=Decimal(str(trade_item.get('px', '0'))),
                    quantity=Decimal(str(trade_item.get('sz', '0'))),
                    timestamp=datetime.fromtimestamp(
                        int(trade_item.get('ts', '0')) / 1000,
                        tz=timezone.utc
                    ),
                    side=trade_item.get('side', 'unknown'),
                    trade_id=str(trade_item.get('tradeId', '')),
                    exchange=self.exchange.value,
                    market_type=self.market_type.value
                )

                await self._publish_trade(trade_data)
                self.stats['trades_processed'] += 1

                self.logger.debug(
                    f"✅ 处理OKX衍生品成交: {symbol}",
                    price=str(trade_data.price),
                    quantity=str(trade_data.quantity),
                    side=trade_data.side
                )

        except Exception as e:
            await self._handle_error("UNKNOWN", "成交数据处理", str(e))

    async def _on_reconnected(self) -> None:
        """重连成功后，重新订阅trades，并复位心跳统计。
        注意：本方法不处理任何消息内容，消息处理应在 _listen_messages/_process_trade_message 中完成。
        """
        try:
            if self.websocket:
                await self._subscribe_trades()
            if getattr(self, '_ws_ctx', None) and self._ws_ctx.use_text_ping and self._ws_ctx.heartbeat:
                hb = self._ws_ctx.heartbeat
                hb.last_message_time = time.time()
                hb.last_outbound_time = 0.0
                hb.waiting_for_pong = False
                hb.ping_sent_time = 0.0
                hb.total_pings_sent = 0
                hb.total_pongs_received = 0
        except Exception as e:
            self.logger.warning("_on_reconnected 执行失败", error=str(e))
        # 不进行任何消息级别处理，以免引用未定义的变量
        return
