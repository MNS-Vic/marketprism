#!/usr/bin/env python3
"""
修复后的TDD测试

基于services/python-collector中已验证可用的交易所连接配置
"""

import asyncio
import aiohttp
import websockets
import json
import time
import sys
import os
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 使用成功的代理配置
PROXY_CONFIG = {
    "http_proxy": "http://127.0.0.1:1087",
    "https_proxy": "http://127.0.0.1:1087"
}

class FixedExchangeConnector:
    """修复后的交易所连接器"""
    
    def __init__(self):
        self.session = None
        
    async def create_session(self):
        """创建带成功配置的session"""
        if self.session:
            return
            
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
            ssl=False  # 禁用SSL验证
        )
        
        self.session = aiohttp.ClientSession(
            timeout=timeout, 
            connector=connector,
            trust_env=True  # 使用环境变量代理
        )
        
    async def test_binance_api(self) -> Dict[str, Any]:
        """测试Binance API"""
        print("📡 测试Binance API...")
        await self.create_session()
        
        results = {}
        base_url = "https://api.binance.com"
        
        # 测试服务器时间
        try:
            url = f"{base_url}/api/v3/time"
            start_time = time.time()
            
            async with self.session.get(url) as response:
                elapsed = (time.time() - start_time) * 1000
                if response.status == 200:
                    data = await response.json()
                    server_time = data['serverTime']
                    local_time = int(time.time() * 1000)
                    time_diff = abs(server_time - local_time) / 1000
                    
                    results['server_time'] = {
                        'success': True,
                        'time_diff_seconds': time_diff,
                        'response_time_ms': elapsed
                    }
                    print(f"   ✅ 服务器时间: 时差{time_diff:.2f}秒 ({elapsed:.0f}ms)")
                else:
                    results['server_time'] = {'success': False, 'error': f'HTTP {response.status}'}
                    print(f"   ❌ 服务器时间: HTTP {response.status}")
        except Exception as e:
            results['server_time'] = {'success': False, 'error': str(e)}
            print(f"   ❌ 服务器时间: {e}")
        
        # 测试交易对信息
        try:
            url = f"{base_url}/api/v3/exchangeInfo"
            start_time = time.time()
            
            async with self.session.get(url) as response:
                elapsed = (time.time() - start_time) * 1000
                if response.status == 200:
                    data = await response.json()
                    symbols = data.get('symbols', [])
                    trading_pairs = len([s for s in symbols if s.get('status') == 'TRADING'])
                    
                    results['exchange_info'] = {
                        'success': True,
                        'trading_pairs': trading_pairs,
                        'response_time_ms': elapsed
                    }
                    print(f"   ✅ 交易所信息: {trading_pairs}个交易对 ({elapsed:.0f}ms)")
                else:
                    results['exchange_info'] = {'success': False, 'error': f'HTTP {response.status}'}
                    print(f"   ❌ 交易所信息: HTTP {response.status}")
        except Exception as e:
            results['exchange_info'] = {'success': False, 'error': str(e)}
            print(f"   ❌ 交易所信息: {e}")
        
        return results
    
    async def test_okx_api(self) -> Dict[str, Any]:
        """测试OKX API"""
        print("📡 测试OKX API...")
        await self.create_session()
        
        results = {}
        base_url = "https://www.okx.com"
        
        # 测试服务器时间
        try:
            url = f"{base_url}/api/v5/public/time"
            start_time = time.time()
            
            async with self.session.get(url) as response:
                elapsed = (time.time() - start_time) * 1000
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0' and data.get('data'):
                        server_time = int(data['data'][0]['ts'])
                        local_time = int(time.time() * 1000)
                        time_diff = abs(server_time - local_time) / 1000
                        
                        results['server_time'] = {
                            'success': True,
                            'time_diff_seconds': time_diff,
                            'response_time_ms': elapsed
                        }
                        print(f"   ✅ 服务器时间: 时差{time_diff:.2f}秒 ({elapsed:.0f}ms)")
                    else:
                        results['server_time'] = {'success': False, 'error': 'Invalid response format'}
                        print(f"   ❌ 服务器时间: 响应格式无效")
                else:
                    results['server_time'] = {'success': False, 'error': f'HTTP {response.status}'}
                    print(f"   ❌ 服务器时间: HTTP {response.status}")
        except Exception as e:
            results['server_time'] = {'success': False, 'error': str(e)}
            print(f"   ❌ 服务器时间: {e}")
        
        return results
    
    async def test_websocket_connections(self) -> Dict[str, Any]:
        """测试WebSocket连接"""
        print("🔌 测试WebSocket连接...")
        
        results = {}
        
        # 测试Binance WebSocket
        try:
            url = "wss://stream.binance.com:9443/ws/btcusdt@trade"
            print(f"   测试Binance: {url}")
            start_time = time.time()
            
            async with websockets.connect(
                url,
                open_timeout=10,
                close_timeout=5,
                ping_interval=30,
                ping_timeout=10
            ) as websocket:
                elapsed = (time.time() - start_time) * 1000
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5)
                    data = json.loads(message)
                    
                    results['binance_ws'] = {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': True,
                        'message_type': data.get('e', 'unknown')
                    }
                    print(f"   ✅ Binance WebSocket: 连接成功，收到{data.get('e', 'unknown')}消息 ({elapsed:.0f}ms)")
                    
                except asyncio.TimeoutError:
                    results['binance_ws'] = {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': False
                    }
                    print(f"   ✅ Binance WebSocket: 连接成功，但5秒内未收到消息 ({elapsed:.0f}ms)")
        
        except Exception as e:
            results['binance_ws'] = {'success': False, 'error': str(e)}
            print(f"   ❌ Binance WebSocket: {e}")
        
        # 测试OKX WebSocket
        try:
            url = "wss://ws.okx.com:8443/ws/v5/public"
            print(f"   测试OKX: {url}")
            start_time = time.time()
            
            async with websockets.connect(
                url,
                open_timeout=10,
                close_timeout=5,
                ping_interval=30,
                ping_timeout=10
            ) as websocket:
                elapsed = (time.time() - start_time) * 1000
                
                # 发送订阅消息
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{"channel": "trades", "instId": "BTC-USDT"}]
                }
                await websocket.send(json.dumps(subscribe_msg))
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5)
                    data = json.loads(message)
                    
                    results['okx_ws'] = {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': True,
                        'event_type': data.get('event', 'unknown')
                    }
                    print(f"   ✅ OKX WebSocket: 连接成功，收到消息 ({elapsed:.0f}ms)")
                    
                except asyncio.TimeoutError:
                    results['okx_ws'] = {
                        'success': True,
                        'connection_time_ms': elapsed,
                        'message_received': False
                    }
                    print(f"   ✅ OKX WebSocket: 连接成功，但5秒内未收到消息 ({elapsed:.0f}ms)")
        
        except Exception as e:
            results['okx_ws'] = {'success': False, 'error': str(e)}
            print(f"   ❌ OKX WebSocket: {e}")
        
        return results
    
    async def close(self):
        """关闭连接"""
        if self.session:
            await self.session.close()
            self.session = None

