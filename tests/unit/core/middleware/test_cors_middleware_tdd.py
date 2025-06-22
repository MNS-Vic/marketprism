"""
CORS中间件TDD测试
专门用于提升cors_middleware.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from typing import Dict, List, Optional

# 导入CORS中间件模块
from core.middleware.cors_middleware import (
    CORSMiddleware, CORSRule, CORSPolicy, CORSConfig, CORSContext, CORSResult,
    AllowedOrigin, AllowedMethod, AllowedHeader, CORSMethod,
    OriginValidator, MethodValidator, HeaderValidator, CORSValidator
)
from core.middleware.middleware_framework import MiddlewareConfig, MiddlewareType, MiddlewareContext


class TestAllowedOrigin:
    """测试允许的源"""
    
    def test_allowed_origin_creation(self):
        """测试：允许源创建"""
        origin = AllowedOrigin(
            origin="https://example.com",
            pattern_type="exact",
            description="示例网站"
        )
        
        assert origin.origin == "https://example.com"
        assert origin.pattern_type == "exact"
        assert origin.description == "示例网站"
        
    def test_allowed_origin_exact_match(self):
        """测试：精确匹配"""
        origin = AllowedOrigin("https://example.com", "exact")
        
        assert origin.matches("https://example.com") is True
        assert origin.matches("https://other.com") is False
        assert origin.matches("http://example.com") is False
        
    def test_allowed_origin_wildcard_match(self):
        """测试：通配符匹配"""
        origin = AllowedOrigin("https://*.example.com", "wildcard")
        
        assert origin.matches("https://api.example.com") is True
        assert origin.matches("https://www.example.com") is True
        assert origin.matches("https://example.com") is False  # 不匹配根域名
        assert origin.matches("https://other.com") is False
        
    def test_allowed_origin_regex_match(self):
        """测试：正则表达式匹配"""
        origin = AllowedOrigin(r"https://.*\.example\.com", "regex")
        
        assert origin.matches("https://api.example.com") is True
        assert origin.matches("https://www.example.com") is True
        assert origin.matches("https://other.com") is False
        
    def test_allowed_origin_invalid_pattern_type(self):
        """测试：无效模式类型"""
        origin = AllowedOrigin("https://example.com", "invalid")
        
        assert origin.matches("https://example.com") is False


class TestAllowedMethod:
    """测试允许的方法"""
    
    def test_allowed_method_creation(self):
        """测试：允许方法创建"""
        method = AllowedMethod(
            method=CORSMethod.GET,
            description="GET请求"
        )
        
        assert method.method == CORSMethod.GET
        assert method.description == "GET请求"
        assert str(method) == "GET"


class TestAllowedHeader:
    """测试允许的头部"""
    
    def test_allowed_header_creation(self):
        """测试：允许头部创建"""
        header = AllowedHeader(
            header="Content-Type",
            description="内容类型",
            case_sensitive=False
        )
        
        assert header.header == "Content-Type"
        assert header.description == "内容类型"
        assert header.case_sensitive is False
        
    def test_allowed_header_case_insensitive_match(self):
        """测试：不区分大小写匹配"""
        header = AllowedHeader("Content-Type", case_sensitive=False)
        
        assert header.matches("Content-Type") is True
        assert header.matches("content-type") is True
        assert header.matches("CONTENT-TYPE") is True
        assert header.matches("Authorization") is False
        
    def test_allowed_header_case_sensitive_match(self):
        """测试：区分大小写匹配"""
        header = AllowedHeader("Content-Type", case_sensitive=True)
        
        assert header.matches("Content-Type") is True
        assert header.matches("content-type") is False
        assert header.matches("CONTENT-TYPE") is False


class TestCORSRule:
    """测试CORS规则"""
    
    def setup_method(self):
        """设置测试方法"""
        self.rule = CORSRule(
            rule_id="test_rule",
            name="测试规则",
            description="测试用CORS规则",
            allowed_origins=[
                AllowedOrigin("https://example.com", "exact"),
                AllowedOrigin("https://*.api.com", "wildcard")
            ],
            allowed_methods=[
                AllowedMethod(CORSMethod.GET),
                AllowedMethod(CORSMethod.POST)
            ],
            allowed_headers=[
                AllowedHeader("Content-Type"),
                AllowedHeader("Authorization")
            ],
            exposed_headers=["X-Total-Count", "X-Page-Count"],
            allow_credentials=True,
            max_age=3600,
            path_pattern="/api/*"
        )
        
    def test_cors_rule_creation(self):
        """测试：CORS规则创建"""
        assert self.rule.rule_id == "test_rule"
        assert self.rule.name == "测试规则"
        assert self.rule.description == "测试用CORS规则"
        assert len(self.rule.allowed_origins) == 2
        assert len(self.rule.allowed_methods) == 2
        assert len(self.rule.allowed_headers) == 2
        assert self.rule.exposed_headers == ["X-Total-Count", "X-Page-Count"]
        assert self.rule.allow_credentials is True
        assert self.rule.max_age == 3600
        assert self.rule.path_pattern == "/api/*"
        
    def test_cors_rule_defaults(self):
        """测试：CORS规则默认值"""
        rule = CORSRule(rule_id="basic", name="基础规则")
        
        assert rule.rule_id == "basic"
        assert rule.name == "基础规则"
        assert rule.description == ""
        assert rule.allowed_origins == []
        assert rule.allowed_methods == []
        assert rule.allowed_headers == []
        assert rule.exposed_headers == []
        assert rule.allow_credentials is False
        assert rule.max_age is None
        assert rule.path_pattern == "*"
        assert rule.enabled is True
        assert rule.priority == 0
        
    def test_cors_rule_matches_path(self):
        """测试：CORS规则路径匹配"""
        # 通配符规则
        wildcard_rule = CORSRule(rule_id="wildcard", name="通配符", path_pattern="*")
        assert wildcard_rule.matches_path("/any/path") is True
        
        # API路径规则
        api_rule = CORSRule(rule_id="api", name="API", path_pattern="/api/*")
        assert api_rule.matches_path("/api/users") is True
        assert api_rule.matches_path("/api/users/123") is True
        assert api_rule.matches_path("/api") is True
        assert api_rule.matches_path("/public/info") is False
        
        # 精确匹配规则
        exact_rule = CORSRule(rule_id="exact", name="精确", path_pattern="/api/health")
        assert exact_rule.matches_path("/api/health") is True
        assert exact_rule.matches_path("/api/health/check") is False
        
    def test_cors_rule_is_origin_allowed(self):
        """测试：CORS规则源检查"""
        assert self.rule.is_origin_allowed("https://example.com") is True
        assert self.rule.is_origin_allowed("https://test.api.com") is True
        assert self.rule.is_origin_allowed("https://other.com") is False
        
    def test_cors_rule_is_method_allowed(self):
        """测试：CORS规则方法检查"""
        assert self.rule.is_method_allowed("GET") is True
        assert self.rule.is_method_allowed("POST") is True
        assert self.rule.is_method_allowed("get") is True  # 不区分大小写
        assert self.rule.is_method_allowed("DELETE") is False
        
    def test_cors_rule_is_header_allowed(self):
        """测试：CORS规则头部检查"""
        assert self.rule.is_header_allowed("Content-Type") is True
        assert self.rule.is_header_allowed("Authorization") is True
        assert self.rule.is_header_allowed("content-type") is True  # 不区分大小写
        assert self.rule.is_header_allowed("X-Custom-Header") is False
        
    def test_cors_rule_get_strings(self):
        """测试：CORS规则字符串获取"""
        methods_str = self.rule.get_allowed_methods_string()
        assert "GET" in methods_str
        assert "POST" in methods_str
        
        headers_str = self.rule.get_allowed_headers_string()
        assert "Content-Type" in headers_str
        assert "Authorization" in headers_str
        
        exposed_str = self.rule.get_exposed_headers_string()
        assert "X-Total-Count" in exposed_str
        assert "X-Page-Count" in exposed_str


class TestCORSPolicy:
    """测试CORS策略"""
    
    def setup_method(self):
        """设置测试方法"""
        self.policy = CORSPolicy(
            policy_id="test_policy",
            name="测试策略",
            description="测试用CORS策略"
        )
        
    def test_cors_policy_creation(self):
        """测试：CORS策略创建"""
        assert self.policy.policy_id == "test_policy"
        assert self.policy.name == "测试策略"
        assert self.policy.description == "测试用CORS策略"
        assert self.policy.rules == []
        assert self.policy.default_rule is None
        assert self.policy.strict_mode is True
        
    def test_add_remove_rule(self):
        """测试：添加和移除规则"""
        rule = CORSRule(rule_id="test_rule", name="测试规则")
        
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
        high_priority_rule = CORSRule(
            rule_id="high_priority",
            name="高优先级",
            path_pattern="/api/important/*",
            allowed_origins=[AllowedOrigin("https://example.com", "exact")],
            priority=100
        )
        
        low_priority_rule = CORSRule(
            rule_id="low_priority",
            name="低优先级",
            path_pattern="/api/*",
            allowed_origins=[AllowedOrigin("https://example.com", "exact")],
            priority=10
        )
        
        default_rule = CORSRule(
            rule_id="default",
            name="默认规则",
            path_pattern="*",
            allowed_origins=[AllowedOrigin("*", "wildcard")]
        )
        
        self.policy.add_rule(low_priority_rule)
        self.policy.add_rule(high_priority_rule)
        self.policy.default_rule = default_rule
        
        # 测试高优先级匹配
        matched = self.policy.find_matching_rule("https://example.com", "/api/important/data")
        assert matched == high_priority_rule
        
        # 测试低优先级匹配
        matched = self.policy.find_matching_rule("https://example.com", "/api/users")
        assert matched == low_priority_rule
        
        # 测试默认规则
        matched = self.policy.find_matching_rule("https://other.com", "/public/info")
        assert matched == default_rule


class TestOriginValidator:
    """测试源验证器"""

    def setup_method(self):
        """设置测试方法"""
        self.validator = OriginValidator()

    def test_origin_validator_initialization(self):
        """测试：源验证器初始化"""
        assert "http" in self.validator.allowed_schemes
        assert "https" in self.validator.allowed_schemes
        assert len(self.validator.blocked_origins) == 0

    def test_validate_origin_valid(self):
        """测试：验证有效源"""
        assert self.validator.validate_origin("https://example.com") is True
        assert self.validator.validate_origin("http://localhost:3000") is True
        assert self.validator.validate_origin("https://api.example.com:8080") is True

    def test_validate_origin_invalid(self):
        """测试：验证无效源"""
        assert self.validator.validate_origin("") is False
        assert self.validator.validate_origin("ftp://example.com") is False
        assert self.validator.validate_origin("invalid-url") is False
        assert self.validator.validate_origin("https://") is False

    def test_blocked_origins(self):
        """测试：阻止的源"""
        origin = "https://malicious.com"

        # 添加到阻止列表
        self.validator.add_blocked_origin(origin)
        assert self.validator.validate_origin(origin) is False

        # 从阻止列表移除
        self.validator.remove_blocked_origin(origin)
        assert self.validator.validate_origin(origin) is True


class TestMethodValidator:
    """测试方法验证器"""

    def setup_method(self):
        """设置测试方法"""
        self.validator = MethodValidator()

    def test_method_validator_initialization(self):
        """测试：方法验证器初始化"""
        assert CORSMethod.GET in self.validator.safe_methods
        assert CORSMethod.HEAD in self.validator.safe_methods
        assert CORSMethod.OPTIONS in self.validator.safe_methods
        assert CORSMethod.POST in self.validator.complex_methods
        assert CORSMethod.PUT in self.validator.complex_methods
        assert CORSMethod.DELETE in self.validator.complex_methods

    def test_is_safe_method(self):
        """测试：安全方法检查"""
        assert self.validator.is_safe_method("GET") is True
        assert self.validator.is_safe_method("HEAD") is True
        assert self.validator.is_safe_method("OPTIONS") is True
        assert self.validator.is_safe_method("POST") is False
        assert self.validator.is_safe_method("INVALID") is False

    def test_is_complex_method(self):
        """测试：复杂方法检查"""
        assert self.validator.is_complex_method("POST") is True
        assert self.validator.is_complex_method("PUT") is True
        assert self.validator.is_complex_method("DELETE") is True
        assert self.validator.is_complex_method("GET") is False
        assert self.validator.is_complex_method("INVALID") is False

    def test_requires_preflight(self):
        """测试：预检需求检查"""
        assert self.validator.requires_preflight("POST") is True
        assert self.validator.requires_preflight("PUT") is True
        assert self.validator.requires_preflight("DELETE") is True
        assert self.validator.requires_preflight("GET") is False


class TestHeaderValidator:
    """测试头部验证器"""

    def setup_method(self):
        """设置测试方法"""
        self.validator = HeaderValidator()

    def test_header_validator_initialization(self):
        """测试：头部验证器初始化"""
        assert "accept" in self.validator.simple_headers
        assert "accept-language" in self.validator.simple_headers
        assert "content-language" in self.validator.simple_headers
        assert "content-type" in self.validator.simple_headers

    def test_is_simple_header(self):
        """测试：简单头部检查"""
        assert self.validator.is_simple_header("Accept") is True
        assert self.validator.is_simple_header("accept") is True
        assert self.validator.is_simple_header("Content-Type") is True
        assert self.validator.is_simple_header("Authorization") is False
        assert self.validator.is_simple_header("X-Custom-Header") is False

    def test_requires_preflight_headers(self):
        """测试：头部预检需求检查"""
        simple_headers = ["Accept", "Content-Type"]
        complex_headers = ["Authorization", "X-Custom-Header"]
        mixed_headers = ["Accept", "Authorization"]

        assert self.validator.requires_preflight(simple_headers) is False
        assert self.validator.requires_preflight(complex_headers) is True
        assert self.validator.requires_preflight(mixed_headers) is True


class TestCORSValidator:
    """测试CORS验证器"""

    def setup_method(self):
        """设置测试方法"""
        self.validator = CORSValidator()

    def test_cors_validator_initialization(self):
        """测试：CORS验证器初始化"""
        assert self.validator.origin_validator is not None
        assert self.validator.method_validator is not None
        assert self.validator.header_validator is not None

    def test_validate_simple_request(self):
        """测试：验证简单请求"""
        assert self.validator.validate_simple_request("https://example.com", "GET") is True
        assert self.validator.validate_simple_request("https://example.com", "POST") is False
        assert self.validator.validate_simple_request("invalid-origin", "GET") is False

    def test_validate_preflight_request(self):
        """测试：验证预检请求"""
        assert self.validator.validate_preflight_request("https://example.com", "POST", []) is True
        assert self.validator.validate_preflight_request("https://example.com", "GET", []) is False
        assert self.validator.validate_preflight_request("invalid-origin", "POST", []) is False

    def test_requires_preflight(self):
        """测试：预检需求检查"""
        assert self.validator.requires_preflight("POST", []) is True
        assert self.validator.requires_preflight("GET", ["Authorization"]) is True
        assert self.validator.requires_preflight("GET", ["Accept"]) is False


class TestCORSResult:
    """测试CORS结果"""

    def test_cors_result_creation(self):
        """测试：CORS结果创建"""
        result = CORSResult(
            allowed=True,
            is_preflight=False,
            response_headers={"Access-Control-Allow-Origin": "*"},
            status_code=200,
            reason="Success"
        )

        assert result.allowed is True
        assert result.is_preflight is False
        assert result.response_headers == {"Access-Control-Allow-Origin": "*"}
        assert result.status_code == 200
        assert result.reason == "Success"

    def test_cors_result_allow(self):
        """测试：CORS允许结果"""
        headers = {"Access-Control-Allow-Origin": "https://example.com"}
        result = CORSResult.allow(headers, is_preflight=True)

        assert result.allowed is True
        assert result.is_preflight is True
        assert result.response_headers == headers
        assert result.status_code == 200

    def test_cors_result_deny(self):
        """测试：CORS拒绝结果"""
        result = CORSResult.deny("Origin not allowed", status_code=403)

        assert result.allowed is False
        assert result.reason == "Origin not allowed"
        assert result.status_code == 403


class TestCORSContext:
    """测试CORS上下文"""

    def test_cors_context_creation(self):
        """测试：CORS上下文创建"""
        context = CORSContext(
            origin="https://example.com",
            method="POST",
            requested_headers=["Content-Type", "Authorization"],
            is_preflight=True,
            is_cors_request=True
        )

        assert context.origin == "https://example.com"
        assert context.method == "POST"
        assert context.requested_headers == ["Content-Type", "Authorization"]
        assert context.is_preflight is True
        assert context.is_cors_request is True

    def test_cors_context_defaults(self):
        """测试：CORS上下文默认值"""
        context = CORSContext()

        assert context.origin == ""
        assert context.method == ""
        assert context.requested_headers == []
        assert context.is_preflight is False
        assert context.is_cors_request is False
        assert context.metadata == {}
