"""
JSON指标导出器

将统一指标管理器中的指标导出为JSON格式，便于API集成和自定义处理。
"""

import json
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import logging

from ..metric_categories import MetricType, MetricDefinition, MetricCategory, MetricSeverity
from ..metric_registry import MetricInstance, MetricValue, HistogramValue, SummaryValue

logger = logging.getLogger(__name__)


class JSONExporter:
    """JSON指标导出器"""
    
    def __init__(self, include_metadata: bool = True, include_timestamps: bool = True,
                 pretty_print: bool = False, include_empty_metrics: bool = False):
        self.include_metadata = include_metadata
        self.include_timestamps = include_timestamps
        self.pretty_print = pretty_print
        self.include_empty_metrics = include_empty_metrics
    
    def export_metrics(self, metrics: Dict[str, MetricInstance]) -> str:
        """导出指标为JSON格式"""
        try:
            export_data = self._build_export_data(metrics)
            
            if self.pretty_print:
                return json.dumps(export_data, indent=2, ensure_ascii=False, default=self._json_serializer)
            else:
                return json.dumps(export_data, ensure_ascii=False, default=self._json_serializer)
                
        except Exception as e:
            logger.error(f"导出JSON指标失败: {e}")
            return json.dumps({"error": f"导出失败: {str(e)}"})
    
    def _build_export_data(self, metrics: Dict[str, MetricInstance]) -> Dict[str, Any]:
        """构建导出数据结构"""
        export_data = {
            "metrics": {},
            "summary": {
                "total_metrics": len(metrics),
                "export_timestamp": datetime.utcnow().isoformat() + "Z",
                "exporter_version": "1.0.0"
            }
        }
        
        if self.include_metadata:
            export_data["metadata"] = self._build_metadata(metrics)
        
        # 导出各个指标
        for metric_name, metric_instance in metrics.items():
            metric_data = self._export_metric_instance(metric_instance)
            
            # 跳过空指标（如果配置了）
            if not self.include_empty_metrics and not metric_data.get("values"):
                continue
            
            export_data["metrics"][metric_name] = metric_data
        
        # 更新摘要统计
        export_data["summary"]["exported_metrics"] = len(export_data["metrics"])
        
        return export_data
    
    def _build_metadata(self, metrics: Dict[str, MetricInstance]) -> Dict[str, Any]:
        """构建元数据"""
        metadata = {
            "categories": {},
            "types": {},
            "severities": {}
        }
        
        for metric_instance in metrics.values():
            definition = metric_instance.definition
            
            # 统计分类
            category = definition.category.value
            metadata["categories"][category] = metadata["categories"].get(category, 0) + 1
            
            # 统计类型
            metric_type = definition.metric_type.name
            metadata["types"][metric_type] = metadata["types"].get(metric_type, 0) + 1
            
            # 统计严重性
            severity = definition.severity.value
            metadata["severities"][severity] = metadata["severities"].get(severity, 0) + 1
        
        return metadata
    
    def _export_metric_instance(self, metric_instance: MetricInstance) -> Dict[str, Any]:
        """导出指标实例"""
        definition = metric_instance.definition
        
        metric_data = {
            "definition": self._export_metric_definition(definition),
            "values": self._export_metric_values(metric_instance),
            "statistics": {
                "value_count": len(metric_instance.get_values()),
                "created_at": metric_instance.created_at,
                "last_updated": metric_instance.last_updated
            }
        }
        
        return metric_data
    
    def _export_metric_definition(self, definition: MetricDefinition) -> Dict[str, Any]:
        """导出指标定义"""
        def_data = {
            "name": definition.name,
            "full_name": definition.full_name,
            "prometheus_name": definition.prometheus_name,
            "type": definition.metric_type.name,
            "category": definition.category.value,
            "description": definition.description,
            "unit": definition.unit,
            "labels": definition.labels,
            "severity": definition.severity.value,
            "help_text": definition.help_text
        }
        
        if definition.subcategory:
            def_data["subcategory"] = definition.subcategory.value
        
        if definition.tags:
            def_data["tags"] = list(definition.tags)
        
        return def_data
    
    def _export_metric_values(self, metric_instance: MetricInstance) -> List[Dict[str, Any]]:
        """导出指标值"""
        values = []
        
        for metric_value in metric_instance.get_values().values():
            value_data = self._export_single_value(metric_value, metric_instance.definition.metric_type)
            values.append(value_data)
        
        return values
    
    def _export_single_value(self, metric_value: MetricValue, metric_type: MetricType) -> Dict[str, Any]:
        """导出单个指标值"""
        base_data = {
            "labels": metric_value.labels,
            "metadata": metric_value.metadata
        }
        
        if self.include_timestamps:
            base_data["timestamp"] = metric_value.timestamp
            base_data["timestamp_iso"] = datetime.fromtimestamp(metric_value.timestamp).isoformat() + "Z"
        
        if isinstance(metric_value, HistogramValue):
            return self._export_histogram_value(metric_value, base_data)
        elif isinstance(metric_value, SummaryValue):
            return self._export_summary_value(metric_value, base_data)
        else:
            base_data["value"] = metric_value.value
            base_data["type"] = "simple"
            return base_data
    
    def _export_histogram_value(self, hist_value: HistogramValue, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """导出直方图值"""
        base_data.update({
            "type": "histogram",
            "sum": hist_value.sum,
            "count": hist_value.count,
            "buckets": [
                {
                    "upper_bound": bucket.upper_bound,
                    "count": bucket.count
                }
                for bucket in hist_value.buckets
            ]
        })
        
        return base_data
    
    def _export_summary_value(self, summary_value: SummaryValue, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """导出摘要值"""
        base_data.update({
            "type": "summary",
            "sum": summary_value.sum,
            "count": summary_value.count,
            "quantiles": summary_value.quantiles
        })
        
        return base_data
    
    def _json_serializer(self, obj):
        """JSON序列化器，处理特殊类型"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return str(obj)


class JSONMetricsAPI:
    """JSON指标API封装"""
    
    def __init__(self, metrics_manager, exporter: Optional[JSONExporter] = None):
        self.metrics_manager = metrics_manager
        self.exporter = exporter or JSONExporter()
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        try:
            metrics = self.metrics_manager.registry.get_all_metrics()
            content = self.exporter.export_metrics(metrics)
            
            return {
                "success": True,
                "data": json.loads(content),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            logger.error(f"获取所有指标失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    
    def get_metrics_by_category(self, category: str) -> Dict[str, Any]:
        """按分类获取指标"""
        try:
            # 验证分类
            try:
                metric_category = MetricCategory(category)
            except ValueError:
                return {
                    "success": False,
                    "error": f"无效的指标分类: {category}",
                    "available_categories": [cat.value for cat in MetricCategory]
                }
            
            metrics = self.metrics_manager.registry.get_metrics_by_category(metric_category)
            content = self.exporter.export_metrics(metrics)
            
            return {
                "success": True,
                "category": category,
                "data": json.loads(content),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            logger.error(f"按分类获取指标失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    
    def get_metric_by_name(self, metric_name: str) -> Dict[str, Any]:
        """按名称获取单个指标"""
        try:
            metric_instance = self.metrics_manager.registry.get_metric(metric_name)
            
            if not metric_instance:
                return {
                    "success": False,
                    "error": f"指标不存在: {metric_name}",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            
            metrics = {metric_name: metric_instance}
            content = self.exporter.export_metrics(metrics)
            
            return {
                "success": True,
                "metric_name": metric_name,
                "data": json.loads(content),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            logger.error(f"按名称获取指标失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        try:
            registry_stats = self.metrics_manager.registry.get_stats()
            manager_stats = self.metrics_manager.get_stats()
            
            return {
                "success": True,
                "summary": {
                    "registry": registry_stats,
                    "manager": manager_stats,
                    "health": self.metrics_manager.get_health_status()
                },
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            logger.error(f"获取指标摘要失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    
    def search_metrics(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """搜索指标"""
        try:
            all_metrics = self.metrics_manager.registry.get_all_metrics()
            
            # 简单的名称匹配搜索
            matching_metrics = {}
            count = 0
            
            for metric_name, metric_instance in all_metrics.items():
                if count >= limit:
                    break
                
                if (query.lower() in metric_name.lower() or 
                    query.lower() in metric_instance.definition.description.lower()):
                    matching_metrics[metric_name] = metric_instance
                    count += 1
            
            content = self.exporter.export_metrics(matching_metrics)
            
            return {
                "success": True,
                "query": query,
                "total_found": count,
                "limit": limit,
                "data": json.loads(content),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        except Exception as e:
            logger.error(f"搜索指标失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }


class MetricsReportGenerator:
    """指标报告生成器"""
    
    def __init__(self, metrics_manager, exporter: Optional[JSONExporter] = None):
        self.metrics_manager = metrics_manager
        self.exporter = exporter or JSONExporter(pretty_print=True)
    
    def generate_full_report(self) -> Dict[str, Any]:
        """生成完整指标报告"""
        try:
            metrics = self.metrics_manager.registry.get_all_metrics()
            
            report = {
                "report_info": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "report_type": "full_metrics_report",
                    "version": "1.0.0"
                },
                "system_info": self._get_system_info(),
                "metrics_summary": self._get_metrics_summary(metrics),
                "detailed_metrics": json.loads(self.exporter.export_metrics(metrics)),
                "health_status": self.metrics_manager.get_health_status(),
                "recommendations": self._generate_recommendations(metrics)
            }
            
            return report
        except Exception as e:
            logger.error(f"生成完整报告失败: {e}")
            return {
                "error": str(e),
                "generated_at": datetime.utcnow().isoformat() + "Z"
            }
    
    def _get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        import platform
        import sys
        
        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "hostname": platform.node(),
            "architecture": platform.architecture(),
            "processor": platform.processor()
        }
    
    def _get_metrics_summary(self, metrics: Dict[str, MetricInstance]) -> Dict[str, Any]:
        """获取指标摘要"""
        summary = {
            "total_metrics": len(metrics),
            "by_category": {},
            "by_type": {},
            "by_severity": {},
            "total_values": 0,
            "last_updated_metrics": []
        }
        
        recent_threshold = time.time() - 300  # 5分钟内更新的指标
        
        for metric_name, metric_instance in metrics.items():
            definition = metric_instance.definition
            
            # 按分类统计
            category = definition.category.value
            summary["by_category"][category] = summary["by_category"].get(category, 0) + 1
            
            # 按类型统计
            metric_type = definition.metric_type.name
            summary["by_type"][metric_type] = summary["by_type"].get(metric_type, 0) + 1
            
            # 按严重性统计
            severity = definition.severity.value
            summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1
            
            # 统计值数量
            summary["total_values"] += len(metric_instance.get_values())
            
            # 最近更新的指标
            if metric_instance.last_updated > recent_threshold:
                summary["last_updated_metrics"].append({
                    "name": metric_name,
                    "last_updated": metric_instance.last_updated,
                    "value_count": len(metric_instance.get_values())
                })
        
        # 排序最近更新的指标
        summary["last_updated_metrics"].sort(key=lambda x: x["last_updated"], reverse=True)
        summary["last_updated_metrics"] = summary["last_updated_metrics"][:10]  # 取前10个
        
        return summary
    
    def _generate_recommendations(self, metrics: Dict[str, MetricInstance]) -> List[Dict[str, str]]:
        """生成优化建议"""
        recommendations = []
        
        # 检查是否有过多的标签组合
        high_cardinality_metrics = []
        for metric_name, metric_instance in metrics.items():
            value_count = len(metric_instance.get_values())
            if value_count > 100:  # 标签组合超过100个
                high_cardinality_metrics.append((metric_name, value_count))
        
        if high_cardinality_metrics:
            recommendations.append({
                "type": "performance",
                "severity": "warning",
                "title": "高基数指标检测",
                "description": f"发现 {len(high_cardinality_metrics)} 个高基数指标，可能影响性能",
                "details": str(high_cardinality_metrics[:5])  # 只显示前5个
            })
        
        # 检查是否有长时间未更新的指标
        stale_threshold = time.time() - 3600  # 1小时
        stale_metrics = []
        for metric_name, metric_instance in metrics.items():
            if metric_instance.last_updated < stale_threshold:
                stale_metrics.append(metric_name)
        
        if stale_metrics:
            recommendations.append({
                "type": "maintenance",
                "severity": "info",
                "title": "过期指标检测",
                "description": f"发现 {len(stale_metrics)} 个长时间未更新的指标",
                "details": str(stale_metrics[:10])  # 只显示前10个
            })
        
        # 检查错误指标
        error_metrics = []
        for metric_name, metric_instance in metrics.items():
            if "error" in metric_name.lower() or metric_instance.definition.severity == MetricSeverity.CRITICAL:
                error_metrics.append(metric_name)
        
        if error_metrics:
            recommendations.append({
                "type": "monitoring",
                "severity": "high",
                "title": "错误指标监控",
                "description": f"建议重点监控 {len(error_metrics)} 个错误相关指标",
                "details": str(error_metrics[:5])
            })
        
        return recommendations


def create_json_exporter(**kwargs) -> JSONExporter:
    """创建JSON导出器的工厂函数"""
    return JSONExporter(**kwargs)


def create_metrics_api(metrics_manager, **kwargs) -> JSONMetricsAPI:
    """创建指标API的工厂函数"""
    return JSONMetricsAPI(metrics_manager, **kwargs)


# 示例使用
if __name__ == "__main__":
    from ..unified_metrics_manager import get_global_manager
    from ..metric_categories import MetricType, MetricCategory
    
    # 获取全局管理器
    manager = get_global_manager()
    
    # 注册测试指标
    manager.registry.register_custom_metric(
        "test_gauge",
        MetricType.GAUGE,
        MetricCategory.SYSTEM,
        "测试仪表"
    )
    
    # 设置一些值
    manager.set_gauge("test_gauge", 42.5, {"component": "cpu"})
    manager.set_gauge("test_gauge", 78.9, {"component": "memory"})
    
    # 导出指标
    exporter = JSONExporter(pretty_print=True)
    metrics = manager.registry.get_all_metrics()
    output = exporter.export_metrics(metrics)
    
    print("JSON指标导出示例:")
    print(output)