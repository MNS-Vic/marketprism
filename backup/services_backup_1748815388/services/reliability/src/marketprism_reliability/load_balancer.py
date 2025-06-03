"""
企业级负载均衡系统

实现多种负载均衡算法、健康检查和自动故障转移
提供实例管理、性能监控和智能路由功能
"""

import asyncio
import time
import random
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import deque, defaultdict
import statistics

logger = logging.getLogger(__name__)


class LoadBalancingStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"                     # 轮询
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"   # 加权轮询
    LEAST_CONNECTIONS = "least_connections"         # 最少连接
    WEIGHTED_LEAST_CONNECTIONS = "weighted_least_connections"  # 加权最少连接
    RANDOM = "random"                               # 随机
    WEIGHTED_RANDOM = "weighted_random"             # 加权随机
    RESPONSE_TIME = "response_time"                 # 响应时间
    HEALTH_AWARE = "health_aware"                   # 健康感知
    ADAPTIVE = "adaptive"                           # 自适应


class InstanceStatus(Enum):
    """实例状态"""
    HEALTHY = "healthy"         # 健康
    UNHEALTHY = "unhealthy"     # 不健康
    DRAINING = "draining"       # 排水中
    MAINTENANCE = "maintenance" # 维护中


@dataclass
class InstanceInfo:
    """实例信息"""
    id: str                                         # 实例ID
    host: str                                       # 主机地址
    port: int                                       # 端口
    weight: float = 1.0                            # 权重
    max_connections: int = 100                      # 最大连接数
    
    # 运行时状态
    status: InstanceStatus = InstanceStatus.HEALTHY
    current_connections: int = 0                    # 当前连接数
    total_requests: int = 0                         # 总请求数
    successful_requests: int = 0                    # 成功请求数
    failed_requests: int = 0                        # 失败请求数
    
    # 性能指标
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    last_health_check: float = 0.0                 # 上次健康检查时间
    consecutive_failures: int = 0                   # 连续失败次数
    
    def __post_init__(self):
        if not isinstance(self.response_times, deque):
            self.response_times = deque(maxlen=100)
    
    @property
    def average_response_time(self) -> float:
        """平均响应时间"""
        return statistics.mean(self.response_times) if self.response_times else 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.successful_requests + self.failed_requests
        return self.successful_requests / total if total > 0 else 1.0
    
    @property
    def load_factor(self) -> float:
        """负载因子"""
        return self.current_connections / self.max_connections if self.max_connections > 0 else 0.0
    
    @property
    def is_available(self) -> bool:
        """是否可用"""
        return (self.status == InstanceStatus.HEALTHY and 
                self.current_connections < self.max_connections)


@dataclass
class LoadBalancerConfig:
    """负载均衡器配置"""
    strategy: LoadBalancingStrategy = LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN
    health_check_interval: float = 30.0             # 健康检查间隔(秒)
    health_check_timeout: float = 5.0               # 健康检查超时(秒)
    max_failures: int = 3                           # 最大失败次数
    recovery_time: float = 60.0                     # 恢复时间(秒)
    
    # 自适应配置
    enable_adaptive: bool = True                    # 启用自适应
    adaptation_interval: float = 60.0               # 自适应间隔(秒)
    performance_window: int = 100                   # 性能窗口大小
    
    # 连接管理
    connection_timeout: float = 30.0                # 连接超时(秒)
    max_retries: int = 3                           # 最大重试次数


