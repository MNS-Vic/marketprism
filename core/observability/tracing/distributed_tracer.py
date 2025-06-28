"""
MarketPrism 分布式追踪系统

跟踪数据从交易所到存储的完整链路
"""

import uuid
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, ContextManager
from dataclasses import dataclass, field
from contextlib import contextmanager
import structlog

try:
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


logger = structlog.get_logger(__name__)


@dataclass
class TraceSpan:
    """追踪跨度"""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok, error, timeout
    
    def finish(self, status: str = "ok") -> None:
        """结束跨度"""
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.status = status
    
    def add_tag(self, key: str, value: Any) -> None:
        """添加标签"""
        self.tags[key] = value
    
    def add_log(self, message: str, level: str = "info", **kwargs) -> None:
        """添加日志"""
        self.logs.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': level,
            'message': message,
            **kwargs
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'span_id': self.span_id,
            'trace_id': self.trace_id,
            'parent_span_id': self.parent_span_id,
            'operation_name': self.operation_name,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_ms': self.duration_ms,
            'tags': self.tags,
            'logs': self.logs,
            'status': self.status
        }


class DistributedTracer:
    """分布式追踪器"""
    
    def __init__(self, service_name: str = "marketprism", config: Dict[str, Any] = None):
        self.service_name = service_name
        self.config = config or {}
        
        # 追踪数据存储
        self.active_spans: Dict[str, TraceSpan] = {}
        self.completed_traces: Dict[str, List[TraceSpan]] = {}
        
        # OpenTelemetry集成
        self.otel_tracer = None
        if OPENTELEMETRY_AVAILABLE and self.config.get('enable_opentelemetry', False):
            self._setup_opentelemetry()
        
        logger.info("分布式追踪器初始化完成", service_name=service_name)
    
    def _setup_opentelemetry(self) -> None:
        """设置OpenTelemetry"""
        try:
            # 设置追踪提供者
            trace.set_tracer_provider(TracerProvider())
            tracer_provider = trace.get_tracer_provider()
            
            # 配置Jaeger导出器
            jaeger_exporter = JaegerExporter(
                agent_host_name=self.config.get('jaeger_host', 'localhost'),
                agent_port=self.config.get('jaeger_port', 6831),
            )
            
            # 添加批量跨度处理器
            span_processor = BatchSpanProcessor(jaeger_exporter)
            tracer_provider.add_span_processor(span_processor)
            
            # 获取追踪器
            self.otel_tracer = trace.get_tracer(self.service_name)
            
            # 自动仪表化
            RequestsInstrumentor().instrument()
            AioHttpClientInstrumentor().instrument()
            
            logger.info("OpenTelemetry集成已启用")
            
        except Exception as e:
            logger.error("OpenTelemetry设置失败", error=str(e))
            self.otel_tracer = None
    
    def start_trace(self, operation_name: str, **tags) -> str:
        """开始新的追踪"""
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        
        span = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=None,
            operation_name=operation_name,
            start_time=datetime.now(timezone.utc),
            tags=tags
        )
        
        self.active_spans[span_id] = span
        
        logger.debug("开始追踪", trace_id=trace_id, operation=operation_name)
        return span_id
    
    def start_span(self, operation_name: str, parent_span_id: str = None, **tags) -> str:
        """开始新的跨度"""
        span_id = str(uuid.uuid4())
        
        # 确定父跨度和追踪ID
        if parent_span_id and parent_span_id in self.active_spans:
            parent_span = self.active_spans[parent_span_id]
            trace_id = parent_span.trace_id
        else:
            trace_id = str(uuid.uuid4())
        
        span = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time=datetime.now(timezone.utc),
            tags=tags
        )
        
        self.active_spans[span_id] = span
        
        logger.debug("开始跨度", 
                    span_id=span_id, 
                    trace_id=trace_id, 
                    operation=operation_name,
                    parent=parent_span_id)
        return span_id
    
    def finish_span(self, span_id: str, status: str = "ok", **tags) -> None:
        """结束跨度"""
        if span_id not in self.active_spans:
            logger.warning("跨度不存在", span_id=span_id)
            return
        
        span = self.active_spans[span_id]
        
        # 添加额外标签
        for key, value in tags.items():
            span.add_tag(key, value)
        
        # 结束跨度
        span.finish(status)
        
        # 移动到已完成追踪
        trace_id = span.trace_id
        if trace_id not in self.completed_traces:
            self.completed_traces[trace_id] = []
        
        self.completed_traces[trace_id].append(span)
        del self.active_spans[span_id]
        
        logger.debug("结束跨度", 
                    span_id=span_id, 
                    trace_id=trace_id,
                    duration_ms=span.duration_ms,
                    status=status)
    
    def add_span_tag(self, span_id: str, key: str, value: Any) -> None:
        """添加跨度标签"""
        if span_id in self.active_spans:
            self.active_spans[span_id].add_tag(key, value)
    
    def add_span_log(self, span_id: str, message: str, level: str = "info", **kwargs) -> None:
        """添加跨度日志"""
        if span_id in self.active_spans:
            self.active_spans[span_id].add_log(message, level, **kwargs)
    
    @contextmanager
    def trace_operation(self, operation_name: str, parent_span_id: str = None, **tags):
        """追踪操作上下文管理器"""
        span_id = self.start_span(operation_name, parent_span_id, **tags)
        try:
            yield span_id
            self.finish_span(span_id, "ok")
        except Exception as e:
            self.add_span_tag(span_id, "error", str(e))
            self.add_span_log(span_id, f"操作失败: {str(e)}", "error")
            self.finish_span(span_id, "error")
            raise
    
    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """获取完整追踪"""
        return self.completed_traces.get(trace_id, [])
    
    def get_active_spans(self) -> List[TraceSpan]:
        """获取活跃跨度"""
        return list(self.active_spans.values())
    
    def analyze_trace_performance(self, trace_id: str) -> Dict[str, Any]:
        """分析追踪性能"""
        spans = self.get_trace(trace_id)
        if not spans:
            return {}
        
        # 计算总时间
        start_times = [span.start_time for span in spans]
        end_times = [span.end_time for span in spans if span.end_time]
        
        if not end_times:
            return {}
        
        total_duration = (max(end_times) - min(start_times)).total_seconds() * 1000
        
        # 分析各个操作的耗时
        operation_stats = {}
        for span in spans:
            if span.duration_ms is not None:
                op_name = span.operation_name
                if op_name not in operation_stats:
                    operation_stats[op_name] = {
                        'count': 0,
                        'total_duration': 0,
                        'min_duration': float('inf'),
                        'max_duration': 0
                    }
                
                stats = operation_stats[op_name]
                stats['count'] += 1
                stats['total_duration'] += span.duration_ms
                stats['min_duration'] = min(stats['min_duration'], span.duration_ms)
                stats['max_duration'] = max(stats['max_duration'], span.duration_ms)
        
        # 计算平均时间
        for stats in operation_stats.values():
            stats['avg_duration'] = stats['total_duration'] / stats['count']
        
        return {
            'trace_id': trace_id,
            'total_duration_ms': total_duration,
            'span_count': len(spans),
            'operation_stats': operation_stats,
            'critical_path': self._find_critical_path(spans)
        }
    
    def _find_critical_path(self, spans: List[TraceSpan]) -> List[str]:
        """找到关键路径"""
        # 简单实现：按持续时间排序
        sorted_spans = sorted(spans, key=lambda s: s.duration_ms or 0, reverse=True)
        return [span.operation_name for span in sorted_spans[:5]]  # 返回前5个最耗时的操作


