"""
WebSocket 消息通用工具（交易所层）
- 统一处理交易所 combined streams 外层包裹结构，例如 Binance: {"stream": "btcusdt@trade", "data": {...}}
"""
from typing import Any, Dict


def unwrap_combined_stream_message(message: Any, inner_key: str = "data") -> Any:
    """如果消息是带有外层包裹的 combined streams 结构，则返回其内层数据。
    - 典型结构: {"stream": "...", "data": {...}}
    - 非 dict 或不含内层键时，原样返回
    """
    if isinstance(message, dict) and inner_key in message and isinstance(message.get(inner_key), dict):
        return message[inner_key]
    return message


def is_trade_event(message: Dict[str, Any]) -> bool:
    """简单判断是否为逐笔成交事件（基于通用字段 e == 'trade'）"""
    try:
        return isinstance(message, dict) and message.get("e") == "trade"
    except Exception:
        return False

