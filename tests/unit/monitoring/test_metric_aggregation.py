"""
指标聚合和计算测试
"""

import pytest
import time
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Any
from unittest.mock import Mock

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from marketprism_collector.core.monitoring import (
    UnifiedMetricsManager,
    MetricRegistry,
    MetricType,
    MetricCategory,
    MetricDefinition,
    MetricInstance,
    MetricValue,
    HistogramValue,
    SummaryValue
)


class MetricAggregator:
    """指标聚合器"""
    
    def __init__(self, registry: MetricRegistry):
        self.registry = registry
    
    def aggregate_counter_rate(self, metric_name: str, time_window: float = 60.0) -> Dict[str, float]:
        """计算计数器速率"""
        metric = self.registry.get_metric(metric_name)
        if not metric or metric.definition.metric_type != MetricType.COUNTER:
            return {}
        
        rates = {}
        current_time = time.time()
        
        for label_key, metric_value in metric.get_values().items():
            # 简化的速率计算（实际应该基于时间序列数据）
            time_diff = current_time - metric_value.timestamp
            if time_diff > 0:
                rate = metric_value.value / max(time_diff, time_window)
                rates[label_key] = rate
        
        return rates
    
    def aggregate_gauge_stats(self, metric_name: str) -> Dict[str, Any]:
        """计算仪表统计信息"""
        metric = self.registry.get_metric(metric_name)
        if not metric or metric.definition.metric_type != MetricType.GAUGE:
            return {}
        
        values = [mv.value for mv in metric.get_values().values()]
        if not values:
            return {}
        
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0.0
        }
    
    def aggregate_histogram_percentiles(self, metric_name: str, 
                                      percentiles: List[float] = None) -> Dict[str, Dict[str, float]]:
        """计算直方图百分位数"""
        if percentiles is None:
            percentiles = [0.5, 0.9, 0.95, 0.99]
        
        metric = self.registry.get_metric(metric_name)
        if not metric or metric.definition.metric_type != MetricType.HISTOGRAM:
            return {}
        
        result = {}
        
        for label_key, metric_value in metric.get_values().items():
            if isinstance(metric_value, HistogramValue):
                # 简化的百分位数计算
                # 实际实现应该基于桶数据进行更精确的计算
                percentile_values = {}
                
                total_count = metric_value.count
                if total_count > 0:
                    # 基于桶计算百分位数
                    cumulative_count = 0
                    for percentile in percentiles:
                        target_count = total_count * percentile
                        
                        for bucket in metric_value.buckets:
                            cumulative_count += bucket.count
                            if cumulative_count >= target_count:
                                percentile_values[f"p{percentile*100}"] = bucket.upper_bound
                                break
                        else:
                            # 如果没有找到合适的桶，使用最大值
                            percentile_values[f"p{percentile*100}"] = metric_value.buckets[-1].upper_bound if metric_value.buckets else 0
                
                percentile_values["mean"] = metric_value.sum / total_count if total_count > 0 else 0
                result[label_key] = percentile_values
        
        return result
    
    def aggregate_by_category(self, category: MetricCategory) -> Dict[str, Any]:
        """按分类聚合指标"""
        metrics = self.registry.get_metrics_by_category(category)
        
        aggregation = {
            "category": category.value,
            "total_metrics": len(metrics),
            "by_type": {},
            "total_values": 0,
            "metrics_with_data": 0
        }
        
        for metric_name, metric_instance in metrics.items():
            metric_type = metric_instance.definition.metric_type.name
            
            if metric_type not in aggregation["by_type"]:
                aggregation["by_type"][metric_type] = {
                    "count": 0,
                    "total_values": 0,
                    "metrics": []
                }
            
            values_count = len(metric_instance.get_values())
            aggregation["by_type"][metric_type]["count"] += 1
            aggregation["by_type"][metric_type]["total_values"] += values_count
            aggregation["by_type"][metric_type]["metrics"].append(metric_name)
            
            aggregation["total_values"] += values_count
            if values_count > 0:
                aggregation["metrics_with_data"] += 1
        
        return aggregation
    
    def detect_anomalies(self, metric_name: str, 
                        threshold_multiplier: float = 3.0) -> List[Dict[str, Any]]:
        """检测指标异常值"""
        metric = self.registry.get_metric(metric_name)
        if not metric:
            return []
        
        anomalies = []
        
        if metric.definition.metric_type == MetricType.GAUGE:
            values = [mv.value for mv in metric.get_values().values()]
            if len(values) < 2:
                return anomalies
            
            mean_value = statistics.mean(values)
            std_dev = statistics.stdev(values)
            threshold = std_dev * threshold_multiplier
            
            for label_key, metric_value in metric.get_values().items():
                deviation = abs(metric_value.value - mean_value)
                if deviation > threshold:
                    anomalies.append({
                        "metric_name": metric_name,
                        "labels": metric_value.labels,
                        "value": metric_value.value,
                        "mean": mean_value,
                        "std_dev": std_dev,
                        "deviation": deviation,
                        "threshold": threshold,
                        "timestamp": metric_value.timestamp
                    })
        
        return anomalies
    
    def calculate_sla_metrics(self, success_metric: str, total_metric: str) -> Dict[str, float]:
        """计算SLA指标"""
        success_metric_instance = self.registry.get_metric(success_metric)
        total_metric_instance = self.registry.get_metric(total_metric)
        
        if not success_metric_instance or not total_metric_instance:
            return {}
        
        sla_metrics = {}
        
        # 获取成功计数
        success_values = {}
        for label_key, metric_value in success_metric_instance.get_values().items():
            success_values[label_key] = metric_value.value
        
        # 计算可用性
        for label_key, metric_value in total_metric_instance.get_values().items():
            total_count = metric_value.value
            success_count = success_values.get(label_key, 0)
            
            if total_count > 0:
                availability = (success_count / total_count) * 100
                error_rate = ((total_count - success_count) / total_count) * 100
                
                labels_str = "|".join(f"{k}={v}" for k, v in sorted(metric_value.labels.items()))
                sla_metrics[labels_str] = {
                    "availability_percent": availability,
                    "error_rate_percent": error_rate,
                    "success_count": success_count,
                    "total_count": total_count,
                    "labels": metric_value.labels
                }
        
        return sla_metrics


