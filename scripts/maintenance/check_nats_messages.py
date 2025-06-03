#!/usr/bin/env python3
"""
检查NATS中的市场数据消息
"""
import asyncio
import json
import time
import os
from collections import defaultdict
import nats
from nats.js.api import StreamConfig

async def check_messages():
    # 连接到NATS
    nats_url = os.environ.get("NATS_URL", "nats://localhost:4222")
    print(f"连接到NATS服务器：{nats_url}")
    
    nc = await nats.connect(nats_url)
    js = nc.jetstream()
    
    # 获取MARKET_DATA流
    try:
        stream_info = await js.stream_info("MARKET_DATA")
        print(f"MARKET_DATA流状态：")
        print(f"  消息总数：{stream_info.state.messages}")
        print(f"  消息字节数：{stream_info.state.bytes}")
        print(f"  主题：{stream_info.config.subjects}")
        
        # 创建计数器
        message_counts = defaultdict(int)
        subject_counts = defaultdict(int)
        
        # 获取消息样本
        print("\n获取消息样本...")
        
        # 创建消费者
        consumer_config = nats.js.api.ConsumerConfig(
            durable_name="sample_consumer",
            ack_policy=nats.js.api.AckPolicy.NONE,
            deliver_policy=nats.js.api.DeliverPolicy.LAST,
            max_deliver=1,
            filter_subject="market.>",
            max_ack_pending=100,
        )
        
        consumer = await js.add_consumer("MARKET_DATA", consumer_config)
        
        # 使用拉取方式获取消息
        sub = await js.pull_subscribe("market.>", "sample_consumer")
        
        # 获取消息样本
        max_samples = 100
        total_processed = 0
        
        try:
            msgs = await sub.fetch(10, timeout=5)
            for msg in msgs:
                try:
                    subject = msg.subject
                    subject_parts = subject.split('.')
                    
                    if len(subject_parts) >= 3:
                        data_type = subject_parts[1]
                        symbol = subject_parts[2]
                        
                        subject_counts[subject] += 1
                        message_counts[data_type] += 1
                        
                        total_processed += 1
                        
                        # 打印第一条消息的内容
                        if total_processed <= 3:
                            try:
                                data = json.loads(msg.data.decode())
                                print(f"\n样本消息 {total_processed}:")
                                print(f"  主题: {subject}")
                                print(f"  数据类型: {data_type}")
                                print(f"  交易对: {symbol}")
                                print(f"  时间戳: {data.get('timestamp', 'N/A')}")
                                print(f"  内容: {json.dumps(data, indent=2)[:200]}...")
                            except json.JSONDecodeError:
                                print(f"  无法解码JSON: {msg.data.decode()[:50]}...")
                        
                        # 限制样本数量
                        if total_processed >= max_samples:
                            break
                    
                except Exception as e:
                    print(f"处理消息时出错: {e}")
                    
            # 继续获取更多样本，直到达到限制
            if total_processed < max_samples:
                try:
                    more_msgs = await sub.fetch(min(max_samples - total_processed, 10), timeout=1)
                    for msg in more_msgs:
                        subject = msg.subject
                        subject_parts = subject.split('.')
                        
                        if len(subject_parts) >= 3:
                            data_type = subject_parts[1]
                            
                            subject_counts[subject] += 1
                            message_counts[data_type] += 1
                            
                            total_processed += 1
                except Exception as e:
                    print(f"获取更多消息时出错: {e}")
                
        except Exception as e:
            print(f"获取消息时出错: {e}")
        
        # 打印统计信息
        print("\n消息类型统计:")
        for data_type, count in message_counts.items():
            print(f"  {data_type}: {count} 条消息")
        
        print("\n主题统计 (前10个):")
        for subject, count in sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {subject}: {count} 条消息")
        
        # 删除临时消费者
        try:
            await js.delete_consumer("MARKET_DATA", "sample_consumer")
        except Exception as e:
            print(f"删除消费者时出错: {e}")
        
    except Exception as e:
        print(f"检查MARKET_DATA流时出错: {e}")
    
    # 关闭连接
    await nc.close()

if __name__ == "__main__":
    asyncio.run(check_messages()) 