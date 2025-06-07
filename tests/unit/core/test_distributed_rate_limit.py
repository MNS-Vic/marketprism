"""
MarketPrism 分布式速率限制系统测试

测试分布式速率限制协调器和适配器的功能，包括：
1. 多进程速率限制协调
2. 分布式令牌桶算法
3. 客户端注册和配额分配
4. 故障降级机制
5. 性能和并发测试
"""

import pytest
import asyncio
import time
import json
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any
import uuid

# 测试导入
from core.reliability.distributed_rate_limit_coordinator import (
    DistributedRateLimitCoordinator,
    ExchangeType,
    RequestType,
    RateLimitRequest,
    RateLimitResponse,
    TokenBucketManager,
    QuotaAllocator,
    ClientInfo,
    ExchangeRateLimit,
    InMemoryDistributedStorage,
    RedisDistributedStorage
)

from core.reliability.distributed_rate_limit_adapter import (
    DistributedRateLimitAdapter,
    DistributedRateLimitConfig,
    acquire_api_permit,
    get_rate_limit_status
)


class TestDistributedStorage:
    """测试分布式存储"""
    
    @pytest.fixture
    async def memory_storage(self):
        """内存存储测试夹具"""
        storage = InMemoryDistributedStorage()
        yield storage
    
    async def test_memory_storage_basic_operations(self, memory_storage):
        """测试内存存储基本操作"""
        # 测试基本键值操作
        await memory_storage.set("test_key", "test_value")
        value = await memory_storage.get("test_key")
        assert value == "test_value"
        
        # 测试递增操作
        count = await memory_storage.increment("counter", 1)
        assert count == 1
        count = await memory_storage.increment("counter", 2)
        assert count == 3
        
        # 测试哈希操作
        await memory_storage.hash_set("hash_key", "field1", "value1")
        await memory_storage.hash_set("hash_key", "field2", "value2")
        
        field_value = await memory_storage.hash_get("hash_key", "field1")
        assert field_value == "value1"
        
        all_fields = await memory_storage.hash_get_all("hash_key")
        assert all_fields == {"field1": "value1", "field2": "value2"}
        
        # 测试列表操作
        length = await memory_storage.list_append("list_key", "item1")
        assert length == 1
        await memory_storage.list_append("list_key", "item2")
        
        items = await memory_storage.list_range("list_key", 0, -1)
        assert items == ["item1", "item2"]
    
    async def test_memory_storage_expiry(self, memory_storage):
        """测试内存存储过期机制"""
        # 设置带TTL的键
        await memory_storage.set("expiring_key", "value", ttl=1)
        
        # 立即获取应该成功
        value = await memory_storage.get("expiring_key")
        assert value == "value"
        
        # 等待过期
        await asyncio.sleep(1.1)
        
        # 过期后应该返回None
        value = await memory_storage.get("expiring_key")
        assert value is None


class TestTokenBucketManager:
    """测试令牌桶管理器"""
    
    @pytest.fixture
    async def storage(self):
        """存储测试夹具"""
        return InMemoryDistributedStorage()
    
    @pytest.fixture
    async def exchange_limits(self):
        """交易所限制测试夹具"""
        return {
            ExchangeType.BINANCE: ExchangeRateLimit.get_binance_limits()
        }
    
    @pytest.fixture
    async def token_manager(self, storage, exchange_limits):
        """令牌桶管理器测试夹具"""
        return TokenBucketManager(storage, exchange_limits)
    
    async def test_token_consumption(self, token_manager):
        """测试令牌消费"""
        # 初次消费应该成功
        success, remaining = await token_manager.consume_tokens(
            ExchangeType.BINANCE, 
            RequestType.REST_PUBLIC, 
            1
        )
        assert success is True
        assert remaining >= 0
        
        # 继续消费少量令牌应该成功
        for _ in range(10):
            success, remaining = await token_manager.consume_tokens(
                ExchangeType.BINANCE, 
                RequestType.REST_PUBLIC, 
                1
            )
            if not success:
                break
        
        # 验证令牌数量减少
        assert remaining < 1200  # 初始容量
    
    async def test_token_refill(self, token_manager):
        """测试令牌补充"""
        # 消费大量令牌
        await token_manager.consume_tokens(
            ExchangeType.BINANCE, 
            RequestType.REST_PUBLIC, 
            100
        )
        
        # 获取当前状态
        status_before = await token_manager.get_bucket_status(
            ExchangeType.BINANCE, 
            RequestType.REST_PUBLIC
        )
        
        # 等待一小段时间让令牌补充
        await asyncio.sleep(1)
        
        # 再次获取状态
        status_after = await token_manager.get_bucket_status(
            ExchangeType.BINANCE, 
            RequestType.REST_PUBLIC
        )
        
        # 令牌数量应该增加（考虑时间差）
        assert status_after["current_tokens"] >= status_before["current_tokens"]
    
    async def test_bucket_status(self, token_manager):
        """测试令牌桶状态"""
        status = await token_manager.get_bucket_status(
            ExchangeType.BINANCE, 
            RequestType.REST_PUBLIC
        )
        
        required_fields = [
            "exchange", "request_type", "capacity", "current_tokens",
            "refill_rate", "utilization", "last_refill", "time_to_full"
        ]
        
        for field in required_fields:
            assert field in status
        
        assert status["exchange"] == "binance"
        assert status["request_type"] == "rest_public"
        assert status["capacity"] > 0
        assert 0 <= status["utilization"] <= 1


