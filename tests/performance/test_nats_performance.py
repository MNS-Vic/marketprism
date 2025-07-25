"""
MarketPrism NATS性能测试

测试NATS消息服务在高负载下的性能表现
"""
from datetime import datetime, timezone
import sys
import os
import json
import time
import asyncio
import pytest
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入测试辅助工具    
from tests.utils.data_factory import data_factory
from tests.utils.test_helpers import test_helpers

# 如果存在实际的NATS服务模块，则导入它
try:
    from services.common.nats_service import NatsService
    HAS_NATS_MODULE = True
except ImportError:
    HAS_NATS_MODULE = False
    # 创建简化的NATS服务类用于测试
    class NatsService:
        async def connect(self):
            pass
            
        async def close(self):
            pass
            
        async def publish(self, subject, payload):
            pass

# NATS性能测试配置
PERFORMANCE_CONFIG = {
    "message_counts": [100, 1000, 10000],
    "payload_sizes": [100, 1000, 10000],  # 字节
    "batch_sizes": [1, 10, 100, 1000],
    "concurrency_levels": [1, 5, 10, 50, 100]
}

# 性能测试基类
@pytest.mark.performance
class NatsPerformanceTestBase:
    """NATS性能测试基类"""
    
    @staticmethod
    def generate_test_payload(size_bytes: int) -> Dict:
        """生成指定大小的测试负载"""
        # 创建基本数据
        base_data = data_factory.create_trade()
        
        # 增加额外数据以达到所需大小
        extra_size = max(0, size_bytes - len(json.dumps(base_data).encode()))
        if extra_size > 0:
            filler = "x" * extra_size
            base_data["filler"] = filler
            
        return base_data
    
    @staticmethod
    def calculate_performance_metrics(durations: List[float], message_count: int) -> Dict:
        """计算性能指标"""
        total_time = sum(durations)
        avg_time = total_time / len(durations)
        messages_per_second = message_count / total_time if total_time > 0 else 0
        
        metrics = {
            "total_time_seconds": total_time,
            "average_time_seconds": avg_time,
            "messages_per_second": messages_per_second,
            "min_time_seconds": min(durations),
            "max_time_seconds": max(durations),
            "std_dev_seconds": statistics.stdev(durations) if len(durations) > 1 else 0
        }
        
        return metrics
    
    @staticmethod
    def print_performance_report(test_name: str, metrics: Dict, config: Dict) -> None:
        """打印性能报告"""
        print(f"\n=== {test_name} 性能报告 ===")
        print(f"配置: {json.dumps(config, indent=2)}")
        print(f"指标: {json.dumps(metrics, indent=2)}")
        print("=" * 50)


