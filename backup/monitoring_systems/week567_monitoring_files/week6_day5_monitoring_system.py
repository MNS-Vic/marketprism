#!/usr/bin/env python3
"""
📊 Week 6 Day 5: API Gateway Monitoring System
企业级API网关监控和可观测性系统

实现的核心组件:
1. MetricsCollector (指标收集器)
2. RealTimeMonitoringEngine (实时监控引擎)  
3. LogAggregator (日志聚合器)
4. PerformanceAnalyzer (性能分析器)
5. HealthCheckManager (健康检查管理器)
6. ObservabilityPlatform (可观测性平台)
"""

import asyncio
import time
import json
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from collections import defaultdict, deque
import uuid

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 尝试导入psutil，如果失败则使用模拟数据
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    logger.warning("psutil not available, using mock data")
    PSUTIL_AVAILABLE = False

# ===== 数据模型定义 =====

class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"

class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class Metric:
    """指标数据"""
    name: str
    value: float
    type: MetricType
    labels: Dict[str, str]
    timestamp: datetime
    unit: str = ""

@dataclass
class LogEntry:
    """日志条目"""
    timestamp: datetime
    level: str
    message: str
    source: str
    labels: Dict[str, str]
    trace_id: Optional[str] = None

@dataclass
class Alert:
    """告警信息"""
    id: str
    name: str
    level: AlertLevel
    message: str
    timestamp: datetime
    labels: Dict[str, str]
    resolved: bool = False

# ===== 1. MetricsCollector (指标收集器) =====

class MetricsCollector:
    """指标收集器 - 收集各类系统和业务指标"""
    
    def __init__(self):
        self.metrics_storage: Dict[str, List[Metric]] = defaultdict(list)
        self.collectors: List[Callable] = []
        self.running = False
        self.collection_interval = 5.0  # 5秒收集一次
        self._collection_task = None
        
    async def start(self):
        """启动指标收集"""
        self.running = True
        logger.info("📊 MetricsCollector started")
        
        # 注册默认收集器
        self.register_collector(self._collect_api_metrics)
        self.register_collector(self._collect_gateway_metrics)
        self.register_collector(self._collect_infrastructure_metrics)
        
        # 启动收集循环
        self._collection_task = asyncio.create_task(self._collection_loop())
        
    async def stop(self):
        """停止指标收集"""
        self.running = False
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        logger.info("📊 MetricsCollector stopped")
        
    def register_collector(self, collector: Callable):
        """注册指标收集器"""
        self.collectors.append(collector)
        logger.info(f"📊 Registered metrics collector: {collector.__name__}")
        
    async def _collection_loop(self):
        """指标收集循环"""
        while self.running:
            try:
                for collector in self.collectors:
                    metrics = await collector()
                    for metric in metrics:
                        self.metrics_storage[metric.name].append(metric)
                        # 保持最近1000个指标
                        if len(self.metrics_storage[metric.name]) > 1000:
                            self.metrics_storage[metric.name] = self.metrics_storage[metric.name][-1000:]
                            
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")
                
    async def _collect_api_metrics(self) -> List[Metric]:
        """收集API指标"""
        now = datetime.now()
        # 生成模拟API指标数据
        return [
            Metric("api_requests_total", 100 + time.time() % 50, MetricType.COUNTER, {"endpoint": "/api/v1/data"}, now),
            Metric("api_response_time", 0.1 + (time.time() % 10) / 100, MetricType.HISTOGRAM, {"endpoint": "/api/v1/data"}, now, "seconds"),
            Metric("api_error_rate", (time.time() % 100) / 1000, MetricType.GAUGE, {"endpoint": "/api/v1/data"}, now, "percent"),
            Metric("api_throughput", 50 + time.time() % 30, MetricType.GAUGE, {"endpoint": "/api/v1/data"}, now, "rps"),
        ]
        
    async def _collect_gateway_metrics(self) -> List[Metric]:
        """收集网关指标"""
        now = datetime.now()
        return [
            Metric("gateway_active_connections", 200 + time.time() % 100, MetricType.GAUGE, {"gateway": "main"}, now),
            Metric("gateway_route_latency", 0.05 + (time.time() % 5) / 100, MetricType.HISTOGRAM, {"route": "api"}, now, "seconds"),
            Metric("gateway_load_balance_ratio", 0.8 + (time.time() % 20) / 100, MetricType.GAUGE, {"backend": "service1"}, now),
        ]
        
    async def _collect_infrastructure_metrics(self) -> List[Metric]:
        """收集基础设施指标"""
        now = datetime.now()
        
        if PSUTIL_AVAILABLE:
            try:
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
            except:
                # 如果psutil调用失败，使用模拟数据
                cpu_percent = 45 + time.time() % 30
                memory_percent = 60 + time.time() % 20
                memory_available = 8.0 + time.time() % 4
        else:
            # 使用模拟数据
            cpu_percent = 45 + time.time() % 30
            memory_percent = 60 + time.time() % 20
            memory_available = 8.0 + time.time() % 4
        
        metrics = [
            Metric("system_cpu_usage", cpu_percent, MetricType.GAUGE, {"host": "gateway1"}, now, "percent"),
        ]
        
        if PSUTIL_AVAILABLE:
            try:
                metrics.extend([
                    Metric("system_memory_usage", memory.percent, MetricType.GAUGE, {"host": "gateway1"}, now, "percent"),
                    Metric("system_memory_available", memory.available / (1024**3), MetricType.GAUGE, {"host": "gateway1"}, now, "GB"),
                ])
            except:
                metrics.extend([
                    Metric("system_memory_usage", memory_percent, MetricType.GAUGE, {"host": "gateway1"}, now, "percent"),
                    Metric("system_memory_available", memory_available, MetricType.GAUGE, {"host": "gateway1"}, now, "GB"),
                ])
        else:
            metrics.extend([
                Metric("system_memory_usage", memory_percent, MetricType.GAUGE, {"host": "gateway1"}, now, "percent"),
                Metric("system_memory_available", memory_available, MetricType.GAUGE, {"host": "gateway1"}, now, "GB"),
            ])
        
        return metrics
        
    def get_metrics(self, name: str, duration: timedelta = timedelta(minutes=5)) -> List[Metric]:
        """获取指定时间段内的指标"""
        cutoff_time = datetime.now() - duration
        return [m for m in self.metrics_storage.get(name, []) if m.timestamp >= cutoff_time]

