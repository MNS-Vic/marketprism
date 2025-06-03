"""
MarketPrism API网关 - 请求处理器

统一的HTTP请求处理、响应转换、错误处理和中间件支持

Week 6 Day 1 核心组件
"""

import time
import json
import logging
import asyncio
# import aiohttp  # 简化依赖
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import traceback
from urllib.parse import urljoin, urlparse

from .routing_engine import RouteRule, RouteMatch
from .load_balancer import ServiceInstance

# 设置日志
logger = logging.getLogger(__name__)

class ResponseFormat(Enum):
    """响应格式"""
    JSON = "application/json"
    XML = "application/xml"
    HTML = "text/html"
    TEXT = "text/plain"
    BINARY = "application/octet-stream"

@dataclass
class RequestContext:
    """请求上下文"""
    # 基本请求信息
    request_id: str
    method: str
    path: str
    query_params: Dict[str, List[str]] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    
    # 客户端信息
    client_ip: str = "unknown"
    user_agent: str = ""
    
    # 路由信息
    route_match: Optional[RouteMatch] = None
    target_instance: Optional[ServiceInstance] = None
    
    # 认证信息
    authenticated: bool = False
    user_id: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    
    # 处理时间
    start_time: float = field(default_factory=time.time)
    route_time: float = 0.0
    upstream_time: float = 0.0
    total_time: float = 0.0
    
    # 元数据
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass 
class ResponseContext:
    """响应上下文"""
    # 响应信息
    status_code: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    
    # 错误信息
    error: Optional[Exception] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # 性能信息
    response_time: float = 0.0
    upstream_response_time: float = 0.0
    content_length: int = 0
    
    # 处理状态
    cached: bool = False
    retried: bool = False
    retry_count: int = 0

class MiddlewareType(Enum):
    """中间件类型"""
    PRE_ROUTING = "pre_routing"      # 路由前
    POST_ROUTING = "post_routing"    # 路由后
    PRE_UPSTREAM = "pre_upstream"    # 上游请求前
    POST_UPSTREAM = "post_upstream"  # 上游响应后
    ERROR_HANDLING = "error_handling" # 错误处理

class Middleware:
    """中间件基类"""
    
    def __init__(self, name: str, middleware_type: MiddlewareType):
        self.name = name
        self.type = middleware_type
        self.enabled = True
        self.priority = 100  # 数字越小优先级越高
    
    async def process_request(self, context: RequestContext) -> bool:
        """
        处理请求
        
        Returns:
            bool: True继续处理，False中断处理
        """
        return True
    
    async def process_response(self, context: RequestContext, response: ResponseContext) -> bool:
        """
        处理响应
        
        Returns:
            bool: True继续处理，False中断处理
        """
        return True
    
    async def handle_error(self, context: RequestContext, error: Exception) -> Optional[ResponseContext]:
        """
        处理错误
        
        Returns:
            ResponseContext: 自定义响应，None表示继续抛出错误
        """
        return None

class CORSMiddleware(Middleware):
    """CORS中间件"""
    
    def __init__(self, allowed_origins: List[str] = None, 
                 allowed_methods: List[str] = None,
                 allowed_headers: List[str] = None,
                 allow_credentials: bool = False):
        super().__init__("cors", MiddlewareType.PRE_UPSTREAM)
        self.allowed_origins = allowed_origins or ["*"]
        self.allowed_methods = allowed_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allowed_headers = allowed_headers or ["Content-Type", "Authorization"]
        self.allow_credentials = allow_credentials
    
    async def process_request(self, context: RequestContext) -> bool:
        # 处理预检请求
        if context.method == "OPTIONS":
            return False  # 直接返回CORS响应，不继续处理
        return True
    
    async def process_response(self, context: RequestContext, response: ResponseContext) -> bool:
        # 添加CORS头
        origin = context.headers.get("origin", "")
        
        if "*" in self.allowed_origins or origin in self.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
        
        response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allowed_methods)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allowed_headers)
        
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return True

class RateLimitMiddleware(Middleware):
    """限流中间件"""
    
    def __init__(self, rate_limit: int = 1000, time_window: int = 60):
        super().__init__("rate_limit", MiddlewareType.PRE_ROUTING)
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.client_requests: Dict[str, List[float]] = {}
        self.priority = 10  # 高优先级
    
    async def process_request(self, context: RequestContext) -> bool:
        client_ip = context.client_ip
        current_time = time.time()
        
        # 清理过期记录
        if client_ip in self.client_requests:
            self.client_requests[client_ip] = [
                req_time for req_time in self.client_requests[client_ip]
                if current_time - req_time < self.time_window
            ]
        else:
            self.client_requests[client_ip] = []
        
        # 检查是否超出限制
        if len(self.client_requests[client_ip]) >= self.rate_limit:
            logger.warning(f"Rate limit exceeded for client {client_ip}")
            return False
        
        # 记录请求
        self.client_requests[client_ip].append(current_time)
        return True

