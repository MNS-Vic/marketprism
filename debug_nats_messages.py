#!/usr/bin/env python3
"""
调试NATS消息格式
"""

import asyncio
import nats
import json

async def debug_nats_messages():
    nc = await nats.connect('nats://localhost:4222')
    
    print('🔍 调试NATS消息格式...')
    print()
    
    count = 0
    
    async def message_handler(msg):
        nonlocal count
        count += 1
        
        print(f"=== 消息 {count} ===")
        print(f"主题: {msg.subject}")
        print(f"数据长度: {len(msg.data)} 字节")
        print(f"原始数据: {msg.data}")
        
        try:
            # 尝试解码为字符串
            text_data = msg.data.decode('utf-8')
            print(f"文本数据: {text_data[:200]}...")
            
            # 尝试解析为JSON
            json_data = json.loads(text_data)
            print(f"JSON解析成功!")
            print(f"数据类型: {type(json_data)}")
            
            if isinstance(json_data, dict):
                print(f"字段: {list(json_data.keys())}")
                if 'bids' in json_data:
                    print(f"bids数组长度: {len(json_data['bids'])}")
                    if len(json_data['bids']) > 0:
                        print(f"第一个bid类型: {type(json_data['bids'][0])}")
                        print(f"第一个bid内容: {json_data['bids'][0]}")
                        if hasattr(json_data['bids'][0], '__dict__'):
                            print(f"第一个bid属性: {json_data['bids'][0].__dict__}")
                if 'asks' in json_data:
                    print(f"asks数组长度: {len(json_data['asks'])}")
                    if len(json_data['asks']) > 0:
                        print(f"第一个ask类型: {type(json_data['asks'][0])}")
                        print(f"第一个ask内容: {json_data['asks'][0]}")
                        if hasattr(json_data['asks'][0], '__dict__'):
                            print(f"第一个ask属性: {json_data['asks'][0].__dict__}")
            
        except UnicodeDecodeError as e:
            print(f"❌ 解码错误: {e}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析错误: {e}")
        except Exception as e:
            print(f"❌ 其他错误: {e}")
        
        print()
        
        if count >= 5:
            await nc.close()
    
    await nc.subscribe('orderbook-data.>', cb=message_handler)
    await asyncio.sleep(30)
    await nc.close()
    
    if count == 0:
        print('❌ 没有收到任何消息')

if __name__ == "__main__":
    asyncio.run(debug_nats_messages())
