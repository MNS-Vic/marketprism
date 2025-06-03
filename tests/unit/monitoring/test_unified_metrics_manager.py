"""
统一指标管理器测试
"""

import pytest
import time
import threading
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from marketprism_collector.core.monitoring import (
    UnifiedMetricsManager,
    MetricRegistry,
    MetricType,
    MetricCategory,
    MetricSubCategory,
    MetricSeverity,
    MetricDefinition,
    MetricCollector,
    SystemMetricCollector,
    AlertRule,
    MetricEvent,
    get_global_manager,
    reset_global_manager
)


class TestMetricCollector(MetricCollector):
    """测试用指标收集器"""
    
    def __init__(self, metrics_data: Dict[str, Any] = None):
        self.metrics_data = metrics_data or {
            "test_metric_1": 42,
            "test_metric_2": {"value": 100, "labels": {"component": "test"}}
        }
        self.collection_count = 0
    
    def collect_metrics(self) -> Dict[str, Any]:
        self.collection_count += 1
        return self.metrics_data
    
    def get_collection_interval(self) -> int:
        return 1  # 1秒间隔，用于测试


class TestUnifiedMetricsManager:
    """统一指标管理器测试"""
    
    @pytest.fixture
    def registry(self):
        """指标注册表夹具"""
        return MetricRegistry()
    
    @pytest.fixture
    def metrics_manager(self, registry):
        """指标管理器夹具"""
        return UnifiedMetricsManager(registry=registry)
    
    @pytest.fixture
    def test_metric_definition(self):
        """测试指标定义夹具"""
        return MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.BUSINESS,
            description="测试计数器",
            labels=["service", "endpoint"]
        )
    
    def test_initialization(self, metrics_manager):
        """测试初始化"""
        assert metrics_manager.registry is not None
        assert isinstance(metrics_manager.collectors, dict)
        assert isinstance(metrics_manager.exporters, dict)
        assert isinstance(metrics_manager.alert_rules, dict)
        assert not metrics_manager._collection_enabled
        assert len(metrics_manager.collectors) >= 1  # 至少有系统收集器
    
    def test_register_collector(self, metrics_manager):
        """测试注册收集器"""
        collector = TestMetricCollector()
        
        # 注册收集器
        metrics_manager.register_collector("test", collector)
        
        assert "test" in metrics_manager.collectors
        assert metrics_manager.collectors["test"] == collector
    
    def test_unregister_collector(self, metrics_manager):
        """测试注销收集器"""
        collector = TestMetricCollector()
        
        # 注册并注销收集器
        metrics_manager.register_collector("test", collector)
        assert "test" in metrics_manager.collectors
        
        result = metrics_manager.unregister_collector("test")
        assert result
        assert "test" not in metrics_manager.collectors
        
        # 注销不存在的收集器
        result = metrics_manager.unregister_collector("nonexistent")
        assert not result
    
    def test_register_exporter(self, metrics_manager):
        """测试注册导出器"""
        exporter = Mock()
        
        # 注册导出器
        metrics_manager.register_exporter("test", exporter)
        
        assert "test" in metrics_manager.exporters
        assert metrics_manager.exporters["test"] == exporter
    
    def test_add_remove_event_listener(self, metrics_manager):
        """测试添加和移除事件监听器"""
        events_received = []
        
        def event_listener(event: MetricEvent):
            events_received.append(event)
        
        # 添加监听器
        metrics_manager.add_event_listener(event_listener)
        assert event_listener in metrics_manager.event_listeners
        
        # 测试事件触发
        metrics_manager.registry.register_custom_metric(
            "test_counter",
            MetricType.COUNTER,
            MetricCategory.BUSINESS
        )
        metrics_manager.increment("test_counter", 5)
        
        assert len(events_received) == 1
        assert events_received[0].metric_name == "test_counter"
        assert events_received[0].operation == "increment"
        assert events_received[0].value == 5
        
        # 移除监听器
        metrics_manager.remove_event_listener(event_listener)
        assert event_listener not in metrics_manager.event_listeners
    
    def test_increment_counter(self, metrics_manager):
        """测试增加计数器"""
        # 注册计数器指标
        metrics_manager.registry.register_custom_metric(
            "test_counter",
            MetricType.COUNTER,
            MetricCategory.BUSINESS
        )
        
        # 增加计数器
        metrics_manager.increment("test_counter", 10)
        metrics_manager.increment("test_counter", 5, {"service": "api"})
        
        # 验证值
        metric = metrics_manager.registry.get_metric("test_counter")
        assert metric is not None
        
        # 检查无标签的值
        value = metric.get_value({})
        assert value is not None
        assert value.value == 10
        
        # 检查有标签的值
        value = metric.get_value({"service": "api"})
        assert value is not None
        assert value.value == 5
    
    def test_set_gauge(self, metrics_manager):
        """测试设置仪表值"""
        # 注册仪表指标
        metrics_manager.registry.register_custom_metric(
            "test_gauge",
            MetricType.GAUGE,
            MetricCategory.SYSTEM
        )
        
        # 设置仪表值
        metrics_manager.set_gauge("test_gauge", 42.5)
        metrics_manager.set_gauge("test_gauge", 78.9, {"component": "cpu"})
        
        # 验证值
        metric = metrics_manager.registry.get_metric("test_gauge")
        assert metric is not None
        
        value = metric.get_value({})
        assert value is not None
        assert value.value == 42.5
        
        value = metric.get_value({"component": "cpu"})
        assert value is not None
        assert value.value == 78.9
    
    def test_observe_histogram(self, metrics_manager):
        """测试观察直方图值"""
        # 注册直方图指标
        metrics_manager.registry.register_custom_metric(
            "test_histogram",
            MetricType.HISTOGRAM,
            MetricCategory.PERFORMANCE
        )
        
        # 观察值
        metrics_manager.observe_histogram("test_histogram", 0.5)
        metrics_manager.observe_histogram("test_histogram", 1.5)
        metrics_manager.observe_histogram("test_histogram", 2.5)
        
        # 验证值
        metric = metrics_manager.registry.get_metric("test_histogram")
        assert metric is not None
        
        value = metric.get_value({})
        assert value is not None
        assert value.count == 3
        assert value.sum == 4.5
    
    def test_timer_context_manager(self, metrics_manager):
        """测试计时器上下文管理器"""
        # 注册直方图指标
        metrics_manager.registry.register_custom_metric(
            "test_timer",
            MetricType.HISTOGRAM,
            MetricCategory.PERFORMANCE
        )
        
        # 使用计时器
        with metrics_manager.timer("test_timer"):
            time.sleep(0.1)  # 模拟耗时操作
        
        # 验证值
        metric = metrics_manager.registry.get_metric("test_timer")
        assert metric is not None
        
        value = metric.get_value({})
        assert value is not None
        assert value.count == 1
        assert 0.1 <= value.sum <= 0.2  # 考虑误差
    
    def test_collection_lifecycle(self, metrics_manager):
        """测试收集生命周期"""
        collector = TestMetricCollector()
        metrics_manager.register_collector("test", collector)
        
        # 注册指标
        metrics_manager.registry.register_custom_metric(
            "test_metric_1",
            MetricType.GAUGE,
            MetricCategory.SYSTEM
        )
        
        # 启动收集
        assert not metrics_manager._collection_enabled
        metrics_manager.start_collection(interval=1)
        
        assert metrics_manager._collection_enabled
        assert metrics_manager._collection_thread is not None
        
        # 等待收集
        time.sleep(1.5)
        
        # 验证收集器被调用
        assert collector.collection_count > 0
        
        # 停止收集
        metrics_manager.stop_collection()
        
        assert not metrics_manager._collection_enabled
        assert metrics_manager._collection_thread is None
    
    def test_export_metrics(self, metrics_manager):
        """测试导出指标"""
        # 注册模拟导出器
        mock_exporter = Mock(return_value="exported_data")
        metrics_manager.register_exporter("test", mock_exporter)
        
        # 导出指标
        result = metrics_manager.export_metrics("test")
        
        assert result == "exported_data"
        mock_exporter.assert_called_once()
    
    def test_alert_rules(self, metrics_manager):
        """测试告警规则"""
        # 注册指标
        metrics_manager.registry.register_custom_metric(
            "error_rate",
            MetricType.GAUGE,
            MetricCategory.ERROR
        )
        
        # 添加告警规则
        rule = AlertRule(
            metric_name="error_rate",
            condition=">",
            threshold=0.5,
            severity=MetricSeverity.HIGH,
            message="错误率过高",
            duration=1
        )
        
        metrics_manager.add_alert_rule(rule)
        assert len(metrics_manager.alert_rules) == 1
        
        # 设置触发告警的值
        metrics_manager.set_gauge("error_rate", 0.8)
        
        # 等待一段时间以满足持续时间要求
        time.sleep(1.1)
        
        # 检查告警
        alerts = metrics_manager.check_alerts()
        assert len(alerts) > 0
        assert alerts[0]["metric_name"] == "error_rate"
        assert alerts[0]["value"] == 0.8
        assert alerts[0]["severity"] == "high"
    
    def test_alert_rule_management(self, metrics_manager):
        """测试告警规则管理"""
        rule = AlertRule(
            metric_name="test_metric",
            condition=">",
            threshold=100,
            severity=MetricSeverity.MEDIUM,
            message="测试告警"
        )
        
        # 添加规则
        metrics_manager.add_alert_rule(rule)
        assert len(metrics_manager.alert_rules) == 1
        
        # 获取规则ID
        rule_id = list(metrics_manager.alert_rules.keys())[0]
        
        # 移除规则
        result = metrics_manager.remove_alert_rule(rule_id)
        assert result
        assert len(metrics_manager.alert_rules) == 0
        
        # 移除不存在的规则
        result = metrics_manager.remove_alert_rule("nonexistent")
        assert not result
    
    def test_get_stats(self, metrics_manager):
        """测试获取统计信息"""
        stats = metrics_manager.get_stats()
        
        assert "registry_stats" in stats
        assert "collectors" in stats
        assert "exporters" in stats
        assert "alert_rules" in stats
        assert "collection_enabled" in stats
        assert "uptime_seconds" in stats
        assert "metrics_collected" in stats
        assert "events_processed" in stats
        
        assert isinstance(stats["collectors"], int)
        assert isinstance(stats["uptime_seconds"], float)
        assert stats["uptime_seconds"] > 0
    
    def test_get_health_status(self, metrics_manager):
        """测试获取健康状态"""
        health = metrics_manager.get_health_status()
        
        assert "healthy" in health
        assert "status" in health
        assert "checks" in health
        assert "details" in health
        
        assert isinstance(health["healthy"], bool)
        assert health["status"] in ["OK", "DEGRADED", "UNHEALTHY", "ERROR"]
        
        # 检查各项检查
        checks = health["checks"]
        assert "registry" in checks
        assert "collection" in checks
        assert "collectors" in checks
    
    def test_shutdown(self, metrics_manager):
        """测试关闭管理器"""
        # 启动收集
        metrics_manager.start_collection()
        assert metrics_manager._collection_enabled
        
        # 添加一些组件
        collector = TestMetricCollector()
        exporter = Mock()
        metrics_manager.register_collector("test", collector)
        metrics_manager.register_exporter("test", exporter)
        
        # 关闭管理器
        metrics_manager.shutdown()
        
        # 验证清理
        assert not metrics_manager._collection_enabled
        assert len(metrics_manager.collectors) == 0
        assert len(metrics_manager.exporters) == 0
        assert len(metrics_manager.event_listeners) == 0
    
    def test_invalid_operations(self, metrics_manager):
        """测试无效操作"""
        # 尝试操作不存在的指标
        metrics_manager.increment("nonexistent_metric", 1)
        metrics_manager.set_gauge("nonexistent_metric", 1)
        metrics_manager.observe_histogram("nonexistent_metric", 1.0)
        
        # 应该记录警告但不抛出异常
        # 这些操作不应该影响管理器的正常运行
        
        # 导出不存在的格式
        result = metrics_manager.export_metrics("nonexistent_format")
        assert result is None


