#!/usr/bin/env python3
"""
重置NATS流
"""
import asyncio
import os
import nats
import sys

# NATS服务器URL
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")

async def delete_all_streams():
    """删除所有现有流"""
    try:
        # 连接到NATS服务器
        print(f"连接到NATS服务器 {NATS_URL}...")
        nc = await nats.connect(NATS_URL)
        js = nc.jetstream()
        print("✅ 连接到NATS服务器成功")
        
        # 获取所有流
        streams_info = await js.streams_info()
        stream_names = [stream.config.name for stream in streams_info]
        print(f"发现 {len(stream_names)} 个流: {', '.join(stream_names)}")
        
        if not stream_names:
            print("没有流需要删除")
            await nc.close()
            return True
        
        # 询问确认
        if "YES" in sys.argv:
            confirm = "y"
        else:
            confirm = input(f"确定要删除所有 {len(stream_names)} 个流吗? [y/N]: ")
        
        if confirm.lower() != 'y':
            print("操作已取消")
            await nc.close()
            return False
        
        # 删除所有流
        for name in stream_names:
            try:
                await js.delete_stream(name)
                print(f"✅ 流 {name} 已删除")
            except Exception as e:
                print(f"❌ 删除流 {name} 出错: {e}")
        
        await nc.close()
        return True
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        return False

if __name__ == "__main__":
    if "help" in sys.argv or "-h" in sys.argv:
        print("用法: python reset_nats_streams.py [YES]")
        print("参数:")
        print("  YES    跳过确认提示，直接删除所有流")
        sys.exit(0)
    
    asyncio.run(delete_all_streams())