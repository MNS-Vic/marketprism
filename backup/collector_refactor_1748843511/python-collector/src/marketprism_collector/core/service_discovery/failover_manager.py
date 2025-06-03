#!/usr/bin/env python3
"""
MarketPrism 故障转移管理器

这个模块实现了企业级故障转移管理系统，提供：
- 智能故障检测
- 自动故障转移
- 熔断器机制
- 重试策略管理
- 服务降级支持

Week 6 Day 2: 微服务服务发现系统 - 故障转移管理器
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Union
import threading
from collections import defaultdict, deque
import math

from .service_registry import ServiceInstance, ServiceStatus
from .health_monitor import HealthStatus, HealthCheckResult

logger = logging.getLogger(__name__)

class FailoverStrategy(Enum):
    """故障转移策略"""
    IMMEDIATE = "immediate"      # 立即切换
    GRADUAL = "gradual"         # 渐进式切换
    MANUAL = "manual"           # 手动切换
    CONDITIONAL = "conditional" # 条件切换

class FailoverTrigger(Enum):
    """故障转移触发器"""
    HEALTH_CHECK_FAILED = "health_check_failed"
    RESPONSE_TIME_HIGH = "response_time_high"
    ERROR_RATE_HIGH = "error_rate_high"
    CONNECTION_REFUSED = "connection_refused"
    TIMEOUT = "timeout"
    MANUAL_TRIGGER = "manual_trigger"

class FailoverState(Enum):
    """故障转移状态"""
    NORMAL = "normal"
    DETECTING = "detecting"
    FAILING_OVER = "failing_over"
    FAILED_OVER = "failed_over"
    RECOVERING = "recovering"
    RECOVERED = "recovered"

class CircuitBreakerState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态，允许请求通过
    OPEN = "open"          # 熔断状态，拒绝请求
    HALF_OPEN = "half_open" # 半开状态，允许少量请求试探

class BackoffStrategy(Enum):
    """退避策略"""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    JITTERED = "jittered"

@dataclass
class FailoverAction:
    """故障转移动作"""
    action_type: str  # 动作类型：redirect, scale, alert, etc.
    target_service: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True

@dataclass
class FailoverEvent:
    """故障转移事件"""
    event_id: str
    service_id: str
    service_name: str
    trigger: FailoverTrigger
    state: FailoverState
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    
    # 故障转移结果
    success: bool = False
    actions_taken: List[FailoverAction] = field(default_factory=list)
    recovery_time: Optional[datetime] = None

@dataclass
class RetryPolicy:
    """重试策略"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_multiplier: float = 2.0
    jitter: bool = True
    
    # 重试条件
    retry_on_timeout: bool = True
    retry_on_connection_error: bool = True
    retry_on_http_errors: List[int] = field(default_factory=lambda: [500, 502, 503, 504])
    
    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        if self.backoff_strategy == BackoffStrategy.FIXED:
            delay = self.base_delay
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.base_delay * (self.backoff_multiplier ** (attempt - 1))
        else:  # JITTERED
            base_delay = self.base_delay * (self.backoff_multiplier ** (attempt - 1))
            delay = base_delay * (0.5 + random.random() * 0.5)
        
        # 应用上限
        delay = min(delay, self.max_delay)
        
        # 添加抖动
        if self.jitter and self.backoff_strategy != BackoffStrategy.JITTERED:
            jitter_amount = delay * 0.1 * random.random()
            delay += jitter_amount
        
        return delay

@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    # 熔断阈值
    failure_threshold: int = 5          # 连续失败次数阈值
    failure_rate_threshold: float = 50.0  # 失败率阈值（百分比）
    minimum_requests: int = 10          # 最小请求数
    
    # 时间窗口
    evaluation_window: int = 60         # 评估窗口（秒）
    open_timeout: int = 60              # 熔断超时时间（秒）
    half_open_max_calls: int = 3        # 半开状态最大调用数
    
    # 成功阈值
    success_threshold: int = 3          # 半开状态成功阈值

