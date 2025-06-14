"""
MarketPrism 认证中间件

这个模块实现了企业级认证中间件，支持多种认证方式包括JWT、API密钥、基础认证等。
提供灵活的认证策略和完整的认证上下文管理。

核心功能:
1. 多种认证类型：JWT、API密钥、基础认证
2. 认证提供者：可扩展的认证提供者架构
3. Token验证：JWT token验证和管理
4. API密钥管理：API密钥生成、验证和存储
5. 认证上下文：完整的认证上下文和用户信息
6. 认证异常：详细的认证错误处理
"""

import asyncio
import time
import jwt
import hashlib
import secrets
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
import threading
from datetime import datetime, timedelta, timezone

from .middleware_framework import (
    BaseMiddleware, MiddlewareConfig, MiddlewareContext, MiddlewareResult,
    MiddlewareType, MiddlewarePriority
)


class AuthenticationType(Enum):
    """认证类型枚举"""
    JWT = "jwt"                           # JWT认证
    API_KEY = "api_key"                   # API密钥认证
    BASIC_AUTH = "basic_auth"             # 基础认证
    BEARER_TOKEN = "bearer_token"         # Bearer令牌认证
    OAUTH2 = "oauth2"                     # OAuth2认证
    CUSTOM = "custom"                     # 自定义认证


@dataclass
class JWTClaims:
    """JWT声明"""
    user_id: str
    username: str = ""
    email: str = ""
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    issuer: str = ""
    audience: str = ""
    custom_claims: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at:
            return datetime.now(timezone.utc) > self.expires_at
        return False
    
    def get_claim(self, key: str, default: Any = None) -> Any:
        """获取自定义声明"""
        return self.custom_claims.get(key, default)
    
    def set_claim(self, key: str, value: Any) -> None:
        """设置自定义声明"""
        self.custom_claims[key] = value


@dataclass
class AuthenticationContext:
    """认证上下文"""
    is_authenticated: bool = False
    authentication_type: Optional[AuthenticationType] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    jwt_claims: Optional[JWTClaims] = None
    api_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    authenticated_at: Optional[datetime] = None
    
    def add_role(self, role: str) -> None:
        """添加角色"""
        if role not in self.roles:
            self.roles.append(role)
    
    def has_role(self, role: str) -> bool:
        """检查是否有指定角色"""
        return role in self.roles
    
    def add_permission(self, permission: str) -> None:
        """添加权限"""
        if permission not in self.permissions:
            self.permissions.append(permission)
    
    def has_permission(self, permission: str) -> bool:
        """检查是否有指定权限"""
        return permission in self.permissions
    
    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)


@dataclass
class AuthenticationResult:
    """认证结果"""
    success: bool
    context: Optional[AuthenticationContext] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def success_result(cls, context: AuthenticationContext, **kwargs) -> 'AuthenticationResult':
        """创建成功结果"""
        return cls(success=True, context=context, **kwargs)
    
    @classmethod
    def failure_result(cls, error: str, error_code: Optional[str] = None, **kwargs) -> 'AuthenticationResult':
        """创建失败结果"""
        return cls(success=False, error=error, error_code=error_code, **kwargs)


class AuthenticationProvider(ABC):
    """认证提供者抽象基类"""
    
    @abstractmethod
    async def authenticate(self, request_context: MiddlewareContext) -> AuthenticationResult:
        """执行认证"""
        pass
    
    @abstractmethod
    def get_authentication_type(self) -> AuthenticationType:
        """获取认证类型"""
        pass


@dataclass
class JWTConfig:
    """JWT配置"""
    secret_key: str
    algorithm: str = "HS256"
    issuer: str = ""
    audience: str = ""
    token_ttl: int = 3600  # 令牌有效期（秒）
    refresh_ttl: int = 86400  # 刷新令牌有效期（秒）
    verify_signature: bool = True
    verify_exp: bool = True
    verify_iat: bool = True
    verify_iss: bool = False
    verify_aud: bool = False
    leeway: int = 0  # 时间偏移容忍度（秒）
    
    def get_decode_options(self) -> Dict[str, bool]:
        """获取JWT解码选项"""
        return {
            'verify_signature': self.verify_signature,
            'verify_exp': self.verify_exp,
            'verify_iat': self.verify_iat,
            'verify_iss': self.verify_iss,
            'verify_aud': self.verify_aud,
        }


