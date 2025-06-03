#!/usr/bin/env python3
"""
MarketPrism 性能分析器
配置管理系统 2.0 - Week 5 Day 5

高级性能分析组件，提供深度性能分析、趋势预测、
瓶颈识别和性能报告生成功能。

Author: MarketPrism团队
Created: 2025-01-29
Version: 1.0.0
"""

import time
import threading
import statistics
import json
import math
import warnings
from typing import Dict, Any, List, Optional, Callable, Union, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict, deque
import uuid
import psutil
import logging

# 数值计算和统计库
import numpy as np
from scipy import stats as scipy_stats
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64

# 导入相关组件
from .config_performance_monitor import (
    ConfigPerformanceMonitor, 
    PerformanceMetric,
    PerformanceAlert,
    MetricType,
    AlertSeverity,
    get_performance_monitor
)

# 抑制警告
warnings.filterwarnings('ignore', category=UserWarning)


class AnalysisType(Enum):
    """分析类型"""
    TREND_ANALYSIS = auto()       # 趋势分析
    ANOMALY_DETECTION = auto()    # 异常检测
    CORRELATION_ANALYSIS = auto() # 相关性分析
    BOTTLENECK_ANALYSIS = auto()  # 瓶颈分析
    CAPACITY_PLANNING = auto()    # 容量规划
    PERFORMANCE_REGRESSION = auto() # 性能回归分析


class TrendType(Enum):
    """趋势类型"""
    INCREASING = auto()           # 上升趋势
    DECREASING = auto()           # 下降趋势
    STABLE = auto()               # 稳定趋势
    VOLATILE = auto()             # 波动趋势
    SEASONAL = auto()             # 季节性趋势


class AnomalyType(Enum):
    """异常类型"""
    SPIKE = auto()                # 尖刺异常
    DIP = auto()                  # 下降异常
    PLATEAU = auto()              # 平台异常
    OSCILLATION = auto()          # 振荡异常
    DRIFT = auto()                # 漂移异常


class BottleneckType(Enum):
    """瓶颈类型"""
    CPU_BOUND = auto()            # CPU瓶颈
    MEMORY_BOUND = auto()         # 内存瓶颈
    IO_BOUND = auto()             # IO瓶颈
    NETWORK_BOUND = auto()        # 网络瓶颈
    LOCK_CONTENTION = auto()      # 锁竞争
    CACHE_MISS = auto()           # 缓存缺失


@dataclass
class TrendAnalysis:
    """趋势分析结果"""
    component: str
    metric_type: MetricType
    trend_type: TrendType
    slope: float                  # 趋势斜率
    correlation: float            # 相关系数
    p_value: float               # p值
    confidence: float            # 置信度
    start_time: datetime
    end_time: datetime
    sample_count: int
    prediction: Optional[Dict[str, float]] = None  # 预测值
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['metric_type'] = self.metric_type.name
        data['trend_type'] = self.trend_type.name
        data['start_time'] = self.start_time.isoformat()
        data['end_time'] = self.end_time.isoformat()
        return data


@dataclass
class AnomalyDetection:
    """异常检测结果"""
    anomaly_id: str
    component: str
    metric_type: MetricType
    anomaly_type: AnomalyType
    timestamp: datetime
    value: float
    expected_value: float
    deviation: float              # 偏差程度
    severity: float              # 严重程度 (0-1)
    confidence: float            # 置信度 (0-1)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['metric_type'] = self.metric_type.name
        data['anomaly_type'] = self.anomaly_type.name
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class BottleneckAnalysis:
    """瓶颈分析结果"""
    component: str
    bottleneck_type: BottleneckType
    severity: float              # 严重程度 (0-1)
    description: str
    contributing_factors: List[str]
    recommendations: List[str]
    impact_estimate: float       # 影响估计 (0-1)
    detected_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['bottleneck_type'] = self.bottleneck_type.name
        data['detected_at'] = self.detected_at.isoformat()
        return data


