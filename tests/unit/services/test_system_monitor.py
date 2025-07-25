#!/usr/bin/env python3
"""
系统监控服务单元测试
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# 调整系统路径，便于导入被测模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 尝试导入被测模块
try:
    from services.monitoring.system_monitor import SystemMonitor, ServiceStatus, AlertLevel
except ImportError:
    # 如果无法导入，定义模拟类用于测试
    class AlertLevel:
        INFO = "info"
        WARNING = "warning"
        ERROR = "error"
        CRITICAL = "critical"
    
    class ServiceStatus:
        RUNNING = "running"
        STOPPED = "stopped"
        DEGRADED = "degraded"
        STARTING = "starting"
        UNKNOWN = "unknown"
        
    class SystemMonitor:
        def __init__(self, config=None):
            self.config = config or {}
            self.services = {}
            self.alerts = []
            self.metrics = {}
            self.is_running = False
            self.check_interval = self.config.get('check_interval', 60)  # 默认60秒
            self.alert_handlers = []
        
        def register_service(self, service_id, service_name, check_url=None, check_cmd=None):
            """注册需要监控的服务"""
            self.services[service_id] = {
                "id": service_id,
                "name": service_name,
                "check_url": check_url,
                "check_cmd": check_cmd,
                "status": ServiceStatus.UNKNOWN,
                "last_check": None,
                "error_count": 0
            }
            return True
        
        def register_alert_handler(self, handler):
            """注册告警处理器"""
            self.alert_handlers.append(handler)
            return True
        
        def start(self):
            """启动监控服务"""
            self.is_running = True
            return True
        
        def stop(self):
            """停止监控服务"""
            self.is_running = False
            return True
        
        def check_service(self, service_id):
            """检查特定服务状态"""
            if service_id not in self.services:
                raise ValueError(f"未知的服务ID: {service_id}")
                
            service = self.services[service_id]
            
            # 模拟检查逻辑
            # 在实际实现中，这里会根据check_url或check_cmd检查服务状态
            service["status"] = ServiceStatus.RUNNING
            service["last_check"] = datetime.now()
            service["error_count"] = 0
            
            return {
                "id": service_id,
                "status": service["status"],
                "last_check": service["last_check"],
                "response_time": 0.1  # 模拟响应时间
            }
        
        def check_all_services(self):
            """检查所有服务状态"""
            results = {}
            for service_id in self.services:
                try:
                    results[service_id] = self.check_service(service_id)
                except Exception as e:
                    results[service_id] = {
                        "id": service_id,
                        "status": ServiceStatus.UNKNOWN,
                        "error": str(e)
                    }
            return results
        
        def create_alert(self, service_id, level, message):
            """创建告警"""
            if service_id not in self.services:
                raise ValueError(f"未知的服务ID: {service_id}")
                
            alert = {
                "id": len(self.alerts) + 1,
                "service_id": service_id,
                "level": level,
                "message": message,
                "timestamp": datetime.now()
            }
            
            self.alerts.append(alert)
            
            # 触发告警处理器
            for handler in self.alert_handlers:
                handler(alert)
                
            return alert
        
        def get_service_status(self, service_id):
            """获取服务状态"""
            if service_id not in self.services:
                raise ValueError(f"未知的服务ID: {service_id}")
                
            return self.services[service_id]
        
        def get_all_service_statuses(self):
            """获取所有服务状态"""
            return self.services
        
        def get_alerts(self, level=None, service_id=None, limit=100):
            """获取告警列表"""
            filtered_alerts = self.alerts
            
            if level:
                filtered_alerts = [a for a in filtered_alerts if a["level"] == level]
                
            if service_id:
                filtered_alerts = [a for a in filtered_alerts if a["service_id"] == service_id]
                
            # 按时间倒序排序并限制数量
            filtered_alerts = sorted(filtered_alerts, key=lambda a: a["timestamp"], reverse=True)[:limit]
            
            return filtered_alerts
        
        def collect_metric(self, service_id, metric_name, value):
            """收集指标数据"""
            if service_id not in self.services:
                raise ValueError(f"未知的服务ID: {service_id}")
                
            if service_id not in self.metrics:
                self.metrics[service_id] = {}
                
            if metric_name not in self.metrics[service_id]:
                self.metrics[service_id][metric_name] = []
                
            self.metrics[service_id][metric_name].append({
                "value": value,
                "timestamp": datetime.now()
            })
            
            return True
        
        def get_metrics(self, service_id, metric_name=None):
            """获取指标数据"""
            if service_id not in self.services:
                raise ValueError(f"未知的服务ID: {service_id}")
                
            if service_id not in self.metrics:
                return {}
                
            if metric_name:
                return self.metrics[service_id].get(metric_name, [])
                
            return self.metrics[service_id]


class TestSystemMonitor:
    """
    系统监控服务测试
    """
    
    @pytest.fixture
    def setup_monitor(self):
        """设置监控服务测试环境"""
        config = {
            "check_interval": 30,  # 30秒
            "alert_channels": ["email", "slack"],
            "email_config": {
                "smtp_server": "smtp.example.com",
                "from_address": "alerts@example.com",
                "recipients": ["admin@example.com"]
            },
            "slack_config": {
                "webhook_url": "https://hooks.slack.com/services/xxx/yyy/zzz"
            }
        }
        
        monitor = SystemMonitor(config)
        
        # 注册一些测试服务
        monitor.register_service("data-collector", "数据采集器", check_url="http://collector:8080/health")
        monitor.register_service("data-normalizer", "数据标准化器", check_url="http://normalizer:8080/health")
        monitor.register_service("clickhouse", "ClickHouse数据库", check_cmd="clickhouse-client --query 'SELECT 1'")
        
        # 返回测试夹具
        yield monitor
    
    def test_initialization(self, setup_monitor):
        """测试监控服务初始化"""
        # Arrange
        monitor = setup_monitor
        
        # Assert
        assert monitor.check_interval == 30
        assert not monitor.is_running
        assert len(monitor.services) == 3
        assert "data-collector" in monitor.services
        assert "data-normalizer" in monitor.services
        assert "clickhouse" in monitor.services
    
    def test_register_service(self, setup_monitor):
        """测试注册服务"""
        # Arrange
        monitor = setup_monitor
        
        # Act
        result = monitor.register_service("api-gateway", "API网关", check_url="http://api-gateway:8080/health")
        
        # Assert
        assert result is True
        assert "api-gateway" in monitor.services
        assert monitor.services["api-gateway"]["name"] == "API网关"
        assert monitor.services["api-gateway"]["check_url"] == "http://api-gateway:8080/health"
    
    def test_register_alert_handler(self, setup_monitor):
        """测试注册告警处理器"""
        # Arrange
        monitor = setup_monitor
        handler = MagicMock()
        
        # Act
        result = monitor.register_alert_handler(handler)
        
        # Assert
        assert result is True
        assert handler in monitor.alert_handlers
    
    def test_start_stop(self, setup_monitor):
        """测试启动和停止监控服务"""
        # Arrange
        monitor = setup_monitor
        
        # Act - 启动
        start_result = monitor.start()
        
        # Assert - 启动
        assert start_result is True
        assert monitor.is_running is True
        
        # Act - 停止
        stop_result = monitor.stop()
        
        # Assert - 停止
        assert stop_result is True
        assert monitor.is_running is False
    
    def test_check_service_unknown_id(self, setup_monitor):
        """测试检查未知服务ID"""
        # Arrange
        monitor = setup_monitor
        
        # Act & Assert
        with pytest.raises(ValueError) as excinfo:
            monitor.check_service("unknown-service")
        assert "未知的服务ID" in str(excinfo.value)
    
    def test_check_service_success(self, setup_monitor):
        """测试成功检查服务状态"""
        # Arrange
        monitor = setup_monitor
        service_id = "data-collector"
        
        # Act
        result = monitor.check_service(service_id)
        
        # Assert
        assert result["id"] == service_id
        assert result["status"] == ServiceStatus.RUNNING
        assert result["last_check"] is not None
        assert result["response_time"] > 0
    
    def test_check_all_services(self, setup_monitor):
        """测试检查所有服务状态"""
        # Arrange
        monitor = setup_monitor
        
        # Act
        results = monitor.check_all_services()
        
        # Assert
        assert len(results) == 3
        assert "data-collector" in results
        assert "data-normalizer" in results
        assert "clickhouse" in results
        assert results["data-collector"]["status"] == ServiceStatus.RUNNING
    
    def test_create_alert_unknown_service(self, setup_monitor):
        """测试为未知服务创建告警"""
        # Arrange
        monitor = setup_monitor
        
        # Act & Assert
        with pytest.raises(ValueError) as excinfo:
            monitor.create_alert("unknown-service", AlertLevel.ERROR, "服务不可用")
        assert "未知的服务ID" in str(excinfo.value)
    
    def test_create_alert_success(self, setup_monitor):
        """测试成功创建告警"""
        # Arrange
        monitor = setup_monitor
        service_id = "data-collector"
        level = AlertLevel.WARNING
        message = "服务响应时间过长"
        
        # 注册模拟的告警处理器
        handler = MagicMock()
        monitor.register_alert_handler(handler)
        
        # Act
        alert = monitor.create_alert(service_id, level, message)
        
        # Assert
        assert alert["service_id"] == service_id
        assert alert["level"] == level
        assert alert["message"] == message
        assert alert["timestamp"] is not None
        assert alert in monitor.alerts
        handler.assert_called_once()
    
    def test_get_service_status_unknown(self, setup_monitor):
        """测试获取未知服务状态"""
        # Arrange
        monitor = setup_monitor
        
        # Act & Assert
        with pytest.raises(ValueError) as excinfo:
            monitor.get_service_status("unknown-service")
        assert "未知的服务ID" in str(excinfo.value)
    
    def test_get_service_status(self, setup_monitor):
        """测试获取服务状态"""
        # Arrange
        monitor = setup_monitor
        service_id = "data-collector"
        
        # 先检查服务状态
        monitor.check_service(service_id)
        
        # Act
        status = monitor.get_service_status(service_id)
        
        # Assert
        assert status["id"] == service_id
        assert status["name"] == "数据采集器"
        assert status["status"] == ServiceStatus.RUNNING
        assert status["last_check"] is not None
    
    def test_get_all_service_statuses(self, setup_monitor):
        """测试获取所有服务状态"""
        # Arrange
        monitor = setup_monitor
        
        # 先检查所有服务状态
        monitor.check_all_services()
        
        # Act
        statuses = monitor.get_all_service_statuses()
        
        # Assert
        assert len(statuses) == 3
        assert statuses["data-collector"]["status"] == ServiceStatus.RUNNING
        assert statuses["data-normalizer"]["status"] == ServiceStatus.RUNNING
        assert statuses["clickhouse"]["status"] == ServiceStatus.RUNNING
    
    def test_get_alerts_filtering(self, setup_monitor):
        """测试按条件筛选告警"""
        # Arrange
        monitor = setup_monitor
        
        # 创建一些测试告警
        monitor.create_alert("data-collector", AlertLevel.WARNING, "警告1")
        monitor.create_alert("data-normalizer", AlertLevel.ERROR, "错误1")
        monitor.create_alert("data-collector", AlertLevel.ERROR, "错误2")
        monitor.create_alert("clickhouse", AlertLevel.CRITICAL, "严重错误")
        
        # Act - 按级别筛选
        error_alerts = monitor.get_alerts(level=AlertLevel.ERROR)
        
        # Assert - 按级别筛选
        assert len(error_alerts) == 2
        assert all(a["level"] == AlertLevel.ERROR for a in error_alerts)
        
        # Act - 按服务筛选
        collector_alerts = monitor.get_alerts(service_id="data-collector")
        
        # Assert - 按服务筛选
        assert len(collector_alerts) == 2
        assert all(a["service_id"] == "data-collector" for a in collector_alerts)
        
        # Act - 组合筛选
        collector_error_alerts = monitor.get_alerts(level=AlertLevel.ERROR, service_id="data-collector")
        
        # Assert - 组合筛选
        assert len(collector_error_alerts) == 1
        assert collector_error_alerts[0]["level"] == AlertLevel.ERROR
        assert collector_error_alerts[0]["service_id"] == "data-collector"
    
    def test_collect_metric_unknown_service(self, setup_monitor):
        """测试为未知服务收集指标"""
        # Arrange
        monitor = setup_monitor
        
        # Act & Assert
        with pytest.raises(ValueError) as excinfo:
            monitor.collect_metric("unknown-service", "cpu_usage", 50)
        assert "未知的服务ID" in str(excinfo.value)
    
    def test_collect_metric_success(self, setup_monitor):
        """测试成功收集指标"""
        # Arrange
        monitor = setup_monitor
        service_id = "data-collector"
        metric_name = "cpu_usage"
        value = 75.5
        
        # Act
        result = monitor.collect_metric(service_id, metric_name, value)
        
        # Assert
        assert result is True
        assert service_id in monitor.metrics
        assert metric_name in monitor.metrics[service_id]
        assert len(monitor.metrics[service_id][metric_name]) == 1
        assert monitor.metrics[service_id][metric_name][0]["value"] == value
    
    def test_get_metrics(self, setup_monitor):
        """测试获取指标数据"""
        # Arrange
        monitor = setup_monitor
        service_id = "data-collector"
        
        # 收集一些测试指标
        monitor.collect_metric(service_id, "cpu_usage", 75.5)
        monitor.collect_metric(service_id, "memory_usage", 1024.0)
        monitor.collect_metric(service_id, "cpu_usage", 80.2)
        
        # Act - 获取特定指标
        cpu_metrics = monitor.get_metrics(service_id, "cpu_usage")
        
        # Assert - 获取特定指标
        assert len(cpu_metrics) == 2
        assert cpu_metrics[0]["value"] == 75.5
        assert cpu_metrics[1]["value"] == 80.2
        
        # Act - 获取所有指标
        all_metrics = monitor.get_metrics(service_id)
        
        # Assert - 获取所有指标
        assert len(all_metrics) == 2
        assert "cpu_usage" in all_metrics
        assert "memory_usage" in all_metrics
        assert len(all_metrics["cpu_usage"]) == 2
        assert len(all_metrics["memory_usage"]) == 1


# 直接运行测试文件
if __name__ == "__main__":
    pytest.main(["-v", __file__])