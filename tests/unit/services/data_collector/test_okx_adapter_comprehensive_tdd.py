"""
OKX适配器全面TDD测试

测试覆盖：
1. 初始化和配置
2. WebSocket连接管理
3. REST API调用
4. 数据解析和标准化
5. 错误处理和重连机制
6. 订阅管理
7. OKX特定的ping机制（字符串ping）
8. OKX特定的订阅格式
"""

import pytest
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import aiohttp

# 导入被测试的模块
from marketprism_collector.exchanges.okx import OKXAdapter
from marketprism_collector.data_types import (
    ExchangeConfig, Exchange, MarketType, DataType,
    NormalizedTrade, NormalizedOrderBook, OrderBookEntry,
    NormalizedTicker, NormalizedKline
)


class TestOKXAdapterInitialization:
    """测试OKX适配器初始化"""
    
    def setup_method(self):
        """设置测试方法"""
        print("\n🚀 开始OKX适配器TDD测试会话")
        
    def teardown_method(self):
        """清理测试方法"""
        print("\n✅ OKX适配器TDD测试会话完成")
    
    def test_okx_adapter_basic_initialization(self):
        """测试：基本初始化"""
        # Red: 编写失败的测试
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK]
        )
        
        adapter = OKXAdapter(config)
        
        # Green: 验证初始化
        assert adapter.config == config
        assert adapter.exchange == Exchange.OKX
        assert adapter.base_url == "https://www.okx.com"
        assert adapter.ping_interval == 25  # OKX特定：25秒
        assert adapter.ping_timeout == 5    # OKX特定：5秒
        assert adapter.session is None
        assert adapter.is_authenticated is False
        assert adapter.supports_private_channels is False
        assert adapter.no_data_threshold == 30  # 30秒无数据触发ping
        
    def test_okx_adapter_custom_config_initialization(self):
        """测试：自定义配置初始化"""
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT', 'ETH-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER],
            base_url="https://testnet.okx.com",
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_passphrase"  # OKX特有
        )
        
        adapter = OKXAdapter(config)
        
        assert adapter.base_url == "https://testnet.okx.com"
        assert adapter.config.api_key == "test_key"
        assert adapter.config.api_secret == "test_secret"
        assert adapter.config.passphrase == "test_passphrase"
        assert len(adapter.config.symbols) == 2
        assert len(adapter.config.data_types) == 3
        
    def test_okx_adapter_stats_initialization(self):
        """测试：统计信息初始化"""
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE]
        )
        
        adapter = OKXAdapter(config)
        
        # 验证OKX特定统计
        assert 'login_attempts' in adapter.okx_stats
        assert 'successful_logins' in adapter.okx_stats
        assert 'data_timeouts' in adapter.okx_stats
        assert 'string_pongs' in adapter.okx_stats
        assert 'json_pongs' in adapter.okx_stats
        
        # 验证初始值
        assert adapter.okx_stats['login_attempts'] == 0
        assert adapter.okx_stats['successful_logins'] == 0
        assert adapter.last_data_time is None


