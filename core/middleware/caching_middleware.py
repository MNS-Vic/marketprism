"""
MarketPrism 缓存中间件

这个模块实现了企业级缓存中间件，支持多层缓存、智能缓存策略、
缓存失效和缓存预热功能。

核心功能:
1. 多层缓存：内存、Redis等多层缓存支持
2. 缓存策略：灵活的缓存策略和TTL计算
3. 缓存键生成：智能的缓存键生成策略
4. 缓存失效：主动缓存失效和更新
5. 缓存预热：缓存预热和预加载
6. 缓存统计：详细的缓存命中率统计
"""

import asyncio
import time
import hashlib
import json
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Callable
import threading
from datetime import datetime, timedelta, timezone

from .middleware_framework import (
    BaseMiddleware, MiddlewareConfig, MiddlewareContext, MiddlewareResult,
    MiddlewareType, MiddlewarePriority
)


class CacheStrategy(Enum):
    """缓存策略枚举"""
    NO_CACHE = "no_cache"                 # 不缓存
    CACHE_ONLY = "cache_only"             # 仅缓存
    CACHE_FIRST = "cache_first"           # 缓存优先
    NETWORK_FIRST = "network_first"       # 网络优先
    STALE_WHILE_REVALIDATE = "stale_while_revalidate"  # 过期时重新验证


class CacheScope(Enum):
    """缓存作用域枚举"""
    GLOBAL = "global"                     # 全局缓存
    USER = "user"                         # 用户缓存
    SESSION = "session"                   # 会话缓存
    IP = "ip"                             # IP缓存
    ENDPOINT = "endpoint"                 # 端点缓存
    CUSTOM = "custom"                     # 自定义缓存


@dataclass
class CacheRule:
    """缓存规则"""
    rule_id: str
    name: str
    description: str = ""
    path_pattern: str = "*"
    method_pattern: str = "*"
    cache_strategy: CacheStrategy = CacheStrategy.CACHE_FIRST
    cache_scope: CacheScope = CacheScope.GLOBAL
    ttl: int = 300                        # 生存时间（秒）
    max_size: Optional[int] = None        # 最大缓存大小
    vary_headers: List[str] = field(default_factory=list)  # 变化头部
    cache_conditions: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches_request(self, method: str, path: str) -> bool:
        """检查请求是否匹配规则"""
        method_match = (self.method_pattern == "*" or 
                       self.method_pattern.upper() == method.upper())
        
        path_match = (self.path_pattern == "*" or 
                     path.startswith(self.path_pattern))
        
        return method_match and path_match
    
    def should_cache_response(self, status_code: int) -> bool:
        """检查响应是否应该缓存"""
        # 默认只缓存成功响应
        cacheable_codes = self.cache_conditions.get('status_codes', [200, 301, 302, 304])
        return status_code in cacheable_codes


