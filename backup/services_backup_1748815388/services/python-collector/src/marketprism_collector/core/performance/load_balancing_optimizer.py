"""
⚖️ LoadBalancingOptimizer - 负载均衡优化器

智能负载均衡算法选择和优化
提供动态权重调整、性能感知路由、故障转移、容量管理等功能
"""

import asyncio
import time
import random
import hashlib
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import statistics

logger = logging.getLogger(__name__)


class LoadBalancingAlgorithm(Enum):
    """负载均衡算法枚举"""
    ROUND_ROBIN = "round_robin"                # 轮询
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"  # 加权轮询
    LEAST_CONNECTIONS = "least_connections"     # 最少连接
    WEIGHTED_LEAST_CONNECTIONS = "weighted_least_connections"  # 加权最少连接
    LEAST_RESPONSE_TIME = "least_response_time"  # 最短响应时间
    CONSISTENT_HASH = "consistent_hash"         # 一致性哈希
    RANDOM = "random"                          # 随机
    WEIGHTED_RANDOM = "weighted_random"        # 加权随机
    PERFORMANCE_BASED = "performance_based"     # 基于性能
    ADAPTIVE = "adaptive"                      # 自适应


class ServerStatus(Enum):
    """服务器状态枚举"""
    HEALTHY = "healthy"        # 健康
    DEGRADED = "degraded"      # 降级
    UNHEALTHY = "unhealthy"    # 不健康
    MAINTENANCE = "maintenance"  # 维护中
    UNKNOWN = "unknown"        # 未知


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str
    port: int
    weight: float = 1.0
    max_connections: int = 1000
    timeout: float = 30.0
    health_check_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServerMetrics:
    """服务器指标"""
    current_connections: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    last_health_check: float = 0.0
    status: ServerStatus = ServerStatus.UNKNOWN
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    load_score: float = 0.0  # 综合负载评分
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def avg_response_time(self) -> float:
        """平均响应时间"""
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)
    
    @property
    def connection_utilization(self) -> float:
        """连接利用率"""
        # 这里需要根据实际配置计算
        max_conn = 1000  # 默认最大连接数
        return self.current_connections / max_conn if max_conn > 0 else 0.0


@dataclass
class LoadBalancingConfig:
    """负载均衡配置"""
    algorithm: LoadBalancingAlgorithm = LoadBalancingAlgorithm.ADAPTIVE
    health_check_interval: float = 30.0
    failure_threshold: int = 3
    recovery_threshold: int = 2
    enable_circuit_breaker: bool = True
    circuit_breaker_timeout: float = 60.0
    sticky_session_enabled: bool = False
    session_timeout: float = 3600.0
    performance_weight: float = 0.4
    availability_weight: float = 0.6


