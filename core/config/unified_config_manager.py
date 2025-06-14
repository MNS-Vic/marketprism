"""
统一配置管理器

提供统一的配置管理功能，包括：
- 配置加载和保存
- 热重载机制
- 环境变量覆盖
- 配置验证
- 配置合并
"""

from datetime import datetime, timezone
import os
import threading
import time
from typing import Dict, Any, Optional, List, Set, Type, Union, Callable
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict
import structlog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .base_config import BaseConfig, ConfigType, ConfigMetadata
from .config_registry import ConfigRegistry, config_registry
from .validators import ConfigValidator, ValidationResult, ValidationSeverity
from .hot_reload import ConfigHotReloadManager
from .env_override import EnvironmentOverrideManager


@dataclass
class ConfigLoadResult:
    """配置加载结果"""
    config_name: str
    success: bool
    config: Optional[BaseConfig] = None
    errors: List[str] = None
    warnings: List[str] = None
    load_time: datetime = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.load_time is None:
            self.load_time = datetime.now(timezone.utc)


class ConfigChangeEvent:
    """配置变更事件"""
    
    def __init__(self, config_name: str, old_config: BaseConfig, 
                 new_config: BaseConfig, change_type: str = "update"):
        self.config_name = config_name
        self.old_config = old_config
        self.new_config = new_config
        self.change_type = change_type
        self.timestamp = datetime.now(timezone.utc)


