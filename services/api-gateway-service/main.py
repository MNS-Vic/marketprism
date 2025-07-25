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
from datetime import datetime, timedelta, timezone
import aiohttp
from aiohttp import web, ClientTimeout
import json
import jwt
from collections import defaultdict, deque
import yaml
import traceback
import logging
import signal

# 确保能正确找到项目根目录并添加到sys.path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入微服务框架
from core.service_framework import BaseService
# 导入统一的ServiceRegistry
from services.service_registry import ServiceRegistry


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


class ApiGatewayService(BaseService):
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
        super().__init__("api-gateway-service", config)
        
        self.service_registry = ServiceRegistry()
        self.rate_limiter = RateLimiter(
            max_requests=config.get('rate_limit_requests', 100),
            time_window=config.get('rate_limit_window', 60)
        )
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        self.jwt_secret = config.get('jwt_secret', 'your-secret-key')
        self.jwt_algorithm = config.get('jwt_algorithm', 'HS256')
        self.enable_auth = config.get('enable_auth', False)
        
        self.routes_config = config.get('routes', [])
        self.response_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = config.get('cache_ttl', 300)
        self.client_session: Optional[aiohttp.ClientSession] = None
        self.logger.info("API Gateway Service 初始化完成")

    async def on_startup(self):
        """服务启动时的钩子"""
        await self.initialize_service()
        await self.start_service()

    async def on_shutdown(self):
        """服务关闭时的钩子"""
        await self.stop_service()

    def setup_routes(self):
        """设置API路由"""
        self._setup_internal_routes()
        self._setup_proxy_routes()

    async def initialize_service(self) -> bool:
        """初始化网关服务"""
        try:
            self._register_default_services()
            asyncio.create_task(self._health_check_loop())
            self.client_session = aiohttp.ClientSession()
            self.logger.info("API Gateway Service 初始化成功")
            return True
        except Exception as e:
            self.logger.error(f"API Gateway Service 初始化失败: {e}", exc_info=True)
            return False
    
    async def start_service(self) -> bool:
        """启动网关服务"""
        self.logger.info("API Gateway Service 启动成功")
        return True
            
    async def stop_service(self) -> bool:
        """停止网关服务"""
        self.logger.info("API Gateway Service 已停止")
        if self.client_session:
            await self.client_session.close()
        return True
    
    def _register_default_services(self):
        """注册配置文件中定义的服务"""
        default_services = self.config.get('services', {})
        for name, info in default_services.items():
            service_info = {
                'name': name,
                'host': info['host'],
                'port': info['port'],
                'health_endpoint': info.get('health_endpoint', '/health')
            }
            self.service_registry.register_service(name, service_info)

    def _setup_internal_routes(self):
        """设置网关自身的管理路由"""
        self.app.router.add_get("/_gateway/status", self._gateway_status)
        self.app.router.add_get("/api/v1/gateway/status", self._gateway_status)  # 添加标准API路由
        self.app.router.add_get("/_gateway/services", self._list_services)
        self.app.router.add_post("/_gateway/register", self._register_service)
        self.app.router.add_get("/_gateway/stats", self._get_stats)
        self.app.router.add_post("/auth/login", self._login)
        self.app.router.add_post("/auth/refresh", self._refresh_token)

    def _setup_proxy_routes(self):
        """根据配置设置所有代理路由"""
        if not self.routes_config:
            self.logger.info("未配置代理路由，跳过路由设置")
            return
            
        for route_config in self.routes_config:
            try:
                prefix = route_config.get('prefix')
                target_service = route_config.get('target')
                
                if not prefix or not target_service:
                    self.logger.warning(f"路由配置不完整，跳过: {route_config}")
                    continue
                    
                # 使用 aiohttp 的 aiohttp.web.Any() 来匹配所有HTTP方法
                self.app.router.add_route("*", f"{prefix}/{{tail:.*}}", self.create_proxy_handler(target_service))
                self.logger.info(f"Setup proxy for {prefix} -> {target_service}")
            except Exception as e:
                self.logger.error(f"设置代理路由失败: {route_config}, 错误: {e}")

    def create_proxy_handler(self, target_service_url: str):
        """创建一个处理代理请求的闭包"""
        async def handler(request: web.Request) -> web.Response:
            target_url = f"{target_service_url}{request.path_qs}"
            try:
                async with self.client_session.request(
                    request.method,
                    target_url,
                    headers=request.headers,
                    data=await request.read()
                ) as resp:
                    return web.Response(
                        status=resp.status,
                        body=await resp.read(),
                        headers=resp.headers
                    )
            except aiohttp.ClientError as e:
                self.logger.error(f"Proxy error targeting {target_url}: {e}")
                return web.Response(status=502, text=f"Bad Gateway: {e}")
        return handler

    async def _gateway_status(self, request):
        return web.json_response({"status": "running"})
    async def _list_services(self, request):
        return web.json_response(self.service_registry.list_services())
    async def _register_service(self, request):
        return web.json_response({"status": "not_implemented"})
    async def _get_stats(self, request):
        return web.json_response({"stats": "not_implemented"})
    async def _login(self, request):
        return web.json_response({"token": "not_implemented"})
    async def _refresh_token(self, request):
        return web.json_response({"token": "not_implemented"})
    async def _health_check_loop(self):
        while True:
            await self.service_registry.health_check_all_services()
            await asyncio.sleep(30)


async def main():
    """服务主入口点"""
    try:
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / 'config' / 'services.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f) or {}
        
        service_config = full_config.get('services', {}).get('api-gateway-service', {})
        
        service = ApiGatewayService(config=service_config)
        await service.run()

    except Exception as e:
        logging.basicConfig()
        logging.critical(f"API Gateway Service failed to start: {e}", exc_info=True)
        traceback.print_exc(file=sys.stderr)
        print(f"详细错误信息: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # 配置日志记录
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    
    asyncio.run(main())