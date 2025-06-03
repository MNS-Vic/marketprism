"""
企业级安全合规和审计自动化系统

Week 5 Day 7 - 为MarketPrism项目提供完整的安全合规管理、自动化审计和企业级安全治理能力

主要组件：
1. ComplianceManager - 合规管理器
2. AuditSystem - 审计系统
3. RiskAssessmentEngine - 风险评估引擎
4. SecurityGovernance - 安全治理
5. RegulatoryCompliance - 法规遵循系统

Author: MarketPrism Team
Date: 2025-01-28
Version: 1.0.0
"""

from .compliance_manager import ComplianceManager
from .audit_system import AuditSystem
from .risk_assessment_engine import RiskAssessmentEngine
from .security_governance import SecurityGovernance
from .regulatory_compliance import RegulatoryCompliance

__all__ = [
    'ComplianceManager',
    'AuditSystem', 
    'RiskAssessmentEngine',
    'SecurityGovernance',
    'RegulatoryCompliance'
]

__version__ = "1.0.0"