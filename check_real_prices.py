#!/usr/bin/env python3
"""
检查系统中的实际BTC价格
"""

import asyncio
import nats
import json

async def check_actual_prices():
    nc = await nats.connect('nats://localhost:4222')
    
    print('🔍 检查系统中的实际BTC价格...')
    print('真实BTC价格应该是: $105,839.50')
    print()
    
    count = 0
    
    async def message_handler(msg):
        nonlocal count
        try:
            data = json.loads(msg.data.decode())
            if 'bids' in data and len(data['bids']) > 0:
                # 处理两种数据格式
                bid = data['bids'][0]
                if isinstance(bid, dict) and 'price' in bid:
                    # 对象格式: {"price": "105903.9", "quantity": "1.09281899"}
                    price = float(bid['price'])
                elif isinstance(bid, list) and len(bid) >= 2:
                    # 数组格式: [105903.9, 1.09281899]
                    price = float(bid[0])
                else:
                    print(f'   ❌ 未知的bid格式: {bid}')
                    return

                print(f'📊 {msg.subject}')
                print(f'   最高买价: ${price:,.2f}')
                print(f'   与真实价格差异: ${abs(price - 105839.50):,.2f}')
                if abs(price - 105839.50) > 50000:
                    print('   🚨 这是Mock/测试数据！')
                else:
                    print('   ✅ 价格接近真实值')
                print()
                count += 1
                if count >= 3:
                    await nc.close()
        except Exception as e:
            print(f'解析错误: {e}')
    
    await nc.subscribe('orderbook-data.*.*.BTCUSDT', cb=message_handler)
    await asyncio.sleep(25)
    await nc.close()
    
    if count == 0:
        print('❌ 没有收到任何数据')

if __name__ == "__main__":
    asyncio.run(check_actual_prices())
