"""服务元数据管理器 (Metadata Manager)

实现服务元数据管理功能，提供：
- 结构化元数据存储
- 元数据验证和约束
- 高级查询和过滤
- 元数据版本控制
- 变更跟踪和通知
"""

import json
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Union, Callable
from datetime import datetime
import logging
import re

from .service_registry import ServiceInstance


class MetadataType(Enum):
    """元数据类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    JSON = "json"


class MetadataScope(Enum):
    """元数据作用域"""
    SERVICE = "service"       # 服务级别
    INSTANCE = "instance"     # 实例级别
    GLOBAL = "global"         # 全局级别


@dataclass
class MetadataSchema:
    """元数据模式定义"""
    key: str                                    # 键名
    data_type: MetadataType                     # 数据类型
    scope: MetadataScope                        # 作用域
    required: bool = False                      # 是否必需
    default_value: Any = None                   # 默认值
    validation_pattern: Optional[str] = None    # 验证模式（正则）
    min_value: Optional[Union[int, float]] = None  # 最小值
    max_value: Optional[Union[int, float]] = None  # 最大值
    allowed_values: Optional[Set[Any]] = field(default=None)   # 允许的值
    description: str = ""                       # 描述


@dataclass
class ServiceMetadata:
    """服务元数据"""
    service_name: str                           # 服务名称
    instance_id: Optional[str] = None          # 实例ID（实例级别元数据）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    tags: Set[str] = field(default_factory=set)  # 标签
    version: int = 1                           # 版本号
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    updated_at: datetime = field(default_factory=datetime.now)  # 更新时间


@dataclass
class MetadataChangeEvent:
    """元数据变更事件"""
    service_name: str                          # 服务名称
    key: str                                  # 变更的键
    instance_id: Optional[str] = None         # 实例ID
    old_value: Any = None                     # 旧值
    new_value: Any = None                     # 新值
    change_type: str = "UPDATE"               # 变更类型 (CREATE, UPDATE, DELETE)
    timestamp: datetime = field(default_factory=datetime.now)  # 时间戳
    user: Optional[str] = None                # 操作用户


class MetadataManager:
    """元数据管理器
    
    提供企业级元数据管理功能：
    - 结构化元数据存储
    - 元数据验证和约束
    - 高级查询和过滤
    - 元数据版本控制
    - 变更跟踪和通知
    """
    
    def __init__(self):
        """初始化元数据管理器"""
        # 元数据存储
        self._service_metadata: Dict[str, ServiceMetadata] = {}  # service_name -> metadata
        self._instance_metadata: Dict[str, ServiceMetadata] = {}  # instance_id -> metadata
        self._global_metadata: ServiceMetadata = ServiceMetadata(service_name="__global__")
        
        # 模式定义
        self._schemas: Dict[str, MetadataSchema] = {}
        
        # 变更历史
        self._change_history: List[MetadataChangeEvent] = []
        self._max_history_size = 1000
        
        # 索引
        self._tag_index: Dict[str, Set[str]] = {}  # tag -> set of service_names/instance_ids
        self._key_index: Dict[str, Set[str]] = {}  # key -> set of service_names/instance_ids
        
        # 回调
        self._change_callbacks: List[Callable[[MetadataChangeEvent], None]] = []
        
        # 统计
        self._stats = {
            'total_services': 0,
            'total_instances': 0,
            'total_schemas': 0,
            'total_changes': 0,
            'validation_errors': 0
        }
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register_schema(self, schema: MetadataSchema) -> bool:
        """注册元数据模式
        
        Args:
            schema: 元数据模式
            
        Returns:
            bool: 注册是否成功
        """
        try:
            with self._lock:
                self._schemas[schema.key] = schema
                self._stats['total_schemas'] += 1
                
                self.logger.info(f"Registered metadata schema: {schema.key}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to register schema {schema.key}: {e}")
            return False
    
    def set_service_metadata(self, service_name: str, key: str, value: Any, 
                           user: Optional[str] = None) -> bool:
        """设置服务元数据
        
        Args:
            service_name: 服务名称
            key: 元数据键
            value: 元数据值
            user: 操作用户
            
        Returns:
            bool: 设置是否成功
        """
        try:
            # 验证元数据
            if not self._validate_metadata(key, value, MetadataScope.SERVICE):
                return False
            
            with self._lock:
                # 获取或创建服务元数据
                if service_name not in self._service_metadata:
                    self._service_metadata[service_name] = ServiceMetadata(service_name=service_name)
                    self._stats['total_services'] += 1
                
                metadata = self._service_metadata[service_name]
                old_value = metadata.metadata.get(key)
                
                # 设置新值
                metadata.metadata[key] = value
                metadata.updated_at = datetime.now()
                metadata.version += 1
                
                # 更新索引
                self._update_key_index(key, service_name)
                
                # 记录变更
                change_type = "CREATE" if old_value is None else "UPDATE"
                self._record_change(service_name, None, key, old_value, value, change_type, user)
                
                self.logger.debug(f"Set service metadata: {service_name}.{key} = {value}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to set service metadata {service_name}.{key}: {e}")
            return False
    
    def set_instance_metadata(self, instance_id: str, service_name: str, 
                            key: str, value: Any, user: Optional[str] = None) -> bool:
        """设置实例元数据
        
        Args:
            instance_id: 实例ID
            service_name: 服务名称
            key: 元数据键
            value: 元数据值
            user: 操作用户
            
        Returns:
            bool: 设置是否成功
        """
        try:
            # 验证元数据
            if not self._validate_metadata(key, value, MetadataScope.INSTANCE):
                return False
            
            with self._lock:
                # 获取或创建实例元数据
                if instance_id not in self._instance_metadata:
                    self._instance_metadata[instance_id] = ServiceMetadata(
                        service_name=service_name, 
                        instance_id=instance_id
                    )
                    self._stats['total_instances'] += 1
                
                metadata = self._instance_metadata[instance_id]
                old_value = metadata.metadata.get(key)
                
                # 设置新值
                metadata.metadata[key] = value
                metadata.updated_at = datetime.now()
                metadata.version += 1
                
                # 更新索引
                self._update_key_index(key, instance_id)
                
                # 记录变更
                change_type = "CREATE" if old_value is None else "UPDATE"
                self._record_change(service_name, instance_id, key, old_value, value, change_type, user)
                
                self.logger.debug(f"Set instance metadata: {instance_id}.{key} = {value}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to set instance metadata {instance_id}.{key}: {e}")
            return False
    
    def set_global_metadata(self, key: str, value: Any, user: Optional[str] = None) -> bool:
        """设置全局元数据
        
        Args:
            key: 元数据键
            value: 元数据值
            user: 操作用户
            
        Returns:
            bool: 设置是否成功
        """
        try:
            # 验证元数据
            if not self._validate_metadata(key, value, MetadataScope.GLOBAL):
                return False
            
            with self._lock:
                old_value = self._global_metadata.metadata.get(key)
                
                # 设置新值
                self._global_metadata.metadata[key] = value
                self._global_metadata.updated_at = datetime.now()
                self._global_metadata.version += 1
                
                # 更新索引
                self._update_key_index(key, "__global__")
                
                # 记录变更
                change_type = "CREATE" if old_value is None else "UPDATE"
                self._record_change("__global__", None, key, old_value, value, change_type, user)
                
                self.logger.debug(f"Set global metadata: {key} = {value}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to set global metadata {key}: {e}")
            return False
    
    def get_service_metadata(self, service_name: str, key: Optional[str] = None) -> Any:
        """获取服务元数据
        
        Args:
            service_name: 服务名称
            key: 元数据键（可选）
            
        Returns:
            Any: 元数据值或元数据字典
        """
        with self._lock:
            if service_name not in self._service_metadata:
                return None if key else {}
            
            metadata = self._service_metadata[service_name]
            
            if key:
                return metadata.metadata.get(key)
            else:
                return metadata.metadata.copy()
    
    def get_instance_metadata(self, instance_id: str, key: Optional[str] = None) -> Any:
        """获取实例元数据
        
        Args:
            instance_id: 实例ID
            key: 元数据键（可选）
            
        Returns:
            Any: 元数据值或元数据字典
        """
        with self._lock:
            if instance_id not in self._instance_metadata:
                return None if key else {}
            
            metadata = self._instance_metadata[instance_id]
            
            if key:
                return metadata.metadata.get(key)
            else:
                return metadata.metadata.copy()
    
    def get_global_metadata(self, key: Optional[str] = None) -> Any:
        """获取全局元数据
        
        Args:
            key: 元数据键（可选）
            
        Returns:
            Any: 元数据值或元数据字典
        """
        with self._lock:
            if key:
                return self._global_metadata.metadata.get(key)
            else:
                return self._global_metadata.metadata.copy()
    
    def query_services_by_metadata(self, filters: Dict[str, Any]) -> List[str]:
        """根据元数据查询服务
        
        Args:
            filters: 过滤条件
            
        Returns:
            List[str]: 服务名称列表
        """
        with self._lock:
            result = []
            
            for service_name, metadata in self._service_metadata.items():
                if self._match_filters(metadata.metadata, filters):
                    result.append(service_name)
            
            return result
    
    def query_instances_by_metadata(self, filters: Dict[str, Any]) -> List[str]:
        """根据元数据查询实例
        
        Args:
            filters: 过滤条件
            
        Returns:
            List[str]: 实例ID列表
        """
        with self._lock:
            result = []
            
            for instance_id, metadata in self._instance_metadata.items():
                if self._match_filters(metadata.metadata, filters):
                    result.append(instance_id)
            
            return result
    
    def add_service_tag(self, service_name: str, tag: str) -> bool:
        """为服务添加标签
        
        Args:
            service_name: 服务名称
            tag: 标签
            
        Returns:
            bool: 添加是否成功
        """
        try:
            with self._lock:
                if service_name not in self._service_metadata:
                    self._service_metadata[service_name] = ServiceMetadata(service_name=service_name)
                    self._stats['total_services'] += 1
                
                metadata = self._service_metadata[service_name]
                metadata.tags.add(tag)
                metadata.updated_at = datetime.now()
                
                # 更新标签索引
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(service_name)
                
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to add service tag {service_name}.{tag}: {e}")
            return False
    
    def add_instance_tag(self, instance_id: str, service_name: str, tag: str) -> bool:
        """为实例添加标签
        
        Args:
            instance_id: 实例ID
            service_name: 服务名称
            tag: 标签
            
        Returns:
            bool: 添加是否成功
        """
        try:
            with self._lock:
                if instance_id not in self._instance_metadata:
                    self._instance_metadata[instance_id] = ServiceMetadata(
                        service_name=service_name,
                        instance_id=instance_id
                    )
                    self._stats['total_instances'] += 1
                
                metadata = self._instance_metadata[instance_id]
                metadata.tags.add(tag)
                metadata.updated_at = datetime.now()
                
                # 更新标签索引
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(instance_id)
                
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to add instance tag {instance_id}.{tag}: {e}")
            return False
    
    def query_by_tags(self, tags: Set[str], match_all: bool = True) -> Dict[str, List[str]]:
        """根据标签查询
        
        Args:
            tags: 标签集合
            match_all: 是否匹配所有标签
            
        Returns:
            Dict[str, List[str]]: 查询结果 {"services": [...], "instances": [...]}
        """
        with self._lock:
            services = set()
            instances = set()
            
            if match_all:
                # 交集
                for tag in tags:
                    if tag in self._tag_index:
                        if not services and not instances:
                            # 第一个标签
                            tagged_items = self._tag_index[tag]
                            for item in tagged_items:
                                if item in self._service_metadata:
                                    services.add(item)
                                elif item in self._instance_metadata:
                                    instances.add(item)
                        else:
                            # 求交集
                            tagged_items = self._tag_index[tag]
                            services &= {item for item in tagged_items if item in self._service_metadata}
                            instances &= {item for item in tagged_items if item in self._instance_metadata}
            else:
                # 并集
                for tag in tags:
                    if tag in self._tag_index:
                        tagged_items = self._tag_index[tag]
                        for item in tagged_items:
                            if item in self._service_metadata:
                                services.add(item)
                            elif item in self._instance_metadata:
                                instances.add(item)
            
            return {
                "services": list(services),
                "instances": list(instances)
            }
    
    def _validate_metadata(self, key: str, value: Any, scope: MetadataScope) -> bool:
        """验证元数据"""
        if key not in self._schemas:
            return True  # 没有模式定义，允许
        
        schema = self._schemas[key]
        
        # 检查作用域
        if schema.scope != scope:
            self.logger.warning(f"Metadata key {key} scope mismatch: expected {schema.scope}, got {scope}")
            self._stats['validation_errors'] += 1
            return False
        
        # 检查类型
        if not self._validate_type(value, schema.data_type):
            self.logger.warning(f"Metadata key {key} type validation failed")
            self._stats['validation_errors'] += 1
            return False
        
        # 检查值范围
        if schema.min_value is not None and isinstance(value, (int, float)):
            if value < schema.min_value:
                self.logger.warning(f"Metadata key {key} value {value} < min {schema.min_value}")
                self._stats['validation_errors'] += 1
                return False
        
        if schema.max_value is not None and isinstance(value, (int, float)):
            if value > schema.max_value:
                self.logger.warning(f"Metadata key {key} value {value} > max {schema.max_value}")
                self._stats['validation_errors'] += 1
                return False
        
        # 检查允许的值
        if schema.allowed_values is not None:
            if value not in schema.allowed_values:
                self.logger.warning(f"Metadata key {key} value {value} not in allowed values")
                self._stats['validation_errors'] += 1
                return False
        
        # 检查正则模式
        if schema.validation_pattern and isinstance(value, str):
            if not re.match(schema.validation_pattern, value):
                self.logger.warning(f"Metadata key {key} value {value} doesn't match pattern")
                self._stats['validation_errors'] += 1
                return False
        
        return True
    
    def _validate_type(self, value: Any, expected_type: MetadataType) -> bool:
        """验证数据类型"""
        if expected_type == MetadataType.STRING:
            return isinstance(value, str)
        elif expected_type == MetadataType.INTEGER:
            return isinstance(value, int)
        elif expected_type == MetadataType.FLOAT:
            return isinstance(value, (int, float))
        elif expected_type == MetadataType.BOOLEAN:
            return isinstance(value, bool)
        elif expected_type == MetadataType.LIST:
            return isinstance(value, list)
        elif expected_type == MetadataType.DICT:
            return isinstance(value, dict)
        elif expected_type == MetadataType.JSON:
            try:
                json.dumps(value)
                return True
            except (TypeError, ValueError):
                return False
        else:
            return True
    
    def _match_filters(self, metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """匹配过滤条件"""
        for key, expected_value in filters.items():
            if key not in metadata:
                return False
            
            actual_value = metadata[key]
            
            # 支持简单匹配和模式匹配
            if isinstance(expected_value, str) and expected_value.startswith("*"):
                # 模糊匹配
                pattern = expected_value[1:]
                if pattern not in str(actual_value):
                    return False
            elif actual_value != expected_value:
                return False
        
        return True
    
    def _update_key_index(self, key: str, identifier: str):
        """更新键索引"""
        if key not in self._key_index:
            self._key_index[key] = set()
        self._key_index[key].add(identifier)
    
    def _record_change(self, service_name: str, instance_id: Optional[str], 
                      key: str, old_value: Any, new_value: Any, 
                      change_type: str, user: Optional[str]):
        """记录变更"""
        event = MetadataChangeEvent(
            service_name=service_name,
            key=key,
            instance_id=instance_id,
            old_value=old_value,
            new_value=new_value,
            change_type=change_type,
            user=user
        )
        
        self._change_history.append(event)
        
        # 限制历史记录大小
        if len(self._change_history) > self._max_history_size:
            self._change_history = self._change_history[-self._max_history_size:]
        
        self._stats['total_changes'] += 1
        
        # 触发变更回调
        for callback in self._change_callbacks:
            try:
                callback(event)
            except Exception as e:
                self.logger.error(f"Error in metadata change callback: {e}")
    
    def add_change_callback(self, callback: Callable[[MetadataChangeEvent], None]):
        """添加变更回调"""
        self._change_callbacks.append(callback)
    
    def get_change_history(self, limit: Optional[int] = None) -> List[MetadataChangeEvent]:
        """获取变更历史"""
        with self._lock:
            if limit:
                return self._change_history[-limit:]
            return self._change_history.copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()