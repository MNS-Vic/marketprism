"""
指标注册表模块

管理所有指标的注册、查找和生命周期管理。
"""

from datetime import datetime, timezone
import threading
from typing import Dict, List, Optional, Set, Any, Union, Callable, Type
from collections import defaultdict
import time
import logging
from dataclasses import dataclass, field

from .metric_categories import (
    MetricDefinition, MetricType, MetricCategory, MetricSubCategory,
    MetricSeverity, StandardMetrics
)

logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """指标值封装"""
    value: Union[int, float]
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class HistogramBucket:
    """直方图桶"""
    upper_bound: float
    count: int = 0


@dataclass
class HistogramValue(MetricValue):
    """直方图值"""
    buckets: List[HistogramBucket] = field(default_factory=list)
    sum: float = 0.0
    count: int = 0
    
    def add_observation(self, value: float):
        """添加观察值"""
        self.sum += value
        self.count += 1
        
        for bucket in self.buckets:
            if value <= bucket.upper_bound:
                bucket.count += 1


@dataclass
class SummaryValue(MetricValue):
    """摘要值"""
    sum: float = 0.0
    count: int = 0
    quantiles: Dict[float, float] = field(default_factory=dict)
    
    def add_observation(self, value: float):
        """添加观察值"""
        self.sum += value
        self.count += 1