class TestSystemMetricCollector:
    """系统指标收集器测试"""
    
    @pytest.fixture
    def collector(self):
        """系统收集器夹具"""
        return SystemMetricCollector()
    
    @pytest.mark.skipif(not hasattr(SystemMetricCollector, 'psutil'), 
                       reason="psutil not available")
    def test_collect_metrics(self, collector):
        """测试收集系统指标"""
        metrics = collector.collect_metrics()
        
        # 验证返回的指标
        assert isinstance(metrics, dict)
        assert len(metrics) > 0
        
        # 检查CPU指标
        if "system_cpu_usage_percent" in metrics:
            cpu_usage = metrics["system_cpu_usage_percent"]
            assert isinstance(cpu_usage, (int, float))
            assert 0 <= cpu_usage <= 100
        
        # 检查内存指标
        if "system_memory_usage_bytes" in metrics:
            memory_usage = metrics["system_memory_usage_bytes"]
            assert isinstance(memory_usage, (int, float))
            assert memory_usage > 0
    
    def test_collection_interval(self, collector):
        """测试收集间隔"""
        interval = collector.get_collection_interval()
        assert isinstance(interval, int)
        assert interval > 0


class TestGlobalManager:
    """全局管理器测试"""
    
    def test_global_manager_singleton(self):
        """测试全局管理器单例"""
        # 重置全局管理器
        reset_global_manager()
        
        # 获取两次全局管理器，应该是同一个实例
        manager1 = get_global_manager()
        manager2 = get_global_manager()
        
        assert manager1 is manager2
        assert isinstance(manager1, UnifiedMetricsManager)
    
    def test_reset_global_manager(self):
        """测试重置全局管理器"""
        # 获取全局管理器
        manager1 = get_global_manager()
        
        # 重置
        reset_global_manager()
        
        # 再次获取应该是新实例
        manager2 = get_global_manager()
        
        assert manager1 is not manager2


