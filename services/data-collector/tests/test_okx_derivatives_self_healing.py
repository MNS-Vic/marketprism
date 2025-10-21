import asyncio
import time
import types
import pytest
from unittest.mock import AsyncMock

#    
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from collector.orderbook_managers.okx_derivatives_manager import OKXDerivativesOrderBookManager


class DummyNormalizer:
    def normalize_orderbook(self, **kwargs):
        return kwargs


class DummyPublisher:
    async def publish_orderbook(self, exchange, market_type, symbol, normalized_data):
        return True


@pytest.mark.asyncio
async def test_update_before_snapshot_triggers_resubscribe(monkeypatch):
    symbol = "BTC-USDT-SWAP"
    config = {
        "buffer_timeout": 0.1,  # 短超时，便于测试
    }
    mgr = OKXDerivativesOrderBookManager(
        exchange="okx",
        market_type="perpetual",
        symbols=[symbol],
        normalizer=DummyNormalizer(),
        nats_publisher=DummyPublisher(),
        config=config,
    )

    # 注入 fake ws client
    fake_client = types.SimpleNamespace(
        unsubscribe_orderbook=AsyncMock(return_value=None),
        subscribe_orderbook=AsyncMock(return_value=None),
    )
    mgr.okx_ws_client = fake_client

    await mgr.initialize_orderbook_states()

    # 发送两次 update（无快照），间隔超过阈值，第二次应触发重订阅
    update_msg = {
        "action": "update",
        "bids": [["50000", "1"]],
        "asks": [["50010", "1"]],
        "prevSeqId": 0,
        "seqId": 1,
        "ts": str(int(time.time() * 1000)),
    }

    await mgr.process_websocket_message(symbol, update_msg)
    await asyncio.sleep(0.25)  # > 2*buffer_timeout
    await mgr.process_websocket_message(symbol, update_msg)

    assert fake_client.unsubscribe_orderbook.await_count >= 1
    assert fake_client.subscribe_orderbook.await_count >= 1


@pytest.mark.asyncio
async def test_snapshot_clears_waiting_flag(monkeypatch):
    symbol = "BTC-USDT-SWAP"
    config = {"buffer_timeout": 0.1}
    mgr = OKXDerivativesOrderBookManager(
        exchange="okx",
        market_type="perpetual",
        symbols=[symbol],
        normalizer=DummyNormalizer(),
        nats_publisher=DummyPublisher(),
        config=config,
    )

    await mgr.initialize_orderbook_states()
    # 先模拟等待中
    mgr.waiting_for_snapshot_since[symbol] = time.time()

    snapshot_msg = {
        "action": "snapshot",
        "bids": [["50000", "1"]],
        "asks": [["50010", "1"]],
        "prevSeqId": -1,
        "seqId": 2,
        "ts": str(int(time.time() * 1000)),
    }

    await mgr.process_websocket_message(symbol, snapshot_msg)

    assert mgr.waiting_for_snapshot_since.get(symbol) is None