class Server:
    """服务器实例"""
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.metrics = ServerMetrics()
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.circuit_breaker_open = False
        self.circuit_breaker_last_failure = 0.0
        self.last_used = 0.0
        
        logger.debug(f"服务器创建: {self.config.host}:{self.config.port}")
    
    @property
    def id(self) -> str:
        """服务器ID"""
        return f"{self.config.host}:{self.config.port}"
    
    @property
    def is_available(self) -> bool:
        """是否可用"""
        if self.circuit_breaker_open:
            # 检查熔断器是否应该半开
            if time.time() - self.circuit_breaker_last_failure > 60.0:  # 60秒后尝试恢复
                self.circuit_breaker_open = False
                logger.info(f"熔断器半开: {self.id}")
                return True
            return False
        
        return self.metrics.status in [ServerStatus.HEALTHY, ServerStatus.DEGRADED]
    
    async def handle_request(self, request_func: Callable, *args, **kwargs) -> Any:
        """处理请求"""
        if not self.is_available:
            raise Exception(f"服务器不可用: {self.id}")
        
        start_time = time.time()
        self.metrics.current_connections += 1
        self.last_used = start_time
        
        try:
            result = await request_func(self, *args, **kwargs)
            
            # 记录成功
            response_time = time.time() - start_time
            self.metrics.response_times.append(response_time)
            self.metrics.total_requests += 1
            self.metrics.successful_requests += 1
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            
            # 检查是否从故障中恢复
            if self.metrics.status == ServerStatus.UNHEALTHY and self.consecutive_successes >= 2:
                self.metrics.status = ServerStatus.HEALTHY
                logger.info(f"服务器恢复: {self.id}")
            
            return result
        
        except Exception as e:
            # 记录失败
            self.metrics.total_requests += 1
            self.metrics.failed_requests += 1
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            
            # 检查是否需要标记为不健康
            if self.consecutive_failures >= 3:
                self.metrics.status = ServerStatus.UNHEALTHY
                self.circuit_breaker_open = True
                self.circuit_breaker_last_failure = time.time()
                logger.warning(f"服务器标记为不健康: {self.id}")
            
            raise e
        
        finally:
            self.metrics.current_connections -= 1
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 这里应该实现实际的健康检查逻辑
            # 可以是HTTP健康检查、TCP连接检查等
            
            self.metrics.last_health_check = time.time()
            
            # 模拟健康检查结果
            if self.metrics.status == ServerStatus.UNKNOWN:
                self.metrics.status = ServerStatus.HEALTHY
            
            return self.metrics.status in [ServerStatus.HEALTHY, ServerStatus.DEGRADED]
        
        except Exception as e:
            self.metrics.status = ServerStatus.UNHEALTHY
            logger.error(f"健康检查失败: {self.id}, error={e}")
            return False
    
    def calculate_load_score(self) -> float:
        """计算负载评分（越低越好）"""
        # 综合考虑连接数、响应时间、CPU、内存等因素
        connection_score = self.metrics.connection_utilization
        response_time_score = min(self.metrics.avg_response_time / 1000.0, 1.0)  # 归一化到0-1
        cpu_score = self.metrics.cpu_usage / 100.0
        memory_score = self.metrics.memory_usage / 100.0
        
        # 计算综合评分
        load_score = (
            connection_score * 0.3 +
            response_time_score * 0.3 +
            cpu_score * 0.2 +
            memory_score * 0.2
        )
        
        self.metrics.load_score = load_score
        return load_score


