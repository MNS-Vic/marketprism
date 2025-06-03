#!/usr/bin/env python3
"""
简化连接测试

使用不同的方法测试网络连接，找出问题所在
"""

import asyncio
import aiohttp
import requests
import time
import sys


async def test_aiohttp_connection(url: str, timeout: int = 5):
    """使用aiohttp测试连接"""
    print(f"🔍 aiohttp测试: {url}")
    start_time = time.time()
    
    try:
        timeout_config = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.get(url) as response:
                elapsed = (time.time() - start_time) * 1000
                print(f"   ✅ 成功: {response.status} ({elapsed:.0f}ms)")
                return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ 失败: {e} ({elapsed:.0f}ms)")
        return False


def test_requests_connection(url: str, timeout: int = 5):
    """使用requests测试连接"""
    print(f"🔍 requests测试: {url}")
    start_time = time.time()
    
    try:
        response = requests.get(url, timeout=timeout)
        elapsed = (time.time() - start_time) * 1000
        print(f"   ✅ 成功: {response.status_code} ({elapsed:.0f}ms)")
        return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ 失败: {e} ({elapsed:.0f}ms)")
        return False


async def test_websocket_connection(url: str, timeout: int = 5):
    """测试WebSocket连接"""
    print(f"🔍 WebSocket测试: {url}")
    start_time = time.time()
    
    try:
        import websockets
        
        async with websockets.connect(
            url,
            open_timeout=timeout,
            close_timeout=2,
            ping_interval=None
        ) as websocket:
            elapsed = (time.time() - start_time) * 1000
            print(f"   ✅ 成功: WebSocket连接建立 ({elapsed:.0f}ms)")
            return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ 失败: {e} ({elapsed:.0f}ms)")
        return False


async def main():
    """主函数"""
    print("🔗 简化连接测试")
    print("=" * 50)
    
    # 测试URL列表
    test_urls = {
        'binance_api': 'https://api.binance.com/api/v3/ping',
        'binance_ws': 'wss://stream.binance.com:9443/ws/btcusdt@trade',
        'okx_api': 'https://www.okx.com/api/v5/public/time',
        'okx_ws': 'wss://ws.okx.com:8443/ws/v5/public',
        'deribit_api': 'https://www.deribit.com/api/v2/public/get_time',
        'deribit_ws': 'wss://www.deribit.com/ws/api/v2'
    }
    
    results = {}
    
    # 测试REST API
    print("\n📡 测试REST API连接...")
    for name, url in test_urls.items():
        if '_api' in name:
            print(f"\n{name}:")
            
            # 使用requests测试
            requests_success = test_requests_connection(url, timeout=5)
            
            # 使用aiohttp测试
            aiohttp_success = await test_aiohttp_connection(url, timeout=5)
            
            results[name] = {
                'requests': requests_success,
                'aiohttp': aiohttp_success
            }
    
    # 测试WebSocket连接
    print("\n🔌 测试WebSocket连接...")
    for name, url in test_urls.items():
        if '_ws' in name:
            print(f"\n{name}:")
            
            ws_success = await test_websocket_connection(url, timeout=5)
            results[name] = {'websocket': ws_success}
    
    # 生成报告
    print("\n📊 连接测试报告")
    print("=" * 50)
    
    for name, result in results.items():
        print(f"\n{name}:")
        for method, success in result.items():
            status = "✅" if success else "❌"
            print(f"   {method}: {status}")
    
    # 分析问题
    print("\n💡 问题分析:")
    
    api_issues = []
    ws_issues = []
    
    for name, result in results.items():
        if '_api' in name:
            if result.get('requests', False) and not result.get('aiohttp', False):
                api_issues.append(f"{name}: requests成功但aiohttp失败")
            elif not result.get('requests', False) and not result.get('aiohttp', False):
                api_issues.append(f"{name}: 两种方法都失败")
        elif '_ws' in name:
            if not result.get('websocket', False):
                ws_issues.append(f"{name}: WebSocket连接失败")
    
    if api_issues:
        print("   REST API问题:")
        for issue in api_issues:
            print(f"   - {issue}")
    
    if ws_issues:
        print("   WebSocket问题:")
        for issue in ws_issues:
            print(f"   - {issue}")
    
    if not api_issues and not ws_issues:
        print("   🎉 所有连接都正常！")
    
    print("\n🔧 建议解决方案:")
    if api_issues:
        print("   - 检查aiohttp的SSL配置")
        print("   - 尝试设置代理或DNS配置")
        print("   - 检查防火墙设置")
    
    if ws_issues:
        print("   - 检查WebSocket代理设置")
        print("   - 验证防火墙是否阻止WebSocket连接")
    
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main()) 