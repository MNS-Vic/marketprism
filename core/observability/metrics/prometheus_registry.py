"""
全局Prometheus注册表管理器

避免指标重复注册的问题
"""

import logging
from typing import Dict, Any, Optional
import threading

try:
    from prometheus_client import CollectorRegistry, REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CollectorRegistry = None
    REGISTRY = None

logger = logging.getLogger(__name__)


class GlobalPrometheusRegistry:
    """全局Prometheus注册表管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.registry = CollectorRegistry() if PROMETHEUS_AVAILABLE else None
        self.registered_metrics: Dict[str, Any] = {}
        self.lock = threading.RLock()
        
        logger.info("全局Prometheus注册表初始化完成")
    
    def get_or_create_metric(self, metric_class, name: str, description: str, 
                           labels: list = None, **kwargs):
        """获取或创建指标，避免重复注册"""
        if not PROMETHEUS_AVAILABLE:
            return None
        
        with self.lock:
            if name in self.registered_metrics:
                logger.debug(f"返回已存在的指标: {name}")
                return self.registered_metrics[name]
            
            try:
                # 创建新指标
                if labels:
                    metric = metric_class(
                        name, description, labels, 
                        registry=self.registry, **kwargs
                    )
                else:
                    metric = metric_class(
                        name, description, 
                        registry=self.registry, **kwargs
                    )
                
                self.registered_metrics[name] = metric
                logger.info(f"注册新指标: {name}")
                return metric
                
            except Exception as e:
                logger.error(f"创建指标失败 {name}: {e}")
                return None
    
    def clear_registry(self):
        """清空注册表"""
        with self.lock:
            if self.registry:
                self.registry = CollectorRegistry()
            self.registered_metrics.clear()
            logger.info("清空Prometheus注册表")
    
    def get_metrics_count(self) -> int:
        """获取已注册指标数量"""
        return len(self.registered_metrics)
    
    def list_metrics(self) -> list:
        """列出所有已注册的指标名称"""
        return list(self.registered_metrics.keys())


# 全局实例
global_registry = GlobalPrometheusRegistry()


def get_global_registry() -> GlobalPrometheusRegistry:
    """获取全局注册表实例"""
    return global_registry


def create_counter(name: str, description: str, labels: list = None):
    """创建Counter指标"""
    if not PROMETHEUS_AVAILABLE:
        return None
    
    from prometheus_client import Counter
    return global_registry.get_or_create_metric(
        Counter, name, description, labels
    )


def create_gauge(name: str, description: str, labels: list = None):
    """创建Gauge指标"""
    if not PROMETHEUS_AVAILABLE:
        return None
    
    from prometheus_client import Gauge
    return global_registry.get_or_create_metric(
        Gauge, name, description, labels
    )


def create_histogram(name: str, description: str, labels: list = None, 
                    buckets: list = None):
    """创建Histogram指标"""
    if not PROMETHEUS_AVAILABLE:
        return None
    
    from prometheus_client import Histogram
    kwargs = {}
    if buckets:
        kwargs['buckets'] = buckets
    
    return global_registry.get_or_create_metric(
        Histogram, name, description, labels, **kwargs
    )


def create_summary(name: str, description: str, labels: list = None):
    """创建Summary指标"""
    if not PROMETHEUS_AVAILABLE:
        return None
    
    from prometheus_client import Summary
    return global_registry.get_or_create_metric(
        Summary, name, description, labels
    )
