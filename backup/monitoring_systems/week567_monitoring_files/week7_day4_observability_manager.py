#!/usr/bin/env python3
"""
Week 7 Day 4: 可观测性和监控系统
MarketPrism Observability and Monitoring System

企业级可观测性平台，提供完整的监控、告警、追踪和分析能力
"""

import asyncio
import json
import time
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from abc import ABC, abstractmethod
import logging
from collections import defaultdict, deque
import statistics
import random

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('observability_system.log')
    ]
)
logger = logging.getLogger(__name__)

# ===================== 数据模型定义 =====================

class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"          # 计数器 - 累积型指标
    GAUGE = "gauge"              # 仪表 - 瞬时值指标
    HISTOGRAM = "histogram"      # 直方图 - 分布统计
    SUMMARY = "summary"          # 摘要 - 分位数统计
    CUSTOM = "custom"            # 自定义 - 业务指标

class LogLevel(Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AlertSeverity(Enum):
    """告警严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ComponentStatus(Enum):
    """组件状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DOWN = "down"

@dataclass
class MetricPoint:
    """指标数据点"""
    name: str
    value: Union[int, float]
    labels: Dict[str, str]
    timestamp: datetime
    metric_type: MetricType

@dataclass
class LogEntry:
    """日志条目"""
    timestamp: datetime
    level: LogLevel
    message: str
    source: str
    labels: Dict[str, str]
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

@dataclass
class TraceSpan:
    """追踪跨度"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_ms: Optional[float]
    tags: Dict[str, str]
    logs: List[Dict[str, Any]]
    status: str = "ok"

@dataclass
class Alert:
    """告警"""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    source: str
    labels: Dict[str, str]
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None

@dataclass
class SLOConfig:
    """SLO配置"""
    name: str
    description: str
    sli_query: str
    target: float  # 目标值 (例如 99.9%)
    error_budget_burn_rate: float
    time_window: str  # 例如 "30d", "7d"
    alert_threshold: float

# ===================== 核心组件实现 =====================

class MetricsCollector:
    """指标收集器 - 多维度指标收集和存储"""
    
    def __init__(self):
        self.metrics_store: Dict[str, List[MetricPoint]] = defaultdict(list)
        self.aggregations: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.retention_policy = {"default": timedelta(days=30)}
        self.compression_ratio = 0.8
        
    async def collect_metric(self, metric: MetricPoint) -> bool:
        """收集指标"""
        try:
            # 验证指标数据
            if not metric.name or metric.value is None:
                return False
                
            # 存储指标
            self.metrics_store[metric.name].append(metric)
            
            # 实时聚合
            await self._update_aggregations(metric)
            
            # 应用保留策略
            await self._apply_retention_policy(metric.name)
            
            logger.debug(f"收集指标: {metric.name}={metric.value}")
            return True
            
        except Exception as e:
            logger.error(f"指标收集失败: {e}")
            return False
    
    async def _update_aggregations(self, metric: MetricPoint):
        """更新聚合数据"""
        key = metric.name
        
        if key not in self.aggregations:
            self.aggregations[key] = {
                "count": 0,
                "sum": 0,
                "min": float('inf'),
                "max": float('-inf'),
                "avg": 0,
                "last_value": 0,
                "rate": 0,
                "percentiles": {}
            }
        
        agg = self.aggregations[key]
        agg["count"] += 1
        agg["sum"] += metric.value
        agg["min"] = min(agg["min"], metric.value)
        agg["max"] = max(agg["max"], metric.value)
        agg["avg"] = agg["sum"] / agg["count"]
        agg["last_value"] = metric.value
        
        # 计算百分位数
        values = [m.value for m in self.metrics_store[key]]
        if len(values) >= 10:  # 足够的数据点
            agg["percentiles"] = {
                "p50": statistics.median(values),
                "p95": statistics.quantiles(values, n=20)[18] if len(values) > 20 else max(values),
                "p99": statistics.quantiles(values, n=100)[98] if len(values) > 100 else max(values)
            }
    
    async def _apply_retention_policy(self, metric_name: str):
        """应用数据保留策略"""
        retention = self.retention_policy.get(metric_name, self.retention_policy["default"])
        cutoff_time = datetime.now() - retention
        
        # 移除过期数据
        self.metrics_store[metric_name] = [
            m for m in self.metrics_store[metric_name] 
            if m.timestamp > cutoff_time
        ]
    
    async def query_metrics(self, metric_name: str, 
                          start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None,
                          labels: Optional[Dict[str, str]] = None) -> List[MetricPoint]:
        """查询指标"""
        try:
            metrics = self.metrics_store.get(metric_name, [])
            
            # 时间过滤
            if start_time:
                metrics = [m for m in metrics if m.timestamp >= start_time]
            if end_time:
                metrics = [m for m in metrics if m.timestamp <= end_time]
            
            # 标签过滤
            if labels:
                metrics = [
                    m for m in metrics 
                    if all(m.labels.get(k) == v for k, v in labels.items())
                ]
            
            return metrics
            
        except Exception as e:
            logger.error(f"指标查询失败: {e}")
            return []
    
    async def get_aggregations(self, metric_name: str) -> Dict[str, Any]:
        """获取聚合数据"""
        return self.aggregations.get(metric_name, {})
    
    async def compress_data(self) -> Dict[str, Any]:
        """数据压缩"""
        compressed_size = 0
        original_size = 0
        
        for metric_name, points in self.metrics_store.items():
            original_size += len(points)
            # 模拟压缩 - 保留关键数据点
            if len(points) > 1000:
                # 保留最新的500个点 + 采样的500个历史点
                recent_points = points[-500:]
                sampled_points = points[:-500:max(1, len(points[:-500]) // 500)]
                self.metrics_store[metric_name] = recent_points + sampled_points
                compressed_size += len(self.metrics_store[metric_name])
            else:
                compressed_size += len(points)
        
        compression_ratio = 1 - (compressed_size / max(original_size, 1))
        return {
            "original_size": original_size,
            "compressed_size": compressed_size,
            "compression_ratio": compression_ratio
        }

class LogAggregator:
    """日志聚合器 - 多源日志收集和分析"""
    
    def __init__(self):
        self.log_store: List[LogEntry] = []
        self.index: Dict[str, List[int]] = defaultdict(list)  # 倒排索引
        self.retention_days = 30
        self.max_logs = 100000
        
    async def ingest_log(self, log_entry: LogEntry) -> bool:
        """接收日志"""
        try:
            # 添加到存储
            self.log_store.append(log_entry)
            
            # 更新索引
            log_index = len(self.log_store) - 1
            await self._update_index(log_entry, log_index)
            
            # 应用保留策略
            await self._apply_log_retention()
            
            logger.debug(f"接收日志: {log_entry.level} - {log_entry.message[:100]}")
            return True
            
        except Exception as e:
            logger.error(f"日志接收失败: {e}")
            return False
    
    async def _update_index(self, log_entry: LogEntry, index: int):
        """更新搜索索引"""
        # 索引关键字段
        keywords = [
            log_entry.level.value,
            log_entry.source,
            *log_entry.message.split(),
            *log_entry.labels.keys(),
            *log_entry.labels.values()
        ]
        
        for keyword in keywords:
            if isinstance(keyword, str) and len(keyword) > 1:  # 忽略太短的词
                self.index[keyword.lower()].append(index)
    
    async def _apply_log_retention(self):
        """应用日志保留策略"""
        # 按时间保留
        cutoff_time = datetime.now() - timedelta(days=self.retention_days)
        valid_logs = []
        new_index = defaultdict(list)
        
        for i, log in enumerate(self.log_store):
            if log.timestamp > cutoff_time:
                new_index_pos = len(valid_logs)
                valid_logs.append(log)
                
                # 重建索引
                keywords = [
                    log.level.value,
                    log.source,
                    *log.message.split(),
                    *log.labels.keys(),
                    *log.labels.values()
                ]
                
                for keyword in keywords:
                    if isinstance(keyword, str) and len(keyword) > 1:
                        new_index[keyword.lower()].append(new_index_pos)
        
        # 按数量保留 - 如果还是太多，保留最新的
        if len(valid_logs) > self.max_logs:
            valid_logs = valid_logs[-self.max_logs:]
            # 重建索引
            new_index = defaultdict(list)
            for i, log in enumerate(valid_logs):
                keywords = [
                    log.level.value,
                    log.source,
                    *log.message.split(),
                    *log.labels.keys(),
                    *log.labels.values()
                ]
                
                for keyword in keywords:
                    if isinstance(keyword, str) and len(keyword) > 1:
                        new_index[keyword.lower()].append(i)
        
        self.log_store = valid_logs
        self.index = new_index
    
    async def search_logs(self, query: str, 
                         level: Optional[LogLevel] = None,
                         source: Optional[str] = None,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         limit: int = 100) -> List[LogEntry]:
        """搜索日志"""
        try:
            # 全文搜索
            matching_indices = set()
            query_terms = query.lower().split()
            
            if query_terms:
                # 获取第一个词的匹配
                first_term = query_terms[0]
                if first_term in self.index:
                    matching_indices = set(self.index[first_term])
                    
                    # 与其他词求交集
                    for term in query_terms[1:]:
                        if term in self.index:
                            matching_indices &= set(self.index[term])
                        else:
                            matching_indices = set()  # 没有匹配
                            break
            else:
                # 没有查询词，返回所有
                matching_indices = set(range(len(self.log_store)))
            
            # 应用过滤器
            results = []
            for i in matching_indices:
                if i < len(self.log_store):
                    log = self.log_store[i]
                    
                    # 级别过滤
                    if level and log.level != level:
                        continue
                    
                    # 来源过滤
                    if source and log.source != source:
                        continue
                    
                    # 时间过滤
                    if start_time and log.timestamp < start_time:
                        continue
                    if end_time and log.timestamp > end_time:
                        continue
                    
                    results.append(log)
            
            # 按时间排序，最新的在前
            results.sort(key=lambda x: x.timestamp, reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"日志搜索失败: {e}")
            return []
    
    async def get_log_statistics(self) -> Dict[str, Any]:
        """获取日志统计"""
        try:
            total_logs = len(self.log_store)
            if total_logs == 0:
                return {"total_logs": 0}
            
            # 按级别统计
            level_counts = defaultdict(int)
            source_counts = defaultdict(int)
            hourly_counts = defaultdict(int)
            
            for log in self.log_store:
                level_counts[log.level.value] += 1
                source_counts[log.source] += 1
                hour_key = log.timestamp.strftime("%Y-%m-%d %H:00")
                hourly_counts[hour_key] += 1
            
            return {
                "total_logs": total_logs,
                "level_distribution": dict(level_counts),
                "source_distribution": dict(source_counts),
                "hourly_distribution": dict(hourly_counts),
                "index_size": len(self.index),
                "retention_days": self.retention_days
            }
            
        except Exception as e:
            logger.error(f"获取日志统计失败: {e}")
            return {"error": str(e)}

class TracingSystem:
    """分布式追踪系统 - 端到端请求追踪"""
    
    def __init__(self):
        self.traces: Dict[str, List[TraceSpan]] = defaultdict(list)
        self.span_index: Dict[str, TraceSpan] = {}
        self.sampling_rate = 0.1  # 10%采样率
        self.retention_hours = 24
        
    async def start_span(self, operation_name: str, 
                        parent_span_id: Optional[str] = None,
                        trace_id: Optional[str] = None) -> TraceSpan:
        """开始新的跨度"""
        try:
            if trace_id is None:
                trace_id = str(uuid.uuid4())
            
            span_id = str(uuid.uuid4())
            
            span = TraceSpan(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                operation_name=operation_name,
                start_time=datetime.now(),
                end_time=None,
                duration_ms=None,
                tags={},
                logs=[]
            )
            
            # 采样决策
            if random.random() < self.sampling_rate:
                self.traces[trace_id].append(span)
                self.span_index[span_id] = span
                
            logger.debug(f"开始跨度: {operation_name} (trace_id: {trace_id})")
            return span
            
        except Exception as e:
            logger.error(f"开始跨度失败: {e}")
            raise
    
    async def finish_span(self, span: TraceSpan, 
                         tags: Optional[Dict[str, str]] = None,
                         status: str = "ok") -> bool:
        """结束跨度"""
        try:
            span.end_time = datetime.now()
            span.duration_ms = (span.end_time - span.start_time).total_seconds() * 1000
            span.status = status
            
            if tags:
                span.tags.update(tags)
            
            logger.debug(f"结束跨度: {span.operation_name} (耗时: {span.duration_ms:.2f}ms)")
            return True
            
        except Exception as e:
            logger.error(f"结束跨度失败: {e}")
            return False
    
    async def add_span_log(self, span: TraceSpan, log_data: Dict[str, Any]) -> bool:
        """添加跨度日志"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                **log_data
            }
            span.logs.append(log_entry)
            return True
            
        except Exception as e:
            logger.error(f"添加跨度日志失败: {e}")
            return False
    
    async def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """获取完整追踪"""
        return self.traces.get(trace_id, [])
    
    async def find_traces(self, operation_name: Optional[str] = None,
                         min_duration_ms: Optional[float] = None,
                         max_duration_ms: Optional[float] = None,
                         tags: Optional[Dict[str, str]] = None,
                         limit: int = 100) -> List[str]:
        """查找追踪"""
        try:
            matching_trace_ids = []
            
            for trace_id, spans in self.traces.items():
                if len(matching_trace_ids) >= limit:
                    break
                    
                match = False
                for span in spans:
                    # 操作名过滤
                    if operation_name and span.operation_name != operation_name:
                        continue
                    
                    # 持续时间过滤
                    if span.duration_ms is not None:
                        if min_duration_ms and span.duration_ms < min_duration_ms:
                            continue
                        if max_duration_ms and span.duration_ms > max_duration_ms:
                            continue
                    
                    # 标签过滤
                    if tags:
                        if not all(span.tags.get(k) == v for k, v in tags.items()):
                            continue
                    
                    match = True
                    break
                
                if match:
                    matching_trace_ids.append(trace_id)
            
            return matching_trace_ids
            
        except Exception as e:
            logger.error(f"查找追踪失败: {e}")
            return []
    
    async def get_service_map(self) -> Dict[str, Any]:
        """获取服务依赖图"""
        try:
            services = set()
            dependencies = []
            
            for spans in self.traces.values():
                # 按时间排序
                sorted_spans = sorted(spans, key=lambda x: x.start_time)
                
                for span in sorted_spans:
                    service = span.tags.get("service.name", "unknown")
                    services.add(service)
                    
                    # 找到父子关系
                    if span.parent_span_id:
                        parent_span = self.span_index.get(span.parent_span_id)
                        if parent_span:
                            parent_service = parent_span.tags.get("service.name", "unknown")
                            if parent_service != service:
                                dependency = {
                                    "from": parent_service,
                                    "to": service,
                                    "operation": span.operation_name
                                }
                                if dependency not in dependencies:
                                    dependencies.append(dependency)
            
            return {
                "services": list(services),
                "dependencies": dependencies,
                "total_traces": len(self.traces),
                "total_spans": sum(len(spans) for spans in self.traces.values())
            }
            
        except Exception as e:
            logger.error(f"获取服务依赖图失败: {e}")
            return {"error": str(e)}
    
    async def cleanup_old_traces(self):
        """清理旧的追踪数据"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
            traces_to_remove = []
            
            for trace_id, spans in self.traces.items():
                if all(span.start_time < cutoff_time for span in spans):
                    traces_to_remove.append(trace_id)
            
            for trace_id in traces_to_remove:
                spans = self.traces.pop(trace_id)
                for span in spans:
                    self.span_index.pop(span.span_id, None)
            
            logger.info(f"清理了 {len(traces_to_remove)} 个过期追踪")
            
        except Exception as e:
            logger.error(f"清理追踪数据失败: {e}")

class ObservabilityManager:
    """可观测性管理器 - 统一管理和协调所有可观测性组件"""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.log_aggregator = LogAggregator()
        self.tracing_system = TracingSystem()
        
        self.status = ComponentStatus.DOWN
        self.start_time: Optional[datetime] = None
        self.components = {}
        self.health_checks = {}
        
    async def initialize(self) -> bool:
        """初始化可观测性系统"""
        try:
            logger.info("初始化可观测性系统...")
            
            # 初始化组件
            self.components = {
                "metrics_collector": self.metrics_collector,
                "log_aggregator": self.log_aggregator,
                "tracing_system": self.tracing_system
            }
            
            # 设置健康检查
            self.health_checks = {
                "metrics_collector": self._check_metrics_health,
                "log_aggregator": self._check_logs_health,
                "tracing_system": self._check_tracing_health
            }
            
            self.status = ComponentStatus.HEALTHY
            self.start_time = datetime.now()
            
            logger.info("可观测性系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            self.status = ComponentStatus.DOWN
            return False
    
    async def _check_metrics_health(self) -> Dict[str, Any]:
        """检查指标收集器健康状态"""
        try:
            metrics_count = sum(len(points) for points in self.metrics_collector.metrics_store.values())
            compression_stats = await self.metrics_collector.compress_data()
            
            return {
                "status": "healthy",
                "metrics_count": metrics_count,
                "unique_metrics": len(self.metrics_collector.metrics_store),
                "compression_ratio": compression_stats.get("compression_ratio", 0)
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_logs_health(self) -> Dict[str, Any]:
        """检查日志聚合器健康状态"""
        try:
            stats = await self.log_aggregator.get_log_statistics()
            return {
                "status": "healthy",
                **stats
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_tracing_health(self) -> Dict[str, Any]:
        """检查追踪系统健康状态"""
        try:
            service_map = await self.tracing_system.get_service_map()
            return {
                "status": "healthy",
                **service_map,
                "sampling_rate": self.tracing_system.sampling_rate
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        try:
            uptime = datetime.now() - self.start_time if self.start_time else timedelta(0)
            
            # 检查各组件健康状态
            component_health = {}
            overall_health = "healthy"
            
            for component_name, health_check in self.health_checks.items():
                health = await health_check()
                component_health[component_name] = health
                
                if health.get("status") != "healthy":
                    overall_health = "degraded"
            
            return {
                "overall_status": overall_health,
                "uptime_seconds": uptime.total_seconds(),
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "components": component_health,
                "system_info": {
                    "version": "1.0.0",
                    "environment": "production"
                }
            }
            
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return {
                "overall_status": "unhealthy",
                "error": str(e)
            }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        try:
            # 收集各组件指标
            metrics_stats = {}
            for metric_name, aggregations in self.metrics_collector.aggregations.items():
                metrics_stats[metric_name] = aggregations
            
            log_stats = await self.log_aggregator.get_log_statistics()
            service_map = await self.tracing_system.get_service_map()
            
            return {
                "metrics": {
                    "total_metrics": len(self.metrics_collector.metrics_store),
                    "aggregations": metrics_stats
                },
                "logs": log_stats,
                "tracing": service_map,
                "system": {
                    "memory_usage_mb": 0,  # 模拟
                    "cpu_usage_percent": 0,  # 模拟
                    "disk_usage_mb": 0  # 模拟
                }
            }
            
        except Exception as e:
            logger.error(f"获取系统指标失败: {e}")
            return {"error": str(e)}
    
    async def shutdown(self) -> bool:
        """关闭可观测性系统"""
        try:
            logger.info("关闭可观测性系统...")
            
            # 清理资源
            await self.tracing_system.cleanup_old_traces()
            
            self.status = ComponentStatus.DOWN
            logger.info("可观测性系统已关闭")
            return True
            
        except Exception as e:
            logger.error(f"关闭失败: {e}")
            return False

# ===================== 测试和演示函数 =====================

async def demonstrate_observability_system():
    """演示可观测性系统功能"""
    print("🔍 可观测性和监控系统演示")
    print("=" * 60)
    
    # 初始化系统
    obs_manager = ObservabilityManager()
    await obs_manager.initialize()
    
    # 1. 指标收集演示
    print("\n📊 指标收集演示:")
    metrics = [
        MetricPoint("api_requests_total", 100, {"method": "GET", "status": "200"}, datetime.now(), MetricType.COUNTER),
        MetricPoint("api_latency_ms", 150.5, {"endpoint": "/api/v1/trades"}, datetime.now(), MetricType.GAUGE),
        MetricPoint("cpu_usage_percent", 75.2, {"node": "worker-1"}, datetime.now(), MetricType.GAUGE),
        MetricPoint("memory_usage_mb", 2048, {"service": "collector"}, datetime.now(), MetricType.GAUGE)
    ]
    
    for metric in metrics:
        await obs_manager.metrics_collector.collect_metric(metric)
        print(f"  ✅ 收集指标: {metric.name} = {metric.value}")
    
    # 查询聚合数据
    aggregations = await obs_manager.metrics_collector.get_aggregations("api_latency_ms")
    print(f"  📈 延迟聚合: 平均={aggregations.get('avg', 0):.2f}ms, 最大={aggregations.get('max', 0):.2f}ms")
    
    # 2. 日志收集演示
    print("\n📝 日志收集演示:")
    logs = [
        LogEntry(datetime.now(), LogLevel.INFO, "API请求成功", "api-gateway", {"request_id": "req-001"}),
        LogEntry(datetime.now(), LogLevel.WARNING, "数据库连接超时，重试中", "collector", {"db": "clickhouse"}),
        LogEntry(datetime.now(), LogLevel.ERROR, "交易数据解析失败", "parser", {"exchange": "binance"}),
        LogEntry(datetime.now(), LogLevel.INFO, "监控检查完成", "monitor", {"status": "healthy"})
    ]
    
    for log in logs:
        await obs_manager.log_aggregator.ingest_log(log)
        print(f"  ✅ 收集日志: [{log.level.value.upper()}] {log.message[:50]}...")
    
    # 日志搜索
    search_results = await obs_manager.log_aggregator.search_logs("连接", limit=5)
    print(f"  🔍 搜索'连接': 找到 {len(search_results)} 条日志")
    
    # 3. 分布式追踪演示
    print("\n🔍 分布式追踪演示:")
    
    # 创建一个完整的追踪
    root_span = await obs_manager.tracing_system.start_span("http_request")
    root_span.tags.update({"service.name": "api-gateway", "http.method": "POST"})
    
    # 子跨度 - 数据库查询
    db_span = await obs_manager.tracing_system.start_span(
        "database_query", 
        parent_span_id=root_span.span_id,
        trace_id=root_span.trace_id
    )
    db_span.tags.update({"service.name": "database", "db.statement": "SELECT * FROM trades"})
    
    await asyncio.sleep(0.01)  # 模拟处理时间
    await obs_manager.tracing_system.finish_span(db_span, {"db.rows": "1000"})
    
    # 子跨度 - 外部API调用
    api_span = await obs_manager.tracing_system.start_span(
        "external_api_call",
        parent_span_id=root_span.span_id,
        trace_id=root_span.trace_id
    )
    api_span.tags.update({"service.name": "external-api", "http.url": "https://api.binance.com"})
    
    await asyncio.sleep(0.02)  # 模拟处理时间
    await obs_manager.tracing_system.finish_span(api_span, {"http.status_code": "200"})
    
    await obs_manager.tracing_system.finish_span(root_span, {"http.status_code": "200"})
    
    print(f"  ✅ 创建追踪: {root_span.trace_id[:8]}... (包含 3 个跨度)")
    
    # 获取追踪数据
    trace_spans = await obs_manager.tracing_system.get_trace(root_span.trace_id)
    print(f"  📊 追踪详情: 总跨度数={len(trace_spans)}, 总耗时={root_span.duration_ms:.2f}ms")
    
    # 4. 系统状态检查
    print("\n🏥 系统健康检查:")
    status = await obs_manager.get_system_status()
    print(f"  📊 总体状态: {status['overall_status'].upper()}")
    print(f"  ⏱️ 运行时间: {status['uptime_seconds']:.1f}秒")
    
    for component, health in status['components'].items():
        print(f"  🔧 {component}: {health.get('status', 'unknown').upper()}")
    
    # 5. 性能指标展示
    print("\n📈 性能指标:")
    metrics_data = await obs_manager.get_metrics()
    
    print(f"  📊 指标统计: {metrics_data['metrics']['total_metrics']} 个指标类型")
    print(f"  📝 日志统计: {metrics_data['logs'].get('total_logs', 0)} 条日志")
    print(f"  🔍 追踪统计: {metrics_data['tracing'].get('total_traces', 0)} 个追踪")
    
    # 数据压缩演示
    compression_stats = await obs_manager.metrics_collector.compress_data()
    print(f"  🗜️ 数据压缩: {compression_stats.get('compression_ratio', 0)*100:.1f}% 压缩率")
    
    print("\n✨ 可观测性系统演示完成！")
    
    await obs_manager.shutdown()
    return obs_manager

if __name__ == "__main__":
    asyncio.run(demonstrate_observability_system())