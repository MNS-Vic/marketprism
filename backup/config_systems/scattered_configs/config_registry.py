"""
配置注册表

管理所有配置类的注册、发现和实例化
"""

from typing import Dict, Type, Optional, List, Set, Any
from collections import defaultdict
import threading
from dataclasses import dataclass
from enum import Enum

from .base_config import BaseConfig, ConfigType, ConfigMetadata


class RegistrationStatus(Enum):
    """注册状态"""
    REGISTERED = "registered"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


@dataclass
class ConfigRegistration:
    """配置注册信息"""
    config_class: Type[BaseConfig]
    metadata: ConfigMetadata
    status: RegistrationStatus = RegistrationStatus.REGISTERED
    instance: Optional[BaseConfig] = None
    registration_order: int = 0


class ConfigRegistry:
    """
    配置注册表
    
    负责管理所有配置类的注册、实例化和生命周期管理
    """
    
    def __init__(self):
        self._registry: Dict[str, ConfigRegistration] = {}
        self._type_index: Dict[ConfigType, Set[str]] = defaultdict(set)
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self._instances: Dict[str, BaseConfig] = {}
        self._lock = threading.RLock()
        self._registration_counter = 0
        
    def register(self, 
                 config_class: Type[BaseConfig], 
                 name: Optional[str] = None,
                 override: bool = False) -> str:
        """
        注册配置类
        
        Args:
            config_class: 配置类
            name: 配置名称，如果不提供则使用类名
            override: 是否覆盖已存在的注册
            
        Returns:
            str: 配置名称
            
        Raises:
            ValueError: 如果配置已存在且不允许覆盖
            TypeError: 如果配置类不是BaseConfig的子类
        """
        if not issubclass(config_class, BaseConfig):
            raise TypeError(f"配置类必须继承BaseConfig: {config_class}")
            
        # 获取配置元数据
        try:
            temp_instance = config_class()
            metadata = temp_instance.metadata
        except Exception as e:
            raise ValueError(f"无法创建配置类实例获取元数据: {config_class}, 错误: {e}")
            
        config_name = name or metadata.name or config_class.__name__
        
        with self._lock:
            # 检查是否已存在
            if config_name in self._registry and not override:
                raise ValueError(f"配置已存在: {config_name}")
                
            # 创建注册信息
            registration = ConfigRegistration(
                config_class=config_class,
                metadata=metadata,
                status=RegistrationStatus.REGISTERED,
                registration_order=self._registration_counter
            )
            
            # 注册
            self._registry[config_name] = registration
            self._registration_counter += 1
            
            # 更新索引
            self._update_indexes(config_name, metadata)
            
            # 更新依赖图
            self._update_dependency_graph(config_name, metadata.dependencies)
            
        return config_name
        
    def unregister(self, name: str):
        """
        注销配置
        
        Args:
            name: 配置名称
        """
        with self._lock:
            if name not in self._registry:
                return
                
            registration = self._registry[name]
            
            # 检查是否有其他配置依赖此配置
            dependents = self._get_dependents(name)
            if dependents:
                raise ValueError(f"不能注销配置 {name}，以下配置依赖它: {dependents}")
                
            # 清理实例
            if name in self._instances:
                del self._instances[name]
                
            # 清理索引
            self._remove_from_indexes(name, registration.metadata)
            
            # 清理依赖图
            del self._dependency_graph[name]
            for deps in self._dependency_graph.values():
                deps.discard(name)
                
            # 移除注册
            del self._registry[name]
            
    def get_config_class(self, name: str) -> Optional[Type[BaseConfig]]:
        """
        获取配置类
        
        Args:
            name: 配置名称
            
        Returns:
            Optional[Type[BaseConfig]]: 配置类，如果不存在返回None
        """
        with self._lock:
            registration = self._registry.get(name)
            return registration.config_class if registration else None
            
    def get_config_instance(self, name: str, 
                          create_if_not_exists: bool = True,
                          **kwargs) -> Optional[BaseConfig]:
        """
        获取配置实例
        
        Args:
            name: 配置名称
            create_if_not_exists: 如果实例不存在是否创建
            **kwargs: 创建实例时的参数
            
        Returns:
            Optional[BaseConfig]: 配置实例
        """
        with self._lock:
            # 检查是否已有实例
            if name in self._instances:
                return self._instances[name]
                
            # 检查是否已注册
            if name not in self._registry:
                return None
                
            if not create_if_not_exists:
                return None
                
            # 创建实例
            registration = self._registry[name]
            try:
                instance = registration.config_class(**kwargs)
                self._instances[name] = instance
                registration.instance = instance
                return instance
            except Exception as e:
                raise ValueError(f"创建配置实例失败: {name}, 错误: {e}")
                
    def list_configs(self, 
                    config_type: Optional[ConfigType] = None,
                    tags: Optional[Set[str]] = None,
                    status: Optional[RegistrationStatus] = None) -> List[str]:
        """
        列出配置
        
        Args:
            config_type: 配置类型过滤
            tags: 标签过滤
            status: 状态过滤
            
        Returns:
            List[str]: 配置名称列表
        """
        with self._lock:
            results = set(self._registry.keys())
            
            # 按类型过滤
            if config_type is not None:
                results &= self._type_index[config_type]
                
            # 按标签过滤
            if tags:
                for tag in tags:
                    results &= self._tag_index[tag]
                    
            # 按状态过滤
            if status is not None:
                results = {
                    name for name in results 
                    if self._registry[name].status == status
                }
                
            # 按注册顺序排序
            return sorted(results, key=lambda x: self._registry[x].registration_order)
            
    def get_config_metadata(self, name: str) -> Optional[ConfigMetadata]:
        """
        获取配置元数据
        
        Args:
            name: 配置名称
            
        Returns:
            Optional[ConfigMetadata]: 配置元数据
        """
        with self._lock:
            registration = self._registry.get(name)
            return registration.metadata if registration else None
            
    def get_dependencies(self, name: str) -> Set[str]:
        """
        获取配置依赖
        
        Args:
            name: 配置名称
            
        Returns:
            Set[str]: 依赖的配置名称集合
        """
        with self._lock:
            return self._dependency_graph[name].copy()
            
    def get_dependents(self, name: str) -> Set[str]:
        """
        获取依赖此配置的其他配置
        
        Args:
            name: 配置名称
            
        Returns:
            Set[str]: 依赖此配置的配置名称集合
        """
        with self._lock:
            return self._get_dependents(name)
            
    def resolve_dependencies(self, name: str) -> List[str]:
        """
        解析配置依赖顺序
        
        Args:
            name: 配置名称
            
        Returns:
            List[str]: 按依赖顺序排列的配置名称列表
            
        Raises:
            ValueError: 如果存在循环依赖
        """
        with self._lock:
            return self._topological_sort([name])
            
    def resolve_all_dependencies(self) -> List[str]:
        """
        解析所有配置的依赖顺序
        
        Returns:
            List[str]: 按依赖顺序排列的所有配置名称列表
            
        Raises:
            ValueError: 如果存在循环依赖
        """
        with self._lock:
            return self._topological_sort(list(self._registry.keys()))
            
    def validate_dependencies(self) -> Dict[str, List[str]]:
        """
        验证依赖关系
        
        Returns:
            Dict[str, List[str]]: 验证错误，key为配置名称，value为错误列表
        """
        errors = {}
        
        with self._lock:
            for name, registration in self._registry.items():
                config_errors = []
                
                # 检查依赖是否存在
                for dep in registration.metadata.dependencies:
                    if dep not in self._registry:
                        config_errors.append(f"依赖的配置不存在: {dep}")
                        
                # 检查循环依赖
                try:
                    self.resolve_dependencies(name)
                except ValueError as e:
                    config_errors.append(f"循环依赖: {e}")
                    
                if config_errors:
                    errors[name] = config_errors
                    
        return errors
        
    def get_registry_stats(self) -> Dict[str, Any]:
        """
        获取注册表统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            stats = {
                "total_configs": len(self._registry),
                "active_instances": len(self._instances),
                "config_types": {
                    config_type.value: len(configs) 
                    for config_type, configs in self._type_index.items()
                },
                "status_distribution": {},
                "dependency_stats": {
                    "total_dependencies": sum(len(deps) for deps in self._dependency_graph.values()),
                    "configs_with_dependencies": sum(1 for deps in self._dependency_graph.values() if deps),
                    "max_dependencies": max(len(deps) for deps in self._dependency_graph.values()) if self._dependency_graph else 0
                }
            }
            
            # 状态分布
            status_count = defaultdict(int)
            for registration in self._registry.values():
                status_count[registration.status.value] += 1
            stats["status_distribution"] = dict(status_count)
            
            return stats
            
    def _update_indexes(self, name: str, metadata: ConfigMetadata):
        """更新索引"""
        self._type_index[metadata.config_type].add(name)
        for tag in metadata.tags:
            self._tag_index[tag].add(name)
            
    def _remove_from_indexes(self, name: str, metadata: ConfigMetadata):
        """从索引中移除"""
        self._type_index[metadata.config_type].discard(name)
        for tag in metadata.tags:
            self._tag_index[tag].discard(name)
            
    def _update_dependency_graph(self, name: str, dependencies: List[str]):
        """更新依赖图"""
        self._dependency_graph[name] = set(dependencies)
        
    def _get_dependents(self, name: str) -> Set[str]:
        """获取依赖者"""
        dependents = set()
        for config_name, deps in self._dependency_graph.items():
            if name in deps:
                dependents.add(config_name)
        return dependents
        
    def _topological_sort(self, names: List[str]) -> List[str]:
        """拓扑排序"""
        # 构建子图
        subgraph = {}
        in_degree = {}
        
        def add_node(node):
            if node not in subgraph:
                subgraph[node] = set()
                in_degree[node] = 0
                
        # 添加所有相关节点
        to_visit = set(names)
        visited = set()
        
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
                
            visited.add(current)
            add_node(current)
            
            # 添加依赖
            deps = self._dependency_graph.get(current, set())
            for dep in deps:
                add_node(dep)
                subgraph[dep].add(current)
                in_degree[current] += 1
                to_visit.add(dep)
                
        # 拓扑排序
        result = []
        queue = [node for node, degree in in_degree.items() if degree == 0]
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            for neighbor in subgraph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    
        # 检查循环依赖
        if len(result) != len(subgraph):
            remaining = set(subgraph.keys()) - set(result)
            raise ValueError(f"检测到循环依赖: {remaining}")
            
        # 只返回请求的配置
        return [name for name in result if name in names]


# 全局配置注册表实例
config_registry = ConfigRegistry()