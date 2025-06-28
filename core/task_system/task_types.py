"""
MarketPrism 异步任务系统 - 任务类型定义
实现统一的任务事件模式和数据结构
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """任务类型"""
    # 数据收集任务
    DATA_COLLECTION = "data_collection"
    FUNDING_RATE_COLLECTION = "funding_rate_collection"
    OPEN_INTEREST_COLLECTION = "open_interest_collection"
    LIQUIDATION_MONITORING = "liquidation_monitoring"
    
    # 数据处理任务
    DATA_PROCESSING = "data_processing"
    DATA_CLEANING = "data_cleaning"
    INDICATOR_CALCULATION = "indicator_calculation"
    ANOMALY_DETECTION = "anomaly_detection"
    
    # 数据管理任务
    DATA_MIGRATION = "data_migration"
    DATA_ARCHIVE = "data_archive"
    DATA_CLEANUP = "data_cleanup"
    DATA_BACKUP = "data_backup"
    
    # 监控任务
    HEALTH_CHECK = "health_check"
    PERFORMANCE_MONITORING = "performance_monitoring"
    ALERT_EVALUATION = "alert_evaluation"
    METRICS_COLLECTION = "metrics_collection"
    
    # 系统维护任务
    SYSTEM_MAINTENANCE = "system_maintenance"
    INDEX_OPTIMIZATION = "index_optimization"
    LOG_ROTATION = "log_rotation"
    CACHE_CLEANUP = "cache_cleanup"


class TaskPriority(str, Enum):
    """任务优先级"""
    CRITICAL = "critical"    # 关键任务，立即执行
    HIGH = "high"           # 高优先级，优先执行
    MEDIUM = "medium"       # 中等优先级，正常执行
    LOW = "low"            # 低优先级，空闲时执行
    BACKGROUND = "background"  # 后台任务，最低优先级


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"         # 等待执行
    QUEUED = "queued"          # 已入队
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 执行失败
    CANCELLED = "cancelled"    # 已取消
    TIMEOUT = "timeout"        # 执行超时
    RETRYING = "retrying"      # 重试中


class TaskEventType(str, Enum):
    """任务事件类型"""
    CREATED = "created"        # 任务创建
    QUEUED = "queued"         # 任务入队
    STARTED = "started"       # 任务开始
    PROGRESS = "progress"     # 任务进度更新
    COMPLETED = "completed"   # 任务完成
    FAILED = "failed"         # 任务失败
    CANCELLED = "cancelled"   # 任务取消
    TIMEOUT = "timeout"       # 任务超时
    RETRY = "retry"           # 任务重试


@dataclass
class TaskMetadata:
    """任务元数据"""
    source: str                    # 任务来源
    creator: str                   # 创建者
    environment: str = "production"  # 环境
    tags: Dict[str, str] = field(default_factory=dict)  # 标签
    annotations: Dict[str, str] = field(default_factory=dict)  # 注释
    dependencies: List[str] = field(default_factory=list)  # 依赖任务ID


class AsyncTask(BaseModel):
    """异步任务定义"""
    
    # 基本信息
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="任务名称")
    description: str = Field(default="", description="任务描述")
    
    # 任务分类
    task_type: TaskType = Field(..., description="任务类型")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="任务优先级")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    
    # 执行配置
    target_service: str = Field(..., description="目标服务")
    target_endpoint: str = Field(..., description="目标端点")
    payload: Dict[str, Any] = Field(default_factory=dict, description="任务参数")
    
    # 调度配置
    cron_expression: Optional[str] = Field(None, description="Cron表达式")
    delay_seconds: Optional[int] = Field(None, description="延迟执行秒数")
    timeout_seconds: int = Field(default=300, description="超时时间")
    
    # 重试配置
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: int = Field(default=60, description="重试间隔秒数")
    retry_count: int = Field(default=0, description="当前重试次数")
    
    # 时间信息
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_retry_at: Optional[datetime] = None
    
    # 执行信息
    worker_id: Optional[str] = None
    execution_time: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    labels: Dict[str, str] = Field(default_factory=dict)
    
    def to_message(self) -> Dict[str, Any]:
        """转换为NATS消息格式"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "priority": self.priority,
            "status": self.status,
            "target_service": self.target_service,
            "target_endpoint": self.target_endpoint,
            "payload": self.payload,
            "cron_expression": self.cron_expression,
            "delay_seconds": self.delay_seconds,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "metadata": self.metadata,
            "labels": self.labels
        }
    
    @classmethod
    def from_message(cls, data: Dict[str, Any]) -> "AsyncTask":
        """从NATS消息创建任务"""
        # 处理时间字段
        if data.get("created_at"):
            data["created_at"] = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))
        if data.get("scheduled_at"):
            data["scheduled_at"] = datetime.fromisoformat(data["scheduled_at"].replace('Z', '+00:00'))
        
        return cls(**data)


