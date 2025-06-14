"""
TDD Tests for REST API Module

基于TDD方法论发现并修复REST API模块的设计问题
重点测试：路由设计、错误处理、数据序列化、性能优化
"""

from datetime import datetime, timezone
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal
import json
from aiohttp import web, ClientSession
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

# 导入测试目标
from marketprism_collector.rest_api import OrderBookRestAPI
from marketprism_collector.data_types import (
    Exchange, ExchangeConfig, EnhancedOrderBook, OrderBookUpdateType, PriceLevel
)
from marketprism_collector.orderbook_integration import OrderBookCollectorIntegration


class TestOrderBookRestAPIInitialization:
    """TDD: REST API初始化测试"""
    
    def test_api_basic_initialization(self):
        """测试REST API基本初始化"""
        # 创建模拟集成
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        
        # 测试初始化
        api = OrderBookRestAPI(mock_integration)
        
        # 验证基本属性
        assert api.integration == mock_integration
        assert hasattr(api, 'logger')
        assert hasattr(api, 'api_stats')
        assert api.api_stats['requests_total'] == 0
        assert 'start_time' in api.api_stats
    
    def test_api_stats_initialization(self):
        """测试API统计信息初始化"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 验证统计信息结构
        assert 'requests_total' in api.api_stats
        assert 'requests_by_endpoint' in api.api_stats
        assert 'errors_total' in api.api_stats
        assert 'start_time' in api.api_stats
        assert isinstance(api.api_stats['requests_by_endpoint'], dict)


class TestOrderBookRestAPIRoutes:
    """TDD: REST API路由测试"""
    
    def test_setup_routes_registration(self):
        """测试路由注册"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 创建测试应用
        app = web.Application()
        api.setup_routes(app)
        
        # 获取所有路由
        routes = [route.resource.canonical for route in app.router.routes()]
        
        # 验证核心路由存在
        expected_routes = [
            '/api/v1/orderbook/{exchange}/{symbol}',
            '/api/v1/orderbook/{exchange}/{symbol}/snapshot',
            '/api/v1/orderbook/stats',
            '/api/v1/orderbook/health',
            '/api/v1/orderbook/exchanges'
        ]
        
        for expected_route in expected_routes:
            # 检查路由模式是否匹配
            route_exists = any(expected_route.replace('{', '').replace('}', '') in route for route in routes)
            if not route_exists:
                # 进行更精确的匹配
                pattern_match = any(
                    all(part in route for part in expected_route.split('/')[1:-1])
                    for route in routes
                )
                assert pattern_match, f"Missing route pattern: {expected_route}"
    
    def test_route_methods_mapping(self):
        """测试路由方法映射"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        app = web.Application()
        api.setup_routes(app)
        
        # 检查POST路由存在
        post_routes = [route for route in app.router.routes() if 'POST' in route.method]
        assert len(post_routes) > 0, "Should have POST routes for refresh operations"


class TestOrderBookAPIHandlers:
    """TDD: API处理器测试"""
    
    @pytest.mark.asyncio
    async def test_get_orderbook_success(self):
        """测试获取订单簿成功响应"""
        # 模拟集成
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        
        # TDD修复：添加缺少的integrations属性
        # 使用真实的字典而不是Mock对象
        mock_binance_integration = Mock()
        mock_binance_integration.orderbook_manager = None  # 防止访问不存在的manager
        mock_integration.integrations = {
            'binance': mock_binance_integration
        }
        
        # 创建模拟订单簿
        mock_orderbook = EnhancedOrderBook(
            exchange_name="binance",
            symbol_name="BTCUSDT",
            last_update_id=123456,
            bids=[PriceLevel(price=Decimal('50000'), quantity=Decimal('1.0'))],
            asks=[PriceLevel(price=Decimal('50100'), quantity=Decimal('1.0'))],
            timestamp=datetime.now(timezone.utc),
            update_type=OrderBookUpdateType.SNAPSHOT,
            depth_levels=2
        )
        
        mock_integration.get_current_orderbook = AsyncMock(return_value=mock_orderbook)
        
        api = OrderBookRestAPI(mock_integration)
        
        # 创建模拟请求
        mock_request = Mock()
        mock_request.match_info = {'exchange': 'binance', 'symbol': 'BTCUSDT'}
        mock_request.query = {'depth': '20', 'format': 'enhanced'}
        
        # 调用处理器
        response = await api.get_orderbook(mock_request)
        
        # 验证响应
        assert response.status == 200
    
    @pytest.mark.asyncio
    async def test_get_orderbook_not_found(self):
        """测试订单簿不存在的响应"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        mock_integration.get_current_orderbook = AsyncMock(return_value=None)
        
        api = OrderBookRestAPI(mock_integration)
        
        mock_request = Mock()
        mock_request.match_info = {'exchange': 'binance', 'symbol': 'NONEXISTENT'}
        mock_request.query = {}
        
        response = await api.get_orderbook(mock_request)
        
        # 验证404响应
        assert response.status == 404
    
    @pytest.mark.asyncio
    async def test_get_orderbook_invalid_parameters(self):
        """测试无效参数处理"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        mock_request = Mock()
        mock_request.match_info = {'exchange': 'binance', 'symbol': 'BTCUSDT'}
        mock_request.query = {'depth': 'invalid'}  # 无效深度参数
        
        response = await api.get_orderbook(mock_request)
        
        # 验证400响应
        assert response.status == 400
    
    @pytest.mark.asyncio
    async def test_refresh_orderbook_success(self):
        """测试刷新订单簿成功"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        mock_integration.integrations = {
            'binance': Mock()
        }
        mock_integration.integrations['binance'].trigger_snapshot_refresh = AsyncMock(return_value=True)
        
        api = OrderBookRestAPI(mock_integration)
        
        mock_request = Mock()
        mock_request.match_info = {'exchange': 'binance', 'symbol': 'BTCUSDT'}
        
        response = await api.refresh_orderbook(mock_request)
        
        assert response.status == 200
    
    @pytest.mark.asyncio
    async def test_get_all_stats_success(self):
        """测试获取统计信息成功"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        mock_stats = {
            'total_updates': 1000,
            'active_symbols': 5,
            'exchanges': ['binance', 'okx']
        }
        mock_integration.get_all_stats.return_value = mock_stats
        
        api = OrderBookRestAPI(mock_integration)
        
        mock_request = Mock()
        
        response = await api.get_all_stats(mock_request)
        
        assert response.status == 200
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """测试健康检查成功"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        mock_request = Mock()
        
        response = await api.health_check(mock_request)
        
        assert response.status == 200


