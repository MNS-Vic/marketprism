"""
MarketPrism API网关中间件系统

Week 6 Day 3: API网关中间件系统
提供企业级的可扩展中间件处理链，包含认证、授权、限流、日志、CORS和缓存等核心中间件。

核心组件:
1. MiddlewareFramework - 中间件框架和处理链
2. AuthenticationMiddleware - 认证中间件
3. AuthorizationMiddleware - 授权中间件  
4. RateLimitingMiddleware - 限流中间件
5. LoggingMiddleware - 日志中间件
6. CORSMiddleware - CORS中间件
7. CachingMiddleware - 缓存中间件

设计原则:
- 责任链模式：中间件链式处理
- 可配置性：灵活的中间件配置
- 可扩展性：支持自定义中间件
- 高性能：异步处理和优化
- 线程安全：多线程环境支持
"""

from .middleware_framework import (
    # 中间件框架核心
    MiddlewareFramework,
    MiddlewareChain,
    MiddlewareProcessor,
    
    # 中间件基础类
    BaseMiddleware,
    MiddlewareConfig,
    MiddlewareContext,
    MiddlewareResult,
    
    # 中间件类型和状态
    MiddlewareType,
    MiddlewareStatus,
    MiddlewarePriority,
    
    # 请求响应模型
    MiddlewareRequest,
    MiddlewareResponse,
    RequestHeaders,
    ResponseHeaders,
    
    # 异常和错误
    MiddlewareError,
    MiddlewareChainError,
    MiddlewareConfigError,
)

from .authentication_middleware import (
    # 认证中间件
    AuthenticationMiddleware,
    AuthenticationConfig,
    AuthenticationContext,
    AuthenticationResult,
    
    # 认证类型和提供者
    AuthenticationType,
    AuthenticationProvider,
    TokenValidator,
    
    # JWT相关
    JWTConfig,
    JWTValidator,
    JWTClaims,
    
    # API密钥相关
    APIKeyConfig,
    APIKeyValidator,
    APIKeyStore,
    
    # Basic认证
    BasicAuthConfig,
    BasicAuthValidator,
    
    # 认证异常
    AuthenticationError,
    InvalidTokenError,
    ExpiredTokenError,
    InvalidCredentialsError,
)

from .authorization_middleware import (
    # 授权中间件
    AuthorizationMiddleware,
    AuthorizationConfig,
    AuthorizationContext,
    AuthorizationResult,
    
    # 授权策略
    AuthorizationPolicy,
    PolicyEngine,
    PolicyEvaluator,
    
    # RBAC相关
    RBACConfig,
    Role,
    Permission,
    RoleManager,
    PermissionManager,
    
    # ACL相关
    ACLConfig,
    AccessControlList,
    ACLEntry,
    
    # 授权动作和资源
    AuthorizationAction,
    ResourceType,
    
    # 授权异常
    AuthorizationError,
    InsufficientPermissionsError,
    RoleNotFoundError,
    PolicyViolationError,
)

from .rate_limiting_middleware import (
    # 限流中间件
    RateLimitingMiddleware,
    RateLimitingConfig,
    RateLimitContext,
    RateLimitResult,
    
    # 限流算法
    RateLimitAlgorithm,
    TokenBucketLimiter,
    LeakyBucketLimiter,
    SlidingWindowLimiter,
    FixedWindowLimiter,
    
    # 限流策略
    RateLimitPolicy,
    RateLimitRule,
    RateLimitScope,
    
    # 限流存储
    RateLimitStore,
    MemoryRateLimitStore,
    RedisRateLimitStore,
    
    # 限流异常
    RateLimitError,
    RateLimitExceededError,
    RateLimitConfigError,
)

from .logging_middleware import (
    # 日志中间件
    LoggingMiddleware,
    LoggingConfig,
    LoggingResult,
    
    # 日志格式化
    LogFormatter,
    StructuredLogFormatter,
    JSONLogFormatter,
    TextLogFormatter,
    
    # 日志记录器
    MiddlewareLogger,
    RequestLogger,
    ResponseLogger,
    ErrorLogger,
    
    # 日志级别和类型
    LogLevel,
    LogType,
    LogEvent,
    
    # 日志异常
    LoggingError,
    LogFormatterError,
    LoggerConfigError,
)

