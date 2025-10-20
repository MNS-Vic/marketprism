from __future__ import annotations
# Re-exported policy module relocated here.
# Original: services/data-collector/collector/ws_policy.py

import asyncio
import time
from typing import Any, Dict, Optional, Tuple
import json

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Gauge
    PROM_AVAILABLE = True
except Exception:
    PROM_AVAILABLE = False
    Counter = None  # type: ignore
    Gauge = None    # type: ignore

# Text heartbeat metrics (add per-channel dimension)
if PROM_AVAILABLE:
    WS_TEXT_PINGS_TOTAL = Counter(
        'marketprism_ws_text_pings_total',
        'Total number of text ping messages sent to exchange/channel',
        ['exchange', 'channel']
    )
    WS_TEXT_PONGS_TOTAL = Counter(
        'marketprism_ws_text_pongs_total',
        'Total number of text pong messages received from exchange/channel',
        ['exchange', 'channel']
    )
    WS_PONG_TIMEOUTS_TOTAL = Counter(
        'marketprism_ws_pong_timeouts_total',
        'Total number of text pong timeouts per exchange/channel',
        ['exchange', 'channel']
    )
    WS_LAST_INBOUND_TS = Gauge(
        'marketprism_ws_last_inbound_timestamp',
        'Unix timestamp of last inbound message per exchange/channel',
        ['exchange', 'channel']
    )
    WS_LAST_OUTBOUND_PING_TS = Gauge(
        'marketprism_ws_last_outbound_ping_timestamp',
        'Unix timestamp of last outbound text ping per exchange/channel',
        ['exchange', 'channel']
    )
    WS_IMPLIED_PONGS_TOTAL = Counter(
        'marketprism_ws_implied_pongs_total',
        'Total number of implied pongs (inbound activity while waiting) per exchange/channel',
        ['exchange', 'channel']
    )



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
            'outbound_ping_interval': 20,
            'pong_timeout': 10,
            'heartbeat_check_interval': 2,
        }
    # 🔧 修复：Binance 心跳策略（服务器主动PING，客户端被动响应）
    # 根据 Binance 官方文档：
    # - WebSocket 服务器每20秒发送 PING 消息
    # - 客户端必须在1分钟内响应 PONG，否则连接会被断开
    # - 客户端不应主动发送 PING（会导致连接异常关闭 1006）
    return {
        'connect_kwargs': {
            'ping_interval': None,  # 🔧 修复：禁用客户端主动PING（Binance服务器会主动发送）
            'ping_timeout': None,   # 🔧 修复：禁用超时检测（依赖服务器的1分钟超时）
            'close_timeout': 10,
        },
        'jitter_range': (0.2, 0.8),
        'use_text_ping': False,  # Binance使用WebSocket协议级别的PING/PONG帧
        'heartbeat_interval': 20,  # 服务器PING间隔（用于监控）
        'outbound_ping_interval': 0,  # 不主动发送PING
        'pong_timeout': 60,  # 🔧 修复：Binance允许60秒内响应（从10秒提高到60秒）
        'heartbeat_check_interval': 5,
    }


