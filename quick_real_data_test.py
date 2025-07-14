#!/usr/bin/env python3
"""
快速真实数据测试
直接启动数据收集器并验证NATS数据推送
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, '/home/ubuntu/marketprism')
sys.path.insert(0, '/home/ubuntu/marketprism/services/data-collector')

try:
    import nats
    from nats.errors import TimeoutError
except ImportError:
    print("❌ 请安装nats-py: pip install nats-py")
    exit(1)

from collector.nats_publisher import NATSPublisher
from collector.normalizer import DataNormalizer
from exchanges.binance_websocket import BinanceWebSocket
from collector.data_types import MarketType, Exchange


class QuickRealDataTest:
    def __init__(self):
        self.publisher = None
        self.subscriber = None
        self.binance_manager = None
        self.received_count = 0
        self.price_samples = {}
        
    async def setup_nats(self):
        """设置NATS发布者和订阅者"""
        # 设置发布者
        normalizer = DataNormalizer()
        self.publisher = NATSPublisher(normalizer=normalizer)
        await self.publisher.connect()
        print("✅ NATS发布者连接成功")
        
        # 设置订阅者
        self.subscriber = await nats.connect("nats://localhost:4222")
        print("✅ NATS订阅者连接成功")
    
    async def setup_binance_collector(self):
        """设置Binance数据收集器"""
        config = {
            'exchange': Exchange.BINANCE_SPOT,
            'market_type': MarketType.SPOT,
            'symbols': ['BTCUSDT', 'ETHUSDT'],
            'base_url': 'https://api.binance.com',
            'websocket_url': 'wss://stream.binance.com:9443/ws',
            'nats_publisher': self.publisher
        }
        
        self.binance_manager = BinanceWebSocket(config)
        print("✅ Binance WebSocket管理器创建成功")
    
    async def message_handler(self, msg):
        """处理接收到的NATS消息"""
        try:
            self.received_count += 1
            subject = msg.subject
            data = json.loads(msg.data.decode())
            
            # 解析主题
            parts = subject.split('.')
            if len(parts) >= 4:
                exchange = parts[1]
                market_type = parts[2]
                symbol = parts[3]
                
                # 提取价格信息
                if 'data' in data and 'metadata' in data:
                    orderbook_data = data['data']
                    if orderbook_data.get('bids') and orderbook_data.get('asks'):
                        try:
                            bids = orderbook_data['bids']
                            asks = orderbook_data['asks']
                            
                            if bids and asks:
                                # 检查数据格式并提取价格
                                if isinstance(bids[0], dict) and 'price' in bids[0]:
                                    best_bid = float(bids[0]['price'])
                                    best_ask = float(asks[0]['price'])
                                elif isinstance(bids[0], (list, tuple)) and len(bids[0]) >= 2:
                                    best_bid = float(bids[0][0])
                                    best_ask = float(asks[0][0])
                                else:
                                    return
                                
                                key = f"{exchange}.{symbol}"
                                self.price_samples[key] = {
                                    'bid': best_bid,
                                    'ask': best_ask,
                                    'spread': best_ask - best_bid,
                                    'timestamp': data['metadata'].get('timestamp')
                                }
                                
                                # 实时显示价格
                                spread_pct = (best_ask - best_bid) / best_bid * 100
                                print(f"💰 {key}: 买={best_bid:.2f}, 卖={best_ask:.2f}, 价差={spread_pct:.4f}%")
                        except (KeyError, ValueError, IndexError, TypeError):
                            pass
            
            # 每10条消息打印一次统计
            if self.received_count % 10 == 0:
                print(f"\n📊 已接收 {self.received_count} 条消息")
                
        except Exception as e:
            print(f"❌ 处理消息异常: {e}")
    
    async def start_binance_collection(self):
        """启动Binance数据收集"""
        print("🚀 启动Binance数据收集...")
        await self.binance_manager.start()
        print("✅ Binance数据收集已启动")
    
    async def subscribe_data(self):
        """订阅NATS数据"""
        subject = "orderbook-data.>"
        print(f"🔔 订阅NATS主题: {subject}")
        
        await self.subscriber.subscribe(subject, cb=self.message_handler)
        print("✅ NATS订阅成功，等待实时数据...")
        
        # 运行60秒接收实时数据
        await asyncio.sleep(60)
    
    async def print_final_summary(self):
        """打印最终统计摘要"""
        print(f"\n🎉 快速真实数据测试完成!")
        print(f"📊 总计接收消息: {self.received_count}条")
        
        if self.price_samples:
            print(f"\n💰 最终价格快照:")
            for key, price_info in self.price_samples.items():
                spread_pct = (price_info['spread'] / price_info['bid']) * 100
                print(f"   {key}:")
                print(f"     买盘: {price_info['bid']:.2f}")
                print(f"     卖盘: {price_info['ask']:.2f}")
                print(f"     价差: {spread_pct:.4f}%")
                print(f"     时间: {price_info['timestamp']}")
        else:
            print("⚠️ 未接收到价格数据")
    
    async def close(self):
        """关闭所有连接"""
        if self.binance_manager:
            await self.binance_manager.stop()
        if self.publisher and hasattr(self.publisher, 'disconnect'):
            await self.publisher.disconnect()
        if self.subscriber:
            await self.subscriber.close()
        print("🔌 所有连接已关闭")


async def main():
    """主函数"""
    print("🚀 启动快速真实数据测试")
    print("=" * 50)
    print("📡 将连接到Binance WebSocket获取真实BTC和ETH价格")
    print("💰 显示真实的市场价格数据")
    print("=" * 50)
    
    test = QuickRealDataTest()
    
    try:
        # 设置NATS
        await test.setup_nats()
        
        # 设置Binance收集器
        await test.setup_binance_collector()
        
        # 启动数据收集
        await test.start_binance_collection()
        
        # 等待连接稳定
        print("⏳ 等待WebSocket连接稳定...")
        await asyncio.sleep(5)
        
        # 订阅数据
        await test.subscribe_data()
        
        # 打印摘要
        await test.print_final_summary()
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    except Exception as e:
        print(f"❌ 运行异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await test.close()


if __name__ == "__main__":
    asyncio.run(main())
