"""
安全策略引擎

提供企业级安全策略管理和执行功能：
- 安全策略定义和管理
- 策略规则引擎
- 策略执行和强制
- 合规性检查和评估
- 策略违规处理

Week 5 Day 6 实现
"""

import json
import time
import uuid
import threading
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta


class PolicyType(Enum):
    """策略类型"""
    ACCESS_CONTROL = "access_control"
    DATA_PROTECTION = "data_protection"
    NETWORK_SECURITY = "network_security"
    SYSTEM_HARDENING = "system_hardening"
    COMPLIANCE = "compliance"
    OPERATIONAL = "operational"


class PolicySeverity(Enum):
    """策略严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyStatus(Enum):
    """策略状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    DEPRECATED = "deprecated"


class PolicyAction(Enum):
    """策略动作"""
    ALLOW = "allow"
    DENY = "deny"
    LOG = "log"
    ALERT = "alert"
    BLOCK = "block"
    REDIRECT = "redirect"


@dataclass
class PolicyCondition:
    """策略条件"""
    field: str
    operator: str  # eq, ne, gt, lt, gte, lte, in, not_in, regex, contains
    value: Any
    case_sensitive: bool = True
    
    def evaluate(self, context: dict) -> bool:
        """评估条件"""
        try:
            field_value = self._get_field_value(context, self.field)
            
            if not self.case_sensitive and isinstance(field_value, str) and isinstance(self.value, str):
                field_value = field_value.lower()
                compare_value = self.value.lower()
            else:
                compare_value = self.value
            
            if self.operator == "eq":
                return field_value == compare_value
            elif self.operator == "ne":
                return field_value != compare_value
            elif self.operator == "gt":
                return field_value > compare_value
            elif self.operator == "lt":
                return field_value < compare_value
            elif self.operator == "gte":
                return field_value >= compare_value
            elif self.operator == "lte":
                return field_value <= compare_value
            elif self.operator == "in":
                return field_value in compare_value
            elif self.operator == "not_in":
                return field_value not in compare_value
            elif self.operator == "regex":
                import re
                return bool(re.search(str(compare_value), str(field_value)))
            elif self.operator == "contains":
                return str(compare_value) in str(field_value)
            else:
                return False
                
        except Exception:
            return False
    
    def _get_field_value(self, context: dict, field: str) -> Any:
        """获取字段值（支持嵌套字段）"""
        if '.' not in field:
            return context.get(field)
        
        keys = field.split('.')
        value = context
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value


@dataclass
class PolicyRule:
    """策略规则"""
    rule_id: str
    name: str
    description: str
    conditions: List[PolicyCondition]
    action: PolicyAction
    severity: PolicySeverity
    enabled: bool = True
    logic_operator: str = "AND"  # AND, OR
    
    def evaluate(self, context: dict) -> bool:
        """评估规则"""
        if not self.enabled:
            return False
        
        if not self.conditions:
            return True
        
        results = [condition.evaluate(context) for condition in self.conditions]
        
        if self.logic_operator == "AND":
            return all(results)
        elif self.logic_operator == "OR":
            return any(results)
        else:
            return False


@dataclass
class SecurityPolicy:
    """安全策略"""
    policy_id: str
    name: str
    description: str
    policy_type: PolicyType
    rules: List[PolicyRule]
    status: PolicyStatus = PolicyStatus.ACTIVE
    version: str = "1.0.0"
    created_at: float = None
    updated_at: float = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.updated_at is None:
            self.updated_at = time.time()
        if self.tags is None:
            self.tags = []
    
    def evaluate(self, context: dict) -> List[dict]:
        """评估策略"""
        violations = []
        
        if self.status != PolicyStatus.ACTIVE:
            return violations
        
        for rule in self.rules:
            if rule.evaluate(context):
                violations.append({
                    'policy_id': self.policy_id,
                    'policy_name': self.name,
                    'rule_id': rule.rule_id,
                    'rule_name': rule.name,
                    'action': rule.action.value,
                    'severity': rule.severity.value,
                    'timestamp': time.time(),
                    'context': context
                })
        
        return violations


@dataclass
class PolicyViolation:
    """策略违规"""
    violation_id: str
    policy_id: str
    rule_id: str
    action: str
    severity: str
    context: dict
    timestamp: float
    resolved: bool = False
    resolution_notes: str = ""


