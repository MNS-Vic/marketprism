"""
监控仪表板配置生成器

自动生成Grafana等监控系统的仪表板配置。
"""

import json
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import logging

from ..metric_categories import MetricType, MetricCategory, MetricSubCategory, MetricDefinition
from ..metric_registry import MetricInstance

logger = logging.getLogger(__name__)


class GrafanaDashboardGenerator:
    """Grafana仪表板生成器"""
    
    def __init__(self, dashboard_title: str = "MarketPrism Metrics", 
                 refresh_interval: str = "5s"):
        self.dashboard_title = dashboard_title
        self.refresh_interval = refresh_interval
        self.panel_id_counter = 1
        self.grid_pos_y = 0
        
    def generate_dashboard(self, metrics: Dict[str, MetricInstance]) -> Dict[str, Any]:
        """生成完整的Grafana仪表板配置"""
        try:
            dashboard = {
                "dashboard": {
                    "id": None,
                    "title": self.dashboard_title,
                    "tags": ["marketprism", "monitoring", "metrics"],
                    "style": "dark",
                    "timezone": "browser",
                    "refresh": self.refresh_interval,
                    "schemaVersion": 30,
                    "version": 1,
                    "time": {
                        "from": "now-1h",
                        "to": "now"
                    },
                    "timepicker": {
                        "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"]
                    },
                    "panels": [],
                    "templating": {
                        "list": self._generate_template_variables(metrics)
                    },
                    "annotations": {
                        "list": []
                    },
                    "links": [],
                    "gnetId": None,
                    "description": f"MarketPrism监控仪表板 - 生成时间: {datetime.now(timezone.utc).isoformat()}"
                },
                "folderId": None,
                "overwrite": True
            }
            
            # 按分类组织指标
            metrics_by_category = self._group_metrics_by_category(metrics)
            
            # 为每个分类生成面板
            for category, category_metrics in metrics_by_category.items():
                self._add_category_panels(dashboard["dashboard"]["panels"], category, category_metrics)
            
            return dashboard
            
        except Exception as e:
            logger.error(f"生成Grafana仪表板失败: {e}")
            return {}
    
    def _group_metrics_by_category(self, metrics: Dict[str, MetricInstance]) -> Dict[str, Dict[str, MetricInstance]]:
        """按分类分组指标"""
        grouped = {}
        
        for metric_name, metric_instance in metrics.items():
            category = metric_instance.definition.category.value
            
            if category not in grouped:
                grouped[category] = {}
            
            grouped[category][metric_name] = metric_instance
        
        return grouped
    
    def _add_category_panels(self, panels: List[Dict], category: str, 
                           category_metrics: Dict[str, MetricInstance]) -> None:
        """为分类添加面板"""
        # 添加分类标题行
        title_panel = self._create_text_panel(
            title=f"{category.upper()} 指标",
            content=f"## {category.title()} 分类指标\n\n共 {len(category_metrics)} 个指标",
            gridPos={"h": 3, "w": 24, "x": 0, "y": self.grid_pos_y}
        )
        panels.append(title_panel)
        self.grid_pos_y += 3
        
        # 将指标按类型分组
        metrics_by_type = {}
        for metric_name, metric_instance in category_metrics.items():
            metric_type = metric_instance.definition.metric_type
            if metric_type not in metrics_by_type:
                metrics_by_type[metric_type] = {}
            metrics_by_type[metric_type][metric_name] = metric_instance
        
        # 为每种类型创建面板
        for metric_type, type_metrics in metrics_by_type.items():
            if metric_type == MetricType.COUNTER:
                self._add_counter_panels(panels, type_metrics)
            elif metric_type == MetricType.GAUGE:
                self._add_gauge_panels(panels, type_metrics)
            elif metric_type == MetricType.HISTOGRAM:
                self._add_histogram_panels(panels, type_metrics)
            elif metric_type == MetricType.SUMMARY:
                self._add_summary_panels(panels, type_metrics)
    
    def _add_counter_panels(self, panels: List[Dict], metrics: Dict[str, MetricInstance]) -> None:
        """添加计数器面板"""
        if not metrics:
            return
        
        # 创建计数器总量面板
        panel = self._create_graph_panel(
            title="计数器指标 - 总计",
            metrics=[
                {
                    "expr": f"rate({metric_instance.definition.prometheus_name}[5m])",
                    "legendFormat": f"{{{{instance}}}} - {metric_name}"
                }
                for metric_name, metric_instance in metrics.items()
            ],
            gridPos={"h": 8, "w": 12, "x": 0, "y": self.grid_pos_y},
            yAxes=[
                {"label": "每秒速率", "min": 0},
                {"label": "", "show": False}
            ]
        )
        panels.append(panel)
        
        # 创建计数器增长率面板
        panel = self._create_graph_panel(
            title="计数器指标 - 增长率",
            metrics=[
                {
                    "expr": f"increase({metric_instance.definition.prometheus_name}[1m])",
                    "legendFormat": f"{{{{instance}}}} - {metric_name}"
                }
                for metric_name, metric_instance in metrics.items()
            ],
            gridPos={"h": 8, "w": 12, "x": 12, "y": self.grid_pos_y},
            yAxes=[
                {"label": "1分钟增长", "min": 0},
                {"label": "", "show": False}
            ]
        )
        panels.append(panel)
        
        self.grid_pos_y += 8
    
    def _add_gauge_panels(self, panels: List[Dict], metrics: Dict[str, MetricInstance]) -> None:
        """添加仪表面板"""
        if not metrics:
            return
        
        # 为每个仪表指标创建单独的面板
        metrics_per_row = 3
        current_x = 0
        panel_width = 24 // metrics_per_row
        
        for i, (metric_name, metric_instance) in enumerate(metrics.items()):
            if i > 0 and i % metrics_per_row == 0:
                self.grid_pos_y += 8
                current_x = 0
            
            panel = self._create_stat_panel(
                title=metric_instance.definition.description or metric_name,
                metric=metric_instance.definition.prometheus_name,
                gridPos={"h": 8, "w": panel_width, "x": current_x, "y": self.grid_pos_y},
                unit=self._get_grafana_unit(metric_instance.definition.unit)
            )
            panels.append(panel)
            
            current_x += panel_width
        
        self.grid_pos_y += 8
    
    def _add_histogram_panels(self, panels: List[Dict], metrics: Dict[str, MetricInstance]) -> None:
        """添加直方图面板"""
        if not metrics:
            return
        
        for metric_name, metric_instance in metrics.items():
            # 分位数面板
            panel = self._create_graph_panel(
                title=f"{metric_instance.definition.description or metric_name} - 分位数",
                metrics=[
                    {
                        "expr": f"histogram_quantile(0.50, rate({metric_instance.definition.prometheus_name}_bucket[5m]))",
                        "legendFormat": "50th percentile"
                    },
                    {
                        "expr": f"histogram_quantile(0.90, rate({metric_instance.definition.prometheus_name}_bucket[5m]))",
                        "legendFormat": "90th percentile"
                    },
                    {
                        "expr": f"histogram_quantile(0.95, rate({metric_instance.definition.prometheus_name}_bucket[5m]))",
                        "legendFormat": "95th percentile"
                    },
                    {
                        "expr": f"histogram_quantile(0.99, rate({metric_instance.definition.prometheus_name}_bucket[5m]))",
                        "legendFormat": "99th percentile"
                    }
                ],
                gridPos={"h": 8, "w": 12, "x": 0, "y": self.grid_pos_y},
                yAxes=[
                    {"label": metric_instance.definition.unit or "值", "min": 0},
                    {"label": "", "show": False}
                ]
            )
            panels.append(panel)
            
            # 请求率面板
            panel = self._create_graph_panel(
                title=f"{metric_instance.definition.description or metric_name} - 请求率",
                metrics=[
                    {
                        "expr": f"rate({metric_instance.definition.prometheus_name}_count[5m])",
                        "legendFormat": "请求/秒"
                    }
                ],
                gridPos={"h": 8, "w": 12, "x": 12, "y": self.grid_pos_y},
                yAxes=[
                    {"label": "请求/秒", "min": 0},
                    {"label": "", "show": False}
                ]
            )
            panels.append(panel)
            
            self.grid_pos_y += 8
    
    def _add_summary_panels(self, panels: List[Dict], metrics: Dict[str, MetricInstance]) -> None:
        """添加摘要面板"""
        # 摘要面板类似于直方图面板
        self._add_histogram_panels(panels, metrics)
    
    def _create_graph_panel(self, title: str, metrics: List[Dict], gridPos: Dict, 
                           yAxes: List[Dict] = None) -> Dict[str, Any]:
        """创建图表面板"""
        panel = {
            "id": self.panel_id_counter,
            "title": title,
            "type": "graph",
            "gridPos": gridPos,
            "targets": [
                {
                    "expr": metric["expr"],
                    "legendFormat": metric.get("legendFormat", ""),
                    "refId": chr(65 + i),  # A, B, C, ...
                    "format": "time_series",
                    "intervalFactor": 1
                }
                for i, metric in enumerate(metrics)
            ],
            "xAxes": [
                {
                    "mode": "time",
                    "name": None,
                    "show": True,
                    "type": "linear"
                }
            ],
            "yAxes": yAxes or [
                {"label": "", "min": None, "show": True},
                {"label": "", "show": False}
            ],
            "legend": {
                "avg": False,
                "current": False,
                "max": False,
                "min": False,
                "show": True,
                "total": False,
                "values": False
            },
            "lines": True,
            "linewidth": 1,
            "fill": 1,
            "fillGradient": 0,
            "pointradius": 2,
            "points": False,
            "renderer": "flot",
            "spaceLength": 10,
            "stack": False,
            "steppedLine": False,
            "timeFrom": None,
            "timeRegions": [],
            "timeShift": None,
            "tooltip": {
                "shared": True,
                "sort": 0,
                "value_type": "individual"
            },
            "transparent": False
        }
        
        self.panel_id_counter += 1
        return panel
    
    def _create_stat_panel(self, title: str, metric: str, gridPos: Dict, 
                          unit: str = "short") -> Dict[str, Any]:
        """创建状态面板"""
        panel = {
            "id": self.panel_id_counter,
            "title": title,
            "type": "stat",
            "gridPos": gridPos,
            "targets": [
                {
                    "expr": metric,
                    "legendFormat": "",
                    "refId": "A",
                    "format": "time_series",
                    "instant": True
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "color": {
                        "mode": "palette-classic"
                    },
                    "custom": {
                        "axisLabel": "",
                        "axisPlacement": "auto",
                        "barAlignment": 0,
                        "drawStyle": "line",
                        "fillOpacity": 10,
                        "gradientMode": "none",
                        "hideFrom": {
                            "graph": False,
                            "legend": False,
                            "tooltip": False
                        },
                        "lineInterpolation": "linear",
                        "lineWidth": 1,
                        "pointSize": 5,
                        "scaleDistribution": {
                            "type": "linear"
                        },
                        "showPoints": "never",
                        "spanNulls": True
                    },
                    "mappings": [],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": 80}
                        ]
                    },
                    "unit": unit
                },
                "overrides": []
            },
            "options": {
                "reduceOptions": {
                    "values": False,
                    "calcs": ["lastNotNull"],
                    "fields": ""
                },
                "orientation": "auto",
                "textMode": "auto",
                "colorMode": "value",
                "graphMode": "area",
                "justifyMode": "auto"
            },
            "pluginVersion": "8.0.0"
        }
        
        self.panel_id_counter += 1
        return panel
    
    def _create_text_panel(self, title: str, content: str, gridPos: Dict) -> Dict[str, Any]:
        """创建文本面板"""
        panel = {
            "id": self.panel_id_counter,
            "title": title,
            "type": "text",
            "gridPos": gridPos,
            "options": {
                "mode": "markdown",
                "content": content
            }
        }
        
        self.panel_id_counter += 1
        return panel
    
    def _generate_template_variables(self, metrics: Dict[str, MetricInstance]) -> List[Dict[str, Any]]:
        """生成模板变量"""
        variables = []
        
        # 实例变量
        variables.append({
            "allValue": None,
            "current": {
                "selected": True,
                "text": "All",
                "value": "$__all"
            },
            "datasource": "${DS_PROMETHEUS}",
            "definition": "label_values(up, instance)",
            "hide": 0,
            "includeAll": True,
            "multi": True,
            "name": "instance",
            "options": [],
            "query": "label_values(up, instance)",
            "refresh": 1,
            "regex": "",
            "skipUrlSync": False,
            "sort": 1,
            "type": "query"
        })
        
        # 交易所变量（如果有相关指标）
        has_exchange_metrics = any(
            "exchange" in metric_instance.definition.labels
            for metric_instance in metrics.values()
        )
        
        if has_exchange_metrics:
            variables.append({
                "allValue": None,
                "current": {
                    "selected": True,
                    "text": "All",
                    "value": "$__all"
                },
                "datasource": "${DS_PROMETHEUS}",
                "definition": "label_values(marketprism_business_messages_processed_total, exchange)",
                "hide": 0,
                "includeAll": True,
                "multi": True,
                "name": "exchange",
                "options": [],
                "query": "label_values(marketprism_business_messages_processed_total, exchange)",
                "refresh": 1,
                "regex": "",
                "skipUrlSync": False,
                "sort": 1,
                "type": "query"
            })
        
        return variables
    
    def _get_grafana_unit(self, unit: str) -> str:
        """获取Grafana单位"""
        unit_mapping = {
            "bytes": "bytes",
            "seconds": "s",
            "milliseconds": "ms",
            "microseconds": "µs",
            "percent": "percent",
            "ratio": "percentunit",
            "count": "short",
            "": "short"
        }
        
        return unit_mapping.get(unit.lower(), "short")


