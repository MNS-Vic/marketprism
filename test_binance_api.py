#!/usr/bin/env python3
"""
测试Binance永续合约API端点
"""

import asyncio
import aiohttp
import json

async def test_binance_api():
    """测试Binance API端点"""
    
    # 测试不同的API端点
    test_cases = [
        {
            "name": "现货API (应该失败)",
            "url": "https://api.binance.com/api/v3/depth",
            "params": {"symbol": "BTCUSDT", "limit": 5}
        },
        {
            "name": "永续合约API (应该成功)",
            "url": "https://fapi.binance.com/fapi/v1/depth",
            "params": {"symbol": "BTCUSDT", "limit": 5}
        }
    ]
    
    async with aiohttp.ClientSession() as session:
        for test_case in test_cases:
            print(f"\n🔧 测试: {test_case['name']}")
            print(f"URL: {test_case['url']}")
            print(f"参数: {test_case['params']}")
            
            try:
                async with session.get(test_case['url'], params=test_case['params']) as response:
                    print(f"状态码: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ 成功! lastUpdateId: {data.get('lastUpdateId', 'N/A')}")
                        print(f"Bids数量: {len(data.get('bids', []))}")
                        print(f"Asks数量: {len(data.get('asks', []))}")
                    else:
                        error_text = await response.text()
                        print(f"❌ 失败! 错误: {error_text[:200]}")
                        
            except Exception as e:
                print(f"❌ 异常: {e}")

if __name__ == "__main__":
    asyncio.run(test_binance_api())
