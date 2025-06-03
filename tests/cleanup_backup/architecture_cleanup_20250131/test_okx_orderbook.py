#!/usr/bin/env python3
"""
OKX订单簿维护测试

测试OKX交易所的订单簿同步和增量更新功能
验证系统能够正确处理OKX的WebSocket数据流
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


class OKXOrderBookTester:
    def __init__(self):
        self.session = None
        
    async def start(self):
        """启动测试器"""
        # 设置代理环境变量（如果需要）
        import os
        proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        if not proxy:
            # 尝试使用常见的代理端口
            proxy = "http://127.0.0.1:1087"  # v2ray代理
            os.environ['HTTP_PROXY'] = proxy
            os.environ['HTTPS_PROXY'] = proxy
            print(f"🔗 设置代理: {proxy}")
        
        # 创建HTTP客户端
        connector = aiohttp.TCPConnector(limit=100)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=10)  # 减少超时时间
        )
        
    async def stop(self):
        """停止测试器"""
        if self.session:
            await self.session.close()
    
    async def test_okx_orderbook_maintenance(self):
        """测试OKX订单簿维护功能"""
        print("\n🚀 开始OKX订单簿维护测试")
        print("=" * 60)
        
        # 配置OKX交易所
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            base_url="https://www.okx.com",
            ws_url="wss://ws.okx.com:8443/ws/v5/public",
            symbols=["BTC-USDT", "ETH-USDT"],
            data_types=[DataType.ORDERBOOK]
        )
        
        # 创建标准化器和订单簿管理器
        normalizer = DataNormalizer()
        orderbook_manager = OrderBookManager(config, normalizer)
        orderbook_manager.session = self.session
        
        try:
            # 测试快照获取
            print("\n📊 测试OKX快照获取...")
            # 设置代理
            orderbook_manager.proxy = os.getenv('HTTP_PROXY')
            snapshot = await orderbook_manager._fetch_okx_snapshot("BTC-USDT")
            
            if snapshot:
                print(f"   ✅ 快照获取成功")
                print(f"   📈 买盘档位: {len(snapshot.bids)}")
                print(f"   📉 卖盘档位: {len(snapshot.asks)}")
                print(f"   🆔 更新ID: {snapshot.last_update_id}")
                print(f"   ⏰ 时间戳: {snapshot.timestamp}")
                
                if snapshot.bids and snapshot.asks:
                    best_bid = snapshot.bids[0].price
                    best_ask = snapshot.asks[0].price
                    spread = best_ask - best_bid
                    print(f"   💰 最佳买价: ${best_bid}")
                    print(f"   💰 最佳卖价: ${best_ask}")
                    print(f"   📏 价差: ${spread}")
                    
                    # 验证价格排序
                    bid_sorted = all(snapshot.bids[i].price >= snapshot.bids[i+1].price 
                                   for i in range(len(snapshot.bids)-1))
                    ask_sorted = all(snapshot.asks[i].price <= snapshot.asks[i+1].price 
                                   for i in range(len(snapshot.asks)-1))
                    
                    if bid_sorted and ask_sorted:
                        print(f"   ✅ 价格排序正确")
                    else:
                        print(f"   ❌ 价格排序错误")
                        return False
                else:
                    print(f"   ❌ 订单簿数据为空")
                    return False
            else:
                print(f"   ❌ 快照获取失败")
                return False
            
            # 测试增量更新解析
            print("\n🔄 测试OKX增量更新解析...")
            
            # 模拟OKX WebSocket增量更新数据
            mock_update_data = {
                "bids": [
                    ["67000.5", "0.1", "0", "1"],
                    ["67000.0", "0.0", "0", "0"]  # 删除价位
                ],
                "asks": [
                    ["67001.0", "0.2", "0", "1"],
                    ["67001.5", "0.0", "0", "0"]  # 删除价位
                ],
                "ts": str(int(time.time() * 1000))
            }
            
            # 使用正确的方法名
            update = orderbook_manager._parse_okx_update("BTC-USDT", mock_update_data)
            
            if update:
                print(f"   ✅ 增量更新解析成功")
                print(f"   📈 买盘更新: {len(update.bids)}")
                print(f"   📉 卖盘更新: {len(update.asks)}")
                print(f"   🆔 更新ID: {update.last_update_id}")
                print(f"   ⏰ 时间戳: {update.timestamp}")
                
                # 验证更新数据
                for bid in update.bids:
                    print(f"   📈 买盘更新: ${bid.price} @ {bid.quantity}")
                for ask in update.asks:
                    print(f"   📉 卖盘更新: ${ask.price} @ {ask.quantity}")
            else:
                print(f"   ❌ 增量更新解析失败")
                return False
            
            # 测试序列验证
            print("\n🔍 测试OKX序列验证...")
            
            # 创建模拟状态
            from marketprism_collector.orderbook_manager import OrderBookState
            state = OrderBookState(
                symbol="BTC-USDT",
                exchange="okx",
                last_update_id=int(time.time() * 1000) - 1000  # 1秒前的时间戳
            )
            
            # 创建模拟更新
            from marketprism_collector.orderbook_manager import OrderBookUpdate
            update = OrderBookUpdate(
                symbol="BTC-USDT",
                exchange="okx",
                first_update_id=int(time.time() * 1000),
                last_update_id=int(time.time() * 1000),
                bids=[PriceLevel(price=Decimal("67000"), quantity=Decimal("0.1"))],
                asks=[PriceLevel(price=Decimal("67001"), quantity=Decimal("0.1"))],
                timestamp=datetime.utcnow()
            )
            
            # 临时设置配置
            orderbook_manager.config = config
            orderbook_manager.orderbook_states = {"BTC-USDT": state}
            
            is_valid = orderbook_manager._validate_update_sequence(state, update)
            
            if is_valid:
                print(f"   ✅ 序列验证成功")
                print(f"   🔗 状态ID: {state.last_update_id}")
                print(f"   🔗 更新ID: {update.last_update_id}")
            else:
                print(f"   ❌ 序列验证失败")
                return False
            
            print("\n🎉 OKX订单簿维护测试完成！")
            print("=" * 60)
            print("✅ 所有测试通过")
            print("📊 OKX订单簿维护功能正常工作")
            
            return True
            
        except Exception as e:
            print(f"\n❌ 测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_okx_vs_binance_comparison(self):
        """对比OKX和Binance的订单簿数据"""
        print("\n🔄 开始OKX vs Binance订单簿对比测试")
        print("=" * 60)
        
        try:
            # 配置OKX
            okx_config = ExchangeConfig(
                exchange=Exchange.OKX,
                market_type=MarketType.SPOT,
                base_url="https://www.okx.com",
                ws_url="wss://ws.okx.com:8443/ws/v5/public",
                symbols=["BTC-USDT"],
                data_types=[DataType.ORDERBOOK]
            )
            
            # 配置Binance
            binance_config = ExchangeConfig(
                exchange=Exchange.BINANCE,
                market_type=MarketType.SPOT,
                base_url="https://api.binance.com",
                ws_url="wss://stream.binance.com:9443/ws",
                symbols=["BTCUSDT"],
                data_types=[DataType.ORDERBOOK]
            )
            
            # 创建管理器
            normalizer = DataNormalizer()
            okx_manager = OrderBookManager(okx_config, normalizer)
            binance_manager = OrderBookManager(binance_config, normalizer)
            
            okx_manager.session = self.session
            binance_manager.session = self.session
            
            # 获取快照
            print("\n📊 获取OKX快照...")
            okx_snapshot = await okx_manager._fetch_okx_snapshot("BTC-USDT")
            
            print("📊 获取Binance快照...")
            binance_snapshot = await binance_manager._fetch_binance_snapshot("BTCUSDT")
            
            if okx_snapshot and binance_snapshot:
                print("\n📈 订单簿对比结果:")
                print(f"   OKX 买盘档位: {len(okx_snapshot.bids)}")
                print(f"   Binance 买盘档位: {len(binance_snapshot.bids)}")
                print(f"   OKX 卖盘档位: {len(okx_snapshot.asks)}")
                print(f"   Binance 卖盘档位: {len(binance_snapshot.asks)}")
                
                if okx_snapshot.bids and binance_snapshot.bids:
                    okx_best_bid = okx_snapshot.bids[0].price
                    binance_best_bid = binance_snapshot.bids[0].price
                    bid_diff = abs(okx_best_bid - binance_best_bid)
                    
                    print(f"   OKX 最佳买价: ${okx_best_bid}")
                    print(f"   Binance 最佳买价: ${binance_best_bid}")
                    print(f"   买价差异: ${bid_diff}")
                    
                if okx_snapshot.asks and binance_snapshot.asks:
                    okx_best_ask = okx_snapshot.asks[0].price
                    binance_best_ask = binance_snapshot.asks[0].price
                    ask_diff = abs(okx_best_ask - binance_best_ask)
                    
                    print(f"   OKX 最佳卖价: ${okx_best_ask}")
                    print(f"   Binance 最佳卖价: ${binance_best_ask}")
                    print(f"   卖价差异: ${ask_diff}")
                    
                print("\n✅ 对比测试完成")
                return True
            else:
                print("❌ 无法获取快照数据")
                return False
                
        except Exception as e:
            print(f"\n❌ 对比测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """主函数"""
    tester = OKXOrderBookTester()
    
    try:
        await tester.start()
        
        # 运行测试
        success1 = await tester.test_okx_orderbook_maintenance()
        success2 = await tester.test_okx_vs_binance_comparison()
        
        if success1 and success2:
            print("\n🎉 所有测试通过！OKX订单簿维护功能正常工作")
            return True
        else:
            print("\n❌ 部分测试失败")
            return False
            
    finally:
        await tester.stop()


if __name__ == "__main__":
    asyncio.run(main())