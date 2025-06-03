#!/usr/bin/env python3
import asyncio
import nats
import time
import json
import os
from nats.js.api import StreamConfig, ConsumerConfig, RetentionPolicy, DiscardPolicy, StorageType

# 流配置
STREAMS_CONFIG = [
    {
        "name": "TRADES",
        "subjects": ["market.trades.*"],
        "description": "交易数据流",
        "max_age": 86400000000000,  # 24小时，以纳秒为单位
        "need_dlq": True
    },
    {
        "name": "DEPTH",
        "subjects": ["market.depth.*"],
        "description": "深度数据流",
        "max_age": 86400000000000,  # 24小时，以纳秒为单位
        "need_dlq": True
    },
    {
        "name": "FUNDING",
        "subjects": ["market.funding.*"],
        "description": "资金费率数据流",
        "max_age": 86400000000000,  # 24小时，以纳秒为单位
        "need_dlq": True
    },
    {
        "name": "OPEN_INTEREST",
        "subjects": ["market.open_interest.*"],
        "description": "未平仓合约数据流",
        "max_age": 86400000000000,  # 24小时，以纳秒为单位
        "need_dlq": True
    },
    {
        "name": "ORDERS",
        "subjects": ["market.orders.*"],
        "description": "订单数据流",
        "max_age": 86400000000000,  # 24小时，以纳秒为单位
        "need_dlq": True
    },
    {
        "name": "HEARTBEATS",
        "subjects": ["system.heartbeat.*"],
        "description": "服务心跳数据流",
        "max_age": 86400000000000,  # 24小时，以纳秒为单位
        "need_dlq": False
    },
    {
        "name": "METRICS",
        "subjects": ["system.metrics.*"],
        "description": "系统指标数据流",
        "max_age": 172800000000000,  # 48小时，以纳秒为单位
        "need_dlq": False
    },
    {
        "name": "DLQ",
        "subjects": ["deadletter.*"],
        "description": "死信队列",
        "max_age": 259200000000000,  # 72小时，以纳秒为单位
        "need_dlq": False
    }
]

# 消费者配置
CONSUMERS_CONFIG = [
    {
        "stream": "TRADES",
        "consumers": [
            {
                "name": "TRADES_ARCHIVER",
                "description": "数据归档服务消费者",
                "filter_subject": "market.trades.*",
                "deliver_policy": "all",
                "ack_policy": "explicit",
                "max_deliver": 5,
                "ack_wait": 30000000000,  # 30秒
                "max_ack_pending": 1000
            },
            {
                "name": "TRADES_INGESTION",
                "description": "数据接收服务消费者",
                "filter_subject": "market.trades.*",
                "deliver_policy": "all",
                "ack_policy": "explicit",
                "max_deliver": 5,
                "ack_wait": 30000000000,  # 30秒
                "max_ack_pending": 1000
            }
        ]
    },
    {
        "stream": "DEPTH",
        "consumers": [
            {
                "name": "DEPTH_INGESTION",
                "description": "深度数据接收服务消费者",
                "filter_subject": "market.depth.*",
                "deliver_policy": "all",
                "ack_policy": "explicit",
                "max_deliver": 3,
                "ack_wait": 15000000000,  # 15秒
                "max_ack_pending": 1000
            }
        ]
    },
    {
        "stream": "FUNDING",
        "consumers": [
            {
                "name": "FUNDING_INGESTION",
                "description": "资金费率数据接收服务消费者",
                "filter_subject": "market.funding.*",
                "deliver_policy": "all",
                "ack_policy": "explicit",
                "max_deliver": 3,
                "ack_wait": 30000000000,  # 30秒
                "max_ack_pending": 1000
            }
        ]
    },
    {
        "stream": "OPEN_INTEREST",
        "consumers": [
            {
                "name": "OI_INGESTION",
                "description": "未平仓合约数据接收服务消费者",
                "filter_subject": "market.open_interest.*",
                "deliver_policy": "all",
                "ack_policy": "explicit",
                "max_deliver": 3,
                "ack_wait": 30000000000,  # 30秒
                "max_ack_pending": 1000
            }
        ]
    }
]

# NATS服务器URL
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
MAX_RETRIES = 5

