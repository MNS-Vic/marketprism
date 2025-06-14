"""
Data Collector 数据类型 TDD 测试

测试覆盖：
- 标准化数据结构
- 数据验证
- 序列化/反序列化
- 枚举类型
- 默认值处理
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "data-collector" / "src"))

from marketprism_collector.data_types import (
    DataType, Exchange, MarketType, OrderBookUpdateType,
    PriceLevel, NormalizedTrade, NormalizedOrderBook, EnhancedOrderBook,
    NormalizedKline, NormalizedTicker, NormalizedFundingRate,
    NormalizedOpenInterest, NormalizedLiquidation, ExchangeConfig,
    CollectorMetrics, HealthStatus, NormalizedTopTraderLongShortRatio,
    NormalizedAccountCommission, NormalizedTradingDayTicker, NormalizedAvgPrice,
    NormalizedSessionInfo, EnhancedOrderBookUpdate, OrderBookDelta
)


class TestEnums:
    """枚举类型测试"""
    
    def test_data_type_enum(self):
        """测试：数据类型枚举"""
        assert DataType.TRADE == "trade"
        assert DataType.ORDERBOOK == "orderbook"
        assert DataType.KLINE == "kline"
        assert DataType.TICKER == "ticker"
        assert DataType.FUNDING_RATE == "funding_rate"
        assert DataType.OPEN_INTEREST == "open_interest"
        assert DataType.LIQUIDATION == "liquidation"
        assert DataType.TOP_TRADER_LONG_SHORT_RATIO == "top_trader_long_short_ratio"
    
    def test_exchange_enum(self):
        """测试：交易所枚举"""
        assert Exchange.BINANCE == "binance"
        assert Exchange.OKX == "okx"
        assert Exchange.DERIBIT == "deribit"
        assert Exchange.BYBIT == "bybit"
        assert Exchange.HUOBI == "huobi"
    
    def test_market_type_enum(self):
        """测试：市场类型枚举"""
        assert MarketType.SPOT == "spot"
        assert MarketType.FUTURES == "futures"
        assert MarketType.PERPETUAL == "perpetual"
        assert MarketType.OPTIONS == "options"
        assert MarketType.DERIVATIVES == "derivatives"
    
    def test_orderbook_update_type_enum(self):
        """测试：订单簿更新类型枚举"""
        assert OrderBookUpdateType.SNAPSHOT == "snapshot"
        assert OrderBookUpdateType.UPDATE == "update"
        assert OrderBookUpdateType.DELTA == "delta"
        assert OrderBookUpdateType.FULL_REFRESH == "full_refresh"


class TestPriceLevel:
    """价格档位测试"""
    
    def test_create_price_level(self):
        """测试：创建价格档位"""
        price_level = PriceLevel(
            price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )
        
        assert price_level.price == Decimal("50000.00")
        assert price_level.quantity == Decimal("0.1")
    
    def test_price_level_serialization(self):
        """测试：价格档位序列化"""
        price_level = PriceLevel(
            price=Decimal("50000.00"),
            quantity=Decimal("0.1")
        )
        
        data = price_level.model_dump()
        assert data["price"] == Decimal("50000.00")
        assert data["quantity"] == Decimal("0.1")
    
    def test_price_level_with_string_values(self):
        """测试：使用字符串值创建价格档位"""
        price_level = PriceLevel(
            price="50000.00",
            quantity="0.1"
        )
        
        assert price_level.price == Decimal("50000.00")
        assert price_level.quantity == Decimal("0.1")


class TestNormalizedTrade:
    """标准化交易数据测试"""
    
    def test_create_normalized_trade(self):
        """测试：创建标准化交易数据"""
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=datetime.now(timezone.utc),
            side="buy"
        )
        
        assert trade.exchange_name == "binance"
        assert trade.symbol_name == "BTCUSDT"
        assert trade.trade_id == "12345"
        assert trade.price == Decimal("50000.00")
        assert trade.quantity == Decimal("0.1")
        assert trade.side == "buy"
    
    def test_trade_with_binance_2023_fields(self):
        """测试：包含Binance 2023新增字段的交易数据"""
        now = datetime.now(timezone.utc)
        
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=now,
            side="buy",
            transact_time=now,
            order_id="order_123",
            commission=Decimal("0.001"),
            commission_asset="BNB",
            prevented_quantity=Decimal("0.01"),
            prevented_price=Decimal("49000.00"),
            prevented_quote_qty=Decimal("490.00")
        )
        
        assert trade.transact_time == now
        assert trade.order_id == "order_123"
        assert trade.commission == Decimal("0.001")
        assert trade.commission_asset == "BNB"
        assert trade.prevented_quantity == Decimal("0.01")
        assert trade.prevented_price == Decimal("49000.00")
        assert trade.prevented_quote_qty == Decimal("490.00")
    
    def test_trade_serialization(self):
        """测试：交易数据序列化"""
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=datetime.now(timezone.utc),
            side="buy"
        )
        
        data = trade.model_dump()
        assert isinstance(data, dict)
        assert data["exchange_name"] == "binance"
        assert data["symbol_name"] == "BTCUSDT"
        
        json_str = trade.model_dump_json()
        assert isinstance(json_str, str)
        assert "binance" in json_str
    
    def test_trade_with_raw_data(self):
        """测试：包含原始数据的交易"""
        raw_data = {
            "id": 12345,
            "price": "50000.00",
            "qty": "0.1",
            "quoteQty": "5000.00",
            "time": 1640995200000,
            "isBuyerMaker": False
        }
        
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=datetime.now(timezone.utc),
            side="buy",
            raw_data=raw_data
        )
        
        assert trade.raw_data == raw_data
        assert trade.raw_data["id"] == 12345


class TestNormalizedOrderBook:
    """标准化订单簿数据测试"""
    
    def test_create_normalized_orderbook(self):
        """测试：创建标准化订单簿数据"""
        bids = [
            PriceLevel(price=Decimal("49000"), quantity=Decimal("0.1")),
            PriceLevel(price=Decimal("48000"), quantity=Decimal("0.2"))
        ]
        asks = [
            PriceLevel(price=Decimal("51000"), quantity=Decimal("0.1")),
            PriceLevel(price=Decimal("52000"), quantity=Decimal("0.2"))
        ]
        
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_update_id=12345,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc)
        )
        
        assert orderbook.exchange_name == "binance"
        assert orderbook.symbol_name == "BTCUSDT"
        assert orderbook.last_update_id == 12345
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0].price == Decimal("49000")
        assert orderbook.asks[0].price == Decimal("51000")
    
    def test_orderbook_without_update_id(self):
        """测试：没有更新ID的订单簿"""
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            bids=[],
            asks=[],
            timestamp=datetime.now(timezone.utc)
        )
        
        assert orderbook.last_update_id is None
    
    def test_orderbook_serialization(self):
        """测试：订单簿序列化"""
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            bids=[PriceLevel(price=Decimal("49000"), quantity=Decimal("0.1"))],
            asks=[PriceLevel(price=Decimal("51000"), quantity=Decimal("0.1"))],
            timestamp=datetime.now(timezone.utc)
        )
        
        data = orderbook.model_dump()
        assert isinstance(data, dict)
        assert data["exchange_name"] == "binance"
        assert len(data["bids"]) == 1
        assert len(data["asks"]) == 1


class TestEnhancedOrderBook:
    """增强订单簿数据测试"""
    
    def test_create_enhanced_orderbook(self):
        """测试：创建增强订单簿数据"""
        bids = [PriceLevel(price=Decimal("49000"), quantity=Decimal("0.1"))]
        asks = [PriceLevel(price=Decimal("51000"), quantity=Decimal("0.1"))]
        
        enhanced_orderbook = EnhancedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_update_id=12345,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
            update_type=OrderBookUpdateType.SNAPSHOT,
            first_update_id=12340,
            depth_levels=20,
            checksum=123456,
            is_valid=True
        )
        
        assert enhanced_orderbook.update_type == OrderBookUpdateType.SNAPSHOT
        assert enhanced_orderbook.first_update_id == 12340
        assert enhanced_orderbook.depth_levels == 20
        assert enhanced_orderbook.checksum == 123456
        assert enhanced_orderbook.is_valid is True
        assert enhanced_orderbook.validation_errors == []
    
    def test_enhanced_orderbook_with_changes(self):
        """测试：包含变化的增强订单簿"""
        bid_changes = [PriceLevel(price=Decimal("49100"), quantity=Decimal("0.05"))]
        ask_changes = [PriceLevel(price=Decimal("50900"), quantity=Decimal("0.05"))]
        
        enhanced_orderbook = EnhancedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_update_id=12346,
            bids=[],
            asks=[],
            timestamp=datetime.now(timezone.utc),
            update_type=OrderBookUpdateType.UPDATE,
            bid_changes=bid_changes,
            ask_changes=ask_changes,
            removed_bids=[Decimal("49000")],
            removed_asks=[Decimal("51000")]
        )
        
        assert enhanced_orderbook.update_type == OrderBookUpdateType.UPDATE
        assert len(enhanced_orderbook.bid_changes) == 1
        assert len(enhanced_orderbook.ask_changes) == 1
        assert enhanced_orderbook.removed_bids == [Decimal("49000")]
        assert enhanced_orderbook.removed_asks == [Decimal("51000")]
    
    def test_enhanced_orderbook_defaults(self):
        """测试：增强订单簿默认值"""
        enhanced_orderbook = EnhancedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            bids=[],
            asks=[],
            timestamp=datetime.now(timezone.utc)
        )
        
        assert enhanced_orderbook.update_type == OrderBookUpdateType.UPDATE
        assert enhanced_orderbook.depth_levels == 0
        assert enhanced_orderbook.is_valid is True
        assert enhanced_orderbook.validation_errors == []
        assert enhanced_orderbook.bid_changes is None
        assert enhanced_orderbook.ask_changes is None


class TestNormalizedKline:
    """标准化K线数据测试"""
    
    def test_create_normalized_kline(self):
        """测试：创建标准化K线数据"""
        now = datetime.now(timezone.utc)
        
        kline = NormalizedKline(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            open_time=now,
            close_time=now + datetime.timedelta(minutes=1),
            interval="1m",
            open_price=Decimal("50000.00"),
            high_price=Decimal("50100.00"),
            low_price=Decimal("49900.00"),
            close_price=Decimal("50050.00"),
            volume=Decimal("10.5"),
            quote_volume=Decimal("525000.00"),
            trade_count=100,
            taker_buy_volume=Decimal("5.5"),
            taker_buy_quote_volume=Decimal("275000.00")
        )
        
        assert kline.exchange_name == "binance"
        assert kline.symbol_name == "BTCUSDT"
        assert kline.interval == "1m"
        assert kline.open_price == Decimal("50000.00")
        assert kline.high_price == Decimal("50100.00")
        assert kline.low_price == Decimal("49900.00")
        assert kline.close_price == Decimal("50050.00")
        assert kline.volume == Decimal("10.5")
        assert kline.trade_count == 100


class TestNormalizedTicker:
    """标准化行情数据测试"""
    
    def test_create_normalized_ticker(self):
        """测试：创建标准化行情数据"""
        now = datetime.now(timezone.utc)
        
        ticker = NormalizedTicker(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_price=Decimal("50000.00"),
            open_price=Decimal("49000.00"),
            high_price=Decimal("51000.00"),
            low_price=Decimal("48000.00"),
            volume=Decimal("1000.0"),
            quote_volume=Decimal("50000000.0"),
            price_change=Decimal("1000.0"),
            price_change_percent=Decimal("2.04"),
            weighted_avg_price=Decimal("49500.00"),
            last_quantity=Decimal("0.1"),
            best_bid_price=Decimal("49990.00"),
            best_bid_quantity=Decimal("0.5"),
            best_ask_price=Decimal("50010.00"),
            best_ask_quantity=Decimal("0.5"),
            open_time=now - datetime.timedelta(hours=24),
            close_time=now,
            first_trade_id=123456,
            last_trade_id=234567,
            trade_count=10000,
            timestamp=now
        )
        
        assert ticker.exchange_name == "binance"
        assert ticker.symbol_name == "BTCUSDT"
        assert ticker.last_price == Decimal("50000.00")
        assert ticker.price_change == Decimal("1000.0")
        assert ticker.price_change_percent == Decimal("2.04")
        assert ticker.trade_count == 10000


class TestNormalizedFundingRate:
    """资金费率数据测试"""
    
    def test_create_funding_rate(self):
        """测试：创建资金费率数据"""
        now = datetime.now(timezone.utc)
        
        funding_rate = NormalizedFundingRate(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            funding_rate=Decimal("0.0001"),
            estimated_rate=Decimal("0.00012"),
            next_funding_time=now + datetime.timedelta(hours=8),
            mark_price=Decimal("50000.00"),
            index_price=Decimal("49995.00"),
            premium_index=Decimal("5.00"),
            funding_interval="8h",
            timestamp=now
        )
        
        assert funding_rate.exchange_name == "binance"
        assert funding_rate.symbol_name == "BTCUSDT"
        assert funding_rate.funding_rate == Decimal("0.0001")
        assert funding_rate.estimated_rate == Decimal("0.00012")
        assert funding_rate.funding_interval == "8h"
        assert funding_rate.premium_index == Decimal("5.00")


class TestNormalizedOpenInterest:
    """持仓量数据测试"""
    
    def test_create_open_interest(self):
        """测试：创建持仓量数据"""
        now = datetime.now(timezone.utc)
        
        open_interest = NormalizedOpenInterest(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            open_interest=Decimal("1000000"),
            open_interest_value=Decimal("50000000000"),
            open_interest_value_usd=Decimal("50000000000"),
            change_24h=Decimal("50000"),
            change_24h_percent=Decimal("5.0"),
            instrument_type="futures",
            timestamp=now
        )
        
        assert open_interest.exchange_name == "binance"
        assert open_interest.symbol_name == "BTCUSDT"
        assert open_interest.open_interest == Decimal("1000000")
        assert open_interest.open_interest_value == Decimal("50000000000")
        assert open_interest.change_24h_percent == Decimal("5.0")
        assert open_interest.instrument_type == "futures"


class TestNormalizedLiquidation:
    """强平数据测试"""
    
    def test_create_liquidation(self):
        """测试：创建强平数据"""
        now = datetime.now(timezone.utc)
        
        liquidation = NormalizedLiquidation(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            liquidation_id="liq_123456",
            side="sell",
            price=Decimal("48000.00"),
            quantity=Decimal("0.5"),
            value=Decimal("24000.00"),
            leverage=Decimal("10"),
            margin_type="isolated",
            liquidation_fee=Decimal("24.00"),
            instrument_type="futures",
            user_id="user_***",
            timestamp=now
        )
        
        assert liquidation.exchange_name == "binance"
        assert liquidation.symbol_name == "BTCUSDT"
        assert liquidation.liquidation_id == "liq_123456"
        assert liquidation.side == "sell"
        assert liquidation.price == Decimal("48000.00")
        assert liquidation.quantity == Decimal("0.5")
        assert liquidation.leverage == Decimal("10")
        assert liquidation.margin_type == "isolated"


class TestExchangeConfig:
    """交易所配置测试"""
    
    def test_create_exchange_config(self):
        """测试：创建交易所配置"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            enabled=True,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443/ws",
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            symbols=["BTCUSDT", "ETHUSDT"]
        )
        
        assert config.exchange == Exchange.BINANCE
        assert config.market_type == MarketType.SPOT
        assert config.enabled is True
        assert config.base_url == "https://api.binance.com"
        assert DataType.TRADE in config.data_types
        assert "BTCUSDT" in config.symbols
    
    def test_exchange_config_defaults(self):
        """测试：交易所配置默认值"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        
        assert config.market_type == MarketType.SPOT
        assert config.enabled is True
        assert config.base_url == ""
        assert config.ws_url == ""
        assert config.data_types == [DataType.TRADE]
        assert config.symbols == ["BTCUSDT"]
        assert config.max_requests_per_minute == 1200
        assert config.ping_interval == 30
        assert config.reconnect_attempts == 5
    
    def test_exchange_config_name_property(self):
        """测试：交易所配置name属性"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        
        assert config.name == "binance"
    
    def test_exchange_config_for_binance(self):
        """测试：Binance配置工厂方法"""
        config = ExchangeConfig.for_binance(
            market_type=MarketType.FUTURES,
            api_key="test_key",
            api_secret="test_secret",
            symbols=["BTCUSDT"],
            data_types=[DataType.TRADE, DataType.TICKER]
        )
        
        assert config.exchange == Exchange.BINANCE
        assert config.market_type == MarketType.FUTURES
        assert config.api_key == "test_key"
        assert config.api_secret == "test_secret"
        assert config.symbols == ["BTCUSDT"]
        assert config.data_types == [DataType.TRADE, DataType.TICKER]
        assert "fapi" in config.base_url  # 期货API URL
    
    def test_exchange_config_for_okx(self):
        """测试：OKX配置工厂方法"""
        config = ExchangeConfig.for_okx(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_passphrase"
        )
        
        assert config.exchange == Exchange.OKX
        assert config.api_key == "test_key"
        assert config.api_secret == "test_secret"
        assert config.passphrase == "test_passphrase"
        assert "okx.com" in config.base_url
    
    def test_exchange_config_for_deribit(self):
        """测试：Deribit配置工厂方法"""
        config = ExchangeConfig.for_deribit()
        
        assert config.exchange == Exchange.DERIBIT
        assert config.market_type == MarketType.DERIVATIVES
        assert "deribit.com" in config.base_url


