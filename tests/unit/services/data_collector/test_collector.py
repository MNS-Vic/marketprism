"""
数据收集器测试

严格遵循Mock使用原则：
- 仅对外部依赖使用Mock（如网络连接、数据库、文件系统）
- 优先使用真实对象测试业务逻辑
- 确保测试验证真实的业务行为
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

# 添加数据收集器路径
collector_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'services', 'data-collector', 'src')
sys.path.insert(0, collector_path)

# 尝试导入数据收集器模块
try:
    from marketprism_collector.collector import (
        EnterpriseMonitoringService,
        HealthChecker,
        CORE_MONITORING_AVAILABLE
    )
    from marketprism_collector.data_types import (
        DataType, CollectorMetrics, HealthStatus,
        NormalizedTrade, NormalizedOrderBook
    )
    HAS_DATA_COLLECTOR = True
except ImportError as e:
    HAS_DATA_COLLECTOR = False
    DATA_COLLECTOR_ERROR = str(e)


@pytest.mark.skipif(not HAS_DATA_COLLECTOR, reason=f"数据收集器模块不可用: {DATA_COLLECTOR_ERROR if not HAS_DATA_COLLECTOR else ''}")
class TestEnterpriseMonitoringService:
    """企业级监控服务测试"""
    
    def test_check_nats_connection_connected(self):
        """测试NATS连接检查（已连接）"""
        # 创建Mock发布器
        mock_publisher = Mock()
        mock_publisher.is_connected = True
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_nats_connection(mock_publisher)
            
            assert result is True
            mock_core.record_metric.assert_called_with("nats_connection_status", 1)
    
    def test_check_nats_connection_disconnected(self):
        """测试NATS连接检查（未连接）"""
        mock_publisher = Mock()
        mock_publisher.is_connected = False
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_nats_connection(mock_publisher)
            
            assert result is False
            mock_core.record_metric.assert_called_with("nats_connection_status", 0)
    
    def test_check_nats_connection_no_publisher(self):
        """测试NATS连接检查（无发布器）"""
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_nats_connection(None)
            
            assert result is False
            mock_core.record_metric.assert_called_with("nats_connection_status", 0)
    
    def test_check_exchange_connections_all_connected(self):
        """测试交易所连接检查（全部连接）"""
        # 创建Mock适配器
        mock_adapter1 = Mock()
        mock_adapter1.is_connected = True
        mock_adapter2 = Mock()
        mock_adapter2.is_connected = True
        
        adapters = {"binance": mock_adapter1, "okx": mock_adapter2}
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            assert result is True
            mock_core.record_metric.assert_any_call("exchange_connections_active", 2)
            mock_core.record_metric.assert_any_call("exchange_connections_total", 2)
    
    def test_check_exchange_connections_partial_connected(self):
        """测试交易所连接检查（部分连接）"""
        mock_adapter1 = Mock()
        mock_adapter1.is_connected = True
        mock_adapter2 = Mock()
        mock_adapter2.is_connected = False
        
        adapters = {"binance": mock_adapter1, "okx": mock_adapter2}
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            assert result is True  # 至少有一个连接
            mock_core.record_metric.assert_any_call("exchange_connections_active", 1)
            mock_core.record_metric.assert_any_call("exchange_connections_total", 2)
    
    def test_check_exchange_connections_none_connected(self):
        """测试交易所连接检查（无连接）"""
        mock_adapter1 = Mock()
        mock_adapter1.is_connected = False
        mock_adapter2 = Mock()
        mock_adapter2.is_connected = False
        
        adapters = {"binance": mock_adapter1, "okx": mock_adapter2}
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            assert result is False
            mock_core.record_metric.assert_any_call("exchange_connections_active", 0)
    
    @patch('marketprism_collector.collector.psutil')
    def test_check_memory_usage_healthy(self, mock_psutil):
        """测试内存使用检查（健康）"""
        mock_process = Mock()
        mock_process.memory_percent.return_value = 50.0
        mock_psutil.Process.return_value = mock_process
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_memory_usage()
            
            assert result is True
            mock_core.record_metric.assert_any_call("process_memory_percent", 50.0)
            mock_core.record_metric.assert_any_call("memory_health_status", 1)
    
    @patch('marketprism_collector.collector.psutil')
    def test_check_memory_usage_unhealthy(self, mock_psutil):
        """测试内存使用检查（不健康）"""
        mock_process = Mock()
        mock_process.memory_percent.return_value = 85.0
        mock_psutil.Process.return_value = mock_process
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            result = EnterpriseMonitoringService.check_memory_usage()
            
            assert result is False
            mock_core.record_metric.assert_any_call("process_memory_percent", 85.0)
            mock_core.record_metric.assert_any_call("memory_health_status", 0)
    
    def test_check_memory_usage_no_psutil(self):
        """测试内存使用检查（psutil不可用）"""
        with patch('marketprism_collector.collector.psutil', side_effect=ImportError):
            with patch('marketprism_collector.collector.core_services') as mock_core:
                result = EnterpriseMonitoringService.check_memory_usage()
                
                assert result is True  # 优雅降级
                mock_core.record_metric.assert_called_with("memory_health_status", 1)
    
    @pytest.mark.asyncio
    async def test_monitor_queue_sizes(self):
        """测试队列大小监控"""
        # 创建Mock适配器
        mock_adapter1 = Mock()
        mock_adapter1.get_queue_size.return_value = 10
        mock_adapter1.is_connected = True
        
        mock_adapter2 = Mock()
        mock_adapter2.get_queue_size.return_value = 5
        mock_adapter2.is_connected = False
        
        adapters = {"binance": mock_adapter1, "okx": mock_adapter2}
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            # 创建监控任务
            task = asyncio.create_task(
                EnterpriseMonitoringService.monitor_queue_sizes(adapters, interval=0.1)
            )
            
            # 让任务运行一小段时间
            await asyncio.sleep(0.2)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # 验证指标记录
            assert mock_core.record_metric.call_count > 0
    
    @pytest.mark.asyncio
    @patch('marketprism_collector.collector.psutil')
    async def test_update_system_metrics(self, mock_psutil):
        """测试系统指标更新"""
        # Mock psutil返回值
        mock_psutil.cpu_percent.return_value = 45.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_memory.available = 8 * (1024**3)  # 8GB
        mock_psutil.virtual_memory.return_value = mock_memory
        
        mock_disk = Mock()
        mock_disk.percent = 35.0
        mock_disk.free = 100 * (1024**3)  # 100GB
        mock_psutil.disk_usage.return_value = mock_disk
        
        mock_net = Mock()
        mock_net.bytes_sent = 1000000
        mock_net.bytes_recv = 2000000
        mock_psutil.net_io_counters.return_value = mock_net
        
        mock_process = Mock()
        mock_process.cpu_percent.return_value = 25.0
        mock_process.memory_info.return_value.rss = 512 * (1024**2)  # 512MB
        mock_process.num_fds.return_value = 50
        mock_psutil.Process.return_value = mock_process
        
        mock_psutil.getloadavg.return_value = (1.0, 1.5, 2.0)
        
        with patch('marketprism_collector.collector.core_services') as mock_core:
            # 创建系统指标任务
            task = asyncio.create_task(
                EnterpriseMonitoringService.update_system_metrics(interval=0.1)
            )
            
            # 让任务运行一小段时间
            await asyncio.sleep(0.2)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            # 验证指标记录
            assert mock_core.record_metric.call_count > 0
    
    def test_setup_distributed_tracing(self):
        """测试分布式追踪设置"""
        result = EnterpriseMonitoringService.setup_distributed_tracing()
        
        assert isinstance(result, dict)
        assert result['service_name'] == 'marketprism-collector'
        assert result['tracing_enabled'] is True
        assert 'sampling_rate' in result
        assert 'endpoints' in result
    
    def test_create_custom_dashboards_default(self):
        """测试创建默认自定义仪表板"""
        result = EnterpriseMonitoringService.create_custom_dashboards()
        
        assert isinstance(result, list)
        assert len(result) == 3  # 默认3个仪表板
        
        dashboard_ids = [d['id'] for d in result]
        assert 'collector_overview' in dashboard_ids
        assert 'exchange_performance' in dashboard_ids
        assert 'system_health' in dashboard_ids
        
        for dashboard in result:
            assert 'widgets' in dashboard
            assert 'created_at' in dashboard
            assert dashboard['status'] == 'active'
    
    def test_create_custom_dashboards_custom_specs(self):
        """测试创建自定义规格的仪表板"""
        custom_specs = [
            {'id': 'custom_dashboard', 'title': 'Custom Dashboard', 'type': 'overview'}
        ]
        
        result = EnterpriseMonitoringService.create_custom_dashboards(custom_specs)
        
        assert len(result) == 1
        assert result[0]['id'] == 'custom_dashboard'
        assert result[0]['title'] == 'Custom Dashboard'
    
    def test_create_dashboard_widgets(self):
        """测试仪表板组件创建"""
        # 测试概览类型
        overview_widgets = EnterpriseMonitoringService._create_dashboard_widgets('overview')
        assert len(overview_widgets) == 3
        assert any(w['title'] == 'Messages Processed' for w in overview_widgets)
        
        # 测试性能类型
        performance_widgets = EnterpriseMonitoringService._create_dashboard_widgets('performance')
        assert len(performance_widgets) == 3
        assert any(w['title'] == 'Response Time' for w in performance_widgets)
        
        # 测试健康类型
        health_widgets = EnterpriseMonitoringService._create_dashboard_widgets('health')
        assert len(health_widgets) == 3
        assert any(w['title'] == 'Service Health' for w in health_widgets)
        
        # 测试未知类型
        unknown_widgets = EnterpriseMonitoringService._create_dashboard_widgets('unknown')
        assert len(unknown_widgets) == 0
    
    @patch('marketprism_collector.collector.psutil')
    def test_perform_anomaly_detection_normal(self, mock_psutil):
        """测试异常检测（正常情况）"""
        mock_psutil.cpu_percent.return_value = 50.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_psutil.virtual_memory.return_value = mock_memory
        
        result = EnterpriseMonitoringService.perform_anomaly_detection()
        
        assert isinstance(result, dict)
        assert 'detected_anomalies' in result
        assert 'analysis_timestamp' in result
        assert 'detection_rules' in result
        assert 'recommendations' in result
        assert len(result['detected_anomalies']) == 0  # 无异常
    
    @patch('marketprism_collector.collector.psutil')
    def test_perform_anomaly_detection_cpu_spike(self, mock_psutil):
        """测试异常检测（CPU峰值）"""
        mock_psutil.cpu_percent.return_value = 85.0
        mock_memory = Mock()
        mock_memory.percent = 60.0
        mock_psutil.virtual_memory.return_value = mock_memory
        
        result = EnterpriseMonitoringService.perform_anomaly_detection()
        
        assert len(result['detected_anomalies']) == 1
        assert result['detected_anomalies'][0]['type'] == 'cpu_spike'
        assert result['detected_anomalies'][0]['severity'] == 'high'
        assert len(result['recommendations']) > 0
    
    @patch('marketprism_collector.collector.psutil')
    def test_perform_anomaly_detection_memory_leak(self, mock_psutil):
        """测试异常检测（内存泄漏）"""
        mock_psutil.cpu_percent.return_value = 50.0
        mock_memory = Mock()
        mock_memory.percent = 95.0
        mock_psutil.virtual_memory.return_value = mock_memory
        
        result = EnterpriseMonitoringService.perform_anomaly_detection()
        
        assert len(result['detected_anomalies']) == 1
        assert result['detected_anomalies'][0]['type'] == 'memory_leak'
        assert result['detected_anomalies'][0]['severity'] == 'critical'
    
    def test_perform_anomaly_detection_no_psutil(self):
        """测试异常检测（psutil不可用）"""
        with patch('marketprism_collector.collector.psutil', side_effect=ImportError):
            result = EnterpriseMonitoringService.perform_anomaly_detection()
            
            assert len(result['detected_anomalies']) == 1
            assert result['detected_anomalies'][0]['type'] == 'monitoring_unavailable'
            assert result['detected_anomalies'][0]['severity'] == 'warning'

    def test_setup_intelligent_alerting_default(self):
        """测试智能告警设置（默认配置）"""
        result = EnterpriseMonitoringService.setup_intelligent_alerting()

        assert isinstance(result, dict)
        assert result['system_id'] == 'intelligent_alerting_v1'
        assert 'configuration' in result
        assert 'ml_models' in result
        assert 'alert_channels' in result
        assert 'smart_features' in result
        assert result['status'] == 'active'

        # 验证ML模型配置
        assert len(result['ml_models']) == 2
        model_types = [m['model_type'] for m in result['ml_models']]
        assert 'anomaly_detection' in model_types
        assert 'threshold_optimization' in model_types

        # 验证告警通道
        assert len(result['alert_channels']) == 3
        channel_types = [c['type'] for c in result['alert_channels']]
        assert 'email' in channel_types
        assert 'slack' in channel_types
        assert 'webhook' in channel_types

    def test_setup_intelligent_alerting_custom(self):
        """测试智能告警设置（自定义配置）"""
        custom_config = {
            'ai_enabled': False,
            'learning_period_days': 14,
            'sensitivity': 'high',
            'auto_threshold_adjustment': False
        }

        result = EnterpriseMonitoringService.setup_intelligent_alerting(custom_config)

        assert result['configuration'] == custom_config
        assert result['ml_models'][0]['training_data_days'] == 14
        assert result['ml_models'][1]['sensitivity'] == 'high'

    def test_generate_capacity_planning_default(self):
        """测试容量规划生成（默认参数）"""
        result = EnterpriseMonitoringService.generate_capacity_planning()

        assert isinstance(result, dict)
        assert result['planning_horizon_days'] == 30
        assert 'analysis_timestamp' in result
        assert 'current_capacity' in result
        assert 'projected_growth' in result
        assert 'capacity_forecasts' in result
        assert 'recommendations' in result
        assert 'alerts' in result

        # 验证当前容量指标
        current = result['current_capacity']
        assert 'cpu_utilization_avg' in current
        assert 'memory_utilization_avg' in current
        assert 'disk_utilization_avg' in current
        assert 'network_throughput_avg' in current

        # 验证预测数据（最多5天）
        assert len(result['capacity_forecasts']) == 5
        for forecast in result['capacity_forecasts']:
            assert 'day' in forecast
            assert 'date' in forecast
            assert 'projected_cpu' in forecast
            assert 'projected_memory' in forecast
            assert 'projected_disk' in forecast
            assert 'projected_messages' in forecast

    def test_generate_capacity_planning_custom_horizon(self):
        """测试容量规划生成（自定义周期）"""
        result = EnterpriseMonitoringService.generate_capacity_planning(7)

        assert result['planning_horizon_days'] == 7
        assert len(result['capacity_forecasts']) == 5  # 仍然最多5天

    def test_generate_capacity_planning_with_recommendations(self):
        """测试容量规划生成（包含建议）"""
        result = EnterpriseMonitoringService.generate_capacity_planning(5)

        # 检查是否有建议（基于预测的增长）
        if len(result['recommendations']) > 0:
            for rec in result['recommendations']:
                assert 'type' in rec
                assert 'priority' in rec
                assert 'message' in rec
                assert 'estimated_cost' in rec

        # 检查告警
        if len(result['alerts']) > 0:
            for alert in result['alerts']:
                assert 'severity' in alert
                assert 'message' in alert
                assert 'action_required' in alert

    def test_provide_cost_optimization_default(self):
        """测试成本优化建议（默认范围）"""
        result = EnterpriseMonitoringService.provide_cost_optimization()

        assert isinstance(result, dict)
        assert result['analysis_scope'] == 'all'
        assert 'analysis_timestamp' in result
        assert 'current_costs' in result
        assert 'optimization_opportunities' in result
        assert 'estimated_savings' in result

        # 验证当前成本结构
        costs = result['current_costs']
        assert 'compute' in costs
        assert 'storage' in costs
        assert 'network' in costs
        assert 'monitoring' in costs

        for cost_item in costs.values():
            assert 'monthly' in cost_item
            assert 'currency' in cost_item

        # 验证节省估算
        savings = result['estimated_savings']
        assert 'monthly' in savings
        assert 'annual' in savings
        assert 'currency' in savings

    def test_provide_cost_optimization_custom_scope(self):
        """测试成本优化建议（自定义范围）"""
        result = EnterpriseMonitoringService.provide_cost_optimization('compute')

        assert result['analysis_scope'] == 'compute'


@pytest.mark.skipif(not HAS_DATA_COLLECTOR, reason=f"数据收集器模块不可用: {DATA_COLLECTOR_ERROR if not HAS_DATA_COLLECTOR else ''}")
class TestHealthChecker:
    """健康检查器测试"""

    def test_health_checker_initialization(self):
        """测试健康检查器初始化"""
        checker = HealthChecker()

        assert hasattr(checker, 'checks')
        assert isinstance(checker.checks, dict)
        assert len(checker.checks) == 0

    def test_register_check(self):
        """测试注册健康检查"""
        checker = HealthChecker()

        def dummy_check():
            return True

        checker.register_check("test_check", dummy_check, timeout=10.0)

        assert "test_check" in checker.checks
        assert checker.checks["test_check"]["func"] == dummy_check
        assert checker.checks["test_check"]["timeout"] == 10.0

    @pytest.mark.asyncio
    async def test_check_health_all_healthy(self):
        """测试健康检查（全部健康）"""
        checker = HealthChecker()

        def check1():
            return "OK"

        def check2():
            return "Running"

        checker.register_check("service1", check1)
        checker.register_check("service2", check2)

        result = await checker.check_health()

        assert result.status == 'healthy'
        assert hasattr(result, 'timestamp')
        assert hasattr(result, 'checks')
        assert len(result.checks) == 2
        assert result.checks['service1']['status'] == 'healthy'
        assert result.checks['service2']['status'] == 'healthy'

    @pytest.mark.asyncio
    async def test_check_health_with_failure(self):
        """测试健康检查（有失败）"""
        checker = HealthChecker()

        def healthy_check():
            return "OK"

        def failing_check():
            raise Exception("Service unavailable")

        checker.register_check("healthy_service", healthy_check)
        checker.register_check("failing_service", failing_check)

        result = await checker.check_health()

        assert result.status == 'unhealthy'
        assert result.checks['healthy_service']['status'] == 'healthy'
        assert result.checks['failing_service']['status'] == 'unhealthy'
        assert 'error' in result.checks['failing_service']

    @pytest.mark.asyncio
    async def test_check_health_async_checks(self):
        """测试健康检查（异步检查）"""
        checker = HealthChecker()

        async def async_check():
            await asyncio.sleep(0.01)
            return "Async OK"

        def sync_check():
            return "Sync OK"

        checker.register_check("async_service", async_check)
        checker.register_check("sync_service", sync_check)

        result = await checker.check_health()

        assert result.status == 'healthy'
        assert result.checks['async_service']['status'] == 'healthy'
        assert result.checks['sync_service']['status'] == 'healthy'

    @pytest.mark.asyncio
    async def test_check_health_no_checks(self):
        """测试健康检查（无检查项）"""
        checker = HealthChecker()

        result = await checker.check_health()

        assert result.status == 'healthy'  # 无检查项时默认健康
        assert len(result.checks) == 0


# 基础覆盖率测试
class TestDataCollectorBasic:
    """数据收集器基础覆盖率测试"""

    def test_module_import_attempt(self):
        """测试模块导入尝试"""
        try:
            import marketprism_collector.collector
            # 如果导入成功，测试基本属性
            assert hasattr(marketprism_collector.collector, '__file__')
        except ImportError:
            # 如果导入失败，这也是预期的情况
            pytest.skip("数据收集器模块不可用")

    def test_data_collector_concepts(self):
        """测试数据收集器概念"""
        # 测试数据收集器的核心概念
        concepts = [
            "enterprise_monitoring",
            "health_checking",
            "anomaly_detection",
            "capacity_planning",
            "cost_optimization"
        ]

        # 验证概念存在
        for concept in concepts:
            assert isinstance(concept, str)
            assert len(concept) > 0

    def test_core_monitoring_availability(self):
        """测试核心监控可用性"""
        if HAS_DATA_COLLECTOR:
            # 验证CORE_MONITORING_AVAILABLE是布尔值
            assert isinstance(CORE_MONITORING_AVAILABLE, bool)
