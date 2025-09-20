#!/usr/bin/env python3
"""
临时调试脚本 - 测试 BinanceSpotTradesManager 工厂创建
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from collector.data_types import Exchange, MarketType
from collector.trades_manager_factory import trades_manager_factory
from collector.normalizer import DataNormalizer
from collector.nats_publisher import NATSPublisher

def test_factory():
    print("🔧 开始测试 BinanceSpotTradesManager 工厂创建")
    
    try:
        # 创建必要的依赖
        normalizer = DataNormalizer()
        nats_publisher = NATSPublisher()
        
        # 测试参数
        exchange = Exchange.BINANCE_SPOT
        market_type = MarketType.SPOT
        symbols = ['BTCUSDT', 'ETHUSDT']
        config = {
            'ws_url': 'wss://stream.binance.com:9443/ws',
            'heartbeat_interval': 30,
            'connection_timeout': 10
        }
        
        print(f"📊 参数信息:")
        print(f"  exchange: {exchange} (type: {type(exchange)})")
        print(f"  market_type: {market_type} (type: {type(market_type)})")
        print(f"  symbols: {symbols}")
        print(f"  config keys: {list(config.keys())}")
        
        # 测试工厂创建
        print("🏭 调用工厂创建管理器...")
        manager = trades_manager_factory.create_trades_manager(
            exchange=exchange,
            market_type=market_type,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        if manager:
            print(f"✅ 管理器创建成功: {type(manager).__name__}")
            print(f"  exchange: {manager.exchange}")
            print(f"  market_type: {manager.market_type}")
            print(f"  symbols: {manager.symbols}")
        else:
            print("❌ 管理器创建失败: 返回 None")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_factory()
