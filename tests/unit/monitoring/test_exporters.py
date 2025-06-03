"""
指标导出器测试
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from marketprism_collector.core.monitoring import (
    MetricRegistry,
    MetricType,
    MetricCategory,
    MetricSubCategory,
    MetricSeverity,
    MetricDefinition,
    UnifiedMetricsManager
)
from marketprism_collector.core.monitoring.exporters import (
    PrometheusExporter,
    PrometheusMetricsHandler,
    PrometheusGatewayPusher,
    JSONExporter,
    JSONMetricsAPI,
    MetricsReportGenerator,
    GrafanaDashboardGenerator,
    PrometheusAlertGenerator
)


class TestPrometheusExporter:
    """Prometheus导出器测试"""
    
    @pytest.fixture
    def registry_with_metrics(self):
        """带有测试指标的注册表"""
        registry = MetricRegistry()
        
        # 注册不同类型的指标
        counter_def = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.BUSINESS,
            description="测试计数器",
            help_text="用于测试的计数器指标"
        )
        registry.register_metric(counter_def)
        
        gauge_def = MetricDefinition(
            name="test_gauge",
            metric_type=MetricType.GAUGE,
            category=MetricCategory.SYSTEM,
            description="测试仪表",
            unit="bytes"
        )
        registry.register_metric(gauge_def)
        
        histogram_def = MetricDefinition(
            name="test_histogram",
            metric_type=MetricType.HISTOGRAM,
            category=MetricCategory.PERFORMANCE,
            description="测试直方图",
            unit="seconds"
        )
        registry.register_metric(histogram_def)
        
        # 设置一些值
        counter_metric = registry.get_metric("test_counter")
        counter_metric.increment(10, {"service": "api"})
        counter_metric.increment(5, {"service": "web"})
        
        gauge_metric = registry.get_metric("test_gauge")
        gauge_metric.set_value(1024, {"component": "memory"})
        gauge_metric.set_value(2048, {"component": "disk"})
        
        histogram_metric = registry.get_metric("test_histogram")
        histogram_metric.observe_histogram(0.1, {"endpoint": "/api/users"})
        histogram_metric.observe_histogram(0.5, {"endpoint": "/api/users"})
        histogram_metric.observe_histogram(1.0, {"endpoint": "/api/orders"})
        
        return registry
    
    @pytest.fixture
    def prometheus_exporter(self):
        """Prometheus导出器夹具"""
        return PrometheusExporter(include_timestamp=False, include_help=True)
    
    def test_export_counter_metrics(self, prometheus_exporter, registry_with_metrics):
        """测试导出计数器指标"""
        metrics = registry_with_metrics.get_all_metrics()
        output = prometheus_exporter.export_metrics(metrics)
        
        # 验证输出包含计数器指标
        assert "# HELP marketprism_business_test_counter 用于测试的计数器指标" in output
        assert "# TYPE marketprism_business_test_counter counter" in output
        assert 'marketprism_business_test_counter{service="api"} 10' in output
        assert 'marketprism_business_test_counter{service="web"} 5' in output
    
    def test_export_gauge_metrics(self, prometheus_exporter, registry_with_metrics):
        """测试导出仪表指标"""
        metrics = registry_with_metrics.get_all_metrics()
        output = prometheus_exporter.export_metrics(metrics)
        
        # 验证输出包含仪表指标
        assert "# TYPE marketprism_system_test_gauge gauge" in output
        assert 'marketprism_system_test_gauge{component="memory"} 1024' in output
        assert 'marketprism_system_test_gauge{component="disk"} 2048' in output
    
    def test_export_histogram_metrics(self, prometheus_exporter, registry_with_metrics):
        """测试导出直方图指标"""
        metrics = registry_with_metrics.get_all_metrics()
        output = prometheus_exporter.export_metrics(metrics)
        
        # 验证输出包含直方图指标
        assert "# TYPE marketprism_performance_test_histogram histogram" in output
        
        # 检查桶数据
        assert "_bucket{" in output
        assert "le=" in output
        
        # 检查总数和和值
        assert "_sum{" in output
        assert "_count{" in output
    
    def test_label_escaping(self, prometheus_exporter):
        """测试标签转义"""
        registry = MetricRegistry()
        
        # 注册指标
        metric_def = MetricDefinition(
            name="test_metric",
            metric_type=MetricType.GAUGE,
            category=MetricCategory.BUSINESS
        )
        registry.register_metric(metric_def)
        
        # 设置包含特殊字符的标签值
        metric = registry.get_metric("test_metric")
        metric.set_value(42, {"label": 'value with "quotes" and \n newlines'})
        
        # 导出
        output = prometheus_exporter.export_metrics(registry.get_all_metrics())
        
        # 验证转义
        assert 'label="value with \\"quotes\\" and \\n newlines"' in output
    
    def test_timestamp_inclusion(self, registry_with_metrics):
        """测试时间戳包含"""
        # 包含时间戳
        exporter_with_ts = PrometheusExporter(include_timestamp=True)
        output = exporter_with_ts.export_metrics(registry_with_metrics.get_all_metrics())
        
        # 应该包含时间戳（毫秒）
        lines = output.strip().split('\n')
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
        
        for line in metric_lines:
            if line.strip():
                parts = line.split()
                assert len(parts) >= 3  # metric_name{labels} value timestamp
                timestamp = parts[-1]
                assert timestamp.isdigit()
                assert len(timestamp) >= 13  # 毫秒时间戳长度
    
    def test_empty_metrics(self, prometheus_exporter):
        """测试空指标导出"""
        empty_metrics = {}
        output = prometheus_exporter.export_metrics(empty_metrics)
        
        assert output == ""


class TestPrometheusMetricsHandler:
    """Prometheus指标处理器测试"""
    
    @pytest.fixture
    def metrics_manager(self):
        """指标管理器夹具"""
        registry = MetricRegistry()
        manager = UnifiedMetricsManager(registry=registry)
        
        # 注册测试指标
        manager.registry.register_custom_metric(
            "http_requests",
            MetricType.COUNTER,
            MetricCategory.API,
            "HTTP请求总数"
        )
        
        # 设置一些值
        manager.increment("http_requests", 100, {"method": "GET", "status": "200"})
        manager.increment("http_requests", 50, {"method": "POST", "status": "201"})
        
        return manager
    
    def test_get_metrics(self, metrics_manager):
        """测试获取指标"""
        handler = PrometheusMetricsHandler(metrics_manager)
        content, content_type = handler.get_metrics()
        
        assert content_type == "text/plain; version=0.0.4; charset=utf-8"
        assert "http_requests" in content
        assert "method=" in content
        assert "status=" in content
    
    def test_handle_request(self, metrics_manager):
        """测试处理HTTP请求"""
        handler = PrometheusMetricsHandler(metrics_manager)
        response = handler.handle_request()
        
        assert response["status_code"] == 200
        assert "Content-Type" in response["headers"]
        assert "Cache-Control" in response["headers"]
        assert "body" in response
        assert "http_requests" in response["body"]


class TestPrometheusGatewayPusher:
    """Prometheus网关推送器测试"""
    
    @pytest.fixture
    def pusher(self):
        """网关推送器夹具"""
        return PrometheusGatewayPusher(
            gateway_url="http://localhost:9091",
            job_name="test_job",
            instance_name="test_instance"
        )
    
    @pytest.fixture
    def metrics_dict(self):
        """测试指标字典"""
        registry = MetricRegistry()
        
        metric_def = MetricDefinition(
            name="test_metric",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.BUSINESS
        )
        registry.register_metric(metric_def)
        
        metric = registry.get_metric("test_metric")
        metric.increment(42)
        
        return registry.get_all_metrics()
    
    @patch('requests.post')
    def test_push_metrics_success(self, mock_post, pusher, metrics_dict):
        """测试成功推送指标"""
        mock_post.return_value.status_code = 200
        
        result = pusher.push_metrics(metrics_dict)
        
        assert result is True
        mock_post.assert_called_once()
        
        # 验证调用参数
        call_args = mock_post.call_args
        assert "http://localhost:9091/metrics/job/test_job/instance/test_instance" in call_args[0]
        assert call_args[1]["headers"]["Content-Type"] == "text/plain"
    
    @patch('requests.post')
    def test_push_metrics_failure(self, mock_post, pusher, metrics_dict):
        """测试推送指标失败"""
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"
        
        result = pusher.push_metrics(metrics_dict)
        
        assert result is False
    
    @patch('requests.delete')
    def test_delete_metrics_success(self, mock_delete, pusher):
        """测试成功删除指标"""
        mock_delete.return_value.status_code = 202
        
        result = pusher.delete_metrics()
        
        assert result is True
        mock_delete.assert_called_once()


class TestJSONExporter:
    """JSON导出器测试"""
    
    @pytest.fixture
    def json_exporter(self):
        """JSON导出器夹具"""
        return JSONExporter(
            include_metadata=True,
            include_timestamps=True,
            pretty_print=False
        )
    
    @pytest.fixture
    def registry_with_metrics(self):
        """带有测试指标的注册表"""
        registry = MetricRegistry()
        
        # 注册指标
        counter_def = MetricDefinition(
            name="api_requests",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.API,
            description="API请求总数",
            labels=["method", "endpoint"]
        )
        registry.register_metric(counter_def)
        
        # 设置值
        metric = registry.get_metric("api_requests")
        metric.increment(100, {"method": "GET", "endpoint": "/users"})
        metric.increment(50, {"method": "POST", "endpoint": "/orders"})
        
        return registry
    
    def test_export_basic_structure(self, json_exporter, registry_with_metrics):
        """测试导出基本结构"""
        output = json_exporter.export_metrics(registry_with_metrics.get_all_metrics())
        data = json.loads(output)
        
        # 验证基本结构
        assert "metrics" in data
        assert "summary" in data
        assert "metadata" in data
        
        # 验证摘要信息
        summary = data["summary"]
        assert "total_metrics" in summary
        assert "export_timestamp" in summary
        assert "exported_metrics" in summary
        
        # 验证元数据
        metadata = data["metadata"]
        assert "categories" in metadata
        assert "types" in metadata
        assert "severities" in metadata
    
    def test_export_metric_details(self, json_exporter, registry_with_metrics):
        """测试导出指标详细信息"""
        output = json_exporter.export_metrics(registry_with_metrics.get_all_metrics())
        data = json.loads(output)
        
        # 检查指标数据
        metrics = data["metrics"]
        assert "api_requests" in metrics
        
        api_requests = metrics["api_requests"]
        assert "definition" in api_requests
        assert "values" in api_requests
        assert "statistics" in api_requests
        
        # 检查定义
        definition = api_requests["definition"]
        assert definition["name"] == "api_requests"
        assert definition["type"] == "COUNTER"
        assert definition["category"] == "api"
        assert definition["description"] == "API请求总数"
        
        # 检查值
        values = api_requests["values"]
        assert len(values) == 2  # 两个标签组合
        
        for value in values:
            assert "labels" in value
            assert "timestamp" in value
            assert "value" in value
            assert "type" in value
    
    def test_pretty_print(self, registry_with_metrics):
        """测试美化打印"""
        # 美化打印
        pretty_exporter = JSONExporter(pretty_print=True)
        pretty_output = pretty_exporter.export_metrics(registry_with_metrics.get_all_metrics())
        
        # 非美化打印
        compact_exporter = JSONExporter(pretty_print=False)
        compact_output = compact_exporter.export_metrics(registry_with_metrics.get_all_metrics())
        
        # 美化版本应该更长（包含缩进和换行）
        assert len(pretty_output) > len(compact_output)
        assert "\n" in pretty_output
        assert "  " in pretty_output  # 缩进
    
    def test_exclude_empty_metrics(self, json_exporter):
        """测试排除空指标"""
        registry = MetricRegistry()
        
        # 注册指标但不设置值
        metric_def = MetricDefinition(
            name="empty_metric",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.BUSINESS
        )
        registry.register_metric(metric_def)
        
        # 不包含空指标
        exporter = JSONExporter(include_empty_metrics=False)
        output = exporter.export_metrics(registry.get_all_metrics())
        data = json.loads(output)
        
        assert "empty_metric" not in data["metrics"]
        
        # 包含空指标
        exporter = JSONExporter(include_empty_metrics=True)
        output = exporter.export_metrics(registry.get_all_metrics())
        data = json.loads(output)
        
        assert "empty_metric" in data["metrics"]


class TestJSONMetricsAPI:
    """JSON指标API测试"""
    
    @pytest.fixture
    def metrics_manager(self):
        """指标管理器夹具"""
        registry = MetricRegistry()
        manager = UnifiedMetricsManager(registry=registry)
        
        # 注册不同分类的指标
        manager.registry.register_custom_metric(
            "business_metric",
            MetricType.COUNTER,
            MetricCategory.BUSINESS
        )
        
        manager.registry.register_custom_metric(
            "system_metric",
            MetricType.GAUGE,
            MetricCategory.SYSTEM
        )
        
        # 设置一些值
        manager.increment("business_metric", 100)
        manager.set_gauge("system_metric", 42)
        
        return manager
    
    @pytest.fixture
    def json_api(self, metrics_manager):
        """JSON API夹具"""
        return JSONMetricsAPI(metrics_manager)
    
    def test_get_all_metrics(self, json_api):
        """测试获取所有指标"""
        result = json_api.get_all_metrics()
        
        assert result["success"] is True
        assert "data" in result
        assert "timestamp" in result
        
        data = result["data"]
        assert "metrics" in data
        assert "business_metric" in data["metrics"]
        assert "system_metric" in data["metrics"]
    
    def test_get_metrics_by_category(self, json_api):
        """测试按分类获取指标"""
        # 有效分类
        result = json_api.get_metrics_by_category("business")
        
        assert result["success"] is True
        assert result["category"] == "business"
        assert "data" in result
        
        data = result["data"]
        assert "business_metric" in data["metrics"]
        assert "system_metric" not in data["metrics"]
        
        # 无效分类
        result = json_api.get_metrics_by_category("invalid_category")
        
        assert result["success"] is False
        assert "error" in result
        assert "available_categories" in result
    
    def test_get_metric_by_name(self, json_api):
        """测试按名称获取指标"""
        # 存在的指标
        result = json_api.get_metric_by_name("business_metric")
        
        assert result["success"] is True
        assert result["metric_name"] == "business_metric"
        assert "data" in result
        
        # 不存在的指标
        result = json_api.get_metric_by_name("nonexistent_metric")
        
        assert result["success"] is False
        assert "error" in result
    
    def test_get_metrics_summary(self, json_api):
        """测试获取指标摘要"""
        result = json_api.get_metrics_summary()
        
        assert result["success"] is True
        assert "summary" in result
        
        summary = result["summary"]
        assert "registry" in summary
        assert "manager" in summary
        assert "health" in summary
    
    def test_search_metrics(self, json_api):
        """测试搜索指标"""
        # 搜索业务指标
        result = json_api.search_metrics("business", limit=10)
        
        assert result["success"] is True
        assert result["query"] == "business"
        assert result["limit"] == 10
        assert "data" in result
        
        data = result["data"]
        assert "business_metric" in data["metrics"]
        
        # 搜索不存在的指标
        result = json_api.search_metrics("nonexistent", limit=10)
        
        assert result["success"] is True
        assert result["total_found"] == 0


class TestGrafanaDashboardGenerator:
    """Grafana仪表板生成器测试"""
    
    @pytest.fixture
    def dashboard_generator(self):
        """仪表板生成器夹具"""
        return GrafanaDashboardGenerator(
            dashboard_title="Test Dashboard",
            refresh_interval="10s"
        )
    
    @pytest.fixture
    def metrics_dict(self):
        """测试指标字典"""
        registry = MetricRegistry()
        
        # 不同类型的指标
        counter_def = MetricDefinition(
            name="http_requests",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.API
        )
        registry.register_metric(counter_def)
        
        gauge_def = MetricDefinition(
            name="cpu_usage",
            metric_type=MetricType.GAUGE,
            category=MetricCategory.SYSTEM
        )
        registry.register_metric(gauge_def)
        
        histogram_def = MetricDefinition(
            name="response_time",
            metric_type=MetricType.HISTOGRAM,
            category=MetricCategory.PERFORMANCE
        )
        registry.register_metric(histogram_def)
        
        return registry.get_all_metrics()
    
    def test_generate_dashboard_structure(self, dashboard_generator, metrics_dict):
        """测试生成仪表板结构"""
        dashboard = dashboard_generator.generate_dashboard(metrics_dict)
        
        assert "dashboard" in dashboard
        assert "folderId" in dashboard
        assert "overwrite" in dashboard
        
        dash = dashboard["dashboard"]
        assert dash["title"] == "Test Dashboard"
        assert dash["refresh"] == "10s"
        assert "panels" in dash
        assert "templating" in dash
        assert "time" in dash
    
    def test_generate_panels_by_category(self, dashboard_generator, metrics_dict):
        """测试按分类生成面板"""
        dashboard = dashboard_generator.generate_dashboard(metrics_dict)
        panels = dashboard["dashboard"]["panels"]
        
        # 应该有面板
        assert len(panels) > 0
        
        # 检查面板类型
        panel_types = [panel.get("type") for panel in panels]
        assert "text" in panel_types  # 分类标题
        assert "graph" in panel_types or "stat" in panel_types  # 指标面板
    
    def test_template_variables(self, dashboard_generator, metrics_dict):
        """测试模板变量生成"""
        dashboard = dashboard_generator.generate_dashboard(metrics_dict)
        variables = dashboard["dashboard"]["templating"]["list"]
        
        # 应该至少有instance变量
        assert len(variables) > 0
        
        instance_var = next((var for var in variables if var["name"] == "instance"), None)
        assert instance_var is not None
        assert instance_var["type"] == "query"


class TestPrometheusAlertGenerator:
    """Prometheus告警生成器测试"""
    
    @pytest.fixture
    def alert_generator(self):
        """告警生成器夹具"""
        return PrometheusAlertGenerator(namespace="test")
    
    @pytest.fixture
    def metrics_dict(self):
        """测试指标字典"""
        registry = MetricRegistry()
        
        # 错误指标
        error_def = MetricDefinition(
            name="error_rate",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.ERROR
        )
        registry.register_metric(error_def)
        
        # 性能指标
        perf_def = MetricDefinition(
            name="response_time",
            metric_type=MetricType.HISTOGRAM,
            category=MetricCategory.PERFORMANCE
        )
        registry.register_metric(perf_def)
        
        # 资源指标
        resource_def = MetricDefinition(
            name="cpu_usage",
            metric_type=MetricType.GAUGE,
            category=MetricCategory.RESOURCE
        )
        registry.register_metric(resource_def)
        
        return registry.get_all_metrics()
    
    def test_generate_alert_rules_structure(self, alert_generator, metrics_dict):
        """测试生成告警规则结构"""
        rules = alert_generator.generate_alert_rules(metrics_dict)
        
        assert "groups" in rules
        assert len(rules["groups"]) > 0
        
        group = rules["groups"][0]
        assert group["name"] == "test.rules"
        assert "rules" in group
    
    def test_error_alert_generation(self, alert_generator, metrics_dict):
        """测试错误告警生成"""
        rules = alert_generator.generate_alert_rules(metrics_dict)
        alert_rules = rules["groups"][0]["rules"]
        
        # 查找错误告警
        error_alert = next((rule for rule in alert_rules if "error_rate" in rule.get("alert", "")), None)
        assert error_alert is not None
        
        assert "expr" in error_alert
        assert "for" in error_alert
        assert "labels" in error_alert
        assert "annotations" in error_alert
        assert error_alert["labels"]["category"] == "error"
    
    def test_performance_alert_generation(self, alert_generator, metrics_dict):
        """测试性能告警生成"""
        rules = alert_generator.generate_alert_rules(metrics_dict)
        alert_rules = rules["groups"][0]["rules"]
        
        # 查找性能告警
        perf_alert = next((rule for rule in alert_rules if "response_time" in rule.get("alert", "")), None)
        assert perf_alert is not None
        
        assert "histogram_quantile" in perf_alert["expr"]
        assert perf_alert["labels"]["category"] == "performance"
    
    def test_resource_alert_generation(self, alert_generator, metrics_dict):
        """测试资源告警生成"""
        rules = alert_generator.generate_alert_rules(metrics_dict)
        alert_rules = rules["groups"][0]["rules"]
        
        # 查找资源告警
        resource_alert = next((rule for rule in alert_rules if "cpu_usage" in rule.get("alert", "")), None)
        assert resource_alert is not None
        
        assert resource_alert["labels"]["severity"] == "critical"
        assert resource_alert["labels"]["category"] == "resource"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])