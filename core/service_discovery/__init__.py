"""
MarketPrism 服务发现模块

提供分布式环境下的服务注册、发现和健康检查功能
支持多种后端：Consul、etcd、NATS、Redis等
"""

from .registry import ServiceRegistry, ServiceInstance, ServiceStatus
from .discovery_client import ServiceDiscoveryClient
from .backends import ConsulBackend, EtcdBackend, NATSBackend, RedisBackend, InMemoryBackend

__all__ = [
    'ServiceRegistry',
    'ServiceInstance', 
    'ServiceStatus',
    'ServiceDiscoveryClient',
    'ConsulBackend',
    'EtcdBackend', 
    'NATSBackend',
    'RedisBackend',
    'InMemoryBackend'
]

__version__ = '1.0.0' 