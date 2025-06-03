"""
缓存性能优化引擎

提供自动性能调优、预测缓存、性能分析和优化建议。
"""

import asyncio
import time
import statistics
from typing import Any, Optional, Dict, List, Union, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import logging

from .cache_interface import Cache, CacheKey, CacheValue, CacheStatistics
from .cache_coordinator import CacheCoordinator, CacheInstance


class OptimizationType(Enum):
    """优化类型"""
    MEMORY_USAGE = "memory_usage"
    HIT_RATE = "hit_rate"
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    COST_EFFICIENCY = "cost_efficiency"


class PredictionModel(Enum):
    """预测模型类型"""
    LINEAR_REGRESSION = "linear_regression"
    MOVING_AVERAGE = "moving_average"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    PATTERN_BASED = "pattern_based"


@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    target_value: Optional[float] = None
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None


@dataclass
class OptimizationRecommendation:
    """优化建议"""
    type: OptimizationType
    priority: int  # 1-10, 10最高
    description: str
    action: str
    expected_improvement: float
    confidence: float  # 0-1
    estimated_cost: Optional[float] = None


@dataclass
class AccessPattern:
    """访问模式"""
    key_pattern: str
    frequency: int
    last_access: datetime
    avg_access_interval: float  # 秒
    size_bytes: int
    hit_rate: float


@dataclass
class PerformanceOptimizerConfig:
    """性能优化器配置"""
    name: str = "performance_optimizer"
    
    # 监控配置
    monitoring_interval: int = 60  # 监控间隔（秒）
    history_retention_hours: int = 24  # 历史数据保留时间
    
    # 预测配置
    enable_prediction: bool = True
    prediction_model: PredictionModel = PredictionModel.MOVING_AVERAGE
    prediction_window_hours: int = 4  # 预测窗口
    
    # 优化配置
    enable_auto_optimization: bool = True
    optimization_interval: int = 300  # 优化间隔（秒）
    max_memory_usage_pct: float = 80.0  # 最大内存使用率
    min_hit_rate_pct: float = 70.0  # 最小命中率
    max_response_time_ms: float = 100.0  # 最大响应时间
    
    # 预加载配置
    enable_preloading: bool = True
    preload_threshold: int = 5  # 预加载阈值（访问次数）
    max_preload_items: int = 1000  # 最大预加载项数
    
    # 报告配置
    enable_reports: bool = True
    report_interval: int = 3600  # 报告间隔（秒）


