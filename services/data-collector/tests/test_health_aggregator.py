"""
HealthAggregator 单元测试
"""

import pytest
import time
from core.health_aggregator import (
    HealthAggregator, ProcessHealth, HealthStatus
)


class TestHealthStatus:
    """测试 HealthStatus 枚举"""
    
    def test_health_status_values(self):
        """测试健康状态值"""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestProcessHealth:
    """测试 ProcessHealth"""

    def test_create_process_health(self):
        """测试创建进程健康状态"""
        health = ProcessHealth("okx_spot")
        assert health.exchange == "okx_spot"
        assert health.status == HealthStatus.UNKNOWN

    def test_create_with_params(self):
        """测试创建带参数的进程健康状态"""
        health = ProcessHealth(
            exchange="okx_spot",
            status=HealthStatus.HEALTHY,
            cpu_percent=45.5,
            memory_mb=120.0,
            uptime_seconds=3600.0,
            services={"nats": {"status": "healthy"}}
        )

        assert health.exchange == "okx_spot"
        assert health.status == HealthStatus.HEALTHY
        assert health.cpu_percent == 45.5
        assert health.memory_mb == 120.0
        assert health.uptime_seconds == 3600.0
        assert health.services == {"nats": {"status": "healthy"}}

    def test_to_dict(self):
        """测试转换为字典"""
        health = ProcessHealth(
            exchange="okx_spot",
            status=HealthStatus.HEALTHY,
            cpu_percent=45.5,
            memory_mb=120.0,
            uptime_seconds=3600.0,
            services={"nats": {"status": "healthy"}}
        )

        d = health.to_dict()
        assert d["status"] == "healthy"
        assert d["cpu_percent"] == 45.5
        assert d["memory_mb"] == 120.0
        assert d["uptime_seconds"] == 3600.0
        assert d["services"] == {"nats": {"status": "healthy"}}


class TestHealthAggregator:
    """测试 HealthAggregator"""
    
    def test_create_aggregator(self):
        """测试创建聚合器"""
        aggregator = HealthAggregator()
        assert aggregator.process_health == {}
    
    def test_update_process_health(self):
        """测试更新进程健康状态"""
        aggregator = HealthAggregator()

        aggregator.update_process_health(
            exchange="okx_spot",
            status="healthy",
            cpu_percent=45.5,
            memory_mb=120.0,
            uptime_seconds=3600.0,
            services={"nats": {"status": "healthy"}}
        )

        assert "okx_spot" in aggregator.process_health
        health = aggregator.process_health["okx_spot"]
        assert health.status == HealthStatus.HEALTHY
        assert health.cpu_percent == 45.5

    def test_get_process_health(self):
        """测试获取指定进程的健康状态"""
        aggregator = HealthAggregator()

        aggregator.update_process_health(
            exchange="okx_spot",
            status="healthy",
            cpu_percent=45.5,
            memory_mb=120.0,
            uptime_seconds=3600.0,
            services={}
        )

        health = aggregator.get_process_health("okx_spot")
        assert health.status == HealthStatus.HEALTHY
    
    def test_get_aggregated_status_all_healthy(self):
        """测试聚合状态（全部健康）"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("binance_spot", "healthy", 50.0, 120.0, 3600.0, {})
        
        status = aggregator.get_aggregated_status()
        assert status == HealthStatus.HEALTHY
    
    def test_get_aggregated_status_one_degraded(self):
        """测试聚合状态（一个降级）"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("binance_spot", "degraded", 50.0, 120.0, 3600.0, {})
        
        status = aggregator.get_aggregated_status()
        assert status == HealthStatus.DEGRADED
    
    def test_get_aggregated_status_one_unhealthy(self):
        """测试聚合状态（一个不健康）"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("binance_spot", "unhealthy", 50.0, 120.0, 3600.0, {})
        
        status = aggregator.get_aggregated_status()
        assert status == HealthStatus.UNHEALTHY
    
    def test_get_aggregated_status_all_unknown(self):
        """测试聚合状态（全部未知）"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "unknown", 0.0, 0.0, 0.0, {})
        aggregator.update_process_health("binance_spot", "unknown", 0.0, 0.0, 0.0, {})
        
        status = aggregator.get_aggregated_status()
        assert status == HealthStatus.UNKNOWN
    
    def test_generate_health_response(self):
        """测试生成健康检查响应"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("binance_spot", "healthy", 60.0, 150.0, 3600.0, {})
        
        response = aggregator.generate_health_response()
        
        # 检查整体状态
        assert response["status"] == "healthy"
        assert response["mode"] == "multiprocess"
        
        # 检查进程详情
        assert "processes" in response
        assert "okx_spot" in response["processes"]
        assert "binance_spot" in response["processes"]
        
        # 检查汇总信息
        assert "summary" in response
        assert response["summary"]["total_processes"] == 2
        assert response["summary"]["healthy_processes"] == 2
        assert response["summary"]["total_cpu_percent"] == 100.0
        assert response["summary"]["total_memory_mb"] == 250.0
    
    def test_clear_process_health(self):
        """测试清除指定进程的健康状态"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("binance_spot", "healthy", 60.0, 150.0, 3600.0, {})
        
        aggregator.clear_process_health("okx_spot")
        
        assert "okx_spot" not in aggregator.process_health
        assert "binance_spot" in aggregator.process_health
    
    def test_clear_all_health(self):
        """测试清除所有健康状态"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("binance_spot", "healthy", 60.0, 150.0, 3600.0, {})
        
        aggregator.clear_all_health()
        
        assert aggregator.process_health == {}
    
    def test_health_ttl(self):
        """测试健康状态过期"""
        aggregator = HealthAggregator(health_ttl=0.5)  # 0.5 秒过期
        
        # 添加健康状态
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        
        # 立即检查（未过期）
        health = aggregator.get_process_health("okx_spot")
        assert health is not None
        
        # 等待过期
        time.sleep(0.6)
        
        # 检查是否过期
        response = aggregator.generate_health_response()
        # 过期的进程应该被标记为 unknown 或从列表中移除
        if "okx_spot" in response["processes"]:
            assert response["processes"]["okx_spot"]["status"] == "unknown"
    
    def test_get_all_process_health(self):
        """测试获取所有进程的健康状态"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("okx_spot", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("binance_spot", "degraded", 60.0, 150.0, 3600.0, {})
        
        all_health = aggregator.get_all_process_health()
        assert len(all_health) == 2
        assert "okx_spot" in all_health
        assert "binance_spot" in all_health


