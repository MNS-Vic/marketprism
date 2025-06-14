"""
MarketPrism 性能分析器

设计目标：
- 实时性能监控和分析
- 性能瓶颈识别
- 资源使用优化建议
- 性能趋势预测

核心功能：
1. 响应时间分析 - 统计、分布、趋势
2. 吞吐量分析 - RPS、TPS、并发数
3. 资源使用分析 - CPU、内存、磁盘、网络
4. 错误率分析 - 错误类型、频率、影响
5. 瓶颈识别 - 慢查询、资源争用、性能热点
6. 优化建议 - 基于分析结果的改进建议

分析维度：
┌─────────────────────────────────────────────────────────┐
│                    性能分析器                            │
├─────────────────┬─────────────────┬─────────────────────┤
│   响应时间分析   │   吞吐量分析     │   资源使用分析       │
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────────┐ │
│ │ 平均响应时间 │ │ │ 请求/秒    │ │ │ CPU使用率       │ │
│ │ P95响应时间 │ │ │ 事务/秒    │ │ │ 内存使用率       │ │
│ │ P99响应时间 │ │ │ 并发连接数  │ │ │ 磁盘I/O        │ │
│ │ 响应时间分布 │ │ │ 队列长度   │ │ │ 网络带宽       │ │
│ └─────────────┘ │ └─────────────┘ │ └─────────────────┘ │
└─────────────────┴─────────────────┴─────────────────────┘
"""

import asyncio
import time
import logging
import statistics
from typing import Dict, Any, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
import json
import threading

logger = logging.getLogger(__name__)


class PerformanceLevel(Enum):
    """性能级别"""
    EXCELLENT = "excellent"  # 优秀
    GOOD = "good"           # 良好
    FAIR = "fair"           # 一般
    POOR = "poor"           # 较差
    CRITICAL = "critical"   # 严重


class BottleneckType(Enum):
    """瓶颈类型"""
    CPU_BOUND = "cpu_bound"           # CPU密集
    MEMORY_BOUND = "memory_bound"     # 内存密集
    IO_BOUND = "io_bound"             # I/O密集
    NETWORK_BOUND = "network_bound"   # 网络密集
    DATABASE_BOUND = "database_bound" # 数据库密集
    LOCK_CONTENTION = "lock_contention"  # 锁竞争
    UNKNOWN = "unknown"               # 未知


@dataclass
class PerformanceMetric:
    """性能指标"""
    timestamp: float
    operation: str
    response_time_ms: float
    success: bool
    error_type: Optional[str] = None
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    thread_id: Optional[int] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResponseTimeStats:
    """响应时间统计"""
    count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    avg_time: float = 0.0
    p50: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    std_dev: float = 0.0


@dataclass
class ThroughputStats:
    """吞吐量统计"""
    rps: float = 0.0          # 每秒请求数
    tps: float = 0.0          # 每秒事务数
    concurrent_connections: int = 0
    queue_length: int = 0
    success_rate: float = 0.0


