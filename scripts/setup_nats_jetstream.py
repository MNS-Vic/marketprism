#!/usr/bin/env python3
"""
NATS JetStream配置脚本
"""
import asyncio
import nats
from nats.js import JetStreamContext
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup_jetstream():
    """配置NATS JetStream"""
    try:
        # 连接到NATS服务器
        nc = await nats.connect("nats://localhost:4222")
        logger.info("✅ 成功连接到NATS服务器")
        
        # 获取JetStream上下文
        js = nc.jetstream()
        logger.info("✅ 获取JetStream上下文成功")
        
        # 创建MARKET_DATA流
        try:
            from nats.js.api import StreamConfig, RetentionPolicy, StorageType
            
            stream_config = StreamConfig(
                name="MARKET_DATA",
                subjects=["market.>", "binance.>", "okx.>"],
                retention=RetentionPolicy.LIMITS,
                max_msgs=1000000,
                max_bytes=1073741824,  # 1GB
                max_age=86400,  # 24 hours
                max_consumers=10,
                num_replicas=1,
                storage=StorageType.FILE
            )
            
            await js.add_stream(stream_config)
            logger.info("✅ 创建MARKET_DATA流成功")
            
        except Exception as e:
            if "stream name already in use" in str(e).lower():
                logger.info("ℹ️ MARKET_DATA流已存在")
            else:
                logger.error(f"❌ 创建MARKET_DATA流失败: {e}")
                
        # 创建TRADES流
        try:
            trades_config = StreamConfig(
                name="TRADES",
                subjects=["trades.>"],
                retention=RetentionPolicy.LIMITS,
                max_msgs=500000,
                max_bytes=536870912,  # 512MB
                max_age=43200,  # 12 hours
                max_consumers=5,
                num_replicas=1,
                storage=StorageType.FILE
            )
            
            await js.add_stream(trades_config)
            logger.info("✅ 创建TRADES流成功")
            
        except Exception as e:
            if "stream name already in use" in str(e).lower():
                logger.info("ℹ️ TRADES流已存在")
            else:
                logger.error(f"❌ 创建TRADES流失败: {e}")
        
        # 列出所有流
        try:
            streams_info = await js.streams_info()
            streams = []
            for stream in streams_info:
                streams.append(stream.config.name)
                logger.info(f"📊 流: {stream.config.name}, 主题: {stream.config.subjects}")
                
            logger.info(f"✅ JetStream配置完成，共有 {len(streams)} 个流")
        except Exception as e:
            logger.warning(f"⚠️ 无法列出流信息: {e}")
            logger.info("✅ JetStream配置完成")
        
        # 关闭连接
        await nc.close()
        
    except Exception as e:
        logger.error(f"❌ JetStream配置失败: {e}")
        return False
        
    return True

async def test_jetstream():
    """测试JetStream功能"""
    try:
        # 连接到NATS服务器
        nc = await nats.connect("nats://localhost:4222")
        js = nc.jetstream()
        
        # 发布测试消息
        test_subject = "market.test"
        test_message = b"Hello JetStream!"
        
        ack = await js.publish(test_subject, test_message)
        logger.info(f"✅ 发布测试消息成功: {ack.seq}")
        
        # 创建消费者并接收消息
        consumer = await js.pull_subscribe(test_subject, "test-consumer")
        
        # 拉取消息
        msgs = await consumer.fetch(1, timeout=5)
        if msgs:
            msg = msgs[0]
            logger.info(f"✅ 接收测试消息成功: {msg.data.decode()}")
            await msg.ack()
        else:
            logger.warning("⚠️ 未接收到测试消息")
            
        await nc.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ JetStream测试失败: {e}")
        return False

async def main():
    """主函数"""
    logger.info("🚀 开始配置NATS JetStream...")
    
    # 配置JetStream
    if await setup_jetstream():
        logger.info("✅ JetStream配置成功")
        
        # 测试JetStream
        if await test_jetstream():
            logger.info("✅ JetStream测试成功")
        else:
            logger.error("❌ JetStream测试失败")
    else:
        logger.error("❌ JetStream配置失败")

if __name__ == "__main__":
    asyncio.run(main())