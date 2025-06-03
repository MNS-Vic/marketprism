#!/usr/bin/env python3
"""
MarketPrism 服务健康监控器

这个模块实现了企业级服务健康监控系统，提供：
- 多种健康检查策略
- 实时健康状态监控
- 智能阈值管理
- 健康告警机制
- 自动恢复检测

Week 6 Day 2: 微服务服务发现系统 - 服务健康监控器
"""

import asyncio
import aiohttp
import logging
import time
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Union
import threading
from collections import defaultdict, deque

from .service_registry import ServiceInstance, ServiceStatus, ServiceEndpoint

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    """健康状态"""
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    DOWN = "down"

class HealthCheckType(Enum):
    """健康检查类型"""
    HTTP = "http"
    TCP = "tcp"
    GRPC = "grpc"
    CUSTOM = "custom"
    PASSIVE = "passive"  # 被动检查，基于心跳

class HealthAlertLevel(Enum):
    """健康告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class HealthThreshold:
    """健康阈值配置"""
    # 响应时间阈值（毫秒）
    response_time_warning: int = 1000
    response_time_critical: int = 5000
    
    # 成功率阈值（百分比）
    success_rate_warning: float = 90.0
    success_rate_critical: float = 70.0
    
    # 连续失败次数阈值
    consecutive_failures_warning: int = 3
    consecutive_failures_critical: int = 5
    
    # 心跳超时阈值（秒）
    heartbeat_timeout_warning: int = 60
    heartbeat_timeout_critical: int = 120

@dataclass
class HealthCheckResult:
    """健康检查结果"""
    service_id: str
    check_time: datetime
    status: HealthStatus
    response_time_ms: int
    success: bool
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    # 端点信息
    endpoint_url: Optional[str] = None
    http_status_code: Optional[int] = None

@dataclass
class HealthMetrics:
    """健康指标"""
    service_id: str
    
    # 基本指标
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    
    # 性能指标
    average_response_time: float = 0.0
    min_response_time: int = 0
    max_response_time: int = 0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    
    # 可用性指标
    uptime_percentage: float = 100.0
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    
    # 时间指标
    last_check_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    
    # 状态历史
    status_history: List[HealthStatus] = field(default_factory=list)
    
    def success_rate(self) -> float:
        """计算成功率"""
        if self.total_checks == 0:
            return 100.0
        return (self.successful_checks / self.total_checks) * 100

@dataclass
class HealthAlert:
    """健康告警"""
    alert_id: str
    service_id: str
    service_name: str
    level: HealthAlertLevel
    message: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    # 告警详情
    threshold_name: Optional[str] = None
    current_value: Optional[Any] = None
    threshold_value: Optional[Any] = None
    
    def resolve(self):
        """解决告警"""
        self.resolved = True
        self.resolved_at = datetime.now()

@dataclass
class HealthCheck:
    """健康检查配置"""
    service_id: str
    check_type: HealthCheckType
    endpoint: ServiceEndpoint
    interval: int = 30  # 检查间隔（秒）
    timeout: int = 5    # 超时时间（秒）
    
    # HTTP检查配置
    http_method: str = "GET"
    http_path: str = "/health"
    expected_status_codes: List[int] = field(default_factory=lambda: [200])
    headers: Dict[str, str] = field(default_factory=dict)
    
    # 自定义检查配置
    custom_checker: Optional[Callable] = None
    
    # 检查选项
    enabled: bool = True
    retries: int = 1
    
    def get_check_url(self) -> str:
        """获取检查URL"""
        return f"{self.endpoint.protocol}://{self.endpoint.host}:{self.endpoint.port}{self.http_path}"

# 异常类
class HealthMonitorError(Exception):
    """健康监控基础异常"""
    pass

class HealthCheckFailedError(HealthMonitorError):
    """健康检查失败异常"""
    pass

class HealthThresholdExceededError(HealthMonitorError):
    """健康阈值超标异常"""
    pass

@dataclass
class HealthCheckConfig:
    """健康检查配置"""
    # 基本配置
    default_interval: int = 30
    default_timeout: int = 5
    max_concurrent_checks: int = 100
    
    # 阈值配置
    thresholds: HealthThreshold = field(default_factory=HealthThreshold)
    
    # 重试配置
    retry_attempts: int = 2
    retry_delay: float = 1.0
    
    # 历史数据配置
    history_size: int = 100
    metrics_window_size: int = 1000
    
    # 告警配置
    enable_alerts: bool = True
    alert_cooldown: int = 300  # 告警冷却时间（秒）
    
    # 性能配置
    batch_size: int = 10
    enable_metrics: bool = True

class ServiceHealthMonitor:
    """
    企业级服务健康监控器
    
    提供完整的服务健康检查、监控、告警和指标收集功能
    """
    
    def __init__(self, config: HealthCheckConfig = None):
        self.config = config or HealthCheckConfig()
        
        self._health_checks: Dict[str, HealthCheck] = {}
        self._health_metrics: Dict[str, HealthMetrics] = {}
        self._health_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.config.history_size))
        self._response_time_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.config.metrics_window_size))
        
        self._active_alerts: Dict[str, HealthAlert] = {}
        self._alert_history: List[HealthAlert] = []
        self._alert_listeners: List[Callable[[HealthAlert], None]] = []
        
        self._running = False
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            "total_services": 0,
            "healthy_services": 0,
            "warning_services": 0,
            "critical_services": 0,
            "down_services": 0,
            "total_checks": 0,
            "total_alerts": 0,
            "active_alerts": 0
        }
        
        logger.info("服务健康监控器初始化完成")
    
    async def start(self):
        """启动健康监控器"""
        if self._running:
            return
        
        logger.info("启动服务健康监控器")
        self._running = True
        
        # 创建HTTP会话
        connector = aiohttp.TCPConnector(
            limit=self.config.max_concurrent_checks,
            limit_per_host=10
        )
        timeout = aiohttp.ClientTimeout(total=self.config.default_timeout)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        
        # 启动现有健康检查
        with self._lock:
            for health_check in self._health_checks.values():
                if health_check.enabled:
                    await self._start_health_check(health_check)
        
        logger.info("服务健康监控器启动完成")
    
    async def stop(self):
        """停止健康监控器"""
        if not self._running:
            return
        
        logger.info("停止服务健康监控器")
        self._running = False
        
        # 停止所有健康检查任务
        for task in self._check_tasks.values():
            task.cancel()
        
        # 等待任务完成
        if self._check_tasks:
            await asyncio.gather(*self._check_tasks.values(), return_exceptions=True)
        
        self._check_tasks.clear()
        
        # 关闭HTTP会话
        if self._session:
            await self._session.close()
            self._session = None
        
        logger.info("服务健康监控器已停止")
    
    async def add_health_check(self, health_check: HealthCheck):
        """添加健康检查"""
        with self._lock:
            self._health_checks[health_check.service_id] = health_check
            
            # 初始化健康指标
            if health_check.service_id not in self._health_metrics:
                self._health_metrics[health_check.service_id] = HealthMetrics(
                    service_id=health_check.service_id
                )
        
        # 如果监控器正在运行，立即启动检查
        if self._running and health_check.enabled:
            await self._start_health_check(health_check)
        
        logger.info(f"添加健康检查: {health_check.service_id}")
    
    def remove_health_check(self, service_id: str):
        """移除健康检查"""
        with self._lock:
            # 停止检查任务
            if service_id in self._check_tasks:
                self._check_tasks[service_id].cancel()
                del self._check_tasks[service_id]
            
            # 移除配置和数据
            self._health_checks.pop(service_id, None)
            self._health_metrics.pop(service_id, None)
            self._health_history.pop(service_id, None)
            self._response_time_history.pop(service_id, None)
        
        logger.info(f"移除健康检查: {service_id}")
    
    async def check_service_health(self, service_id: str) -> Optional[HealthCheckResult]:
        """立即检查服务健康状态"""
        health_check = self._health_checks.get(service_id)
        if not health_check:
            return None
        
        return await self._perform_health_check(health_check)
    
    def get_service_health_status(self, service_id: str) -> HealthStatus:
        """获取服务健康状态"""
        metrics = self._health_metrics.get(service_id)
        if not metrics or not metrics.status_history:
            return HealthStatus.UNKNOWN
        
        return metrics.status_history[-1]
    
    def get_service_metrics(self, service_id: str) -> Optional[HealthMetrics]:
        """获取服务健康指标"""
        with self._lock:
            return self._health_metrics.get(service_id)
    
    def get_all_service_health(self) -> Dict[str, HealthStatus]:
        """获取所有服务健康状态"""
        with self._lock:
            return {
                service_id: (metrics.status_history[-1] if metrics.status_history else HealthStatus.UNKNOWN)
                for service_id, metrics in self._health_metrics.items()
            }
    
    def get_active_alerts(self) -> List[HealthAlert]:
        """获取活跃告警"""
        with self._lock:
            return [alert for alert in self._active_alerts.values() if not alert.resolved]
    
    def get_alert_history(self, limit: int = 100) -> List[HealthAlert]:
        """获取告警历史"""
        with self._lock:
            return self._alert_history[-limit:]
    
    def add_alert_listener(self, listener: Callable[[HealthAlert], None]):
        """添加告警监听器"""
        self._alert_listeners.append(listener)
    
    def remove_alert_listener(self, listener: Callable[[HealthAlert], None]):
        """移除告警监听器"""
        if listener in self._alert_listeners:
            self._alert_listeners.remove(listener)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            # 实时计算状态统计
            status_counts = defaultdict(int)
            for metrics in self._health_metrics.values():
                if metrics.status_history:
                    status = metrics.status_history[-1]
                    status_counts[status] += 1
            
            active_alerts = len([a for a in self._active_alerts.values() if not a.resolved])
            
            self._stats.update({
                "total_services": len(self._health_metrics),
                "healthy_services": status_counts[HealthStatus.HEALTHY],
                "warning_services": status_counts[HealthStatus.WARNING],
                "critical_services": status_counts[HealthStatus.CRITICAL],
                "down_services": status_counts[HealthStatus.DOWN],
                "total_alerts": len(self._alert_history),
                "active_alerts": active_alerts
            })
            
            return self._stats.copy()
    
    # 私有方法
    async def _start_health_check(self, health_check: HealthCheck):
        """启动健康检查任务"""
        if health_check.service_id in self._check_tasks:
            # 取消现有任务
            self._check_tasks[health_check.service_id].cancel()
        
        # 创建新任务
        task = asyncio.create_task(self._health_check_loop(health_check))
        self._check_tasks[health_check.service_id] = task
    
    async def _health_check_loop(self, health_check: HealthCheck):
        """健康检查循环"""
        service_id = health_check.service_id
        
        while self._running:
            try:
                # 执行健康检查
                result = await self._perform_health_check(health_check)
                
                if result:
                    # 更新指标
                    await self._update_health_metrics(result)
                    
                    # 检查阈值和告警
                    await self._check_thresholds(service_id)
                
                # 等待下次检查
                await asyncio.sleep(health_check.interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查循环异常 {service_id}: {e}")
                await asyncio.sleep(5)
    
    async def _perform_health_check(self, health_check: HealthCheck) -> Optional[HealthCheckResult]:
        """执行健康检查"""
        start_time = time.time()
        
        try:
            if health_check.check_type == HealthCheckType.HTTP:
                return await self._http_health_check(health_check, start_time)
            elif health_check.check_type == HealthCheckType.TCP:
                return await self._tcp_health_check(health_check, start_time)
            elif health_check.check_type == HealthCheckType.CUSTOM:
                return await self._custom_health_check(health_check, start_time)
            else:
                logger.warning(f"不支持的健康检查类型: {health_check.check_type}")
                return None
                
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            
            return HealthCheckResult(
                service_id=health_check.service_id,
                check_time=datetime.now(),
                status=HealthStatus.DOWN,
                response_time_ms=response_time,
                success=False,
                error_message=str(e),
                endpoint_url=health_check.get_check_url()
            )
    
    async def _http_health_check(self, health_check: HealthCheck, start_time: float) -> HealthCheckResult:
        """HTTP健康检查"""
        url = health_check.get_check_url()
        
        async with self._session.request(
            health_check.http_method,
            url,
            headers=health_check.headers,
            timeout=aiohttp.ClientTimeout(total=health_check.timeout)
        ) as response:
            response_time = int((time.time() - start_time) * 1000)
            
            # 检查状态码
            success = response.status in health_check.expected_status_codes
            
            # 确定健康状态
            if success:
                if response_time <= self.config.thresholds.response_time_warning:
                    status = HealthStatus.HEALTHY
                elif response_time <= self.config.thresholds.response_time_critical:
                    status = HealthStatus.WARNING
                else:
                    status = HealthStatus.CRITICAL
            else:
                status = HealthStatus.DOWN
            
            return HealthCheckResult(
                service_id=health_check.service_id,
                check_time=datetime.now(),
                status=status,
                response_time_ms=response_time,
                success=success,
                endpoint_url=url,
                http_status_code=response.status
            )
    
    async def _tcp_health_check(self, health_check: HealthCheck, start_time: float) -> HealthCheckResult:
        """TCP健康检查"""
        try:
            # 尝试建立TCP连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    health_check.endpoint.host,
                    health_check.endpoint.port
                ),
                timeout=health_check.timeout
            )
            
            writer.close()
            await writer.wait_closed()
            
            response_time = int((time.time() - start_time) * 1000)
            
            return HealthCheckResult(
                service_id=health_check.service_id,
                check_time=datetime.now(),
                status=HealthStatus.HEALTHY,
                response_time_ms=response_time,
                success=True,
                endpoint_url=f"tcp://{health_check.endpoint.host}:{health_check.endpoint.port}"
            )
            
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            
            return HealthCheckResult(
                service_id=health_check.service_id,
                check_time=datetime.now(),
                status=HealthStatus.DOWN,
                response_time_ms=response_time,
                success=False,
                error_message=str(e),
                endpoint_url=f"tcp://{health_check.endpoint.host}:{health_check.endpoint.port}"
            )
    
    async def _custom_health_check(self, health_check: HealthCheck, start_time: float) -> HealthCheckResult:
        """自定义健康检查"""
        if not health_check.custom_checker:
            raise HealthCheckFailedError("自定义检查器未定义")
        
        try:
            # 调用自定义检查器
            if asyncio.iscoroutinefunction(health_check.custom_checker):
                result = await health_check.custom_checker(health_check)
            else:
                result = health_check.custom_checker(health_check)
            
            response_time = int((time.time() - start_time) * 1000)
            
            if isinstance(result, bool):
                status = HealthStatus.HEALTHY if result else HealthStatus.DOWN
                return HealthCheckResult(
                    service_id=health_check.service_id,
                    check_time=datetime.now(),
                    status=status,
                    response_time_ms=response_time,
                    success=result
                )
            elif isinstance(result, HealthCheckResult):
                return result
            else:
                raise HealthCheckFailedError(f"无效的自定义检查结果: {type(result)}")
                
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            
            return HealthCheckResult(
                service_id=health_check.service_id,
                check_time=datetime.now(),
                status=HealthStatus.DOWN,
                response_time_ms=response_time,
                success=False,
                error_message=str(e)
            )
    
    async def _update_health_metrics(self, result: HealthCheckResult):
        """更新健康指标"""
        with self._lock:
            service_id = result.service_id
            metrics = self._health_metrics.get(service_id)
            
            if not metrics:
                metrics = HealthMetrics(service_id=service_id)
                self._health_metrics[service_id] = metrics
            
            # 更新基本计数
            metrics.total_checks += 1
            if result.success:
                metrics.successful_checks += 1
                metrics.consecutive_successes += 1
                metrics.consecutive_failures = 0
                metrics.last_success_time = result.check_time
            else:
                metrics.failed_checks += 1
                metrics.consecutive_failures += 1
                metrics.consecutive_successes = 0
                metrics.last_failure_time = result.check_time
            
            # 更新响应时间统计
            self._response_time_history[service_id].append(result.response_time_ms)
            response_times = list(self._response_time_history[service_id])
            
            if response_times:
                metrics.average_response_time = statistics.mean(response_times)
                metrics.min_response_time = min(response_times)
                metrics.max_response_time = max(response_times)
                
                if len(response_times) >= 20:  # 需要足够的样本计算百分位数
                    metrics.p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
                    metrics.p99_response_time = statistics.quantiles(response_times, n=100)[98]  # 99th percentile
            
            # 更新时间信息
            metrics.last_check_time = result.check_time
            
            # 更新状态历史
            metrics.status_history.append(result.status)
            if len(metrics.status_history) > self.config.history_size:
                metrics.status_history = metrics.status_history[-self.config.history_size:]
            
            # 计算可用性
            if metrics.total_checks > 0:
                metrics.uptime_percentage = (metrics.successful_checks / metrics.total_checks) * 100
            
            # 更新全局统计
            self._stats["total_checks"] += 1
    
    async def _check_thresholds(self, service_id: str):
        """检查阈值和生成告警"""
        if not self.config.enable_alerts:
            return
        
        metrics = self._health_metrics.get(service_id)
        if not metrics:
            return
        
        # 检查响应时间阈值
        if metrics.average_response_time > self.config.thresholds.response_time_critical:
            await self._create_alert(
                service_id, HealthAlertLevel.CRITICAL,
                f"响应时间过高: {metrics.average_response_time:.1f}ms",
                "response_time", metrics.average_response_time,
                self.config.thresholds.response_time_critical
            )
        elif metrics.average_response_time > self.config.thresholds.response_time_warning:
            await self._create_alert(
                service_id, HealthAlertLevel.WARNING,
                f"响应时间警告: {metrics.average_response_time:.1f}ms",
                "response_time", metrics.average_response_time,
                self.config.thresholds.response_time_warning
            )
        
        # 检查成功率阈值
        success_rate = metrics.success_rate()
        if success_rate < self.config.thresholds.success_rate_critical:
            await self._create_alert(
                service_id, HealthAlertLevel.CRITICAL,
                f"成功率过低: {success_rate:.1f}%",
                "success_rate", success_rate,
                self.config.thresholds.success_rate_critical
            )
        elif success_rate < self.config.thresholds.success_rate_warning:
            await self._create_alert(
                service_id, HealthAlertLevel.WARNING,
                f"成功率警告: {success_rate:.1f}%",
                "success_rate", success_rate,
                self.config.thresholds.success_rate_warning
            )
        
        # 检查连续失败次数
        if metrics.consecutive_failures >= self.config.thresholds.consecutive_failures_critical:
            await self._create_alert(
                service_id, HealthAlertLevel.CRITICAL,
                f"连续失败次数过多: {metrics.consecutive_failures}",
                "consecutive_failures", metrics.consecutive_failures,
                self.config.thresholds.consecutive_failures_critical
            )
        elif metrics.consecutive_failures >= self.config.thresholds.consecutive_failures_warning:
            await self._create_alert(
                service_id, HealthAlertLevel.WARNING,
                f"连续失败次数警告: {metrics.consecutive_failures}",
                "consecutive_failures", metrics.consecutive_failures,
                self.config.thresholds.consecutive_failures_warning
            )
    
    async def _create_alert(self, service_id: str, level: HealthAlertLevel,
                          message: str, threshold_name: str,
                          current_value: Any, threshold_value: Any):
        """创建告警"""
        # 检查冷却时间
        alert_key = f"{service_id}:{threshold_name}:{level.value}"
        existing_alert = self._active_alerts.get(alert_key)
        
        if existing_alert and not existing_alert.resolved:
            # 在冷却期内，不创建新告警
            time_since_alert = (datetime.now() - existing_alert.timestamp).total_seconds()
            if time_since_alert < self.config.alert_cooldown:
                return
        
        # 创建新告警
        alert = HealthAlert(
            alert_id=f"{service_id}-{int(time.time())}",
            service_id=service_id,
            service_name=service_id,  # 在实际实现中，这应该是服务名称
            level=level,
            message=message,
            timestamp=datetime.now(),
            threshold_name=threshold_name,
            current_value=current_value,
            threshold_value=threshold_value
        )
        
        # 存储告警
        self._active_alerts[alert_key] = alert
        self._alert_history.append(alert)
        
        # 通知监听器
        for listener in self._alert_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(alert)
                else:
                    listener(alert)
            except Exception as e:
                logger.error(f"告警监听器异常: {e}")
        
        logger.warning(f"健康告警: {alert.service_name} - {alert.message}")