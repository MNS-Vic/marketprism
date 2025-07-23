#!/usr/bin/env python3
"""
Trades Manager与统一数据收集器集成测试
验证逐笔成交数据收集功能的完整集成
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from managers.trades_manager import TradesManager
from collector.nats_publisher import NATSPublisher, NATSConfig
from collector.normalizer import DataNormalizer
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


class TradesIntegrationTester:
    """Trades Manager集成测试器"""
    
    def __init__(self):
        self.logger = logger
        self.trades_manager = None
        self.nats_publisher = None
        self.normalizer = DataNormalizer()
        
        # 测试统计
        self.test_stats = {
            'trades_processed': 0,
            'test_start_time': None,
            'exchanges_tested': set(),
            'symbols_tested': set()
        }
    
    async def setup(self):
        """设置测试环境"""
        try:
            self.logger.info("🔧 设置Trades Manager集成测试环境")
            
            # 初始化NATS发布器（模拟模式）
            nats_config = NATSConfig(
                servers=["nats://localhost:4222"],
                client_name="trades-manager-test"
            )
            self.nats_publisher = NATSPublisher(nats_config, self.normalizer)
            
            # 尝试连接NATS（如果失败则使用模拟模式）
            try:
                await self.nats_publisher.connect()
                self.logger.info("✅ NATS连接成功")
            except Exception as e:
                self.logger.warning("⚠️ NATS连接失败，使用模拟模式", error=str(e))
                # 创建模拟发布器
                self.nats_publisher = MockNATSPublisher()
            
            # 初始化Trades Manager
            self.trades_manager = TradesManager(self.nats_publisher)
            
            # 添加数据回调用于测试
            self.trades_manager.add_data_callback(self._test_data_callback)
            
            # 初始化Trades Manager
            await self.trades_manager.initialize()
            
            self.logger.info("✅ 集成测试环境设置完成")
            
        except Exception as e:
            self.logger.error("❌ 集成测试环境设置失败", error=str(e), exc_info=True)
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
    
    async def test_trades_manager_initialization(self):
        """测试Trades Manager初始化"""
        self.logger.info("🧪 测试Trades Manager初始化")
        
        try:
            # 检查初始化状态
            assert self.trades_manager is not None, "Trades Manager未初始化"
            assert self.trades_manager.normalizer is not None, "标准化器未初始化"
            assert self.trades_manager.nats_publisher is not None, "NATS发布器未初始化"
            
            # 检查WebSocket管理器
            expected_managers = [
                'binance_spot', 'binance_derivatives',
                'okx_spot', 'okx_derivatives'
            ]
            
            for manager_key in expected_managers:
                assert manager_key in self.trades_manager.websocket_managers, f"缺少{manager_key}管理器"
            
            self.logger.info("✅ Trades Manager初始化测试通过")
            return True
            
        except Exception as e:
            self.logger.error("❌ Trades Manager初始化测试失败", error=str(e), exc_info=True)
            return False
    
    async def test_data_processing_pipeline(self):
        """测试数据处理管道"""
        self.logger.info("🧪 测试数据处理管道")
        
        try:
            # 模拟不同交易所的数据处理
            test_cases = [
                {
                    'exchange': 'binance',
                    'market_type': 'spot',
                    'raw_data': {
                        "e": "trade",
                        "E": 1672515782136,
                        "s": "BTCUSDT",
                        "t": 12345,
                        "p": "42000.50",
                        "q": "0.001",
                        "T": 1672515782136,
                        "m": False
                    }
                },
                {
                    'exchange': 'binance',
                    'market_type': 'derivatives',
                    'raw_data': {
                        "e": "aggTrade",
                        "E": 1672515782136,
                        "s": "ETHUSDT",
                        "a": 26129,
                        "p": "3200.25",
                        "q": "0.1",
                        "f": 100,
                        "l": 105,
                        "T": 1672515782136,
                        "m": True
                    }
                },
                {
                    'exchange': 'okx',
                    'market_type': 'spot',
                    'raw_data': {
                        "arg": {
                            "channel": "trades",
                            "instId": "BTC-USDT"
                        },
                        "data": [{
                            "instId": "BTC-USDT",
                            "tradeId": "130639474",
                            "px": "42219.9",
                            "sz": "0.12060306",
                            "side": "buy",
                            "ts": "1629386267792"
                        }]
                    }
                },
                {
                    'exchange': 'okx',
                    'market_type': 'derivatives',
                    'raw_data': {
                        "arg": {
                            "channel": "trades",
                            "instId": "ETH-USDT-SWAP"
                        },
                        "data": [{
                            "instId": "ETH-USDT-SWAP",
                            "tradeId": "130639475",
                            "px": "3250.1",
                            "sz": "0.5",
                            "side": "sell",
                            "ts": "1629386267800"
                        }]
                    }
                }
            ]
            
            initial_count = self.test_stats['trades_processed']
            
            # 处理测试数据
            for test_case in test_cases:
                await self.trades_manager._process_trade_data(
                    test_case['exchange'],
                    test_case['market_type'],
                    test_case['raw_data']
                )
            
            # 验证处理结果
            processed_count = self.test_stats['trades_processed'] - initial_count
            expected_count = len(test_cases)
            
            if processed_count == expected_count:
                self.logger.info("✅ 数据处理管道测试通过",
                               processed=processed_count,
                               expected=expected_count)
                return True
            else:
                self.logger.error("❌ 数据处理管道测试失败",
                                processed=processed_count,
                                expected=expected_count)
                return False
            
        except Exception as e:
            self.logger.error("❌ 数据处理管道测试失败", error=str(e), exc_info=True)
            return False
    
    async def test_nats_publishing(self):
        """测试NATS发布功能"""
        self.logger.info("🧪 测试NATS发布功能")
        
        try:
            # 模拟标准化数据
            test_data = {
                'exchange': 'binance',
                'market_type': 'spot',
                'symbol': 'BTC-USDT',
                'trade_id': '12345',
                'price': '42000.50',
                'quantity': '0.001',
                'side': 'buy',
                'timestamp': '2025-07-15T14:50:03.853145Z'
            }
            
            # 测试NATS发布
            await self.trades_manager._publish_to_nats(test_data)
            
            # 检查统计信息
            stats = self.trades_manager.get_stats()
            if stats['total_trades_published'] > 0:
                self.logger.info("✅ NATS发布功能测试通过")
                return True
            else:
                self.logger.error("❌ NATS发布功能测试失败")
                return False
            
        except Exception as e:
            self.logger.error("❌ NATS发布功能测试失败", error=str(e), exc_info=True)
            return False
    
    async def test_statistics_tracking(self):
        """测试统计信息跟踪"""
        self.logger.info("🧪 测试统计信息跟踪")
        
        try:
            # 获取统计信息
            stats = self.trades_manager.get_stats()
            
            # 验证统计信息结构
            required_fields = [
                'total_trades_received',
                'total_trades_published',
                'trades_by_exchange',
                'last_trade_time',
                'errors',
                'is_running',
                'subscribed_symbols',
                'websocket_status'
            ]
            
            for field in required_fields:
                assert field in stats, f"统计信息缺少字段: {field}"
            
            self.logger.info("✅ 统计信息跟踪测试通过", stats=stats)
            return True
            
        except Exception as e:
            self.logger.error("❌ 统计信息跟踪测试失败", error=str(e), exc_info=True)
            return False
    
    async def cleanup(self):
        """清理测试环境"""
        try:
            self.logger.info("🧹 清理集成测试环境")
            
            if self.trades_manager:
                await self.trades_manager.stop()
            
            if hasattr(self.nats_publisher, 'disconnect'):
                await self.nats_publisher.disconnect()
            
            self.logger.info("✅ 集成测试环境清理完成")
            
        except Exception as e:
            self.logger.error("❌ 集成测试环境清理失败", error=str(e), exc_info=True)


class MockNATSPublisher:
    """模拟NATS发布器"""
    
    def __init__(self):
        self.published_messages = []
    
    async def publish(self, subject: str, data: dict):
        """模拟发布消息"""
        self.published_messages.append({
            'subject': subject,
            'data': data
        })
    
    async def disconnect(self):
        """模拟断开连接"""
        pass


async def main():
    """主测试函数"""
    tester = TradesIntegrationTester()
    
    try:
        # 设置测试环境
        await tester.setup()
        
        # 运行集成测试
        tests = [
            ("Trades Manager初始化", tester.test_trades_manager_initialization),
            ("数据处理管道", tester.test_data_processing_pipeline),
            ("NATS发布功能", tester.test_nats_publishing),
            ("统计信息跟踪", tester.test_statistics_tracking)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🧪 执行测试: {test_name}")
            if await test_func():
                passed_tests += 1
                print(f"✅ {test_name} 通过")
            else:
                print(f"❌ {test_name} 失败")
        
        # 显示测试结果
        print(f"\n📊 集成测试结果: {passed_tests}/{total_tests} 通过")
        
        if passed_tests == total_tests:
            print("🎉 所有集成测试通过！")
            print("✅ Trades Manager与统一数据收集器集成成功")
            print("✅ 数据处理管道完全正常")
            print("✅ NATS发布功能正常工作")
            print("✅ 统计信息跟踪完整")
            return True
        else:
            print("❌ 部分集成测试失败")
            return False
        
    except KeyboardInterrupt:
        logger.info("⚠️ 集成测试被用户中断")
        return False
    except Exception as e:
        logger.error("❌ 集成测试失败", error=str(e), exc_info=True)
        return False
    finally:
        # 清理测试环境
        await tester.cleanup()


if __name__ == "__main__":
    print("🚀 MarketPrism Trades Manager 集成测试")
    print("验证与统一数据收集器的完整集成")
    print("="*80)
    
    success = asyncio.run(main())
    exit(0 if success else 1)
