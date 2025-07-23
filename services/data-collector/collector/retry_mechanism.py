#!/usr/bin/env python3
"""
重试机制实现 - 提高系统容错性
"""

import asyncio
import random
import time
from typing import Callable, Any, Optional, List, Type
from dataclasses import dataclass
from enum import Enum
import structlog


class RetryStrategy(Enum):
    """重试策略"""
    FIXED = "fixed"                    # 固定间隔
    EXPONENTIAL = "exponential"        # 指数退避
    LINEAR = "linear"                  # 线性增长
    RANDOM = "random"                  # 随机间隔


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3                           # 最大重试次数
    base_delay: float = 1.0                        # 基础延迟时间（秒）
    max_delay: float = 60.0                        # 最大延迟时间（秒）
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL  # 重试策略
    backoff_multiplier: float = 2.0                # 退避乘数
    jitter: bool = True                            # 是否添加随机抖动
    retryable_exceptions: List[Type[Exception]] = None  # 可重试的异常类型


class RetryExhaustedException(Exception):
    """重试次数耗尽异常"""
    
    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(f"重试{attempts}次后仍然失败: {last_exception}")


class RetryMechanism:
    """重试机制实现"""
    
    def __init__(self, name: str, config: RetryConfig):
        self.name = name
        self.config = config
        self.logger = structlog.get_logger(__name__)
        
        # 设置默认可重试异常
        if self.config.retryable_exceptions is None:
            self.config.retryable_exceptions = [
                ConnectionError,
                TimeoutError,
                asyncio.TimeoutError,
                OSError
            ]
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行带重试的函数"""
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                self.logger.debug("执行重试", 
                                name=self.name, 
                                attempt=attempt, 
                                max_attempts=self.config.max_attempts)
                
                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # 成功执行
                if attempt > 1:
                    self.logger.info("重试成功", 
                                   name=self.name, 
                                   attempt=attempt)
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # 检查是否为可重试异常
                if not self._is_retryable_exception(e):
                    self.logger.error("遇到不可重试异常", 
                                    name=self.name, 
                                    attempt=attempt,
                                    error=str(e))
                    raise e
                
                # 如果是最后一次尝试，抛出异常
                if attempt == self.config.max_attempts:
                    self.logger.error("重试次数耗尽", 
                                    name=self.name, 
                                    attempts=attempt,
                                    error=str(e))
                    raise RetryExhaustedException(attempt, e)
                
                # 计算延迟时间
                delay = self._calculate_delay(attempt)
                
                self.logger.warning("执行失败，准备重试", 
                                  name=self.name, 
                                  attempt=attempt,
                                  delay=delay,
                                  error=str(e))
                
                # 等待后重试
                await asyncio.sleep(delay)
        
        # 理论上不会到达这里
        raise RetryExhaustedException(self.config.max_attempts, last_exception)
    
    def _is_retryable_exception(self, exception: Exception) -> bool:
        """检查异常是否可重试"""
        return any(isinstance(exception, exc_type) for exc_type in self.config.retryable_exceptions)
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        if self.config.strategy == RetryStrategy.FIXED:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (self.config.backoff_multiplier ** (attempt - 1))
        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.base_delay * attempt
        elif self.config.strategy == RetryStrategy.RANDOM:
            delay = random.uniform(self.config.base_delay, self.config.max_delay)
        else:
            delay = self.config.base_delay
        
        # 限制最大延迟
        delay = min(delay, self.config.max_delay)
        
        # 添加随机抖动
        if self.config.jitter:
            jitter_range = delay * 0.1  # 10%的抖动
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0, delay)  # 确保延迟不为负数
        
        return delay


def retry_on_failure(config: RetryConfig, name: Optional[str] = None):
    """重试装饰器"""
    def decorator(func: Callable) -> Callable:
        retry_name = name or f"{func.__module__}.{func.__name__}"
        retry_mechanism = RetryMechanism(retry_name, config)
        
        async def async_wrapper(*args, **kwargs):
            return await retry_mechanism.execute(func, *args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(retry_mechanism.execute(func, *args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 预定义的重试配置
WEBSOCKET_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    strategy=RetryStrategy.EXPONENTIAL,
    backoff_multiplier=2.0,
    jitter=True,
    retryable_exceptions=[ConnectionError, OSError, asyncio.TimeoutError]
)

NATS_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    base_delay=0.5,
    max_delay=10.0,
    strategy=RetryStrategy.EXPONENTIAL,
    backoff_multiplier=1.5,
    jitter=True,
    retryable_exceptions=[ConnectionError, TimeoutError, asyncio.TimeoutError]
)

API_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=2.0,
    max_delay=60.0,
    strategy=RetryStrategy.EXPONENTIAL,
    backoff_multiplier=2.0,
    jitter=True,
    retryable_exceptions=[ConnectionError, TimeoutError, OSError]
)

DATA_PROCESSING_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=0.1,
    max_delay=1.0,
    strategy=RetryStrategy.FIXED,
    jitter=False,
    retryable_exceptions=[ValueError, KeyError]
)


# 便捷装饰器
def websocket_retry(name: Optional[str] = None):
    """WebSocket重试装饰器"""
    return retry_on_failure(WEBSOCKET_RETRY_CONFIG, name)


def nats_retry(name: Optional[str] = None):
    """NATS重试装饰器"""
    return retry_on_failure(NATS_RETRY_CONFIG, name)


def api_retry(name: Optional[str] = None):
    """API重试装饰器"""
    return retry_on_failure(API_RETRY_CONFIG, name)


def data_processing_retry(name: Optional[str] = None):
    """数据处理重试装饰器"""
    return retry_on_failure(DATA_PROCESSING_RETRY_CONFIG, name)


class RetryManager:
    """重试管理器"""
    
    def __init__(self):
        self.retry_mechanisms: dict[str, RetryMechanism] = {}
        self.logger = structlog.get_logger(__name__)
    
    def create_retry_mechanism(self, name: str, config: RetryConfig) -> RetryMechanism:
        """创建重试机制"""
        mechanism = RetryMechanism(name, config)
        self.retry_mechanisms[name] = mechanism
        self.logger.info("创建重试机制", name=name)
        return mechanism
    
    def get_retry_mechanism(self, name: str) -> Optional[RetryMechanism]:
        """获取重试机制"""
        return self.retry_mechanisms.get(name)
    
    def get_all_mechanisms(self) -> dict[str, RetryMechanism]:
        """获取所有重试机制"""
        return self.retry_mechanisms.copy()


# 全局重试管理器
retry_manager = RetryManager()


# 使用示例
async def example_usage():
    """使用示例"""
    
    # 方式1: 使用装饰器
    @websocket_retry("binance_websocket")
    async def connect_websocket():
        # 模拟可能失败的WebSocket连接
        if random.random() < 0.7:  # 70%失败率
            raise ConnectionError("WebSocket连接失败")
        return "连接成功"
    
    # 方式2: 直接使用重试机制
    retry_mechanism = retry_manager.create_retry_mechanism(
        "custom_operation", 
        WEBSOCKET_RETRY_CONFIG
    )
    
    async def risky_operation():
        if random.random() < 0.5:
            raise ConnectionError("操作失败")
        return "操作成功"
    
    try:
        result1 = await connect_websocket()
        print(f"装饰器方式结果: {result1}")
        
        result2 = await retry_mechanism.execute(risky_operation)
        print(f"直接调用方式结果: {result2}")
        
    except RetryExhaustedException as e:
        print(f"重试耗尽: {e}")
    except Exception as e:
        print(f"其他异常: {e}")


if __name__ == "__main__":
    asyncio.run(example_usage())
