"""
安全监控系统

提供实时安全监控功能：
- 实时安全事件监控
- 安全指标收集
- 安全告警管理
- 安全仪表板
- 安全报告生成

Week 5 Day 6 实现
"""

import time
import threading
import queue
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque


class SecurityEventType(Enum):
    """安全事件类型"""
    LOGIN_ATTEMPT = "login_attempt"
    AUTHENTICATION_FAILURE = "authentication_failure"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DATA_ACCESS = "data_access"
    CONFIGURATION_CHANGE = "configuration_change"
    POLICY_VIOLATION = "policy_violation"
    THREAT_DETECTED = "threat_detected"
    SYSTEM_ANOMALY = "system_anomaly"
    SECURITY_INCIDENT = "security_incident"


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class SecurityEvent:
    """安全事件"""
    event_id: str
    event_type: SecurityEventType
    source: str
    target: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    severity: str = "medium"
    tags: List[str] = field(default_factory=list)


@dataclass
class SecurityMetric:
    """安全指标"""
    metric_id: str
    name: str
    value: float
    unit: str = ""
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)
    
    @property
    def metric_key(self) -> str:
        """获取指标键"""
        return f"{self.name}:{':'.join(f'{k}={v}' for k, v in sorted(self.tags.items()))}"


@dataclass
class SecurityAlert:
    """安全告警"""
    alert_id: str
    title: str
    description: str
    level: AlertLevel
    source_events: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    resolved: bool = False
    resolution_notes: str = ""


@dataclass
class MonitoringRule:
    """监控规则"""
    rule_id: str
    name: str
    description: str
    event_types: List[SecurityEventType]
    conditions: List[Dict[str, Any]]
    alert_level: AlertLevel
    threshold: Optional[Dict[str, Any]] = None
    time_window: int = 300  # 时间窗口（秒）
    enabled: bool = True
    
    def evaluate(self, events: List[SecurityEvent], metrics: List[SecurityMetric]) -> Optional[SecurityAlert]:
        """评估规则"""
        if not self.enabled:
            return None
        
        try:
            # 过滤相关事件
            relevant_events = [
                event for event in events
                if event.event_type in self.event_types
                and (time.time() - event.timestamp) <= self.time_window
            ]
            
            if not relevant_events:
                return None
            
            # 评估条件
            if self._evaluate_conditions(relevant_events, metrics):
                return SecurityAlert(
                    alert_id=f"alert_{self.rule_id}_{int(time.time())}",
                    title=f"安全规则触发: {self.name}",
                    description=self.description,
                    level=self.alert_level,
                    source_events=[event.event_id for event in relevant_events]
                )
            
            return None
            
        except Exception:
            return None
    
    def _evaluate_conditions(self, events: List[SecurityEvent], metrics: List[SecurityMetric]) -> bool:
        """评估条件"""
        if not self.conditions:
            return len(events) > 0
        
        for condition in self.conditions:
            condition_type = condition.get('type')
            
            if condition_type == 'event_count':
                threshold = condition.get('threshold', 1)
                if len(events) >= threshold:
                    return True
            
            elif condition_type == 'unique_sources':
                unique_sources = len(set(event.source for event in events))
                threshold = condition.get('threshold', 1)
                if unique_sources >= threshold:
                    return True
            
            elif condition_type == 'failure_rate':
                failure_events = [
                    event for event in events
                    if event.event_type == SecurityEventType.AUTHENTICATION_FAILURE
                ]
                total_events = len(events)
                if total_events > 0:
                    failure_rate = len(failure_events) / total_events
                    threshold = condition.get('threshold', 0.5)
                    if failure_rate >= threshold:
                        return True
        
        return False


