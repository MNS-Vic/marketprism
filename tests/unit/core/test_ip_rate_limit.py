"""
IP级别速率限制测试

测试重点验证"访问限制是基于IP的"这一核心特性
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from core.reliability.ip_aware_rate_limit_coordinator import (
    IPRateLimit,
    IPManager,
    IPAwareRateLimitCoordinator,
    IPPoolConfig,
    ExchangeType,
    RequestType,
    IPStatus
)
from core.reliability.distributed_rate_limit_coordinator import InMemoryDistributedStorage


class TestIPRateLimit:
    """测试IP级别的速率限制"""
    
    def test_binance_ip_limit_creation(self):
        """测试Binance IP限制创建"""
        ip = "192.168.1.100"
        limit = IPRateLimit.create_for_binance(ip)
        
        assert limit.ip_address == ip
        assert limit.exchange == ExchangeType.BINANCE
        assert limit.requests_per_minute == 1200  # Binance文档规定
        assert limit.weight_per_minute == 6000     # Binance文档规定
        assert limit.order_requests_per_second == 10
        assert limit.websocket_connections == 5
    
    def test_okx_ip_limit_creation(self):
        """测试OKX IP限制创建"""
        ip = "192.168.1.101"
        limit = IPRateLimit.create_for_okx(ip)
        
        assert limit.ip_address == ip
        assert limit.exchange == ExchangeType.OKX
        assert limit.requests_per_minute == 600   # OKX文档规定
        assert limit.weight_per_minute == 3000
        assert limit.order_requests_per_second == 5
    
    def test_can_make_request_normal(self):
        """测试正常情况下可以发出请求"""
        limit = IPRateLimit.create_for_binance("192.168.1.100")
        
        can_request, reason = limit.can_make_request(weight=1)
        assert can_request is True
        assert "可以发出请求" in reason
    
    def test_can_make_request_weight_limit(self):
        """测试权重限制"""
        limit = IPRateLimit.create_for_binance("192.168.1.100")
        limit.current_weight = 5999  # 接近6000限制
        
        # 权重1的请求应该可以通过
        can_request, reason = limit.can_make_request(weight=1)
        assert can_request is True
        
        # 权重2的请求应该被拒绝
        can_request, reason = limit.can_make_request(weight=2)
        assert can_request is False
        assert "超过每分钟权重限制" in reason
    
    def test_can_make_request_frequency_limit(self):
        """测试请求频率限制"""
        limit = IPRateLimit.create_for_binance("192.168.1.100")
        limit.current_requests = 1200  # 达到Binance的1200/分钟限制
        
        can_request, reason = limit.can_make_request(weight=1)
        assert can_request is False
        assert "超过每分钟请求限制" in reason
    
    def test_ip_ban_functionality(self):
        """测试IP封禁功能"""
        limit = IPRateLimit.create_for_binance("192.168.1.100")
        
        # 正常状态
        assert limit.is_banned() is False
        assert limit.status == IPStatus.ACTIVE
        
        # 模拟418响应（IP封禁）
        limit.handle_418_response(retry_after=3600)
        
        assert limit.is_banned() is True
        assert limit.status == IPStatus.BANNED
        assert limit.ban_until > time.time()
        
        # 检查被封禁时不能发请求
        can_request, reason = limit.can_make_request(weight=1)
        assert can_request is False
        assert "IP被封禁" in reason
    
    def test_429_response_handling(self):
        """测试429响应处理"""
        limit = IPRateLimit.create_for_binance("192.168.1.100")
        
        # 模拟429响应
        limit.handle_429_response(retry_after=60)
        
        assert limit.status == IPStatus.WARNING
        assert limit.last_429_time is not None
        assert limit.warning_count == 1
    
    def test_consume_request(self):
        """测试请求消费"""
        limit = IPRateLimit.create_for_binance("192.168.1.100")
        
        initial_requests = limit.current_requests
        initial_weight = limit.current_weight
        initial_orders = limit.current_orders_today
        
        # 消费普通请求
        limit.consume_request(weight=5, is_order=False)
        assert limit.current_requests == initial_requests + 1
        assert limit.current_weight == initial_weight + 5
        assert limit.current_orders_today == initial_orders
        
        # 消费订单请求
        limit.consume_request(weight=1, is_order=True)
        assert limit.current_orders_today == initial_orders + 1
    
    def test_reset_functionality(self):
        """测试重置功能"""
        limit = IPRateLimit.create_for_binance("192.168.1.100")
        
        # 设置一些使用量
        limit.current_requests = 100
        limit.current_weight = 500
        limit.last_reset_time = time.time() - 70  # 70秒前
        
        # 触发重置
        limit.reset_if_needed()
        
        # 应该被重置
        assert limit.current_requests == 0
        assert limit.current_weight == 0


class TestIPManager:
    """测试IP管理器"""
    
    @pytest.fixture
    async def ip_manager(self):
        """创建IP管理器实例"""
        config = IPPoolConfig(
            primary_ip="192.168.1.100",
            backup_ips=["192.168.1.101", "192.168.1.102"],
            auto_rotation=True
        )
        storage = InMemoryDistributedStorage()
        manager = IPManager(config, storage)
        return manager
    
    @pytest.mark.asyncio
    async def test_get_current_ip(self, ip_manager):
        """测试获取当前IP"""
        current_ip = await ip_manager.get_current_ip()
        assert current_ip == "192.168.1.100"  # 应该返回主IP
    
    @pytest.mark.asyncio
    async def test_can_make_request(self, ip_manager):
        """测试是否可以发出请求"""
        can_request, ip, reason = await ip_manager.can_make_request(weight=1)
        
        assert can_request is True
        assert ip == "192.168.1.100"
        assert "可以发出请求" in reason
    
    @pytest.mark.asyncio
    async def test_consume_request(self, ip_manager):
        """测试消费请求"""
        initial_requests = ip_manager.ip_limits["192.168.1.100"].current_requests
        
        await ip_manager.consume_request(weight=5, is_order=False)
        
        final_requests = ip_manager.ip_limits["192.168.1.100"].current_requests
        assert final_requests == initial_requests + 1
    
    @pytest.mark.asyncio
    async def test_ip_rotation_on_ban(self, ip_manager):
        """测试IP封禁时的自动轮换"""
        # 封禁主IP
        main_ip_limit = ip_manager.ip_limits["192.168.1.100"]
        main_ip_limit.handle_418_response(retry_after=3600)
        
        # 获取当前IP应该切换到备用IP
        current_ip = await ip_manager.get_current_ip()
        assert current_ip != "192.168.1.100"
        assert current_ip in ["192.168.1.101", "192.168.1.102"]
    
    @pytest.mark.asyncio
    async def test_handle_exchange_response(self, ip_manager):
        """测试处理交易所响应"""
        # 模拟429响应
        await ip_manager.handle_exchange_response(
            status_code=429,
            headers={"Retry-After": "60", "X-MBX-USED-WEIGHT-1M": "5000"},
            ip="192.168.1.100"
        )
        
        limit = ip_manager.ip_limits["192.168.1.100"]
        assert limit.status == IPStatus.WARNING
        assert limit.last_429_time is not None
    
    @pytest.mark.asyncio
    async def test_ip_status_summary(self, ip_manager):
        """测试IP状态摘要"""
        summary = await ip_manager.get_ip_status_summary()
        
        assert "current_ip" in summary
        assert "total_ips" in summary
        assert "active_ips" in summary
        assert "ip_details" in summary
        
        assert summary["total_ips"] == 3  # 1主IP + 2备用IP
        assert summary["current_ip"] == "192.168.1.100"


class TestIPAwareRateLimitCoordinator:
    """测试IP感知的速率限制协调器"""
    
    @pytest.fixture
    async def coordinator(self):
        """创建协调器实例"""
        storage = InMemoryDistributedStorage()
        config = IPPoolConfig(
            primary_ip="192.168.1.100",
            backup_ips=["192.168.1.101", "192.168.1.102"]
        )
        coordinator = IPAwareRateLimitCoordinator(storage, config)
        return coordinator
    
    @pytest.mark.asyncio
    async def test_acquire_permit_success(self, coordinator):
        """测试成功获取许可"""
        result = await coordinator.acquire_permit(
            exchange=ExchangeType.BINANCE,
            request_type=RequestType.REST_PUBLIC,
            weight=1,
            endpoint="/api/v3/ticker/24hr"
        )
        
        assert result["granted"] is True
        assert result["ip_address"] == "192.168.1.100"
        assert result["exchange"] == "binance"
        assert result["weight"] == 1
        assert result["blocked_by_ip_limit"] is False
    
    @pytest.mark.asyncio
    async def test_acquire_permit_weight_limit(self, coordinator):
        """测试权重限制阻止请求"""
        # 先消耗大量权重
        ip_limit = coordinator.ip_manager.ip_limits["192.168.1.100"]
        ip_limit.current_weight = 5999  # 接近6000限制
        
        # 尝试一个大权重请求
        result = await coordinator.acquire_permit(
            exchange=ExchangeType.BINANCE,
            request_type=RequestType.REST_PUBLIC,
            weight=10  # 这会超过限制
        )
        
        assert result["granted"] is False
        assert "权重限制" in result["reason"]
        assert result["blocked_by_ip_limit"] is True
    
    @pytest.mark.asyncio
    async def test_multiple_requests_same_ip(self, coordinator):
        """测试同一IP下的多个请求（体现IP级别限制）"""
        requests_count = 5
        results = []
        
        for i in range(requests_count):
            result = await coordinator.acquire_permit(
                exchange=ExchangeType.BINANCE,
                request_type=RequestType.REST_PUBLIC,
                weight=1
            )
            results.append(result)
        
        # 所有请求都应该使用同一个IP
        ips_used = {r["ip_address"] for r in results}
        assert len(ips_used) == 1  # 只使用了一个IP
        
        # 验证IP使用统计
        ip_limit = coordinator.ip_manager.ip_limits["192.168.1.100"]
        assert ip_limit.current_requests == requests_count
        assert ip_limit.current_weight == requests_count
    
    @pytest.mark.asyncio
    async def test_ip_switch_on_limit(self, coordinator):
        """测试达到限制时的IP切换"""
        # 将主IP推到限制边缘
        main_ip_limit = coordinator.ip_manager.ip_limits["192.168.1.100"]
        main_ip_limit.current_requests = 1200  # 达到Binance的1200/分钟限制
        
        # 尝试新请求，应该触发IP切换
        result = await coordinator.acquire_permit(
            exchange=ExchangeType.BINANCE,
            request_type=RequestType.REST_PUBLIC,
            weight=1
        )
        
        # 应该切换到备用IP
        if result["granted"]:
            assert result["ip_address"] != "192.168.1.100"
            assert result["ip_address"] in ["192.168.1.101", "192.168.1.102"]
    
    @pytest.mark.asyncio
    async def test_report_exchange_response(self, coordinator):
        """测试报告交易所响应"""
        # 报告429响应
        await coordinator.report_exchange_response(
            status_code=429,
            headers={"Retry-After": "60"},
            ip="192.168.1.100"
        )
        
        # 检查统计是否更新
        assert coordinator.stats["rate_limit_hits"] > 0
        
        # 检查IP状态是否更新
        ip_limit = coordinator.ip_manager.ip_limits["192.168.1.100"]
        assert ip_limit.status == IPStatus.WARNING
    
    @pytest.mark.asyncio
    async def test_system_status(self, coordinator):
        """测试系统状态报告"""
        status = await coordinator.get_system_status()
        
        # 验证状态结构
        assert "coordinator_info" in status
        assert "ip_management" in status
        assert "current_ip" in status
        assert "ip_availability" in status
        
        # 验证IP管理信息
        ip_mgmt = status["ip_management"]
        assert "current_ip" in ip_mgmt
        assert "total_ips" in ip_mgmt
        assert "ip_details" in ip_mgmt
        
        # 验证IP详情
        ip_details = ip_mgmt["ip_details"]
        assert "192.168.1.100" in ip_details
        assert "192.168.1.101" in ip_details
        assert "192.168.1.102" in ip_details


@pytest.mark.asyncio
async def test_concurrent_requests_same_ip():
    """测试并发请求在同一IP下的行为"""
    storage = InMemoryDistributedStorage()
    config = IPPoolConfig(primary_ip="192.168.1.100")
    coordinator = IPAwareRateLimitCoordinator(storage, config)
    
    async def make_request(request_id):
        return await coordinator.acquire_permit(
            exchange=ExchangeType.BINANCE,
            request_type=RequestType.REST_PUBLIC,
            weight=1
        )
    
    # 并发发送10个请求
    tasks = [make_request(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    
    # 所有请求都应该使用同一个IP
    ips_used = {r["ip_address"] for r in results}
    assert len(ips_used) == 1
    
    # 验证请求计数
    ip_limit = coordinator.ip_manager.ip_limits["192.168.1.100"]
    granted_count = sum(1 for r in results if r["granted"])
    assert ip_limit.current_requests == granted_count


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])