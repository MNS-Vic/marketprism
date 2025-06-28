"""
MarketPrism 告警类型定义

定义告警系统中使用的各种数据类型和枚举
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from typing import Literal


class AlertSeverity(str, Enum):
    """告警严重程度"""
    CRITICAL = "critical"    # P1 - 严重：服务不可用
    HIGH = "high"           # P2 - 高：功能受影响
    MEDIUM = "medium"       # P3 - 中：性能下降
    LOW = "low"            # P4 - 低：潜在问题


class AlertStatus(str, Enum):
    """告警状态"""
    ACTIVE = "active"       # 活跃
    RESOLVED = "resolved"   # 已解决
    SUPPRESSED = "suppressed"  # 已抑制
    ACKNOWLEDGED = "acknowledged"  # 已确认


class AlertCategory(str, Enum):
    """告警类别"""
    SYSTEM = "system"           # 系统告警
    BUSINESS = "business"       # 业务告警
    PERFORMANCE = "performance" # 性能告警
    SECURITY = "security"       # 安全告警
    CAPACITY = "capacity"       # 容量告警


class NotificationChannel(str, Enum):
    """通知渠道"""
    EMAIL = "email"
    SLACK = "slack"
    DINGTALK = "dingtalk"
    SMS = "sms"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"


@dataclass
class AlertMetadata:
    """告警元数据"""
    source: str                    # 告警源
    component: str                 # 组件名称
    instance: Optional[str] = None # 实例标识
    environment: str = "production" # 环境
    tags: Dict[str, str] = field(default_factory=dict)  # 标签
    annotations: Dict[str, str] = field(default_factory=dict)  # 注释


class Alert(BaseModel):
    """基础告警类"""
    
    # 基本信息
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="告警名称")
    description: str = Field(..., description="告警描述")
    
    # 分类信息
    severity: AlertSeverity = Field(..., description="严重程度")
    category: AlertCategory = Field(..., description="告警类别")
    status: AlertStatus = Field(default=AlertStatus.ACTIVE, description="告警状态")
    
    # 时间信息
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    labels: Dict[str, str] = Field(default_factory=dict)
    
    # 指标信息
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    
    # 处理信息
    assignee: Optional[str] = None
    resolution_notes: Optional[str] = None
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def acknowledge(self, assignee: str) -> None:
        """确认告警"""
        self.status = AlertStatus.ACKNOWLEDGED
        self.assignee = assignee
        self.updated_at = datetime.now(timezone.utc)
    
    def resolve(self, resolution_notes: str = None) -> None:
        """解决告警"""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        if resolution_notes:
            self.resolution_notes = resolution_notes
    
    def suppress(self) -> None:
        """抑制告警"""
        self.status = AlertStatus.SUPPRESSED
        self.updated_at = datetime.now(timezone.utc)
    
    def get_duration(self) -> Optional[float]:
        """获取告警持续时间（秒）"""
        if self.resolved_at:
            return (self.resolved_at - self.created_at).total_seconds()
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()
    
    def is_critical(self) -> bool:
        """是否为严重告警"""
        return self.severity == AlertSeverity.CRITICAL
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.dict()


class SystemAlert(Alert):
    """系统告警"""
    category: Literal[AlertCategory.SYSTEM] = AlertCategory.SYSTEM
    
    # 系统特定字段
    service_name: Optional[str] = None
    host: Optional[str] = None
    process_id: Optional[int] = None


class BusinessAlert(Alert):
    """业务告警"""
    category: Literal[AlertCategory.BUSINESS] = AlertCategory.BUSINESS
    
    # 业务特定字段
    exchange: Optional[str] = None
    symbol: Optional[str] = None
    data_type: Optional[str] = None
    error_rate: Optional[float] = None


class PerformanceAlert(Alert):
    """性能告警"""
    category: Literal[AlertCategory.PERFORMANCE] = AlertCategory.PERFORMANCE
    
    # 性能特定字段
    response_time: Optional[float] = None
    throughput: Optional[float] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None


@dataclass
class AlertRule:
    """告警规则"""
    id: str
    name: str
    description: str
    severity: AlertSeverity
    category: AlertCategory
    metric_name: str
    condition: str  # 条件表达式，如 "> 0.8"
    threshold: float
    duration: int  # 持续时间（秒）
    enabled: bool = True
    tags: Dict[str, str] = field(default_factory=dict)
    
    def evaluate(self, metric_value: float, duration: int) -> bool:
        """评估告警条件"""
        if not self.enabled:
            return False
        
        # 简单的条件评估
        if self.condition.startswith('>'):
            threshold = float(self.condition[1:].strip())
            condition_met = metric_value > threshold
        elif self.condition.startswith('<'):
            threshold = float(self.condition[1:].strip())
            condition_met = metric_value < threshold
        elif self.condition.startswith('>='):
            threshold = float(self.condition[2:].strip())
            condition_met = metric_value >= threshold
        elif self.condition.startswith('<='):
            threshold = float(self.condition[2:].strip())
            condition_met = metric_value <= threshold
        elif self.condition.startswith('=='):
            threshold = float(self.condition[2:].strip())
            condition_met = abs(metric_value - threshold) < 0.001
        else:
            return False
        
        # 检查持续时间
        return condition_met and duration >= self.duration


class AlertPriority(str, Enum):
    """告警优先级（与严重程度对应）"""
    P1 = "P1"  # Critical
    P2 = "P2"  # High  
    P3 = "P3"  # Medium
    P4 = "P4"  # Low
    
    @classmethod
    def from_severity(cls, severity: AlertSeverity) -> 'AlertPriority':
        """从严重程度转换为优先级"""
        mapping = {
            AlertSeverity.CRITICAL: cls.P1,
            AlertSeverity.HIGH: cls.P2,
            AlertSeverity.MEDIUM: cls.P3,
            AlertSeverity.LOW: cls.P4
        }
        return mapping.get(severity, cls.P4)
