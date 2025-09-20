import pytest

from exchanges.common.ws_message_utils import unwrap_combined_stream_message


def test_deribit_subscription_message_passthrough():
    # Deribit 典型订阅推送：顶层为 jsonrpc/method/params，data 在 params 下
    msg = {
        "jsonrpc": "2.0",
        "method": "subscription",
        "params": {
            "channel": "trades.BTC-PERPETUAL.raw",
            "data": {
                "trade_seq": 123456,
                "trade_id": "ETH-123",
                "timestamp": 1700000000000,
                "price": 25000.5,
                "amount": 100.0,
                "direction": "sell"
            }
        }
    }
    out = unwrap_combined_stream_message(msg)
    # unwrap 只在顶层存在 data 且为 dict 时才解包；此处应保持原样
    assert out is msg

