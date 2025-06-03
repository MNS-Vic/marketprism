"""
Exchanges模块TDD测试 - 系统性发现设计问题

基于MarketPrism TDD方法论，全面评估exchanges模块的设计质量
目标：发现真实的设计问题，驱动企业级改进
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

# 基础导入测试
class TestExchangesModuleStructure:
    """TDD Level 0: 模块结构和导入测试"""
    
    def test_exchanges_module_imports_correctly(self):
        """TDD: 验证exchanges模块可以正常导入"""
        import marketprism_collector.exchanges
        assert marketprism_collector.exchanges is not None
    
    def test_base_exchange_adapter_exists(self):
        """TDD: 验证基础ExchangeAdapter类存在"""
        from marketprism_collector.exchanges.base import ExchangeAdapter
        assert ExchangeAdapter is not None
    
    def test_enhanced_exchange_adapter_exists(self):
        """TDD: 验证增强版ExchangeAdapter类存在"""
        from marketprism_collector.exchanges.enhanced_base import EnhancedExchangeAdapter
        assert EnhancedExchangeAdapter is not None
    
    def test_concrete_exchange_adapters_exist(self):
        """TDD: 验证具体交易所适配器存在"""
        from marketprism_collector.exchanges.binance import BinanceAdapter
        from marketprism_collector.exchanges.okx import OKXAdapter
        from marketprism_collector.exchanges.deribit import DeribitAdapter
        
        assert BinanceAdapter is not None
        assert OKXAdapter is not None
        assert DeribitAdapter is not None

class TestExchangeAdapterDesignIssues:
    """TDD Level 1: 发现ExchangeAdapter设计问题"""
    
    def test_mock_adapter_initialization_flexibility(self):
        """TDD: 验证MockAdapter支持灵活初始化"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        # 应该支持无参数初始化
        adapter = MockExchangeAdapter()
        assert adapter is not None
        
        # 应该支持配置参数
        config = {"api_key": "test", "secret": "test"}
        adapter_with_config = MockExchangeAdapter(config)
        assert adapter_with_config is not None
        assert hasattr(adapter_with_config, 'config')
    
    def test_mock_adapter_required_methods_exist(self):
        """TDD: 验证MockAdapter具有期望的核心方法"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        adapter = MockExchangeAdapter()
        
        # 核心数据获取方法
        expected_methods = [
            'get_trades', 'get_orderbook', 'get_ticker',
            'get_klines', 'get_funding_rate', 'get_open_interest'
        ]
        
        for method_name in expected_methods:
            assert hasattr(adapter, method_name), f"缺少方法: {method_name}"
            method = getattr(adapter, method_name)
            assert callable(method), f"方法不可调用: {method_name}"

class TestExchangeFactoryPattern:
    """TDD Level 3: 发现缺少工厂模式支持"""
    
    def test_exchange_factory_exists(self):
        """TDD: 验证交易所工厂模式存在"""
        from marketprism_collector.exchanges import ExchangeFactory
        assert ExchangeFactory is not None
    
    def test_factory_create_methods(self):
        """TDD: 验证工厂具有创建方法"""
        from marketprism_collector.exchanges import ExchangeFactory
        
        factory = ExchangeFactory()
        
        # 应该有通用创建方法
        assert hasattr(factory, 'create_adapter')
        assert hasattr(factory, 'create_binance_adapter')
        assert hasattr(factory, 'create_okx_adapter')

class TestExchangeManagerPattern:
    """TDD Level 4: 发现缺少统一管理器"""
    
    def test_exchange_manager_exists(self):
        """TDD: 验证交易所管理器存在"""
        from marketprism_collector.exchanges import ExchangeManager
        assert ExchangeManager is not None
    
    def test_manager_adapter_management(self):
        """TDD: 验证管理器能管理多个适配器"""
        from marketprism_collector.exchanges import ExchangeManager
        
        manager = ExchangeManager()
        
        # 管理方法
        assert hasattr(manager, 'add_adapter')
        assert hasattr(manager, 'remove_adapter')
        assert hasattr(manager, 'get_adapter')

class TestExchangeEnterpriseFeatures:
    """TDD Level 5: 企业级特性验证"""
    
    def test_rate_limiting_integration(self):
        """TDD: 验证费率限制集成"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        adapter = MockExchangeAdapter()
        
        # 应该有费率限制功能
        assert hasattr(adapter, 'rate_limiter')
        assert hasattr(adapter, 'check_rate_limit')
    
    def test_retry_mechanism_support(self):
        """TDD: 验证重试机制支持"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        adapter = MockExchangeAdapter()
        
        # 应该有重试配置和功能
        assert hasattr(adapter, 'retry_config')
        assert hasattr(adapter, 'execute_with_retry')

class TestExchangeConfigurationManagement:
    """TDD Level 6: 配置管理系统测试"""
    
    def test_hierarchical_configuration(self):
        """TDD: 验证分层配置支持"""
        from marketprism_collector.exchanges.enhanced_base import EnhancedExchangeAdapter
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        # 使用MockAdapter测试配置管理
        global_config = {"timeout": 30, "retries": 3}
        exchange_config = {"api_key": "test", "timeout": 60}
        
        adapter = MockExchangeAdapter({**global_config, **exchange_config})
        
        # 配置应该正确存储
        stored_config = adapter.get_config()
        assert stored_config.get('timeout') == 60
        assert stored_config.get('retries') == 3
        assert stored_config.get('api_key') == 'test'

class TestExchangeDataNormalization:
    """TDD Level 7: 数据标准化测试"""
    
    def test_trade_data_normalization(self):
        """TDD: 验证交易数据标准化"""
        from marketprism_collector.exchanges.binance import BinanceAdapter
        from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
        
        # 创建完整的配置对象
        config = ExchangeConfig.for_binance(
            market_type=MarketType.FUTURES,
            api_key="test",
            api_secret="test",
            symbols=["BTCUSDT"],
            data_types=[DataType.TRADE]
        )
        
        adapter = BinanceAdapter(config)
        
        # 应该有数据标准化方法
        assert hasattr(adapter, 'normalize_trade')

class TestExchangeWebSocketIntegration:
    """TDD Level 8: WebSocket集成测试"""
    
    def test_websocket_manager_exists(self):
        """TDD: 验证WebSocket管理器存在"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        adapter = MockExchangeAdapter()
        
        # 应该有WebSocket管理功能
        assert hasattr(adapter, 'websocket_manager')
        assert hasattr(adapter, 'start_websocket')
        assert hasattr(adapter, 'stop_websocket')

