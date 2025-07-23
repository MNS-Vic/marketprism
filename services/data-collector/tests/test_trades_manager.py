#!/usr/bin/env python3
"""
MarketPrism Trades Manager测试脚本
基于OrderBook Manager的成功经验，测试逐笔成交数据收集功能
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from managers.trades_manager import TradesManager
from collector.nats_publisher import NATSPublisher
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


class TradesManagerTester:
    """Trades Manager测试器"""
    
    def __init__(self):
        self.logger = logger
        self.trades_manager = None
        self.nats_publisher = None
        self.normalizer = TradesNormalizer()
        
        # 测试统计
        self.test_stats = {
            'trades_received': 0,
            'trades_processed': 0,
            'test_start_time': None,
            'exchanges_tested': set(),
            'symbols_tested': set()
        }
    
    async def setup(self):
        """设置测试环境"""
        try:
            self.logger.info("🔧 设置Trades Manager测试环境")
            
            # 初始化NATS发布器（模拟模式）
            self.nats_publisher = NATSPublisher()
            await self.nats_publisher.connect()
            
            # 初始化Trades Manager
            self.trades_manager = TradesManager(self.nats_publisher)
            
            # 添加数据回调用于测试
            self.trades_manager.add_data_callback(self._test_data_callback)
            
            # 初始化Trades Manager
            await self.trades_manager.initialize()
            
            self.logger.info("✅ 测试环境设置完成")
            
        except Exception as e:
            self.logger.error("❌ 测试环境设置失败", error=str(e), exc_info=True)
            raise
    
    async def _test_data_callback(self, normalized_data):
        """测试数据回调"""
        try:
            self.test_stats['trades_processed'] += 1
            self.test_stats['exchanges_tested'].add(normalized_data['exchange'])
            self.test_stats['symbols_tested'].add(normalized_data['symbol'])
            
            self.logger.info("📊 收到标准化成交数据",
                           exchange=normalized_data['exchange'],
                           symbol=normalized_data['symbol'],
                           trade_id=normalized_data['trade_id'],
                           price=normalized_data['price'],
                           quantity=normalized_data['quantity'],
                           side=normalized_data['side'])
            
        except Exception as e:
            self.logger.error("测试数据回调失败", error=str(e), exc_info=True)
    
    async def test_normalizer(self):
        """测试数据标准化器"""
        self.logger.info("🧪 测试数据标准化器")
        
        # 测试Binance现货数据标准化
        binance_spot_data = {
            "e": "trade",
            "E": 1672515782136,
            "s": "BTCUSDT",
            "t": 12345,
            "p": "42000.50",
            "q": "0.001",
            "T": 1672515782136,
            "m": False,
            "M": True
        }
        
        normalized = self.normalizer.normalize_binance_trade(binance_spot_data, 'spot')
        if normalized and self.normalizer.validate_normalized_data(normalized):
            self.logger.info("✅ Binance现货数据标准化测试通过", data=normalized)
        else:
            self.logger.error("❌ Binance现货数据标准化测试失败")
        
        # 测试OKX现货数据标准化
        okx_spot_data = {
            "instId": "BTC-USDT",
            "tradeId": "130639474",
            "px": "42219.9",
            "sz": "0.12060306",
            "side": "buy",
            "ts": "1629386267792"
        }
        
        normalized = self.normalizer.normalize_okx_trade(okx_spot_data, 'spot')
        if normalized and self.normalizer.validate_normalized_data(normalized):
            self.logger.info("✅ OKX现货数据标准化测试通过", data=normalized)
        else:
            self.logger.error("❌ OKX现货数据标准化测试失败")
        
        # 测试NATS主题生成
        test_data = {
            'exchange': 'binance',
            'market_type': 'spot',
            'symbol': 'BTC-USDT'
        }
        topic = self.normalizer.get_nats_topic(test_data)
        expected_topic = "trades-data.binance_spot.BTC-USDT"
        
        if topic == expected_topic:
            self.logger.info("✅ NATS主题生成测试通过", topic=topic)
        else:
            self.logger.error("❌ NATS主题生成测试失败", 
                            expected=expected_topic, actual=topic)
    
    async def test_trades_subscription(self):
        """测试逐笔成交数据订阅"""
        self.logger.info("🧪 测试逐笔成交数据订阅")
        
        try:
            # 启动Trades Manager
            await self.trades_manager.start()
            
            # 测试订阅不同交易所和市场的数据
            test_subscriptions = [
                ('binance', 'spot', 'BTCUSDT'),
                ('binance', 'spot', 'ETHUSDT'),
                ('okx', 'spot', 'BTC-USDT'),
                ('okx', 'spot', 'ETH-USDT'),
                ('okx', 'derivatives', 'BTC-USDT-SWAP'),
                ('okx', 'derivatives', 'ETH-USDT-SWAP')
            ]
            
            for exchange, market_type, symbol in test_subscriptions:
                try:
                    await self.trades_manager.subscribe_symbol(exchange, market_type, symbol)
                    self.logger.info("✅ 订阅成功", 
                                   exchange=exchange, 
                                   market_type=market_type, 
                                   symbol=symbol)
                    
                    # 短暂等待以避免过快订阅
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    self.logger.error("❌ 订阅失败", 
                                    exchange=exchange, 
                                    market_type=market_type, 
                                    symbol=symbol, 
                                    error=str(e))
            
            self.logger.info("📊 所有订阅请求已发送，等待数据...")
            
        except Exception as e:
            self.logger.error("❌ 逐笔成交数据订阅测试失败", error=str(e), exc_info=True)
    
    async def run_data_collection_test(self, duration: int = 60):
        """运行数据收集测试"""
        self.logger.info("🚀 开始逐笔成交数据收集测试", duration=duration)
        
        self.test_stats['test_start_time'] = time.time()
        
        try:
            # 等待指定时间收集数据
            await asyncio.sleep(duration)
            
            # 获取统计信息
            manager_stats = self.trades_manager.get_stats()
            
            self.logger.info("📊 数据收集测试完成",
                           duration=duration,
                           trades_received=manager_stats['total_trades_received'],
                           trades_published=manager_stats['total_trades_published'],
                           exchanges_tested=list(self.test_stats['exchanges_tested']),
                           symbols_tested=list(self.test_stats['symbols_tested']),
                           errors=manager_stats['errors'])
            
            # 显示详细统计
            self._print_detailed_stats(manager_stats)
            
        except Exception as e:
            self.logger.error("❌ 数据收集测试失败", error=str(e), exc_info=True)
    
    def _print_detailed_stats(self, stats):
        """打印详细统计信息"""
        print("\n" + "="*80)
        print("📊 MarketPrism Trades Manager 测试结果")
        print("="*80)
        
        print(f"🔄 运行状态: {'✅ 运行中' if stats['is_running'] else '❌ 已停止'}")
        print(f"📈 总接收成交数: {stats['total_trades_received']}")
        print(f"📤 总发布成交数: {stats['total_trades_published']}")
        print(f"❌ 错误数量: {stats['errors']}")
        
        print(f"\n📊 各交易所成交数据统计:")
        for exchange, count in stats['trades_by_exchange'].items():
            print(f"  {exchange}: {count}")
        
        print(f"\n🕐 最后成交时间:")
        for exchange, last_time in stats['last_trade_time'].items():
            print(f"  {exchange}: {last_time or '无数据'}")
        
        print(f"\n📋 已订阅交易对:")
        for manager, symbols in stats['subscribed_symbols'].items():
            print(f"  {manager}: {symbols}")
        
        print(f"\n🔌 WebSocket连接状态:")
        for manager, status in stats['websocket_status'].items():
            print(f"  {manager}: {status}")
        
        print("="*80)
    
    async def cleanup(self):
        """清理测试环境"""
        try:
            self.logger.info("🧹 清理测试环境")
            
            if self.trades_manager:
                await self.trades_manager.stop()
            
            if self.nats_publisher:
                await self.nats_publisher.disconnect()
            
            self.logger.info("✅ 测试环境清理完成")
            
        except Exception as e:
            self.logger.error("❌ 测试环境清理失败", error=str(e), exc_info=True)


async def main():
    """主测试函数"""
    tester = TradesManagerTester()
    
    try:
        # 设置测试环境
        await tester.setup()
        
        # 测试数据标准化器
        await tester.test_normalizer()
        
        # 测试逐笔成交数据订阅
        await tester.test_trades_subscription()
        
        # 运行数据收集测试（60秒）
        await tester.run_data_collection_test(60)
        
    except KeyboardInterrupt:
        logger.info("⚠️ 测试被用户中断")
    except Exception as e:
        logger.error("❌ 测试失败", error=str(e), exc_info=True)
    finally:
        # 清理测试环境
        await tester.cleanup()


if __name__ == "__main__":
    print("🚀 MarketPrism Trades Manager 测试")
    print("基于OrderBook Manager的成功经验开发")
    print("支持Binance和OKX的现货和衍生品逐笔成交数据")
    print("="*80)
    
    asyncio.run(main())
