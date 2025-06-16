"""
服务发现客户端
为微服务提供简单易用的服务发现API
"""

import asyncio
import os
from typing import Dict, List, Optional, Any, Callable
import logging

from .registry import ServiceRegistry, ServiceInstance, ServiceStatus
from .backends import (
    ConsulBackend, EtcdBackend, NATSBackend, 
    RedisBackend, InMemoryBackend
)

logger = logging.getLogger(__name__)


class ServiceDiscoveryClient:
    """服务发现客户端"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.registry: Optional[ServiceRegistry] = None
        self.backend = None
        self.my_instance: Optional[ServiceInstance] = None
        self.auto_register = self.config.get('auto_register', True)
        
    async def initialize(self):
        """初始化服务发现客户端"""
        # 选择后端
        backend_type = self.config.get('backend', 'memory')
        backend_config = self.config.get('backend_config', {})
        
        if backend_type.lower() == 'consul':
            consul_url = backend_config.get('url', os.getenv('CONSUL_URL', 'http://localhost:8500'))
            self.backend = ConsulBackend(consul_url)
        elif backend_type.lower() == 'etcd':
            etcd_url = backend_config.get('url', os.getenv('ETCD_URL', 'http://localhost:2379'))
            self.backend = EtcdBackend(etcd_url)
        elif backend_type.lower() == 'nats':
            nats_url = backend_config.get('url', os.getenv('NATS_URL', 'nats://localhost:4222'))
            self.backend = NATSBackend(nats_url)
        elif backend_type.lower() == 'redis':
            redis_url = backend_config.get('url', os.getenv('REDIS_URL', 'redis://localhost:6379'))
            self.backend = RedisBackend(redis_url)
        else:
            self.backend = InMemoryBackend()
        
        # 创建服务注册表
        self.registry = ServiceRegistry(self.backend, self.config)
        
        # 启动后端连接
        if hasattr(self.backend, '__aenter__'):
            await self.backend.__aenter__()
        
        # 启动注册表
        await self.registry.start()
        
        logger.info(f"服务发现客户端初始化完成，后端: {backend_type}")
    
    async def shutdown(self):
        """关闭服务发现客户端"""
        if self.registry:
            await self.registry.stop()
        
        if self.backend and hasattr(self.backend, '__aexit__'):
            await self.backend.__aexit__(None, None, None)
        
        logger.info("服务发现客户端关闭完成")
    
    async def register_myself(
        self,
        service_name: str,
        host: str,
        port: int,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        version: str = "1.0.0"
    ) -> ServiceInstance:
        """注册当前服务"""
        if not self.registry:
            raise RuntimeError("服务发现客户端未初始化")
        
        self.my_instance = await self.registry.register_service(
            service_name=service_name,
            host=host,
            port=port,
            metadata=metadata,
            tags=tags,
            version=version
        )
        
        logger.info(f"当前服务注册成功: {service_name} at {host}:{port}")
        return self.my_instance
    
    async def deregister_myself(self) -> bool:
        """注销当前服务"""
        if not self.registry or not self.my_instance:
            return False
        
        success = await self.registry.deregister_service(
            self.my_instance.service_name,
            self.my_instance.instance_id
        )
        
        if success:
            self.my_instance = None
            logger.info("当前服务注销成功")
        
        return success
    
    async def discover(self, service_name: str) -> List[ServiceInstance]:
        """发现服务实例"""
        if not self.registry:
            raise RuntimeError("服务发现客户端未初始化")
        
        return await self.registry.discover_service(service_name)
    
    async def get_service(self, service_name: str) -> Optional[ServiceInstance]:
        """获取单个健康的服务实例"""
        if not self.registry:
            raise RuntimeError("服务发现客户端未初始化")
        
        return await self.registry.get_service_instance(service_name)
    
    async def get_service_url(self, service_name: str) -> Optional[str]:
        """获取服务的URL"""
        instance = await self.get_service(service_name)
        return instance.base_url if instance else None
    
    async def list_all_services(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        if not self.registry:
            raise RuntimeError("服务发现客户端未初始化")
        
        return await self.registry.list_all_services()
    
    async def update_my_status(self, status: ServiceStatus) -> bool:
        """更新当前服务状态"""
        if not self.registry or not self.my_instance:
            return False
        
        return await self.registry.update_service_status(
            self.my_instance.service_name,
            self.my_instance.instance_id,
            status
        )
    
    def add_event_handler(self, event_type: str, handler: Callable):
        """添加事件处理器"""
        if self.registry:
            self.registry.add_event_handler(event_type, handler)
    
    def remove_event_handler(self, event_type: str, handler: Callable):
        """移除事件处理器"""
        if self.registry:
            self.registry.remove_event_handler(event_type, handler)
    
    async def wait_for_service(
        self, 
        service_name: str, 
        timeout: int = 60,
        check_interval: int = 5
    ) -> Optional[ServiceInstance]:
        """等待服务可用"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            instance = await self.get_service(service_name)
            if instance:
                logger.info(f"服务 {service_name} 已可用")
                return instance
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"等待服务 {service_name} 超时")
                return None
            
            await asyncio.sleep(check_interval)
    
    async def health_check_service(self, service_name: str, instance_id: str) -> bool:
        """检查特定服务实例的健康状态"""
        instances = await self.discover(service_name)
        
        for instance in instances:
            if instance.instance_id == instance_id:
                if self.registry:
                    return await self.registry._check_instance_health(instance)
        
        return False


# 全局服务发现客户端实例
_global_discovery_client: Optional[ServiceDiscoveryClient] = None


async def get_discovery_client(config: Dict[str, Any] = None) -> ServiceDiscoveryClient:
    """获取全局服务发现客户端"""
    global _global_discovery_client
    
    if _global_discovery_client is None:
        _global_discovery_client = ServiceDiscoveryClient(config)
        await _global_discovery_client.initialize()
    
    return _global_discovery_client


async def shutdown_discovery_client():
    """关闭全局服务发现客户端"""
    global _global_discovery_client
    
    if _global_discovery_client:
        await _global_discovery_client.shutdown()
        _global_discovery_client = None


# 便捷函数
async def register_service(
    service_name: str,
    host: str,
    port: int,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    version: str = "1.0.0",
    config: Dict[str, Any] = None
) -> ServiceInstance:
    """注册服务的便捷函数"""
    client = await get_discovery_client(config)
    return await client.register_myself(service_name, host, port, metadata, tags, version)


async def discover_service(service_name: str, config: Dict[str, Any] = None) -> List[ServiceInstance]:
    """发现服务的便捷函数"""
    client = await get_discovery_client(config)
    return await client.discover(service_name)


async def get_service_url(service_name: str, config: Dict[str, Any] = None) -> Optional[str]:
    """获取服务URL的便捷函数"""
    client = await get_discovery_client(config)
    return await client.get_service_url(service_name)


async def wait_for_service(
    service_name: str, 
    timeout: int = 60,
    config: Dict[str, Any] = None
) -> Optional[ServiceInstance]:
    """等待服务可用的便捷函数"""
    client = await get_discovery_client(config)
    return await client.wait_for_service(service_name, timeout)