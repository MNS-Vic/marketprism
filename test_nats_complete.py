#!/usr/bin/env python3
"""
完整的NATS发布和订阅测试
同时运行发布进程和订阅进程来验证数据流
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, '/home/ubuntu/marketprism/services/data-collector')

from collector.nats_publisher import NATSPublisher
from collector.normalizer import DataNormalizer
from collector.data_types import EnhancedOrderBook, PriceLevel

try:
    import nats
    from nats.errors import TimeoutError
except ImportError:
    print("❌ 请安装nats-py: pip install nats-py")
    exit(1)


class NATSTestRunner:
    def __init__(self):
        self.publisher = None
        self.subscriber = None
        self.received_count = 0
        self.exchanges_seen = set()
        self.symbols_seen = set()
        self.market_types_seen = set()
        self.sample_data = {}
        
    async def create_test_orderbook(self, exchange: str, market_type: str, symbol: str) -> EnhancedOrderBook:
        """创建测试订单簿数据"""
        
        # 创建测试价格档位
        bids = [
            PriceLevel(price=Decimal("50000.00"), quantity=Decimal("1.5")),
            PriceLevel(price=Decimal("49999.50"), quantity=Decimal("2.0")),
            PriceLevel(price=Decimal("49999.00"), quantity=Decimal("1.8")),
        ]
        
        asks = [
            PriceLevel(price=Decimal("50001.00"), quantity=Decimal("1.2")),
            PriceLevel(price=Decimal("50001.50"), quantity=Decimal("1.8")),
            PriceLevel(price=Decimal("50002.00"), quantity=Decimal("2.2")),
        ]
        
        # 创建增强订单簿
        orderbook = EnhancedOrderBook(
            exchange_name=exchange,
            symbol_name=symbol,
            market_type=market_type,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
            last_update_id=12345,
            checksum=12345
        )
        
        return orderbook
    
    async def setup_publisher(self):
        """设置发布者"""
        normalizer = DataNormalizer()
        self.publisher = NATSPublisher(normalizer=normalizer)
        await self.publisher.connect()
        print("✅ 发布者连接成功")
    
    async def setup_subscriber(self):
        """设置订阅者"""
        self.subscriber = await nats.connect("nats://localhost:4222")
        print("✅ 订阅者连接成功")
    
    async def message_handler(self, msg):
        """处理接收到的订单簿消息"""
        try:
            self.received_count += 1
            subject = msg.subject
            data = json.loads(msg.data.decode())
            
            # 解析主题
            parts = subject.split('.')
            if len(parts) >= 4:
                data_type = parts[0]  # orderbook-data
                exchange = parts[1]   # binance_spot, okx_spot, etc.
                market_type = parts[2]  # spot, perpetual
                symbol = parts[3]     # BTC-USDT, ETH-USDT
                
                self.exchanges_seen.add(exchange)
                self.market_types_seen.add(market_type)
                self.symbols_seen.add(symbol)
                
                # 保存样例数据
                key = f"{exchange}.{market_type}.{symbol}"
                if key not in self.sample_data:
                    self.sample_data[key] = data
            
            # 每5条消息打印一次统计
            if self.received_count % 5 == 0:
                print(f"\n📊 接收统计 (第{self.received_count}条消息)")
                print(f"   主题: {subject}")
                print(f"   交易所: {sorted(self.exchanges_seen)}")
                print(f"   市场类型: {sorted(self.market_types_seen)}")
                print(f"   交易对: {sorted(self.symbols_seen)}")
                
                # 验证数据格式
                self._validate_data_format(data, subject)
                
        except Exception as e:
            print(f"❌ 处理消息异常: {e}")
    
    def _validate_data_format(self, data, subject):
        """验证订单簿数据格式"""
        # 检查NATS消息结构
        if 'data' in data and 'metadata' in data:
            # 新的NATS消息格式
            orderbook_data = data['data']
            metadata = data['metadata']
            
            print(f"   ✅ NATS消息格式正确")
            print(f"   📋 元数据: exchange={metadata.get('exchange')}, market_type={metadata.get('market_type')}, symbol={metadata.get('symbol')}")
            
            # 检查订单簿数据
            bid_count = len(orderbook_data.get('bids', []))
            ask_count = len(orderbook_data.get('asks', []))
            print(f"   📈 深度: 买盘{bid_count}档, 卖盘{ask_count}档")
            
            # 检查价格合理性
            if orderbook_data.get('bids') and orderbook_data.get('asks'):
                try:
                    bids = orderbook_data['bids']
                    asks = orderbook_data['asks']
                    
                    if bids and asks:
                        # 检查是否是字典格式 {'price': ..., 'quantity': ...}
                        if isinstance(bids[0], dict) and 'price' in bids[0]:
                            best_bid = float(bids[0]['price'])
                            best_ask = float(asks[0]['price'])
                        # 检查是否是列表格式 [price, quantity]
                        elif isinstance(bids[0], (list, tuple)) and len(bids[0]) >= 2:
                            best_bid = float(bids[0][0])
                            best_ask = float(asks[0][0])
                        else:
                            print(f"   ⚠️ 未知的价格数据格式: {type(bids[0])}")
                            return
                            
                        spread = best_ask - best_bid
                        spread_pct = (spread / best_bid) * 100
                        print(f"   💰 最优价格: 买={best_bid}, 卖={best_ask}, 价差={spread_pct:.4f}%")
                except (KeyError, ValueError, IndexError, TypeError) as e:
                    print(f"   ⚠️ 价格数据格式错误: {e}")
    
    async def publish_data(self):
        """发布测试数据"""
        test_configs = [
            ("binance_spot", "spot", "BTCUSDT"),
            ("binance_derivatives", "perpetual", "BTCUSDT"),
            ("okx_spot", "spot", "BTC-USDT"),
            ("okx_derivatives", "perpetual", "BTC-USDT-SWAP"),
        ]
        
        print(f"\n📡 开始发布测试数据...")
        
        for i in range(20):  # 发布20轮数据
            for exchange, market_type, symbol in test_configs:
                orderbook = await self.create_test_orderbook(exchange, market_type, symbol)
                await self.publisher.publish_enhanced_orderbook(orderbook)
            
            await asyncio.sleep(1)  # 每秒发布一轮
            
            if (i + 1) % 5 == 0:
                print(f"   已发布 {i + 1} 轮数据")
    
    async def subscribe_data(self):
        """订阅数据"""
        subject = "orderbook-data.>"
        print(f"🔔 订阅主题: {subject}")
        
        await self.subscriber.subscribe(subject, cb=self.message_handler)
        print("✅ 订阅成功，等待数据...")
        
        # 等待25秒接收数据
        await asyncio.sleep(25)
    
    async def print_summary(self):
        """打印最终统计摘要"""
        print(f"\n🎉 测试完成!")
        print(f"📊 总计接收消息: {self.received_count}条")
        print(f"🏢 交易所数量: {len(self.exchanges_seen)}")
        print(f"📈 市场类型: {len(self.market_types_seen)}")
        print(f"💱 交易对数量: {len(self.symbols_seen)}")
        
        print(f"\n📋 详细统计:")
        print(f"   交易所: {sorted(self.exchanges_seen)}")
        print(f"   市场类型: {sorted(self.market_types_seen)}")
        print(f"   交易对: {sorted(self.symbols_seen)}")
        
        # 打印样例数据
        print(f"\n📄 样例数据:")
        for key, data in list(self.sample_data.items())[:3]:  # 显示前3个
            print(f"\n🔍 {key}:")
            
            # 检查数据格式
            if 'data' in data and 'metadata' in data:
                # 新的NATS消息格式
                orderbook_data = data['data']
                metadata = data['metadata']
                
                print(f"   Symbol: {metadata.get('symbol')}")
                print(f"   Exchange: {metadata.get('exchange')}")
                print(f"   Market Type: {metadata.get('market_type')}")
                print(f"   Timestamp: {metadata.get('timestamp')}")
                print(f"   Bids: {len(orderbook_data.get('bids', []))}档")
                print(f"   Asks: {len(orderbook_data.get('asks', []))}档")
                
                if orderbook_data.get('bids') and orderbook_data.get('asks'):
                    try:
                        bids = orderbook_data['bids']
                        asks = orderbook_data['asks']
                        
                        if bids and asks:
                            # 检查是否是字典格式 {'price': ..., 'quantity': ...}
                            if isinstance(bids[0], dict) and 'price' in bids[0]:
                                print(f"   Best Bid: {bids[0]['price']} @ {bids[0]['quantity']}")
                                print(f"   Best Ask: {asks[0]['price']} @ {asks[0]['quantity']}")
                            # 检查是否是列表格式 [price, quantity]
                            elif isinstance(bids[0], (list, tuple)) and len(bids[0]) >= 2:
                                print(f"   Best Bid: {bids[0][0]} @ {bids[0][1]}")
                                print(f"   Best Ask: {asks[0][0]} @ {asks[0][1]}")
                            else:
                                print(f"   ⚠️ 未知的价格数据格式: {type(bids[0])}")
                    except (KeyError, IndexError, TypeError):
                        print(f"   ⚠️ 价格数据格式异常")
    
    async def close(self):
        """关闭连接"""
        if self.publisher and hasattr(self.publisher, 'disconnect'):
            await self.publisher.disconnect()
        if self.subscriber:
            await self.subscriber.close()
        print("🔌 所有连接已关闭")


async def main():
    """主函数"""
    print("🚀 启动完整的NATS发布和订阅测试")
    print("=" * 50)
    
    runner = NATSTestRunner()
    
    try:
        # 设置发布者和订阅者
        await runner.setup_publisher()
        await runner.setup_subscriber()
        
        # 同时运行发布和订阅
        await asyncio.gather(
            runner.publish_data(),
            runner.subscribe_data()
        )
        
        # 打印摘要
        await runner.print_summary()
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    except Exception as e:
        print(f"❌ 运行异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
