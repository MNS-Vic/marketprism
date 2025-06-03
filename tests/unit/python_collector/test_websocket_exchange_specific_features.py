"""
测试WebSocket集成的交易所特定特性

验证不同交易所的特殊要求是否被正确处理：
- Binance: ping/pong维持连接、WebSocket API支持、速率限制
- OKX: 认证流程、会话管理、私有频道
- 通用: 动态订阅、错误恢复、性能监控
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from marketprism_collector.exchanges.enhanced_binance import EnhancedBinanceAdapter
from marketprism_collector.exchanges.enhanced_okx import EnhancedOKXAdapter
from marketprism_collector.exchanges.intelligent_factory import IntelligentAdapterFactory, AdapterCapability
from marketprism_collector.exchanges.factory import ExchangeFactory
from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType


class TestBinanceSpecificFeatures:
    """测试Binance特定的WebSocket特性"""
    
    def setup_method(self):
        """设置测试环境"""
        self.config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.FUTURES,
            symbols=['BTC-USDT', 'ETH-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            ws_url='wss://stream.binance.com:9443/ws',
            enable_dynamic_subscription=True,
            force_enhanced_adapter=True
        )
    
    @pytest.mark.asyncio
    async def test_binance_ping_pong_mechanism(self):
        """测试Binance ping/pong连接维持机制"""
        adapter = EnhancedBinanceAdapter(self.config)
        
        # Mock WebSocket连接
        adapter.ws_connection = AsyncMock()
        adapter.is_connected = True
        adapter.session_active = True
        
        # 模拟ping循环
        ping_sent = False
        
        async def mock_send(message):
            nonlocal ping_sent
            import json
            data = json.loads(message)
            if data.get('method') == 'ping':
                ping_sent = True
        
        adapter.ws_connection.send.side_effect = mock_send
        
        # 启动ping任务并快速停止
        ping_task = asyncio.create_task(adapter._ping_loop())
        await asyncio.sleep(0.1)  # 让ping循环运行一小段时间
        ping_task.cancel()
        
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
        
        # 验证ping机制配置
        assert adapter.ping_interval == 300  # 5分钟
        assert adapter.ping_timeout == 10
        assert hasattr(adapter, 'last_ping_time')
        assert hasattr(adapter, 'last_pong_time')
    
    @pytest.mark.asyncio
    async def test_binance_rate_limit_handling(self):
        """测试Binance速率限制处理"""
        adapter = EnhancedBinanceAdapter(self.config)
        
        # 模拟速率限制消息
        rate_limit_message = {
            "error": {
                "code": -1003,
                "msg": "Rate limit exceeded"
            }
        }
        
        # Mock实施退避策略
        backoff_called = False
        original_backoff = adapter._implement_backoff_strategy
        
        async def mock_backoff():
            nonlocal backoff_called
            backoff_called = True
        
        adapter._implement_backoff_strategy = mock_backoff
        
        # 处理速率限制消息
        await adapter._handle_rate_limit_message(rate_limit_message)
        
        # 验证退避策略被调用
        assert backoff_called
        assert adapter.max_request_weight == 1200
        assert hasattr(adapter, 'consecutive_failures')
    
    @pytest.mark.asyncio
    async def test_binance_dynamic_subscription(self):
        """测试Binance动态订阅功能"""
        adapter = EnhancedBinanceAdapter(self.config)
        adapter.ws_connection = AsyncMock()
        
        # 测试动态添加订阅
        symbol = "DOT-USDT"
        data_types = ["trade", "orderbook"]
        
        sent_messages = []
        
        async def capture_send(message):
            import json
            sent_messages.append(json.loads(message))
        
        adapter.ws_connection.send.side_effect = capture_send
        
        await adapter.add_symbol_subscription(symbol, data_types)
        
        # 验证发送的订阅消息
        assert len(sent_messages) == 1
        subscribe_msg = sent_messages[0]
        assert subscribe_msg['method'] == 'SUBSCRIBE'
        assert 'dotusdt@trade' in subscribe_msg['params']
        assert 'dotusdt@depth@100ms' in subscribe_msg['params']
        
        # 测试动态移除订阅
        sent_messages.clear()
        await adapter.remove_symbol_subscription(symbol, data_types)
        
        # 验证发送的取消订阅消息
        assert len(sent_messages) == 1
        unsubscribe_msg = sent_messages[0]
        assert unsubscribe_msg['method'] == 'UNSUBSCRIBE'
    
    def test_binance_enhanced_stats(self):
        """测试Binance增强统计信息"""
        adapter = EnhancedBinanceAdapter(self.config)
        
        # 设置一些测试数据
        adapter.message_stats['pings_sent'] = 10
        adapter.message_stats['pongs_received'] = 9
        adapter.session_active = True
        adapter.consecutive_failures = 2
        
        stats = adapter.get_enhanced_stats()
        
        # 验证增强统计结构
        assert 'binance_specific' in stats
        binance_stats = stats['binance_specific']
        
        assert 'ping_pong' in binance_stats
        assert binance_stats['ping_pong']['pings_sent'] == 10
        assert binance_stats['ping_pong']['pongs_received'] == 9
        
        assert 'session' in binance_stats
        assert binance_stats['session']['session_active'] == True
        
        assert 'connection' in binance_stats
        assert binance_stats['connection']['consecutive_failures'] == 2


class TestOKXSpecificFeatures:
    """测试OKX特定的WebSocket特性"""
    
    def setup_method(self):
        """设置测试环境"""
        self.config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.FUTURES,
            symbols=['BTC-USDT', 'ETH-USDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            ws_url='wss://ws.okx.com:8443/ws/v5/public',
            api_key='test_key',
            api_secret='test_secret',
            passphrase='test_passphrase',
            enable_dynamic_subscription=True
        )
    
    @pytest.mark.asyncio
    async def test_okx_authentication_flow(self):
        """测试OKX认证流程"""
        adapter = EnhancedOKXAdapter(self.config)
        adapter.ws_connection = AsyncMock()
        
        # 捕获发送的消息
        sent_messages = []
        
        async def capture_send(message):
            import json
            sent_messages.append(json.loads(message))
        
        adapter.ws_connection.send.side_effect = capture_send
        
        # 执行登录
        await adapter._perform_login()
        
        # 验证登录消息
        assert len(sent_messages) == 1
        login_msg = sent_messages[0]
        assert login_msg['op'] == 'login'
        assert 'args' in login_msg
        
        login_args = login_msg['args'][0]
        assert 'apiKey' in login_args
        assert 'passphrase' in login_args
        assert 'timestamp' in login_args
        assert 'sign' in login_args
        
        # 验证登录统计
        assert adapter.okx_stats['login_attempts'] == 1
    
    @pytest.mark.asyncio
    async def test_okx_ping_pong_string_format(self):
        """测试OKX字符串格式的ping/pong"""
        adapter = EnhancedOKXAdapter(self.config)
        adapter.ws_connection = AsyncMock()
        adapter.is_connected = True
        
        # 模拟ping循环
        ping_sent = False
        
        async def mock_send(message):
            nonlocal ping_sent
            if message == "ping":
                ping_sent = True
        
        adapter.ws_connection.send.side_effect = mock_send
        
        # 启动ping任务并快速停止
        ping_task = asyncio.create_task(adapter._okx_ping_loop())
        await asyncio.sleep(0.1)
        ping_task.cancel()
        
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
        
        # 验证OKX特定的ping配置
        assert adapter.ping_interval == 30  # 30秒
        assert adapter.okx_reconnect_delay == 1  # 1秒重连延迟
    
    @pytest.mark.asyncio
    async def test_okx_login_response_handling(self):
        """测试OKX登录响应处理"""
        adapter = EnhancedOKXAdapter(self.config)
        
        # 测试成功登录响应
        success_response = {
            "event": "login",
            "code": "0",
            "msg": "Login successful"
        }
        
        await adapter._handle_login_response(success_response)
        assert adapter.is_authenticated == True
        assert adapter.okx_stats['successful_logins'] == 1
        
        # 测试失败登录响应
        adapter.is_authenticated = False
        adapter.okx_stats['successful_logins'] = 0
        
        failure_response = {
            "event": "login",
            "code": "50001",
            "msg": "Invalid API key"
        }
        
        await adapter._handle_login_response(failure_response)
        assert adapter.is_authenticated == False
        assert adapter.okx_stats['successful_logins'] == 0
    
    @pytest.mark.asyncio
    async def test_okx_dynamic_subscription(self):
        """测试OKX动态订阅功能"""
        adapter = EnhancedOKXAdapter(self.config)
        adapter.ws_connection = AsyncMock()
        
        # 测试动态添加订阅
        symbol = "DOT-USDT"
        data_types = ["trade", "orderbook"]
        
        sent_messages = []
        
        async def capture_send(message):
            import json
            sent_messages.append(json.loads(message))
        
        adapter.ws_connection.send.side_effect = capture_send
        
        await adapter.add_symbol_subscription(symbol, data_types)
        
        # 验证OKX格式的订阅消息
        assert len(sent_messages) == 1
        subscribe_msg = sent_messages[0]
        assert subscribe_msg['op'] == 'subscribe'
        assert 'args' in subscribe_msg
        
        # 检查频道格式
        channels = subscribe_msg['args']
        assert any(ch['channel'] == 'trades' and ch['instId'] == 'DOT-USDT' for ch in channels)
        assert any(ch['channel'] == 'books' and ch['instId'] == 'DOT-USDT' for ch in channels)


class TestIntelligentAdapterFactory:
    """测试智能适配器工厂"""
    
    def setup_method(self):
        """设置测试环境"""
        self.factory = IntelligentAdapterFactory()
    
    def test_binance_requirements_analysis(self):
        """测试Binance要求分析"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.FUTURES,
            enable_dynamic_subscription=True,
            force_enhanced_adapter=True
        )
        
        required_capabilities = self.factory._analyze_config_requirements(config)
        
        # 验证基本能力
        assert AdapterCapability.BASIC_CONNECTION in required_capabilities
        assert AdapterCapability.DYNAMIC_SUBSCRIPTION in required_capabilities
        
        # 检查是否需要增强适配器
        needs_enhanced = self.factory._needs_enhanced_adapter(
            Exchange.BINANCE, required_capabilities, config
        )
        assert needs_enhanced == True
    
    def test_okx_requirements_analysis(self):
        """测试OKX要求分析"""
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.FUTURES,
            api_key='test_key',
            api_secret='test_secret',
            passphrase='test_passphrase'
        )
        
        required_capabilities = self.factory._analyze_config_requirements(config)
        
        # 验证认证相关能力
        assert AdapterCapability.AUTHENTICATION in required_capabilities
        assert AdapterCapability.USER_DATA_STREAM in required_capabilities
        
        # 检查是否需要增强适配器
        needs_enhanced = self.factory._needs_enhanced_adapter(
            Exchange.OKX, required_capabilities, config
        )
        assert needs_enhanced == True
    
    def test_adapter_capabilities_detection(self):
        """测试适配器能力检测"""
        # 测试Binance增强适配器能力
        binance_caps = self.factory.get_adapter_capabilities(Exchange.BINANCE, enhanced=True)
        
        assert binance_caps[AdapterCapability.BASIC_CONNECTION] == True
        assert binance_caps[AdapterCapability.PING_PONG_MAINTENANCE] == True
        assert binance_caps[AdapterCapability.DYNAMIC_SUBSCRIPTION] == True
        
        # 测试OKX增强适配器能力
        okx_caps = self.factory.get_adapter_capabilities(Exchange.OKX, enhanced=True)
        
        assert okx_caps[AdapterCapability.BASIC_CONNECTION] == True
        assert okx_caps[AdapterCapability.AUTHENTICATION] == True
        assert okx_caps[AdapterCapability.SESSION_MANAGEMENT] == True
    
    def test_exchange_recommendations(self):
        """测试交易所特定建议"""
        # 测试Binance建议
        binance_rec = self.factory.get_exchange_recommendations(Exchange.BINANCE)
        
        assert binance_rec['exchange'] == 'binance'
        assert 'suggested_config' in binance_rec
        assert binance_rec['suggested_config']['ping_interval'] == 300
        assert 'performance_tips' in binance_rec
        assert 'best_practices' in binance_rec
        
        # 测试OKX建议
        okx_rec = self.factory.get_exchange_recommendations(Exchange.OKX)
        
        assert okx_rec['exchange'] == 'okx'
        assert 'suggested_config' in okx_rec
        assert okx_rec['suggested_config']['ping_interval'] == 30
        assert okx_rec['suggested_config']['reconnect_delay'] == 1
    
    def test_requirements_validation(self):
        """测试要求验证"""
        # 测试满足要求的配置
        valid_config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.FUTURES,
            enable_dynamic_subscription=True
        )
        
        validation = self.factory.validate_adapter_requirements(Exchange.BINANCE, valid_config)
        
        assert validation['valid'] == True
        assert isinstance(validation['missing_capabilities'], list)
        assert isinstance(validation['warnings'], list)
        assert isinstance(validation['recommendations'], list)


