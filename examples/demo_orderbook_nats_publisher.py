#!/usr/bin/env python3
"""
订单簿NATS推送器演示脚本

展示如何使用订单簿NATS推送器将OrderBook Manager维护的标准化订单簿数据每秒推送到NATS
"""

import asyncio
import sys
import os
from datetime import datetime
import structlog

# 添加项目路径
sys.path.append('services/python-collector/src')

from marketprism_collector.data_types import Exchange, MarketType, ExchangeConfig, DataType
from marketprism_collector.normalizer import DataNormalizer
from marketprism_collector.orderbook_manager import OrderBookManager
from marketprism_collector.orderbook_nats_publisher import OrderBookNATSPublisher, create_orderbook_nats_publisher

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

async def demo_orderbook_nats_publisher():
    """演示订单簿NATS推送器"""
    
    print("🚀 MarketPrism 订单簿NATS推送器演示")
    print("=" * 60)
    
    # 演示配置
    demo_symbols = ["BTCUSDT", "ETHUSDT"]
    demo_duration = 60  # 演示1分钟
    
    # NATS配置
    nats_config = {
        "url": "nats://localhost:4222",
        "stream_name": "MARKET_DATA",
        "subject_prefix": "market"
    }
    
    # 推送器配置
    publisher_config = {
        "enabled": True,
        "publish_interval": 1.0,  # 每秒推送一次
        "symbols": demo_symbols,
        "quality_control": {
            "min_depth_levels": 10,
            "max_age_seconds": 30,
            "skip_unchanged": True
        }
    }
    
    # 设置SOCKS代理（推荐）
    os.environ['ALL_PROXY'] = 'socks5://127.0.0.1:1080'
    
    orderbook_manager = None
    nats_publisher = None
    
    try:
        print("📋 演示配置:")
        print(f"  • 交易对: {demo_symbols}")
        print(f"  • 演示时长: {demo_duration}秒")
        print(f"  • NATS服务器: {nats_config['url']}")
        print(f"  • 推送间隔: {publisher_config['publish_interval']}秒")
        print()
        
        # 第一步：创建OrderBook Manager
        print("📊 第一步：创建OrderBook Manager")
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443/ws",
            data_types=[DataType.ORDERBOOK],
            symbols=demo_symbols,
            depth_limit=400,
            snapshot_interval=300
        )
        
        normalizer = DataNormalizer()
        orderbook_manager = OrderBookManager(config, normalizer)
        print("✅ OrderBook Manager创建成功")
        
        # 第二步：创建NATS推送器
        print("\n📡 第二步：创建订单簿NATS推送器")
        nats_publisher = await create_orderbook_nats_publisher(
            orderbook_manager=orderbook_manager,
            nats_config=nats_config,
            publisher_config=publisher_config
        )
        print("✅ NATS推送器创建成功")
        
        # 第三步：启动OrderBook Manager
        print("\n🔄 第三步：启动OrderBook Manager")
        success = await orderbook_manager.start(demo_symbols)
        if not success:
            raise Exception("OrderBook Manager启动失败")
        print("✅ OrderBook Manager启动成功")
        
        # 第四步：等待订单簿初始化
        print("\n⏳ 第四步：等待订单簿初始化...")
        await asyncio.sleep(10)
        
        # 检查订单簿状态
        print("\n📈 订单簿状态检查:")
        for symbol in demo_symbols:
            orderbook = orderbook_manager.get_current_orderbook(symbol)
            if orderbook:
                print(f"  ✅ {symbol}: {len(orderbook.bids)}买档 + {len(orderbook.asks)}卖档 = {len(orderbook.bids) + len(orderbook.asks)}档深度")
            else:
                print(f"  ⚠️ {symbol}: 订单簿未就绪")
        
        # 第五步：启动NATS推送器
        print("\n🚀 第五步：启动NATS推送器")
        await nats_publisher.start(demo_symbols)
        print("✅ NATS推送器启动成功")
        print(f"📡 推送主题格式: market.binance.{'{symbol}'}.orderbook")
        
        # 第六步：运行演示
        print(f"\n🏃 第六步：运行演示 ({demo_duration}秒)")
        print("NATS推送器将每秒推送一次订单簿数据到NATS...")
        print()
        
        start_time = datetime.datetime.now(datetime.timezone.utc)
        check_interval = 10  # 每10秒检查一次
        elapsed = 0
        
        while elapsed < demo_duration:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # 获取统计信息
            publisher_stats = nats_publisher.get_stats()
            symbol_stats = nats_publisher.get_symbol_stats()
            manager_stats = orderbook_manager.get_stats()
            
            print(f"⏰ 进度: {elapsed}/{demo_duration}秒 ({elapsed/demo_duration*100:.1f}%)")
            print(f"📡 NATS推送统计:")
            print(f"  • 总推送次数: {publisher_stats['total_publishes']}")
            print(f"  • 成功推送: {publisher_stats['successful_publishes']}")
            print(f"  • 失败推送: {publisher_stats['failed_publishes']}")
            print(f"  • 推送成功率: {publisher_stats['publish_rate']:.2%}")
            print(f"  • 交易对数量: {publisher_stats['symbols_published']}")
            
            # 显示交易对详情
            print(f"📊 交易对推送详情:")
            for symbol, stats in symbol_stats.items():
                status = "✅" if stats['is_ready'] else "❌"
                print(f"  • {symbol} {status}: 更新ID={stats['last_update_id']}, 深度={stats['depth_levels']}档")
                if stats['best_bid'] and stats['best_ask']:
                    spread = stats['best_ask'] - stats['best_bid']
                    print(f"    买价={stats['best_bid']:.2f}, 卖价={stats['best_ask']:.2f}, 价差={spread:.2f}")
            
            # 检查OrderBook Manager状态
            print(f"📈 OrderBook Manager统计:")
            print(f"  • 快照获取次数: {manager_stats['snapshots_fetched']}")
            print(f"  • 更新处理次数: {manager_stats['updates_processed']}")
            print(f"  • 同步错误次数: {manager_stats['sync_errors']}")
            print()
        
        # 第七步：演示完成，显示最终统计
        print("🏁 第七步：演示完成")
        end_time = datetime.datetime.now(datetime.timezone.utc)
        total_time = (end_time - start_time).total_seconds()
        
        final_publisher_stats = nats_publisher.get_stats()
        final_symbol_stats = nats_publisher.get_symbol_stats()
        final_manager_stats = orderbook_manager.get_stats()
        
        print(f"\n📊 最终统计 (总时长: {total_time:.1f}秒):")
        print("=" * 40)
        
        # NATS推送器统计
        print("📡 NATS推送器:")
        print(f"  • 总推送次数: {final_publisher_stats['total_publishes']}")
        print(f"  • 推送成功率: {final_publisher_stats['publish_rate']:.2%}")
        print(f"  • 错误次数: {final_publisher_stats['errors']}")
        
        # 计算性能指标
        if final_publisher_stats['total_publishes'] > 0:
            publishes_per_second = final_publisher_stats['total_publishes'] / total_time
            print(f"  • 推送频率: {publishes_per_second:.2f}次/秒")
        
        # OrderBook Manager统计
        print("\n📈 OrderBook Manager:")
        print(f"  • 快照获取: {final_manager_stats['snapshots_fetched']}")
        print(f"  • 更新处理: {final_manager_stats['updates_processed']}")
        print(f"  • 错误次数: {final_manager_stats['sync_errors']}")
        
        # 交易对最终状态
        print("\n📋 交易对最终状态:")
        for symbol, stats in final_symbol_stats.items():
            status = "✅" if stats['is_ready'] else "❌"
            print(f"  • {symbol} {status}:")
            print(f"    - 最后更新ID: {stats['last_update_id']}")
            print(f"    - 深度档位: {stats['depth_levels']}")
            if stats['last_publish_time']:
                print(f"    - 最后推送: {stats['last_publish_time']}")
        
        # 性能评估
        print("\n🎯 性能评估:")
        success_rate = final_publisher_stats['publish_rate']
        if success_rate >= 0.95:
            print("  ✅ 推送成功率: 优秀")
        elif success_rate >= 0.90:
            print("  ⚠️ 推送成功率: 良好")
        else:
            print("  ❌ 推送成功率: 需要改进")
        
        expected_publishes = int(total_time / publisher_config['publish_interval'])
        actual_publishes = final_publisher_stats['total_publishes']
        timing_accuracy = actual_publishes / max(expected_publishes, 1)
        
        if timing_accuracy >= 0.95:
            print("  ✅ 推送时序: 优秀")
        elif timing_accuracy >= 0.90:
            print("  ⚠️ 推送时序: 良好")
        else:
            print("  ❌ 推送时序: 需要优化")
        
        print("\n🎉 演示成功完成！")
        print("\n💡 下一步:")
        print("  1. 运行 'python example_nats_depth_consumer.py' 订阅NATS数据")
        print("  2. 使用 'python run_orderbook_nats_publisher.py' 启动生产服务")
        print("  3. 查看 'docs/订单簿NATS推送器使用指南.md' 了解更多")
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断演示")
    except Exception as e:
        print(f"\n❌ 演示异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        print("\n🧹 清理演示资源...")
        
        if nats_publisher:
            await nats_publisher.stop()
            print("  ✅ NATS推送器已停止")
        
        if orderbook_manager:
            await orderbook_manager.stop()
            print("  ✅ OrderBook Manager已停止")
        
        print("✅ 演示清理完成")

async def main():
    """主函数"""
    print("🌟 欢迎使用MarketPrism订单簿NATS推送器演示")
    print("本演示将展示如何将实时订单簿数据每秒推送到NATS")
    print()
    
    # 检查是否需要继续
    try:
        response = input("是否继续演示？(y/N): ").strip().lower()
        if response not in ['y', 'yes', '是']:
            print("演示已取消")
            return 0
    except KeyboardInterrupt:
        print("\n演示已取消")
        return 0
    
    print()
    await demo_orderbook_nats_publisher()
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 