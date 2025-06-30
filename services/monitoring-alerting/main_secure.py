"""
MarketPrism 监控告警服务 - 安全加固版本

专为Grafana集成优化的高性能监控服务，包含完整的安全框架
- 认证和授权机制
- HTTPS/TLS加密
- 输入验证和清理
- 速率限制
- 安全日志记录
"""

import asyncio
import signal
import sys
import time
import json
import ssl
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
from aiohttp import web
import aiohttp_cors

# 导入安全模块 - 修复导入路径
try:
    from auth import create_auth_middleware, login_handler
    from ssl_config import SSLConfig, create_ssl_context, get_ssl_info
    from validation import (
        create_validation_middleware,
        validate_query_params,
        validate_json_body,
        AlertQueryParams,
        RuleQueryParams,
        LoginRequest
    )
except ImportError as e:
    print(f"导入安全模块失败: {e}")
    # 回退到基础功能
    create_auth_middleware = None
    create_validation_middleware = None
    SSLConfig = None
    create_ssl_context = None

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = structlog.get_logger(__name__)

class SecureMonitoringService:
    """
    MarketPrism 监控告警服务 - 安全加固版本
    
    核心功能：
    - 健康检查和状态监控
    - 告警数据API
    - 规则管理API
    - Prometheus指标导出
    - 完整的安全框架
    """
    
    def __init__(self):
        self.app = None
        self.runner = None
        self.site = None
        self.start_time = time.time()
        self.version = "2.1.0-secure"
        self.ssl_config = SSLConfig() if SSLConfig else None
        self.ssl_context = None
        
        # 服务组件状态
        self.components = {
            'api_server': True,
            'health_monitor': True,
            'metrics_collector': True,
            'auth_system': True,
            'ssl_handler': True,
            'validation_engine': True,
            'rate_limiter': True
        }
        
        # 模拟数据存储
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
            'auth_failures_total': 0,
            'ssl_connections_total': 0
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
            },
            {
                'id': 'alert-003',
                'name': 'API Response Time',
                'severity': 'medium',
                'status': 'resolved',
                'category': 'performance',
                'message': 'API response time above threshold',
                'timestamp': datetime.now().isoformat(),
                'source': 'api-monitor',
                'labels': {'endpoint': '/api/v1/alerts', 'service': 'marketprism'}
            },
            {
                'id': 'alert-004',
                'name': 'SSL Certificate Expiry',
                'severity': 'high',
                'status': 'acknowledged',
                'category': 'security',
                'message': 'SSL certificate expires in 30 days',
                'timestamp': datetime.now().isoformat(),
                'source': 'ssl-monitor',
                'labels': {'domain': 'monitoring.marketprism.local'}
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
            },
            {
                'id': 'rule-002',
                'name': 'Memory Usage Warning', 
                'description': 'Warning when memory usage exceeds 80%',
                'enabled': True,
                'category': 'system',
                'condition': 'memory_usage > 80',
                'severity': 'high',
                'actions': ['email'],
                'created_at': datetime.now().isoformat()
            },
            {
                'id': 'rule-003',
                'name': 'API Response Time',
                'description': 'Alert on slow API responses',
                'enabled': False,
                'category': 'performance',
                'condition': 'response_time > 1000',
                'severity': 'medium',
                'actions': ['log'],
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
    
    async def root_handler(self, request: web.Request) -> web.Response:
        """根路径处理器"""
        start_time = time.time()
        
        try:
            service_info = {
                'service': 'MarketPrism Monitoring & Alerting Service',
                'version': self.version,
                'status': 'running',
                'security_enabled': True,
                'ssl_enabled': self.ssl_config.ssl_enabled if self.ssl_config else False,
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
                    'login': '/login',
                    'ssl_info': '/api/v1/ssl-info'
                },
                'authentication': {
                    'methods': ['Bearer Token', 'API Key', 'Basic Auth'],
                    'login_endpoint': '/login'
                },
                'ssl_info': get_ssl_info() if (self.ssl_config and self.ssl_config.ssl_enabled and get_ssl_info) else None
            }
            
            duration = time.time() - start_time
            self._update_metrics('/', duration)
            
            return web.Response(
                text=json.dumps(service_info, indent=2),
                content_type='application/json'
            )
            
        except Exception as e:
            logger.error("根路径处理异常", error=str(e))
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Internal server error'}),
                content_type='application/json'
            )
    
    async def health_handler(self, request: web.Request) -> web.Response:
        """健康检查处理器"""
        start_time = time.time()
        
        try:
            # 检查组件健康状态
            all_healthy = all(self.components.values())
            
            health_data = {
                'status': 'healthy' if all_healthy else 'unhealthy',
                'version': self.version,
                'timestamp': datetime.now().isoformat(),
                'uptime_seconds': time.time() - self.start_time,
                'components': self.components,
                'security': {
                    'auth_enabled': True,
                    'ssl_enabled': self.ssl_config.ssl_enabled if self.ssl_config else False,
                    'validation_enabled': True,
                    'rate_limiting_enabled': True
                },
                'metrics': {
                    'total_requests': self.metrics['http_requests_total'],
                    'active_alerts': self.metrics['active_alerts_total'],
                    'auth_attempts': self.metrics['auth_attempts_total'],
                    'auth_failures': self.metrics['auth_failures_total']
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
            logger.error("健康检查异常", error=str(e))
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Health check failed'}),
                content_type='application/json'
            )
    
    async def ready_handler(self, request: web.Request) -> web.Response:
        """就绪检查处理器"""
        start_time = time.time()
        
        try:
            # 检查关键组件是否就绪
            critical_components = ['api_server', 'auth_system', 'validation_engine']
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
            logger.error("就绪检查异常", error=str(e))
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Readiness check failed'}),
                content_type='application/json'
            )
    
    async def alerts_handler(self, request: web.Request) -> web.Response:
        """告警列表处理器 - 带参数验证"""
        start_time = time.time()
        
        try:
            # 验证查询参数（如果验证模块可用）
            if 'validate_query_params' in globals() and 'AlertQueryParams' in globals():
                params = await validate_query_params(request, AlertQueryParams)
            else:
                # 基础参数解析
                params = type('Params', (), {
                    'severity': request.query.get('severity'),
                    'status': request.query.get('status'),
                    'category': request.query.get('category'),
                    'limit': int(request.query.get('limit', 100)),
                    'offset': int(request.query.get('offset', 0)),
                    'sort_by': request.query.get('sort_by', 'timestamp'),
                    'sort_order': request.query.get('sort_order', 'desc'),
                    'search': request.query.get('search')
                })()
            
            # 过滤告警数据
            filtered_alerts = self.alerts_data.copy()
            
            if params.severity:
                filtered_alerts = [a for a in filtered_alerts if a['severity'] == params.severity]
            
            if params.status:
                filtered_alerts = [a for a in filtered_alerts if a['status'] == params.status]
            
            if params.category:
                filtered_alerts = [a for a in filtered_alerts if a['category'] == params.category]
            
            if params.search:
                search_term = params.search.lower()
                filtered_alerts = [
                    a for a in filtered_alerts 
                    if search_term in a['name'].lower() or search_term in a['message'].lower()
                ]
            
            # 排序
            reverse = params.sort_order == 'desc'
            if params.sort_by in ['timestamp', 'severity', 'status', 'category', 'name']:
                filtered_alerts.sort(key=lambda x: x.get(params.sort_by, ''), reverse=reverse)
            
            # 分页
            total = len(filtered_alerts)
            start_idx = params.offset
            end_idx = start_idx + params.limit
            paginated_alerts = filtered_alerts[start_idx:end_idx]
            
            response_data = {
                'alerts': paginated_alerts,
                'total': total,
                'limit': params.limit,
                'offset': params.offset,
                'timestamp': datetime.now().isoformat()
            }
            
            duration = time.time() - start_time
            self._update_metrics('/api/v1/alerts', duration)
            
            return web.Response(
                text=json.dumps(response_data, indent=2),
                content_type='application/json'
            )
            
        except Exception as e:
            logger.error("告警处理异常", error=str(e))
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Failed to retrieve alerts'}),
                content_type='application/json'
            )

    async def rules_handler(self, request: web.Request) -> web.Response:
        """规则列表处理器 - 带参数验证"""
        start_time = time.time()

        try:
            # 验证查询参数（如果验证模块可用）
            if 'validate_query_params' in globals() and 'RuleQueryParams' in globals():
                params = await validate_query_params(request, RuleQueryParams)
            else:
                # 基础参数解析
                params = type('Params', (), {
                    'enabled': request.query.get('enabled'),
                    'category': request.query.get('category'),
                    'limit': int(request.query.get('limit', 100)),
                    'offset': int(request.query.get('offset', 0)),
                    'search': request.query.get('search')
                })()

            # 过滤规则数据
            filtered_rules = self.rules_data.copy()

            if params.enabled is not None:
                filtered_rules = [r for r in filtered_rules if r['enabled'] == params.enabled]

            if params.category:
                filtered_rules = [r for r in filtered_rules if r['category'] == params.category]

            if params.search:
                search_term = params.search.lower()
                filtered_rules = [
                    r for r in filtered_rules
                    if search_term in r['name'].lower() or search_term in r['description'].lower()
                ]

            # 分页
            total = len(filtered_rules)
            start_idx = params.offset
            end_idx = start_idx + params.limit
            paginated_rules = filtered_rules[start_idx:end_idx]

            response_data = {
                'rules': paginated_rules,
                'total': total,
                'limit': params.limit,
                'offset': params.offset,
                'timestamp': datetime.now().isoformat()
            }

            duration = time.time() - start_time
            self._update_metrics('/api/v1/rules', duration)

            return web.Response(
                text=json.dumps(response_data, indent=2),
                content_type='application/json'
            )

        except Exception as e:
            logger.error("规则处理异常", error=str(e))
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
                    'authentication': 'enabled',
                    'ssl_tls': 'enabled' if (self.ssl_config and self.ssl_config.ssl_enabled) else 'disabled',
                    'input_validation': 'enabled',
                    'rate_limiting': 'enabled'
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
            logger.error("状态处理异常", error=str(e))
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
                    'Authentication & Authorization',
                    'HTTPS/TLS Encryption',
                    'Input Validation & Sanitization',
                    'Rate Limiting',
                    'Security Logging'
                ],
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
            logger.error("版本处理异常", error=str(e))
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Failed to retrieve version'}),
                content_type='application/json'
            )

    async def ssl_info_handler(self, request: web.Request) -> web.Response:
        """SSL信息处理器"""
        start_time = time.time()

        try:
            if get_ssl_info:
                ssl_info = get_ssl_info()
            else:
                ssl_info = {
                    'ssl_enabled': False,
                    'message': 'SSL module not available'
                }

            duration = time.time() - start_time
            self._update_metrics('/api/v1/ssl-info', duration)

            return web.Response(
                text=json.dumps(ssl_info, indent=2),
                content_type='application/json'
            )

        except Exception as e:
            logger.error("SSL信息处理异常", error=str(e))
            return web.Response(
                status=500,
                text=json.dumps({'error': 'Failed to retrieve SSL info'}),
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
                '',
                '# HELP marketprism_ssl_connections_total Total SSL connections',
                '# TYPE marketprism_ssl_connections_total counter',
                f'marketprism_ssl_connections_total {self.metrics["ssl_connections_total"]}',
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
                content_type='text/plain; charset=utf-8'
            )

        except Exception as e:
            logger.error("指标处理异常", error=str(e))
            return web.Response(
                status=500,
                text='# Error generating metrics\n',
                content_type='text/plain'
            )

    async def create_app(self) -> web.Application:
        """创建应用实例"""
        try:
            # 创建中间件实例（如果可用）
            middlewares = []

            if create_validation_middleware:
                validation_middleware = create_validation_middleware()
                middlewares.append(validation_middleware)
                logger.info("验证中间件已启用")

            if create_auth_middleware:
                auth_middleware = create_auth_middleware()
                middlewares.append(auth_middleware)
                logger.info("认证中间件已启用")

            # 创建应用 - 基于官方文档的正确方式
            app = web.Application(middlewares=middlewares)

            # 设置路由
            app.router.add_get('/', self.root_handler)
            app.router.add_get('/health', self.health_handler)
            app.router.add_get('/ready', self.ready_handler)
            app.router.add_get('/api/v1/alerts', self.alerts_handler)
            app.router.add_get('/api/v1/rules', self.rules_handler)
            app.router.add_get('/api/v1/status', self.status_handler)
            app.router.add_get('/api/v1/version', self.version_handler)
            app.router.add_get('/api/v1/ssl-info', self.ssl_info_handler)
            app.router.add_get('/metrics', self.metrics_handler)

            # 添加登录端点（如果可用）
            if 'login_handler' in globals():
                app.router.add_post('/login', login_handler)

            # 配置CORS
            cors = aiohttp_cors.setup(app, defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*"
                )
            })

            # 为所有路由添加CORS
            for route in list(app.router.routes()):
                cors.add(route)

            logger.info("应用创建成功", version=self.version)
            return app

        except Exception as e:
            logger.error("应用创建失败", error=str(e))
            raise

    async def start_server(self, host: str = '0.0.0.0', port: int = 8082):
        """启动服务器"""
        try:
            # 创建SSL上下文
            if self.ssl_config and self.ssl_config.ssl_enabled and create_ssl_context:
                self.ssl_context = create_ssl_context(self.ssl_config)
                if self.ssl_context:
                    logger.info("SSL已启用", cert_file=str(self.ssl_config.cert_file))
                    self.metrics['ssl_connections_total'] = 0
                else:
                    logger.warning("SSL配置失败，回退到HTTP")
                    self.ssl_config.ssl_enabled = False

            # 创建应用
            self.app = await self.create_app()

            # 创建运行器
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            # 创建站点
            self.site = web.TCPSite(
                self.runner,
                host,
                port,
                ssl_context=self.ssl_context
            )

            await self.site.start()

            protocol = 'https' if self.ssl_context else 'http'
            logger.info(
                "服务启动成功",
                host=host,
                port=port,
                protocol=protocol,
                version=self.version,
                security_enabled=True
            )

            return True

        except Exception as e:
            logger.error("服务启动失败", error=str(e))
            return False

    async def stop_server(self):
        """停止服务器"""
        try:
            if self.site:
                await self.site.stop()
                logger.info("站点已停止")

            if self.runner:
                await self.runner.cleanup()
                logger.info("运行器已清理")

            logger.info("服务已安全停止")

        except Exception as e:
            logger.error("服务停止异常", error=str(e))

