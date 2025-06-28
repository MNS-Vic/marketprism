"""
MarketPrism 通知管理器

支持多种通知渠道的告警通知系统
"""

import asyncio
import json
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any
import aiohttp
import structlog

from .alert_types import Alert, AlertSeverity, NotificationChannel


logger = structlog.get_logger(__name__)


class NotificationChannel:
    """通知渠道基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get('enabled', True)
    
    async def send(self, alert: Alert, message: str) -> bool:
        """发送通知"""
        raise NotImplementedError


class EmailNotificationChannel(NotificationChannel):
    """邮件通知渠道"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.smtp_server = config.get('smtp_server', 'localhost')
        self.smtp_port = config.get('smtp_port', 587)
        self.username = config.get('username')
        self.password = config.get('password')
        self.from_email = config.get('from_email')
        self.to_emails = config.get('to_emails', [])
        self.use_tls = config.get('use_tls', True)
    
    async def send(self, alert: Alert, message: str) -> bool:
        """发送邮件通知"""
        if not self.enabled or not self.to_emails:
            return False
        
        try:
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = ', '.join(self.to_emails)
            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.name}"
            
            # 邮件内容
            body = self._format_email_body(alert, message)
            msg.attach(MIMEText(body, 'html'))
            
            # 发送邮件
            await self._send_email(msg)
            
            logger.info("邮件通知发送成功", alert_id=alert.id, recipients=len(self.to_emails))
            return True
            
        except Exception as e:
            logger.error("邮件通知发送失败", error=str(e), alert_id=alert.id)
            return False
    
    async def _send_email(self, msg: MIMEMultipart) -> None:
        """发送邮件"""
        loop = asyncio.get_event_loop()
        
        def _send():
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)
        
        await loop.run_in_executor(None, _send)
    
    def _format_email_body(self, alert: Alert, message: str) -> str:
        """格式化邮件内容"""
        severity_colors = {
            AlertSeverity.CRITICAL: '#dc3545',
            AlertSeverity.HIGH: '#fd7e14',
            AlertSeverity.MEDIUM: '#ffc107',
            AlertSeverity.LOW: '#28a745'
        }
        
        color = severity_colors.get(alert.severity, '#6c757d')
        
        return f"""
        <html>
        <body>
            <h2 style="color: {color};">MarketPrism 告警通知</h2>
            <table border="1" cellpadding="5" cellspacing="0">
                <tr><td><strong>告警名称</strong></td><td>{alert.name}</td></tr>
                <tr><td><strong>严重程度</strong></td><td style="color: {color};">{alert.severity.value.upper()}</td></tr>
                <tr><td><strong>类别</strong></td><td>{alert.category.value}</td></tr>
                <tr><td><strong>描述</strong></td><td>{alert.description}</td></tr>
                <tr><td><strong>创建时间</strong></td><td>{alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
                <tr><td><strong>告警ID</strong></td><td>{alert.id}</td></tr>
            </table>
            <br>
            <p><strong>详细信息：</strong></p>
            <pre>{message}</pre>
            <br>
            <p><em>此邮件由 MarketPrism 监控系统自动发送</em></p>
        </body>
        </html>
        """


