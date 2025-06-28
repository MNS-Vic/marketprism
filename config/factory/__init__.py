"""
MarketPrism 统一配置工厂

提供统一的配置管理、加载、验证和热重载功能
"""

from .config_factory import ConfigFactory, ConfigManager
from .loaders import YamlLoader, EnvLoader, SecretLoader
from .validators import SchemaValidator, DependencyValidator, SecurityValidator
from .managers import HotReloadManager, VersionManager, CacheManager

__version__ = "1.0.0"
__author__ = "MarketPrism Team"

# 导出主要类
__all__ = [
    # 核心工厂类
    "ConfigFactory",
    "ConfigManager",
    
    # 配置加载器
    "YamlLoader",
    "EnvLoader", 
    "SecretLoader",
    
    # 配置验证器
    "SchemaValidator",
    "DependencyValidator",
    "SecurityValidator",
    
    # 配置管理器
    "HotReloadManager",
    "VersionManager",
    "CacheManager",
]

# 默认配置工厂实例
default_factory = None

def get_config_factory() -> ConfigFactory:
    """获取默认配置工厂实例"""
    global default_factory
    if default_factory is None:
        default_factory = ConfigFactory()
    return default_factory

def create_config_factory(config_root: str = None, 
                         environment: str = None,
                         enable_hot_reload: bool = True,
                         enable_validation: bool = True,
                         enable_caching: bool = True) -> ConfigFactory:
    """创建配置工厂实例"""
    return ConfigFactory(
        config_root=config_root,
        environment=environment,
        enable_hot_reload=enable_hot_reload,
        enable_validation=enable_validation,
        enable_caching=enable_caching
    )

# 便捷函数
def load_config(service_name: str, config_type: str = "service") -> dict:
    """加载指定服务的配置"""
    factory = get_config_factory()
    return factory.load_service_config(service_name, config_type)

def get_environment_config() -> dict:
    """获取当前环境配置"""
    factory = get_config_factory()
    return factory.get_environment_config()

def validate_config(config: dict, schema_name: str = None) -> bool:
    """验证配置"""
    factory = get_config_factory()
    return factory.validate_config(config, schema_name)

def reload_config(service_name: str = None) -> bool:
    """重新加载配置"""
    factory = get_config_factory()
    return factory.reload_config(service_name)

# 配置常量
CONFIG_ENVIRONMENTS = ["development", "staging", "production", "local"]
CONFIG_TYPES = ["service", "database", "monitoring", "security"]
DEFAULT_CONFIG_ROOT = "config"
DEFAULT_ENVIRONMENT = "development"
