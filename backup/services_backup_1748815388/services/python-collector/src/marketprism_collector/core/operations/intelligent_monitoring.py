"""
智能监控系统 - Week 5 Day 8
提供全方位系统监控、智能预警、异常检测等功能
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

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MetricType(Enum):
    """监控指标类型"""
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage" 
    DISK_USAGE = "disk_usage"
    NETWORK_IO = "network_io"
    APPLICATION_RESPONSE_TIME = "app_response_time"
    DATABASE_CONNECTIONS = "db_connections"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    QUEUE_LENGTH = "queue_length"
    CACHE_HIT_RATE = "cache_hit_rate"
    ACTIVE_USERS = "active_users"
    API_LATENCY = "api_latency"
    SECURITY_EVENTS = "security_events"
    COMPLIANCE_SCORE = "compliance_score"
    AVAILABILITY = "availability"


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertChannel(Enum):
    """告警渠道"""
    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    WEBHOOK = "webhook"
    DASHBOARD = "dashboard"


@dataclass
class MonitoringMetric:
    """监控指标数据模型"""
    metric_id: str
    metric_type: MetricType
    value: float
    timestamp: datetime
    source: str
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str
    metric_type: MetricType
    condition: str  # >, <, >=, <=, ==
    threshold: float
    duration: int  # 持续时间(秒)
    alert_level: AlertLevel
    channels: List[AlertChannel]
    enabled: bool = True
    suppress_until: Optional[datetime] = None


@dataclass
class Alert:
    """告警信息"""
    alert_id: str
    rule_id: str
    metric: MonitoringMetric
    level: AlertLevel
    message: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    acknowledgment: bool = False
    acknowledged_by: str = ""
    acknowledged_at: Optional[datetime] = None


@dataclass
class MonitoringDashboard:
    """监控仪表板"""
    dashboard_id: str
    name: str
    metrics: List[MetricType]
    refresh_interval: int  # 刷新间隔(秒)
    layout: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, str] = field(default_factory=dict)


@dataclass
class AnomalyDetectionConfig:
    """异常检测配置"""
    metric_type: MetricType
    detection_method: str  # "statistical", "ml", "threshold"
    sensitivity: float  # 0.0-1.0
    learning_period: int  # 学习周期(小时)
    min_data_points: int = 50
    confidence_threshold: float = 0.95


class IntelligentMonitoring:
    """智能监控系统"""
    
    def __init__(self):
        self.metrics_storage: Dict[str, List[MonitoringMetric]] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.dashboards: Dict[str, MonitoringDashboard] = {}
        self.anomaly_configs: Dict[MetricType, AnomalyDetectionConfig] = {}
        self.baseline_data: Dict[MetricType, Dict[str, float]] = {}
        self.alert_history: List[Alert] = []
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 初始化默认配置
        self._initialize_default_configs()
        logger.info("智能监控系统初始化完成")
    
    def _initialize_default_configs(self):
        """初始化默认配置"""
        
        # 默认告警规则
        default_rules = [
            AlertRule(
                rule_id="cpu_high",
                metric_type=MetricType.CPU_USAGE,
                condition=">=",
                threshold=85.0,
                duration=300,
                alert_level=AlertLevel.WARNING,
                channels=[AlertChannel.EMAIL, AlertChannel.DASHBOARD]
            ),
            AlertRule(
                rule_id="memory_critical",
                metric_type=MetricType.MEMORY_USAGE,
                condition=">=",
                threshold=95.0,
                duration=60,
                alert_level=AlertLevel.CRITICAL,
                channels=[AlertChannel.SMS, AlertChannel.SLACK, AlertChannel.WEBHOOK]
            ),
            AlertRule(
                rule_id="error_rate_high",
                metric_type=MetricType.ERROR_RATE,
                condition=">",
                threshold=5.0,
                duration=120,
                alert_level=AlertLevel.ERROR,
                channels=[AlertChannel.EMAIL, AlertChannel.SLACK]
            ),
            AlertRule(
                rule_id="response_time_slow",
                metric_type=MetricType.APPLICATION_RESPONSE_TIME,
                condition=">",
                threshold=2000.0,
                duration=180,
                alert_level=AlertLevel.WARNING,
                channels=[AlertChannel.DASHBOARD, AlertChannel.EMAIL]
            )
        ]
        
        for rule in default_rules:
            self.alert_rules[rule.rule_id] = rule
        
        # 默认异常检测配置
        default_anomaly_configs = [
            AnomalyDetectionConfig(
                metric_type=MetricType.CPU_USAGE,
                detection_method="statistical",
                sensitivity=0.8,
                learning_period=24
            ),
            AnomalyDetectionConfig(
                metric_type=MetricType.MEMORY_USAGE,
                detection_method="statistical",
                sensitivity=0.9,
                learning_period=48
            ),
            AnomalyDetectionConfig(
                metric_type=MetricType.APPLICATION_RESPONSE_TIME,
                detection_method="ml",
                sensitivity=0.7,
                learning_period=12
            )
        ]
        
        for config in default_anomaly_configs:
            self.anomaly_configs[config.metric_type] = config
        
        # 默认仪表板
        self.dashboards["system_overview"] = MonitoringDashboard(
            dashboard_id="system_overview",
            name="系统概览",
            metrics=[
                MetricType.CPU_USAGE,
                MetricType.MEMORY_USAGE,
                MetricType.DISK_USAGE,
                MetricType.NETWORK_IO
            ],
            refresh_interval=30
        )
        
        self.dashboards["application_performance"] = MonitoringDashboard(
            dashboard_id="application_performance",
            name="应用性能",
            metrics=[
                MetricType.APPLICATION_RESPONSE_TIME,
                MetricType.THROUGHPUT,
                MetricType.ERROR_RATE,
                MetricType.API_LATENCY
            ],
            refresh_interval=10
        )
    
    def collect_metric(self, metric: MonitoringMetric) -> bool:
        """收集监控指标"""
        try:
            metric_key = f"{metric.metric_type.value}_{metric.source}"
            
            if metric_key not in self.metrics_storage:
                self.metrics_storage[metric_key] = []
            
            self.metrics_storage[metric_key].append(metric)
            
            # 保留最近1000个数据点
            if len(self.metrics_storage[metric_key]) > 1000:
                self.metrics_storage[metric_key] = self.metrics_storage[metric_key][-1000:]
            
            logger.debug(f"收集监控指标: {metric.metric_type.value} = {metric.value}")
            return True
            
        except Exception as e:
            logger.error(f"收集监控指标失败: {e}")
            return False
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """获取监控统计信息"""
        try:
            stats = {
                "total_metrics": sum(len(metrics) for metrics in self.metrics_storage.values()),
                "active_alerts": len(self.active_alerts),
                "alert_rules": len(self.alert_rules),
                "dashboards": len(self.dashboards),
                "metric_types": len(set(key.split('_')[0] for key in self.metrics_storage.keys())),
                "sources": len(set(key.split('_', 1)[1] for key in self.metrics_storage.keys() if '_' in key)),
                "alert_history_count": len(self.alert_history),
                "anomaly_configs": len(self.anomaly_configs)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取监控统计失败: {e}")
            return {}
    
    def get_dashboard_data(self, dashboard_id: str) -> Optional[Dict[str, Any]]:
        """获取仪表板数据"""
        try:
            if dashboard_id not in self.dashboards:
                logger.warning(f"仪表板 {dashboard_id} 不存在")
                return None
            
            dashboard = self.dashboards[dashboard_id]
            dashboard_data = {
                "dashboard_id": dashboard.dashboard_id,
                "name": dashboard.name,
                "refresh_interval": dashboard.refresh_interval,
                "last_updated": datetime.now().isoformat(),
                "metrics_data": {},
                "alerts": [],
                "summary": {}
            }
            
            # 收集仪表板相关的指标数据
            for metric_type in dashboard.metrics:
                metric_data = []
                for key, metrics in self.metrics_storage.items():
                    if key.startswith(metric_type.value):
                        # 获取最近的指标数据
                        recent_metrics = sorted(metrics, key=lambda m: m.timestamp)[-20:]  # 最近20个数据点
                        for metric in recent_metrics:
                            metric_data.append({
                                "timestamp": metric.timestamp.isoformat(),
                                "value": metric.value,
                                "source": metric.source,
                                "tags": metric.tags
                            })
                
                dashboard_data["metrics_data"][metric_type.value] = metric_data
                
                # 计算该指标的统计信息
                if metric_data:
                    values = [m["value"] for m in metric_data]
                    dashboard_data["summary"][metric_type.value] = {
                        "current": values[-1] if values else 0,
                        "average": statistics.mean(values) if values else 0,
                        "max": max(values) if values else 0,
                        "min": min(values) if values else 0,
                        "count": len(values)
                    }
            
            # 获取相关的活跃告警
            for alert in self.active_alerts.values():
                if alert.metric.metric_type in dashboard.metrics:
                    dashboard_data["alerts"].append({
                        "alert_id": alert.alert_id,
                        "level": alert.level.value,
                        "message": alert.message,
                        "timestamp": alert.timestamp.isoformat(),
                        "metric_type": alert.metric.metric_type.value,
                        "metric_value": alert.metric.value
                    })
            
            logger.debug(f"获取仪表板数据: {dashboard_id}")
            return dashboard_data
            
        except Exception as e:
            logger.error(f"获取仪表板数据失败: {e}")
            return None


# 生成模拟监控数据的辅助函数
def generate_sample_metrics(monitoring_system: IntelligentMonitoring, count: int = 50):
    """生成示例监控指标"""
    metric_types = list(MetricType)
    sources = ["server-01", "server-02", "app-frontend", "app-backend", "database"]
    
    base_time = datetime.now() - timedelta(hours=1)
    
    for i in range(count):
        metric_type = random.choice(metric_types)
        source = random.choice(sources)
        timestamp = base_time + timedelta(minutes=i)
        
        # 根据指标类型生成合理的值
        if metric_type in [MetricType.CPU_USAGE, MetricType.MEMORY_USAGE, MetricType.DISK_USAGE]:
            value = random.uniform(10, 95)
        elif metric_type == MetricType.APPLICATION_RESPONSE_TIME:
            value = random.uniform(100, 3000)
        elif metric_type == MetricType.ERROR_RATE:
            value = random.uniform(0, 10)
        elif metric_type == MetricType.THROUGHPUT:
            value = random.uniform(100, 10000)
        else:
            value = random.uniform(0, 100)
        
        metric = MonitoringMetric(
            metric_id=f"metric_{i}",
            metric_type=metric_type,
            value=value,
            timestamp=timestamp,
            source=source,
            tags={"environment": "production", "region": "us-east-1"}
        )
        
        monitoring_system.collect_metric(metric)