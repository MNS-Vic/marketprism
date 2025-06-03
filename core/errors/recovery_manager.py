"""
错误恢复管理器

实现智能错误恢复机制，包括重试、熔断器、故障转移等策略。
支持自定义恢复动作和自适应恢复策略。
"""

import time
import asyncio
import logging
import threading
from typing import Dict, Any, Optional, List, Callable, Union
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from .error_categories import ErrorType, RecoveryStrategy
from .exceptions import MarketPrismError


class RecoveryStatus(Enum):
    """恢复状态枚举"""
    NOT_ATTEMPTED = "not_attempted"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RecoveryResult:
    """恢复结果"""
    status: RecoveryStatus
    strategy: RecoveryStrategy
    attempts: int
    total_duration: float
    success: bool
    error_message: Optional[str] = None
    recovery_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "status": self.status.value,
            "strategy": self.strategy.value,
            "attempts": self.attempts,
            "total_duration": self.total_duration,
            "success": self.success,
            "error_message": self.error_message,
            "recovery_data": self.recovery_data,
            "timestamp": self.timestamp.isoformat()
        }


class RecoveryAction(ABC):
    """恢复动作抽象基类"""
    
    @abstractmethod
    def execute(self, error: MarketPrismError, context: Dict[str, Any] = None) -> RecoveryResult:
        """执行恢复动作"""
        pass
    
    @abstractmethod
    def can_handle(self, error: MarketPrismError) -> bool:
        """判断是否能处理该错误"""
        pass


class RetryAction(RecoveryAction):
    """重试恢复动作"""
    
    def __init__(self, 
                 max_attempts: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_backoff: bool = True,
                 jitter: bool = True):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff
        self.jitter = jitter
        self.logger = logging.getLogger(__name__)
    
    def can_handle(self, error: MarketPrismError) -> bool:
        """判断是否能处理该错误"""
        retryable_strategies = {
            RecoveryStrategy.RETRY,
            RecoveryStrategy.EXPONENTIAL_BACKOFF
        }
        return error.recovery_strategy in retryable_strategies
    
    def execute(self, error: MarketPrismError, context: Dict[str, Any] = None) -> RecoveryResult:
        """执行重试恢复"""
        start_time = time.time()
        context = context or {}
        retry_function = context.get('retry_function')
        
        if not retry_function:
            return RecoveryResult(
                status=RecoveryStatus.SKIPPED,
                strategy=RecoveryStrategy.RETRY,
                attempts=0,
                total_duration=0.0,
                success=False,
                error_message="没有提供重试函数"
            )
        
        attempts = 0
        last_error = None
        
        for attempt in range(self.max_attempts):
            attempts += 1
            
            try:
                # 执行重试函数
                result = retry_function()
                
                # 成功恢复
                total_duration = time.time() - start_time
                return RecoveryResult(
                    status=RecoveryStatus.SUCCESS,
                    strategy=RecoveryStrategy.RETRY,
                    attempts=attempts,
                    total_duration=total_duration,
                    success=True,
                    recovery_data={"retry_result": result}
                )
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"重试第{attempt + 1}次失败: {e}")
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < self.max_attempts - 1:
                    delay = self._calculate_delay(attempt)
                    time.sleep(delay)
        
        # 所有重试都失败
        total_duration = time.time() - start_time
        return RecoveryResult(
            status=RecoveryStatus.FAILED,
            strategy=RecoveryStrategy.RETRY,
            attempts=attempts,
            total_duration=total_duration,
            success=False,
            error_message=str(last_error) if last_error else "重试失败"
        )
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        if self.exponential_backoff:
            delay = self.base_delay * (2 ** attempt)
        else:
            delay = self.base_delay
        
        # 限制最大延迟
        delay = min(delay, self.max_delay)
        
        # 添加抖动
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random() * 0.5)
        
        return delay