class LoadBalancer:
    """企业级负载均衡器"""
    
    def __init__(self, name: str, config: LoadBalancerConfig = None):
        self.name = name
        self.config = config or LoadBalancerConfig()
        
        # 实例管理
        self.instances: Dict[str, InstanceInfo] = {}
        self.healthy_instances: List[str] = []
        
        # 负载均衡状态
        self.current_index = 0                      # 轮询索引
        self.weighted_list: List[str] = []          # 加权列表
        
        # 监控指标
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time": 0.0,
            "instance_count": 0,
            "healthy_instance_count": 0,
            "load_distribution": {},
            "strategy_switches": 0
        }
        
        # 自适应参数
        self.current_strategy = self.config.strategy
        self.last_adaptation = time.time()
        self.performance_history = deque(maxlen=self.config.performance_window)
        
        # 健康检查
        self.health_check_task = None
        self.health_check_callbacks: List[Callable] = []
        
        self._lock = asyncio.Lock()
        
        logger.info(f"负载均衡器 '{name}' 初始化完成，策略: {self.config.strategy.value}")
    
    async def add_instance(self, instance: InstanceInfo):
        """添加实例"""
        async with self._lock:
            self.instances[instance.id] = instance
            if instance.is_available:
                self.healthy_instances.append(instance.id)
            
            await self._rebuild_weighted_list()
            self.metrics["instance_count"] = len(self.instances)
            self.metrics["healthy_instance_count"] = len(self.healthy_instances)
            
            logger.info(f"负载均衡器 '{self.name}' 添加实例: {instance.id} ({instance.host}:{instance.port})")
    
    async def remove_instance(self, instance_id: str):
        """移除实例"""
        async with self._lock:
            if instance_id in self.instances:
                del self.instances[instance_id]
                
                if instance_id in self.healthy_instances:
                    self.healthy_instances.remove(instance_id)
                
                await self._rebuild_weighted_list()
                self.metrics["instance_count"] = len(self.instances)
                self.metrics["healthy_instance_count"] = len(self.healthy_instances)
                
                logger.info(f"负载均衡器 '{self.name}' 移除实例: {instance_id}")
    
    async def select_instance(self, request_context: Dict[str, Any] = None) -> Optional[InstanceInfo]:
        """
        选择实例
        
        Args:
            request_context: 请求上下文
            
        Returns:
            选中的实例信息
        """
        async with self._lock:
            if not self.healthy_instances:
                logger.warning(f"负载均衡器 '{self.name}' 没有可用实例")
                return None
            
            # 自适应策略调整
            if self.config.enable_adaptive:
                await self._adaptive_strategy_adjustment()
            
            # 根据策略选择实例
            instance_id = await self._select_by_strategy(request_context)
            
            if instance_id and instance_id in self.instances:
                instance = self.instances[instance_id]
                
                # 更新连接计数
                instance.current_connections += 1
                instance.total_requests += 1
                
                self.metrics["total_requests"] += 1
                
                return instance
            
            return None
    
    async def _select_by_strategy(self, request_context: Dict[str, Any] = None) -> Optional[str]:
        """根据策略选择实例"""
        if self.current_strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._round_robin()
        
        elif self.current_strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin()
        
        elif self.current_strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections()
        
        elif self.current_strategy == LoadBalancingStrategy.WEIGHTED_LEAST_CONNECTIONS:
            return self._weighted_least_connections()
        
        elif self.current_strategy == LoadBalancingStrategy.RANDOM:
            return self._random()
        
        elif self.current_strategy == LoadBalancingStrategy.WEIGHTED_RANDOM:
            return self._weighted_random()
        
        elif self.current_strategy == LoadBalancingStrategy.RESPONSE_TIME:
            return self._response_time_based()
        
        elif self.current_strategy == LoadBalancingStrategy.HEALTH_AWARE:
            return self._health_aware()
        
        elif self.current_strategy == LoadBalancingStrategy.ADAPTIVE:
            return await self._adaptive_selection(request_context)
        
        else:
            return self._round_robin()
    
    def _round_robin(self) -> str:
        """轮询算法"""
        if not self.healthy_instances:
            return None
        
        instance_id = self.healthy_instances[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.healthy_instances)
        return instance_id
    
    def _weighted_round_robin(self) -> str:
        """加权轮询算法"""
        if not self.weighted_list:
            return self._round_robin()
        
        instance_id = self.weighted_list[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.weighted_list)
        return instance_id
    
    def _least_connections(self) -> str:
        """最少连接算法"""
        if not self.healthy_instances:
            return None
        
        min_connections = float('inf')
        selected_instance = None
        
        for instance_id in self.healthy_instances:
            instance = self.instances[instance_id]
            if instance.current_connections < min_connections:
                min_connections = instance.current_connections
                selected_instance = instance_id
        
        return selected_instance
    
    def _weighted_least_connections(self) -> str:
        """加权最少连接算法"""
        if not self.healthy_instances:
            return None
        
        min_ratio = float('inf')
        selected_instance = None
        
        for instance_id in self.healthy_instances:
            instance = self.instances[instance_id]
            ratio = instance.current_connections / instance.weight if instance.weight > 0 else float('inf')
            
            if ratio < min_ratio:
                min_ratio = ratio
                selected_instance = instance_id
        
        return selected_instance
    
    def _random(self) -> str:
        """随机算法"""
        if not self.healthy_instances:
            return None
        
        return random.choice(self.healthy_instances)
    
    def _weighted_random(self) -> str:
        """加权随机算法"""
        if not self.weighted_list:
            return self._random()
        
        return random.choice(self.weighted_list)
    
    def _response_time_based(self) -> str:
        """基于响应时间的算法"""
        if not self.healthy_instances:
            return None
        
        min_response_time = float('inf')
        selected_instance = None
        
        for instance_id in self.healthy_instances:
            instance = self.instances[instance_id]
            avg_time = instance.average_response_time
            
            if avg_time < min_response_time:
                min_response_time = avg_time
                selected_instance = instance_id
        
        return selected_instance or self.healthy_instances[0]
    
    def _health_aware(self) -> str:
        """健康感知算法"""
        if not self.healthy_instances:
            return None
        
        # 计算综合得分：成功率 * 权重 / (响应时间 + 1) / (负载因子 + 0.1)
        best_score = -1
        selected_instance = None
        
        for instance_id in self.healthy_instances:
            instance = self.instances[instance_id]
            
            score = (instance.success_rate * instance.weight / 
                    (instance.average_response_time + 1) / 
                    (instance.load_factor + 0.1))
            
            if score > best_score:
                best_score = score
                selected_instance = instance_id
        
        return selected_instance or self.healthy_instances[0]
    
    async def _adaptive_selection(self, request_context: Dict[str, Any] = None) -> str:
        """自适应选择算法"""
        # 根据当前系统状态选择最优策略
        if len(self.healthy_instances) <= 2:
            return self._round_robin()
        
        # 分析性能历史
        if len(self.performance_history) >= 10:
            recent_performance = list(self.performance_history)[-10:]
            avg_response_time = statistics.mean(recent_performance)
            
            if avg_response_time > 1.0:  # 响应时间较高
                return self._least_connections()
            elif avg_response_time < 0.1:  # 响应时间很低
                return self._weighted_round_robin()
        
        return self._health_aware()
    
    async def release_instance(self, instance_id: str, response_time: float, success: bool):
        """释放实例连接"""
        async with self._lock:
            if instance_id in self.instances:
                instance = self.instances[instance_id]
                
                # 更新连接计数
                instance.current_connections = max(0, instance.current_connections - 1)
                
                # 记录性能指标
                instance.response_times.append(response_time)
                self.performance_history.append(response_time)
                
                if success:
                    instance.successful_requests += 1
                    instance.consecutive_failures = 0
                    self.metrics["successful_requests"] += 1
                else:
                    instance.failed_requests += 1
                    instance.consecutive_failures += 1
                    self.metrics["failed_requests"] += 1
                    
                    # 检查是否需要标记为不健康
                    if instance.consecutive_failures >= self.config.max_failures:
                        await self._mark_instance_unhealthy(instance_id)
                
                # 更新负载分布统计
                if instance_id not in self.metrics["load_distribution"]:
                    self.metrics["load_distribution"][instance_id] = 0
                self.metrics["load_distribution"][instance_id] += 1
                
                # 更新平均响应时间
                if self.performance_history:
                    self.metrics["average_response_time"] = statistics.mean(self.performance_history)
    
    async def _mark_instance_unhealthy(self, instance_id: str):
        """标记实例为不健康"""
        if instance_id in self.instances:
            instance = self.instances[instance_id]
            instance.status = InstanceStatus.UNHEALTHY
            
            if instance_id in self.healthy_instances:
                self.healthy_instances.remove(instance_id)
                await self._rebuild_weighted_list()
                self.metrics["healthy_instance_count"] = len(self.healthy_instances)
            
            logger.warning(f"实例 {instance_id} 被标记为不健康")
    
    async def _mark_instance_healthy(self, instance_id: str):
        """标记实例为健康"""
        if instance_id in self.instances:
            instance = self.instances[instance_id]
            instance.status = InstanceStatus.HEALTHY
            instance.consecutive_failures = 0
            
            if instance_id not in self.healthy_instances:
                self.healthy_instances.append(instance_id)
                await self._rebuild_weighted_list()
                self.metrics["healthy_instance_count"] = len(self.healthy_instances)
            
            logger.info(f"实例 {instance_id} 恢复健康")
    
    async def _rebuild_weighted_list(self):
        """重建加权列表"""
        self.weighted_list.clear()
        
        for instance_id in self.healthy_instances:
            instance = self.instances[instance_id]
            weight = max(1, int(instance.weight * 10))  # 权重放大10倍
            
            for _ in range(weight):
                self.weighted_list.append(instance_id)
        
        # 重置索引
        self.current_index = 0
    
    async def start_health_checks(self):
        """启动健康检查"""
        if self.health_check_task is None:
            self.health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info(f"负载均衡器 '{self.name}' 启动健康检查")
    
    async def stop_health_checks(self):
        """停止健康检查"""
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
            self.health_check_task = None
            logger.info(f"负载均衡器 '{self.name}' 停止健康检查")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")
                await asyncio.sleep(5)  # 错误后短暂等待
    
    async def _perform_health_checks(self):
        """执行健康检查"""
        for instance_id, instance in self.instances.items():
            try:
                # 执行健康检查回调
                is_healthy = True
                for callback in self.health_check_callbacks:
                    if not await callback(instance):
                        is_healthy = False
                        break
                
                instance.last_health_check = time.time()
                
                if is_healthy and instance.status == InstanceStatus.UNHEALTHY:
                    # 检查是否可以恢复
                    if time.time() - instance.last_health_check >= self.config.recovery_time:
                        await self._mark_instance_healthy(instance_id)
                
            except Exception as e:
                logger.error(f"实例 {instance_id} 健康检查失败: {e}")
                await self._mark_instance_unhealthy(instance_id)
    
    def add_health_check_callback(self, callback: Callable):
        """添加健康检查回调"""
        self.health_check_callbacks.append(callback)
    
    async def _adaptive_strategy_adjustment(self):
        """自适应策略调整"""
        now = time.time()
        if now - self.last_adaptation < self.config.adaptation_interval:
            return
        
        if len(self.performance_history) < 50:  # 数据不足
            return
        
        # 分析性能趋势
        recent_performance = list(self.performance_history)[-50:]
        avg_response_time = statistics.mean(recent_performance)
        response_time_std = statistics.stdev(recent_performance) if len(recent_performance) > 1 else 0
        
        # 根据性能指标调整策略
        old_strategy = self.current_strategy
        
        if avg_response_time > 2.0 and response_time_std > 1.0:
            # 高延迟且不稳定，使用最少连接
            self.current_strategy = LoadBalancingStrategy.LEAST_CONNECTIONS
        elif avg_response_time < 0.1:
            # 低延迟，使用加权轮询
            self.current_strategy = LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN
        else:
            # 中等性能，使用健康感知
            self.current_strategy = LoadBalancingStrategy.HEALTH_AWARE
        
        if old_strategy != self.current_strategy:
            self.metrics["strategy_switches"] += 1
            logger.info(f"负载均衡器 '{self.name}' 策略调整: {old_strategy.value} -> {self.current_strategy.value}")
        
        self.last_adaptation = now
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        instance_metrics = {}
        for instance_id, instance in self.instances.items():
            instance_metrics[instance_id] = {
                "status": instance.status.value,
                "current_connections": instance.current_connections,
                "total_requests": instance.total_requests,
                "success_rate": instance.success_rate,
                "average_response_time": instance.average_response_time,
                "load_factor": instance.load_factor
            }
        
        return {
            **self.metrics,
            "current_strategy": self.current_strategy.value,
            "instances": instance_metrics,
            "config": {
                "strategy": self.config.strategy.value,
                "health_check_interval": self.config.health_check_interval,
                "max_failures": self.config.max_failures
            }
        }
    
    async def shutdown(self):
        """关闭负载均衡器"""
        await self.stop_health_checks()
        logger.info(f"负载均衡器 '{self.name}' 已关闭")


