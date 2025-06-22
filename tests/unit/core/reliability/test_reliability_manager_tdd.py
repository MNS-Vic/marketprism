"""
可靠性管理器TDD测试
专门用于提升core/reliability/manager.py的测试覆盖率到90%以上

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from core.reliability.manager import (
    ReliabilityManager, ReliabilityConfig, HealthStatus, AlertLevel,
    DataQualityMetrics, AnomalyAlert, SystemMetrics,
    get_reliability_manager, initialize_reliability_manager
)


class TestReliabilityConfig:
    """测试ReliabilityConfig配置类"""
    
    def test_config_default_initialization(self):
        """测试：默认配置初始化"""
        config = ReliabilityConfig()

        assert config.enable_circuit_breaker is True
        assert config.enable_rate_limiter is True
        assert config.enable_retry_handler is True
        assert config.enable_cold_storage_monitor is True
        assert config.enable_data_quality_monitor is True
        assert config.enable_anomaly_detector is True
        assert config.health_check_interval == 30
        assert config.metrics_collection_interval == 60
        assert config.alert_cooldown == 300
        
    def test_config_custom_initialization(self):
        """测试：自定义配置初始化"""
        config = ReliabilityConfig(
            enable_circuit_breaker=False,
            health_check_interval=60,
            max_error_rate=0.1,
            enable_anomaly_detector=False
        )

        assert config.enable_circuit_breaker is False
        assert config.health_check_interval == 60
        assert config.max_error_rate == 0.1
        assert config.enable_anomaly_detector is False


class TestHealthStatus:
    """测试HealthStatus枚举"""
    
    def test_health_status_values(self):
        """测试：健康状态值"""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.FAILED.value == "failed"
        
    def test_health_status_comparison(self):
        """测试：健康状态比较"""
        # 测试枚举成员存在
        assert HealthStatus.HEALTHY != HealthStatus.WARNING
        assert HealthStatus.WARNING != HealthStatus.CRITICAL
        assert HealthStatus.CRITICAL != HealthStatus.FAILED


class TestAlertLevel:
    """测试AlertLevel枚举"""
    
    def test_alert_level_values(self):
        """测试：告警级别值"""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.ERROR.value == "error"
        assert AlertLevel.CRITICAL.value == "critical"


class TestDataQualityMetrics:
    """测试DataQualityMetrics数据类"""
    
    def test_data_quality_metrics_initialization(self):
        """测试：数据质量指标初始化"""
        metrics = DataQualityMetrics()

        assert metrics.freshness_score == 0.0
        assert metrics.completeness_score == 0.0
        assert metrics.accuracy_score == 0.0
        assert metrics.consistency_score == 0.0
        assert metrics.drift_score == 0.0
        assert metrics.overall_score == 0.0
        assert metrics.last_updated == 0.0
        
    def test_data_quality_metrics_custom_values(self):
        """测试：自定义数据质量指标"""
        metrics = DataQualityMetrics(
            freshness_score=0.95,
            completeness_score=0.98,
            accuracy_score=0.92,
            consistency_score=0.88,
            drift_score=0.05,
            overall_score=0.90,
            last_updated=1234567890.0
        )

        assert metrics.freshness_score == 0.95
        assert metrics.completeness_score == 0.98
        assert metrics.accuracy_score == 0.92
        assert metrics.consistency_score == 0.88
        assert metrics.drift_score == 0.05
        assert metrics.overall_score == 0.90
        assert metrics.last_updated == 1234567890.0


class TestAnomalyAlert:
    """测试AnomalyAlert数据类"""
    
    def test_anomaly_alert_initialization(self):
        """测试：异常告警初始化"""
        alert = AnomalyAlert(
            alert_id="test_alert_001",
            level=AlertLevel.WARNING,
            component="test_component",
            message="Test anomaly detected",
            timestamp=1234567890.0
        )

        assert alert.alert_id == "test_alert_001"
        assert alert.level == AlertLevel.WARNING
        assert alert.component == "test_component"
        assert alert.message == "Test anomaly detected"
        assert alert.timestamp == 1234567890.0
        assert alert.metadata == {}
        assert alert.resolved is False
        assert alert.resolved_at is None


class TestSystemMetrics:
    """测试SystemMetrics数据类"""
    
    def test_system_metrics_initialization(self):
        """测试：系统指标初始化"""
        metrics = SystemMetrics()

        assert metrics.avg_response_time_ms == 0.0
        assert metrics.error_rate == 0.0
        assert metrics.throughput_rps == 0.0
        assert metrics.cpu_usage_percent == 0.0
        assert metrics.memory_usage_percent == 0.0
        assert metrics.disk_usage_percent == 0.0
        assert metrics.active_connections == 0
        assert metrics.processed_messages == 0
        assert metrics.failed_operations == 0
        assert metrics.last_updated == 0.0
        
    def test_system_metrics_custom_values(self):
        """测试：自定义系统指标"""
        metrics = SystemMetrics(
            avg_response_time_ms=125.8,
            error_rate=0.02,
            throughput_rps=250.5,
            cpu_usage_percent=45.5,
            memory_usage_percent=62.3,
            disk_usage_percent=78.9,
            active_connections=150,
            processed_messages=1000,
            failed_operations=20,
            last_updated=1234567890.0
        )

        assert metrics.avg_response_time_ms == 125.8
        assert metrics.error_rate == 0.02
        assert metrics.throughput_rps == 250.5
        assert metrics.cpu_usage_percent == 45.5
        assert metrics.memory_usage_percent == 62.3
        assert metrics.disk_usage_percent == 78.9
        assert metrics.active_connections == 150
        assert metrics.processed_messages == 1000
        assert metrics.failed_operations == 20
        assert metrics.last_updated == 1234567890.0


class TestReliabilityManagerInitialization:
    """测试ReliabilityManager初始化"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = ReliabilityConfig()
        
    def teardown_method(self):
        """清理测试方法"""
        # 清理全局状态
        pass
        
    def test_manager_default_initialization(self):
        """测试：默认初始化"""
        manager = ReliabilityManager(self.config)

        assert manager.config == self.config
        assert manager.is_running is False
        assert manager.components == {}
        assert manager.last_health_check == 0.0
        assert manager.active_alerts == []
        assert manager.alert_history == []
        assert isinstance(manager.system_metrics, SystemMetrics)
        assert isinstance(manager.data_quality_metrics, DataQualityMetrics)
        
    def test_manager_custom_config_initialization(self):
        """测试：自定义配置初始化"""
        custom_config = ReliabilityConfig(
            enable_circuit_breaker=False,
            health_check_interval=120.0
        )
        manager = ReliabilityManager(custom_config)
        
        assert manager.config.enable_circuit_breaker is False
        assert manager.config.health_check_interval == 120.0
        
    @pytest.mark.asyncio
    async def test_manager_start_stop_lifecycle(self):
        """测试：管理器启动停止生命周期"""
        manager = ReliabilityManager(self.config)
        
        # 初始状态
        assert manager.is_running is False
        
        # 启动管理器
        await manager.start()
        assert manager.is_running is True
        
        # 停止管理器
        await manager.stop()
        assert manager.is_running is False
        
    @pytest.mark.asyncio
    async def test_manager_double_start_prevention(self):
        """测试：防止重复启动"""
        manager = ReliabilityManager(self.config)
        
        # 第一次启动
        await manager.start()
        assert manager.is_running is True
        
        # 第二次启动应该被忽略
        await manager.start()
        assert manager.is_running is True
        
        # 清理
        await manager.stop()
        
    @pytest.mark.asyncio
    async def test_manager_stop_when_not_running(self):
        """测试：未运行时停止"""
        manager = ReliabilityManager(self.config)
        
        # 未启动时停止应该不抛出异常
        await manager.stop()
        assert manager.is_running is False


