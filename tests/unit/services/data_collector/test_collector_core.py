"""
数据收集器核心功能测试
测试MarketDataCollector的核心逻辑和功能
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

# 导入被测试的模块
try:
    from marketprism_collector.collector import MarketDataCollector
    from marketprism_collector.config import CollectorConfig
    from marketprism_collector.types import TradeData, OrderBookData, TickerData
except ImportError as e:
    pytest.skip(f"数据收集器模块导入失败: {e}", allow_module_level=True)


class TestMarketDataCollectorInitialization:
    """数据收集器初始化测试"""
    
    def test_collector_initialization_with_default_config(self):
        """测试使用默认配置初始化收集器"""
        config = CollectorConfig()
        collector = MarketDataCollector(config)
        
        assert collector is not None
        assert collector.config == config
        assert hasattr(collector, '_exchanges')
        assert hasattr(collector, '_subscriptions')
        assert hasattr(collector, '_running')
        
    def test_collector_initialization_with_custom_config(self, sample_config):
        """测试使用自定义配置初始化收集器"""
        config = CollectorConfig(**sample_config)
        collector = MarketDataCollector(config)
        
        assert collector.config == config
        assert collector.config.exchanges is not None
        
    def test_collector_initialization_validates_config(self):
        """测试收集器初始化时验证配置"""
        # 测试无效配置
        with pytest.raises((ValueError, TypeError)):
            MarketDataCollector(None)
            
    def test_collector_has_required_attributes(self):
        """测试收集器具有必需的属性"""
        config = CollectorConfig()
        collector = MarketDataCollector(config)
        
        required_attributes = [
            '_exchanges', '_subscriptions', '_running',
            '_metrics', '_health_checker', '_logger'
        ]
        
        for attr in required_attributes:
            assert hasattr(collector, attr), f"缺少必需属性: {attr}"


class TestMarketDataCollectorExchangeManagement:
    """数据收集器交易所管理测试"""
    
    @pytest.fixture
    def collector(self, sample_config):
        """创建测试用的收集器实例"""
        config = CollectorConfig(**sample_config)
        return MarketDataCollector(config)
        
    def test_collector_loads_enabled_exchanges(self, collector):
        """测试收集器加载启用的交易所"""
        # 模拟交易所配置
        with patch.object(collector, '_load_exchanges') as mock_load:
            collector._initialize_exchanges()
            mock_load.assert_called_once()
            
    def test_collector_creates_exchange_adapters(self, collector):
        """测试收集器创建交易所适配器"""
        with patch('marketprism_collector.exchanges.BinanceAdapter') as mock_binance:
            with patch('marketprism_collector.exchanges.OKXAdapter') as mock_okx:
                mock_binance.return_value = Mock()
                mock_okx.return_value = Mock()
                
                collector._create_exchange_adapters()
                
                # 验证适配器创建
                assert len(collector._exchanges) > 0
                
    def test_collector_validates_exchange_config(self, collector):
        """测试收集器验证交易所配置"""
        invalid_exchange_config = {
            "binance": {
                "enabled": True,
                # 缺少必需的api_key和api_secret
            }
        }
        
        with pytest.raises(ValueError):
            collector._validate_exchange_config(invalid_exchange_config)
            
    def test_collector_handles_exchange_connection_errors(self, collector):
        """测试收集器处理交易所连接错误"""
        mock_adapter = AsyncMock()
        mock_adapter.connect.side_effect = ConnectionError("连接失败")
        
        collector._exchanges = {"binance": mock_adapter}
        
        # 测试连接错误处理
        with pytest.raises(ConnectionError):
            asyncio.run(collector._connect_exchange("binance"))


class TestMarketDataCollectorSubscriptionManagement:
    """数据收集器订阅管理测试"""
    
    @pytest.fixture
    def collector_with_mock_exchanges(self, sample_config):
        """创建带有模拟交易所的收集器"""
        config = CollectorConfig(**sample_config)
        collector = MarketDataCollector(config)
        
        # 添加模拟交易所适配器
        mock_binance = AsyncMock()
        mock_okx = AsyncMock()
        
        collector._exchanges = {
            "binance": mock_binance,
            "okx": mock_okx
        }
        
        return collector
        
    async def test_collector_subscribe_to_trades(self, collector_with_mock_exchanges):
        """测试订阅交易数据"""
        collector = collector_with_mock_exchanges
        
        await collector.subscribe_trades("binance", "BTCUSDT")
        
        # 验证订阅调用
        collector._exchanges["binance"].subscribe_trades.assert_called_once_with("BTCUSDT")
        
        # 验证订阅记录
        assert ("binance", "BTCUSDT", "trades") in collector._subscriptions
        
    async def test_collector_subscribe_to_orderbook(self, collector_with_mock_exchanges):
        """测试订阅订单簿数据"""
        collector = collector_with_mock_exchanges
        
        await collector.subscribe_orderbook("binance", "BTCUSDT")
        
        collector._exchanges["binance"].subscribe_orderbook.assert_called_once_with("BTCUSDT")
        assert ("binance", "BTCUSDT", "orderbook") in collector._subscriptions
        
    async def test_collector_subscribe_to_ticker(self, collector_with_mock_exchanges):
        """测试订阅行情数据"""
        collector = collector_with_mock_exchanges
        
        await collector.subscribe_ticker("binance", "BTCUSDT")
        
        collector._exchanges["binance"].subscribe_ticker.assert_called_once_with("BTCUSDT")
        assert ("binance", "BTCUSDT", "ticker") in collector._subscriptions
        
    async def test_collector_unsubscribe_from_data(self, collector_with_mock_exchanges):
        """测试取消订阅数据"""
        collector = collector_with_mock_exchanges
        
        # 先订阅
        await collector.subscribe_trades("binance", "BTCUSDT")
        
        # 再取消订阅
        await collector.unsubscribe("binance", "BTCUSDT", "trades")
        
        collector._exchanges["binance"].unsubscribe_trades.assert_called_once_with("BTCUSDT")
        assert ("binance", "BTCUSDT", "trades") not in collector._subscriptions
        
    async def test_collector_batch_subscribe(self, collector_with_mock_exchanges):
        """测试批量订阅"""
        collector = collector_with_mock_exchanges
        
        subscriptions = [
            {"exchange": "binance", "symbol": "BTCUSDT", "data_types": ["trades", "ticker"]},
            {"exchange": "okx", "symbol": "ETH-USDT", "data_types": ["orderbook"]}
        ]
        
        await collector.batch_subscribe(subscriptions)
        
        # 验证批量订阅调用
        collector._exchanges["binance"].subscribe_trades.assert_called_with("BTCUSDT")
        collector._exchanges["binance"].subscribe_ticker.assert_called_with("BTCUSDT")
        collector._exchanges["okx"].subscribe_orderbook.assert_called_with("ETH-USDT")


class TestMarketDataCollectorDataProcessing:
    """数据收集器数据处理测试"""
    
    @pytest.fixture
    def collector_with_processors(self, sample_config):
        """创建带有数据处理器的收集器"""
        config = CollectorConfig(**sample_config)
        collector = MarketDataCollector(config)
        
        # 模拟数据处理器
        collector._data_processor = Mock()
        collector._normalizer = Mock()
        collector._nats_client = AsyncMock()
        
        return collector
        
    async def test_collector_processes_trade_data(self, collector_with_processors, sample_trade_data):
        """测试处理交易数据"""
        collector = collector_with_processors
        
        # 模拟接收到交易数据
        await collector._handle_trade_data("binance", sample_trade_data)
        
        # 验证数据处理流程
        collector._normalizer.normalize_trade.assert_called_once_with(sample_trade_data)
        collector._nats_client.publish.assert_called_once()
        
    async def test_collector_processes_orderbook_data(self, collector_with_processors, sample_orderbook_data):
        """测试处理订单簿数据"""
        collector = collector_with_processors
        
        await collector._handle_orderbook_data("binance", sample_orderbook_data)
        
        collector._normalizer.normalize_orderbook.assert_called_once_with(sample_orderbook_data)
        collector._nats_client.publish.assert_called_once()
        
    async def test_collector_processes_ticker_data(self, collector_with_processors, sample_ticker_data):
        """测试处理行情数据"""
        collector = collector_with_processors
        
        await collector._handle_ticker_data("binance", sample_ticker_data)
        
        collector._normalizer.normalize_ticker.assert_called_once_with(sample_ticker_data)
        collector._nats_client.publish.assert_called_once()
        
    async def test_collector_handles_data_processing_errors(self, collector_with_processors):
        """测试数据处理错误处理"""
        collector = collector_with_processors
        
        # 模拟处理错误
        collector._normalizer.normalize_trade.side_effect = ValueError("数据格式错误")
        
        invalid_data = {"invalid": "data"}
        
        # 应该不抛出异常，而是记录错误
        await collector._handle_trade_data("binance", invalid_data)
        
        # 验证错误被记录
        assert collector._metrics.increment.called
        
    async def test_collector_validates_incoming_data(self, collector_with_processors):
        """测试验证传入数据"""
        collector = collector_with_processors
        
        # 测试有效数据
        valid_data = {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "quantity": 0.1,
            "timestamp": 1640995200000
        }
        
        is_valid = collector._validate_trade_data(valid_data)
        assert is_valid is True
        
        # 测试无效数据
        invalid_data = {"symbol": "BTCUSDT"}  # 缺少必需字段
        
        is_valid = collector._validate_trade_data(invalid_data)
        assert is_valid is False


class TestMarketDataCollectorLifecycle:
    """数据收集器生命周期测试"""
    
    @pytest.fixture
    def collector_with_mocks(self, sample_config):
        """创建带有所有模拟组件的收集器"""
        config = CollectorConfig(**sample_config)
        collector = MarketDataCollector(config)
        
        # 模拟所有组件
        collector._exchanges = {"binance": AsyncMock(), "okx": AsyncMock()}
        collector._nats_client = AsyncMock()
        collector._health_checker = AsyncMock()
        collector._metrics = Mock()
        
        return collector
        
    async def test_collector_start_lifecycle(self, collector_with_mocks):
        """测试收集器启动生命周期"""
        collector = collector_with_mocks
        
        await collector.start()
        
        # 验证启动流程
        assert collector._running is True
        collector._nats_client.connect.assert_called_once()
        
        for exchange_adapter in collector._exchanges.values():
            exchange_adapter.connect.assert_called_once()
            
    async def test_collector_stop_lifecycle(self, collector_with_mocks):
        """测试收集器停止生命周期"""
        collector = collector_with_mocks
        
        # 先启动
        collector._running = True
        
        await collector.stop()
        
        # 验证停止流程
        assert collector._running is False
        collector._nats_client.close.assert_called_once()
        
        for exchange_adapter in collector._exchanges.values():
            exchange_adapter.disconnect.assert_called_once()
            
    async def test_collector_graceful_shutdown(self, collector_with_mocks):
        """测试收集器优雅关闭"""
        collector = collector_with_mocks
        collector._running = True
        
        # 模拟正在进行的订阅
        collector._subscriptions = {
            ("binance", "BTCUSDT", "trades"),
            ("okx", "ETH-USDT", "orderbook")
        }
        
        await collector.shutdown()
        
        # 验证优雅关闭流程
        assert len(collector._subscriptions) == 0
        assert collector._running is False
        
    async def test_collector_health_check(self, collector_with_mocks):
        """测试收集器健康检查"""
        collector = collector_with_mocks
        
        # 模拟健康状态
        collector._health_checker.check_health.return_value = {
            "status": "healthy",
            "exchanges": {"binance": "connected", "okx": "connected"},
            "subscriptions": 2
        }
        
        health_status = await collector.get_health_status()
        
        assert health_status["status"] == "healthy"
        assert "exchanges" in health_status
        assert "subscriptions" in health_status


@pytest.mark.integration
class TestMarketDataCollectorIntegration:
    """数据收集器集成测试"""
    
    async def test_collector_end_to_end_data_flow(self, sample_config):
        """测试端到端数据流"""
        config = CollectorConfig(**sample_config)
        collector = MarketDataCollector(config)
        
        # 模拟完整的数据流
        with patch.multiple(
            collector,
            _exchanges={"binance": AsyncMock()},
            _nats_client=AsyncMock(),
            _normalizer=Mock(),
            _data_processor=Mock()
        ):
            # 启动收集器
            await collector.start()
            
            # 订阅数据
            await collector.subscribe_trades("binance", "BTCUSDT")
            
            # 模拟接收数据
            trade_data = {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "quantity": 0.1,
                "timestamp": 1640995200000
            }
            
            await collector._handle_trade_data("binance", trade_data)
            
            # 验证数据流
            collector._normalizer.normalize_trade.assert_called_once()
            collector._nats_client.publish.assert_called_once()
            
            # 停止收集器
            await collector.stop()
            
    async def test_collector_error_recovery(self, sample_config):
        """测试收集器错误恢复"""
        config = CollectorConfig(**sample_config)
        collector = MarketDataCollector(config)
        
        mock_adapter = AsyncMock()
        mock_adapter.connect.side_effect = [
            ConnectionError("首次连接失败"),
            None  # 第二次连接成功
        ]
        
        collector._exchanges = {"binance": mock_adapter}
        
        # 测试重连机制
        with patch.object(collector, '_retry_connection') as mock_retry:
            mock_retry.return_value = True
            
            await collector._connect_with_retry("binance")
            
            # 验证重试被调用
            mock_retry.assert_called_once()
