"""
MarketPrism 微服务基础框架
提供统一的服务基础设施：健康检查、配置管理、日志、监控等
"""

import asyncio
import logging
import signal
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp
from aiohttp import web
import yaml
import json

from core.monitoring import get_global_monitoring
from core.config import get_global_config


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


class PrometheusMetrics:
    """Prometheus指标收集器"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.monitoring = get_global_monitoring()
        
    def counter(self, name: str, value: float = 1, labels: Optional[Dict[str, str]] = None):
        """计数器指标"""
        metric_name = f"{self.service_name}_{name}"
        self.monitoring.record_metric(metric_name, value, labels or {})
        
    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """仪表盘指标"""
        metric_name = f"{self.service_name}_{name}"
        self.monitoring.record_metric(metric_name, value, labels or {})
        
    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """直方图指标"""
        metric_name = f"{self.service_name}_{name}"
        self.monitoring.record_metric(metric_name, value, labels or {})


class StructuredLogger:
    """结构化日志记录器"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        
        # 配置日志格式
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        
    def info(self, message: str, **kwargs):
        """信息日志"""
        extra_data = {"service": self.service_name, **kwargs}
        self.logger.info(f"{message} | {json.dumps(extra_data)}")
        
    def error(self, message: str, **kwargs):
        """错误日志"""
        extra_data = {"service": self.service_name, **kwargs}
        self.logger.error(f"{message} | {json.dumps(extra_data)}")
        
    def warning(self, message: str, **kwargs):
        """警告日志"""
        extra_data = {"service": self.service_name, **kwargs}
        self.logger.warning(f"{message} | {json.dumps(extra_data)}")


class BaseService(ABC):
    """微服务基础类"""
    
    def __init__(self, service_name: str, config_path: Optional[str] = None):
        self.service_name = service_name
        self.config_path = config_path or f"config/{service_name}.yaml"
        
        # 初始化组件
        self.config = self._load_config()
        self.health_checker = HealthChecker(service_name)
        self.metrics = PrometheusMetrics(service_name)
        self.logger = StructuredLogger(service_name)
        
        # 服务状态
        self.is_running = False
        self.app = None
        self.runner = None
        self.site = None
        
        # 注册基础健康检查
        self.health_checker.add_check("service_status", self._check_service_status)
        
    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            # 优先使用全局配置
            global_config = get_global_config()
            service_config = global_config.get(self.service_name, {})
            
            # 如果有专门的配置文件，则合并
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
                    service_config.update(file_config)
            except FileNotFoundError:
                pass
                
            return service_config
        except Exception as e:
            print(f"Failed to load config: {e}")
            return {}
            
    async def _check_service_status(self) -> str:
        """检查服务状态"""
        return "running" if self.is_running else "stopped"
        
    async def _setup_http_server(self):
        """设置HTTP服务器"""
        self.app = web.Application()
        
        # 健康检查端点
        self.app.router.add_get('/health', self._health_endpoint)
        self.app.router.add_get('/metrics', self._metrics_endpoint)
        
        # 添加服务特定路由
        await self.setup_routes()
        
        # 启动HTTP服务器
        port = self.config.get('port', 8080)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', port)
        await self.site.start()
        
        self.logger.info(f"HTTP server started on port {port}")
        
    async def _health_endpoint(self, request):
        """健康检查端点"""
        health_status = await self.health_checker.get_health_status()
        status_code = 200 if health_status["status"] == "healthy" else 503
        return web.json_response(health_status, status=status_code)
        
    async def _metrics_endpoint(self, request):
        """指标端点"""
        # 这里可以返回Prometheus格式的指标
        metrics_data = {
            "service": self.service_name,
            "timestamp": datetime.now().isoformat(),
            "metrics": "# Prometheus metrics would go here"
        }
        return web.json_response(metrics_data)
        
    async def start(self):
        """启动服务"""
        try:
            self.logger.info("Starting service", service=self.service_name)
            
            # 设置信号处理
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            # 启动HTTP服务器
            await self._setup_http_server()
            
            # 执行服务特定的启动逻辑
            await self.on_startup()
            
            self.is_running = True
            self.metrics.gauge("service_status", 1)
            self.logger.info("Service started successfully")
            
            # 保持服务运行
            await self._keep_running()
            
        except Exception as e:
            self.logger.error(f"Failed to start service: {e}")
            await self.stop()
            
    async def stop(self):
        """停止服务"""
        try:
            self.logger.info("Stopping service")
            self.is_running = False
            
            # 执行服务特定的停止逻辑
            await self.on_shutdown()
            
            # 停止HTTP服务器
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
                
            self.metrics.gauge("service_status", 0)
            self.logger.info("Service stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error during service shutdown: {e}")
            
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(self.stop())
        
    async def _keep_running(self):
        """保持服务运行"""
        while self.is_running:
            await asyncio.sleep(1)
            
    @abstractmethod
    async def setup_routes(self):
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