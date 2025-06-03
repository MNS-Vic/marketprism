"""
健康检查模块

提供系统健康状态监控，包括连接检查、资源监控等
"""

import asyncio
import time
import psutil
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime, timedelta
from dataclasses import dataclass
import structlog


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: str
    duration_ms: float
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


@dataclass
class HealthStatus:
    """总体健康状态"""
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: str
    uptime_seconds: float
    checks: Dict[str, HealthCheckResult]
    details: Dict[str, Any]


class HealthChecker:
    """健康检查器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.checks: Dict[str, Dict[str, Any]] = {}
        self.start_time = datetime.utcnow()
        
        # TDD改进：添加状态和生命周期管理
        self.status = "stopped"
        self.is_running = False
    
    def register_check(
        self, 
        name: str, 
        check_func: Callable[[], Awaitable[HealthCheckResult]], 
        timeout: float = 5.0,
        critical: bool = True
    ):
        """注册健康检查项
        
        Args:
            name: 检查项名称
            check_func: 检查函数
            timeout: 超时时间（秒）
            critical: 是否为关键检查项
        """
        self.checks[name] = {
            'func': check_func,
            'timeout': timeout,
            'critical': critical
        }
        self.logger.debug("注册健康检查项", name=name, timeout=timeout, critical=critical)
    
    # TDD改进：添加标准化接口方法
    def add_check(self, name: str, check_func: Callable, timeout: float = 5.0, critical: bool = True):
        """TDD改进：添加健康检查项（兼容接口）"""
        # 如果是同步函数，包装成异步
        if not asyncio.iscoroutinefunction(check_func):
            async def async_wrapper():
                result = check_func()
                if isinstance(result, dict):
                    return HealthCheckResult(
                        name=name,
                        status=result.get('status', 'healthy'),
                        message=result.get('message', 'OK'),
                        duration_ms=0.0,
                        timestamp=datetime.utcnow(),
                        details=result.get('details')
                    )
                return result
            check_func = async_wrapper
        
        self.register_check(name, check_func, timeout, critical)
    
    def remove_check(self, name: str):
        """TDD改进：移除健康检查项"""
        if name in self.checks:
            del self.checks[name]
            self.logger.debug("移除健康检查项", name=name)
    
    async def run_checks(self) -> Dict[str, HealthCheckResult]:
        """TDD改进：运行所有健康检查"""
        results = {}
        
        for name, config in self.checks.items():
            try:
                start_time = time.time()
                
                # 执行检查（带超时）
                result = await asyncio.wait_for(
                    config['func'](),
                    timeout=config['timeout']
                )
                
                if not isinstance(result, HealthCheckResult):
                    # 兼容性处理
                    result = HealthCheckResult(
                        name=name,
                        status="healthy",
                        message="OK",
                        duration_ms=(time.time() - start_time) * 1000,
                        timestamp=datetime.utcnow()
                    )
                
                results[name] = result
                
            except asyncio.TimeoutError:
                results[name] = HealthCheckResult(
                    name=name,
                    status="unhealthy",
                    message=f"检查超时 ({config['timeout']}s)",
                    duration_ms=config['timeout'] * 1000,
                    timestamp=datetime.utcnow()
                )
            except Exception as e:
                results[name] = HealthCheckResult(
                    name=name,
                    status="unhealthy",
                    message=f"检查失败: {str(e)}",
                    duration_ms=0.0,
                    timestamp=datetime.utcnow()
                )
        
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """TDD改进：获取健康状态"""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            'status': self.status,
            'is_running': self.is_running,
            'uptime_seconds': uptime,
            'checks_count': len(self.checks),
            'checks': list(self.checks.keys()),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    # TDD改进：生命周期管理方法
    def start(self):
        """启动健康检查器"""
        self.is_running = True
        self.status = "running"
        self.logger.info("健康检查器已启动")
    
    def stop(self):
        """停止健康检查器"""
        self.is_running = False
        self.status = "stopped"
        self.logger.info("健康检查器已停止")
    
    def restart(self):
        """重启健康检查器"""
        self.stop()
        self.start()
        self.logger.info("健康检查器已重启")


# 具体的健康检查函数

async def check_nats_connection(nats_publisher) -> HealthCheckResult:
    """检查NATS连接健康状态"""
    start_time = time.time()
    
    try:
        if not nats_publisher:
            return HealthCheckResult(
                name="nats_connection",
                status="unhealthy",
                message="NATS发布器未初始化",
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow()
            )
        
        if nats_publisher.is_connected:
            return HealthCheckResult(
                name="nats_connection",
                status="healthy", 
                message="NATS连接正常",
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow(),
                details={
                    "server_url": nats_publisher.config.url,
                    "client_name": nats_publisher.config.client_name
                }
            )
        else:
            return HealthCheckResult(
                name="nats_connection",
                status="unhealthy",
                message="NATS连接断开",
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow()
            )
            
    except Exception as e:
        return HealthCheckResult(
            name="nats_connection",
            status="unhealthy",
            message=f"NATS连接检查失败: {str(e)}",
            duration_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow()
        )


async def check_exchange_connections(exchange_adapters: Dict[str, Any]) -> HealthCheckResult:
    """检查交易所连接健康状态"""
    start_time = time.time()
    
    try:
        if not exchange_adapters:
            return HealthCheckResult(
                name="exchange_connections",
                status="degraded",
                message="没有活跃的交易所连接",
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow()
            )
        
        connected_count = 0
        total_count = len(exchange_adapters)
        connection_details = {}
        
        for adapter_key, adapter in exchange_adapters.items():
            try:
                is_connected = adapter.is_connected if hasattr(adapter, 'is_connected') else False
                connection_details[adapter_key] = {
                    "connected": is_connected,
                    "exchange": getattr(adapter, 'exchange_name', 'unknown')
                }
                if is_connected:
                    connected_count += 1
            except Exception as e:
                connection_details[adapter_key] = {
                    "connected": False,
                    "error": str(e)
                }
        
        if connected_count == total_count:
            status = "healthy"
            message = f"所有交易所连接正常 ({connected_count}/{total_count})"
        elif connected_count > 0:
            status = "degraded"
            message = f"部分交易所连接正常 ({connected_count}/{total_count})"
        else:
            status = "unhealthy"
            message = f"所有交易所连接断开 ({connected_count}/{total_count})"
        
        return HealthCheckResult(
            name="exchange_connections",
            status=status,
            message=message,
            duration_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow(),
            details=connection_details
        )
        
    except Exception as e:
        return HealthCheckResult(
            name="exchange_connections",
            status="unhealthy",
            message=f"交易所连接检查失败: {str(e)}",
            duration_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow()
        )


async def check_memory_usage() -> HealthCheckResult:
    """检查内存使用情况"""
    start_time = time.time()
    
    try:
        # 获取系统内存信息
        memory = psutil.virtual_memory()
        process = psutil.Process()
        process_memory = process.memory_info()
        
        # 计算使用率
        system_usage_percent = memory.percent
        process_usage_mb = process_memory.rss / 1024 / 1024
        
        # 判断状态
        if system_usage_percent > 90:
            status = "unhealthy"
            message = f"系统内存使用过高: {system_usage_percent:.1f}%"
        elif system_usage_percent > 80:
            status = "degraded"
            message = f"系统内存使用较高: {system_usage_percent:.1f}%"
        else:
            status = "healthy"
            message = f"内存使用正常: {system_usage_percent:.1f}%"
        
        return HealthCheckResult(
            name="memory_usage",
            status=status,
            message=message,
            duration_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow(),
            details={
                "system_usage_percent": system_usage_percent,
                "system_total_gb": memory.total / 1024 / 1024 / 1024,
                "system_available_gb": memory.available / 1024 / 1024 / 1024,
                "process_usage_mb": process_usage_mb,
                "process_usage_percent": (process_memory.rss / memory.total) * 100
            }
        )
        
    except Exception as e:
        return HealthCheckResult(
            name="memory_usage",
            status="unhealthy",
            message=f"内存检查失败: {str(e)}",
            duration_ms=(time.time() - start_time) * 1000,
            timestamp=datetime.utcnow()
        )


async def monitor_queue_sizes(exchange_adapters: Dict[str, Any], interval: float = 30.0):
    """监控队列大小（后台任务）"""
    logger = structlog.get_logger(__name__)
    
    while True:
        try:
            for adapter_key, adapter in exchange_adapters.items():
                if hasattr(adapter, 'get_queue_sizes'):
                    queue_sizes = adapter.get_queue_sizes()
                    logger.debug("队列大小监控", adapter=adapter_key, sizes=queue_sizes)
            
            await asyncio.sleep(interval)
            
        except Exception as e:
            logger.error("队列大小监控失败", error=str(e))
            await asyncio.sleep(interval)


async def update_system_metrics(interval: float = 60.0):
    """更新系统指标（后台任务）"""
    logger = structlog.get_logger(__name__)
    
    try:
        from .metrics import get_metrics
        metrics = get_metrics()
        
        while True:
            try:
                metrics.update_system_metrics()
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error("系统指标更新失败", error=str(e))
                await asyncio.sleep(interval)
                
    except ImportError:
        logger.warning("无法导入指标模块，跳过系统指标更新")
    except Exception as e:
        logger.error("系统指标更新任务启动失败", error=str(e)) 