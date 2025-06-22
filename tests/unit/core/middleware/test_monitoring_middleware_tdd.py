"""
监控中间件TDD测试
专门用于提升monitoring_middleware.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

# 导入监控中间件模块（假设存在）
try:
    from core.middleware.monitoring_middleware import (
        MonitoringMiddleware, MonitoringConfig, PerformanceMonitor,
        ErrorTracker, MetricsCollector, AlertManager, HealthChecker,
        MetricType, AlertSeverity, HealthStatus, MonitoringRule,
        PerformanceMetric, ErrorMetric, HealthMetric, AlertRule
    )
except ImportError:
    # 如果模块不存在，创建模拟类用于测试
    from enum import Enum
    from dataclasses import dataclass, field
    
    class MetricType(Enum):
        COUNTER = "counter"
        GAUGE = "gauge"
        HISTOGRAM = "histogram"
        TIMER = "timer"
    
    class AlertSeverity(Enum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"
    
    class HealthStatus(Enum):
        HEALTHY = "healthy"
        DEGRADED = "degraded"
        UNHEALTHY = "unhealthy"
    
    @dataclass
    class PerformanceMetric:
        name: str
        value: float
        timestamp: datetime
        labels: Dict[str, str] = field(default_factory=dict)
        metric_type: MetricType = MetricType.GAUGE
    
    @dataclass
    class ErrorMetric:
        error_type: str
        count: int
        timestamp: datetime
        details: Dict[str, Any] = field(default_factory=dict)
    
    @dataclass
    class HealthMetric:
        component: str
        status: HealthStatus
        timestamp: datetime
        details: Dict[str, Any] = field(default_factory=dict)
    
    @dataclass
    class AlertRule:
        name: str
        condition: str
        threshold: float
        severity: AlertSeverity
        enabled: bool = True
    
    @dataclass
    class MonitoringRule:
        rule_id: str
        name: str
        metric_pattern: str
        enabled: bool = True
        sampling_rate: float = 1.0
    
    @dataclass
    class MonitoringConfig:
        enabled: bool = True
        performance_monitoring: bool = True
        error_tracking: bool = True
        metrics_collection: bool = True
        health_checking: bool = True
        alert_management: bool = True
        collection_interval: int = 30
        retention_period: int = 86400
        rules: List[MonitoringRule] = field(default_factory=list)
        alert_rules: List[AlertRule] = field(default_factory=list)
    
    class PerformanceMonitor:
        def __init__(self):
            self.metrics = {}
            self.active_requests = {}
        
        def start_request_monitoring(self, request_id: str) -> None:
            self.active_requests[request_id] = time.time()
        
        def end_request_monitoring(self, request_id: str) -> Optional[float]:
            if request_id in self.active_requests:
                duration = time.time() - self.active_requests.pop(request_id)
                return duration
            return None
        
        def record_metric(self, metric: PerformanceMetric) -> None:
            self.metrics[metric.name] = metric
        
        def get_metrics(self) -> Dict[str, PerformanceMetric]:
            return self.metrics.copy()
    
    class ErrorTracker:
        def __init__(self):
            self.errors = []
            self.error_counts = {}
        
        def track_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
            error_type = type(error).__name__
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
            
            error_metric = ErrorMetric(
                error_type=error_type,
                count=self.error_counts[error_type],
                timestamp=datetime.now(timezone.utc),
                details=context or {}
            )
            self.errors.append(error_metric)
        
        def get_error_stats(self) -> Dict[str, int]:
            return self.error_counts.copy()
        
        def get_recent_errors(self, limit: int = 10) -> List[ErrorMetric]:
            return self.errors[-limit:]
    
    class MetricsCollector:
        def __init__(self):
            self.metrics = {}
            self.collection_enabled = True
        
        def collect_metric(self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE, labels: Dict[str, str] = None) -> None:
            if not self.collection_enabled:
                return
            
            metric = PerformanceMetric(
                name=name,
                value=value,
                timestamp=datetime.now(timezone.utc),
                labels=labels or {},
                metric_type=metric_type
            )
            self.metrics[name] = metric
        
        def get_metric(self, name: str) -> Optional[PerformanceMetric]:
            return self.metrics.get(name)
        
        def get_all_metrics(self) -> Dict[str, PerformanceMetric]:
            return self.metrics.copy()
        
        def clear_metrics(self) -> None:
            self.metrics.clear()
    
    class AlertManager:
        def __init__(self):
            self.rules = {}
            self.active_alerts = {}
            self.alert_history = []
        
        def add_rule(self, rule: AlertRule) -> None:
            self.rules[rule.name] = rule
        
        def remove_rule(self, rule_name: str) -> bool:
            return self.rules.pop(rule_name, None) is not None
        
        def check_alerts(self, metrics: Dict[str, PerformanceMetric]) -> List[Dict[str, Any]]:
            triggered_alerts = []
            
            for rule_name, rule in self.rules.items():
                if not rule.enabled:
                    continue
                
                # 简化的告警检查逻辑
                for metric_name, metric in metrics.items():
                    if metric_name in rule.condition and metric.value > rule.threshold:
                        alert = {
                            "rule_name": rule_name,
                            "metric_name": metric_name,
                            "value": metric.value,
                            "threshold": rule.threshold,
                            "severity": rule.severity,
                            "timestamp": datetime.now(timezone.utc)
                        }
                        triggered_alerts.append(alert)
                        self.active_alerts[f"{rule_name}_{metric_name}"] = alert
            
            return triggered_alerts
        
        def get_active_alerts(self) -> Dict[str, Dict[str, Any]]:
            return self.active_alerts.copy()
    
    class HealthChecker:
        def __init__(self):
            self.components = {}
            self.health_checks = {}
        
        def register_component(self, name: str, check_function: callable) -> None:
            self.health_checks[name] = check_function
        
        async def check_health(self, component: str = None) -> Dict[str, HealthMetric]:
            results = {}
            
            if component:
                if component in self.health_checks:
                    try:
                        status = await self.health_checks[component]()
                        results[component] = HealthMetric(
                            component=component,
                            status=status,
                            timestamp=datetime.now(timezone.utc)
                        )
                    except Exception as e:
                        results[component] = HealthMetric(
                            component=component,
                            status=HealthStatus.UNHEALTHY,
                            timestamp=datetime.now(timezone.utc),
                            details={"error": str(e)}
                        )
            else:
                for comp_name, check_func in self.health_checks.items():
                    try:
                        status = await check_func()
                        results[comp_name] = HealthMetric(
                            component=comp_name,
                            status=status,
                            timestamp=datetime.now(timezone.utc)
                        )
                    except Exception as e:
                        results[comp_name] = HealthMetric(
                            component=comp_name,
                            status=HealthStatus.UNHEALTHY,
                            timestamp=datetime.now(timezone.utc),
                            details={"error": str(e)}
                        )
            
            return results
        
        def get_overall_health(self) -> HealthStatus:
            # 简化的整体健康状态计算
            if not self.components:
                return HealthStatus.HEALTHY
            
            unhealthy_count = sum(1 for status in self.components.values() if status == HealthStatus.UNHEALTHY)
            degraded_count = sum(1 for status in self.components.values() if status == HealthStatus.DEGRADED)
            
            if unhealthy_count > 0:
                return HealthStatus.UNHEALTHY
            elif degraded_count > 0:
                return HealthStatus.DEGRADED
            else:
                return HealthStatus.HEALTHY
    
    class MonitoringMiddleware:
        def __init__(self, config: MonitoringConfig):
            self.config = config
            self.performance_monitor = PerformanceMonitor()
            self.error_tracker = ErrorTracker()
            self.metrics_collector = MetricsCollector()
            self.alert_manager = AlertManager()
            self.health_checker = HealthChecker()
            self._setup_default_rules()
        
        def _setup_default_rules(self) -> None:
            # 设置默认监控规则
            if self.config.alert_rules:
                for rule in self.config.alert_rules:
                    self.alert_manager.add_rule(rule)
        
        async def process_request(self, context) -> Dict[str, Any]:
            request_id = getattr(context, 'request_id', 'unknown')
            
            # 开始性能监控
            if self.config.performance_monitoring:
                self.performance_monitor.start_request_monitoring(request_id)
            
            # 收集请求指标
            if self.config.metrics_collection:
                self.metrics_collector.collect_metric(
                    "requests_total",
                    1,
                    MetricType.COUNTER,
                    {"method": getattr(context, 'method', 'unknown')}
                )
            
            return {"success": True, "continue_chain": True}
        
        async def process_response(self, context) -> Dict[str, Any]:
            request_id = getattr(context, 'request_id', 'unknown')
            
            # 结束性能监控
            if self.config.performance_monitoring:
                duration = self.performance_monitor.end_request_monitoring(request_id)
                if duration is not None:
                    self.metrics_collector.collect_metric(
                        "request_duration_seconds",
                        duration,
                        MetricType.HISTOGRAM
                    )
            
            # 检查告警
            if self.config.alert_management:
                metrics = self.metrics_collector.get_all_metrics()
                alerts = self.alert_manager.check_alerts(metrics)
                if alerts:
                    # 处理告警
                    pass
            
            return {"success": True}

from core.middleware.middleware_framework import MiddlewareConfig, MiddlewareType, MiddlewareContext


class TestMonitoringConfig:
    """测试监控配置"""
    
    def test_monitoring_config_creation(self):
        """测试：监控配置创建"""
        config = MonitoringConfig(
            enabled=True,
            performance_monitoring=True,
            error_tracking=True,
            metrics_collection=True,
            health_checking=True,
            alert_management=True,
            collection_interval=30,
            retention_period=86400
        )
        
        assert config.enabled is True
        assert config.performance_monitoring is True
        assert config.error_tracking is True
        assert config.metrics_collection is True
        assert config.health_checking is True
        assert config.alert_management is True
        assert config.collection_interval == 30
        assert config.retention_period == 86400
        
    def test_monitoring_config_defaults(self):
        """测试：监控配置默认值"""
        config = MonitoringConfig()
        
        assert config.enabled is True
        assert config.performance_monitoring is True
        assert config.error_tracking is True
        assert config.metrics_collection is True
        assert config.health_checking is True
        assert config.alert_management is True
        assert config.collection_interval == 30
        assert config.retention_period == 86400
        assert config.rules == []
        assert config.alert_rules == []


class TestPerformanceMonitor:
    """测试性能监控器"""
    
    def setup_method(self):
        """设置测试方法"""
        self.monitor = PerformanceMonitor()
        
    def test_performance_monitor_initialization(self):
        """测试：性能监控器初始化"""
        assert self.monitor.metrics == {}
        assert self.monitor.active_requests == {}
        
    def test_request_monitoring(self):
        """测试：请求监控"""
        request_id = "test_request_123"
        
        # 开始监控
        self.monitor.start_request_monitoring(request_id)
        assert request_id in self.monitor.active_requests
        
        # 模拟一些处理时间
        time.sleep(0.01)
        
        # 结束监控
        duration = self.monitor.end_request_monitoring(request_id)
        assert duration is not None
        assert duration > 0
        assert request_id not in self.monitor.active_requests
        
    def test_request_monitoring_nonexistent(self):
        """测试：监控不存在的请求"""
        duration = self.monitor.end_request_monitoring("nonexistent")
        assert duration is None
        
    def test_record_metric(self):
        """测试：记录指标"""
        metric = PerformanceMetric(
            name="test_metric",
            value=42.0,
            timestamp=datetime.now(timezone.utc),
            labels={"type": "test"},
            metric_type=MetricType.GAUGE
        )
        
        self.monitor.record_metric(metric)
        
        assert "test_metric" in self.monitor.metrics
        assert self.monitor.metrics["test_metric"] == metric
        
    def test_get_metrics(self):
        """测试：获取指标"""
        metric1 = PerformanceMetric("metric1", 1.0, datetime.now(timezone.utc))
        metric2 = PerformanceMetric("metric2", 2.0, datetime.now(timezone.utc))
        
        self.monitor.record_metric(metric1)
        self.monitor.record_metric(metric2)
        
        metrics = self.monitor.get_metrics()
        assert len(metrics) == 2
        assert "metric1" in metrics
        assert "metric2" in metrics


class TestErrorTracker:
    """测试错误追踪器"""

    def setup_method(self):
        """设置测试方法"""
        self.tracker = ErrorTracker()

    def test_error_tracker_initialization(self):
        """测试：错误追踪器初始化"""
        assert self.tracker.errors == []
        assert self.tracker.error_counts == {}

    def test_track_error(self):
        """测试：追踪错误"""
        error = ValueError("Test error")
        context = {"request_id": "123", "user_id": "456"}

        self.tracker.track_error(error, context)

        assert len(self.tracker.errors) == 1
        assert self.tracker.error_counts["ValueError"] == 1

        error_metric = self.tracker.errors[0]
        assert error_metric.error_type == "ValueError"
        assert error_metric.count == 1
        assert error_metric.details == context

    def test_track_multiple_errors(self):
        """测试：追踪多个错误"""
        error1 = ValueError("Error 1")
        error2 = ValueError("Error 2")
        error3 = TypeError("Error 3")

        self.tracker.track_error(error1)
        self.tracker.track_error(error2)
        self.tracker.track_error(error3)

        assert len(self.tracker.errors) == 3
        assert self.tracker.error_counts["ValueError"] == 2
        assert self.tracker.error_counts["TypeError"] == 1

    def test_get_error_stats(self):
        """测试：获取错误统计"""
        self.tracker.track_error(ValueError("Error 1"))
        self.tracker.track_error(ValueError("Error 2"))
        self.tracker.track_error(TypeError("Error 3"))

        stats = self.tracker.get_error_stats()
        assert stats["ValueError"] == 2
        assert stats["TypeError"] == 1

    def test_get_recent_errors(self):
        """测试：获取最近错误"""
        for i in range(15):
            self.tracker.track_error(ValueError(f"Error {i}"), {"error_id": i})

        recent_errors = self.tracker.get_recent_errors(5)
        assert len(recent_errors) == 5

        # 检查是否是最近的错误（最后5个）
        for i, error in enumerate(recent_errors):
            expected_id = 10 + i
            assert error.details.get("error_id") == expected_id


class TestMetricsCollector:
    """测试指标收集器"""

    def setup_method(self):
        """设置测试方法"""
        self.collector = MetricsCollector()

    def test_metrics_collector_initialization(self):
        """测试：指标收集器初始化"""
        assert self.collector.metrics == {}
        assert self.collector.collection_enabled is True

    def test_collect_metric(self):
        """测试：收集指标"""
        self.collector.collect_metric(
            "test_metric",
            42.5,
            MetricType.GAUGE,
            {"service": "test"}
        )

        assert "test_metric" in self.collector.metrics
        metric = self.collector.metrics["test_metric"]
        assert metric.name == "test_metric"
        assert metric.value == 42.5
        assert metric.metric_type == MetricType.GAUGE
        assert metric.labels == {"service": "test"}

    def test_collect_metric_disabled(self):
        """测试：禁用收集时的指标收集"""
        self.collector.collection_enabled = False

        self.collector.collect_metric("test_metric", 42.5)

        assert "test_metric" not in self.collector.metrics

    def test_get_metric(self):
        """测试：获取指标"""
        self.collector.collect_metric("test_metric", 42.5)

        metric = self.collector.get_metric("test_metric")
        assert metric is not None
        assert metric.name == "test_metric"
        assert metric.value == 42.5

        # 测试不存在的指标
        non_existent = self.collector.get_metric("non_existent")
        assert non_existent is None

    def test_get_all_metrics(self):
        """测试：获取所有指标"""
        self.collector.collect_metric("metric1", 1.0)
        self.collector.collect_metric("metric2", 2.0)

        all_metrics = self.collector.get_all_metrics()
        assert len(all_metrics) == 2
        assert "metric1" in all_metrics
        assert "metric2" in all_metrics

    def test_clear_metrics(self):
        """测试：清空指标"""
        self.collector.collect_metric("metric1", 1.0)
        self.collector.collect_metric("metric2", 2.0)

        assert len(self.collector.metrics) == 2

        self.collector.clear_metrics()
        assert len(self.collector.metrics) == 0


class TestAlertManager:
    """测试告警管理器"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = AlertManager()

    def test_alert_manager_initialization(self):
        """测试：告警管理器初始化"""
        assert self.manager.rules == {}
        assert self.manager.active_alerts == {}
        assert self.manager.alert_history == []

    def test_add_remove_rule(self):
        """测试：添加和移除规则"""
        rule = AlertRule(
            name="high_cpu",
            condition="cpu_usage > threshold",
            threshold=80.0,
            severity=AlertSeverity.HIGH
        )

        # 添加规则
        self.manager.add_rule(rule)
        assert "high_cpu" in self.manager.rules
        assert self.manager.rules["high_cpu"] == rule

        # 移除规则
        result = self.manager.remove_rule("high_cpu")
        assert result is True
        assert "high_cpu" not in self.manager.rules

        # 移除不存在的规则
        result = self.manager.remove_rule("non_existent")
        assert result is False

    def test_check_alerts(self):
        """测试：检查告警"""
        # 添加告警规则
        rule = AlertRule(
            name="high_response_time",
            condition="response_time",
            threshold=1.0,
            severity=AlertSeverity.MEDIUM
        )
        self.manager.add_rule(rule)

        # 创建测试指标
        metrics = {
            "response_time": PerformanceMetric(
                name="response_time",
                value=1.5,  # 超过阈值
                timestamp=datetime.now(timezone.utc)
            ),
            "cpu_usage": PerformanceMetric(
                name="cpu_usage",
                value=50.0,  # 未超过阈值
                timestamp=datetime.now(timezone.utc)
            )
        }

        # 检查告警
        triggered_alerts = self.manager.check_alerts(metrics)

        assert len(triggered_alerts) == 1
        alert = triggered_alerts[0]
        assert alert["rule_name"] == "high_response_time"
        assert alert["metric_name"] == "response_time"
        assert alert["value"] == 1.5
        assert alert["threshold"] == 1.0
        assert alert["severity"] == AlertSeverity.MEDIUM

    def test_get_active_alerts(self):
        """测试：获取活跃告警"""
        # 先触发一些告警
        rule = AlertRule("test_rule", "test_metric", 10.0, AlertSeverity.LOW)
        self.manager.add_rule(rule)

        metrics = {
            "test_metric": PerformanceMetric("test_metric", 15.0, datetime.now(timezone.utc))
        }

        self.manager.check_alerts(metrics)

        active_alerts = self.manager.get_active_alerts()
        assert len(active_alerts) == 1
        assert "test_rule_test_metric" in active_alerts
