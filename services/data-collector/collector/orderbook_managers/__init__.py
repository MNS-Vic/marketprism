"""
订单簿管理器模块

提供不同交易所的专用订单簿管理器：
- OKXSpotOrderBookManager: OKX现货订单簿管理
- OKXDerivativesOrderBookManager: OKX衍生品订单簿管理
- BinanceSpotOrderBookManager: Binance现货订单簿管理
- BinanceDerivativesOrderBookManager: Binance衍生品订单簿管理
- OrderBookManagerFactory: 管理器工厂类

架构特点：
1. 每个交易所有独立的管理器实现
2. 保持与原有架构的完全兼容性
3. 串行消息处理和原子化操作
4. 交易所特定的序列验证和错误处理
"""

from .base_orderbook_manager import BaseOrderBookManager
from .okx_spot_manager import OKXSpotOrderBookManager
from .okx_derivatives_manager import OKXDerivativesOrderBookManager
from .binance_spot_manager import BinanceSpotOrderBookManager
from .binance_derivatives_manager import BinanceDerivativesOrderBookManager
from .manager_factory import OrderBookManagerFactory, orderbook_manager_factory

__all__ = [
    'BaseOrderBookManager',
    'OKXSpotOrderBookManager',
    'OKXDerivativesOrderBookManager',
    'BinanceSpotOrderBookManager',
    'BinanceDerivativesOrderBookManager',
    'OrderBookManagerFactory',
    'orderbook_manager_factory'
]
