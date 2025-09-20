#!/usr/bin/env python3
"""
测试open_interest和liquidation管理器
用于诊断数据源问题
"""

import asyncio
import sys
import os
import logging

# 添加项目路径
sys.path.append('/app')
sys.path.append('/app/services/data-collector')

from collector.open_interest_managers.open_interest_manager_factory import OpenInterestManagerFactory
from collector.liquidation_managers.liquidation_manager_factory import LiquidationManagerFactory
from collector.nats_publisher import NATSPublisher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_open_interest_managers():
    """测试open_interest管理器"""
    logger.info("🔍 开始测试open_interest管理器")
    
    # 创建NATS发布器
    nats_publisher = NATSPublisher()
    await nats_publisher.connect("nats://localhost:4222")
    
    # 测试交易所列表
    test_exchanges = [
        ("binance_derivatives", ["BTCUSDT", "ETHUSDT"]),
        ("okx_derivatives", ["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    ]
    
    for exchange, symbols in test_exchanges:
        try:
            logger.info(f"📊 测试 {exchange} open_interest管理器")
            
            # 创建管理器
            manager = OpenInterestManagerFactory.create_manager(
                exchange=exchange,
                symbols=symbols,
                nats_publisher=nats_publisher
            )
            
            if manager:
                logger.info(f"✅ {exchange} open_interest管理器创建成功")
                
                # 启动管理器
                await manager.start()
                logger.info(f"✅ {exchange} open_interest管理器启动成功")
                
                # 等待一次数据收集
                await asyncio.sleep(10)
                
                # 停止管理器
                await manager.stop()
                logger.info(f"✅ {exchange} open_interest管理器停止成功")
                
            else:
                logger.error(f"❌ {exchange} open_interest管理器创建失败")
                
        except Exception as e:
            logger.error(f"❌ {exchange} open_interest管理器测试异常: {e}", exc_info=True)
    
    await nats_publisher.close()

async def test_liquidation_managers():
    """测试liquidation管理器"""
    logger.info("🔍 开始测试liquidation管理器")
    
    # 创建NATS发布器
    nats_publisher = NATSPublisher()
    await nats_publisher.connect("nats://localhost:4222")
    
    # 测试交易所列表
    test_exchanges = [
        ("binance_derivatives", "perpetual", ["BTCUSDT", "ETHUSDT"]),
        ("okx_derivatives", "perpetual", ["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    ]
    
    for exchange, market_type, symbols in test_exchanges:
        try:
            logger.info(f"📊 测试 {exchange} liquidation管理器")
            
            # 创建管理器配置
            config = {
                'ws_url': None,  # 使用默认URL
                'heartbeat_interval': 180 if 'binance' in exchange else 25,
                'connection_timeout': 30,
                'max_reconnect_attempts': 3,
                'reconnect_delay': 1.0,
                'max_reconnect_delay': 30.0,
                'backoff_multiplier': 2.0
            }
            
            # 创建管理器
            try:
                manager = LiquidationManagerFactory.create_manager(
                    exchange=exchange,
                    market_type=market_type,
                    symbols=symbols,
                    normalizer=None,  # 简化测试
                    nats_publisher=nats_publisher,
                    config=config
                )
                
                if manager:
                    logger.info(f"✅ {exchange} liquidation管理器创建成功")
                    
                    # 启动管理器
                    success = await manager.start()
                    if success:
                        logger.info(f"✅ {exchange} liquidation管理器启动成功")
                        
                        # 等待一段时间观察数据
                        await asyncio.sleep(30)
                        
                        # 停止管理器
                        await manager.stop()
                        logger.info(f"✅ {exchange} liquidation管理器停止成功")
                    else:
                        logger.error(f"❌ {exchange} liquidation管理器启动失败")
                        
                else:
                    logger.error(f"❌ {exchange} liquidation管理器创建失败")
                    
            except Exception as factory_error:
                logger.error(f"❌ {exchange} liquidation管理器工厂异常: {factory_error}")
                
        except Exception as e:
            logger.error(f"❌ {exchange} liquidation管理器测试异常: {e}", exc_info=True)
    
    await nats_publisher.close()

async def test_api_connectivity():
    """测试API连通性"""
    logger.info("🔍 测试API连通性")
    
    import aiohttp
    
    # 测试API端点
    test_apis = [
        ("Binance Open Interest", "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=1"),
        ("OKX Open Interest", "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?instId=BTC-USDT-SWAP&period=5m&limit=1"),
        ("Binance Liquidation", "https://fapi.binance.com/fapi/v1/forceOrders?symbol=BTCUSDT&limit=1"),
        ("OKX Liquidation", "https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&instId=BTC-USDT-SWAP&limit=1")
    ]
    
    async with aiohttp.ClientSession() as session:
        for name, url in test_apis:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ {name} API连通正常: {len(str(data))} bytes")
                    else:
                        logger.error(f"❌ {name} API响应异常: {response.status}")
                        
            except Exception as e:
                logger.error(f"❌ {name} API连接失败: {e}")

async def main():
    """主函数"""
    logger.info("🚀 开始数据源诊断测试")
    
    # 测试API连通性
    await test_api_connectivity()
    
    # 测试open_interest管理器
    await test_open_interest_managers()
    
    # 测试liquidation管理器
    # await test_liquidation_managers()  # 暂时注释，先测试open_interest
    
    logger.info("🎉 数据源诊断测试完成")

if __name__ == "__main__":
    asyncio.run(main())
