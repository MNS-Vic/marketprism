"""
企业级熔断器系统

实现三状态熔断机制：CLOSED -> OPEN -> HALF_OPEN
提供智能故障检测、优雅降级和自动恢复功能
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Any, Callable, Optional, Dict, List
from dataclasses import dataclass
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常状态，允许请求通过
    OPEN = "open"           # 熔断状态，拒绝请求
    HALF_OPEN = "half_open" # 半开状态，允许少量请求测试


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5          # 失败阈值
    recovery_timeout: float = 30.0      # 恢复超时时间(秒)
    half_open_max_calls: int = 3        # 半开状态最大调用次数
    success_threshold: int = 2          # 半开状态成功阈值
    timeout: float = 10.0               # 操作超时时间(秒)
    
    # 高级配置
    failure_rate_threshold: float = 0.5  # 失败率阈值 (50%)
    minimum_throughput: int = 10         # 最小吞吐量要求
    sliding_window_size: int = 100       # 滑动窗口大小
    slow_call_duration_threshold: float = 5.0  # 慢调用阈值(秒)


class CircuitBreakerException(Exception):
    """熔断器异常"""
    pass


class CircuitBreaker:
    """企业级熔断器"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # 状态管理
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        
        # 滑动窗口统计
        self.call_results = deque(maxlen=self.config.sliding_window_size)
        self.call_durations = deque(maxlen=self.config.sliding_window_size)
        
        # 监控指标
        self.metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "circuit_opened_count": 0,
            "fallback_calls": 0,
            "average_response_time": 0.0,
            "current_failure_rate": 0.0
        }
        
        # 锁保护
        self._lock = asyncio.Lock()
        
        logger.info(f"熔断器 '{name}' 初始化完成，配置: {self.config}")
    
    async def call(self, func: Callable, *args, fallback: Optional[Callable] = None, **kwargs) -> Any:
        """
        执行受熔断保护的调用
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            fallback: 降级函数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果或降级结果
            
        Raises:
            CircuitBreakerException: 熔断器开启时抛出
        """
        async with self._lock:
            self.metrics["total_calls"] += 1
            
            # 检查熔断器状态
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    return await self._execute_fallback(fallback, "熔断器开启")
            
            elif self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    return await self._execute_fallback(fallback, "半开状态调用次数超限")
        
        # 执行实际调用
        start_time = time.time()
        try:
            # 设置超时
            result = await asyncio.wait_for(
                func(*args, **kwargs), 
                timeout=self.config.timeout
            )
            
            # 记录成功
            duration = time.time() - start_time
            await self._record_success(duration)
            
            return result
            
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            await self._record_failure("timeout", duration)
            return await self._execute_fallback(fallback, f"调用超时 ({duration:.2f}s)")
            
        except Exception as e:
            duration = time.time() - start_time
            await self._record_failure(str(e), duration)
            return await self._execute_fallback(fallback, f"调用失败: {e}")
    
    async def _record_success(self, duration: float):
        """记录成功调用"""
        async with self._lock:
            self.call_results.append(True)
            self.call_durations.append(duration)
            self.metrics["successful_calls"] += 1
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self._transition_to_closed()
            
            self._update_metrics()
            
            logger.debug(f"熔断器 '{self.name}' 记录成功调用，耗时: {duration:.3f}s")
    
    async def _record_failure(self, error: str, duration: float):
        """记录失败调用"""
        async with self._lock:
            self.call_results.append(False)
            self.call_durations.append(duration)
            self.metrics["failed_calls"] += 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            # 检查是否需要开启熔断
            if self.state == CircuitState.CLOSED:
                if self._should_open_circuit():
                    self._transition_to_open()
            elif self.state == CircuitState.HALF_OPEN:
                self._transition_to_open()
            
            self._update_metrics()
            
            logger.warning(f"熔断器 '{self.name}' 记录失败调用: {error}, 耗时: {duration:.3f}s")
    
    def _should_open_circuit(self) -> bool:
        """判断是否应该开启熔断"""
        # 检查失败次数阈值
        if self.failure_count >= self.config.failure_threshold:
            return True
        
        # 检查失败率阈值（需要足够的样本）
        if len(self.call_results) >= self.config.minimum_throughput:
            failure_rate = self._calculate_failure_rate()
            if failure_rate >= self.config.failure_rate_threshold:
                return True
        
        # 检查慢调用比例
        if len(self.call_durations) >= self.config.minimum_throughput:
            slow_calls = sum(1 for d in self.call_durations 
                           if d >= self.config.slow_call_duration_threshold)
            slow_call_rate = slow_calls / len(self.call_durations)
            if slow_call_rate >= 0.5:  # 50%的调用都很慢
                return True
        
        return False
    
    def _should_attempt_reset(self) -> bool:
        """判断是否应该尝试重置熔断器"""
        return (time.time() - self.last_failure_time) >= self.config.recovery_timeout
    
    def _transition_to_open(self):
        """转换到开启状态"""
        self.state = CircuitState.OPEN
        self.metrics["circuit_opened_count"] += 1
        logger.warning(f"熔断器 '{self.name}' 开启，失败次数: {self.failure_count}")
    
    def _transition_to_half_open(self):
        """转换到半开状态"""
        self.state = CircuitState.HALF_OPEN
        self.half_open_calls = 0
        self.success_count = 0
        logger.info(f"熔断器 '{self.name}' 转换到半开状态")
    
    def _transition_to_closed(self):
        """转换到关闭状态"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0
        logger.info(f"熔断器 '{self.name}' 恢复到关闭状态")
    
    async def _execute_fallback(self, fallback: Optional[Callable], reason: str) -> Any:
        """执行降级逻辑"""
        self.metrics["fallback_calls"] += 1
        
        if fallback:
            try:
                logger.info(f"熔断器 '{self.name}' 执行降级逻辑: {reason}")
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                else:
                    return fallback()
            except Exception as e:
                logger.error(f"降级逻辑执行失败: {e}")
                raise CircuitBreakerException(f"降级逻辑失败: {e}")
        else:
            raise CircuitBreakerException(f"熔断器开启，无降级逻辑: {reason}")
    
    def _calculate_failure_rate(self) -> float:
        """计算失败率"""
        if not self.call_results:
            return 0.0
        
        failures = sum(1 for result in self.call_results if not result)
        return failures / len(self.call_results)
    
    def _update_metrics(self):
        """更新监控指标"""
        if self.call_durations:
            self.metrics["average_response_time"] = statistics.mean(self.call_durations)
        
        self.metrics["current_failure_rate"] = self._calculate_failure_rate()
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        return {
            **self.metrics,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "half_open_calls": self.half_open_calls,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "timeout": self.config.timeout
            }
        }
    
    def reset(self):
        """重置熔断器状态"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.half_open_calls = 0
            self.call_results.clear()
            self.call_durations.clear()
            
            # 重置指标
            self.metrics.update({
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "fallback_calls": 0,
                "average_response_time": 0.0,
                "current_failure_rate": 0.0
            })
            
            logger.info(f"熔断器 '{self.name}' 已重置")


