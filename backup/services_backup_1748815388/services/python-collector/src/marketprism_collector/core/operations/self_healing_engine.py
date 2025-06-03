"""
故障自愈引擎 - Week 5 Day 8
提供自动化故障检测、智能根因分析、自动修复策略执行等功能
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor
import json
import random
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FaultType(Enum):
    """故障类型"""
    SERVICE_DOWN = "service_down"
    HIGH_LATENCY = "high_latency"
    MEMORY_LEAK = "memory_leak"
    CPU_SPIKE = "cpu_spike"
    DISK_FULL = "disk_full"
    NETWORK_ISSUE = "network_issue"
    DATABASE_ERROR = "database_error"
    AUTHENTICATION_FAILURE = "auth_failure"
    CONFIG_ERROR = "config_error"
    DEPENDENCY_FAILURE = "dependency_failure"


class FaultSeverity(Enum):
    """故障严重性"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class DiagnosticStatus(Enum):
    """诊断状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HealingAction(Enum):
    """修复操作类型"""
    RESTART_SERVICE = "restart_service"
    SCALE_UP = "scale_up"
    CLEAR_CACHE = "clear_cache"
    ROLLBACK = "rollback"
    FAILOVER = "failover"
    CLEAN_DISK = "clean_disk"
    RESET_CONNECTION = "reset_connection"
    UPDATE_CONFIG = "update_config"
    REFRESH_TOKEN = "refresh_token"
    CIRCUIT_BREAK = "circuit_break"


@dataclass
class FaultEvent:
    """故障事件"""
    event_id: str
    fault_type: FaultType
    severity: FaultSeverity
    source: str
    message: str
    detected_at: datetime
    resolved_at: Optional[datetime] = None
    symptoms: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""


@dataclass
class DiagnosticResult:
    """诊断结果"""
    diagnostic_id: str
    fault_event_id: str
    root_cause: str
    confidence_score: float
    evidence: List[str] = field(default_factory=list)
    contributing_factors: List[str] = field(default_factory=list)
    recommended_actions: List[HealingAction] = field(default_factory=list)
    status: DiagnosticStatus = DiagnosticStatus.PENDING
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class HealingTask:
    """修复任务"""
    task_id: str
    fault_event_id: str
    action: HealingAction
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, executing, completed, failed
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class HealingRule:
    """修复规则"""
    rule_id: str
    fault_type: FaultType
    conditions: Dict[str, Any]
    actions: List[HealingAction]
    priority: int = 1
    enabled: bool = True
    cooldown_period: int = 300  # 冷却期(秒)
    success_rate: float = 0.0
    execution_count: int = 0


@dataclass
class KnowledgeBase:
    """知识库条目"""
    kb_id: str
    fault_pattern: str
    solution: str
    success_rate: float
    usage_count: int = 0
    last_used: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)


class SelfHealingEngine:
    """故障自愈引擎"""
    
    def __init__(self):
        self.fault_events: Dict[str, FaultEvent] = {}
        self.diagnostic_results: Dict[str, DiagnosticResult] = {}
        self.healing_tasks: Dict[str, HealingTask] = {}
        self.healing_rules: Dict[str, HealingRule] = {}
        self.knowledge_base: Dict[str, KnowledgeBase] = {}
        self.active_healings: Dict[str, str] = {}  # source -> task_id
        self.executor = ThreadPoolExecutor(max_workers=6)
        
        # 初始化默认配置
        self._initialize_default_configs()
        logger.info("故障自愈引擎初始化完成")
    
    def _initialize_default_configs(self):
        """初始化默认配置"""
        
        # 创建默认修复规则
        self._create_default_healing_rules()
        
        # 创建知识库
        self._create_knowledge_base()
        
        logger.info("默认配置初始化完成")
    
    def _create_default_healing_rules(self):
        """创建默认修复规则"""
        rules = [
            HealingRule(
                rule_id="service_down_restart",
                fault_type=FaultType.SERVICE_DOWN,
                conditions={"downtime_seconds": {">=": 60}},
                actions=[HealingAction.RESTART_SERVICE],
                priority=1
            ),
            HealingRule(
                rule_id="high_memory_scale",
                fault_type=FaultType.MEMORY_LEAK,
                conditions={"memory_usage_percent": {">=": 90}},
                actions=[HealingAction.RESTART_SERVICE, HealingAction.SCALE_UP],
                priority=2
            ),
            HealingRule(
                rule_id="cpu_spike_handle",
                fault_type=FaultType.CPU_SPIKE,
                conditions={"cpu_usage_percent": {">=": 95}},
                actions=[HealingAction.SCALE_UP, HealingAction.CLEAR_CACHE],
                priority=2
            ),
            HealingRule(
                rule_id="disk_full_cleanup",
                fault_type=FaultType.DISK_FULL,
                conditions={"disk_usage_percent": {">=": 95}},
                actions=[HealingAction.CLEAN_DISK],
                priority=1
            ),
            HealingRule(
                rule_id="database_error_reset",
                fault_type=FaultType.DATABASE_ERROR,
                conditions={"error_rate": {">=": 50}},
                actions=[HealingAction.RESET_CONNECTION, HealingAction.FAILOVER],
                priority=1
            ),
            HealingRule(
                rule_id="auth_failure_refresh",
                fault_type=FaultType.AUTHENTICATION_FAILURE,
                conditions={"auth_error_count": {">=": 10}},
                actions=[HealingAction.REFRESH_TOKEN],
                priority=2
            )
        ]
        
        for rule in rules:
            self.healing_rules[rule.rule_id] = rule
    
    def _create_knowledge_base(self):
        """创建知识库"""
        kb_entries = [
            KnowledgeBase(
                kb_id="service_restart_pattern",
                fault_pattern="服务无响应且健康检查失败",
                solution="重启服务实例，验证配置文件，检查依赖服务状态",
                success_rate=0.85,
                tags=["service", "restart", "health_check"],
                examples=["API服务502错误", "数据库连接超时", "微服务不响应"]
            ),
            KnowledgeBase(
                kb_id="memory_leak_pattern",
                fault_pattern="内存使用持续增长且不释放",
                solution="重启服务，增加内存限制，检查代码内存泄漏",
                success_rate=0.78,
                tags=["memory", "leak", "performance"],
                examples=["Java堆内存溢出", "Python内存不释放", "缓存过度增长"]
            ),
            KnowledgeBase(
                kb_id="network_timeout_pattern",
                fault_pattern="网络请求超时或连接失败",
                solution="检查网络连接，重启网络服务，调整超时配置",
                success_rate=0.72,
                tags=["network", "timeout", "connectivity"],
                examples=["API调用超时", "数据库连接失败", "外部服务不可达"]
            ),
            KnowledgeBase(
                kb_id="disk_space_pattern",
                fault_pattern="磁盘空间不足影响服务运行",
                solution="清理临时文件，压缩日志文件，扩展存储空间",
                success_rate=0.92,
                tags=["disk", "storage", "cleanup"],
                examples=["日志文件过大", "临时文件堆积", "数据库文件增长"]
            ),
            KnowledgeBase(
                kb_id="config_error_pattern",
                fault_pattern="配置文件错误导致服务异常",
                solution="验证配置格式，回滚到上一版本配置，重新加载配置",
                success_rate=0.88,
                tags=["configuration", "validation", "rollback"],
                examples=["YAML格式错误", "数据库连接配置错误", "环境变量缺失"]
            )
        ]
        
        for entry in kb_entries:
            self.knowledge_base[entry.kb_id] = entry
    
    def detect_fault(self, fault_type: FaultType, source: str, message: str, 
                    severity: FaultSeverity = FaultSeverity.MEDIUM, 
                    symptoms: List[str] = None, 
                    metrics: Dict[str, float] = None,
                    context: Dict[str, Any] = None) -> str:
        """检测故障"""
        try:
            event_id = f"fault_{fault_type.value}_{source}_{uuid.uuid4().hex[:8]}"
            
            fault_event = FaultEvent(
                event_id=event_id,
                fault_type=fault_type,
                severity=severity,
                source=source,
                message=message,
                detected_at=datetime.now(),
                symptoms=symptoms or [],
                metrics=metrics or {},
                context=context or {}
            )
            
            self.fault_events[event_id] = fault_event
            
            # 异步开始诊断和修复流程
            self.executor.submit(self._process_fault_event, fault_event)
            
            logger.warning(f"检测到故障: {fault_type.value} 在 {source} - {message}")
            return event_id
            
        except Exception as e:
            logger.error(f"故障检测失败: {e}")
            return ""
    
    def _process_fault_event(self, fault_event: FaultEvent):
        """处理故障事件"""
        try:
            # 1. 进行根因分析
            diagnostic_result = self._diagnose_fault(fault_event)
            
            # 2. 查找匹配的修复规则
            matching_rules = self._find_matching_rules(fault_event)
            
            # 3. 执行自动修复
            if matching_rules:
                for rule in matching_rules:
                    self._execute_healing_actions(fault_event, rule, diagnostic_result)
            else:
                logger.warning(f"未找到匹配的修复规则: {fault_event.fault_type.value}")
                
        except Exception as e:
            logger.error(f"处理故障事件失败: {e}")
    
    def _diagnose_fault(self, fault_event: FaultEvent) -> DiagnosticResult:
        """诊断故障"""
        try:
            diagnostic_id = f"diag_{fault_event.event_id}"
            
            # 基于知识库进行诊断
            root_cause, confidence, evidence = self._analyze_with_knowledge_base(fault_event)
            
            # 分析贡献因素
            contributing_factors = self._identify_contributing_factors(fault_event)
            
            # 推荐修复操作
            recommended_actions = self._recommend_healing_actions(fault_event, root_cause)
            
            diagnostic_result = DiagnosticResult(
                diagnostic_id=diagnostic_id,
                fault_event_id=fault_event.event_id,
                root_cause=root_cause,
                confidence_score=confidence,
                evidence=evidence,
                contributing_factors=contributing_factors,
                recommended_actions=recommended_actions,
                status=DiagnosticStatus.COMPLETED,
                completed_at=datetime.now()
            )
            
            self.diagnostic_results[diagnostic_id] = diagnostic_result
            
            logger.info(f"故障诊断完成: {diagnostic_id}, 根因: {root_cause}")
            return diagnostic_result
            
        except Exception as e:
            logger.error(f"故障诊断失败: {e}")
            return DiagnosticResult(
                diagnostic_id=f"diag_{fault_event.event_id}",
                fault_event_id=fault_event.event_id,
                root_cause="诊断失败",
                confidence_score=0.0,
                status=DiagnosticStatus.FAILED
            )
    
    def _analyze_with_knowledge_base(self, fault_event: FaultEvent) -> tuple:
        """基于知识库分析故障"""
        best_match = None
        best_score = 0.0
        
        for kb_entry in self.knowledge_base.values():
            # 简单的模式匹配
            score = 0.0
            
            # 检查故障类型匹配
            if fault_event.fault_type.value in kb_entry.fault_pattern.lower():
                score += 0.5
            
            # 检查症状匹配
            for symptom in fault_event.symptoms:
                if symptom.lower() in kb_entry.fault_pattern.lower():
                    score += 0.3
            
            # 检查消息匹配
            if any(keyword in fault_event.message.lower() for keyword in kb_entry.tags):
                score += 0.2
            
            if score > best_score:
                best_score = score
                best_match = kb_entry
        
        if best_match:
            # 更新知识库使用统计
            best_match.usage_count += 1
            best_match.last_used = datetime.now()
            
            return (
                best_match.solution,
                min(best_score, 0.95),
                [f"匹配知识库模式: {best_match.fault_pattern}"]
            )
        else:
            return (
                f"未知{fault_event.fault_type.value}故障",
                0.3,
                ["基于故障类型的通用分析"]
            )
    
    def _identify_contributing_factors(self, fault_event: FaultEvent) -> List[str]:
        """识别贡献因素"""
        factors = []
        
        # 基于指标分析
        metrics = fault_event.metrics
        if metrics.get("cpu_usage", 0) > 80:
            factors.append("CPU使用率过高")
        if metrics.get("memory_usage", 0) > 85:
            factors.append("内存使用率过高")
        if metrics.get("error_rate", 0) > 5:
            factors.append("错误率异常")
        if metrics.get("response_time", 0) > 5000:
            factors.append("响应时间过长")
        
        # 基于时间分析
        hour = fault_event.detected_at.hour
        if 9 <= hour <= 18:
            factors.append("发生在业务高峰时段")
        elif 22 <= hour or hour <= 6:
            factors.append("发生在维护时段")
        
        # 基于上下文分析
        context = fault_event.context
        if context.get("recent_deployment"):
            factors.append("最近有部署活动")
        if context.get("traffic_spike"):
            factors.append("流量突增")
        
        return factors
    
    def _recommend_healing_actions(self, fault_event: FaultEvent, root_cause: str) -> List[HealingAction]:
        """推荐修复操作"""
        actions = []
        
        # 基于故障类型推荐
        fault_type_actions = {
            FaultType.SERVICE_DOWN: [HealingAction.RESTART_SERVICE],
            FaultType.HIGH_LATENCY: [HealingAction.SCALE_UP, HealingAction.CLEAR_CACHE],
            FaultType.MEMORY_LEAK: [HealingAction.RESTART_SERVICE, HealingAction.SCALE_UP],
            FaultType.CPU_SPIKE: [HealingAction.SCALE_UP],
            FaultType.DISK_FULL: [HealingAction.CLEAN_DISK],
            FaultType.NETWORK_ISSUE: [HealingAction.RESET_CONNECTION],
            FaultType.DATABASE_ERROR: [HealingAction.RESET_CONNECTION, HealingAction.FAILOVER],
            FaultType.AUTHENTICATION_FAILURE: [HealingAction.REFRESH_TOKEN],
            FaultType.CONFIG_ERROR: [HealingAction.UPDATE_CONFIG, HealingAction.ROLLBACK]
        }
        
        actions.extend(fault_type_actions.get(fault_event.fault_type, []))
        
        # 基于严重性调整
        if fault_event.severity == FaultSeverity.CRITICAL:
            if HealingAction.FAILOVER not in actions:
                actions.append(HealingAction.FAILOVER)
        
        return actions
    
    def _find_matching_rules(self, fault_event: FaultEvent) -> List[HealingRule]:
        """查找匹配的修复规则"""
        matching_rules = []
        
        for rule in self.healing_rules.values():
            if not rule.enabled:
                continue
                
            if rule.fault_type != fault_event.fault_type:
                continue
            
            # 检查条件匹配
            if self._evaluate_rule_conditions(rule, fault_event):
                matching_rules.append(rule)
        
        # 按优先级排序
        matching_rules.sort(key=lambda r: r.priority)
        
        return matching_rules
    
    def _evaluate_rule_conditions(self, rule: HealingRule, fault_event: FaultEvent) -> bool:
        """评估规则条件"""
        try:
            for condition_key, condition_value in rule.conditions.items():
                metric_value = fault_event.metrics.get(condition_key)
                
                if metric_value is None:
                    continue
                
                # 支持比较操作符
                if isinstance(condition_value, dict):
                    for operator, threshold in condition_value.items():
                        if operator == ">=":
                            if not (metric_value >= threshold):
                                return False
                        elif operator == "<=":
                            if not (metric_value <= threshold):
                                return False
                        elif operator == ">":
                            if not (metric_value > threshold):
                                return False
                        elif operator == "<":
                            if not (metric_value < threshold):
                                return False
                        elif operator == "==":
                            if not (abs(metric_value - threshold) < 0.001):
                                return False
                else:
                    # 直接比较
                    if metric_value != condition_value:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"评估规则条件失败: {e}")
            return False
    
    def _execute_healing_actions(self, fault_event: FaultEvent, rule: HealingRule, diagnostic_result: DiagnosticResult):
        """执行修复操作"""
        try:
            for action in rule.actions:
                task_id = f"heal_{action.value}_{fault_event.event_id}_{uuid.uuid4().hex[:8]}"
                
                healing_task = HealingTask(
                    task_id=task_id,
                    fault_event_id=fault_event.event_id,
                    action=action,
                    target=fault_event.source,
                    parameters={
                        "rule_id": rule.rule_id,
                        "diagnostic_id": diagnostic_result.diagnostic_id,
                        "severity": fault_event.severity.value
                    }
                )
                
                self.healing_tasks[task_id] = healing_task
                
                # 异步执行修复任务
                self.executor.submit(self._execute_healing_task, healing_task)
                
                logger.info(f"创建修复任务: {task_id} ({action.value})")
                
        except Exception as e:
            logger.error(f"执行修复操作失败: {e}")
    
    def _execute_healing_task(self, task: HealingTask):
        """执行修复任务"""
        try:
            task.status = "executing"
            task.started_at = datetime.now()
            
            logger.info(f"执行修复任务: {task.action.value} 目标: {task.target}")
            
            # 根据操作类型执行相应的修复逻辑
            success = self._perform_healing_action(task)
            
            if success:
                task.status = "completed"
                task.result = {"success": True, "message": f"{task.action.value} 执行成功"}
                logger.info(f"修复任务完成: {task.task_id}")
                
                # 验证修复效果
                self._verify_healing_result(task)
            else:
                task.status = "failed"
                task.result = {"success": False, "message": f"{task.action.value} 执行失败"}
                
                # 重试逻辑
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = "pending"
                    logger.warning(f"修复任务失败，准备重试: {task.task_id} (重试 {task.retry_count}/{task.max_retries})")
                    # 延迟重试
                    import time
                    time.sleep(30)
                    self._execute_healing_task(task)
                else:
                    logger.error(f"修复任务最终失败: {task.task_id}")
                    
        except Exception as e:
            task.status = "failed"
            task.result = {"success": False, "error": str(e)}
            logger.error(f"修复任务执行异常: {e}")
        
        finally:
            task.completed_at = datetime.now()
    
    def _perform_healing_action(self, task: HealingTask) -> bool:
        """执行具体的修复操作"""
        try:
            action = task.action
            target = task.target
            
            # 模拟修复操作执行
            import time
            time.sleep(random.uniform(1, 3))  # 模拟执行时间
            
            if action == HealingAction.RESTART_SERVICE:
                logger.info(f"重启服务: {target}")
                return random.random() > 0.1  # 90% 成功率
                
            elif action == HealingAction.SCALE_UP:
                logger.info(f"扩容服务: {target}")
                return random.random() > 0.15  # 85% 成功率
                
            elif action == HealingAction.CLEAR_CACHE:
                logger.info(f"清理缓存: {target}")
                return random.random() > 0.05  # 95% 成功率
                
            elif action == HealingAction.ROLLBACK:
                logger.info(f"回滚服务: {target}")
                return random.random() > 0.2  # 80% 成功率
                
            elif action == HealingAction.FAILOVER:
                logger.info(f"故障转移: {target}")
                return random.random() > 0.25  # 75% 成功率
                
            elif action == HealingAction.CLEAN_DISK:
                logger.info(f"清理磁盘: {target}")
                return random.random() > 0.05  # 95% 成功率
                
            elif action == HealingAction.RESET_CONNECTION:
                logger.info(f"重置连接: {target}")
                return random.random() > 0.1  # 90% 成功率
                
            elif action == HealingAction.UPDATE_CONFIG:
                logger.info(f"更新配置: {target}")
                return random.random() > 0.15  # 85% 成功率
                
            elif action == HealingAction.REFRESH_TOKEN:
                logger.info(f"刷新令牌: {target}")
                return random.random() > 0.05  # 95% 成功率
                
            elif action == HealingAction.CIRCUIT_BREAK:
                logger.info(f"熔断保护: {target}")
                return random.random() > 0.02  # 98% 成功率
                
            else:
                logger.warning(f"未知的修复操作: {action}")
                return False
                
        except Exception as e:
            logger.error(f"执行修复操作失败: {e}")
            return False
    
    def _verify_healing_result(self, task: HealingTask):
        """验证修复效果"""
        try:
            # 简单的修复效果验证
            fault_event = self.fault_events.get(task.fault_event_id)
            if fault_event and not fault_event.resolved_at:
                # 标记故障已解决
                fault_event.resolved_at = datetime.now()
                logger.info(f"故障已解决: {fault_event.event_id}")
                
        except Exception as e:
            logger.error(f"验证修复效果失败: {e}")
    
    def get_healing_stats(self) -> Dict[str, Any]:
        """获取修复统计信息"""
        try:
            stats = {
                "total_fault_events": len(self.fault_events),
                "resolved_faults": len([f for f in self.fault_events.values() if f.resolved_at]),
                "diagnostic_results": len(self.diagnostic_results),
                "healing_tasks": len(self.healing_tasks),
                "healing_rules": len(self.healing_rules),
                "knowledge_base_entries": len(self.knowledge_base)
            }
            
            # 统计故障类型分布
            fault_type_counts = {}
            for fault in self.fault_events.values():
                fault_type = fault.fault_type.value
                fault_type_counts[fault_type] = fault_type_counts.get(fault_type, 0) + 1
            
            stats["fault_type_distribution"] = fault_type_counts
            
            # 统计修复任务状态
            task_status_counts = {}
            for task in self.healing_tasks.values():
                status = task.status
                task_status_counts[status] = task_status_counts.get(status, 0) + 1
            
            stats["healing_task_status"] = task_status_counts
            
            # 计算修复成功率
            completed_tasks = [t for t in self.healing_tasks.values() if t.status == "completed"]
            if self.healing_tasks:
                success_rate = len(completed_tasks) / len(self.healing_tasks) * 100
            else:
                success_rate = 0
            
            stats["overall_success_rate"] = round(success_rate, 2)
            
            # 统计修复操作分布
            action_counts = {}
            for task in self.healing_tasks.values():
                action = task.action.value
                action_counts[action] = action_counts.get(action, 0) + 1
            
            stats["healing_action_distribution"] = action_counts
            
            return stats
            
        except Exception as e:
            logger.error(f"获取修复统计失败: {e}")
            return {}


# 生成示例故障事件的辅助函数
def generate_sample_faults(healing_engine: SelfHealingEngine, count: int = 20):
    """生成示例故障事件"""
    fault_types = list(FaultType)
    severities = list(FaultSeverity)
    sources = ["prod-api-01", "prod-db-01", "prod-cache-01", "prod-queue-01", "prod-frontend-01"]
    
    for i in range(count):
        fault_type = random.choice(fault_types)
        severity = random.choice(severities)
        source = random.choice(sources)
        
        # 根据故障类型生成相应的消息和指标
        if fault_type == FaultType.SERVICE_DOWN:
            message = f"{source} 服务无响应"
            metrics = {"downtime_seconds": random.uniform(30, 300)}
            symptoms = ["健康检查失败", "连接超时", "HTTP 502错误"]
        elif fault_type == FaultType.MEMORY_LEAK:
            message = f"{source} 内存使用率异常"
            metrics = {"memory_usage_percent": random.uniform(85, 98)}
            symptoms = ["内存持续增长", "GC频繁", "响应变慢"]
        elif fault_type == FaultType.CPU_SPIKE:
            message = f"{source} CPU使用率激增"
            metrics = {"cpu_usage_percent": random.uniform(90, 100)}
            symptoms = ["CPU使用率高", "请求队列积压", "超时增加"]
        elif fault_type == FaultType.DISK_FULL:
            message = f"{source} 磁盘空间不足"
            metrics = {"disk_usage_percent": random.uniform(95, 100)}
            symptoms = ["写入失败", "日志停止", "临时文件无法创建"]
        else:
            message = f"{source} 发生 {fault_type.value} 故障"
            metrics = {"error_rate": random.uniform(10, 50)}
            symptoms = ["服务异常", "用户投诉", "监控告警"]
        
        context = {
            "recent_deployment": random.choice([True, False]),
            "traffic_spike": random.choice([True, False]),
            "maintenance_window": random.choice([True, False])
        }
        
        healing_engine.detect_fault(
            fault_type=fault_type,
            source=source,
            message=message,
            severity=severity,
            symptoms=symptoms,
            metrics=metrics,
            context=context
        )