#!/usr/bin/env python3
"""
简单的NATS数据流监控脚本
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

class SimpleNATSMonitor:
    def __init__(self):
        self.nc = None
        self.message_count = 0
        self.topics_seen = set()
        self.data_types_seen = set()
        
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
            
            # 提取数据类型
            data_type = "unknown"
            if "data_type" in data:
                data_type = data["data_type"]
                self.data_types_seen.add(data_type)
            
            # 简化显示
            exchange = data.get("exchange", "unknown")
            symbol = data.get("symbol", "unknown")
            
            print(f"📨 [{timestamp}] {data_type.upper()}: {exchange} - {symbol}")
            
            # 显示关键数据
            if data_type == "orderbook":
                bids_count = len(data.get('bids', []))
                asks_count = len(data.get('asks', []))
                print(f"    📊 买盘: {bids_count}档, 卖盘: {asks_count}档")
                
            elif data_type == "trade":
                price = data.get('price', 'N/A')
                quantity = data.get('quantity', 'N/A')
                side = data.get('side', 'N/A')
                print(f"    💰 价格: {price}, 数量: {quantity}, 方向: {side}")
                
            elif data_type == "funding_rate":
                rate = data.get('funding_rate', 'N/A')
                next_time = data.get('next_funding_time', 'N/A')
                print(f"    💸 费率: {rate}, 下次: {next_time}")
                
            elif data_type == "open_interest":
                oi = data.get('open_interest', 'N/A')
                print(f"    📈 未平仓量: {oi}")
                
            elif data_type == "liquidation":
                price = data.get('price', 'N/A')
                quantity = data.get('quantity', 'N/A')
                side = data.get('side', 'N/A')
                print(f"    ⚡ 强平 - 价格: {price}, 数量: {quantity}, 方向: {side}")
                
            elif data_type in ["lsr_top_position", "lsr_all_account"]:
                long_ratio = data.get('long_ratio', data.get('long_position_ratio', 'N/A'))
                short_ratio = data.get('short_ratio', data.get('short_position_ratio', 'N/A'))
                print(f"    🎭 多仓: {long_ratio}, 空仓: {short_ratio}")
                
            elif data_type == "volatility_index":
                vol_index = data.get('vol_index', 'N/A')
                print(f"    📊 波动率指数: {vol_index}")
                
        except json.JSONDecodeError:
            print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] 无法解析JSON: {msg.subject}")
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
        last_count = 0
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
            
            # 每10秒显示一次统计
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                new_messages = self.message_count - last_count
                if new_messages > 0:
                    print(f"📊 [{int(elapsed)}s] 新消息: {new_messages}, 总计: {self.message_count}")
                    last_count = self.message_count
                
            await asyncio.sleep(1)
        
        # 显示最终统计信息
        print("\n" + "=" * 60)
        print("📊 监控统计:")
        print(f"  总消息数: {self.message_count}")
        print(f"  主题数量: {len(self.topics_seen)}")
        print(f"  数据类型: {', '.join(sorted(self.data_types_seen))}")
        
        if self.message_count == 0:
            print("\n⚠️ 未收到任何NATS消息，可能的原因:")
            print("  1. MarketPrism数据收集器未启动")
            print("  2. NATS连接配置错误")
            print("  3. 数据推送功能未正常工作")
        else:
            print(f"\n✅ NATS数据推送正常工作! 平均 {self.message_count/duration:.1f} 消息/秒")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 NATS连接已关闭")

async def main():
    """主函数"""
    print("🚀 简单NATS数据流监控工具")
    print("=" * 60)
    
    monitor = SimpleNATSMonitor()
    
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
