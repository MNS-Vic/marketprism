"""
MetricsAggregator 单元测试
"""

import pytest
import asyncio
import time
from core.metrics_aggregator import (
    MetricsAggregator, MetricsCollector, MetricNames
)


class TestMetricsCollector:
    """测试 MetricsCollector"""
    
    def test_create_collector(self):
        """测试创建收集器"""
        collector = MetricsCollector("okx_spot")
        assert collector.exchange == "okx_spot"
        assert collector.metrics == {}
    
    def test_set_metric(self):
        """测试设置指标"""
        collector = MetricsCollector("okx_spot")
        collector.set_metric("cpu_percent", 45.5)
        
        assert collector.get_metric("cpu_percent") == 45.5
    
    def test_increment_metric(self):
        """测试增加指标"""
        collector = MetricsCollector("okx_spot")
        
        # 第一次增加
        collector.increment_metric("data_count", 10)
        assert collector.get_metric("data_count") == 10
        
        # 第二次增加
        collector.increment_metric("data_count", 5)
        assert collector.get_metric("data_count") == 15
    
    def test_get_all_metrics(self):
        """测试获取所有指标"""
        collector = MetricsCollector("okx_spot")
        collector.set_metric("cpu_percent", 45.5)
        collector.set_metric("memory_mb", 120.0)
        
        metrics = collector.get_all_metrics()
        assert metrics == {"cpu_percent": 45.5, "memory_mb": 120.0}
    
    def test_clear_metrics(self):
        """测试清除指标"""
        collector = MetricsCollector("okx_spot")
        collector.set_metric("cpu_percent", 45.5)
        collector.clear_metrics()
        
        assert collector.metrics == {}
    
    def test_to_dict(self):
        """测试转换为字典"""
        collector = MetricsCollector("okx_spot")
        collector.set_metric("cpu_percent", 45.5)
        
        d = collector.to_dict()
        assert d == {"cpu_percent": 45.5}


class TestMetricsAggregator:
    """测试 MetricsAggregator"""
    
    def test_create_aggregator(self):
        """测试创建聚合器"""
        aggregator = MetricsAggregator()
        assert aggregator.process_metrics == {}
        assert aggregator.aggregated_metrics == {}
    
    def test_update_process_metrics(self):
        """测试更新进程指标"""
        aggregator = MetricsAggregator()
        
        metrics = {"cpu_percent": 45.5, "memory_mb": 120.0}
        aggregator.update_process_metrics("okx_spot", metrics)
        
        assert "okx_spot" in aggregator.process_metrics
        assert aggregator.process_metrics["okx_spot"] == metrics
    
    def test_aggregate_metrics_sum(self):
        """测试聚合指标（求和）"""
        aggregator = MetricsAggregator()
        
        # 添加多个进程的指标
        aggregator.update_process_metrics("okx_spot", {
            "data_count_total": 100,
            "error_count_total": 5
        })
        aggregator.update_process_metrics("binance_spot", {
            "data_count_total": 200,
            "error_count_total": 3
        })
        
        # 检查聚合结果
        aggregated = aggregator.get_aggregated_metrics()
        assert aggregated["data_count_total"] == 300
        assert aggregated["error_count_total"] == 8
    
    def test_aggregate_metrics_average(self):
        """测试聚合指标（平均值）"""
        aggregator = MetricsAggregator()
        
        # 添加多个进程的 CPU 指标
        aggregator.update_process_metrics("okx_spot", {"cpu_percent": 40.0})
        aggregator.update_process_metrics("binance_spot", {"cpu_percent": 60.0})
        
        # 检查聚合结果（CPU 使用平均值）
        aggregated = aggregator.get_aggregated_metrics()
        assert aggregated["cpu_percent"] == 50.0
    
    def test_get_process_metrics(self):
        """测试获取指定进程的指标"""
        aggregator = MetricsAggregator()
        
        metrics = {"cpu_percent": 45.5}
        aggregator.update_process_metrics("okx_spot", metrics)
        
        result = aggregator.get_process_metrics("okx_spot")
        assert result == metrics
    
    def test_get_all_process_metrics(self):
        """测试获取所有进程的指标"""
        aggregator = MetricsAggregator()
        
        aggregator.update_process_metrics("okx_spot", {"cpu_percent": 40.0})
        aggregator.update_process_metrics("binance_spot", {"cpu_percent": 60.0})
        
        all_metrics = aggregator.get_all_process_metrics()
        assert len(all_metrics) == 2
        assert "okx_spot" in all_metrics
        assert "binance_spot" in all_metrics
    
    def test_generate_prometheus_metrics(self):
        """测试生成 Prometheus 格式指标"""
        aggregator = MetricsAggregator()
        
        aggregator.update_process_metrics("okx_spot", {
            "cpu_percent": 40.0,
            "memory_mb": 100.0
        })
        aggregator.update_process_metrics("binance_spot", {
            "cpu_percent": 60.0,
            "memory_mb": 150.0
        })
        
        prometheus_text = aggregator.generate_prometheus_metrics()
        
        # 检查聚合指标
        assert "cpu_percent 50.0" in prometheus_text
        assert "memory_mb 125.0" in prometheus_text
        
        # 检查按进程分组的指标
        assert 'cpu_percent{process="okx_spot"} 40.0' in prometheus_text
        assert 'cpu_percent{process="binance_spot"} 60.0' in prometheus_text
    
    def test_clear_process_metrics(self):
        """测试清除指定进程的指标"""
        aggregator = MetricsAggregator()
        
        aggregator.update_process_metrics("okx_spot", {"cpu_percent": 40.0})
        aggregator.update_process_metrics("binance_spot", {"cpu_percent": 60.0})
        
        aggregator.clear_process_metrics("okx_spot")
        
        assert "okx_spot" not in aggregator.process_metrics
        assert "binance_spot" in aggregator.process_metrics
    
    def test_clear_all_metrics(self):
        """测试清除所有指标"""
        aggregator = MetricsAggregator()
        
        aggregator.update_process_metrics("okx_spot", {"cpu_percent": 40.0})
        aggregator.update_process_metrics("binance_spot", {"cpu_percent": 60.0})
        
        aggregator.clear_all_metrics()
        
        assert aggregator.process_metrics == {}
        assert aggregator.aggregated_metrics == {}
    
    def test_metric_ttl(self):
        """测试指标过期"""
        aggregator = MetricsAggregator()
        aggregator.metric_ttl = 0.5  # 0.5 秒过期
        
        # 添加指标
        aggregator.update_process_metrics("okx_spot", {"cpu_percent": 40.0})
        
        # 立即检查（未过期）
        aggregated = aggregator.get_aggregated_metrics()
        assert "cpu_percent" in aggregated
        
        # 等待过期
        time.sleep(0.6)
        
        # 重新聚合（应该过期）
        aggregator._aggregate_metrics()
        aggregated = aggregator.get_aggregated_metrics()
        assert "cpu_percent" not in aggregated or aggregated["cpu_percent"] == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_metrics(self):
        """测试清理过期指标"""
        aggregator = MetricsAggregator()
        aggregator.metric_ttl = 0.5  # 0.5 秒过期
        
        # 添加指标
        aggregator.update_process_metrics("okx_spot", {"cpu_percent": 40.0})
        
        # 启动清理任务
        cleanup_task = asyncio.create_task(
            aggregator.cleanup_expired_metrics(interval=0.3)
        )
        
        # 等待过期和清理
        await asyncio.sleep(1.0)
        
        # 取消任务
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        
        # 检查是否已清理
        assert "okx_spot" not in aggregator.process_metrics