@dataclass
class PerformanceReport:
    """性能报告"""
    report_id: str
    title: str
    period_start: datetime
    period_end: datetime
    analysis_types: List[AnalysisType]
    summary: Dict[str, Any]
    trend_analyses: List[TrendAnalysis]
    anomaly_detections: List[AnomalyDetection]
    bottleneck_analyses: List[BottleneckAnalysis]
    recommendations: List[str]
    charts: Dict[str, str] = field(default_factory=dict)  # Base64编码的图表
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['period_start'] = self.period_start.isoformat()
        data['period_end'] = self.period_end.isoformat()
        data['analysis_types'] = [t.name for t in self.analysis_types]
        data['created_at'] = self.created_at.isoformat()
        data['trend_analyses'] = [t.to_dict() for t in self.trend_analyses]
        data['anomaly_detections'] = [a.to_dict() for a in self.anomaly_detections]
        data['bottleneck_analyses'] = [b.to_dict() for b in self.bottleneck_analyses]
        return data


class PerformanceAnalyzer:
    """性能分析器
    
    提供深度性能分析功能，包括：
    - 趋势分析和预测
    - 异常检测和识别
    - 瓶颈分析和诊断
    - 相关性分析
    - 性能报告生成
    """
    
    def __init__(self,
                 analysis_window_hours: int = 24,
                 anomaly_sensitivity: float = 2.0,
                 min_sample_size: int = 10):
        """初始化性能分析器
        
        Args:
            analysis_window_hours: 分析时间窗口（小时）
            anomaly_sensitivity: 异常检测敏感度（标准差倍数）
            min_sample_size: 最小样本数量
        """
        self.analysis_window = timedelta(hours=analysis_window_hours)
        self.anomaly_sensitivity = anomaly_sensitivity
        self.min_sample_size = min_sample_size
        
        # 组件引用
        self._monitor = get_performance_monitor()
        
        # 分析结果存储
        self.trend_analyses: List[TrendAnalysis] = []
        self.anomaly_detections: List[AnomalyDetection] = []
        self.bottleneck_analyses: List[BottleneckAnalysis] = []
        self.performance_reports: List[PerformanceReport] = []
        
        # 分析状态
        self._analyzing = False
        self._analysis_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # 统计信息
        self.stats = {
            "total_analyses": 0,
            "anomalies_detected": 0,
            "bottlenecks_identified": 0,
            "reports_generated": 0,
            "last_analysis": None
        }
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def start_analysis(self, interval_minutes: int = 60):
        """启动性能分析
        
        Args:
            interval_minutes: 分析间隔（分钟）
        """
        if self._analyzing:
            return
            
        self._analyzing = True
        self._analysis_interval = interval_minutes * 60
        self._analysis_thread = threading.Thread(
            target=self._analysis_loop,
            daemon=True,
            name="PerformanceAnalyzer"
        )
        self._analysis_thread.start()
        self.logger.info("性能分析器已启动")
        
    def stop_analysis(self):
        """停止性能分析"""
        self._analyzing = False
        if self._analysis_thread:
            self._analysis_thread.join(timeout=5.0)
        self.logger.info("性能分析器已停止")
        
    def analyze_trends(self, 
                      component: Optional[str] = None,
                      metric_type: Optional[MetricType] = None) -> List[TrendAnalysis]:
        """分析性能趋势
        
        Args:
            component: 组件过滤
            metric_type: 指标类型过滤
            
        Returns:
            趋势分析结果列表
        """
        with self._lock:
            try:
                # 获取分析时间窗口内的数据
                end_time = datetime.now()
                start_time = end_time - self.analysis_window
                
                metrics = self._monitor.get_metrics(
                    component=component,
                    metric_type=metric_type,
                    since=start_time
                )
                
                if len(metrics) < self.min_sample_size:
                    self.logger.warning(f"样本数量不足: {len(metrics)} < {self.min_sample_size}")
                    return []
                    
                # 按组件和指标类型分组
                grouped_metrics = self._group_metrics(metrics)
                
                trend_analyses = []
                for key, metric_list in grouped_metrics.items():
                    if len(metric_list) < self.min_sample_size:
                        continue
                        
                    component_name, metric_type_name = key.split('.')
                    metric_type_enum = MetricType[metric_type_name]
                    
                    trend_analysis = self._analyze_metric_trend(
                        metric_list, 
                        component_name, 
                        metric_type_enum
                    )
                    
                    if trend_analysis:
                        trend_analyses.append(trend_analysis)
                        
                self.trend_analyses.extend(trend_analyses)
                self.stats["total_analyses"] += len(trend_analyses)
                
                return trend_analyses
                
            except Exception as e:
                self.logger.error(f"趋势分析失败: {e}")
                return []
                
    def detect_anomalies(self,
                        component: Optional[str] = None,
                        metric_type: Optional[MetricType] = None) -> List[AnomalyDetection]:
        """检测性能异常
        
        Args:
            component: 组件过滤
            metric_type: 指标类型过滤
            
        Returns:
            异常检测结果列表
        """
        with self._lock:
            try:
                # 获取较长时间窗口的数据用于建立基线
                end_time = datetime.now()
                start_time = end_time - (self.analysis_window * 2)
                
                metrics = self._monitor.get_metrics(
                    component=component,
                    metric_type=metric_type,
                    since=start_time
                )
                
                if len(metrics) < self.min_sample_size * 2:
                    return []
                    
                # 按组件和指标类型分组
                grouped_metrics = self._group_metrics(metrics)
                
                anomalies = []
                for key, metric_list in grouped_metrics.items():
                    if len(metric_list) < self.min_sample_size * 2:
                        continue
                        
                    component_name, metric_type_name = key.split('.')
                    metric_type_enum = MetricType[metric_type_name]
                    
                    metric_anomalies = self._detect_metric_anomalies(
                        metric_list,
                        component_name,
                        metric_type_enum
                    )
                    
                    anomalies.extend(metric_anomalies)
                    
                self.anomaly_detections.extend(anomalies)
                self.stats["anomalies_detected"] += len(anomalies)
                
                return anomalies
                
            except Exception as e:
                self.logger.error(f"异常检测失败: {e}")
                return []
                
    def analyze_bottlenecks(self) -> List[BottleneckAnalysis]:
        """分析系统瓶颈
        
        Returns:
            瓶颈分析结果列表
        """
        with self._lock:
            try:
                # 获取最近的性能数据
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=1)  # 最近1小时
                
                metrics = self._monitor.get_metrics(since=start_time)
                
                if len(metrics) < self.min_sample_size:
                    return []
                    
                bottlenecks = []
                
                # 分析CPU瓶颈
                cpu_metrics = [m for m in metrics if m.metric_type == MetricType.CPU_USAGE]
                if cpu_metrics:
                    cpu_bottleneck = self._analyze_cpu_bottleneck(cpu_metrics)
                    if cpu_bottleneck:
                        bottlenecks.append(cpu_bottleneck)
                        
                # 分析内存瓶颈
                memory_metrics = [m for m in metrics if m.metric_type == MetricType.MEMORY_USAGE]
                if memory_metrics:
                    memory_bottleneck = self._analyze_memory_bottleneck(memory_metrics)
                    if memory_bottleneck:
                        bottlenecks.append(memory_bottleneck)
                        
                # 分析缓存瓶颈
                cache_metrics = [m for m in metrics if m.metric_type == MetricType.CACHE_HIT_RATE]
                if cache_metrics:
                    cache_bottleneck = self._analyze_cache_bottleneck(cache_metrics)
                    if cache_bottleneck:
                        bottlenecks.append(cache_bottleneck)
                        
                # 分析延迟瓶颈
                latency_metrics = [m for m in metrics if m.metric_type == MetricType.LATENCY]
                if latency_metrics:
                    latency_bottleneck = self._analyze_latency_bottleneck(latency_metrics)
                    if latency_bottleneck:
                        bottlenecks.append(latency_bottleneck)
                        
                self.bottleneck_analyses.extend(bottlenecks)
                self.stats["bottlenecks_identified"] += len(bottlenecks)
                
                return bottlenecks
                
            except Exception as e:
                self.logger.error(f"瓶颈分析失败: {e}")
                return []
                
    def generate_performance_report(self,
                                  title: str = "性能分析报告",
                                  include_charts: bool = True) -> PerformanceReport:
        """生成性能报告
        
        Args:
            title: 报告标题
            include_charts: 是否包含图表
            
        Returns:
            性能报告
        """
        with self._lock:
            try:
                end_time = datetime.now()
                start_time = end_time - self.analysis_window
                
                # 执行各种分析
                trends = self.analyze_trends()
                anomalies = self.detect_anomalies()
                bottlenecks = self.analyze_bottlenecks()
                
                # 生成摘要
                summary = self._generate_summary(trends, anomalies, bottlenecks)
                
                # 生成建议
                recommendations = self._generate_recommendations(trends, anomalies, bottlenecks)
                
                # 生成图表
                charts = {}
                if include_charts:
                    charts = self._generate_charts(start_time, end_time)
                    
                # 创建报告
                report = PerformanceReport(
                    report_id=str(uuid.uuid4()),
                    title=title,
                    period_start=start_time,
                    period_end=end_time,
                    analysis_types=[
                        AnalysisType.TREND_ANALYSIS,
                        AnalysisType.ANOMALY_DETECTION,
                        AnalysisType.BOTTLENECK_ANALYSIS
                    ],
                    summary=summary,
                    trend_analyses=trends,
                    anomaly_detections=anomalies,
                    bottleneck_analyses=bottlenecks,
                    recommendations=recommendations,
                    charts=charts
                )
                
                self.performance_reports.append(report)
                self.stats["reports_generated"] += 1
                
                return report
                
            except Exception as e:
                self.logger.error(f"生成性能报告失败: {e}")
                raise
                
    def get_analysis_summary(self) -> Dict[str, Any]:
        """获取分析摘要"""
        with self._lock:
            return {
                "timestamp": datetime.now().isoformat(),
                "analysis_status": "active" if self._analyzing else "inactive",
                "stats": self.stats.copy(),
                "recent_trends": len([t for t in self.trend_analyses 
                                    if (datetime.now() - t.start_time).days < 7]),
                "recent_anomalies": len([a for a in self.anomaly_detections 
                                       if (datetime.now() - a.timestamp).days < 7]),
                "active_bottlenecks": len([b for b in self.bottleneck_analyses 
                                         if (datetime.now() - b.detected_at).total_seconds() < 24*3600]),
                "recent_reports": len([r for r in self.performance_reports 
                                     if (datetime.now() - r.created_at).days < 7])
            }
            
    def _analysis_loop(self):
        """分析循环"""
        while self._analyzing:
            try:
                self.logger.info("开始性能分析...")
                
                # 执行各种分析
                trends = self.analyze_trends()
                anomalies = self.detect_anomalies()
                bottlenecks = self.analyze_bottlenecks()
                
                if trends or anomalies or bottlenecks:
                    self.logger.info(f"分析完成: {len(trends)}个趋势, "
                                   f"{len(anomalies)}个异常, {len(bottlenecks)}个瓶颈")
                    
                self.stats["last_analysis"] = datetime.now().isoformat()
                
                # 等待下一次分析
                time.sleep(self._analysis_interval)
                
            except Exception as e:
                self.logger.error(f"分析循环异常: {e}")
                time.sleep(300)  # 错误后等待5分钟
                
    def _group_metrics(self, metrics: List[PerformanceMetric]) -> Dict[str, List[PerformanceMetric]]:
        """按组件和指标类型分组指标"""
        grouped = defaultdict(list)
        for metric in metrics:
            key = f"{metric.component}.{metric.metric_type.name}"
            grouped[key].append(metric)
        return dict(grouped)
        
    def _analyze_metric_trend(self, 
                            metrics: List[PerformanceMetric],
                            component: str,
                            metric_type: MetricType) -> Optional[TrendAnalysis]:
        """分析单个指标的趋势"""
        try:
            if len(metrics) < self.min_sample_size:
                return None
                
            # 按时间排序
            metrics.sort(key=lambda m: m.timestamp)
            
            # 提取时间和值
            timestamps = [m.timestamp for m in metrics]
            values = [m.value for m in metrics]
            
            # 转换为数值时间
            time_nums = [(t - timestamps[0]).total_seconds() for t in timestamps]
            
            # 线性回归分析
            slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(time_nums, values)
            
            # 确定趋势类型
            trend_type = TrendType.STABLE
            if abs(r_value) > 0.7:  # 强相关性
                if slope > 0:
                    trend_type = TrendType.INCREASING
                else:
                    trend_type = TrendType.DECREASING
            elif statistics.stdev(values) / statistics.mean(values) > 0.2:  # 高变异系数
                trend_type = TrendType.VOLATILE
                
            # 计算置信度
            confidence = abs(r_value) * (1 - p_value) if p_value < 0.05 else 0.5
            
            # 预测未来值
            future_time = time_nums[-1] + 3600  # 1小时后
            predicted_value = slope * future_time + intercept
            
            return TrendAnalysis(
                component=component,
                metric_type=metric_type,
                trend_type=trend_type,
                slope=slope,
                correlation=r_value,
                p_value=p_value,
                confidence=confidence,
                start_time=timestamps[0],
                end_time=timestamps[-1],
                sample_count=len(metrics),
                prediction={"1h": predicted_value}
            )
            
        except Exception as e:
            self.logger.error(f"趋势分析失败: {e}")
            return None
            
    def _detect_metric_anomalies(self,
                               metrics: List[PerformanceMetric],
                               component: str,
                               metric_type: MetricType) -> List[AnomalyDetection]:
        """检测单个指标的异常"""
        try:
            anomalies = []
            
            if len(metrics) < self.min_sample_size * 2:
                return anomalies
                
            # 按时间排序
            metrics.sort(key=lambda m: m.timestamp)
            
            # 分割数据：前70%作为基线，后30%检测异常
            split_point = int(len(metrics) * 0.7)
            baseline_metrics = metrics[:split_point]
            test_metrics = metrics[split_point:]
            
            # 计算基线统计
            baseline_values = [m.value for m in baseline_metrics]
            baseline_mean = statistics.mean(baseline_values)
            baseline_std = statistics.stdev(baseline_values) if len(baseline_values) > 1 else 0
            
            if baseline_std == 0:
                return anomalies
                
            # 检测异常
            for metric in test_metrics:
                z_score = abs(metric.value - baseline_mean) / baseline_std
                
                if z_score > self.anomaly_sensitivity:
                    # 确定异常类型
                    anomaly_type = AnomalyType.SPIKE if metric.value > baseline_mean else AnomalyType.DIP
                    
                    anomaly = AnomalyDetection(
                        anomaly_id=str(uuid.uuid4()),
                        component=component,
                        metric_type=metric_type,
                        anomaly_type=anomaly_type,
                        timestamp=metric.timestamp,
                        value=metric.value,
                        expected_value=baseline_mean,
                        deviation=z_score,
                        severity=min(z_score / 5.0, 1.0),  # 归一化到0-1
                        confidence=min(z_score / 3.0, 1.0),
                        context={
                            "baseline_mean": baseline_mean,
                            "baseline_std": baseline_std,
                            "z_score": z_score
                        }
                    )
                    
                    anomalies.append(anomaly)
                    
            return anomalies
            
        except Exception as e:
            self.logger.error(f"异常检测失败: {e}")
            return []
            
    def _analyze_cpu_bottleneck(self, cpu_metrics: List[PerformanceMetric]) -> Optional[BottleneckAnalysis]:
        """分析CPU瓶颈"""
        try:
            if not cpu_metrics:
                return None
                
            values = [m.value for m in cpu_metrics]
            avg_cpu = statistics.mean(values)
            max_cpu = max(values)
            
            if avg_cpu > 80 or max_cpu > 95:
                severity = min((avg_cpu - 50) / 50, 1.0)
                
                return BottleneckAnalysis(
                    component="system",
                    bottleneck_type=BottleneckType.CPU_BOUND,
                    severity=severity,
                    description=f"CPU使用率过高: 平均{avg_cpu:.1f}%, 峰值{max_cpu:.1f}%",
                    contributing_factors=[
                        "高CPU密集型操作",
                        "可能的死循环或无限递归",
                        "线程争抢CPU资源"
                    ],
                    recommendations=[
                        "优化CPU密集型算法",
                        "增加CPU核心数量",
                        "使用异步处理减少CPU阻塞",
                        "实施负载均衡"
                    ],
                    impact_estimate=severity,
                    detected_at=datetime.now()
                )
                
            return None
            
        except Exception as e:
            self.logger.error(f"CPU瓶颈分析失败: {e}")
            return None
            
    def _analyze_memory_bottleneck(self, memory_metrics: List[PerformanceMetric]) -> Optional[BottleneckAnalysis]:
        """分析内存瓶颈"""
        try:
            if not memory_metrics:
                return None
                
            values = [m.value for m in memory_metrics]
            avg_memory = statistics.mean(values)
            max_memory = max(values)
            
            if avg_memory > 1000 or max_memory > 2000:  # MB
                severity = min((avg_memory - 500) / 1500, 1.0)
                
                return BottleneckAnalysis(
                    component="system",
                    bottleneck_type=BottleneckType.MEMORY_BOUND,
                    severity=severity,
                    description=f"内存使用过高: 平均{avg_memory:.1f}MB, 峰值{max_memory:.1f}MB",
                    contributing_factors=[
                        "内存泄漏",
                        "大对象缓存过多",
                        "垃圾回收不及时"
                    ],
                    recommendations=[
                        "检查内存泄漏",
                        "优化缓存策略",
                        "增加内存容量",
                        "启用内存压缩"
                    ],
                    impact_estimate=severity,
                    detected_at=datetime.now()
                )
                
            return None
            
        except Exception as e:
            self.logger.error(f"内存瓶颈分析失败: {e}")
            return None
            
    def _analyze_cache_bottleneck(self, cache_metrics: List[PerformanceMetric]) -> Optional[BottleneckAnalysis]:
        """分析缓存瓶颈"""
        try:
            if not cache_metrics:
                return None
                
            values = [m.value for m in cache_metrics]
            avg_hit_rate = statistics.mean(values)
            min_hit_rate = min(values)
            
            if avg_hit_rate < 0.7 or min_hit_rate < 0.5:
                severity = (0.9 - avg_hit_rate) / 0.4  # 归一化
                
                return BottleneckAnalysis(
                    component="cache",
                    bottleneck_type=BottleneckType.CACHE_MISS,
                    severity=severity,
                    description=f"缓存命中率低: 平均{avg_hit_rate:.1%}, 最低{min_hit_rate:.1%}",
                    contributing_factors=[
                        "缓存大小不足",
                        "缓存策略不当",
                        "访问模式变化",
                        "热点数据未预加载"
                    ],
                    recommendations=[
                        "增加缓存容量",
                        "优化缓存策略",
                        "预加载热点数据",
                        "分析访问模式"
                    ],
                    impact_estimate=severity,
                    detected_at=datetime.now()
                )
                
            return None
            
        except Exception as e:
            self.logger.error(f"缓存瓶颈分析失败: {e}")
            return None
            
    def _analyze_latency_bottleneck(self, latency_metrics: List[PerformanceMetric]) -> Optional[BottleneckAnalysis]:
        """分析延迟瓶颈"""
        try:
            if not latency_metrics:
                return None
                
            values = [m.value for m in latency_metrics]
            avg_latency = statistics.mean(values)
            p95_latency = np.percentile(values, 95)
            
            if avg_latency > 200 or p95_latency > 500:  # ms
                severity = min(avg_latency / 1000, 1.0)
                
                return BottleneckAnalysis(
                    component="performance",
                    bottleneck_type=BottleneckType.IO_BOUND,
                    severity=severity,
                    description=f"响应延迟过高: 平均{avg_latency:.1f}ms, P95 {p95_latency:.1f}ms",
                    contributing_factors=[
                        "IO操作阻塞",
                        "网络延迟",
                        "数据库查询慢",
                        "锁竞争"
                    ],
                    recommendations=[
                        "优化IO操作",
                        "使用连接池",
                        "实施缓存策略",
                        "异步处理长时间操作"
                    ],
                    impact_estimate=severity,
                    detected_at=datetime.now()
                )
                
            return None
            
        except Exception as e:
            self.logger.error(f"延迟瓶颈分析失败: {e}")
            return None
            
    def _generate_summary(self,
                        trends: List[TrendAnalysis],
                        anomalies: List[AnomalyDetection],
                        bottlenecks: List[BottleneckAnalysis]) -> Dict[str, Any]:
        """生成分析摘要"""
        return {
            "period": f"{self.analysis_window.total_seconds() / 3600:.1f} hours",
            "trend_analysis": {
                "total_trends": len(trends),
                "increasing_trends": len([t for t in trends if t.trend_type == TrendType.INCREASING]),
                "decreasing_trends": len([t for t in trends if t.trend_type == TrendType.DECREASING]),
                "stable_trends": len([t for t in trends if t.trend_type == TrendType.STABLE]),
                "volatile_trends": len([t for t in trends if t.trend_type == TrendType.VOLATILE])
            },
            "anomaly_detection": {
                "total_anomalies": len(anomalies),
                "spikes": len([a for a in anomalies if a.anomaly_type == AnomalyType.SPIKE]),
                "dips": len([a for a in anomalies if a.anomaly_type == AnomalyType.DIP]),
                "avg_severity": statistics.mean([a.severity for a in anomalies]) if anomalies else 0
            },
            "bottleneck_analysis": {
                "total_bottlenecks": len(bottlenecks),
                "cpu_bottlenecks": len([b for b in bottlenecks if b.bottleneck_type == BottleneckType.CPU_BOUND]),
                "memory_bottlenecks": len([b for b in bottlenecks if b.bottleneck_type == BottleneckType.MEMORY_BOUND]),
                "cache_bottlenecks": len([b for b in bottlenecks if b.bottleneck_type == BottleneckType.CACHE_MISS]),
                "io_bottlenecks": len([b for b in bottlenecks if b.bottleneck_type == BottleneckType.IO_BOUND])
            }
        }
        
    def _generate_recommendations(self,
                                trends: List[TrendAnalysis],
                                anomalies: List[AnomalyDetection],
                                bottlenecks: List[BottleneckAnalysis]) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 基于趋势的建议
        increasing_latency_trends = [t for t in trends 
                                   if t.metric_type == MetricType.LATENCY and 
                                   t.trend_type == TrendType.INCREASING]
        if increasing_latency_trends:
            recommendations.append("检测到延迟上升趋势，建议进行性能优化")
            
        # 基于异常的建议
        high_severity_anomalies = [a for a in anomalies if a.severity > 0.7]
        if high_severity_anomalies:
            recommendations.append("检测到高严重性异常，建议立即调查原因")
            
        # 基于瓶颈的建议
        for bottleneck in bottlenecks:
            recommendations.extend(bottleneck.recommendations[:1])  # 每个瓶颈取一个建议
            
        return recommendations[:10]  # 最多10个建议
        
    def _generate_charts(self, start_time: datetime, end_time: datetime) -> Dict[str, str]:
        """生成性能图表"""
        charts = {}
        
        try:
            # 获取数据
            metrics = self._monitor.get_metrics(since=start_time)
            
            if not metrics:
                return charts
                
            # 按指标类型分组
            latency_metrics = [m for m in metrics if m.metric_type == MetricType.LATENCY]
            memory_metrics = [m for m in metrics if m.metric_type == MetricType.MEMORY_USAGE]
            
            # 延迟趋势图
            if latency_metrics:
                charts["latency_trend"] = self._create_line_chart(
                    latency_metrics,
                    "延迟趋势",
                    "时间",
                    "延迟 (ms)"
                )
                
            # 内存使用图
            if memory_metrics:
                charts["memory_usage"] = self._create_line_chart(
                    memory_metrics,
                    "内存使用",
                    "时间",
                    "内存 (MB)"
                )
                
        except Exception as e:
            self.logger.error(f"图表生成失败: {e}")
            
        return charts
        
    def _create_line_chart(self,
                         metrics: List[PerformanceMetric],
                         title: str,
                         xlabel: str,
                         ylabel: str) -> str:
        """创建线图"""
        try:
            # 准备数据
            timestamps = [m.timestamp for m in metrics]
            values = [m.value for m in metrics]
            
            # 创建图表
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(timestamps, values, linewidth=2, alpha=0.8)
            
            # 设置标签
            ax.set_title(title, fontsize=14, fontweight='bold')
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            
            # 格式化时间轴
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            
            # 添加网格
            ax.grid(True, alpha=0.3)
            
            # 旋转时间标签
            plt.xticks(rotation=45)
            
            # 调整布局
            plt.tight_layout()
            
            # 转换为Base64
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return image_base64
            
        except Exception as e:
            self.logger.error(f"创建图表失败: {e}")
            return ""


