"""
Kubernetes自动扩缩容模块

提供企业级自动扩缩容管理功能：
- 水平Pod自动扩缩容（HPA）
- 垂直Pod自动扩缩容（VPA）
- 集群自动扩缩容（CA）
- 自定义指标扩缩容
- 预测性扩缩容

Author: MarketPrism Team
Date: 2025-06-02
"""

from .auto_scaler import AutoScaler
from .hpa_manager import HPAManager
from .vpa_manager import VPAManager
from .cluster_autoscaler import ClusterAutoscaler

__all__ = [
    'AutoScaler',
    'HPAManager',
    'VPAManager',
    'ClusterAutoscaler'
]