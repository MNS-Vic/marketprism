"""
MarketPrism Trades Managers - 逐笔成交数据管理器
基于OrderBook Manager的成功架构模式实现
"""

__version__ = "1.0.0"
__author__ = "MarketPrism Team"

from .base_trades_manager import BaseTradesManager
from .binance_spot_trades_manager import BinanceSpotTradesManager
from .binance_derivatives_trades_manager import BinanceDerivativesTradesManager
from .okx_spot_trades_manager import OKXSpotTradesManager
from .okx_derivatives_trades_manager import OKXDerivativesTradesManager

__all__ = [
    "BaseTradesManager",
    "BinanceSpotTradesManager", 
    "BinanceDerivativesTradesManager",
    "OKXSpotTradesManager",
    "OKXDerivativesTradesManager"
]
