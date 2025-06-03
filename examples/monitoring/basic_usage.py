#!/usr/bin/env python3
"""
MarketPrism统一监控系统基本使用示例

展示如何使用统一指标管理器进行监控指标的注册、收集和导出。
"""

import time
import sys
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from marketprism_collector.core.monitoring import (
    get_global_manager, 
    MetricType, 
    MetricCategory,
    MetricCollector
)
from marketprism_collector.core.monitoring.exporters import (
    PrometheusExporter,
    JSONExporter,
    create_grafana_dashboard
)


class ExampleMetricCollector(MetricCollector):
    """示例指标收集器"""
    
    def collect_metrics(self):
        """收集示例指标"""
        return {
            "active_connections": 42,
            "queue_size": 128,
            "cpu_usage_percent": 65.5,
            "memory_usage_bytes": 1024 * 1024 * 512  # 512MB
        }
    
    def get_collection_interval(self):
        return 5  # 5秒收集一次


def setup_metrics():
    """设置监控指标"""
    print("🔧 设置监控指标...")
    
    # 获取全局管理器
    manager = get_global_manager()
    
    # 注册业务指标
    manager.registry.register_custom_metric(
        "requests_processed",
        MetricType.COUNTER,
        MetricCategory.BUSINESS,
        "处理的请求总数",
        labels=["method", "endpoint", "status"]
    )
    
    # 注册性能指标
    manager.registry.register_custom_metric(
        "request_duration",
        MetricType.HISTOGRAM,
        MetricCategory.PERFORMANCE,
        "请求处理时间分布",
        labels=["endpoint"],
        unit="seconds"
    )
    
    # 注册系统指标
    manager.registry.register_custom_metric(
        "active_connections",
        MetricType.GAUGE,
        MetricCategory.NETWORK,
        "当前活跃连接数"
    )
    
    manager.registry.register_custom_metric(
        "queue_size",
        MetricType.GAUGE,
        MetricCategory.SYSTEM,
        "消息队列大小"
    )
    
    manager.registry.register_custom_metric(
        "cpu_usage_percent",
        MetricType.GAUGE,
        MetricCategory.RESOURCE,
        "CPU使用率",
        unit="percent"
    )
    
    manager.registry.register_custom_metric(
        "memory_usage",
        MetricType.GAUGE,
        MetricCategory.RESOURCE,
        "内存使用量",
        unit="bytes"
    )
    
    print("✅ 指标设置完成")
    return manager


def simulate_application_metrics(manager):
    """模拟应用程序产生指标数据"""
    print("📊 模拟应用程序指标...")
    
    # 模拟请求处理
    endpoints = ["/api/users", "/api/orders", "/api/products"]
    methods = ["GET", "POST", "PUT", "DELETE"]
    statuses = ["200", "201", "400", "404", "500"]
    
    import random
    
    for _ in range(50):
        endpoint = random.choice(endpoints)
        method = random.choice(methods)
        status = random.choice(statuses)
        
        # 增加请求计数
        manager.increment(
            "requests_processed", 
            1, 
            {"method": method, "endpoint": endpoint, "status": status}
        )
        
        # 记录请求时间
        duration = random.uniform(0.01, 2.0)  # 10ms到2s
        manager.observe_histogram(
            "request_duration",
            duration,
            {"endpoint": endpoint}
        )
    
    # 设置系统指标
    manager.set_gauge("active_connections", random.randint(20, 100))
    manager.set_gauge("queue_size", random.randint(50, 200))
    manager.set_gauge("cpu_usage_percent", random.uniform(30, 90))
    manager.set_gauge("memory_usage", random.randint(300, 800) * 1024 * 1024)
    
    print("✅ 指标数据模拟完成")


def demonstrate_timer_context(manager):
    """演示计时器上下文管理器"""
    print("⏱️  演示计时器上下文管理器...")
    
    # 注册计时器指标
    manager.registry.register_custom_metric(
        "operation_duration",
        MetricType.HISTOGRAM,
        MetricCategory.PERFORMANCE,
        "操作执行时间",
        unit="seconds"
    )
    
    # 使用计时器测量操作耗时
    with manager.timer("operation_duration", {"operation": "data_processing"}):
        print("   执行数据处理操作...")
        time.sleep(0.1)  # 模拟耗时操作
    
    with manager.timer("operation_duration", {"operation": "api_call"}):
        print("   执行API调用...")
        time.sleep(0.05)  # 模拟API调用
    
    print("✅ 计时器演示完成")


