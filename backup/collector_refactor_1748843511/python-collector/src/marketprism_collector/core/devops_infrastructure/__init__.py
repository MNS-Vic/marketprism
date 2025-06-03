"""
MarketPrism DevOps基础设施和CI/CD流水线模块

本模块提供企业级DevOps基础设施能力，包括：
- CI/CD流水线管理
- Docker构建系统
- 环境管理
- 部署自动化
- 测试自动化
- 质量门禁

Week 7 Day 1: DevOps基础设施和CI/CD流水线
"""

from .devops_manager import DevOpsInfrastructureManager
from .ci_pipeline.pipeline_manager import CIPipelineManager
from .docker_system.build_manager import DockerBuildSystem
from .environment.environment_manager import EnvironmentManager
from .deployment.deployment_manager import DeploymentAutomation
from .testing.test_orchestrator import TestAutomation
from .quality_gate.quality_manager import QualityGate

__all__ = [
    'DevOpsInfrastructureManager',
    'CIPipelineManager', 
    'DockerBuildSystem',
    'EnvironmentManager',
    'DeploymentAutomation',
    'TestAutomation',
    'QualityGate'
]

__version__ = '1.0.0'
__author__ = 'MarketPrism DevOps Team'