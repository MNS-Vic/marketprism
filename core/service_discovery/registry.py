"""
服务注册表核心实现
支持分布式环境下的服务注册、发现和管理
"""

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import logging

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """服务状态枚举"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STARTING = "starting"
    STOPPING = "stopping"
    MAINTENANCE = "maintenance"


@dataclass
class ServiceInstance:
    """服务实例信息"""
    service_name: str
    instance_id: str
    host: str
    port: int
    status: ServiceStatus = ServiceStatus.UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    region: str = "default"
    datacenter: str = "default"
    health_check_url: str = ""
    last_heartbeat: datetime = field(default_factory=datetime.now)
    registered_at: datetime = field(default_factory=datetime.now)
    weight: int = 100  # 负载均衡权重
    
    def __post_init__(self):
        if not self.health_check_url:
            self.health_check_url = f"http://{self.host}:{self.port}/health"
        if not self.instance_id:
            self.instance_id = f"{self.service_name}-{self.host}-{self.port}-{uuid.uuid4().hex[:8]}"
    
    @property
    def address(self) -> str:
        """获取服务地址"""
        return f"{self.host}:{self.port}"
    
    @property
    def base_url(self) -> str:
        """获取服务基础URL"""
        return f"http://{self.host}:{self.port}"
    
    def is_healthy(self) -> bool:
        """检查是否健康"""
        return self.status == ServiceStatus.HEALTHY
    
    def is_expired(self, ttl_seconds: int = 300) -> bool:
        """检查是否过期"""
        return (datetime.now() - self.last_heartbeat).total_seconds() > ttl_seconds
    
    def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        data['last_heartbeat'] = self.last_heartbeat.isoformat()
        data['registered_at'] = self.registered_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServiceInstance':
        """从字典创建实例"""
        data = data.copy()
        data['status'] = ServiceStatus(data['status'])
        data['last_heartbeat'] = datetime.fromisoformat(data['last_heartbeat'])
        data['registered_at'] = datetime.fromisoformat(data['registered_at'])
        return cls(**data)


class ServiceRegistryBackend(ABC):
    """服务注册表后端抽象基类"""
    
    @abstractmethod
    async def register(self, instance: ServiceInstance) -> bool:
        """注册服务实例"""
        pass
    
    @abstractmethod
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """注销服务实例"""
        pass
    
    @abstractmethod
    async def discover(self, service_name: str) -> List[ServiceInstance]:
        """发现服务实例"""
        pass
    
    @abstractmethod
    async def list_all(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        pass
    
    @abstractmethod
    async def update_status(self, service_name: str, instance_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        pass


class ServiceRegistry:
    """服务注册表主类"""
    
    def __init__(self, backend: ServiceRegistryBackend, config: Dict[str, Any] = None):
        self.backend = backend
        self.config = config or {}
        self.local_instances: Dict[str, ServiceInstance] = {}
        self.event_handlers: Dict[str, List[Callable]] = {
            'service_registered': [],
            'service_deregistered': [],
            'service_status_changed': [],
            'service_discovered': []
        }
        
        # 配置参数
        self.health_check_interval = self.config.get('health_check_interval', 30)
        self.instance_ttl = self.config.get('instance_ttl', 300)
        self.cleanup_interval = self.config.get('cleanup_interval', 60)
        
        # 运行状态
        self.running = False
        self.health_check_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动服务注册表"""
        if self.running:
            return
        
        self.running = True
        
        # 启动健康检查任务
        self.health_check_task = asyncio.create_task(self._health_check_loop())
        
        # 启动清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("服务注册表启动完成")
    
    async def stop(self):
        """停止服务注册表"""
        if not self.running:
            return
        
        self.running = False
        
        # 停止任务
        if self.health_check_task:
            self.health_check_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # 注销本地实例
        instances_to_deregister = list(self.local_instances.values())
        for instance in instances_to_deregister:
            await self.deregister_service(instance.service_name, instance.instance_id)
        
        logger.info("服务注册表停止完成")
    
    async def register_service(
        self,
        service_name: str,
        host: str,
        port: int,
        instance_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        version: str = "1.0.0"
    ) -> ServiceInstance:
        """注册服务"""
        instance = ServiceInstance(
            service_name=service_name,
            instance_id=instance_id or f"{service_name}-{host}-{port}-{uuid.uuid4().hex[:8]}",
            host=host,
            port=port,
            metadata=metadata or {},
            tags=tags or [],
            version=version
        )
        
        success = await self.backend.register(instance)
        if success:
            self.local_instances[instance.instance_id] = instance
            await self._emit_event('service_registered', instance)
            logger.info(f"服务注册成功: {service_name} at {host}:{port}")
            return instance
        else:
            raise RuntimeError(f"服务注册失败: {service_name}")
    
    async def deregister_service(self, service_name: str, instance_id: str) -> bool:
        """注销服务"""
        success = await self.backend.deregister(service_name, instance_id)
        if success:
            instance = self.local_instances.pop(instance_id, None)
            if instance:
                await self._emit_event('service_deregistered', instance)
            logger.info(f"服务注销成功: {service_name}#{instance_id}")
        return success
    
    async def discover_service(self, service_name: str) -> List[ServiceInstance]:
        """发现服务实例"""
        instances = await self.backend.discover(service_name)
        
        # 过滤过期实例
        healthy_instances = [
            inst for inst in instances
            if not inst.is_expired(self.instance_ttl)
        ]
        
        await self._emit_event('service_discovered', {
            'service_name': service_name,
            'instances': healthy_instances
        })
        
        return healthy_instances
    
    async def get_service_instance(self, service_name: str) -> Optional[ServiceInstance]:
        """获取单个健康的服务实例（负载均衡）"""
        instances = await self.discover_service(service_name)
        
        # 如果没有实例，返回None
        if not instances:
            return None
        
        # 优先选择健康的实例，如果没有健康的实例，则选择任意实例
        healthy_instances = [inst for inst in instances if inst.is_healthy()]
        if not healthy_instances:
            # 如果没有明确健康的实例，选择状态未知的实例
            unknown_instances = [inst for inst in instances if inst.status == ServiceStatus.UNKNOWN]
            if unknown_instances:
                healthy_instances = unknown_instances
            else:
                # 如果都不健康，返回第一个实例
                return instances[0]
        
        # 简单的加权轮询
        total_weight = sum(inst.weight for inst in healthy_instances)
        if total_weight == 0:
            return healthy_instances[0]
        
        import random
        target = random.randint(1, total_weight)
        current = 0
        
        for instance in healthy_instances:
            current += instance.weight
            if current >= target:
                return instance
        
        return healthy_instances[0]
    
    async def list_all_services(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        return await self.backend.list_all()
    
    async def update_service_status(self, service_name: str, instance_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        success = await self.backend.update_status(service_name, instance_id, status)
        if success:
            # 更新本地缓存
            if instance_id in self.local_instances:
                old_status = self.local_instances[instance_id].status
                self.local_instances[instance_id].status = status
                self.local_instances[instance_id].update_heartbeat()
                
                await self._emit_event('service_status_changed', {
                    'service_name': service_name,
                    'instance_id': instance_id,
                    'old_status': old_status,
                    'new_status': status
                })
        
        return success
    
    def add_event_handler(self, event_type: str, handler: Callable):
        """添加事件处理器"""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].append(handler)
    
    def remove_event_handler(self, event_type: str, handler: Callable):
        """移除事件处理器"""
        if event_type in self.event_handlers and handler in self.event_handlers[event_type]:
            self.event_handlers[event_type].remove(handler)
    
    async def _emit_event(self, event_type: str, data: Any):
        """触发事件"""
        for handler in self.event_handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"事件处理器执行失败 {event_type}: {e}")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.running:
            try:
                all_services = await self.list_all_services()
                
                for service_name, instances in all_services.items():
                    for instance in instances:
                        # 检查健康状态
                        is_healthy = await self._check_instance_health(instance)
                        new_status = ServiceStatus.HEALTHY if is_healthy else ServiceStatus.UNHEALTHY
                        
                        if instance.status != new_status:
                            await self.update_service_status(
                                service_name, 
                                instance.instance_id, 
                                new_status
                            )
                
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")
                await asyncio.sleep(5)
    
    async def _cleanup_loop(self):
        """清理过期实例循环"""
        while self.running:
            try:
                all_services = await self.list_all_services()
                
                for service_name, instances in all_services.items():
                    for instance in instances:
                        if instance.is_expired(self.instance_ttl):
                            logger.info(f"清理过期实例: {service_name}#{instance.instance_id}")
                            await self.deregister_service(service_name, instance.instance_id)
                
                await asyncio.sleep(self.cleanup_interval)
                
            except Exception as e:
                logger.error(f"清理循环错误: {e}")
                await asyncio.sleep(10)
    
    async def _check_instance_health(self, instance: ServiceInstance) -> bool:
        """检查实例健康状态"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    instance.health_check_url,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception:
            return False 