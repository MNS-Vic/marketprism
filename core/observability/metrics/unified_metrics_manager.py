"""
统一指标管理器

统一管理系统中所有监控指标，提供标准化的指标收集、存储和导出功能。
"""

import threading
import time
import logging
from typing import Dict, List, Optional, Any, Union, Callable, Set
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from collections import defaultdict, deque
import asyncio
from contextlib import contextmanager
import re

from .metric_categories import (
    MetricDefinition, MetricType, MetricCategory, MetricSubCategory,
    MetricSeverity, StandardMetrics, MetricNamingStandards
)
from .metric_registry import MetricRegistry, MetricInstance, MetricValue, get_global_registry

logger = logging.getLogger(__name__)


@dataclass
class MetricEvent:
    """指标事件"""
    metric_name: str
    operation: str  # set, increment, observe
    value: Union[int, float]
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    """告警规则"""
    metric_name: str
    condition: str  # >, <, >=, <=, ==, !=
    threshold: Union[int, float]
    severity: MetricSeverity
    message: str
    labels_filter: Dict[str, str] = field(default_factory=dict)
    duration: int = 60  # 持续时间（秒）
    enabled: bool = True


class MetricCollector:
    """指标收集器接口"""
    
    def collect_metrics(self) -> Dict[str, Any]:
        """收集指标数据"""
        raise NotImplementedError
    
    def get_collection_interval(self) -> int:
        """获取收集间隔（秒）"""
        return 60


class SystemMetricCollector(MetricCollector):
    """系统指标收集器"""
    
    def __init__(self):
        import psutil
        self.psutil = psutil
    
    def collect_metrics(self) -> Dict[str, Any]:
        """收集系统指标"""
        try:
            metrics = {}
            
            # CPU指标
            cpu_percent = self.psutil.cpu_percent(interval=0.1)
            metrics["system_cpu_usage_percent"] = cpu_percent
            
            # 内存指标
            memory = self.psutil.virtual_memory()
            metrics["system_memory_usage_bytes"] = memory.used
            metrics["system_memory_usage_percent"] = memory.percent
            metrics["system_memory_available_bytes"] = memory.available
            
            # 磁盘指标
            disk = self.psutil.disk_usage('/')
            metrics["system_disk_usage_bytes"] = disk.used
            metrics["system_disk_usage_percent"] = (disk.used / disk.total) * 100
            metrics["system_disk_free_bytes"] = disk.free
            
            # 网络指标
            network = self.psutil.net_io_counters()
            metrics["system_network_bytes_sent"] = network.bytes_sent
            metrics["system_network_bytes_recv"] = network.bytes_recv
            metrics["system_network_packets_sent"] = network.packets_sent
            metrics["system_network_packets_recv"] = network.packets_recv
            
            return metrics
            
        except Exception as e:
            logger.error(f"系统指标收集失败: {e}")
            return {}


