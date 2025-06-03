"""
🚀 MarketPrism 统一配置管理模块
整合所有配置功能的统一入口

导出的主要类和函数:
- UnifiedConfigManager: 统一配置管理器
- ConfigFactory: 配置工厂
- get_global_config: 获取全局配置
- get_config/set_config: 便捷配置操作
"""

from .unified_config_system import (
    UnifiedConfigManager,
    ConfigFactory,
    get_global_config,
    set_global_config,
    get_config,
    set_config
)

__all__ = [
    'UnifiedConfigManager',
    'ConfigFactory', 
    'get_global_config',
    'set_global_config',
    'get_config',
    'set_config'
]

# 模块信息
__version__ = "2.0.0"
__description__ = "MarketPrism统一配置管理系统"
__author__ = "MarketPrism团队"
__created__ = "2025-06-01"
