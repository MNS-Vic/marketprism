#!/usr/bin/env python3
"""
MarketPrism 配置优化引擎
配置管理系统 2.0 - Week 5 Day 5

智能配置优化引擎，提供自动性能调优、配置建议生成、
瓶颈识别和优化策略推荐功能。

Author: MarketPrism团队
Created: 2025-01-29
Version: 1.0.0
"""

import time
import threading
import statistics
import json
import math
from typing import Dict, Any, List, Optional, Callable, Union, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict, deque
import uuid
import psutil
import numpy as np
from scipy import stats as scipy_stats
import logging

# 导入相关组件
from .config_performance_monitor import (
    ConfigPerformanceMonitor, 
    PerformanceMetric,
    PerformanceAlert,
    MetricType,
    AlertSeverity,
    get_performance_monitor
)

from .config_cache import (
    MultiLevelConfigCache,
    CachePriority,
    get_config_cache
)


class OptimizationType(Enum):
    """优化类型"""
    PERFORMANCE = auto()      # 性能优化
    MEMORY = auto()           # 内存优化
    THROUGHPUT = auto()       # 吞吐量优化
    LATENCY = auto()          # 延迟优化
    CACHE = auto()            # 缓存优化
    RESOURCE = auto()         # 资源优化
    CONSISTENCY = auto()      # 一致性优化


class OptimizationSeverity(Enum):
    """优化严重程度"""
    CRITICAL = 1              # 严重
    HIGH = 2                 # 高
    MEDIUM = 3               # 中
    LOW = 4                  # 低
    INFO = 5                 # 信息


class OptimizationAction(Enum):
    """优化动作"""
    INCREASE_CACHE_SIZE = auto()      # 增加缓存大小
    DECREASE_CACHE_SIZE = auto()      # 减少缓存大小
    ADJUST_TTL = auto()               # 调整TTL
    CHANGE_STRATEGY = auto()          # 改变策略
    ADD_PRELOAD = auto()              # 添加预加载
    REMOVE_PRELOAD = auto()           # 移除预加载
    OPTIMIZE_SERIALIZATION = auto()    # 优化序列化
    REDUCE_POLLING = auto()           # 减少轮询
    INCREASE_POLLING = auto()         # 增加轮询
    ENABLE_COMPRESSION = auto()       # 启用压缩
    DISABLE_COMPRESSION = auto()      # 禁用压缩


@dataclass
class OptimizationRecommendation:
    """优化建议"""
    recommendation_id: str
    optimization_type: OptimizationType
    severity: OptimizationSeverity
    action: OptimizationAction
    component: str
    description: str
    impact_estimate: float  # 预期影响 (0-1)
    confidence: float       # 置信度 (0-1)
    parameters: Dict[str, Any] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    applied: bool = False
    applied_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['optimization_type'] = self.optimization_type.name
        data['severity'] = self.severity.name
        data['action'] = self.action.name
        data['created_at'] = self.created_at.isoformat()
        if self.applied_at:
            data['applied_at'] = self.applied_at.isoformat()
        return data


@dataclass
class PerformanceBaseline:
    """性能基线"""
    component: str
    operation: str
    baseline_latency_ms: float
    baseline_throughput: float
    baseline_error_rate: float
    baseline_memory_mb: float
    created_at: datetime
    sample_count: int
    confidence_interval: Tuple[float, float]  # 95%置信区间
    
    def is_degraded(self, current_latency: float, threshold: float = 0.2) -> bool:
        """检查性能是否下降"""
        return current_latency > self.baseline_latency_ms * (1 + threshold)
        
    def is_improved(self, current_latency: float, threshold: float = 0.1) -> bool:
        """检查性能是否改善"""
        return current_latency < self.baseline_latency_ms * (1 - threshold)


@dataclass
class OptimizationRule:
    """优化规则"""
    rule_id: str
    name: str
    description: str
    condition: Callable[[Dict[str, Any]], bool]  # 触发条件
    action_generator: Callable[[Dict[str, Any]], OptimizationRecommendation]  # 动作生成器
    priority: int = 1  # 优先级，数字越小优先级越高
    enabled: bool = True


