"""
BinanceSpotTradesManager - Binance现货逐笔成交数据管理器
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


class BinanceSpotTradesManager(BaseTradesManager):
    """
    Binance现货逐笔成交数据管理器
    订阅trade stream，处理逐笔成交数据
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        super().__init__(
            exchange=Exchange.BINANCE_SPOT,
            market_type=MarketType.SPOT,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # Binance现货WebSocket配置
        self.ws_url = config.get('ws_url', "wss://stream.binance.com:9443/ws")
        self.websocket = None

        # 构建订阅参数
        self.streams = [f"{symbol.lower()}@trade" for symbol in symbols]
        self.stream_url = f"{self.ws_url}/{'/'.join(self.streams)}"

        # 连接管理配置
        self.heartbeat_interval = config.get('heartbeat_interval', 30)
        self.connection_timeout = config.get('connection_timeout', 10)

        self.logger.info("🏗️ Binance现货成交数据管理器初始化完成",
                        symbols=symbols,
                        streams=self.streams,
                        ws_url=self.ws_url)

    async def start(self) -> bool:
        """启动Binance现货成交数据管理器"""
        try:
            self.logger.info("🚀 启动Binance现货成交数据管理器")
            
            self.is_running = True
            self.websocket_task = asyncio.create_task(self._connect_websocket())
            
            self.logger.info("✅ Binance现货成交数据管理器启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Binance现货成交数据管理器启动失败: {e}")
            return False

    async def stop(self):
        """停止Binance现货成交数据管理器"""
        try:
            self.logger.info("🛑 停止Binance现货成交数据管理器")
            
            self.is_running = False
            
            if self.websocket:
                await self.websocket.close()
                
            if self.websocket_task:
                self.websocket_task.cancel()
                try:
                    await self.websocket_task
                except asyncio.CancelledError:
                    pass
                    
            self.logger.info("✅ Binance现货成交数据管理器已停止")
            
        except Exception as e:
            self.logger.error(f"❌ 停止Binance现货成交数据管理器失败: {e}")

    async def _connect_websocket(self):
        """连接Binance现货WebSocket - 优化重连机制"""
        reconnect_count = 0

        while self.is_running and reconnect_count < self.max_reconnect_attempts:
            try:
                self.logger.info("🔌 连接Binance现货成交WebSocket",
                               url=self.stream_url,
                               attempt=reconnect_count + 1)

                # 使用配置的连接超时
                async with websockets.connect(
                    self.stream_url,
                    timeout=self.connection_timeout
                ) as websocket:
                    self.websocket = websocket
                    self.logger.info("✅ Binance现货成交WebSocket连接成功")

                    # 重置重连计数
                    reconnect_count = 0
                    self.stats['reconnections'] += 1

                    # 开始监听消息
                    await self._listen_messages()

            except Exception as e:
                reconnect_count += 1
                self.stats['connection_errors'] += 1
                self.logger.error(f"❌ Binance现货成交WebSocket连接失败: {e}",
                                attempt=reconnect_count)

                if self.is_running and reconnect_count < self.max_reconnect_attempts:
                    delay = min(self.reconnect_delay * reconnect_count, 60)  # 最大60秒
                    self.logger.info(f"🔄 {delay}秒后重新连接...", attempt=reconnect_count)
                    await asyncio.sleep(delay)

        if reconnect_count >= self.max_reconnect_attempts:
            self.logger.error("❌ 达到最大重连次数，停止重连")
            self.is_running = False

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
            self.logger.warning("⚠️ Binance现货成交WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听消息失败: {e}")

    async def _process_trade_message(self, message: Dict[str, Any]):
        """处理Binance现货成交消息"""
        try:
            self.stats['trades_received'] += 1
            
            # Binance现货trade消息格式
            # {
            #   "e": "trade",
            #   "E": 123456789,
            #   "s": "BNBBTC",
            #   "t": 12345,
            #   "p": "0.001",
            #   "q": "100",
            #   "b": 88,
            #   "a": 50,
            #   "T": 123456785,
            #   "m": true,
            #   "M": true
            # }
            
            if message.get('e') != 'trade':
                return
                
            symbol = message.get('s')
            if not symbol or symbol not in self.symbols:
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
                trade_id=str(message.get('t', '')),
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )
            
            # 发布成交数据
            await self._publish_trade(trade_data)
            self.stats['trades_processed'] += 1
            
            self.logger.debug(f"✅ 处理Binance现货成交: {symbol}",
                            price=str(trade_data.price),
                            quantity=str(trade_data.quantity),
                            side=trade_data.side)
            
        except Exception as e:
            await self._handle_error("UNKNOWN", "成交数据处理", str(e))
