"""
统一配置管理模块

提供统一的配置管理功能：
- 配置基类和接口
- 配置注册表
- 配置验证框架
- 热重载机制
- 环境变量覆盖
"""

from datetime import datetime, timezone
from .unified_config_manager import UnifiedConfigManager
from .base_config import BaseConfig, ConfigType, ConfigMetadata
from .config_registry import ConfigRegistry
from .validators import ConfigValidator, ValidationError

# 全局配置管理器实例
global_config_manager = UnifiedConfigManager()

# 初始化全局配置管理器
global_config_manager.initialize()

def get_global_config_manager() -> UnifiedConfigManager:
    """获取全局配置管理器"""
    return global_config_manager

__all__ = [
    'UnifiedConfigManager',
    'get_global_config_manager',
    'BaseConfig', 
    'ConfigType',
    'ConfigMetadata',
    'ConfigRegistry',
    'ConfigValidator',
    'ValidationError'
]