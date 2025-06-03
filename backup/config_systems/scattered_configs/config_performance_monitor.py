#!/usr/bin/env python3
"""
MarketPrism 配置性能监控器
配置管理系统 2.0 - Week 5 Day 5

高性能配置监控组件，提供实时性能指标收集、瓶颈识别和优化建议。
支持多维度性能分析、实时警报和自动调优机制。

Author: MarketPrism团队
Created: 2025-01-29
Version: 1.0.0
"""

import time
import threading
import statistics
import json
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict, deque
import asyncio
import concurrent.futures
from contextlib import contextmanager
import psutil
import uuid
import gc


class MetricType(Enum):
    """性能指标类型"""
    LATENCY = auto()          # 延迟
    THROUGHPUT = auto()       # 吞吐量
    ERROR_RATE = auto()       # 错误率
    MEMORY_USAGE = auto()     # 内存使用
    CPU_USAGE = auto()        # CPU使用
    CACHE_HIT_RATE = auto()   # 缓存命中率
    QUEUE_LENGTH = auto()     # 队列长度
    CONNECTION_COUNT = auto()  # 连接数


class AlertSeverity(Enum):
    """告警严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PerformanceThreshold(Enum):
    """性能阈值级别"""
    EXCELLENT = auto()    # 优秀 (<10ms)
    GOOD = auto()        # 良好 (10-50ms)
    ACCEPTABLE = auto()   # 可接受 (50-200ms)
    POOR = auto()        # 较差 (200-1000ms)
    CRITICAL = auto()     # 严重 (>1000ms)


@dataclass
class PerformanceMetric:
    """性能指标数据结构"""
    metric_id: str
    metric_type: MetricType
    value: float
    unit: str
    timestamp: datetime
    component: str
    operation: str
    tags: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['metric_type'] = self.metric_type.name
        return data


@dataclass
class PerformanceAlert:
    """性能告警数据结构"""
    alert_id: str
    severity: AlertSeverity
    metric_type: MetricType
    current_value: float
    threshold: float
    component: str
    operation: str
    message: str
    timestamp: datetime
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['severity'] = self.severity.value
        data['metric_type'] = self.metric_type.name
        if self.resolution_time:
            data['resolution_time'] = self.resolution_time.isoformat()
        return data


@dataclass
class PerformanceStats:
    """性能统计信息"""
    count: int = 0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    avg_value: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    std_dev: float = 0.0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    
    def update(self, value: float, timestamp: datetime):
        """更新统计信息"""
        self.count += 1
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        
        if self.first_seen is None:
            self.first_seen = timestamp
        self.last_seen = timestamp


class ConfigPerformanceMonitor:
    """配置性能监控器
    
    提供全方位的配置系统性能监控，包括：
    - 实时性能指标收集
    - 自动阈值检测和告警
    - 性能趋势分析
    - 瓶颈识别和优化建议
    - 多维度统计分析
    """
    
    def __init__(self, 
                 monitoring_interval: float = 1.0,
                 history_size: int = 10000,
                 enable_auto_gc: bool = True):
        """初始化性能监控器
        
        Args:
            monitoring_interval: 监控采样间隔（秒）
            history_size: 历史数据保留数量
            enable_auto_gc: 是否启用自动垃圾回收
        """
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size
        self.enable_auto_gc = enable_auto_gc
        
        # 性能指标存储
        self.metrics: deque = deque(maxlen=history_size)
        self.alerts: deque = deque(maxlen=history_size)
        self.stats: Dict[str, PerformanceStats] = defaultdict(PerformanceStats)
        
        # 阈值配置
        self.thresholds: Dict[MetricType, Dict[str, float]] = {
            MetricType.LATENCY: {
                'excellent': 10.0,    # ms
                'good': 50.0,
                'acceptable': 200.0,
                'poor': 1000.0
            },
            MetricType.THROUGHPUT: {
                'excellent': 10000.0,  # ops/sec
                'good': 5000.0,
                'acceptable': 1000.0,
                'poor': 100.0
            },
            MetricType.ERROR_RATE: {
                'excellent': 0.001,   # 0.1%
                'good': 0.01,         # 1%
                'acceptable': 0.05,   # 5%
                'poor': 0.1           # 10%
            },
            MetricType.MEMORY_USAGE: {
                'excellent': 100.0,   # MB
                'good': 500.0,
                'acceptable': 1000.0,
                'poor': 2000.0
            },
            MetricType.CPU_USAGE: {
                'excellent': 20.0,    # %
                'good': 50.0,
                'acceptable': 80.0,
                'poor': 95.0
            },
            MetricType.CACHE_HIT_RATE: {
                'excellent': 0.95,    # 95%
                'good': 0.90,         # 90%
                'acceptable': 0.80,   # 80%
                'poor': 0.50          # 50%
            }
        }
        
        # 告警回调函数
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        self.metric_callbacks: List[Callable[[PerformanceMetric], None]] = []
        
        # 控制变量
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # 性能计数器
        self._operation_counters: Dict[str, int] = defaultdict(int)
        self._timing_data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # 系统资源监控
        self._process = psutil.Process()
        
        # 指标聚合器
        self._metric_aggregators: Dict[str, List[float]] = defaultdict(list)
        self._aggregation_window = timedelta(minutes=1)
        
    def start_monitoring(self):
        """启动性能监控"""
        if self._monitoring:
            return
            
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="ConfigPerformanceMonitor"
        )
        self._monitor_thread.start()
        
    def stop_monitoring(self):
        """停止性能监控"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
            
    def record_metric(self, 
                     metric_type: MetricType,
                     value: float,
                     component: str,
                     operation: str,
                     unit: str = "",
                     tags: Optional[Dict[str, Any]] = None) -> str:
        """记录性能指标
        
        Args:
            metric_type: 指标类型
            value: 指标值
            component: 组件名称
            operation: 操作名称
            unit: 单位
            tags: 附加标签
            
        Returns:
            指标ID
        """
        metric_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        metric = PerformanceMetric(
            metric_id=metric_id,
            metric_type=metric_type,
            value=value,
            unit=unit,
            timestamp=timestamp,
            component=component,
            operation=operation,
            tags=tags or {}
        )
        
        with self._lock:
            # 存储指标
            self.metrics.append(metric)
            
            # 更新统计信息
            stats_key = f"{component}.{operation}.{metric_type.name}"
            self.stats[stats_key].update(value, timestamp)
            
            # 聚合数据
            self._metric_aggregators[stats_key].append(value)
            
            # 检查阈值
            self._check_thresholds(metric)
            
            # 触发回调
            for callback in self.metric_callbacks:
                try:
                    callback(metric)
                except Exception as e:
                    print(f"Error in metric callback: {e}")
                    
        return metric_id
        
    @contextmanager
    def measure_operation(self, 
                         component: str, 
                         operation: str,
                         tags: Optional[Dict[str, Any]] = None):
        """测量操作耗时的上下文管理器
        
        Args:
            component: 组件名称
            operation: 操作名称
            tags: 附加标签
        """
        start_time = time.perf_counter()
        operation_key = f"{component}.{operation}"
        
        try:
            yield
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            
            # 记录延迟指标
            self.record_metric(
                MetricType.LATENCY,
                duration_ms,
                component,
                operation,
                "ms",
                tags
            )
            
            # 更新操作计数
            with self._lock:
                self._operation_counters[operation_key] += 1
                self._timing_data[operation_key].append(duration_ms)
                
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """添加告警回调函数"""
        self.alert_callbacks.append(callback)
        
    def add_metric_callback(self, callback: Callable[[PerformanceMetric], None]):
        """添加指标回调函数"""
        self.metric_callbacks.append(callback)
        
    def get_metrics(self, 
                   component: Optional[str] = None,
                   metric_type: Optional[MetricType] = None,
                   since: Optional[datetime] = None,
                   limit: Optional[int] = None) -> List[PerformanceMetric]:
        """获取性能指标
        
        Args:
            component: 组件过滤
            metric_type: 指标类型过滤
            since: 时间过滤
            limit: 数量限制
            
        Returns:
            指标列表
        """
        with self._lock:
            filtered_metrics = []
            
            for metric in reversed(self.metrics):
                # 应用过滤条件
                if component and metric.component != component:
                    continue
                if metric_type and metric.metric_type != metric_type:
                    continue
                if since and metric.timestamp < since:
                    continue
                    
                filtered_metrics.append(metric)
                
                # 应用数量限制
                if limit and len(filtered_metrics) >= limit:
                    break
                    
            return filtered_metrics
            
    def get_alerts(self, 
                  severity: Optional[AlertSeverity] = None,
                  resolved: Optional[bool] = None,
                  since: Optional[datetime] = None) -> List[PerformanceAlert]:
        """获取告警信息
        
        Args:
            severity: 严重程度过滤
            resolved: 解决状态过滤
            since: 时间过滤
            
        Returns:
            告警列表
        """
        with self._lock:
            filtered_alerts = []
            
            for alert in reversed(self.alerts):
                # 应用过滤条件
                if severity and alert.severity != severity:
                    continue
                if resolved is not None and alert.resolved != resolved:
                    continue
                if since and alert.timestamp < since:
                    continue
                    
                filtered_alerts.append(alert)
                
            return filtered_alerts
            
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        with self._lock:
            now = datetime.now()
            
            # 系统资源使用
            memory_info = self._process.memory_info()
            cpu_percent = self._process.cpu_percent()
            
            # 指标统计
            total_metrics = len(self.metrics)
            total_alerts = len(self.alerts)
            active_alerts = sum(1 for alert in self.alerts if not alert.resolved)
            
            # 最近性能
            recent_metrics = [m for m in self.metrics 
                            if (now - m.timestamp) < timedelta(minutes=5)]
            
            # 计算平均延迟
            latency_metrics = [m for m in recent_metrics 
                             if m.metric_type == MetricType.LATENCY]
            avg_latency = statistics.mean([m.value for m in latency_metrics]) if latency_metrics else 0
            
            # 计算吞吐量
            throughput_metrics = [m for m in recent_metrics 
                                if m.metric_type == MetricType.THROUGHPUT]
            avg_throughput = statistics.mean([m.value for m in throughput_metrics]) if throughput_metrics else 0
            
            # 计算错误率
            error_metrics = [m for m in recent_metrics 
                           if m.metric_type == MetricType.ERROR_RATE]
            avg_error_rate = statistics.mean([m.value for m in error_metrics]) if error_metrics else 0
            
            return {
                "timestamp": now.isoformat(),
                "monitoring_status": "active" if self._monitoring else "inactive",
                "system_resources": {
                    "memory_usage_mb": memory_info.rss / 1024 / 1024,
                    "memory_usage_percent": self._process.memory_percent(),
                    "cpu_usage_percent": cpu_percent,
                    "threads_count": self._process.num_threads()
                },
                "metrics_summary": {
                    "total_metrics": total_metrics,
                    "recent_metrics_5min": len(recent_metrics),
                    "metrics_per_second": len(recent_metrics) / 300 if recent_metrics else 0
                },
                "alerts_summary": {
                    "total_alerts": total_alerts,
                    "active_alerts": active_alerts,
                    "resolved_alerts": total_alerts - active_alerts
                },
                "performance_indicators": {
                    "avg_latency_ms": round(avg_latency, 2),
                    "avg_throughput_ops": round(avg_throughput, 2),
                    "avg_error_rate_percent": round(avg_error_rate * 100, 4),
                    "performance_level": self._assess_performance_level(avg_latency)
                },
                "operation_stats": dict(self._operation_counters),
                "top_operations": self._get_top_operations()
            }
            
    def get_component_stats(self, component: str) -> Dict[str, Any]:
        """获取组件统计信息"""
        with self._lock:
            component_metrics = [m for m in self.metrics if m.component == component]
            
            if not component_metrics:
                return {"component": component, "status": "no_data"}
                
            # 按操作分组
            operations = defaultdict(list)
            for metric in component_metrics:
                operations[metric.operation].append(metric)
                
            operation_stats = {}
            for operation, metrics in operations.items():
                latency_metrics = [m.value for m in metrics if m.metric_type == MetricType.LATENCY]
                
                if latency_metrics:
                    operation_stats[operation] = {
                        "count": len(latency_metrics),
                        "avg_latency_ms": statistics.mean(latency_metrics),
                        "min_latency_ms": min(latency_metrics),
                        "max_latency_ms": max(latency_metrics),
                        "p95_latency_ms": self._calculate_percentile(latency_metrics, 0.95),
                        "p99_latency_ms": self._calculate_percentile(latency_metrics, 0.99)
                    }
                    
            return {
                "component": component,
                "total_metrics": len(component_metrics),
                "operation_stats": operation_stats,
                "first_seen": min(m.timestamp for m in component_metrics).isoformat(),
                "last_seen": max(m.timestamp for m in component_metrics).isoformat()
            }
            
    def export_metrics(self, format_type: str = "json") -> str:
        """导出指标数据
        
        Args:
            format_type: 导出格式 (json, csv, prometheus)
            
        Returns:
            导出的数据字符串
        """
        if format_type.lower() == "json":
            return self._export_json()
        elif format_type.lower() == "csv":
            return self._export_csv()
        elif format_type.lower() == "prometheus":
            return self._export_prometheus()
        else:
            raise ValueError(f"Unsupported format: {format_type}")
            
    def clear_metrics(self, before: Optional[datetime] = None):
        """清理指标数据
        
        Args:
            before: 清理此时间之前的数据，None表示清理所有
        """
        with self._lock:
            if before is None:
                self.metrics.clear()
                self.alerts.clear()
                self.stats.clear()
                self._operation_counters.clear()
                self._timing_data.clear()
                self._metric_aggregators.clear()
            else:
                # 清理旧指标
                self.metrics = deque(
                    [m for m in self.metrics if m.timestamp >= before],
                    maxlen=self.history_size
                )
                
                # 清理旧告警
                self.alerts = deque(
                    [a for a in self.alerts if a.timestamp >= before],
                    maxlen=self.history_size
                )
                
    def _monitoring_loop(self):
        """监控循环"""
        while self._monitoring:
            try:
                # 收集系统指标
                self._collect_system_metrics()
                
                # 聚合指标
                self._aggregate_metrics()
                
                # 垃圾回收
                if self.enable_auto_gc:
                    gc.collect()
                    
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(self.monitoring_interval)
                
    def _collect_system_metrics(self):
        """收集系统指标"""
        try:
            # 内存使用
            memory_info = self._process.memory_info()
            self.record_metric(
                MetricType.MEMORY_USAGE,
                memory_info.rss / 1024 / 1024,  # MB
                "system",
                "memory_monitor",
                "MB"
            )
            
            # CPU使用
            cpu_percent = self._process.cpu_percent()
            self.record_metric(
                MetricType.CPU_USAGE,
                cpu_percent,
                "system",
                "cpu_monitor",
                "%"
            )
            
        except Exception as e:
            print(f"Error collecting system metrics: {e}")
            
    def _aggregate_metrics(self):
        """聚合指标数据"""
        try:
            with self._lock:
                now = datetime.now()
                
                for key, values in self._metric_aggregators.items():
                    if values:
                        # 计算吞吐量 (操作数/秒)
                        component, operation, metric_type = key.split('.')
                        
                        if metric_type == MetricType.LATENCY.name:
                            ops_per_sec = len(values) / 60  # 每分钟的操作数 / 60秒
                            self.record_metric(
                                MetricType.THROUGHPUT,
                                ops_per_sec,
                                component,
                                operation,
                                "ops/sec"
                            )
                            
                        # 清理旧数据
                        self._metric_aggregators[key] = []
                        
        except Exception as e:
            print(f"Error aggregating metrics: {e}")
            
    def _check_thresholds(self, metric: PerformanceMetric):
        """检查阈值并生成告警"""
        if metric.metric_type not in self.thresholds:
            return
            
        thresholds = self.thresholds[metric.metric_type]
        
        # 确定告警级别
        severity = None
        threshold_value = None
        
        if metric.metric_type in [MetricType.LATENCY, MetricType.ERROR_RATE, 
                                MetricType.MEMORY_USAGE, MetricType.CPU_USAGE]:
            # 值越高越差
            if metric.value > thresholds['poor']:
                severity = AlertSeverity.CRITICAL
                threshold_value = thresholds['poor']
            elif metric.value > thresholds['acceptable']:
                severity = AlertSeverity.HIGH
                threshold_value = thresholds['acceptable']
            elif metric.value > thresholds['good']:
                severity = AlertSeverity.MEDIUM
                threshold_value = thresholds['good']
                
        elif metric.metric_type in [MetricType.THROUGHPUT, MetricType.CACHE_HIT_RATE]:
            # 值越高越好
            if metric.value < thresholds['poor']:
                severity = AlertSeverity.CRITICAL
                threshold_value = thresholds['poor']
            elif metric.value < thresholds['acceptable']:
                severity = AlertSeverity.HIGH
                threshold_value = thresholds['acceptable']
            elif metric.value < thresholds['good']:
                severity = AlertSeverity.MEDIUM
                threshold_value = thresholds['good']
                
        if severity:
            alert = PerformanceAlert(
                alert_id=str(uuid.uuid4()),
                severity=severity,
                metric_type=metric.metric_type,
                current_value=metric.value,
                threshold=threshold_value,
                component=metric.component,
                operation=metric.operation,
                message=self._generate_alert_message(metric, severity, threshold_value),
                timestamp=metric.timestamp
            )
            
            with self._lock:
                self.alerts.append(alert)
                
            # 触发告警回调
            for callback in self.alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    print(f"Error in alert callback: {e}")
                    
    def _generate_alert_message(self, 
                              metric: PerformanceMetric, 
                              severity: AlertSeverity,
                              threshold: float) -> str:
        """生成告警消息"""
        return (f"{severity.value.upper()} alert: {metric.component}.{metric.operation} "
                f"{metric.metric_type.name.lower()} is {metric.value:.2f}{metric.unit}, "
                f"exceeding {threshold:.2f}{metric.unit} threshold")
                
    def _assess_performance_level(self, avg_latency: float) -> str:
        """评估性能级别"""
        if avg_latency < 10:
            return "excellent"
        elif avg_latency < 50:
            return "good"
        elif avg_latency < 200:
            return "acceptable"
        elif avg_latency < 1000:
            return "poor"
        else:
            return "critical"
            
    def _get_top_operations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取热门操作"""
        with self._lock:
            sorted_ops = sorted(
                self._operation_counters.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            top_ops = []
            for operation_key, count in sorted_ops[:limit]:
                timing_data = self._timing_data.get(operation_key, [])
                avg_latency = statistics.mean(timing_data) if timing_data else 0
                
                top_ops.append({
                    "operation": operation_key,
                    "count": count,
                    "avg_latency_ms": round(avg_latency, 2)
                })
                
            return top_ops
            
    def _calculate_percentile(self, values: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not values:
            return 0.0
            
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile)
        return sorted_values[min(index, len(sorted_values) - 1)]
        
    def _export_json(self) -> str:
        """导出JSON格式"""
        with self._lock:
            data = {
                "timestamp": datetime.now().isoformat(),
                "metrics": [metric.to_dict() for metric in self.metrics],
                "alerts": [alert.to_dict() for alert in self.alerts],
                "summary": self.get_performance_summary()
            }
            return json.dumps(data, indent=2, ensure_ascii=False)
            
    def _export_csv(self) -> str:
        """导出CSV格式"""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入头部
        writer.writerow([
            'timestamp', 'metric_type', 'value', 'unit', 
            'component', 'operation', 'tags'
        ])
        
        # 写入数据
        with self._lock:
            for metric in self.metrics:
                writer.writerow([
                    metric.timestamp.isoformat(),
                    metric.metric_type.name,
                    metric.value,
                    metric.unit,
                    metric.component,
                    metric.operation,
                    json.dumps(metric.tags)
                ])
                
        return output.getvalue()
        
    def _export_prometheus(self) -> str:
        """导出Prometheus格式"""
        lines = []
        
        with self._lock:
            # 按指标类型分组
            metrics_by_type = defaultdict(list)
            for metric in self.metrics:
                metrics_by_type[metric.metric_type].append(metric)
                
            for metric_type, metrics in metrics_by_type.items():
                metric_name = f"config_{metric_type.name.lower()}"
                
                # 添加HELP和TYPE注释
                lines.append(f"# HELP {metric_name} {metric_type.name} metric")
                lines.append(f"# TYPE {metric_name} gauge")
                
                # 添加指标数据
                for metric in metrics[-100:]:  # 只导出最近100个
                    labels = f'component="{metric.component}",operation="{metric.operation}"'
                    if metric.tags:
                        tag_labels = ','.join(f'{k}="{v}"' for k, v in metric.tags.items())
                        labels += f",{tag_labels}"
                        
                    timestamp_ms = int(metric.timestamp.timestamp() * 1000)
                    lines.append(f"{metric_name}{{{labels}}} {metric.value} {timestamp_ms}")
                    
        return '\n'.join(lines)


# 全局监控器实例
_global_monitor: Optional[ConfigPerformanceMonitor] = None


def get_performance_monitor() -> ConfigPerformanceMonitor:
    """获取全局性能监控器实例"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = ConfigPerformanceMonitor()
        _global_monitor.start_monitoring()
    return _global_monitor