@dataclass
class CachePolicy:
    """缓存策略"""
    policy_id: str
    name: str
    description: str = ""
    rules: List[CacheRule] = field(default_factory=list)
    default_rule: Optional[CacheRule] = None
    global_ttl: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_rule(self, rule: CacheRule) -> None:
        """添加缓存规则"""
        self.rules.append(rule)
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除缓存规则"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                self.rules.remove(rule)
                return True
        return False
    
    def find_matching_rule(self, method: str, path: str) -> Optional[CacheRule]:
        """查找匹配的规则"""
        # 按优先级排序
        sorted_rules = sorted([r for r in self.rules if r.enabled], 
                             key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            if rule.matches_request(method, path):
                return rule
        
        return self.default_rule


class CacheKeyGenerator:
    """缓存键生成器"""
    
    def __init__(self, prefix: str = "marketprism_cache"):
        self.prefix = prefix
    
    def generate_key(self, context: MiddlewareContext, rule: CacheRule) -> str:
        """生成缓存键"""
        key_parts = [self.prefix]
        
        # 添加作用域
        if rule.cache_scope == CacheScope.GLOBAL:
            key_parts.append("global")
        elif rule.cache_scope == CacheScope.USER:
            user_id = context.get_user_data('user_id', 'anonymous')
            key_parts.append(f"user_{user_id}")
        elif rule.cache_scope == CacheScope.SESSION:
            session_id = context.get_data('session_id', 'no_session')
            key_parts.append(f"session_{session_id}")
        elif rule.cache_scope == CacheScope.IP:
            ip = context.request.remote_addr
            key_parts.append(f"ip_{ip}")
        elif rule.cache_scope == CacheScope.ENDPOINT:
            key_parts.append(f"endpoint_{context.request.path}")
        
        # 添加请求路径和方法
        key_parts.append(context.request.method)
        key_parts.append(context.request.path.replace('/', '_'))
        
        # 添加查询参数
        if context.request.query_params:
            query_hash = self._hash_dict(context.request.query_params)
            key_parts.append(f"query_{query_hash}")
        
        # 添加变化头部
        if rule.vary_headers:
            vary_values = []
            for header in rule.vary_headers:
                value = context.request.get_header(header)
                if value:
                    vary_values.append(f"{header}_{value}")
            if vary_values:
                vary_hash = self._hash_string("_".join(vary_values))
                key_parts.append(f"vary_{vary_hash}")
        
        return ":".join(key_parts)
    
    def _hash_dict(self, data: Dict[str, Any]) -> str:
        """哈希字典"""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()[:8]
    
    def _hash_string(self, data: str) -> str:
        """哈希字符串"""
        return hashlib.md5(data.encode()).hexdigest()[:8]


class CacheTTLCalculator:
    """缓存TTL计算器"""
    
    def __init__(self):
        self.default_ttl = 300
        self.max_ttl = 86400
    
    def calculate_ttl(self, context: MiddlewareContext, rule: CacheRule) -> int:
        """计算TTL"""
        # 从响应头获取缓存控制
        if context.response:
            cache_control = context.response.get_header('cache-control')
            if cache_control:
                ttl = self._parse_cache_control_ttl(cache_control)
                if ttl is not None:
                    return min(ttl, self.max_ttl)
            
            # 从Expires头获取
            expires = context.response.get_header('expires')
            if expires:
                ttl = self._parse_expires_ttl(expires)
                if ttl is not None:
                    return min(ttl, self.max_ttl)
        
        # 使用规则TTL
        return min(rule.ttl, self.max_ttl)
    
    def _parse_cache_control_ttl(self, cache_control: str) -> Optional[int]:
        """解析Cache-Control头的TTL"""
        try:
            directives = [d.strip() for d in cache_control.split(',')]
            for directive in directives:
                if directive.startswith('max-age='):
                    return int(directive.split('=')[1])
            return None
        except Exception:
            return None
    
    def _parse_expires_ttl(self, expires: str) -> Optional[int]:
        """解析Expires头的TTL"""
        try:
            from email.utils import parsedate_to_datetime
            expires_dt = parsedate_to_datetime(expires)
            now = datetime.now(expires_dt.tzinfo)
            ttl = int((expires_dt - now).total_seconds())
            return max(0, ttl)
        except Exception:
            return None


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: bytes
    created_at: float
    expires_at: float
    last_accessed: float
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.expires_at
    
    def is_stale(self, stale_threshold: int = 60) -> bool:
        """检查是否过期但在允许范围内"""
        now = time.time()
        return self.expires_at < now < (self.expires_at + stale_threshold)
    
    def access(self) -> None:
        """记录访问"""
        self.last_accessed = time.time()
        self.access_count += 1


class CacheStore(ABC):
    """缓存存储抽象基类"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: bytes, ttl: int, metadata: Dict[str, Any] = None) -> bool:
        """设置缓存条目"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存条目"""
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """清空缓存"""
        pass
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        pass


class MemoryCacheStore(CacheStore):
    """内存缓存存储"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: Dict[str, CacheEntry] = {}
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'evictions': 0,
        }
        self._lock = threading.Lock()
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        with self._lock:
            entry = self.cache.get(key)
            if entry:
                if entry.is_expired():
                    del self.cache[key]
                    self.stats['misses'] += 1
                    return None
                else:
                    entry.access()
                    self.stats['hits'] += 1
                    return entry
            else:
                self.stats['misses'] += 1
                return None
    
    async def set(self, key: str, value: bytes, ttl: int, metadata: Dict[str, Any] = None) -> bool:
        """设置缓存条目"""
        try:
            with self._lock:
                now = time.time()
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=now,
                    expires_at=now + ttl,
                    last_accessed=now,
                    metadata=metadata or {}
                )
                
                # 检查是否需要驱逐
                if len(self.cache) >= self.max_size and key not in self.cache:
                    self._evict_lru()
                
                self.cache[key] = entry
                self.stats['sets'] += 1
                return True
        except Exception:
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存条目"""
        with self._lock:
            if key in self.cache:
                del self.cache[key]
                self.stats['deletes'] += 1
                return True
            return False
    
    async def clear(self) -> bool:
        """清空缓存"""
        with self._lock:
            self.cache.clear()
            return True
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **self.stats,
                'total_requests': total_requests,
                'hit_rate': hit_rate,
                'cache_size': len(self.cache),
                'max_size': self.max_size,
            }
    
    def _evict_lru(self) -> None:
        """驱逐最少使用的条目"""
        if not self.cache:
            return
        
        # 找到最少使用的条目
        lru_key = min(self.cache.keys(), key=lambda k: self.cache[k].last_accessed)
        del self.cache[lru_key]
        self.stats['evictions'] += 1