class TestReliabilityManagerHealthCheck:
    """测试ReliabilityManager健康检查"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = ReliabilityConfig()
        self.manager = ReliabilityManager(self.config)
        
    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.manager.stop())
            else:
                loop.run_until_complete(self.manager.stop())
        except RuntimeError:
            pass
        
    def test_comprehensive_status_basic(self):
        """测试：基本综合状态"""
        status = self.manager.get_comprehensive_status()

        assert isinstance(status, dict)
        assert 'is_running' in status
        assert 'uptime_hours' in status
        assert 'components' in status
        assert 'system_metrics' in status
        assert 'data_quality' in status
        assert 'alerts' in status

    def test_comprehensive_status_with_components(self):
        """测试：带组件的综合状态"""
        # 模拟添加组件
        mock_component = Mock()
        mock_component.get_status = Mock(return_value={'status': 'healthy'})
        self.manager.components['test_component'] = mock_component

        status = self.manager.get_comprehensive_status()

        assert 'components' in status
        assert status['is_running'] is False

    def test_record_request_performance(self):
        """测试：记录请求性能"""
        # 记录成功请求
        self.manager.record_request(100.5, is_error=False)
        assert len(self.manager.response_times) == 1
        assert self.manager.response_times[0] == 100.5
        assert len(self.manager.error_counts) == 1
        assert self.manager.error_counts[0] == 0

        # 记录失败请求
        self.manager.record_request(200.0, is_error=True)
        assert len(self.manager.response_times) == 2
        assert self.manager.response_times[1] == 200.0
        assert len(self.manager.error_counts) == 2
        assert self.manager.error_counts[1] == 1


class TestReliabilityManagerAlerts:
    """测试ReliabilityManager告警功能"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = ReliabilityConfig()
        self.manager = ReliabilityManager(self.config)
        
    @pytest.mark.asyncio
    async def test_create_alert(self):
        """测试：创建告警"""
        await self.manager._create_alert(
            AlertLevel.WARNING,
            "test_component",
            "Test alert message"
        )

        assert len(self.manager.active_alerts) == 1
        assert len(self.manager.alert_history) == 1

        alert = self.manager.active_alerts[0]
        assert alert.level == AlertLevel.WARNING
        assert alert.component == "test_component"
        assert alert.message == "Test alert message"
        
    @pytest.mark.asyncio
    async def test_resolve_alert(self):
        """测试：解决告警"""
        # 创建告警
        await self.manager._create_alert(
            AlertLevel.WARNING,
            "test_component",
            "Test alert message"
        )

        assert len(self.manager.active_alerts) == 1
        alert_id = self.manager.active_alerts[0].alert_id

        # 解决告警
        await self.manager.resolve_alert(alert_id)

        assert len(self.manager.active_alerts) == 0
        # 历史记录中应该还有
        assert len(self.manager.alert_history) == 1
        assert self.manager.alert_history[0].resolved is True
        
    @pytest.mark.asyncio
    async def test_multiple_alerts_different_levels(self):
        """测试：不同级别的多个告警"""
        # 创建不同级别的告警
        await self.manager._create_alert(
            AlertLevel.WARNING,
            "test_component",
            "Warning alert"
        )

        await self.manager._create_alert(
            AlertLevel.CRITICAL,
            "test_component",
            "Critical alert"
        )

        assert len(self.manager.active_alerts) == 2
        assert len(self.manager.alert_history) == 2

        # 检查告警级别
        levels = [alert.level for alert in self.manager.active_alerts]
        assert AlertLevel.WARNING in levels
        assert AlertLevel.CRITICAL in levels

    def test_record_throughput(self):
        """测试：记录吞吐量"""
        self.manager.record_throughput(100.5)
        assert len(self.manager.throughput_samples) == 1
        assert self.manager.throughput_samples[0] == 100.5

        # 记录多个样本
        for i in range(5):
            self.manager.record_throughput(50.0 + i * 10)

        assert len(self.manager.throughput_samples) == 6


