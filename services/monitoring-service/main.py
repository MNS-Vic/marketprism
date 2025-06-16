"""
Monitoring Service - Phase 3
综合监控服务，负责系统监控、指标收集、告警管理

这是MarketPrism微服务架构的监控中心，提供：
1. Prometheus指标收集和存储
2. Grafana仪表板管理
3. 告警规则配置和通知
4. 系统健康监控
5. 性能指标分析
6. 日志聚合和分析
7. 服务状态跟踪
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
from aiohttp import web
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import psutil
import yaml
import traceback
import logging
import signal

# 确保能正确找到项目根目录并添加到sys.path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入微服务框架
from core.service_framework import BaseService, get_service_registry


class PrometheusManager:
    """Prometheus指标管理器"""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        
        # 系统指标
        self.system_cpu_usage = Gauge(
            'system_cpu_usage_percent', 
            'System CPU usage percentage',
            registry=self.registry
        )
        self.system_memory_usage = Gauge(
            'system_memory_usage_percent',
            'System memory usage percentage', 
            registry=self.registry
        )
        self.system_disk_usage = Gauge(
            'system_disk_usage_percent',
            'System disk usage percentage',
            ['mountpoint'],
            registry=self.registry
        )
        
        # 服务指标
        self.service_status = Gauge(
            'service_status',
            'Service health status (1=healthy, 0=unhealthy)',
            ['service_name'],
            registry=self.registry
        )
        self.service_response_time = Histogram(
            'service_response_time_seconds',
            'Service response time in seconds',
            ['service_name', 'endpoint'],
            registry=self.registry
        )
        self.service_requests_total = Counter(
            'service_requests_total',
            'Total service requests',
            ['service_name', 'method', 'status'],
            registry=self.registry
        )
        
        # 数据处理指标
        self.data_processed_total = Counter(
            'data_processed_total',
            'Total data processed',
            ['service_name', 'data_type'],
            registry=self.registry
        )
        self.data_processing_errors = Counter(
            'data_processing_errors_total',
            'Total data processing errors',
            ['service_name', 'error_type'],
            registry=self.registry
        )
        
        # 自定义业务指标
        self.active_connections = Gauge(
            'active_connections',
            'Number of active connections',
            ['service_name', 'connection_type'],
            registry=self.registry
        )
        self.message_queue_size = Gauge(
            'message_queue_size',
            'Message queue size',
            ['queue_name'],
            registry=self.registry
        )
    
    def update_system_metrics(self):
        """更新系统指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            self.system_cpu_usage.set(cpu_percent)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            self.system_memory_usage.set(memory.percent)
            
            # 磁盘使用率
            for partition in psutil.disk_partitions():
                try:
                    disk_usage = psutil.disk_usage(partition.mountpoint)
                    usage_percent = (disk_usage.used / disk_usage.total) * 100
                    self.system_disk_usage.labels(mountpoint=partition.mountpoint).set(usage_percent)
                except PermissionError:
                    # 某些分区可能没有权限访问
                    pass
        except Exception as e:
            print(f"更新系统指标失败: {e}")
    
    def update_service_status(self, service_name: str, is_healthy: bool):
        """更新服务状态"""
        self.service_status.labels(service_name=service_name).set(1 if is_healthy else 0)
    
    def record_service_request(self, service_name: str, method: str, status: int, response_time: float, endpoint: str = ""):
        """记录服务请求"""
        self.service_requests_total.labels(
            service_name=service_name,
            method=method,
            status=str(status)
        ).inc()
        
        self.service_response_time.labels(
            service_name=service_name,
            endpoint=endpoint
        ).observe(response_time)
    
    def generate_metrics(self) -> str:
        """生成Prometheus指标文本"""
        return prometheus_client.generate_latest(self.registry).decode('utf-8')


