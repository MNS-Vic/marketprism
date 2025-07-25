#!/usr/bin/env python3
"""
MarketPrism监控告警服务认证模块
实现基于Token和Basic Auth的双重认证机制
"""

import os
import hashlib
import hmac
import time
import json
import base64
from typing import Optional, Dict, Any
from aiohttp import web, hdrs
import logging

logger = logging.getLogger(__name__)

class AuthenticationError(Exception):
    """认证异常"""
    pass

class AuthConfig:
    """认证配置类"""
    
    def __init__(self):
        # 从环境变量获取配置，提供默认值
        self.username = os.getenv('MONITORING_USERNAME', 'admin')
        self.password = os.getenv('MONITORING_PASSWORD', 'marketprism2024!')
        self.api_key = os.getenv('MONITORING_API_KEY', 'mp-monitoring-key-2024')
        self.secret_key = os.getenv('MONITORING_SECRET_KEY', 'mp-secret-key-2024')
        self.token_expiry = int(os.getenv('TOKEN_EXPIRY_SECONDS', '3600'))  # 1小时
        
        # 安全配置
        self.require_https = os.getenv('REQUIRE_HTTPS', 'false').lower() == 'true'
        self.rate_limit_enabled = os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true'
        self.max_requests_per_minute = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '100'))

class TokenManager:
    """Token管理器"""
    
    def __init__(self, secret_key: str, expiry_seconds: int = 3600):
        self.secret_key = secret_key.encode('utf-8')
        self.expiry_seconds = expiry_seconds
    
    def generate_token(self, username: str) -> str:
        """生成JWT风格的token"""
        timestamp = int(time.time())
        payload = {
            'username': username,
            'issued_at': timestamp,
            'expires_at': timestamp + self.expiry_seconds
        }
        
        # 创建签名
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.secret_key,
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # 组合token
        token_data = {
            'payload': payload,
            'signature': signature
        }
        
        return base64.b64encode(json.dumps(token_data).encode('utf-8')).decode('utf-8')
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证token"""
        try:
            # 解码token
            token_data = json.loads(base64.b64decode(token.encode('utf-8')).decode('utf-8'))
            payload = token_data['payload']
            signature = token_data['signature']
            
            # 验证签名
            payload_str = json.dumps(payload, sort_keys=True)
            expected_signature = hmac.new(
                self.secret_key,
                payload_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Token签名验证失败")
                return None
            
            # 检查过期时间
            current_time = int(time.time())
            if current_time > payload['expires_at']:
                logger.warning("Token已过期")
                return None
            
            return payload
            
        except Exception as e:
            logger.error(f"Token验证异常: {e}")
            return None

class RateLimiter:
    """速率限制器"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # {client_ip: [(timestamp, count), ...]}
    
    def is_allowed(self, client_ip: str) -> bool:
        """检查是否允许请求"""
        current_time = time.time()
        window_start = current_time - self.window_seconds
        
        # 清理过期记录
        if client_ip in self.requests:
            self.requests[client_ip] = [
                (timestamp, count) for timestamp, count in self.requests[client_ip]
                if timestamp > window_start
            ]
        else:
            self.requests[client_ip] = []
        
        # 计算当前窗口内的请求数
        total_requests = sum(count for _, count in self.requests[client_ip])
        
        if total_requests >= self.max_requests:
            logger.warning(f"客户端 {client_ip} 超过速率限制: {total_requests}/{self.max_requests}")
            return False
        
        # 记录当前请求
        self.requests[client_ip].append((current_time, 1))
        return True

