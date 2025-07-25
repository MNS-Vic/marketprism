#!/usr/bin/env python3
"""
展示MarketPrism Collector的OrderBook Manager维护的实时订单簿格式

这个脚本演示了订单簿的数据结构和格式
"""

import asyncio
import sys
import os
import json
from datetime import datetime
from decimal import Decimal

# 设置代理（如果需要）
os.environ['http_proxy'] = 'http://127.0.0.1:1087'
os.environ['https_proxy'] = 'http://127.0.0.1:1087'

sys.path.append('services/python-collector/src')

from marketprism_collector.data_types import (
    Exchange, MarketType, ExchangeConfig, DataType, 
    EnhancedOrderBook, PriceLevel, OrderBookUpdateType
)
from marketprism_collector.normalizer import DataNormalizer
from marketprism_collector.orderbook_manager import OrderBookManager

def print_orderbook_format(orderbook: EnhancedOrderBook):
    """打印订单簿格式"""
    print("=" * 80)
    print("📊 MarketPrism 实时订单簿格式")
    print("=" * 80)
    
    print(f"🏢 交易所: {orderbook.exchange_name}")
    print(f"💱 交易对: {orderbook.symbol_name}")
    print(f"🔄 更新类型: {orderbook.update_type.value}")
    print(f"🆔 更新ID: {orderbook.last_update_id}")
    print(f"📊 深度档位: {orderbook.depth_levels}")
    print(f"⏰ 时间戳: {orderbook.timestamp}")
    print(f"📥 采集时间: {orderbook.collected_at}")
    print(f"⚙️ 处理时间: {orderbook.processed_at}")
    print(f"✅ 数据有效: {orderbook.is_valid}")
    
    if orderbook.checksum:
        print(f"🔐 校验和: {orderbook.checksum}")
    
    print("\n" + "=" * 40)
    print("📈 买单 (Bids) - 按价格从高到低排序")
    print("=" * 40)
    print(f"{'档位':<4} {'价格':<15} {'数量':<15} {'总价值':<15}")
    print("-" * 60)
    
    for i, bid in enumerate(orderbook.bids[:10]):  # 显示前10档
        total_value = bid.price * bid.quantity
        print(f"{i+1:<4} {bid.price:<15} {bid.quantity:<15} {total_value:<15}")
    
    if len(orderbook.bids) > 10:
        print(f"... 还有 {len(orderbook.bids) - 10} 档买单")
    
    print("\n" + "=" * 40)
    print("📉 卖单 (Asks) - 按价格从低到高排序")
    print("=" * 40)
    print(f"{'档位':<4} {'价格':<15} {'数量':<15} {'总价值':<15}")
    print("-" * 60)
    
    for i, ask in enumerate(orderbook.asks[:10]):  # 显示前10档
        total_value = ask.price * ask.quantity
        print(f"{i+1:<4} {ask.price:<15} {ask.quantity:<15} {total_value:<15}")
    
    if len(orderbook.asks) > 10:
        print(f"... 还有 {len(orderbook.asks) - 10} 档卖单")
    
    # 计算价差
    if orderbook.bids and orderbook.asks:
        best_bid = orderbook.bids[0].price
        best_ask = orderbook.asks[0].price
        spread = best_ask - best_bid
        spread_percent = (spread / best_bid) * 100
        
        print("\n" + "=" * 40)
        print("💰 市场信息")
        print("=" * 40)
        print(f"最佳买价: ${best_bid}")
        print(f"最佳卖价: ${best_ask}")
        print(f"买卖价差: ${spread}")
        print(f"价差百分比: {spread_percent:.4f}%")
    
    print("\n" + "=" * 40)
    print("📋 数据结构信息")
    print("=" * 40)
    print("订单簿数据结构包含以下字段:")
    print("- exchange_name: 交易所名称")
    print("- symbol_name: 交易对名称")
    print("- last_update_id: 最后更新ID")
    print("- bids: 买单列表 [PriceLevel(price, quantity)]")
    print("- asks: 卖单列表 [PriceLevel(price, quantity)]")
    print("- timestamp: 数据时间戳")
    print("- update_type: 更新类型 (snapshot/update/delta)")
    print("- depth_levels: 深度档位数")
    print("- checksum: 数据校验和 (可选)")
    print("- is_valid: 数据有效性标志")
    print("- collected_at: 数据采集时间")
    print("- processed_at: 数据处理时间")

