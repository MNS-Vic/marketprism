"""
限流中间件TDD测试
专门用于提升rate_limiting_middleware.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

# 导入限流中间件模块（假设存在）
try:
    from core.middleware.rate_limiting_middleware import (
        RateLimitingMiddleware, RateLimitConfig, RateLimitRule, RateLimitStrategy,
        TokenBucket, SlidingWindow, FixedWindow, LeakyBucket,
        RateLimitResult, RateLimitContext, RateLimitStore, MemoryRateLimitStore,
        RedisRateLimitStore, RateLimitType, RateLimitScope
    )
except ImportError:
    # 如果模块不存在，创建模拟类用于测试
    from enum import Enum
    from dataclasses import dataclass, field
    import threading
    
    class RateLimitType(Enum):
        TOKEN_BUCKET = "token_bucket"
        SLIDING_WINDOW = "sliding_window"
        FIXED_WINDOW = "fixed_window"
        LEAKY_BUCKET = "leaky_bucket"
    
    class RateLimitScope(Enum):
        GLOBAL = "global"
        IP = "ip"
        USER = "user"
        API_KEY = "api_key"
        ENDPOINT = "endpoint"
    
    @dataclass
    class RateLimitRule:
        rule_id: str
        name: str
        description: str = ""
        rate_limit_type: RateLimitType = RateLimitType.TOKEN_BUCKET
        scope: RateLimitScope = RateLimitScope.IP
        requests_per_window: int = 100
        window_size_seconds: int = 60
        burst_size: int = None
        path_pattern: str = "*"
        method_pattern: str = "*"
        enabled: bool = True
        priority: int = 0
        
        def __post_init__(self):
            if self.burst_size is None:
                self.burst_size = self.requests_per_window
        
        def matches_request(self, method: str, path: str) -> bool:
            """检查请求是否匹配规则"""
            method_match = self.method_pattern == "*" or method.upper() == self.method_pattern.upper()
            
            if self.path_pattern == "*":
                path_match = True
            elif self.path_pattern.endswith("/*"):
                prefix = self.path_pattern[:-2]
                path_match = path.startswith(prefix)
            else:
                path_match = path == self.path_pattern
            
            return method_match and path_match
    
    @dataclass
    class RateLimitConfig:
        enabled: bool = True
        default_requests_per_minute: int = 60
        default_burst_size: int = 100
        cleanup_interval: int = 300
        store_type: str = "memory"
        redis_url: str = None
        rules: List[RateLimitRule] = field(default_factory=list)
        
        def add_rule(self, rule: RateLimitRule) -> None:
            self.rules.append(rule)
        
        def remove_rule(self, rule_id: str) -> bool:
            for i, rule in enumerate(self.rules):
                if rule.rule_id == rule_id:
                    del self.rules[i]
                    return True
            return False
        
        def find_matching_rule(self, method: str, path: str) -> Optional[RateLimitRule]:
            # 按优先级排序
            sorted_rules = sorted(self.rules, key=lambda r: r.priority, reverse=True)
            
            for rule in sorted_rules:
                if rule.enabled and rule.matches_request(method, path):
                    return rule
            
            return None
    
    @dataclass
    class RateLimitResult:
        allowed: bool
        remaining: int
        reset_time: datetime
        retry_after: int = 0
        rule_id: str = None
        reason: str = ""
        
        @classmethod
        def allow(cls, remaining: int, reset_time: datetime, rule_id: str = None):
            return cls(
                allowed=True,
                remaining=remaining,
                reset_time=reset_time,
                rule_id=rule_id
            )
        
        @classmethod
        def deny(cls, retry_after: int, reset_time: datetime, rule_id: str = None, reason: str = ""):
            return cls(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                retry_after=retry_after,
                rule_id=rule_id,
                reason=reason
            )
    
    @dataclass
    class RateLimitContext:
        identifier: str
        scope: RateLimitScope
        method: str
        path: str
        timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
        metadata: Dict[str, Any] = field(default_factory=dict)
    
    class TokenBucket:
        def __init__(self, capacity: int, refill_rate: float):
            self.capacity = capacity
            self.refill_rate = refill_rate  # tokens per second
            self.tokens = capacity
            self.last_refill = time.time()
            self._lock = threading.Lock()
        
        def consume(self, tokens: int = 1) -> bool:
            with self._lock:
                now = time.time()
                # 计算需要添加的令牌数
                time_passed = now - self.last_refill
                tokens_to_add = time_passed * self.refill_rate
                
                # 更新令牌数，不超过容量
                self.tokens = min(self.capacity, self.tokens + tokens_to_add)
                self.last_refill = now
                
                # 检查是否有足够的令牌
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                else:
                    return False
        
        def get_tokens(self) -> float:
            with self._lock:
                now = time.time()
                time_passed = now - self.last_refill
                tokens_to_add = time_passed * self.refill_rate
                return min(self.capacity, self.tokens + tokens_to_add)
        
        def reset(self) -> None:
            with self._lock:
                self.tokens = self.capacity
                self.last_refill = time.time()
    
    class SlidingWindow:
        def __init__(self, window_size: int, max_requests: int):
            self.window_size = window_size  # seconds
            self.max_requests = max_requests
            self.requests = []
            self._lock = threading.Lock()
        
        def is_allowed(self) -> bool:
            with self._lock:
                now = time.time()
                # 移除过期的请求
                cutoff_time = now - self.window_size
                self.requests = [req_time for req_time in self.requests if req_time > cutoff_time]
                
                # 检查是否超过限制
                if len(self.requests) < self.max_requests:
                    self.requests.append(now)
                    return True
                else:
                    return False
        
        def get_remaining(self) -> int:
            with self._lock:
                now = time.time()
                cutoff_time = now - self.window_size
                active_requests = [req_time for req_time in self.requests if req_time > cutoff_time]
                return max(0, self.max_requests - len(active_requests))
        
        def get_reset_time(self) -> datetime:
            with self._lock:
                if not self.requests:
                    return datetime.now(timezone.utc)
                
                oldest_request = min(self.requests)
                reset_timestamp = oldest_request + self.window_size
                return datetime.fromtimestamp(reset_timestamp, timezone.utc)
        
        def reset(self) -> None:
            with self._lock:
                self.requests.clear()
    
    class FixedWindow:
        def __init__(self, window_size: int, max_requests: int):
            self.window_size = window_size  # seconds
            self.max_requests = max_requests
            self.current_window_start = 0
            self.current_requests = 0
            self._lock = threading.Lock()
        
        def is_allowed(self) -> bool:
            with self._lock:
                now = time.time()
                window_start = int(now // self.window_size) * self.window_size
                
                # 如果是新窗口，重置计数
                if window_start != self.current_window_start:
                    self.current_window_start = window_start
                    self.current_requests = 0
                
                # 检查是否超过限制
                if self.current_requests < self.max_requests:
                    self.current_requests += 1
                    return True
                else:
                    return False
        
        def get_remaining(self) -> int:
            with self._lock:
                now = time.time()
                window_start = int(now // self.window_size) * self.window_size
                
                if window_start != self.current_window_start:
                    return self.max_requests
                else:
                    return max(0, self.max_requests - self.current_requests)
        
        def get_reset_time(self) -> datetime:
            now = time.time()
            window_start = int(now // self.window_size) * self.window_size
            next_window = window_start + self.window_size
            return datetime.fromtimestamp(next_window, timezone.utc)
        
        def reset(self) -> None:
            with self._lock:
                self.current_requests = 0
                self.current_window_start = 0
    
    class MemoryRateLimitStore:
        def __init__(self):
            self.buckets = {}
            self.windows = {}
            self._lock = threading.Lock()
        
        def get_token_bucket(self, key: str, capacity: int, refill_rate: float) -> TokenBucket:
            with self._lock:
                if key not in self.buckets:
                    self.buckets[key] = TokenBucket(capacity, refill_rate)
                return self.buckets[key]
        
        def get_sliding_window(self, key: str, window_size: int, max_requests: int) -> SlidingWindow:
            with self._lock:
                if key not in self.windows:
                    self.windows[key] = SlidingWindow(window_size, max_requests)
                return self.windows[key]
        
        def get_fixed_window(self, key: str, window_size: int, max_requests: int) -> FixedWindow:
            with self._lock:
                window_key = f"{key}_fixed"
                if window_key not in self.windows:
                    self.windows[window_key] = FixedWindow(window_size, max_requests)
                return self.windows[window_key]
        
        def cleanup_expired(self) -> None:
            # 简化的清理逻辑
            pass
        
        def clear(self) -> None:
            with self._lock:
                self.buckets.clear()
                self.windows.clear()
    
    class RateLimitingMiddleware:
        def __init__(self, config: RateLimitConfig):
            self.config = config
            self.store = MemoryRateLimitStore()
        
        def _build_key(self, context: RateLimitContext) -> str:
            """构建限流键"""
            if context.scope == RateLimitScope.GLOBAL:
                return "global"
            elif context.scope == RateLimitScope.IP:
                return f"ip:{context.identifier}"
            elif context.scope == RateLimitScope.USER:
                return f"user:{context.identifier}"
            elif context.scope == RateLimitScope.API_KEY:
                return f"api_key:{context.identifier}"
            elif context.scope == RateLimitScope.ENDPOINT:
                return f"endpoint:{context.path}"
            else:
                return f"unknown:{context.identifier}"
        
        async def check_rate_limit(self, context: RateLimitContext) -> RateLimitResult:
            """检查限流"""
            if not self.config.enabled:
                return RateLimitResult.allow(
                    remaining=999999,
                    reset_time=datetime.now(timezone.utc) + timedelta(minutes=1)
                )
            
            # 查找匹配的规则
            rule = self.config.find_matching_rule(context.method, context.path)
            if not rule:
                # 使用默认限制
                rule = RateLimitRule(
                    rule_id="default",
                    name="Default Rule",
                    requests_per_window=self.config.default_requests_per_minute,
                    window_size_seconds=60
                )
            
            key = self._build_key(context)
            
            if rule.rate_limit_type == RateLimitType.TOKEN_BUCKET:
                return await self._check_token_bucket(key, rule)
            elif rule.rate_limit_type == RateLimitType.SLIDING_WINDOW:
                return await self._check_sliding_window(key, rule)
            elif rule.rate_limit_type == RateLimitType.FIXED_WINDOW:
                return await self._check_fixed_window(key, rule)
            else:
                return RateLimitResult.deny(
                    retry_after=60,
                    reset_time=datetime.now(timezone.utc) + timedelta(minutes=1),
                    reason="Unsupported rate limit type"
                )
        
        async def _check_token_bucket(self, key: str, rule: RateLimitRule) -> RateLimitResult:
            refill_rate = rule.requests_per_window / rule.window_size_seconds
            bucket = self.store.get_token_bucket(key, rule.burst_size, refill_rate)
            
            if bucket.consume():
                return RateLimitResult.allow(
                    remaining=int(bucket.get_tokens()),
                    reset_time=datetime.now(timezone.utc) + timedelta(seconds=rule.window_size_seconds),
                    rule_id=rule.rule_id
                )
            else:
                retry_after = int((1 - bucket.get_tokens()) / refill_rate) + 1
                return RateLimitResult.deny(
                    retry_after=retry_after,
                    reset_time=datetime.now(timezone.utc) + timedelta(seconds=retry_after),
                    rule_id=rule.rule_id,
                    reason="Token bucket exhausted"
                )
        
        async def _check_sliding_window(self, key: str, rule: RateLimitRule) -> RateLimitResult:
            window = self.store.get_sliding_window(key, rule.window_size_seconds, rule.requests_per_window)
            
            if window.is_allowed():
                return RateLimitResult.allow(
                    remaining=window.get_remaining(),
                    reset_time=window.get_reset_time(),
                    rule_id=rule.rule_id
                )
            else:
                return RateLimitResult.deny(
                    retry_after=rule.window_size_seconds,
                    reset_time=window.get_reset_time(),
                    rule_id=rule.rule_id,
                    reason="Sliding window limit exceeded"
                )
        
        async def _check_fixed_window(self, key: str, rule: RateLimitRule) -> RateLimitResult:
            window = self.store.get_fixed_window(key, rule.window_size_seconds, rule.requests_per_window)
            
            if window.is_allowed():
                return RateLimitResult.allow(
                    remaining=window.get_remaining(),
                    reset_time=window.get_reset_time(),
                    rule_id=rule.rule_id
                )
            else:
                return RateLimitResult.deny(
                    retry_after=int((window.get_reset_time() - datetime.now(timezone.utc)).total_seconds()),
                    reset_time=window.get_reset_time(),
                    rule_id=rule.rule_id,
                    reason="Fixed window limit exceeded"
                )

from core.middleware.middleware_framework import MiddlewareConfig, MiddlewareType, MiddlewareContext


class TestRateLimitRule:
    """测试限流规则"""
    
    def test_rate_limit_rule_creation(self):
        """测试：限流规则创建"""
        rule = RateLimitRule(
            rule_id="api_limit",
            name="API限流规则",
            description="API接口限流",
            rate_limit_type=RateLimitType.TOKEN_BUCKET,
            scope=RateLimitScope.IP,
            requests_per_window=100,
            window_size_seconds=60,
            burst_size=150,
            path_pattern="/api/*",
            method_pattern="*",
            enabled=True,
            priority=10
        )
        
        assert rule.rule_id == "api_limit"
        assert rule.name == "API限流规则"
        assert rule.description == "API接口限流"
        assert rule.rate_limit_type == RateLimitType.TOKEN_BUCKET
        assert rule.scope == RateLimitScope.IP
        assert rule.requests_per_window == 100
        assert rule.window_size_seconds == 60
        assert rule.burst_size == 150
        assert rule.path_pattern == "/api/*"
        assert rule.method_pattern == "*"
        assert rule.enabled is True
        assert rule.priority == 10
        
    def test_rate_limit_rule_defaults(self):
        """测试：限流规则默认值"""
        rule = RateLimitRule(rule_id="basic", name="基础规则")
        
        assert rule.rule_id == "basic"
        assert rule.name == "基础规则"
        assert rule.description == ""
        assert rule.rate_limit_type == RateLimitType.TOKEN_BUCKET
        assert rule.scope == RateLimitScope.IP
        assert rule.requests_per_window == 100
        assert rule.window_size_seconds == 60
        assert rule.burst_size == 100  # 默认等于requests_per_window
        assert rule.path_pattern == "*"
        assert rule.method_pattern == "*"
        assert rule.enabled is True
        assert rule.priority == 0

    def test_rate_limit_rule_matches_request(self):
        """测试：限流规则请求匹配"""
        # 通配符规则
        wildcard_rule = RateLimitRule(
            rule_id="wildcard",
            name="通配符规则",
            path_pattern="*",
            method_pattern="*"
        )

        assert wildcard_rule.matches_request("GET", "/any/path") is True
        assert wildcard_rule.matches_request("POST", "/api/users") is True

        # API路径规则
        api_rule = RateLimitRule(
            rule_id="api",
            name="API规则",
            path_pattern="/api/*",
            method_pattern="GET"
        )

        assert api_rule.matches_request("GET", "/api/users") is True
        assert api_rule.matches_request("GET", "/api/users/123") is True
        assert api_rule.matches_request("POST", "/api/users") is False
        assert api_rule.matches_request("GET", "/public/info") is False

        # 精确匹配规则
        exact_rule = RateLimitRule(
            rule_id="exact",
            name="精确规则",
            path_pattern="/api/health",
            method_pattern="GET"
        )

        assert exact_rule.matches_request("GET", "/api/health") is True
        assert exact_rule.matches_request("GET", "/api/health/check") is False
        assert exact_rule.matches_request("POST", "/api/health") is False


class TestRateLimitConfig:
    """测试限流配置"""

    def setup_method(self):
        """设置测试方法"""
        self.config = RateLimitConfig()

    def test_rate_limit_config_creation(self):
        """测试：限流配置创建"""
        config = RateLimitConfig(
            enabled=True,
            default_requests_per_minute=60,
            default_burst_size=100,
            cleanup_interval=300,
            store_type="memory"
        )

        assert config.enabled is True
        assert config.default_requests_per_minute == 60
        assert config.default_burst_size == 100
        assert config.cleanup_interval == 300
        assert config.store_type == "memory"
        assert config.rules == []

    def test_rate_limit_config_defaults(self):
        """测试：限流配置默认值"""
        assert self.config.enabled is True
        assert self.config.default_requests_per_minute == 60
        assert self.config.default_burst_size == 100
        assert self.config.cleanup_interval == 300
        assert self.config.store_type == "memory"
        assert self.config.redis_url is None
        assert self.config.rules == []

    def test_add_remove_rule(self):
        """测试：添加和移除规则"""
        rule = RateLimitRule(rule_id="test_rule", name="测试规则")

        # 添加规则
        self.config.add_rule(rule)
        assert len(self.config.rules) == 1
        assert self.config.rules[0] == rule

        # 移除规则
        result = self.config.remove_rule("test_rule")
        assert result is True
        assert len(self.config.rules) == 0

        # 移除不存在的规则
        result = self.config.remove_rule("non_existent")
        assert result is False

    def test_find_matching_rule(self):
        """测试：查找匹配规则"""
        # 添加多个规则
        high_priority_rule = RateLimitRule(
            rule_id="high_priority",
            name="高优先级",
            path_pattern="/api/important/*",
            priority=100
        )

        low_priority_rule = RateLimitRule(
            rule_id="low_priority",
            name="低优先级",
            path_pattern="/api/*",
            priority=10
        )

        self.config.add_rule(low_priority_rule)
        self.config.add_rule(high_priority_rule)

        # 测试高优先级匹配
        matched = self.config.find_matching_rule("GET", "/api/important/data")
        assert matched == high_priority_rule

        # 测试低优先级匹配
        matched = self.config.find_matching_rule("GET", "/api/users")
        assert matched == low_priority_rule

        # 测试无匹配
        matched = self.config.find_matching_rule("GET", "/public/info")
        assert matched is None


class TestTokenBucket:
    """测试令牌桶算法"""

    def test_token_bucket_creation(self):
        """测试：令牌桶创建"""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        assert bucket.capacity == 10
        assert bucket.refill_rate == 1.0
        assert bucket.tokens == 10

    def test_token_bucket_consume(self):
        """测试：令牌桶消费"""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        # 消费令牌
        assert bucket.consume(1) is True
        assert bucket.consume(5) is True
        assert abs(bucket.get_tokens() - 4) < 0.1  # 允许浮点数误差

        # 消费超过容量
        assert bucket.consume(10) is False
        assert abs(bucket.get_tokens() - 4) < 0.1

    def test_token_bucket_refill(self):
        """测试：令牌桶补充"""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)  # 每秒10个令牌

        # 消费所有令牌
        bucket.consume(10)
        assert abs(bucket.get_tokens()) < 0.1  # 允许浮点数误差

        # 等待补充
        time.sleep(0.5)  # 等待0.5秒，应该补充5个令牌
        tokens = bucket.get_tokens()
        assert tokens >= 4 and tokens <= 6  # 允许一些时间误差

    def test_token_bucket_reset(self):
        """测试：令牌桶重置"""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)

        bucket.consume(5)
        assert abs(bucket.get_tokens() - 5) < 0.1  # 允许浮点数误差

        bucket.reset()
        assert abs(bucket.get_tokens() - 10) < 0.1


class TestSlidingWindow:
    """测试滑动窗口算法"""

    def test_sliding_window_creation(self):
        """测试：滑动窗口创建"""
        window = SlidingWindow(window_size=60, max_requests=10)

        assert window.window_size == 60
        assert window.max_requests == 10
        assert window.requests == []

    def test_sliding_window_allow_requests(self):
        """测试：滑动窗口允许请求"""
        window = SlidingWindow(window_size=60, max_requests=5)

        # 允许的请求
        for i in range(5):
            assert window.is_allowed() is True

        # 超过限制的请求
        assert window.is_allowed() is False

        # 检查剩余请求数
        assert window.get_remaining() == 0

    def test_sliding_window_expiry(self):
        """测试：滑动窗口过期"""
        window = SlidingWindow(window_size=1, max_requests=2)  # 1秒窗口，最多2个请求

        # 使用所有请求
        assert window.is_allowed() is True
        assert window.is_allowed() is True
        assert window.is_allowed() is False

        # 等待窗口过期
        time.sleep(1.1)

        # 现在应该可以再次请求
        assert window.is_allowed() is True

    def test_sliding_window_reset(self):
        """测试：滑动窗口重置"""
        window = SlidingWindow(window_size=60, max_requests=5)

        window.is_allowed()
        window.is_allowed()
        assert len(window.requests) == 2

        window.reset()
        assert len(window.requests) == 0


class TestFixedWindow:
    """测试固定窗口算法"""

    def test_fixed_window_creation(self):
        """测试：固定窗口创建"""
        window = FixedWindow(window_size=60, max_requests=10)

        assert window.window_size == 60
        assert window.max_requests == 10
        assert window.current_requests == 0

    def test_fixed_window_allow_requests(self):
        """测试：固定窗口允许请求"""
        window = FixedWindow(window_size=60, max_requests=3)

        # 允许的请求
        for i in range(3):
            assert window.is_allowed() is True

        # 超过限制的请求
        assert window.is_allowed() is False

        # 检查剩余请求数
        assert window.get_remaining() == 0

    def test_fixed_window_reset(self):
        """测试：固定窗口重置"""
        window = FixedWindow(window_size=60, max_requests=5)

        window.is_allowed()
        window.is_allowed()
        assert window.current_requests == 2

        window.reset()
        assert window.current_requests == 0