class MarketDataTracer:
    """市场数据专用追踪器"""
    
    def __init__(self, tracer: DistributedTracer):
        self.tracer = tracer
    
    def trace_data_flow(self, exchange: str, symbol: str, data_type: str) -> str:
        """追踪数据流"""
        return self.tracer.start_trace(
            f"market_data_flow",
            exchange=exchange,
            symbol=symbol,
            data_type=data_type,
            component="data_collector"
        )
    
    def trace_exchange_connection(self, exchange: str, parent_span_id: str) -> str:
        """追踪交易所连接"""
        return self.tracer.start_span(
            "exchange_connection",
            parent_span_id,
            exchange=exchange,
            component="exchange_adapter"
        )
    
    def trace_data_normalization(self, data_type: str, parent_span_id: str) -> str:
        """追踪数据标准化"""
        return self.tracer.start_span(
            "data_normalization",
            parent_span_id,
            data_type=data_type,
            component="data_normalizer"
        )
    
    def trace_nats_publish(self, subject: str, parent_span_id: str) -> str:
        """追踪NATS发布"""
        return self.tracer.start_span(
            "nats_publish",
            parent_span_id,
            subject=subject,
            component="nats_client"
        )
    
    def trace_storage_write(self, storage_type: str, parent_span_id: str) -> str:
        """追踪存储写入"""
        return self.tracer.start_span(
            "storage_write",
            parent_span_id,
            storage_type=storage_type,
            component="storage_manager"
        )


# 全局追踪器实例
_global_tracer: Optional[DistributedTracer] = None
_global_market_tracer: Optional[MarketDataTracer] = None


def get_tracer() -> DistributedTracer:
    """获取全局追踪器"""
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = DistributedTracer()
    return _global_tracer


def get_market_tracer() -> MarketDataTracer:
    """获取市场数据追踪器"""
    global _global_market_tracer
    if _global_market_tracer is None:
        _global_market_tracer = MarketDataTracer(get_tracer())
    return _global_market_tracer
