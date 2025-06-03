#!/usr/bin/env python3
"""
MarketPrism 配置负载均衡器
配置管理系统 2.0 - Week 5 Day 5

智能配置负载均衡组件，提供多节点配置分发、
故障转移、流量调度和负载均衡功能。

Author: MarketPrism团队
Created: 2025-01-29
Version: 1.0.0
"""

import time
import threading
import statistics
import json
import hashlib
import random
from typing import Dict, Any, List, Optional, Callable, Union, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict, deque
import uuid
import psutil
import logging
import socket
import asyncio
import aiohttp
import requests
from urllib.parse import urljoin

# 导入相关组件
from .config_performance_monitor import (
    ConfigPerformanceMonitor, 
    MetricType,
    get_performance_monitor,
    monitor_performance
)


class LoadBalancingStrategy(Enum):
    """负载均衡策略"""
    ROUND_ROBIN = auto()          # 轮询
    WEIGHTED_ROUND_ROBIN = auto() # 加权轮询
    LEAST_CONNECTIONS = auto()    # 最少连接
    LEAST_RESPONSE_TIME = auto()  # 最少响应时间
    IP_HASH = auto()              # IP哈希
    CONSISTENT_HASH = auto()      # 一致性哈希
    RANDOM = auto()               # 随机
    HEALTH_BASED = auto()         # 基于健康状态


class NodeStatus(Enum):
    """节点状态"""
    HEALTHY = auto()              # 健康
    DEGRADED = auto()             # 降级
    UNHEALTHY = auto()            # 不健康
    MAINTENANCE = auto()          # 维护中
    OFFLINE = auto()              # 离线


class FailoverStrategy(Enum):
    """故障转移策略"""
    IMMEDIATE = auto()            # 立即转移
    CIRCUIT_BREAKER = auto()      # 熔断器
    RETRY_THEN_FAILOVER = auto()  # 重试后转移
    GRACEFUL_DEGRADATION = auto() # 优雅降级


@dataclass
class ConfigNode:
    """配置节点"""
    node_id: str
    name: str
    host: str
    port: int
    protocol: str = "http"
    weight: int = 100            # 权重 (1-1000)
    max_connections: int = 1000  # 最大连接数
    timeout: float = 30.0        # 超时时间（秒）
    priority: int = 1            # 优先级 (1最高)
    tags: Dict[str, str] = field(default_factory=dict)
    
    # 运行时状态
    status: NodeStatus = NodeStatus.HEALTHY
    current_connections: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    last_health_check: Optional[datetime] = None
    consecutive_failures: int = 0
    
    @property
    def base_url(self) -> str:
        """基础URL"""
        return f"{self.protocol}://{self.host}:{self.port}"
        
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
        
    @property
    def load_factor(self) -> float:
        """负载因子"""
        if self.max_connections == 0:
            return 1.0
        return self.current_connections / self.max_connections
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.name
        if self.last_health_check:
            data['last_health_check'] = self.last_health_check.isoformat()
        return data


