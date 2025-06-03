"""
MarketPrism Kubernetes编排系统

企业级Kubernetes容器编排和管理平台，提供：
- 集群管理和节点编排
- 工作负载生命周期管理
- 服务网格集成和治理
- 自动扩缩容和资源优化
- 配置和密钥管理
- 存储编排和数据管理

Author: MarketPrism Team
Date: 2025-06-02
Version: 1.0.0
"""

from .kubernetes_orchestration_manager import KubernetesOrchestrationManager
from .cluster_management.cluster_manager import KubernetesClusterManager
from .workload_orchestration.workload_orchestrator import WorkloadOrchestrator
from .service_mesh.service_mesh_integration import ServiceMeshIntegration
from .auto_scaling.auto_scaler import AutoScaler
from .config_management.configmap_manager import ConfigMapManager
from .storage_orchestration.storage_orchestrator import StorageOrchestrator

__all__ = [
    'KubernetesOrchestrationManager',
    'KubernetesClusterManager',
    'WorkloadOrchestrator',
    'ServiceMeshIntegration',
    'AutoScaler',
    'ConfigMapManager',
    'StorageOrchestrator'
]

__version__ = "1.0.0"
__author__ = "MarketPrism Team"