class ConfigOptimizer:
    """配置优化引擎
    
    智能分析系统性能，识别瓶颈，生成优化建议，
    并可自动应用某些安全的优化措施。
    """
    
    def __init__(self,
                 optimization_interval: float = 300.0,  # 5分钟
                 auto_apply_safe_optimizations: bool = True,
                 max_recommendations: int = 100):
        """初始化配置优化引擎
        
        Args:
            optimization_interval: 优化分析间隔（秒）
            auto_apply_safe_optimizations: 是否自动应用安全的优化
            max_recommendations: 最大建议数量
        """
        self.optimization_interval = optimization_interval
        self.auto_apply_safe_optimizations = auto_apply_safe_optimizations
        self.max_recommendations = max_recommendations
        
        # 组件引用
        self._monitor = get_performance_monitor()
        self._cache = get_config_cache()
        
        # 数据存储
        self.recommendations: deque = deque(maxlen=max_recommendations)
        self.baselines: Dict[str, PerformanceBaseline] = {}
        self.optimization_rules: List[OptimizationRule] = []
        
        # 状态控制
        self._optimizing = False
        self._optimization_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            "total_recommendations": 0,
            "applied_recommendations": 0,
            "successful_optimizations": 0,
            "failed_optimizations": 0,
            "last_optimization": None
        }
        
        # 初始化规则
        self._initialize_optimization_rules()
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def start_optimization(self):
        """启动优化引擎"""
        if self._optimizing:
            return
            
        self._optimizing = True
        self._optimization_thread = threading.Thread(
            target=self._optimization_loop,
            daemon=True,
            name="ConfigOptimizer"
        )
        self._optimization_thread.start()
        self.logger.info("配置优化引擎已启动")
        
    def stop_optimization(self):
        """停止优化引擎"""
        self._optimizing = False
        if self._optimization_thread:
            self._optimization_thread.join(timeout=5.0)
        self.logger.info("配置优化引擎已停止")
        
    def analyze_performance(self) -> List[OptimizationRecommendation]:
        """分析性能并生成优化建议
        
        Returns:
            优化建议列表
        """
        with self._lock:
            recommendations = []
            
            try:
                # 获取性能数据
                performance_data = self._collect_performance_data()
                
                # 更新性能基线
                self._update_baselines(performance_data)
                
                # 应用优化规则
                for rule in self.optimization_rules:
                    if not rule.enabled:
                        continue
                        
                    try:
                        if rule.condition(performance_data):
                            recommendation = rule.action_generator(performance_data)
                            recommendations.append(recommendation)
                    except Exception as e:
                        self.logger.error(f"优化规则 {rule.name} 执行失败: {e}")
                        
                # 按优先级排序
                recommendations.sort(key=lambda r: (r.severity.value, -r.confidence))
                
                # 存储建议
                for rec in recommendations:
                    self.recommendations.append(rec)
                    self.stats["total_recommendations"] += 1
                    
                # 自动应用安全的优化
                if self.auto_apply_safe_optimizations:
                    self._auto_apply_recommendations(recommendations)
                    
                return recommendations
                
            except Exception as e:
                self.logger.error(f"性能分析失败: {e}")
                return []
                
    def apply_recommendation(self, recommendation_id: str) -> bool:
        """应用优化建议
        
        Args:
            recommendation_id: 建议ID
            
        Returns:
            是否成功应用
        """
        with self._lock:
            # 查找建议
            recommendation = None
            for rec in self.recommendations:
                if rec.recommendation_id == recommendation_id:
                    recommendation = rec
                    break
                    
            if not recommendation:
                self.logger.error(f"未找到建议: {recommendation_id}")
                return False
                
            if recommendation.applied:
                self.logger.warning(f"建议已经应用: {recommendation_id}")
                return True
                
            try:
                # 应用优化
                success = self._apply_optimization(recommendation)
                
                # 更新状态
                recommendation.applied = True
                recommendation.applied_at = datetime.now()
                
                if success:
                    self.stats["applied_recommendations"] += 1
                    self.stats["successful_optimizations"] += 1
                    self.logger.info(f"成功应用优化建议: {recommendation.description}")
                else:
                    self.stats["failed_optimizations"] += 1
                    self.logger.error(f"应用优化建议失败: {recommendation.description}")
                    
                return success
                
            except Exception as e:
                self.logger.error(f"应用优化建议异常: {e}")
                self.stats["failed_optimizations"] += 1
                return False
                
    def get_recommendations(self,
                          severity: Optional[OptimizationSeverity] = None,
                          optimization_type: Optional[OptimizationType] = None,
                          applied: Optional[bool] = None,
                          limit: Optional[int] = None) -> List[OptimizationRecommendation]:
        """获取优化建议
        
        Args:
            severity: 严重程度过滤
            optimization_type: 优化类型过滤
            applied: 应用状态过滤
            limit: 数量限制
            
        Returns:
            建议列表
        """
        with self._lock:
            filtered_recommendations = []
            
            for rec in reversed(self.recommendations):
                # 应用过滤条件
                if severity and rec.severity != severity:
                    continue
                if optimization_type and rec.optimization_type != optimization_type:
                    continue
                if applied is not None and rec.applied != applied:
                    continue
                    
                filtered_recommendations.append(rec)
                
                # 应用数量限制
                if limit and len(filtered_recommendations) >= limit:
                    break
                    
            return filtered_recommendations
            
    def get_optimization_summary(self) -> Dict[str, Any]:
        """获取优化摘要"""
        with self._lock:
            # 计算各类统计
            total_recommendations = len(self.recommendations)
            applied_count = sum(1 for r in self.recommendations if r.applied)
            pending_count = total_recommendations - applied_count
            
            # 按类型分组
            by_type = defaultdict(int)
            by_severity = defaultdict(int)
            
            for rec in self.recommendations:
                by_type[rec.optimization_type.name] += 1
                by_severity[rec.severity.name] += 1
                
            # 最近的建议
            recent_recommendations = [
                rec.to_dict() for rec in list(self.recommendations)[-5:]
            ]
            
            # 性能基线信息
            baseline_count = len(self.baselines)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "optimization_status": "active" if self._optimizing else "inactive",
                "summary": {
                    "total_recommendations": total_recommendations,
                    "applied_recommendations": applied_count,
                    "pending_recommendations": pending_count,
                    "success_rate": (self.stats["successful_optimizations"] / 
                                   max(self.stats["applied_recommendations"], 1)) * 100,
                    "baseline_count": baseline_count
                },
                "stats": self.stats.copy(),
                "distribution": {
                    "by_type": dict(by_type),
                    "by_severity": dict(by_severity)
                },
                "recent_recommendations": recent_recommendations,
                "rules": {
                    "total_rules": len(self.optimization_rules),
                    "enabled_rules": sum(1 for r in self.optimization_rules if r.enabled)
                }
            }
            
    def add_optimization_rule(self, rule: OptimizationRule):
        """添加优化规则"""
        with self._lock:
            self.optimization_rules.append(rule)
            # 按优先级排序
            self.optimization_rules.sort(key=lambda r: r.priority)
            
    def remove_optimization_rule(self, rule_id: str) -> bool:
        """移除优化规则"""
        with self._lock:
            for i, rule in enumerate(self.optimization_rules):
                if rule.rule_id == rule_id:
                    del self.optimization_rules[i]
                    return True
            return False
            
    def enable_rule(self, rule_id: str) -> bool:
        """启用规则"""
        with self._lock:
            for rule in self.optimization_rules:
                if rule.rule_id == rule_id:
                    rule.enabled = True
                    return True
            return False
            
    def disable_rule(self, rule_id: str) -> bool:
        """禁用规则"""
        with self._lock:
            for rule in self.optimization_rules:
                if rule.rule_id == rule_id:
                    rule.enabled = False
                    return True
            return False
            
    def export_recommendations(self, format_type: str = "json") -> str:
        """导出优化建议
        
        Args:
            format_type: 导出格式 (json, csv)
            
        Returns:
            导出的数据字符串
        """
        if format_type.lower() == "json":
            return self._export_recommendations_json()
        elif format_type.lower() == "csv":
            return self._export_recommendations_csv()
        else:
            raise ValueError(f"不支持的格式: {format_type}")
            
    def _optimization_loop(self):
        """优化循环"""
        while self._optimizing:
            try:
                # 执行性能分析
                recommendations = self.analyze_performance()
                
                if recommendations:
                    self.logger.info(f"生成 {len(recommendations)} 个优化建议")
                    
                self.stats["last_optimization"] = datetime.now().isoformat()
                
                # 等待下一次分析
                time.sleep(self.optimization_interval)
                
            except Exception as e:
                self.logger.error(f"优化循环异常: {e}")
                time.sleep(60)  # 错误后等待1分钟
                
    def _collect_performance_data(self) -> Dict[str, Any]:
        """收集性能数据"""
        # 从监控器获取最近的指标
        recent_metrics = self._monitor.get_metrics(
            since=datetime.now() - timedelta(minutes=15),
            limit=1000
        )
        
        # 从缓存获取统计信息
        cache_stats = self._cache.get_global_stats()
        
        # 获取系统资源
        process = psutil.Process()
        memory_info = process.memory_info()
        
        # 按组件和操作分组指标
        metrics_by_component = defaultdict(lambda: defaultdict(list))
        for metric in recent_metrics:
            metrics_by_component[metric.component][metric.operation].append(metric)
            
        # 计算聚合统计
        component_stats = {}
        for component, operations in metrics_by_component.items():
            component_stats[component] = {}
            for operation, metrics in operations.items():
                latency_values = [m.value for m in metrics if m.metric_type == MetricType.LATENCY]
                
                if latency_values:
                    component_stats[component][operation] = {
                        "avg_latency": statistics.mean(latency_values),
                        "p95_latency": np.percentile(latency_values, 95),
                        "p99_latency": np.percentile(latency_values, 99),
                        "count": len(latency_values),
                        "std_dev": statistics.stdev(latency_values) if len(latency_values) > 1 else 0
                    }
                    
        return {
            "timestamp": datetime.now(),
            "recent_metrics": recent_metrics,
            "component_stats": component_stats,
            "cache_stats": cache_stats,
            "system_stats": {
                "memory_usage_mb": memory_info.rss / 1024 / 1024,
                "memory_percent": process.memory_percent(),
                "cpu_percent": process.cpu_percent(),
                "threads_count": process.num_threads()
            }
        }
        
    def _update_baselines(self, performance_data: Dict[str, Any]):
        """更新性能基线"""
        component_stats = performance_data.get("component_stats", {})
        
        for component, operations in component_stats.items():
            for operation, stats in operations.items():
                baseline_key = f"{component}.{operation}"
                
                if baseline_key not in self.baselines:
                    # 创建新基线
                    self.baselines[baseline_key] = PerformanceBaseline(
                        component=component,
                        operation=operation,
                        baseline_latency_ms=stats["avg_latency"],
                        baseline_throughput=stats["count"] / 900,  # 15分钟的操作数
                        baseline_error_rate=0.0,  # TODO: 计算错误率
                        baseline_memory_mb=performance_data["system_stats"]["memory_usage_mb"],
                        created_at=datetime.now(),
                        sample_count=stats["count"],
                        confidence_interval=(stats["avg_latency"] - stats["std_dev"], 
                                           stats["avg_latency"] + stats["std_dev"])
                    )
                else:
                    # 更新现有基线 (指数移动平均)
                    baseline = self.baselines[baseline_key]
                    alpha = 0.1  # 平滑系数
                    baseline.baseline_latency_ms = (
                        alpha * stats["avg_latency"] + 
                        (1 - alpha) * baseline.baseline_latency_ms
                    )
                    
    def _auto_apply_recommendations(self, recommendations: List[OptimizationRecommendation]):
        """自动应用安全的优化建议"""
        safe_actions = {
            OptimizationAction.ADJUST_TTL,
            OptimizationAction.ADD_PRELOAD,
            OptimizationAction.ENABLE_COMPRESSION
        }
        
        for rec in recommendations:
            if (rec.action in safe_actions and 
                rec.confidence > 0.8 and 
                rec.severity in [OptimizationSeverity.HIGH, OptimizationSeverity.CRITICAL]):
                
                try:
                    self.apply_recommendation(rec.recommendation_id)
                except Exception as e:
                    self.logger.error(f"自动应用优化失败: {e}")
                    
    def _apply_optimization(self, recommendation: OptimizationRecommendation) -> bool:
        """应用具体的优化"""
        try:
            action = recommendation.action
            params = recommendation.parameters
            
            if action == OptimizationAction.INCREASE_CACHE_SIZE:
                # TODO: 实现增加缓存大小
                return True
                
            elif action == OptimizationAction.ADJUST_TTL:
                # TODO: 实现调整TTL
                return True
                
            elif action == OptimizationAction.ADD_PRELOAD:
                if "keys" in params:
                    self._cache.preload(params["keys"])
                return True
                
            elif action == OptimizationAction.ENABLE_COMPRESSION:
                # TODO: 实现启用压缩
                return True
                
            else:
                self.logger.warning(f"未实现的优化动作: {action}")
                return False
                
        except Exception as e:
            self.logger.error(f"应用优化失败: {e}")
            return False
            
    def _initialize_optimization_rules(self):
        """初始化优化规则"""
        
        # 规则1: 高延迟优化
        def high_latency_condition(data: Dict[str, Any]) -> bool:
            component_stats = data.get("component_stats", {})
            for component, operations in component_stats.items():
                for operation, stats in operations.items():
                    if stats["avg_latency"] > 100:  # 100ms
                        return True
            return False
            
        def high_latency_action(data: Dict[str, Any]) -> OptimizationRecommendation:
            return OptimizationRecommendation(
                recommendation_id=str(uuid.uuid4()),
                optimization_type=OptimizationType.LATENCY,
                severity=OptimizationSeverity.HIGH,
                action=OptimizationAction.INCREASE_CACHE_SIZE,
                component="cache",
                description="检测到高延迟，建议增加缓存大小以提高命中率",
                impact_estimate=0.7,
                confidence=0.8,
                evidence=["平均延迟超过100ms阈值"]
            )
            
        self.add_optimization_rule(OptimizationRule(
            rule_id="high_latency_rule",
            name="高延迟优化规则",
            description="当检测到高延迟时触发优化",
            condition=high_latency_condition,
            action_generator=high_latency_action,
            priority=1
        ))
        
        # 规则2: 低缓存命中率优化
        def low_cache_hit_condition(data: Dict[str, Any]) -> bool:
            cache_stats = data.get("cache_stats", {})
            return cache_stats.get("global_hit_rate", 1.0) < 0.7
            
        def low_cache_hit_action(data: Dict[str, Any]) -> OptimizationRecommendation:
            return OptimizationRecommendation(
                recommendation_id=str(uuid.uuid4()),
                optimization_type=OptimizationType.CACHE,
                severity=OptimizationSeverity.MEDIUM,
                action=OptimizationAction.ADD_PRELOAD,
                component="cache",
                description="缓存命中率低，建议添加预加载热点数据",
                impact_estimate=0.6,
                confidence=0.9,
                evidence=[f"缓存命中率: {data.get('cache_stats', {}).get('global_hit_rate', 0):.2%}"]
            )
            
        self.add_optimization_rule(OptimizationRule(
            rule_id="low_cache_hit_rule",
            name="低缓存命中率优化规则",
            description="当缓存命中率低时触发优化",
            condition=low_cache_hit_condition,
            action_generator=low_cache_hit_action,
            priority=2
        ))
        
        # 规则3: 高内存使用优化
        def high_memory_condition(data: Dict[str, Any]) -> bool:
            system_stats = data.get("system_stats", {})
            return system_stats.get("memory_percent", 0) > 80
            
        def high_memory_action(data: Dict[str, Any]) -> OptimizationRecommendation:
            return OptimizationRecommendation(
                recommendation_id=str(uuid.uuid4()),
                optimization_type=OptimizationType.MEMORY,
                severity=OptimizationSeverity.CRITICAL,
                action=OptimizationAction.ENABLE_COMPRESSION,
                component="cache",
                description="内存使用率过高，建议启用压缩以减少内存占用",
                impact_estimate=0.8,
                confidence=0.9,
                evidence=[f"内存使用率: {data.get('system_stats', {}).get('memory_percent', 0):.1f}%"]
            )
            
        self.add_optimization_rule(OptimizationRule(
            rule_id="high_memory_rule",
            name="高内存使用优化规则",
            description="当内存使用率过高时触发优化",
            condition=high_memory_condition,
            action_generator=high_memory_action,
            priority=1
        ))
        
    def _export_recommendations_json(self) -> str:
        """导出JSON格式的建议"""
        with self._lock:
            data = {
                "timestamp": datetime.now().isoformat(),
                "summary": self.get_optimization_summary(),
                "recommendations": [rec.to_dict() for rec in self.recommendations]
            }
            return json.dumps(data, indent=2, ensure_ascii=False)
            
    def _export_recommendations_csv(self) -> str:
        """导出CSV格式的建议"""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入头部
        writer.writerow([
            'recommendation_id', 'optimization_type', 'severity', 'action',
            'component', 'description', 'impact_estimate', 'confidence',
            'created_at', 'applied', 'applied_at'
        ])
        
        # 写入数据
        with self._lock:
            for rec in self.recommendations:
                writer.writerow([
                    rec.recommendation_id,
                    rec.optimization_type.name,
                    rec.severity.name,
                    rec.action.name,
                    rec.component,
                    rec.description,
                    rec.impact_estimate,
                    rec.confidence,
                    rec.created_at.isoformat(),
                    rec.applied,
                    rec.applied_at.isoformat() if rec.applied_at else ""
                ])
                
        return output.getvalue()


