#!/usr/bin/env python3
"""
创建一个简单的NATS流作为测试
"""
import asyncio
import os
import nats

# NATS服务器URL
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")

async def create_test_stream():
    """创建测试流"""
    try:
        print(f"连接到NATS服务器 {NATS_URL}...")
        nc = await nats.connect(NATS_URL)
        js = nc.jetstream()
        print("✓ 连接到NATS服务器成功")
        
        # 创建简单的流
        stream_config = {
            "name": "TEST_STREAM",
            "subjects": ["test.>"],
            "retention": "limits",
            "max_age": 86400000000000  # 24小时（纳秒）
        }
        
        # 创建流
        try:
            stream = await js.add_stream(**stream_config)
            print(f"✓ 创建测试流成功: {stream.config.name}")
        except Exception as e:
            print(f"× 创建测试流失败: {e}")
        
        await nc.close()
        print("完成")
    except Exception as e:
        print(f"操作失败: {e}")

if __name__ == "__main__":
    asyncio.run(create_test_stream())