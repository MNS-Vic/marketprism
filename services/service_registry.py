"""
服务注册表模块
管理微服务的注册、发现和健康检查
"""
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """服务注册表类"""
    
    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}
        self.health_checks: Dict[str, bool] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self._session:
            await self._session.close()
    
    def register_service(self, service_name: str, service_info: Dict[str, Any]) -> bool:
        """注册服务"""
        try:
            # 验证必要字段
            required_fields = ['name', 'host', 'port']
            for field in required_fields:
                if field not in service_info:
                    logger.error(f"Service {service_name} missing required field: {field}")
                    return False
            
            # 添加注册时间
            service_info['registered_at'] = datetime.now().isoformat()
            service_info['last_heartbeat'] = datetime.now().isoformat()
            
            # 注册服务
            self.services[service_name] = service_info
            self.health_checks[service_name] = False
            
            logger.info(f"Service {service_name} registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register service {service_name}: {e}")
            return False
    
    def unregister_service(self, service_name: str) -> bool:
        """注销服务"""
        try:
            if service_name in self.services:
                del self.services[service_name]
                if service_name in self.health_checks:
                    del self.health_checks[service_name]
                
                logger.info(f"Service {service_name} unregistered successfully")
                return True
            else:
                logger.warning(f"Service {service_name} not found for unregistration")
                return False
                
        except Exception as e:
            logger.error(f"Failed to unregister service {service_name}: {e}")
            return False
    
    def get_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        """获取服务信息"""
        return self.services.get(service_name)
    
    def list_services(self) -> Dict[str, Dict[str, Any]]:
        """列出所有服务"""
        return self.services.copy()
    
    def update_service_heartbeat(self, service_name: str) -> bool:
        """更新服务心跳"""
        if service_name in self.services:
            self.services[service_name]['last_heartbeat'] = datetime.now().isoformat()
            return True
        return False
    
    async def health_check_service(self, service_name: str) -> bool:
        """检查单个服务健康状态"""
        service_info = self.get_service(service_name)
        if not service_info:
            logger.warning(f"Service {service_name} not found for health check")
            return False
        
        try:
            # 构建健康检查URL
            host = service_info['host']
            port = service_info['port']
            health_endpoint = service_info.get('health_endpoint', '/health')
            
            url = f"http://{host}:{port}{health_endpoint}"
            
            # 确保有session
            if not self._session:
                self._session = aiohttp.ClientSession()
            
            # 发送健康检查请求
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    self.health_checks[service_name] = True
                    self.update_service_heartbeat(service_name)
                    logger.debug(f"Service {service_name} health check passed")
                    return True
                else:
                    self.health_checks[service_name] = False
                    logger.warning(f"Service {service_name} health check failed with status {response.status}")
                    return False
                    
        except Exception as e:
            self.health_checks[service_name] = False
            logger.error(f"Health check failed for service {service_name}: {e}")
            return False
    
    async def health_check_all_services(self) -> Dict[str, bool]:
        """检查所有服务健康状态"""
        results = {}
        
        # 并发执行所有健康检查
        tasks = []
        for service_name in self.services.keys():
            task = asyncio.create_task(self.health_check_service(service_name))
            tasks.append((service_name, task))
        
        # 等待所有任务完成
        for service_name, task in tasks:
            try:
                result = await task
                results[service_name] = result
            except Exception as e:
                logger.error(f"Health check task failed for {service_name}: {e}")
                results[service_name] = False
        
        return results
    
    def get_healthy_services(self) -> List[str]:
        """获取健康的服务列表"""
        return [name for name, healthy in self.health_checks.items() if healthy]
    
    def get_unhealthy_services(self) -> List[str]:
        """获取不健康的服务列表"""
        return [name for name, healthy in self.health_checks.items() if not healthy]
    
    def get_service_by_type(self, service_type: str) -> List[Dict[str, Any]]:
        """根据服务类型获取服务"""
        matching_services = []
        for service_name, service_info in self.services.items():
            if service_info.get('type') == service_type:
                matching_services.append(service_info)
        return matching_services
    
    def get_load_balanced_service(self, service_type: str) -> Optional[Dict[str, Any]]:
        """获取负载均衡的服务（简单轮询）"""
        services = self.get_service_by_type(service_type)
        healthy_services = [s for s in services if self.health_checks.get(s['name'], False)]
        
        if not healthy_services:
            return None
        
        # 简单的轮询负载均衡
        # 这里可以实现更复杂的负载均衡算法
        return healthy_services[0]
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        total_services = len(self.services)
        healthy_services = len(self.get_healthy_services())
        unhealthy_services = len(self.get_unhealthy_services())
        
        return {
            'total_services': total_services,
            'healthy_services': healthy_services,
            'unhealthy_services': unhealthy_services,
            'health_percentage': (healthy_services / total_services * 100) if total_services > 0 else 0,
            'last_updated': datetime.now().isoformat()
        }