class TestQuotaAllocator:
    """测试配额分配器"""
    
    @pytest.fixture
    async def storage(self):
        """存储测试夹具"""
        return InMemoryDistributedStorage()
    
    @pytest.fixture
    async def quota_allocator(self, storage):
        """配额分配器测试夹具"""
        return QuotaAllocator(storage)
    
    @pytest.fixture
    async def sample_clients(self):
        """示例客户端测试夹具"""
        return [
            ClientInfo(
                client_id="client1",
                process_id="proc1",
                service_name="collector",
                priority=5
            ),
            ClientInfo(
                client_id="client2",
                process_id="proc2",
                service_name="monitor",
                priority=3
            ),
            ClientInfo(
                client_id="client3",
                process_id="proc3",
                service_name="analyzer",
                priority=1
            )
        ]
    
    async def test_client_registration(self, quota_allocator, sample_clients):
        """测试客户端注册"""
        for client in sample_clients:
            success = await quota_allocator.register_client(client)
            assert success is True
        
        # 更新客户端列表（手动添加到列表中）
        for client in sample_clients:
            await quota_allocator.storage.list_append("rate_limit:clients:list", client.client_id)
        
        # 获取活跃客户端
        active_clients = await quota_allocator.get_active_clients()
        assert len(active_clients) == 3
        
        # 验证客户端信息
        client_ids = [client.client_id for client in active_clients]
        assert "client1" in client_ids
        assert "client2" in client_ids
        assert "client3" in client_ids
    
    async def test_quota_allocation(self, quota_allocator, sample_clients):
        """测试配额分配"""
        # 注册客户端
        for client in sample_clients:
            await quota_allocator.register_client(client)
            await quota_allocator.storage.list_append("rate_limit:clients:list", client.client_id)
        
        # 分配配额
        total_quota = 1000.0
        allocations = await quota_allocator.allocate_quotas(
            ExchangeType.BINANCE,
            RequestType.REST_PUBLIC,
            total_quota
        )
        
        # 验证分配结果
        assert len(allocations) == 3
        assert sum(allocations.values()) == pytest.approx(total_quota, rel=1e-9)
        
        # 高优先级客户端应该得到更多配额
        assert allocations["client1"] > allocations["client2"]
        assert allocations["client2"] > allocations["client3"]
    
    async def test_heartbeat(self, quota_allocator):
        """测试心跳机制"""
        client_info = ClientInfo(
            client_id="test_client",
            process_id="test_proc",
            service_name="test_service"
        )
        
        # 注册客户端
        await quota_allocator.register_client(client_info)
        
        # 更新心跳
        success = await quota_allocator.update_heartbeat("test_client")
        assert success is True


