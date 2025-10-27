from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import structlog

from collector.data_types import PriceLevel


class BaseOrderBookSnapManager(ABC):
    """
    Snapshot manager base class.

    Responsibilities:
    - lifecycle (start/stop)
    - fixed 1-second tick scheduling (no phase staggering)
    - per-symbol fetch via _fetch_one(symbol)
    - normalization + publish helper hooks
    - minimal metrics/log hooks (logger only for now)
    
    Notes:
    - Frequency is fixed to 1s (by config). We will NOT auto downscale interval.
    - If previous request for a symbol hasn't completed, we skip this tick for that symbol
      to avoid request piling.
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
        self.exchange = exchange
        self.market_type = market_type
        self.symbols = list(symbols)
        self.normalizer = normalizer
        self.nats = nats_publisher
        self.config = config or {}
        self.metrics = metrics_collector

        self.logger = structlog.get_logger(f"snap_manager:{exchange}:{market_type}")
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._inflight: Dict[str, asyncio.Task] = {}

        # Config with safe defaults (fixed 1s/100 depth per product requirement)
        self.snapshot_interval: float = float(self.config.get("snapshot_interval", 1))
        # depth used for fetching (subclasses should honor when calling API)
        self.snapshot_depth: int = int(self.config.get("snapshot_depth", self.config.get("depth_limit", 100)))

    async def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self.logger.info("Starting snapshot manager", symbols=self.symbols, interval=self.snapshot_interval, depth=self.snapshot_depth)
        self._loop_task = asyncio.create_task(self._fetch_loop())
        return True

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except Exception:
                pass
            self._loop_task = None

        # cancel inflight
        for sym, task in list(self._inflight.items()):
            if not task.done():
                task.cancel()
        self._inflight.clear()
        self.logger.info("Snapshot manager stopped")

    async def _fetch_loop(self) -> None:
        next_ts = time.monotonic()
        try:
            while self._running:
                next_ts += self.snapshot_interval
                for sym in self.symbols:
                    # Skip if previous tick still in-flight for this symbol
                    t = self._inflight.get(sym)
                    if t and not t.done():
                        # Skipping prevents piling
                        continue
                    self._inflight[sym] = asyncio.create_task(self._safe_fetch_one(sym))
                # precise sleep to align to ticks
                await asyncio.sleep(max(0.0, next_ts - time.monotonic()))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error("Snapshot fetch loop error", error=str(e))
        finally:
            # cleanup inflight
            for sym, task in list(self._inflight.items()):
                if not task.done():
                    task.cancel()
            self._inflight.clear()

    async def _safe_fetch_one(self, symbol: str) -> None:
        start_time = time.time()
        status = "success"
        try:
            await self._fetch_one(symbol)
        except asyncio.TimeoutError:
            status = "timeout"
            if self.metrics:
                self.metrics.snapshot_timeouts_total.labels(
                    exchange=self.exchange,
                    market_type=self.market_type,
                    symbol=symbol
                ).inc()
                #
                self.metrics.collector_errors_total.labels(
                    exchange=self.exchange,
                    data_type='orderbook_snapshot',
                    code='timeout'
                ).inc()
            self.logger.warning("fetch_one timeout", symbol=symbol)
        except asyncio.CancelledError:
            status = "cancelled"
            pass
        except Exception as e:
            status = "error"
            if self.metrics:
                self.metrics.collector_errors_total.labels(
                    exchange=self.exchange,
                    data_type='orderbook_snapshot',
                    code='exception'
                ).inc()
            self.logger.error("fetch_one failed", symbol=symbol, error=str(e))
        finally:
            # Record metrics
            if self.metrics:
                duration = time.time() - start_time
                self.metrics.snapshot_request_duration_seconds.labels(
                    exchange=self.exchange,
                    market_type=self.market_type,
                    symbol=symbol
                ).observe(duration)

                self.metrics.snapshot_requests_total.labels(
                    exchange=self.exchange,
                    market_type=self.market_type,
                    symbol=symbol,
                    status=status
                ).inc()

            # allow next tick to schedule
            self._inflight.pop(symbol, None)

    @abstractmethod
    async def _fetch_one(self, symbol: str) -> None:
        """
        Fetch one snapshot for the given symbol, and call self._normalize_and_publish(...)
        Subclasses must implement the fetching logic (REST or WS API request/response).
        """
        raise NotImplementedError

    async def _normalize_and_publish(
        self,
        symbol: str,
        bids: Iterable[Iterable[str | float | int]],
        asks: Iterable[Iterable[str | float | int]],
        last_update_id: Optional[int] = None,
        event_time_ms: Optional[int] = None,
    ) -> None:
        try:
            # 将原始 [[price, qty], ...] 转换为 PriceLevel 对象列表
            bid_levels = [
                PriceLevel(price=Decimal(str(level[0])), quantity=Decimal(str(level[1])))
                for level in bids
            ]
            ask_levels = [
                PriceLevel(price=Decimal(str(level[0])), quantity=Decimal(str(level[1])))
                for level in asks
            ]

            eob = self.normalizer.normalize_enhanced_orderbook_from_snapshot(
                exchange=self.exchange,
                symbol=symbol,
                bids=bid_levels,
                asks=ask_levels,
                market_type=self.market_type,
                last_update_id=last_update_id,
            )
            await self.nats.publish_enhanced_orderbook(eob)

            # Metrics on successful publish
            if getattr(self, 'metrics', None):
                try:
                    # 通用订单簿更新指标
                    self.metrics.orderbook_updates_total.labels(
                        exchange=self.exchange,
                        symbol=symbol
                    ).inc()
                    self.metrics.last_orderbook_update_timestamp.labels(
                        exchange=self.exchange,
                        symbol=symbol
                    ).set_to_current_time()
                    # 采集成功时间（按数据类型）
                    self.metrics.collector_last_success_timestamp_seconds.labels(
                        exchange=self.exchange,
                        data_type='orderbook_snapshot'
                    ).set(time.time())
                except Exception:
                    # 指标异常不影响主流程
                    pass
        except Exception as e:
            self.logger.error("normalize/publish failed", symbol=symbol, error=str(e))

    @property
    def is_running(self) -> bool:
        """兼容性属性：返回运行状态"""
        return self._running

