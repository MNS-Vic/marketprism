"""
MarketPrism 告警规则引擎

提供灵活的告警规则定义、评估和管理功能
"""

import re
import ast
import operator
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import structlog

from .alert_types import Alert, AlertSeverity, AlertCategory, AlertPriority


logger = structlog.get_logger(__name__)


class ConditionOperator(str, Enum):
    """条件操作符"""
    GT = ">"          # 大于
    GTE = ">="        # 大于等于
    LT = "<"          # 小于
    LTE = "<="        # 小于等于
    EQ = "=="         # 等于
    NEQ = "!="        # 不等于
    CONTAINS = "contains"     # 包含
    NOT_CONTAINS = "not_contains"  # 不包含
    REGEX = "regex"           # 正则匹配
    IN = "in"                 # 在列表中
    NOT_IN = "not_in"         # 不在列表中


class AggregationFunction(str, Enum):
    """聚合函数"""
    AVG = "avg"       # 平均值
    SUM = "sum"       # 求和
    MIN = "min"       # 最小值
    MAX = "max"       # 最大值
    COUNT = "count"   # 计数
    RATE = "rate"     # 变化率
    INCREASE = "increase"  # 增量


@dataclass
class AlertCondition:
    """告警条件"""
    metric_name: str
    operator: ConditionOperator
    threshold: Union[float, str, List]
    aggregation: Optional[AggregationFunction] = None
    time_window: int = 300  # 时间窗口（秒）
    labels: Dict[str, str] = field(default_factory=dict)
    
    def evaluate(self, metric_value: float, metric_labels: Dict[str, str] = None) -> bool:
        """评估条件"""
        # 检查标签匹配
        if self.labels and metric_labels:
            for key, value in self.labels.items():
                if metric_labels.get(key) != value:
                    return False
        
        # 评估条件
        return self._evaluate_condition(metric_value)
    
    def _evaluate_condition(self, value: float) -> bool:
        """评估具体条件"""
        ops = {
            ConditionOperator.GT: operator.gt,
            ConditionOperator.GTE: operator.ge,
            ConditionOperator.LT: operator.lt,
            ConditionOperator.LTE: operator.le,
            ConditionOperator.EQ: operator.eq,
            ConditionOperator.NEQ: operator.ne,
        }
        
        if self.operator in ops:
            return ops[self.operator](value, float(self.threshold))
        elif self.operator == ConditionOperator.IN:
            return value in self.threshold
        elif self.operator == ConditionOperator.NOT_IN:
            return value not in self.threshold
        elif self.operator == ConditionOperator.CONTAINS:
            return str(self.threshold) in str(value)
        elif self.operator == ConditionOperator.NOT_CONTAINS:
            return str(self.threshold) not in str(value)
        elif self.operator == ConditionOperator.REGEX:
            return bool(re.search(str(self.threshold), str(value)))
        
        return False


@dataclass
class AlertRule:
    """告警规则"""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    category: AlertCategory
    conditions: List[AlertCondition]
    duration: int = 300  # 持续时间（秒）
    enabled: bool = True
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    
    # 高级配置
    evaluation_interval: int = 60  # 评估间隔（秒）
    resolve_timeout: int = 300     # 解决超时（秒）
    max_alerts: int = 10           # 最大告警数量
    
    # 抑制配置
    inhibit_rules: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.conditions:
            raise ValueError("告警规则必须包含至少一个条件")
    
    def evaluate(self, metrics_data: Dict[str, Any]) -> bool:
        """评估告警规则"""
        if not self.enabled:
            return False
        
        # 评估所有条件（AND逻辑）
        for condition in self.conditions:
            metric_data = metrics_data.get(condition.metric_name)
            if not metric_data:
                return False
            
            # 获取指标值和标签
            metric_value = metric_data.get('value', 0)
            metric_labels = metric_data.get('labels', {})
            
            if not condition.evaluate(metric_value, metric_labels):
                return False
        
        return True
    
    def create_alert(self, metrics_data: Dict[str, Any]) -> Alert:
        """创建告警"""
        # 收集相关指标信息
        metric_info = {}
        for condition in self.conditions:
            if condition.metric_name in metrics_data:
                metric_info[condition.metric_name] = metrics_data[condition.metric_name]
        
        # 创建告警
        alert = Alert(
            name=self.name,
            description=self.description,
            severity=self.severity,
            category=self.category,
            labels=self.labels.copy(),
            metadata={
                'rule_id': self.id,
                'metrics': metric_info,
                'conditions': [
                    {
                        'metric': c.metric_name,
                        'operator': c.operator.value,
                        'threshold': c.threshold
                    }
                    for c in self.conditions
                ]
            }
        )
        
        # 添加注释
        for key, value in self.annotations.items():
            alert.labels[f"annotation_{key}"] = value
        
        return alert
    
    def get_priority(self) -> AlertPriority:
        """获取告警优先级"""
        return AlertPriority.from_severity(self.severity)