class LoadBalancingOptimizer:
    """
    ⚖️ 负载均衡优化器
    
    提供智能负载均衡、动态权重调整、性能感知路由、故障转移等功能
    """
    
    def __init__(self, config: Optional[LoadBalancingConfig] = None):
        self.config = config or LoadBalancingConfig()
        self.servers: Dict[str, Server] = {}
        self.server_ring: List[str] = []  # 用于一致性哈希
        self.round_robin_index = 0
        self.session_map: Dict[str, str] = {}  # 会话粘性映射
        self.algorithm_stats: Dict[LoadBalancingAlgorithm, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.current_algorithm = self.config.algorithm
        self.health_check_task: Optional[asyncio.Task] = None
        self.optimization_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info(f"LoadBalancingOptimizer初始化: algorithm={self.config.algorithm.value}")
    
    async def start(self):
        """启动负载均衡优化器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动健康检查任务
        self.health_check_task = asyncio.create_task(self._health_check_loop())
        
        # 启动优化任务
        self.optimization_task = asyncio.create_task(self._optimization_loop())
        
        logger.info("LoadBalancingOptimizer已启动")
    
    async def stop(self):
        """停止负载均衡优化器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消任务
        if self.health_check_task:
            self.health_check_task.cancel()
        if self.optimization_task:
            self.optimization_task.cancel()
        
        logger.info("LoadBalancingOptimizer已停止")
    
    def add_server(self, config: ServerConfig) -> str:
        """添加服务器"""
        server = Server(config)
        server_id = server.id
        self.servers[server_id] = server
        
        # 更新一致性哈希环
        self._update_hash_ring()
        
        logger.info(f"添加服务器: {server_id}")
        return server_id
    
    def remove_server(self, server_id: str):
        """移除服务器"""
        if server_id in self.servers:
            del self.servers[server_id]
            self._update_hash_ring()
            logger.info(f"移除服务器: {server_id}")
    
    async def select_server(self, request_key: Optional[str] = None, 
                           session_id: Optional[str] = None) -> Optional[Server]:
        """选择服务器"""
        available_servers = [server for server in self.servers.values() if server.is_available]
        
        if not available_servers:
            logger.warning("没有可用服务器")
            return None
        
        # 会话粘性
        if session_id and self.config.sticky_session_enabled:
            if session_id in self.session_map:
                server_id = self.session_map[session_id]
                if server_id in self.servers and self.servers[server_id].is_available:
                    return self.servers[server_id]
        
        # 根据算法选择服务器
        if self.current_algorithm == LoadBalancingAlgorithm.ROUND_ROBIN:
            server = self._round_robin_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN:
            server = self._weighted_round_robin_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
            server = self._least_connections_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.WEIGHTED_LEAST_CONNECTIONS:
            server = self._weighted_least_connections_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.LEAST_RESPONSE_TIME:
            server = self._least_response_time_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.CONSISTENT_HASH:
            server = self._consistent_hash_select(available_servers, request_key)
        elif self.current_algorithm == LoadBalancingAlgorithm.RANDOM:
            server = self._random_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.WEIGHTED_RANDOM:
            server = self._weighted_random_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.PERFORMANCE_BASED:
            server = self._performance_based_select(available_servers)
        elif self.current_algorithm == LoadBalancingAlgorithm.ADAPTIVE:
            server = await self._adaptive_select(available_servers, request_key)
        else:
            server = self._round_robin_select(available_servers)
        
        # 更新会话映射
        if session_id and server and self.config.sticky_session_enabled:
            self.session_map[session_id] = server.id
        
        return server
    
    def _round_robin_select(self, servers: List[Server]) -> Server:
        """轮询选择"""
        self.round_robin_index = (self.round_robin_index + 1) % len(servers)
        return servers[self.round_robin_index]
    
    def _weighted_round_robin_select(self, servers: List[Server]) -> Server:
        """加权轮询选择"""
        total_weight = sum(server.config.weight for server in servers)
        if total_weight == 0:
            return self._round_robin_select(servers)
        
        # 构建加权列表
        weighted_servers = []
        for server in servers:
            count = int(server.config.weight * 100)  # 放大权重以便计算
            weighted_servers.extend([server] * count)
        
        if not weighted_servers:
            return servers[0]
        
        self.round_robin_index = (self.round_robin_index + 1) % len(weighted_servers)
        return weighted_servers[self.round_robin_index]
    
    def _least_connections_select(self, servers: List[Server]) -> Server:
        """最少连接选择"""
        return min(servers, key=lambda s: s.metrics.current_connections)
    
    def _weighted_least_connections_select(self, servers: List[Server]) -> Server:
        """加权最少连接选择"""
        def score(server):
            if server.config.weight == 0:
                return float('inf')
            return server.metrics.current_connections / server.config.weight
        
        return min(servers, key=score)
    
    def _least_response_time_select(self, servers: List[Server]) -> Server:
        """最短响应时间选择"""
        return min(servers, key=lambda s: s.metrics.avg_response_time)
    
    def _consistent_hash_select(self, servers: List[Server], request_key: Optional[str]) -> Server:
        """一致性哈希选择"""
        if not request_key:
            return self._round_robin_select(servers)
        
        # 计算请求键的哈希值
        hash_value = int(hashlib.md5(request_key.encode()).hexdigest(), 16)
        
        # 在哈希环中找到第一个大于等于哈希值的服务器
        server_ids = [s.id for s in servers]
        server_ids.sort()
        
        for server_id in server_ids:
            server_hash = int(hashlib.md5(server_id.encode()).hexdigest(), 16)
            if server_hash >= hash_value:
                return next(s for s in servers if s.id == server_id)
        
        # 如果没找到，返回第一个服务器
        return servers[0]
    
    def _random_select(self, servers: List[Server]) -> Server:
        """随机选择"""
        return random.choice(servers)
    
    def _weighted_random_select(self, servers: List[Server]) -> Server:
        """加权随机选择"""
        weights = [server.config.weight for server in servers]
        total_weight = sum(weights)
        
        if total_weight == 0:
            return self._random_select(servers)
        
        random_value = random.uniform(0, total_weight)
        cumulative_weight = 0
        
        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if random_value <= cumulative_weight:
                return servers[i]
        
        return servers[-1]
    
    def _performance_based_select(self, servers: List[Server]) -> Server:
        """基于性能选择"""
        # 计算每个服务器的性能评分
        for server in servers:
            server.calculate_load_score()
        
        # 选择负载评分最低的服务器
        return min(servers, key=lambda s: s.metrics.load_score)
    
    async def _adaptive_select(self, servers: List[Server], request_key: Optional[str]) -> Server:
        """自适应选择"""
        # 根据当前系统状态动态选择最优算法
        best_algorithm = await self._determine_best_algorithm(servers)
        
        if best_algorithm != self.current_algorithm:
            logger.info(f"切换负载均衡算法: {self.current_algorithm.value} -> {best_algorithm.value}")
            self.current_algorithm = best_algorithm
        
        # 使用选定的算法
        if best_algorithm == LoadBalancingAlgorithm.PERFORMANCE_BASED:
            return self._performance_based_select(servers)
        elif best_algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
            return self._least_connections_select(servers)
        elif best_algorithm == LoadBalancingAlgorithm.LEAST_RESPONSE_TIME:
            return self._least_response_time_select(servers)
        else:
            return self._weighted_round_robin_select(servers)
    
    async def _determine_best_algorithm(self, servers: List[Server]) -> LoadBalancingAlgorithm:
        """确定最佳算法"""
        # 分析当前系统状态
        avg_connections = statistics.mean([s.metrics.current_connections for s in servers]) if servers else 0
        avg_response_time = statistics.mean([s.metrics.avg_response_time for s in servers]) if servers else 0
        load_variance = statistics.variance([s.metrics.load_score for s in servers]) if len(servers) > 1 else 0
        
        # 根据系统状态选择算法
        if avg_response_time > 1000:  # 响应时间过长
            return LoadBalancingAlgorithm.LEAST_RESPONSE_TIME
        elif avg_connections > 100:  # 连接数过多
            return LoadBalancingAlgorithm.LEAST_CONNECTIONS
        elif load_variance > 0.3:  # 负载不均衡
            return LoadBalancingAlgorithm.PERFORMANCE_BASED
        else:
            return LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN
    
    def _update_hash_ring(self):
        """更新一致性哈希环"""
        self.server_ring = list(self.servers.keys())
        self.server_ring.sort()
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查失败: {e}")
    
    async def _perform_health_checks(self):
        """执行健康检查"""
        tasks = []
        for server in self.servers.values():
            task = asyncio.create_task(server.health_check())
            tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            healthy_count = sum(1 for result in results if result is True)
            logger.debug(f"健康检查完成: {healthy_count}/{len(self.servers)} 服务器健康")
    
    async def _optimization_loop(self):
        """优化循环"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # 每分钟优化一次
                await self._optimize_weights()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"优化失败: {e}")
    
    async def _optimize_weights(self):
        """优化权重"""
        if not self.servers:
            return
        
        # 基于性能动态调整权重
        for server in self.servers.values():
            if server.metrics.total_requests > 0:
                # 根据成功率和响应时间调整权重
                performance_factor = (
                    server.metrics.success_rate * self.config.availability_weight +
                    (1 - min(server.metrics.avg_response_time / 1000.0, 1.0)) * self.config.performance_weight
                )
                
                # 调整权重（缓慢调整以避免震荡）
                new_weight = server.config.weight * 0.9 + performance_factor * 0.1
                server.config.weight = max(0.1, min(2.0, new_weight))
        
        logger.debug("权重优化完成")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        server_stats = {}
        for server_id, server in self.servers.items():
            server_stats[server_id] = {
                "status": server.metrics.status.value,
                "connections": server.metrics.current_connections,
                "total_requests": server.metrics.total_requests,
                "success_rate": server.metrics.success_rate,
                "avg_response_time": server.metrics.avg_response_time,
                "load_score": server.metrics.load_score,
                "weight": server.config.weight,
                "circuit_breaker_open": server.circuit_breaker_open
            }
        
        return {
            "algorithm": self.current_algorithm.value,
            "total_servers": len(self.servers),
            "available_servers": len([s for s in self.servers.values() if s.is_available]),
            "server_stats": server_stats,
            "session_count": len(self.session_map)
        }
    
    def get_optimization_suggestions(self) -> List[str]:
        """获取优化建议"""
        suggestions = []
        
        if not self.servers:
            suggestions.append("没有配置服务器")
            return suggestions
        
        available_count = len([s for s in self.servers.values() if s.is_available])
        if available_count == 0:
            suggestions.append("所有服务器都不可用，请检查服务器状态")
        elif available_count < len(self.servers) * 0.5:
            suggestions.append("超过一半的服务器不可用，可能存在系统性问题")
        
        # 分析负载分布
        if len(self.servers) > 1:
            load_scores = [s.metrics.load_score for s in self.servers.values()]
            if statistics.variance(load_scores) > 0.3:
                suggestions.append("服务器负载分布不均，建议检查权重配置或算法选择")
        
        # 分析响应时间
        avg_response_times = [s.metrics.avg_response_time for s in self.servers.values() if s.metrics.avg_response_time > 0]
        if avg_response_times:
            avg_time = statistics.mean(avg_response_times)
            if avg_time > 1000:
                suggestions.append("平均响应时间过长，建议优化后端服务或增加服务器")
        
        return suggestions