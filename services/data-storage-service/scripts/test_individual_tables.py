#!/usr/bin/env python3
"""
逐个测试表创建
"""

import asyncio
import aiohttp


async def execute_query(query: str, description: str):
    """执行查询"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:8123/", data=query) as response:
                if response.status == 200:
                    result = await response.text()
                    print(f"✅ {description} 成功")
                    if result.strip():
                        print(f"   结果: {result.strip()}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ {description} 失败 (状态码: {response.status}): {error_text}")
                    return False
    except Exception as e:
        print(f"❌ {description} 异常: {e}")
        return False


async def test_orderbooks_table():
    """测试订单簿表"""
    print("\n🔍 测试订单簿表创建...")
    
    # 简化的订单簿表
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.orderbooks (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            market_type String,
            symbol String,
            last_update_id UInt64,
            best_bid_price Decimal64(8),
            best_ask_price Decimal64(8),
            bids String,
            asks String,
            data_source String DEFAULT 'marketprism'
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, exchange, symbol)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
    """
    
    return await execute_query(table_sql, "订单簿表创建")


async def test_trades_table():
    """测试交易表"""
    print("\n🔍 测试交易表创建...")
    
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.trades (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            market_type String,
            symbol String,
            trade_id String,
            price Decimal64(8),
            quantity Decimal64(8),
            side String,
            is_maker Bool DEFAULT false,
            data_source String DEFAULT 'marketprism'
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, exchange, symbol, trade_id)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
    """
    
    return await execute_query(table_sql, "交易表创建")


async def test_funding_rates_table():
    """测试资金费率表"""
    print("\n🔍 测试资金费率表创建...")
    
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.funding_rates (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            market_type String,
            symbol String,
            funding_rate Decimal64(8),
            funding_time DateTime64(3, 'UTC'),
            next_funding_time DateTime64(3, 'UTC'),
            data_source String DEFAULT 'marketprism'
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, exchange, symbol)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
    """
    
    return await execute_query(table_sql, "资金费率表创建")


async def test_open_interests_table():
    """测试未平仓量表"""
    print("\n🔍 测试未平仓量表创建...")
    
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.open_interests (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            market_type String,
            symbol String,
            open_interest Decimal64(8),
            open_interest_value Decimal64(8),
            count UInt64,
            data_source String DEFAULT 'marketprism'
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, exchange, symbol)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
    """
    
    return await execute_query(table_sql, "未平仓量表创建")


async def test_liquidations_table():
    """测试强平表"""
    print("\n🔍 测试强平表创建...")
    
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.liquidations (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            market_type String,
            symbol String,
            side String,
            price Decimal64(8),
            quantity Decimal64(8),
            liquidation_time DateTime64(3, 'UTC'),
            data_source String DEFAULT 'marketprism'
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, exchange, symbol)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
    """
    
    return await execute_query(table_sql, "强平表创建")


async def test_lsrs_table():
    """测试LSR表"""
    print("\n🔍 测试LSR表创建...")
    
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.lsrs (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            market_type String,
            symbol String,
            long_short_ratio Decimal64(8),
            long_account Decimal64(8),
            short_account Decimal64(8),
            period String,
            data_source String DEFAULT 'marketprism'
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, exchange, symbol, period)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
    """
    
    return await execute_query(table_sql, "LSR表创建")


async def test_volatility_indices_table():
    """测试波动率指数表"""
    print("\n🔍 测试波动率指数表创建...")
    
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.volatility_indices (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            market_type String,
            symbol String,
            index_value Decimal64(8),
            underlying_asset String,
            maturity_date Date,
            data_source String DEFAULT 'marketprism'
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, exchange, symbol)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
    """
    
    return await execute_query(table_sql, "波动率指数表创建")


async def verify_all_tables():
    """验证所有表"""
    print("\n🔍 验证所有表...")
    
    query = "SELECT name FROM system.tables WHERE database = 'marketprism_hot' ORDER BY name"
    await execute_query(query, "查询所有表")


async def main():
    """主函数"""
    print("🚀 开始逐个测试表创建")
    
    # 测试各个表
    success_count = 0
    total_count = 7
    
    if await test_orderbooks_table():
        success_count += 1
    
    if await test_trades_table():
        success_count += 1
    
    if await test_funding_rates_table():
        success_count += 1
    
    if await test_open_interests_table():
        success_count += 1
    
    if await test_liquidations_table():
        success_count += 1
    
    if await test_lsrs_table():
        success_count += 1
    
    if await test_volatility_indices_table():
        success_count += 1
    
    # 验证所有表
    await verify_all_tables()
    
    print(f"\n📊 表创建结果: {success_count}/{total_count} 成功")
    
    if success_count == total_count:
        print("🎉 所有表创建成功！")
    else:
        print("⚠️ 部分表创建失败")


if __name__ == "__main__":
    asyncio.run(main())