class JWTValidator:
    """JWT验证器"""
    
    def __init__(self, config: JWTConfig):
        self.config = config
    
    async def validate_token(self, token: str) -> AuthenticationResult:
        """验证JWT令牌"""
        try:
            # 解码JWT
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                options=self.config.get_decode_options(),
                leeway=self.config.leeway,
                issuer=self.config.issuer if self.config.verify_iss else None,
                audience=self.config.audience if self.config.verify_aud else None
            )
            
            # 提取声明
            claims = JWTClaims(
                user_id=payload.get('sub', ''),
                username=payload.get('username', ''),
                email=payload.get('email', ''),
                roles=payload.get('roles', []),
                permissions=payload.get('permissions', []),
                issued_at=datetime.fromtimestamp(payload.get('iat', 0)) if payload.get('iat') else None,
                expires_at=datetime.fromtimestamp(payload.get('exp', 0)) if payload.get('exp') else None,
                issuer=payload.get('iss', ''),
                audience=payload.get('aud', ''),
                custom_claims={k: v for k, v in payload.items() 
                             if k not in ['sub', 'username', 'email', 'roles', 'permissions', 
                                        'iat', 'exp', 'iss', 'aud']}
            )
            
            # 检查是否过期
            if claims.is_expired():
                return AuthenticationResult.failure_result(
                    "Token has expired", 
                    "TOKEN_EXPIRED"
                )
            
            # 创建认证上下文
            context = AuthenticationContext(
                is_authenticated=True,
                authentication_type=AuthenticationType.JWT,
                user_id=claims.user_id,
                username=claims.username,
                email=claims.email,
                roles=claims.roles,
                permissions=claims.permissions,
                jwt_claims=claims,
                authenticated_at=datetime.now(timezone.utc)
            )
            
            return AuthenticationResult.success_result(context)
            
        except jwt.ExpiredSignatureError:
            return AuthenticationResult.failure_result(
                "Token has expired", 
                "TOKEN_EXPIRED"
            )
        except jwt.InvalidTokenError as e:
            return AuthenticationResult.failure_result(
                f"Invalid token: {str(e)}", 
                "INVALID_TOKEN"
            )
        except Exception as e:
            return AuthenticationResult.failure_result(
                f"Token validation error: {str(e)}", 
                "VALIDATION_ERROR"
            )
    
    def generate_token(self, claims: JWTClaims) -> str:
        """生成JWT令牌"""
        now = datetime.now(timezone.utc)
        payload = {
            'sub': claims.user_id,
            'username': claims.username,
            'email': claims.email,
            'roles': claims.roles,
            'permissions': claims.permissions,
            'iat': int(now.timestamp()),
            'exp': int((now + timedelta(seconds=self.config.token_ttl)).timestamp()),
            'iss': self.config.issuer,
            'aud': self.config.audience,
            **claims.custom_claims
        }
        
        return jwt.encode(payload, self.config.secret_key, algorithm=self.config.algorithm)


class JWTProvider(AuthenticationProvider):
    """JWT认证提供者"""
    
    def __init__(self, config: JWTConfig):
        self.config = config
        self.validator = JWTValidator(config)
    
    async def authenticate(self, request_context: MiddlewareContext) -> AuthenticationResult:
        """执行JWT认证"""
        # 从Authorization头获取token
        auth_header = request_context.request.get_header('authorization')
        if not auth_header:
            return AuthenticationResult.failure_result(
                "Missing Authorization header", 
                "MISSING_AUTH_HEADER"
            )
        
        # 检查Bearer前缀
        if not auth_header.startswith('Bearer '):
            return AuthenticationResult.failure_result(
                "Invalid Authorization header format", 
                "INVALID_AUTH_FORMAT"
            )
        
        # 提取token
        token = auth_header[7:]  # 移除"Bearer "
        if not token:
            return AuthenticationResult.failure_result(
                "Missing token", 
                "MISSING_TOKEN"
            )
        
        # 验证token
        return await self.validator.validate_token(token)
    
    def get_authentication_type(self) -> AuthenticationType:
        """获取认证类型"""
        return AuthenticationType.JWT


@dataclass
class APIKeyConfig:
    """API密钥配置"""
    header_name: str = "X-API-Key"
    query_param: str = "api_key"
    allow_query_param: bool = True
    hash_algorithm: str = "sha256"
    key_length: int = 32
    prefix: str = ""
    
    def hash_key(self, key: str) -> str:
        """哈希API密钥"""
        hasher = hashlib.new(self.hash_algorithm)
        hasher.update(key.encode('utf-8'))
        return hasher.hexdigest()