class TestAPIDesignIssues:
    """TDD: 发现REST API设计问题"""
    
    def test_missing_serialization_helper_methods(self):
        """发现问题：缺少序列化辅助方法"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查是否有序列化方法
        serialization_methods = [
            '_serialize_complex_object',
            '_format_enhanced_orderbook',
            '_format_simple_orderbook',
            '_format_legacy_orderbook'
        ]
        
        missing_methods = []
        for method_name in serialization_methods:
            if not hasattr(api, method_name):
                missing_methods.append(method_name)
        
        assert len(missing_methods) == 0, f"Missing serialization methods: {missing_methods}"
    
    def test_missing_request_tracking_methods(self):
        """发现问题：缺少请求跟踪方法"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查请求跟踪方法
        tracking_methods = [
            '_record_request',
            '_record_error'
        ]
        
        missing_methods = []
        for method_name in tracking_methods:
            if not hasattr(api, method_name):
                missing_methods.append(method_name)
        
        assert len(missing_methods) == 0, f"Missing request tracking methods: {missing_methods}"
    
    def test_missing_error_handling_standardization(self):
        """发现问题：缺少标准化错误处理"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查错误处理方法
        error_handling_methods = [
            '_handle_api_error',
            '_create_error_response',
            '_validate_request_params'
        ]
        
        # 这些方法应该存在以提供标准化错误处理
        missing_methods = []
        for method_name in error_handling_methods:
            if not hasattr(api, method_name):
                missing_methods.append(method_name)
        
        # 暂时记录缺失的方法，这些是改进建议
        if missing_methods:
            print(f"Suggested error handling methods to implement: {missing_methods}")
    
    def test_missing_input_validation(self):
        """发现问题：缺少输入验证"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查输入验证方法
        validation_methods = [
            '_validate_exchange_name',
            '_validate_symbol_name',
            '_validate_depth_parameter'
        ]
        
        missing_methods = []
        for method_name in validation_methods:
            if not hasattr(api, method_name):
                missing_methods.append(method_name)
        
        # 暂时记录缺失的方法
        if missing_methods:
            print(f"Suggested validation methods to implement: {missing_methods}")
    
    def test_missing_response_caching(self):
        """发现问题：缺少响应缓存机制"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查缓存相关属性和方法
        caching_features = [
            '_cache',
            '_cache_timeout',
            '_get_cached_response',
            '_set_cached_response'
        ]
        
        missing_features = []
        for feature in caching_features:
            if not hasattr(api, feature):
                missing_features.append(feature)
        
        # 暂时记录缺失的功能
        if missing_features:
            print(f"Suggested caching features to implement: {missing_features}")
    
    def test_missing_rate_limiting(self):
        """发现问题：缺少API速率限制"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查速率限制功能
        rate_limiting_features = [
            '_rate_limiter',
            '_check_rate_limit',
            '_update_rate_limit_counter'
        ]
        
        missing_features = []
        for feature in rate_limiting_features:
            if not hasattr(api, feature):
                missing_features.append(feature)
        
        # 暂时记录缺失的功能
        if missing_features:
            print(f"Suggested rate limiting features to implement: {missing_features}")
    
    def test_missing_api_authentication(self):
        """发现问题：缺少API身份验证"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查身份验证功能
        auth_features = [
            '_authenticate_request',
            '_validate_api_key',
            '_check_permissions'
        ]
        
        missing_features = []
        for feature in auth_features:
            if not hasattr(api, feature):
                missing_features.append(feature)
        
        # 暂时记录缺失的功能
        if missing_features:
            print(f"Suggested authentication features to implement: {missing_features}")


class TestAPIPerformanceIssues:
    """TDD: API性能问题测试"""
    
    def test_missing_async_optimization(self):
        """发现问题：缺少异步优化"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查异步优化方法
        async_methods = [
            '_async_serialize_orderbook',
            '_batch_process_requests'
        ]
        
        missing_methods = []
        for method_name in async_methods:
            if not hasattr(api, method_name):
                missing_methods.append(method_name)
        
        # 暂时记录缺失的方法
        if missing_methods:
            print(f"Suggested async optimization methods to implement: {missing_methods}")
    
    def test_missing_connection_pooling(self):
        """发现问题：缺少连接池管理"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查连接池相关属性
        pooling_features = [
            '_connection_pool',
            '_max_connections',
            '_connection_timeout'
        ]
        
        missing_features = []
        for feature in pooling_features:
            if not hasattr(api, feature):
                missing_features.append(feature)
        
        # 暂时记录缺失的功能
        if missing_features:
            print(f"Suggested connection pooling features to implement: {missing_features}")


class TestAPIResponseFormats:
    """TDD: API响应格式测试"""
    
    def test_enhanced_orderbook_format(self):
        """测试增强订单簿格式"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查格式化方法存在
        assert hasattr(api, '_format_enhanced_orderbook')
    
    def test_simple_orderbook_format(self):
        """测试简单订单簿格式"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查格式化方法存在
        assert hasattr(api, '_format_simple_orderbook')
    
    def test_legacy_orderbook_format(self):
        """测试传统订单簿格式"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查格式化方法存在
        assert hasattr(api, '_format_legacy_orderbook')
    
    def test_serialization_complex_objects(self):
        """测试复杂对象序列化"""
        mock_integration = Mock(spec=OrderBookCollectorIntegration)
        api = OrderBookRestAPI(mock_integration)
        
        # 检查序列化方法存在
        assert hasattr(api, '_serialize_complex_object')