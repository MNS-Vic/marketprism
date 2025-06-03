"""
MarketPrism 统一配置管理系统 2.0

企业级配置管理解决方案，支持版本控制、分布式部署、安全保障和智能监控。
"""

from .config_manager_v2 import UnifiedConfigManagerV2
from .repositories import (
    ConfigRepository,
    FileConfigRepository,
    DatabaseConfigRepository,
    RemoteConfigRepository,
    ConfigSourceManager
)
from .version_control import (
    ConfigCommit,
    ConfigBranch,
    ConfigMerge,
    ConfigHistory,
    ConfigVersionControl
)
from .distribution import (
    ConfigServer,
    ConfigClient,
    ConfigSync,
    ConfigSubscription
)
# TODO: Implement these modules in future days
# from .security import (
#     ConfigEncryption,
#     AccessControl,
#     ConfigVault,
#     SecurityAudit,
#     ConfigSecurity
# )
# from .monitoring import (
#     ConfigChangeDetector,
#     ConfigAlerts,
#     ConfigMetrics,
#     ConfigDashboard,
#     ConfigMonitoring
# )
# from .orchestration import (
#     DependencyManager,
#     RollbackManager,
#     ValidationOrchestrator,
#     UpdateOrchestrator,
#     ConfigOrchestrator
# )

__version__ = "2.0.0"
__author__ = "MarketPrism Team"

__all__ = [
    # 主要管理器
    "UnifiedConfigManagerV2",
    
    # 配置仓库
    "ConfigRepository",
    "FileConfigRepository", 
    "DatabaseConfigRepository",
    "RemoteConfigRepository",
    "ConfigSourceManager",
    
    # 版本控制
    "ConfigCommit",
    "ConfigBranch",
    "ConfigMerge", 
    "ConfigHistory",
    "ConfigVersionControl",
    
    # 分发系统
    "ConfigServer",
    "ConfigClient",
    "ConfigSync",
    "ConfigSubscription",
    
    # TODO: Add these when implemented
    # # 安全系统
    # "ConfigEncryption",
    # "AccessControl",
    # "ConfigVault",
    # "SecurityAudit",
    # "ConfigSecurity",
    # 
    # # 监控系统
    # "ConfigChangeDetector",
    # "ConfigAlerts", 
    # "ConfigMetrics",
    # "ConfigDashboard",
    # "ConfigMonitoring",
    # 
    # # 编排系统
    # "DependencyManager",
    # "RollbackManager",
    # "ValidationOrchestrator",
    # "UpdateOrchestrator", 
    # "ConfigOrchestrator",
]