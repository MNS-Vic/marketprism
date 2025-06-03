#!/usr/bin/env python3
"""
WebSocket代理修复测试

专门测试WebSocket在代理环境下的连接问题
"""

import asyncio
import websockets
import time
import os
import sys
import json
from typing import Dict, Any


async def test_websocket_direct(url: str, name: str) -> Dict[str, Any]:
    """直接WebSocket连接测试"""
    print(f"🔍 测试 {name} 直接连接: {url}")
    start_time = time.time()
    
    try:
        async with websockets.connect(
            url,
            open_timeout=10,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=10
        ) as websocket:
            elapsed = (time.time() - start_time) * 1000
            print(f"   ✅ 直接连接成功 ({elapsed:.0f}ms)")
            
            # 尝试接收一条消息
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"   📨 接收到消息: {len(message)} 字符")
                return {"success": True, "time": elapsed, "message_received": True}
            except asyncio.TimeoutError:
                print(f"   ⏰ 未在5秒内接收到消息")
                return {"success": True, "time": elapsed, "message_received": False}
                
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ 直接连接失败: {e} ({elapsed:.0f}ms)")
        return {"success": False, "time": elapsed, "error": str(e)}


async def test_websocket_with_socks_proxy(url: str, name: str) -> Dict[str, Any]:
    """使用SOCKS代理的WebSocket连接测试"""
    print(f"🔍 测试 {name} SOCKS代理连接: {url}")
    start_time = time.time()
    
    try:
        # 尝试使用python-socks库
        try:
            import python_socks
            from python_socks import ProxyType
            
            # 创建SOCKS代理连接
            proxy = python_socks.Proxy(
                proxy_type=ProxyType.SOCKS5,
                host="127.0.0.1",
                port=1080
            )
            
            # 这里需要特殊的WebSocket代理实现
            # websockets库本身不直接支持SOCKS代理
            print(f"   ⚠️ websockets库不直接支持SOCKS代理")
            return {"success": False, "time": 0, "error": "websockets库不支持SOCKS代理"}
            
        except ImportError:
            print(f"   ⚠️ python-socks库未安装")
            return {"success": False, "time": 0, "error": "python-socks库未安装"}
            
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ SOCKS代理连接失败: {e} ({elapsed:.0f}ms)")
        return {"success": False, "time": elapsed, "error": str(e)}


async def test_websocket_with_http_proxy_headers(url: str, name: str) -> Dict[str, Any]:
    """使用HTTP代理头的WebSocket连接测试"""
    print(f"🔍 测试 {name} HTTP代理头连接: {url}")
    start_time = time.time()
    
    try:
        # 添加代理相关的头部
        extra_headers = {
            "Proxy-Connection": "keep-alive",
            "User-Agent": "MarketPrism/1.0"
        }
        
        async with websockets.connect(
            url,
            extra_headers=extra_headers,
            open_timeout=10,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=10
        ) as websocket:
            elapsed = (time.time() - start_time) * 1000
            print(f"   ✅ HTTP代理头连接成功 ({elapsed:.0f}ms)")
            
            # 尝试接收一条消息
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"   📨 接收到消息: {len(message)} 字符")
                return {"success": True, "time": elapsed, "message_received": True}
            except asyncio.TimeoutError:
                print(f"   ⏰ 未在5秒内接收到消息")
                return {"success": True, "time": elapsed, "message_received": False}
                
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        print(f"   ❌ HTTP代理头连接失败: {e} ({elapsed:.0f}ms)")
        return {"success": False, "time": elapsed, "error": str(e)}


async def test_websocket_with_different_ports(url: str, name: str) -> Dict[str, Any]:
    """测试不同端口的WebSocket连接"""
    print(f"🔍 测试 {name} 不同端口连接")
    
    # 尝试不同的端口或URL变体
    test_urls = []
    
    if "binance" in url.lower():
        test_urls = [
            "wss://stream.binance.com:9443/ws/btcusdt@trade",
            "wss://stream.binance.com/ws/btcusdt@trade",  # 不指定端口
            "wss://data-stream.binance.vision/ws/btcusdt@trade"  # 备用域名
        ]
    elif "okx" in url.lower():
        test_urls = [
            "wss://ws.okx.com:8443/ws/v5/public",
            "wss://ws.okx.com/ws/v5/public",  # 不指定端口
        ]
    elif "deribit" in url.lower():
        test_urls = [
            "wss://www.deribit.com/ws/api/v2",
            "wss://deribit.com/ws/api/v2",  # 不带www
        ]
    
    results = []
    for test_url in test_urls:
        print(f"   尝试: {test_url}")
        result = await test_websocket_direct(test_url, f"{name}_alt")
        results.append({"url": test_url, "result": result})
        
        if result["success"]:
            print(f"   ✅ 找到可用URL: {test_url}")
            return {"success": True, "working_url": test_url, "results": results}
    
    return {"success": False, "results": results}