class TextHeartbeatRunner:
    def __init__(self, logger, heartbeat_interval: int = 25, outbound_ping_interval: int = 15, pong_timeout: int = 15, check_interval: int = 5, exchange_label: str = "unknown", ping_pong_verbose: bool = False, channel_label: str = "unknown") -> None:
        self.logger = logger
        self.heartbeat_interval = heartbeat_interval
        self.outbound_ping_interval = outbound_ping_interval
        self.pong_timeout = pong_timeout
        self.check_interval = check_interval
        self.exchange_label = exchange_label
        self.channel_label = channel_label
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
        """
        统一处理入站心跳：
        - 文本 'pong'：标记收到PONG
        - 文本 'ping'：立即异步回复 'pong'
        - JSON {'op': 'pong'|'ping'} 或 {'event': 'ping'}：兼容OKX可能的JSON心跳形式
        该方法为同步函数，主动发送操作通过 asyncio.create_task 调度。
        """
        # 记录入站时间
        self.last_message_time = time.time()
        if PROM_AVAILABLE:
            WS_LAST_INBOUND_TS.labels(exchange=self.exchange_label, channel=self.channel_label).set(self.last_message_time)

        # bytes/binary -> 尝试解码为utf-8再按文本处理
        if isinstance(message, (bytes, bytearray)):
            try:
                message = message.decode('utf-8', errors='ignore')
            except Exception:
                message = ''

        # 1) 纯文本处理
        if isinstance(message, str):
            msg_str = message.strip()
            low = msg_str.lower()
            if low == 'pong':
                self.total_pongs_received += 1
                self.waiting_for_pong = False
                if PROM_AVAILABLE:
                    WS_TEXT_PONGS_TOTAL.labels(exchange=self.exchange_label, channel=self.channel_label).inc()
                if self.logger:
                    if getattr(self, 'ping_pong_verbose', False):
                        self.logger.info("💚 收到文本pong", total_pongs=self.total_pongs_received, channel=self.channel_label)
                    else:
                        self.logger.debug("💚 收到文本pong", total_pongs=self.total_pongs_received, channel=self.channel_label)
                return True
            if low == 'ping':
                # 服务器主动PING：异步回复PONG
                if self.logger and getattr(self, 'ping_pong_verbose', False):
                    self.logger.info("💓 收到文本ping，自动回复pong", channel=self.channel_label)
                if self.websocket:
                    try:
                        asyncio.create_task(self.websocket.send('pong'))
                    except Exception:
                        pass
                return True
            # JSON字符串（可能包含 op/event）
            if msg_str.startswith('{') and msg_str.endswith('}'):
                try:
                    obj = json.loads(msg_str)
                except Exception:
                    obj = None
                if isinstance(obj, dict):
                    op = str(obj.get('op', '') or obj.get('event', '')).lower()
                    if op == 'pong':
                        self.total_pongs_received += 1
                        self.waiting_for_pong = False
                        if PROM_AVAILABLE:
                            WS_TEXT_PONGS_TOTAL.labels(exchange=self.exchange_label, channel=self.channel_label).inc()
                        if self.logger and getattr(self, 'ping_pong_verbose', False):
                            self.logger.info("💚 收到JSON pong", total_pongs=self.total_pongs_received, channel=self.channel_label)
                        return True
                    if op == 'ping':
                        if self.logger and getattr(self, 'ping_pong_verbose', False):
                            self.logger.info("💓 收到JSON ping，自动回复JSON pong", channel=self.channel_label)
                        resp = {'op': 'pong'}
                        if 'ts' in obj:
                            resp['ts'] = obj['ts']
                        if self.websocket:
                            try:
                                asyncio.create_task(self.websocket.send(json.dumps(resp)))
                            except Exception:
                                pass
                        return True
        return False
    def notify_inbound(self) -> None:
        self.last_message_time = time.time()
        if PROM_AVAILABLE:
            WS_LAST_INBOUND_TS.labels(exchange=self.exchange_label, channel=self.channel_label).set(self.last_message_time)
        # 隐式pong：在等待文本pong且仍在超时窗口内，任意入站视为pong
        now = self.last_message_time
        if self.waiting_for_pong and (now - self.ping_sent_time) <= self.pong_timeout:
            self.total_pongs_received += 1
            self.waiting_for_pong = False
            if PROM_AVAILABLE:
                WS_IMPLIED_PONGS_TOTAL.labels(exchange=self.exchange_label, channel=self.channel_label).inc()
            if self.logger and getattr(self, 'ping_pong_verbose', False):
                self.logger.info("💚 收到隐式pong（入站活动）", channel=self.channel_label)

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
                            WS_TEXT_PINGS_TOTAL.labels(exchange=self.exchange_label, channel=self.channel_label).inc()
                            WS_LAST_OUTBOUND_PING_TS.labels(exchange=self.exchange_label, channel=self.channel_label).set(now)
                        if self.logger:
                            if getattr(self, 'ping_pong_verbose', False):
                                self.logger.info("💓 发送文本ping", total_pings=self.total_pings_sent, channel=self.channel_label)
                            else:
                                self.logger.debug("💓 发送文本ping", total_pings=self.total_pings_sent, channel=self.channel_label)

                    if self.waiting_for_pong and (now - self.ping_sent_time > self.pong_timeout):
                        if PROM_AVAILABLE:
                            WS_PONG_TIMEOUTS_TOTAL.labels(exchange=self.exchange_label, channel=self.channel_label).inc()
                        if self.logger:
                            self.logger.warning("💔 文本pong超时", timeout=f"{now - self.ping_sent_time:.1f}s", channel=self.channel_label)
                        self.waiting_for_pong = False

                except Exception as e:
                    if self.logger:
                        self.logger.warning("心跳循环异常", error=str(e))

                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            return

