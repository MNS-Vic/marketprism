"""
🧪 统一监控管理系统测试套件
测试所有整合的监控功能

创建时间: 2025-06-01 22:45:08
"""

import unittest
import time
from datetime import datetime
from unittest.mock import Mock, patch

# 导入统一监控系统
from core.monitoring import (
    UnifiedMonitoringPlatform,
    MonitoringFactory,
    MetricData,
    AlertRule,
    MonitoringLevel,
    get_global_monitoring,
    monitor,
    alert_on
)

class TestUnifiedMonitoringPlatform(unittest.TestCase):
    """统一监控平台测试"""
    
    def setUp(self):
        """测试前设置"""
        self.platform = UnifiedMonitoringPlatform()
    
    def tearDown(self):
        """测试后清理"""
        if self.platform.is_running:
            self.platform.stop_monitoring()
    
    def test_basic_monitoring(self):
        """测试基础监控功能"""
        # 测试指标收集
        self.platform.collect_metric("test.cpu", 75.5, {"host": "server1"})
        
        # 验证指标存储
        metrics = self.platform.get_metrics("test.cpu")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].name, "test.cpu")
        self.assertEqual(metrics[0].value, 75.5)
    
    def test_alert_system(self):
        """测试告警系统"""
        # 创建告警规则
        alert_triggered = []
        
        def alert_callback(rule, metric):
            alert_triggered.append((rule.name, metric.value))
        
        rule = AlertRule("high_cpu", "cpu > 80", 80.0, MonitoringLevel.WARNING, alert_callback)
        self.platform.add_alert_rule(rule)
        
        # 触发告警
        self.platform.collect_metric("cpu", 85.0)
        
        # 验证告警触发
        self.assertEqual(len(alert_triggered), 1)
        self.assertEqual(alert_triggered[0][0], "high_cpu")
        self.assertEqual(alert_triggered[0][1], 85.0)
    
    def test_monitoring_lifecycle(self):
        """测试监控生命周期"""
        # 启动监控
        self.platform.start_monitoring()
        self.assertTrue(self.platform.is_running)
        
        # 停止监控
        self.platform.stop_monitoring()
        self.assertFalse(self.platform.is_running)
    
    def test_api_gateway_monitoring(self):
        """测试API网关监控"""
        # 测试API调用跟踪
        self.platform.track_api_call("/api/users", "GET", 150.5, 200)
        
        # 验证指标收集
        metrics = self.platform.get_metrics("api./api/users.GET")
        self.assertTrue(len(metrics) >= 2)  # response_time + requests
    
    def test_intelligent_monitoring(self):
        """测试智能监控"""
        # 启用智能监控
        self.platform.enable_intelligent_monitoring()
        
        # 测试趋势分析
        trends = self.platform.analyze_trends("cpu.usage")
        self.assertIn("trend", trends)
        self.assertIn("prediction", trends)

class TestMonitoringFactory(unittest.TestCase):
    """监控工厂测试"""
    
    def test_basic_monitoring_creation(self):
        """测试基础监控创建"""
        platform = MonitoringFactory.create_basic_monitoring()
        self.assertIsInstance(platform, UnifiedMonitoringPlatform)
    
    def test_enterprise_monitoring_creation(self):
        """测试企业级监控创建"""
        platform = MonitoringFactory.create_enterprise_monitoring()
        self.assertIsInstance(platform, UnifiedMonitoringPlatform)

class TestGlobalMonitoring(unittest.TestCase):
    """全局监控测试"""
    
    def test_global_monitoring_access(self):
        """测试全局监控访问"""
        global_monitoring = get_global_monitoring()
        self.assertIsInstance(global_monitoring, UnifiedMonitoringPlatform)
    
    def test_convenient_functions(self):
        """测试便捷函数"""
        # 测试便捷监控函数
        monitor("test.memory", 512.0, {"host": "server1"})
        
        # 测试便捷告警函数
        alert_on("memory_high", "memory > 1000", 1000.0, MonitoringLevel.ERROR)
        
        # 验证全局监控中的数据
        global_monitoring = get_global_monitoring()
        metrics = global_monitoring.get_metrics("test.memory")
        self.assertTrue(len(metrics) > 0)

class TestMonitoringIntegration(unittest.TestCase):
    """监控系统集成测试"""
    
    def test_subsystem_integration(self):
        """测试子系统集成"""
        platform = UnifiedMonitoringPlatform()
        
        # TODO: 测试各子系统集成
        # - 测试智能监控集成
        # - 测试网关监控集成  
        # - 测试可观测性集成
        # - 测试告警系统集成
        
        self.assertTrue(True)  # 占位测试
    
    def test_performance_under_load(self):
        """测试负载下的性能"""
        platform = UnifiedMonitoringPlatform()
        
        # 大量指标收集测试
        start_time = time.time()
        for i in range(1000):
            platform.collect_metric(f"test.metric_{i % 10}", float(i), {"batch": "load_test"})
        end_time = time.time()
        
        # 验证性能
        self.assertLess(end_time - start_time, 5.0)  # 应在5秒内完成
        self.assertEqual(len(platform.metrics_storage), 1000)

if __name__ == "__main__":
    unittest.main()
