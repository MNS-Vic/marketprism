"""
NATS客户端覆盖率提升测试
专门测试未覆盖的代码路径，提升覆盖率从89%到95%+
"""

from datetime import datetime, timezone
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal
import json

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'services', 'python-collector', 'src'))

from marketprism_collector.nats_client import (
    MarketDataPublisher, NATSManager, EnhancedMarketDataPublisher
)
from marketprism_collector.data_types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedKline, 
    NormalizedTicker, NormalizedFundingRate, NormalizedOpenInterest,
    NormalizedLiquidation, NormalizedTopTraderLongShortRatio,
    PriceLevel
)
from marketprism_collector.config import NATSConfig


class TestNATSCoverageBoost:
    """NATS客户端覆盖率提升测试"""
    
    @pytest.fixture
    def nats_config(self):
        """NATS配置"""
        return NATSConfig(
            url="nats://localhost:4222",
            client_name="test_client",
            max_reconnect_attempts=3,
            reconnect_time_wait=2.0
        )
    
    @pytest.fixture
    def publisher(self, nats_config):
        """NATS发布器实例"""
        return MarketDataPublisher(nats_config)
    
    @pytest.mark.asyncio
    async def test_stream_creation_exception(self, publisher):
        """测试流创建异常处理 - 覆盖109-111行"""
        publisher.is_connected = True
        mock_js = AsyncMock()
        
        # 模拟流创建失败
        mock_js.stream_info.side_effect = Exception("流不存在")
        mock_js.add_stream.side_effect = Exception("创建流失败")
        publisher.js = mock_js
        
        # 应该抛出异常
        with pytest.raises(Exception, match="创建流失败"):
            await publisher._ensure_streams()
    
    @pytest.mark.asyncio 
    async def test_publish_data_json_fallback(self, publisher):
        """测试_publish_data的json序列化路径 - 覆盖179-184行"""
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 1
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        # 测试普通字典数据（没有json方法）
        dict_data = {
            "exchange": "binance", 
            "symbol": "BTCUSDT",
            "price": "50000"
        }
        
        result = await publisher._publish_data("test.subject", dict_data)
        
        assert result is True
        mock_js.publish.assert_called_once()
        # 验证调用了json.dumps
        call_args = mock_js.publish.call_args[0]
        assert call_args[0] == "test.subject"
        assert b'"exchange": "binance"' in call_args[1]
    
    @pytest.mark.asyncio
    async def test_publish_data_exception_handling(self, publisher):
        """测试_publish_data异常处理 - 覆盖199行"""
        publisher.is_connected = True
        mock_js = AsyncMock()
        mock_js.publish.side_effect = Exception("发布失败")
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
        
        result = await publisher._publish_data("test.subject", trade)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_error_handler(self, publisher):
        """测试错误处理器 - 覆盖298行"""
        test_error = Exception("测试错误")
        
        # 应该不抛出异常
        await publisher._error_handler(test_error)
    
    @pytest.mark.asyncio
    async def test_closed_handler(self, publisher):
        """测试连接关闭处理器 - 覆盖299-300行"""
        publisher.is_connected = True
        
        await publisher._closed_handler()
        
        assert publisher.is_connected is False
    
    @pytest.mark.asyncio
    async def test_reconnected_handler(self, publisher):
        """测试重连处理器 - 覆盖301-302行"""
        publisher.is_connected = False
        
        await publisher._reconnected_handler()
        
        assert publisher.is_connected is True
    
    def test_get_health_status(self, publisher):
        """测试健康状态获取 - 确保覆盖完整"""
        publisher.is_connected = True
        
        status = publisher.get_health_status()
        
        assert status["connected"] is True
        assert status["server_url"] == publisher.config.url
        assert status["client_name"] == publisher.config.client_name
        assert "last_check" in status


class TestNATSManagerCoverage:
    """NATS管理器覆盖率测试"""
    
    @pytest.fixture
    def nats_config(self):
        return NATSConfig(url="nats://localhost:4222")
    
    @pytest.fixture
    def manager(self, nats_config):
        return NATSManager(nats_config)
    
    @pytest.mark.asyncio
    async def test_manager_start_stop(self, manager):
        """测试管理器启动停止 - 覆盖321-330行"""
        with patch.object(manager.publisher, 'connect', return_value=True) as mock_connect:
            result = await manager.start()
            assert result is True
            mock_connect.assert_called_once()
        
        with patch.object(manager.publisher, 'disconnect') as mock_disconnect:
            await manager.stop()
            mock_disconnect.assert_called_once()
    
    def test_get_publisher(self, manager):
        """测试获取发布器实例"""
        publisher = manager.get_publisher()
        assert publisher is manager.publisher
    
    @pytest.mark.asyncio
    async def test_health_check(self, manager):
        """测试健康检查 - 覆盖334-340行"""
        manager.publisher.is_connected = True
        
        health = await manager.health_check()
        
        assert "nats" in health
        assert health["status"] == "healthy"
        
        # 测试未连接状态
        manager.publisher.is_connected = False
        health = await manager.health_check()
        assert health["status"] == "unhealthy"


