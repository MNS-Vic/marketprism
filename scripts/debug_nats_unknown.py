#!/usr/bin/env python3
"""
调试NATS UNKNOWN消息的脚本
专门用于分析为什么会出现UNKNOWN数据类型
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

class NATSDebugger:
    def __init__(self):
        self.nc = None
        self.message_count = 0
        self.unknown_count = 0
        self.known_count = 0
        self.data_types_seen = set()
        self.unknown_messages = []
        
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
        
        # 解析消息数据
        try:
            data = json.loads(msg.data.decode())
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # 提取数据类型
            data_type = data.get("data_type", "MISSING")
            
            # 检查是否为已知数据类型
            known_types = {
                "orderbook", "trade", "funding_rate", "open_interest",
                "liquidation", "lsr_top_position", "lsr_all_account",
                "volatility_index", "ticker",
                # 兼容枚举字符串表示形式
                "DataType.ORDERBOOK", "DataType.TRADE", "DataType.FUNDING_RATE",
                "DataType.OPEN_INTEREST", "DataType.LIQUIDATION", "DataType.LSR_TOP_POSITION",
                "DataType.LSR_ALL_ACCOUNT", "DataType.VOLATILITY_INDEX", "DataType.TICKER"
            }
            
            if data_type in known_types:
                self.known_count += 1
                self.data_types_seen.add(data_type)
                # 只显示简要信息
                if self.known_count % 50 == 0:  # 每50条显示一次统计
                    print(f"✅ [{timestamp}] 已知类型: {data_type} (总计: {self.known_count})")
            else:
                self.unknown_count += 1
                print(f"❓ [{timestamp}] UNKNOWN消息 #{self.unknown_count}")
                print(f"   主题: {msg.subject}")
                print(f"   data_type字段: {data_type}")
                
                # 显示消息的所有顶级字段
                print(f"   消息字段: {list(data.keys())}")
                
                # 显示部分消息内容（限制长度）
                data_str = json.dumps(data, ensure_ascii=False, indent=2)
                if len(data_str) > 500:
                    data_str = data_str[:500] + "..."
                print(f"   消息内容: {data_str}")
                print("-" * 60)
                
                # 保存前10个UNKNOWN消息用于分析
                if len(self.unknown_messages) < 10:
                    self.unknown_messages.append({
                        'subject': msg.subject,
                        'data': data,
                        'timestamp': timestamp
                    })
                
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
            print("🔍 开始调试NATS消息...")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    async def monitor(self, duration=30):
        """监控指定时间"""
        print(f"⏰ 调试监控时间: {duration}秒")
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
                
            await asyncio.sleep(1)
        
        # 显示详细统计信息
        print("\n" + "=" * 60)
        print("🔍 调试统计结果:")
        print(f"  总消息数: {self.message_count}")
        print(f"  已知类型消息: {self.known_count}")
        print(f"  UNKNOWN消息: {self.unknown_count}")
        print(f"  UNKNOWN比例: {self.unknown_count/self.message_count*100:.1f}%")
        print(f"  发现的数据类型: {', '.join(sorted(self.data_types_seen))}")
        
        # 分析UNKNOWN消息的模式
        if self.unknown_messages:
            print(f"\n📊 UNKNOWN消息分析 (前{len(self.unknown_messages)}条):")
            
            # 按主题分组
            subjects = {}
            data_type_values = {}
            
            for msg in self.unknown_messages:
                subject = msg['subject']
                data_type = msg['data'].get('data_type', 'MISSING')
                
                subjects[subject] = subjects.get(subject, 0) + 1
                data_type_values[data_type] = data_type_values.get(data_type, 0) + 1
            
            print("  主题分布:")
            for subject, count in subjects.items():
                print(f"    - {subject}: {count}次")
                
            print("  data_type值分布:")
            for dt, count in data_type_values.items():
                print(f"    - '{dt}': {count}次")
                
            # 显示第一个UNKNOWN消息的完整内容
            print(f"\n📝 第一个UNKNOWN消息详情:")
            first_msg = self.unknown_messages[0]
            print(f"  主题: {first_msg['subject']}")
            print(f"  时间: {first_msg['timestamp']}")
            print(f"  内容: {json.dumps(first_msg['data'], ensure_ascii=False, indent=2)}")
        
        if self.unknown_count == 0:
            print("🎉 没有发现UNKNOWN消息，所有消息都被正确识别！")
        else:
            print(f"\n💡 建议:")
            print("1. 检查数据发布代码是否正确设置data_type字段")
            print("2. 确认所有数据类型都在监控脚本的已知类型列表中")
            print("3. 检查是否有其他服务也在向NATS发布消息")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 NATS连接已关闭")

async def main():
    """主函数"""
    print("🔍 NATS UNKNOWN消息调试工具")
    print("=" * 60)
    
    debugger = NATSDebugger()
    
    # 连接NATS
    if not await debugger.connect():
        return
    
    try:
        # 订阅所有消息
        await debugger.subscribe_all()
        
        # 监控30秒
        await debugger.monitor(30)
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断调试")
    except Exception as e:
        print(f"❌ 调试过程中出错: {e}")
    finally:
        await debugger.close()

if __name__ == "__main__":
    asyncio.run(main())
