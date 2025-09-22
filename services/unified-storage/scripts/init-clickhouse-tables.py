#!/usr/bin/env python3
"""
MarketPrism ClickHouse表初始化脚本
确保所有必要的表结构存在
"""
import asyncio
import aiohttp
import logging
import time

logger = logging.getLogger("clickhouse-init")

# 8种数据类型的表结构
TABLE_SCHEMAS = {
    "orderbooks": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.orderbooks (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        bids Array(Tuple(Float64, Float64)),
        asks Array(Tuple(Float64, Float64)),
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """,
    
    "trades": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.trades (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        price Float64,
        amount Float64,
        side String,
        trade_id String,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """,
    
    "funding_rates": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.funding_rates (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        funding_rate Float64,
        next_funding_time DateTime,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """,
    
    "open_interests": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.open_interests (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        open_interest Float64,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """,
    
    "liquidations": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.liquidations (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        side String,
        price Float64,
        amount Float64,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """,
    
    "lsr_top_positions": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.lsr_top_positions (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        long_short_ratio Float64,
        long_account Float64,
        short_account Float64,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """,
    
    "lsr_all_accounts": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.lsr_all_accounts (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        long_short_ratio Float64,
        long_account Float64,
        short_account Float64,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """,
    
    "volatility_indices": """
    CREATE TABLE IF NOT EXISTS marketprism_hot.volatility_indices (
        timestamp DateTime,
        exchange String,
        market String,
        symbol String,
        volatility_index Float64,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, timestamp)
    SETTINGS index_granularity = 8192
    """
}

async def wait_for_clickhouse():
    """等待ClickHouse服务可用"""
    max_retries = 30
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8123/ping", timeout=5) as resp:
                    if resp.status == 200:
                        logger.info("ClickHouse服务已就绪")
                        return True
        except Exception as e:
            logger.info(f"等待ClickHouse服务... ({retry_count + 1}/{max_retries})")
            retry_count += 1
            await asyncio.sleep(2)
    
    logger.error("ClickHouse服务启动超时")
    return False

async def create_database():
    """创建数据库"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8123/",
                data="CREATE DATABASE IF NOT EXISTS marketprism_hot",
                timeout=10
            ) as resp:
                if resp.status == 200:
                    logger.info("数据库 marketprism_hot 创建成功")
                    return True
                else:
                    logger.error(f"创建数据库失败: {resp.status}")
                    return False
    except Exception as e:
        logger.error(f"创建数据库异常: {e}")
        return False

async def create_tables():
    """创建所有表"""
    success_count = 0
    
    for table_name, schema in TABLE_SCHEMAS.items():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:8123/",
                    data=schema,
                    timeout=30
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"表 {table_name} 创建成功")
                        success_count += 1
                    else:
                        logger.error(f"创建表 {table_name} 失败: {resp.status}")
        except Exception as e:
            logger.error(f"创建表 {table_name} 异常: {e}")
    
    logger.info(f"成功创建 {success_count}/{len(TABLE_SCHEMAS)} 个表")
    return success_count == len(TABLE_SCHEMAS)

async def main():
    """主函数"""
    logging.basicConfig(level=logging.INFO)
    logger.info("开始初始化ClickHouse表结构...")
    
    # 等待ClickHouse服务
    if not await wait_for_clickhouse():
        exit(1)
    
    # 创建数据库
    if not await create_database():
        exit(1)
    
    # 创建表
    if not await create_tables():
        exit(1)
    
    logger.info("ClickHouse表结构初始化完成")

if __name__ == "__main__":
    asyncio.run(main())