class SecurityPolicyEngine:
    """安全策略引擎"""
    
    def __init__(self, config_path: str = "/tmp/security_policies"):
        self.config_path = config_path
        self.policies: Dict[str, SecurityPolicy] = {}
        self.violations: List[PolicyViolation] = []
        self.evaluation_callbacks: List[Callable] = []
        self.statistics = {
            'total_evaluations': 0,
            'total_violations': 0,
            'policies_loaded': 0,
            'last_evaluation': None
        }
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 初始化默认策略
        self._initialize_default_policies()
    
    def _initialize_default_policies(self):
        """初始化默认安全策略"""
        default_policies = [
            # 访问控制策略
            SecurityPolicy(
                policy_id="access_control_001",
                name="强制认证策略",
                description="所有配置访问都必须进行身份认证",
                policy_type=PolicyType.ACCESS_CONTROL,
                rules=[
                    PolicyRule(
                        rule_id="auth_required",
                        name="认证必需",
                        description="检查是否存在有效的认证令牌",
                        conditions=[
                            PolicyCondition("auth_token", "eq", None)
                        ],
                        action=PolicyAction.DENY,
                        severity=PolicySeverity.HIGH
                    )
                ]
            ),
            
            # 数据保护策略
            SecurityPolicy(
                policy_id="data_protection_001",
                name="敏感数据加密策略",
                description="敏感配置数据必须加密存储",
                policy_type=PolicyType.DATA_PROTECTION,
                rules=[
                    PolicyRule(
                        rule_id="encrypt_sensitive",
                        name="敏感数据加密",
                        description="密码、密钥等敏感数据必须加密",
                        conditions=[
                            PolicyCondition("config_type", "in", ["password", "secret", "key"]),
                            PolicyCondition("encrypted", "eq", False)
                        ],
                        action=PolicyAction.BLOCK,
                        severity=PolicySeverity.CRITICAL
                    )
                ]
            ),
            
            # 网络安全策略
            SecurityPolicy(
                policy_id="network_security_001",
                name="安全连接策略",
                description="网络连接必须使用安全协议",
                policy_type=PolicyType.NETWORK_SECURITY,
                rules=[
                    PolicyRule(
                        rule_id="secure_protocol",
                        name="安全协议检查",
                        description="禁止使用不安全的网络协议",
                        conditions=[
                            PolicyCondition("protocol", "in", ["http", "ftp", "telnet"])
                        ],
                        action=PolicyAction.BLOCK,
                        severity=PolicySeverity.HIGH
                    )
                ]
            ),
            
            # 系统加固策略
            SecurityPolicy(
                policy_id="system_hardening_001",
                name="默认密码策略",
                description="禁止使用默认密码",
                policy_type=PolicyType.SYSTEM_HARDENING,
                rules=[
                    PolicyRule(
                        rule_id="no_default_password",
                        name="禁用默认密码",
                        description="检测并禁止使用常见的默认密码",
                        conditions=[
                            PolicyCondition("password", "in", ["admin", "password", "123456", "root", "admin123"])
                        ],
                        action=PolicyAction.BLOCK,
                        severity=PolicySeverity.CRITICAL
                    )
                ]
            )
        ]
        
        for policy in default_policies:
            self.add_policy(policy)
    
    def add_policy(self, policy: SecurityPolicy) -> bool:
        """添加策略"""
        with self._lock:
            try:
                self.policies[policy.policy_id] = policy
                self.statistics['policies_loaded'] = len(self.policies)
                return True
            except Exception:
                return False
    
    def remove_policy(self, policy_id: str) -> bool:
        """移除策略"""
        with self._lock:
            try:
                if policy_id in self.policies:
                    del self.policies[policy_id]
                    self.statistics['policies_loaded'] = len(self.policies)
                    return True
                return False
            except Exception:
                return False
    
    def get_policy(self, policy_id: str) -> Optional[SecurityPolicy]:
        """获取策略"""
        with self._lock:
            return self.policies.get(policy_id)
    
    def list_policies(
        self,
        policy_type: Optional[PolicyType] = None,
        status: Optional[PolicyStatus] = None
    ) -> List[SecurityPolicy]:
        """列出策略"""
        with self._lock:
            policies = list(self.policies.values())
            
            if policy_type:
                policies = [p for p in policies if p.policy_type == policy_type]
            
            if status:
                policies = [p for p in policies if p.status == status]
            
            return policies
    
    def evaluate_context(self, context: dict) -> List[PolicyViolation]:
        """评估上下文"""
        with self._lock:
            violations = []
            
            try:
                self.statistics['total_evaluations'] += 1
                self.statistics['last_evaluation'] = time.time()
                
                for policy in self.policies.values():
                    if policy.status == PolicyStatus.ACTIVE:
                        policy_violations = policy.evaluate(context)
                        
                        for violation_data in policy_violations:
                            violation = PolicyViolation(
                                violation_id=str(uuid.uuid4()),
                                policy_id=violation_data['policy_id'],
                                rule_id=violation_data['rule_id'],
                                action=violation_data['action'],
                                severity=violation_data['severity'],
                                context=violation_data['context'],
                                timestamp=violation_data['timestamp']
                            )
                            violations.append(violation)
                            self.violations.append(violation)
                
                self.statistics['total_violations'] += len(violations)
                
                # 调用回调函数
                for callback in self.evaluation_callbacks:
                    try:
                        callback(context, violations)
                    except Exception:
                        pass
                
                return violations
                
            except Exception as e:
                # 记录错误但不抛出异常
                return []
    
    def evaluate_compliance(self) -> dict:
        """评估合规性"""
        with self._lock:
            try:
                active_policies = [p for p in self.policies.values() if p.status == PolicyStatus.ACTIVE]
                total_policies = len(active_policies)
                
                if total_policies == 0:
                    return {
                        'compliance_rate': 1.0,
                        'total_policies': 0,
                        'compliant_policies': 0,
                        'violations': 0,
                        'status': 'NO_POLICIES'
                    }
                
                # 统计近期违规
                recent_violations = [
                    v for v in self.violations 
                    if v.timestamp > (time.time() - 3600) and not v.resolved  # 最近1小时
                ]
                
                violation_policies = set(v.policy_id for v in recent_violations)
                compliant_policies = total_policies - len(violation_policies)
                compliance_rate = compliant_policies / total_policies
                
                return {
                    'compliance_rate': compliance_rate,
                    'total_policies': total_policies,
                    'compliant_policies': compliant_policies,
                    'violations': len(recent_violations),
                    'status': 'COMPLIANT' if compliance_rate >= 0.9 else 'NON_COMPLIANT'
                }
                
            except Exception:
                return {
                    'compliance_rate': 0.0,
                    'total_policies': len(self.policies),
                    'compliant_policies': 0,
                    'violations': len(self.violations),
                    'status': 'ERROR'
                }
    
    def get_violations(
        self,
        severity: Optional[PolicySeverity] = None,
        resolved: Optional[bool] = None,
        limit: int = 100
    ) -> List[PolicyViolation]:
        """获取违规记录"""
        with self._lock:
            violations = self.violations.copy()
            
            if severity:
                violations = [v for v in violations if v.severity == severity.value]
            
            if resolved is not None:
                violations = [v for v in violations if v.resolved == resolved]
            
            # 按时间倒序排列
            violations.sort(key=lambda x: x.timestamp, reverse=True)
            
            return violations[:limit]
    
    def resolve_violation(self, violation_id: str, resolution_notes: str = "") -> bool:
        """解决违规"""
        with self._lock:
            for violation in self.violations:
                if violation.violation_id == violation_id:
                    violation.resolved = True
                    violation.resolution_notes = resolution_notes
                    return True
            return False
    
    def add_evaluation_callback(self, callback: Callable):
        """添加评估回调"""
        with self._lock:
            self.evaluation_callbacks.append(callback)
    
    def remove_evaluation_callback(self, callback: Callable):
        """移除评估回调"""
        with self._lock:
            if callback in self.evaluation_callbacks:
                self.evaluation_callbacks.remove(callback)
    
    def get_policy_status(self) -> dict:
        """获取策略状态"""
        with self._lock:
            status_counts = {}
            type_counts = {}
            
            for policy in self.policies.values():
                # 状态统计
                status = policy.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
                
                # 类型统计
                policy_type = policy.policy_type.value
                type_counts[policy_type] = type_counts.get(policy_type, 0) + 1
            
            return {
                'total_policies': len(self.policies),
                'status_distribution': status_counts,
                'type_distribution': type_counts,
                'statistics': self.statistics.copy()
            }
    
    def generate_policy_report(self) -> dict:
        """生成策略报告"""
        with self._lock:
            compliance = self.evaluate_compliance()
            status = self.get_policy_status()
            recent_violations = self.get_violations(limit=50)
            
            return {
                'report_timestamp': time.time(),
                'compliance': compliance,
                'policy_status': status,
                'recent_violations': [
                    {
                        'violation_id': v.violation_id,
                        'policy_id': v.policy_id,
                        'rule_id': v.rule_id,
                        'severity': v.severity,
                        'action': v.action,
                        'timestamp': v.timestamp,
                        'resolved': v.resolved
                    }
                    for v in recent_violations
                ],
                'recommendations': self._generate_policy_recommendations(compliance, status)
            }
    
    def _generate_policy_recommendations(self, compliance: dict, status: dict) -> List[dict]:
        """生成策略建议"""
        recommendations = []
        
        # 合规性建议
        if compliance['compliance_rate'] < 0.8:
            recommendations.append({
                'category': 'COMPLIANCE',
                'priority': 'HIGH',
                'description': f"合规率仅为{compliance['compliance_rate']:.1%}，建议审查和加强安全策略",
                'action': 'review_policies'
            })
        
        # 违规建议
        if compliance['violations'] > 10:
            recommendations.append({
                'category': 'VIOLATIONS',
                'priority': 'MEDIUM',
                'description': f"发现{compliance['violations']}个违规，建议及时处理",
                'action': 'resolve_violations'
            })
        
        # 策略覆盖建议
        if status['total_policies'] < 5:
            recommendations.append({
                'category': 'COVERAGE',
                'priority': 'MEDIUM',
                'description': "安全策略数量较少，建议增加更多安全策略以提高覆盖率",
                'action': 'add_policies'
            })
        
        return recommendations
    
    def start(self):
        """启动策略引擎"""
        # 策略引擎启动逻辑
        pass
    
    def stop(self):
        """停止策略引擎"""
        # 策略引擎停止逻辑
        pass


class PolicyEnforcementError(Exception):
    """策略执行错误"""
    pass


def create_security_policy_engine(config_path: str = None) -> SecurityPolicyEngine:
    """
    创建安全策略引擎
    
    Args:
        config_path: 配置路径
        
    Returns:
        SecurityPolicyEngine: 策略引擎实例
    """
    return SecurityPolicyEngine(config_path or "/tmp/security_policies")