class CircuitBreakerAction(RecoveryAction):
    """熔断器恢复动作"""
    
    def __init__(self,
                 failure_threshold: int = 5,
                 recovery_timeout: int = 60,
                 success_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.logger = logging.getLogger(__name__)
        
        # 熔断器状态
        self._failure_count = 0
        self._last_failure_time = None
        self._success_count = 0
        self._is_open = False
        self._lock = threading.Lock()
    
    def can_handle(self, error: MarketPrismError) -> bool:
        """判断是否能处理该错误"""
        return error.recovery_strategy == RecoveryStrategy.CIRCUIT_BREAKER
    
    def execute(self, error: MarketPrismError, context: Dict[str, Any] = None) -> RecoveryResult:
        """执行熔断器恢复"""
        start_time = time.time()
        context = context or {}
        
        with self._lock:
            # 检查熔断器状态
            if self._is_circuit_open():
                return RecoveryResult(
                    status=RecoveryStatus.SKIPPED,
                    strategy=RecoveryStrategy.CIRCUIT_BREAKER,
                    attempts=0,
                    total_duration=time.time() - start_time,
                    success=False,
                    error_message="熔断器开启，跳过执行"
                )
            
            # 尝试执行
            try:
                action_function = context.get('action_function')
                if not action_function:
                    return RecoveryResult(
                        status=RecoveryStatus.SKIPPED,
                        strategy=RecoveryStrategy.CIRCUIT_BREAKER,
                        attempts=0,
                        total_duration=time.time() - start_time,
                        success=False,
                        error_message="没有提供执行函数"
                    )
                
                result = action_function()
                self._record_success()
                
                return RecoveryResult(
                    status=RecoveryStatus.SUCCESS,
                    strategy=RecoveryStrategy.CIRCUIT_BREAKER,
                    attempts=1,
                    total_duration=time.time() - start_time,
                    success=True,
                    recovery_data={"circuit_breaker_result": result}
                )
                
            except Exception as e:
                self._record_failure()
                
                return RecoveryResult(
                    status=RecoveryStatus.FAILED,
                    strategy=RecoveryStrategy.CIRCUIT_BREAKER,
                    attempts=1,
                    total_duration=time.time() - start_time,
                    success=False,
                    error_message=str(e)
                )
    
    def _is_circuit_open(self) -> bool:
        """检查熔断器是否开启"""
        if not self._is_open:
            return False
        
        # 检查是否可以尝试恢复
        if self._last_failure_time:
            time_since_failure = time.time() - self._last_failure_time
            if time_since_failure > self.recovery_timeout:
                self._is_open = False
                return False
        
        return True
    
    def _record_failure(self):
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._success_count = 0
        
        if self._failure_count >= self.failure_threshold:
            self._is_open = True
            self.logger.warning(f"熔断器开启，失败次数: {self._failure_count}")
    
    def _record_success(self):
        """记录成功"""
        self._success_count += 1
        
        if self._success_count >= self.success_threshold:
            self._failure_count = 0
            self._is_open = False
            self.logger.info("熔断器重置，恢复正常")


class FailoverAction(RecoveryAction):
    """故障转移恢复动作"""
    
    def __init__(self, fallback_providers: List[Callable] = None):
        self.fallback_providers = fallback_providers or []
        self.logger = logging.getLogger(__name__)
    
    def can_handle(self, error: MarketPrismError) -> bool:
        """判断是否能处理该错误"""
        return error.recovery_strategy == RecoveryStrategy.FAILOVER
    
    def execute(self, error: MarketPrismError, context: Dict[str, Any] = None) -> RecoveryResult:
        """执行故障转移"""
        start_time = time.time()
        context = context or {}
        
        fallback_providers = context.get('fallback_providers', self.fallback_providers)
        
        if not fallback_providers:
            return RecoveryResult(
                status=RecoveryStatus.SKIPPED,
                strategy=RecoveryStrategy.FAILOVER,
                attempts=0,
                total_duration=time.time() - start_time,
                success=False,
                error_message="没有可用的故障转移提供者"
            )
        
        attempts = 0
        last_error = None
        
        for provider in fallback_providers:
            attempts += 1
            
            try:
                result = provider()
                
                return RecoveryResult(
                    status=RecoveryStatus.SUCCESS,
                    strategy=RecoveryStrategy.FAILOVER,
                    attempts=attempts,
                    total_duration=time.time() - start_time,
                    success=True,
                    recovery_data={"failover_result": result, "provider_index": attempts - 1}
                )
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"故障转移提供者{attempts}失败: {e}")
        
        return RecoveryResult(
            status=RecoveryStatus.FAILED,
            strategy=RecoveryStrategy.FAILOVER,
            attempts=attempts,
            total_duration=time.time() - start_time,
            success=False,
            error_message=str(last_error) if last_error else "所有故障转移提供者都失败"
        )


