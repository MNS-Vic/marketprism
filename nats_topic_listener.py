#!/usr/bin/env python3
"""
NATS主题监听器
用于调试和确认实际的NATS主题名称
"""

import asyncio
import nats
import json
from datetime import datetime

async def main():
    try:
        # 连接NATS
        nc = await nats.connect('nats://localhost:4222')
        print(f"✅ NATS连接成功 - {datetime.now()}")
        
        received_topics = set()
        message_count = 0
        
        async def message_handler(msg):
            nonlocal message_count
            message_count += 1
            received_topics.add(msg.subject)
            
            # 解析消息内容
            try:
                data = json.loads(msg.data.decode())
                symbol = data.get('symbol', 'unknown')
                exchange = data.get('exchange', 'unknown')
                best_bid = data.get('bids', [{}])[0].get('price', 'N/A') if data.get('bids') else 'N/A'
                best_ask = data.get('asks', [{}])[0].get('price', 'N/A') if data.get('asks') else 'N/A'
                
                print(f"📨 {msg.subject} | {exchange} {symbol} | {best_bid}/{best_ask}")
                
            except Exception as e:
                print(f"📨 {msg.subject} | 解析失败: {e}")
        
        # 订阅所有orderbook主题
        await nc.subscribe('orderbook-data.>', cb=message_handler)
        print("🔍 监听所有 orderbook-data.* 主题...")
        print("⏳ 等待30秒收集消息...\n")
        
        # 等待30秒
        await asyncio.sleep(30)
        
        print(f"\n📊 统计结果:")
        print(f"   总消息数: {message_count}")
        print(f"   唯一主题数: {len(received_topics)}")
        print(f"   主题列表:")
        for topic in sorted(received_topics):
            print(f"     - {topic}")
        
        await nc.close()
        
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
