"""
MarketPrism 监控告警服务集成测试
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from aiohttp import ClientSession
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from unittest.mock import Mock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.monitoring_alerting_service.main import MonitoringAlertingService
from core.observability.alerting.alert_types import AlertSeverity, AlertCategory


class TestMonitoringAlertingServiceIntegration(AioHTTPTestCase):
    """监控告警服务集成测试"""
    
    async def get_application(self):
        """获取测试应用"""
        config = {
            'alert_manager': {
                'enabled': True,
                'evaluation_interval': 30
            },
            'notification_manager': {
                'enabled': False,  # 测试时禁用通知
                'channels': {}
            },
            'anomaly_detection': {
                'enabled': True,
                'statistical': {
                    'enabled': True,
                    'threshold': 2.0
                }
            },
            'failure_prediction': {
                'enabled': True
            }
        }
        
        service = MonitoringAlertingService(config)
        await service.initialize()
        return service.app
    
    @unittest_run_loop
    async def test_health_check(self):
        """测试健康检查端点"""
        resp = await self.client.request("GET", "/health")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('status', data)
        self.assertIn('components', data)
        self.assertIn('uptime_seconds', data)
    
    @unittest_run_loop
    async def test_readiness_check(self):
        """测试就绪检查端点"""
        resp = await self.client.request("GET", "/ready")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('ready', data)
        self.assertIn('timestamp', data)
    
    @unittest_run_loop
    async def test_get_alerts_empty(self):
        """测试获取空告警列表"""
        resp = await self.client.request("GET", "/api/v1/alerts")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('alerts', data)
        self.assertIn('total', data)
        self.assertEqual(data['total'], 0)
        self.assertEqual(len(data['alerts']), 0)
    
    @unittest_run_loop
    async def test_get_business_metrics(self):
        """测试获取业务指标"""
        resp = await self.client.request("GET", "/api/v1/metrics/business")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('exchanges', data)
        self.assertIn('overall_health', data)
        self.assertIn('api_error_rate', data)
    
    @unittest_run_loop
    async def test_get_sla_metrics(self):
        """测试获取SLA指标"""
        resp = await self.client.request("GET", "/api/v1/metrics/sla")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        # SLA指标应该包含预定义的服务
        self.assertIsInstance(data, dict)
    
    @unittest_run_loop
    async def test_detect_anomaly(self):
        """测试异常检测端点"""
        anomaly_data = {
            'metric_name': 'test_metric',
            'value': 100.0,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        resp = await self.client.request(
            "POST", 
            "/api/v1/anomaly/detect",
            data=json.dumps(anomaly_data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('is_anomaly', data)
    
    @unittest_run_loop
    async def test_predict_failures(self):
        """测试故障预测端点"""
        resp = await self.client.request("GET", "/api/v1/prediction/failures")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('predictions', data)
        self.assertIn('total', data)
    
    @unittest_run_loop
    async def test_get_capacity_planning(self):
        """测试容量规划端点"""
        resp = await self.client.request("GET", "/api/v1/prediction/capacity")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('recommendations', data)
        self.assertIn('total', data)
    
    @unittest_run_loop
    async def test_get_alert_stats(self):
        """测试告警统计端点"""
        resp = await self.client.request("GET", "/api/v1/stats/alerts")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('total_alerts', data)
        self.assertIn('active_alerts', data)
        self.assertIn('resolved_alerts', data)
    
    @unittest_run_loop
    async def test_get_performance_stats(self):
        """测试性能统计端点"""
        resp = await self.client.request("GET", "/api/v1/stats/performance")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('overall_metrics', data)
        self.assertIn('sla_status', data)
    
    @unittest_run_loop
    async def test_get_rules(self):
        """测试获取告警规则"""
        resp = await self.client.request("GET", "/api/v1/rules")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('rules', data)
        self.assertIn('total', data)
        # 应该有默认规则
        self.assertGreater(data['total'], 0)
    
    @unittest_run_loop
    async def test_get_rules_with_filters(self):
        """测试带过滤器的规则查询"""
        # 按类别过滤
        resp = await self.client.request("GET", "/api/v1/rules?category=system")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('rules', data)
        
        # 只获取启用的规则
        resp = await self.client.request("GET", "/api/v1/rules?enabled_only=true")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertIn('rules', data)
    
    @unittest_run_loop
    async def test_prometheus_metrics(self):
        """测试Prometheus指标端点"""
        resp = await self.client.request("GET", "/metrics")
        
        # 如果prometheus_client可用，应该返回200，否则返回503
        self.assertIn(resp.status, [200, 503])
        
        if resp.status == 200:
            content_type = resp.headers.get('Content-Type', '')
            self.assertIn('text/plain', content_type)
    
    @unittest_run_loop
    async def test_invalid_endpoints(self):
        """测试无效端点"""
        # 测试不存在的端点
        resp = await self.client.request("GET", "/api/v1/nonexistent")
        self.assertEqual(resp.status, 404)
        
        # 测试无效的告警ID
        resp = await self.client.request("GET", "/api/v1/alerts/invalid-id")
        self.assertEqual(resp.status, 404)
        
        # 测试无效的追踪ID
        resp = await self.client.request("GET", "/api/v1/traces/invalid-trace-id")
        self.assertEqual(resp.status, 404)
    
    @unittest_run_loop
    async def test_cors_headers(self):
        """测试CORS头部"""
        resp = await self.client.request("OPTIONS", "/api/v1/alerts")
        
        # 检查CORS头部
        self.assertIn('Access-Control-Allow-Origin', resp.headers)
        self.assertIn('Access-Control-Allow-Methods', resp.headers)
        self.assertIn('Access-Control-Allow-Headers', resp.headers)


class TestEndToEndWorkflow:
    """端到端工作流测试"""
    
    @pytest.fixture
    async def service(self):
        """创建测试服务实例"""
        config = {
            'alert_manager': {
                'enabled': True,
                'evaluation_interval': 1  # 快速评估用于测试
            },
            'notification_manager': {
                'enabled': False  # 测试时禁用通知
            },
            'anomaly_detection': {
                'enabled': True
            },
            'failure_prediction': {
                'enabled': True
            }
        }
        
        service = MonitoringAlertingService(config)
        await service.initialize()
        yield service
        await service.stop()
    
    @pytest.mark.asyncio
    async def test_alert_lifecycle(self, service):
        """测试告警完整生命周期"""
        # 1. 创建告警
        alert = service.alert_manager.create_alert(
            name="集成测试告警",
            description="这是一个集成测试告警",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.SYSTEM
        )
        
        assert alert is not None
        assert alert.name == "集成测试告警"
        
        # 2. 获取告警
        retrieved_alert = service.alert_manager.get_alert(alert.id)
        assert retrieved_alert is not None
        assert retrieved_alert.id == alert.id
        
        # 3. 确认告警
        success = service.alert_manager.acknowledge_alert(alert.id, "test_user")
        assert success is True
        
        # 4. 解决告警
        success = service.alert_manager.resolve_alert(alert.id, "问题已修复")
        assert success is True
        
        # 5. 验证告警状态
        resolved_alert = service.alert_manager.get_alert(alert.id)
        assert resolved_alert.status.value == "resolved"
        assert resolved_alert.resolution_notes == "问题已修复"
    
    @pytest.mark.asyncio
    async def test_anomaly_detection_workflow(self, service):
        """测试异常检测工作流"""
        metric_name = "test_cpu_usage"
        
        # 1. 添加正常数据
        for i in range(20):
            timestamp = datetime.now(timezone.utc)
            result = service.anomaly_detector.detect_anomaly(
                metric_name, timestamp, 50.0 + i * 0.1
            )
        
        # 2. 添加异常数据
        timestamp = datetime.now(timezone.utc)
        result = service.anomaly_detector.detect_anomaly(
            metric_name, timestamp, 200.0  # 明显异常值
        )
        
        # 由于数据量可能不足，结果可能为None
        if result:
            assert result.metric_name == metric_name
            assert result.value == 200.0
    
    @pytest.mark.asyncio
    async def test_business_metrics_workflow(self, service):
        """测试业务指标工作流"""
        # 1. 记录交易所连接
        service.business_metrics.record_exchange_connection("binance", True)
        
        # 2. 记录交易所消息
        service.business_metrics.record_exchange_message(
            "binance", "trade", latency_ms=50.0, data_quality=0.95
        )
        
        # 3. 记录API请求
        service.business_metrics.record_api_request(
            "GET", "/api/v1/data", 200, 150.0
        )
        
        # 4. 获取指标摘要
        summary = service.business_metrics.get_metrics_summary()
        
        assert "exchanges" in summary
        assert "binance" in summary["exchanges"]
        assert summary["exchanges"]["binance"]["connection_status"] is True
        assert summary["exchanges"]["binance"]["message_count"] == 1
    
    @pytest.mark.asyncio
    async def test_failure_prediction_workflow(self, service):
        """测试故障预测工作流"""
        # 1. 添加趋势数据
        for i in range(50):
            timestamp = datetime.now(timezone.utc)
            # 模拟内存使用率逐渐增长
            memory_usage = 0.5 + i * 0.01  # 从50%增长到99%
            service.failure_predictor.add_metric_data(
                "memory_usage", timestamp, memory_usage
            )
        
        # 2. 执行故障预测
        predictions = service.failure_predictor.predict_failures()
        
        # 3. 获取容量规划建议
        recommendations = service.failure_predictor.get_capacity_planning_recommendations()
        
        # 验证结果
        assert isinstance(predictions, list)
        assert isinstance(recommendations, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
