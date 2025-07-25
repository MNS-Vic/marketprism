#!/usr/bin/env python3
"""
Web服务监控示例

展示如何在Web服务中集成MarketPrism监控系统，包括：
- HTTP请求监控
- 响应时间跟踪
- 错误率统计
- 资源使用监控
"""

import time
import sys
from pathlib import Path
from typing import Dict, Any
import threading
import random

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from marketprism_collector.core.monitoring import (
    get_global_manager,
    MetricType,
    MetricCategory,
    MetricCollector,
    AlertRule,
    MetricSeverity
)
from marketprism_collector.core.monitoring.exporters import (
    PrometheusMetricsHandler,
    JSONMetricsAPI
)


class WebServiceMetricCollector(MetricCollector):
    """Web服务指标收集器"""
    
    def __init__(self):
        self.request_count = 0
        self.active_requests = 0
        
    def collect_metrics(self) -> Dict[str, Any]:
        """收集Web服务指标"""
        import psutil
        
        # 收集系统资源指标
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "system_cpu_usage_percent": cpu_percent,
            "system_memory_usage_bytes": memory.used,
            "system_memory_usage_percent": memory.percent,
            "system_disk_usage_bytes": disk.used,
            "system_disk_usage_percent": (disk.used / disk.total) * 100,
            "active_requests": self.active_requests,
            "total_requests": self.request_count
        }
    
    def get_collection_interval(self) -> int:
        return 10  # 10秒收集间隔


