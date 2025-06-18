"""
测试数据工厂
使用Factory Boy生成各种测试数据
"""

import factory
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List
from decimal import Decimal

# 尝试导入数据类型
try:
    from marketprism_collector.types import TradeData, OrderBookData, TickerData
    HAS_COLLECTOR_TYPES = True
except ImportError:
    HAS_COLLECTOR_TYPES = False


class BaseDataFactory(factory.Factory):
    """基础数据工厂"""
    
    @classmethod
    def _create(cls, model_class, **kwargs):
        """创建数据实例"""
        if HAS_COLLECTOR_TYPES and hasattr(model_class, '__annotations__'):
            # 如果是Pydantic模型，使用模型创建
            return model_class(**kwargs)
        else:
            # 否则返回字典
            return kwargs


class ExchangeConfigFactory(factory.DictFactory):
    """交易所配置工厂"""
    
    enabled = True
    api_key = factory.Faker('uuid4')
    api_secret = factory.Faker('uuid4')
    testnet = True
    rate_limit = 1200
    timeout = 30


class BinanceConfigFactory(ExchangeConfigFactory):
    """Binance配置工厂"""
    
    name = "binance"
    base_url = "https://api.binance.com"
    websocket_url = "wss://stream.binance.com:9443"


class OKXConfigFactory(ExchangeConfigFactory):
    """OKX配置工厂"""
    
    name = "okx"
    base_url = "https://www.okx.com"
    websocket_url = "wss://ws.okx.com:8443"
    passphrase = factory.Faker('password')


class TradeDataFactory(BaseDataFactory):
    """交易数据工厂"""
    
    class Meta:
        model = dict if not HAS_COLLECTOR_TYPES else TradeData
    
    exchange = factory.Iterator(["binance", "okx", "deribit"])
    symbol = factory.Iterator(["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT"])
    trade_id = factory.Sequence(lambda n: f"trade_{n}")
    price = factory.LazyFunction(lambda: round(random.uniform(1000, 100000), 2))
    quantity = factory.LazyFunction(lambda: round(random.uniform(0.001, 10), 6))
    side = factory.Iterator(["buy", "sell"])
    timestamp = factory.LazyFunction(lambda: int(datetime.now().timestamp() * 1000))
    is_buyer_maker = factory.Faker('boolean')


class OrderBookDataFactory(BaseDataFactory):
    """订单簿数据工厂"""
    
    class Meta:
        model = dict if not HAS_COLLECTOR_TYPES else OrderBookData
    
    exchange = factory.Iterator(["binance", "okx", "deribit"])
    symbol = factory.Iterator(["BTCUSDT", "ETHUSDT", "ADAUSDT"])
    timestamp = factory.LazyFunction(lambda: int(datetime.now().timestamp() * 1000))
    
    @factory.lazy_attribute
    def bids(self):
        """生成买单数据"""
        base_price = random.uniform(40000, 60000)
        return [
            [round(base_price - i * 10, 2), round(random.uniform(0.1, 5), 4)]
            for i in range(20)
        ]
    
    @factory.lazy_attribute
    def asks(self):
        """生成卖单数据"""
        base_price = random.uniform(40000, 60000)
        return [
            [round(base_price + i * 10, 2), round(random.uniform(0.1, 5), 4)]
            for i in range(20)
        ]


class TickerDataFactory(BaseDataFactory):
    """行情数据工厂"""
    
    class Meta:
        model = dict if not HAS_COLLECTOR_TYPES else TickerData
    
    exchange = factory.Iterator(["binance", "okx", "deribit"])
    symbol = factory.Iterator(["BTCUSDT", "ETHUSDT", "ADAUSDT"])
    timestamp = factory.LazyFunction(lambda: int(datetime.now().timestamp() * 1000))
    
    @factory.lazy_attribute
    def open_price(self):
        return round(random.uniform(40000, 60000), 2)
    
    @factory.lazy_attribute
    def high_price(self):
        return round(self.open_price * random.uniform(1.0, 1.1), 2)
    
    @factory.lazy_attribute
    def low_price(self):
        return round(self.open_price * random.uniform(0.9, 1.0), 2)
    
    @factory.lazy_attribute
    def close_price(self):
        return round(random.uniform(self.low_price, self.high_price), 2)
    
    volume = factory.LazyFunction(lambda: round(random.uniform(1000, 100000), 2))
    quote_volume = factory.LazyFunction(lambda: round(random.uniform(50000000, 5000000000), 2))
    count = factory.LazyFunction(lambda: random.randint(10000, 1000000))


