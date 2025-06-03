"""
CI/CD流水线系统

提供企业级CI/CD流水线管理能力，包括：
- 多阶段流水线管理
- 并行执行和智能重试
- 状态跟踪和通知
- 性能监控和优化
"""

from .pipeline_manager import (
    CIPipelineManager, 
    PipelineConfig, 
    PipelineResult,
    StageConfig,
    StageResult,
    PipelineStatus,
    StageStatus,
    StageType
)
from .build_stage import BuildStage
from .test_stage import TestStage
from .deploy_stage import DeployStage
from .validation_stage import ValidationStage

__all__ = [
    'CIPipelineManager',
    'PipelineConfig', 
    'PipelineResult',
    'StageConfig',
    'StageResult',
    'PipelineStatus',
    'StageStatus',
    'StageType',
    'BuildStage',
    'TestStage',
    'DeployStage',
    'ValidationStage'
]