@dataclass
class CircuitBreaker:
    """熔断器"""
    service_id: str
    config: CircuitBreakerConfig
    
    def __init__(self, service_id: str, config: CircuitBreakerConfig):
        self.service_id = service_id
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state_changed_time = datetime.now()
        
        # 请求历史（用于计算失败率）
        self.request_history: deque = deque(maxlen=1000)
        self._lock = threading.RLock()
    
    async def call(self, func: Callable, *args, **kwargs):
        """通过熔断器调用函数"""
        # 检查熔断器状态
        if not await self._can_execute():
            raise CircuitBreakerOpenError(f"熔断器开启: {self.service_id}")
        
        try:
            # 执行函数
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # 记录成功
            await self._on_success()
            return result
            
        except Exception as e:
            # 记录失败
            await self._on_failure(e)
            raise
    
    async def _can_execute(self) -> bool:
        """检查是否可以执行"""
        with self._lock:
            current_time = datetime.now()
            
            if self.state == CircuitBreakerState.CLOSED:
                return True
            elif self.state == CircuitBreakerState.OPEN:
                # 检查是否可以转为半开状态
                if (current_time - self.state_changed_time).total_seconds() >= self.config.open_timeout:
                    await self._transition_to_half_open()
                    return True
                return False
            elif self.state == CircuitBreakerState.HALF_OPEN:
                # 半开状态下限制请求数
                return self.success_count < self.config.half_open_max_calls
            
            return False
    
    async def _on_success(self):
        """处理成功调用"""
        with self._lock:
            current_time = datetime.now()
            self.request_history.append((current_time, True))
            
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    await self._transition_to_closed()
            elif self.state == CircuitBreakerState.CLOSED:
                # 重置失败计数
                self.failure_count = 0
    
    async def _on_failure(self, exception: Exception):
        """处理失败调用"""
        with self._lock:
            current_time = datetime.now()
            self.request_history.append((current_time, False))
            self.failure_count += 1
            self.last_failure_time = current_time
            
            if self.state == CircuitBreakerState.HALF_OPEN:
                await self._transition_to_open()
            elif self.state == CircuitBreakerState.CLOSED:
                # 检查是否需要熔断
                if await self._should_trip():
                    await self._transition_to_open()
    
    async def _should_trip(self) -> bool:
        """检查是否应该熔断"""
        # 检查连续失败次数
        if self.failure_count >= self.config.failure_threshold:
            return True
        
        # 检查失败率
        recent_requests = self._get_recent_requests()
        if len(recent_requests) >= self.config.minimum_requests:
            failure_rate = self._calculate_failure_rate(recent_requests)
            if failure_rate >= self.config.failure_rate_threshold:
                return True
        
        return False
    
    def _get_recent_requests(self) -> List[tuple]:
        """获取最近的请求"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(seconds=self.config.evaluation_window)
        
        return [
            (timestamp, success) for timestamp, success in self.request_history
            if timestamp >= cutoff_time
        ]
    
    def _calculate_failure_rate(self, requests: List[tuple]) -> float:
        """计算失败率"""
        if not requests:
            return 0.0
        
        failures = sum(1 for _, success in requests if not success)
        return (failures / len(requests)) * 100
    
    async def _transition_to_open(self):
        """转换到开启状态"""
        self.state = CircuitBreakerState.OPEN
        self.state_changed_time = datetime.now()
        self.success_count = 0
        logger.warning(f"熔断器开启: {self.service_id}")
    
    async def _transition_to_half_open(self):
        """转换到半开状态"""
        self.state = CircuitBreakerState.HALF_OPEN
        self.state_changed_time = datetime.now()
        self.success_count = 0
        logger.info(f"熔断器半开: {self.service_id}")
    
    async def _transition_to_closed(self):
        """转换到关闭状态"""
        self.state = CircuitBreakerState.CLOSED
        self.state_changed_time = datetime.now()
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"熔断器关闭: {self.service_id}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取熔断器指标"""
        with self._lock:
            recent_requests = self._get_recent_requests()
            failure_rate = self._calculate_failure_rate(recent_requests)
            
            return {
                "service_id": self.service_id,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "failure_rate": failure_rate,
                "recent_requests_count": len(recent_requests),
                "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
                "state_changed_time": self.state_changed_time.isoformat()
            }

# 异常类
class FailoverError(Exception):
    """故障转移基础异常"""
    pass

class CircuitBreakerOpenError(FailoverError):
    """熔断器开启异常"""
    pass

class RetryExhaustedError(FailoverError):
    """重试耗尽异常"""
    pass

@dataclass
class FailoverConfig:
    """故障转移配置"""
    # 基本配置
    enable_failover: bool = True
    default_strategy: FailoverStrategy = FailoverStrategy.IMMEDIATE
    
    # 检测配置
    health_check_interval: int = 30
    failure_detection_threshold: int = 3
    recovery_check_interval: int = 60
    
    # 熔断器配置
    enable_circuit_breaker: bool = True
    circuit_breaker_config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    
    # 重试配置
    default_retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    
    # 超时配置
    operation_timeout: int = 30
    recovery_timeout: int = 300
    
    # 告警配置
    enable_alerts: bool = True
    alert_cooldown: int = 300

