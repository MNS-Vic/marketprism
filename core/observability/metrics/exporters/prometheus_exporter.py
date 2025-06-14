"""
Prometheus指标导出器

将统一指标管理器中的指标导出为Prometheus格式。
"""

import time
from typing import Dict, List, Optional, Any, TextIO
from io import StringIO
import logging
from datetime import datetime, timezone

from ..metric_categories import MetricType, MetricDefinition
from ..metric_registry import MetricInstance, MetricValue, HistogramValue, SummaryValue

logger = logging.getLogger(__name__)


class PrometheusExporter:
    """Prometheus指标导出器"""
    
    def __init__(self, include_timestamp: bool = True, include_help: bool = True):
        self.include_timestamp = include_timestamp
        self.include_help = include_help
    
    def export_metrics(self, metrics: Dict[str, MetricInstance]) -> str:
        """导出指标为Prometheus格式"""
        output = StringIO()
        
        try:
            # 按指标名称排序
            sorted_metrics = sorted(metrics.items())
            
            for metric_name, metric_instance in sorted_metrics:
                self._export_metric(output, metric_name, metric_instance)
                output.write('\n')  # 指标间添加空行
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"导出Prometheus指标失败: {e}")
            return ""
        finally:
            output.close()
    
    def _export_metric(self, output: TextIO, metric_name: str, 
                      metric_instance: MetricInstance) -> None:
        """导出单个指标"""
        definition = metric_instance.definition
        
        # 写入HELP注释
        if self.include_help and definition.help_text:
            output.write(f"# HELP {definition.prometheus_name} {definition.help_text}\n")
        
        # 写入TYPE注释
        prometheus_type = self._get_prometheus_type(definition.metric_type)
        output.write(f"# TYPE {definition.prometheus_name} {prometheus_type}\n")
        
        # 导出指标值
        if definition.metric_type == MetricType.HISTOGRAM:
            self._export_histogram(output, definition, metric_instance)
        elif definition.metric_type == MetricType.SUMMARY:
            self._export_summary(output, definition, metric_instance)
        else:
            self._export_simple_metric(output, definition, metric_instance)
    
    def _export_simple_metric(self, output: TextIO, definition: MetricDefinition,
                             metric_instance: MetricInstance) -> None:
        """导出简单指标（Counter/Gauge）"""
        for metric_value in metric_instance.get_values().values():
            labels_str = self._format_labels(metric_value.labels)
            timestamp_str = self._format_timestamp(metric_value.timestamp)
            
            output.write(f"{definition.prometheus_name}{labels_str} {metric_value.value}{timestamp_str}\n")
    
    def _export_histogram(self, output: TextIO, definition: MetricDefinition,
                         metric_instance: MetricInstance) -> None:
        """导出直方图指标"""
        for hist_value in metric_instance.get_values().values():
            if not isinstance(hist_value, HistogramValue):
                continue
            
            base_labels = hist_value.labels.copy()
            
            # 导出桶数据
            for bucket in hist_value.buckets:
                bucket_labels = base_labels.copy()
                bucket_labels['le'] = str(bucket.upper_bound)
                labels_str = self._format_labels(bucket_labels)
                timestamp_str = self._format_timestamp(hist_value.timestamp)
                
                output.write(f"{definition.prometheus_name}_bucket{labels_str} {bucket.count}{timestamp_str}\n")
            
            # 导出总数和和值
            labels_str = self._format_labels(base_labels)
            timestamp_str = self._format_timestamp(hist_value.timestamp)
            
            output.write(f"{definition.prometheus_name}_sum{labels_str} {hist_value.sum}{timestamp_str}\n")
            output.write(f"{definition.prometheus_name}_count{labels_str} {hist_value.count}{timestamp_str}\n")
    
    def _export_summary(self, output: TextIO, definition: MetricDefinition,
                       metric_instance: MetricInstance) -> None:
        """导出摘要指标"""
        for summary_value in metric_instance.get_values().values():
            if not isinstance(summary_value, SummaryValue):
                continue
            
            base_labels = summary_value.labels.copy()
            
            # 导出分位数
            for quantile, value in summary_value.quantiles.items():
                quantile_labels = base_labels.copy()
                quantile_labels['quantile'] = str(quantile)
                labels_str = self._format_labels(quantile_labels)
                timestamp_str = self._format_timestamp(summary_value.timestamp)
                
                output.write(f"{definition.prometheus_name}{labels_str} {value}{timestamp_str}\n")
            
            # 导出总数和和值
            labels_str = self._format_labels(base_labels)
            timestamp_str = self._format_timestamp(summary_value.timestamp)
            
            output.write(f"{definition.prometheus_name}_sum{labels_str} {summary_value.sum}{timestamp_str}\n")
            output.write(f"{definition.prometheus_name}_count{labels_str} {summary_value.count}{timestamp_str}\n")
    
    def _format_labels(self, labels: Dict[str, str]) -> str:
        """格式化标签"""
        if not labels:
            return ""
        
        # 转义标签值中的特殊字符
        escaped_labels = []
        for key, value in sorted(labels.items()):
            escaped_value = self._escape_label_value(str(value))
            escaped_labels.append(f'{key}="{escaped_value}"')
        
        return "{" + ",".join(escaped_labels) + "}"
    
    def _escape_label_value(self, value: str) -> str:
        """转义标签值"""
        # 转义反斜杠、双引号和换行符
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    
    def _format_timestamp(self, timestamp: float) -> str:
        """格式化时间戳"""
        if not self.include_timestamp:
            return ""
        
        # Prometheus使用毫秒时间戳
        return f" {int(timestamp * 1000)}"
    
    def _get_prometheus_type(self, metric_type: MetricType) -> str:
        """获取Prometheus指标类型"""
        type_mapping = {
            MetricType.COUNTER: "counter",
            MetricType.GAUGE: "gauge",
            MetricType.HISTOGRAM: "histogram",
            MetricType.SUMMARY: "summary",
            MetricType.TIMER: "histogram"  # 计时器作为直方图处理
        }
        
        return type_mapping.get(metric_type, "gauge")


