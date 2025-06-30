#!/usr/bin/env python3
"""
简化的NATS连接测试
用于诊断task-worker的NATS连接问题
"""

import asyncio
import logging
import nats
import json
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_nats_connection():
    """测试基本NATS连接"""
    print("🔍 测试基本NATS连接")
    print("=" * 30)
    
    try:
        # 连接到NATS
        nc = await nats.connect(
            servers=["nats://nats:4222"],
            name="simple-test-client",
            connect_timeout=10,
            max_reconnect_attempts=3,
            reconnect_time_wait=2
        )
        
        print("✅ NATS连接成功")
        
        # 测试基本发布/订阅
        received_messages = []
        
        async def message_handler(msg):
            data = msg.data.decode()
            received_messages.append(data)
            print(f"收到消息: {data}")
            await msg.respond(b"ACK")
        
        # 订阅测试主题
        await nc.subscribe("test.simple", cb=message_handler)
        print("✅ 订阅测试主题成功")
        
        # 发布测试消息
        test_message = json.dumps({
            "test": "simple_nats_test",
            "timestamp": datetime.now().isoformat()
        })
        
        response = await nc.request("test.simple", test_message.encode(), timeout=5)
        print(f"✅ 发布消息成功，收到响应: {response.data.decode()}")
        
        # 等待消息处理
        await asyncio.sleep(2)
        
        # 关闭连接
        await nc.close()
        print("✅ NATS连接已关闭")
        
        return True
        
    except Exception as e:
        print(f"❌ NATS连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_jetstream_connection():
    """测试JetStream连接"""
    print("\n🔍 测试JetStream连接")
    print("=" * 30)
    
    try:
        # 连接到NATS
        nc = await nats.connect(
            servers=["nats://nats:4222"],
            name="jetstream-test-client",
            connect_timeout=10,
            max_reconnect_attempts=3,
            reconnect_time_wait=2
        )
        
        print("✅ NATS连接成功")
        
        # 获取JetStream上下文
        js = nc.jetstream()
        print("✅ JetStream上下文获取成功")
        
        # 检查现有流
        try:
            streams = await js.streams_info()
            print(f"✅ 现有流数量: {len(streams)}")
            for stream in streams:
                print(f"   流名称: {stream.config.name}, 主题: {stream.config.subjects}")
        except Exception as e:
            print(f"⚠️ 获取流信息失败: {e}")
        
        # 尝试创建简单的测试流
        try:
            await js.add_stream(name="TEST_SIMPLE", subjects=["test.simple.>"])
            print("✅ 测试流创建成功")
        except Exception as e:
            if "stream name already in use" in str(e).lower():
                print("✅ 测试流已存在")
            else:
                print(f"⚠️ 测试流创建失败: {e}")
        
        # 关闭连接
        await nc.close()
        print("✅ JetStream连接已关闭")
        
        return True
        
    except Exception as e:
        print(f"❌ JetStream连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_consumer_creation():
    """测试消费者创建"""
    print("\n🔍 测试消费者创建")
    print("=" * 30)
    
    try:
        # 连接到NATS
        nc = await nats.connect(
            servers=["nats://nats:4222"],
            name="consumer-test-client",
            connect_timeout=10,
            max_reconnect_attempts=3,
            reconnect_time_wait=2
        )
        
        print("✅ NATS连接成功")
        
        # 获取JetStream上下文
        js = nc.jetstream()
        print("✅ JetStream上下文获取成功")
        
        # 确保测试流存在
        try:
            await js.add_stream(name="TEST_CONSUMER", subjects=["test.consumer.>"])
            print("✅ 测试流创建成功")
        except Exception as e:
            if "stream name already in use" in str(e).lower():
                print("✅ 测试流已存在")
            else:
                print(f"⚠️ 测试流创建失败: {e}")
        
        # 创建简单的消费者
        from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy
        
        consumer_config = ConsumerConfig(
            durable_name="test-consumer",
            deliver_policy=DeliverPolicy.NEW,
            ack_policy=AckPolicy.EXPLICIT,
            max_deliver=3,
            ack_wait=60,  # 1分钟
            max_ack_pending=1
        )
        
        async def simple_handler(msg):
            print(f"收到JetStream消息: {msg.data.decode()}")
            await msg.ack()
        
        # 使用较短的超时时间
        subscription = await asyncio.wait_for(
            js.subscribe(
                subject="test.consumer.simple",
                stream="TEST_CONSUMER",
                config=consumer_config,
                cb=simple_handler
            ),
            timeout=10.0  # 10秒超时
        )
        
        print("✅ 消费者创建成功")
        
        # 发布测试消息
        test_message = json.dumps({
            "test": "consumer_test",
            "timestamp": datetime.now().isoformat()
        })
        
        ack = await js.publish(
            "test.consumer.simple",
            test_message.encode()
        )
        print(f"✅ 消息发布成功，序列号: {ack.seq}")
        
        # 等待消息处理
        await asyncio.sleep(3)
        
        # 取消订阅
        await subscription.unsubscribe()
        print("✅ 订阅已取消")
        
        # 关闭连接
        await nc.close()
        print("✅ 连接已关闭")
        
        return True
        
    except asyncio.TimeoutError:
        print("❌ 消费者创建超时")
        return False
    except Exception as e:
        print(f"❌ 消费者创建测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("🚀 NATS连接诊断测试")
    print("=" * 50)
    
    # 测试1: 基本NATS连接
    basic_success = await test_basic_nats_connection()
    
    # 测试2: JetStream连接
    jetstream_success = await test_jetstream_connection()
    
    # 测试3: 消费者创建
    consumer_success = await test_consumer_creation()
    
    print("\n" + "=" * 50)
    print("📋 测试结果总结:")
    print(f"   基本NATS连接: {'✅ 成功' if basic_success else '❌ 失败'}")
    print(f"   JetStream连接: {'✅ 成功' if jetstream_success else '❌ 失败'}")
    print(f"   消费者创建: {'✅ 成功' if consumer_success else '❌ 失败'}")
    
    if all([basic_success, jetstream_success, consumer_success]):
        print("\n🎉 所有测试通过！NATS连接正常")
        return True
    else:
        print("\n⚠️ 部分测试失败，需要进一步诊断")
        return False


if __name__ == "__main__":
    asyncio.run(main())
