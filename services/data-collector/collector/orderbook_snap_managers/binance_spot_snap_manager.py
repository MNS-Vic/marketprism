from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from .base_orderbook_snap_manager import BaseOrderBookSnapManager


class BinanceSpotSnapManager(BaseOrderBookSnapManager):
    """
    Binance Spot REST 快照管理器（GET /api/v3/depth）。

    要点：
    - 每个 1s tick 内对每个符号发起 REST GET 请求
    - 超时或错误时跳过本 tick，不降频
    - 使用 aiohttp 会话池复用连接
    """

    def __init__(
        self,
        exchange: str,
        market_type: str,
        symbols: List[str],
        normalizer: Any,
        nats_publisher: Any,
        config: Dict[str, Any],
        metrics_collector: Optional[Any] = None,
    ) -> None:
        super().__init__(exchange, market_type, symbols, normalizer, nats_publisher, config, metrics_collector)
        self.rest_base: str = (config or {}).get("rest_base") or "https://api.binance.com"
        self.request_timeout: float = float(self.config.get("request_timeout", min(0.9, self.snapshot_interval * 0.8)))
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> bool:
        # 创建 aiohttp 会话（复用连接）
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return await super().start()

    async def stop(self) -> None:
        await super().stop()
        if self._session:
            await self._session.close()
            self._session = None

    async def _fetch_one(self, symbol: str) -> None:
        if not self._session:
            self.logger.warning("会话未初始化，跳过", symbol=symbol)
            return

        url = f"{self.rest_base}/api/v3/depth"
        params = {"symbol": symbol, "limit": int(self.snapshot_depth)}
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.logger.warning("REST 快照请求失败", symbol=symbol, status=resp.status, body=text[:200])
                    return
                data = await resp.json()
                bids = data.get("bids") or []
                asks = data.get("asks") or []
                last_update_id = data.get("lastUpdateId")
                # Binance Spot REST 快照无事件时间，使用 None
                await self._normalize_and_publish(symbol, bids, asks, last_update_id=last_update_id, event_time_ms=None)
        except asyncio.TimeoutError:
            self.logger.warning("REST 快照超时，跳过", symbol=symbol, timeout=self.request_timeout)
        except Exception as e:
            self.logger.error("REST 快照异常", symbol=symbol, error=str(e))