class TestExchangeTestingSupport:
    """TDD Level 9: 测试支持功能"""
    
    def test_mock_adapter_exists(self):
        """TDD: 验证模拟适配器存在"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        assert MockExchangeAdapter is not None
    
    def test_sandbox_mode_support(self):
        """TDD: 验证沙盒模式支持"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        config = {"sandbox": True}
        adapter = MockExchangeAdapter(config)
        
        # 应该正确识别沙盒模式
        assert hasattr(adapter, 'is_sandbox_mode')
        assert adapter.is_sandbox_mode() is True

class TestExchangePerformanceFeatures:
    """TDD Level 10: 性能特性测试"""
    
    def test_performance_monitoring(self):
        """TDD: 验证性能监控功能"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        adapter = MockExchangeAdapter()
        
        # 应该有性能监控
        assert hasattr(adapter, 'performance_metrics')
        assert hasattr(adapter, 'record_request_time')
        assert hasattr(adapter, 'get_latency_stats')
        assert hasattr(adapter, 'get_throughput_stats')
    
    def test_circuit_breaker_integration(self):
        """TDD: 验证熔断器集成"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        adapter = MockExchangeAdapter()
        
        # 应该集成熔断器功能
        assert hasattr(adapter, 'circuit_breaker')
        assert hasattr(adapter, 'is_circuit_open')
        assert hasattr(adapter, 'reset_circuit')

class TestExchangeAsyncOperations:
    """TDD Level 11: 异步操作测试"""
    
    @pytest.mark.asyncio
    async def test_async_data_retrieval(self):
        """TDD: 验证异步数据获取"""
        from marketprism_collector.exchanges import MockExchangeAdapter
        
        adapter = MockExchangeAdapter()
        
        # 测试异步方法
        trades = await adapter.get_trades('BTC/USDT')
        assert trades is not None
        assert len(trades) > 0
        
        orderbook = await adapter.get_orderbook('BTC/USDT')
        assert orderbook is not None
        
        ticker = await adapter.get_ticker('BTC/USDT')
        assert ticker is not None

