#!/usr/bin/env python3
"""
调试Binance WebSocket消息格式
"""

import asyncio
import json
import websockets
from datetime import datetime

async def debug_binance_websocket():
    """调试Binance WebSocket消息"""
    print("🔍 调试Binance WebSocket消息格式")
    print("=" * 60)
    
    try:
        # 连接到Binance WebSocket
        uri = "wss://stream.binance.com:9443/ws"
        websocket = await websockets.connect(uri)
        print(f"✅ 已连接到: {uri}")
        
        # 订阅BTCUSDT订单簿数据
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": ["btcusdt@depth20@100ms"],
            "id": 1
        }
        
        await websocket.send(json.dumps(subscribe_msg))
        print(f"📊 已订阅: btcusdt@depth20@100ms")
        print("🔍 等待消息...")
        print("-" * 60)
        
        message_count = 0
        
        # 监听消息
        async for message in websocket:
            try:
                data = json.loads(message)
                message_count += 1
                
                print(f"\n📨 消息 #{message_count} ({datetime.now().strftime('%H:%M:%S')})")
                print(f"消息类型: {type(data)}")
                print(f"消息键: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
                
                # 详细分析消息结构
                if isinstance(data, dict):
                    if 'result' in data:
                        print("🔧 订阅确认消息:")
                        print(f"  result: {data.get('result')}")
                        print(f"  id: {data.get('id')}")
                        
                    elif 'stream' in data and 'data' in data:
                        print("📊 标准订单簿数据:")
                        stream = data['stream']
                        orderbook_data = data['data']
                        print(f"  stream: {stream}")
                        print(f"  data keys: {list(orderbook_data.keys())}")
                        
                        # 检查关键字段
                        if 'U' in orderbook_data and 'u' in orderbook_data:
                            print(f"  更新ID: U={orderbook_data['U']}, u={orderbook_data['u']}")
                        if 'pu' in orderbook_data:
                            print(f"  前一个更新ID: pu={orderbook_data['pu']}")
                        if 'b' in orderbook_data:
                            print(f"  bids数量: {len(orderbook_data['b'])}")
                        if 'a' in orderbook_data:
                            print(f"  asks数量: {len(orderbook_data['a'])}")
                            
                    elif 'e' in data:
                        print("📈 事件消息:")
                        print(f"  事件类型: {data.get('e')}")
                        print(f"  symbol: {data.get('s', 'N/A')}")
                        
                    else:
                        print("❓ 未知格式消息:")
                        print(f"  完整消息: {json.dumps(data, indent=2)[:500]}...")
                        
                else:
                    print(f"❓ 非字典消息: {str(data)[:200]}...")
                
                print("-" * 40)
                
                # 只显示前10条消息
                if message_count >= 10:
                    print("\n🛑 已收集10条消息，停止监听")
                    break
                    
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print(f"原始消息: {message[:200]}...")
            except Exception as e:
                print(f"❌ 处理消息失败: {e}")
        
        await websocket.close()
        print("\n🔌 WebSocket连接已关闭")
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(debug_binance_websocket())
    except KeyboardInterrupt:
        print("\n🛑 用户中断")
    except Exception as e:
        print(f"❌ 程序异常: {e}")
