#!/usr/bin/env python3
"""
简单的深度数据获取示例

演示如何直接从交易所获取深度数据，不依赖Docker服务
"""

import asyncio
import aiohttp
import json
import sys
import os
from decimal import Decimal
from datetime import datetime

# 设置代理
os.environ['http_proxy'] = 'http://127.0.0.1:1087'
os.environ['https_proxy'] = 'http://127.0.0.1:1087'

class SimpleDepthClient:
    """简单深度数据客户端"""
    
    def __init__(self):
        self.session = None
        self.proxy = 'http://127.0.0.1:1087'
    
    async def start(self):
        """启动客户端"""
        connector = aiohttp.TCPConnector(limit=100)
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            connector=connector
        )
        print("✅ HTTP客户端已启动")
    
    async def stop(self):
        """停止客户端"""
        if self.session:
            await self.session.close()
        print("✅ HTTP客户端已停止")
    
    async def get_binance_depth(self, symbol: str, limit: int = 400):
        """获取Binance深度数据"""
        try:
            url = "https://api.binance.com/api/v3/depth"
            params = {
                "symbol": symbol.replace("-", ""),
                "limit": limit
            }
            
            print(f"📡 请求Binance深度数据: {symbol} ({limit}档)")
            
            async with self.session.get(url, params=params, proxy=self.proxy) as response:
                if response.status != 200:
                    print(f"❌ 请求失败: {response.status}")
                    return None
                
                data = await response.json()
                
                # 解析数据
                bids = []
                for price, qty in data["bids"]:
                    bids.append({
                        "price": Decimal(price),
                        "quantity": Decimal(qty)
                    })
                
                asks = []
                for price, qty in data["asks"]:
                    asks.append({
                        "price": Decimal(price),
                        "quantity": Decimal(qty)
                    })
                
                result = {
                    "exchange": "binance",
                    "symbol": symbol,
                    "last_update_id": data["lastUpdateId"],
                    "bids": bids,
                    "asks": asks,
                    "timestamp": datetime.utcnow().isoformat(),
                    "depth_levels": len(bids) + len(asks)
                }
                
                print(f"✅ 获取成功:")
                print(f"   买盘档数: {len(bids)}")
                print(f"   卖盘档数: {len(asks)}")
                print(f"   总档数: {result['depth_levels']}")
                print(f"   更新ID: {result['last_update_id']}")
                
                if bids and asks:
                    spread = asks[0]["price"] - bids[0]["price"]
                    print(f"   最佳买价: {bids[0]['price']}")
                    print(f"   最佳卖价: {asks[0]['price']}")
                    print(f"   价差: {spread}")
                
                return result
                
        except Exception as e:
            print(f"❌ 获取Binance深度失败: {e}")
            return None
    
    async def get_okx_depth(self, symbol: str, limit: int = 400):
        """获取OKX深度数据"""
        try:
            url = "https://www.okx.com/api/v5/market/books"
            params = {
                "instId": symbol,
                "sz": str(limit)
            }
            
            print(f"📡 请求OKX深度数据: {symbol} ({limit}档)")
            
            async with self.session.get(url, params=params, proxy=self.proxy) as response:
                if response.status != 200:
                    print(f"❌ 请求失败: {response.status}")
                    return None
                
                data = await response.json()
                
                if data.get('code') != '0':
                    print(f"❌ OKX API错误: {data.get('msg')}")
                    return None
                
                if not data.get('data') or not data['data']:
                    print("❌ 无数据返回")
                    return None
                
                book_data = data['data'][0]
                
                # 解析数据
                bids = []
                for price, qty, _, _ in book_data["bids"]:
                    bids.append({
                        "price": Decimal(price),
                        "quantity": Decimal(qty)
                    })
                
                asks = []
                for price, qty, _, _ in book_data["asks"]:
                    asks.append({
                        "price": Decimal(price),
                        "quantity": Decimal(qty)
                    })
                
                result = {
                    "exchange": "okx",
                    "symbol": symbol,
                    "last_update_id": int(book_data["ts"]),
                    "bids": bids,
                    "asks": asks,
                    "timestamp": datetime.utcnow().isoformat(),
                    "depth_levels": len(bids) + len(asks)
                }
                
                print(f"✅ 获取成功:")
                print(f"   买盘档数: {len(bids)}")
                print(f"   卖盘档数: {len(asks)}")
                print(f"   总档数: {result['depth_levels']}")
                print(f"   时间戳: {result['last_update_id']}")
                
                if bids and asks:
                    spread = asks[0]["price"] - bids[0]["price"]
                    print(f"   最佳买价: {bids[0]['price']}")
                    print(f"   最佳卖价: {asks[0]['price']}")
                    print(f"   价差: {spread}")
                
                return result
                
        except Exception as e:
            print(f"❌ 获取OKX深度失败: {e}")
            return None
    
    async def compare_depths(self, symbol_binance: str, symbol_okx: str):
        """比较两个交易所的深度数据"""
        print(f"\\n🔍 比较深度数据:")
        print(f"   Binance: {symbol_binance}")
        print(f"   OKX: {symbol_okx}")
        print("-" * 50)
        
        # 并发获取数据
        binance_task = self.get_binance_depth(symbol_binance)
        okx_task = self.get_okx_depth(symbol_okx)
        
        binance_data, okx_data = await asyncio.gather(binance_task, okx_task)
        
        if binance_data and okx_data:
            print(f"\\n📊 对比结果:")
            print(f"   Binance最佳买价: {binance_data['bids'][0]['price']}")
            print(f"   OKX最佳买价: {okx_data['bids'][0]['price']}")
            print(f"   Binance最佳卖价: {binance_data['asks'][0]['price']}")
            print(f"   OKX最佳卖价: {okx_data['asks'][0]['price']}")
            
            # 计算价差
            binance_spread = binance_data['asks'][0]['price'] - binance_data['bids'][0]['price']
            okx_spread = okx_data['asks'][0]['price'] - okx_data['bids'][0]['price']
            
            print(f"   Binance价差: {binance_spread}")
            print(f"   OKX价差: {okx_spread}")
            
            # 计算套利机会
            if binance_data['asks'][0]['price'] < okx_data['bids'][0]['price']:
                arbitrage = okx_data['bids'][0]['price'] - binance_data['asks'][0]['price']
                print(f"   🚀 套利机会: 在Binance买入，在OKX卖出，价差 {arbitrage}")
            elif okx_data['asks'][0]['price'] < binance_data['bids'][0]['price']:
                arbitrage = binance_data['bids'][0]['price'] - okx_data['asks'][0]['price']
                print(f"   🚀 套利机会: 在OKX买入，在Binance卖出，价差 {arbitrage}")
            else:
                print("   📈 暂无明显套利机会")
    
    async def monitor_depth_changes(self, exchange: str, symbol: str, duration: int = 60):
        """监控深度变化"""
        print(f"\\n🔄 监控 {exchange} {symbol} 深度变化 ({duration}秒)")
        
        start_time = asyncio.get_event_loop().time()
        last_update_id = 0
        update_count = 0
        
        while (asyncio.get_event_loop().time() - start_time) < duration:
            if exchange.lower() == "binance":
                data = await self.get_binance_depth(symbol)
            elif exchange.lower() == "okx":
                data = await self.get_okx_depth(symbol)
            else:
                print(f"❌ 不支持的交易所: {exchange}")
                break
            
            if data and data['last_update_id'] != last_update_id:
                update_count += 1
                last_update_id = data['last_update_id']
                
                print(f"📊 更新 #{update_count} - {data['timestamp']}")
                print(f"   更新ID: {data['last_update_id']}")
                print(f"   最佳买价: {data['bids'][0]['price']}")
                print(f"   最佳卖价: {data['asks'][0]['price']}")
                print("-" * 30)
            
            await asyncio.sleep(5)  # 每5秒检查一次
        
        print(f"✅ 监控完成，共捕获 {update_count} 次更新")

async def main():
    """主函数"""
    client = SimpleDepthClient()
    
    try:
        print("🚀 MarketPrism 简单深度数据获取示例")
        print("=" * 50)
        
        await client.start()
        
        # 1. 获取Binance深度
        print("\\n1️⃣ 获取Binance深度数据:")
        await client.get_binance_depth("BTCUSDT", 400)
        
        await asyncio.sleep(1)
        
        # 2. 获取OKX深度
        print("\\n2️⃣ 获取OKX深度数据:")
        await client.get_okx_depth("BTC-USDT", 400)
        
        await asyncio.sleep(1)
        
        # 3. 比较两个交易所
        await client.compare_depths("BTCUSDT", "BTC-USDT")
        
        # 4. 可选：监控深度变化
        print(f"\\n4️⃣ 是否监控深度变化？(y/n): ", end="")
        # 自动选择不监控
        choice = "n"
        print(choice)
        
        if choice.lower() == 'y':
            await client.monitor_depth_changes("binance", "BTCUSDT", 30)
        
        print("\\n✅ 示例完成！")
        
    except Exception as e:
        print(f"❌ 运行异常: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(main())