# NATS发布性能测试
@pytest.mark.skipif(not test_helpers.is_nats_available(), reason="NATS服务不可用")
@pytest.mark.performance
class TestNatsPublishPerformance(NatsPerformanceTestBase):
    """测试NATS消息发布性能"""
    
    @pytest.fixture
    async def nats_service(self):
        """创建NATS服务实例"""
        if not HAS_NATS_MODULE:
            pytest.skip("NATS服务模块不可用")
            
        service = NatsService(servers=["nats://localhost:4222"])
        
        try:
            await service.connect()
            yield service
        finally:
            await service.close()
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("message_count", PERFORMANCE_CONFIG["message_counts"])
    @pytest.mark.parametrize("payload_size", PERFORMANCE_CONFIG["payload_sizes"])
    async def test_publish_performance(self, nats_service, message_count, payload_size):
        """测试消息发布性能"""
        # 准备测试数据
        test_subject = f"performance.test.publish.{message_count}.{payload_size}"
        test_payload = self.generate_test_payload(payload_size)
        
        # 执行发布测试
        durations = []
        
        for _ in range(message_count):
            start_time = time.time()
            await nats_service.publish(test_subject, test_payload)
            end_time = time.time()
            durations.append(end_time - start_time)
        
        # 计算性能指标
        metrics = self.calculate_performance_metrics(durations, message_count)
        config = {
            "message_count": message_count,
            "payload_size_bytes": payload_size
        }
        
        # 打印性能报告
        self.print_performance_report("发布性能", metrics, config)
        
        # 验证最低性能要求
        # 注意：这里的性能要求需要根据实际环境进行调整
        assert metrics["messages_per_second"] > 100, "消息发布性能低于预期"
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("batch_size", PERFORMANCE_CONFIG["batch_sizes"])
    async def test_batch_publish_performance(self, nats_service, batch_size):
        """测试批量发布性能"""
        if batch_size > 1000:
            pytest.skip("批量大小超过1000，跳过测试")
            
        # 准备测试数据
        test_subject = f"performance.test.batch.{batch_size}"
        test_payload = self.generate_test_payload(1000)  # 1KB负载
        
        # 创建批量发布任务
        async def publish_batch():
            start_time = time.time()
            tasks = []
            for _ in range(batch_size):
                tasks.append(nats_service.publish(test_subject, test_payload))
            await asyncio.gather(*tasks)
            end_time = time.time()
            return end_time - start_time
        
        # 执行批量发布测试
        iterations = 5
        durations = []
        
        for _ in range(iterations):
            batch_duration = await publish_batch()
            durations.append(batch_duration)
        
        # 计算性能指标
        metrics = self.calculate_performance_metrics(durations, batch_size * iterations)
        config = {
            "batch_size": batch_size,
            "iterations": iterations,
            "payload_size_bytes": 1000
        }
        
        # 打印性能报告
        self.print_performance_report("批量发布性能", metrics, config)
        
        # 验证最低性能要求
        assert metrics["messages_per_second"] > 500, "批量发布性能低于预期"


# NATS发布-订阅性能测试
@pytest.mark.skipif(not test_helpers.is_nats_available(), reason="NATS服务不可用")
@pytest.mark.performance
class TestNatsPubSubPerformance(NatsPerformanceTestBase):
    """测试NATS发布-订阅性能"""
    
    @pytest.fixture
    async def nats_service(self):
        """创建NATS服务实例"""
        if not HAS_NATS_MODULE:
            pytest.skip("NATS服务模块不可用")
            
        service = NatsService(servers=["nats://localhost:4222"])
        
        try:
            await service.connect()
            yield service
        finally:
            await service.close()
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("concurrency", PERFORMANCE_CONFIG["concurrency_levels"])
    async def test_pubsub_concurrency_performance(self, nats_service, concurrency):
        """测试并发发布-订阅性能"""
        if concurrency > 50:
            pytest.skip("并发级别超过50，跳过测试")
            
        # 准备测试数据
        test_subject_prefix = f"performance.test.pubsub.{concurrency}."
        test_payload = self.generate_test_payload(1000)  # 1KB负载
        message_count = 100  # 每个发布者发送的消息数
        
        # 消息计数器
        received_messages = 0
        message_times = []  # 消息处理时间
        
        # 完成事件
        completion_event = asyncio.Event()
        
        # 创建消息处理回调
        async def message_handler(msg):
            nonlocal received_messages
            
            start_time = time.time()
            # 模拟消息处理
            await asyncio.sleep(0.001)
            
            received_messages += 1
            message_times.append(time.time() - start_time)
            
            # 检查是否所有消息都已接收
            if received_messages >= concurrency * message_count:
                completion_event.set()
        
        # 创建发布者任务
        async def publisher(publisher_id):
            subject = f"{test_subject_prefix}{publisher_id}"
            
            for i in range(message_count):
                payload = test_payload.copy()
                payload["publisher_id"] = publisher_id
                payload["message_id"] = i
                
                await nats_service.publish(subject, payload)
                
                # 添加小延迟避免过载
                await asyncio.sleep(0.01)
        
        # 创建并执行订阅
        subscription_tasks = []
        for i in range(concurrency):
            subject = f"{test_subject_prefix}{i}"
            # 这里假设nats_service.subscribe()方法可以订阅消息
            # 实际测试中需要根据真实API进行调整
            await nats_service.subscribe(subject, message_handler)
        
        # 启动并发发布者
        start_time = time.time()
        publish_tasks = [publisher(i) for i in range(concurrency)]
        await asyncio.gather(*publish_tasks)
        
        # 等待所有消息都被处理
        await asyncio.wait_for(completion_event.wait(), timeout=60.0)
        total_time = time.time() - start_time
        
        # 计算性能指标
        total_messages = concurrency * message_count
        metrics = {
            "total_time_seconds": total_time,
            "messages_per_second": total_messages / total_time,
            "average_processing_time": sum(message_times) / len(message_times) if message_times else 0,
            "concurrency_level": concurrency,
            "total_messages": total_messages
        }
        
        config = {
            "concurrency": concurrency,
            "messages_per_publisher": message_count,
            "payload_size_bytes": 1000
        }
        
        # 打印性能报告
        self.print_performance_report("并发发布-订阅性能", metrics, config)
        
        # 验证最低性能要求
        assert metrics["messages_per_second"] > 100, "并发发布-订阅性能低于预期"


