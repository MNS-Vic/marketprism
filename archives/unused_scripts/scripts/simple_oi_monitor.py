#!/usr/bin/env python3
"""
简单的Open Interest NATS监控
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
except ImportError as e:
    print(f"❌ 无法导入NATS库: {e}")
    sys.exit(1)

async def message_handler(msg):
    """处理消息"""
    try:
        data = json.loads(msg.data.decode())
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"🎯 [{timestamp}] 收到Open Interest数据!")
        print(f"    主题: {msg.subject}")
        print(f"    交易所: {data.get('exchange', 'N/A')}")
        print(f"    交易对: {data.get('symbol', 'N/A')}")
        print(f"    未平仓量USD: {data.get('open_interest_usd', 'N/A')}")
        print("-" * 60)
        
    except Exception as e:
        print(f"❌ 处理消息错误: {e}")

async def main():
    """主函数"""
    print("🔍 简单Open Interest监控")
    print("=" * 60)
    
    try:
        # 连接NATS
        nc = await nats.connect("nats://localhost:4222")
        print("✅ 连接NATS成功")
        
        # 订阅所有可能的主题
        await nc.subscribe("open-interest.>", cb=message_handler)
        print("📡 已订阅Open Interest主题")
        
        # 等待10分钟
        print("⏰ 等待Open Interest数据...")
        await asyncio.sleep(600)
        
        await nc.close()
        print("🔌 连接已关闭")
        
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
