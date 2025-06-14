#!/usr/bin/env python3
"""
NATS架构验证脚本

快速验证MarketPrism NATS推送架构是否正常工作
"""

import asyncio
import sys
import time
from datetime import datetime
import json

try:
    import nats
    from nats.errors import TimeoutError, NoServersError
except ImportError:
    print("❌ 请安装nats-py: pip install nats-py")
    sys.exit(1)

class NATSSetupVerifier:
    """NATS架构设置验证器"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc = None
        self.js = None
        self.test_results = {}
        
    async def verify_all(self) -> bool:
        """执行完整验证"""
        print("🔍 MarketPrism NATS架构验证")
        print("=" * 50)
        
        tests = [
            ("NATS连接", self.test_nats_connection),
            ("JetStream功能", self.test_jetstream),
            ("流配置", self.test_stream_config),
            ("消息发布", self.test_message_publish),
            ("消息订阅", self.test_message_subscribe),
            ("推送器配置", self.test_publisher_config),
            ("系统资源", self.test_system_resources)
        ]
        
        all_passed = True
        
        for test_name, test_func in tests:
            print(f"\n📋 测试: {test_name}")
            try:
                result = await test_func()
                if result:
                    print(f"✅ {test_name}: 通过")
                    self.test_results[test_name] = "PASS"
                else:
                    print(f"❌ {test_name}: 失败")
                    self.test_results[test_name] = "FAIL"
                    all_passed = False
            except Exception as e:
                print(f"❌ {test_name}: 异常 - {e}")
                self.test_results[test_name] = f"ERROR: {e}"
                all_passed = False
        
        # 输出总结
        print(f"\n📊 验证总结")
        print("=" * 30)
        
        for test_name, result in self.test_results.items():
            status = "✅" if result == "PASS" else "❌"
            print(f"{status} {test_name}: {result}")
        
        if all_passed:
            print(f"\n🎉 所有测试通过！NATS架构配置正确")
            print(f"💡 下一步:")
            print(f"  1. 运行 'python demo_orderbook_nats_publisher.py' 启动演示")
            print(f"  2. 运行 'python example_nats_orderbook_consumer.py' 查看数据")
        else:
            print(f"\n⚠️ 部分测试失败，请检查配置")
            print(f"💡 故障排除:")
            print(f"  1. 确保NATS服务器运行: docker-compose -f docker-compose.infrastructure.yml up -d")
            print(f"  2. 检查网络连接: ping localhost")
            print(f"  3. 查看NATS日志: docker logs marketprism_nats_1")
        
        return all_passed
    
    async def test_nats_connection(self) -> bool:
        """测试NATS连接"""
        try:
            self.nc = await nats.connect(self.nats_url, connect_timeout=5)
            print(f"  • 连接地址: {self.nc.connected_url}")
            print(f"  • 服务器信息: {self.nc.server_info}")
            return True
        except NoServersError:
            print(f"  • 无法连接到NATS服务器: {self.nats_url}")
            return False
        except Exception as e:
            print(f"  • 连接异常: {e}")
            return False
    
    async def test_jetstream(self) -> bool:
        """测试JetStream功能"""
        if not self.nc:
            return False
        
        try:
            self.js = self.nc.jetstream()
            
            # 测试JetStream是否可用
            account_info = await self.js.account_info()
            print(f"  • JetStream账户: {account_info.domain or 'default'}")
            print(f"  • 内存使用: {account_info.memory}")
            print(f"  • 存储使用: {account_info.store}")
            
            return True
        except Exception as e:
            print(f"  • JetStream不可用: {e}")
            return False
    
    async def test_stream_config(self) -> bool:
        """测试流配置"""
        if not self.js:
            return False
        
        try:
            # 检查MARKET_DATA流是否存在
            try:
                stream_info = await self.js.stream_info("MARKET_DATA")
                print(f"  • 流名称: {stream_info.config.name}")
                print(f"  • 主题: {stream_info.config.subjects}")
                print(f"  • 消息数: {stream_info.state.messages}")
                print(f"  • 存储类型: {stream_info.config.storage}")
                return True
            except:
                # 流不存在，尝试创建
                print(f"  • MARKET_DATA流不存在，尝试创建...")
                
                from nats.js.api import StreamConfig
                config = StreamConfig(
                    name="MARKET_DATA",
                    subjects=["market.>"],
                    storage="memory",
                    max_msgs=100000,
                    max_age=3600  # 1小时
                )
                
                stream_info = await self.js.add_stream(config)
                print(f"  • 流创建成功: {stream_info.config.name}")
                return True
                
        except Exception as e:
            print(f"  • 流配置失败: {e}")
            return False
    
    async def test_message_publish(self) -> bool:
        """测试消息发布"""
        if not self.js:
            return False
        
        try:
            # 发布测试消息
            test_data = {
                "exchange_name": "test",
                "symbol_name": "TESTUSDT",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "test_message": True
            }
            
            subject = "market.test.TESTUSDT.orderbook"
            ack = await self.js.publish(subject, json.dumps(test_data).encode())
            
            print(f"  • 消息发布成功")
            print(f"  • 主题: {subject}")
            print(f"  • 序列号: {ack.seq}")
            print(f"  • 流: {ack.stream}")
            
            return True
        except Exception as e:
            print(f"  • 消息发布失败: {e}")
            return False
    
    async def test_message_subscribe(self) -> bool:
        """测试消息订阅"""
        if not self.nc:
            return False
        
        try:
            received_messages = []
            
            async def test_handler(msg):
                received_messages.append(msg)
            
            # 订阅测试主题
            sub = await self.nc.subscribe("market.test.*.orderbook", cb=test_handler)
            
            # 发布测试消息
            test_data = {"test": "subscription", "timestamp": time.time()}
            await self.nc.publish("market.test.TESTUSDT.orderbook", json.dumps(test_data).encode())
            
            # 等待消息接收
            await asyncio.sleep(1)
            
            # 取消订阅
            await sub.unsubscribe()
            
            if received_messages:
                print(f"  • 消息订阅成功")
                print(f"  • 接收消息数: {len(received_messages)}")
                return True
            else:
                print(f"  • 未接收到消息")
                return False
                
        except Exception as e:
            print(f"  • 消息订阅失败: {e}")
            return False
    
    async def test_publisher_config(self) -> bool:
        """测试推送器配置"""
        try:
            import os
            config_file = "config/orderbook_nats_publisher.yaml"
            
            if os.path.exists(config_file):
                print(f"  • 配置文件存在: {config_file}")
                
                # 检查配置文件内容
                with open(config_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                required_sections = ['nats:', 'orderbook_nats_publisher:', 'exchange:']
                missing_sections = []
                
                for section in required_sections:
                    if section not in content:
                        missing_sections.append(section)
                
                if missing_sections:
                    print(f"  • 缺少配置部分: {missing_sections}")
                    return False
                else:
                    print(f"  • 配置文件格式正确")
                    return True
            else:
                print(f"  • 配置文件不存在: {config_file}")
                return False
                
        except Exception as e:
            print(f"  • 配置检查失败: {e}")
            return False
    
    async def test_system_resources(self) -> bool:
        """测试系统资源"""
        try:
            import psutil
            
            # 检查内存
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            
            print(f"  • 可用内存: {available_gb:.1f} GB")
            
            if available_gb < 1:
                print(f"  • 警告: 可用内存不足1GB")
                return False
            
            # 检查磁盘空间
            disk = psutil.disk_usage('.')
            available_disk_gb = disk.free / (1024**3)
            
            print(f"  • 可用磁盘: {available_disk_gb:.1f} GB")
            
            if available_disk_gb < 5:
                print(f"  • 警告: 可用磁盘空间不足5GB")
                return False
            
            # 检查CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            print(f"  • CPU使用率: {cpu_percent:.1f}%")
            
            return True
            
        except ImportError:
            print(f"  • psutil未安装，跳过系统资源检查")
            return True
        except Exception as e:
            print(f"  • 系统资源检查失败: {e}")
            return False
    
    async def cleanup(self):
        """清理资源"""
        if self.nc:
            await self.nc.close()

async def main():
    """主函数"""
    print("🌟 MarketPrism NATS架构验证工具")
    print("本工具将验证NATS推送架构是否正确配置")
    print()
    
    # 获取NATS服务器地址
    nats_url = input("NATS服务器地址 (默认: nats://localhost:4222): ").strip()
    if not nats_url:
        nats_url = "nats://localhost:4222"
    
    verifier = NATSSetupVerifier(nats_url)
    
    try:
        success = await verifier.verify_all()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n⏹️ 验证被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 验证过程异常: {e}")
        return 1
    finally:
        await verifier.cleanup()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 