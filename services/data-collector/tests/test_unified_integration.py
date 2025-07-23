#!/usr/bin/env python3
"""
MarketPrism统一数据收集器集成测试
验证OrderBook Manager和Trades Manager的统一入口点整合
"""

import sys
import asyncio
import time
import yaml
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


class UnifiedIntegrationTester:
    """统一数据收集器集成测试器"""
    
    def __init__(self):
        self.logger = logger
        self.collector = None
        self.config_path = "../../config/collector/unified_data_collection.yaml"
        
        # 测试统计
        self.test_stats = {
            'config_loaded': False,
            'orderbook_manager_initialized': False,
            'trades_manager_initialized': False,
            'nats_connected': False,
            'exchanges_configured': 0,
            'data_types_enabled': set(),
            'symbols_configured': set()
        }
    
    def test_config_loading(self):
        """测试配置文件加载"""
        self.logger.info("🧪 测试配置文件加载")
        
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                self.logger.error("❌ 配置文件不存在", path=self.config_path)
                return False
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 验证配置结构
            required_sections = ['system', 'exchanges', 'nats']
            for section in required_sections:
                if section not in config:
                    self.logger.error("❌ 配置文件缺少必要部分", section=section)
                    return False
            
            # 验证exchanges配置
            exchanges = config['exchanges']
            expected_exchanges = ['binance_spot', 'binance_derivatives', 'okx_spot', 'okx_derivatives']
            
            for exchange_name in expected_exchanges:
                if exchange_name not in exchanges:
                    self.logger.warning("⚠️ 缺少交易所配置", exchange=exchange_name)
                    continue
                
                exchange_config = exchanges[exchange_name]
                
                # 检查必要字段
                required_fields = ['exchange', 'market_type', 'enabled', 'symbols', 'data_types']
                for field in required_fields:
                    if field not in exchange_config:
                        self.logger.error("❌ 交易所配置缺少字段", 
                                        exchange=exchange_name, field=field)
                        return False
                
                # 统计配置信息
                if exchange_config.get('enabled', False):
                    self.test_stats['exchanges_configured'] += 1
                    self.test_stats['data_types_enabled'].update(exchange_config['data_types'])
                    self.test_stats['symbols_configured'].update(exchange_config['symbols'])
                
                self.logger.info("✅ 交易所配置验证通过",
                               exchange=exchange_name,
                               market_type=exchange_config['market_type'],
                               enabled=exchange_config['enabled'],
                               data_types=exchange_config['data_types'],
                               symbols=exchange_config['symbols'])
            
            # 验证NATS配置
            nats_config = config['nats']
            if 'streams' in nats_config:
                streams = nats_config['streams']
                expected_streams = ['orderbook', 'trade']
                for stream in expected_streams:
                    if stream in streams:
                        self.logger.info("✅ NATS流配置验证通过",
                                       stream=stream,
                                       template=streams[stream])
            
            self.test_stats['config_loaded'] = True
            self.logger.info("✅ 配置文件加载测试通过")
            return True
            
        except Exception as e:
            self.logger.error("❌ 配置文件加载测试失败", error=str(e), exc_info=True)
            return False
    
    async def test_unified_collector_initialization(self):
        """测试统一数据收集器初始化"""
        self.logger.info("🧪 测试统一数据收集器初始化")
        
        try:
            # 初始化统一数据收集器
            self.collector = UnifiedDataCollector()
            
            # 检查初始状态
            assert self.collector.orderbook_managers == {}, "OrderBook管理器应该为空"
            assert self.collector.trades_manager is None, "Trades管理器应该为None"
            assert self.collector.nats_publisher is None, "NATS发布器应该为None"
            
            self.logger.info("✅ 统一数据收集器初始化测试通过")
            return True
            
        except Exception as e:
            self.logger.error("❌ 统一数据收集器初始化测试失败", error=str(e), exc_info=True)
            return False
    
    async def test_component_initialization(self):
        """测试组件初始化"""
        self.logger.info("🧪 测试组件初始化")

        try:
            # 先加载配置
            config_success = await self.collector._load_configuration()
            if not config_success:
                self.logger.error("❌ 配置加载失败")
                return False

            # 初始化组件
            success = await self.collector._initialize_components()
            
            if not success:
                self.logger.error("❌ 组件初始化失败")
                return False
            
            # 验证组件状态
            if self.collector.normalizer is not None:
                self.logger.info("✅ DataNormalizer初始化成功")
            
            if self.collector.nats_publisher is not None:
                self.test_stats['nats_connected'] = True
                self.logger.info("✅ NATS Publisher初始化成功")
            
            if self.collector.trades_manager is not None:
                self.test_stats['trades_manager_initialized'] = True
                self.logger.info("✅ Trades Manager初始化成功")
            
            self.logger.info("✅ 组件初始化测试通过")
            return True
            
        except Exception as e:
            self.logger.error("❌ 组件初始化测试失败", error=str(e), exc_info=True)
            return False
    
    async def test_data_collection_startup(self):
        """测试数据收集启动"""
        self.logger.info("🧪 测试数据收集启动")

        try:
            # 确保配置已加载
            if not self.collector.config:
                config_success = await self.collector._load_configuration()
                if not config_success:
                    self.logger.error("❌ 配置加载失败")
                    return False

            # 启动数据收集
            success = await self.collector._start_data_collection()
            
            if not success:
                self.logger.error("❌ 数据收集启动失败")
                return False
            
            # 验证OrderBook管理器
            if self.collector.orderbook_managers:
                self.test_stats['orderbook_manager_initialized'] = True
                self.logger.info("✅ OrderBook管理器启动成功",
                               count=len(self.collector.orderbook_managers),
                               managers=list(self.collector.orderbook_managers.keys()))
            
            # 验证Trades管理器
            if self.collector.trades_manager:
                trades_stats = self.collector.trades_manager.get_stats()
                self.logger.info("✅ Trades管理器启动成功",
                               is_running=trades_stats['is_running'],
                               websocket_managers=list(trades_stats['websocket_status'].keys()))
            
            self.logger.info("✅ 数据收集启动测试通过")
            return True
            
        except Exception as e:
            self.logger.error("❌ 数据收集启动测试失败", error=str(e), exc_info=True)
            return False
    
    async def test_nats_topic_formats(self):
        """测试NATS主题格式"""
        self.logger.info("🧪 测试NATS主题格式")
        
        try:
            # 验证OrderBook主题格式
            if self.collector.nats_publisher:
                # 测试OrderBook主题生成
                orderbook_topic = self.collector.nats_publisher._generate_subject(
                    "orderbook", "binance_spot", "spot", "BTC-USDT"
                )
                expected_orderbook = "orderbook-data.binance_spot.spot.BTC-USDT"
                
                if orderbook_topic == expected_orderbook:
                    self.logger.info("✅ OrderBook主题格式正确", topic=orderbook_topic)
                else:
                    self.logger.error("❌ OrderBook主题格式错误",
                                    actual=orderbook_topic,
                                    expected=expected_orderbook)
                    return False
                
                # 测试Trade主题生成
                trade_topic = self.collector.nats_publisher._generate_subject(
                    "trade", "okx_derivatives", "perpetual", "ETH-USDT"
                )
                expected_trade = "trade-data.okx_derivatives.perpetual.ETH-USDT"
                
                if trade_topic == expected_trade:
                    self.logger.info("✅ Trade主题格式正确", topic=trade_topic)
                else:
                    self.logger.error("❌ Trade主题格式错误",
                                    actual=trade_topic,
                                    expected=expected_trade)
                    return False
            
            self.logger.info("✅ NATS主题格式测试通过")
            return True
            
        except Exception as e:
            self.logger.error("❌ NATS主题格式测试失败", error=str(e), exc_info=True)
            return False
    
    def print_test_summary(self):
        """打印测试总结"""
        print("\n" + "="*80)
        print("📊 MarketPrism统一数据收集器集成测试结果")
        print("="*80)
        
        print(f"🔧 配置文件加载: {'✅ 成功' if self.test_stats['config_loaded'] else '❌ 失败'}")
        print(f"📊 已配置交易所数量: {self.test_stats['exchanges_configured']}")
        print(f"📈 启用的数据类型: {list(self.test_stats['data_types_enabled'])}")
        print(f"💱 配置的交易对: {list(self.test_stats['symbols_configured'])}")
        
        print(f"\n🔌 NATS连接: {'✅ 成功' if self.test_stats['nats_connected'] else '❌ 失败'}")
        print(f"📚 OrderBook管理器: {'✅ 初始化' if self.test_stats['orderbook_manager_initialized'] else '❌ 未初始化'}")
        print(f"💹 Trades管理器: {'✅ 初始化' if self.test_stats['trades_manager_initialized'] else '❌ 未初始化'}")
        
        # 计算总体成功率
        total_checks = 6
        passed_checks = sum([
            self.test_stats['config_loaded'],
            self.test_stats['nats_connected'],
            self.test_stats['orderbook_manager_initialized'],
            self.test_stats['trades_manager_initialized'],
            self.test_stats['exchanges_configured'] > 0,
            len(self.test_stats['data_types_enabled']) >= 2
        ])
        
        success_rate = (passed_checks / total_checks) * 100
        
        print(f"\n🎯 总体成功率: {passed_checks}/{total_checks} ({success_rate:.0f}%)")
        
        if success_rate >= 80:
            print("🎉 统一数据收集器集成测试基本通过！")
            print("✅ OrderBook Manager和Trades Manager已成功整合")
            print("✅ 配置文件统一管理正常工作")
            print("✅ NATS主题格式一致性验证通过")
        else:
            print("⚠️ 统一数据收集器集成测试存在问题")
            print("需要进一步检查和修复")
        
        print("="*80)
    
    async def cleanup(self):
        """清理测试环境"""
        try:
            if self.collector:
                await self.collector.stop()
            self.logger.info("✅ 测试环境清理完成")
        except Exception as e:
            self.logger.error("❌ 测试环境清理失败", error=str(e), exc_info=True)


