#!/usr/bin/env python3
"""
订单簿一致性测试

测试流程：
1. 获取全量深度快照A
2. 应用一系列增量更新
3. 获取全量深度快照B
4. 对比快照B和增量更新后的订单簿是否一致
"""

import asyncio
import sys
import os
import time
import json
import aiohttp
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services/python-collector/src'))

from marketprism_collector.orderbook_manager import OrderBookManager, OrderBookSnapshot
from marketprism_collector.normalizer import DataNormalizer
from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType, PriceLevel


class OrderBookConsistencyTester:
    def __init__(self):
        self.session = None
        self.proxy = "http://127.0.0.1:1087"
    
    async def start(self):
        """启动测试器"""
        # 设置代理环境变量
        os.environ['HTTP_PROXY'] = self.proxy
        os.environ['HTTPS_PROXY'] = self.proxy
        
        # 创建HTTP客户端
        connector = aiohttp.TCPConnector(limit=100)
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            connector=connector
        )
    
    async def stop(self):
        """停止测试器"""
        if self.session:
            await self.session.close()
    
    async def fetch_binance_snapshot(self, symbol: str, limit: int = 1000) -> Optional[OrderBookSnapshot]:
        """获取Binance订单簿快照"""
        try:
            url = "https://api.binance.com/api/v3/depth"
            params = {
                "symbol": symbol.replace("-", ""),
                "limit": limit
            }
            
            async with self.session.get(url, params=params, proxy=self.proxy) as response:
                if response.status != 200:
                    print(f"❌ 获取快照失败: {response.status} - {await response.text()}")
                    return None
                
                data = await response.json()
                
                bids = [
                    PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                    for price, qty in data["bids"]
                ]
                asks = [
                    PriceLevel(price=Decimal(price), quantity=Decimal(qty))
                    for price, qty in data["asks"]
                ]
                
                return OrderBookSnapshot(
                    symbol=symbol,
                    exchange="binance",
                    last_update_id=data["lastUpdateId"],
                    bids=bids,
                    asks=asks,
                    timestamp=datetime.utcnow()
                )
                
        except Exception as e:
            print(f"❌ 获取快照异常: {e}")
            return None
    
    def compare_orderbooks(self, snapshot1: OrderBookSnapshot, snapshot2: OrderBookSnapshot, 
                          updated_orderbook: OrderBookSnapshot, symbol: str) -> Dict:
        """对比两个快照和增量更新后的订单簿"""
        print(f"\n📊 对比订单簿一致性 - {symbol}")
        print(f"快照A更新ID: {snapshot1.last_update_id}")
        print(f"快照B更新ID: {snapshot2.last_update_id}")
        print(f"增量更新后ID: {updated_orderbook.last_update_id}")
        
        # 转换为字典便于比较
        def orderbook_to_dict(snapshot: OrderBookSnapshot) -> Tuple[Dict, Dict]:
            bids_dict = {level.price: level.quantity for level in snapshot.bids}
            asks_dict = {level.price: level.quantity for level in snapshot.asks}
            return bids_dict, asks_dict
        
        snapshot2_bids, snapshot2_asks = orderbook_to_dict(snapshot2)
        updated_bids, updated_asks = orderbook_to_dict(updated_orderbook)
        
        # 比较买单
        bid_differences = []
        all_bid_prices = set(snapshot2_bids.keys()) | set(updated_bids.keys())
        
        for price in all_bid_prices:
            snapshot_qty = snapshot2_bids.get(price, Decimal('0'))
            updated_qty = updated_bids.get(price, Decimal('0'))
            
            if snapshot_qty != updated_qty:
                bid_differences.append({
                    'price': price,
                    'snapshot_qty': snapshot_qty,
                    'updated_qty': updated_qty,
                    'difference': updated_qty - snapshot_qty
                })
        
        # 比较卖单
        ask_differences = []
        all_ask_prices = set(snapshot2_asks.keys()) | set(updated_asks.keys())
        
        for price in all_ask_prices:
            snapshot_qty = snapshot2_asks.get(price, Decimal('0'))
            updated_qty = updated_asks.get(price, Decimal('0'))
            
            if snapshot_qty != updated_qty:
                ask_differences.append({
                    'price': price,
                    'snapshot_qty': snapshot_qty,
                    'updated_qty': updated_qty,
                    'difference': updated_qty - snapshot_qty
                })
        
        # 统计结果
        result = {
            'is_consistent': len(bid_differences) == 0 and len(ask_differences) == 0,
            'bid_differences_count': len(bid_differences),
            'ask_differences_count': len(ask_differences),
            'bid_differences': bid_differences[:10],  # 只显示前10个差异
            'ask_differences': ask_differences[:10],
            'snapshot1_update_id': snapshot1.last_update_id,
            'snapshot2_update_id': snapshot2.last_update_id,
            'updated_update_id': updated_orderbook.last_update_id,
            'total_updates_applied': updated_orderbook.last_update_id - snapshot1.last_update_id
        }
        
        # 打印结果
        if result['is_consistent']:
            print("✅ 订单簿完全一致！")
        else:
            print(f"❌ 发现不一致:")
            print(f"   - 买单差异: {result['bid_differences_count']} 个价位")
            print(f"   - 卖单差异: {result['ask_differences_count']} 个价位")
            
            if bid_differences:
                print("   - 买单差异示例:")
                for diff in bid_differences[:3]:
                    print(f"     价格{diff['price']}: 快照{diff['snapshot_qty']} vs 更新{diff['updated_qty']}")
            
            if ask_differences:
                print("   - 卖单差异示例:")
                for diff in ask_differences[:3]:
                    print(f"     价格{diff['price']}: 快照{diff['snapshot_qty']} vs 更新{diff['updated_qty']}")
        
        return result


