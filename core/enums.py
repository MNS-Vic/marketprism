"""
Core Enums for MarketPrism

This module provides a centralized, single source of truth for all
fundamental enumerations used across the entire system.
"""

from datetime import datetime, timezone
from enum import Enum


class DataType(str, Enum):
    """Supported data types"""
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    KLINE = "kline"
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


class MarketType(str, Enum):
    """Market types"""
    SPOT = "spot"
    FUTURES = "futures"
    PERPETUAL = "perpetual"
    OPTIONS = "options"
    DERIVATIVES = "derivatives" 