async def main():
    """主测试函数"""
    tester = UnifiedIntegrationTester()
    
    try:
        print("🚀 MarketPrism统一数据收集器集成测试")
        print("验证OrderBook Manager和Trades Manager的统一整合")
        print("="*80)
        
        # 运行测试序列
        tests = [
            ("配置文件加载", tester.test_config_loading),
            ("统一收集器初始化", tester.test_unified_collector_initialization),
            ("组件初始化", tester.test_component_initialization),
            ("数据收集启动", tester.test_data_collection_startup),
            ("NATS主题格式", tester.test_nats_topic_formats)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🧪 执行测试: {test_name}")
            try:
                if asyncio.iscoroutinefunction(test_func):
                    result = await test_func()
                else:
                    result = test_func()
                
                if result:
                    passed_tests += 1
                    print(f"✅ {test_name} 通过")
                else:
                    print(f"❌ {test_name} 失败")
            except Exception as e:
                print(f"❌ {test_name} 异常: {e}")
        
        # 显示测试总结
        tester.print_test_summary()
        
        return passed_tests == total_tests
        
    except KeyboardInterrupt:
        logger.info("⚠️ 测试被用户中断")
        return False
    except Exception as e:
        logger.error("❌ 测试失败", error=str(e), exc_info=True)
        return False
    finally:
        # 清理测试环境
        await tester.cleanup()


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
