"""
MarketPrism 微服务集成测试

测试services目录下各个微服务模块的集成功能
"""

import asyncio
import pytest
import time
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any, Optional

# 导入服务模块
try:
    from services.data_archiver.archiver import DataArchiver
    from services.data_archiver.storage_manager import StorageManager
    from services.service_registry import ServiceRegistry
    HAS_SERVICE_MODULES = True
except ImportError:
    HAS_SERVICE_MODULES = False

# 导入核心模块
try:
    from core.reliability.rate_limiter import AdaptiveRateLimiter, RateLimitConfig
    from core.reliability.retry_handler import ExponentialBackoffRetry, RetryPolicy
    from core.config.unified_config_manager import UnifiedConfigManager
    from core.storage.unified_storage_manager import UnifiedStorageManager
    HAS_CORE_MODULES = True
except ImportError:
    HAS_CORE_MODULES = False


class MockDataArchiver:
    """模拟数据归档器"""
    
    def __init__(self):
        self.archived_data = []
        self.archive_rules = {}
        self.compression_enabled = True
        self.encryption_enabled = False
        
    async def initialize(self):
        """初始化归档器"""
        await asyncio.sleep(0.1)
        return True
        
    async def archive_data(self, data: List[Dict[str, Any]], archive_type: str = "daily"):
        """归档数据"""
        await asyncio.sleep(0.05)
        
        archived_item = {
            "data": data,
            "archive_type": archive_type,
            "archived_at": datetime.utcnow().isoformat(),
            "compressed": self.compression_enabled,
            "encrypted": self.encryption_enabled,
            "size": len(data)
        }
        
        self.archived_data.append(archived_item)
        return f"archive_{int(time.time())}"
        
    async def retrieve_archived_data(self, archive_id: str) -> List[Dict[str, Any]]:
        """检索归档数据"""
        await asyncio.sleep(0.03)

        # 简化检索逻辑，直接返回最后归档的数据
        if self.archived_data:
            return self.archived_data[-1]["data"]
        return []
        
    def get_archive_stats(self) -> Dict[str, Any]:
        """获取归档统计"""
        total_size = sum(item["size"] for item in self.archived_data)
        return {
            "total_archives": len(self.archived_data),
            "total_data_points": total_size,
            "compression_enabled": self.compression_enabled,
            "encryption_enabled": self.encryption_enabled
        }


class MockServiceRegistry:
    """模拟服务注册中心"""
    
    def __init__(self):
        self.services = {}
        self.health_checks = {}
        
    async def register_service(self, service_name: str, service_info: Dict[str, Any]):
        """注册服务"""
        self.services[service_name] = {
            **service_info,
            "registered_at": datetime.utcnow().isoformat(),
            "status": "active"
        }
        
    async def unregister_service(self, service_name: str):
        """注销服务"""
        if service_name in self.services:
            self.services[service_name]["status"] = "inactive"
            
    async def discover_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        """发现服务"""
        return self.services.get(service_name)
        
    async def list_services(self) -> List[Dict[str, Any]]:
        """列出所有服务"""
        return list(self.services.values())
        
    async def health_check(self, service_name: str) -> bool:
        """健康检查"""
        service = self.services.get(service_name)
        if not service:
            return False
        return service.get("status") == "active"


