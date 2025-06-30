"""
数据标准化模块

将不同交易所的数据转换为统一格式
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from decimal import Decimal
import structlog

from .data_types import (
    NormalizedTrade, NormalizedOrderBook,
    OrderBookEntry, PriceLevel, EnhancedOrderBook, OrderBookDelta,
    OrderBookUpdateType, Exchange, EnhancedOrderBookUpdate,
    NormalizedLiquidation, LiquidationSide, LiquidationStatus, ProductType,
    NormalizedOpenInterest, NormalizedFundingRate, NormalizedTopTraderLongShortRatio,
    NormalizedMarketLongShortRatio, NormalizedVolatilityIndex
)


class DataNormalizer:
    """数据标准化器 - 集成到collector中的模块"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
    
    def _normalize_symbol_format(self, symbol: str) -> str:
        """统一交易对格式为 xxx-yyy"""
        # 如果已经是 xxx-yyy 格式，直接返回
        if "-" in symbol:
            return symbol.upper()
        
        # 处理常见的交易对格式转换
        symbol = symbol.upper()
        
        # 常见的基础货币和计价货币
        quote_currencies = ["USDT", "USDC", "BTC", "ETH", "BNB", "USD", "EUR", "GBP", "JPY"]
        
        # 尝试匹配已知的计价货币
        for quote in quote_currencies:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                if base:  # 确保基础货币不为空
                    return f"{base}-{quote}"
        
        # 如果无法识别，返回原始格式
        return symbol
    
    def normalize_enhanced_orderbook_from_snapshot(
        self, 
        exchange: str, 
        symbol: str, 
        bids: List[PriceLevel], 
        asks: List[PriceLevel],
        last_update_id: Optional[int] = None,
        checksum: Optional[int] = None
    ) -> EnhancedOrderBook:
        """从快照数据创建增强订单簿"""
        return EnhancedOrderBook(
            exchange_name=exchange,
            symbol_name=self._normalize_symbol_format(symbol),
            last_update_id=last_update_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
            update_type=OrderBookUpdateType.SNAPSHOT,
            depth_levels=len(bids) + len(asks),
            checksum=checksum,
            is_valid=True
        )
    
    def normalize_enhanced_orderbook_from_update(
        self,
        exchange: str,
        symbol: str,
        bids: List[PriceLevel],
        asks: List[PriceLevel],
        first_update_id: int,
        last_update_id: int,
        prev_update_id: Optional[int] = None,
        bid_changes: Optional[List[PriceLevel]] = None,
        ask_changes: Optional[List[PriceLevel]] = None,
        removed_bids: Optional[List[Decimal]] = None,
        removed_asks: Optional[List[Decimal]] = None
    ) -> EnhancedOrderBook:
        """从增量更新数据创建增强订单簿"""
        return EnhancedOrderBook(
            exchange_name=exchange,
            symbol_name=self._normalize_symbol_format(symbol),
            last_update_id=last_update_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
            update_type=OrderBookUpdateType.UPDATE,
            first_update_id=first_update_id,
            prev_update_id=prev_update_id,
            depth_levels=len(bids) + len(asks),
            bid_changes=bid_changes,
            ask_changes=ask_changes,
            removed_bids=removed_bids,
            removed_asks=removed_asks,
            is_valid=True
        )
    
    def create_orderbook_delta(
        self,
        exchange: str,
        symbol: str,
        update_id: int,
        bid_updates: List[PriceLevel],
        ask_updates: List[PriceLevel],
        prev_update_id: Optional[int] = None
    ) -> OrderBookDelta:
        """创建纯增量订单簿变化"""
        return OrderBookDelta(
            exchange_name=exchange,
            symbol_name=self._normalize_symbol_format(symbol),
            update_id=update_id,
            prev_update_id=prev_update_id,
            bid_updates=bid_updates,
            ask_updates=ask_updates,
            total_bid_changes=len(bid_updates),
            total_ask_changes=len(ask_updates),
            timestamp=datetime.now(timezone.utc)
        )
    
    def normalize_binance_depth_update(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化Binance深度更新数据"""
        try:
            # 解析增量数据
            bids = [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty in raw_data.get("b", [])
            ]
            asks = [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty in raw_data.get("a", [])
            ]
            
            return {
                "exchange": "binance",
                "symbol": raw_data.get("s", ""),
                "first_update_id": raw_data.get("U"),
                "last_update_id": raw_data.get("u"),
                "prev_update_id": raw_data.get("pu"),
                "bids": bids,
                "asks": asks,
                "timestamp": datetime.now(timezone.utc)
            }
        except Exception as e:
            self.logger.error(
                "标准化Binance深度更新失败",
                exc_info=True,
                raw_data=raw_data
            )
            return {}
    
    def normalize_okx_depth_update(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化OKX深度更新数据"""
        try:
            if "data" not in raw_data or not raw_data["data"]:
                return {}
            
            book_data = raw_data["data"][0]
            
            # 解析增量数据
            bids = [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty, _, _ in book_data.get("bids", [])
            ]
            asks = [
                PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                for price, qty, _, _ in book_data.get("asks", [])
            ]
            
            return {
                "exchange": "okx",
                "symbol": book_data.get("instId", ""),
                "first_update_id": int(book_data.get("seqId", 0)),
                "last_update_id": int(book_data.get("seqId", 0)),
                "prev_update_id": int(book_data.get("prevSeqId", 0)) if book_data.get("prevSeqId") else None,
                "bids": bids,
                "asks": asks,
                "checksum": int(book_data.get("checksum", 0)) if book_data.get("checksum") else None,
                "timestamp": datetime.fromtimestamp(int(book_data.get("ts", 0)) / 1000)
            }
        except Exception as e:
            self.logger.error(
                "标准化OKX深度更新失败",
                exc_info=True,
                raw_data=raw_data
            )
            return {}
    
    async def normalize_depth_update(self, raw_data: Dict[str, Any], 
                                   exchange: str, symbol: str) -> Optional[EnhancedOrderBookUpdate]:
        """统一增量深度标准化方法"""
        try:
            if exchange.lower() == 'binance':
                normalized = self.normalize_binance_depth_update(raw_data)
            elif exchange.lower() == 'okx':
                normalized = self.normalize_okx_depth_update(raw_data)
            else:
                self.logger.warning(f"Unsupported exchange for depth update: {exchange}")
                return None
            
            if not normalized:
                return None
            
            # 创建标准化的增量深度更新
            return EnhancedOrderBookUpdate(
                exchange_name=exchange.lower(),
                symbol_name=self._normalize_symbol_format(symbol),
                first_update_id=normalized.get("first_update_id"),
                last_update_id=normalized["last_update_id"],
                prev_update_id=normalized.get("prev_update_id"),
                bid_updates=normalized.get("bids", []),
                ask_updates=normalized.get("asks", []),
                total_bid_changes=len(normalized.get("bids", [])),
                total_ask_changes=len(normalized.get("asks", [])),
                checksum=normalized.get("checksum"),
                timestamp=normalized.get("timestamp", datetime.now(timezone.utc)),
                is_valid=True
            )
            
        except Exception as e:
            self.logger.error(
                "统一增量深度标准化失败",
                exchange=exchange,
                symbol=symbol,
                exc_info=True,
                raw_data=raw_data
            )
            return None
    
    def normalize_okx_trade(self, raw_data: dict, symbol: str) -> Optional[NormalizedTrade]:
        """标准化OKX交易数据"""
        try:
            if "data" not in raw_data or not raw_data["data"]:
                return None
            
            trade_data = raw_data["data"][0]  # 取第一条交易数据
            
            # 统一交易对格式为 xxx-yyy
            symbol_name = self._normalize_symbol_format(symbol)
            
            price = Decimal(trade_data["px"])
            quantity = Decimal(trade_data["sz"])
            
            return NormalizedTrade(
                exchange_name="okx",
                symbol_name=symbol_name,
                trade_id=trade_data.get("tradeId", ""),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,
                side=trade_data["side"],  # "buy" or "sell"
                timestamp=datetime.fromtimestamp(int(trade_data["ts"]) / 1000)
            )
        except Exception as e:
            self.logger.error("标准化OKX交易数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    def normalize_okx_orderbook(self, raw_data: dict, symbol: str) -> Optional[NormalizedOrderBook]:
        """标准化OKX订单簿数据"""
        try:
            if "data" not in raw_data or not raw_data["data"]:
                return None
            
            book_data = raw_data["data"][0]
            
            # 转换bids和asks
            bids = []
            for bid in book_data.get("bids", []):
                bids.append(PriceLevel(
                    price=Decimal(bid[0]),
                    quantity=Decimal(bid[1])
                ))
            
            asks = []
            for ask in book_data.get("asks", []):
                asks.append(PriceLevel(
                    price=Decimal(ask[0]),
                    quantity=Decimal(ask[1])
                ))
            
            return NormalizedOrderBook(
                exchange_name="okx",
                symbol_name=self._normalize_symbol_format(symbol),
                bids=bids,
                asks=asks,
                timestamp=datetime.fromtimestamp(int(book_data["ts"]) / 1000),
                last_update_id=int(book_data.get("seqId", 0)) if book_data.get("seqId") else None
            )
        except Exception as e:
            self.logger.error("标准化OKX订单簿数据失败", exc_info=True, raw_data=raw_data)
            return None
    

    
    def normalize_binance_trade(self, raw_data: dict) -> Optional[NormalizedTrade]:
        """标准化Binance交易数据"""
        try:
            # 统一交易对格式：BTCUSDT -> BTC-USDT
            raw_symbol = raw_data["s"]
            symbol_name = self._normalize_symbol_format(raw_symbol)
            
            price = Decimal(raw_data["p"])
            quantity = Decimal(raw_data["q"])
            
            return NormalizedTrade(
                exchange_name="binance",
                symbol_name=symbol_name,
                trade_id=str(raw_data["t"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,
                side="sell" if raw_data["m"] else "buy",  # m=true表示卖方是maker
                timestamp=datetime.fromtimestamp(raw_data["T"] / 1000)
            )
        except Exception as e:
            self.logger.error("标准化Binance交易数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    def normalize_binance_orderbook(self, raw_data: dict, symbol: str) -> Optional[NormalizedOrderBook]:
        """标准化Binance订单簿数据"""
        try:
            bids = []
            for bid in raw_data.get("bids", []):
                bids.append(PriceLevel(
                    price=Decimal(bid[0]),
                    quantity=Decimal(bid[1])
                ))
            
            asks = []
            for ask in raw_data.get("asks", []):
                asks.append(PriceLevel(
                    price=Decimal(ask[0]),
                    quantity=Decimal(ask[1])
                ))
            
            return NormalizedOrderBook(
                exchange_name="binance",
                symbol_name=self._normalize_symbol_format(symbol),
                bids=bids,
                asks=asks,
                timestamp=datetime.now(timezone.utc),  # Binance depth没有时间戳
                last_update_id=raw_data.get("lastUpdateId")
            )
        except Exception as e:
            self.logger.error("标准化Binance订单簿数据失败", exc_info=True, raw_data=raw_data)
            return None
    

    
    def convert_to_legacy_orderbook(self, enhanced_orderbook: EnhancedOrderBook) -> NormalizedOrderBook:
        """将增强订单簿转换为传统订单簿格式（向后兼容）"""
        return NormalizedOrderBook(
            exchange_name=enhanced_orderbook.exchange_name,
            symbol_name=enhanced_orderbook.symbol_name,
            last_update_id=enhanced_orderbook.last_update_id,
            bids=enhanced_orderbook.bids,
            asks=enhanced_orderbook.asks,
            timestamp=enhanced_orderbook.timestamp,
            collected_at=enhanced_orderbook.collected_at
        )

    def normalize_okx_liquidation(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLiquidation]:
        """
        标准化OKX强平订单数据

        支持的产品类型：
        - MARGIN: 杠杆交易 (仅OKX支持按symbol订阅)
        - SWAP: 永续合约 (OKX和Binance都支持)

        Args:
            raw_data: OKX WebSocket强平订单事件的原始数据

        Returns:
            标准化的强平订单对象，失败时返回None
        """
        try:
            # OKX强平订单数据嵌套在data数组中
            if "data" not in raw_data or not raw_data["data"]:
                self.logger.warning("OKX强平订单数据缺少data字段")
                return None

            data = raw_data["data"][0]

            # 解析产品类型
            inst_type = data.get("instType", "").upper()
            if inst_type == "MARGIN":
                product_type = ProductType.MARGIN
            elif inst_type == "SWAP":
                product_type = ProductType.SWAP
            elif inst_type == "FUTURES":
                product_type = ProductType.FUTURES
            else:
                self.logger.warning(f"不支持的OKX产品类型: {inst_type}")
                return None

            # 标准化交易对格式
            symbol_name = self._normalize_symbol_format(data.get("instId", ""))

            # 解析强平方向
            side_str = data.get("side", "").lower()
            if side_str == "buy":
                side = LiquidationSide.BUY
            elif side_str == "sell":
                side = LiquidationSide.SELL
            else:
                self.logger.warning(f"无效的强平方向: {side_str}")
                return None

            # 解析强平状态
            state = data.get("state", "").lower()
            if state == "filled":
                status = LiquidationStatus.FILLED
            elif state == "partially_filled":
                status = LiquidationStatus.PARTIALLY_FILLED
            elif state == "cancelled":
                status = LiquidationStatus.CANCELLED
            else:
                status = LiquidationStatus.PENDING

            # 解析价格和数量
            price = Decimal(str(data.get("bkPx", "0")))  # 破产价格
            quantity = Decimal(str(data.get("sz", "0")))  # 强平数量
            filled_quantity = Decimal(str(data.get("fillSz", "0")))  # 已成交数量

            # 计算平均价格
            average_price = None
            if "fillPx" in data and data["fillPx"]:
                average_price = Decimal(str(data["fillPx"]))

            # 计算名义价值
            notional_value = price * quantity

            # 解析时间戳
            timestamp_ms = int(data.get("ts", "0"))
            liquidation_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            # 解析保证金率
            margin_ratio = None
            if "mgnRatio" in data and data["mgnRatio"]:
                margin_ratio = Decimal(str(data["mgnRatio"]))

            return NormalizedLiquidation(
                exchange_name="okx",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=data.get("instId", ""),
                liquidation_id=data.get("details", [{}])[0].get("tradeId", "") if data.get("details") else "",
                side=side,
                status=status,
                price=price,
                quantity=quantity,
                filled_quantity=filled_quantity,
                average_price=average_price,
                notional_value=notional_value,
                liquidation_time=liquidation_time,
                timestamp=liquidation_time,
                margin_ratio=margin_ratio,
                bankruptcy_price=price,  # OKX的bkPx就是破产价格
                raw_data=raw_data
            )

        except (KeyError, ValueError, TypeError, IndexError) as e:
            self.logger.error(f"OKX强平订单标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"OKX强平订单标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_liquidation(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLiquidation]:
        """
        标准化Binance强平订单数据

        注意：仅支持期货产品的强平订单
        - USDⓈ-M期货: 支持按symbol订阅
        - COIN-M期货: 支持按symbol订阅
        - 杠杆交易: 不支持按symbol订阅强平订单

        Args:
            raw_data: Binance WebSocket强平订单事件的原始数据

        Returns:
            标准化的强平订单对象，失败时返回None
        """
        try:
            # Binance强平订单数据结构
            if "o" not in raw_data:
                self.logger.warning("Binance强平订单数据缺少订单信息")
                return None

            order_data = raw_data["o"]

            # Binance强平订单只支持期货产品
            # 根据symbol格式判断产品类型
            symbol = order_data.get("s", "")
            if "USDT" in symbol and not symbol.endswith("_"):
                product_type = ProductType.SWAP  # USDⓈ-M永续合约
            elif "_" in symbol:
                product_type = ProductType.FUTURES  # COIN-M期货
            else:
                self.logger.warning(f"无法识别的Binance产品类型: {symbol}")
                return None

            # 标准化交易对格式
            symbol_name = self._normalize_symbol_format(symbol)

            # 解析强平方向
            side_str = order_data.get("S", "").lower()
            if side_str == "buy":
                side = LiquidationSide.BUY
            elif side_str == "sell":
                side = LiquidationSide.SELL
            else:
                self.logger.warning(f"无效的强平方向: {side_str}")
                return None

            # 解析强平状态
            status_str = order_data.get("X", "").upper()
            if status_str == "FILLED":
                status = LiquidationStatus.FILLED
            elif status_str == "PARTIALLY_FILLED":
                status = LiquidationStatus.PARTIALLY_FILLED
            elif status_str == "CANCELED":
                status = LiquidationStatus.CANCELLED
            else:
                status = LiquidationStatus.PENDING

            # 解析价格和数量
            price = Decimal(str(order_data.get("p", "0")))
            quantity = Decimal(str(order_data.get("q", "0")))
            filled_quantity = Decimal(str(order_data.get("z", "0")))

            # 计算平均价格
            average_price = None
            if "ap" in order_data and order_data["ap"]:
                average_price = Decimal(str(order_data["ap"]))

            # 计算名义价值
            notional_value = price * quantity

            # 解析时间戳
            timestamp_ms = int(order_data.get("T", raw_data.get("E", "0")))
            liquidation_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return NormalizedLiquidation(
                exchange_name="binance",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=symbol,
                liquidation_id=str(order_data.get("t", "")),
                side=side,
                status=status,
                price=price,
                quantity=quantity,
                filled_quantity=filled_quantity,
                average_price=average_price,
                notional_value=notional_value,
                liquidation_time=liquidation_time,
                timestamp=liquidation_time,
                bankruptcy_price=price,  # Binance的强平价格即为破产价格
                raw_data=raw_data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Binance强平订单标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Binance强平订单标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_okx_open_interest(self, data: Dict[str, Any]) -> Optional[NormalizedOpenInterest]:
        """
        标准化OKX持仓量数据

        OKX持仓量数据格式:
        {
            "instId": "BTC-USDT-SWAP",
            "oi": "1234567.89",
            "oiCcy": "123456789.12",
            "ts": "1640995200000"
        }
        """
        try:
            # 基础信息
            instrument_id = data.get("instId", "")
            if not instrument_id:
                self.logger.warning("OKX持仓量数据缺少instId字段")
                return None

            # 解析产品类型和交易对
            if "-SWAP" in instrument_id:
                product_type = "swap"
                symbol_name = instrument_id.replace("-SWAP", "")
            elif "-" in instrument_id and len(instrument_id.split("-")) >= 3:
                # 期货合约格式: BTC-USD-240329
                product_type = "futures"
                parts = instrument_id.split("-")
                symbol_name = f"{parts[0]}-{parts[1]}"
            else:
                product_type = "swap"  # 默认为永续合约
                symbol_name = self._normalize_symbol_format(instrument_id)

            # 持仓量信息
            open_interest_value = Decimal(str(data.get("oi", "0")))
            open_interest_usd = None
            if data.get("oiCcy"):
                open_interest_usd = Decimal(str(data.get("oiCcy", "0")))

            # 时间信息
            timestamp_ms = int(data.get("ts", "0"))
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return NormalizedOpenInterest(
                exchange_name="okx",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=instrument_id,
                open_interest_value=open_interest_value,
                open_interest_usd=open_interest_usd,
                open_interest_unit="contracts",
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"OKX持仓量数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"OKX持仓量数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_open_interest(self, data: Dict[str, Any]) -> Optional[NormalizedOpenInterest]:
        """
        标准化Binance持仓量数据

        Binance持仓量数据格式:
        {
            "symbol": "BTCUSDT",
            "openInterest": "1234567.89000000",
            "time": 1640995200000
        }
        """
        try:
            # 基础信息
            symbol = data.get("symbol", "")
            if not symbol:
                self.logger.warning("Binance持仓量数据缺少symbol字段")
                return None

            # 标准化交易对格式
            symbol_name = self._normalize_symbol_format(symbol)

            # Binance期货API主要是永续合约
            product_type = "swap"

            # 持仓量信息
            open_interest_value = Decimal(str(data.get("openInterest", "0")))

            # Binance返回的是合约张数，需要根据合约规格计算USD价值
            # 这里暂时不计算USD价值，留待后续处理
            open_interest_usd = None

            # 时间信息
            timestamp_ms = int(data.get("time", "0"))
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return NormalizedOpenInterest(
                exchange_name="binance",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=symbol,
                open_interest_value=open_interest_value,
                open_interest_usd=open_interest_usd,
                open_interest_unit="contracts",
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Binance持仓量数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Binance持仓量数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_okx_funding_rate(self, data: Dict[str, Any]) -> Optional[NormalizedFundingRate]:
        """
        标准化OKX资金费率数据

        OKX资金费率历史数据格式 (REST API /api/v5/public-data/funding-rate-history):
        {
            "code": "0",
            "msg": "",
            "data": [{
                "instType": "SWAP",
                "instId": "BTC-USDT-SWAP",
                "fundingRate": "0.00010000",
                "realizedRate": "0.00010000",
                "fundingTime": "1640995200000"
            }]
        }

        OKX资金费率WebSocket数据格式 (funding-rate频道):
        {
            "arg": {
                "channel": "funding-rate",
                "instId": "BTC-USDT-SWAP"
            },
            "data": [{
                "instType": "SWAP",
                "instId": "BTC-USDT-SWAP",
                "fundingRate": "0.00010000",
                "nextFundingTime": "1640995200000",
                "fundingTime": "1640995200000"
            }]
        }
        """
        try:
            # 处理REST API响应格式 (有code和data字段)
            if "code" in data and "data" in data and isinstance(data["data"], list) and data["data"]:
                funding_data = data["data"][0]
            # 处理WebSocket格式 (有data数组)
            elif "data" in data and isinstance(data["data"], list) and data["data"]:
                funding_data = data["data"][0]
            # 处理直接的数据对象格式
            elif "instId" in data:
                funding_data = data
            else:
                self.logger.warning("OKX资金费率数据格式无效")
                return None

            # 基础信息
            instrument_id = funding_data.get("instId", "")
            if not instrument_id:
                self.logger.warning("OKX资金费率数据缺少instId字段")
                return None

            # 解析产品类型和交易对
            if "-SWAP" in instrument_id:
                product_type = "swap"
                symbol_name = instrument_id.replace("-SWAP", "")
            elif "-PERPETUAL" in instrument_id:
                product_type = "perpetual"
                symbol_name = instrument_id.replace("-PERPETUAL", "")
            else:
                product_type = "swap"  # 默认为永续合约
                symbol_name = self._normalize_symbol_format(instrument_id)

            # 资金费率信息 - 优先使用realizedRate（历史实际费率），其次使用fundingRate
            current_funding_rate = Decimal(str(funding_data.get("realizedRate", funding_data.get("fundingRate", "0"))))

            # 下次资金费率时间 (仅WebSocket数据有此字段)
            next_funding_time = None
            if "nextFundingTime" in funding_data and funding_data["nextFundingTime"]:
                next_funding_time_ms = int(funding_data["nextFundingTime"])
                next_funding_time = datetime.fromtimestamp(next_funding_time_ms / 1000, tz=timezone.utc)
            else:
                # 历史数据没有nextFundingTime，根据fundingTime计算下一个8小时周期
                funding_time_ms = int(funding_data.get("fundingTime", "0"))
                if funding_time_ms:
                    funding_time = datetime.fromtimestamp(funding_time_ms / 1000, tz=timezone.utc)
                    # 计算下一个8小时周期 (0:00, 8:00, 16:00 UTC)
                    hours_since_midnight = funding_time.hour
                    next_funding_hour = ((hours_since_midnight // 8) + 1) * 8
                    if next_funding_hour >= 24:
                        next_funding_time = funding_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    else:
                        next_funding_time = funding_time.replace(hour=next_funding_hour, minute=0, second=0, microsecond=0)

            # 当前时间戳
            funding_time_ms = int(funding_data.get("fundingTime", funding_data.get("ts", "0")))
            if funding_time_ms:
                timestamp = datetime.fromtimestamp(funding_time_ms / 1000, tz=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            return NormalizedFundingRate(
                exchange_name="okx",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=instrument_id,
                current_funding_rate=current_funding_rate,
                next_funding_time=next_funding_time or timestamp,  # 如果没有nextFundingTime，使用当前时间戳
                funding_interval="8h",  # OKX默认8小时
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"OKX资金费率数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"OKX资金费率数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_funding_rate(self, data: Dict[str, Any]) -> Optional[NormalizedFundingRate]:
        """
        标准化Binance资金费率数据

        Binance资金费率历史数据格式 (REST API /fapi/v1/fundingRate):
        {
            "symbol": "BTCUSDT",
            "fundingRate": "-0.03750000",
            "fundingTime": 1570608000000,
            "markPrice": "34287.54619963"
        }

        Binance当前资金费率数据格式 (REST API /fapi/v1/premiumIndex):
        {
            "symbol": "BTCUSDT",
            "markPrice": "45000.00000000",
            "indexPrice": "44995.12345678",
            "estimatedSettlePrice": "44998.87654321",
            "lastFundingRate": "0.00010000",
            "nextFundingTime": 1640995200000,
            "interestRate": "0.00010000",
            "time": 1640995200000
        }

        注意：Binance不支持资金费率的WebSocket实时推送
        """
        try:
            # 基础信息
            symbol = data.get("symbol", "")
            if not symbol:
                self.logger.warning("Binance资金费率数据缺少symbol字段")
                return None

            # 标准化交易对格式
            symbol_name = self._normalize_symbol_format(symbol)

            # Binance期货API主要是永续合约
            product_type = "swap"

            # 资金费率信息 - 区分历史数据和当前数据
            current_funding_rate = None
            if "fundingRate" in data:
                # 历史数据格式
                current_funding_rate = Decimal(str(data["fundingRate"]))
            elif "lastFundingRate" in data:
                # 当前数据格式
                current_funding_rate = Decimal(str(data["lastFundingRate"]))
            else:
                self.logger.warning("Binance资金费率数据缺少fundingRate或lastFundingRate字段")
                return None

            # 预估资金费率 (仅当前数据有此字段)
            estimated_funding_rate = None
            if "interestRate" in data and data["interestRate"]:
                estimated_funding_rate = Decimal(str(data["interestRate"]))

            # 下次资金费率时间
            next_funding_time = None
            if "nextFundingTime" in data and data["nextFundingTime"]:
                # 当前数据格式
                next_funding_time_ms = int(data["nextFundingTime"])
                next_funding_time = datetime.fromtimestamp(next_funding_time_ms / 1000, tz=timezone.utc)
            elif "fundingTime" in data:
                # 历史数据格式 - 根据fundingTime计算下一个8小时周期
                funding_time_ms = int(data["fundingTime"])
                funding_time = datetime.fromtimestamp(funding_time_ms / 1000, tz=timezone.utc)
                # Binance资金费率时间: 0:00, 8:00, 16:00 UTC
                hours_since_midnight = funding_time.hour
                next_funding_hour = ((hours_since_midnight // 8) + 1) * 8
                if next_funding_hour >= 24:
                    next_funding_time = funding_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                else:
                    next_funding_time = funding_time.replace(hour=next_funding_hour, minute=0, second=0, microsecond=0)

            # 价格信息
            mark_price = None
            index_price = None
            premium_index = None

            if "markPrice" in data and data["markPrice"]:
                mark_price = Decimal(str(data["markPrice"]))

            if "indexPrice" in data and data["indexPrice"]:
                index_price = Decimal(str(data["indexPrice"]))

            # 计算溢价指数
            if mark_price and index_price:
                premium_index = mark_price - index_price

            # 时间戳 - 区分历史数据和当前数据
            timestamp = None
            if "fundingTime" in data:
                # 历史数据格式
                timestamp_ms = int(data["fundingTime"])
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            elif "time" in data:
                # 当前数据格式
                timestamp_ms = int(data["time"])
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            return NormalizedFundingRate(
                exchange_name="binance",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=symbol,
                current_funding_rate=current_funding_rate,
                estimated_funding_rate=estimated_funding_rate,
                next_funding_time=next_funding_time or timestamp,  # 如果没有nextFundingTime，使用当前时间戳
                funding_interval="8h",  # Binance默认8小时
                mark_price=mark_price,
                index_price=index_price,
                premium_index=premium_index,
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Binance资金费率数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Binance资金费率数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_top_trader_long_short_ratio(self, data: Dict[str, Any], period: Optional[str] = None) -> Optional[NormalizedTopTraderLongShortRatio]:
        """
        标准化Binance大户多空持仓比数据

        Binance大户持仓量多空比数据格式 (REST API /futures/data/topLongShortPositionRatio):
        {
            "symbol": "BTCUSDT",
            "longShortRatio": "1.4342",
            "longAccount": "0.5344",
            "shortAccount": "0.4238",
            "timestamp": "1583139600000"
        }
        """
        try:
            symbol = data.get("symbol", "")
            if not symbol:
                self.logger.warning("Binance大户多空持仓比数据缺少symbol字段")
                return None

            # 标准化交易对格式 (BTCUSDT -> BTC-USDT)
            symbol_name = self._normalize_symbol_format(symbol)

            # 提取币种 (BTC-USDT -> BTC)
            currency = symbol_name.split('-')[0] if '-' in symbol_name else symbol.replace('USDT', '').replace('BUSD', '').replace('USDC', '')

            # 核心数据字段
            long_short_ratio = Decimal(str(data.get("longShortRatio", "0")))
            long_position_ratio = Decimal(str(data.get("longAccount", "0")))
            short_position_ratio = Decimal(str(data.get("shortAccount", "0")))

            # 数据质量检查
            ratio_sum = long_position_ratio + short_position_ratio
            ratio_sum_check = abs(ratio_sum - Decimal("1.0")) < Decimal("0.01")  # 允许1%的误差

            # 计算数据质量评分
            data_quality_score = Decimal("1.0")
            if not ratio_sum_check:
                data_quality_score -= Decimal("0.3")  # 比例和不正确扣分
            if long_short_ratio <= 0:
                data_quality_score -= Decimal("0.5")  # 比值异常扣分

            # 时间戳处理
            timestamp_ms = int(data.get("timestamp", "0"))
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return NormalizedTopTraderLongShortRatio(
                exchange_name="binance",
                symbol_name=symbol_name,
                currency=currency,
                long_short_ratio=long_short_ratio,
                long_position_ratio=long_position_ratio,
                short_position_ratio=short_position_ratio,
                data_type="position",  # Binance API提供的是持仓量比例
                period=period,  # 从请求参数传入
                instrument_type="futures",  # Binance期货API
                data_quality_score=data_quality_score,
                ratio_sum_check=ratio_sum_check,
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Binance大户多空持仓比数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Binance大户多空持仓比数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_okx_top_trader_long_short_ratio(self, data: Dict[str, Any], period: Optional[str] = None) -> Optional[NormalizedTopTraderLongShortRatio]:
        """
        标准化OKX精英交易员多空持仓比数据

        OKX精英交易员合约多空持仓仓位比数据格式 (REST API /api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader):
        {
            "ccy": "BTC",
            "longShortRatio": "1.2345",
            "longRatio": "0.5523",
            "shortRatio": "0.4477",
            "ts": "1583139600000"
        }
        """
        try:
            # 处理OKX API响应格式 (有code和data字段)
            if "code" in data and "data" in data and isinstance(data["data"], list) and data["data"]:
                ratio_data = data["data"][0]
            # 处理直接的数据对象格式
            elif "ccy" in data:
                ratio_data = data
            else:
                self.logger.warning("OKX精英交易员多空持仓比数据格式无效")
                return None

            currency = ratio_data.get("ccy", "")
            if not currency:
                self.logger.warning("OKX精英交易员多空持仓比数据缺少ccy字段")
                return None

            # 构造标准化交易对格式 (BTC -> BTC-USDT)
            # 注意：OKX只提供币种，需要推断主要交易对
            symbol_name = f"{currency}-USDT"  # 默认使用USDT交易对

            # 核心数据字段
            long_short_ratio = Decimal(str(ratio_data.get("longShortRatio", "0")))
            long_position_ratio = Decimal(str(ratio_data.get("longRatio", "0")))
            short_position_ratio = Decimal(str(ratio_data.get("shortRatio", "0")))

            # 数据质量检查
            ratio_sum = long_position_ratio + short_position_ratio
            ratio_sum_check = abs(ratio_sum - Decimal("1.0")) < Decimal("0.01")  # 允许1%的误差

            # 计算数据质量评分
            data_quality_score = Decimal("1.0")
            if not ratio_sum_check:
                data_quality_score -= Decimal("0.3")  # 比例和不正确扣分
            if long_short_ratio <= 0:
                data_quality_score -= Decimal("0.5")  # 比值异常扣分

            # 时间戳处理
            timestamp_ms = int(ratio_data.get("ts", "0"))
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return NormalizedTopTraderLongShortRatio(
                exchange_name="okx",
                symbol_name=symbol_name,
                currency=currency,
                long_short_ratio=long_short_ratio,
                long_position_ratio=long_position_ratio,
                short_position_ratio=short_position_ratio,
                data_type="position",  # OKX API提供的是持仓量比例
                period=period,  # 从请求参数传入
                instrument_type="swap",  # OKX永续合约
                data_quality_score=data_quality_score,
                ratio_sum_check=ratio_sum_check,
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"OKX精英交易员多空持仓比数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"OKX精英交易员多空持仓比数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_market_long_short_ratio(self, data: Dict[str, Any], period: Optional[str] = None) -> Optional[NormalizedMarketLongShortRatio]:
        """
        标准化Binance整体市场多空人数比数据

        Binance全球用户多空持仓人数比数据格式 (REST API /futures/data/globalLongShortAccountRatio):
        {
            "symbol": "BTCUSDT",
            "longShortRatio": "0.1960",
            "longAccount": "0.6622",
            "shortAccount": "0.3378",
            "timestamp": "1583139600000"
        }
        """
        try:
            symbol = data.get("symbol", "")
            if not symbol:
                self.logger.warning("Binance市场多空人数比数据缺少symbol字段")
                return None

            # 标准化交易对格式 (BTCUSDT -> BTC-USDT)
            symbol_name = self._normalize_symbol_format(symbol)

            # 提取币种 (BTC-USDT -> BTC)
            currency = symbol_name.split('-')[0] if '-' in symbol_name else symbol.replace('USDT', '').replace('BUSD', '').replace('USDC', '')

            # 核心数据字段
            long_short_ratio = Decimal(str(data.get("longShortRatio", "0")))
            long_account_ratio = Decimal(str(data.get("longAccount", "0")))
            short_account_ratio = Decimal(str(data.get("shortAccount", "0")))

            # 数据质量检查
            ratio_sum = long_account_ratio + short_account_ratio
            ratio_sum_check = abs(ratio_sum - Decimal("1.0")) < Decimal("0.01")  # 允许1%的误差

            # 计算数据质量评分
            data_quality_score = Decimal("1.0")
            if not ratio_sum_check:
                data_quality_score -= Decimal("0.3")  # 比例和不正确扣分
            if long_short_ratio <= 0:
                data_quality_score -= Decimal("0.5")  # 比值异常扣分

            # 时间戳处理
            timestamp_ms = int(data.get("timestamp", "0"))
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return NormalizedMarketLongShortRatio(
                exchange_name="binance",
                symbol_name=symbol_name,
                currency=currency,
                long_short_ratio=long_short_ratio,
                long_account_ratio=long_account_ratio,
                short_account_ratio=short_account_ratio,
                data_type="account",  # Binance API提供的是人数比例
                period=period,  # 从请求参数传入
                instrument_type="futures",  # Binance期货API
                data_quality_score=data_quality_score,
                ratio_sum_check=ratio_sum_check,
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Binance市场多空人数比数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Binance市场多空人数比数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_okx_market_long_short_ratio(self, data: Dict[str, Any], inst_id: str, period: Optional[str] = None) -> Optional[NormalizedMarketLongShortRatio]:
        """
        标准化OKX合约多空持仓人数比数据

        OKX合约多空持仓人数比数据格式 (REST API /api/v5/rubik/stat/contracts/long-short-account-ratio-contract):
        {
            "code": "0",
            "msg": "",
            "data": [
                [
                    "1701417600000",    // timestamp
                    "1.1739"            // long/short account num ratio
                ]
            ]
        }
        """
        try:
            # 处理OKX API响应格式
            if "code" in data and "data" in data and isinstance(data["data"], list) and data["data"]:
                # OKX返回的是数组格式 [timestamp, ratio]
                ratio_data = data["data"][0]  # 取第一条数据
                if not isinstance(ratio_data, list) or len(ratio_data) < 2:
                    self.logger.warning("OKX市场多空人数比数据格式无效")
                    return None

                timestamp_str = ratio_data[0]
                long_short_ratio_str = ratio_data[1]
            else:
                self.logger.warning("OKX市场多空人数比数据格式无效")
                return None

            if not inst_id:
                self.logger.warning("OKX市场多空人数比数据缺少instId参数")
                return None

            # 从instId提取币种信息 (BTC-USDT -> BTC)
            symbol_name = inst_id  # 保持原格式
            currency = inst_id.split('-')[0] if '-' in inst_id else inst_id

            # 核心数据字段
            long_short_ratio = Decimal(str(long_short_ratio_str))

            # 注意：OKX只提供多空比值，没有提供具体的多仓和空仓人数比例
            # 我们可以根据多空比值推算出大概的比例
            # 如果 long_short_ratio = long_accounts / short_accounts
            # 且 long_ratio + short_ratio = 1
            # 则 long_ratio = long_short_ratio / (1 + long_short_ratio)
            # short_ratio = 1 / (1 + long_short_ratio)
            if long_short_ratio > 0:
                long_account_ratio = long_short_ratio / (Decimal("1") + long_short_ratio)
                short_account_ratio = Decimal("1") / (Decimal("1") + long_short_ratio)
            else:
                long_account_ratio = None
                short_account_ratio = None

            # 数据质量检查
            ratio_sum_check = None
            if long_account_ratio is not None and short_account_ratio is not None:
                ratio_sum = long_account_ratio + short_account_ratio
                ratio_sum_check = abs(ratio_sum - Decimal("1.0")) < Decimal("0.01")

            # 计算数据质量评分
            data_quality_score = Decimal("1.0")
            if ratio_sum_check is False:
                data_quality_score -= Decimal("0.3")  # 比例和不正确扣分
            if long_short_ratio <= 0:
                data_quality_score -= Decimal("0.5")  # 比值异常扣分
            if long_account_ratio is None:
                data_quality_score -= Decimal("0.2")  # 缺少详细比例扣分

            # 时间戳处理
            timestamp_ms = int(timestamp_str)
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            return NormalizedMarketLongShortRatio(
                exchange_name="okx",
                symbol_name=symbol_name,
                currency=currency,
                long_short_ratio=long_short_ratio,
                long_account_ratio=long_account_ratio,
                short_account_ratio=short_account_ratio,
                data_type="account",  # OKX API提供的是人数比例
                period=period,  # 从请求参数传入
                instrument_type="swap",  # OKX合约
                data_quality_score=data_quality_score,
                ratio_sum_check=ratio_sum_check,
                timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"OKX市场多空人数比数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"OKX市场多空人数比数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_spot_trade(self, data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        """
        标准化Binance现货逐笔交易数据

        Binance现货逐笔交易数据格式 (WebSocket):
        {
            "e": "trade",        // 事件类型
            "E": 1672515782136,  // 事件时间
            "s": "BNBBTC",       // 交易对
            "t": 12345,          // 交易ID
            "p": "0.001",        // 成交价格
            "q": "100",          // 成交数量
            "T": 1672515782136,  // 成交时间
            "m": true            // 买方是否是做市方
        }
        """
        try:
            symbol = data.get("s", "")
            if not symbol:
                self.logger.warning("Binance现货交易数据缺少symbol字段")
                return None

            # 标准化交易对格式 (BNBBTC -> BNB-BTC)
            symbol_name = self._normalize_symbol_format(symbol)

            # 提取币种 (BNB-BTC -> BNB)
            currency = symbol_name.split('-')[0] if '-' in symbol_name else symbol[:3]  # 现货通常前3位是币种

            # 核心交易数据
            trade_id = str(data.get("t", ""))
            price = Decimal(str(data.get("p", "0")))
            quantity = Decimal(str(data.get("q", "0")))
            quote_quantity = price * quantity  # 计算成交金额

            # 交易方向转换：Binance的m字段表示买方是否是做市方
            # m=true表示主动卖出，m=false表示主动买入
            is_maker = data.get("m", False)
            side = "sell" if is_maker else "buy"

            # 时间戳处理
            trade_time_ms = int(data.get("T", "0"))
            event_time_ms = int(data.get("E", "0"))

            trade_time = datetime.fromtimestamp(trade_time_ms / 1000, tz=timezone.utc)
            event_time = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc) if event_time_ms else None

            return NormalizedTrade(
                exchange_name="binance",
                symbol_name=symbol_name,
                currency=currency,
                trade_id=trade_id,
                price=price,
                quantity=quantity,
                quote_quantity=quote_quantity,
                side=side,
                timestamp=trade_time,
                event_time=event_time,
                trade_type="spot",
                is_maker=is_maker,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Binance现货交易数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Binance现货交易数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_futures_trade(self, data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        """
        标准化Binance期货归集交易数据

        Binance期货归集交易数据格式 (WebSocket):
        {
            "e": "aggTrade",  // 事件类型
            "E": 123456789,   // 事件时间
            "s": "BNBUSDT",   // 交易对
            "a": 5933014,     // 归集成交ID
            "p": "0.001",     // 成交价格
            "q": "100",       // 成交量
            "f": 100,         // 被归集的首个交易ID
            "l": 105,         // 被归集的末次交易ID
            "T": 123456785,   // 成交时间
            "m": true         // 买方是否是做市方
        }
        """
        try:
            symbol = data.get("s", "")
            if not symbol:
                self.logger.warning("Binance期货交易数据缺少symbol字段")
                return None

            # 标准化交易对格式 (BNBUSDT -> BNB-USDT)
            symbol_name = self._normalize_symbol_format(symbol)

            # 提取币种 (BNB-USDT -> BNB)
            currency = symbol_name.split('-')[0] if '-' in symbol_name else symbol.replace('USDT', '').replace('BUSD', '').replace('USDC', '')

            # 核心交易数据
            trade_id = str(data.get("a", ""))  # 使用归集交易ID作为主要交易ID
            agg_trade_id = str(data.get("a", ""))
            first_trade_id = str(data.get("f", ""))
            last_trade_id = str(data.get("l", ""))

            price = Decimal(str(data.get("p", "0")))
            quantity = Decimal(str(data.get("q", "0")))
            quote_quantity = price * quantity  # 计算成交金额

            # 交易方向转换：Binance的m字段表示买方是否是做市方
            # m=true表示主动卖出，m=false表示主动买入
            is_maker = data.get("m", False)
            side = "sell" if is_maker else "buy"

            # 时间戳处理
            trade_time_ms = int(data.get("T", "0"))
            event_time_ms = int(data.get("E", "0"))

            trade_time = datetime.fromtimestamp(trade_time_ms / 1000, tz=timezone.utc)
            event_time = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc) if event_time_ms else None

            return NormalizedTrade(
                exchange_name="binance",
                symbol_name=symbol_name,
                currency=currency,
                trade_id=trade_id,
                price=price,
                quantity=quantity,
                quote_quantity=quote_quantity,
                side=side,
                timestamp=trade_time,
                event_time=event_time,
                trade_type="futures",
                is_maker=is_maker,
                agg_trade_id=agg_trade_id,
                first_trade_id=first_trade_id,
                last_trade_id=last_trade_id,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Binance期货交易数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Binance期货交易数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_okx_trade(self, data: Dict[str, Any], trade_type: str = "spot") -> Optional[NormalizedTrade]:
        """
        标准化OKX交易数据

        OKX交易数据格式 (WebSocket):
        {
            "arg": {
                "channel": "trades",
                "instId": "BTC-USDT"
            },
            "data": [{
                "instId": "BTC-USDT",
                "tradeId": "130639474",
                "px": "42219.9",
                "sz": "0.12060306",
                "side": "buy",
                "ts": "1629386781174"
            }]
        }
        """
        try:
            # 处理OKX WebSocket响应格式
            if "data" in data and isinstance(data["data"], list) and data["data"]:
                trade_data = data["data"][0]  # 取第一条交易数据

                # 从arg中获取instId作为备用
                inst_id_from_arg = None
                if "arg" in data and "instId" in data["arg"]:
                    inst_id_from_arg = data["arg"]["instId"]
            elif "instId" in data:
                # 直接的交易数据格式
                trade_data = data
                inst_id_from_arg = None
            else:
                self.logger.warning("OKX交易数据格式无效")
                return None

            # 获取交易对信息
            symbol = trade_data.get("instId") or inst_id_from_arg
            if not symbol:
                self.logger.warning("OKX交易数据缺少instId字段")
                return None

            # OKX的交易对格式通常已经是标准格式 (BTC-USDT)
            symbol_name = symbol

            # 提取币种 (BTC-USDT -> BTC)
            currency = symbol_name.split('-')[0] if '-' in symbol_name else symbol

            # 核心交易数据
            trade_id = str(trade_data.get("tradeId", ""))
            price = Decimal(str(trade_data.get("px", "0")))
            quantity = Decimal(str(trade_data.get("sz", "0")))
            quote_quantity = price * quantity  # 计算成交金额

            # OKX直接提供交易方向
            side = trade_data.get("side", "buy")  # buy 或 sell

            # 时间戳处理
            timestamp_ms = int(trade_data.get("ts", "0"))
            trade_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            # 根据instId判断交易类型
            if trade_type == "auto":
                if "-SWAP" in symbol:
                    trade_type = "swap"
                elif any(month in symbol for month in ["0329", "0628", "0927", "1228"]):
                    trade_type = "futures"
                else:
                    trade_type = "spot"

            return NormalizedTrade(
                exchange_name="okx",
                symbol_name=symbol_name,
                currency=currency,
                trade_id=trade_id,
                price=price,
                quantity=quantity,
                quote_quantity=quote_quantity,
                side=side,
                timestamp=trade_time,
                trade_type=trade_type,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"OKX交易数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"OKX交易数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_deribit_volatility_index(self, data: Dict[str, Any]) -> Optional[NormalizedVolatilityIndex]:
        """
        标准化Deribit波动率指数数据

        Args:
            data: Deribit get_volatility_index_data API返回的数据

        Returns:
            NormalizedVolatilityIndex对象或None

        Expected data format:
        {
            "result": {
                "data": [
                    {
                        "timestamp": 1609459200000,
                        "volatility": 0.85,
                        "index_name": "BTCDVOL_USDC-DERIBIT-INDEX"
                    }
                ]
            }
        }
        """
        try:
            # 处理API响应格式
            if "result" in data:
                result_data = data["result"]
                if "data" in result_data and isinstance(result_data["data"], list) and result_data["data"]:
                    # 取第一个数据点
                    volatility_data = result_data["data"][0]
                else:
                    # 直接是result数据
                    volatility_data = result_data
            else:
                # 直接是数据格式
                volatility_data = data

            # 提取必需字段
            timestamp_ms = volatility_data.get("timestamp")
            volatility_value = volatility_data.get("volatility")
            index_name = volatility_data.get("index_name", "")

            # 验证必需字段
            if timestamp_ms is None or volatility_value is None:
                self.logger.warning(f"Deribit波动率指数数据缺少必需字段: {volatility_data}")
                return None

            # 转换时间戳
            if isinstance(timestamp_ms, (int, float)):
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            else:
                self.logger.warning(f"无效的时间戳格式: {timestamp_ms}")
                return None

            # 从index_name提取货币信息
            currency = "BTC"  # 默认值
            if index_name:
                # 解析类似 "BTCDVOL_USDC-DERIBIT-INDEX" 的格式
                if index_name.startswith("BTC"):
                    currency = "BTC"
                elif index_name.startswith("ETH"):
                    currency = "ETH"
                elif "DVOL" in index_name:
                    # 提取DVOL前的货币名称
                    dvol_pos = index_name.find("DVOL")
                    if dvol_pos > 0:
                        currency = index_name[:dvol_pos]

            # 转换波动率值
            volatility_decimal = Decimal(str(volatility_value))

            # 计算数据质量评分
            quality_score = self._calculate_volatility_quality_score(
                volatility_decimal, timestamp, index_name
            )

            # 提取分辨率信息（如果有）
            resolution = volatility_data.get("resolution")

            return NormalizedVolatilityIndex(
                exchange_name="deribit",
                currency=currency,
                index_name=index_name,
                volatility_value=volatility_decimal,
                timestamp=timestamp,
                resolution=resolution,
                data_quality_score=quality_score,
                source_timestamp=timestamp,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Deribit波动率指数数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Deribit波动率指数数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def _calculate_volatility_quality_score(
        self,
        volatility_value: Decimal,
        timestamp: datetime,
        index_name: str
    ) -> Decimal:
        """计算波动率数据质量评分"""
        score = Decimal('1.0')

        # 时间延迟检查
        current_time = datetime.now(timezone.utc)
        if timestamp:
            delay_seconds = (current_time - timestamp).total_seconds()
            if delay_seconds > 300:  # 超过5分钟
                score -= Decimal('0.2')
            elif delay_seconds > 60:  # 超过1分钟
                score -= Decimal('0.1')

        # 波动率值合理性检查
        if volatility_value < 0:
            score -= Decimal('0.5')  # 负值严重错误
        elif volatility_value > Decimal('5.0'):  # 超过500%
            score -= Decimal('0.3')
        elif volatility_value > Decimal('3.0'):  # 超过300%
            score -= Decimal('0.1')

        # 指数名称完整性检查
        if not index_name or "DVOL" not in index_name:
            score -= Decimal('0.1')

        return max(score, Decimal('0.0'))