class TestCollectorMetrics:
    """收集器指标测试"""
    
    def test_create_collector_metrics(self):
        """测试：创建收集器指标"""
        metrics = CollectorMetrics()
        
        assert metrics.messages_received == 0
        assert metrics.messages_processed == 0
        assert metrics.messages_published == 0
        assert metrics.errors_count == 0
        assert metrics.last_message_time is None
        assert metrics.uptime_seconds == 0.0
        assert metrics.exchange_stats == {}
    
    def test_collector_metrics_with_data(self):
        """测试：包含数据的收集器指标"""
        now = datetime.now(timezone.utc)
        
        metrics = CollectorMetrics(
            messages_received=1000,
            messages_processed=990,
            messages_published=980,
            errors_count=10,
            last_message_time=now,
            uptime_seconds=3600.0,
            exchange_stats={
                "binance": {"trades": 500, "orderbooks": 300},
                "okx": {"trades": 200, "orderbooks": 100}
            }
        )
        
        assert metrics.messages_received == 1000
        assert metrics.messages_processed == 990
        assert metrics.messages_published == 980
        assert metrics.errors_count == 10
        assert metrics.last_message_time == now
        assert metrics.uptime_seconds == 3600.0
        assert "binance" in metrics.exchange_stats
        assert metrics.exchange_stats["binance"]["trades"] == 500


