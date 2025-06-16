"""
服务接口模块
定义服务的基础接口和抽象类
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ServiceInterface(ABC):
    """服务接口基类"""
    
    def __init__(self, service_name: str, config: Dict[str, Any] = None):
        self.service_name = service_name
        self.config = config or {}
        self.status = "stopped"
        self.start_time: Optional[datetime] = None
        self.metrics: Dict[str, Any] = {}
        self.logger = logging.getLogger(f"service.{service_name}")
    
    async def start(self) -> bool:
        """启动服务"""
        try:
            self.logger.info(f"Starting service {self.service_name}")
            self.status = "starting"
            
            # 执行服务特定的设置
            await self._setup_service()
            
            self.status = "running"
            self.start_time = datetime.now()
            
            self.logger.info(f"Service {self.service_name} started successfully")
            return True
            
        except Exception as e:
            self.status = "error"
            self.logger.error(f"Failed to start service {self.service_name}: {e}")
            raise
    
    async def stop(self) -> bool:
        """停止服务"""
        try:
            self.logger.info(f"Stopping service {self.service_name}")
            self.status = "stopping"
            
            # 执行服务特定的清理
            await self._cleanup_service()
            
            self.status = "stopped"
            self.start_time = None
            
            self.logger.info(f"Service {self.service_name} stopped successfully")
            return True
            
        except Exception as e:
            self.status = "error"
            self.logger.error(f"Failed to stop service {self.service_name}: {e}")
            return False
    
    async def restart(self) -> bool:
        """重启服务"""
        self.logger.info(f"Restarting service {self.service_name}")
        
        if self.status == "running":
            await self.stop()
        
        return await self.start()
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if self.status != "running":
                return False
            
            # 执行服务特定的健康检查
            return await self._perform_health_check()
            
        except Exception as e:
            self.logger.error(f"Health check failed for service {self.service_name}: {e}")
            return False
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取服务指标"""
        try:
            base_metrics = {
                'service_name': self.service_name,
                'status': self.status,
                'uptime': self._get_uptime(),
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'timestamp': datetime.now().isoformat()
            }
            
            # 获取服务特定的指标
            service_metrics = await self._collect_metrics()
            
            # 合并指标
            base_metrics.update(service_metrics)
            self.metrics = base_metrics
            
            return base_metrics
            
        except Exception as e:
            self.logger.error(f"Failed to collect metrics for service {self.service_name}: {e}")
            return {'error': str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'service_name': self.service_name,
            'status': self.status,
            'uptime': self._get_uptime(),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'config': self.config
        }
    
    def _get_uptime(self) -> Optional[float]:
        """获取运行时间（秒）"""
        if self.start_time and self.status == "running":
            return (datetime.now() - self.start_time).total_seconds()
        return None
    
    @abstractmethod
    async def _setup_service(self):
        """服务特定的设置逻辑"""
        pass
    
    @abstractmethod
    async def _cleanup_service(self):
        """服务特定的清理逻辑"""
        pass
    
    async def _perform_health_check(self) -> bool:
        """服务特定的健康检查逻辑"""
        # 默认实现：如果服务在运行就认为健康
        return self.status == "running"
    
    async def _collect_metrics(self) -> Dict[str, Any]:
        """服务特定的指标收集逻辑"""
        # 默认实现：返回空字典
        return {}


class DataCollectorInterface(ServiceInterface):
    """数据收集器接口"""
    
    @abstractmethod
    async def collect_data(self, symbol: str) -> Dict[str, Any]:
        """收集数据"""
        pass
    
    @abstractmethod
    async def subscribe_to_stream(self, symbol: str, data_type: str):
        """订阅数据流"""
        pass
    
    @abstractmethod
    async def unsubscribe_from_stream(self, symbol: str, data_type: str):
        """取消订阅数据流"""
        pass


class APIGatewayInterface(ServiceInterface):
    """API网关接口"""
    
    @abstractmethod
    async def route_request(self, request_path: str, method: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """路由请求"""
        pass
    
    @abstractmethod
    async def authenticate_request(self, headers: Dict[str, str]) -> bool:
        """认证请求"""
        pass
    
    @abstractmethod
    async def rate_limit_check(self, client_id: str) -> bool:
        """速率限制检查"""
        pass


class MonitoringInterface(ServiceInterface):
    """监控服务接口"""
    
    @abstractmethod
    async def collect_system_metrics(self) -> Dict[str, Any]:
        """收集系统指标"""
        pass
    
    @abstractmethod
    async def generate_alerts(self) -> List[Dict[str, Any]]:
        """生成告警"""
        pass
    
    @abstractmethod
    async def store_metrics(self, metrics: Dict[str, Any]):
        """存储指标"""
        pass


class StorageInterface(ServiceInterface):
    """存储服务接口"""
    
    @abstractmethod
    async def save_data(self, key: str, data: Any) -> bool:
        """保存数据"""
        pass
    
    @abstractmethod
    async def load_data(self, key: str) -> Any:
        """加载数据"""
        pass
    
    @abstractmethod
    async def delete_data(self, key: str) -> bool:
        """删除数据"""
        pass
    
    @abstractmethod
    async def query_data(self, query: Dict[str, Any]) -> List[Any]:
        """查询数据"""
        pass


class SchedulerInterface(ServiceInterface):
    """调度器服务接口"""
    
    @abstractmethod
    async def add_job(self, job_config: Dict[str, Any]) -> str:
        """添加任务"""
        pass
    
    @abstractmethod
    async def remove_job(self, job_id: str) -> bool:
        """移除任务"""
        pass
    
    @abstractmethod
    async def list_jobs(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        pass
    
    @abstractmethod
    async def pause_job(self, job_id: str) -> bool:
        """暂停任务"""
        pass
    
    @abstractmethod
    async def resume_job(self, job_id: str) -> bool:
        """恢复任务"""
        pass


class MessageBrokerInterface(ServiceInterface):
    """消息代理服务接口"""
    
    @abstractmethod
    async def publish_message(self, topic: str, message: Dict[str, Any]) -> bool:
        """发布消息"""
        pass
    
    @abstractmethod
    async def subscribe_to_topic(self, topic: str, callback) -> str:
        """订阅主题"""
        pass
    
    @abstractmethod
    async def unsubscribe_from_topic(self, subscription_id: str) -> bool:
        """取消订阅主题"""
        pass
    
    @abstractmethod
    async def create_topic(self, topic: str, config: Dict[str, Any] = None) -> bool:
        """创建主题"""
        pass
    
    @abstractmethod
    async def delete_topic(self, topic: str) -> bool:
        """删除主题"""
        pass