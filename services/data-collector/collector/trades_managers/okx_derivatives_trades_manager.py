"""
OKXDerivativesTradesManager - OKX衍生品逐笔成交数据管理器
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

        # 连接管理配置
        self.heartbeat_interval = config.get('heartbeat_interval', 25)  # OKX推荐25秒
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
                self.logger.info("🔌 连接OKX衍生品成交WebSocket",
                               url=self.ws_url)

                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    self.logger.info("✅ OKX衍生品成交WebSocket连接成功")

                    # 订阅成交数据
                    await self._subscribe_trades()

                    # 开始监听消息
                    await self._listen_messages()
                    
            except Exception as e:
                self.logger.error(f"❌ OKX衍生品成交WebSocket连接失败: {e}")
                if self.is_running:
                    self.logger.info("🔄 5秒后重新连接...")
                    await asyncio.sleep(5)

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
            
            await self.websocket.send(json.dumps(subscribe_msg))
            self.logger.info("📊 已订阅OKX衍生品成交数据", symbols=self.symbols)
            
        except Exception as e:
            self.logger.error(f"❌ 订阅OKX衍生品成交数据失败: {e}")

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
            self.logger.warning("⚠️ OKX衍生品成交WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听消息失败: {e}")

    async def _process_trade_message(self, message: Dict[str, Any]):
        """处理OKX衍生品成交消息"""
        try:
            # 跳过订阅确认消息
            if 'event' in message:
                if message.get('event') == 'subscribe':
                    self.logger.info("✅ OKX衍生品成交数据订阅确认")
                elif message.get('event') == 'error':
                    self.logger.error("❌ OKX衍生品订阅失败", error=message)
                return

            # 处理成交数据
            if 'data' not in message or 'arg' not in message:
                self.logger.debug("跳过非数据消息", message_keys=list(message.keys()))
                return

            arg = message.get('arg', {})
            if arg.get('channel') != 'trades':
                self.logger.debug("跳过非trades频道消息", channel=arg.get('channel'))
                return

            symbol = arg.get('instId')
            if not symbol:
                self.logger.warning("消息缺少instId字段", arg=arg)
                return

            # 🔧 调试日志：symbol检查
            if symbol not in self.symbols:
                self.logger.warning("⚠️ [DEBUG] OKX衍生品symbol不在订阅列表中",
                                  symbol=symbol,
                                  subscribed_symbols=self.symbols,
                                  channel=arg.get('channel'))
                return

            self.stats['trades_received'] += 1

            # 处理成交数据数组
            for trade_item in message.get('data', []):
                # OKX衍生品trades消息格式
                # {
                #   "instId": "BTC-USDT-SWAP",
                #   "tradeId": "130639474",
                #   "px": "42219.9",
                #   "sz": "100",
                #   "side": "buy",
                #   "ts": "1629386781174"
                # }

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

                # 发布成交数据
                await self._publish_trade(trade_data)
                self.stats['trades_processed'] += 1

                self.logger.debug(f"✅ 处理OKX衍生品成交: {symbol}",
                                price=str(trade_data.price),
                                quantity=str(trade_data.quantity),
                                side=trade_data.side)
            
        except Exception as e:
            await self._handle_error("UNKNOWN", "成交数据处理", str(e))
