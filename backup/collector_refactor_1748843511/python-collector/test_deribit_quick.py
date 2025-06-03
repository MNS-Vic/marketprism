#!/usr/bin/env python3
"""
快速测试Deribit aiohttp适配器

30秒快速验证连接和数据接收
"""

import asyncio
import time
import json
import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
from marketprism_collector.exchanges.deribit_aiohttp import DeribitAiohttpAdapter


async def quick_test():
    """快速测试"""
    print("🚀 Deribit快速连接测试 (30秒)")
    print("=" * 60)
    
    # 创建配置
    config = ExchangeConfig(
        exchange=Exchange.DERIBIT,
        market_type=MarketType.DERIVATIVES,
        enabled=True,
        symbols=["BTC-PERPETUAL"],
        data_types=[DataType.TRADE],
        ws_url="wss://www.deribit.com/ws/api/v2",
        base_url="https://www.deribit.com",
        ping_interval=20,
        reconnect_attempts=3,
        reconnect_delay=5,
        depth_limit=20
    )
    
    # 创建适配器
    adapter = DeribitAiohttpAdapter(config)
    
    message_count = 0
    
    async def on_trade(trade):
        nonlocal message_count
        message_count += 1
        print(f"📈 交易数据 {message_count}: {trade.symbol_name} 价格={trade.price} 数量={trade.quantity}")
    
    adapter.register_callback(DataType.TRADE, on_trade)
    
    try:
        print("🔌 启动适配器...")
        success = await adapter.start()
        
        if not success:
            print("❌ 启动失败")
            return
        
        print("✅ 启动成功，等待30秒...")
        await asyncio.sleep(30)
        
        print(f"\n📊 结果: 接收到 {message_count} 条交易数据")
        
        if message_count > 0:
            print("🎉 测试成功！")
        else:
            print("⚠️ 未接收到数据")
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await adapter.stop()


if __name__ == "__main__":
    asyncio.run(quick_test())