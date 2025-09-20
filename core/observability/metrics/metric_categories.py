"""
指标分类模块

定义标准化的指标分类和类型，确保所有指标遵循统一标准。
"""

from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, List, Optional, Set
from dataclasses import dataclass


class MetricType(Enum):
    """指标类型枚举"""
    COUNTER = auto()        # 计数器 - 只增不减
    GAUGE = auto()          # 仪表 - 可增可减
    HISTOGRAM = auto()      # 直方图 - 分布统计
    SUMMARY = auto()        # 摘要 - 分位数统计
    TIMER = auto()          # 计时器 - 时间相关


class MetricCategory(Enum):
    """指标分类枚举"""
    # 业务指标
    BUSINESS = "business"
    DATA_QUALITY = "data_quality"
    MARKET_DATA = "market_data"
    
    # 系统指标
    SYSTEM = "system"
    PERFORMANCE = "performance"
    RESOURCE = "resource"
    
    # 网络指标
    NETWORK = "network"
    API = "api"
    WEBSOCKET = "websocket"
    
    # 可靠性指标
    RELIABILITY = "reliability"
    ERROR = "error"
    HEALTH = "health"
    
    # 存储指标
    STORAGE = "storage"
    DATABASE = "database"
    CACHE = "cache"
    
    # 消息指标
    MESSAGE = "message"
    QUEUE = "queue"
    STREAM = "stream"


class MetricSubCategory(Enum):
    """指标子分类枚举"""
    # 业务子分类
    TRADE = "trade"
    ORDERBOOK = "orderbook"

    TICKER = "ticker"
    FUNDING_RATE = "funding_rate"
    LIQUIDATION = "liquidation"
    
    # 系统子分类
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK_IO = "network_io"
    
    # API子分类
    REST = "rest"
    WEBSOCKET_CONN = "websocket"
    RATE_LIMIT = "rate_limit"
    
    # 错误子分类
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    PROCESSING = "processing"
    
    # 存储子分类
    CLICKHOUSE = "clickhouse"
    NATS = "nats"
    REDIS = "redis"