class AuthenticationMiddleware(Middleware):
    """认证中间件"""
    
    def __init__(self, auth_handler: Optional[Callable] = None):
        super().__init__("authentication", MiddlewareType.POST_ROUTING)
        self.auth_handler = auth_handler
        self.priority = 20
    
    async def process_request(self, context: RequestContext) -> bool:
        # 检查是否需要认证
        if context.route_match and context.route_match.route_rule:
            route_rule = context.route_match.route_rule
            
            # 如果路由需要认证
            if "auth_required" in route_rule.tags and route_rule.tags["auth_required"] == "true":
                if self.auth_handler:
                    auth_result = await self.auth_handler(context)
                    if not auth_result:
                        logger.warning(f"Authentication failed for request {context.request_id}")
                        return False
                else:
                    # 默认认证逻辑：检查Authorization头
                    auth_header = context.headers.get("authorization", "")
                    if not auth_header.startswith("Bearer "):
                        logger.warning(f"Missing or invalid authorization header for request {context.request_id}")
                        return False
                    
                    # 简单的token验证（实际中应该验证JWT等）
                    token = auth_header[7:]  # 移除"Bearer "
                    if len(token) < 10:  # 简单验证
                        logger.warning(f"Invalid token for request {context.request_id}")
                        return False
                    
                    context.authenticated = True
                    context.user_id = "user_from_token"  # 实际中从token解析
        
        return True

class LoggingMiddleware(Middleware):
    """日志中间件"""
    
    def __init__(self, log_requests: bool = True, log_responses: bool = True):
        super().__init__("logging", MiddlewareType.PRE_ROUTING)
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.priority = 5  # 最高优先级
    
    async def process_request(self, context: RequestContext) -> bool:
        if self.log_requests:
            logger.info(f"Request {context.request_id}: {context.method} {context.path} "
                       f"from {context.client_ip}")
        return True
    
    async def process_response(self, context: RequestContext, response: ResponseContext) -> bool:
        if self.log_responses:
            logger.info(f"Response {context.request_id}: {response.status_code} "
                       f"({response.response_time:.2f}ms)")
        return True