def monitor_performance(component: str, operation: str, tags: Optional[Dict[str, Any]] = None):
    """性能监控装饰器
    
    Args:
        component: 组件名称
        operation: 操作名称
        tags: 附加标签
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            with monitor.measure_operation(component, operation, tags):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# 使用示例
if __name__ == "__main__":
    # 创建监控器
    monitor = ConfigPerformanceMonitor(monitoring_interval=0.5)
    
    # 添加告警回调
    def alert_handler(alert: PerformanceAlert):
        print(f"🚨 {alert.severity.value.upper()}: {alert.message}")
        
    monitor.add_alert_callback(alert_handler)
    
    # 启动监控
    monitor.start_monitoring()
    
    # 模拟一些操作
    import random
    
    for i in range(20):
        # 模拟配置加载操作
        latency = random.uniform(5, 150)
        monitor.record_metric(
            MetricType.LATENCY,
            latency,
            "config_loader",
            "load_config",
            "ms"
        )
        
        # 模拟缓存操作
        hit_rate = random.uniform(0.7, 0.99)
        monitor.record_metric(
            MetricType.CACHE_HIT_RATE,
            hit_rate,
            "config_cache",
            "get_config",
            "ratio"
        )
        
        time.sleep(0.1)
        
    # 测试上下文管理器
    @monitor_performance("test_component", "test_operation")
    def test_function():
        time.sleep(random.uniform(0.01, 0.1))
        
    for _ in range(10):
        test_function()
        
    time.sleep(2)
    
    # 显示性能摘要
    summary = monitor.get_performance_summary()
    print("\n=== 性能摘要 ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    # 显示告警
    alerts = monitor.get_alerts()
    if alerts:
        print(f"\n=== 告警信息 ({len(alerts)}条) ===")
        for alert in alerts:
            print(f"- {alert.severity.value}: {alert.message}")
            
    # 停止监控
    monitor.stop_monitoring()
    
    print("\n✅ 配置性能监控器演示完成")