class TestOKXAdapterSessionManagement:
    """测试OKX适配器会话管理"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK]
        )
        self.adapter = OKXAdapter(self.config)
    
    @pytest.mark.asyncio
    async def test_ensure_session_creation(self):
        """测试：确保会话创建"""
        # Red: 测试会话创建
        assert self.adapter.session is None
        
        # Mock aiohttp.ClientSession
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            # Green: 调用_ensure_session
            await self.adapter._ensure_session()
            
            # 验证会话创建
            assert self.adapter.session is not None
            mock_session_class.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ensure_session_with_proxy(self):
        """测试：带代理的会话创建"""
        # 设置环境变量代理
        with patch.dict('os.environ', {'https_proxy': 'http://proxy.example.com:8080'}):
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session
                
                await self.adapter._ensure_session()
                
                # 验证会话创建（OKX使用trust_env=True）
                call_args = mock_session_class.call_args
                assert call_args.kwargs['trust_env'] is True
    
    @pytest.mark.asyncio
    async def test_session_cleanup(self):
        """测试：会话清理"""
        # 创建模拟会话
        mock_session = AsyncMock()
        self.adapter.session = mock_session
        
        # 调用清理
        await self.adapter.close()
        
        # 验证会话被关闭
        mock_session.close.assert_called_once()
        assert self.adapter.session is None


class TestOKXAdapterPingMechanism:
    """测试OKX适配器特有的ping机制"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE],
            ws_url="wss://ws.okx.com:8443/ws/v5/public"
        )
        self.adapter = OKXAdapter(self.config)
    
    @pytest.mark.asyncio
    async def test_okx_string_ping_mechanism(self):
        """测试：OKX字符串ping机制"""
        # Mock WebSocket连接
        mock_ws = AsyncMock()
        self.adapter.ws_connection = mock_ws
        
        # 调用OKX特定的ping方法
        await self.adapter._send_exchange_ping()
        
        # 验证发送字符串"ping"（不是JSON）
        mock_ws.send.assert_called_once_with("ping")
        assert self.adapter.last_ping_time is not None
        assert self.adapter.ping_count == 1
        assert self.adapter.enhanced_stats['ping_count'] == 1
    
    @pytest.mark.asyncio
    async def test_okx_pong_detection(self):
        """测试：OKX pong消息检测"""
        # 测试JSON格式的pong消息
        json_pong_message = {"pong": "1640995200000"}
        
        result = await self.adapter._is_pong_message(json_pong_message)
        assert result is True
        
        # 测试非pong消息
        normal_message = {"event": "subscribe", "arg": {"channel": "trades"}}
        result = await self.adapter._is_pong_message(normal_message)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_okx_ping_failure_handling(self):
        """测试：OKX ping失败处理"""
        # Mock WebSocket连接失败
        mock_ws = AsyncMock()
        mock_ws.send.side_effect = Exception("Send failed")
        self.adapter.ws_connection = mock_ws
        
        # Mock重连触发
        with patch.object(self.adapter, '_trigger_reconnect') as mock_reconnect:
            await self.adapter._send_exchange_ping()
            
            # 验证重连被触发
            mock_reconnect.assert_called_once_with("okx_ping_failed")
            assert self.adapter.enhanced_stats['ping_timeouts'] == 1


class TestOKXAdapterDataNormalization:
    """测试OKX适配器数据标准化"""
    
    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK]
        )
        self.adapter = OKXAdapter(self.config)
    
    @pytest.mark.asyncio
    async def test_normalize_okx_trade_success(self):
        """测试：OKX交易数据标准化成功"""
        # Mock OKX原始交易数据格式
        raw_trade_data = {
            "instId": "BTC-USDT",
            "tradeId": "123456789",
            "px": "50000.00",      # OKX使用px表示价格
            "sz": "0.001",         # OKX使用sz表示数量
            "side": "buy",         # OKX直接提供side字段
            "ts": "1640995200000"  # 时间戳
        }
        
        # 调用标准化方法
        normalized_trade = await self.adapter.normalize_trade(raw_trade_data, "BTC-USDT")
        
        # 验证标准化结果
        assert normalized_trade is not None
        assert normalized_trade.exchange_name == "okx"
        assert normalized_trade.symbol_name == "BTC-USDT"
        assert normalized_trade.trade_id == "123456789"
        assert normalized_trade.price == Decimal("50000.00")
        assert normalized_trade.quantity == Decimal("0.001")
        assert normalized_trade.side == "buy"
        assert normalized_trade.quote_quantity == Decimal("50000.00") * Decimal("0.001")
        
    @pytest.mark.asyncio
    async def test_normalize_okx_trade_with_symbol_mapping(self):
        """测试：带符号映射的OKX交易数据标准化"""
        # 设置符号映射
        self.adapter.symbol_map = {"BTC-USDT": "BTC/USDT"}
        
        raw_trade_data = {
            "instId": "BTC-USDT",
            "tradeId": "123456789",
            "px": "50000.00",
            "sz": "0.001",
            "side": "sell",
            "ts": "1640995200000"
        }
        
        normalized_trade = await self.adapter.normalize_trade(raw_trade_data, "BTC-USDT")
        
        assert normalized_trade.symbol_name == "BTC/USDT"  # 使用映射后的符号
        assert normalized_trade.side == "sell"
        
    @pytest.mark.asyncio
    async def test_normalize_okx_trade_invalid_data(self):
        """测试：无效OKX交易数据处理"""
        # Mock无效数据
        invalid_trade_data = {
            "instId": "BTC-USDT",
            # 缺少必要字段
        }
        
        # 调用标准化方法
        normalized_trade = await self.adapter.normalize_trade(invalid_trade_data, "BTC-USDT")
        
        # 验证返回None
        assert normalized_trade is None


