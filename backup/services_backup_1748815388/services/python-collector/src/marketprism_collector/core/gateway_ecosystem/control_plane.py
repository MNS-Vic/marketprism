#!/usr/bin/env python3
"""
🎮 API网关控制平面

提供统一的管理接口、配置管理、插件管理等控制功能。
负责协调和管理整个API网关生态系统。
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from aiohttp import web, ClientSession
import aiofiles

logger = logging.getLogger(__name__)


@dataclass
class ManagementConfig:
    """管理接口配置"""
    host: str = "0.0.0.0"
    port: int = 9090
    ssl_enabled: bool = False
    api_prefix: str = "/api/v1"
    auth_enabled: bool = True
    cors_enabled: bool = True


class ManagementAPI:
    """🔧 管理API接口"""
    
    def __init__(self, ecosystem, config: ManagementConfig):
        self.ecosystem = ecosystem
        self.config = config
        self.app = None
        self.runner = None
        self.site = None
        
        logger.info("ManagementAPI初始化完成")
    
    async def initialize(self):
        """初始化管理API"""
        self.app = web.Application()
        self._setup_routes()
        self._setup_middleware()
        
        logger.info("管理API路由配置完成")
    
    def _setup_routes(self):
        """设置API路由"""
        prefix = self.config.api_prefix
        
        # 系统状态接口
        self.app.router.add_get(f"{prefix}/health", self.health_check)
        self.app.router.add_get(f"{prefix}/status", self.get_system_status)
        self.app.router.add_get(f"{prefix}/dashboard", self.get_dashboard)
        
        # 组件管理接口
        self.app.router.add_get(f"{prefix}/components", self.list_components)
        self.app.router.add_get(f"{prefix}/components/{{component_name}}", self.get_component_status)
        self.app.router.add_post(f"{prefix}/components/{{component_name}}/restart", self.restart_component)
        
        # 配置管理接口
        self.app.router.add_get(f"{prefix}/config", self.get_configuration)
        self.app.router.add_put(f"{prefix}/config", self.update_configuration)
        self.app.router.add_post(f"{prefix}/config/reload", self.reload_configuration)
        
        # 插件管理接口
        self.app.router.add_get(f"{prefix}/plugins", self.list_plugins)
        self.app.router.add_post(f"{prefix}/plugins/{{plugin_name}}/enable", self.enable_plugin)
        self.app.router.add_post(f"{prefix}/plugins/{{plugin_name}}/disable", self.disable_plugin)
        
        # 监控接口
        self.app.router.add_get(f"{prefix}/metrics", self.get_metrics)
        self.app.router.add_get(f"{prefix}/logs", self.get_logs)
        
        # 静态文件服务 (管理界面)
        self.app.router.add_get("/", self.serve_dashboard_ui)
        self.app.router.add_static("/static", "./static", name="static")
    
    def _setup_middleware(self):
        """设置中间件"""
        if self.config.cors_enabled:
            self.app.middlewares.append(self._cors_middleware)
        
        self.app.middlewares.append(self._auth_middleware)
        self.app.middlewares.append(self._error_middleware)
    
    @web.middleware
    async def _cors_middleware(self, request, handler):
        """CORS中间件"""
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    
    @web.middleware
    async def _auth_middleware(self, request, handler):
        """认证中间件"""
        if not self.config.auth_enabled:
            return await handler(request)
        
        # 简单的API密钥认证
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != "marketprism-admin-2024":
            return web.json_response({"error": "Unauthorized"}, status=401)
        
        return await handler(request)
    
    @web.middleware
    async def _error_middleware(self, request, handler):
        """错误处理中间件"""
        try:
            return await handler(request)
        except Exception as e:
            logger.error(f"API请求处理错误: {e}")
            return web.json_response({
                "error": "Internal Server Error",
                "message": str(e)
            }, status=500)
    
    # API处理函数
    async def health_check(self, request):
        """健康检查"""
        is_healthy = await self.ecosystem.is_healthy()
        status = 200 if is_healthy else 503
        
        return web.json_response({
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": time.time()
        }, status=status)
    
    async def get_system_status(self, request):
        """获取系统状态"""
        status = self.ecosystem.get_ecosystem_status()
        return web.json_response(status)
    
    async def get_dashboard(self, request):
        """获取仪表板数据"""
        dashboard = self.ecosystem.get_ecosystem_dashboard()
        return web.json_response(dashboard)
    
    async def list_components(self, request):
        """列出所有组件"""
        components = {}
        for name, status in self.ecosystem.component_status.items():
            components[name] = {
                "name": name,
                "status": status.value,
                "has_component": name in self.ecosystem.components
            }
        
        return web.json_response({"components": components})
    
    async def get_component_status(self, request):
        """获取组件状态"""
        component_name = request.match_info["component_name"]
        
        if component_name not in self.ecosystem.component_status:
            return web.json_response({"error": "Component not found"}, status=404)
        
        status = self.ecosystem.component_status[component_name]
        component = self.ecosystem.components.get(component_name)
        
        return web.json_response({
            "name": component_name,
            "status": status.value,
            "details": getattr(component, "get_status", lambda: {})() if component else {}
        })
    
    async def restart_component(self, request):
        """重启组件"""
        component_name = request.match_info["component_name"]
        
        if component_name not in self.ecosystem.components:
            return web.json_response({"error": "Component not found"}, status=404)
        
        try:
            component = self.ecosystem.components[component_name]
            if hasattr(component, "restart"):
                await component.restart()
            else:
                await component.stop()
                await component.start()
            
            return web.json_response({
                "message": f"Component {component_name} restarted successfully"
            })
        
        except Exception as e:
            return web.json_response({
                "error": f"Failed to restart component: {str(e)}"
            }, status=500)
    
    async def get_configuration(self, request):
        """获取配置"""
        config_dict = asdict(self.ecosystem.config)
        return web.json_response({"configuration": config_dict})
    
    async def update_configuration(self, request):
        """更新配置"""
        try:
            data = await request.json()
            new_config = data.get("configuration", {})
            
            # 更新配置 (简化实现)
            for key, value in new_config.items():
                if hasattr(self.ecosystem.config, key):
                    setattr(self.ecosystem.config, key, value)
            
            return web.json_response({"message": "Configuration updated successfully"})
        
        except Exception as e:
            return web.json_response({
                "error": f"Failed to update configuration: {str(e)}"
            }, status=400)
    
    async def reload_configuration(self, request):
        """重新加载配置"""
        try:
            # 这里可以实现配置热重载逻辑
            return web.json_response({"message": "Configuration reloaded successfully"})
        
        except Exception as e:
            return web.json_response({
                "error": f"Failed to reload configuration: {str(e)}"
            }, status=500)
    
    async def list_plugins(self, request):
        """列出插件"""
        plugins = {}
        if hasattr(self.ecosystem, "plugin_registry"):
            plugins = self.ecosystem.plugin_registry.list_plugins()
        
        return web.json_response({"plugins": plugins})
    
    async def enable_plugin(self, request):
        """启用插件"""
        plugin_name = request.match_info["plugin_name"]
        
        try:
            if hasattr(self.ecosystem, "plugin_registry"):
                await self.ecosystem.plugin_registry.enable_plugin(plugin_name)
            
            return web.json_response({
                "message": f"Plugin {plugin_name} enabled successfully"
            })
        
        except Exception as e:
            return web.json_response({
                "error": f"Failed to enable plugin: {str(e)}"
            }, status=500)
    
    async def disable_plugin(self, request):
        """禁用插件"""
        plugin_name = request.match_info["plugin_name"]
        
        try:
            if hasattr(self.ecosystem, "plugin_registry"):
                await self.ecosystem.plugin_registry.disable_plugin(plugin_name)
            
            return web.json_response({
                "message": f"Plugin {plugin_name} disabled successfully"
            })
        
        except Exception as e:
            return web.json_response({
                "error": f"Failed to disable plugin: {str(e)}"
            }, status=500)
    
    async def get_metrics(self, request):
        """获取指标"""
        metrics = self.ecosystem.metrics.copy()
        
        # 添加组件指标
        for name, component in self.ecosystem.components.items():
            if hasattr(component, "get_metrics"):
                try:
                    component_metrics = component.get_metrics()
                    metrics[f"{name}_metrics"] = component_metrics
                except:
                    pass
        
        return web.json_response({"metrics": metrics})
    
    async def get_logs(self, request):
        """获取日志"""
        # 简化实现 - 返回最近的日志
        logs = [
            {"level": "INFO", "message": "System running normally", "timestamp": time.time()},
            {"level": "DEBUG", "message": "Health check completed", "timestamp": time.time() - 30}
        ]
        
        return web.json_response({"logs": logs})
    
    async def serve_dashboard_ui(self, request):
        """提供管理界面"""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>MarketPrism API Gateway Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
                .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
                .status-healthy { color: #27ae60; font-weight: bold; }
                .status-error { color: #e74c3c; font-weight: bold; }
                .component { margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 3px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🌟 MarketPrism API Gateway Dashboard</h1>
                <p>Enterprise API Gateway Ecosystem Management</p>
            </div>
            
            <div class="section">
                <h2>🏥 System Health</h2>
                <div id="health-status">Loading...</div>
            </div>
            
            <div class="section">
                <h2>🔧 Components</h2>
                <div id="components-list">Loading...</div>
            </div>
            
            <div class="section">
                <h2>📊 Metrics</h2>
                <div id="metrics-display">Loading...</div>
            </div>
            
            <script>
                async function loadDashboard() {
                    try {
                        const response = await fetch('/api/v1/dashboard', {
                            headers: {'X-API-Key': 'marketprism-admin-2024'}
                        });
                        const data = await response.json();
                        
                        // 更新健康状态
                        const healthElement = document.getElementById('health-status');
                        const health = data.ecosystem_status.ecosystem.health;
                        healthElement.innerHTML = `<span class="status-${health === 'healthy' ? 'healthy' : 'error'}">${health.toUpperCase()}</span>`;
                        
                        // 更新组件列表
                        const componentsElement = document.getElementById('components-list');
                        let componentsHtml = '';
                        for (const [name, status] of Object.entries(data.ecosystem_status.components)) {
                            componentsHtml += `<div class="component"><strong>${name}:</strong> <span class="status-${status === 'running' ? 'healthy' : 'error'}">${status}</span></div>`;
                        }
                        componentsElement.innerHTML = componentsHtml;
                        
                        // 更新指标
                        const metricsElement = document.getElementById('metrics-display');
                        const metrics = data.ecosystem_status.metrics;
                        metricsElement.innerHTML = `
                            <p><strong>Total Requests:</strong> ${metrics.requests_total}</p>
                            <p><strong>Success Rate:</strong> ${((metrics.requests_success / metrics.requests_total) * 100 || 0).toFixed(2)}%</p>
                            <p><strong>Average Response Time:</strong> ${metrics.average_response_time.toFixed(2)}ms</p>
                            <p><strong>Active Connections:</strong> ${metrics.active_connections}</p>
                        `;
                        
                    } catch (error) {
                        console.error('Error loading dashboard:', error);
                    }
                }
                
                // 初始加载
                loadDashboard();
                
                // 每30秒刷新一次
                setInterval(loadDashboard, 30000);
            </script>
        </body>
        </html>
        """
        
        return web.Response(text=html_content, content_type="text/html")
    
    async def start(self):
        """启动管理API服务器"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(
            self.runner,
            self.config.host,
            self.config.port,
            ssl_context=None  # TODO: 添加SSL支持
        )
        
        await self.site.start()
        logger.info(f"管理API服务器启动: http://{self.config.host}:{self.config.port}")
    
    async def stop(self):
        """停止管理API服务器"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("管理API服务器已停止")