# 全局优化器实例
_global_optimizer: Optional[ConfigOptimizer] = None


def get_config_optimizer() -> ConfigOptimizer:
    """获取全局配置优化器实例"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = ConfigOptimizer()
        _global_optimizer.start_optimization()
    return _global_optimizer


def optimize_config(optimization_type: OptimizationType):
    """配置优化装饰器
    
    Args:
        optimization_type: 优化类型
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            optimizer = get_config_optimizer()
            
            # 执行函数并测量性能
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                end_time = time.perf_counter()
                
                # 记录性能数据用于优化分析
                duration_ms = (end_time - start_time) * 1000
                
                # 这里可以添加更多的性能分析逻辑
                
                return result
                
            except Exception as e:
                # 记录错误用于优化分析
                raise
                
        return wrapper
    return decorator


# 使用示例
if __name__ == "__main__":
    import random
    
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建优化器
    optimizer = ConfigOptimizer(
        optimization_interval=10.0,  # 10秒分析一次
        auto_apply_safe_optimizations=True
    )
    
    print("=== 配置优化引擎测试 ===")
    
    # 启动优化器
    optimizer.start_optimization()
    
    # 模拟一些性能问题
    monitor = get_performance_monitor()
    cache = get_config_cache()
    
    # 模拟高延迟
    for i in range(10):
        latency = random.uniform(120, 200)  # 高延迟
        monitor.record_metric(
            MetricType.LATENCY,
            latency,
            "test_component",
            "test_operation",
            "ms"
        )
        time.sleep(0.1)
        
    # 等待优化分析
    time.sleep(12)
    
    # 获取建议
    recommendations = optimizer.get_recommendations(limit=5)
    print(f"\n=== 优化建议 ({len(recommendations)}条) ===")
    for rec in recommendations:
        print(f"- {rec.severity.name}: {rec.description}")
        print(f"  影响: {rec.impact_estimate:.0%}, 置信度: {rec.confidence:.0%}")
        
    # 显示优化摘要
    summary = optimizer.get_optimization_summary()
    print(f"\n=== 优化摘要 ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    # 测试优化装饰器
    @optimize_config(OptimizationType.PERFORMANCE)
    def test_function():
        time.sleep(random.uniform(0.05, 0.15))
        return "test_result"
        
    print(f"\n=== 测试优化装饰器 ===")
    for i in range(5):
        result = test_function()
        print(f"第{i+1}次调用: {result}")
        
    # 停止优化器
    optimizer.stop_optimization()
    
    print("\n✅ 配置优化引擎演示完成")