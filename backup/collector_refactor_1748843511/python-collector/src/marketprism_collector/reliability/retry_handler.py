"""
MarketPrism 指数退避重试系统

设计目标：
- 智能故障恢复
- 最小化对交易所的影响
- 自适应重试策略
- 全面错误分类处理

特性：
- 指数退避算法
- 抖动 (Jitter) 防雷同
- 重试策略配置
- 失败分类处理
- 断路器集成
"""

import asyncio
import time
import random
import logging
from typing import Any, Callable, Optional, Dict, List, Type, Union
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
import traceback

logger = logging.getLogger(__name__)


class RetryErrorType(Enum):
    """重试错误类型"""
    CONNECTION_ERROR = "connection_error"      # 连接错误
    TIMEOUT_ERROR = "timeout_error"           # 超时错误
    RATE_LIMIT_ERROR = "rate_limit_error"     # 限流错误
    SERVER_ERROR = "server_error"             # 服务器错误
    AUTHENTICATION_ERROR = "auth_error"       # 认证错误
    VALIDATION_ERROR = "validation_error"     # 验证错误
    UNKNOWN_ERROR = "unknown_error"           # 未知错误


@dataclass
class RetryPolicy:
    """重试策略配置"""
    max_attempts: int = 5               # 最大重试次数
    base_delay: float = 1.0             # 基础延迟 (秒)
    max_delay: float = 60.0             # 最大延迟 (秒)
    multiplier: float = 2.0             # 延迟倍数
    jitter_range: float = 0.1           # 抖动范围 (±10%)
    backoff_strategy: str = "exponential"  # 退避策略: exponential, linear, fixed
    retryable_errors: List[RetryErrorType] = field(default_factory=lambda: [
        RetryErrorType.CONNECTION_ERROR,
        RetryErrorType.TIMEOUT_ERROR,
        RetryErrorType.RATE_LIMIT_ERROR,
        RetryErrorType.SERVER_ERROR
    ])
    non_retryable_errors: List[RetryErrorType] = field(default_factory=lambda: [
        RetryErrorType.AUTHENTICATION_ERROR,
        RetryErrorType.VALIDATION_ERROR
    ])


@dataclass
class RetryAttempt:
    """重试尝试记录"""
    attempt_number: int
    timestamp: float = field(default_factory=time.time)
    error_type: Optional[RetryErrorType] = None
    error_message: str = ""
    delay_before: float = 0.0
    response_time: float = 0.0
    success: bool = False


