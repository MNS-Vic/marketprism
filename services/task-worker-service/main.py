"""
MarketPrism 任务工作者服务
处理来自NATS的异步任务
"""

import asyncio
import logging
import os
import sys
import signal
from typing import Dict, Any, List
from aiohttp import web
import json
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from nats_task_worker import NATSTaskWorker

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TaskWorkerService:
    """任务工作者服务 - 管理多个工作者实例"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app = web.Application()
        self.workers: List[NATSTaskWorker] = []
        self.is_running = False
        
        # 服务配置
        self.worker_count = config.get('worker_count', 3)
        self.worker_type = config.get('worker_type', 'general')
        self.max_concurrent_tasks = config.get('max_concurrent_tasks', 5)
        
        # 设置路由
        self._setup_routes()
        
        logger.info(f"任务工作者服务初始化完成: worker_count={self.worker_count}")
    
    def _setup_routes(self):
        """设置HTTP路由"""
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_get('/api/v1/status', self._get_status)
        self.app.router.add_get('/api/v1/stats', self._get_stats)
        self.app.router.add_get('/api/v1/workers', self._get_workers)
        self.app.router.add_get('/api/v1/workers/{worker_id}/stats', self._get_worker_stats)
        self.app.router.add_post('/api/v1/workers/scale', self._scale_workers)
    
    async def start(self):
        """启动任务工作者服务"""
        if self.is_running:
            return
        
        try:
            logger.info("启动任务工作者服务...")
            
            # 启动工作者
            nats_url = os.getenv("NATS_URL", "nats://nats:4222")
            
            for i in range(self.worker_count):
                worker = NATSTaskWorker(
                    worker_id=f"{self.worker_type}-worker-{i+1}",
                    nats_url=nats_url,
                    worker_type=self.worker_type,
                    max_concurrent_tasks=self.max_concurrent_tasks
                )
                
                await worker.start()
                self.workers.append(worker)
                
                logger.info(f"✅ 工作者启动成功: {worker.worker_id}")
            
            self.is_running = True
            logger.info(f"✅ 任务工作者服务启动成功，共 {len(self.workers)} 个工作者")
            
        except Exception as e:
            logger.error(f"❌ 任务工作者服务启动失败: {e}")
            raise
    
    async def stop(self):
        """停止任务工作者服务"""
        if not self.is_running:
            return
        
        logger.info("停止任务工作者服务...")
        
        # 停止所有工作者
        for worker in self.workers:
            try:
                await worker.stop()
                logger.info(f"✅ 工作者已停止: {worker.worker_id}")
            except Exception as e:
                logger.error(f"⚠️ 工作者停止失败: {worker.worker_id}, error={e}")
        
        self.workers.clear()
        self.is_running = False
        logger.info("✅ 任务工作者服务已停止")
    
    # HTTP API处理器
    async def _health_check(self, request: web.Request) -> web.Response:
        """健康检查"""
        healthy_workers = sum(1 for worker in self.workers if worker.is_running)
        
        return web.json_response({
            "status": "healthy" if healthy_workers > 0 else "unhealthy",
            "service": "task-worker-service",
            "worker_count": len(self.workers),
            "healthy_workers": healthy_workers,
            "timestamp": datetime.now().isoformat()
        })
    
    async def _get_status(self, request: web.Request) -> web.Response:
        """获取服务状态"""
        return web.json_response({
            "service": "task-worker-service",
            "is_running": self.is_running,
            "worker_count": len(self.workers),
            "worker_type": self.worker_type,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "workers": [
                {
                    "worker_id": worker.worker_id,
                    "is_running": worker.is_running,
                    "current_tasks": worker.current_tasks
                }
                for worker in self.workers
            ],
            "timestamp": datetime.now().isoformat()
        })
    
    async def _get_stats(self, request: web.Request) -> web.Response:
        """获取统计信息"""
        total_stats = {
            "total_workers": len(self.workers),
            "running_workers": sum(1 for worker in self.workers if worker.is_running),
            "total_tasks_processed": sum(worker.tasks_processed for worker in self.workers),
            "total_tasks_completed": sum(worker.tasks_completed for worker in self.workers),
            "total_tasks_failed": sum(worker.tasks_failed for worker in self.workers),
            "total_current_tasks": sum(worker.current_tasks for worker in self.workers),
            "total_max_concurrent": sum(worker.max_concurrent_tasks for worker in self.workers),
            "average_success_rate": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        # 计算平均成功率
        if total_stats["total_tasks_processed"] > 0:
            total_stats["average_success_rate"] = (
                total_stats["total_tasks_completed"] / total_stats["total_tasks_processed"] * 100
            )
        
        return web.json_response(total_stats)
    
    async def _get_workers(self, request: web.Request) -> web.Response:
        """获取所有工作者信息"""
        workers_info = []
        
        for worker in self.workers:
            workers_info.append(worker.get_stats())
        
        return web.json_response({
            "workers": workers_info,
            "total_count": len(workers_info)
        })
    
    async def _get_worker_stats(self, request: web.Request) -> web.Response:
        """获取特定工作者统计信息"""
        worker_id = request.match_info['worker_id']
        
        for worker in self.workers:
            if worker.worker_id == worker_id:
                return web.json_response(worker.get_stats())
        
        return web.json_response({
            "error": f"Worker not found: {worker_id}"
        }, status=404)
    
    async def _scale_workers(self, request: web.Request) -> web.Response:
        """动态扩缩容工作者"""
        try:
            data = await request.json()
            target_count = data.get('worker_count', self.worker_count)
            
            current_count = len(self.workers)
            
            if target_count > current_count:
                # 扩容
                nats_url = os.getenv("NATS_URL", "nats://nats:4222")
                
                for i in range(current_count, target_count):
                    worker = NATSTaskWorker(
                        worker_id=f"{self.worker_type}-worker-{i+1}",
                        nats_url=nats_url,
                        worker_type=self.worker_type,
                        max_concurrent_tasks=self.max_concurrent_tasks
                    )
                    
                    await worker.start()
                    self.workers.append(worker)
                    
                    logger.info(f"✅ 新工作者启动: {worker.worker_id}")
                
                message = f"扩容成功: {current_count} → {target_count}"
                
            elif target_count < current_count:
                # 缩容
                workers_to_stop = self.workers[target_count:]
                self.workers = self.workers[:target_count]
                
                for worker in workers_to_stop:
                    await worker.stop()
                    logger.info(f"✅ 工作者已停止: {worker.worker_id}")
                
                message = f"缩容成功: {current_count} → {target_count}"
                
            else:
                message = f"工作者数量无变化: {current_count}"
            
            return web.json_response({
                "status": "success",
                "message": message,
                "previous_count": current_count,
                "current_count": len(self.workers)
            })
            
        except Exception as e:
            logger.error(f"工作者扩缩容失败: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)


async def create_app():
    """创建应用"""
    config = {
        'host': '0.0.0.0',
        'port': 8090,
        'worker_count': int(os.getenv('WORKER_COUNT', '3')),
        'worker_type': os.getenv('WORKER_TYPE', 'general'),
        'max_concurrent_tasks': int(os.getenv('MAX_CONCURRENT_TASKS', '5'))
    }
    
    service = TaskWorkerService(config)
    
    # 设置启动和关闭处理器
    async def startup_handler(app):
        await service.start()
    
    async def cleanup_handler(app):
        await service.stop()
    
    service.app.on_startup.append(startup_handler)
    service.app.on_cleanup.append(cleanup_handler)
    
    return service.app, service


def setup_signal_handlers(service):
    """设置信号处理器"""
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在停止服务...")
        asyncio.create_task(service.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main():
    """主函数"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        app, service = loop.run_until_complete(create_app())
        
        # 设置信号处理器
        setup_signal_handlers(service)
        
        # 启动Web服务器
        web.run_app(
            app,
            host='0.0.0.0',
            port=8090
        )
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止服务...")
    except Exception as e:
        logger.error(f"服务运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