class SecurityDashboard:
    """安全仪表板"""
    
    def __init__(self):
        self.widgets = {}
        self.refresh_interval = 60  # 刷新间隔（秒）
        self.last_refresh = 0
    
    def add_widget(self, widget_id: str, widget_config: dict):
        """添加小部件"""
        self.widgets[widget_id] = widget_config
    
    def remove_widget(self, widget_id: str):
        """移除小部件"""
        if widget_id in self.widgets:
            del self.widgets[widget_id]
    
    def get_dashboard_data(self, events: List[SecurityEvent], metrics: List[SecurityMetric], alerts: List[SecurityAlert]) -> dict:
        """获取仪表板数据"""
        current_time = time.time()
        
        # 计算基本统计
        recent_events = [e for e in events if (current_time - e.timestamp) < 3600]  # 最近1小时
        active_alerts = [a for a in alerts if not a.resolved]
        
        # 事件类型分布
        event_type_counts = defaultdict(int)
        for event in recent_events:
            event_type_counts[event.event_type.value] += 1
        
        # 告警级别分布
        alert_level_counts = defaultdict(int)
        for alert in active_alerts:
            alert_level_counts[alert.level.value] += 1
        
        # 安全评分（简化算法）
        security_score = self._calculate_security_score(recent_events, active_alerts)
        
        return {
            'timestamp': current_time,
            'summary': {
                'total_events_last_hour': len(recent_events),
                'active_alerts': len(active_alerts),
                'security_score': security_score,
                'status': self._determine_security_status(security_score, active_alerts)
            },
            'event_distribution': dict(event_type_counts),
            'alert_distribution': dict(alert_level_counts),
            'recent_events': [
                {
                    'event_id': e.event_id,
                    'event_type': e.event_type.value,
                    'source': e.source,
                    'timestamp': e.timestamp,
                    'severity': e.severity
                }
                for e in recent_events[-10:]  # 最近10个事件
            ],
            'active_alerts': [
                {
                    'alert_id': a.alert_id,
                    'title': a.title,
                    'level': a.level.value,
                    'timestamp': a.timestamp,
                    'acknowledged': a.acknowledged
                }
                for a in active_alerts[-10:]  # 最近10个告警
            ]
        }
    
    def _calculate_security_score(self, events: List[SecurityEvent], alerts: List[SecurityAlert]) -> float:
        """计算安全评分"""
        base_score = 100.0
        
        # 根据事件数量扣分
        event_penalty = min(len(events) * 0.5, 30)  # 最多扣30分
        
        # 根据告警级别扣分
        alert_penalty = 0
        for alert in alerts:
            if alert.level == AlertLevel.EMERGENCY:
                alert_penalty += 20
            elif alert.level == AlertLevel.CRITICAL:
                alert_penalty += 10
            elif alert.level == AlertLevel.WARNING:
                alert_penalty += 5
            elif alert.level == AlertLevel.INFO:
                alert_penalty += 1
        
        alert_penalty = min(alert_penalty, 50)  # 最多扣50分
        
        final_score = max(base_score - event_penalty - alert_penalty, 0)
        return round(final_score, 1)
    
    def _determine_security_status(self, score: float, alerts: List[SecurityAlert]) -> str:
        """确定安全状态"""
        # 检查紧急告警
        emergency_alerts = [a for a in alerts if a.level == AlertLevel.EMERGENCY]
        if emergency_alerts:
            return "EMERGENCY"
        
        # 检查严重告警
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        if critical_alerts:
            return "CRITICAL"
        
        # 基于评分确定状态
        if score >= 90:
            return "EXCELLENT"
        elif score >= 80:
            return "GOOD"
        elif score >= 70:
            return "WARNING"
        elif score >= 60:
            return "POOR"
        else:
            return "CRITICAL"