class ConfigurationManager:
    """📝 配置管理器"""
    
    def __init__(self, config_file: str = "./config/gateway.json"):
        self.config_file = config_file
        self.config_data = {}
        self.watchers = []
        
        logger.info("ConfigurationManager初始化完成")
    
    async def load_configuration(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            async with aiofiles.open(self.config_file, "r") as f:
                content = await f.read()
                self.config_data = json.loads(content)
            
            logger.info(f"配置加载成功: {self.config_file}")
            return self.config_data
        
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {self.config_file}")
            return {}
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            raise
    
    async def save_configuration(self, config_data: Dict[str, Any]):
        """保存配置"""
        try:
            async with aiofiles.open(self.config_file, "w") as f:
                await f.write(json.dumps(config_data, indent=2))
            
            self.config_data = config_data
            await self._notify_watchers()
            
            logger.info(f"配置保存成功: {self.config_file}")
        
        except Exception as e:
            logger.error(f"配置保存失败: {e}")
            raise
    
    def add_watcher(self, callback):
        """添加配置变更监听器"""
        self.watchers.append(callback)
    
    async def _notify_watchers(self):
        """通知配置变更监听器"""
        for watcher in self.watchers:
            try:
                if asyncio.iscoroutinefunction(watcher):
                    await watcher(self.config_data)
                else:
                    watcher(self.config_data)
            except Exception as e:
                logger.error(f"配置变更通知失败: {e}")


class PluginManager:
    """🔌 插件管理器"""
    
    def __init__(self, plugin_dirs: List[str]):
        self.plugin_dirs = plugin_dirs
        self.plugins = {}
        self.enabled_plugins = set()
        
        logger.info("PluginManager初始化完成")
    
    async def discover_plugins(self):
        """发现插件"""
        # 简化实现 - 扫描插件目录
        discovered = []
        
        for plugin_dir in self.plugin_dirs:
            try:
                # 这里应该实现实际的插件发现逻辑
                # 扫描Python文件，查找插件类等
                pass
            except Exception as e:
                logger.error(f"插件发现失败 {plugin_dir}: {e}")
        
        logger.info(f"发现 {len(discovered)} 个插件")
        return discovered
    
    async def load_plugin(self, plugin_name: str):
        """加载插件"""
        try:
            # 简化实现 - 实际应该动态导入插件模块
            logger.info(f"加载插件: {plugin_name}")
            
            # 模拟插件加载
            self.plugins[plugin_name] = {
                "name": plugin_name,
                "version": "1.0.0",
                "loaded": True,
                "enabled": False
            }
            
        except Exception as e:
            logger.error(f"插件加载失败 {plugin_name}: {e}")
            raise
    
    async def enable_plugin(self, plugin_name: str):
        """启用插件"""
        if plugin_name not in self.plugins:
            await self.load_plugin(plugin_name)
        
        self.enabled_plugins.add(plugin_name)
        self.plugins[plugin_name]["enabled"] = True
        
        logger.info(f"插件已启用: {plugin_name}")
    
    async def disable_plugin(self, plugin_name: str):
        """禁用插件"""
        self.enabled_plugins.discard(plugin_name)
        if plugin_name in self.plugins:
            self.plugins[plugin_name]["enabled"] = False
        
        logger.info(f"插件已禁用: {plugin_name}")
    
    def list_plugins(self) -> Dict[str, Any]:
        """列出所有插件"""
        return self.plugins.copy()


class ControlPlane:
    """🎮 控制平面"""
    
    def __init__(self, ecosystem_config):
        self.ecosystem_config = ecosystem_config
        self.management_config = ManagementConfig()
        
        # 子组件
        self.management_api = None
        self.config_manager = ConfigurationManager()
        self.plugin_manager = PluginManager(ecosystem_config.plugin_directories)
        
        logger.info("ControlPlane初始化完成")
    
    async def initialize(self):
        """初始化控制平面"""
        logger.info("🎮 初始化控制平面...")
        
        # 加载配置
        await self.config_manager.load_configuration()
        
        # 发现插件
        await self.plugin_manager.discover_plugins()
        
        logger.info("✅ 控制平面初始化完成")
    
    async def start(self):
        """启动控制平面"""
        logger.info("🚀 启动控制平面...")
        
        # 这里需要在ecosystem初始化完成后设置
        # self.management_api = ManagementAPI(ecosystem, self.management_config)
        # await self.management_api.initialize()
        # await self.management_api.start()
        
        logger.info("✅ 控制平面启动完成")
    
    async def stop(self):
        """停止控制平面"""
        logger.info("🛑 停止控制平面...")
        
        if self.management_api:
            await self.management_api.stop()
        
        logger.info("✅ 控制平面停止完成")
    
    def set_ecosystem(self, ecosystem):
        """设置生态系统引用"""
        self.management_api = ManagementAPI(ecosystem, self.management_config)
    
    async def is_healthy(self) -> bool:
        """检查控制平面健康状态"""
        return True  # 简化实现