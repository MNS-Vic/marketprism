#!/usr/bin/env python3
"""
交易所连接测试

专门测试各个交易所的连接状态，不涉及复杂的性能测试
帮助诊断和解决连接问题
"""

import asyncio
import aiohttp
import time
import sys
import os
from typing import Dict, Any, Optional

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType


class ExchangeConnectionTester:
    """交易所连接测试器"""
    
    def __init__(self):
        self.exchange_configs = {
            'binance': {
                'rest_url': 'https://api.binance.com',
                'ws_url': 'wss://stream.binance.com:9443/ws/btcusdt@trade',
                'test_endpoint': '/api/v3/ping'
            },
            'okx': {
                'rest_url': 'https://www.okx.com',
                'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
                'test_endpoint': '/api/v5/public/time'
            },
            'deribit': {
                'rest_url': 'https://www.deribit.com',
                'ws_url': 'wss://www.deribit.com/ws/api/v2',
                'test_endpoint': '/api/v2/public/get_time'
            }
        }
    
    async def test_all_exchanges(self):
        """测试所有交易所连接"""
        print("🔗 交易所连接测试")
        print("=" * 60)
        print("🎯 测试目标: 验证各交易所REST API和WebSocket连接")
        print()
        
        results = {}
        
        for exchange_name, config in self.exchange_configs.items():
            print(f"🔍 测试 {exchange_name.upper()} 交易所...")
            
            # 测试REST API
            rest_result = await self._test_rest_api(exchange_name, config)
            
            # 测试WebSocket连接
            ws_result = await self._test_websocket(exchange_name, config)
            
            results[exchange_name] = {
                'rest': rest_result,
                'websocket': ws_result,
                'overall': rest_result['success'] and ws_result['success']
            }
            
            # 显示结果
            rest_status = "✅" if rest_result['success'] else "❌"
            ws_status = "✅" if ws_result['success'] else "❌"
            overall_status = "✅" if results[exchange_name]['overall'] else "❌"
            
            print(f"   REST API: {rest_status} ({rest_result['response_time']:.0f}ms)")
            print(f"   WebSocket: {ws_status} ({ws_result['response_time']:.0f}ms)")
            print(f"   整体状态: {overall_status}")
            
            if not rest_result['success']:
                print(f"   REST错误: {rest_result['error']}")
            if not ws_result['success']:
                print(f"   WebSocket错误: {ws_result['error']}")
            
            print()
        
        # 生成总结报告
        await self._generate_connection_report(results)
        
        return results
    
    async def _test_rest_api(self, exchange_name: str, config: Dict[str, str]) -> Dict[str, Any]:
        """测试REST API连接"""
        start_time = time.time()
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = config['rest_url'] + config['test_endpoint']
                
                async with session.get(url) as response:
                    response_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        return {
                            'success': True,
                            'response_time': response_time,
                            'status_code': response.status,
                            'error': None
                        }
                    else:
                        return {
                            'success': False,
                            'response_time': response_time,
                            'status_code': response.status,
                            'error': f"HTTP {response.status}"
                        }
        
        except asyncio.TimeoutError:
            return {
                'success': False,
                'response_time': (time.time() - start_time) * 1000,
                'status_code': None,
                'error': "连接超时"
            }
        except Exception as e:
            return {
                'success': False,
                'response_time': (time.time() - start_time) * 1000,
                'status_code': None,
                'error': str(e)
            }
    
    async def _test_websocket(self, exchange_name: str, config: Dict[str, str]) -> Dict[str, Any]:
        """测试WebSocket连接"""
        start_time = time.time()
        
        try:
            import websockets
            
            # 设置较短的超时时间
            async with websockets.connect(
                config['ws_url'],
                ping_interval=None,
                ping_timeout=None,
                close_timeout=5,
                open_timeout=10
            ) as websocket:
                
                response_time = (time.time() - start_time) * 1000
                
                # 发送测试消息（根据交易所不同）
                if exchange_name == 'binance':
                    # Binance不需要发送订阅消息，连接即可接收数据
                    pass
                elif exchange_name == 'okx':
                    # OKX需要发送订阅消息
                    subscribe_msg = {
                        "op": "subscribe",
                        "args": [{"channel": "trades", "instId": "BTC-USDT"}]
                    }
                    await websocket.send(str(subscribe_msg).replace("'", '"'))
                elif exchange_name == 'deribit':
                    # Deribit需要发送订阅消息
                    subscribe_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "public/subscribe",
                        "params": {"channels": ["trades.BTC-PERPETUAL.100ms"]}
                    }
                    await websocket.send(str(subscribe_msg).replace("'", '"'))
                
                # 等待响应（最多3秒）
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                    return {
                        'success': True,
                        'response_time': response_time,
                        'error': None,
                        'message_received': True
                    }
                except asyncio.TimeoutError:
                    # 连接成功但没有收到消息也算成功
                    return {
                        'success': True,
                        'response_time': response_time,
                        'error': None,
                        'message_received': False
                    }
        
        except asyncio.TimeoutError:
            return {
                'success': False,
                'response_time': (time.time() - start_time) * 1000,
                'error': "WebSocket连接超时"
            }
        except Exception as e:
            return {
                'success': False,
                'response_time': (time.time() - start_time) * 1000,
                'error': f"WebSocket错误: {str(e)}"
            }
    
    async def _generate_connection_report(self, results: Dict[str, Dict[str, Any]]):
        """生成连接测试报告"""
        print("📊 交易所连接测试报告")
        print("=" * 60)
        
        total_exchanges = len(results)
        successful_exchanges = sum(1 for r in results.values() if r['overall'])
        
        print(f"📈 总体状况:")
        print(f"   测试交易所: {total_exchanges}个")
        print(f"   连接成功: {successful_exchanges}个")
        print(f"   成功率: {successful_exchanges/total_exchanges*100:.1f}%")
        print()
        
        print(f"📋 详细结果:")
        for exchange_name, result in results.items():
            status = "✅ 正常" if result['overall'] else "❌ 异常"
            rest_time = result['rest']['response_time']
            ws_time = result['websocket']['response_time']
            
            print(f"   {exchange_name.upper()}: {status}")
            print(f"      REST API: {rest_time:.0f}ms")
            print(f"      WebSocket: {ws_time:.0f}ms")
            
            if not result['overall']:
                if not result['rest']['success']:
                    print(f"      REST问题: {result['rest']['error']}")
                if not result['websocket']['success']:
                    print(f"      WebSocket问题: {result['websocket']['error']}")
            print()
        
        # 生成建议
        print(f"💡 优化建议:")
        
        failed_exchanges = [name for name, result in results.items() if not result['overall']]
        if failed_exchanges:
            print(f"   需要修复的交易所: {', '.join(failed_exchanges)}")
            
            for exchange_name in failed_exchanges:
                result = results[exchange_name]
                if not result['rest']['success']:
                    print(f"   - {exchange_name} REST API连接问题，检查网络和API端点")
                if not result['websocket']['success']:
                    print(f"   - {exchange_name} WebSocket连接问题，检查防火墙和代理设置")
        else:
            print(f"   🎉 所有交易所连接正常，可以进行多交易所并发测试！")
        
        print("=" * 60)
    
    async def test_specific_exchange(self, exchange_name: str):
        """测试特定交易所"""
        if exchange_name not in self.exchange_configs:
            print(f"❌ 不支持的交易所: {exchange_name}")
            return False
        
        print(f"🔍 测试 {exchange_name.upper()} 交易所连接...")
        
        config = self.exchange_configs[exchange_name]
        
        # 测试REST API
        print("   测试REST API...")
        rest_result = await self._test_rest_api(exchange_name, config)
        
        # 测试WebSocket
        print("   测试WebSocket...")
        ws_result = await self._test_websocket(exchange_name, config)
        
        # 显示结果
        print(f"\n📊 {exchange_name.upper()} 连接测试结果:")
        print(f"   REST API: {'✅ 成功' if rest_result['success'] else '❌ 失败'} ({rest_result['response_time']:.0f}ms)")
        print(f"   WebSocket: {'✅ 成功' if ws_result['success'] else '❌ 失败'} ({ws_result['response_time']:.0f}ms)")
        
        if not rest_result['success']:
            print(f"   REST错误: {rest_result['error']}")
        if not ws_result['success']:
            print(f"   WebSocket错误: {ws_result['error']}")
        
        overall_success = rest_result['success'] and ws_result['success']
        print(f"   整体状态: {'✅ 正常' if overall_success else '❌ 异常'}")
        
        return overall_success


async def main():
    """主函数"""
    tester = ExchangeConnectionTester()
    
    if len(sys.argv) > 1:
        # 测试特定交易所
        exchange_name = sys.argv[1].lower()
        success = await tester.test_specific_exchange(exchange_name)
        sys.exit(0 if success else 1)
    else:
        # 测试所有交易所
        results = await tester.test_all_exchanges()
        
        # 检查是否所有交易所都连接成功
        all_success = all(result['overall'] for result in results.values())
        
        if all_success:
            print("🎉 所有交易所连接测试通过！")
            sys.exit(0)
        else:
            print("⚠️ 部分交易所连接存在问题")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 