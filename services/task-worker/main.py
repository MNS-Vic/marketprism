"""
MarketPrism 任务工作者服务 - 重构版本
基于BaseService框架的分布式任务处理服务
"""

import asyncio
import logging
import os
import sys
import yaml
from typing import Dict, Any, List
from aiohttp import web
import json
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
# 在Docker容器中，工作目录就是/app，core目录在/app/core
project_root = Path(__file__).resolve().parent
if not (project_root / 'core').exists():
    # 如果当前目录没有core，尝试上级目录
    project_root = project_root.parent
sys.path.insert(0, str(project_root))

# 导入BaseService框架
from core.service_framework import BaseService

# 导入NATS任务工作者
from nats_task_worker import NATSTaskWorker

# 配置日志
import structlog
logger = structlog.get_logger(__name__)


class TaskWorkerService(BaseService):
    """
    任务工作者服务 - 基于BaseService框架
    
    提供分布式任务处理功能：
    - NATS分布式任务队列
    - 多worker负载均衡
    - 动态扩容/缩容
    - 任务状态监控
    - 故障转移和重试
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("task-worker", config)
        
        # 工作者管理
        self.workers: List[NATSTaskWorker] = []
        
        # 服务配置
        self.worker_count = config.get('worker_count', 3)
        self.worker_type = config.get('worker_type', 'general')
        self.max_concurrent_tasks = config.get('max_concurrent_tasks', 5)
        self.nats_url = config.get('nats_url', os.getenv("NATS_URL", "nats://nats:4222"))
        
        # 统计信息
        self.stats = {
            'total_workers': 0,
            'running_workers': 0,
            'total_max_concurrent': 0,
            'tasks_processed': 0,
            'tasks_failed': 0,
            'last_scale_time': None
        }

        # 记录服务启动时间
        self.start_time = datetime.now()

        self.logger.info(f"任务工作者服务初始化完成: worker_count={self.worker_count}")

    def setup_routes(self):
        """设置API路由"""
        # 标准化API端点
        self.app.router.add_get('/api/v1/status', self._get_service_status)

        # Task Worker特有的API端点
        self.app.router.add_get('/api/v1/workers/status', self._get_workers_status)
        self.app.router.add_get('/api/v1/workers/stats', self._get_workers_stats)
        self.app.router.add_get('/api/v1/workers', self._get_workers_list)
        self.app.router.add_post('/api/v1/workers/scale', self._scale_workers)
        self.app.router.add_get('/api/v1/tasks/stats', self._get_task_stats)
        self.app.router.add_post('/api/v1/tasks/submit', self._submit_task)

        # 兼容性路由（保持向后兼容）
        self.app.router.add_get('/status', self._get_service_status)
        self.app.router.add_get('/workers', self._get_workers_list)

    def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
        """
        创建标准化成功响应

        Args:
            data: 响应数据
            message: 成功消息

        Returns:
            标准化的成功响应
        """
        return web.json_response({
            "status": "success",
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })

    def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                              status_code: int = 500) -> web.Response:
        """
        创建标准化错误响应

        Args:
            message: 错误描述信息
            error_code: 标准化错误代码
            status_code: HTTP状态码

        Returns:
            标准化的错误响应
        """
        return web.json_response({
            "status": "error",
            "error_code": error_code,
            "message": message,
            "data": None,
            "timestamp": datetime.now().isoformat()
        }, status=status_code)

    # 标准化错误代码常量
    ERROR_CODES = {
        'WORKER_START_ERROR': 'WORKER_START_ERROR',
        'WORKER_STOP_ERROR': 'WORKER_STOP_ERROR',
        'WORKER_NOT_FOUND': 'WORKER_NOT_FOUND',
        'TASK_SUBMISSION_ERROR': 'TASK_SUBMISSION_ERROR',
        'TASK_EXECUTION_ERROR': 'TASK_EXECUTION_ERROR',
        'NATS_CONNECTION_ERROR': 'NATS_CONNECTION_ERROR',
        'SCALING_ERROR': 'SCALING_ERROR',
        'INVALID_WORKER_CONFIG': 'INVALID_WORKER_CONFIG',
        'INVALID_TASK_DATA': 'INVALID_TASK_DATA',
        'INVALID_PARAMETERS': 'INVALID_PARAMETERS',
        'SERVICE_UNAVAILABLE': 'SERVICE_UNAVAILABLE',
        'INTERNAL_ERROR': 'INTERNAL_ERROR'
    }

    async def on_startup(self):
        """服务启动时的回调"""
        try:
            self.logger.info("启动任务工作者服务...")
            
            # 启动工作者
            for i in range(self.worker_count):
                worker = NATSTaskWorker(
                    worker_id=f"{self.worker_type}-worker-{i+1}",
                    nats_url=self.nats_url,
                    worker_type=self.worker_type,
                    max_concurrent_tasks=self.max_concurrent_tasks
                )
                
                await worker.start()
                self.workers.append(worker)
                
                self.logger.info(f"✅ 工作者启动成功: {worker.worker_id}")
            
            # 更新统计信息
            self._update_stats()
            
            self.logger.info(f"✅ 任务工作者服务启动成功，共 {len(self.workers)} 个工作者")
            
        except Exception as e:
            self.logger.error(f"❌ 任务工作者服务启动失败: {e}")
            raise

    async def on_shutdown(self):
        """服务停止时的回调"""
        try:
            self.logger.info("停止任务工作者服务...")
            
            # 停止所有工作者
            for worker in self.workers:
                try:
                    await worker.stop()
                    self.logger.info(f"✅ 工作者停止成功: {worker.worker_id}")
                except Exception as e:
                    self.logger.error(f"❌ 工作者停止失败: {worker.worker_id}, 错误: {e}")
            
            self.workers.clear()
            self.logger.info("✅ 任务工作者服务停止完成")
            
        except Exception as e:
            self.logger.error(f"❌ 任务工作者服务停止失败: {e}")

    def _update_stats(self):
        """
        更新服务统计信息

        收集并更新工作者状态、任务处理统计等关键指标，
        用于监控服务健康状态和性能表现。
        """
        self.stats.update({
            'total_workers': len(self.workers),
            'running_workers': sum(1 for w in self.workers if getattr(w, 'is_running', False)),
            'total_max_concurrent': len(self.workers) * self.max_concurrent_tasks,
            'last_update': datetime.now().isoformat()
        })

    async def _get_service_status(self, request: web.Request) -> web.Response:
        """获取服务状态 - 标准化API端点"""
        try:
            self._update_stats()

            # 计算运行时间
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()

            # 检查NATS连接状态
            nats_connected = all(w.is_connected for w in self.workers if hasattr(w, 'is_connected'))

            status_data = {
                "service": "task-worker",
                "status": "running" if self.is_running else "stopped",
                "uptime_seconds": round(uptime_seconds, 2),
                "version": "1.0.0",
                "environment": self.config.get('environment', 'production'),
                "port": self.config.get('port', 8090),
                "features": {
                    "distributed_tasks": True,
                    "nats_integration": True,
                    "auto_scaling": True,
                    "load_balancing": True,
                    "fault_tolerance": True
                },
                "worker_summary": {
                    "total_workers": self.stats['total_workers'],
                    "running_workers": self.stats['running_workers'],
                    "worker_type": self.worker_type,
                    "max_concurrent_per_worker": self.max_concurrent_tasks,
                    "total_max_concurrent": self.stats['total_max_concurrent']
                },
                "nats_info": {
                    "url": self.nats_url,
                    "connected": nats_connected,
                    "connection_count": len([w for w in self.workers if hasattr(w, 'is_connected') and w.is_connected])
                },
                "statistics": {
                    "tasks_processed": self.stats.get('tasks_processed', 0),
                    "tasks_failed": self.stats.get('tasks_failed', 0),
                    "current_active_tasks": sum(getattr(w, 'current_tasks', 0) for w in self.workers),
                    "average_task_duration": self.stats.get('avg_task_duration', 0.0)
                }
            }

            return self._create_success_response(status_data, "Service status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取服务状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve service status: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _get_workers_status(self, request: web.Request) -> web.Response:
        """获取工作者状态信息"""
        try:
            self._update_stats()

            # 检查NATS连接状态
            nats_connected = all(getattr(w, 'is_connected', False) for w in self.workers)

            status_data = {
                "worker_summary": {
                    "total_workers": self.stats['total_workers'],
                    "running_workers": self.stats['running_workers'],
                    "worker_type": self.worker_type,
                    "max_concurrent_per_worker": self.max_concurrent_tasks,
                    "total_max_concurrent": self.stats['total_max_concurrent']
                },
                "nats_connection": {
                    "url": self.nats_url,
                    "connected": nats_connected,
                    "active_connections": len([w for w in self.workers if getattr(w, 'is_connected', False)])
                },
                "health_status": "healthy" if nats_connected and self.is_running else "degraded"
            }

            return self._create_success_response(status_data, "Worker status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取工作者状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve worker status: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _get_workers_stats(self, request: web.Request) -> web.Response:
        """获取详细的工作者统计信息"""
        try:
            self._update_stats()

            # 收集工作者统计
            worker_stats = []
            for worker in self.workers:
                if hasattr(worker, 'get_stats'):
                    worker_stats.append(worker.get_stats())
                else:
                    worker_stats.append({
                        'worker_id': getattr(worker, 'worker_id', f'worker-{len(worker_stats)}'),
                        'is_running': getattr(worker, 'is_running', False),
                        'is_connected': getattr(worker, 'is_connected', False),
                        'current_tasks': getattr(worker, 'current_tasks', 0),
                        'max_concurrent_tasks': getattr(worker, 'max_concurrent_tasks', self.max_concurrent_tasks),
                        'tasks_processed': getattr(worker, 'tasks_processed', 0),
                        'tasks_failed': getattr(worker, 'tasks_failed', 0),
                        'last_activity': getattr(worker, 'last_activity', None)
                    })

            stats_data = {
                "service_stats": self.stats,
                "worker_stats": worker_stats,
                "aggregated_stats": {
                    'total_workers': len(self.workers),
                    'running_workers': sum(1 for s in worker_stats if s.get('is_running', False)),
                    'connected_workers': sum(1 for s in worker_stats if s.get('is_connected', False)),
                    'total_current_tasks': sum(s.get('current_tasks', 0) for s in worker_stats),
                    'total_max_concurrent': sum(s.get('max_concurrent_tasks', 0) for s in worker_stats)
                },
                "performance": {
                    "total_tasks_processed": sum(w.get('tasks_processed', 0) for w in worker_stats),
                    "total_tasks_failed": sum(w.get('tasks_failed', 0) for w in worker_stats),
                    "current_active_tasks": sum(w.get('current_tasks', 0) for w in worker_stats),
                    "success_rate": self._calculate_success_rate(worker_stats)
                }
            }

            return self._create_success_response(stats_data, "Worker statistics retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取工作者统计失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve worker statistics: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    def _calculate_success_rate(self, worker_stats: List[Dict]) -> float:
        """
        计算任务成功率

        Args:
            worker_stats: 工作者统计数据列表

        Returns:
            成功率百分比 (0.0-100.0)
        """
        total_processed = sum(w.get('tasks_processed', 0) for w in worker_stats)
        total_failed = sum(w.get('tasks_failed', 0) for w in worker_stats)

        if total_processed == 0:
            return 100.0

        success_count = total_processed - total_failed
        return round((success_count / total_processed) * 100.0, 2)

    async def _get_workers_list(self, request: web.Request) -> web.Response:
        """获取工作者列表"""
        try:
            workers_info = []

            for worker in self.workers:
                start_time = getattr(worker, 'start_time', None)
                worker_info = {
                    'worker_id': getattr(worker, 'worker_id', f'worker-{len(workers_info)}'),
                    'worker_type': getattr(worker, 'worker_type', self.worker_type),
                    'is_running': getattr(worker, 'is_running', False),
                    'is_connected': getattr(worker, 'is_connected', False),
                    'nats_connected': getattr(worker, 'nc', None) is not None,
                    'current_tasks': getattr(worker, 'current_tasks', 0),
                    'max_concurrent_tasks': getattr(worker, 'max_concurrent_tasks', self.max_concurrent_tasks),
                    'start_time': start_time.isoformat() if start_time else None,
                    'tasks_processed': getattr(worker, 'tasks_processed', 0),
                    'tasks_failed': getattr(worker, 'tasks_failed', 0)
                }
                workers_info.append(worker_info)

            workers_data = {
                'workers': workers_info,
                'total_count': len(workers_info),
                'summary': {
                    'running': sum(1 for w in workers_info if w['is_running']),
                    'connected': sum(1 for w in workers_info if w['nats_connected']),
                    'total_capacity': sum(w['max_concurrent_tasks'] for w in workers_info),
                    'current_load': sum(w['current_tasks'] for w in workers_info)
                }
            }

            return self._create_success_response(workers_data, "Workers list retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取工作者列表失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve workers list: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _scale_workers(self, request: web.Request) -> web.Response:
        """动态扩容/缩容工作者"""
        try:
            # 解析请求数据
            data = await request.json()
            target_count = data.get('worker_count')

            # 验证参数
            if target_count is None:
                return self._create_error_response(
                    "worker_count parameter is required",
                    self.ERROR_CODES['INVALID_PARAMETERS'],
                    400
                )

            if not isinstance(target_count, int) or target_count < 1:
                return self._create_error_response(
                    "worker_count must be a positive integer",
                    self.ERROR_CODES['INVALID_PARAMETERS'],
                    400
                )

            current_count = len(self.workers)

            if target_count > current_count:
                # 扩容
                for i in range(current_count, target_count):
                    worker = NATSTaskWorker(
                        worker_id=f"{self.worker_type}-worker-{i+1}",
                        nats_url=self.nats_url,
                        worker_type=self.worker_type,
                        max_concurrent_tasks=self.max_concurrent_tasks
                    )

                    await worker.start()
                    self.workers.append(worker)
                    self.logger.info(f"✅ 新工作者启动: {worker.worker_id}")

            elif target_count < current_count:
                # 缩容
                workers_to_remove = self.workers[target_count:]
                self.workers = self.workers[:target_count]

                for worker in workers_to_remove:
                    try:
                        await worker.stop()
                        self.logger.info(f"✅ 工作者停止: {worker.worker_id}")
                    except Exception as e:
                        self.logger.error(f"❌ 工作者停止失败: {worker.worker_id}, 错误: {e}")

            # 更新统计信息
            self._update_stats()
            self.stats['last_scale_time'] = datetime.now().isoformat()

            scale_data = {
                'previous_count': current_count,
                'current_count': len(self.workers),
                'target_count': target_count,
                'scale_action': 'scale_up' if target_count > current_count else 'scale_down' if target_count < current_count else 'no_change',
                'scale_time': self.stats['last_scale_time']
            }

            return self._create_success_response(
                scale_data,
                f"Workers scaled from {current_count} to {len(self.workers)}"
            )

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_PARAMETERS'],
                400
            )
        except Exception as e:
            self.logger.error(f"工作者扩缩容失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to scale workers: {str(e)}",
                self.ERROR_CODES['SCALING_ERROR']
            )

    async def _get_task_stats(self, request: web.Request) -> web.Response:
        """获取任务统计信息"""
        try:
            self._update_stats()

            # 收集任务统计
            total_processed = sum(getattr(w, 'tasks_processed', 0) for w in self.workers)
            total_failed = sum(getattr(w, 'tasks_failed', 0) for w in self.workers)
            current_active = sum(getattr(w, 'current_tasks', 0) for w in self.workers)

            task_stats = {
                "task_summary": {
                    "total_processed": total_processed,
                    "total_failed": total_failed,
                    "total_successful": total_processed - total_failed,
                    "current_active": current_active,
                    "success_rate": self._calculate_success_rate([
                        {'tasks_processed': total_processed, 'tasks_failed': total_failed}
                    ])
                },
                "worker_capacity": {
                    "total_workers": len(self.workers),
                    "total_capacity": sum(getattr(w, 'max_concurrent_tasks', self.max_concurrent_tasks) for w in self.workers),
                    "current_utilization": round((current_active / max(1, sum(getattr(w, 'max_concurrent_tasks', self.max_concurrent_tasks) for w in self.workers))) * 100, 2)
                },
                "performance_metrics": {
                    "average_task_duration": self.stats.get('avg_task_duration', 0.0),
                    "tasks_per_minute": self.stats.get('tasks_per_minute', 0.0),
                    "error_rate": round((total_failed / max(1, total_processed)) * 100, 2)
                }
            }

            return self._create_success_response(task_stats, "Task statistics retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取任务统计失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve task statistics: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _submit_task(self, request: web.Request) -> web.Response:
        """提交任务到工作队列"""
        try:
            # 解析请求数据
            data = await request.json()

            # 验证必需字段
            task_type = data.get('task_type')
            task_data = data.get('task_data')

            if not task_type:
                return self._create_error_response(
                    "task_type is required",
                    self.ERROR_CODES['INVALID_TASK_DATA'],
                    400
                )

            if task_data is None:
                return self._create_error_response(
                    "task_data is required",
                    self.ERROR_CODES['INVALID_TASK_DATA'],
                    400
                )

            # 检查是否有可用的工作者
            available_workers = [w for w in self.workers if getattr(w, 'is_connected', False)]
            if not available_workers:
                return self._create_error_response(
                    "No available workers to process the task",
                    self.ERROR_CODES['SERVICE_UNAVAILABLE'],
                    503
                )

            # 创建任务
            task_id = f"task-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(self.workers)}"
            task = {
                'task_id': task_id,
                'task_type': task_type,
                'task_data': task_data,
                'priority': data.get('priority', 'normal'),
                'timeout': data.get('timeout', 300),
                'submitted_at': datetime.now().isoformat(),
                'submitted_by': request.remote or 'unknown'
            }

            # 这里应该将任务提交到NATS队列
            # 由于这是一个示例，我们只是记录任务提交
            self.logger.info(f"任务提交: {task_id}, 类型: {task_type}")

            submission_data = {
                "task_id": task_id,
                "task_type": task_type,
                "status": "submitted",
                "submitted_at": task['submitted_at'],
                "estimated_processing_time": data.get('timeout', 300),
                "assigned_workers": len(available_workers)
            }

            return self._create_success_response(submission_data, f"Task {task_id} submitted successfully")

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_TASK_DATA'],
                400
            )
        except Exception as e:
            self.logger.error(f"任务提交失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to submit task: {str(e)}",
                self.ERROR_CODES['TASK_SUBMISSION_ERROR']
            )


async def main():
    """服务主入口点"""
    try:
        # 读取配置
        config_path = project_root / 'config' / 'services.yaml'

        # 如果配置文件不存在，使用默认配置
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f) or {}
            service_config = full_config.get('services', {}).get('task-worker', {})
        else:
            # 使用默认配置
            service_config = {
                'port': int(os.getenv('API_PORT', '8090')),
                'worker_count': int(os.getenv('WORKER_COUNT', '3')),
                'worker_type': os.getenv('WORKER_TYPE', 'general'),
                'max_concurrent_tasks': int(os.getenv('MAX_CONCURRENT_TASKS', '5')),
                'nats_url': os.getenv('NATS_URL', 'nats://nats:4222')
            }
        
        # 创建并运行服务
        service = TaskWorkerService(config=service_config)
        await service.run()

    except Exception as e:
        logging.critical("Task Worker Service failed to start", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # 配置结构化日志
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    
    asyncio.run(main())