# 全局分析器实例
_global_analyzer: Optional[PerformanceAnalyzer] = None


def get_performance_analyzer() -> PerformanceAnalyzer:
    """获取全局性能分析器实例"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = PerformanceAnalyzer()
    return _global_analyzer


# 使用示例
if __name__ == "__main__":
    import random
    
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建分析器
    analyzer = PerformanceAnalyzer(
        analysis_window_hours=1,
        anomaly_sensitivity=2.0
    )
    
    print("=== 性能分析器测试 ===")
    
    # 模拟性能数据
    monitor = get_performance_monitor()
    
    # 模拟递增延迟趋势
    base_latency = 50
    for i in range(20):
        latency = base_latency + i * 5 + random.uniform(-10, 10)
        monitor.record_metric(
            MetricType.LATENCY,
            latency,
            "test_component",
            "test_operation",
            "ms"
        )
        time.sleep(0.1)
        
    # 模拟异常值
    for _ in range(3):
        anomaly_latency = 200 + random.uniform(0, 100)
        monitor.record_metric(
            MetricType.LATENCY,
            anomaly_latency,
            "test_component",
            "test_operation",
            "ms"
        )
        time.sleep(0.1)
        
    # 执行分析
    print("\n=== 趋势分析 ===")
    trends = analyzer.analyze_trends()
    for trend in trends:
        print(f"- {trend.component}: {trend.trend_type.name}, "
              f"斜率={trend.slope:.2f}, 置信度={trend.confidence:.2f}")
        
    print("\n=== 异常检测 ===")
    anomalies = analyzer.detect_anomalies()
    for anomaly in anomalies:
        print(f"- {anomaly.component}: {anomaly.anomaly_type.name}, "
              f"严重程度={anomaly.severity:.2f}, 置信度={anomaly.confidence:.2f}")
        
    print("\n=== 瓶颈分析 ===")
    bottlenecks = analyzer.analyze_bottlenecks()
    for bottleneck in bottlenecks:
        print(f"- {bottleneck.component}: {bottleneck.bottleneck_type.name}, "
              f"严重程度={bottleneck.severity:.2f}")
        
    # 生成性能报告
    print("\n=== 性能报告 ===")
    report = analyzer.generate_performance_report(include_charts=False)
    print(f"报告ID: {report.report_id}")
    print(f"分析周期: {report.period_start} 到 {report.period_end}")
    print(f"趋势数量: {len(report.trend_analyses)}")
    print(f"异常数量: {len(report.anomaly_detections)}")
    print(f"瓶颈数量: {len(report.bottleneck_analyses)}")
    print(f"建议数量: {len(report.recommendations)}")
    
    # 显示分析摘要
    summary = analyzer.get_analysis_summary()
    print(f"\n=== 分析摘要 ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    print("\n✅ 性能分析器演示完成")