class APIKeyStore(ABC):
    """API密钥存储抽象基类"""
    
    @abstractmethod
    async def get_key_info(self, api_key: str) -> Optional[Dict[str, Any]]:
        """获取API密钥信息"""
        pass
    
    @abstractmethod
    async def validate_key(self, api_key: str) -> bool:
        """验证API密钥"""
        pass


class MemoryAPIKeyStore(APIKeyStore):
    """内存API密钥存储"""
    
    def __init__(self):
        self.keys: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def add_key(self, api_key: str, user_info: Dict[str, Any]) -> None:
        """添加API密钥"""
        with self._lock:
            self.keys[api_key] = {
                'user_id': user_info.get('user_id', ''),
                'username': user_info.get('username', ''),
                'email': user_info.get('email', ''),
                'roles': user_info.get('roles', []),
                'permissions': user_info.get('permissions', []),
                'created_at': datetime.now(timezone.utc),
                'last_used': None,
                'metadata': user_info.get('metadata', {})
            }
    
    async def get_key_info(self, api_key: str) -> Optional[Dict[str, Any]]:
        """获取API密钥信息"""
        with self._lock:
            info = self.keys.get(api_key)
            if info:
                # 更新最后使用时间
                info['last_used'] = datetime.now(timezone.utc)
            return info
    
    async def validate_key(self, api_key: str) -> bool:
        """验证API密钥"""
        return api_key in self.keys


class APIKeyValidator:
    """API密钥验证器"""
    
    def __init__(self, config: APIKeyConfig, store: APIKeyStore):
        self.config = config
        self.store = store
    
    async def validate_key(self, api_key: str) -> AuthenticationResult:
        """验证API密钥"""
        try:
            # 验证密钥格式
            if not api_key:
                return AuthenticationResult.failure_result(
                    "Empty API key", 
                    "EMPTY_API_KEY"
                )
            
            # 从存储中获取密钥信息
            key_info = await self.store.get_key_info(api_key)
            if not key_info:
                return AuthenticationResult.failure_result(
                    "Invalid API key", 
                    "INVALID_API_KEY"
                )
            
            # 创建认证上下文
            context = AuthenticationContext(
                is_authenticated=True,
                authentication_type=AuthenticationType.API_KEY,
                user_id=key_info.get('user_id', ''),
                username=key_info.get('username', ''),
                email=key_info.get('email', ''),
                roles=key_info.get('roles', []),
                permissions=key_info.get('permissions', []),
                api_key=api_key,
                authenticated_at=datetime.now(timezone.utc)
            )
            
            # 设置元数据
            for key, value in key_info.get('metadata', {}).items():
                context.set_metadata(key, value)
            
            return AuthenticationResult.success_result(context)
            
        except Exception as e:
            return AuthenticationResult.failure_result(
                f"API key validation error: {str(e)}", 
                "VALIDATION_ERROR"
            )
    
    def generate_key(self) -> str:
        """生成API密钥"""
        key = secrets.token_urlsafe(self.config.key_length)
        if self.config.prefix:
            key = f"{self.config.prefix}{key}"
        return key


class APIKeyProvider(AuthenticationProvider):
    """API密钥认证提供者"""
    
    def __init__(self, config: APIKeyConfig, store: APIKeyStore):
        self.config = config
        self.store = store
        self.validator = APIKeyValidator(config, store)
    
    async def authenticate(self, request_context: MiddlewareContext) -> AuthenticationResult:
        """执行API密钥认证"""
        # 从头部获取API密钥
        api_key = request_context.request.get_header(self.config.header_name)
        
        # 如果头部没有，从查询参数获取
        if not api_key and self.config.allow_query_param:
            api_key = request_context.request.get_query_param(self.config.query_param)
        
        if not api_key:
            return AuthenticationResult.failure_result(
                f"Missing API key in {self.config.header_name} header or {self.config.query_param} parameter", 
                "MISSING_API_KEY"
            )
        
        # 验证API密钥
        return await self.validator.validate_key(api_key)
    
    def get_authentication_type(self) -> AuthenticationType:
        """获取认证类型"""
        return AuthenticationType.API_KEY


@dataclass
class BasicAuthConfig:
    """基础认证配置"""
    realm: str = "MarketPrism API"
    charset: str = "utf-8"
    
    def encode_credentials(self, username: str, password: str) -> str:
        """编码凭证"""
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode(self.charset)).decode('ascii')
        return f"Basic {encoded}"
    
    def decode_credentials(self, auth_header: str) -> Optional[tuple[str, str]]:
        """解码凭证"""
        try:
            if not auth_header.startswith('Basic '):
                return None
            
            encoded = auth_header[6:]
            decoded = base64.b64decode(encoded).decode(self.charset)
            
            if ':' not in decoded:
                return None
                
            username, password = decoded.split(':', 1)
            return username, password
        except Exception:
            return None


