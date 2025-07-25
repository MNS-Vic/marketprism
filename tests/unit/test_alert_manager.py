"""
MarketPrism 告警管理器单元测试
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.observability.alerting.alert_manager import AlertManager
from core.observability.alerting.alert_types import (
    Alert, AlertSeverity, AlertCategory, AlertStatus
)


class TestAlertManager:
    """告警管理器测试类"""
    
    @pytest.fixture
    async def alert_manager(self):
        """创建告警管理器实例"""
        config = {
            'notifications': {
                'channels': {
                    'email': {
                        'enabled': False
                    }
                }
            }
        }
        manager = AlertManager(config)
        await manager.start()
        yield manager
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_create_alert(self, alert_manager):
        """测试创建告警"""
        alert = alert_manager.create_alert(
            name="测试告警",
            description="这是一个测试告警",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.SYSTEM
        )
        
        assert alert is not None
        assert alert.name == "测试告警"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.category == AlertCategory.SYSTEM
        assert alert.status == AlertStatus.ACTIVE
        assert alert.id in alert_manager.active_alerts
    
    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, alert_manager):
        """测试确认告警"""
        alert = alert_manager.create_alert(
            name="测试告警",
            description="测试描述",
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.BUSINESS
        )
        
        success = alert_manager.acknowledge_alert(alert.id, "test_user")
        
        assert success is True
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.assignee == "test_user"
    
    @pytest.mark.asyncio
    async def test_resolve_alert(self, alert_manager):
        """测试解决告警"""
        alert = alert_manager.create_alert(
            name="测试告警",
            description="测试描述",
            severity=AlertSeverity.LOW,
            category=AlertCategory.PERFORMANCE
        )
        
        success = alert_manager.resolve_alert(alert.id, "问题已修复")
        
        assert success is True
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolution_notes == "问题已修复"
        assert alert.id not in alert_manager.active_alerts
        assert alert.id in alert_manager.resolved_alerts
    
    @pytest.mark.asyncio
    async def test_suppress_alert(self, alert_manager):
        """测试抑制告警"""
        alert = alert_manager.create_alert(
            name="测试告警",
            description="测试描述",
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.SECURITY
        )
        
        success = alert_manager.suppress_alert(alert.id)
        
        assert success is True
        assert alert.status == AlertStatus.SUPPRESSED
    
    @pytest.mark.asyncio
    async def test_get_active_alerts_by_severity(self, alert_manager):
        """测试按严重程度获取活跃告警"""
        # 创建不同严重程度的告警
        alert1 = alert_manager.create_alert(
            name="严重告警",
            description="严重问题",
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.SYSTEM
        )
        
        alert2 = alert_manager.create_alert(
            name="高级告警",
            description="高级问题",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.SYSTEM
        )
        
        alert3 = alert_manager.create_alert(
            name="中级告警",
            description="中级问题",
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.SYSTEM
        )
        
        # 获取严重告警
        critical_alerts = alert_manager.get_active_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical_alerts) == 1
        assert critical_alerts[0].id == alert1.id
        
        # 获取高级告警
        high_alerts = alert_manager.get_active_alerts(severity=AlertSeverity.HIGH)
        assert len(high_alerts) == 1
        assert high_alerts[0].id == alert2.id
    
    @pytest.mark.asyncio
    async def test_get_active_alerts_by_category(self, alert_manager):
        """测试按类别获取活跃告警"""
        # 创建不同类别的告警
        alert1 = alert_manager.create_alert(
            name="系统告警",
            description="系统问题",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.SYSTEM
        )
        
        alert2 = alert_manager.create_alert(
            name="业务告警",
            description="业务问题",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.BUSINESS
        )
        
        # 获取系统告警
        system_alerts = alert_manager.get_active_alerts(category=AlertCategory.SYSTEM)
        assert len(system_alerts) == 1
        assert system_alerts[0].id == alert1.id
        
        # 获取业务告警
        business_alerts = alert_manager.get_active_alerts(category=AlertCategory.BUSINESS)
        assert len(business_alerts) == 1
        assert business_alerts[0].id == alert2.id
    
    @pytest.mark.asyncio
    async def test_alert_callbacks(self, alert_manager):
        """测试告警回调"""
        callback_called = False
        callback_alert = None
        
        def test_callback(alert):
            nonlocal callback_called, callback_alert
            callback_called = True
            callback_alert = alert
        
        alert_manager.add_callback(test_callback)
        
        alert = alert_manager.create_alert(
            name="回调测试告警",
            description="测试回调功能",
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.SYSTEM
        )
        
        assert callback_called is True
        assert callback_alert is not None
        assert callback_alert.id == alert.id
    
    @pytest.mark.asyncio
    async def test_alert_statistics(self, alert_manager):
        """测试告警统计"""
        # 创建多个告警
        alert1 = alert_manager.create_alert(
            name="告警1",
            description="描述1",
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.SYSTEM
        )
        
        alert2 = alert_manager.create_alert(
            name="告警2",
            description="描述2",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.BUSINESS
        )
        
        alert3 = alert_manager.create_alert(
            name="告警3",
            description="描述3",
            severity=AlertSeverity.MEDIUM,
            category=AlertCategory.PERFORMANCE
        )
        
        # 解决一个告警
        alert_manager.resolve_alert(alert3.id, "已解决")
        
        # 获取统计信息
        stats = alert_manager.get_stats()
        
        assert stats['total_alerts'] == 3
        assert stats['active_alerts'] == 2
        assert stats['resolved_alerts'] == 1
    
    @pytest.mark.asyncio
    async def test_alert_not_found_operations(self, alert_manager):
        """测试对不存在告警的操作"""
        fake_id = "non-existent-id"
        
        # 测试确认不存在的告警
        success = alert_manager.acknowledge_alert(fake_id, "test_user")
        assert success is False
        
        # 测试解决不存在的告警
        success = alert_manager.resolve_alert(fake_id, "test notes")
        assert success is False
        
        # 测试抑制不存在的告警
        success = alert_manager.suppress_alert(fake_id)
        assert success is False
        
        # 测试获取不存在的告警
        alert = alert_manager.get_alert(fake_id)
        assert alert is None
    
    @pytest.mark.asyncio
    async def test_alert_duration(self, alert_manager):
        """测试告警持续时间"""
        alert = alert_manager.create_alert(
            name="持续时间测试",
            description="测试持续时间计算",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.SYSTEM
        )
        
        # 等待一小段时间
        await asyncio.sleep(0.1)
        
        # 获取持续时间
        duration = alert.get_duration()
        assert duration is not None
        assert duration > 0
        
        # 解决告警
        alert_manager.resolve_alert(alert.id, "测试完成")
        
        # 再次获取持续时间
        final_duration = alert.get_duration()
        assert final_duration is not None
        assert final_duration >= duration
    
    @pytest.mark.asyncio
    async def test_alert_manager_lifecycle(self):
        """测试告警管理器生命周期"""
        manager = AlertManager()
        
        # 测试启动
        await manager.start()
        assert manager.is_running is True
        
        # 测试停止
        await manager.stop()
        assert manager.is_running is False
        
        # 测试重复启动
        await manager.start()
        assert manager.is_running is True
        
        # 测试重复停止
        await manager.stop()
        await manager.stop()  # 应该不会出错
        assert manager.is_running is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
