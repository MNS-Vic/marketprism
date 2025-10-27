from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed
from utils.json_compat import loads, dumps

from .base_orderbook_snap_manager import BaseOrderBookSnapManager


class BinanceDerivativesSnapManager(BaseOrderBookSnapManager):
    """
    Binance USDS-M Futures WS API 快照管理器（请求-响应模式，method=depth）。

    要点：
    - 单长连复用：所有符号共用一个 ws_api_url 连接
    - 每个 1s tick 内，对每个符号发送一条 depth 请求，使用 id 进行响应匹配
    - 重连：显式关闭旧连接后再重连；不降频
    - 正常化与发布：使用基类 _normalize_and_publish
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
        # WS API 入口，默认使用官方地址
        self.ws_api_url: str = (
            (config or {}).get("ws_api_url")
            or "wss://ws-fapi.binance.com/ws-fapi/v1"
        )

        # 连接与请求管理
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._recv_task: Optional[asyncio.Task] = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._next_id: int = int(time.time() * 1000)
        self._reconnect_attempts: int = 0

        # 超时与backoff
        self.request_timeout: float = float(self.config.get("request_timeout", min(0.9, self.snapshot_interval * 0.8)))
        self.max_reconnect_attempts: int = int(self.config.get("max_reconnect_attempts", -1))  # -1 表示无限
        self.backoff_initial: float = float(self.config.get("reconnect_initial_delay", 1.0))
        self.backoff_multiplier: float = float(self.config.get("reconnect_backoff", 2.0))
        self.backoff_max: float = float(self.config.get("reconnect_max_delay", 30.0))

    async def _fetch_one(self, symbol: str) -> None:
        # 确保连接可用
        if not await self._ensure_connection():
            self.logger.warning("WS API 未连接，跳过本tick", symbol=symbol)
            return

        req_id = self._next_request_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        try:
            payload = {
                "id": req_id,
                "method": "depth",
                "params": {"symbol": symbol, "limit": int(self.snapshot_depth)}
            }
            await self._send_json(payload)

            # 等待响应（超时则跳过本tick，不降频）
            try:
                resp = await asyncio.wait_for(fut, timeout=self.request_timeout)
            except asyncio.TimeoutError:
                self._pending.pop(req_id, None)
                self.logger.warning("WS API depth 响应超时，跳过", symbol=symbol, timeout=self.request_timeout)
                return

            # 解析并发布
            result = resp.get("result") if isinstance(resp, dict) else resp
            if not isinstance(result, dict):
                self.logger.error("WS API 响应格式异常", symbol=symbol)
                return
            bids = result.get("bids") or []
            asks = result.get("asks") or []
            last_update_id = result.get("lastUpdateId")
            event_time_ms = result.get("T") or result.get("E")  # 兜底：事件时间或服务器时间
            await self._normalize_and_publish(symbol, bids, asks, last_update_id=last_update_id, event_time_ms=event_time_ms)

        except ConnectionClosed as e:
            self.logger.error("WS 发送或等待期间连接关闭", symbol=symbol, code=getattr(e, 'code', None))
            await self._handle_connection_lost("send_or_wait_connection_closed")
        except Exception as e:
            self.logger.error("_fetch_one异常", symbol=symbol, error=str(e))
        finally:
            # 清理pending
            self._pending.pop(req_id, None)

    async def _send_json(self, obj: Dict[str, Any]) -> None:
        data = dumps(obj)
        # websockets 允许并发send，但为稳妥起见串行化
        async with self._send_lock:
            await self._ws.send(data)

    def _next_request_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _is_ws_open(self) -> bool:
        """检查 WebSocket 连接是否打开（兼容 websockets 12+）"""
        if not self._ws:
            return False
        # websockets 12+ 使用 close_code 判断，None 表示未关闭
        try:
            return getattr(self._ws, 'close_code', None) is None
        except Exception:
            # 回退：若有 closed 属性则使用
            return not getattr(self._ws, 'closed', True)

    async def _ensure_connection(self) -> bool:
        if self._is_ws_open():
            return True
        async with self._ws_lock:
            if self._is_ws_open():
                return True
            await self._close_ws()
            try:
                self.logger.info("🔗 连接Binance WS API", url=self.ws_api_url)
                # Binance 建议禁用客户端自动 ping，服务端会发PING（若有）。
                self._ws = await websockets.connect(
                    self.ws_api_url,
                    max_queue=512,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=10,
                )
                self._reconnect_attempts = 0
                # 启动接收循环
                self._recv_task = asyncio.create_task(self._recv_loop())
                self.logger.info("✅ WS API 连接成功")
                return True
            except Exception as e:
                self.logger.error("❌ WS API 连接失败", error=str(e))
                await self._schedule_reconnect()
                return False

    async def _recv_loop(self) -> None:
        try:
            while True:
                msg = await self._ws.recv()
                try:
                    data = loads(msg)
                except Exception as je:
                    self.logger.error("WS API JSON解析失败", error=str(je))
                    continue

                # 请求-响应匹配
                req_id = data.get("id") if isinstance(data, dict) else None
                if req_id is not None:
                    fut = self._pending.pop(req_id, None)
                    if fut and not fut.done():
                        # 错误响应
                        if "code" in data and "msg" in data:
                            fut.set_exception(Exception(f"Binance WS-API error {data['code']}: {data['msg']}"))
                        else:
                            fut.set_result(data)
                    continue

                # 非请求响应型消息（忽略或后续扩展）
                self.logger.debug("收到非响应消息", sample=str(data)[:200])
        except asyncio.CancelledError:
            pass
        except ConnectionClosed as e:
            self.logger.warning("WS API 读循环连接关闭", code=getattr(e, 'code', None))
            await self._handle_connection_lost("recv_connection_closed")
        except Exception as e:
            self.logger.error("WS API 读循环异常", error=str(e))
            await self._handle_connection_lost("recv_loop_exception")
        finally:
            # 将所有未完成请求置为异常，避免悬挂
            for _, fut in list(self._pending.items()):
                if not fut.done():
                    fut.set_exception(Exception("connection_lost"))
            self._pending.clear()

    async def _handle_connection_lost(self, reason: str) -> None:
        self.logger.warning("处理连接丢失，准备重连", reason=reason)
        await self._close_ws()
        await self._schedule_reconnect()

    async def _schedule_reconnect(self) -> None:
        # 固定 1s 频率不变，这里只负责连接重试，不影响tick
        if self.max_reconnect_attempts >= 0 and self._reconnect_attempts >= self.max_reconnect_attempts:
            self.logger.error("达到最大重连次数，停止重连")
            return
        delay = min(self.backoff_initial * (self.backoff_multiplier ** self._reconnect_attempts), self.backoff_max)
        self._reconnect_attempts += 1

        # Record reconnection metric
        if self.metrics:
            self.metrics.snapshot_reconnections_total.labels(
                exchange=self.exchange,
                market_type=self.market_type
            ).inc()

        self.logger.info("计划重连", delay=delay, attempts=self._reconnect_attempts)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        await self._ensure_connection()

    async def _close_ws(self) -> None:
        # 先取消接收任务
        if self._recv_task:
            try:
                self._recv_task.cancel()
                await self._recv_task
            except Exception:
                pass
            self._recv_task = None
        # 再关闭连接
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