class TestExchangeFactoryIntegration:
    """测试集成了智能工厂的ExchangeFactory"""
    
    def setup_method(self):
        """设置测试环境"""
        self.factory = ExchangeFactory()
    
    @pytest.mark.asyncio
    async def test_intelligent_adapter_selection(self):
        """测试智能适配器选择"""
        # 测试Binance智能选择
        config = {
            'exchange': 'binance',
            'enable_dynamic_subscription': True,
            'force_enhanced_adapter': True
        }
        
        with patch.object(self.factory.intelligent_factory, 'create_adapter') as mock_create:
            mock_adapter = Mock()
            mock_create.return_value = mock_adapter
            
            adapter = self.factory.create_adapter('binance', config, use_intelligent_selection=True)
            
            # 验证智能工厂被调用
            assert mock_create.called
            assert adapter == mock_adapter
    
    def test_enhanced_adapter_creation(self):
        """测试强制创建增强适配器"""
        config = {
            'exchange': 'binance',
            'symbols': ['BTC-USDT'],
            'data_types': ['trade']
        }
        
        adapter = self.factory.create_enhanced_adapter('binance', config)
        
        # 验证创建了增强适配器
        assert adapter is not None
        assert isinstance(adapter, EnhancedBinanceAdapter)
    
    def test_adapter_requirements_validation(self):
        """测试适配器要求验证"""
        config = {
            'exchange': 'binance',
            'enable_dynamic_subscription': True
        }
        
        validation = self.factory.validate_adapter_requirements('binance', config)
        
        assert 'valid' in validation
        assert 'missing_capabilities' in validation
        assert 'warnings' in validation
        assert 'recommendations' in validation
    
    def test_exchange_recommendations_retrieval(self):
        """测试获取交易所建议"""
        recommendations = self.factory.get_exchange_recommendations('binance')
        
        assert 'exchange' in recommendations
        assert recommendations['exchange'] == 'binance'
        assert 'suggested_config' in recommendations
        assert 'performance_tips' in recommendations
    
    def test_adapter_capabilities_retrieval(self):
        """测试获取适配器能力"""
        # 测试标准适配器能力
        standard_caps = self.factory.get_adapter_capabilities('binance', enhanced=False)
        assert isinstance(standard_caps, dict)
        assert 'basic_connection' in standard_caps
        
        # 测试增强适配器能力
        enhanced_caps = self.factory.get_adapter_capabilities('binance', enhanced=True)
        assert isinstance(enhanced_caps, dict)
        assert 'basic_connection' in enhanced_caps
        assert 'ping_pong_maintenance' in enhanced_caps


