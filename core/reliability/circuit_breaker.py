"""
MarketPrism 熔断器系统

设计目标：
- 防止雪崩效应
- 保护系统稳定性  
- 提供优雅降级策略
- 支持自动恢复机制

状态转换：
CLOSED -> OPEN -> HALF_OPEN -> CLOSED
"""

from datetime import datetime, timezone
import asyncio
import time
import logging
from typing import Any, Callable, Optional, Dict, List
from enum import Enum
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


class CircuitBreakerOpenException(Exception):
    """熔断器开放状态异常"""
    pass


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "CLOSED"      # 关闭状态：正常运行
    OPEN = "OPEN"          # 开放状态：熔断生效
    HALF_OPEN = "HALF_OPEN"  # 半开状态：尝试恢复


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5          # 失败阈值
    recovery_timeout: float = 30.0      # 恢复超时 (秒)
    half_open_limit: int = 3            # 半开状态请求限制
    success_threshold: int = 2          # 恢复成功阈值
    failure_rate_threshold: float = 0.5 # 失败率阈值 (50%)
    minimum_requests: int = 10          # 最小请求数
    window_size: int = 60               # 时间窗口 (秒)


@dataclass
class OperationResult:
    """操作结果"""
    success: bool
    timestamp: float = field(default_factory=time.time)
    error: Optional[Exception] = None
    response_time: float = 0.0


