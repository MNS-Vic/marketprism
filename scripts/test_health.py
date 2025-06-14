#!/usr/bin/env python3
import asyncio
import aiohttp

async def test_health():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8080/health', timeout=5) as response:
                print(f'状态码: {response.status}')
                text = await response.text()
                print(f'响应内容: {text}')
                return response.status == 200
    except Exception as e:
        print(f'请求失败: {e}')
        return False

if __name__ == "__main__":
    result = asyncio.run(test_health())
    print(f'健康检查结果: {"✅ 成功" if result else "❌ 失败"}')