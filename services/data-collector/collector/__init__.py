"""
MarketPrism Data Collector - 集成微服务
包含数据收集、OrderBook管理和数据聚合功能
"""

__version__ = "1.0.0"
__author__ = "MarketPrism Team"

from .service import DataCollectorService
from .orderbook_manager import OrderBookManager
from .normalizer import DataNormalizer

__all__ = [
    "DataCollectorService",
    "OrderBookManager",
    "DataNormalizer"
]
