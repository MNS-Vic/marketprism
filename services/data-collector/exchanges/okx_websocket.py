"""
OKX WebSocket客户端
基于OKX官方文档要求的专用WebSocket实现
支持OKX特有的心跳机制和重连策略，实现统一的WebSocket接口
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, Callable, List
import websockets

# 🔧 标准化导入路径 - 支持动态导入
import sys
from pathlib import Path

# 添加exchanges目录到Python路径以支持动态导入
exchanges_dir = Path(__file__).parent
if str(exchanges_dir) not in sys.path:
    sys.path.insert(0, str(exchanges_dir))
from core.observability.logging import get_managed_logger, ComponentType

from base_websocket import BaseWebSocketClient

from exchanges.policies.ws_policy_adapter import WSPolicyContext

class OKXWebSocketManager(BaseWebSocketClient):
    """
    OKX专用WebSocket管理器
    实现OKX官方文档要求的连接维护和重连机制
    """

    def __init__(self,
                 symbols: List[str],
                 on_orderbook_update: Callable[[str, Dict[str, Any]], None] = None,
                 ws_base_url: str = None,
                 market_type: str = 'spot',
                 websocket_depth: int = 400,
                 config: Optional[Dict[str, Any]] = None,
                 update_frequency: str = '100ms'):
        """
        初始化OKX WebSocket管理器

        Args:
            symbols: 交易对列表
            on_orderbook_update: 订单簿更新回调函数 (symbol, data)
            ws_base_url: WebSocket基础URL（已弃用，使用config）
            market_type: 市场类型 ('spot', 'perpetual')
            websocket_depth: WebSocket深度 (OKX最大400)
            config: 统一配置字典
            update_frequency: 更新频率 ('100ms', '400ms', '1000ms')
        """
        # 调用父类构造函数
        super().__init__(symbols, on_orderbook_update, market_type, min(websocket_depth, 400))

        # 🔧 迁移到统一日志系统
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

        from core.observability.metrics.unified_metrics_manager import get_global_manager
        from core.observability.metrics.metric_categories import MetricType, MetricCategory, MetricSubCategory

        self.logger = get_managed_logger(
            ComponentType.WEBSOCKET,
            exchange="okx",
            market_type=market_type
        )

        # 观测与指标
        self.config = config or {}
        # 配置可能在 system.observability 或直接在 observability 下
        self._observability_cfg = (
            self.config.get('system', {}).get('observability') or
            self.config.get('observability') or
            {}
        )
        self.ping_pong_log_enabled = bool(self._observability_cfg.get('ping_pong_verbose', False))
        self.metrics = get_global_manager()
        self._metric_labels = {"exchange": "okx", "market_type": market_type}
        # 注册/获取指标
        try:
            reg = self.metrics.registry
            reg.register_custom_metric(
                name="websocket_reconnects_total",
                metric_type=MetricType.COUNTER,
                category=MetricCategory.NETWORK,
                subcategory=MetricSubCategory.WEBSOCKET_CONN,
                description="Total WebSocket reconnections",
                labels=["exchange", "market_type"],
            )
            reg.register_custom_metric(
                name="websocket_heartbeat_pings_total",
                metric_type=MetricType.COUNTER,
                category=MetricCategory.NETWORK,
                subcategory=MetricSubCategory.WEBSOCKET_CONN,
                description="Total heartbeat pings sent",
                labels=["exchange", "market_type"],
            )
            reg.register_custom_metric(
                name="websocket_heartbeat_pongs_total",
                metric_type=MetricType.COUNTER,
                category=MetricCategory.NETWORK,
                subcategory=MetricSubCategory.WEBSOCKET_CONN,
                description="Total heartbeat pongs received",
                labels=["exchange", "market_type"],
            )
            reg.register_custom_metric(
                name="websocket_heartbeat_failures_total",
                metric_type=MetricType.COUNTER,
                category=MetricCategory.RELIABILITY,
                subcategory=MetricSubCategory.WEBSOCKET_CONN,
                description="Total heartbeat failures (timeouts)",
                labels=["exchange", "market_type"],
            )
        except Exception:
            # 注册失败不影响主流程
            pass

        # OKX特定配置
        self.update_frequency = update_frequency
        self._validate_update_frequency()

        # 🔧 配置统一：从统一配置获取WebSocket URL
        exchanges_config = self.config.get('exchanges', {})

        # 根据市场类型选择正确的配置
        if market_type == 'perpetual':
            okx_config = exchanges_config.get('okx_derivatives', {})
        else:
            okx_config = exchanges_config.get('okx_spot', {})

        # 优先使用统一配置，然后是传入参数，最后是默认值
        if ws_base_url:
            self.ws_base_url = ws_base_url
        else:
            self.ws_base_url = okx_config.get('api', {}).get('ws_url', "wss://ws.okx.com:8443/ws/v5/public")

        # 🔧 统一属性命名：添加ws_url别名以保持兼容性
        self.ws_url = self.ws_base_url

        # 统一策略上下文（用于 TextHeartbeatRunner 替换内建心跳）
        try:
            self._ws_ctx = WSPolicyContext('okx_'+market_type, self.logger, self.config)
        except Exception:
            self._ws_ctx = None
        # WebSocket连接管理
        self.websocket = None

        # 任务管理
        self.listen_task = None
        self.heartbeat_task = None
        self.reconnect_task = None

        # 🔧 OKX特有的心跳机制 - 严格按照官方文档要求
        self.last_message_time = 0
        self.last_ping_time = 0  # 上次发送ping的时间
        self.heartbeat_interval = 25  # 25秒发送ping（OKX要求30秒内必须有活动）
        self.pong_timeout = 10  # pong响应超时时间10秒
        self.heartbeat_check_interval = 5  # 每5秒检查一次心跳状态
        self.waiting_for_pong = False
        self.ping_sent_time = 0
        self.total_pings_sent = 0
        self.total_pongs_received = 0
        self.heartbeat_failures = 0
        self.consecutive_heartbeat_failures = 0  # 连续心跳失败次数
        self.max_consecutive_failures = 3  # 最大连续失败次数

        # 重连配置 - 符合OKX官方文档要求
        self.max_reconnect_attempts = -1  # 无限重连
        self.reconnect_delay = 1.0  # 初始重连延迟1秒
        self.max_reconnect_delay = 30.0  # 最大重连延迟30秒
        self.backoff_multiplier = 2.0  # 指数退避倍数
        self.current_reconnect_attempts = 0
        self.connection_timeout = 10.0  # 连接超时10秒

        # 统计信息
        self.total_messages = 0
        self.reconnect_count = 0
        self._summary_interval_sec = int(self._observability_cfg.get("ws_summary_interval_sec", 60))
        self._last_summary_ts = time.time()

        # 摘要与阈值
        self._summary_interval_sec = int(self._observability_cfg.get("ws_summary_interval_sec", 60))
        self._last_summary_ts = time.time()
        self._last_summary = {
            "pings": 0,
            "pongs": 0,
            "failures": 0,
            "reconnects": 0,
        }
        self._warn_reconnects = int(self._observability_cfg.get("warn_reconnects_per_interval", 1))
        self._warn_heartbeat_failures = int(self._observability_cfg.get("warn_heartbeat_failures_per_interval", 1))

        self.logger.info("🔧 OKX WebSocket管理器初始化完成",
                        symbols=symbols, market_type=market_type,
                        websocket_depth=self.websocket_depth,
                        update_frequency=self.update_frequency,
                        ws_url=self.ws_base_url,
                        ping_pong_verbose=self.ping_pong_log_enabled,
                        summary_interval_sec=self._summary_interval_sec)

    def _validate_update_frequency(self):
        """验证更新频率参数"""
        valid_frequencies = ['100ms', '400ms', '1000ms']
        if self.update_frequency not in valid_frequencies:
            self.logger.warning(f"⚠️ 无效的更新频率: {self.update_frequency}, 使用默认值100ms")
            self.update_frequency = '100ms'
        else:
            self.logger.info(f"📊 OKX订单簿更新频率设置为: {self.update_frequency}")

    async def start(self):
        """启动OKX WebSocket管理器（orderbook_manager期望的接口）"""
        try:
            self.logger.info("🚀 启动OKX WebSocket管理器",
                           symbols=self.symbols,
                           url=self.ws_base_url,
                           market_type=self.market_type)

            self.is_running = True

            # 🔧 修正：启动连接管理任务但不等待，避免阻塞启动流程
            self.reconnect_task = asyncio.create_task(self._connection_manager())

            # 🔧 修正：等待初始连接建立，但设置超时避免无限等待
            try:
                await asyncio.wait_for(self._wait_for_initial_connection(), timeout=10.0)
                self.logger.info("✅ OKX WebSocket初始连接建立成功")
            except asyncio.TimeoutError:
                self.logger.warning("⚠️ OKX WebSocket初始连接超时，将在后台继续尝试")

        except Exception:
            self.logger.error("OKX WebSocket管理器启动失败", exc_info=True)
            raise

    async def _wait_for_initial_connection(self):
        """等待初始连接建立"""
        while not self.is_connected:
            await asyncio.sleep(0.1)

    async def stop(self):
        """停止OKX WebSocket管理器"""
        self.logger.info("🛑 停止OKX WebSocket管理器")

        self.is_running = False

        # 停止所有任务
        if getattr(self, '_ws_ctx', None) and self._ws_ctx.heartbeat:
            try:
                await self._ws_ctx.stop_heartbeat()
            except Exception:
                pass
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()

        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()

        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()

        # 关闭WebSocket连接
        if self.websocket:
            try:
                # 安全检查连接状态 - 兼容不同WebSocket实现
                is_closed = False
                if hasattr(self.websocket, 'closed'):
                    is_closed = self.websocket.closed
                elif hasattr(self.websocket, 'close_code'):
                    # aiohttp ClientWebSocketResponse使用close_code判断
                    is_closed = self.websocket.close_code is not None

                if not is_closed:
                    await self.websocket.close()
            except Exception as e:
                self.logger.debug("关闭WebSocket连接时出错", error=str(e))

        self.is_connected = False
        self.logger.info("✅ OKX WebSocket管理器已停止")

    async def connect(self) -> bool:
        """建立WebSocket连接"""
        try:
            # 🔧 迁移到统一日志系统 - 标准化连接日志
            self.logger.connection_success("Connecting to OKX WebSocket", url=self.ws_base_url)
            self.websocket = await websockets.connect(self.ws_base_url)
            self.is_connected = True
            self.last_message_time = time.time()

            # 重置重连计数
            self.current_reconnect_attempts = 0

            # 🔧 迁移到统一日志系统 - 连接成功日志会被自动去重
            self.logger.connection_success("OKX WebSocket connection established")
            return True

        except Exception as e:
            # 🔧 迁移到统一日志系统 - 标准化连接错误
            self.logger.connection_failure("OKX WebSocket connection failed", error=e)
            self.is_connected = False
            return False

    async def _connection_manager(self):
        """
        连接管理器 - 处理连接和重连

        根据OKX官方文档：
        - 实现指数退避重连策略
        - 连接失败时自动重连
        - 维护连接健康状态
        """
        while self.is_running:
            try:
                await self._connect_and_run()

                # 连接成功，重置重连计数
                if self.current_reconnect_attempts > 0:
                    self.logger.info("✅ OKX WebSocket重连成功，重置重连计数")
                    self.current_reconnect_attempts = 0

            except websockets.exceptions.ConnectionClosed as e:
                self.logger.warning(f"🔗 OKX WebSocket连接关闭: {e}")
                await self._handle_reconnection("连接关闭")

            except websockets.exceptions.InvalidURI as e:
                self.logger.error(f"❌ OKX WebSocket URI无效: {e}")
                break  # URI错误不重连

            except asyncio.TimeoutError:
                self.logger.warning("⏰ OKX WebSocket连接超时")
                await self._handle_reconnection("连接超时")

            except Exception as e:
                self.logger.error(f"❌ OKX WebSocket连接异常: {e}", exc_info=True)
                await self._handle_reconnection(f"连接异常: {str(e)}")

                if not self.is_running:
                    break

    async def _handle_reconnection(self, reason: str):
        """
        处理重连逻辑

        Args:
            reason: 重连原因
        """
        if not self.is_running:
            return

        # 计算重连延迟（指数退避）
        delay = min(
            self.reconnect_delay * (self.backoff_multiplier ** self.current_reconnect_attempts),
            self.max_reconnect_delay
        )

        self.current_reconnect_attempts += 1
        self.reconnect_count += 1
        # 指标：重连计数
        try:
            self.metrics.counter("websocket_reconnects_total", 1, self._metric_labels)
        except Exception:
            pass
        # 汇总计数
        self._last_summary["reconnects"] += 1

        self.logger.warning(f"🔄 OKX WebSocket将在{delay:.1f}秒后重连",
                          reason=reason,
                          attempt=self.current_reconnect_attempts,
                          total_reconnects=self.reconnect_count)

        await asyncio.sleep(delay)

    async def _connect_and_run(self):
        """
        连接并运行WebSocket

        根据OKX官方文档：
        - 使用连接超时防止长时间等待
        - 连接成功后立即订阅数据
        - 启动心跳和消息监听
        """
        # 连接WebSocket（带超时）
        self.logger.info("🔌 连接OKX WebSocket", url=self.ws_base_url)

        try:
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    self.ws_base_url,
                    ping_interval=None,  # 禁用内置ping，使用自定义心跳
                    ping_timeout=None,
                    close_timeout=10
                ),
                timeout=self.connection_timeout
            )

            self.is_connected = True
            current_time = time.time()
            self.last_message_time = current_time
            self.last_ping_time = current_time  # 初始化心跳时间，避免立即触发心跳
            # 连接Gauge置1
            try:
                from core.observability.metrics.metric_categories import StandardMetrics
                self.metrics.set_gauge(StandardMetrics.WEBSOCKET_CONNECTIONS.name, 1, {"exchange": "okx", "channel": self.market_type})
            except Exception:
                pass
            # 🔧 迁移到统一日志系统 - 连接成功日志会被自动去重
            self.logger.connection_success("OKX WebSocket connection established")

            # 订阅订单簿数据
            await self.subscribe_orderbook()

            # 启动心跳任务（切换到 TextHeartbeatRunner）
            if getattr(self, '_ws_ctx', None) and self._ws_ctx.use_text_ping:
                self._ws_ctx.bind(self.websocket, lambda: self.is_running and self.is_connected)
                self._ws_ctx.start_heartbeat()
                self.heartbeat_task = None
            else:
                self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 启动消息监听
            self.listen_task = asyncio.create_task(self._listen_messages())

            # 等待任务完成（通常是连接断开）
            wait_tasks = [self.listen_task] if self.heartbeat_task is None else [self.heartbeat_task, self.listen_task]
            done, pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except asyncio.TimeoutError:
            self.logger.error(f"❌ OKX WebSocket连接超时 ({self.connection_timeout}s)")
            raise

        except Exception as e:
            self.logger.error(f"❌ OKX WebSocket连接失败: {e}")
            raise

        finally:
            # 清理连接
            self.is_connected = False
            # 连接Gauge置0
            try:
                from core.observability.metrics.metric_categories import StandardMetrics
                self.metrics.set_gauge(StandardMetrics.WEBSOCKET_CONNECTIONS.name, 0, {"exchange": "okx", "channel": self.market_type})
            except Exception:
                pass
            if hasattr(self, 'websocket') and self.websocket:
                try:
                    # 安全检查连接状态 - 兼容不同WebSocket实现
                    is_closed = False
                    if hasattr(self.websocket, 'closed'):

                        is_closed = self.websocket.closed
                    elif hasattr(self.websocket, 'close_code'):
                        # aiohttp ClientWebSocketResponse使用close_code判断
                        is_closed = self.websocket.close_code is not None

                    if not is_closed:
                        await self.websocket.close()
                except Exception as e:
                    self.logger.debug(f"关闭WebSocket连接时出错: {e}")

            # 清理任务
            for task_name in ['heartbeat_task', 'listen_task']:
                if hasattr(self, task_name):
                    task = getattr(self, task_name)
                    if task and not task.done():
                        task.cancel()

    async def _heartbeat_loop(self):
        """
        OKX心跳循环 - 严格按照官方文档要求实现

        根据OKX官方文档：
        - 客户端需要在30秒内发送ping或其他消息
        - 服务器会响应pong
        - 如果30秒内没有任何消息，服务器会断开连接
        """
        self.logger.info("🔧 启动OKX心跳循环", heartbeat_interval=self.heartbeat_interval)
        # 若使用 TextHeartbeatRunner，则跳过本地循环
        if getattr(self, '_ws_ctx', None) and self._ws_ctx.use_text_ping:
            self.logger.info("🔧 跳过本地心跳循环，使用 TextHeartbeatRunner")
            return
        while self.is_connected and self.is_running:
            try:
                current_time = time.time()

                # 检查是否需要发送ping（基于固定间隔，而不是消息间隔）
                if current_time - self.last_ping_time > self.heartbeat_interval:
                    if not self.waiting_for_pong:
                        # 发送ping
                        if self.ping_pong_log_enabled:
                            self.logger.info("💓 发送OKX心跳ping",
                                           total_pings=self.total_pings_sent + 1,
                                           last_message_ago=f"{current_time - self.last_message_time:.1f}s")

                        await self.websocket.send('ping')
                        self.waiting_for_pong = True
                        self.ping_sent_time = current_time
                        self.last_ping_time = current_time  # 更新上次ping时间
                        self.total_pings_sent += 1
                        # 指标：计数 ping
                        try:
                            self.metrics.counter("websocket_heartbeat_pings_total", 1, self._metric_labels)
                        except Exception:
                            pass
                        # 汇总计数
                        self._last_summary["pings"] += 1
                        self.consecutive_heartbeat_failures = 0  # 重置连续失败计数

                    else:
                        # 检查pong超时
                        if current_time - self.ping_sent_time > self.pong_timeout:
                            self.heartbeat_failures += 1
                            self.consecutive_heartbeat_failures += 1
                            try:
                                self.metrics.counter("websocket_heartbeat_failures_total", 1, self._metric_labels)
                            except Exception:
                                pass
                            # 汇总计数
                            self._last_summary["failures"] += 1

                            self.logger.error("💔 OKX心跳pong超时",
                                            timeout_seconds=f"{current_time - self.ping_sent_time:.1f}s",
                                            consecutive_failures=self.consecutive_heartbeat_failures,
                                            total_failures=self.heartbeat_failures,
                                            total_pings=self.total_pings_sent,
                                            total_pongs=self.total_pongs_received)

                            # 连续失败超过阈值时触发重连
                            if self.consecutive_heartbeat_failures >= self.max_consecutive_failures:
                                self.logger.error(f"💔 连续{self.consecutive_heartbeat_failures}次心跳失败，触发重连")
                                raise Exception(f"连续{self.consecutive_heartbeat_failures}次心跳失败")

                            # 重置等待状态，准备下次ping
                            self.waiting_for_pong = False

                # 周期性输出摘要与告警（即使没有业务消息也输出）
                if time.time() - self._last_summary_ts >= self._summary_interval_sec:

                    try:
                        if self._last_summary["reconnects"] > self._warn_reconnects:
                            self.logger.warning("⚠️ WS重连频率偏高", interval_sec=self._summary_interval_sec, reconnects=self._last_summary["reconnects"])
                        if self._last_summary["failures"] > self._warn_heartbeat_failures:
                            self.logger.warning("⚠️ 心跳失败偏多", interval_sec=self._summary_interval_sec, failures=self._last_summary["failures"])
                        self.logger.info("📝 WS心跳/重连摘要", **{f"summary_{k}": v for k, v in self._last_summary.items()})
                    finally:
                        self._last_summary_ts = time.time()
                        self._last_summary = {"pings": 0, "pongs": 0, "failures": 0, "reconnects": 0}
                # 使用配置的检查间隔
                await asyncio.sleep(self.heartbeat_check_interval)

            except Exception as e:
                self.logger.error(f"💔 OKX心跳循环异常: {e}", exc_info=True)
                # 不要直接break，而是继续尝试
                await asyncio.sleep(self.heartbeat_check_interval)

        self.logger.info("🔧 OKX心跳循环结束")

    async def _listen_messages(self):
        """监听WebSocket消息"""
        self.logger.info("🎧 开始监听OKX WebSocket消息...")

        try:
            async for message in self.websocket:

                try:
                    # 定期输出汇总与阈值告警
                    if time.time() - self._last_summary_ts >= self._summary_interval_sec:
                        try:
                            if self._last_summary["reconnects"] > self._warn_reconnects:
                                self.logger.warning("⚠️ WS重连频率偏高", interval_sec=self._summary_interval_sec, reconnects=self._last_summary["reconnects"])
                            if self._last_summary["failures"] > self._warn_heartbeat_failures:
                                self.logger.warning("⚠️ 心跳失败偏多", interval_sec=self._summary_interval_sec, failures=self._last_summary["failures"])
                            self.logger.info("📝 WS心跳/重连摘要", **{f"summary_{k}": v for k, v in self._last_summary.items()})
                        finally:
                            self._last_summary_ts = time.time()
                            self._last_summary = {"pings": 0, "pongs": 0, "failures": 0, "reconnects": 0}
                    self.total_messages += 1
                    self.last_message_time = time.time()

                    # 处理心跳响应 - 符合OKX官方文档
                    # 统一文本心跳处理（若启用策略）
                    if getattr(self, '_ws_ctx', None):
                        if self._ws_ctx.handle_incoming(message):
                            # pong 已由策略处理
                            continue
                        else:
                            # 非 pong 的入站活动，通知策略更新时间戳
                            self._ws_ctx.notify_inbound()


                    # 记录消息接收
                    if self.total_messages % 1000 == 0:  # 每1000条消息记录一次（降低频率）
                        self.logger.info(f"📊 已接收 {self.total_messages} 条OKX消息")

                    # 解析JSON消息
                    if isinstance(message, str):
                        data = json.loads(message)
                    else:
                        data = json.loads(message.decode('utf-8'))

                    # 处理消息
                    await self._handle_message(data)

                except json.JSONDecodeError as e:
                    self.logger.warning(f"⚠️ JSON解析失败: {e}")
                    continue
                except Exception as e:
                    self.logger.error(f"❌ 处理消息异常: {e}", exc_info=True)
                    continue

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"🔌 OKX WebSocket连接已关闭: {e}")
        except Exception as e:
            self.logger.error(f"❌ OKX WebSocket监听异常: {e}", exc_info=True)
        finally:
            self.logger.info(f"🔌 OKX WebSocket消息监听已停止 total_messages={self.total_messages}")
            self.is_connected = False



    async def disconnect(self):
        """断开WebSocket连接"""
        try:
            if self.websocket and self.is_connected:
                await self.websocket.close()
                self.is_connected = False
                self.logger.info("🔌 OKX WebSocket已断开")
        except Exception as e:
            self.logger.error("❌ 断开OKX WebSocket失败", error=str(e))

    async def _handle_message(self, message: Dict[str, Any]):
        """处理WebSocket消息"""
        try:
            self.logger.debug("🔍 处理OKX消息", message_keys=list(message.keys()) if isinstance(message, dict) else "非字典")

            # 🔧 修复：处理所有数据类型，不仅仅是订单簿数据
            if 'data' in message and self.on_orderbook_update:
                # 获取频道信息
                channel = message.get('arg', {}).get('channel', 'unknown')
                self.logger.debug("🔍 OKX数据频道", channel=channel)

                # 解析OKX WebSocket消息格式
                if 'data' in message:
                    # 打印完整的外层消息结构用于调试
                    self.logger.debug("🔍 完整OKX消息结构", message_keys=list(message.keys()),
                                   arg_info=message.get('arg', {}),
                                   action=message.get('action', 'unknown'),
                                   channel=channel)

                    # OKX数据格式（支持订单簿和Trades）
                    data_list = message['data']
                    self.logger.debug(f"📊 收到OKX {channel} 数据", data_count=len(data_list))

                    # 从外层消息中获取instId信息
                    symbol = None
                    if 'arg' in message and 'instId' in message['arg']:
                        symbol = message['arg']['instId']
                        self.logger.debug("🎯 从外层消息获取到symbol", symbol=symbol)

                    for item in data_list:
                        self.logger.debug("🔍 检查OKX数据项", item_keys=list(item.keys()) if isinstance(item, dict) else f"类型: {type(item)}")

                        # 优先使用数据项中的instId，如果没有则使用外层的
                        item_symbol = item.get('instId', symbol)

                        if item_symbol:
                            # 🔧 修复：根据频道类型处理不同的数据
                            if channel == 'books':
                                self.logger.debug("📊 处理OKX订单簿更新", symbol=item_symbol, item_keys=list(item.keys()))

                                # 🎯 确保seqId、prevSeqId、checksum字段存在
                                if 'seqId' in item:
                                    self.logger.debug("✅ OKX订单簿数据包含seqId",
                                                    symbol=item_symbol,
                                                    seqId=item.get('seqId'),
                                                    prevSeqId=item.get('prevSeqId'),
                                                    checksum=item.get('checksum'))
                                else:
                                    self.logger.warning("⚠️ OKX订单簿数据缺少seqId字段",
                                                      symbol=item_symbol,
                                                      item_keys=list(item.keys()))

                            elif channel == 'trades':
                                self.logger.info("💹 处理OKX逐笔成交数据", symbol=item_symbol,
                                                trade_id=item.get('tradeId', 'N/A'),
                                                price=item.get('px', 'N/A'),
                                                size=item.get('sz', 'N/A'),
                                                side=item.get('side', 'N/A'))

                            else:
                                self.logger.info(f"📊 处理OKX {channel} 数据", symbol=item_symbol, item_keys=list(item.keys()))

                            # 🎯 精确修复：基于OKX官方文档的消息格式判断
                            enhanced_item = item.copy()

                            # 根据OKX官方WebSocket API文档：
                            # 1. 订单簿频道推送分为snapshot和update两种类型
                            # 2. snapshot用于初始化订单簿（prevSeqId=-1）
                            # 3. update用于增量更新订单簿
                            # 4. 交易频道只有update类型

                            if channel == 'books':
                                prev_seq_id = item.get('prevSeqId')
                                seq_id = item.get('seqId')

                                # 根据OKX官方文档：prevSeqId=-1表示snapshot，其他为update
                                if prev_seq_id == -1:
                                    enhanced_item['action'] = 'snapshot'
                                    self.logger.info(f"📊 OKX订单簿快照: {item.get('instId')}, seqId={seq_id}")
                                else:
                                    enhanced_item['action'] = 'update'
                                    self.logger.debug(f"🔄 OKX订单簿更新: {item.get('instId')}, seqId={seq_id}, prevSeqId={prev_seq_id}")

                            elif channel == 'trades':
                                # 交易数据：根据OKX文档，交易数据只有update类型
                                enhanced_item['action'] = 'update'
                                self.logger.debug(f"💱 OKX交易数据: {item.get('instId')}")
                            else:
                                # 其他数据类型：默认为update
                                enhanced_item['action'] = 'update'

                            enhanced_item['channel'] = channel

                            # 🔍 调试：记录回调调用
                            self.logger.debug(f"🔧 调用OKX WebSocket回调: {item_symbol}")

                            # 调用回调函数，传递symbol和增强的update数据
                            if asyncio.iscoroutinefunction(self.on_orderbook_update):
                                await self.on_orderbook_update(item_symbol, enhanced_item)
                            else:
                                self.on_orderbook_update(item_symbol, enhanced_item)

                            self.logger.debug(f"✅ OKX WebSocket回调完成: {item_symbol}")
                        else:
                            self.logger.warning("❌ OKX数据项和外层消息都缺少instId",
                                              item_keys=list(item.keys()) if isinstance(item, dict) else f"类型: {type(item)}",
                                              message_keys=list(message.keys()))
                            # 打印完整的数据项内容用于调试
                            self.logger.warning("完整数据项内容", item=str(item)[:500])

                elif 'event' in message:
                    # 订阅确认或错误消息
                    if message['event'] == 'subscribe':
                        # 🔧 修复：避免参数冲突，使用不同的参数名
                        self.logger.info("OKX subscription successful", event_message=message)
                    elif message['event'] == 'error':
                        # 🔧 修复：避免参数冲突，使用不同的参数名
                        self.logger.error("OKX subscription error", event_message=message)
                    else:
                        # 🔧 修复：避免参数冲突，使用不同的参数名
                        self.logger.debug("Received OKX event message", event_message=message)
                else:
                    # 其他格式的消息
                    # 🔧 修复：避免参数冲突，使用不同的参数名
                    self.logger.warning("Received unknown format OKX message", raw_message=str(message)[:200])

        except Exception as e:
            # 🔧 修复：避免参数冲突，使用不同的参数名
            self.logger.error("Failed to process OKX WebSocket message", error=e, raw_message=str(message)[:200])

    async def _handle_error(self, error: Exception):
        """处理WebSocket错误"""
        self.logger.error("❌ OKX WebSocket错误", error=str(error))
        self.is_connected = False

    async def _handle_close(self, code: int, reason: str):
        """处理WebSocket关闭"""
        self.logger.warning("🔌 OKX WebSocket连接关闭",
                          code=code, reason=reason)
        self.is_connected = False

    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            'connected': self.is_connected,
            'ws_url': self.ws_base_url,
            'market_type': self.market_type,
            'symbols': self.symbols,
            'websocket_depth': self.websocket_depth
        }

    async def send_message(self, message: Dict[str, Any]):
        """发送消息到WebSocket"""
        try:
            if self.websocket and self.is_connected:
                await self.websocket.send(json.dumps(message))
            else:
                self.logger.warning("⚠️ WebSocket未连接，无法发送消息")
        except Exception as e:
            self.logger.error("❌ 发送WebSocket消息失败", error=str(e))

    async def subscribe_orderbook(self, symbols: List[str] = None):
        """订阅订单簿数据"""
        if symbols is None:
            symbols = self.symbols

        try:
            # OKX订单簿订阅消息格式
            subscribe_args = []
            for symbol in symbols:
                # 🔧 修复：根据市场类型调整symbol格式
                if self.market_type == 'perpetual' or self.market_type == 'derivatives':
                    # 永续合约格式：BTC-USDT-SWAP
                    if not symbol.endswith('-SWAP'):
                        symbol = f"{symbol}-SWAP"
                elif self.market_type == 'spot':
                    # 🔧 修复：现货格式确保为BTC-USDT格式
                    if '-' not in symbol:
                        # 如果是BTCUSDT格式，转换为BTC-USDT格式
                        if 'USDT' in symbol:
                            base = symbol.replace('USDT', '')
                            symbol = f"{base}-USDT"
                        elif 'USDC' in symbol:
                            base = symbol.replace('USDC', '')
                            symbol = f"{base}-USDC"
                        # 可以根据需要添加更多货币对

                # 按OKX官方文档，books频道不支持freq参数，移除以避免订阅错误
                subscribe_args.append({
                    "channel": "books",
                    "instId": symbol
                })

            subscribe_msg = {
                "op": "subscribe",
                "args": subscribe_args
            }

            await self.send_message(subscribe_msg)
            self.logger.info("📊 已订阅OKX订单簿数据", symbols=symbols)

        except Exception as e:
            self.logger.error("❌ 订阅OKX订单簿失败", error=str(e))

    async def unsubscribe_orderbook(self, symbols: List[str] = None):
        """取消订阅订单簿数据"""
        if symbols is None:
            symbols = self.symbols

        try:
            unsubscribe_args = []
            for symbol in symbols:
                # 🔧 修复：统一symbol格式处理
                if self.market_type == 'perpetual' or self.market_type == 'derivatives':
                    if not symbol.endswith('-SWAP'):
                        symbol = f"{symbol}-SWAP"
                elif self.market_type == 'spot':
                    # 现货格式确保为BTC-USDT格式
                    if '-' not in symbol:
                        if 'USDT' in symbol:
                            base = symbol.replace('USDT', '')
                            symbol = f"{base}-USDT"
                        elif 'USDC' in symbol:
                            base = symbol.replace('USDC', '')
                            symbol = f"{base}-USDC"

                unsubscribe_args.append({
                    "channel": "books",
                    "instId": symbol
                })

            unsubscribe_msg = {
                "op": "unsubscribe",
                "args": unsubscribe_args
            }

            await self.send_message(unsubscribe_msg)
            self.logger.info("📊 已取消订阅OKX订单簿数据", symbols=symbols)

        except Exception as e:
            self.logger.error("❌ 取消订阅OKX订单簿失败", error=str(e))

    # 🔧 新增：逐笔成交数据订阅功能
    async def subscribe_trades(self, symbols: List[str] = None):
        """
        订阅逐笔成交数据
        使用 trades 频道
        """
        if symbols is None:
            symbols = self.symbols

        try:
            for symbol in symbols:
                # 🔧 修复：统一symbol格式处理
                formatted_symbol = symbol
                if self.market_type == 'perpetual' or self.market_type == 'derivatives':
                    # 永续合约格式：BTC-USDT-SWAP
                    if not symbol.endswith('-SWAP'):
                        formatted_symbol = f"{symbol}-SWAP"
                elif self.market_type == 'spot':
                    # 现货格式确保为BTC-USDT格式
                    if '-' not in symbol:
                        if 'USDT' in symbol:
                            base = symbol.replace('USDT', '')
                            formatted_symbol = f"{base}-USDT"
                        elif 'USDC' in symbol:
                            base = symbol.replace('USDC', '')
                            formatted_symbol = f"{base}-USDC"

                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "trades",
                        "instId": formatted_symbol
                    }]
                }
                await self.websocket.send(json.dumps(subscribe_msg))

            self.logger.info("✅ 订阅OKX逐笔成交数据成功",
                           symbols=symbols,
                           market_type=self.market_type)

        except Exception as e:
            self.logger.error("❌ 订阅OKX逐笔成交数据失败", error=str(e))

    async def unsubscribe_trades(self, symbols: List[str] = None):
        """取消订阅逐笔成交数据"""
        if symbols is None:
            symbols = self.symbols

        try:
            for symbol in symbols:
                unsubscribe_msg = {
                    "op": "unsubscribe",
                    "args": [{
                        "channel": "trades",
                        "instId": symbol
                    }]
                }
                await self.websocket.send(json.dumps(unsubscribe_msg))

            self.logger.info("✅ 取消订阅OKX逐笔成交数据成功", symbols=symbols)

        except Exception as e:
            self.logger.error("❌ 取消订阅OKX逐笔成交数据失败", error=str(e))

    async def subscribe_channel(self, channel_data: Dict[str, Any]):
        """
        订阅单个频道（通用方法）
        支持订单簿、逐笔成交等各种数据频道
        """
        try:
            subscribe_msg = {
                "op": "subscribe",
                "args": [channel_data]
            }

            await self.websocket.send(json.dumps(subscribe_msg))
            self.logger.debug("✅ 订阅OKX数据频道成功", channel=channel_data)

        except Exception as e:
            self.logger.error("❌ 订阅OKX数据频道失败", channel=channel_data, error=str(e))

    def get_stats(self) -> dict:
        """获取OKX WebSocket统计信息"""
        return {
            'is_connected': self.is_connected,
            'total_messages': self.total_messages,
            'reconnect_attempts': self.current_reconnect_attempts,
            'last_message_time': self.last_message_time,
            # 🔧 新增心跳统计
            'heartbeat_stats': self.get_heartbeat_stats()
        }

    def get_heartbeat_stats(self) -> dict:
        """获取OKX心跳统计信息
        若启用了统一策略(TextHeartbeatRunner)，优先返回策略侧的统计。
        """
        if getattr(self, '_ws_ctx', None) and getattr(self._ws_ctx, 'heartbeat', None):
            hb = self._ws_ctx.heartbeat
            last_msg = getattr(hb, 'last_message_time', 0.0) or 0.0
            total_pings = getattr(hb, 'total_pings_sent', 0)
            total_pongs = getattr(hb, 'total_pongs_received', 0)
            waiting = getattr(hb, 'waiting_for_pong', False)
            ping_sent_time = getattr(hb, 'ping_sent_time', 0.0) or 0.0
            return {
                'heartbeat_interval': getattr(hb, 'heartbeat_interval', self.heartbeat_interval),
                'pong_timeout': getattr(hb, 'pong_timeout', self.pong_timeout),
                'outbound_ping_interval': getattr(hb, 'outbound_ping_interval', None),
                'total_pings_sent': total_pings,
                'total_pongs_received': total_pongs,
                'heartbeat_failures': self.heartbeat_failures,
                'waiting_for_pong': waiting,
                'ping_sent_time': ping_sent_time,
                'last_message_time': last_msg,
                'ping_success_rate': (total_pongs / total_pings * 100) if total_pings > 0 else 0,
                'time_since_last_message': time.time() - last_msg if last_msg > 0 else 0
            }
        return {
            'heartbeat_interval': self.heartbeat_interval,
            'pong_timeout': self.pong_timeout,
            'total_pings_sent': self.total_pings_sent,
            'total_pongs_received': self.total_pongs_received,
            'heartbeat_failures': self.heartbeat_failures,
            'waiting_for_pong': self.waiting_for_pong,
            'ping_sent_time': self.ping_sent_time,
            'last_message_time': self.last_message_time,
            'ping_success_rate': (self.total_pongs_received / self.total_pings_sent * 100) if self.total_pings_sent > 0 else 0,
            'time_since_last_message': time.time() - self.last_message_time if self.last_message_time > 0 else 0
        }


class OKXWebSocketManagerForTrades:
    """
    OKX WebSocket管理器 - 专门用于Trades Manager
    支持通用数据回调，不限于订单簿数据
    """

    def __init__(self, market_type: str = 'spot', symbols: List[str] = None, data_callback: Callable = None):
        self.market_type = market_type
        self.symbols = symbols or []
        self.data_callback = data_callback
        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(
            ComponentType.WEBSOCKET,
            exchange="okx",
            market_type="trades"
        )

        # 使用现有的WebSocket客户端
        self.client = OKXWebSocketManager(
            symbols=self.symbols,
            on_orderbook_update=self._handle_data,
            market_type=market_type
        )

        self.is_connected = False

    async def start(self):
        """启动WebSocket连接"""
        try:
            success = await self.client.connect()
            # 🔧 修复：同步连接状态
            self.is_connected = success and self.client.is_connected

            if self.is_connected:
                self.logger.info("✅ OKXWebSocketManagerForTrades启动成功", market_type=self.market_type)
            else:
                self.logger.error("❌ OKXWebSocketManagerForTrades连接失败", market_type=self.market_type)

        except Exception as e:
            self.is_connected = False
            self.logger.error("❌ OKXWebSocketManagerForTrades启动失败", error=str(e), exc_info=True)
            raise

    async def stop(self):
        """停止WebSocket连接"""
        try:
            await self.client.disconnect()
            self.is_connected = False
            self.logger.info("✅ OKXWebSocketManagerForTrades停止成功")
        except Exception as e:
            self.logger.error("❌ OKXWebSocketManagerForTrades停止失败", error=str(e), exc_info=True)

    async def subscribe_channel(self, channel_data: Dict[str, Any]):
        """订阅数据频道"""
        await self.client.subscribe_channel(channel_data)

    async def subscribe_trades(self, symbols: List[str] = None):
        """订阅逐笔成交数据"""
        await self.client.subscribe_trades(symbols)

    async def subscribe_orderbook(self, symbols: List[str] = None):
        """订阅订单簿数据"""
        await self.client.subscribe_orderbook(symbols)

    async def _handle_data(self, symbol: str, data: Dict[str, Any]):
        """处理接收到的数据"""
        if self.data_callback:
            try:
                if asyncio.iscoroutinefunction(self.data_callback):
                    await self.data_callback(data)
                else:
                    self.data_callback(data)
            except Exception as e:
                self.logger.error("数据回调处理失败", error=str(e), exc_info=True)


# 向后兼容的别名
OKXWebSocketClient = OKXWebSocketManager
OKXWebSocket = OKXWebSocketManager