class RequestHandler:
    """
    请求处理器
    
    统一处理HTTP请求的路由、认证、限流、转发等功能
    """
    
    def __init__(self, enable_access_log: bool = True):
        self.enable_access_log = enable_access_log
        
        # 中间件管理
        self.middleware_stack: Dict[MiddlewareType, List[Middleware]] = {
            middleware_type: [] for middleware_type in MiddlewareType
        }
        
        # HTTP客户端
        self.http_client: Optional[aiohttp.ClientSession] = None
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_response_time': 0.0,
            'status_code_counts': {},
            'method_counts': {},
            'error_counts': {},
        }
        
        logger.info("RequestHandler initialized")
    
    async def start(self):
        """启动请求处理器"""
        # 模拟HTTP客户端创建
        # timeout = aiohttp.ClientTimeout(total=30)
        # self.http_client = aiohttp.ClientSession(timeout=timeout)
        self.http_client = "mock_client"  # 简化实现
        
        logger.info("RequestHandler started")
    
    async def stop(self):
        """停止请求处理器"""
        # 模拟关闭HTTP客户端
        # if self.http_client:
        #     await self.http_client.close()
        self.http_client = None
        
        logger.info("RequestHandler stopped")
    
    def add_middleware(self, middleware: Middleware):
        """添加中间件"""
        middleware_list = self.middleware_stack[middleware.type]
        middleware_list.append(middleware)
        
        # 按优先级排序
        middleware_list.sort(key=lambda m: m.priority)
        
        logger.info(f"Added middleware: {middleware.name} ({middleware.type.value})")
    
    def remove_middleware(self, middleware_name: str, middleware_type: MiddlewareType) -> bool:
        """移除中间件"""
        middleware_list = self.middleware_stack[middleware_type]
        
        for i, middleware in enumerate(middleware_list):
            if middleware.name == middleware_name:
                del middleware_list[i]
                logger.info(f"Removed middleware: {middleware_name} ({middleware_type.value})")
                return True
        
        return False
    
    async def handle_request(self, context: RequestContext, 
                           route_handler: Callable, 
                           load_balancer_handler: Callable) -> ResponseContext:
        """
        处理HTTP请求
        
        Args:
            context: 请求上下文
            route_handler: 路由处理函数
            load_balancer_handler: 负载均衡处理函数
            
        Returns:
            ResponseContext: 响应上下文
        """
        response = ResponseContext()
        
        try:
            # 更新统计
            self.stats['total_requests'] += 1
            self.stats['method_counts'][context.method] = self.stats['method_counts'].get(context.method, 0) + 1
            
            # 执行PRE_ROUTING中间件
            if not await self._execute_middleware(MiddlewareType.PRE_ROUTING, context, response):
                response.status_code = 403
                response.error_message = "Request blocked by middleware"
                return response
            
            # 路由匹配
            route_start_time = time.time()
            context.route_match = await route_handler(context.path, context.method, context.headers, context.client_ip)
            context.route_time = time.time() - route_start_time
            
            if not context.route_match or not context.route_match.matched:
                response.status_code = 404
                response.error_message = "Route not found"
                return response
            
            # 执行POST_ROUTING中间件
            if not await self._execute_middleware(MiddlewareType.POST_ROUTING, context, response):
                response.status_code = 403
                response.error_message = "Request blocked by middleware"
                return response
            
            # 选择服务实例
            request_context_dict = {
                'path': context.path,
                'method': context.method,
                'headers': context.headers,
                'client_ip': context.client_ip,
                'route_rule': context.route_match.route_rule,
                'path_params': context.route_match.path_params,
                'query_params': context.query_params,
            }
            
            context.target_instance = await load_balancer_handler(
                context.route_match.route_rule.target_service, 
                request_context_dict
            )
            
            if not context.target_instance:
                response.status_code = 503
                response.error_message = "Service unavailable"
                return response
            
            # 执行PRE_UPSTREAM中间件
            if not await self._execute_middleware(MiddlewareType.PRE_UPSTREAM, context, response):
                response.status_code = 403
                response.error_message = "Request blocked by middleware"
                return response
            
            # 转发请求到上游服务
            upstream_start_time = time.time()
            await self._forward_request(context, response)
            context.upstream_time = time.time() - upstream_start_time
            
            # 执行POST_UPSTREAM中间件
            await self._execute_middleware(MiddlewareType.POST_UPSTREAM, context, response)
            
        except Exception as e:
            logger.error(f"Error handling request {context.request_id}: {e}")
            logger.error(traceback.format_exc())
            
            response.error = e
            response.status_code = 500
            response.error_message = "Internal server error"
            
            # 执行错误处理中间件
            error_response = await self._execute_error_middleware(context, e)
            if error_response:
                response = error_response
        
        finally:
            # 计算总处理时间
            context.total_time = time.time() - context.start_time
            response.response_time = context.total_time
            
            # 更新统计
            self._update_stats(context, response)
            
            # 访问日志
            if self.enable_access_log:
                self._log_access(context, response)
        
        return response
    
    async def _execute_middleware(self, middleware_type: MiddlewareType, 
                                context: RequestContext, 
                                response: ResponseContext) -> bool:
        """执行中间件"""
        for middleware in self.middleware_stack[middleware_type]:
            if not middleware.enabled:
                continue
            
            try:
                if middleware_type in [MiddlewareType.PRE_ROUTING, MiddlewareType.POST_ROUTING, MiddlewareType.PRE_UPSTREAM]:
                    if not await middleware.process_request(context):
                        logger.debug(f"Request blocked by middleware: {middleware.name}")
                        return False
                else:  # POST_UPSTREAM
                    if not await middleware.process_response(context, response):
                        logger.debug(f"Response processing stopped by middleware: {middleware.name}")
                        return False
            
            except Exception as e:
                logger.error(f"Error in middleware {middleware.name}: {e}")
                # 继续执行其他中间件
        
        return True
    
    async def _execute_error_middleware(self, context: RequestContext, 
                                      error: Exception) -> Optional[ResponseContext]:
        """执行错误处理中间件"""
        for middleware in self.middleware_stack[MiddlewareType.ERROR_HANDLING]:
            if not middleware.enabled:
                continue
            
            try:
                error_response = await middleware.handle_error(context, error)
                if error_response:
                    return error_response
            
            except Exception as e:
                logger.error(f"Error in error handling middleware {middleware.name}: {e}")
        
        return None
    
    async def _forward_request(self, context: RequestContext, response: ResponseContext):
        """转发请求到上游服务"""
        if not self.http_client or not context.target_instance or not context.route_match:
            raise Exception("Invalid state for request forwarding")
        
        route_rule = context.route_match.route_rule
        target_instance = context.target_instance
        
        # 构建目标URL
        target_path = route_rule.target_path or context.path
        if route_rule.rewrite and route_rule.rewrite.enabled:
            target_path = route_rule.rewrite.target_path or target_path
        
        # 处理路径参数替换
        if context.route_match.path_params:
            for param_name, param_value in context.route_match.path_params.items():
                target_path = target_path.replace(f"{{{param_name}}}", param_value)
        
        # 构建完整URL
        scheme = "https" if target_instance.port == 443 else "http"
        target_url = f"{scheme}://{target_instance.host}:{target_instance.port}{target_path}"
        
        # 处理查询参数
        if context.query_params:
            query_string = "&".join([
                f"{key}={value}" 
                for key, values in context.query_params.items() 
                for value in values
            ])
            target_url += f"?{query_string}"
        
        # 准备请求头
        headers = context.headers.copy()
        
        # 添加代理头
        headers["X-Forwarded-For"] = context.client_ip
        headers["X-Forwarded-Proto"] = "http"  # 或从原始请求推断
        headers["X-Real-IP"] = context.client_ip
        
        # 处理重写头
        if route_rule.rewrite and route_rule.rewrite.enabled:
            # 添加头
            for key, value in route_rule.rewrite.add_headers.items():
                headers[key] = value
            
            # 移除头
            for key in route_rule.rewrite.remove_headers:
                headers.pop(key, None)
        
        # 移除hop-by-hop头
        hop_by_hop_headers = [
            'connection', 'keep-alive', 'proxy-authenticate',
            'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade'
        ]
        for header in hop_by_hop_headers:
            headers.pop(header, None)
        
        try:
            # 模拟请求转发
            # 简化实现：直接返回模拟响应
            response.status_code = 200
            response.body = b'{"message": "success", "target": "' + target_url.encode() + b'"}'
            response.content_length = len(response.body)
            
            # 设置基本响应头
            response.headers["Content-Type"] = "application/json"
            response.headers["Content-Length"] = str(response.content_length)
            
            logger.debug(f"Simulated forwarded request to {target_url}, status: {response.status_code}")
        
        except asyncio.TimeoutError:
            logger.error(f"Timeout forwarding request to {target_url}")
            response.status_code = 504
            response.error_message = "Gateway timeout"
            
        except Exception as e:
            logger.error(f"Error forwarding request to {target_url}: {e}")
            response.status_code = 502
            response.error_message = "Bad gateway"
            response.error = e
    
    def _update_stats(self, context: RequestContext, response: ResponseContext):
        """更新统计信息"""
        # 更新响应时间统计
        self.stats['total_response_time'] += response.response_time
        
        # 更新状态码统计
        status_code = response.status_code
        self.stats['status_code_counts'][status_code] = self.stats['status_code_counts'].get(status_code, 0) + 1
        
        # 更新成功/失败统计
        if 200 <= status_code < 400:
            self.stats['successful_requests'] += 1
        else:
            self.stats['failed_requests'] += 1
        
        # 更新错误统计
        if response.error:
            error_type = type(response.error).__name__
            self.stats['error_counts'][error_type] = self.stats['error_counts'].get(error_type, 0) + 1
    
    def _log_access(self, context: RequestContext, response: ResponseContext):
        """记录访问日志"""
        log_data = {
            'request_id': context.request_id,
            'timestamp': context.start_time,
            'client_ip': context.client_ip,
            'method': context.method,
            'path': context.path,
            'status_code': response.status_code,
            'response_time': response.response_time,
            'content_length': response.content_length,
            'user_agent': context.user_agent,
            'route_time': context.route_time,
            'upstream_time': context.upstream_time,
        }
        
        if context.target_instance:
            log_data['target_instance'] = context.target_instance.address
        
        if context.route_match and context.route_match.route_rule:
            log_data['route_rule'] = context.route_match.route_rule.rule_id
        
        if response.error_message:
            log_data['error_message'] = response.error_message
        
        logger.info(f"Access log: {json.dumps(log_data)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        
        if self.stats['total_requests'] > 0:
            stats['success_rate'] = self.stats['successful_requests'] / self.stats['total_requests'] * 100
            stats['average_response_time'] = self.stats['total_response_time'] / self.stats['total_requests']
        else:
            stats['success_rate'] = 0.0
            stats['average_response_time'] = 0.0
        
        return stats

class ResponseHandler:
    """
    响应处理器
    
    处理响应转换、缓存、压缩等功能
    """
    
    def __init__(self):
        self.response_transformers: List[Callable] = []
        
        logger.info("ResponseHandler initialized")
    
    def add_transformer(self, transformer: Callable):
        """添加响应转换器"""
        self.response_transformers.append(transformer)
    
    async def process_response(self, context: RequestContext, response: ResponseContext) -> ResponseContext:
        """处理响应"""
        # 应用响应转换器
        for transformer in self.response_transformers:
            try:
                response = await transformer(context, response)
            except Exception as e:
                logger.error(f"Error in response transformer: {e}")
        
        return response

# 便利函数
def create_request_context(request_id: str, method: str, path: str, **kwargs) -> RequestContext:
    """创建请求上下文的便利函数"""
    return RequestContext(
        request_id=request_id,
        method=method,
        path=path,
        **kwargs
    )