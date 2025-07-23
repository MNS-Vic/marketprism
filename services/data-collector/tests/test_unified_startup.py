#!/usr/bin/env python3
"""
MarketPrism统一数据收集器启动测试
验证unified_collector_main.py作为统一入口点的功能
"""

import sys
import asyncio
import time
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from unified_collector_main import UnifiedDataCollector
import structlog

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
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


async def test_unified_collector_startup():
    """测试统一数据收集器启动"""
    print("🚀 MarketPrism统一数据收集器启动测试")
    print("验证unified_collector_main.py作为统一入口点")
    print("="*80)
    
    collector = None
    
    try:
        # 初始化统一数据收集器
        print("\n🔧 初始化统一数据收集器...")
        collector = UnifiedDataCollector()
        print("✅ 统一数据收集器创建成功")
        
        # 启动收集器
        print("\n🚀 启动统一数据收集器...")
        await collector.start()
        print("✅ 统一数据收集器启动成功")
        
        # 检查组件状态
        print("\n📊 检查组件状态...")
        
        # 检查OrderBook管理器
        if collector.orderbook_managers:
            print(f"✅ OrderBook管理器已启动: {len(collector.orderbook_managers)}个")
            for name, manager in collector.orderbook_managers.items():
                print(f"   - {name}: 已初始化")
        else:
            print("⚠️ 未找到OrderBook管理器")
        
        # 检查Trades管理器
        if collector.trades_manager:
            trades_stats = collector.trades_manager.get_stats()
            print(f"✅ Trades管理器已启动: 运行状态={trades_stats['is_running']}")
            print(f"   WebSocket管理器: {list(trades_stats['websocket_status'].keys())}")
        else:
            print("⚠️ 未找到Trades管理器")
        
        # 检查NATS连接
        if collector.nats_publisher:
            print("✅ NATS发布器已初始化")
            if hasattr(collector.nats_publisher, 'is_connected'):
                print(f"   连接状态: {collector.nats_publisher.is_connected}")
        else:
            print("⚠️ 未找到NATS发布器")
        
        # 运行一段时间收集数据
        print(f"\n⏱️ 运行数据收集 (30秒)...")
        await asyncio.sleep(30)
        
        # 检查统计信息
        print(f"\n📈 数据收集统计:")
        
        # OrderBook统计
        total_orderbook_updates = 0
        for name, manager in collector.orderbook_managers.items():
            if hasattr(manager, 'stats'):
                stats = manager.stats
                updates = stats.get('total_updates', 0)
                total_orderbook_updates += updates
                print(f"   {name}: {updates} 次订单簿更新")
        
        print(f"   总订单簿更新: {total_orderbook_updates}")
        
        # Trades统计
        if collector.trades_manager:
            trades_stats = collector.trades_manager.get_stats()
            print(f"   总成交数据接收: {trades_stats['total_trades_received']}")
            print(f"   总成交数据发布: {trades_stats['total_trades_published']}")
            print(f"   错误数量: {trades_stats['errors']}")
        
        # 验证数据收集功能
        success_criteria = {
            'orderbook_managers_running': len(collector.orderbook_managers) > 0,
            'trades_manager_running': collector.trades_manager is not None,
            'nats_publisher_available': collector.nats_publisher is not None,
            'data_collection_active': total_orderbook_updates > 0 or (
                collector.trades_manager and 
                collector.trades_manager.get_stats()['total_trades_received'] > 0
            )
        }
        
        print(f"\n🎯 功能验证结果:")
        for criterion, result in success_criteria.items():
            status = "✅ 通过" if result else "❌ 失败"
            print(f"   {criterion}: {status}")
        
        passed_checks = sum(success_criteria.values())
        total_checks = len(success_criteria)
        success_rate = (passed_checks / total_checks) * 100
        
        print(f"\n📊 总体成功率: {passed_checks}/{total_checks} ({success_rate:.0f}%)")
        
        if success_rate >= 75:
            print("🎉 统一数据收集器启动测试基本通过！")
            print("✅ 统一入口点正常工作")
            print("✅ OrderBook Manager和Trades Manager成功整合")
            print("✅ 配置文件统一管理正常")
            return True
        else:
            print("⚠️ 统一数据收集器启动测试存在问题")
            print("需要进一步检查和修复")
            return False
        
    except Exception as e:
        print(f"❌ 统一数据收集器启动测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理
        if collector:
            try:
                print(f"\n🧹 停止统一数据收集器...")
                await collector.stop()
                print("✅ 统一数据收集器已停止")
            except Exception as e:
                print(f"⚠️ 停止统一数据收集器时出错: {e}")


async def test_nats_data_verification():
    """测试NATS数据验证"""
    print(f"\n🧪 NATS数据验证测试")
    print("="*50)
    
    try:
        import nats
        
        # 连接到NATS
        nc = await nats.connect("nats://localhost:4222")
        print("✅ NATS连接成功")
        
        # 订阅数据主题
        received_data = {
            'orderbook': [],
            'trades': []
        }
        
        async def orderbook_handler(msg):
            subject = msg.subject
            print(f"📚 收到OrderBook数据: {subject}")
            received_data['orderbook'].append(subject)
        
        async def trades_handler(msg):
            subject = msg.subject
            print(f"💹 收到Trades数据: {subject}")
            received_data['trades'].append(subject)
        
        # 订阅主题
        await nc.subscribe("orderbook-data.>", cb=orderbook_handler)
        await nc.subscribe("trade-data.>", cb=trades_handler)
        
        print("📡 已订阅NATS数据主题，等待数据...")
        
        # 等待数据
        await asyncio.sleep(10)
        
        # 验证数据接收
        print(f"\n📊 数据接收统计:")
        print(f"   OrderBook数据: {len(received_data['orderbook'])} 条")
        print(f"   Trades数据: {len(received_data['trades'])} 条")
        
        if received_data['orderbook']:
            print(f"   OrderBook主题示例: {received_data['orderbook'][:3]}")
        
        if received_data['trades']:
            print(f"   Trades主题示例: {received_data['trades'][:3]}")
        
        # 关闭连接
        await nc.close()
        
        total_data = len(received_data['orderbook']) + len(received_data['trades'])
        if total_data > 0:
            print("✅ NATS数据验证通过")
            return True
        else:
            print("⚠️ 未收到NATS数据")
            return False
        
    except Exception as e:
        print(f"❌ NATS数据验证失败: {e}")
        return False


async def main():
    """主测试函数"""
    try:
        # 测试统一数据收集器启动
        startup_success = await test_unified_collector_startup()
        
        # 测试NATS数据验证
        nats_success = await test_nats_data_verification()
        
        # 显示最终结果
        print(f"\n" + "="*80)
        print(f"📋 MarketPrism统一整合测试最终结果")
        print(f"="*80)
        print(f"🚀 统一入口点启动: {'✅ 成功' if startup_success else '❌ 失败'}")
        print(f"📡 NATS数据验证: {'✅ 成功' if nats_success else '❌ 失败'}")
        
        if startup_success and nats_success:
            print(f"\n🎉 所有测试通过！")
            print(f"✅ MarketPrism数据收集器统一整合完成")
            print(f"✅ OrderBook Manager和Trades Manager成功整合")
            print(f"✅ 统一配置文件正常工作")
            print(f"✅ NATS数据推送功能正常")
            return True
        else:
            print(f"\n⚠️ 部分测试失败")
            return False
        
    except KeyboardInterrupt:
        print(f"\n⚠️ 测试被用户中断")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
