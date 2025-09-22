#!/usr/bin/env python3
"""
MarketPrism Message Broker - Docker部署测试脚本
测试容器化版本的功能完整性和兼容性
"""

import asyncio
import aiohttp
import json
import time
import sys
from typing import Dict, Any, Optional


class DockerDeploymentTester:
    """Docker部署测试器"""
    
    def __init__(self):
        self.base_url = "http://localhost:8085"
        self.nats_monitor_url = "http://localhost:8222"
        self.test_results = {}
        
    async def run_all_tests(self) -> bool:
        """运行所有测试"""
        print("🧪 开始MarketPrism Message Broker Docker部署测试")
        print("=" * 60)
        
        tests = [
            ("健康检查测试", self.test_health_check),
            ("监控指标测试", self.test_metrics),
            ("状态信息测试", self.test_status),
            ("NATS连接测试", self.test_nats_connection),
            ("配置加载测试", self.test_configuration),
            ("环境变量测试", self.test_environment_variables),
        ]
        
        all_passed = True
        
        for test_name, test_func in tests:
            print(f"\n🔍 {test_name}...")
            try:
                result = await test_func()
                if result:
                    print(f"✅ {test_name} - 通过")
                    self.test_results[test_name] = "PASS"
                else:
                    print(f"❌ {test_name} - 失败")
                    self.test_results[test_name] = "FAIL"
                    all_passed = False
            except Exception as e:
                print(f"❌ {test_name} - 异常: {e}")
                self.test_results[test_name] = f"ERROR: {e}"
                all_passed = False
        
        # 显示测试总结
        self.print_test_summary()
        
        return all_passed
    
    async def test_health_check(self) -> bool:
        """测试健康检查端点"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 验证健康检查响应格式
                        required_fields = ['status', 'timestamp', 'version', 'nats_connected']
                        for field in required_fields:
                            if field not in data:
                                print(f"   ❌ 缺少字段: {field}")
                                return False
                        
                        if data['status'] == 'healthy':
                            print(f"   ✅ 服务状态: {data['status']}")
                            print(f"   ✅ NATS连接: {data['nats_connected']}")
                            print(f"   ✅ 版本: {data['version']}")
                            return True
                        else:
                            print(f"   ❌ 服务状态不健康: {data['status']}")
                            return False
                    else:
                        print(f"   ❌ HTTP状态码: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 连接失败: {e}")
            return False
    
    async def test_metrics(self) -> bool:
        """测试监控指标端点"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/metrics") as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 验证指标响应格式
                        required_fields = ['uptime_seconds', 'messages_processed', 'connections', 'errors']
                        for field in required_fields:
                            if field not in data:
                                print(f"   ❌ 缺少指标: {field}")
                                return False
                        
                        print(f"   ✅ 运行时间: {data['uptime_seconds']:.2f}秒")
                        print(f"   ✅ 处理消息数: {data['messages_processed']}")
                        print(f"   ✅ 连接数: {data['connections']}")
                        print(f"   ✅ 错误数: {data['errors']}")
                        return True
                    else:
                        print(f"   ❌ HTTP状态码: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 连接失败: {e}")
            return False
    
    async def test_status(self) -> bool:
        """测试状态信息端点"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/status") as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 验证状态响应格式
                        if 'service' not in data or 'mode' not in data or 'config' not in data:
                            print("   ❌ 状态响应格式不正确")
                            return False
                        
                        print(f"   ✅ 服务名称: {data['service']}")
                        print(f"   ✅ 运行模式: {data['mode']}")
                        print(f"   ✅ 运行状态: {data['is_running']}")
                        
                        config = data['config']
                        print(f"   ✅ NATS URL: {config.get('nats_url', 'N/A')}")
                        print(f"   ✅ 服务端口: {config.get('service_port', 'N/A')}")
                        print(f"   ✅ 环境: {config.get('environment', 'N/A')}")
                        
                        return True
                    else:
                        print(f"   ❌ HTTP状态码: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 连接失败: {e}")
            return False
    
    async def test_nats_connection(self) -> bool:
        """测试NATS连接"""
        try:
            async with aiohttp.ClientSession() as session:
                # 测试NATS监控端点
                async with session.get(f"{self.nats_monitor_url}/healthz") as response:
                    if response.status == 200:
                        print("   ✅ NATS服务器健康")
                    else:
                        print(f"   ❌ NATS服务器不健康: {response.status}")
                        return False
                
                # 测试JetStream状态
                async with session.get(f"{self.nats_monitor_url}/jsz") as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"   ✅ JetStream状态: {data.get('config', {}).get('store_dir', 'N/A')}")
                        print(f"   ✅ 流数量: {data.get('streams', 0)}")
                        print(f"   ✅ 消费者数量: {data.get('consumers', 0)}")
                        return True
                    else:
                        print(f"   ❌ JetStream状态获取失败: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ NATS连接测试失败: {e}")
            return False
    
    async def test_configuration(self) -> bool:
        """测试配置加载"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/status") as response:
                    if response.status == 200:
                        data = await response.json()
                        config = data.get('config', {})
                        
                        # 验证关键配置项
                        expected_configs = {
                            'nats_url': 'nats://nats:4222',
                            'service_port': 8085,
                            'environment': 'test',
                            'jetstream_enabled': True,
                            'lsr_enabled': True
                        }
                        
                        for key, expected_value in expected_configs.items():
                            actual_value = config.get(key)
                            if actual_value == expected_value:
                                print(f"   ✅ {key}: {actual_value}")
                            else:
                                print(f"   ❌ {key}: 期望 {expected_value}, 实际 {actual_value}")
                                return False
                        
                        return True
                    else:
                        print(f"   ❌ 无法获取配置: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 配置测试失败: {e}")
            return False
    
    async def test_environment_variables(self) -> bool:
        """测试环境变量配置"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/status") as response:
                    if response.status == 200:
                        data = await response.json()
                        config = data.get('config', {})
                        
                        # 验证环境变量是否正确应用
                        env_tests = [
                            ('environment', 'test'),
                            ('nats_url', 'nats://nats:4222'),
                            ('service_port', 8085)
                        ]
                        
                        for key, expected in env_tests:
                            actual = config.get(key)
                            if actual == expected:
                                print(f"   ✅ 环境变量 {key}: {actual}")
                            else:
                                print(f"   ❌ 环境变量 {key}: 期望 {expected}, 实际 {actual}")
                                return False
                        
                        return True
                    else:
                        print(f"   ❌ 无法获取状态: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 环境变量测试失败: {e}")
            return False
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("📊 测试总结")
        print("=" * 60)
        
        passed = sum(1 for result in self.test_results.values() if result == "PASS")
        total = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            status_icon = "✅" if result == "PASS" else "❌"
            print(f"{status_icon} {test_name}: {result}")
        
        print(f"\n📈 总体结果: {passed}/{total} 测试通过")
        
        if passed == total:
            print("🎉 所有测试通过！Docker部署成功！")
        else:
            print("⚠️ 部分测试失败，请检查配置和服务状态")


async def main():
    """主函数"""
    print("🐳 MarketPrism Message Broker Docker部署测试")
    print("等待服务启动...")
    
    # 等待服务启动
    await asyncio.sleep(10)
    
    tester = DockerDeploymentTester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 Docker部署测试完全成功！")
        return 0
    else:
        print("\n❌ Docker部署测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        sys.exit(1)
