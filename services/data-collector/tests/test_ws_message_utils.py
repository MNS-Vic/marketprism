import pytest

from exchanges.common.ws_message_utils import (
    unwrap_combined_stream_message,
    is_trade_event,
)


def test_unwrap_combined_stream_message_returns_inner_data():
    msg = {"stream": "btcusdt@trade", "data": {"e": "trade", "x": 1}}
    assert unwrap_combined_stream_message(msg) == {"e": "trade", "x": 1}


def test_unwrap_combined_stream_message_passthrough_when_no_data():
    msg = {"stream": "btcusdt@trade", "payload": {"e": "trade"}}
    assert unwrap_combined_stream_message(msg) is msg


def test_is_trade_event_true_when_e_trade():
    assert is_trade_event({"e": "trade"}) is True


def test_is_trade_event_false_on_other():
    assert is_trade_event({"e": "aggTrade"}) is False
    assert is_trade_event({}) is False

