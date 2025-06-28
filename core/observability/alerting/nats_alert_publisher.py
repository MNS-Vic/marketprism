"""
MarketPrism 告警NATS发布器
实现异步告警流：monitoring-alerting → NATS → notification
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
import nats
from nats.js import JetStreamContext
from nats.js.api import StreamConfig, RetentionPolicy, StorageType
import traceback

from .alert_types import Alert, AlertSeverity, AlertCategory

logger = logging.getLogger(__name__)


class AlertEventType(Enum):
    """告警事件类型"""
    CREATED = "created"
    UPDATED = "updated"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    SUPPRESSED = "suppressed"


class NATSAlertPublisher:
    """NATS告警发布器 - 异步发送告警消息"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        """
        初始化NATS告警发布器
        
        Args:
            nats_url: NATS服务器URL
        """
        self.nats_url = nats_url
        self.nc = None
        self.js = None
        self.is_connected = False
        self.published_count = 0
        self.error_count = 0
        self.last_publish_time = None
        
        # 告警主题配置
        self.alert_subjects = {
            AlertSeverity.CRITICAL: "alerts.critical",
            AlertSeverity.HIGH: "alerts.high",
            AlertSeverity.MEDIUM: "alerts.medium",
            AlertSeverity.LOW: "alerts.low"
        }
        
        # 告警类别主题
        self.category_subjects = {
            AlertCategory.SYSTEM: "alerts.system",
            AlertCategory.PERFORMANCE: "alerts.performance",
            AlertCategory.CAPACITY: "alerts.capacity",
            AlertCategory.SECURITY: "alerts.security",
            AlertCategory.BUSINESS: "alerts.business"
        }
        
        logger.info("NATS告警发布器初始化完成")
    
    async def start(self):
        """启动NATS告警发布器"""
        if self.is_connected:
            logger.warning("NATS告警发布器已连接")
            return
        
        try:
            logger.info(f"连接到NATS服务器: {self.nats_url}")
            
            # 连接到NATS
            self.nc = await nats.connect(
                servers=[self.nats_url],
                name="marketprism-alert-publisher",
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
                error_cb=self._error_callback,
                disconnected_cb=self._disconnected_callback,
                reconnected_cb=self._reconnected_callback
            )
            
            # 获取JetStream上下文
            self.js = self.nc.jetstream()
            
            # 设置告警流
            await self._setup_alert_streams()
            
            self.is_connected = True
            logger.info("✅ NATS告警发布器启动成功")
            
        except Exception as e:
            logger.error(f"❌ NATS告警发布器启动失败: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def stop(self):
        """停止NATS告警发布器"""
        if not self.is_connected:
            return
        
        logger.info("停止NATS告警发布器...")
        
        # 关闭连接
        if self.nc:
            await self.nc.close()
        
        self.is_connected = False
        logger.info("✅ NATS告警发布器已停止")
    
    async def _setup_alert_streams(self):
        """设置告警流"""
        try:
            # 使用简化的流创建方式，参考官方文档
            # 创建或更新告警流
            try:
                await self.js.add_stream(name="ALERTS", subjects=["alerts.>"])
                logger.info("✅ ALERTS流创建成功")
            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    logger.info("ALERTS流已存在")
                else:
                    logger.warning(f"创建ALERTS流时出现问题: {e}")

            # 创建或更新通知流
            try:
                await self.js.add_stream(name="NOTIFICATIONS", subjects=["notifications.>"])
                logger.info("✅ NOTIFICATIONS流创建成功")
            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    logger.info("NOTIFICATIONS流已存在")
                else:
                    logger.warning(f"创建NOTIFICATIONS流时出现问题: {e}")

        except Exception as e:
            logger.error(f"❌ 设置告警流失败: {e}")
            raise
    
    async def publish_alert(self, alert: Alert, event_type: AlertEventType = AlertEventType.CREATED) -> bool:
        """
        发布告警消息
        
        Args:
            alert: 告警对象
            event_type: 事件类型
            
        Returns:
            bool: 发布是否成功
        """
        if not self.is_connected:
            logger.error("NATS未连接，无法发布告警")
            return False
        
        try:
            # 构建告警消息
            alert_message = self._build_alert_message(alert, event_type)
            
            # 确定主题
            subject = self._get_alert_subject(alert, event_type)
            
            # 发布消息
            message_data = json.dumps(alert_message, ensure_ascii=False, default=str)
            
            # 设置消息头
            headers = {
                'alert-id': alert.id,
                'alert-severity': str(alert.severity),
                'alert-category': str(alert.category),
                'event-type': event_type.value,
                'timestamp': datetime.now().isoformat()
            }
            
            # 发布到JetStream
            ack = await self.js.publish(
                subject=subject,
                payload=message_data.encode('utf-8'),
                headers=headers
            )
            
            self.published_count += 1
            self.last_publish_time = datetime.now()
            
            logger.info(
                "告警消息发布成功",
                alert_id=alert.id,
                subject=subject,
                event_type=event_type.value,
                sequence=ack.seq
            )
            
            return True
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"告警消息发布失败: {e}")
            logger.error(f"告警ID: {alert.id}")
            logger.error(traceback.format_exc())
            return False
    
    async def publish_notification_request(self, alert: Alert, channels: List[str], message: str) -> bool:
        """
        发布通知请求
        
        Args:
            alert: 告警对象
            channels: 通知渠道列表
            message: 通知消息
            
        Returns:
            bool: 发布是否成功
        """
        if not self.is_connected:
            logger.error("NATS未连接，无法发布通知请求")
            return False
        
        try:
            # 构建通知请求消息
            notification_message = {
                'alert_id': alert.id,
                'alert_name': alert.name,
                'alert_severity': str(alert.severity),
                'alert_category': str(alert.category),
                'channels': channels,
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'alert_data': {
                    'description': alert.description,
                    'metadata': alert.metadata,
                    'created_at': alert.created_at.isoformat(),
                    'updated_at': alert.updated_at.isoformat() if alert.updated_at else None
                }
            }
            
            # 确定通知主题
            subject = f"notifications.{alert.severity}"
            
            # 发布消息
            message_data = json.dumps(notification_message, ensure_ascii=False, default=str)
            
            # 设置消息头
            headers = {
                'alert-id': alert.id,
                'notification-channels': ','.join(channels),
                'timestamp': datetime.now().isoformat()
            }
            
            # 发布到JetStream
            ack = await self.js.publish(
                subject=subject,
                payload=message_data.encode('utf-8'),
                headers=headers
            )
            
            logger.info(
                "通知请求发布成功",
                alert_id=alert.id,
                subject=subject,
                channels=channels,
                sequence=ack.seq
            )
            
            return True
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"通知请求发布失败: {e}")
            logger.error(f"告警ID: {alert.id}")
            logger.error(traceback.format_exc())
            return False
    
    def _build_alert_message(self, alert: Alert, event_type: AlertEventType) -> Dict[str, Any]:
        """构建告警消息"""
        return {
            'event_type': event_type.value,
            'alert': {
                'id': alert.id,
                'name': alert.name,
                'description': alert.description,
                'severity': str(alert.severity),
                'category': str(alert.category),
                'status': str(alert.status),
                'created_at': alert.created_at.isoformat(),
                'updated_at': alert.updated_at.isoformat() if alert.updated_at else None,
                'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
                'metadata': alert.metadata
            },
            'timestamp': datetime.now().isoformat(),
            'source': 'marketprism-monitoring-alerting'
        }
    
    def _get_alert_subject(self, alert: Alert, event_type: AlertEventType) -> str:
        """获取告警主题"""
        # 基础主题：alerts.{severity}.{event_type}
        base_subject = f"alerts.{alert.severity}.{event_type.value}"

        # 如果是关键告警，添加特殊路由
        if str(alert.severity) == "critical":
            return f"alerts.critical.{event_type.value}"

        return base_subject
    
    async def _error_callback(self, error):
        """NATS错误回调"""
        logger.error(f"NATS错误: {error}")
    
    async def _disconnected_callback(self):
        """NATS断开连接回调"""
        logger.warning("NATS连接已断开")
        self.is_connected = False
    
    async def _reconnected_callback(self):
        """NATS重连回调"""
        logger.info("NATS连接已重新建立")
        self.is_connected = True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取发布器统计信息"""
        return {
            "is_connected": self.is_connected,
            "published_count": self.published_count,
            "error_count": self.error_count,
            "last_publish_time": self.last_publish_time.isoformat() if self.last_publish_time else None,
            "nats_url": self.nats_url
        }
