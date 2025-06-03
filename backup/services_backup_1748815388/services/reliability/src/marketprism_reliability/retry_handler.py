"""
企业级智能重试处理器

实现多种重试策略、自适应算法和错误分类
提供完整的重试监控和故障统计功能
"""

import asyncio
import time
import logging
import random
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """重试策略"""
    EXPONENTIAL_BACKOFF = "exponential_backoff"     # 指数退避
    LINEAR_BACKOFF = "linear_backoff"               # 线性退避
    FIXED_DELAY = "fixed_delay"                     # 固定延迟
    FIBONACCI = "fibonacci"                         # 斐波那契
    ADAPTIVE = "adaptive"                           # 自适应


class ErrorCategory(Enum):
    """错误分类"""
    RETRYABLE = "retryable"           # 可重试错误
    NON_RETRYABLE = "non_retryable"   # 不可重试错误
    RATE_LIMITED = "rate_limited"     # 限流错误
    TIMEOUT = "timeout"               # 超时错误
    NETWORK = "network"               # 网络错误
    SERVER_ERROR = "server_error"     # 服务器错误


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3                           # 最大重试次数
    base_delay: float = 1.0                         # 基础延迟(秒)
    max_delay: float = 60.0                         # 最大延迟(秒)
    multiplier: float = 2.0                         # 指数退避倍数
    jitter: bool = True                             # 启用抖动
    strategy: RetryStrategy = RetryStrategy.ADAPTIVE
    
    # 自适应配置
    success_threshold: float = 0.8                  # 成功率阈值
    failure_threshold: float = 0.5                  # 失败率阈值
    adaptive_window: int = 100                      # 自适应窗口大小
    
    # 错误分类配置
    retryable_exceptions: List[str] = None          # 可重试异常类型
    non_retryable_exceptions: List[str] = None      # 不可重试异常类型


class RetryException(Exception):
    """重试异常"""
    pass


