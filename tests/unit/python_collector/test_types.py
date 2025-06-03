"""
Python Collector 数据类型单元测试

测试所有Pydantic数据模型的验证、序列化和边界条件
"""

import pytest
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.types import (
    DataType, Exchange, ExchangeType, MarketType,
    PriceLevel, NormalizedTrade, NormalizedOrderBook,
    NormalizedKline, NormalizedTicker, NormalizedFundingRate,
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
        assert DataType.KLINE == "kline"
        assert DataType.TICKER == "ticker"
        assert DataType.FUNDING_RATE == "funding_rate"
        assert DataType.OPEN_INTEREST == "open_interest"
        assert DataType.LIQUIDATION == "liquidation"
        assert DataType.TOP_TRADER_LONG_SHORT_RATIO == "top_trader_long_short_ratio"
        assert DataType.MARKET_LONG_SHORT_RATIO == "market_long_short_ratio"
        
        # 测试枚举包含所有预期值
        expected_values = {
            "trade", "orderbook", "kline", "ticker", 
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
        
        # 测试JSON序列化
        json_data = price_level.model_dump()
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
        
        # 测试模型序列化
        json_data = trade.model_dump()
        assert json_data["exchange_name"] == "binance"
        assert json_data["price"] == Decimal("50000.50")
        assert json_data["timestamp"] == timestamp
        
        # 测试JSON序列化兼容性
        json_str = trade.model_dump_json()
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
            PriceLevel(price=Decimal("49999.00"), quantity=Decimal("2.0"))
        ]
        asks = [
            PriceLevel(price=Decimal("50000.50"), quantity=Decimal("1.5")),
            PriceLevel(price=Decimal("50001.00"), quantity=Decimal("2.5"))
        ]
        
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            bids=bids,
            asks=asks,
            timestamp=timestamp
        )
        
        assert orderbook.exchange_name == "binance"
        assert orderbook.symbol_name == "BTC/USDT"
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0].price == Decimal("49999.50")
        assert orderbook.asks[0].price == Decimal("50000.50")
        assert orderbook.timestamp == timestamp
        assert orderbook.last_update_id is None  # 可选字段
    
    def test_orderbook_with_update_id(self):
        """测试包含更新ID的订单簿"""
        timestamp = datetime.now(timezone.utc)
        bids = [PriceLevel(price=Decimal("49999.50"), quantity=Decimal("1.0"))]
        asks = [PriceLevel(price=Decimal("50000.50"), quantity=Decimal("1.5"))]
        
        orderbook = NormalizedOrderBook(
            exchange_name="okx",
            symbol_name="ETH/USDT",
            last_update_id=123456,
            bids=bids,
            asks=asks,
            timestamp=timestamp
        )
        
        assert orderbook.last_update_id == 123456
    
    def test_empty_orderbook(self):
        """测试空订单簿"""
        timestamp = datetime.now(timezone.utc)
        
        orderbook = NormalizedOrderBook(
            exchange_name="deribit",
            symbol_name="BTC-PERPETUAL",
            bids=[],
            asks=[],
            timestamp=timestamp
        )
        
        assert len(orderbook.bids) == 0
        assert len(orderbook.asks) == 0
    
    def test_orderbook_validation_errors(self):
        """测试订单簿验证错误"""
        timestamp = datetime.now(timezone.utc)
        
        # 测试无效的价格档位
        with pytest.raises(ValueError):
            NormalizedOrderBook(
                exchange_name="binance",
                symbol_name="BTC/USDT",
                bids=[{"invalid": "data"}],  # 无效的价格档位
                asks=[],
                timestamp=timestamp
            )


