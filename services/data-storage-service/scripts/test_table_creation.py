#!/usr/bin/env python3
"""
测试ClickHouse表创建
"""

import asyncio
import aiohttp


async def test_table_creation():
    """测试表创建"""
    
    # 简化的表定义
    table_sql = """
        CREATE TABLE IF NOT EXISTS marketprism_hot.orderbooks_simple (
            timestamp DateTime64(3, 'UTC'),
            exchange String,
            symbol String,
            price Decimal64(8),
            quantity Decimal64(8)
        )
        ENGINE = MergeTree()
        ORDER BY (timestamp, exchange, symbol)
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:8123/", data=table_sql) as response:
                if response.status == 200:
                    print("✅ 简化表创建成功")
                    result = await response.text()
                    print(f"结果: {result}")
                else:
                    error_text = await response.text()
                    print(f"❌ 表创建失败 (状态码: {response.status}): {error_text}")
    
    except Exception as e:
        print(f"❌ 异常: {e}")
    
    # 验证表是否存在
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:8123/", data="SELECT name FROM system.tables WHERE database = 'marketprism_hot'") as response:
                if response.status == 200:
                    result = await response.text()
                    print(f"✅ 当前表列表:\n{result}")
                else:
                    error_text = await response.text()
                    print(f"❌ 查询失败: {error_text}")
    except Exception as e:
        print(f"❌ 查询异常: {e}")


if __name__ == "__main__":
    asyncio.run(test_table_creation())
