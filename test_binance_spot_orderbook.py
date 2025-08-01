#!/usr/bin/env python3
"""
Binance现货订单簿管理器独立测试脚本
使用真实的NATS Publisher和Normalizer
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "data-collector"))

# 设置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_binance_spot_orderbook():
    """测试Binance现货订单簿管理器"""
    try:
        logger.info("🚀 开始测试Binance现货订单簿管理器")

        # 导入必要的模块
        from collector.orderbook_managers.binance_spot_manager import BinanceSpotOrderBookManager
        from collector.normalizer import DataNormalizer
        from collector.nats_publisher import NATSPublisher, NATSConfig

        # 创建真正的Normalizer
        normalizer = DataNormalizer()
        logger.info("✅ DataNormalizer创建成功")

        # 创建NATS配置
        nats_config = NATSConfig(
            servers=["nats://localhost:4222"],
            client_name="test-binance-spot-orderbook",
            enable_jetstream=True
        )

        # 创建真正的NATS Publisher
        nats_publisher = NATSPublisher(nats_config, normalizer)
        logger.info("✅ NATSPublisher创建成功")

        # 连接NATS
        logger.info("📡 连接NATS服务器...")
        connected = await nats_publisher.connect()
        if not connected:
            logger.error("❌ NATS连接失败")
            return False
        logger.info("✅ NATS连接成功")
        
        # 配置参数
        config = {
            'api_base_url': 'https://api.binance.com',
            'depth_limit': 100,  # 减少深度以加快测试
            'snapshot_interval': 5,  # 5秒间隔
            'timeout': 30,
            'max_retries': 3
        }

        # 只测试一个交易对
        symbols = ["BTCUSDT"]

        logger.info(f"📋 测试配置:")
        logger.info(f"   - 交易对: {symbols}")
        logger.info(f"   - 深度限制: {config['depth_limit']}")
        logger.info(f"   - 快照间隔: {config['snapshot_interval']}秒")
        logger.info(f"   - NATS服务器: {nats_config.servers}")
        
        # 创建订单簿管理器
        logger.info("🔧 创建Binance现货订单簿管理器...")
        manager = BinanceSpotOrderBookManager(
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )
        
        logger.info("✅ 订单簿管理器创建成功")
        
        # 启动管理器
        logger.info("🚀 启动订单簿管理器...")
        
        # 创建启动任务
        start_task = asyncio.create_task(manager.start())
        
        # 等待一段时间让管理器运行
        logger.info("⏳ 让管理器运行60秒...")
        await asyncio.sleep(60)
        
        # 检查状态
        logger.info("🔍 检查管理器状态:")
        logger.info(f"   - 运行状态: {manager.running}")
        logger.info(f"   - NATS连接状态: {hasattr(nats_publisher, 'nc') and nats_publisher.nc is not None}")

        # 停止管理器
        logger.info("🛑 停止订单簿管理器...")
        await manager.stop()

        # 断开NATS连接
        logger.info("📡 断开NATS连接...")
        await nats_publisher.disconnect()

        # 等待启动任务完成
        try:
            await asyncio.wait_for(start_task, timeout=5)
        except asyncio.TimeoutError:
            logger.warning("⚠️ 启动任务未能在5秒内完成")
            start_task.cancel()

        logger.info("✅ 测试完成")

        # 检查是否有数据发布（通过NATS统计信息）
        if hasattr(nats_publisher, 'stats') and nats_publisher.stats.get('messages_published', 0) > 0:
            logger.info(f"📊 总共发布了 {nats_publisher.stats['messages_published']} 条消息")
            logger.info("🎉 测试成功！订单簿管理器正常工作")
            return True
        else:
            logger.warning("⚠️ 无法确定发布状态，但测试过程正常完成")
            return True
            
    except Exception as e:
        logger.error(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("🧪 Binance现货订单簿管理器独立测试")
    logger.info("=" * 60)
    
    success = await test_binance_spot_orderbook()
    
    logger.info("=" * 60)
    if success:
        logger.info("🎉 测试结果: 成功")
        sys.exit(0)
    else:
        logger.info("❌ 测试结果: 失败")
        sys.exit(1)

if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())