class RetryHandler:
    """企业级智能重试处理器"""
    
    def __init__(self, name: str, config: RetryConfig = None):
        self.name = name
        self.config = config or RetryConfig()
        
        # 初始化默认异常类型
        if self.config.retryable_exceptions is None:
            self.config.retryable_exceptions = [
                "ConnectionError", "TimeoutError", "HTTPError",
                "ServiceUnavailable", "TemporaryFailure"
            ]
        
        if self.config.non_retryable_exceptions is None:
            self.config.non_retryable_exceptions = [
                "AuthenticationError", "AuthorizationError", 
                "ValidationError", "BadRequest", "NotFound",
                "ValueError", "TypeError", "AttributeError"
            ]
        
        # 自适应参数
        self.adaptive_multiplier = 1.0
        self.last_adjustment = time.time()
        
        # 统计数据
        self.recent_results = deque(maxlen=self.config.adaptive_window)
        self.fibonacci_cache = [1, 1]  # 斐波那契缓存
        
        # 监控指标
        self.metrics = {
            "total_attempts": 0,
            "successful_attempts": 0,
            "failed_attempts": 0,
            "retries_performed": 0,
            "average_attempts_per_operation": 0.0,
            "success_rate": 0.0,
            "average_delay": 0.0,
            "total_delay_time": 0.0
        }
        
        # 错误统计
        self.error_stats = {}
        self.operation_history = deque(maxlen=1000)
        
        logger.info(f"重试处理器 '{name}' 初始化完成，配置: {self.config}")
    
    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        带重试的执行函数
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            RetryException: 重试次数耗尽后的异常
        """
        operation_id = f"{self.name}_{int(time.time() * 1000)}"
        start_time = time.time()
        last_exception = None
        
        for attempt in range(self.config.max_attempts):
            attempt_start = time.time()
            
            try:
                # 记录尝试
                self.metrics["total_attempts"] += 1
                
                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # 记录成功
                await self._record_success(operation_id, attempt + 1, 
                                         time.time() - start_time)
                return result
                
            except Exception as e:
                last_exception = e
                error_category = self._classify_error(e)
                
                # 记录错误
                await self._record_error(e, error_category, attempt + 1)
                
                # 检查是否应该重试
                if not self._should_retry(e, attempt + 1):
                    await self._record_failure(operation_id, attempt + 1, 
                                             time.time() - start_time, e)
                    # 对于不可重试错误，直接抛出原始异常
                    if error_category == ErrorCategory.NON_RETRYABLE:
                        raise e
                    else:
                        raise RetryException(f"达到最大重试次数 {self.config.max_attempts}, "
                                           f"最后异常: {e}") from e
                
                # 如果不是最后一次尝试，计算延迟并等待
                if attempt < self.config.max_attempts - 1:
                    delay = await self._calculate_delay(attempt + 1, error_category)
                    
                    logger.warning(f"重试处理器 '{self.name}' 第{attempt + 1}次尝试失败: {e}, "
                                 f"{delay:.2f}秒后重试")
                    
                    await asyncio.sleep(delay)
                    self.metrics["total_delay_time"] += delay
        
        # 所有重试都失败了
        await self._record_failure(operation_id, self.config.max_attempts, 
                                 time.time() - start_time, last_exception)
        raise RetryException(f"达到最大重试次数 {self.config.max_attempts}, "
                           f"最后异常: {last_exception}") from last_exception
    
    def _classify_error(self, error: Exception) -> ErrorCategory:
        """分类错误类型"""
        error_name = type(error).__name__
        error_message = str(error).lower()
        
        # 检查是否为明确的不可重试错误
        if error_name in self.config.non_retryable_exceptions:
            return ErrorCategory.NON_RETRYABLE
        
        # 检查是否为明确的可重试错误
        if error_name in self.config.retryable_exceptions:
            return ErrorCategory.RETRYABLE
        
        # 基于错误消息进行启发式分类
        if any(keyword in error_message for keyword in 
               ["rate limit", "too many requests", "quota exceeded"]):
            return ErrorCategory.RATE_LIMITED
        
        if any(keyword in error_message for keyword in 
               ["timeout", "timed out", "deadline exceeded"]):
            return ErrorCategory.TIMEOUT
        
        if any(keyword in error_message for keyword in 
               ["connection", "network", "unreachable", "dns"]):
            return ErrorCategory.NETWORK
        
        if any(keyword in error_message for keyword in 
               ["500", "502", "503", "504", "internal server error"]):
            return ErrorCategory.SERVER_ERROR
        
        # 默认为可重试
        return ErrorCategory.RETRYABLE
    
    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.config.max_attempts:
            return False
        
        error_category = self._classify_error(error)
        
        # 不可重试的错误
        if error_category == ErrorCategory.NON_RETRYABLE:
            return False
        
        return True
    
    async def _calculate_delay(self, attempt: int, error_category: ErrorCategory) -> float:
        """计算重试延迟"""
        base_delay = self.config.base_delay
        
        # 根据错误类型调整基础延迟
        if error_category == ErrorCategory.RATE_LIMITED:
            base_delay *= 2.0  # 限流错误使用更长延迟
        elif error_category == ErrorCategory.TIMEOUT:
            base_delay *= 1.5  # 超时错误稍微增加延迟
        
        # 应用自适应调整
        await self._adaptive_adjustment()
        base_delay *= self.adaptive_multiplier
        
        # 根据策略计算延迟
        if self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = base_delay * (self.config.multiplier ** (attempt - 1))
        
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = base_delay * attempt
        
        elif self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = base_delay
        
        elif self.config.strategy == RetryStrategy.FIBONACCI:
            fib_value = self._get_fibonacci(attempt)
            delay = base_delay * fib_value
        
        elif self.config.strategy == RetryStrategy.ADAPTIVE:
            # 自适应策略：基于最近的成功率调整
            success_rate = self._calculate_recent_success_rate()
            if success_rate > self.config.success_threshold:
                delay = base_delay * (self.config.multiplier ** max(0, attempt - 2))
            else:
                delay = base_delay * (self.config.multiplier ** attempt)
        
        else:
            delay = base_delay * (self.config.multiplier ** (attempt - 1))
        
        # 限制最大延迟
        delay = min(delay, self.config.max_delay)
        
        # 添加抖动
        if self.config.jitter:
            jitter_range = delay * 0.1  # 10%的抖动
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.1, delay)  # 确保至少有0.1秒延迟
    
    def _get_fibonacci(self, n: int) -> int:
        """获取斐波那契数列的第n项"""
        while len(self.fibonacci_cache) <= n:
            next_fib = self.fibonacci_cache[-1] + self.fibonacci_cache[-2]
            self.fibonacci_cache.append(next_fib)
        
        return self.fibonacci_cache[n] if n < len(self.fibonacci_cache) else self.fibonacci_cache[-1]
    
    def _calculate_recent_success_rate(self) -> float:
        """计算最近的成功率"""
        if not self.recent_results:
            return 0.5  # 默认成功率
        
        return sum(self.recent_results) / len(self.recent_results)
    
    async def _adaptive_adjustment(self):
        """自适应调整"""
        if self.config.strategy != RetryStrategy.ADAPTIVE:
            return
        
        now = time.time()
        if now - self.last_adjustment < 10.0:  # 每10秒调整一次
            return
        
        success_rate = self._calculate_recent_success_rate()
        
        # 根据成功率调整倍数
        if success_rate > self.config.success_threshold:
            # 成功率高，减少延迟
            self.adaptive_multiplier *= 0.9
        elif success_rate < self.config.failure_threshold:
            # 成功率低，增加延迟
            self.adaptive_multiplier *= 1.1
        
        # 限制调整范围
        self.adaptive_multiplier = max(0.1, min(5.0, self.adaptive_multiplier))
        self.last_adjustment = now
        
        logger.debug(f"重试处理器 '{self.name}' 自适应调整: "
                    f"成功率={success_rate:.2f}, 延迟倍数={self.adaptive_multiplier:.2f}")
    
    async def _record_success(self, operation_id: str, attempts: int, duration: float):
        """记录成功操作"""
        self.metrics["successful_attempts"] += 1
        self.metrics["retries_performed"] += attempts - 1
        self.recent_results.append(1)  # 成功
        
        # 更新平均指标
        total_ops = self.metrics["successful_attempts"] + self.metrics["failed_attempts"]
        if total_ops > 0:
            self.metrics["success_rate"] = self.metrics["successful_attempts"] / total_ops
            
            total_attempts = self.metrics["total_attempts"]
            self.metrics["average_attempts_per_operation"] = total_attempts / total_ops
        
        # 记录操作历史
        self.operation_history.append({
            "operation_id": operation_id,
            "success": True,
            "attempts": attempts,
            "duration": duration,
            "timestamp": time.time()
        })
        
        logger.debug(f"重试处理器 '{self.name}' 操作成功: {operation_id}, "
                    f"尝试次数={attempts}, 耗时={duration:.2f}s")
    
    async def _record_failure(self, operation_id: str, attempts: int, 
                            duration: float, error: Exception):
        """记录失败操作"""
        self.metrics["failed_attempts"] += 1
        self.metrics["retries_performed"] += attempts - 1
        self.recent_results.append(0)  # 失败
        
        # 更新平均指标
        total_ops = self.metrics["successful_attempts"] + self.metrics["failed_attempts"]
        if total_ops > 0:
            self.metrics["success_rate"] = self.metrics["successful_attempts"] / total_ops
            
            total_attempts = self.metrics["total_attempts"]
            self.metrics["average_attempts_per_operation"] = total_attempts / total_ops
        
        # 记录操作历史
        self.operation_history.append({
            "operation_id": operation_id,
            "success": False,
            "attempts": attempts,
            "duration": duration,
            "error": str(error),
            "timestamp": time.time()
        })
        
        logger.error(f"重试处理器 '{self.name}' 操作失败: {operation_id}, "
                    f"尝试次数={attempts}, 耗时={duration:.2f}s, 错误={error}")
    
    async def _record_error(self, error: Exception, category: ErrorCategory, attempt: int):
        """记录错误统计"""
        error_type = type(error).__name__
        
        if error_type not in self.error_stats:
            self.error_stats[error_type] = {
                "count": 0,
                "category": category.value,
                "first_seen": time.time(),
                "last_seen": time.time()
            }
        
        self.error_stats[error_type]["count"] += 1
        self.error_stats[error_type]["last_seen"] = time.time()
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        return {
            **self.metrics,
            "config": {
                "max_attempts": self.config.max_attempts,
                "base_delay": self.config.base_delay,
                "max_delay": self.config.max_delay,
                "strategy": self.config.strategy.value if hasattr(self.config.strategy, 'value') else str(self.config.strategy),
                "adaptive_multiplier": self.adaptive_multiplier
            },
            "recent_success_rate": self._calculate_recent_success_rate(),
            "error_distribution": self.error_stats,
            "average_delay": (
                self.metrics["total_delay_time"] / self.metrics["retries_performed"]
                if self.metrics["retries_performed"] > 0 else 0.0
            )
        }
    
    def get_operation_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取操作历史"""
        return list(self.operation_history)[-limit:]
    
    def reset(self):
        """重置统计数据"""
        self.metrics = {
            "total_attempts": 0,
            "successful_attempts": 0,
            "failed_attempts": 0,
            "retries_performed": 0,
            "average_attempts_per_operation": 0.0,
            "success_rate": 0.0,
            "average_delay": 0.0,
            "total_delay_time": 0.0
        }
        
        self.error_stats.clear()
        self.recent_results.clear()
        self.operation_history.clear()
        self.adaptive_multiplier = 1.0
        
        logger.info(f"重试处理器 '{self.name}' 已重置")