@dataclass
class LoadBalancingRequest:
    """负载均衡请求"""
    request_id: str
    client_ip: str
    path: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    data: Optional[Any] = None
    timestamp: datetime = field(default_factory=datetime.now)
    priority: int = 1            # 请求优先级
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class LoadBalancingResponse:
    """负载均衡响应"""
    request_id: str
    node_id: str
    status_code: int
    response_time: float         # 响应时间（毫秒）
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class LoadBalancingStats:
    """负载均衡统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    requests_per_second: float = 0.0
    active_connections: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ConfigLoadBalancer:
    """配置负载均衡器
    
    提供多节点配置服务的负载均衡，包括：
    - 多种负载均衡策略
    - 健康检查和故障转移
    - 请求路由和分发
    - 性能监控和统计
    - 动态节点管理
    """
    
    def __init__(self,
                 strategy: LoadBalancingStrategy = LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN,
                 health_check_interval: float = 30.0,
                 max_retries: int = 3,
                 circuit_breaker_threshold: int = 5):
        """初始化负载均衡器
        
        Args:
            strategy: 负载均衡策略
            health_check_interval: 健康检查间隔（秒）
            max_retries: 最大重试次数
            circuit_breaker_threshold: 熔断器阈值
        """
        self.strategy = strategy
        self.health_check_interval = health_check_interval
        self.max_retries = max_retries
        self.circuit_breaker_threshold = circuit_breaker_threshold
        
        # 节点管理
        self.nodes: Dict[str, ConfigNode] = {}
        self.healthy_nodes: List[str] = []
        self.unhealthy_nodes: List[str] = []
        
        # 策略状态
        self._round_robin_index = 0
        self._consistent_hash_ring: Dict[int, str] = {}
        self._last_requests: deque = deque(maxlen=1000)
        
        # 统计信息
        self.stats = LoadBalancingStats()
        self.node_stats: Dict[str, LoadBalancingStats] = defaultdict(LoadBalancingStats)
        
        # 控制变量
        self._health_checking = False
        self._health_check_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # HTTP会话
        self._session = requests.Session()
        self._session.timeout = 30
        
        # 性能监控
        self._monitor = get_performance_monitor()
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def start_health_checks(self):
        """启动健康检查"""
        if self._health_checking:
            return
            
        self._health_checking = True
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="ConfigLoadBalancerHealthCheck"
        )
        self._health_check_thread.start()
        self.logger.info("负载均衡器健康检查已启动")
        
    def stop_health_checks(self):
        """停止健康检查"""
        self._health_checking = False
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5.0)
        self.logger.info("负载均衡器健康检查已停止")
        
    def add_node(self, node: ConfigNode) -> bool:
        """添加配置节点
        
        Args:
            node: 配置节点
            
        Returns:
            是否成功添加
        """
        with self._lock:
            try:
                self.nodes[node.node_id] = node
                self.node_stats[node.node_id] = LoadBalancingStats()
                
                # 执行初始健康检查
                if self._perform_health_check(node):
                    node.status = NodeStatus.HEALTHY
                    if node.node_id not in self.healthy_nodes:
                        self.healthy_nodes.append(node.node_id)
                else:
                    node.status = NodeStatus.UNHEALTHY
                    if node.node_id not in self.unhealthy_nodes:
                        self.unhealthy_nodes.append(node.node_id)
                        
                # 更新一致性哈希环
                if self.strategy == LoadBalancingStrategy.CONSISTENT_HASH:
                    self._update_consistent_hash_ring()
                    
                self.logger.info(f"添加节点: {node.name} ({node.base_url})")
                return True
                
            except Exception as e:
                self.logger.error(f"添加节点失败: {e}")
                return False
                
    def remove_node(self, node_id: str) -> bool:
        """移除配置节点
        
        Args:
            node_id: 节点ID
            
        Returns:
            是否成功移除
        """
        with self._lock:
            if node_id not in self.nodes:
                return False
                
            try:
                node = self.nodes[node_id]
                
                # 等待当前连接完成
                timeout = 30  # 30秒超时
                start_time = time.time()
                while node.current_connections > 0 and (time.time() - start_time) < timeout:
                    time.sleep(0.1)
                    
                # 从各个列表中移除
                if node_id in self.healthy_nodes:
                    self.healthy_nodes.remove(node_id)
                if node_id in self.unhealthy_nodes:
                    self.unhealthy_nodes.remove(node_id)
                    
                # 删除节点和统计
                del self.nodes[node_id]
                if node_id in self.node_stats:
                    del self.node_stats[node_id]
                    
                # 更新一致性哈希环
                if self.strategy == LoadBalancingStrategy.CONSISTENT_HASH:
                    self._update_consistent_hash_ring()
                    
                self.logger.info(f"移除节点: {node.name}")
                return True
                
            except Exception as e:
                self.logger.error(f"移除节点失败: {e}")
                return False
                
    @monitor_performance("load_balancer", "select_node")
    def select_node(self, request: LoadBalancingRequest) -> Optional[ConfigNode]:
        """选择配置节点
        
        Args:
            request: 负载均衡请求
            
        Returns:
            选中的节点或None
        """
        with self._lock:
            if not self.healthy_nodes:
                self.logger.warning("没有健康的节点可用")
                return None
                
            try:
                if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
                    return self._select_round_robin()
                elif self.strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
                    return self._select_weighted_round_robin()
                elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
                    return self._select_least_connections()
                elif self.strategy == LoadBalancingStrategy.LEAST_RESPONSE_TIME:
                    return self._select_least_response_time()
                elif self.strategy == LoadBalancingStrategy.IP_HASH:
                    return self._select_ip_hash(request.client_ip)
                elif self.strategy == LoadBalancingStrategy.CONSISTENT_HASH:
                    return self._select_consistent_hash(request.client_ip)
                elif self.strategy == LoadBalancingStrategy.RANDOM:
                    return self._select_random()
                elif self.strategy == LoadBalancingStrategy.HEALTH_BASED:
                    return self._select_health_based()
                else:
                    return self._select_round_robin()
                    
            except Exception as e:
                self.logger.error(f"节点选择失败: {e}")
                return None
                
    @monitor_performance("load_balancer", "forward_request")
    def forward_request(self, request: LoadBalancingRequest) -> LoadBalancingResponse:
        """转发请求
        
        Args:
            request: 负载均衡请求
            
        Returns:
            负载均衡响应
        """
        start_time = time.perf_counter()
        attempts = 0
        last_error = None
        
        while attempts < self.max_retries:
            attempts += 1
            
            # 选择节点
            node = self.select_node(request)
            if not node:
                return LoadBalancingResponse(
                    request_id=request.request_id,
                    node_id="",
                    status_code=503,
                    response_time=0,
                    success=False,
                    error="没有可用的节点"
                )
                
            try:
                # 增加连接计数
                with self._lock:
                    node.current_connections += 1
                    
                # 构建URL
                url = urljoin(node.base_url, request.path)
                
                # 发送请求
                response = self._send_request(node, url, request)
                
                # 记录成功
                end_time = time.perf_counter()
                response_time = (end_time - start_time) * 1000
                
                self._record_success(node, response_time)
                
                return LoadBalancingResponse(
                    request_id=request.request_id,
                    node_id=node.node_id,
                    status_code=response.status_code,
                    response_time=response_time,
                    success=True,
                    data=response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                )
                
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"请求失败 (尝试 {attempts}/{self.max_retries}): {e}")
                
                # 记录失败
                self._record_failure(node)
                
                # 如果是最后一次尝试，返回失败响应
                if attempts >= self.max_retries:
                    break
                    
                # 等待后重试
                time.sleep(0.1 * attempts)
                
            finally:
                # 减少连接计数
                with self._lock:
                    node.current_connections = max(0, node.current_connections - 1)
                    
        # 所有尝试都失败
        end_time = time.perf_counter()
        response_time = (end_time - start_time) * 1000
        
        return LoadBalancingResponse(
            request_id=request.request_id,
            node_id=node.node_id if node else "",
            status_code=500,
            response_time=response_time,
            success=False,
            error=last_error or "请求失败"
        )
        
    def get_node_status(self, node_id: Optional[str] = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """获取节点状态
        
        Args:
            node_id: 节点ID，None表示获取所有节点
            
        Returns:
            节点状态信息
        """
        with self._lock:
            if node_id:
                if node_id not in self.nodes:
                    return {}
                node = self.nodes[node_id]
                stats = self.node_stats[node_id]
                return {
                    "node": node.to_dict(),
                    "stats": stats.to_dict()
                }
            else:
                return [
                    {
                        "node": node.to_dict(),
                        "stats": self.node_stats[node_id].to_dict()
                    }
                    for node_id, node in self.nodes.items()
                ]
                
    def get_load_balancer_stats(self) -> Dict[str, Any]:
        """获取负载均衡器统计信息"""
        with self._lock:
            # 计算最近的请求速率
            now = datetime.now()
            recent_requests = [
                req for req in self._last_requests
                if (now - req).total_seconds() < 60
            ]
            
            return {
                "timestamp": now.isoformat(),
                "strategy": self.strategy.name,
                "nodes": {
                    "total": len(self.nodes),
                    "healthy": len(self.healthy_nodes),
                    "unhealthy": len(self.unhealthy_nodes)
                },
                "global_stats": self.stats.to_dict(),
                "performance": {
                    "requests_last_minute": len(recent_requests),
                    "avg_response_time": self.stats.avg_response_time,
                    "success_rate": self.stats.success_rate
                },
                "health_check": {
                    "enabled": self._health_checking,
                    "interval": self.health_check_interval
                }
            }
            
    def set_strategy(self, strategy: LoadBalancingStrategy):
        """设置负载均衡策略"""
        with self._lock:
            old_strategy = self.strategy
            self.strategy = strategy
            
            # 重置策略状态
            self._round_robin_index = 0
            
            # 更新一致性哈希环
            if strategy == LoadBalancingStrategy.CONSISTENT_HASH:
                self._update_consistent_hash_ring()
                
            self.logger.info(f"负载均衡策略从 {old_strategy.name} 变更为 {strategy.name}")
            
    def _health_check_loop(self):
        """健康检查循环"""
        while self._health_checking:
            try:
                self._perform_health_checks()
                time.sleep(self.health_check_interval)
            except Exception as e:
                self.logger.error(f"健康检查循环异常: {e}")
                time.sleep(60)
                
    def _perform_health_checks(self):
        """执行健康检查"""
        with self._lock:
            nodes_to_check = list(self.nodes.values())
            
        for node in nodes_to_check:
            try:
                is_healthy = self._perform_health_check(node)
                
                with self._lock:
                    node.last_health_check = datetime.now()
                    
                    if is_healthy:
                        if node.status == NodeStatus.UNHEALTHY:
                            node.status = NodeStatus.HEALTHY
                            if node.node_id in self.unhealthy_nodes:
                                self.unhealthy_nodes.remove(node.node_id)
                            if node.node_id not in self.healthy_nodes:
                                self.healthy_nodes.append(node.node_id)
                            self.logger.info(f"节点 {node.name} 恢复健康")
                            
                        node.consecutive_failures = 0
                        
                    else:
                        node.consecutive_failures += 1
                        
                        if (node.consecutive_failures >= self.circuit_breaker_threshold and
                            node.status == NodeStatus.HEALTHY):
                            node.status = NodeStatus.UNHEALTHY
                            if node.node_id in self.healthy_nodes:
                                self.healthy_nodes.remove(node.node_id)
                            if node.node_id not in self.unhealthy_nodes:
                                self.unhealthy_nodes.append(node.node_id)
                            self.logger.warning(f"节点 {node.name} 标记为不健康")
                            
            except Exception as e:
                self.logger.error(f"节点 {node.name} 健康检查失败: {e}")
                
    def _perform_health_check(self, node: ConfigNode) -> bool:
        """执行单个节点的健康检查"""
        try:
            health_url = urljoin(node.base_url, "/health")
            response = self._session.get(
                health_url,
                timeout=min(node.timeout, 10)  # 健康检查超时不超过10秒
            )
            return response.status_code == 200
        except Exception:
            return False
            
    def _send_request(self, node: ConfigNode, url: str, request: LoadBalancingRequest) -> requests.Response:
        """发送HTTP请求"""
        kwargs = {
            'timeout': node.timeout,
            'headers': request.headers
        }
        
        if request.data:
            if request.method.upper() in ['POST', 'PUT', 'PATCH']:
                if isinstance(request.data, dict):
                    kwargs['json'] = request.data
                else:
                    kwargs['data'] = request.data
                    
        method = getattr(self._session, request.method.lower())
        return method(url, **kwargs)
        
    def _record_success(self, node: ConfigNode, response_time: float):
        """记录成功请求"""
        with self._lock:
            # 更新节点统计
            node.total_requests += 1
            node.successful_requests += 1
            node.avg_response_time = (
                (node.avg_response_time * (node.total_requests - 1) + response_time) /
                node.total_requests
            )
            
            # 更新节点统计对象
            node_stats = self.node_stats[node.node_id]
            node_stats.total_requests += 1
            node_stats.successful_requests += 1
            node_stats.avg_response_time = (
                (node_stats.avg_response_time * (node_stats.total_requests - 1) + response_time) /
                node_stats.total_requests
            )
            
            # 更新全局统计
            self.stats.total_requests += 1
            self.stats.successful_requests += 1
            self.stats.avg_response_time = (
                (self.stats.avg_response_time * (self.stats.total_requests - 1) + response_time) /
                self.stats.total_requests
            )
            
            # 记录请求时间
            self._last_requests.append(datetime.now())
            
            # 记录性能指标
            self._monitor.record_metric(
                MetricType.LATENCY,
                response_time,
                "load_balancer",
                "forward_request",
                "ms",
                {"node_id": node.node_id, "result": "success"}
            )
            
    def _record_failure(self, node: ConfigNode):
        """记录失败请求"""
        with self._lock:
            # 更新节点统计
            node.total_requests += 1
            node.failed_requests += 1
            
            # 更新节点统计对象
            node_stats = self.node_stats[node.node_id]
            node_stats.total_requests += 1
            node_stats.failed_requests += 1
            
            # 更新全局统计
            self.stats.total_requests += 1
            self.stats.failed_requests += 1
            
            # 记录错误指标
            self._monitor.record_metric(
                MetricType.ERROR_RATE,
                1.0,
                "load_balancer",
                "forward_request",
                "count",
                {"node_id": node.node_id, "result": "failure"}
            )
            
    def _select_round_robin(self) -> Optional[ConfigNode]:
        """轮询选择"""
        if not self.healthy_nodes:
            return None
            
        node_id = self.healthy_nodes[self._round_robin_index % len(self.healthy_nodes)]
        self._round_robin_index += 1
        return self.nodes[node_id]
        
    def _select_weighted_round_robin(self) -> Optional[ConfigNode]:
        """加权轮询选择"""
        if not self.healthy_nodes:
            return None
            
        # 计算总权重
        total_weight = sum(self.nodes[node_id].weight for node_id in self.healthy_nodes)
        
        if total_weight == 0:
            return self._select_round_robin()
            
        # 根据权重选择
        target_weight = self._round_robin_index % total_weight
        current_weight = 0
        
        for node_id in self.healthy_nodes:
            current_weight += self.nodes[node_id].weight
            if current_weight > target_weight:
                self._round_robin_index += 1
                return self.nodes[node_id]
                
        # 备用方案
        return self._select_round_robin()
        
    def _select_least_connections(self) -> Optional[ConfigNode]:
        """最少连接选择"""
        if not self.healthy_nodes:
            return None
            
        min_connections = float('inf')
        selected_node = None
        
        for node_id in self.healthy_nodes:
            node = self.nodes[node_id]
            if node.current_connections < min_connections:
                min_connections = node.current_connections
                selected_node = node
                
        return selected_node
        
    def _select_least_response_time(self) -> Optional[ConfigNode]:
        """最少响应时间选择"""
        if not self.healthy_nodes:
            return None
            
        min_response_time = float('inf')
        selected_node = None
        
        for node_id in self.healthy_nodes:
            node = self.nodes[node_id]
            if node.avg_response_time < min_response_time:
                min_response_time = node.avg_response_time
                selected_node = node
                
        return selected_node
        
    def _select_ip_hash(self, client_ip: str) -> Optional[ConfigNode]:
        """IP哈希选择"""
        if not self.healthy_nodes:
            return None
            
        # 计算IP哈希
        hash_value = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        index = hash_value % len(self.healthy_nodes)
        
        node_id = self.healthy_nodes[index]
        return self.nodes[node_id]
        
    def _select_consistent_hash(self, client_ip: str) -> Optional[ConfigNode]:
        """一致性哈希选择"""
        if not self.healthy_nodes or not self._consistent_hash_ring:
            return None
            
        # 计算客户端哈希
        client_hash = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        
        # 在哈希环上找到最近的节点
        ring_keys = sorted(self._consistent_hash_ring.keys())
        
        for ring_key in ring_keys:
            if client_hash <= ring_key:
                node_id = self._consistent_hash_ring[ring_key]
                if node_id in self.healthy_nodes:
                    return self.nodes[node_id]
                    
        # 如果没找到，使用第一个节点
        if ring_keys:
            node_id = self._consistent_hash_ring[ring_keys[0]]
            if node_id in self.healthy_nodes:
                return self.nodes[node_id]
                
        return None
        
    def _select_random(self) -> Optional[ConfigNode]:
        """随机选择"""
        if not self.healthy_nodes:
            return None
            
        node_id = random.choice(self.healthy_nodes)
        return self.nodes[node_id]
        
    def _select_health_based(self) -> Optional[ConfigNode]:
        """基于健康状态选择"""
        if not self.healthy_nodes:
            return None
            
        # 计算综合评分：成功率 * 权重 / (响应时间 + 1)
        best_score = 0
        selected_node = None
        
        for node_id in self.healthy_nodes:
            node = self.nodes[node_id]
            
            # 计算评分
            success_rate = node.success_rate
            weight = node.weight / 100.0  # 归一化权重
            response_time_factor = 1 / (node.avg_response_time + 1)
            
            score = success_rate * weight * response_time_factor
            
            if score > best_score:
                best_score = score
                selected_node = node
                
        return selected_node
        
    def _update_consistent_hash_ring(self):
        """更新一致性哈希环"""
        self._consistent_hash_ring.clear()
        
        for node_id in self.healthy_nodes:
            node = self.nodes[node_id]
            
            # 为每个节点创建多个虚拟节点
            virtual_nodes = max(1, node.weight // 10)
            
            for i in range(virtual_nodes):
                virtual_key = f"{node_id}:{i}"
                hash_value = int(hashlib.md5(virtual_key.encode()).hexdigest(), 16)
                self._consistent_hash_ring[hash_value] = node_id


# 全局负载均衡器实例
_global_load_balancer: Optional[ConfigLoadBalancer] = None


def get_config_load_balancer() -> ConfigLoadBalancer:
    """获取全局配置负载均衡器实例"""
    global _global_load_balancer
    if _global_load_balancer is None:
        _global_load_balancer = ConfigLoadBalancer()
        _global_load_balancer.start_health_checks()
    return _global_load_balancer


def load_balance_request(path: str, client_ip: str = "127.0.0.1", method: str = "GET"):
    """负载均衡请求装饰器
    
    Args:
        path: 请求路径
        client_ip: 客户端IP
        method: HTTP方法
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            balancer = get_config_load_balancer()
            
            # 创建请求
            request = LoadBalancingRequest(
                request_id=str(uuid.uuid4()),
                client_ip=client_ip,
                path=path,
                method=method
            )
            
            # 转发请求
            response = balancer.forward_request(request)
            
            if response.success:
                return response.data
            else:
                raise Exception(f"负载均衡请求失败: {response.error}")
                
        return wrapper
    return decorator


