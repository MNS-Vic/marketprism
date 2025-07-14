#!/usr/bin/env python3
"""
NATS订阅测试脚本 - 验证数据标准化
"""

import asyncio
import json
import sys
from datetime import datetime
import nats
from nats.errors import TimeoutError

async def test_nats_subscription():
    """测试NATS订阅并验证数据格式"""
    try:
        # 连接到NATS服务器
        nc = await nats.connect("nats://localhost:4222")
        print(f"✅ 成功连接到NATS服务器")
        
        message_count = 0
        max_messages = 10
        
        async def message_handler(msg):
            nonlocal message_count
            message_count += 1
            
            try:
                # 解析消息
                data = json.loads(msg.data.decode())
                
                print(f"\n📨 消息 #{message_count}")
                print(f"🔗 主题: {msg.subject}")
                print(f"📊 交易所: {data.get('exchange', 'N/A')}")
                print(f"💱 交易对: {data.get('symbol', 'N/A')}")
                print(f"🏪 市场类型: {data.get('market_type', 'N/A')}")
                print(f"📈 买单档位: {len(data.get('bids', []))}")
                print(f"📉 卖单档位: {len(data.get('asks', []))}")
                
                # 验证数据标准化
                symbol = data.get('symbol', '')
                if symbol:
                    if '-' in symbol:
                        print(f"✅ 符号格式标准化正确: {symbol}")
                    else:
                        print(f"❌ 符号格式未标准化: {symbol}")
                
                # 显示前3个买卖档位
                bids = data.get('bids', [])
                asks = data.get('asks', [])
                
                if bids:
                    print(f"📈 前3个买单: {bids[:3]}")
                if asks:
                    print(f"📉 前3个卖单: {asks[:3]}")
                
                print("-" * 50)
                
                if message_count >= max_messages:
                    print(f"✅ 已收到 {max_messages} 条消息，测试完成")
                    await nc.close()
                    
            except Exception as e:
                print(f"❌ 解析消息失败: {e}")
                print(f"原始数据: {msg.data.decode()[:200]}...")
        
        # 订阅所有orderbook数据
        await nc.subscribe("orderbook-data.>", cb=message_handler)
        print(f"🔍 开始监听 orderbook-data.> 主题...")
        
        # 等待消息
        timeout_seconds = 60
        start_time = datetime.now()
        
        while message_count < max_messages:
            await asyncio.sleep(1)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if elapsed > timeout_seconds:
                print(f"⏰ 超时 ({timeout_seconds}秒)，收到 {message_count} 条消息")
                break
        
        await nc.close()
        print(f"🔚 NATS连接已关闭")
        
    except Exception as e:
        print(f"❌ NATS测试失败: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 启动NATS订阅测试...")
    result = asyncio.run(test_nats_subscription())
    sys.exit(0 if result else 1)
