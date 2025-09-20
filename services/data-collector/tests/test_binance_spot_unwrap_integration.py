import asyncio
import time
import pytest

from collector.trades_managers.binance_spot_trades_manager import BinanceSpotTradesManager


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish_data(self, data_type, exchange, market_type, symbol, data):
        self.calls.append({
            'data_type': data_type,
            'exchange': exchange,
            'market_type': market_type,
            'symbol': symbol,
            'data': data,
        })
        return True


@pytest.mark.asyncio
async def test_binance_spot_process_trade_message_with_combined_wrapper():
    fake_pub = FakePublisher()
    # 正常无需 normalizer，Base 会走原始数据路径
    mgr = BinanceSpotTradesManager(symbols=["BTCUSDT"], normalizer=None, nats_publisher=fake_pub, config={})

    combined = {
        "stream": "btcusdt@trade",
        "data": {
            "e": "trade",
            "E": 1672515782136,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "42000.50",
            "q": "0.001",
            "T": int(time.time() * 1000),
            "m": False,
            "M": True
        }
    }

    await mgr._process_trade_message(combined)

    # 发布被调用一次
    assert len(fake_pub.calls) == 1
    call = fake_pub.calls[0]

    # 关键信息正确
    assert call['data_type'] == 'trade'
    assert call['exchange'] == 'binance_spot'
    assert call['market_type'] == 'spot'
    # 无 normalizer 情况下，subject 使用原始 symbol
    assert call['symbol'] == 'BTCUSDT'
    payload = call['data']
    assert payload['symbol'] == 'BTCUSDT'
    assert payload['trade_id'] == '12345'
    assert payload['price'] == '42000.50'
    assert payload['quantity'] == '0.001'