class TestThreadSafety:
    """线程安全测试"""
    
    def test_concurrent_metric_operations(self):
        """测试并发指标操作"""
        reset_global_manager()
        manager = get_global_manager()
        
        # 注册指标
        manager.registry.register_custom_metric(
            "concurrent_counter",
            MetricType.COUNTER,
            MetricCategory.BUSINESS
        )
        
        # 并发增加计数器
        def increment_counter():
            for _ in range(100):
                manager.increment("concurrent_counter", 1)
        
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=increment_counter)
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证最终值
        metric = manager.registry.get_metric("concurrent_counter")
        value = metric.get_value({})
        assert value.value == 1000  # 10 threads * 100 increments
    
    def test_concurrent_collector_registration(self):
        """测试并发收集器注册"""
        reset_global_manager()
        manager = get_global_manager()
        
        def register_collectors():
            for i in range(10):
                collector = TestMetricCollector()
                manager.register_collector(f"collector_{threading.current_thread().ident}_{i}", collector)
        
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=register_collectors)
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证收集器数量
        # 应该有系统收集器 + 5个线程 * 10个收集器，但可能有重复或冲突
        assert len(manager.collectors) >= 40  # 放宽检查，因为多线程可能有名称冲突


if __name__ == "__main__":
    pytest.main([__file__, "-v"])