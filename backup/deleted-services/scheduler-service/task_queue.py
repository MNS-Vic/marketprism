"""
任务队列管理器 - 解决任务丢失问题
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import json
import uuid

logger = logging.getLogger(__name__)

class TaskPriority(Enum):
    """任务优先级"""
    HIGH = 1
    MEDIUM = 2
    LOW = 3

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class QueuedTask:
    """队列任务"""
    task_id: str
    name: str
    target_service: str
    endpoint: str
    payload: Dict[str, Any]
    priority: TaskPriority = TaskPriority.MEDIUM
    max_retries: int = 3
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_at: Optional[datetime] = None
    timeout_seconds: int = 600
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "target_service": self.target_service,
            "endpoint": self.endpoint,
            "payload": self.payload,
            "priority": self.priority.value,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "timeout_seconds": self.timeout_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueuedTask':
        """从字典创建"""
        return cls(
            task_id=data["task_id"],
            name=data["name"],
            target_service=data["target_service"],
            endpoint=data["endpoint"],
            payload=data["payload"],
            priority=TaskPriority(data["priority"]),
            max_retries=data["max_retries"],
            retry_count=data["retry_count"],
            created_at=datetime.fromisoformat(data["created_at"]),
            scheduled_at=datetime.fromisoformat(data["scheduled_at"]) if data["scheduled_at"] else None,
            timeout_seconds=data["timeout_seconds"]
        )

class PriorityTaskQueue:
    """优先级任务队列"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queues = {
            TaskPriority.HIGH: asyncio.Queue(maxsize=max_size // 3),
            TaskPriority.MEDIUM: asyncio.Queue(maxsize=max_size // 3),
            TaskPriority.LOW: asyncio.Queue(maxsize=max_size // 3)
        }
        self.pending_tasks: Dict[str, QueuedTask] = {}
        self.running_tasks: Dict[str, QueuedTask] = {}
        self.completed_tasks: Dict[str, QueuedTask] = {}
        self.failed_tasks: Dict[str, QueuedTask] = {}
        
        # 统计信息
        self.stats = {
            "total_enqueued": 0,
            "total_completed": 0,
            "total_failed": 0,
            "queue_full_rejections": 0
        }
        
        self._running = False
        self._consumer_task = None
    
    async def start(self):
        """启动队列消费者"""
        self._running = True
        self._consumer_task = asyncio.create_task(self._queue_consumer())
        logger.info("PriorityTaskQueue started")
    
    async def stop(self):
        """停止队列消费者"""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        logger.info("PriorityTaskQueue stopped")
    
    async def enqueue(self, task: QueuedTask) -> bool:
        """入队任务"""
        try:
            queue = self.queues[task.priority]
            
            # 检查队列是否已满
            if queue.full():
                self.stats["queue_full_rejections"] += 1
                logger.warning(f"队列已满，拒绝任务: {task.task_id}")
                return False
            
            # 添加到队列
            await queue.put(task)
            self.pending_tasks[task.task_id] = task
            self.stats["total_enqueued"] += 1
            
            logger.info(f"任务已入队: {task.task_id}, 优先级: {task.priority.name}")
            return True
            
        except Exception as e:
            logger.error(f"任务入队失败: {task.task_id}, error: {e}")
            return False
    
    async def dequeue(self) -> Optional[QueuedTask]:
        """出队任务（按优先级）"""
        # 按优先级顺序检查队列
        for priority in [TaskPriority.HIGH, TaskPriority.MEDIUM, TaskPriority.LOW]:
            queue = self.queues[priority]
            try:
                task = queue.get_nowait()
                # 移动到运行队列
                if task.task_id in self.pending_tasks:
                    del self.pending_tasks[task.task_id]
                self.running_tasks[task.task_id] = task
                return task
            except asyncio.QueueEmpty:
                continue
        
        return None
    
    async def _queue_consumer(self):
        """队列消费者（内部使用）"""
        while self._running:
            try:
                # 等待任意队列有任务
                tasks = []
                for priority in [TaskPriority.HIGH, TaskPriority.MEDIUM, TaskPriority.LOW]:
                    queue = self.queues[priority]
                    if not queue.empty():
                        task = await queue.get()
                        tasks.append(task)
                        break
                
                if not tasks:
                    await asyncio.sleep(0.1)  # 短暂等待
                    continue
                
                # 这里可以添加任务分发逻辑
                # 当前版本由外部调用dequeue()获取任务
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"队列消费者异常: {e}")
                await asyncio.sleep(1)
    
    def mark_task_completed(self, task_id: str, success: bool = True):
        """标记任务完成"""
        if task_id in self.running_tasks:
            task = self.running_tasks.pop(task_id)
            if success:
                self.completed_tasks[task_id] = task
                self.stats["total_completed"] += 1
            else:
                # 检查是否需要重试
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    asyncio.create_task(self.enqueue(task))
                    logger.info(f"任务重试: {task_id}, 重试次数: {task.retry_count}")
                else:
                    self.failed_tasks[task_id] = task
                    self.stats["total_failed"] += 1
                    logger.error(f"任务最终失败: {task_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        return {
            **self.stats,
            "pending_tasks": len(self.pending_tasks),
            "running_tasks": len(self.running_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "queue_sizes": {
                priority.name: self.queues[priority].qsize() 
                for priority in TaskPriority
            }
        }
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        if task_id in self.pending_tasks:
            return TaskStatus.PENDING
        elif task_id in self.running_tasks:
            return TaskStatus.RUNNING
        elif task_id in self.completed_tasks:
            return TaskStatus.COMPLETED
        elif task_id in self.failed_tasks:
            return TaskStatus.FAILED
        else:
            return None
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理旧任务记录"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        for task_dict in [self.completed_tasks, self.failed_tasks]:
            to_remove = []
            for task_id, task in task_dict.items():
                if task.created_at < cutoff_time:
                    to_remove.append(task_id)
            
            for task_id in to_remove:
                del task_dict[task_id]
        
        logger.info(f"清理了 {len(to_remove)} 个旧任务记录")
