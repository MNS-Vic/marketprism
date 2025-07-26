#!/usr/bin/env python3
"""
测试@depth@100ms订阅频率，检查是否能减少与WebSocket API的差距
"""

import asyncio
import json
import time
import websockets
from datetime import datetime
from collections import deque

class StreamFrequencyTest:
    """Stream频率测试"""
    
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.messages = deque(maxlen=100)
        self.running = False
        
    async def test_stream_frequency(self, stream_type="@depth@100ms", duration=10):
        """测试Stream频率"""
        ws_url = f"wss://fstream.binance.com/ws/{self.symbol.lower()}{stream_type}"
        
        print(f"🔗 测试Stream: {ws_url}")
        print(f"⏱️  测试时长: {duration}秒")
        print("-" * 60)
        
        try:
            async with websockets.connect(ws_url) as websocket:
                self.running = True
                start_time = time.time()
                message_count = 0
                
                while self.running and (time.time() - start_time) < duration:
                    try:
                        message_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        message = json.loads(message_str)
                        
                        message_count += 1
                        current_time = time.time()
                        
                        # 保存消息
                        message['received_at'] = current_time
                        self.messages.append(message)
                        
                        # 每秒显示一次统计
                        if message_count % 10 == 0 or message_count <= 5:
                            elapsed = current_time - start_time
                            rate = message_count / elapsed if elapsed > 0 else 0
                            
                            print(f"📊 {message_count:3d}条消息 | "
                                  f"⏱️ {elapsed:.1f}s | "
                                  f"📈 {rate:.1f}msg/s | "
                                  f"U={message.get('U', 'N/A')}, u={message.get('u', 'N/A')}")
                        
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"❌ 接收消息异常: {e}")
                        break
                
                # 统计结果
                total_time = time.time() - start_time
                avg_rate = message_count / total_time if total_time > 0 else 0
                
                print("-" * 60)
                print(f"📊 测试完成:")
                print(f"  总消息数: {message_count}")
                print(f"  总时长: {total_time:.1f}秒")
                print(f"  平均频率: {avg_rate:.1f}消息/秒")
                
                # 分析消息间隔
                if len(self.messages) >= 2:
                    intervals = []
                    messages_list = list(self.messages)
                    
                    for i in range(1, len(messages_list)):
                        interval = messages_list[i]['received_at'] - messages_list[i-1]['received_at']
                        intervals.append(interval * 1000)  # 转换为毫秒
                    
                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        min_interval = min(intervals)
                        max_interval = max(intervals)
                        
                        print(f"  消息间隔: 平均{avg_interval:.0f}ms, 范围{min_interval:.0f}-{max_interval:.0f}ms")
                
                return {
                    'message_count': message_count,
                    'duration': total_time,
                    'avg_rate': avg_rate,
                    'stream_type': stream_type
                }
                
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return None

async def compare_stream_types():
    """对比不同Stream类型的频率"""
    symbol = "BTCUSDT"
    duration = 15
    
    print("🚀 Binance衍生品Stream频率对比测试")
    print(f"测试交易对: {symbol}")
    print("=" * 80)
    
    # 测试不同的Stream类型
    stream_types = [
        "@depth",           # 原始格式
        "@depth@100ms",     # 100ms频率
    ]
    
    results = []
    
    for stream_type in stream_types:
        print(f"\n🔍 测试 {stream_type}")
        print("=" * 40)
        
        tester = StreamFrequencyTest(symbol)
        result = await tester.test_stream_frequency(stream_type, duration)
        
        if result:
            results.append(result)
        
        # 间隔2秒
        await asyncio.sleep(2)
    
    # 对比结果
    if len(results) >= 2:
        print("\n" + "=" * 80)
        print("📊 对比结果")
        print("=" * 80)
        
        for result in results:
            print(f"{result['stream_type']}:")
            print(f"  消息频率: {result['avg_rate']:.1f} 消息/秒")
            print(f"  总消息数: {result['message_count']}")
        
        # 计算改进
        if results[1]['avg_rate'] > results[0]['avg_rate']:
            improvement = (results[1]['avg_rate'] / results[0]['avg_rate'] - 1) * 100
            print(f"\n💡 @depth@100ms 比 @depth 频率提高了 {improvement:.1f}%")
        else:
            print(f"\n💡 两种格式频率相近")

async def main():
    """主函数"""
    await compare_stream_types()

if __name__ == "__main__":
    asyncio.run(main())