async def wait_for_nats_server(url=NATS_URL, max_attempts=10, retry_delay=1):
    """
    等待NATS服务器就绪
    """
    print("等待NATS服务就绪...")
    
    for attempt in range(1, max_attempts + 1):
        try:
            # 尝试连接NATS服务器
            nc = await nats.connect(url, connect_timeout=3)
            # 如果连接成功，关闭连接并返回
            await nc.close()
            return True
        except Exception as e:
            if attempt < max_attempts:
                # 如果连接失败，等待一段时间后重试
                await asyncio.sleep(retry_delay)
                retry_delay *= 1.5  # 指数退避
            else:
                print(f"无法连接到NATS服务器: {e}")
                return False
    
    return False

async def create_stream(js, stream_config):
    """
    创建NATS流
    """
    try:
        name = stream_config["name"]
        
        # 检查流是否已存在
        try:
            # 尝试获取流信息
            await js.stream_info(name)
            print(f"流 {name} 已存在，跳过创建")
            return True
        except nats.js.errors.NotFoundError:
            # 流不存在，准备创建
            print(f"流 {name} 不存在，准备创建")
            
            # 创建StreamConfig对象
            config = StreamConfig(
                name=name,
                subjects=stream_config["subjects"],
                description=stream_config.get("description", ""),
                retention=RetentionPolicy.LIMITS,
                max_consumers=-1,
                max_msgs_per_subject=-1,
                max_msgs=-1,
                max_bytes=-1,
                max_age=stream_config.get("max_age", 86400000000000),  # 默认24小时，纳秒
                max_msg_size=-1,
                storage=StorageType.FILE,
                discard=DiscardPolicy.OLD,
                num_replicas=1,
                duplicate_window=120000000000
            )
            
            # 创建流 - 使用as_dict方法将配置转换为字典
            try:
                await js.add_stream(**config.as_dict())
                print(f"✅ 流 {name} 创建成功")
                return True
            except Exception as e:
                print(f"❌ 创建流 {name} 出错: {e}")
                return False
                
    except Exception as e:
        print(f"❌ 处理流配置出错: {e}")
        return False

async def create_consumer(js, stream, consumer_config):
    """
    创建消费者
    """
    try:
        stream_name = stream
        consumer_name = consumer_config["name"]
        
        # 检查消费者是否已存在
        try:
            # 尝试获取消费者信息
            await js.consumer_info(stream_name, consumer_name)
            print(f"消费者 {consumer_name} 已存在，跳过创建")
            return True
        except nats.js.errors.NotFoundError:
            # 消费者不存在，准备创建
            print(f"消费者 {consumer_name} 不存在，准备创建")
            
            # 创建ConsumerConfig对象
            config = ConsumerConfig(
                durable_name=consumer_name,
                description=consumer_config.get("description", ""),
                deliver_subject=f"_INBOX.{consumer_name}",
                deliver_policy=consumer_config.get("deliver_policy", "all"),
                ack_policy=consumer_config.get("ack_policy", "explicit"),
                max_deliver=consumer_config.get("max_deliver", 3),
                filter_subject=consumer_config.get("filter_subject", ""),
                ack_wait=consumer_config.get("ack_wait", 30000000000),  # 30秒
                max_ack_pending=consumer_config.get("max_ack_pending", 1000)
            )
            
            # 创建消费者 - 使用as_dict方法将配置转换为字典
            try:
                await js.add_consumer(stream_name, **config.as_dict())
                print(f"✅ 消费者 {consumer_name} 创建成功")
                return True
            except Exception as e:
                print(f"❌ 创建消费者 {consumer_name} 出错: {e}")
                return False
                
    except Exception as e:
        print(f"❌ 处理消费者配置出错: {e}")
        return False