class MarketPrismCircuitBreaker:
    """企业级熔断器系统"""
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        
        # 操作历史记录 (用于故障率计算)
        self.operation_history: deque = deque(maxlen=1000)
        
        # 缓存数据 (用于降级策略)
        self.cached_responses: Dict[str, Any] = {}
        self.cache_ttl: Dict[str, float] = {}
        
        # 统计指标
        self.total_requests = 0
        self.total_failures = 0
        self.total_fallbacks = 0
        
        # TDD改进：回调机制支持
        self._state_change_listeners: List[Callable] = []
        self._on_open_callbacks: List[Callable] = []
        self._on_close_callbacks: List[Callable] = []
        self._on_half_open_callbacks: List[Callable] = []
        
        logger.info(f"熔断器 '{name}' 已初始化，配置: {self.config}")
    
    async def execute_with_breaker(
        self, 
        operation: Callable, 
        fallback: Optional[Callable] = None,
        cache_key: Optional[str] = None,
        *args, 
        **kwargs
    ) -> Any:
        """带熔断保护的操作执行"""
        self.total_requests += 1
        
        # 检查熔断器状态
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                self.total_fallbacks += 1
                # TDD修复：OPEN状态应该拒绝请求，而不是执行操作
                return await self._execute_fallback(fallback, cache_key, CircuitBreakerOpenException(f"熔断器 '{self.name}' 处于开放状态"))
        
        # 半开状态下限制请求数
        if self.state == CircuitState.HALF_OPEN:
            if self.success_count >= self.config.half_open_limit:
                return await self._execute_fallback(fallback, cache_key, CircuitBreakerOpenException(f"熔断器 '{self.name}' 半开状态请求限制"))
        
        # 执行主要操作
        start_time = time.time()
        try:
            result = await operation(*args, **kwargs)
            response_time = time.time() - start_time
            
            # 记录成功
            await self._on_success(result, response_time, cache_key)
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            
            # 记录失败
            await self._on_failure(e, response_time)
            
            # 执行降级策略
            self.total_fallbacks += 1
            return await self._execute_fallback(fallback, cache_key, e)
    
    async def _on_success(self, result: Any, response_time: float, cache_key: Optional[str]):
        """处理成功结果"""
        operation_result = OperationResult(
            success=True,
            response_time=response_time
        )
        self.operation_history.append(operation_result)
        
        # 更新缓存
        if cache_key:
            self.cached_responses[cache_key] = result
            self.cache_ttl[cache_key] = time.time() + 300  # 5分钟TTL
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.info(f"熔断器 '{self.name}' 半开状态成功: {self.success_count}/{self.config.success_threshold}")
            
            # 达到成功阈值，恢复到关闭状态
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
        
        elif self.state == CircuitState.CLOSED:
            # 清零失败计数
            self.failure_count = 0
    
    async def _on_failure(self, error: Exception, response_time: float):
        """处理失败结果"""
        operation_result = OperationResult(
            success=False,
            response_time=response_time,
            error=error
        )
        self.operation_history.append(operation_result)
        
        self.failure_count += 1
        self.total_failures += 1
        self.last_failure_time = time.time()
        
        logger.warning(f"熔断器 '{self.name}' 操作失败: {error}, 失败计数: {self.failure_count}")
        
        # 检查是否需要开启熔断
        if self._should_trip():
            self._transition_to_open()
    
    def _should_trip(self) -> bool:
        """判断是否应该触发熔断"""
        # 检查失败次数阈值
        if self.failure_count >= self.config.failure_threshold:
            return True
        
        # 检查失败率阈值 (需要最小请求数)
        recent_operations = self._get_recent_operations()
        if len(recent_operations) >= self.config.minimum_requests:
            failure_rate = self._calculate_failure_rate(recent_operations)
            if failure_rate >= self.config.failure_rate_threshold:
                logger.warning(f"熔断器 '{self.name}' 失败率过高: {failure_rate:.2%}")
                return True
        
        return False
    
    def _should_attempt_reset(self) -> bool:
        """判断是否应该尝试重置"""
        if self.state != CircuitState.OPEN:
            return False
        
        time_since_open = time.time() - self.last_state_change
        return time_since_open >= self.config.recovery_timeout
    
    def _get_recent_operations(self) -> List[OperationResult]:
        """获取时间窗口内的操作记录"""
        current_time = time.time()
        cutoff_time = current_time - self.config.window_size
        
        return [
            op for op in self.operation_history 
            if op.timestamp >= cutoff_time
        ]
    
    def _calculate_failure_rate(self, operations: List[OperationResult]) -> float:
        """计算失败率"""
        if not operations:
            return 0.0
        
        failures = sum(1 for op in operations if not op.success)
        return failures / len(operations)
    
    async def _execute_fallback(
        self, 
        fallback: Optional[Callable],
        cache_key: Optional[str],
        error: Optional[Exception] = None
    ) -> Any:
        """执行降级策略"""
        logger.info(f"熔断器 '{self.name}' 执行降级策略")
        
        # 1. 优先执行自定义降级函数
        if fallback:
            try:
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                else:
                    return fallback()
            except Exception as e:
                logger.error(f"降级函数执行失败: {e}")
        
        # 2. 尝试返回缓存数据
        if cache_key and cache_key in self.cached_responses:
            if time.time() < self.cache_ttl.get(cache_key, 0):
                logger.info(f"返回缓存数据: {cache_key}")
                return self.cached_responses[cache_key]
        
        # TDD改进：如果没有fallback且有原始错误，重新抛出异常
        if error and not fallback:
            logger.warning(f"熔断器 '{self.name}' 无降级策略，重新抛出异常: {error}")
            raise error
        
        # 3. 返回默认响应
        return self._get_default_response(error)
    
    def _get_default_response(self, error: Optional[Exception] = None) -> Dict[str, Any]:
        """获取默认响应"""
        return {
            "status": "circuit_breaker_open",
            "message": f"熔断器 '{self.name}' 已开启，服务暂时不可用",
            "fallback": True,
            "timestamp": time.time(),
            "error": str(error) if error else None
        }
    
    def _transition_to_open(self):
        """转换到开放状态"""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.last_state_change = time.time()
        self.success_count = 0
        logger.warning(f"熔断器 '{self.name}' 转换到开放状态")
        
        # TDD改进：触发回调通知
        self._notify_state_change(old_state, CircuitState.OPEN)
        self._notify_open()
    
    def _transition_to_half_open(self):
        """转换到半开状态"""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.last_state_change = time.time()
        self.success_count = 0
        logger.info(f"熔断器 '{self.name}' 转换到半开状态")
        
        # TDD改进：触发回调通知
        self._notify_state_change(old_state, CircuitState.HALF_OPEN)
        self._notify_half_open()
    
    def _transition_to_closed(self):
        """转换到关闭状态"""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.last_state_change = time.time()
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"熔断器 '{self.name}' 转换到关闭状态")
        
        # TDD改进：触发回调通知
        self._notify_state_change(old_state, CircuitState.CLOSED)
        self._notify_close()
    
    def get_status(self) -> Dict[str, Any]:
        """获取熔断器状态"""
        recent_operations = self._get_recent_operations()
        failure_rate = self._calculate_failure_rate(recent_operations)
        
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_rate": failure_rate,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_fallbacks": self.total_fallbacks,
            "last_state_change": self.last_state_change,
            "recent_operations": len(recent_operations),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "failure_rate_threshold": self.config.failure_rate_threshold
            }
        }
    
    def reset(self):
        """重置熔断器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        self.operation_history.clear()
        logger.info(f"熔断器 '{self.name}' 已重置")

    async def call(
        self, 
        operation: Callable, 
        fallback: Optional[Callable] = None,
        cache_key: Optional[str] = None,
        *args, 
        **kwargs
    ) -> Any:
        """TDD改进：更直观的调用方法，是execute_with_breaker的别名"""
        return await self.execute_with_breaker(
            operation, fallback, cache_key, *args, **kwargs
        )

    def get_state(self) -> CircuitState:
        """TDD改进：获取当前熔断器状态"""
        return self.state
    
    def get_failure_count(self) -> int:
        """TDD改进：获取当前失败计数"""
        return self.failure_count
    
    def get_success_count(self) -> int:
        """TDD改进：获取当前成功计数"""
        return self.success_count
    
    def get_stats(self) -> Dict[str, Any]:
        """TDD改进：获取基础统计信息"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_fallbacks": self.total_fallbacks,
            "last_failure_time": self.last_failure_time,
            "last_state_change": self.last_state_change,
            "uptime_seconds": time.time() - self.last_state_change
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """TDD改进：获取详细监控指标"""
        recent_operations = [
            op for op in self.operation_history 
            if op.timestamp > time.time() - self.config.window_size
        ]
        
        failure_rate = self._calculate_failure_rate(recent_operations)
        avg_response_time = (
            sum(op.response_time for op in recent_operations) / len(recent_operations)
            if recent_operations else 0.0
        )
        
        return {
            **self.get_stats(),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "half_open_limit": self.config.half_open_limit,
                "success_threshold": self.config.success_threshold,
                "failure_rate_threshold": self.config.failure_rate_threshold,
                "minimum_requests": self.config.minimum_requests,
                "window_size": self.config.window_size
            },
            "performance": {
                "failure_rate": failure_rate,
                "avg_response_time": avg_response_time,
                "recent_operations_count": len(recent_operations),
                "cache_size": len(self.cached_responses)
            },
            "health": {
                "is_healthy": self.state == CircuitState.CLOSED,
                "time_since_last_failure": time.time() - self.last_failure_time if self.last_failure_time > 0 else None,
                "time_in_current_state": time.time() - self.last_state_change
            }
        }

    def __call__(self, func: Callable) -> Callable:
        """TDD改进：支持装饰器模式"""
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                return await self.call(func, *args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                # 对于同步函数，包装成异步调用
                async def async_func():
                    return func(*args, **kwargs)
                return asyncio.run(self.call(async_func))
            return sync_wrapper

    # TDD改进：回调机制支持
    def add_listener(self, callback: Callable[[CircuitState, CircuitState], None]):
        """添加状态变更监听器"""
        self._state_change_listeners.append(callback)
    
    def on_state_change(self, callback: Callable[[CircuitState, CircuitState], None]):
        """状态变更回调装饰器"""
        self.add_listener(callback)
        return callback
    
    def on_open(self, callback: Callable[[], None]):
        """熔断器开启回调"""
        self._on_open_callbacks.append(callback)
        return callback
    
    def on_close(self, callback: Callable[[], None]):
        """熔断器关闭回调"""
        self._on_close_callbacks.append(callback)
        return callback
    
    def on_half_open(self, callback: Callable[[], None]):
        """熔断器半开回调"""
        self._on_half_open_callbacks.append(callback)
        return callback
    
    def _notify_state_change(self, old_state: CircuitState, new_state: CircuitState):
        """通知状态变更"""
        for listener in self._state_change_listeners:
            try:
                listener(old_state, new_state)
            except Exception as e:
                logger.error(f"状态变更回调执行失败: {e}")
    
    def _notify_open(self):
        """通知熔断器开启"""
        for callback in self._on_open_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"开启回调执行失败: {e}")
    
    def _notify_close(self):
        """通知熔断器关闭"""
        for callback in self._on_close_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"关闭回调执行失败: {e}")
    
    def _notify_half_open(self):
        """通知熔断器半开"""
        for callback in self._on_half_open_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"半开回调执行失败: {e}")

    # TDD改进：上下文管理器支持
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        # 如果有异常，记录到熔断器统计中
        if exc_type is not None:
            # 模拟失败操作用于统计
            await self._on_failure(exc_val or Exception("Context manager exception"), 0.0)
        return False  # 不抑制异常


# 熔断器装饰器
def circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """熔断器装饰器"""
    breaker = MarketPrismCircuitBreaker(name, config)
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await breaker.execute_with_breaker(func, *args, **kwargs)
        return wrapper
    return decorator 