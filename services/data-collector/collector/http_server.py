"""
MarketPrism订单簿管理系统HTTP服务器

提供健康检查、监控指标和API端点。
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from aiohttp import web, web_request
import structlog
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .health_check import HealthChecker
from .metrics import MetricsCollector

logger = structlog.get_logger(__name__)


class HTTPServer:
    """HTTP服务器类"""
    
    def __init__(self, 
                 health_check_port: int = 8080,
                 metrics_port: int = 8081,
                 health_checker: Optional[HealthChecker] = None,
                 metrics_collector: Optional[MetricsCollector] = None):
        self.health_check_port = health_check_port
        self.metrics_port = metrics_port
        self.health_checker = health_checker or HealthChecker()
        self.metrics_collector = metrics_collector
        self.logger = structlog.get_logger(__name__)
        
        # 服务器实例
        self.health_app = None
        self.metrics_app = None
        self.health_runner = None
        self.metrics_runner = None
        
        # 外部依赖引用
        self.nats_client = None
        self.websocket_connections = None
        self.orderbook_manager = None
        
        # 启动时间
        self.start_time = time.time()
    
    def set_dependencies(self, 
                        nats_client=None, 
                        websocket_connections=None,
                        orderbook_manager=None):
        """设置外部依赖"""
        self.nats_client = nats_client
        self.websocket_connections = websocket_connections
        self.orderbook_manager = orderbook_manager
    
    async def health_handler(self, request: web_request.Request) -> web.Response:
        """健康检查处理器"""
        try:
            # 执行健康检查
            health_report = await self.health_checker.perform_comprehensive_health_check(
                nats_client=self.nats_client,
                websocket_connections=self.websocket_connections,
                orderbook_manager=self.orderbook_manager
            )
            
            # 确定HTTP状态码
            status_code = 200 if health_report.get("status") == "healthy" else 503
            
            return web.json_response(
                health_report,
                status=status_code
            )
            
        except Exception as e:
            self.logger.error("健康检查处理失败", error=str(e), exc_info=True)
            
            error_response = {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": f"Health check handler failed: {str(e)}"
            }
            
            return web.json_response(error_response, status=503)
    
    async def metrics_handler(self, request: web_request.Request) -> web.Response:
        """Prometheus指标处理器"""
        try:
            # 更新指标
            if self.metrics_collector:
                await self.metrics_collector.update_metrics(
                    nats_client=self.nats_client,
                    websocket_connections=self.websocket_connections,
                    orderbook_manager=self.orderbook_manager
                )
            
            # 生成Prometheus格式的指标
            metrics_data = generate_latest()
            
            return web.Response(
                body=metrics_data,
                content_type=CONTENT_TYPE_LATEST
            )
            
        except Exception as e:
            self.logger.error("指标处理失败", error=str(e), exc_info=True)
            
            # 返回基本的错误指标
            error_metrics = f"""# HELP marketprism_metrics_error Metrics collection error
# TYPE marketprism_metrics_error gauge
marketprism_metrics_error 1
# HELP marketprism_uptime_seconds System uptime in seconds
# TYPE marketprism_uptime_seconds gauge
marketprism_uptime_seconds {time.time() - self.start_time}
"""
            
            return web.Response(
                body=error_metrics,
                content_type=CONTENT_TYPE_LATEST
            )
    
    async def status_handler(self, request: web_request.Request) -> web.Response:
        """系统状态处理器"""
        try:
            # 获取查询参数
            detailed = request.query.get('detailed', 'false').lower() == 'true'
            
            # 基础状态信息
            status_info = {
                "service": "MarketPrism OrderBook Manager",
                "version": "1.0.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "uptime": time.time() - self.start_time,
                "status": "running"
            }
            
            if detailed:
                # 详细状态信息
                health_report = await self.health_checker.perform_comprehensive_health_check(
                    nats_client=self.nats_client,
                    websocket_connections=self.websocket_connections,
                    orderbook_manager=self.orderbook_manager
                )
                
                status_info.update({
                    "detailed_health": health_report,
                    "active_symbols": len(getattr(self.orderbook_manager, 'orderbook_states', {})) if self.orderbook_manager else 0,
                    "nats_connected": (self.nats_client.is_connected if self.nats_client else False),
                    "websocket_connections": len(self.websocket_connections) if self.websocket_connections else 0
                })
            
            return web.json_response(status_info)
            
        except Exception as e:
            self.logger.error("状态处理失败", error=str(e), exc_info=True)
            
            error_response = {
                "service": "MarketPrism OrderBook Manager",
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
            
            return web.json_response(error_response, status=500)
    
    async def ping_handler(self, request: web_request.Request) -> web.Response:
        """简单ping处理器"""
        return web.json_response({
            "pong": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def version_handler(self, request: web_request.Request) -> web.Response:
        """版本信息处理器"""
        version_info = {
            "service": "MarketPrism OrderBook Manager",
            "version": "1.0.0",
            "build_time": "2025-07-03T12:00:00Z",
            "git_commit": "latest",
            "python_version": "3.11+",
            "features": [
                "Real-time OrderBook Management",
                "Multi-Exchange Support",
                "NATS Message Publishing",
                "Prometheus Metrics",
                "Health Monitoring"
            ]
        }
        
        return web.json_response(version_info)
    
    def create_health_app(self) -> web.Application:
        """创建健康检查应用"""
        app = web.Application()
        
        # 添加路由
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/status', self.status_handler)
        app.router.add_get('/ping', self.ping_handler)
        app.router.add_get('/version', self.version_handler)
        app.router.add_get('/', self.ping_handler)  # 根路径也返回ping
        
        return app
    
    def create_metrics_app(self) -> web.Application:
        """创建指标应用"""
        app = web.Application()
        
        # 添加路由
        app.router.add_get('/metrics', self.metrics_handler)
        app.router.add_get('/', self.metrics_handler)  # 根路径也返回指标
        
        return app
    
    async def start(self):
        """启动HTTP服务器"""
        try:
            # 创建应用
            self.health_app = self.create_health_app()
            self.metrics_app = self.create_metrics_app()
            
            # 创建运行器
            self.health_runner = web.AppRunner(self.health_app)
            self.metrics_runner = web.AppRunner(self.metrics_app)
            
            # 设置运行器
            await self.health_runner.setup()
            await self.metrics_runner.setup()
            
            # 创建站点
            health_site = web.TCPSite(
                self.health_runner, 
                '0.0.0.0', 
                self.health_check_port
            )
            
            metrics_site = web.TCPSite(
                self.metrics_runner, 
                '0.0.0.0', 
                self.metrics_port
            )
            
            # 启动站点
            await health_site.start()
            await metrics_site.start()
            
            self.logger.info(
                "HTTP服务器启动成功",
                health_port=self.health_check_port,
                metrics_port=self.metrics_port
            )
            
        except Exception as e:
            self.logger.error("HTTP服务器启动失败", error=str(e), exc_info=True)
            raise
    
    async def stop(self):
        """停止HTTP服务器"""
        try:
            if self.health_runner:
                await self.health_runner.cleanup()
                self.health_runner = None
            
            if self.metrics_runner:
                await self.metrics_runner.cleanup()
                self.metrics_runner = None
            
            self.logger.info("HTTP服务器已停止")
            
        except Exception as e:
            self.logger.error("HTTP服务器停止失败", error=str(e), exc_info=True)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()