class TestExchangeFactoryIntegration:
    """TDD Level 12: 工厂集成测试（修改为使用真实交易所）"""
    
    def test_factory_create_binance_adapters(self):
        """TDD: 验证工厂能创建Binance适配器"""
        from marketprism_collector.exchanges import ExchangeFactory
        
        factory = ExchangeFactory()
        
        # 设置测试配置
        test_config = {
            'api_key': 'test_key',
            'secret': 'test_secret',
            'sandbox': True
        }
        
        # 应该能创建Binance适配器
        binance_adapter = factory.create_adapter('binance', test_config)
        assert binance_adapter is not None
    
    def test_factory_caching_mechanism(self):
        """TDD: 验证工厂缓存机制（使用Binance）"""
        from marketprism_collector.exchanges import ExchangeFactory
        
        factory = ExchangeFactory()
        
        config = {'api_key': 'test', 'secret': 'test'}
        
        # 第一次创建
        adapter1 = factory.create_adapter('binance', config, use_cache=True)
        
        # 第二次创建应该返回相同实例（缓存）
        adapter2 = factory.create_adapter('binance', config, use_cache=True)
        
        assert adapter1 is adapter2
        
        # 禁用缓存应该创建新实例
        adapter3 = factory.create_adapter('binance', config, use_cache=False)
        assert adapter3 is not adapter1

class TestExchangeRealAdapterIntegration:
    """TDD Level 13: 真实适配器集成测试"""
    
    def test_binance_adapter_creation_with_factory(self):
        """TDD: 验证工厂能正确创建Binance适配器"""
        from marketprism_collector.exchanges import ExchangeFactory
        from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
        
        factory = ExchangeFactory()
        
        # 创建完整的ExchangeConfig
        config = ExchangeConfig.for_binance(
            market_type=MarketType.FUTURES,
            api_key="test_key",
            api_secret="test_secret",
            symbols=["BTCUSDT"],
            data_types=[DataType.TRADE]
        )
        
        # 工厂应该能接受ExchangeConfig对象
        adapter = factory.create_adapter_from_config('binance', config)
        assert adapter is not None
    
    def test_factory_config_conversion(self):
        """TDD: 验证工厂的配置转换功能"""
        from marketprism_collector.exchanges import ExchangeFactory
        from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
        
        factory = ExchangeFactory()
        
        # 字典配置应该能转换为ExchangeConfig
        dict_config = {
            'api_key': 'test_key',
            'secret': 'test_secret',
            'sandbox': True
        }
        
        # 工厂应该能内部转换配置格式
        exchange_config = factory.create_exchange_config('binance', dict_config)
        assert isinstance(exchange_config, ExchangeConfig)
        assert exchange_config.api_key == 'test_key'
    
    def test_okx_adapter_creation(self):
        """TDD: 验证OKX适配器创建"""
        from marketprism_collector.exchanges import ExchangeFactory
        
        factory = ExchangeFactory()
        
        config = {
            'api_key': 'test_key',
            'secret': 'test_secret',
            'passphrase': 'test_passphrase'
        }
        
        adapter = factory.create_adapter('okx', config)
        assert adapter is not None
    
    def test_multiple_exchanges_support(self):
        """TDD: 验证多交易所支持"""
        from marketprism_collector.exchanges import ExchangeFactory
        
        factory = ExchangeFactory()
        
        supported_exchanges = factory.get_supported_exchanges()
        
        # 应该支持多个真实交易所
        expected_exchanges = ['binance', 'okx', 'deribit']
        for exchange in expected_exchanges:
            assert exchange in supported_exchanges
        
        # 验证每个交易所都能创建适配器
        for exchange in expected_exchanges:
            config = {'api_key': 'test', 'secret': 'test'}
            if exchange == 'okx':
                config['passphrase'] = 'test'
                
            adapter = factory.create_adapter(exchange, config)
            assert adapter is not None, f"无法创建{exchange}适配器"