def export_metrics_examples(manager):
    """演示指标导出"""
    print("📤 导出指标...")
    
    metrics = manager.registry.get_all_metrics()
    
    # Prometheus格式导出
    print("\n--- Prometheus格式 ---")
    prometheus_exporter = PrometheusExporter(include_help=True, include_timestamp=False)
    prometheus_output = prometheus_exporter.export_metrics(metrics)
    print(prometheus_output[:500] + "..." if len(prometheus_output) > 500 else prometheus_output)
    
    # JSON格式导出
    print("\n--- JSON格式 ---")
    json_exporter = JSONExporter(pretty_print=True, include_metadata=True)
    json_output = json_exporter.export_metrics(metrics)
    
    # 只显示部分JSON输出
    import json
    data = json.loads(json_output)
    summary = data.get("summary", {})
    print(f"指标总数: {summary.get('total_metrics', 0)}")
    print(f"导出指标数: {summary.get('exported_metrics', 0)}")
    
    # 显示第一个指标的详细信息
    if data.get("metrics"):
        first_metric_name = next(iter(data["metrics"]))
        first_metric = data["metrics"][first_metric_name]
        print(f"\n示例指标 '{first_metric_name}':")
        print(f"  类型: {first_metric['definition']['type']}")
        print(f"  分类: {first_metric['definition']['category']}")
        print(f"  描述: {first_metric['definition']['description']}")
        print(f"  值数量: {len(first_metric['values'])}")


def demonstrate_alert_rules(manager):
    """演示告警规则"""
    print("🚨 演示告警规则...")
    
    from marketprism_collector.core.monitoring import AlertRule, MetricSeverity
    
    # 添加CPU使用率告警
    cpu_alert = AlertRule(
        metric_name="cpu_usage_percent",
        condition=">",
        threshold=80.0,
        severity=MetricSeverity.HIGH,
        message="CPU使用率过高",
        duration=5  # 持续5秒
    )
    
    # 添加内存使用告警
    memory_alert = AlertRule(
        metric_name="memory_usage",
        condition=">",
        threshold=700 * 1024 * 1024,  # 700MB
        severity=MetricSeverity.MEDIUM,
        message="内存使用量过高"
    )
    
    manager.add_alert_rule(cpu_alert)
    manager.add_alert_rule(memory_alert)
    
    print(f"✅ 添加了 {len(manager.alert_rules)} 个告警规则")
    
    # 检查告警
    alerts = manager.check_alerts()
    if alerts:
        print("⚠️  检测到告警:")
        for alert in alerts:
            print(f"  - {alert['message']} (当前值: {alert['value']})")
    else:
        print("✅ 当前无告警")


def demonstrate_collection_lifecycle(manager):
    """演示指标收集生命周期"""
    print("🔄 演示指标收集生命周期...")
    
    # 注册自定义收集器
    collector = ExampleMetricCollector()
    manager.register_collector("example", collector)
    
    print("启动指标收集...")
    manager.start_collection(interval=1)  # 1秒收集间隔
    
    # 运行几秒钟
    time.sleep(3)
    
    print("停止指标收集...")
    manager.stop_collection()
    
    # 检查收集到的指标
    print("收集到的系统指标:")
    for metric_name in ["active_connections", "queue_size", "cpu_usage_percent"]:
        metric = manager.registry.get_metric(metric_name)
        if metric and metric.get_values():
            value = next(iter(metric.get_values().values())).value
            print(f"  {metric_name}: {value}")


def generate_grafana_dashboard(manager):
    """生成Grafana仪表板配置"""
    print("📊 生成Grafana仪表板...")
    
    metrics = manager.registry.get_all_metrics()
    dashboard = create_grafana_dashboard(
        metrics,
        dashboard_title="MarketPrism监控仪表板",
        refresh_interval="10s"
    )
    
    # 保存到文件
    import json
    dashboard_file = project_root / "examples" / "monitoring" / "grafana_dashboard.json"
    with open(dashboard_file, 'w', encoding='utf-8') as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Grafana仪表板配置已保存到: {dashboard_file}")
    print(f"   面板数量: {len(dashboard['dashboard']['panels'])}")


def main():
    """主函数"""
    print("🚀 MarketPrism统一监控系统示例")
    print("=" * 50)
    
    # 设置指标
    manager = setup_metrics()
    
    # 模拟应用指标
    simulate_application_metrics(manager)
    
    # 演示计时器
    demonstrate_timer_context(manager)
    
    # 导出指标
    export_metrics_examples(manager)
    
    # 演示告警规则
    demonstrate_alert_rules(manager)
    
    # 演示收集生命周期
    demonstrate_collection_lifecycle(manager)
    
    # 生成Grafana仪表板
    generate_grafana_dashboard(manager)
    
    # 显示最终统计
    print("\n📈 最终统计:")
    stats = manager.get_stats()
    print(f"  总指标数: {stats['registry_stats']['total_metrics']}")
    print(f"  收集器数: {stats['collectors']}")
    print(f"  告警规则数: {stats['alert_rules']}")
    print(f"  运行时间: {stats['uptime_seconds']:.2f}秒")
    
    # 健康状态
    health = manager.get_health_status()
    print(f"  系统状态: {health['status']}")
    print(f"  健康状态: {'✅' if health['healthy'] else '⚠️'}")
    
    print("\n🎉 示例演示完成！")
    print("   你可以查看生成的Grafana仪表板配置文件")
    print("   也可以将Prometheus输出接入你的监控系统")


if __name__ == "__main__":
    main()