# ===== 2. RealTimeMonitoringEngine (实时监控引擎) =====

class RealTimeMonitoringEngine:
    """实时监控引擎 - 提供实时监控能力"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.dashboard_data: Dict[str, Any] = {}
        self.alert_rules: List[Dict[str, Any]] = []
        self.active_alerts: List[Alert] = []
        self.subscribers: List[Callable] = []
        self.running = False
        self._monitoring_task = None
        
    async def start(self):
        """启动实时监控引擎"""
        self.running = True
        logger.info("🔍 RealTimeMonitoringEngine started")
        
        # 配置默认告警规则
        self._setup_default_alert_rules()
        
        # 启动监控循环
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
    async def stop(self):
        """停止实时监控引擎"""
        self.running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("🔍 RealTimeMonitoringEngine stopped")
        
    def _setup_default_alert_rules(self):
        """设置默认告警规则"""
        self.alert_rules = [
            {
                "name": "high_cpu_usage",
                "metric": "system_cpu_usage",
                "condition": "value > 80",
                "level": AlertLevel.WARNING,
                "message": "CPU usage is above 80%"
            },
            {
                "name": "high_error_rate",
                "metric": "api_error_rate",
                "condition": "value > 0.05",
                "level": AlertLevel.ERROR,
                "message": "API error rate is above 5%"
            },
            {
                "name": "slow_response_time",
                "metric": "api_response_time",
                "condition": "value > 1.0",
                "level": AlertLevel.WARNING,
                "message": "API response time is above 1 second"
            }
        ]
        
    async def _monitoring_loop(self):
        """实时监控循环"""
        while self.running:
            try:
                # 更新仪表板数据
                await self._update_dashboard()
                
                # 检查告警规则
                await self._check_alert_rules()
                
                # 异常检测
                await self._detect_anomalies()
                
                # 通知订阅者
                await self._notify_subscribers()
                
                await asyncio.sleep(1.0)  # 每秒更新
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in real-time monitoring: {e}")
                
    async def _update_dashboard(self):
        """更新仪表板数据"""
        self.dashboard_data = {
            "timestamp": datetime.now().isoformat(),
            "api_metrics": self._get_api_summary(),
            "gateway_metrics": self._get_gateway_summary(),
            "system_metrics": self._get_system_summary(),
            "alerts": [asdict(alert) for alert in self.active_alerts if not alert.resolved]
        }
        
    def _get_api_summary(self) -> Dict[str, Any]:
        """获取API指标摘要"""
        request_metrics = self.metrics_collector.get_metrics("api_requests_total")
        response_metrics = self.metrics_collector.get_metrics("api_response_time")
        error_metrics = self.metrics_collector.get_metrics("api_error_rate")
        
        return {
            "total_requests": len(request_metrics),
            "avg_response_time": statistics.mean([m.value for m in response_metrics]) if response_metrics else 0,
            "current_error_rate": error_metrics[-1].value if error_metrics else 0,
            "requests_per_minute": len([m for m in request_metrics if m.timestamp >= datetime.now() - timedelta(minutes=1)])
        }
        
    def _get_gateway_summary(self) -> Dict[str, Any]:
        """获取网关指标摘要"""
        connection_metrics = self.metrics_collector.get_metrics("gateway_active_connections")
        latency_metrics = self.metrics_collector.get_metrics("gateway_route_latency")
        
        return {
            "active_connections": connection_metrics[-1].value if connection_metrics else 0,
            "avg_route_latency": statistics.mean([m.value for m in latency_metrics]) if latency_metrics else 0,
            "total_routes": 5,  # 示例数据
            "healthy_backends": 3  # 示例数据
        }
        
    def _get_system_summary(self) -> Dict[str, Any]:
        """获取系统指标摘要"""
        cpu_metrics = self.metrics_collector.get_metrics("system_cpu_usage")
        memory_metrics = self.metrics_collector.get_metrics("system_memory_usage")
        
        return {
            "cpu_usage": cpu_metrics[-1].value if cpu_metrics else 0,
            "memory_usage": memory_metrics[-1].value if memory_metrics else 0,
            "uptime": time.time() % 86400,  # 示例数据
            "health_score": 95  # 示例数据
        }
        
    async def _check_alert_rules(self):
        """检查告警规则"""
        for rule in self.alert_rules:
            metric_name = rule["metric"]
            metrics = self.metrics_collector.get_metrics(metric_name, timedelta(minutes=1))
            
            if metrics:
                latest_metric = metrics[-1]
                # 简单的条件检查
                if "value >" in rule["condition"]:
                    threshold = float(rule["condition"].split(">")[1].strip())
                    if latest_metric.value > threshold:
                        await self._trigger_alert(rule, latest_metric)
                        
    async def _trigger_alert(self, rule: Dict[str, Any], metric: Metric):
        """触发告警"""
        alert_id = str(uuid.uuid4())
        alert = Alert(
            id=alert_id,
            name=rule["name"],
            level=rule["level"],
            message=f"{rule['message']} (current: {metric.value})",
            timestamp=datetime.now(),
            labels=metric.labels
        )
        
        # 检查是否是重复告警
        existing_alert = next((a for a in self.active_alerts 
                              if a.name == alert.name and not a.resolved), None)
        if not existing_alert:
            self.active_alerts.append(alert)
            logger.warning(f"🚨 Alert triggered: {alert.name} - {alert.message}")
            
    async def _detect_anomalies(self):
        """异常检测"""
        # 简单的异常检测 - 检查指标突然变化
        for metric_name in ["api_response_time", "system_cpu_usage"]:
            metrics = self.metrics_collector.get_metrics(metric_name, timedelta(minutes=5))
            if len(metrics) >= 10:
                recent_values = [m.value for m in metrics[-10:]]
                mean_val = statistics.mean(recent_values)
                std_val = statistics.stdev(recent_values) if len(recent_values) > 1 else 0
                
                if std_val > 0 and abs(recent_values[-1] - mean_val) > 2 * std_val:
                    logger.info(f"🔍 Anomaly detected in {metric_name}: value {recent_values[-1]} deviates from mean {mean_val}")
                    
    async def _notify_subscribers(self):
        """通知订阅者"""
        for subscriber in self.subscribers:
            try:
                await subscriber(self.dashboard_data)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")
                
    def subscribe(self, callback: Callable):
        """订阅实时数据"""
        self.subscribers.append(callback)
        
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据"""
        return self.dashboard_data

