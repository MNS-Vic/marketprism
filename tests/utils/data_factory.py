"""
MarketPrism测试数据工厂

提供一致且可定制的测试数据生成接口，支持各种数据类型
"""
import random
import time
import datetime
import uuid
from typing import Dict, List, Any, Optional, Union, Tuple
import json
import os

class DataFactory:
    """测试数据工厂，集中管理测试数据生成"""
    
    @staticmethod
    def create_trade(exchange: str = "binance", 
                    symbol: str = "BTC/USDT", 
                    price: float = None,
                    amount: float = None,
                    side: str = None,
                    timestamp: float = None,
                    trade_id: str = None) -> Dict[str, Any]:
        """
        创建交易数据
        
        Args:
            exchange: 交易所名称
            symbol: 交易对
            price: 价格，如未指定则生成随机值
            amount: 交易量，如未指定则生成随机值
            side: 方向 (buy/sell)，如未指定则随机选择
            timestamp: 时间戳，如未指定则使用当前时间
            trade_id: 交易ID，如未指定则生成随机ID
            
        Returns:
            Dict: 交易数据对象
        """
        if price is None:
            # 根据不同的币种设置合理的价格范围
            price_ranges = {
                "BTC/USDT": (45000, 65000),
                "ETH/USDT": (2000, 4000),
                "BNB/USDT": (200, 500),
                "SOL/USDT": (50, 150),
            }
            price_range = price_ranges.get(symbol, (10, 1000))
            price = round(random.uniform(*price_range), 2)
            
        if amount is None:
            # BTC等高价值币种的数量通常较小
            if "BTC" in symbol:
                amount = round(random.uniform(0.001, 1.0), 6)
            else:
                amount = round(random.uniform(0.1, 100.0), 6)
                
        if side is None:
            side = random.choice(["buy", "sell"])
            
        if timestamp is None:
            timestamp = time.time()
            
        if trade_id is None:
            trade_id = f"{exchange}_{int(timestamp)}_{uuid.uuid4().hex[:8]}"
            
        return {
            "exchange": exchange,
            "symbol": symbol,
            "price": price,
            "amount": amount,
            "timestamp": timestamp,
            "trade_id": trade_id,
            "side": side,
            "value": round(price * amount, 2)
        }
    
    @staticmethod
    def create_orderbook(exchange: str = "binance", 
                        symbol: str = "BTC/USDT", 
                        depth: int = 10,
                        price_base: float = None,
                        timestamp: float = None,
                        spread_percent: float = 0.02) -> Dict[str, Any]:
        """
        创建订单簿数据
        
        Args:
            exchange: 交易所名称
            symbol: 交易对
            depth: 订单簿深度
            price_base: 基准价格，如未指定则根据交易对生成合适价格
            timestamp: 时间戳，如未指定则使用当前时间
            spread_percent: 买卖价差百分比
            
        Returns:
            Dict: 订单簿数据对象
        """
        if price_base is None:
            # 根据不同的币种设置合理的价格
            price_bases = {
                "BTC/USDT": random.uniform(45000, 65000),
                "ETH/USDT": random.uniform(2000, 4000),
                "BNB/USDT": random.uniform(200, 500),
                "SOL/USDT": random.uniform(50, 150),
            }
            price_base = price_bases.get(symbol, random.uniform(10, 1000))
        
        if timestamp is None:
            timestamp = time.time()
        
        # 计算实际价差
        spread = price_base * spread_percent
        mid_price = price_base
        
        # 构建买单和卖单
        bids = []
        asks = []
        
        # 买单从中间价格减去半个价差开始递减
        bid_start = mid_price - (spread / 2)
        for i in range(depth):
            price_decrease = (i * 0.0001 * price_base)
            price = round(bid_start - price_decrease, 2)
            amount = round(random.uniform(0.01, 5) * (1 - (i / depth / 2)), 6)  # 更高价格的买单量略大
            bids.append([price, amount])
        
        # 卖单从中间价格加上半个价差开始递增
        ask_start = mid_price + (spread / 2)
        for i in range(depth):
            price_increase = (i * 0.0001 * price_base)
            price = round(ask_start + price_increase, 2)
            amount = round(random.uniform(0.01, 5) * (1 - (i / depth / 2)), 6)  # 更低价格的卖单量略大
            asks.append([price, amount])
        
        return {
            "exchange": exchange,
            "symbol": symbol,
            "timestamp": timestamp,
            "bids": bids,
            "asks": asks
        }
    
    @staticmethod
    def create_kline(exchange: str = "binance", 
                    symbol: str = "BTC/USDT", 
                    interval: str = "1m",
                    base_price: float = None,
                    timestamp: float = None,
                    volatility: float = 0.01) -> Dict[str, Any]:
        """
        创建K线数据
        
        Args:
            exchange: 交易所名称
            symbol: 交易对
            interval: K线周期
            base_price: 基准价格，如未指定则根据交易对生成合适价格
            timestamp: 起始时间戳，如未指定则使用当前时间
            volatility: 价格波动率
            
        Returns:
            Dict: K线数据对象
        """
        if base_price is None:
            # 根据不同的币种设置合理的价格
            price_bases = {
                "BTC/USDT": random.uniform(45000, 65000),
                "ETH/USDT": random.uniform(2000, 4000),
                "BNB/USDT": random.uniform(200, 500),
                "SOL/USDT": random.uniform(50, 150),
            }
            base_price = price_bases.get(symbol, random.uniform(10, 1000))
        
        if timestamp is None:
            timestamp = time.time()
        
        # 根据volatility参数生成价格波动
        price_range = base_price * volatility
        open_price = base_price
        close_price = round(random.uniform(base_price - price_range, base_price + price_range), 2)
        high_price = round(max(open_price, close_price) + random.uniform(0, price_range / 2), 2)
        low_price = round(min(open_price, close_price) - random.uniform(0, price_range / 2), 2)
        
        # 生成合理的交易量
        volume = round(random.uniform(0.1, 100), 6)
        if "BTC" in symbol:
            volume = round(random.uniform(0.1, 10), 6)  # BTC交易量通常较小
        
        # 计算时间区间
        interval_seconds = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
            "1w": 604800,
        }
        duration = interval_seconds.get(interval, 60)
        open_time = int(timestamp)
        close_time = int(open_time + duration - 1)  # 减1避免与下一周期重叠
        
        return {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "open_time": open_time,
            "close_time": close_time,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume,
            "trades": random.randint(10, 1000),
            "closed": True
        }
    
    @staticmethod
    def create_funding_rate(exchange: str = "binance", 
                           symbol: str = "BTC/USDT", 
                           timestamp: float = None,
                           rate: float = None) -> Dict[str, Any]:
        """
        创建资金费率数据
        
        Args:
            exchange: 交易所名称
            symbol: 交易对
            timestamp: 时间戳，如未指定则使用当前时间
            rate: 费率，如未指定则生成随机费率
            
        Returns:
            Dict: 资金费率数据对象
        """
        if timestamp is None:
            timestamp = time.time()
            
        if rate is None:
            # 资金费率通常在 -0.1% 到 0.1% 之间
            rate = round(random.uniform(-0.001, 0.001), 6)
            
        next_funding_time = int(timestamp) + (8 * 3600)  # 通常每8小时结算一次
        next_funding_time = (next_funding_time // (8 * 3600)) * (8 * 3600)  # 对齐到8小时间隔
        
        return {
            "exchange": exchange,
            "symbol": symbol,
            "timestamp": timestamp,
            "funding_rate": rate,
            "next_funding_time": next_funding_time
        }
    
    @staticmethod
    def create_batch(creator_func, count: int, **kwargs) -> List[Dict[str, Any]]:
        """
        批量创建数据
        
        Args:
            creator_func: 数据创建函数
            count: 创建数量
            **kwargs: 传递给创建函数的参数
            
        Returns:
            List: 数据对象列表
        """
        return [creator_func(**kwargs) for _ in range(count)]
    
    @staticmethod
    def create_time_series(creator_func, 
                          start_time: Union[int, float, datetime.datetime],
                          end_time: Union[int, float, datetime.datetime] = None,
                          interval_seconds: int = 60,
                          **kwargs) -> List[Dict[str, Any]]:
        """
        创建时间序列数据
        
        Args:
            creator_func: 数据创建函数
            start_time: 起始时间
            end_time: 结束时间，如未指定则使用当前时间
            interval_seconds: 时间间隔(秒)
            **kwargs: 传递给创建函数的参数
            
        Returns:
            List: 按时间顺序排列的数据对象列表
        """
        # 转换时间格式
        if isinstance(start_time, datetime.datetime):
            start_time = start_time.timestamp()
            
        if end_time is None:
            end_time = time.time()
        elif isinstance(end_time, datetime.datetime):
            end_time = end_time.timestamp()
        
        # 生成时间点
        timestamps = []
        current = start_time
        while current <= end_time:
            timestamps.append(current)
            current += interval_seconds
        
        # 创建数据
        result = []
        for ts in timestamps:
            data = creator_func(timestamp=ts, **kwargs)
            result.append(data)
            
        return result
    
    @staticmethod
    def save_to_file(data: Union[Dict, List], filepath: str) -> None:
        """
        将测试数据保存到文件
        
        Args:
            data: 要保存的数据
            filepath: 文件路径
        """
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    @staticmethod
    def load_from_file(filepath: str) -> Union[Dict, List]:
        """
        从文件加载测试数据
        
        Args:
            filepath: 文件路径
            
        Returns:
            加载的数据
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
            
# 全局实例，便于直接导入使用
data_factory = DataFactory()