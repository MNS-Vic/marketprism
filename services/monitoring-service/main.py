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
from datetime import datetime, timedelta
import aiohttp
from aiohttp import web
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import psutil
import yaml

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入微服务框架
from core.service_framework import BaseService


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
        current_time = datetime.utcnow()
        
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
            stats['last_check_time'] = datetime.utcnow().isoformat()
            
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
    """
    监控服务
    
    提供全面的系统监控功能：
    - Prometheus指标收集和暴露
    - 服务健康监控
    - 告警管理和通知
    - 系统性能监控
    - 监控数据聚合和分析
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            service_name="monitoring-service",
            service_version="1.0.0",
            service_port=config.get('port', 8083),
            config=config
        )
        
        self.logger = structlog.get_logger(__name__)
        
        # 核心组件
        self.prometheus_manager = PrometheusManager()
        self.alert_manager = AlertManager(config.get('alerting', {}))
        
        # 服务监控器
        services_config = config.get('monitored_services', {})
        self.service_monitor = ServiceMonitor(services_config)
        
        # 配置
        self.check_interval = config.get('check_interval', 30)
        self.enable_alerts = config.get('enable_alerts', True)
        self.prometheus_port = config.get('prometheus_port', 9090)
        
        # 状态
        self.monitoring_stats = {
            'start_time': datetime.utcnow(),
            'total_checks': 0,
            'failed_checks': 0,
            'alerts_triggered': 0,
            'alerts_resolved': 0
        }
        
        self.logger.info("Monitoring Service 初始化完成")
    
    async def initialize_service(self) -> bool:
        """初始化监控服务"""
        try:
            # 启动监控循环
            asyncio.create_task(self._monitoring_loop())
            
            # 启动告警检查循环
            if self.enable_alerts:
                asyncio.create_task(self._alert_check_loop())
            
            self.logger.info("Monitoring Service 初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"Monitoring Service 初始化失败: {e}")
            return False
    
    async def start_service(self) -> bool:
        """启动监控服务"""
        try:
            self.logger.info("Monitoring Service 启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动Monitoring Service失败: {e}")
            return False
    
    async def stop_service(self) -> bool:
        """停止监控服务"""
        try:
            self.logger.info("Monitoring Service 已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"停止Monitoring Service失败: {e}")
            return False
    
    async def _monitoring_loop(self):
        """主监控循环"""
        while True:
            try:
                self.monitoring_stats['total_checks'] += 1
                
                # 更新系统指标
                self.prometheus_manager.update_system_metrics()
                
                # 检查服务健康状态
                health_results = await self.service_monitor.check_services_health()
                
                # 更新服务状态指标
                for service_name, result in health_results.items():
                    is_healthy = result['status'] == 'healthy'
                    self.prometheus_manager.update_service_status(service_name, is_healthy)
                    
                    if 'response_time' in result:
                        self.prometheus_manager.record_service_request(
                            service_name, 'GET', 200 if is_healthy else 503, 
                            result['response_time'], '/health'
                        )
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                self.monitoring_stats['failed_checks'] += 1
                self.logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(5)
    
    async def _alert_check_loop(self):
        """告警检查循环"""
        while True:
            try:
                # 收集当前指标
                metrics = {
                    'cpu_usage': psutil.cpu_percent(),
                    'memory_usage': psutil.virtual_memory().percent,
                    'service_status': 1,  # 简化，实际需要从服务监控获取
                    'avg_response_time': 0.1,  # 简化，实际需要计算平均值
                    'error_rate': 0.01  # 简化，实际需要从错误统计计算
                }
                
                # 检查告警
                self.alert_manager.check_alerts(metrics)
                
                await asyncio.sleep(60)  # 每分钟检查一次告警
                
            except Exception as e:
                self.logger.error(f"告警检查错误: {e}")
                await asyncio.sleep(10)
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """获取系统概览"""
        try:
            # 系统资源
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk_usage = psutil.disk_usage('/')
            
            # 服务状态
            service_health = await self.service_monitor.check_services_health()
            healthy_services = sum(1 for s in service_health.values() if s['status'] == 'healthy')
            total_services = len(service_health)
            
            # 告警状态
            active_alerts = self.alert_manager.get_active_alerts()
            critical_alerts = sum(1 for a in active_alerts if a['severity'] == 'critical')
            
            overview = {
                'timestamp': datetime.utcnow().isoformat(),
                'uptime_seconds': (datetime.utcnow() - self.monitoring_stats['start_time']).total_seconds(),
                'system_resources': {
                    'cpu_usage_percent': cpu_percent,
                    'memory_usage_percent': memory.percent,
                    'memory_available_gb': memory.available / (1024**3),
                    'disk_usage_percent': (disk_usage.used / disk_usage.total) * 100,
                    'disk_free_gb': disk_usage.free / (1024**3)
                },
                'services': {
                    'total': total_services,
                    'healthy': healthy_services,
                    'unhealthy': total_services - healthy_services,
                    'health_percentage': (healthy_services / total_services * 100) if total_services > 0 else 0
                },
                'alerts': {
                    'active': len(active_alerts),
                    'critical': critical_alerts,
                    'warning': len(active_alerts) - critical_alerts
                },
                'monitoring_stats': self.monitoring_stats
            }
            
            return overview
            
        except Exception as e:
            self.logger.error(f"获取系统概览失败: {e}")
            return {'error': str(e)}
    
    async def get_service_details(self, service_name: str) -> Dict[str, Any]:
        """获取服务详细信息"""
        try:
            service_stats = self.service_monitor.get_service_stats()
            
            if service_name not in service_stats:
                return {'error': f'Service {service_name} not found'}
            
            # 获取当前健康状态
            health_results = await self.service_monitor.check_services_health()
            current_health = health_results.get(service_name, {'status': 'unknown'})
            
            details = {
                'service_name': service_name,
                'current_status': current_health,
                'statistics': service_stats[service_name],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            return details
            
        except Exception as e:
            return {'error': str(e)}


async def main():
    """主函数"""
    try:
        # 加载配置
        import yaml
        config_path = project_root / "config" / "services.yaml"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                services_config = yaml.safe_load(f)
            config = services_config.get('monitoring-service', {})
        else:
            # 默认配置
            config = {
                'port': 8083,
                'check_interval': 30,
                'enable_alerts': True,
                'prometheus_port': 9090,
                'monitored_services': {
                    'market-data-collector': {'host': 'localhost', 'port': 8081},
                    'api-gateway-service': {'host': 'localhost', 'port': 8080},
                    'data-storage-service': {'host': 'localhost', 'port': 8082},
                    'scheduler-service': {'host': 'localhost', 'port': 8084}
                }
            }
        
        # 创建并启动服务
        service = MonitoringService(config)
        
        # 注册API路由
        @service.app.get("/api/v1/overview")
        async def get_overview(request):
            from aiohttp import web
            overview = await service.get_system_overview()
            return web.json_response(overview)
        
        @service.app.get("/api/v1/services")
        async def get_services(request):
            from aiohttp import web
            health_results = await service.service_monitor.check_services_health()
            service_stats = service.service_monitor.get_service_stats()
            
            return web.json_response({
                'health_status': health_results,
                'statistics': service_stats
            })
        
        @service.app.get("/api/v1/services/{service_name}")
        async def get_service_details(request):
            from aiohttp import web
            service_name = request.match_info['service_name']
            details = await service.get_service_details(service_name)
            return web.json_response(details)
        
        @service.app.get("/api/v1/alerts")
        async def get_alerts(request):
            from aiohttp import web
            active_alerts = service.alert_manager.get_active_alerts()
            alert_history = service.alert_manager.get_alert_history()
            
            return web.json_response({
                'active_alerts': active_alerts,
                'alert_history': alert_history
            })
        
        @service.app.get("/metrics")
        async def get_prometheus_metrics(request):
            from aiohttp import web
            metrics_text = service.prometheus_manager.generate_metrics()
            return web.Response(text=metrics_text, content_type='text/plain')
        
        # 启动服务
        await service.run()
        
    except KeyboardInterrupt:
        print("服务被用户中断")
    except Exception as e:
        print(f"服务启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())