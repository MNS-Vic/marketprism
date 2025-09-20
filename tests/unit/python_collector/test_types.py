"""
Python Collector 数据类型单元测试

测试所有Pydantic数据模型的验证、序列化和边界条件
"""

from datetime import datetime, timezone
import pytest
import json
from decimal import Decimal
from typing import Dict, Any

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/data-collector/src'))

from marketprism_collector.data_types import (
    DataType, Exchange, ExchangeType, MarketType,
    PriceLevel, NormalizedTrade, NormalizedOrderBook,
    NormalizedTicker, NormalizedFundingRate,
    NormalizedOpenInterest, NormalizedLiquidation,
    ExchangeConfig, CollectorMetrics, HealthStatus
)


class TestEnums:
    """测试枚举类型"""
    
    def test_data_type_enum(self):
        """测试数据类型枚举"""
        # 测试所有有效值
        assert DataType.TRADE == "trade"
        assert DataType.ORDERBOOK == "orderbook"
        assert DataType.TICKER == "ticker"
        assert DataType.FUNDING_RATE == "funding_rate"
        assert DataType.OPEN_INTEREST == "open_interest"
        assert DataType.LIQUIDATION == "liquidation"
        assert DataType.TOP_TRADER_LONG_SHORT_RATIO == "top_trader_long_short_ratio"
        assert DataType.MARKET_LONG_SHORT_RATIO == "market_long_short_ratio"
        
        # 测试枚举包含所有预期值
        expected_values = {
            "trade", "orderbook", "ticker",
            "funding_rate", "open_interest", "liquidation",
            "top_trader_long_short_ratio", "market_long_short_ratio"
        }
        actual_values = {item.value for item in DataType}
        assert actual_values == expected_values
    
    def test_exchange_enum(self):
        """测试交易所枚举"""
        # 测试所有有效值
        assert Exchange.BINANCE == "binance"
        assert Exchange.OKX == "okx"
        assert Exchange.DERIBIT == "deribit"
        assert Exchange.BYBIT == "bybit"
        assert Exchange.HUOBI == "huobi"
        
        # 测试枚举包含所有预期值
        expected_values = {"binance", "okx", "deribit", "bybit", "huobi"}
        actual_values = {item.value for item in Exchange}
        assert actual_values == expected_values
    
    def test_market_type_enum(self):
        """测试市场类型枚举"""
        # 测试所有有效值
        assert MarketType.SPOT == "spot"
        assert MarketType.FUTURES == "futures"
        assert MarketType.PERPETUAL == "perpetual"
        assert MarketType.OPTIONS == "options"
        assert MarketType.DERIVATIVES == "derivatives"
        
        # 测试枚举包含所有预期值
        expected_values = {"spot", "futures", "perpetual", "options", "derivatives"}
        actual_values = {item.value for item in MarketType}
        assert actual_values == expected_values


class TestPriceLevel:
    """测试价格档位模型"""
    
    def test_valid_price_level(self):
        """测试有效的价格档位"""
        price_level = PriceLevel(
            price=Decimal("50000.50"),
            quantity=Decimal("1.5")
        )
        
        assert price_level.price == Decimal("50000.50")
        assert price_level.quantity == Decimal("1.5")
    
    def test_price_level_serialization(self):
        """测试价格档位序列化"""
        price_level = PriceLevel(
            price=Decimal("50000.50"),
            quantity=Decimal("1.5")
        )
        
        # 测试JSON序列化 - Pydantic v1保留原始Decimal类型
        json_data = price_level.dict()
        assert json_data["price"] == Decimal("50000.50")
        assert json_data["quantity"] == Decimal("1.5")
    
    def test_price_level_validation_errors(self):
        """测试价格档位验证错误"""
        # 测试缺少必需字段
        with pytest.raises(ValueError):
            PriceLevel(price=Decimal("50000"))  # 缺少quantity
        
        with pytest.raises(ValueError):
            PriceLevel(quantity=Decimal("1.5"))  # 缺少price
        
        # 测试无效类型
        with pytest.raises(ValueError):
            PriceLevel(price="invalid", quantity=Decimal("1.5"))
    
    def test_price_level_edge_cases(self):
        """测试价格档位边界情况"""
        # 测试零值
        price_level = PriceLevel(price=Decimal("0"), quantity=Decimal("0"))
        assert price_level.price == Decimal("0")
        assert price_level.quantity == Decimal("0")
        
        # 测试极大值
        price_level = PriceLevel(
            price=Decimal("999999999.99999999"),
            quantity=Decimal("999999999.99999999")
        )
        assert price_level.price == Decimal("999999999.99999999")
        assert price_level.quantity == Decimal("999999999.99999999")


