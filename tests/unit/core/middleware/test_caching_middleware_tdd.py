"""
缓存中间件TDD测试
专门用于提升caching_middleware.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import time
import json
import pickle
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Optional

# 导入缓存中间件模块
from core.middleware.caching_middleware import (
    CachingMiddleware, CacheRule, CachePolicy, CacheKeyGenerator,
    CacheTTLCalculator, CacheEntry, CacheStore, MemoryCacheStore,
    RedisCacheStore, MultiLevelCacheStore, CacheStrategy, CacheScope
)
from core.middleware.middleware_framework import MiddlewareConfig, MiddlewareType, MiddlewareContext


class TestCacheRule:
    """测试缓存规则"""
    
    def test_cache_rule_creation(self):
        """测试：缓存规则创建"""
        rule = CacheRule(
            rule_id="api_cache",
            name="API缓存规则",
            description="API接口缓存",
            path_pattern="/api/*",
            method_pattern="GET",
            cache_strategy=CacheStrategy.CACHE_FIRST,
            cache_scope=CacheScope.GLOBAL,
            ttl=300,
            vary_headers=["Authorization", "Accept-Language"]
        )
        
        assert rule.rule_id == "api_cache"
        assert rule.name == "API缓存规则"
        assert rule.description == "API接口缓存"
        assert rule.path_pattern == "/api/*"
        assert rule.method_pattern == "GET"
        assert rule.cache_strategy == CacheStrategy.CACHE_FIRST
        assert rule.cache_scope == CacheScope.GLOBAL
        assert rule.ttl == 300
        assert rule.vary_headers == ["Authorization", "Accept-Language"]
        
    def test_cache_rule_defaults(self):
        """测试：缓存规则默认值"""
        rule = CacheRule(rule_id="basic_rule", name="基础规则")
        
        assert rule.rule_id == "basic_rule"
        assert rule.name == "基础规则"
        assert rule.description == ""
        assert rule.path_pattern == "*"
        assert rule.method_pattern == "*"
        assert rule.cache_strategy == CacheStrategy.CACHE_FIRST
        assert rule.cache_scope == CacheScope.GLOBAL
        assert rule.ttl == 300
        assert rule.vary_headers == []
        assert rule.enabled is True
        assert rule.priority == 0
        
    def test_cache_rule_matches_request(self):
        """测试：缓存规则请求匹配"""
        # 通配符规则
        wildcard_rule = CacheRule(
            rule_id="wildcard",
            name="通配符规则",
            path_pattern="*",
            method_pattern="*"
        )
        
        assert wildcard_rule.matches_request("GET", "/any/path") is True
        assert wildcard_rule.matches_request("POST", "/api/users") is True
        
        # API路径规则
        api_rule = CacheRule(
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
        exact_rule = CacheRule(
            rule_id="exact",
            name="精确规则",
            path_pattern="/api/health",
            method_pattern="GET"
        )
        
        assert exact_rule.matches_request("GET", "/api/health") is True
        assert exact_rule.matches_request("GET", "/api/health/check") is False
        assert exact_rule.matches_request("POST", "/api/health") is False
        
    def test_cache_rule_should_cache_response(self):
        """测试：缓存规则响应缓存判断"""
        rule = CacheRule(rule_id="test", name="测试规则")
        
        # 默认缓存成功响应
        assert rule.should_cache_response(200) is True
        assert rule.should_cache_response(301) is True
        assert rule.should_cache_response(302) is True
        assert rule.should_cache_response(304) is True
        
        # 不缓存错误响应
        assert rule.should_cache_response(400) is False
        assert rule.should_cache_response(404) is False
        assert rule.should_cache_response(500) is False
        
        # 自定义缓存状态码
        custom_rule = CacheRule(
            rule_id="custom",
            name="自定义规则",
            cache_conditions={"status_codes": [200, 404]}
        )
        
        assert custom_rule.should_cache_response(200) is True
        assert custom_rule.should_cache_response(404) is True
        assert custom_rule.should_cache_response(500) is False


class TestCachePolicy:
    """测试缓存策略"""
    
    def setup_method(self):
        """设置测试方法"""
        self.policy = CachePolicy(
            policy_id="test_policy",
            name="测试策略",
            description="测试用缓存策略"
        )
        
    def test_cache_policy_creation(self):
        """测试：缓存策略创建"""
        assert self.policy.policy_id == "test_policy"
        assert self.policy.name == "测试策略"
        assert self.policy.description == "测试用缓存策略"
        assert self.policy.rules == []
        assert self.policy.default_rule is None
        assert self.policy.global_ttl is None
        
    def test_add_remove_rule(self):
        """测试：添加和移除规则"""
        rule = CacheRule(rule_id="test_rule", name="测试规则")
        
        # 添加规则
        self.policy.add_rule(rule)
        assert len(self.policy.rules) == 1
        assert self.policy.rules[0] == rule
        
        # 移除规则
        result = self.policy.remove_rule("test_rule")
        assert result is True
        assert len(self.policy.rules) == 0
        
        # 移除不存在的规则
        result = self.policy.remove_rule("non_existent")
        assert result is False
        
    def test_find_matching_rule(self):
        """测试：查找匹配规则"""
        # 添加多个规则
        high_priority_rule = CacheRule(
            rule_id="high_priority",
            name="高优先级",
            path_pattern="/api/important/*",
            priority=100
        )
        
        low_priority_rule = CacheRule(
            rule_id="low_priority",
            name="低优先级",
            path_pattern="/api/*",
            priority=10
        )
        
        default_rule = CacheRule(
            rule_id="default",
            name="默认规则",
            path_pattern="*"
        )
        
        self.policy.add_rule(low_priority_rule)
        self.policy.add_rule(high_priority_rule)
        self.policy.default_rule = default_rule
        
        # 测试高优先级匹配
        matched = self.policy.find_matching_rule("GET", "/api/important/data")
        assert matched == high_priority_rule
        
        # 测试低优先级匹配
        matched = self.policy.find_matching_rule("GET", "/api/users")
        assert matched == low_priority_rule
        
        # 测试默认规则
        matched = self.policy.find_matching_rule("GET", "/public/info")
        assert matched == default_rule
        
        # 测试无匹配（禁用规则）
        high_priority_rule.enabled = False
        low_priority_rule.enabled = False
        matched = self.policy.find_matching_rule("GET", "/api/users")
        assert matched == default_rule


class TestCacheKeyGenerator:
    """测试缓存键生成器"""
    
    def setup_method(self):
        """设置测试方法"""
        self.generator = CacheKeyGenerator(prefix="test_cache")
        
    def test_cache_key_generator_initialization(self):
        """测试：缓存键生成器初始化"""
        assert self.generator.prefix == "test_cache"
        
        # 测试默认前缀
        default_generator = CacheKeyGenerator()
        assert default_generator.prefix == "marketprism_cache"
        
    def test_generate_global_cache_key(self):
        """测试：生成全局缓存键"""
        # 创建模拟上下文
        context = Mock(spec=MiddlewareContext)
        context.request = Mock()
        context.request.method = "GET"
        context.request.path = "/api/users"
        context.request.query_params = {}
        context.request.get_header = Mock(return_value=None)
        
        rule = CacheRule(
            rule_id="global_rule",
            name="全局规则",
            cache_scope=CacheScope.GLOBAL
        )
        
        key = self.generator.generate_key(context, rule)
        
        assert key.startswith("test_cache:global")
        assert "GET" in key
        assert "api_users" in key
        
    def test_generate_user_cache_key(self):
        """测试：生成用户缓存键"""
        context = Mock(spec=MiddlewareContext)
        context.request = Mock()
        context.request.method = "GET"
        context.request.path = "/api/profile"
        context.request.query_params = {}
        context.request.get_header = Mock(return_value=None)
        context.get_user_data = Mock(return_value="user123")
        
        rule = CacheRule(
            rule_id="user_rule",
            name="用户规则",
            cache_scope=CacheScope.USER
        )
        
        key = self.generator.generate_key(context, rule)
        
        assert "user_user123" in key
        
    def test_generate_cache_key_with_query_params(self):
        """测试：生成带查询参数的缓存键"""
        context = Mock(spec=MiddlewareContext)
        context.request = Mock()
        context.request.method = "GET"
        context.request.path = "/api/search"
        context.request.query_params = {"q": "test", "page": "1"}
        context.request.get_header = Mock(return_value=None)
        
        rule = CacheRule(
            rule_id="search_rule",
            name="搜索规则",
            cache_scope=CacheScope.GLOBAL
        )
        
        key = self.generator.generate_key(context, rule)
        
        assert "query_" in key
        
    def test_generate_cache_key_with_vary_headers(self):
        """测试：生成带变化头部的缓存键"""
        context = Mock(spec=MiddlewareContext)
        context.request = Mock()
        context.request.method = "GET"
        context.request.path = "/api/data"
        context.request.query_params = {}
        context.request.get_header = Mock(side_effect=lambda h: "en-US" if h == "Accept-Language" else None)
        
        rule = CacheRule(
            rule_id="vary_rule",
            name="变化规则",
            cache_scope=CacheScope.GLOBAL,
            vary_headers=["Accept-Language"]
        )
        
        key = self.generator.generate_key(context, rule)
        
        assert "vary_" in key
        
    def test_hash_methods(self):
        """测试：哈希方法"""
        # 测试字典哈希
        data = {"key1": "value1", "key2": "value2"}
        hash1 = self.generator._hash_dict(data)
        hash2 = self.generator._hash_dict(data)
        assert hash1 == hash2
        assert len(hash1) == 8
        
        # 测试字符串哈希
        string = "test_string"
        hash1 = self.generator._hash_string(string)
        hash2 = self.generator._hash_string(string)
        assert hash1 == hash2
        assert len(hash1) == 8


class TestCacheTTLCalculator:
    """测试缓存TTL计算器"""
    
    def setup_method(self):
        """设置测试方法"""
        self.calculator = CacheTTLCalculator()
        
    def test_ttl_calculator_initialization(self):
        """测试：TTL计算器初始化"""
        assert self.calculator.default_ttl == 300
        assert self.calculator.max_ttl == 86400
        
    def test_calculate_ttl_from_rule(self):
        """测试：从规则计算TTL"""
        context = Mock(spec=MiddlewareContext)
        context.response = None
        
        rule = CacheRule(
            rule_id="test_rule",
            name="测试规则",
            ttl=600
        )
        
        ttl = self.calculator.calculate_ttl(context, rule)
        assert ttl == 600
        
    def test_calculate_ttl_from_cache_control(self):
        """测试：从Cache-Control头计算TTL"""
        context = Mock(spec=MiddlewareContext)
        context.response = Mock()
        context.response.get_header = Mock(side_effect=lambda h: "max-age=1800" if h == "cache-control" else None)
        
        rule = CacheRule(rule_id="test", name="测试", ttl=300)
        
        ttl = self.calculator.calculate_ttl(context, rule)
        assert ttl == 1800
        
    def test_calculate_ttl_max_limit(self):
        """测试：TTL最大限制"""
        context = Mock(spec=MiddlewareContext)
        context.response = Mock()
        context.response.get_header = Mock(side_effect=lambda h: "max-age=100000" if h == "cache-control" else None)
        
        rule = CacheRule(rule_id="test", name="测试", ttl=300)
        
        ttl = self.calculator.calculate_ttl(context, rule)
        assert ttl == self.calculator.max_ttl  # 应该被限制为最大值
        
    def test_parse_cache_control_ttl(self):
        """测试：解析Cache-Control TTL"""
        # 正常情况
        ttl = self.calculator._parse_cache_control_ttl("max-age=3600")
        assert ttl == 3600
        
        # 多个指令
        ttl = self.calculator._parse_cache_control_ttl("public, max-age=1800, must-revalidate")
        assert ttl == 1800
        
        # 无max-age
        ttl = self.calculator._parse_cache_control_ttl("no-cache")
        assert ttl is None
        
        # 无效格式
        ttl = self.calculator._parse_cache_control_ttl("invalid")
        assert ttl is None


class TestCacheEntry:
    """测试缓存条目"""

    def test_cache_entry_creation(self):
        """测试：缓存条目创建"""
        now = time.time()
        entry = CacheEntry(
            key="test_key",
            value=b"test_value",
            created_at=now,
            expires_at=now + 300,
            last_accessed=now,
            access_count=0,
            metadata={"type": "test"}
        )

        assert entry.key == "test_key"
        assert entry.value == b"test_value"
        assert entry.created_at == now
        assert entry.expires_at == now + 300
        assert entry.last_accessed == now
        assert entry.access_count == 0
        assert entry.metadata == {"type": "test"}

    def test_cache_entry_is_expired(self):
        """测试：缓存条目过期检查"""
        now = time.time()

        # 未过期条目
        valid_entry = CacheEntry(
            key="valid",
            value=b"data",
            created_at=now,
            expires_at=now + 300,
            last_accessed=now
        )
        assert valid_entry.is_expired() is False

        # 已过期条目
        expired_entry = CacheEntry(
            key="expired",
            value=b"data",
            created_at=now - 600,
            expires_at=now - 300,
            last_accessed=now - 600
        )
        assert expired_entry.is_expired() is True

    def test_cache_entry_is_stale(self):
        """测试：缓存条目过期但可用检查"""
        now = time.time()

        # 新鲜条目
        fresh_entry = CacheEntry(
            key="fresh",
            value=b"data",
            created_at=now,
            expires_at=now + 300,
            last_accessed=now
        )
        assert fresh_entry.is_stale() is False

        # 过期但在允许范围内
        stale_entry = CacheEntry(
            key="stale",
            value=b"data",
            created_at=now - 400,
            expires_at=now - 30,  # 30秒前过期
            last_accessed=now - 400
        )
        assert stale_entry.is_stale(stale_threshold=60) is True

        # 过期太久
        too_old_entry = CacheEntry(
            key="too_old",
            value=b"data",
            created_at=now - 500,
            expires_at=now - 120,  # 120秒前过期
            last_accessed=now - 500
        )
        assert too_old_entry.is_stale(stale_threshold=60) is False

    def test_cache_entry_access(self):
        """测试：缓存条目访问记录"""
        entry = CacheEntry(
            key="test",
            value=b"data",
            created_at=time.time(),
            expires_at=time.time() + 300,
            last_accessed=time.time(),
            access_count=0
        )

        initial_access_time = entry.last_accessed
        initial_count = entry.access_count

        # 模拟访问
        time.sleep(0.01)  # 确保时间差异
        entry.access()

        assert entry.last_accessed > initial_access_time
        assert entry.access_count == initial_count + 1


class TestMemoryCacheStore:
    """测试内存缓存存储"""

    def setup_method(self):
        """设置测试方法"""
        self.store = MemoryCacheStore(max_size=10)

    def test_memory_cache_store_initialization(self):
        """测试：内存缓存存储初始化"""
        assert self.store.max_size == 10
        assert self.store.cache == {}
        assert 'hits' in self.store.stats
        assert 'misses' in self.store.stats
        assert 'sets' in self.store.stats
        assert 'deletes' in self.store.stats
        assert 'evictions' in self.store.stats

    @pytest.mark.asyncio
    async def test_memory_cache_set_get(self):
        """测试：内存缓存设置和获取"""
        # 设置缓存
        result = await self.store.set("test_key", b"test_value", 300)
        assert result is True
        assert self.store.stats['sets'] == 1

        # 获取缓存
        entry = await self.store.get("test_key")
        assert entry is not None
        assert entry.key == "test_key"
        assert entry.value == b"test_value"
        assert self.store.stats['hits'] == 1

        # 获取不存在的缓存
        entry = await self.store.get("non_existent")
        assert entry is None
        assert self.store.stats['misses'] == 1

    @pytest.mark.asyncio
    async def test_memory_cache_delete(self):
        """测试：内存缓存删除"""
        # 先设置缓存
        await self.store.set("test_key", b"test_value", 300)

        # 删除存在的缓存
        result = await self.store.delete("test_key")
        assert result is True
        assert self.store.stats['deletes'] == 1

        # 删除不存在的缓存
        result = await self.store.delete("non_existent")
        assert result is False

    @pytest.mark.asyncio
    async def test_memory_cache_clear(self):
        """测试：内存缓存清空"""
        # 设置多个缓存
        await self.store.set("key1", b"value1", 300)
        await self.store.set("key2", b"value2", 300)

        assert len(self.store.cache) == 2

        # 清空缓存
        result = await self.store.clear()
        assert result is True
        assert len(self.store.cache) == 0

    @pytest.mark.asyncio
    async def test_memory_cache_stats(self):
        """测试：内存缓存统计"""
        # 执行一些操作
        await self.store.set("key1", b"value1", 300)
        await self.store.get("key1")
        await self.store.get("non_existent")

        stats = await self.store.get_stats()

        assert stats['sets'] == 1
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['total_requests'] == 2
        assert stats['hit_rate'] == 50.0
        assert stats['cache_size'] == 1
        assert stats['max_size'] == 10

    @pytest.mark.asyncio
    async def test_memory_cache_expired_entry(self):
        """测试：内存缓存过期条目处理"""
        # 设置一个很短TTL的缓存
        await self.store.set("short_lived", b"value", 0.01)

        # 等待过期
        await asyncio.sleep(0.02)

        # 获取应该返回None并清理过期条目
        entry = await self.store.get("short_lived")
        assert entry is None
        assert "short_lived" not in self.store.cache
        assert self.store.stats['misses'] == 1