class AuthMiddleware:
    """认证中间件"""
    
    def __init__(self, config: AuthConfig):
        self.config = config
        self.token_manager = TokenManager(config.secret_key, config.token_expiry)
        self.rate_limiter = RateLimiter(
            config.max_requests_per_minute, 60
        ) if config.rate_limit_enabled else None
        
        # 不需要认证的端点
        self.public_endpoints = {
            '/health',
            '/ready',
            '/',
            '/login'
        }
    
    async def __call__(self, request: web.Request, handler):
        """中间件处理函数 - 基于aiohttp官方文档的正确实现"""

        # 检查HTTPS要求
        if self.config.require_https and request.scheme != 'https':
            logger.warning(f"HTTPS required but got {request.scheme}")
            return web.Response(
                status=426,
                text=json.dumps({"error": "HTTPS required"}),
                content_type='application/json'
            )

        # 速率限制检查
        if self.rate_limiter:
            # 获取客户端IP地址 - 基于官方文档的正确方式
            client_ip = 'unknown'

            # 方法1: 从transport获取peername (推荐)
            if hasattr(request, 'transport') and request.transport:
                peername = request.transport.get_extra_info('peername')
                if peername is not None:
                    client_ip = peername[0]  # (host, port) tuple

            # 方法2: 从headers获取代理IP
            if client_ip == 'unknown':
                client_ip = (request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or
                           request.headers.get('X-Real-IP', '') or
                           request.headers.get('CF-Connecting-IP', '') or
                           'unknown')

            if not self.rate_limiter.is_allowed(client_ip):
                return web.Response(
                    status=429,
                    text=json.dumps({"error": "Rate limit exceeded"}),
                    content_type='application/json'
                )

        # 检查是否为公开端点
        if request.path in self.public_endpoints:
            return await handler(request)

        # 认证检查
        auth_result = await self._authenticate(request)
        if not auth_result['success']:
            return web.Response(
                status=401,
                text=json.dumps({"error": auth_result['error']}),
                content_type='application/json',
                headers={'WWW-Authenticate': 'Bearer realm="MarketPrism Monitoring"'}
            )

        # 将用户信息添加到请求中 - 基于官方文档的字典接口
        request['user'] = auth_result['user']

        return await handler(request)
    
    async def _authenticate(self, request: web.Request) -> Dict[str, Any]:
        """执行认证"""
        
        # 尝试Bearer Token认证
        auth_header = request.headers.get(hdrs.AUTHORIZATION, '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]  # 移除 "Bearer " 前缀
            payload = self.token_manager.verify_token(token)
            if payload:
                return {
                    'success': True,
                    'user': {'username': payload['username'], 'auth_type': 'token'}
                }
        
        # 尝试API Key认证
        api_key = request.headers.get('X-API-Key') or request.query.get('api_key')
        if api_key and api_key == self.config.api_key:
            return {
                'success': True,
                'user': {'username': 'api_user', 'auth_type': 'api_key'}
            }
        
        # 尝试Basic Auth认证
        if auth_header.startswith('Basic '):
            try:
                credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
                username, password = credentials.split(':', 1)
                
                if username == self.config.username and password == self.config.password:
                    return {
                        'success': True,
                        'user': {'username': username, 'auth_type': 'basic'}
                    }
            except Exception as e:
                logger.error(f"Basic Auth解析失败: {e}")
        
        return {
            'success': False,
            'error': 'Authentication required. Use Bearer token, API key, or Basic auth.'
        }

async def login_handler(request: web.Request) -> web.Response:
    """登录端点，返回token"""
    try:
        data = await request.json()
        username = data.get('username')
        password = data.get('password')
        
        # 获取认证配置
        config = AuthConfig()
        
        if username == config.username and password == config.password:
            token_manager = TokenManager(config.secret_key, config.token_expiry)
            token = token_manager.generate_token(username)
            
            return web.Response(
                text=json.dumps({
                    'success': True,
                    'token': token,
                    'expires_in': config.token_expiry,
                    'token_type': 'Bearer'
                }),
                content_type='application/json'
            )
        else:
            return web.Response(
                status=401,
                text=json.dumps({'error': 'Invalid credentials'}),
                content_type='application/json'
            )
            
    except Exception as e:
        logger.error(f"登录处理异常: {e}")
        return web.Response(
            status=400,
            text=json.dumps({'error': 'Invalid request format'}),
            content_type='application/json'
        )

def create_auth_middleware() -> AuthMiddleware:
    """创建认证中间件实例"""
    config = AuthConfig()
    return AuthMiddleware(config)

# 导出主要组件
__all__ = [
    'AuthMiddleware',
    'AuthConfig', 
    'TokenManager',
    'RateLimiter',
    'create_auth_middleware',
    'login_handler'
]
