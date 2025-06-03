"""
OKX交易所适配器

实现OKX现货交易所的数据收集功能
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base import ExchangeAdapter
from ..types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedKline, 
    NormalizedTicker, DataType, OrderBookEntry,
    NormalizedFundingRate, NormalizedOpenInterest, NormalizedLiquidation
)


class OKXAdapter(ExchangeAdapter):
    """OKX交易所适配器"""
    
    def __init__(self, config):
        super().__init__(config)
        self.logger = structlog.get_logger(__name__).bind(exchange="okx")
        
        # OKX特定配置
        self.symbol_map = {}  # 符号映射
        
    async def subscribe_data_streams(self):
        """订阅OKX数据流"""
        try:
            # OKX使用不同的订阅格式
            subscribe_requests = []
            
            for symbol in self.config.symbols:
                # OKX符号格式已经是正确的 (BTC-USDT)
                okx_symbol = symbol
                self.symbol_map[okx_symbol] = symbol
                
                # 根据配置的数据类型订阅相应流
                if DataType.TRADE in self.config.data_types:
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "trades",
                            "instId": okx_symbol
                        }]
                    })
                
                if DataType.ORDERBOOK in self.config.data_types:
                    subscribe_requests.append({
                        "op": "subscribe", 
                        "args": [{
                            "channel": "books",
                            "instId": okx_symbol
                        }]
                    })
                
                if DataType.TICKER in self.config.data_types:
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "tickers",
                            "instId": okx_symbol
                        }]
                    })
                
                # 订阅期货相关数据流
                if DataType.FUNDING_RATE in self.config.data_types:
                    # 检查是否为期货合约 (SWAP合约)
                    swap_symbol = symbol + "-SWAP"
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "funding-rate",
                            "instId": swap_symbol
                        }]
                    })
                
                if DataType.OPEN_INTEREST in self.config.data_types:
                    # 持仓量数据 (期货合约)
                    swap_symbol = symbol + "-SWAP"
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "open-interest",
                            "instId": swap_symbol
                        }]
                    })
                
                if DataType.LIQUIDATION in self.config.data_types:
                    # 强平数据
                    swap_symbol = symbol + "-SWAP"
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "liquidation-orders",
                            "instId": swap_symbol
                        }]
                    })
            
            # 发送所有订阅请求
            for request in subscribe_requests:
                await self.ws_connection.send(json.dumps(request))
                self.logger.debug("发送OKX订阅请求", request=request)
                
            self.logger.info("已订阅OKX数据流", count=len(subscribe_requests))
            
        except Exception as e:
            self.logger.error("订阅OKX数据流失败", error=str(e))
            raise
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理OKX消息"""
        try:
            # 跳过订阅确认消息
            if "event" in data:
                if data["event"] == "subscribe":
                    self.logger.info("OKX订阅确认", channel=data.get("arg", {}).get("channel"))
                return
            
            # 处理数据消息
            if "arg" in data and "data" in data:
                channel = data["arg"]["channel"]
                inst_id = data["arg"]["instId"]
                data_list = data["data"]
                
                for item in data_list:
                    if channel == "trades":
                        trade = await self.normalize_trade(item, inst_id)
                        if trade:
                            await self._emit_data(DataType.TRADE, trade)
                    
                    elif channel == "books":
                        orderbook = await self.normalize_orderbook(item, inst_id)
                        if orderbook:
                            await self._emit_data(DataType.ORDERBOOK, orderbook)
                    
                    elif channel == "tickers":
                        ticker = await self.normalize_ticker(item, inst_id)
                        if ticker:
                            await self._emit_data(DataType.TICKER, ticker)
                    
                    elif channel == "funding-rate":
                        funding_rate = await self.normalize_funding_rate(item, inst_id)
                        if funding_rate:
                            await self._emit_data(DataType.FUNDING_RATE, funding_rate)
                    
                    elif channel == "open-interest":
                        open_interest = await self.normalize_open_interest(item, inst_id)
                        if open_interest:
                            await self._emit_data(DataType.OPEN_INTEREST, open_interest)
                    
                    elif channel == "liquidation-orders":
                        liquidation = await self.normalize_liquidation(item, inst_id)
                        if liquidation:
                            await self._emit_data(DataType.LIQUIDATION, liquidation)
            
        except Exception as e:
            self.logger.error("处理OKX消息失败", error=str(e), data=str(data)[:200])
    
    async def normalize_trade(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedTrade]:
        """标准化OKX交易数据"""
        try:
            symbol = self.symbol_map.get(inst_id, inst_id)
            
            price = self._safe_decimal(raw_data["px"])
            quantity = self._safe_decimal(raw_data["sz"])
            
            return NormalizedTrade(
                exchange_name="okx",
                symbol_name=symbol,
                trade_id=str(raw_data["tradeId"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,  # 计算成交金额
                timestamp=self._safe_timestamp(int(raw_data["ts"])),
                side=raw_data["side"]  # OKX直接提供side字段: "buy" 或 "sell"
            )
            
        except Exception as e:
            self.logger.error("标准化OKX交易数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_orderbook(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedOrderBook]:
        """标准化OKX订单簿数据"""
        try:
            symbol = self.symbol_map.get(inst_id, inst_id)
            
            # OKX订单簿格式
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
                exchange_name="okx",
                symbol_name=symbol,
                bids=bids,
                asks=asks,
                timestamp=self._safe_timestamp(int(raw_data["ts"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX订单簿数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化OKX K线数据"""
        try:
            # OKX K线数据格式 [ts, o, h, l, c, vol, volCcy]
            return NormalizedKline(
                exchange_name="okx",
                symbol_name=raw_data["instId"],
                interval="1m",  # 需要从配置获取
                open_time=self._safe_timestamp(int(raw_data[0])),
                close_time=self._safe_timestamp(int(raw_data[0]) + 60000),  # 假设1分钟
                open_price=self._safe_decimal(raw_data[1]),
                high_price=self._safe_decimal(raw_data[2]),
                low_price=self._safe_decimal(raw_data[3]),
                close_price=self._safe_decimal(raw_data[4]),
                volume=self._safe_decimal(raw_data[5]),
                trade_count=0,  # OKX不提供交易次数
                is_closed=True
            )
            
        except Exception as e:
            self.logger.error("标准化OKX K线数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_ticker(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedTicker]:
        """标准化OKX行情数据"""
        try:
            symbol = self.symbol_map.get(inst_id, inst_id)
            
            # 从原始数据中提取值，提供默认值以确保所有必填字段都有值
            last_price = self._safe_decimal(raw_data["last"])
            open24h = self._safe_decimal(raw_data.get("open24h", raw_data["last"]))
            high24h = self._safe_decimal(raw_data["high24h"])
            low24h = self._safe_decimal(raw_data["low24h"])
            vol24h = self._safe_decimal(raw_data["vol24h"])
            volCcy24h = self._safe_decimal(raw_data["volCcy24h"])
            
            # 计算价格变动
            price_change = last_price - open24h
            price_change_percent = (price_change / open24h * 100) if open24h > 0 else Decimal("0")
            
            # 提取最新交易量
            last_qty = self._safe_decimal(raw_data.get("lastSz", "0"))
            
            # 提取买卖盘最优价格和数量
            bid_px = self._safe_decimal(raw_data.get("bidPx", last_price))
            bid_sz = self._safe_decimal(raw_data.get("bidSz", "0"))
            ask_px = self._safe_decimal(raw_data.get("askPx", last_price))
            ask_sz = self._safe_decimal(raw_data.get("askSz", "0"))
            
            # 计算加权平均价格 (如果没有提供，使用当前价格)
            weighted_avg = volCcy24h / vol24h if vol24h > 0 else last_price
            
            # 时间戳
            ts = self._safe_timestamp(int(raw_data["ts"]))
            
            return NormalizedTicker(
                exchange_name="okx",
                symbol_name=symbol,
                last_price=last_price,
                open_price=open24h,
                high_price=high24h,
                low_price=low24h,
                volume=vol24h,
                quote_volume=volCcy24h,
                price_change=price_change,
                price_change_percent=price_change_percent,
                weighted_avg_price=weighted_avg,
                last_quantity=last_qty,
                best_bid_price=bid_px,
                best_bid_quantity=bid_sz,
                best_ask_price=ask_px,
                best_ask_quantity=ask_sz,
                open_time=ts - timedelta(hours=24),  # 24小时前
                close_time=ts,
                first_trade_id=None,  # OKX不提供
                last_trade_id=None,   # OKX不提供
                trade_count=0,        # OKX不提供
                timestamp=ts
            )
            
        except Exception as e:
            self.logger.error("标准化OKX行情数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_funding_rate(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedFundingRate]:
        """标准化OKX资金费率数据"""
        try:
            # 从inst_id中提取基础符号 (BTC-USDT-SWAP -> BTC-USDT)
            symbol = inst_id.replace("-SWAP", "")
            
            funding_rate = self._safe_decimal(raw_data["fundingRate"])
            next_funding_time = self._safe_timestamp(int(raw_data["nextFundingTime"]))
            mark_price = self._safe_decimal(raw_data.get("markPx", "0"))
            index_price = self._safe_decimal(raw_data.get("indexPx", "0"))
            
            return NormalizedFundingRate(
                exchange_name="okx",
                symbol_name=symbol,
                funding_rate=funding_rate,
                estimated_rate=self._safe_decimal(raw_data.get("estimatedRate")),
                next_funding_time=next_funding_time,
                mark_price=mark_price,
                index_price=index_price,
                premium_index=mark_price - index_price if mark_price and index_price else Decimal("0"),
                funding_interval="8h",  # OKX资金费率每8小时结算
                timestamp=self._safe_timestamp(int(raw_data["ts"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX资金费率数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_open_interest(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedOpenInterest]:
        """标准化OKX持仓量数据"""
        try:
            # 从inst_id中提取基础符号 (BTC-USDT-SWAP -> BTC-USDT)
            symbol = inst_id.replace("-SWAP", "")
            
            open_interest = self._safe_decimal(raw_data["oi"])
            open_interest_usd = self._safe_decimal(raw_data.get("oiCcy", "0"))
            
            return NormalizedOpenInterest(
                exchange_name="okx",
                symbol_name=symbol,
                open_interest=open_interest,
                open_interest_value=open_interest_usd,
                open_interest_value_usd=open_interest_usd,
                change_24h=None,  # OKX不提供24h变化量
                change_24h_percent=None,
                instrument_type="swap",  # OKX永续合约
                timestamp=self._safe_timestamp(int(raw_data["ts"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX持仓量数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_liquidation(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedLiquidation]:
        """标准化OKX强平数据"""
        try:
            # 从inst_id中提取基础符号 (BTC-USDT-SWAP -> BTC-USDT)
            symbol = inst_id.replace("-SWAP", "")
            
            price = self._safe_decimal(raw_data["details"][0]["bkPx"])  # 破产价格
            quantity = self._safe_decimal(raw_data["details"][0]["sz"])
            side = raw_data["details"][0]["side"]  # "long" or "short"
            
            # 转换OKX的side格式
            normalized_side = "sell" if side == "long" else "buy"
            
            return NormalizedLiquidation(
                exchange_name="okx",
                symbol_name=symbol,
                liquidation_id=raw_data.get("ordId"),
                side=normalized_side,
                price=price,
                quantity=quantity,
                value=price * quantity if price and quantity else None,
                leverage=None,  # OKX强平数据不包含杠杆信息
                margin_type=None,
                liquidation_fee=None,
                instrument_type="swap",
                timestamp=self._safe_timestamp(int(raw_data["ts"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX强平数据失败", error=str(e), raw_data=raw_data)
            return None 