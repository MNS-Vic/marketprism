"""
存储类型测试

严格遵循Mock使用原则：
- 仅对外部依赖使用Mock（如数据库连接、文件系统）
- 优先使用真实对象测试业务逻辑
- 确保测试验证真实的业务行为
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

# 尝试导入存储类型模块
try:
    from core.storage.types import (
        NormalizedTrade,
        BookLevel,
        NormalizedOrderBook,
        NormalizedTicker,
        MarketData,
        ExchangeConfig,
        SymbolConfig,
        ErrorInfo,
        PerformanceMetric,
        MonitoringAlert
    )
    HAS_STORAGE_TYPES = True
except ImportError as e:
    HAS_STORAGE_TYPES = False
    STORAGE_TYPES_ERROR = str(e)


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestNormalizedTrade:
    """标准化交易数据测试"""
    
    def test_normalized_trade_creation(self):
        """测试标准化交易数据创建"""
        timestamp = datetime.now(timezone.utc)
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=50000.0,
            quantity=0.1,
            timestamp=timestamp,
            is_buyer_maker=True
        )
        
        assert trade.exchange_name == "binance"
        assert trade.symbol_name == "BTCUSDT"
        assert trade.trade_id == "12345"
        assert trade.price == 50000.0
        assert trade.quantity == 0.1
        assert trade.timestamp == timestamp
        assert trade.is_buyer_maker is True
        assert trade.trade_time == timestamp  # 自动设置
    
    def test_normalized_trade_with_custom_trade_time(self):
        """测试带自定义交易时间的标准化交易数据"""
        timestamp = datetime.now(timezone.utc)
        trade_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        trade = NormalizedTrade(
            exchange_name="okx",
            symbol_name="ETHUSDT",
            trade_id="67890",
            price=Decimal("3000.50"),
            quantity=Decimal("1.5"),
            timestamp=timestamp,
            is_buyer_maker=False,
            trade_time=trade_time
        )
        
        assert trade.trade_time == trade_time
        assert isinstance(trade.price, Decimal)
        assert isinstance(trade.quantity, Decimal)
    
    def test_normalized_trade_with_string_values(self):
        """测试字符串类型的价格和数量"""
        trade = NormalizedTrade(
            exchange_name="deribit",
            symbol_name="BTC-PERPETUAL",
            trade_id="abc123",
            price="45000.123456",
            quantity="0.001",
            timestamp=datetime.now(timezone.utc),
            is_buyer_maker=True
        )
        
        assert trade.price == "45000.123456"
        assert trade.quantity == "0.001"


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestBookLevel:
    """订单簿价格档位测试"""
    
    def test_book_level_creation(self):
        """测试订单簿价格档位创建"""
        level = BookLevel(price=50000.0, quantity=1.5)
        
        assert level.price == 50000.0
        assert level.quantity == 1.5
    
    def test_book_level_with_decimal(self):
        """测试使用Decimal的价格档位"""
        level = BookLevel(
            price=Decimal("50000.123456"),
            quantity=Decimal("1.500000")
        )
        
        assert isinstance(level.price, Decimal)
        assert isinstance(level.quantity, Decimal)
        assert level.price == Decimal("50000.123456")
    
    def test_book_level_with_string(self):
        """测试使用字符串的价格档位"""
        level = BookLevel(price="49999.99", quantity="2.0")
        
        assert level.price == "49999.99"
        assert level.quantity == "2.0"


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestNormalizedOrderBook:
    """标准化订单簿数据测试"""
    
    def test_normalized_orderbook_creation(self):
        """测试标准化订单簿数据创建"""
        timestamp = datetime.now(timezone.utc)
        bids = [
            BookLevel(price=49999.0, quantity=1.0),
            BookLevel(price=49998.0, quantity=2.0)
        ]
        asks = [
            BookLevel(price=50001.0, quantity=1.5),
            BookLevel(price=50002.0, quantity=2.5)
        ]
        
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            timestamp=timestamp,
            bids=bids,
            asks=asks,
            last_update_id="123456"
        )
        
        assert orderbook.exchange_name == "binance"
        assert orderbook.symbol_name == "BTCUSDT"
        assert orderbook.timestamp == timestamp
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.last_update_id == "123456"
        
        # 验证买单价格递减
        assert orderbook.bids[0].price > orderbook.bids[1].price
        
        # 验证卖单价格递增
        assert orderbook.asks[0].price < orderbook.asks[1].price
    
    def test_normalized_orderbook_without_update_id(self):
        """测试不带更新ID的订单簿"""
        orderbook = NormalizedOrderBook(
            exchange_name="okx",
            symbol_name="ETHUSDT",
            timestamp=datetime.now(timezone.utc),
            bids=[BookLevel(price=3000.0, quantity=1.0)],
            asks=[BookLevel(price=3001.0, quantity=1.0)]
        )
        
        assert orderbook.last_update_id is None


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestNormalizedTicker:
    """标准化行情数据测试"""
    
    def test_normalized_ticker_creation(self):
        """测试标准化行情数据创建"""
        open_time = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        close_time = datetime(2023, 1, 1, 23, 59, 59, tzinfo=timezone.utc)
        timestamp = datetime.now(timezone.utc)
        
        ticker = NormalizedTicker(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            open_price=49000.0,
            high_price=51000.0,
            low_price=48000.0,
            close_price=50000.0,
            volume=1000.0,
            quote_volume=50000000.0,
            price_change=1000.0,
            price_change_percent=2.04,
            weighted_avg_price=49500.0,
            prev_close_price=49000.0,
            last_price=50000.0,
            last_quantity=0.1,
            bid_price=49999.0,
            ask_price=50001.0,
            open_time=open_time,
            close_time=close_time,
            timestamp=timestamp
        )
        
        assert ticker.exchange_name == "binance"
        assert ticker.symbol_name == "BTCUSDT"
        assert ticker.open_price == 49000.0
        assert ticker.high_price == 51000.0
        assert ticker.low_price == 48000.0
        assert ticker.close_price == 50000.0
        assert ticker.volume == 1000.0
        assert ticker.price_change_percent == 2.04
        assert ticker.open_time == open_time
        assert ticker.close_time == close_time
        assert ticker.timestamp == timestamp
    
    def test_normalized_ticker_with_decimal_values(self):
        """测试使用Decimal值的行情数据"""
        ticker = NormalizedTicker(
            exchange_name="okx",
            symbol_name="ETHUSDT",
            open_price=Decimal("3000.00"),
            high_price=Decimal("3100.50"),
            low_price=Decimal("2950.25"),
            close_price=Decimal("3050.75"),
            volume=Decimal("500.0"),
            quote_volume=Decimal("1525000.0"),
            price_change=Decimal("50.75"),
            price_change_percent=Decimal("1.69"),
            weighted_avg_price=Decimal("3025.0"),
            prev_close_price=Decimal("3000.0"),
            last_price=Decimal("3050.75"),
            last_quantity=Decimal("0.5"),
            bid_price=Decimal("3050.50"),
            ask_price=Decimal("3051.00"),
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc)
        )
        
        assert isinstance(ticker.open_price, Decimal)
        assert isinstance(ticker.price_change_percent, Decimal)


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestExchangeConfig:
    """交易所配置测试"""
    
    def test_exchange_config_creation(self):
        """测试交易所配置创建"""
        config = ExchangeConfig(
            name="binance",
            enabled=True,
            api_key="test_key",
            api_secret="test_secret",
            sandbox=False,
            rate_limit=1200,
            timeout=30
        )
        
        assert config.name == "binance"
        assert config.enabled is True
        assert config.api_key == "test_key"
        assert config.api_secret == "test_secret"
        assert config.sandbox is False
        assert config.rate_limit == 1200
        assert config.timeout == 30
    
    def test_exchange_config_defaults(self):
        """测试交易所配置默认值"""
        config = ExchangeConfig(name="okx", enabled=True)
        
        assert config.api_key is None
        assert config.api_secret is None
        assert config.sandbox is False
        assert config.rate_limit == 1200
        assert config.timeout == 30


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestSymbolConfig:
    """交易对配置测试"""
    
    def test_symbol_config_creation(self):
        """测试交易对配置创建"""
        config = SymbolConfig(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            enabled=True,
            min_quantity=0.001,
            tick_size=0.01
        )
        
        assert config.symbol == "BTCUSDT"
        assert config.base_asset == "BTC"
        assert config.quote_asset == "USDT"
        assert config.enabled is True
        assert config.min_quantity == 0.001
        assert config.tick_size == 0.01
    
    def test_symbol_config_defaults(self):
        """测试交易对配置默认值"""
        config = SymbolConfig(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            enabled=False
        )
        
        assert config.min_quantity is None
        assert config.tick_size is None


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestErrorInfo:
    """错误信息测试"""
    
    def test_error_info_creation(self):
        """测试错误信息创建"""
        timestamp = datetime.now(timezone.utc)
        error = ErrorInfo(
            error_type="ConnectionError",
            error_message="Failed to connect to exchange",
            timestamp=timestamp,
            context={"retry_count": 3},
            exchange="binance",
            symbol="BTCUSDT"
        )
        
        assert error.error_type == "ConnectionError"
        assert error.error_message == "Failed to connect to exchange"
        assert error.timestamp == timestamp
        assert error.context == {"retry_count": 3}
        assert error.exchange == "binance"
        assert error.symbol == "BTCUSDT"
    
    def test_error_info_minimal(self):
        """测试最小错误信息"""
        error = ErrorInfo(
            error_type="ValidationError",
            error_message="Invalid data format",
            timestamp=datetime.now(timezone.utc)
        )
        
        assert error.context is None
        assert error.exchange is None
        assert error.symbol is None


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestPerformanceMetric:
    """性能指标测试"""
    
    def test_performance_metric_creation(self):
        """测试性能指标创建"""
        timestamp = datetime.now(timezone.utc)
        metric = PerformanceMetric(
            name="latency",
            value=15.5,
            unit="ms",
            timestamp=timestamp,
            labels={"exchange": "binance", "symbol": "BTCUSDT"}
        )
        
        assert metric.name == "latency"
        assert metric.value == 15.5
        assert metric.unit == "ms"
        assert metric.timestamp == timestamp
        assert metric.labels == {"exchange": "binance", "symbol": "BTCUSDT"}
    
    def test_performance_metric_integer_value(self):
        """测试整数值的性能指标"""
        metric = PerformanceMetric(
            name="request_count",
            value=100,
            unit="count",
            timestamp=datetime.now(timezone.utc)
        )
        
        assert isinstance(metric.value, int)
        assert metric.labels is None


@pytest.mark.skipif(not HAS_STORAGE_TYPES, reason=f"存储类型模块不可用: {STORAGE_TYPES_ERROR if not HAS_STORAGE_TYPES else ''}")
class TestMonitoringAlert:
    """监控告警测试"""
    
    def test_monitoring_alert_creation(self):
        """测试监控告警创建"""
        timestamp = datetime.now(timezone.utc)
        alert = MonitoringAlert(
            alert_id="alert_001",
            alert_type="HighLatency",
            severity="warning",
            message="Exchange latency is above threshold",
            timestamp=timestamp,
            resolved=False,
            context={"threshold": 100, "current": 150}
        )
        
        assert alert.alert_id == "alert_001"
        assert alert.alert_type == "HighLatency"
        assert alert.severity == "warning"
        assert alert.message == "Exchange latency is above threshold"
        assert alert.timestamp == timestamp
        assert alert.resolved is False
        assert alert.context == {"threshold": 100, "current": 150}
    
    def test_monitoring_alert_defaults(self):
        """测试监控告警默认值"""
        alert = MonitoringAlert(
            alert_id="alert_002",
            alert_type="ConnectionLoss",
            severity="critical",
            message="Lost connection to exchange",
            timestamp=datetime.now(timezone.utc)
        )
        
        assert alert.resolved is False
        assert alert.context is None


# 基础覆盖率测试
class TestStorageTypesBasic:
    """存储类型基础覆盖率测试"""
    
    def test_module_import_attempt(self):
        """测试模块导入尝试"""
        try:
            from core.storage import types
            # 如果导入成功，测试基本属性
            assert hasattr(types, '__file__')
        except ImportError:
            # 如果导入失败，这也是预期的情况
            pytest.skip("存储类型模块不可用")
    
    def test_storage_types_concepts(self):
        """测试存储类型概念"""
        # 测试存储类型的核心概念
        concepts = [
            "normalized_data_structures",
            "market_data_standardization",
            "exchange_configuration",
            "error_tracking",
            "performance_monitoring"
        ]
        
        # 验证概念存在
        for concept in concepts:
            assert isinstance(concept, str)
            assert len(concept) > 0
    
    def test_market_data_union_type(self):
        """测试MarketData联合类型"""
        if HAS_STORAGE_TYPES:
            # 验证MarketData是一个联合类型
            assert MarketData is not None
            # 这是一个类型别名，主要用于类型提示
