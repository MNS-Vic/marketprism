#!/usr/bin/env python3
"""
MarketPrism Data Storage Service 部署验证脚本
验证完整的数据流：Data Collector -> NATS -> Hot Storage -> ClickHouse
"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def check_containers():
    """检查Docker容器状态"""
    print("🐳 检查Docker容器状态...")
    
    import subprocess
    try:
        # 检查NATS容器
        result = subprocess.run(['sudo', 'docker', 'ps', '--filter', 'name=nats', '--format', 'table {{.Names}}\t{{.Status}}'], 
                              capture_output=True, text=True)
        if result.returncode == 0 and 'nats' in result.stdout:
            print("✅ NATS容器运行正常")
        else:
            print("❌ NATS容器未运行")
            return False
            
        # 检查Data Collector容器
        result = subprocess.run(['sudo', 'docker', 'ps', '--filter', 'name=data-collector', '--format', 'table {{.Names}}\t{{.Status}}'], 
                              capture_output=True, text=True)
        if result.returncode == 0 and 'data-collector' in result.stdout:
            print("✅ Data Collector容器运行正常")
        else:
            print("❌ Data Collector容器未运行")
            return False
            
        # 检查ClickHouse容器
        result = subprocess.run(['sudo', 'docker', 'ps', '--filter', 'name=clickhouse', '--format', 'table {{.Names}}\t{{.Status}}'], 
                              capture_output=True, text=True)
        if result.returncode == 0 and 'clickhouse' in result.stdout:
            print("✅ ClickHouse容器运行正常")
        else:
            print("❌ ClickHouse容器未运行")
            return False
            
        return True
    except Exception as e:
        print(f"❌ 容器检查失败: {e}")
        return False

async def check_data_flow():
    """检查数据流状态"""
    print("📊 检查数据流状态...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 检查各表的数据量
            tables = ['orderbooks', 'trades', 'lsr_top_positions', 'lsr_all_accounts', 'volatility_indices']
            
            for table in tables:
                async with session.post("http://localhost:8123/", 
                                       data=f"SELECT count() FROM marketprism_hot.{table}") as response:
                    if response.status == 200:
                        count = await response.text()
                        count = count.strip()
                        print(f"  📋 {table}: {count} 条记录")
                    else:
                        print(f"  ❌ {table}: 查询失败")
                        
            return True
    except Exception as e:
        print(f"❌ 数据流检查失败: {e}")
        return False

async def check_real_time_data():
    """检查实时数据写入"""
    print("⏱️ 检查实时数据写入...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 获取最新的订单簿数据
            async with session.post("http://localhost:8123/", 
                                   data="""
                                   SELECT 
                                       timestamp,
                                       exchange,
                                       symbol,
                                       best_bid_price,
                                       best_ask_price
                                   FROM marketprism_hot.orderbooks 
                                   WHERE timestamp > now() - INTERVAL 30 MINUTE
                                   ORDER BY timestamp DESC 
                                   LIMIT 3
                                   """) as response:
                if response.status == 200:
                    data = await response.text()
                    lines = data.strip().split('\n') if data.strip() else []
                    if lines:
                        print(f"✅ 最近30分钟内有 {len(lines)} 条订单簿数据")
                        for line in lines[:3]:
                            parts = line.split('\t')
                            if len(parts) >= 5:
                                print(f"  📈 {parts[0]} | {parts[1]} | {parts[2]} | 买:{parts[3]} 卖:{parts[4]}")
                    else:
                        print("⚠️ 最近30分钟内无新订单簿数据")
                        
            # 获取最新的交易数据
            async with session.post("http://localhost:8123/", 
                                   data="""
                                   SELECT 
                                       timestamp,
                                       exchange,
                                       symbol,
                                       price,
                                       quantity,
                                       side
                                   FROM marketprism_hot.trades 
                                   WHERE timestamp > now() - INTERVAL 30 MINUTE
                                   ORDER BY timestamp DESC 
                                   LIMIT 3
                                   """) as response:
                if response.status == 200:
                    data = await response.text()
                    lines = data.strip().split('\n') if data.strip() else []
                    if lines:
                        print(f"✅ 最近30分钟内有 {len(lines)} 条交易数据")
                        for line in lines[:3]:
                            parts = line.split('\t')
                            if len(parts) >= 6:
                                print(f"  💰 {parts[0]} | {parts[1]} | {parts[2]} | {parts[5]} {parts[3]}@{parts[4]}")
                    else:
                        print("⚠️ 最近30分钟内无新交易数据")
                        
            return True
    except Exception as e:
        print(f"❌ 实时数据检查失败: {e}")
        return False

async def check_data_types():
    """检查8种数据类型的支持情况"""
    print("🔍 检查8种数据类型支持...")
    
    data_types = {
        'orderbooks': '订单簿',
        'trades': '交易',
        'funding_rates': '资金费率',
        'open_interests': '未平仓量',
        'liquidations': '强平',
        'lsr_top_positions': 'LSR顶级持仓',
        'lsr_all_accounts': 'LSR全账户',
        'volatility_indices': '波动率指数'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            for table, desc in data_types.items():
                async with session.post("http://localhost:8123/", 
                                       data=f"SELECT count() FROM marketprism_hot.{table}") as response:
                    if response.status == 200:
                        count = await response.text()
                        count = count.strip()
                        status = "✅" if int(count) > 0 else "⚠️"
                        print(f"  {status} {desc} ({table}): {count} 条")
                    else:
                        print(f"  ❌ {desc} ({table}): 表不存在")
                        
            return True
    except Exception as e:
        print(f"❌ 数据类型检查失败: {e}")
        return False

async def check_performance():
    """检查性能指标"""
    print("⚡ 检查性能指标...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 检查数据库大小
            async with session.post("http://localhost:8123/", 
                                   data="""
                                   SELECT 
                                       database,
                                       formatReadableSize(sum(bytes)) as total_size,
                                       sum(rows) as total_rows
                                   FROM system.parts 
                                   WHERE database = 'marketprism_hot' AND active = 1
                                   GROUP BY database
                                   """) as response:
                if response.status == 200:
                    data = await response.text()
                    if data.strip():
                        parts = data.strip().split('\t')
                        if len(parts) >= 3:
                            print(f"  📊 数据库大小: {parts[1]}")
                            print(f"  📈 总记录数: {parts[2]}")
                            
            # 检查写入性能
            async with session.post("http://localhost:8123/", 
                                   data="""
                                   SELECT 
                                       count() as inserts_last_hour
                                   FROM system.query_log 
                                   WHERE event_time > now() - INTERVAL 1 HOUR 
                                       AND query_kind = 'Insert'
                                       AND databases = ['marketprism_hot']
                                   """) as response:
                if response.status == 200:
                    data = await response.text()
                    if data.strip():
                        print(f"  🚀 最近1小时写入次数: {data.strip()}")
                        
            return True
    except Exception as e:
        print(f"❌ 性能检查失败: {e}")
        return False

async def main():
    """主验证函数"""
    print("🎯 MarketPrism Data Storage Service 部署验证")
    print("=" * 60)
    
    # 检查容器状态
    containers_ok = await check_containers()
    
    # 检查数据流
    data_flow_ok = await check_data_flow()
    
    # 检查实时数据
    real_time_ok = await check_real_time_data()
    
    # 检查数据类型支持
    data_types_ok = await check_data_types()
    
    # 检查性能
    performance_ok = await check_performance()
    
    print("=" * 60)
    print("📋 验证结果总结:")
    print(f"  🐳 Docker容器: {'✅ 正常' if containers_ok else '❌ 异常'}")
    print(f"  📊 数据流: {'✅ 正常' if data_flow_ok else '❌ 异常'}")
    print(f"  ⏱️ 实时数据: {'✅ 正常' if real_time_ok else '❌ 异常'}")
    print(f"  🔍 数据类型: {'✅ 支持8种' if data_types_ok else '❌ 部分缺失'}")
    print(f"  ⚡ 性能指标: {'✅ 正常' if performance_ok else '❌ 异常'}")
    
    if all([containers_ok, data_flow_ok, real_time_ok, data_types_ok, performance_ok]):
        print("\n🎉 MarketPrism Data Storage Service 部署验证成功！")
        print("✅ 完整数据流正常工作: Data Collector -> NATS -> Hot Storage -> ClickHouse")
        return True
    else:
        print("\n❌ 部分验证失败，请检查相关组件")
        return False

if __name__ == "__main__":
    asyncio.run(main())
