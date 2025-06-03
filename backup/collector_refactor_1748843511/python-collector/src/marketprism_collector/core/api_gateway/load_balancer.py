"""
MarketPrism API网关 - 负载均衡器

支持多种负载均衡算法、健康检查和故障转移、服务实例管理

Week 6 Day 1 核心组件
"""

import time
import random
import hashlib
import logging
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
import statistics

# 设置日志
logger = logging.getLogger(__name__)

class LoadBalancingStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = "round_robin"                    # 轮询
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"  # 加权轮询
    LEAST_CONNECTIONS = "least_connections"        # 最少连接数
    WEIGHTED_LEAST_CONNECTIONS = "weighted_least_connections"  # 加权最少连接
    RANDOM = "random"                              # 随机
    WEIGHTED_RANDOM = "weighted_random"            # 加权随机
    IP_HASH = "ip_hash"                           # IP哈希
    CONSISTENT_HASH = "consistent_hash"            # 一致性哈希
    LEAST_RESPONSE_TIME = "least_response_time"    # 最小响应时间
    HEALTH_AWARE = "health_aware"                  # 健康感知

class ServiceStatus(Enum):
    """服务状态"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"  # 排水状态，不接受新请求但处理现有请求
    DISABLED = "disabled"

@dataclass
class ServiceInstance:
    """服务实例"""
    instance_id: str
    host: str
    port: int
    weight: float = 1.0
    status: ServiceStatus = ServiceStatus.HEALTHY
    
    # 连接统计
    active_connections: int = 0
    total_connections: int = 0
    
    # 性能统计
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    
    # 健康检查
    last_health_check: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    # 元数据
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # 一致性哈希相关
    hash_ring_positions: List[int] = field(default_factory=list)
    
    @property
    def address(self) -> str:
        """获取服务地址"""
        return f"{self.host}:{self.port}"
    
    @property
    def success_rate(self) -> float:
        """获取成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def average_response_time(self) -> float:
        """获取平均响应时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests
    
    @property
    def is_available(self) -> bool:
        """检查实例是否可用"""
        return self.status in [ServiceStatus.HEALTHY, ServiceStatus.DRAINING]
    
    def update_stats(self, response_time: float, success: bool):
        """更新统计信息"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.total_response_time += response_time
            self.consecutive_failures = 0
            self.consecutive_successes += 1
        else:
            self.failed_requests += 1
            self.consecutive_successes = 0
            self.consecutive_failures += 1
        
        self.updated_at = time.time()

class LoadBalancingAlgorithm(ABC):
    """负载均衡算法基类"""
    
    @abstractmethod
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        """选择服务实例"""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """获取算法名称"""
        pass

class RoundRobinAlgorithm(LoadBalancingAlgorithm):
    """轮询算法"""
    
    def __init__(self):
        self.current_index = 0
        self._lock = threading.Lock()
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        with self._lock:
            instance = available_instances[self.current_index % len(available_instances)]
            self.current_index += 1
            return instance
    
    def get_name(self) -> str:
        return "RoundRobin"

class WeightedRoundRobinAlgorithm(LoadBalancingAlgorithm):
    """加权轮询算法"""
    
    def __init__(self):
        self.current_weights = {}
        self._lock = threading.Lock()
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        with self._lock:
            # 初始化权重
            for instance in available_instances:
                if instance.instance_id not in self.current_weights:
                    self.current_weights[instance.instance_id] = 0
            
            # 计算总权重
            total_weight = sum(inst.weight for inst in available_instances)
            if total_weight == 0:
                return available_instances[0]
            
            # 增加当前权重
            for instance in available_instances:
                self.current_weights[instance.instance_id] += instance.weight
            
            # 选择权重最高的实例
            selected_instance = max(available_instances, 
                                  key=lambda inst: self.current_weights[inst.instance_id])
            
            # 减少选中实例的权重
            self.current_weights[selected_instance.instance_id] -= total_weight
            
            return selected_instance
    
    def get_name(self) -> str:
        return "WeightedRoundRobin"

