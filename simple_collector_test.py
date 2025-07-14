#!/usr/bin/env python3
"""
简化的数据收集器测试
用于验证NATS推送和永续合约数据
"""

import asyncio
import sys
import os
sys.path.insert(0, '/home/ubuntu/marketprism/services/data-collector')

from collector.nats_publisher import NATSPublisher
from collector.normalizer import DataNormalizer
from collector.data_types import EnhancedOrderBook, PriceLevel
from decimal import Decimal
from datetime import datetime, timezone

async def create_test_orderbook(exchange: str, market_type: str, symbol: str) -> EnhancedOrderBook:
    """创建测试订单簿数据"""
    
    # 创建测试价格档位
    bids = [
        PriceLevel(price=Decimal("50000.00"), quantity=Decimal("1.5")),
        PriceLevel(price=Decimal("49999.50"), quantity=Decimal("2.0")),
        PriceLevel(price=Decimal("49999.00"), quantity=Decimal("1.8")),
    ]
    
    asks = [
        PriceLevel(price=Decimal("50001.00"), quantity=Decimal("1.2")),
        PriceLevel(price=Decimal("50001.50"), quantity=Decimal("1.8")),
        PriceLevel(price=Decimal("50002.00"), quantity=Decimal("2.2")),
    ]
    
    # 创建增强订单簿
    orderbook = EnhancedOrderBook(
        exchange_name=exchange,
        symbol_name=symbol,
        market_type=market_type,
        bids=bids,
        asks=asks,
        timestamp=datetime.now(timezone.utc),
        last_update_id=12345,
        checksum=12345
    )
    
    return orderbook

async def test_nats_publishing():
    """测试NATS发布功能"""
    print("🧪 启动简化的NATS发布测试")
    print("=" * 50)
    
    # 初始化组件
    normalizer = DataNormalizer()
    publisher = NATSPublisher(normalizer=normalizer)
    
    try:
        # 连接NATS
        await publisher.connect()
        print("✅ NATS连接成功")
        
        # 测试数据配置
        test_configs = [
            ("binance_spot", "spot", "BTCUSDT"),
            ("binance_derivatives", "perpetual", "BTCUSDT"),
            ("okx_spot", "spot", "BTC-USDT"),
            ("okx_derivatives", "perpetual", "BTC-USDT-SWAP"),
        ]
        
        print(f"\n📡 开始发布测试数据...")
        
        for exchange, market_type, symbol in test_configs:
            print(f"\n🔄 测试 {exchange}.{market_type}.{symbol}")
            
            # 创建测试订单簿
            orderbook = await create_test_orderbook(exchange, market_type, symbol)
            
            # 发布到NATS
            success = await publisher.publish_enhanced_orderbook(orderbook)
            
            if success:
                print(f"   ✅ 发布成功")
            else:
                print(f"   ❌ 发布失败")
            
            # 等待一下
            await asyncio.sleep(1)
        
        print(f"\n📊 发布统计:")
        stats = publisher.get_stats()
        print(f"   总发布: {stats['total_published']}")
        print(f"   成功: {stats['successful_published']}")
        print(f"   失败: {stats['failed_published']}")
        print(f"   成功率: {stats['success_rate']:.1f}%")
        
        # 持续发布一段时间
        print(f"\n🔄 持续发布30秒...")
        for i in range(30):
            for exchange, market_type, symbol in test_configs:
                orderbook = await create_test_orderbook(exchange, market_type, symbol)
                await publisher.publish_enhanced_orderbook(orderbook)
            await asyncio.sleep(1)
            if (i + 1) % 10 == 0:
                print(f"   已发布 {i + 1} 轮数据")
        
        print(f"\n📊 最终统计:")
        stats = publisher.get_stats()
        print(f"   总发布: {stats['total_published']}")
        print(f"   成功: {stats['successful_published']}")
        print(f"   失败: {stats['failed_published']}")
        print(f"   成功率: {stats['success_rate']:.1f}%")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if hasattr(publisher, 'close'):
            await publisher.close()
        elif hasattr(publisher, 'disconnect'):
            await publisher.disconnect()
        print("🔌 NATS连接已关闭")

if __name__ == "__main__":
    asyncio.run(test_nats_publishing())
