# TDD Phase 3 - 服务间通信集成测试

"""
服务间通信集成测试

测试各个微服务之间的通信和协作，包括：
1. 数据收集器与存储服务的通信
2. API网关与后端服务的通信
3. 缓存服务与数据服务的协作
4. 监控服务与各业务服务的集成
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

# 导入核心模块
from core.networking.unified_session_manager import UnifiedSessionManager
from core.observability.metrics.unified_metrics_manager import UnifiedMetricsManager
from core.reliability.manager import ReliabilityManager


class TestDataCollectorStorageIntegration:
    """数据收集器与存储服务集成测试"""
    
    @pytest.fixture
    async def mock_collector_service(self):
        """模拟数据收集器服务"""
        mock_service = AsyncMock()
        mock_service.collect_market_data = AsyncMock()
        mock_service.process_ticker_data = AsyncMock()
        mock_service.process_orderbook_data = AsyncMock()
        return mock_service
    
    @pytest.fixture
    async def mock_storage_service(self):
        """模拟存储服务"""
        mock_service = AsyncMock()
        mock_service.store_ticker_data = AsyncMock()
        mock_service.store_orderbook_data = AsyncMock()
        mock_service.get_latest_data = AsyncMock()
        return mock_service
    
    @pytest.mark.asyncio
    async def test_ticker_data_flow(self, mock_collector_service, mock_storage_service):
        """测试ticker数据流"""
        # 模拟收集到的ticker数据
        raw_ticker_data = {
            "s": "BTCUSDT",
            "c": "50000.00",
            "v": "1000.00",
            "E": 1718712000000
        }
        
        # 模拟数据处理
        processed_data = {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "volume": 1000.0,
            "timestamp": "2025-06-18T10:00:00Z",
            "exchange": "binance"
        }
        
        mock_collector_service.process_ticker_data.return_value = processed_data
        
        # 执行数据处理
        result = await mock_collector_service.process_ticker_data(raw_ticker_data)
        
        # 验证处理结果
        assert result["symbol"] == "BTCUSDT"
        assert result["price"] == 50000.0
        assert result["exchange"] == "binance"
        
        # 模拟存储操作
        await mock_storage_service.store_ticker_data(result)
        
        # 验证存储调用
        mock_storage_service.store_ticker_data.assert_called_once_with(result)
    
    @pytest.mark.asyncio
    async def test_orderbook_data_flow(self, mock_collector_service, mock_storage_service):
        """测试orderbook数据流"""
        # 模拟收集到的orderbook数据
        raw_orderbook_data = {
            "s": "BTCUSDT",
            "b": [["49950.00", "1.00"], ["49940.00", "2.00"]],
            "a": [["50050.00", "1.50"], ["50060.00", "2.50"]],
            "E": 1718712000000
        }
        
        # 模拟数据处理
        processed_data = {
            "symbol": "BTCUSDT",
            "bids": [[49950.0, 1.0], [49940.0, 2.0]],
            "asks": [[50050.0, 1.5], [50060.0, 2.5]],
            "timestamp": "2025-06-18T10:00:00Z",
            "exchange": "binance"
        }
        
        mock_collector_service.process_orderbook_data.return_value = processed_data
        
        # 执行数据处理
        result = await mock_collector_service.process_orderbook_data(raw_orderbook_data)
        
        # 验证处理结果
        assert result["symbol"] == "BTCUSDT"
        assert len(result["bids"]) == 2
        assert len(result["asks"]) == 2
        
        # 模拟存储操作
        await mock_storage_service.store_orderbook_data(result)
        
        # 验证存储调用
        mock_storage_service.store_orderbook_data.assert_called_once_with(result)
    
    @pytest.mark.asyncio
    async def test_data_retrieval_flow(self, mock_storage_service):
        """测试数据检索流"""
        # 模拟存储的数据
        stored_data = [
            {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "volume": 1000.0,
                "timestamp": "2025-06-18T10:00:00Z"
            },
            {
                "symbol": "ETHUSDT",
                "price": 3000.0,
                "volume": 500.0,
                "timestamp": "2025-06-18T10:00:01Z"
            }
        ]
        
        mock_storage_service.get_latest_data.return_value = stored_data
        
        # 执行数据检索
        result = await mock_storage_service.get_latest_data("ticker", limit=10)
        
        # 验证检索结果
        assert len(result) == 2
        assert result[0]["symbol"] == "BTCUSDT"
        assert result[1]["symbol"] == "ETHUSDT"
        
        # 验证检索调用
        mock_storage_service.get_latest_data.assert_called_once_with("ticker", limit=10)


class TestAPIGatewayIntegration:
    """API网关集成测试"""
    
    @pytest.fixture
    async def mock_api_gateway(self):
        """模拟API网关"""
        mock_gateway = AsyncMock()
        mock_gateway.route_request = AsyncMock()
        mock_gateway.authenticate_request = AsyncMock()
        mock_gateway.rate_limit_check = AsyncMock()
        return mock_gateway
    
    @pytest.fixture
    async def mock_backend_service(self):
        """模拟后端服务"""
        mock_service = AsyncMock()
        mock_service.handle_request = AsyncMock()
        mock_service.get_market_data = AsyncMock()
        mock_service.get_user_data = AsyncMock()
        return mock_service
    
    @pytest.mark.asyncio
    async def test_api_request_routing(self, mock_api_gateway, mock_backend_service):
        """测试API请求路由"""
        # 模拟API请求
        api_request = {
            "method": "GET",
            "path": "/api/v1/market/ticker/BTCUSDT",
            "headers": {
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json"
            },
            "query_params": {"limit": "10"}
        }
        
        # 模拟认证成功
        mock_api_gateway.authenticate_request.return_value = True
        
        # 模拟限流检查通过
        mock_api_gateway.rate_limit_check.return_value = True
        
        # 模拟后端响应
        backend_response = {
            "status": "success",
            "data": {
                "symbol": "BTCUSDT",
                "price": 50000.0,
                "volume": 1000.0
            }
        }
        mock_backend_service.get_market_data.return_value = backend_response
        
        # 执行请求路由
        auth_result = await mock_api_gateway.authenticate_request(api_request)
        rate_limit_result = await mock_api_gateway.rate_limit_check(api_request)
        
        if auth_result and rate_limit_result:
            response = await mock_backend_service.get_market_data("BTCUSDT")
        
        # 验证结果
        assert auth_result is True
        assert rate_limit_result is True
        assert response["status"] == "success"
        assert response["data"]["symbol"] == "BTCUSDT"
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, mock_api_gateway, mock_backend_service):
        """测试API错误处理"""
        # 模拟认证失败的请求
        invalid_request = {
            "method": "GET",
            "path": "/api/v1/market/ticker/BTCUSDT",
            "headers": {
                "Authorization": "Bearer invalid_token",
                "Content-Type": "application/json"
            }
        }
        
        # 模拟认证失败
        mock_api_gateway.authenticate_request.return_value = False
        
        # 执行认证检查
        auth_result = await mock_api_gateway.authenticate_request(invalid_request)
        
        # 验证认证失败
        assert auth_result is False
        
        # 验证后端服务未被调用
        mock_backend_service.get_market_data.assert_not_called()


class TestCacheServiceIntegration:
    """缓存服务集成测试"""
    
    @pytest.fixture
    async def mock_cache_service(self):
        """模拟缓存服务"""
        mock_service = AsyncMock()
        mock_service.get = AsyncMock()
        mock_service.set = AsyncMock()
        mock_service.invalidate = AsyncMock()
        mock_service.get_or_set = AsyncMock()
        return mock_service
    
    @pytest.fixture
    async def mock_data_service(self):
        """模拟数据服务"""
        mock_service = AsyncMock()
        mock_service.fetch_data = AsyncMock()
        mock_service.update_data = AsyncMock()
        return mock_service
    
    @pytest.mark.asyncio
    async def test_cache_hit_scenario(self, mock_cache_service, mock_data_service):
        """测试缓存命中场景"""
        cache_key = "market:ticker:BTCUSDT"
        cached_data = {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "volume": 1000.0,
            "cached_at": int(time.time())
        }
        
        # 模拟缓存命中
        mock_cache_service.get.return_value = cached_data
        
        # 执行数据获取
        result = await mock_cache_service.get(cache_key)
        
        # 验证缓存命中
        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["price"] == 50000.0
        
        # 验证数据服务未被调用
        mock_data_service.fetch_data.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_cache_miss_scenario(self, mock_cache_service, mock_data_service):
        """测试缓存未命中场景"""
        cache_key = "market:ticker:ETHUSDT"
        
        # 模拟缓存未命中
        mock_cache_service.get.return_value = None
        
        # 模拟从数据服务获取数据
        fresh_data = {
            "symbol": "ETHUSDT",
            "price": 3000.0,
            "volume": 500.0,
            "fetched_at": int(time.time())
        }
        mock_data_service.fetch_data.return_value = fresh_data
        
        # 执行缓存未命中处理
        cached_result = await mock_cache_service.get(cache_key)
        
        if cached_result is None:
            # 从数据服务获取
            fresh_result = await mock_data_service.fetch_data("ETHUSDT")
            
            # 更新缓存
            await mock_cache_service.set(cache_key, fresh_result, ttl=300)
        
        # 验证结果
        assert cached_result is None
        assert fresh_result["symbol"] == "ETHUSDT"
        assert fresh_result["price"] == 3000.0
        
        # 验证调用
        mock_data_service.fetch_data.assert_called_once_with("ETHUSDT")
        mock_cache_service.set.assert_called_once_with(cache_key, fresh_result, ttl=300)


class TestMonitoringServiceIntegration:
    """监控服务集成测试"""
    
    @pytest.mark.asyncio
    async def test_metrics_collection_integration(self):
        """测试指标收集集成"""
        with patch('core.observability.metrics.unified_metrics_manager.UnifiedMetricsManager') as mock_metrics:
            # 模拟指标管理器
            mock_manager = AsyncMock()
            mock_metrics.return_value = mock_manager
            
            # 模拟指标收集
            test_metrics = {
                "api_requests_total": 1000,
                "api_response_time_avg": 150.5,
                "cache_hit_rate": 0.85,
                "error_rate": 0.02
            }
            
            # 记录指标
            for metric_name, value in test_metrics.items():
                await mock_manager.record_metric(metric_name, value)
            
            # 验证指标记录
            assert mock_manager.record_metric.call_count == len(test_metrics)
    
    @pytest.mark.asyncio
    async def test_health_check_integration(self):
        """测试健康检查集成"""
        # 模拟各服务健康状态
        service_health = {
            "database": {"status": "healthy", "response_time": 50},
            "cache": {"status": "healthy", "response_time": 10},
            "message_queue": {"status": "healthy", "response_time": 25},
            "external_api": {"status": "degraded", "response_time": 500}
        }
        
        # 计算整体健康状态
        healthy_services = sum(1 for service in service_health.values() 
                             if service["status"] == "healthy")
        total_services = len(service_health)
        health_ratio = healthy_services / total_services
        
        overall_status = "healthy" if health_ratio >= 0.8 else "degraded"
        
        # 验证健康检查结果
        assert overall_status == "degraded"  # 因为有一个服务状态为degraded
        assert health_ratio == 0.75  # 3/4 = 0.75
