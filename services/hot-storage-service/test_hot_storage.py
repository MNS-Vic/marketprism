#!/usr/bin/env python3
"""
MarketPrism 热存储服务测试脚本
测试NATS连接和ClickHouse写入功能
"""

import asyncio
import json
import aiohttp
from datetime import datetime

async def test_clickhouse_connection():
    """测试ClickHouse连接"""
    print("🔧 测试ClickHouse连接...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8123/ping") as response:
                if response.status == 200:
                    result = await response.text()
                    print(f"✅ ClickHouse连接成功: {result.strip()}")
                    return True
                else:
                    print(f"❌ ClickHouse连接失败: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ ClickHouse连接异常: {e}")
        return False

async def test_clickhouse_tables():
    """测试ClickHouse表"""
    print("🔧 测试ClickHouse表...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:8123/", 
                                   data="SELECT name FROM system.tables WHERE database = 'marketprism_hot' ORDER BY name") as response:
                if response.status == 200:
                    tables = await response.text()
                    table_list = tables.strip().split('\n') if tables.strip() else []
                    print(f"✅ 找到 {len(table_list)} 个表:")
                    for table in table_list:
                        print(f"  - {table}")
                    return len(table_list) == 8
                else:
                    print(f"❌ 查询表失败: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ 查询表异常: {e}")
        return False

async def test_data_insert():
    """测试数据插入"""
    print("🔧 测试数据插入...")
    
    # 测试订单簿数据插入
    test_data = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'exchange': 'test_exchange',
        'market_type': 'spot',
        'symbol': 'BTC-USDT',
        'last_update_id': 12345,
        'best_bid_price': 45000.50,
        'best_ask_price': 45001.00,
        'bids': '[[45000.50, 1.5]]',
        'asks': '[[45001.00, 2.0]]',
        'data_source': 'test'
    }
    
    sql = f"""
    INSERT INTO marketprism_hot.orderbooks 
    (timestamp, exchange, market_type, symbol, last_update_id, best_bid_price, best_ask_price, bids, asks, data_source)
    VALUES 
    ('{test_data['timestamp']}', '{test_data['exchange']}', '{test_data['market_type']}', 
     '{test_data['symbol']}', {test_data['last_update_id']}, {test_data['best_bid_price']}, 
     {test_data['best_ask_price']}, '{test_data['bids']}', '{test_data['asks']}', '{test_data['data_source']}')
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:8123/", data=sql) as response:
                if response.status == 200:
                    print("✅ 测试数据插入成功")
                    
                    # 验证数据
                    async with session.post("http://localhost:8123/", 
                                           data="SELECT count() FROM marketprism_hot.orderbooks WHERE data_source = 'test'") as verify_response:
                        if verify_response.status == 200:
                            count = await verify_response.text()
                            print(f"✅ 验证成功，测试数据条数: {count.strip()}")
                            return True
                else:
                    error_text = await response.text()
                    print(f"❌ 数据插入失败: {response.status}, {error_text}")
                    return False
    except Exception as e:
        print(f"❌ 数据插入异常: {e}")
        return False

async def test_nats_connection():
    """测试NATS连接"""
    print("🔧 测试NATS连接...")
    
    try:
        import nats
        
        nc = await nats.connect("nats://localhost:4222")
        print("✅ NATS连接成功")
        
        # 测试JetStream
        js = nc.jetstream()
        print("✅ JetStream连接成功")
        
        await nc.close()
        return True
        
    except Exception as e:
        print(f"❌ NATS连接失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("🚀 MarketPrism热存储服务测试开始")
    print("=" * 50)
    
    # 测试ClickHouse连接
    ch_conn = await test_clickhouse_connection()
    
    # 测试ClickHouse表
    ch_tables = await test_clickhouse_tables()
    
    # 测试数据插入
    ch_insert = await test_data_insert()
    
    # 测试NATS连接
    nats_conn = await test_nats_connection()
    
    print("=" * 50)
    print("📊 测试结果总结:")
    print(f"  ClickHouse连接: {'✅ 通过' if ch_conn else '❌ 失败'}")
    print(f"  ClickHouse表: {'✅ 通过' if ch_tables else '❌ 失败'}")
    print(f"  数据插入: {'✅ 通过' if ch_insert else '❌ 失败'}")
    print(f"  NATS连接: {'✅ 通过' if nats_conn else '❌ 失败'}")
    
    if all([ch_conn, ch_tables, ch_insert, nats_conn]):
        print("🎉 所有测试通过！热存储服务准备就绪")
        return True
    else:
        print("❌ 部分测试失败，请检查配置")
        return False

if __name__ == "__main__":
    asyncio.run(main())
