"""
MarketPrism 告警管理器

核心告警管理器，负责：
- 告警的创建、更新、解决
- 告警规则的管理和评估
- 告警聚合和去重
- 通知分发
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Callable, Any
from collections import defaultdict
import structlog

from .alert_types import (
    Alert, AlertStatus, AlertSeverity, AlertCategory,
    SystemAlert, BusinessAlert, PerformanceAlert,
    AlertRule, AlertPriority
)
from .alert_aggregator import AlertAggregator, AlertDeduplicator
from .notification_manager import NotificationManager
from .anomaly_detector import AnomalyDetector


logger = structlog.get_logger(__name__)


class AlertManager:
    """智能告警管理器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # 告警存储
        self.active_alerts: Dict[str, Alert] = {}
        self.resolved_alerts: Dict[str, Alert] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        
        # 组件初始化
        self.aggregator = AlertAggregator()
        self.deduplicator = AlertDeduplicator()
        self.notification_manager = NotificationManager(self.config.get('notifications', {}))
        self.anomaly_detector = AnomalyDetector()
        
        # 统计信息
        self.stats = {
            'total_alerts': 0,
            'active_alerts': 0,
            'resolved_alerts': 0,
            'suppressed_alerts': 0,
            'notifications_sent': 0
        }
        
        # 回调函数
        self.alert_callbacks: List[Callable[[Alert], None]] = []
        
        # 运行状态
        self.is_running = False
        self._background_tasks: Set[asyncio.Task] = set()
        
        logger.info("告警管理器初始化完成")
    
    async def start(self) -> None:
        """启动告警管理器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动后台任务
        await self._start_background_tasks()
        
        logger.info("告警管理器已启动")
    
    async def stop(self) -> None:
        """停止告警管理器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 停止后台任务
        for task in self._background_tasks:
            task.cancel()
        
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        
        logger.info("告警管理器已停止")
    
    async def _start_background_tasks(self) -> None:
        """启动后台任务"""
        # 告警评估任务
        task1 = asyncio.create_task(self._alert_evaluation_loop())
        self._background_tasks.add(task1)
        
        # 告警清理任务
        task2 = asyncio.create_task(self._alert_cleanup_loop())
        self._background_tasks.add(task2)
        
        # 统计更新任务
        task3 = asyncio.create_task(self._stats_update_loop())
        self._background_tasks.add(task3)
    
    def create_alert(
        self,
        name: str,
        description: str,
        severity: AlertSeverity,
        category: AlertCategory = AlertCategory.SYSTEM,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Alert:
        """创建告警"""
        
        # 根据类别创建不同类型的告警
        if category == AlertCategory.SYSTEM:
            alert = SystemAlert(
                name=name,
                description=description,
                severity=severity,
                category=category,
                metadata=metadata or {},
                **kwargs
            )
        elif category == AlertCategory.BUSINESS:
            alert = BusinessAlert(
                name=name,
                description=description,
                severity=severity,
                category=category,
                metadata=metadata or {},
                **kwargs
            )
        elif category == AlertCategory.PERFORMANCE:
            alert = PerformanceAlert(
                name=name,
                description=description,
                severity=severity,
                category=category,
                metadata=metadata or {},
                **kwargs
            )
        else:
            alert = Alert(
                name=name,
                description=description,
                severity=severity,
                category=category,
                metadata=metadata or {},
                **kwargs
            )
        
        # 去重检查
        if not self.deduplicator.should_create_alert(alert, list(self.active_alerts.values())):
            logger.debug("告警被去重过滤", alert_name=name)
            return None
        
        # 存储告警
        self.active_alerts[alert.id] = alert
        self.stats['total_alerts'] += 1
        self.stats['active_alerts'] += 1
        
        logger.info(
            "创建告警",
            alert_id=alert.id,
            name=name,
            severity=severity.value,
            category=category.value
        )
        
        # 触发回调
        self._trigger_callbacks(alert)
        
        # 异步发送通知
        asyncio.create_task(self._send_notification(alert))
        
        return alert
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """获取告警"""
        return self.active_alerts.get(alert_id) or self.resolved_alerts.get(alert_id)
    
    def get_active_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        category: Optional[AlertCategory] = None
    ) -> List[Alert]:
        """获取活跃告警列表"""
        alerts = list(self.active_alerts.values())
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        if category:
            alerts = [a for a in alerts if a.category == category]
        
        return sorted(alerts, key=lambda x: x.created_at, reverse=True)
    
    def acknowledge_alert(self, alert_id: str, assignee: str) -> bool:
        """确认告警"""
        alert = self.active_alerts.get(alert_id)
        if not alert:
            return False
        
        alert.acknowledge(assignee)
        
        logger.info("告警已确认", alert_id=alert_id, assignee=assignee)
        return True
    
    def resolve_alert(self, alert_id: str, resolution_notes: str = None) -> bool:
        """解决告警"""
        alert = self.active_alerts.get(alert_id)
        if not alert:
            return False
        
        alert.resolve(resolution_notes)
        
        # 移动到已解决列表
        self.resolved_alerts[alert_id] = alert
        del self.active_alerts[alert_id]
        
        self.stats['active_alerts'] -= 1
        self.stats['resolved_alerts'] += 1
        
        logger.info("告警已解决", alert_id=alert_id, notes=resolution_notes)
        return True
    
    def suppress_alert(self, alert_id: str) -> bool:
        """抑制告警"""
        alert = self.active_alerts.get(alert_id)
        if not alert:
            return False
        
        alert.suppress()
        self.stats['suppressed_alerts'] += 1
        
        logger.info("告警已抑制", alert_id=alert_id)
        return True
    
    def add_alert_rule(self, rule: AlertRule) -> None:
        """添加告警规则"""
        self.alert_rules[rule.id] = rule
        logger.info("添加告警规则", rule_id=rule.id, name=rule.name)
    
    def remove_alert_rule(self, rule_id: str) -> bool:
        """移除告警规则"""
        if rule_id in self.alert_rules:
            del self.alert_rules[rule_id]
            logger.info("移除告警规则", rule_id=rule_id)
            return True
        return False
    
    def add_callback(self, callback: Callable[[Alert], None]) -> None:
        """添加告警回调函数"""
        self.alert_callbacks.append(callback)
    
    def _trigger_callbacks(self, alert: Alert) -> None:
        """触发告警回调"""
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error("告警回调执行失败", error=str(e), alert_id=alert.id)
    
    async def _send_notification(self, alert: Alert) -> None:
        """发送告警通知"""
        try:
            await self.notification_manager.send_alert_notification(alert)
            self.stats['notifications_sent'] += 1
        except Exception as e:
            logger.error("发送告警通知失败", error=str(e), alert_id=alert.id)
    
    async def _alert_evaluation_loop(self) -> None:
        """告警评估循环"""
        while self.is_running:
            try:
                # 这里可以添加基于规则的告警评估逻辑
                await asyncio.sleep(30)  # 每30秒评估一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("告警评估循环异常", error=str(e))
                await asyncio.sleep(60)
    
    async def _alert_cleanup_loop(self) -> None:
        """告警清理循环"""
        while self.is_running:
            try:
                await self._cleanup_old_alerts()
                await asyncio.sleep(3600)  # 每小时清理一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("告警清理循环异常", error=str(e))
                await asyncio.sleep(3600)
    
    async def _cleanup_old_alerts(self) -> None:
        """清理旧告警"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
        
        # 清理已解决的旧告警
        to_remove = []
        for alert_id, alert in self.resolved_alerts.items():
            if alert.resolved_at and alert.resolved_at < cutoff_time:
                to_remove.append(alert_id)
        
        for alert_id in to_remove:
            del self.resolved_alerts[alert_id]
        
        if to_remove:
            logger.info("清理旧告警", count=len(to_remove))
    
    async def _stats_update_loop(self) -> None:
        """统计更新循环"""
        while self.is_running:
            try:
                self._update_stats()
                await asyncio.sleep(60)  # 每分钟更新一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("统计更新循环异常", error=str(e))
                await asyncio.sleep(60)
    
    def _update_stats(self) -> None:
        """更新统计信息"""
        self.stats['active_alerts'] = len(self.active_alerts)
        self.stats['resolved_alerts'] = len(self.resolved_alerts)
        
        # 按严重程度统计
        severity_stats = defaultdict(int)
        for alert in self.active_alerts.values():
            severity_stats[alert.severity.value] += 1
        
        self.stats['by_severity'] = dict(severity_stats)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()


# 全局告警管理器实例
_global_alert_manager: Optional[AlertManager] = None


def get_global_alert_manager() -> AlertManager:
    """获取全局告警管理器"""
    global _global_alert_manager
    if _global_alert_manager is None:
        _global_alert_manager = AlertManager()
    return _global_alert_manager