class BasicAuthValidator:
    """基础认证验证器"""
    
    def __init__(self, config: BasicAuthConfig, credential_validator: Callable[[str, str], Optional[Dict[str, Any]]]):
        self.config = config
        self.credential_validator = credential_validator
    
    async def validate_credentials(self, username: str, password: str) -> AuthenticationResult:
        """验证凭证"""
        try:
            # 验证用户名密码
            user_info = self.credential_validator(username, password)
            if not user_info:
                return AuthenticationResult.failure_result(
                    "Invalid username or password", 
                    "INVALID_CREDENTIALS"
                )
            
            # 创建认证上下文
            context = AuthenticationContext(
                is_authenticated=True,
                authentication_type=AuthenticationType.BASIC_AUTH,
                user_id=user_info.get('user_id', username),
                username=username,
                email=user_info.get('email', ''),
                roles=user_info.get('roles', []),
                permissions=user_info.get('permissions', []),
                authenticated_at=datetime.now(timezone.utc)
            )
            
            # 设置元数据
            for key, value in user_info.get('metadata', {}).items():
                context.set_metadata(key, value)
            
            return AuthenticationResult.success_result(context)
            
        except Exception as e:
            return AuthenticationResult.failure_result(
                f"Credential validation error: {str(e)}", 
                "VALIDATION_ERROR"
            )


class BasicAuthProvider(AuthenticationProvider):
    """基础认证提供者"""
    
    def __init__(self, config: BasicAuthConfig, credential_validator: Callable[[str, str], Optional[Dict[str, Any]]]):
        self.config = config
        self.validator = BasicAuthValidator(config, credential_validator)
    
    async def authenticate(self, request_context: MiddlewareContext) -> AuthenticationResult:
        """执行基础认证"""
        # 从Authorization头获取凭证
        auth_header = request_context.request.get_header('authorization')
        if not auth_header:
            return AuthenticationResult.failure_result(
                "Missing Authorization header", 
                "MISSING_AUTH_HEADER"
            )
        
        # 解码凭证
        credentials = self.config.decode_credentials(auth_header)
        if not credentials:
            return AuthenticationResult.failure_result(
                "Invalid Authorization header format", 
                "INVALID_AUTH_FORMAT"
            )
        
        username, password = credentials
        
        # 验证凭证
        return await self.validator.validate_credentials(username, password)
    
    def get_authentication_type(self) -> AuthenticationType:
        """获取认证类型"""
        return AuthenticationType.BASIC_AUTH


@dataclass
class AuthenticationConfig:
    """认证中间件配置"""
    enabled_providers: List[AuthenticationType] = field(default_factory=list)
    primary_provider: Optional[AuthenticationType] = None
    allow_anonymous: bool = False
    require_authentication: bool = True
    skip_paths: List[str] = field(default_factory=list)
    jwt_config: Optional[JWTConfig] = None
    api_key_config: Optional[APIKeyConfig] = None
    basic_auth_config: Optional[BasicAuthConfig] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TokenValidator:
    """令牌验证器接口"""
    
    def __init__(self):
        self.validators = {}
    
    def register_validator(self, auth_type: AuthenticationType, validator: AuthenticationProvider) -> None:
        """注册验证器"""
        self.validators[auth_type] = validator
    
    async def validate(self, auth_type: AuthenticationType, request_context: MiddlewareContext) -> AuthenticationResult:
        """验证令牌"""
        validator = self.validators.get(auth_type)
        if not validator:
            return AuthenticationResult.failure_result(
                f"No validator registered for {auth_type.value}", 
                "NO_VALIDATOR"
            )
        
        return await validator.authenticate(request_context)


