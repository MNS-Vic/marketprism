#!/usr/bin/env python3
"""
MarketPrism ClickHouse 数据库简化初始化脚本
直接使用ClickHouse HTTP API创建数据库和表结构
"""

import asyncio
import sys
import os
from pathlib import Path
import yaml
import aiohttp
import json


class SimpleClickHouseInitializer:
    """简化的ClickHouse数据库初始化器"""
    
    def __init__(self, config: dict):
        """
        初始化ClickHouse初始化器
        
        Args:
            config: 配置字典
        """
        self.config = config
        
        # 热端和冷端配置
        self.hot_config = config.get('hot_storage', {})
        self.cold_config = config.get('cold_storage', {})
    
    async def initialize(self):
        """初始化ClickHouse数据库"""
        try:
            print("🚀 开始初始化ClickHouse数据库")
            
            # 初始化热端数据库
            await self._initialize_hot_storage()
            
            # 初始化冷端数据库（如果配置了不同的主机）
            if self.cold_config.get('clickhouse_host') != self.hot_config.get('clickhouse_host'):
                await self._initialize_cold_storage()
            else:
                print("🔄 冷端和热端使用相同数据库，跳过冷端初始化")
            
            print("✅ ClickHouse数据库初始化完成")
            
        except Exception as e:
            print(f"❌ ClickHouse数据库初始化失败: {e}")
            raise
    
    async def _initialize_hot_storage(self):
        """初始化热端存储"""
        try:
            print("🔥 初始化热端ClickHouse数据库")
            
            host = self.hot_config.get('clickhouse_host', 'localhost')
            port = self.hot_config.get('clickhouse_http_port', 8123)
            user = self.hot_config.get('clickhouse_user', 'default')
            password = self.hot_config.get('clickhouse_password', '')
            database = self.hot_config.get('clickhouse_database', 'marketprism_hot')
            
            # 创建数据库
            await self._create_database(host, port, user, password, database)
            
            # 创建表结构
            await self._create_tables(host, port, user, password, database, 'hot')
            
            print("✅ 热端ClickHouse数据库初始化完成")
            
        except Exception as e:
            print(f"❌ 热端ClickHouse数据库初始化失败: {e}")
            raise
    
    async def _initialize_cold_storage(self):
        """初始化冷端存储"""
        try:
            print("🧊 初始化冷端ClickHouse数据库")
            
            host = self.cold_config.get('clickhouse_host', 'localhost')
            port = self.cold_config.get('clickhouse_http_port', 8123)
            user = self.cold_config.get('clickhouse_user', 'default')
            password = self.cold_config.get('clickhouse_password', '')
            database = self.cold_config.get('clickhouse_database', 'marketprism_cold')
            
            # 创建数据库
            await self._create_database(host, port, user, password, database)
            
            # 创建表结构
            await self._create_tables(host, port, user, password, database, 'cold')
            
            print("✅ 冷端ClickHouse数据库初始化完成")
            
        except Exception as e:
            print(f"❌ 冷端ClickHouse数据库初始化失败: {e}")
            raise
    
    async def _create_database(self, host: str, port: int, user: str, password: str, database: str):
        """创建数据库"""
        try:
            query = f"CREATE DATABASE IF NOT EXISTS {database}"
            await self._execute_query(host, port, user, password, query)
            print(f"✅ 数据库创建成功: {database}")
        except Exception as e:
            print(f"❌ 数据库创建失败 {database}: {e}")
            raise
    
    async def _create_tables(self, host: str, port: int, user: str, password: str, database: str, storage_type: str):
        """创建表结构"""
        try:
            # 切换到目标数据库
            await self._execute_query(host, port, user, password, f"USE {database}")
            
            # 定义表结构
            tables = self._get_table_definitions(storage_type)
            
            # 创建表
            for table_name, table_sql in tables.items():
                try:
                    await self._execute_query(host, port, user, password, table_sql)
                    print(f"✅ 表创建成功: {table_name}")
                except Exception as e:
                    print(f"⚠️ 表创建失败 {table_name}: {e}")
            
            print(f"✅ 表结构创建完成: {storage_type}")
            
        except Exception as e:
            print(f"❌ 表结构创建失败 {storage_type}: {e}")
            raise
    
    def _get_table_definitions(self, storage_type: str) -> dict:
        """获取表定义"""
        ttl_days = 3 if storage_type == 'hot' else 365
        
        return {
            "orderbooks": f"""
                CREATE TABLE IF NOT EXISTS orderbooks (
                    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    exchange LowCardinality(String) CODEC(ZSTD),
                    market_type LowCardinality(String) CODEC(ZSTD),
                    symbol LowCardinality(String) CODEC(ZSTD),
                    last_update_id UInt64 CODEC(Delta, ZSTD),
                    bids_count UInt32 CODEC(Delta, ZSTD),
                    asks_count UInt32 CODEC(Delta, ZSTD),
                    best_bid_price Decimal64(8) CODEC(ZSTD),
                    best_ask_price Decimal64(8) CODEC(ZSTD),
                    best_bid_quantity Decimal64(8) CODEC(ZSTD),
                    best_ask_quantity Decimal64(8) CODEC(ZSTD),
                    bids String CODEC(ZSTD),
                    asks String CODEC(ZSTD),
                    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
                    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
                )
                ENGINE = MergeTree()
                PARTITION BY (toYYYYMM(timestamp), exchange)
                ORDER BY (timestamp, exchange, symbol, last_update_id)
                TTL toDateTime(timestamp) + INTERVAL {ttl_days} DAY DELETE
                SETTINGS index_granularity = 8192
            """,

            "trades": f"""
                CREATE TABLE IF NOT EXISTS trades (
                    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    exchange LowCardinality(String) CODEC(ZSTD),
                    market_type LowCardinality(String) CODEC(ZSTD),
                    symbol LowCardinality(String) CODEC(ZSTD),
                    trade_id String CODEC(ZSTD),
                    price Decimal64(8) CODEC(ZSTD),
                    quantity Decimal64(8) CODEC(ZSTD),
                    side LowCardinality(String) CODEC(ZSTD),
                    is_maker Bool DEFAULT false CODEC(ZSTD),
                    trade_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
                    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
                )
                ENGINE = MergeTree()
                PARTITION BY (toYYYYMM(timestamp), exchange)
                ORDER BY (timestamp, exchange, symbol, trade_id)
                TTL toDateTime(timestamp) + INTERVAL {ttl_days} DAY DELETE
                SETTINGS index_granularity = 8192
            """,
            
            "funding_rates": f"""
                CREATE TABLE IF NOT EXISTS funding_rates (
                    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    exchange LowCardinality(String) CODEC(ZSTD),
                    market_type LowCardinality(String) CODEC(ZSTD),
                    symbol LowCardinality(String) CODEC(ZSTD),
                    funding_rate Decimal64(8) CODEC(ZSTD),
                    funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    next_funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    mark_price Decimal64(8) CODEC(ZSTD),
                    index_price Decimal64(8) CODEC(ZSTD),
                    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
                    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
                )
                ENGINE = MergeTree()
                PARTITION BY (toYYYYMM(timestamp), exchange)
                ORDER BY (timestamp, exchange, symbol)
                TTL toDateTime(timestamp) + INTERVAL {ttl_days} DAY DELETE
                SETTINGS index_granularity = 8192
            """,

            "open_interests": f"""
                CREATE TABLE IF NOT EXISTS open_interests (
                    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    exchange LowCardinality(String) CODEC(ZSTD),
                    market_type LowCardinality(String) CODEC(ZSTD),
                    symbol LowCardinality(String) CODEC(ZSTD),
                    open_interest Decimal64(8) CODEC(ZSTD),
                    open_interest_value Decimal64(8) CODEC(ZSTD),
                    count UInt64 CODEC(Delta, ZSTD),
                    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
                    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
                )
                ENGINE = MergeTree()
                PARTITION BY (toYYYYMM(timestamp), exchange)
                ORDER BY (timestamp, exchange, symbol)
                TTL toDateTime(timestamp) + INTERVAL {ttl_days} DAY DELETE
                SETTINGS index_granularity = 8192
            """,

            "liquidations": f"""
                CREATE TABLE IF NOT EXISTS liquidations (
                    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    exchange LowCardinality(String) CODEC(ZSTD),
                    market_type LowCardinality(String) CODEC(ZSTD),
                    symbol LowCardinality(String) CODEC(ZSTD),
                    side LowCardinality(String) CODEC(ZSTD),
                    price Decimal64(8) CODEC(ZSTD),
                    quantity Decimal64(8) CODEC(ZSTD),
                    liquidation_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
                    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
                )
                ENGINE = MergeTree()
                PARTITION BY (toYYYYMM(timestamp), exchange)
                ORDER BY (timestamp, exchange, symbol)
                TTL toDateTime(timestamp) + INTERVAL {ttl_days} DAY DELETE
                SETTINGS index_granularity = 8192
            """,

            "lsrs": f"""
                CREATE TABLE IF NOT EXISTS lsrs (
                    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    exchange LowCardinality(String) CODEC(ZSTD),
                    market_type LowCardinality(String) CODEC(ZSTD),
                    symbol LowCardinality(String) CODEC(ZSTD),
                    long_short_ratio Decimal64(8) CODEC(ZSTD),
                    long_account Decimal64(8) CODEC(ZSTD),
                    short_account Decimal64(8) CODEC(ZSTD),
                    period LowCardinality(String) CODEC(ZSTD),
                    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
                    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
                )
                ENGINE = MergeTree()
                PARTITION BY (toYYYYMM(timestamp), exchange)
                ORDER BY (timestamp, exchange, symbol, period)
                TTL toDateTime(timestamp) + INTERVAL {ttl_days} DAY DELETE
                SETTINGS index_granularity = 8192
            """,

            "volatility_indices": f"""
                CREATE TABLE IF NOT EXISTS volatility_indices (
                    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
                    exchange LowCardinality(String) CODEC(ZSTD),
                    market_type LowCardinality(String) CODEC(ZSTD),
                    symbol LowCardinality(String) CODEC(ZSTD),
                    index_value Decimal64(8) CODEC(ZSTD),
                    underlying_asset LowCardinality(String) CODEC(ZSTD),
                    maturity_date Date CODEC(ZSTD),
                    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
                    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
                )
                ENGINE = MergeTree()
                PARTITION BY (toYYYYMM(timestamp), exchange)
                ORDER BY (timestamp, exchange, symbol)
                TTL toDateTime(timestamp) + INTERVAL {ttl_days} DAY DELETE
                SETTINGS index_granularity = 8192
            """
        }
    
    async def _execute_query(self, host: str, port: int, user: str, password: str, query: str):
        """执行ClickHouse查询"""
        url = f"http://{host}:{port}/"
        
        auth = None
        if user and password:
            auth = aiohttp.BasicAuth(user, password)
        elif user:
            auth = aiohttp.BasicAuth(user, '')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=query, auth=auth) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"ClickHouse查询失败 (状态码: {response.status}): {error_text}")
                
                return await response.text()
    
    async def verify_setup(self):
        """验证数据库设置"""
        try:
            print("🔍 验证ClickHouse数据库设置")
            
            # 验证热端数据库
            await self._verify_database(
                self.hot_config.get('clickhouse_host', 'localhost'),
                self.hot_config.get('clickhouse_http_port', 8123),
                self.hot_config.get('clickhouse_user', 'default'),
                self.hot_config.get('clickhouse_password', ''),
                self.hot_config.get('clickhouse_database', 'marketprism_hot'),
                "热端"
            )
            
            # 验证冷端数据库（如果不同）
            if self.cold_config.get('clickhouse_host') != self.hot_config.get('clickhouse_host'):
                await self._verify_database(
                    self.cold_config.get('clickhouse_host', 'localhost'),
                    self.cold_config.get('clickhouse_http_port', 8123),
                    self.cold_config.get('clickhouse_user', 'default'),
                    self.cold_config.get('clickhouse_password', ''),
                    self.cold_config.get('clickhouse_database', 'marketprism_cold'),
                    "冷端"
                )
            
            print("✅ ClickHouse数据库验证完成")
            
        except Exception as e:
            print(f"❌ ClickHouse数据库验证失败: {e}")
            raise
    
    async def _verify_database(self, host: str, port: int, user: str, password: str, database: str, db_type: str):
        """验证单个数据库"""
        try:
            # 检查表是否存在
            tables = ['orderbooks', 'trades', 'funding_rates', 'open_interests', 
                     'liquidations', 'lsrs', 'volatility_indices']
            
            # 先切换到数据库
            await self._execute_query(host, port, user, password, f"USE {database}")

            for table in tables:
                query = f"SELECT count() FROM {table} LIMIT 1"
                await self._execute_query(host, port, user, password, query)
                print(f"✅ {db_type}表验证成功: {table}")
            
            print(f"✅ {db_type}数据库验证完成")
            
        except Exception as e:
            print(f"❌ {db_type}数据库验证失败: {e}")
            raise


async def main():
    """主函数"""
    try:
        # 加载配置
        config_path = Path(__file__).parent.parent / "config" / "tiered_storage_config.yaml"
        
        if not config_path.exists():
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 初始化ClickHouse
        initializer = SimpleClickHouseInitializer(config)
        await initializer.initialize()
        await initializer.verify_setup()
        
        print("🎉 ClickHouse数据库初始化成功！")
        
    except Exception as e:
        print(f"❌ ClickHouse数据库初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
