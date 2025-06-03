"""
错误分类和严重程度定义

定义MarketPrism系统中的错误分类、严重程度、错误类型和恢复策略。
提供结构化的错误分类体系，便于错误统计、分析和处理。
"""

from enum import Enum, auto
from typing import Dict, List, Optional
from dataclasses import dataclass


class ErrorCategory(Enum):
    """错误分类枚举
    
    按照业务领域和技术层面对错误进行分类，便于统计和分析。
    """
    # 业务层错误
    BUSINESS = "business"                    # 业务逻辑错误
    VALIDATION = "validation"                # 数据验证错误
    CONFIGURATION = "configuration"          # 配置错误
    
    # 数据层错误  
    DATA_PROCESSING = "data_processing"      # 数据处理错误
    DATA_QUALITY = "data_quality"           # 数据质量错误
    STORAGE = "storage"                      # 存储系统错误
    
    # 网络层错误
    NETWORK = "network"                      # 网络连接错误
    API = "api"                              # API调用错误
    WEBSOCKET = "websocket"                  # WebSocket连接错误
    
    # 交易所相关错误
    EXCHANGE = "exchange"                    # 交易所接口错误
    MARKET_DATA = "market_data"              # 市场数据错误
    RATE_LIMIT = "rate_limit"                # 频率限制错误
    
    # 系统层错误
    SYSTEM = "system"                        # 系统级错误
    RESOURCE = "resource"                    # 资源不足错误
    PERFORMANCE = "performance"              # 性能问题
    
    # 安全相关错误
    SECURITY = "security"                    # 安全相关错误
    AUTHENTICATION = "authentication"        # 认证错误
    AUTHORIZATION = "authorization"          # 授权错误
    
    # 监控相关错误
    MONITORING = "monitoring"                # 监控系统错误
    LOGGING = "logging"                      # 日志系统错误
    
    # 未知错误
    UNKNOWN = "unknown"                      # 未分类错误


class ErrorSeverity(Enum):
    """错误严重程度枚举
    
    定义错误的严重程度，用于告警级别和处理优先级决策。
    """
    CRITICAL = "critical"        # 严重错误：系统无法继续运行
    HIGH = "high"               # 高级错误：功能严重受损
    MEDIUM = "medium"           # 中级错误：功能部分受损
    LOW = "low"                 # 低级错误：轻微影响
    INFO = "info"               # 信息级别：仅记录信息
    
    @property
    def priority(self) -> int:
        """获取严重程度对应的优先级数值"""
        priorities = {
            ErrorSeverity.CRITICAL: 5,
            ErrorSeverity.HIGH: 4,
            ErrorSeverity.MEDIUM: 3,
            ErrorSeverity.LOW: 2,
            ErrorSeverity.INFO: 1
        }
        return priorities[self]


class ErrorType(Enum):
    """错误类型枚举
    
    定义具体的错误类型，提供更细粒度的错误分类。
    """
    # 配置相关
    INVALID_CONFIG = auto()
    MISSING_CONFIG = auto()
    CONFIG_VALIDATION_FAILED = auto()
    
    # 网络相关
    CONNECTION_TIMEOUT = auto()
    CONNECTION_REFUSED = auto()
    DNS_RESOLUTION_FAILED = auto()
    SSL_ERROR = auto()
    
    # API相关
    API_KEY_INVALID = auto()
    API_RATE_LIMITED = auto()
    API_RESPONSE_INVALID = auto()
    API_UNAVAILABLE = auto()
    
    # 数据相关
    DATA_CORRUPTION = auto()
    DATA_FORMAT_INVALID = auto()
    DATA_MISSING = auto()
    DATA_INCONSISTENT = auto()
    
    # 存储相关
    DATABASE_CONNECTION_FAILED = auto()
    DATABASE_QUERY_FAILED = auto()
    DATABASE_TIMEOUT = auto()
    DISK_FULL = auto()
    
    # 系统相关
    MEMORY_EXHAUSTED = auto()
    CPU_OVERLOAD = auto()
    THREAD_POOL_EXHAUSTED = auto()
    PERMISSION_DENIED = auto()
    
    # 业务相关
    BUSINESS_RULE_VIOLATED = auto()
    WORKFLOW_INTERRUPTED = auto()
    STATE_INCONSISTENT = auto()
    
    # 未知错误
    UNKNOWN_ERROR = auto()