class TestNormalizedTrade:
    """测试标准化交易数据模型"""
    
    def test_valid_trade(self):
        """测试有效的交易数据"""
        timestamp = datetime.now(timezone.utc)
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            trade_id="12345",
            price=Decimal("50000.50"),
            quantity=Decimal("1.5"),
            quote_quantity=Decimal("75000.75"),
            timestamp=timestamp,
            side="sell"
        )
        
        assert trade.exchange_name == "binance"
        assert trade.symbol_name == "BTC/USDT"
        assert trade.trade_id == "12345"
        assert trade.price == Decimal("50000.50")
        assert trade.quantity == Decimal("1.5")
        assert trade.quote_quantity == Decimal("75000.75")
        assert trade.timestamp == timestamp
        assert trade.side == "sell"
        assert trade.is_best_match is None  # 可选字段
        assert trade.raw_data is None  # 可选字段
        assert isinstance(trade.collected_at, datetime)  # 自动生成
    
    def test_trade_with_optional_fields(self):
        """测试包含可选字段的交易数据"""
        timestamp = datetime.now(timezone.utc)
        raw_data = {"original": "data"}
        
        trade = NormalizedTrade(
            exchange_name="okx",
            symbol_name="ETH/USDT",
            trade_id="67890",
            price=Decimal("3000.25"),
            quantity=Decimal("2.0"),
            quote_quantity=Decimal("6000.50"),
            timestamp=timestamp,
            side="buy",
            is_best_match=True,
            raw_data=raw_data
        )
        
        assert trade.side == "buy"
        assert trade.is_best_match is True
        assert trade.raw_data == raw_data
    
    def test_trade_validation_errors(self):
        """测试交易数据验证错误"""
        timestamp = datetime.now(timezone.utc)
        
        # 测试缺少必需字段
        with pytest.raises(ValueError):
            NormalizedTrade(
                symbol_name="BTC/USDT",
                trade_id="12345",
                price=Decimal("50000.50"),
                quantity=Decimal("1.5"),
                quote_quantity=Decimal("75000.75"),
                timestamp=timestamp,
                side="sell"
            )  # 缺少exchange_name
        
        # 测试无效类型
        with pytest.raises(ValueError):
            NormalizedTrade(
                exchange_name="binance",
                symbol_name="BTC/USDT",
                trade_id="12345",
                price="invalid_price",  # 无效类型
                quantity=Decimal("1.5"),
                quote_quantity=Decimal("75000.75"),
                timestamp=timestamp,
                side="sell"
            )
    
    def test_trade_serialization(self):
        """测试交易数据序列化"""
        timestamp = datetime.now(timezone.utc)
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            trade_id="12345",
            price=Decimal("50000.50"),
            quantity=Decimal("1.5"),
            quote_quantity=Decimal("75000.75"),
            timestamp=timestamp,
            side="sell"
        )
        
        # 测试模型序列化 - Pydantic v1保留原始datetime对象
        json_data = trade.dict()
        assert json_data["exchange_name"] == "binance"
        assert json_data["price"] == Decimal("50000.50")
        assert json_data["timestamp"] == timestamp  # v1保留datetime对象
        
        # 测试JSON序列化兼容性
        json_str = trade.json()
        assert isinstance(json_str, str)
        
        # 测试反序列化
        parsed_data = json.loads(json_str)
        assert parsed_data["exchange_name"] == "binance"


