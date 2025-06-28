"""
MarketPrism 智能告警系统

企业级智能监控告警系统，提供：
- 多级告警规则（P1-P4优先级）
- 基于机器学习的异常检测
- 告警聚合和去重机制
- 多渠道通知系统
- 故障预测和自动恢复建议
"""

from datetime import datetime, timezone
from .alert_manager import AlertManager, get_global_alert_manager
from .alert_rules import AlertRule, AlertPriority, AlertCondition, AlertRuleEngine
from .anomaly_detector import AnomalyDetector, MLAnomalyDetector
from .notification_manager import NotificationManager, NotificationChannel
from .alert_aggregator import AlertAggregator, AlertDeduplicator
from .failure_predictor import FailurePredictor, TrendAnalyzer
from .alert_types import (
    Alert, AlertStatus, AlertSeverity, AlertCategory,
    SystemAlert, BusinessAlert, PerformanceAlert
)

# 全局告警管理器实例
_global_alert_manager = None

def get_alert_manager() -> AlertManager:
    """获取全局告警管理器实例"""
    global _global_alert_manager
    if _global_alert_manager is None:
        _global_alert_manager = AlertManager()
    return _global_alert_manager

# 公开接口
__all__ = [
    # 核心管理器
    'AlertManager',
    'get_global_alert_manager',
    'get_alert_manager',
    
    # 告警规则
    'AlertRule',
    'AlertPriority', 
    'AlertCondition',
    'AlertRuleEngine',
    
    # 异常检测
    'AnomalyDetector',
    'MLAnomalyDetector',
    
    # 通知管理
    'NotificationManager',
    'NotificationChannel',
    
    # 告警聚合
    'AlertAggregator',
    'AlertDeduplicator',
    
    # 故障预测
    'FailurePredictor',
    'TrendAnalyzer',
    
    # 告警类型
    'Alert',
    'AlertStatus',
    'AlertSeverity', 
    'AlertCategory',
    'SystemAlert',
    'BusinessAlert',
    'PerformanceAlert'
]

__version__ = "1.0.0"
__author__ = "MarketPrism Team"
