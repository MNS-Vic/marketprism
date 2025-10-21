"""
MarketPrism订单簿管理系统健康检查模块

提供系统健康状态检查、监控指标收集和状态报告功能。
"""

import asyncio
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ServiceStatus:
    """服务状态数据类"""
    name: str
    status: str  # healthy, unhealthy, unknown
    last_check: datetime
    response_time: Optional[float] = None
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemMetrics:
    """系统指标数据类"""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: float
    process_count: int


class HealthChecker:
    """健康检查器"""
    
    def __init__(self):

        self.start_time = time.time()
        self.service_statuses: Dict[str, ServiceStatus] = {}
        
        # 健康检查配置
        self.check_timeout = 5.0  # 检查超时时间
        self.unhealthy_threshold = 3  # 连续失败次数阈值
        self.check_interval = 30  # 检查间隔（秒）
        
        # 服务失败计数
        self.failure_counts: Dict[str, int] = {}

    async def check_health(self) -> Dict[str, Any]:
        """简单的健康检查方法"""
        try:
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "uptime_seconds": time.time() - self.start_time,
                "service": "MarketPrism HealthChecker"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "service": "MarketPrism HealthChecker"
            }

    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        try:
            system_metrics = self.get_system_metrics()
            return {
                "status": "running",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "uptime_seconds": time.time() - self.start_time,
                "memory_usage_mb": system_metrics.memory_used_mb,
                "cpu_usage_percent": system_metrics.cpu_percent,
                "service": "MarketPrism System"
            }
        except Exception as e:
            return {
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "service": "MarketPrism System"
            }

    async def check_nats_health(self, nats_client) -> ServiceStatus:
        """检查NATS服务健康状态"""
        start_time = time.time()
        
        try:
            if nats_client and hasattr(nats_client, 'is_connected') and nats_client.is_connected:
                # 尝试发布测试消息
                test_subject = "health.check.test"
                test_data = b"health_check"
                
                await asyncio.wait_for(
                    nats_client.client.publish(test_subject, test_data),
                    timeout=self.check_timeout
                )
                
                response_time = time.time() - start_time
                
                return ServiceStatus(
                    name="nats",
                    status="healthy",
                    last_check=datetime.now(timezone.utc),
                    response_time=response_time,
                    details={
                        "connected": True,
                        "server_info": str(getattr(nats_client.client, 'server_info', {}))
                    }
                )
            else:
                return ServiceStatus(
                    name="nats",
                    status="unhealthy",
                    last_check=datetime.now(timezone.utc),
                    error_message="NATS client not connected"
                )
                
        except asyncio.TimeoutError:
            return ServiceStatus(
                name="nats",
                status="unhealthy",
                last_check=datetime.now(timezone.utc),
                error_message="NATS health check timeout"
            )
        except Exception as e:
            return ServiceStatus(
                name="nats",
                status="unhealthy",
                last_check=datetime.now(timezone.utc),
                error_message=f"NATS health check failed: {str(e)}"
            )
    
    async def check_websocket_health(self, websocket_connections: Dict[str, Any]) -> List[ServiceStatus]:
        """检查WebSocket连接健康状态"""
        statuses = []
        
        for exchange, connection in websocket_connections.items():
            try:
                if connection and hasattr(connection, 'is_connected') and connection.is_connected:
                    last_message_time = getattr(connection, 'last_message_time', None)
                    status = ServiceStatus(
                        name=f"websocket_{exchange}",
                        status="healthy",
                        last_check=datetime.now(timezone.utc),
                        details={
                            "exchange": exchange,
                            "connected": True,
                            "last_message": last_message_time.isoformat() if isinstance(last_message_time, datetime) else last_message_time
                        }
                    )
                else:
                    status = ServiceStatus(
                        name=f"websocket_{exchange}",
                        status="unhealthy",
                        last_check=datetime.now(timezone.utc),
                        error_message=f"{exchange} WebSocket not connected",
                        details={"exchange": exchange, "connected": False}
                    )
                
                statuses.append(status)
                
            except Exception as e:
                status = ServiceStatus(
                    name=f"websocket_{exchange}",
                    status="unhealthy",
                    last_check=datetime.now(timezone.utc),
                    error_message=f"{exchange} WebSocket check failed: {str(e)}",
                    details={"exchange": exchange}
                )
                statuses.append(status)
        
        return statuses
    
    def get_system_metrics(self) -> SystemMetrics:
        """获取系统指标"""
        try:
            # 简化的系统指标，避免依赖psutil
            uptime_seconds = time.time() - self.start_time

            return SystemMetrics(
                cpu_percent=10.5,  # 模拟值
                memory_percent=45.2,  # 模拟值
                memory_used_mb=1024.0,  # 模拟值
                memory_total_mb=2048.0,  # 模拟值
                disk_percent=30.1,  # 模拟值
                disk_used_gb=50.0,  # 模拟值
                disk_total_gb=100.0,  # 模拟值
                uptime_seconds=uptime_seconds,
                process_count=50  # 模拟值
            )
            
        except Exception as e:
            logger.error(f"获取系统指标失败: {str(e)}")
            # 返回默认值
            return SystemMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                memory_total_mb=0.0,
                disk_percent=0.0,
                disk_used_gb=0.0,
                disk_total_gb=0.0,
                uptime_seconds=time.time() - self.start_time,
                process_count=0
            )
    
    async def check_orderbook_manager_health(self, orderbook_manager) -> ServiceStatus:
        """检查订单簿管理器健康状态"""
        try:
            if not orderbook_manager:
                return ServiceStatus(
                    name="orderbook_manager",
                    status="unhealthy",
                    last_check=datetime.now(timezone.utc),
                    error_message="OrderBook manager not initialized"
                )
            
            # 检查活跃交易对数量
            states_dict = getattr(orderbook_manager, 'orderbook_states', {}) or {}
            active_symbols = len(states_dict)

            # 汇总每个symbol的最后更新时间age（秒）
            ages = []
            now = datetime.now(timezone.utc)
            for _, state in states_dict.items():
                ts = getattr(state, 'last_snapshot_time', None)
                if ts is None:
                    continue
                if isinstance(ts, datetime):
                    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ages.append((now - ts).total_seconds())

            # 计算总体健康：存在部分通道老化则标记为 degraded
            if active_symbols == 0:
                status = "unhealthy"
                error_message = "No active symbols"
                time_since_update = float('inf')
            elif not ages:
                status = "unhealthy"
                error_message = "No timestamps available"
                time_since_update = float('inf')
            else:
                min_age = min(ages)
                max_age = max(ages)
                stale_count = sum(1 for a in ages if a >= 60)
                fresh_count = sum(1 for a in ages if a < 60)
                time_since_update = min_age  # 兼容字段：最近一次成功更新距今

                if fresh_count > 0 and stale_count > 0:
                    status = "degraded"
                    error_message = f"{stale_count} symbols stale (>=60s)"
                elif fresh_count > 0 and stale_count == 0:
                    status = "healthy"
                    error_message = None
                else:
                    # 全部陈旧
                    status = "unhealthy"
                    error_message = f"No updates for {min_age:.0f} seconds"

            return ServiceStatus(
                name="orderbook_manager",
                status=status,
                last_check=datetime.now(timezone.utc),
                error_message=error_message,
                details={
                    "active_symbols": active_symbols,
                    "time_since_last_update": time_since_update,
                    "fresh_symbols": int(fresh_count) if active_symbols > 0 else 0,
                    "stale_symbols": int(stale_count) if active_symbols > 0 else 0
                }
            )
            
        except Exception as e:
            return ServiceStatus(
                name="orderbook_manager",
                status="unhealthy",
                last_check=datetime.now(timezone.utc),
                error_message=f"OrderBook manager check failed: {str(e)}"
            )
    
    async def perform_comprehensive_health_check(self, 
                                               nats_client=None, 
                                               websocket_connections=None,
                                               orderbook_manager=None) -> Dict[str, Any]:
        """执行全面健康检查"""
        start_time = time.time()
        
        try:
            # 检查各个服务
            checks = []
            
            # NATS健康检查
            if nats_client:
                nats_status = await self.check_nats_health(nats_client)
                checks.append(nats_status)
            
            # WebSocket健康检查
            if websocket_connections:
                ws_statuses = await self.check_websocket_health(websocket_connections)
                checks.extend(ws_statuses)
            
            # 订单簿管理器健康检查
            if orderbook_manager:
                ob_status = await self.check_orderbook_manager_health(orderbook_manager)
                checks.append(ob_status)
            
            # 获取系统指标
            system_metrics = self.get_system_metrics()
            
            # 计算总体健康状态
            healthy_services = sum(1 for check in checks if check.status == "healthy")
            total_services = len(checks)
            overall_healthy = healthy_services == total_services and total_services > 0
            
            # 构建响应
            health_report = {
                "status": "healthy" if overall_healthy else "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "1.0.0",
                "uptime": system_metrics.uptime_seconds,
                "checks": {check.name: self._serialize_check(check) for check in checks},
                "metrics": asdict(system_metrics),
                "summary": {
                    "total_services": total_services,
                    "healthy_services": healthy_services,
                    "unhealthy_services": total_services - healthy_services,
                    "check_duration": time.time() - start_time
                }
            }
            
            # 更新服务状态
            for check in checks:
                self.service_statuses[check.name] = check
                
                # 更新失败计数
                if check.status == "healthy":
                    self.failure_counts[check.name] = 0
                else:
                    self.failure_counts[check.name] = self.failure_counts.get(check.name, 0) + 1
            
            # 确保所有datetime对象都被序列化
            return self._serialize_datetime_objects(health_report)
            
        except Exception as e:
            logger.error(f"健康检查执行失败: {str(e)}")
            return {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": f"Health check failed: {str(e)}",
                "uptime": time.time() - self.start_time
            }

    def _serialize_check(self, check: ServiceStatus) -> Dict[str, Any]:
        """序列化ServiceStatus对象，处理datetime对象"""
        result = asdict(check)
        # 递归处理所有datetime对象
        return self._serialize_datetime_objects(result)

    def _serialize_datetime_objects(self, obj):
        """递归序列化所有datetime对象"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._serialize_datetime_objects(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_datetime_objects(item) for item in obj]
        else:
            return obj

    def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        """获取特定服务状态"""
        return self.service_statuses.get(service_name)
    
    def is_service_critical(self, service_name: str) -> bool:
        """判断服务是否处于关键状态"""
        failure_count = self.failure_counts.get(service_name, 0)
        return failure_count >= self.unhealthy_threshold
