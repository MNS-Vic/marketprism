from __future__ import annotations

from typing import List, Optional

import structlog

from .base_orderbook_snap_manager import BaseOrderBookSnapManager
from .binance_spot_snap_manager import BinanceSpotSnapManager
from .binance_derivatives_snap_manager import BinanceDerivativesSnapManager
from .okx_spot_snap_manager import OKXSpotSnapManager
from .okx_derivatives_snap_manager import OKXDerivativesSnapManager


class OrderBookSnapManagerFactory:
    """Factory for snapshot-based orderbook managers."""

    def __init__(self) -> None:
        self.logger = structlog.get_logger("orderbook_snap_manager_factory")

    def create_manager(
        self,
        exchange: str,
        market_type: str,
        symbols: List[str],
        normalizer,
        nats_publisher,
        config: dict,
        metrics_collector=None,
    ) -> Optional[BaseOrderBookSnapManager]:
        try:
            key = f"{exchange}_{market_type}"
            self.logger.info("Create snapshot orderbook manager", key=key)

            if exchange in ("binance", "binance_spot") and market_type == "spot":
                return BinanceSpotSnapManager(exchange, market_type, symbols, normalizer, nats_publisher, config, metrics_collector)

            if exchange in ("binance", "binance_derivatives") and market_type in ("perpetual", "swap", "perp"):
                return BinanceDerivativesSnapManager(exchange, market_type, symbols, normalizer, nats_publisher, config, metrics_collector)

            if exchange in ("okx", "okx_spot") and market_type == "spot":
                return OKXSpotSnapManager(exchange, market_type, symbols, normalizer, nats_publisher, config, metrics_collector)

            if exchange in ("okx", "okx_derivatives") and market_type in ("perpetual", "swap", "perp"):
                return OKXDerivativesSnapManager(exchange, market_type, symbols, normalizer, nats_publisher, config, metrics_collector)

            self.logger.error("Unsupported exchange/market for snapshot", exchange=exchange, market_type=market_type)
            return None
        except Exception as e:
            self.logger.error("Failed to create snapshot manager", error=str(e))
            return None

