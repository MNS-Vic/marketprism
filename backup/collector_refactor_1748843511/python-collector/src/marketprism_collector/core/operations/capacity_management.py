"""
容量管理系统 - Week 5 Day 8
提供资源使用分析、容量规划预测、弹性伸缩策略等功能
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
import math

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """资源类型"""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    GPU = "gpu"
    STORAGE = "storage"
    DATABASE_CONNECTIONS = "db_connections"
    API_CALLS = "api_calls"
    BANDWIDTH = "bandwidth"


class ScalingDirection(Enum):
    """伸缩方向"""
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    SCALE_OUT = "scale_out"
    SCALE_IN = "scale_in"


class ScalingTrigger(Enum):
    """伸缩触发器"""
    METRIC_BASED = "metric_based"
    SCHEDULE_BASED = "schedule_based"
    PREDICTIVE = "predictive"
    MANUAL = "manual"
    EVENT_BASED = "event_based"


class CostOptimizationStrategy(Enum):
    """成本优化策略"""
    RIGHT_SIZING = "right_sizing"
    RESERVED_INSTANCES = "reserved_instances"
    SPOT_INSTANCES = "spot_instances"
    AUTO_SCHEDULING = "auto_scheduling"
    RESOURCE_POOLING = "resource_pooling"


@dataclass
class ResourceUsage:
    """资源使用情况"""
    resource_id: str
    resource_type: ResourceType
    current_usage: float
    capacity: float
    utilization_rate: float
    timestamp: datetime
    source: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    cost_per_hour: float = 0.0


@dataclass
class CapacityForecast:
    """容量预测"""
    forecast_id: str
    resource_type: ResourceType
    current_capacity: float
    predicted_usage: float
    forecast_period: int  # 预测天数
    confidence_level: float
    growth_rate: float
    seasonal_patterns: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    forecast_timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ScalingRule:
    """伸缩规则"""
    rule_id: str
    resource_type: ResourceType
    metric_name: str
    threshold_up: float
    threshold_down: float
    scale_up_amount: int
    scale_down_amount: int
    cooldown_period: int  # 冷却期(秒)
    enabled: bool = True
    trigger_type: ScalingTrigger = ScalingTrigger.METRIC_BASED
    conditions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScalingAction:
    """伸缩操作"""
    action_id: str
    rule_id: str
    direction: ScalingDirection
    resource_target: str
    amount: int
    reason: str
    triggered_at: datetime
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, executing, completed, failed
    result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourcePool:
    """资源池"""
    pool_id: str
    name: str
    resource_type: ResourceType
    total_capacity: float
    available_capacity: float
    allocated_resources: Dict[str, float] = field(default_factory=dict)
    allocation_strategy: str = "fair_share"  # fair_share, priority, demand_based
    cost_optimization: bool = True
    auto_scaling_enabled: bool = True


@dataclass
class CostAnalysis:
    """成本分析"""
    analysis_id: str
    resource_type: ResourceType
    current_cost: float
    projected_cost: float
    cost_trend: str  # increasing, decreasing, stable
    optimization_opportunities: List[str] = field(default_factory=list)
    potential_savings: float = 0.0
    roi_recommendations: List[str] = field(default_factory=list)
    analysis_period: int = 30  # 分析周期(天)


@dataclass
class CapacityPlan:
    """容量规划计划"""
    plan_id: str
    name: str
    target_date: datetime
    resource_requirements: Dict[ResourceType, float] = field(default_factory=dict)
    budget_constraints: Dict[str, float] = field(default_factory=dict)
    growth_assumptions: Dict[str, float] = field(default_factory=dict)
    risk_factors: List[str] = field(default_factory=list)
    approval_status: str = "draft"  # draft, submitted, approved, rejected


class CapacityManagement:
    """容量管理系统"""
    
    def __init__(self):
        self.resource_usage: Dict[str, List[ResourceUsage]] = {}
        self.capacity_forecasts: Dict[str, CapacityForecast] = {}
        self.scaling_rules: Dict[str, ScalingRule] = {}
        self.scaling_actions: List[ScalingAction] = []
        self.resource_pools: Dict[str, ResourcePool] = {}
        self.cost_analyses: Dict[str, CostAnalysis] = {}
        self.capacity_plans: Dict[str, CapacityPlan] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 初始化默认配置
        self._initialize_default_configs()
        logger.info("容量管理系统初始化完成")
    
    def _initialize_default_configs(self):
        """初始化默认配置"""
        
        # 创建默认资源池
        self._create_default_resource_pools()
        
        # 创建默认伸缩规则
        self._create_default_scaling_rules()
        
        # 生成示例资源使用数据
        self._generate_sample_resource_data()
        
        logger.info("默认配置初始化完成")
    
    def _create_default_resource_pools(self):
        """创建默认资源池"""
        pools = [
            ResourcePool(
                pool_id="cpu_pool_production",
                name="生产环境CPU池",
                resource_type=ResourceType.CPU,
                total_capacity=1000.0,
                available_capacity=750.0,
                allocated_resources={
                    "marketprism-api": 200.0,
                    "marketprism-collector": 150.0,
                    "marketprism-frontend": 100.0
                }
            ),
            ResourcePool(
                pool_id="memory_pool_production",
                name="生产环境内存池",
                resource_type=ResourceType.MEMORY,
                total_capacity=2048.0,  # GB
                available_capacity=1500.0,
                allocated_resources={
                    "marketprism-api": 300.0,
                    "marketprism-collector": 200.0,
                    "marketprism-database": 250.0
                }
            ),
            ResourcePool(
                pool_id="storage_pool_production",
                name="生产环境存储池",
                resource_type=ResourceType.STORAGE,
                total_capacity=10240.0,  # GB
                available_capacity=6000.0,
                allocated_resources={
                    "marketprism-database": 2000.0,
                    "marketprism-logs": 1000.0,
                    "marketprism-backup": 1240.0
                }
            )
        ]
        
        for pool in pools:
            self.resource_pools[pool.pool_id] = pool
    
    def _create_default_scaling_rules(self):
        """创建默认伸缩规则"""
        rules = [
            ScalingRule(
                rule_id="cpu_auto_scale",
                resource_type=ResourceType.CPU,
                metric_name="cpu_utilization",
                threshold_up=80.0,
                threshold_down=30.0,
                scale_up_amount=2,
                scale_down_amount=1,
                cooldown_period=300,
                conditions={"min_instances": 2, "max_instances": 20}
            ),
            ScalingRule(
                rule_id="memory_auto_scale",
                resource_type=ResourceType.MEMORY,
                metric_name="memory_utilization",
                threshold_up=85.0,
                threshold_down=40.0,
                scale_up_amount=1,
                scale_down_amount=1,
                cooldown_period=600,
                conditions={"min_memory_gb": 4, "max_memory_gb": 128}
            ),
            ScalingRule(
                rule_id="api_calls_scale",
                resource_type=ResourceType.API_CALLS,
                metric_name="requests_per_second",
                threshold_up=1000.0,
                threshold_down=200.0,
                scale_up_amount=3,
                scale_down_amount=1,
                cooldown_period=180,
                trigger_type=ScalingTrigger.PREDICTIVE
            ),
            ScalingRule(
                rule_id="database_connections_scale",
                resource_type=ResourceType.DATABASE_CONNECTIONS,
                metric_name="active_connections",
                threshold_up=80.0,  # 百分比
                threshold_down=30.0,
                scale_up_amount=50,  # 增加50个连接
                scale_down_amount=25,
                cooldown_period=900
            )
        ]
        
        for rule in rules:
            self.scaling_rules[rule.rule_id] = rule
    
    def _generate_sample_resource_data(self):
        """生成示例资源使用数据"""
        resource_types = list(ResourceType)
        sources = ["prod-cluster-1", "prod-cluster-2", "staging-cluster", "test-cluster"]
        
        base_time = datetime.now() - timedelta(days=7)
        
        for i in range(500):  # 生成一周的数据
            timestamp = base_time + timedelta(hours=i * 0.5)
            
            for resource_type in resource_types[:5]:  # 只生成前5种资源类型的数据
                for source in sources[:2]:  # 只使用前2个源
                    usage = self._generate_realistic_usage(resource_type, timestamp)
                    
                    resource_usage = ResourceUsage(
                        resource_id=f"{resource_type.value}_{source}_{i}",
                        resource_type=resource_type,
                        current_usage=usage["current"],
                        capacity=usage["capacity"],
                        utilization_rate=usage["utilization"],
                        timestamp=timestamp,
                        source=source,
                        cost_per_hour=usage["cost"]
                    )
                    
                    key = f"{resource_type.value}_{source}"
                    if key not in self.resource_usage:
                        self.resource_usage[key] = []
                    self.resource_usage[key].append(resource_usage)
    
    def _generate_realistic_usage(self, resource_type: ResourceType, timestamp: datetime) -> Dict[str, float]:
        """生成真实的资源使用数据"""
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        
        # 基础使用模式
        base_patterns = {
            ResourceType.CPU: {"base": 40, "peak": 85, "capacity": 100, "cost": 0.05},
            ResourceType.MEMORY: {"base": 60, "peak": 90, "capacity": 100, "cost": 0.08},
            ResourceType.DISK: {"base": 30, "peak": 70, "capacity": 100, "cost": 0.03},
            ResourceType.NETWORK: {"base": 20, "peak": 80, "capacity": 100, "cost": 0.02},
            ResourceType.API_CALLS: {"base": 100, "peak": 2000, "capacity": 5000, "cost": 0.001}
        }
        
        pattern = base_patterns.get(resource_type, {"base": 50, "peak": 80, "capacity": 100, "cost": 0.05})
        
        # 工作时间模式 (9:00-18:00)
        if 9 <= hour <= 18 and day_of_week < 5:  # 工作日工作时间
            usage_factor = 0.7 + 0.3 * math.sin((hour - 9) / 9 * math.pi)
        elif day_of_week >= 5:  # 周末
            usage_factor = 0.3 + 0.2 * random.random()
        else:  # 非工作时间
            usage_factor = 0.2 + 0.3 * random.random()
        
        # 添加随机波动
        noise = random.uniform(-0.1, 0.1)
        usage_factor = max(0.1, min(1.0, usage_factor + noise))
        
        current_usage = pattern["base"] + (pattern["peak"] - pattern["base"]) * usage_factor
        capacity = pattern["capacity"]
        utilization = (current_usage / capacity) * 100
        cost = pattern["cost"] * (current_usage / capacity)
        
        return {
            "current": current_usage,
            "capacity": capacity,
            "utilization": utilization,
            "cost": cost
        }
    
    def record_resource_usage(self, usage: ResourceUsage) -> bool:
        """记录资源使用情况"""
        try:
            key = f"{usage.resource_type.value}_{usage.source}"
            
            if key not in self.resource_usage:
                self.resource_usage[key] = []
            
            self.resource_usage[key].append(usage)
            
            # 保留最近1000个数据点
            if len(self.resource_usage[key]) > 1000:
                self.resource_usage[key] = self.resource_usage[key][-1000:]
            
            # 异步处理容量分析
            self.executor.submit(self._analyze_capacity_trends, usage)
            
            logger.debug(f"记录资源使用: {usage.resource_type.value} = {usage.current_usage}")
            return True
            
        except Exception as e:
            logger.error(f"记录资源使用失败: {e}")
            return False
    
    def _analyze_capacity_trends(self, usage: ResourceUsage):
        """分析容量趋势"""
        try:
            key = f"{usage.resource_type.value}_{usage.source}"
            usage_data = self.resource_usage.get(key, [])
            
            if len(usage_data) < 10:
                return
            
            # 检查伸缩规则
            self._check_scaling_rules(usage)
            
            # 更新容量预测
            self._update_capacity_forecast(usage.resource_type, usage_data)
            
        except Exception as e:
            logger.error(f"容量趋势分析失败: {e}")
    
    def _check_scaling_rules(self, usage: ResourceUsage):
        """检查伸缩规则"""
        try:
            for rule in self.scaling_rules.values():
                if rule.resource_type != usage.resource_type or not rule.enabled:
                    continue
                
                # 检查是否需要伸缩
                if usage.utilization_rate >= rule.threshold_up:
                    self._trigger_scaling_action(rule, ScalingDirection.SCALE_UP, usage)
                elif usage.utilization_rate <= rule.threshold_down:
                    self._trigger_scaling_action(rule, ScalingDirection.SCALE_DOWN, usage)
                    
        except Exception as e:
            logger.error(f"检查伸缩规则失败: {e}")
    
    def _trigger_scaling_action(self, rule: ScalingRule, direction: ScalingDirection, usage: ResourceUsage):
        """触发伸缩操作"""
        try:
            # 检查冷却期
            last_action = None
            for action in reversed(self.scaling_actions):
                if action.rule_id == rule.rule_id:
                    last_action = action
                    break
            
            if last_action:
                cooldown_end = last_action.triggered_at + timedelta(seconds=rule.cooldown_period)
                if datetime.now() < cooldown_end:
                    logger.debug(f"伸缩规则在冷却期内: {rule.rule_id}")
                    return
            
            # 创建伸缩操作
            action_id = f"scale_{rule.rule_id}_{direction.value}_{int(datetime.now().timestamp())}"
            
            amount = rule.scale_up_amount if direction in [ScalingDirection.SCALE_UP, ScalingDirection.SCALE_OUT] else rule.scale_down_amount
            
            action = ScalingAction(
                action_id=action_id,
                rule_id=rule.rule_id,
                direction=direction,
                resource_target=usage.source,
                amount=amount,
                reason=f"{rule.metric_name} 达到阈值: {usage.utilization_rate:.2f}%",
                triggered_at=datetime.now()
            )
            
            self.scaling_actions.append(action)
            
            # 异步执行伸缩操作
            self.executor.submit(self._execute_scaling_action, action)
            
            logger.info(f"触发伸缩操作: {action_id}")
            
        except Exception as e:
            logger.error(f"触发伸缩操作失败: {e}")
    
    def _execute_scaling_action(self, action: ScalingAction):
        """执行伸缩操作"""
        try:
            action.status = "executing"
            action.executed_at = datetime.now()
            
            # 模拟伸缩操作执行
            logger.info(f"执行伸缩操作: {action.direction.value} {action.amount} 单位")
            
            # 模拟执行时间
            import time
            time.sleep(random.uniform(1, 3))
            
            action.status = "completed"
            action.completed_at = datetime.now()
            action.result = {
                "success": True,
                "new_capacity": action.amount,
                "execution_time": (action.completed_at - action.executed_at).total_seconds()
            }
            
            logger.info(f"伸缩操作完成: {action.action_id}")
            
        except Exception as e:
            action.status = "failed"
            action.result = {"success": False, "error": str(e)}
            logger.error(f"伸缩操作失败: {e}")
    
    def _update_capacity_forecast(self, resource_type: ResourceType, usage_data: List[ResourceUsage]):
        """更新容量预测"""
        try:
            if len(usage_data) < 50:  # 需要足够的数据点
                return
            
            # 计算趋势
            recent_data = usage_data[-50:]
            utilization_values = [u.utilization_rate for u in recent_data]
            
            # 简单的线性回归预测
            x_values = list(range(len(utilization_values)))
            n = len(x_values)
            
            sum_x = sum(x_values)
            sum_y = sum(utilization_values)
            sum_xy = sum(x * y for x, y in zip(x_values, utilization_values))
            sum_x2 = sum(x * x for x in x_values)
            
            # 计算趋势斜率
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            intercept = (sum_y - slope * sum_x) / n
            
            # 预测未来7天的使用率
            future_days = 7
            future_utilization = intercept + slope * (len(x_values) + future_days * 48)  # 48个半小时点
            
            # 计算增长率
            current_avg = statistics.mean(utilization_values[-10:])
            growth_rate = slope * 48 * 7 / current_avg if current_avg > 0 else 0  # 周增长率
            
            # 创建或更新预测
            forecast_id = f"forecast_{resource_type.value}"
            
            # 生成建议
            recommendations = []
            if future_utilization > 85:
                recommendations.append("建议增加资源容量")
                recommendations.append("考虑水平扩展")
            elif future_utilization < 30:
                recommendations.append("建议缩减资源以节约成本")
                recommendations.append("评估资源池整合机会")
            
            if growth_rate > 0.2:  # 增长率超过20%
                recommendations.append("资源增长过快，建议制定容量规划")
            
            forecast = CapacityForecast(
                forecast_id=forecast_id,
                resource_type=resource_type,
                current_capacity=recent_data[-1].capacity,
                predicted_usage=future_utilization,
                forecast_period=7,
                confidence_level=0.8,
                growth_rate=growth_rate,
                recommendations=recommendations
            )
            
            self.capacity_forecasts[forecast_id] = forecast
            
            logger.debug(f"更新容量预测: {resource_type.value}, 预测使用率: {future_utilization:.2f}%")
            
        except Exception as e:
            logger.error(f"更新容量预测失败: {e}")
    
    def generate_cost_analysis(self, resource_type: ResourceType, period_days: int = 30) -> str:
        """生成成本分析"""
        try:
            analysis_id = f"cost_analysis_{resource_type.value}_{int(datetime.now().timestamp())}"
            
            # 收集相关资源使用数据
            relevant_usage = []
            for key, usage_list in self.resource_usage.items():
                if resource_type.value in key:
                    relevant_usage.extend(usage_list)
            
            if not relevant_usage:
                logger.warning(f"没有找到 {resource_type.value} 的使用数据")
                return ""
            
            # 计算当前成本
            recent_usage = [u for u in relevant_usage if u.timestamp >= datetime.now() - timedelta(days=period_days)]
            current_cost = sum(u.cost_per_hour * 24 for u in recent_usage) / len(recent_usage) * period_days
            
            # 预测未来成本
            forecast = self.capacity_forecasts.get(f"forecast_{resource_type.value}")
            if forecast:
                growth_factor = 1 + forecast.growth_rate
                projected_cost = current_cost * growth_factor
            else:
                projected_cost = current_cost * 1.1  # 默认10%增长
            
            # 成本趋势
            if projected_cost > current_cost * 1.2:
                cost_trend = "increasing"
            elif projected_cost < current_cost * 0.8:
                cost_trend = "decreasing"
            else:
                cost_trend = "stable"
            
            # 优化建议
            optimization_opportunities = []
            potential_savings = 0.0
            
            if current_cost > 1000:  # 高成本资源
                optimization_opportunities.append("考虑预留实例以获得折扣")
                potential_savings += current_cost * 0.3
            
            avg_utilization = statistics.mean([u.utilization_rate for u in recent_usage])
            if avg_utilization < 50:
                optimization_opportunities.append("资源利用率较低，建议右调整")
                potential_savings += current_cost * 0.2
            
            if cost_trend == "increasing":
                optimization_opportunities.append("成本快速增长，建议容量优化")
            
            roi_recommendations = [
                "投资自动化伸缩以优化成本",
                "实施资源标记和成本分摊",
                "定期审查和优化资源配置"
            ]
            
            analysis = CostAnalysis(
                analysis_id=analysis_id,
                resource_type=resource_type,
                current_cost=current_cost,
                projected_cost=projected_cost,
                cost_trend=cost_trend,
                optimization_opportunities=optimization_opportunities,
                potential_savings=potential_savings,
                roi_recommendations=roi_recommendations,
                analysis_period=period_days
            )
            
            self.cost_analyses[analysis_id] = analysis
            
            logger.info(f"生成成本分析: {analysis_id}")
            return analysis_id
            
        except Exception as e:
            logger.error(f"生成成本分析失败: {e}")
            return ""
    
    def create_capacity_plan(self, name: str, target_date: datetime, requirements: Dict[ResourceType, float]) -> str:
        """创建容量规划计划"""
        try:
            plan_id = f"plan_{int(datetime.now().timestamp())}"
            
            # 基于当前趋势生成建议
            budget_constraints = {}
            growth_assumptions = {}
            risk_factors = []
            
            for resource_type, required_capacity in requirements.items():
                # 估算成本
                current_cost = 100  # 基础成本
                budget_constraints[resource_type.value] = current_cost * required_capacity
                
                # 增长假设
                forecast = self.capacity_forecasts.get(f"forecast_{resource_type.value}")
                if forecast:
                    growth_assumptions[resource_type.value] = forecast.growth_rate
                else:
                    growth_assumptions[resource_type.value] = 0.1  # 默认10%增长
                
                # 风险因素
                if required_capacity > 1000:
                    risk_factors.append(f"{resource_type.value} 容量需求过大")
                
                if growth_assumptions[resource_type.value] > 0.5:
                    risk_factors.append(f"{resource_type.value} 增长率过高")
            
            plan = CapacityPlan(
                plan_id=plan_id,
                name=name,
                target_date=target_date,
                resource_requirements=requirements,
                budget_constraints=budget_constraints,
                growth_assumptions=growth_assumptions,
                risk_factors=risk_factors
            )
            
            self.capacity_plans[plan_id] = plan
            
            logger.info(f"创建容量规划计划: {plan_id}")
            return plan_id
            
        except Exception as e:
            logger.error(f"创建容量规划计划失败: {e}")
            return ""
    
    def get_capacity_stats(self) -> Dict[str, Any]:
        """获取容量管理统计信息"""
        try:
            stats = {
                "total_resource_records": sum(len(usage_list) for usage_list in self.resource_usage.values()),
                "resource_pools": len(self.resource_pools),
                "scaling_rules": len(self.scaling_rules),
                "scaling_actions": len(self.scaling_actions),
                "capacity_forecasts": len(self.capacity_forecasts),
                "cost_analyses": len(self.cost_analyses),
                "capacity_plans": len(self.capacity_plans)
            }
            
            # 统计伸缩操作状态
            action_status_counts = {}
            for action in self.scaling_actions:
                status = action.status
                action_status_counts[status] = action_status_counts.get(status, 0) + 1
            
            stats["scaling_action_status"] = action_status_counts
            
            # 资源池利用率
            pool_utilization = {}
            for pool_id, pool in self.resource_pools.items():
                utilization = (pool.total_capacity - pool.available_capacity) / pool.total_capacity * 100
                pool_utilization[pool_id] = round(utilization, 2)
            
            stats["resource_pool_utilization"] = pool_utilization
            
            # 最新容量预测摘要
            forecast_summary = {}
            for forecast_id, forecast in self.capacity_forecasts.items():
                forecast_summary[forecast_id] = {
                    "predicted_usage": round(forecast.predicted_usage, 2),
                    "growth_rate": round(forecast.growth_rate * 100, 2),
                    "recommendations_count": len(forecast.recommendations)
                }
            
            stats["capacity_forecasts_summary"] = forecast_summary
            
            return stats
            
        except Exception as e:
            logger.error(f"获取容量统计失败: {e}")
            return {}


# 生成示例资源使用数据的辅助函数
def generate_sample_capacity_data(capacity_system: CapacityManagement, count: int = 100):
    """生成示例容量数据"""
    resource_types = [ResourceType.CPU, ResourceType.MEMORY, ResourceType.DISK, ResourceType.NETWORK]
    sources = ["prod-cluster-1", "prod-cluster-2", "staging-cluster"]
    
    base_time = datetime.now() - timedelta(hours=24)
    
    for i in range(count):
        timestamp = base_time + timedelta(minutes=i * 15)  # 每15分钟一个数据点
        
        for resource_type in resource_types:
            for source in sources:
                # 生成真实的使用模式
                hour = timestamp.hour
                if 9 <= hour <= 18:  # 工作时间高使用率
                    usage_factor = random.uniform(0.6, 0.9)
                else:  # 非工作时间低使用率
                    usage_factor = random.uniform(0.2, 0.5)
                
                if resource_type == ResourceType.CPU:
                    capacity = 100.0
                    current_usage = capacity * usage_factor
                    cost_per_hour = 0.05
                elif resource_type == ResourceType.MEMORY:
                    capacity = 64.0  # GB
                    current_usage = capacity * usage_factor
                    cost_per_hour = 0.08
                elif resource_type == ResourceType.DISK:
                    capacity = 1000.0  # GB
                    current_usage = capacity * usage_factor
                    cost_per_hour = 0.03
                else:  # NETWORK
                    capacity = 1000.0  # Mbps
                    current_usage = capacity * usage_factor
                    cost_per_hour = 0.02
                
                usage = ResourceUsage(
                    resource_id=f"{resource_type.value}_{source}_{i}",
                    resource_type=resource_type,
                    current_usage=current_usage,
                    capacity=capacity,
                    utilization_rate=(current_usage / capacity) * 100,
                    timestamp=timestamp,
                    source=source,
                    cost_per_hour=cost_per_hour
                )
                
                capacity_system.record_resource_usage(usage)