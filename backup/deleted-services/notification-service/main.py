"""
MarketPrism 通知服务
处理来自NATS的告警消息并发送通知
"""

import asyncio
import logging
import os
import sys
from typing import Dict, Any
from aiohttp import web
import json
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nats_notification_subscriber import NATSNotificationSubscriber

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务 - 处理告警通知"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app = web.Application()
        self.nats_subscriber = None
        self.is_running = False
        self.notification_stats = {
            'total_notifications': 0,
            'email_notifications': 0,
            'webhook_notifications': 0,
            'dingtalk_notifications': 0,
            'sms_notifications': 0
        }
        
        # 设置路由
        self._setup_routes()
        
        # 初始化通知处理器
        self.notification_handlers = {
            'email': self._handle_email_notification,
            'webhook': self._handle_webhook_notification,
            'dingtalk': self._handle_dingtalk_notification,
            'sms': self._handle_sms_notification
        }
        
        logger.info("通知服务初始化完成")
    
    def _setup_routes(self):
        """设置HTTP路由"""
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_get('/api/v1/status', self._get_status)
        self.app.router.add_get('/api/v1/stats', self._get_stats)
        self.app.router.add_get('/api/v1/nats/status', self._get_nats_status)
        self.app.router.add_post('/api/v1/test/notification', self._test_notification)
    
    async def start(self):
        """启动通知服务"""
        if self.is_running:
            return
        
        try:
            # 启动NATS订阅器
            nats_url = os.getenv("NATS_URL", "nats://nats:4222")
            self.nats_subscriber = NATSNotificationSubscriber(
                notification_handlers=self.notification_handlers,
                nats_url=nats_url
            )
            await self.nats_subscriber.start()
            
            self.is_running = True
            logger.info("✅ 通知服务启动成功")
            
        except Exception as e:
            logger.error(f"❌ 通知服务启动失败: {e}")
            raise
    
    async def stop(self):
        """停止通知服务"""
        if not self.is_running:
            return
        
        logger.info("停止通知服务...")
        
        # 停止NATS订阅器
        if self.nats_subscriber:
            await self.nats_subscriber.stop()
        
        self.is_running = False
        logger.info("✅ 通知服务已停止")
    
    # HTTP API处理器
    async def _health_check(self, request: web.Request) -> web.Response:
        """健康检查"""
        return web.json_response({
            "status": "healthy",
            "service": "notification-service",
            "timestamp": datetime.now().isoformat()
        })
    
    async def _get_status(self, request: web.Request) -> web.Response:
        """获取服务状态"""
        return web.json_response({
            "service": "notification-service",
            "is_running": self.is_running,
            "nats_subscriber_running": self.nats_subscriber.is_running if self.nats_subscriber else False,
            "available_handlers": list(self.notification_handlers.keys()),
            "timestamp": datetime.now().isoformat()
        })
    
    async def _get_stats(self, request: web.Request) -> web.Response:
        """获取统计信息"""
        stats = self.notification_stats.copy()
        
        if self.nats_subscriber:
            stats.update(self.nats_subscriber.get_stats())
        
        return web.json_response(stats)
    
    async def _get_nats_status(self, request: web.Request) -> web.Response:
        """获取NATS状态"""
        if not self.nats_subscriber:
            return web.json_response({
                "status": "disabled",
                "message": "NATS订阅器未初始化"
            })
        
        return web.json_response(self.nats_subscriber.get_stats())
    
    async def _test_notification(self, request: web.Request) -> web.Response:
        """测试通知发送"""
        try:
            data = await request.json()
            channel = data.get('channel', 'webhook')
            message = data.get('message', '测试通知消息')
            alert_data = data.get('alert_data', {})
            
            if channel in self.notification_handlers:
                handler = self.notification_handlers[channel]
                result = await handler(message, alert_data)
                
                return web.json_response({
                    "status": "success" if result else "failed",
                    "channel": channel,
                    "message": "通知发送成功" if result else "通知发送失败"
                })
            else:
                return web.json_response({
                    "status": "error",
                    "message": f"不支持的通知渠道: {channel}"
                }, status=400)
                
        except Exception as e:
            logger.error(f"测试通知失败: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    # 通知处理器
    async def _handle_email_notification(self, message: str, alert_data: Dict[str, Any]) -> bool:
        """处理邮件通知"""
        try:
            logger.info(f"📧 邮件通知: {message}")
            logger.info(f"告警数据: {alert_data}")
            
            # 这里可以集成真实的邮件发送逻辑
            # 例如使用SMTP、SendGrid、阿里云邮件推送等
            
            self.notification_stats['email_notifications'] += 1
            self.notification_stats['total_notifications'] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"邮件通知发送失败: {e}")
            return False
    
    async def _handle_webhook_notification(self, message: str, alert_data: Dict[str, Any]) -> bool:
        """处理Webhook通知"""
        try:
            logger.info(f"🔗 Webhook通知: {message}")
            logger.info(f"告警数据: {alert_data}")
            
            # 这里可以集成真实的Webhook发送逻辑
            # 例如发送到Slack、Teams、自定义Webhook等
            
            self.notification_stats['webhook_notifications'] += 1
            self.notification_stats['total_notifications'] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Webhook通知发送失败: {e}")
            return False
    
    async def _handle_dingtalk_notification(self, message: str, alert_data: Dict[str, Any]) -> bool:
        """处理钉钉通知"""
        try:
            logger.info(f"📱 钉钉通知: {message}")
            logger.info(f"告警数据: {alert_data}")
            
            # 这里可以集成真实的钉钉机器人发送逻辑
            
            self.notification_stats['dingtalk_notifications'] += 1
            self.notification_stats['total_notifications'] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"钉钉通知发送失败: {e}")
            return False
    
    async def _handle_sms_notification(self, message: str, alert_data: Dict[str, Any]) -> bool:
        """处理短信通知"""
        try:
            logger.info(f"📲 短信通知: {message}")
            logger.info(f"告警数据: {alert_data}")
            
            # 这里可以集成真实的短信发送逻辑
            # 例如使用阿里云短信、腾讯云短信等
            
            self.notification_stats['sms_notifications'] += 1
            self.notification_stats['total_notifications'] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"短信通知发送失败: {e}")
            return False


async def create_app():
    """创建应用"""
    config = {
        'host': '0.0.0.0',
        'port': 8089
    }
    
    service = NotificationService(config)
    
    # 设置启动和关闭处理器
    async def startup_handler(app):
        await service.start()
    
    async def cleanup_handler(app):
        await service.stop()
    
    service.app.on_startup.append(startup_handler)
    service.app.on_cleanup.append(cleanup_handler)
    
    return service.app


def main():
    """主函数"""
    try:
        app = asyncio.run(create_app())
        
        # 启动Web服务器
        web.run_app(
            app,
            host='0.0.0.0',
            port=8089
        )
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止服务...")
    except Exception as e:
        logger.error(f"服务运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
