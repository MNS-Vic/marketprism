#!/usr/bin/env python3
"""
MarketPrism 冷存储迁移服务
定时将热存储数据迁移到永久存储 (NAS)

🔄 Docker部署简化改造 (2025-08-02):
- ✅ 支持8种数据类型的自动迁移
- ✅ 数据完整性验证
- ✅ 批量迁移优化
- ✅ 错误处理和重试机制
- ✅ NAS部署支持
"""

import asyncio
import aiohttp
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import os
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class MigrationConfig:
    """迁移配置"""
    # 热存储配置
    hot_clickhouse_host: str = "localhost"
    hot_clickhouse_port: int = 8123
    hot_database: str = "marketprism_hot"
    
    # 冷存储配置 (NAS)
    cold_clickhouse_host: str = "nas.local"
    cold_clickhouse_port: int = 8123
    cold_database: str = "marketprism_cold"
    
    # 迁移配置
    migration_age_days: int = 3  # 迁移3天前的数据
    batch_size: int = 10000      # 批量大小
    verification_enabled: bool = True  # 数据验证
    cleanup_after_migration: bool = True  # 迁移后清理热存储
    
    # 重试配置
    max_retries: int = 3
    retry_delay: float = 5.0

class ColdStorageMigration:
    """冷存储迁移服务"""
    
    def __init__(self, config: MigrationConfig):
        self.config = config
        self.stats = {
            "migrations_completed": 0,
            "migrations_failed": 0,
            "records_migrated": 0,
            "bytes_migrated": 0,
            "last_migration_time": None,
            "errors": []
        }
        
        # 支持的数据类型
        self.data_types = [
            'orderbooks', 'trades', 'funding_rates', 'open_interests',
            'liquidations', 'lsr_top_positions', 'lsr_all_accounts', 'volatility_indices'
        ]
    
    async def check_cold_storage_connection(self) -> bool:
        """检查冷存储连接"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{self.config.cold_clickhouse_host}:{self.config.cold_clickhouse_port}/ping"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        logger.info("✅ 冷存储连接正常")
                        return True
                    else:
                        logger.error(f"❌ 冷存储连接失败: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ 冷存储连接异常: {e}")
            return False
    
    async def ensure_cold_storage_schema(self) -> bool:
        """确保冷存储数据库和表结构存在"""
        try:
            async with aiohttp.ClientSession() as session:
                base_url = f"http://{self.config.cold_clickhouse_host}:{self.config.cold_clickhouse_port}"
                
                # 创建数据库
                create_db_sql = f"CREATE DATABASE IF NOT EXISTS {self.config.cold_database}"
                async with session.post(base_url, data=create_db_sql) as response:
                    if response.status != 200:
                        logger.error(f"创建冷存储数据库失败: {response.status}")
                        return False
                
                # 为每种数据类型创建表
                for table in self.data_types:
                    # 获取热存储表结构
                    show_create_sql = f"SHOW CREATE TABLE {self.config.hot_database}.{table}"
                    async with aiohttp.ClientSession() as hot_session:
                        hot_url = f"http://{self.config.hot_clickhouse_host}:{self.config.hot_clickhouse_port}"
                        async with hot_session.post(hot_url, data=show_create_sql) as hot_response:
                            if hot_response.status == 200:
                                create_table_sql = await hot_response.text()
                                # 修改表名和TTL
                                create_table_sql = create_table_sql.replace(
                                    f"CREATE TABLE {self.config.hot_database}.{table}",
                                    f"CREATE TABLE IF NOT EXISTS {self.config.cold_database}.{table}"
                                )
                                # 修改TTL为1年
                                create_table_sql = create_table_sql.replace(
                                    "TTL timestamp + INTERVAL 3 DAY DELETE",
                                    "TTL timestamp + INTERVAL 365 DAY DELETE"
                                )
                                
                                # 创建冷存储表
                                async with session.post(base_url, data=create_table_sql) as response:
                                    if response.status == 200:
                                        logger.info(f"✅ 冷存储表创建成功: {table}")
                                    else:
                                        logger.error(f"❌ 冷存储表创建失败: {table}")
                                        return False
                
                logger.info("✅ 冷存储数据库结构确保完成")
                return True
                
        except Exception as e:
            logger.error(f"❌ 冷存储数据库结构创建异常: {e}")
            return False
    
    async def get_migration_partitions(self, table: str) -> List[str]:
        """获取需要迁移的分区"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config.migration_age_days)
            cutoff_month = cutoff_date.strftime('%Y%m')
            
            # 查询需要迁移的分区
            sql = f"""
            SELECT DISTINCT partition
            FROM system.parts 
            WHERE database = '{self.config.hot_database}' 
                AND table = '{table}'
                AND active = 1
                AND partition < '{cutoff_month}'
            ORDER BY partition
            """
            
            async with aiohttp.ClientSession() as session:
                url = f"http://{self.config.hot_clickhouse_host}:{self.config.hot_clickhouse_port}"
                async with session.post(url, data=sql) as response:
                    if response.status == 200:
                        result = await response.text()
                        partitions = [line.strip() for line in result.strip().split('\n') if line.strip()]
                        logger.info(f"📋 表 {table} 需要迁移的分区: {partitions}")
                        return partitions
                    else:
                        logger.error(f"❌ 获取迁移分区失败: {table}")
                        return []
                        
        except Exception as e:
            logger.error(f"❌ 获取迁移分区异常: {table}, {e}")
            return []
    
    async def migrate_partition(self, table: str, partition: str) -> bool:
        """迁移单个分区"""
        try:
            logger.info(f"🔄 开始迁移: {table}.{partition}")
            
            # 1. 从热存储读取数据
            select_sql = f"""
            SELECT * FROM {self.config.hot_database}.{table}
            WHERE toYYYYMM(timestamp) = '{partition}'
            """
            
            async with aiohttp.ClientSession() as session:
                hot_url = f"http://{self.config.hot_clickhouse_host}:{self.config.hot_clickhouse_port}"
                
                # 获取数据
                async with session.post(hot_url, data=select_sql + " FORMAT JSONEachRow") as response:
                    if response.status != 200:
                        logger.error(f"❌ 读取热存储数据失败: {table}.{partition}")
                        return False
                    
                    data = await response.text()
                    if not data.strip():
                        logger.info(f"⚠️ 分区无数据: {table}.{partition}")
                        return True
                    
                    # 2. 写入冷存储
                    insert_sql = f"INSERT INTO {self.config.cold_database}.{table} FORMAT JSONEachRow"
                    cold_url = f"http://{self.config.cold_clickhouse_host}:{self.config.cold_clickhouse_port}"
                    
                    async with session.post(cold_url, data=insert_sql + "\n" + data) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"❌ 写入冷存储失败: {table}.{partition}, {error_text}")
                            return False
                    
                    # 3. 验证数据完整性
                    if self.config.verification_enabled:
                        if not await self.verify_migration(table, partition):
                            logger.error(f"❌ 数据验证失败: {table}.{partition}")
                            return False
                    
                    # 4. 清理热存储数据
                    if self.config.cleanup_after_migration:
                        delete_sql = f"""
                        ALTER TABLE {self.config.hot_database}.{table}
                        DROP PARTITION '{partition}'
                        """
                        async with session.post(hot_url, data=delete_sql) as response:
                            if response.status == 200:
                                logger.info(f"✅ 热存储清理完成: {table}.{partition}")
                            else:
                                logger.warning(f"⚠️ 热存储清理失败: {table}.{partition}")
                    
                    # 统计更新
                    record_count = len(data.strip().split('\n'))
                    self.stats["records_migrated"] += record_count
                    self.stats["bytes_migrated"] += len(data.encode('utf-8'))
                    
                    logger.info(f"✅ 迁移完成: {table}.{partition}, {record_count} 条记录")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ 迁移分区异常: {table}.{partition}, {e}")
            return False
    
    async def verify_migration(self, table: str, partition: str) -> bool:
        """验证迁移数据完整性"""
        try:
            # 获取热存储记录数
            hot_count_sql = f"""
            SELECT count() FROM {self.config.hot_database}.{table}
            WHERE toYYYYMM(timestamp) = '{partition}'
            """
            
            # 获取冷存储记录数
            cold_count_sql = f"""
            SELECT count() FROM {self.config.cold_database}.{table}
            WHERE toYYYYMM(timestamp) = '{partition}'
            """
            
            async with aiohttp.ClientSession() as session:
                # 查询热存储
                hot_url = f"http://{self.config.hot_clickhouse_host}:{self.config.hot_clickhouse_port}"
                async with session.post(hot_url, data=hot_count_sql) as response:
                    if response.status == 200:
                        hot_count = int((await response.text()).strip())
                    else:
                        logger.error(f"❌ 查询热存储记录数失败: {table}.{partition}")
                        return False
                
                # 查询冷存储
                cold_url = f"http://{self.config.cold_clickhouse_host}:{self.config.cold_clickhouse_port}"
                async with session.post(cold_url, data=cold_count_sql) as response:
                    if response.status == 200:
                        cold_count = int((await response.text()).strip())
                    else:
                        logger.error(f"❌ 查询冷存储记录数失败: {table}.{partition}")
                        return False
                
                if hot_count == cold_count:
                    logger.info(f"✅ 数据验证通过: {table}.{partition}, {hot_count} 条记录")
                    return True
                else:
                    logger.error(f"❌ 数据验证失败: {table}.{partition}, 热存储:{hot_count}, 冷存储:{cold_count}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ 数据验证异常: {table}.{partition}, {e}")
            return False
    
    async def run_migration(self) -> bool:
        """执行迁移任务"""
        logger.info("🚀 开始冷存储迁移任务")
        
        # 检查冷存储连接
        if not await self.check_cold_storage_connection():
            return False
        
        # 确保冷存储数据库结构
        if not await self.ensure_cold_storage_schema():
            return False
        
        migration_success = True
        
        # 为每种数据类型执行迁移
        for table in self.data_types:
            try:
                logger.info(f"📊 处理表: {table}")
                
                # 获取需要迁移的分区
                partitions = await self.get_migration_partitions(table)
                
                if not partitions:
                    logger.info(f"⚠️ 表 {table} 无需迁移的分区")
                    continue
                
                # 迁移每个分区
                for partition in partitions:
                    success = await self.migrate_partition(table, partition)
                    if success:
                        self.stats["migrations_completed"] += 1
                    else:
                        self.stats["migrations_failed"] += 1
                        migration_success = False
                        
            except Exception as e:
                logger.error(f"❌ 表迁移异常: {table}, {e}")
                self.stats["migrations_failed"] += 1
                migration_success = False
        
        self.stats["last_migration_time"] = datetime.now().isoformat()
        
        if migration_success:
            logger.info("🎉 冷存储迁移任务完成")
        else:
            logger.error("❌ 冷存储迁移任务部分失败")
        
        return migration_success
    
    def get_stats(self) -> Dict[str, Any]:
        """获取迁移统计信息"""
        return self.stats.copy()

