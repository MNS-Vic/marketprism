"""
MarketPrism API网关核心模块

Week 6 Day 1: API网关核心系统
- 请求路由引擎: 动态路由配置、路径匹配和重写、请求转发和代理
- 负载均衡器: 多种负载均衡算法、健康检查和故障转移、服务实例管理
- API Gateway Manager: 网关配置管理、路由规则管理、服务注册管理
"""

from .routing_engine import RoutingEngine, RouteRule, RouteMatch, HTTPMethod, RouteMatchType
from .load_balancer import LoadBalancer, LoadBalancingStrategy, ServiceInstance, ServiceStatus  
from .gateway_manager import APIGatewayManager, GatewayConfig, ServiceRegistration
from .request_handler import RequestHandler, ResponseHandler, RequestContext, ResponseContext
from .health_checker import HealthChecker, HealthStatus, CheckType

__all__ = [
    # 路由引擎
    'RoutingEngine',
    'RouteRule', 
    'RouteMatch',
    'HTTPMethod',
    'RouteMatchType',
    
    # 负载均衡
    'LoadBalancer',
    'LoadBalancingStrategy',
    'ServiceInstance',
    'ServiceStatus',
    
    # 网关管理
    'APIGatewayManager',
    'GatewayConfig',
    'ServiceRegistration',
    
    # 请求处理
    'RequestHandler',
    'ResponseHandler',
    'RequestContext',
    'ResponseContext',
    
    # 健康检查
    'HealthChecker',
    'HealthStatus',
    'CheckType'
]

__version__ = "1.0.0"
__author__ = "MarketPrism Team"
__description__ = "Enterprise-grade API Gateway Core System"