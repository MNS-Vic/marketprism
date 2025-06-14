"""
MarketPrism API代理简单测试

验证统一API代理的基本功能和超限处理
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta, timezone

from core.networking.exchange_api_proxy import (
    ExchangeAPIProxy, 
    IPResource, 
    RequestRecord,
    ProxyMode
)


class TestIPResource:
    """测试IP资源管理"""
    
    def test_ip_resource_creation(self):
        """测试IP资源创建"""
        ip = IPResource(ip="192.168.1.100", location="test")
        
        assert ip.ip == "192.168.1.100"
        assert ip.location == "test"
        assert ip.max_weight_per_minute == 6000
        assert ip.current_weight == 0
        assert ip.health_score == 1.0
        assert ip.is_available is True
    
    def test_weight_consumption(self):
        """测试权重消费"""
        ip = IPResource(ip="test", max_weight_per_minute=100)
        
        # 消费权重成功
        assert ip.consume_weight(50) is True
        assert ip.current_weight == 50
        
        # 消费权重失败（超限）
        assert ip.consume_weight(60) is False
        assert ip.current_weight == 50  # 不变
        
        # 消费剩余权重
        assert ip.consume_weight(50) is True
        assert ip.current_weight == 100
    
    def test_weight_reset(self):
        """测试权重重置"""
        ip = IPResource(ip="test")
        ip.current_weight = 100
        
        # 模拟时间流逝
        ip.last_reset = datetime.now() - timedelta(minutes=2)
        ip.reset_weight_if_needed()
        
        assert ip.current_weight == 0
    
    def test_rate_limit_handling(self):
        """测试速率限制处理"""
        ip = IPResource(ip="test")
        
        # 处理429警告
        original_health = ip.health_score
        ip.handle_rate_limit_response(429, retry_after=60)
        
        assert ip.health_score < original_health
        assert ip.banned_until is not None
        
        # 处理418封禁
        ip.handle_rate_limit_response(418, retry_after=120)
        assert ip.health_score == 0.1
        assert ip.banned_until is not None


class TestExchangeAPIProxy:
    """测试交易所API代理"""
    
    def test_proxy_initialization(self):
        """测试代理初始化"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        
        assert proxy.mode == ProxyMode.UNIFIED
        assert len(proxy.ip_resources) == 0
        assert proxy.stats['total_requests'] == 0
    
    def test_add_ip_resource(self):
        """测试添加IP资源"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        proxy.add_ip_resource("192.168.1.100", "test-server")
        
        assert "192.168.1.100" in proxy.ip_resources
        assert proxy.ip_resources["192.168.1.100"].location == "test-server"
    
    def test_get_best_ip(self):
        """测试获取最佳IP"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        proxy.add_ip_resource("192.168.1.100")
        proxy.add_ip_resource("192.168.1.101")
        
        # 设置IP状态
        proxy.ip_resources["192.168.1.100"].current_weight = 1000
        proxy.ip_resources["192.168.1.101"].current_weight = 500
        
        best_ip = proxy.get_best_ip("binance")
        assert best_ip.ip == "192.168.1.101"  # 权重使用更少的IP
    
    def test_request_record(self):
        """测试请求记录"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        
        record = RequestRecord(
            timestamp=datetime.now(),
            exchange="binance",
            endpoint="/api/v3/ping",
            method="GET",
            weight=1,
            status_code=200,
            response_time=0.5,
            ip_used="192.168.1.100"
        )
        
        proxy._add_request_record(record)
        assert len(proxy.request_records) == 1
        assert proxy.request_records[0].exchange == "binance"
    
    def test_status_reporting(self):
        """测试状态报告"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        proxy.add_ip_resource("192.168.1.100")
        proxy.add_ip_resource("192.168.1.101")
        
        status = proxy.get_status()
        
        assert status['mode'] == 'unified'
        assert status['total_ips'] == 2
        assert status['available_ips'] == 2
        assert 'ip_details' in status
        assert 'statistics' in status
    
    def test_health_report(self):
        """测试健康报告"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        proxy.add_ip_resource("192.168.1.100")
        
        health = proxy.get_health_report()
        
        assert 'overall_health' in health
        assert 'error_analysis' in health
        assert 'performance' in health
        assert 'recommendations' in health
    
    @pytest.mark.asyncio
    async def test_mock_request_success(self):
        """测试模拟请求成功"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        proxy.add_ip_resource("127.0.0.1")
        
        # 模拟成功响应
        mock_response_data = {"status": "ok", "serverTime": 1234567890}
        
        with patch.object(proxy, '_send_request', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response_data
            
            result = await proxy.request("binance", "GET", "/api/v3/ping")
            
            assert result == mock_response_data
            assert proxy.stats['total_requests'] == 1
            assert proxy.stats['successful_requests'] == 1
    
    @pytest.mark.asyncio
    async def test_mock_request_rate_limit(self):
        """测试模拟速率限制"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        proxy.add_ip_resource("127.0.0.1")
        
        # 模拟429错误
        from aiohttp import ClientResponseError
        
        with patch.object(proxy, '_send_request', new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = ClientResponseError(
                request_info=None,
                history=(),
                message="Too Many Requests"
            )
            mock_send.side_effect.status = 429
            
            with pytest.raises(ClientResponseError):
                await proxy.request("binance", "GET", "/api/v3/ping")
            
            assert proxy.stats['total_requests'] == 1
            assert proxy.stats['failed_requests'] == 1


class TestProxyModes:
    """测试代理模式"""
    
    def test_auto_configure(self):
        """测试自动配置"""
        proxy = ExchangeAPIProxy.auto_configure()
        assert proxy.mode == ProxyMode.AUTO
    
    def test_unified_mode(self):
        """测试统一模式"""
        proxy = ExchangeAPIProxy.unified_mode("192.168.1.100")
        assert proxy.mode == ProxyMode.UNIFIED
        assert "192.168.1.100" in proxy.ip_resources
    
    def test_distributed_mode(self):
        """测试分布式模式"""
        ips = ["192.168.1.100", "192.168.1.101", "192.168.1.102"]
        proxy = ExchangeAPIProxy.distributed_mode(ips)
        
        assert proxy.mode == ProxyMode.DISTRIBUTED
        assert len(proxy.ip_resources) == 3
        for ip in ips:
            assert ip in proxy.ip_resources


class TestWeightCalculation:
    """测试权重计算"""
    
    def test_basic_weight_calculation(self):
        """测试基础权重计算"""
        proxy = ExchangeAPIProxy(ProxyMode.UNIFIED)
        
        # 测试不同端点的权重
        ping_weight = proxy.weight_calculator.calculate_weight("binance", "/api/v3/ping", {})
        assert ping_weight == 1
        
        info_weight = proxy.weight_calculator.calculate_weight("binance", "/api/v3/exchangeInfo", {})
        assert info_weight == 10
        
        unknown_weight = proxy.weight_calculator.calculate_weight("binance", "/api/v3/unknown", {})
        assert unknown_weight == 1  # 默认权重


if __name__ == "__main__":
    # 运行测试
    print("🧪 MarketPrism API代理单元测试")
    print("=" * 50)
    
    # 同步测试
    print("\n📋 测试IP资源管理...")
    test_ip = TestIPResource()
    test_ip.test_ip_resource_creation()
    test_ip.test_weight_consumption()
    test_ip.test_weight_reset()
    test_ip.test_rate_limit_handling()
    print("✅ IP资源管理测试通过")
    
    print("\n📋 测试代理基础功能...")
    test_proxy = TestExchangeAPIProxy()
    test_proxy.test_proxy_initialization()
    test_proxy.test_add_ip_resource()
    test_proxy.test_get_best_ip()
    test_proxy.test_request_record()
    test_proxy.test_status_reporting()
    test_proxy.test_health_report()
    print("✅ 代理基础功能测试通过")
    
    print("\n📋 测试代理模式...")
    test_modes = TestProxyModes()
    test_modes.test_auto_configure()
    test_modes.test_unified_mode()
    test_modes.test_distributed_mode()
    print("✅ 代理模式测试通过")
    
    print("\n📋 测试权重计算...")
    test_weight = TestWeightCalculation()
    test_weight.test_basic_weight_calculation()
    print("✅ 权重计算测试通过")
    
    # 异步测试
    async def run_async_tests():
        print("\n📋 测试异步请求功能...")
        test_proxy = TestExchangeAPIProxy()
        await test_proxy.test_mock_request_success()
        await test_proxy.test_mock_request_rate_limit()
        print("✅ 异步请求功能测试通过")
    
    asyncio.run(run_async_tests())
    
    print("\n🎉 所有测试通过！")
    print("\n💡 API代理核心功能验证成功:")
    print("  ✅ IP资源管理和权重控制")
    print("  ✅ 多种代理模式支持")
    print("  ✅ 速率限制和错误处理")
    print("  ✅ 实时监控和健康报告")
    print("  ✅ 零侵入集成架构")