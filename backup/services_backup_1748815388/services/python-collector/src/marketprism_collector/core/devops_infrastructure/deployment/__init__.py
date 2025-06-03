"""
部署自动化模块

提供自动化部署能力，包括：
- 多种部署策略
- 自动回滚
- 部署监控
"""

from .deployment_manager import DeploymentAutomation

__all__ = ['DeploymentAutomation']