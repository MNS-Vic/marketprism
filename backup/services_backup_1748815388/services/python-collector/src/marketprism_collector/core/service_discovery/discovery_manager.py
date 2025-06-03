"""服务发现管理器 (Discovery Manager)

实现统一的服务发现管理，提供：
- 组件集成和协调
- 统一配置管理
- 生命周期管理
- 事件回调系统
- 统计和监控
"""

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Set
from datetime import datetime
import logging

from .service_registry import ServiceRegistry, ServiceInstance, ServiceStatus
from .service_discovery_client import ServiceDiscoveryClient, DiscoveryConfig, LoadBalanceStrategy
from .health_integration import HealthIntegration, HealthCheckConfig, HealthCheckType
from .metadata_manager import MetadataManager, MetadataSchema, MetadataChangeEvent


@dataclass
class DiscoveryManagerConfig:
    """发现管理器配置"""
    # 注册中心配置
    heartbeat_interval: int = 30                # 心跳间隔(秒)
    health_check_interval: int = 10             # 健康检查间隔(秒)  
    instance_timeout: int = 90                  # 实例超时时间(秒)
    cleanup_interval: int = 60                  # 清理间隔(秒)
    
    # 健康检查配置
    health_check_type: HealthCheckType = HealthCheckType.HTTP  # 健康检查类型
    health_timeout: float = 5.0                 # 健康检查超时(秒)
    health_retries: int = 3                     # 健康检查重试次数
    success_threshold: int = 2                  # 成功阈值
    failure_threshold: int = 3                  # 失败阈值
    
    # 服务发现配置
    cache_ttl: int = 60                         # 缓存TTL(秒)
    load_balance_strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN
    circuit_breaker_enabled: bool = True       # 启用熔断器
    max_retries: int = 3                        # 最大重试次数
    
    # 其他配置
    enable_health_checks: bool = True           # 启用健康检查
    enable_metadata_management: bool = True    # 启用元数据管理
    enable_event_callbacks: bool = True        # 启用事件回调


