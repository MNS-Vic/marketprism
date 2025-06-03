"""
Binance交易所适配器

实现Binance现货交易所的数据收集功能
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


class BinanceAdapter(ExchangeAdapter):
    """Binance交易所适配器"""
    
    def __init__(self, config):
        super().__init__(config)
        self.logger = structlog.get_logger(__name__).bind(exchange="binance")
        
        # Binance特定配置
        self.stream_names = []
        self.symbol_map = {}  # 符号映射
        
    async def subscribe_data_streams(self):
        """订阅Binance数据流"""
        try:
            streams = []
            
            for symbol in self.config.symbols:
                # 转换符号格式 (BTC-USDT -> BTCUSDT -> btcusdt)
                binance_symbol = symbol.replace("-", "").lower()
                self.symbol_map[binance_symbol] = symbol
                # 同时映射大写格式 BTCUSDT -> BTC-USDT
                self.symbol_map[symbol.replace("-", "")] = symbol
                
                # 根据配置的数据类型订阅相应流
                if DataType.TRADE in self.config.data_types:
                    streams.append(f"{binance_symbol}@trade")
                
                if DataType.ORDERBOOK in self.config.data_types:
                    streams.append(f"{binance_symbol}@depth@100ms")  # 增量深度流
                
                if DataType.TICKER in self.config.data_types:
                    streams.append(f"{binance_symbol}@ticker")
                
                if DataType.LIQUIDATION in self.config.data_types:
                    # 币安强平订单流 - 单个交易对
                    streams.append(f"{binance_symbol}@forceOrder")
            
            # 如果需要强平数据，也可以订阅全市场强平流
            if DataType.LIQUIDATION in self.config.data_types:
                # 全市场强平订单流 (可选，获取所有交易对的强平数据)
                streams.append("!forceOrder@arr")
            
            # 发送订阅消息
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": streams,
                "id": 1
            }
            
            await self.ws_connection.send(json.dumps(subscribe_msg))
            self.logger.info("已订阅数据流", streams=streams)
            
        except Exception as e:
            self.logger.error("订阅数据流失败", error=str(e))
            raise
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理Binance消息"""
        try:
            # 跳过订阅确认消息
            if "result" in data or "id" in data:
                self.logger.debug("收到订阅确认消息", data=data)
                return
            
            # 处理组合流消息格式 (stream + data)
            if "stream" in data and "data" in data:
                stream = data["stream"]
                stream_data = data["data"]
                
                # 添加调试日志
                if "@depth" in stream:
                    self.logger.debug("收到深度数据", stream=stream, update_id=stream_data.get("u", "N/A"))
                
                # 解析流类型
                if "@trade" in stream:
                    trade = await self.normalize_trade(stream_data)
                    if trade:
                        await self._emit_data(DataType.TRADE, trade)
                
                elif "@depth" in stream:
                    # 发送原始数据给OrderBook Manager
                    symbol = self.symbol_map.get(stream_data["s"].lower(), stream_data["s"])
                    self.logger.info("发送原始深度数据", symbol=symbol, update_id=stream_data.get("u"))
                    await self._emit_raw_data('depth', 'binance', symbol, stream_data)
                    
                    # 标准化并发送给NATS
                    orderbook = await self.normalize_orderbook(stream_data)
                    if orderbook:
                        await self._emit_data(DataType.ORDERBOOK, orderbook)
                
                elif "@ticker" in stream:
                    ticker = await self.normalize_ticker(stream_data)
                    if ticker:
                        await self._emit_data(DataType.TICKER, ticker)
                
                elif "@forceOrder" in stream:
                    # 处理强平订单数据
                    liquidation = await self.normalize_liquidation(stream_data)
                    if liquidation:
                        await self._emit_data(DataType.LIQUIDATION, liquidation)
            
            # 处理单一流消息格式 (直接事件)
            elif "e" in data:
                event_type = data["e"]
                
                if event_type == "trade":
                    trade = await self.normalize_trade(data)
                    if trade:
                        await self._emit_data(DataType.TRADE, trade)
                
                elif event_type == "depthUpdate":
                    self.logger.debug("收到增量深度数据", symbol=data.get("s"), update_id=data.get("u", "N/A"))
                    
                    # 发送原始数据给OrderBook Manager
                    symbol = self.symbol_map.get(data["s"].lower(), data["s"])
                    await self._emit_raw_data('depth', 'binance', symbol, data)
                    
                    # 标准化并发送给NATS
                    orderbook = await self.normalize_orderbook(data)
                    if orderbook:
                        await self._emit_data(DataType.ORDERBOOK, orderbook)
                
                elif event_type == "24hrTicker":
                    ticker = await self.normalize_ticker(data)
                    if ticker:
                        await self._emit_data(DataType.TICKER, ticker)
                
                elif event_type == "forceOrder":
                    # 处理强平订单事件
                    liquidation = await self.normalize_liquidation(data)
                    if liquidation:
                        await self._emit_data(DataType.LIQUIDATION, liquidation)
                
                else:
                    self.logger.debug("收到未知事件类型", event_type=event_type)
            
            else:
                self.logger.debug("收到未知格式消息", data=str(data)[:200])
            
        except Exception as e:
            self.logger.error("处理消息失败", error=str(e), data=str(data)[:200])
    
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        """标准化交易数据"""
        try:
            symbol = self.symbol_map.get(raw_data["s"].lower(), raw_data["s"])
            
            price = self._safe_decimal(raw_data["p"])
            quantity = self._safe_decimal(raw_data["q"])
            
            return NormalizedTrade(
                exchange_name="binance",
                symbol_name=symbol,
                trade_id=str(raw_data["t"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,  # 计算成交金额
                timestamp=self._safe_timestamp(raw_data["T"]),
                side="sell" if raw_data["m"] else "buy"  # m=true表示买方是maker，即卖单成交
            )
            
        except Exception as e:
            self.logger.error("标准化交易数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_orderbook(self, raw_data: Dict[str, Any]) -> Optional[NormalizedOrderBook]:
        """标准化订单簿数据"""
        try:
            symbol = self.symbol_map.get(raw_data["s"].lower(), raw_data["s"])
            
            # 处理买单和卖单
            bids = [
                OrderBookEntry(
                    price=self._safe_decimal(bid[0]),
                    quantity=self._safe_decimal(bid[1])
                )
                for bid in raw_data.get("b", [])
            ]
            
            asks = [
                OrderBookEntry(
                    price=self._safe_decimal(ask[0]),
                    quantity=self._safe_decimal(ask[1])
                )
                for ask in raw_data.get("a", [])
            ]
            
            # 创建增强订单簿对象
            from ..types import EnhancedOrderBook, OrderBookUpdateType
            
            return EnhancedOrderBook(
                exchange_name="binance",
                symbol_name=symbol,
                bids=bids,
                asks=asks,
                timestamp=self._safe_timestamp(raw_data.get("E", None)),
                last_update_id=raw_data.get("u", 0),
                first_update_id=raw_data.get("U", None),
                update_type=OrderBookUpdateType.DELTA,
                depth_levels=len(bids) + len(asks),
                is_valid=True
            )
            
        except Exception as e:
            self.logger.error("标准化订单簿数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化K线数据"""
        try:
            # Binance K线数据格式
            kline_data = raw_data["k"]
            symbol = self.symbol_map.get(kline_data["s"].lower(), kline_data["s"])
            
            return NormalizedKline(
                exchange_name="binance",
                symbol_name=symbol,
                interval=kline_data["i"],
                open_time=self._safe_timestamp(kline_data["t"]),
                close_time=self._safe_timestamp(kline_data["T"]),
                open_price=self._safe_decimal(kline_data["o"]),
                high_price=self._safe_decimal(kline_data["h"]),
                low_price=self._safe_decimal(kline_data["l"]),
                close_price=self._safe_decimal(kline_data["c"]),
                volume=self._safe_decimal(kline_data["v"]),
                quote_volume=self._safe_decimal(kline_data["q"]),  # 成交额
                trade_count=self._safe_int(kline_data["n"]),
                taker_buy_volume=self._safe_decimal(kline_data["V"]),  # 主动买入成交量
                taker_buy_quote_volume=self._safe_decimal(kline_data["Q"]),  # 主动买入成交额
                is_closed=kline_data["x"]
            )
            
        except Exception as e:
            self.logger.error("标准化K线数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_ticker(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTicker]:
        """标准化行情数据"""
        try:
            symbol = self.symbol_map.get(raw_data["s"].lower(), raw_data["s"])
            
            # Binance ticker 24hr数据有完整字段
            last_price = self._safe_decimal(raw_data["c"])
            open_price = self._safe_decimal(raw_data["o"])
            high_price = self._safe_decimal(raw_data["h"])
            low_price = self._safe_decimal(raw_data["l"])
            volume = self._safe_decimal(raw_data["v"])
            quote_volume = self._safe_decimal(raw_data["q"])
            price_change = self._safe_decimal(raw_data["p"])
            price_change_percent = self._safe_decimal(raw_data["P"])
            weighted_avg_price = self._safe_decimal(raw_data["w"])
            
            # 提取更多字段
            last_qty = self._safe_decimal(raw_data["Q"])
            bid_price = self._safe_decimal(raw_data["b"])
            bid_qty = self._safe_decimal(raw_data["B"])
            ask_price = self._safe_decimal(raw_data["a"])
            ask_qty = self._safe_decimal(raw_data["A"])
            
            # 时间相关
            open_time = self._safe_timestamp(raw_data["O"])
            close_time = self._safe_timestamp(raw_data["C"])
            first_trade_id = self._safe_int(raw_data["F"])
            last_trade_id = self._safe_int(raw_data["L"])
            trade_count = self._safe_int(raw_data["n"])
            
            return NormalizedTicker(
                exchange_name="binance",
                symbol_name=symbol,
                last_price=last_price,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                volume=volume,
                quote_volume=quote_volume,
                price_change=price_change,
                price_change_percent=price_change_percent,
                weighted_avg_price=weighted_avg_price,
                last_quantity=last_qty,
                best_bid_price=bid_price,
                best_bid_quantity=bid_qty,
                best_ask_price=ask_price,
                best_ask_quantity=ask_qty,
                open_time=open_time,
                close_time=close_time,
                first_trade_id=first_trade_id,
                last_trade_id=last_trade_id,
                trade_count=trade_count,
                timestamp=close_time
            )
            
        except Exception as e:
            self.logger.error("标准化行情数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_liquidation(self, raw_data: Dict[str, Any]) -> Optional['NormalizedLiquidation']:
        """标准化币安强平数据"""
        try:
            # 导入强平数据类型
            from ..types import NormalizedLiquidation
            
            # 币安强平数据结构
            # 格式1: 嵌套格式 (WebSocket事件)
            # {
            #   "e":"forceOrder",                   // 事件类型
            #   "E":1568014460893,                  // 事件时间
            #   "o":{
            #     "s":"BTCUSDT",                   // 交易对
            #     "S":"SELL",                      // 订单方向
            #     "o":"LIMIT",                     // 订单类型
            #     "f":"IOC",                       // 有效方式
            #     "q":"0.014",                     // 订单数量
            #     "p":"9910",                      // 订单价格
            #     "ap":"9910",                     // 平均价格
            #     "X":"FILLED",                    // 订单状态
            #     "l":"0.014",                     // 订单最近成交量
            #     "z":"0.014",                     // 订单累计成交量
            #     "T":1568014460893,               // 交易时间
            #   }
            # }
            #
            # 格式2: 直接格式 (订单数据)
            # {
            #   "s":"BTCUSDT",                     // 交易对
            #   "S":"SELL",                        // 订单方向
            #   "o":"LIMIT",                       // 订单类型
            #   "f":"IOC",                         // 有效方式
            #   "q":"0.014",                       // 订单数量
            #   "p":"9910",                        // 订单价格
            #   "ap":"9910",                       // 平均价格
            #   "X":"FILLED",                      // 订单状态
            #   "l":"0.014",                       // 订单最近成交量
            #   "z":"0.014",                       // 订单累计成交量
            #   "T":1568014460893,                 // 交易时间
            # }
            
            # 判断数据格式并提取订单数据
            if "e" in raw_data and raw_data["e"] == "forceOrder" and "o" in raw_data and isinstance(raw_data["o"], dict):
                # 嵌套格式：事件包含订单数据
                order_data = raw_data["o"]
                event_time = raw_data.get("E")
            elif "s" in raw_data and "S" in raw_data:
                # 直接格式：数据本身就是订单数据
                order_data = raw_data
                event_time = None
            else:
                # 无法识别的格式
                self.logger.warning("无法识别的强平数据格式", raw_data=raw_data)
                return None
            
            # 提取基本信息
            symbol_raw = order_data["s"]
            
            # 确保symbol_map已初始化，如果没有则创建基本映射
            if not hasattr(self, 'symbol_map') or not self.symbol_map:
                self.symbol_map = {}
            
            # 创建符号映射 (BTCUSDT -> BTC-USDT)
            if symbol_raw not in self.symbol_map and symbol_raw.lower() not in self.symbol_map:
                # 尝试转换格式
                if "USDT" in symbol_raw:
                    base = symbol_raw.replace("USDT", "")
                    symbol = f"{base}-USDT"
                elif "BTC" in symbol_raw and symbol_raw != "BTC":
                    base = symbol_raw.replace("BTC", "")
                    symbol = f"{base}-BTC"
                else:
                    symbol = symbol_raw
                
                # 添加到映射
                self.symbol_map[symbol_raw] = symbol
                self.symbol_map[symbol_raw.lower()] = symbol
            else:
                symbol = self.symbol_map.get(symbol_raw.lower(), self.symbol_map.get(symbol_raw, symbol_raw))
            
            # 转换币安的方向格式到标准格式
            side = order_data["S"].lower()  # "BUY" -> "buy", "SELL" -> "sell"
            
            # 提取价格和数量
            price = self._safe_decimal(order_data.get("ap"))  # 使用平均价格
            if not price:
                price = self._safe_decimal(order_data.get("p"))  # 如果没有平均价格，使用订单价格
            
            quantity = self._safe_decimal(order_data.get("z"))  # 使用累计成交量
            if not quantity:
                quantity = self._safe_decimal(order_data.get("q"))  # 如果没有成交量，使用订单数量
            
            # 计算强平价值
            value = price * quantity if price and quantity else None
            
            # 提取时间戳 (优先使用交易时间，其次使用事件时间)
            timestamp = self._safe_timestamp(order_data.get("T", event_time))
            
            # 确定合约类型 (根据交易对判断)
            instrument_type = "futures"
            if "USDT" in symbol_raw:
                instrument_type = "futures"  # USDT本位期货
            elif any(coin in symbol_raw for coin in ["BTC", "ETH", "BNB"]):
                instrument_type = "futures"  # 币本位期货
            
            return NormalizedLiquidation(
                exchange_name="binance",
                symbol_name=symbol,
                liquidation_id=None,  # 币安不提供强平ID
                side=side,
                price=price,
                quantity=quantity,
                value=value,
                leverage=None,  # 币安强平数据不包含杠杆信息
                margin_type=None,  # 币安强平数据不包含保证金类型
                liquidation_fee=None,  # 币安强平数据不包含手续费
                instrument_type=instrument_type,
                user_id=None,  # 币安不提供用户ID
                timestamp=timestamp
            )
            
        except Exception as e:
            self.logger.error("标准化币安强平数据失败", error=str(e), raw_data=raw_data)
            return None 