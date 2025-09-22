from __future__ import annotations
# Re-exported policy module relocated here.
# Original: services/data-collector/collector/ws_policy.py

import asyncio
import time
from typing import Any, Dict, Optional, Tuple

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Gauge
    PROM_AVAILABLE = True
except Exception:
    PROM_AVAILABLE = False
    Counter = None  # type: ignore
    Gauge = None    # type: ignore

# Text heartbeat metrics
if PROM_AVAILABLE:
    WS_TEXT_PINGS_TOTAL = Counter('marketprism_ws_text_pings_total', 'Total number of text ping messages sent to exchange', ['exchange'])
    WS_TEXT_PONGS_TOTAL = Counter('marketprism_ws_text_pongs_total', 'Total number of text pong messages received from exchange', ['exchange'])
    WS_PONG_TIMEOUTS_TOTAL = Counter('marketprism_ws_pong_timeouts_total', 'Total number of text pong timeouts', ['exchange'])
    WS_LAST_INBOUND_TS = Gauge('marketprism_ws_last_inbound_timestamp', 'Unix timestamp of last inbound message', ['exchange'])
    WS_LAST_OUTBOUND_PING_TS = Gauge('marketprism_ws_last_outbound_ping_timestamp', 'Unix timestamp of last outbound text ping', ['exchange'])


def get_ws_policy(exchange: str) -> Dict[str, Any]:
    ex = (exchange or '').lower()
    if ex.startswith('okx'):
        return {
            'connect_kwargs': {
                'ping_interval': None,
                'ping_timeout': None,
                'close_timeout': 10,
            },
            'jitter_range': (0.2, 0.8),
            'use_text_ping': True,
            'heartbeat_interval': 25,
            'outbound_ping_interval': 15,
            'pong_timeout': 15,
            'heartbeat_check_interval': 5,
        }
    return {
        'connect_kwargs': {
            'ping_interval': 20,
            'ping_timeout': 10,
            'close_timeout': 10,
        },
        'jitter_range': (0.2, 0.8),
        'use_text_ping': False,
        'heartbeat_interval': 20,
        'outbound_ping_interval': 0,
        'pong_timeout': 10,
        'heartbeat_check_interval': 5,
    }


class TextHeartbeatRunner:
    def __init__(self, logger, heartbeat_interval: int = 25, outbound_ping_interval: int = 15, pong_timeout: int = 15, check_interval: int = 5, exchange_label: str = "unknown", ping_pong_verbose: bool = False) -> None:
        self.logger = logger
        self.heartbeat_interval = heartbeat_interval
        self.outbound_ping_interval = outbound_ping_interval
        self.pong_timeout = pong_timeout
        self.check_interval = check_interval
        self.exchange_label = exchange_label
        self.ping_pong_verbose = ping_pong_verbose

        self.websocket = None
        self._task: Optional[asyncio.Task] = None
        self._running_flag_cb = None

        self.last_message_time = 0.0
        self.last_outbound_time = 0.0
        self.waiting_for_pong = False
        self.ping_sent_time = 0.0
        self.total_pings_sent = 0
        self.total_pongs_received = 0

    def bind(self, websocket, running_flag_cb) -> None:
        self.websocket = websocket
        self._running_flag_cb = running_flag_cb
        now = time.time()
        self.last_message_time = now
        self.last_outbound_time = 0.0
        self.waiting_for_pong = False

    def start(self) -> None:
        if not self._task:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    def handle_incoming(self, message: Any) -> bool:
        if isinstance(message, str) and message == 'pong':
            self.total_pongs_received += 1
            self.waiting_for_pong = False
            if PROM_AVAILABLE:
                WS_TEXT_PONGS_TOTAL.labels(exchange=self.exchange_label).inc()
            if self.logger:
                if getattr(self, 'ping_pong_verbose', False):
                    self.logger.info("💚 收到文本pong", total_pongs=self.total_pongs_received)
                else:
                    self.logger.debug("💚 收到文本pong", total_pongs=self.total_pongs_received)
            return True
        self.last_message_time = time.time()
        if PROM_AVAILABLE:
            WS_LAST_INBOUND_TS.labels(exchange=self.exchange_label).set(self.last_message_time)
        return False

    def notify_inbound(self) -> None:
        self.last_message_time = time.time()
        if PROM_AVAILABLE:
            WS_LAST_INBOUND_TS.labels(exchange=self.exchange_label).set(self.last_message_time)

    async def _loop(self) -> None:
        try:
            while True:
                if self._running_flag_cb and not self._running_flag_cb():
                    await asyncio.sleep(self.check_interval)
                    continue
                if not self.websocket:
                    await asyncio.sleep(self.check_interval)
                    continue

                now = time.time()
                try:
                    need_ping = False
                    if now - self.last_message_time > self.heartbeat_interval and not self.waiting_for_pong:
                        need_ping = True
                    elif (self.outbound_ping_interval > 0 and now - self.last_outbound_time > self.outbound_ping_interval and not self.waiting_for_pong):
                        need_ping = True

                    if need_ping:
                        await self.websocket.send('ping')
                        self.waiting_for_pong = True
                        self.ping_sent_time = now
                        self.total_pings_sent += 1
                        self.last_outbound_time = now
                        if PROM_AVAILABLE:
                            WS_TEXT_PINGS_TOTAL.labels(exchange=self.exchange_label).inc()
                            WS_LAST_OUTBOUND_PING_TS.labels(exchange=self.exchange_label).set(now)
                        if self.logger:
                            if getattr(self, 'ping_pong_verbose', False):
                                self.logger.info("💓 发送文本ping", total_pings=self.total_pings_sent)
                            else:
                                self.logger.debug("💓 发送文本ping", total_pings=self.total_pings_sent)

                    if self.waiting_for_pong and (now - self.ping_sent_time > self.pong_timeout):
                        if PROM_AVAILABLE:
                            WS_PONG_TIMEOUTS_TOTAL.labels(exchange=self.exchange_label).inc()
                        if self.logger:
                            self.logger.warning("💔 文本pong超时", timeout=f"{now - self.ping_sent_time:.1f}s")
                        self.waiting_for_pong = False

                except Exception as e:
                    if self.logger:
                        self.logger.warning("心跳循环异常", error=str(e))

                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            return