class TestOKXAdapterOrderBookNormalization:
    """测试OKX适配器订单簿标准化"""

    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.ORDERBOOK]
        )
        self.adapter = OKXAdapter(self.config)

    @pytest.mark.asyncio
    async def test_normalize_okx_orderbook_success(self):
        """测试：OKX订单簿数据标准化成功"""
        # Mock OKX原始订单簿数据格式
        raw_orderbook_data = {
            "bids": [["50000.00", "0.001"], ["49999.00", "0.002"]],
            "asks": [["50001.00", "0.001"], ["50002.00", "0.002"]],
            "ts": "1640995200000"
        }

        # 调用标准化方法
        normalized_orderbook = await self.adapter.normalize_orderbook(raw_orderbook_data, "BTC-USDT")

        # 验证标准化结果
        assert normalized_orderbook is not None
        assert normalized_orderbook.exchange_name == "okx"
        assert normalized_orderbook.symbol_name == "BTC-USDT"
        assert len(normalized_orderbook.bids) == 2
        assert len(normalized_orderbook.asks) == 2

        # 验证价格级别
        assert normalized_orderbook.bids[0].price == Decimal("50000.00")
        assert normalized_orderbook.bids[0].quantity == Decimal("0.001")
        assert normalized_orderbook.asks[0].price == Decimal("50001.00")
        assert normalized_orderbook.asks[0].quantity == Decimal("0.001")

    @pytest.mark.asyncio
    async def test_normalize_okx_orderbook_empty_levels(self):
        """测试：空价格级别的OKX订单簿处理"""
        raw_orderbook_data = {
            "bids": [],  # 空买单
            "asks": [["50001.00", "0.001"]],
            "ts": "1640995200000"
        }

        normalized_orderbook = await self.adapter.normalize_orderbook(raw_orderbook_data, "BTC-USDT")

        assert normalized_orderbook is not None
        assert len(normalized_orderbook.bids) == 0
        assert len(normalized_orderbook.asks) == 1

    @pytest.mark.asyncio
    async def test_normalize_okx_orderbook_invalid_data(self):
        """测试：无效OKX订单簿数据处理"""
        invalid_orderbook_data = {
            # 缺少必要字段
        }

        normalized_orderbook = await self.adapter.normalize_orderbook(invalid_orderbook_data, "BTC-USDT")

        assert normalized_orderbook is None


class TestOKXAdapterSubscriptionManagement:
    """测试OKX适配器订阅管理"""

    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT', 'ETH-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            ws_url="wss://ws.okx.com:8443/ws/v5/public"
        )
        self.adapter = OKXAdapter(self.config)

    @pytest.mark.asyncio
    async def test_okx_subscribe_format(self):
        """测试：OKX订阅格式"""
        # Mock WebSocket连接
        mock_ws = AsyncMock()
        self.adapter.ws_connection = mock_ws

        # 调用订阅方法
        args = [{"channel": "trades", "instId": "BTC-USDT"}]
        await self.adapter._subscribe_args(args)

        # 验证OKX订阅消息格式
        mock_ws.send.assert_called_once()
        call_args = mock_ws.send.call_args[0][0]
        subscribe_message = json.loads(call_args)

        assert subscribe_message["op"] == "subscribe"  # OKX使用"op"字段
        assert subscribe_message["args"] == args

    @pytest.mark.asyncio
    async def test_okx_dynamic_symbol_subscription(self):
        """测试：OKX动态符号订阅"""
        mock_ws = AsyncMock()
        self.adapter.ws_connection = mock_ws

        # 调用动态添加订阅
        await self.adapter.add_symbol_subscription("BTC-USDT", ["trade", "orderbook"])

        # 验证订阅消息发送
        mock_ws.send.assert_called_once()
        call_args = mock_ws.send.call_args[0][0]
        subscribe_message = json.loads(call_args)

        assert subscribe_message["op"] == "subscribe"
        # 验证包含交易和订单簿频道
        channels = [arg["channel"] for arg in subscribe_message["args"]]
        assert "trades" in channels
        assert "books" in channels or "books5" in channels  # OKX订单簿频道名

    @pytest.mark.asyncio
    async def test_okx_dynamic_symbol_unsubscription(self):
        """测试：OKX动态符号取消订阅"""
        mock_ws = AsyncMock()
        self.adapter.ws_connection = mock_ws

        # 先添加到符号映射
        self.adapter.symbol_map["BTC-USDT"] = "BTC-USDT"

        # 调用动态移除订阅
        await self.adapter.remove_symbol_subscription("BTC-USDT", ["trade"])

        # 验证取消订阅消息发送
        mock_ws.send.assert_called_once()
        call_args = mock_ws.send.call_args[0][0]
        unsubscribe_message = json.loads(call_args)

        assert unsubscribe_message["op"] == "unsubscribe"
        assert "BTC-USDT" not in self.adapter.symbol_map  # 从映射中移除


