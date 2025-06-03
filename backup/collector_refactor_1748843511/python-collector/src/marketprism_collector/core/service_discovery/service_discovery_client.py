"""服务发现客户端 (Service Discovery Client)

实现智能服务发现机制，提供：
- 多种负载均衡策略
- 服务实例缓存和故障转移
- 健康检查集成
- 熔断器模式
- 自动重试机制
"""

import asyncio
import random
import time
import hashlib
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime, timedelta
import logging
from collections import defaultdict

from .service_registry import ServiceInstance, ServiceRegistry, ServiceStatus


class LoadBalanceStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"                 # 轮询
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"  # 加权轮询
    LEAST_CONNECTIONS = "least_connections"     # 最少连接
    RANDOM = "random"                          # 随机
    IP_HASH = "ip_hash"                        # IP哈希


class CircuitBreakerState(Enum):
    """熔断器状态"""
    CLOSED = "closed"         # 关闭（正常）
    OPEN = "open"             # 开启（熔断）
    HALF_OPEN = "half_open"   # 半开（探测）


@dataclass
class DiscoveryConfig:
    """服务发现配置"""
    service_name: str                                    # 服务名称
    load_balance_strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN  # 负载均衡策略
    cache_ttl: int = 60                                 # 缓存TTL(秒)
    health_check_enabled: bool = True                   # 是否启用健康检查
    circuit_breaker_enabled: bool = True               # 是否启用熔断器
    failure_threshold: int = 5                          # 失败阈值
    recovery_timeout: int = 30                          # 恢复超时时间(秒)
    max_retries: int = 3                               # 最大重试次数
    retry_delay: float = 1.0                           # 重试延迟(秒)
    timeout: float = 10.0                              # 请求超时时间(秒)
    tags: Optional[set] = field(default_factory=set)   # 标签过滤


@dataclass
class CircuitBreaker:
    """熔断器"""
    failure_count: int = 0                             # 失败计数
    last_failure_time: Optional[datetime] = None      # 最后失败时间
    state: CircuitBreakerState = CircuitBreakerState.CLOSED  # 状态
    success_count: int = 0                             # 成功计数（半开状态下）


@dataclass
class RequestResult:
    """请求结果"""
    success: bool                                      # 是否成功
    response_time: float                               # 响应时间
    error: Optional[Exception] = None                  # 错误信息
    instance: Optional[ServiceInstance] = None         # 服务实例