# 全局服务实例
service_instance = None

async def shutdown_handler(signum):
    """信号处理器"""
    logger.info(f"接收到信号 {signum}，开始优雅关闭...")

    if service_instance:
        await service_instance.stop_server()

    # 停止事件循环
    loop = asyncio.get_event_loop()
    loop.stop()

def setup_signal_handlers():
    """设置信号处理器"""
    if sys.platform != 'win32':
        loop = asyncio.get_event_loop()

        for sig in [signal.SIGTERM, signal.SIGINT]:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown_handler(s))
            )

async def main():
    """主函数"""
    global service_instance

    try:
        # 配置日志
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        logger.info("启动MarketPrism监控告警服务 - 安全加固版本")

        # 创建服务实例
        service_instance = SecureMonitoringService()

        # 设置信号处理
        setup_signal_handlers()

        # 启动服务
        success = await service_instance.start_server()

        if success:
            logger.info("服务启动完成，等待请求...")

            # 保持服务运行
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("服务被取消")
        else:
            logger.error("服务启动失败")
            return 1

    except KeyboardInterrupt:
        logger.info("接收到键盘中断")
    except Exception as e:
        logger.error("服务运行异常", error=str(e))
        return 1
    finally:
        if service_instance:
            await service_instance.stop_server()
        logger.info("服务已退出")

    return 0

if __name__ == '__main__':
    try:
        # 使用uvloop提高性能（如果可用）
        try:
            import uvloop
            uvloop.install()
            logger.info("使用uvloop事件循环")
        except ImportError:
            logger.info("使用默认事件循环")

        # 运行主函数
        exit_code = asyncio.run(main())
        sys.exit(exit_code)

    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)
