"""
test_nats_client.py - 修复版本
批量修复应用：异步清理、导入路径、Mock回退
"""
from datetime import datetime, timezone
import os
import sys
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

# 添加路径
sys.path.insert(0, 'tests')
sys.path.insert(0, os.path.join(os.getcwd(), 'services', 'python-collector', 'src'))

# 导入助手
from helpers import AsyncTestManager, async_test_with_cleanup

# 尝试导入实际模块，失败时使用Mock
try:
    # 实际导入将在这里添加
    MODULES_AVAILABLE = True
except ImportError:
    # Mock类将在这里添加  
    MODULES_AVAILABLE = False

"""
Python Collector NATS客户端单元测试

测试NATS连接、消息发布、流管理等功能
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.nats_client import MarketDataPublisher, NATSManager
from marketprism_collector.config import NATSConfig
from marketprism_collector.data_types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker,
    NormalizedKline, NormalizedFundingRate, NormalizedOpenInterest,
    NormalizedLiquidation, PriceLevel, Exchange, MarketType, DataType
)


class TestMarketDataPublisher:
    """测试市场数据发布器"""
    
    @pytest.fixture
    def nats_config(self):
        """NATS配置fixture"""
        return NATSConfig(
            url="nats://localhost:4222",
            client_name="test-collector"
        )
    
    @pytest.fixture
    def publisher(self, nats_config):
        """发布器fixture"""
        return MarketDataPublisher(nats_config)
    
    def test_publisher_initialization(self, publisher, nats_config):
        """测试发布器初始化"""
        assert publisher.config == nats_config
        assert publisher.client is None
        assert publisher.js is None
        assert publisher.is_connected is False
        
        # 验证主题格式
        assert publisher.trade_subject_format == "market.{exchange}.{symbol}.trade"
        assert publisher.orderbook_subject_format == "market.{exchange}.{symbol}.orderbook"
        assert publisher.kline_subject_format == "market.{exchange}.{symbol}.kline.{interval}"
        assert publisher.ticker_subject_format == "market.{exchange}.{symbol}.ticker"
        assert publisher.funding_rate_subject_format == "market.{exchange}.{symbol}.funding_rate"
        assert publisher.open_interest_subject_format == "market.{exchange}.{symbol}.open_interest"
        assert publisher.liquidation_subject_format == "market.{exchange}.{symbol}.liquidation"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_connect_success(self, publisher):
        """测试成功连接NATS"""
        # Mock NATS客户端
        mock_client = AsyncMock()
        mock_js = AsyncMock()
        
        # jetstream()方法是同步的，使用MagicMock而不是AsyncMock
        mock_client.jetstream = MagicMock(return_value=mock_js)
        
        # Mock _ensure_streams方法以避免复杂的流创建逻辑
        with patch('marketprism_collector.nats_client.nats.connect') as mock_connect, \
             patch.object(publisher, '_ensure_streams') as mock_ensure_streams:
            
            mock_connect.return_value = mock_client
            mock_ensure_streams.return_value = None  # async方法返回None表示成功
            
            result = await publisher.connect()
            
            assert result is True
            assert publisher.is_connected is True
            assert publisher.client == mock_client
            assert publisher.js == mock_js
            mock_ensure_streams.assert_called_once()
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_connect_failure(self, publisher):
        """测试连接NATS失败"""
        with patch('marketprism_collector.nats_client.nats.connect', side_effect=Exception("Connection failed")):
            result = await publisher.connect()
            
            assert result is False
            assert publisher.is_connected is False
            assert publisher.client is None
            assert publisher.js is None
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_disconnect(self, publisher):
        """测试断开NATS连接"""
        # 设置已连接状态
        mock_client = AsyncMock()
        mock_client.is_closed = False
        publisher.client = mock_client
        publisher.is_connected = True
        
        await publisher.disconnect()
        
        mock_client.close.assert_called_once()
        assert publisher.is_connected is False
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_ensure_streams_existing(self, publisher):
        """测试确保流存在 - 流已存在"""
        mock_js = AsyncMock()
        mock_js.stream_info = AsyncMock(return_value={"name": "MARKET_DATA"})
        publisher.js = mock_js
        
        await publisher._ensure_streams()
        
        # 验证只调用了stream_info，没有创建新流
        mock_js.stream_info.assert_called()
        mock_js.add_stream.assert_not_called()
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_ensure_streams_create_new(self, publisher):
        """测试确保流存在 - 创建新流"""
        mock_js = AsyncMock()
        # 第一次调用stream_info抛出异常（流不存在）
        mock_js.stream_info = AsyncMock(side_effect=Exception("Stream not found"))
        mock_js.add_stream = AsyncMock()
        publisher.js = mock_js
        
        with patch('marketprism_collector.nats_client.StreamConfig') as mock_stream_config:
            mock_config_instance = MagicMock()
            mock_stream_config.return_value = mock_config_instance
            
            await publisher._ensure_streams()
            
            # 验证创建了新流
            mock_js.add_stream.assert_called_once_with(mock_config_instance)
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_trade_success(self, publisher):
        """测试成功发布交易数据"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 123
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试交易数据
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=datetime.now(timezone.utc),
            side="sell"
        )
        
        result = await publisher.publish_trade(trade)
        
        assert result is True
        mock_js.publish.assert_called_once()
        
        # 验证主题格式
        call_args = mock_js.publish.call_args
        subject = call_args[0][0]
        assert subject == "market.binance.btcusdt.trade"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_trade_not_connected(self, publisher):
        """测试未连接时发布交易数据"""
        publisher.is_connected = False
        
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=datetime.now(timezone.utc),
            side="sell"
        )
        
        result = await publisher.publish_trade(trade)
        
        assert result is False
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_orderbook_success(self, publisher):
        """测试成功发布订单簿数据"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 124
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试订单簿数据
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            bids=[PriceLevel(price=Decimal("49999.00"), quantity=Decimal("0.5"))],
            asks=[PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.3"))],
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_orderbook(orderbook)
        
        assert result is True
        mock_js.publish.assert_called_once()
        
        # 验证主题格式
        call_args = mock_js.publish.call_args
        subject = call_args[0][0]
        assert subject == "market.binance.btcusdt.orderbook"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_ticker_success(self, publisher):
        """测试成功发布行情数据"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 125
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试行情数据
        ticker = NormalizedTicker(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_price=Decimal("50000.00"),
            open_price=Decimal("49000.00"),
            high_price=Decimal("51000.00"),
            low_price=Decimal("48000.00"),
            volume=Decimal("1000.0"),
            quote_volume=Decimal("50000000.0"),
            price_change=Decimal("1000.00"),
            price_change_percent=Decimal("2.04"),
            weighted_avg_price=Decimal("49500.00"),
            last_quantity=Decimal("0.1"),
            best_bid_price=Decimal("49999.00"),
            best_bid_quantity=Decimal("0.5"),
            best_ask_price=Decimal("50001.00"),
            best_ask_quantity=Decimal("0.3"),
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            trade_count=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_ticker(ticker)
        
        assert result is True
        mock_js.publish.assert_called_once()
        
        # 验证主题格式
        call_args = mock_js.publish.call_args
        subject = call_args[0][0]
        assert subject == "market.binance.btcusdt.ticker"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_kline_success(self, publisher):
        """测试成功发布K线数据"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 126
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试K线数据
        kline = NormalizedKline(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            interval="1m",
            open_price=Decimal("49000.00"),
            high_price=Decimal("51000.00"),
            low_price=Decimal("48000.00"),
            close_price=Decimal("50000.00"),
            volume=Decimal("1000.0"),
            quote_volume=Decimal("50000000.0"),
            trade_count=500,
            taker_buy_volume=Decimal("600.0"),
            taker_buy_quote_volume=Decimal("30000000.0")
        )
        
        result = await publisher.publish_kline(kline)
        
        assert result is True
        mock_js.publish.assert_called_once()
        
        # 验证主题格式
        call_args = mock_js.publish.call_args
        subject = call_args[0][0]
        assert subject == "market.binance.btcusdt.kline.1m"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_funding_rate_success(self, publisher):
        """测试成功发布资金费率数据"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 127
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试资金费率数据
        funding_rate = NormalizedFundingRate(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            funding_rate=Decimal("0.0001"),
            next_funding_time=datetime.now(timezone.utc),
            mark_price=Decimal("50000.00"),
            index_price=Decimal("49999.50"),
            premium_index=Decimal("0.50"),
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_funding_rate(funding_rate)
        
        assert result is True
        mock_js.publish.assert_called_once()
        
        # 验证主题格式（符号中的-被替换为_）
        call_args = mock_js.publish.call_args
        subject = call_args[0][0]
        assert subject == "market.binance.btc_usdt.funding_rate"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_open_interest_success(self, publisher):
        """测试成功发布持仓量数据"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 128
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试持仓量数据
        open_interest = NormalizedOpenInterest(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            open_interest=Decimal("1000000.0"),
            open_interest_value=Decimal("50000000000.0"),
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_open_interest(open_interest)
        
        assert result is True
        mock_js.publish.assert_called_once()
        
        # 验证主题格式
        call_args = mock_js.publish.call_args
        subject = call_args[0][0]
        assert subject == "market.binance.btc_usdt.open_interest"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_liquidation_success(self, publisher):
        """测试成功发布强平数据"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 129
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试强平数据
        liquidation = NormalizedLiquidation(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            side="sell",
            price=Decimal("49000.00"),
            quantity=Decimal("0.5"),
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_liquidation(liquidation)
        
        assert result is True
        mock_js.publish.assert_called_once()
        
        # 验证主题格式
        call_args = mock_js.publish.call_args
        subject = call_args[0][0]
        assert subject == "market.binance.btc_usdt.liquidation"
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_data_exception(self, publisher):
        """测试发布数据时发生异常"""
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_js.publish.side_effect = Exception("Publish failed")
        publisher.js = mock_js
        
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="12345",
            price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.00"),
            timestamp=datetime.now(timezone.utc),
            side="sell"
        )
        
        result = await publisher.publish_trade(trade)
        
        assert result is False
    
    def test_get_health_status_connected(self, publisher):
        """测试获取健康状态 - 已连接"""
        publisher.is_connected = True
        
        status = publisher.get_health_status()
        
        assert status["connected"] is True
        assert status["client_name"] == "test-collector"
        assert "last_check" in status
    
    def test_get_health_status_disconnected(self, publisher):
        """测试获取健康状态 - 未连接"""
        publisher.is_connected = False
        
        status = publisher.get_health_status()
        
        assert status["connected"] is False
        assert status["client_name"] == "test-collector"
        assert "last_check" in status
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_error_handler(self, publisher):
        """测试错误处理器"""
        # 这个方法主要是记录日志，我们验证它不会抛出异常
        await publisher._error_handler(Exception("Test error"))
        # 如果没有异常，测试通过
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_closed_handler(self, publisher):
        """测试连接关闭处理器"""
        publisher.is_connected = True
        
        await publisher._closed_handler()
        
        assert publisher.is_connected is False
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_reconnected_handler(self, publisher):
        """测试重连处理器"""
        publisher.is_connected = False
        
        await publisher._reconnected_handler()
        
        assert publisher.is_connected is True


class TestNATSManager:
    """测试NATS管理器"""
    
    @pytest.fixture
    def nats_config(self):
        """NATS配置fixture"""
        return NATSConfig(
            url="nats://localhost:4222",
            client_name="test-manager"
        )
    
    @pytest.fixture
    def manager(self, nats_config):
        """管理器fixture"""
        return NATSManager(nats_config)
    
    def test_manager_initialization(self, manager, nats_config):
        """测试管理器初始化"""
        assert manager.config == nats_config
        assert isinstance(manager.publisher, MarketDataPublisher)
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_start_success(self, manager):
        """测试成功启动管理器"""
        with patch.object(manager.publisher, 'connect', return_value=True):
            result = await manager.start()
            
            assert result is True
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_start_failure(self, manager):
        """测试启动管理器失败"""
        with patch.object(manager.publisher, 'connect', return_value=False):
            result = await manager.start()
            
            assert result is False
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_stop(self, manager):
        """测试停止管理器"""
        with patch.object(manager.publisher, 'disconnect') as mock_disconnect:
            await manager.stop()
            
            mock_disconnect.assert_called_once()
    
    def test_get_publisher(self, manager):
        """测试获取发布器"""
        publisher = manager.get_publisher()
        
        assert publisher == manager.publisher
        assert isinstance(publisher, MarketDataPublisher)
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_health_check(self, manager):
        """测试健康检查"""
        mock_status = {
            "connected": True,
            "client_name": "test-manager",
            "last_check": datetime.now(timezone.utc).isoformat()
        }
        
        with patch.object(manager.publisher, 'get_health_status', return_value=mock_status):
            status = await manager.health_check()
            
            # NATSManager的health_check方法返回包装后的结构
            assert status["nats"] == mock_status
            assert "status" in status


class TestNATSIntegration:
    """测试NATS集成"""
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """测试完整的工作流程"""
        config = NATSConfig(
            url="nats://localhost:4222",
            client_name="integration-test"
        )
        
        manager = NATSManager(config)
        publisher = manager.get_publisher()
        
        # Mock连接
        with patch.object(publisher, 'connect', return_value=True):
            # 启动管理器
            start_result = await manager.start()
            assert start_result is True
            
            # 获取健康状态
            with patch.object(publisher, 'get_health_status', return_value={"connected": True}):
                health = await manager.health_check()
                # NATSManager返回包装后的结构
                assert health["nats"]["connected"] is True
                assert "status" in health
            
            # 停止管理器
            with patch.object(publisher, 'disconnect'):
                await manager.stop()
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_publish_all_data_types(self):
        """测试发布所有数据类型"""
        config = NATSConfig()
        publisher = MarketDataPublisher(config)
        
        # 设置连接状态
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 1
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 创建测试数据
        trade = NormalizedTrade(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            trade_id="1",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000"),
            timestamp=datetime.now(timezone.utc),
            side="sell"
        )
        
        orderbook = NormalizedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            bids=[PriceLevel(price=Decimal("49999"), quantity=Decimal("0.5"))],
            asks=[PriceLevel(price=Decimal("50001"), quantity=Decimal("0.3"))],
            timestamp=datetime.now(timezone.utc)
        )
        
        ticker = NormalizedTicker(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_price=Decimal("50000"),
            open_price=Decimal("49000"),
            high_price=Decimal("51000"),
            low_price=Decimal("48000"),
            volume=Decimal("1000"),
            quote_volume=Decimal("50000000"),
            price_change=Decimal("1000"),
            price_change_percent=Decimal("2.04"),
            weighted_avg_price=Decimal("49500"),
            last_quantity=Decimal("0.1"),
            best_bid_price=Decimal("49999"),
            best_bid_quantity=Decimal("0.5"),
            best_ask_price=Decimal("50001"),
            best_ask_quantity=Decimal("0.3"),
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            trade_count=1000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # 发布所有数据类型
        trade_result = await publisher.publish_trade(trade)
        orderbook_result = await publisher.publish_orderbook(orderbook)
        ticker_result = await publisher.publish_ticker(ticker)
        
        assert trade_result is True
        assert orderbook_result is True
        assert ticker_result is True
        
        # 验证发布了3次
        assert mock_js.publish.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 