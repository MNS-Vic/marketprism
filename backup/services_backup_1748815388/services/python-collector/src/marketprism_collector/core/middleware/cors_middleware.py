"""
MarketPrism CORS中间件

这个模块实现了企业级CORS（跨域资源共享）中间件，支持灵活的CORS策略配置、
预检请求处理和安全的跨域访问控制。

核心功能:
1. CORS策略：灵活的跨域策略配置
2. 源验证：安全的源域名验证
3. 方法控制：HTTP方法访问控制
4. 头部管理：请求和响应头部管理
5. 预检处理：OPTIONS预检请求处理
6. 凭证控制：跨域凭证传输控制
"""

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set
import threading
from urllib.parse import urlparse

from .middleware_framework import (
    BaseMiddleware, MiddlewareConfig, MiddlewareContext, MiddlewareResult,
    MiddlewareType, MiddlewarePriority
)


class CORSMethod(Enum):
    """CORS方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    TRACE = "TRACE"
    CONNECT = "CONNECT"


@dataclass
class AllowedOrigin:
    """允许的源"""
    origin: str
    pattern_type: str = "exact"           # exact/wildcard/regex
    description: str = ""
    
    def matches(self, origin: str) -> bool:
        """检查源是否匹配"""
        if self.pattern_type == "exact":
            return self.origin == origin
        elif self.pattern_type == "wildcard":
            # 简单通配符匹配
            pattern = self.origin.replace("*", ".*")
            return bool(re.match(f"^{pattern}$", origin))
        elif self.pattern_type == "regex":
            return bool(re.match(self.origin, origin))
        else:
            return False


@dataclass
class AllowedMethod:
    """允许的方法"""
    method: CORSMethod
    description: str = ""
    
    def __str__(self) -> str:
        return self.method.value


@dataclass
class AllowedHeader:
    """允许的头部"""
    header: str
    description: str = ""
    case_sensitive: bool = False
    
    def matches(self, header: str) -> bool:
        """检查头部是否匹配"""
        if self.case_sensitive:
            return self.header == header
        else:
            return self.header.lower() == header.lower()


@dataclass
class CORSRule:
    """CORS规则"""
    rule_id: str
    name: str
    description: str = ""
    allowed_origins: List[AllowedOrigin] = field(default_factory=list)
    allowed_methods: List[AllowedMethod] = field(default_factory=list)
    allowed_headers: List[AllowedHeader] = field(default_factory=list)
    exposed_headers: List[str] = field(default_factory=list)
    allow_credentials: bool = False
    max_age: Optional[int] = None         # 预检缓存时间（秒）
    path_pattern: str = "*"
    enabled: bool = True
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches_path(self, path: str) -> bool:
        """检查路径是否匹配"""
        if self.path_pattern == "*":
            return True
        return path.startswith(self.path_pattern)
    
    def is_origin_allowed(self, origin: str) -> bool:
        """检查源是否被允许"""
        for allowed_origin in self.allowed_origins:
            if allowed_origin.matches(origin):
                return True
        return False
    
    def is_method_allowed(self, method: str) -> bool:
        """检查方法是否被允许"""
        for allowed_method in self.allowed_methods:
            if allowed_method.method.value == method.upper():
                return True
        return False
    
    def is_header_allowed(self, header: str) -> bool:
        """检查头部是否被允许"""
        for allowed_header in self.allowed_headers:
            if allowed_header.matches(header):
                return True
        return False
    
    def get_allowed_methods_string(self) -> str:
        """获取允许的方法字符串"""
        return ", ".join([method.method.value for method in self.allowed_methods])
    
    def get_allowed_headers_string(self) -> str:
        """获取允许的头部字符串"""
        return ", ".join([header.header for header in self.allowed_headers])
    
    def get_exposed_headers_string(self) -> str:
        """获取暴露的头部字符串"""
        return ", ".join(self.exposed_headers)


@dataclass
class CORSPolicy:
    """CORS策略"""
    policy_id: str
    name: str
    description: str = ""
    rules: List[CORSRule] = field(default_factory=list)
    default_rule: Optional[CORSRule] = None
    strict_mode: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_rule(self, rule: CORSRule) -> None:
        """添加CORS规则"""
        self.rules.append(rule)
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除CORS规则"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                self.rules.remove(rule)
                return True
        return False
    
    def find_matching_rule(self, origin: str, path: str) -> Optional[CORSRule]:
        """查找匹配的规则"""
        # 按优先级排序
        sorted_rules = sorted([r for r in self.rules if r.enabled], 
                             key=lambda r: r.priority, reverse=True)
        
        for rule in sorted_rules:
            if rule.matches_path(path) and rule.is_origin_allowed(origin):
                return rule
        
        return self.default_rule


class OriginValidator:
    """源验证器"""
    
    def __init__(self):
        self.allowed_schemes = {"http", "https"}
        self.blocked_origins = set()
        self._lock = threading.Lock()
    
    def validate_origin(self, origin: str) -> bool:
        """验证源"""
        try:
            if not origin:
                return False
            
            # 检查是否被阻止
            if origin in self.blocked_origins:
                return False
            
            # 解析URL
            parsed = urlparse(origin)
            
            # 验证协议
            if parsed.scheme not in self.allowed_schemes:
                return False
            
            # 验证主机名
            if not parsed.netloc:
                return False
            
            return True
            
        except Exception:
            return False
    
    def add_blocked_origin(self, origin: str) -> None:
        """添加阻止的源"""
        with self._lock:
            self.blocked_origins.add(origin)
    
    def remove_blocked_origin(self, origin: str) -> None:
        """移除阻止的源"""
        with self._lock:
            self.blocked_origins.discard(origin)


class MethodValidator:
    """方法验证器"""
    
    def __init__(self):
        self.safe_methods = {CORSMethod.GET, CORSMethod.HEAD, CORSMethod.OPTIONS}
        self.complex_methods = {CORSMethod.POST, CORSMethod.PUT, CORSMethod.DELETE, CORSMethod.PATCH}
    
    def is_safe_method(self, method: str) -> bool:
        """检查是否为安全方法"""
        try:
            cors_method = CORSMethod(method.upper())
            return cors_method in self.safe_methods
        except ValueError:
            return False
    
    def is_complex_method(self, method: str) -> bool:
        """检查是否为复杂方法"""
        try:
            cors_method = CORSMethod(method.upper())
            return cors_method in self.complex_methods
        except ValueError:
            return False
    
    def requires_preflight(self, method: str) -> bool:
        """检查是否需要预检"""
        return self.is_complex_method(method)


class HeaderValidator:
    """头部验证器"""
    
    def __init__(self):
        # 简单头部（不需要预检）
        self.simple_headers = {
            "accept",
            "accept-language",
            "content-language",
            "content-type",
        }
        
        # 简单内容类型
        self.simple_content_types = {
            "application/x-www-form-urlencoded",
            "multipart/form-data",
            "text/plain",
        }
    
    def is_simple_header(self, header: str) -> bool:
        """检查是否为简单头部"""
        header_lower = header.lower()
        
        if header_lower in self.simple_headers:
            return True
        
        # 检查Content-Type的值
        if header_lower == "content-type":
            # 这里需要检查实际的Content-Type值，暂时返回True
            return True
        
        return False
    
    def requires_preflight(self, headers: List[str]) -> bool:
        """检查头部是否需要预检"""
        for header in headers:
            if not self.is_simple_header(header):
                return True
        return False


class CORSValidator:
    """CORS验证器"""
    
    def __init__(self):
        self.origin_validator = OriginValidator()
        self.method_validator = MethodValidator()
        self.header_validator = HeaderValidator()
    
    def validate_simple_request(self, origin: str, method: str) -> bool:
        """验证简单请求"""
        return (self.origin_validator.validate_origin(origin) and 
                self.method_validator.is_safe_method(method))
    
    def validate_preflight_request(self, origin: str, method: str, headers: List[str]) -> bool:
        """验证预检请求"""
        return (self.origin_validator.validate_origin(origin) and
                self.method_validator.is_complex_method(method))
    
    def requires_preflight(self, method: str, headers: List[str]) -> bool:
        """检查是否需要预检"""
        return (self.method_validator.requires_preflight(method) or
                self.header_validator.requires_preflight(headers))


@dataclass
class CORSResult:
    """CORS处理结果"""
    allowed: bool
    is_preflight: bool = False
    response_headers: Dict[str, str] = field(default_factory=dict)
    status_code: int = 200
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def allow(cls, response_headers: Dict[str, str], is_preflight: bool = False, **kwargs) -> 'CORSResult':
        """创建允许结果"""
        return cls(allowed=True, is_preflight=is_preflight, response_headers=response_headers, **kwargs)
    
    @classmethod
    def deny(cls, reason: str = "", status_code: int = 403, **kwargs) -> 'CORSResult':
        """创建拒绝结果"""
        return cls(allowed=False, reason=reason, status_code=status_code, **kwargs)


@dataclass
class CORSContext:
    """CORS上下文"""
    origin: str = ""
    method: str = ""
    requested_headers: List[str] = field(default_factory=list)
    is_preflight: bool = False
    is_cors_request: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CORSConfig:
    """CORS中间件配置"""
    enabled: bool = True
    policies: List[CORSPolicy] = field(default_factory=list)
    default_policy: Optional[CORSPolicy] = None
    strict_origin_validation: bool = True
    allow_null_origin: bool = False
    max_age_default: int = 86400          # 默认预检缓存时间（秒）
    skip_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CORSMiddleware(BaseMiddleware):
    """CORS中间件"""
    
    def __init__(self, config: MiddlewareConfig, cors_config: CORSConfig):
        super().__init__(config)
        self.cors_config = cors_config
        self.policies: Dict[str, CORSPolicy] = {}
        self.validator = CORSValidator()
        self._setup_policies()
        self._setup_default_policy()
    
    def _setup_policies(self) -> None:
        """设置CORS策略"""
        for policy in self.cors_config.policies:
            self.policies[policy.policy_id] = policy
    
    def _setup_default_policy(self) -> None:
        """设置默认策略"""
        if not self.cors_config.default_policy:
            # 创建默认策略
            default_rule = CORSRule(
                rule_id="default",
                name="Default CORS Rule",
                description="Default permissive CORS rule",
                allowed_origins=[AllowedOrigin("*", "wildcard")],
                allowed_methods=[
                    AllowedMethod(CORSMethod.GET),
                    AllowedMethod(CORSMethod.POST),
                    AllowedMethod(CORSMethod.PUT),
                    AllowedMethod(CORSMethod.DELETE),
                    AllowedMethod(CORSMethod.OPTIONS),
                ],
                allowed_headers=[
                    AllowedHeader("Content-Type"),
                    AllowedHeader("Authorization"),
                    AllowedHeader("X-Requested-With"),
                ],
                allow_credentials=False,
                max_age=3600,
            )
            
            self.cors_config.default_policy = CORSPolicy(
                policy_id="default",
                name="Default CORS Policy",
                description="Default permissive CORS policy",
                rules=[default_rule],
                default_rule=default_rule,
                strict_mode=False
            )
    
    def _should_skip_cors(self, path: str) -> bool:
        """检查是否应该跳过CORS"""
        for skip_path in self.cors_config.skip_paths:
            if path.startswith(skip_path):
                return True
        return False
    
    def _extract_cors_context(self, context: MiddlewareContext) -> CORSContext:
        """提取CORS上下文"""
        origin = context.request.get_header('origin') or ""
        method = context.request.method
        
        # 检查是否为预检请求
        is_preflight = (method.upper() == "OPTIONS" and
                       context.request.get_header('access-control-request-method') is not None)
        
        # 提取请求的头部
        requested_headers = []
        if is_preflight:
            headers_header = context.request.get_header('access-control-request-headers')
            if headers_header:
                requested_headers = [h.strip() for h in headers_header.split(',')]
        
        # 检查是否为CORS请求
        is_cors_request = bool(origin)
        
        return CORSContext(
            origin=origin,
            method=method,
            requested_headers=requested_headers,
            is_preflight=is_preflight,
            is_cors_request=is_cors_request,
        )
    
    def _find_applicable_policy(self, cors_context: CORSContext, path: str) -> Optional[CORSPolicy]:
        """查找适用的策略"""
        # 这里可以根据请求特征选择策略
        # 目前返回第一个策略，实际实现中可以更复杂
        if self.policies:
            return list(self.policies.values())[0]
        return self.cors_config.default_policy
    
    def _process_simple_request(self, cors_context: CORSContext, rule: CORSRule) -> CORSResult:
        """处理简单请求"""
        response_headers = {}
        
        # 检查源
        if not rule.is_origin_allowed(cors_context.origin):
            return CORSResult.deny("Origin not allowed")
        
        # 检查方法
        if not rule.is_method_allowed(cors_context.method):
            return CORSResult.deny("Method not allowed")
        
        # 设置响应头
        response_headers['Access-Control-Allow-Origin'] = cors_context.origin
        
        if rule.allow_credentials:
            response_headers['Access-Control-Allow-Credentials'] = 'true'
        
        if rule.exposed_headers:
            response_headers['Access-Control-Expose-Headers'] = rule.get_exposed_headers_string()
        
        return CORSResult.allow(response_headers)
    
    def _process_preflight_request(self, cors_context: CORSContext, rule: CORSRule, context: MiddlewareContext = None) -> CORSResult:
        """处理预检请求"""
        response_headers = {}
        
        # 检查源
        if not rule.is_origin_allowed(cors_context.origin):
            return CORSResult.deny("Origin not allowed")
        
        # 获取请求的方法
        # 需要从上下文中获取，这里简化处理
        requested_method = cors_context.method
        if not requested_method or not rule.is_method_allowed(requested_method):
            return CORSResult.deny("Requested method not allowed")
        
        # 检查请求的头部
        for header in cors_context.requested_headers:
            if not rule.is_header_allowed(header):
                return CORSResult.deny(f"Requested header '{header}' not allowed")
        
        # 设置响应头
        response_headers['Access-Control-Allow-Origin'] = cors_context.origin
        response_headers['Access-Control-Allow-Methods'] = rule.get_allowed_methods_string()
        response_headers['Access-Control-Allow-Headers'] = rule.get_allowed_headers_string()
        
        if rule.allow_credentials:
            response_headers['Access-Control-Allow-Credentials'] = 'true'
        
        if rule.max_age is not None:
            response_headers['Access-Control-Max-Age'] = str(rule.max_age)
        else:
            response_headers['Access-Control-Max-Age'] = str(self.cors_config.max_age_default)
        
        return CORSResult.allow(response_headers, is_preflight=True, status_code=204)
    
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理CORS请求"""
        try:
            # 检查是否跳过CORS
            if self._should_skip_cors(context.request.path):
                context.set_data('cors_skipped', True)
                return MiddlewareResult.success_result()
            
            # 提取CORS上下文
            cors_context = self._extract_cors_context(context)
            context.set_data('cors_context', cors_context)
            
            # 如果不是CORS请求，直接通过
            if not cors_context.is_cors_request:
                context.set_data('cors_not_required', True)
                return MiddlewareResult.success_result()
            
            # 查找适用的策略
            policy = self._find_applicable_policy(cors_context, context.request.path)
            if not policy:
                return MiddlewareResult.stop_result(
                    status_code=500,
                    body=b'{"error": "No CORS policy configured"}'
                )
            
            # 查找匹配的规则
            rule = policy.find_matching_rule(cors_context.origin, context.request.path)
            if not rule:
                if policy.strict_mode:
                    return MiddlewareResult.stop_result(
                        status_code=403,
                        body=b'{"error": "CORS request denied"}'
                    )
                else:
                    # 使用默认规则
                    rule = policy.default_rule
                    if not rule:
                        return MiddlewareResult.stop_result(
                            status_code=403,
                            body=b'{"error": "No CORS rule matches"}'
                        )
            
            # 处理CORS请求
            if cors_context.is_preflight:
                cors_result = self._process_preflight_request(cors_context, rule, context)
            else:
                cors_result = self._process_simple_request(cors_context, rule)
            
            context.set_data('cors_result', cors_result)
            
            if not cors_result.allowed:
                return MiddlewareResult.stop_result(
                    status_code=cors_result.status_code,
                    body=f'{{"error": "CORS denied", "reason": "{cors_result.reason}"}}'.encode()
                )
            
            # 预检请求直接返回
            if cors_result.is_preflight:
                return MiddlewareResult.stop_result(
                    status_code=cors_result.status_code,
                    headers=cors_result.response_headers
                )
            
            return MiddlewareResult.success_result(headers=cors_result.response_headers)
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    async def process_response(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理CORS响应"""
        try:
            # 检查是否跳过CORS
            if context.get_data('cors_skipped') or context.get_data('cors_not_required'):
                return MiddlewareResult.success_result()
            
            cors_result = context.get_data('cors_result')
            if cors_result and cors_result.allowed and not cors_result.is_preflight:
                # 添加CORS响应头
                if context.response:
                    for header, value in cors_result.response_headers.items():
                        context.response.set_header(header, value)
            
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    def get_cors_context(self, context: MiddlewareContext) -> Optional[CORSContext]:
        """获取CORS上下文"""
        return context.get_data('cors_context')
    
    def get_cors_result(self, context: MiddlewareContext) -> Optional[CORSResult]:
        """获取CORS结果"""
        return context.get_data('cors_result')
    
    def add_policy(self, policy: CORSPolicy) -> bool:
        """添加CORS策略"""
        try:
            self.policies[policy.policy_id] = policy
            return True
        except Exception:
            return False
    
    def remove_policy(self, policy_id: str) -> bool:
        """移除CORS策略"""
        try:
            if policy_id in self.policies:
                del self.policies[policy_id]
                return True
            return False
        except Exception:
            return False
    
    def get_policy(self, policy_id: str) -> Optional[CORSPolicy]:
        """获取CORS策略"""
        return self.policies.get(policy_id)


# CORS异常类
class CORSError(Exception):
    """CORS基础异常"""
    pass


class CORSOriginError(CORSError):
    """CORS源异常"""
    pass


class CORSMethodError(CORSError):
    """CORS方法异常"""
    pass


class CORSHeaderError(CORSError):
    """CORS头部异常"""
    pass