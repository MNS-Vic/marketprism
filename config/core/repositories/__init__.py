"""
配置仓库系统

支持多种配置源的统一管理和访问。
"""

from .config_repository import (
    ConfigRepository, ConfigSource, ConfigEntry, ConfigFormat, 
    ConfigSourceType, ConfigTransaction
)
from .file_repository import FileConfigRepository
from .database_repository import DatabaseConfigRepository
from .remote_repository import RemoteConfigRepository
from .source_manager import ConfigSourceManager, MergeStrategy, FallbackStrategy

__all__ = [
    # 基础类和接口
    "ConfigRepository",
    "ConfigSource",
    "ConfigEntry", 
    "ConfigFormat",
    "ConfigSourceType",
    "ConfigTransaction",
    
    # 具体实现
    "FileConfigRepository",
    "DatabaseConfigRepository", 
    "RemoteConfigRepository",
    
    # 管理器
    "ConfigSourceManager",
    "MergeStrategy",
    "FallbackStrategy",
]