class TestBinance2023Features:
    """Binance 2023特性测试"""
    
    def test_normalized_account_commission(self):
        """测试：账户佣金信息(2023-12-04新增)"""
        now = datetime.now(timezone.utc)
        
        commission = NormalizedAccountCommission(
            exchange_name="binance",
            symbol="BTCUSDT",
            standard_commission={
                "maker": Decimal("0.001"),
                "taker": Decimal("0.001")
            },
            tax_commission={
                "maker": Decimal("0.0001"),
                "taker": Decimal("0.0001")
            },
            discount={
                "maker": Decimal("0.25"),
                "taker": Decimal("0.25")
            },
            maker_commission=Decimal("0.00075"),
            taker_commission=Decimal("0.00075"),
            timestamp=now
        )
        
        assert commission.exchange_name == "binance"
        assert commission.symbol == "BTCUSDT"
        assert commission.maker_commission == Decimal("0.00075")
        assert commission.taker_commission == Decimal("0.00075")
    
    def test_normalized_trading_day_ticker(self):
        """测试：交易日行情数据(2023-12-04新增)"""
        now = datetime.now(timezone.utc)
        
        ticker = NormalizedTradingDayTicker(
            exchange_name="binance",
            symbol="BTCUSDT",
            price_change=Decimal("1000.0"),
            price_change_percent=Decimal("2.0"),
            weighted_avg_price=Decimal("49500.0"),
            open_price=Decimal("49000.0"),
            high_price=Decimal("51000.0"),
            low_price=Decimal("48000.0"),
            last_price=Decimal("50000.0"),
            volume=Decimal("1000.0"),
            quote_volume=Decimal("50000000.0"),
            open_time=now - datetime.timedelta(hours=24),
            close_time=now,
            first_id=123456,
            last_id=234567,
            count=10000,
            timestamp=now
        )
        
        assert ticker.exchange_name == "binance"
        assert ticker.symbol == "BTCUSDT"
        assert ticker.price_change == Decimal("1000.0")
        assert ticker.count == 10000
    
    def test_normalized_avg_price_with_close_time(self):
        """测试：平均价格数据包含closeTime字段(2023-12-04新增)"""
        now = datetime.now(timezone.utc)
        
        avg_price = NormalizedAvgPrice(
            exchange_name="binance",
            symbol="BTCUSDT",
            price=Decimal("50000.0"),
            close_time=now,
            timestamp=now
        )
        
        assert avg_price.exchange_name == "binance"
        assert avg_price.symbol == "BTCUSDT"
        assert avg_price.price == Decimal("50000.0")
        assert avg_price.close_time == now
    
    def test_normalized_session_info(self):
        """测试：会话信息(2023-12-04 Ed25519认证)"""
        now = datetime.now(timezone.utc)
        
        session = NormalizedSessionInfo(
            exchange_name="binance",
            session_id="session_123",
            status="AUTHENTICATED",
            auth_method="Ed25519",
            permissions=["spot_trading", "margin_trading"],
            login_time=now,
            expires_at=now + datetime.timedelta(hours=24),
            timestamp=now
        )
        
        assert session.exchange_name == "binance"
        assert session.session_id == "session_123"
        assert session.status == "AUTHENTICATED"
        assert session.auth_method == "Ed25519"
        assert "spot_trading" in session.permissions