class SlackNotificationChannel(NotificationChannel):
    """Slack通知渠道"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.webhook_url = config.get('webhook_url')
        self.channel = config.get('channel', '#alerts')
        self.username = config.get('username', 'MarketPrism')
    
    async def send(self, alert: Alert, message: str) -> bool:
        """发送Slack通知"""
        if not self.enabled or not self.webhook_url:
            return False
        
        try:
            payload = self._create_slack_payload(alert, message)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.info("Slack通知发送成功", alert_id=alert.id)
                        return True
                    else:
                        logger.error("Slack通知发送失败", 
                                   status=response.status, 
                                   alert_id=alert.id)
                        return False
                        
        except Exception as e:
            logger.error("Slack通知发送失败", error=str(e), alert_id=alert.id)
            return False
    
    def _create_slack_payload(self, alert: Alert, message: str) -> Dict[str, Any]:
        """创建Slack消息载荷"""
        severity_colors = {
            AlertSeverity.CRITICAL: 'danger',
            AlertSeverity.HIGH: 'warning',
            AlertSeverity.MEDIUM: 'warning',
            AlertSeverity.LOW: 'good'
        }
        
        color = severity_colors.get(alert.severity, '#36a64f')
        
        return {
            "channel": self.channel,
            "username": self.username,
            "icon_emoji": ":warning:",
            "attachments": [
                {
                    "color": color,
                    "title": f"[{alert.severity.value.upper()}] {alert.name}",
                    "text": alert.description,
                    "fields": [
                        {
                            "title": "类别",
                            "value": alert.category.value,
                            "short": True
                        },
                        {
                            "title": "创建时间",
                            "value": alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                            "short": True
                        },
                        {
                            "title": "告警ID",
                            "value": alert.id,
                            "short": False
                        }
                    ],
                    "footer": "MarketPrism 监控系统",
                    "ts": int(alert.created_at.timestamp())
                }
            ]
        }


class DingTalkNotificationChannel(NotificationChannel):
    """钉钉通知渠道"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.webhook_url = config.get('webhook_url')
        self.secret = config.get('secret')
    
    async def send(self, alert: Alert, message: str) -> bool:
        """发送钉钉通知"""
        if not self.enabled or not self.webhook_url:
            return False
        
        try:
            payload = self._create_dingtalk_payload(alert, message)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('errcode') == 0:
                            logger.info("钉钉通知发送成功", alert_id=alert.id)
                            return True
                        else:
                            logger.error("钉钉通知发送失败", 
                                       error=result.get('errmsg'), 
                                       alert_id=alert.id)
                            return False
                    else:
                        logger.error("钉钉通知发送失败", 
                                   status=response.status, 
                                   alert_id=alert.id)
                        return False
                        
        except Exception as e:
            logger.error("钉钉通知发送失败", error=str(e), alert_id=alert.id)
            return False
    
    def _create_dingtalk_payload(self, alert: Alert, message: str) -> Dict[str, Any]:
        """创建钉钉消息载荷"""
        severity_emojis = {
            AlertSeverity.CRITICAL: "🔴",
            AlertSeverity.HIGH: "🟠", 
            AlertSeverity.MEDIUM: "🟡",
            AlertSeverity.LOW: "🟢"
        }
        
        emoji = severity_emojis.get(alert.severity, "⚪")
        
        text = f"""
{emoji} **MarketPrism 告警通知**

**告警名称**: {alert.name}
**严重程度**: {alert.severity.value.upper()}
**类别**: {alert.category.value}
**描述**: {alert.description}
**创建时间**: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
**告警ID**: {alert.id}

---
{message}
        """.strip()
        
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"[{alert.severity.value.upper()}] {alert.name}",
                "text": text
            }
        }