class PrometheusAlertGenerator:
    """Prometheus告警规则生成器"""
    
    def __init__(self, namespace: str = "marketprism"):
        self.namespace = namespace
    
    def generate_alert_rules(self, metrics: Dict[str, MetricInstance]) -> Dict[str, Any]:
        """生成Prometheus告警规则"""
        rules = {
            "groups": [
                {
                    "name": f"{self.namespace}.rules",
                    "rules": []
                }
            ]
        }
        
        # 为不同类型的指标生成告警规则
        for metric_name, metric_instance in metrics.items():
            definition = metric_instance.definition
            
            if definition.category == MetricCategory.ERROR:
                rules["groups"][0]["rules"].append(
                    self._create_error_alert(metric_name, definition)
                )
            elif definition.category == MetricCategory.PERFORMANCE:
                rules["groups"][0]["rules"].append(
                    self._create_performance_alert(metric_name, definition)
                )
            elif definition.category == MetricCategory.RESOURCE:
                rules["groups"][0]["rules"].append(
                    self._create_resource_alert(metric_name, definition)
                )
        
        return rules
    
    def _create_error_alert(self, metric_name: str, definition: MetricDefinition) -> Dict[str, Any]:
        """创建错误告警规则"""
        return {
            "alert": f"{metric_name}_high",
            "expr": f"rate({definition.prometheus_name}[5m]) > 0.1",
            "for": "2m",
            "labels": {
                "severity": "warning",
                "category": "error"
            },
            "annotations": {
                "summary": f"{definition.description} 错误率过高",
                "description": f"指标 {metric_name} 的错误率在过去5分钟内超过0.1/秒"
            }
        }
    
    def _create_performance_alert(self, metric_name: str, definition: MetricDefinition) -> Dict[str, Any]:
        """创建性能告警规则"""
        return {
            "alert": f"{metric_name}_slow",
            "expr": f"histogram_quantile(0.95, rate({definition.prometheus_name}_bucket[5m])) > 1",
            "for": "5m",
            "labels": {
                "severity": "warning",
                "category": "performance"
            },
            "annotations": {
                "summary": f"{definition.description} 性能下降",
                "description": f"指标 {metric_name} 的95%分位数超过1秒"
            }
        }
    
    def _create_resource_alert(self, metric_name: str, definition: MetricDefinition) -> Dict[str, Any]:
        """创建资源告警规则"""
        return {
            "alert": f"{metric_name}_high",
            "expr": f"{definition.prometheus_name} > 0.8",
            "for": "10m",
            "labels": {
                "severity": "critical",
                "category": "resource"
            },
            "annotations": {
                "summary": f"{definition.description} 资源使用过高",
                "description": f"指标 {metric_name} 的值超过80%"
            }
        }