class ConfigDataFactory(factory.DictFactory):
    """配置数据工厂"""
    
    app = factory.SubFactory(factory.DictFactory, 
        name="marketprism-test",
        version="1.0.0",
        debug=True
    )
    
    logging = factory.SubFactory(factory.DictFactory,
        level="DEBUG",
        format="json",
        file="test.log"
    )
    
    exchanges = factory.SubFactory(factory.DictFactory,
        binance=factory.SubFactory(BinanceConfigFactory),
        okx=factory.SubFactory(OKXConfigFactory)
    )
    
    storage = factory.SubFactory(factory.DictFactory,
        clickhouse=factory.SubFactory(factory.DictFactory,
            host="localhost",
            port=8123,
            database="test_marketprism",
            user="default",
            password=""
        ),
        redis=factory.SubFactory(factory.DictFactory,
            host="localhost",
            port=6379,
            db=0,
            password=""
        )
    )
    
    nats = factory.SubFactory(factory.DictFactory,
        servers=["nats://localhost:4222"],
        cluster_id="test-cluster",
        client_id=factory.Faker('uuid4')
    )


class ErrorDataFactory(factory.DictFactory):
    """错误数据工厂"""
    
    error_type = factory.Iterator([
        "ConnectionError", 
        "DataValidationError", 
        "ConfigurationError",
        "ExchangeError"
    ])
    
    message = factory.Faker('sentence')
    timestamp = factory.LazyFunction(lambda: datetime.now().isoformat())
    severity = factory.Iterator(["low", "medium", "high", "critical"])
    component = factory.Iterator(["data_collector", "storage", "config", "network"])
    
    @factory.lazy_attribute
    def context(self):
        return {
            "exchange": random.choice(["binance", "okx", "deribit"]),
            "symbol": random.choice(["BTCUSDT", "ETHUSDT", "ADAUSDT"]),
            "operation": random.choice(["connect", "subscribe", "write", "read"])
        }


class MetricsDataFactory(factory.DictFactory):
    """指标数据工厂"""
    
    metric_name = factory.Iterator([
        "trades_processed",
        "orderbook_updates", 
        "connection_errors",
        "data_validation_errors",
        "processing_latency"
    ])
    
    value = factory.LazyFunction(lambda: random.uniform(0, 1000))
    timestamp = factory.LazyFunction(lambda: datetime.now().timestamp())
    
    @factory.lazy_attribute
    def tags(self):
        return {
            "exchange": random.choice(["binance", "okx", "deribit"]),
            "symbol": random.choice(["BTCUSDT", "ETHUSDT", "ADAUSDT"]),
            "data_type": random.choice(["trade", "orderbook", "ticker"])
        }


class HealthCheckDataFactory(factory.DictFactory):
    """健康检查数据工厂"""
    
    status = factory.Iterator(["healthy", "degraded", "unhealthy"])
    timestamp = factory.LazyFunction(lambda: datetime.now().isoformat())
    
    @factory.lazy_attribute
    def components(self):
        return {
            "database": random.choice(["healthy", "degraded", "unhealthy"]),
            "message_queue": random.choice(["healthy", "degraded", "unhealthy"]),
            "exchanges": {
                "binance": random.choice(["connected", "disconnected", "error"]),
                "okx": random.choice(["connected", "disconnected", "error"])
            }
        }
    
    @factory.lazy_attribute
    def metrics(self):
        return {
            "uptime": random.randint(0, 86400),
            "memory_usage": random.uniform(0.1, 0.9),
            "cpu_usage": random.uniform(0.1, 0.8),
            "active_connections": random.randint(0, 100)
        }


