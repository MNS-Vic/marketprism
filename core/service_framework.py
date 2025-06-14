"""
MarketPrism 微服务基础框架
提供统一的服务基础设施：健康检查、配置管理、日志、监控等
"""

import asyncio
import logging
import signal
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import aiohttp
from aiohttp import web
import yaml
import json

from core.observability.metrics import get_global_manager as get_global_monitoring
from core.observability.logging.structured_logger import StructuredLogger
from core.config import get_global_config_manager


class HealthChecker:
    """服务健康检查器"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.start_time = datetime.now()
        self.health_checks = {}
        
    def add_check(self, name: str, check_func):
        """添加健康检查项"""
        self.health_checks[name] = check_func
        
    async def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        status = {
            "service": self.service_name,
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "checks": {}
        }
        
        for name, check_func in self.health_checks.items():
            try:
                result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                status["checks"][name] = {"status": "pass", "result": result}
            except Exception as e:
                status["checks"][name] = {"status": "fail", "error": str(e)}
                status["status"] = "unhealthy"
                
        return status


class BaseService(ABC):
    """微服务基础类"""
    
    def __init__(self, service_name: str, config: Dict[str, Any]):
        self.service_name = service_name
        self.config = config
        
        # 初始化组件
        self.health_checker = HealthChecker(service_name)
        self.metrics = get_global_monitoring()
        self.logger = StructuredLogger(service_name)
        
        # 服务状态
        self.is_running = False
        self.app = None
        self.runner = None
        self.site = None
        
        # 注册基础健康检查
        self.health_checker.add_check("service_status", self._check_service_status)
        
    async def _check_service_status(self) -> str:
        """检查服务状态"""
        return "running" if self.is_running else "stopped"
        
    async def run(self):
        """启动并运行服务，直到接收到停止信号。"""
        self.logger.info("Starting service", service=self.service_name)
        
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def signal_handler():
            self.logger.info("Stop signal received, shutting down.")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
            
        try:
            self.app = web.Application()
            # 设置基础路由
            self.app.router.add_get('/health', self._health_endpoint)
            self.app.router.add_get('/metrics', self._metrics_endpoint)

            # 设置服务特定路由
            self.setup_routes()

            # 启动服务逻辑
            await self.on_startup()

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            port = self.config.get('port', 8080)
            self.site = web.TCPSite(self.runner, '0.0.0.0', port)
            await self.site.start()
            
            self.is_running = True
            self.logger.info(f"Service '{self.service_name}' running on port {port}")
            
            # 等待停止信号
            await stop_event.wait()

        except Exception as e:
            self.logger.error("Service run failed", error=str(e), exc_info=True)
            # 重新抛出异常以便主程序能获取详细错误信息
            raise
        finally:
            self.logger.info("Service shutting down.")
            self.is_running = False
            # 关闭服务逻辑
            await self.on_shutdown()

            # 清理服务器
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            
            self.logger.info("Service shutdown complete.")

    async def _health_endpoint(self, request):
        """健康检查端点"""
        health_status = await self.health_checker.get_health_status()
        status_code = 200 if health_status["status"] == "healthy" else 503
        return web.json_response(health_status, status=status_code)
        
    async def _metrics_endpoint(self, request):
        """指标端点"""
        # This should be handled by the prometheus_exporter in the observability module
        # For now, we return a placeholder
        metrics_data = {
            "service": self.service_name,
            "timestamp": datetime.now().isoformat(),
            "metrics": self.metrics.export_to_text()
        }
        return web.Response(text=metrics_data["metrics"], content_type="text/plain")
        
    @abstractmethod
    def setup_routes(self):
        """设置服务特定的路由"""
        pass
        
    @abstractmethod
    async def on_startup(self):
        """服务启动时的回调"""
        pass
        
    @abstractmethod
    async def on_shutdown(self):
        """服务停止时的回调"""
        pass


class ServiceRegistry:
    """服务注册发现"""
    
    def __init__(self):
        self.services = {}
        
    async def register_service(self, service_name: str, host: str, port: int, metadata: Dict[str, Any] = None):
        """注册服务"""
        service_info = {
            "name": service_name,
            "host": host,
            "port": port,
            "metadata": metadata or {},
            "registered_at": datetime.now().isoformat(),
            "health_check_url": f"http://{host}:{port}/health"
        }
        self.services[service_name] = service_info
        print(f"Service registered: {service_name} at {host}:{port}")
        
    async def deregister_service(self, service_name: str):
        """注销服务"""
        if service_name in self.services:
            del self.services[service_name]
            print(f"Service deregistered: {service_name}")
            
    async def discover_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        """发现服务"""
        return self.services.get(service_name)
        
    async def list_services(self) -> Dict[str, Dict[str, Any]]:
        """列出所有服务"""
        return self.services.copy()


# 全局服务注册表
_service_registry = ServiceRegistry()


def get_service_registry() -> ServiceRegistry:
    """获取全局服务注册表"""
    return _service_registry