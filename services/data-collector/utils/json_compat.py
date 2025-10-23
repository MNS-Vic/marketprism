"""
轻量 JSON 兼容层：优先使用 orjson，其次 ujson，最后回退到标准库 json。
- 提供 loads、dumps、JSONDecodeError 三个符号，方便等价替换。
- dumps 返回 str（对于 orjson -> bytes 会自动解码为 UTF-8）。
- 兼容 Decimal 序列化（默认转 float）。
"""
from __future__ import annotations

from typing import Any
import decimal as _decimal


def _default(obj: Any):
    """默认的对象序列化器：兼容 Decimal -> float。"""
    if isinstance(obj, _decimal.Decimal):
        return float(obj)
    # 交给调用方/底层库决定是否报错
    raise TypeError(f"Type is not JSON serializable: {type(obj).__name__}")


# 优先 orjson（高性能、低内存）
try:
    import orjson as _orjson  # type: ignore

    def loads(s: Any) -> Any:
        return _orjson.loads(s)

    def dumps(obj: Any) -> str:
        # orjson.dumps 返回 bytes，需解码为 str 以保持原调用方语义
        return _orjson.dumps(obj, default=_default).decode("utf-8")

    JSONDecodeError = _orjson.JSONDecodeError  # noqa: N816

except Exception:  # pragma: no cover - 回退路径
    # 次选 ujson（如未安装则继续回退）
    try:
        import ujson as _ujson  # type: ignore

        def loads(s: Any) -> Any:  # type: ignore[no-redef]
            return _ujson.loads(s)

        def _convert(o: Any):
            # 递归转换常见容器内的 Decimal
            if isinstance(o, _decimal.Decimal):
                return float(o)
            if isinstance(o, dict):
                return {k: _convert(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [ _convert(v) for v in o ]
            return o

        def dumps(obj: Any) -> str:  # type: ignore[no-redef]
            return _ujson.dumps(_convert(obj))

        # ujson 抛 ValueError
        JSONDecodeError = ValueError  # type: ignore[assignment]

    except Exception:  # 最后回退到标准库 json
        import json as _json  # type: ignore

        def loads(s: Any) -> Any:  # type: ignore[no-redef]
            return _json.loads(s)

        def dumps(obj: Any) -> str:  # type: ignore[no-redef]
            return _json.dumps(obj, default=_default, ensure_ascii=False)

        JSONDecodeError = _json.JSONDecodeError  # type: ignore[assignment]

__all__ = ["loads", "dumps", "JSONDecodeError"]

