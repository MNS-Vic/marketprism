#!/usr/bin/env python3
"""
MarketPrism 服务注册中心

这个模块实现了企业级服务注册中心，提供：
- 服务实例生命周期管理
- 服务元数据存储
- 服务健康状态跟踪
- 服务发现查询接口
- 事件通知机制
- 集群高可用支持

Week 6 Day 2: 微服务服务发现系统 - 服务注册中心
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Union
import threading
from collections import defaultdict
import json

logger = logging.getLogger(__name__)

class ServiceStatus(Enum):
    """服务状态枚举"""
    UNKNOWN = "unknown"
    STARTING = "starting" 
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    STOPPED = "stopped"
    MAINTENANCE = "maintenance"

class RegistryEventType(Enum):
    """注册表事件类型"""
    SERVICE_REGISTERED = "service_registered"
    SERVICE_DEREGISTERED = "service_deregistered"
    SERVICE_UPDATED = "service_updated"
    SERVICE_STATUS_CHANGED = "service_status_changed"
    SERVICE_EXPIRED = "service_expired"
    REGISTRY_STARTED = "registry_started"
    REGISTRY_STOPPED = "registry_stopped"

@dataclass
class ServiceEndpoint:
    """服务端点信息"""
    host: str
    port: int
    protocol: str = "http"
    path: str = "/"
    weight: int = 100
    
    @property
    def url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}{self.path}"
    
    def __str__(self) -> str:
        return self.url

@dataclass
class ServiceMetadata:
    """服务元数据"""
    name: str
    version: str
    environment: str = "production"
    tags: Set[str] = field(default_factory=set)
    attributes: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    
    def has_tag(self, tag: str) -> bool:
        return tag in self.tags
    
    def get_attribute(self, key: str, default: Any = None) -> Any:
        return self.attributes.get(key, default)

@dataclass
class ServiceInstance:
    """服务实例"""
    id: str
    metadata: ServiceMetadata
    endpoints: List[ServiceEndpoint]
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_heartbeat: Optional[datetime] = None
    registration_time: Optional[datetime] = None
    ttl: int = 30  # 心跳TTL（秒）
    health_check_url: Optional[str] = None
    
    def __post_init__(self):
        if self.registration_time is None:
            self.registration_time = datetime.now()
        if self.last_heartbeat is None:
            self.last_heartbeat = datetime.now()
    
    @property
    def is_expired(self) -> bool:
        """检查服务实例是否过期"""
        if not self.last_heartbeat:
            return True
        return (datetime.now() - self.last_heartbeat).total_seconds() > self.ttl * 2
    
    @property
    def primary_endpoint(self) -> Optional[ServiceEndpoint]:
        """获取主要端点"""
        if not self.endpoints:
            return None
        return max(self.endpoints, key=lambda ep: ep.weight)
    
    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.now()

@dataclass
class RegistrationRequest:
    """服务注册请求"""
    service_name: str
    service_version: str
    endpoints: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    ttl: int = 30
    health_check_url: Optional[str] = None

@dataclass
class RegistrationResponse:
    """服务注册响应"""
    service_id: str
    success: bool
    message: str
    registered_at: datetime

@dataclass
class DeregistrationRequest:
    """服务注销请求"""
    service_id: str
    reason: str = "normal_shutdown"

@dataclass
class RegistryEvent:
    """注册表事件"""
    event_type: RegistryEventType
    service_id: Optional[str]
    service_name: Optional[str]
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ServiceFilter:
    """服务过滤器"""
    name_pattern: Optional[str] = None
    version_pattern: Optional[str] = None
    environment: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    status: Optional[ServiceStatus] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ServiceQuery:
    """服务查询请求"""
    service_name: Optional[str] = None
    filters: Optional[ServiceFilter] = None
    limit: int = 100
    include_unhealthy: bool = False

# 异常类
class ServiceRegistryError(Exception):
    """服务注册表基础异常"""
    pass

class ServiceNotFoundError(ServiceRegistryError):
    """服务未找到异常"""
    pass

class ServiceAlreadyExistsError(ServiceRegistryError):
    """服务已存在异常"""
    pass

class RegistryUnavailableError(ServiceRegistryError):
    """注册表不可用异常"""
    pass

@dataclass
class ServiceRegistryConfig:
    """服务注册表配置"""
    # 基本配置
    registry_name: str = "marketprism-registry"
    cleanup_interval: int = 30  # 清理间隔（秒）
    max_services: int = 10000
    
    # 持久化配置
    enable_persistence: bool = True
    persistence_path: str = "./registry_data"
    backup_interval: int = 300  # 备份间隔（秒）
    
    # 集群配置
    enable_clustering: bool = False
    cluster_nodes: List[str] = field(default_factory=list)
    replication_factor: int = 3
    
    # 性能配置
    cache_size: int = 1000
    batch_size: int = 100
    max_concurrent_operations: int = 1000
    
    # 监控配置
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    # 安全配置
    enable_auth: bool = False
    auth_token: Optional[str] = None
    allowed_hosts: List[str] = field(default_factory=list)

class ServiceRegistry:
    """
    企业级服务注册中心
    
    提供完整的微服务注册、发现、健康检查和生命周期管理功能
    """
    
    def __init__(self, config: ServiceRegistryConfig = None):
        self.config = config or ServiceRegistryConfig()
        self._services: Dict[str, ServiceInstance] = {}
        self._service_index: Dict[str, Set[str]] = defaultdict(set)  # 按名称索引
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)      # 按标签索引
        self._status_index: Dict[ServiceStatus, Set[str]] = defaultdict(set)  # 按状态索引
        
        self._event_listeners: List[Callable[[RegistryEvent], None]] = []
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._backup_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            "total_registrations": 0,
            "total_deregistrations": 0,
            "total_queries": 0,
            "current_services": 0,
            "healthy_services": 0,
            "unhealthy_services": 0
        }
        
        logger.info(f"服务注册中心初始化完成: {self.config.registry_name}")
    
    async def start(self):
        """启动服务注册中心"""
        if self._running:
            return
        
        logger.info(f"启动服务注册中心: {self.config.registry_name}")
        self._running = True
        
        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # 启动备份任务
        if self.config.enable_persistence:
            self._backup_task = asyncio.create_task(self._backup_loop())
        
        # 发送启动事件
        await self._emit_event(RegistryEvent(
            event_type=RegistryEventType.REGISTRY_STARTED,
            service_id=None,
            service_name=None,
            timestamp=datetime.now(),
            data={"registry_name": self.config.registry_name}
        ))
        
        logger.info("服务注册中心启动完成")
    
    async def stop(self):
        """停止服务注册中心"""
        if not self._running:
            return
        
        logger.info("停止服务注册中心")
        self._running = False
        
        # 取消任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._backup_task:
            self._backup_task.cancel()
        
        # 发送停止事件
        await self._emit_event(RegistryEvent(
            event_type=RegistryEventType.REGISTRY_STOPPED,
            service_id=None,
            service_name=None,
            timestamp=datetime.now(),
            data={"registry_name": self.config.registry_name}
        ))
        
        logger.info("服务注册中心已停止")
    
    async def register_service(self, request: RegistrationRequest) -> RegistrationResponse:
        """注册服务"""
        try:
            with self._lock:
                # 生成服务ID
                service_id = f"{request.service_name}-{uuid.uuid4().hex[:8]}"
                
                # 检查服务数量限制
                if len(self._services) >= self.config.max_services:
                    raise ServiceRegistryError(f"服务数量超过限制: {self.config.max_services}")
                
                # 创建服务元数据
                metadata = ServiceMetadata(
                    name=request.service_name,
                    version=request.service_version,
                    environment=request.metadata.get("environment", "production"),
                    tags=set(request.metadata.get("tags", [])),
                    attributes=request.metadata.get("attributes", {}),
                    dependencies=request.metadata.get("dependencies", [])
                )
                
                # 创建服务端点
                endpoints = []
                for ep_data in request.endpoints:
                    endpoint = ServiceEndpoint(
                        host=ep_data["host"],
                        port=ep_data["port"],
                        protocol=ep_data.get("protocol", "http"),
                        path=ep_data.get("path", "/"),
                        weight=ep_data.get("weight", 100)
                    )
                    endpoints.append(endpoint)
                
                # 创建服务实例
                service_instance = ServiceInstance(
                    id=service_id,
                    metadata=metadata,
                    endpoints=endpoints,
                    status=ServiceStatus.STARTING,
                    ttl=request.ttl,
                    health_check_url=request.health_check_url
                )
                
                # 注册服务
                self._services[service_id] = service_instance
                self._update_indexes(service_instance)
                
                # 更新统计
                self._stats["total_registrations"] += 1
                self._stats["current_services"] = len(self._services)
                
                # 发送注册事件
                await self._emit_event(RegistryEvent(
                    event_type=RegistryEventType.SERVICE_REGISTERED,
                    service_id=service_id,
                    service_name=request.service_name,
                    timestamp=datetime.now(),
                    data={
                        "version": request.service_version,
                        "endpoints": [ep.url for ep in endpoints],
                        "metadata": request.metadata
                    }
                ))
                
                logger.info(f"服务注册成功: {service_id} ({request.service_name})")
                
                return RegistrationResponse(
                    service_id=service_id,
                    success=True,
                    message="服务注册成功",
                    registered_at=service_instance.registration_time
                )
                
        except Exception as e:
            logger.error(f"服务注册失败: {e}")
            return RegistrationResponse(
                service_id="",
                success=False,
                message=f"服务注册失败: {str(e)}",
                registered_at=datetime.now()
            )
    
    async def deregister_service(self, request: DeregistrationRequest) -> bool:
        """注销服务"""
        try:
            with self._lock:
                if request.service_id not in self._services:
                    raise ServiceNotFoundError(f"服务未找到: {request.service_id}")
                
                service_instance = self._services[request.service_id]
                
                # 移除服务
                del self._services[request.service_id]
                self._remove_from_indexes(service_instance)
                
                # 更新统计
                self._stats["total_deregistrations"] += 1
                self._stats["current_services"] = len(self._services)
                
                # 发送注销事件
                await self._emit_event(RegistryEvent(
                    event_type=RegistryEventType.SERVICE_DEREGISTERED,
                    service_id=request.service_id,
                    service_name=service_instance.metadata.name,
                    timestamp=datetime.now(),
                    data={"reason": request.reason}
                ))
                
                logger.info(f"服务注销成功: {request.service_id}")
                return True
                
        except Exception as e:
            logger.error(f"服务注销失败: {e}")
            return False
    
    async def heartbeat(self, service_id: str) -> bool:
        """服务心跳"""
        try:
            with self._lock:
                if service_id not in self._services:
                    return False
                
                service_instance = self._services[service_id]
                old_status = service_instance.status
                
                # 更新心跳
                service_instance.update_heartbeat()
                
                # 如果状态是STARTING，改为HEALTHY
                if service_instance.status == ServiceStatus.STARTING:
                    service_instance.status = ServiceStatus.HEALTHY
                    self._update_status_index(service_instance, old_status)
                    
                    # 发送状态变更事件
                    await self._emit_event(RegistryEvent(
                        event_type=RegistryEventType.SERVICE_STATUS_CHANGED,
                        service_id=service_id,
                        service_name=service_instance.metadata.name,
                        timestamp=datetime.now(),
                        data={"old_status": old_status.value, "new_status": service_instance.status.value}
                    ))
                
                return True
                
        except Exception as e:
            logger.error(f"心跳更新失败: {e}")
            return False
    
    async def update_service_status(self, service_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        try:
            with self._lock:
                if service_id not in self._services:
                    return False
                
                service_instance = self._services[service_id]
                old_status = service_instance.status
                
                if old_status != status:
                    service_instance.status = status
                    self._update_status_index(service_instance, old_status)
                    
                    # 发送状态变更事件
                    await self._emit_event(RegistryEvent(
                        event_type=RegistryEventType.SERVICE_STATUS_CHANGED,
                        service_id=service_id,
                        service_name=service_instance.metadata.name,
                        timestamp=datetime.now(),
                        data={"old_status": old_status.value, "new_status": status.value}
                    ))
                
                return True
                
        except Exception as e:
            logger.error(f"状态更新失败: {e}")
            return False
    
    async def query_services(self, query: ServiceQuery) -> List[ServiceInstance]:
        """查询服务"""
        try:
            with self._lock:
                self._stats["total_queries"] += 1
                
                # 获取候选服务
                if query.service_name:
                    candidate_ids = self._service_index.get(query.service_name, set())
                else:
                    candidate_ids = set(self._services.keys())
                
                # 应用过滤器
                if query.filters:
                    candidate_ids = self._apply_filters(candidate_ids, query.filters)
                
                # 获取服务实例
                services = []
                for service_id in candidate_ids:
                    service = self._services.get(service_id)
                    if service:
                        # 检查是否包含不健康服务
                        if not query.include_unhealthy and service.status not in [ServiceStatus.HEALTHY]:
                            continue
                        services.append(service)
                
                # 限制结果数量
                if query.limit > 0:
                    services = services[:query.limit]
                
                return services
                
        except Exception as e:
            logger.error(f"服务查询失败: {e}")
            return []
    
    async def get_service(self, service_id: str) -> Optional[ServiceInstance]:
        """获取单个服务"""
        with self._lock:
            return self._services.get(service_id)
    
    def add_event_listener(self, listener: Callable[[RegistryEvent], None]):
        """添加事件监听器"""
        self._event_listeners.append(listener)
    
    def remove_event_listener(self, listener: Callable[[RegistryEvent], None]):
        """移除事件监听器"""
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            # 实时计算健康/不健康服务数量
            healthy_count = len(self._status_index[ServiceStatus.HEALTHY])
            unhealthy_count = sum(len(self._status_index[status]) 
                                for status in [ServiceStatus.UNHEALTHY, ServiceStatus.CRITICAL])
            
            self._stats.update({
                "current_services": len(self._services),
                "healthy_services": healthy_count,
                "unhealthy_services": unhealthy_count
            })
            
            return self._stats.copy()
    
    # 私有方法
    def _update_indexes(self, service: ServiceInstance):
        """更新索引"""
        # 按名称索引
        self._service_index[service.metadata.name].add(service.id)
        
        # 按标签索引
        for tag in service.metadata.tags:
            self._tag_index[tag].add(service.id)
        
        # 按状态索引
        self._status_index[service.status].add(service.id)
    
    def _remove_from_indexes(self, service: ServiceInstance):
        """从索引中移除"""
        # 从名称索引移除
        self._service_index[service.metadata.name].discard(service.id)
        
        # 从标签索引移除
        for tag in service.metadata.tags:
            self._tag_index[tag].discard(service.id)
        
        # 从状态索引移除
        self._status_index[service.status].discard(service.id)
    
    def _update_status_index(self, service: ServiceInstance, old_status: ServiceStatus):
        """更新状态索引"""
        self._status_index[old_status].discard(service.id)
        self._status_index[service.status].add(service.id)
    
    def _apply_filters(self, candidate_ids: Set[str], filters: ServiceFilter) -> Set[str]:
        """应用过滤器"""
        filtered_ids = candidate_ids.copy()
        
        # 版本过滤
        if filters.version_pattern:
            filtered_ids = {
                sid for sid in filtered_ids 
                if self._services.get(sid) and filters.version_pattern in self._services[sid].metadata.version
            }
        
        # 环境过滤
        if filters.environment:
            filtered_ids = {
                sid for sid in filtered_ids
                if self._services.get(sid) and self._services[sid].metadata.environment == filters.environment
            }
        
        # 标签过滤
        if filters.tags:
            for tag in filters.tags:
                tag_ids = self._tag_index.get(tag, set())
                filtered_ids = filtered_ids.intersection(tag_ids)
        
        # 状态过滤
        if filters.status:
            status_ids = self._status_index.get(filters.status, set())
            filtered_ids = filtered_ids.intersection(status_ids)
        
        # 属性过滤
        if filters.attributes:
            for key, value in filters.attributes.items():
                filtered_ids = {
                    sid for sid in filtered_ids
                    if self._services.get(sid) and self._services[sid].metadata.get_attribute(key) == value
                }
        
        return filtered_ids
    
    async def _cleanup_loop(self):
        """清理循环 - 移除过期服务"""
        while self._running:
            try:
                expired_services = []
                
                with self._lock:
                    for service_id, service in self._services.items():
                        if service.is_expired:
                            expired_services.append(service_id)
                
                # 移除过期服务
                for service_id in expired_services:
                    await self._remove_expired_service(service_id)
                
                await asyncio.sleep(self.config.cleanup_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理任务异常: {e}")
                await asyncio.sleep(5)
    
    async def _remove_expired_service(self, service_id: str):
        """移除过期服务"""
        try:
            with self._lock:
                if service_id in self._services:
                    service = self._services[service_id]
                    
                    # 移除服务
                    del self._services[service_id]
                    self._remove_from_indexes(service)
                    
                    # 发送过期事件
                    await self._emit_event(RegistryEvent(
                        event_type=RegistryEventType.SERVICE_EXPIRED,
                        service_id=service_id,
                        service_name=service.metadata.name,
                        timestamp=datetime.now(),
                        data={"last_heartbeat": service.last_heartbeat.isoformat() if service.last_heartbeat else None}
                    ))
                    
                    logger.warning(f"移除过期服务: {service_id}")
                    
        except Exception as e:
            logger.error(f"移除过期服务失败: {e}")
    
    async def _backup_loop(self):
        """备份循环"""
        while self._running:
            try:
                await self._backup_registry()
                await asyncio.sleep(self.config.backup_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"备份任务异常: {e}")
                await asyncio.sleep(60)
    
    async def _backup_registry(self):
        """备份注册表"""
        try:
            import os
            
            # 确保备份目录存在
            os.makedirs(self.config.persistence_path, exist_ok=True)
            
            # 准备备份数据
            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "registry_name": self.config.registry_name,
                "services": {},
                "stats": self._stats.copy()
            }
            
            with self._lock:
                for service_id, service in self._services.items():
                    backup_data["services"][service_id] = {
                        "metadata": {
                            "name": service.metadata.name,
                            "version": service.metadata.version,
                            "environment": service.metadata.environment,
                            "tags": list(service.metadata.tags),
                            "attributes": service.metadata.attributes,
                            "dependencies": service.metadata.dependencies
                        },
                        "endpoints": [
                            {
                                "host": ep.host,
                                "port": ep.port,
                                "protocol": ep.protocol,
                                "path": ep.path,
                                "weight": ep.weight
                            }
                            for ep in service.endpoints
                        ],
                        "status": service.status.value,
                        "last_heartbeat": service.last_heartbeat.isoformat() if service.last_heartbeat else None,
                        "registration_time": service.registration_time.isoformat() if service.registration_time else None,
                        "ttl": service.ttl,
                        "health_check_url": service.health_check_url
                    }
            
            # 写入备份文件
            backup_file = os.path.join(
                self.config.persistence_path,
                f"registry_backup_{int(time.time())}.json"
            )
            
            with open(backup_file, 'w') as f:
                json.dump(backup_data, f, indent=2)
            
            logger.debug(f"注册表备份完成: {backup_file}")
            
        except Exception as e:
            logger.error(f"注册表备份失败: {e}")
    
    async def _emit_event(self, event: RegistryEvent):
        """发送事件"""
        for listener in self._event_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                logger.error(f"事件监听器异常: {e}")