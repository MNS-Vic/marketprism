#!/usr/bin/env python3
"""
NATS数据流监控脚本
用于验证MarketPrism是否正常推送数据到NATS
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

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

class NATSMonitor:
    def __init__(self):
        self.nc = None
        self.message_count = 0
        self.topics_seen = set()
        
    async def connect(self):
        """连接到NATS服务器"""
        try:
            self.nc = await nats.connect("nats://localhost:4222")
            print("✅ 成功连接到NATS服务器")
            return True
        except Exception as e:
            print(f"❌ 连接NATS服务器失败: {e}")
            return False
    
    async def message_handler(self, msg):
        """处理接收到的消息"""
        self.message_count += 1
        self.topics_seen.add(msg.subject)
        
        # 解析消息数据
        try:
            data = json.loads(msg.data.decode())
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # 根据主题类型显示不同信息
            if "orderbook-data" in msg.subject:
                print(f"📊 [{timestamp}] OrderBook: {msg.subject}")
                if 'bids' in data and 'asks' in data:
                    best_bid = data['bids'][0] if data['bids'] else None
                    best_ask = data['asks'][0] if data['asks'] else None
                    print(f"    最佳买价: {best_bid}, 最佳卖价: {best_ask}")
                    
            elif "trade-data" in msg.subject:
                print(f"💰 [{timestamp}] Trade: {msg.subject}")
                if 'price' in data and 'quantity' in data:
                    print(f"    价格: {data.get('price')}, 数量: {data.get('quantity')}, 方向: {data.get('side', 'N/A')}")
                    
            elif "funding-rate-data" in msg.subject:
                print(f"💸 [{timestamp}] Funding Rate: {msg.subject}")
                if 'funding_rate' in data:
                    print(f"    资金费率: {data.get('funding_rate')}, 下次更新: {data.get('next_funding_time', 'N/A')}")
                    
            elif "open-interest-data" in msg.subject:
                print(f"📈 [{timestamp}] Open Interest: {msg.subject}")
                if 'open_interest' in data:
                    print(f"    未平仓量: {data.get('open_interest')}")
                    
            elif "liquidation-data" in msg.subject:
                print(f"⚡ [{timestamp}] Liquidation: {msg.subject}")
                if 'quantity' in data:
                    print(f"    强平数量: {data.get('quantity')}, 价格: {data.get('price', 'N/A')}")
                    
            elif "lsr-data" in msg.subject:
                print(f"🎭 [{timestamp}] LSR: {msg.subject}")
                if 'long_ratio' in data:
                    print(f"    多仓比例: {data.get('long_ratio')}, 空仓比例: {data.get('short_ratio')}")
                    
            elif "vol-index-data" in msg.subject:
                print(f"📊 [{timestamp}] Vol Index: {msg.subject}")
                if 'vol_index' in data:
                    print(f"    波动率指数: {data.get('vol_index')}")
                    
            else:
                print(f"📨 [{timestamp}] 其他数据: {msg.subject}")
                
        except json.JSONDecodeError:
            print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] 无法解析JSON数据: {msg.subject}")
        except Exception as e:
            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] 处理消息错误: {e}")
    
    async def subscribe_all(self):
        """订阅所有主题"""
        if not self.nc:
            print("❌ 未连接到NATS服务器")
            return
            
        try:
            # 订阅所有主题
            await self.nc.subscribe(">", cb=self.message_handler)
            print("🔍 开始监控所有NATS消息...")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    async def monitor(self, duration=60):
        """监控指定时间"""
        print(f"⏰ 监控时间: {duration}秒")
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
                
            await asyncio.sleep(1)
        
        # 显示统计信息
        print("\n" + "=" * 60)
        print("📊 监控统计:")
        print(f"  总消息数: {self.message_count}")
        print(f"  主题数量: {len(self.topics_seen)}")
        print("  发现的主题:")
        for topic in sorted(self.topics_seen):
            print(f"    - {topic}")
            
        if self.message_count == 0:
            print("⚠️ 未收到任何NATS消息，可能的原因:")
            print("  1. MarketPrism数据收集器未启动")
            print("  2. NATS连接配置错误")
            print("  3. 数据推送功能未正常工作")
        else:
            print("✅ NATS数据推送正常工作!")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 NATS连接已关闭")

async def main():
    """主函数"""
    print("🚀 NATS数据流监控工具")
    print("=" * 60)
    
    monitor = NATSMonitor()
    
    # 连接NATS
    if not await monitor.connect():
        return
    
    try:
        # 订阅所有消息
        await monitor.subscribe_all()
        
        # 监控60秒
        await monitor.monitor(60)
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断监控")
    except Exception as e:
        print(f"❌ 监控过程中出错: {e}")
    finally:
        await monitor.close()

if __name__ == "__main__":
    asyncio.run(main())