class RecoveryStrategy(Enum):
    """错误恢复策略枚举
    
    定义不同错误的恢复策略，指导自动错误恢复机制。
    """
    RETRY = "retry"                          # 重试操作
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避重试
    CIRCUIT_BREAKER = "circuit_breaker"      # 熔断器模式
    FAILOVER = "failover"                    # 故障转移
    GRACEFUL_DEGRADATION = "graceful_degradation"  # 优雅降级
    RESTART_COMPONENT = "restart_component"   # 重启组件
    MANUAL_INTERVENTION = "manual_intervention"  # 人工干预
    IGNORE = "ignore"                        # 忽略错误
    LOG_ONLY = "log_only"                    # 仅记录日志


@dataclass
class ErrorDefinition:
    """错误定义数据类
    
    定义一个错误类型的完整信息，包括分类、严重程度、描述等。
    """
    error_type: ErrorType
    category: ErrorCategory
    severity: ErrorSeverity
    description: str
    recovery_strategy: RecoveryStrategy
    retry_count: int = 3
    retry_delay: float = 1.0
    tags: Optional[List[str]] = None
    documentation_url: Optional[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class ErrorCategoryManager:
    """错误分类管理器
    
    管理错误定义、分类映射和错误统计。
    提供错误分类查询、统计分析等功能。
    """
    
    def __init__(self):
        self._error_definitions: Dict[ErrorType, ErrorDefinition] = {}
        self._category_mappings: Dict[ErrorCategory, List[ErrorType]] = {}
        self._severity_mappings: Dict[ErrorSeverity, List[ErrorType]] = {}
        self._initialize_default_definitions()
    
    def _initialize_default_definitions(self):
        """初始化默认错误定义"""
        default_definitions = [
            # 配置相关错误
            ErrorDefinition(
                ErrorType.INVALID_CONFIG,
                ErrorCategory.CONFIGURATION,
                ErrorSeverity.HIGH,
                "配置文件格式无效或包含非法值",
                RecoveryStrategy.MANUAL_INTERVENTION,
                tags=["config", "validation"]
            ),
            ErrorDefinition(
                ErrorType.MISSING_CONFIG,
                ErrorCategory.CONFIGURATION,
                ErrorSeverity.CRITICAL,
                "缺少必需的配置项",
                RecoveryStrategy.MANUAL_INTERVENTION,
                tags=["config", "missing"]
            ),
            
            # 网络相关错误
            ErrorDefinition(
                ErrorType.CONNECTION_TIMEOUT,
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                "网络连接超时",
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                retry_count=5,
                retry_delay=2.0,
                tags=["network", "timeout"]
            ),
            ErrorDefinition(
                ErrorType.CONNECTION_REFUSED,
                ErrorCategory.NETWORK,
                ErrorSeverity.HIGH,
                "网络连接被拒绝",
                RecoveryStrategy.RETRY,
                retry_count=3,
                tags=["network", "connection"]
            ),
            
            # API相关错误
            ErrorDefinition(
                ErrorType.API_RATE_LIMITED,
                ErrorCategory.RATE_LIMIT,
                ErrorSeverity.MEDIUM,
                "API请求频率超过限制",
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                retry_count=10,
                retry_delay=5.0,
                tags=["api", "rate_limit"]
            ),
            ErrorDefinition(
                ErrorType.API_KEY_INVALID,
                ErrorCategory.API,
                ErrorSeverity.CRITICAL,
                "API密钥无效或已过期",
                RecoveryStrategy.MANUAL_INTERVENTION,
                tags=["api", "authentication"]
            ),
            
            # 数据相关错误
            ErrorDefinition(
                ErrorType.DATA_CORRUPTION,
                ErrorCategory.DATA_QUALITY,
                ErrorSeverity.HIGH,
                "数据损坏或格式错误",
                RecoveryStrategy.GRACEFUL_DEGRADATION,
                tags=["data", "corruption"]
            ),
            ErrorDefinition(
                ErrorType.DATA_FORMAT_INVALID,
                ErrorCategory.DATA_PROCESSING,
                ErrorSeverity.MEDIUM,
                "数据格式不符合预期",
                RecoveryStrategy.LOG_ONLY,
                tags=["data", "format"]
            ),
            
            # 存储相关错误
            ErrorDefinition(
                ErrorType.DATABASE_CONNECTION_FAILED,
                ErrorCategory.STORAGE,
                ErrorSeverity.CRITICAL,
                "数据库连接失败",
                RecoveryStrategy.RETRY,
                retry_count=5,
                retry_delay=10.0,
                tags=["database", "connection"]
            ),
            ErrorDefinition(
                ErrorType.DATABASE_TIMEOUT,
                ErrorCategory.STORAGE,
                ErrorSeverity.MEDIUM,
                "数据库操作超时",
                RecoveryStrategy.RETRY,
                retry_count=3,
                retry_delay=5.0,
                tags=["database", "timeout"]
            ),
            
            # 系统相关错误
            ErrorDefinition(
                ErrorType.MEMORY_EXHAUSTED,
                ErrorCategory.RESOURCE,
                ErrorSeverity.CRITICAL,
                "系统内存不足",
                RecoveryStrategy.RESTART_COMPONENT,
                tags=["system", "memory"]
            ),
            ErrorDefinition(
                ErrorType.CPU_OVERLOAD,
                ErrorCategory.PERFORMANCE,
                ErrorSeverity.HIGH,
                "CPU使用率过高",
                RecoveryStrategy.GRACEFUL_DEGRADATION,
                tags=["system", "cpu"]
            )
        ]
        
        for definition in default_definitions:
            self.register_error_definition(definition)
    
    def register_error_definition(self, definition: ErrorDefinition):
        """注册错误定义"""
        self._error_definitions[definition.error_type] = definition
        
        # 更新分类映射
        if definition.category not in self._category_mappings:
            self._category_mappings[definition.category] = []
        if definition.error_type not in self._category_mappings[definition.category]:
            self._category_mappings[definition.category].append(definition.error_type)
        
        # 更新严重程度映射
        if definition.severity not in self._severity_mappings:
            self._severity_mappings[definition.severity] = []
        if definition.error_type not in self._severity_mappings[definition.severity]:
            self._severity_mappings[definition.severity].append(definition.error_type)
    
    def get_error_definition(self, error_type: ErrorType) -> Optional[ErrorDefinition]:
        """获取错误定义"""
        return self._error_definitions.get(error_type)
    
    def get_errors_by_category(self, category: ErrorCategory) -> List[ErrorType]:
        """获取指定分类的所有错误类型"""
        return self._category_mappings.get(category, [])
    
    def get_errors_by_severity(self, severity: ErrorSeverity) -> List[ErrorType]:
        """获取指定严重程度的所有错误类型"""
        return self._severity_mappings.get(severity, [])
    
    def get_all_categories(self) -> List[ErrorCategory]:
        """获取所有错误分类"""
        return list(self._category_mappings.keys())
    
    def get_all_severities(self) -> List[ErrorSeverity]:
        """获取所有严重程度"""
        return list(self._severity_mappings.keys())
    
    def get_error_statistics(self) -> Dict[str, int]:
        """获取错误定义统计信息"""
        return {
            "total_definitions": len(self._error_definitions),
            "categories": len(self._category_mappings),
            "severities": len(self._severity_mappings),
            "critical_errors": len(self.get_errors_by_severity(ErrorSeverity.CRITICAL)),
            "high_errors": len(self.get_errors_by_severity(ErrorSeverity.HIGH))
        }


# 全局错误分类管理器实例
_global_category_manager = None


def get_global_category_manager() -> ErrorCategoryManager:
    """获取全局错误分类管理器"""
    global _global_category_manager
    if _global_category_manager is None:
        _global_category_manager = ErrorCategoryManager()
    return _global_category_manager


def reset_global_category_manager():
    """重置全局错误分类管理器（主要用于测试）"""
    global _global_category_manager
    _global_category_manager = None