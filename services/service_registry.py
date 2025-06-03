"""
服务注册中心

提供服务发现、健康检查、负载均衡等功能
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ServiceInfo:
    """服务信息"""
    name: str
    host: str
    port: int
    health_check_url: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_heartbeat: Optional[datetime] = None
    status: str = "unknown"  # unknown, healthy, unhealthy


class ServiceRegistry:
    """服务注册中心"""
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.health_check_interval = 30
        self.is_running = False
        
        logger.info("服务注册中心已初始化")
    
    async def register_service(self, service_info: ServiceInfo) -> bool:
        """注册服务"""
        self.services[service_info.name] = service_info
        logger.info(f"服务已注册: {service_info.name} at {service_info.host}:{service_info.port}")
        return True
    
    async def unregister_service(self, service_name: str) -> bool:
        """注销服务"""
        if service_name in self.services:
            del self.services[service_name]
            logger.info(f"服务已注销: {service_name}")
            return True
        return False
    
    def discover_service(self, service_name: str) -> Optional[ServiceInfo]:
        """发现服务"""
        return self.services.get(service_name)
    
    def list_services(self) -> List[ServiceInfo]:
        """列出所有服务"""
        return list(self.services.values())
    
    async def start_health_checks(self):
        """启动健康检查"""
        self.is_running = True
        
        while self.is_running:
            await self._perform_health_checks()
            await asyncio.sleep(self.health_check_interval)
    
    async def _perform_health_checks(self):
        """执行健康检查"""
        for service_name, service_info in self.services.items():
            try:
                # 这里应该实际进行HTTP健康检查
                # 现在只是模拟
                service_info.status = "healthy"
                service_info.last_heartbeat = datetime.now()
            except Exception as e:
                service_info.status = "unhealthy"
                logger.warning(f"服务健康检查失败: {service_name} - {e}")


# 全局服务注册中心实例
service_registry = ServiceRegistry()
