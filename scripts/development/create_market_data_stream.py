#!/usr/bin/env python3
"""
使用低级API直接创建NATS MARKET_DATA流
"""
import asyncio
import json
import os
import sys
import nats

# NATS服务器URL
NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")

async def create_market_data_stream():
    """
    使用原始JSON请求直接创建MARKET_DATA流
    通过直接发送JSON请求到NATS API，避开StreamConfig对象中可能存在的问题
    """
    try:
        print(f"连接到NATS服务器 {NATS_URL}...")
        nc = await nats.connect(NATS_URL)
        print("✓ 连接到NATS服务器成功")
        
        # 列出现有流
        js = nc.jetstream()
        try:
            streams = await js.streams_info()
            existing_streams = [stream.config.name for stream in streams]
            print(f"现有NATS流: {existing_streams}")
            
            # 检查是否已存在MARKET_DATA流
            if "MARKET_DATA" in existing_streams:
                print("MARKET_DATA流已存在，尝试删除...")
                try:
                    await js.delete_stream("MARKET_DATA")
                    print("✓ 成功删除MARKET_DATA流")
                except Exception as e:
                    print(f"× 删除MARKET_DATA流失败: {e}")
                    print("将尝试直接创建新流...")
        except Exception as e:
            print(f"获取流列表失败: {e}")
        
        # 直接使用NATS API创建流
        print("\n正在使用原始API创建MARKET_DATA流...")
        
        # 构建流配置JSON - 注意避免使用复杂的参数
        stream_config = {
            "name": "MARKET_DATA",
            "subjects": ["market.>"],
            "retention": "limits",
            "max_consumers": -1,
            "max_msgs": -1,
            "max_bytes": -1,
            "discard": "old",
            "max_age": 86400000000000,  # 24小时（纳秒）
            "storage": "file",
            "num_replicas": 1
        }
        
        # 直接发送API请求
        try:
            # 使用JetStream $JS.API.STREAM.CREATE.MARKET_DATA 主题
            resp = await nc.request(
                "$JS.API.STREAM.CREATE.MARKET_DATA",
                json.dumps(stream_config).encode(),
                timeout=10
            )
            
            response = json.loads(resp.data.decode())
            if response.get("type") == "io.nats.jetstream.api.v1.stream_create_response":
                print(f"✓ MARKET_DATA流创建成功!")
                print(f"  配置: {json.dumps(response.get('config', {}), indent=2)}")
            else:
                print(f"× 创建流失败: {json.dumps(response, indent=2)}")
        except Exception as e:
            print(f"× 使用API创建流失败: {e}")
            
            # 尝试第二种方法 - 使用nc.publish
            print("\n尝试使用publish方法创建流...")
            try:
                await nc.publish(
                    "$JS.API.STREAM.CREATE.MARKET_DATA",
                    json.dumps(stream_config).encode()
                )
                # 等待一会儿让操作完成
                await asyncio.sleep(1)
                
                # 检查流是否创建成功
                try:
                    stream_info = await js.stream_info("MARKET_DATA")
                    print(f"✓ MARKET_DATA流创建成功!")
                    print(f"  配置: {stream_info.config}")
                except Exception as check_e:
                    print(f"× 无法确认流是否创建成功: {check_e}")
            except Exception as pub_e:
                print(f"× 使用publish方法创建流失败: {pub_e}")
        
        # 列出当前所有流，验证创建结果
        print("\n验证MARKET_DATA流创建状态...")
        try:
            streams = await js.streams_info()
            stream_names = [stream.config.name for stream in streams]
            print(f"当前NATS流: {stream_names}")
            
            if "MARKET_DATA" in stream_names:
                # 获取详细信息
                market_data = await js.stream_info("MARKET_DATA")
                print(f"MARKET_DATA流信息:")
                print(f"  主题: {market_data.config.subjects}")
                print(f"  消息数: {market_data.state.messages}")
                print(f"  存储: {market_data.config.storage}")
                
                # 测试向MARKET_DATA流发布消息
                print("\n测试向MARKET_DATA流发布消息...")
                
                test_subject = "market.test"
                test_msg = {
                    "test": True,
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                }
                
                ack = await js.publish(test_subject, json.dumps(test_msg).encode())
                print(f"✓ 消息发布成功! 流: {ack.stream}, 序列号: {ack.seq}")
                
                # 成功!
                print("\n✓ MARKET_DATA流配置和测试成功!")
            else:
                print("× MARKET_DATA流创建失败，未在流列表中找到")
        except Exception as e:
            print(f"× 验证流状态失败: {e}")
        
        await nc.close()
        
    except Exception as e:
        print(f"× 操作失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(create_market_data_stream())
    sys.exit(exit_code) 