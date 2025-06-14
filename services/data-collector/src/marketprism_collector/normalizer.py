"""
数据标准化模块

将不同交易所的数据转换为统一格式
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from decimal import Decimal
import structlog

from .data_types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker, 
    OrderBookEntry, PriceLevel, EnhancedOrderBook, OrderBookDelta,
    OrderBookUpdateType, Exchange, EnhancedOrderBookUpdate
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
    
    def normalize_okx_ticker(self, raw_data: dict, symbol: str) -> Optional[NormalizedTicker]:
        """标准化OKX行情数据"""
        try:
            if "data" not in raw_data or not raw_data["data"]:
                return None
            
            ticker_data = raw_data["data"][0]
            
            return NormalizedTicker(
                exchange_name="okx",
                symbol_name=self._normalize_symbol_format(symbol),
                last_price=Decimal(ticker_data["last"]),
                best_bid_price=Decimal(ticker_data.get("bidPx", "0")) if ticker_data.get("bidPx") else None,
                best_ask_price=Decimal(ticker_data.get("askPx", "0")) if ticker_data.get("askPx") else None,
                open_price=Decimal(ticker_data.get("open24h", "0")) if ticker_data.get("open24h") else None,
                high_price=Decimal(ticker_data.get("high24h", "0")) if ticker_data.get("high24h") else None,
                low_price=Decimal(ticker_data.get("low24h", "0")) if ticker_data.get("low24h") else None,
                volume=Decimal(ticker_data.get("vol24h", "0")) if ticker_data.get("vol24h") else None,
                price_change=Decimal("0"),  # 需要计算
                price_change_percent=Decimal("0"),  # 需要计算
                weighted_avg_price=Decimal("0"),  # OKX没有提供
                best_bid_quantity=Decimal("0"),  # OKX没有提供
                best_ask_quantity=Decimal("0"),  # OKX没有提供
                open_time=datetime.now(timezone.utc),  # OKX没有提供
                close_time=datetime.now(timezone.utc),  # OKX没有提供
                trade_count=0,  # OKX没有提供
                timestamp=datetime.fromtimestamp(int(ticker_data["ts"]) / 1000)
            )
        except Exception as e:
            self.logger.error("标准化OKX行情数据失败", exc_info=True, raw_data=raw_data)
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
    
    def normalize_binance_ticker(self, raw_data: dict) -> Optional[NormalizedTicker]:
        """标准化Binance行情数据"""
        try:
            return NormalizedTicker(
                exchange_name="binance",
                symbol_name=self._normalize_symbol_format(raw_data["s"]),
                last_price=Decimal(raw_data["c"]),
                best_bid_price=Decimal(raw_data.get("b", "0")) if raw_data.get("b") else None,
                best_ask_price=Decimal(raw_data.get("a", "0")) if raw_data.get("a") else None,
                open_price=Decimal(raw_data.get("o", "0")) if raw_data.get("o") else None,
                high_price=Decimal(raw_data.get("h", "0")) if raw_data.get("h") else None,
                low_price=Decimal(raw_data.get("l", "0")) if raw_data.get("l") else None,
                volume=Decimal(raw_data.get("v", "0")) if raw_data.get("v") else None,
                price_change=Decimal(raw_data.get("p", "0")) if raw_data.get("p") else None,
                price_change_percent=Decimal(raw_data.get("P", "0")) if raw_data.get("P") else None,
                weighted_avg_price=Decimal(raw_data.get("w", "0")) if raw_data.get("w") else None,
                best_bid_quantity=Decimal(raw_data.get("B", "0")) if raw_data.get("B") else None,
                best_ask_quantity=Decimal(raw_data.get("A", "0")) if raw_data.get("A") else None,
                open_time=datetime.fromtimestamp(raw_data.get("O", 0) / 1000) if raw_data.get("O") else datetime.now(timezone.utc),
                close_time=datetime.fromtimestamp(raw_data.get("C", 0) / 1000) if raw_data.get("C") else datetime.now(timezone.utc),
                trade_count=raw_data.get("n", 0),
                timestamp=datetime.fromtimestamp(raw_data["E"] / 1000)
            )
        except Exception as e:
            self.logger.error("标准化Binance行情数据失败", exc_info=True, raw_data=raw_data)
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