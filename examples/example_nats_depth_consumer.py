#!/usr/bin/env python3
"""
通过NATS消息队列获取深度数据示例

演示如何订阅NATS JetStream中的订单簿数据流
"""

import asyncio
import json
import nats
from nats.js import JetStreamContext
from datetime import datetime

class NATSDepthConsumer:
    """NATS深度数据消费者"""
    
    def __init__(self, nats_url="nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc = None
        self.js = None
    
    async def connect(self):
        """连接到NATS服务器"""
        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()
            print(f"✅ 已连接到NATS服务器: {self.nats_url}")
            return True
        except Exception as e:
            print(f"❌ 连接NATS失败: {e}")
            return False
    
    async def subscribe_orderbook_stream(self, exchange: str = None, symbol: str = None):
        """订阅订单簿数据流"""
        try:
            # 构建订阅主题
            if exchange and symbol:
                subject = f"market.orderbook.{exchange}.{symbol}"
            elif exchange:
                subject = f"market.orderbook.{exchange}.*"
            else:
                subject = "market.orderbook.*"
            
            print(f"📡 订阅主题: {subject}")
            
            # 创建消费者
            consumer_config = {
                "durable_name": f"depth_consumer_{int(datetime.now().timestamp())}",
                "deliver_policy": "new",  # 只接收新消息
            }
            
            # 订阅消息
            subscription = await self.js.subscribe(
                subject,
                **consumer_config
            )
            
            print(f"🔄 开始接收订单簿数据...")
            
            async for msg in subscription.messages:
                await self.handle_orderbook_message(msg)
                await msg.ack()
                
        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    async def handle_orderbook_message(self, msg):
        """处理订单簿消息"""
        try:
            # 解析消息
            data = json.loads(msg.data.decode())
            
            # 提取关键信息
            exchange = data.get('exchange_name', 'unknown')
            symbol = data.get('symbol_name', 'unknown')
            update_type = data.get('update_type', 'unknown')
            depth_levels = data.get('depth_levels', 0)
            timestamp = data.get('timestamp', '')
            
            print(f"📊 {exchange} {symbol} - {update_type}")
            print(f"   深度档数: {depth_levels}")
            print(f"   时间戳: {timestamp}")
            
            # 显示最佳买卖价
            bids = data.get('bids', [])
            asks = data.get('asks', [])
            
            if bids and asks:
                best_bid = bids[0]['price']
                best_ask = asks[0]['price']
                spread = float(best_ask) - float(best_bid)
                
                print(f"   最佳买价: {best_bid}")
                print(f"   最佳卖价: {best_ask}")
                print(f"   价差: {spread:.8f}")
            
            # 显示变化信息（如果是增量更新）
            if update_type == "UPDATE":
                bid_changes = data.get('bid_changes', [])
                ask_changes = data.get('ask_changes', [])
                
                if bid_changes or ask_changes:
                    print(f"   买盘变化: {len(bid_changes)} 档")
                    print(f"   卖盘变化: {len(ask_changes)} 档")
            
            print("-" * 50)
            
        except Exception as e:
            print(f"❌ 处理消息失败: {e}")
    
    async def get_stream_info(self):
        """获取数据流信息"""
        try:
            # 获取所有流信息
            streams = await self.js.streams_info()
            
            print("📊 NATS JetStream 信息:")
            for stream in streams:
                if "MARKET" in stream.config.name:
                    print(f"   流名称: {stream.config.name}")
                    print(f"   主题: {stream.config.subjects}")
                    print(f"   消息数: {stream.state.messages}")
                    print(f"   存储大小: {stream.state.bytes} bytes")
                    print(f"   消费者数: {stream.state.consumer_count}")
                    print("-" * 30)
                    
        except Exception as e:
            print(f"❌ 获取流信息失败: {e}")
    
    async def disconnect(self):
        """断开连接"""
        if self.nc:
            await self.nc.close()
            print("✅ 已断开NATS连接")

async def main():
    """主函数"""
    consumer = NATSDepthConsumer()
    
    try:
        print("🚀 MarketPrism NATS深度数据消费示例")
        print("=" * 50)
        
        # 1. 连接到NATS
        if not await consumer.connect():
            return
        
        # 2. 获取流信息
        print("\n📊 获取数据流信息:")
        await consumer.get_stream_info()
        
        # 3. 选择订阅模式
        print(f"\n🔄 选择订阅模式:")
        print("1. 订阅所有订单簿数据")
        print("2. 订阅Binance所有交易对")
        print("3. 订阅Binance BTCUSDT")
        print("4. 订阅OKX所有交易对")
        
        # 自动选择模式3进行演示
        choice = "3"
        print(f"选择: {choice}")
        
        if choice == "1":
            await consumer.subscribe_orderbook_stream()
        elif choice == "2":
            await consumer.subscribe_orderbook_stream("binance")
        elif choice == "3":
            await consumer.subscribe_orderbook_stream("binance", "BTCUSDT")
        elif choice == "4":
            await consumer.subscribe_orderbook_stream("okx")
        else:
            print("无效选择")
            return
        
    except KeyboardInterrupt:
        print("\\n⏹️  用户中断")
    except Exception as e:
        print(f"❌ 运行异常: {e}")
    finally:
        await consumer.disconnect()

if __name__ == "__main__":
    # 注意：需要先启动NATS服务器和MarketPrism collector
    print("⚠️  注意：此示例需要NATS服务器和MarketPrism collector正在运行")
    print("启动命令: docker-compose -f docker-compose.infrastructure.yml up -d")
    print("然后: docker-compose up -d python-collector")
    print()
    
    asyncio.run(main())