class UnifiedMetricsManager:
    """统一指标管理器"""
    
    def __init__(self, registry: Optional[MetricRegistry] = None):
        self.registry = registry or get_global_registry()
        self.collectors: Dict[str, MetricCollector] = {}
        self.exporters: Dict[str, Callable] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, datetime] = {}
        
        self._collection_enabled = False
        self._collection_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        
        # 事件处理
        self.event_listeners: List[Callable[[MetricEvent], None]] = []
        self.event_queue: deque = deque(maxlen=10000)
        
        # 统计信息
        self.stats = {
            "metrics_collected": 0,
            "events_processed": 0,
            "alerts_triggered": 0,
            "collection_errors": 0,
            "started_at": time.time(),
            "last_collection": None
        }
        
        # 初始化
        self._initialize()
    
    def _initialize(self) -> None:
        """初始化管理器"""
        # 注册系统指标收集器
        self.register_collector("system", SystemMetricCollector())
        
        # 注册内置指标
        self._register_builtin_metrics()
        
        logger.info("统一指标管理器初始化完成")
    
    def _register_builtin_metrics(self) -> None:
        """注册内置指标"""
        # 管理器自身的指标
        manager_metrics = [
            MetricDefinition(
                name="metrics_manager_collections_total",
                metric_type=MetricType.COUNTER,
                category=MetricCategory.SYSTEM,
                description="指标收集总次数",
                help_text="指标管理器执行的收集操作总数"
            ),
            MetricDefinition(
                name="metrics_manager_events_processed_total",
                metric_type=MetricType.COUNTER,
                category=MetricCategory.SYSTEM,
                description="处理的指标事件总数",
                help_text="指标管理器处理的事件总数"
            ),
            MetricDefinition(
                name="metrics_manager_alerts_total",
                metric_type=MetricType.COUNTER,
                category=MetricCategory.RELIABILITY,
                description="触发的告警总数",
                labels=["severity", "metric_name"],
                help_text="按严重性和指标名称分组的告警总数"
            ),
            MetricDefinition(
                name="metrics_manager_collection_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                category=MetricCategory.PERFORMANCE,
                description="指标收集耗时",
                unit="seconds",
                labels=["collector"],
                help_text="各收集器的收集时间分布"
            )
        ]
        
        for metric_def in manager_metrics:
            try:
                self.registry.register_metric(metric_def)
            except Exception as e:
                logger.error(f"注册内置指标失败 {metric_def.name}: {e}")
    
    def register_collector(self, name: str, collector: MetricCollector) -> None:
        """注册指标收集器"""
        with self._lock:
            self.collectors[name] = collector
            logger.info(f"注册指标收集器: {name}")
    
    def unregister_collector(self, name: str) -> bool:
        """注销指标收集器"""
        with self._lock:
            if name in self.collectors:
                del self.collectors[name]
                logger.info(f"注销指标收集器: {name}")
                return True
            return False
    
    def register_exporter(self, name: str, exporter: Callable) -> None:
        """注册指标导出器"""
        with self._lock:
            self.exporters[name] = exporter
            logger.info(f"注册指标导出器: {name}")
    
    def add_event_listener(self, listener: Callable[[MetricEvent], None]) -> None:
        """添加事件监听器"""
        self.event_listeners.append(listener)
    
    def remove_event_listener(self, listener: Callable[[MetricEvent], None]) -> None:
        """移除事件监听器"""
        if listener in self.event_listeners:
            self.event_listeners.remove(listener)
    
    def _emit_event(self, event: MetricEvent) -> None:
        """发出指标事件"""
        self.event_queue.append(event)
        
        for listener in self.event_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"事件监听器执行失败: {e}")
        
        self.stats["events_processed"] += 1
    
    # 指标操作方法
    def increment(self, metric_name: str, amount: Union[int, float] = 1,
                 labels: Dict[str, str] = None) -> None:
        """增加计数器"""
        metric = self.registry.get_metric(metric_name)
        if not metric:
            logger.warning(f"指标不存在: {metric_name}")
            return
        
        try:
            metric.increment(amount, labels)
            self._emit_event(MetricEvent(
                metric_name=metric_name,
                operation="increment",
                value=amount,
                labels=labels or {}
            ))
        except Exception as e:
            logger.error(f"增加计数器失败 {metric_name}: {e}")
    
    def counter(self, metric_name: str, amount: Union[int, float] = 1,
               labels: Dict[str, str] = None) -> None:
        """计数器方法（increment的别名）"""
        self.increment(metric_name, amount, labels)
    
    def set_gauge(self, metric_name: str, value: Union[int, float],
                 labels: Dict[str, str] = None) -> None:
        """设置仪表值"""
        metric = self.registry.get_metric(metric_name)
        if not metric:
            logger.warning(f"指标不存在: {metric_name}")
            return

        try:
            metric.set_value(value, labels)
            self._emit_event(MetricEvent(
                metric_name=metric_name,
                operation="set",
                value=value,
                labels=labels or {}
            ))
        except Exception as e:
            logger.error(f"设置仪表值失败 {metric_name}: {e}")

    def gauge(self, metric_name: str, value: Union[int, float],
             labels: Dict[str, str] = None) -> None:
        """设置仪表值（set_gauge的别名）"""
        self.set_gauge(metric_name, value, labels)
    
    def observe_histogram(self, metric_name: str, value: float,
                         labels: Dict[str, str] = None,
                         buckets: List[float] = None) -> None:
        """观察直方图值"""
        metric = self.registry.get_metric(metric_name)
        if not metric:
            logger.warning(f"指标不存在: {metric_name}")
            return
        
        try:
            metric.observe_histogram(value, labels, buckets)
            self._emit_event(MetricEvent(
                metric_name=metric_name,
                operation="observe",
                value=value,
                labels=labels or {}
            ))
        except Exception as e:
            logger.error(f"观察直方图值失败 {metric_name}: {e}")
    
    def observe_summary(self, metric_name: str, value: float,
                       labels: Dict[str, str] = None) -> None:
        """观察摘要值"""
        metric = self.registry.get_metric(metric_name)
        if not metric:
            logger.warning(f"指标不存在: {metric_name}")
            return
        
        try:
            metric.observe_summary(value, labels)
            self._emit_event(MetricEvent(
                metric_name=metric_name,
                operation="observe",
                value=value,
                labels=labels or {}
            ))
        except Exception as e:
            logger.error(f"观察摘要值失败 {metric_name}: {e}")
    
    @contextmanager
    def timer(self, metric_name: str, labels: Dict[str, str] = None):
        """计时器上下文管理器"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.observe_histogram(metric_name, duration, labels)
    
    # 收集和导出
    def start_collection(self, interval: int = 60) -> None:
        """开始指标收集"""
        if self._collection_enabled:
            logger.warning("指标收集已经启动")
            return
        
        self._collection_enabled = True
        self._stop_event.clear()
        
        self._collection_thread = threading.Thread(
            target=self._collection_loop,
            args=(interval,),
            daemon=True,
            name="MetricsCollection"
        )
        self._collection_thread.start()
        
        logger.info(f"启动指标收集，间隔: {interval}秒")
    
    def stop_collection(self) -> None:
        """停止指标收集"""
        if not self._collection_enabled:
            return
        
        self._collection_enabled = False
        self._stop_event.set()
        
        if self._collection_thread:
            self._collection_thread.join(timeout=5)
            self._collection_thread = None
        
        logger.info("停止指标收集")
    
    def _collection_loop(self, interval: int) -> None:
        """收集循环"""
        while self._collection_enabled and not self._stop_event.wait(interval):
            try:
                self._collect_all_metrics()
            except Exception as e:
                logger.error(f"指标收集出错: {e}")
                self.stats["collection_errors"] += 1
    
    def _collect_all_metrics(self) -> None:
        """收集所有指标"""
        collection_start = time.time()
        
        for collector_name, collector in self.collectors.items():
            try:
                with self.timer("metrics_manager_collection_duration_seconds", 
                              {"collector": collector_name}):
                    metrics = collector.collect_metrics()
                    
                    # 更新指标
                    for metric_name, value in metrics.items():
                        if isinstance(value, (int, float)):
                            self.set_gauge(metric_name, value)
                        elif isinstance(value, dict) and "value" in value:
                            labels = value.get("labels", {})
                            self.set_gauge(metric_name, value["value"], labels)
                
            except Exception as e:
                logger.error(f"收集器 {collector_name} 执行失败: {e}")
                self.stats["collection_errors"] += 1
        
        # 更新统计
        self.stats["metrics_collected"] += 1
        self.stats["last_collection"] = datetime.now(timezone.utc).isoformat()
        
        # 增加收集次数指标
        self.increment("metrics_manager_collections_total")
        
        collection_duration = time.time() - collection_start
        logger.debug(f"指标收集完成，耗时: {collection_duration:.3f}秒")
    
    def export_metrics(self, format_name: str = "prometheus") -> Optional[str]:
        """导出指标"""
        exporter = self.exporters.get(format_name)
        if not exporter:
            logger.error(f"导出器不存在: {format_name}")
            return None
        
        try:
            return exporter(self.registry.get_all_metrics())
        except Exception as e:
            logger.error(f"导出指标失败 {format_name}: {e}")
            return None
    
    def export_to_text(self) -> str:
        """导出指标为文本格式（Prometheus格式）"""
        try:
            # 如果有prometheus导出器，使用它
            if "prometheus" in self.exporters:
                return self.exporters["prometheus"](self.registry.get_all_metrics())
            
            # 否则生成基本的指标文本
            lines = []
            lines.append("# MarketPrism Metrics")
            lines.append(f"# Generated at {time.time()}")
            
            # 添加管理器统计信息
            for key, value in self.stats.items():
                if isinstance(value, (int, float)):
                    lines.append(f"metrics_manager_{key} {value}")
            
            # 添加注册表中的指标
            try:
                all_metrics = self.registry.get_all_metrics()
                for metric_name, metric_data in all_metrics.items():
                    if isinstance(metric_data, dict) and 'value' in metric_data:
                        value = metric_data['value']
                        if isinstance(value, (int, float)):
                            lines.append(f"{metric_name} {value}")
            except Exception as e:
                logger.error(f"获取注册表指标失败: {e}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"导出指标文本失败: {e}")
            return f"# Error exporting metrics: {e}"
    
    # 告警管理
    def add_alert_rule(self, rule: "AlertRule"):
        """添加告警规则"""
        self.alert_rules[rule.name] = rule
        logger.info(f"添加告警规则: {rule.name} {rule.condition} {rule.threshold}")
    
    def remove_alert_rule(self, rule_name: str) -> bool:
        """移除告警规则"""
        if rule_name in self.alert_rules:
            del self.alert_rules[rule_name]
            logger.info(f"移除告警规则: {rule_name}")
            return True
        return False
    
    def check_alerts(self) -> List[Dict[str, Any]]:
        """检查告警"""
        triggered_alerts = []
        
        for rule_name, rule in self.alert_rules.items():
            if not rule.enabled:
                continue
            
            # 从条件中提取指标名称
            # 这是一个简单的实现，可以根据需要变得更复杂
            match = re.search(r"(\w+)", rule.condition)
            if not match:
                continue
            
            metric_name = match.group(1)
            metric = self.registry.get_metric(metric_name)
            
            if not metric:
                continue

            try:
                for label_key, metric_value in metric.get_values().items():
                    if self._matches_labels(metric_value.labels, rule.labels_filter):
                        if self._evaluate_condition(metric_value.value, rule.condition, rule.threshold):
                            alert_key = f"{rule_name}_{label_key}"
                            now = datetime.now(timezone.utc)
                            
                            if alert_key not in self.active_alerts or \
                               (now - self.active_alerts[alert_key]['first_triggered']).total_seconds() >= rule.duration:
                                
                                if alert_key not in self.active_alerts:
                                    self.active_alerts[alert_key] = {'first_triggered': now, 'last_alerted': now}
                                
                                # 检查通知频率
                                if (now - self.active_alerts[alert_key]['last_alerted']).total_seconds() >= rule.notification_interval:
                                    triggered_alerts.append({
                                        "rule_name": rule_name,
                                        "metric_name": metric_name,
                                        "value": metric_value.value,
                                        "threshold": rule.threshold,
                                        "labels": metric_value.labels
                                    })
                                    self.active_alerts[alert_key]['last_alerted'] = now
                        else:
                            # 条件不满足，移除活跃告警
                            alert_key = f"{rule_name}_{label_key}"
                            self.active_alerts.pop(alert_key, None)
                            
            except Exception as e:
                logger.error(f"检查告警规则失败 {rule_name}: {e}")
        
        return triggered_alerts
    
    def _matches_labels(self, metric_labels: Dict[str, str], 
                       filter_labels: Dict[str, str]) -> bool:
        """检查标签是否匹配"""
        for key, value in filter_labels.items():
            if metric_labels.get(key) != value:
                return False
        return True
    
    def _evaluate_condition(self, value: Union[int, float], 
                          condition: str, threshold: Union[int, float]) -> bool:
        """评估条件"""
        conditions = {
            ">": lambda v, t: v > t,
            "<": lambda v, t: v < t,
            ">=": lambda v, t: v >= t,
            "<=": lambda v, t: v <= t,
            "==": lambda v, t: v == t,
            "!=": lambda v, t: v != t
        }
        
        condition_func = conditions.get(condition)
        if not condition_func:
            logger.warning(f"不支持的条件: {condition}")
            return False
        
        return condition_func(value, threshold)
    
    # 统计和状态
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self.stats["started_at"]
        
        return {
            "registry_stats": self.registry.get_stats(),
            "collectors": len(self.collectors),
            "exporters": len(self.exporters),
            "alert_rules": len(self.alert_rules),
            "active_alerts": len(self.active_alerts),
            "collection_enabled": self._collection_enabled,
            "uptime_seconds": uptime,
            "event_queue_size": len(self.event_queue),
            **self.stats
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        try:
            stats = self.get_stats()
            registry_validation = self.registry.validate_registry()
            
            health_status = {
                "healthy": True,
                "status": "OK",
                "checks": {
                    "registry": registry_validation["valid"],
                    "collection": self._collection_enabled,
                    "collectors": len(self.collectors) > 0,
                    "recent_collection": (
                        stats.get("last_collection") is not None and
                        (time.time() - time.mktime(
                            datetime.fromisoformat(stats["last_collection"]).timetuple()
                        )) < 300  # 5分钟内有收集
                    ) if stats.get("last_collection") else False
                },
                "details": {
                    "total_metrics": stats["registry_stats"]["total_metrics"],
                    "collection_errors": stats["collection_errors"],
                    "alerts_triggered": stats["alerts_triggered"],
                    "uptime": f"{stats['uptime_seconds']:.0f}s"
                }
            }
            
            # 检查是否健康
            if not all(health_status["checks"].values()):
                health_status["healthy"] = False
                health_status["status"] = "DEGRADED"
            
            if stats["collection_errors"] > 10:  # 错误太多
                health_status["healthy"] = False
                health_status["status"] = "UNHEALTHY"
            
            return health_status
            
        except Exception as e:
            logger.error(f"获取健康状态失败: {e}")
            return {
                "healthy": False,
                "status": "ERROR",
                "error": str(e)
            }
    
    def shutdown(self) -> None:
        """关闭管理器"""
        logger.info("关闭统一指标管理器")
        
        # 停止收集
        self.stop_collection()
        
        # 清理资源
        with self._lock:
            self.collectors.clear()
            self.exporters.clear()
            self.event_listeners.clear()
            self.alert_rules.clear()
            self.active_alerts.clear()
        
        logger.info("统一指标管理器已关闭")


# 全局管理器实例
_global_manager = None
_global_manager_lock = threading.Lock()


def get_global_manager() -> UnifiedMetricsManager:
    """获取全局指标管理器"""
    global _global_manager
    
    if _global_manager is None:
        with _global_manager_lock:
            if _global_manager is None:
                _global_manager = UnifiedMetricsManager()
                logger.info("初始化全局指标管理器")
    
    return _global_manager


def reset_global_manager() -> None:
    """重置全局指标管理器（主要用于测试）"""
    global _global_manager
    
    with _global_manager_lock:
        if _global_manager:
            _global_manager.shutdown()
        _global_manager = None
        logger.info("重置全局指标管理器")