"""
MarketPrism Python Collector

一个高性能的加密货币市场数据收集器，支持多个交易所的实时数据采集、
数据标准化和通过NATS进行数据分发。

主要功能：
- 支持多个主流加密货币交易所 (Binance, OKX, Deribit等)
- 实时WebSocket数据流
- 数据标准化和清洗
- NATS消息队列集成
- 高性能异步处理
- 完善的监控和日志记录
"""

__version__ = "1.0.0"
__author__ = "MarketPrism Team"
__email__ = "team@marketprism.com"

from .collector import MarketDataCollector
from .config import Config
from .types import *

__all__ = [
    "MarketDataCollector",
    "Config",
    "NormalizedTrade",
    "NormalizedOrderBook", 
    "NormalizedKline",
    "NormalizedTicker",
] 