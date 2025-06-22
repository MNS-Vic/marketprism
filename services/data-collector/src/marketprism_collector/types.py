"""
MarketPrism数据类型模块 - 兼容性别名

这个模块提供了对data_types模块的兼容性导入，
确保旧的导入路径仍然可以工作。
"""

# 从data_types模块导入所有内容
from .data_types import *

# 为了兼容性，创建别名
TradeData = NormalizedTrade
OrderBookData = NormalizedOrderBook
TickerData = NormalizedTicker

# 确保所有重要的类型都可以通过这个模块访问
__all__ = [
    # 枚举类型
    'Exchange',
    'MarketType', 
    'DataType',
    'OrderSide',
    'OrderType',
    'OrderStatus',
    'TimeInForce',
    
    # 数据类型
    'OrderBookEntry',
    'NormalizedOrderBook',
    'NormalizedTrade',
    'NormalizedTicker',
    'NormalizedKline',
    'NormalizedFundingRate',
    'NormalizedOpenInterest',
    'NormalizedLiquidation',
    'NormalizedTopTrader',
    'NormalizedMarketRatio',
    'NormalizedAccount',
    'NormalizedOrder',
    'NormalizedCommission',
    'NormalizedSession',
    'NormalizedAvgPrice',
    'NormalizedTradingDay',
    
    # 配置类型
    'ExchangeConfig',
    'CollectorConfig',
    'DataCollectorConfig',
    
    # 基础类型
    'BaseNormalizedData',

    # 兼容性别名
    'TradeData',
    'OrderBookData',
    'TickerData',
]