class RedisCacheStore(CacheStore):
    """Redis缓存存储"""
    
    def __init__(self, redis_client, prefix: str = "cache"):
        self.redis = redis_client
        self.prefix = prefix
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
        }
        self._lock = threading.Lock()
    
    def _make_key(self, key: str) -> str:
        """生成Redis键"""
        return f"{self.prefix}:{key}"
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        try:
            redis_key = self._make_key(key)
            data = await self.redis.get(redis_key)
            
            if data:
                entry = pickle.loads(data)
                if entry.is_expired():
                    await self.redis.delete(redis_key)
                    with self._lock:
                        self.stats['misses'] += 1
                    return None
                else:
                    entry.access()
                    # 更新访问信息
                    await self.redis.set(redis_key, pickle.dumps(entry), ex=int(entry.expires_at - time.time()))
                    with self._lock:
                        self.stats['hits'] += 1
                    return entry
            else:
                with self._lock:
                    self.stats['misses'] += 1
                return None
        except Exception:
            with self._lock:
                self.stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: bytes, ttl: int, metadata: Dict[str, Any] = None) -> bool:
        """设置缓存条目"""
        try:
            now = time.time()
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                expires_at=now + ttl,
                last_accessed=now,
                metadata=metadata or {}
            )
            
            redis_key = self._make_key(key)
            await self.redis.set(redis_key, pickle.dumps(entry), ex=ttl)
            
            with self._lock:
                self.stats['sets'] += 1
            return True
        except Exception:
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存条目"""
        try:
            redis_key = self._make_key(key)
            result = await self.redis.delete(redis_key)
            
            with self._lock:
                if result:
                    self.stats['deletes'] += 1
            return bool(result)
        except Exception:
            return False
    
    async def clear(self) -> bool:
        """清空缓存"""
        try:
            pattern = f"{self.prefix}:*"
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
            return True
        except Exception:
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **self.stats,
                'total_requests': total_requests,
                'hit_rate': hit_rate,
                'store_type': 'redis',
            }


class MultiLevelCacheStore(CacheStore):
    """多级缓存存储"""
    
    def __init__(self, l1_store: CacheStore, l2_store: CacheStore):
        self.l1_store = l1_store  # 一级缓存（通常是内存）
        self.l2_store = l2_store  # 二级缓存（通常是Redis）
        self.stats = {
            'l1_hits': 0,
            'l2_hits': 0,
            'misses': 0,
            'sets': 0,
        }
        self._lock = threading.Lock()
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        # 先查L1缓存
        entry = await self.l1_store.get(key)
        if entry:
            with self._lock:
                self.stats['l1_hits'] += 1
            return entry
        
        # 再查L2缓存
        entry = await self.l2_store.get(key)
        if entry:
            # 回填到L1缓存
            ttl = int(entry.expires_at - time.time())
            if ttl > 0:
                await self.l1_store.set(key, entry.value, ttl, entry.metadata)
            
            with self._lock:
                self.stats['l2_hits'] += 1
            return entry
        
        with self._lock:
            self.stats['misses'] += 1
        return None
    
    async def set(self, key: str, value: bytes, ttl: int, metadata: Dict[str, Any] = None) -> bool:
        """设置缓存条目"""
        # 同时设置L1和L2缓存
        l1_success = await self.l1_store.set(key, value, ttl, metadata)
        l2_success = await self.l2_store.set(key, value, ttl, metadata)
        
        with self._lock:
            self.stats['sets'] += 1
        
        return l1_success or l2_success
    
    async def delete(self, key: str) -> bool:
        """删除缓存条目"""
        l1_result = await self.l1_store.delete(key)
        l2_result = await self.l2_store.delete(key)
        return l1_result or l2_result
    
    async def clear(self) -> bool:
        """清空缓存"""
        l1_result = await self.l1_store.clear()
        l2_result = await self.l2_store.clear()
        return l1_result and l2_result
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        l1_stats = await self.l1_store.get_stats()
        l2_stats = await self.l2_store.get_stats()
        
        with self._lock:
            total_requests = self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['misses']
            l1_hit_rate = (self.stats['l1_hits'] / total_requests * 100) if total_requests > 0 else 0
            l2_hit_rate = (self.stats['l2_hits'] / total_requests * 100) if total_requests > 0 else 0
            total_hit_rate = ((self.stats['l1_hits'] + self.stats['l2_hits']) / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **self.stats,
                'total_requests': total_requests,
                'l1_hit_rate': l1_hit_rate,
                'l2_hit_rate': l2_hit_rate,
                'total_hit_rate': total_hit_rate,
                'l1_stats': l1_stats,
                'l2_stats': l2_stats,
            }


class CacheControl:
    """缓存控制器"""
    
    def __init__(self, store: CacheStore):
        self.store = store
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """按模式失效缓存"""
        # 这里需要根据存储类型实现模式匹配删除
        # 简化实现，实际需要更复杂的逻辑
        return 0
    
    async def warm_cache(self, entries: List[tuple[str, bytes, int]]) -> int:
        """缓存预热"""
        warmed = 0
        for key, value, ttl in entries:
            success = await self.store.set(key, value, ttl)
            if success:
                warmed += 1
        return warmed


class CacheInvalidator:
    """缓存失效器"""
    
    def __init__(self, store: CacheStore):
        self.store = store
        self.invalidation_rules: Dict[str, List[str]] = {}
    
    def add_invalidation_rule(self, trigger_pattern: str, target_patterns: List[str]) -> None:
        """添加失效规则"""
        self.invalidation_rules[trigger_pattern] = target_patterns
    
    async def invalidate_by_pattern(self, pattern: str) -> int:
        """按模式失效"""
        # 简化实现
        return 0


class CacheWarmer:
    """缓存预热器"""
    
    def __init__(self, store: CacheStore):
        self.store = store
        self.warm_rules: List[Dict[str, Any]] = []
    
    def add_warm_rule(self, rule: Dict[str, Any]) -> None:
        """添加预热规则"""
        self.warm_rules.append(rule)
    
    async def warm_cache(self) -> int:
        """执行缓存预热"""
        warmed = 0
        for rule in self.warm_rules:
            # 简化实现，实际需要根据规则生成缓存条目
            pass
        return warmed


@dataclass
class CachingResult:
    """缓存结果"""
    hit: bool
    cached: bool = False
    key: str = ""
    ttl: int = 0
    size: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CachingContext:
    """缓存上下文"""
    enabled: bool = True
    rule: Optional[CacheRule] = None
    key: str = ""
    strategy: CacheStrategy = CacheStrategy.CACHE_FIRST
    ttl: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CachingConfig:
    """缓存中间件配置"""
    enabled: bool = True
    default_strategy: CacheStrategy = CacheStrategy.CACHE_FIRST
    default_ttl: int = 300
    max_ttl: int = 86400
    policies: List[CachePolicy] = field(default_factory=list)
    skip_paths: List[str] = field(default_factory=list)
    skip_methods: List[str] = field(default_factory=lambda: ["POST", "PUT", "DELETE"])
    cache_store_config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CachingMiddleware(BaseMiddleware):
    """缓存中间件"""
    
    def __init__(self, config: MiddlewareConfig, cache_config: CachingConfig, store: Optional[CacheStore] = None):
        super().__init__(config)
        self.cache_config = cache_config
        self.store = store or MemoryCacheStore()
        self.policies: Dict[str, CachePolicy] = {}
        self.key_generator = CacheKeyGenerator()
        self.ttl_calculator = CacheTTLCalculator()
        self.cache_control = CacheControl(self.store)
        self.invalidator = CacheInvalidator(self.store)
        self.warmer = CacheWarmer(self.store)
        self._setup_policies()
    
    def _setup_policies(self) -> None:
        """设置缓存策略"""
        for policy in self.cache_config.policies:
            self.policies[policy.policy_id] = policy
    
    def _should_skip_caching(self, method: str, path: str) -> bool:
        """检查是否应该跳过缓存"""
        if method.upper() in self.cache_config.skip_methods:
            return True
        
        for skip_path in self.cache_config.skip_paths:
            if path.startswith(skip_path):
                return True
        
        return False
    
    def _find_applicable_policy(self, context: MiddlewareContext) -> Optional[CachePolicy]:
        """查找适用的策略"""
        if self.policies:
            return list(self.policies.values())[0]
        return None
    
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理缓存请求"""
        try:
            # 检查是否跳过缓存
            if self._should_skip_caching(context.request.method, context.request.path):
                context.set_data('caching_skipped', True)
                return MiddlewareResult.success_result()
            
            # 查找适用的策略
            policy = self._find_applicable_policy(context)
            if policy:
                rule = policy.find_matching_rule(context.request.method, context.request.path)
            else:
                rule = None
            
            if not rule:
                context.set_data('caching_not_applicable', True)
                return MiddlewareResult.success_result()
            
            # 生成缓存键
            cache_key = self.key_generator.generate_key(context, rule)
            
            # 设置缓存上下文
            cache_context = CachingContext(
                enabled=True,
                rule=rule,
                key=cache_key,
                strategy=rule.cache_strategy,
                ttl=rule.ttl,
            )
            context.set_data('caching_context', cache_context)
            
            # 根据策略处理缓存
            if rule.cache_strategy == CacheStrategy.NO_CACHE:
                return MiddlewareResult.success_result()
            elif rule.cache_strategy == CacheStrategy.CACHE_ONLY:
                return await self._handle_cache_only(context, cache_context)
            elif rule.cache_strategy == CacheStrategy.CACHE_FIRST:
                return await self._handle_cache_first(context, cache_context)
            elif rule.cache_strategy == CacheStrategy.NETWORK_FIRST:
                return await self._handle_network_first(context, cache_context)
            elif rule.cache_strategy == CacheStrategy.STALE_WHILE_REVALIDATE:
                return await self._handle_stale_while_revalidate(context, cache_context)
            
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    async def _handle_cache_only(self, context: MiddlewareContext, cache_context: CachingContext) -> MiddlewareResult:
        """处理仅缓存策略"""
        entry = await self.store.get(cache_context.key)
        if entry:
            # 缓存命中
            context.set_data('caching_result', CachingResult(hit=True, key=cache_context.key))
            return MiddlewareResult.stop_result(
                status_code=200,
                body=entry.value,
                headers={'X-Cache': 'HIT'}
            )
        else:
            # 缓存未命中
            context.set_data('caching_result', CachingResult(hit=False, key=cache_context.key))
            return MiddlewareResult.stop_result(
                status_code=404,
                body=b'{"error": "Resource not found in cache"}',
                headers={'X-Cache': 'MISS'}
            )
    
    async def _handle_cache_first(self, context: MiddlewareContext, cache_context: CachingContext) -> MiddlewareResult:
        """处理缓存优先策略"""
        entry = await self.store.get(cache_context.key)
        if entry:
            # 缓存命中
            context.set_data('caching_result', CachingResult(hit=True, key=cache_context.key))
            return MiddlewareResult.stop_result(
                status_code=200,
                body=entry.value,
                headers={'X-Cache': 'HIT'}
            )
        else:
            # 缓存未命中，继续处理请求
            context.set_data('caching_result', CachingResult(hit=False, key=cache_context.key))
            return MiddlewareResult.success_result()
    
    async def _handle_network_first(self, context: MiddlewareContext, cache_context: CachingContext) -> MiddlewareResult:
        """处理网络优先策略"""
        # 网络优先，总是继续处理请求
        context.set_data('caching_result', CachingResult(hit=False, key=cache_context.key))
        return MiddlewareResult.success_result()
    
    async def _handle_stale_while_revalidate(self, context: MiddlewareContext, cache_context: CachingContext) -> MiddlewareResult:
        """处理过期时重新验证策略"""
        entry = await self.store.get(cache_context.key)
        if entry:
            if not entry.is_expired():
                # 缓存有效
                context.set_data('caching_result', CachingResult(hit=True, key=cache_context.key))
                return MiddlewareResult.stop_result(
                    status_code=200,
                    body=entry.value,
                    headers={'X-Cache': 'HIT'}
                )
            elif entry.is_stale():
                # 缓存过期但在容忍范围内，返回缓存内容但标记需要重新验证
                context.set_data('caching_result', CachingResult(hit=True, key=cache_context.key))
                context.set_data('cache_needs_revalidation', True)
                return MiddlewareResult.stop_result(
                    status_code=200,
                    body=entry.value,
                    headers={'X-Cache': 'STALE'}
                )
        
        # 缓存未命中或完全过期
        context.set_data('caching_result', CachingResult(hit=False, key=cache_context.key))
        return MiddlewareResult.success_result()
    
    async def process_response(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理缓存响应"""
        try:
            # 检查是否跳过缓存
            if context.get_data('caching_skipped') or context.get_data('caching_not_applicable'):
                return MiddlewareResult.success_result()
            
            cache_context = context.get_data('caching_context')
            if not cache_context or not cache_context.enabled:
                return MiddlewareResult.success_result()
            
            caching_result = context.get_data('caching_result')
            if caching_result and caching_result.hit:
                # 已经从缓存返回，不需要再处理
                return MiddlewareResult.success_result()
            
            # 检查响应是否应该缓存
            if context.response and cache_context.rule:
                if cache_context.rule.should_cache_response(context.response.status_code):
                    # 计算TTL
                    ttl = self.ttl_calculator.calculate_ttl(context, cache_context.rule)
                    
                    # 缓存响应
                    if context.response.body:
                        success = await self.store.set(
                            cache_context.key,
                            context.response.body,
                            ttl,
                            {
                                'status_code': context.response.status_code,
                                'content_type': context.response.content_type,
                                'cached_at': time.time(),
                            }
                        )
                        
                        if success:
                            context.response.set_header('X-Cache', 'MISS')
                            context.response.set_header('X-Cache-TTL', str(ttl))
                            
                            # 更新缓存结果
                            if caching_result:
                                caching_result.cached = True
                                caching_result.ttl = ttl
                                caching_result.size = len(context.response.body)
            
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    def get_caching_context(self, context: MiddlewareContext) -> Optional[CachingContext]:
        """获取缓存上下文"""
        return context.get_data('caching_context')
    
    def get_caching_result(self, context: MiddlewareContext) -> Optional[CachingResult]:
        """获取缓存结果"""
        return context.get_data('caching_result')
    
    async def invalidate_cache(self, pattern: str) -> int:
        """失效缓存"""
        return await self.invalidator.invalidate_by_pattern(pattern)
    
    async def warm_cache(self) -> int:
        """预热缓存"""
        return await self.warmer.warm_cache()
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return await self.store.get_stats()
    
    def add_policy(self, policy: CachePolicy) -> bool:
        """添加缓存策略"""
        try:
            self.policies[policy.policy_id] = policy
            return True
        except Exception:
            return False
    
    def remove_policy(self, policy_id: str) -> bool:
        """移除缓存策略"""
        try:
            if policy_id in self.policies:
                del self.policies[policy_id]
                return True
            return False
        except Exception:
            return False


# 缓存异常类
class CachingError(Exception):
    """缓存基础异常"""
    pass


class CacheKeyError(CachingError):
    """缓存键异常"""
    pass


class CacheStoreError(CachingError):
    """缓存存储异常"""
    pass


class CacheInvalidationError(CachingError):
    """缓存失效异常"""
    pass