#!/usr/bin/env python3
"""
全面的NATS订阅监控脚本
验证MarketPrism所有managers的数据推送是否正常
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "services" / "data-collector"))

try:
    import nats
    from nats.errors import TimeoutError
except ImportError as e:
    print(f"❌ 无法导入NATS库: {e}")
    print("请安装: pip install nats-py")
    sys.exit(1)

class ComprehensiveNATSSubscriber:
    def __init__(self):
        self.nc = None
        self.message_count = 0
        self.data_type_stats = defaultdict(int)
        self.exchange_stats = defaultdict(int)
        self.symbol_stats = defaultdict(int)
        self.topic_stats = defaultdict(int)
        self.last_messages = {}  # 存储每种数据类型的最新消息
        
    async def connect(self):
        """连接到NATS服务器"""
        try:
            import os
            nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
            self.nc = await nats.connect(nats_url)
            print(f"✅ 成功连接到NATS服务器: {nats_url}")
            return True
        except Exception as e:
            print(f"❌ 连接NATS服务器失败: {e}")
            return False
    
    async def message_handler(self, msg):
        """处理接收到的消息"""
        self.message_count += 1
        
        try:
            data = json.loads(msg.data.decode())
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # 提取关键信息
            exchange = data.get("exchange", "unknown")
            symbol = data.get("symbol", "unknown")
            data_type = data.get("data_type", "unknown")
            
            # 统计信息
            self.data_type_stats[data_type] += 1
            self.exchange_stats[exchange] += 1
            self.symbol_stats[f"{exchange}:{symbol}"] += 1
            self.topic_stats[msg.subject] += 1
            
            # 存储最新消息样本
            key = f"{exchange}:{data_type}:{symbol}"
            self.last_messages[key] = {
                'timestamp': timestamp,
                'subject': msg.subject,
                'data': data,
                'sample_data': self._extract_sample_data(data, data_type)
            }
            
            # 实时显示重要数据类型
            if self.message_count % 100 == 0:
                print(f"📊 [{timestamp}] 已处理 {self.message_count} 条消息")
                
        except json.JSONDecodeError:
            print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] 无法解析JSON: {msg.subject}")
        except Exception as e:
            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] 处理消息错误: {e}")
    
    def _extract_sample_data(self, data, data_type):
        """提取数据样本用于显示"""
        if data_type == "orderbook":
            bids_count = len(data.get('bids', []))
            asks_count = len(data.get('asks', []))
            best_bid = data.get('bids', [{}])[0] if data.get('bids') else None
            best_ask = data.get('asks', [{}])[0] if data.get('asks') else None
            return {
                'bids_count': bids_count,
                'asks_count': asks_count,
                'best_bid': best_bid,
                'best_ask': best_ask
            }
        elif data_type == "trade":
            return {
                'price': data.get('price'),
                'quantity': data.get('quantity'),
                'side': data.get('side'),
                'trade_time': data.get('trade_time')
            }
        elif data_type == "funding_rate":
            return {
                'funding_rate': data.get('funding_rate'),
                'next_funding_time': data.get('next_funding_time')
            }
        elif data_type == "open_interest":
            return {
                'open_interest': data.get('open_interest'),
                'open_interest_value': data.get('open_interest_value')
            }
        elif data_type == "liquidation":
            return {
                'price': data.get('price'),
                'quantity': data.get('quantity'),
                'side': data.get('side')
            }
        elif data_type in ["lsr_top_position", "lsr_all_account"]:
            return {
                'long_ratio': data.get('long_ratio', data.get('long_position_ratio')),
                'short_ratio': data.get('short_ratio', data.get('short_position_ratio'))
            }
        elif data_type == "volatility_index":
            return {
                'vol_index': data.get('vol_index'),
                'symbol': data.get('symbol')
            }
        else:
            return {'raw_keys': list(data.keys())[:5]}  # 显示前5个字段
    
    async def subscribe_all(self):
        """订阅业务相关主题，过滤NATS内部主题"""
        if not self.nc:
            print("❌ 未连接到NATS服务器")
            return

        try:
            # 仅订阅业务主题前缀，避免 _INBOX.* 等内部主题对统计的干扰
            business_subjects = [
                "orderbook.>",
                "trade.>",
                "funding_rate.>",
                "open_interest.>",
                "liquidation.>",
                "lsr_top_position.>",
                "lsr_all_account.>",
                "volatility_index.>"
            ]
            for subj in business_subjects:
                await self.nc.subscribe(subj, cb=self.message_handler)
            print("🔍 开始监控业务NATS消息(已过滤内部主题)...")
            print("=" * 80)

        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    async def monitor(self, duration=60):
        """监控指定时间"""
        print(f"⏰ 监控时间: {duration}秒")
        
        start_time = asyncio.get_event_loop().time()
        last_report_time = start_time
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
            
            # 每15秒显示一次统计
            if current_time - last_report_time >= 15:
                await self._show_interim_stats()
                last_report_time = current_time
                
            await asyncio.sleep(1)
        
        # 显示最终统计
        await self._show_final_stats()
    
    async def _show_interim_stats(self):
        """显示中期统计"""
        print(f"\n📊 中期统计 (总消息: {self.message_count}):")
        print(f"  数据类型: {dict(self.data_type_stats)}")
        print(f"  交易所: {dict(self.exchange_stats)}")
        print("-" * 50)
    
    async def _show_final_stats(self):
        """显示最终详细统计"""
        print("\n" + "=" * 80)
        print("📊 完整的NATS数据订阅统计报告")
        print("=" * 80)
        
        print(f"🔢 总体统计:")
        print(f"  总消息数: {self.message_count}")
        print(f"  消息频率: {self.message_count/60:.1f} 消息/秒")
        
        print(f"\n📈 数据类型分布:")
        total_business_msgs = sum(self.data_type_stats.values()) or 1
        for data_type, count in sorted(self.data_type_stats.items(), key=lambda x: x[1], reverse=True):
            percentage = count / total_business_msgs * 100
            print(f"  {data_type}: {count} 条 ({percentage:.1f}%)")

        print(f"\n🏢 交易所分布:")
        for exchange, count in sorted(self.exchange_stats.items(), key=lambda x: x[1], reverse=True):
            percentage = count / total_business_msgs * 100
            print(f"  {exchange}: {count} 条 ({percentage:.1f}%)")
        
        print(f"\n💱 交易对分布:")
        for symbol, count in sorted(self.symbol_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {symbol}: {count} 条")
        
        print(f"\n📡 NATS主题分布:")
        # 仅展示业务主题
        business_topic_stats = {k: v for k, v in self.topic_stats.items() if not k.startswith("_INBOX.")}
        for topic, count in sorted(business_topic_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {topic}: {count} 条")
        
        # 显示每种数据类型的样本数据
        print(f"\n🔍 数据样本 (每种数据类型的最新消息):")
        for key, msg_info in self.last_messages.items():
            exchange, data_type, symbol = key.split(':', 2)
            print(f"\n  📋 {data_type.upper()} - {exchange} - {symbol}:")
            print(f"    主题: {msg_info['subject']}")
            print(f"    时间: {msg_info['timestamp']}")
            print(f"    样本数据: {msg_info['sample_data']}")
        
        # 验证所有预期的数据类型
        expected_data_types = {
            "orderbook", "trade", "funding_rate", "open_interest", 
            "liquidation", "lsr_top_position", "lsr_all_account", "volatility_index"
        }
        found_data_types = set(self.data_type_stats.keys())
        
        print(f"\n✅ 数据类型覆盖验证:")
        for dt in expected_data_types:
            if dt in found_data_types:
                print(f"  ✅ {dt}: 已收到 {self.data_type_stats[dt]} 条消息")
            else:
                print(f"  ❌ {dt}: 未收到消息")
        
        missing_types = expected_data_types - found_data_types
        unexpected_types = found_data_types - expected_data_types
        
        if missing_types:
            print(f"\n⚠️ 缺失的数据类型: {missing_types}")
        if unexpected_types:
            print(f"\n🔍 意外的数据类型: {unexpected_types}")
        
        if not missing_types and self.message_count > 0:
            print(f"\n🎉 所有预期的数据类型都已收到！系统运行完美！")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 NATS连接已关闭")

async def main():
    """主函数"""
    print("🚀 MarketPrism全面NATS订阅监控")
    print("=" * 80)
    
    subscriber = ComprehensiveNATSSubscriber()
    
    # 连接NATS
    if not await subscriber.connect():
        return
    
    try:
        # 订阅所有消息
        await subscriber.subscribe_all()
        
        # 监控60秒
        await subscriber.monitor(60)
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断监控")
    except Exception as e:
        print(f"❌ 监控过程中出错: {e}")
    finally:
        await subscriber.close()

if __name__ == "__main__":
    asyncio.run(main())