class RetryableException(Exception):
    """可重试异常基类"""
    def __init__(self, message: str, error_type: RetryErrorType, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error


class ExponentialBackoffRetry:
    """指数退避重试系统"""
    
    def __init__(self, name: str, default_policy: Optional[RetryPolicy] = None):
        self.name = name
        self.default_policy = default_policy or RetryPolicy()
        
        # 错误类型映射
        self.error_type_mapping: Dict[Type[Exception], RetryErrorType] = {
            ConnectionError: RetryErrorType.CONNECTION_ERROR,
            TimeoutError: RetryErrorType.TIMEOUT_ERROR,
            asyncio.TimeoutError: RetryErrorType.TIMEOUT_ERROR,
            OSError: RetryErrorType.CONNECTION_ERROR,
        }
        
        # 策略缓存
        self.policy_cache: Dict[str, RetryPolicy] = {}
        
        # 统计数据
        self.retry_stats = defaultdict(int)
        self.error_stats = defaultdict(int)
        self.attempt_history: List[RetryAttempt] = []
        
        logger.info(f"重试系统 '{name}' 已初始化，默认策略: {self.default_policy}")
    
    async def retry_with_backoff(
        self,
        operation: Callable,
        exchange_name: str,
        operation_type: str = "default",
        policy: Optional[RetryPolicy] = None,
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs
    ) -> Any:
        """带退避策略的重试执行"""
        retry_policy = policy or self._get_policy_for_operation(operation_type)
        attempt = 0
        delay = retry_policy.base_delay
        last_error = None
        
        while attempt < retry_policy.max_attempts:
            attempt += 1
            start_time = time.time()
            
            try:
                # 记录尝试开始
                logger.debug(f"重试系统 '{self.name}' 开始尝试 {attempt}/{retry_policy.max_attempts}: {operation_type}")
                
                # 执行操作
                result = await self._execute_operation(operation, *args, **kwargs)
                
                # 记录成功
                response_time = time.time() - start_time
                self._record_attempt(attempt, None, "", 0.0, response_time, True)
                self.retry_stats[f"{operation_type}_success"] += 1
                
                logger.info(f"重试系统 '{self.name}' 操作成功: {operation_type} (尝试 {attempt})")
                return result
                
            except Exception as e:
                response_time = time.time() - start_time
                error_type = self._classify_error(e)
                last_error = e
                
                # 记录失败尝试
                self._record_attempt(attempt, error_type, str(e), delay, response_time, False)
                self.error_stats[error_type.value] += 1
                
                logger.warning(f"重试系统 '{self.name}' 尝试失败 {attempt}/{retry_policy.max_attempts}: {e}")
                
                # 检查是否应该重试
                if not self._should_retry(error_type, attempt, retry_policy):
                    break
                
                # 最后一次尝试失败，不再等待
                if attempt >= retry_policy.max_attempts:
                    break
                
                # 计算延迟并等待
                actual_delay = self._calculate_delay(delay, retry_policy)
                logger.info(f"重试系统 '{self.name}' 等待 {actual_delay:.2f}s 后重试...")
                await asyncio.sleep(actual_delay)
                
                # 更新延迟
                delay = self._update_delay(delay, retry_policy)
        
        # 所有重试尝试都失败了
        self.retry_stats[f"{operation_type}_failed"] += 1
        await self._trigger_alert(exchange_name, operation_type, last_error, attempt)
        
        # 抛出最后的错误
        if isinstance(last_error, RetryableException):
            raise last_error
        else:
            raise RetryableException(
                f"重试 {retry_policy.max_attempts} 次后仍然失败: {last_error}",
                self._classify_error(last_error),
                last_error
            )
    
    async def _execute_operation(self, operation: Callable, *args, **kwargs) -> Any:
        """执行操作"""
        if asyncio.iscoroutinefunction(operation):
            return await operation(*args, **kwargs)
        else:
            return operation(*args, **kwargs)
    
    def _classify_error(self, error: Exception) -> RetryErrorType:
        """分类错误类型"""
        # 检查是否已经是分类的错误
        if isinstance(error, RetryableException):
            return error.error_type
        
        # 根据异常类型分类
        error_type = type(error)
        if error_type in self.error_type_mapping:
            return self.error_type_mapping[error_type]
        
        # 根据错误消息分类
        error_message = str(error).lower()
        
        if any(keyword in error_message for keyword in ['timeout', 'timed out']):
            return RetryErrorType.TIMEOUT_ERROR
        elif any(keyword in error_message for keyword in ['connection', 'network', 'unreachable']):
            return RetryErrorType.CONNECTION_ERROR
        elif any(keyword in error_message for keyword in ['rate limit', 'too many requests', '429']):
            return RetryErrorType.RATE_LIMIT_ERROR
        elif any(keyword in error_message for keyword in ['server error', '500', '502', '503', '504']):
            return RetryErrorType.SERVER_ERROR
        elif any(keyword in error_message for keyword in ['unauthorized', '401', 'forbidden', '403']):
            return RetryErrorType.AUTHENTICATION_ERROR
        elif any(keyword in error_message for keyword in ['invalid', 'validation', 'bad request', '400']):
            return RetryErrorType.VALIDATION_ERROR
        
        return RetryErrorType.UNKNOWN_ERROR
    
    def _should_retry(self, error_type: RetryErrorType, attempt: int, policy: RetryPolicy) -> bool:
        """判断是否应该重试"""
        # 检查是否达到最大尝试次数
        if attempt >= policy.max_attempts:
            return False
        
        # 检查错误类型是否可重试
        if error_type in policy.non_retryable_errors:
            logger.info(f"错误类型 {error_type.value} 不可重试")
            return False
        
        if error_type not in policy.retryable_errors:
            logger.info(f"错误类型 {error_type.value} 不在可重试列表中")
            return False
        
        return True
    
    def _calculate_delay(self, base_delay: float, policy: RetryPolicy) -> float:
        """计算延迟时间"""
        # 添加抖动
        jitter = random.uniform(-policy.jitter_range, policy.jitter_range)
        jittered_delay = base_delay * (1 + jitter)
        
        # 确保不超过最大延迟
        return min(jittered_delay, policy.max_delay)
    
    def _update_delay(self, current_delay: float, policy: RetryPolicy) -> float:
        """更新下次延迟"""
        if policy.backoff_strategy == "exponential":
            return min(current_delay * policy.multiplier, policy.max_delay)
        elif policy.backoff_strategy == "linear":
            return min(current_delay + policy.base_delay, policy.max_delay)
        elif policy.backoff_strategy == "fixed":
            return policy.base_delay
        else:
            # 默认使用指数退避
            return min(current_delay * policy.multiplier, policy.max_delay)
    
    def _record_attempt(
        self,
        attempt_number: int,
        error_type: Optional[RetryErrorType],
        error_message: str,
        delay_before: float,
        response_time: float,
        success: bool
    ):
        """记录重试尝试"""
        attempt = RetryAttempt(
            attempt_number=attempt_number,
            error_type=error_type,
            error_message=error_message,
            delay_before=delay_before,
            response_time=response_time,
            success=success
        )
        
        self.attempt_history.append(attempt)
        
        # 保持历史记录大小
        if len(self.attempt_history) > 10000:
            self.attempt_history = self.attempt_history[-5000:]
    
    async def _trigger_alert(
        self,
        exchange_name: str,
        operation_type: str,
        error: Exception,
        attempts: int
    ):
        """触发告警"""
        alert_message = f"""
        重试系统告警:
        - 系统: {self.name}
        - 交易所: {exchange_name}
        - 操作: {operation_type}
        - 错误: {error}
        - 重试次数: {attempts}
        - 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        logger.error(alert_message)
        
        # 这里可以集成真实的告警系统 (邮件、钉钉、Slack等)
        # await self.alert_manager.send_alert(alert_message)
    
    def _get_policy_for_operation(self, operation_type: str) -> RetryPolicy:
        """获取操作类型的重试策略"""
        if operation_type in self.policy_cache:
            return self.policy_cache[operation_type]
        
        # 根据操作类型返回定制策略
        if operation_type == "funding_rate_collection":
            policy = RetryPolicy(
                max_attempts=3,
                base_delay=5.0,
                max_delay=30.0,
                multiplier=2.0
            )
        elif operation_type == "trade_data_processing":
            policy = RetryPolicy(
                max_attempts=5,
                base_delay=1.0,
                max_delay=10.0,
                multiplier=1.5
            )
        elif operation_type == "health_check":
            policy = RetryPolicy(
                max_attempts=3,
                base_delay=2.0,
                max_delay=15.0,
                multiplier=2.0
            )
        else:
            policy = self.default_policy
        
        self.policy_cache[operation_type] = policy
        return policy
    
    def add_error_mapping(self, exception_type: Type[Exception], error_type: RetryErrorType):
        """添加错误类型映射"""
        self.error_type_mapping[exception_type] = error_type
        logger.info(f"重试系统 '{self.name}' 添加错误映射: {exception_type.__name__} -> {error_type.value}")
    
    def set_policy_for_operation(self, operation_type: str, policy: RetryPolicy):
        """设置操作类型的重试策略"""
        self.policy_cache[operation_type] = policy
        logger.info(f"重试系统 '{self.name}' 设置策略: {operation_type}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取重试系统状态"""
        recent_attempts = self.attempt_history[-100:] if self.attempt_history else []
        success_rate = 0.0
        
        if recent_attempts:
            successful = sum(1 for attempt in recent_attempts if attempt.success)
            success_rate = successful / len(recent_attempts)
        
        return {
            "name": self.name,
            "total_attempts": len(self.attempt_history),
            "recent_success_rate": success_rate,
            "retry_stats": dict(self.retry_stats),
            "error_stats": dict(self.error_stats),
            "error_mappings": {
                exc.__name__: error_type.value 
                for exc, error_type in self.error_type_mapping.items()
            },
            "cached_policies": list(self.policy_cache.keys()),
            "default_policy": {
                "max_attempts": self.default_policy.max_attempts,
                "base_delay": self.default_policy.base_delay,
                "max_delay": self.default_policy.max_delay,
                "multiplier": self.default_policy.multiplier
            }
        }
    
    def reset_stats(self):
        """重置统计数据"""
        self.retry_stats.clear()
        self.error_stats.clear()
        self.attempt_history.clear()
        logger.info(f"重试系统 '{self.name}' 统计数据已重置")


# 重试装饰器
def retry_on_failure(
    name: str = "default",
    policy: Optional[RetryPolicy] = None,
    operation_type: str = "default"
):
    """重试装饰器"""
    retry_handler = ExponentialBackoffRetry(name, policy)
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await retry_handler.retry_with_backoff(
                func, 
                exchange_name="unknown",
                operation_type=operation_type,
                *args, 
                **kwargs
            )
        return wrapper
    return decorator


# 重试管理器
class RetryManager:
    """重试管理器"""
    
    def __init__(self):
        self.handlers: Dict[str, ExponentialBackoffRetry] = {}
        
        # 预定义重试策略
        self.predefined_policies = {
            "connection_retry": RetryPolicy(
                max_attempts=5,
                base_delay=2.0,
                max_delay=60.0,
                multiplier=2.0,
                retryable_errors=[
                    RetryErrorType.CONNECTION_ERROR,
                    RetryErrorType.TIMEOUT_ERROR
                ]
            ),
            "rate_limit_retry": RetryPolicy(
                max_attempts=3,
                base_delay=5.0,
                max_delay=30.0,
                multiplier=2.0,
                retryable_errors=[
                    RetryErrorType.RATE_LIMIT_ERROR
                ]
            ),
            "server_error_retry": RetryPolicy(
                max_attempts=4,
                base_delay=1.0,
                max_delay=20.0,
                multiplier=2.0,
                retryable_errors=[
                    RetryErrorType.SERVER_ERROR
                ]
            )
        }
    
    def get_handler(self, name: str, policy: Optional[RetryPolicy] = None) -> ExponentialBackoffRetry:
        """获取或创建重试处理器"""
        if name not in self.handlers:
            self.handlers[name] = ExponentialBackoffRetry(name, policy)
        return self.handlers[name]
    
    def get_policy(self, policy_name: str) -> Optional[RetryPolicy]:
        """获取预定义策略"""
        return self.predefined_policies.get(policy_name)
    
    async def retry_operation(
        self,
        operation: Callable,
        handler_name: str = "default",
        exchange_name: str = "unknown",
        operation_type: str = "default",
        policy_name: Optional[str] = None,
        *args,
        **kwargs
    ) -> Any:
        """便捷方法：执行重试操作"""
        handler = self.get_handler(handler_name)
        policy = self.get_policy(policy_name) if policy_name else None
        
        return await handler.retry_with_backoff(
            operation,
            exchange_name,
            operation_type,
            policy,
            None,
            *args,
            **kwargs
        )
    
    def get_all_status(self) -> Dict[str, Any]:
        """获取所有重试处理器状态"""
        return {
            name: handler.get_status()
            for name, handler in self.handlers.items()
        }


# 全局重试管理器实例
retry_manager = RetryManager() 