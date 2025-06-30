"""
MarketPrism 调度服务
基于data_archiver的分布式任务调度服务
提供定时任务、数据归档、系统维护等调度功能
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from aiohttp import web
import aiohttp
from dataclasses import dataclass
from enum import Enum
import uuid
import yaml
import sys
from pathlib import Path
import logging
import traceback
import signal

from core.service_framework import BaseService, get_service_registry

# 确保能正确找到项目根目录并添加到sys.path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入任务队列
try:
    from .task_queue import PriorityTaskQueue, QueuedTask, TaskPriority, TaskStatus as QueueTaskStatus
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    import sys
    sys.path.append(str(Path(__file__).parent))
    from task_queue import PriorityTaskQueue, QueuedTask, TaskPriority, TaskStatus as QueueTaskStatus

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """调度任务数据类"""
    task_id: str
    name: str
    cron_expression: str
    target_service: str
    target_endpoint: str
    payload: Dict[str, Any]
    status: TaskStatus
    created_at: datetime
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None


class CronParser:
    """简单的Cron表达式解析器"""
    
    @staticmethod
    def parse_cron(cron_expr: str) -> Dict[str, Any]:
        """解析Cron表达式"""
        # 简化实现，支持基本格式：分 时 日 月 周
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValueError("Invalid cron expression format")
            
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "weekday": parts[4]
        }
        
    @staticmethod
    def next_run_time(cron_expr: str, from_time: datetime = None) -> datetime:
        """计算下次运行时间"""
        if from_time is None:
            from_time = datetime.now()
            
        # 简化实现：每小时运行一次
        if cron_expr == "0 * * * *":
            next_hour = from_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return next_hour
            
        # 每天凌晨2点运行
        elif cron_expr == "0 2 * * *":
            next_day = from_time.replace(hour=2, minute=0, second=0, microsecond=0)
            if next_day <= from_time:
                next_day += timedelta(days=1)
            return next_day
            
        # 每5分钟运行一次
        elif cron_expr == "*/5 * * * *":
            next_time = from_time.replace(second=0, microsecond=0)
            next_time += timedelta(minutes=5 - (next_time.minute % 5))
            return next_time
            
        # 默认：1小时后
        return from_time + timedelta(hours=1)


class AsyncTaskExecutor:
    """增强的异步任务执行器 - 整合task-worker的异步优化功能和任务队列"""

    def __init__(self, logger, metrics, max_concurrent_tasks=5, queue_size=1000):
        self.logger = logger
        self.metrics = metrics
        self.max_concurrent_tasks = max_concurrent_tasks

        # 任务队列
        self.task_queue = PriorityTaskQueue(max_size=queue_size)

        # 任务状态跟踪
        self.running_tasks = {}
        self.current_tasks = 0

        # 统计信息
        self.tasks_processed = 0
        self.tasks_completed = 0
        self.tasks_failed = 0

        # HTTP会话
        self.session = None

        # 执行器控制
        self._running = False
        self._executor_task = None

    async def start(self):
        """启动执行器"""
        # 启动HTTP会话
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=600)  # 10分钟超时
        )

        # 启动任务队列
        await self.task_queue.start()

        # 启动任务执行器
        self._running = True
        self._executor_task = asyncio.create_task(self._task_executor_loop())

        self.logger.info(f"AsyncTaskExecutor started with max_concurrent_tasks={self.max_concurrent_tasks}")

    async def stop(self):
        """停止执行器"""
        # 停止执行器循环
        self._running = False
        if self._executor_task:
            self._executor_task.cancel()
            try:
                await self._executor_task
            except asyncio.CancelledError:
                pass

        # 停止任务队列
        await self.task_queue.stop()

        # 关闭HTTP会话
        if self.session:
            await self.session.close()

        self.logger.info("AsyncTaskExecutor stopped")

    async def execute_task(self, task: ScheduledTask, priority: TaskPriority = TaskPriority.MEDIUM) -> bool:
        """执行任务 - 使用队列机制避免任务丢失"""
        # 创建队列任务
        queued_task = QueuedTask(
            task_id=task.task_id,
            name=task.name,
            target_service=task.target_service,
            endpoint=task.endpoint,
            payload=task.payload,
            priority=priority,
            timeout_seconds=getattr(task, 'timeout_seconds', 600)
        )

        # 入队任务
        success = await self.task_queue.enqueue(queued_task)
        if success:
            self.logger.info(f"任务已入队: {task.name} (task_id={task.task_id})")
        else:
            self.logger.error(f"任务入队失败: {task.name} (task_id={task.task_id})")

        return success

    async def _task_executor_loop(self):
        """任务执行器主循环"""
        while self._running:
            try:
                # 检查是否可以执行更多任务
                if self.current_tasks >= self.max_concurrent_tasks:
                    await asyncio.sleep(0.1)
                    continue

                # 从队列获取任务
                queued_task = await self.task_queue.dequeue()
                if queued_task is None:
                    await asyncio.sleep(0.1)
                    continue

                # 异步执行任务
                asyncio.create_task(self._execute_queued_task_async(queued_task))

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"任务执行器循环异常: {e}")
                await asyncio.sleep(1)

    async def _execute_queued_task_async(self, queued_task: QueuedTask):
        """执行队列任务"""
        task_start_time = datetime.now()

        try:
            # 更新统计
            self.tasks_processed += 1
            self.current_tasks += 1

            # 记录任务开始
            self.running_tasks[queued_task.task_id] = {
                "task": queued_task,
                "start_time": task_start_time,
                "status": "running"
            }

            self.logger.info(f"开始执行队列任务: {queued_task.name} (task_id={queued_task.task_id})")

            # 执行任务
            success = await self._execute_task_internal_queued(queued_task)

            # 标记任务完成
            self.task_queue.mark_task_completed(queued_task.task_id, success)

            if success:
                self.tasks_completed += 1
                self.metrics.increment("tasks_completed")
                self.logger.info(f"队列任务执行成功: {queued_task.name}")
            else:
                self.tasks_failed += 1
                self.metrics.increment("tasks_failed")
                self.logger.error(f"队列任务执行失败: {queued_task.name}")

        except Exception as e:
            self.tasks_failed += 1
            self.metrics.increment("tasks_failed")
            self.task_queue.mark_task_completed(queued_task.task_id, False)
            self.logger.error(f"队列任务异步执行异常: {queued_task.name}, error: {e}")

        finally:
            # 清理任务状态
            self.current_tasks -= 1
            if queued_task.task_id in self.running_tasks:
                del self.running_tasks[queued_task.task_id]

            execution_time = (datetime.now() - task_start_time).total_seconds()
            self.logger.info(f"队列任务执行完成: {queued_task.name}, 耗时: {execution_time:.2f}s")

    async def _execute_task_async(self, task: ScheduledTask):
        """异步执行任务 - 整合task-worker的异步优化"""
        task_start_time = datetime.now()

        try:
            # 更新统计
            self.tasks_processed += 1
            self.current_tasks += 1

            # 记录任务开始
            self.running_tasks[task.task_id] = {
                "task": task,
                "start_time": task_start_time,
                "status": "running"
            }

            self.logger.info(f"开始异步执行任务: {task.name} (task_id={task.task_id})")

            # 执行任务
            success = await self._execute_task_internal(task)

            if success:
                self.tasks_completed += 1
                self.metrics.increment("tasks_completed")
                self.logger.info(f"任务执行成功: {task.name}")
            else:
                self.tasks_failed += 1
                self.metrics.increment("tasks_failed")
                self.logger.error(f"任务执行失败: {task.name}")

        except Exception as e:
            self.tasks_failed += 1
            self.metrics.increment("tasks_failed")
            self.logger.error(f"任务异步执行异常: {task.name}, error: {e}")

        finally:
            # 清理任务状态
            self.current_tasks -= 1
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]

            execution_time = (datetime.now() - task_start_time).total_seconds()
            self.logger.info(f"任务执行完成: {task.name}, 耗时: {execution_time:.2f}s")

    async def _execute_task_internal(self, task: ScheduledTask) -> bool:
        """内部任务执行逻辑"""
        try:
            # 根据目标服务执行任务
            if task.target_service == "data-storage-service":
                return await self._execute_storage_task(task)
            elif task.target_service == "monitoring-service":
                return await self._execute_monitoring_task(task)
            elif task.target_service == "system":
                return await self._execute_system_task(task)
            else:
                return await self._execute_http_task(task)

        except Exception as e:
            self.logger.error(f"Task execution failed: {e}", task_id=task.task_id)
            return False

    async def _execute_task_internal_queued(self, queued_task: QueuedTask) -> bool:
        """队列任务内部执行逻辑"""
        try:
            # 根据目标服务执行任务
            if queued_task.target_service == "data-storage-service":
                return await self._execute_storage_task_queued(queued_task)
            elif queued_task.target_service == "monitoring-service":
                return await self._execute_monitoring_task_queued(queued_task)
            elif queued_task.target_service == "system":
                return await self._execute_system_task_queued(queued_task)
            else:
                return await self._execute_http_task_queued(queued_task)

        except Exception as e:
            self.logger.error(f"Queued task execution failed: {e}", task_id=queued_task.task_id)
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取执行器统计信息"""
        base_stats = {
            "tasks_processed": self.tasks_processed,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "current_tasks": self.current_tasks,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "running_tasks": len(self.running_tasks)
        }

        # 添加队列统计
        queue_stats = self.task_queue.get_stats()
        base_stats.update({
            "queue_stats": queue_stats
        })

        return base_stats

    async def _execute_storage_task(self, task: ScheduledTask) -> bool:
        """执行存储相关任务"""
        try:
            # 获取存储服务地址
            registry = get_service_registry()
            storage_service = await registry.discover_service("data-storage-service")
            
            if not storage_service:
                self.logger.error("Storage service not found")
                return False
                
            # 发送HTTP请求到存储服务
            url = f"http://{storage_service['host']}:{storage_service['port']}{task.target_endpoint}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=task.payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"Storage task completed: {result}")
                        return True
                    else:
                        self.logger.error(f"Storage task failed with status: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Storage task execution error: {e}")
            return False
            
    async def _execute_monitoring_task(self, task: ScheduledTask) -> bool:
        """执行监控相关任务"""
        try:
            # 模拟监控任务执行
            self.logger.info(f"Executing monitoring task: {task.target_endpoint}")
            
            if task.target_endpoint == "/health-check-all":
                return await self._health_check_all_services()
            elif task.target_endpoint == "/generate-report":
                return await self._generate_monitoring_report()
                
            return True
            
        except Exception as e:
            self.logger.error(f"Monitoring task execution error: {e}")
            return False
            
    async def _execute_system_task(self, task: ScheduledTask) -> bool:
        """执行系统维护任务"""
        try:
            self.logger.info(f"Executing system task: {task.target_endpoint}")
            
            if task.target_endpoint == "/cleanup-logs":
                return await self._cleanup_old_logs()
            elif task.target_endpoint == "/backup-config":
                return await self._backup_configuration()
                
            return True
            
        except Exception as e:
            self.logger.error(f"System task execution error: {e}")
            return False
            
    async def _execute_http_task(self, task: ScheduledTask) -> bool:
        """执行HTTP任务"""
        try:
            # 通用HTTP任务执行
            registry = get_service_registry()
            target_service = await registry.discover_service(task.target_service)
            
            if not target_service:
                self.logger.error(f"Target service not found: {task.target_service}")
                return False
                
            url = f"http://{target_service['host']}:{target_service['port']}{task.target_endpoint}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=task.payload) as response:
                    if response.status == 200:
                        return True
                    else:
                        self.logger.error(f"HTTP task failed with status: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"HTTP task execution error: {e}")
            return False
            
    async def _health_check_all_services(self) -> bool:
        """健康检查所有服务"""
        try:
            registry = get_service_registry()
            services = await registry.list_services()
            
            healthy_count = 0
            total_count = len(services)
            
            for service_name, service_info in services.items():
                try:
                    health_url = service_info.get('health_check_url')
                    if health_url:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                                if response.status == 200:
                                    healthy_count += 1
                                    self.logger.info(f"Service {service_name} is healthy")
                                else:
                                    self.logger.warning(f"Service {service_name} is unhealthy")
                except Exception as e:
                    self.logger.warning(f"Failed to check health of {service_name}: {e}")
                    
            self.metrics.gauge("services_total", total_count)
            self.metrics.gauge("services_healthy", healthy_count)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Health check all services failed: {e}")
            return False
            
    async def _generate_monitoring_report(self) -> bool:
        """生成监控报告"""
        try:
            # 模拟生成监控报告
            report = {
                "timestamp": datetime.now().isoformat(),
                "services_status": "healthy",
                "total_requests": 10000,
                "error_rate": 0.01,
                "avg_response_time": 150
            }
            
            self.logger.info(f"Generated monitoring report: {report}")
            return True
            
        except Exception as e:
            self.logger.error(f"Generate monitoring report failed: {e}")
            return False
            
    async def _cleanup_old_logs(self) -> bool:
        """清理旧日志"""
        try:
            # 模拟清理旧日志
            self.logger.info("Cleaning up old logs...")
            # 这里可以实现实际的日志清理逻辑
            return True
            
        except Exception as e:
            self.logger.error(f"Cleanup old logs failed: {e}")
            return False
            
    async def _backup_configuration(self) -> bool:
        """备份配置"""
        try:
            # 模拟备份配置
            self.logger.info("Backing up configuration...")
            # 这里可以实现实际的配置备份逻辑
            return True
            
        except Exception as e:
            self.logger.error(f"Backup configuration failed: {e}")
            return False


class MockTaskScheduler:
    """一个模拟的任务调度器，用于演示"""
    def __init__(self):
        self._jobs = {}
        self.logger = logging.getLogger(self.__class__.__name__)
    async def start(self):
        self.logger.info("Mock Task Scheduler started.")
    async def stop(self):
        self.logger.info("Mock Task Scheduler stopped.")
    async def add_job(self, func, trigger, **kwargs):
        job_id = f"job_{len(self._jobs) + 1}"
        self._jobs[job_id] = {"func": func, "trigger": trigger, "kwargs": kwargs}
        self.logger.info(f"Added job {job_id} with trigger {trigger}")
        return job_id
    async def get_jobs(self):
        return list(self._jobs.values())


class SchedulerService(BaseService):
    """调度微服务"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("scheduler-service", config)
        # self.scheduler = TaskScheduler(JobStore()) # 实际实现
        self.scheduler = MockTaskScheduler() # 使用模拟对象
        self.tasks: Dict[str, ScheduledTask] = {}
        # 使用增强的异步任务执行器
        max_concurrent = self.config.get('task_executor', {}).get('max_concurrent_tasks', 5)
        self.executor = AsyncTaskExecutor(self.logger, self.metrics, max_concurrent)
        self.scheduler_running = False
        
    def setup_routes(self):
        """设置API路由"""
        self.app.router.add_post('/api/v1/scheduler/jobs', self.add_job)
        self.app.router.add_get('/api/v1/scheduler/jobs', self.get_jobs)
        self.app.router.add_delete('/api/v1/scheduler/jobs/{job_id}', self.remove_job)
        self.app.router.add_post('/api/v1/scheduler/jobs/{job_id}/pause', self.pause_job)
        self.app.router.add_post('/api/v1/scheduler/jobs/{job_id}/resume', self.resume_job)
        
        # 任务管理API
        self.app.router.add_post('/api/v1/scheduler/tasks', self.create_task)
        self.app.router.add_get('/api/v1/scheduler/tasks', self.list_tasks)
        self.app.router.add_get('/api/v1/scheduler/tasks/{task_id}', self.get_task)
        self.app.router.add_put('/api/v1/scheduler/tasks/{task_id}', self.update_task)
        self.app.router.add_delete('/api/v1/scheduler/tasks/{task_id}', self.delete_task)
        
        # 任务控制API
        self.app.router.add_post('/api/v1/scheduler/tasks/{task_id}/run', self.run_task_now)
        self.app.router.add_post('/api/v1/scheduler/tasks/{task_id}/cancel', self.cancel_task)
        
        # 调度器控制API
        self.app.router.add_post('/api/v1/scheduler/start', self.start_scheduler)
        self.app.router.add_post('/api/v1/scheduler/stop', self.stop_scheduler)
        self.app.router.add_get('/api/v1/scheduler/status', self.get_scheduler_status)
        self.app.router.add_get('/api/v1/scheduler/stats', self.get_executor_stats)
        
    async def on_startup(self):
        """服务启动初始化"""
        try:
            # 启动异步任务执行器
            await self.executor.start()

            # 注册健康检查
            self.health_checker.add_check("scheduler_status", self._check_scheduler_health)

            # 创建默认任务
            await self._create_default_tasks()

            # 启动调度器
            await self._start_scheduler_loop()
            
            # 注册服务
            registry = get_service_registry()
            registry.register_service(
                service_name="scheduler-service",
                service_info={
                    "name": "scheduler-service",
                    "host": "localhost",
                    "port": self.config.get('port', 8084),
                    "health_endpoint": "/health",
                    "type": "scheduler",
                    "metadata": {
                        "version": "1.0.0",
                        "capabilities": ["task_scheduling", "cron_jobs", "distributed_tasks"]
                    }
                }
            )
            
            await self.scheduler.start()
            
            # 示例：启动一个默认的归档任务
            await self.scheduler.add_job(
                self.trigger_archiving, 'interval', seconds=self.config.get("default_archive_interval", 3600)
            )
            
            self.logger.info("Scheduler service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize scheduler service: {e}")
            raise
            
    async def on_shutdown(self):
        """服务停止清理"""
        try:
            # 停止调度器
            self.scheduler_running = False

            # 停止异步任务执行器
            await self.executor.stop()

            # 注销服务
            registry = get_service_registry()
            registry.unregister_service("scheduler-service")
            
            if self.scheduler:
                await self.scheduler.stop()
            
            self.logger.info("Scheduler service shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during scheduler service shutdown: {e}")
            
    async def _check_scheduler_health(self) -> str:
        """检查调度器健康状态"""
        if self.scheduler_running:
            return f"running_with_{len(self.tasks)}_tasks"
        else:
            return "stopped"
            
    async def _create_default_tasks(self):
        """创建默认任务"""
        # 每日数据归档任务
        archive_task = ScheduledTask(
            task_id=str(uuid.uuid4()),
            name="daily_data_archive",
            cron_expression="0 2 * * *",  # 每天凌晨2点
            target_service="data-storage-service",
            target_endpoint="/api/v1/storage/cold/archive",
            payload={"data_type": "all", "cutoff_hours": 24},
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        archive_task.next_run = CronParser.next_run_time(archive_task.cron_expression)
        self.tasks[archive_task.task_id] = archive_task
        
        # 每5分钟健康检查任务
        health_task = ScheduledTask(
            task_id=str(uuid.uuid4()),
            name="health_check_all_services",
            cron_expression="*/5 * * * *",  # 每5分钟
            target_service="monitoring-service",
            target_endpoint="/health-check-all",
            payload={},
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        health_task.next_run = CronParser.next_run_time(health_task.cron_expression)
        self.tasks[health_task.task_id] = health_task
        
        # 每小时清理过期数据任务
        cleanup_task = ScheduledTask(
            task_id=str(uuid.uuid4()),
            name="cleanup_expired_data",
            cron_expression="0 * * * *",  # 每小时
            target_service="data-storage-service",
            target_endpoint="/api/v1/storage/lifecycle/cleanup",
            payload={"retention_hours": 72},
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        cleanup_task.next_run = CronParser.next_run_time(cleanup_task.cron_expression)
        self.tasks[cleanup_task.task_id] = cleanup_task
        
        self.logger.info(f"Created {len(self.tasks)} default tasks")
        
    async def _start_scheduler_loop(self):
        """启动调度器循环"""
        self.scheduler_running = True
        asyncio.create_task(self._scheduler_loop())
        
    async def _scheduler_loop(self):
        """调度器主循环"""
        while self.scheduler_running:
            try:
                current_time = datetime.now()
                
                for task in self.tasks.values():
                    if (task.status == TaskStatus.PENDING and 
                        task.next_run and 
                        current_time >= task.next_run):
                        
                        # 执行任务
                        asyncio.create_task(self._execute_task(task))
                        
                # 每30秒检查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(60)  # 出错时等待更长时间
                
    async def _execute_task(self, task: ScheduledTask):
        """执行单个任务"""
        try:
            # 更新任务状态
            task.status = TaskStatus.RUNNING
            task.last_run = datetime.now()
            task.run_count += 1
            
            self.metrics.increment("tasks_executed")
            
            # 执行任务
            success = await self.executor.execute_task(task)
            
            if success:
                task.status = TaskStatus.COMPLETED
                self.metrics.increment("tasks_completed")
            else:
                task.status = TaskStatus.FAILED
                task.error_count += 1
                self.metrics.increment("tasks_failed")
                
            # 计算下次运行时间
            task.next_run = CronParser.next_run_time(task.cron_expression)
            task.status = TaskStatus.PENDING
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_count += 1
            task.last_error = str(e)
            self.logger.error(f"Task execution error: {e}", task_id=task.task_id)
            self.metrics.increment("tasks_failed")
            
    # ==================== API Handlers ====================
    
    async def add_job(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "error", "message": "Not implemented"}, status=501)
    
    async def get_jobs(self, request: web.Request) -> web.Response:
        jobs = await self.scheduler.get_jobs()
        return web.json_response({"status": "success", "jobs": jobs})

    async def remove_job(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "error", "message": "Not implemented"}, status=501)

    async def pause_job(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "error", "message": "Not implemented"}, status=501)

    async def resume_job(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "error", "message": "Not implemented"}, status=501)

    # ==================== 任务管理API ====================
    
    async def create_task(self, request):
        """创建新任务"""
        try:
            data = await request.json()
            
            task = ScheduledTask(
                task_id=str(uuid.uuid4()),
                name=data['name'],
                cron_expression=data['cron_expression'],
                target_service=data['target_service'],
                target_endpoint=data['target_endpoint'],
                payload=data.get('payload', {}),
                status=TaskStatus.PENDING,
                created_at=datetime.now()
            )
            
            # 计算下次运行时间
            task.next_run = CronParser.next_run_time(task.cron_expression)
            
            self.tasks[task.task_id] = task
            self.metrics.increment("tasks_created")
            
            return web.json_response({
                "status": "success",
                "task_id": task.task_id,
                "message": "Task created successfully",
                "next_run": task.next_run.isoformat() if task.next_run else None
            })
            
        except Exception as e:
            self.logger.error(f"Failed to create task: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def list_tasks(self, request):
        """列出所有任务"""
        try:
            tasks_data = []
            for task in self.tasks.values():
                tasks_data.append({
                    "task_id": task.task_id,
                    "name": task.name,
                    "cron_expression": task.cron_expression,
                    "target_service": task.target_service,
                    "target_endpoint": task.target_endpoint,
                    "status": task.status.value,
                    "created_at": task.created_at.isoformat(),
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "next_run": task.next_run.isoformat() if task.next_run else None,
                    "run_count": task.run_count,
                    "error_count": task.error_count
                })
                
            return web.json_response({
                "status": "success",
                "data": tasks_data,
                "count": len(tasks_data),
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to list tasks: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def get_task(self, request):
        """获取单个任务详情"""
        try:
            task_id = request.match_info['task_id']
            task = self.tasks.get(task_id)
            
            if not task:
                return web.json_response({
                    "status": "not_found",
                    "message": f"Task {task_id} not found"
                }, status=404)
                
            return web.json_response({
                "status": "success",
                "data": {
                    "task_id": task.task_id,
                    "name": task.name,
                    "cron_expression": task.cron_expression,
                    "target_service": task.target_service,
                    "target_endpoint": task.target_endpoint,
                    "payload": task.payload,
                    "status": task.status.value,
                    "created_at": task.created_at.isoformat(),
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "next_run": task.next_run.isoformat() if task.next_run else None,
                    "run_count": task.run_count,
                    "error_count": task.error_count,
                    "last_error": task.last_error
                }
            })
            
        except Exception as e:
            self.logger.error(f"Failed to get task: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def update_task(self, request):
        """更新任务"""
        try:
            task_id = request.match_info['task_id']
            task = self.tasks.get(task_id)
            
            if not task:
                return web.json_response({
                    "status": "not_found",
                    "message": f"Task {task_id} not found"
                }, status=404)
                
            data = await request.json()
            
            # 更新任务属性
            if 'name' in data:
                task.name = data['name']
            if 'cron_expression' in data:
                task.cron_expression = data['cron_expression']
                task.next_run = CronParser.next_run_time(task.cron_expression)
            if 'target_service' in data:
                task.target_service = data['target_service']
            if 'target_endpoint' in data:
                task.target_endpoint = data['target_endpoint']
            if 'payload' in data:
                task.payload = data['payload']
                
            self.metrics.increment("tasks_updated")
            
            return web.json_response({
                "status": "success",
                "message": "Task updated successfully",
                "next_run": task.next_run.isoformat() if task.next_run else None
            })
            
        except Exception as e:
            self.logger.error(f"Failed to update task: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def delete_task(self, request):
        """删除任务"""
        try:
            task_id = request.match_info['task_id']
            
            if task_id not in self.tasks:
                return web.json_response({
                    "status": "not_found",
                    "message": f"Task {task_id} not found"
                }, status=404)
                
            del self.tasks[task_id]
            self.metrics.increment("tasks_deleted")
            
            return web.json_response({
                "status": "success",
                "message": "Task deleted successfully"
            })
            
        except Exception as e:
            self.logger.error(f"Failed to delete task: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def run_task_now(self, request):
        """立即运行任务"""
        try:
            task_id = request.match_info['task_id']
            task = self.tasks.get(task_id)
            
            if not task:
                return web.json_response({
                    "status": "not_found",
                    "message": f"Task {task_id} not found"
                }, status=404)
                
            # 异步执行任务
            asyncio.create_task(self._execute_task(task))
            
            return web.json_response({
                "status": "success",
                "message": "Task execution started"
            })
            
        except Exception as e:
            self.logger.error(f"Failed to run task now: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def cancel_task(self, request):
        """取消任务"""
        try:
            task_id = request.match_info['task_id']
            task = self.tasks.get(task_id)
            
            if not task:
                return web.json_response({
                    "status": "not_found",
                    "message": f"Task {task_id} not found"
                }, status=404)
                
            task.status = TaskStatus.CANCELLED
            self.metrics.increment("tasks_cancelled")
            
            return web.json_response({
                "status": "success",
                "message": "Task cancelled successfully"
            })
            
        except Exception as e:
            self.logger.error(f"Failed to cancel task: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def start_scheduler(self, request):
        """启动调度器"""
        try:
            if not self.scheduler_running:
                await self._start_scheduler_loop()
                
            return web.json_response({
                "status": "success",
                "message": "Scheduler started successfully"
            })
            
        except Exception as e:
            self.logger.error(f"Failed to start scheduler: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def stop_scheduler(self, request):
        """停止调度器"""
        try:
            self.scheduler_running = False
            
            return web.json_response({
                "status": "success",
                "message": "Scheduler stopped successfully"
            })
            
        except Exception as e:
            self.logger.error(f"Failed to stop scheduler: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def get_scheduler_status(self, request):
        """获取调度器状态"""
        try:
            status_data = {
                "scheduler_running": self.scheduler_running,
                "total_tasks": len(self.tasks),
                "pending_tasks": len([t for t in self.tasks.values() if t.status == TaskStatus.PENDING]),
                "running_tasks": len([t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]),
                "completed_tasks": len([t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]),
                "failed_tasks": len([t for t in self.tasks.values() if t.status == TaskStatus.FAILED]),
                "cancelled_tasks": len([t for t in self.tasks.values() if t.status == TaskStatus.CANCELLED]),
                "timestamp": datetime.now().isoformat()
            }
            
            return web.json_response({
                "status": "success",
                "data": status_data
            })
            
        except Exception as e:
            self.logger.error(f"Failed to get scheduler status: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    async def get_executor_stats(self, request):
        """获取任务执行器统计信息"""
        try:
            stats = self.executor.get_stats()
            return web.json_response({
                "status": "success",
                "data": stats
            })
        except Exception as e:
            self.logger.error(f"Failed to get executor stats: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    async def trigger_archiving(self):
        """这是一个由调度器触发的任务示例"""
        self.logger.info("Triggering data archiving task...")
        # 在实际应用中，这里会调用 data-storage-service 的归档API
        # ...


async def main():
    """服务主入口点"""
    try:
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / 'config' / 'services.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f) or {}
        
        service_config = full_config.get('services', {}).get('scheduler-service', {})
        
        service = SchedulerService(config=service_config)
        await service.run()

    except Exception:
        logging.basicConfig()
        logging.critical("Scheduler Service failed to start", exc_info=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

# 在AsyncTaskExecutor类中添加队列版本的执行方法
def add_queued_task_methods():
    """为AsyncTaskExecutor添加队列版本的任务执行方法"""

    async def _execute_storage_task_queued(self, queued_task: QueuedTask) -> bool:
        """执行存储相关队列任务"""
        try:
            # 获取存储服务地址
            registry = get_service_registry()
            storage_service = await registry.discover_service("data-storage-service")

            if not storage_service:
                self.logger.error("Storage service not found")
                return False

            url = f"http://{storage_service['host']}:{storage_service['port']}{queued_task.endpoint}"

            async with self.session.post(url, json=queued_task.payload) as response:
                if response.status == 200:
                    self.logger.info(f"Storage task completed: {queued_task.name}")
                    return True
                else:
                    self.logger.error(f"Storage task failed: {queued_task.name}, status: {response.status}")
                    return False

        except Exception as e:
            self.logger.error(f"Storage task execution error: {e}")
            return False

    async def _execute_monitoring_task_queued(self, queued_task: QueuedTask) -> bool:
        """执行监控相关队列任务"""
        try:
            # 获取监控服务地址
            registry = get_service_registry()
            monitoring_service = await registry.discover_service("monitoring-alerting-service")

            if not monitoring_service:
                self.logger.error("Monitoring service not found")
                return False

            url = f"http://{monitoring_service['host']}:{monitoring_service['port']}{queued_task.endpoint}"

            async with self.session.post(url, json=queued_task.payload) as response:
                if response.status == 200:
                    self.logger.info(f"Monitoring task completed: {queued_task.name}")
                    return True
                else:
                    self.logger.error(f"Monitoring task failed: {queued_task.name}, status: {response.status}")
                    return False

        except Exception as e:
            self.logger.error(f"Monitoring task execution error: {e}")
            return False

    async def _execute_system_task_queued(self, queued_task: QueuedTask) -> bool:
        """执行系统相关队列任务"""
        try:
            # 系统任务通常是本地操作
            if queued_task.name == "cleanup":
                # 执行清理任务
                await self.task_queue.cleanup_old_tasks()
                self.logger.info("System cleanup task completed")
                return True
            else:
                self.logger.warning(f"Unknown system task: {queued_task.name}")
                return False

        except Exception as e:
            self.logger.error(f"System task execution error: {e}")
            return False

    async def _execute_http_task_queued(self, queued_task: QueuedTask) -> bool:
        """执行通用HTTP队列任务"""
        try:
            # 构建完整URL
            if queued_task.endpoint.startswith('http'):
                url = queued_task.endpoint
            else:
                # 需要服务发现
                registry = get_service_registry()
                service = await registry.discover_service(queued_task.target_service)
                if not service:
                    self.logger.error(f"Service not found: {queued_task.target_service}")
                    return False
                url = f"http://{service['host']}:{service['port']}{queued_task.endpoint}"

            async with self.session.post(url, json=queued_task.payload) as response:
                if response.status == 200:
                    self.logger.info(f"HTTP task completed: {queued_task.name}")
                    return True
                else:
                    self.logger.error(f"HTTP task failed: {queued_task.name}, status: {response.status}")
                    return False

        except Exception as e:
            self.logger.error(f"HTTP task execution error: {e}")
            return False

    # 将方法添加到AsyncTaskExecutor类
    AsyncTaskExecutor._execute_storage_task_queued = _execute_storage_task_queued
    AsyncTaskExecutor._execute_monitoring_task_queued = _execute_monitoring_task_queued
    AsyncTaskExecutor._execute_system_task_queued = _execute_system_task_queued
    AsyncTaskExecutor._execute_http_task_queued = _execute_http_task_queued

# 调用函数添加方法
add_queued_task_methods()


if __name__ == "__main__":
    # ... (日志配置) ...
    asyncio.run(main())