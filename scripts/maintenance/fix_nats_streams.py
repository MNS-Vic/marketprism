#!/usr/bin/env python3
import asyncio
import nats
import json
import os
import time

# 简化的流配置，移除可能导致JSON格式问题的字段
STREAMS_CONFIG = [
    {
        "name": "MARKET_TRADES",
        "subjects": ["market.trades.>"],
        "description": "交易数据流"
    },
    {
        "name": "MARKET_DEPTH",
        "subjects": ["market.depth.>"],
        "description": "深度数据流"
    },
    {
        "name": "MARKET_FUNDING",
        "subjects": ["market.funding.>"],
        "description": "资金费率数据流"
    },
    {
        "name": "MARKET_ORDERS",
        "subjects": ["market.orders.>"],
        "description": "订单数据流"
    },
    {
        "name": "SYSTEM",
        "subjects": ["system.>"],
        "description": "系统消息流"
    }
]

async def create_stream(nc, name, subjects, description):
    """使用最简单的配置创建流"""
    print(f"尝试创建流: {name}")
    
    js = nc.jetstream()
    
    # 检查流是否已存在
    try:
        await js.stream_info(name)
        print(f"✅ 流 {name} 已存在")
        return True
    except Exception:
        print(f"流 {name} 不存在，准备创建")
    
    try:
        # 使用最简化的参数避免JSON问题
        stream = await js.add_stream(name=name, subjects=subjects)
        print(f"✅ 流 {name} 创建成功!")
        return True
    except Exception as e:
        print(f"❌ 创建流 {name} 失败: {e}")
        
        # 尝试直接用API创建
        try:
            print("尝试使用原始API创建流...")
            
            # 创建最简化的配置
            config = {
                "name": name,
                "subjects": subjects if isinstance(subjects, list) else [subjects]
            }
            
            # 使用pubsub命令直接创建流
            msg = await nc.request(
                "STREAM.CREATE."+name, 
                json.dumps(config).encode()
            )
            response = json.loads(msg.data.decode())
            
            if response.get("success") is True:
                print(f"✅ 使用API创建流 {name} 成功!")
                return True
            else:
                print(f"❌ API创建失败: {response}")
                return False
        except Exception as api_err:
            print(f"❌ API创建也失败: {api_err}")
            return False

async def test_and_fix_streams():
    # 连接到NATS
    try:
        nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
        print(f"连接到NATS服务器: {nats_url}")
        nc = await nats.connect(nats_url)
        
        success_count = 0
        total_streams = len(STREAMS_CONFIG)
        
        # 尝试创建每个流
        for stream_config in STREAMS_CONFIG:
            if await create_stream(
                nc,
                stream_config["name"],
                stream_config["subjects"],
                stream_config.get("description", "")
            ):
                success_count += 1
        
        # 测试发布消息
        js = nc.jetstream()
        
        print("\n测试发布消息...")
        
        test_messages = [
            ("market.trades.test", {"symbol": "BTCUSDT", "price": 50000}),
            ("system.status", {"status": "ok", "timestamp": time.time()})
        ]
        
        msg_success = 0
        for subject, data in test_messages:
            try:
                ack = await js.publish(subject, json.dumps(data).encode())
                print(f"✅ 消息发布到 {subject} 成功: {ack.stream}")
                msg_success += 1
            except Exception as e:
                print(f"❌ 消息发布到 {subject} 失败: {e}")
        
        # 如果流创建失败，但消息发布成功，可能是默认流已创建
        if success_count == 0 and msg_success > 0:
            print("\n⚠️ 流可能已被自动创建。尝试列出所有流...")
            try:
                streams = await js.streams_info()
                print(f"发现 {len(streams)} 个流:")
                for stream in streams:
                    print(f"  - {stream.config.name}")
                    print(f"    主题: {stream.config.subjects}")
            except Exception as e:
                print(f"❌ 无法列出流: {e}")
        
        await nc.close()
        
        print(f"\n结果: {success_count}/{total_streams} 个流创建成功，{msg_success}/{len(test_messages)} 条消息发布成功")
        
    except Exception as e:
        print(f"❌ 执行过程中出错: {e}")

if __name__ == "__main__":
    print("=== 修复 NATS 流配置 ===")
    asyncio.run(test_and_fix_streams())