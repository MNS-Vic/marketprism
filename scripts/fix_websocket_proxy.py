#!/usr/bin/env python3
"""
WebSocket代理修复脚本

解决Binance WebSocket连接问题，使用SOCKS代理配置
"""

import asyncio
import websockets
import json
import time
import aiohttp
import socks
import socket
from typing import Dict, Any

# WebSocket SOCKS代理配置
WEBSOCKET_PROXY_CONFIG = {
    "socks_proxy": "127.0.0.1",
    "socks_port": 1080,
    "socks_type": socks.SOCKS5,  # 或者 socks.SOCKS4
    "http_proxy": "http://127.0.0.1:1087",
    "https_proxy": "http://127.0.0.1:1087"
}

class WebSocketProxyConnector:
    """WebSocket代理连接器"""
    
    def __init__(self):
        self.setup_socks_proxy()
    
    def setup_socks_proxy(self):
        """设置SOCKS代理"""
        try:
            # 设置默认SOCKS代理
            socks.set_default_proxy(
                WEBSOCKET_PROXY_CONFIG["socks_type"],
                WEBSOCKET_PROXY_CONFIG["socks_proxy"],
                WEBSOCKET_PROXY_CONFIG["socks_port"]
            )
            
            # 使socket模块使用代理
            socket.socket = socks.socksocket
            print(f"✅ SOCKS代理设置成功: {WEBSOCKET_PROXY_CONFIG['socks_proxy']}:{WEBSOCKET_PROXY_CONFIG['socks_port']}")
            
        except Exception as e:
            print(f"❌ SOCKS代理设置失败: {e}")
    
    async def test_binance_websocket_with_proxy(self) -> Dict[str, Any]:
        """使用代理测试Binance WebSocket"""
        print("🔌 测试Binance WebSocket (SOCKS代理)...")
        
        try:
            url = "wss://stream.binance.com:9443/ws/btcusdt@trade"
            start_time = time.time()
            
            # 设置WebSocket连接参数
            extra_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with websockets.connect(
                url,
                extra_headers=extra_headers,
                open_timeout=15,
                close_timeout=5,
                ping_interval=30,
                ping_timeout=10,
                max_size=2**20,  # 1MB
                max_queue=32
            ) as websocket:
                elapsed = (time.time() - start_time) * 1000
                print(f"   ✅ 连接建立成功 ({elapsed:.0f}ms)")
                
                # 等待消息
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                    data = json.loads(message)
                    
                    return {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': True,
                        'event_type': data.get('e', 'unknown'),
                        'symbol': data.get('s', 'unknown'),
                        'price': data.get('p', 'unknown')
                    }
                
                except asyncio.TimeoutError:
                    return {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': False,
                        'error': 'No message received within 10 seconds'
                    }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    async def test_okx_websocket_with_proxy(self) -> Dict[str, Any]:
        """使用代理测试OKX WebSocket"""
        print("🔌 测试OKX WebSocket (SOCKS代理)...")
        
        try:
            url = "wss://ws.okx.com:8443/ws/v5/public"
            start_time = time.time()
            
            # 设置WebSocket连接参数
            extra_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with websockets.connect(
                url,
                extra_headers=extra_headers,
                open_timeout=15,
                close_timeout=5,
                ping_interval=30,
                ping_timeout=10
            ) as websocket:
                elapsed = (time.time() - start_time) * 1000
                print(f"   ✅ 连接建立成功 ({elapsed:.0f}ms)")
                
                # 发送订阅消息
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{"channel": "trades", "instId": "BTC-USDT"}]
                }
                await websocket.send(json.dumps(subscribe_msg))
                print(f"   📤 发送订阅消息: {subscribe_msg}")
                
                # 等待响应
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                    data = json.loads(message)
                    
                    return {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': True,
                        'event_type': data.get('event', 'unknown'),
                        'code': data.get('code', 'unknown')
                    }
                
                except asyncio.TimeoutError:
                    return {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': False,
                        'error': 'No message received within 10 seconds'
                    }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }

    async def test_http_proxy_compatibility(self) -> Dict[str, Any]:
        """测试HTTP代理兼容性"""
        print("🌐 测试HTTP代理兼容性...")
        
        try:
            connector = aiohttp.TCPConnector(
                limit=100,
                ssl=False,
                use_dns_cache=True
            )
            
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                trust_env=True
            ) as session:
                
                # 测试Binance REST API
                url = "https://api.binance.com/api/v3/time"
                start_time = time.time()
                
                async with session.get(url) as response:
                    elapsed = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        return {
                            'success': True,
                            'response_time_ms': elapsed,
                            'server_time': data.get('serverTime'),
                            'proxy_working': True
                        }
                    else:
                        return {
                            'success': False,
                            'error': f'HTTP {response.status}',
                            'response_time_ms': elapsed
                        }
                        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }

