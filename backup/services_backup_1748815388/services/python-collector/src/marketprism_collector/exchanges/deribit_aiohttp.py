"""
Deribit交易所适配器 - aiohttp WebSocket版本

使用aiohttp WebSocket解决Deribit连接问题
"""

import json
import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, Callable
import structlog
import aiohttp

from ..types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedKline, 
    NormalizedTicker, DataType, OrderBookEntry, ExchangeConfig
)


class DeribitAiohttpAdapter:
    """Deribit交易所适配器 - 使用aiohttp WebSocket"""
    
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.logger = structlog.get_logger(__name__).bind(exchange="deribit_aiohttp")
        
        # 连接状态
        self.is_connected = False
        self.is_running = False
        self.session = None
        self.ws_connection = None
        self.reconnect_count = 0
        
        # Deribit特定配置
        self.request_id = 1
        
        # 回调函数
        self.callbacks = {
            DataType.TRADE: [],
            DataType.ORDERBOOK: [],
            DataType.TICKER: [],
            DataType.KLINE: [],
            DataType.FUNDING_RATE: [],
            DataType.OPEN_INTEREST: [],
            DataType.LIQUIDATION: []
        }
        
        # 统计信息
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'errors': 0,
            'connected_at': None,
            'last_message_time': None
        }
    
    async def start(self) -> bool:
        """启动适配器"""
        try:
            self.logger.info("启动Deribit适配器")
            self.is_running = True
            
            # 连接WebSocket
            success = await self.connect()
            if success:
                # 订阅数据流
                await self.subscribe_data_streams()
                return True
            
            return False
            
        except Exception as e:
            self.logger.error("启动Deribit适配器失败", error=str(e))
            return False
    
    async def stop(self):
        """停止适配器"""
        try:
            self.logger.info("停止Deribit适配器")
            self.is_running = False
            self.is_connected = False
            
            # 关闭WebSocket连接
            if self.ws_connection:
                await self.ws_connection.close()
            
            # 关闭HTTP会话
            if self.session:
                await self.session.close()
                
        except Exception as e:
            self.logger.error("停止Deribit适配器失败", error=str(e))
    
    async def connect(self) -> bool:
        """连接WebSocket"""
        try:
            self.logger.info("连接Deribit WebSocket", url=self.config.ws_url)
            
            # 获取代理设置
            proxy = None
            http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
            https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
            
            if https_proxy or http_proxy:
                proxy = https_proxy or http_proxy
                self.logger.info("使用代理连接Deribit", proxy=proxy)
            
            # 创建HTTP会话
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
            # 连接WebSocket
            self.ws_connection = await self.session.ws_connect(
                self.config.ws_url,
                proxy=proxy,
                ssl=False,  # 禁用SSL验证以解决连接问题
                heartbeat=30
            )
            
            self.is_connected = True
            self.stats['connected_at'] = datetime.utcnow()
            self.reconnect_count = 0
            
            self.logger.info("Deribit WebSocket连接成功")
            
            # 启动消息处理循环
            asyncio.create_task(self._message_loop())
            
            return True
            
        except Exception as e:
            self.logger.error("Deribit WebSocket连接失败", error=str(e))
            self.is_connected = False
            return False
    
    async def _message_loop(self):
        """消息处理循环"""
        try:
            async for msg in self.ws_connection:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._process_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error("WebSocket错误", error=msg.data)
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    self.logger.warning("WebSocket连接关闭")
                    break
                    
        except Exception as e:
            self.logger.error("消息循环错误", error=str(e))
            self.stats['errors'] += 1
        finally:
            self.is_connected = False
            if self.is_running:
                await self._handle_reconnect()
    
    async def _process_message(self, message: str):
        """处理接收到的消息"""
        try:
            self.stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.utcnow()
            
            # 解析JSON消息
            data = json.loads(message)
            
            # 处理不同类型的数据
            await self.handle_message(data)
            
            self.stats['messages_processed'] += 1
            
        except Exception as e:
            self.logger.error("处理消息失败", error=str(e), message=message[:200])
            self.stats['errors'] += 1
    
    async def _handle_reconnect(self):
        """处理重连"""
        if self.reconnect_count >= self.config.reconnect_attempts:
            self.logger.error("达到最大重连次数，停止重连")
            return
        
        self.reconnect_count += 1
        self.logger.info(
            "尝试重连Deribit", 
            attempt=self.reconnect_count,
            max_attempts=self.config.reconnect_attempts
        )
        
        # 等待重连延迟
        await asyncio.sleep(self.config.reconnect_delay)
        
        # 尝试重连
        success = await self.connect()
        if success:
            await self.subscribe_data_streams()
    
    async def subscribe_data_streams(self):
        """订阅Deribit数据流"""
        try:
            # Deribit使用JSON-RPC 2.0格式
            channels = []
            
            for symbol in self.config.symbols:
                # 根据配置的数据类型订阅相应流
                if DataType.TRADE in self.config.data_types:
                    # 使用公开的交易数据流，不需要认证
                    channels.append(f"trades.{symbol}.100ms")
                
                if DataType.ORDERBOOK in self.config.data_types:
                    channels.append(f"book.{symbol}.none.20.100ms")
                
                if DataType.TICKER in self.config.data_types:
                    # 使用公开的ticker数据流
                    channels.append(f"ticker.{symbol}.100ms")
            
            # 发送订阅请求
            subscribe_msg = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "public/subscribe",
                "params": {
                    "channels": channels
                }
            }
            
            await self.ws_connection.send_str(json.dumps(subscribe_msg))
            self.request_id += 1
            
            self.logger.info("已订阅Deribit数据流", channels=channels)
            
        except Exception as e:
            self.logger.error("订阅Deribit数据流失败", error=str(e))
            raise
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理Deribit消息"""
        try:
            # 记录所有接收到的消息
            self.logger.info("收到Deribit消息", message_type=type(data).__name__, data_keys=list(data.keys()) if isinstance(data, dict) else "non-dict")
            
            # 跳过RPC响应消息
            if "id" in data and "result" in data:
                self.logger.info("Deribit订阅确认", result=data["result"])
                return
            
            # 处理通知消息
            if "method" in data and data["method"] == "subscription":
                params = data["params"]
                channel = params["channel"]
                data_item = params["data"]
                
                self.logger.info("处理订阅数据", channel=channel, data_type=type(data_item).__name__)
                
                if channel.startswith("trades."):
                    # 处理交易数据
                    if isinstance(data_item, list):
                        for trade_data in data_item:
                            trade = await self.normalize_trade(trade_data, channel)
                            if trade:
                                await self._emit_data(DataType.TRADE, trade)
                    else:
                        trade = await self.normalize_trade(data_item, channel)
                        if trade:
                            await self._emit_data(DataType.TRADE, trade)
                
                elif channel.startswith("book."):
                    # 处理订单簿数据
                    orderbook = await self.normalize_orderbook(data_item, channel)
                    if orderbook:
                        await self._emit_data(DataType.ORDERBOOK, orderbook)
                
                elif channel.startswith("ticker."):
                    # 处理行情数据
                    ticker = await self.normalize_ticker(data_item, channel)
                    if ticker:
                        await self._emit_data(DataType.TICKER, ticker)
            else:
                # 记录未处理的消息类型
                self.logger.warning("未处理的消息类型", data=str(data)[:500])
            
        except Exception as e:
            self.logger.error("处理Deribit消息失败", error=str(e), data=str(data)[:200])
    
    async def normalize_trade(self, raw_data: Dict[str, Any], channel: str) -> Optional[NormalizedTrade]:
        """标准化Deribit交易数据"""
        try:
            # 从channel中提取symbol
            symbol = channel.split(".")[1]
            
            price = self._safe_decimal(raw_data["price"])
            quantity = self._safe_decimal(raw_data["amount"])
            
            return NormalizedTrade(
                exchange_name="deribit",
                symbol_name=symbol,
                trade_id=str(raw_data["trade_id"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,  # 计算成交金额
                timestamp=self._safe_timestamp(raw_data["timestamp"]),
                is_buyer_maker=raw_data["direction"] == "sell"  # Deribit: sell=maker买入
            )
            
        except Exception as e:
            self.logger.error("标准化Deribit交易数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_orderbook(self, raw_data: Dict[str, Any], channel: str) -> Optional[NormalizedOrderBook]:
        """标准化Deribit订单簿数据"""
        try:
            # 从channel中提取symbol
            symbol = channel.split(".")[1]
            
            # Deribit订单簿格式
            bids = [
                OrderBookEntry(
                    price=self._safe_decimal(bid[0]),
                    quantity=self._safe_decimal(bid[1])
                )
                for bid in raw_data.get("bids", [])
            ]
            
            asks = [
                OrderBookEntry(
                    price=self._safe_decimal(ask[0]),
                    quantity=self._safe_decimal(ask[1])
                )
                for ask in raw_data.get("asks", [])
            ]
            
            return NormalizedOrderBook(
                exchange_name="deribit",
                symbol_name=symbol,
                bids=bids,
                asks=asks,
                timestamp=self._safe_timestamp(raw_data["timestamp"])
            )
            
        except Exception as e:
            self.logger.error("标准化Deribit订单簿数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_ticker(self, raw_data: Dict[str, Any], channel: str) -> Optional[NormalizedTicker]:
        """标准化Deribit行情数据"""
        try:
            # 从channel中提取symbol
            symbol = channel.split(".")[1]
            
            last_price = self._safe_decimal(raw_data["last_price"])
            
            # Deribit提供的字段有限，需要计算或使用默认值
            price_change = self._safe_decimal(raw_data.get("price_change", "0"))
            price_change_percent = self._safe_decimal(raw_data.get("price_change_percent", "0"))
            high_price = self._safe_decimal(raw_data.get("high", last_price))
            low_price = self._safe_decimal(raw_data.get("low", last_price))
            volume = self._safe_decimal(raw_data.get("volume", "0"))
            volume_usd = self._safe_decimal(raw_data.get("volume_usd", "0"))
            
            # Deribit不提供的字段使用合理默认值
            open_price = last_price - price_change if price_change else last_price
            weighted_avg = volume_usd / volume if volume > 0 else last_price
            
            # 买卖盘信息（如果没有提供使用last_price）
            bid_price = self._safe_decimal(raw_data.get("best_bid_price", last_price))
            ask_price = self._safe_decimal(raw_data.get("best_ask_price", last_price))
            bid_amount = self._safe_decimal(raw_data.get("best_bid_amount", "0"))
            ask_amount = self._safe_decimal(raw_data.get("best_ask_amount", "0"))
            
            ts = self._safe_timestamp(raw_data["timestamp"])
            
            return NormalizedTicker(
                exchange_name="deribit",
                symbol_name=symbol,
                last_price=last_price,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                volume=volume,
                quote_volume=volume_usd,
                price_change=price_change,
                price_change_percent=price_change_percent,
                weighted_avg_price=weighted_avg,
                last_quantity=Decimal("0"),  # Deribit不提供
                best_bid_price=bid_price,
                best_bid_quantity=bid_amount,
                best_ask_price=ask_price,
                best_ask_quantity=ask_amount,
                open_time=ts - timedelta(hours=24),  # 24小时前
                close_time=ts,
                first_trade_id=None,  # Deribit不提供
                last_trade_id=None,   # Deribit不提供
                trade_count=0,        # Deribit不提供
                timestamp=ts
            )
            
        except Exception as e:
            self.logger.error("标准化Deribit行情数据失败", error=str(e), raw_data=raw_data)
            return None
    
    def register_callback(self, data_type: DataType, callback: Callable):
        """注册数据回调函数"""
        self.callbacks[data_type].append(callback)
    
    async def _emit_data(self, data_type: DataType, data: Any):
        """发送数据到回调函数"""
        for callback in self.callbacks[data_type]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(
                    "回调函数执行失败",
                    data_type=data_type.value,
                    error=str(e)
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'is_connected': self.is_connected,
            'reconnect_count': self.reconnect_count,
            'exchange': self.config.exchange.value,
            'market_type': self.config.market_type.value
        }
    
    # 工具方法
    
    def _safe_decimal(self, value: Any) -> Decimal:
        """安全转换为Decimal"""
        try:
            if value is None or value == '':
                return Decimal('0')
            return Decimal(str(value))
        except:
            return Decimal('0')
    
    def _safe_int(self, value: Any) -> int:
        """安全转换为int"""
        try:
            if value is None or value == '':
                return 0
            return int(float(str(value)))
        except:
            return 0
    
    def _safe_timestamp(self, timestamp: Any) -> datetime:
        """安全转换时间戳"""
        try:
            if isinstance(timestamp, (int, float)):
                # 处理毫秒时间戳
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
                return datetime.utcfromtimestamp(timestamp)
            else:
                return datetime.utcnow()
        except:
            return datetime.utcnow() 