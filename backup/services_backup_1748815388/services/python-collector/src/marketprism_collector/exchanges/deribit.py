"""
Deribit交易所适配器

实现Deribit衍生品交易所的数据收集功能
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base import ExchangeAdapter
from ..types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedKline, 
    NormalizedTicker, DataType, OrderBookEntry
)


class DeribitAdapter(ExchangeAdapter):
    """Deribit交易所适配器"""
    
    def __init__(self, config):
        super().__init__(config)
        self.logger = structlog.get_logger(__name__).bind(exchange="deribit")
        
        # Deribit特定配置
        self.request_id = 1
        
    async def subscribe_data_streams(self):
        """订阅Deribit数据流"""
        try:
            # Deribit使用JSON-RPC 2.0格式
            channels = []
            
            for symbol in self.config.symbols:
                # 根据配置的数据类型订阅相应流
                if DataType.TRADE in self.config.data_types:
                    channels.append(f"trades.{symbol}.raw")
                
                if DataType.ORDERBOOK in self.config.data_types:
                    channels.append(f"book.{symbol}.none.20.100ms")
                
                if DataType.TICKER in self.config.data_types:
                    channels.append(f"ticker.{symbol}.raw")
            
            # 发送订阅请求
            subscribe_msg = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "public/subscribe",
                "params": {
                    "channels": channels
                }
            }
            
            await self.ws_connection.send(json.dumps(subscribe_msg))
            self.request_id += 1
            
            self.logger.info("已订阅Deribit数据流", channels=channels)
            
        except Exception as e:
            self.logger.error("订阅Deribit数据流失败", error=str(e))
            raise
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理Deribit消息"""
        try:
            # 跳过RPC响应消息
            if "id" in data and "result" in data:
                self.logger.info("Deribit订阅确认", result=data["result"])
                return
            
            # 处理通知消息
            if "method" in data and data["method"] == "subscription":
                params = data["params"]
                channel = params["channel"]
                data_item = params["data"]
                
                if channel.startswith("trades."):
                    # 处理交易数据
                    for trade_data in data_item:
                        trade = await self.normalize_trade(trade_data, channel)
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
                side=raw_data["direction"]  # Deribit提供direction字段: "buy" 或 "sell"
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
    
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化Deribit K线数据"""
        try:
            # Deribit暂不支持K线数据流，需要通过API获取
            return None
            
        except Exception as e:
            self.logger.error("标准化Deribit K线数据失败", error=str(e), raw_data=raw_data)
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