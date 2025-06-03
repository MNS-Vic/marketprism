#!/usr/bin/env python3
"""
检查代理可用性
"""
import os
import sys
import asyncio
import aiohttp
import json

async def check_proxy(proxy_url, test_url="https://api.binance.com/api/v3/ping"):
    """检查代理是否可用"""
    try:
        async with aiohttp.ClientSession() as session:
            # 设置代理
            proxy = {
                'http': proxy_url,
                'https': proxy_url,
            }
            # 设置超时
            timeout = aiohttp.ClientTimeout(total=10)
            # 发送请求
            async with session.get(test_url, proxy=proxy_url, timeout=timeout) as response:
                if response.status == 200:
                    return True, await response.text()
                else:
                    return False, f"状态码: {response.status}, 响应: {await response.text()}"
    except Exception as e:
        return False, str(e)

async def find_working_proxy(ports=[7890, 7891, 1080, 1087, 8080, 8118]):
    """找到一个可用的代理端口"""
    results = []
    
    for port in ports:
        proxy_url = f"http://127.0.0.1:{port}"
        success, msg = await check_proxy(proxy_url)
        if success:
            print(f"代理 {proxy_url} 可用")
            return proxy_url
        else:
            results.append((proxy_url, msg))
    
    print("未找到可用的代理:")
    for proxy_url, error in results:
        print(f"  {proxy_url} - 错误: {error}")
    return None

async def main():
    # 检查环境变量中是否已设置代理
    http_proxy = os.environ.get('http_proxy')
    https_proxy = os.environ.get('https_proxy')
    
    # 如果设置了代理，先检查它是否可用
    if http_proxy:
        success, msg = await check_proxy(http_proxy)
        if success:
            print(f"当前HTTP代理 {http_proxy} 可用")
            return http_proxy
        else:
            print(f"当前HTTP代理 {http_proxy} 不可用: {msg}")
    
    if https_proxy and https_proxy != http_proxy:
        success, msg = await check_proxy(https_proxy)
        if success:
            print(f"当前HTTPS代理 {https_proxy} 可用")
            return https_proxy
        else:
            print(f"当前HTTPS代理 {https_proxy} 不可用: {msg}")
    
    # 尝试查找可用的代理
    return await find_working_proxy()

if __name__ == "__main__":
    working_proxy = asyncio.run(main())
    
    if working_proxy:
        # 输出结果为JSON，方便脚本使用
        result = {
            "status": "success",
            "proxy": working_proxy
        }
    else:
        result = {
            "status": "failure",
            "proxy": None
        }
    
    print(json.dumps(result))
    
    # 如果是作为命令行工具运行，则设置返回码
    if not working_proxy:
        sys.exit(1)