# 装饰器支持
def circuit_breaker(name: str, config: CircuitBreakerConfig = None, fallback: Optional[Callable] = None):
    """熔断器装饰器"""
    breaker = CircuitBreaker(name, config)
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, fallback=fallback, **kwargs)
        return wrapper
    return decorator


# 使用示例
if __name__ == "__main__":
    async def example_usage():
        # 创建熔断器配置
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=10.0,
            timeout=5.0
        )
        
        # 创建熔断器
        breaker = CircuitBreaker("okx_api", config)
        
        # 模拟API调用
        async def api_call():
            # 模拟可能失败的API调用
            import random
            if random.random() < 0.3:  # 30%失败率
                raise Exception("API调用失败")
            return {"data": "success"}
        
        # 降级函数
        async def fallback():
            return {"data": "cached_data", "source": "fallback"}
        
        # 执行调用
        for i in range(10):
            try:
                result = await breaker.call(api_call, fallback=fallback)
                print(f"调用 {i+1}: {result}")
            except Exception as e:
                print(f"调用 {i+1} 失败: {e}")
            
            await asyncio.sleep(1)
        
        # 打印指标
        print("\n熔断器指标:")
        metrics = breaker.get_metrics()
        for key, value in metrics.items():
            print(f"  {key}: {value}")
    
    # 运行示例
    asyncio.run(example_usage()) 