async def configure_dlq(js, stream_name):
    """
    为流配置死信队列
    """
    try:
        # 确保DLQ流存在
        dlq_exists = False
        try:
            await js.stream_info("DLQ")
            dlq_exists = True
        except nats.js.errors.NotFoundError:
            pass
        
        if not dlq_exists:
            print("死信队列流不存在，请先创建DLQ流")
            return False
        
        # 为流创建死信队列消费者
        consumer_name = f"{stream_name}_DLQ"
        
        # 检查死信队列消费者是否已存在
        try:
            await js.consumer_info(stream_name, consumer_name)
            print(f"死信队列消费者 {consumer_name} 已存在")
            return True
        except nats.js.errors.NotFoundError:
            # 消费者不存在，创建死信队列消费者
            config = ConsumerConfig(
                durable_name=consumer_name,
                description=f"{stream_name}流的死信队列消费者",
                filter_subject=f"market.{stream_name.lower()}.*",
                ack_policy="explicit",
                max_deliver=5,  # 最大重试5次
                ack_wait=30000000000,  # 30秒
                max_ack_pending=1000,
                deliver_policy="all"
            )
            
            # 创建消费者 - 使用as_dict方法将配置转换为字典
            try:
                await js.add_consumer(stream_name, **config.as_dict())
                print(f"✅ 死信队列消费者 {consumer_name} 创建成功")
                return True
            except Exception as e:
                print(f"❌ 创建死信队列消费者 {consumer_name} 出错: {e}")
                return False
                
    except Exception as e:
        print(f"❌ 配置死信队列出错: {e}")
        return False

async def list_streams_and_consumers():
    """
    列出所有流和消费者
    """
    try:
        # 连接NATS服务器
        nc = await nats.connect(NATS_URL)
        js = nc.jetstream()
        
        # 获取所有流
        stream_names = []
        try:
            # 获取streams列表
            streams = await js.streams_info()
            for stream in streams:
                stream_names.append(stream.config.name)
            
            print(f"\n现有流 ({len(stream_names)}):")
            for name in stream_names:
                stream_info = await js.stream_info(name)
                print(f"  - {name}: {stream_info.config.description}")
                print(f"    主题: {stream_info.config.subjects}")
                print(f"    消息数: {stream_info.state.messages}")
                
                # 获取流的消费者
                consumers = []
                try:
                    consumers_info = await js.consumers_info(name)
                    for consumer in consumers_info:
                        consumers.append(consumer.name)
                    
                    print(f"    消费者 ({len(consumers)}):")
                    for consumer_name in consumers:
                        consumer_info = await js.consumer_info(name, consumer_name)
                        print(f"      - {consumer_name}: {consumer_info.config.description}")
                        print(f"        过滤主题: {consumer_info.config.filter_subject}")
                        print(f"        投递策略: {consumer_info.config.deliver_policy}")
                except Exception as e:
                    print(f"    获取消费者列表出错: {e}")
                
                print()
        except Exception as e:
            print(f"获取流列表出错: {e}")
        
        await nc.close()
    except Exception as e:
        print(f"获取NATS信息时出错: {e}")

async def main():
    """
    主函数，配置NATS流和消费者
    """
    # 等待NATS服务器就绪
    if not await wait_for_nats_server():
        print("NATS服务器未就绪，退出")
        return
    
    print("===== 配置NATS流 =====")
    
    # 连接NATS服务器
    print(f"连接到NATS服务器 {NATS_URL}...")
    try:
        nc = await nats.connect(NATS_URL)
        js = nc.jetstream()
        print("✅ 连接到NATS服务器成功")
    except Exception as e:
        print(f"❌ 连接到NATS服务器失败: {e}")
        return
    
    # 创建流
    for stream_config in STREAMS_CONFIG:
        await create_stream(js, stream_config)
    
    print("===== 配置消费者及死信队列 =====")
    
    # 创建消费者
    for consumer_group in CONSUMERS_CONFIG:
        stream = consumer_group["stream"]
        consumers = consumer_group["consumers"]
        
        for consumer_config in consumers:
            try:
                await create_consumer(js, stream, consumer_config)
            except Exception as e:
                print(f"❌ 配置消费者出错: {e}")
        
        # 配置死信队列
        for stream_config in STREAMS_CONFIG:
            if stream_config["name"] == stream and stream_config.get("need_dlq", False):
                await configure_dlq(js, stream)
    
    await nc.close()
    print("===== NATS流和消费者配置完成 =====\n")
    
    # 列出当前状态
    print("===== 当前NATS流和消费者状态 =====")
    for retry in range(MAX_RETRIES):
        try:
            await list_streams_and_consumers()
            break
        except Exception as e:
            if retry < MAX_RETRIES - 1:
                print(f"NATS流创建失败（尝试 {retry+1}/{MAX_RETRIES}）: {e}")
                wait_time = (retry + 1) * 3
                print(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
                await main()  # 递归重试
            else:
                print(f"达到最大尝试次数，流创建失败。")
                break

if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(list_streams_and_consumers()) 