def create_grafana_dashboard(metrics: Dict[str, MetricInstance], **kwargs) -> Dict[str, Any]:
    """创建Grafana仪表板的工厂函数"""
    generator = GrafanaDashboardGenerator(**kwargs)
    return generator.generate_dashboard(metrics)


def create_alert_rules(metrics: Dict[str, MetricInstance], **kwargs) -> Dict[str, Any]:
    """创建告警规则的工厂函数"""
    generator = PrometheusAlertGenerator(**kwargs)
    return generator.generate_alert_rules(metrics)


# 示例使用
if __name__ == "__main__":
    from ..unified_metrics_manager import get_global_manager
    from ..metric_categories import MetricType, MetricCategory
    
    # 获取全局管理器
    manager = get_global_manager()
    
    # 注册一些测试指标
    manager.registry.register_custom_metric(
        "api_requests",
        MetricType.COUNTER,
        MetricCategory.API,
        "API请求总数"
    )
    
    manager.registry.register_custom_metric(
        "response_time",
        MetricType.HISTOGRAM,
        MetricCategory.PERFORMANCE,
        "响应时间分布"
    )
    
    # 生成仪表板
    generator = GrafanaDashboardGenerator()
    metrics = manager.registry.get_all_metrics()
    dashboard = generator.generate_dashboard(metrics)
    
    print("Grafana仪表板配置:")
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))