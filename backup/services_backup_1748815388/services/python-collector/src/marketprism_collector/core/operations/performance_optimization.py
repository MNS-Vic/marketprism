"""
性能优化引擎 - Week 5 Day 8
提供应用性能分析、系统瓶颈识别、优化建议生成等功能
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor
import json
import statistics
import random
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceMetricType(Enum):
    """性能指标类型"""
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    CPU_UTILIZATION = "cpu_utilization"
    MEMORY_UTILIZATION = "memory_utilization"
    DISK_IO = "disk_io"
    NETWORK_IO = "network_io"
    DATABASE_QUERY_TIME = "db_query_time"
    CACHE_HIT_RATE = "cache_hit_rate"
    CONCURRENT_USERS = "concurrent_users"


class BottleneckType(Enum):
    """瓶颈类型"""
    CPU_BOUND = "cpu_bound"
    MEMORY_BOUND = "memory_bound"
    IO_BOUND = "io_bound"
    NETWORK_BOUND = "network_bound"
    DATABASE_BOUND = "database_bound"
    CACHE_BOUND = "cache_bound"
    ALGORITHM_BOUND = "algorithm_bound"
    CONCURRENCY_BOUND = "concurrency_bound"


class OptimizationType(Enum):
    """优化类型"""
    CODE_OPTIMIZATION = "code_optimization"
    CACHING = "caching"
    DATABASE_OPTIMIZATION = "database_optimization"
    SCALING = "scaling"
    LOAD_BALANCING = "load_balancing"
    CDN = "cdn"
    COMPRESSION = "compression"
    ASYNC_PROCESSING = "async_processing"


class TestType(Enum):
    """测试类型"""
    LOAD_TEST = "load_test"
    STRESS_TEST = "stress_test"
    SPIKE_TEST = "spike_test"
    ENDURANCE_TEST = "endurance_test"
    VOLUME_TEST = "volume_test"


@dataclass
class PerformanceMetric:
    """性能指标"""
    metric_id: str
    metric_type: PerformanceMetricType
    value: float
    timestamp: datetime
    source: str
    tags: Dict[str, str] = field(default_factory=dict)
    baseline_value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class BottleneckAnalysis:
    """瓶颈分析"""
    analysis_id: str
    bottleneck_type: BottleneckType
    severity: str  # low, medium, high, critical
    affected_components: List[str]
    symptoms: List[str]
    impact_description: str
    confidence_score: float
    detected_at: datetime
    root_cause: str = ""
    contributing_factors: List[str] = field(default_factory=list)


@dataclass
class OptimizationRecommendation:
    """优化建议"""
    recommendation_id: str
    optimization_type: OptimizationType
    title: str
    description: str
    expected_improvement: str
    effort_level: str  # low, medium, high
    priority: int  # 1-5
    implementation_steps: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    roi_estimate: str = ""


@dataclass
class PerformanceTest:
    """性能测试"""
    test_id: str
    test_type: TestType
    target_system: str
    test_scenario: str
    configuration: Dict[str, Any]
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: Dict[str, Any] = field(default_factory=dict)
    baseline_comparison: Dict[str, float] = field(default_factory=dict)


@dataclass
class PerformanceBenchmark:
    """性能基准"""
    benchmark_id: str
    system_component: str
    metric_type: PerformanceMetricType
    baseline_value: float
    target_value: float
    current_value: float
    last_updated: datetime
    improvement_percentage: float = 0.0
    status: str = "tracking"  # tracking, achieved, degraded


@dataclass
class OptimizationPlan:
    """优化计划"""
    plan_id: str
    name: str
    target_system: str
    recommendations: List[str]  # recommendation_ids
    timeline: Dict[str, str]  # phase -> description
    budget: float
    expected_roi: float
    status: str = "draft"  # draft, approved, in_progress, completed
    progress: float = 0.0


class PerformanceOptimization:
    """性能优化引擎"""
    
    def __init__(self):
        self.performance_metrics: Dict[str, List[PerformanceMetric]] = {}
        self.bottleneck_analyses: Dict[str, BottleneckAnalysis] = {}
        self.optimization_recommendations: Dict[str, OptimizationRecommendation] = {}
        self.performance_tests: Dict[str, PerformanceTest] = {}
        self.performance_benchmarks: Dict[str, PerformanceBenchmark] = {}
        self.optimization_plans: Dict[str, OptimizationPlan] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 初始化默认配置
        self._initialize_default_configs()
        logger.info("性能优化引擎初始化完成")
    
    def _initialize_default_configs(self):
        """初始化默认配置"""
        
        # 创建默认性能基准
        self._create_default_benchmarks()
        
        # 生成示例性能数据
        self._generate_sample_performance_data()
        
        logger.info("默认配置初始化完成")
    
    def _create_default_benchmarks(self):
        """创建默认性能基准"""
        benchmarks = [
            PerformanceBenchmark(
                benchmark_id="api_response_time",
                system_component="marketprism-api",
                metric_type=PerformanceMetricType.RESPONSE_TIME,
                baseline_value=200.0,  # ms
                target_value=150.0,
                current_value=180.0,
                last_updated=datetime.now()
            ),
            PerformanceBenchmark(
                benchmark_id="api_throughput",
                system_component="marketprism-api",
                metric_type=PerformanceMetricType.THROUGHPUT,
                baseline_value=1000.0,  # req/s
                target_value=1500.0,
                current_value=1200.0,
                last_updated=datetime.now()
            ),
            PerformanceBenchmark(
                benchmark_id="db_query_time",
                system_component="marketprism-database",
                metric_type=PerformanceMetricType.DATABASE_QUERY_TIME,
                baseline_value=50.0,  # ms
                target_value=30.0,
                current_value=45.0,
                last_updated=datetime.now()
            ),
            PerformanceBenchmark(
                benchmark_id="cache_hit_rate",
                system_component="marketprism-cache",
                metric_type=PerformanceMetricType.CACHE_HIT_RATE,
                baseline_value=80.0,  # %
                target_value=95.0,
                current_value=85.0,
                last_updated=datetime.now()
            )
        ]
        
        for benchmark in benchmarks:
            self.performance_benchmarks[benchmark.benchmark_id] = benchmark
    
    def _generate_sample_performance_data(self):
        """生成示例性能数据"""
        metric_types = list(PerformanceMetricType)
        sources = ["api-service", "db-service", "cache-service", "queue-service"]
        
        base_time = datetime.now() - timedelta(hours=24)
        
        for i in range(200):  # 生成24小时的数据
            timestamp = base_time + timedelta(minutes=i * 7)  # 每7分钟一个数据点
            
            for metric_type in metric_types[:6]:  # 只生成前6种指标
                for source in sources[:2]:  # 只使用前2个源
                    value = self._generate_realistic_performance_value(metric_type, timestamp)
                    
                    metric = PerformanceMetric(
                        metric_id=f"{metric_type.value}_{source}_{i}",
                        metric_type=metric_type,
                        value=value,
                        timestamp=timestamp,
                        source=source,
                        tags={"environment": "production", "version": "v1.5.2"}
                    )
                    
                    key = f"{metric_type.value}_{source}"
                    if key not in self.performance_metrics:
                        self.performance_metrics[key] = []
                    self.performance_metrics[key].append(metric)
    
    def _generate_realistic_performance_value(self, metric_type: PerformanceMetricType, timestamp: datetime) -> float:
        """生成真实的性能数据"""
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        
        # 基础性能模式
        base_patterns = {
            PerformanceMetricType.RESPONSE_TIME: {"base": 100, "peak": 300, "factor": 1.5},
            PerformanceMetricType.THROUGHPUT: {"base": 500, "peak": 2000, "factor": 0.8},
            PerformanceMetricType.ERROR_RATE: {"base": 0.1, "peak": 5.0, "factor": 2.0},
            PerformanceMetricType.CPU_UTILIZATION: {"base": 30, "peak": 80, "factor": 1.2},
            PerformanceMetricType.MEMORY_UTILIZATION: {"base": 40, "peak": 85, "factor": 1.1},
            PerformanceMetricType.DATABASE_QUERY_TIME: {"base": 20, "peak": 100, "factor": 1.8}
        }
        
        pattern = base_patterns.get(metric_type, {"base": 50, "peak": 100, "factor": 1.0})
        
        # 工作时间模式
        if 9 <= hour <= 18 and day_of_week < 5:  # 工作日工作时间
            load_factor = 0.8 + 0.2 * (1 + abs(12 - hour) / 12)
        elif day_of_week >= 5:  # 周末
            load_factor = 0.3 + 0.2 * random.random()
        else:  # 非工作时间
            load_factor = 0.2 + 0.3 * random.random()
        
        # 添加随机波动
        noise = random.uniform(-0.1, 0.1)
        load_factor = max(0.1, min(1.0, load_factor + noise))
        
        # 计算具体值
        if metric_type in [PerformanceMetricType.RESPONSE_TIME, PerformanceMetricType.DATABASE_QUERY_TIME]:
            # 响应时间类指标：负载高时性能下降
            value = pattern["base"] + (pattern["peak"] - pattern["base"]) * load_factor
        elif metric_type == PerformanceMetricType.THROUGHPUT:
            # 吞吐量：负载高时增加，但有上限
            value = pattern["base"] + (pattern["peak"] - pattern["base"]) * min(load_factor, 0.9)
        elif metric_type == PerformanceMetricType.ERROR_RATE:
            # 错误率：负载高时增加
            value = pattern["base"] + (pattern["peak"] - pattern["base"]) * (load_factor ** 2)
        else:
            # 利用率类指标
            value = pattern["base"] + (pattern["peak"] - pattern["base"]) * load_factor
        
        return round(value, 2)
    
    def record_performance_metric(self, metric: PerformanceMetric) -> bool:
        """记录性能指标"""
        try:
            key = f"{metric.metric_type.value}_{metric.source}"
            
            if key not in self.performance_metrics:
                self.performance_metrics[key] = []
            
            self.performance_metrics[key].append(metric)
            
            # 保留最近1000个数据点
            if len(self.performance_metrics[key]) > 1000:
                self.performance_metrics[key] = self.performance_metrics[key][-1000:]
            
            # 异步进行性能分析
            self.executor.submit(self._analyze_performance_trends, metric)
            
            logger.debug(f"记录性能指标: {metric.metric_type.value} = {metric.value}")
            return True
            
        except Exception as e:
            logger.error(f"记录性能指标失败: {e}")
            return False
    
    def _analyze_performance_trends(self, metric: PerformanceMetric):
        """分析性能趋势"""
        try:
            key = f"{metric.metric_type.value}_{metric.source}"
            metrics_data = self.performance_metrics.get(key, [])
            
            if len(metrics_data) < 20:
                return
            
            # 检测性能瓶颈
            self._detect_performance_bottlenecks(metric, metrics_data)
            
            # 更新性能基准
            self._update_performance_benchmarks(metric)
            
            # 生成优化建议
            self._generate_optimization_recommendations(metric, metrics_data)
            
        except Exception as e:
            logger.error(f"性能趋势分析失败: {e}")
    
    def _detect_performance_bottlenecks(self, metric: PerformanceMetric, metrics_data: List[PerformanceMetric]):
        """检测性能瓶颈"""
        try:
            recent_data = metrics_data[-20:]
            values = [m.value for m in recent_data]
            
            avg_value = statistics.mean(values)
            max_value = max(values)
            trend = self._calculate_trend(values)
            
            # 检测不同类型的瓶颈
            bottleneck_detected = False
            bottleneck_type = None
            severity = "low"
            symptoms = []
            
            if metric.metric_type == PerformanceMetricType.RESPONSE_TIME:
                if avg_value > 1000:  # 超过1秒
                    bottleneck_detected = True
                    bottleneck_type = BottleneckType.IO_BOUND
                    severity = "high" if avg_value > 2000 else "medium"
                    symptoms = ["响应时间过长", "用户体验下降"]
                    
            elif metric.metric_type == PerformanceMetricType.CPU_UTILIZATION:
                if avg_value > 80:
                    bottleneck_detected = True
                    bottleneck_type = BottleneckType.CPU_BOUND
                    severity = "critical" if avg_value > 95 else "high"
                    symptoms = ["CPU使用率过高", "处理能力不足"]
                    
            elif metric.metric_type == PerformanceMetricType.MEMORY_UTILIZATION:
                if avg_value > 85:
                    bottleneck_detected = True
                    bottleneck_type = BottleneckType.MEMORY_BOUND
                    severity = "critical" if avg_value > 95 else "high"
                    symptoms = ["内存使用率过高", "可能发生内存溢出"]
                    
            elif metric.metric_type == PerformanceMetricType.DATABASE_QUERY_TIME:
                if avg_value > 100:  # 超过100ms
                    bottleneck_detected = True
                    bottleneck_type = BottleneckType.DATABASE_BOUND
                    severity = "high" if avg_value > 500 else "medium"
                    symptoms = ["数据库查询慢", "数据访问瓶颈"]
            
            if bottleneck_detected and bottleneck_type:
                analysis_id = f"bottleneck_{bottleneck_type.value}_{metric.source}_{int(datetime.now().timestamp())}"
                
                analysis = BottleneckAnalysis(
                    analysis_id=analysis_id,
                    bottleneck_type=bottleneck_type,
                    severity=severity,
                    affected_components=[metric.source],
                    symptoms=symptoms,
                    impact_description=f"{metric.metric_type.value} 性能下降影响系统整体表现",
                    confidence_score=0.8,
                    detected_at=datetime.now(),
                    root_cause=f"{metric.metric_type.value} 指标异常",
                    contributing_factors=[f"平均值: {avg_value:.2f}", f"趋势: {trend}"]
                )
                
                self.bottleneck_analyses[analysis_id] = analysis
                logger.warning(f"检测到性能瓶颈: {bottleneck_type.value} 在 {metric.source}")
                
        except Exception as e:
            logger.error(f"性能瓶颈检测失败: {e}")
    
    def _calculate_trend(self, values: List[float]) -> str:
        """计算趋势"""
        if len(values) < 2:
            return "stable"
        
        # 简单的线性回归
        n = len(values)
        x_values = list(range(n))
        
        sum_x = sum(x_values)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(x_values, values))
        sum_x2 = sum(x * x for x in x_values)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    def _update_performance_benchmarks(self, metric: PerformanceMetric):
        """更新性能基准"""
        try:
            # 查找相关基准
            for benchmark in self.performance_benchmarks.values():
                if (benchmark.system_component == metric.source and 
                    benchmark.metric_type == metric.metric_type):
                    
                    benchmark.current_value = metric.value
                    benchmark.last_updated = datetime.now()
                    
                    # 计算改进百分比
                    if benchmark.baseline_value > 0:
                        if metric.metric_type in [PerformanceMetricType.RESPONSE_TIME, 
                                                PerformanceMetricType.DATABASE_QUERY_TIME,
                                                PerformanceMetricType.ERROR_RATE]:
                            # 对于这些指标，值越小越好
                            improvement = (benchmark.baseline_value - metric.value) / benchmark.baseline_value * 100
                        else:
                            # 对于这些指标，值越大越好
                            improvement = (metric.value - benchmark.baseline_value) / benchmark.baseline_value * 100
                        
                        benchmark.improvement_percentage = improvement
                        
                        # 更新状态
                        if metric.metric_type in [PerformanceMetricType.RESPONSE_TIME, 
                                                PerformanceMetricType.DATABASE_QUERY_TIME,
                                                PerformanceMetricType.ERROR_RATE]:
                            if metric.value <= benchmark.target_value:
                                benchmark.status = "achieved"
                            elif metric.value > benchmark.baseline_value:
                                benchmark.status = "degraded"
                            else:
                                benchmark.status = "tracking"
                        else:
                            if metric.value >= benchmark.target_value:
                                benchmark.status = "achieved"
                            elif metric.value < benchmark.baseline_value:
                                benchmark.status = "degraded"
                            else:
                                benchmark.status = "tracking"
                    
                    break
                    
        except Exception as e:
            logger.error(f"更新性能基准失败: {e}")
    
    def _generate_optimization_recommendations(self, metric: PerformanceMetric, metrics_data: List[PerformanceMetric]):
        """生成优化建议"""
        try:
            recommendations = []
            
            recent_data = metrics_data[-10:]
            avg_value = statistics.mean([m.value for m in recent_data])
            
            # 基于指标类型和当前值生成建议
            if metric.metric_type == PerformanceMetricType.RESPONSE_TIME and avg_value > 500:
                recommendations.extend([
                    {
                        "type": OptimizationType.CACHING,
                        "title": "实施缓存策略",
                        "description": "通过增加缓存层减少数据库查询和计算开销",
                        "improvement": "响应时间可减少30-50%",
                        "effort": "medium",
                        "priority": 2
                    },
                    {
                        "type": OptimizationType.DATABASE_OPTIMIZATION,
                        "title": "优化数据库查询",
                        "description": "分析慢查询，添加索引，优化SQL语句",
                        "improvement": "查询性能提升40-60%",
                        "effort": "high",
                        "priority": 1
                    }
                ])
            
            elif metric.metric_type == PerformanceMetricType.CPU_UTILIZATION and avg_value > 80:
                recommendations.extend([
                    {
                        "type": OptimizationType.CODE_OPTIMIZATION,
                        "title": "代码性能优化",
                        "description": "优化算法复杂度，减少不必要的计算",
                        "improvement": "CPU使用率降低20-30%",
                        "effort": "high",
                        "priority": 1
                    },
                    {
                        "type": OptimizationType.SCALING,
                        "title": "水平扩展",
                        "description": "增加服务器实例数量分担负载",
                        "improvement": "整体处理能力提升50-100%",
                        "effort": "low",
                        "priority": 2
                    }
                ])
            
            elif metric.metric_type == PerformanceMetricType.MEMORY_UTILIZATION and avg_value > 85:
                recommendations.extend([
                    {
                        "type": OptimizationType.CODE_OPTIMIZATION,
                        "title": "内存优化",
                        "description": "优化数据结构，减少内存泄漏，实施内存池",
                        "improvement": "内存使用率降低25-40%",
                        "effort": "high",
                        "priority": 1
                    }
                ])
            
            elif metric.metric_type == PerformanceMetricType.DATABASE_QUERY_TIME and avg_value > 100:
                recommendations.extend([
                    {
                        "type": OptimizationType.DATABASE_OPTIMIZATION,
                        "title": "数据库索引优化",
                        "description": "分析查询模式，添加复合索引，优化表结构",
                        "improvement": "查询时间减少50-70%",
                        "effort": "medium",
                        "priority": 1
                    },
                    {
                        "type": OptimizationType.CACHING,
                        "title": "数据库查询缓存",
                        "description": "实施查询结果缓存，减少重复查询",
                        "improvement": "数据库负载降低60-80%",
                        "effort": "low",
                        "priority": 2
                    }
                ])
            
            # 创建优化建议记录
            for rec_data in recommendations:
                rec_id = f"rec_{rec_data['type'].value}_{metric.source}_{uuid.uuid4().hex[:8]}"
                
                if rec_id not in self.optimization_recommendations:
                    recommendation = OptimizationRecommendation(
                        recommendation_id=rec_id,
                        optimization_type=rec_data["type"],
                        title=rec_data["title"],
                        description=rec_data["description"],
                        expected_improvement=rec_data["improvement"],
                        effort_level=rec_data["effort"],
                        priority=rec_data["priority"],
                        implementation_steps=self._get_implementation_steps(rec_data["type"]),
                        prerequisites=self._get_prerequisites(rec_data["type"]),
                        risks=self._get_optimization_risks(rec_data["type"])
                    )
                    
                    self.optimization_recommendations[rec_id] = recommendation
                    logger.info(f"生成优化建议: {rec_data['title']} for {metric.source}")
            
        except Exception as e:
            logger.error(f"生成优化建议失败: {e}")
    
    def _get_implementation_steps(self, optimization_type: OptimizationType) -> List[str]:
        """获取实施步骤"""
        steps_map = {
            OptimizationType.CACHING: [
                "分析缓存需求和访问模式",
                "选择合适的缓存技术",
                "设计缓存键策略",
                "实施缓存层",
                "配置缓存过期策略",
                "监控缓存效果"
            ],
            OptimizationType.DATABASE_OPTIMIZATION: [
                "分析慢查询日志",
                "识别缺失索引",
                "优化SQL语句",
                "添加必要索引",
                "测试性能改进",
                "部署到生产环境"
            ],
            OptimizationType.CODE_OPTIMIZATION: [
                "性能分析和profiling",
                "识别性能热点",
                "优化算法和数据结构",
                "代码重构",
                "单元测试验证",
                "性能测试确认"
            ],
            OptimizationType.SCALING: [
                "评估扩展需求",
                "设计负载均衡策略",
                "配置自动扩展",
                "测试扩展效果",
                "监控扩展性能"
            ]
        }
        
        return steps_map.get(optimization_type, ["制定详细实施计划"])
    
    def _get_prerequisites(self, optimization_type: OptimizationType) -> List[str]:
        """获取前置条件"""
        prereq_map = {
            OptimizationType.CACHING: ["缓存基础设施", "监控系统"],
            OptimizationType.DATABASE_OPTIMIZATION: ["数据库访问权限", "测试环境"],
            OptimizationType.CODE_OPTIMIZATION: ["性能分析工具", "开发环境"],
            OptimizationType.SCALING: ["云基础设施", "负载均衡器"]
        }
        
        return prereq_map.get(optimization_type, [])
    
    def _get_optimization_risks(self, optimization_type: OptimizationType) -> List[str]:
        """获取优化风险"""
        risk_map = {
            OptimizationType.CACHING: ["缓存一致性问题", "内存使用增加"],
            OptimizationType.DATABASE_OPTIMIZATION: ["索引维护开销", "锁竞争"],
            OptimizationType.CODE_OPTIMIZATION: ["引入新bug", "向后兼容性"],
            OptimizationType.SCALING: ["成本增加", "复杂性提升"]
        }
        
        return risk_map.get(optimization_type, ["实施风险"])
    
    def create_performance_test(self, test_type: TestType, target_system: str, 
                              scenario: str, config: Dict[str, Any]) -> str:
        """创建性能测试"""
        try:
            test_id = f"test_{test_type.value}_{target_system}_{uuid.uuid4().hex[:8]}"
            
            test = PerformanceTest(
                test_id=test_id,
                test_type=test_type,
                target_system=target_system,
                test_scenario=scenario,
                configuration=config
            )
            
            self.performance_tests[test_id] = test
            
            # 异步执行测试
            self.executor.submit(self._execute_performance_test, test)
            
            logger.info(f"创建性能测试: {test_id}")
            return test_id
            
        except Exception as e:
            logger.error(f"创建性能测试失败: {e}")
            return ""
    
    def _execute_performance_test(self, test: PerformanceTest):
        """执行性能测试"""
        try:
            test.status = "running"
            test.started_at = datetime.now()
            
            logger.info(f"执行性能测试: {test.test_id}")
            
            # 模拟测试执行
            import time
            time.sleep(random.uniform(10, 30))  # 模拟测试时间
            
            # 生成测试结果
            test.results = self._generate_test_results(test)
            test.status = "completed"
            test.completed_at = datetime.now()
            
            logger.info(f"性能测试完成: {test.test_id}")
            
        except Exception as e:
            test.status = "failed"
            test.results = {"error": str(e)}
            logger.error(f"性能测试失败: {e}")
    
    def _generate_test_results(self, test: PerformanceTest) -> Dict[str, Any]:
        """生成测试结果"""
        base_results = {
            "duration_seconds": random.uniform(300, 1800),
            "total_requests": random.randint(10000, 100000),
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time": random.uniform(100, 1000),
            "min_response_time": random.uniform(50, 200),
            "max_response_time": random.uniform(1000, 5000),
            "throughput_rps": random.uniform(100, 1000),
            "error_rate_percent": random.uniform(0.1, 5.0)
        }
        
        # 计算成功和失败请求数
        error_rate = base_results["error_rate_percent"] / 100
        base_results["failed_requests"] = int(base_results["total_requests"] * error_rate)
        base_results["successful_requests"] = base_results["total_requests"] - base_results["failed_requests"]
        
        # 根据测试类型调整结果
        if test.test_type == TestType.STRESS_TEST:
            base_results["max_response_time"] *= 2
            base_results["error_rate_percent"] *= 1.5
        elif test.test_type == TestType.SPIKE_TEST:
            base_results["max_response_time"] *= 3
            base_results["error_rate_percent"] *= 2
        
        return base_results
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        try:
            stats = {
                "total_metrics": sum(len(metrics) for metrics in self.performance_metrics.values()),
                "bottleneck_analyses": len(self.bottleneck_analyses),
                "optimization_recommendations": len(self.optimization_recommendations),
                "performance_tests": len(self.performance_tests),
                "performance_benchmarks": len(self.performance_benchmarks),
                "optimization_plans": len(self.optimization_plans)
            }
            
            # 统计瓶颈类型分布
            bottleneck_types = {}
            for analysis in self.bottleneck_analyses.values():
                bt = analysis.bottleneck_type.value
                bottleneck_types[bt] = bottleneck_types.get(bt, 0) + 1
            
            stats["bottleneck_type_distribution"] = bottleneck_types
            
            # 统计优化类型分布
            optimization_types = {}
            for rec in self.optimization_recommendations.values():
                ot = rec.optimization_type.value
                optimization_types[ot] = optimization_types.get(ot, 0) + 1
            
            stats["optimization_type_distribution"] = optimization_types
            
            # 统计测试状态
            test_status = {}
            for test in self.performance_tests.values():
                status = test.status
                test_status[status] = test_status.get(status, 0) + 1
            
            stats["test_status_distribution"] = test_status
            
            # 性能基准摘要
            benchmark_summary = {}
            for bench_id, benchmark in self.performance_benchmarks.items():
                benchmark_summary[bench_id] = {
                    "current_value": benchmark.current_value,
                    "target_value": benchmark.target_value,
                    "improvement_percentage": round(benchmark.improvement_percentage, 2),
                    "status": benchmark.status
                }
            
            stats["benchmark_summary"] = benchmark_summary
            
            return stats
            
        except Exception as e:
            logger.error(f"获取优化统计失败: {e}")
            return {}


# 生成示例性能数据的辅助函数
def generate_sample_performance_data(optimization_engine: PerformanceOptimization, count: int = 100):
    """生成示例性能数据"""
    metric_types = [
        PerformanceMetricType.RESPONSE_TIME,
        PerformanceMetricType.THROUGHPUT,
        PerformanceMetricType.CPU_UTILIZATION,
        PerformanceMetricType.MEMORY_UTILIZATION
    ]
    sources = ["api-service", "db-service", "cache-service"]
    
    base_time = datetime.now() - timedelta(hours=12)
    
    for i in range(count):
        timestamp = base_time + timedelta(minutes=i * 7)
        
        for metric_type in metric_types:
            for source in sources:
                value = optimization_engine._generate_realistic_performance_value(metric_type, timestamp)
                
                metric = PerformanceMetric(
                    metric_id=f"{metric_type.value}_{source}_{i}",
                    metric_type=metric_type,
                    value=value,
                    timestamp=timestamp,
                    source=source,
                    tags={"environment": "production", "version": "v1.5.2"}
                )
                
                optimization_engine.record_performance_metric(metric)