from .cors_middleware import (
    # CORS中间件
    CORSMiddleware,
    CORSConfig,
    CORSResult,
    
    # CORS策略
    CORSPolicy,
    CORSRule,
    AllowedOrigin,
    AllowedMethod,
    AllowedHeader,
    
    # CORS方法
    CORSMethod,
    
    # CORS验证器
    CORSValidator,
    OriginValidator,
    MethodValidator,
    HeaderValidator,
    
    # CORS异常
    CORSError,
    CORSOriginError,
    CORSMethodError,
    CORSHeaderError,
)

from .caching_middleware import (
    # 缓存中间件
    CachingMiddleware,
    CachingConfig,
    CachingResult,
    
    # 缓存策略
    CachePolicy,
    CacheRule,
    CacheKeyGenerator,
    CacheTTLCalculator,
    
    # 缓存存储
    CacheStore,
    MemoryCacheStore,
    RedisCacheStore,
    MultiLevelCacheStore,
    
    # 缓存控制
    CacheControl,
    CacheInvalidator,
    CacheWarmer,
    
    # 缓存异常
    CachingError,
    CacheKeyError,
    CacheStoreError,
    CacheInvalidationError,
)

# 版本信息
__version__ = "1.0.0"
__author__ = "MarketPrism Team"
__description__ = "Enterprise API Gateway Middleware System"

# 所有导出
__all__ = [
    # 中间件框架
    "MiddlewareFramework", "MiddlewareChain", "MiddlewareProcessor",
    "BaseMiddleware", "MiddlewareConfig", "MiddlewareContext", "MiddlewareResult",
    "MiddlewareType", "MiddlewareStatus", "MiddlewarePriority",
    "MiddlewareRequest", "MiddlewareResponse", "RequestHeaders", "ResponseHeaders",
    "MiddlewareError", "MiddlewareChainError", "MiddlewareConfigError",
    
    # 认证中间件
    "AuthenticationMiddleware", "AuthenticationConfig", "AuthenticationContext", "AuthenticationResult",
    "AuthenticationType", "AuthenticationProvider", "TokenValidator",
    "JWTConfig", "JWTValidator", "JWTClaims",
    "APIKeyConfig", "APIKeyValidator", "APIKeyStore",
    "BasicAuthConfig", "BasicAuthValidator",
    "AuthenticationError", "InvalidTokenError", "ExpiredTokenError", "InvalidCredentialsError",
    
    # 授权中间件
    "AuthorizationMiddleware", "AuthorizationConfig", "AuthorizationContext", "AuthorizationResult",
    "AuthorizationPolicy", "PolicyEngine", "PolicyEvaluator",
    "RBACConfig", "Role", "Permission", "RoleManager", "PermissionManager",
    "ACLConfig", "AccessControlList", "ACLEntry",
    "AuthorizationAction", "ResourceType",
    "AuthorizationError", "InsufficientPermissionsError", "RoleNotFoundError", "PolicyViolationError",
    
    # 限流中间件
    "RateLimitingMiddleware", "RateLimitingConfig", "RateLimitContext", "RateLimitResult",
    "RateLimitAlgorithm", "TokenBucketLimiter", "LeakyBucketLimiter", "SlidingWindowLimiter", "FixedWindowLimiter",
    "RateLimitPolicy", "RateLimitRule", "RateLimitScope",
    "RateLimitStore", "MemoryRateLimitStore", "RedisRateLimitStore",
    "RateLimitError", "RateLimitExceededError", "RateLimitConfigError",
    
    # 日志中间件
    "LoggingMiddleware", "LoggingConfig", "LoggingResult",
    "LogFormatter", "StructuredLogFormatter", "JSONLogFormatter", "TextLogFormatter",
    "MiddlewareLogger", "RequestLogger", "ResponseLogger", "ErrorLogger",
    "LogLevel", "LogType", "LogEvent",
    "LoggingError", "LogFormatterError", "LoggerConfigError",
    
    # CORS中间件
    "CORSMiddleware", "CORSConfig", "CORSResult",
    "CORSPolicy", "CORSRule", "AllowedOrigin", "AllowedMethod", "AllowedHeader",
    "CORSMethod",
    "CORSValidator", "OriginValidator", "MethodValidator", "HeaderValidator",
    "CORSError", "CORSOriginError", "CORSMethodError", "CORSHeaderError",
    
    # 缓存中间件
    "CachingMiddleware", "CachingConfig", "CachingResult",
    "CachePolicy", "CacheRule", "CacheKeyGenerator", "CacheTTLCalculator",
    "CacheStore", "MemoryCacheStore", "RedisCacheStore", "MultiLevelCacheStore",
    "CacheControl", "CacheInvalidator", "CacheWarmer",
    "CachingError", "CacheKeyError", "CacheStoreError", "CacheInvalidationError",
]