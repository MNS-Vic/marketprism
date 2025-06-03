"""
企业级可靠性管理器

统一管理熔断器、限流器、重试处理器和负载均衡器
提供一站式可靠性解决方案和统一的监控接口
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from collections import defaultdict

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .rate_limiter import RateLimiter, RateLimitConfig, RequestPriority
from .retry_handler import RetryHandler, RetryConfig
from .load_balancer import LoadBalancer, LoadBalancerConfig, InstanceInfo

logger = logging.getLogger(__name__)


@dataclass
class ReliabilityConfig:
    """可靠性管理器配置"""
    # 组件启用开关
    enable_circuit_breaker: bool = True
    enable_rate_limiter: bool = True
    enable_retry_handler: bool = True
    enable_load_balancer: bool = True
    
    # 组件配置
    circuit_breaker_config: CircuitBreakerConfig = None
    rate_limiter_config: RateLimitConfig = None
    retry_handler_config: RetryConfig = None
    load_balancer_config: LoadBalancerConfig = None
    
    # 监控配置
    metrics_collection_interval: float = 60.0      # 指标收集间隔(秒)
    enable_detailed_metrics: bool = True           # 启用详细指标
    
    # 告警配置
    enable_alerts: bool = True                     # 启用告警
    alert_thresholds: Dict[str, float] = None      # 告警阈值


class ReliabilityManager:
    """企业级可靠性管理器"""
    
    def __init__(self, name: str, config: ReliabilityConfig = None):
        self.name = name
        self.config = config or ReliabilityConfig()
        
        # 初始化组件
        self.circuit_breaker = None
        self.rate_limiter = None
        self.retry_handler = None
        self.load_balancer = None
        
        # 监控指标
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "circuit_breaker_trips": 0,
            "rate_limit_rejections": 0,
            "retry_attempts": 0,
            "load_balancer_switches": 0,
            "average_response_time": 0.0,
            "system_health_score": 1.0
        }
        
        # 告警状态
        self.alerts = []
        self.alert_history = []
        
        # 任务管理
        self.background_tasks = []
        self.is_running = False
        
        self._lock = asyncio.Lock()
        
        # 设置默认告警阈值
        if self.config.alert_thresholds is None:
            self.config.alert_thresholds = {
                "failure_rate": 0.1,           # 10%失败率
                "response_time": 2.0,          # 2秒响应时间
                "circuit_breaker_trips": 5,    # 5次熔断
                "rate_limit_rejections": 100   # 100次限流拒绝
            }
        
        logger.info(f"可靠性管理器 '{name}' 初始化完成")
    
    async def initialize(self):
        """初始化所有组件"""
        # 初始化熔断器
        if self.config.enable_circuit_breaker:
            cb_config = self.config.circuit_breaker_config or CircuitBreakerConfig()
            self.circuit_breaker = CircuitBreaker(f"{self.name}_circuit_breaker", cb_config)
            logger.info("熔断器组件已初始化")
        
        # 初始化限流器
        if self.config.enable_rate_limiter:
            rl_config = self.config.rate_limiter_config or RateLimitConfig()
            self.rate_limiter = RateLimiter(f"{self.name}_rate_limiter", rl_config)
            logger.info("限流器组件已初始化")
        
        # 初始化重试处理器
        if self.config.enable_retry_handler:
            retry_config = self.config.retry_handler_config or RetryConfig()
            self.retry_handler = RetryHandler(f"{self.name}_retry_handler", retry_config)
            logger.info("重试处理器组件已初始化")
        
        # 初始化负载均衡器
        if self.config.enable_load_balancer:
            lb_config = self.config.load_balancer_config or LoadBalancerConfig()
            self.load_balancer = LoadBalancer(f"{self.name}_load_balancer", lb_config)
            logger.info("负载均衡器组件已初始化")
    
    async def start(self):
        """启动可靠性管理器"""
        if self.is_running:
            return
        
        await self.initialize()
        
        # 启动负载均衡器健康检查
        if self.load_balancer:
            await self.load_balancer.start_health_checks()
        
        # 启动后台任务
        self.background_tasks = [
            asyncio.create_task(self._metrics_collection_loop()),
            asyncio.create_task(self._alert_monitoring_loop())
        ]
        
        self.is_running = True
        logger.info(f"可靠性管理器 '{self.name}' 已启动")
    
    async def stop(self):
        """停止可靠性管理器"""
        if not self.is_running:
            return
        
        # 停止后台任务
        for task in self.background_tasks:
            task.cancel()
        
        # 等待任务完成
        await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # 停止负载均衡器
        if self.load_balancer:
            await self.load_balancer.shutdown()
        
        self.is_running = False
        logger.info(f"可靠性管理器 '{self.name}' 已停止")
    
    async def execute_with_protection(self, 
                                    func: Callable, 
                                    *args, 
                                    priority: RequestPriority = RequestPriority.NORMAL,
                                    fallback: Optional[Callable] = None,
                                    **kwargs) -> Any:
        """
        执行受保护的函数调用
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            priority: 请求优先级
            fallback: 降级函数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
        """
        start_time = time.time()
        
        try:
            # 1. 限流检查
            if self.rate_limiter:
                if not await self.rate_limiter.acquire(priority):
                    async with self._lock:
                        self.metrics["rate_limit_rejections"] += 1
                    raise Exception("请求被限流拒绝")
            
            # 2. 负载均衡选择实例
            selected_instance = None
            if self.load_balancer:
                selected_instance = await self.load_balancer.select_instance()
                if not selected_instance:
                    raise Exception("没有可用的服务实例")
            
            # 3. 熔断器保护执行
            if self.circuit_breaker:
                if self.retry_handler:
                    # 结合重试机制
                    async def protected_func():
                        return await self.circuit_breaker.call(func, *args, fallback=fallback, **kwargs)
                    
                    result = await self.retry_handler.execute_with_retry(protected_func)
                else:
                    result = await self.circuit_breaker.call(func, *args, fallback=fallback, **kwargs)
            else:
                # 仅使用重试机制
                if self.retry_handler:
                    result = await self.retry_handler.execute_with_retry(func, *args, **kwargs)
                else:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
            
            # 记录成功
            response_time = time.time() - start_time
            await self._record_success(response_time, selected_instance)
            
            return result
            
        except Exception as e:
            # 记录失败
            response_time = time.time() - start_time
            await self._record_failure(response_time, selected_instance, e)
            raise e
    
    async def _record_success(self, response_time: float, instance: Optional[InstanceInfo]):
        """记录成功请求"""
        async with self._lock:
            self.metrics["total_requests"] += 1
            self.metrics["successful_requests"] += 1
            
            # 更新平均响应时间
            total_requests = self.metrics["total_requests"]
            current_avg = self.metrics["average_response_time"]
            self.metrics["average_response_time"] = (
                (current_avg * (total_requests - 1) + response_time) / total_requests
            )
        
        # 释放负载均衡器实例
        if self.load_balancer and instance:
            await self.load_balancer.release_instance(instance.id, response_time, True)
    
    async def _record_failure(self, response_time: float, instance: Optional[InstanceInfo], error: Exception):
        """记录失败请求"""
        async with self._lock:
            self.metrics["total_requests"] += 1
            self.metrics["failed_requests"] += 1
            
            # 更新平均响应时间
            total_requests = self.metrics["total_requests"]
            current_avg = self.metrics["average_response_time"]
            self.metrics["average_response_time"] = (
                (current_avg * (total_requests - 1) + response_time) / total_requests
            )
        
        # 释放负载均衡器实例
        if self.load_balancer and instance:
            await self.load_balancer.release_instance(instance.id, response_time, False)
    
    async def add_instance(self, instance: InstanceInfo):
        """添加服务实例"""
        if self.load_balancer:
            await self.load_balancer.add_instance(instance)
            logger.info(f"添加服务实例: {instance.id}")
    
    async def remove_instance(self, instance_id: str):
        """移除服务实例"""
        if self.load_balancer:
            await self.load_balancer.remove_instance(instance_id)
            logger.info(f"移除服务实例: {instance_id}")
    
    async def _metrics_collection_loop(self):
        """指标收集循环"""
        while True:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.config.metrics_collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标收集错误: {e}")
                await asyncio.sleep(5)
    
    async def _collect_metrics(self):
        """收集所有组件的指标"""
        async with self._lock:
            # 收集熔断器指标
            if self.circuit_breaker:
                cb_metrics = self.circuit_breaker.get_metrics()
                self.metrics["circuit_breaker_trips"] = cb_metrics.get("circuit_opened_count", 0)
            
            # 收集限流器指标
            if self.rate_limiter:
                rl_metrics = self.rate_limiter.get_metrics()
                self.metrics["rate_limit_rejections"] = rl_metrics.get("rejected_requests", 0)
            
            # 收集重试处理器指标
            if self.retry_handler:
                retry_metrics = self.retry_handler.get_metrics()
                self.metrics["retry_attempts"] = retry_metrics.get("retry_attempts", 0)
            
            # 收集负载均衡器指标
            if self.load_balancer:
                lb_metrics = self.load_balancer.get_metrics()
                self.metrics["load_balancer_switches"] = lb_metrics.get("strategy_switches", 0)
            
            # 计算系统健康分数
            self.metrics["system_health_score"] = self._calculate_health_score()
    
    def _calculate_health_score(self) -> float:
        """计算系统健康分数 (0-1)"""
        score = 1.0
        
        # 基于失败率调整
        total_requests = self.metrics["total_requests"]
        if total_requests > 0:
            failure_rate = self.metrics["failed_requests"] / total_requests
            score *= (1 - failure_rate)
        
        # 基于响应时间调整
        avg_response_time = self.metrics["average_response_time"]
        if avg_response_time > 1.0:
            score *= max(0.1, 1.0 - (avg_response_time - 1.0) / 10.0)
        
        # 基于熔断器状态调整
        if self.circuit_breaker and self.circuit_breaker.state.value == "open":
            score *= 0.5
        
        return max(0.0, min(1.0, score))
    
    async def _alert_monitoring_loop(self):
        """告警监控循环"""
        if not self.config.enable_alerts:
            return
        
        while True:
            try:
                await self._check_alerts()
                await asyncio.sleep(30)  # 每30秒检查一次告警
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"告警监控错误: {e}")
                await asyncio.sleep(5)
    
    async def _check_alerts(self):
        """检查告警条件"""
        current_alerts = []
        
        # 检查失败率告警
        total_requests = self.metrics["total_requests"]
        if total_requests > 0:
            failure_rate = self.metrics["failed_requests"] / total_requests
            if failure_rate > self.config.alert_thresholds["failure_rate"]:
                current_alerts.append({
                    "type": "high_failure_rate",
                    "message": f"失败率过高: {failure_rate:.2%}",
                    "severity": "critical",
                    "timestamp": time.time()
                })
        
        # 检查响应时间告警
        avg_response_time = self.metrics["average_response_time"]
        if avg_response_time > self.config.alert_thresholds["response_time"]:
            current_alerts.append({
                "type": "high_response_time",
                "message": f"响应时间过长: {avg_response_time:.2f}s",
                "severity": "warning",
                "timestamp": time.time()
            })
        
        # 检查熔断器告警
        circuit_trips = self.metrics["circuit_breaker_trips"]
        if circuit_trips > self.config.alert_thresholds["circuit_breaker_trips"]:
            current_alerts.append({
                "type": "frequent_circuit_trips",
                "message": f"熔断器频繁触发: {circuit_trips}次",
                "severity": "warning",
                "timestamp": time.time()
            })
        
        # 更新告警状态
        async with self._lock:
            self.alerts = current_alerts
            self.alert_history.extend(current_alerts)
            
            # 保持告警历史在合理范围内
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-500:]
        
        # 记录告警
        for alert in current_alerts:
            logger.warning(f"可靠性告警: {alert['message']}")
    
    def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """获取综合指标"""
        result = {
            "manager_metrics": self.metrics.copy(),
            "alerts": {
                "current": self.alerts.copy(),
                "history_count": len(self.alert_history)
            },
            "component_metrics": {}
        }
        
        # 添加各组件的详细指标
        if self.circuit_breaker:
            result["component_metrics"]["circuit_breaker"] = self.circuit_breaker.get_metrics()
        
        if self.rate_limiter:
            result["component_metrics"]["rate_limiter"] = self.rate_limiter.get_metrics()
        
        if self.retry_handler:
            result["component_metrics"]["retry_handler"] = self.retry_handler.get_metrics()
        
        if self.load_balancer:
            result["component_metrics"]["load_balancer"] = self.load_balancer.get_metrics()
        
        return result
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        return {
            "overall_health": self.metrics["system_health_score"],
            "status": "healthy" if self.metrics["system_health_score"] > 0.8 else 
                     "degraded" if self.metrics["system_health_score"] > 0.5 else "unhealthy",
            "active_alerts": len(self.alerts),
            "components": {
                "circuit_breaker": {
                    "enabled": self.config.enable_circuit_breaker,
                    "status": self.circuit_breaker.state.value if self.circuit_breaker else "disabled"
                },
                "rate_limiter": {
                    "enabled": self.config.enable_rate_limiter,
                    "current_load": self.rate_limiter.metrics.get("current_load", 0) if self.rate_limiter else 0
                },
                "retry_handler": {
                    "enabled": self.config.enable_retry_handler,
                    "success_rate": self.retry_handler.metrics.get("success_rate", 0) if self.retry_handler else 0
                },
                "load_balancer": {
                    "enabled": self.config.enable_load_balancer,
                    "healthy_instances": self.load_balancer.metrics.get("healthy_instance_count", 0) if self.load_balancer else 0
                }
            }
        }


# 使用示例
if __name__ == "__main__":
    async def example_usage():
        # 创建可靠性管理器配置
        config = ReliabilityConfig(
            enable_circuit_breaker=True,
            enable_rate_limiter=True,
            enable_retry_handler=True,
            enable_load_balancer=True,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            rate_limiter_config=RateLimitConfig(max_requests_per_second=10.0),
            retry_handler_config=RetryConfig(max_attempts=3),
            load_balancer_config=LoadBalancerConfig()
        )
        
        # 创建可靠性管理器
        manager = ReliabilityManager("api_manager", config)
        
        # 启动管理器
        await manager.start()
        
        # 添加服务实例
        instances = [
            InstanceInfo("service1", "192.168.1.10", 8080),
            InstanceInfo("service2", "192.168.1.11", 8080),
            InstanceInfo("service3", "192.168.1.12", 8080)
        ]
        
        for instance in instances:
            await manager.add_instance(instance)
        
        # 模拟API调用
        async def api_call():
            import random
            if random.random() < 0.2:  # 20%失败率
                raise Exception("API调用失败")
            await asyncio.sleep(random.uniform(0.1, 0.5))  # 模拟处理时间
            return {"status": "success", "data": "response"}
        
        # 降级函数
        async def fallback():
            return {"status": "fallback", "data": "cached_response"}
        
        # 执行受保护的调用
        for i in range(20):
            try:
                result = await manager.execute_with_protection(
                    api_call,
                    priority=RequestPriority.NORMAL,
                    fallback=fallback
                )
                print(f"调用 {i+1}: {result}")
            except Exception as e:
                print(f"调用 {i+1} 失败: {e}")
            
            await asyncio.sleep(0.5)
        
        # 等待指标收集
        await asyncio.sleep(5)
        
        # 打印综合指标
        print("\n=== 综合指标 ===")
        metrics = manager.get_comprehensive_metrics()
        print(f"管理器指标: {metrics['manager_metrics']}")
        
        print("\n=== 健康状态 ===")
        health = manager.get_health_status()
        print(f"整体健康: {health}")
        
        # 停止管理器
        await manager.stop()
    
    # 运行示例
    asyncio.run(example_usage()) 