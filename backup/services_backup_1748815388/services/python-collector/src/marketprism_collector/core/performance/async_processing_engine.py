"""
⚡ AsyncProcessingEngine - 异步处理引擎

异步路由和并发控制优化
提供非阻塞IO、任务队列、并发控制、背压处理等功能
"""

import asyncio
import time
import uuid
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import weakref
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """任务优先级枚举"""
    URGENT = 1      # 紧急
    HIGH = 2        # 高
    NORMAL = 3      # 正常
    LOW = 4         # 低
    BACKGROUND = 5  # 后台


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 等待中
    RUNNING = "running"      # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"      # 超时


class BackpressureStrategy(Enum):
    """背压策略枚举"""
    DROP_OLDEST = "drop_oldest"    # 丢弃最旧任务
    DROP_NEWEST = "drop_newest"    # 丢弃最新任务
    BLOCK = "block"                # 阻塞等待
    REJECT = "reject"              # 拒绝新任务
    ADAPTIVE = "adaptive"          # 自适应


@dataclass
class TaskConfig:
    """任务配置"""
    timeout: Optional[float] = None
    retry_count: int = 0
    retry_delay: float = 1.0
    priority: TaskPriority = TaskPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingConfig:
    """处理配置"""
    max_concurrent_tasks: int = 1000
    max_queue_size: int = 10000
    worker_count: int = 10
    backpressure_strategy: BackpressureStrategy = BackpressureStrategy.ADAPTIVE
    enable_metrics: bool = True
    metrics_interval: float = 30.0
    default_timeout: float = 300.0
    cleanup_interval: float = 60.0


