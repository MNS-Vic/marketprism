"""
MarketPrism 任务工作者 - NATS任务队列消费者
实现异步任务执行：scheduler → NATS → task-workers
"""

import asyncio
import json
import logging
import uuid
import aiohttp
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
import nats
from nats.js import JetStreamContext
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy
import traceback
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.task_system.task_types import AsyncTask, TaskEvent, TaskEventType, TaskStatus, TaskPriority, TaskSubjects

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器"""
    
    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.session = None
    
    async def start(self):
        """启动执行器"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=600)  # 10分钟超时
        )
    
    async def stop(self):
        """停止执行器"""
        if self.session:
            await self.session.close()
    
    async def execute_task(self, task: AsyncTask) -> Dict[str, Any]:
        """
        执行任务
        
        Args:
            task: 任务对象
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            logger.info(
                f"开始执行任务: task_id={task.task_id}, "
                f"name={task.name}, type={task.task_type}, "
                f"target={task.target_service}"
            )
            
            # 根据目标服务类型执行任务
            if task.target_service == "data-storage-service":
                result = await self._execute_storage_task(task)
            elif task.target_service == "data-collector":
                result = await self._execute_collector_task(task)
            elif task.target_service == "monitoring-service":
                result = await self._execute_monitoring_task(task)
            elif task.target_service == "system":
                result = await self._execute_system_task(task)
            else:
                result = await self._execute_http_task(task)
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            logger.info(
                f"任务执行成功: task_id={task.task_id}, "
                f"execution_time={execution_time:.2f}s"
            )
            
            return {
                "success": True,
                "execution_time": execution_time,
                "result": result,
                "worker_id": self.worker_id,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = str(e)
            
            logger.error(
                f"任务执行失败: task_id={task.task_id}, "
                f"error={error_msg}, execution_time={execution_time:.2f}s"
            )
            
            return {
                "success": False,
                "execution_time": execution_time,
                "error": error_msg,
                "worker_id": self.worker_id,
                "failed_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def _execute_storage_task(self, task: AsyncTask) -> Dict[str, Any]:
        """执行存储服务任务"""
        try:
            # 构建URL
            base_url = self._get_service_url("data-storage-service", 8083)
            url = f"{base_url}{task.target_endpoint}"
            
            # 发送请求
            async with self.session.post(url, json=task.payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"status": "success", "data": result}
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
                    
        except Exception as e:
            raise Exception(f"存储任务执行失败: {e}")
    
    async def _execute_collector_task(self, task: AsyncTask) -> Dict[str, Any]:
        """执行数据收集任务"""
        try:
            # 构建URL
            base_url = self._get_service_url("data-collector", 8084)
            url = f"{base_url}{task.target_endpoint}"
            
            # 发送请求
            async with self.session.post(url, json=task.payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"status": "success", "data": result}
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
                    
        except Exception as e:
            raise Exception(f"数据收集任务执行失败: {e}")
    
    async def _execute_monitoring_task(self, task: AsyncTask) -> Dict[str, Any]:
        """执行监控任务"""
        try:
            # 构建URL
            base_url = self._get_service_url("monitoring-service", 8082)
            url = f"{base_url}{task.target_endpoint}"
            
            # 发送请求
            async with self.session.get(url, params=task.payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"status": "success", "data": result}
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
                    
        except Exception as e:
            raise Exception(f"监控任务执行失败: {e}")
    
    async def _execute_system_task(self, task: AsyncTask) -> Dict[str, Any]:
        """执行系统任务"""
        try:
            # 系统任务通常是内部操作
            task_name = task.name.lower()
            
            if "health" in task_name:
                return await self._system_health_check()
            elif "cleanup" in task_name:
                return await self._system_cleanup()
            elif "backup" in task_name:
                return await self._system_backup()
            else:
                return {"status": "success", "message": f"系统任务 {task.name} 执行完成"}
                
        except Exception as e:
            raise Exception(f"系统任务执行失败: {e}")
    
    async def _execute_http_task(self, task: AsyncTask) -> Dict[str, Any]:
        """执行通用HTTP任务"""
        try:
            # 构建URL
            base_url = self._get_service_url(task.target_service, 8080)
            url = f"{base_url}{task.target_endpoint}"
            
            # 发送请求
            async with self.session.post(url, json=task.payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"status": "success", "data": result}
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
                    
        except Exception as e:
            raise Exception(f"HTTP任务执行失败: {e}")
    
    def _get_service_url(self, service_name: str, default_port: int) -> str:
        """获取服务URL"""
        # 映射到实际的Docker服务名
        service_mapping = {
            "data-storage-service": "marketprism-data-storage-hot-test",
            "monitoring-service": "marketprism-monitoring-alerting",
            "data-collector": "marketprism-market-data-collector-test"
        }

        actual_host = service_mapping.get(service_name, service_name)
        return f"http://{actual_host}:{default_port}"
    
    async def _system_health_check(self) -> Dict[str, Any]:
        """系统健康检查"""
        # 模拟健康检查
        await asyncio.sleep(1)
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "cpu": "ok",
                "memory": "ok",
                "disk": "ok"
            }
        }
    
    async def _system_cleanup(self) -> Dict[str, Any]:
        """系统清理"""
        # 模拟清理操作
        await asyncio.sleep(2)
        return {
            "status": "completed",
            "cleaned_files": 150,
            "freed_space_mb": 1024
        }
    
    async def _system_backup(self) -> Dict[str, Any]:
        """系统备份"""
        # 模拟备份操作
        await asyncio.sleep(5)
        return {
            "status": "completed",
            "backup_size_mb": 2048,
            "backup_location": "/backups/backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        }


class NATSTaskWorker:
    """NATS任务工作者 - 异步消费和执行任务"""
    
    def __init__(self, worker_id: Optional[str] = None, 
                 nats_url: str = "nats://localhost:4222",
                 worker_type: str = "general",
                 max_concurrent_tasks: int = 5):
        """
        初始化NATS任务工作者
        
        Args:
            worker_id: 工作者ID
            nats_url: NATS服务器URL
            worker_type: 工作者类型
            max_concurrent_tasks: 最大并发任务数
        """
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.nats_url = nats_url
        self.worker_type = worker_type
        self.max_concurrent_tasks = max_concurrent_tasks
        
        self.nc = None
        self.js = None
        self.subscriptions = []
        self.is_running = False
        
        # 统计信息
        self.tasks_processed = 0
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.current_tasks = 0
        self.start_time = None
        
        # 任务执行器
        self.executor = TaskExecutor(self.worker_id)
        
        # 当前执行的任务
        self.running_tasks = {}
        
        logger.info(f"NATS任务工作者初始化完成: worker_id={self.worker_id}")
    
    async def start(self):
        """启动NATS任务工作者"""
        if self.is_running:
            logger.warning("NATS任务工作者已在运行")
            return
        
        try:
            logger.info(f"启动NATS任务工作者: {self.worker_id}")
            
            # 启动执行器
            await self.executor.start()
            
            # 连接到NATS
            self.nc = await nats.connect(
                servers=[self.nats_url],
                name=f"marketprism-task-worker-{self.worker_id}",
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
                error_cb=self._error_callback,
                disconnected_cb=self._disconnected_callback,
                reconnected_cb=self._reconnected_callback,
                connect_timeout=30,  # 30秒连接超时
                max_outstanding_pings=5,
                ping_interval=20
            )

            # 获取JetStream上下文
            self.js = self.nc.jetstream()

            # 确保流存在
            await self._ensure_streams_exist()

            # 设置订阅
            await self._setup_subscriptions()
            
            # 启动心跳
            asyncio.create_task(self._heartbeat_loop())
            
            self.is_running = True
            self.start_time = datetime.now(timezone.utc)
            
            logger.info(f"✅ NATS任务工作者启动成功: {self.worker_id}")
            
        except Exception as e:
            logger.error(f"❌ NATS任务工作者启动失败: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def stop(self):
        """停止NATS任务工作者"""
        if not self.is_running:
            return
        
        logger.info(f"停止NATS任务工作者: {self.worker_id}")
        
        self.is_running = False
        
        # 等待当前任务完成
        if self.running_tasks:
            logger.info(f"等待 {len(self.running_tasks)} 个任务完成...")
            await asyncio.sleep(5)  # 给任务一些时间完成
        
        # 取消所有订阅
        for subscription in self.subscriptions:
            try:
                await subscription.unsubscribe()
            except Exception as e:
                logger.error(f"取消订阅失败: {e}")
        
        # 停止执行器
        await self.executor.stop()
        
        # 关闭连接
        if self.nc:
            await self.nc.close()
        
        logger.info(f"✅ NATS任务工作者已停止: {self.worker_id}")

    async def _ensure_streams_exist(self):
        """确保NATS流存在"""
        try:
            logger.info("检查并创建必要的NATS流...")

            # 检查现有流
            try:
                streams = await self.js.streams_info()
                existing_streams = {stream.config.name for stream in streams}
                logger.info(f"现有流: {existing_streams}")
            except Exception as e:
                logger.warning(f"无法获取现有流信息: {e}")
                existing_streams = set()

            # 创建TASKS流（如果不存在）
            if "TASKS" not in existing_streams:
                try:
                    await self.js.add_stream(name="TASKS", subjects=["tasks.>"])
                    logger.info("✅ TASKS流创建成功")
                except Exception as e:
                    logger.warning(f"创建TASKS流时出现问题: {e}")
            else:
                logger.info("TASKS流已存在")

            # 跳过TASK_EVENTS流创建，因为可能与ALERTS流冲突
            logger.info("跳过TASK_EVENTS流创建（避免主题冲突）")

            # 创建WORKERS流（如果不存在）
            if "WORKERS" not in existing_streams:
                try:
                    await self.js.add_stream(name="WORKERS", subjects=["workers.>"])
                    logger.info("✅ WORKERS流创建成功")
                except Exception as e:
                    logger.warning(f"创建WORKERS流时出现问题: {e}")
            else:
                logger.info("WORKERS流已存在")

        except Exception as e:
            logger.error(f"❌ 确保流存在失败: {e}")
            # 不要抛出异常，继续尝试订阅
            logger.warning("继续尝试订阅现有流...")

    async def _setup_subscriptions(self):
        """设置NATS订阅"""
        try:
            logger.info("开始设置NATS订阅...")

            # 使用非持久化消费者避免冲突
            import time
            timestamp = int(time.time())

            # 订阅特定的任务队列，避免重复处理
            subject = "tasks.queue.medium"  # 先只订阅medium优先级队列

            logger.info(f"尝试订阅主题: {subject}")

            try:
                # 使用queue group确保负载均衡
                queue_group = f"task-workers-{self.worker_type}"

                # 使用持久化消费者配置，但每个worker有唯一的消费者名
                consumer_config = ConsumerConfig(
                    durable_name=f"worker-{self.worker_type}-{timestamp}",
                    deliver_policy=DeliverPolicy.NEW,
                    ack_policy=AckPolicy.EXPLICIT,
                    max_deliver=3,
                    ack_wait=120,  # 2分钟
                    max_ack_pending=1  # 每次只处理一个消息
                )

                # 使用较长的超时时间
                subscription = await asyncio.wait_for(
                    self.js.subscribe(
                        subject=subject,
                        stream="TASKS",
                        config=consumer_config,
                        cb=self._task_message_handler,
                        queue=queue_group  # 关键：使用queue group
                    ),
                    timeout=30.0  # 30秒超时
                )

                self.subscriptions.append(subscription)
                logger.info(f"✅ 订阅任务队列成功: {subject}, queue_group: {queue_group}")

            except asyncio.TimeoutError:
                logger.error(f"❌ 订阅任务队列超时: {subject}")
                # 尝试使用更简单的订阅方式
                logger.info("尝试使用基本NATS订阅...")

                # 回退到基本NATS订阅
                subscription = await self.nc.subscribe(
                    subject="tasks.simple",
                    cb=self._simple_message_handler
                )

                self.subscriptions.append(subscription)
                logger.info("✅ 使用基本NATS订阅成功")

            except Exception as e:
                logger.error(f"❌ 订阅任务队列失败: {subject}, error: {e}")
                # 尝试基本订阅作为回退
                logger.info("尝试使用基本NATS订阅作为回退...")

                subscription = await self.nc.subscribe(
                    subject="tasks.simple",
                    cb=self._simple_message_handler
                )

                self.subscriptions.append(subscription)
                logger.info("✅ 基本NATS订阅成功")

            logger.info(f"✅ 订阅设置完成，共 {len(self.subscriptions)} 个订阅")

        except Exception as e:
            logger.error(f"❌ 设置订阅失败: {e}")
            raise

    async def _simple_message_handler(self, msg):
        """简单消息处理器（基本NATS）"""
        try:
            self.tasks_processed += 1
            self.current_tasks += 1

            # 解析任务消息
            data = json.loads(msg.data.decode('utf-8'))

            logger.info(f"收到简单任务消息: {data.get('name', 'unknown')}")

            # 模拟任务处理
            await asyncio.sleep(1)

            self.tasks_completed += 1
            logger.info("简单任务处理完成")

        except Exception as e:
            self.tasks_failed += 1
            logger.error(f"简单任务处理失败: {e}")
        finally:
            self.current_tasks -= 1

    async def _task_message_handler(self, msg):
        """任务消息处理器"""
        if self.current_tasks >= self.max_concurrent_tasks:
            # 如果达到最大并发数，不确认消息，让其他worker处理
            logger.warning(f"达到最大并发数 {self.max_concurrent_tasks}，跳过任务")
            return

        try:
            # 检查消息是否已被确认
            if hasattr(msg, '_ackd') and msg._ackd:
                logger.warning(f"消息已被确认，跳过处理: {msg.subject}")
                return

            self.tasks_processed += 1
            self.current_tasks += 1

            # 解析任务消息
            data = json.loads(msg.data.decode('utf-8'))
            task = AsyncTask.from_message(data)

            # 检查是否已在处理此任务
            if task.task_id in self.running_tasks:
                logger.warning(f"任务已在处理中，跳过: {task.task_id}")
                self.current_tasks -= 1
                return

            logger.info(
                f"[{self.worker_id}] 收到任务: task_id={task.task_id}, "
                f"name={task.name}, priority={task.priority}"
            )

            # 异步执行任务
            asyncio.create_task(self._execute_task_async(task, msg))

        except Exception as e:
            self.current_tasks -= 1
            logger.error(f"任务消息处理失败: {e}")
            logger.error(traceback.format_exc())

            # 确认消息避免无限重试
            try:
                if not (hasattr(msg, '_ackd') and msg._ackd):
                    await msg.ack()
            except Exception as ack_error:
                logger.error(f"消息确认失败: {ack_error}")

    async def _execute_task_async(self, task: AsyncTask, msg):
        """异步执行任务"""
        task_start_time = datetime.now(timezone.utc)
        message_acked = False

        try:
            # 记录任务开始
            self.running_tasks[task.task_id] = {
                "task": task,
                "start_time": task_start_time,
                "worker_id": self.worker_id,
                "msg": msg
            }

            logger.info(f"[{self.worker_id}] 开始执行任务: {task.task_id}")

            # 发布任务开始事件
            await self._publish_task_event(task.task_id, TaskEventType.STARTED)

            # 执行任务
            result = await self.executor.execute_task(task)

            if result["success"]:
                self.tasks_completed += 1
                await self._publish_task_event(
                    task.task_id,
                    TaskEventType.COMPLETED,
                    result=result
                )
                logger.info(f"[{self.worker_id}] 任务执行成功: {task.task_id}")
            else:
                self.tasks_failed += 1
                await self._publish_task_event(
                    task.task_id,
                    TaskEventType.FAILED,
                    error=result.get("error")
                )
                logger.error(f"[{self.worker_id}] 任务执行失败: {task.task_id}, error={result.get('error')}")

            # 确认消息（只确认一次）
            try:
                if not (hasattr(msg, '_ackd') and msg._ackd):
                    await msg.ack()
                    message_acked = True
                    logger.debug(f"[{self.worker_id}] 消息已确认: {task.task_id}")
            except Exception as ack_error:
                logger.error(f"[{self.worker_id}] 消息确认失败: {task.task_id}, error={ack_error}")

        except Exception as e:
            self.tasks_failed += 1
            logger.error(f"[{self.worker_id}] 任务执行异常: {task.task_id}, error={e}")

            # 发布任务失败事件
            await self._publish_task_event(
                task.task_id,
                TaskEventType.FAILED,
                error=str(e)
            )

            # 确认消息
            try:
                if not message_acked and not (hasattr(msg, '_ackd') and msg._ackd):
                    await msg.ack()
                    logger.debug(f"[{self.worker_id}] 异常情况下消息已确认: {task.task_id}")
            except Exception as ack_error:
                logger.error(f"[{self.worker_id}] 异常情况下消息确认失败: {task.task_id}, error={ack_error}")

        finally:
            # 清理任务记录
            if task.task_id in self.running_tasks:
                del self.running_tasks[task.task_id]
            self.current_tasks -= 1
            logger.debug(f"[{self.worker_id}] 任务清理完成: {task.task_id}")

    async def _publish_task_event(self, task_id: str, event_type: TaskEventType,
                                 progress: Optional[float] = None,
                                 message: Optional[str] = None,
                                 error: Optional[str] = None,
                                 result: Optional[Dict[str, Any]] = None):
        """发布任务事件"""
        try:
            # 创建事件
            event = {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "task_id": task_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "worker_id": self.worker_id,
                "progress": progress,
                "message": message,
                "error": error,
                "result": result
            }

            # 发布事件
            subject = TaskSubjects.get_event_subject(task_id, event_type)
            message_data = json.dumps(event, ensure_ascii=False, default=str)

            await self.js.publish(
                subject=subject,
                payload=message_data.encode('utf-8'),
                headers={
                    'event-type': str(event_type),
                    'task-id': task_id,
                    'worker-id': self.worker_id
                }
            )

        except Exception as e:
            logger.error(f"发布任务事件失败: {e}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.is_running:
            try:
                # 发布心跳
                heartbeat = {
                    "worker_id": self.worker_id,
                    "worker_type": self.worker_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "running",
                    "current_tasks": self.current_tasks,
                    "max_concurrent_tasks": self.max_concurrent_tasks,
                    "tasks_processed": self.tasks_processed,
                    "tasks_completed": self.tasks_completed,
                    "tasks_failed": self.tasks_failed,
                    "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds() if self.start_time else 0
                }

                subject = f"workers.heartbeat.{self.worker_id}"
                message_data = json.dumps(heartbeat, ensure_ascii=False, default=str)

                await self.js.publish(
                    subject=subject,
                    payload=message_data.encode('utf-8'),
                    headers={
                        'worker-id': self.worker_id,
                        'worker-type': self.worker_type
                    }
                )

                # 每30秒发送一次心跳
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                await asyncio.sleep(60)

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
        """获取工作者统计信息"""
        uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds() if self.start_time else 0

        return {
            "worker_id": self.worker_id,
            "worker_type": self.worker_type,
            "is_running": self.is_running,
            "current_tasks": self.current_tasks,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "tasks_processed": self.tasks_processed,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "success_rate": (self.tasks_completed / self.tasks_processed * 100) if self.tasks_processed > 0 else 0,
            "uptime_seconds": uptime,
            "running_tasks": list(self.running_tasks.keys()),
            "nats_connected": self.nc.is_connected if self.nc else False
        }