class TestTopTraderData:
    """大户持仓比数据测试"""
    
    def test_create_top_trader_long_short_ratio(self):
        """测试：创建大户多空持仓比数据"""
        now = datetime.now(timezone.utc)
        
        data = NormalizedTopTraderLongShortRatio(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            long_short_ratio=Decimal("1.5"),
            long_position_ratio=Decimal("0.6"),
            short_position_ratio=Decimal("0.4"),
            long_account_ratio=Decimal("0.55"),
            short_account_ratio=Decimal("0.45"),
            long_short_account_ratio=Decimal("1.22"),
            data_type="position",
            period="5m",
            instrument_type="futures",
            timestamp=now
        )
        
        assert data.exchange_name == "binance"
        assert data.symbol_name == "BTC-USDT"
        assert data.long_short_ratio == Decimal("1.5")
        assert data.long_position_ratio == Decimal("0.6")
        assert data.short_position_ratio == Decimal("0.4")
        assert data.data_type == "position"
        assert data.period == "5m"
    
    def test_top_trader_hash(self):
        """测试：大户数据哈希值"""
        now = datetime.now(timezone.utc)
        
        data1 = NormalizedTopTraderLongShortRatio(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            long_short_ratio=Decimal("1.5"),
            long_position_ratio=Decimal("0.6"),
            short_position_ratio=Decimal("0.4"),
            timestamp=now
        )
        
        data2 = NormalizedTopTraderLongShortRatio(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            long_short_ratio=Decimal("1.5"),
            long_position_ratio=Decimal("0.6"),
            short_position_ratio=Decimal("0.4"),
            timestamp=now
        )
        
        # 相同的数据应该有相同的哈希值
        assert hash(data1) == hash(data2)