class AlertManager:
    """告警管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.alert_rules = {}
        self.active_alerts = {}
        self.alert_history = []
        self.logger = structlog.get_logger(__name__)
        
        # 加载默认告警规则
        self._load_default_alert_rules()
    
    def _load_default_alert_rules(self):
        """加载默认告警规则"""
        self.alert_rules = {
            'high_cpu_usage': {
                'name': 'High CPU Usage',
                'description': 'CPU usage is too high',
                'condition': 'cpu_usage > 90',
                'threshold': 90,
                'duration': 300,  # 5分钟
                'severity': 'warning'
            },
            'high_memory_usage': {
                'name': 'High Memory Usage', 
                'description': 'Memory usage is too high',
                'condition': 'memory_usage > 95',
                'threshold': 95,
                'duration': 300,
                'severity': 'critical'
            },
            'service_down': {
                'name': 'Service Down',
                'description': 'Service is not responding',
                'condition': 'service_status == 0',
                'threshold': 0,
                'duration': 60,
                'severity': 'critical'
            },
            'high_response_time': {
                'name': 'High Response Time',
                'description': 'Service response time is too high',
                'condition': 'response_time > 5',
                'threshold': 5,
                'duration': 180,
                'severity': 'warning'
            },
            'data_processing_errors': {
                'name': 'Data Processing Errors',
                'description': 'Too many data processing errors',
                'condition': 'error_rate > 0.1',
                'threshold': 0.1,
                'duration': 300,
                'severity': 'warning'
            }
        }
    
    def check_alerts(self, metrics: Dict[str, float]):
        """检查告警条件"""
        current_time = datetime.now(timezone.utc)
        
        for rule_id, rule in self.alert_rules.items():
            try:
                # 简单的条件检查（实际实现可能需要更复杂的表达式解析）
                alert_triggered = self._evaluate_condition(rule, metrics)
                
                if alert_triggered:
                    if rule_id not in self.active_alerts:
                        # 新告警
                        alert = {
                            'rule_id': rule_id,
                            'rule_name': rule['name'],
                            'description': rule['description'],
                            'severity': rule['severity'],
                            'start_time': current_time,
                            'last_checked': current_time,
                            'value': metrics.get(self._get_metric_key(rule), 0)
                        }
                        self.active_alerts[rule_id] = alert
                        self._send_alert_notification(alert)
                        
                    else:
                        # 更新现有告警
                        self.active_alerts[rule_id]['last_checked'] = current_time
                        self.active_alerts[rule_id]['value'] = metrics.get(self._get_metric_key(rule), 0)
                
                else:
                    if rule_id in self.active_alerts:
                        # 告警恢复
                        alert = self.active_alerts[rule_id]
                        alert['end_time'] = current_time
                        alert['status'] = 'resolved'
                        
                        self.alert_history.append(alert.copy())
                        del self.active_alerts[rule_id]
                        
                        self._send_recovery_notification(alert)
                        
            except Exception as e:
                self.logger.error(f"检查告警规则失败 {rule_id}: {e}")
    
    def _evaluate_condition(self, rule: Dict[str, Any], metrics: Dict[str, float]) -> bool:
        """评估告警条件"""
        condition = rule['condition']
        threshold = rule['threshold']
        
        # 简化的条件评估，实际实现可能需要更复杂的逻辑
        if 'cpu_usage' in condition:
            return metrics.get('cpu_usage', 0) > threshold
        elif 'memory_usage' in condition:
            return metrics.get('memory_usage', 0) > threshold
        elif 'service_status' in condition:
            return metrics.get('service_status', 1) == threshold
        elif 'response_time' in condition:
            return metrics.get('avg_response_time', 0) > threshold
        elif 'error_rate' in condition:
            return metrics.get('error_rate', 0) > threshold
        
        return False
    
    def _get_metric_key(self, rule: Dict[str, Any]) -> str:
        """获取指标键名"""
        condition = rule['condition']
        if 'cpu_usage' in condition:
            return 'cpu_usage'
        elif 'memory_usage' in condition:
            return 'memory_usage'
        elif 'service_status' in condition:
            return 'service_status'
        elif 'response_time' in condition:
            return 'avg_response_time'
        elif 'error_rate' in condition:
            return 'error_rate'
        return 'unknown'
    
    def _send_alert_notification(self, alert: Dict[str, Any]):
        """发送告警通知"""
        self.logger.warning(
            "告警触发",
            alert_id=alert['rule_id'],
            alert_name=alert['rule_name'],
            severity=alert['severity'],
            description=alert['description'],
            value=alert['value']
        )
        
        # 这里可以集成更多通知方式：邮件、短信、Slack等
        
    def _send_recovery_notification(self, alert: Dict[str, Any]):
        """发送恢复通知"""
        self.logger.info(
            "告警恢复",
            alert_id=alert['rule_id'],
            alert_name=alert['rule_name'],
            duration=(alert['end_time'] - alert['start_time']).total_seconds()
        )
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """获取活跃告警"""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警历史"""
        return self.alert_history[-limit:]