class TestEnhancedMarketDataPublisher:
    """增强数据发布器覆盖率测试"""
    
    @pytest.fixture
    def base_publisher(self):
        """基础发布器Mock"""
        config = NATSConfig(url="nats://localhost:4222")
        publisher = MarketDataPublisher(config)
        publisher.is_connected = True
        return publisher
    
    @pytest.fixture
    def enhanced_publisher(self, base_publisher):
        """增强发布器"""
        return EnhancedMarketDataPublisher(base_publisher)
    
    @pytest.mark.asyncio
    async def test_enhanced_publisher_initialization(self, enhanced_publisher, base_publisher):
        """测试增强发布器初始化 - 覆盖344行及后续"""
        # 验证所有属性都被正确继承
        assert enhanced_publisher.config is base_publisher.config
        assert enhanced_publisher.logger is base_publisher.logger
        assert enhanced_publisher.client is base_publisher.client
        assert enhanced_publisher.js is base_publisher.js
        assert enhanced_publisher.is_connected is base_publisher.is_connected
        
        # 验证主题格式继承
        assert enhanced_publisher.trade_subject_format == base_publisher.trade_subject_format
        assert enhanced_publisher.orderbook_subject_format == base_publisher.orderbook_subject_format
        
        # 验证新增主题
        assert hasattr(enhanced_publisher, 'orderbook_delta_subject')
        assert hasattr(enhanced_publisher, 'depth_update_subject')


class TestDataTypePublishingCoverage:
    """各种数据类型发布覆盖率测试"""
    
    @pytest.fixture
    def publisher(self):
        """设置好的发布器"""
        config = NATSConfig(url="nats://localhost:4222")
        publisher = MarketDataPublisher(config)
        publisher.is_connected = True
        
        # Mock JetStream
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.seq = 1
        mock_js.publish.return_value = mock_ack
        publisher.js = mock_js
        
        return publisher
    
    @pytest.mark.asyncio
    async def test_publish_kline(self, publisher):
        """测试K线数据发布"""
        kline = NormalizedKline(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            interval="1m",
            open_time=datetime.now(timezone.utc),
            close_time=datetime.now(timezone.utc),
            open_price=Decimal("50000"),
            high_price=Decimal("51000"),
            low_price=Decimal("49000"),
            close_price=Decimal("50500"),
            volume=Decimal("100"),
            quote_volume=Decimal("5000000"),
            trade_count=1000,
            taker_buy_volume=Decimal("40"),  # 必需字段
            taker_buy_quote_volume=Decimal("2000000"),  # 必需字段
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_kline(kline)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_publish_funding_rate(self, publisher):
        """测试资金费率发布"""
        funding_rate = NormalizedFundingRate(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            funding_rate=Decimal("0.0001"),
            next_funding_time=datetime.now(timezone.utc),
            mark_price=Decimal("50000"),  # 必需字段
            index_price=Decimal("49950"),  # 必需字段
            premium_index=Decimal("50"),  # 必需字段
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_funding_rate(funding_rate)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_publish_liquidation(self, publisher):
        """测试强平数据发布"""
        liquidation = NormalizedLiquidation(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            side="long",
            price=Decimal("50000"),
            quantity=Decimal("1.5"),
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_liquidation(liquidation)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_publish_top_trader_ratio(self, publisher):
        """测试大户持仓比发布"""
        top_trader_data = NormalizedTopTraderLongShortRatio(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            long_short_ratio=Decimal("1.25"),
            long_position_ratio=Decimal("0.55"),  # 必需字段
            short_position_ratio=Decimal("0.45"),  # 必需字段
            long_account_ratio=Decimal("0.55"),  # 正确的字段名
            short_account_ratio=Decimal("0.45"),  # 正确的字段名
            timestamp=datetime.now(timezone.utc)
        )
        
        result = await publisher.publish_top_trader_long_short_ratio(top_trader_data)
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__]) 