async def test_websocket_comprehensive():
    """综合WebSocket代理测试"""
    print("🚀 WebSocket代理修复综合测试")
    print("=" * 80)
    
    # 显示代理设置
    print(f"🔧 当前代理设置:")
    print(f"   http_proxy: {os.getenv('http_proxy', '未设置')}")
    print(f"   https_proxy: {os.getenv('https_proxy', '未设置')}")
    print(f"   ALL_PROXY: {os.getenv('ALL_PROXY', '未设置')}")
    print()
    
    # 测试目标
    test_targets = [
        ("Binance", "wss://stream.binance.com:9443/ws/btcusdt@trade"),
        ("OKX", "wss://ws.okx.com:8443/ws/v5/public"),
        ("Deribit", "wss://www.deribit.com/ws/api/v2")
    ]
    
    results = {}
    
    for name, url in test_targets:
        print(f"📡 测试 {name} WebSocket连接")
        print("-" * 60)
        
        # 测试1: 直接连接
        direct_result = await test_websocket_direct(url, name)
        
        # 测试2: HTTP代理头
        proxy_header_result = await test_websocket_with_http_proxy_headers(url, name)
        
        # 测试3: SOCKS代理
        socks_result = await test_websocket_with_socks_proxy(url, name)
        
        # 测试4: 不同端口
        alt_ports_result = await test_websocket_with_different_ports(url, name)
        
        results[name] = {
            "original_url": url,
            "direct": direct_result,
            "proxy_headers": proxy_header_result,
            "socks_proxy": socks_result,
            "alternative_ports": alt_ports_result
        }
        
        print()
    
    # 生成报告
    print("📊 WebSocket代理测试报告")
    print("=" * 80)
    
    for name, result in results.items():
        print(f"\n🔍 {name} 测试结果:")
        
        # 直接连接
        direct = result["direct"]
        status = "✅" if direct["success"] else "❌"
        print(f"   直接连接: {status} ({direct.get('time', 0):.0f}ms)")
        
        # 代理头连接
        proxy_headers = result["proxy_headers"]
        status = "✅" if proxy_headers["success"] else "❌"
        print(f"   代理头连接: {status} ({proxy_headers.get('time', 0):.0f}ms)")
        
        # SOCKS代理
        socks = result["socks_proxy"]
        status = "✅" if socks["success"] else "❌"
        print(f"   SOCKS代理: {status}")
        
        # 备用端口
        alt_ports = result["alternative_ports"]
        status = "✅" if alt_ports["success"] else "❌"
        print(f"   备用端口: {status}")
        
        if alt_ports["success"]:
            print(f"     可用URL: {alt_ports['working_url']}")
    
    # 成功率统计
    total_tests = len(results) * 4  # 每个交易所4种测试方法
    successful_tests = 0
    
    for result in results.values():
        if result["direct"]["success"]:
            successful_tests += 1
        if result["proxy_headers"]["success"]:
            successful_tests += 1
        if result["socks_proxy"]["success"]:
            successful_tests += 1
        if result["alternative_ports"]["success"]:
            successful_tests += 1
    
    success_rate = successful_tests / total_tests * 100
    
    print(f"\n📈 总体成功率: {success_rate:.1f}% ({successful_tests}/{total_tests})")
    
    # 建议
    print(f"\n💡 修复建议:")
    
    working_exchanges = []
    failing_exchanges = []
    
    for name, result in results.items():
        if (result["direct"]["success"] or 
            result["proxy_headers"]["success"] or 
            result["alternative_ports"]["success"]):
            working_exchanges.append(name)
        else:
            failing_exchanges.append(name)
    
    if working_exchanges:
        print(f"   ✅ 可用交易所: {', '.join(working_exchanges)}")
    
    if failing_exchanges:
        print(f"   ❌ 需修复交易所: {', '.join(failing_exchanges)}")
        print(f"   🔧 建议解决方案:")
        print(f"      1. 检查防火墙设置")
        print(f"      2. 尝试使用备用域名或端口")
        print(f"      3. 配置SOCKS代理支持")
        print(f"      4. 检查网络运营商是否阻止WebSocket连接")
    
    # 保存结果
    result_file = f"websocket_proxy_test_result_{int(time.time())}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n📄 详细结果已保存到: {result_file}")
    print("=" * 80)


async def main():
    """主函数"""
    try:
        await test_websocket_comprehensive()
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())