# ===== 3. LogAggregator (日志聚合器) =====

class LogAggregator:
    """日志聚合器 - 集中管理和分析日志"""
    
    def __init__(self):
        self.log_storage: List[LogEntry] = []
        self.log_patterns: Dict[str, int] = defaultdict(int)
        self.running = False
        self._analysis_task = None
        
    async def start(self):
        """启动日志聚合器"""
        self.running = True
        logger.info("📝 LogAggregator started")
        
        # 启动日志分析任务
        self._analysis_task = asyncio.create_task(self._analysis_loop())
        
    async def stop(self):
        """停止日志聚合器"""
        self.running = False
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
        logger.info("📝 LogAggregator stopped")
        
    async def collect_log(self, entry: LogEntry):
        """收集日志条目"""
        self.log_storage.append(entry)
        
        # 保持最近10000条日志
        if len(self.log_storage) > 10000:
            self.log_storage = self.log_storage[-10000:]
            
        # 更新模式统计
        self.log_patterns[entry.level] += 1
        
    async def _analysis_loop(self):
        """日志分析循环"""
        while self.running:
            try:
                await self._analyze_error_patterns()
                await self._analyze_trends()
                await asyncio.sleep(30)  # 每30秒分析一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in log analysis: {e}")
                
    async def _analyze_error_patterns(self):
        """分析错误模式"""
        recent_logs = [log for log in self.log_storage 
                      if log.timestamp >= datetime.now() - timedelta(minutes=5)]
        
        error_logs = [log for log in recent_logs if log.level in ["ERROR", "CRITICAL"]]
        
        if len(error_logs) > 10:  # 5分钟内超过10个错误
            logger.warning(f"⚠️ High error rate detected: {len(error_logs)} errors in last 5 minutes")
            
    async def _analyze_trends(self):
        """分析日志趋势"""
        if len(self.log_storage) >= 100:
            recent_100 = self.log_storage[-100:]
            error_rate = len([log for log in recent_100 if log.level in ["ERROR", "CRITICAL"]]) / 100
            if error_rate > 0.1:  # 错误率超过10%
                logger.warning(f"⚠️ High error rate trend: {error_rate:.2%}")
                
    def search_logs(self, query: str, start_time: Optional[datetime] = None, 
                   end_time: Optional[datetime] = None) -> List[LogEntry]:
        """搜索日志"""
        logs = self.log_storage
        
        if start_time:
            logs = [log for log in logs if log.timestamp >= start_time]
        if end_time:
            logs = [log for log in logs if log.timestamp <= end_time]
            
        # 简单的文本搜索
        return [log for log in logs if query.lower() in log.message.lower()]
        
    def get_log_summary(self, duration: timedelta = timedelta(hours=1)) -> Dict[str, Any]:
        """获取日志摘要"""
        cutoff_time = datetime.now() - duration
        recent_logs = [log for log in self.log_storage if log.timestamp >= cutoff_time]
        
        level_counts = defaultdict(int)
        source_counts = defaultdict(int)
        
        for log in recent_logs:
            level_counts[log.level] += 1
            source_counts[log.source] += 1
            
        return {
            "total_logs": len(recent_logs),
            "level_distribution": dict(level_counts),
            "source_distribution": dict(source_counts),
            "time_range": f"{duration.total_seconds()/3600:.1f} hours"
        }

