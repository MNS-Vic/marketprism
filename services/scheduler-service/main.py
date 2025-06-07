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

from core.service_framework import BaseService, get_service_registry


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


class TaskExecutor:
    """任务执行器"""
    
    def __init__(self, logger, metrics):
        self.logger = logger
        self.metrics = metrics
        
    async def execute_task(self, task: ScheduledTask) -> bool:
        """执行任务"""
        try:
            self.logger.info(f"Executing task: {task.name}", task_id=task.task_id)
            
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


class SchedulerService(BaseService):
    """调度服务"""
    
    def __init__(self):
        super().__init__("scheduler-service")
        self.tasks: Dict[str, ScheduledTask] = {}
        self.executor = TaskExecutor(self.logger, self.metrics)
        self.scheduler_running = False
        
    async def setup_routes(self):
        """设置API路由"""
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
        
    async def on_startup(self):
        """服务启动初始化"""
        try:
            # 注册健康检查
            self.health_checker.add_check("scheduler_status", self._check_scheduler_health)
            
            # 创建默认任务
            await self._create_default_tasks()
            
            # 启动调度器
            await self._start_scheduler_loop()
            
            # 注册服务
            registry = get_service_registry()
            await registry.register_service(
                service_name="scheduler-service",
                host="localhost",
                port=self.config.get('port', 8081),
                metadata={
                    "version": "1.0.0",
                    "capabilities": ["task_scheduling", "cron_jobs", "distributed_tasks"]
                }
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
            
            # 注销服务
            registry = get_service_registry()
            await registry.deregister_service("scheduler-service")
            
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
            
            self.metrics.counter("tasks_executed")
            
            # 执行任务
            success = await self.executor.execute_task(task)
            
            if success:
                task.status = TaskStatus.COMPLETED
                self.metrics.counter("tasks_completed")
            else:
                task.status = TaskStatus.FAILED
                task.error_count += 1
                self.metrics.counter("tasks_failed")
                
            # 计算下次运行时间
            task.next_run = CronParser.next_run_time(task.cron_expression)
            task.status = TaskStatus.PENDING
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_count += 1
            task.last_error = str(e)
            self.logger.error(f"Task execution error: {e}", task_id=task.task_id)
            self.metrics.counter("tasks_failed")
            
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
            self.metrics.counter("tasks_created")
            
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
                
            self.metrics.counter("tasks_updated")
            
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
            self.metrics.counter("tasks_deleted")
            
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
            self.metrics.counter("tasks_cancelled")
            
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


async def main():
    """主函数"""
    service = SchedulerService()
    await service.start()


if __name__ == "__main__":
    asyncio.run(main())