class TestNormalizedFundingRate:
    """测试标准化资金费率数据模型"""
    
    def test_valid_funding_rate(self):
        """测试有效的资金费率数据"""
        timestamp = datetime.now(timezone.utc)
        next_funding_time = datetime.now(timezone.utc)
        
        funding_rate = NormalizedFundingRate(
            exchange_name="okx",
            symbol_name="BTC-USDT",
            funding_rate=Decimal("0.0001"),
            next_funding_time=next_funding_time,
            mark_price=Decimal("50000.50"),
            index_price=Decimal("50000.25"),
            premium_index=Decimal("0.25"),
            timestamp=timestamp
        )
        
        assert funding_rate.exchange_name == "okx"
        assert funding_rate.symbol_name == "BTC-USDT"
        assert funding_rate.funding_rate == Decimal("0.0001")
        assert funding_rate.mark_price == Decimal("50000.50")
        assert funding_rate.index_price == Decimal("50000.25")
        assert funding_rate.premium_index == Decimal("0.25")
        assert funding_rate.funding_interval == "8h"  # 默认值
    
    def test_funding_rate_with_optional_fields(self):
        """测试包含可选字段的资金费率"""
        timestamp = datetime.now(timezone.utc)
        next_funding_time = datetime.now(timezone.utc)
        
        funding_rate = NormalizedFundingRate(
            exchange_name="binance",
            symbol_name="ETH-USDT",
            funding_rate=Decimal("0.0002"),
            estimated_rate=Decimal("0.00025"),
            next_funding_time=next_funding_time,
            mark_price=Decimal("3000.50"),
            index_price=Decimal("3000.25"),
            premium_index=Decimal("0.25"),
            funding_interval="4h",
            timestamp=timestamp
        )
        
        assert funding_rate.estimated_rate == Decimal("0.00025")
        assert funding_rate.funding_interval == "4h"
    
    def test_funding_rate_json_encoding(self):
        """测试资金费率JSON编码"""
        timestamp = datetime.now(timezone.utc)
        next_funding_time = datetime.now(timezone.utc)
        
        funding_rate = NormalizedFundingRate(
            exchange_name="okx",
            symbol_name="BTC-USDT",
            funding_rate=Decimal("0.0001"),
            next_funding_time=next_funding_time,
            mark_price=Decimal("50000.50"),
            index_price=Decimal("50000.25"),
            premium_index=Decimal("0.25"),
            timestamp=timestamp
        )
        
        # 测试JSON序列化
        json_str = funding_rate.model_dump_json()
        assert isinstance(json_str, str)
        
        # 验证JSON内容
        parsed_data = json.loads(json_str)
        assert parsed_data["funding_rate"] == "0.0001"
        assert parsed_data["mark_price"] == "50000.50"


class TestNormalizedOpenInterest:
    """测试标准化持仓量数据模型"""
    
    def test_valid_open_interest(self):
        """测试有效的持仓量数据"""
        timestamp = datetime.now(timezone.utc)
        
        open_interest = NormalizedOpenInterest(
            exchange_name="okx",
            symbol_name="BTC-USDT",
            open_interest=Decimal("1000000"),
            open_interest_value=Decimal("50000000000"),
            timestamp=timestamp
        )
        
        assert open_interest.exchange_name == "okx"
        assert open_interest.symbol_name == "BTC-USDT"
        assert open_interest.open_interest == Decimal("1000000")
        assert open_interest.open_interest_value == Decimal("50000000000")
        assert open_interest.instrument_type == "futures"  # 默认值
    
    def test_open_interest_with_changes(self):
        """测试包含变化数据的持仓量"""
        timestamp = datetime.now(timezone.utc)
        
        open_interest = NormalizedOpenInterest(
            exchange_name="binance",
            symbol_name="ETH-USDT",
            open_interest=Decimal("500000"),
            open_interest_value=Decimal("1500000000"),
            open_interest_value_usd=Decimal("1500000000"),
            change_24h=Decimal("50000"),
            change_24h_percent=Decimal("10.5"),
            instrument_type="perpetual",
            timestamp=timestamp
        )
        
        assert open_interest.change_24h == Decimal("50000")
        assert open_interest.change_24h_percent == Decimal("10.5")
        assert open_interest.instrument_type == "perpetual"


