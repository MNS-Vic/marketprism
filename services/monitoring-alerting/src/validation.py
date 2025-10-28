#!/usr/bin/env python3
"""
MarketPrism监控告警服务输入验证模块
提供全面的输入验证和数据清理功能
"""

import re
import json
import html
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, ValidationError, field_validator, Field
from aiohttp import web
import logging

logger = logging.getLogger(__name__)

# 安全正则表达式模式
SAFE_STRING_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\s]+$')
SAFE_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_\-]*$')
SQL_INJECTION_PATTERNS = [
    re.compile(r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)', re.IGNORECASE),
    re.compile(r'(\b(OR|AND)\s+\d+\s*=\s*\d+)', re.IGNORECASE),
    re.compile(r'[\'";]', re.IGNORECASE),
    re.compile(r'--', re.IGNORECASE),
    re.compile(r'/\*.*\*/', re.IGNORECASE)
]

class ValidationConfig:
    """验证配置类"""
    
    # 字符串长度限制
    MAX_STRING_LENGTH = 1000
    MAX_QUERY_PARAM_LENGTH = 100
    MAX_JSON_SIZE = 10 * 1024  # 10KB
    
    # 数值限制
    MAX_LIMIT_VALUE = 1000
    MIN_LIMIT_VALUE = 1
    
    # 允许的字段值
    ALLOWED_SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']
    ALLOWED_STATUSES = ['active', 'resolved', 'acknowledged', 'suppressed']
    ALLOWED_CATEGORIES = ['system', 'application', 'network', 'security', 'performance']
    ALLOWED_SORT_FIELDS = ['timestamp', 'severity', 'status', 'category', 'name']
    ALLOWED_SORT_ORDERS = ['asc', 'desc']

class SecurityValidator:
    """安全验证器"""
    
    @staticmethod
    def check_sql_injection(value: str) -> bool:
        """检查SQL注入攻击"""
        if not isinstance(value, str):
            return True
        
        for pattern in SQL_INJECTION_PATTERNS:
            if pattern.search(value):
                logger.warning(f"检测到潜在SQL注入攻击: {value[:50]}...")
                return False
        return True
    
    @staticmethod
    def check_xss(value: str) -> bool:
        """检查XSS攻击"""
        if not isinstance(value, str):
            return True
        
        # 检查常见XSS模式
        xss_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ]
        
        for pattern in xss_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"检测到潜在XSS攻击: {value[:50]}...")
                return False
        return True
    
    @staticmethod
    def sanitize_string(value: str) -> str:
        """清理字符串"""
        if not isinstance(value, str):
            return str(value)
        
        # HTML转义
        sanitized = html.escape(value)
        
        # 移除控制字符
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
        
        # 限制长度
        if len(sanitized) > ValidationConfig.MAX_STRING_LENGTH:
            sanitized = sanitized[:ValidationConfig.MAX_STRING_LENGTH]
            logger.warning(f"字符串被截断到{ValidationConfig.MAX_STRING_LENGTH}字符")
        
        return sanitized.strip()

# Pydantic模型定义
class AlertQueryParams(BaseModel):
    """告警查询参数模型"""
    
    severity: Optional[str] = Field(None, description="告警严重级别")
    status: Optional[str] = Field(None, description="告警状态")
    category: Optional[str] = Field(None, description="告警类别")
    limit: Optional[int] = Field(100, ge=1, le=1000, description="返回结果数量限制")
    offset: Optional[int] = Field(0, ge=0, description="结果偏移量")
    sort_by: Optional[str] = Field('timestamp', description="排序字段")
    sort_order: Optional[str] = Field('desc', description="排序顺序")
    start_time: Optional[str] = Field(None, description="开始时间")
    end_time: Optional[str] = Field(None, description="结束时间")
    search: Optional[str] = Field(None, max_length=100, description="搜索关键词")
    
    @field_validator('severity')
    def validate_severity(cls, v):
        if v is not None and v not in ValidationConfig.ALLOWED_SEVERITIES:
            raise ValueError(f'severity必须是以下值之一: {ValidationConfig.ALLOWED_SEVERITIES}')
        return v
    
    @field_validator('status')
    def validate_status(cls, v):
        if v is not None and v not in ValidationConfig.ALLOWED_STATUSES:
            raise ValueError(f'status必须是以下值之一: {ValidationConfig.ALLOWED_STATUSES}')
        return v
    
    @field_validator('category')
    def validate_category(cls, v):
        if v is not None and v not in ValidationConfig.ALLOWED_CATEGORIES:
            raise ValueError(f'category必须是以下值之一: {ValidationConfig.ALLOWED_CATEGORIES}')
        return v
    
    @field_validator('sort_by')
    def validate_sort_by(cls, v):
        if v not in ValidationConfig.ALLOWED_SORT_FIELDS:
            raise ValueError(f'sort_by必须是以下值之一: {ValidationConfig.ALLOWED_SORT_FIELDS}')
        return v
    
    @field_validator('sort_order')
    def validate_sort_order(cls, v):
        if v not in ValidationConfig.ALLOWED_SORT_ORDERS:
            raise ValueError(f'sort_order必须是以下值之一: {ValidationConfig.ALLOWED_SORT_ORDERS}')
        return v
    
    @field_validator('start_time', 'end_time')
    def validate_time_format(cls, v):
        if v is not None:
            try:
                datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError('时间格式必须是ISO 8601格式')
        return v
    
    @field_validator('search')
    def validate_search(cls, v):
        if v is not None:
            # 安全检查
            if not SecurityValidator.check_sql_injection(v):
                raise ValueError('搜索词包含不安全字符')
            if not SecurityValidator.check_xss(v):
                raise ValueError('搜索词包含不安全字符')
            # 清理字符串
            v = SecurityValidator.sanitize_string(v)
        return v

