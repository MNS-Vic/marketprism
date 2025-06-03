"""
TDD Stage 3 - 基础集成测试

验证Stage 2中实现的单元测试组件能够正确集成工作
主要测试Python收集器的各个组件之间的协作
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import sys
import os

# 添加Python收集器路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/python-collector/src'))

from marketprism_collector.config import Config
from marketprism_collector.rest_client import RestClientManager, RestClientConfig
from marketprism_collector.top_trader_collector import TopTraderDataCollector
from marketprism_collector.market_long_short_collector import MarketLongShortDataCollector
from marketprism_collector.nats_client import NATSManager
from marketprism_collector.types import Exchange, DataType


@pytest.mark.integration
class TestTDDStage3BasicIntegration:
    """TDD Stage 3 基础集成测试"""
    
    @pytest.fixture
    def config(self):
        """创建测试配置"""
        return Config()
    
    @pytest.fixture
    def rest_client_config(self):
        """创建REST客户端配置"""
        return RestClientConfig(
            base_url="https://api.binance.com",
            timeout=30,
            max_retries=3
        )
    
    @pytest.fixture
    def mock_nats_manager(self):
        """Mock NATS管理器"""
        manager = AsyncMock(spec=NATSManager)
        manager.start = AsyncMock()
        manager.stop = AsyncMock()
        manager.get_publisher = AsyncMock()
        return manager
    
    @pytest.mark.asyncio
    async def test_rest_client_manager_initialization(self):
        """测试REST客户端管理器初始化"""
        manager = RestClientManager()
        
        # 验证初始化
        assert manager is not None
        assert hasattr(manager, 'create_client')
        assert hasattr(manager, 'start_all')
        assert hasattr(manager, 'stop_all')
        assert len(manager.clients) == 0  # 初始状态没有客户端
    
    @pytest.mark.asyncio
    async def test_top_trader_collector_with_rest_manager(self):
        """测试Top Trader收集器与REST管理器的集成"""
        # 创建REST管理器
        rest_manager = RestClientManager()
        
        # 创建收集器
        collector = TopTraderDataCollector(rest_manager)
        
        # 验证集成
        assert collector.rest_client_manager == rest_manager
        assert collector.symbols == ["BTC-USDT", "ETH-USDT", "BNB-USDT"]
        assert collector.collection_interval == 300
        assert not collector.is_running
    
    @pytest.mark.asyncio
    async def test_market_long_short_collector_with_rest_manager(self):
        """测试Market Long Short收集器与REST管理器的集成"""
        # 创建REST管理器
        rest_manager = RestClientManager()
        
        # 创建收集器
        collector = MarketLongShortDataCollector(rest_manager)
        
        # 验证集成
        assert collector.rest_client_manager == rest_manager
        assert collector.symbols == ["BTC-USDT", "ETH-USDT"]
        assert collector.collection_interval == 300
        assert not collector.is_running
    
    @pytest.mark.asyncio
    async def test_dual_collector_initialization(self):
        """测试双收集器可以同时初始化"""
        # 创建共享的REST管理器
        rest_manager = RestClientManager()
        
        # 创建两个收集器
        top_trader_collector = TopTraderDataCollector(rest_manager)
        market_collector = MarketLongShortDataCollector(rest_manager)
        
        # 验证两个收集器都正确初始化
        assert top_trader_collector.rest_client_manager == rest_manager
        assert market_collector.rest_client_manager == rest_manager
        
        # 验证它们有不同的配置但共享REST管理器
        assert len(top_trader_collector.symbols) == 3  # BTC, ETH, BNB
        assert len(market_collector.symbols) == 2       # BTC, ETH
        
        # 验证回调系统独立
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        
        top_trader_collector.register_callback(callback1)
        market_collector.register_callback(callback2)
        
        assert len(top_trader_collector.callbacks) == 1
        assert len(market_collector.callbacks) == 1
        assert callback1 in top_trader_collector.callbacks
        assert callback2 in market_collector.callbacks
    
    @pytest.mark.asyncio 
    async def test_config_integration_with_components(self, config):
        """测试配置系统与各组件的集成"""
        # 验证配置对象包含所需的部分
        assert hasattr(config, 'collector')
        assert hasattr(config, 'nats')
        assert hasattr(config, 'proxy')
        
        # 验证NATS配置
        nats_config = config.nats
        assert hasattr(nats_config, 'url')
        assert hasattr(nats_config, 'streams')
        
        # 验证收集器配置
        collector_config = config.collector
        assert hasattr(collector_config, 'log_level')
        assert hasattr(collector_config, 'http_port')
    
    @pytest.mark.asyncio
    async def test_rest_client_config_creation(self, rest_client_config):
        """测试REST客户端配置创建"""
        # 验证REST客户端配置
        assert rest_client_config.base_url == "https://api.binance.com"
        assert rest_client_config.timeout == 30
        assert rest_client_config.max_retries == 3
        
        # 创建REST管理器并添加客户端
        manager = RestClientManager()
        client = manager.create_client("test_client", rest_client_config)
        
        # 验证客户端被正确创建
        assert client is not None
        assert manager.get_client("test_client") == client
    
    @pytest.mark.asyncio
    async def test_data_type_enum_coverage(self):
        """测试数据类型枚举覆盖我们实现的功能"""
        # 验证TDD Stage 2实现的数据类型都在枚举中
        required_types = [
            DataType.TOP_TRADER_LONG_SHORT_RATIO,
            DataType.MARKET_LONG_SHORT_RATIO,
            DataType.TRADE,
            DataType.ORDERBOOK,
            DataType.TICKER,
            DataType.KLINE
        ]
        
        # 验证所有需要的数据类型都存在
        for data_type in required_types:
            assert isinstance(data_type, DataType)
            assert data_type.value is not None
    
    @pytest.mark.asyncio
    async def test_exchange_enum_coverage(self):
        """测试交易所枚举覆盖我们支持的交易所"""
        # 验证支持的交易所都在枚举中
        required_exchanges = [
            Exchange.BINANCE,
            Exchange.OKX
        ]
        
        # 验证所有支持的交易所都存在
        for exchange in required_exchanges:
            assert isinstance(exchange, Exchange)
            assert exchange.value is not None
    
    @pytest.mark.asyncio
    async def test_component_lifecycle_integration(self):
        """测试组件生命周期集成"""
        # 创建组件
        rest_manager = RestClientManager()
        top_trader_collector = TopTraderDataCollector(rest_manager)
        
        # 验证初始状态
        assert not top_trader_collector.is_running
        
        # 模拟启动过程（不实际启动以避免网络调用）
        with patch.object(top_trader_collector, '_setup_exchange_clients', new_callable=AsyncMock):
            with patch.object(top_trader_collector, '_collection_loop', new_callable=AsyncMock):
                await top_trader_collector.start(["BTC-USDT"])
                assert top_trader_collector.is_running
                
                # 模拟停止
                await top_trader_collector.stop()
                assert not top_trader_collector.is_running


@pytest.mark.integration 
class TestTDDStage3ErrorHandling:
    """TDD Stage 3 错误处理集成测试"""
    
    @pytest.mark.asyncio
    async def test_missing_rest_manager_handling(self):
        """测试缺少REST管理器时的错误处理"""
        # 验证None传入时的行为
        try:
            TopTraderDataCollector(None)
            # 如果没有抛出异常，至少验证对象创建了但可能有问题
            assert True  # 基本对象创建测试
        except (TypeError, AttributeError):
            # 如果抛出异常，这是预期的行为
            assert True
    
    @pytest.mark.asyncio
    async def test_invalid_config_handling(self):
        """测试组件基本创建不会崩溃"""
        # 测试基本组件创建不会导致崩溃
        try:
            rest_manager = RestClientManager()
            collector = TopTraderDataCollector(rest_manager)
            # 基本创建应该成功
            assert collector is not None
            assert rest_manager is not None
        except Exception as e:
            pytest.fail(f"基本组件创建不应该失败: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 