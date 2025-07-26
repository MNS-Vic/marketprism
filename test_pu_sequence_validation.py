#!/usr/bin/env python3
"""
测试Binance衍生品WebSocket Stream中的pu序列连续性
验证：当前event的pu值 == 上一条消息的u值
"""

import asyncio
import json
import time
import websockets
from datetime import datetime
from collections import deque

class PuSequenceValidator:
    """pu序列验证器"""
    
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.messages = deque(maxlen=200)
        self.sequence_errors = []
        self.running = False
        
    async def validate_sequence(self, duration=30):
        """验证序列连续性"""
        ws_url = f"wss://fstream.binance.com/ws/{self.symbol.lower()}@depth@100ms"
        
        print(f"🔗 连接WebSocket Stream: {ws_url}")
        print(f"⏱️  验证时长: {duration}秒")
        print(f"🎯 验证规则: 当前event的pu == 上一条消息的u")
        print("=" * 80)
        
        try:
            async with websockets.connect(ws_url) as websocket:
                self.running = True
                start_time = time.time()
                message_count = 0
                valid_sequences = 0
                invalid_sequences = 0
                
                prev_message = None
                
                while self.running and (time.time() - start_time) < duration:
                    try:
                        message_str = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        message = json.loads(message_str)
                        
                        message_count += 1
                        current_time = time.time()
                        message['received_at'] = current_time
                        
                        # 获取关键字段
                        U = message.get('U')
                        u = message.get('u')
                        pu = message.get('pu')
                        
                        # 验证序列连续性
                        if prev_message is not None:
                            prev_u = prev_message.get('u')
                            
                            if pu == prev_u:
                                valid_sequences += 1
                                status = "✅"
                            else:
                                invalid_sequences += 1
                                status = "❌"
                                
                                # 记录错误
                                error_info = {
                                    'message_num': message_count,
                                    'prev_u': prev_u,
                                    'current_pu': pu,
                                    'gap': pu - prev_u if prev_u and pu else None,
                                    'timestamp': current_time
                                }
                                self.sequence_errors.append(error_info)
                            
                            # 显示验证结果
                            if message_count <= 10 or message_count % 20 == 0 or status == "❌":
                                elapsed = current_time - start_time
                                print(f"{status} #{message_count:3d} | "
                                      f"⏱️ {elapsed:5.1f}s | "
                                      f"prev_u={prev_u} | "
                                      f"curr_pu={pu} | "
                                      f"U={U}, u={u}")
                                
                                if status == "❌":
                                    gap = pu - prev_u if prev_u and pu else "N/A"
                                    print(f"      ⚠️  序列不连续! gap={gap}")
                        else:
                            # 第一条消息
                            print(f"🚀 #{message_count:3d} | 首条消息 | U={U}, u={u}, pu={pu}")
                        
                        # 保存消息
                        self.messages.append(message)
                        prev_message = message
                        
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"❌ 接收消息异常: {e}")
                        break
                
                # 统计结果
                total_time = time.time() - start_time
                total_validations = valid_sequences + invalid_sequences
                
                print("\n" + "=" * 80)
                print("📊 序列连续性验证结果")
                print("=" * 80)
                print(f"总消息数: {message_count}")
                print(f"总验证数: {total_validations} (第一条消息不参与验证)")
                print(f"✅ 连续序列: {valid_sequences}")
                print(f"❌ 不连续序列: {invalid_sequences}")
                
                if total_validations > 0:
                    success_rate = (valid_sequences / total_validations) * 100
                    print(f"🎯 连续性成功率: {success_rate:.2f}%")
                
                print(f"⏱️  总时长: {total_time:.1f}秒")
                print(f"📈 消息频率: {message_count / total_time:.1f} 消息/秒")
                
                # 分析错误
                if self.sequence_errors:
                    print(f"\n❌ 发现 {len(self.sequence_errors)} 个序列不连续:")
                    print("-" * 60)
                    
                    for i, error in enumerate(self.sequence_errors[:10]):  # 只显示前10个错误
                        gap = error['gap']
                        print(f"  {i+1}. 消息#{error['message_num']}: "
                              f"prev_u={error['prev_u']}, curr_pu={error['current_pu']}, gap={gap}")
                    
                    if len(self.sequence_errors) > 10:
                        print(f"  ... 还有 {len(self.sequence_errors) - 10} 个错误")
                    
                    # 分析gap分布
                    gaps = [e['gap'] for e in self.sequence_errors if e['gap'] is not None]
                    if gaps:
                        print(f"\n📊 Gap分析:")
                        print(f"  平均gap: {sum(gaps) / len(gaps):.0f}")
                        print(f"  最小gap: {min(gaps)}")
                        print(f"  最大gap: {max(gaps)}")
                else:
                    print(f"\n🎉 完美！所有序列都是连续的！")
                
                return {
                    'total_messages': message_count,
                    'valid_sequences': valid_sequences,
                    'invalid_sequences': invalid_sequences,
                    'success_rate': (valid_sequences / total_validations * 100) if total_validations > 0 else 0,
                    'errors': self.sequence_errors
                }
                
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return None

async def main():
    """主函数"""
    print("🚀 Binance衍生品pu序列连续性验证测试")
    print("验证规则: 当前event的pu值 == 上一条消息的u值")
    print()
    
    validator = PuSequenceValidator("BTCUSDT")
    result = await validator.validate_sequence(30)
    
    if result:
        print(f"\n🏁 测试完成!")
        if result['success_rate'] >= 99:
            print(f"✅ 序列连续性优秀: {result['success_rate']:.2f}%")
        elif result['success_rate'] >= 95:
            print(f"⚠️  序列连续性良好: {result['success_rate']:.2f}%")
        else:
            print(f"❌ 序列连续性较差: {result['success_rate']:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
