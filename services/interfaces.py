"""
Services模块统一接口定义

定义所有服务的标准接口，确保服务间通信的一致性
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import asyncio


class ServiceInterface(ABC):
    """服务基础接口"""
    
    @abstractmethod
    async def start(self) -> None:
        """启动服务"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """停止服务"""
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        pass
    
    @abstractmethod
    def get_health(self) -> Dict[str, Any]:
        """获取健康状态"""
        pass


class DataCollectorInterface(ServiceInterface):
    """数据收集器接口"""
    
    @abstractmethod
    async def collect_data(self, source: str, params: Dict[str, Any]) -> Any:
        """收集数据"""
        pass


class StorageInterface(ServiceInterface):
    """存储接口"""
    
    @abstractmethod
    async def write_data(self, data: Any, table: str) -> bool:
        """写入数据"""
        pass
    
    @abstractmethod
    async def read_data(self, query: str, params: Dict[str, Any]) -> Any:
        """读取数据"""
        pass


class MonitoringInterface(ServiceInterface):
    """监控接口"""
    
    @abstractmethod
    def record_metric(self, name: str, value: float, labels: Dict[str, str]) -> None:
        """记录指标"""
        pass
    
    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        pass
