"""健康检查集成 (Health Integration)

实现服务健康检查机制，提供：
- 多协议健康检查支持
- 异步健康监控
- 健康状态回调
- 健康记录统计
- 自动状态更新
"""

import asyncio
import aiohttp
import socket
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime, timedelta
import logging

from .service_registry import ServiceInstance, ServiceRegistry, ServiceStatus


class HealthCheckType(Enum):
    """健康检查类型"""
    HTTP = "http"         # HTTP检查
    HTTPS = "https"       # HTTPS检查
    TCP = "tcp"           # TCP检查
    GRPC = "grpc"         # gRPC检查
    CUSTOM = "custom"     # 自定义检查


@dataclass
class HealthCheckConfig:
    """健康检查配置"""
    check_type: HealthCheckType = HealthCheckType.HTTP  # 检查类型
    interval: int = 10                                  # 检查间隔(秒)
    timeout: float = 5.0                               # 超时时间(秒)
    retries: int = 3                                   # 重试次数
    success_threshold: int = 2                         # 成功阈值
    failure_threshold: int = 3                         # 失败阈值
    path: str = "/health"                              # 健康检查路径
    expected_status: int = 200                         # 期望状态码
    expected_response: Optional[str] = None            # 期望响应内容
    headers: Dict[str, str] = field(default_factory=dict)  # HTTP头
    custom_check_func: Optional[Callable] = None       # 自定义检查函数


@dataclass
class HealthRecord:
    """健康记录"""
    timestamp: datetime                                # 时间戳
    status: ServiceStatus                              # 健康状态
    response_time: float                              # 响应时间
    error: Optional[str] = None                       # 错误信息
    check_type: Optional[HealthCheckType] = None      # 检查类型