def print_json_format(orderbook: EnhancedOrderBook):
    """打印JSON格式的订单簿"""
    print("\n" + "=" * 80)
    print("📄 JSON格式示例 (前5档)")
    print("=" * 80)
    
    # 创建简化的JSON格式
    json_data = {
        "exchange_name": orderbook.exchange_name,
        "symbol_name": orderbook.symbol_name,
        "last_update_id": orderbook.last_update_id,
        "timestamp": orderbook.timestamp.isoformat() + 'Z',
        "update_type": orderbook.update_type.value,
        "depth_levels": orderbook.depth_levels,
        "bids": [
            {
                "price": str(bid.price),
                "quantity": str(bid.quantity)
            }
            for bid in orderbook.bids[:5]
        ],
        "asks": [
            {
                "price": str(ask.price),
                "quantity": str(ask.quantity)
            }
            for ask in orderbook.asks[:5]
        ],
        "is_valid": orderbook.is_valid,
        "collected_at": orderbook.collected_at.isoformat() + 'Z'
    }
    
    print(json.dumps(json_data, indent=2, ensure_ascii=False))

def create_sample_orderbook():
    """创建示例订单簿数据"""
    print("📋 创建示例订单簿数据...")
    
    # 创建示例买单和卖单
    bids = []
    asks = []
    
    base_price = Decimal("45000.00")  # BTC基础价格
    
    # 生成买单 (价格递减)
    for i in range(20):
        price = base_price - Decimal(str(i * 0.5))
        quantity = Decimal(str(round(0.1 + i * 0.05, 3)))
        bids.append(PriceLevel(price=price, quantity=quantity))
    
    # 生成卖单 (价格递增)
    for i in range(20):
        price = base_price + Decimal(str((i + 1) * 0.5))
        quantity = Decimal(str(round(0.1 + i * 0.05, 3)))
        asks.append(PriceLevel(price=price, quantity=quantity))
    
    # 创建增强订单簿
    orderbook = EnhancedOrderBook(
        exchange_name="binance",
        symbol_name="BTCUSDT",
        last_update_id=12345678,
        bids=bids,
        asks=asks,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        update_type=OrderBookUpdateType.SNAPSHOT,
        depth_levels=len(bids) + len(asks),
        checksum=987654321,
        is_valid=True
    )
    
    return orderbook

async def main():
    """主函数"""
    print("🎯 MarketPrism OrderBook Manager 订单簿格式演示")
    print("=" * 80)
    
    # 使用示例数据演示
    sample_orderbook = create_sample_orderbook()
    print_orderbook_format(sample_orderbook)
    print_json_format(sample_orderbook)
    
    print("\n" + "=" * 80)
    print("💡 OrderBook Manager 工作原理")
    print("=" * 80)
    print("1. 快照获取: 通过REST API获取完整订单簿快照")
    print("2. 增量更新: 通过WebSocket接收实时增量更新")
    print("3. 本地维护: 将增量更新应用到本地快照")
    print("4. 数据验证: 通过update_id序列验证数据完整性")
    print("5. 定期同步: 定期重新获取快照确保数据准确性")
    
    print("\n支持的交易所:")
    print("- Binance: 使用官方推荐的快照+增量同步算法")
    print("- OKX: 使用WebSocket + 定时快照同步模式")
    print("- Deribit: 支持期权和期货订单簿")
    
    print("\n数据特点:")
    print("- 400档深度: 统一使用400档深度提高性能")
    print("- 实时更新: 毫秒级延迟的订单簿更新")
    print("- 数据完整性: 通过序列ID确保无数据丢失")
    print("- 容错机制: 自动重连和数据重同步")

if __name__ == "__main__":
    asyncio.run(main())