class TestDataGenerator:
    """测试数据生成器"""
    
    @staticmethod
    def generate_trade_batch(count: int = 100, exchange: str = None) -> List[Dict[str, Any]]:
        """生成交易数据批次"""
        kwargs = {}
        if exchange:
            kwargs['exchange'] = exchange
            
        return TradeDataFactory.build_batch(count, **kwargs)
    
    @staticmethod
    def generate_orderbook_batch(count: int = 10, exchange: str = None) -> List[Dict[str, Any]]:
        """生成订单簿数据批次"""
        kwargs = {}
        if exchange:
            kwargs['exchange'] = exchange
            
        return OrderBookDataFactory.build_batch(count, **kwargs)
    
    @staticmethod
    def generate_ticker_batch(count: int = 50, exchange: str = None) -> List[Dict[str, Any]]:
        """生成行情数据批次"""
        kwargs = {}
        if exchange:
            kwargs['exchange'] = exchange
            
        return TickerDataFactory.build_batch(count, **kwargs)
    
    @staticmethod
    def generate_time_series_data(
        data_type: str = "trade",
        start_time: datetime = None,
        end_time: datetime = None,
        interval_seconds: int = 60,
        exchange: str = "binance",
        symbol: str = "BTCUSDT"
    ) -> List[Dict[str, Any]]:
        """生成时间序列数据"""
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=1)
        if end_time is None:
            end_time = datetime.now()
            
        data = []
        current_time = start_time
        
        factory_map = {
            "trade": TradeDataFactory,
            "orderbook": OrderBookDataFactory,
            "ticker": TickerDataFactory
        }
        
        factory_class = factory_map.get(data_type, TradeDataFactory)
        
        while current_time <= end_time:
            timestamp = int(current_time.timestamp() * 1000)
            
            data_point = factory_class.build(
                exchange=exchange,
                symbol=symbol,
                timestamp=timestamp
            )
            
            data.append(data_point)
            current_time += timedelta(seconds=interval_seconds)
            
        return data
    
    @staticmethod
    def generate_error_scenarios() -> List[Dict[str, Any]]:
        """生成错误场景数据"""
        scenarios = [
            # 连接错误
            ErrorDataFactory.build(
                error_type="ConnectionError",
                message="Failed to connect to exchange",
                severity="high",
                context={"exchange": "binance", "operation": "connect"}
            ),
            
            # 数据验证错误
            ErrorDataFactory.build(
                error_type="DataValidationError", 
                message="Invalid price format",
                severity="medium",
                context={"exchange": "okx", "symbol": "BTCUSDT", "operation": "validate"}
            ),
            
            # 配置错误
            ErrorDataFactory.build(
                error_type="ConfigurationError",
                message="Missing API key",
                severity="critical",
                context={"component": "config", "operation": "load"}
            )
        ]
        
        return scenarios
    
    @staticmethod
    def generate_performance_test_data(scale: str = "small") -> Dict[str, List[Dict[str, Any]]]:
        """生成性能测试数据"""
        scale_config = {
            "small": {"trades": 1000, "orderbooks": 100, "tickers": 200},
            "medium": {"trades": 10000, "orderbooks": 1000, "tickers": 2000},
            "large": {"trades": 100000, "orderbooks": 10000, "tickers": 20000}
        }
        
        config = scale_config.get(scale, scale_config["small"])
        
        return {
            "trades": TestDataGenerator.generate_trade_batch(config["trades"]),
            "orderbooks": TestDataGenerator.generate_orderbook_batch(config["orderbooks"]),
            "tickers": TestDataGenerator.generate_ticker_batch(config["tickers"])
        }