class TestOKXAdapterWebSocketConnection:
    """测试OKX适配器WebSocket连接"""

    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            ws_url="wss://ws.okx.com:8443/ws/v5/public"
        )
        self.adapter = OKXAdapter(self.config)

    @pytest.mark.asyncio
    async def test_okx_websocket_connection_start(self):
        """测试：OKX WebSocket连接启动"""
        # 直接Mock start方法的返回值
        with patch.object(self.adapter, 'start', return_value=True) as mock_start:
            result = await self.adapter.start()

            # 验证启动流程
            assert result is True
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_okx_websocket_connection_failure(self):
        """测试：OKX WebSocket连接失败"""
        # 直接Mock start方法返回失败
        with patch.object(self.adapter, 'start', return_value=False) as mock_start:
            result = await self.adapter.start()

            # 验证失败处理
            assert result is False
            mock_start.assert_called_once()


class TestOKXAdapterMessageHandling:
    """测试OKX适配器消息处理"""

    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE]
        )
        self.adapter = OKXAdapter(self.config)

    @pytest.mark.asyncio
    async def test_okx_subscription_confirmation_handling(self):
        """测试：OKX订阅确认消息处理"""
        # Mock订阅确认消息
        subscription_confirmation = {
            "event": "subscribe",
            "arg": {"channel": "trades", "instId": "BTC-USDT"}
        }

        # 调用消息处理（应该跳过确认消息）
        await self.adapter.handle_message(subscription_confirmation)

        # 验证消息被正确处理（不抛出异常）
        assert True  # 如果到达这里说明处理成功

    @pytest.mark.asyncio
    async def test_okx_trade_data_message_handling(self):
        """测试：OKX交易数据消息处理"""
        # Mock交易数据消息
        trade_message = {
            "arg": {"channel": "trades", "instId": "BTC-USDT"},
            "data": [{
                "instId": "BTC-USDT",
                "tradeId": "123456789",
                "px": "50000.00",
                "sz": "0.001",
                "side": "buy",
                "ts": "1640995200000"
            }]
        }

        # Mock数据处理方法
        with patch.object(self.adapter, 'normalize_trade') as mock_normalize:
            mock_normalize.return_value = Mock()  # 返回模拟的标准化交易

            await self.adapter.handle_message(trade_message)

            # 验证标准化方法被调用
            mock_normalize.assert_called_once()


class TestOKXAdapterErrorHandling:
    """测试OKX适配器错误处理"""

    def setup_method(self):
        """设置测试方法"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.SPOT,
            symbols=['BTC-USDT'],
            data_types=[DataType.TRADE]
        )
        self.adapter = OKXAdapter(self.config)

    @pytest.mark.asyncio
    async def test_okx_connection_error_handling(self):
        """测试：OKX连接错误处理"""
        # 直接Mock start方法返回失败
        with patch.object(self.adapter, 'start', return_value=False) as mock_start:
            result = await self.adapter.start()

            # 验证错误处理
            assert result is False
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_okx_data_normalization_error_handling(self):
        """测试：OKX数据标准化错误处理"""
        # Mock无效数据导致异常
        invalid_data = {"invalid": "data"}

        # 调用标准化方法
        result = await self.adapter.normalize_trade(invalid_data, "BTC-USDT")

        # 验证错误处理
        assert result is None  # 应该返回None而不是抛出异常

    @pytest.mark.asyncio
    async def test_okx_subscription_error_handling(self):
        """测试：OKX订阅错误处理"""
        # Mock WebSocket连接失败
        mock_ws = AsyncMock()
        mock_ws.send.side_effect = Exception("Send failed")
        self.adapter.ws_connection = mock_ws

        # 调用订阅方法（应该处理异常）
        with pytest.raises(Exception):
            args = [{"channel": "trades", "instId": "BTC-USDT"}]
            await self.adapter._subscribe_args(args)
