#!/usr/bin/env python3
"""
aiohttp代理配置修复测试

专门测试aiohttp在代理环境下的连接问题
"""

import asyncio
import aiohttp
import time
import sys
import os


async def test_aiohttp_with_proxy_config():
    """测试aiohttp的不同代理配置方法"""
    print("🔧 aiohttp代理配置修复测试")
    print("=" * 60)
    
    test_urls = [
        "https://api.binance.com/api/v3/ping",
        "https://www.okx.com/api/v5/public/time",
        "https://www.deribit.com/api/v2/public/get_time"
    ]
    
    # 方法1: 使用环境变量（当前方法）
    print("\n📡 方法1: 使用环境变量代理")
    for url in test_urls:
        await test_url_with_env_proxy(url)
    
    # 方法2: 显式设置代理
    print("\n📡 方法2: 显式设置HTTP代理")
    for url in test_urls:
        await test_url_with_explicit_proxy(url, "http://127.0.0.1:1087")
    
    # 方法3: 禁用SSL验证
    print("\n📡 方法3: 禁用SSL验证")
    for url in test_urls:
        await test_url_with_no_ssl_verify(url)
    
    # 方法4: 使用connector配置
    print("\n📡 方法4: 使用connector配置")
    for url in test_urls:
        await test_url_with_connector_config(url)


async def test_url_with_env_proxy(url: str):
    """使用环境变量代理测试"""
    print(f"   测试: {url}")
    start_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                elapsed = (time.time() - start_time) * 1000
                print(f"   ✅ 环境变量代理成功: {response.status} ({elapsed:.0f}ms)")
                return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ 环境变量代理失败: {e} ({elapsed:.0f}ms)")
        return False


async def test_url_with_explicit_proxy(url: str, proxy: str):
    """使用显式代理设置测试"""
    print(f"   测试: {url}")
    start_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, proxy=proxy) as response:
                elapsed = (time.time() - start_time) * 1000
                print(f"   ✅ 显式代理成功: {response.status} ({elapsed:.0f}ms)")
                return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ 显式代理失败: {e} ({elapsed:.0f}ms)")
        return False


async def test_url_with_no_ssl_verify(url: str):
    """禁用SSL验证测试"""
    print(f"   测试: {url}")
    start_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.get(url, proxy="http://127.0.0.1:1087") as response:
                elapsed = (time.time() - start_time) * 1000
                print(f"   ✅ 禁用SSL成功: {response.status} ({elapsed:.0f}ms)")
                return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ 禁用SSL失败: {e} ({elapsed:.0f}ms)")
        return False


async def test_url_with_connector_config(url: str):
    """使用connector配置测试"""
    print(f"   测试: {url}")
    start_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.get(url, proxy="http://127.0.0.1:1087") as response:
                elapsed = (time.time() - start_time) * 1000
                print(f"   ✅ connector配置成功: {response.status} ({elapsed:.0f}ms)")
                return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ connector配置失败: {e} ({elapsed:.0f}ms)")
        return False


async def test_websocket_proxy_fix():
    """测试WebSocket代理修复"""
    print("\n🔌 WebSocket代理修复测试")
    print("=" * 60)
    
    ws_urls = [
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        "wss://ws.okx.com:8443/ws/v5/public",
        "wss://www.deribit.com/ws/api/v2"
    ]
    
    for url in ws_urls:
        await test_websocket_with_proxy(url)


async def test_websocket_with_proxy(url: str):
    """测试WebSocket代理连接"""
    print(f"   测试: {url}")
    start_time = time.time()
    
    try:
        import websockets
        
        # 尝试使用代理连接
        async with websockets.connect(
            url,
            open_timeout=5,
            close_timeout=2,
            ping_interval=None,
            # 注意：websockets库可能不直接支持HTTP代理
            # 需要使用其他方法
        ) as websocket:
            elapsed = (time.time() - start_time) * 1000
            print(f"   ✅ WebSocket连接成功 ({elapsed:.0f}ms)")
            return True
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ WebSocket连接失败: {e} ({elapsed:.0f}ms)")
        return False


async def main():
    """主函数"""
    print("🚀 开始aiohttp代理配置修复测试")
    
    # 显示当前代理设置
    print(f"\n🔧 当前代理设置:")
    print(f"   http_proxy: {os.getenv('http_proxy', '未设置')}")
    print(f"   https_proxy: {os.getenv('https_proxy', '未设置')}")
    print(f"   ALL_PROXY: {os.getenv('ALL_PROXY', '未设置')}")
    
    # 测试aiohttp代理配置
    await test_aiohttp_with_proxy_config()
    
    # 测试WebSocket代理配置
    await test_websocket_proxy_fix()
    
    print("\n📊 测试完成")
    print("=" * 60)
    print("💡 如果显式代理设置成功，我们可以修改collector代码使用显式代理")
    print("💡 如果禁用SSL成功，可能是SSL证书验证问题")
    print("💡 WebSocket可能需要使用SOCKS代理或其他解决方案")


if __name__ == "__main__":
    asyncio.run(main())