class TestMetricNames:
    """测试 MetricNames 常量"""
    
    def test_metric_names_constants(self):
        """测试指标名称常量"""
        assert MetricNames.CPU_PERCENT == "marketprism_process_cpu_percent"
        assert MetricNames.MEMORY_MB == "marketprism_process_memory_mb"
        assert MetricNames.DATA_COUNT_TOTAL == "marketprism_data_count_total"
        assert MetricNames.ERROR_COUNT_TOTAL == "marketprism_error_count_total"
        assert MetricNames.PROCESS_UPTIME_SECONDS == "marketprism_process_uptime_seconds"


class TestIntegration:
    """集成测试"""
    
    def test_collector_to_aggregator_flow(self):
        """测试从收集器到聚合器的完整流程"""
        # 创建收集器
        collector1 = MetricsCollector("okx_spot")
        collector1.set_metric(MetricNames.CPU_PERCENT, 40.0)
        collector1.set_metric(MetricNames.MEMORY_MB, 100.0)
        
        collector2 = MetricsCollector("binance_spot")
        collector2.set_metric(MetricNames.CPU_PERCENT, 60.0)
        collector2.set_metric(MetricNames.MEMORY_MB, 150.0)
        
        # 创建聚合器
        aggregator = MetricsAggregator()
        
        # 更新指标
        aggregator.update_process_metrics("okx_spot", collector1.to_dict())
        aggregator.update_process_metrics("binance_spot", collector2.to_dict())
        
        # 检查聚合结果
        aggregated = aggregator.get_aggregated_metrics()
        assert aggregated[MetricNames.CPU_PERCENT] == 50.0
        assert aggregated[MetricNames.MEMORY_MB] == 125.0
        
        # 生成 Prometheus 格式
        prometheus_text = aggregator.generate_prometheus_metrics()
        assert MetricNames.CPU_PERCENT in prometheus_text
        assert "okx_spot" in prometheus_text
        assert "binance_spot" in prometheus_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

