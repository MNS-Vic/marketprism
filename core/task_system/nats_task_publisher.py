"""
MarketPrism 任务发布器 - NATS任务队列发布
实现异步任务流：scheduler → NATS → task-workers
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import nats
from nats.js import JetStreamContext
from nats.js.api import StreamConfig, RetentionPolicy, StorageType
import traceback

from .task_types import AsyncTask, TaskEvent, TaskEventType, TaskPriority, TaskSubjects

logger = logging.getLogger(__name__)


class NATSTaskPublisher:
    """NATS任务发布器 - 异步发布任务到队列"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        """
        初始化NATS任务发布器
        
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
        
        logger.info("NATS任务发布器初始化完成")
    
    async def start(self):
        """启动NATS任务发布器"""
        if self.is_connected:
            logger.warning("NATS任务发布器已连接")
            return
        
        try:
            logger.info(f"连接到NATS服务器: {self.nats_url}")
            
            # 连接到NATS
            self.nc = await nats.connect(
                servers=[self.nats_url],
                name="marketprism-task-publisher",
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
                error_cb=self._error_callback,
                disconnected_cb=self._disconnected_callback,
                reconnected_cb=self._reconnected_callback
            )
            
            # 获取JetStream上下文
            self.js = self.nc.jetstream()
            
            # 设置任务流
            await self._setup_task_streams()
            
            self.is_connected = True
            logger.info("✅ NATS任务发布器启动成功")
            
        except Exception as e:
            logger.error(f"❌ NATS任务发布器启动失败: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def stop(self):
        """停止NATS任务发布器"""
        if not self.is_connected:
            return
        
        logger.info("停止NATS任务发布器...")
        
        # 关闭连接
        if self.nc:
            await self.nc.close()
        
        self.is_connected = False
        logger.info("✅ NATS任务发布器已停止")
    
    async def _setup_task_streams(self):
        """设置任务流"""
        try:
            # 任务队列流配置
            task_stream_config = StreamConfig(
                name="TASKS",
                subjects=["tasks.>"],
                retention=RetentionPolicy.LIMITS,
                max_age=7 * 24 * 3600,  # 7天
                max_msgs=10000000,  # 1000万条消息
                max_bytes=50 * 1024 * 1024 * 1024,  # 50GB
                storage=StorageType.FILE,
                duplicate_window=300  # 5分钟去重窗口
            )
            
            # 创建或更新任务流
            try:
                await self.js.add_stream(name="TASKS", subjects=["tasks.>"])
                logger.info("✅ TASKS流创建成功")
            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    logger.info("TASKS流已存在")
                else:
                    logger.warning(f"创建TASKS流时出现问题: {e}")
            
            # 任务事件流配置
            try:
                await self.js.add_stream(name="TASK_EVENTS", subjects=["tasks.events.>"])
                logger.info("✅ TASK_EVENTS流创建成功")
            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    logger.info("TASK_EVENTS流已存在")
                else:
                    logger.warning(f"创建TASK_EVENTS流时出现问题: {e}")
            
            # 工作者状态流配置
            try:
                await self.js.add_stream(name="WORKERS", subjects=["workers.>"])
                logger.info("✅ WORKERS流创建成功")
            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    logger.info("WORKERS流已存在")
                else:
                    logger.warning(f"创建WORKERS流时出现问题: {e}")
                    
        except Exception as e:
            logger.error(f"❌ 设置任务流失败: {e}")
            raise
    
    async def publish_task(self, task: AsyncTask) -> bool:
        """
        发布任务到队列
        
        Args:
            task: 异步任务对象
            
        Returns:
            bool: 发布是否成功
        """
        if not self.is_connected:
            logger.error("NATS未连接，无法发布任务")
            return False
        
        try:
            # 确定任务队列主题
            subject = TaskSubjects.get_task_subject(task.priority)
            
            # 构建任务消息
            task_message = task.to_message()
            
            # 发布消息
            message_data = json.dumps(task_message, ensure_ascii=False, default=str)
            
            # 设置消息头
            headers = {
                'task-id': task.task_id,
                'task-type': str(task.task_type),
                'task-priority': str(task.priority),
                'target-service': task.target_service,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # 发布到JetStream
            ack = await self.js.publish(
                subject=subject,
                payload=message_data.encode('utf-8'),
                headers=headers
            )
            
            self.published_count += 1
            self.last_publish_time = datetime.now(timezone.utc)
            
            logger.info(
                f"任务发布成功: task_id={task.task_id}, "
                f"subject={subject}, priority={task.priority}, "
                f"sequence={ack.seq}"
            )
            
            # 发布任务创建事件
            await self._publish_task_event(task, TaskEventType.QUEUED)
            
            return True
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"任务发布失败: {e}")
            logger.error(f"任务ID: {task.task_id}")
            logger.error(traceback.format_exc())
            return False
    
    async def publish_task_batch(self, tasks: List[AsyncTask]) -> Dict[str, bool]:
        """
        批量发布任务
        
        Args:
            tasks: 任务列表
            
        Returns:
            Dict[str, bool]: 任务ID -> 发布结果映射
        """
        results = {}
        
        for task in tasks:
            results[task.task_id] = await self.publish_task(task)
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(
            f"批量任务发布完成: 总数={len(tasks)}, "
            f"成功={success_count}, 失败={len(tasks) - success_count}"
        )
        
        return results
    
    async def publish_task_event(self, task_id: str, event_type: TaskEventType, 
                                worker_id: Optional[str] = None, 
                                progress: Optional[float] = None,
                                message: Optional[str] = None,
                                error: Optional[str] = None,
                                result: Optional[Dict[str, Any]] = None) -> bool:
        """
        发布任务事件
        
        Args:
            task_id: 任务ID
            event_type: 事件类型
            worker_id: 工作者ID
            progress: 进度 (0.0-1.0)
            message: 消息
            error: 错误信息
            result: 结果数据
            
        Returns:
            bool: 发布是否成功
        """
        if not self.is_connected:
            logger.error("NATS未连接，无法发布任务事件")
            return False
        
        try:
            # 创建任务事件
            event = TaskEvent(
                event_type=event_type,
                task_id=task_id,
                worker_id=worker_id,
                progress=progress,
                message=message,
                error=error,
                result=result
            )
            
            return await self._publish_task_event_obj(event)
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"任务事件发布失败: {e}")
            return False
    
    async def _publish_task_event(self, task: AsyncTask, event_type: TaskEventType) -> bool:
        """发布任务事件（内部方法）"""
        try:
            event = TaskEvent(
                event_type=event_type,
                task_id=task.task_id,
                task_snapshot=task.to_message()
            )
            
            return await self._publish_task_event_obj(event)
            
        except Exception as e:
            logger.error(f"内部任务事件发布失败: {e}")
            return False
    
    async def _publish_task_event_obj(self, event: TaskEvent) -> bool:
        """发布任务事件对象"""
        try:
            # 确定事件主题
            subject = TaskSubjects.get_event_subject(event.task_id, event.event_type)
            
            # 构建事件消息
            event_message = event.to_message()
            
            # 发布消息
            message_data = json.dumps(event_message, ensure_ascii=False, default=str)
            
            # 设置消息头
            headers = {
                'event-id': event.event_id,
                'event-type': str(event.event_type),
                'task-id': event.task_id,
                'timestamp': event.timestamp.isoformat()
            }
            
            if event.worker_id:
                headers['worker-id'] = event.worker_id
            
            # 发布到JetStream
            ack = await self.js.publish(
                subject=subject,
                payload=message_data.encode('utf-8'),
                headers=headers
            )
            
            logger.debug(
                f"任务事件发布成功: event_id={event.event_id}, "
                f"task_id={event.task_id}, event_type={event.event_type}, "
                f"sequence={ack.seq}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"任务事件对象发布失败: {e}")
            return False
    
    async def publish_scheduled_task(self, task: AsyncTask, schedule_time: datetime) -> bool:
        """
        发布定时任务
        
        Args:
            task: 任务对象
            schedule_time: 调度时间
            
        Returns:
            bool: 发布是否成功
        """
        # 设置调度时间
        task.scheduled_at = schedule_time
        
        # 计算延迟时间
        now = datetime.now(timezone.utc)
        if schedule_time > now:
            delay_seconds = int((schedule_time - now).total_seconds())
            task.delay_seconds = delay_seconds
        
        return await self.publish_task(task)
    
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