class MetricInstance:
    """指标实例"""
    
    def __init__(self, definition: MetricDefinition):
        self.definition = definition
        self.values: Dict[str, MetricValue] = {}
        self.created_at = time.time()
        self.last_updated = time.time()
        self._lock = threading.RLock()
        
    def _get_label_key(self, labels: Dict[str, str]) -> str:
        """生成标签键"""
        if not labels:
            return ""
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
    
    def set_value(self, value: Union[int, float], labels: Dict[str, str] = None) -> None:
        """设置指标值（适用于Gauge）"""
        if self.definition.metric_type != MetricType.GAUGE:
            raise ValueError(f"set_value只能用于GAUGE类型指标")
        
        labels = labels or {}
        label_key = self._get_label_key(labels)
        
        with self._lock:
            self.values[label_key] = MetricValue(value=value, labels=labels)
            self.last_updated = time.time()
    
    def increment(self, amount: Union[int, float] = 1, labels: Dict[str, str] = None) -> None:
        """增加计数器值"""
        if self.definition.metric_type != MetricType.COUNTER:
            raise ValueError(f"increment只能用于COUNTER类型指标")
        
        labels = labels or {}
        label_key = self._get_label_key(labels)
        
        with self._lock:
            if label_key in self.values:
                self.values[label_key].value += amount
            else:
                self.values[label_key] = MetricValue(value=amount, labels=labels)
            self.last_updated = time.time()
    
    def observe_histogram(self, value: float, labels: Dict[str, str] = None, 
                         buckets: List[float] = None) -> None:
        """观察直方图值"""
        if self.definition.metric_type != MetricType.HISTOGRAM:
            raise ValueError(f"observe_histogram只能用于HISTOGRAM类型指标")
        
        labels = labels or {}
        label_key = self._get_label_key(labels)
        buckets = buckets or [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')]
        
        with self._lock:
            if label_key not in self.values:
                histogram_buckets = [HistogramBucket(upper_bound=b) for b in buckets]
                self.values[label_key] = HistogramValue(
                    value=0, labels=labels, buckets=histogram_buckets
                )
            
            hist_value = self.values[label_key]
            hist_value.add_observation(value)
            self.last_updated = time.time()
    
    def observe_summary(self, value: float, labels: Dict[str, str] = None) -> None:
        """观察摘要值"""
        if self.definition.metric_type != MetricType.SUMMARY:
            raise ValueError(f"observe_summary只能用于SUMMARY类型指标")
        
        labels = labels or {}
        label_key = self._get_label_key(labels)
        
        with self._lock:
            if label_key not in self.values:
                self.values[label_key] = SummaryValue(value=0, labels=labels)
            
            summary_value = self.values[label_key]
            summary_value.add_observation(value)
            self.last_updated = time.time()
    
    def get_values(self) -> Dict[str, MetricValue]:
        """获取所有值"""
        with self._lock:
            return dict(self.values)
    
    def get_value(self, labels: Dict[str, str] = None) -> Optional[MetricValue]:
        """获取特定标签的值"""
        label_key = self._get_label_key(labels or {})
        with self._lock:
            return self.values.get(label_key)
    
    def reset(self) -> None:
        """重置指标（仅适用于计数器）"""
        if self.definition.metric_type not in [MetricType.COUNTER, MetricType.HISTOGRAM, MetricType.SUMMARY]:
            logger.warning(f"重置指标 {self.definition.name} 可能不安全")
        
        with self._lock:
            self.values.clear()
            self.last_updated = time.time()


class MetricRegistry:
    """指标注册表"""
    
    def __init__(self):
        self.metrics: Dict[str, MetricInstance] = {}
        self.definitions: Dict[str, MetricDefinition] = {}
        self.category_index: Dict[MetricCategory, Set[str]] = defaultdict(set)
        self.type_index: Dict[MetricType, Set[str]] = defaultdict(set)
        self.severity_index: Dict[MetricSeverity, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self.created_at = time.time()
        self.stats = {
            "registrations": 0,
            "deregistrations": 0,
            "value_updates": 0,
            "last_update": None
        }
        
        # 自动注册标准指标
        self._register_standard_metrics()
    
    def _register_standard_metrics(self) -> None:
        """注册标准指标"""
        for metric_def in StandardMetrics.get_all_metrics():
            try:
                self.register_metric(metric_def)
                logger.debug(f"注册标准指标: {metric_def.name}")
            except Exception as e:
                logger.error(f"注册标准指标失败 {metric_def.name}: {e}")
    
    def register_metric(self, definition: MetricDefinition,
                       force: bool = False) -> MetricInstance:
        """注册指标"""
        with self._lock:
            if definition.name in self.metrics and not force:
                # 降低重复注册的日志级别以减少噪声（WARNING → INFO）
                logger.info(f"指标 {definition.name} 已存在")
                return self.metrics[definition.name]

            # 创建指标实例
            instance = MetricInstance(definition)

            # 存储
            self.metrics[definition.name] = instance
            self.definitions[definition.name] = definition

            # 更新索引
            self.category_index[definition.category].add(definition.name)
            self.type_index[definition.metric_type].add(definition.name)
            self.severity_index[definition.severity].add(definition.name)
            
            # 更新统计
            self.stats["registrations"] += 1
            self.stats["last_update"] = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"注册指标: {definition.name} ({definition.metric_type.name})")
            return instance
    
    def register_custom_metric(self, name: str, metric_type: MetricType,
                             category: MetricCategory, description: str = "",
                             labels: List[str] = None, unit: str = "",
                             subcategory: Optional[MetricSubCategory] = None,
                             severity: MetricSeverity = MetricSeverity.INFO) -> MetricInstance:
        """注册自定义指标"""
        definition = MetricDefinition(
            name=name,
            metric_type=metric_type,
            category=category,
            subcategory=subcategory,
            description=description,
            unit=unit,
            labels=labels or [],
            severity=severity
        )
        return self.register_metric(definition)
    
    def get_metric(self, name: str) -> Optional[MetricInstance]:
        """获取指标实例"""
        with self._lock:
            return self.metrics.get(name)
    
    def get_metric_definition(self, name: str) -> Optional[MetricDefinition]:
        """获取指标定义"""
        with self._lock:
            return self.definitions.get(name)
    
    def deregister_metric(self, name: str) -> bool:
        """注销指标"""
        with self._lock:
            if name not in self.metrics:
                return False
            
            definition = self.definitions[name]
            
            # 从索引中移除
            self.category_index[definition.category].discard(name)
            self.type_index[definition.metric_type].discard(name)
            self.severity_index[definition.severity].discard(name)
            
            # 移除实例和定义
            del self.metrics[name]
            del self.definitions[name]
            
            # 更新统计
            self.stats["deregistrations"] += 1
            self.stats["last_update"] = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"注销指标: {name}")
            return True
    
    def list_metrics(self, category: Optional[MetricCategory] = None,
                    metric_type: Optional[MetricType] = None,
                    severity: Optional[MetricSeverity] = None) -> List[str]:
        """列出指标名称"""
        with self._lock:
            metric_names = set(self.metrics.keys())
            
            if category:
                metric_names &= self.category_index[category]
            
            if metric_type:
                metric_names &= self.type_index[metric_type]
            
            if severity:
                metric_names &= self.severity_index[severity]
            
            return sorted(metric_names)
    
    def get_metrics_by_category(self, category: MetricCategory) -> Dict[str, MetricInstance]:
        """按分类获取指标"""
        metric_names = self.list_metrics(category=category)
        with self._lock:
            return {name: self.metrics[name] for name in metric_names}
    
    def get_metrics_by_type(self, metric_type: MetricType) -> Dict[str, MetricInstance]:
        """按类型获取指标"""
        metric_names = self.list_metrics(metric_type=metric_type)
        with self._lock:
            return {name: self.metrics[name] for name in metric_names}
    
    def get_all_metrics(self) -> Dict[str, MetricInstance]:
        """获取所有指标"""
        with self._lock:
            return dict(self.metrics)
    
    def get_all_definitions(self) -> Dict[str, MetricDefinition]:
        """获取所有指标定义"""
        with self._lock:
            return dict(self.definitions)
    
    def clear(self) -> None:
        """清空注册表"""
        with self._lock:
            count = len(self.metrics)
            
            self.metrics.clear()
            self.definitions.clear()
            self.category_index.clear()
            self.type_index.clear()
            self.severity_index.clear()
            
            self.stats["deregistrations"] += count
            self.stats["last_update"] = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"清空指标注册表，移除 {count} 个指标")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        with self._lock:
            return {
                "total_metrics": len(self.metrics),
                "categories": len(self.category_index),
                "types": len(self.type_index),
                "severities": len(self.severity_index),
                "created_at": self.created_at,
                "uptime_seconds": time.time() - self.created_at,
                **self.stats
            }
    
    def validate_registry(self) -> Dict[str, Any]:
        """验证注册表一致性"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "statistics": {}
        }
        
        with self._lock:
            # 检查索引一致性
            for name in self.metrics:
                if name not in self.definitions:
                    validation_result["errors"].append(f"指标 {name} 缺少定义")
                    validation_result["valid"] = False
            
            # 检查指标名称重复
            names = list(self.metrics.keys())
            if len(names) != len(set(names)):
                validation_result["errors"].append("存在重复的指标名称")
                validation_result["valid"] = False
            
            # 统计信息
            validation_result["statistics"] = {
                "total_metrics": len(self.metrics),
                "by_category": {cat.value: len(metrics) for cat, metrics in self.category_index.items()},
                "by_type": {typ.name: len(metrics) for typ, metrics in self.type_index.items()},
                "by_severity": {sev.value: len(metrics) for sev, metrics in self.severity_index.items()}
            }
        
        return validation_result


# 全局注册表实例
_global_registry = None
_global_registry_lock = threading.Lock()


def get_global_registry() -> MetricRegistry:
    """获取全局指标注册表"""
    global _global_registry
    
    if _global_registry is None:
        with _global_registry_lock:
            if _global_registry is None:
                _global_registry = MetricRegistry()
                logger.info("初始化全局指标注册表")
    
    return _global_registry


def reset_global_registry() -> None:
    """重置全局指标注册表（主要用于测试）"""
    global _global_registry
    
    with _global_registry_lock:
        if _global_registry:
            _global_registry.clear()
        _global_registry = None
        logger.info("重置全局指标注册表")