class MetricSeverity(Enum):
    """指标严重性级别"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class MetricDefinition:
    """指标定义"""
    name: str
    metric_type: MetricType
    category: MetricCategory
    subcategory: Optional[MetricSubCategory] = None
    description: str = ""
    unit: str = ""
    labels: Optional[List[str]] = None
    severity: MetricSeverity = MetricSeverity.INFO
    help_text: str = ""
    tags: Optional[Set[str]] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = []
        if self.tags is None:
            self.tags = set()
            
    @property
    def full_name(self) -> str:
        """获取完整指标名称"""
        parts = ["marketprism"]
        
        if self.category:
            parts.append(self.category.value)
            
        if self.subcategory:
            parts.append(self.subcategory.value)
            
        parts.append(self.name)
        
        return "_".join(parts)
    
    @property
    def prometheus_name(self) -> str:
        """获取Prometheus标准名称"""
        return self.full_name.lower().replace("-", "_")


class StandardMetrics:
    """标准指标定义库"""
    
    # 业务指标
    MESSAGES_PROCESSED = MetricDefinition(
        name="messages_processed_total",
        metric_type=MetricType.COUNTER,
        category=MetricCategory.BUSINESS,
        description="处理的消息总数",
        labels=["exchange", "symbol", "data_type"],
        help_text="按交易所、交易对和数据类型分组的处理消息数"
    )
    
    DATA_POINTS_COLLECTED = MetricDefinition(
        name="data_points_collected_total",
        metric_type=MetricType.COUNTER,
        category=MetricCategory.DATA_QUALITY,
        description="收集的数据点总数",
        labels=["source", "data_type"],
        help_text="从各数据源收集的数据点总数"
    )
    
    # 性能指标
    PROCESSING_DURATION = MetricDefinition(
        name="processing_duration_seconds",
        metric_type=MetricType.HISTOGRAM,
        category=MetricCategory.PERFORMANCE,
        description="处理耗时分布",
        unit="seconds",
        labels=["operation", "status"],
        help_text="各种操作的处理时间分布"
    )
    
    MEMORY_USAGE = MetricDefinition(
        name="memory_usage_bytes",
        metric_type=MetricType.GAUGE,
        category=MetricCategory.RESOURCE,
        subcategory=MetricSubCategory.MEMORY,
        description="内存使用量",
        unit="bytes",
        labels=["component"],
        help_text="各组件的内存使用情况"
    )
    
    # 网络指标
    HTTP_REQUESTS = MetricDefinition(
        name="http_requests_total",
        metric_type=MetricType.COUNTER,
        category=MetricCategory.API,
        subcategory=MetricSubCategory.REST,
        description="HTTP请求总数",
        labels=["method", "endpoint", "status_code"],
        help_text="HTTP请求统计，按方法、端点和状态码分组"
    )
    
    WEBSOCKET_CONNECTIONS = MetricDefinition(
        name="websocket_connections_active",
        metric_type=MetricType.GAUGE,
        category=MetricCategory.NETWORK,
        subcategory=MetricSubCategory.WEBSOCKET_CONN,
        description="活跃WebSocket连接数",
        labels=["exchange", "channel"],
        help_text="当前活跃的WebSocket连接数量"
    )
    
    # 错误指标
    ERRORS_TOTAL = MetricDefinition(
        name="errors_total",
        metric_type=MetricType.COUNTER,
        category=MetricCategory.ERROR,
        description="错误总数",
        labels=["error_type", "component", "severity"],
        severity=MetricSeverity.HIGH,
        help_text="系统中发生的各类错误统计"
    )
    
    # 存储指标
    DATABASE_OPERATIONS = MetricDefinition(
        name="database_operations_total",
        metric_type=MetricType.COUNTER,
        category=MetricCategory.STORAGE,
        subcategory=MetricSubCategory.CLICKHOUSE,
        description="数据库操作总数",
        labels=["operation", "table", "status"],
        help_text="数据库操作统计，包括查询、插入等"
    )
    
    QUEUE_SIZE = MetricDefinition(
        name="queue_size",
        metric_type=MetricType.GAUGE,
        category=MetricCategory.MESSAGE,
        subcategory=MetricSubCategory.NATS,
        description="队列大小",
        labels=["queue_name", "stream"],
        help_text="消息队列中待处理的消息数量"
    )
    
    @classmethod
    def get_all_metrics(cls) -> List[MetricDefinition]:
        """获取所有标准指标定义"""
        return [
            getattr(cls, attr) for attr in dir(cls)
            if isinstance(getattr(cls, attr), MetricDefinition)
        ]
    
    @classmethod
    def get_metrics_by_category(cls, category: MetricCategory) -> List[MetricDefinition]:
        """按分类获取指标定义"""
        return [
            metric for metric in cls.get_all_metrics()
            if metric.category == category
        ]
    
    @classmethod
    def get_metrics_by_type(cls, metric_type: MetricType) -> List[MetricDefinition]:
        """按类型获取指标定义"""
        return [
            metric for metric in cls.get_all_metrics()
            if metric.metric_type == metric_type
        ]


class MetricNamingStandards:
    """指标命名标准"""
    
    # 命名规则
    NAMING_RULES = {
        "prefix": "marketprism",
        "separator": "_",
        "case": "lowercase",
        "max_length": 63,  # Prometheus限制
        "reserved_words": {"total", "count", "sum", "bucket", "created"}
    }
    
    # 后缀标准
    COUNTER_SUFFIXES = ["_total", "_created"]
    GAUGE_SUFFIXES = ["_active", "_current", "_size", "_usage"]
    HISTOGRAM_SUFFIXES = ["_duration", "_size", "_latency"]
    SUMMARY_SUFFIXES = ["_duration", "_size"]
    
    # 单位标准
    STANDARD_UNITS = {
        "time": ["seconds", "milliseconds", "microseconds"],
        "size": ["bytes", "kilobytes", "megabytes"],
        "rate": ["per_second", "per_minute", "per_hour"],
        "percentage": ["ratio", "percent"]
    }
    
    @staticmethod
    def validate_metric_name(name: str) -> Dict[str, bool]:
        """验证指标名称"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # 检查长度
        if len(name) > MetricNamingStandards.NAMING_RULES["max_length"]:
            validation_result["valid"] = False
            validation_result["errors"].append(f"名称过长: {len(name)} > 63")
        
        # 检查字符
        if not name.replace("_", "").replace("-", "").isalnum():
            validation_result["valid"] = False
            validation_result["errors"].append("包含非法字符")
        
        # 检查前缀
        if not name.startswith("marketprism_"):
            validation_result["warnings"].append("建议使用 marketprism_ 前缀")
        
        # 检查保留字
        for word in MetricNamingStandards.NAMING_RULES["reserved_words"]:
            if word in name and not name.endswith(f"_{word}"):
                validation_result["warnings"].append(f"包含保留字: {word}")
        
        return validation_result
    
    @staticmethod
    def suggest_metric_name(
        category: MetricCategory,
        metric_type: MetricType,
        base_name: str,
        subcategory: Optional[MetricSubCategory] = None
    ) -> str:
        """建议指标名称"""
        parts = ["marketprism"]
        
        if category:
            parts.append(category.value)
        
        if subcategory:
            parts.append(subcategory.value)
        
        parts.append(base_name)
        
        # 根据类型添加合适的后缀
        suggested_name = "_".join(parts)
        
        if metric_type == MetricType.COUNTER and not any(
            suggested_name.endswith(suffix) for suffix in MetricNamingStandards.COUNTER_SUFFIXES
        ):
            suggested_name += "_total"
        
        return suggested_name.lower()