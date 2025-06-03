"""
MarketPrism 限流中间件

这个模块实现了企业级限流中间件，支持多种限流算法包括令牌桶、漏桶、
滑动窗口和固定窗口。提供灵活的限流策略和分布式限流存储。

核心功能:
1. 多种限流算法：令牌桶、漏桶、滑动窗口、固定窗口
2. 限流策略：基于IP、用户、API密钥等的限流策略
3. 分布式存储：内存和Redis存储支持
4. 动态配置：运行时限流参数调整
5. 限流统计：详细的限流统计和监控
6. 异常处理：完善的限流异常处理
"""

import asyncio
import time
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union
import threading
from collections import deque, defaultdict
from datetime import datetime, timedelta

from .middleware_framework import (
    BaseMiddleware, MiddlewareConfig, MiddlewareContext, MiddlewareResult,
    MiddlewareType, MiddlewarePriority
)


class RateLimitAlgorithm(Enum):
    """限流算法枚举"""
    TOKEN_BUCKET = "token_bucket"         # 令牌桶算法
    LEAKY_BUCKET = "leaky_bucket"         # 漏桶算法
    SLIDING_WINDOW = "sliding_window"     # 滑动窗口算法
    FIXED_WINDOW = "fixed_window"         # 固定窗口算法


class RateLimitScope(Enum):
    """限流作用域枚举"""
    GLOBAL = "global"                     # 全局限流
    IP = "ip"                             # IP限流
    USER = "user"                         # 用户限流
    API_KEY = "api_key"                   # API密钥限流
    ENDPOINT = "endpoint"                 # 端点限流
    CUSTOM = "custom"                     # 自定义限流


@dataclass
class RateLimitRule:
    """限流规则"""
    rule_id: str
    name: str
    description: str = ""
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    scope: RateLimitScope = RateLimitScope.IP
    rate: int = 100                       # 速率（请求数）
    window: int = 60                      # 时间窗口（秒）
    burst: Optional[int] = None           # 突发容量
    key_pattern: str = "*"                # 键模式
    enabled: bool = True
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches_key(self, key: str) -> bool:
        """检查规则是否匹配键"""
        if self.key_pattern == "*":
            return True
        return key.startswith(self.key_pattern)


