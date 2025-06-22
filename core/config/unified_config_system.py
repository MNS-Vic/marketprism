"""
统一配置系统

提供全局配置管理功能，包括配置工厂和便捷函数
"""

# 从unified_config_manager导入所需的类和函数
from .unified_config_manager import (
    UnifiedConfigManager,
    ConfigFactory,
    get_global_config,
    get_config,
    set_config
)

# 导出所有公共接口
__all__ = [
    'ConfigFactory',
    'get_global_config', 
    'get_config',
    'set_config',
    'UnifiedConfigManager'
]
