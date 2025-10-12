"""
MarketPrism订单簿管理系统指标收集模块

提供Prometheus格式的监控指标收集和导出功能。
"""

import time
import psutil
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from prometheus_client import Counter, Gauge, Histogram, Info, CollectorRegistry, REGISTRY
import structlog

logger = structlog.get_logger(__name__)


class MetricsCollector:
    """指标收集器"""

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or REGISTRY
        self.logger = structlog.get_logger(__name__)
        self.start_time = time.time()
        # 采集层最近成功缓存（便于/health覆盖统计）
        self._last_success: Dict[str, Dict[str, float]] = {}

        # 初始化指标
        self._init_metrics()

    def _init_metrics(self):
        """初始化Prometheus指标"""

        # 系统信息指标
        self.system_info = Info(
            'marketprism_system_info',
            'System information',
            registry=self.registry
        )

        # 系统运行时间
        self.uptime_seconds = Gauge(
            'marketprism_uptime_seconds',
            'System uptime in seconds',
            registry=self.registry
        )

        # 系统资源指标
        self.cpu_usage_percent = Gauge(
            'marketprism_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )

        self.memory_usage_percent = Gauge(
            'marketprism_memory_usage_percent',
            'Memory usage percentage',
            registry=self.registry
        )

        self.memory_usage_bytes = Gauge(
            'marketprism_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )

        self.disk_usage_percent = Gauge(
            'marketprism_disk_usage_percent',
            'Disk usage percentage',
            registry=self.registry
        )

        # 订单簿管理指标
        self.active_symbols_count = Gauge(
            'marketprism_active_symbols_count',
            'Number of active symbols',
            registry=self.registry
        )

        self.orderbook_updates_total = Counter(
            'marketprism_orderbook_updates_total',
            'Total number of orderbook updates',
            ['exchange', 'symbol'],
            registry=self.registry
        )

        self.orderbook_update_duration = Histogram(
            'marketprism_orderbook_update_duration_seconds',
            'Time spent processing orderbook updates',
            ['exchange', 'symbol'],
            registry=self.registry
        )

        self.last_orderbook_update_timestamp = Gauge(
            'marketprism_last_orderbook_update_timestamp',
            'Timestamp of last orderbook update',
            ['exchange', 'symbol'],
            registry=self.registry
        )
        # 队列丢弃统计（按交易所/交易对）
        self.orderbook_queue_drops_total = Gauge(
            'marketprism_orderbook_queue_drops_total',
            'Total number of dropped websocket messages due to full queue',
            ['exchange', 'symbol'],
            registry=self.registry
        )

        # 采集层通用指标（新增）：
        # 1) 采集错误计数（含HTTP状态码/限制码）
        self.collector_errors_total = Counter(
            'marketprism_collector_errors_total',
            'Total number of collector errors (HTTP/WS etc.)',
            ['exchange', 'data_type', 'code'],
            registry=self.registry
        )
        # 2) 最近成功采集时间戳（按交易所×数据类型）
        self.collector_last_success_timestamp_seconds = Gauge(
            'marketprism_collector_last_success_timestamp_seconds',
            'Last success timestamp (epoch seconds) by exchange and data type',
            ['exchange', 'data_type'],
            registry=self.registry
        )


        # WebSocket连接指标
        self.websocket_connected = Gauge(
            'marketprism_websocket_connected',
            'WebSocket connection status (1=connected, 0=disconnected)',
            ['exchange'],
            registry=self.registry
        )

        self.websocket_reconnections_total = Counter(
            'marketprism_websocket_reconnections_total',
            'Total number of WebSocket reconnections',
            ['exchange'],
            registry=self.registry
        )

        self.websocket_messages_received_total = Counter(
            'marketprism_websocket_messages_received_total',
            'Total number of WebSocket messages received',
            ['exchange', 'message_type'],
            registry=self.registry
        )

        # NATS指标
        self.nats_connected = Gauge(
            'marketprism_nats_connected',
            'NATS connection status (1=connected, 0=disconnected)',
            registry=self.registry
        )

        self.nats_messages_published_total = Counter(
            'marketprism_nats_messages_published_total',
            'Total number of messages published to NATS',
            ['subject'],
            registry=self.registry
        )

        self.nats_publish_errors_total = Counter(
            'marketprism_nats_publish_errors_total',
            'Total number of NATS publish errors',
            ['subject', 'error_type'],
            registry=self.registry
        )

        self.nats_publish_duration = Histogram(
            'marketprism_nats_publish_duration_seconds',
            'Time spent publishing messages to NATS',
            ['subject'],
            registry=self.registry
        )

        # 错误指标
        self.errors_total = Counter(
            'marketprism_errors_total',
            'Total number of errors',
            ['component', 'error_type'],
            registry=self.registry
        )

        # 数据质量指标
        self.data_validation_errors_total = Counter(
            'marketprism_data_validation_errors_total',
            'Total number of data validation errors',
            ['exchange', 'validation_type'],
            registry=self.registry
        )

        self.orderbook_sync_status = Gauge(
            'marketprism_orderbook_sync_status',
            'OrderBook synchronization status (1=synced, 0=out_of_sync)',
            ['exchange', 'symbol'],
            registry=self.registry
        )

        # 性能指标
        self.request_duration_seconds = Histogram(
            'marketprism_request_duration_seconds',
            'Time spent processing requests',
            ['endpoint', 'method'],
            registry=self.registry
        )

        # 设置系统信息
        self.system_info.info({
            'version': '1.0.0',
            'service': 'marketprism-orderbook-manager',
            'python_version': '3.11+',
            'build_time': '2025-07-03T12:00:00Z'
        })

    async def update_metrics(self,
                           nats_client=None,
                           websocket_connections=None,
                           orderbook_manager=None,
                           orderbook_managers=None):
        """更新所有指标"""
        try:
            # 更新系统指标
            self._update_system_metrics()

            # 更新NATS指标
            if nats_client:
                self._update_nats_metrics(nats_client)

            # 更新WebSocket指标
            if websocket_connections:
                self._update_websocket_metrics(websocket_connections)

            # 更新订单簿管理器指标（兼容单个管理器）
            if orderbook_manager:
                self._update_orderbook_metrics(orderbook_manager)

            # 更新队列丢弃指标：优先从多个管理器聚合；否则回退到单个
            self._update_queue_drop_metrics(orderbook_managers, orderbook_manager)

        except Exception as e:
            self.logger.error("更新指标失败", error=str(e), exc_info=True)
            self.errors_total.labels(component='metrics', error_type='update_failed').inc()

    def _update_queue_drop_metrics(self, orderbook_managers=None, orderbook_manager=None):
        """更新队列丢弃(drops)指标，支持多个或单个管理器"""
        try:
            updated = False
            if isinstance(orderbook_managers, dict) and orderbook_managers:
                for mgr in orderbook_managers.values():
                    exchange_name = getattr(mgr, 'exchange', 'unknown')
                    queue_drops = getattr(mgr, '_queue_drops', None)
                    if isinstance(queue_drops, dict):
                        for sym, val in queue_drops.items():
                            try:
                                self.orderbook_queue_drops_total.labels(
                                    exchange=exchange_name,
                                    symbol=sym
                                ).set(float(val))
                                updated = True
                            except Exception:
                                pass
            # fallback: 单管理器
            if not updated and orderbook_manager is not None:
                exchange_name = getattr(orderbook_manager, 'exchange', 'unknown')
                queue_drops = getattr(orderbook_manager, '_queue_drops', None)
                if isinstance(queue_drops, dict):
                    for sym, val in queue_drops.items():
                        try:
                            self.orderbook_queue_drops_total.labels(
                                exchange=exchange_name,
                                symbol=sym
                            ).set(float(val))
                        except Exception:
                            pass
        except Exception as e:
            self.logger.error("更新队列丢弃指标失败", error=str(e))


    def _update_system_metrics(self):
        """更新系统指标"""
        try:
            # 运行时间
            self.uptime_seconds.set(time.time() - self.start_time)

            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=None)
            self.cpu_usage_percent.set(cpu_percent)

            # 内存使用情况
            memory = psutil.virtual_memory()
            self.memory_usage_percent.set(memory.percent)
            self.memory_usage_bytes.set(memory.used)

            # 磁盘使用情况
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            self.disk_usage_percent.set(disk_percent)

        except Exception as e:
            self.logger.error("更新系统指标失败", error=str(e))

    def _update_nats_metrics(self, nats_client):
        """更新NATS指标"""
        try:
            # NATS连接状态
            if hasattr(nats_client, 'is_connected'):
                connected = 1 if nats_client.is_connected else 0
            else:
                connected = 1 if getattr(nats_client, '_is_connected', False) else 0

            self.nats_connected.set(connected)

        except Exception as e:
            self.logger.error("更新NATS指标失败", error=str(e))

    def _update_websocket_metrics(self, websocket_connections):
        """更新WebSocket指标"""
        try:
            for exchange, connection in websocket_connections.items():
                # WebSocket连接状态
                if connection and hasattr(connection, 'is_connected'):
                    connected = 1 if connection.is_connected else 0
                else:
                    connected = 0

                self.websocket_connected.labels(exchange=exchange).set(connected)

        except Exception as e:
            self.logger.error("更新WebSocket指标失败", error=str(e))

    def _update_orderbook_metrics(self, orderbook_manager):
        """更新订单簿管理器指标，并同步 collector 层指标"""
        try:
            # 活跃交易对数量
            orderbook_states = getattr(orderbook_manager, 'orderbook_states', {})
            self.active_symbols_count.set(len(orderbook_states))

            # 更新每个交易对的指标
            for symbol, state in orderbook_states.items():
                exchange = getattr(state, 'exchange', 'unknown')

                # 最后更新时间
                if hasattr(state, 'last_snapshot_time') and state.last_snapshot_time:
                    last_dt = state.last_snapshot_time
                    if getattr(last_dt, 'tzinfo', None) is None:
                        # 视为UTC
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    last_update = last_dt.timestamp()
                    self.last_orderbook_update_timestamp.labels(
                        exchange=exchange,
                        symbol=symbol
                    ).set(last_update)
                    # 同步设置按 exchange×data_type 的最后成功时间（仅orderbook）
                    try:
                        self.collector_last_success_timestamp_seconds.labels(
                            exchange=exchange,
                            data_type='orderbook'
                        ).set(last_update)
                    except Exception:
                        pass

                # 同步状态
                if hasattr(state, 'is_synced'):
                    sync_status = 1 if state.is_synced else 0
                    self.orderbook_sync_status.labels(
                        exchange=exchange,
                        symbol=symbol
                    ).set(sync_status)

        except Exception as e:
            self.logger.error("更新订单簿指标失败", error=str(e))

    def record_orderbook_update(self, exchange: str, symbol: str, duration: float):
        """记录订单簿更新指标"""
        self.orderbook_updates_total.labels(exchange=exchange, symbol=symbol).inc()
        self.orderbook_update_duration.labels(exchange=exchange, symbol=symbol).observe(duration)

    def record_websocket_message(self, exchange: str, message_type: str):
        """记录WebSocket消息指标"""
        self.websocket_messages_received_total.labels(
            exchange=exchange,
            message_type=message_type
        ).inc()

    def record_websocket_reconnection(self, exchange: str):
        """记录WebSocket重连指标"""
        self.websocket_reconnections_total.labels(exchange=exchange).inc()

    def record_nats_publish(self, subject: str, duration: float, success: bool = True):
        """记录NATS发布指标"""
        self.nats_messages_published_total.labels(subject=subject).inc()
        self.nats_publish_duration.labels(subject=subject).observe(duration)

        if not success:
            self.nats_publish_errors_total.labels(
                subject=subject,
                error_type='publish_failed'
            ).inc()

    def record_error(self, component: str, error_type: str):
        """记录错误指标"""
        self.errors_total.labels(component=component, error_type=error_type).inc()

    def record_data_validation_error(self, exchange: str, validation_type: str):
        """记录数据验证错误指标"""
        self.data_validation_errors_total.labels(
            exchange=exchange,
            validation_type=validation_type
        ).inc()

    def record_request_duration(self, endpoint: str, method: str, duration: float):
        """记录请求处理时间指标"""
        self.request_duration_seconds.labels(
            endpoint=endpoint,
            method=method
        ).observe(duration)


    # === 采集层指标（扩展API）===
    def record_collector_error(self, exchange: str, data_type: str, code: str):
        """记录采集层错误（HTTP/WS/限流等）"""
        try:
            self.collector_errors_total.labels(
                exchange=exchange or 'unknown',
                data_type=data_type or 'unknown',
                code=str(code) if code is not None else 'unknown'
            ).inc()
        except Exception:
            pass

    def record_data_success(self, exchange: str, data_type: str, ts_seconds: float | None = None):
        """记录采集层最后成功时间（用于健康与可观测）"""
        try:
            ex = (exchange or 'unknown')
            dt = (data_type or 'unknown')
            ts = float(ts_seconds) if ts_seconds is not None else float(time.time())
            self.collector_last_success_timestamp_seconds.labels(
                exchange=ex,
                data_type=dt
            ).set(ts)
            # 同步内存快照，便于 /health 构建 coverage
            if dt not in self._last_success:
                self._last_success[dt] = {}
            self._last_success[dt][ex] = ts
        except Exception:
            pass


    def get_last_success_snapshot(self) -> Dict[str, Dict[str, float]]:
        """返回 {data_type: {exchange: ts_seconds}} 的快照"""
        try:
            # 浅拷贝，避免外部修改内部结构
            return {dt: dict(ex_map) for dt, ex_map in self._last_success.items()}
        except Exception:
            return {}