class DiscoveryManager:
    """服务发现管理器
    
    提供统一的服务发现管理功能：
    - 组件集成和协调
    - 统一配置管理
    - 生命周期管理
    - 事件回调系统
    - 统计和监控
    """
    
    def __init__(self, config: Optional[DiscoveryManagerConfig] = None):
        """初始化发现管理器
        
        Args:
            config: 配置参数
        """
        self.config = config or DiscoveryManagerConfig()
        
        # 核心组件
        self.registry = ServiceRegistry(
            heartbeat_interval=self.config.heartbeat_interval,
            health_check_interval=self.config.health_check_interval,
            instance_timeout=self.config.instance_timeout,
            cleanup_interval=self.config.cleanup_interval
        )
        
        self.metadata_manager = MetadataManager() if self.config.enable_metadata_management else None
        
        self.health_integration: Optional[HealthIntegration] = None
        
        # 服务发现客户端缓存
        self._discovery_clients: Dict[str, ServiceDiscoveryClient] = {}
        
        # 状态
        self._running = False
        self._startup_complete = False
        
        # 回调
        self._service_callbacks: List[Callable] = []
        self._health_callbacks: List[Callable] = []
        self._metadata_callbacks: List[Callable] = []
        
        # 统计信息
        self._stats = {
            'start_time': None,
            'total_services_registered': 0,
            'total_services_deregistered': 0,
            'total_discovery_requests': 0,
            'total_health_checks': 0,
            'total_metadata_operations': 0,
            'active_discovery_clients': 0
        }
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 设置组件间回调
        self._setup_callbacks()
    
    async def start(self):
        """启动发现管理器"""
        if self._running:
            return
        
        self.logger.info("Starting Discovery Manager...")
        
        try:
            # 启动服务注册中心
            self.registry.start()
            
            # 启动健康检查
            if self.config.enable_health_checks:
                health_config = HealthCheckConfig(
                    check_type=self.config.health_check_type,
                    interval=self.config.health_check_interval,
                    timeout=self.config.health_timeout,
                    retries=self.config.health_retries,
                    success_threshold=self.config.success_threshold,
                    failure_threshold=self.config.failure_threshold
                )
                
                self.health_integration = HealthIntegration(self.registry, health_config)
                await self.health_integration.start()
            
            self._running = True
            self._startup_complete = True
            self._stats['start_time'] = datetime.now()
            
            self.logger.info("Discovery Manager started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start Discovery Manager: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止发现管理器"""
        if not self._running:
            return
        
        self.logger.info("Stopping Discovery Manager...")
        
        try:
            # 停止健康检查
            if self.health_integration:
                await self.health_integration.stop()
                self.health_integration = None
            
            # 停止服务注册中心
            self.registry.stop()
            
            # 清理发现客户端
            self._discovery_clients.clear()
            
            self._running = False
            self._startup_complete = False
            
            self.logger.info("Discovery Manager stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Discovery Manager: {e}")
    
    def register_service(self, instance: ServiceInstance) -> bool:
        """注册服务
        
        Args:
            instance: 服务实例
            
        Returns:
            bool: 注册是否成功
        """
        if not self._running:
            self.logger.error("Discovery Manager is not running")
            return False
        
        success = self.registry.register_service(instance)
        
        if success:
            self._stats['total_services_registered'] += 1
            
            # 同步元数据
            if self.metadata_manager:
                self._sync_instance_metadata(instance)
        
        return success
    
    def deregister_service(self, instance_id: str) -> bool:
        """注销服务
        
        Args:
            instance_id: 实例ID
            
        Returns:
            bool: 注销是否成功
        """
        if not self._running:
            self.logger.error("Discovery Manager is not running")
            return False
        
        success = self.registry.deregister_service(instance_id)
        
        if success:
            self._stats['total_services_deregistered'] += 1
        
        return success
    
    def get_discovery_client(self, service_name: str, 
                           custom_config: Optional[DiscoveryConfig] = None) -> ServiceDiscoveryClient:
        """获取服务发现客户端
        
        Args:
            service_name: 服务名称
            custom_config: 自定义配置
            
        Returns:
            ServiceDiscoveryClient: 发现客户端
        """
        if not self._running:
            raise RuntimeError("Discovery Manager is not running")
        
        cache_key = f"{service_name}_{hash(str(custom_config)) if custom_config else 'default'}"
        
        if cache_key not in self._discovery_clients:
            # 创建配置
            if custom_config:
                config = custom_config
            else:
                config = DiscoveryConfig(
                    service_name=service_name,
                    load_balance_strategy=self.config.load_balance_strategy,
                    cache_ttl=self.config.cache_ttl,
                    circuit_breaker_enabled=self.config.circuit_breaker_enabled,
                    max_retries=self.config.max_retries
                )
            
            # 创建客户端
            client = ServiceDiscoveryClient(self.registry, config)
            self._discovery_clients[cache_key] = client
            
            with self._lock:
                self._stats['active_discovery_clients'] += 1
        
        return self._discovery_clients[cache_key]
    
    async def discover_service(self, service_name: str, 
                              client_ip: Optional[str] = None,
                              custom_config: Optional[DiscoveryConfig] = None) -> Optional[ServiceInstance]:
        """发现服务实例
        
        Args:
            service_name: 服务名称
            client_ip: 客户端IP
            custom_config: 自定义配置
            
        Returns:
            Optional[ServiceInstance]: 服务实例
        """
        if not self._running:
            self.logger.error("Discovery Manager is not running")
            return None
        
        client = self.get_discovery_client(service_name, custom_config)
        instance = await client.discover_instance(client_ip)
        
        self._stats['total_discovery_requests'] += 1
        
        return instance
    
    def register_metadata_schema(self, schema: MetadataSchema) -> bool:
        """注册元数据模式
        
        Args:
            schema: 元数据模式
            
        Returns:
            bool: 注册是否成功
        """
        if not self.metadata_manager:
            self.logger.warning("Metadata management is disabled")
            return False
        
        return self.metadata_manager.register_schema(schema)
    
    def set_service_metadata(self, service_name: str, key: str, value: Any) -> bool:
        """设置服务元数据
        
        Args:
            service_name: 服务名称
            key: 元数据键
            value: 元数据值
            
        Returns:
            bool: 设置是否成功
        """
        if not self.metadata_manager:
            self.logger.warning("Metadata management is disabled")
            return False
        
        success = self.metadata_manager.set_service_metadata(service_name, key, value)
        
        if success:
            self._stats['total_metadata_operations'] += 1
        
        return success
    
    def set_instance_metadata(self, instance_id: str, service_name: str, 
                            key: str, value: Any) -> bool:
        """设置实例元数据
        
        Args:
            instance_id: 实例ID
            service_name: 服务名称
            key: 元数据键
            value: 元数据值
            
        Returns:
            bool: 设置是否成功
        """
        if not self.metadata_manager:
            self.logger.warning("Metadata management is disabled")
            return False
        
        success = self.metadata_manager.set_instance_metadata(instance_id, service_name, key, value)
        
        if success:
            self._stats['total_metadata_operations'] += 1
        
        return success
    
    def query_services_by_metadata(self, filters: Dict[str, Any]) -> List[str]:
        """根据元数据查询服务
        
        Args:
            filters: 过滤条件
            
        Returns:
            List[str]: 服务名称列表
        """
        if not self.metadata_manager:
            return []
        
        return self.metadata_manager.query_services_by_metadata(filters)
    
    def add_service_tag(self, service_name: str, tag: str) -> bool:
        """为服务添加标签
        
        Args:
            service_name: 服务名称
            tag: 标签
            
        Returns:
            bool: 添加是否成功
        """
        if not self.metadata_manager:
            return False
        
        return self.metadata_manager.add_service_tag(service_name, tag)
    
    def query_by_tags(self, tags: Set[str], match_all: bool = True) -> Dict[str, List[str]]:
        """根据标签查询
        
        Args:
            tags: 标签集合
            match_all: 是否匹配所有标签
            
        Returns:
            Dict[str, List[str]]: 查询结果
        """
        if not self.metadata_manager:
            return {"services": [], "instances": []}
        
        return self.metadata_manager.query_by_tags(tags, match_all)
    
    def add_service_callback(self, callback: Callable[[ServiceInstance, str], None]):
        """添加服务事件回调
        
        Args:
            callback: 回调函数 (instance, event_type)
        """
        self._service_callbacks.append(callback)
    
    def add_health_callback(self, callback: Callable):
        """添加健康状态变化回调
        
        Args:
            callback: 回调函数
        """
        self._health_callbacks.append(callback)
    
    def add_metadata_callback(self, callback: Callable[[MetadataChangeEvent], None]):
        """添加元数据变化回调
        
        Args:
            callback: 回调函数
        """
        self._metadata_callbacks.append(callback)
        
        if self.metadata_manager:
            self.metadata_manager.add_change_callback(callback)
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """获取综合统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            stats = self._stats.copy()
            
            # 添加组件统计
            stats['registry'] = self.registry.get_stats()
            
            if self.health_integration:
                stats['health'] = self.health_integration.get_stats()
            
            if self.metadata_manager:
                stats['metadata'] = self.metadata_manager.get_stats()
            
            # 添加发现客户端统计
            stats['discovery_clients'] = {}
            for client_key, client in self._discovery_clients.items():
                stats['discovery_clients'][client_key] = client.get_stats()
            
            return stats
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取整体健康状态
        
        Returns:
            Dict[str, Any]: 健康状态
        """
        status = {
            'overall_status': 'healthy' if self._running and self._startup_complete else 'unhealthy',
            'components': {
                'registry': 'healthy' if self.registry else 'unhealthy',
                'health_integration': 'healthy' if self.health_integration else 'disabled',
                'metadata_manager': 'healthy' if self.metadata_manager else 'disabled'
            },
            'stats': self.get_comprehensive_stats()
        }
        
        return status
    
    def _setup_callbacks(self):
        """设置组件间回调"""
        if self.config.enable_event_callbacks:
            # 注册中心回调
            self.registry.add_registration_callback(self._on_service_registered)
            self.registry.add_deregistration_callback(self._on_service_deregistered)
            self.registry.add_status_change_callback(self._on_service_status_changed)
    
    def _on_service_registered(self, instance: ServiceInstance):
        """服务注册回调"""
        for callback in self._service_callbacks:
            try:
                callback(instance, "registered")
            except Exception as e:
                self.logger.error(f"Error in service registration callback: {e}")
        
        # 同步元数据
        if self.metadata_manager:
            self._sync_instance_metadata(instance)
    
    def _on_service_deregistered(self, instance: ServiceInstance):
        """服务注销回调"""
        for callback in self._service_callbacks:
            try:
                callback(instance, "deregistered")
            except Exception as e:
                self.logger.error(f"Error in service deregistration callback: {e}")
    
    def _on_service_status_changed(self, instance: ServiceInstance, 
                                  old_status: ServiceStatus, new_status: ServiceStatus):
        """服务状态变化回调"""
        for callback in self._service_callbacks:
            try:
                callback(instance, f"status_changed:{old_status.value}->{new_status.value}")
            except Exception as e:
                self.logger.error(f"Error in service status change callback: {e}")
    
    def _sync_instance_metadata(self, instance: ServiceInstance):
        """同步实例元数据到元数据管理器"""
        if not self.metadata_manager:
            return
        
        try:
            # 同步基本元数据
            for key, value in instance.metadata.items():
                self.metadata_manager.set_instance_metadata(
                    instance.instance_id, instance.service_name, key, value
                )
            
            # 同步标签
            for tag in instance.tags:
                self.metadata_manager.add_instance_tag(
                    instance.instance_id, instance.service_name, tag
                )
                
        except Exception as e:
            self.logger.error(f"Failed to sync instance metadata: {e}")
    
    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running
    
    @property
    def is_ready(self) -> bool:
        """检查是否就绪"""
        return self._running and self._startup_complete