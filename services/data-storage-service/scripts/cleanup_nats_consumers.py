#!/usr/bin/env python3
"""
清理NATS JetStream consumers
"""

import asyncio
import nats
from nats.js import JetStreamContext


async def cleanup_consumers():
    """清理所有consumers"""
    try:
        print("🧹 开始清理NATS consumers")
        
        # 连接NATS
        nc = await nats.connect("nats://localhost:4222")
        js = nc.jetstream()
        
        # 获取stream信息
        try:
            stream_info = await js.stream_info("MARKET_DATA")
            print(f"✅ 找到stream: MARKET_DATA")
        except Exception as e:
            print(f"❌ 获取stream信息失败: {e}")
            return
        
        # 删除所有consumers
        consumer_names = [
            "simple_hot_storage_orderbook",
            "simple_hot_storage_trade", 
            "simple_hot_storage_funding_rate",
            "simple_hot_storage_open_interest",
            "simple_hot_storage_liquidation",
            "simple_hot_storage_lsr",
            "simple_hot_storage_volatility_index"
        ]
        
        for consumer_name in consumer_names:
            try:
                await js.delete_consumer("MARKET_DATA", consumer_name)
                print(f"✅ 删除consumer: {consumer_name}")
            except Exception as e:
                print(f"⚠️ 删除consumer失败 {consumer_name}: {e}")
        
        # 关闭连接
        await nc.close()
        print("✅ NATS consumers清理完成")
        
    except Exception as e:
        print(f"❌ 清理失败: {e}")


if __name__ == "__main__":
    asyncio.run(cleanup_consumers())
