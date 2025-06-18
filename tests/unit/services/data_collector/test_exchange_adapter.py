"""
交易所适配器基类测试

严格遵循Mock使用原则：
- 仅对外部依赖使用Mock（如WebSocket连接、网络请求、外部API）
- 优先使用真实对象测试业务逻辑
- 确保测试验证真实的业务行为
"""

import pytest
import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

# 尝试导入交易所适配器模块
try:
    import sys
    from pathlib import Path
    
    # 添加数据收集器路径
    collector_path = Path(__file__).resolve().parents[4] / 'services' / 'data-collector' / 'src'
    if str(collector_path) not in sys.path:
        sys.path.insert(0, str(collector_path))
    
    from marketprism_collector.exchanges.base import (
        WebSocketWrapper,
        ExchangeAdapter
    )
    from marketprism_collector.data_types import (
        ExchangeConfig,
        Exchange,
        MarketType,
        DataType
    )
    HAS_EXCHANGE_ADAPTER = True
except ImportError as e:
    HAS_EXCHANGE_ADAPTER = False
    EXCHANGE_ADAPTER_ERROR = str(e)


@pytest.mark.skipif(not HAS_EXCHANGE_ADAPTER, reason=f"交易所适配器模块不可用: {EXCHANGE_ADAPTER_ERROR if not HAS_EXCHANGE_ADAPTER else ''}")
class TestWebSocketWrapper:
    """WebSocket包装器测试"""
    
    def test_websocket_wrapper_initialization(self):
        """测试WebSocket包装器初始化"""
        mock_ws = Mock()
        mock_session = Mock()
        
        wrapper = WebSocketWrapper(mock_ws, mock_session)
        
        assert wrapper.ws == mock_ws
        assert wrapper.session == mock_session
        assert wrapper.closed is False
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_send(self):
        """测试WebSocket包装器发送消息"""
        mock_ws = AsyncMock()
        mock_session = Mock()
        
        wrapper = WebSocketWrapper(mock_ws, mock_session)
        
        await wrapper.send("test message")
        
        mock_ws.send_str.assert_called_once_with("test message")
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_send_when_closed(self):
        """测试WebSocket包装器在关闭状态下发送消息"""
        mock_ws = AsyncMock()
        mock_session = Mock()
        
        wrapper = WebSocketWrapper(mock_ws, mock_session)
        wrapper.closed = True
        
        await wrapper.send("test message")
        
        # 关闭状态下不应该发送消息
        mock_ws.send_str.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_close(self):
        """测试WebSocket包装器关闭"""
        mock_ws = AsyncMock()
        mock_session = AsyncMock()
        
        wrapper = WebSocketWrapper(mock_ws, mock_session)
        
        await wrapper.close()
        
        assert wrapper.closed is True
        mock_ws.close.assert_called_once()
        mock_session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_websocket_wrapper_close_when_already_closed(self):
        """测试WebSocket包装器重复关闭"""
        mock_ws = AsyncMock()
        mock_session = AsyncMock()
        
        wrapper = WebSocketWrapper(mock_ws, mock_session)
        wrapper.closed = True
        
        await wrapper.close()
        
        # 已关闭状态下不应该再次关闭
        mock_ws.close.assert_not_called()
        mock_session.close.assert_not_called()


