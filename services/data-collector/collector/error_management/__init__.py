"""
错误管理模块
集成Binance官方错误码管理和统一错误处理
"""

from .binance_error_codes import (
    BinanceErrorManager,
    BinanceErrorCategory,
    BinanceErrorSeverity,
    ErrorInfo,
    binance_error_manager
)

from .error_handler import (
    ErrorHandler,
    BinanceAPIError,
    RetryHandler
)

__all__ = [
    'BinanceErrorManager',
    'BinanceErrorCategory', 
    'BinanceErrorSeverity',
    'ErrorInfo',
    'binance_error_manager',
    'ErrorHandler',
    'BinanceAPIError',
    'RetryHandler'
]