class HealthIntegration:
    """健康检查集成器
    
    提供企业级健康检查功能：
    - 多协议健康检查支持
    - 异步健康监控
    - 健康状态回调
    - 健康记录统计
    - 自动状态更新
    """
    
    def __init__(self, registry: ServiceRegistry, config: HealthCheckConfig):
        """初始化健康检查集成器
        
        Args:
            registry: 服务注册中心
            config: 健康检查配置
        """
        self.registry = registry
        self.config = config
        
        # 健康状态跟踪
        self._health_states: Dict[str, Dict[str, Any]] = {}  # instance_id -> state
        self._health_records: Dict[str, List[HealthRecord]] = {}  # instance_id -> records
        
        # 异步会话
        self._session: Optional[aiohttp.ClientSession] = None
        
        # 控制
        self._running = False
        self._check_tasks: Dict[str, asyncio.Task] = {}
        
        # 回调
        self._health_change_callbacks: List[Callable] = []
        
        # 统计信息
        self._stats = {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'average_response_time': 0.0,
            'active_monitors': 0
        }
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def start(self):
        """启动健康检查"""
        if self._running:
            return
        
        self._running = True
        
        # 创建HTTP会话
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        # 注册回调监听服务注册事件
        self.registry.add_registration_callback(self._on_service_registered)
        self.registry.add_deregistration_callback(self._on_service_deregistered)
        
        # 为现有实例启动健康检查
        for instance in self.registry.get_all_instances():
            await self._start_health_check(instance)
        
        self.logger.info("Health Integration started")
    
    async def stop(self):
        """停止健康检查"""
        if not self._running:
            return
        
        self._running = False
        
        # 停止所有检查任务
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
        
        self.logger.info("Health Integration stopped")
    
    async def check_instance_health(self, instance: ServiceInstance) -> HealthRecord:
        """检查单个实例健康状态
        
        Args:
            instance: 服务实例
            
        Returns:
            HealthRecord: 健康记录
        """
        start_time = time.time()
        
        try:
            if self.config.check_type == HealthCheckType.HTTP:
                status, error = await self._http_check(instance)
            elif self.config.check_type == HealthCheckType.HTTPS:
                status, error = await self._https_check(instance)
            elif self.config.check_type == HealthCheckType.TCP:
                status, error = await self._tcp_check(instance)
            elif self.config.check_type == HealthCheckType.GRPC:
                status, error = await self._grpc_check(instance)
            elif self.config.check_type == HealthCheckType.CUSTOM:
                status, error = await self._custom_check(instance)
            else:
                status = ServiceStatus.UNKNOWN
                error = f"Unsupported check type: {self.config.check_type}"
            
            response_time = time.time() - start_time
            
            record = HealthRecord(
                timestamp=datetime.now(),
                status=status,
                response_time=response_time,
                error=error,
                check_type=self.config.check_type
            )
            
            # 记录健康状态
            self._record_health_check(instance, record)
            
            return record
            
        except Exception as e:
            response_time = time.time() - start_time
            
            record = HealthRecord(
                timestamp=datetime.now(),
                status=ServiceStatus.UNHEALTHY,
                response_time=response_time,
                error=str(e),
                check_type=self.config.check_type
            )
            
            self._record_health_check(instance, record)
            return record
    
    async def _http_check(self, instance: ServiceInstance) -> Tuple[ServiceStatus, Optional[str]]:
        """HTTP健康检查"""
        url = f"http://{instance.host}:{instance.port}{self.config.path}"
        
        if instance.health_check_url:
            url = instance.health_check_url
        
        try:
            async with self._session.get(url, headers=self.config.headers) as response:
                if response.status == self.config.expected_status:
                    if self.config.expected_response:
                        text = await response.text()
                        if self.config.expected_response in text:
                            return ServiceStatus.HEALTHY, None
                        else:
                            return ServiceStatus.UNHEALTHY, f"Unexpected response content"
                    else:
                        return ServiceStatus.HEALTHY, None
                else:
                    return ServiceStatus.UNHEALTHY, f"HTTP {response.status}"
                    
        except Exception as e:
            return ServiceStatus.UNHEALTHY, str(e)
    
    async def _https_check(self, instance: ServiceInstance) -> Tuple[ServiceStatus, Optional[str]]:
        """HTTPS健康检查"""
        url = f"https://{instance.host}:{instance.port}{self.config.path}"
        
        if instance.health_check_url:
            url = instance.health_check_url
        
        try:
            async with self._session.get(url, headers=self.config.headers, ssl=False) as response:
                if response.status == self.config.expected_status:
                    if self.config.expected_response:
                        text = await response.text()
                        if self.config.expected_response in text:
                            return ServiceStatus.HEALTHY, None
                        else:
                            return ServiceStatus.UNHEALTHY, f"Unexpected response content"
                    else:
                        return ServiceStatus.HEALTHY, None
                else:
                    return ServiceStatus.UNHEALTHY, f"HTTPS {response.status}"
                    
        except Exception as e:
            return ServiceStatus.UNHEALTHY, str(e)
    
    async def _tcp_check(self, instance: ServiceInstance) -> Tuple[ServiceStatus, Optional[str]]:
        """TCP健康检查"""
        try:
            # 创建TCP连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(instance.host, instance.port),
                timeout=self.config.timeout
            )
            
            writer.close()
            await writer.wait_closed()
            
            return ServiceStatus.HEALTHY, None
            
        except Exception as e:
            return ServiceStatus.UNHEALTHY, str(e)
    
    async def _grpc_check(self, instance: ServiceInstance) -> Tuple[ServiceStatus, Optional[str]]:
        """gRPC健康检查"""
        # 这里可以实现gRPC健康检查
        # 目前简化为TCP检查
        return await self._tcp_check(instance)
    
    async def _custom_check(self, instance: ServiceInstance) -> Tuple[ServiceStatus, Optional[str]]:
        """自定义健康检查"""
        if not self.config.custom_check_func:
            return ServiceStatus.UNKNOWN, "No custom check function provided"
        
        try:
            result = await self.config.custom_check_func(instance)
            if isinstance(result, bool):
                return ServiceStatus.HEALTHY if result else ServiceStatus.UNHEALTHY, None
            elif isinstance(result, tuple):
                return result
            else:
                return ServiceStatus.UNHEALTHY, "Invalid custom check result"
                
        except Exception as e:
            return ServiceStatus.UNHEALTHY, str(e)
    
    def _record_health_check(self, instance: ServiceInstance, record: HealthRecord):
        """记录健康检查结果"""
        instance_id = instance.instance_id
        
        with self._lock:
            # 初始化实例状态
            if instance_id not in self._health_states:
                self._health_states[instance_id] = {
                    'consecutive_successes': 0,
                    'consecutive_failures': 0,
                    'current_status': ServiceStatus.UNKNOWN
                }
            
            if instance_id not in self._health_records:
                self._health_records[instance_id] = []
            
            # 添加记录
            self._health_records[instance_id].append(record)
            
            # 只保留最近100条记录
            if len(self._health_records[instance_id]) > 100:
                self._health_records[instance_id] = self._health_records[instance_id][-100:]
            
            # 更新状态计数
            state = self._health_states[instance_id]
            
            if record.status == ServiceStatus.HEALTHY:
                state['consecutive_successes'] += 1
                state['consecutive_failures'] = 0
            else:
                state['consecutive_failures'] += 1
                state['consecutive_successes'] = 0
            
            # 判断是否需要更新实例状态
            old_status = state['current_status']
            new_status = self._determine_health_status(state)
            
            if old_status != new_status:
                state['current_status'] = new_status
                
                # 更新注册中心中的实例状态
                self.registry.update_instance_status(instance_id, new_status)
                
                # 触发健康状态变化回调
                self._trigger_health_change_callbacks(instance, old_status, new_status, record)
            
            # 更新统计
            self._stats['total_checks'] += 1
            if record.status == ServiceStatus.HEALTHY:
                self._stats['successful_checks'] += 1
            else:
                self._stats['failed_checks'] += 1
            
            # 更新平均响应时间
            total_checks = self._stats['total_checks']
            old_avg = self._stats['average_response_time']
            self._stats['average_response_time'] = (
                (old_avg * (total_checks - 1) + record.response_time) / total_checks
            )
    
    def _determine_health_status(self, state: Dict[str, Any]) -> ServiceStatus:
        """确定健康状态"""
        if state['consecutive_successes'] >= self.config.success_threshold:
            return ServiceStatus.HEALTHY
        elif state['consecutive_failures'] >= self.config.failure_threshold:
            return ServiceStatus.UNHEALTHY
        else:
            return state['current_status']  # 保持当前状态
    
    async def _start_health_check(self, instance: ServiceInstance):
        """为实例启动健康检查"""
        instance_id = instance.instance_id
        
        if instance_id in self._check_tasks:
            return  # 已经在检查
        
        # 创建检查任务
        task = asyncio.create_task(self._health_check_loop(instance))
        self._check_tasks[instance_id] = task
        
        with self._lock:
            self._stats['active_monitors'] += 1
        
        self.logger.info(f"Started health check for instance: {instance_id}")
    
    async def _stop_health_check(self, instance: ServiceInstance):
        """停止实例健康检查"""
        instance_id = instance.instance_id
        
        if instance_id in self._check_tasks:
            task = self._check_tasks[instance_id]
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            del self._check_tasks[instance_id]
            
            with self._lock:
                self._stats['active_monitors'] -= 1
            
            self.logger.info(f"Stopped health check for instance: {instance_id}")
    
    async def _health_check_loop(self, instance: ServiceInstance):
        """健康检查循环"""
        instance_id = instance.instance_id
        
        while self._running and instance_id in self._check_tasks:
            try:
                await self.check_instance_health(instance)
                await asyncio.sleep(self.config.interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check loop for {instance_id}: {e}")
                await asyncio.sleep(self.config.interval)
    
    def _on_service_registered(self, instance: ServiceInstance):
        """服务注册回调"""
        if self._running:
            asyncio.create_task(self._start_health_check(instance))
    
    def _on_service_deregistered(self, instance: ServiceInstance):
        """服务注销回调"""
        if self._running:
            asyncio.create_task(self._stop_health_check(instance))
    
    def add_health_change_callback(self, 
                                  callback: Callable[[ServiceInstance, ServiceStatus, ServiceStatus, HealthRecord], None]):
        """添加健康状态变化回调"""
        self._health_change_callbacks.append(callback)
    
    def _trigger_health_change_callbacks(self, instance: ServiceInstance, 
                                       old_status: ServiceStatus,
                                       new_status: ServiceStatus, 
                                       record: HealthRecord):
        """触发健康状态变化回调"""
        for callback in self._health_change_callbacks:
            try:
                callback(instance, old_status, new_status, record)
            except Exception as e:
                self.logger.error(f"Error in health change callback: {e}")
    
    def get_instance_health_records(self, instance_id: str) -> List[HealthRecord]:
        """获取实例健康记录"""
        with self._lock:
            return self._health_records.get(instance_id, []).copy()
    
    def get_instance_health_state(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """获取实例健康状态"""
        with self._lock:
            return self._health_states.get(instance_id, {}).copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()