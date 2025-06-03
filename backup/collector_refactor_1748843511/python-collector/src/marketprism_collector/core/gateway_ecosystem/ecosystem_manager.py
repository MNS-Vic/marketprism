#!/usr/bin/env python3
"""
🌟 API网关生态系统管理器

负责管理和协调整个API网关生态系统的所有组件，
提供统一的管理接口和生命周期控制。
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ComponentStatus(Enum):
    """组件状态枚举"""
    UNKNOWN = "unknown"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class EcosystemHealth(Enum):
    """生态系统健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


@dataclass
class EcosystemConfig:
    """生态系统配置"""
    # 基础配置
    name: str = "MarketPrism API Gateway"
    version: str = "1.0.0"
    environment: str = "production"
    
    # 组件配置
    enable_gateway_core: bool = True
    enable_service_discovery: bool = True
    enable_middleware: bool = True
    enable_security: bool = True
    enable_monitoring: bool = True
    enable_performance: bool = True
    
    # 网络配置
    host: str = "0.0.0.0"
    port: int = 8080
    ssl_enabled: bool = False
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    
    # 性能配置
    worker_count: int = 4
    max_connections: int = 1000
    request_timeout: float = 30.0
    keepalive_timeout: float = 60.0
    
    # 健康检查配置
    health_check_interval: float = 30.0
    health_check_timeout: float = 5.0
    
    # 其他配置
    plugin_directories: List[str] = field(default_factory=lambda: ["./plugins"])
    config_reload_enabled: bool = True
    debug_mode: bool = False