# ===== 简化版的其他组件 =====

class PerformanceAnalyzer:
    """性能分析器 (简化版)"""
    
    def __init__(self):
        self.running = False
        
    async def start(self):
        self.running = True
        logger.info("⚡ PerformanceAnalyzer started")
        
    async def stop(self):
        self.running = False
        logger.info("⚡ PerformanceAnalyzer stopped")
        
    def analyze_performance(self) -> Dict[str, Any]:
        """分析性能"""
        return {
            "bottleneck": "none",
            "recommendation": "system performing well",
            "performance_score": 85
        }

class HealthCheckManager:
    """健康检查管理器 (简化版)"""
    
    def __init__(self):
        self.running = False
        
    async def start(self):
        self.running = True
        logger.info("💊 HealthCheckManager started")
        
    async def stop(self):
        self.running = False
        logger.info("💊 HealthCheckManager stopped")
        
    def get_health_status(self) -> HealthStatus:
        """获取健康状态"""
        return HealthStatus.HEALTHY

class ObservabilityPlatform:
    """可观测性平台 (简化版)"""
    
    def __init__(self):
        self.running = False
        
    async def start(self):
        self.running = True
        logger.info("🔬 ObservabilityPlatform started")
        
    async def stop(self):
        self.running = False
        logger.info("🔬 ObservabilityPlatform stopped")
        
    def get_service_map(self) -> Dict[str, Any]:
        """获取服务地图"""
        return {
            "services": ["gateway", "backend1", "backend2"],
            "connections": [
                {"from": "gateway", "to": "backend1"},
                {"from": "gateway", "to": "backend2"}
            ]
        }

# ===== MonitoringGatewayManager (监控网关管理器) =====

