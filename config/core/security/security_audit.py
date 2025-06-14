"""
安全审计系统

提供配置系统的安全审计、威胁检测和合规报告功能。
支持实时监控、异常检测、风险评估和审计报告生成。
"""

import uuid
import json
import logging
from typing import Dict, List, Optional, Any, Union, Set, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import Lock, Thread
import time
import statistics
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """审计事件类型"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFIGURATION_ACCESS = "config_access"
    CONFIGURATION_CHANGE = "config_change"
    ENCRYPTION_OPERATION = "encryption_op"
    VAULT_ACCESS = "vault_access"
    SECURITY_VIOLATION = "security_violation"
    SYSTEM_EVENT = "system_event"
    USER_MANAGEMENT = "user_management"
    ROLE_MANAGEMENT = "role_management"


class SeverityLevel(Enum):
    """严重程度级别"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatLevel(Enum):
    """威胁级别"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplianceStandard(Enum):
    """合规标准"""
    GDPR = "gdpr"
    SOX = "sox"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO_27001 = "iso_27001"
    SOC2 = "soc2"


@dataclass
class AuditEvent:
    """审计事件"""
    event_id: str
    event_type: AuditEventType
    severity: SeverityLevel
    timestamp: datetime
    user_id: str
    resource: str
    action: str
    result: bool
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    correlation_id: Optional[str] = None
    risk_score: float = 0.0
    threat_indicators: List[str] = field(default_factory=list)


@dataclass
class SecurityRule:
    """安全规则"""
    rule_id: str
    name: str
    description: str
    rule_type: str
    severity: SeverityLevel
    condition: Callable[[AuditEvent], bool]
    action: Callable[[AuditEvent], None]
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    triggered_count: int = 0
    last_triggered: Optional[datetime] = None


@dataclass
class ThreatPattern:
    """威胁模式"""
    pattern_id: str
    name: str
    description: str
    indicators: List[str]
    severity: SeverityLevel
    threshold: int
    time_window: int  # 秒
    actions: List[str]
    is_active: bool = True


@dataclass
class SecurityAlert:
    """安全警报"""
    alert_id: str
    title: str
    description: str
    severity: SeverityLevel
    threat_level: ThreatLevel
    event_ids: List[str]
    user_id: str
    timestamp: datetime
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    response_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceReport:
    """合规报告"""
    report_id: str
    standard: ComplianceStandard
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    total_events: int
    violations: List[Dict[str, Any]]
    compliance_score: float
    recommendations: List[str]
    details: Dict[str, Any] = field(default_factory=dict)


class SecurityAuditError(Exception):
    """安全审计错误"""
    pass


class SecurityAudit:
    """
    安全审计系统
    
    提供配置系统的安全审计、威胁检测和合规报告功能。
    支持实时监控、异常检测、风险评估和审计报告生成。
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        max_events: int = 100000,
        retention_days: int = 365,
        enable_real_time_monitoring: bool = True
    ):
        # 存储
        self.events: deque = deque(maxlen=max_events)
        self.rules: Dict[str, SecurityRule] = {}
        self.threat_patterns: Dict[str, ThreatPattern] = {}
        self.alerts: Dict[str, SecurityAlert] = {}
        
        # 配置
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_events = max_events
        self.retention_days = retention_days
        self.enable_real_time_monitoring = enable_real_time_monitoring
        
        # 统计
        self.total_events = 0
        self.events_by_type = defaultdict(int)
        self.events_by_severity = defaultdict(int)
        self.violations_count = 0
        self.alerts_count = 0
        
        # 风险评估
        self.risk_scores = deque(maxlen=1000)
        self.threat_indicators = defaultdict(int)
        
        # 实时监控
        self.monitoring_thread = None
        self.is_monitoring = False
        
        # 线程安全
        self._lock = Lock()
        
        # 初始化
        self._initialize()
    
    def _initialize(self):
        """初始化安全审计系统"""
        try:
            # 创建默认规则
            self._create_default_rules()
            
            # 创建威胁模式
            self._create_threat_patterns()
            
            # 加载历史数据
            if self.storage_path and self.storage_path.exists():
                self._load_audit_data()
            
            # 启动实时监控
            if self.enable_real_time_monitoring:
                self._start_monitoring()
            
            logger.info("SecurityAudit initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize SecurityAudit: {e}")
            raise SecurityAuditError(f"Initialization failed: {e}")
    
    def log_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        resource: str,
        action: str,
        result: bool,
        severity: SeverityLevel = SeverityLevel.INFO,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        记录审计事件
        
        Args:
            event_type: 事件类型
            user_id: 用户ID
            resource: 资源
            action: 操作
            result: 结果
            severity: 严重程度
            details: 详细信息
            ip_address: IP地址
            user_agent: 用户代理
            session_id: 会话ID
            tags: 标签
            
        Returns:
            str: 事件ID
        """
        with self._lock:
            try:
                # 创建事件
                event_id = str(uuid.uuid4())
                correlation_id = self._generate_correlation_id(user_id, session_id)
                
                event = AuditEvent(
                    event_id=event_id,
                    event_type=event_type,
                    severity=severity,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    user_id=user_id,
                    resource=resource,
                    action=action,
                    result=result,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    session_id=session_id,
                    details=details or {},
                    tags=set(tags) if tags else set(),
                    correlation_id=correlation_id
                )
                
                # 风险评估
                event.risk_score = self._calculate_risk_score(event)
                event.threat_indicators = self._detect_threat_indicators(event)
                
                # 存储事件
                self.events.append(event)
                self.total_events += 1
                self.events_by_type[event_type.value] += 1
                self.events_by_severity[severity.value] += 1
                
                # 更新风险统计
                self.risk_scores.append(event.risk_score)
                for indicator in event.threat_indicators:
                    self.threat_indicators[indicator] += 1
                
                # 触发规则检查
                self._check_security_rules(event)
                
                # 威胁检测
                self._detect_threats(event)
                
                logger.debug(f"Audit event logged: {event_id} ({event_type.value})")
                return event_id
                
            except Exception as e:
                logger.error(f"Failed to log audit event: {e}")
                raise SecurityAuditError(f"Failed to log event: {e}")
    
    def create_security_rule(
        self,
        name: str,
        description: str,
        rule_type: str,
        severity: SeverityLevel,
        condition: Callable[[AuditEvent], bool],
        action: Callable[[AuditEvent], None]
    ) -> str:
        """
        创建安全规则
        
        Args:
            name: 规则名称
            description: 规则描述
            rule_type: 规则类型
            severity: 严重程度
            condition: 条件函数
            action: 动作函数
            
        Returns:
            str: 规则ID
        """
        with self._lock:
            try:
                rule_id = str(uuid.uuid4())
                
                rule = SecurityRule(
                    rule_id=rule_id,
                    name=name,
                    description=description,
                    rule_type=rule_type,
                    severity=severity,
                    condition=condition,
                    action=action
                )
                
                self.rules[rule_id] = rule
                
                logger.info(f"Security rule created: {name} ({rule_id})")
                return rule_id
                
            except Exception as e:
                logger.error(f"Failed to create security rule: {e}")
                raise SecurityAuditError(f"Failed to create rule: {e}")
    
    def create_alert(
        self,
        title: str,
        description: str,
        severity: SeverityLevel,
        threat_level: ThreatLevel,
        event_ids: List[str],
        user_id: str,
        response_actions: Optional[List[str]] = None
    ) -> str:
        """
        创建安全警报
        
        Args:
            title: 警报标题
            description: 警报描述
            severity: 严重程度
            threat_level: 威胁级别
            event_ids: 相关事件ID列表
            user_id: 用户ID
            response_actions: 响应动作
            
        Returns:
            str: 警报ID
        """
        with self._lock:
            try:
                alert_id = str(uuid.uuid4())
                
                alert = SecurityAlert(
                    alert_id=alert_id,
                    title=title,
                    description=description,
                    severity=severity,
                    threat_level=threat_level,
                    event_ids=event_ids,
                    user_id=user_id,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    response_actions=response_actions or []
                )
                
                self.alerts[alert_id] = alert
                self.alerts_count += 1
                
                logger.warning(f"Security alert created: {title} ({alert_id})")
                return alert_id
                
            except Exception as e:
                logger.error(f"Failed to create alert: {e}")
                raise SecurityAuditError(f"Failed to create alert: {e}")
    
    def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[AuditEventType] = None,
        user_id: Optional[str] = None,
        severity: Optional[SeverityLevel] = None,
        resource: Optional[str] = None,
        result: Optional[bool] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        查询审计事件
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            event_type: 事件类型
            user_id: 用户ID
            severity: 严重程度
            resource: 资源
            result: 结果
            limit: 限制数量
            
        Returns:
            List[Dict[str, Any]]: 事件列表
        """
        with self._lock:
            try:
                filtered_events = []
                
                for event in self.events:
                    # 时间过滤
                    if start_time and event.timestamp < start_time:
                        continue
                    if end_time and event.timestamp > end_time:
                        continue
                    
                    # 类型过滤
                    if event_type and event.event_type != event_type:
                        continue
                    
                    # 用户过滤
                    if user_id and event.user_id != user_id:
                        continue
                    
                    # 严重程度过滤
                    if severity and event.severity != severity:
                        continue
                    
                    # 资源过滤
                    if resource and resource not in event.resource:
                        continue
                    
                    # 结果过滤
                    if result is not None and event.result != result:
                        continue
                    
                    # 转换为字典
                    event_dict = {
                        'event_id': event.event_id,
                        'event_type': event.event_type.value,
                        'severity': event.severity.value,
                        'timestamp': event.timestamp.isoformat(),
                        'user_id': event.user_id,
                        'resource': event.resource,
                        'action': event.action,
                        'result': event.result,
                        'ip_address': event.ip_address,
                        'user_agent': event.user_agent,
                        'session_id': event.session_id,
                        'details': event.details,
                        'tags': list(event.tags),
                        'correlation_id': event.correlation_id,
                        'risk_score': event.risk_score,
                        'threat_indicators': event.threat_indicators
                    }
                    
                    filtered_events.append(event_dict)
                    
                    if len(filtered_events) >= limit:
                        break
                
                return filtered_events
                
            except Exception as e:
                logger.error(f"Failed to query events: {e}")
                raise SecurityAuditError(f"Failed to query events: {e}")
    
    def get_security_dashboard(self) -> Dict[str, Any]:
        """
        获取安全仪表板数据
        
        Returns:
            Dict[str, Any]: 仪表板数据
        """
        with self._lock:
            try:
                # 时间范围
                now = datetime.datetime.now(datetime.timezone.utc)
                last_24h = now - timedelta(hours=24)
                last_7d = now - timedelta(days=7)
                
                # 最近24小时事件
                recent_events = [e for e in self.events if e.timestamp > last_24h]
                
                # 高风险事件
                high_risk_events = [e for e in recent_events if e.risk_score > 7.0]
                
                # 活跃警报
                active_alerts = [a for a in self.alerts.values() if not a.is_resolved]
                
                # 威胁级别分布
                threat_levels = defaultdict(int)
                for alert in active_alerts:
                    threat_levels[alert.threat_level.value] += 1
                
                # 用户活动统计
                user_activity = defaultdict(int)
                for event in recent_events:
                    user_activity[event.user_id] += 1
                
                # 风险趋势
                avg_risk_score = statistics.mean(self.risk_scores) if self.risk_scores else 0.0
                
                return {
                    'summary': {
                        'total_events': self.total_events,
                        'recent_events_24h': len(recent_events),
                        'high_risk_events': len(high_risk_events),
                        'active_alerts': len(active_alerts),
                        'violations_count': self.violations_count,
                        'avg_risk_score': round(avg_risk_score, 2)
                    },
                    'events_by_type': dict(self.events_by_type),
                    'events_by_severity': dict(self.events_by_severity),
                    'threat_levels': dict(threat_levels),
                    'user_activity': dict(user_activity),
                    'top_threat_indicators': dict(sorted(
                        self.threat_indicators.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:10]),
                    'recent_alerts': [
                        {
                            'alert_id': a.alert_id,
                            'title': a.title,
                            'severity': a.severity.value,
                            'threat_level': a.threat_level.value,
                            'timestamp': a.timestamp.isoformat()
                        }
                        for a in sorted(active_alerts, key=lambda x: x.timestamp, reverse=True)[:5]
                    ]
                }
                
            except Exception as e:
                logger.error(f"Failed to get security dashboard: {e}")
                raise SecurityAuditError(f"Failed to get dashboard: {e}")
    
    def generate_compliance_report(
        self,
        standard: ComplianceStandard,
        start_date: datetime,
        end_date: datetime
    ) -> ComplianceReport:
        """
        生成合规报告
        
        Args:
            standard: 合规标准
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            ComplianceReport: 合规报告
        """
        with self._lock:
            try:
                # 筛选相关事件
                relevant_events = [
                    e for e in self.events
                    if start_date <= e.timestamp <= end_date
                ]
                
                # 检查违规
                violations = self._check_compliance_violations(standard, relevant_events)
                
                # 计算合规得分
                compliance_score = self._calculate_compliance_score(standard, violations, len(relevant_events))
                
                # 生成建议
                recommendations = self._generate_compliance_recommendations(standard, violations)
                
                # 创建报告
                report = ComplianceReport(
                    report_id=str(uuid.uuid4()),
                    standard=standard,
                    period_start=start_date,
                    period_end=end_date,
                    generated_at=datetime.datetime.now(datetime.timezone.utc),
                    total_events=len(relevant_events),
                    violations=violations,
                    compliance_score=compliance_score,
                    recommendations=recommendations,
                    details={
                        'events_by_type': self._group_events_by_type(relevant_events),
                        'risk_analysis': self._analyze_risks(relevant_events),
                        'user_access_patterns': self._analyze_user_patterns(relevant_events)
                    }
                )
                
                logger.info(f"Compliance report generated: {standard.value} ({report.report_id})")
                return report
                
            except Exception as e:
                logger.error(f"Failed to generate compliance report: {e}")
                raise SecurityAuditError(f"Failed to generate report: {e}")
    
    def get_audit_statistics(self) -> Dict[str, Any]:
        """获取审计统计信息"""
        with self._lock:
            active_rules = len([r for r in self.rules.values() if r.is_active])
            active_patterns = len([p for p in self.threat_patterns.values() if p.is_active])
            
            return {
                'total_events': self.total_events,
                'events_in_memory': len(self.events),
                'events_by_type': dict(self.events_by_type),
                'events_by_severity': dict(self.events_by_severity),
                'violations_count': self.violations_count,
                'alerts_count': self.alerts_count,
                'active_rules': active_rules,
                'total_rules': len(self.rules),
                'active_threat_patterns': active_patterns,
                'total_threat_patterns': len(self.threat_patterns),
                'avg_risk_score': statistics.mean(self.risk_scores) if self.risk_scores else 0.0,
                'max_risk_score': max(self.risk_scores) if self.risk_scores else 0.0,
                'retention_days': self.retention_days,
                'monitoring_enabled': self.is_monitoring
            }
    
    def _create_default_rules(self):
        """创建默认安全规则"""
        # 多次登录失败规则
        def failed_login_condition(event: AuditEvent) -> bool:
            if event.event_type != AuditEventType.AUTHENTICATION or event.result:
                return False
            
            # 检查最近5分钟内的失败次数
            recent_failures = 0
            cutoff_time = event.timestamp - timedelta(minutes=5)
            
            for e in self.events:
                if (e.user_id == event.user_id and
                    e.event_type == AuditEventType.AUTHENTICATION and
                    not e.result and
                    e.timestamp > cutoff_time):
                    recent_failures += 1
            
            return recent_failures >= 5
        
        def failed_login_action(event: AuditEvent):
            self.create_alert(
                title="Multiple Failed Login Attempts",
                description=f"User {event.user_id} has multiple failed login attempts",
                severity=SeverityLevel.HIGH,
                threat_level=ThreatLevel.MEDIUM,
                event_ids=[event.event_id],
                user_id=event.user_id,
                response_actions=["lock_user", "investigate"]
            )
        
        self.create_security_rule(
            name="Multiple Failed Logins",
            description="Detect multiple failed login attempts",
            rule_type="authentication",
            severity=SeverityLevel.HIGH,
            condition=failed_login_condition,
            action=failed_login_action
        )
        
        # 高权限操作规则
        def high_privilege_condition(event: AuditEvent) -> bool:
            high_privilege_actions = ["delete", "admin", "manage_users", "manage_roles"]
            return any(action in event.action.lower() for action in high_privilege_actions)
        
        def high_privilege_action(event: AuditEvent):
            if event.severity.value in ["high", "critical"]:
                self.create_alert(
                    title="High Privilege Operation",
                    description=f"High privilege operation performed: {event.action}",
                    severity=SeverityLevel.MEDIUM,
                    threat_level=ThreatLevel.LOW,
                    event_ids=[event.event_id],
                    user_id=event.user_id,
                    response_actions=["review", "audit"]
                )
        
        self.create_security_rule(
            name="High Privilege Operations",
            description="Monitor high privilege operations",
            rule_type="authorization",
            severity=SeverityLevel.MEDIUM,
            condition=high_privilege_condition,
            action=high_privilege_action
        )
    
    def _create_threat_patterns(self):
        """创建威胁模式"""
        # 暴力破解模式
        brute_force = ThreatPattern(
            pattern_id="brute_force",
            name="Brute Force Attack",
            description="Multiple failed authentication attempts",
            indicators=["failed_login", "multiple_attempts", "short_timeframe"],
            severity=SeverityLevel.HIGH,
            threshold=10,
            time_window=300,  # 5分钟
            actions=["create_alert", "block_ip", "lock_user"]
        )
        self.threat_patterns["brute_force"] = brute_force
        
        # 权限提升模式
        privilege_escalation = ThreatPattern(
            pattern_id="privilege_escalation",
            name="Privilege Escalation",
            description="Unusual privilege escalation patterns",
            indicators=["role_change", "permission_grant", "admin_access"],
            severity=SeverityLevel.CRITICAL,
            threshold=3,
            time_window=3600,  # 1小时
            actions=["create_alert", "investigate", "notify_admin"]
        )
        self.threat_patterns["privilege_escalation"] = privilege_escalation
    
    def _calculate_risk_score(self, event: AuditEvent) -> float:
        """计算事件风险分数"""
        score = 0.0
        
        # 基础分数（根据严重程度）
        severity_scores = {
            SeverityLevel.INFO: 1.0,
            SeverityLevel.LOW: 2.0,
            SeverityLevel.MEDIUM: 5.0,
            SeverityLevel.HIGH: 8.0,
            SeverityLevel.CRITICAL: 10.0
        }
        score += severity_scores.get(event.severity, 1.0)
        
        # 失败操作加分
        if not event.result:
            score += 2.0
        
        # 敏感操作加分
        sensitive_actions = ["delete", "admin", "encrypt", "decrypt", "manage"]
        if any(action in event.action.lower() for action in sensitive_actions):
            score += 1.5
        
        # 异常时间加分（非工作时间）
        hour = event.timestamp.hour
        if hour < 6 or hour > 22:  # 非工作时间
            score += 1.0
        
        # IP地址异常加分（如果有IP白名单的话）
        # 这里简化处理
        
        return min(score, 10.0)  # 最高10分
    
    def _detect_threat_indicators(self, event: AuditEvent) -> List[str]:
        """检测威胁指标"""
        indicators = []
        
        # 失败操作指标
        if not event.result:
            indicators.append("operation_failed")
        
        # 高权限操作指标
        if any(action in event.action.lower() for action in ["admin", "delete", "manage"]):
            indicators.append("high_privilege_operation")
        
        # 敏感资源访问指标
        if any(resource in event.resource.lower() for resource in ["vault", "secret", "password"]):
            indicators.append("sensitive_resource_access")
        
        # 异常时间指标
        hour = event.timestamp.hour
        if hour < 6 or hour > 22:
            indicators.append("unusual_time")
        
        # 连续操作指标
        recent_events = [e for e in self.events 
                        if e.user_id == event.user_id and 
                        e.timestamp > event.timestamp - timedelta(minutes=5)]
        if len(recent_events) > 10:
            indicators.append("high_frequency_operations")
        
        return indicators
    
    def _check_security_rules(self, event: AuditEvent):
        """检查安全规则"""
        for rule in self.rules.values():
            if rule.is_active:
                try:
                    if rule.condition(event):
                        rule.triggered_count += 1
                        rule.last_triggered = datetime.datetime.now(datetime.timezone.utc)
                        rule.action(event)
                except Exception as e:
                    logger.error(f"Error checking security rule {rule.rule_id}: {e}")
    
    def _detect_threats(self, event: AuditEvent):
        """威胁检测"""
        for pattern in self.threat_patterns.values():
            if pattern.is_active:
                # 检查威胁指标匹配
                matching_indicators = [i for i in event.threat_indicators if i in pattern.indicators]
                
                if matching_indicators:
                    # 检查时间窗口内的事件
                    cutoff_time = event.timestamp - timedelta(seconds=pattern.time_window)
                    matching_events = [
                        e for e in self.events
                        if e.timestamp > cutoff_time and
                        any(i in e.threat_indicators for i in pattern.indicators)
                    ]
                    
                    if len(matching_events) >= pattern.threshold:
                        # 触发威胁警报
                        self.create_alert(
                            title=f"Threat Detected: {pattern.name}",
                            description=pattern.description,
                            severity=pattern.severity,
                            threat_level=ThreatLevel.HIGH,
                            event_ids=[e.event_id for e in matching_events],
                            user_id=event.user_id,
                            response_actions=pattern.actions
                        )
    
    def _check_compliance_violations(self, standard: ComplianceStandard, events: List[AuditEvent]) -> List[Dict[str, Any]]:
        """检查合规违规"""
        violations = []
        
        if standard == ComplianceStandard.GDPR:
            # GDPR检查：个人数据访问记录
            for event in events:
                if ("personal" in event.resource.lower() or 
                    "user_data" in event.resource.lower()):
                    if not event.details.get("consent_recorded"):
                        violations.append({
                            "type": "GDPR_NO_CONSENT",
                            "event_id": event.event_id,
                            "description": "Personal data access without recorded consent",
                            "timestamp": event.timestamp.isoformat()
                        })
        
        elif standard == ComplianceStandard.SOX:
            # SOX检查：财务数据访问控制
            for event in events:
                if "financial" in event.resource.lower():
                    if not event.details.get("approval_recorded"):
                        violations.append({
                            "type": "SOX_NO_APPROVAL",
                            "event_id": event.event_id,
                            "description": "Financial data access without proper approval",
                            "timestamp": event.timestamp.isoformat()
                        })
        
        # 添加更多合规标准检查...
        
        return violations
    
    def _calculate_compliance_score(self, standard: ComplianceStandard, violations: List[Dict], total_events: int) -> float:
        """计算合规得分"""
        if total_events == 0:
            return 100.0
        
        violation_penalty = len(violations) * 5  # 每个违规扣5分
        base_score = 100.0
        
        score = max(0.0, base_score - violation_penalty)
        return round(score, 2)
    
    def _generate_compliance_recommendations(self, standard: ComplianceStandard, violations: List[Dict]) -> List[str]:
        """生成合规建议"""
        recommendations = []
        
        if violations:
            recommendations.append("Review and address all identified violations")
            recommendations.append("Implement additional access controls")
            recommendations.append("Enhance audit logging and monitoring")
        
        if standard == ComplianceStandard.GDPR:
            recommendations.extend([
                "Ensure all personal data access is properly consented",
                "Implement data retention policies",
                "Provide data portability mechanisms"
            ])
        
        elif standard == ComplianceStandard.SOX:
            recommendations.extend([
                "Implement segregation of duties",
                "Enhance financial data access controls",
                "Maintain comprehensive audit trails"
            ])
        
        return recommendations
    
    def _group_events_by_type(self, events: List[AuditEvent]) -> Dict[str, int]:
        """按类型分组事件"""
        groups = defaultdict(int)
        for event in events:
            groups[event.event_type.value] += 1
        return dict(groups)
    
    def _analyze_risks(self, events: List[AuditEvent]) -> Dict[str, Any]:
        """分析风险"""
        risk_scores = [e.risk_score for e in events]
        
        return {
            'total_events': len(events),
            'avg_risk_score': statistics.mean(risk_scores) if risk_scores else 0.0,
            'max_risk_score': max(risk_scores) if risk_scores else 0.0,
            'high_risk_events': len([s for s in risk_scores if s > 7.0]),
            'risk_distribution': {
                'low': len([s for s in risk_scores if s <= 3.0]),
                'medium': len([s for s in risk_scores if 3.0 < s <= 7.0]),
                'high': len([s for s in risk_scores if s > 7.0])
            }
        }
    
    def _analyze_user_patterns(self, events: List[AuditEvent]) -> Dict[str, Any]:
        """分析用户模式"""
        user_events = defaultdict(list)
        for event in events:
            user_events[event.user_id].append(event)
        
        patterns = {}
        for user_id, user_event_list in user_events.items():
            patterns[user_id] = {
                'total_events': len(user_event_list),
                'failed_operations': len([e for e in user_event_list if not e.result]),
                'avg_risk_score': statistics.mean([e.risk_score for e in user_event_list]),
                'event_types': list(set(e.event_type.value for e in user_event_list))
            }
        
        return patterns
    
    def _generate_correlation_id(self, user_id: str, session_id: Optional[str]) -> str:
        """生成关联ID"""
        base = f"{user_id}:{session_id or 'no_session'}"
        return f"corr_{hash(base) % 1000000:06d}"
    
    def _start_monitoring(self):
        """启动实时监控"""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitoring_thread = Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()
            logger.info("Real-time monitoring started")
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.is_monitoring:
            try:
                # 清理过期事件
                self._cleanup_old_events()
                
                # 检查系统健康状态
                self._check_system_health()
                
                # 等待
                time.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
    
    def _cleanup_old_events(self):
        """清理过期事件"""
        if not self.retention_days:
            return
        
        cutoff_time = datetime.datetime.now(datetime.timezone.utc) - timedelta(days=self.retention_days)
        
        # 清理过期事件（deque会自动限制大小，这里主要是清理alerts）
        expired_alerts = [
            alert_id for alert_id, alert in self.alerts.items()
            if alert.timestamp < cutoff_time and alert.is_resolved
        ]
        
        for alert_id in expired_alerts:
            del self.alerts[alert_id]
    
    def _check_system_health(self):
        """检查系统健康状态"""
        # 检查内存使用
        if len(self.events) > self.max_events * 0.9:
            logger.warning("Audit events approaching memory limit")
        
        # 检查磁盘空间（如果配置了存储路径）
        if self.storage_path:
            try:
                import shutil
                _, _, free = shutil.disk_usage(self.storage_path.parent)
                if free < 1024 * 1024 * 1024:  # 少于1GB
                    logger.warning("Low disk space for audit storage")
            except Exception:
                pass
    
    def _save_audit_data(self):
        """保存审计数据"""
        # 实现数据持久化
        pass
    
    def _load_audit_data(self):
        """加载审计数据"""
        # 实现数据加载
        pass


# 便利函数
def create_security_audit(
    storage_path: Optional[str] = None,
    max_events: int = 100000,
    retention_days: int = 365
) -> SecurityAudit:
    """
    创建安全审计系统实例
    
    Args:
        storage_path: 存储路径
        max_events: 最大事件数
        retention_days: 保留天数
        
    Returns:
        SecurityAudit: 安全审计系统实例
    """
    return SecurityAudit(
        storage_path=storage_path,
        max_events=max_events,
        retention_days=retention_days
    )