# NATS请求-响应性能测试
@pytest.mark.skipif(not test_helpers.is_nats_available(), reason="NATS服务不可用")
@pytest.mark.performance
class TestNatsRequestResponsePerformance(NatsPerformanceTestBase):
    """测试NATS请求-响应性能"""
    
    @pytest.fixture
    async def nats_service_pair(self):
        """创建一对NATS服务实例（请求者和响应者）"""
        if not HAS_NATS_MODULE:
            pytest.skip("NATS服务模块不可用")
            
        requester = NatsService(servers=["nats://localhost:4222"])
        responder = NatsService(servers=["nats://localhost:4222"])
        
        try:
            await requester.connect()
            await responder.connect()
            
            # 设置响应者服务
            async def response_handler(msg):
                # 解析请求
                request_data = json.loads(msg.data.decode())
                
                # 创建响应
                response_data = {
                    "request_id": request_data.get("id", "unknown"),
                    "timestamp": time.time(),
                    "status": "success",
                    "data": {"result": "processed"}
                }
                
                # 发送响应
                await responder.publish(msg.reply, response_data)
            
            # 假设响应者需要订阅请求主题
            await responder.subscribe("request.>", response_handler)
            
            # 等待一段时间确保订阅已建立
            await asyncio.sleep(1)
            
            yield requester
        finally:
            await responder.close()
            await requester.close()
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("message_count", [10, 100, 1000])
    async def test_request_response_performance(self, nats_service_pair, message_count):
        """测试请求-响应性能"""
        if message_count > 1000:
            pytest.skip("消息数超过1000，跳过测试")
            
        # 准备测试数据
        requester = nats_service_pair
        request_subject = "request.performance.test"
        
        # 执行请求-响应测试
        durations = []
        
        for i in range(message_count):
            # 创建请求数据
            request_data = {
                "id": f"req-{i}",
                "timestamp": time.time(),
                "action": "process"
            }
            
            # 发送请求并等待响应
            start_time = time.time()
            response = await requester.request(request_subject, request_data, timeout=5.0)
            end_time = time.time()
            
            # 验证响应
            response_data = json.loads(response.data.decode())
            assert response_data["request_id"] == f"req-{i}"
            assert response_data["status"] == "success"
            
            durations.append(end_time - start_time)
        
        # 计算性能指标
        metrics = self.calculate_performance_metrics(durations, message_count)
        config = {
            "message_count": message_count
        }
        
        # 打印性能报告
        self.print_performance_report("请求-响应性能", metrics, config)
        
        # 验证最低性能要求
        assert metrics["messages_per_second"] > 10, "请求-响应性能低于预期"


if __name__ == "__main__":
    pytest.main(["-v", __file__])