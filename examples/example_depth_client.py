#!/usr/bin/env python3
"""
深度数据获取示例客户端

演示如何从MarketPrism collector获取实时深度数据
"""

import asyncio
import aiohttp
import json
import websockets
from datetime import datetime

class DepthDataClient:
    """深度数据客户端"""
    
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http", "ws")
    
    async def get_current_depth(self, exchange: str, symbol: str):
        """获取当前深度快照"""
        url = f"{self.base_url}/api/v1/orderbook/{exchange}/{symbol}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    print(f"获取深度失败: {response.status}")
                    return None
    
    async def subscribe_depth_updates(self, exchange: str, symbol: str):
        """订阅实时深度更新"""
        ws_url = f"{self.ws_url}/ws/orderbook/{exchange}/{symbol}"
        
        try:
            async with websockets.connect(ws_url) as websocket:
                print(f"🔗 已连接到 {exchange} {symbol} 深度流")
                
                async for message in websocket:
                    data = json.loads(message)
                    await self.handle_depth_update(data)
                    
        except Exception as e:
            print(f"WebSocket连接失败: {e}")
    
    async def handle_depth_update(self, data):
        """处理深度更新"""
        print(f"📊 深度更新 - {data['exchange_name']} {data['symbol_name']}")
        print(f"   更新ID: {data['last_update_id']}")
        print(f"   深度档数: {data['depth_levels']}")
        print(f"   最佳买价: {data['bids'][0]['price'] if data['bids'] else 'N/A'}")
        print(f"   最佳卖价: {data['asks'][0]['price'] if data['asks'] else 'N/A'}")
        print(f"   时间戳: {data['timestamp']}")
        print("-" * 50)

async def main():
    """主函数 - 演示不同的获取方式"""
    client = DepthDataClient()
    
    print("🚀 MarketPrism 深度数据获取示例")
    print("=" * 50)
    
    # 1. 获取当前深度快照
    print("\n📊 获取当前深度快照:")
    
    # Binance BTCUSDT
    btc_depth = await client.get_current_depth("binance", "BTCUSDT")
    if btc_depth:
        print(f"✅ Binance BTCUSDT:")
        print(f"   买盘档数: {len(btc_depth['bids'])}")
        print(f"   卖盘档数: {len(btc_depth['asks'])}")
        print(f"   最佳买价: {btc_depth['bids'][0]['price']}")
        print(f"   最佳卖价: {btc_depth['asks'][0]['price']}")
        print(f"   更新ID: {btc_depth['last_update_id']}")
    
    # OKX BTC-USDT
    okx_depth = await client.get_current_depth("okx", "BTC-USDT")
    if okx_depth:
        print(f"✅ OKX BTC-USDT:")
        print(f"   买盘档数: {len(okx_depth['bids'])}")
        print(f"   卖盘档数: {len(okx_depth['asks'])}")
        print(f"   最佳买价: {okx_depth['bids'][0]['price']}")
        print(f"   最佳卖价: {okx_depth['asks'][0]['price']}")
        print(f"   更新ID: {okx_depth['last_update_id']}")
    
    # 2. 订阅实时更新（示例，实际需要WebSocket服务端支持）
    print(f"\n🔄 实时深度更新订阅:")
    print("注意: 需要WebSocket服务端支持，当前为演示代码")
    
    # 实际使用时取消注释
    # await client.subscribe_depth_updates("binance", "BTCUSDT")

if __name__ == "__main__":
    asyncio.run(main())