class TestMetricAggregation:
    """指标聚合测试"""
    
    @pytest.fixture
    def registry_with_data(self):
        """带有测试数据的注册表"""
        registry = MetricRegistry()
        
        # 注册各种类型的指标
        counter_def = MetricDefinition(
            name="requests_total",
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
        
        # 设置计数器数据
        counter_metric = registry.get_metric("requests_total")
        counter_metric.increment(1000, {"service": "api", "status": "200"})
        counter_metric.increment(50, {"service": "api", "status": "404"})
        counter_metric.increment(10, {"service": "api", "status": "500"})
        
        # 设置仪表数据
        gauge_metric = registry.get_metric("cpu_usage")
        gauge_metric.set_value(25.0, {"host": "server1"})
        gauge_metric.set_value(45.0, {"host": "server2"})
        gauge_metric.set_value(85.0, {"host": "server3"})  # 异常值
        gauge_metric.set_value(30.0, {"host": "server4"})
        gauge_metric.set_value(35.0, {"host": "server5"})  # 增加更多数据点
        
        # 设置直方图数据
        histogram_metric = registry.get_metric("response_time")
        # 模拟多次观察
        for _ in range(100):
            histogram_metric.observe_histogram(0.1, {"endpoint": "/api/users"})
        for _ in range(50):
            histogram_metric.observe_histogram(0.5, {"endpoint": "/api/users"})
        for _ in range(20):
            histogram_metric.observe_histogram(1.0, {"endpoint": "/api/users"})
        
        return registry
    
    @pytest.fixture
    def aggregator(self, registry_with_data):
        """聚合器夹具"""
        return MetricAggregator(registry_with_data)
    
    def test_counter_rate_calculation(self, aggregator):
        """测试计数器速率计算"""
        rates = aggregator.aggregate_counter_rate("requests_total")
        
        assert len(rates) == 3  # 三个标签组合
        
        # 验证速率都是正数
        for rate in rates.values():
            assert rate > 0
    
    def test_gauge_statistics(self, aggregator):
        """测试仪表统计计算"""
        stats = aggregator.aggregate_gauge_stats("cpu_usage")
        
        assert stats["count"] == 5  # 更新为5个数据点
        assert stats["min"] == 25.0
        assert stats["max"] == 85.0
        assert 25.0 <= stats["mean"] <= 85.0
        assert stats["std_dev"] > 0  # 应该有标准差
        
        # 验证总和
        expected_sum = 25.0 + 45.0 + 85.0 + 30.0 + 35.0
        assert abs(stats["sum"] - expected_sum) < 0.001
    
    def test_histogram_percentiles(self, aggregator):
        """测试直方图百分位数计算"""
        percentiles = aggregator.aggregate_histogram_percentiles("response_time")
        
        assert len(percentiles) > 0
        
        # 检查第一个标签组合的百分位数
        first_result = next(iter(percentiles.values()))
        
        assert "p50.0" in first_result or "p50" in first_result
        assert "p90.0" in first_result or "p90" in first_result
        assert "p95.0" in first_result or "p95" in first_result
        assert "p99.0" in first_result or "p99" in first_result
        assert "mean" in first_result
        
        # 百分位数应该是递增的
        p50_key = "p50.0" if "p50.0" in first_result else "p50"
        p90_key = "p90.0" if "p90.0" in first_result else "p90"
        p95_key = "p95.0" if "p95.0" in first_result else "p95"
        p99_key = "p99.0" if "p99.0" in first_result else "p99"
        
        assert first_result[p50_key] <= first_result[p90_key]
        assert first_result[p90_key] <= first_result[p95_key]
        assert first_result[p95_key] <= first_result[p99_key]
    
    def test_category_aggregation(self, aggregator):
        """测试按分类聚合"""
        api_aggregation = aggregator.aggregate_by_category(MetricCategory.API)
        
        assert api_aggregation["category"] == "api"
        assert api_aggregation["total_metrics"] >= 1  # requests_total 及可能的其他API指标
        assert "COUNTER" in api_aggregation["by_type"]
        assert api_aggregation["by_type"]["COUNTER"]["count"] >= 1
        assert api_aggregation["metrics_with_data"] >= 1
        
        system_aggregation = aggregator.aggregate_by_category(MetricCategory.SYSTEM)
        
        assert system_aggregation["category"] == "system"
        assert system_aggregation["total_metrics"] >= 1  # cpu_usage 及可能的其他系统指标
        assert "GAUGE" in system_aggregation["by_type"]
    
    def test_anomaly_detection(self, aggregator):
        """测试异常检测"""
        anomalies = aggregator.detect_anomalies("cpu_usage", threshold_multiplier=2.0)
        
        # 应该检测到server3的异常值（85.0）
        assert len(anomalies) > 0
        
        # 找到server3的异常
        server3_anomaly = next(
            (a for a in anomalies if a["labels"].get("host") == "server3"), 
            None
        )
        assert server3_anomaly is not None
        assert server3_anomaly["value"] == 85.0
        assert server3_anomaly["deviation"] > server3_anomaly["threshold"]
    
    def test_sla_calculation(self, aggregator, registry_with_data):
        """测试SLA计算"""
        # 添加成功请求指标
        success_def = MetricDefinition(
            name="requests_success",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.API
        )
        registry_with_data.register_metric(success_def)
        
        success_metric = registry_with_data.get_metric("requests_success")
        success_metric.increment(950, {"service": "api"})  # 95%成功率
        
        # 添加总请求指标
        total_def = MetricDefinition(
            name="requests_all",
            metric_type=MetricType.COUNTER,
            category=MetricCategory.API
        )
        registry_with_data.register_metric(total_def)
        
        total_metric = registry_with_data.get_metric("requests_all")
        total_metric.increment(1000, {"service": "api"})  # 总计1000请求
        
        # 计算SLA
        sla_metrics = aggregator.calculate_sla_metrics("requests_success", "requests_all")
        
        assert len(sla_metrics) > 0
        
        # 检查API服务的SLA
        api_sla = next(iter(sla_metrics.values()))
        assert api_sla["availability_percent"] == 95.0
        assert api_sla["error_rate_percent"] == 5.0
        assert api_sla["success_count"] == 950
        assert api_sla["total_count"] == 1000
    
    def test_empty_metrics_handling(self, aggregator):
        """测试空指标处理"""
        # 测试不存在的指标
        rates = aggregator.aggregate_counter_rate("nonexistent_metric")
        assert rates == {}
        
        stats = aggregator.aggregate_gauge_stats("nonexistent_metric")
        assert stats == {}
        
        percentiles = aggregator.aggregate_histogram_percentiles("nonexistent_metric")
        assert percentiles == {}
        
        anomalies = aggregator.detect_anomalies("nonexistent_metric")
        assert anomalies == []
    
    def test_single_value_metrics(self, aggregator, registry_with_data):
        """测试单值指标处理"""
        # 创建只有一个值的指标
        single_def = MetricDefinition(
            name="single_gauge",
            metric_type=MetricType.GAUGE,
            category=MetricCategory.SYSTEM
        )
        registry_with_data.register_metric(single_def)
        
        single_metric = registry_with_data.get_metric("single_gauge")
        single_metric.set_value(42.0, {"component": "test"})
        
        # 测试统计计算
        stats = aggregator.aggregate_gauge_stats("single_gauge")
        
        assert stats["count"] == 1
        assert stats["min"] == 42.0
        assert stats["max"] == 42.0
        assert stats["mean"] == 42.0
        assert stats["std_dev"] == 0.0  # 单值的标准差为0
        
        # 测试异常检测（单值不应该有异常）
        anomalies = aggregator.detect_anomalies("single_gauge")
        assert anomalies == []


class TestAdvancedAggregation:
    """高级聚合测试"""
    
    @pytest.fixture
    def time_series_registry(self):
        """时间序列数据注册表"""
        registry = MetricRegistry()
        
        # 创建时间序列指标
        ts_def = MetricDefinition(
            name="time_series_metric",
            metric_type=MetricType.GAUGE,
            category=MetricCategory.BUSINESS
        )
        registry.register_metric(ts_def)
        
        metric = registry.get_metric("time_series_metric")
        
        # 模拟时间序列数据
        base_time = time.time() - 3600  # 1小时前开始
        for i in range(60):  # 60个数据点
            timestamp = base_time + (i * 60)  # 每分钟一个点
            value = 50 + 10 * (i % 10) + (i * 0.5)  # 模拟趋势和周期性
            
            # 手动设置时间戳
            metric_value = MetricValue(value=value, timestamp=timestamp)
            metric.values[f"series_{i}"] = metric_value
        
        return registry
    
    def test_time_series_trend_analysis(self, time_series_registry):
        """测试时间序列趋势分析"""
        aggregator = MetricAggregator(time_series_registry)
        metric = time_series_registry.get_metric("time_series_metric")
        
        # 获取按时间排序的值
        values_with_time = [
            (mv.timestamp, mv.value) 
            for mv in metric.get_values().values()
        ]
        values_with_time.sort(key=lambda x: x[0])
        
        # 简单的趋势检测
        values = [v[1] for v in values_with_time]
        
        # 计算移动平均
        window_size = 5
        moving_averages = []
        for i in range(len(values) - window_size + 1):
            window = values[i:i + window_size]
            moving_averages.append(sum(window) / len(window))
        
        # 检查趋势（最后的移动平均应该大于最初的）
        assert len(moving_averages) > 0
        trend = moving_averages[-1] - moving_averages[0]
        assert trend > 0  # 应该有上升趋势
    
    def test_correlation_analysis(self, time_series_registry):
        """测试相关性分析"""
        # 添加第二个相关指标
        corr_def = MetricDefinition(
            name="correlated_metric",
            metric_type=MetricType.GAUGE,
            category=MetricCategory.BUSINESS
        )
        time_series_registry.register_metric(corr_def)
        
        corr_metric = time_series_registry.get_metric("correlated_metric")
        original_metric = time_series_registry.get_metric("time_series_metric")
        
        # 创建相关数据（与原始指标正相关）
        for key, original_value in original_metric.get_values().items():
            correlated_value = original_value.value * 1.5 + 10  # 正相关关系
            corr_metric.set_value(correlated_value)
        
        # 简单的相关系数计算
        original_values = [mv.value for mv in original_metric.get_values().values()]
        correlated_values = [mv.value for mv in corr_metric.get_values().values()]
        
        # 计算皮尔逊相关系数
        if len(original_values) > 1 and len(correlated_values) > 1:
            correlation = self._calculate_correlation(original_values, correlated_values)
            assert correlation > 0.9  # 应该有强正相关
    
    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """计算皮尔逊相关系数"""
        n = len(x)
        if n != len(y) or n < 2:
            return 0.0
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        denominator = (sum_sq_x * sum_sq_y) ** 0.5
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator


class TestMetricAggregationIntegration:
    """指标聚合集成测试"""
    
    def test_unified_manager_aggregation(self):
        """测试统一管理器的聚合功能"""
        manager = UnifiedMetricsManager()
        
        # 注册指标
        manager.registry.register_custom_metric(
            "integration_counter",
            MetricType.COUNTER,
            MetricCategory.BUSINESS
        )
        
        manager.registry.register_custom_metric(
            "integration_gauge",
            MetricType.GAUGE,
            MetricCategory.SYSTEM
        )
        
        # 设置数据
        for i in range(10):
            manager.increment("integration_counter", i, {"batch": str(i // 5)})
            manager.set_gauge("integration_gauge", i * 10, {"server": f"host{i}"})
        
        # 创建聚合器
        aggregator = MetricAggregator(manager.registry)
        
        # 测试聚合
        business_agg = aggregator.aggregate_by_category(MetricCategory.BUSINESS)
        system_agg = aggregator.aggregate_by_category(MetricCategory.SYSTEM)
        
        assert business_agg["total_metrics"] >= 1  # 可能有其他业务指标
        assert system_agg["total_metrics"] >= 1  # 可能有其他系统指标
        
        # 测试统计
        gauge_stats = aggregator.aggregate_gauge_stats("integration_gauge")
        assert gauge_stats["count"] == 10
        assert gauge_stats["min"] == 0
        assert gauge_stats["max"] == 90
    
    def test_real_time_aggregation(self):
        """测试实时聚合"""
        manager = UnifiedMetricsManager()
        
        # 注册指标
        manager.registry.register_custom_metric(
            "realtime_metric",
            MetricType.GAUGE,
            MetricCategory.PERFORMANCE
        )
        
        aggregator = MetricAggregator(manager.registry)
        
        # 实时添加数据并聚合
        for i in range(5):
            manager.set_gauge("realtime_metric", i * 2, {"iteration": str(i)})
            
            # 每次添加后检查聚合结果
            stats = aggregator.aggregate_gauge_stats("realtime_metric")
            assert stats["count"] == i + 1
            assert stats["max"] == i * 2
        
        # 最终验证
        final_stats = aggregator.aggregate_gauge_stats("realtime_metric")
        assert final_stats["count"] == 5
        assert final_stats["sum"] == 20  # 0+2+4+6+8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])