class TestNormalizedLiquidation:
    """测试标准化强平数据模型"""
    
    def test_valid_liquidation(self):
        """测试有效的强平数据"""
        timestamp = datetime.now(timezone.utc)
        
        liquidation = NormalizedLiquidation(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            side="sell",
            price=Decimal("49000.00"),
            quantity=Decimal("2.5"),
            timestamp=timestamp
        )
        
        assert liquidation.exchange_name == "binance"
        assert liquidation.symbol_name == "BTC-USDT"
        assert liquidation.side == "sell"
        assert liquidation.price == Decimal("49000.00")
        assert liquidation.quantity == Decimal("2.5")
        assert liquidation.instrument_type == "futures"  # 默认值
    
    def test_liquidation_with_optional_fields(self):
        """测试包含可选字段的强平数据"""
        timestamp = datetime.now(timezone.utc)
        
        liquidation = NormalizedLiquidation(
            exchange_name="okx",
            symbol_name="ETH-USDT",
            liquidation_id="LIQ123456",
            side="buy",
            price=Decimal("2900.00"),
            quantity=Decimal("5.0"),
            value=Decimal("14500.00"),
            leverage=Decimal("10"),
            margin_type="isolated",
            liquidation_fee=Decimal("14.50"),
            instrument_type="swap",
            user_id="user_anonymous",
            timestamp=timestamp
        )
        
        assert liquidation.liquidation_id == "LIQ123456"
        assert liquidation.value == Decimal("14500.00")
        assert liquidation.leverage == Decimal("10")
        assert liquidation.margin_type == "isolated"
        assert liquidation.liquidation_fee == Decimal("14.50")
        assert liquidation.instrument_type == "swap"
        assert liquidation.user_id == "user_anonymous"