async def main():
    """主测试函数"""
    print("🚀 WebSocket代理修复测试")
    print("="*60)
    
    connector = WebSocketProxyConnector()
    results = {}
    
    # 测试1: HTTP代理兼容性
    print("\n📋 测试1: HTTP代理兼容性")
    print("-"*40)
    http_result = await connector.test_http_proxy_compatibility()
    results['http_proxy'] = http_result
    
    if http_result.get('success'):
        print(f"   ✅ HTTP代理工作正常 ({http_result.get('response_time_ms', 0):.0f}ms)")
    else:
        print(f"   ❌ HTTP代理测试失败: {http_result.get('error')}")
    
    # 测试2: Binance WebSocket with SOCKS代理
    print("\n📋 测试2: Binance WebSocket")
    print("-"*40)
    binance_ws_result = await connector.test_binance_websocket_with_proxy()
    results['binance_ws'] = binance_ws_result
    
    if binance_ws_result.get('success'):
        if binance_ws_result.get('message_received'):
            print(f"   ✅ Binance WebSocket成功: 收到{binance_ws_result.get('event_type')}消息")
            print(f"      符号: {binance_ws_result.get('symbol')}, 价格: {binance_ws_result.get('price')}")
        else:
            print(f"   ⚠️ Binance WebSocket连接成功但未收到消息")
    else:
        print(f"   ❌ Binance WebSocket失败: {binance_ws_result.get('error')}")
    
    # 测试3: OKX WebSocket with SOCKS代理
    print("\n📋 测试3: OKX WebSocket")
    print("-"*40)
    okx_ws_result = await connector.test_okx_websocket_with_proxy()
    results['okx_ws'] = okx_ws_result
    
    if okx_ws_result.get('success'):
        if okx_ws_result.get('message_received'):
            print(f"   ✅ OKX WebSocket成功: 收到{okx_ws_result.get('event_type')}消息")
        else:
            print(f"   ⚠️ OKX WebSocket连接成功但未收到消息")
    else:
        print(f"   ❌ OKX WebSocket失败: {okx_ws_result.get('error')}")
    
    # 统计结果
    print("\n📊 测试结果统计")
    print("="*60)
    
    total_tests = len(results)
    successful_tests = sum(1 for r in results.values() if r.get('success', False))
    success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"成功率: {success_rate:.1f}% ({successful_tests}/{total_tests})")
    
    for test_name, result in results.items():
        status = "✅" if result.get('success') else "❌"
        print(f"  {status} {test_name}")
    
    # 保存结果
    result_file = f"websocket_proxy_test_{int(time.time())}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n📄 详细结果已保存到: {result_file}")
    
    return results

if __name__ == "__main__":
    # 需要安装: pip install PySocks
    try:
        asyncio.run(main())
    except ImportError as e:
        if "socks" in str(e):
            print("❌ 需要安装SOCKS支持: pip install PySocks")
        else:
            print(f"❌ 导入错误: {e}")
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")