class TestEnhancedDataTypes:
    """增强数据类型测试"""
    
    def test_enhanced_orderbook_update(self):
        """测试：增强订单簿更新"""
        now = datetime.now(timezone.utc)
        
        update = EnhancedOrderBookUpdate(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            first_update_id=12340,
            last_update_id=12345,
            prev_update_id=12339,
            bid_updates=[PriceLevel(price=Decimal("49000"), quantity=Decimal("0.1"))],
            ask_updates=[PriceLevel(price=Decimal("51000"), quantity=Decimal("0.1"))],
            total_bid_changes=1,
            total_ask_changes=1,
            checksum=123456,
            is_valid=True,
            timestamp=now
        )
        
        assert update.exchange_name == "binance"
        assert update.symbol_name == "BTCUSDT"
        assert update.first_update_id == 12340
        assert update.last_update_id == 12345
        assert update.total_bid_changes == 1
        assert update.total_ask_changes == 1
        assert update.is_valid is True
    
    def test_orderbook_delta(self):
        """测试：订单簿增量数据"""
        now = datetime.now(timezone.utc)
        
        delta = OrderBookDelta(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            update_id=12345,
            prev_update_id=12344,
            bid_updates=[PriceLevel(price=Decimal("49000"), quantity=Decimal("0.1"))],
            ask_updates=[PriceLevel(price=Decimal("51000"), quantity=Decimal("0.1"))],
            total_bid_changes=1,
            total_ask_changes=1,
            timestamp=now
        )
        
        assert delta.exchange_name == "binance"
        assert delta.symbol_name == "BTCUSDT"
        assert delta.update_id == 12345
        assert delta.prev_update_id == 12344
        assert delta.total_bid_changes == 1
        assert delta.total_ask_changes == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])