class GracefulDegradationAction(RecoveryAction):
    """优雅降级恢复动作"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def can_handle(self, error: MarketPrismError) -> bool:
        """判断是否能处理该错误"""
        return error.recovery_strategy == RecoveryStrategy.GRACEFUL_DEGRADATION
    
    def execute(self, error: MarketPrismError, context: Dict[str, Any] = None) -> RecoveryResult:
        """执行优雅降级"""
        start_time = time.time()
        context = context or {}
        
        degraded_function = context.get('degraded_function')
        
        if not degraded_function:
            return RecoveryResult(
                status=RecoveryStatus.SKIPPED,
                strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                attempts=0,
                total_duration=time.time() - start_time,
                success=False,
                error_message="没有提供降级函数"
            )
        
        try:
            result = degraded_function()
            
            return RecoveryResult(
                status=RecoveryStatus.SUCCESS,
                strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                attempts=1,
                total_duration=time.time() - start_time,
                success=True,
                recovery_data={"degraded_result": result}
            )
            
        except Exception as e:
            return RecoveryResult(
                status=RecoveryStatus.FAILED,
                strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                attempts=1,
                total_duration=time.time() - start_time,
                success=False,
                error_message=str(e)
            )


class ErrorRecoveryManager:
    """错误恢复管理器
    
    管理各种错误恢复策略和恢复动作，提供智能错误恢复机制。
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.recovery_actions: Dict[RecoveryStrategy, RecoveryAction] = {}
        self.recovery_history: List[RecoveryResult] = []
        self._lock = threading.Lock()
        
        # 注册默认恢复动作
        self._register_default_actions()
    
    def _register_default_actions(self):
        """注册默认恢复动作"""
        self.register_action(RecoveryStrategy.RETRY, RetryAction())
        self.register_action(RecoveryStrategy.EXPONENTIAL_BACKOFF, RetryAction(exponential_backoff=True))
        self.register_action(RecoveryStrategy.CIRCUIT_BREAKER, CircuitBreakerAction())
        self.register_action(RecoveryStrategy.FAILOVER, FailoverAction())
        self.register_action(RecoveryStrategy.GRACEFUL_DEGRADATION, GracefulDegradationAction())
    
    def register_action(self, strategy: RecoveryStrategy, action: RecoveryAction):
        """注册恢复动作"""
        self.recovery_actions[strategy] = action
        self.logger.info(f"注册恢复动作: {strategy.value}")
    
    def attempt_recovery(self, 
                        error: MarketPrismError,
                        context: Dict[str, Any] = None) -> Optional[RecoveryResult]:
        """尝试错误恢复
        
        Args:
            error: 要恢复的错误
            context: 恢复上下文，包含恢复所需的函数和参数
            
        Returns:
            恢复结果
        """
        if error.recovery_strategy == RecoveryStrategy.LOG_ONLY:
            # 仅记录日志，不进行恢复
            return RecoveryResult(
                status=RecoveryStatus.SKIPPED,
                strategy=RecoveryStrategy.LOG_ONLY,
                attempts=0,
                total_duration=0.0,
                success=False,
                error_message="策略为仅记录日志，跳过恢复"
            )
        
        if error.recovery_strategy == RecoveryStrategy.MANUAL_INTERVENTION:
            # 需要人工干预
            return RecoveryResult(
                status=RecoveryStatus.SKIPPED,
                strategy=RecoveryStrategy.MANUAL_INTERVENTION,
                attempts=0,
                total_duration=0.0,
                success=False,
                error_message="需要人工干预，跳过自动恢复"
            )
        
        # 查找对应的恢复动作
        action = self.recovery_actions.get(error.recovery_strategy)
        if not action:
            self.logger.warning(f"未找到恢复策略的处理器: {error.recovery_strategy}")
            return RecoveryResult(
                status=RecoveryStatus.SKIPPED,
                strategy=error.recovery_strategy,
                attempts=0,
                total_duration=0.0,
                success=False,
                error_message=f"未找到恢复策略处理器: {error.recovery_strategy.value}"
            )
        
        if not action.can_handle(error):
            self.logger.warning(f"恢复动作无法处理该错误: {error.error_type}")
            return RecoveryResult(
                status=RecoveryStatus.SKIPPED,
                strategy=error.recovery_strategy,
                attempts=0,
                total_duration=0.0,
                success=False,
                error_message="恢复动作无法处理该错误"
            )
        
        # 执行恢复
        self.logger.info(f"尝试恢复错误: {error.error_type.name}, 策略: {error.recovery_strategy.value}")
        
        try:
            result = action.execute(error, context)
            
            # 记录恢复历史
            with self._lock:
                self.recovery_history.append(result)
                # 限制历史记录大小
                if len(self.recovery_history) > 1000:
                    self.recovery_history = self.recovery_history[-1000:]
            
            self.logger.info(f"恢复完成: {result.status.value}, 成功: {result.success}")
            return result
            
        except Exception as e:
            self.logger.error(f"恢复执行失败: {e}")
            return RecoveryResult(
                status=RecoveryStatus.FAILED,
                strategy=error.recovery_strategy,
                attempts=1,
                total_duration=0.0,
                success=False,
                error_message=f"恢复执行异常: {str(e)}"
            )
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """获取恢复统计信息"""
        with self._lock:
            if not self.recovery_history:
                return {
                    "total_attempts": 0,
                    "success_rate": 0.0,
                    "by_strategy": {},
                    "by_status": {}
                }
            
            total = len(self.recovery_history)
            successful = len([r for r in self.recovery_history if r.success])
            
            # 按策略统计
            by_strategy = {}
            for result in self.recovery_history:
                strategy = result.strategy.value
                if strategy not in by_strategy:
                    by_strategy[strategy] = {"total": 0, "success": 0}
                by_strategy[strategy]["total"] += 1
                if result.success:
                    by_strategy[strategy]["success"] += 1
            
            # 按状态统计
            by_status = {}
            for result in self.recovery_history:
                status = result.status.value
                by_status[status] = by_status.get(status, 0) + 1
            
            return {
                "total_attempts": total,
                "successful_attempts": successful,
                "success_rate": successful / total if total > 0 else 0.0,
                "by_strategy": by_strategy,
                "by_status": by_status,
                "last_recovery": self.recovery_history[-1].timestamp.isoformat() if self.recovery_history else None
            }
    
    def get_recent_recoveries(self, limit: int = 10) -> List[RecoveryResult]:
        """获取最近的恢复记录"""
        with self._lock:
            return self.recovery_history[-limit:] if self.recovery_history else []
    
    def clear_history(self):
        """清除恢复历史"""
        with self._lock:
            self.recovery_history.clear()
            self.logger.info("清除恢复历史记录")