#!/usr/bin/env python3
"""
测试WebSocket代理连接修复
"""

import asyncio
import sys
import os
import structlog
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

# 导入本项目模块
from marketprism_collector.config import CollectorConfig
from marketprism_collector.exchanges.factory import ExchangeFactory


async def test_single_exchange_websocket_proxy(exchange_name: str):
    """测试单个交易所的WebSocket代理连接"""
    print(f"\n🟡 测试 {exchange_name.capitalize()} WebSocket代理连接...")
    print("=" * 50)
    
    try:
        # 加载配置
        collector_config = CollectorConfig.load_from_file("config/collector_config.yaml")
        
        # 获取交易所配置
        exchange_config_file = f"config/exchanges/{exchange_name}.yaml"
        if exchange_name == "binance":
            exchange_config_file = "config/exchanges/binance_futures.yaml"
        
        print(f"📋 加载配置文件: {exchange_config_file}")
        
        # 创建工厂
        factory = ExchangeFactory()
        
        # 创建适配器（只需要基本连接能力）
        adapter = factory.create_exchange_adapter(
            exchange_name=exchange_name,
            config_file=exchange_config_file,
            required_capabilities=['basic_connection']
        )
        
        if not adapter:
            print(f"❌ 无法创建 {exchange_name} 适配器")
            return False
        
        print(f"✅ {exchange_name.capitalize()} 适配器创建成功: {type(adapter).__name__}")
        
        # 显示代理配置信息
        if hasattr(adapter.config, 'proxy'):
            print(f"📝 代理配置: {adapter.config.proxy}")
        
        print(f"📊 {exchange_name.capitalize()} 初始统计: 连接={adapter.is_connected}, 消息={adapter.stats['messages_received']}")
        
        # 启动适配器
        print(f"🚀 启动 {exchange_name.capitalize()} 适配器连接...")
        start_success = await adapter.start()
        
        if not start_success:
            print(f"⚠️ {exchange_name.capitalize()} 适配器 start() 返回 False")
            return False
        
        # 等待连接建立
        print(f"⏳ 等待 {exchange_name.capitalize()} 连接建立 (10 秒)...")
        await asyncio.sleep(10)
        
        # 检查连接状态
        final_connected = adapter.is_connected
        final_stats = adapter.get_stats()
        
        print(f"🔗 {exchange_name.capitalize()} 实时连接状态: {final_connected}")
        print(f"📈 {exchange_name.capitalize()} 实时统计: 消息={final_stats['messages_received']}, 错误={final_stats['errors']}")
        
        # 停止适配器
        print(f"🛑 停止 {exchange_name.capitalize()} 适配器...")
        await adapter.stop()
        print(f"✅ {exchange_name.capitalize()} 适配器已停止")
        
        return final_connected
        
    except Exception as e:
        print(f"❌ {exchange_name.capitalize()} 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("🧪 MarketPrism WebSocket代理连接修复测试")
    print("=" * 80)
    
    # 检查代理环境变量
    print("\n🔧 代理环境变量:")
    print(f"   http_proxy: {os.getenv('http_proxy', '未设置')}")
    print(f"   https_proxy: {os.getenv('https_proxy', '未设置')}")
    
    # 测试交易所
    exchanges = ["binance", "okx", "deribit"]
    results = {}
    
    for exchange in exchanges:
        results[exchange] = await test_single_exchange_websocket_proxy(exchange)
        await asyncio.sleep(2)  # 间隔2秒
    
    # 总结
    print("\n" + "=" * 80)
    print("📊 WebSocket代理连接测试结果总结")
    print("=" * 80)
    
    success_count = sum(results.values())
    total_count = len(results)
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
    
    print(f"💻 测试交易所数: {total_count}")
    print(f"✅ 成功连接: {success_count}")
    print(f"❌ 连接失败: {total_count - success_count}")
    print(f"📈 连接成功率: {success_rate:.1f}%")
    
    print("\n📋 各交易所状态:")
    for exchange, success in results.items():
        status = "✅ 成功连接" if success else "❌ 连接失败"
        print(f"   {status} 📁 {exchange.capitalize()}")
    
    if success_count == total_count:
        print("\n🎉 所有交易所WebSocket代理连接测试成功！")
        return True
    else:
        print(f"\n⚠️ {total_count - success_count} 个交易所连接失败，请查看上面的详细信息")
        return False


if __name__ == "__main__":
    # 配置日志
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # 运行测试
    result = asyncio.run(main())
    sys.exit(0 if result else 1)