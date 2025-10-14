#!/usr/bin/env python3
"""
简单的数据测试脚本
"""

import asyncio
import json
import time
from datetime import datetime
import nats

async def test_data():
    print("🔍 开始简单数据测试...")
    
    try:
        # 连接到 NATS
        nc = await nats.connect("nats://localhost:4222")
        js = nc.jetstream()
        print("✅ 已连接到 NATS JetStream")
        
        # 测试几个主题
        subjects_to_test = [
            "funding_rate.okx_derivatives.perpetual.BTC-USDT",
            "open_interest.okx_derivatives.perpetual.BTC-USDT",
            "orderbook.okx_spot.spot.BTC-USDT",
            "trade.okx_spot.spot.BTC-USDT"
        ]
        
        for subject in subjects_to_test:
            print(f"\n=== 测试主题: {subject} ===")
            try:
                durable = f"test_{subject.replace('.', '_').replace('-', '_')}"
                sub = await js.subscribe(subject, durable=durable, stream="MARKET_DATA")
                
                # 获取一条消息
                msg = await sub.next_msg(timeout=5.0)
                data = json.loads(msg.data.decode())
                
                print(f"✅ 收到消息，大小: {len(msg.data)} 字节")
                print(f"📊 数据字段: {list(data.keys())}")
                
                # 检查关键字段
                if 'timestamp' in data:
                    print(f"⏰ 时间戳: {data['timestamp']}")
                    print(f"⏰ 时间戳类型: {type(data['timestamp'])}")
                    
                    # 尝试解析时间戳
                    try:
                        if isinstance(data['timestamp'], str) and 'T' in data['timestamp']:
                            dt = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
                            current_time = datetime.now(dt.tzinfo)
                            latency = (current_time - dt).total_seconds()
                            print(f"⚡ 延迟: {latency:.3f}秒")
                        else:
                            print("⚠️ 时间戳格式不是ISO格式")
                    except Exception as e:
                        print(f"❌ 时间戳解析失败: {e}")
                
                if 'data_type' in data:
                    print(f"📝 数据类型: {data['data_type']}")
                    
                if 'exchange' in data:
                    print(f"🏢 交易所: {data['exchange']}")
                    
                if 'symbol' in data:
                    print(f"💱 交易对: {data['symbol']}")
                
                await sub.drain()
                
            except Exception as e:
                print(f"❌ 测试失败: {e}")
        
        await nc.close()
        print("\n✅ 测试完成")
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_data())
