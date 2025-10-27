"""
Snapshot-based OrderBook managers package.

Provides:
- BaseOrderBookSnapManager: common 1s polling loop and publish helpers
- Concrete managers (placeholders for now):
  * BinanceSpotSnapManager
  * BinanceDerivativesSnapManager
  * OKXSpotSnapManager
  * OKXDerivativesSnapManager
- OrderBookSnapManagerFactory: factory for snapshot managers
"""

from .base_orderbook_snap_manager import BaseOrderBookSnapManager
from .manager_factory import OrderBookSnapManagerFactory
from .binance_spot_snap_manager import BinanceSpotSnapManager
from .binance_derivatives_snap_manager import BinanceDerivativesSnapManager
from .okx_spot_snap_manager import OKXSpotSnapManager
from .okx_derivatives_snap_manager import OKXDerivativesSnapManager

