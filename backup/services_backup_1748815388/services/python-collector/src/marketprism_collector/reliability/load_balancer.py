"""
MarketPrism 负载均衡系统 (基础版本)

设计目标：
- 多实例部署支持
- 横向扩展能力
- 健康状态感知选择
- 智能负载分配

当前状态：基础框架实现
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LoadBalancingStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    HEALTH_AWARE = "health_aware"


@dataclass
class InstanceInfo:
    """实例信息"""
    id: str
    weight: float = 1.0
    active_connections: int = 0
    total_requests: int = 0
    error_rate: float = 0.0
    is_healthy: bool = True
    last_health_check: float = 0.0


class LoadBalancer:
    """负载均衡器 (基础实现)"""
    
    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN):
        self.strategy = strategy
        self.instances: List[InstanceInfo] = []
        self.current_index = 0
        self.health_status: Dict[str, bool] = {}
        self.load_metrics: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"负载均衡器已初始化，策略: {strategy.value}")
    
    async def add_instance(self, instance_id: str, weight: float = 1.0):
        """添加实例"""
        instance = InstanceInfo(
            id=instance_id,
            weight=weight
        )
        self.instances.append(instance)
        self.health_status[instance_id] = True
        logger.info(f"添加实例: {instance_id}, 权重: {weight}")
    
    async def select_instance(self, request_type: str = "default") -> Optional[InstanceInfo]:
        """选择实例"""
        if not self.instances:
            return None
        
        healthy_instances = [
            instance for instance in self.instances 
            if self.health_status.get(instance.id, False)
        ]
        
        if not healthy_instances:
            logger.warning("没有健康的实例可用")
            return None
        
        if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._round_robin_select(healthy_instances)
        elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections_select(healthy_instances)
        else:
            return healthy_instances[0]  # 默认返回第一个
    
    def _round_robin_select(self, instances: List[InstanceInfo]) -> InstanceInfo:
        """轮询选择"""
        selected = instances[self.current_index % len(instances)]
        self.current_index += 1
        return selected
    
    def _least_connections_select(self, instances: List[InstanceInfo]) -> InstanceInfo:
        """最少连接选择"""
        return min(instances, key=lambda x: x.active_connections)
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "strategy": self.strategy.value,
            "total_instances": len(self.instances),
            "healthy_instances": sum(1 for status in self.health_status.values() if status),
            "instances": [
                {
                    "id": instance.id,
                    "weight": instance.weight,
                    "active_connections": instance.active_connections,
                    "is_healthy": self.health_status.get(instance.id, False)
                }
                for instance in self.instances
            ]
        } 