import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from collector.vol_index_managers.base_vol_index_manager import BaseVolIndexManager


class DummyManager(BaseVolIndexManager):
    def __init__(self):
        super().__init__(exchange="deribit_derivatives", symbols=["BTC"], nats_publisher=None, config={
            "vol_index": {"timeout": 1, "max_retries": 2, "retry_delay": 0.1}
        })

    async def _fetch_vol_index_data(self, symbol: str):
        return None

    async def _normalize_data(self, symbol: str, raw_data):
        return None


class DummyResponse:
    def __init__(self, status: int, json_side_effect=None, json_value=None):
        self.status = status
        self._json_side_effect = json_side_effect
        self._json_value = json_value

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        if self._json_side_effect:
            raise self._json_side_effect
        return self._json_value


@pytest.mark.asyncio
async def test_http_request_non_json():
    mgr = DummyManager()
    # 模拟200但非JSON可解析
    # session.get 返回异步上下文管理器对象本身（非协程）
    mgr.session = MagicMock()
    mgr.session.closed = False
    mgr.session.get = MagicMock(return_value=DummyResponse(200, json_side_effect=ValueError("invalid json")))
    res = await mgr._make_http_request("http://example.com", {"a": 1})
    assert res is None  # 不崩溃，返回None


@pytest.mark.asyncio
async def test_http_request_429_retry(monkeypatch):
    mgr = DummyManager()
    calls = {"n": 0}

    def fake_get(url, params=None):
        calls["n"] += 1
        return DummyResponse(429, json_value=None)

    mgr.session = MagicMock()
    mgr.session.closed = False
    mgr.session.get = MagicMock(side_effect=lambda url, params=None: fake_get(url, params))

    res = await mgr._make_http_request("http://example.com", {})
    assert res is None
    # 至少尝试了多次（根据max_retries）
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_http_request_5xx_retry():
    mgr = DummyManager()
    calls = {"n": 0}

    def fake_get(url, params=None):
        calls["n"] += 1
        return DummyResponse(503, json_value=None)

    mgr.session = MagicMock()
    mgr.session.closed = False
    mgr.session.get = MagicMock(side_effect=lambda url, params=None: fake_get(url, params))

    res = await mgr._make_http_request("http://example.com", {})
    assert res is None
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_http_request_empty_body():
    mgr = DummyManager()

    async def fake_get(url, params=None):
        # 200 但空 body（json() 返回 None）
        return DummyResponse(200, json_value=None)

    mgr.session = MagicMock()
    mgr.session.get = AsyncMock(side_effect=lambda url, params=None: fake_get(url, params))

    res = await mgr._make_http_request("http://example.com", {})
    assert res is None

