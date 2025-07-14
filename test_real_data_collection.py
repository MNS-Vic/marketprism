#!/usr/bin/env python3
"""
真实数据收集器测试
连接到真实的交易所WebSocket获取实时订单簿数据并推送到NATS
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, '/home/ubuntu/marketprism/services/data-collector')

from collector.nats_publisher import NATSPublisher
from collector.normalizer import DataNormalizer
from collector.data_collection_config_manager import DataCollectionConfigManager

try:
    import nats
    from nats.errors import TimeoutError
except ImportError:
    print("❌ 请安装nats-py: pip install nats-py")
    exit(1)


class RealDataTestRunner:
    def __init__(self):
        self.config_manager = None
        self.publisher = None
        self.subscriber = None
        self.collectors = []
        self.received_count = 0
        self.exchanges_seen = set()
        self.symbols_seen = set()
        self.market_types_seen = set()
        self.price_samples = {}
        
    async def setup_config(self):
        """设置配置管理器"""
        self.config_manager = ConfigManager(
            config_dir="/home/ubuntu/marketprism/config",
            env_override=True,
            hot_reload=False
        )
        print("✅ 配置管理器初始化成功")
    
    async def setup_publisher(self):
        """设置NATS发布者"""
        normalizer = DataNormalizer()
        self.publisher = NATSPublisher(normalizer=normalizer)
        await self.publisher.connect()
        print("✅ NATS发布者连接成功")
    
    async def setup_subscriber(self):
        """设置NATS订阅者"""
        self.subscriber = await nats.connect("nats://localhost:4222")
        print("✅ NATS订阅者连接成功")
    
    async def setup_collectors(self):
        """设置真实数据收集器"""
        try:
            # 获取配置
            exchange_config = self.config_manager.get_config('exchange')
            
            # 创建Binance现货收集器
            binance_config = {
                'exchange_name': 'binance_spot',
                'market_type': 'spot',
                'symbols': ['BTCUSDT', 'ETHUSDT'],
                'api_config': exchange_config.binance,
                'nats_publisher': self.publisher
            }
            
            binance_collector = BinanceSpotCollector(binance_config)
            self.collectors.append(binance_collector)
            print("✅ Binance现货收集器创建成功")
            
            # 创建OKX现货收集器
            okx_config = {
                'exchange_name': 'okx_spot',
                'market_type': 'spot', 
                'symbols': ['BTC-USDT', 'ETH-USDT'],
                'api_config': exchange_config.okx,
                'nats_publisher': self.publisher
            }
            
            okx_collector = OKXSpotCollector(okx_config)
            self.collectors.append(okx_collector)
            print("✅ OKX现货收集器创建成功")
            
        except Exception as e:
            print(f"❌ 创建收集器失败: {e}")
            import traceback
            traceback.print_exc()
    
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
                
                # 保存价格样例
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
                        except (KeyError, ValueError, IndexError, TypeError):
                            pass
            
            # 每10条消息打印一次统计
            if self.received_count % 10 == 0:
                print(f"\n📊 实时数据统计 (第{self.received_count}条消息)")
                print(f"   主题: {subject}")
                print(f"   交易所: {sorted(self.exchanges_seen)}")
                print(f"   市场类型: {sorted(self.market_types_seen)}")
                print(f"   交易对: {sorted(self.symbols_seen)}")
                
                # 显示实时价格
                print(f"\n💰 实时价格:")
                for key, price_info in list(self.price_samples.items())[-4:]:  # 显示最新4个
                    spread_pct = (price_info['spread'] / price_info['bid']) * 100
                    print(f"   {key}: 买={price_info['bid']:.2f}, 卖={price_info['ask']:.2f}, 价差={spread_pct:.4f}%")
                
        except Exception as e:
            print(f"❌ 处理消息异常: {e}")
    
    async def start_collectors(self):
        """启动所有数据收集器"""
        print(f"\n🚀 启动 {len(self.collectors)} 个数据收集器...")
        
        tasks = []
        for collector in self.collectors:
            task = asyncio.create_task(collector.start())
            tasks.append(task)
            print(f"   ✅ {collector.exchange_name} 收集器已启动")
        
        return tasks
    
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
        print(f"\n🎉 实时数据测试完成!")
        print(f"📊 总计接收消息: {self.received_count}条")
        print(f"🏢 交易所数量: {len(self.exchanges_seen)}")
        print(f"📈 市场类型: {len(self.market_types_seen)}")
        print(f"💱 交易对数量: {len(self.symbols_seen)}")
        
        print(f"\n📋 详细统计:")
        print(f"   交易所: {sorted(self.exchanges_seen)}")
        print(f"   市场类型: {sorted(self.market_types_seen)}")
        print(f"   交易对: {sorted(self.symbols_seen)}")
        
        # 显示最终价格快照
        print(f"\n💰 最终价格快照:")
        for key, price_info in self.price_samples.items():
            spread_pct = (price_info['spread'] / price_info['bid']) * 100
            print(f"   {key}:")
            print(f"     买盘: {price_info['bid']:.2f}")
            print(f"     卖盘: {price_info['ask']:.2f}")
            print(f"     价差: {spread_pct:.4f}%")
            print(f"     时间: {price_info['timestamp']}")
    
    async def stop_collectors(self):
        """停止所有数据收集器"""
        print(f"\n⏹️ 停止数据收集器...")
        for collector in self.collectors:
            try:
                await collector.stop()
                print(f"   ✅ {collector.exchange_name} 收集器已停止")
            except Exception as e:
                print(f"   ⚠️ 停止 {collector.exchange_name} 收集器时出错: {e}")
    
    async def close(self):
        """关闭所有连接"""
        await self.stop_collectors()
        
        if self.publisher and hasattr(self.publisher, 'disconnect'):
            await self.publisher.disconnect()
        if self.subscriber:
            await self.subscriber.close()
        print("🔌 所有连接已关闭")


async def main():
    """主函数"""
    print("🚀 启动真实数据收集器测试")
    print("=" * 50)
    print("📡 将连接到真实的交易所WebSocket获取实时订单簿数据")
    print("💰 显示真实的BTC和ETH价格")
    print("=" * 50)
    
    runner = RealDataTestRunner()
    
    try:
        # 设置组件
        await runner.setup_config()
        await runner.setup_publisher()
        await runner.setup_subscriber()
        await runner.setup_collectors()
        
        # 启动数据收集器
        collector_tasks = await runner.start_collectors()
        
        # 等待收集器连接
        print("⏳ 等待收集器连接到交易所...")
        await asyncio.sleep(5)
        
        # 订阅数据
        await runner.subscribe_data()
        
        # 打印摘要
        await runner.print_final_summary()
        
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
