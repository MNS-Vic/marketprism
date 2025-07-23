#!/usr/bin/env python3
"""
专门测试Trades Manager订阅功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.append(str(Path(__file__).parent))

from managers.trades_manager import TradesManager
from collector.nats_publisher import NATSPublisher, create_nats_config_from_yaml
import yaml
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


async def test_trades_subscription():
    """测试Trades Manager订阅功能"""
    print("🧪 测试Trades Manager订阅功能")
    print("="*60)
    
    trades_manager = None
    
    try:
        # 1. 加载配置
        print("📋 1. 加载配置...")
        config_path = "../../config/collector/unified_data_collection.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 2. 创建NATS发布器
        print("🔌 2. 创建NATS发布器...")
        nats_config = create_nats_config_from_yaml(config)
        nats_publisher = NATSPublisher(nats_config)
        
        # 3. 创建Trades Manager
        print("💹 3. 创建Trades Manager...")
        try:
            trades_manager = TradesManager(nats_publisher)
            print(f"   WebSocket管理器: {list(trades_manager.websocket_managers.keys())}")
        except Exception as e:
            print(f"   ❌ Trades Manager创建失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # 4. 启动Trades Manager
        print("🚀 4. 启动Trades Manager...")
        await trades_manager.start()
        
        # 5. 检查WebSocket连接状态
        print("🔍 5. 检查WebSocket连接状态...")
        for manager_name, manager in trades_manager.websocket_managers.items():
            is_connected = getattr(manager, 'is_connected', False)
            print(f"   {manager_name}: 连接状态={is_connected}")
        
        # 6. 等待连接建立
        print("⏱️ 6. 等待WebSocket连接建立...")
        await asyncio.sleep(5)
        
        # 7. 再次检查连接状态
        print("🔍 7. 再次检查WebSocket连接状态...")
        for manager_name, manager in trades_manager.websocket_managers.items():
            is_connected = getattr(manager, 'is_connected', False)
            print(f"   {manager_name}: 连接状态={is_connected}")
        
        # 8. 测试订阅功能
        print("📡 8. 测试订阅功能...")
        
        test_subscriptions = [
            ('binance', 'spot', 'BTCUSDT'),
            ('binance', 'derivatives', 'ETHUSDT'),
            ('okx', 'spot', 'BTC-USDT'),
            ('okx', 'derivatives', 'ETH-USDT-SWAP')
        ]
        
        for exchange, market_type, symbol in test_subscriptions:
            print(f"   订阅 {exchange} {market_type} {symbol}...")
            try:
                await trades_manager.subscribe_symbol(exchange, market_type, symbol)
                print(f"   ✅ {exchange} {market_type} {symbol} 订阅成功")
            except Exception as e:
                print(f"   ❌ {exchange} {market_type} {symbol} 订阅失败: {e}")
        
        # 9. 检查订阅状态
        print("📊 9. 检查订阅状态...")
        for manager_key, symbols in trades_manager.subscribed_symbols.items():
            print(f"   {manager_key}: {symbols}")
        
        # 10. 运行一段时间收集数据
        print("⏱️ 10. 运行数据收集 (15秒)...")
        await asyncio.sleep(15)
        
        # 11. 检查统计信息
        print("📈 11. 检查统计信息...")
        stats = trades_manager.get_stats()
        print(f"   运行状态: {stats['is_running']}")
        print(f"   总接收数据: {stats['total_trades_received']}")
        print(f"   总发布数据: {stats['total_trades_published']}")
        print(f"   错误数量: {stats['errors']}")
        
        # 检查每个WebSocket的状态
        websocket_status = stats.get('websocket_status', {})
        for exchange, status in websocket_status.items():
            print(f"   {exchange}:")
            if isinstance(status, dict):
                print(f"     连接状态: {status.get('connected', False)}")
                print(f"     接收消息: {status.get('messages_received', 0)}")
                print(f"     错误数量: {status.get('errors', 0)}")
            else:
                print(f"     状态: {status}")
        
        # 判断测试结果
        total_received = stats.get('total_trades_received', 0)
        connected_count = sum(1 for status in websocket_status.values() 
                            if status.get('connected', False))
        
        print(f"\n📊 测试结果:")
        print(f"   连接的WebSocket: {connected_count}/4")
        print(f"   接收的数据: {total_received}")
        
        if connected_count >= 2 and total_received > 0:
            print("🎉 Trades Manager订阅测试基本通过！")
            return True
        elif connected_count >= 2:
            print("⚠️ WebSocket连接正常，但未收到数据")
            print("   可能需要检查数据流配置或回调函数")
            return False
        else:
            print("❌ WebSocket连接失败")
            print("   需要检查网络连接或WebSocket配置")
            return False
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理
        if trades_manager:
            try:
                print("🧹 清理资源...")
                await trades_manager.stop()
                print("✅ 资源清理完成")
            except Exception as e:
                print(f"⚠️ 资源清理失败: {e}")


async def main():
    """主函数"""
    try:
        success = await test_trades_subscription()
        return success
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