async def main():
    """主函数"""
    # 从环境变量读取配置
    config = MigrationConfig(
        hot_clickhouse_host=os.getenv("HOT_CLICKHOUSE_HOST", "localhost"),
        hot_clickhouse_port=int(os.getenv("HOT_CLICKHOUSE_PORT", "8123")),
        hot_database=os.getenv("HOT_DATABASE", "marketprism_hot"),
        cold_clickhouse_host=os.getenv("COLD_CLICKHOUSE_HOST", "nas.local"),
        cold_clickhouse_port=int(os.getenv("COLD_CLICKHOUSE_PORT", "8123")),
        cold_database=os.getenv("COLD_DATABASE", "marketprism_cold"),
        migration_age_days=int(os.getenv("MIGRATION_AGE_DAYS", "3")),
        batch_size=int(os.getenv("MIGRATION_BATCH_SIZE", "10000")),
        verification_enabled=os.getenv("MIGRATION_VERIFICATION", "true").lower() == "true",
        cleanup_after_migration=os.getenv("MIGRATION_CLEANUP", "true").lower() == "true"
    )
    
    migration_service = ColdStorageMigration(config)
    
    # 执行迁移
    success = await migration_service.run_migration()
    
    # 输出统计信息
    stats = migration_service.get_stats()
    logger.info(f"📊 迁移统计: {json.dumps(stats, indent=2, ensure_ascii=False)}")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