class AuthenticationMiddleware(BaseMiddleware):
    """认证中间件"""
    
    def __init__(self, config: MiddlewareConfig, auth_config: AuthenticationConfig):
        super().__init__(config)
        self.auth_config = auth_config
        self.providers: Dict[AuthenticationType, AuthenticationProvider] = {}
        self.token_validator = TokenValidator()
        self._setup_providers()
    
    def _setup_providers(self) -> None:
        """设置认证提供者"""
        # 设置JWT提供者
        if AuthenticationType.JWT in self.auth_config.enabled_providers and self.auth_config.jwt_config:
            provider = JWTProvider(self.auth_config.jwt_config)
            self.providers[AuthenticationType.JWT] = provider
            self.token_validator.register_validator(AuthenticationType.JWT, provider)
        
        # 设置API密钥提供者
        if AuthenticationType.API_KEY in self.auth_config.enabled_providers and self.auth_config.api_key_config:
            # 需要提供API密钥存储实现
            store = MemoryAPIKeyStore()  # 默认使用内存存储
            provider = APIKeyProvider(self.auth_config.api_key_config, store)
            self.providers[AuthenticationType.API_KEY] = provider
            self.token_validator.register_validator(AuthenticationType.API_KEY, provider)
        
        # 设置基础认证提供者
        if AuthenticationType.BASIC_AUTH in self.auth_config.enabled_providers and self.auth_config.basic_auth_config:
            # 需要提供凭证验证函数
            def default_validator(username: str, password: str) -> Optional[Dict[str, Any]]:
                # 这里应该连接到实际的用户存储系统
                if username == "admin" and password == "password":
                    return {
                        'user_id': 'admin',
                        'roles': ['admin'],
                        'permissions': ['read', 'write', 'admin']
                    }
                return None
            
            provider = BasicAuthProvider(self.auth_config.basic_auth_config, default_validator)
            self.providers[AuthenticationType.BASIC_AUTH] = provider
            self.token_validator.register_validator(AuthenticationType.BASIC_AUTH, provider)
    
    def _should_skip_authentication(self, path: str) -> bool:
        """检查是否应该跳过认证"""
        for skip_path in self.auth_config.skip_paths:
            if path.startswith(skip_path):
                return True
        return False
    
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理认证请求"""
        try:
            # 检查是否跳过认证
            if self._should_skip_authentication(context.request.path):
                context.set_data('authentication_skipped', True)
                return MiddlewareResult.success_result()
            
            # 检查是否需要认证
            if not self.auth_config.require_authentication and self.auth_config.allow_anonymous:
                context.set_data('authentication_optional', True)
                return MiddlewareResult.success_result()
            
            # 尝试使用各种认证提供者
            auth_result = None
            for auth_type in self.auth_config.enabled_providers:
                provider = self.providers.get(auth_type)
                if provider:
                    result = await provider.authenticate(context)
                    if result.success:
                        auth_result = result
                        break
                    elif not self.auth_config.allow_anonymous:
                        # 如果不允许匿名且认证失败，记录错误但继续尝试其他提供者
                        context.add_error(Exception(f"{auth_type.value} authentication failed: {result.error}"))
            
            # 检查认证结果
            if not auth_result or not auth_result.success:
                if self.auth_config.allow_anonymous:
                    # 允许匿名访问
                    context.set_data('authentication_anonymous', True)
                    return MiddlewareResult.success_result()
                else:
                    # 认证失败
                    return MiddlewareResult.stop_result(
                        status_code=401,
                        body=b'{"error": "Authentication required"}'
                    )
            
            # 认证成功，设置上下文
            context.set_data('authentication_context', auth_result.context)
            context.set_user_data('user_id', auth_result.context.user_id)
            context.set_user_data('username', auth_result.context.username)
            context.set_user_data('roles', auth_result.context.roles)
            context.set_user_data('permissions', auth_result.context.permissions)
            
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            return MiddlewareResult.error_result(e)
    
    def get_authentication_context(self, context: MiddlewareContext) -> Optional[AuthenticationContext]:
        """获取认证上下文"""
        return context.get_data('authentication_context')
    
    def is_authenticated(self, context: MiddlewareContext) -> bool:
        """检查是否已认证"""
        auth_context = self.get_authentication_context(context)
        return auth_context is not None and auth_context.is_authenticated
    
    def get_user_id(self, context: MiddlewareContext) -> Optional[str]:
        """获取用户ID"""
        return context.get_user_data('user_id')
    
    def get_user_roles(self, context: MiddlewareContext) -> List[str]:
        """获取用户角色"""
        return context.get_user_data('roles', [])
    
    def get_user_permissions(self, context: MiddlewareContext) -> List[str]:
        """获取用户权限"""
        return context.get_user_data('permissions', [])


# 认证异常类
class AuthenticationError(Exception):
    """认证基础异常"""
    pass


class InvalidTokenError(AuthenticationError):
    """无效令牌异常"""
    pass


class ExpiredTokenError(AuthenticationError):
    """令牌过期异常"""
    pass


class InvalidCredentialsError(AuthenticationError):
    """无效凭证异常"""
    pass