class MonitoringGatewayManager:
    """监控网关管理器 - 统一管理所有监控组件"""
    
    def __init__(self):
        # 核心组件
        self.metrics_collector = MetricsCollector()
        self.monitoring_engine = RealTimeMonitoringEngine(self.metrics_collector)
        self.log_aggregator = LogAggregator()
        self.performance_analyzer = PerformanceAnalyzer()
        self.health_check_manager = HealthCheckManager()
        self.observability_platform = ObservabilityPlatform()
        
        self.running = False
        
    async def start(self):
        """启动监控网关管理器"""
        logger.info("🚀 Starting MonitoringGatewayManager...")
        
        try:
            # 启动所有组件
            await self.metrics_collector.start()
            await self.monitoring_engine.start()
            await self.log_aggregator.start()
            await self.performance_analyzer.start()
            await self.health_check_manager.start()
            await self.observability_platform.start()
            
            self.running = True
            logger.info("✅ MonitoringGatewayManager started successfully")
            
            # 生成示例日志
            await self._generate_sample_logs()
            
        except Exception as e:
            logger.error(f"❌ Failed to start MonitoringGatewayManager: {e}")
            raise
            
    async def stop(self):
        """停止监控网关管理器"""
        logger.info("🛑 Stopping MonitoringGatewayManager...")
        
        try:
            await self.metrics_collector.stop()
            await self.monitoring_engine.stop()
            await self.log_aggregator.stop()
            await self.performance_analyzer.stop()
            await self.health_check_manager.stop()
            await self.observability_platform.stop()
            
            self.running = False
            logger.info("✅ MonitoringGatewayManager stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Error stopping MonitoringGatewayManager: {e}")
            
    async def _generate_sample_logs(self):
        """生成示例日志"""
        sample_logs = [
            LogEntry(datetime.now(), "INFO", "Gateway started successfully", "gateway", {"component": "main"}),
            LogEntry(datetime.now(), "INFO", "Health check passed for backend service", "health_checker", {"service": "backend1"}),
            LogEntry(datetime.now(), "WARNING", "High response time detected", "performance_monitor", {"endpoint": "/api/v1/data"}),
            LogEntry(datetime.now(), "ERROR", "Connection timeout to backend service", "gateway", {"service": "backend2"}),
        ]
        
        for log in sample_logs:
            await self.log_aggregator.collect_log(log)
            
    def get_monitoring_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        return {
            "running": self.running,
            "components": {
                "metrics_collector": "active" if self.metrics_collector.running else "inactive",
                "monitoring_engine": "active" if self.monitoring_engine.running else "inactive", 
                "log_aggregator": "active" if self.log_aggregator.running else "inactive",
                "performance_analyzer": "active" if self.performance_analyzer.running else "inactive",
                "health_check_manager": "active" if self.health_check_manager.running else "inactive",
                "observability_platform": "active" if self.observability_platform.running else "inactive"
            },
            "dashboard_data": self.monitoring_engine.get_dashboard_data(),
            "health_status": self.health_check_manager.get_health_status().value,
            "log_summary": self.log_aggregator.get_log_summary()
        }

# ===== 主函数 =====

async def main():
    """主函数"""
    logger.info("🎯 Week 6 Day 5: API Gateway Monitoring System")
    logger.info("📊 Starting comprehensive monitoring and observability system...")
    
    # 创建监控网关管理器
    monitoring_manager = MonitoringGatewayManager()
    
    try:
        # 启动系统
        await monitoring_manager.start()
        
        # 运行监控系统
        logger.info("🔄 Monitoring system is running...")
        logger.info("📈 Collecting metrics, monitoring in real-time, aggregating logs...")
        
        # 运行30秒展示监控效果
        for i in range(6):
            await asyncio.sleep(5)
            status = monitoring_manager.get_monitoring_status()
            
            logger.info(f"📊 Monitoring Status Report #{i+1}:")
            logger.info(f"   - API Requests/min: {status['dashboard_data'].get('api_metrics', {}).get('requests_per_minute', 0)}")
            logger.info(f"   - Avg Response Time: {status['dashboard_data'].get('api_metrics', {}).get('avg_response_time', 0):.3f}s")
            logger.info(f"   - System CPU: {status['dashboard_data'].get('system_metrics', {}).get('cpu_usage', 0):.1f}%")
            logger.info(f"   - Active Connections: {status['dashboard_data'].get('gateway_metrics', {}).get('active_connections', 0)}")
            logger.info(f"   - Health Score: {status['dashboard_data'].get('system_metrics', {}).get('health_score', 0)}")
            logger.info(f"   - Total Logs: {status['log_summary']['total_logs']}")
            
        logger.info("✅ Week 6 Day 5 monitoring system demonstration completed!")
        
    except Exception as e:
        logger.error(f"❌ Error in monitoring system: {e}")
        raise
    finally:
        # 清理资源
        await monitoring_manager.stop()

if __name__ == "__main__":
    asyncio.run(main())