#!/usr/bin/env python3
"""
使用低级API创建基本的NATS流
"""
import asyncio
import os
import json

import nats

# NATS服务器URL
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")

async def create_basic_streams():
    """创建基本流"""
    try:
        print(f"连接到NATS服务器 {NATS_URL}...")
        nc = await nats.connect(NATS_URL)
        
        # 获取JetStream上下文
        js = nc.jetstream()
        print("✓ 连接到NATS服务器成功")
        
        # 使用低级API创建流
        # 创建交易数据流
        try:
            # 发送API请求创建流
            req = {"name": "MARKET_DATA", "subjects": ["binance.>", "market.>"], "retention": "limits", 
                   "max_age": 86400000000000, "storage": "file", "num_replicas": 1}
            
            resp = await nc.request("$JS.API.STREAM.CREATE.MARKET_DATA", json.dumps(req).encode())
            result = json.loads(resp.data.decode())
            if "error" in result:
                print(f"× 创建MARKET_DATA流失败: {result['error']['description']}")
            else:
                print("✓ 创建MARKET_DATA流成功")
        except Exception as e:
            print(f"× 创建MARKET_DATA流失败: {e}")
        
        # 查看所有流
        resp = await nc.request("$JS.API.STREAM.LIST", b'')
        info = json.loads(resp.data.decode())
        print("\n当前流:")
        if "streams" in info:
            for stream in info["streams"]:
                print(f" - {stream['name']}: {stream.get('subjects', [])}")
        
        await nc.close()
        print("\n✓ 完成")
        
    except Exception as e:
        print(f"操作失败: {e}")

if __name__ == "__main__":
    asyncio.run(create_basic_streams())