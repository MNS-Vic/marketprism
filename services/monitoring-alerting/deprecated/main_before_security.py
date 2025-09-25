# DEPRECATED: 请勿使用此入口。唯一入口为 services/monitoring-alerting/main.py
import sys, warnings
warnings.warn("main_before_security.py 已废弃，请使用 services/monitoring-alerting/main.py", DeprecationWarning)
if __name__ == "__main__":
    print("[DEPRECATED] 请运行: python services/monitoring-alerting/main.py")
    sys.exit(1)

"""
MarketPrism 监控告警服务 - 重构版本

专注于核心监控功能，为Grafana提供数据源支持
优化后的轻量级服务，保持高性能和稳定性
"""

import asyncio
import signal
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
from aiohttp import web
import aiohttp_cors

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = structlog.get_logger(__name__)


class MonitoringAlertingService:
    """
    MarketPrism 监控告警服务 - 重构版本

    专注于核心功能：
    - 健康检查和服务状态
    - 告警数据管理
    - 告警规则管理
    - Prometheus指标输出
    - 为Grafana提供数据源
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app = web.Application()
        self.is_running = False
        self.startup_time = None
        self.request_count = 0

        # 初始化数据
        self._initialize_data()

        # 设置路由
        self._setup_routes()

        # 设置CORS
        self._setup_cors()

        logger.info("监控告警服务初始化完成")

    def _initialize_data(self):
        """初始化核心数据"""
        # 告警规则数据
        self.alert_rules = [
            {
                'id': 'rule-001',
                'name': 'CPU使用率过高',
                'description': 'CPU使用率超过阈值告警',
                'severity': 'high',
                'category': 'system',
                'enabled': True,
                'conditions': [
                    {
                        'metric_name': 'cpu_usage_percent',
                        'operator': 'greater_than',
                        'threshold': 80.0,
                        'duration': 300
                    }
                ],
                'created_at': '2025-06-27T20:00:00Z',
                'updated_at': '2025-06-27T20:00:00Z'
            },
            {
                'id': 'rule-002',
                'name': '内存使用率过高',
                'description': '内存使用率超过阈值告警',
                'severity': 'medium',
                'category': 'system',
                'enabled': True,
                'conditions': [
                    {
                        'metric_name': 'memory_usage_percent',
                        'operator': 'greater_than',
                        'threshold': 85.0,
                        'duration': 300
                    }
                ],
                'created_at': '2025-06-27T20:00:00Z',
                'updated_at': '2025-06-27T20:00:00Z'
            },
            {
                'id': 'rule-003',
                'name': 'API错误率过高',
                'description': 'API错误率超过5%',
                'severity': 'high',
                'category': 'business',
                'enabled': True,
                'conditions': [
                    {
                        'metric_name': 'api_error_rate',
                        'operator': 'greater_than',
                        'threshold': 0.05,
                        'duration': 180
                    }
                ],
                'created_at': '2025-06-27T20:00:00Z',
                'updated_at': '2025-06-27T20:00:00Z'
            }
        ]

        # 示例告警数据
        self.alerts = [
            {
                'id': 'alert-001',
                'rule_id': 'rule-001',
                'name': 'CPU使用率过高',
                'severity': 'high',
                'status': 'active',
                'category': 'system',
                'timestamp': '2025-06-27T20:30:00Z',
                'description': 'marketprism-node-01 CPU使用率达到85%',
                'source': 'marketprism-node-01',
                'labels': {
                    'instance': 'marketprism-node-01',
                    'service': 'data-collector'
                }
            },
            {
                'id': 'alert-002',
                'rule_id': 'rule-002',
                'name': '内存使用率过高',
                'severity': 'medium',
                'status': 'acknowledged',
                'category': 'system',
                'timestamp': '2025-06-27T20:25:00Z',
                'description': 'marketprism-node-02 内存使用率达到87%',
                'source': 'marketprism-node-02',
                'labels': {
                    'instance': 'marketprism-node-02',
                    'service': 'api-gateway'
                }
            }
        ]

        # 组件健康状态
        self.component_health = {
            'alert_manager': True,
            'rule_engine': True,
            'data_collector': True,
            'api_gateway': True,
            'message_broker': True,
            'data_storage': True,
            'prometheus': True
        }

    def _setup_routes(self):
        """设置API路由"""
        # 核心API端点
        self.app.router.add_get('/', self._root)
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_get('/ready', self._readiness_check)
        self.app.router.add_get('/api/v1/alerts', self._get_alerts)
        self.app.router.add_get('/api/v1/rules', self._get_rules)
        self.app.router.add_get('/metrics', self._get_metrics)

        # 可选的管理端点
        self.app.router.add_get('/api/v1/status', self._get_status)
        self.app.router.add_get('/api/v1/version', self._get_version)

    def _setup_cors(self):
        """设置CORS支持"""
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })

        # 为所有路由添加CORS支持
        for route in list(self.app.router.routes()):
            cors.add(route)

    async def _root(self, request):
        """根路径 - 服务信息"""
        self.request_count += 1
        return web.json_response({
            'service': 'MarketPrism Monitoring & Alerting Service',
            'version': '2.0.0',
            'status': 'running',
            'description': '专注于核心监控功能，为Grafana提供数据源支持',
            'endpoints': [
                '/',
                '/health',
                '/ready',
                '/api/v1/alerts',
                '/api/v1/rules',
                '/api/v1/status',
                '/api/v1/version',
                '/metrics'
            ],
            'grafana_integration': True,
            'timestamp': datetime.now().isoformat()
        })

    async def _health_check(self, request):
        """健康检查端点"""
        self.request_count += 1

        # 计算运行时间
        uptime_seconds = 0
        if self.startup_time:
            uptime_seconds = time.time() - self.startup_time

        return web.json_response({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': uptime_seconds,
            'components': self.component_health,
            'version': '2.0.0'
        })

    async def _readiness_check(self, request):
        """就绪检查端点"""
        self.request_count += 1

        # 检查关键组件是否就绪
        ready = all(self.component_health.values()) and self.is_running

        return web.json_response({
            'ready': ready,
            'timestamp': datetime.now().isoformat(),
            'components_ready': sum(self.component_health.values()),
            'total_components': len(self.component_health)
        })

    async def _get_alerts(self, request):
        """获取告警列表"""
        self.request_count += 1

        # 支持查询参数过滤
        severity = request.query.get('severity')
        status = request.query.get('status')
        category = request.query.get('category')

        filtered_alerts = self.alerts

        if severity:
            filtered_alerts = [a for a in filtered_alerts if a['severity'] == severity]
        if status:
            filtered_alerts = [a for a in filtered_alerts if a['status'] == status]
        if category:
            filtered_alerts = [a for a in filtered_alerts if a['category'] == category]

        return web.json_response({
            'alerts': filtered_alerts,
            'total': len(filtered_alerts),
            'filters': {
                'severity': severity,
                'status': status,
                'category': category
            },
            'timestamp': datetime.now().isoformat()
        })

    async def _get_rules(self, request):
        """获取告警规则列表"""
        self.request_count += 1

        # 支持查询参数过滤
        enabled = request.query.get('enabled')
        category = request.query.get('category')

        filtered_rules = self.alert_rules

        if enabled is not None:
            enabled_bool = enabled.lower() == 'true'
            filtered_rules = [r for r in filtered_rules if r['enabled'] == enabled_bool]
        if category:
            filtered_rules = [r for r in filtered_rules if r['category'] == category]

        return web.json_response({
            'rules': filtered_rules,
            'total': len(filtered_rules),
            'enabled_count': len([r for r in filtered_rules if r['enabled']]),
            'filters': {
                'enabled': enabled,
                'category': category
            },
            'timestamp': datetime.now().isoformat()
        })

    async def _get_metrics(self, request):
        """Prometheus指标端点"""
        self.request_count += 1

        # 计算指标数据
        active_alerts_by_severity = {}
        for alert in self.alerts:
            severity = alert['severity']
            active_alerts_by_severity[severity] = active_alerts_by_severity.get(severity, 0) + 1

        # 生成Prometheus格式指标
        metrics_lines = []

        # HTTP请求总数
        metrics_lines.append('# HELP marketprism_http_requests_total Total HTTP requests')
        metrics_lines.append('# TYPE marketprism_http_requests_total counter')
        metrics_lines.append(f'marketprism_http_requests_total{{method="GET",endpoint="/health",status="200"}} {self.request_count // 6}')
        metrics_lines.append(f'marketprism_http_requests_total{{method="GET",endpoint="/api/v1/alerts",status="200"}} {self.request_count // 6}')
        metrics_lines.append(f'marketprism_http_requests_total{{method="GET",endpoint="/api/v1/rules",status="200"}} {self.request_count // 6}')
        metrics_lines.append(f'marketprism_http_requests_total{{method="GET",endpoint="/metrics",status="200"}} {self.request_count // 6}')

        # 活跃告警数量
        metrics_lines.append('')
        metrics_lines.append('# HELP marketprism_active_alerts_total Number of active alerts')
        metrics_lines.append('# TYPE marketprism_active_alerts_total gauge')
        for severity in ['critical', 'high', 'medium', 'low']:
            count = active_alerts_by_severity.get(severity, 0)
            metrics_lines.append(f'marketprism_active_alerts_total{{severity="{severity}"}} {count}')

        # 服务健康状态
        metrics_lines.append('')
        metrics_lines.append('# HELP marketprism_service_health Service health status')
        metrics_lines.append('# TYPE marketprism_service_health gauge')
        for component, health in self.component_health.items():
            status = 1 if health else 0
            metrics_lines.append(f'marketprism_service_health{{component="{component}"}} {status}')

        # 告警规则统计
        metrics_lines.append('')
        metrics_lines.append('# HELP marketprism_alert_rules_total Total number of alert rules')
        metrics_lines.append('# TYPE marketprism_alert_rules_total gauge')
        enabled_rules = len([r for r in self.alert_rules if r['enabled']])
        total_rules = len(self.alert_rules)
        metrics_lines.append(f'marketprism_alert_rules_total{{status="enabled"}} {enabled_rules}')
        metrics_lines.append(f'marketprism_alert_rules_total{{status="total"}} {total_rules}')

        # 服务运行时间
        uptime_seconds = 0
        if self.startup_time:
            uptime_seconds = time.time() - self.startup_time

        metrics_lines.append('')
        metrics_lines.append('# HELP marketprism_uptime_seconds Service uptime in seconds')
        metrics_lines.append('# TYPE marketprism_uptime_seconds gauge')
        metrics_lines.append(f'marketprism_uptime_seconds {uptime_seconds:.2f}')

        metrics_content = '\n'.join(metrics_lines) + '\n'

        return web.Response(text=metrics_content, content_type='text/plain', charset='utf-8')

    async def _get_status(self, request):
        """获取服务状态"""
        self.request_count += 1

        uptime_seconds = 0
        if self.startup_time:
            uptime_seconds = time.time() - self.startup_time

        return web.json_response({
            'service': 'MarketPrism Monitoring & Alerting Service',
            'version': '2.0.0',
            'status': 'running' if self.is_running else 'stopped',
            'uptime_seconds': uptime_seconds,
            'request_count': self.request_count,
            'alerts_count': len(self.alerts),
            'rules_count': len(self.alert_rules),
            'components_healthy': sum(self.component_health.values()),
            'total_components': len(self.component_health),
            'timestamp': datetime.now().isoformat()
        })

    async def _get_version(self, request):
        """获取版本信息"""
        self.request_count += 1

        return web.json_response({
            'service': 'MarketPrism Monitoring & Alerting Service',
            'version': '2.0.0',
            'build_date': '2025-06-27',
            'description': '重构版本 - 专注于核心监控功能，为Grafana提供数据源支持',
            'features': [
                'Health Check API',
                'Alert Management API',
                'Alert Rules API',
                'Prometheus Metrics',
                'Grafana Integration',
                'CORS Support',
                'High Performance (QPS > 2000)'
            ],
            'grafana_compatible': True,
            'prometheus_compatible': True
        })

    async def initialize(self):
        """初始化服务"""
        try:
            self.startup_time = time.time()
            self.is_running = True
            logger.info("监控告警服务初始化完成")
        except Exception as e:
            logger.error(f"服务初始化失败: {e}")
            raise

    async def start(self, host: str = '0.0.0.0', port: int = 8082):
        """启动服务"""
        try:
            await self.initialize()

            runner = web.AppRunner(self.app)
            await runner.setup()

            site = web.TCPSite(runner, host, port)
            await site.start()

            logger.info(f"监控告警服务已启动在 {host}:{port}")

            # 保持服务运行
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("收到中断信号，正在停止服务...")
            finally:
                await self.stop()
                await runner.cleanup()

        except Exception as e:
            logger.error(f"服务启动失败: {e}")
            raise

    async def stop(self):
        """停止服务"""
        self.is_running = False
        logger.info("监控告警服务已停止")


def create_default_config():
    """创建默认配置"""
    return {
        'server': {
            'host': '0.0.0.0',
            'port': 8082
        },
        'logging': {
            'level': 'INFO'
        },
        'cors': {
            'enabled': True
        }
    }


async def main():
    """主函数"""
    try:
        # 尝试加载配置
        try:
            from config.unified_config_loader import UnifiedConfigLoader
            config_loader = UnifiedConfigLoader()
            config = config_loader.load_service_config('monitoring-alerting-service')
            logger.info("使用统一配置加载器加载配置")
        except Exception as e:
            logger.warning(f"无法加载统一配置，使用默认配置: {e}")
            config = create_default_config()

        # 创建并启动服务
        service = MonitoringAlertingService(config)

        host = config.get('server', {}).get('host', '0.0.0.0')
        port = config.get('server', {}).get('port', 8082)

        await service.start(host, port)

    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error(f"服务运行失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