class TestWebSocketFeatureIntegration:
    """测试WebSocket特性集成"""
    
    @pytest.mark.asyncio
    async def test_feature_comparison_across_exchanges(self):
        """测试不同交易所特性对比"""
        factory = IntelligentAdapterFactory()
        
        # 获取Binance和OKX的能力对比
        binance_caps = factory.get_adapter_capabilities(Exchange.BINANCE, enhanced=True)
        okx_caps = factory.get_adapter_capabilities(Exchange.OKX, enhanced=True)
        
        # 验证共同特性
        common_features = set(binance_caps.keys()) & set(okx_caps.keys())
        assert AdapterCapability.BASIC_CONNECTION in common_features
        assert AdapterCapability.DYNAMIC_SUBSCRIPTION in common_features
        
        # 验证不同特性
        assert binance_caps.get(AdapterCapability.PING_PONG_MAINTENANCE, False)
        assert okx_caps.get(AdapterCapability.AUTHENTICATION, False)
    
    def test_websocket_specific_configuration_recommendations(self):
        """测试WebSocket特定配置建议"""
        factory = IntelligentAdapterFactory()
        
        # 获取WebSocket相关的配置建议
        binance_rec = factory.get_exchange_recommendations(Exchange.BINANCE)
        okx_rec = factory.get_exchange_recommendations(Exchange.OKX)
        
        # 验证Binance WebSocket建议
        assert binance_rec['suggested_config']['ping_interval'] == 300
        assert "ping维持连接" in str(binance_rec['best_practices'])
        
        # 验证OKX WebSocket建议
        assert okx_rec['suggested_config']['ping_interval'] == 30
        assert "认证" in str(okx_rec['performance_tips'])
    
    @pytest.mark.asyncio
    async def test_error_recovery_mechanisms(self):
        """测试错误恢复机制"""
        # 测试Binance错误恢复
        binance_config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.FUTURES,
            force_enhanced_adapter=True
        )
        
        binance_adapter = EnhancedBinanceAdapter(binance_config)
        
        # 验证重连机制配置
        assert binance_adapter.binance_reconnect_delay == 5
        assert binance_adapter.max_consecutive_failures == 5
        
        # 测试OKX错误恢复
        okx_config = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.FUTURES,
            api_key='test', api_secret='test', passphrase='test'
        )
        
        okx_adapter = EnhancedOKXAdapter(okx_config)
        
        # 验证重连机制配置
        assert okx_adapter.okx_reconnect_delay == 1
        assert okx_adapter.max_reconnect_attempts == 10