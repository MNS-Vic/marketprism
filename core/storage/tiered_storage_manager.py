"""
MarketPrism 分层存储管理器
实现热端-冷端数据存储架构，支持数据生命周期管理
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import structlog

from .unified_clickhouse_writer import UnifiedClickHouseWriter
from .types import (
    NormalizedOrderBook, NormalizedTrade
)


class StorageTier(Enum):
    """存储层级枚举"""
    HOT = "hot"      # 热端存储：高频访问，短期保留
    COLD = "cold"    # 冷端存储：低频访问，长期保留
    ARCHIVE = "archive"  # 归档存储：极少访问，永久保留


@dataclass
class TierConfig:
    """存储层级配置"""
    tier: StorageTier
    clickhouse_host: str
    clickhouse_port: int
    clickhouse_user: str
    clickhouse_password: str
    clickhouse_database: str
    retention_days: int
    batch_size: int = 1000
    flush_interval: int = 5
    max_retries: int = 3


@dataclass
class DataTransferTask:
    """数据传输任务"""
    task_id: str
    source_tier: StorageTier
    target_tier: StorageTier
    data_type: str
    exchange: str
    symbol: str
    start_time: datetime
    end_time: datetime
    status: str = "pending"  # pending, running, completed, failed
    created_at: datetime = None
    updated_at: datetime = None
    error_message: Optional[str] = None
    records_count: int = 0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = self.created_at


class TieredStorageManager:
    """分层存储管理器"""
    
    def __init__(self, hot_config: TierConfig, cold_config: TierConfig):
        """
        初始化分层存储管理器
        
        Args:
            hot_config: 热端存储配置
            cold_config: 冷端存储配置
        """
        self.logger = structlog.get_logger("core.storage.tiered_storage_manager")
        
        # 存储配置
        self.hot_config = hot_config
        self.cold_config = cold_config
        
        # ClickHouse写入器
        self.hot_writer: Optional[UnifiedClickHouseWriter] = None
        self.cold_writer: Optional[UnifiedClickHouseWriter] = None
        
        # 数据传输任务队列
        self.transfer_tasks: Dict[str, DataTransferTask] = {}
        self.transfer_queue = asyncio.Queue()
        
        # 运行状态
        self.is_running = False
        self.transfer_worker_task: Optional[asyncio.Task] = None
        
        # 统计信息
        self.stats = {
            "hot_storage": {
                "total_writes": 0,
                "failed_writes": 0,
                "last_write_time": None
            },
            "cold_storage": {
                "total_writes": 0,
                "failed_writes": 0,
                "last_write_time": None
            },
            "data_transfers": {
                "total_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0,
                "last_transfer_time": None
            }
        }
    
    async def initialize(self):
        """初始化分层存储管理器"""
        try:
            self.logger.info("🚀 初始化分层存储管理器")
            
            # 初始化热端存储
            self.hot_writer = UnifiedClickHouseWriter(
                host=self.hot_config.clickhouse_host,
                port=self.hot_config.clickhouse_port,
                user=self.hot_config.clickhouse_user,
                password=self.hot_config.clickhouse_password,
                database=self.hot_config.clickhouse_database,
                batch_size=self.hot_config.batch_size,
                flush_interval=self.hot_config.flush_interval
            )
            await self.hot_writer.initialize()
            self.logger.info("✅ 热端存储初始化成功", 
                           host=self.hot_config.clickhouse_host,
                           database=self.hot_config.clickhouse_database)
            
            # 初始化冷端存储
            self.cold_writer = UnifiedClickHouseWriter(
                host=self.cold_config.clickhouse_host,
                port=self.cold_config.clickhouse_port,
                user=self.cold_config.clickhouse_user,
                password=self.cold_config.clickhouse_password,
                database=self.cold_config.clickhouse_database,
                batch_size=self.cold_config.batch_size,
                flush_interval=self.cold_config.flush_interval
            )
            await self.cold_writer.initialize()
            self.logger.info("✅ 冷端存储初始化成功",
                           host=self.cold_config.clickhouse_host,
                           database=self.cold_config.clickhouse_database)
            
            # 启动数据传输工作器
            self.is_running = True
            self.transfer_worker_task = asyncio.create_task(self._transfer_worker())
            
            self.logger.info("✅ 分层存储管理器初始化完成")
            
        except Exception as e:
            self.logger.error("❌ 分层存储管理器初始化失败", error=str(e))
            raise
    
    async def close(self):
        """关闭分层存储管理器"""
        try:
            self.logger.info("🛑 关闭分层存储管理器")
            
            # 停止传输工作器
            self.is_running = False
            if self.transfer_worker_task:
                self.transfer_worker_task.cancel()
                try:
                    await self.transfer_worker_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭存储写入器
            if self.hot_writer:
                await self.hot_writer.close()
                self.logger.info("✅ 热端存储已关闭")
            
            if self.cold_writer:
                await self.cold_writer.close()
                self.logger.info("✅ 冷端存储已关闭")
            
            self.logger.info("✅ 分层存储管理器已关闭")
            
        except Exception as e:
            self.logger.error("❌ 关闭分层存储管理器失败", error=str(e))
    
    # ==================== 数据写入方法 ====================
    
    async def store_to_hot(self, data_type: str, data: Union[Dict, List[Dict]]) -> bool:
        """存储数据到热端"""
        try:
            if not self.hot_writer:
                self.logger.error("❌ 热端存储未初始化")
                return False
            
            # 根据数据类型选择存储方法
            success = await self._store_by_type(self.hot_writer, data_type, data)
            
            # 更新统计
            if success:
                self.stats["hot_storage"]["total_writes"] += 1
                self.stats["hot_storage"]["last_write_time"] = datetime.now(timezone.utc)
            else:
                self.stats["hot_storage"]["failed_writes"] += 1
            
            return success
            
        except Exception as e:
            self.logger.error("❌ 热端存储失败", data_type=data_type, error=str(e))
            self.stats["hot_storage"]["failed_writes"] += 1
            return False
    
    async def store_to_cold(self, data_type: str, data: Union[Dict, List[Dict]]) -> bool:
        """存储数据到冷端"""
        try:
            if not self.cold_writer:
                self.logger.error("❌ 冷端存储未初始化")
                return False
            
            # 根据数据类型选择存储方法
            success = await self._store_by_type(self.cold_writer, data_type, data)
            
            # 更新统计
            if success:
                self.stats["cold_storage"]["total_writes"] += 1
                self.stats["cold_storage"]["last_write_time"] = datetime.now(timezone.utc)
            else:
                self.stats["cold_storage"]["failed_writes"] += 1
            
            return success
            
        except Exception as e:
            self.logger.error("❌ 冷端存储失败", data_type=data_type, error=str(e))
            self.stats["cold_storage"]["failed_writes"] += 1
            return False
    
    async def _store_by_type(self, writer: UnifiedClickHouseWriter, data_type: str, data: Union[Dict, List[Dict]]) -> bool:
        """根据数据类型存储数据"""
        try:
            # 确保数据是列表格式
            if isinstance(data, dict):
                data = [data]
            
            # 根据数据类型调用相应的存储方法
            if data_type == "orderbook":
                return await writer.store_orderbooks(data)
            elif data_type == "trade":
                return await writer.store_trades(data)
            elif data_type == "funding_rate":
                return await writer.store_funding_rates(data)
            elif data_type == "open_interest":
                return await writer.store_open_interests(data)
            elif data_type == "liquidation":
                return await writer.store_liquidations(data)
            elif data_type == "lsr":
                return await writer.store_lsrs(data)
            elif data_type == "volatility_index":
                return await writer.store_volatility_indices(data)
            else:
                self.logger.error("❌ 不支持的数据类型", data_type=data_type)
                return False
                
        except Exception as e:
            self.logger.error("❌ 数据存储失败", data_type=data_type, error=str(e))
            return False

    # ==================== 数据传输方法 ====================

    async def schedule_data_transfer(self, data_type: str, exchange: str, symbol: str,
                                   start_time: datetime, end_time: datetime) -> str:
        """调度数据传输任务"""
        try:
            # 生成任务ID
            task_id = f"transfer_{data_type}_{exchange}_{symbol}_{int(time.time())}"

            # 创建传输任务
            task = DataTransferTask(
                task_id=task_id,
                source_tier=StorageTier.HOT,
                target_tier=StorageTier.COLD,
                data_type=data_type,
                exchange=exchange,
                symbol=symbol,
                start_time=start_time,
                end_time=end_time
            )

            # 添加到任务队列
            self.transfer_tasks[task_id] = task
            await self.transfer_queue.put(task)

            self.stats["data_transfers"]["total_tasks"] += 1

            self.logger.info("📋 数据传输任务已调度",
                           task_id=task_id,
                           data_type=data_type,
                           exchange=exchange,
                           symbol=symbol)

            return task_id

        except Exception as e:
            self.logger.error("❌ 调度数据传输任务失败", error=str(e))
            raise

    async def _transfer_worker(self):
        """数据传输工作器"""
        self.logger.info("🔄 数据传输工作器已启动")

        while self.is_running:
            try:
                # 等待传输任务
                task = await asyncio.wait_for(self.transfer_queue.get(), timeout=1.0)

                # 执行数据传输
                await self._execute_transfer_task(task)

            except asyncio.TimeoutError:
                # 超时是正常的，继续循环
                continue
            except Exception as e:
                self.logger.error("❌ 数据传输工作器异常", error=str(e))
                await asyncio.sleep(5)  # 错误时等待5秒

        self.logger.info("🛑 数据传输工作器已停止")

    async def _execute_transfer_task(self, task: DataTransferTask):
        """执行数据传输任务"""
        try:
            self.logger.info("🚀 开始执行数据传输任务", task_id=task.task_id)

            # 更新任务状态
            task.status = "running"
            task.updated_at = datetime.now(timezone.utc)

            # 从热端查询数据
            hot_data = await self._query_hot_data(
                task.data_type, task.exchange, task.symbol,
                task.start_time, task.end_time
            )

            if not hot_data:
                self.logger.warning("⚠️ 未找到需要传输的数据", task_id=task.task_id)
                task.status = "completed"
                task.records_count = 0
                task.updated_at = datetime.now(timezone.utc)
                return

            # 存储到冷端
            success = await self.store_to_cold(task.data_type, hot_data)

            if success:
                task.status = "completed"
                task.records_count = len(hot_data) if isinstance(hot_data, list) else 1
                self.stats["data_transfers"]["completed_tasks"] += 1
                self.stats["data_transfers"]["last_transfer_time"] = datetime.now(timezone.utc)

                self.logger.info("✅ 数据传输任务完成",
                               task_id=task.task_id,
                               records_count=task.records_count)

                # 可选：删除热端数据（根据配置决定）
                # await self._cleanup_hot_data(task)

            else:
                task.status = "failed"
                task.error_message = "冷端存储失败"
                self.stats["data_transfers"]["failed_tasks"] += 1

                self.logger.error("❌ 数据传输任务失败", task_id=task.task_id)

            task.updated_at = datetime.now(timezone.utc)

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.updated_at = datetime.now(timezone.utc)
            self.stats["data_transfers"]["failed_tasks"] += 1

            self.logger.error("❌ 执行数据传输任务异常",
                            task_id=task.task_id, error=str(e))

    async def _query_hot_data(self, data_type: str, exchange: str, symbol: str,
                            start_time: datetime, end_time: datetime) -> List[Dict]:
        """从热端查询数据"""
        try:
            if not self.hot_writer:
                return []

            # 构建查询SQL
            table_name = self._get_table_name(data_type)
            query = f"""
                SELECT * FROM {table_name}
                WHERE exchange = %(exchange)s
                AND symbol = %(symbol)s
                AND timestamp >= %(start_time)s
                AND timestamp < %(end_time)s
                ORDER BY timestamp
            """

            params = {
                'exchange': exchange,
                'symbol': symbol,
                'start_time': start_time,
                'end_time': end_time
            }

            # 执行查询
            result = await self.hot_writer.execute_query(query, params)

            self.logger.debug("📊 热端数据查询完成",
                            data_type=data_type,
                            exchange=exchange,
                            symbol=symbol,
                            records_count=len(result))

            return result

        except Exception as e:
            self.logger.error("❌ 热端数据查询失败", error=str(e))
            return []

    def _get_table_name(self, data_type: str) -> str:
        """获取数据类型对应的表名"""
        table_mapping = {
            "orderbook": "orderbooks",
            "trade": "trades",
            "funding_rate": "funding_rates",
            "open_interest": "open_interests",
            "liquidation": "liquidations",
            "lsr": "lsrs",
            "volatility_index": "volatility_indices"
        }
        return table_mapping.get(data_type, data_type)

    # ==================== 数据生命周期管理 ====================

    async def cleanup_expired_hot_data(self) -> Dict[str, Any]:
        """清理过期的热端数据"""
        try:
            self.logger.info("🧹 开始清理过期热端数据")

            cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.hot_config.retention_days)

            cleanup_summary = {
                "cutoff_time": cutoff_time.isoformat(),
                "tables_cleaned": {},
                "total_records_deleted": 0
            }

            # 清理各种数据类型的表
            data_types = ["orderbook", "trade", "funding_rate", "open_interest",
                         "liquidation", "lsr", "volatility_index"]

            for data_type in data_types:
                try:
                    table_name = self._get_table_name(data_type)
                    deleted_count = await self._cleanup_table_data(table_name, cutoff_time)

                    cleanup_summary["tables_cleaned"][table_name] = deleted_count
                    cleanup_summary["total_records_deleted"] += deleted_count

                    self.logger.info("✅ 表数据清理完成",
                                   table=table_name,
                                   deleted_count=deleted_count)

                except Exception as e:
                    self.logger.error("❌ 表数据清理失败",
                                    table=table_name, error=str(e))
                    cleanup_summary["tables_cleaned"][table_name] = f"error: {str(e)}"

            self.logger.info("✅ 热端数据清理完成",
                           total_deleted=cleanup_summary["total_records_deleted"])

            return cleanup_summary

        except Exception as e:
            self.logger.error("❌ 清理过期热端数据失败", error=str(e))
            raise

    async def _cleanup_table_data(self, table_name: str, cutoff_time: datetime) -> int:
        """清理指定表的过期数据"""
        try:
            if not self.hot_writer:
                return 0

            # 构建删除SQL
            delete_query = f"""
                ALTER TABLE {table_name} DELETE
                WHERE timestamp < %(cutoff_time)s
            """

            params = {'cutoff_time': cutoff_time}

            # 执行删除
            await self.hot_writer.execute_query(delete_query, params)

            # 查询删除的记录数（ClickHouse的DELETE是异步的，这里返回估算值）
            count_query = f"""
                SELECT count() FROM {table_name}
                WHERE timestamp < %(cutoff_time)s
            """

            result = await self.hot_writer.execute_query(count_query, params)
            deleted_count = result[0]['count()'] if result else 0

            return deleted_count

        except Exception as e:
            self.logger.error("❌ 清理表数据失败", table=table_name, error=str(e))
            return 0

    # ==================== 状态查询方法 ====================

    def get_transfer_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取传输任务状态"""
        task = self.transfer_tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "source_tier": task.source_tier.value,
            "target_tier": task.target_tier.value,
            "data_type": task.data_type,
            "exchange": task.exchange,
            "symbol": task.symbol,
            "start_time": task.start_time.isoformat(),
            "end_time": task.end_time.isoformat(),
            "status": task.status,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "error_message": task.error_message,
            "records_count": task.records_count
        }

    def get_all_transfer_tasks(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有传输任务"""
        tasks = []
        for task in self.transfer_tasks.values():
            if status_filter is None or task.status == status_filter:
                tasks.append(self.get_transfer_task_status(task.task_id))

        # 按创建时间倒序排列
        tasks.sort(key=lambda x: x["created_at"], reverse=True)
        return tasks

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hot_storage": {
                **self.stats["hot_storage"],
                "config": {
                    "host": self.hot_config.clickhouse_host,
                    "database": self.hot_config.clickhouse_database,
                    "retention_days": self.hot_config.retention_days
                },
                "status": "connected" if self.hot_writer else "disconnected"
            },
            "cold_storage": {
                **self.stats["cold_storage"],
                "config": {
                    "host": self.cold_config.clickhouse_host,
                    "database": self.cold_config.clickhouse_database,
                    "retention_days": self.cold_config.retention_days
                },
                "status": "connected" if self.cold_writer else "disconnected"
            },
            "data_transfers": {
                **self.stats["data_transfers"],
                "pending_tasks": len([t for t in self.transfer_tasks.values() if t.status == "pending"]),
                "running_tasks": len([t for t in self.transfer_tasks.values() if t.status == "running"]),
                "queue_size": self.transfer_queue.qsize()
            },
            "system": {
                "is_running": self.is_running,
                "transfer_worker_active": self.transfer_worker_task is not None and not self.transfer_worker_task.done()
            }
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }

        # 检查热端存储
        try:
            if self.hot_writer:
                await self.hot_writer.health_check()
                health_status["components"]["hot_storage"] = {"status": "healthy"}
            else:
                health_status["components"]["hot_storage"] = {"status": "not_initialized"}
        except Exception as e:
            health_status["components"]["hot_storage"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # 检查冷端存储
        try:
            if self.cold_writer:
                await self.cold_writer.health_check()
                health_status["components"]["cold_storage"] = {"status": "healthy"}
            else:
                health_status["components"]["cold_storage"] = {"status": "not_initialized"}
        except Exception as e:
            health_status["components"]["cold_storage"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # 检查传输工作器
        if self.is_running and self.transfer_worker_task and not self.transfer_worker_task.done():
            health_status["components"]["transfer_worker"] = {"status": "healthy"}
        else:
            health_status["components"]["transfer_worker"] = {"status": "stopped"}
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"

        return health_status

    # ==================== 便捷方法 ====================

    async def auto_schedule_transfers(self, data_types: List[str] = None,
                                    exchanges: List[str] = None,
                                    lookback_hours: int = 24) -> List[str]:
        """自动调度数据传输任务"""
        try:
            if data_types is None:
                data_types = ["orderbook", "trade", "funding_rate", "open_interest",
                             "liquidation", "lsr", "volatility_index"]

            if exchanges is None:
                exchanges = ["binance_spot", "binance_derivatives", "okx_spot",
                           "okx_derivatives", "deribit_derivatives"]

            # 计算时间范围
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=lookback_hours)

            task_ids = []

            for data_type in data_types:
                for exchange in exchanges:
                    # 这里可以根据实际需求获取symbol列表
                    # 暂时使用通用symbol
                    symbol = "BTC-USDT"  # 可以从配置或数据库获取

                    try:
                        task_id = await self.schedule_data_transfer(
                            data_type, exchange, symbol, start_time, end_time
                        )
                        task_ids.append(task_id)
                    except Exception as e:
                        self.logger.error("❌ 自动调度传输任务失败",
                                        data_type=data_type,
                                        exchange=exchange,
                                        error=str(e))

            self.logger.info("✅ 自动调度传输任务完成",
                           scheduled_tasks=len(task_ids),
                           lookback_hours=lookback_hours)

            return task_ids

        except Exception as e:
            self.logger.error("❌ 自动调度传输任务失败", error=str(e))
            return []