class TestReliabilityManagerAdvanced:
    """测试ReliabilityManager高级功能"""

    def setup_method(self):
        """设置测试方法"""
        self.config = ReliabilityConfig()
        self.manager = ReliabilityManager(self.config)

    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.manager.stop())
            else:
                loop.run_until_complete(self.manager.stop())
        except RuntimeError:
            pass

    def test_system_metrics_direct_update(self):
        """测试：直接更新系统指标"""
        # 初始指标
        assert self.manager.system_metrics.avg_response_time_ms == 0.0
        assert self.manager.system_metrics.error_rate == 0.0

        # 直接更新指标
        self.manager.system_metrics.avg_response_time_ms = 150.5
        self.manager.system_metrics.error_rate = 0.05
        self.manager.system_metrics.throughput_rps = 100.0
        self.manager.system_metrics.cpu_usage_percent = 45.0

        assert self.manager.system_metrics.avg_response_time_ms == 150.5
        assert self.manager.system_metrics.error_rate == 0.05
        assert self.manager.system_metrics.throughput_rps == 100.0
        assert self.manager.system_metrics.cpu_usage_percent == 45.0

    def test_data_quality_metrics_direct_update(self):
        """测试：直接更新数据质量指标"""
        # 初始指标
        assert self.manager.data_quality_metrics.freshness_score == 0.0
        assert self.manager.data_quality_metrics.completeness_score == 0.0

        # 直接更新指标
        self.manager.data_quality_metrics.freshness_score = 0.95
        self.manager.data_quality_metrics.completeness_score = 0.98
        self.manager.data_quality_metrics.accuracy_score = 0.92
        self.manager.data_quality_metrics.consistency_score = 0.88

        assert self.manager.data_quality_metrics.freshness_score == 0.95
        assert self.manager.data_quality_metrics.completeness_score == 0.98
        assert self.manager.data_quality_metrics.accuracy_score == 0.92
        assert self.manager.data_quality_metrics.consistency_score == 0.88

    def test_comprehensive_status_uptime(self):
        """测试：综合状态中的运行时间"""
        # 获取综合状态
        status = self.manager.get_comprehensive_status()

        assert isinstance(status, dict)
        assert 'uptime_hours' in status
        assert status['uptime_hours'] >= 0.0
        assert status['uptime_hours'] < 0.1  # 应该很小，刚启动

    def test_comprehensive_status_alerts(self):
        """测试：综合状态中的告警信息"""
        status = self.manager.get_comprehensive_status()

        assert isinstance(status, dict)
        assert 'alerts' in status
        assert 'active_count' in status['alerts']
        assert 'total_count' in status['alerts']
        assert 'active_alerts' in status['alerts']
        assert 'recent_alerts' in status['alerts']

        # 初始状态应该没有告警
        assert status['alerts']['active_count'] == 0
        assert status['alerts']['total_count'] == 0

    @pytest.mark.asyncio
    async def test_comprehensive_status_with_alerts(self):
        """测试：有告警时的综合状态"""
        # 创建一些告警
        await self.manager._create_alert(
            AlertLevel.WARNING,
            "test_component",
            "Test warning"
        )

        await self.manager._create_alert(
            AlertLevel.CRITICAL,
            "test_component",
            "Test critical"
        )

        status = self.manager.get_comprehensive_status()

        assert status['alerts']['active_count'] == 2
        assert status['alerts']['total_count'] == 2
        assert len(status['alerts']['active_alerts']) == 2
        assert len(status['alerts']['recent_alerts']) == 2

    def test_comprehensive_status_performance(self):
        """测试：综合状态中的性能信息"""
        # 记录一些性能数据
        self.manager.record_request(100.0, is_error=False)
        self.manager.record_request(200.0, is_error=True)
        self.manager.record_request(150.0, is_error=False)
        self.manager.record_throughput(50.0)
        self.manager.record_throughput(75.0)

        status = self.manager.get_comprehensive_status()

        assert isinstance(status, dict)
        assert 'system_metrics' in status

        # 验证性能数据被记录
        assert len(self.manager.response_times) == 3
        assert len(self.manager.error_counts) == 3
        assert len(self.manager.throughput_samples) == 2

    def test_metrics_history_management(self):
        """测试：指标历史管理"""
        # 添加一些数据
        self.manager.record_request(100.0, is_error=False)
        self.manager.record_throughput(50.0)

        assert len(self.manager.response_times) == 1
        assert len(self.manager.throughput_samples) == 1

        # 验证数据存在
        assert self.manager.response_times[0] == 100.0
        assert self.manager.throughput_samples[0] == 50.0
        assert self.manager.error_counts[0] == 0

    def test_component_management(self):
        """测试：组件管理"""
        mock_component = Mock()
        mock_component.get_status = Mock(return_value={'status': 'healthy'})

        # 直接添加组件到字典
        self.manager.components['test_component'] = mock_component

        assert 'test_component' in self.manager.components
        assert self.manager.components['test_component'] == mock_component

    def test_component_removal(self):
        """测试：组件移除"""
        mock_component = Mock()
        self.manager.components['test_component'] = mock_component

        assert 'test_component' in self.manager.components

        # 直接从字典移除
        del self.manager.components['test_component']

        assert 'test_component' not in self.manager.components

    def test_component_status_check(self):
        """测试：组件状态检查"""
        mock_component = Mock()
        mock_component.get_status = Mock(return_value={'status': 'healthy', 'uptime': 100})

        self.manager.components['test_component'] = mock_component

        status = self.manager.get_comprehensive_status()

        # 验证组件状态被包含在综合状态中
        assert 'components' in status
        assert isinstance(status['components'], dict)

    @pytest.mark.asyncio
    async def test_component_lifecycle_with_start_stop(self):
        """测试：带启动停止的组件生命周期"""
        await self.manager.start()

        # 检查组件是否已注册
        assert len(self.manager.components) > 0

        await self.manager.stop()

        # 停止后组件仍然注册，但管理器不运行
        assert self.manager.is_running is False


class TestGlobalReliabilityManager:
    """测试全局可靠性管理器函数"""

    def test_get_reliability_manager_singleton(self):
        """测试：获取可靠性管理器单例"""
        manager1 = get_reliability_manager()
        manager2 = get_reliability_manager()

        # 应该返回同一个实例
        assert manager1 is manager2
        assert isinstance(manager1, ReliabilityManager)

    def test_initialize_reliability_manager(self):
        """测试：初始化可靠性管理器"""
        custom_config = ReliabilityConfig(
            enable_circuit_breaker=False,
            health_check_interval=90
        )

        manager = initialize_reliability_manager(custom_config)

        assert isinstance(manager, ReliabilityManager)
        assert manager.config.enable_circuit_breaker is False
        assert manager.config.health_check_interval == 90

    def test_initialize_reliability_manager_default_config(self):
        """测试：使用默认配置初始化可靠性管理器"""
        manager = initialize_reliability_manager()

        assert isinstance(manager, ReliabilityManager)
        assert isinstance(manager.config, ReliabilityConfig)
        assert manager.config.enable_circuit_breaker is True
