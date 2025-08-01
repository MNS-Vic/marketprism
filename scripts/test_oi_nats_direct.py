#!/usr/bin/env python3
"""
直接测试Open Interest NATS主题订阅
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

async def message_handler(msg):
    """处理消息"""
    try:
        data = json.loads(msg.data.decode())
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"🎯 [{timestamp}] 收到消息!")
        print(f"    主题: {msg.subject}")
        print(f"    数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
        print("-" * 80)
        
    except json.JSONDecodeError:
        print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] 无法解析JSON: {msg.subject}")
        print(f"    原始数据: {msg.data}")
    except Exception as e:
        print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] 处理消息错误: {e}")

async def main():
    """主函数"""
    print("🔍 直接测试Open Interest NATS主题")
    print("=" * 80)
    
    try:
        # 连接NATS
        nc = await nats.connect("nats://localhost:4222")
        print("✅ 成功连接到NATS服务器")
        
        # 订阅具体的主题
        expected_topics = [
            "open_interest-data.okx_derivatives.perpetual.BTC-USDT",
            "open_interest-data.binance_derivatives.perpetual.BTC-USDT",
            "open-interest-data.okx_derivatives.perpetual.BTC-USDT",
            "open-interest-data.binance_derivatives.perpetual.BTC-USDT"
        ]
        
        print("📡 订阅以下主题:")
        for topic in expected_topics:
            await nc.subscribe(topic, cb=message_handler)
            print(f"  - {topic}")
        
        # 也订阅通配符
        await nc.subscribe("*interest*", cb=message_handler)
        print(f"  - *interest* (通配符)")
        
        print("\n⏰ 等待Open Interest数据 (5分钟)...")
        print("=" * 80)
        
        # 等待5分钟
        await asyncio.sleep(300)
        
        print("\n⏹️ 监控结束")
        await nc.close()
        
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
