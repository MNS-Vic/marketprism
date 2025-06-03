#!/usr/bin/env python3
import asyncio
import aiohttp
import json
from decimal import Decimal
import os

async def test_ethusdt():
    proxy = 'http://127.0.0.1:1087'
    
    # 获取本地订单簿
    async with aiohttp.ClientSession() as session:
        async with session.get('http://localhost:8080/api/v1/orderbook/binance/ETHUSDT?depth=5') as resp:
            local = await resp.json()
        
        # 获取实时快照
        async with session.get('https://api.binance.com/api/v3/depth?symbol=ETHUSDT&limit=5', proxy=proxy) as resp:
            snapshot = await resp.json()
    
    print('=== ETHUSDT 一致性测试 ===')
    print(f'本地更新ID: {local.get("last_update_id")}')
    print(f'快照更新ID: {snapshot.get("lastUpdateId")}')
    print(f'差异: {snapshot.get("lastUpdateId", 0) - local.get("last_update_id", 0)}')
    
    print(f'本地最优买价: {local["bids"][0]["price"]}')
    print(f'快照最优买价: {snapshot["bids"][0][0]}')
    print(f'买价差异: {abs(Decimal(local["bids"][0]["price"]) - Decimal(snapshot["bids"][0][0]))}')
    
    print(f'本地最优卖价: {local["asks"][0]["price"]}')
    print(f'快照最优卖价: {snapshot["asks"][0][0]}')
    print(f'卖价差异: {abs(Decimal(local["asks"][0]["price"]) - Decimal(snapshot["asks"][0][0]))}')
    
    # 检查前5档的匹配情况
    matches = 0
    for i in range(5):
        local_bid_price = Decimal(local["bids"][i]["price"])
        snapshot_bid_price = Decimal(snapshot["bids"][i][0])
        if local_bid_price == snapshot_bid_price:
            matches += 1
    
    print(f'前5档买单价格匹配: {matches}/5')

if __name__ == "__main__":
    asyncio.run(test_ethusdt()) 