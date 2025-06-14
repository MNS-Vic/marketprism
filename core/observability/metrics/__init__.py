"""
统一监控模块

提供统一的监控指标管理功能：
- 指标分类和定义
- 指标注册表
- 统一指标管理器
- 标准化命名规范
"""

from datetime import datetime, timezone
from .metric_categories import (
    MetricType, MetricCategory, MetricSubCategory, MetricSeverity,
    MetricDefinition, StandardMetrics, MetricNamingStandards
)
from .metric_registry import (
    MetricRegistry, MetricInstance, MetricValue, HistogramValue, SummaryValue,
    get_global_registry, reset_global_registry
)
from .unified_metrics_manager import (
    UnifiedMetricsManager, MetricEvent, AlertRule, MetricCollector,
    SystemMetricCollector, get_global_manager, reset_global_manager
)
from .naming_standards import (
    MetricNameGenerator, MetricNameValidator, NamingConvention,
    generate_metric_name, validate_metric_name, validate_label_name,
    COMMON_METRIC_TEMPLATES
)

__all__ = [
    # 指标分类和定义
    'MetricType',
    'MetricCategory',
    'MetricSubCategory',
    'MetricSeverity',
    'MetricDefinition',
    'StandardMetrics',
    'MetricNamingStandards',
    
    # 指标注册表
    'MetricRegistry',
    'MetricInstance',
    'MetricValue',
    'HistogramValue',
    'SummaryValue',
    'get_global_registry',
    'reset_global_registry',
    
    # 统一指标管理器
    'UnifiedMetricsManager',
    'MetricEvent',
    'AlertRule',
    'MetricCollector',
    'SystemMetricCollector',
    'get_global_manager',
    'reset_global_manager',
    
    # 命名标准
    'MetricNameGenerator',
    'MetricNameValidator',
    'NamingConvention',
    'generate_metric_name',
    'validate_metric_name',
    'validate_label_name',
    'COMMON_METRIC_TEMPLATES'
]