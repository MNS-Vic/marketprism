"""
OKXSpotTradesManager - OKX现货逐笔成交数据管理器
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


class OKXSpotTradesManager(BaseTradesManager):
    """
    OKX现货逐笔成交数据管理器
    订阅trades频道，处理逐笔成交数据
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher):
        super().__init__(
            exchange=Exchange.OKX_SPOT,
            market_type=MarketType.SPOT,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher
        )
        
        # OKX现货WebSocket配置
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.websocket = None
        
        self.logger.info("🏗️ OKX现货成交数据管理器初始化完成",
                        symbols=symbols)

    async def start(self) -> bool:
        """启动OKX现货成交数据管理器"""
        try:
            self.logger.info("🚀 启动OKX现货成交数据管理器")
            
            self.is_running = True
            self.websocket_task = asyncio.create_task(self._connect_websocket())
            
            self.logger.info("✅ OKX现货成交数据管理器启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ OKX现货成交数据管理器启动失败: {e}")
            return False

    async def stop(self):
        """停止OKX现货成交数据管理器"""
        try:
            self.logger.info("🛑 停止OKX现货成交数据管理器")
            
            self.is_running = False
            
            if self.websocket:
                await self.websocket.close()
                
            if self.websocket_task:
                self.websocket_task.cancel()
                try:
                    await self.websocket_task
                except asyncio.CancelledError:
                    pass
                    
            self.logger.info("✅ OKX现货成交数据管理器已停止")
            
        except Exception as e:
            self.logger.error(f"❌ 停止OKX现货成交数据管理器失败: {e}")

    async def _connect_websocket(self):
        """连接OKX现货WebSocket"""
        while self.is_running:
            try:
                self.logger.info("🔌 连接OKX现货成交WebSocket",
                               url=self.ws_url)
                
                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    self.logger.info("✅ OKX现货成交WebSocket连接成功")
                    
                    # 订阅成交数据
                    await self._subscribe_trades()
                    
                    # 开始监听消息
                    await self._listen_messages()
                    
            except Exception as e:
                self.logger.error(f"❌ OKX现货成交WebSocket连接失败: {e}")
                if self.is_running:
                    self.logger.info("🔄 5秒后重新连接...")
                    await asyncio.sleep(5)

    async def _subscribe_trades(self):
        """订阅OKX现货成交数据"""
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
            self.logger.info("📊 已订阅OKX现货成交数据", symbols=self.symbols)
            
        except Exception as e:
            self.logger.error(f"❌ 订阅OKX现货成交数据失败: {e}")

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
            self.logger.warning("⚠️ OKX现货成交WebSocket连接关闭")
        except Exception as e:
            self.logger.error(f"❌ 监听消息失败: {e}")

    async def _process_trade_message(self, message: Dict[str, Any]):
        """处理OKX现货成交消息"""
        try:
            # 跳过订阅确认消息
            if 'event' in message:
                if message.get('event') == 'subscribe':
                    self.logger.info("✅ OKX现货成交数据订阅确认")
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
            
            # 处理成交数据数组
            for trade_item in message.get('data', []):
                # OKX现货trades消息格式
                # {
                #   "instId": "BTC-USDT",
                #   "tradeId": "130639474",
                #   "px": "42219.9",
                #   "sz": "0.12060306",
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
                
                self.logger.debug(f"✅ 处理OKX现货成交: {symbol}",
                                price=str(trade_data.price),
                                quantity=str(trade_data.quantity),
                                side=trade_data.side)
            
        except Exception as e:
            await self._handle_error("UNKNOWN", "成交数据处理", str(e))
