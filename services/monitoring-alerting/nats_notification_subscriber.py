"""
MarketPrism 通知服务 - NATS订阅器
实现异步告警流：monitoring-alerting → NATS → notification
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import nats
from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy
import traceback

logger = logging.getLogger(__name__)


class NATSNotificationSubscriber:
    """NATS通知订阅器 - 异步接收告警消息并发送通知"""
    
    def __init__(self, notification_handlers: Dict[str, Callable], nats_url: str = "nats://localhost:4222"):
        """
        初始化NATS通知订阅器
        
        Args:
            notification_handlers: 通知处理器字典 {channel_name: handler_function}
            nats_url: NATS服务器URL
        """
        self.notification_handlers = notification_handlers
        self.nats_url = nats_url
        self.nc = None
        self.js = None
        self.subscriptions = []
        self.is_running = False
        self.message_count = 0
        self.error_count = 0
        self.notification_count = 0
        self.last_message_time = None
        
        logger.info("NATS通知订阅器初始化完成")
    
    async def start(self):
        """启动NATS通知订阅器"""
        if self.is_running:
            logger.warning("NATS通知订阅器已在运行")
            return
        
        try:
            logger.info(f"连接到NATS服务器: {self.nats_url}")
            
            # 连接到NATS
            self.nc = await nats.connect(
                servers=[self.nats_url],
                name="marketprism-notification-subscriber",
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
                error_cb=self._error_callback,
                disconnected_cb=self._disconnected_callback,
                reconnected_cb=self._reconnected_callback
            )
            
            # 获取JetStream上下文
            self.js = self.nc.jetstream()
            
            # 设置订阅
            await self._setup_subscriptions()
            
            self.is_running = True
            logger.info("✅ NATS通知订阅器启动成功")
            
        except Exception as e:
            logger.error(f"❌ NATS通知订阅器启动失败: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def stop(self):
        """停止NATS通知订阅器"""
        if not self.is_running:
            return
        
        logger.info("停止NATS通知订阅器...")
        
        # 取消所有订阅
        for subscription in self.subscriptions:
            try:
                await subscription.unsubscribe()
            except Exception as e:
                logger.error(f"取消订阅失败: {e}")
        
        # 关闭连接
        if self.nc:
            await self.nc.close()
        
        self.is_running = False
        logger.info("✅ NATS通知订阅器已停止")
    
    async def _setup_subscriptions(self):
        """设置NATS订阅"""
        try:
            # 确保流存在
            await self._ensure_streams_exist()
            
            # 告警订阅配置
            alert_consumer_config = ConsumerConfig(
                durable_name="notification-alert-consumer",
                deliver_policy=DeliverPolicy.NEW,
                ack_policy=AckPolicy.EXPLICIT,
                max_deliver=3,
                ack_wait=30,
                max_ack_pending=1000
            )
            
            # 订阅告警流
            alert_subscription = await self.js.subscribe(
                subject="alerts.>",
                stream="ALERTS",
                config=alert_consumer_config,
                cb=self._alert_message_handler
            )
            
            self.subscriptions.append(alert_subscription)
            logger.info("✅ 告警订阅设置完成")
            
            # 通知请求订阅配置
            notification_consumer_config = ConsumerConfig(
                durable_name="notification-request-consumer",
                deliver_policy=DeliverPolicy.NEW,
                ack_policy=AckPolicy.EXPLICIT,
                max_deliver=3,
                ack_wait=30,
                max_ack_pending=1000
            )
            
            # 订阅通知请求流
            notification_subscription = await self.js.subscribe(
                subject="notifications.>",
                stream="NOTIFICATIONS",
                config=notification_consumer_config,
                cb=self._notification_message_handler
            )
            
            self.subscriptions.append(notification_subscription)
            logger.info("✅ 通知请求订阅设置完成")
            
        except Exception as e:
            logger.error(f"❌ 设置订阅失败: {e}")
            raise
    
    async def _ensure_streams_exist(self):
        """确保必要的流存在"""
        try:
            # 检查ALERTS流是否存在
            try:
                await self.js.stream_info("ALERTS")
                logger.info("✅ ALERTS流已存在")
            except Exception:
                logger.warning("ALERTS流不存在，等待创建...")
                
            # 检查NOTIFICATIONS流是否存在
            try:
                await self.js.stream_info("NOTIFICATIONS")
                logger.info("✅ NOTIFICATIONS流已存在")
            except Exception:
                logger.warning("NOTIFICATIONS流不存在，等待创建...")
                
        except Exception as e:
            logger.error(f"检查流状态失败: {e}")
    
    async def _alert_message_handler(self, msg):
        """告警消息处理器"""
        try:
            self.message_count += 1
            self.last_message_time = datetime.now()
            
            # 解析消息
            subject = msg.subject
            data = json.loads(msg.data.decode('utf-8'))
            
            # 提取告警信息
            event_type = data.get('event_type')
            alert_data = data.get('alert', {})
            
            logger.info(
                f"收到告警消息: alert_id={alert_data.get('id')}, "
                f"event_type={event_type}, severity={alert_data.get('severity')}, "
                f"subject={subject}"
            )
            
            # 根据事件类型处理告警
            await self._process_alert_event(alert_data, event_type)
            
            await msg.ack()
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"处理告警消息失败: {e}")
            logger.error(f"消息主题: {msg.subject}")
            logger.error(f"消息数据: {msg.data}")
            logger.error(traceback.format_exc())
            
            # 确认消息避免无限重试
            try:
                await msg.ack()
            except Exception:
                pass
    
    async def _notification_message_handler(self, msg):
        """通知请求消息处理器"""
        try:
            self.message_count += 1
            self.last_message_time = datetime.now()
            
            # 解析消息
            subject = msg.subject
            data = json.loads(msg.data.decode('utf-8'))
            
            # 提取通知信息
            alert_id = data.get('alert_id')
            channels = data.get('channels', [])
            message = data.get('message', '')
            alert_data = data.get('alert_data', {})
            
            logger.info(
                f"收到通知请求: alert_id={alert_id}, "
                f"channels={channels}, subject={subject}"
            )
            
            # 处理通知请求
            await self._process_notification_request(alert_id, channels, message, alert_data)
            
            await msg.ack()
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"处理通知请求失败: {e}")
            logger.error(f"消息主题: {msg.subject}")
            logger.error(f"消息数据: {msg.data}")
            logger.error(traceback.format_exc())
            
            # 确认消息避免无限重试
            try:
                await msg.ack()
            except Exception:
                pass
    
    async def _process_alert_event(self, alert_data: Dict[str, Any], event_type: str):
        """处理告警事件"""
        try:
            # 根据告警严重程度确定通知渠道
            severity = alert_data.get('severity', 'medium')
            channels = self._get_channels_for_severity(severity)
            
            # 格式化通知消息
            message = self._format_alert_message(alert_data, event_type)
            
            # 发送通知
            await self._send_notifications(channels, message, alert_data)
            
        except Exception as e:
            logger.error(f"处理告警事件失败: {e}")
            raise
    
    async def _process_notification_request(self, alert_id: str, channels: List[str], message: str, alert_data: Dict[str, Any]):
        """处理通知请求"""
        try:
            # 发送通知
            await self._send_notifications(channels, message, alert_data)
            
        except Exception as e:
            logger.error(f"处理通知请求失败: {e}")
            raise
    
    async def _send_notifications(self, channels: List[str], message: str, alert_data: Dict[str, Any]):
        """发送通知到指定渠道"""
        tasks = []
        
        for channel in channels:
            if channel in self.notification_handlers:
                handler = self.notification_handlers[channel]
                task = asyncio.create_task(handler(message, alert_data))
                tasks.append(task)
            else:
                logger.warning(f"未找到通知渠道处理器: {channel}")
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for result in results if result is True)
            
            self.notification_count += success_count
            
            logger.info(
                f"通知发送完成: total_channels={len(tasks)}, "
                f"success_count={success_count}, alert_id={alert_data.get('id')}"
            )
    
    def _get_channels_for_severity(self, severity: str) -> List[str]:
        """根据严重程度获取通知渠道"""
        channel_mapping = {
            'critical': ['email', 'sms', 'dingtalk', 'webhook'],
            'high': ['email', 'dingtalk', 'webhook'],
            'medium': ['email', 'webhook'],
            'low': ['webhook']
        }

        return channel_mapping.get(severity, ['webhook'])
    
    def _format_alert_message(self, alert_data: Dict[str, Any], event_type: str) -> str:
        """格式化告警消息"""
        alert_name = alert_data.get('name', '未知告警')
        severity = alert_data.get('severity', 'unknown')
        description = alert_data.get('description', '')
        
        event_text = {
            'created': '触发',
            'updated': '更新',
            'resolved': '解决',
            'acknowledged': '确认',
            'escalated': '升级',
            'suppressed': '抑制'
        }.get(event_type, event_type)
        
        return f"【{severity.upper()}】告警{event_text}: {alert_name}\n描述: {description}"
    
    async def _error_callback(self, error):
        """NATS错误回调"""
        logger.error(f"NATS错误: {error}")
    
    async def _disconnected_callback(self):
        """NATS断开连接回调"""
        logger.warning("NATS连接已断开")
    
    async def _reconnected_callback(self):
        """NATS重连回调"""
        logger.info("NATS连接已重新建立")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取订阅器统计信息"""
        return {
            "is_running": self.is_running,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "notification_count": self.notification_count,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "subscriptions_count": len(self.subscriptions),
            "nats_connected": self.nc.is_connected if self.nc else False,
            "available_handlers": list(self.notification_handlers.keys())
        }