async def test_orderbook_consistency():
    """测试订单簿一致性"""
    print("=== 订单簿一致性测试 ===")
    
    tester = OrderBookConsistencyTester()
    await tester.start()
    
    # 创建订单簿管理器
    exchange_config = ExchangeConfig(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        enabled=True,
        base_url="https://api.binance.com",
        ws_url="wss://stream.binance.com:9443/ws",
        symbols=["BTCUSDT"],
        data_types=[DataType.ORDERBOOK],
        depth_limit=1000,
        snapshot_interval=60
    )
    
    normalizer = DataNormalizer()
    orderbook_manager = OrderBookManager(exchange_config, normalizer)
    
    symbol = "BTCUSDT"
    
    try:
        print(f"\n1. 获取初始快照A - {symbol}")
        snapshot_a = await tester.fetch_binance_snapshot(symbol)
        if not snapshot_a:
            print("❌ 无法获取初始快照")
            return
        
        print(f"✅ 快照A获取成功: 更新ID {snapshot_a.last_update_id}")
        print(f"   - 买单: {len(snapshot_a.bids)} 档")
        print(f"   - 卖单: {len(snapshot_a.asks)} 档")
        
        print(f"\n2. 启动订单簿管理器并模拟增量更新")
        await orderbook_manager.start([symbol])
        
        # 手动设置初始状态
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot_a
        state.last_update_id = snapshot_a.last_update_id
        state.is_synced = True
        
        print(f"✅ 订单簿管理器初始化完成")
        
        print(f"\n3. 等待并收集WebSocket增量更新...")
        
        # 创建WebSocket连接来收集更新
        from marketprism_collector.exchanges import ExchangeAdapterFactory
        adapter = ExchangeAdapterFactory.create_adapter(exchange_config)
        
        updates_received = []
        
        async def handle_raw_depth(exchange: str, symbol: str, raw_data: dict):
            """处理原始深度数据"""
            updates_received.append(raw_data)
            
            # 应用到订单簿管理器
            enhanced_orderbook = await orderbook_manager.process_update(symbol, raw_data)
            if enhanced_orderbook:
                print(f"📈 更新应用成功: ID {enhanced_orderbook.last_update_id} (总计:{len(updates_received)})")
            else:
                print(f"⚠️  更新缓冲或失败: ID {raw_data.get('u', 'N/A')}")
        
        adapter.register_raw_callback('depth', handle_raw_depth)
        
        # 启动WebSocket
        await adapter.start()
        
        # 收集30秒的更新
        print("⏳ 收集30秒的增量更新...")
        start_time = time.time()
        while time.time() - start_time < 30:
            await asyncio.sleep(1)
            if len(updates_received) > 0 and len(updates_received) % 50 == 0:
                print(f"   已收集 {len(updates_received)} 个更新")
        
        await adapter.stop()
        
        print(f"\n4. 获取最终快照B")
        snapshot_b = await tester.fetch_binance_snapshot(symbol)
        if not snapshot_b:
            print("❌ 无法获取最终快照")
            return
        
        print(f"✅ 快照B获取成功: 更新ID {snapshot_b.last_update_id}")
        
        print(f"\n5. 获取增量更新后的订单簿")
        current_orderbook = orderbook_manager.get_current_orderbook(symbol)
        if not current_orderbook:
            print("❌ 无法获取当前订单簿")
            return
        
        # 转换为快照格式便于比较
        updated_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=current_orderbook.last_update_id,
            bids=current_orderbook.bids,
            asks=current_orderbook.asks,
            timestamp=current_orderbook.timestamp
        )
        
        print(f"✅ 当前订单簿: 更新ID {updated_snapshot.last_update_id}")
        
        print(f"\n6. 对比一致性")
        result = tester.compare_orderbooks(snapshot_a, snapshot_b, updated_snapshot, symbol)
        
        print(f"\n📊 测试总结:")
        print(f"   - 收集的更新数量: {len(updates_received)}")
        print(f"   - 应用的更新数量: {result['total_updates_applied']}")
        print(f"   - 订单簿是否一致: {'✅ 是' if result['is_consistent'] else '❌ 否'}")
        
        if not result['is_consistent']:
            print(f"   - 买单差异数量: {result['bid_differences_count']}")
            print(f"   - 卖单差异数量: {result['ask_differences_count']}")
        
        # 获取管理器统计
        manager_stats = orderbook_manager.get_stats()
        print(f"   - 管理器统计: {manager_stats['global_stats']}")
        
        await orderbook_manager.stop()
        
        return result['is_consistent']
        
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await tester.stop()


if __name__ == "__main__":
    success = asyncio.run(test_orderbook_consistency())
    if success:
        print("\n🎉 订单簿一致性测试通过！")
    else:
        print("\n💥 订单簿一致性测试失败！") 