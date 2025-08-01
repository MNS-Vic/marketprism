#!/usr/bin/env python3
"""
专门监控Open Interest NATS主题的脚本
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

class OpenInterestNATSMonitor:
    def __init__(self):
        self.nc = None
        self.oi_messages = []
        
    async def connect(self):
        """连接到NATS服务器"""
        try:
            self.nc = await nats.connect("nats://localhost:4222")
            print("✅ 成功连接到NATS服务器")
            return True
        except Exception as e:
            print(f"❌ 连接NATS服务器失败: {e}")
            return False
    
    async def oi_message_handler(self, msg):
        """处理Open Interest消息"""
        try:
            data = json.loads(msg.data.decode())
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            print(f"🎯 [{timestamp}] 收到Open Interest数据!")
            print(f"    主题: {msg.subject}")
            print(f"    交易所: {data.get('exchange', 'N/A')}")
            print(f"    交易对: {data.get('symbol', 'N/A')}")
            print(f"    未平仓量: {data.get('open_interest_value', 'N/A')}")
            print(f"    USD价值: {data.get('open_interest_usd', 'N/A')}")
            print(f"    时间戳: {data.get('timestamp', 'N/A')}")
            print(f"    完整数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
            print("-" * 80)
            
            self.oi_messages.append({
                'timestamp': timestamp,
                'subject': msg.subject,
                'data': data
            })
            
        except json.JSONDecodeError:
            print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] 无法解析JSON: {msg.subject}")
        except Exception as e:
            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] 处理消息错误: {e}")
    
    async def subscribe_oi_topics(self):
        """订阅Open Interest相关主题"""
        if not self.nc:
            print("❌ 未连接到NATS服务器")
            return
            
        try:
            # 订阅所有open interest相关主题
            await self.nc.subscribe("open-interest-data.>", cb=self.oi_message_handler)
            await self.nc.subscribe("open_interest-data.>", cb=self.oi_message_handler)  # 备用格式
            await self.nc.subscribe("*.open-interest.*", cb=self.oi_message_handler)
            await self.nc.subscribe("*.open_interest.*", cb=self.oi_message_handler)
            
            print("🔍 开始专门监控Open Interest NATS主题...")
            print("订阅的主题模式:")
            print("  - open-interest-data.>")
            print("  - open_interest-data.>")
            print("  - *.open-interest.*")
            print("  - *.open_interest.*")
            print("=" * 80)
            
        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    async def monitor(self, duration=300):  # 监控5分钟
        """监控指定时间"""
        print(f"⏰ 监控时间: {duration}秒 (等待Open Interest数据)")
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
            
            # 每30秒显示一次状态
            if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                print(f"📊 [{int(elapsed)}s] 已收到 {len(self.oi_messages)} 条Open Interest消息")
                
            await asyncio.sleep(1)
        
        # 显示最终统计
        print("\n" + "=" * 80)
        print("📊 Open Interest监控结果:")
        print("=" * 80)
        
        if self.oi_messages:
            print(f"✅ 成功收到 {len(self.oi_messages)} 条Open Interest消息")
            
            # 显示所有消息
            for i, msg in enumerate(self.oi_messages, 1):
                print(f"\n消息 {i}:")
                print(f"  时间: {msg['timestamp']}")
                print(f"  主题: {msg['subject']}")
                print(f"  交易所: {msg['data'].get('exchange', 'N/A')}")
                print(f"  交易对: {msg['data'].get('symbol', 'N/A')}")
                print(f"  未平仓量: {msg['data'].get('open_interest_value', 'N/A')}")
                print(f"  USD价值: {msg['data'].get('open_interest_usd', 'N/A')}")
        else:
            print("❌ 未收到任何Open Interest消息")
            print("\n可能的原因:")
            print("1. Open Interest数据还未到5分钟收集间隔")
            print("2. NATS主题名称与预期不符")
            print("3. Open Interest manager的NATS发布有问题")
            print("4. 数据处理过程中出现错误")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 NATS连接已关闭")

async def main():
    """主函数"""
    print("🔍 Open Interest NATS主题专门监控")
    print("=" * 80)
    
    monitor = OpenInterestNATSMonitor()
    
    # 连接NATS
    if not await monitor.connect():
        return
    
    try:
        # 订阅Open Interest主题
        await monitor.subscribe_oi_topics()
        
        # 监控5分钟（等待5分钟间隔的数据）
        await monitor.monitor(300)
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断监控")
    except Exception as e:
        print(f"❌ 监控过程中出错: {e}")
    finally:
        await monitor.close()

if __name__ == "__main__":
    asyncio.run(main())
