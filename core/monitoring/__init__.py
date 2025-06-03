"""
🚀 MarketPrism 统一监控管理模块
整合所有监控功能的统一入口

导出的主要类和函数:
- UnifiedMonitoringPlatform: 统一监控平台
- MonitoringFactory: 监控工厂
- MetricData: 监控指标数据
- AlertRule: 告警规则
- MonitoringLevel: 监控级别
- get_global_monitoring: 获取全局监控
- monitor/alert_on: 便捷监控函数
"""

from .unified_monitoring_platform import (
    UnifiedMonitoringPlatform,
    MonitoringFactory,
    MetricData,
    AlertRule,
    MonitoringLevel,
    get_global_monitoring,
    set_global_monitoring,
    monitor,
    alert_on
)

__all__ = [
    'UnifiedMonitoringPlatform',
    'MonitoringFactory',
    'MetricData', 
    'AlertRule',
    'MonitoringLevel',
    'get_global_monitoring',
    'set_global_monitoring',
    'monitor',
    'alert_on'
]

# 模块信息
__version__ = "2.0.0"
__description__ = "MarketPrism统一监控管理系统"
__author__ = "MarketPrism团队"
__created__ = "2025-06-01"

# 告警引擎
from .alerting.enhanced_alerting_engine import (
    EnhancedAlertingEngine,
    AlertSeverity,
    AlertRule,
    Alert,
    get_alerting_engine,
    alert
)
