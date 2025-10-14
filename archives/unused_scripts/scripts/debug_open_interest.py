#!/usr/bin/env python3
"""
调试Open Interest数据收集的脚本
专门检查为什么没有收到open_interest数据
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

class OpenInterestDebugger:
    def __init__(self):
        self.nc = None
        self.message_count = 0
        self.open_interest_count = 0
        self.funding_rate_count = 0
        self.liquidation_count = 0
        self.all_messages = []
        
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
        
        try:
            data = json.loads(msg.data.decode())
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # 提取关键信息
            exchange = data.get("exchange", "unknown")
            symbol = data.get("symbol", "unknown")
            data_type = data.get("data_type", "unknown")
            
            # 专门关注缺失的数据类型
            if data_type == "open_interest":
                self.open_interest_count += 1
                print(f"🎯 [{timestamp}] 发现OPEN_INTEREST数据!")
                print(f"    交易所: {exchange}")
                print(f"    交易对: {symbol}")
                print(f"    主题: {msg.subject}")
                print(f"    数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
                print("-" * 60)
                
            elif data_type == "funding_rate":
                self.funding_rate_count += 1
                print(f"💰 [{timestamp}] 发现FUNDING_RATE数据!")
                print(f"    交易所: {exchange}")
                print(f"    交易对: {symbol}")
                print(f"    主题: {msg.subject}")
                print(f"    资金费率: {data.get('funding_rate', 'N/A')}")
                print("-" * 60)
                
            elif data_type == "liquidation":
                self.liquidation_count += 1
                print(f"⚡ [{timestamp}] 发现LIQUIDATION数据!")
                print(f"    交易所: {exchange}")
                print(f"    交易对: {symbol}")
                print(f"    主题: {msg.subject}")
                print(f"    强平价格: {data.get('price', 'N/A')}")
                print(f"    强平数量: {data.get('quantity', 'N/A')}")
                print("-" * 60)
            
            # 存储所有消息用于分析
            self.all_messages.append({
                'timestamp': timestamp,
                'subject': msg.subject,
                'data_type': data_type,
                'exchange': exchange,
                'symbol': symbol
            })
            
            # 每100条消息显示一次统计
            if self.message_count % 100 == 0:
                print(f"📊 [{timestamp}] 统计: 总消息={self.message_count}, "
                      f"OI={self.open_interest_count}, FR={self.funding_rate_count}, "
                      f"LIQ={self.liquidation_count}")
                
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
            await self.nc.subscribe(">", cb=self.message_handler)
            print("🔍 开始专门监控Open Interest相关数据...")
            print("=" * 80)
            
        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    async def monitor(self, duration=120):  # 监控2分钟
        """监控指定时间"""
        print(f"⏰ 监控时间: {duration}秒 (专门等待Open Interest数据)")
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
                
            await asyncio.sleep(1)
        
        # 显示最终统计
        print("\n" + "=" * 80)
        print("🔍 Open Interest调试结果:")
        print("=" * 80)
        
        print(f"📊 统计结果:")
        print(f"  总消息数: {self.message_count}")
        print(f"  Open Interest消息: {self.open_interest_count}")
        print(f"  Funding Rate消息: {self.funding_rate_count}")
        print(f"  Liquidation消息: {self.liquidation_count}")
        
        # 分析主题分布
        subject_counts = {}
        data_type_counts = {}
        
        for msg in self.all_messages:
            subject_counts[msg['subject']] = subject_counts.get(msg['subject'], 0) + 1
            data_type_counts[msg['data_type']] = data_type_counts.get(msg['data_type'], 0) + 1
        
        print(f"\n📡 主题分布 (前10个):")
        for subject, count in sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {subject}: {count}条")
        
        print(f"\n📈 数据类型分布:")
        for data_type, count in sorted(data_type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {data_type}: {count}条")
        
        # 检查是否有相关主题但数据类型不匹配的情况
        oi_subjects = [msg for msg in self.all_messages if 'open-interest' in msg['subject']]
        fr_subjects = [msg for msg in self.all_messages if 'funding-rate' in msg['subject']]
        liq_subjects = [msg for msg in self.all_messages if 'liquidation' in msg['subject']]
        
        print(f"\n🔍 主题匹配分析:")
        print(f"  包含'open-interest'的主题: {len(oi_subjects)}个")
        print(f"  包含'funding-rate'的主题: {len(fr_subjects)}个")
        print(f"  包含'liquidation'的主题: {len(liq_subjects)}个")
        
        if oi_subjects:
            print(f"  Open Interest相关主题:")
            for msg in oi_subjects[:5]:  # 显示前5个
                print(f"    - {msg['subject']} (data_type: {msg['data_type']})")
        
        # 结论
        if self.open_interest_count == 0:
            print(f"\n❌ 未收到Open Interest数据的可能原因:")
            print(f"  1. Open Interest管理器未正确启动")
            print(f"  2. API请求失败或数据为空")
            print(f"  3. 数据处理或发布过程中出错")
            print(f"  4. 5分钟间隔内没有新数据")
            print(f"  5. 配置文件中未正确启用open_interest")
        else:
            print(f"\n✅ Open Interest数据收集正常!")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 NATS连接已关闭")

async def main():
    """主函数"""
    print("🔍 Open Interest数据调试工具")
    print("=" * 80)
    
    debugger = OpenInterestDebugger()
    
    # 连接NATS
    if not await debugger.connect():
        return
    
    try:
        # 订阅所有消息
        await debugger.subscribe_all()
        
        # 监控2分钟（等待5分钟间隔的数据）
        await debugger.monitor(120)
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断监控")
    except Exception as e:
        print(f"❌ 监控过程中出错: {e}")
    finally:
        await debugger.close()

if __name__ == "__main__":
    asyncio.run(main())
