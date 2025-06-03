#!/usr/bin/env python3
"""
MarketPrism 微服务服务发现系统

这个模块提供了完整的企业级微服务服务发现能力，包括：
- 服务注册中心：集中式服务实例管理
- 服务发现机制：动态服务查找和路由
- 健康检查系统：实时服务健康监控
- 负载均衡集成：与负载均衡器深度集成
- 服务路由引擎：智能服务路由决策
- 故障检测恢复：自动故障转移和恢复

Week 6 Day 2: 微服务服务发现系统
开发日期: 2025年5月31日
"""

from .service_registry import (
    ServiceRegistry,
    ServiceRegistryConfig,
    ServiceInstance,
    ServiceMetadata,
    ServiceStatus,
    ServiceEndpoint,
    RegistrationRequest,
    RegistrationResponse,
    DeregistrationRequest,
    RegistryEvent,
    RegistryEventType,
    ServiceFilter,
    ServiceQuery,
    ServiceRegistryError,
    ServiceNotFoundError,
    ServiceAlreadyExistsError,
    RegistryUnavailableError
)

from .service_discovery import (
    ServiceDiscovery,
    ServiceDiscoveryConfig,
    DiscoveryRequest,
    DiscoveryResponse,
    ServiceResolution,
    ResolutionStrategy,
    DiscoveryCache,
    DiscoveryCacheConfig,
    ServiceWatcher,
    WatchEvent,
    WatchEventType,
    ServiceDiscoveryError,
    ServiceResolutionError,
    DiscoveryTimeoutError
)

from .service_routing import (
    ServiceRouter,
    ServiceRoutingConfig,
    RoutingRule,
    RoutingTarget,
    RoutingDecision,
    RoutingStrategy,
    RoutingContext,
    RouteMatch,
    RoutingPolicy,
    RoutingMetrics,
    ServiceRoutingError,
    RoutingRuleError,
    RoutingTargetError
)

from .health_monitor import (
    ServiceHealthMonitor,
    HealthCheckConfig,
    HealthCheck,
    HealthCheckResult,
    HealthStatus,
    HealthCheckType,
    HealthThreshold,
    HealthMetrics,
    HealthAlert,
    HealthAlertLevel,
    HealthMonitorError,
    HealthCheckFailedError,
    HealthThresholdExceededError
)

from .failover_manager import (
    FailoverManager,
    FailoverConfig,
    FailoverStrategy,
    FailoverTrigger,
    FailoverAction,
    FailoverState,
    FailoverEvent,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    RetryPolicy,
    BackoffStrategy,
    FailoverError,
    CircuitBreakerOpenError,
    RetryExhaustedError
)

from .service_mesh_integration import (
    ServiceMeshIntegration,
    ServiceMeshConfig,
    MeshTopology,
    ServiceMeshNode,
    MeshConnection,
    TrafficPolicy,
    SecurityPolicy,
    TrafficPolicyType,
    SecurityPolicyType,
    MeshTopologyType,
    ObservabilityConfig,
    MeshMetrics,
    ServiceMeshError,
    MeshConnectionError,
    PolicyEnforcementError
)

__all__ = [
    # Service Registry
    "ServiceRegistry",
    "ServiceRegistryConfig", 
    "ServiceInstance",
    "ServiceMetadata",
    "ServiceStatus",
    "ServiceEndpoint",
    "RegistrationRequest",
    "RegistrationResponse",
    "DeregistrationRequest",
    "RegistryEvent",
    "RegistryEventType",
    "ServiceFilter",
    "ServiceQuery",
    "ServiceRegistryError",
    "ServiceNotFoundError",
    "ServiceAlreadyExistsError",
    "RegistryUnavailableError",
    
    # Service Discovery
    "ServiceDiscovery",
    "ServiceDiscoveryConfig",
    "DiscoveryRequest",
    "DiscoveryResponse",
    "ServiceResolution",
    "ResolutionStrategy",
    "DiscoveryCache",
    "DiscoveryCacheConfig",
    "ServiceWatcher",
    "WatchEvent",
    "WatchEventType",
    "ServiceDiscoveryError",
    "ServiceResolutionError",
    "DiscoveryTimeoutError",
    
    # Service Routing
    "ServiceRouter",
    "ServiceRoutingConfig",
    "RoutingRule",
    "RoutingTarget",
    "RoutingDecision",
    "RoutingStrategy",
    "RoutingContext",
    "RouteMatch",
    "RoutingPolicy",
    "RoutingMetrics",
    "ServiceRoutingError",
    "RoutingRuleError", 
    "RoutingTargetError",
    
    # Health Monitor
    "ServiceHealthMonitor",
    "HealthCheckConfig",
    "HealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "HealthCheckType",
    "HealthThreshold",
    "HealthMetrics",
    "HealthAlert",
    "HealthAlertLevel",
    "HealthMonitorError",
    "HealthCheckFailedError",
    "HealthThresholdExceededError",
    
    # Failover Manager
    "FailoverManager",
    "FailoverConfig",
    "FailoverStrategy",
    "FailoverTrigger",
    "FailoverAction",
    "FailoverState",
    "FailoverEvent",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "RetryPolicy",
    "BackoffStrategy",
    "FailoverError",
    "CircuitBreakerOpenError",
    "RetryExhaustedError",
    
    # Service Mesh Integration
    "ServiceMeshIntegration",
    "ServiceMeshConfig",
    "MeshTopology",
    "ServiceMeshNode",
    "MeshConnection",
    "TrafficPolicy",
    "SecurityPolicy",
    "TrafficPolicyType",
    "SecurityPolicyType",
    "MeshTopologyType",
    "ObservabilityConfig",
    "MeshMetrics",
    "ServiceMeshError",
    "MeshConnectionError",
    "PolicyEnforcementError"
]

# 版本信息
__version__ = "1.0.0"
__author__ = "MarketPrism Team"
__description__ = "企业级微服务服务发现系统"