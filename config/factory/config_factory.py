"""
MarketPrism 配置工厂核心实现
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime
import threading

from .loaders.yaml_loader import YamlLoader
from .loaders.env_loader import EnvLoader
from .loaders.secret_loader import SecretLoader
from .validators.schema_validator import SchemaValidator
from .validators.dependency_validator import DependencyValidator
from .validators.security_validator import SecurityValidator
from .managers.hot_reload_manager import HotReloadManager
from .managers.version_manager import VersionManager
from .managers.cache_manager import CacheManager


@dataclass
class ConfigMetadata:
    """配置元数据"""
    name: str
    type: str
    environment: str
    version: str
    loaded_at: datetime
    file_paths: List[Path] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    checksum: str = ""


class ConfigManager:
    """配置管理器 - 管理单个配置的生命周期"""
    
    def __init__(self, name: str, config_type: str, factory: 'ConfigFactory'):
        self.name = name
        self.type = config_type
        self.factory = factory
        self.metadata = None
        self.config_data = {}
        self.is_loaded = False
        self.lock = threading.RLock()
        
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        """加载配置"""
        with self.lock:
            if self.is_loaded and not force_reload:
                return self.config_data
            
            try:
                self.config_data = self._load_config()
                self.is_loaded = True
                self.logger.info(f"配置 {self.name} 加载成功")
                return self.config_data
            except Exception as e:
                self.logger.error(f"配置 {self.name} 加载失败: {e}")
                raise
    
    def _load_config(self) -> Dict[str, Any]:
        """内部配置加载逻辑"""
        # 1. 加载基础配置
        base_config = self.factory.yaml_loader.load_base_config()
        
        # 2. 加载环境配置
        env_config = self.factory.yaml_loader.load_environment_config(
            self.factory.environment
        )
        
        # 3. 加载服务配置
        service_config = self.factory.yaml_loader.load_service_config(
            self.name, self.type
        )
        
        # 4. 合并配置
        merged_config = self._merge_configs([
            base_config,
            env_config,
            service_config
        ])
        
        # 5. 应用环境变量覆盖
        final_config = self.factory.env_loader.apply_env_overrides(merged_config)
        
        # 6. 处理密钥
        final_config = self.factory.secret_loader.resolve_secrets(final_config)
        
        # 7. 创建元数据
        self.metadata = ConfigMetadata(
            name=self.name,
            type=self.type,
            environment=self.factory.environment,
            version="1.0.0",
            loaded_at=datetime.now()
        )
        
        return final_config
    
    def _merge_configs(self, configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并多个配置"""
        result = {}
        for config in configs:
            if config:
                result = self._deep_merge(result, config)
        return result
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def validate(self) -> bool:
        """验证配置"""
        if not self.is_loaded:
            return False
        
        try:
            # 模式验证
            if not self.factory.schema_validator.validate(self.config_data, self.type):
                return False
            
            # 依赖验证
            if not self.factory.dependency_validator.validate(self.name, self.config_data):
                return False
            
            # 安全验证
            if not self.factory.security_validator.validate(self.config_data):
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"配置验证失败: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置数据"""
        if not self.is_loaded:
            self.load()
        return self.config_data.copy()
    
    def get_metadata(self) -> Optional[ConfigMetadata]:
        """获取配置元数据"""
        return self.metadata


