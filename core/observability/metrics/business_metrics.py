"""
MarketPrism 业务级监控指标

专门针对MarketPrism业务场景的监控指标收集和分析
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict, deque
from dataclasses import dataclass, field
import structlog

try:
    from prometheus_client import Counter, Histogram, Gauge, Summary
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    structlog.get_logger(__name__).warning("prometheus_client不可用")


logger = structlog.get_logger(__name__)


@dataclass
class ExchangeHealthMetrics:
    """交易所健康度指标"""
    exchange_name: str
    connection_status: bool = False
    last_message_time: Optional[datetime] = None
    message_count: int = 0
    error_count: int = 0
    reconnection_count: int = 0
    latency_ms: float = 0.0
    data_quality_score: float = 1.0  # 0-1之间
    
    def get_health_score(self) -> float:
        """计算健康度评分 (0-1)"""
        if not self.connection_status:
            return 0.0
        
        # 基础分数
        score = 0.5
        
        # 消息活跃度 (最近1分钟有消息 +0.2)
        if self.last_message_time:
            time_diff = datetime.now(timezone.utc) - self.last_message_time
            if time_diff < timedelta(minutes=1):
                score += 0.2
        
        # 错误率 (错误率<1% +0.15)
        if self.message_count > 0:
            error_rate = self.error_count / self.message_count
            if error_rate < 0.01:
                score += 0.15
        
        # 延迟 (延迟<100ms +0.1)
        if self.latency_ms < 100:
            score += 0.1
        
        # 数据质量
        score += self.data_quality_score * 0.05
        
        return min(score, 1.0)


@dataclass
class DataFlowMetrics:
    """数据流指标"""
    source: str
    destination: str
    message_count: int = 0
    bytes_transferred: int = 0
    processing_time_ms: float = 0.0
    error_count: int = 0
    last_activity: Optional[datetime] = None
    
    def get_throughput_per_second(self, window_seconds: int = 60) -> float:
        """计算吞吐量 (消息/秒)"""
        if not self.last_activity:
            return 0.0
        
        time_diff = datetime.now(timezone.utc) - self.last_activity
        if time_diff.total_seconds() > window_seconds:
            return 0.0
        
        return self.message_count / window_seconds


class BusinessMetricsCollector:
    """业务指标收集器"""
    
    def __init__(self):
        # Prometheus指标
        if PROMETHEUS_AVAILABLE:
            self._init_prometheus_metrics()
        
        # 业务指标存储
        self.exchange_metrics: Dict[str, ExchangeHealthMetrics] = {}
        self.data_flow_metrics: Dict[str, DataFlowMetrics] = {}
        self.api_metrics: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        # 时间窗口数据
        self.message_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.latency_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        logger.info("业务指标收集器初始化完成")
    
    def _init_prometheus_metrics(self):
        """初始化Prometheus指标"""
        if not PROMETHEUS_AVAILABLE:
            return
        
        # 交易所连接指标
        self.exchange_connection_status = Gauge(
            'marketprism_exchange_connection_status',
            'Exchange connection status (1=connected, 0=disconnected)',
            ['exchange']
        )
        
        self.exchange_message_total = Counter(
            'marketprism_exchange_messages_total',
            'Total messages received from exchange',
            ['exchange', 'message_type']
        )
        
        self.exchange_error_total = Counter(
            'marketprism_exchange_errors_total',
            'Total errors from exchange',
            ['exchange', 'error_type']
        )
        
        self.exchange_latency = Histogram(
            'marketprism_exchange_latency_seconds',
            'Exchange message latency',
            ['exchange'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
        )
        
        # 数据处理指标
        self.data_processing_duration = Histogram(
            'marketprism_data_processing_duration_seconds',
            'Data processing duration',
            ['stage', 'data_type'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
        )
        
        self.data_quality_score = Gauge(
            'marketprism_data_quality_score',
            'Data quality score (0-1)',
            ['exchange', 'symbol', 'data_type']
        )
        
        # API性能指标
        self.api_request_duration = Histogram(
            'marketprism_api_request_duration_seconds',
            'API request duration',
            ['method', 'endpoint', 'status'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )
        
        self.api_request_total = Counter(
            'marketprism_business_api_requests_total',
            'Total business API requests',
            ['method', 'endpoint', 'status']
        )
        
        # 业务健康度指标
        self.business_health_score = Gauge(
            'marketprism_business_health_score',
            'Overall business health score (0-1)',
            ['component']
        )
        
        # NATS指标
        self.nats_message_published = Counter(
            'marketprism_nats_messages_published_total',
            'Total messages published to NATS',
            ['subject']
        )
        
        self.nats_publish_duration = Histogram(
            'marketprism_nats_publish_duration_seconds',
            'NATS message publish duration',
            ['subject'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5]
        )
    
    def record_exchange_connection(self, exchange: str, connected: bool) -> None:
        """记录交易所连接状态"""
        if exchange not in self.exchange_metrics:
            self.exchange_metrics[exchange] = ExchangeHealthMetrics(exchange_name=exchange)
        
        metrics = self.exchange_metrics[exchange]
        metrics.connection_status = connected
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE and hasattr(self, 'exchange_connection_status'):
            self.exchange_connection_status.labels(exchange=exchange).set(1 if connected else 0)
        
        logger.debug("记录交易所连接状态", exchange=exchange, connected=connected)
    
    def record_exchange_message(self, exchange: str, message_type: str, 
                              latency_ms: float = None, data_quality: float = 1.0) -> None:
        """记录交易所消息"""
        if exchange not in self.exchange_metrics:
            self.exchange_metrics[exchange] = ExchangeHealthMetrics(exchange_name=exchange)
        
        metrics = self.exchange_metrics[exchange]
        metrics.message_count += 1
        metrics.last_message_time = datetime.now(timezone.utc)
        metrics.data_quality_score = data_quality
        
        if latency_ms is not None:
            metrics.latency_ms = latency_ms
            self.latency_windows[exchange].append(latency_ms)
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE:
            if hasattr(self, 'exchange_message_total'):
                self.exchange_message_total.labels(
                    exchange=exchange, 
                    message_type=message_type
                ).inc()
            
            if latency_ms is not None and hasattr(self, 'exchange_latency'):
                self.exchange_latency.labels(exchange=exchange).observe(latency_ms / 1000)
            
            if hasattr(self, 'data_quality_score'):
                self.data_quality_score.labels(
                    exchange=exchange,
                    symbol="all",
                    data_type=message_type
                ).set(data_quality)
        
        # 记录到时间窗口
        self.message_windows[exchange].append({
            'timestamp': datetime.now(timezone.utc),
            'type': message_type,
            'latency': latency_ms,
            'quality': data_quality
        })
    
    def record_exchange_error(self, exchange: str, error_type: str, error_message: str = None) -> None:
        """记录交易所错误"""
        if exchange not in self.exchange_metrics:
            self.exchange_metrics[exchange] = ExchangeHealthMetrics(exchange_name=exchange)
        
        metrics = self.exchange_metrics[exchange]
        metrics.error_count += 1
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE and hasattr(self, 'exchange_error_total'):
            self.exchange_error_total.labels(
                exchange=exchange,
                error_type=error_type
            ).inc()
        
        logger.warning("交易所错误", 
                      exchange=exchange, 
                      error_type=error_type, 
                      message=error_message)
    
    def record_data_processing(self, stage: str, data_type: str, duration_ms: float) -> None:
        """记录数据处理性能"""
        if PROMETHEUS_AVAILABLE and hasattr(self, 'data_processing_duration'):
            self.data_processing_duration.labels(
                stage=stage,
                data_type=data_type
            ).observe(duration_ms / 1000)
    
    def record_api_request(self, method: str, endpoint: str, status_code: int, 
                          duration_ms: float) -> None:
        """记录API请求"""
        status = str(status_code)
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE:
            if hasattr(self, 'api_request_total'):
                self.api_request_total.labels(
                    method=method,
                    endpoint=endpoint,
                    status=status
                ).inc()
            
            if hasattr(self, 'api_request_duration'):
                self.api_request_duration.labels(
                    method=method,
                    endpoint=endpoint,
                    status=status
                ).observe(duration_ms / 1000)
        
        # 记录到API指标
        key = f"{method}:{endpoint}"
        if key not in self.api_metrics:
            self.api_metrics[key] = {
                'total_requests': 0,
                'error_count': 0,
                'total_duration': 0.0,
                'last_request': None
            }
        
        api_metric = self.api_metrics[key]
        api_metric['total_requests'] += 1
        api_metric['total_duration'] += duration_ms
        api_metric['last_request'] = datetime.now(timezone.utc)
        
        if status_code >= 400:
            api_metric['error_count'] += 1
    
    def record_nats_publish(self, subject: str, duration_ms: float, success: bool = True) -> None:
        """记录NATS消息发布"""
        if PROMETHEUS_AVAILABLE:
            if success and hasattr(self, 'nats_message_published'):
                self.nats_message_published.labels(subject=subject).inc()
            
            if hasattr(self, 'nats_publish_duration'):
                self.nats_publish_duration.labels(subject=subject).observe(duration_ms / 1000)
    
    def get_exchange_health(self, exchange: str) -> Optional[ExchangeHealthMetrics]:
        """获取交易所健康度"""
        return self.exchange_metrics.get(exchange)
    
    def get_overall_health_score(self) -> float:
        """获取整体健康度评分"""
        if not self.exchange_metrics:
            return 0.0
        
        # 计算所有交易所的平均健康度
        total_score = sum(metrics.get_health_score() for metrics in self.exchange_metrics.values())
        avg_score = total_score / len(self.exchange_metrics)
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE and hasattr(self, 'business_health_score'):
            self.business_health_score.labels(component="overall").set(avg_score)
        
        return avg_score
    
    def get_api_error_rate(self, time_window_minutes: int = 5) -> float:
        """获取API错误率"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        total_requests = 0
        error_requests = 0
        
        for api_metric in self.api_metrics.values():
            if api_metric['last_request'] and api_metric['last_request'] > cutoff_time:
                total_requests += api_metric['total_requests']
                error_requests += api_metric['error_count']
        
        return error_requests / total_requests if total_requests > 0 else 0.0
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        return {
            'exchanges': {
                name: {
                    'health_score': metrics.get_health_score(),
                    'connection_status': metrics.connection_status,
                    'message_count': metrics.message_count,
                    'error_count': metrics.error_count,
                    'latency_ms': metrics.latency_ms
                }
                for name, metrics in self.exchange_metrics.items()
            },
            'overall_health': self.get_overall_health_score(),
            'api_error_rate': self.get_api_error_rate()
        }


# 全局业务指标收集器实例
_global_business_metrics: Optional[BusinessMetricsCollector] = None


def get_business_metrics() -> BusinessMetricsCollector:
    """获取全局业务指标收集器"""
    global _global_business_metrics
    if _global_business_metrics is None:
        _global_business_metrics = BusinessMetricsCollector()
    return _global_business_metrics