@dataclass
class RateLimitPolicy:
    """限流策略"""
    policy_id: str
    name: str
    description: str = ""
    rules: List[RateLimitRule] = field(default_factory=list)
    default_rule: Optional[RateLimitRule] = None
    enforcement_mode: str = "strict"      # strict/permissive
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_rule(self, rule: RateLimitRule) -> None:
        """添加限流规则"""
        self.rules.append(rule)
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除限流规则"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                self.rules.remove(rule)
                return True
        return False
    
    def find_matching_rule(self, key: str) -> Optional[RateLimitRule]:
        """查找匹配的规则"""
        # 按优先级排序
        sorted_rules = sorted([r for r in self.rules if r.enabled], 
                             key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            if rule.matches_key(key):
                return rule
        
        return self.default_rule


@dataclass
class RateLimitResult:
    """限流结果"""
    allowed: bool
    remaining: int = 0
    reset_time: Optional[datetime] = None
    retry_after: Optional[int] = None
    limit: int = 0
    used: int = 0
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def allow(cls, remaining: int, limit: int, used: int, **kwargs) -> 'RateLimitResult':
        """创建允许结果"""
        return cls(allowed=True, remaining=remaining, limit=limit, used=used, **kwargs)
    
    @classmethod
    def deny(cls, retry_after: int, limit: int, used: int, reason: str = "", **kwargs) -> 'RateLimitResult':
        """创建拒绝结果"""
        return cls(allowed=False, retry_after=retry_after, limit=limit, used=used, reason=reason, **kwargs)


@dataclass
class RateLimitContext:
    """限流上下文"""
    key: str
    scope: RateLimitScope
    user_id: Optional[str] = None
    ip_address: str = ""
    api_key: Optional[str] = None
    endpoint: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class RateLimitStore(ABC):
    """限流存储抽象基类"""
    
    @abstractmethod
    async def get_count(self, key: str) -> int:
        """获取计数"""
        pass
    
    @abstractmethod
    async def increment(self, key: str, window: int) -> int:
        """递增计数"""
        pass
    
    @abstractmethod
    async def set_count(self, key: str, count: int, ttl: int) -> bool:
        """设置计数"""
        pass
    
    @abstractmethod
    async def get_bucket_state(self, key: str) -> Dict[str, Any]:
        """获取桶状态"""
        pass
    
    @abstractmethod
    async def set_bucket_state(self, key: str, state: Dict[str, Any], ttl: int) -> bool:
        """设置桶状态"""
        pass


class MemoryRateLimitStore(RateLimitStore):
    """内存限流存储"""
    
    def __init__(self):
        self.counts: Dict[str, int] = defaultdict(int)
        self.expiry: Dict[str, float] = {}
        self.bucket_states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def _cleanup_expired(self) -> None:
        """清理过期数据"""
        current_time = time.time()
        expired_keys = []
        
        for key, exp_time in self.expiry.items():
            if current_time > exp_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            self.counts.pop(key, None)
            self.expiry.pop(key, None)
            self.bucket_states.pop(key, None)
    
    async def get_count(self, key: str) -> int:
        """获取计数"""
        with self._lock:
            self._cleanup_expired()
            return self.counts.get(key, 0)
    
    async def increment(self, key: str, window: int) -> int:
        """递增计数"""
        with self._lock:
            self._cleanup_expired()
            self.counts[key] += 1
            self.expiry[key] = time.time() + window
            return self.counts[key]
    
    async def set_count(self, key: str, count: int, ttl: int) -> bool:
        """设置计数"""
        with self._lock:
            self.counts[key] = count
            self.expiry[key] = time.time() + ttl
            return True
    
    async def get_bucket_state(self, key: str) -> Dict[str, Any]:
        """获取桶状态"""
        with self._lock:
            self._cleanup_expired()
            return self.bucket_states.get(key, {})
    
    async def set_bucket_state(self, key: str, state: Dict[str, Any], ttl: int) -> bool:
        """设置桶状态"""
        with self._lock:
            self.bucket_states[key] = state
            self.expiry[key] = time.time() + ttl
            return True


class RedisRateLimitStore(RateLimitStore):
    """Redis限流存储"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get_count(self, key: str) -> int:
        """获取计数"""
        try:
            count = await self.redis.get(f"rate_limit_count:{key}")
            return int(count) if count else 0
        except Exception:
            return 0
    
    async def increment(self, key: str, window: int) -> int:
        """递增计数"""
        try:
            pipe = self.redis.pipeline()
            count_key = f"rate_limit_count:{key}"
            pipe.incr(count_key)
            pipe.expire(count_key, window)
            results = await pipe.execute()
            return results[0]
        except Exception:
            return 0
    
    async def set_count(self, key: str, count: int, ttl: int) -> bool:
        """设置计数"""
        try:
            await self.redis.setex(f"rate_limit_count:{key}", ttl, count)
            return True
        except Exception:
            return False
    
    async def get_bucket_state(self, key: str) -> Dict[str, Any]:
        """获取桶状态"""
        try:
            state = await self.redis.hgetall(f"rate_limit_bucket:{key}")
            return {k.decode(): float(v.decode()) for k, v in state.items()} if state else {}
        except Exception:
            return {}
    
    async def set_bucket_state(self, key: str, state: Dict[str, Any], ttl: int) -> bool:
        """设置桶状态"""
        try:
            bucket_key = f"rate_limit_bucket:{key}"
            await self.redis.hmset(bucket_key, state)
            await self.redis.expire(bucket_key, ttl)
            return True
        except Exception:
            return False


class TokenBucketLimiter:
    """令牌桶限流器"""
    
    def __init__(self, rate: int, burst: int, store: RateLimitStore):
        self.rate = rate          # 令牌生成速率（令牌/秒）
        self.burst = burst        # 桶容量
        self.store = store
    
    async def is_allowed(self, key: str) -> RateLimitResult:
        """检查是否允许请求"""
        try:
            current_time = time.time()
            
            # 获取桶状态
            state = await self.store.get_bucket_state(key)
            tokens = state.get('tokens', self.burst)
            last_refill = state.get('last_refill', current_time)
            
            # 计算需要添加的令牌数
            time_passed = current_time - last_refill
            tokens_to_add = time_passed * self.rate
            tokens = min(self.burst, tokens + tokens_to_add)
            
            if tokens >= 1:
                # 消费一个令牌
                tokens -= 1
                
                # 更新状态
                new_state = {
                    'tokens': tokens,
                    'last_refill': current_time
                }
                await self.store.set_bucket_state(key, new_state, 3600)
                
                return RateLimitResult.allow(
                    remaining=int(tokens),
                    limit=self.burst,
                    used=self.burst - int(tokens)
                )
            else:
                # 令牌不足
                retry_after = int((1 - tokens) / self.rate)
                return RateLimitResult.deny(
                    retry_after=retry_after,
                    limit=self.burst,
                    used=self.burst,
                    reason="Token bucket exhausted"
                )
                
        except Exception as e:
            return RateLimitResult.deny(
                retry_after=60,
                limit=self.burst,
                used=0,
                reason=f"Rate limiting error: {str(e)}"
            )


class LeakyBucketLimiter:
    """漏桶限流器"""
    
    def __init__(self, rate: int, capacity: int, store: RateLimitStore):
        self.rate = rate          # 漏出速率（请求/秒）
        self.capacity = capacity  # 桶容量
        self.store = store
    
    async def is_allowed(self, key: str) -> RateLimitResult:
        """检查是否允许请求"""
        try:
            current_time = time.time()
            
            # 获取桶状态
            state = await self.store.get_bucket_state(key)
            volume = state.get('volume', 0)
            last_leak = state.get('last_leak', current_time)
            
            # 计算漏出的请求数
            time_passed = current_time - last_leak
            leaked = time_passed * self.rate
            volume = max(0, volume - leaked)
            
            if volume < self.capacity:
                # 桶未满，添加请求
                volume += 1
                
                # 更新状态
                new_state = {
                    'volume': volume,
                    'last_leak': current_time
                }
                await self.store.set_bucket_state(key, new_state, 3600)
                
                return RateLimitResult.allow(
                    remaining=int(self.capacity - volume),
                    limit=self.capacity,
                    used=int(volume)
                )
            else:
                # 桶已满
                retry_after = int((volume - self.capacity + 1) / self.rate)
                return RateLimitResult.deny(
                    retry_after=retry_after,
                    limit=self.capacity,
                    used=int(volume),
                    reason="Leaky bucket full"
                )
                
        except Exception as e:
            return RateLimitResult.deny(
                retry_after=60,
                limit=self.capacity,
                used=0,
                reason=f"Rate limiting error: {str(e)}"
            )


class SlidingWindowLimiter:
    """滑动窗口限流器"""
    
    def __init__(self, rate: int, window: int, store: RateLimitStore):
        self.rate = rate          # 允许的请求数
        self.window = window      # 时间窗口（秒）
        self.store = store
        self.windows: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
    
    async def is_allowed(self, key: str) -> RateLimitResult:
        """检查是否允许请求"""
        try:
            current_time = time.time()
            window_start = current_time - self.window
            
            with self._lock:
                # 获取窗口内的请求
                if key not in self.windows:
                    self.windows[key] = deque()
                
                requests = self.windows[key]
                
                # 移除过期请求
                while requests and requests[0] < window_start:
                    requests.popleft()
                
                if len(requests) < self.rate:
                    # 允许请求
                    requests.append(current_time)
                    
                    return RateLimitResult.allow(
                        remaining=self.rate - len(requests),
                        limit=self.rate,
                        used=len(requests)
                    )
                else:
                    # 超出限制
                    oldest_request = requests[0]
                    retry_after = int(oldest_request + self.window - current_time)
                    
                    return RateLimitResult.deny(
                        retry_after=max(1, retry_after),
                        limit=self.rate,
                        used=len(requests),
                        reason="Sliding window limit exceeded"
                    )
                    
        except Exception as e:
            return RateLimitResult.deny(
                retry_after=60,
                limit=self.rate,
                used=0,
                reason=f"Rate limiting error: {str(e)}"
            )


class FixedWindowLimiter:
    """固定窗口限流器"""
    
    def __init__(self, rate: int, window: int, store: RateLimitStore):
        self.rate = rate          # 允许的请求数
        self.window = window      # 时间窗口（秒）
        self.store = store
    
    async def is_allowed(self, key: str) -> RateLimitResult:
        """检查是否允许请求"""
        try:
            current_time = time.time()
            window_start = int(current_time // self.window) * self.window
            window_key = f"{key}:{window_start}"
            
            # 获取当前窗口的请求数
            count = await self.store.get_count(window_key)
            
            if count < self.rate:
                # 允许请求
                new_count = await self.store.increment(window_key, self.window)
                
                return RateLimitResult.allow(
                    remaining=self.rate - new_count,
                    limit=self.rate,
                    used=new_count,
                    reset_time=datetime.fromtimestamp(window_start + self.window)
                )
            else:
                # 超出限制
                reset_time = window_start + self.window
                retry_after = int(reset_time - current_time)
                
                return RateLimitResult.deny(
                    retry_after=retry_after,
                    limit=self.rate,
                    used=count,
                    reason="Fixed window limit exceeded",
                    reset_time=datetime.fromtimestamp(reset_time)
                )
                
        except Exception as e:
            return RateLimitResult.deny(
                retry_after=60,
                limit=self.rate,
                used=0,
                reason=f"Rate limiting error: {str(e)}"
            )


@dataclass
class RateLimitingConfig:
    """限流中间件配置"""
    enabled: bool = True
    default_algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    default_rate: int = 100
    default_window: int = 60
    default_burst: Optional[int] = None
    policies: List[RateLimitPolicy] = field(default_factory=list)
    key_extractors: Dict[RateLimitScope, str] = field(default_factory=dict)
    skip_paths: List[str] = field(default_factory=list)
    store_config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class RateLimitingMiddleware(BaseMiddleware):
    """限流中间件"""
    
    def __init__(self, config: MiddlewareConfig, rate_config: RateLimitingConfig, store: Optional[RateLimitStore] = None):
        super().__init__(config)
        self.rate_config = rate_config
        self.store = store or MemoryRateLimitStore()
        self.policies: Dict[str, RateLimitPolicy] = {}
        self.limiters: Dict[str, Union[TokenBucketLimiter, LeakyBucketLimiter, SlidingWindowLimiter, FixedWindowLimiter]] = {}
        self._setup_policies()
        self._setup_limiters()
    
    def _setup_policies(self) -> None:
        """设置限流策略"""
        for policy in self.rate_config.policies:
            self.policies[policy.policy_id] = policy
    
    def _setup_limiters(self) -> None:
        """设置限流器"""
        # 为每种算法创建默认限流器
        burst = self.rate_config.default_burst or self.rate_config.default_rate
        
        self.limiters[RateLimitAlgorithm.TOKEN_BUCKET.value] = TokenBucketLimiter(
            self.rate_config.default_rate,
            burst,
            self.store
        )
        
        self.limiters[RateLimitAlgorithm.LEAKY_BUCKET.value] = LeakyBucketLimiter(
            self.rate_config.default_rate,
            burst,
            self.store
        )
        
        self.limiters[RateLimitAlgorithm.SLIDING_WINDOW.value] = SlidingWindowLimiter(
            self.rate_config.default_rate,
            self.rate_config.default_window,
            self.store
        )
        
        self.limiters[RateLimitAlgorithm.FIXED_WINDOW.value] = FixedWindowLimiter(
            self.rate_config.default_rate,
            self.rate_config.default_window,
            self.store
        )
    
    def _should_skip_rate_limiting(self, path: str) -> bool:
        """检查是否应该跳过限流"""
        for skip_path in self.rate_config.skip_paths:
            if path.startswith(skip_path):
                return True
        return False
    
    def _extract_rate_limit_key(self, context: MiddlewareContext, scope: RateLimitScope) -> str:
        """提取限流键"""
        if scope == RateLimitScope.IP:
            return f"ip:{context.request.remote_addr}"
        elif scope == RateLimitScope.USER:
            user_id = context.get_user_data('user_id')
            return f"user:{user_id}" if user_id else f"ip:{context.request.remote_addr}"
        elif scope == RateLimitScope.API_KEY:
            auth_context = context.get_data('authentication_context')
            if auth_context and auth_context.api_key:
                return f"api_key:{auth_context.api_key}"
            return f"ip:{context.request.remote_addr}"
        elif scope == RateLimitScope.ENDPOINT:
            return f"endpoint:{context.request.path}"
        elif scope == RateLimitScope.GLOBAL:
            return "global"
        else:
            return f"custom:{context.request.remote_addr}"
    
    def _find_applicable_policy(self, context: MiddlewareContext) -> Optional[RateLimitPolicy]:
        """查找适用的策略"""
        # 这里可以根据请求特征选择策略
        # 目前返回第一个策略，实际实现中可以更复杂
        if self.policies:
            return list(self.policies.values())[0]
        return None
    
    def _create_limiter_for_rule(self, rule: RateLimitRule) -> Union[TokenBucketLimiter, LeakyBucketLimiter, SlidingWindowLimiter, FixedWindowLimiter]:
        """为规则创建限流器"""
        burst = rule.burst or rule.rate
        
        if rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            return TokenBucketLimiter(rule.rate, burst, self.store)
        elif rule.algorithm == RateLimitAlgorithm.LEAKY_BUCKET:
            return LeakyBucketLimiter(rule.rate, burst, self.store)
        elif rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            return SlidingWindowLimiter(rule.rate, rule.window, self.store)
        elif rule.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            return FixedWindowLimiter(rule.rate, rule.window, self.store)
        else:
            return self.limiters[self.rate_config.default_algorithm.value]
    
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理限流请求"""
        try:
            # 检查是否跳过限流
            if self._should_skip_rate_limiting(context.request.path):
                context.set_data('rate_limiting_skipped', True)
                return MiddlewareResult.success_result()
            
            # 查找适用的策略
            policy = self._find_applicable_policy(context)
            if not policy:
                # 使用默认限流
                key = self._extract_rate_limit_key(context, RateLimitScope.IP)
                limiter = self.limiters[self.rate_config.default_algorithm.value]
                result = await limiter.is_allowed(key)
            else:
                # 使用策略规则
                key = self._extract_rate_limit_key(context, RateLimitScope.IP)
                rule = policy.find_matching_rule(key)
                
                if not rule:
                    rule = policy.default_rule
                
                if rule:
                    limiter = self._create_limiter_for_rule(rule)
                    specific_key = self._extract_rate_limit_key(context, rule.scope)
                    result = await limiter.is_allowed(specific_key)
                else:
                    # 使用默认限流
                    limiter = self.limiters[self.rate_config.default_algorithm.value]
                    result = await limiter.is_allowed(key)
            
            # 设置限流结果
            context.set_data('rate_limit_result', result)
            
            # 添加限流头部
            if context.response:
                if result.limit > 0:
                    context.response.set_header('X-RateLimit-Limit', str(result.limit))
                    context.response.set_header('X-RateLimit-Remaining', str(result.remaining))
                    context.response.set_header('X-RateLimit-Used', str(result.used))
                
                if result.reset_time:
                    context.response.set_header('X-RateLimit-Reset', str(int(result.reset_time.timestamp())))
                
                if result.retry_after:
                    context.response.set_header('Retry-After', str(result.retry_after))
            
            if not result.allowed:
                # 限流触发
                return MiddlewareResult.stop_result(
                    status_code=429,
                    body=f'{{"error": "Rate limit exceeded", "retry_after": {result.retry_after}}}'.encode(),
                    headers={
                        'X-RateLimit-Limit': str(result.limit),
                        'X-RateLimit-Used': str(result.used),
                        'Retry-After': str(result.retry_after)
                    }
                )
            
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    def get_rate_limit_result(self, context: MiddlewareContext) -> Optional[RateLimitResult]:
        """获取限流结果"""
        return context.get_data('rate_limit_result')
    
    def add_policy(self, policy: RateLimitPolicy) -> bool:
        """添加限流策略"""
        try:
            self.policies[policy.policy_id] = policy
            return True
        except Exception:
            return False
    
    def remove_policy(self, policy_id: str) -> bool:
        """移除限流策略"""
        try:
            if policy_id in self.policies:
                del self.policies[policy_id]
                return True
            return False
        except Exception:
            return False
    
    def get_policy(self, policy_id: str) -> Optional[RateLimitPolicy]:
        """获取限流策略"""
        return self.policies.get(policy_id)


# 限流异常类
class RateLimitError(Exception):
    """限流基础异常"""
    pass


class RateLimitExceededError(RateLimitError):
    """限流超出异常"""
    pass


class RateLimitConfigError(RateLimitError):
    """限流配置异常"""
    pass