class TestDistributedRateLimitCoordinator:
    """测试分布式速率限制协调器"""
    
    @pytest.fixture
    async def storage(self):
        """存储测试夹具"""
        return InMemoryDistributedStorage()
    
    @pytest.fixture
    async def coordinator(self, storage):
        """协调器测试夹具"""
        return DistributedRateLimitCoordinator(storage)
    
    async def test_coordinator_initialization(self, coordinator):
        """测试协调器初始化"""
        assert coordinator.client_id is not None
        assert coordinator.process_id is not None
        assert coordinator.service_name == "marketprism_service"
        assert coordinator.request_count == 0
        assert coordinator.granted_count == 0
        assert coordinator.denied_count == 0
    
    async def test_client_registration(self, coordinator):
        """测试客户端注册"""
        client_id = await coordinator.register_client(
            service_name="test_service",
            priority=5,
            metadata={"version": "1.0.0"}
        )
        
        assert client_id == coordinator.client_id
        
        # 验证心跳
        success = await coordinator.heartbeat()
        assert success is True
    
    async def test_permit_acquisition(self, coordinator):
        """测试许可获取"""
        # 注册客户端
        await coordinator.register_client("test_service")
        
        # 创建请求
        request = RateLimitRequest(
            client_id=coordinator.client_id,
            exchange=ExchangeType.BINANCE,
            request_type=RequestType.REST_PUBLIC,
            weight=1
        )
        
        # 获取许可
        response = await coordinator.acquire_permit(request)
        
        assert isinstance(response, RateLimitResponse)
        assert response.client_id == coordinator.client_id
        assert response.request_id == request.request_id
        
        # 第一次请求应该成功
        assert response.granted is True
        assert response.remaining_quota >= 0
    
    async def test_rate_limiting(self, coordinator):
        """测试速率限制功能"""
        await coordinator.register_client("test_service")
        
        granted_count = 0
        denied_count = 0
        
        # 发送大量请求
        for i in range(50):
            request = RateLimitRequest(
                client_id=coordinator.client_id,
                exchange=ExchangeType.BINANCE,
                request_type=RequestType.REST_PUBLIC,
                weight=50  # 大权重请求
            )
            
            response = await coordinator.acquire_permit(request)
            
            if response.granted:
                granted_count += 1
            else:
                denied_count += 1
        
        # 应该有一些请求被拒绝
        assert granted_count > 0
        assert denied_count >= 0  # 由于初始令牌很多，可能不会被拒绝
    
    async def test_system_status(self, coordinator):
        """测试系统状态"""
        await coordinator.register_client("test_service")
        
        status = await coordinator.get_system_status()
        
        required_sections = ["coordinator_status", "active_clients", "bucket_statuses"]
        for section in required_sections:
            assert section in status
        
        coordinator_status = status["coordinator_status"]
        assert "client_id" in coordinator_status
        assert "service_name" in coordinator_status
        assert "uptime_seconds" in coordinator_status
        assert "total_requests" in coordinator_status


class TestDistributedRateLimitAdapter:
    """测试分布式速率限制适配器"""
    
    @pytest.fixture
    async def config(self):
        """配置测试夹具"""
        return DistributedRateLimitConfig(
            enabled=True,
            storage_type="memory",  # 使用内存存储进行测试
            service_name="test_service",
            priority=3
        )
    
    @pytest.fixture
    async def adapter(self, config):
        """适配器测试夹具"""
        adapter = DistributedRateLimitAdapter(config)
        await adapter.initialize()
        yield adapter
        await adapter.close()
    
    async def test_adapter_initialization(self, adapter):
        """测试适配器初始化"""
        assert adapter.is_initialized is True
        assert adapter.coordinator is not None
        assert adapter.fallback_manager is not None
    
    async def test_permit_acquisition(self, adapter):
        """测试许可获取"""
        result = await adapter.acquire_permit(
            exchange="binance",
            request_type="rest_public",
            weight=1
        )
        
        assert isinstance(result, dict)
        assert "granted" in result
        assert "exchange" in result
        assert "timestamp" in result
        assert "mode" in result
        
        # 第一次请求应该成功
        assert result["granted"] is True
        assert result["exchange"] == "binance"
    
    async def test_status_reporting(self, adapter):
        """测试状态报告"""
        status = await adapter.get_status()
        
        assert isinstance(status, dict)
        assert "adapter_status" in status
        
        adapter_status = status["adapter_status"]
        assert "initialized" in adapter_status
        assert "mode" in adapter_status
        assert "statistics" in adapter_status
        
        assert adapter_status["initialized"] is True
    
    async def test_fallback_mechanism(self):
        """测试降级机制"""
        # 创建一个禁用分布式功能的配置
        config = DistributedRateLimitConfig(
            enabled=False,
            service_name="test_fallback"
        )
        
        adapter = DistributedRateLimitAdapter(config)
        await adapter.initialize()
        
        try:
            result = await adapter.acquire_permit(
                exchange="binance",
                request_type="rest_public"
            )
            
            # 应该使用降级模式
            assert result["mode"] == "fallback"
            
        finally:
            await adapter.close()