class AlertRuleEngine:
    """告警规则引擎"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.rules: Dict[str, AlertRule] = {}
        self.rule_states: Dict[str, Dict[str, Any]] = {}  # 规则状态跟踪
        self.metrics_cache: Dict[str, Any] = {}
        
        # 加载默认规则
        self._load_default_rules()
        
        logger.info("告警规则引擎初始化完成")
    
    def _load_default_rules(self) -> None:
        """加载默认告警规则"""
        default_rules = [
            # 系统资源告警
            AlertRule(
                id="high_memory_usage",
                name="内存使用率过高",
                description="系统内存使用率超过85%",
                severity=AlertSeverity.HIGH,
                category=AlertCategory.SYSTEM,
                conditions=[
                    AlertCondition(
                        metric_name="memory_usage_percent",
                        operator=ConditionOperator.GT,
                        threshold=85.0,
                        time_window=300
                    )
                ],
                duration=300,
                labels={"component": "system", "type": "resource"}
            ),
            
            AlertRule(
                id="high_cpu_usage",
                name="CPU使用率过高",
                description="系统CPU使用率超过80%",
                severity=AlertSeverity.HIGH,
                category=AlertCategory.SYSTEM,
                conditions=[
                    AlertCondition(
                        metric_name="cpu_usage_percent",
                        operator=ConditionOperator.GT,
                        threshold=80.0,
                        time_window=300
                    )
                ],
                duration=600,  # 10分钟持续时间
                labels={"component": "system", "type": "resource"}
            ),
            
            AlertRule(
                id="disk_space_low",
                name="磁盘空间不足",
                description="磁盘使用率超过90%",
                severity=AlertSeverity.CRITICAL,
                category=AlertCategory.SYSTEM,
                conditions=[
                    AlertCondition(
                        metric_name="disk_usage_percent",
                        operator=ConditionOperator.GT,
                        threshold=90.0,
                        time_window=60
                    )
                ],
                duration=60,
                labels={"component": "system", "type": "storage"}
            ),
            
            # 业务指标告警
            AlertRule(
                id="high_error_rate",
                name="错误率过高",
                description="API错误率超过5%",
                severity=AlertSeverity.HIGH,
                category=AlertCategory.BUSINESS,
                conditions=[
                    AlertCondition(
                        metric_name="api_error_rate",
                        operator=ConditionOperator.GT,
                        threshold=0.05,
                        time_window=300
                    )
                ],
                duration=300,
                labels={"component": "api", "type": "error"}
            ),
            
            AlertRule(
                id="slow_response_time",
                name="响应时间过慢",
                description="API平均响应时间超过2秒",
                severity=AlertSeverity.MEDIUM,
                category=AlertCategory.PERFORMANCE,
                conditions=[
                    AlertCondition(
                        metric_name="api_response_time_avg",
                        operator=ConditionOperator.GT,
                        threshold=2000.0,  # 毫秒
                        time_window=300
                    )
                ],
                duration=600,
                labels={"component": "api", "type": "performance"}
            ),
            
            # MarketPrism特定告警
            AlertRule(
                id="exchange_connection_down",
                name="交易所连接断开",
                description="与交易所的连接已断开",
                severity=AlertSeverity.CRITICAL,
                category=AlertCategory.BUSINESS,
                conditions=[
                    AlertCondition(
                        metric_name="exchange_connection_status",
                        operator=ConditionOperator.EQ,
                        threshold=0,  # 0表示断开
                        time_window=60
                    )
                ],
                duration=60,
                labels={"component": "data_collector", "type": "connection"}
            ),
            
            AlertRule(
                id="data_delay_high",
                name="数据延迟过高",
                description="市场数据延迟超过5秒",
                severity=AlertSeverity.HIGH,
                category=AlertCategory.BUSINESS,
                conditions=[
                    AlertCondition(
                        metric_name="market_data_delay_seconds",
                        operator=ConditionOperator.GT,
                        threshold=5.0,
                        time_window=300
                    )
                ],
                duration=300,
                labels={"component": "data_collector", "type": "latency"}
            ),
            
            AlertRule(
                id="nats_queue_backlog",
                name="NATS队列积压",
                description="NATS消息队列积压超过1000条",
                severity=AlertSeverity.MEDIUM,
                category=AlertCategory.SYSTEM,
                conditions=[
                    AlertCondition(
                        metric_name="nats_queue_size",
                        operator=ConditionOperator.GT,
                        threshold=1000,
                        time_window=300
                    )
                ],
                duration=300,
                labels={"component": "message_broker", "type": "queue"}
            )
        ]
        
        # 添加规则
        for rule in default_rules:
            self.add_rule(rule)
    
    def add_rule(self, rule: AlertRule) -> None:
        """添加告警规则"""
        self.rules[rule.id] = rule
        self.rule_states[rule.id] = {
            'last_evaluation': None,
            'last_triggered': None,
            'trigger_count': 0,
            'active_alerts': []
        }
        
        logger.info("添加告警规则", rule_id=rule.id, name=rule.name)
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除告警规则"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            del self.rule_states[rule_id]
            logger.info("移除告警规则", rule_id=rule_id)
            return True
        return False
    
    def update_rule(self, rule: AlertRule) -> bool:
        """更新告警规则"""
        if rule.id in self.rules:
            self.rules[rule.id] = rule
            logger.info("更新告警规则", rule_id=rule.id, name=rule.name)
            return True
        return False
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """获取告警规则"""
        return self.rules.get(rule_id)
    
    def list_rules(self, category: Optional[AlertCategory] = None, 
                  enabled_only: bool = False) -> List[AlertRule]:
        """列出告警规则"""
        rules = list(self.rules.values())
        
        if category:
            rules = [r for r in rules if r.category == category]
        
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        
        return rules
    
    def evaluate_rules(self, metrics_data: Dict[str, Any]) -> List[Alert]:
        """评估所有告警规则"""
        alerts = []
        current_time = datetime.now(timezone.utc)
        
        for rule_id, rule in self.rules.items():
            try:
                if self._should_evaluate_rule(rule, current_time):
                    if rule.evaluate(metrics_data):
                        # 检查持续时间
                        if self._check_duration(rule_id, current_time):
                            alert = rule.create_alert(metrics_data)
                            alerts.append(alert)
                            
                            # 更新规则状态
                            self.rule_states[rule_id]['last_triggered'] = current_time
                            self.rule_states[rule_id]['trigger_count'] += 1
                    
                    # 更新评估时间
                    self.rule_states[rule_id]['last_evaluation'] = current_time
                    
            except Exception as e:
                logger.error("告警规则评估失败", rule_id=rule_id, error=str(e))
        
        return alerts
    
    def _should_evaluate_rule(self, rule: AlertRule, current_time: datetime) -> bool:
        """判断是否应该评估规则"""
        if not rule.enabled:
            return False
        
        last_evaluation = self.rule_states[rule.id]['last_evaluation']
        if last_evaluation is None:
            return True
        
        # 检查评估间隔
        time_since_last = (current_time - last_evaluation).total_seconds()
        return time_since_last >= rule.evaluation_interval
    
    def _check_duration(self, rule_id: str, current_time: datetime) -> bool:
        """检查告警持续时间"""
        rule = self.rules[rule_id]
        last_triggered = self.rule_states[rule_id]['last_triggered']
        
        if last_triggered is None:
            # 第一次触发，记录时间但不立即告警
            self.rule_states[rule_id]['last_triggered'] = current_time
            return False
        
        # 检查是否满足持续时间要求
        duration = (current_time - last_triggered).total_seconds()
        return duration >= rule.duration
    
    def get_rule_statistics(self) -> Dict[str, Any]:
        """获取规则统计信息"""
        stats = {
            'total_rules': len(self.rules),
            'enabled_rules': len([r for r in self.rules.values() if r.enabled]),
            'rules_by_severity': {},
            'rules_by_category': {},
            'trigger_counts': {}
        }
        
        # 按严重程度统计
        for severity in AlertSeverity:
            count = len([r for r in self.rules.values() if r.severity == severity])
            stats['rules_by_severity'][severity.value] = count
        
        # 按类别统计
        for category in AlertCategory:
            count = len([r for r in self.rules.values() if r.category == category])
            stats['rules_by_category'][category.value] = count
        
        # 触发次数统计
        for rule_id, state in self.rule_states.items():
            stats['trigger_counts'][rule_id] = state['trigger_count']
        
        return stats
