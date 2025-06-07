"""
API Gateway Service - Phase 2
统一API网关服务，负责请求路由、认证、限流等功能

这是MarketPrism微服务架构的统一入口，提供：
1. 统一API入口和路由
2. 服务发现和负载均衡  
3. 认证和授权
4. 请求限流和熔断
5. API版本管理
6. 请求/响应转换
7. 缓存和压缩
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime, timedelta
import aiohttp
from aiohttp import web, ClientTimeout
import json
import jwt
from collections import defaultdict, deque

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入微服务框架
from core.service_framework import BaseService


class RateLimiter:
    """令牌桶算法实现的速率限制器"""
    
    def __init__(self, max_requests: int = 100, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.buckets: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, client_id: str) -> bool:
        """检查是否允许请求"""
        now = time.time()
        bucket = self.buckets[client_id]
        
        # 移除过期的请求记录
        while bucket and bucket[0] <= now - self.time_window:
            bucket.popleft()
        
        # 检查是否超过限制
        if len(bucket) >= self.max_requests:
            return False
        
        # 添加当前请求
        bucket.append(now)
        return True
    
    def get_remaining(self, client_id: str) -> int:
        """获取剩余请求次数"""
        bucket = self.buckets[client_id]
        return max(0, self.max_requests - len(bucket))


class CircuitBreaker:
    """熔断器实现"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        """包装函数调用并提供熔断保护"""
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'HALF_OPEN'
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """成功时重置状态"""
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def _on_failure(self):
        """失败时更新状态"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'


class ServiceRegistry:
    """服务注册和发现"""
    
    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}
        self.health_check_interval = 30
        self.logger = structlog.get_logger(__name__)
    
    def register_service(self, service_name: str, host: str, port: int, health_endpoint: str = "/health"):
        """注册服务"""
        service_info = {
            'host': host,
            'port': port,
            'health_endpoint': health_endpoint,
            'base_url': f"http://{host}:{port}",
            'last_health_check': None,
            'healthy': True,
            'registered_at': datetime.utcnow()
        }
        
        self.services[service_name] = service_info
        self.logger.info(f"服务注册成功: {service_name}", service_info=service_info)
    
    def get_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        """获取服务信息"""
        return self.services.get(service_name)
    
    def get_service_url(self, service_name: str) -> Optional[str]:
        """获取服务URL"""
        service = self.get_service(service_name)
        return service['base_url'] if service and service['healthy'] else None
    
    def list_services(self) -> Dict[str, Dict[str, Any]]:
        """列出所有服务"""
        return self.services.copy()
    
    async def health_check_services(self):
        """健康检查所有注册的服务"""
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=5)) as session:
            for service_name, service_info in self.services.items():
                try:
                    health_url = f"{service_info['base_url']}{service_info['health_endpoint']}"
                    async with session.get(health_url) as response:
                        if response.status == 200:
                            service_info['healthy'] = True
                            service_info['last_health_check'] = datetime.utcnow()
                        else:
                            service_info['healthy'] = False
                            self.logger.warning(f"服务健康检查失败: {service_name}", status=response.status)
                
                except Exception as e:
                    service_info['healthy'] = False
                    self.logger.error(f"服务健康检查异常: {service_name}", error=str(e))