# 装饰器支持
def retry(name: str = None, config: RetryConfig = None):
    """重试装饰器"""
    def decorator(func):
        handler_name = name or f"retry_{func.__name__}"
        retry_handler = RetryHandler(handler_name, config)
        
        async def async_wrapper(*args, **kwargs):
            return await retry_handler.execute_with_retry(func, *args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 使用示例
if __name__ == "__main__":
    async def example_usage():
        # 创建重试配置
        config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            jitter=True
        )
        
        # 创建重试处理器
        retry_handler = RetryHandler("api_retry", config)
        
        # 模拟可能失败的函数
        call_count = 0
        async def unreliable_api_call():
            nonlocal call_count
            call_count += 1
            
            if call_count < 2:  # 前两次调用失败
                raise ConnectionError(f"连接失败 (第{call_count}次调用)")
            
            return {"status": "success", "data": "API响应数据"}
        
        try:
            # 使用重试处理器执行函数
            result = await retry_handler.execute_with_retry(unreliable_api_call)
            print(f"API调用成功: {result}")
            
            # 打印指标
            print("\n重试处理器指标:")
            metrics = retry_handler.get_metrics()
            for key, value in metrics.items():
                print(f"  {key}: {value}")
            
        except RetryException as e:
            print(f"重试失败: {e}")
    
    # 运行示例
    asyncio.run(example_usage())