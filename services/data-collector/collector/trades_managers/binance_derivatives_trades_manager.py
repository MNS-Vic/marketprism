"""
BinanceDerivativesTradesManager - Binance衍生品逐笔成交数据管理器
借鉴OrderBook Manager的成功架构模式
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Any

from .base_trades_manager import BaseTradesManager, TradeData
from collector.data_types import Exchange, MarketType
from exchanges.common.ws_message_utils import unwrap_combined_stream_message


class BinanceDerivativesTradesManager(BaseTradesManager):
    """
    Binance衍生品逐笔成交数据管理器
    订阅aggTrade stream，处理聚合成交数据
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        super().__init__(
            exchange=Exchange.BINANCE_DERIVATIVES,
            market_type=MarketType.PERPETUAL,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # Binance衍生品WebSocket配置
        self.ws_url = config.get('ws_url', "wss://fstream.binance.com/ws")
        self.websocket = None

        # 构建订阅参数 - 使用aggTrade获取聚合成交数据
        self.streams = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
        self.stream_url = f"{self.ws_url}/{'/'.join(self.streams)}"

        # 连接管理配置
        self.heartbeat_interval = config.get('heartbeat_interval', 30)
        self.connection_timeout = config.get('connection_timeout', 10)

        self.logger.info("🏗️ Binance衍生品成交数据管理器初始化完成",
                        symbols=symbols,
                        streams=self.streams,
                        ws_url=self.ws_url)

    async def start(self) -> bool:
        """启动Binance衍生品成交数据管理器"""
        try:
            self.logger.info("🚀 启动Binance衍生品成交数据管理器")
            
            self.is_running = True
            self.websocket_task = asyncio.create_task(self._connect_websocket())
            
            self.logger.info("✅ Binance衍生品成交数据管理器启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Binance衍生品成交数据管理器启动失败: {e}")
            return False

    async def stop(self):
        """停止Binance衍生品成交数据管理器"""
        try:
            self.logger.info("🛑 停止Binance衍生品成交数据管理器")
            
            self.is_running = False
            
            if self.websocket:
                await self.websocket.close()
                
            if self.websocket_task:
                self.websocket_task.cancel()
                try:
                    await self.websocket_task
                except asyncio.CancelledError:
                    pass
                    
            self.logger.info("✅ Binance衍生品成交数据管理器已停止")
            
        except Exception as e:
            self.logger.error(f"❌ 停止Binance衍生品成交数据管理器失败: {e}")

    async def _connect_websocket(self):
        """连接Binance衍生品WebSocket"""
        while self.is_running:
            try:
                self.logger.info("🔌 连接Binance衍生品成交WebSocket", url=self.stream_url)

                async with websockets.connect(
                    self.stream_url,
                    **(self._ws_ctx.ws_connect_kwargs if getattr(self, '_ws_ctx', None) else {})
                ) as websocket:
                    self.websocket = websocket
                    self.logger.info("✅ Binance衍生品成交WebSocket连接成功")

                    # 开始监听消息
                    await self._listen_messages()
                    
            except Exception as e:
                self.logger.error(f"❌ Binance衍生品成交WebSocket连接失败: {e}")
                if self.is_running:
                    import random
                    jitter = random.uniform(0.2, 0.8)
                    self.logger.info("🔄 重连前等待(含抖动)...", base_delay=5, jitter=f"{jitter:.2f}s")
                    await asyncio.sleep(5 + jitter)

    async def _listen_messages(self):
        """监听WebSocket消息"""
        try:
            async for message in self.websocket:
                if not self.is_running:
                    break
                    
                try:
                    data = json.loads(message)
                    await self._process_trade_message(data)
                    
                except json.JSONDecodeError as e:
                    self.logger.error(f"❌ JSON解析失败: {e}")
                except Exception as e:
                    self.logger.error(f"❌ 处理消息失败: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("⚠️ Binance衍生品成交WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听消息失败: {e}")

    async def _process_trade_message(self, message: Dict[str, Any]):
        """处理Binance衍生品成交消息（兼容可能的combined streams外层包裹）"""
        try:
            self.stats['trades_received'] += 1

            # 统一预解包（若非包裹结构则原样返回）
            message = unwrap_combined_stream_message(message)

            # Binance衍生品aggTrade消息格式
            # {
            #   "e": "aggTrade",
            #   "E": 123456789,
            #   "s": "BTCUSDT",
            #   "a": 5933014,
            #   "p": "0.001",
            #   "q": "100",
            #   "f": 100,
            #   "l": 105,
            #   "T": 123456785,
            #   "m": true
            # }
            
            if message.get('e') != 'aggTrade':
                self.logger.debug("跳过非aggTrade消息", event_type=message.get('e'))
                return

            symbol = message.get('s')
            if not symbol:
                self.logger.warning("消息缺少symbol字段", message_keys=list(message.keys()))
                return

            # 🔧 调试日志：symbol检查
            if symbol not in self.symbols:
                self.logger.warning("⚠️ [DEBUG] Binance衍生品symbol不在订阅列表中",
                                  symbol=symbol,
                                  subscribed_symbols=self.symbols,
                                  message_event=message.get('e'))
                return

            # 解析成交数据
            trade_data = TradeData(
                symbol=symbol,
                price=Decimal(str(message.get('p', '0'))),
                quantity=Decimal(str(message.get('q', '0'))),
                timestamp=datetime.fromtimestamp(
                    message.get('T', 0) / 1000,
                    tz=timezone.utc
                ),
                side='sell' if message.get('m', False) else 'buy',  # m=true表示买方是maker
                trade_id=str(message.get('a', '')),  # 聚合成交ID
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )

            # 发布成交数据
            await self._publish_trade(trade_data)
            self.stats['trades_processed'] += 1

            self.logger.debug(f"✅ 处理Binance衍生品成交: {symbol}",
                            price=str(trade_data.price),
                            quantity=str(trade_data.quantity),
                            side=trade_data.side)
            
        except Exception as e:
            await self._handle_error("UNKNOWN", "成交数据处理", str(e))