class ServiceDiscoveryClient:
    """服务发现客户端
    
    提供智能服务发现功能：
    - 多种负载均衡策略
    - 服务实例缓存和故障转移
    - 健康检查集成
    - 熔断器模式
    - 自动重试机制
    """
    
    def __init__(self, registry: ServiceRegistry, config: DiscoveryConfig):
        """初始化服务发现客户端
        
        Args:
            registry: 服务注册中心
            config: 发现配置
        """
        self.registry = registry
        self.config = config
        
        # 缓存
        self._cache: List[ServiceInstance] = []
        self._cache_updated_at: Optional[datetime] = None
        self._cache_lock = threading.RLock()
        
        # 负载均衡状态
        self._round_robin_index = 0
        self._connection_counts: Dict[str, int] = defaultdict(int)
        
        # 熔断器
        self._circuit_breakers: Dict[str, CircuitBreaker] = defaultdict(CircuitBreaker)
        
        # 统计信息
        self._stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'circuit_breaker_trips': 0,
            'retries_performed': 0
        }
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def discover_instance(self, client_ip: Optional[str] = None) -> Optional[ServiceInstance]:
        """发现服务实例
        
        Args:
            client_ip: 客户端IP（用于IP哈希负载均衡）
            
        Returns:
            Optional[ServiceInstance]: 服务实例
        """
        instances = await self._get_available_instances()
        
        if not instances:
            self.logger.warning(f"No available instances for service: {self.config.service_name}")
            return None
        
        # 选择实例
        instance = self._select_instance(instances, client_ip)
        
        if instance and self.config.circuit_breaker_enabled:
            # 检查熔断器状态
            circuit_breaker = self._circuit_breakers[instance.instance_id]
            if not self._is_circuit_breaker_allowed(circuit_breaker):
                self.logger.warning(f"Circuit breaker is open for instance: {instance.instance_id}")
                # 尝试获取其他实例
                other_instances = [inst for inst in instances if inst.instance_id != instance.instance_id]
                if other_instances:
                    instance = self._select_instance(other_instances, client_ip)
                else:
                    return None
        
        return instance
    
    async def make_request(self, 
                          request_func: Callable[[ServiceInstance], Any],
                          client_ip: Optional[str] = None) -> RequestResult:
        """发起请求
        
        Args:
            request_func: 请求函数
            client_ip: 客户端IP
            
        Returns:
            RequestResult: 请求结果
        """
        self._stats['total_requests'] += 1
        
        for attempt in range(self.config.max_retries + 1):
            instance = await self.discover_instance(client_ip)
            
            if not instance:
                return RequestResult(
                    success=False,
                    response_time=0.0,
                    error=Exception("No available instances")
                )
            
            start_time = time.time()
            
            try:
                # 更新连接计数
                with self._lock:
                    self._connection_counts[instance.instance_id] += 1
                
                # 发起请求
                result = await self._execute_request(request_func, instance)
                response_time = time.time() - start_time
                
                # 记录成功
                self._record_success(instance, response_time)
                self._stats['successful_requests'] += 1
                
                return RequestResult(
                    success=True,
                    response_time=response_time,
                    instance=instance
                )
                
            except Exception as e:
                response_time = time.time() - start_time
                
                # 记录失败
                self._record_failure(instance, e, response_time)
                self._stats['failed_requests'] += 1
                
                # 如果是最后一次尝试，返回失败结果
                if attempt == self.config.max_retries:
                    return RequestResult(
                        success=False,
                        response_time=response_time,
                        error=e,
                        instance=instance
                    )
                
                # 等待重试
                self._stats['retries_performed'] += 1
                await asyncio.sleep(self.config.retry_delay)
                
            finally:
                # 更新连接计数
                with self._lock:
                    self._connection_counts[instance.instance_id] -= 1
    
    async def _get_available_instances(self) -> List[ServiceInstance]:
        """获取可用实例列表"""
        with self._cache_lock:
            # 检查缓存是否有效
            if self._is_cache_valid():
                self._stats['cache_hits'] += 1
                return self._cache.copy()
            
            # 从注册中心获取最新实例
            self._stats['cache_misses'] += 1
            instances = self.registry.discover_services(
                service_name=self.config.service_name,
                healthy_only=self.config.health_check_enabled,
                tags=self.config.tags
            )
            
            # 更新缓存
            self._cache = instances
            self._cache_updated_at = datetime.now()
            
            return instances.copy()
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self._cache_updated_at:
            return False
        
        cache_age = (datetime.now() - self._cache_updated_at).total_seconds()
        return cache_age < self.config.cache_ttl
    
    def _select_instance(self, instances: List[ServiceInstance], 
                        client_ip: Optional[str] = None) -> Optional[ServiceInstance]:
        """选择服务实例"""
        if not instances:
            return None
        
        strategy = self.config.load_balance_strategy
        
        if strategy == LoadBalanceStrategy.ROUND_ROBIN:
            return self._round_robin_select(instances)
        elif strategy == LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_select(instances)
        elif strategy == LoadBalanceStrategy.LEAST_CONNECTIONS:
            return self._least_connections_select(instances)
        elif strategy == LoadBalanceStrategy.RANDOM:
            return random.choice(instances)
        elif strategy == LoadBalanceStrategy.IP_HASH:
            return self._ip_hash_select(instances, client_ip)
        else:
            return instances[0]
    
    def _round_robin_select(self, instances: List[ServiceInstance]) -> ServiceInstance:
        """轮询选择"""
        with self._lock:
            index = self._round_robin_index % len(instances)
            self._round_robin_index += 1
            return instances[index]
    
    def _weighted_round_robin_select(self, instances: List[ServiceInstance]) -> ServiceInstance:
        """加权轮询选择"""
        total_weight = sum(inst.weight for inst in instances)
        
        if total_weight == 0:
            return self._round_robin_select(instances)
        
        # 生成随机权重值
        random_weight = random.randint(1, total_weight)
        current_weight = 0
        
        for instance in instances:
            current_weight += instance.weight
            if current_weight >= random_weight:
                return instance
        
        return instances[-1]
    
    def _least_connections_select(self, instances: List[ServiceInstance]) -> ServiceInstance:
        """最少连接选择"""
        with self._lock:
            min_connections = float('inf')
            selected_instance = instances[0]
            
            for instance in instances:
                connections = self._connection_counts[instance.instance_id]
                if connections < min_connections:
                    min_connections = connections
                    selected_instance = instance
            
            return selected_instance
    
    def _ip_hash_select(self, instances: List[ServiceInstance], 
                       client_ip: Optional[str] = None) -> ServiceInstance:
        """IP哈希选择"""
        if not client_ip:
            return self._round_robin_select(instances)
        
        # 计算IP哈希
        hash_value = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        index = hash_value % len(instances)
        
        return instances[index]
    
    async def _execute_request(self, request_func: Callable, instance: ServiceInstance) -> Any:
        """执行请求"""
        # 这里可以根据需要实现超时机制
        try:
            return await asyncio.wait_for(
                request_func(instance),
                timeout=self.config.timeout
            )
        except asyncio.TimeoutError:
            raise Exception(f"Request timeout after {self.config.timeout} seconds")
    
    def _record_success(self, instance: ServiceInstance, response_time: float):
        """记录成功请求"""
        # 更新实例统计
        instance.update_stats(response_time, False)
        
        # 更新熔断器
        if self.config.circuit_breaker_enabled:
            circuit_breaker = self._circuit_breakers[instance.instance_id]
            
            if circuit_breaker.state == CircuitBreakerState.HALF_OPEN:
                circuit_breaker.success_count += 1
                if circuit_breaker.success_count >= 3:  # 连续3次成功就关闭熔断器
                    circuit_breaker.state = CircuitBreakerState.CLOSED
                    circuit_breaker.failure_count = 0
                    circuit_breaker.success_count = 0
                    self.logger.info(f"Circuit breaker closed for instance: {instance.instance_id}")
            elif circuit_breaker.state == CircuitBreakerState.CLOSED:
                circuit_breaker.failure_count = max(0, circuit_breaker.failure_count - 1)
    
    def _record_failure(self, instance: ServiceInstance, error: Exception, response_time: float):
        """记录失败请求"""
        # 更新实例统计
        instance.update_stats(response_time, True)
        
        # 更新熔断器
        if self.config.circuit_breaker_enabled:
            circuit_breaker = self._circuit_breakers[instance.instance_id]
            circuit_breaker.failure_count += 1
            circuit_breaker.last_failure_time = datetime.now()
            
            if (circuit_breaker.state == CircuitBreakerState.CLOSED and 
                circuit_breaker.failure_count >= self.config.failure_threshold):
                circuit_breaker.state = CircuitBreakerState.OPEN
                self._stats['circuit_breaker_trips'] += 1
                self.logger.warning(f"Circuit breaker opened for instance: {instance.instance_id}")
    
    def _is_circuit_breaker_allowed(self, circuit_breaker: CircuitBreaker) -> bool:
        """检查熔断器是否允许请求"""
        if circuit_breaker.state == CircuitBreakerState.CLOSED:
            return True
        elif circuit_breaker.state == CircuitBreakerState.OPEN:
            # 检查是否应该进入半开状态
            if (circuit_breaker.last_failure_time and 
                (datetime.now() - circuit_breaker.last_failure_time).total_seconds() >= self.config.recovery_timeout):
                circuit_breaker.state = CircuitBreakerState.HALF_OPEN
                circuit_breaker.success_count = 0
                self.logger.info(f"Circuit breaker half-opened for recovery attempt")
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            stats = self._stats.copy()
            stats['cache_size'] = len(self._cache)
            stats['cache_age'] = (
                (datetime.now() - self._cache_updated_at).total_seconds()
                if self._cache_updated_at else 0
            )
            stats['active_connections'] = dict(self._connection_counts)
            stats['circuit_breaker_states'] = {
                instance_id: cb.state.value 
                for instance_id, cb in self._circuit_breakers.items()
            }
            return stats
    
    def invalidate_cache(self):
        """使缓存失效"""
        with self._cache_lock:
            self._cache_updated_at = None
            self._cache.clear()
            self.logger.info("Service discovery cache invalidated")
    
    def reset_circuit_breaker(self, instance_id: str):
        """重置熔断器"""
        if instance_id in self._circuit_breakers:
            circuit_breaker = self._circuit_breakers[instance_id]
            circuit_breaker.state = CircuitBreakerState.CLOSED
            circuit_breaker.failure_count = 0
            circuit_breaker.success_count = 0
            circuit_breaker.last_failure_time = None
            self.logger.info(f"Circuit breaker reset for instance: {instance_id}")