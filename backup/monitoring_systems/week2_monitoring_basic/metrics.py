"""
Prometheus监控指标模块

提供企业级监控指标，包括消息计数、错误统计、性能监控等
符合MarketPrism监控系统优化规范 v2.0
"""

import time
from typing import Dict, Any, Optional, List
from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry, generate_latest
import structlog
import psutil
import platform
from datetime import datetime


class CollectorMetrics:
    """收集器Prometheus指标 - 标准化版本"""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.logger = structlog.get_logger(__name__)
        self.registry = registry or CollectorRegistry()
        self._init_metrics()
    
    def _init_metrics(self):
        """初始化所有监控指标 - 符合标准化规范"""
        
        # === Counter指标 (累计计数) ===
        
        # 消息处理计数 - 标准化命名
        self.collector_messages_total = Counter(
            'marketprism_collector_messages_total',
            'Total messages processed by exchange and data type',
            ['exchange', 'data_type', 'status'],
            registry=self.registry
        )
        
        # 错误计数 - 标准化命名
        self.collector_errors_total = Counter(
            'marketprism_collector_errors_total',
            'Total errors by exchange and error type',
            ['exchange', 'error_type'],
            registry=self.registry
        )
        
        # NATS发布计数 - 标准化命名
        self.nats_publishes_total = Counter(
            'marketprism_nats_publishes_total',
            'Total NATS publishes by exchange and data type',
            ['exchange', 'data_type', 'status'],
            registry=self.registry
        )
        
        # WebSocket重连计数 - 标准化命名
        self.websocket_reconnects_total = Counter(
            'marketprism_websocket_reconnects_total',
            'Total WebSocket reconnections by exchange',
            ['exchange'],
            registry=self.registry
        )
        
        # === Gauge指标 (瞬时值) ===
        
        # 连接状态 - 标准化命名
        self.exchange_connection_status = Gauge(
            'marketprism_exchange_connection_status',
            'Exchange connection status (1=connected, 0=disconnected)',
            ['exchange'],
            registry=self.registry
        )
        
        self.nats_connection_status = Gauge(
            'marketprism_nats_connection_status',
            'NATS connection status (1=connected, 0=disconnected)',
            registry=self.registry
        )
        
        # 系统资源 - 标准化命名
        self.system_memory_usage_bytes = Gauge(
            'marketprism_system_memory_usage_bytes',
            'Current memory usage in bytes',
            registry=self.registry
        )
        
        self.system_cpu_usage_percent = Gauge(
            'marketprism_system_cpu_usage_percent',
            'Current CPU usage percentage',
            registry=self.registry
        )
        
        self.system_disk_usage_percent = Gauge(
            'marketprism_system_disk_usage_percent',
            'Current disk usage percentage',
            registry=self.registry
        )
        
        # 队列大小 - 标准化命名
        self.queue_size = Gauge(
            'marketprism_queue_size',
            'Current queue size by exchange and queue type',
            ['exchange', 'queue_type'],
            registry=self.registry
        )
        
        # 活跃连接数 - 标准化命名
        self.websocket_connections_active = Gauge(
            'marketprism_websocket_connections_active',
            'Number of active WebSocket connections by exchange',
            ['exchange'],
            registry=self.registry
        )
        
        # 实时性能指标 - 标准化命名
        self.collector_messages_per_second = Gauge(
            'marketprism_collector_messages_per_second',
            'Current messages per second by exchange',
            ['exchange'],
            registry=self.registry
        )
        
        self.collector_error_rate_percent = Gauge(
            'marketprism_collector_error_rate_percent',
            'Current error rate percentage by exchange',
            ['exchange'],
            registry=self.registry
        )
        
        # 运行时间 - 标准化命名
        self.collector_uptime_seconds = Gauge(
            'marketprism_collector_uptime_seconds',
            'Collector uptime in seconds',
            registry=self.registry
        )
        
        # === Histogram指标 (分布统计) ===
        
        # 消息处理延迟 - 标准化命名
        self.collector_processing_duration_seconds = Histogram(
            'marketprism_collector_processing_duration_seconds',
            'Time spent processing messages by exchange and data type',
            ['exchange', 'data_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, float('inf')],
            registry=self.registry
        )
        
        # NATS发布延迟 - 标准化命名
        self.nats_publish_duration_seconds = Histogram(
            'marketprism_nats_publish_duration_seconds',
            'Time spent publishing to NATS by exchange and data type',
            ['exchange', 'data_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, float('inf')],
            registry=self.registry
        )
        
        # 消息大小分布 - 新增业务指标
        self.message_size_bytes = Histogram(
            'marketprism_message_size_bytes',
            'Message size distribution by exchange and data type',
            ['exchange', 'data_type'],
            buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, float('inf')],
            registry=self.registry
        )
        
        # 批处理大小 - 新增业务指标
        self.batch_size = Histogram(
            'marketprism_batch_size',
            'Batch processing size distribution',
            ['operation', 'data_type'],
            buckets=[1, 10, 50, 100, 500, 1000, 5000, float('inf')],
            registry=self.registry
        )
        
        # === Info指标 (元数据) ===
        
        # 系统信息 - 标准化命名
        self.collector_info = Info(
            'marketprism_collector_info',
            'Collector system information',
            registry=self.registry
        )
        
        # 交易所信息 - 新增业务指标
        self.exchange_info = Info(
            'marketprism_exchange_info',
            'Exchange connection information',
            registry=self.registry
        )
        
        # NATS信息 - 新增业务指标
        self.nats_info = Info(
            'marketprism_nats_info',
            'NATS server information',
            registry=self.registry
        )
        
        # === 新增业务指标 ===
        
        # 数据新鲜度
        self.collector_last_message_timestamp = Gauge(
            'marketprism_collector_last_message_timestamp',
            'Timestamp of last processed message by exchange and data type',
            ['exchange', 'data_type'],
            registry=self.registry
        )
        
        # 交易对活跃度
        self.symbol_activity_count = Gauge(
            'marketprism_symbol_activity_count',
            'Number of active symbols by exchange',
            ['exchange'],
            registry=self.registry
        )
        
        # 数据质量指标
        self.data_quality_score = Gauge(
            'marketprism_data_quality_score',
            'Data quality score (0-100) by exchange and data type',
            ['exchange', 'data_type'],
            registry=self.registry
        )
    
    # === 标准化方法名 ===
    
    def record_message_processed(self, exchange: str, data_type: str, status: str, message_size: int = 0):
        """记录消息处理 - 增强版"""
        self.collector_messages_total.labels(
            exchange=exchange, 
            data_type=data_type, 
            status=status
        ).inc()
        
        # 记录消息大小
        if message_size > 0:
            self.message_size_bytes.labels(
                exchange=exchange,
                data_type=data_type
            ).observe(message_size)
        
        # 更新最后消息时间
        self.collector_last_message_timestamp.labels(
            exchange=exchange,
            data_type=data_type
        ).set(time.time())
    
    def record_error(self, exchange: str, error_type: str):
        """记录错误 - 标准化"""
        self.collector_errors_total.labels(
            exchange=exchange, 
            error_type=error_type
        ).inc()
    
    def record_processing_time(self, exchange: str, data_type: str, duration: float):
        """记录处理时间 - 标准化"""
        self.collector_processing_duration_seconds.labels(
            exchange=exchange, 
            data_type=data_type
        ).observe(duration)
    
    def record_nats_publish(self, exchange: str, data_type: str, status: str):
        """记录NATS发布 - 标准化"""
        self.nats_publishes_total.labels(
            exchange=exchange, 
            data_type=data_type, 
            status=status
        ).inc()
    
    def record_nats_publish_time(self, exchange: str, data_type: str, duration: float):
        """记录NATS发布时间 - 标准化"""
        self.nats_publish_duration_seconds.labels(
            exchange=exchange, 
            data_type=data_type
        ).observe(duration)
    
    def record_batch_operation(self, operation: str, data_type: str, batch_size: int):
        """记录批处理操作 - 新增"""
        self.batch_size.labels(
            operation=operation,
            data_type=data_type
        ).observe(batch_size)
    
    def update_connection_status(self, exchange: str, connected: bool):
        """更新连接状态 - 标准化"""
        self.exchange_connection_status.labels(exchange=exchange).set(1 if connected else 0)
    
    def update_nats_connection_status(self, connected: bool):
        """更新NATS连接状态 - 标准化"""
        self.nats_connection_status.set(1 if connected else 0)
    
    def update_queue_size(self, exchange: str, queue_type: str, size: int):
        """更新队列大小 - 标准化"""
        self.queue_size.labels(exchange=exchange, queue_type=queue_type).set(size)
    
    def update_websocket_connections(self, exchange: str, count: int):
        """更新WebSocket连接数 - 标准化"""
        self.websocket_connections_active.labels(exchange=exchange).set(count)
    
    def record_websocket_reconnect(self, exchange: str):
        """记录WebSocket重连 - 标准化"""
        self.websocket_reconnects_total.labels(exchange=exchange).inc()
    
    def update_system_metrics(self):
        """更新系统指标 - 标准化"""
        try:
            # 内存使用
            memory_info = psutil.virtual_memory()
            process = psutil.Process()
            self.system_memory_usage_bytes.set(process.memory_info().rss)
            
            # CPU使用
            cpu_percent = psutil.cpu_percent(interval=1)
            self.system_cpu_usage_percent.set(cpu_percent)
            
            # 磁盘使用
            disk_usage = psutil.disk_usage('/')
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            self.system_disk_usage_percent.set(disk_percent)
            
        except Exception as e:
            self.logger.error("更新系统指标失败", error=str(e))
    
    def update_system_info(self, info: Dict[str, str]):
        """更新系统信息 - 标准化"""
        self.collector_info.info(info)
    
    def update_exchange_info(self, exchange: str, info: Dict[str, str]):
        """更新交易所信息 - 新增"""
        info_with_exchange = {**info, 'exchange': exchange}
        self.exchange_info.info(info_with_exchange)
    
    def update_nats_info(self, info: Dict[str, str]):
        """更新NATS信息 - 新增"""
        self.nats_info.info(info)
    
    def update_uptime(self, start_time: datetime):
        """更新运行时间 - 标准化"""
        uptime = (datetime.utcnow() - start_time).total_seconds()
        self.collector_uptime_seconds.set(uptime)
    
    def update_messages_per_second(self, exchange: str, rate: float):
        """更新每秒消息数 - 新增"""
        self.collector_messages_per_second.labels(exchange=exchange).set(rate)
    
    def update_error_rate(self, exchange: str, rate: float):
        """更新错误率 - 新增"""
        self.collector_error_rate_percent.labels(exchange=exchange).set(rate)
    
    def update_symbol_activity(self, exchange: str, count: int):
        """更新交易对活跃度 - 新增"""
        self.symbol_activity_count.labels(exchange=exchange).set(count)
    
    def update_data_quality(self, exchange: str, data_type: str, score: float):
        """更新数据质量评分 - 新增"""
        self.data_quality_score.labels(
            exchange=exchange,
            data_type=data_type
        ).set(score)
    
    def get_metrics(self) -> str:
        """获取Prometheus格式的指标 - 标准化"""
        return generate_latest(self.registry).decode('utf-8')
    
    # === 兼容性方法 (保持向后兼容) ===
    
    @property
    def messages_total(self):
        """向后兼容"""
        return self.collector_messages_total
    
    @property
    def errors_total(self):
        """向后兼容"""
        return self.collector_errors_total
    
    @property
    def processing_duration_seconds(self):
        """向后兼容"""
        return self.collector_processing_duration_seconds
    
    @property
    def memory_usage_bytes(self):
        """向后兼容"""
        return self.system_memory_usage_bytes
    
    @property
    def cpu_usage_percent(self):
        """向后兼容"""
        return self.system_cpu_usage_percent
    
    @property
    def uptime_seconds(self):
        """向后兼容"""
        return self.collector_uptime_seconds
    
    @property
    def websocket_connections(self):
        """向后兼容"""
        return self.websocket_connections_active
    
    @property
    def messages_per_second(self):
        """向后兼容"""
        return self.collector_messages_per_second
    
    @property
    def error_rate(self):
        """向后兼容"""
        return self.collector_error_rate_percent
    
    @property
    def info(self):
        """向后兼容"""
        return self.collector_info


def init_metrics() -> CollectorMetrics:
    """初始化指标实例"""
    return CollectorMetrics()


# 全局指标实例
_metrics_instance = None

def get_metrics() -> CollectorMetrics:
    """获取全局指标实例"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = init_metrics()
    return _metrics_instance 


class MetricsCollector:
    """TDD改进：标准化指标收集器接口
    
    提供统一的指标收集接口，兼容现有CollectorMetrics
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.interval = self.config.get('interval', 30)
        
        # 基础指标存储
        self.counters: Dict[str, float] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = {}
        self.timers: Dict[str, float] = {}
        
        # 内部CollectorMetrics实例
        self._collector_metrics = CollectorMetrics()
        
        self.logger = structlog.get_logger(__name__)
        self.logger.info("MetricsCollector初始化完成", config=self.config)
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """增加计数器"""
        if not self.enabled:
            return
            
        if name not in self.counters:
            self.counters[name] = 0
        self.counters[name] += value
        
        # 同时更新Prometheus指标
        if hasattr(self._collector_metrics, 'collector_messages_total') and labels:
            self._collector_metrics.collector_messages_total.labels(**labels).inc(value)
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """设置仪表盘值"""
        if not self.enabled:
            return
            
        self.gauges[name] = value
        
        # 同时更新Prometheus指标
        if hasattr(self._collector_metrics, 'collector_memory_usage_mb') and labels:
            self._collector_metrics.collector_memory_usage_mb.labels(**labels).set(value)
    
    def record_histogram(self, name: str, value: float):
        """记录直方图值"""
        if not self.enabled:
            return
            
        if name not in self.histograms:
            self.histograms[name] = []
        self.histograms[name].append(value)
        
        # 保持最近1000个值
        if len(self.histograms[name]) > 1000:
            self.histograms[name] = self.histograms[name][-1000:]
    
    def start_timer(self, name: str) -> float:
        """开始计时器"""
        start_time = time.time()
        self.timers[f"{name}_start"] = start_time
        return start_time
    
    def stop_timer(self, name: str) -> float:
        """停止计时器并记录持续时间"""
        end_time = time.time()
        start_time = self.timers.get(f"{name}_start", end_time)
        duration = end_time - start_time
        
        self.record_histogram(f"{name}_duration", duration)
        return duration
    
    def get_counter(self, name: str) -> float:
        """获取计数器值"""
        return self.counters.get(name, 0.0)
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        return {
            'counters': self.counters.copy(),
            'gauges': self.gauges.copy(),
            'histograms': {k: len(v) for k, v in self.histograms.items()},
            'timers': {k: v for k, v in self.timers.items() if not k.endswith('_start')},
            'enabled': self.enabled,
            'config': self.config,
            'timestamp': time.time()
        }
    
    def get_prometheus_metrics(self) -> str:
        """TDD改进：获取Prometheus格式指标"""
        return self._collector_metrics.get_prometheus_metrics()['prometheus_metrics']
    
    def export_prometheus(self) -> Dict[str, Any]:
        """TDD改进：导出Prometheus指标"""
        return self._collector_metrics.get_prometheus_metrics()
    
    def register_prometheus(self, metric_name: str, metric_type: str, description: str):
        """TDD改进：注册Prometheus指标"""
        # 这里可以扩展动态注册功能
        self.logger.info("注册Prometheus指标", name=metric_name, type=metric_type)
        return True 