class TestExchangeConfig:
    """测试交易所配置模型"""
    
    def test_valid_exchange_config(self):
        """测试有效的交易所配置"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443",
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            symbols=["BTC/USDT", "ETH/USDT"]
        )
        
        assert config.exchange == Exchange.BINANCE
        assert config.market_type == MarketType.SPOT
        assert config.enabled is True  # 默认值
        assert config.base_url == "https://api.binance.com"
        assert config.ws_url == "wss://stream.binance.com:9443"
        assert DataType.TRADE in config.data_types
        assert DataType.ORDERBOOK in config.data_types
        assert "BTC/USDT" in config.symbols
        assert config.max_requests_per_minute == 1200  # 默认值
    
    def test_exchange_config_with_api_credentials(self):
        """测试包含API凭证的交易所配置"""
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.FUTURES,
            base_url="https://www.okx.com",
            ws_url="wss://ws.okx.com:8443",
            api_key="test_api_key",
            api_secret="test_api_secret",
            passphrase="test_passphrase",
            data_types=[DataType.FUNDING_RATE],
            symbols=["BTC-USDT-SWAP"]
        )
        
        assert config.api_key == "test_api_key"
        assert config.api_secret == "test_api_secret"
        assert config.passphrase == "test_passphrase"
    
    def test_exchange_config_validation_errors(self):
        """测试交易所配置验证错误"""
        # 测试缺少必需字段
        with pytest.raises(ValueError):
            ExchangeConfig(
                market_type=MarketType.SPOT,
                base_url="https://api.binance.com",
                ws_url="wss://stream.binance.com:9443",
                data_types=[DataType.TRADE],
                symbols=["BTC/USDT"]
            )  # 缺少exchange
        
        # 测试空的数据类型列表 - 当前实现允许空列表，这是一个设计决策
        # 在实际使用中，空列表可能表示暂时禁用数据收集
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443",
            data_types=[],  # 空列表是允许的
            symbols=["BTC/USDT"]
        )
        assert config.data_types == []
        
        # 测试空的交易对列表
        config_empty_symbols = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443",
            data_types=[DataType.TRADE],
            symbols=[]  # 空列表也是允许的
        )
        assert config_empty_symbols.symbols == []


class TestCollectorMetrics:
    """测试收集器指标模型"""
    
    def test_valid_collector_metrics(self):
        """测试有效的收集器指标"""
        metrics = CollectorMetrics(
            messages_received=1000,
            messages_processed=950,
            messages_published=950,
            errors_count=5,
            uptime_seconds=3600.5
        )
        
        assert metrics.messages_received == 1000
        assert metrics.messages_processed == 950
        assert metrics.messages_published == 950
        assert metrics.errors_count == 5
        assert metrics.uptime_seconds == 3600.5
        assert metrics.last_message_time is None  # 可选字段
        assert isinstance(metrics.exchange_stats, dict)  # 默认空字典
    
    def test_collector_metrics_with_exchange_stats(self):
        """测试包含交易所统计的收集器指标"""
        exchange_stats = {
            "binance": {"trade": 500, "orderbook": 200},
            "okx": {"trade": 300, "ticker": 100}
        }
        
        metrics = CollectorMetrics(
            messages_received=1100,
            messages_processed=1100,
            messages_published=1100,
            errors_count=0,
            last_message_time=datetime.now(timezone.utc),
            uptime_seconds=7200.0,
            exchange_stats=exchange_stats
        )
        
        assert metrics.exchange_stats == exchange_stats
        assert isinstance(metrics.last_message_time, datetime)


class TestHealthStatus:
    """测试健康状态模型"""
    
    def test_valid_health_status(self):
        """测试有效的健康状态"""
        metrics = CollectorMetrics()
        exchanges_connected = {"binance": True, "okx": True, "deribit": False}
        
        health = HealthStatus(
            status="healthy",
            version="1.0.0",
            uptime_seconds=3600.0,
            nats_connected=True,
            exchanges_connected=exchanges_connected,
            metrics=metrics
        )
        
        assert health.status == "healthy"
        assert health.version == "1.0.0"
        assert health.uptime_seconds == 3600.0
        assert health.nats_connected is True
        assert health.exchanges_connected == exchanges_connected
        assert isinstance(health.metrics, CollectorMetrics)
        assert isinstance(health.timestamp, datetime)  # 自动生成
    
    def test_health_status_degraded(self):
        """测试降级状态"""
        metrics = CollectorMetrics(errors_count=10)
        exchanges_connected = {"binance": True, "okx": False}
        
        health = HealthStatus(
            status="degraded",
            version="1.0.0",
            uptime_seconds=1800.0,
            nats_connected=True,
            exchanges_connected=exchanges_connected,
            metrics=metrics
        )
        
        assert health.status == "degraded"
        assert health.exchanges_connected["okx"] is False
        assert health.metrics.errors_count == 10
    
    def test_health_status_unhealthy(self):
        """测试不健康状态"""
        metrics = CollectorMetrics(errors_count=100)
        exchanges_connected = {"binance": False, "okx": False}
        
        health = HealthStatus(
            status="unhealthy",
            version="1.0.0",
            uptime_seconds=300.0,
            nats_connected=False,
            exchanges_connected=exchanges_connected,
            metrics=metrics
        )
        
        assert health.status == "unhealthy"
        assert health.nats_connected is False
        assert all(not connected for connected in health.exchanges_connected.values())


class TestDataModelIntegration:
    """测试数据模型集成"""
    
    def test_complete_data_flow(self):
        """测试完整的数据流模型"""
        # 创建交易数据
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
        
        # 创建订单簿数据
        bids = [PriceLevel(price=Decimal("49999.50"), quantity=Decimal("1.0"))]
        asks = [PriceLevel(price=Decimal("50000.50"), quantity=Decimal("1.5"))]
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTC/USDT",
            bids=bids,
            asks=asks,
            timestamp=timestamp
        )
        
        # 创建指标
        metrics = CollectorMetrics(
            messages_received=2,
            messages_processed=2,
            messages_published=2,
            errors_count=0
        )
        
        # 创建健康状态
        health = HealthStatus(
            status="healthy",
            version="1.0.0",
            uptime_seconds=3600.0,
            nats_connected=True,
            exchanges_connected={"binance": True},
            metrics=metrics
        )
        
        # 验证所有模型都能正常工作
        assert trade.exchange_name == "binance"
        assert orderbook.exchange_name == "binance"
        assert health.status == "healthy"
        assert health.metrics.messages_received == 2
    
    def test_model_serialization_compatibility(self):
        """测试模型序列化兼容性"""
        # 创建各种数据模型
        timestamp = datetime.now(timezone.utc)
        
        models = [
            NormalizedTrade(
                exchange_name="binance",
                symbol_name="BTC/USDT",
                trade_id="12345",
                price=Decimal("50000.50"),
                quantity=Decimal("1.5"),
                quote_quantity=Decimal("75000.75"),
                timestamp=timestamp,
                side="sell"
            ),
            NormalizedFundingRate(
                exchange_name="okx",
                symbol_name="BTC-USDT",
                funding_rate=Decimal("0.0001"),
                next_funding_time=timestamp,
                mark_price=Decimal("50000.50"),
                index_price=Decimal("50000.25"),
                premium_index=Decimal("0.25"),
                timestamp=timestamp
            ),
            CollectorMetrics(
                messages_received=100,
                messages_processed=95,
                messages_published=95,
                errors_count=5
            )
        ]
        
        # 测试所有模型都能序列化
        for model in models:
            json_str = model.model_dump_json()
            assert isinstance(json_str, str)
            assert len(json_str) > 0
            
            # 测试能够解析JSON
            parsed_data = json.loads(json_str)
            assert isinstance(parsed_data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 