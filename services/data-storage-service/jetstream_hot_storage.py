#!/usr/bin/env python3
"""
MarketPrism 纯JetStream热端存储服务
基于A/B测试结果，完全迁移到JetStream架构，移除Core NATS回退机制
"""
import asyncio
import json
import time
import traceback
from typing import Dict, Any, Optional
import nats
from nats.js.api import ConsumerConfig, DeliverPolicy, AckPolicy
import os
import sys

class JetStreamHotStorage:
    """纯JetStream热端存储服务"""
    
    def __init__(self):
        self.nats_client = None
        self.jetstream = None
        self.subscriptions = {}
        self.is_running = False
        self.stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "last_message_time": 0,
            "last_error_time": 0
        }
        
        # 数据类型到流的映射
        self.data_type_to_stream = {
            "orderbook": "ORDERBOOK_SNAP",
            "trade": "MARKET_DATA",
            "funding_rate": "MARKET_DATA",
            "open_interest": "MARKET_DATA",
            "liquidation": "MARKET_DATA",
            "lsr_top_position": "MARKET_DATA",
            "lsr_all_account": "MARKET_DATA",
            "volatility_index": "MARKET_DATA"
        }
        
        # 主题映射
        self.subject_mapping = {
            "funding_rate": "funding_rate.>",
            "open_interest": "open_interest.>",
            "lsr_top_position": "lsr_top_position.>",
            "lsr_all_account": "lsr_all_account.>",
            "orderbook": "orderbook.>",
            "trade": "trade.>",
            "liquidation": "liquidation.>",
            "volatility_index": "volatility_index.>"
        }

    async def connect(self):
        """连接NATS JetStream"""
        nats_url = os.getenv("NATS_URL") or os.getenv("MARKETPRISM_NATS_URL") or "nats://localhost:4222"
        print(f"连接NATS: {nats_url}")
        
        self.nats_client = await nats.connect(servers=[nats_url])
        self.jetstream = self.nats_client.jetstream()
        print("✅ NATS JetStream连接成功")

    async def setup_subscriptions(self):
        """设置JetStream订阅"""
        print("=== 设置JetStream订阅 ===")
        
        data_types = ["orderbook", "trade", "funding_rate", "open_interest",
                     "liquidation", "lsr_top_position", "lsr_all_account", "volatility_index"]
        
        for data_type in data_types:
            try:
                await self._subscribe_to_data_type(data_type)
            except Exception as e:
                print(f"❌ 订阅 {data_type} 失败: {e}")
                print(traceback.format_exc())
                # 继续处理其他数据类型
                continue
        
        print(f"✅ JetStream订阅设置完成，成功订阅数量: {len(self.subscriptions)}")

    async def _subscribe_to_data_type(self, data_type: str):
        """订阅特定数据类型 - 纯JetStream模式"""
        # 获取主题模式和流名称
        subject_pattern = self.subject_mapping.get(data_type, f"{data_type}.>")
        stream_name = self.data_type_to_stream.get(data_type, "MARKET_DATA")
        
        print(f"订阅 {data_type}: {subject_pattern} -> {stream_name}")
        
        # 等待流可用
        for attempt in range(10):
            try:
                await self.jetstream._jsm.stream_info(stream_name)
                print(f"✅ 流 {stream_name} 可用")
                break
            except Exception:
                print(f"⏳ 等待流 {stream_name} 可用... (尝试 {attempt+1}/10)")
                await asyncio.sleep(2)
        else:
            raise Exception(f"流 {stream_name} 在20秒内未就绪")

        # 创建消费者
        durable_name = f"simple_hot_storage_realtime_{data_type}"
        
        # 删除旧消费者（如果存在）
        try:
            await self.jetstream._jsm.delete_consumer(stream_name, durable_name)
            print(f"删除旧消费者: {durable_name}")
        except Exception:
            pass

        # 创建新消费者
        consumer_config = ConsumerConfig(
            durable_name=durable_name,
            deliver_policy=DeliverPolicy.LAST,
            ack_policy=AckPolicy.EXPLICIT,
            max_deliver=3,
            ack_wait=60,
            max_ack_pending=2000,
            filter_subject=subject_pattern
        )
        
        await self.jetstream._jsm.add_consumer(stream_name, consumer_config)
        print(f"✅ 消费者创建成功: {durable_name}")

        # 创建pull订阅
        consumer = await self.jetstream.pull_subscribe(
            subject=subject_pattern,
            durable=durable_name,
            stream=stream_name
        )
        
        # 启动消息处理任务
        task = asyncio.create_task(self._pull_message_handler(consumer, data_type))
        self.subscriptions[data_type] = {"consumer": consumer, "task": task}
        
        print(f"✅ JetStream订阅成功: {data_type} -> {subject_pattern}")

    async def _pull_message_handler(self, consumer, data_type: str):
        """Pull消费者消息处理器"""
        print(f"启动 {data_type} 消息处理器")
        
        while self.is_running:
            try:
                # 批量拉取消息
                msgs = await consumer.fetch(batch=10, timeout=5.0)
                
                for msg in msgs:
                    try:
                        await self._handle_message(msg, data_type)
                        await msg.ack()
                        self.stats["messages_processed"] += 1
                    except Exception as e:
                        print(f"❌ 消息处理失败 {data_type}: {e}")
                        self.stats["messages_failed"] += 1
                        await msg.nak()
                        
            except asyncio.TimeoutError:
                # 正常超时，继续循环
                continue
            except Exception as e:
                print(f"❌ Pull消息处理器错误 {data_type}: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, msg, data_type: str):
        """处理单个消息"""
        self.stats["messages_received"] += 1
        self.stats["last_message_time"] = time.time()
        
        try:
            # 解析消息
            data = json.loads(msg.data.decode())
            
            # 这里可以添加具体的数据处理逻辑
            # 例如：写入ClickHouse、数据验证等
            print(f"✅ 消息处理成功: {data_type} -> {msg.subject}")
            
        except Exception as e:
            print(f"❌ 消息处理失败: {e}")
            self.stats["last_error_time"] = time.time()
            raise

    async def start(self):
        """启动服务"""
        print("🚀 启动JetStream热端存储服务")
        self.is_running = True
        
        try:
            await self.connect()
            await self.setup_subscriptions()
            
            print("✅ 服务启动成功，开始处理消息...")
            
            # 保持服务运行
            while self.is_running:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"❌ 服务启动失败: {e}")
            print(traceback.format_exc())
            raise

    async def stop(self):
        """停止服务"""
        print("🛑 停止JetStream热端存储服务")
        self.is_running = False
        
        # 停止所有订阅任务
        for data_type, sub_info in self.subscriptions.items():
            if "task" in sub_info:
                sub_info["task"].cancel()
        
        # 关闭NATS连接
        if self.nats_client:
            await self.nats_client.close()
        
        print("✅ 服务已停止")

    def get_stats(self):
        """获取统计信息"""
        return self.stats.copy()

async def main():
    """主函数"""
    storage = JetStreamHotStorage()
    
    try:
        await storage.start()
    except KeyboardInterrupt:
        print("\n收到中断信号，正在停止服务...")
        await storage.stop()
    except Exception as e:
        print(f"服务运行错误: {e}")
        await storage.stop()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