class LeastConnectionsAlgorithm(LoadBalancingAlgorithm):
    """最少连接数算法"""
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        # 选择连接数最少的实例
        return min(available_instances, key=lambda inst: inst.active_connections)
    
    def get_name(self) -> str:
        return "LeastConnections"

class WeightedLeastConnectionsAlgorithm(LoadBalancingAlgorithm):
    """加权最少连接算法"""
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        # 选择连接数/权重比最小的实例
        def connection_weight_ratio(instance):
            if instance.weight == 0:
                return float('inf')
            return instance.active_connections / instance.weight
        
        return min(available_instances, key=connection_weight_ratio)
    
    def get_name(self) -> str:
        return "WeightedLeastConnections"

class RandomAlgorithm(LoadBalancingAlgorithm):
    """随机算法"""
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        return random.choice(available_instances)
    
    def get_name(self) -> str:
        return "Random"

class WeightedRandomAlgorithm(LoadBalancingAlgorithm):
    """加权随机算法"""
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        # 计算权重总和
        total_weight = sum(inst.weight for inst in available_instances)
        if total_weight == 0:
            return random.choice(available_instances)
        
        # 随机选择
        rand_val = random.uniform(0, total_weight)
        current_weight = 0
        
        for instance in available_instances:
            current_weight += instance.weight
            if rand_val <= current_weight:
                return instance
        
        return available_instances[-1]
    
    def get_name(self) -> str:
        return "WeightedRandom"

class IPHashAlgorithm(LoadBalancingAlgorithm):
    """IP哈希算法"""
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        # 获取客户端IP
        client_ip = "unknown"
        if request_context and 'client_ip' in request_context:
            client_ip = request_context['client_ip']
        
        # 计算哈希值
        hash_value = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        index = hash_value % len(available_instances)
        
        return available_instances[index]
    
    def get_name(self) -> str:
        return "IPHash"

class ConsistentHashAlgorithm(LoadBalancingAlgorithm):
    """一致性哈希算法"""
    
    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.hash_ring = {}
        self.sorted_keys = []
        self._lock = threading.Lock()
    
    def _build_ring(self, instances: List[ServiceInstance]):
        """构建哈希环"""
        self.hash_ring.clear()
        
        for instance in instances:
            if not instance.is_available:
                continue
            
            # 清空之前的哈希环位置
            instance.hash_ring_positions.clear()
            
            # 为每个实例创建虚拟节点
            for i in range(self.virtual_nodes):
                key = f"{instance.address}:{i}"
                hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
                self.hash_ring[hash_value] = instance
                instance.hash_ring_positions.append(hash_value)
        
        self.sorted_keys = sorted(self.hash_ring.keys())
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        with self._lock:
            # 重建哈希环（简化实现，实际中应该缓存）
            self._build_ring(available_instances)
            
            if not self.sorted_keys:
                return None
            
            # 获取请求键
            request_key = "default"
            if request_context:
                if 'client_ip' in request_context:
                    request_key = request_context['client_ip']
                elif 'session_id' in request_context:
                    request_key = request_context['session_id']
            
            # 计算请求哈希值
            request_hash = int(hashlib.md5(request_key.encode()).hexdigest(), 16)
            
            # 在哈希环上找到第一个大于等于请求哈希值的节点
            for key in self.sorted_keys:
                if key >= request_hash:
                    return self.hash_ring[key]
            
            # 如果没找到，返回第一个节点（环形）
            return self.hash_ring[self.sorted_keys[0]]
    
    def get_name(self) -> str:
        return "ConsistentHash"

class LeastResponseTimeAlgorithm(LoadBalancingAlgorithm):
    """最小响应时间算法"""
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        available_instances = [inst for inst in instances if inst.is_available]
        if not available_instances:
            return None
        
        # 选择平均响应时间最短的实例
        return min(available_instances, key=lambda inst: inst.average_response_time)
    
    def get_name(self) -> str:
        return "LeastResponseTime"