@dataclass
class ResourceStats:
    """资源使用统计"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_usage_mb: float = 0.0
    disk_read_mb_s: float = 0.0
    disk_write_mb_s: float = 0.0
    network_in_mb_s: float = 0.0
    network_out_mb_s: float = 0.0
    active_threads: int = 0
    open_connections: int = 0


@dataclass
class PerformanceBottleneck:
    """性能瓶颈"""
    type: BottleneckType
    severity: PerformanceLevel
    component: str
    description: str
    impact_score: float  # 0-1, 影响分数
    suggested_actions: List[str]
    detected_at: float = field(default_factory=time.time)


@dataclass
class OptimizationSuggestion:
    """优化建议"""
    category: str
    priority: str  # high, medium, low
    title: str
    description: str
    expected_improvement: str
    implementation_complexity: str  # simple, moderate, complex
    estimated_effort_hours: int
    prerequisites: List[str] = field(default_factory=list)


class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self, max_history_size: int = 10000):
        self.max_history_size = max_history_size
        
        # 性能数据存储
        self.metrics_history: deque = deque(maxlen=max_history_size)
        self.operation_stats: Dict[str, List[PerformanceMetric]] = defaultdict(list)
        
        # 统计数据
        self.response_time_stats: Dict[str, ResponseTimeStats] = {}
        self.throughput_stats = ThroughputStats()
        self.resource_stats = ResourceStats()
        
        # 瓶颈和建议
        self.detected_bottlenecks: List[PerformanceBottleneck] = []
        self.optimization_suggestions: List[OptimizationSuggestion] = []
        
        # 分析配置
        self.analysis_window_minutes = 5  # 分析时间窗口
        self.slow_operation_threshold_ms = 1000  # 慢操作阈值
        self.high_cpu_threshold = 80.0  # 高CPU使用率阈值
        self.high_memory_threshold = 80.0  # 高内存使用率阈值
        
        # 运行时状态
        self.is_analyzing = False
        self.last_analysis_time = 0.0
        self.analysis_lock = threading.Lock()
        
        logger.info("性能分析器已初始化")
    
    def record_metric(self, metric: PerformanceMetric):
        """记录性能指标"""
        with self.analysis_lock:
            self.metrics_history.append(metric)
            self.operation_stats[metric.operation].append(metric)
            
            # 限制每个操作的历史记录数量
            if len(self.operation_stats[metric.operation]) > 1000:
                self.operation_stats[metric.operation] = self.operation_stats[metric.operation][-500:]
    
    async def analyze_performance(self) -> Dict[str, Any]:
        """执行性能分析"""
        if self.is_analyzing:
            logger.debug("性能分析正在进行中，跳过")
            return {}
        
        self.is_analyzing = True
        try:
            analysis_start = time.time()
            
            # 获取分析窗口内的数据
            window_metrics = self._get_window_metrics()
            
            if not window_metrics:
                logger.debug("没有足够的性能数据进行分析")
                return {}
            
            # 执行各项分析
            response_analysis = await self._analyze_response_times(window_metrics)
            throughput_analysis = await self._analyze_throughput(window_metrics)
            resource_analysis = await self._analyze_resource_usage(window_metrics)
            error_analysis = await self._analyze_errors(window_metrics)
            
            # 检测性能瓶颈
            bottlenecks = await self._detect_bottlenecks(window_metrics)
            
            # 生成优化建议
            suggestions = await self._generate_suggestions(bottlenecks)
            
            analysis_time = time.time() - analysis_start
            self.last_analysis_time = time.time()
            
            return {
                "analysis_timestamp": datetime.now().isoformat(),
                "analysis_duration_ms": analysis_time * 1000,
                "metrics_analyzed": len(window_metrics),
                "response_times": response_analysis,
                "throughput": throughput_analysis,
                "resource_usage": resource_analysis,
                "errors": error_analysis,
                "bottlenecks": [self._bottleneck_to_dict(b) for b in bottlenecks],
                "optimization_suggestions": [self._suggestion_to_dict(s) for s in suggestions],
                "overall_performance_score": self._calculate_performance_score()
            }
            
        finally:
            self.is_analyzing = False
    
    def _get_window_metrics(self) -> List[PerformanceMetric]:
        """获取分析窗口内的指标"""
        current_time = time.time()
        window_start = current_time - (self.analysis_window_minutes * 60)
        
        return [
            metric for metric in self.metrics_history
            if metric.timestamp >= window_start
        ]
    
    async def _analyze_response_times(self, metrics: List[PerformanceMetric]) -> Dict[str, Any]:
        """分析响应时间"""
        operation_times = defaultdict(list)
        
        # 按操作分组响应时间
        for metric in metrics:
            operation_times[metric.operation].append(metric.response_time_ms)
        
        analysis_result = {}
        
        for operation, times in operation_times.items():
            if not times:
                continue
            
            # 计算统计指标
            stats = ResponseTimeStats()
            stats.count = len(times)
            stats.total_time = sum(times)
            stats.min_time = min(times)
            stats.max_time = max(times)
            stats.avg_time = statistics.mean(times)
            
            if len(times) > 1:
                stats.std_dev = statistics.stdev(times)
            
            # 计算百分位数
            sorted_times = sorted(times)
            stats.p50 = self._percentile(sorted_times, 50)
            stats.p90 = self._percentile(sorted_times, 90)
            stats.p95 = self._percentile(sorted_times, 95)
            stats.p99 = self._percentile(sorted_times, 99)
            
            self.response_time_stats[operation] = stats
            
            analysis_result[operation] = {
                "count": stats.count,
                "avg_ms": round(stats.avg_time, 2),
                "min_ms": round(stats.min_time, 2),
                "max_ms": round(stats.max_time, 2),
                "p50_ms": round(stats.p50, 2),
                "p90_ms": round(stats.p90, 2),
                "p95_ms": round(stats.p95, 2),
                "p99_ms": round(stats.p99, 2),
                "std_dev": round(stats.std_dev, 2),
                "slow_operations": len([t for t in times if t > self.slow_operation_threshold_ms])
            }
        
        return analysis_result
    
    async def _analyze_throughput(self, metrics: List[PerformanceMetric]) -> Dict[str, Any]:
        """分析吞吐量"""
        if not metrics:
            return {}
        
        # 计算时间窗口
        window_seconds = self.analysis_window_minutes * 60
        
        # 总请求数和成功请求数
        total_requests = len(metrics)
        successful_requests = len([m for m in metrics if m.success])
        
        # 计算RPS和成功率
        rps = total_requests / window_seconds if window_seconds > 0 else 0
        success_rate = successful_requests / total_requests if total_requests > 0 else 0
        
        # 按时间段分析吞吐量变化
        time_buckets = defaultdict(int)
        bucket_size = 60  # 1分钟为一个时间桶
        
        for metric in metrics:
            bucket = int(metric.timestamp // bucket_size) * bucket_size
            time_buckets[bucket] += 1
        
        # 计算吞吐量趋势
        bucket_values = list(time_buckets.values())
        avg_throughput = statistics.mean(bucket_values) if bucket_values else 0
        
        self.throughput_stats = ThroughputStats(
            rps=rps,
            success_rate=success_rate
        )
        
        return {
            "requests_per_second": round(rps, 2),
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "success_rate": round(success_rate * 100, 2),
            "avg_throughput_per_minute": round(avg_throughput, 2),
            "throughput_stability": self._calculate_throughput_stability(bucket_values)
        }
    
    async def _analyze_resource_usage(self, metrics: List[PerformanceMetric]) -> Dict[str, Any]:
        """分析资源使用"""
        if not metrics:
            return {}
        
        cpu_values = [m.cpu_usage for m in metrics if m.cpu_usage > 0]
        memory_values = [m.memory_usage for m in metrics if m.memory_usage > 0]
        
        analysis = {}
        
        if cpu_values:
            analysis["cpu"] = {
                "avg_percent": round(statistics.mean(cpu_values), 2),
                "max_percent": round(max(cpu_values), 2),
                "min_percent": round(min(cpu_values), 2),
                "high_usage_periods": len([v for v in cpu_values if v > self.high_cpu_threshold])
            }
        
        if memory_values:
            analysis["memory"] = {
                "avg_percent": round(statistics.mean(memory_values), 2),
                "max_percent": round(max(memory_values), 2),
                "min_percent": round(min(memory_values), 2),
                "high_usage_periods": len([v for v in memory_values if v > self.high_memory_threshold])
            }
        
        return analysis
    
    async def _analyze_errors(self, metrics: List[PerformanceMetric]) -> Dict[str, Any]:
        """分析错误"""
        error_metrics = [m for m in metrics if not m.success]
        
        if not error_metrics:
            return {"total_errors": 0, "error_rate": 0.0}
        
        # 按错误类型分组
        error_types = defaultdict(int)
        for metric in error_metrics:
            error_type = metric.error_type or "unknown"
            error_types[error_type] += 1
        
        total_requests = len(metrics)
        error_rate = len(error_metrics) / total_requests if total_requests > 0 else 0
        
        return {
            "total_errors": len(error_metrics),
            "error_rate": round(error_rate * 100, 2),
            "error_types": dict(error_types),
            "most_common_error": max(error_types.items(), key=lambda x: x[1]) if error_types else None
        }
    
    async def _detect_bottlenecks(self, metrics: List[PerformanceMetric]) -> List[PerformanceBottleneck]:
        """检测性能瓶颈"""
        bottlenecks = []
        
        # 检测慢操作瓶颈
        slow_operations = defaultdict(list)
        for metric in metrics:
            if metric.response_time_ms > self.slow_operation_threshold_ms:
                slow_operations[metric.operation].append(metric)
        
        for operation, slow_metrics in slow_operations.items():
            if len(slow_metrics) > len(metrics) * 0.1:  # 超过10%的请求是慢操作
                bottleneck = PerformanceBottleneck(
                    type=BottleneckType.UNKNOWN,
                    severity=PerformanceLevel.POOR,
                    component=operation,
                    description=f"操作 '{operation}' 响应时间过长",
                    impact_score=len(slow_metrics) / len(metrics),
                    suggested_actions=[
                        "检查操作逻辑是否有优化空间",
                        "增加缓存机制",
                        "考虑异步处理",
                        "检查数据库查询效率"
                    ]
                )
                bottlenecks.append(bottleneck)
        
        # 检测高CPU使用率
        cpu_values = [m.cpu_usage for m in metrics if m.cpu_usage > 0]
        if cpu_values:
            avg_cpu = statistics.mean(cpu_values)
            if avg_cpu > self.high_cpu_threshold:
                bottleneck = PerformanceBottleneck(
                    type=BottleneckType.CPU_BOUND,
                    severity=PerformanceLevel.CRITICAL if avg_cpu > 90 else PerformanceLevel.POOR,
                    component="system",
                    description=f"CPU使用率过高: {avg_cpu:.1f}%",
                    impact_score=min(avg_cpu / 100, 1.0),
                    suggested_actions=[
                        "检查CPU密集型操作",
                        "优化算法复杂度",
                        "考虑并行处理",
                        "增加服务器资源"
                    ]
                )
                bottlenecks.append(bottleneck)
        
        # 检测高内存使用率
        memory_values = [m.memory_usage for m in metrics if m.memory_usage > 0]
        if memory_values:
            avg_memory = statistics.mean(memory_values)
            if avg_memory > self.high_memory_threshold:
                bottleneck = PerformanceBottleneck(
                    type=BottleneckType.MEMORY_BOUND,
                    severity=PerformanceLevel.CRITICAL if avg_memory > 90 else PerformanceLevel.POOR,
                    component="system",
                    description=f"内存使用率过高: {avg_memory:.1f}%",
                    impact_score=min(avg_memory / 100, 1.0),
                    suggested_actions=[
                        "检查内存泄漏",
                        "优化数据结构",
                        "增加内存缓存策略",
                        "增加服务器内存"
                    ]
                )
                bottlenecks.append(bottleneck)
        
        self.detected_bottlenecks = bottlenecks
        return bottlenecks
    
    async def _generate_suggestions(self, bottlenecks: List[PerformanceBottleneck]) -> List[OptimizationSuggestion]:
        """生成优化建议"""
        suggestions = []
        
        # 基于瓶颈生成建议
        for bottleneck in bottlenecks:
            if bottleneck.type == BottleneckType.CPU_BOUND:
                suggestion = OptimizationSuggestion(
                    category="performance",
                    priority="high",
                    title="CPU性能优化",
                    description="优化CPU密集型操作以降低CPU使用率",
                    expected_improvement="CPU使用率降低15-30%",
                    implementation_complexity="moderate",
                    estimated_effort_hours=8,
                    prerequisites=["性能分析工具", "代码审查"]
                )
                suggestions.append(suggestion)
            
            elif bottleneck.type == BottleneckType.MEMORY_BOUND:
                suggestion = OptimizationSuggestion(
                    category="memory",
                    priority="high",
                    title="内存使用优化",
                    description="优化内存使用模式，减少内存占用",
                    expected_improvement="内存使用率降低20-40%",
                    implementation_complexity="moderate",
                    estimated_effort_hours=12,
                    prerequisites=["内存分析工具", "代码重构"]
                )
                suggestions.append(suggestion)
        
        # 基于响应时间统计生成建议
        slow_operations = [
            op for op, stats in self.response_time_stats.items()
            if stats.avg_time > self.slow_operation_threshold_ms
        ]
        
        if slow_operations:
            suggestion = OptimizationSuggestion(
                category="response_time",
                priority="medium",
                title="响应时间优化",
                description=f"优化慢操作: {', '.join(slow_operations[:3])}",
                expected_improvement="响应时间减少30-50%",
                implementation_complexity="simple",
                estimated_effort_hours=6,
                prerequisites=["性能测试环境"]
            )
            suggestions.append(suggestion)
        
        # 缓存优化建议
        if self.throughput_stats.rps > 50:  # 高吞吐量场景
            suggestion = OptimizationSuggestion(
                category="caching",
                priority="medium",
                title="缓存策略优化",
                description="实施智能缓存策略以提高响应速度",
                expected_improvement="响应时间减少40-60%",
                implementation_complexity="moderate",
                estimated_effort_hours=16,
                prerequisites=["缓存服务器", "缓存失效策略"]
            )
            suggestions.append(suggestion)
        
        self.optimization_suggestions = suggestions
        return suggestions
    
    def _percentile(self, sorted_values: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not sorted_values:
            return 0.0
        
        index = (percentile / 100) * (len(sorted_values) - 1)
        lower = int(index)
        upper = min(lower + 1, len(sorted_values) - 1)
        
        if lower == upper:
            return sorted_values[lower]
        
        weight = index - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
    
    def _calculate_throughput_stability(self, bucket_values: List[int]) -> float:
        """计算吞吐量稳定性"""
        if len(bucket_values) < 2:
            return 1.0
        
        # 使用变异系数评估稳定性
        mean_val = statistics.mean(bucket_values)
        if mean_val == 0:
            return 1.0
        
        std_val = statistics.stdev(bucket_values)
        cv = std_val / mean_val  # 变异系数
        
        # 转换为稳定性分数 (0-1, 越高越稳定)
        stability = max(0, 1 - cv)
        return round(stability, 3)
    
    def _calculate_performance_score(self) -> float:
        """计算综合性能分数"""
        scores = []
        
        # 响应时间分数 (基于平均响应时间)
        if self.response_time_stats:
            avg_response_times = [stats.avg_time for stats in self.response_time_stats.values()]
            avg_response_time = statistics.mean(avg_response_times)
            
            # 响应时间分数 (100ms=100分, 1000ms=50分, 2000ms+=0分)
            response_score = max(0, 100 - (avg_response_time - 100) / 19)
            scores.append(response_score)
        
        # 成功率分数
        success_score = self.throughput_stats.success_rate * 100
        scores.append(success_score)
        
        # 瓶颈影响分数
        if self.detected_bottlenecks:
            max_impact = max(b.impact_score for b in self.detected_bottlenecks)
            bottleneck_score = (1 - max_impact) * 100
        else:
            bottleneck_score = 100
        scores.append(bottleneck_score)
        
        # 综合分数
        if scores:
            return round(statistics.mean(scores), 1)
        return 0.0
    
    def _bottleneck_to_dict(self, bottleneck: PerformanceBottleneck) -> Dict[str, Any]:
        """将瓶颈转换为字典"""
        return {
            "type": bottleneck.type.value,
            "severity": bottleneck.severity.value,
            "component": bottleneck.component,
            "description": bottleneck.description,
            "impact_score": round(bottleneck.impact_score, 3),
            "suggested_actions": bottleneck.suggested_actions,
            "detected_at": datetime.fromtimestamp(bottleneck.detected_at).isoformat()
        }
    
    def _suggestion_to_dict(self, suggestion: OptimizationSuggestion) -> Dict[str, Any]:
        """将优化建议转换为字典"""
        return {
            "category": suggestion.category,
            "priority": suggestion.priority,
            "title": suggestion.title,
            "description": suggestion.description,
            "expected_improvement": suggestion.expected_improvement,
            "implementation_complexity": suggestion.implementation_complexity,
            "estimated_effort_hours": suggestion.estimated_effort_hours,
            "prerequisites": suggestion.prerequisites
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        return {
            "last_analysis": datetime.fromtimestamp(self.last_analysis_time).isoformat() if self.last_analysis_time else None,
            "metrics_count": len(self.metrics_history),
            "operations_monitored": len(self.operation_stats),
            "active_bottlenecks": len(self.detected_bottlenecks),
            "optimization_suggestions": len(self.optimization_suggestions),
            "overall_performance_score": self._calculate_performance_score(),
            "throughput": {
                "rps": self.throughput_stats.rps,
                "success_rate": self.throughput_stats.success_rate * 100
            }
        }
    
    def clear_history(self):
        """清除历史数据"""
        with self.analysis_lock:
            self.metrics_history.clear()
            self.operation_stats.clear()
            self.response_time_stats.clear()
            self.detected_bottlenecks.clear()
            self.optimization_suggestions.clear()
        
        logger.info("性能分析器历史数据已清除") 