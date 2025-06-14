"""
归档管理器 - 从services/data_archiver整合而来

整合DataArchiver和相关服务的功能到统一的归档管理器中
支持热存储到冷存储的数据迁移、定时归档、数据恢复等功能
"""

import asyncio
import logging
import time
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
from pathlib import Path

try:
    import nats
    from croniter import croniter
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False
    croniter = None

# 避免循环导入，使用TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .unified_storage_manager import UnifiedStorageManager, UnifiedStorageConfig

logger = logging.getLogger(__name__)


@dataclass
class ArchiveConfig:
    """归档配置"""
    enabled: bool = True
    schedule: str = "0 2 * * *"  # 每天凌晨2点
    retention_days: int = 14
    batch_size: int = 100000
    max_retries: int = 3
    
    # 清理配置
    cleanup_enabled: bool = True
    cleanup_schedule: str = "0 3 * * *"  # 每天凌晨3点
    max_age_days: int = 90
    disk_threshold: int = 80
    smart_cleanup: bool = True
    
    # 服务配置
    heartbeat_interval: int = 60
    nats_enabled: bool = False
    nats_url: str = "nats://localhost:4222"
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ArchiveConfig':
        """从字典创建配置"""
        return cls(
            enabled=config_dict.get('enabled', True),
            schedule=config_dict.get('schedule', '0 2 * * *'),
            retention_days=config_dict.get('retention_days', 14),
            batch_size=config_dict.get('batch_size', 100000),
            max_retries=config_dict.get('max_retries', 3),
            
            cleanup_enabled=config_dict.get('cleanup_enabled', True),
            cleanup_schedule=config_dict.get('cleanup_schedule', '0 3 * * *'),
            max_age_days=config_dict.get('max_age_days', 90),
            disk_threshold=config_dict.get('disk_threshold', 80),
            smart_cleanup=config_dict.get('smart_cleanup', True),
            
            heartbeat_interval=config_dict.get('heartbeat_interval', 60),
            nats_enabled=config_dict.get('nats_enabled', False),
            nats_url=config_dict.get('nats_url', 'nats://localhost:4222')
        )


