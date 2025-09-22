import pytest

from exchanges.common.ws_message_utils import unwrap_combined_stream_message


def test_okx_trades_message_noop_when_data_is_list():
    # OKX常见结构：data为list，不应该被unwrap处理
    msg = {
        "arg": {"channel": "trades", "instId": "BTC-USDT"},
        "data": [
            {"tradeId": "1", "px": "100", "sz": "0.01", "side": "buy", "ts": "1700000000000"}
        ]
    }
    out = unwrap_combined_stream_message(msg)
    assert out is msg  # 应保持引用不变（未被解包）


def test_okx_orderbook_message_noop_plain_fields():
    # OKX WebSocket管理器可能已将消息扁平化为action/bids/asks
    msg = {
        "action": "update",
        "seqId": 123,
        "prevSeqId": 122,
        "bids": [["100", "1"]],
        "asks": [["101", "2"]],
        "ts": "1700000000100"
    }
    out = unwrap_combined_stream_message(msg)
    assert out is msg


def test_hypothetical_wrapped_okx_message_should_unwrap_dict_inner():
    # 假设未来OKX也采用外层包裹：{"data": {"action": "update", ...}}
    inner = {
        "action": "update",
        "seqId": 200,
        "prevSeqId": 199,
        "bids": [["100", "1"]],
        "asks": [["101", "2"]],
        "ts": "1700000000200"
    }
    wrapped = {"data": inner}
    out = unwrap_combined_stream_message(wrapped)
    assert out == inner