class TestHealthStatusPriority:
    """测试健康状态优先级"""
    
    def test_status_priority_unhealthy_wins(self):
        """测试不健康状态优先级最高"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("p1", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("p2", "degraded", 50.0, 120.0, 3600.0, {})
        aggregator.update_process_health("p3", "unhealthy", 60.0, 150.0, 3600.0, {})
        
        status = aggregator.get_aggregated_status()
        assert status == HealthStatus.UNHEALTHY
    
    def test_status_priority_degraded_over_healthy(self):
        """测试降级状态优先于健康"""
        aggregator = HealthAggregator()
        
        aggregator.update_process_health("p1", "healthy", 40.0, 100.0, 3600.0, {})
        aggregator.update_process_health("p2", "healthy", 50.0, 120.0, 3600.0, {})
        aggregator.update_process_health("p3", "degraded", 60.0, 150.0, 3600.0, {})
        
        status = aggregator.get_aggregated_status()
        assert status == HealthStatus.DEGRADED


class TestIntegration:
    """集成测试"""

    def test_process_health_to_aggregator_flow(self):
        """测试从进程健康状态到聚合器的完整流程"""
        # 创建进程健康状态
        health1 = ProcessHealth(
            exchange="okx_spot",
            status=HealthStatus.HEALTHY,
            cpu_percent=40.0,
            memory_mb=100.0,
            uptime_seconds=3600.0,
            services={"nats": {"status": "healthy"}}
        )

        health2 = ProcessHealth(
            exchange="binance_spot",
            status=HealthStatus.DEGRADED,
            cpu_percent=60.0,
            memory_mb=150.0,
            uptime_seconds=3600.0,
            services={"nats": {"status": "degraded"}}
        )

        # 创建聚合器
        aggregator = HealthAggregator()

        # 更新健康状态
        data1 = health1.to_dict()
        aggregator.update_process_health(
            "okx_spot",
            data1["status"],
            data1["cpu_percent"],
            data1["memory_mb"],
            data1["uptime_seconds"],
            data1["services"]
        )

        data2 = health2.to_dict()
        aggregator.update_process_health(
            "binance_spot",
            data2["status"],
            data2["cpu_percent"],
            data2["memory_mb"],
            data2["uptime_seconds"],
            data2["services"]
        )

        # 检查聚合结果
        status = aggregator.get_aggregated_status()
        assert status == HealthStatus.DEGRADED

        # 生成响应
        response = aggregator.generate_health_response()
        assert response["status"] == "degraded"
        assert response["summary"]["total_processes"] == 2
        assert response["summary"]["healthy_processes"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

