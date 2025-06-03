#!/usr/bin/env python3
import asyncio
import nats
import json

async def main():
    # 连接到NATS服务器
    try:
        nc = await nats.connect("nats://localhost:4222")
        js = nc.jetstream()
        
        # 获取所有流
        streams_info = await js.streams_info()
        
        # 打印流信息
        print("===== NATS流信息 =====")
        for stream in streams_info:
            print(f"流名称: {stream.config.name}")
            print(f"    主题: {stream.config.subjects}")
            print(f"    消息数: {stream.state.messages}")
            print()
            
            # 尝试获取消费者信息
            try:
                consumers = await js.consumers_info(stream.config.name)
                if consumers:
                    print(f"    消费者列表:")
                    for consumer in consumers:
                        print(f"      - {consumer.name}: {consumer.config.description}")
                    print()
            except Exception as e:
                print(f"    获取消费者列表失败: {e}")
                print()
        
    except Exception as e:
        print(f"连接NATS或获取流信息失败: {e}")
    finally:
        await nc.close()

if __name__ == "__main__":
    asyncio.run(main())