class TaskEvent(BaseModel):
    """任务事件"""
    
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: TaskEventType = Field(..., description="事件类型")
    task_id: str = Field(..., description="任务ID")
    
    # 事件数据
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    worker_id: Optional[str] = None
    progress: Optional[float] = None  # 0.0 - 1.0
    message: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    # 任务快照
    task_snapshot: Optional[Dict[str, Any]] = None
    
    def to_message(self) -> Dict[str, Any]:
        """转换为NATS消息格式"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "worker_id": self.worker_id,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "task_snapshot": self.task_snapshot
        }


class TaskQueue(str, Enum):
    """任务队列"""
    # 按优先级分队列
    CRITICAL_QUEUE = "tasks.critical"
    HIGH_QUEUE = "tasks.high"
    MEDIUM_QUEUE = "tasks.medium"
    LOW_QUEUE = "tasks.low"
    BACKGROUND_QUEUE = "tasks.background"
    
    # 按类型分队列
    DATA_COLLECTION_QUEUE = "tasks.data_collection"
    DATA_PROCESSING_QUEUE = "tasks.data_processing"
    DATA_MANAGEMENT_QUEUE = "tasks.data_management"
    MONITORING_QUEUE = "tasks.monitoring"
    MAINTENANCE_QUEUE = "tasks.maintenance"
    
    # 特殊队列
    RETRY_QUEUE = "tasks.retry"
    DEAD_LETTER_QUEUE = "tasks.dead_letter"


class TaskSubjects:
    """任务主题定义"""
    
    # 任务队列主题
    TASK_QUEUES = {
        TaskPriority.CRITICAL: "tasks.queue.critical",
        TaskPriority.HIGH: "tasks.queue.high",
        TaskPriority.MEDIUM: "tasks.queue.medium",
        TaskPriority.LOW: "tasks.queue.low",
        TaskPriority.BACKGROUND: "tasks.queue.background"
    }
    
    # 任务事件主题
    TASK_EVENTS = "tasks.events.>"
    TASK_STATUS = "tasks.status.>"
    TASK_PROGRESS = "tasks.progress.>"
    
    # 工作者主题
    WORKER_HEARTBEAT = "workers.heartbeat.>"
    WORKER_STATUS = "workers.status.>"
    
    @classmethod
    def get_task_subject(cls, priority: TaskPriority) -> str:
        """获取任务队列主题"""
        return cls.TASK_QUEUES.get(priority, cls.TASK_QUEUES[TaskPriority.MEDIUM])
    
    @classmethod
    def get_event_subject(cls, task_id: str, event_type: TaskEventType) -> str:
        """获取事件主题"""
        return f"tasks.events.{task_id}.{event_type}"
    
    @classmethod
    def get_status_subject(cls, task_id: str) -> str:
        """获取状态主题"""
        return f"tasks.status.{task_id}"


# 预定义任务模板
TASK_TEMPLATES = {
    "data_migration": {
        "name": "数据迁移任务",
        "task_type": TaskType.DATA_MIGRATION,
        "priority": TaskPriority.HIGH,
        "target_service": "data-storage-service",
        "target_endpoint": "/api/v1/storage/migrate/hot-to-cold",
        "timeout_seconds": 1800,  # 30分钟
        "max_retries": 2
    },
    
    "health_check": {
        "name": "系统健康检查",
        "task_type": TaskType.HEALTH_CHECK,
        "priority": TaskPriority.MEDIUM,
        "target_service": "monitoring-service",
        "target_endpoint": "/api/v1/health/check",
        "timeout_seconds": 60,
        "max_retries": 3
    },
    
    "funding_rate_collection": {
        "name": "资金费率收集",
        "task_type": TaskType.FUNDING_RATE_COLLECTION,
        "priority": TaskPriority.HIGH,
        "target_service": "data-collector",
        "target_endpoint": "/api/v1/collect/funding-rates",
        "timeout_seconds": 300,
        "max_retries": 2
    },
    
    "data_cleanup": {
        "name": "数据清理任务",
        "task_type": TaskType.DATA_CLEANUP,
        "priority": TaskPriority.LOW,
        "target_service": "data-storage-service",
        "target_endpoint": "/api/v1/storage/lifecycle/cleanup",
        "timeout_seconds": 3600,  # 1小时
        "max_retries": 1
    }
}
