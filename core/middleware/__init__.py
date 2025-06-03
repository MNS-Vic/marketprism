"""
MarketPrism 中间件框架

提供灵活、高性能的中间件处理框架，支持认证、授权、限流、日志等功能。
"""

from .middleware_framework import (
    MiddlewareType, MiddlewareStatus, MiddlewarePriority,
    BaseMiddleware, MiddlewareChain, MiddlewareProcessor, 
    MiddlewareFramework, MiddlewareRequest, MiddlewareResponse,
    MiddlewareContext, MiddlewareResult, MiddlewareConfig
)

__all__ = [
    "MiddlewareType", "MiddlewareStatus", "MiddlewarePriority",
    "BaseMiddleware", "MiddlewareChain", "MiddlewareProcessor",
    "MiddlewareFramework", "MiddlewareRequest", "MiddlewareResponse",
    "MiddlewareContext", "MiddlewareResult", "MiddlewareConfig"
]
# 完整的中间件实现
try:
    from .middleware_framework import *
    from .authentication_middleware import AuthenticationMiddleware
    from .authorization_middleware import AuthorizationMiddleware
    from .rate_limiting_middleware import RateLimitingMiddleware
    from .cors_middleware import CORSMiddleware
    from .caching_middleware import CachingMiddleware
    from .logging_middleware import LoggingMiddleware
except ImportError as e:
    # 某些中间件组件可能未安装
    print(f"Warning: 部分中间件组件未安装: {e}")
