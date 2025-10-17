#!/usr/bin/env python3
"""
MarketPrism ClickHouse 数据库初始化脚本
自动创建数据库、表结构和索引
"""

import asyncio
import sys
import os
from pathlib import Path
import yaml
import structlog
from typing import Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from core.storage.unified_clickhouse_writer import UnifiedClickHouseWriter


class ClickHouseInitializer:
    """ClickHouse数据库初始化器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化ClickHouse初始化器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = structlog.get_logger("clickhouse.initializer")
        
        # 热端和冷端配置
        self.hot_config = config.get('hot_storage', {})
        self.cold_config = config.get('cold_storage', {})
        
        # ClickHouse客户端
        self.hot_client = None
        self.cold_client = None
    
    async def initialize(self):
        """初始化ClickHouse数据库"""
        try:
            self.logger.info("🚀 开始初始化ClickHouse数据库")
            
            # 初始化热端数据库
            await self._initialize_hot_storage()
            
            # 初始化冷端数据库（如果配置了）
            if self.cold_config.get('clickhouse_host') != self.hot_config.get('clickhouse_host'):
                await self._initialize_cold_storage()
            else:
                self.logger.info("🔄 冷端和热端使用相同数据库，跳过冷端初始化")
            
            self.logger.info("✅ ClickHouse数据库初始化完成")
            
        except Exception as e:
            self.logger.error("❌ ClickHouse数据库初始化失败", error=str(e))
            raise
    
    async def _initialize_hot_storage(self):
        """初始化热端存储"""
        try:
            self.logger.info("🔥 初始化热端ClickHouse数据库")
            
            # 创建ClickHouse客户端配置
            hot_clickhouse_config = {
                'clickhouse_direct_write': True,
                'clickhouse': {
                    'host': self.hot_config.get('clickhouse_host', 'localhost'),
                    'port': self.hot_config.get('clickhouse_http_port', 8123),
                    'user': self.hot_config.get('clickhouse_user', 'default'),
                    'password': self.hot_config.get('clickhouse_password', ''),
                    'database': self.hot_config.get('clickhouse_database', 'marketprism_hot')
                }
            }

            self.hot_client = UnifiedClickHouseWriter(hot_clickhouse_config)
            
            await self.hot_client.start()
            
            # 创建数据库
            await self._create_database(
                self.hot_client,
                self.hot_config.get('clickhouse_database', 'marketprism_hot')
            )
            
            # 创建表结构
            await self._create_tables(self.hot_client, 'hot')
            
            # 创建索引
            await self._create_indexes(self.hot_client)
            
            self.logger.info("✅ 热端ClickHouse数据库初始化完成")
            
        except Exception as e:
            self.logger.error(f"❌ 热端ClickHouse数据库初始化失败: {e}")
            raise
    
    async def _initialize_cold_storage(self):
        """初始化冷端存储"""
        try:
            self.logger.info("🧊 初始化冷端ClickHouse数据库")
            
            # 创建ClickHouse客户端配置
            cold_clickhouse_config = {
                'clickhouse_direct_write': True,
                'clickhouse': {
                    'host': self.cold_config.get('clickhouse_host', 'localhost'),
                    'port': self.cold_config.get('clickhouse_http_port', 8123),
                    'user': self.cold_config.get('clickhouse_user', 'default'),
                    'password': self.cold_config.get('clickhouse_password', ''),
                    'database': self.cold_config.get('clickhouse_database', 'marketprism_cold')
                }
            }

            self.cold_client = UnifiedClickHouseWriter(cold_clickhouse_config)
            
            await self.cold_client.start()
            
            # 创建数据库
            await self._create_database(
                self.cold_client,
                self.cold_config.get('clickhouse_database', 'marketprism_cold')
            )
            
            # 创建表结构
            await self._create_tables(self.cold_client, 'cold')
            
            # 创建索引
            await self._create_indexes(self.cold_client)
            
            self.logger.info("✅ 冷端ClickHouse数据库初始化完成")
            
        except Exception as e:
            self.logger.error("❌ 冷端ClickHouse数据库初始化失败", error=str(e))
            raise
    
    async def _create_database(self, client: UnifiedClickHouseWriter, database_name: str):
        """创建数据库"""
        try:
            query = f"CREATE DATABASE IF NOT EXISTS {database_name}"
            await client.execute_query(query)
            self.logger.info("✅ 数据库创建成功", database=database_name)
        except Exception as e:
            self.logger.error("❌ 数据库创建失败", database=database_name, error=str(e))
            raise
    
    async def _create_tables(self, client: UnifiedClickHouseWriter, storage_type: str):
        """创建表结构"""
        try:
            # 读取表结构SQL文件
            schema_file = Path(__file__).parent.parent / "config" / "clickhouse_schema.sql"
            
            if not schema_file.exists():
                raise FileNotFoundError(f"表结构文件不存在: {schema_file}")
            
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            # 分割SQL语句
            statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
            
            # 过滤相关的SQL语句
            if storage_type == 'hot':
                # 执行热端相关的SQL
                relevant_statements = [
                    stmt for stmt in statements 
                    if 'marketprism_hot' in stmt or 'USE marketprism_hot' in stmt or 
                       ('CREATE TABLE' in stmt and 'marketprism_cold' not in stmt and 'USE marketprism_cold' not in stmt)
                ]
            else:
                # 执行冷端相关的SQL
                relevant_statements = [
                    stmt for stmt in statements 
                    if 'marketprism_cold' in stmt or 'USE marketprism_cold' in stmt
                ]
            
            # 执行SQL语句
            for statement in relevant_statements:
                if statement:
                    try:
                        await client.execute_query(statement)
                        self.logger.debug("✅ SQL语句执行成功", statement=statement[:100])
                    except Exception as e:
                        self.logger.warning("⚠️ SQL语句执行失败", 
                                          statement=statement[:100], 
                                          error=str(e))
            
            self.logger.info("✅ 表结构创建完成", storage_type=storage_type)
            
        except Exception as e:
            self.logger.error("❌ 表结构创建失败", storage_type=storage_type, error=str(e))
            raise
    
    async def _create_indexes(self, client: UnifiedClickHouseWriter):
        """创建索引"""
        try:
            # 索引创建SQL（从schema文件中提取）
            index_statements = [
                "ALTER TABLE orderbooks ADD INDEX IF NOT EXISTS idx_price_range (best_bid_price, best_ask_price) TYPE minmax GRANULARITY 4",
                "ALTER TABLE trades ADD INDEX IF NOT EXISTS idx_price_quantity (price, quantity) TYPE minmax GRANULARITY 4",
                "ALTER TABLE trades ADD INDEX IF NOT EXISTS idx_trade_time (trade_time) TYPE minmax GRANULARITY 4",
                "ALTER TABLE funding_rates ADD INDEX IF NOT EXISTS idx_funding_rate (funding_rate) TYPE minmax GRANULARITY 4",
                "ALTER TABLE open_interests ADD INDEX IF NOT EXISTS idx_open_interest (open_interest) TYPE minmax GRANULARITY 4",
                "ALTER TABLE liquidations ADD INDEX IF NOT EXISTS idx_liquidation_price (price) TYPE minmax GRANULARITY 4",
                "ALTER TABLE lsrs ADD INDEX IF NOT EXISTS idx_lsr_ratio (long_short_ratio) TYPE minmax GRANULARITY 4",
                "ALTER TABLE volatility_indices ADD INDEX IF NOT EXISTS idx_volatility_value (index_value) TYPE minmax GRANULARITY 4"
            ]
            
            for statement in index_statements:
                try:
                    await client.execute_query(statement)
                    self.logger.debug("✅ 索引创建成功", statement=statement[:50])
                except Exception as e:
                    self.logger.warning("⚠️ 索引创建失败", 
                                      statement=statement[:50], 
                                      error=str(e))
            
            self.logger.info("✅ 索引创建完成")
            
        except Exception as e:
            self.logger.error("❌ 索引创建失败", error=str(e))
            raise
    
    async def verify_setup(self):
        """验证数据库设置"""
        try:
            self.logger.info("🔍 验证ClickHouse数据库设置")
            
            # 验证热端数据库
            if self.hot_client:
                await self._verify_database(self.hot_client, "热端")
            
            # 验证冷端数据库
            if self.cold_client:
                await self._verify_database(self.cold_client, "冷端")
            
            self.logger.info("✅ ClickHouse数据库验证完成")
            
        except Exception as e:
            self.logger.error("❌ ClickHouse数据库验证失败", error=str(e))
            raise
    
    async def _verify_database(self, client: UnifiedClickHouseWriter, db_type: str):
        """验证单个数据库"""
        try:
            # 检查表是否存在
            tables = ['orderbooks', 'trades', 'funding_rates', 'open_interests', 
                     'liquidations', 'lsrs', 'volatility_indices']
            
            for table in tables:
                query = f"SELECT count() FROM {table} LIMIT 1"
                result = await client.execute_query(query)
                self.logger.info(f"✅ {db_type}表验证成功", table=table)
            
            self.logger.info(f"✅ {db_type}数据库验证完成")
            
        except Exception as e:
            self.logger.error(f"❌ {db_type}数据库验证失败", error=str(e))
            raise
    
    async def close(self):
        """关闭连接"""
        try:
            if self.hot_client:
                await self.hot_client.close()
            
            if self.cold_client:
                await self.cold_client.close()
            
            self.logger.info("✅ ClickHouse连接已关闭")
            
        except Exception as e:
            self.logger.error("❌ 关闭ClickHouse连接失败", error=str(e))


async def main():
    """主函数"""
    try:
        # 加载配置
        config_path = Path(__file__).parent.parent / "config" / "hot_storage_config.yaml"

        if not config_path.exists():
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 初始化ClickHouse
        initializer = ClickHouseInitializer(config)
        await initializer.initialize()
        await initializer.verify_setup()
        await initializer.close()
        
        print("🎉 ClickHouse数据库初始化成功！")
        
    except Exception as e:
        print(f"❌ ClickHouse数据库初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