class APIGatewayEcosystem:
    """🌟 API网关生态系统管理器"""
    
    def __init__(self, config: EcosystemConfig):
        self.config = config
        self.start_time = None
        self.components = {}
        self.component_status = {}
        self.health_status = EcosystemHealth.UNHEALTHY
        self.metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_error": 0,
            "average_response_time": 0.0,
            "active_connections": 0
        }
        
        # 核心组件
        self._control_plane = None
        self._data_plane = None
        self._gateway_core = None
        self._service_discovery = None
        self._middleware_system = None
        self._security_system = None
        self._monitoring_system = None
        self._performance_system = None
        
        # 事件循环和任务
        self._health_check_task = None
        self._running = False
        
        logger.info(f"APIGatewayEcosystem初始化: {config.name} v{config.version}")
    
    async def initialize(self):
        """初始化生态系统"""
        logger.info("🚀 初始化API网关生态系统...")
        
        try:
            # 初始化控制平面
            if self.config.enable_monitoring:
                await self._init_control_plane()
            
            # 初始化数据平面
            await self._init_data_plane()
            
            # 初始化核心组件
            await self._init_core_components()
            
            # 初始化插件系统
            await self._init_plugin_system()
            
            self.health_status = EcosystemHealth.HEALTHY
            logger.info("✅ API网关生态系统初始化完成")
            
        except Exception as e:
            self.health_status = EcosystemHealth.CRITICAL
            logger.error(f"❌ 生态系统初始化失败: {e}")
            raise
    
    async def _init_control_plane(self):
        """初始化控制平面"""
        logger.info("🎮 初始化控制平面...")
        
        try:
            from .control_plane import ControlPlane
            
            self._control_plane = ControlPlane(self.config)
            await self._control_plane.initialize()
            
            self.components["control_plane"] = self._control_plane
            self.component_status["control_plane"] = ComponentStatus.INITIALIZING
            
            logger.info("✅ 控制平面初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 控制平面初始化失败: {e}")
            self.component_status["control_plane"] = ComponentStatus.ERROR
            raise
    
    async def _init_data_plane(self):
        """初始化数据平面"""
        logger.info("🚦 初始化数据平面...")
        
        try:
            from .data_plane import DataPlane
            
            self._data_plane = DataPlane(self.config)
            await self._data_plane.initialize()
            
            self.components["data_plane"] = self._data_plane
            self.component_status["data_plane"] = ComponentStatus.INITIALIZING
            
            logger.info("✅ 数据平面初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 数据平面初始化失败: {e}")
            self.component_status["data_plane"] = ComponentStatus.ERROR
            raise
    
    async def _init_core_components(self):
        """初始化核心组件"""
        logger.info("🔧 初始化核心组件...")
        
        # 初始化网关核心
        if self.config.enable_gateway_core:
            await self._init_gateway_core()
        
        # 初始化服务发现
        if self.config.enable_service_discovery:
            await self._init_service_discovery()
        
        # 初始化中间件系统
        if self.config.enable_middleware:
            await self._init_middleware_system()
        
        # 初始化安全系统
        if self.config.enable_security:
            await self._init_security_system()
        
        # 初始化监控系统
        if self.config.enable_monitoring:
            await self._init_monitoring_system()
        
        # 初始化性能优化系统
        if self.config.enable_performance:
            await self._init_performance_system()
        
        logger.info("✅ 核心组件初始化完成")
    
    async def _init_gateway_core(self):
        """初始化网关核心"""
        try:
            from ..api_gateway import APIGatewayManager, GatewayConfig
            
            gateway_config = GatewayConfig(
                host=self.config.host,
                port=self.config.port,
                ssl_enabled=self.config.ssl_enabled
            )
            
            self._gateway_core = APIGatewayManager(gateway_config)
            await self._gateway_core.start()
            
            self.components["gateway_core"] = self._gateway_core
            self.component_status["gateway_core"] = ComponentStatus.RUNNING
            
            logger.info("✅ 网关核心初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 网关核心初始化失败: {e}")
            self.component_status["gateway_core"] = ComponentStatus.ERROR
    
    async def _init_service_discovery(self):
        """初始化服务发现"""
        try:
            from ..service_discovery import ServiceDiscoveryManager, ServiceDiscoveryConfig
            
            discovery_config = ServiceDiscoveryConfig(
                consul_host="localhost",
                consul_port=8500,
                health_check_enabled=True
            )
            
            self._service_discovery = ServiceDiscoveryManager(discovery_config)
            await self._service_discovery.start()
            
            self.components["service_discovery"] = self._service_discovery
            self.component_status["service_discovery"] = ComponentStatus.RUNNING
            
            logger.info("✅ 服务发现初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 服务发现初始化失败: {e}")
            self.component_status["service_discovery"] = ComponentStatus.ERROR
    
    async def _init_middleware_system(self):
        """初始化中间件系统"""
        try:
            from ..middleware import MiddlewareManager, MiddlewareConfig
            
            middleware_config = MiddlewareConfig(
                enable_logging=True,
                enable_metrics=True,
                enable_cors=True
            )
            
            self._middleware_system = MiddlewareManager(middleware_config)
            await self._middleware_system.start()
            
            self.components["middleware_system"] = self._middleware_system
            self.component_status["middleware_system"] = ComponentStatus.RUNNING
            
            logger.info("✅ 中间件系统初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 中间件系统初始化失败: {e}")
            self.component_status["middleware_system"] = ComponentStatus.ERROR
    
    async def _init_security_system(self):
        """初始化安全系统"""
        try:
            from ..security import SecurityManager, SecurityConfig
            
            security_config = SecurityConfig(
                enable_authentication=True,
                enable_authorization=True,
                enable_rate_limiting=True
            )
            
            self._security_system = SecurityManager(security_config)
            await self._security_system.start()
            
            self.components["security_system"] = self._security_system
            self.component_status["security_system"] = ComponentStatus.RUNNING
            
            logger.info("✅ 安全系统初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 安全系统初始化失败: {e}")
            self.component_status["security_system"] = ComponentStatus.ERROR
    
    async def _init_monitoring_system(self):
        """初始化监控系统"""
        try:
            from ..monitoring import MonitoringManager, MonitoringConfig
            
            monitoring_config = MonitoringConfig(
                enable_metrics=True,
                enable_alerts=True,
                enable_dashboard=True
            )
            
            self._monitoring_system = MonitoringManager(monitoring_config)
            await self._monitoring_system.start()
            
            self.components["monitoring_system"] = self._monitoring_system
            self.component_status["monitoring_system"] = ComponentStatus.RUNNING
            
            logger.info("✅ 监控系统初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 监控系统初始化失败: {e}")
            self.component_status["monitoring_system"] = ComponentStatus.ERROR
    
    async def _init_performance_system(self):
        """初始化性能优化系统"""
        try:
            from ..performance import PerformanceOptimizationManager, PerformanceConfig, OptimizationLevel
            
            performance_config = PerformanceConfig(
                optimization_level=OptimizationLevel.STANDARD,
                enable_auto_optimization=True
            )
            
            self._performance_system = PerformanceOptimizationManager(performance_config)
            await self._performance_system.start()
            
            self.components["performance_system"] = self._performance_system
            self.component_status["performance_system"] = ComponentStatus.RUNNING
            
            logger.info("✅ 性能优化系统初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 性能优化系统初始化失败: {e}")
            self.component_status["performance_system"] = ComponentStatus.ERROR
    
    async def _init_plugin_system(self):
        """初始化插件系统"""
        logger.info("🔌 初始化插件系统...")
        
        try:
            from .plugin_system import PluginRegistry
            
            self.plugin_registry = PluginRegistry(self.config.plugin_directories)
            await self.plugin_registry.initialize()
            
            self.components["plugin_system"] = self.plugin_registry
            self.component_status["plugin_system"] = ComponentStatus.RUNNING
            
            logger.info("✅ 插件系统初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 插件系统初始化失败: {e}")
            self.component_status["plugin_system"] = ComponentStatus.ERROR
    
    async def start(self):
        """启动生态系统"""
        logger.info("🚀 启动API网关生态系统...")
        
        try:
            self.start_time = time.time()
            self._running = True
            
            # 启动控制平面
            if self._control_plane:
                await self._control_plane.start()
                self.component_status["control_plane"] = ComponentStatus.RUNNING
            
            # 启动数据平面
            if self._data_plane:
                await self._data_plane.start()
                self.component_status["data_plane"] = ComponentStatus.RUNNING
            
            # 启动健康检查
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            self.health_status = EcosystemHealth.HEALTHY
            logger.info("✅ API网关生态系统启动完成")
            
        except Exception as e:
            self.health_status = EcosystemHealth.CRITICAL
            logger.error(f"❌ 生态系统启动失败: {e}")
            raise
    
    async def stop(self):
        """停止生态系统"""
        logger.info("🛑 停止API网关生态系统...")
        
        try:
            self._running = False
            
            # 停止健康检查
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # 停止所有组件
            for name, component in self.components.items():
                try:
                    if hasattr(component, 'stop'):
                        await component.stop()
                    self.component_status[name] = ComponentStatus.STOPPED
                except Exception as e:
                    logger.error(f"❌ 停止组件 {name} 失败: {e}")
                    self.component_status[name] = ComponentStatus.ERROR
            
            self.health_status = EcosystemHealth.UNHEALTHY
            logger.info("✅ API网关生态系统停止完成")
            
        except Exception as e:
            logger.error(f"❌ 生态系统停止失败: {e}")
            raise
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self._running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 健康检查失败: {e}")
                await asyncio.sleep(5.0)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        healthy_components = 0
        total_components = len(self.components)
        
        if total_components == 0:
            self.health_status = EcosystemHealth.UNHEALTHY
            return
        
        for name, component in self.components.items():
            try:
                if hasattr(component, 'is_healthy') and await component.is_healthy():
                    self.component_status[name] = ComponentStatus.RUNNING
                    healthy_components += 1
                else:
                    self.component_status[name] = ComponentStatus.ERROR
            except Exception as e:
                logger.warning(f"⚠️ 组件 {name} 健康检查失败: {e}")
                self.component_status[name] = ComponentStatus.ERROR
        
        # 计算健康状态
        health_ratio = healthy_components / total_components
        if health_ratio == 1.0:
            self.health_status = EcosystemHealth.HEALTHY
        elif health_ratio >= 0.8:
            self.health_status = EcosystemHealth.DEGRADED
        elif health_ratio >= 0.5:
            self.health_status = EcosystemHealth.UNHEALTHY
        else:
            self.health_status = EcosystemHealth.CRITICAL
    
    def get_ecosystem_status(self) -> Dict[str, Any]:
        """获取生态系统状态"""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            "ecosystem": {
                "name": self.config.name,
                "version": self.config.version,
                "environment": self.config.environment,
                "health": self.health_status.value,
                "running": self._running,
                "uptime": uptime
            },
            "components": {
                name: status.value for name, status in self.component_status.items()
            },
            "metrics": self.metrics.copy(),
            "timestamp": time.time()
        }
    
    def get_ecosystem_dashboard(self) -> Dict[str, Any]:
        """获取生态系统仪表板"""
        status = self.get_ecosystem_status()
        
        # 组件统计
        component_stats = {}
        for status_value in ComponentStatus:
            component_stats[status_value.value] = sum(
                1 for s in self.component_status.values() if s == status_value
            )
        
        # 性能指标
        performance_metrics = {}
        if self._performance_system:
            try:
                performance_metrics = self._performance_system.get_performance_dashboard()
            except:
                pass
        
        # 监控指标
        monitoring_metrics = {}
        if self._monitoring_system:
            try:
                monitoring_metrics = self._monitoring_system.get_monitoring_dashboard()
            except:
                pass
        
        return {
            "ecosystem_status": status,
            "component_statistics": component_stats,
            "performance_metrics": performance_metrics,
            "monitoring_metrics": monitoring_metrics,
            "health_summary": {
                "overall_health": self.health_status.value,
                "total_components": len(self.components),
                "healthy_components": sum(
                    1 for s in self.component_status.values() 
                    if s == ComponentStatus.RUNNING
                ),
                "error_components": sum(
                    1 for s in self.component_status.values() 
                    if s == ComponentStatus.ERROR
                )
            }
        }
    
    @asynccontextmanager
    async def lifecycle(self):
        """生态系统生命周期上下文管理器"""
        try:
            await self.initialize()
            await self.start()
            yield self
        finally:
            await self.stop()
    
    async def is_healthy(self) -> bool:
        """检查生态系统是否健康"""
        return self.health_status in [EcosystemHealth.HEALTHY, EcosystemHealth.DEGRADED]
    
    def get_component(self, name: str):
        """获取指定组件"""
        return self.components.get(name)
    
    def get_all_components(self) -> Dict[str, Any]:
        """获取所有组件"""
        return self.components.copy()


# 工厂函数
def create_ecosystem(config: Optional[EcosystemConfig] = None) -> APIGatewayEcosystem:
    """创建API网关生态系统实例"""
    if config is None:
        config = EcosystemConfig()
    
    return APIGatewayEcosystem(config)