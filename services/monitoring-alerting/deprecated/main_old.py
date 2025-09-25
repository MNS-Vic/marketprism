# DEPRECATED: 请勿使用此入口。唯一入口为 services/monitoring-alerting/main.py
import sys, warnings
warnings.warn("main_old.py 已废弃，请使用 services/monitoring-alerting/main.py", DeprecationWarning)
if __name__ == "__main__":
    print("[DEPRECATED] 请运行: python services/monitoring-alerting/main.py")
    sys.exit(1)

"""
MarketPrism 监控告警服务

专注于核心监控功能，为Grafana提供数据源支持
"""

import asyncio
import signal
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from aiohttp import web
import aiohttp_cors
import json

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.unified_config_loader import UnifiedConfigLoader

logger = structlog.get_logger(__name__)


class MonitoringAlertingService:
    """智能监控告警服务"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app = web.Application()

        # 核心组件
        self.alert_manager: Optional[AlertManager] = None
        self.rule_engine: Optional[AlertRuleEngine] = None
        self.anomaly_detector: Optional[AnomalyDetector] = None
        self.failure_predictor: Optional[FailurePredictor] = None

        # 监控组件
        self.business_metrics = get_business_metrics()
        self.tracer = get_tracer()
        self.market_tracer = get_market_tracer()
        self.ux_monitor = get_ux_monitor()

        # 服务状态
        self.is_running = False
        self.startup_time = None

        logger.info("监控告警服务初始化完成")

    def _initialize_metrics(self) -> None:
        """初始化Prometheus指标"""
        try:
            from prometheus_client import Counter, Gauge, Histogram
            from core.observability.metrics.prometheus_registry import get_global_registry

            registry = get_global_registry()

            # 创建基础指标
            self.request_count = Counter(
                'marketprism_http_requests_total',
                'Total HTTP requests',
                ['method', 'endpoint', 'status'],
                registry=registry.registry
            )

            self.request_duration = Histogram(
                'marketprism_http_request_duration_seconds',
                'HTTP request duration in seconds',
                ['method', 'endpoint'],
                registry=registry.registry
            )

            self.active_alerts = Gauge(
                'marketprism_active_alerts_total',
                'Number of active alerts',
                ['severity'],
                registry=registry.registry
            )

            self.service_health = Gauge(
                'marketprism_service_health',
                'Service health status (1=healthy, 0=unhealthy)',
                ['component'],
                registry=registry.registry
            )

            # 初始化一些基础指标值
            self.active_alerts.labels(severity='critical').set(0)
            self.active_alerts.labels(severity='warning').set(0)
            self.active_alerts.labels(severity='info').set(0)

            logger.info("Prometheus指标初始化完成")

        except Exception as e:
            logger.error("指标初始化失败", error=str(e))

    async def initialize(self) -> None:
        """初始化服务组件"""
        try:
            # 初始化Prometheus指标
            self._initialize_metrics()

            # 初始化告警管理器
            self.alert_manager = get_global_alert_manager()
            await self.alert_manager.start()

            # 初始化规则引擎
            self.rule_engine = AlertRuleEngine(self.config.get('alert_rules', {}))

            # 初始化异常检测器
            anomaly_config = self.config.get('anomaly_detection', {})
            self.anomaly_detector = AnomalyDetector(anomaly_config)

            # 初始化故障预测器
            prediction_config = self.config.get('failure_prediction', {})
            self.failure_predictor = FailurePredictor(prediction_config)

            # 设置路由
            self._setup_routes()

            # 设置中间件
            self._setup_middlewares()

            logger.info("服务组件初始化完成")

        except Exception as e:
            logger.error("服务初始化失败", error=str(e))
            raise

    def _setup_routes(self) -> None:
        """设置API路由"""
        # 健康检查
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_get('/ready', self._readiness_check)

        # 告警管理API
        self.app.router.add_get('/api/v1/alerts', self._get_alerts)
        self.app.router.add_get('/api/v1/alerts/{alert_id}', self._get_alert)
        self.app.router.add_post('/api/v1/alerts/{alert_id}/acknowledge', self._acknowledge_alert)
        self.app.router.add_post('/api/v1/alerts/{alert_id}/resolve', self._resolve_alert)

        # 告警规则API
        self.app.router.add_get('/api/v1/rules', self._get_rules)
        self.app.router.add_post('/api/v1/rules', self._create_rule)
        self.app.router.add_put('/api/v1/rules/{rule_id}', self._update_rule)
        self.app.router.add_delete('/api/v1/rules/{rule_id}', self._delete_rule)

        # 监控指标API
        self.app.router.add_get('/api/v1/metrics/business', self._get_business_metrics)
        self.app.router.add_get('/api/v1/metrics/exchange/{exchange}', self._get_exchange_metrics)
        self.app.router.add_get('/api/v1/metrics/sla', self._get_sla_metrics)

        # 异常检测API
        self.app.router.add_post('/api/v1/anomaly/detect', self._detect_anomaly)
        self.app.router.add_get('/api/v1/anomaly/history', self._get_anomaly_history)

        # 故障预测API
        self.app.router.add_get('/api/v1/prediction/failures', self._predict_failures)
        self.app.router.add_get('/api/v1/prediction/capacity', self._get_capacity_planning)

        # 追踪API
        self.app.router.add_get('/api/v1/traces/{trace_id}', self._get_trace)
        self.app.router.add_get('/api/v1/traces/{trace_id}/analysis', self._analyze_trace)

        # 统计API
        self.app.router.add_get('/api/v1/stats/alerts', self._get_alert_stats)
        self.app.router.add_get('/api/v1/stats/performance', self._get_performance_stats)

        # Prometheus指标端点
        self.app.router.add_get('/metrics', self._prometheus_metrics)

    def _setup_middlewares(self) -> None:
        """设置中间件"""
        # CORS支持
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })

        # 为所有路由添加CORS
        for route in list(self.app.router.routes()):
            cors.add(route)

    async def start(self, host: str = '0.0.0.0', port: int = 8082) -> None:
        """启动服务"""
        try:
            await self.initialize()

            # 启动后台任务
            await self._start_background_tasks()

            # 启动HTTP服务器
            runner = web.AppRunner(self.app)
            await runner.setup()

            site = web.TCPSite(runner, host, port)
            await site.start()

            self.is_running = True
            self.startup_time = asyncio.get_event_loop().time()

            logger.info("监控告警服务已启动", host=host, port=port)

            # 等待停止信号
            await self._wait_for_shutdown()

        except Exception as e:
            logger.error("服务启动失败", error=str(e))
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """停止服务"""
        if not self.is_running:
            return

        self.is_running = False

        try:
            # 停止告警管理器
            if self.alert_manager:
                await self.alert_manager.stop()

            logger.info("监控告警服务已停止")

        except Exception as e:
            logger.error("服务停止失败", error=str(e))

    async def _start_background_tasks(self) -> None:
        """启动后台任务"""
        # 定期评估告警规则
        asyncio.create_task(self._rule_evaluation_loop())

        # 定期故障预测
        asyncio.create_task(self._failure_prediction_loop())

        # 定期健康检查
        asyncio.create_task(self._health_check_loop())

    async def _rule_evaluation_loop(self) -> None:
        """告警规则评估循环"""
        while self.is_running:
            try:
                # 这里可以从Prometheus或其他数据源获取指标
                # 暂时使用模拟数据
                metrics_data = await self._collect_metrics_data()

                # 评估规则
                if self.rule_engine:
                    alerts = self.rule_engine.evaluate_rules(metrics_data)

                    # 创建告警
                    for alert in alerts:
                        if self.alert_manager:
                            self.alert_manager.create_alert(
                                alert.name,
                                alert.description,
                                alert.severity,
                                alert.category,
                                alert.metadata
                            )

                await asyncio.sleep(30)  # 30秒评估一次

            except Exception as e:
                logger.error("告警规则评估失败", error=str(e))
                await asyncio.sleep(60)

    async def _failure_prediction_loop(self) -> None:
        """故障预测循环"""
        while self.is_running:
            try:
                if self.failure_predictor:
                    predictions = self.failure_predictor.predict_failures()

                    # 为预测结果创建告警
                    for prediction in predictions:
                        if self.alert_manager:
                            self.alert_manager.create_alert(
                                f"故障预测: {prediction.description}",
                                f"预计在{prediction.time_to_failure}后发生故障",
                                prediction.severity.value,
                                "capacity",
                                {
                                    'prediction_type': prediction.prediction_type.value,
                                    'confidence': prediction.confidence,
                                    'recommendations': prediction.recommendations
                                }
                            )

                await asyncio.sleep(300)  # 5分钟预测一次

            except Exception as e:
                logger.error("故障预测失败", error=str(e))
                await asyncio.sleep(600)

    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while self.is_running:
            try:
                # 检查各组件健康状态
                health_status = await self._get_component_health()

                # 记录健康状态到业务指标
                for component, is_healthy in health_status.items():
                    self.ux_monitor.record_service_availability(component, is_healthy)

                await asyncio.sleep(60)  # 1分钟检查一次

            except Exception as e:
                logger.error("健康检查失败", error=str(e))
                await asyncio.sleep(60)

    async def _collect_metrics_data(self) -> Dict[str, Any]:
        """收集指标数据"""
        # 这里应该从实际的监控系统获取数据
        # 暂时返回模拟数据
        return {
            'memory_usage_percent': {'value': 75.0, 'labels': {'instance': 'localhost'}},
            'cpu_usage_percent': {'value': 60.0, 'labels': {'instance': 'localhost'}},
            'disk_usage_percent': {'value': 85.0, 'labels': {'instance': 'localhost'}},
            'api_error_rate': {'value': 0.02, 'labels': {'service': 'api_gateway'}},
            'api_response_time_avg': {'value': 150.0, 'labels': {'service': 'api_gateway'}}
        }

    async def _get_component_health(self) -> Dict[str, bool]:
        """获取组件健康状态"""
        return {
            'alert_manager': self.alert_manager is not None and self.alert_manager.is_running,
            'rule_engine': self.rule_engine is not None,
            'anomaly_detector': self.anomaly_detector is not None,
            'failure_predictor': self.failure_predictor is not None,
            'business_metrics': self.business_metrics is not None,
            'tracer': self.tracer is not None,
            'ux_monitor': self.ux_monitor is not None
        }

    async def _wait_for_shutdown(self) -> None:
        """等待停止信号"""
        def signal_handler(signum, frame):
            logger.info("收到停止信号", signal=signum)
            self.is_running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while self.is_running:
            await asyncio.sleep(1)

    # API处理器方法
    async def _health_check(self, request: web.Request) -> web.Response:
        """健康检查端点"""
        health_status = await self._get_component_health()

        is_healthy = all(health_status.values())
        status_code = 200 if is_healthy else 503

        return web.json_response({
            'status': 'healthy' if is_healthy else 'unhealthy',
            'timestamp': asyncio.get_event_loop().time(),
            'uptime_seconds': asyncio.get_event_loop().time() - (self.startup_time or 0),
            'components': health_status
        }, status=status_code)

    async def _readiness_check(self, request: web.Request) -> web.Response:
        """就绪检查端点"""
        is_ready = (
            self.alert_manager is not None and
            self.rule_engine is not None and
            self.is_running
        )

        status_code = 200 if is_ready else 503

        return web.json_response({
            'ready': is_ready,
            'timestamp': asyncio.get_event_loop().time()
        }, status=status_code)

    async def _get_alerts(self, request: web.Request) -> web.Response:
        """获取告警列表"""
        if not self.alert_manager:
            return web.json_response({'error': 'Alert manager not available'}, status=503)

        # 获取查询参数
        severity = request.query.get('severity')
        category = request.query.get('category')

        alerts = self.alert_manager.get_active_alerts(severity, category)

        return web.json_response({
            'alerts': [alert.to_dict() for alert in alerts],
            'total': len(alerts)
        })

    async def _get_alert(self, request: web.Request) -> web.Response:
        """获取单个告警"""
        alert_id = request.match_info['alert_id']

        if not self.alert_manager:
            return web.json_response({'error': 'Alert manager not available'}, status=503)

        alert = self.alert_manager.get_alert(alert_id)
        if not alert:
            return web.json_response({'error': 'Alert not found'}, status=404)

        return web.json_response(alert.to_dict())

    async def _acknowledge_alert(self, request: web.Request) -> web.Response:
        """确认告警"""
        alert_id = request.match_info['alert_id']
        data = await request.json()
        assignee = data.get('assignee', 'unknown')

        if not self.alert_manager:
            return web.json_response({'error': 'Alert manager not available'}, status=503)

        success = self.alert_manager.acknowledge_alert(alert_id, assignee)
        if not success:
            return web.json_response({'error': 'Alert not found'}, status=404)

        return web.json_response({'status': 'acknowledged'})

    async def _resolve_alert(self, request: web.Request) -> web.Response:
        """解决告警"""
        alert_id = request.match_info['alert_id']
        data = await request.json()
        resolution_notes = data.get('resolution_notes', '')

        if not self.alert_manager:
            return web.json_response({'error': 'Alert manager not available'}, status=503)

        success = self.alert_manager.resolve_alert(alert_id, resolution_notes)
        if not success:
            return web.json_response({'error': 'Alert not found'}, status=404)

        return web.json_response({'status': 'resolved'})

    async def _get_rules(self, request: web.Request) -> web.Response:
        """获取告警规则列表"""
        if not self.rule_engine:
            return web.json_response({'error': 'Rule engine not available'}, status=503)

        category = request.query.get('category')
        enabled_only = request.query.get('enabled_only', 'false').lower() == 'true'

        rules = self.rule_engine.list_rules(category, enabled_only)

        return web.json_response({
            'rules': [
                {
                    'id': rule.id,
                    'name': rule.name,
                    'description': rule.description,
                    'severity': rule.severity.value,
                    'category': rule.category.value,
                    'enabled': rule.enabled,
                    'conditions': [
                        {
                            'metric_name': c.metric_name,
                            'operator': c.operator.value,
                            'threshold': c.threshold
                        }
                        for c in rule.conditions
                    ]
                }
                for rule in rules
            ],
            'total': len(rules)
        })

    async def _create_rule(self, request: web.Request) -> web.Response:
        """创建告警规则"""
        # 实现创建规则逻辑
        return web.json_response({'error': 'Not implemented'}, status=501)

    async def _update_rule(self, request: web.Request) -> web.Response:
        """更新告警规则"""
        # 实现更新规则逻辑
        return web.json_response({'error': 'Not implemented'}, status=501)

    async def _delete_rule(self, request: web.Request) -> web.Response:
        """删除告警规则"""
        rule_id = request.match_info['rule_id']

        if not self.rule_engine:
            return web.json_response({'error': 'Rule engine not available'}, status=503)

        success = self.rule_engine.remove_rule(rule_id)
        if not success:
            return web.json_response({'error': 'Rule not found'}, status=404)

        return web.json_response({'status': 'deleted'})

    async def _get_business_metrics(self, request: web.Request) -> web.Response:
        """获取业务指标"""
        metrics_summary = self.business_metrics.get_metrics_summary()
        return web.json_response(metrics_summary)

    async def _get_exchange_metrics(self, request: web.Request) -> web.Response:
        """获取交易所指标"""
        exchange = request.match_info['exchange']

        exchange_health = self.business_metrics.get_exchange_health(exchange)
        if not exchange_health:
            return web.json_response({'error': 'Exchange not found'}, status=404)

        return web.json_response({
            'exchange': exchange,
            'health_score': exchange_health.get_health_score(),
            'connection_status': exchange_health.connection_status,
            'message_count': exchange_health.message_count,
            'error_count': exchange_health.error_count,
            'latency_ms': exchange_health.latency_ms,
            'data_quality_score': exchange_health.data_quality_score,
            'last_message_time': exchange_health.last_message_time.isoformat() if exchange_health.last_message_time else None
        })

    async def _get_sla_metrics(self, request: web.Request) -> web.Response:
        """获取SLA指标"""
        sla_status = self.ux_monitor.get_sla_status()
        return web.json_response(sla_status)

    async def _detect_anomaly(self, request: web.Request) -> web.Response:
        """检测异常"""
        data = await request.json()
        metric_name = data.get('metric_name')
        value = data.get('value')
        timestamp_str = data.get('timestamp')

        if not all([metric_name, value is not None]):
            return web.json_response({'error': 'Missing required fields'}, status=400)

        from datetime import datetime, timezone
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(timezone.utc)

        if self.anomaly_detector:
            result = self.anomaly_detector.detect_anomaly(metric_name, timestamp, float(value))
            if result:
                return web.json_response(result.to_dict())

        return web.json_response({'is_anomaly': False})

    async def _get_anomaly_history(self, request: web.Request) -> web.Response:
        """获取异常历史"""
        # 实现异常历史查询
        return web.json_response({'error': 'Not implemented'}, status=501)

    async def _predict_failures(self, request: web.Request) -> web.Response:
        """预测故障"""
        if not self.failure_predictor:
            return web.json_response({'error': 'Failure predictor not available'}, status=503)

        predictions = self.failure_predictor.predict_failures()

        return web.json_response({
            'predictions': [pred.to_dict() for pred in predictions],
            'total': len(predictions)
        })

    async def _get_capacity_planning(self, request: web.Request) -> web.Response:
        """获取容量规划建议"""
        if not self.failure_predictor:
            return web.json_response({'error': 'Failure predictor not available'}, status=503)

        recommendations = self.failure_predictor.get_capacity_planning_recommendations()

        return web.json_response({
            'recommendations': recommendations,
            'total': len(recommendations)
        })

    async def _get_trace(self, request: web.Request) -> web.Response:
        """获取追踪信息"""
        trace_id = request.match_info['trace_id']

        trace_spans = self.tracer.get_trace(trace_id)
        if not trace_spans:
            return web.json_response({'error': 'Trace not found'}, status=404)

        return web.json_response({
            'trace_id': trace_id,
            'spans': [span.to_dict() for span in trace_spans],
            'span_count': len(trace_spans)
        })

    async def _analyze_trace(self, request: web.Request) -> web.Response:
        """分析追踪性能"""
        trace_id = request.match_info['trace_id']

        analysis = self.tracer.analyze_trace_performance(trace_id)
        if not analysis:
            return web.json_response({'error': 'Trace not found'}, status=404)

        return web.json_response(analysis)

    async def _get_alert_stats(self, request: web.Request) -> web.Response:
        """获取告警统计"""
        if not self.alert_manager:
            return web.json_response({'error': 'Alert manager not available'}, status=503)

        stats = self.alert_manager.get_stats()

        if self.rule_engine:
            rule_stats = self.rule_engine.get_rule_statistics()
            stats.update(rule_stats)

        return web.json_response(stats)

    async def _get_performance_stats(self, request: web.Request) -> web.Response:
        """获取性能统计"""
        performance_summary = self.ux_monitor.get_performance_summary()
        return web.json_response(performance_summary)

    async def _prometheus_metrics(self, request: web.Request) -> web.Response:
        """Prometheus指标端点"""
        try:
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            from core.observability.metrics.prometheus_registry import get_global_registry

            # 使用全局注册表
            global_registry = get_global_registry()
            if global_registry.registry:
                metrics_data = generate_latest(global_registry.registry)
            else:
                metrics_data = generate_latest()

            # 修复content_type问题 - 移除charset部分
            content_type = CONTENT_TYPE_LATEST.split(';')[0]
            return web.Response(body=metrics_data, content_type=content_type)
        except ImportError:
            return web.json_response({'error': 'Prometheus client not available'}, status=503)


async def main():
    """主函数"""
    # 加载配置
    config_loader = UnifiedConfigLoader()
    config = config_loader.load_service_config('monitoring-alerting-service')

    # 创建并启动服务
    service = MonitoringAlertingService(config)

    # 从配置获取端口
    port = config.get('server', {}).get('port', 8082)
    host = config.get('server', {}).get('host', '0.0.0.0')

    await service.start(host, port)


if __name__ == '__main__':
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

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error("服务运行失败", error=str(e))
        sys.exit(1)
