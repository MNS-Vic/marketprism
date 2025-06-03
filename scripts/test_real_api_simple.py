#!/usr/bin/env python3
"""
简化的真实API测试
验证与真实交易所的基本连接

使用方法:
    source scripts/proxy_config.sh
    python scripts/test_real_api_simple.py
"""

import asyncio
import json
import logging
import os
import sys
import aiohttp
from datetime import datetime

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_exchange_api(exchange: str, proxy: str = None) -> bool:
    """测试交易所API连接"""
    
    urls = {
        'binance': 'https://api.binance.com/api/v3/time',
        'okx': 'https://www.okx.com/api/v5/public/time',
        'deribit': 'https://www.deribit.com/api/v2/public/get_time'
    }
    
    if exchange not in urls:
        logger.error(f"❌ 不支持的交易所: {exchange}")
        return False
    
    try:
        logger.info(f"🔍 测试 {exchange} API连接...")
        if proxy:
            logger.info(f"   使用代理: {proxy}")
        
        timeout = aiohttp.ClientTimeout(total=15)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(urls[exchange], proxy=proxy) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ {exchange} API连接成功")
                    logger.info(f"   响应数据: {json.dumps(data, indent=2)}")
                    return True
                else:
                    logger.error(f"❌ {exchange} API连接失败: HTTP {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ {exchange} API测试异常: {e}")
        return False

async def test_binance_market_data(proxy: str = None) -> bool:
    """测试Binance市场数据"""
    try:
        logger.info("🔍 测试Binance市场数据...")
        
        # 获取BTC/USDT的24小时价格统计
        url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
        
        timeout = aiohttp.ClientTimeout(total=15)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, proxy=proxy) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info("✅ Binance市场数据获取成功")
                    logger.info(f"   BTCUSDT价格: {data['lastPrice']}")
                    logger.info(f"   24h涨跌: {data['priceChangePercent']}%")
                    logger.info(f"   24h交易量: {data['volume']}")
                    return True
                else:
                    logger.error(f"❌ Binance市场数据获取失败: HTTP {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Binance市场数据测试异常: {e}")
        return False

async def main():
    """主函数"""
    logger.info("🚀 开始简化的真实API测试")
    logger.info(f"测试时间: {datetime.now()}")
    
    # 检查代理配置
    proxy = os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY')
    if proxy:
        logger.info(f"🔧 使用代理: {proxy}")
    else:
        logger.info("🔧 未配置代理，使用直连")
    
    # 测试结果
    results = {}
    
    # 测试不同交易所
    exchanges = ['binance', 'okx', 'deribit']
    for exchange in exchanges:
        logger.info(f"\n{'='*60}")
        results[exchange] = await test_exchange_api(exchange, proxy)
    
    # 如果Binance连接成功，进一步测试市场数据
    if results.get('binance'):
        logger.info(f"\n{'='*60}")
        results['binance_market_data'] = await test_binance_market_data(proxy)
    
    # 汇总结果
    logger.info(f"\n{'='*80}")
    logger.info("📊 真实API测试结果汇总")
    logger.info(f"{'='*80}")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    success_rate = (passed / total) * 100 if total > 0 else 0
    logger.info(f"\n总结: {passed}/{total} 通过 ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        logger.info("🎉 真实API测试大部分通过，网络和代理配置良好！")
        return 0
    elif success_rate >= 50:
        logger.info("⚠️ 真实API测试部分通过，部分交易所可能有网络问题")
        return 0
    else:
        logger.info("❌ 真实API测试大部分失败，请检查网络和代理配置")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试执行异常: {e}")
        sys.exit(1)