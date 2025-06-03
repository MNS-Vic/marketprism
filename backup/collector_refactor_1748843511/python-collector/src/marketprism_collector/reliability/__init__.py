"""
MarketPrism 可靠性系统

企业级可靠性保障解决方案，提供：

🛡️ 核心组件：
- 熔断器系统 - 服务故障保护
- 智能限流器 - 流量控制和保护  
- 指数退避重试 - 智能失败恢复
- 冷存储监控 - 数据存储管理
- 负载均衡器 - 流量分发

🧠 智能分析：
- 统一可靠性管理器 - 组件协调和统一管理
- 性能分析器 - 性能监控和瓶颈识别
- 配置管理系统 - 统一配置和热重载
- 数据质量监控 - 数据完整性和一致性
- 异常检测系统 - 智能故障检测和告警

📊 监控告警：
- 实时健康监控
- 智能异常检测  
- 性能指标分析
- 优化建议生成
- 多渠道告警通知

🔧 企业特性：
- 高可用架构设计
- 自适应阈值调整
- 配置热重载
- 详细性能分析
- 故障自动恢复

Version: 3.0.0
SLA目标: 99.9%可用性
"""

# 核心组件
from .circuit_breaker import (
    MarketPrismCircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    OperationResult,
    CircuitBreakerOpenException,
    circuit_breaker
)

from .rate_limiter import (
    AdaptiveRateLimiter,
    RateLimitConfig,
    RequestPriority,
    RateLimiterManager
)

from .retry_handler import (
    ExponentialBackoffRetry,
    RetryPolicy,
    RetryErrorType,
    RetryableException
)

from .redundancy_manager import (
    ColdStorageMonitor,
    ColdStorageConfig,
    StorageType,
    MigrationStatus
)

from .load_balancer import (
    LoadBalancer,
    LoadBalancingStrategy,
    InstanceInfo
)

# 智能分析和管理
from .reliability_manager import (
    ReliabilityManager,
    ReliabilityConfig,
    HealthStatus,
    AlertLevel,
    DataQualityMetrics,
    AnomalyAlert,
    SystemMetrics,
    get_reliability_manager,
    initialize_reliability_manager
)

from .performance_analyzer import (
    PerformanceAnalyzer,
    PerformanceMetric,
    ResponseTimeStats,
    ThroughputStats,
    ResourceStats,
    PerformanceBottleneck,
    OptimizationSuggestion,
    PerformanceLevel,
    BottleneckType
)

from .config_manager import (
    ConfigManager,
    MarketPrismReliabilityConfig,
    GlobalConfig,
    MonitoringConfig,
    IntegrationConfig,
    AdvancedConfig,
    get_config_manager,
    initialize_config_manager
)

# 测试和验证
# from .test_integrated_reliability import (
#     IntegratedReliabilityTest,
#     MockDataSource, 
#     run_integrated_tests
# )

# 版本信息
__version__ = "3.0.0"
__author__ = "MarketPrism Team"
__description__ = "Enterprise-grade reliability system for MarketPrism"

# 公开接口
__all__ = [
    # 核心组件
    "MarketPrismCircuitBreaker",
    "CircuitBreakerConfig", 
    "CircuitState",
    "OperationResult",
    "CircuitBreakerOpenException",
    "circuit_breaker",
    
    "AdaptiveRateLimiter",
    "RateLimitConfig",
    "RequestPriority",
    "RateLimiterManager",
    
    "ExponentialBackoffRetry",
    "RetryPolicy",
    "RetryErrorType",
    "RetryableException",
    
    "ColdStorageMonitor",
    "ColdStorageConfig",
    "StorageType",
    "MigrationStatus",
    
    "LoadBalancer",
    "LoadBalancingStrategy",
    "InstanceInfo",
    
    # 智能分析和管理
    "ReliabilityManager",
    "ReliabilityConfig",
    "HealthStatus",
    "AlertLevel",
    "DataQualityMetrics",
    "AnomalyAlert", 
    "SystemMetrics",
    "get_reliability_manager",
    "initialize_reliability_manager",
    
    "PerformanceAnalyzer",
    "PerformanceMetric",
    "ResponseTimeStats",
    "ThroughputStats",
    "ResourceStats",
    "PerformanceBottleneck",
    "OptimizationSuggestion",
    "PerformanceLevel",
    "BottleneckType",
    
    "ConfigManager",
    "MarketPrismReliabilityConfig",
    "GlobalConfig",
    "MonitoringConfig", 
    "IntegrationConfig",
    "AdvancedConfig",
    "get_config_manager",
    "initialize_config_manager",
    
    # 测试和验证
    # "IntegratedReliabilityTest",
    # "MockDataSource", 
    # "run_integrated_tests"
]


def get_system_info():
    """获取可靠性系统信息"""
    return {
        "name": "MarketPrism Reliability System",
        "version": __version__,
        "description": __description__,
        "components": {
            "circuit_breaker": "服务故障保护",
            "rate_limiter": "智能流量控制",
            "retry_handler": "失败恢复机制",
            "cold_storage_monitor": "数据存储管理",
            "load_balancer": "流量分发",
            "reliability_manager": "统一可靠性管理",
            "performance_analyzer": "性能监控分析",
            "config_manager": "配置管理系统"
        },
        "features": [
            "99.9% SLA目标",
            "智能异常检测",
            "自适应阈值调整", 
            "性能瓶颈识别",
            "优化建议生成",
            "配置热重载",
            "多渠道告警",
            "故障自动恢复"
        ],
        "enterprise_ready": True,
        "production_tested": True
    }


def quick_setup(config_path: str = None) -> ReliabilityManager:
    """快速设置可靠性系统"""
    # 初始化配置管理器
    config_manager = initialize_config_manager(config_path)
    config = config_manager.load_config()
    
    # 初始化可靠性管理器
    reliability_manager = initialize_reliability_manager(config.reliability)
    
    return reliability_manager


async def health_check() -> dict:
    """系统健康检查"""
    manager = get_reliability_manager()
    if not manager:
        return {
            "status": "not_initialized",
            "message": "可靠性管理器未初始化",
            "healthy": False
        }
    
    if not manager.is_running:
        return {
            "status": "not_running", 
            "message": "可靠性管理器未运行",
            "healthy": False
        }
    
    status = manager.get_comprehensive_status()
    return {
        "status": "running",
        "healthy": True,
        "uptime_hours": status.get("uptime_hours", 0),
        "active_alerts": status.get("alerts", {}).get("active_count", 0),
        "components": status.get("components", {})
    } 