# 使用示例
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建负载均衡器
    balancer = ConfigLoadBalancer(
        strategy=LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN,
        health_check_interval=10.0
    )
    
    print("=== 配置负载均衡器测试 ===")
    
    # 添加配置节点（模拟）
    nodes = [
        ConfigNode(
            node_id="node1",
            name="配置节点1",
            host="127.0.0.1",
            port=8001,
            weight=100
        ),
        ConfigNode(
            node_id="node2", 
            name="配置节点2",
            host="127.0.0.1",
            port=8002,
            weight=150
        ),
        ConfigNode(
            node_id="node3",
            name="配置节点3", 
            host="127.0.0.1",
            port=8003,
            weight=80
        )
    ]
    
    for node in nodes:
        success = balancer.add_node(node)
        print(f"{'✓' if success else '✗'} 添加节点: {node.name}")
        
    # 启动健康检查
    balancer.start_health_checks()
    
    # 测试节点选择
    print(f"\n=== 节点选择测试 ({balancer.strategy.name}) ===")
    for i in range(10):
        request = LoadBalancingRequest(
            request_id=f"req_{i}",
            client_ip=f"192.168.1.{i % 10 + 1}",
            path="/config/get"
        )
        
        selected_node = balancer.select_node(request)
        if selected_node:
            print(f"请求 {i+1}: {selected_node.name} (权重: {selected_node.weight})")
        else:
            print(f"请求 {i+1}: 无可用节点")
            
    # 测试不同的负载均衡策略
    strategies = [
        LoadBalancingStrategy.ROUND_ROBIN,
        LoadBalancingStrategy.LEAST_CONNECTIONS,
        LoadBalancingStrategy.RANDOM,
        LoadBalancingStrategy.IP_HASH
    ]
    
    for strategy in strategies:
        print(f"\n=== 策略测试: {strategy.name} ===")
        balancer.set_strategy(strategy)
        
        selected_nodes = []
        for i in range(5):
            request = LoadBalancingRequest(
                request_id=f"test_{i}",
                client_ip="192.168.1.100",
                path="/config/test"
            )
            node = balancer.select_node(request)
            if node:
                selected_nodes.append(node.name)
                
        print(f"选择的节点: {selected_nodes}")
        
    # 显示统计信息
    print(f"\n=== 负载均衡器统计 ===")
    stats = balancer.get_load_balancer_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    # 显示节点状态
    print(f"\n=== 节点状态 ===")
    node_statuses = balancer.get_node_status()
    for status in node_statuses:
        node = status['node']
        stats = status['stats']
        print(f"- {node['name']}: {node['status']}, "
              f"连接: {node['current_connections']}, "
              f"成功率: {stats['success_rate']:.2%}")
        
    # 测试负载均衡装饰器
    @load_balance_request("/config/test", "192.168.1.200")
    def get_config():
        return {"config": "test_value"}
        
    print(f"\n=== 装饰器测试 ===")
    try:
        result = get_config()
        print(f"配置获取结果: {result}")
    except Exception as e:
        print(f"配置获取失败: {e}")
        
    # 停止健康检查
    balancer.stop_health_checks()
    
    print("\n✅ 配置负载均衡器演示完成")