"""
MarketPrism 测试数据工厂

提供一致、可重复的测试数据生成功能
"""
import random
import datetime
from typing import Dict, List, Any, Optional, Union
from decimal import Decimal
import uuid

# 移除faker依赖，使用简单的随机数据生成
def fake_sentence():
    """生成假句子"""
    words = ['market', 'data', 'trading', 'exchange', 'price', 'volume', 'order', 'book']
    return ' '.join(random.choices(words, k=random.randint(3, 8)))

def fake_text():
    """生成假文本"""
    return ' '.join([fake_sentence() for _ in range(random.randint(2, 5))])

def fake_ipv4():
    """生成假IP地址"""
    return f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"

def fake_uuid4():
    """生成假UUID"""
    return str(uuid.uuid4())

class BaseDataFactory:
    """基础数据工厂"""
    
    @staticmethod
    def generate_timestamp(
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None
    ) -> float:
        """生成时间戳"""
        if start_date is None:
            start_date = datetime.datetime.now() - datetime.timedelta(days=30)
        if end_date is None:
            end_date = datetime.datetime.now()
        
        time_between = end_date - start_date
        days_between = time_between.days
        random_days = random.randrange(days_between)
        random_time = start_date + datetime.timedelta(days=random_days)
        
        return random_time.timestamp()
    
    @staticmethod
    def generate_price(base_price: float = 50000.0, volatility: float = 0.1) -> float:
        """生成价格数据"""
        change_percent = random.uniform(-volatility, volatility)
        return round(base_price * (1 + change_percent), 2)
    
    @staticmethod
    def generate_volume(min_vol: float = 0.001, max_vol: float = 100.0) -> float:
        """生成交易量"""
        return round(random.uniform(min_vol, max_vol), 6)