class ArchiveManager:
    """
    归档管理器
    
    整合了DataArchiver和DataArchiverService的功能：
    1. 数据归档（热存储 -> 冷存储）
    2. 数据恢复（冷存储 -> 热存储）  
    3. 定时任务调度
    4. 数据清理
    5. NATS消息处理（可选）
    """
    
    def __init__(self, 
                 hot_storage_manager: 'UnifiedStorageManager',
                 cold_storage_manager: Optional['UnifiedStorageManager'] = None,
                 archive_config: Optional[Union[ArchiveConfig, Dict[str, Any]]] = None):
        """
        初始化归档管理器
        
        Args:
            hot_storage_manager: 热存储管理器
            cold_storage_manager: 冷存储管理器（可选）
            archive_config: 归档配置
        """
        self.hot_storage = hot_storage_manager
        self.cold_storage = cold_storage_manager
        
        # 处理归档配置
        if isinstance(archive_config, dict):
            self.config = ArchiveConfig.from_dict(archive_config)
        elif isinstance(archive_config, ArchiveConfig):
            self.config = archive_config
        else:
            self.config = ArchiveConfig()
        
        # 运行状态
        self.is_running = False
        self.start_time = None
        self.archive_task = None
        self.cleanup_task = None
        self.heartbeat_task = None
        
        # NATS客户端（可选）
        self.nats_client = None
        self.nats_js = None
        
        # 统计信息
        self.stats = {
            'archives_completed': 0,
            'records_archived': 0,
            'cleanup_completed': 0,
            'records_cleaned': 0,
            'errors': 0,
            'last_archive_time': None,
            'last_cleanup_time': None
        }
        
        logger.info(f"归档管理器已初始化，配置: {self.config}")
    
    async def start(self):
        """启动归档管理器"""
        if self.is_running:
            logger.warning("归档管理器已在运行")
            return
        
        self.is_running = True
        self.start_time = time.time()
        
        # 确保存储管理器已启动
        if not self.hot_storage.is_running:
            await self.hot_storage.start()
        
        if self.cold_storage and not self.cold_storage.is_running:
            await self.cold_storage.start()
        
        # 连接NATS（如果启用）
        if self.config.nats_enabled and NATS_AVAILABLE:
            await self._connect_nats()
        
        # 启动定时任务
        if self.config.enabled:
            self.archive_task = asyncio.create_task(self._archive_scheduler())
        
        if self.config.cleanup_enabled:
            self.cleanup_task = asyncio.create_task(self._cleanup_scheduler())
        
        # 启动心跳任务（如果启用NATS）
        if self.config.nats_enabled and self.nats_client:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info("归档管理器已启动")
    
    async def stop(self):
        """停止归档管理器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 停止定时任务
        for task in [self.archive_task, self.cleanup_task, self.heartbeat_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 关闭NATS连接
        if self.nats_client:
            await self.nats_client.close()
        
        logger.info("归档管理器已停止")
    
    # ==================== 核心归档功能 ====================
    
    async def archive_data(self, 
                          tables: Optional[List[str]] = None,
                          retention_days: Optional[int] = None,
                          force: bool = False,
                          dry_run: bool = False) -> Dict[str, int]:
        """
        归档数据到冷存储
        
        Args:
            tables: 要归档的表列表（None表示所有表）
            retention_days: 保留天数（覆盖配置）
            force: 是否强制归档
            dry_run: 是否仅模拟运行
            
        Returns:
            每个表归档的记录数
        """
        if not self.cold_storage:
            logger.error("冷存储未配置，无法执行归档")
            return {}
        
        retention_days = retention_days or self.config.retention_days
        cutoff_date = datetime.now() - datetime.timedelta(days=retention_days)
        
        logger.info(f"开始归档数据，截止日期: {cutoff_date.strftime('%Y-%m-%d')}")
        
        # 获取要归档的表
        if tables is None:
            tables = await self._get_archivable_tables()
        
        results = {}
        total_archived = 0
        
        for table in tables:
            try:
                count = await self._archive_table(table, cutoff_date, force, dry_run)
                results[table] = count
                total_archived += count
                logger.info(f"表 {table} 归档完成，迁移 {count} 条记录")
            except Exception as e:
                logger.error(f"表 {table} 归档失败: {e}")
                results[table] = -1
                self.stats['errors'] += 1
        
        # 更新统计
        if not dry_run:
            self.stats['archives_completed'] += 1
            self.stats['records_archived'] += total_archived
            self.stats['last_archive_time'] = datetime.now().isoformat()
        
        logger.info(f"归档完成，共处理 {len(tables)} 个表，归档 {total_archived} 条记录")
        return results
    
    async def restore_data(self,
                          table: str,
                          date_from: str,
                          date_to: str,
                          dry_run: bool = False) -> int:
        """
        从冷存储恢复数据到热存储
        
        Args:
            table: 表名
            date_from: 起始日期 (YYYY-MM-DD)
            date_to: 结束日期 (YYYY-MM-DD)
            dry_run: 是否仅模拟运行
            
        Returns:
            恢复的记录数
        """
        if not self.cold_storage:
            logger.error("冷存储未配置，无法恢复数据")
            return 0
        
        logger.info(f"准备从冷存储恢复表 {table} 的数据，日期范围: {date_from} 到 {date_to}")
        
        try:
            # 查询冷存储中的数据
            query = f"""
                SELECT * FROM {table}
                WHERE timestamp >= '{date_from}' AND timestamp <= '{date_to}'
                ORDER BY timestamp
            """
            
            # 使用冷存储的查询接口
            if hasattr(self.cold_storage, 'clickhouse_client'):
                results = await self.cold_storage.clickhouse_client.fetchall(query)
            else:
                logger.error("冷存储客户端不可用")
                return 0
            
            if not results:
                logger.info("没有找到符合条件的数据")
                return 0
            
            total_count = len(results)
            logger.info(f"找到 {total_count} 条记录需要恢复")
            
            if dry_run:
                logger.info("模拟运行模式，不实际恢复数据")
                return total_count
            
            # 批量写入热存储
            batch_size = self.config.batch_size
            restored_count = 0
            
            for i in range(0, total_count, batch_size):
                batch = results[i:i + batch_size]
                
                # 根据表类型选择适当的存储方法
                for record in batch:
                    record_dict = dict(record) if hasattr(record, '_asdict') else record
                    
                    if table.endswith('trades'):
                        await self.hot_storage.store_trade(record_dict)
                    elif table.endswith('tickers'):
                        await self.hot_storage.store_ticker(record_dict)
                    elif table.endswith('orderbooks'):
                        await self.hot_storage.store_orderbook(record_dict)
                    else:
                        # 通用存储方法
                        await self.hot_storage.write_data(record_dict, table)
                
                restored_count += len(batch)
                logger.debug(f"已恢复 {restored_count}/{total_count} 条记录")
            
            logger.info(f"表 {table} 恢复完成，共恢复 {restored_count} 条记录")
            return restored_count
            
        except Exception as e:
            logger.error(f"恢复数据失败: {e}")
            self.stats['errors'] += 1
            return 0
    
    async def cleanup_expired_data(self,
                                  tables: Optional[List[str]] = None,
                                  max_age_days: Optional[int] = None,
                                  force: bool = False,
                                  dry_run: bool = False) -> Dict[str, int]:
        """
        清理过期数据
        
        Args:
            tables: 要清理的表列表
            max_age_days: 最大保留天数
            force: 是否强制清理
            dry_run: 是否仅模拟运行
            
        Returns:
            每个表清理的记录数
        """
        max_age_days = max_age_days or self.config.max_age_days
        cutoff_date = datetime.now() - datetime.timedelta(days=max_age_days)
        
        logger.info(f"开始清理过期数据，截止日期: {cutoff_date.strftime('%Y-%m-%d')}")
        
        if tables is None:
            tables = await self._get_cleanable_tables()
        
        results = {}
        total_cleaned = 0
        
        for table in tables:
            try:
                count = await self._cleanup_table(table, cutoff_date, force, dry_run)
                results[table] = count
                total_cleaned += count
                logger.info(f"表 {table} 清理完成，删除 {count} 条记录")
            except Exception as e:
                logger.error(f"表 {table} 清理失败: {e}")
                results[table] = -1
                self.stats['errors'] += 1
        
        # 更新统计
        if not dry_run:
            self.stats['cleanup_completed'] += 1
            self.stats['records_cleaned'] += total_cleaned
            self.stats['last_cleanup_time'] = datetime.now().isoformat()
        
        logger.info(f"清理完成，共处理 {len(tables)} 个表，清理 {total_cleaned} 条记录")
        return results
    
    # ==================== 内部方法 ====================
    
    async def _archive_table(self, table: str, cutoff_date: datetime, 
                            force: bool, dry_run: bool) -> int:
        """归档单个表的数据"""
        # 计算要归档的记录数
        count_query = f"""
            SELECT count() FROM {table} 
            WHERE timestamp < '{cutoff_date.strftime('%Y-%m-%d')}'
        """
        
        if hasattr(self.hot_storage, 'clickhouse_client'):
            result = await self.hot_storage.clickhouse_client.fetchone(count_query)
            total_count = result[0] if result else 0
        else:
            total_count = 0
        
        if total_count == 0:
            logger.info(f"表 {table} 没有需要归档的数据")
            return 0
        
        if dry_run:
            logger.info(f"模拟运行：表 {table} 将归档 {total_count} 条记录")
            return total_count
        
        # 实际归档逻辑（分批处理）
        query = f"""
            SELECT * FROM {table}
            WHERE timestamp < '{cutoff_date.strftime('%Y-%m-%d')}'
            ORDER BY timestamp
        """
        
        archived_count = 0
        batch_size = self.config.batch_size
        
        # 分批查询和迁移
        offset = 0
        while True:
            batch_query = f"{query} LIMIT {batch_size} OFFSET {offset}"
            
            if hasattr(self.hot_storage, 'clickhouse_client'):
                batch_results = await self.hot_storage.clickhouse_client.fetchall(batch_query)
            else:
                break
            
            if not batch_results:
                break
            
            # 写入冷存储
            for record in batch_results:
                record_dict = dict(record) if hasattr(record, '_asdict') else record
                
                # 添加归档时间戳
                record_dict['archived_at'] = datetime.now()
                
                # 写入冷存储
                if hasattr(self.cold_storage, 'clickhouse_client'):
                    # 这里需要根据具体的表结构调整插入逻辑
                    pass
            
            archived_count += len(batch_results)
            offset += batch_size
            
            # 如果批次小于batch_size，说明已经处理完所有数据
            if len(batch_results) < batch_size:
                break
        
        # 从热存储删除已归档的数据
        if archived_count > 0 and not dry_run:
            delete_query = f"""
                ALTER TABLE {table} 
                DELETE WHERE timestamp < '{cutoff_date.strftime('%Y-%m-%d')}'
            """
            
            if hasattr(self.hot_storage, 'clickhouse_client'):
                await self.hot_storage.clickhouse_client.execute(delete_query)
        
        return archived_count
    
    async def _cleanup_table(self, table: str, cutoff_date: datetime,
                           force: bool, dry_run: bool) -> int:
        """清理单个表的过期数据"""
        # 计算要清理的记录数
        count_query = f"""
            SELECT count() FROM {table}
            WHERE timestamp < '{cutoff_date.strftime('%Y-%m-%d')}'
        """
        
        if hasattr(self.hot_storage, 'clickhouse_client'):
            result = await self.hot_storage.clickhouse_client.fetchone(count_query)
            total_count = result[0] if result else 0
        else:
            total_count = 0
        
        if total_count == 0:
            return 0
        
        if dry_run:
            logger.info(f"模拟运行：表 {table} 将清理 {total_count} 条记录")
            return total_count
        
        # 执行清理
        delete_query = f"""
            ALTER TABLE {table}
            DELETE WHERE timestamp < '{cutoff_date.strftime('%Y-%m-%d')}'
        """
        
        if hasattr(self.hot_storage, 'clickhouse_client'):
            await self.hot_storage.clickhouse_client.execute(delete_query)
        
        return total_count
    
    async def _get_archivable_tables(self) -> List[str]:
        """获取可归档的表列表"""
        # 从热存储获取表列表
        if hasattr(self.hot_storage, 'clickhouse_client'):
            query = "SHOW TABLES"
            results = await self.hot_storage.clickhouse_client.fetchall(query)
            return [row[0] for row in results if not row[0].startswith('system')]
        return []
    
    async def _get_cleanable_tables(self) -> List[str]:
        """获取可清理的表列表"""
        return await self._get_archivable_tables()
    
    # ==================== 调度器 ====================
    
    async def _archive_scheduler(self):
        """归档任务调度器"""
        if not croniter:
            logger.error("croniter不可用，无法启动归档调度器")
            return
        
        cron = croniter(self.config.schedule, datetime.now())
        next_run = cron.get_next(datetime)
        
        logger.info(f"归档调度器已启动，下次运行时间: {next_run}")
        
        while self.is_running:
            now = datetime.now()
            
            if now >= next_run:
                logger.info(f"执行计划归档任务: {now}")
                try:
                    await self.archive_data()
                    next_run = cron.get_next(datetime)
                    logger.info(f"下次归档时间: {next_run}")
                except Exception as e:
                    logger.error(f"归档任务执行失败: {e}")
                    # 发生错误时，延迟1小时后重试
                    next_run = now + datetime.timedelta(hours=1)
            
            # 每分钟检查一次
            await asyncio.sleep(60)
    
    async def _cleanup_scheduler(self):
        """清理任务调度器"""
        if not croniter:
            logger.error("croniter不可用，无法启动清理调度器")
            return
        
        cron = croniter(self.config.cleanup_schedule, datetime.now())
        next_run = cron.get_next(datetime)
        
        logger.info(f"清理调度器已启动，下次运行时间: {next_run}")
        
        while self.is_running:
            now = datetime.now()
            
            if now >= next_run:
                logger.info(f"执行计划清理任务: {now}")
                try:
                    await self.cleanup_expired_data()
                    next_run = cron.get_next(datetime)
                    logger.info(f"下次清理时间: {next_run}")
                except Exception as e:
                    logger.error(f"清理任务执行失败: {e}")
                    next_run = now + datetime.timedelta(hours=1)
            
            # 每分钟检查一次
            await asyncio.sleep(60)
    
    # ==================== NATS集成 ====================
    
    async def _connect_nats(self):
        """连接NATS服务器"""
        if not NATS_AVAILABLE:
            logger.warning("NATS不可用，跳过连接")
            return
        
        try:
            self.nats_client = await nats.connect(self.config.nats_url)
            self.nats_js = self.nats_client.jetstream()
            logger.info(f"NATS连接成功: {self.config.nats_url}")
        except Exception as e:
            logger.error(f"NATS连接失败: {e}")
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.is_running:
            try:
                heartbeat = {
                    "service": "archive_manager",
                    "timestamp": datetime.now().isoformat(),
                    "status": "healthy",
                    "stats": self.stats.copy()
                }
                
                if self.nats_js:
                    await self.nats_js.publish(
                        "system.heartbeat.archive_manager",
                        json.dumps(heartbeat).encode()
                    )
            except Exception as e:
                logger.error(f"发送心跳失败: {e}")
            
            await asyncio.sleep(self.config.heartbeat_interval)
    
    # ==================== 状态和监控 ====================
    
    def get_status(self) -> Dict[str, Any]:
        """获取归档管理器状态"""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            'is_running': self.is_running,
            'uptime_seconds': uptime,
            'config': {
                'enabled': self.config.enabled,
                'schedule': self.config.schedule,
                'retention_days': self.config.retention_days,
                'cleanup_enabled': self.config.cleanup_enabled,
                'nats_enabled': self.config.nats_enabled
            },
            'storage': {
                'hot_storage_running': self.hot_storage.is_running if self.hot_storage else False,
                'cold_storage_running': self.cold_storage.is_running if self.cold_storage else False,
                'cold_storage_available': self.cold_storage is not None
            },
            'stats': self.stats.copy(),
            'tasks': {
                'archive_task_running': self.archive_task and not self.archive_task.done(),
                'cleanup_task_running': self.cleanup_task and not self.cleanup_task.done(),
                'heartbeat_task_running': self.heartbeat_task and not self.heartbeat_task.done()
            }
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()


# ==================== 向后兼容接口 ====================

class DataArchiver:
    """向后兼容的DataArchiver接口"""
    
    def __init__(self, config_path=None):
        logger.warning("DataArchiver已废弃，请使用ArchiveManager")
        # 创建简化的配置
        self.archive_manager = None
        logger.info("DataArchiver兼容层已初始化")
    
    async def archive_tables(self, tables=None, days=None, force=False, dry_run=False):
        """兼容的归档接口"""
        if self.archive_manager:
            return await self.archive_manager.archive_data(tables, days, force, dry_run)
        return {}
    
    async def restore_data(self, table, date_from, date_to, dry_run=False):
        """兼容的恢复接口"""
        if self.archive_manager:
            return await self.archive_manager.restore_data(table, date_from, date_to, dry_run)
        return 0
    
    def get_status(self):
        """兼容的状态接口"""
        if self.archive_manager:
            return self.archive_manager.get_status()
        return {'status': 'deprecated'}


class DataArchiverService:
    """向后兼容的DataArchiverService接口"""
    
    def __init__(self, config_path=None):
        logger.warning("DataArchiverService已废弃，请使用ArchiveManager")
        self.archive_manager = None
        self.running = False
    
    async def start_async(self):
        """兼容的启动接口"""
        if self.archive_manager:
            await self.archive_manager.start()
        self.running = True
    
    async def stop_async(self):
        """兼容的停止接口"""
        if self.archive_manager:
            await self.archive_manager.stop()
        self.running = False
    
    def health_check(self):
        """兼容的健康检查接口"""
        if self.archive_manager:
            return self.archive_manager.get_status()
        return {'status': 'deprecated', 'healthy': False}