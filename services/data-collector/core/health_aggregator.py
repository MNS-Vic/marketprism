"""
健康检查聚合器 - 聚合所有子进程的健康状态

功能：
1. 从子进程收集健康状态
2. 聚合健康状态（整体状态判断）
3. 生成健康检查响应
4. 支持按进程分组的健康状态
"""

import time
from typing import Dict, Optional, Any
from enum import Enum


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"         # 健康
    DEGRADED = "degraded"       # 降级（部分功能异常）
    UNHEALTHY = "unhealthy"     # 不健康（严重异常）
    UNKNOWN = "unknown"         # 未知（无数据）


class ProcessHealth:
    """进程健康状态"""
    
    def __init__(
        self,
        exchange: str,
        status: HealthStatus = HealthStatus.UNKNOWN,
        cpu_percent: float = 0.0,
        memory_mb: float = 0.0,
        uptime_seconds: float = 0.0,
        services: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None
    ):
        self.exchange = exchange
        self.status = status
        self.cpu_percent = cpu_percent
        self.memory_mb = memory_mb
        self.uptime_seconds = uptime_seconds
        self.services = services or {}
        self.timestamp = timestamp or time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "status": self.status.value,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "uptime_seconds": self.uptime_seconds,
            "services": self.services,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, exchange: str, data: Dict[str, Any]) -> 'ProcessHealth':
        """从字典创建"""
        status_str = data.get("status", "unknown")
        try:
            status = HealthStatus(status_str)
        except ValueError:
            status = HealthStatus.UNKNOWN
        
        return cls(
            exchange=exchange,
            status=status,
            cpu_percent=data.get("cpu_percent", 0.0),
            memory_mb=data.get("memory_mb", 0.0),
            uptime_seconds=data.get("uptime_seconds", 0.0),
            services=data.get("services", {}),
            timestamp=data.get("timestamp", time.time())
        )


class HealthAggregator:
    """健康检查聚合器"""
    
    def __init__(self, health_ttl: float = 30.0):
        """
        初始化健康检查聚合器
        
        Args:
            health_ttl: 健康状态过期时间（秒）
        """
        # 存储每个进程的健康状态
        self.process_health: Dict[str, ProcessHealth] = {}
        
        # 健康状态过期时间
        self.health_ttl = health_ttl
        
        # 主进程启动时间
        self.start_time = time.time()
    
    def update_process_health(
        self,
        exchange: str,
        status: str,
        cpu_percent: float,
        memory_mb: float,
        uptime_seconds: float,
        services: Dict[str, Any]
    ):
        """
        更新子进程的健康状态
        
        Args:
            exchange: 交易所名称
            status: 健康状态
            cpu_percent: CPU 使用率
            memory_mb: 内存使用（MB）
            uptime_seconds: 运行时间（秒）
            services: 服务状态详情
        """
        try:
            health_status = HealthStatus(status)
        except ValueError:
            health_status = HealthStatus.UNKNOWN
        
        self.process_health[exchange] = ProcessHealth(
            exchange=exchange,
            status=health_status,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            uptime_seconds=uptime_seconds,
            services=services,
            timestamp=time.time()
        )
    
    def get_process_health(self, exchange: str) -> Optional[ProcessHealth]:
        """获取指定进程的健康状态"""
        health = self.process_health.get(exchange)
        
        # 检查是否过期
        if health and time.time() - health.timestamp > self.health_ttl:
            return ProcessHealth(
                exchange=exchange,
                status=HealthStatus.UNKNOWN
            )
        
        return health
    
    def get_all_process_health(self) -> Dict[str, ProcessHealth]:
        """获取所有进程的健康状态"""
        current_time = time.time()
        result = {}
        
        for exchange, health in self.process_health.items():
            # 检查是否过期
            if current_time - health.timestamp > self.health_ttl:
                result[exchange] = ProcessHealth(
                    exchange=exchange,
                    status=HealthStatus.UNKNOWN
                )
            else:
                result[exchange] = health
        
        return result
    
    def get_aggregated_status(self) -> HealthStatus:
        """
        获取聚合后的整体健康状态
        
        规则：
        - 所有进程健康 → healthy
        - 部分进程降级 → degraded
        - 任一进程不健康 → unhealthy
        - 所有进程未知 → unknown
        """
        if not self.process_health:
            return HealthStatus.UNKNOWN
        
        current_time = time.time()
        statuses = []
        
        for health in self.process_health.values():
            # 检查是否过期
            if current_time - health.timestamp > self.health_ttl:
                statuses.append(HealthStatus.UNKNOWN)
            else:
                statuses.append(health.status)
        
        # 判断整体状态
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.UNKNOWN
    
    def generate_health_response(self) -> Dict[str, Any]:
        """
        生成健康检查响应
        
        Returns:
            Dict: 健康检查响应
        """
        overall_status = self.get_aggregated_status()
        uptime = time.time() - self.start_time
        
        # 获取所有进程的健康状态
        processes = {}
        for exchange, health in self.get_all_process_health().items():
            processes[exchange] = health.to_dict()
        
        # 计算总 CPU 和内存
        total_cpu = sum(h.cpu_percent for h in self.process_health.values())
        total_memory = sum(h.memory_mb for h in self.process_health.values())
        
        # 聚合服务状态
        aggregated_services = {}
        for health in self.process_health.values():
            for service_name, service_status in health.services.items():
                if service_name not in aggregated_services:
                    aggregated_services[service_name] = {
                        "status": "healthy",
                        "count": 0
                    }
                
                # 更新服务状态
                if isinstance(service_status, dict):
                    status = service_status.get("status", "unknown")
                else:
                    status = str(service_status)
                
                aggregated_services[service_name]["count"] += 1
                
                # 如果有任何不健康的服务，更新状态
                if status != "healthy":
                    aggregated_services[service_name]["status"] = status
        
        return {
            "status": overall_status.value,
            "uptime_seconds": uptime,
            "mode": "multiprocess",
            "processes": processes,
            "summary": {
                "total_processes": len(self.process_health),
                "healthy_processes": sum(
                    1 for h in self.process_health.values()
                    if h.status == HealthStatus.HEALTHY
                ),
                "total_cpu_percent": total_cpu,
                "total_memory_mb": total_memory
            },
            "services": aggregated_services
        }
    
    def clear_process_health(self, exchange: str):
        """清除指定进程的健康状态"""
        if exchange in self.process_health:
            del self.process_health[exchange]
    
    def clear_all_health(self):
        """清除所有健康状态"""
        self.process_health.clear()

