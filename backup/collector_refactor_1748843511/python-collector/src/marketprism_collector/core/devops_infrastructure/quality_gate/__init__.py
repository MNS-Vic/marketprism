"""
质量门禁模块

提供质量门禁能力，包括：
- 代码质量检查
- 安全扫描
- 性能基准
"""

from .quality_manager import QualityGate

__all__ = ['QualityGate']