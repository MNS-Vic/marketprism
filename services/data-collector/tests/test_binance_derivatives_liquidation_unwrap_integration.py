import asyncio
import pytest

from collector.liquidation_managers.binance_derivatives_liquidation_manager_v2 import (
    BinanceDerivativesLiquidationManagerV2,
)


class _TestableBinanceDerivativesLiquidationManagerV2(BinanceDerivativesLiquidationManagerV2):
    async def _parse_liquidation_message(self, message: dict):  # abstract in base
        return None

    async def _subscribe_liquidation_data(self):  # abstract in base
        return None


class FakeNormalizer:
    def normalize_binance_liquidation(self, liquidation_data: dict):
        # Build a minimal object with required attributes used by _publish_to_nats
        class _NL:
            def __init__(self):
                self.exchange_name = "binance_derivatives"
                # Simulate enum-like with .value
                class _PT:
                    value = "perpetual"
                self.product_type = _PT()
                self.symbol_name = "BTC-USDT"
                self.instrument_id = liquidation_data.get("s", "BTCUSDT")
                self.liquidation_id = "test-liq-id"
                class _Side:
                    value = liquidation_data.get("S", "SELL")
                self.side = _Side()
                class _St:
                    value = "FILLED"
                self.status = _St()
                self.price = liquidation_data.get("p", "10000")
                self.quantity = liquidation_data.get("q", "0.01")
                self.filled_quantity = liquidation_data.get("l", "0.01")
                self.notional_value = "100"
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                self.liquidation_time = now
                self.timestamp = now
                self.collected_at = now
                # optional fields
                self.average_price = None
                self.margin_ratio = None
                self.bankruptcy_price = None
        return _NL()


class FakePublisher:
    def __init__(self):
        self.published = []

    async def publish_liquidation(self, exchange, market_type, symbol, liquidation_data):
        self.published.append(
            {
                "exchange": exchange,
                "market_type": market_type,
                "symbol": symbol,
                "data": liquidation_data,
            }
        )
        return True


@pytest.mark.asyncio
async def test_liquidation_v2_combined_stream_unwrap_and_process():
    normalizer = FakeNormalizer()
    publisher = FakePublisher()

    mgr = _TestableBinanceDerivativesLiquidationManagerV2(
        symbols=["BTCUSDT"], normalizer=normalizer, nats_publisher=publisher, config={}
    )

    # Simulate combined stream message
    message = {
        "stream": "!forceOrder@arr",
        "data": {
            "e": "forceOrder",
            "E": 1568014460893,
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",
                "o": "LIMIT",
                "f": "IOC",
                "q": "0.014",
                "p": "9910",
                "ap": "9910",
                "X": "FILLED",
                "l": "0.014",
                "z": "0.014",
                "T": 1568014460893,
            },
        },
    }

    # Directly call the processing method
    await mgr._process_all_market_liquidation(message)

    # Should have published exactly once for target symbol
    assert len(publisher.published) == 1
    pub = publisher.published[0]
    assert pub["exchange"] == "binance_derivatives"
    assert pub["market_type"] == "perpetual"
    assert pub["symbol"] == "BTC-USDT"
    assert pub["data"]["symbol"] == "BTC-USDT"

