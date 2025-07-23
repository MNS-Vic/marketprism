#!/usr/bin/env python3
"""
NATS连接测试脚本
验证NATS服务器是否正常运行并可连接
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

try:
    import nats
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False


async def test_nats_connection():
    """测试NATS连接"""
    print("🧪 测试NATS连接")
    print("="*50)
    
    if not NATS_AVAILABLE:
        print("❌ NATS客户端不可用，请安装: pip install nats-py")
        return False
    
    try:
        # 连接到NATS服务器
        print("🔌 尝试连接到NATS服务器 (localhost:4222)...")
        nc = await nats.connect("nats://localhost:4222")
        
        print("✅ NATS连接成功！")
        
        # 测试发布和订阅
        print("📤 测试消息发布和订阅...")
        
        received_messages = []
        
        async def message_handler(msg):
            subject = msg.subject
            data = msg.data.decode()
            print(f"📨 收到消息: {subject} -> {data}")
            received_messages.append((subject, data))
        
        # 订阅测试主题
        await nc.subscribe("test.marketprism", cb=message_handler)
        
        # 发布测试消息
        await nc.publish("test.marketprism", b"Hello MarketPrism!")
        
        # 等待消息处理
        await asyncio.sleep(0.5)
        
        # 验证消息接收
        if received_messages:
            print("✅ 消息发布和订阅测试通过")
            print(f"   收到 {len(received_messages)} 条消息")
        else:
            print("❌ 消息发布和订阅测试失败")
            return False
        
        # 测试JetStream（如果可用）
        print("🚀 测试JetStream功能...")
        try:
            js = nc.jetstream()
            
            # 创建测试流
            stream_config = {
                "name": "TEST_STREAM",
                "subjects": ["test.jetstream.>"],
                "retention": "limits",
                "max_msgs": 1000,
                "max_bytes": 1024*1024,  # 1MB
                "max_age": 3600,  # 1小时
            }
            
            try:
                await js.add_stream(**stream_config)
                print("✅ JetStream流创建成功")
            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    print("✅ JetStream流已存在")
                else:
                    print(f"⚠️ JetStream流创建失败: {e}")
            
            # 发布到JetStream
            ack = await js.publish("test.jetstream.data", b"JetStream test message")
            print(f"✅ JetStream消息发布成功: {ack}")
            
        except Exception as e:
            print(f"⚠️ JetStream测试失败: {e}")
            print("   这可能是因为NATS服务器未启用JetStream")
        
        # 关闭连接
        await nc.close()
        print("✅ NATS连接已关闭")
        
        return True
        
    except Exception as e:
        print(f"❌ NATS连接测试失败: {e}")
        return False


async def test_nats_config():
    """测试NATS配置"""
    print("\n🧪 测试NATS配置")
    print("="*50)
    
    try:
        from collector.nats_publisher import NATSConfig, create_nats_config_from_yaml
        import yaml
        
        # 加载配置文件
        config_path = "../../config/collector/unified_data_collection.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 创建NATS配置
        nats_config = create_nats_config_from_yaml(config)
        
        print("✅ NATS配置创建成功")
        print(f"   服务器: {nats_config.servers}")
        print(f"   客户端名称: {nats_config.client_name}")
        print(f"   最大重连次数: {nats_config.max_reconnect_attempts}")
        print(f"   启用JetStream: {nats_config.enable_jetstream}")
        
        if nats_config.streams:
            print(f"   配置的流:")
            for stream_name, stream_config in nats_config.streams.items():
                print(f"     - {stream_name}: {stream_config['subjects']}")
        
        return True
        
    except Exception as e:
        print(f"❌ NATS配置测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("🚀 MarketPrism NATS连接测试")
    print("验证NATS服务器状态和连接功能")
    print("="*80)
    
    try:
        # 测试NATS连接
        connection_success = await test_nats_connection()
        
        # 测试NATS配置
        config_success = await test_nats_config()
        
        # 显示总结
        print(f"\n📊 测试结果总结:")
        print(f"🔌 NATS连接测试: {'✅ 通过' if connection_success else '❌ 失败'}")
        print(f"⚙️ NATS配置测试: {'✅ 通过' if config_success else '❌ 失败'}")
        
        if connection_success and config_success:
            print("\n🎉 所有NATS测试通过！")
            print("✅ NATS服务器正常运行")
            print("✅ 连接和消息传递功能正常")
            print("✅ 配置文件解析正确")
            print("✅ 准备好进行统一数据收集器测试")
            return True
        else:
            print("\n⚠️ NATS测试存在问题")
            if not connection_success:
                print("❌ NATS服务器连接失败")
                print("   请检查NATS服务器是否在localhost:4222运行")
            if not config_success:
                print("❌ NATS配置解析失败")
                print("   请检查配置文件格式")
            return False
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
