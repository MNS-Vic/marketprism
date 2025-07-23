#!/usr/bin/env python3
"""
断路器模式实现 - 防止级联失败
"""

import time
import asyncio
from typing import Callable, Any, Optional, Dict
from enum import Enum
from dataclasses import dataclass
import structlog


class CircuitState(Enum):
    """断路器状态"""
    CLOSED = "closed"      # 正常状态，允许请求通过
    OPEN = "open"          # 断路状态，拒绝请求
    HALF_OPEN = "half_open"  # 半开状态，允许少量请求测试


@dataclass
class CircuitBreakerConfig:
    """断路器配置"""
    failure_threshold: int = 5          # 失败阈值
    recovery_timeout: float = 60.0      # 恢复超时时间（秒）
    expected_exception: type = Exception # 预期的异常类型
    success_threshold: int = 3          # 半开状态下成功阈值
    timeout: float = 30.0               # 操作超时时间


class CircuitBreakerOpenException(Exception):
    """断路器开启异常"""
    pass


class CircuitBreaker:
    """断路器实现"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.logger = structlog.get_logger(__name__)
        
    def __call__(self, func: Callable) -> Callable:
        """装饰器模式"""
        async def wrapper(*args, **kwargs):
            return await self.call(func, *args, **kwargs)
        return wrapper
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """执行被保护的函数"""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                self.logger.info("断路器进入半开状态", name=self.name)
            else:
                raise CircuitBreakerOpenException(f"断路器 {self.name} 处于开启状态")
        
        try:
            # 设置超时
            result = await asyncio.wait_for(
                self._execute_function(func, *args, **kwargs),
                timeout=self.config.timeout
            )
            
            # 成功执行
            await self._on_success()
            return result
            
        except asyncio.TimeoutError as e:
            await self._on_failure(e)
            raise
        except self.config.expected_exception as e:
            await self._on_failure(e)
            raise
        except Exception as e:
            # 非预期异常，不触发断路器
            self.logger.warning("断路器遇到非预期异常", name=self.name, error=str(e))
            raise
    
    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """执行函数"""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    
    async def _on_success(self):
        """成功处理"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.logger.info("断路器恢复到关闭状态", name=self.name)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    async def _on_failure(self, exception: Exception):
        """失败处理"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        self.logger.warning("断路器记录失败", 
                          name=self.name, 
                          failure_count=self.failure_count,
                          error=str(exception))
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.logger.error("断路器从半开状态转为开启状态", name=self.name)
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self.logger.error("断路器开启", 
                            name=self.name, 
                            failure_count=self.failure_count,
                            threshold=self.config.failure_threshold)
    
    def _should_attempt_reset(self) -> bool:
        """是否应该尝试重置"""
        return (time.time() - self.last_failure_time) >= self.config.recovery_timeout
    
    def get_state(self) -> Dict[str, Any]:
        """获取断路器状态"""
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_time': self.last_failure_time,
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'recovery_timeout': self.config.recovery_timeout,
                'success_threshold': self.config.success_threshold,
                'timeout': self.config.timeout
            }
        }
    
    def reset(self):
        """手动重置断路器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.logger.info("断路器手动重置", name=self.name)


class CircuitBreakerManager:
    """断路器管理器"""
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.logger = structlog.get_logger(__name__)
    
    def create_breaker(self, name: str, config: CircuitBreakerConfig) -> CircuitBreaker:
        """创建断路器"""
        if name in self.breakers:
            self.logger.warning("断路器已存在，将被替换", name=name)
        
        breaker = CircuitBreaker(name, config)
        self.breakers[name] = breaker
        self.logger.info("创建断路器", name=name)
        return breaker
    
    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """获取断路器"""
        return self.breakers.get(name)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有断路器状态"""
        return {name: breaker.get_state() for name, breaker in self.breakers.items()}
    
    def reset_all(self):
        """重置所有断路器"""
        for breaker in self.breakers.values():
            breaker.reset()
        self.logger.info("重置所有断路器")
    
    def get_open_breakers(self) -> List[str]:
        """获取开启状态的断路器"""
        return [
            name for name, breaker in self.breakers.items()
            if breaker.state == CircuitState.OPEN
        ]


# 全局断路器管理器
circuit_breaker_manager = CircuitBreakerManager()


def create_websocket_breaker(exchange: str) -> CircuitBreaker:
    """为WebSocket连接创建断路器"""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=30.0,
        expected_exception=ConnectionError,
        success_threshold=2,
        timeout=10.0
    )
    return circuit_breaker_manager.create_breaker(f"websocket_{exchange}", config)


def create_nats_breaker() -> CircuitBreaker:
    """为NATS发布创建断路器"""
    config = CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=60.0,
        expected_exception=Exception,
        success_threshold=3,
        timeout=5.0
    )
    return circuit_breaker_manager.create_breaker("nats_publisher", config)


def create_api_breaker(exchange: str) -> CircuitBreaker:
    """为API请求创建断路器"""
    config = CircuitBreakerConfig(
        failure_threshold=10,
        recovery_timeout=120.0,
        expected_exception=Exception,
        success_threshold=5,
        timeout=30.0
    )
    return circuit_breaker_manager.create_breaker(f"api_{exchange}", config)


# 使用示例装饰器
def websocket_circuit_breaker(exchange: str):
    """WebSocket断路器装饰器"""
    def decorator(func):
        breaker = create_websocket_breaker(exchange)
        return breaker(func)
    return decorator


def nats_circuit_breaker(func):
    """NATS断路器装饰器"""
    breaker = create_nats_breaker()
    return breaker(func)


def api_circuit_breaker(exchange: str):
    """API断路器装饰器"""
    def decorator(func):
        breaker = create_api_breaker(exchange)
        return breaker(func)
    return decorator