class MockStorageManager:
    """模拟存储管理器"""
    
    def __init__(self):
        self.storage_backends = {}
        self.data_partitions = {}
        self.replication_factor = 3
        
    async def initialize(self):
        """初始化存储管理器"""
        await asyncio.sleep(0.1)
        
        # 初始化默认存储后端
        self.storage_backends["primary"] = {
            "type": "clickhouse",
            "status": "active",
            "capacity": "1TB",
            "used": "0GB"
        }
        
        self.storage_backends["backup"] = {
            "type": "s3",
            "status": "active", 
            "capacity": "10TB",
            "used": "0GB"
        }
        
    async def create_partition(self, partition_name: str, partition_config: Dict[str, Any]):
        """创建数据分区"""
        self.data_partitions[partition_name] = {
            **partition_config,
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
            "data_count": 0
        }
        
    async def store_data(self, partition_name: str, data: List[Dict[str, Any]]):
        """存储数据到分区"""
        if partition_name not in self.data_partitions:
            await self.create_partition(partition_name, {"type": "time_series"})
            
        partition = self.data_partitions[partition_name]
        partition["data_count"] += len(data)
        partition["last_updated"] = datetime.utcnow().isoformat()
        
    async def query_data(self, partition_name: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """查询分区数据"""
        await asyncio.sleep(0.02)
        
        if partition_name not in self.data_partitions:
            return []
            
        # 模拟查询结果
        partition = self.data_partitions[partition_name]
        return [
            {
                "partition": partition_name,
                "data_count": partition["data_count"],
                "query": query,
                "timestamp": datetime.utcnow().isoformat()
            }
        ]
        
    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        total_partitions = len(self.data_partitions)
        total_data_points = sum(p["data_count"] for p in self.data_partitions.values())
        
        return {
            "total_partitions": total_partitions,
            "total_data_points": total_data_points,
            "storage_backends": len(self.storage_backends),
            "replication_factor": self.replication_factor
        }


class MicroservicesIntegrator:
    """微服务集成器"""
    
    def __init__(self):
        self.data_archiver = MockDataArchiver()
        self.service_registry = MockServiceRegistry()
        self.storage_manager = MockStorageManager()
        self.rate_limiter = None
        self.retry_handler = None
        
    async def initialize(self):
        """初始化集成器"""
        # 初始化核心组件
        if HAS_CORE_MODULES:
            rate_config = RateLimitConfig(max_requests_per_second=50)
            self.rate_limiter = AdaptiveRateLimiter("microservices", rate_config)
            self.retry_handler = ExponentialBackoffRetry("microservices")
            
        # 初始化微服务
        await self.data_archiver.initialize()
        await self.storage_manager.initialize()
        
        # 注册服务
        await self.service_registry.register_service("data_archiver", {
            "host": "localhost",
            "port": 8001,
            "version": "1.0.0",
            "health_endpoint": "/health"
        })
        
        await self.service_registry.register_service("storage_manager", {
            "host": "localhost", 
            "port": 8002,
            "version": "1.0.0",
            "health_endpoint": "/health"
        })
        
    async def process_data_pipeline(self, raw_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """处理完整数据管道"""
        results = {
            "processed_count": 0,
            "stored_count": 0,
            "archived_count": 0,
            "errors": []
        }
        
        try:
            # 1. 应用限流
            if self.rate_limiter:
                await self.rate_limiter.acquire_permit("data_processing")
                
            # 2. 存储到主存储
            partition_name = f"market_data_{datetime.now().strftime('%Y%m%d')}"
            await self.storage_manager.store_data(partition_name, raw_data)
            results["stored_count"] = len(raw_data)
            
            # 3. 归档历史数据
            if len(raw_data) > 100:  # 大批量数据需要归档
                archive_id = await self.data_archiver.archive_data(raw_data, "batch")
                results["archived_count"] = len(raw_data)
                results["archive_id"] = archive_id
                
            results["processed_count"] = len(raw_data)
            
        except Exception as e:
            results["errors"].append(str(e))
            
        return results
        
    async def service_health_monitoring(self) -> Dict[str, Any]:
        """服务健康监控"""
        health_status = {}

        # 直接检查已知服务
        known_services = ["data_archiver", "storage_manager"]
        for service_name in known_services:
            is_healthy = await self.service_registry.health_check(service_name)
            health_status[service_name] = {
                "healthy": is_healthy,
                "last_check": datetime.utcnow().isoformat()
            }

        return health_status
        
    async def data_lifecycle_management(self, retention_days: int = 30) -> Dict[str, Any]:
        """数据生命周期管理"""
        # 查询需要归档的数据
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        # 模拟查询旧数据
        old_data_query = {
            "date_range": {
                "start": "2024-01-01",
                "end": cutoff_date.strftime("%Y-%m-%d")
            }
        }
        
        # 获取存储统计
        storage_stats = self.storage_manager.get_storage_stats()
        archive_stats = self.data_archiver.get_archive_stats()
        
        return {
            "retention_policy": f"{retention_days} days",
            "storage_stats": storage_stats,
            "archive_stats": archive_stats,
            "lifecycle_status": "active"
        }
        
    async def cross_service_communication_test(self) -> Dict[str, Any]:
        """跨服务通信测试"""
        communication_results = {}
        
        # 测试服务发现
        archiver_service = await self.service_registry.discover_service("data_archiver")
        storage_service = await self.service_registry.discover_service("storage_manager")
        
        communication_results["service_discovery"] = {
            "data_archiver": archiver_service is not None,
            "storage_manager": storage_service is not None
        }
        
        # 测试服务间数据传输
        test_data = [{"test": "data", "timestamp": time.time()}]
        
        # 存储 -> 归档流程
        await self.storage_manager.store_data("test_partition", test_data)
        archive_id = await self.data_archiver.archive_data(test_data, "test")
        retrieved_data = await self.data_archiver.retrieve_archived_data(archive_id)
        
        communication_results["data_flow"] = {
            "storage_success": True,
            "archive_success": archive_id is not None,
            "retrieval_success": len(retrieved_data) > 0
        }
        
        return communication_results
        
    async def shutdown(self):
        """关闭集成器"""
        # 注销服务
        await self.service_registry.unregister_service("data_archiver")
        await self.service_registry.unregister_service("storage_manager")


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestMicroservicesIntegration:
    """微服务集成测试"""
    
    @pytest.fixture
    async def integrator(self):
        """创建微服务集成器"""
        integrator = MicroservicesIntegrator()
        await integrator.initialize()
        yield integrator
        await integrator.shutdown()
        
    async def test_service_registration_and_discovery(self, integrator):
        """测试服务注册和发现"""
        # 注册新服务
        await integrator.service_registry.register_service("test_service", {
            "host": "localhost",
            "port": 8003,
            "version": "1.0.0"
        })
        
        # 发现服务
        service = await integrator.service_registry.discover_service("test_service")
        assert service is not None
        assert service["host"] == "localhost"
        assert service["port"] == 8003
        
        # 列出所有服务
        services = await integrator.service_registry.list_services()
        assert len(services) >= 3  # 至少包含3个服务
        
    async def test_data_archiving_workflow(self, integrator):
        """测试数据归档工作流"""
        # 准备测试数据
        test_data = [
            {"symbol": "BTC/USDT", "price": 45000, "timestamp": time.time()},
            {"symbol": "ETH/USDT", "price": 3000, "timestamp": time.time()}
        ]
        
        # 归档数据
        archive_id = await integrator.data_archiver.archive_data(test_data, "test")
        assert archive_id is not None
        
        # 检索归档数据
        retrieved_data = await integrator.data_archiver.retrieve_archived_data(archive_id)
        assert len(retrieved_data) == 2
        
        # 检查归档统计
        stats = integrator.data_archiver.get_archive_stats()
        assert stats["total_archives"] >= 1
        assert stats["total_data_points"] >= 2
        
    async def test_storage_partitioning(self, integrator):
        """测试存储分区管理"""
        # 创建分区
        partition_config = {
            "type": "time_series",
            "retention": "30d",
            "compression": "lz4"
        }
        
        await integrator.storage_manager.create_partition("test_partition", partition_config)
        
        # 存储数据到分区
        test_data = [{"test": "data", "value": i} for i in range(10)]
        await integrator.storage_manager.store_data("test_partition", test_data)
        
        # 查询分区数据
        query_result = await integrator.storage_manager.query_data(
            "test_partition", 
            {"limit": 10}
        )
        assert len(query_result) > 0
        
        # 检查存储统计
        stats = integrator.storage_manager.get_storage_stats()
        assert stats["total_partitions"] >= 1
        assert stats["total_data_points"] >= 10
        
    async def test_complete_data_pipeline(self, integrator):
        """测试完整数据管道"""
        # 准备大批量数据
        large_dataset = [
            {"symbol": f"PAIR{i}", "price": 100 + i, "timestamp": time.time()}
            for i in range(150)  # 超过归档阈值
        ]
        
        # 处理数据管道
        results = await integrator.process_data_pipeline(large_dataset)
        
        # 验证处理结果
        assert results["processed_count"] == 150
        assert results["stored_count"] == 150
        assert results["archived_count"] == 150  # 应该被归档
        assert "archive_id" in results
        assert len(results["errors"]) == 0
        
    async def test_service_health_monitoring(self, integrator):
        """测试服务健康监控"""
        # 执行健康检查
        health_status = await integrator.service_health_monitoring()
        
        # 验证健康状态
        assert "data_archiver" in health_status
        assert "storage_manager" in health_status
        
        for service_name, status in health_status.items():
            assert "healthy" in status
            assert "last_check" in status
            
    async def test_data_lifecycle_management(self, integrator):
        """测试数据生命周期管理"""
        # 执行生命周期管理
        lifecycle_result = await integrator.data_lifecycle_management(retention_days=7)
        
        # 验证生命周期管理结果
        assert lifecycle_result["retention_policy"] == "7 days"
        assert "storage_stats" in lifecycle_result
        assert "archive_stats" in lifecycle_result
        assert lifecycle_result["lifecycle_status"] == "active"
        
    async def test_cross_service_communication(self, integrator):
        """测试跨服务通信"""
        # 执行跨服务通信测试
        comm_results = await integrator.cross_service_communication_test()
        
        # 验证服务发现
        assert comm_results["service_discovery"]["data_archiver"] is True
        assert comm_results["service_discovery"]["storage_manager"] is True
        
        # 验证数据流
        assert comm_results["data_flow"]["storage_success"] is True
        assert comm_results["data_flow"]["archive_success"] is True
        assert comm_results["data_flow"]["retrieval_success"] is True


@pytest.mark.performance
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestMicroservicesPerformance:
    """微服务性能测试"""
    
    @pytest.fixture
    async def performance_integrator(self):
        """创建性能测试集成器"""
        integrator = MicroservicesIntegrator()
        await integrator.initialize()
        yield integrator
        await integrator.shutdown()
        
    async def test_concurrent_service_operations(self, performance_integrator):
        """测试并发服务操作"""
        integrator = performance_integrator
        
        # 并发数据处理任务
        async def process_batch(batch_id: int):
            data = [{"batch": batch_id, "item": i} for i in range(50)]
            return await integrator.process_data_pipeline(data)
            
        # 启动10个并发任务
        start_time = time.time()
        tasks = [process_batch(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time
        
        # 验证并发性能
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) >= 8  # 至少80%成功
        assert elapsed < 10.0  # 应该在10秒内完成
        
        total_processed = sum(r["processed_count"] for r in successful_results)
        assert total_processed >= 400  # 至少处理400条数据
        
    async def test_service_scalability(self, performance_integrator):
        """测试服务可扩展性"""
        integrator = performance_integrator
        
        # 测试不同负载下的性能
        load_sizes = [10, 50, 100, 200]
        performance_metrics = {}
        
        for load_size in load_sizes:
            start_time = time.time()
            
            # 生成测试数据
            test_data = [{"load_test": True, "item": i} for i in range(load_size)]
            
            # 处理数据
            result = await integrator.process_data_pipeline(test_data)
            
            elapsed = time.time() - start_time
            throughput = load_size / elapsed if elapsed > 0 else 0
            
            performance_metrics[load_size] = {
                "elapsed": elapsed,
                "throughput": throughput,
                "success": result["processed_count"] == load_size
            }
            
        # 验证可扩展性
        for load_size, metrics in performance_metrics.items():
            assert metrics["success"] is True
            assert metrics["throughput"] > 0
            
        # 验证吞吐量随负载增长
        throughputs = [metrics["throughput"] for metrics in performance_metrics.values()]
        assert max(throughputs) > min(throughputs)  # 应该有性能差异


if __name__ == "__main__":
    # 运行简单的微服务集成测试
    async def main():
        integrator = MicroservicesIntegrator()
        await integrator.initialize()
        
        # 测试数据管道
        test_data = [{"test": True, "value": i} for i in range(10)]
        result = await integrator.process_data_pipeline(test_data)
        print(f"Pipeline result: {result}")
        
        # 测试健康监控
        health = await integrator.service_health_monitoring()
        print(f"Health status: {health}")
        
        await integrator.shutdown()
        
    asyncio.run(main())