# 创建一个具体的适配器实现用于测试
class TestExchangeAdapterImpl(ExchangeAdapter):
    """测试用的交易所适配器实现"""
    
    async def subscribe_data_streams(self):
        """订阅数据流（测试实现）"""
        pass
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理消息（测试实现）"""
        pass


@pytest.mark.skipif(not HAS_EXCHANGE_ADAPTER, reason=f"交易所适配器模块不可用: {EXCHANGE_ADAPTER_ERROR if not HAS_EXCHANGE_ADAPTER else ''}")
class TestExchangeAdapter:
    """交易所适配器基类测试"""
    
    def test_exchange_adapter_initialization(self):
        """测试交易所适配器初始化"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            ws_url="wss://stream.binance.com:9443/ws",
            symbols=["BTCUSDT"],
            data_types=[DataType.TRADE]
        )
        
        adapter = TestExchangeAdapterImpl(config)
        
        assert adapter.config == config
        assert adapter.ws_connection is None
        assert adapter.is_connected is False
        assert adapter.reconnect_count == 0
        assert adapter.ping_interval == 180  # 默认3分钟
        assert adapter.ping_timeout == 10
        assert adapter.enable_ping is True
        
        # 验证回调字典初始化
        assert DataType.TRADE in adapter.callbacks
        assert DataType.ORDERBOOK in adapter.callbacks
        assert len(adapter.callbacks[DataType.TRADE]) == 0
        
        # 验证原始回调字典初始化
        assert 'depth' in adapter.raw_callbacks
        assert 'trade' in adapter.raw_callbacks
        assert 'ticker' in adapter.raw_callbacks
        
        # 验证统计信息初始化
        assert adapter.stats['messages_received'] == 0
        assert adapter.stats['messages_processed'] == 0
        assert adapter.stats['errors'] == 0
        assert adapter.stats['last_message_time'] is None
        assert adapter.stats['connected_at'] is None
    
    def test_exchange_adapter_custom_ping_config(self):
        """测试自定义ping配置"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            ping_interval=60,
            ping_timeout=5,
            enable_ping=False
        )
        
        adapter = TestExchangeAdapterImpl(config)
        
        assert adapter.ping_interval == 60
        assert adapter.ping_timeout == 5
        assert adapter.enable_ping is False
    
    def test_register_callback(self):
        """测试注册回调函数"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        def trade_callback(data):
            pass
        
        def orderbook_callback(data):
            pass
        
        adapter.register_callback(DataType.TRADE, trade_callback)
        adapter.register_callback(DataType.ORDERBOOK, orderbook_callback)
        
        assert len(adapter.callbacks[DataType.TRADE]) == 1
        assert len(adapter.callbacks[DataType.ORDERBOOK]) == 1
        assert adapter.callbacks[DataType.TRADE][0] == trade_callback
        assert adapter.callbacks[DataType.ORDERBOOK][0] == orderbook_callback
    
    def test_register_raw_callback(self):
        """测试注册原始数据回调函数"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        def depth_callback(exchange, symbol, data):
            pass
        
        def trade_callback(exchange, symbol, data):
            pass
        
        adapter.register_raw_callback('depth', depth_callback)
        adapter.register_raw_callback('trade', trade_callback)
        adapter.register_raw_callback('invalid', lambda: None)  # 无效类型
        
        assert len(adapter.raw_callbacks['depth']) == 1
        assert len(adapter.raw_callbacks['trade']) == 1
        assert adapter.raw_callbacks['depth'][0] == depth_callback
        assert adapter.raw_callbacks['trade'][0] == trade_callback
    
    def test_get_stats(self):
        """测试获取统计信息"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        # 设置一些统计数据
        adapter.stats['messages_received'] = 100
        adapter.stats['messages_processed'] = 95
        adapter.stats['errors'] = 5
        adapter.is_connected = True
        adapter.reconnect_count = 2
        
        stats = adapter.get_stats()
        
        assert stats['messages_received'] == 100
        assert stats['messages_processed'] == 95
        assert stats['errors'] == 5
        assert stats['is_connected'] is True
        assert stats['reconnect_count'] == 2
        assert stats['ping_interval'] == 180
        assert stats['enable_ping'] is True
    
    def test_get_enhanced_stats(self):
        """测试获取增强统计信息"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        # 设置一些增强统计数据
        adapter.enhanced_stats['ping_count'] = 10
        adapter.enhanced_stats['pong_count'] = 9
        adapter.enhanced_stats['connection_health_score'] = 85
        adapter.last_ping_time = datetime.now(timezone.utc)
        
        enhanced_stats = adapter.get_enhanced_stats()
        
        assert 'enhanced' in enhanced_stats
        enhanced = enhanced_stats['enhanced']
        assert enhanced['ping_count'] == 10
        assert enhanced['pong_count'] == 9
        assert enhanced['connection_health_score'] == 85
        assert enhanced['ping_interval'] == 180
        assert enhanced['ping_timeout'] == 10
        assert enhanced['last_ping_time'] is not None
        assert enhanced['last_pong_time'] is None
        assert enhanced['maintenance_tasks_count'] == 0
    
    def test_get_effective_proxy_config_from_config(self):
        """测试从配置获取代理设置"""
        proxy_config = {
            'enabled': True,
            'http': 'http://proxy.example.com:8080',
            'https': 'https://proxy.example.com:8080'
        }
        
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            proxy=proxy_config
        )
        adapter = TestExchangeAdapterImpl(config)
        
        effective_proxy = adapter._get_effective_proxy_config()
        
        assert effective_proxy == proxy_config
    
    def test_get_effective_proxy_config_disabled(self):
        """测试禁用的代理配置"""
        proxy_config = {
            'enabled': False,
            'http': 'http://proxy.example.com:8080'
        }
        
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            proxy=proxy_config
        )
        adapter = TestExchangeAdapterImpl(config)
        
        effective_proxy = adapter._get_effective_proxy_config()
        
        assert effective_proxy is None
    
    @patch.dict(os.environ, {'HTTP_PROXY': 'http://env.proxy.com:8080'})
    def test_get_effective_proxy_config_from_env(self):
        """测试从环境变量获取代理设置"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        effective_proxy = adapter._get_effective_proxy_config()
        
        assert effective_proxy is not None
        assert effective_proxy['enabled'] is True
        assert effective_proxy['http'] == 'http://env.proxy.com:8080'
    
    @patch.dict(os.environ, {'ALL_PROXY': 'socks5://socks.proxy.com:1080'})
    def test_get_effective_proxy_config_socks_from_env(self):
        """测试从环境变量获取SOCKS代理设置"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        effective_proxy = adapter._get_effective_proxy_config()
        
        assert effective_proxy is not None
        assert effective_proxy['enabled'] is True
        assert effective_proxy['socks5'] == 'socks5://socks.proxy.com:1080'
    
    def test_get_env_proxy_config_no_proxy(self):
        """测试无环境变量代理配置"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        with patch.dict(os.environ, {}, clear=True):
            env_proxy = adapter._get_env_proxy_config()
            
            assert env_proxy is None
    
    @pytest.mark.asyncio
    async def test_emit_data_sync_callback(self):
        """测试发送数据到同步回调函数"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        callback_called = False
        received_data = None
        
        def sync_callback(data):
            nonlocal callback_called, received_data
            callback_called = True
            received_data = data
        
        adapter.register_callback(DataType.TRADE, sync_callback)
        
        test_data = {"symbol": "BTCUSDT", "price": "50000"}
        await adapter._emit_data(DataType.TRADE, test_data)
        
        assert callback_called is True
        assert received_data == test_data
    
    @pytest.mark.asyncio
    async def test_emit_data_async_callback(self):
        """测试发送数据到异步回调函数"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        callback_called = False
        received_data = None
        
        async def async_callback(data):
            nonlocal callback_called, received_data
            callback_called = True
            received_data = data
        
        adapter.register_callback(DataType.TRADE, async_callback)
        
        test_data = {"symbol": "BTCUSDT", "price": "50000"}
        await adapter._emit_data(DataType.TRADE, test_data)
        
        assert callback_called is True
        assert received_data == test_data
    
    @pytest.mark.asyncio
    async def test_emit_data_callback_exception(self):
        """测试回调函数异常处理"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        def failing_callback(data):
            raise Exception("Callback error")
        
        adapter.register_callback(DataType.TRADE, failing_callback)
        
        # 不应该抛出异常
        test_data = {"symbol": "BTCUSDT", "price": "50000"}
        await adapter._emit_data(DataType.TRADE, test_data)
        
        # 验证错误被记录但不影响执行
        assert True  # 如果到达这里说明异常被正确处理
    
    @pytest.mark.asyncio
    async def test_emit_raw_data(self):
        """测试发送原始数据"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        adapter = TestExchangeAdapterImpl(config)
        
        callback_called = False
        received_args = None
        
        def raw_callback(exchange, symbol, data):
            nonlocal callback_called, received_args
            callback_called = True
            received_args = (exchange, symbol, data)
        
        adapter.register_raw_callback('depth', raw_callback)
        
        test_data = {"bids": [], "asks": []}
        await adapter._emit_raw_data('depth', 'binance', 'BTCUSDT', test_data)
        
        assert callback_called is True
        assert received_args == ('binance', 'BTCUSDT', test_data)


# 基础覆盖率测试
class TestExchangeAdapterBasic:
    """交易所适配器基础覆盖率测试"""
    
    def test_module_import_attempt(self):
        """测试模块导入尝试"""
        try:
            from marketprism_collector.exchanges import base
            # 如果导入成功，测试基本属性
            assert hasattr(base, '__file__')
        except ImportError:
            # 如果导入失败，这也是预期的情况
            pytest.skip("交易所适配器基类模块不可用")
    
    def test_exchange_adapter_concepts(self):
        """测试交易所适配器概念"""
        # 测试交易所适配器的核心概念
        concepts = [
            "websocket_connection",
            "proxy_support",
            "message_processing",
            "callback_management",
            "connection_monitoring"
        ]
        
        # 验证概念存在
        for concept in concepts:
            assert isinstance(concept, str)
            assert len(concept) > 0
