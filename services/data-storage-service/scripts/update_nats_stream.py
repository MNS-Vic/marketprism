#!/usr/bin/env python3
"""
更新NATS JetStream配置，添加LSR数据类型支持
"""

import asyncio
import nats
from nats.js import JetStreamContext
from nats.js.api import StreamConfig, RetentionPolicy, DiscardPolicy, StorageType


async def update_stream_config():
    """更新stream配置，添加LSR subjects"""
    try:
        print("🔧 开始更新NATS stream配置")
        
        # 连接NATS
        nc = await nats.connect("nats://localhost:4222")
        js = nc.jetstream()
        
        # 获取当前stream信息
        try:
            current_stream = await js.stream_info("MARKET_DATA")
            print(f"✅ 找到现有stream: MARKET_DATA")
            print(f"   当前subjects: {current_stream.config.subjects}")
        except Exception as e:
            print(f"❌ 获取stream信息失败: {e}")
            return
        
        # 定义新的subjects列表（包含LSR）
        new_subjects = [
            "orderbook-data.>",
            "trade-data.>", 
            "funding-rate.>",
            "funding-rate-data.>",  # 兼容两种格式
            "open-interest.>",
            "open-interest-data.>",  # 兼容两种格式
            "liquidation-data.>",
            "kline-data.>",
            "volatility_index-data.>",
            # 新增LSR相关subjects
            "lsr-top-position-data.>",
            "lsr-all-account-data.>",
            "lsr-data.>",  # 通用LSR格式
        ]
        
        print(f"\n📝 新的subjects列表:")
        for i, subject in enumerate(new_subjects, 1):
            print(f"   {i:2d}. {subject}")
        
        # 创建新的stream配置
        new_config = StreamConfig(
            name="MARKET_DATA",
            subjects=new_subjects,
            retention=RetentionPolicy.LIMITS,
            max_consumers=50,
            max_msgs=5000000,
            max_bytes=2147483648,
            max_age=172800,  # 48小时
            discard=DiscardPolicy.OLD,
            storage=StorageType.FILE,
            num_replicas=1,
            duplicate_window=120,
        )
        
        # 更新stream配置
        print(f"\n🔄 更新stream配置...")
        updated_stream = await js.update_stream(new_config)
        
        print(f"✅ Stream配置更新成功!")
        print(f"   更新后subjects数量: {len(updated_stream.config.subjects)}")
        print(f"   新增subjects:")
        
        # 显示新增的subjects
        old_subjects = set(current_stream.config.subjects)
        new_subjects_set = set(updated_stream.config.subjects)
        added_subjects = new_subjects_set - old_subjects
        
        for subject in added_subjects:
            print(f"     + {subject}")
        
        # 关闭连接
        await nc.close()
        print("✅ NATS stream配置更新完成")
        
    except Exception as e:
        print(f"❌ 更新失败: {e}")


if __name__ == "__main__":
    asyncio.run(update_stream_config())
