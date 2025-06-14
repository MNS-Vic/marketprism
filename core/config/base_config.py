"""
配置基类和接口定义

定义了所有配置类必须继承的基类和接口规范
"""

from datetime import datetime, timezone
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, Set, Union, Type
from dataclasses import dataclass, field
from pathlib import Path
import json
import yaml


class ConfigType(Enum):
    """配置类型枚举"""
    EXCHANGE = "exchange"
    NATS = "nats"
    COLLECTOR = "collector"
    PROXY = "proxy"
    RELIABILITY = "reliability"
    STORAGE = "storage"
    MONITORING = "monitoring"
    REST_CLIENT = "rest_client"
    RATE_LIMIT = "rate_limit"
    COLD_STORAGE = "cold_storage"


@dataclass
class ConfigMetadata:
    """配置元数据"""
    name: str
    config_type: ConfigType
    version: str = "1.0.0"
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    schema_version: str = "1.0"


class BaseConfig(ABC):
    """
    配置基类
    
    所有配置类必须继承此基类，提供：
    - 配置验证
    - 序列化/反序列化
    - 环境变量覆盖
    - 配置合并
    - 热重载支持
    """
    
    def __init__(self, metadata: Optional[ConfigMetadata] = None):
        self._metadata = metadata or self._get_default_metadata()
        self._source_file: Optional[Path] = None
        self._env_overrides: Dict[str, Any] = {}
        self._validation_errors: List[str] = []
        
    @property
    def metadata(self) -> ConfigMetadata:
        """获取配置元数据"""
        return self._metadata
        
    @property
    def source_file(self) -> Optional[Path]:
        """获取配置源文件路径"""
        return self._source_file
        
    @property
    def env_overrides(self) -> Dict[str, Any]:
        """获取环境变量覆盖"""
        return self._env_overrides.copy()
        
    @property
    def validation_errors(self) -> List[str]:
        """获取验证错误列表"""
        return self._validation_errors.copy()
        
    @abstractmethod
    def _get_default_metadata(self) -> ConfigMetadata:
        """获取默认元数据"""
        pass
        
    @abstractmethod
    def validate(self) -> bool:
        """
        验证配置
        
        Returns:
            bool: 验证是否通过
        """
        pass
        
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典
        
        Returns:
            Dict[str, Any]: 配置字典
        """
        pass
        
    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseConfig':
        """
        从字典创建配置实例
        
        Args:
            data: 配置数据字典
            
        Returns:
            BaseConfig: 配置实例
        """
        pass
        
    def to_json(self, indent: int = 2) -> str:
        """
        转换为JSON字符串
        
        Args:
            indent: JSON缩进
            
        Returns:
            str: JSON字符串
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
        
    def to_yaml(self) -> str:
        """
        转换为YAML字符串
        
        Returns:
            str: YAML字符串
        """
        return yaml.dump(self.to_dict(), default_flow_style=False, allow_unicode=True)
        
    @classmethod
    def from_json(cls, json_str: str) -> 'BaseConfig':
        """
        从JSON字符串创建配置实例
        
        Args:
            json_str: JSON字符串
            
        Returns:
            BaseConfig: 配置实例
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
        
    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'BaseConfig':
        """
        从YAML字符串创建配置实例
        
        Args:
            yaml_str: YAML字符串
            
        Returns:
            BaseConfig: 配置实例
        """
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)
        
    @classmethod
    def from_file(cls, file_path: Union[str, Path]) -> 'BaseConfig':
        """
        从文件加载配置
        
        Args:
            file_path: 配置文件路径
            
        Returns:
            BaseConfig: 配置实例
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {file_path}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if file_path.suffix.lower() in ['.json']:
            config = cls.from_json(content)
        elif file_path.suffix.lower() in ['.yaml', '.yml']:
            config = cls.from_yaml(content)
        else:
            raise ValueError(f"不支持的配置文件格式: {file_path.suffix}")
            
        config._source_file = file_path
        return config
        
    def save_to_file(self, file_path: Union[str, Path]):
        """
        保存配置到文件
        
        Args:
            file_path: 目标文件路径
        """
        file_path = Path(file_path)
        
        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if file_path.suffix.lower() in ['.json']:
            content = self.to_json()
        elif file_path.suffix.lower() in ['.yaml', '.yml']:
            content = self.to_yaml()
        else:
            raise ValueError(f"不支持的配置文件格式: {file_path.suffix}")
            
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    def apply_env_overrides(self, env_overrides: Dict[str, Any]):
        """
        应用环境变量覆盖
        
        Args:
            env_overrides: 环境变量覆盖字典
        """
        self._env_overrides.update(env_overrides)
        self._apply_overrides()
        
    def merge_config(self, other: 'BaseConfig'):
        """
        合并另一个配置
        
        Args:
            other: 要合并的配置
        """
        if not isinstance(other, type(self)):
            raise TypeError(f"不能合并不同类型的配置: {type(self)} vs {type(other)}")
            
        other_dict = other.to_dict()
        self._merge_dict(self.to_dict(), other_dict)
        self._update_from_dict(other_dict)
        
    def clone(self) -> 'BaseConfig':
        """
        克隆配置
        
        Returns:
            BaseConfig: 配置副本
        """
        return type(self).from_dict(self.to_dict())
        
    def get_diff(self, other: 'BaseConfig') -> Dict[str, Any]:
        """
        获取与另一个配置的差异
        
        Args:
            other: 比较的配置
            
        Returns:
            Dict[str, Any]: 差异字典
        """
        if not isinstance(other, type(self)):
            raise TypeError(f"不能比较不同类型的配置: {type(self)} vs {type(other)}")
            
        return self._dict_diff(self.to_dict(), other.to_dict())
        
    def _apply_overrides(self):
        """应用环境变量覆盖到配置"""
        pass  # 子类实现具体逻辑
        
    def _update_from_dict(self, data: Dict[str, Any]):
        """从字典更新配置"""
        pass  # 子类实现具体逻辑
        
    def _merge_dict(self, target: Dict[str, Any], source: Dict[str, Any]):
        """合并字典"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_dict(target[key], value)
            else:
                target[key] = value
                
    def _dict_diff(self, dict1: Dict[str, Any], dict2: Dict[str, Any], 
                   path: str = "") -> Dict[str, Any]:
        """计算字典差异"""
        diff = {}
        
        # 检查dict1中的键
        for key, value in dict1.items():
            key_path = f"{path}.{key}" if path else key
            
            if key not in dict2:
                diff[key_path] = {"type": "removed", "old_value": value}
            elif isinstance(value, dict) and isinstance(dict2[key], dict):
                sub_diff = self._dict_diff(value, dict2[key], key_path)
                diff.update(sub_diff)
            elif value != dict2[key]:
                diff[key_path] = {
                    "type": "changed", 
                    "old_value": value, 
                    "new_value": dict2[key]
                }
                
        # 检查dict2中新增的键
        for key, value in dict2.items():
            key_path = f"{path}.{key}" if path else key
            if key not in dict1:
                diff[key_path] = {"type": "added", "new_value": value}
                
        return diff
        
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.metadata.name})"
        
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.metadata.name}', type='{self.metadata.config_type.value}')"