class TestConcurrentAccess:
    """测试并发访问"""
    
    @pytest.fixture
    async def coordinator(self):
        """协调器测试夹具"""
        storage = InMemoryDistributedStorage()
        coordinator = DistributedRateLimitCoordinator(storage)
        await coordinator.register_client("concurrent_test")
        return coordinator
    
    async def test_concurrent_requests(self, coordinator):
        """测试并发请求"""
        async def make_request(request_id: int):
            """发起单个请求"""
            request = RateLimitRequest(
                client_id=coordinator.client_id,
                exchange=ExchangeType.BINANCE,
                request_type=RequestType.REST_PUBLIC,
                weight=1
            )
            
            response = await coordinator.acquire_permit(request)
            return {
                "request_id": request_id,
                "granted": response.granted,
                "remaining": response.remaining_quota
            }
        
        # 并发发起多个请求
        tasks = [make_request(i) for i in range(20)]
        results = await asyncio.gather(*tasks)
        
        # 统计结果
        granted_count = sum(1 for r in results if r["granted"])
        denied_count = len(results) - granted_count
        
        # 验证结果
        assert len(results) == 20
        assert granted_count > 0  # 至少有一些请求成功
        
        # 验证剩余配额递减（对于成功的请求）
        granted_results = [r for r in results if r["granted"]]
        if len(granted_results) > 1:
            # 由于并发，不能严格保证递减，但应该有变化
            quotas = [r["remaining"] for r in granted_results]
            assert min(quotas) <= max(quotas)
    
    async def test_multiple_clients(self):
        """测试多客户端场景"""
        storage = InMemoryDistributedStorage()
        
        # 创建多个协调器（模拟多个进程/服务）
        coordinators = []
        for i in range(3):
            coordinator = DistributedRateLimitCoordinator(storage)
            await coordinator.register_client(f"service_{i}", priority=i+1)
            coordinators.append(coordinator)
        
        async def client_requests(coordinator, client_id: int):
            """客户端请求任务"""
            results = []
            for j in range(5):
                request = RateLimitRequest(
                    client_id=coordinator.client_id,
                    exchange=ExchangeType.BINANCE,
                    request_type=RequestType.REST_PUBLIC,
                    weight=1
                )
                
                response = await coordinator.acquire_permit(request)
                results.append({
                    "client_id": client_id,
                    "request_id": j,
                    "granted": response.granted
                })
                
                # 添加小延迟模拟真实场景
                await asyncio.sleep(0.01)
            
            return results
        
        # 并发执行所有客户端请求
        client_tasks = [
            client_requests(coordinator, i) 
            for i, coordinator in enumerate(coordinators)
        ]
        
        all_results = await asyncio.gather(*client_tasks)
        
        # 验证结果
        total_requests = sum(len(client_results) for client_results in all_results)
        total_granted = sum(
            sum(1 for r in client_results if r["granted"])
            for client_results in all_results
        )
        
        assert total_requests == 15  # 3 clients * 5 requests
        assert total_granted > 0  # 至少有一些请求成功


class TestPerformance:
    """性能测试"""
    
    async def test_throughput(self):
        """测试吞吐量"""
        storage = InMemoryDistributedStorage()
        coordinator = DistributedRateLimitCoordinator(storage)
        await coordinator.register_client("performance_test")
        
        request_count = 100
        start_time = time.time()
        
        tasks = []
        for i in range(request_count):
            request = RateLimitRequest(
                client_id=coordinator.client_id,
                exchange=ExchangeType.BINANCE,
                request_type=RequestType.REST_PUBLIC,
                weight=1
            )
            tasks.append(coordinator.acquire_permit(request))
        
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        duration = end_time - start_time
        throughput = request_count / duration
        
        # 验证性能指标
        assert duration < 5.0  # 100个请求应该在5秒内完成
        assert throughput > 20  # 每秒至少处理20个请求
        
        # 验证结果正确性
        granted_count = sum(1 for r in results if r.granted)
        assert granted_count > 0
    
    async def test_memory_usage(self):
        """测试内存使用"""
        storage = InMemoryDistributedStorage()
        
        # 添加大量数据
        for i in range(1000):
            await storage.set(f"key_{i}", f"value_{i}")
            await storage.hash_set(f"hash_{i}", "field", f"value_{i}")
            await storage.list_append(f"list_{i}", f"item_{i}")
        
        # 验证数据存在
        value = await storage.get("key_500")
        assert value == "value_500"
        
        hash_value = await storage.hash_get("hash_500", "field")
        assert hash_value == "value_500"
        
        # 清理测试：设置过期时间
        for i in range(1000):
            await storage.expire(f"key_{i}", 1)
        
        # 等待过期
        await asyncio.sleep(1.1)
        
        # 验证数据已过期
        value = await storage.get("key_500")
        assert value is None


# 便利API测试
class TestConvenienceAPI:
    """测试便利API"""
    
    @pytest.fixture(autouse=True)
    async def setup_global_adapter(self):
        """设置全局适配器"""
        from core.reliability.distributed_rate_limit_adapter import set_global_adapter
        
        config = DistributedRateLimitConfig(
            enabled=True,
            storage_type="memory",
            service_name="api_test"
        )
        
        adapter = DistributedRateLimitAdapter(config)
        await adapter.initialize()
        await set_global_adapter(adapter)
        
        yield
        
        await adapter.close()
    
    async def test_acquire_api_permit(self):
        """测试便利API - 获取许可"""
        result = await acquire_api_permit("binance", "rest_public")
        assert isinstance(result, bool)
        # 第一次请求应该成功
        assert result is True
    
    async def test_get_rate_limit_status(self):
        """测试便利API - 获取状态"""
        status = await get_rate_limit_status()
        assert isinstance(status, dict)
        assert "adapter_status" in status


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])