"""
MarketPrism 数据迁移服务
负责将热数据迁移到冷存储，并进行数据一致性验证
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import structlog
from dataclasses import dataclass
import json

from .storage_config_manager import StorageConfigManager, StorageMode

logger = structlog.get_logger(__name__)

@dataclass
class MigrationTask:
    """迁移任务"""
    table_name: str
    partition_id: str
    start_time: datetime
    end_time: datetime
    record_count: int
    size_bytes: int
    priority: int = 1

@dataclass
class MigrationResult:
    """迁移结果"""
    task: MigrationTask
    success: bool
    migrated_records: int
    duration_seconds: float
    error_message: Optional[str] = None

class DataMigrationService:
    """数据迁移服务"""
    
    def __init__(self, config_manager: StorageConfigManager):
        self.config_manager = config_manager
        self.migration_config = config_manager.get_migration_config()
        self.clickhouse_config = config_manager.get_clickhouse_config()
        self.ttl_config = config_manager.get_ttl_config()
        
        # 只有热存储模式才启用迁移服务
        self.enabled = config_manager.is_hot_storage() and self.migration_config.enabled
        
        # HTTP会话
        self.session: Optional[aiohttp.ClientSession] = None
        
        # 迁移统计
        self.stats = {
            'total_migrations': 0,
            'successful_migrations': 0,
            'failed_migrations': 0,
            'total_records_migrated': 0,
            'total_bytes_migrated': 0,
            'last_migration_time': None,
            'current_migration_status': 'idle'
        }
        
        logger.info(
            "数据迁移服务初始化",
            enabled=self.enabled,
            cold_endpoint=self.migration_config.cold_storage_endpoint if self.enabled else None
        )
    
    async def start(self):
        """启动迁移服务"""
        if not self.enabled:
            logger.info("数据迁移服务未启用")
            return
        
        # 创建HTTP会话
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),
            headers={'Content-Type': 'application/json'}
        )
        
        logger.info("数据迁移服务已启动")
    
    async def stop(self):
        """停止迁移服务"""
        if self.session:
            await self.session.close()
        logger.info("数据迁移服务已停止")
    
    async def execute_migration_cycle(self) -> List[MigrationResult]:
        """执行一次完整的迁移周期"""
        if not self.enabled:
            return []
        
        logger.info("开始执行数据迁移周期")
        self.stats['current_migration_status'] = 'running'
        
        try:
            # 1. 识别需要迁移的数据
            migration_tasks = await self._identify_migration_tasks()
            
            if not migration_tasks:
                logger.info("没有需要迁移的数据")
                return []
            
            logger.info(f"发现 {len(migration_tasks)} 个迁移任务")
            
            # 2. 按优先级排序任务
            migration_tasks.sort(key=lambda x: (-x.priority, x.start_time))
            
            # 3. 执行迁移任务
            results = []
            for task in migration_tasks:
                try:
                    result = await self._execute_migration_task(task)
                    results.append(result)
                    
                    # 更新统计信息
                    self._update_stats(result)
                    
                    # 短暂延迟，避免过载
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"迁移任务执行失败: {e}", task=task)
                    results.append(MigrationResult(
                        task=task,
                        success=False,
                        migrated_records=0,
                        duration_seconds=0,
                        error_message=str(e)
                    ))
            
            # 4. 清理已迁移的热数据
            await self._cleanup_migrated_data(results)
            
            self.stats['last_migration_time'] = datetime.now()
            logger.info(f"迁移周期完成，处理了 {len(results)} 个任务")
            
            return results
            
        except Exception as e:
            logger.error(f"迁移周期执行失败: {e}")
            return []
        finally:
            self.stats['current_migration_status'] = 'idle'
    
    async def _identify_migration_tasks(self) -> List[MigrationTask]:
        """识别需要迁移的数据"""
        tasks = []
        
        # 计算迁移阈值时间
        threshold_time = datetime.now() - timedelta(hours=self.migration_config.strategy['age_threshold_hours'])
        
        # 查询需要迁移的分区
        tables = ['hot_trades', 'hot_tickers', 'hot_orderbooks']
        
        for table in tables:
            try:
                # 查询过期分区
                query = f"""
                SELECT 
                    partition,
                    min(timestamp) as start_time,
                    max(timestamp) as end_time,
                    count() as record_count,
                    sum(bytes_on_disk) as size_bytes
                FROM system.parts 
                WHERE 
                    database = '{self.clickhouse_config.database}'
                    AND table = '{table}'
                    AND max_time < '{threshold_time.strftime('%Y-%m-%d %H:%M:%S')}'
                    AND active = 1
                GROUP BY partition
                ORDER BY start_time
                """
                
                partitions = await self._execute_clickhouse_query(query)
                
                for partition in partitions:
                    # 计算优先级
                    priority = self._calculate_migration_priority(table, partition)
                    
                    task = MigrationTask(
                        table_name=table,
                        partition_id=partition['partition'],
                        start_time=partition['start_time'],
                        end_time=partition['end_time'],
                        record_count=partition['record_count'],
                        size_bytes=partition['size_bytes'],
                        priority=priority
                    )
                    tasks.append(task)
                    
            except Exception as e:
                logger.error(f"查询表 {table} 的迁移任务失败: {e}")
        
        return tasks
    
    def _calculate_migration_priority(self, table: str, partition: Dict[str, Any]) -> int:
        """计算迁移优先级"""
        priority = 1
        
        # 根据表类型调整优先级
        if table == 'hot_trades':
            priority += 3  # 交易数据优先级最高
        elif table == 'hot_tickers':
            priority += 2  # 行情数据次之
        elif table == 'hot_orderbooks':
            priority += 1  # 订单簿数据最低
        
        # 根据数据大小调整优先级
        size_mb = partition['size_bytes'] / (1024 * 1024)
        if size_mb > self.migration_config.strategy['size_threshold_mb']:
            priority += 2  # 大分区优先迁移
        
        return priority
    
    async def _execute_migration_task(self, task: MigrationTask) -> MigrationResult:
        """执行单个迁移任务"""
        start_time = datetime.now()
        
        try:
            logger.info(f"开始迁移任务: {task.table_name}:{task.partition_id}")
            
            # 1. 从热存储读取数据
            data = await self._read_partition_data(task)
            
            # 2. 写入冷存储
            await self._write_to_cold_storage(task, data)
            
            # 3. 验证数据一致性（如果启用）
            if self.migration_config.verification_enabled:
                await self._verify_migration(task)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                f"迁移任务完成: {task.table_name}:{task.partition_id}",
                records=len(data),
                duration=duration
            )
            
            return MigrationResult(
                task=task,
                success=True,
                migrated_records=len(data),
                duration_seconds=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"迁移任务失败: {task.table_name}:{task.partition_id}, 错误: {e}")
            
            return MigrationResult(
                task=task,
                success=False,
                migrated_records=0,
                duration_seconds=duration,
                error_message=str(e)
            )
    
    async def _read_partition_data(self, task: MigrationTask) -> List[Dict[str, Any]]:
        """从热存储读取分区数据"""
        query = f"""
        SELECT * FROM {self.clickhouse_config.database}.{task.table_name}
        WHERE partition = '{task.partition_id}'
        ORDER BY timestamp
        LIMIT {self.migration_config.batch_size}
        FORMAT JSONEachRow
        """
        
        return await self._execute_clickhouse_query(query, format_json=True)
    
    async def _write_to_cold_storage(self, task: MigrationTask, data: List[Dict[str, Any]]):
        """写入数据到冷存储"""
        if not data:
            return
        
        # 转换表名（hot_ -> cold_）
        cold_table = task.table_name.replace('hot_', 'cold_')
        
        # 构建插入语句
        insert_query = f"INSERT INTO marketprism_cold.{cold_table} FORMAT JSONEachRow"
        
        # 准备数据
        json_data = '\n'.join(json.dumps(row) for row in data)
        
        # 发送到冷存储
        async with self.session.post(
            f"{self.migration_config.cold_storage_endpoint}/",
            data=f"{insert_query}\n{json_data}",
            headers={'Content-Type': 'text/plain'}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"冷存储写入失败: {response.status}, {error_text}")
    
    async def _verify_migration(self, task: MigrationTask):
        """验证迁移数据一致性"""
        # 查询热存储记录数
        hot_count_query = f"""
        SELECT count() as count 
        FROM {self.clickhouse_config.database}.{task.table_name}
        WHERE partition = '{task.partition_id}'
        """
        hot_result = await self._execute_clickhouse_query(hot_count_query)
        hot_count = hot_result[0]['count']
        
        # 查询冷存储记录数
        cold_table = task.table_name.replace('hot_', 'cold_')
        cold_count_query = f"""
        SELECT count() as count 
        FROM marketprism_cold.{cold_table}
        WHERE partition = '{task.partition_id}'
        """
        
        async with self.session.post(
            f"{self.migration_config.cold_storage_endpoint}/",
            data=cold_count_query,
            headers={'Content-Type': 'text/plain'}
        ) as response:
            if response.status != 200:
                raise Exception(f"冷存储验证查询失败: {response.status}")
            
            cold_result = await response.json()
            cold_count = cold_result[0]['count']
        
        if hot_count != cold_count:
            raise Exception(f"数据一致性验证失败: 热存储={hot_count}, 冷存储={cold_count}")
        
        logger.info(f"数据一致性验证通过: {task.table_name}:{task.partition_id}, 记录数={hot_count}")
    
    async def _cleanup_migrated_data(self, results: List[MigrationResult]):
        """清理已成功迁移的热数据"""
        for result in results:
            if result.success:
                try:
                    # 删除已迁移的分区
                    drop_query = f"""
                    ALTER TABLE {self.clickhouse_config.database}.{result.task.table_name}
                    DROP PARTITION '{result.task.partition_id}'
                    """
                    
                    await self._execute_clickhouse_query(drop_query)
                    
                    logger.info(f"已清理迁移数据: {result.task.table_name}:{result.task.partition_id}")
                    
                except Exception as e:
                    logger.error(f"清理迁移数据失败: {e}", task=result.task)
    
    async def _execute_clickhouse_query(self, query: str, format_json: bool = False) -> List[Dict[str, Any]]:
        """执行ClickHouse查询"""
        url = f"http://{self.clickhouse_config.host}:{self.clickhouse_config.port}/"
        
        async with self.session.post(url, data=query) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"ClickHouse查询失败: {response.status}, {error_text}")
            
            if format_json:
                text = await response.text()
                return [json.loads(line) for line in text.strip().split('\n') if line]
            else:
                return await response.json()
    
    def _update_stats(self, result: MigrationResult):
        """更新迁移统计信息"""
        self.stats['total_migrations'] += 1
        
        if result.success:
            self.stats['successful_migrations'] += 1
            self.stats['total_records_migrated'] += result.migrated_records
        else:
            self.stats['failed_migrations'] += 1
    
    def get_migration_stats(self) -> Dict[str, Any]:
        """获取迁移统计信息"""
        return self.stats.copy()
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """获取迁移状态"""
        # 查询待迁移数据量
        pending_tasks = await self._identify_migration_tasks()
        
        return {
            'service_enabled': self.enabled,
            'current_status': self.stats['current_migration_status'],
            'pending_migrations': len(pending_tasks),
            'total_pending_records': sum(task.record_count for task in pending_tasks),
            'last_migration': self.stats['last_migration_time'].isoformat() if self.stats['last_migration_time'] else None,
            'statistics': self.stats
        }
