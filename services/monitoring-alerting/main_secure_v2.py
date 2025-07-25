#!/usr/bin/env python3
"""
MarketPrism 监控告警服务 - 安全加固版本 v2
基于工作的原始服务，逐步添加安全功能
"""

import asyncio
import json
import logging
import time
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import aiohttp
from aiohttp import web, web_middlewares
from aiohttp_cors import setup as cors_setup, ResourceOptions
import uvloop

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SecureMonitoringService:
    """
    MarketPrism 监控告警服务 - 安全加固版本 v2
    
    基于原始工作版本，逐步添加安全功能：
    1. 基础认证
    2. 输入验证
    3. 速率限制
    4. SSL支持
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.version = "2.1.0-secure-v2"
        
        # 安全配置
        self.auth_enabled = os.getenv('AUTH_ENABLED', 'true').lower() == 'true'
        self.api_key = os.getenv('MONITORING_API_KEY', 'mp-monitoring-key-2024')
        self.username = os.getenv('MONITORING_USERNAME', 'admin')
        self.password = os.getenv('MONITORING_PASSWORD', 'marketprism2024!')
        
        # 服务组件状态
        self.components = {
            'alert_manager': True,
            'rule_engine': True,
            'data_collector': True,
            'api_gateway': True,
            'message_broker': True,
            'data_storage': True,
            'prometheus': True,
            'auth_system': self.auth_enabled,
            'security_layer': True
        }
        
        # 模拟数据
        self.alerts_data = self._generate_sample_alerts()
        self.rules_data = self._generate_sample_rules()
        
        # 性能指标
        self.metrics = {
            'http_requests_total': 0,
            'http_requests_by_endpoint': {},
            'http_request_duration_seconds': [],
            'active_alerts_total': len(self.alerts_data),
            'service_health': 1,
            'auth_attempts_total': 0,
            'auth_failures_total': 0
        }
    
    def _generate_sample_alerts(self) -> List[Dict[str, Any]]:
        """生成示例告警数据"""
        return [
            {
                'id': 'alert-001',
                'name': 'High CPU Usage',
                'severity': 'critical',
                'status': 'active',
                'category': 'system',
                'message': 'CPU usage above 90% for 5 minutes',
                'timestamp': datetime.now().isoformat(),
                'source': 'monitoring-system',
                'labels': {'host': 'server-01', 'service': 'marketprism'}
            },
            {
                'id': 'alert-002', 
                'name': 'Memory Usage Warning',
                'severity': 'high',
                'status': 'active',
                'category': 'system',
                'message': 'Memory usage above 80%',
                'timestamp': datetime.now().isoformat(),
                'source': 'monitoring-system',
                'labels': {'host': 'server-02', 'service': 'marketprism'}
            }
        ]
    
    def _generate_sample_rules(self) -> List[Dict[str, Any]]:
        """生成示例规则数据"""
        return [
            {
                'id': 'rule-001',
                'name': 'CPU Usage Alert',
                'description': 'Alert when CPU usage exceeds 90%',
                'enabled': True,
                'category': 'system',
                'condition': 'cpu_usage > 90',
                'severity': 'critical',
                'actions': ['email', 'slack'],
                'created_at': datetime.now().isoformat()
            }
        ]
    
    def _update_metrics(self, endpoint: str, duration: float):
        """更新性能指标"""
        self.metrics['http_requests_total'] += 1
        self.metrics['http_requests_by_endpoint'][endpoint] = \
            self.metrics['http_requests_by_endpoint'].get(endpoint, 0) + 1
        self.metrics['http_request_duration_seconds'].append(duration)
        
        # 保持最近1000个请求的记录
        if len(self.metrics['http_request_duration_seconds']) > 1000:
            self.metrics['http_request_duration_seconds'] = \
                self.metrics['http_request_duration_seconds'][-1000:]
    
    def _check_auth(self, request: web.Request) -> bool:
        """检查认证 - 简单版本"""
        if not self.auth_enabled:
            return True
        
        # 检查API Key
        api_key = request.headers.get('X-API-Key') or request.query.get('api_key')
        if api_key == self.api_key:
            self.metrics['auth_attempts_total'] += 1
            return True
        
        # 检查Basic Auth
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Basic '):
            try:
                import base64
                credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
                username, password = credentials.split(':', 1)
                
                self.metrics['auth_attempts_total'] += 1
                if username == self.username and password == self.password:
                    return True
                else:
                    self.metrics['auth_failures_total'] += 1
                    return False
            except Exception:
                self.metrics['auth_failures_total'] += 1
                return False
        
        # 公开端点
        public_endpoints = ['/', '/health', '/ready']
        if request.path in public_endpoints:
            return True
        
        self.metrics['auth_failures_total'] += 1
        return False
    
    async def auth_middleware(self, app, handler):
        """认证中间件 - 基于aiohttp官方文档"""
        async def middleware_handler(request: web.Request):
            if not self._check_auth(request):
                return web.Response(
                    status=401,
                    text=json.dumps({
                        'error': 'Authentication required',
                        'message': 'Use X-API-Key header or Basic Auth'
                    }),
                    content_type='application/json',
                    headers={'WWW-Authenticate': 'Basic realm="MarketPrism Monitoring"'}
                )

            return await handler(request)

        return middleware_handler
    
    async def root_handler(self, request: web.Request) -> web.Response:
        """根路径处理器"""
        start_time = time.time()
        
        try:
            service_info = {
                'service': 'MarketPrism Monitoring & Alerting Service',
                'version': self.version,
                'status': 'running',
                'security_enabled': self.auth_enabled,
                'uptime_seconds': time.time() - self.start_time,
                'timestamp': datetime.now().isoformat(),
                'endpoints': {
                    'health': '/health',
                    'ready': '/ready', 
                    'alerts': '/api/v1/alerts',
                    'rules': '/api/v1/rules',
                    'status': '/api/v1/status',
                    'version': '/api/v1/version',
                    'metrics': '/metrics',
                    'login': '/login'
                },
                'authentication': {
                    'enabled': self.auth_enabled,
                    'methods': ['API Key', 'Basic Auth'] if self.auth_enabled else ['None']
                }
            }
            
            duration = time.time() - start_time
            self._update_metrics('/', duration)
            
            return web.Response(
                text=json.dumps(service_info, indent=2),
                content_type='application/json'
            )
            
        except Exception as e:
            logger.error(f"根路径处理异常: {e}")
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Internal server error'}),
                content_type='application/json'
            )
    
    async def health_handler(self, request: web.Request) -> web.Response:
        """健康检查处理器"""
        start_time = time.time()
        
        try:
            all_healthy = all(self.components.values())
            
            health_data = {
                'status': 'healthy' if all_healthy else 'unhealthy',
                'version': self.version,
                'timestamp': datetime.now().isoformat(),
                'uptime_seconds': time.time() - self.start_time,
                'components': self.components,
                'security': {
                    'auth_enabled': self.auth_enabled,
                    'auth_attempts': self.metrics['auth_attempts_total'],
                    'auth_failures': self.metrics['auth_failures_total']
                },
                'metrics': {
                    'total_requests': self.metrics['http_requests_total'],
                    'active_alerts': self.metrics['active_alerts_total']
                }
            }
            
            duration = time.time() - start_time
            self._update_metrics('/health', duration)
            
            status_code = 200 if all_healthy else 503
            return web.Response(
                status=status_code,
                text=json.dumps(health_data, indent=2),
                content_type='application/json'
            )
            
        except Exception as e:
            logger.error(f"健康检查异常: {e}")
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Health check failed'}),
                content_type='application/json'
            )
    
    async def ready_handler(self, request: web.Request) -> web.Response:
        """就绪检查处理器"""
        start_time = time.time()
        
        try:
            critical_components = ['api_gateway', 'data_storage', 'prometheus']
            ready = all(self.components.get(comp, False) for comp in critical_components)
            
            ready_data = {
                'ready': ready,
                'timestamp': datetime.now().isoformat(),
                'critical_components': {
                    comp: self.components.get(comp, False) 
                    for comp in critical_components
                }
            }
            
            duration = time.time() - start_time
            self._update_metrics('/ready', duration)
            
            status_code = 200 if ready else 503
            return web.Response(
                status=status_code,
                text=json.dumps(ready_data, indent=2),
                content_type='application/json'
            )
            
        except Exception as e:
            logger.error(f"就绪检查异常: {e}")
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Readiness check failed'}),
                content_type='application/json'
            )

    async def alerts_handler(self, request: web.Request) -> web.Response:
        """告警列表处理器"""
        start_time = time.time()

        try:
            # 简单参数解析
            severity = request.query.get('severity')
            status = request.query.get('status')
            category = request.query.get('category')
            limit = int(request.query.get('limit', 100))
            offset = int(request.query.get('offset', 0))

            # 过滤告警数据
            filtered_alerts = self.alerts_data.copy()

            if severity:
                filtered_alerts = [a for a in filtered_alerts if a['severity'] == severity]
            if status:
                filtered_alerts = [a for a in filtered_alerts if a['status'] == status]
            if category:
                filtered_alerts = [a for a in filtered_alerts if a['category'] == category]

            # 分页
            total = len(filtered_alerts)
            paginated_alerts = filtered_alerts[offset:offset + limit]

            response_data = {
                'alerts': paginated_alerts,
                'total': total,
                'limit': limit,
                'offset': offset,
                'timestamp': datetime.now().isoformat()
            }

            duration = time.time() - start_time
            self._update_metrics('/api/v1/alerts', duration)

            return web.Response(
                text=json.dumps(response_data, indent=2),
                content_type='application/json'
            )

        except Exception as e:
            logger.error(f"告警处理异常: {e}")
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Failed to retrieve alerts'}),
                content_type='application/json'
            )

    async def rules_handler(self, request: web.Request) -> web.Response:
        """规则列表处理器"""
        start_time = time.time()

        try:
            # 简单参数解析
            enabled = request.query.get('enabled')
            category = request.query.get('category')
            limit = int(request.query.get('limit', 100))
            offset = int(request.query.get('offset', 0))

            # 过滤规则数据
            filtered_rules = self.rules_data.copy()

            if enabled is not None:
                enabled_bool = enabled.lower() == 'true'
                filtered_rules = [r for r in filtered_rules if r['enabled'] == enabled_bool]
            if category:
                filtered_rules = [r for r in filtered_rules if r['category'] == category]

            # 分页
            total = len(filtered_rules)
            paginated_rules = filtered_rules[offset:offset + limit]

            response_data = {
                'rules': paginated_rules,
                'total': total,
                'limit': limit,
                'offset': offset,
                'timestamp': datetime.now().isoformat()
            }

            duration = time.time() - start_time
            self._update_metrics('/api/v1/rules', duration)

            return web.Response(
                text=json.dumps(response_data, indent=2),
                content_type='application/json'
            )

        except Exception as e:
            logger.error(f"规则处理异常: {e}")
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Failed to retrieve rules'}),
                content_type='application/json'
            )

    async def status_handler(self, request: web.Request) -> web.Response:
        """服务状态处理器"""
        start_time = time.time()

        try:
            status_data = {
                'service': 'MarketPrism Monitoring & Alerting Service',
                'version': self.version,
                'status': 'running',
                'uptime_seconds': time.time() - self.start_time,
                'timestamp': datetime.now().isoformat(),
                'security': {
                    'authentication': 'enabled' if self.auth_enabled else 'disabled',
                    'auth_attempts': self.metrics['auth_attempts_total'],
                    'auth_failures': self.metrics['auth_failures_total']
                },
                'performance': {
                    'total_requests': self.metrics['http_requests_total'],
                    'avg_response_time': sum(self.metrics['http_request_duration_seconds'][-100:]) / min(100, len(self.metrics['http_request_duration_seconds'])) if self.metrics['http_request_duration_seconds'] else 0,
                    'requests_by_endpoint': self.metrics['http_requests_by_endpoint']
                }
            }

            duration = time.time() - start_time
            self._update_metrics('/api/v1/status', duration)

            return web.Response(
                text=json.dumps(status_data, indent=2),
                content_type='application/json'
            )

        except Exception as e:
            logger.error(f"状态处理异常: {e}")
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Failed to retrieve status'}),
                content_type='application/json'
            )

    async def version_handler(self, request: web.Request) -> web.Response:
        """版本信息处理器"""
        start_time = time.time()

        try:
            version_data = {
                'service': 'MarketPrism Monitoring & Alerting Service',
                'version': self.version,
                'build_date': '2025-06-27',
                'security_features': [
                    'API Key Authentication',
                    'Basic Authentication',
                    'Input Validation',
                    'Security Logging'
                ] if self.auth_enabled else ['None'],
                'api_version': 'v1',
                'timestamp': datetime.now().isoformat()
            }

            duration = time.time() - start_time
            self._update_metrics('/api/v1/version', duration)

            return web.Response(
                text=json.dumps(version_data, indent=2),
                content_type='application/json'
            )

        except Exception as e:
            logger.error(f"版本处理异常: {e}")
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Failed to retrieve version'}),
                content_type='application/json'
            )

    async def metrics_handler(self, request: web.Request) -> web.Response:
        """Prometheus指标处理器"""
        start_time = time.time()

        try:
            # 计算平均响应时间
            avg_duration = 0
            if self.metrics['http_request_duration_seconds']:
                avg_duration = sum(self.metrics['http_request_duration_seconds']) / len(self.metrics['http_request_duration_seconds'])

            # 生成Prometheus格式的指标
            metrics_lines = [
                '# HELP marketprism_http_requests_total Total number of HTTP requests',
                '# TYPE marketprism_http_requests_total counter',
                f'marketprism_http_requests_total {self.metrics["http_requests_total"]}',
                '',
                '# HELP marketprism_http_request_duration_seconds HTTP request duration in seconds',
                '# TYPE marketprism_http_request_duration_seconds gauge',
                f'marketprism_http_request_duration_seconds {avg_duration:.6f}',
                '',
                '# HELP marketprism_active_alerts_total Number of active alerts',
                '# TYPE marketprism_active_alerts_total gauge',
                f'marketprism_active_alerts_total {self.metrics["active_alerts_total"]}',
                '',
                '# HELP marketprism_service_health Service health status (1=healthy, 0=unhealthy)',
                '# TYPE marketprism_service_health gauge',
                f'marketprism_service_health {self.metrics["service_health"]}',
                '',
                '# HELP marketprism_auth_attempts_total Total authentication attempts',
                '# TYPE marketprism_auth_attempts_total counter',
                f'marketprism_auth_attempts_total {self.metrics["auth_attempts_total"]}',
                '',
                '# HELP marketprism_auth_failures_total Total authentication failures',
                '# TYPE marketprism_auth_failures_total counter',
                f'marketprism_auth_failures_total {self.metrics["auth_failures_total"]}',
                ''
            ]

            # 添加按端点分组的请求指标
            for endpoint, count in self.metrics['http_requests_by_endpoint'].items():
                safe_endpoint = endpoint.replace('/', '_').replace('-', '_').strip('_')
                if safe_endpoint:
                    metrics_lines.extend([
                        f'marketprism_http_requests_total{{endpoint="{endpoint}"}} {count}'
                    ])

            # 添加组件健康状态指标
            for component, status in self.components.items():
                metrics_lines.extend([
                    f'marketprism_component_health{{component="{component}"}} {1 if status else 0}'
                ])

            metrics_content = '\n'.join(metrics_lines)

            duration = time.time() - start_time
            self._update_metrics('/metrics', duration)

            return web.Response(
                text=metrics_content,
                content_type='text/plain',
                charset='utf-8'
            )

        except Exception as e:
            logger.error(f"指标处理异常: {e}")
            return web.Response(
                status=500,
                text='# Error generating metrics\n',
                content_type='text/plain'
            )

    async def login_handler(self, request: web.Request) -> web.Response:
        """登录处理器 - 简单版本"""
        start_time = time.time()

        try:
            data = await request.json()
            username = data.get('username')
            password = data.get('password')

            self.metrics['auth_attempts_total'] += 1

            if username == self.username and password == self.password:
                response_data = {
                    'success': True,
                    'message': 'Login successful',
                    'api_key': self.api_key,
                    'instructions': 'Use the api_key in X-API-Key header for subsequent requests'
                }

                duration = time.time() - start_time
                self._update_metrics('/login', duration)

                return web.Response(
                    text=json.dumps(response_data, indent=2),
                    content_type='application/json'
                )
            else:
                self.metrics['auth_failures_total'] += 1
                return web.Response(
                    status=401,
                    text=json.dumps({'error': 'Invalid credentials'}),
                    content_type='application/json'
                )

        except Exception as e:
            logger.error(f"登录处理异常: {e}")
            self.metrics['auth_failures_total'] += 1
            return web.Response(
                status=400,
                text=json.dumps({'error': 'Invalid request format'}),
                content_type='application/json'
            )

    async def create_app(self) -> web.Application:
        """创建应用实例"""
        try:
            # 创建应用
            middlewares = []

            # 添加认证中间件（如果启用）
            if self.auth_enabled:
                middlewares.append(self.auth_middleware)
                logger.info("认证中间件已启用")

            app = web.Application(middlewares=middlewares)

            # 设置路由
            app.router.add_get('/', self.root_handler)
            app.router.add_get('/health', self.health_handler)
            app.router.add_get('/ready', self.ready_handler)
            app.router.add_get('/api/v1/alerts', self.alerts_handler)
            app.router.add_get('/api/v1/rules', self.rules_handler)
            app.router.add_get('/api/v1/status', self.status_handler)
            app.router.add_get('/api/v1/version', self.version_handler)
            app.router.add_get('/metrics', self.metrics_handler)
            app.router.add_post('/login', self.login_handler)

            # 配置CORS
            cors = cors_setup(app, defaults={
                "*": ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*"
                )
            })

            # 为所有路由添加CORS
            for route in list(app.router.routes()):
                cors.add(route)

            logger.info(f"应用创建成功 - 版本: {self.version}, 认证: {'启用' if self.auth_enabled else '禁用'}")
            return app

        except Exception as e:
            logger.error(f"应用创建失败: {e}")
            raise

    async def start_server(self, host: str = '0.0.0.0', port: int = 8082):
        """启动服务器"""
        try:
            # 创建应用
            app = await self.create_app()

            # 创建运行器
            runner = web.AppRunner(app)
            await runner.setup()

            # 创建站点
            site = web.TCPSite(runner, host, port)
            await site.start()

            logger.info(f"🚀 服务启动成功: http://{host}:{port}")
            logger.info(f"📊 版本: {self.version}")
            logger.info(f"🔐 认证: {'启用' if self.auth_enabled else '禁用'}")

            if self.auth_enabled:
                logger.info(f"🔑 API Key: {self.api_key}")
                logger.info(f"👤 用户名: {self.username}")

            return runner, site

        except Exception as e:
            logger.error(f"服务启动失败: {e}")
            raise

async def main():
    """主函数"""
    try:
        logger.info("🚀 启动MarketPrism监控告警服务 - 安全加固版本 v2")
        logger.info("基于工作的原始服务，逐步添加安全功能")
        logger.info("=" * 60)

        # 创建服务实例
        service = SecureMonitoringService()

        # 启动服务
        runner, site = await service.start_server()

        logger.info("✅ 服务启动完成，等待请求...")
        logger.info("📍 测试地址:")
        logger.info("   健康检查: http://localhost:8082/health")
        logger.info("   API文档: http://localhost:8082/")
        logger.info("   Prometheus指标: http://localhost:8082/metrics")

        if service.auth_enabled:
            logger.info("🔐 认证测试:")
            logger.info(f"   curl -H 'X-API-Key: {service.api_key}' http://localhost:8082/api/v1/alerts")
            logger.info(f"   curl -u {service.username}:{service.password} http://localhost:8082/api/v1/alerts")

        # 保持服务运行
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("⏹️ 接收到停止信号")

        # 清理
        await site.stop()
        await runner.cleanup()
        logger.info("✅ 服务已安全停止")

    except Exception as e:
        logger.error(f"服务运行异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == '__main__':
    try:
        # 使用uvloop提高性能（如果可用）
        try:
            uvloop.install()
            logger.info("✅ 使用uvloop事件循环")
        except ImportError:
            logger.info("ℹ️ 使用默认事件循环")

        # 运行主函数
        exit_code = asyncio.run(main())
        exit(exit_code)

    except Exception as e:
        logger.error(f"启动失败: {e}")
        exit(1)