class ServiceMonitor:
    """服务监控器"""
    
    def __init__(self, services_config: Dict[str, Dict[str, Any]]):
        self.services_config = services_config
        self.service_stats = {}
        self.logger = structlog.get_logger(__name__)
    
    async def check_services_health(self) -> Dict[str, Dict[str, Any]]:
        """检查所有服务健康状态"""
        health_results = {}
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            for service_name, service_config in self.services_config.items():
                try:
                    base_url = f"http://{service_config.get('host', 'localhost')}:{service_config['port']}"
                    health_endpoint = service_config.get('health_endpoint', '/health')
                    
                    start_time = time.time()
                    async with session.get(f"{base_url}{health_endpoint}") as response:
                        response_time = time.time() - start_time
                        
                        if response.status == 200:
                            health_data = await response.json()
                            health_results[service_name] = {
                                'status': 'healthy',
                                'response_time': response_time,
                                'details': health_data
                            }
                        else:
                            health_results[service_name] = {
                                'status': 'unhealthy',
                                'response_time': response_time,
                                'error': f'HTTP {response.status}'
                            }
                
                except Exception as e:
                    health_results[service_name] = {
                        'status': 'unreachable',
                        'error': str(e)
                    }
        
        # 更新服务统计
        self._update_service_stats(health_results)
        
        return health_results
    
    def _update_service_stats(self, health_results: Dict[str, Dict[str, Any]]):
        """更新服务统计"""
        for service_name, result in health_results.items():
            if service_name not in self.service_stats:
                self.service_stats[service_name] = {
                    'total_checks': 0,
                    'healthy_checks': 0,
                    'unhealthy_checks': 0,
                    'unreachable_checks': 0,
                    'avg_response_time': 0,
                    'last_check_time': None,
                    'uptime_percentage': 0
                }
            
            stats = self.service_stats[service_name]
            stats['total_checks'] += 1
            stats['last_check_time'] = datetime.now(timezone.utc).isoformat()
            
            if result['status'] == 'healthy':
                stats['healthy_checks'] += 1
                if 'response_time' in result:
                    # 计算平均响应时间
                    current_avg = stats['avg_response_time']
                    new_avg = (current_avg * (stats['healthy_checks'] - 1) + result['response_time']) / stats['healthy_checks']
                    stats['avg_response_time'] = new_avg
            elif result['status'] == 'unhealthy':
                stats['unhealthy_checks'] += 1
            else:
                stats['unreachable_checks'] += 1
            
            # 计算正常运行时间百分比
            stats['uptime_percentage'] = (stats['healthy_checks'] / stats['total_checks']) * 100
    
    def get_service_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取服务统计"""
        return self.service_stats.copy()


class MonitoringService(BaseService):
    """监控微服务，提供Prometheus指标聚合和健康检查端点"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("monitoring-service", config)
        # 本服务自己的核心指标
        self.internal_metrics = {
            'scrapes_total': prometheus_client.Counter(
                'monitoring_service_scrapes_total',
                'Total number of scrapes handled by the monitoring service'
            ),
            'scrape_errors_total': prometheus_client.Counter(
                'monitoring_service_scrape_errors_total',
                'Total number of scrape errors'
            )
        }
        
        self.prometheus_manager = PrometheusManager()
        self.alert_manager = AlertManager(config.get('alerts', {}))
        
        # 从配置中获取服务列表
        services_config = config.get('monitored_services', {})
        self.service_monitor = ServiceMonitor(services_config)
        
        self.monitoring_task = None
        self.alert_task = None
        self.is_running = False

    def setup_routes(self):
        """设置API路由"""
        # 添加标准状态API路由
        self.app.router.add_get('/api/v1/monitoring/status', self.get_overview_handler)
        
        self.app.router.add_get('/api/v1/monitoring/metrics', self.handle_metrics_request)
        self.app.router.add_get('/api/v1/monitoring/targets', self.get_targets)
        
        # Phase 3 测试需要的路由
        self.app.router.add_get('/api/v1/overview', self.get_overview_handler)
        self.app.router.add_get('/api/v1/services', self.get_services_handler)
        self.app.router.add_get('/api/v1/services/{service_name}', self.get_service_details_handler)
        self.app.router.add_get('/api/v1/alerts', self.get_alerts_handler)
        
        # 使用我们自己的PrometheusManager的/metrics端点（会覆盖基础服务的）
        self.app.router.add_get('/metrics', self.get_prometheus_metrics_handler)

    async def on_startup(self):
        self.logger.info("Monitoring service initialized successfully.")
        # 启动监控和告警循环
        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.alert_task = asyncio.create_task(self._alert_check_loop())

    async def on_shutdown(self):
        self.logger.info("Monitoring service shutting down...")
        self.is_running = False
        
        # 停止监控任务
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self.alert_task:
            self.alert_task.cancel()
            try:
                await self.alert_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Monitoring service shutdown completed.")

    async def handle_metrics_request(self, request: web.Request) -> web.Response:
        """处理Prometheus的抓取请求，返回所有聚合的指标"""
        self.internal_metrics['scrapes_total'].inc()
        # 在真实实现中，这里会聚合来自所有其他服务的指标
        # 目前，我们只返回prometheus_client库的默认指标和本服务的指标
        return web.Response(
            body=prometheus_client.generate_latest(),
            content_type='text/plain; version=0.0.4'
        )

    async def get_targets(self, request: web.Request) -> web.Response:
        """返回当前配置的监控目标"""
        # 这里的目标可以从配置或服务发现中动态获取
        targets = self.config.get("scrape_configs", [])
        return web.json_response(targets)

    async def _monitoring_loop(self):
        """主监控循环"""
        while self.is_running:
            try:
                # 更新系统指标
                self.prometheus_manager.update_system_metrics()
                
                # 检查服务健康度
                health_results = await self.service_monitor.check_services_health()
                
                # 更新Prometheus中的服务状态
                for service_name, result in health_results.items():
                    self.prometheus_manager.update_service_status(service_name, result['status'] == 'healthy')
                
            except Exception as e:
                self.logger.error(f"监控循环异常: {e}")
            
            await asyncio.sleep(self.config.get('monitoring_interval', 15))

    async def _alert_check_loop(self):
        """告警检查循环"""
        while self.is_running:
            try:
                # 获取最新的服务统计信息
                service_stats = self.service_monitor.get_service_stats()
                
                # 准备用于告警检查的指标字典
                metrics_for_alerts = {
                    'cpu_usage': psutil.cpu_percent(),
                    'memory_usage': psutil.virtual_memory().percent
                    # ... 可以添加更多指标
                }
                
                # 检查告警
                self.alert_manager.check_alerts(metrics_for_alerts)
                
            except Exception as e:
                self.logger.error(f"告警检查循环异常: {e}")
            
            await asyncio.sleep(self.config.get('alert_check_interval', 60))

    async def get_system_overview(self) -> Dict[str, Any]:
        """获取系统概览"""
        try:
            # 获取系统资源信息
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # 获取服务状态信息
            health_results = await self.service_monitor.check_services_health()
            total_services = len(health_results)
            healthy_services = sum(1 for result in health_results.values() if result['status'] == 'healthy')
            
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'system_resources': {
                    'cpu_usage_percent': cpu_usage,
                    'memory_usage_percent': memory.percent,
                    'disk_usage_percent': (disk.used / disk.total) * 100,
                    'memory_total_gb': memory.total / (1024**3),
                    'memory_available_gb': memory.available / (1024**3),
                    'disk_total_gb': disk.total / (1024**3),
                    'disk_free_gb': disk.free / (1024**3)
                },
                'services': {
                    'total': total_services,
                    'healthy': healthy_services,
                    'unhealthy': total_services - healthy_services,
                    'health_percentage': (healthy_services / total_services * 100) if total_services > 0 else 0
                },
                'monitoring_stats': {
                    'monitored_services': list(health_results.keys()),
                    'last_check_time': datetime.now(timezone.utc).isoformat(),
                    'alert_count': len(self.alert_manager.get_active_alerts())
                }
            }
        except Exception as e:
            self.logger.error(f"获取系统概览失败: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

    async def get_service_details(self, service_name: str) -> Dict[str, Any]:
        """获取服务详情"""
        try:
            # 获取服务健康状态
            health_results = await self.service_monitor.check_services_health()
            service_stats = self.service_monitor.get_service_stats()
            
            if service_name not in health_results:
                return {
                    'error': f'Service {service_name} not found',
                    'available_services': list(health_results.keys())
                }
            
            health_info = health_results[service_name]
            stats_info = service_stats.get(service_name, {})
            
            return {
                'service_name': service_name,
                'current_status': {
                    'status': health_info['status'],
                    'response_time': health_info.get('response_time', 0),
                    'last_check': health_info.get('timestamp', ''),
                    'details': health_info.get('details', {})
                },
                'statistics': {
                    'uptime': stats_info.get('uptime', 0),
                    'total_checks': stats_info.get('total_checks', 0),
                    'healthy_checks': stats_info.get('healthy_checks', 0),
                    'unhealthy_checks': stats_info.get('unhealthy_checks', 0),
                    'unreachable_checks': stats_info.get('unreachable_checks', 0),
                    'uptime_percentage': (
                        stats_info.get('healthy_checks', 0) / max(stats_info.get('total_checks', 1), 1) * 100
                    ) if stats_info.get('total_checks', 0) > 0 else 0
                }
            }
            
        except Exception as e:
            self.logger.error(f"获取服务详情失败 {service_name}: {e}")
            return {
                'service_name': service_name,
                'error': str(e),
                'health_status': 'unknown'
            }

    # --- Route Handlers ---
    async def get_overview_handler(self, request: web.Request) -> web.Response:
        overview = await self.get_system_overview()
        return web.json_response(overview)

    async def get_services_handler(self, request: web.Request) -> web.Response:
        # 获取服务健康状态
        health_results = await self.service_monitor.check_services_health()
        service_stats = self.service_monitor.get_service_stats()
        
        # 转换为测试期望的格式
        health_status = {}
        for service_name, result in health_results.items():
            health_status[service_name] = {
                'status': result['status'],
                'response_time': result.get('response_time', 0)
            }
        
        response_data = {
            'health_status': health_status,
            'statistics': service_stats
        }
        
        return web.json_response(response_data)

    async def get_service_details_handler(self, request: web.Request) -> web.Response:
        service_name = request.match_info['service_name']
        details = await self.get_service_details(service_name)
        return web.json_response(details)

    async def get_alerts_handler(self, request: web.Request) -> web.Response:
        try:
            active_alerts = self.alert_manager.get_active_alerts()
            history = self.alert_manager.get_alert_history()
            
            # 转换datetime对象为字符串
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return obj
            
            # 序列化活跃告警
            serialized_active = []
            for alert in active_alerts:
                serialized_alert = {}
                for key, value in alert.items():
                    serialized_alert[key] = serialize_datetime(value)
                serialized_active.append(serialized_alert)
            
            # 序列化历史告警
            serialized_history = []
            for alert in history:
                serialized_alert = {}
                for key, value in alert.items():
                    serialized_alert[key] = serialize_datetime(value)
                serialized_history.append(serialized_alert)
            
            response_data = {
                'active_alerts': serialized_active, 
                'alert_history': serialized_history
            }
            
            return web.json_response(response_data)
            
        except Exception as e:
            self.logger.error(f"获取告警信息失败: {e}")
            return web.json_response({
                'active_alerts': [], 
                'alert_history': [],
                'error': str(e)
            }, status=500)

    async def _metrics_endpoint(self, request: web.Request) -> web.Response:
        """重写基础服务的指标端点，使用监控服务的PrometheusManager"""
        try:
            # 更新系统指标
            self.prometheus_manager.update_system_metrics()
            
            # 获取服务健康状态并更新指标
            health_results = await self.service_monitor.check_services_health()
            for service_name, result in health_results.items():
                self.prometheus_manager.update_service_status(service_name, result['status'] == 'healthy')
            
            # 生成指标
            metrics = self.prometheus_manager.generate_metrics()
            
            # 添加调试信息
            debug_info = f"# DEBUG: PrometheusManager metrics generated at {datetime.now(timezone.utc).isoformat()}\n"
            debug_info += f"# DEBUG: System metrics updated\n"
            debug_info += f"# DEBUG: Service health checked for {len(health_results)} services\n"
            
            return web.Response(text=debug_info + metrics, content_type='text/plain')
            
        except Exception as e:
            self.logger.error(f"生成Prometheus指标失败: {e}")
            return web.Response(text=f"# Error generating metrics: {e}", content_type='text/plain')

    async def get_prometheus_metrics_handler(self, request: web.Request) -> web.Response:
        """别名方法，调用重写的_metrics_endpoint"""
        return await self._metrics_endpoint(request)


async def main():
    """服务主入口点"""
    try:
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / 'config' / 'services.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f) or {}
            
        service_config = full_config.get('services', {}).get('monitoring-service', {})
        
        service = MonitoringService(config=service_config)
        await service.run()

    except Exception:
        logging.basicConfig()
        logging.critical("Monitoring Service failed to start", exc_info=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())