class WebServiceMonitor:
    """Web服务监控器"""
    
    def __init__(self):
        self.manager = get_global_manager()
        self.collector = WebServiceMetricCollector()
        self.setup_metrics()
        self.setup_alerts()
        self.setup_collectors()
    
    def setup_metrics(self):
        """设置监控指标"""
        print("🔧 设置Web服务监控指标...")
        
        # HTTP请求指标
        self.manager.registry.register_custom_metric(
            "http_requests_total",
            MetricType.COUNTER,
            MetricCategory.API,
            "HTTP请求总数",
            labels=["method", "endpoint", "status_code"],
            unit="requests"
        )
        
        self.manager.registry.register_custom_metric(
            "http_request_duration_seconds",
            MetricType.HISTOGRAM,
            MetricCategory.PERFORMANCE,
            "HTTP请求处理时间",
            labels=["method", "endpoint"],
            unit="seconds"
        )
        
        # 错误指标
        self.manager.registry.register_custom_metric(
            "http_errors_total",
            MetricType.COUNTER,
            MetricCategory.ERROR,
            "HTTP错误总数",
            labels=["endpoint", "error_type"]
        )
        
        # 活跃连接指标
        self.manager.registry.register_custom_metric(
            "active_connections",
            MetricType.GAUGE,
            MetricCategory.NETWORK,
            "当前活跃连接数"
        )
        
        # 业务指标
        self.manager.registry.register_custom_metric(
            "user_sessions",
            MetricType.GAUGE,
            MetricCategory.BUSINESS,
            "用户会话数"
        )
        
        self.manager.registry.register_custom_metric(
            "database_query_duration",
            MetricType.HISTOGRAM,
            MetricCategory.PERFORMANCE,
            "数据库查询时间",
            labels=["query_type"],
            unit="seconds"
        )
        
        # 系统资源指标
        self.manager.registry.register_custom_metric(
            "system_cpu_usage_percent",
            MetricType.GAUGE,
            MetricCategory.RESOURCE,
            "系统CPU使用率",
            unit="percent"
        )
        
        self.manager.registry.register_custom_metric(
            "system_memory_usage_bytes",
            MetricType.GAUGE,
            MetricCategory.RESOURCE,
            "系统内存使用量",
            unit="bytes"
        )
        
        print("✅ 指标设置完成")
    
    def setup_alerts(self):
        """设置告警规则"""
        print("🚨 设置告警规则...")
        
        # CPU使用率告警
        cpu_alert = AlertRule(
            metric_name="system_cpu_usage_percent",
            condition=">",
            threshold=80.0,
            severity=MetricSeverity.HIGH,
            message="系统CPU使用率过高",
            duration=60  # 持续1分钟
        )
        
        # 内存使用率告警
        memory_alert = AlertRule(
            metric_name="system_memory_usage_bytes",
            condition=">",
            threshold=8 * 1024 * 1024 * 1024,  # 8GB
            severity=MetricSeverity.MEDIUM,
            message="系统内存使用量过高"
        )
        
        # HTTP错误率告警
        error_alert = AlertRule(
            metric_name="http_errors_total",
            condition=">",
            threshold=10,
            severity=MetricSeverity.HIGH,
            message="HTTP错误数量过多",
            duration=30
        )
        
        self.manager.add_alert_rule(cpu_alert)
        self.manager.add_alert_rule(memory_alert)
        self.manager.add_alert_rule(error_alert)
        
        print(f"✅ 添加了 {len(self.manager.alert_rules)} 个告警规则")
    
    def setup_collectors(self):
        """设置指标收集器"""
        self.manager.register_collector("web_service", self.collector)
    
    def start_monitoring(self):
        """启动监控"""
        print("🚀 启动Web服务监控...")
        self.manager.start_collection(interval=5)  # 5秒收集间隔
        print("✅ 监控已启动")
    
    def stop_monitoring(self):
        """停止监控"""
        print("🛑 停止监控...")
        self.manager.stop_collection()
        print("✅ 监控已停止")
    
    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """记录HTTP请求"""
        labels = {
            "method": method,
            "endpoint": endpoint,
            "status_code": str(status_code)
        }
        
        # 记录请求总数
        self.manager.increment("http_requests_total", 1, labels)
        
        # 记录请求时间
        timing_labels = {"method": method, "endpoint": endpoint}
        self.manager.observe_histogram("http_request_duration_seconds", duration, timing_labels)
        
        # 记录错误
        if status_code >= 400:
            error_type = "client_error" if status_code < 500 else "server_error"
            error_labels = {"endpoint": endpoint, "error_type": error_type}
            self.manager.increment("http_errors_total", 1, error_labels)
        
        # 更新收集器状态
        self.collector.request_count += 1
    
    def record_database_query(self, query_type: str, duration: float):
        """记录数据库查询"""
        self.manager.observe_histogram(
            "database_query_duration",
            duration,
            {"query_type": query_type}
        )
    
    def update_active_connections(self, count: int):
        """更新活跃连接数"""
        self.manager.set_gauge("active_connections", count)
        self.collector.active_requests = count
    
    def update_user_sessions(self, count: int):
        """更新用户会话数"""
        self.manager.set_gauge("user_sessions", count)
    
    def get_metrics_endpoint(self) -> str:
        """获取Prometheus格式的指标"""
        handler = PrometheusMetricsHandler(self.manager)
        content, content_type = handler.get_metrics()
        return content
    
    def get_metrics_json(self) -> Dict[str, Any]:
        """获取JSON格式的指标"""
        api = JSONMetricsAPI(self.manager)
        return api.get_all_metrics()
    
    def check_health(self) -> Dict[str, Any]:
        """检查服务健康状态"""
        return self.manager.get_health_status()
    
    def get_alerts(self) -> list:
        """获取当前告警"""
        return self.manager.check_alerts()