class UnifiedConfigManager:
    """
    统一配置管理器
    
    管理整个系统的配置，提供：
    - 统一的配置加载和管理
    - 配置热重载
    - 环境变量覆盖
    - 配置验证
    - 配置变更通知
    """
    
    def __init__(self, 
                 config_dir: Union[str, Path] = None,
                 registry: Optional[ConfigRegistry] = None,
                 enable_hot_reload: bool = True,
                 enable_env_override: bool = True):
        """
        初始化统一配置管理器
        
        Args:
            config_dir: 配置文件目录
            registry: 配置注册表，如果不提供则使用全局注册表
            enable_hot_reload: 是否启用热重载
            enable_env_override: 是否启用环境变量覆盖
        """
        self.config_dir = Path(config_dir) if config_dir else Path.cwd() / "config"
        self.registry = registry or config_registry
        self.enable_hot_reload = enable_hot_reload
        self.enable_env_override = enable_env_override
        
        self.logger = structlog.get_logger(__name__)
        
        # 配置存储
        self._configs: Dict[str, BaseConfig] = {}
        self._config_files: Dict[str, Path] = {}
        self._config_validators: Dict[str, ConfigValidator] = {}
        
        # 事件和回调
        self._change_listeners: List[Callable[[ConfigChangeEvent], None]] = []
        self._load_listeners: List[Callable[[ConfigLoadResult], None]] = []
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 热重载管理器
        self._hot_reload_manager = None
        if enable_hot_reload:
            self._hot_reload_manager = ConfigHotReloadManager(self)
            
        # 环境变量覆盖管理器
        self._env_override_manager = None
        if enable_env_override:
            self._env_override_manager = EnvironmentOverrideManager()
            
        # 状态
        self._initialized = False
        self._start_time = datetime.now(timezone.utc)
        
        # 统计信息
        self._stats = {
            "configs_loaded": 0,
            "configs_reloaded": 0,
            "validation_errors": 0,
            "change_events": 0
        }
        
    def initialize(self, auto_discover: bool = True) -> bool:
        """
        初始化配置管理器
        
        Args:
            auto_discover: 是否自动发现配置文件
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            with self._lock:
                if self._initialized:
                    self.logger.warning("配置管理器已经初始化")
                    return True
                    
                # 确保配置目录存在
                self.config_dir.mkdir(parents=True, exist_ok=True)
                
                # 启动热重载
                if self._hot_reload_manager:
                    self._hot_reload_manager.start()
                    
                # 自动发现配置文件
                if auto_discover:
                    self._auto_discover_configs()
                    
                self._initialized = True
                self.logger.info(
                    "统一配置管理器初始化成功",
                    config_dir=str(self.config_dir),
                    hot_reload=self.enable_hot_reload,
                    env_override=self.enable_env_override
                )
                return True
                
        except Exception as e:
            self.logger.error("配置管理器初始化失败", error=str(e))
            return False
            
    def shutdown(self):
        """关闭配置管理器"""
        try:
            with self._lock:
                if not self._initialized:
                    return
                    
                # 停止热重载
                if self._hot_reload_manager:
                    self._hot_reload_manager.stop()
                    
                self._initialized = False
                self.logger.info("统一配置管理器已关闭")
                
        except Exception as e:
            self.logger.error("配置管理器关闭失败", error=str(e))
            
    def register_config_class(self, 
                            config_class: Type[BaseConfig],
                            name: Optional[str] = None,
                            config_file: Optional[Union[str, Path]] = None,
                            validator: Optional[ConfigValidator] = None) -> str:
        """
        注册配置类
        
        Args:
            config_class: 配置类
            name: 配置名称
            config_file: 配置文件路径
            validator: 配置验证器
            
        Returns:
            str: 配置名称
        """
        config_name = self.registry.register(config_class, name)
        
        # 设置配置文件路径
        if config_file:
            self._config_files[config_name] = Path(config_file)
        else:
            # 默认配置文件路径
            file_name = f"{config_name.lower()}.yaml"
            self._config_files[config_name] = self.config_dir / file_name
            
        # 设置验证器
        if validator:
            self._config_validators[config_name] = validator
            
        self.logger.debug(
            "配置类注册成功",
            config_name=config_name,
            config_class=config_class.__name__,
            config_file=str(self._config_files[config_name])
        )
        
        return config_name
        
    def load_config(self, 
                   config_name: str,
                   config_data: Optional[Dict[str, Any]] = None,
                   from_file: bool = True,
                   validate: bool = True) -> ConfigLoadResult:
        """
        加载配置
        
        Args:
            config_name: 配置名称
            config_data: 配置数据，如果提供则不从文件加载
            from_file: 是否从文件加载
            validate: 是否验证配置
            
        Returns:
            ConfigLoadResult: 加载结果
        """
        start_time = time.time()
        result = ConfigLoadResult(config_name=config_name, success=False)
        
        try:
            with self._lock:
                # 检查配置是否已注册
                config_class = self.registry.get_config_class(config_name)
                if not config_class:
                    result.errors.append(f"配置未注册: {config_name}")
                    return result
                    
                # 获取配置数据
                if config_data is None and from_file:
                    config_file = self._config_files.get(config_name)
                    if config_file and config_file.exists():
                        try:
                            config = config_class.from_file(config_file)
                        except Exception as e:
                            result.errors.append(f"配置文件加载失败: {e}")
                            return result
                    else:
                        # 创建默认配置
                        config = config_class()
                elif config_data:
                    try:
                        config = config_class.from_dict(config_data)
                    except Exception as e:
                        result.errors.append(f"配置数据解析失败: {e}")
                        return result
                else:
                    # 创建默认配置
                    config = config_class()
                    
                # 应用环境变量覆盖
                if self._env_override_manager:
                    env_overrides = self._env_override_manager.get_overrides(config_name)
                    if env_overrides:
                        config.apply_env_overrides(env_overrides)
                        
                # 验证配置
                if validate:
                    validation_results = self._validate_config(config_name, config)
                    errors = [r for r in validation_results if r.severity == ValidationSeverity.ERROR]
                    warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARNING]
                    
                    result.errors.extend([r.message for r in errors])
                    result.warnings.extend([r.message for r in warnings])
                    
                    if errors:
                        self._stats["validation_errors"] += len(errors)
                        return result
                        
                # 存储配置
                old_config = self._configs.get(config_name)
                self._configs[config_name] = config
                
                # 触发变更事件
                if old_config:
                    self._trigger_change_event(config_name, old_config, config)
                    
                result.success = True
                result.config = config
                self._stats["configs_loaded"] += 1
                
                # 触发加载事件
                self._trigger_load_event(result)
                
                load_time = time.time() - start_time
                self.logger.info(
                    "配置加载成功",
                    config_name=config_name,
                    load_time=f"{load_time:.3f}s",
                    warnings=len(result.warnings)
                )
                
                return result
                
        except Exception as e:
            result.errors.append(f"配置加载异常: {e}")
            self.logger.error("配置加载失败", config_name=config_name, error=str(e))
            return result
            
    def get_config(self, config_name: str) -> Optional[BaseConfig]:
        """
        获取配置
        
        Args:
            config_name: 配置名称
            
        Returns:
            Optional[BaseConfig]: 配置实例
        """
        with self._lock:
            return self._configs.get(config_name)
            
    def get_service_config(self, 
                          service_name: str,
                          config_type: Optional[ConfigType] = None,
                          **filters) -> Optional[BaseConfig]:
        """
        获取服务配置
        
        Args:
            service_name: 服务名称
            config_type: 配置类型
            **filters: 其他过滤条件
            
        Returns:
            Optional[BaseConfig]: 配置实例
        """
        # 首先尝试直接匹配服务名称
        config = self.get_config(service_name)
        if config:
            return config
            
        # 按类型查找
        if config_type:
            configs = self.list_configs(config_type=config_type)
            if configs:
                return self.get_config(configs[0])
                
        return None
        
    def reload_config(self, config_name: str) -> ConfigLoadResult:
        """
        重新加载配置
        
        Args:
            config_name: 配置名称
            
        Returns:
            ConfigLoadResult: 加载结果
        """
        self.logger.info("重新加载配置", config_name=config_name)
        result = self.load_config(config_name, from_file=True)
        
        if result.success:
            self._stats["configs_reloaded"] += 1
            
        return result
        
    def reload_all_configs(self) -> Dict[str, ConfigLoadResult]:
        """
        重新加载所有配置
        
        Returns:
            Dict[str, ConfigLoadResult]: 加载结果字典
        """
        results = {}
        
        for config_name in self._configs:
            results[config_name] = self.reload_config(config_name)
            
        return results
        
    def save_config(self, config_name: str) -> bool:
        """
        保存配置到文件
        
        Args:
            config_name: 配置名称
            
        Returns:
            bool: 保存是否成功
        """
        try:
            with self._lock:
                config = self._configs.get(config_name)
                if not config:
                    self.logger.error("配置不存在", config_name=config_name)
                    return False
                    
                config_file = self._config_files.get(config_name)
                if not config_file:
                    self.logger.error("配置文件路径未设置", config_name=config_name)
                    return False
                    
                config.save_to_file(config_file)
                self.logger.info("配置保存成功", config_name=config_name, file=str(config_file))
                return True
                
        except Exception as e:
            self.logger.error("配置保存失败", config_name=config_name, error=str(e))
            return False
            
    def list_configs(self, 
                    config_type: Optional[ConfigType] = None,
                    tags: Optional[Set[str]] = None,
                    loaded_only: bool = False) -> List[str]:
        """
        列出配置
        
        Args:
            config_type: 配置类型过滤
            tags: 标签过滤
            loaded_only: 是否只返回已加载的配置
            
        Returns:
            List[str]: 配置名称列表
        """
        with self._lock:
            if loaded_only:
                configs = set(self._configs.keys())
            else:
                configs = set(self.registry.list_configs(config_type=config_type, tags=tags))
                
            if config_type or tags:
                registry_configs = set(self.registry.list_configs(config_type=config_type, tags=tags))
                configs &= registry_configs
                
            return sorted(configs)
            
    def add_change_listener(self, listener: Callable[[ConfigChangeEvent], None]):
        """
        添加配置变更监听器
        
        Args:
            listener: 监听器函数
        """
        self._change_listeners.append(listener)
        
    def remove_change_listener(self, listener: Callable[[ConfigChangeEvent], None]):
        """
        移除配置变更监听器
        
        Args:
            listener: 监听器函数
        """
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)
            
    def add_load_listener(self, listener: Callable[[ConfigLoadResult], None]):
        """
        添加配置加载监听器
        
        Args:
            listener: 监听器函数
        """
        self._load_listeners.append(listener)
        
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            
            return {
                "uptime_seconds": uptime,
                "initialized": self._initialized,
                "config_dir": str(self.config_dir),
                "hot_reload_enabled": self.enable_hot_reload,
                "env_override_enabled": self.enable_env_override,
                "registered_configs": len(self.registry.list_configs()),
                "loaded_configs": len(self._configs),
                "config_files": len(self._config_files),
                "change_listeners": len(self._change_listeners),
                "load_listeners": len(self._load_listeners),
                **self._stats
            }
            
    def _auto_discover_configs(self):
        """自动发现配置文件"""
        if not self.config_dir.exists():
            return
            
        # 查找配置文件
        config_files = []
        for pattern in ['*.yaml', '*.yml', '*.json']:
            config_files.extend(self.config_dir.glob(pattern))
            
        for config_file in config_files:
            # 尝试从文件名猜测配置名称
            config_name = config_file.stem
            
            # 检查是否已注册对应的配置类
            if config_name in self.registry.list_configs():
                self._config_files[config_name] = config_file
                self.logger.debug("发现配置文件", config_name=config_name, file=str(config_file))
                
    def _validate_config(self, config_name: str, config: BaseConfig) -> List[ValidationResult]:
        """验证配置"""
        results = []
        
        # 配置自身验证
        try:
            if not config.validate():
                for error in config.validation_errors:
                    results.append(ValidationResult(
                        field_name="",
                        severity=ValidationSeverity.ERROR,
                        message=error,
                        value=None
                    ))
        except Exception as e:
            results.append(ValidationResult(
                field_name="",
                severity=ValidationSeverity.ERROR,
                message=f"配置验证异常: {e}",
                value=None
            ))
            
        # 使用注册的验证器
        validator = self._config_validators.get(config_name)
        if validator:
            try:
                config_dict = config.to_dict()
                validator_results = validator.validate_config(config_dict)
                results.extend(validator_results)
            except Exception as e:
                results.append(ValidationResult(
                    field_name="",
                    severity=ValidationSeverity.ERROR,
                    message=f"验证器执行异常: {e}",
                    value=None
                ))
                
        return results
        
    def _trigger_change_event(self, config_name: str, old_config: BaseConfig, new_config: BaseConfig):
        """触发配置变更事件"""
        event = ConfigChangeEvent(config_name, old_config, new_config)
        
        for listener in self._change_listeners:
            try:
                listener(event)
            except Exception as e:
                self.logger.error("配置变更监听器执行失败", listener=listener, error=str(e))
                
        self._stats["change_events"] += 1
        
    def _trigger_load_event(self, result: ConfigLoadResult):
        """触发配置加载事件"""
        for listener in self._load_listeners:
            try:
                listener(result)
            except Exception as e:
                self.logger.error("配置加载监听器执行失败", listener=listener, error=str(e))