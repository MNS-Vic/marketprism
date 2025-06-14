"""
Core Middleware Framework

This module provides a flexible and extensible middleware framework for `aiohttp`.
It allows for easy composition of middleware layers for handling cross-cutting concerns
like authentication, authorization, logging, caching, and more.
"""

from datetime import datetime, timezone
from .middleware_framework import (
    BaseMiddleware,
    MiddlewareManager,
    middleware_adapter,
    create_middleware_chain
)
from .authentication_middleware import AuthenticationMiddleware
from .authorization_middleware import AuthorizationMiddleware
from .caching_middleware import CachingMiddleware
from .cors_middleware import CorsMiddleware

__all__ = [
    "BaseMiddleware",
    "MiddlewareManager",
    "middleware_adapter",
    "create_middleware_chain",
    "AuthenticationMiddleware",
    "AuthorizationMiddleware",
    "CachingMiddleware",
    "CorsMiddleware",
]
