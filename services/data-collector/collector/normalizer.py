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
    NormalizedMarketLongShortRatio, NormalizedVolatilityIndex, NormalizedLSRTopPosition, NormalizedLSRAllAccount
)


class DataNormalizer:
    """
    增强数据标准化器 - 系统唯一的数据标准化入口

    核心原则：一次标准化，全链路使用
    - 所有Symbol格式统一为 BTC-USDT 格式
    - 所有市场类型从配置获取，不进行推断
    - 所有交易所名称标准化
    - 所有数据结构统一
    """

    def __init__(self):
        self.logger = structlog.get_logger(__name__)

        # 标准化配置
        self.standard_quote_currencies = [
            "USDT", "USDC", "BUSD", "BTC", "ETH", "BNB",
            "USD", "EUR", "GBP", "JPY", "DAI", "TUSD"
        ]

    # 统一时间字段规范化：ClickHouse 友好字符串（UTC，毫秒精度：YYYY-MM-DD HH:MM:SS.mmm）
    def _to_clickhouse_millis_str(self, val: Any) -> str:
        try:
            if isinstance(val, datetime):
                return val.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:23]
            if isinstance(val, str):
                t = val
                # 去除尾部 Z、去除时区偏移、替换 T 为空格
                if t.endswith('Z'):
                    t = t[:-1]
                if 'T' in t:
                    t = t.replace('T', ' ')
                if '+' in t:
                    t = t.split('+')[0]
                # 规整到毫秒精度
                if t.count(':') >= 2:
                    if '.' in t:
                        head, frac = t.split('.', 1)
                        frac = (frac + '000')[:3]
                        t = f"{head}.{frac}"
                    else:
                        t = t + '.000'
                return t
        except Exception:
            pass
        # 兜底：当前UTC时间毫秒
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:23]

    def normalize_time_fields(self, data: Dict[str, Any], ensure_collected_at: bool = True) -> Dict[str, Any]:
        """规范化常见时间字段到 ClickHouse 兼容的毫秒字符串。
        处理字段：timestamp, trade_time, collected_at, next_funding_time
        """
        if not isinstance(data, dict):
            return data
        for key in ('timestamp', 'trade_time', 'collected_at', 'next_funding_time'):
            if key in data and data.get(key):
                data[key] = self._to_clickhouse_millis_str(data[key])
            elif key == 'collected_at' and ensure_collected_at:
                data[key] = self._to_clickhouse_millis_str(datetime.now(timezone.utc))
        return data

    def normalize(self, data: Dict[str, Any], data_type: str = None, exchange: str = None) -> Dict[str, Any]:
        """通用数据标准化方法 - 修复版：生成ClickHouse兼容时间戳"""
        try:
            # 基础标准化 - 确保所有数据都有基本字段
            # 使用ClickHouse兼容的时间戳格式（毫秒精度，UTC）
            clickhouse_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            normalized = {
                **data,
                'timestamp': clickhouse_timestamp,
                'data_source': 'marketprism'  # 替换normalized等字段
            }

            # 如果提供了交易所信息，标准化交易所名称
            if exchange:
                normalized['exchange'] = self.normalize_exchange_name(exchange)

            # 移除不需要的字段
            for field in ['data_type', 'normalized', 'normalizer_version', 'publisher']:
                normalized.pop(field, None)

            return normalized

        except Exception as e:
            self.logger.error(f"数据标准化失败: {e}", exc_info=True)
            # 返回原始数据加上错误标记（毫秒精度，UTC）
            clickhouse_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            return {
                **data,
                'timestamp': clickhouse_timestamp,
                'data_source': 'marketprism',
                'normalization_error': str(e)
            }



    def normalize_symbol_format(self, symbol: str, exchange: str = None) -> str:
        """
        系统唯一的Symbol格式标准化方法

        统一所有交易对格式为 BTC-USDT 格式：
        - Binance现货: BTCUSDT -> BTC-USDT
        - Binance永续: BTCUSDT -> BTC-USDT
        - OKX现货: BTC-USDT -> BTC-USDT
        - OKX永续: 保持官方格式 BTC-USDT-SWAP；如遇 -PERPETUAL 则规范化为 -SWAP

        Args:
            symbol: 原始交易对符号
            exchange: 交易所名称（用于特殊处理）

        Returns:
            统一格式的交易对符号 (BTC-USDT)
        """
        if not symbol:
            return symbol

        symbol = symbol.upper()
        exchange = exchange.lower() if exchange else ""

        # 1. 处理交易所特殊后缀
        # 🎯 支持新的市场分类架构：okx_spot, okx_derivatives
        if exchange in ['okx', 'okx_spot', 'okx_derivatives']:
            # OKX永续合约后缀处理（严格按官方格式）
            # -SWAP: 保留；-PERPETUAL: 规范化为 -SWAP
            if symbol.endswith('-PERPETUAL'):
                symbol = symbol[:-len('-PERPETUAL')] + '-SWAP'

        # 1.1 Deribit 特殊：允许单币种或 DVOL 标识符，不提示警告
        if exchange.startswith('deribit'):
            # 形如 BTC、ETH 或 BTC-DVOL 这类标识，直接返回
            if '-' not in symbol or symbol.endswith('-DVOL'):
                return symbol

        # 2. 如果已经是标准格式 (XXX-YYY)，直接返回
        if "-" in symbol and not symbol.endswith('-') and len(symbol.split('-')) == 2:
            return symbol

        # 3. 处理无分隔符格式 (BTCUSDT -> BTC-USDT)
        for quote in self.standard_quote_currencies:
            if symbol.endswith(quote) and len(symbol) > len(quote):
                base = symbol[:-len(quote)]
                if base:  # 确保基础货币不为空
                    return f"{base}-{quote}"

        # 4. 如果无法识别，记录警告并返回原始格式
        exchange_info = exchange if exchange else "unknown"
        self.logger.warning(f"无法标准化Symbol格式: {symbol}, exchange: {exchange_info}")
        return symbol

    def _normalize_symbol_format(self, symbol: str) -> str:
        """向后兼容方法，调用新的标准化方法"""
        return self.normalize_symbol_format(symbol)

    def normalize_exchange_name(self, exchange: str) -> str:
        """
        标准化交易所名称

        Args:
            exchange: 原始交易所名称

        Returns:
            标准化的交易所名称
        """
        if not exchange:
            return exchange

        exchange = exchange.lower()

        # 标准化映射
        exchange_mapping = {
            'binance_spot': 'binance',
            'binance_perpetual': 'binance',
            'binance_futures': 'binance',
            'okx_spot': 'okx',
            'okx_perpetual': 'okx',
            'okx_swap': 'okx',
            'okx_futures': 'okx'
        }

        return exchange_mapping.get(exchange, exchange)

    def normalize_market_type(self, market_type: str) -> str:
        """
        标准化市场类型

        Args:
            market_type: 原始市场类型

        Returns:
            标准化的市场类型 (spot/perpetual)
        """
        if not market_type:
            return 'spot'  # 默认为现货

        market_type = market_type.lower()

        # 标准化映射
        market_type_mapping = {
            'swap': 'perpetual',
            'futures': 'perpetual',
            'perp': 'perpetual',
            'perpetual': 'perpetual',
            'spot': 'spot'
        }

        return market_type_mapping.get(market_type, 'spot')

    def normalize_symbol(self, symbol: str, exchange: Exchange = None) -> str:
        """
        公开的交易对标准化方法 - 🔧 修复：添加缺失的API方法

        Args:
            symbol: 原始交易对符号
            exchange: 交易所（可选，用于特定交易所的处理）

        Returns:
            标准化后的交易对符号
        """
        # 正确传递 exchange 以支持交易所特定规则（如 OKX 的 -SWAP 永续后缀）
        exch = None
        if exchange is not None:
            try:
                # 兼容 Enum 或 str
                exch = exchange.value if hasattr(exchange, 'value') else str(exchange)
            except Exception:
                exch = str(exchange)
        return self.normalize_symbol_format(symbol, exch)

    def normalize_enhanced_orderbook_from_snapshot(
        self,
        exchange: str,
        symbol: str,
        bids: List[PriceLevel],
        asks: List[PriceLevel],
        market_type: str = 'spot',
        last_update_id: Optional[int] = None,
        checksum: Optional[int] = None
    ) -> EnhancedOrderBook:
        """
        从快照数据创建增强订单簿

        Args:
            exchange: 交易所名称
            symbol: 交易对符号
            bids: 买单列表
            asks: 卖单列表
            market_type: 市场类型 (从配置传入，不进行推断)
            last_update_id: 最后更新ID
            checksum: 校验和

        Returns:
            标准化的增强订单簿对象
        """
        # 🔧 使用增强的标准化方法
        normalized_exchange = self.normalize_exchange_name(exchange)
        normalized_symbol = self.normalize_symbol_format(symbol, exchange)
        normalized_market_type = self.normalize_market_type(market_type)

        return EnhancedOrderBook(
            exchange_name=normalized_exchange,
            symbol_name=normalized_symbol,
            market_type=normalized_market_type,  # 添加市场类型字段
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
                "timestamp": datetime.fromtimestamp(int(book_data.get("ts", 0)) / 1000, tz=timezone.utc)
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
            # 🎯 支持新的市场分类架构
            exchange_lower = exchange.lower()
            if exchange_lower in ['binance', 'binance_spot', 'binance_derivatives']:
                normalized = self.normalize_binance_depth_update(raw_data)
            elif exchange_lower in ['okx', 'okx_spot', 'okx_derivatives']:
                normalized = self.normalize_okx_depth_update(raw_data)
            else:
                self.logger.warning(f"Unsupported exchange for depth update: {exchange}")
                return None

            if not normalized:
                return None

            # 创建标准化的增量深度更新
            return EnhancedOrderBookUpdate(
                exchange_name=exchange.lower(),
                symbol_name=self.normalize_symbol_format(symbol, exchange),  # 🔧 修复：传递exchange参数
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

    # 🗑️ 已删除：旧版本的normalize_okx_trade方法，使用新版本（第1557行）

    def normalize_okx_orderbook(self, raw_data: dict, symbol: str, market_type: str = "spot") -> Optional[NormalizedOrderBook]:
        """标准化OKX订单簿数据

        Args:
            raw_data: 原始订单簿数据
            symbol: 交易对符号
            market_type: 市场类型 (spot, perpetual, futures)
        """
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

            # 根据market_type确定交易所名称
            exchange_name = "okx_spot" if market_type == "spot" else "okx_derivatives"

            return NormalizedOrderBook(
                exchange_name=exchange_name,
                symbol_name=self.normalize_symbol_format(symbol, exchange_name),
                bids=bids,
                asks=asks,
                timestamp=datetime.fromtimestamp(int(book_data["ts"]) / 1000, tz=timezone.utc),
                last_update_id=int(book_data.get("seqId", 0)) if book_data.get("seqId") else None
            )
        except Exception as e:
            self.logger.error("标准化OKX订单簿数据失败", exc_info=True, raw_data=raw_data)
            return None



    # 🗑️ 已删除：旧版本的normalize_binance_trade方法，使用新版本的专用方法：
    # - normalize_binance_spot_trade() (第1410行)
    # - normalize_binance_futures_trade() (第1479行)

    def normalize_binance_orderbook(self, raw_data: dict, symbol: str, market_type: str = "spot", event_time_ms: Optional[int] = None) -> Optional[NormalizedOrderBook]:
        """标准化Binance订单簿数据

        Args:
            raw_data: 原始订单簿数据
            symbol: 交易对符号
            market_type: 市场类型 (spot, perpetual, futures)
            event_time_ms: 可选的事件时间戳（毫秒），来自WebSocket消息的E字段
        """
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

            # 🔧 时间戳修复：优先使用事件时间戳，否则使用当前时间
            if event_time_ms:
                timestamp = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)  # Binance REST API没有时间戳

            # 根据market_type确定交易所名称
            exchange_name = "binance_spot" if market_type == "spot" else "binance_derivatives"

            return NormalizedOrderBook(
                exchange_name=exchange_name,
                symbol_name=self._normalize_symbol_format(symbol),
                bids=bids,
                asks=asks,
                timestamp=timestamp,
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

        实际OKX强平数据格式:
        {
          "data": [{
            "instId": "BTC-USDT-SWAP",
            "details": [{
              "side": "buy",
              "sz": "0.1",
              "bkPx": "50000",
              "bkLoss": "100",
              "ts": "1640995200000",
              "ccy": "",
              "posSide": "short"
            }]
          }]
        }

        Args:
            raw_data: OKX WebSocket强平订单事件的原始数据

        Returns:
            标准化的强平订单对象，失败时返回None
        """
        try:
            # 验证数据结构
            if "data" not in raw_data or not raw_data["data"]:
                self.logger.warning("OKX强平数据缺少data字段", raw_data_preview=str(raw_data)[:200])
                return None

            data_item = raw_data["data"][0]

            # 获取交易对ID（优先使用返回字段，其次使用请求上下文字段）
            inst_id = data_item.get("instId") or raw_data.get("instId") or raw_data.get("symbol") or (raw_data.get("arg", {}) if isinstance(raw_data.get("arg"), dict) else {}).get("instId") or ""
            if not inst_id:
                self.logger.warning("OKX强平数据缺少instId字段", data_item=data_item)
                return None

            # 检查数据格式：嵌套格式还是扁平格式
            if "details" in data_item:
                # 嵌套格式：从details数组中获取数据
                details = data_item.get("details", [])
                if not details:
                    self.logger.warning("OKX强平数据details为空", inst_id=inst_id)
                    return None
                detail = details[0]  # 处理第一个详情
            else:
                # 扁平格式：直接使用data_item作为detail
                detail = data_item

            # 解析产品类型 - 从arg或instId推断
            if "SWAP" in inst_id:
                product_type = ProductType.PERPETUAL
            elif "FUTURES" in inst_id:
                product_type = ProductType.FUTURES
            else:
                product_type = ProductType.PERPETUAL  # 默认为永续合约

            # 标准化交易对格式
            symbol_name = self.normalize_symbol_format(inst_id, exchange="okx_derivatives")
            if not symbol_name:
                self.logger.warning("无法标准化OKX交易对格式",
                                  inst_id=inst_id,
                                  exchange="okx_derivatives")
                return None

            # 解析强平方向
            side_str = detail.get("side", "").lower()
            if side_str == "buy":
                side = LiquidationSide.BUY
            elif side_str == "sell":
                side = LiquidationSide.SELL
            else:
                self.logger.warning("无效的OKX强平方向", side=side_str, inst_id=inst_id)
                return None

            # 解析价格和数量
            try:
                # OKX使用bkPx作为破产价格
                price = Decimal(str(detail.get("bkPx", "0")))
                quantity = Decimal(str(detail.get("sz", "0")))

                # 验证价格和数量
                if price <= 0:
                    self.logger.warning("OKX强平价格无效", price=price, inst_id=inst_id)
                    return None
                if quantity <= 0:
                    self.logger.warning("OKX强平数量无效", quantity=quantity, inst_id=inst_id)
                    return None

            except (ValueError, TypeError, InvalidOperation) as e:
                self.logger.warning("OKX价格或数量解析失败",
                                  error=str(e),
                                  bkPx=detail.get("bkPx"),
                                  sz=detail.get("sz"),
                                  inst_id=inst_id)
                return None

            # 解析时间戳
            timestamp_str = detail.get("ts", "")
            try:
                timestamp_ms = int(timestamp_str)
                liquidation_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (ValueError, TypeError) as e:
                self.logger.warning("OKX时间戳解析失败",
                                  error=str(e),
                                  timestamp=timestamp_str,
                                  inst_id=inst_id)
                return None

            # OKX强平订单通常是已成交状态
            status = LiquidationStatus.FILLED

            # 计算名义价值
            notional_value = price * quantity

            # 生成唯一ID
            liquidation_id = f"okx_{timestamp_ms}_{inst_id}_{side_str}"

            return NormalizedLiquidation(
                exchange_name="okx_derivatives",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=inst_id,
                liquidation_id=liquidation_id,
                side=side,
                status=status,
                price=price,
                quantity=quantity,
                filled_quantity=quantity,  # OKX强平通常全部成交
                average_price=price,  # 使用破产价格作为平均价格
                notional_value=notional_value,
                liquidation_time=liquidation_time,
                timestamp=liquidation_time,
                bankruptcy_price=price,  # OKX的bkPx就是破产价格
                raw_data=raw_data
            )

        except Exception as e:
            self.logger.error("OKX强平数据标准化失败",
                            error=str(e),
                            raw_data_preview=str(raw_data)[:200])
            return None
        except Exception as e:
            self.logger.error(f"OKX强平订单标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_binance_liquidation(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLiquidation]:
        """
        标准化Binance强平订单数据

        Binance强平数据格式:
        {
          "e": "forceOrder",
          "E": 1568014460893,
          "o": {
            "s": "BTCUSDT",
            "S": "SELL",
            "o": "LIMIT",
            "f": "IOC",
            "q": "0.014",
            "p": "9910",
            "ap": "9910",
            "X": "FILLED",
            "l": "0.014",
            "z": "0.014",
            "T": 1568014460893
          }
        }

        Args:
            raw_data: Binance WebSocket强平订单事件的原始数据

        Returns:
            标准化的强平订单对象，失败时返回None
        """
        try:
            # 验证数据结构
            if "o" not in raw_data:
                self.logger.warning("Binance强平数据缺少订单信息", raw_data_preview=str(raw_data)[:200])
                return None

            order_data = raw_data["o"]

            # 获取交易对
            symbol = order_data.get("s", "")
            if not symbol:
                self.logger.warning("Binance强平数据缺少交易对", order_data=order_data)
                return None

            # 根据symbol格式判断产品类型
            if "USDT" in symbol and not symbol.endswith("_"):
                product_type = ProductType.PERPETUAL  # USDⓈ-M永续合约
            elif "_" in symbol:
                product_type = ProductType.FUTURES  # COIN-M期货
            else:
                self.logger.warning("无法识别的Binance产品类型", symbol=symbol)
                return None

            # 标准化交易对格式
            symbol_name = self.normalize_symbol_format(symbol, exchange="binance_derivatives")
            if not symbol_name:
                self.logger.warning("无法标准化Binance交易对格式",
                                  symbol=symbol,
                                  exchange="binance_derivatives")
                return None

            # 解析强平方向
            side_str = order_data.get("S", "").lower()
            if side_str == "buy":
                side = LiquidationSide.BUY
            elif side_str == "sell":
                side = LiquidationSide.SELL
            else:
                self.logger.warning("无效的Binance强平方向", side=side_str, symbol=symbol)
                return None

            # 解析价格和数量
            try:
                # Binance优先使用平均价格，回退到订单价格
                ap_str = order_data.get("ap", "")
                p_str = order_data.get("p", "")

                if ap_str and ap_str != "0":
                    price = Decimal(str(ap_str))
                    average_price = price
                elif p_str and p_str != "0":
                    price = Decimal(str(p_str))
                    average_price = None
                else:
                    self.logger.warning("Binance强平数据缺少有效价格",
                                      ap=ap_str, p=p_str, symbol=symbol)
                    return None

                quantity = Decimal(str(order_data.get("q", "0")))
                filled_quantity = Decimal(str(order_data.get("z", "0")))

                # 验证价格和数量
                if price <= 0:
                    self.logger.warning("Binance强平价格无效", price=price, symbol=symbol)
                    return None
                if quantity <= 0:
                    self.logger.warning("Binance强平数量无效", quantity=quantity, symbol=symbol)
                    return None

            except (ValueError, TypeError, InvalidOperation) as e:
                self.logger.warning("Binance价格或数量解析失败",
                                  error=str(e),
                                  ap=order_data.get("ap"),
                                  p=order_data.get("p"),
                                  q=order_data.get("q"),
                                  symbol=symbol)
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

            # 解析时间戳
            timestamp_ms = order_data.get("T", raw_data.get("E", 0))
            try:
                timestamp_ms = int(timestamp_ms)
                liquidation_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (ValueError, TypeError) as e:
                self.logger.warning("Binance时间戳解析失败",
                                  error=str(e),
                                  timestamp=timestamp_ms,
                                  symbol=symbol)
                return None

            # 计算名义价值
            notional_value = price * quantity

            # 生成唯一ID
            liquidation_id = f"binance_{timestamp_ms}_{symbol}_{side_str}"

            return NormalizedLiquidation(
                exchange_name="binance_derivatives",
                symbol_name=symbol_name,
                product_type=product_type,
                instrument_id=symbol,
                liquidation_id=liquidation_id,
                side=side,
                status=status,
                price=price,
                quantity=quantity,
                filled_quantity=filled_quantity,
                average_price=average_price,
                notional_value=notional_value,
                liquidation_time=liquidation_time,
                timestamp=liquidation_time,
                bankruptcy_price=price,  # 使用强平价格作为破产价格
                raw_data=raw_data
            )

        except Exception as e:
            self.logger.error("Binance强平数据标准化失败",
                            error=str(e),
                            raw_data_preview=str(raw_data)[:200])
            return None

    def normalize_okx_lsr_top_position(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRTopPosition]:
        """
        标准化OKX顶级大户多空持仓比例数据（按持仓量计算）

        OKX数据格式:
        {
          "code": "0",
          "msg": "",
          "data": [{
            "ts": "1597026383085",
            "longShortRatio": "1.4342",
            "longRatio": "0.5344",
            "shortRatio": "0.4656"
          }]
        }

        Args:
            raw_data: OKX API响应的原始数据

        Returns:
            标准化的顶级大户多空持仓比例对象，失败时返回None
        """
        try:
            # 验证数据结构
            if "data" not in raw_data:
                self.logger.warning("OKX顶级交易者数据缺少data字段", raw_data_preview=str(raw_data)[:200])
                return None

            data_list = raw_data["data"]
            if not data_list:
                self.logger.warning("OKX顶级交易者数据data为空")
                return None

            # 处理第一个数据项
            data_item = data_list[0]

            # 检查数据格式：OKX可能返回数组格式 [timestamp, ratio] 或对象格式
            if isinstance(data_item, list):
                # 数组格式: ["1753532700000", "0.9718379446640316"]
                if len(data_item) < 2:
                    self.logger.warning("OKX数组格式数据长度不足", data_item=data_item)
                    return None

                timestamp_ms = int(data_item[0])
                long_short_ratio = Decimal(str(data_item[1]))

                # 对于数组格式，我们只有总的比例，需要计算多空比例
                # 假设 long_short_ratio 是 long/(long+short) 的比例
                if long_short_ratio > 1:
                    # 如果大于1，可能是 long/short 的比值
                    long_position_ratio = long_short_ratio / (long_short_ratio + 1)
                    short_position_ratio = 1 / (long_short_ratio + 1)
                else:
                    # 如果小于等于1，可能是 long/(long+short) 的比例
                    long_position_ratio = long_short_ratio
                    short_position_ratio = 1 - long_short_ratio
                    long_short_ratio = long_position_ratio / short_position_ratio if short_position_ratio > 0 else Decimal('0')

                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            elif isinstance(data_item, dict):
                # 对象格式: {"ts": "1597026383085", "longShortRatio": "1.4342", ...}
                # 解析时间戳
                try:
                    timestamp_ms = int(data_item.get("ts", "0"))
                    timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                except (ValueError, TypeError) as e:
                    self.logger.warning("OKX时间戳解析失败",
                                      error=str(e),
                                      timestamp=data_item.get("ts"))
                    return None

                # 解析比例数据
                try:
                    long_short_ratio = Decimal(str(data_item.get("longShortRatio", "0")))
                    long_position_ratio = Decimal(str(data_item.get("longRatio", "0")))
                    short_position_ratio = Decimal(str(data_item.get("shortRatio", "0")))

                    # 验证数据有效性
                    if long_short_ratio <= 0 or long_position_ratio <= 0 or short_position_ratio <= 0:
                        self.logger.warning("OKX比例数据无效",
                                          long_short_ratio=long_short_ratio,
                                          long_position_ratio=long_position_ratio,
                                          short_position_ratio=short_position_ratio)
                        return None

                except (ValueError, TypeError, InvalidOperation) as e:
                    self.logger.warning("OKX比例数据解析失败",
                                      error=str(e),
                                      longShortRatio=data_item.get("longShortRatio"),
                                      longRatio=data_item.get("longRatio"),
                                      shortRatio=data_item.get("shortRatio"))
                    return None
            else:
                self.logger.warning("OKX数据格式不支持", data_item_type=type(data_item), data_item=data_item)
                return None

            # 从请求参数中获取交易对和周期信息（需要在调用时传入）
            instrument_id = raw_data.get("instId") or raw_data.get("symbol") or (raw_data.get("arg", {}) if isinstance(raw_data.get("arg"), dict) else {}).get("instId") or ""
            period = raw_data.get("period", "1h")

            if not instrument_id:
                self.logger.warning("OKX顶级交易者数据缺少交易对信息")
                return None

            # 标准化交易对格式
            symbol_name = self.normalize_symbol_format(instrument_id, exchange="okx_derivatives")
            if not symbol_name:
                self.logger.warning("无法标准化OKX交易对格式",
                                  instrument_id=instrument_id,
                                  exchange="okx_derivatives")
                return None

            return NormalizedLSRTopPosition(
                exchange_name="okx_derivatives",
                symbol_name=symbol_name,
                product_type=ProductType.PERPETUAL,
                instrument_id=instrument_id,
                timestamp=timestamp,
                long_short_ratio=long_short_ratio,
                long_position_ratio=long_position_ratio,
                short_position_ratio=short_position_ratio,
                period=period,
                raw_data=raw_data
            )

        except Exception as e:
            self.logger.error("OKX顶级交易者数据标准化失败",
                            error=str(e),
                            raw_data_preview=str(raw_data)[:200])
            return None

    def normalize_binance_lsr_top_position(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRTopPosition]:
        """
        标准化Binance顶级大户多空持仓比例数据（按持仓量计算）

        Binance数据格式:
        [{
          "symbol": "BTCUSDT",
          "longShortRatio": "1.4342",
          "longAccount": "0.5344",
          "shortAccount": "0.4238",
          "timestamp": "1583139600000"
        }]

        Args:
            raw_data: Binance API响应的原始数据

        Returns:
            标准化的顶级交易者多空持仓比例对象，失败时返回None
        """
        try:
            # 验证数据结构
            if not isinstance(raw_data, list) or not raw_data:
                self.logger.warning("Binance顶级交易者数据格式无效", raw_data_preview=str(raw_data)[:200])
                return None

            # 处理第一个数据项
            data_item = raw_data[0]

            # 获取交易对
            symbol = data_item.get("symbol", "")
            if not symbol:
                self.logger.warning("Binance顶级交易者数据缺少交易对", data_item=data_item)
                return None

            # 标准化交易对格式
            symbol_name = self.normalize_symbol_format(symbol, exchange="binance_derivatives")
            if not symbol_name:
                self.logger.warning("无法标准化Binance交易对格式",
                                  symbol=symbol,
                                  exchange="binance_derivatives")
                return None

            # 解析时间戳
            try:
                timestamp_ms = int(data_item.get("timestamp", "0"))
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (ValueError, TypeError) as e:
                self.logger.warning("Binance时间戳解析失败",
                                  error=str(e),
                                  timestamp=data_item.get("timestamp"))
                return None

            # 解析比例数据
            try:
                long_short_ratio = Decimal(str(data_item.get("longShortRatio", "0")))
                long_account = Decimal(str(data_item.get("longAccount", "0")))
                short_account = Decimal(str(data_item.get("shortAccount", "0")))

                # 验证数据有效性
                if long_short_ratio <= 0 or long_account <= 0 or short_account <= 0:
                    self.logger.warning("Binance比例数据无效",
                                      long_short_ratio=long_short_ratio,
                                      long_account=long_account,
                                      short_account=short_account)
                    return None

            except (ValueError, TypeError, InvalidOperation) as e:
                self.logger.warning("Binance比例数据解析失败",
                                  error=str(e),
                                  longShortRatio=data_item.get("longShortRatio"),
                                  longAccount=data_item.get("longAccount"),
                                  shortAccount=data_item.get("shortAccount"))
                return None

            # 从请求参数中获取周期信息（需要在调用时传入）
            period = raw_data.get("period", "1h") if isinstance(raw_data, dict) else "1h"

            return NormalizedLSRTopPosition(
                exchange_name="binance_derivatives",
                symbol_name=symbol_name,
                product_type=ProductType.PERPETUAL,
                instrument_id=symbol,
                timestamp=timestamp,
                long_short_ratio=long_short_ratio,
                long_position_ratio=long_account,
                short_position_ratio=short_account,
                period=period,
                raw_data={"data": raw_data}  # 包装为统一格式
            )

        except Exception as e:
            self.logger.error("Binance顶级交易者数据标准化失败",
                            error=str(e),
                            raw_data_preview=str(raw_data)[:200])
            return None

    def normalize_okx_lsr_all_account(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRAllAccount]:
        """
        标准化OKX全市场多空持仓人数比例数据（按账户数计算）

        OKX数据格式:
        {
          "code": "0",
          "msg": "",
          "data": [{
            "ts": "1597026383085",
            "longShortRatio": "1.4342",
            "longRatio": "0.5344",
            "shortRatio": "0.4656"
          }]
        }

        Args:
            raw_data: OKX API响应的原始数据

        Returns:
            标准化的多空持仓人数比例对象，失败时返回None
        """
        try:
            # 验证数据结构
            if "data" not in raw_data:
                self.logger.warning("OKX多空持仓人数比例数据缺少data字段", raw_data_preview=str(raw_data)[:200])
                return None

            data_list = raw_data["data"]
            if not data_list:
                self.logger.warning("OKX多空持仓人数比例数据data为空")
                return None

            # 处理第一个数据项
            data_item = data_list[0]

            # 检查数据格式：OKX可能返回数组格式 [timestamp, ratio] 或对象格式
            if isinstance(data_item, list):
                # 数组格式: ["1753532700000", "0.9718379446640316"]
                if len(data_item) < 2:
                    self.logger.warning("OKX数组格式数据长度不足", data_item=data_item)
                    return None

                timestamp_ms = int(data_item[0])
                long_short_ratio = Decimal(str(data_item[1]))

                # 对于数组格式，我们只有总的比例，需要计算多空比例
                # 假设 long_short_ratio 是 long/(long+short) 的比例
                if long_short_ratio > 1:
                    # 如果大于1，可能是 long/short 的比值
                    long_account_ratio = long_short_ratio / (long_short_ratio + 1)
                    short_account_ratio = 1 / (long_short_ratio + 1)
                else:
                    # 如果小于等于1，可能是 long/(long+short) 的比例
                    long_account_ratio = long_short_ratio
                    short_account_ratio = 1 - long_short_ratio
                    long_short_ratio = long_account_ratio / short_account_ratio if short_account_ratio > 0 else Decimal('0')

                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

            elif isinstance(data_item, dict):
                # 对象格式: {"ts": "1597026383085", "longShortRatio": "1.4342", ...}
                # 解析时间戳
                try:
                    timestamp_ms = int(data_item.get("ts", "0"))
                    timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                except (ValueError, TypeError) as e:
                    self.logger.warning("OKX时间戳解析失败",
                                      error=str(e),
                                      timestamp=data_item.get("ts"))
                    return None

                # 解析比例数据
                try:
                    long_short_ratio = Decimal(str(data_item.get("longShortRatio", "0")))
                    long_account_ratio = Decimal(str(data_item.get("longRatio", "0")))
                    short_account_ratio = Decimal(str(data_item.get("shortRatio", "0")))

                    # 验证数据有效性
                    if long_short_ratio <= 0 or long_account_ratio <= 0 or short_account_ratio <= 0:
                        self.logger.warning("OKX比例数据无效",
                                          long_short_ratio=long_short_ratio,
                                          long_account_ratio=long_account_ratio,
                                          short_account_ratio=short_account_ratio)
                        return None

                except (ValueError, TypeError, InvalidOperation) as e:
                    self.logger.warning("OKX比例数据解析失败",
                                      error=str(e),
                                      longShortRatio=data_item.get("longShortRatio"),
                                      longRatio=data_item.get("longRatio"),
                                      shortRatio=data_item.get("shortRatio"))
                    return None
            else:
                self.logger.warning("OKX数据格式不支持", data_item_type=type(data_item), data_item=data_item)
                return None

            # 从请求参数中获取交易对和周期信息（需要在调用时传入）
            # All Account API使用ccy参数，需要重构为完整的交易对
            ccy = raw_data.get("ccy", "")
            period = raw_data.get("period", "5m")

            if not ccy:
                self.logger.warning("OKX多空持仓人数比例数据缺少币种信息")
                return None

            # 从ccy重构为完整的交易对格式（假设是USDT永续合约）
            instrument_id = f"{ccy}-USDT-SWAP"

            # 标准化交易对格式
            symbol_name = self.normalize_symbol_format(instrument_id, exchange="okx_derivatives")
            if not symbol_name:
                self.logger.warning("无法标准化OKX交易对格式",
                                  instrument_id=instrument_id,
                                  ccy=ccy,
                                  exchange="okx_derivatives")
                return None

            return NormalizedLSRAllAccount(
                exchange_name="okx_derivatives",
                symbol_name=symbol_name,
                product_type=ProductType.PERPETUAL,
                instrument_id=instrument_id,
                timestamp=timestamp,
                long_short_ratio=long_short_ratio,
                long_account_ratio=long_account_ratio,
                short_account_ratio=short_account_ratio,
                period=period,
                raw_data=raw_data
            )

        except Exception as e:
            self.logger.error("OKX多空持仓人数比例数据标准化失败",
                            error=str(e),
                            raw_data_preview=str(raw_data)[:200])
            return None

    def normalize_binance_lsr_all_account(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRAllAccount]:
        """
        标准化Binance全市场多空持仓人数比例数据（按账户数计算）

        Binance数据格式:
        [{
          "symbol": "BTCUSDT",
          "longShortRatio": "0.1960",
          "longAccount": "0.6622",
          "shortAccount": "0.3378",
          "timestamp": "1583139600000"
        }]

        Args:
            raw_data: Binance API响应的原始数据

        Returns:
            标准化的多空持仓人数比例对象，失败时返回None
        """
        try:
            # 验证数据结构
            if not isinstance(raw_data, list) or not raw_data:
                self.logger.warning("Binance多空持仓人数比例数据格式无效", raw_data_preview=str(raw_data)[:200])
                return None

            # 处理第一个数据项
            data_item = raw_data[0]

            # 获取交易对
            symbol = data_item.get("symbol", "")
            if not symbol:
                self.logger.warning("Binance多空持仓人数比例数据缺少交易对", data_item=data_item)
                return None

            # 标准化交易对格式
            symbol_name = self.normalize_symbol_format(symbol, exchange="binance_derivatives")
            if not symbol_name:
                self.logger.warning("无法标准化Binance交易对格式",
                                  symbol=symbol,
                                  exchange="binance_derivatives")
                return None

            # 解析时间戳
            try:
                timestamp_ms = int(data_item.get("timestamp", "0"))
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (ValueError, TypeError) as e:
                self.logger.warning("Binance时间戳解析失败",
                                  error=str(e),
                                  timestamp=data_item.get("timestamp"))
                return None

            # 解析比例数据
            try:
                long_short_ratio = Decimal(str(data_item.get("longShortRatio", "0")))
                long_account = Decimal(str(data_item.get("longAccount", "0")))
                short_account = Decimal(str(data_item.get("shortAccount", "0")))

                # 验证数据有效性
                if long_short_ratio <= 0 or long_account <= 0 or short_account <= 0:
                    self.logger.warning("Binance比例数据无效",
                                      long_short_ratio=long_short_ratio,
                                      long_account=long_account,
                                      short_account=short_account)
                    return None

            except (ValueError, TypeError, InvalidOperation) as e:
                self.logger.warning("Binance比例数据解析失败",
                                  error=str(e),
                                  longShortRatio=data_item.get("longShortRatio"),
                                  longAccount=data_item.get("longAccount"),
                                  shortAccount=data_item.get("shortAccount"))
                return None

            # 从请求参数中获取周期信息（需要在调用时传入）
            period = raw_data.get("period", "5m") if isinstance(raw_data, dict) else "5m"

            return NormalizedLSRAllAccount(
                exchange_name="binance_derivatives",
                symbol_name=symbol_name,
                product_type=ProductType.PERPETUAL,
                instrument_id=symbol,
                timestamp=timestamp,
                long_short_ratio=long_short_ratio,
                long_account_ratio=long_account,
                short_account_ratio=short_account,
                period=period,
                raw_data={"data": raw_data}  # 包装为统一格式
            )

        except Exception as e:
            self.logger.error("Binance多空持仓人数比例数据标准化失败",
                            error=str(e),
                            raw_data_preview=str(raw_data)[:200])
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
                product_type = "perpetual"
                symbol_name = instrument_id.replace("-SWAP", "")
            elif "-" in instrument_id and len(instrument_id.split("-")) >= 3:
                # 期货合约格式: BTC-USD-240329
                product_type = "futures"
                parts = instrument_id.split("-")
                symbol_name = f"{parts[0]}-{parts[1]}"
            else:
                product_type = "perpetual"  # 默认为永续合约
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
                exchange_name="okx_derivatives",
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
            product_type = "perpetual"

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
                product_type = "perpetual"
                symbol_name = instrument_id.replace("-SWAP", "")
            elif "-PERPETUAL" in instrument_id:
                product_type = "perpetual"
                symbol_name = instrument_id.replace("-PERPETUAL", "")
            else:
                product_type = "perpetual"  # 默认为永续合约
                symbol_name = self._normalize_symbol_format(instrument_id)

            # 资金费率信息 - 优先使用realizedRate（历史实际费率），其次使用fundingRate
            current_funding_rate = Decimal(str(funding_data.get("realizedRate", funding_data.get("fundingRate", "0"))))

            # 下次资金费率时间优先取原始字段；缺失时基于“当前时间”推算最近的8小时结算点
            next_funding_time = None
            if "nextFundingTime" in funding_data and funding_data["nextFundingTime"]:
                next_funding_time_ms = int(funding_data["nextFundingTime"])
                next_funding_time = datetime.fromtimestamp(next_funding_time_ms / 1000, tz=timezone.utc)
            else:
                # 基于当前UTC时间推算：选择 {00:00, 08:00, 16:00} 中“下一个”结算点，避免因历史fundingTime造成>8h偏移
                now_utc = datetime.now(timezone.utc)
                base_hour = (now_utc.hour // 8) * 8
                candidate_hour = base_hour + 8
                if candidate_hour >= 24:
                    next_funding_time = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                else:
                    next_funding_time = now_utc.replace(hour=candidate_hour, minute=0, second=0, microsecond=0)

            # 基于当前时间对 next_funding_time 进行业务窗口收敛（<= 8h）
            try:
                now_utc = datetime.now(timezone.utc)
                # 目标最近结算点（相对 now）
                base_hour = (now_utc.hour // 8) * 8
                candidate_hour = base_hour + 8
                desired_next = (now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)) \
                    if candidate_hour >= 24 else now_utc.replace(hour=candidate_hour, minute=0, second=0, microsecond=0)
                if next_funding_time is None or (next_funding_time - now_utc).total_seconds() > 8*3600 + 60:
                    next_funding_time = desired_next
            except Exception:
                pass

            # 当前时间戳
            funding_time_ms = int(funding_data.get("fundingTime", funding_data.get("ts", "0")))
            if funding_time_ms:
                timestamp = datetime.fromtimestamp(funding_time_ms / 1000, tz=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            return NormalizedFundingRate(
                exchange_name="okx_derivatives",
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
            product_type = "perpetual"

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
                instrument_type="perpetual",  # OKX永续合约
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
                instrument_type="perpetual",  # OKX合约
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

            # 🔧 交易方向转换：Binance的m字段表示买方是否是做市方
            # m=true: 买方是做市方 → 此次成交是主动卖出 → side="sell"
            # m=false: 买方是接受方 → 此次成交是主动买入 → side="buy"
            is_maker = data.get("m", False)
            side = "sell" if is_maker else "buy"

            # 时间戳处理
            trade_time_ms = int(data.get("T", "0"))
            event_time_ms = int(data.get("E", "0"))

            trade_time = datetime.fromtimestamp(trade_time_ms / 1000, tz=timezone.utc)
            event_time = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc) if event_time_ms else None

            return NormalizedTrade(
                exchange_name="binance_spot",
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

            # 🔧 交易方向转换：Binance的m字段表示买方是否是做市方
            # m=true: 买方是做市方 → 此次成交是主动卖出 → side="sell"
            # m=false: 买方是接受方 → 此次成交是主动买入 → side="buy"
            is_maker = data.get("m", False)
            side = "sell" if is_maker else "buy"

            # 时间戳处理
            trade_time_ms = int(data.get("T", "0"))
            event_time_ms = int(data.get("E", "0"))

            trade_time = datetime.fromtimestamp(trade_time_ms / 1000, tz=timezone.utc)
            event_time = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc) if event_time_ms else None

            return NormalizedTrade(
                exchange_name="binance_derivatives",
                symbol_name=symbol_name,
                currency=currency,
                trade_id=trade_id,
                price=price,
                quantity=quantity,
                quote_quantity=quote_quantity,
                side=side,
                timestamp=trade_time,
                event_time=event_time,
                trade_type="perpetual",
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
                    trade_type = "perpetual"
                elif any(month in symbol for month in ["0329", "0628", "0927", "1228"]):
                    trade_type = "futures"
                else:
                    trade_type = "spot"

            # 根据trade_type确定正确的交易所名称
            if trade_type == "spot":
                exchange_name = "okx_spot"
            elif trade_type in ["perpetual", "futures"]:
                exchange_name = "okx_derivatives"
            else:
                exchange_name = "okx_spot"  # 默认现货

            return NormalizedTrade(
                exchange_name=exchange_name,
                symbol_name=symbol_name,
                currency=currency,
                trade_id=trade_id,
                price=price,
                quantity=quantity,
                quote_quantity=quote_quantity,
                side=side,
                timestamp=trade_time,
                event_time=trade_time,  # OKX只提供一个时间戳，事件时间与成交时间相同
                trade_type=trade_type,
                # 🔧 OKX不提供做市方信息，设为None保持一致性
                is_maker=None,
                raw_data=data
            )

        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"OKX交易数据标准化失败: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"OKX交易数据标准化发生未知错误: {e}", exc_info=True)
            return None

    def normalize_trade_data(self, trade_data: Dict[str, Any], exchange: Exchange, market_type) -> Dict[str, Any]:
        """
        🔧 新增：统一成交数据标准化方法
        为TradesManager提供统一的数据标准化接口
        """
        try:
            # 基础标准化 - 使用ClickHouse兼容毫秒UTC时间戳
            # 事件时间优先（来自交易所的成交/事件时间），如缺失则兜底为采集时间
            ts_val = trade_data.get('timestamp')
            clickhouse_timestamp: str
            if ts_val is None:
                # 兜底：当前UTC时间（毫秒）
                clickhouse_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            else:
                try:
                    if isinstance(ts_val, (int, float)):
                        # 认为是毫秒时间戳
                        dt = datetime.fromtimestamp(float(ts_val) / 1000.0, tz=timezone.utc)
                        clickhouse_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    elif isinstance(ts_val, str):
                        from dateutil import parser as date_parser
                        dt = date_parser.parse(ts_val)
                        # 强制转换到UTC
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            dt = dt.astimezone(timezone.utc)
                        clickhouse_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    elif hasattr(ts_val, 'isoformat'):
                        # datetime
                        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                        clickhouse_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    else:
                        clickhouse_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                except Exception:
                    clickhouse_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            collected_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            normalized = {
                'symbol': trade_data.get('symbol', ''),
                'price': str(trade_data.get('price', '0')),
                'quantity': str(trade_data.get('quantity', '0')),
                'timestamp': clickhouse_timestamp,  # 事件时间（毫秒UTC）
                'trade_time': clickhouse_timestamp,  # 补齐 trade_time 字段，等于 timestamp
                'collected_at': collected_at,       # 采集时间（毫秒UTC）
                'side': trade_data.get('side', 'unknown'),
                'trade_id': str(trade_data.get('trade_id', '')),
                'exchange': exchange.value,
                'market_type': trade_data.get('market_type', ''),
                'data_source': 'marketprism'
            }

            # 标准化交易对格式
            symbol = trade_data.get('symbol', '')
            normalized_symbol = self.normalize_symbol_format(symbol, exchange.value)
            if normalized_symbol:
                normalized['normalized_symbol'] = normalized_symbol
            else:
                self.logger.warning(f"无法标准化Symbol格式: {symbol}, exchange: {exchange.value}")
                normalized['normalized_symbol'] = symbol

            # 移除调试代码 - 已确认 trade_time 字段正常工作

            return normalized

        except Exception as e:
            self.logger.error(f"成交数据标准化失败: {e}")
            return trade_data

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

            # 提取必需字段 - 支持多种字段名
            timestamp_ms = volatility_data.get("timestamp")
            volatility_value = volatility_data.get("volatility") or volatility_data.get("volatility_index")
            index_name = volatility_data.get("index_name", "")
            currency = volatility_data.get("currency", "")

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

            # 从多个来源提取交易对信息 - 解析完整的交易对格式
            symbol_pair = ""
            if currency:
                # 如果直接提供了currency字段，使用它作为基础
                symbol_pair = currency.upper()
            elif index_name:
                # 解析类似 "BTCDVOL_USDC-DERIBIT-INDEX" 的格式
                if "DVOL_" in index_name:
                    # 提取DVOL前后的货币信息
                    dvol_pos = index_name.find("DVOL_")
                    if dvol_pos > 0:
                        base_currency = index_name[:dvol_pos]  # BTC
                        # 提取DVOL_后面到"-DERIBIT"之间的部分
                        after_dvol = index_name[dvol_pos + 5:]  # "USDC-DERIBIT-INDEX"
                        if "-" in after_dvol:
                            quote_currency = after_dvol.split("-")[0]  # USDC
                            symbol_pair = f"{base_currency}-{quote_currency}"  # BTC-USDC
                        else:
                            symbol_pair = base_currency  # 如果没有找到报价货币，只用基础货币
                elif index_name.startswith("BTC"):
                    symbol_pair = "BTC-USDC"  # 默认BTC对USDC
                elif index_name.startswith("ETH"):
                    symbol_pair = "ETH-USDC"  # 默认ETH对USDC

            # 如果还是没有找到，使用默认值
            if not symbol_pair:
                symbol_pair = "BTC-USDC"  # 默认交易对

            # 转换波动率值
            volatility_decimal = Decimal(str(volatility_value))

            # 计算数据质量评分
            quality_score = self._calculate_volatility_quality_score(
                volatility_decimal, timestamp, index_name
            )

            # 提取分辨率信息（如果有）
            resolution = volatility_data.get("resolution")

            # 从交易对中提取基础货币
            base_currency = symbol_pair.split("-")[0] if "-" in symbol_pair else symbol_pair

            return NormalizedVolatilityIndex(
                exchange_name="deribit_derivatives",
                currency=base_currency,  # 基础货币 (BTC, ETH)
                symbol_name=symbol_pair,  # 完整交易对 (BTC-USDC, ETH-USDC)
                index_name=index_name or f"{base_currency}DVOL",
                market_type="options",  # 修复：波动率指数来源于期权产品，不是永续合约
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

    def normalize_funding_rate(self, exchange: str, market_type: str, symbol: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化资金费率数据（就地统一时间戳为UTC毫秒字符串）

        输入原始数据字段兼容：
        - Binance: { symbol, lastFundingRate, nextFundingTime(ms), time(ms), markPrice, indexPrice }
        - OKX: { instId, fundingRate, nextFundingRate, fundingTime(ms) }
        其他来源：若提供 ISO 字符串 / datetime / epoch 秒/毫秒 亦能解析。
        """
        from datetime import datetime, timezone
        from decimal import Decimal
        try:
            # 小范围局部解析函数（不抽公共工具，遵循“就地处理”）
            def to_ms_str(ts_val) -> Optional[str]:
                if ts_val is None:
                    return None
                try:
                    if isinstance(ts_val, (int, float)):
                        # 既支持秒也支持毫秒：按 >1e12 判断
                        sec = float(ts_val) / (1000.0 if ts_val > 1e12 else 1.0)
                        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if hasattr(ts_val, 'isoformat'):
                        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if isinstance(ts_val, str):
                        try:
                            from dateutil import parser as date_parser
                            dt = date_parser.parse(ts_val)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        except Exception:
                            pass
                except Exception:
                    pass
                # 兜底当前时间
                return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # 统一 symbol 与 instrument_id
            instrument_id = raw_data.get('symbol') or raw_data.get('instId') or symbol
            normalized_symbol = self.normalize_symbol_format(instrument_id, exchange)

            # 解析费率与价格（正确处理字段优先级，0值是有效的）
            def get_first_valid_value(*keys):
                """获取第一个非空非None的值，0是有效值"""
                for key in keys:
                    value = raw_data.get(key)
                    if value is not None and value != '':
                        return value
                return None

            current_funding_rate = get_first_valid_value('lastFundingRate', 'fundingRate', 'currentFundingRate', 'realizedRate')
            est_rate = get_first_valid_value('nextFundingRate', 'estimatedFundingRate', 'interestRate')
            mark_price = get_first_valid_value('markPrice')
            index_price = get_first_valid_value('indexPrice')

            premium_index = None
            try:
                if mark_price is not None and index_price is not None:
                    premium_index = str(Decimal(str(mark_price)) - Decimal(str(index_price)))
            except Exception:
                premium_index = None

            # 时间戳来源优先级
            ts_candidates = [raw_data.get('time'), raw_data.get('ts'), raw_data.get('fundingTime')]
            ts_val = next((v for v in ts_candidates if v is not None), None)
            next_ft = raw_data.get('nextFundingTime') or raw_data.get('fundingTime')

            result = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': normalized_symbol,
                'instrument_id': instrument_id,
                'current_funding_rate': str(current_funding_rate) if current_funding_rate is not None else None,
                'estimated_funding_rate': str(est_rate) if est_rate is not None else None,
                'next_funding_time': to_ms_str(next_ft) if next_ft is not None else None,
                'funding_interval': '8h',
                'mark_price': str(mark_price) if mark_price is not None else None,
                'index_price': str(index_price) if index_price is not None else None,
                'premium_index': premium_index,
                'timestamp': to_ms_str(ts_val) if ts_val is not None else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'data_source': 'marketprism'
            }
            return result
        except Exception as e:
            self.logger.error(f"资金费率标准化失败: {e}")
            # 返回最小安全对象
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            return {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol,
                'timestamp': now,
                'collected_at': now,
                'data_source': 'marketprism'
            }

    def normalize_open_interest(self, exchange: str, market_type: str, symbol: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化未平仓量数据（就地统一时间戳为UTC毫秒字符串）

        输入原始数据字段兼容：
        - Binance: { symbol, openInterest, time(ms), markPrice, contractSize }
        - OKX: { instId, oi, ts(ms), markPrice, ctVal, ctValCcy, oiCcy }
        其他来源：若提供 ISO 字符串 / datetime / epoch 秒/毫秒 亦能解析。
        """
        from datetime import datetime, timezone
        from decimal import Decimal
        try:
            # 小范围局部解析函数（不抽公共工具，遵循"就地处理"）
            def to_ms_str(ts_val) -> Optional[str]:
                if ts_val is None:
                    return None
                try:
                    if isinstance(ts_val, (int, float)):
                        # 既支持秒也支持毫秒：按 >1e12 判断
                        sec = float(ts_val) / (1000.0 if ts_val > 1e12 else 1.0)
                        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if hasattr(ts_val, 'isoformat'):
                        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if isinstance(ts_val, str):
                        try:
                            from dateutil import parser as date_parser
                            dt = date_parser.parse(ts_val)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        except Exception:
                            pass
                except Exception:
                    pass
                # 兜底当前时间
                return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # 统一 symbol 与 instrument_id
            instrument_id = raw_data.get('symbol') or raw_data.get('instId') or symbol
            normalized_symbol = self.normalize_symbol_format(instrument_id, exchange)

            # 解析未平仓量数值（合约张数）
            open_interest_value = raw_data.get('openInterest') or raw_data.get('oi')

            # 解析价格相关字段
            mark_price = raw_data.get('markPrice')
            index_price = raw_data.get('indexPrice')

            # 解析合约规格（用于USD估值计算）
            contract_size = raw_data.get('contractSize') or raw_data.get('ctVal')
            contract_size_ccy = raw_data.get('ctValCcy') or raw_data.get('oiCcy')

            # 计算USD估值（如果有足够信息）
            open_interest_usd = None
            try:
                if all(x is not None for x in [open_interest_value, contract_size, mark_price]):
                    oi_val = Decimal(str(open_interest_value))
                    cs_val = Decimal(str(contract_size))
                    mp_val = Decimal(str(mark_price))
                    open_interest_usd = str(oi_val * cs_val * mp_val)
            except Exception:
                open_interest_usd = None

            # 时间戳来源优先级
            ts_candidates = [raw_data.get('time'), raw_data.get('ts'), raw_data.get('timestamp')]
            ts_val = next((v for v in ts_candidates if v is not None), None)

            result = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': normalized_symbol,
                'instrument_id': instrument_id,
                'open_interest_value': str(open_interest_value) if open_interest_value is not None else None,
                'open_interest_usd': open_interest_usd,
                'open_interest_unit': 'contracts',
                'mark_price': str(mark_price) if mark_price is not None else None,
                'index_price': str(index_price) if index_price is not None else None,
                'contract_size': str(contract_size) if contract_size is not None else None,
                'contract_size_ccy': contract_size_ccy,
                'change_24h': None,  # 需要额外计算
                'change_24h_percent': None,
                'timestamp': to_ms_str(ts_val) if ts_val is not None else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'data_source': 'marketprism'
            }
            return result
        except Exception as e:
            self.logger.error(f"未平仓量标准化失败: {e}")
            # 返回最小安全对象
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            return {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol,
                'timestamp': now,
                'collected_at': now,
                'data_source': 'marketprism'
            }

    def normalize_liquidation(self, exchange: str, market_type: str, symbol: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化强平数据（就地统一时间戳为UTC毫秒字符串）

        输入原始数据字段兼容：
        - Binance: { E(ms), o: { s, S, q, p, T(ms), ... } }
        - OKX: { instId, side, sz, bkPx, bkLoss, ts(ms), cTime(ms) }
        其他来源：若提供 ISO 字符串 / datetime / epoch 秒/毫秒 亦能解析。
        """
        from datetime import datetime, timezone
        from decimal import Decimal
        try:
            # 小范围局部解析函数（不抽公共工具，遵循"就地处理"）
            def to_ms_str(ts_val) -> Optional[str]:
                if ts_val is None:
                    return None
                try:
                    if isinstance(ts_val, (int, float)):
                        # 既支持秒也支持毫秒：按 >1e12 判断
                        sec = float(ts_val) / (1000.0 if ts_val > 1e12 else 1.0)
                        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if hasattr(ts_val, 'isoformat'):
                        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if isinstance(ts_val, str):
                        try:
                            from dateutil import parser as date_parser
                            dt = date_parser.parse(ts_val)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        except Exception:
                            pass
                except Exception:
                    pass
                # 兜底当前时间
                return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # 解析不同交易所的数据格式
            if exchange.startswith('binance'):
                # Binance 格式：{ E: 事件时间, o: { s: symbol, S: side, q: quantity, p: price, T: 交易时间 } }
                event_time = raw_data.get('E')
                order_data = raw_data.get('o', {})
                instrument_id = order_data.get('s') or symbol
                side = order_data.get('S', '').lower()
                quantity = order_data.get('q')
                price = order_data.get('p')
                trade_time = order_data.get('T')
                liquidation_time = trade_time or event_time

            elif exchange.startswith('okx'):
                # OKX 格式：{ instId, side, sz, bkPx, bkLoss, ts, cTime }
                instrument_id = raw_data.get('instId') or symbol
                side = raw_data.get('side', '').lower()
                quantity = raw_data.get('sz')
                price = raw_data.get('bkPx')  # 破产价格
                event_time = raw_data.get('ts')
                liquidation_time = raw_data.get('cTime') or event_time

            else:
                # 通用格式处理
                instrument_id = raw_data.get('symbol') or raw_data.get('instId') or symbol
                side = raw_data.get('side', '').lower()
                quantity = raw_data.get('quantity') or raw_data.get('sz') or raw_data.get('q')
                price = raw_data.get('price') or raw_data.get('bkPx') or raw_data.get('p')
                event_time = raw_data.get('timestamp') or raw_data.get('ts') or raw_data.get('E')
                liquidation_time = raw_data.get('liquidation_time') or raw_data.get('cTime') or raw_data.get('T') or event_time

            # 统一 symbol
            normalized_symbol = self.normalize_symbol_format(instrument_id, exchange)

            # 时间戳来源优先级
            ts_candidates = [event_time, liquidation_time, raw_data.get('time')]
            ts_val = next((v for v in ts_candidates if v is not None), None)

            result = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': normalized_symbol,
                'instrument_id': instrument_id,
                'side': side,
                'quantity': str(quantity) if quantity is not None else None,
                'price': str(price) if price is not None else None,
                'liquidation_type': 'forced',  # 强制平仓
                'order_status': 'filled',  # 强平订单通常已成交
                'liquidation_time': to_ms_str(liquidation_time) if liquidation_time is not None else None,
                'timestamp': to_ms_str(ts_val) if ts_val is not None else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'data_source': 'marketprism'
            }
            return result
        except Exception as e:
            self.logger.error(f"强平数据标准化失败: {e}")
            # 返回最小安全对象
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            return {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol,
                'timestamp': now,
                'collected_at': now,
                'data_source': 'marketprism'
            }

    def normalize_lsr_top_position(self, exchange: str, market_type: str, symbol: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化LSR顶级持仓数据（就地统一时间戳为UTC毫秒字符串）

        输入原始数据字段兼容：
        - Binance: { symbol, longShortRatio, longAccount, shortAccount, timestamp(ms) }
        - OKX: { ts(ms), longShortRatio, longRatio, shortRatio }
        其他来源：若提供 ISO 字符串 / datetime / epoch 秒/毫秒 亦能解析。
        """
        from datetime import datetime, timezone
        from decimal import Decimal
        try:
            # 小范围局部解析函数（不抽公共工具，遵循"就地处理"）
            def to_ms_str(ts_val) -> Optional[str]:
                if ts_val is None:
                    return None
                try:
                    if isinstance(ts_val, (int, float)):
                        # 既支持秒也支持毫秒：按 >1e12 判断
                        sec = float(ts_val) / (1000.0 if ts_val > 1e12 else 1.0)
                        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if hasattr(ts_val, 'isoformat'):
                        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if isinstance(ts_val, str):
                        try:
                            from dateutil import parser as date_parser
                            dt = date_parser.parse(ts_val)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        except Exception:
                            pass
                except Exception:
                    pass
                # 兜底当前时间
                return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # 解析不同交易所的数据格式
            if exchange.startswith('binance'):
                # Binance 格式：{ symbol, longShortRatio, longAccount, shortAccount, timestamp }
                # 或者包装格式：{ data: [{ symbol, longShortRatio, longAccount, shortAccount, timestamp }] }
                if 'data' in raw_data and isinstance(raw_data['data'], list) and len(raw_data['data']) > 0:
                    data_item = raw_data['data'][0]
                else:
                    data_item = raw_data

                # 🔧 修复：检查 data_item 是否为 dict 类型
                if isinstance(data_item, dict):
                    instrument_id = data_item.get('symbol') or symbol
                    long_short_ratio = data_item.get('longShortRatio')
                    long_position_ratio = data_item.get('longAccount')  # Binance 使用 longAccount
                    short_position_ratio = data_item.get('shortAccount')  # Binance 使用 shortAccount
                    event_time = data_item.get('timestamp')
                else:
                    # 如果不是 dict，使用默认值
                    instrument_id = symbol
                    long_short_ratio = None
                    long_position_ratio = None
                    short_position_ratio = None
                    event_time = None

            elif exchange.startswith('okx'):
                # OKX 格式：{ data: [{ ts, longShortRatio, longRatio, shortRatio }] }
                # 或者直接格式：{ ts, longShortRatio, longRatio, shortRatio }
                if 'data' in raw_data and isinstance(raw_data['data'], list) and len(raw_data['data']) > 0:
                    data_item = raw_data['data'][0]
                    # 处理数组格式 [timestamp, longShortRatio, longRatio, shortRatio]
                    if isinstance(data_item, list) and len(data_item) >= 4:
                        event_time = data_item[0]
                        long_short_ratio = data_item[1]
                        long_position_ratio = data_item[2]
                        short_position_ratio = data_item[3]
                    else:
                        # 对象格式
                        event_time = data_item.get('ts')
                        long_short_ratio = data_item.get('longShortRatio')
                        long_position_ratio = data_item.get('longRatio')
                        short_position_ratio = data_item.get('shortRatio')
                else:
                    data_item = raw_data
                    # 🔧 修复：检查 data_item 是否为 dict 类型
                    if isinstance(data_item, dict):
                        event_time = data_item.get('ts')
                        long_short_ratio = data_item.get('longShortRatio')
                        long_position_ratio = data_item.get('longRatio')
                        short_position_ratio = data_item.get('shortRatio')
                    else:
                        # 如果不是 dict，使用默认值
                        event_time = None
                        long_short_ratio = None
                        long_position_ratio = None
                        short_position_ratio = None

                instrument_id = raw_data.get('symbol') if isinstance(raw_data, dict) else symbol

            else:
                # 通用格式处理
                # 🔧 修复：检查 raw_data 是否为 dict 类型
                if isinstance(raw_data, dict):
                    instrument_id = raw_data.get('symbol') or raw_data.get('instId') or symbol
                    long_short_ratio = raw_data.get('longShortRatio')
                    long_position_ratio = raw_data.get('longRatio') or raw_data.get('longAccount')
                    short_position_ratio = raw_data.get('shortRatio') or raw_data.get('shortAccount')
                    event_time = raw_data.get('timestamp') or raw_data.get('ts')
                else:
                    # 如果不是 dict，使用默认值
                    instrument_id = symbol
                    long_short_ratio = None
                    long_position_ratio = None
                    short_position_ratio = None
                    event_time = None

            # 统一 symbol
            normalized_symbol = self.normalize_symbol_format(instrument_id, exchange)

            # 时间戳来源优先级
            ts_candidates = [event_time, raw_data.get('time') if isinstance(raw_data, dict) else None]
            ts_val = next((v for v in ts_candidates if v is not None), None)

            result = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': normalized_symbol,
                'instrument_id': instrument_id,
                'long_short_ratio': str(long_short_ratio) if long_short_ratio is not None else None,
                'long_position_ratio': str(long_position_ratio) if long_position_ratio is not None else None,
                'short_position_ratio': str(short_position_ratio) if short_position_ratio is not None else None,
                'period': '5m',  # 默认周期
                'timestamp': to_ms_str(ts_val) if ts_val is not None else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'data_source': 'marketprism'
            }
            return result
        except Exception as e:
            self.logger.error(f"LSR顶级持仓数据标准化失败: {e}")
            # 返回最小安全对象
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            return {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol,
                'timestamp': now,
                'collected_at': now,
                'data_source': 'marketprism'
            }

    def normalize_lsr_all_account(self, exchange: str, market_type: str, symbol: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化LSR全账户数据（就地统一时间戳为UTC毫秒字符串）

        输入原始数据字段兼容：
        - Binance: { symbol, longShortRatio, longAccount, shortAccount, timestamp(ms) }
        - OKX: { ts(ms), longShortRatio, longRatio, shortRatio } (注意：OKX全账户API使用longRatio/shortRatio字段)
        其他来源：若提供 ISO 字符串 / datetime / epoch 秒/毫秒 亦能解析。
        """
        from datetime import datetime, timezone
        from decimal import Decimal
        try:
            # 小范围局部解析函数（不抽公共工具，遵循"就地处理"）
            def to_ms_str(ts_val) -> Optional[str]:
                if ts_val is None:
                    return None
                try:
                    if isinstance(ts_val, (int, float)):
                        # 既支持秒也支持毫秒：按 >1e12 判断
                        sec = float(ts_val) / (1000.0 if ts_val > 1e12 else 1.0)
                        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if hasattr(ts_val, 'isoformat'):
                        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if isinstance(ts_val, str):
                        try:
                            from dateutil import parser as date_parser
                            dt = date_parser.parse(ts_val)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        except Exception:
                            pass
                except Exception:
                    pass
                # 兜底当前时间
                return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # 解析不同交易所的数据格式
            if exchange.startswith('binance'):
                # Binance 格式：{ symbol, longShortRatio, longAccount, shortAccount, timestamp }
                # 或者包装格式：{ data: [{ symbol, longShortRatio, longAccount, shortAccount, timestamp }] }
                if 'data' in raw_data and isinstance(raw_data['data'], list) and len(raw_data['data']) > 0:
                    data_item = raw_data['data'][0]
                else:
                    data_item = raw_data

                # 🔧 修复：检查 data_item 是否为 dict 类型
                if isinstance(data_item, dict):
                    instrument_id = data_item.get('symbol') or symbol
                    long_short_ratio = data_item.get('longShortRatio')
                    long_account_ratio = data_item.get('longAccount')  # Binance 使用 longAccount
                    short_account_ratio = data_item.get('shortAccount')  # Binance 使用 shortAccount
                    event_time = data_item.get('timestamp')
                else:
                    # 如果不是 dict，使用默认值
                    instrument_id = symbol
                    long_short_ratio = None
                    long_account_ratio = None
                    short_account_ratio = None
                    event_time = None

            elif exchange.startswith('okx'):
                # OKX 格式：{ data: [{ ts, longShortRatio, longRatio, shortRatio }] }
                # 或者直接格式：{ ts, longShortRatio, longRatio, shortRatio }
                # 注意：OKX全账户API使用longRatio/shortRatio字段（与顶级持仓相同）
                if 'data' in raw_data and isinstance(raw_data['data'], list) and len(raw_data['data']) > 0:
                    data_item = raw_data['data'][0]
                    # 处理数组格式 [timestamp, longShortRatio, longRatio, shortRatio]
                    if isinstance(data_item, list) and len(data_item) >= 4:
                        event_time = data_item[0]
                        long_short_ratio = data_item[1]
                        long_account_ratio = data_item[2]  # OKX全账户：longRatio
                        short_account_ratio = data_item[3]  # OKX全账户：shortRatio
                    else:
                        # 对象格式
                        event_time = data_item.get('ts')
                        long_short_ratio = data_item.get('longShortRatio')
                        long_account_ratio = data_item.get('longRatio')  # OKX全账户：longRatio
                        short_account_ratio = data_item.get('shortRatio')  # OKX全账户：shortRatio
                else:
                    data_item = raw_data
                    # 🔧 修复：检查 data_item 是否为 dict 类型
                    if isinstance(data_item, dict):
                        event_time = data_item.get('ts')
                        long_short_ratio = data_item.get('longShortRatio')
                        long_account_ratio = data_item.get('longRatio')  # OKX全账户：longRatio
                        short_account_ratio = data_item.get('shortRatio')  # OKX全账户：shortRatio
                    else:
                        # 如果不是 dict，使用默认值
                        event_time = None
                        long_short_ratio = None
                        long_account_ratio = None
                        short_account_ratio = None

                instrument_id = raw_data.get('symbol') if isinstance(raw_data, dict) else symbol

            else:
                # 通用格式处理
                # 🔧 修复：检查 raw_data 是否为 dict 类型
                if isinstance(raw_data, dict):
                    instrument_id = raw_data.get('symbol') or raw_data.get('instId') or symbol
                    long_short_ratio = raw_data.get('longShortRatio')
                    long_account_ratio = raw_data.get('longRatio') or raw_data.get('longAccount')
                    short_account_ratio = raw_data.get('shortRatio') or raw_data.get('shortAccount')
                    event_time = raw_data.get('timestamp') or raw_data.get('ts')
                else:
                    # 如果不是 dict，使用默认值
                    instrument_id = symbol
                    long_short_ratio = None
                    long_account_ratio = None
                    short_account_ratio = None
                    event_time = None

            # 统一 symbol
            normalized_symbol = self.normalize_symbol_format(instrument_id, exchange)

            # 时间戳来源优先级
            ts_candidates = [event_time, raw_data.get('time') if isinstance(raw_data, dict) else None]
            ts_val = next((v for v in ts_candidates if v is not None), None)

            result = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': normalized_symbol,
                'instrument_id': instrument_id,
                'long_short_ratio': str(long_short_ratio) if long_short_ratio is not None else None,
                'long_account_ratio': str(long_account_ratio) if long_account_ratio is not None else None,
                'short_account_ratio': str(short_account_ratio) if short_account_ratio is not None else None,
                'period': '5m',  # 默认周期
                'timestamp': to_ms_str(ts_val) if ts_val is not None else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'data_source': 'marketprism'
            }
            return result
        except Exception as e:
            self.logger.error(f"LSR全账户数据标准化失败: {e}")
            # 返回最小安全对象
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            return {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol,
                'timestamp': now,
                'collected_at': now,
                'data_source': 'marketprism'
            }

    def normalize_vol_index(self, exchange: str, market_type: str, symbol: str, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化波动率指数数据（就地统一时间戳为UTC毫秒字符串）

        输入原始数据字段兼容：
        - Deribit: { currency, timestamp(ms), volatility_index, volatility_open, volatility_high, volatility_low, raw_data }
        - 或者 API 响应格式：{ result: { data: [timestamp, open, high, low, close] } }
        其他来源：若提供 ISO 字符串 / datetime / epoch 秒/毫秒 亦能解析。
        """
        from datetime import datetime, timezone
        from decimal import Decimal
        try:
            # 小范围局部解析函数（不抽公共工具，遵循"就地处理"）
            def to_ms_str(ts_val) -> Optional[str]:
                if ts_val is None:
                    return None
                try:
                    if isinstance(ts_val, (int, float)):
                        # 既支持秒也支持毫秒：按 >1e12 判断
                        sec = float(ts_val) / (1000.0 if ts_val > 1e12 else 1.0)
                        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if hasattr(ts_val, 'isoformat'):
                        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    if isinstance(ts_val, str):
                        try:
                            from dateutil import parser as date_parser
                            dt = date_parser.parse(ts_val)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        except Exception:
                            pass
                except Exception:
                    pass
                # 兜底当前时间
                return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            # 解析不同交易所的数据格式
            if exchange.startswith('deribit'):
                # Deribit 格式：{ currency, timestamp, volatility_index, volatility_open, volatility_high, volatility_low }
                # 或者 API 响应格式：{ result: { data: [timestamp, open, high, low, close] } }

                if 'result' in raw_data:
                    # API 响应格式
                    result = raw_data['result']
                    if 'data' in result and isinstance(result['data'], list) and len(result['data']) > 0:
                        # 数据点格式：[timestamp, open, high, low, close]
                        data_point = result['data'][-1]  # 取最新数据点
                        if isinstance(data_point, list) and len(data_point) >= 5:
                            event_time = data_point[0]  # 毫秒时间戳
                            volatility_open = data_point[1]
                            volatility_high = data_point[2]
                            volatility_low = data_point[3]
                            volatility_index = data_point[4]  # close 作为当前波动率指数
                        else:
                            # 单个数据点对象格式
                            event_time = data_point.get('timestamp')
                            volatility_index = data_point.get('volatility') or data_point.get('volatility_index')
                            volatility_open = data_point.get('volatility_open')
                            volatility_high = data_point.get('volatility_high')
                            volatility_low = data_point.get('volatility_low')
                    else:
                        # 直接是 result 数据
                        event_time = result.get('timestamp')
                        volatility_index = result.get('volatility') or result.get('volatility_index')
                        volatility_open = result.get('volatility_open')
                        volatility_high = result.get('volatility_high')
                        volatility_low = result.get('volatility_low')
                else:
                    # 直接格式
                    event_time = raw_data.get('timestamp')
                    volatility_index = raw_data.get('volatility_index') or raw_data.get('volatility')
                    volatility_open = raw_data.get('volatility_open')
                    volatility_high = raw_data.get('volatility_high')
                    volatility_low = raw_data.get('volatility_low')

                # 获取货币信息
                currency = raw_data.get('currency') or symbol
                instrument_id = f"{currency}-DVOL"  # Deribit 波动率指数格式

            else:
                # 通用格式处理
                event_time = raw_data.get('timestamp') or raw_data.get('ts')
                volatility_index = raw_data.get('volatility_index') or raw_data.get('volatility')
                volatility_open = raw_data.get('volatility_open')
                volatility_high = raw_data.get('volatility_high')
                volatility_low = raw_data.get('volatility_low')
                currency = raw_data.get('currency') or symbol
                instrument_id = raw_data.get('instrument_id') or symbol

            # 统一 symbol
            normalized_symbol = self.normalize_symbol_format(currency, exchange)

            # 时间戳来源优先级
            ts_candidates = [event_time, raw_data.get('time')]
            ts_val = next((v for v in ts_candidates if v is not None), None)

            result = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': normalized_symbol,
                'currency': currency,
                'instrument_id': instrument_id,
                'volatility_index': str(volatility_index) if volatility_index is not None else None,
                'volatility_open': str(volatility_open) if volatility_open is not None else None,
                'volatility_high': str(volatility_high) if volatility_high is not None else None,
                'volatility_low': str(volatility_low) if volatility_low is not None else None,
                'index_name': f"{currency}DVOL" if currency else "DVOL",
                'timestamp': to_ms_str(ts_val) if ts_val is not None else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'data_source': 'marketprism'
            }
            return result
        except Exception as e:
            self.logger.error(f"波动率指数数据标准化失败: {e}")
            # 返回最小安全对象
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            return {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': symbol,
                'timestamp': now,
                'collected_at': now,
                'data_source': 'marketprism'
            }

    def normalize_orderbook(self, exchange: str, market_type: str, symbol: str,
                           orderbook: 'EnhancedOrderBook') -> Dict[str, Any]:
        """
        标准化订单簿数据用于NATS发布

        Args:
            exchange: 交易所名称
            market_type: 市场类型
            symbol: 交易对符号
            orderbook: 增强订单簿对象

        Returns:
            标准化的订单簿数据字典
        """
        try:
            # 标准化symbol格式（传递 exchange 以处理 -SWAP 等后缀）
            normalized_symbol = self.normalize_symbol(symbol, exchange)

            # 构建标准化数据
            normalized_data = {
                'exchange': exchange,
                'market_type': market_type,
                'symbol': normalized_symbol,
                'last_update_id': orderbook.last_update_id,
                'bids': [
                    {'price': str(level.price), 'quantity': str(level.quantity)}
                    for level in orderbook.bids[:400]  # 限制为400档
                ],
                'asks': [
                    {'price': str(level.price), 'quantity': str(level.quantity)}
                    for level in orderbook.asks[:400]  # 限制为400档
                ],
                'timestamp': orderbook.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'update_type': orderbook.update_type.value if hasattr(orderbook.update_type, 'value') else str(orderbook.update_type),
                'depth_levels': min(len(orderbook.bids) + len(orderbook.asks), 800),
                'data_source': 'marketprism',
                'collected_at': orderbook.collected_at.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],

            }

            # 添加可选字段
            if hasattr(orderbook, 'first_update_id') and orderbook.first_update_id:
                normalized_data['first_update_id'] = orderbook.first_update_id

            if hasattr(orderbook, 'prev_update_id') and orderbook.prev_update_id:
                normalized_data['prev_update_id'] = orderbook.prev_update_id

            return normalized_data

        except Exception as e:
            self.logger.error("订单簿数据标准化失败",
                            exchange=exchange, symbol=symbol, error=str(e))
            raise

    def normalize_liquidation_data(self, exchange_name: str, symbol_name: str,
                                 market_type: str, liquidation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 新增：统一强平数据标准化方法
        为LiquidationManager提供统一的数据标准化接口

        Args:
            exchange_name: 交易所名称
            symbol_name: 交易对符号
            market_type: 市场类型
            liquidation_data: 强平数据字典

        Returns:
            标准化后的强平数据
        """
        try:
            # 标准化交易所名称和符号
            normalized_exchange = self.normalize_exchange_name(exchange_name)
            normalized_symbol = self.normalize_symbol_format(symbol_name)
            normalized_market_type = self.normalize_market_type(market_type)

            # 构建标准化数据
            normalized_data = {
                'exchange': normalized_exchange,
                'symbol': normalized_symbol,
                'market_type': normalized_market_type,
                'price': liquidation_data.get('price'),
                'quantity': liquidation_data.get('quantity'),
                'side': liquidation_data.get('side'),
                'timestamp': liquidation_data.get('timestamp'),
                'liquidation_id': liquidation_data.get('liquidation_id'),
                'data_source': 'marketprism'
            }

            # 添加可选字段
            optional_fields = ['average_price', 'status', 'order_type']
            for field in optional_fields:
                if field in liquidation_data and liquidation_data[field] is not None:
                    normalized_data[field] = liquidation_data[field]

            return normalized_data

        except Exception as e:
            self.logger.error("强平数据标准化失败",
                            exchange=exchange_name, symbol=symbol_name, error=str(e))
            return liquidation_data