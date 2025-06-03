#!/usr/bin/env python3
"""
原生方式创建NATS流
"""
import asyncio
import os
import sys
import nats

# NATS服务器URL
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")

async def create_streams():
    """创建基本流"""
    try:
        print(f"连接到NATS服务器 {NATS_URL}...")
        nc = await nats.connect(NATS_URL)
        js = nc.jetstream()
        print("✓ 连接到NATS服务器成功")
        
        # 创建交易数据流
        trade_config = {
            "name": "MARKET_TRADES",
            "subjects": ["market.trades.*"],
            "retention": "limits",
            "max_age": 86400000000000,  # 24小时（纳秒）
            "storage": "file",
            "discard": "old"
        }
        
        try:
            await js.add_stream(**trade_config)
            print("✓ 创建MARKET_TRADES流成功")
        except Exception as e:
            print(f"× 创建MARKET_TRADES流失败: {e}")
        
        # 创建深度数据流
        depth_config = {
            "name": "MARKET_DEPTH",
            "subjects": ["market.depth.*"],
            "retention": "limits",
            "max_age": 86400000000000,  # 24小时（纳秒）
            "storage": "file",
            "discard": "old"
        }
        
        try:
            await js.add_stream(**depth_config)
            print("✓ 创建MARKET_DEPTH流成功")
        except Exception as e:
            print(f"× 创建MARKET_DEPTH流失败: {e}")
        
        # 查看所有流
        streams = await js.streams_info()
        print("\n当前流:")
        for stream in streams:
            print(f" - {stream.config.name}: {stream.config.subjects}")
        
        await nc.close()
        print("\n✓ 完成")
    except Exception as e:
        print(f"× 操作失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(create_streams())
    sys.exit(exit_code)