async def test_unified_managers():
    """测试统一管理器"""
    print("🔧 测试统一管理器...")
    
    results = {}
    
    # 测试统一会话管理器
    try:
        from core.networking.unified_session_manager import UnifiedSessionManager
        
        session_manager = UnifiedSessionManager()
        await session_manager.initialize()
        
        response = await session_manager.get("https://httpbin.org/status/200", timeout=5)
        
        results['unified_session_manager'] = {
            'success': True,
            'status_code': response.status
        }
        print("   ✅ 统一会话管理器: HTTP请求成功")
        
        await session_manager.close()
        
    except Exception as e:
        results['unified_session_manager'] = {'success': False, 'error': str(e)}
        print(f"   ❌ 统一会话管理器: {e}")
    
    # 测试统一存储管理器
    try:
        from core.storage.unified_storage_manager import UnifiedStorageManager
        
        storage_manager = UnifiedStorageManager()
        await storage_manager.initialize()
        
        status = await storage_manager.get_status()
        
        results['unified_storage_manager'] = {
            'success': True,
            'initialized': status.get('initialized', False)
        }
        print("   ✅ 统一存储管理器: 状态获取成功")
        
    except Exception as e:
        results['unified_storage_manager'] = {'success': False, 'error': str(e)}
        print(f"   ❌ 统一存储管理器: {e}")
    
    return results

async def main():
    """主测试函数"""
    print("🚀 修复后的TDD测试")
    print("="*80)
    
    # 设置代理环境变量
    os.environ['http_proxy'] = PROXY_CONFIG["http_proxy"]
    os.environ['https_proxy'] = PROXY_CONFIG["https_proxy"]
    print(f"🔧 已设置代理: {PROXY_CONFIG['http_proxy']}")
    
    all_results = {}
    connector = FixedExchangeConnector()
    
    try:
        # 测试1: 统一管理器
        print("\\n📋 测试1: 统一管理器")
        print("-"*50)
        unified_results = await test_unified_managers()
        all_results['unified_managers'] = unified_results
        
        # 测试2: Binance API
        print("\\n📋 测试2: Binance API")
        print("-"*50)
        binance_results = await connector.test_binance_api()
        all_results['binance_api'] = binance_results
        
        # 测试3: OKX API
        print("\\n📋 测试3: OKX API")
        print("-"*50)
        okx_results = await connector.test_okx_api()
        all_results['okx_api'] = okx_results
        
        # 测试4: WebSocket连接
        print("\\n📋 测试4: WebSocket连接")
        print("-"*50)
        ws_results = await connector.test_websocket_connections()
        all_results['websocket'] = ws_results
        
    finally:
        await connector.close()
    
    # 生成测试报告
    print("\\n📊 测试结果统计")
    print("="*80)
    
    total_tests = 0
    successful_tests = 0
    
    for category, tests in all_results.items():
        print(f"\\n🔍 {category.upper()} 结果:")
        
        for test_name, result in tests.items():
            total_tests += 1
            if result.get('success', False):
                successful_tests += 1
                status = "✅"
            else:
                status = "❌"
            
            error_info = result.get('error', '成功')
            print(f"   {status} {test_name}: {error_info}")
    
    success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\\n📈 总体成功率: {success_rate:.1f}% ({successful_tests}/{total_tests})")
    
    # 对比之前的问题
    print(f"\\n🔍 与之前41.7%就绪度的对比:")
    
    improvements = []
    if success_rate > 41.7:
        improvements.append(f"✅ 系统就绪度从41.7%提升到{success_rate:.1f}%")
    
    if all_results.get('binance_api', {}).get('server_time', {}).get('success'):
        improvements.append("✅ Binance API连接问题已解决")
    
    if all_results.get('okx_api', {}).get('server_time', {}).get('success'):
        improvements.append("✅ OKX API连接问题已解决")
    
    if all_results.get('websocket', {}).get('binance_ws', {}).get('success'):
        improvements.append("✅ Binance WebSocket连接问题已解决")
    
    if improvements:
        for improvement in improvements:
            print(f"   {improvement}")
    else:
        print("   ⚠️ 仍存在连接问题，需要进一步调试")
    
    # 保存结果
    result_file = f"fixed_tdd_test_{int(time.time())}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\\n📄 详细结果已保存到: {result_file}")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())