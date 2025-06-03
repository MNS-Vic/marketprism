#!/usr/bin/env python3
"""
🚦 API网关数据平面

负责处理实际的API请求流量，包括请求路由、中间件处理、
安全检查、性能优化等核心数据处理功能。
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from aiohttp import web, ClientSession, ClientTimeout
import aiofiles
import json

logger = logging.getLogger(__name__)


@dataclass
class RequestContext:
    """请求上下文"""
    request_id: str
    method: str
    path: str
    headers: Dict[str, str]
    query_params: Dict[str, str]
    body: bytes
    start_time: float
    client_ip: str
    user_agent: str
    metadata: Dict[str, Any]


@dataclass
class ResponseContext:
    """响应上下文"""
    status_code: int
    headers: Dict[str, str]
    body: bytes
    processing_time: float
    backend_response_time: float
    cache_hit: bool
    errors: List[str]


class RequestPipeline:
    """🔄 请求处理流水线"""
    
    def __init__(self):
        self.middleware_chain = []
        self.pre_processors = []
        self.post_processors = []
        
        logger.info("RequestPipeline初始化完成")
    
    def add_middleware(self, middleware: Callable, priority: int = 100):
        """添加中间件"""
        self.middleware_chain.append((priority, middleware))
        self.middleware_chain.sort(key=lambda x: x[0])  # 按优先级排序
        
        logger.info(f"中间件已添加: {middleware.__name__}, 优先级: {priority}")
    
    def add_pre_processor(self, processor: Callable):
        """添加请求预处理器"""
        self.pre_processors.append(processor)
        logger.info(f"请求预处理器已添加: {processor.__name__}")
    
    def add_post_processor(self, processor: Callable):
        """添加响应后处理器"""
        self.post_processors.append(processor)
        logger.info(f"响应后处理器已添加: {processor.__name__}")
    
    async def process_request(self, context: RequestContext) -> RequestContext:
        """处理请求"""
        # 执行预处理器
        for processor in self.pre_processors:
            try:
                context = await processor(context)
            except Exception as e:
                logger.error(f"请求预处理失败: {e}")
                raise
        
        # 执行中间件链
        for priority, middleware in self.middleware_chain:
            try:
                context = await middleware(context)
            except Exception as e:
                logger.error(f"中间件处理失败 {middleware.__name__}: {e}")
                raise
        
        return context
    
    async def process_response(self, context: ResponseContext) -> ResponseContext:
        """处理响应"""
        # 执行后处理器
        for processor in self.post_processors:
            try:
                context = await processor(context)
            except Exception as e:
                logger.error(f"响应后处理失败: {e}")
                # 响应处理错误不应该中断流程
        
        return context


class ResponsePipeline:
    """📤 响应处理流水线"""
    
    def __init__(self):
        self.filters = []
        self.transformers = []
        
        logger.info("ResponsePipeline初始化完成")
    
    def add_filter(self, filter_func: Callable):
        """添加响应过滤器"""
        self.filters.append(filter_func)
        logger.info(f"响应过滤器已添加: {filter_func.__name__}")
    
    def add_transformer(self, transformer: Callable):
        """添加响应转换器"""
        self.transformers.append(transformer)
        logger.info(f"响应转换器已添加: {transformer.__name__}")
    
    async def process(self, response_context: ResponseContext) -> ResponseContext:
        """处理响应"""
        # 执行过滤器
        for filter_func in self.filters:
            try:
                if not await filter_func(response_context):
                    logger.warning(f"响应被过滤器拒绝: {filter_func.__name__}")
                    break
            except Exception as e:
                logger.error(f"响应过滤失败: {e}")
        
        # 执行转换器
        for transformer in self.transformers:
            try:
                response_context = await transformer(response_context)
            except Exception as e:
                logger.error(f"响应转换失败: {e}")
        
        return response_context


class TrafficManager:
    """🚦 流量管理器"""
    
    def __init__(self):
        self.routes = {}
        self.load_balancers = {}
        self.circuit_breakers = {}
        self.rate_limiters = {}
        self.client_session = None
        
        logger.info("TrafficManager初始化完成")
    
    async def initialize(self):
        """初始化流量管理器"""
        # 创建HTTP客户端会话
        timeout = ClientTimeout(total=30.0, connect=5.0)
        self.client_session = ClientSession(timeout=timeout)
        
        logger.info("流量管理器初始化完成")
    
    async def stop(self):
        """停止流量管理器"""
        if self.client_session:
            await self.client_session.close()
        
        logger.info("流量管理器已停止")
    
    def register_route(self, path_pattern: str, backend_urls: List[str], method: str = "GET"):
        """注册路由"""
        self.routes[f"{method}:{path_pattern}"] = {
            "pattern": path_pattern,
            "backends": backend_urls,
            "method": method,
            "created_at": time.time()
        }
        
        logger.info(f"路由已注册: {method} {path_pattern} -> {backend_urls}")
    
    def find_route(self, method: str, path: str) -> Optional[Dict[str, Any]]:
        """查找匹配的路由"""
        route_key = f"{method}:{path}"
        
        # 精确匹配
        if route_key in self.routes:
            return self.routes[route_key]
        
        # 模式匹配 (简化实现)
        for key, route in self.routes.items():
            if key.startswith(f"{method}:") and self._path_matches(path, route["pattern"]):
                return route
        
        return None
    
    def _path_matches(self, path: str, pattern: str) -> bool:
        """检查路径是否匹配模式"""
        # 简化实现 - 支持基本的通配符匹配
        if "*" in pattern:
            prefix = pattern.split("*")[0]
            return path.startswith(prefix)
        
        return path == pattern
    
    async def forward_request(self, context: RequestContext) -> ResponseContext:
        """转发请求到后端服务"""
        route = self.find_route(context.method, context.path)
        if not route:
            return ResponseContext(
                status_code=404,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"error": "Route not found"}).encode(),
                processing_time=0.0,
                backend_response_time=0.0,
                cache_hit=False,
                errors=["Route not found"]
            )
        
        # 选择后端服务器
        backend_url = self._select_backend(route["backends"])
        if not backend_url:
            return ResponseContext(
                status_code=503,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"error": "No backend available"}).encode(),
                processing_time=0.0,
                backend_response_time=0.0,
                cache_hit=False,
                errors=["No backend available"]
            )
        
        # 发送请求到后端
        try:
            backend_start = time.time()
            url = f"{backend_url}{context.path}"
            if context.query_params:
                query_string = "&".join([f"{k}={v}" for k, v in context.query_params.items()])
                url += f"?{query_string}"
            
            async with self.client_session.request(
                method=context.method,
                url=url,
                headers=context.headers,
                data=context.body
            ) as response:
                response_body = await response.read()
                backend_time = time.time() - backend_start
                
                return ResponseContext(
                    status_code=response.status,
                    headers=dict(response.headers),
                    body=response_body,
                    processing_time=time.time() - context.start_time,
                    backend_response_time=backend_time,
                    cache_hit=False,
                    errors=[]
                )
        
        except Exception as e:
            logger.error(f"后端请求失败: {e}")
            return ResponseContext(
                status_code=502,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"error": "Backend error"}).encode(),
                processing_time=time.time() - context.start_time,
                backend_response_time=0.0,
                cache_hit=False,
                errors=[str(e)]
            )
    
    def _select_backend(self, backends: List[str]) -> Optional[str]:
        """选择后端服务器 (简单轮询)"""
        if not backends:
            return None
        
        # 简化实现 - 随机选择
        import random
        return random.choice(backends)
    
    def get_traffic_stats(self) -> Dict[str, Any]:
        """获取流量统计"""
        return {
            "total_routes": len(self.routes),
            "active_backends": sum(len(route["backends"]) for route in self.routes.values()),
            "circuit_breakers": len(self.circuit_breakers),
            "rate_limiters": len(self.rate_limiters)
        }


class DataPlane:
    """🚦 数据平面"""
    
    def __init__(self, ecosystem_config):
        self.config = ecosystem_config
        self.app = None
        self.runner = None
        self.site = None
        
        # 核心组件
        self.request_pipeline = RequestPipeline()
        self.response_pipeline = ResponsePipeline()
        self.traffic_manager = TrafficManager()
        
        # 统计数据
        self.stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_error": 0,
            "total_response_time": 0.0,
            "active_connections": 0
        }
        
        logger.info("DataPlane初始化完成")
    
    async def initialize(self):
        """初始化数据平面"""
        logger.info("🚦 初始化数据平面...")
        
        # 初始化HTTP应用
        self.app = web.Application()
        self._setup_routes()
        self._setup_middleware()
        
        # 初始化流量管理器
        await self.traffic_manager.initialize()
        
        # 注册默认路由
        self._register_default_routes()
        
        # 设置默认中间件
        self._setup_default_middleware()
        
        logger.info("✅ 数据平面初始化完成")
    
    def _setup_routes(self):
        """设置路由"""
        # 通用路由处理器 - 捕获所有请求
        self.app.router.add_route("*", "/{path:.*}", self.handle_request)
    
    def _setup_middleware(self):
        """设置中间件"""
        # 添加基础中间件
        self.app.middlewares.append(self._connection_tracking_middleware)
        self.app.middlewares.append(self._error_handling_middleware)
    
    def _register_default_routes(self):
        """注册默认路由"""
        # 健康检查路由
        self.traffic_manager.register_route(
            "/health", 
            ["http://localhost:8081"], 
            "GET"
        )
        
        # API路由示例
        self.traffic_manager.register_route(
            "/api/*", 
            ["http://localhost:8082", "http://localhost:8083"], 
            "GET"
        )
    
    def _setup_default_middleware(self):
        """设置默认中间件"""
        # 请求日志中间件
        self.request_pipeline.add_middleware(self._logging_middleware, priority=10)
        
        # 认证中间件
        self.request_pipeline.add_middleware(self._auth_middleware, priority=20)
        
        # 限流中间件
        self.request_pipeline.add_middleware(self._rate_limiting_middleware, priority=30)
    
    async def _logging_middleware(self, context: RequestContext) -> RequestContext:
        """日志中间件"""
        logger.info(f"请求: {context.method} {context.path} from {context.client_ip}")
        return context
    
    async def _auth_middleware(self, context: RequestContext) -> RequestContext:
        """认证中间件"""
        # 简化实现 - 跳过认证
        return context
    
    async def _rate_limiting_middleware(self, context: RequestContext) -> RequestContext:
        """限流中间件"""
        # 简化实现 - 不限流
        return context
    
    @web.middleware
    async def _connection_tracking_middleware(self, request, handler):
        """连接跟踪中间件"""
        self.stats["active_connections"] += 1
        try:
            response = await handler(request)
            return response
        finally:
            self.stats["active_connections"] -= 1
    
    @web.middleware
    async def _error_handling_middleware(self, request, handler):
        """错误处理中间件"""
        try:
            response = await handler(request)
            return response
        except Exception as e:
            logger.error(f"请求处理错误: {e}")
            self.stats["requests_error"] += 1
            
            return web.json_response({
                "error": "Internal Server Error",
                "message": str(e)
            }, status=500)
    
    async def handle_request(self, request):
        """处理HTTP请求"""
        start_time = time.time()
        self.stats["requests_total"] += 1
        
        try:
            # 创建请求上下文
            body = await request.read()
            context = RequestContext(
                request_id=f"req_{int(time.time() * 1000)}",
                method=request.method,
                path=request.path_qs.split("?")[0],
                headers=dict(request.headers),
                query_params=dict(request.query),
                body=body,
                start_time=start_time,
                client_ip=request.remote,
                user_agent=request.headers.get("User-Agent", ""),
                metadata={}
            )
            
            # 执行请求流水线
            context = await self.request_pipeline.process_request(context)
            
            # 转发请求
            response_context = await self.traffic_manager.forward_request(context)
            
            # 执行响应流水线
            response_context = await self.response_pipeline.process(response_context)
            
            # 更新统计
            processing_time = time.time() - start_time
            self.stats["total_response_time"] += processing_time
            
            if response_context.status_code < 400:
                self.stats["requests_success"] += 1
            else:
                self.stats["requests_error"] += 1
            
            # 返回响应
            return web.Response(
                body=response_context.body,
                status=response_context.status_code,
                headers=response_context.headers
            )
        
        except Exception as e:
            logger.error(f"请求处理失败: {e}")
            self.stats["requests_error"] += 1
            
            return web.json_response({
                "error": "Request processing failed",
                "message": str(e)
            }, status=500)
    
    async def start(self):
        """启动数据平面"""
        logger.info("🚀 启动数据平面...")
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(
            self.runner,
            self.config.host,
            self.config.port
        )
        
        await self.site.start()
        logger.info(f"数据平面启动完成: http://{self.config.host}:{self.config.port}")
    
    async def stop(self):
        """停止数据平面"""
        logger.info("🛑 停止数据平面...")
        
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        await self.traffic_manager.stop()
        
        logger.info("✅ 数据平面停止完成")
    
    async def is_healthy(self) -> bool:
        """检查数据平面健康状态"""
        # 简化实现 - 检查基本组件状态
        return (
            self.runner is not None and
            self.site is not None and
            self.traffic_manager.client_session is not None
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计数据"""
        stats = self.stats.copy()
        
        # 计算平均响应时间
        if stats["requests_total"] > 0:
            stats["average_response_time"] = stats["total_response_time"] / stats["requests_total"]
        else:
            stats["average_response_time"] = 0.0
        
        # 添加流量管理统计
        stats.update(self.traffic_manager.get_traffic_stats())
        
        return stats
    
    def register_route(self, path_pattern: str, backend_urls: List[str], method: str = "GET"):
        """注册新路由"""
        self.traffic_manager.register_route(path_pattern, backend_urls, method)
    
    def add_middleware(self, middleware: Callable, priority: int = 100):
        """添加请求中间件"""
        self.request_pipeline.add_middleware(middleware, priority)
    
    def add_response_filter(self, filter_func: Callable):
        """添加响应过滤器"""
        self.response_pipeline.add_filter(filter_func)