def simulate_web_traffic(monitor: WebServiceMonitor, duration: int = 30):
    """模拟Web流量"""
    print(f"🌐 模拟 {duration} 秒的Web流量...")
    
    endpoints = [
        "/api/users",
        "/api/orders", 
        "/api/products",
        "/api/auth/login",
        "/api/auth/logout",
        "/health",
        "/metrics"
    ]
    
    methods = ["GET", "POST", "PUT", "DELETE"]
    
    end_time = time.time() + duration
    request_id = 0
    
    while time.time() < end_time:
        # 模拟并发请求
        concurrent_requests = random.randint(1, 5)
        
        for _ in range(concurrent_requests):
            request_id += 1
            endpoint = random.choice(endpoints)
            method = random.choice(methods)
            
            # 模拟请求处理时间
            base_duration = 0.05  # 50ms基础时间
            if endpoint == "/api/orders":
                base_duration = 0.2  # 订单接口较慢
            elif endpoint in ["/health", "/metrics"]:
                base_duration = 0.01  # 健康检查很快
            
            duration = base_duration * random.uniform(0.5, 3.0)
            
            # 模拟状态码分布
            if random.random() < 0.9:  # 90%成功
                status_code = 200 if method == "GET" else 201
            elif random.random() < 0.7:  # 7%客户端错误
                status_code = random.choice([400, 404, 422])
            else:  # 3%服务器错误
                status_code = random.choice([500, 502, 503])
            
            # 记录请求
            monitor.record_http_request(method, endpoint, status_code, duration)
            
            # 模拟数据库查询
            if endpoint.startswith("/api/") and status_code < 400:
                query_type = "SELECT" if method == "GET" else "INSERT"
                query_duration = random.uniform(0.001, 0.05)  # 1-50ms
                monitor.record_database_query(query_type, query_duration)
        
        # 更新活跃连接数
        active_connections = random.randint(10, 100)
        monitor.update_active_connections(active_connections)
        
        # 更新用户会话数
        user_sessions = random.randint(50, 500)
        monitor.update_user_sessions(user_sessions)
        
        # 等待一段时间再发送下一批请求
        time.sleep(random.uniform(0.1, 0.5))
    
    print("✅ Web流量模拟完成")


def demonstrate_monitoring_apis(monitor: WebServiceMonitor):
    """演示监控API"""
    print("📊 演示监控API...")
    
    # Prometheus格式
    print("\n--- Prometheus格式指标 ---")
    prometheus_metrics = monitor.get_metrics_endpoint()
    print(f"指标数据长度: {len(prometheus_metrics)} 字符")
    print("示例片段:")
    lines = prometheus_metrics.split('\n')[:10]
    for line in lines:
        if line.strip():
            print(f"  {line}")
    
    # JSON格式
    print("\n--- JSON格式指标 ---")
    json_metrics = monitor.get_metrics_json()
    if json_metrics["success"]:
        data = json_metrics["data"]
        print(f"总指标数: {data['summary']['total_metrics']}")
        print(f"导出指标数: {data['summary']['exported_metrics']}")
        
        # 显示一些关键指标
        metrics = data["metrics"]
        if "http_requests_total" in metrics:
            http_metrics = metrics["http_requests_total"]
            print(f"HTTP请求指标值数量: {len(http_metrics['values'])}")
    
    # 健康状态
    print("\n--- 健康状态 ---")
    health = monitor.check_health()
    print(f"系统状态: {health['status']}")
    print(f"健康状态: {'✅' if health['healthy'] else '⚠️'}")
    
    # 告警检查
    print("\n--- 告警状态 ---")
    alerts = monitor.get_alerts()
    if alerts:
        print(f"检测到 {len(alerts)} 个告警:")
        for alert in alerts:
            print(f"  ⚠️  {alert['message']} (值: {alert['value']})")
    else:
        print("✅ 当前无告警")


def main():
    """主函数"""
    print("🌐 Web服务监控示例")
    print("=" * 50)
    
    # 创建监控器
    monitor = WebServiceMonitor()
    
    try:
        # 启动监控
        monitor.start_monitoring()
        
        # 模拟Web流量
        simulate_web_traffic(monitor, duration=20)
        
        # 等待一段时间让指标收集器运行
        print("⏳ 等待指标收集...")
        time.sleep(3)
        
        # 演示监控API
        demonstrate_monitoring_apis(monitor)
        
        # 显示最终统计
        print("\n📈 最终统计:")
        stats = monitor.manager.get_stats()
        print(f"  总指标数: {stats['registry_stats']['total_metrics']}")
        print(f"  已处理事件: {stats['events_processed']}")
        print(f"  收集次数: {stats['metrics_collected']}")
        print(f"  运行时间: {stats['uptime_seconds']:.2f}秒")
        
    finally:
        # 停止监控
        monitor.stop_monitoring()
    
    print("\n🎉 Web服务监控示例完成！")
    print("   在实际应用中，你可以:")
    print("   1. 将 /metrics 端点暴露给Prometheus")
    print("   2. 使用JSON API构建自定义监控仪表板")
    print("   3. 集成告警系统接收告警通知")


if __name__ == "__main__":
    main()