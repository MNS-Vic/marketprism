#!/usr/bin/env python3
"""
直接从OrderBook Manager获取深度数据示例

演示如何直接使用OrderBook Manager获取实时深度数据
"""

import asyncio
import sys
import os

# 设置代理
os.environ['http_proxy'] = 'http://127.0.0.1:1087'
os.environ['https_proxy'] = 'http://127.0.0.1:1087'

sys.path.append('services/python-collector/src')

from marketprism_collector.types import Exchange, MarketType, ExchangeConfig, DataType
from marketprism_collector.normalizer import DataNormalizer
from marketprism_collector.orderbook_manager import OrderBookManager

class DirectDepthClient:
    """直接深度数据客户端"""
    
    def __init__(self):
        self.managers = {}
        self.normalizer = DataNormalizer()
    
    async def setup_exchange(self, exchange: Exchange, symbols: list):
        """设置交易所连接"""
        config = ExchangeConfig(
            exchange=exchange,
            market_type=MarketType.SPOT,
            base_url=self._get_base_url(exchange),
            ws_url=self._get_ws_url(exchange),
            data_types=[DataType.ORDERBOOK],
            symbols=symbols,
            depth_limit=400,
            snapshot_interval=300
        )
        
        manager = OrderBookManager(config, self.normalizer)
        await manager.start(symbols)
        
        self.managers[exchange.value] = manager
        return manager
    
    def _get_base_url(self, exchange: Exchange) -> str:
        """获取交易所API基础URL"""
        urls = {
            Exchange.BINANCE: "https://api.binance.com",
            Exchange.OKX: "https://www.okx.com"
        }
        return urls.get(exchange, "")
    
    def _get_ws_url(self, exchange: Exchange) -> str:
        """获取交易所WebSocket URL"""
        urls = {
            Exchange.BINANCE: "wss://stream.binance.com:9443/ws",
            Exchange.OKX: "wss://ws.okx.com:8443/ws/v5/public"
        }
        return urls.get(exchange, "")
    
    async def get_current_orderbook(self, exchange: str, symbol: str):
        """获取当前订单簿"""
        manager = self.managers.get(exchange)
        if not manager:
            print(f"❌ 交易所 {exchange} 未初始化")
            return None
        
        orderbook = manager.get_current_orderbook(symbol)
        return orderbook
    
    async def monitor_depth_changes(self, exchange: str, symbol: str, duration: int = 60):
        """监控深度变化"""
        print(f"🔍 开始监控 {exchange} {symbol} 深度变化 ({duration}秒)")
        
        start_time = asyncio.get_event_loop().time()
        last_update_id = 0
        update_count = 0
        
        while (asyncio.get_event_loop().time() - start_time) < duration:
            orderbook = await self.get_current_orderbook(exchange, symbol)
            
            if orderbook and orderbook.last_update_id != last_update_id:
                update_count += 1
                last_update_id = orderbook.last_update_id
                
                print(f"📊 更新 #{update_count}")
                print(f"   更新ID: {orderbook.last_update_id}")
                print(f"   深度档数: {orderbook.depth_levels}")
                print(f"   最佳买价: {orderbook.bids[0].price if orderbook.bids else 'N/A'}")
                print(f"   最佳卖价: {orderbook.asks[0].price if orderbook.asks else 'N/A'}")
                
                if orderbook.bids and orderbook.asks:
                    spread = orderbook.asks[0].price - orderbook.bids[0].price
                    print(f"   价差: {spread}")
                
                print(f"   时间: {orderbook.timestamp}")
                print("-" * 40)
            
            await asyncio.sleep(1)  # 每秒检查一次
        
        print(f"✅ 监控完成，共捕获 {update_count} 次更新")
    
    async def get_depth_statistics(self, exchange: str, symbol: str):
        """获取深度统计信息"""
        manager = self.managers.get(exchange)
        if not manager:
            return None
        
        stats = manager.get_stats()
        symbol_stats = stats.get('symbol_stats', {}).get(symbol, {})
        
        return {
            'exchange': exchange,
            'symbol': symbol,
            'is_synced': symbol_stats.get('is_synced', False),
            'total_updates': symbol_stats.get('total_updates', 0),
            'last_update_id': symbol_stats.get('last_update_id', 0),
            'buffer_size': symbol_stats.get('buffer_size', 0),
            'error_count': symbol_stats.get('error_count', 0),
            'global_stats': stats.get('global_stats', {})
        }
    
    async def cleanup(self):
        """清理资源"""
        for manager in self.managers.values():
            await manager.stop()

async def main():
    """主函数"""
    client = DirectDepthClient()
    
    try:
        print("🚀 MarketPrism 直接深度数据获取示例")
        print("=" * 50)
        
        # 1. 设置Binance连接
        print("\n📡 设置Binance连接...")
        await client.setup_exchange(Exchange.BINANCE, ["BTCUSDT", "ETHUSDT"])
        
        # 等待初始化
        await asyncio.sleep(5)
        
        # 2. 获取当前订单簿
        print("\n📊 获取当前订单簿:")
        orderbook = await client.get_current_orderbook("binance", "BTCUSDT")
        if orderbook:
            print(f"✅ Binance BTCUSDT 订单簿:")
            print(f"   买盘档数: {len(orderbook.bids)}")
            print(f"   卖盘档数: {len(orderbook.asks)}")
            print(f"   总深度: {orderbook.depth_levels}")
            print(f"   更新ID: {orderbook.last_update_id}")
            print(f"   同步状态: {'已同步' if orderbook else '未同步'}")
        
        # 3. 获取统计信息
        print("\n📈 获取统计信息:")
        stats = await client.get_depth_statistics("binance", "BTCUSDT")
        if stats:
            print(f"✅ 统计信息:")
            print(f"   同步状态: {stats['is_synced']}")
            print(f"   总更新数: {stats['total_updates']}")
            print(f"   缓冲区大小: {stats['buffer_size']}")
            print(f"   错误计数: {stats['error_count']}")
        
        # 4. 监控深度变化（可选）
        print(f"\n🔄 是否监控深度变化？(y/n): ", end="")
        # 自动选择不监控，避免长时间运行
        choice = "n"
        print(choice)
        
        if choice.lower() == 'y':
            await client.monitor_depth_changes("binance", "BTCUSDT", 30)
        
    except Exception as e:
        print(f"❌ 运行异常: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\n🧹 清理资源...")
        await client.cleanup()
        print("✅ 完成")

if __name__ == "__main__":
    asyncio.run(main())