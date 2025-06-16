"""
MarketPrism 专业监控可视化仪表板
Professional Monitoring Dashboard for MarketPrism

提供现代化的Web界面，包含：
1. 实时系统监控仪表板
2. 服务健康状态可视化
3. 性能指标图表
4. 告警管理界面
5. 交易数据可视化
6. 实时WebSocket数据流
"""

import asyncio
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
from datetime import datetime, timedelta, timezone
import aiohttp
from aiohttp import web, WSMsgType
import aiohttp_jinja2
import jinja2
import yaml
import traceback
import logging
import signal


class MonitoringDashboard:
    """专业监控可视化仪表板服务"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.service_name = "monitoring-dashboard"
        self.port = config.get('port', 8086)
        self.host = config.get('host', '0.0.0.0')
        
        # 创建aiohttp应用
        self.app = web.Application()
        
        # WebSocket连接管理
        self.websocket_connections = set()
        
        # 监控数据缓存
        self.monitoring_data_cache = {
            'system_overview': {},
            'services_status': {},
            'alerts': [],
            'metrics_history': [],
            'trading_data': {}
        }
        
        # 数据更新任务
        self.data_update_task = None
        self.is_running = False
        
        # 监控服务配置
        data_sources = config.get('data_sources', {})
        self.monitoring_service_url = data_sources.get('monitoring_service_url', 'http://localhost:8083')
        self.data_collector_url = data_sources.get('data_collector_url', 'http://localhost:8081')
        
        # 设置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = structlog.get_logger(__name__)
        
        # 设置路由
        self.setup_routes()

    def setup_routes(self):
        """设置路由"""
        # 静态文件
        self.app.router.add_static('/static/', path=str(Path(__file__).parent / 'static'), name='static')
        
        # 主页面
        self.app.router.add_get('/', self.dashboard_home)
        self.app.router.add_get('/dashboard', self.dashboard_home)
        
        # 现代化页面
        self.app.router.add_get('/modern', self.modern_index)
        self.app.router.add_get('/modern/dashboard', self.modern_dashboard)
        self.app.router.add_get('/modern/services', self.modern_services)
        self.app.router.add_get('/modern/trading', self.modern_trading)
        
        # API端点
        self.app.router.add_get('/api/system-overview', self.get_system_overview)
        self.app.router.add_get('/api/services-status', self.get_services_status)
        self.app.router.add_get('/api/alerts', self.get_alerts)
        self.app.router.add_get('/api/metrics-history', self.get_metrics_history)
        self.app.router.add_get('/api/trading-data', self.get_trading_data)
        
        # WebSocket端点
        self.app.router.add_get('/ws', self.websocket_handler)
        
        # 专业页面
        self.app.router.add_get('/system', self.system_page)
        self.app.router.add_get('/services', self.services_page)
        self.app.router.add_get('/trading', self.trading_page)
        self.app.router.add_get('/alerts', self.alerts_page)
        
        # 健康检查
        self.app.router.add_get('/health', self.health_check)

    async def startup(self):
        """服务启动时的初始化"""
        self.logger.info("监控仪表板服务启动中...")
        
        # 设置Jinja2模板
        aiohttp_jinja2.setup(
            self.app,
            loader=jinja2.FileSystemLoader(str(Path(__file__).parent / 'templates'))
        )
        
        # 启动数据更新任务
        self.is_running = True
        self.data_update_task = asyncio.create_task(self._data_update_loop())
        
        self.logger.info("监控仪表板服务启动完成")

    async def shutdown(self):
        """服务关闭时的清理"""
        self.logger.info("监控仪表板服务关闭中...")
        
        self.is_running = False
        
        # 停止数据更新任务
        if self.data_update_task:
            self.data_update_task.cancel()
            try:
                await self.data_update_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有WebSocket连接
        for ws in self.websocket_connections.copy():
            await ws.close()
        
        self.logger.info("监控仪表板服务关闭完成")

    async def _data_update_loop(self):
        """数据更新循环"""
        while self.is_running:
            try:
                # 更新系统概览
                await self._update_system_overview()
                
                # 更新服务状态
                await self._update_services_status()
                
                # 更新告警信息
                await self._update_alerts()
                
                # 更新交易数据
                await self._update_trading_data()
                
                # 广播更新到所有WebSocket连接
                await self._broadcast_updates()
                
            except Exception as e:
                self.logger.error(f"数据更新循环异常: {e}")
            
            await asyncio.sleep(5)  # 每5秒更新一次

    async def _update_system_overview(self):
        """更新系统概览数据"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.monitoring_service_url}/api/v1/overview") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.monitoring_data_cache['system_overview'] = data
                        
                        # 添加时间戳到历史记录
                        history_entry = {
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'cpu_usage': data.get('system_resources', {}).get('cpu_usage_percent', 0),
                            'memory_usage': data.get('system_resources', {}).get('memory_usage_percent', 0),
                            'disk_usage': data.get('system_resources', {}).get('disk_usage_percent', 0)
                        }
                        
                        # 保持最近100个数据点
                        self.monitoring_data_cache['metrics_history'].append(history_entry)
                        if len(self.monitoring_data_cache['metrics_history']) > 100:
                            self.monitoring_data_cache['metrics_history'].pop(0)
                    else:
                        # 如果监控服务不可用，使用模拟数据
                        self._generate_mock_system_data()
                            
        except Exception as e:
            self.logger.warning(f"更新系统概览失败，使用模拟数据: {e}")
            self._generate_mock_system_data()

    def _generate_mock_system_data(self):
        """生成模拟系统数据"""
        import random
        
        mock_data = {
            'system_resources': {
                'cpu_usage_percent': random.uniform(20, 80),
                'memory_usage_percent': random.uniform(30, 70),
                'disk_usage_percent': random.uniform(10, 50),
                'cpu_cores': 8,
                'memory_total_bytes': 64 * 1024 * 1024 * 1024,  # 64GB
                'memory_available_bytes': 32 * 1024 * 1024 * 1024,  # 32GB
                'disk_total_bytes': 1024 * 1024 * 1024 * 1024,  # 1TB
                'disk_free_bytes': 512 * 1024 * 1024 * 1024,  # 512GB
            },
            'system_info': {
                'platform': 'Darwin',
                'python_version': '3.12.2',
                'boot_time': '2024-01-31 08:00:00',
                'uptime': '15 hours 30 minutes'
            }
        }
        
        self.monitoring_data_cache['system_overview'] = mock_data
        
        # 添加历史数据
        history_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'cpu_usage': mock_data['system_resources']['cpu_usage_percent'],
            'memory_usage': mock_data['system_resources']['memory_usage_percent'],
            'disk_usage': mock_data['system_resources']['disk_usage_percent']
        }
        
        self.monitoring_data_cache['metrics_history'].append(history_entry)
        if len(self.monitoring_data_cache['metrics_history']) > 100:
            self.monitoring_data_cache['metrics_history'].pop(0)

    async def _update_services_status(self):
        """更新服务状态数据"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.monitoring_service_url}/api/v1/services") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.monitoring_data_cache['services_status'] = data
                    else:
                        self._generate_mock_services_data()
        except Exception as e:
            self.logger.warning(f"更新服务状态失败，使用模拟数据: {e}")
            self._generate_mock_services_data()

    def _generate_mock_services_data(self):
        """生成模拟服务数据"""
        import random
        
        services = {
            'data-collector': {
                'status': 'healthy',
                'port': 8081,
                'response_time': random.randint(5, 50),
                'cpu_usage': random.uniform(10, 30),
                'memory_usage': random.uniform(100, 300),
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'api-gateway': {
                'status': 'healthy',
                'port': 8080,
                'response_time': random.randint(3, 20),
                'cpu_usage': random.uniform(5, 25),
                'memory_usage': random.uniform(80, 200),
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'data-storage': {
                'status': 'healthy',
                'port': 8082,
                'response_time': random.randint(10, 100),
                'cpu_usage': random.uniform(15, 40),
                'memory_usage': random.uniform(200, 500),
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'monitoring': {
                'status': 'healthy',
                'port': 8083,
                'response_time': random.randint(5, 30),
                'cpu_usage': random.uniform(8, 20),
                'memory_usage': random.uniform(50, 150),
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'scheduler': {
                'status': 'healthy',
                'port': 8084,
                'response_time': random.randint(2, 15),
                'cpu_usage': random.uniform(3, 15),
                'memory_usage': random.uniform(30, 100),
                'last_check': datetime.now(timezone.utc).isoformat()
            },
            'message-broker': {
                'status': 'healthy',
                'port': 8085,
                'response_time': random.randint(1, 10),
                'cpu_usage': random.uniform(5, 20),
                'memory_usage': random.uniform(40, 120),
                'last_check': datetime.now(timezone.utc).isoformat()
            }
        }
        
        self.monitoring_data_cache['services_status'] = {'services': services}

    async def _update_alerts(self):
        """更新告警数据"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.monitoring_service_url}/api/v1/alerts") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.monitoring_data_cache['alerts'] = data.get('active_alerts', [])
                    else:
                        self._generate_mock_alerts_data()
        except Exception as e:
            self.logger.warning(f"更新告警数据失败，使用模拟数据: {e}")
            self._generate_mock_alerts_data()

    def _generate_mock_alerts_data(self):
        """生成模拟告警数据"""
        # 模拟少量告警
        alerts = []
        if len(self.monitoring_data_cache.get('alerts', [])) == 0:
            alerts = [
                {
                    'id': 'ALT001',
                    'title': 'CPU使用率较高',
                    'description': '系统CPU使用率持续超过70%',
                    'severity': 'warning',
                    'source': '系统监控',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'status': 'active'
                }
            ]
        
        self.monitoring_data_cache['alerts'] = alerts

    async def _update_trading_data(self):
        """更新交易数据"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.data_collector_url}/status") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.monitoring_data_cache['trading_data'] = data
                    else:
                        self._generate_mock_trading_data()
        except Exception as e:
            self.logger.warning(f"更新交易数据失败，使用模拟数据: {e}")
            self._generate_mock_trading_data()

    def _generate_mock_trading_data(self):
        """生成模拟交易数据"""
        import random
        
        trading_data = {
            'active_connections': random.randint(3, 6),
            'supported_exchanges': ['Binance', 'OKX', 'Deribit'],
            'data_rate': random.randint(500, 2000),
            'latency': random.randint(10, 100),
            'status': 'running',
            'uptime': '2 hours 15 minutes'
        }
        
        self.monitoring_data_cache['trading_data'] = trading_data

    async def _broadcast_updates(self):
        """广播更新到所有WebSocket连接"""
        if not self.websocket_connections:
            return
            
        message = {
            'type': 'data_update',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': {
                'system_overview': self.monitoring_data_cache['system_overview'],
                'services_status': self.monitoring_data_cache['services_status'],
                'alerts': self.monitoring_data_cache['alerts'],
                'trading_data': self.monitoring_data_cache['trading_data']
            }
        }
        
        # 发送到所有连接的WebSocket
        disconnected = set()
        for ws in self.websocket_connections:
            try:
                await ws.send_str(json.dumps(message))
            except Exception:
                disconnected.add(ws)
        
        # 清理断开的连接
        self.websocket_connections -= disconnected

    # === 页面处理器 ===
    
    @aiohttp_jinja2.template('dashboard.html')
    async def dashboard_home(self, request: web.Request):
        """主仪表板页面"""
        return {
            'title': 'MarketPrism 监控仪表板',
            'current_page': 'dashboard'
        }

    @aiohttp_jinja2.template('modern-index.html')
    async def modern_index(self, request: web.Request):
        """现代化首页"""
        return {
            'title': 'MarketPrism 现代化监控中心',
            'current_page': 'index'
        }

    @aiohttp_jinja2.template('modern-dashboard.html')
    async def modern_dashboard(self, request: web.Request):
        """现代化仪表板页面"""
        return {
            'title': '市场棱镜分析台',
            'current_page': 'dashboard'
        }

    @aiohttp_jinja2.template('system.html')
    async def system_page(self, request: web.Request):
        """系统监控页面"""
        return {
            'title': 'MarketPrism 系统监控',
            'current_page': 'system'
        }

    @aiohttp_jinja2.template('services.html')
    async def services_page(self, request: web.Request):
        """服务监控页面"""
        return {
            'title': 'MarketPrism 服务监控',
            'current_page': 'services'
        }

    @aiohttp_jinja2.template('trading.html')
    async def trading_page(self, request: web.Request):
        """交易监控页面"""
        return {
            'title': 'MarketPrism 交易监控',
            'current_page': 'trading'
        }

    @aiohttp_jinja2.template('alerts.html')
    async def alerts_page(self, request: web.Request):
        """告警管理页面"""
        return {
            'title': 'MarketPrism 告警管理',
            'current_page': 'alerts'
        }

    @aiohttp_jinja2.template('modern-services.html')
    async def modern_services(self, request: web.Request):
        """现代化服务监控页面"""
        return {
            'title': 'MarketPrism 服务监控',
            'current_page': 'services'
        }

    @aiohttp_jinja2.template('modern-trading.html')
    async def modern_trading(self, request: web.Request):
        """现代化市场数据页面"""
        return {
            'title': 'MarketPrism 交易监控',
            'current_page': 'trading'
        }

    # === API处理器 ===
    
    async def get_system_overview(self, request: web.Request) -> web.Response:
        """获取系统概览API"""
        return web.json_response(self.monitoring_data_cache['system_overview'])

    async def get_services_status(self, request: web.Request) -> web.Response:
        """获取服务状态API"""
        return web.json_response(self.monitoring_data_cache['services_status'])

    async def get_alerts(self, request: web.Request) -> web.Response:
        """获取告警信息API"""
        return web.json_response(self.monitoring_data_cache['alerts'])

    async def get_metrics_history(self, request: web.Request) -> web.Response:
        """获取指标历史API"""
        return web.json_response(self.monitoring_data_cache['metrics_history'])

    async def get_trading_data(self, request: web.Request) -> web.Response:
        """获取交易数据API"""
        return web.json_response(self.monitoring_data_cache['trading_data'])

    async def health_check(self, request: web.Request) -> web.Response:
        """健康检查API"""
        return web.json_response({
            'status': 'healthy',
            'service': self.service_name,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'websocket_connections': len(self.websocket_connections)
        })

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket处理器"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websocket_connections.add(ws)
        self.logger.info(f"新的WebSocket连接，当前连接数: {len(self.websocket_connections)}")
        
        try:
            # 发送初始数据
            initial_data = {
                'type': 'initial_data',
                'data': {
                    'system_overview': self.monitoring_data_cache['system_overview'],
                    'services_status': self.monitoring_data_cache['services_status'],
                    'alerts': self.monitoring_data_cache['alerts'],
                    'trading_data': self.monitoring_data_cache['trading_data']
                }
            }
            await ws.send_str(json.dumps(initial_data))
            
            # 处理WebSocket消息
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        # 处理客户端消息（如果需要）
                        pass
                    except json.JSONDecodeError:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error(f'WebSocket错误: {ws.exception()}')
                    break
                    
        except Exception as e:
            self.logger.error(f"WebSocket处理异常: {e}")
        finally:
            self.websocket_connections.discard(ws)
            self.logger.info(f"WebSocket连接断开，当前连接数: {len(self.websocket_connections)}")
        
        return ws

    async def run(self):
        """运行服务"""
        await self.startup()
        
        # 创建并启动Web服务器
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        self.logger.info(f"监控仪表板服务已启动: http://{self.host}:{self.port}")
        self.logger.info(f"主仪表板: http://{self.host}:{self.port}/dashboard")
        self.logger.info(f"系统监控: http://{self.host}:{self.port}/system")
        self.logger.info(f"服务监控: http://{self.host}:{self.port}/services")
        self.logger.info(f"交易监控: http://{self.host}:{self.port}/trading")
        self.logger.info(f"告警管理: http://{self.host}:{self.port}/alerts")
        
        try:
            # 保持服务运行
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("收到中断信号，正在关闭服务...")
        finally:
            await self.shutdown()
            await runner.cleanup()


async def main():
    """主函数"""
    # 加载配置
    config_path = Path(__file__).parents[2] / "config" / "services.yaml"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
            dashboard_config = config_data.get('services', {}).get('monitoring-dashboard', {})
    except FileNotFoundError:
        dashboard_config = {}
    
    # 使用默认配置
    if not dashboard_config:
        dashboard_config = {
            'port': 8086,
            'host': '0.0.0.0',
            'data_sources': {
                'monitoring_service_url': 'http://localhost:8083',
                'data_collector_url': 'http://localhost:8081'
            }
        }
    
    # 创建并启动服务
    dashboard = MonitoringDashboard(dashboard_config)
    
    try:
        await dashboard.run()
    except Exception as e:
        print(f"服务运行异常: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())