class HealthAwareAlgorithm(LoadBalancingAlgorithm):
    """健康感知算法"""
    
    def __init__(self, base_algorithm: LoadBalancingAlgorithm = None):
        self.base_algorithm = base_algorithm or WeightedRoundRobinAlgorithm()
    
    def select_instance(self, instances: List[ServiceInstance], 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        # 计算健康分数并过滤
        healthy_instances = []
        for instance in instances:
            if not instance.is_available:
                continue
            
            # 计算健康分数（0-1之间）
            health_score = self._calculate_health_score(instance)
            if health_score > 0.3:  # 健康分数阈值
                # 根据健康分数调整权重
                adjusted_instance = ServiceInstance(
                    instance_id=instance.instance_id,
                    host=instance.host,
                    port=instance.port,
                    weight=instance.weight * health_score,
                    status=instance.status,
                    active_connections=instance.active_connections
                )
                healthy_instances.append(adjusted_instance)
        
        if not healthy_instances:
            # 如果没有健康的实例，降低阈值重试
            for instance in instances:
                if instance.is_available:
                    healthy_instances.append(instance)
        
        return self.base_algorithm.select_instance(healthy_instances, request_context)
    
    def _calculate_health_score(self, instance: ServiceInstance) -> float:
        """计算健康分数"""
        # 成功率权重
        success_score = instance.success_rate * 0.4
        
        # 响应时间权重（越小越好）
        avg_response_time = instance.average_response_time
        if avg_response_time == 0:
            response_score = 1.0
        else:
            # 假设期望响应时间为100ms
            response_score = max(0, 1 - (avg_response_time - 100) / 1000) * 0.3
        
        # 连接数权重（相对值）
        connection_ratio = instance.active_connections / max(instance.weight, 1)
        connection_score = max(0, 1 - connection_ratio / 100) * 0.2
        
        # 连续故障惩罚
        failure_penalty = max(0, 1 - instance.consecutive_failures / 10) * 0.1
        
        return max(0, min(1, success_score + response_score + connection_score + failure_penalty))
    
    def get_name(self) -> str:
        return f"HealthAware({self.base_algorithm.get_name()})"

class LoadBalancer:
    """
    高性能负载均衡器
    
    支持多种负载均衡算法、健康检查和故障转移、服务实例管理
    """
    
    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN,
                 enable_health_check: bool = True, enable_metrics: bool = True):
        self.strategy = strategy
        self.enable_health_check = enable_health_check
        self.enable_metrics = enable_metrics
        
        # 服务实例管理
        self.services: Dict[str, List[ServiceInstance]] = {}
        self._lock = threading.RLock()
        
        # 算法映射
        self.algorithms: Dict[LoadBalancingStrategy, LoadBalancingAlgorithm] = {
            LoadBalancingStrategy.ROUND_ROBIN: RoundRobinAlgorithm(),
            LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN: WeightedRoundRobinAlgorithm(),
            LoadBalancingStrategy.LEAST_CONNECTIONS: LeastConnectionsAlgorithm(),
            LoadBalancingStrategy.WEIGHTED_LEAST_CONNECTIONS: WeightedLeastConnectionsAlgorithm(),
            LoadBalancingStrategy.RANDOM: RandomAlgorithm(),
            LoadBalancingStrategy.WEIGHTED_RANDOM: WeightedRandomAlgorithm(),
            LoadBalancingStrategy.IP_HASH: IPHashAlgorithm(),
            LoadBalancingStrategy.CONSISTENT_HASH: ConsistentHashAlgorithm(),
            LoadBalancingStrategy.LEAST_RESPONSE_TIME: LeastResponseTimeAlgorithm(),
            LoadBalancingStrategy.HEALTH_AWARE: HealthAwareAlgorithm(),
        }
        
        # 性能统计
        self.stats = {
            'total_requests': 0,
            'successful_selections': 0,
            'failed_selections': 0,
            'service_stats': {},
            'algorithm_stats': {},
        }
        
        # 健康检查
        self.health_check_interval = 30  # 秒
        self.health_check_timeout = 5    # 秒
        self.health_check_enabled = enable_health_check
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="load-balancer")
        
        logger.info(f"LoadBalancer initialized with strategy: {strategy.value}")
    
    def add_service(self, service_name: str, instances: List[ServiceInstance]):
        """
        添加服务和实例
        
        Args:
            service_name: 服务名称
            instances: 服务实例列表
        """
        with self._lock:
            if service_name not in self.services:
                self.services[service_name] = []
            
            for instance in instances:
                # 检查是否已存在
                existing_instance = next(
                    (inst for inst in self.services[service_name] 
                     if inst.instance_id == instance.instance_id), None
                )
                
                if existing_instance:
                    logger.warning(f"Instance {instance.instance_id} already exists, updating")
                    self.services[service_name].remove(existing_instance)
                
                self.services[service_name].append(instance)
                
                # 初始化统计
                if self.enable_metrics:
                    service_stats = self.stats['service_stats'].setdefault(service_name, {})
                    service_stats[instance.instance_id] = {
                        'selections': 0,
                        'requests': 0,
                        'successes': 0,
                        'failures': 0,
                    }
            
            logger.info(f"Added {len(instances)} instances to service {service_name}")
    
    def remove_service_instance(self, service_name: str, instance_id: str) -> bool:
        """
        移除服务实例
        
        Args:
            service_name: 服务名称
            instance_id: 实例ID
            
        Returns:
            bool: 是否移除成功
        """
        with self._lock:
            if service_name not in self.services:
                return False
            
            original_count = len(self.services[service_name])
            self.services[service_name] = [
                inst for inst in self.services[service_name] 
                if inst.instance_id != instance_id
            ]
            
            # 清理统计
            if self.enable_metrics and service_name in self.stats['service_stats']:
                self.stats['service_stats'][service_name].pop(instance_id, None)
            
            removed = len(self.services[service_name]) < original_count
            if removed:
                logger.info(f"Removed instance {instance_id} from service {service_name}")
            
            return removed
    
    def select_instance(self, service_name: str, 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        """
        选择服务实例
        
        Args:
            service_name: 服务名称
            request_context: 请求上下文
            
        Returns:
            ServiceInstance: 选中的服务实例，如果没有可用实例则返回None
        """
        with self._lock:
            # 更新统计
            if self.enable_metrics:
                self.stats['total_requests'] += 1
            
            # 检查服务是否存在
            if service_name not in self.services:
                logger.warning(f"Service {service_name} not found")
                if self.enable_metrics:
                    self.stats['failed_selections'] += 1
                return None
            
            instances = self.services[service_name]
            if not instances:
                logger.warning(f"No instances found for service {service_name}")
                if self.enable_metrics:
                    self.stats['failed_selections'] += 1
                return None
            
            # 获取负载均衡算法
            algorithm = self.algorithms[self.strategy]
            
            # 选择实例
            selected_instance = algorithm.select_instance(instances, request_context)
            
            if selected_instance:
                # 增加连接计数
                selected_instance.active_connections += 1
                
                # 更新统计
                if self.enable_metrics:
                    self.stats['successful_selections'] += 1
                    
                    service_stats = self.stats['service_stats'].setdefault(service_name, {})
                    instance_stats = service_stats.setdefault(selected_instance.instance_id, {
                        'selections': 0, 'requests': 0, 'successes': 0, 'failures': 0
                    })
                    instance_stats['selections'] += 1
                    
                    # 算法统计
                    algo_name = algorithm.get_name()
                    self.stats['algorithm_stats'][algo_name] = self.stats['algorithm_stats'].get(algo_name, 0) + 1
                
                logger.debug(f"Selected instance {selected_instance.instance_id} for service {service_name}")
            else:
                if self.enable_metrics:
                    self.stats['failed_selections'] += 1
                logger.warning(f"No available instances for service {service_name}")
            
            return selected_instance
    
    def release_instance(self, instance: ServiceInstance, response_time: float = 0.0, success: bool = True):
        """
        释放服务实例连接
        
        Args:
            instance: 服务实例
            response_time: 响应时间
            success: 是否成功
        """
        with self._lock:
            # 减少连接计数
            instance.active_connections = max(0, instance.active_connections - 1)
            
            # 更新实例统计
            instance.update_stats(response_time, success)
            
            logger.debug(f"Released instance {instance.instance_id}, success: {success}, "
                        f"response_time: {response_time}ms")
    
    def update_instance_status(self, service_name: str, instance_id: str, 
                             status: ServiceStatus) -> bool:
        """
        更新实例状态
        
        Args:
            service_name: 服务名称
            instance_id: 实例ID
            status: 新状态
            
        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            if service_name not in self.services:
                return False
            
            for instance in self.services[service_name]:
                if instance.instance_id == instance_id:
                    old_status = instance.status
                    instance.status = status
                    instance.updated_at = time.time()
                    
                    logger.info(f"Updated instance {instance_id} status: {old_status.value} -> {status.value}")
                    return True
            
            return False
    
    def get_service_instances(self, service_name: str) -> List[ServiceInstance]:
        """获取服务实例列表"""
        with self._lock:
            return self.services.get(service_name, []).copy()
    
    def get_healthy_instances(self, service_name: str) -> List[ServiceInstance]:
        """获取健康的服务实例"""
        instances = self.get_service_instances(service_name)
        return [inst for inst in instances if inst.status == ServiceStatus.HEALTHY]
    
    def get_service_stats(self, service_name: str) -> Dict[str, Any]:
        """获取服务统计信息"""
        with self._lock:
            instances = self.services.get(service_name, [])
            
            stats = {
                'total_instances': len(instances),
                'healthy_instances': len([inst for inst in instances if inst.status == ServiceStatus.HEALTHY]),
                'unhealthy_instances': len([inst for inst in instances if inst.status == ServiceStatus.UNHEALTHY]),
                'draining_instances': len([inst for inst in instances if inst.status == ServiceStatus.DRAINING]),
                'disabled_instances': len([inst for inst in instances if inst.status == ServiceStatus.DISABLED]),
                'total_connections': sum(inst.active_connections for inst in instances),
                'total_requests': sum(inst.total_requests for inst in instances),
                'total_success_rate': 0.0,
                'average_response_time': 0.0,
                'instances': []
            }
            
            if instances:
                success_rates = [inst.success_rate for inst in instances if inst.total_requests > 0]
                if success_rates:
                    stats['total_success_rate'] = statistics.mean(success_rates)
                
                response_times = [inst.average_response_time for inst in instances if inst.successful_requests > 0]
                if response_times:
                    stats['average_response_time'] = statistics.mean(response_times)
                
                # 实例详细信息
                for instance in instances:
                    stats['instances'].append({
                        'instance_id': instance.instance_id,
                        'address': instance.address,
                        'status': instance.status.value,
                        'weight': instance.weight,
                        'active_connections': instance.active_connections,
                        'total_requests': instance.total_requests,
                        'success_rate': instance.success_rate,
                        'average_response_time': instance.average_response_time,
                        'consecutive_failures': instance.consecutive_failures,
                    })
            
            return stats
    
    def get_load_balancer_stats(self) -> Dict[str, Any]:
        """获取负载均衡器统计信息"""
        with self._lock:
            stats = self.stats.copy()
            stats['strategy'] = self.strategy.value
            stats['total_services'] = len(self.services)
            stats['total_instances'] = sum(len(instances) for instances in self.services.values())
            
            if self.stats['total_requests'] > 0:
                stats['success_rate'] = (
                    self.stats['successful_selections'] / self.stats['total_requests'] * 100
                )
            else:
                stats['success_rate'] = 0.0
            
            return stats
    
    def set_strategy(self, strategy: LoadBalancingStrategy):
        """设置负载均衡策略"""
        with self._lock:
            old_strategy = self.strategy
            self.strategy = strategy
            logger.info(f"Load balancing strategy changed: {old_strategy.value} -> {strategy.value}")
    
    def cleanup(self):
        """清理资源"""
        logger.info("Cleaning up LoadBalancer")
        self.executor.shutdown(wait=True)
        with self._lock:
            self.services.clear()
            self.stats = {
                'total_requests': 0,
                'successful_selections': 0,
                'failed_selections': 0,
                'service_stats': {},
                'algorithm_stats': {},
            }

# 便利函数
def create_service_instance(instance_id: str, host: str, port: int, 
                          weight: float = 1.0, **kwargs) -> ServiceInstance:
    """创建服务实例的便利函数"""
    return ServiceInstance(
        instance_id=instance_id,
        host=host,
        port=port,
        weight=weight,
        **kwargs
    )