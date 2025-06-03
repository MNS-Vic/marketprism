#!/usr/bin/env python3
"""
测试优化后的网络连接代码

验证：
1. 统一代理配置管理
2. WebSocket连接管理
3. HTTP会话管理
4. 网络连接管理器
"""

import asyncio
import sys
import os
import json
from typing import Dict, Any

# 添加项目路径
sys.path.append('/Users/yao/Documents/GitHub/marketprism')

from core.networking import (
    proxy_manager, websocket_manager, session_manager, network_manager,
    ProxyConfig, WebSocketConfig, SessionConfig, NetworkConfig
)

class NetworkingTester:
    """网络连接优化测试器"""
    
    def __init__(self):
        self.test_results = {}
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始测试优化后的网络连接代码")
        print("=" * 50)
        
        # 1. 测试代理配置管理
        print("\n📡 1. 测试代理配置管理")
        await self.test_proxy_manager()
        
        # 2. 测试WebSocket连接管理
        print("\n🔌 2. 测试WebSocket连接管理")
        await self.test_websocket_manager()
        
        # 3. 测试HTTP会话管理
        print("\n🌐 3. 测试HTTP会话管理")
        await self.test_session_manager()
        
        # 4. 测试网络连接管理器
        print("\n🎯 4. 测试网络连接管理器")
        await self.test_network_manager()
        
        # 5. 测试交易所连接
        print("\n🏪 5. 测试交易所连接")
        await self.test_exchange_connections()
        
        # 输出测试结果
        print("\n📊 测试结果总结")
        print("=" * 50)
        self.print_test_summary()
    
    async def test_proxy_manager(self):
        """测试代理配置管理"""
        try:
            # 测试环境变量代理配置
            proxy_config = proxy_manager.get_proxy_config()
            print(f"✅ 代理配置获取成功: {proxy_config.has_proxy()}")
            
            if proxy_config.has_proxy():
                print(f"  - HTTP代理: {proxy_config.get_http_proxy()}")
                print(f"  - SOCKS代理: {proxy_config.get_socks_proxy()}")
                print(f"  - aiohttp代理: {proxy_config.to_aiohttp_proxy()}")
            
            # 测试配置验证
            if proxy_config.get_http_proxy():
                is_valid = proxy_manager.validate_proxy_url(proxy_config.get_http_proxy())
                print(f"  - 代理URL验证: {is_valid}")
            
            self.test_results['proxy_manager'] = 'SUCCESS'
            
        except Exception as e:
            print(f"❌ 代理配置管理测试失败: {e}")
            self.test_results['proxy_manager'] = f'FAILED: {e}'
    
    async def test_websocket_manager(self):
        """测试WebSocket连接管理"""
        try:
            # 测试Deribit连接（之前成功的配置）
            config = WebSocketConfig(
                url="wss://www.deribit.com/ws/api/v2",
                timeout=10,
                ssl_verify=False,  # Deribit需要禁用SSL验证
                exchange_name="deribit"
            )
            
            print("  尝试连接Deribit WebSocket...")
            connection = await websocket_manager.connect(config)
            
            if connection:
                print("✅ WebSocket连接建立成功")
                
                # 发送测试消息
                test_message = {
                    "jsonrpc": "2.0",
                    "id": 9929,
                    "method": "public/get_time"
                }
                
                await connection.send(json.dumps(test_message))
                print("  - 测试消息发送成功")
                
                # 关闭连接
                await connection.close()
                print("  - 连接关闭成功")
                
                self.test_results['websocket_manager'] = 'SUCCESS'
            else:
                print("❌ WebSocket连接建立失败")
                self.test_results['websocket_manager'] = 'FAILED: 连接建立失败'
                
        except Exception as e:
            print(f"❌ WebSocket连接管理测试失败: {e}")
            self.test_results['websocket_manager'] = f'FAILED: {e}'
    
    async def test_session_manager(self):
        """测试HTTP会话管理"""
        try:
            # 创建测试会话
            session = await session_manager.get_session("test_session")
            print("✅ HTTP会话创建成功")
            
            # 测试HTTP请求
            response = await session_manager.request(
                'GET',
                'https://httpbin.org/get',
                session_name='test_session'
            )
            
            if response.status == 200:
                print(f"  - HTTP请求成功: {response.status}")
                response.close()
            else:
                print(f"  - HTTP请求失败: {response.status}")
            
            # 获取会话统计
            stats = session_manager.get_session_stats()
            print(f"  - 会话统计: {stats}")
            
            # 关闭会话
            await session_manager.close_session("test_session")
            print("  - 会话关闭成功")
            
            self.test_results['session_manager'] = 'SUCCESS'
            
        except Exception as e:
            print(f"❌ HTTP会话管理测试失败: {e}")
            self.test_results['session_manager'] = f'FAILED: {e}'
    
    async def test_network_manager(self):
        """测试网络连接管理器"""
        try:
            # 测试WebSocket连接创建
            ws_connection = await network_manager.create_websocket_connection(
                url="wss://www.deribit.com/ws/api/v2",
                exchange_name="deribit"
            )
            
            if ws_connection:
                print("✅ 网络管理器WebSocket连接成功")
            
            # 测试HTTP会话创建
            http_session = await network_manager.create_http_session(
                session_name="test_network",
                exchange_name="test"
            )
            
            if http_session:
                print("✅ 网络管理器HTTP会话创建成功")
            
            # 获取网络统计
            stats = network_manager.get_network_stats()
            print(f"  - 网络统计: {stats['overview']}")
            
            # 测试连接性
            connectivity_test = await network_manager.test_connectivity(
                url="wss://www.deribit.com/ws/api/v2",
                connection_type="websocket",
                exchange_name="deribit"
            )
            
            print(f"  - 连接性测试: {connectivity_test['success']}")
            
            # 关闭所有连接
            await network_manager.close_all_connections()
            print("  - 所有连接已关闭")
            
            self.test_results['network_manager'] = 'SUCCESS'
            
        except Exception as e:
            print(f"❌ 网络连接管理器测试失败: {e}")
            self.test_results['network_manager'] = f'FAILED: {e}'
    
    async def test_exchange_connections(self):
        """测试各个交易所连接"""
        exchanges = [
            ("Binance", "wss://stream.binance.com:9443/ws/btcusdt@ticker"),
            ("OKX", "wss://ws.okx.com:8443/ws/v5/public"),
            ("Deribit", "wss://www.deribit.com/ws/api/v2")
        ]
        
        results = {}
        
        for exchange_name, ws_url in exchanges:
            try:
                print(f"  测试 {exchange_name} 连接...")
                
                # 为不同交易所配置不同的SSL设置
                ssl_verify = exchange_name.lower() != "deribit"
                
                config = WebSocketConfig(
                    url=ws_url,
                    timeout=10,
                    ssl_verify=ssl_verify,
                    exchange_name=exchange_name.lower()
                )
                
                connection = await websocket_manager.connect(config)
                
                if connection:
                    print(f"    ✅ {exchange_name} WebSocket连接成功")
                    await connection.close()
                    results[exchange_name] = 'SUCCESS'
                else:
                    print(f"    ❌ {exchange_name} WebSocket连接失败")
                    results[exchange_name] = 'FAILED'
                
                # 短暂延迟避免连接过快
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"    ❌ {exchange_name} 连接测试失败: {e}")
                results[exchange_name] = f'FAILED: {e}'
        
        self.test_results['exchange_connections'] = results
    
    def print_test_summary(self):
        """打印测试结果总结"""
        total_tests = len(self.test_results)
        successful_tests = 0
        
        for test_name, result in self.test_results.items():
            if isinstance(result, dict):
                # 交易所连接测试结果
                success_count = sum(1 for r in result.values() if r == 'SUCCESS')
                total_count = len(result)
                
                print(f"📋 {test_name}: {success_count}/{total_count} 成功")
                for exchange, res in result.items():
                    status_icon = "✅" if res == 'SUCCESS' else "❌"
                    print(f"  {status_icon} {exchange}: {res}")
                
                if success_count == total_count:
                    successful_tests += 1
            else:
                status_icon = "✅" if result == 'SUCCESS' else "❌"
                print(f"📋 {test_name}: {status_icon} {result}")
                
                if result == 'SUCCESS':
                    successful_tests += 1
        
        print(f"\n🎯 总体结果: {successful_tests}/{total_tests} 项测试通过")
        
        if successful_tests == total_tests:
            print("🎉 所有测试通过！网络连接优化成功！")
        else:
            print("⚠️  部分测试失败，请检查相关配置")


async def main():
    """主函数"""
    tester = NetworkingTester()
    try:
        await tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n⏹️  测试被用户中断")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
    finally:
        # 确保清理所有连接
        try:
            await network_manager.close_all_connections()
            await session_manager.close_all_sessions()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())