class TestNormalizedOrderBook:
    """测试标准化订单簿数据模型"""
    
    def test_valid_orderbook(self):
        """测试有效的订单簿数据"""
        timestamp = datetime.now(timezone.utc)
        bids = [
            PriceLevel(price=Decimal("49999.50"), quantity=Decimal("1.0")),
            PriceLevel(price=Decimal("49999.00"), quantity=Decimal("2.5"))
        ]
        asks = [
            PriceLevel(price=Decimal("50000.50"), quantity=Decimal("1.5")),
            PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.8"))
        ]
        
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            timestamp=timestamp,
            bids=bids,
            asks=asks
        )
        
        assert orderbook.exchange_name == "binance"
        assert orderbook.symbol_name == "BTC/USDT"
        assert orderbook.timestamp == timestamp
        assert len(orderbook.bids) == 2
        assert orderbook.bids[0].price == Decimal("49999.50")
        assert len(orderbook.asks) == 2
        assert orderbook.asks[0].price == Decimal("50000.50")
    
    def test_orderbook_serialization(self):
        """测试订单簿序列化"""
        timestamp = datetime.now(timezone.utc)
        orderbook = NormalizedOrderBook(
            exchange_name="okx",
            symbol_name="ETH/USDT",
            bids=[PriceLevel(price=Decimal("49999.00"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.5"))],
            timestamp=timestamp
        )
        
        json_data = orderbook.dict()
        assert len(json_data["bids"]) == 1
        assert json_data["bids"][0]["price"] == Decimal("49999.00")
    
    def test_orderbook_with_update_id(self):
        """测试包含更新ID的订单簿"""
        timestamp = datetime.now(timezone.utc)
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            last_update_id=123456,
            bids=[PriceLevel(price=Decimal("49999.00"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.5"))],
            timestamp=timestamp
        )
        
        json_data = orderbook.dict()
        assert "last_update_id" in json_data
        assert json_data["last_update_id"] == 123456
    
    def test_empty_orderbook(self):
        """测试空的订单簿"""
        timestamp = datetime.now(timezone.utc)
        
        orderbook = NormalizedOrderBook(
            exchange_name="deribit",
            symbol_name="BTC-PERPETUAL",
            bids=[],
            asks=[],
            timestamp=timestamp
        )
        
        json_data = orderbook.dict()
        assert json_data["bids"] == []
        assert json_data["asks"] == []
        assert isinstance(json_data["timestamp"], datetime)
    
    def test_orderbook_validation_errors(self):
        """测试订单簿数据验证错误"""
        timestamp = datetime.now(timezone.utc)
        
        # 测试缺少必需字段
        with pytest.raises(ValueError):
            NormalizedOrderBook(
                symbol_name="BTC/USDT",
                timestamp=timestamp,
                bids=[],
                asks=[]
            )  # 缺少exchange_name
        
        # 测试无效类型
        with pytest.raises(ValueError):
            NormalizedOrderBook(
                exchange_name="binance",
                symbol_name="BTC/USDT",
                timestamp=timestamp,
                bids=["invalid_bid"],  # 无效类型
                asks=[]
            )


class TestNormalizedFundingRate:
    """测试资金费率数据模型"""

    def test_valid_funding_rate(self):
        """测试有效的资金费率"""
        timestamp = datetime.now(timezone.utc)
        next_funding_time = datetime.now(timezone.utc)
        
        funding_rate = NormalizedFundingRate(
            exchange_name="binance",
            symbol_name="BTC-USDT-PERP",
            funding_rate=Decimal("0.0001"),
            next_funding_time=next_funding_time,
            mark_price=Decimal("50000.50"),
            index_price=Decimal("50000.25"),
            premium_index=Decimal("0.25"),
            timestamp=timestamp
        )
        
        assert funding_rate.funding_rate == Decimal("0.0001")
        assert funding_rate.mark_price == Decimal("50000.50")

    def test_funding_rate_with_optional_fields(self):
        """测试包含可选字段的资金费率"""
        timestamp = datetime.now(timezone.utc)
        next_funding_time = datetime.now(timezone.utc)

        funding_rate = NormalizedFundingRate(
            exchange_name="okx",
            symbol_name="ETH-USDT-SWAP",
            funding_rate=Decimal("-0.0005"),
            estimated_rate=Decimal("-0.00045"),
            next_funding_time=next_funding_time,
            mark_price=Decimal("3000.00"),
            index_price=Decimal("3000.10"),
            premium_index=Decimal("-0.10"),
            funding_interval="8h",
            timestamp=timestamp
        )
        
        assert funding_rate.estimated_rate == Decimal("-0.00045")
        assert funding_rate.funding_interval == "8h"

    def test_funding_rate_json_encoding(self):
        """测试资金费率的JSON编码"""
        timestamp = datetime.now(timezone.utc)
        next_funding_time = datetime.now(timezone.utc)
        
        funding_rate = NormalizedFundingRate(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            funding_rate=Decimal("0.0001"),
            next_funding_time=next_funding_time,
            mark_price=Decimal("50000.50"),
            index_price=Decimal("50000.00"),
            premium_index=Decimal("5.00"),
            timestamp=timestamp
        )
        
        json_str = funding_rate.json()
        assert isinstance(json_str, str)
        
        parsed_data = json.loads(json_str)
        assert parsed_data["funding_rate"] == "0.0001"
        assert "next_funding_time" in parsed_data

    def test_funding_rate_validation_errors(self):
        """测试资金费率验证错误"""
        timestamp = datetime.now(timezone.utc)
        next_funding_time = datetime.now(timezone.utc)
        
        # 测试缺少必需字段
        with pytest.raises(ValueError):
            NormalizedFundingRate(
                symbol_name="BTC-USDT",
                funding_rate=Decimal("0.0001"),
                next_funding_time=next_funding_time,
                mark_price=Decimal("50000.50"),
                index_price=Decimal("50000.25"),
                premium_index=Decimal("0.25"),
                timestamp=timestamp
            )  # 缺少exchange_name
        
        # 测试无效类型
        with pytest.raises(ValueError):
            NormalizedFundingRate(
                exchange_name="okx",
                symbol_name="BTC-USDT",
                funding_rate="invalid_funding_rate",  # 无效类型
                next_funding_time=next_funding_time,
                mark_price=Decimal("50000.50"),
                index_price=Decimal("50000.25"),
                premium_index=Decimal("0.25"),
                timestamp=timestamp
            )


class TestNormalizedOpenInterest:
    """测试持仓量数据模型"""

    def test_valid_open_interest(self):
        """测试有效的持仓量"""
        timestamp = datetime.now(timezone.utc)
        
        open_interest = NormalizedOpenInterest(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            open_interest=Decimal("10000"),
            open_interest_value=Decimal("500000000"),
            timestamp=timestamp
        )
        
        json_data = open_interest.dict()
        assert json_data["open_interest"] == Decimal("10000")
        assert json_data["open_interest_value"] == Decimal("500000000")
    
    def test_open_interest_with_changes(self):
        """测试包含变化量的持仓量"""
        timestamp = datetime.now(timezone.utc)
        open_interest = NormalizedOpenInterest(
            exchange_name="okx",
            symbol_name="BTC-USDT",
            open_interest=Decimal("1000000"),
            open_interest_value=Decimal("50000000000"),
            change_24h=Decimal("50000"),
            change_24h_percent=Decimal("10.5"),
            instrument_type="perpetual",
            timestamp=timestamp
        )
        
        json_data = open_interest.dict()
        assert json_data["change_24h"] == Decimal("50000")  # v1保留Decimal类型
        assert json_data["change_24h_percent"] == Decimal("10.5")  # v1保留Decimal类型
    
    def test_open_interest_validation_errors(self):
        """测试持仓量验证错误"""
        timestamp = datetime.now(timezone.utc)

        # 测试缺少必需字段
        with pytest.raises(ValueError):
            NormalizedOpenInterest(
                symbol_name="BTC-USDT",
                open_interest=Decimal("10000"),
                open_interest_value=Decimal("500000000"),
                timestamp=timestamp
            ) # 缺少 exchange_name

        # 测试无效类型
        with pytest.raises(ValueError):
            NormalizedOpenInterest(
                exchange_name="binance",
                symbol_name="BTC-USDT",
                open_interest="invalid_oi", # 无效类型
                open_interest_value=Decimal("500000000"),
                timestamp=timestamp
            )


class TestNormalizedLiquidation:
    """测试强平数据模型"""

    def test_valid_liquidation(self):
        """测试有效的强平数据"""
        timestamp = datetime.now(timezone.utc)
        
        liquidation = NormalizedLiquidation(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            side="sell",
            price=Decimal("45000.00"),
            quantity=Decimal("10.0"),
            timestamp=timestamp
        )
        
        json_data = liquidation.dict()
        assert json_data["side"] == "sell"
        assert json_data["price"] == Decimal("45000.00")
    
    def test_liquidation_with_optional_fields(self):
        """测试包含可选字段的强平数据"""
        timestamp = datetime.now(timezone.utc)
        liquidation = NormalizedLiquidation(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            liquidation_id="LIQ98765",
            side="buy",
            price=Decimal("45000.00"),
            quantity=Decimal("10.0"),
            value=Decimal("450000.00"),
            leverage=Decimal("100"),
            margin_type="isolated",
            liquidation_fee=Decimal("450.00"),
            instrument_type="perpetual",
            user_id="anon123",
            timestamp=timestamp
        )
        
        json_data = liquidation.dict()
        assert json_data["value"] == Decimal("450000.00")
        assert json_data["leverage"] == Decimal("100")
        assert json_data["margin_type"] == "isolated"
    
    def test_liquidation_validation_errors(self):
        """测试强平数据验证错误"""
        timestamp = datetime.now(timezone.utc)

        # 测试缺少必需字段
        with pytest.raises(ValueError):
            NormalizedLiquidation(
                exchange_name="binance",
                symbol_name="BTC-USDT",
                price=Decimal("45000.00"),
                quantity=Decimal("10.0"),
                timestamp=timestamp
            ) # 缺少 side

        # 测试无效类型
        with pytest.raises(ValueError):
            NormalizedLiquidation(
                exchange_name="binance",
                symbol_name="BTC-USDT",
                side="sell",
                price="invalid_price", # 无效类型
                quantity=Decimal("10.0"),
                timestamp=timestamp
            )


class TestExchangeConfig:
    """测试交易所配置模型"""
    
    def test_valid_exchange_config(self):
        """测试有效的交易所配置"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.FUTURES,
            enabled=True,
            base_url="https://fapi.binance.com",
            ws_url="wss://fstream.binance.com/ws",
            symbols=["BTCUSDT", "ETHUSDT"],
            data_types=[DataType.TRADE, DataType.ORDERBOOK]
        )
        assert config.exchange == Exchange.BINANCE
        assert config.max_requests_per_minute == 1200  # 检查默认值

    def test_exchange_config_with_api_credentials(self):
        """测试包含API凭证的交易所配置"""
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_passphrase"
        )
        assert config.api_key == "test_key"
        assert config.passphrase == "test_passphrase"
        
    def test_exchange_config_validation_errors(self):
        """测试交易所配置验证错误"""
        
        # 测试无效的枚举值
        with pytest.raises(ValueError):
            ExchangeConfig(exchange="invalid_exchange")
            
        # 测试字段类型错误
        with pytest.raises(ValueError):
            ExchangeConfig(exchange=Exchange.BINANCE, enabled="not_a_bool")
            
        # 测试便利构造函数
        binance_config = ExchangeConfig.for_binance(
            market_type=MarketType.SPOT, 
            symbols=["BTCUSDT"]
        )
        assert binance_config.exchange == Exchange.BINANCE
        assert "api.binance.com" in binance_config.base_url
        
        okx_config = ExchangeConfig.for_okx()
        assert okx_config.exchange == Exchange.OKX
        assert "okx.com" in okx_config.base_url
        
        deribit_config = ExchangeConfig.for_deribit()
        assert deribit_config.exchange == Exchange.DERIBIT
        assert "deribit.com" in deribit_config.base_url
        assert deribit_config.market_type == MarketType.DERIVATIVES


class TestCollectorMetrics:
    """测试收集器指标模型"""

    def test_valid_collector_metrics(self):
        """测试有效的收集器指标"""
        metrics = CollectorMetrics(
            messages_received=100,
            messages_processed=98,
            messages_published=95,
            errors_count=2
        )
        assert metrics.messages_received == 100
        assert metrics.errors_count == 2
        assert metrics.uptime_seconds == 0.0 # 默认值
        
    def test_collector_metrics_with_exchange_stats(self):
        """测试包含交易所统计的指标"""
        stats = {
            "binance": {"trades": 50, "errors": 1},
            "okx": {"trades": 45, "errors": 0}
        }
        metrics = CollectorMetrics(
            messages_received=100,
            messages_processed=95,
            messages_published=95,
            errors_count=1,
            exchange_stats=stats
        )
        assert metrics.exchange_stats["binance"]["trades"] == 50


class TestHealthStatus:
    """测试健康状态模型"""

    def test_valid_health_status(self):
        """测试有效的健康状态"""
        metrics = CollectorMetrics(messages_received=10)
        health = HealthStatus(
            status="healthy",
            version="1.0.0",
            uptime_seconds=3600.5,
            nats_connected=True,
            exchanges_connected={"binance": True, "okx": False},
            metrics=metrics
        )
        assert health.status == "healthy"
        assert health.exchanges_connected["okx"] is False
        assert health.metrics.messages_received == 10

    def test_health_status_degraded(self):
        """测试降级的健康状态"""
        metrics = CollectorMetrics()
        health = HealthStatus(
            status="degraded",
            version="1.0.1",
            uptime_seconds=7200,
            nats_connected=False, # NATS断开
            exchanges_connected={"binance": True, "okx": True},
            metrics=metrics
        )
        assert health.status == "degraded"
        assert health.nats_connected is False

    def test_health_status_unhealthy(self):
        """测试不健康的健康状态"""
        metrics = CollectorMetrics()
        health = HealthStatus(
            status="unhealthy",
            version="1.0.2",
            uptime_seconds=100,
            nats_connected=False,
            exchanges_connected={"binance": False, "okx": False}, # 所有交易所断开
            metrics=metrics
        )
        assert health.status == "unhealthy"


class TestDataModelIntegration:
    """测试数据模型的集成和兼容性"""

    def test_complete_data_flow(self):
        """测试一个完整的数据流场景"""
        # 1. 创建一个交易
        timestamp = datetime.now(timezone.utc)
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            trade_id="t1",
            price=Decimal("51000"),
            quantity=Decimal("1"),
            quote_quantity=Decimal("51000"),
            timestamp=timestamp,
            side="buy"
        )
        
        # 2. 创建一个订单簿
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            bids=[PriceLevel(price=Decimal("50999"), quantity=Decimal("2"))],
            asks=[PriceLevel(price=Decimal("51001"), quantity=Decimal("3"))],
            timestamp=timestamp
        )
        
        # 3. 创建健康状态报告
        metrics = CollectorMetrics(messages_received=1, messages_processed=1)
        health = HealthStatus(
            status="healthy",
            version="1.0",
            uptime_seconds=10.0,
            nats_connected=True,
            exchanges_connected={"binance": True},
            metrics=metrics
        )
        
        # 序列化和反序列化
        trade_json = trade.json()
        orderbook_json = orderbook.json()
        health_json = health.json()
        
        # 修复JSON格式断言（JSON可能没有空格）
        assert '"price":"51000"' in trade_json or '"price": "51000"' in trade_json
        assert '"price":"50999"' in orderbook_json or '"price": "50999"' in orderbook_json
        assert '"status":"healthy"' in health_json or '"status": "healthy"' in health_json
        
        rehydrated_trade = NormalizedTrade.parse_raw(trade_json)
        assert rehydrated_trade.price == Decimal("51000")

    def test_model_serialization_compatibility(self):
        """测试模型序列化兼容性"""
        
        # 创建一个交易模型
        timestamp = datetime.now(timezone.utc)
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            trade_id="t2",
            price=Decimal("50000.50"),
            quantity=Decimal("1.5"),
            quote_quantity=Decimal("75000.75"),
            timestamp=timestamp,
            side="sell"
        )
        
        # 验证其字典输出可以用于创建其他模型
        trade_dict = trade.dict()
        
        # 创建一个部分匹配的字典
        partial_data = {
            "exchange_name": trade_dict["exchange_name"],
            "symbol_name": trade_dict["symbol_name"],
            "last_price": trade_dict["price"],
            "open_price": "50000.00",
            "high_price": "51000.00",
            "low_price": "49000.00",
            "volume": "1000",
            "quote_volume": "50000000",
            "price_change": "50.50",
            "price_change_percent": "0.1",
            "weighted_avg_price": "50100.00",
            "last_quantity": trade_dict["quantity"],
            "best_bid_price": "50000.49",
            "best_bid_quantity": "10",
            "best_ask_price": "50000.51",
            "best_ask_quantity": "12",
            "open_time": timestamp.isoformat().replace('+00:00', 'Z'),
            "close_time": timestamp.isoformat().replace('+00:00', 'Z'),
            "trade_count": 500,
            "timestamp": trade_dict["timestamp"],
        }
        
        # 可以成功创建 Ticker 模型
        ticker = NormalizedTicker.parse_obj(partial_data)
        assert ticker.symbol_name == "BTC/USDT"
        assert ticker.last_price == Decimal("50000.50")