class APIGatewayService(BaseService):
    """
    API网关服务
    
    提供统一的API入口，包括：
    - 请求路由和代理
    - 服务发现和负载均衡
    - 认证和授权
    - 请求限流和熔断
    - API版本管理
    - 缓存和响应转换
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            service_name="api-gateway",
            service_version="1.0.0", 
            service_port=config.get('port', 8080),
            config=config
        )
        
        self.logger = structlog.get_logger(__name__)
        
        # 核心组件
        self.service_registry = ServiceRegistry()
        self.rate_limiter = RateLimiter(
            max_requests=config.get('rate_limit_requests', 100),
            time_window=config.get('rate_limit_window', 60)
        )
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # 配置
        self.jwt_secret = config.get('jwt_secret', 'your-secret-key')
        self.jwt_algorithm = config.get('jwt_algorithm', 'HS256')
        self.enable_auth = config.get('enable_auth', False)
        self.enable_rate_limiting = config.get('enable_rate_limiting', True)
        self.enable_circuit_breaker = config.get('enable_circuit_breaker', True)
        
        # 路由配置
        self.routes = config.get('routes', {})
        
        # 缓存
        self.response_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = config.get('cache_ttl', 300)  # 5分钟
        
        # 统计
        self.request_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'rate_limited_requests': 0,
            'circuit_breaker_trips': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        self.logger.info("API Gateway Service 初始化完成")
    
    async def initialize_service(self) -> bool:
        """初始化网关服务"""
        try:
            # 注册默认的微服务
            self._register_default_services()
            
            # 设置路由
            self._setup_routes()
            
            # 启动健康检查任务
            asyncio.create_task(self._health_check_loop())
            
            self.logger.info("API Gateway Service 初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"API Gateway Service 初始化失败: {e}")
            return False
    
    async def start_service(self) -> bool:
        """启动网关服务"""
        try:
            self.logger.info("API Gateway Service 启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动API Gateway Service失败: {e}")
            return False
    
    async def stop_service(self) -> bool:
        """停止网关服务"""
        try:
            self.logger.info("API Gateway Service 已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"停止API Gateway Service失败: {e}")
            return False
    
    def _register_default_services(self):
        """注册默认的微服务"""
        # 注册已知的微服务
        default_services = {
            'market-data-collector': {'host': 'localhost', 'port': 8081},
            'data-storage-service': {'host': 'localhost', 'port': 8082},
            'monitoring-service': {'host': 'localhost', 'port': 8083},
            'scheduler-service': {'host': 'localhost', 'port': 8084},
            'message-broker-service': {'host': 'localhost', 'port': 8085}
        }
        
        for service_name, service_config in default_services.items():
            self.service_registry.register_service(
                service_name, 
                service_config['host'], 
                service_config['port']
            )
    
    def _setup_routes(self):
        """设置API路由"""
        # 添加网关管理路由
        self.app.router.add_get('/api/v1/gateway/status', self._gateway_status)
        self.app.router.add_get('/api/v1/gateway/services', self._list_services)
        self.app.router.add_post('/api/v1/gateway/services', self._register_service)
        self.app.router.add_get('/api/v1/gateway/stats', self._get_stats)
        
        # 添加通用代理路由
        self.app.router.add_route('*', '/api/v1/{service}/{path:.*}', self._proxy_request)
        
        # 添加WebSocket代理路由
        self.app.router.add_get('/ws/{service}/{path:.*}', self._proxy_websocket)
        
        # 添加认证路由
        if self.enable_auth:
            self.app.router.add_post('/api/v1/auth/login', self._login)
            self.app.router.add_post('/api/v1/auth/refresh', self._refresh_token)
    
    async def _proxy_request(self, request):
        """代理HTTP请求到微服务"""
        try:
            # 获取目标服务
            service_name = request.match_info['service']
            path = request.match_info['path']
            
            # 请求统计
            self.request_stats['total_requests'] += 1
            
            # 获取客户端ID（用于限流）
            client_id = self._get_client_id(request)
            
            # 认证检查
            if self.enable_auth and not await self._check_auth(request):
                return web.json_response(
                    {'error': 'Unauthorized'}, 
                    status=401
                )
            
            # 速率限制检查
            if self.enable_rate_limiting and not self.rate_limiter.is_allowed(client_id):
                self.request_stats['rate_limited_requests'] += 1
                return web.json_response(
                    {'error': 'Rate limit exceeded'}, 
                    status=429,
                    headers={'X-RateLimit-Remaining': '0'}
                )
            
            # 获取服务URL
            service_url = self.service_registry.get_service_url(service_name)
            if not service_url:
                return web.json_response(
                    {'error': f'Service {service_name} not available'}, 
                    status=503
                )
            
            # 构建目标URL
            target_url = f"{service_url}/api/v1/{path}"
            if request.query_string:
                target_url += f"?{request.query_string}"
            
            # 检查缓存
            cache_key = f"{request.method}:{target_url}"
            if request.method == 'GET':
                cached_response = self._get_cached_response(cache_key)
                if cached_response:
                    self.request_stats['cache_hits'] += 1
                    return web.json_response(cached_response['data'])
                self.request_stats['cache_misses'] += 1
            
            # 获取或创建熔断器
            circuit_breaker = self._get_circuit_breaker(service_name)
            
            # 代理请求
            try:
                if self.enable_circuit_breaker:
                    response_data = await circuit_breaker.call(
                        self._make_request, 
                        target_url, 
                        request
                    )
                else:
                    response_data = await self._make_request(target_url, request)
                
                # 缓存GET请求的响应
                if request.method == 'GET' and response_data['status'] == 200:
                    self._cache_response(cache_key, response_data['data'])
                
                self.request_stats['successful_requests'] += 1
                
                # 添加网关头信息
                headers = {
                    'X-Gateway-Service': service_name,
                    'X-Gateway-Timestamp': datetime.utcnow().isoformat(),
                    'X-RateLimit-Remaining': str(self.rate_limiter.get_remaining(client_id))
                }
                
                return web.json_response(
                    response_data['data'], 
                    status=response_data['status'],
                    headers=headers
                )
                
            except Exception as e:
                self.request_stats['failed_requests'] += 1
                
                if 'Circuit breaker is OPEN' in str(e):
                    self.request_stats['circuit_breaker_trips'] += 1
                    return web.json_response(
                        {'error': 'Service temporarily unavailable'}, 
                        status=503
                    )
                
                self.logger.error(f"代理请求失败: {e}", target_url=target_url)
                return web.json_response(
                    {'error': 'Internal server error'}, 
                    status=500
                )
            
        except Exception as e:
            self.logger.error(f"处理代理请求失败: {e}")
            return web.json_response(
                {'error': 'Gateway error'}, 
                status=500
            )
    
    async def _make_request(self, target_url: str, request):
        """发起HTTP请求到目标服务"""
        timeout = ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 准备请求数据
            headers = dict(request.headers)
            
            # 移除可能导致问题的头
            headers.pop('Host', None)
            headers.pop('Content-Length', None)
            
            # 获取请求体
            data = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                if request.content_type == 'application/json':
                    try:
                        data = await request.json()
                        data = json.dumps(data)
                        headers['Content-Type'] = 'application/json'
                    except:
                        data = await request.text()
                else:
                    data = await request.read()
            
            # 发起请求
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=data
            ) as response:
                try:
                    response_data = await response.json()
                except:
                    response_data = await response.text()
                
                return {
                    'status': response.status,
                    'data': response_data
                }
    
    async def _proxy_websocket(self, request):
        """代理WebSocket连接到微服务"""
        try:
            service_name = request.match_info['service']
            path = request.match_info['path']
            
            # 获取服务URL
            service_url = self.service_registry.get_service_url(service_name)
            if not service_url:
                return web.json_response(
                    {'error': f'Service {service_name} not available'}, 
                    status=503
                )
            
            # 构建WebSocket URL
            ws_url = service_url.replace('http://', 'ws://').replace('https://', 'wss://')
            target_ws_url = f"{ws_url}/ws/{path}"
            
            # 升级到WebSocket
            ws_gateway = web.WebSocketResponse()
            await ws_gateway.prepare(request)
            
            # 连接到目标服务
            session = aiohttp.ClientSession()
            try:
                async with session.ws_connect(target_ws_url) as ws_target:
                    # 双向消息转发
                    async def forward_to_target():
                        async for msg in ws_gateway:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await ws_target.send_str(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await ws_target.send_bytes(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break
                    
                    async def forward_to_gateway():
                        async for msg in ws_target:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await ws_gateway.send_str(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await ws_gateway.send_bytes(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break
                    
                    # 启动双向转发
                    await asyncio.gather(
                        forward_to_target(),
                        forward_to_gateway(),
                        return_exceptions=True
                    )
            
            finally:
                await session.close()
            
            return ws_gateway
            
        except Exception as e:
            self.logger.error(f"WebSocket代理失败: {e}")
            return web.json_response(
                {'error': 'WebSocket proxy error'}, 
                status=500
            )
    
    def _get_client_id(self, request) -> str:
        """获取客户端ID（用于限流）"""
        # 优先使用API Key
        api_key = request.headers.get('X-API-Key')
        if api_key:
            return f"api_key:{api_key}"
        
        # 使用IP地址
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return f"ip:{forwarded_for.split(',')[0].strip()}"
        
        return f"ip:{request.remote}"
    
    async def _check_auth(self, request) -> bool:
        """检查认证"""
        if not self.enable_auth:
            return True
        
        # 检查JWT Token
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False
        
        token = auth_header[7:]  # 移除 'Bearer ' 前缀
        
        try:
            payload = jwt.decode(
                token, 
                self.jwt_secret, 
                algorithms=[self.jwt_algorithm]
            )
            
            # 检查token是否过期
            if payload.get('exp', 0) < time.time():
                return False
            
            # 将用户信息添加到请求中
            request['user'] = payload
            return True
            
        except jwt.InvalidTokenError:
            return False
    
    def _get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()
        return self.circuit_breakers[service_name]
    
    def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取缓存的响应"""
        if cache_key in self.response_cache:
            cached = self.response_cache[cache_key]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                return cached
            else:
                # 缓存过期，删除
                del self.response_cache[cache_key]
        return None
    
    def _cache_response(self, cache_key: str, data: Any):
        """缓存响应"""
        self.response_cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
        
        # 清理过期缓存
        now = time.time()
        expired_keys = [
            key for key, value in self.response_cache.items()
            if now - value['timestamp'] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.response_cache[key]
    
    async def _health_check_loop(self):
        """定期健康检查循环"""
        while True:
            try:
                await self.service_registry.health_check_services()
                await asyncio.sleep(30)  # 30秒检查一次
            except Exception as e:
                self.logger.error(f"健康检查失败: {e}")
                await asyncio.sleep(5)
    
    # API端点实现
    
    async def _gateway_status(self, request):
        """获取网关状态"""
        return web.json_response({
            'service': 'api-gateway',
            'version': self.service_version,
            'status': 'running',
            'timestamp': datetime.utcnow().isoformat(),
            'uptime': (datetime.utcnow() - self.start_time).total_seconds() if hasattr(self, 'start_time') else 0,
            'config': {
                'enable_auth': self.enable_auth,
                'enable_rate_limiting': self.enable_rate_limiting,
                'enable_circuit_breaker': self.enable_circuit_breaker,
                'cache_ttl': self.cache_ttl
            },
            'registered_services': len(self.service_registry.services),
            'active_circuit_breakers': len(self.circuit_breakers),
            'cache_size': len(self.response_cache)
        })
    
    async def _list_services(self, request):
        """列出注册的服务"""
        services = self.service_registry.list_services()
        return web.json_response({
            'services': services,
            'total': len(services)
        })
    
    async def _register_service(self, request):
        """注册新服务"""
        try:
            data = await request.json()
            service_name = data['service_name']
            host = data['host']
            port = data['port']
            health_endpoint = data.get('health_endpoint', '/health')
            
            self.service_registry.register_service(
                service_name, host, port, health_endpoint
            )
            
            return web.json_response({
                'success': True,
                'message': f'Service {service_name} registered successfully'
            })
            
        except Exception as e:
            return web.json_response(
                {'error': str(e)}, 
                status=400
            )
    
    async def _get_stats(self, request):
        """获取网关统计"""
        circuit_breaker_stats = {}
        for service_name, cb in self.circuit_breakers.items():
            circuit_breaker_stats[service_name] = {
                'state': cb.state,
                'failure_count': cb.failure_count,
                'last_failure_time': cb.last_failure_time
            }
        
        return web.json_response({
            'request_stats': self.request_stats,
            'circuit_breaker_stats': circuit_breaker_stats,
            'cache_stats': {
                'size': len(self.response_cache),
                'hit_rate': (
                    self.request_stats['cache_hits'] / 
                    (self.request_stats['cache_hits'] + self.request_stats['cache_misses'])
                    if (self.request_stats['cache_hits'] + self.request_stats['cache_misses']) > 0 
                    else 0
                )
            },
            'rate_limiter_stats': {
                'active_clients': len(self.rate_limiter.buckets)
            }
        })
    
    async def _login(self, request):
        """用户登录"""
        try:
            data = await request.json()
            username = data.get('username')
            password = data.get('password')
            
            # 这里应该验证用户凭据
            # 为了演示，我们使用简单的硬编码验证
            if username == 'admin' and password == 'password':
                # 生成JWT token
                payload = {
                    'user_id': username,
                    'exp': time.time() + 3600,  # 1小时过期
                    'iat': time.time()
                }
                
                token = jwt.encode(
                    payload, 
                    self.jwt_secret, 
                    algorithm=self.jwt_algorithm
                )
                
                return web.json_response({
                    'access_token': token,
                    'token_type': 'bearer',
                    'expires_in': 3600
                })
            
            return web.json_response(
                {'error': 'Invalid credentials'}, 
                status=401
            )
            
        except Exception as e:
            return web.json_response(
                {'error': str(e)}, 
                status=400
            )
    
    async def _refresh_token(self, request):
        """刷新token"""
        try:
            data = await request.json()
            old_token = data.get('refresh_token')
            
            # 验证旧token
            try:
                payload = jwt.decode(
                    old_token, 
                    self.jwt_secret, 
                    algorithms=[self.jwt_algorithm],
                    options={"verify_exp": False}  # 允许过期的token用于刷新
                )
                
                # 生成新token
                new_payload = {
                    'user_id': payload['user_id'],
                    'exp': time.time() + 3600,
                    'iat': time.time()
                }
                
                new_token = jwt.encode(
                    new_payload, 
                    self.jwt_secret, 
                    algorithm=self.jwt_algorithm
                )
                
                return web.json_response({
                    'access_token': new_token,
                    'token_type': 'bearer',
                    'expires_in': 3600
                })
                
            except jwt.InvalidTokenError:
                return web.json_response(
                    {'error': 'Invalid refresh token'}, 
                    status=401
                )
            
        except Exception as e:
            return web.json_response(
                {'error': str(e)}, 
                status=400
            )


async def main():
    """主函数"""
    try:
        # 加载配置
        import yaml
        config_path = project_root / "config" / "services.yaml"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                services_config = yaml.safe_load(f)
            config = services_config.get('api-gateway-service', {})
        else:
            # 默认配置
            config = {
                'port': 8080,
                'enable_auth': False,
                'enable_rate_limiting': True,
                'enable_circuit_breaker': True,
                'rate_limit_requests': 100,
                'rate_limit_window': 60,
                'cache_ttl': 300,
                'jwt_secret': 'your-secret-key',
                'jwt_algorithm': 'HS256'
            }
        
        # 创建并启动服务
        service = APIGatewayService(config)
        await service.run()
        
    except KeyboardInterrupt:
        print("服务被用户中断")
    except Exception as e:
        print(f"服务启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())