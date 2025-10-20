from __future__ import annotations
# Re-exported adapter module relocated here.
# Original: services/data-collector/collector/ws_policy_adapter.py

from typing import Any, Dict, Optional
from .ws_policy import get_ws_policy, TextHeartbeatRunner

class WSPolicyContext:
    """统一策略上下文容器（exchanges/policies）。"""
    def __init__(self, exchange: str, logger, config: dict, channel: Optional[str] = None):
        self.exchange = (exchange or '').lower()
        self.channel = (channel or 'unknown').lower()
        self.policy = get_ws_policy(self.exchange)
        self.logger = logger
        self.config = config or {}
        self.ws_connect_kwargs: Dict[str, Any] = self.policy['connect_kwargs']
        self.use_text_ping: bool = self.policy['use_text_ping']
        self.heartbeat: Optional[TextHeartbeatRunner] = None

        if self.use_text_ping:
            obs_cfg = (self.config.get('system', {}).get('observability', {}) if isinstance(self.config, dict) else {})
            ping_pong_verbose = bool(obs_cfg.get('ping_pong_verbose', False))
            self.heartbeat = TextHeartbeatRunner(
                logger=self.logger,
                heartbeat_interval=self.config.get('heartbeat_interval', self.policy['heartbeat_interval']),
                outbound_ping_interval=self.config.get('outbound_ping_interval', self.policy['outbound_ping_interval']),
                pong_timeout=self.config.get('pong_timeout', self.policy['pong_timeout']),
                check_interval=self.policy['heartbeat_check_interval'],
                exchange_label=self.exchange,
                ping_pong_verbose=ping_pong_verbose,
                channel_label=self.channel,
            )

    def bind(self, websocket, running_flag_cb):
        if self.heartbeat:
            self.heartbeat.bind(websocket, running_flag_cb)

    def start_heartbeat(self):
        if self.heartbeat:
            self.heartbeat.start()

    async def stop_heartbeat(self):
        if self.heartbeat:
            await self.heartbeat.stop()

    def handle_incoming(self, message) -> bool:
        if self.heartbeat:
            return self.heartbeat.handle_incoming(message)
        return False

    def notify_inbound(self):
        if self.heartbeat:
            self.heartbeat.notify_inbound()

