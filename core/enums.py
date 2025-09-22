"""
Core Enums for MarketPrism

This module provides a centralized, single source of truth for all
fundamental enumerations used across the entire system.
"""

from datetime import datetime, timezone
from enum import Enum


# Trading Data Enums
class DataType(str, Enum):
    """Supported data types"""
    TRADE = "trade"
    ORDERBOOK = "orderbook"

    TICKER = "ticker"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    LIQUIDATION = "liquidation"
    TOP_TRADER_LONG_SHORT_RATIO = "top_trader_long_short_ratio"
    MARKET_LONG_SHORT_RATIO = "market_long_short_ratio"


class Exchange(str, Enum):
    """Supported exchanges"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"
    BYBIT = "bybit"
    HUOBI = "huobi"


class ExchangeType(str, Enum):
    """Supported exchanges (alias for backward compatibility)"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"
    BYBIT = "bybit"
    HUOBI = "huobi"


class MarketType(str, Enum):
    """Market types"""
    SPOT = "spot"
    FUTURES = "futures"
    PERPETUAL = "perpetual"
    OPTIONS = "options"
    DERIVATIVES = "derivatives"


# Service Framework Enums
class ServiceStatus(str, Enum):
    """Service status enumeration"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    FAILED = "failed"
    UNKNOWN = "unknown"


class LogLevel(str, Enum):
    """Log level enumeration"""
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    
    @property
    def numeric_level(self) -> int:
        """Get numeric level for comparison"""
        level_map = {
            LogLevel.TRACE: 5,
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50
        }
        return level_map[self] 