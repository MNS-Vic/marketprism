"""
任务调度器

基于APScheduler实现的定时任务调度系统，用于定期收集资金费率、持仓量等数据
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger


class CollectorScheduler:
    """收集器任务调度器"""
    
    def __init__(self, collector):
        self.collector = collector
        self.logger = structlog.get_logger(__name__)
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self._jobs: Dict[str, Dict[str, Any]] = {}
    
    async def start(self):
        """启动调度器"""
        try:
            # 注册默认任务
            await self._register_default_jobs()
            
            # 启动调度器
            self.scheduler.start()
            self.is_running = True
            
            self.logger.info("任务调度器启动成功", jobs_count=len(self._jobs))
            
        except Exception as e:
            self.logger.error("启动任务调度器失败", error=str(e))
            raise
    
    async def stop(self):
        """停止调度器"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            self.logger.info("任务调度器已停止")
    
    async def _register_default_jobs(self):
        """注册默认任务"""
        
        # 资金费率收集任务 - 每小时执行
        await self.add_job(
            job_id="funding_rate_collection",
            job_func=self._collect_funding_rates,
            trigger_type="interval",
            hours=1,
            description="收集资金费率数据"
        )
        
        # 持仓量收集任务 - 每15分钟执行
        await self.add_job(
            job_id="open_interest_collection",
            job_func=self._collect_open_interest,
            trigger_type="interval",
            minutes=15,
            description="收集持仓量数据"
        )
        
        # 强平数据监控任务 - 每分钟执行
        await self.add_job(
            job_id="liquidation_monitoring",
            job_func=self._monitor_liquidations,
            trigger_type="interval",
            minutes=1,
            description="监控强平数据"
        )
        
        # 系统健康检查任务 - 每5分钟执行
        await self.add_job(
            job_id="health_check",
            job_func=self._health_check,
            trigger_type="interval",
            minutes=5,
            description="系统健康检查"
        )
    
    async def add_job(
        self,
        job_id: str,
        job_func,
        trigger_type: str = "interval",
        description: str = "",
        **trigger_kwargs
    ):
        """添加定时任务"""
        try:
            # 创建触发器
            if trigger_type == "interval":
                trigger = IntervalTrigger(**trigger_kwargs)
            elif trigger_type == "cron":
                trigger = CronTrigger(**trigger_kwargs)
            else:
                raise ValueError(f"不支持的触发器类型: {trigger_type}")
            
            # 添加任务到调度器
            self.scheduler.add_job(
                func=job_func,
                trigger=trigger,
                id=job_id,
                name=description or job_id,
                max_instances=1,  # 防止任务重叠
                replace_existing=True
            )
            
            # 记录任务信息
            self._jobs[job_id] = {
                "function": job_func.__name__,
                "trigger_type": trigger_type,
                "trigger_kwargs": trigger_kwargs,
                "description": description,
                "added_at": datetime.utcnow(),
                "last_run": None,
                "run_count": 0
            }
            
            self.logger.info(
                "添加定时任务",
                job_id=job_id,
                description=description,
                trigger_type=trigger_type,
                trigger_kwargs=trigger_kwargs
            )
            
        except Exception as e:
            self.logger.error("添加定时任务失败", job_id=job_id, error=str(e))
            raise
    
    async def remove_job(self, job_id: str):
        """移除定时任务"""
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self._jobs:
                del self._jobs[job_id]
            
            self.logger.info("移除定时任务", job_id=job_id)
            
        except Exception as e:
            self.logger.error("移除定时任务失败", job_id=job_id, error=str(e))
    
    async def _collect_funding_rates(self):
        """收集资金费率数据任务"""
        try:
            self.logger.debug("开始收集资金费率数据")
            
            for adapter_key, adapter in self.collector.exchange_adapters.items():
                if hasattr(adapter, 'collect_funding_rate_data'):
                    try:
                        await adapter.collect_funding_rate_data()
                        self.logger.debug("资金费率收集完成", adapter=adapter_key)
                    except Exception as e:
                        self.logger.error("资金费率收集失败", adapter=adapter_key, error=str(e))
            
            # 更新任务运行记录
            if "funding_rate_collection" in self._jobs:
                self._jobs["funding_rate_collection"]["last_run"] = datetime.utcnow()
                self._jobs["funding_rate_collection"]["run_count"] += 1
                
        except Exception as e:
            self.logger.error("资金费率收集任务执行失败", error=str(e))
    
    async def _collect_open_interest(self):
        """收集持仓量数据任务"""
        try:
            self.logger.debug("开始收集持仓量数据")
            
            for adapter_key, adapter in self.collector.exchange_adapters.items():
                if hasattr(adapter, 'collect_open_interest_data'):
                    try:
                        await adapter.collect_open_interest_data()
                        self.logger.debug("持仓量收集完成", adapter=adapter_key)
                    except Exception as e:
                        self.logger.error("持仓量收集失败", adapter=adapter_key, error=str(e))
            
            # 更新任务运行记录
            if "open_interest_collection" in self._jobs:
                self._jobs["open_interest_collection"]["last_run"] = datetime.utcnow()
                self._jobs["open_interest_collection"]["run_count"] += 1
                
        except Exception as e:
            self.logger.error("持仓量收集任务执行失败", error=str(e))
    
    async def _monitor_liquidations(self):
        """监控强平数据任务"""
        try:
            self.logger.debug("开始监控强平数据")
            
            # 这个任务主要是确保强平数据流的连接状态
            for adapter_key, adapter in self.collector.exchange_adapters.items():
                if hasattr(adapter, 'check_liquidation_stream'):
                    try:
                        await adapter.check_liquidation_stream()
                        self.logger.debug("强平监控检查完成", adapter=adapter_key)
                    except Exception as e:
                        self.logger.error("强平监控检查失败", adapter=adapter_key, error=str(e))
            
            # 更新任务运行记录
            if "liquidation_monitoring" in self._jobs:
                self._jobs["liquidation_monitoring"]["last_run"] = datetime.utcnow()
                self._jobs["liquidation_monitoring"]["run_count"] += 1
                
        except Exception as e:
            self.logger.error("强平监控任务执行失败", error=str(e))
    
    async def _health_check(self):
        """系统健康检查任务"""
        try:
            self.logger.debug("开始系统健康检查")
            
            # 检查交易所连接状态
            for adapter_key, adapter in self.collector.exchange_adapters.items():
                if hasattr(adapter, 'is_connected'):
                    is_connected = adapter.is_connected
                    self.logger.debug(
                        "交易所连接状态",
                        adapter=adapter_key,
                        connected=is_connected
                    )
                    
                    # 如果连接断开，尝试重连
                    if not is_connected:
                        self.logger.warning("检测到连接断开，尝试重连", adapter=adapter_key)
                        try:
                            await adapter.reconnect()
                        except Exception as e:
                            self.logger.error("重连失败", adapter=adapter_key, error=str(e))
            
            # 检查NATS连接
            if self.collector.nats_manager:
                nats_health = await self.collector.nats_manager.health_check()
                self.logger.debug("NATS健康状态", health=nats_health)
            
            # 更新任务运行记录
            if "health_check" in self._jobs:
                self._jobs["health_check"]["last_run"] = datetime.utcnow()
                self._jobs["health_check"]["run_count"] += 1
                
        except Exception as e:
            self.logger.error("健康检查任务执行失败", error=str(e))
    
    def get_jobs_status(self) -> Dict[str, Any]:
        """获取任务状态"""
        status = {
            "scheduler_running": self.is_running,
            "total_jobs": len(self._jobs),
            "jobs": {}
        }
        
        for job_id, job_info in self._jobs.items():
            try:
                job = self.scheduler.get_job(job_id)
                next_run = job.next_run_time if job else None
                
                status["jobs"][job_id] = {
                    "description": job_info["description"],
                    "trigger_type": job_info["trigger_type"],
                    "last_run": job_info["last_run"].isoformat() + 'Z' if job_info["last_run"] else None,
                    "next_run": next_run.isoformat() + 'Z' if next_run else None,
                    "run_count": job_info["run_count"],
                    "enabled": job is not None
                }
            except Exception as e:
                status["jobs"][job_id] = {
                    "error": str(e),
                    "enabled": False
                }
        
        return status 