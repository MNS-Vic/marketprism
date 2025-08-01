"""
MarketPrism 数据同步任务
与task-worker服务集成，实现定时数据同步调度
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import structlog

from core.storage.tiered_storage_manager import TieredStorageManager, TierConfig, StorageTier


class DataSyncTask:
    """数据同步任务"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据同步任务
        
        Args:
            config: 任务配置
        """
        self.config = config
        self.logger = structlog.get_logger("services.data_storage.tasks.data_sync")
        
        # 存储管理器
        self.storage_manager: Optional[TieredStorageManager] = None
        
        # 任务配置
        self.sync_config = config.get('sync', {})
        self.hot_storage_config = config.get('hot_storage', {})
        self.cold_storage_config = config.get('cold_storage', {})
    
    async def initialize(self):
        """初始化任务"""
        try:
            self.logger.info("🚀 初始化数据同步任务")
            
            # 创建热端配置
            hot_config = TierConfig(
                tier=StorageTier.HOT,
                clickhouse_host=self.hot_storage_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=self.hot_storage_config.get('clickhouse_port', 9000),
                clickhouse_user=self.hot_storage_config.get('clickhouse_user', 'default'),
                clickhouse_password=self.hot_storage_config.get('clickhouse_password', ''),
                clickhouse_database=self.hot_storage_config.get('clickhouse_database', 'marketprism_hot'),
                retention_days=self.hot_storage_config.get('retention_days', 3),
                batch_size=self.hot_storage_config.get('batch_size', 1000),
                flush_interval=self.hot_storage_config.get('flush_interval', 5)
            )
            
            # 创建冷端配置
            cold_config = TierConfig(
                tier=StorageTier.COLD,
                clickhouse_host=self.cold_storage_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=self.cold_storage_config.get('clickhouse_port', 9000),
                clickhouse_user=self.cold_storage_config.get('clickhouse_user', 'default'),
                clickhouse_password=self.cold_storage_config.get('clickhouse_password', ''),
                clickhouse_database=self.cold_storage_config.get('clickhouse_database', 'marketprism_cold'),
                retention_days=self.cold_storage_config.get('retention_days', 365),
                batch_size=self.cold_storage_config.get('batch_size', 5000),
                flush_interval=self.cold_storage_config.get('flush_interval', 30)
            )
            
            # 初始化分层存储管理器
            self.storage_manager = TieredStorageManager(hot_config, cold_config)
            await self.storage_manager.initialize()
            
            self.logger.info("✅ 数据同步任务初始化完成")
            
        except Exception as e:
            self.logger.error("❌ 数据同步任务初始化失败", error=str(e))
            raise
    
    async def execute_sync_task(self, task_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行数据同步任务
        
        Args:
            task_params: 任务参数
                - data_type: 数据类型
                - exchange: 交易所
                - symbol: 交易对
                - start_time: 开始时间
                - end_time: 结束时间
                - task_id: 任务ID（可选）
        
        Returns:
            任务执行结果
        """
        try:
            task_id = task_params.get('task_id', f"sync_{int(datetime.now().timestamp())}")
            data_type = task_params['data_type']
            exchange = task_params['exchange']
            symbol = task_params['symbol']
            start_time = datetime.fromisoformat(task_params['start_time'])
            end_time = datetime.fromisoformat(task_params['end_time'])
            
            self.logger.info("🔄 开始执行数据同步任务",
                           task_id=task_id,
                           data_type=data_type,
                           exchange=exchange,
                           symbol=symbol)
            
            # 调度数据传输任务
            transfer_task_id = await self.storage_manager.schedule_data_transfer(
                data_type, exchange, symbol, start_time, end_time
            )
            
            # 等待传输完成
            await self._wait_for_transfer_completion(transfer_task_id)
            
            # 获取传输结果
            transfer_status = self.storage_manager.get_transfer_task_status(transfer_task_id)
            
            if transfer_status and transfer_status['status'] == 'completed':
                result = {
                    "status": "success",
                    "task_id": task_id,
                    "transfer_task_id": transfer_task_id,
                    "records_synced": transfer_status['records_count'],
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
                
                self.logger.info("✅ 数据同步任务完成",
                               task_id=task_id,
                               records_synced=transfer_status['records_count'])
            else:
                result = {
                    "status": "failed",
                    "task_id": task_id,
                    "transfer_task_id": transfer_task_id,
                    "error": transfer_status.get('error_message', '传输任务失败') if transfer_status else '传输任务状态未知',
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
                
                self.logger.error("❌ 数据同步任务失败",
                                task_id=task_id,
                                error=result['error'])
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error("❌ 执行数据同步任务异常", 
                            task_id=task_params.get('task_id', 'unknown'),
                            error=error_msg)
            
            return {
                "status": "error",
                "task_id": task_params.get('task_id', 'unknown'),
                "error": error_msg,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def execute_cleanup_task(self, task_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行数据清理任务
        
        Args:
            task_params: 任务参数
                - task_id: 任务ID（可选）
        
        Returns:
            任务执行结果
        """
        try:
            task_id = task_params.get('task_id', f"cleanup_{int(datetime.now().timestamp())}")
            
            self.logger.info("🧹 开始执行数据清理任务", task_id=task_id)
            
            # 执行热端数据清理
            cleanup_summary = await self.storage_manager.cleanup_expired_hot_data()
            
            result = {
                "status": "success",
                "task_id": task_id,
                "records_deleted": cleanup_summary.get("total_records_deleted", 0),
                "tables_cleaned": cleanup_summary.get("tables_cleaned", {}),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
            self.logger.info("✅ 数据清理任务完成",
                           task_id=task_id,
                           records_deleted=result['records_deleted'])
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error("❌ 执行数据清理任务异常",
                            task_id=task_params.get('task_id', 'unknown'),
                            error=error_msg)
            
            return {
                "status": "error",
                "task_id": task_params.get('task_id', 'unknown'),
                "error": error_msg,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def execute_batch_sync_task(self, task_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行批量数据同步任务
        
        Args:
            task_params: 任务参数
                - lookback_hours: 回溯时间（小时）
                - data_types: 数据类型列表（可选）
                - exchanges: 交易所列表（可选）
                - task_id: 任务ID（可选）
        
        Returns:
            任务执行结果
        """
        try:
            task_id = task_params.get('task_id', f"batch_sync_{int(datetime.now().timestamp())}")
            lookback_hours = task_params.get('lookback_hours', 24)
            data_types = task_params.get('data_types')
            exchanges = task_params.get('exchanges')
            
            self.logger.info("🔄 开始执行批量数据同步任务",
                           task_id=task_id,
                           lookback_hours=lookback_hours)
            
            # 调度自动传输任务
            transfer_task_ids = await self.storage_manager.auto_schedule_transfers(
                data_types=data_types,
                exchanges=exchanges,
                lookback_hours=lookback_hours
            )
            
            # 等待所有传输完成
            await self._wait_for_multiple_transfers_completion(transfer_task_ids)
            
            # 统计结果
            completed_count = 0
            failed_count = 0
            total_records = 0
            
            for transfer_task_id in transfer_task_ids:
                status = self.storage_manager.get_transfer_task_status(transfer_task_id)
                if status:
                    if status['status'] == 'completed':
                        completed_count += 1
                        total_records += status['records_count']
                    elif status['status'] == 'failed':
                        failed_count += 1
            
            result = {
                "status": "success" if failed_count == 0 else "partial",
                "task_id": task_id,
                "total_transfers": len(transfer_task_ids),
                "completed_transfers": completed_count,
                "failed_transfers": failed_count,
                "total_records_synced": total_records,
                "transfer_task_ids": transfer_task_ids,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
            self.logger.info("✅ 批量数据同步任务完成",
                           task_id=task_id,
                           completed_transfers=completed_count,
                           failed_transfers=failed_count,
                           total_records=total_records)
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error("❌ 执行批量数据同步任务异常",
                            task_id=task_params.get('task_id', 'unknown'),
                            error=error_msg)
            
            return {
                "status": "error",
                "task_id": task_params.get('task_id', 'unknown'),
                "error": error_msg,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def _wait_for_transfer_completion(self, transfer_task_id: str, timeout_minutes: int = 30):
        """等待单个传输任务完成"""
        timeout_seconds = timeout_minutes * 60
        start_time = datetime.now(timezone.utc)
        
        while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout_seconds:
            status = self.storage_manager.get_transfer_task_status(transfer_task_id)
            if status and status['status'] in ['completed', 'failed']:
                return
            
            await asyncio.sleep(10)  # 10秒检查一次
        
        # 超时
        self.logger.warning("⚠️ 传输任务等待超时",
                          transfer_task_id=transfer_task_id,
                          timeout_minutes=timeout_minutes)
    
    async def _wait_for_multiple_transfers_completion(self, transfer_task_ids: List[str], timeout_minutes: int = 60):
        """等待多个传输任务完成"""
        timeout_seconds = timeout_minutes * 60
        start_time = datetime.now(timezone.utc)
        
        while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout_seconds:
            pending_tasks = []
            
            for task_id in transfer_task_ids:
                status = self.storage_manager.get_transfer_task_status(task_id)
                if status and status['status'] in ['pending', 'running']:
                    pending_tasks.append(task_id)
            
            if not pending_tasks:
                return  # 所有任务都完成了
            
            await asyncio.sleep(30)  # 30秒检查一次
        
        # 超时
        self.logger.warning("⚠️ 批量传输任务等待超时",
                          total_tasks=len(transfer_task_ids),
                          timeout_minutes=timeout_minutes)
    
    async def close(self):
        """关闭任务"""
        try:
            if self.storage_manager:
                await self.storage_manager.close()
                self.logger.info("✅ 数据同步任务已关闭")
        except Exception as e:
            self.logger.error("❌ 关闭数据同步任务失败", error=str(e))
