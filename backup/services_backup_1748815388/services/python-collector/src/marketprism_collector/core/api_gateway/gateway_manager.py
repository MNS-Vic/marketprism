"""
MarketPrism API网关 - 网关管理器

统一的API网关配置管理、路由规则管理、服务注册管理

Week 6 Day 1 核心组件
"""

import time
import json
import logging
import threading
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from .routing_engine import RoutingEngine, RouteRule, RouteMatch, HTTPMethod, RouteMatchType
from .load_balancer import LoadBalancer, ServiceInstance, LoadBalancingStrategy, ServiceStatus
from .health_checker import HealthChecker, HealthStatus

# 设置日志
logger = logging.getLogger(__name__)

class GatewayStatus(Enum):
    """网关状态"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class GatewayConfig:
    """网关配置"""
    # 基本配置
    gateway_id: str
    name: str = "MarketPrism API Gateway"
    version: str = "1.0.0"
    
    # 网络配置
    host: str = "0.0.0.0"
    port: int = 8080
    max_connections: int = 1000
    request_timeout: float = 30.0
    
    # 路由配置
    default_load_balancing_strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN
    enable_routing_cache: bool = True
    routing_cache_ttl: int = 300  # 秒
    
    # 健康检查配置
    enable_health_check: bool = True
    health_check_interval: int = 30  # 秒
    health_check_timeout: int = 5   # 秒
    health_check_retries: int = 3
    
    # 监控配置
    enable_metrics: bool = True
    metrics_port: int = 9090
    enable_tracing: bool = True
    
    # 安全配置
    enable_cors: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    enable_rate_limiting: bool = True
    default_rate_limit: int = 1000  # 每分钟请求数
    
    # 日志配置
    log_level: str = "INFO"
    log_format: str = "json"
    enable_access_log: bool = True
    
    # 存储配置
    config_storage_path: str = "./config/gateway"
    enable_config_persistence: bool = True
    
    # 高级配置
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 10
    circuit_breaker_timeout: int = 60
    
    # 中间件配置
    middleware_config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GatewayConfig':
        """从字典创建配置"""
        # 处理枚举类型
        if 'default_load_balancing_strategy' in data:
            strategy_value = data['default_load_balancing_strategy']
            if isinstance(strategy_value, str):
                data['default_load_balancing_strategy'] = LoadBalancingStrategy(strategy_value)
        
        return cls(**data)

@dataclass
class ServiceRegistration:
    """服务注册信息"""
    service_id: str
    service_name: str
    instances: List[ServiceInstance]
    load_balancing_strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN
    health_check_path: str = "/health"
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

class APIGatewayManager:
    """
    API网关管理器
    
    统一管理API网关的配置、路由、负载均衡、健康检查等功能
    """
    
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.status = GatewayStatus.INITIALIZING
        self._lock = threading.RLock()
        
        # 核心组件
        self.routing_engine = RoutingEngine(enable_metrics=config.enable_metrics)
        self.load_balancer = LoadBalancer(
            strategy=config.default_load_balancing_strategy,
            enable_health_check=config.enable_health_check,
            enable_metrics=config.enable_metrics
        )
        self.health_checker = HealthChecker(
            check_interval=config.health_check_interval,
            check_timeout=config.health_check_timeout,
            max_retries=config.health_check_retries
        )
        
        # 服务注册表
        self.service_registry: Dict[str, ServiceRegistration] = {}
        
        # 中间件
        self.middleware_stack: List[Callable] = []
        
        # 统计信息
        self.stats = {
            'start_time': time.time(),
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_response_time': 0.0,
            'service_requests': {},
            'route_requests': {},
        }
        
        # 线程池
        self.executor = ThreadPoolExecutor(
            max_workers=10, 
            thread_name_prefix="gateway-manager"
        )
        
        # 配置存储
        self.config_storage_path = Path(config.config_storage_path)
        self.config_storage_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"APIGatewayManager initialized: {config.gateway_id}")
    
    def start(self) -> bool:
        """启动网关"""
        try:
            with self._lock:
                if self.status != GatewayStatus.INITIALIZING:
                    logger.warning(f"Gateway already in state: {self.status.value}")
                    return False
                
                logger.info("Starting API Gateway...")
                
                # 加载持久化配置
                if self.config.enable_config_persistence:
                    self._load_persisted_config()
                
                # 启动健康检查
                if self.config.enable_health_check:
                    self.health_checker.start()
                
                # 注册默认路由
                self._register_default_routes()
                
                self.status = GatewayStatus.RUNNING
                self.stats['start_time'] = time.time()
                
                logger.info(f"API Gateway started successfully on {self.config.host}:{self.config.port}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to start API Gateway: {e}")
            self.status = GatewayStatus.ERROR
            return False
    
    def stop(self) -> bool:
        """停止网关"""
        try:
            with self._lock:
                if self.status not in [GatewayStatus.RUNNING, GatewayStatus.ERROR]:
                    logger.warning(f"Gateway not running, current state: {self.status.value}")
                    return False
                
                logger.info("Stopping API Gateway...")
                self.status = GatewayStatus.STOPPING
                
                # 保存配置
                if self.config.enable_config_persistence:
                    self._persist_config()
                
                # 停止健康检查
                self.health_checker.stop()
                
                # 清理资源
                self.routing_engine.cleanup()
                self.load_balancer.cleanup()
                self.health_checker.cleanup()
                self.executor.shutdown(wait=True)
                
                self.status = GatewayStatus.STOPPED
                logger.info("API Gateway stopped successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to stop API Gateway: {e}")
            self.status = GatewayStatus.ERROR
            return False
    
    def register_service(self, registration: ServiceRegistration) -> bool:
        """
        注册服务
        
        Args:
            registration: 服务注册信息
            
        Returns:
            bool: 是否注册成功
        """
        try:
            with self._lock:
                service_id = registration.service_id
                
                # 检查服务是否已存在
                if service_id in self.service_registry:
                    logger.warning(f"Service {service_id} already registered, updating")
                
                # 注册到负载均衡器
                self.load_balancer.add_service(registration.service_name, registration.instances)
                
                # 设置负载均衡策略
                if registration.load_balancing_strategy != self.config.default_load_balancing_strategy:
                    # TODO: 支持每个服务独立的负载均衡策略
                    pass
                
                # 注册健康检查
                if self.config.enable_health_check:
                    for instance in registration.instances:
                        self.health_checker.add_target(
                            target_id=instance.instance_id,
                            host=instance.host,
                            port=instance.port,
                            check_path=registration.health_check_path
                        )
                
                # 存储服务注册信息
                registration.updated_at = time.time()
                self.service_registry[service_id] = registration
                
                # 初始化统计
                self.stats['service_requests'][service_id] = {
                    'total': 0,
                    'success': 0,
                    'failure': 0,
                    'avg_response_time': 0.0
                }
                
                logger.info(f"Service {service_id} registered successfully with {len(registration.instances)} instances")
                return True
                
        except Exception as e:
            logger.error(f"Failed to register service {registration.service_id}: {e}")
            return False
    
    def unregister_service(self, service_id: str) -> bool:
        """
        注销服务
        
        Args:
            service_id: 服务ID
            
        Returns:
            bool: 是否注销成功
        """
        try:
            with self._lock:
                if service_id not in self.service_registry:
                    logger.warning(f"Service {service_id} not found")
                    return False
                
                registration = self.service_registry[service_id]
                
                # 从健康检查中移除
                if self.config.enable_health_check:
                    for instance in registration.instances:
                        self.health_checker.remove_target(instance.instance_id)
                
                # 移除路由规则（如果有关联的）
                routes_to_remove = []
                for rule_id, route_rule in self.routing_engine.route_rules.items():
                    if route_rule.target_service == registration.service_name:
                        routes_to_remove.append(rule_id)
                
                for rule_id in routes_to_remove:
                    self.routing_engine.remove_route(rule_id)
                
                # 从服务注册表中移除
                del self.service_registry[service_id]
                
                # 清理统计
                self.stats['service_requests'].pop(service_id, None)
                
                logger.info(f"Service {service_id} unregistered successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to unregister service {service_id}: {e}")
            return False
    
    def add_route(self, route_rule: RouteRule) -> bool:
        """
        添加路由规则
        
        Args:
            route_rule: 路由规则
            
        Returns:
            bool: 是否添加成功
        """
        try:
            with self._lock:
                # 验证目标服务是否存在
                if route_rule.target_service:
                    service_exists = any(
                        reg.service_name == route_rule.target_service 
                        for reg in self.service_registry.values()
                    )
                    if not service_exists:
                        logger.warning(f"Target service {route_rule.target_service} not registered")
                
                # 添加路由
                success = self.routing_engine.add_route(route_rule)
                
                if success:
                    # 初始化路由统计
                    self.stats['route_requests'][route_rule.rule_id] = {
                        'total': 0,
                        'success': 0,
                        'failure': 0,
                        'avg_response_time': 0.0
                    }
                    
                    logger.info(f"Route {route_rule.rule_id} added successfully")
                
                return success
                
        except Exception as e:
            logger.error(f"Failed to add route {route_rule.rule_id}: {e}")
            return False
    
    def remove_route(self, rule_id: str) -> bool:
        """
        移除路由规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            bool: 是否移除成功
        """
        try:
            with self._lock:
                success = self.routing_engine.remove_route(rule_id)
                
                if success:
                    # 清理统计
                    self.stats['route_requests'].pop(rule_id, None)
                    logger.info(f"Route {rule_id} removed successfully")
                
                return success
                
        except Exception as e:
            logger.error(f"Failed to remove route {rule_id}: {e}")
            return False
    
    def route_request(self, path: str, method: str = "GET", 
                     headers: Optional[Dict[str, str]] = None,
                     client_ip: str = None) -> Optional[ServiceInstance]:
        """
        路由请求到合适的服务实例
        
        Args:
            path: 请求路径
            method: HTTP方法
            headers: 请求头
            client_ip: 客户端IP
            
        Returns:
            ServiceInstance: 选中的服务实例，如果路由失败则返回None
        """
        start_time = time.time()
        
        try:
            with self._lock:
                # 更新总体统计
                self.stats['total_requests'] += 1
                
                # 路由匹配
                http_method = HTTPMethod(method.upper()) if method.upper() in HTTPMethod.__members__ else HTTPMethod.GET
                match_result = self.routing_engine.match_route(path, http_method, headers)
                
                if not match_result.matched or not match_result.route_rule:
                    logger.warning(f"No route found for {method} {path}")
                    self.stats['failed_requests'] += 1
                    return None
                
                route_rule = match_result.route_rule
                
                # 构建请求上下文
                request_context = {
                    'path': path,
                    'method': method,
                    'headers': headers or {},
                    'client_ip': client_ip or 'unknown',
                    'route_rule': route_rule,
                    'path_params': match_result.path_params,
                    'query_params': match_result.query_params,
                }
                
                # 选择服务实例
                selected_instance = self.load_balancer.select_instance(
                    route_rule.target_service, request_context
                )
                
                if selected_instance:
                    # 更新统计
                    self.stats['successful_requests'] += 1
                    
                    # 更新路由统计
                    if route_rule.rule_id in self.stats['route_requests']:
                        self.stats['route_requests'][route_rule.rule_id]['total'] += 1
                    
                    # 更新服务统计
                    service_id = self._find_service_id_by_name(route_rule.target_service)
                    if service_id and service_id in self.stats['service_requests']:
                        self.stats['service_requests'][service_id]['total'] += 1
                    
                    logger.debug(f"Routed {method} {path} to {selected_instance.address}")
                else:
                    self.stats['failed_requests'] += 1
                    logger.warning(f"No available instances for service {route_rule.target_service}")
                
                return selected_instance
                
        except Exception as e:
            logger.error(f"Error routing request {method} {path}: {e}")
            self.stats['failed_requests'] += 1
            return None
    
    def update_request_stats(self, route_rule_id: str, service_name: str, 
                           response_time: float, success: bool):
        """
        更新请求统计信息
        
        Args:
            route_rule_id: 路由规则ID
            service_name: 服务名称
            response_time: 响应时间
            success: 是否成功
        """
        with self._lock:
            # 更新总体统计
            self.stats['total_response_time'] += response_time
            
            # 更新路由统计
            if route_rule_id in self.stats['route_requests']:
                route_stats = self.stats['route_requests'][route_rule_id]
                if success:
                    route_stats['success'] += 1
                else:
                    route_stats['failure'] += 1
                
                # 更新平均响应时间
                total_requests = route_stats['success'] + route_stats['failure']
                if total_requests > 0:
                    route_stats['avg_response_time'] = (
                        (route_stats['avg_response_time'] * (total_requests - 1) + response_time) 
                        / total_requests
                    )
            
            # 更新服务统计
            service_id = self._find_service_id_by_name(service_name)
            if service_id and service_id in self.stats['service_requests']:
                service_stats = self.stats['service_requests'][service_id]
                if success:
                    service_stats['success'] += 1
                else:
                    service_stats['failure'] += 1
                
                # 更新平均响应时间
                total_requests = service_stats['success'] + service_stats['failure']
                if total_requests > 0:
                    service_stats['avg_response_time'] = (
                        (service_stats['avg_response_time'] * (total_requests - 1) + response_time) 
                        / total_requests
                    )
    
    def _find_service_id_by_name(self, service_name: str) -> Optional[str]:
        """根据服务名称查找服务ID"""
        for service_id, registration in self.service_registry.items():
            if registration.service_name == service_name:
                return service_id
        return None
    
    def _register_default_routes(self):
        """注册默认路由"""
        # 健康检查路由
        health_route = RouteRule(
            rule_id="gateway_health",
            name="Gateway Health Check",
            path_pattern="/health",
            methods=[HTTPMethod.GET],
            target_service="gateway_internal",
            priority=1
        )
        self.routing_engine.add_route(health_route)
        
        # 统计信息路由
        stats_route = RouteRule(
            rule_id="gateway_stats", 
            name="Gateway Statistics",
            path_pattern="/stats",
            methods=[HTTPMethod.GET],
            target_service="gateway_internal",
            priority=1
        )
        self.routing_engine.add_route(stats_route)
        
        # 管理API路由
        admin_route = RouteRule(
            rule_id="gateway_admin",
            name="Gateway Admin API",
            path_pattern="/admin/*",
            methods=[HTTPMethod.ANY],
            target_service="gateway_admin",
            priority=1
        )
        self.routing_engine.add_route(admin_route)
    
    def _load_persisted_config(self):
        """加载持久化配置"""
        try:
            config_file = self.config_storage_path / "gateway_config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    data = json.load(f)
                
                # 加载服务注册信息
                if 'services' in data:
                    for service_data in data['services']:
                        # TODO: 实现服务注册信息的反序列化
                        pass
                
                # 加载路由规则
                if 'routes' in data:
                    for route_data in data['routes']:
                        # TODO: 实现路由规则的反序列化
                        pass
                
                logger.info("Persisted configuration loaded successfully")
                
        except Exception as e:
            logger.error(f"Failed to load persisted configuration: {e}")
    
    def _persist_config(self):
        """持久化配置"""
        try:
            config_data = {
                'gateway_id': self.config.gateway_id,
                'timestamp': time.time(),
                'services': [],
                'routes': [],
                'stats': self.stats.copy()
            }
            
            # 序列化服务注册信息
            for service_id, registration in self.service_registry.items():
                # TODO: 实现服务注册信息的序列化
                pass
            
            # 序列化路由规则
            for rule_id, route_rule in self.routing_engine.route_rules.items():
                # TODO: 实现路由规则的序列化
                pass
            
            config_file = self.config_storage_path / "gateway_config.json"
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2, default=str)
            
            logger.info("Configuration persisted successfully")
            
        except Exception as e:
            logger.error(f"Failed to persist configuration: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取网关状态"""
        with self._lock:
            uptime = time.time() - self.stats['start_time']
            
            status = {
                'gateway_id': self.config.gateway_id,
                'status': self.status.value,
                'uptime': uptime,
                'config': self.config.to_dict(),
                'stats': self.stats.copy(),
                'services': len(self.service_registry),
                'routes': len(self.routing_engine.route_rules),
                'routing_stats': self.routing_engine.get_stats(),
                'load_balancer_stats': self.load_balancer.get_load_balancer_stats(),
                'health_checker_stats': self.health_checker.get_stats(),
            }
            
            # 计算成功率
            if self.stats['total_requests'] > 0:
                status['success_rate'] = (
                    self.stats['successful_requests'] / self.stats['total_requests'] * 100
                )
                status['average_response_time'] = (
                    self.stats['total_response_time'] / self.stats['successful_requests']
                    if self.stats['successful_requests'] > 0 else 0.0
                )
            else:
                status['success_rate'] = 0.0
                status['average_response_time'] = 0.0
            
            return status
    
    def get_service_info(self, service_id: str) -> Optional[Dict[str, Any]]:
        """获取服务信息"""
        with self._lock:
            if service_id not in self.service_registry:
                return None
            
            registration = self.service_registry[service_id]
            service_stats = self.load_balancer.get_service_stats(registration.service_name)
            
            return {
                'service_id': service_id,
                'service_name': registration.service_name,
                'load_balancing_strategy': registration.load_balancing_strategy.value,
                'health_check_path': registration.health_check_path,
                'tags': registration.tags,
                'created_at': registration.created_at,
                'updated_at': registration.updated_at,
                'instances': len(registration.instances),
                'stats': service_stats,
                'request_stats': self.stats['service_requests'].get(service_id, {})
            }
    
    def list_services(self) -> List[Dict[str, Any]]:
        """列出所有服务"""
        with self._lock:
            services = []
            for service_id in self.service_registry:
                service_info = self.get_service_info(service_id)
                if service_info:
                    services.append(service_info)
            return services
    
    def list_routes(self) -> List[Dict[str, Any]]:
        """列出所有路由"""
        with self._lock:
            routes = []
            for route_rule in self.routing_engine.list_routes():
                route_info = {
                    'rule_id': route_rule.rule_id,
                    'name': route_rule.name,
                    'path_pattern': route_rule.path_pattern,
                    'methods': [method.value for method in route_rule.methods],
                    'match_type': route_rule.match_type.value,
                    'target_service': route_rule.target_service,
                    'target_path': route_rule.target_path,
                    'priority': route_rule.priority,
                    'enabled': route_rule.enabled,
                    'timeout': route_rule.timeout,
                    'retry_count': route_rule.retry_count,
                    'created_at': route_rule.created_at,
                    'updated_at': route_rule.updated_at,
                    'tags': route_rule.tags,
                    'stats': self.stats['route_requests'].get(route_rule.rule_id, {})
                }
                routes.append(route_info)
            return routes
    
    def cleanup(self):
        """清理资源"""
        logger.info("Cleaning up APIGatewayManager")
        
        # 停止网关（如果还在运行）
        if self.status == GatewayStatus.RUNNING:
            self.stop()
        
        # 清理组件
        self.routing_engine.cleanup()
        self.load_balancer.cleanup()
        self.health_checker.cleanup()
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        # 清理数据
        with self._lock:
            self.service_registry.clear()
            self.middleware_stack.clear()
            self.stats = {
                'start_time': time.time(),
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'total_response_time': 0.0,
                'service_requests': {},
                'route_requests': {},
            }

# 便利函数
def create_gateway_config(gateway_id: str, **kwargs) -> GatewayConfig:
    """创建网关配置的便利函数"""
    return GatewayConfig(gateway_id=gateway_id, **kwargs)

def create_service_registration(service_id: str, service_name: str, 
                              instances: List[ServiceInstance], **kwargs) -> ServiceRegistration:
    """创建服务注册信息的便利函数"""
    return ServiceRegistration(
        service_id=service_id,
        service_name=service_name,
        instances=instances,
        **kwargs
    )