# 使用示例
if __name__ == "__main__":
    async def example_usage():
        # 创建负载均衡器配置
        config = LoadBalancerConfig(
            strategy=LoadBalancingStrategy.ADAPTIVE,
            health_check_interval=10.0,
            enable_adaptive=True
        )
        
        # 创建负载均衡器
        lb = LoadBalancer("api_balancer", config)
        
        # 添加实例
        instances = [
            InstanceInfo("instance1", "192.168.1.10", 8080, weight=1.0),
            InstanceInfo("instance2", "192.168.1.11", 8080, weight=1.5),
            InstanceInfo("instance3", "192.168.1.12", 8080, weight=0.8)
        ]
        
        for instance in instances:
            await lb.add_instance(instance)
        
        # 添加健康检查回调
        async def health_check(instance: InstanceInfo) -> bool:
            # 模拟健康检查
            return random.random() > 0.1  # 90%健康率
        
        lb.add_health_check_callback(health_check)
        
        # 启动健康检查
        await lb.start_health_checks()
        
        # 模拟请求
        for i in range(20):
            instance = await lb.select_instance()
            if instance:
                # 模拟请求处理
                response_time = random.uniform(0.1, 2.0)
                success = random.random() > 0.1  # 90%成功率
                
                print(f"请求 {i+1}: 选择实例 {instance.id}, 响应时间: {response_time:.3f}s, 成功: {success}")
                
                # 模拟处理时间
                await asyncio.sleep(0.1)
                
                # 释放实例
                await lb.release_instance(instance.id, response_time, success)
            else:
                print(f"请求 {i+1}: 没有可用实例")
        
        # 等待一段时间观察健康检查
        await asyncio.sleep(5)
        
        # 打印指标
        print("\n负载均衡器指标:")
        metrics = lb.get_metrics()
        for key, value in metrics.items():
            if key != "instances":
                print(f"  {key}: {value}")
        
        print("\n实例指标:")
        for instance_id, instance_metrics in metrics["instances"].items():
            print(f"  {instance_id}: {instance_metrics}")
        
        # 关闭
        await lb.shutdown()
    
    # 运行示例
    asyncio.run(example_usage()) 