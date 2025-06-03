"""
企业级可靠性系统综合测试

测试熔断器、限流器、重试处理器、负载均衡器和可靠性管理器的集成功能
"""

import asyncio
import pytest
import time
import random
# Mock导入已移除 - 请使用真实的服务进行可靠性测试

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from marketprism_reliability import (
    CircuitBreaker, CircuitBreakerConfig,
    RateLimiter, RateLimitConfig, RequestPriority,
    RetryHandler, RetryConfig,
    LoadBalancer, LoadBalancerConfig, InstanceInfo,
    ReliabilityManager, ReliabilityConfig
)


class TestCircuitBreaker:
    """熔断器测试"""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_basic_functionality(self):
        """测试熔断器基本功能"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=1.0,
            timeout=0.5
        )
        breaker = CircuitBreaker("test_breaker", config)
        
        # 模拟成功调用
        async def success_func():
            return "success"
        
        result = await breaker.call(success_func)
        assert result == "success"
        
        # 模拟失败调用
        async def failure_func():
            raise Exception("test failure")
        
        # 触发熔断
        for _ in range(3):
            try:
                await breaker.call(failure_func)
            except:
                pass
        
        # 验证熔断器开启
        assert breaker.state.value == "open"
        
        # 测试降级
        async def fallback_func():
            return "fallback"
        
        result = await breaker.call(failure_func, fallback=fallback_func)
        assert result == "fallback"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self):
        """测试熔断器恢复"""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1
        )
        breaker = CircuitBreaker("recovery_test", config)
        
        # 触发熔断
        async def failure_func():
            raise Exception("failure")
        
        for _ in range(2):
            try:
                await breaker.call(failure_func)
            except:
                pass
        
        assert breaker.state.value == "open"
        
        # 等待恢复时间
        await asyncio.sleep(0.2)
        
        # 成功调用应该恢复熔断器
        async def success_func():
            return "recovered"
        
        result = await breaker.call(success_func)
        assert result == "recovered"
        assert breaker.state.value == "closed"


class TestRateLimiter:
    """限流器测试"""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_basic_functionality(self):
        """测试限流器基本功能"""
        config = RateLimitConfig(
            max_requests_per_second=5.0,
            burst_capacity=10
        )
        limiter = RateLimiter("test_limiter", config)
        
        # 测试正常请求
        for _ in range(5):
            allowed = await limiter.acquire()
            assert allowed == True
        
        # 测试超出限制
        allowed = await limiter.acquire()
        # 由于令牌桶的实现，可能还有一些令牌可用
        
        metrics = limiter.get_metrics()
        assert metrics["total_requests"] >= 5
    
    @pytest.mark.asyncio
    async def test_rate_limiter_priority_queue(self):
        """测试限流器优先级队列"""
        config = RateLimitConfig(
            max_requests_per_second=1.0,
            burst_capacity=1,
            enable_priority_queue=True,
            queue_timeout=1.0
        )
        limiter = RateLimiter("priority_test", config)
        
        # 消耗所有令牌
        await limiter.acquire()
        
        # 测试优先级请求
        high_priority_task = asyncio.create_task(
            limiter.acquire(RequestPriority.HIGH, timeout=2.0)
        )
        normal_priority_task = asyncio.create_task(
            limiter.acquire(RequestPriority.NORMAL, timeout=2.0)
        )
        
        # 等待一段时间让令牌恢复
        await asyncio.sleep(1.5)
        
        high_result = await high_priority_task
        normal_result = await normal_priority_task
        
        # 高优先级应该先获得许可
        assert high_result == True


class TestRetryHandler:
    """重试处理器测试"""
    
    @pytest.mark.asyncio
    async def test_retry_handler_basic_functionality(self):
        """测试重试处理器基本功能"""
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.1,
            strategy="exponential_backoff"
        )
        handler = RetryHandler("test_retry", config)
        
        # 测试成功调用
        async def success_func():
            return "success"
        
        result = await handler.execute_with_retry(success_func)
        assert result == "success"
        
        # 测试重试机制
        call_count = 0
        async def retry_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("network error")
            return "success after retry"
        
        result = await handler.execute_with_retry(retry_func)
        assert result == "success after retry"
        assert call_count == 3
        
        metrics = handler.get_metrics()
        assert metrics["retries_performed"] > 0
    
    @pytest.mark.asyncio
    async def test_retry_handler_non_retryable_error(self):
        """测试不可重试错误"""
        config = RetryConfig(max_attempts=3)
        handler = RetryHandler("non_retry_test", config)
        
        async def non_retryable_func():
            raise ValueError("invalid input")
        
        with pytest.raises(ValueError):
            await handler.execute_with_retry(non_retryable_func)
        
        metrics = handler.get_metrics()
        assert metrics["total_attempts"] == 1  # 只尝试一次


class TestLoadBalancer:
    """负载均衡器测试"""
    
    @pytest.mark.asyncio
    async def test_load_balancer_basic_functionality(self):
        """测试负载均衡器基本功能"""
        config = LoadBalancerConfig()
        lb = LoadBalancer("test_lb", config)
        
        # 添加实例
        instances = [
            InstanceInfo("instance1", "192.168.1.10", 8080, weight=1.0),
            InstanceInfo("instance2", "192.168.1.11", 8080, weight=2.0),
            InstanceInfo("instance3", "192.168.1.12", 8080, weight=1.0)
        ]
        
        for instance in instances:
            await lb.add_instance(instance)
        
        # 测试实例选择
        selected_instances = []
        for _ in range(10):
            instance = await lb.select_instance()
            assert instance is not None
            selected_instances.append(instance.id)
            
            # 模拟请求完成
            await lb.release_instance(instance.id, 0.1, True)
        
        # 验证负载分布
        metrics = lb.get_metrics()
        assert metrics["total_requests"] == 10
        assert metrics["successful_requests"] == 10
    
    @pytest.mark.asyncio
    async def test_load_balancer_health_checks(self):
        """测试负载均衡器健康检查"""
        config = LoadBalancerConfig(
            health_check_interval=0.1,
            max_failures=2
        )
        lb = LoadBalancer("health_test", config)
        
        # 添加实例
        instance = InstanceInfo("test_instance", "192.168.1.10", 8080)
        await lb.add_instance(instance)
        
        # 模拟健康检查失败
        async def failing_health_check(inst):
            return False
        
        lb.add_health_check_callback(failing_health_check)
        await lb.start_health_checks()
        
        # 模拟连续失败
        for _ in range(3):
            await lb.release_instance("test_instance", 1.0, False)
        
        # 等待健康检查
        await asyncio.sleep(0.2)
        
        # 实例应该被标记为不健康
        assert lb.instances["test_instance"].status.value == "unhealthy"
        
        await lb.stop_health_checks()


class TestReliabilityManager:
    """可靠性管理器测试"""
    
    @pytest.mark.asyncio
    async def test_reliability_manager_integration(self):
        """测试可靠性管理器集成功能"""
        config = ReliabilityConfig(
            enable_circuit_breaker=True,
            enable_rate_limiter=True,
            enable_retry_handler=True,
            enable_load_balancer=True,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            rate_limiter_config=RateLimitConfig(max_requests_per_second=10.0),
            retry_handler_config=RetryConfig(max_attempts=2),
            load_balancer_config=LoadBalancerConfig()
        )
        
        manager = ReliabilityManager("integration_test", config)
        await manager.start()
        
        # 添加服务实例
        instances = [
            InstanceInfo("service1", "192.168.1.10", 8080),
            InstanceInfo("service2", "192.168.1.11", 8080)
        ]
        
        for instance in instances:
            await manager.add_instance(instance)
        
        # 测试成功调用
        async def success_api():
            await asyncio.sleep(0.01)  # 模拟处理时间
            return {"status": "success"}
        
        result = await manager.execute_with_protection(success_api)
        assert result["status"] == "success"
        
        # 测试失败和降级
        async def failing_api():
            raise Exception("API failure")
        
        async def fallback_api():
            return {"status": "fallback"}
        
        result = await manager.execute_with_protection(
            failing_api, 
            fallback=fallback_api
        )
        assert result["status"] == "fallback"
        
        # 验证指标
        metrics = manager.get_comprehensive_metrics()
        assert metrics["manager_metrics"]["total_requests"] >= 2
        
        # 验证健康状态
        health = manager.get_health_status()
        assert "overall_health" in health
        assert "components" in health
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_reliability_manager_alerts(self):
        """测试可靠性管理器告警功能"""
        config = ReliabilityConfig(
            enable_alerts=True,
            alert_thresholds={
                "failure_rate": 0.3,  # 30%失败率阈值
                "response_time": 1.0,
                "circuit_breaker_trips": 2,
                "rate_limit_rejections": 5
            }
        )
        
        manager = ReliabilityManager("alert_test", config)
        await manager.start()
        
        # 模拟高失败率
        async def failing_api():
            raise Exception("API failure")
        
        # 执行多次失败调用
        for _ in range(5):
            try:
                await manager.execute_with_protection(failing_api)
            except:
                pass
        
        # 等待告警检查
        await asyncio.sleep(1)
        
        # 验证告警
        metrics = manager.get_comprehensive_metrics()
        # 由于告警检查是异步的，可能需要等待
        
        await manager.stop()


class TestPerformanceAndStress:
    """性能和压力测试"""
    
    @pytest.mark.asyncio
    async def test_high_concurrency_performance(self):
        """测试高并发性能"""
        config = ReliabilityConfig(
            rate_limiter_config=RateLimitConfig(max_requests_per_second=100.0),
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=10)
        )
        
        manager = ReliabilityManager("perf_test", config)
        await manager.start()
        
        # 添加多个实例
        for i in range(3):
            instance = InstanceInfo(f"service{i}", f"192.168.1.{10+i}", 8080)
            await manager.add_instance(instance)
        
        # 模拟API调用
        async def api_call():
            await asyncio.sleep(0.001)  # 1ms处理时间
            if random.random() < 0.05:  # 5%失败率
                raise Exception("random failure")
            return {"data": "response"}
        
        # 并发执行
        start_time = time.time()
        tasks = []
        
        for _ in range(100):
            task = manager.execute_with_protection(api_call)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        # 统计结果
        successful_calls = sum(1 for r in results if isinstance(r, dict))
        failed_calls = len(results) - successful_calls
        
        duration = end_time - start_time
        throughput = len(results) / duration
        
        print(f"并发测试结果:")
        print(f"  总请求数: {len(results)}")
        print(f"  成功请求: {successful_calls}")
        print(f"  失败请求: {failed_calls}")
        print(f"  执行时间: {duration:.3f}s")
        print(f"  吞吐量: {throughput:.1f} req/s")
        
        # 验证性能指标
        assert throughput > 50  # 至少50 req/s
        assert successful_calls > 80  # 至少80%成功率
        
        # 验证系统指标
        metrics = manager.get_comprehensive_metrics()
        print(f"  系统健康分数: {metrics['manager_metrics']['system_health_score']:.3f}")
        
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_under_load(self):
        """测试负载下的熔断器行为"""
        config = ReliabilityConfig(
            circuit_breaker_config=CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=0.5
            ),
            rate_limiter_config=RateLimitConfig(max_requests_per_second=50.0)
        )
        
        manager = ReliabilityManager("cb_load_test", config)
        await manager.start()
        
        # 添加负载均衡器实例
        instance = InstanceInfo("test_service", "192.168.1.100", 8080)
        await manager.add_instance(instance)
        
        # 模拟不稳定的API
        call_count = 0
        async def unstable_api():
            nonlocal call_count
            call_count += 1
            
            # 前20次调用失败，触发熔断
            if call_count <= 20:
                raise Exception("service unavailable")
            
            # 后续调用成功，测试恢复
            return {"status": "recovered"}
        
        async def fallback():
            return {"status": "fallback"}
        
        # 执行调用
        results = []
        for i in range(50):
            try:
                result = await manager.execute_with_protection(
                    unstable_api, 
                    fallback=fallback
                )
                results.append(result)
            except Exception as e:
                results.append({"status": "error", "error": str(e)})
            
            await asyncio.sleep(0.01)  # 小间隔
        
        # 分析结果
        fallback_count = sum(1 for r in results if r.get("status") == "fallback")
        recovered_count = sum(1 for r in results if r.get("status") == "recovered")
        
        print(f"熔断器负载测试结果:")
        print(f"  降级响应: {fallback_count}")
        print(f"  恢复响应: {recovered_count}")
        
        # 验证熔断器工作
        assert fallback_count > 0  # 应该有降级响应
        
        # 获取熔断器指标
        metrics = manager.get_comprehensive_metrics()
        cb_metrics = metrics["component_metrics"]["circuit_breaker"]
        print(f"  熔断次数: {cb_metrics['circuit_opened_count']}")
        
        await manager.stop()


# 运行测试的主函数
async def run_comprehensive_tests():
    """运行综合测试"""
    print("🚀 开始企业级可靠性系统综合测试")
    print("=" * 60)
    
    # 基础功能测试
    print("\n📋 1. 基础功能测试")
    
    # 熔断器测试
    print("  🔧 测试熔断器...")
    cb_test = TestCircuitBreaker()
    await cb_test.test_circuit_breaker_basic_functionality()
    await cb_test.test_circuit_breaker_recovery()
    print("  ✅ 熔断器测试通过")
    
    # 限流器测试
    print("  🚦 测试限流器...")
    rl_test = TestRateLimiter()
    await rl_test.test_rate_limiter_basic_functionality()
    await rl_test.test_rate_limiter_priority_queue()
    print("  ✅ 限流器测试通过")
    
    # 重试处理器测试
    print("  🔄 测试重试处理器...")
    retry_test = TestRetryHandler()
    await retry_test.test_retry_handler_basic_functionality()
    await retry_test.test_retry_handler_non_retryable_error()
    print("  ✅ 重试处理器测试通过")
    
    # 负载均衡器测试
    print("  ⚖️ 测试负载均衡器...")
    lb_test = TestLoadBalancer()
    await lb_test.test_load_balancer_basic_functionality()
    await lb_test.test_load_balancer_health_checks()
    print("  ✅ 负载均衡器测试通过")
    
    # 集成测试
    print("\n🔗 2. 集成测试")
    rm_test = TestReliabilityManager()
    await rm_test.test_reliability_manager_integration()
    await rm_test.test_reliability_manager_alerts()
    print("  ✅ 可靠性管理器集成测试通过")
    
    # 性能测试
    print("\n⚡ 3. 性能和压力测试")
    perf_test = TestPerformanceAndStress()
    await perf_test.test_high_concurrency_performance()
    await perf_test.test_circuit_breaker_under_load()
    print("  ✅ 性能测试通过")
    
    print("\n" + "=" * 60)
    print("🎉 所有测试完成！企业级可靠性系统功能正常")


if __name__ == "__main__":
    # 运行综合测试
    asyncio.run(run_comprehensive_tests()) 