class RuleQueryParams(BaseModel):
    """规则查询参数模型"""
    
    enabled: Optional[bool] = Field(None, description="是否启用")
    category: Optional[str] = Field(None, description="规则类别")
    limit: Optional[int] = Field(100, ge=1, le=1000, description="返回结果数量限制")
    offset: Optional[int] = Field(0, ge=0, description="结果偏移量")
    search: Optional[str] = Field(None, max_length=100, description="搜索关键词")
    
    @field_validator('category')
    def validate_category(cls, v):
        if v is not None and v not in ValidationConfig.ALLOWED_CATEGORIES:
            raise ValueError(f'category必须是以下值之一: {ValidationConfig.ALLOWED_CATEGORIES}')
        return v
    
    @field_validator('search')
    def validate_search(cls, v):
        if v is not None:
            if not SecurityValidator.check_sql_injection(v):
                raise ValueError('搜索词包含不安全字符')
            if not SecurityValidator.check_xss(v):
                raise ValueError('搜索词包含不安全字符')
            v = SecurityValidator.sanitize_string(v)
        return v

class LoginRequest(BaseModel):
    """登录请求模型"""
    
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=100, description="密码")
    
    @field_validator('username')
    def validate_username(cls, v):
        if not SAFE_IDENTIFIER_PATTERN.match(v):
            raise ValueError('用户名只能包含字母、数字、下划线和连字符，且必须以字母开头')
        return v
    
    @field_validator('password')
    def validate_password(cls, v):
        # 基本安全检查
        if not SecurityValidator.check_sql_injection(v):
            raise ValueError('密码包含不安全字符')
        return v

class ValidationMiddleware:
    """验证中间件"""
    
    def __init__(self):
        self.validator = SecurityValidator()
    
    async def __call__(self, request: web.Request, handler):
        """中间件处理函数 - 基于aiohttp官方文档的正确实现"""

        # 检查请求大小
        if hasattr(request, 'content_length') and request.content_length:
            if request.content_length > ValidationConfig.MAX_JSON_SIZE:
                logger.warning(f"请求体过大: {request.content_length} bytes")
                return web.Response(
                    status=413,
                    text=json.dumps({"error": "Request entity too large"}),
                    content_type='application/json'
                )

        # 验证查询参数
        for key, value in request.query.items():
            if len(str(value)) > ValidationConfig.MAX_QUERY_PARAM_LENGTH:
                logger.warning(f"查询参数过长: {key}={str(value)[:50]}...")
                return web.Response(
                    status=400,
                    text=json.dumps({"error": f"Query parameter '{key}' too long"}),
                    content_type='application/json'
                )

            # 仅对“开放文本类”参数做安全检查，其余交由具体模型校验，减少误报
            if key in ("search", "q", "query"):
                if not self.validator.check_sql_injection(str(value)):
                    return web.Response(
                        status=400,
                        text=json.dumps({"error": f"Invalid characters in parameter '{key}'"}),
                        content_type='application/json'
                    )

                if not self.validator.check_xss(str(value)):
                    return web.Response(
                        status=400,
                        text=json.dumps({"error": f"Invalid characters in parameter '{key}'"}),
                        content_type='application/json'
                    )

        return await handler(request)

async def validate_query_params(request: web.Request, model_class: BaseModel) -> BaseModel:
    """验证查询参数"""
    try:
        # 获取查询参数
        params = dict(request.query)
        
        # 清理参数值
        cleaned_params = {}
        for key, value in params.items():
            cleaned_params[key] = SecurityValidator.sanitize_string(str(value))
        
        # 验证参数
        validated = model_class(**cleaned_params)
        return validated
        
    except ValidationError as e:
        logger.warning(f"查询参数验证失败: {e}")
        raise web.HTTPBadRequest(
            text=json.dumps({
                "error": "Invalid query parameters",
                "details": [{"field": err["loc"][0], "message": err["msg"]} for err in e.errors()]
            }),
            content_type='application/json'
        )
    except Exception as e:
        logger.error(f"参数验证异常: {e}")
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Parameter validation failed"}),
            content_type='application/json'
        )

async def validate_json_body(request: web.Request, model_class: BaseModel) -> BaseModel:
    """验证JSON请求体"""
    try:
        # 获取JSON数据
        data = await request.json()
        
        # 验证数据
        validated = model_class(**data)
        return validated
        
    except json.JSONDecodeError as e:
        logger.warning(f"JSON解析失败: {e}")
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Invalid JSON format"}),
            content_type='application/json'
        )
    except ValidationError as e:
        logger.warning(f"JSON数据验证失败: {e}")
        raise web.HTTPBadRequest(
            text=json.dumps({
                "error": "Invalid request data",
                "details": [{"field": err["loc"][0], "message": err["msg"]} for err in e.errors()]
            }),
            content_type='application/json'
        )
    except Exception as e:
        logger.error(f"请求体验证异常: {e}")
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Request validation failed"}),
            content_type='application/json'
        )

from aiohttp import web as _web  # for middleware decorator

def create_validation_middleware():
    """创建验证中间件（aiohttp新式中间件）"""
    _instance = ValidationMiddleware()

    @_web.middleware
    async def _middleware(request, handler):
        return await _instance.__call__(request, handler)

    return _middleware

# 导出主要组件
__all__ = [
    'ValidationConfig',
    'SecurityValidator',
    'AlertQueryParams',
    'RuleQueryParams', 
    'LoginRequest',
    'ValidationMiddleware',
    'validate_query_params',
    'validate_json_body',
    'create_validation_middleware'
]