class WebhookNotificationChannel(NotificationChannel):
    """Webhook通知渠道"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get('url')
        self.headers = config.get('headers', {})
        self.timeout = config.get('timeout', 30)
    
    async def send(self, alert: Alert, message: str) -> bool:
        """发送Webhook通知"""
        if not self.enabled or not self.url:
            return False
        
        try:
            payload = {
                "alert": alert.to_dict(),
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.url, 
                    json=payload, 
                    headers=self.headers
                ) as response:
                    if 200 <= response.status < 300:
                        logger.info("Webhook通知发送成功", alert_id=alert.id, url=self.url)
                        return True
                    else:
                        logger.error("Webhook通知发送失败", 
                                   status=response.status, 
                                   alert_id=alert.id,
                                   url=self.url)
                        return False
                        
        except Exception as e:
            logger.error("Webhook通知发送失败", error=str(e), alert_id=alert.id, url=self.url)
            return False


class NotificationManager:
    """通知管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.channels: Dict[str, NotificationChannel] = {}
        
        # 初始化通知渠道
        self._initialize_channels()
        
        # 通知规则
        self.notification_rules = config.get('rules', {})
        
        logger.info("通知管理器初始化完成", channels=list(self.channels.keys()))
    
    def _initialize_channels(self) -> None:
        """初始化通知渠道"""
        channels_config = self.config.get('channels', {})
        
        # 邮件渠道
        if 'email' in channels_config:
            self.channels['email'] = EmailNotificationChannel(channels_config['email'])
        
        # Slack渠道
        if 'slack' in channels_config:
            self.channels['slack'] = SlackNotificationChannel(channels_config['slack'])
        
        # 钉钉渠道
        if 'dingtalk' in channels_config:
            self.channels['dingtalk'] = DingTalkNotificationChannel(channels_config['dingtalk'])
        
        # Webhook渠道
        if 'webhook' in channels_config:
            self.channels['webhook'] = WebhookNotificationChannel(channels_config['webhook'])
    
    async def send_alert_notification(self, alert: Alert) -> None:
        """发送告警通知"""
        # 获取适用的通知渠道
        channels_to_notify = self._get_channels_for_alert(alert)
        
        if not channels_to_notify:
            logger.debug("没有适用的通知渠道", alert_id=alert.id)
            return
        
        # 格式化消息
        message = self._format_alert_message(alert)
        
        # 并发发送通知
        tasks = []
        for channel_name in channels_to_notify:
            if channel_name in self.channels:
                channel = self.channels[channel_name]
                task = asyncio.create_task(channel.send(alert, message))
                tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for result in results if result is True)
            
            logger.info(
                "告警通知发送完成",
                alert_id=alert.id,
                total_channels=len(tasks),
                success_count=success_count
            )
    
    def _get_channels_for_alert(self, alert: Alert) -> List[str]:
        """获取告警适用的通知渠道"""
        # 默认规则：根据严重程度选择渠道
        default_channels = {
            AlertSeverity.CRITICAL: ['email', 'slack', 'dingtalk'],
            AlertSeverity.HIGH: ['email', 'slack'],
            AlertSeverity.MEDIUM: ['slack'],
            AlertSeverity.LOW: ['slack']
        }
        
        # 检查自定义规则
        for rule_name, rule_config in self.notification_rules.items():
            if self._matches_notification_rule(alert, rule_config):
                return rule_config.get('channels', [])
        
        # 使用默认规则
        return default_channels.get(alert.severity, ['slack'])
    
    def _matches_notification_rule(self, alert: Alert, rule: Dict[str, Any]) -> bool:
        """检查告警是否匹配通知规则"""
        conditions = rule.get('conditions', {})
        
        for key, value in conditions.items():
            if key == 'severity':
                if alert.severity.value not in value:
                    return False
            elif key == 'category':
                if alert.category.value not in value:
                    return False
            elif key == 'labels':
                for label_key, label_values in value.items():
                    if alert.labels.get(label_key) not in label_values:
                        return False
        
        return True
    
    def _format_alert_message(self, alert: Alert) -> str:
        """格式化告警消息"""
        message_parts = []
        
        # 基本信息
        message_parts.append(f"告警详情:")
        message_parts.append(f"- 名称: {alert.name}")
        message_parts.append(f"- 严重程度: {alert.severity.value.upper()}")
        message_parts.append(f"- 类别: {alert.category.value}")
        message_parts.append(f"- 描述: {alert.description}")
        
        # 元数据
        if alert.metadata:
            message_parts.append(f"- 元数据: {json.dumps(alert.metadata, indent=2)}")
        
        # 标签
        if alert.labels:
            message_parts.append(f"- 标签: {json.dumps(alert.labels, indent=2)}")
        
        # 指标信息
        if alert.metric_name:
            message_parts.append(f"- 指标: {alert.metric_name}")
            if alert.metric_value is not None:
                message_parts.append(f"- 当前值: {alert.metric_value}")
            if alert.threshold is not None:
                message_parts.append(f"- 阈值: {alert.threshold}")
        
        return '\n'.join(message_parts)