class FailoverManager:
    """
    企业级故障转移管理器
    
    提供完整的故障检测、转移、恢复和熔断器管理功能
    """
    
    def __init__(self, config: FailoverConfig = None):
        self.config = config or FailoverConfig()
        
        self._service_states: Dict[str, FailoverState] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._failover_history: List[FailoverEvent] = []
        self._retry_policies: Dict[str, RetryPolicy] = {}
        
        self._running = False
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._event_listeners: List[Callable[[FailoverEvent], None]] = []
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            "total_failovers": 0,
            "successful_failovers": 0,
            "failed_failovers": 0,
            "active_circuit_breakers": 0,
            "services_in_failover": 0,
            "average_recovery_time": 0.0
        }
        
        logger.info("故障转移管理器初始化完成")
    
    async def start(self):
        """启动故障转移管理器"""
        if self._running:
            return
        
        logger.info("启动故障转移管理器")
        self._running = True
        
        # 启动监控任务
        if self.config.enable_failover:
            asyncio.create_task(self._monitoring_loop())
        
        logger.info("故障转移管理器启动完成")
    
    async def stop(self):
        """停止故障转移管理器"""
        if not self._running:
            return
        
        logger.info("停止故障转移管理器")
        self._running = False
        
        # 停止监控任务
        for task in self._monitoring_tasks.values():
            task.cancel()
        
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks.values(), return_exceptions=True)
        
        self._monitoring_tasks.clear()
        
        logger.info("故障转移管理器已停止")
    
    def register_service(self, service_id: str, retry_policy: Optional[RetryPolicy] = None):
        """注册服务"""
        with self._lock:
            self._service_states[service_id] = FailoverState.NORMAL
            
            # 设置重试策略
            if retry_policy:
                self._retry_policies[service_id] = retry_policy
            else:
                self._retry_policies[service_id] = self.config.default_retry_policy
            
            # 创建熔断器
            if self.config.enable_circuit_breaker:
                self._circuit_breakers[service_id] = CircuitBreaker(
                    service_id, self.config.circuit_breaker_config
                )
        
        logger.info(f"注册服务到故障转移管理器: {service_id}")
    
    def unregister_service(self, service_id: str):
        """注销服务"""
        with self._lock:
            self._service_states.pop(service_id, None)
            self._retry_policies.pop(service_id, None)
            self._circuit_breakers.pop(service_id, None)
            
            # 停止监控任务
            if service_id in self._monitoring_tasks:
                self._monitoring_tasks[service_id].cancel()
                del self._monitoring_tasks[service_id]
        
        logger.info(f"从故障转移管理器注销服务: {service_id}")
    
    async def execute_with_failover(self, service_id: str, func: Callable, 
                                  *args, **kwargs) -> Any:
        """通过故障转移执行函数"""
        # 获取重试策略
        retry_policy = self._retry_policies.get(service_id, self.config.default_retry_policy)
        
        # 获取熔断器
        circuit_breaker = self._circuit_breakers.get(service_id)
        
        last_exception = None
        
        for attempt in range(1, retry_policy.max_attempts + 1):
            try:
                # 通过熔断器执行
                if circuit_breaker:
                    result = await circuit_breaker.call(func, *args, **kwargs)
                else:
                    result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                
                # 成功执行，检查是否需要恢复
                await self._check_recovery(service_id)
                return result
                
            except CircuitBreakerOpenError:
                # 熔断器开启，直接抛出异常
                raise
            except Exception as e:
                last_exception = e
                
                # 记录失败
                await self._on_service_failure(service_id, e)
                
                # 检查是否应该重试
                if attempt < retry_policy.max_attempts and self._should_retry(e, retry_policy):
                    delay = retry_policy.calculate_delay(attempt)
                    logger.warning(f"执行失败，{delay:.2f}秒后重试 (尝试 {attempt}/{retry_policy.max_attempts}): {service_id}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    break
        
        # 重试耗尽
        raise RetryExhaustedError(f"重试耗尽: {service_id}, 最后异常: {last_exception}")
    
    async def trigger_failover(self, service_id: str, trigger: FailoverTrigger,
                             details: Dict[str, Any] = None) -> bool:
        """手动触发故障转移"""
        try:
            event = FailoverEvent(
                event_id=f"{service_id}-{int(time.time())}",
                service_id=service_id,
                service_name=service_id,
                trigger=trigger,
                state=FailoverState.DETECTING,
                timestamp=datetime.now(),
                details=details or {}
            )
            
            success = await self._execute_failover(event)
            
            event.success = success
            if success:
                self._stats["successful_failovers"] += 1
            else:
                self._stats["failed_failovers"] += 1
            
            # 记录事件
            self._failover_history.append(event)
            
            # 通知监听器
            await self._notify_listeners(event)
            
            return success
            
        except Exception as e:
            logger.error(f"触发故障转移失败: {service_id}, {e}")
            return False
    
    def get_service_state(self, service_id: str) -> FailoverState:
        """获取服务状态"""
        with self._lock:
            return self._service_states.get(service_id, FailoverState.NORMAL)
    
    def get_circuit_breaker_metrics(self, service_id: str) -> Optional[Dict[str, Any]]:
        """获取熔断器指标"""
        circuit_breaker = self._circuit_breakers.get(service_id)
        if circuit_breaker:
            return circuit_breaker.get_metrics()
        return None
    
    def get_all_circuit_breaker_metrics(self) -> Dict[str, Dict[str, Any]]:
        """获取所有熔断器指标"""
        return {
            service_id: breaker.get_metrics()
            for service_id, breaker in self._circuit_breakers.items()
        }
    
    def get_failover_history(self, limit: int = 100) -> List[FailoverEvent]:
        """获取故障转移历史"""
        return self._failover_history[-limit:]
    
    def add_event_listener(self, listener: Callable[[FailoverEvent], None]):
        """添加事件监听器"""
        self._event_listeners.append(listener)
    
    def remove_event_listener(self, listener: Callable[[FailoverEvent], None]):
        """移除事件监听器"""
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            # 计算活跃熔断器数量
            active_breakers = sum(
                1 for breaker in self._circuit_breakers.values()
                if breaker.state != CircuitBreakerState.CLOSED
            )
            
            # 计算处于故障转移状态的服务数量
            services_in_failover = sum(
                1 for state in self._service_states.values()
                if state in [FailoverState.FAILING_OVER, FailoverState.FAILED_OVER]
            )
            
            # 计算平均恢复时间
            recovery_times = [
                (event.recovery_time - event.timestamp).total_seconds()
                for event in self._failover_history
                if event.recovery_time and event.success
            ]
            average_recovery_time = statistics.mean(recovery_times) if recovery_times else 0.0
            
            self._stats.update({
                "active_circuit_breakers": active_breakers,
                "services_in_failover": services_in_failover,
                "average_recovery_time": average_recovery_time
            })
            
            return self._stats.copy()
    
    # 私有方法
    async def _on_service_failure(self, service_id: str, exception: Exception):
        """处理服务失败"""
        # 更新服务状态
        current_state = self.get_service_state(service_id)
        
        if current_state == FailoverState.NORMAL:
            with self._lock:
                self._service_states[service_id] = FailoverState.DETECTING
            
            # 可能触发故障转移
            await self._check_failover_trigger(service_id, exception)
    
    async def _check_failover_trigger(self, service_id: str, exception: Exception):
        """检查故障转移触发条件"""
        # 分析异常类型
        trigger = None
        
        if isinstance(exception, asyncio.TimeoutError):
            trigger = FailoverTrigger.TIMEOUT
        elif "Connection refused" in str(exception):
            trigger = FailoverTrigger.CONNECTION_REFUSED
        elif hasattr(exception, 'status') and exception.status >= 500:
            trigger = FailoverTrigger.ERROR_RATE_HIGH
        else:
            trigger = FailoverTrigger.HEALTH_CHECK_FAILED
        
        # 触发故障转移
        await self.trigger_failover(service_id, trigger, {"exception": str(exception)})
    
    async def _execute_failover(self, event: FailoverEvent) -> bool:
        """执行故障转移"""
        try:
            service_id = event.service_id
            
            # 更新状态
            with self._lock:
                self._service_states[service_id] = FailoverState.FAILING_OVER
                self._stats["total_failovers"] += 1
            
            # 根据策略执行故障转移
            strategy = self.config.default_strategy
            
            if strategy == FailoverStrategy.IMMEDIATE:
                success = await self._immediate_failover(event)
            elif strategy == FailoverStrategy.GRADUAL:
                success = await self._gradual_failover(event)
            else:
                success = await self._immediate_failover(event)  # 默认策略
            
            # 更新状态
            with self._lock:
                if success:
                    self._service_states[service_id] = FailoverState.FAILED_OVER
                else:
                    self._service_states[service_id] = FailoverState.NORMAL
            
            return success
            
        except Exception as e:
            logger.error(f"执行故障转移失败: {event.service_id}, {e}")
            return False
    
    async def _immediate_failover(self, event: FailoverEvent) -> bool:
        """立即故障转移"""
        # 在实际实现中，这里会：
        # 1. 将流量重定向到备用服务
        # 2. 标记原服务为不可用
        # 3. 发送告警通知
        
        logger.info(f"执行立即故障转移: {event.service_id}")
        
        # 模拟故障转移操作
        await asyncio.sleep(0.1)
        
        # 添加故障转移动作
        event.actions_taken.append(FailoverAction(
            action_type="redirect_traffic",
            target_service=f"{event.service_id}-backup",
            parameters={"reason": event.trigger.value}
        ))
        
        return True
    
    async def _gradual_failover(self, event: FailoverEvent) -> bool:
        """渐进式故障转移"""
        # 在实际实现中，这里会：
        # 1. 逐步减少到故障服务的流量
        # 2. 逐步增加到备用服务的流量
        # 3. 监控转移过程
        
        logger.info(f"执行渐进式故障转移: {event.service_id}")
        
        # 模拟渐进式转移
        for percentage in [25, 50, 75, 100]:
            await asyncio.sleep(0.1)
            logger.debug(f"转移 {percentage}% 流量: {event.service_id}")
        
        # 添加故障转移动作
        event.actions_taken.append(FailoverAction(
            action_type="gradual_redirect",
            target_service=f"{event.service_id}-backup",
            parameters={"final_percentage": 100}
        ))
        
        return True
    
    async def _check_recovery(self, service_id: str):
        """检查服务恢复"""
        current_state = self.get_service_state(service_id)
        
        if current_state in [FailoverState.FAILED_OVER, FailoverState.DETECTING]:
            # 服务似乎已恢复，更新状态
            with self._lock:
                self._service_states[service_id] = FailoverState.RECOVERING
            
            # 启动恢复检查
            if service_id not in self._monitoring_tasks:
                task = asyncio.create_task(self._recovery_monitor(service_id))
                self._monitoring_tasks[service_id] = task
    
    async def _recovery_monitor(self, service_id: str):
        """恢复监控"""
        try:
            # 等待一段时间观察服务稳定性
            await asyncio.sleep(self.config.recovery_check_interval)
            
            # 检查服务是否稳定恢复
            # 在实际实现中，这里会进行健康检查等验证
            
            with self._lock:
                if self._service_states.get(service_id) == FailoverState.RECOVERING:
                    self._service_states[service_id] = FailoverState.RECOVERED
                    
                    # 创建恢复事件
                    recovery_event = FailoverEvent(
                        event_id=f"{service_id}-recovery-{int(time.time())}",
                        service_id=service_id,
                        service_name=service_id,
                        trigger=FailoverTrigger.MANUAL_TRIGGER,
                        state=FailoverState.RECOVERED,
                        timestamp=datetime.now(),
                        success=True,
                        recovery_time=datetime.now()
                    )
                    
                    self._failover_history.append(recovery_event)
                    await self._notify_listeners(recovery_event)
                    
                    logger.info(f"服务恢复完成: {service_id}")
            
            # 清理监控任务
            self._monitoring_tasks.pop(service_id, None)
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"恢复监控异常: {service_id}, {e}")
    
    def _should_retry(self, exception: Exception, retry_policy: RetryPolicy) -> bool:
        """检查是否应该重试"""
        if isinstance(exception, asyncio.TimeoutError):
            return retry_policy.retry_on_timeout
        
        if "Connection" in str(exception):
            return retry_policy.retry_on_connection_error
        
        if hasattr(exception, 'status'):
            return exception.status in retry_policy.retry_on_http_errors
        
        return False
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self._running:
            try:
                # 监控熔断器状态
                for service_id, breaker in self._circuit_breakers.items():
                    if breaker.state == CircuitBreakerState.OPEN:
                        # 检查是否可以转为半开状态
                        await breaker._can_execute()
                
                await asyncio.sleep(self.config.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(5)
    
    async def _notify_listeners(self, event: FailoverEvent):
        """通知事件监听器"""
        for listener in self._event_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                logger.error(f"故障转移事件监听器异常: {e}")