class RealTimeMonitor:
    """实时监控器"""
    
    def __init__(self):
        self.is_running = False
        self.monitor_thread = None
        self.event_handlers: List[Callable] = []
        self.metric_handlers: List[Callable] = []
        self.alert_handlers: List[Callable] = []
        self.event_queue = queue.Queue(maxsize=1000)
        self.metric_queue = queue.Queue(maxsize=1000)
    
    def start(self):
        """启动实时监控"""
        if not self.is_running:
            self.is_running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
    
    def stop(self):
        """停止实时监控"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
    
    def add_event_handler(self, handler: Callable):
        """添加事件处理器"""
        self.event_handlers.append(handler)
    
    def add_metric_handler(self, handler: Callable):
        """添加指标处理器"""
        self.metric_handlers.append(handler)
    
    def add_alert_handler(self, handler: Callable):
        """添加告警处理器"""
        self.alert_handlers.append(handler)
    
    def process_event(self, event: SecurityEvent):
        """处理事件"""
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            # 队列满时丢弃最旧的事件
            try:
                self.event_queue.get_nowait()
                self.event_queue.put_nowait(event)
            except queue.Empty:
                pass
    
    def process_metric(self, metric: SecurityMetric):
        """处理指标"""
        try:
            self.metric_queue.put_nowait(metric)
        except queue.Full:
            # 队列满时丢弃最旧的指标
            try:
                self.metric_queue.get_nowait()
                self.metric_queue.put_nowait(metric)
            except queue.Empty:
                pass
    
    def _monitor_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                # 处理事件
                while not self.event_queue.empty():
                    try:
                        event = self.event_queue.get_nowait()
                        for handler in self.event_handlers:
                            try:
                                handler(event)
                            except Exception:
                                pass
                    except queue.Empty:
                        break
                
                # 处理指标
                while not self.metric_queue.empty():
                    try:
                        metric = self.metric_queue.get_nowait()
                        for handler in self.metric_handlers:
                            try:
                                handler(metric)
                            except Exception:
                                pass
                    except queue.Empty:
                        break
                
                time.sleep(1)  # 1秒检查一次
                
            except Exception:
                time.sleep(5)  # 错误时等待5秒


class SecurityReport:
    """安全报告"""
    
    @staticmethod
    def generate_security_report(
        events: List[SecurityEvent],
        metrics: List[SecurityMetric],
        alerts: List[SecurityAlert],
        start_time: float,
        end_time: float
    ) -> dict:
        """生成安全报告"""
        # 过滤时间范围内的数据
        filtered_events = [
            e for e in events
            if start_time <= e.timestamp <= end_time
        ]
        
        filtered_metrics = [
            m for m in metrics
            if start_time <= m.timestamp <= end_time
        ]
        
        filtered_alerts = [
            a for a in alerts
            if start_time <= a.timestamp <= end_time
        ]
        
        # 统计分析
        event_stats = SecurityReport._analyze_events(filtered_events)
        metric_stats = SecurityReport._analyze_metrics(filtered_metrics)
        alert_stats = SecurityReport._analyze_alerts(filtered_alerts)
        
        return {
            'report_period': {
                'start_time': start_time,
                'end_time': end_time,
                'duration_hours': (end_time - start_time) / 3600
            },
            'summary': {
                'total_events': len(filtered_events),
                'total_metrics': len(filtered_metrics),
                'total_alerts': len(filtered_alerts),
                'security_incidents': len([a for a in filtered_alerts if a.level in [AlertLevel.CRITICAL, AlertLevel.EMERGENCY]])
            },
            'event_analysis': event_stats,
            'metric_analysis': metric_stats,
            'alert_analysis': alert_stats,
            'recommendations': SecurityReport._generate_recommendations(filtered_events, filtered_alerts)
        }
    
    @staticmethod
    def _analyze_events(events: List[SecurityEvent]) -> dict:
        """分析事件"""
        if not events:
            return {'total': 0}
        
        # 事件类型分布
        type_counts = defaultdict(int)
        source_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        hourly_counts = defaultdict(int)
        
        for event in events:
            type_counts[event.event_type.value] += 1
            source_counts[event.source] += 1
            severity_counts[event.severity] += 1
            
            # 按小时统计
            hour = int(event.timestamp) // 3600 * 3600
            hourly_counts[hour] += 1
        
        return {
            'total': len(events),
            'by_type': dict(type_counts),
            'by_source': dict(source_counts),
            'by_severity': dict(severity_counts),
            'hourly_distribution': dict(hourly_counts),
            'top_sources': sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        }
    
    @staticmethod
    def _analyze_metrics(metrics: List[SecurityMetric]) -> dict:
        """分析指标"""
        if not metrics:
            return {'total': 0}
        
        # 指标统计
        metric_counts = defaultdict(int)
        avg_values = defaultdict(list)
        
        for metric in metrics:
            metric_counts[metric.name] += 1
            avg_values[metric.name].append(metric.value)
        
        # 计算平均值
        metric_averages = {}
        for name, values in avg_values.items():
            metric_averages[name] = sum(values) / len(values) if values else 0
        
        return {
            'total': len(metrics),
            'by_name': dict(metric_counts),
            'averages': metric_averages
        }
    
    @staticmethod
    def _analyze_alerts(alerts: List[SecurityAlert]) -> dict:
        """分析告警"""
        if not alerts:
            return {'total': 0}
        
        # 告警统计
        level_counts = defaultdict(int)
        resolved_count = 0
        acknowledged_count = 0
        
        for alert in alerts:
            level_counts[alert.level.value] += 1
            if alert.resolved:
                resolved_count += 1
            if alert.acknowledged:
                acknowledged_count += 1
        
        return {
            'total': len(alerts),
            'by_level': dict(level_counts),
            'resolved': resolved_count,
            'acknowledged': acknowledged_count,
            'resolution_rate': resolved_count / len(alerts) if alerts else 0
        }
    
    @staticmethod
    def _generate_recommendations(events: List[SecurityEvent], alerts: List[SecurityAlert]) -> List[dict]:
        """生成建议"""
        recommendations = []
        
        # 基于事件分析
        auth_failures = [e for e in events if e.event_type == SecurityEventType.AUTHENTICATION_FAILURE]
        if len(auth_failures) > 10:
            recommendations.append({
                'category': 'AUTHENTICATION',
                'priority': 'HIGH',
                'title': '加强身份认证安全',
                'description': f'检测到{len(auth_failures)}次认证失败，建议加强认证安全措施'
            })
        
        # 基于告警分析
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL and not a.resolved]
        if critical_alerts:
            recommendations.append({
                'category': 'INCIDENT_RESPONSE',
                'priority': 'CRITICAL',
                'title': '处理严重告警',
                'description': f'有{len(critical_alerts)}个严重告警未解决，需要立即处理'
            })
        
        return recommendations


class SecurityMonitoring:
    """安全监控系统"""
    
    def __init__(self, config_path: str = "/tmp/security_monitoring"):
        self.config_path = config_path
        self.events: deque = deque(maxlen=10000)  # 保持最近10000个事件
        self.metrics: deque = deque(maxlen=10000)  # 保持最近10000个指标
        self.alerts: List[SecurityAlert] = []
        self.monitoring_rules: Dict[str, MonitoringRule] = {}
        
        # 组件
        self.dashboard = SecurityDashboard()
        self.real_time_monitor = RealTimeMonitor()
        
        # 统计
        self.statistics = {
            'total_events': 0,
            'total_metrics': 0,
            'total_alerts': 0,
            'monitoring_uptime': 0,
            'last_event': None,
            'last_metric': None,
            'last_alert': None
        }
        
        # 状态
        self.is_monitoring = False
        self.start_time = None
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 初始化默认规则
        self._initialize_default_rules()
    
    def _initialize_default_rules(self):
        """初始化默认监控规则"""
        default_rules = [
            MonitoringRule(
                rule_id="auth_failure_burst",
                name="认证失败突发",
                description="短时间内大量认证失败",
                event_types=[SecurityEventType.AUTHENTICATION_FAILURE],
                conditions=[
                    {'type': 'event_count', 'threshold': 5}
                ],
                alert_level=AlertLevel.WARNING,
                time_window=300  # 5分钟
            ),
            
            MonitoringRule(
                rule_id="privilege_escalation",
                name="权限提升检测",
                description="检测到权限提升尝试",
                event_types=[SecurityEventType.PRIVILEGE_ESCALATION],
                conditions=[
                    {'type': 'event_count', 'threshold': 1}
                ],
                alert_level=AlertLevel.CRITICAL,
                time_window=60  # 1分钟
            ),
            
            MonitoringRule(
                rule_id="unauthorized_access",
                name="未授权访问检测",
                description="检测到未授权访问尝试",
                event_types=[SecurityEventType.UNAUTHORIZED_ACCESS],
                conditions=[
                    {'type': 'event_count', 'threshold': 3}
                ],
                alert_level=AlertLevel.WARNING,
                time_window=300  # 5分钟
            ),
            
            MonitoringRule(
                rule_id="policy_violations",
                name="策略违规检测",
                description="检测到多次策略违规",
                event_types=[SecurityEventType.POLICY_VIOLATION],
                conditions=[
                    {'type': 'event_count', 'threshold': 5}
                ],
                alert_level=AlertLevel.WARNING,
                time_window=600  # 10分钟
            ),
            
            MonitoringRule(
                rule_id="threat_detection",
                name="威胁检测告警",
                description="检测到安全威胁",
                event_types=[SecurityEventType.THREAT_DETECTED],
                conditions=[
                    {'type': 'event_count', 'threshold': 1}
                ],
                alert_level=AlertLevel.CRITICAL,
                time_window=60  # 1分钟
            )
        ]
        
        for rule in default_rules:
            self.monitoring_rules[rule.rule_id] = rule
    
    def start_monitoring(self):
        """启动监控"""
        with self._lock:
            if not self.is_monitoring:
                self.is_monitoring = True
                self.start_time = time.time()
                self.real_time_monitor.start()
                
                # 添加处理器
                self.real_time_monitor.add_event_handler(self._handle_event)
                self.real_time_monitor.add_metric_handler(self._handle_metric)
    
    def stop_monitoring(self):
        """停止监控"""
        with self._lock:
            if self.is_monitoring:
                self.is_monitoring = False
                self.real_time_monitor.stop()
                
                if self.start_time:
                    self.statistics['monitoring_uptime'] += time.time() - self.start_time
    
    def log_event(self, event: SecurityEvent):
        """记录安全事件"""
        with self._lock:
            self.events.append(event)
            self.statistics['total_events'] += 1
            self.statistics['last_event'] = event.timestamp
            
            # 实时处理
            if self.is_monitoring:
                self.real_time_monitor.process_event(event)
    
    def log_metric(self, metric: SecurityMetric):
        """记录安全指标"""
        with self._lock:
            self.metrics.append(metric)
            self.statistics['total_metrics'] += 1
            self.statistics['last_metric'] = metric.timestamp
            
            # 实时处理
            if self.is_monitoring:
                self.real_time_monitor.process_metric(metric)
    
    def _handle_event(self, event: SecurityEvent):
        """处理事件"""
        # 评估监控规则
        recent_events = [
            e for e in self.events
            if (time.time() - e.timestamp) <= 600  # 最近10分钟
        ]
        
        recent_metrics = [
            m for m in self.metrics
            if (time.time() - m.timestamp) <= 600  # 最近10分钟
        ]
        
        for rule in self.monitoring_rules.values():
            alert = rule.evaluate(recent_events, recent_metrics)
            if alert:
                self._generate_alert(alert)
    
    def _handle_metric(self, metric: SecurityMetric):
        """处理指标"""
        # 可以在这里添加基于指标的规则评估
        pass
    
    def _generate_alert(self, alert: SecurityAlert):
        """生成告警"""
        with self._lock:
            self.alerts.append(alert)
            self.statistics['total_alerts'] += 1
            self.statistics['last_alert'] = alert.timestamp
    
    def get_monitoring_health(self) -> dict:
        """获取监控健康状态"""
        with self._lock:
            current_time = time.time()
            uptime = current_time - self.start_time if self.start_time else 0
            
            return {
                'is_active': self.is_monitoring,
                'uptime': uptime,
                'total_events': len(self.events),
                'total_metrics': len(self.metrics),
                'total_alerts': len(self.alerts),
                'active_alerts': len([a for a in self.alerts if not a.resolved]),
                'last_activity': max(
                    self.statistics.get('last_event', 0) or 0,
                    self.statistics.get('last_metric', 0) or 0
                )
            }
    
    def get_status(self) -> dict:
        """获取状态"""
        return self.get_monitoring_health()
    
    def get_security_dashboard(self) -> dict:
        """获取安全仪表板"""
        with self._lock:
            return self.dashboard.get_dashboard_data(
                list(self.events),
                list(self.metrics),
                self.alerts
            )
    
    def generate_monitoring_report(self) -> dict:
        """生成监控报告"""
        with self._lock:
            current_time = time.time()
            start_time = current_time - 86400  # 最近24小时
            
            report = SecurityReport.generate_security_report(
                list(self.events),
                list(self.metrics),
                self.alerts,
                start_time,
                current_time
            )
            
            # 添加监控特定信息
            report['monitoring_status'] = self.get_monitoring_health()
            report['dashboard_data'] = self.get_security_dashboard()
            
            return report


class SecurityMonitoringError(Exception):
    """安全监控错误"""
    pass


def create_security_monitoring(config_path: str = None) -> SecurityMonitoring:
    """
    创建安全监控系统
    
    Args:
        config_path: 配置路径
        
    Returns:
        SecurityMonitoring: 安全监控系统实例
    """
    return SecurityMonitoring(config_path or "/tmp/security_monitoring")