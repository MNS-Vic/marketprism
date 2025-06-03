#!/usr/bin/env python3
"""
Deribit WebSocket连接优化测试

专门解决Deribit WebSocket连接问题，测试多种连接方法和代理配置
"""

import asyncio
import time
import json
import os
import sys
import ssl
from typing import Dict, List, Any, Optional
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

class DeribitWebSocketTester:
    """Deribit WebSocket连接测试器"""
    
    def __init__(self):
        self.test_results = []
        self.proxy_http = "http://127.0.0.1:1087"
        self.proxy_socks = "socks5://127.0.0.1:1080"
        
        # Deribit WebSocket URLs
        self.ws_urls = [
            "wss://www.deribit.com/ws/api/v2",
            "wss://test.deribit.com/ws/api/v2",  # 测试环境
            "wss://deribit.com/ws/api/v2",       # 备用域名
        ]
        
        # Deribit REST API URLs
        self.rest_urls = [
            "https://www.deribit.com/api/v2/public/get_time",
            "https://test.deribit.com/api/v2/public/get_time",
            "https://deribit.com/api/v2/public/get_time",
        ]
    
    async def test_rest_api_connections(self):
        """测试Deribit REST API连接"""
        print("🌐 测试Deribit REST API连接")
        print("=" * 60)
        
        for i, url in enumerate(self.rest_urls, 1):
            print(f"\n📡 测试 {i}: {url}")
            
            # 方法1: 显式代理
            success1 = await self._test_rest_with_explicit_proxy(url)
            
            # 方法2: 环境变量代理
            success2 = await self._test_rest_with_env_proxy(url)
            
            # 方法3: 无代理直连
            success3 = await self._test_rest_direct(url)
            
            result = {
                'url': url,
                'explicit_proxy': success1,
                'env_proxy': success2,
                'direct': success3,
                'any_success': success1 or success2 or success3
            }
            self.test_results.append(result)
            
            if result['any_success']:
                print(f"   ✅ REST API连接成功")
            else:
                print(f"   ❌ REST API连接失败")
    
    async def _test_rest_with_explicit_proxy(self, url: str) -> bool:
        """使用显式代理测试REST API"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, proxy=self.proxy_http) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"   ✅ 显式代理成功: {response.status}, 时间: {data.get('result', 'N/A')}")
                        return True
                    else:
                        print(f"   ❌ 显式代理失败: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 显式代理异常: {e}")
            return False
    
    async def _test_rest_with_env_proxy(self, url: str) -> bool:
        """使用环境变量代理测试REST API"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        print(f"   ✅ 环境变量代理成功: {response.status}")
                        return True
                    else:
                        print(f"   ❌ 环境变量代理失败: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 环境变量代理异常: {e}")
            return False
    
    async def _test_rest_direct(self, url: str) -> bool:
        """直连测试REST API"""
        try:
            # 临时清除代理环境变量
            old_http_proxy = os.environ.pop('http_proxy', None)
            old_https_proxy = os.environ.pop('https_proxy', None)
            old_all_proxy = os.environ.pop('ALL_PROXY', None)
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        print(f"   ✅ 直连成功: {response.status}")
                        return True
                    else:
                        print(f"   ❌ 直连失败: {response.status}")
                        return False
        except Exception as e:
            print(f"   ❌ 直连异常: {e}")
            return False
        finally:
            # 恢复代理环境变量
            if old_http_proxy:
                os.environ['http_proxy'] = old_http_proxy
            if old_https_proxy:
                os.environ['https_proxy'] = old_https_proxy
            if old_all_proxy:
                os.environ['ALL_PROXY'] = old_all_proxy
    
    async def test_websocket_connections(self):
        """测试Deribit WebSocket连接"""
        print("\n🔌 测试Deribit WebSocket连接")
        print("=" * 60)
        
        for i, url in enumerate(self.ws_urls, 1):
            print(f"\n📡 测试 {i}: {url}")
            
            # 方法1: 标准websockets库
            success1 = await self._test_websocket_standard(url)
            
            # 方法2: 使用aiohttp WebSocket
            success2 = await self._test_websocket_aiohttp(url)
            
            # 方法3: 自定义SSL上下文
            success3 = await self._test_websocket_custom_ssl(url)
            
            # 方法4: 禁用SSL验证
            success4 = await self._test_websocket_no_ssl(url)
            
            result = {
                'url': url,
                'standard': success1,
                'aiohttp': success2,
                'custom_ssl': success3,
                'no_ssl': success4,
                'any_success': success1 or success2 or success3 or success4
            }
            self.test_results.append(result)
            
            if result['any_success']:
                print(f"   ✅ WebSocket连接成功")
            else:
                print(f"   ❌ WebSocket连接失败")
    
    async def _test_websocket_standard(self, url: str) -> bool:
        """使用标准websockets库测试"""
        try:
            async with websockets.connect(
                url,
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                # 发送测试消息
                test_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "public/get_time",
                    "params": {}
                }
                await websocket.send(json.dumps(test_msg))
                
                # 等待响应
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(response)
                
                if 'result' in data:
                    print(f"   ✅ 标准websockets成功: 时间 {data['result']}")
                    return True
                else:
                    print(f"   ❌ 标准websockets响应异常: {data}")
                    return False
                    
        except Exception as e:
            print(f"   ❌ 标准websockets失败: {e}")
            return False
    
    async def _test_websocket_aiohttp(self, url: str) -> bool:
        """使用aiohttp WebSocket测试"""
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.ws_connect(
                    url,
                    proxy=self.proxy_http,
                    ssl=False  # 禁用SSL验证
                ) as ws:
                    # 发送测试消息
                    test_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "public/get_time",
                        "params": {}
                    }
                    await ws.send_str(json.dumps(test_msg))
                    
                    # 等待响应
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if 'result' in data:
                            print(f"   ✅ aiohttp WebSocket成功: 时间 {data['result']}")
                            return True
                        else:
                            print(f"   ❌ aiohttp WebSocket响应异常: {data}")
                            return False
                    else:
                        print(f"   ❌ aiohttp WebSocket消息类型异常: {msg.type}")
                        return False
                        
        except Exception as e:
            print(f"   ❌ aiohttp WebSocket失败: {e}")
            return False
    
    async def _test_websocket_custom_ssl(self, url: str) -> bool:
        """使用自定义SSL上下文测试"""
        try:
            # 创建自定义SSL上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            async with websockets.connect(
                url,
                ssl=ssl_context,
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                # 发送测试消息
                test_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "public/get_time",
                    "params": {}
                }
                await websocket.send(json.dumps(test_msg))
                
                # 等待响应
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(response)
                
                if 'result' in data:
                    print(f"   ✅ 自定义SSL成功: 时间 {data['result']}")
                    return True
                else:
                    print(f"   ❌ 自定义SSL响应异常: {data}")
                    return False
                    
        except Exception as e:
            print(f"   ❌ 自定义SSL失败: {e}")
            return False
    
    async def _test_websocket_no_ssl(self, url: str) -> bool:
        """禁用SSL验证测试"""
        try:
            # 将wss改为ws进行测试
            ws_url = url.replace('wss://', 'ws://')
            
            async with websockets.connect(
                ws_url,
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                # 发送测试消息
                test_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "public/get_time",
                    "params": {}
                }
                await websocket.send(json.dumps(test_msg))
                
                # 等待响应
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(response)
                
                if 'result' in data:
                    print(f"   ✅ 无SSL成功: 时间 {data['result']}")
                    return True
                else:
                    print(f"   ❌ 无SSL响应异常: {data}")
                    return False
                    
        except Exception as e:
            print(f"   ❌ 无SSL失败: {e}")
            return False
    
    async def test_deribit_subscription(self):
        """测试Deribit数据订阅"""
        print("\n📊 测试Deribit数据订阅")
        print("=" * 60)
        
        # 找到可用的WebSocket连接方法
        working_method = None
        working_url = None
        
        for result in self.test_results:
            if 'standard' in result and result['standard']:
                working_method = 'standard'
                working_url = result['url']
                break
            elif 'custom_ssl' in result and result['custom_ssl']:
                working_method = 'custom_ssl'
                working_url = result['url']
                break
        
        if not working_method:
            print("   ❌ 没有找到可用的WebSocket连接方法")
            return False
        
        print(f"   🔧 使用方法: {working_method}, URL: {working_url}")
        
        try:
            if working_method == 'standard':
                return await self._test_subscription_standard(working_url)
            elif working_method == 'custom_ssl':
                return await self._test_subscription_custom_ssl(working_url)
        except Exception as e:
            print(f"   ❌ 订阅测试失败: {e}")
            return False
    
    async def _test_subscription_standard(self, url: str) -> bool:
        """使用标准方法测试订阅"""
        try:
            async with websockets.connect(
                url,
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                # 订阅BTC永续合约交易数据
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "public/subscribe",
                    "params": {
                        "channels": ["trades.BTC-PERPETUAL.raw"]
                    }
                }
                await websocket.send(json.dumps(subscribe_msg))
                
                # 等待订阅确认
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(response)
                print(f"   📝 订阅响应: {data}")
                
                # 等待实时数据
                print("   ⏳ 等待实时交易数据...")
                message_count = 0
                start_time = time.time()
                
                while message_count < 5 and (time.time() - start_time) < 30:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5)
                        data = json.loads(message)
                        
                        if 'params' in data and 'data' in data['params']:
                            message_count += 1
                            trade_data = data['params']['data']
                            print(f"   📈 交易数据 {message_count}: 价格 {trade_data.get('price', 'N/A')}, 数量 {trade_data.get('amount', 'N/A')}")
                        
                    except asyncio.TimeoutError:
                        print("   ⏰ 等待数据超时")
                        break
                
                if message_count > 0:
                    print(f"   ✅ 成功接收 {message_count} 条实时交易数据")
                    return True
                else:
                    print("   ❌ 未接收到实时数据")
                    return False
                    
        except Exception as e:
            print(f"   ❌ 标准订阅测试失败: {e}")
            return False
    
    async def _test_subscription_custom_ssl(self, url: str) -> bool:
        """使用自定义SSL方法测试订阅"""
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            async with websockets.connect(
                url,
                ssl=ssl_context,
                open_timeout=10,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                # 订阅BTC永续合约交易数据
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "public/subscribe",
                    "params": {
                        "channels": ["trades.BTC-PERPETUAL.raw"]
                    }
                }
                await websocket.send(json.dumps(subscribe_msg))
                
                # 等待订阅确认
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(response)
                print(f"   📝 订阅响应: {data}")
                
                # 等待实时数据
                print("   ⏳ 等待实时交易数据...")
                message_count = 0
                start_time = time.time()
                
                while message_count < 5 and (time.time() - start_time) < 30:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5)
                        data = json.loads(message)
                        
                        if 'params' in data and 'data' in data['params']:
                            message_count += 1
                            trade_data = data['params']['data']
                            print(f"   📈 交易数据 {message_count}: 价格 {trade_data.get('price', 'N/A')}, 数量 {trade_data.get('amount', 'N/A')}")
                        
                    except asyncio.TimeoutError:
                        print("   ⏰ 等待数据超时")
                        break
                
                if message_count > 0:
                    print(f"   ✅ 成功接收 {message_count} 条实时交易数据")
                    return True
                else:
                    print("   ❌ 未接收到实时数据")
                    return False
                    
        except Exception as e:
            print(f"   ❌ 自定义SSL订阅测试失败: {e}")
            return False
    
    def generate_report(self):
        """生成测试报告"""
        print("\n📊 Deribit连接优化测试报告")
        print("=" * 80)
        
        # 统计成功率
        rest_success = sum(1 for r in self.test_results if 'any_success' in r and r['any_success'] and 'api' in r['url'])
        ws_success = sum(1 for r in self.test_results if 'any_success' in r and r['any_success'] and 'ws' in r['url'])
        
        total_rest = len([r for r in self.test_results if 'api' in r['url']])
        total_ws = len([r for r in self.test_results if 'ws' in r['url']])
        
        print(f"📈 REST API连接成功率: {rest_success}/{total_rest} ({rest_success/max(total_rest,1)*100:.1f}%)")
        print(f"🔌 WebSocket连接成功率: {ws_success}/{total_ws} ({ws_success/max(total_ws,1)*100:.1f}%)")
        
        # 详细结果
        print(f"\n📋 详细测试结果:")
        for result in self.test_results:
            url = result['url']
            if 'api' in url:
                print(f"   REST: {url}")
                print(f"      显式代理: {'✅' if result.get('explicit_proxy') else '❌'}")
                print(f"      环境代理: {'✅' if result.get('env_proxy') else '❌'}")
                print(f"      直连: {'✅' if result.get('direct') else '❌'}")
            elif 'ws' in url:
                print(f"   WebSocket: {url}")
                print(f"      标准方法: {'✅' if result.get('standard') else '❌'}")
                print(f"      aiohttp: {'✅' if result.get('aiohttp') else '❌'}")
                print(f"      自定义SSL: {'✅' if result.get('custom_ssl') else '❌'}")
                print(f"      无SSL: {'✅' if result.get('no_ssl') else '❌'}")
        
        # 推荐方案
        print(f"\n💡 推荐解决方案:")
        
        # 找到最佳REST方法
        best_rest_method = None
        for result in self.test_results:
            if 'api' in result['url'] and result.get('any_success'):
                if result.get('explicit_proxy'):
                    best_rest_method = "显式代理"
                elif result.get('env_proxy'):
                    best_rest_method = "环境变量代理"
                elif result.get('direct'):
                    best_rest_method = "直连"
                break
        
        # 找到最佳WebSocket方法
        best_ws_method = None
        for result in self.test_results:
            if 'ws' in result['url'] and result.get('any_success'):
                if result.get('standard'):
                    best_ws_method = "标准websockets库"
                elif result.get('custom_ssl'):
                    best_ws_method = "自定义SSL上下文"
                elif result.get('aiohttp'):
                    best_ws_method = "aiohttp WebSocket"
                elif result.get('no_ssl'):
                    best_ws_method = "禁用SSL验证"
                break
        
        if best_rest_method:
            print(f"   🌐 REST API推荐方法: {best_rest_method}")
        else:
            print(f"   ❌ REST API: 所有方法都失败，需要检查网络配置")
        
        if best_ws_method:
            print(f"   🔌 WebSocket推荐方法: {best_ws_method}")
        else:
            print(f"   ❌ WebSocket: 所有方法都失败，需要检查防火墙和代理配置")
        
        # 保存结果到文件
        result_file = f"deribit_connection_test_result_{int(time.time())}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细结果已保存到: {result_file}")


async def main():
    """主函数"""
    print("🚀 Deribit WebSocket连接优化测试")
    print("=" * 80)
    
    # 显示当前环境
    print(f"🔧 当前代理设置:")
    print(f"   http_proxy: {os.getenv('http_proxy', '未设置')}")
    print(f"   https_proxy: {os.getenv('https_proxy', '未设置')}")
    print(f"   ALL_PROXY: {os.getenv('ALL_PROXY', '未设置')}")
    print()
    
    # 创建测试器
    tester = DeribitWebSocketTester()
    
    try:
        # 测试REST API连接
        await tester.test_rest_api_connections()
        
        # 测试WebSocket连接
        await tester.test_websocket_connections()
        
        # 测试数据订阅
        await tester.test_deribit_subscription()
        
        # 生成报告
        tester.generate_report()
        
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())