class Task:
    """异步任务"""
    
    def __init__(self, task_id: str, func: Callable, args: tuple, kwargs: dict, 
                 config: Optional[TaskConfig] = None):
        self.id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.config = config or TaskConfig()
        self.status = TaskStatus.PENDING
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.result: Any = None
        self.error: Optional[Exception] = None
        self.retry_count = 0
        self.future: Optional[asyncio.Future] = None
        
    @property
    def duration(self) -> Optional[float]:
        """任务执行时长"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return None
    
    @property
    def wait_time(self) -> float:
        """等待时长"""
        start_time = self.started_at or time.time()
        return start_time - self.created_at
    
    def is_expired(self) -> bool:
        """是否超时"""
        if not self.config.timeout:
            return False
        return time.time() - self.created_at > self.config.timeout


class TaskQueue:
    """任务队列"""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.queues: Dict[TaskPriority, deque] = {
            priority: deque() for priority in TaskPriority
        }
        self.lock = asyncio.Lock()
        self.not_empty = asyncio.Condition()
        self.size = 0
        
    async def put(self, task: Task) -> bool:
        """添加任务"""
        async with self.lock:
            # 检查队列容量
            if self.size >= self.config.max_queue_size:
                if self.config.backpressure_strategy == BackpressureStrategy.DROP_OLDEST:
                    await self._drop_oldest()
                elif self.config.backpressure_strategy == BackpressureStrategy.DROP_NEWEST:
                    return False
                elif self.config.backpressure_strategy == BackpressureStrategy.REJECT:
                    return False
                elif self.config.backpressure_strategy == BackpressureStrategy.ADAPTIVE:
                    if task.config.priority in [TaskPriority.URGENT, TaskPriority.HIGH]:
                        await self._drop_oldest()
                    else:
                        return False
            
            self.queues[task.config.priority].append(task)
            self.size += 1
            
            async with self.not_empty:
                self.not_empty.notify()
            
            return True
    
    async def get(self) -> Optional[Task]:
        """获取任务"""
        async with self.not_empty:
            while self.size == 0:
                await self.not_empty.wait()
            
            async with self.lock:
                # 按优先级获取任务
                for priority in TaskPriority:
                    if self.queues[priority]:
                        task = self.queues[priority].popleft()
                        self.size -= 1
                        return task
                
                return None
    
    async def _drop_oldest(self):
        """丢弃最旧任务"""
        for priority in reversed(list(TaskPriority)):
            if self.queues[priority]:
                dropped_task = self.queues[priority].popleft()
                self.size -= 1
                dropped_task.status = TaskStatus.CANCELLED
                logger.warning(f"丢弃任务: {dropped_task.id}, priority={priority.value}")
                break
    
    def get_size_by_priority(self) -> Dict[TaskPriority, int]:
        """获取各优先级队列大小"""
        return {priority: len(queue) for priority, queue in self.queues.items()}


class WorkerPool:
    """工作池"""
    
    def __init__(self, config: ProcessingConfig, task_queue: TaskQueue):
        self.config = config
        self.task_queue = task_queue
        self.workers: List[asyncio.Task] = []
        self.running_tasks: Dict[str, Task] = {}
        self.lock = asyncio.Lock()
        self.is_running = False
        self.thread_pool = ThreadPoolExecutor(max_workers=config.worker_count)
        
    async def start(self):
        """启动工作池"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 创建工作协程
        for i in range(self.config.worker_count):
            worker = asyncio.create_task(self._worker(f"worker_{i}"))
            self.workers.append(worker)
        
        logger.info(f"工作池启动: {self.config.worker_count} 个工作者")
    
    async def stop(self):
        """停止工作池"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消所有工作者
        for worker in self.workers:
            worker.cancel()
        
        # 等待工作者停止
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
        
        # 关闭线程池
        self.thread_pool.shutdown(wait=True)
        
        self.workers.clear()
        logger.info("工作池已停止")
    
    async def _worker(self, worker_id: str):
        """工作者协程"""
        logger.debug(f"工作者启动: {worker_id}")
        
        while self.is_running:
            try:
                # 获取任务
                task = await self.task_queue.get()
                if not task:
                    continue
                
                # 检查任务是否过期
                if task.is_expired():
                    task.status = TaskStatus.TIMEOUT
                    continue
                
                # 执行任务
                await self._execute_task(task)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"工作者错误: {worker_id}, error={e}")
        
        logger.debug(f"工作者停止: {worker_id}")
    
    async def _execute_task(self, task: Task):
        """执行任务"""
        async with self.lock:
            self.running_tasks[task.id] = task
        
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        
        try:
            # 设置超时
            timeout = task.config.timeout or self.config.default_timeout
            
            # 执行任务
            if asyncio.iscoroutinefunction(task.func):
                result = await asyncio.wait_for(
                    task.func(*task.args, **task.kwargs),
                    timeout=timeout
                )
            else:
                # 在线程池中执行同步函数
                result = await asyncio.get_event_loop().run_in_executor(
                    self.thread_pool,
                    lambda: task.func(*task.args, **task.kwargs)
                )
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            
            # 设置Future结果
            if task.future and not task.future.done():
                task.future.set_result(result)
        
        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.error = TimeoutError("Task execution timeout")
            if task.future and not task.future.done():
                task.future.set_exception(task.error)
        
        except Exception as e:
            task.error = e
            
            # 重试逻辑
            if task.retry_count < task.config.retry_count:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                await asyncio.sleep(task.config.retry_delay)
                await self.task_queue.put(task)
                return
            
            task.status = TaskStatus.FAILED
            if task.future and not task.future.done():
                task.future.set_exception(e)
        
        finally:
            task.completed_at = time.time()
            async with self.lock:
                if task.id in self.running_tasks:
                    del self.running_tasks[task.id]
    
    def get_running_count(self) -> int:
        """获取运行中任务数量"""
        return len(self.running_tasks)
    
    def get_running_tasks(self) -> List[Task]:
        """获取运行中任务列表"""
        return list(self.running_tasks.values())


class AsyncProcessingEngine:
    """
    ⚡ 异步处理引擎
    
    提供异步任务处理、并发控制、队列管理、背压处理等功能
    """
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        self.config = config or ProcessingConfig()
        self.task_queue = TaskQueue(self.config)
        self.worker_pool = WorkerPool(self.config, self.task_queue)
        self.tasks: Dict[str, Task] = {}
        self.completed_tasks: deque = deque(maxlen=1000)  # 保存最近1000个完成的任务
        self.metrics = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_timeout": 0,
            "total_cancelled": 0,
            "avg_wait_time": 0.0,
            "avg_execution_time": 0.0
        }
        self.metrics_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info("AsyncProcessingEngine初始化完成")
    
    async def start(self):
        """启动异步处理引擎"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动工作池
        await self.worker_pool.start()
        
        # 启动指标收集
        if self.config.enable_metrics:
            self.metrics_task = asyncio.create_task(self._metrics_loop())
        
        # 启动清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("AsyncProcessingEngine已启动")
    
    async def stop(self):
        """停止异步处理引擎"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消任务
        if self.metrics_task:
            self.metrics_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # 停止工作池
        await self.worker_pool.stop()
        
        logger.info("AsyncProcessingEngine已停止")
    
    async def submit(self, func: Callable, *args, config: Optional[TaskConfig] = None, **kwargs) -> str:
        """提交任务"""
        task_id = str(uuid.uuid4())
        task_config = config or TaskConfig()
        
        task = Task(task_id, func, args, kwargs, task_config)
        task.future = asyncio.Future()
        
        # 添加到队列
        success = await self.task_queue.put(task)
        if not success:
            raise RuntimeError("任务队列已满，无法提交任务")
        
        self.tasks[task_id] = task
        self.metrics["total_submitted"] += 1
        
        logger.debug(f"任务提交: {task_id}, priority={task_config.priority.value}")
        return task_id
    
    async def submit_and_wait(self, func: Callable, *args, config: Optional[TaskConfig] = None, **kwargs) -> Any:
        """提交任务并等待结果"""
        task_id = await self.submit(func, *args, config=config, **kwargs)
        return await self.wait_for_result(task_id)
    
    async def wait_for_result(self, task_id: str) -> Any:
        """等待任务结果"""
        if task_id not in self.tasks:
            raise ValueError(f"任务不存在: {task_id}")
        
        task = self.tasks[task_id]
        if task.future:
            return await task.future
        else:
            raise RuntimeError(f"任务没有Future对象: {task_id}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.status = TaskStatus.CANCELLED
        
        if task.future and not task.future.done():
            task.future.cancel()
        
        self.metrics["total_cancelled"] += 1
        logger.debug(f"任务取消: {task_id}")
        return True
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        if task_id in self.tasks:
            return self.tasks[task_id].status
        return None
    
    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        if task_id not in self.tasks:
            return None
        
        task = self.tasks[task_id]
        return {
            "id": task.id,
            "status": task.status.value,
            "priority": task.config.priority.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "duration": task.duration,
            "wait_time": task.wait_time,
            "retry_count": task.retry_count,
            "error": str(task.error) if task.error else None
        }
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计"""
        return {
            "total_size": self.task_queue.size,
            "size_by_priority": {p.value: s for p, s in self.task_queue.get_size_by_priority().items()},
            "running_tasks": self.worker_pool.get_running_count(),
            "max_queue_size": self.config.max_queue_size,
            "max_concurrent_tasks": self.config.max_concurrent_tasks
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        queue_stats = self.get_queue_stats()
        
        return {
            **self.metrics,
            **queue_stats,
            "utilization": self.worker_pool.get_running_count() / self.config.worker_count,
            "queue_utilization": self.task_queue.size / self.config.max_queue_size
        }
    
    def get_performance_analysis(self) -> Dict[str, Any]:
        """获取性能分析"""
        metrics = self.get_metrics()
        analysis = {
            "metrics": metrics,
            "bottlenecks": [],
            "recommendations": []
        }
        
        # 分析瓶颈
        if metrics["queue_utilization"] > 0.8:
            analysis["bottlenecks"].append("队列使用率过高")
            analysis["recommendations"].append("考虑增加队列容量或工作者数量")
        
        if metrics["utilization"] > 0.9:
            analysis["bottlenecks"].append("工作者利用率过高")
            analysis["recommendations"].append("增加工作者数量")
        
        if metrics["total_failed"] > metrics["total_completed"] * 0.1:
            analysis["bottlenecks"].append("任务失败率过高")
            analysis["recommendations"].append("检查任务逻辑和系统资源")
        
        if metrics["avg_wait_time"] > 10.0:
            analysis["bottlenecks"].append("任务等待时间过长")
            analysis["recommendations"].append("优化任务调度或增加处理能力")
        
        return analysis
    
    async def _metrics_loop(self):
        """指标收集循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.metrics_interval)
                await self._update_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标收集失败: {e}")
    
    async def _update_metrics(self):
        """更新指标"""
        # 计算平均等待时间和执行时间
        if self.completed_tasks:
            wait_times = [task.wait_time for task in self.completed_tasks if task.wait_time is not None]
            execution_times = [task.duration for task in self.completed_tasks if task.duration is not None]
            
            self.metrics["avg_wait_time"] = sum(wait_times) / len(wait_times) if wait_times else 0.0
            self.metrics["avg_execution_time"] = sum(execution_times) / len(execution_times) if execution_times else 0.0
        
        # 统计任务状态
        completed_count = len([task for task in self.completed_tasks if task.status == TaskStatus.COMPLETED])
        failed_count = len([task for task in self.completed_tasks if task.status == TaskStatus.FAILED])
        timeout_count = len([task for task in self.completed_tasks if task.status == TaskStatus.TIMEOUT])
        cancelled_count = len([task for task in self.completed_tasks if task.status == TaskStatus.CANCELLED])
        
        self.metrics.update({
            "total_completed": completed_count,
            "total_failed": failed_count,
            "total_timeout": timeout_count,
            "total_cancelled": cancelled_count
        })
        
        logger.debug(f"指标更新: {self.metrics}")
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                await self._cleanup_completed_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理任务失败: {e}")
    
    async def _cleanup_completed_tasks(self):
        """清理已完成任务"""
        current_time = time.time()
        cleanup_threshold = 3600  # 1小时
        
        completed_task_ids = []
        for task_id, task in self.tasks.items():
            if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.TIMEOUT, TaskStatus.CANCELLED] and
                task.completed_at and current_time - task.completed_at > cleanup_threshold):
                completed_task_ids.append(task_id)
                self.completed_tasks.append(task)
        
        # 清理任务
        for task_id in completed_task_ids:
            del self.tasks[task_id]
        
        if completed_task_ids:
            logger.debug(f"清理已完成任务: {len(completed_task_ids)} 个")


# 工具函数和装饰器

def async_task(priority: TaskPriority = TaskPriority.NORMAL, 
               timeout: Optional[float] = None,
               retry_count: int = 0):
    """异步任务装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            config = TaskConfig(
                priority=priority,
                timeout=timeout,
                retry_count=retry_count
            )
            # 这里需要从某个地方获取engine实例
            # 在实际使用中，engine应该是全局可访问的
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def batch_process(engine: AsyncProcessingEngine, 
                       func: Callable, 
                       items: List[Any], 
                       batch_size: int = 10,
                       config: Optional[TaskConfig] = None) -> List[Any]:
    """批处理函数"""
    tasks = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        task_id = await engine.submit(func, batch, config=config)
        tasks.append(task_id)
    
    results = []
    for task_id in tasks:
        result = await engine.wait_for_result(task_id)
        results.extend(result)
    
    return results