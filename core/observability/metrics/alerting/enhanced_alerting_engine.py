"""
🚨 MarketPrism 增强告警引擎
整合自 Week 7 Day 4统一告警引擎

创建时间: 2025-06-01 23:11:02
来源: week7_day4_unified_alerting_engine.py
整合到: core/monitoring/alerting/
"""

from typing import Dict, Any, Optional, List, Union, Callable
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass

# 告警级别
class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class AlertRule:
    """告警规则"""
    name: str
    condition: str
    severity: AlertSeverity
    threshold: float
    callback: Optional[Callable] = None
    enabled: bool = True
    labels_filter: Optional[Dict[str, str]] = None
    duration: int = 0
    notification_interval: int = 60

@dataclass
class Alert:
    """告警事件"""
    rule_name: str
    message: str
    severity: AlertSeverity
    timestamp: datetime
    metadata: Dict[str, Any]

class EnhancedAlertingEngine:
    """
    🚨 增强告警引擎
    
    整合自Week 7 Day 4的统一告警系统，
    提供企业级的告警管理能力。
    """
    
    def __init__(self):
        self.rules = {}
        self.alerts_history = []
        self.subscribers = []
        self.is_running = False
    
    def add_rule(self, rule: AlertRule) -> None:
        """添加告警规则"""
        self.rules[rule.name] = rule
    
    def trigger_alert(self, rule_name: str, message: str, metadata: Dict[str, Any] = None) -> None:
        """触发告警"""
        if rule_name not in self.rules:
            return
        
        rule = self.rules[rule_name]
        if not rule.enabled:
            return
        
        alert = Alert(
            rule_name=rule_name,
            message=message,
            severity=rule.severity,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        self.alerts_history.append(alert)
        
        # 执行回调
        if rule.callback:
            rule.callback(alert)
        
        # 通知订阅者
        for subscriber in self.subscribers:
            subscriber(alert)
    
    def get_active_alerts(self, severity: AlertSeverity = None) -> List[Alert]:
        """获取活跃告警"""
        alerts = self.alerts_history[-100:]  # 最近100个
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        return alerts

# 全局告警引擎实例
_global_alerting_engine = None

def get_alerting_engine() -> EnhancedAlertingEngine:
    """获取全局告警引擎"""
    global _global_alerting_engine
    if _global_alerting_engine is None:
        _global_alerting_engine = EnhancedAlertingEngine()
    return _global_alerting_engine

def alert(rule_name: str, message: str, metadata: Dict[str, Any] = None) -> None:
    """便捷告警函数"""
    get_alerting_engine().trigger_alert(rule_name, message, metadata)

# TODO: 从原始文件中提取更多功能
# 这里是基础版本，可以根据原始文件内容进一步完善