class ConfigFactory:
    """配置工厂 - 统一配置管理入口"""
    
    def __init__(self, 
                 config_root: str = None,
                 environment: str = None,
                 enable_hot_reload: bool = True,
                 enable_validation: bool = True,
                 enable_caching: bool = True):
        """
        初始化配置工厂
        
        Args:
            config_root: 配置根目录
            environment: 环境名称
            enable_hot_reload: 是否启用热重载
            enable_validation: 是否启用配置验证
            enable_caching: 是否启用配置缓存
        """
        self.config_root = Path(config_root or "config")
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.enable_hot_reload = enable_hot_reload
        self.enable_validation = enable_validation
        self.enable_caching = enable_caching
        
        self.logger = logging.getLogger(__name__)
        
        # 配置管理器存储
        self.config_managers: Dict[str, ConfigManager] = {}
        self.lock = threading.RLock()
        
        # 初始化组件
        self._init_components()
        
        self.logger.info(f"配置工厂初始化完成 - 环境: {self.environment}")
    
    def _init_components(self):
        """初始化配置工厂组件"""
        # 配置加载器
        self.yaml_loader = YamlLoader(self.config_root)
        self.env_loader = EnvLoader()
        self.secret_loader = SecretLoader()
        
        # 配置验证器
        if self.enable_validation:
            self.schema_validator = SchemaValidator(self.config_root / "schemas")
            self.dependency_validator = DependencyValidator()
            self.security_validator = SecurityValidator()
        
        # 配置管理器
        if self.enable_caching:
            self.cache_manager = CacheManager()
        
        if self.enable_hot_reload:
            self.hot_reload_manager = HotReloadManager(self)
            
        self.version_manager = VersionManager()
    
    def load_service_config(self, service_name: str, config_type: str = "service") -> Dict[str, Any]:
        """加载服务配置"""
        with self.lock:
            manager_key = f"{service_name}:{config_type}"
            
            if manager_key not in self.config_managers:
                self.config_managers[manager_key] = ConfigManager(
                    service_name, config_type, self
                )
            
            manager = self.config_managers[manager_key]
            config = manager.load()
            
            # 验证配置
            if self.enable_validation and not manager.validate():
                raise ValueError(f"配置验证失败: {service_name}")
            
            return config
    
    def get_environment_config(self) -> Dict[str, Any]:
        """获取环境配置"""
        return self.yaml_loader.load_environment_config(self.environment)
    
    def get_base_config(self) -> Dict[str, Any]:
        """获取基础配置"""
        return self.yaml_loader.load_base_config()
    
    def validate_config(self, config: Dict[str, Any], schema_name: str = None) -> bool:
        """验证配置"""
        if not self.enable_validation:
            return True
        
        try:
            return self.schema_validator.validate(config, schema_name)
        except Exception as e:
            self.logger.error(f"配置验证失败: {e}")
            return False
    
    def reload_config(self, service_name: str = None) -> bool:
        """重新加载配置"""
        try:
            with self.lock:
                if service_name:
                    # 重载指定服务配置
                    managers_to_reload = [
                        (key, manager) for key, manager in self.config_managers.items()
                        if manager.name == service_name
                    ]
                else:
                    # 重载所有配置
                    managers_to_reload = list(self.config_managers.items())
                
                for key, manager in managers_to_reload:
                    manager.load(force_reload=True)
                    self.logger.info(f"配置重载成功: {key}")
                
                return True
        except Exception as e:
            self.logger.error(f"配置重载失败: {e}")
            return False
    
    def list_services(self) -> List[str]:
        """列出所有可用的服务"""
        services_dir = self.config_root / "services"
        if not services_dir.exists():
            return []
        
        return [d.name for d in services_dir.iterdir() if d.is_dir()]
    
    def get_config_metadata(self, service_name: str, config_type: str = "service") -> Optional[ConfigMetadata]:
        """获取配置元数据"""
        manager_key = f"{service_name}:{config_type}"
        manager = self.config_managers.get(manager_key)
        return manager.get_metadata() if manager else None
    
    def start_hot_reload(self):
        """启动热重载监控"""
        if self.enable_hot_reload and hasattr(self, 'hot_reload_manager'):
            self.hot_reload_manager.start()
    
    def stop_hot_reload(self):
        """停止热重载监控"""
        if self.enable_hot_reload and hasattr(self, 'hot_reload_manager'):
            self.hot_reload_manager.stop()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取配置工厂统计信息"""
        return {
            "environment": self.environment,
            "config_root": str(self.config_root),
            "loaded_configs": len(self.config_managers),
            "services": self.list_services(),
            "features": {
                "hot_reload": self.enable_hot_reload,
                "validation": self.enable_validation,
                "caching": self.enable_caching
            }
        }