class PerformanceOptimizer:
    """缓存性能优化引擎
    
    特性：
    - 实时性能监控
    - 自动性能调优
    - 预测性缓存
    - 访问模式分析
    - 优化建议生成
    - 性能报告
    """
    
    def __init__(self, config: PerformanceOptimizerConfig):
        self.config = config
        
        # 监控的缓存实例
        self.cache_instances: Dict[str, Cache] = {}
        
        # 性能历史数据
        self.metrics_history: Dict[str, List[PerformanceMetric]] = {}
        
        # 访问模式分析
        self.access_patterns: Dict[str, AccessPattern] = {}
        self.access_history: List[Tuple[str, datetime]] = []  # (key, timestamp)
        
        # 优化建议
        self.recommendations: List[OptimizationRecommendation] = []
        
        # 预测缓存
        self.predicted_keys: Set[str] = set()
        
        # 后台任务
        self._monitoring_task = None
        self._optimization_task = None
        self._reporting_task = None
        self._enabled = False
        
        self._logger = logging.getLogger(__name__)
    
    def add_cache(self, name: str, cache: Cache) -> None:
        """添加缓存实例进行监控"""
        self.cache_instances[name] = cache
        self.metrics_history[name] = []
        self._logger.info(f"添加缓存监控: {name}")
    
    def remove_cache(self, name: str) -> bool:
        """移除缓存监控"""
        if name in self.cache_instances:
            del self.cache_instances[name]
            if name in self.metrics_history:
                del self.metrics_history[name]
            self._logger.info(f"移除缓存监控: {name}")
            return True
        return False
    
    async def start(self) -> None:
        """启动性能优化器"""
        self._enabled = True
        
        # 启动监控任务
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # 启动优化任务
        if self.config.enable_auto_optimization:
            self._optimization_task = asyncio.create_task(self._optimization_loop())
        
        # 启动报告任务
        if self.config.enable_reports:
            self._reporting_task = asyncio.create_task(self._reporting_loop())
        
        self._logger.info("性能优化器启动完成")
    
    async def stop(self) -> None:
        """停止性能优化器"""
        self._enabled = False
        
        # 取消后台任务
        for task in [self._monitoring_task, self._optimization_task, self._reporting_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._logger.info("性能优化器已停止")
    
    async def _monitoring_loop(self) -> None:
        """监控循环"""
        while self._enabled:
            try:
                await self._collect_metrics()
                await self._analyze_access_patterns()
                await asyncio.sleep(self.config.monitoring_interval)
            except Exception as e:
                self._logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(self.config.monitoring_interval)
    
    async def _optimization_loop(self) -> None:
        """优化循环"""
        while self._enabled:
            try:
                await asyncio.sleep(self.config.optimization_interval)
                await self._generate_recommendations()
                await self._apply_auto_optimizations()
                if self.config.enable_prediction:
                    await self._predict_and_preload()
            except Exception as e:
                self._logger.error(f"优化循环错误: {e}")
    
    async def _reporting_loop(self) -> None:
        """报告循环"""
        while self._enabled:
            try:
                await asyncio.sleep(self.config.report_interval)
                await self._generate_performance_report()
            except Exception as e:
                self._logger.error(f"报告循环错误: {e}")
    
    async def _collect_metrics(self) -> None:
        """收集性能指标"""
        current_time = datetime.now(timezone.utc)
        
        for name, cache in self.cache_instances.items():
            try:
                # 获取缓存统计
                stats = cache.stats if hasattr(cache, 'stats') else CacheStatistics()
                
                # 计算关键指标
                hit_rate = stats.hit_rate if stats.total_operations > 0 else 0.0
                avg_response_time = (
                    (stats.total_get_time + stats.total_set_time) / 
                    max(stats.total_operations, 1) * 1000  # 转换为毫秒
                )
                
                # 创建性能指标
                metrics = [
                    PerformanceMetric(
                        name="hit_rate",
                        value=hit_rate * 100,
                        unit="%",
                        timestamp=current_time,
                        target_value=self.config.min_hit_rate_pct,
                        threshold_warning=self.config.min_hit_rate_pct - 10,
                        threshold_critical=self.config.min_hit_rate_pct - 20
                    ),
                    PerformanceMetric(
                        name="response_time",
                        value=avg_response_time,
                        unit="ms",
                        timestamp=current_time,
                        target_value=self.config.max_response_time_ms,
                        threshold_warning=self.config.max_response_time_ms * 1.5,
                        threshold_critical=self.config.max_response_time_ms * 2.0
                    ),
                    PerformanceMetric(
                        name="operations_per_second",
                        value=stats.total_operations / max(time.time() - stats.start_time, 1),
                        unit="ops/s",
                        timestamp=current_time
                    )
                ]
                
                # 如果支持，添加内存使用指标
                if hasattr(cache, 'get_memory_usage'):
                    memory_usage = await cache.get_memory_usage()
                    metrics.append(
                        PerformanceMetric(
                            name="memory_usage",
                            value=memory_usage,
                            unit="MB",
                            timestamp=current_time,
                            target_value=self.config.max_memory_usage_pct,
                            threshold_warning=self.config.max_memory_usage_pct * 0.9,
                            threshold_critical=self.config.max_memory_usage_pct
                        )
                    )
                
                # 保存指标历史
                self.metrics_history[name].extend(metrics)
                
                # 清理过期数据
                cutoff_time = current_time - timedelta(hours=self.config.history_retention_hours)
                self.metrics_history[name] = [
                    m for m in self.metrics_history[name] 
                    if m.timestamp > cutoff_time
                ]
                
            except Exception as e:
                self._logger.warning(f"收集指标失败 {name}: {e}")
    
    async def _analyze_access_patterns(self) -> None:
        """分析访问模式"""
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time - timedelta(hours=1)  # 分析最近1小时
        
        # 清理过期访问历史
        self.access_history = [
            (key, timestamp) for key, timestamp in self.access_history
            if timestamp > cutoff_time
        ]
        
        # 分析访问频率和模式
        key_access_counts = {}
        key_last_access = {}
        key_access_intervals = {}
        
        for key, timestamp in self.access_history:
            key_access_counts[key] = key_access_counts.get(key, 0) + 1
            key_last_access[key] = max(key_last_access.get(key, timestamp), timestamp)
            
            # 计算访问间隔
            if key not in key_access_intervals:
                key_access_intervals[key] = []
            if key in key_last_access:
                interval = (timestamp - key_last_access[key]).total_seconds()
                if interval > 0:
                    key_access_intervals[key].append(interval)
        
        # 更新访问模式
        for key, count in key_access_counts.items():
            if count >= 3:  # 只分析有足够访问次数的键
                avg_interval = (
                    statistics.mean(key_access_intervals.get(key, [60])) 
                    if key_access_intervals.get(key) else 60
                )
                
                self.access_patterns[key] = AccessPattern(
                    key_pattern=key,
                    frequency=count,
                    last_access=key_last_access[key],
                    avg_access_interval=avg_interval,
                    size_bytes=0,  # TODO: 实际计算
                    hit_rate=1.0  # TODO: 实际计算
                )
    
    async def _generate_recommendations(self) -> None:
        """生成优化建议"""
        self.recommendations.clear()
        current_time = datetime.now(timezone.utc)
        
        for name, metrics_list in self.metrics_history.items():
            if not metrics_list:
                continue
            
            # 获取最新指标
            latest_metrics = {
                m.name: m for m in metrics_list 
                if m.timestamp > current_time - timedelta(minutes=5)
            }
            
            # 分析命中率
            if "hit_rate" in latest_metrics:
                hit_rate_metric = latest_metrics["hit_rate"]
                if hit_rate_metric.value < self.config.min_hit_rate_pct:
                    self.recommendations.append(
                        OptimizationRecommendation(
                            type=OptimizationType.HIT_RATE,
                            priority=8,
                            description=f"缓存 {name} 命中率过低: {hit_rate_metric.value:.1f}%",
                            action="增加缓存容量或调整淘汰策略",
                            expected_improvement=20.0,
                            confidence=0.8
                        )
                    )
            
            # 分析响应时间
            if "response_time" in latest_metrics:
                rt_metric = latest_metrics["response_time"]
                if rt_metric.value > self.config.max_response_time_ms:
                    self.recommendations.append(
                        OptimizationRecommendation(
                            type=OptimizationType.RESPONSE_TIME,
                            priority=7,
                            description=f"缓存 {name} 响应时间过长: {rt_metric.value:.1f}ms",
                            action="优化序列化方式或使用更快的存储",
                            expected_improvement=30.0,
                            confidence=0.7
                        )
                    )
            
            # 分析内存使用
            if "memory_usage" in latest_metrics:
                mem_metric = latest_metrics["memory_usage"]
                if mem_metric.value > self.config.max_memory_usage_pct:
                    self.recommendations.append(
                        OptimizationRecommendation(
                            type=OptimizationType.MEMORY_USAGE,
                            priority=9,
                            description=f"缓存 {name} 内存使用过高: {mem_metric.value:.1f}%",
                            action="启用压缩或增加淘汰频率",
                            expected_improvement=25.0,
                            confidence=0.9
                        )
                    )
        
        # 分析访问模式，建议预加载
        frequent_patterns = [
            pattern for pattern in self.access_patterns.values()
            if pattern.frequency >= self.config.preload_threshold
        ]
        
        if frequent_patterns and len(self.predicted_keys) < self.config.max_preload_items:
            self.recommendations.append(
                OptimizationRecommendation(
                    type=OptimizationType.HIT_RATE,
                    priority=6,
                    description=f"发现 {len(frequent_patterns)} 个频繁访问模式",
                    action="启用预测性预加载",
                    expected_improvement=15.0,
                    confidence=0.6
                )
            )
        
        # 按优先级排序
        self.recommendations.sort(key=lambda x: x.priority, reverse=True)
    
    async def _apply_auto_optimizations(self) -> None:
        """应用自动优化"""
        if not self.config.enable_auto_optimization:
            return
        
        for rec in self.recommendations:
            if rec.priority >= 8 and rec.confidence >= 0.8:
                try:
                    await self._apply_optimization(rec)
                    self._logger.info(f"自动应用优化: {rec.action}")
                except Exception as e:
                    self._logger.warning(f"自动优化失败: {e}")
    
    async def _apply_optimization(self, recommendation: OptimizationRecommendation) -> None:
        """应用优化建议"""
        # 这里实现具体的优化逻辑
        # 目前是占位符实现
        if recommendation.type == OptimizationType.MEMORY_USAGE:
            # 触发内存清理
            for cache in self.cache_instances.values():
                if hasattr(cache, 'cleanup'):
                    await cache.cleanup()
        
        elif recommendation.type == OptimizationType.HIT_RATE:
            # 调整缓存策略
            pass
        
        # TODO: 实现更多优化策略
    
    async def _predict_and_preload(self) -> None:
        """预测并预加载数据"""
        if not self.config.enable_preloading:
            return
        
        predicted_keys = await self._predict_next_access()
        
        # 预加载预测的键
        for key in predicted_keys:
            if len(self.predicted_keys) >= self.config.max_preload_items:
                break
            
            if key not in self.predicted_keys:
                # 这里应该从数据源预加载数据到缓存
                # 目前是占位符实现
                self.predicted_keys.add(key)
                self._logger.debug(f"预加载键: {key}")
    
    async def _predict_next_access(self) -> List[str]:
        """预测下一次访问的键"""
        predictions = []
        current_time = datetime.now(timezone.utc)
        
        for key, pattern in self.access_patterns.items():
            # 基于访问间隔预测
            time_since_last = (current_time - pattern.last_access).total_seconds()
            
            if time_since_last >= pattern.avg_access_interval * 0.8:
                predictions.append(key)
        
        return predictions[:self.config.max_preload_items]
    
    async def _generate_performance_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "optimizer_config": {
                "monitoring_interval": self.config.monitoring_interval,
                "auto_optimization": self.config.enable_auto_optimization,
                "prediction_enabled": self.config.enable_prediction
            },
            "cache_instances": len(self.cache_instances),
            "metrics_summary": {},
            "access_patterns": len(self.access_patterns),
            "recommendations": len(self.recommendations),
            "predicted_keys": len(self.predicted_keys)
        }
        
        # 生成指标摘要
        for name, metrics_list in self.metrics_history.items():
            if metrics_list:
                recent_metrics = [
                    m for m in metrics_list
                    if m.timestamp > datetime.now(timezone.utc) - timedelta(hours=1)
                ]
                
                if recent_metrics:
                    hit_rates = [m.value for m in recent_metrics if m.name == "hit_rate"]
                    response_times = [m.value for m in recent_metrics if m.name == "response_time"]
                    
                    report["metrics_summary"][name] = {
                        "avg_hit_rate": statistics.mean(hit_rates) if hit_rates else 0,
                        "avg_response_time": statistics.mean(response_times) if response_times else 0,
                        "metrics_count": len(recent_metrics)
                    }
        
        self._logger.info(f"生成性能报告: {report['cache_instances']} 个缓存实例")
        return report
    
    # 公共接口
    def record_access(self, key: str) -> None:
        """记录访问"""
        self.access_history.append((key, datetime.now(timezone.utc)))
    
    def get_recommendations(self) -> List[OptimizationRecommendation]:
        """获取优化建议"""
        return self.recommendations.copy()
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        summary = {}
        current_time = datetime.now(timezone.utc)
        
        for name, metrics_list in self.metrics_history.items():
            recent_metrics = [
                m for m in metrics_list
                if m.timestamp > current_time - timedelta(minutes=5)
            ]
            
            if recent_metrics:
                summary[name] = {
                    metric.name: metric.value 
                    for metric in recent_metrics
                }
        
        return summary
    
    def get_access_patterns(self) -> Dict[str, AccessPattern]:
        """获取访问模式"""
        return self.access_patterns.copy()


# 便利函数
def create_performance_optimizer(
    config: Optional[PerformanceOptimizerConfig] = None
) -> PerformanceOptimizer:
    """创建性能优化器的便利函数"""
    if config is None:
        config = PerformanceOptimizerConfig()
    
    return PerformanceOptimizer(config) 