class PrometheusMetricsHandler:
    """Prometheus指标HTTP处理器"""
    
    def __init__(self, metrics_manager, exporter: Optional[PrometheusExporter] = None):
        self.metrics_manager = metrics_manager
        self.exporter = exporter or PrometheusExporter()
        self.content_type = "text/plain; version=0.0.4; charset=utf-8"
    
    def get_metrics(self) -> tuple[str, str]:
        """获取指标内容和内容类型"""
        try:
            # 获取所有指标
            metrics = self.metrics_manager.registry.get_all_metrics()
            
            # 导出为Prometheus格式
            content = self.exporter.export_metrics(metrics)
            
            return content, self.content_type
            
        except Exception as e:
            logger.error(f"获取Prometheus指标失败: {e}")
            error_content = f"# Error exporting metrics: {e}\n"
            return error_content, self.content_type
    
    def handle_request(self) -> Dict[str, Any]:
        """处理HTTP请求"""
        content, content_type = self.get_metrics()
        
        return {
            "status_code": 200,
            "headers": {
                "Content-Type": content_type,
                "Cache-Control": "no-cache"
            },
            "body": content
        }


class PrometheusGatewayPusher:
    """Prometheus网关推送器"""
    
    def __init__(self, gateway_url: str, job_name: str, 
                 instance_name: Optional[str] = None):
        self.gateway_url = gateway_url.rstrip('/')
        self.job_name = job_name
        self.instance_name = instance_name or "marketprism"
        self.exporter = PrometheusExporter(include_timestamp=False)
    
    def push_metrics(self, metrics: Dict[str, MetricInstance]) -> bool:
        """推送指标到Prometheus网关"""
        try:
            import requests
            
            # 导出指标
            content = self.exporter.export_metrics(metrics)
            
            # 构建推送URL
            url = f"{self.gateway_url}/metrics/job/{self.job_name}/instance/{self.instance_name}"
            
            # 推送到网关
            response = requests.post(
                url,
                data=content,
                headers={"Content-Type": "text/plain"},
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"成功推送指标到Prometheus网关: {url}")
                return True
            else:
                logger.error(f"推送指标到Prometheus网关失败: {response.status_code} - {response.text}")
                return False
                
        except ImportError:
            logger.error("推送到Prometheus网关需要安装requests库")
            return False
        except Exception as e:
            logger.error(f"推送指标到Prometheus网关失败: {e}")
            return False
    
    def delete_metrics(self) -> bool:
        """从Prometheus网关删除指标"""
        try:
            import requests
            
            # 构建删除URL
            url = f"{self.gateway_url}/metrics/job/{self.job_name}/instance/{self.instance_name}"
            
            # 发送DELETE请求
            response = requests.delete(url, timeout=30)
            
            if response.status_code == 202:
                logger.info(f"成功从Prometheus网关删除指标: {url}")
                return True
            else:
                logger.error(f"从Prometheus网关删除指标失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"从Prometheus网关删除指标失败: {e}")
            return False


def create_prometheus_exporter(**kwargs) -> PrometheusExporter:
    """创建Prometheus导出器的工厂函数"""
    return PrometheusExporter(**kwargs)


def create_metrics_handler(metrics_manager, **kwargs) -> PrometheusMetricsHandler:
    """创建指标处理器的工厂函数"""
    return PrometheusMetricsHandler(metrics_manager, **kwargs)


# 示例使用
if __name__ == "__main__":
    # 这里可以添加测试代码
    from ..unified_metrics_manager import get_global_manager
    from ..metric_categories import MetricType, MetricCategory
    
    # 获取全局管理器
    manager = get_global_manager()
    
    # 注册测试指标
    manager.registry.register_custom_metric(
        "test_counter",
        MetricType.COUNTER,
        MetricCategory.BUSINESS,
        "测试计数器"
    )
    
    # 设置一些值
    manager.increment("test_counter", 10, {"service": "test"})
    manager.increment("test_counter", 5, {"service": "demo"})
    
    # 导出指标
    exporter = PrometheusExporter()
    metrics = manager.registry.get_all_metrics()
    output = exporter.export_metrics(metrics)
    
    print("Prometheus指标导出示例:")
    print(output)