class TradeDataFactory(BaseDataFactory):
    """交易数据工厂"""
    
    EXCHANGES = ['binance', 'okex', 'huobi', 'coinbase', 'kraken']
    SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'DOT/USDT']
    SIDES = ['buy', 'sell']
    
    @classmethod
    def create_trade(
        cls,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        price: Optional[float] = None,
        amount: Optional[float] = None,
        side: Optional[str] = None,
        timestamp: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """创建单个交易数据"""
        return {
            'id': kwargs.get('id', str(uuid.uuid4())),
            'exchange': exchange or random.choice(cls.EXCHANGES),
            'symbol': symbol or random.choice(cls.SYMBOLS),
            'price': price or cls.generate_price(),
            'amount': amount or cls.generate_volume(),
            'side': side or random.choice(cls.SIDES),
            'timestamp': timestamp or cls.generate_timestamp(),
            'trade_id': kwargs.get('trade_id', f"trade_{random.randint(1000000, 9999999)}"),
            'order_id': kwargs.get('order_id', f"order_{random.randint(1000000, 9999999)}"),
            'fee': kwargs.get('fee', round(random.uniform(0.0001, 0.001), 6)),
            'fee_currency': kwargs.get('fee_currency', 'USDT'),
            'taker_or_maker': kwargs.get('taker_or_maker', random.choice(['taker', 'maker']))
        }
    
    @classmethod
    def create_trades_batch(
        cls,
        count: int = 100,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        time_range_hours: int = 24,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """创建批量交易数据"""
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(hours=time_range_hours)
        
        trades = []
        for i in range(count):
            # 生成时间序列数据
            timestamp = start_time.timestamp() + (i * time_range_hours * 3600 / count)
            
            trade = cls.create_trade(
                exchange=exchange,
                symbol=symbol,
                timestamp=timestamp,
                **kwargs
            )
            trades.append(trade)
        
        return trades
    
    @classmethod
    def create_realistic_trade_sequence(
        cls,
        symbol: str = 'BTC/USDT',
        exchange: str = 'binance',
        duration_minutes: int = 60,
        base_price: float = 50000.0,
        volatility: float = 0.02
    ) -> List[Dict[str, Any]]:
        """创建真实的交易序列（价格走势相关）"""
        trades = []
        current_time = datetime.datetime.now()
        current_price = base_price
        
        # 每分钟生成1-10笔交易
        for minute in range(duration_minutes):
            trades_per_minute = random.randint(1, 10)
            
            for trade_idx in range(trades_per_minute):
                # 价格随机游走
                price_change = random.uniform(-volatility, volatility)
                current_price = max(current_price * (1 + price_change), 0.01)
                
                timestamp = (current_time + datetime.timedelta(
                    minutes=minute,
                    seconds=trade_idx * (60 / trades_per_minute)
                )).timestamp()
                
                trade = cls.create_trade(
                    exchange=exchange,
                    symbol=symbol,
                    price=round(current_price, 2),
                    timestamp=timestamp
                )
                trades.append(trade)
        
        return trades


class OrderBookDataFactory(BaseDataFactory):
    """订单簿数据工厂"""
    
    @classmethod
    def create_orderbook(
        cls,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        depth: int = 20,
        spread_percent: float = 0.001,
        base_price: float = 50000.0,
        timestamp: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """创建订单簿数据"""
        exchange = exchange or random.choice(TradeDataFactory.EXCHANGES)
        symbol = symbol or random.choice(TradeDataFactory.SYMBOLS)
        timestamp = timestamp or cls.generate_timestamp()
        
        # 计算买卖价差
        spread = base_price * spread_percent
        best_bid = base_price - spread / 2
        best_ask = base_price + spread / 2
        
        # 生成买单（递减价格）
        bids = []
        for i in range(depth):
            price = round(best_bid * (1 - 0.0001 * i), 2)
            amount = cls.generate_volume(0.01, 10.0)
            bids.append([price, amount])
        
        # 生成卖单（递增价格）
        asks = []
        for i in range(depth):
            price = round(best_ask * (1 + 0.0001 * i), 2)
            amount = cls.generate_volume(0.01, 10.0)
            asks.append([price, amount])
        
        return {
            'exchange': exchange,
            'symbol': symbol,
            'timestamp': timestamp,
            'bids': bids,
            'asks': asks,
            'checksum': kwargs.get('checksum', random.randint(1000000, 9999999)),
            'sequence': kwargs.get('sequence', random.randint(1000000, 9999999))
        }
    
    @classmethod
    def create_orderbook_snapshot_sequence(
        cls,
        symbol: str = 'BTC/USDT',
        exchange: str = 'binance',
        count: int = 100,
        interval_seconds: int = 1,
        base_price: float = 50000.0,
        price_volatility: float = 0.001
    ) -> List[Dict[str, Any]]:
        """创建订单簿快照序列"""
        snapshots = []
        current_time = datetime.datetime.now()
        current_price = base_price
        
        for i in range(count):
            # 价格微调
            price_change = random.uniform(-price_volatility, price_volatility)
            current_price = max(current_price * (1 + price_change), 0.01)
            
            timestamp = (current_time + datetime.timedelta(seconds=i * interval_seconds)).timestamp()
            
            snapshot = cls.create_orderbook(
                exchange=exchange,
                symbol=symbol,
                base_price=current_price,
                timestamp=timestamp
            )
            snapshots.append(snapshot)
        
        return snapshots


class TickerDataFactory(BaseDataFactory):
    """行情数据工厂"""
    
    @classmethod
    def create_ticker(
        cls,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        base_price: float = 50000.0,
        timestamp: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """创建行情数据"""
        exchange = exchange or random.choice(TradeDataFactory.EXCHANGES)
        symbol = symbol or random.choice(TradeDataFactory.SYMBOLS)
        timestamp = timestamp or cls.generate_timestamp()
        
        # 生成OHLCV数据
        open_price = base_price
        high_price = open_price * random.uniform(1.0, 1.05)
        low_price = open_price * random.uniform(0.95, 1.0)
        close_price = random.uniform(low_price, high_price)
        volume = cls.generate_volume(1000, 1000000)
        
        return {
            'exchange': exchange,
            'symbol': symbol,
            'timestamp': timestamp,
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': round(volume, 2),
            'quote_volume': round(volume * close_price, 2),
            'count': kwargs.get('count', random.randint(100, 10000)),
            'bid': round(close_price * 0.999, 2),
            'ask': round(close_price * 1.001, 2),
            'bid_volume': cls.generate_volume(1, 100),
            'ask_volume': cls.generate_volume(1, 100),
            'vwap': round(close_price * random.uniform(0.998, 1.002), 2),
            'change': round((close_price - open_price) / open_price * 100, 2),
            'percentage': round((close_price - open_price) / open_price * 100, 2)
        }


class KlineDataFactory(BaseDataFactory):
    """K线数据工厂"""
    
    INTERVALS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']
    
    @classmethod
    def create_kline(
        cls,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        interval: str = '1h',
        timestamp: Optional[float] = None,
        base_price: float = 50000.0,
        **kwargs
    ) -> Dict[str, Any]:
        """创建K线数据"""
        exchange = exchange or random.choice(TradeDataFactory.EXCHANGES)
        symbol = symbol or random.choice(TradeDataFactory.SYMBOLS)
        timestamp = timestamp or cls.generate_timestamp()
        
        # 生成OHLCV
        open_price = base_price
        volatility = kwargs.get('volatility', 0.02)
        high_price = open_price * random.uniform(1.0, 1 + volatility)
        low_price = open_price * random.uniform(1 - volatility, 1.0)
        close_price = random.uniform(low_price, high_price)
        volume = cls.generate_volume(100, 100000)
        
        return {
            'exchange': exchange,
            'symbol': symbol,
            'interval': interval,
            'timestamp': timestamp,
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(close_price, 2),
            'volume': round(volume, 2),
            'quote_volume': round(volume * close_price, 2),
            'trades_count': random.randint(10, 1000),
            'taker_buy_volume': round(volume * random.uniform(0.4, 0.6), 2),
            'taker_buy_quote_volume': round(volume * close_price * random.uniform(0.4, 0.6), 2)
        }
    
    @classmethod
    def create_kline_series(
        cls,
        symbol: str = 'BTC/USDT',
        exchange: str = 'binance',
        interval: str = '1h',
        count: int = 100,
        start_price: float = 50000.0,
        trend: str = 'random'  # 'up', 'down', 'random'
    ) -> List[Dict[str, Any]]:
        """创建K线序列"""
        klines = []
        current_time = datetime.datetime.now()
        current_price = start_price
        
        # 计算时间间隔
        interval_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440, '1w': 10080
        }
        minutes = interval_minutes.get(interval, 60)
        
        for i in range(count):
            timestamp = (current_time - datetime.timedelta(
                minutes=(count - i) * minutes
            )).timestamp()
            
            # 根据趋势调整价格
            if trend == 'up':
                price_change = random.uniform(-0.01, 0.02)
            elif trend == 'down':
                price_change = random.uniform(-0.02, 0.01)
            else:  # random
                price_change = random.uniform(-0.02, 0.02)
            
            current_price = max(current_price * (1 + price_change), 0.01)
            
            kline = cls.create_kline(
                exchange=exchange,
                symbol=symbol,
                interval=interval,
                timestamp=timestamp,
                base_price=current_price
            )
            klines.append(kline)
        
        return klines


class ExchangeConfigFactory:
    """交易所配置工厂"""
    
    @classmethod
    def create_exchange_config(
        cls,
        exchange_name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """创建交易所配置"""
        exchange_name = exchange_name or random.choice(TradeDataFactory.EXCHANGES)
        
        return {
            'name': exchange_name,
            'enabled': kwargs.get('enabled', True),
            'api_key': kwargs.get('api_key', fake_uuid4()),
            'api_secret': kwargs.get('api_secret', fake_uuid4()),
            'sandbox': kwargs.get('sandbox', True),
            'rate_limit': kwargs.get('rate_limit', random.randint(100, 1000)),
            'timeout': kwargs.get('timeout', random.randint(5, 30)),
            'retry_count': kwargs.get('retry_count', random.randint(3, 10)),
            'symbols': kwargs.get('symbols', random.sample(TradeDataFactory.SYMBOLS, 3)),
            'endpoints': {
                'rest': f'https://api.{exchange_name}.com',
                'websocket': f'wss://stream.{exchange_name}.com',
                'testnet_rest': f'https://testnet.{exchange_name}.com',
                'testnet_websocket': f'wss://testnet-stream.{exchange_name}.com'
            },
            'features': {
                'trades': True,
                'orderbook': True,
                'ticker': True,
                'klines': True,
                'spot': True,
                'futures': kwargs.get('futures', random.choice([True, False]))
            }
        }


class SystemEventFactory:
    """系统事件工厂"""
    
    EVENT_TYPES = ['info', 'warning', 'error', 'critical']
    COMPONENTS = ['collector', 'normalizer', 'archiver', 'api', 'database', 'message_queue']
    
    @classmethod
    def create_system_event(
        cls,
        event_type: Optional[str] = None,
        component: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """创建系统事件"""
        return {
            'id': str(uuid.uuid4()),
            'timestamp': BaseDataFactory.generate_timestamp(),
            'type': event_type or random.choice(cls.EVENT_TYPES),
            'component': component or random.choice(cls.COMPONENTS),
            'message': kwargs.get('message', fake_sentence()),
            'details': kwargs.get('details', fake_text()),
            'severity': kwargs.get('severity', random.randint(1, 5)),
            'resolved': kwargs.get('resolved', random.choice([True, False])),
            'metadata': kwargs.get('metadata', {
                'host': fake_ipv4(),
                'process_id': random.randint(1000, 9999),
                'thread_id': random.randint(100, 999)
            })
        }


# 便捷函数
def create_sample_dataset(
    trades_count: int = 1000,
    orderbooks_count: int = 100,
    tickers_count: int = 50,
    klines_count: int = 200
) -> Dict[str, List[Dict[str, Any]]]:
    """创建完整的样本数据集"""
    return {
        'trades': TradeDataFactory.create_trades_batch(trades_count),
        'orderbooks': [
            OrderBookDataFactory.create_orderbook() 
            for _ in range(orderbooks_count)
        ],
        'tickers': [
            TickerDataFactory.create_ticker() 
            for _ in range(tickers_count)
        ],
        'klines': KlineDataFactory.create_kline_series(count=klines_count)
    }


def create_test_scenario_data(scenario: str) -> Dict[str, Any]:
    """根据测试场景创建数据"""
    scenarios = {
        'high_frequency': {
            'trades': TradeDataFactory.create_trades_batch(10000, time_range_hours=1),
            'orderbooks': OrderBookDataFactory.create_orderbook_snapshot_sequence(
                count=3600, interval_seconds=1
            )
        },
        'multi_exchange': {
            'binance_trades': TradeDataFactory.create_trades_batch(500, exchange='binance'),
            'okex_trades': TradeDataFactory.create_trades_batch(500, exchange='okex'),
            'huobi_trades': TradeDataFactory.create_trades_batch(500, exchange='huobi')
        },
        'price_volatility': {
            'volatile_trades': TradeDataFactory.create_realistic_trade_sequence(
                volatility=0.05, duration_minutes=120
            ),
            'stable_trades': TradeDataFactory.create_realistic_trade_sequence(
                volatility=0.001, duration_minutes=120
            )
        }
    }
    
    return scenarios.get(scenario, create_sample_dataset()) 