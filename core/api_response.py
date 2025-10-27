"""
统一的API响应工具。

- success(data, message="Success", status=200)
- error(message, error_code="INTERNAL_ERROR", status=500, details=None)

保持与现有服务的字段一致性：status/message/data/error_code/timestamp
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime, timezone
from aiohttp import web


class APIResponse:
    """标准化 API 响应工具类"""

    @staticmethod
    def success(data: Any, message: str = "Success", status: int = 200) -> web.Response:
        return web.json_response(
            {
                "status": "success",
                "message": message,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status,
        )

    @staticmethod
    def error(
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status: int = 500,
        details: Optional[Any] = None,
    ) -> web.Response:
        return web.json_response(
            {
                "status": "error",
                "error_code": error_code,
                "message": message,
                "details": details,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status,
        )

