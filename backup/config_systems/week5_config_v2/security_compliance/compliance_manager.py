"""
企业级合规管理器

提供自动化的合规检查、合规状态跟踪、合规报告生成和合规计划管理功能。
支持多种合规框架和标准，实现企业级合规管理能力。

Author: MarketPrism Team
Date: 2025-01-28
"""

import time
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum
from dataclasses import dataclass, asdict
import logging
from concurrent.futures import ThreadPoolExecutor
import threading

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComplianceStatus(Enum):
    """合规状态枚举"""
    COMPLIANT = "compliant"           # 合规
    NON_COMPLIANT = "non_compliant"   # 不合规
    PARTIAL = "partial"               # 部分合规
    UNKNOWN = "unknown"               # 未知状态
    PENDING = "pending"               # 待检查
    REVIEWING = "reviewing"           # 审查中

class ComplianceFramework(Enum):
    """合规框架枚举"""
    SOX = "sox"                       # 萨班斯-奥克斯利法案
    GDPR = "gdpr"                     # 通用数据保护条例
    HIPAA = "hipaa"                   # 健康保险可携性和责任法案
    PCI_DSS = "pci_dss"              # 支付卡行业数据安全标准
    ISO_27001 = "iso_27001"          # ISO 27001信息安全管理体系
    SOC2 = "soc2"                    # SOC 2审计标准
    NIST = "nist"                    # NIST网络安全框架
    CIS = "cis"                      # CIS控制
    COBIT = "cobit"                  # COBIT治理框架
    FISMA = "fisma"                  # 联邦信息安全管理法

class ComplianceSeverity(Enum):
    """合规严重程度"""
    CRITICAL = "critical"             # 严重
    HIGH = "high"                     # 高
    MEDIUM = "medium"                 # 中等
    LOW = "low"                       # 低
    INFO = "info"                     # 信息

@dataclass
class ComplianceRequirement:
    """合规要求数据类"""
    id: str
    framework: ComplianceFramework
    title: str
    description: str
    control_id: str
    severity: ComplianceSeverity
    mandatory: bool
    automated: bool
    check_function: Optional[str] = None
    remediation_steps: List[str] = None
    reference_links: List[str] = None
    
    def __post_init__(self):
        if self.remediation_steps is None:
            self.remediation_steps = []
        if self.reference_links is None:
            self.reference_links = []

@dataclass
class ComplianceResult:
    """合规检查结果数据类"""
    requirement_id: str
    status: ComplianceStatus
    score: float  # 0.0-1.0
    details: str
    evidence: List[str]
    recommendations: List[str]
    check_time: datetime
    next_check_time: datetime
    remediation_deadline: Optional[datetime] = None
    
    def __post_init__(self):
        if not self.evidence:
            self.evidence = []
        if not self.recommendations:
            self.recommendations = []

@dataclass
class CompliancePlan:
    """合规计划数据类"""
    id: str
    name: str
    framework: ComplianceFramework
    requirements: List[str]  # requirement IDs
    start_date: datetime
    end_date: datetime
    responsible_team: str
    status: str
    progress: float  # 0.0-1.0
    created_at: datetime
    updated_at: datetime

class ComplianceManager:
    """企业级合规管理器"""
    
    def __init__(self):
        """初始化合规管理器"""
        self.requirements: Dict[str, ComplianceRequirement] = {}
        self.results: Dict[str, ComplianceResult] = {}
        self.plans: Dict[str, CompliancePlan] = {}
        self.compliance_history: List[Dict[str, Any]] = []
        self.monitoring_enabled = False
        self.monitor_thread = None
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._lock = threading.Lock()
        
        # 初始化默认合规要求
        self._initialize_default_requirements()
        
        logger.info("ComplianceManager 初始化完成")
    
    def _initialize_default_requirements(self):
        """初始化默认合规要求"""
        default_requirements = [
            # SOX合规要求
            ComplianceRequirement(
                id="sox-001",
                framework=ComplianceFramework.SOX,
                title="财务数据访问控制",
                description="确保只有授权人员可以访问财务相关数据",
                control_id="SOX-302",
                severity=ComplianceSeverity.CRITICAL,
                mandatory=True,
                automated=True,
                check_function="check_financial_data_access",
                remediation_steps=[
                    "审查财务数据访问权限",
                    "实施基于角色的访问控制",
                    "定期审计访问日志"
                ]
            ),
            # GDPR合规要求
            ComplianceRequirement(
                id="gdpr-001",
                framework=ComplianceFramework.GDPR,
                title="个人数据加密",
                description="确保个人数据在传输和存储时被加密",
                control_id="GDPR-32",
                severity=ComplianceSeverity.HIGH,
                mandatory=True,
                automated=True,
                check_function="check_personal_data_encryption",
                remediation_steps=[
                    "启用数据传输加密",
                    "配置数据库加密",
                    "验证加密密钥管理"
                ]
            ),
            # PCI DSS合规要求
            ComplianceRequirement(
                id="pci-001",
                framework=ComplianceFramework.PCI_DSS,
                title="支付数据保护",
                description="保护支付卡数据的安全性",
                control_id="PCI-3.4",
                severity=ComplianceSeverity.CRITICAL,
                mandatory=True,
                automated=True,
                check_function="check_payment_data_protection",
                remediation_steps=[
                    "实施支付数据加密",
                    "配置安全的支付处理",
                    "定期安全扫描"
                ]
            ),
            # ISO 27001合规要求
            ComplianceRequirement(
                id="iso27001-001",
                framework=ComplianceFramework.ISO_27001,
                title="信息安全策略",
                description="建立和维护信息安全策略",
                control_id="A.5.1.1",
                severity=ComplianceSeverity.HIGH,
                mandatory=True,
                automated=False,
                remediation_steps=[
                    "制定信息安全策略文档",
                    "获得管理层批准",
                    "定期审查和更新策略"
                ]
            ),
            # SOC 2合规要求
            ComplianceRequirement(
                id="soc2-001",
                framework=ComplianceFramework.SOC2,
                title="安全监控",
                description="实施持续的安全监控机制",
                control_id="CC6.1",
                severity=ComplianceSeverity.HIGH,
                mandatory=True,
                automated=True,
                check_function="check_security_monitoring",
                remediation_steps=[
                    "部署安全监控工具",
                    "配置实时告警",
                    "建立事件响应流程"
                ]
            ),
            # NIST合规要求
            ComplianceRequirement(
                id="nist-001",
                framework=ComplianceFramework.NIST,
                title="身份验证",
                description="实施强身份验证机制",
                control_id="PR.AC-1",
                severity=ComplianceSeverity.HIGH,
                mandatory=True,
                automated=True,
                check_function="check_authentication_controls",
                remediation_steps=[
                    "启用多因素身份验证",
                    "配置密码策略",
                    "实施会话管理"
                ]
            )
        ]
        
        for req in default_requirements:
            self.requirements[req.id] = req
        
        logger.info(f"加载了 {len(default_requirements)} 个默认合规要求")
    
    def add_requirement(self, requirement: ComplianceRequirement) -> bool:
        """添加合规要求"""
        try:
            with self._lock:
                self.requirements[requirement.id] = requirement
            
            logger.info(f"添加合规要求: {requirement.id} - {requirement.title}")
            return True
        except Exception as e:
            logger.error(f"添加合规要求失败: {e}")
            return False
    
    def remove_requirement(self, requirement_id: str) -> bool:
        """删除合规要求"""
        try:
            with self._lock:
                if requirement_id in self.requirements:
                    del self.requirements[requirement_id]
                    # 同时删除相关结果
                    if requirement_id in self.results:
                        del self.results[requirement_id]
                    
                    logger.info(f"删除合规要求: {requirement_id}")
                    return True
                else:
                    logger.warning(f"合规要求不存在: {requirement_id}")
                    return False
        except Exception as e:
            logger.error(f"删除合规要求失败: {e}")
            return False
    
    def run_compliance_check(self, requirement_id: Optional[str] = None, 
                           framework: Optional[ComplianceFramework] = None) -> Dict[str, ComplianceResult]:
        """运行合规检查"""
        try:
            # 确定要检查的要求
            if requirement_id:
                if requirement_id not in self.requirements:
                    logger.error(f"合规要求不存在: {requirement_id}")
                    return {}
                requirements_to_check = [self.requirements[requirement_id]]
            elif framework:
                requirements_to_check = [req for req in self.requirements.values() 
                                       if req.framework == framework]
            else:
                requirements_to_check = list(self.requirements.values())
            
            results = {}
            for req in requirements_to_check:
                result = self._check_single_requirement(req)
                results[req.id] = result
                
                with self._lock:
                    self.results[req.id] = result
            
            # 记录检查历史
            self._record_check_history(results)
            
            logger.info(f"完成合规检查，检查了 {len(results)} 个要求")
            return results
            
        except Exception as e:
            logger.error(f"合规检查失败: {e}")
            return {}
    
    def _check_single_requirement(self, requirement: ComplianceRequirement) -> ComplianceResult:
        """检查单个合规要求"""
        try:
            check_time = datetime.now()
            
            # 如果有自动检查函数，运行它
            if requirement.automated and requirement.check_function:
                status, score, details, evidence = self._run_automated_check(requirement)
            else:
                # 手动检查（返回待检查状态）
                status = ComplianceStatus.PENDING
                score = 0.0
                details = "需要手动检查"
                evidence = []
            
            # 生成建议
            recommendations = self._generate_recommendations(requirement, status, score)
            
            # 计算下次检查时间
            next_check_time = self._calculate_next_check_time(requirement, status)
            
            result = ComplianceResult(
                requirement_id=requirement.id,
                status=status,
                score=score,
                details=details,
                evidence=evidence,
                recommendations=recommendations,
                check_time=check_time,
                next_check_time=next_check_time
            )
            
            return result
            
        except Exception as e:
            logger.error(f"检查合规要求 {requirement.id} 失败: {e}")
            return ComplianceResult(
                requirement_id=requirement.id,
                status=ComplianceStatus.UNKNOWN,
                score=0.0,
                details=f"检查失败: {str(e)}",
                evidence=[],
                recommendations=["联系系统管理员"],
                check_time=datetime.now(),
                next_check_time=datetime.now() + timedelta(hours=1)
            )
    
    def _run_automated_check(self, requirement: ComplianceRequirement) -> Tuple[ComplianceStatus, float, str, List[str]]:
        """运行自动化检查"""
        try:
            # 模拟自动化检查逻辑
            # 在实际实现中，这里会调用具体的检查函数
            
            check_functions = {
                "check_financial_data_access": self._check_financial_data_access,
                "check_personal_data_encryption": self._check_personal_data_encryption,
                "check_payment_data_protection": self._check_payment_data_protection,
                "check_security_monitoring": self._check_security_monitoring,
                "check_authentication_controls": self._check_authentication_controls
            }
            
            if requirement.check_function in check_functions:
                return check_functions[requirement.check_function]()
            else:
                # 默认检查逻辑
                import random
                score = random.uniform(0.6, 1.0)
                if score >= 0.9:
                    status = ComplianceStatus.COMPLIANT
                    details = "自动检查通过"
                elif score >= 0.7:
                    status = ComplianceStatus.PARTIAL
                    details = "部分合规，需要改进"
                else:
                    status = ComplianceStatus.NON_COMPLIANT
                    details = "不合规，需要立即处理"
                
                evidence = [f"自动检查得分: {score:.2f}"]
                return status, score, details, evidence
                
        except Exception as e:
            logger.error(f"自动检查失败: {e}")
            return ComplianceStatus.UNKNOWN, 0.0, f"检查失败: {str(e)}", []
    
    def _check_financial_data_access(self) -> Tuple[ComplianceStatus, float, str, List[str]]:
        """检查财务数据访问控制"""
        # 模拟检查逻辑
        score = 0.85
        status = ComplianceStatus.COMPLIANT
        details = "财务数据访问控制配置正确"
        evidence = [
            "启用了基于角色的访问控制",
            "财务数据访问日志完整",
            "定期访问权限审查"
        ]
        return status, score, details, evidence
    
    def _check_personal_data_encryption(self) -> Tuple[ComplianceStatus, float, str, List[str]]:
        """检查个人数据加密"""
        score = 0.92
        status = ComplianceStatus.COMPLIANT
        details = "个人数据加密配置符合GDPR要求"
        evidence = [
            "传输数据使用TLS 1.3加密",
            "存储数据使用AES-256加密",
            "密钥管理符合最佳实践"
        ]
        return status, score, details, evidence
    
    def _check_payment_data_protection(self) -> Tuple[ComplianceStatus, float, str, List[str]]:
        """检查支付数据保护"""
        score = 0.78
        status = ComplianceStatus.PARTIAL
        details = "支付数据保护部分合规，需要改进"
        evidence = [
            "支付数据已加密存储",
            "部分传输链路需要加强",
            "密钥轮换策略需要优化"
        ]
        return status, score, details, evidence
    
    def _check_security_monitoring(self) -> Tuple[ComplianceStatus, float, str, List[str]]:
        """检查安全监控"""
        score = 0.88
        status = ComplianceStatus.COMPLIANT
        details = "安全监控机制运行正常"
        evidence = [
            "24/7安全监控运行",
            "实时告警系统正常",
            "事件响应流程完善"
        ]
        return status, score, details, evidence
    
    def _check_authentication_controls(self) -> Tuple[ComplianceStatus, float, str, List[str]]:
        """检查身份验证控制"""
        score = 0.95
        status = ComplianceStatus.COMPLIANT
        details = "身份验证控制符合NIST标准"
        evidence = [
            "多因素身份验证已启用",
            "密码策略符合要求",
            "会话管理安全"
        ]
        return status, score, details, evidence
    
    def _generate_recommendations(self, requirement: ComplianceRequirement, 
                                status: ComplianceStatus, score: float) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if status == ComplianceStatus.NON_COMPLIANT:
            recommendations.extend(requirement.remediation_steps)
            recommendations.append("立即制定修复计划")
            recommendations.append("设置修复截止日期")
        elif status == ComplianceStatus.PARTIAL:
            recommendations.append("分析部分合规的原因")
            recommendations.append("制定改进计划")
            recommendations.extend(requirement.remediation_steps[:2])  # 前两个修复步骤
        elif status == ComplianceStatus.COMPLIANT and score < 0.9:
            recommendations.append("继续监控合规状态")
            recommendations.append("考虑进一步优化")
        
        return recommendations
    
    def _calculate_next_check_time(self, requirement: ComplianceRequirement, 
                                 status: ComplianceStatus) -> datetime:
        """计算下次检查时间"""
        base_time = datetime.now()
        
        # 根据合规状态和严重程度确定检查间隔
        if status == ComplianceStatus.NON_COMPLIANT:
            if requirement.severity == ComplianceSeverity.CRITICAL:
                interval = timedelta(hours=6)  # 6小时后重新检查
            else:
                interval = timedelta(hours=24)  # 1天后重新检查
        elif status == ComplianceStatus.PARTIAL:
            interval = timedelta(days=3)  # 3天后重新检查
        else:
            # 合规状态，根据框架确定定期检查间隔
            if requirement.framework in [ComplianceFramework.SOX, ComplianceFramework.PCI_DSS]:
                interval = timedelta(days=30)  # 月度检查
            else:
                interval = timedelta(days=90)  # 季度检查
        
        return base_time + interval
    
    def _record_check_history(self, results: Dict[str, ComplianceResult]):
        """记录检查历史"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "check_id": str(uuid.uuid4()),
                "results_count": len(results),
                "summary": self._generate_check_summary(results)
            }
            
            with self._lock:
                self.compliance_history.append(history_entry)
                # 保持历史记录在合理范围内
                if len(self.compliance_history) > 1000:
                    self.compliance_history = self.compliance_history[-500:]
            
        except Exception as e:
            logger.error(f"记录检查历史失败: {e}")
    
    def _generate_check_summary(self, results: Dict[str, ComplianceResult]) -> Dict[str, Any]:
        """生成检查摘要"""
        if not results:
            return {}
        
        status_counts = {}
        total_score = 0
        severity_issues = {severity: 0 for severity in ComplianceSeverity}
        
        for result in results.values():
            # 统计状态
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            total_score += result.score
            
            # 统计严重程度
            if result.requirement_id in self.requirements:
                req = self.requirements[result.requirement_id]
                if result.status in [ComplianceStatus.NON_COMPLIANT, ComplianceStatus.PARTIAL]:
                    severity_issues[req.severity] += 1
        
        return {
            "total_checks": len(results),
            "average_score": total_score / len(results) if results else 0,
            "status_distribution": status_counts,
            "severity_issues": {k.value: v for k, v in severity_issues.items() if v > 0}
        }
    
    def create_compliance_plan(self, name: str, framework: ComplianceFramework,
                             requirement_ids: List[str], responsible_team: str,
                             duration_days: int = 90) -> str:
        """创建合规计划"""
        try:
            plan_id = str(uuid.uuid4())
            start_date = datetime.now()
            end_date = start_date + timedelta(days=duration_days)
            
            plan = CompliancePlan(
                id=plan_id,
                name=name,
                framework=framework,
                requirements=requirement_ids,
                start_date=start_date,
                end_date=end_date,
                responsible_team=responsible_team,
                status="active",
                progress=0.0,
                created_at=start_date,
                updated_at=start_date
            )
            
            with self._lock:
                self.plans[plan_id] = plan
            
            logger.info(f"创建合规计划: {name} ({plan_id})")
            return plan_id
            
        except Exception as e:
            logger.error(f"创建合规计划失败: {e}")
            return ""
    
    def update_plan_progress(self, plan_id: str) -> bool:
        """更新合规计划进度"""
        try:
            if plan_id not in self.plans:
                logger.error(f"合规计划不存在: {plan_id}")
                return False
            
            plan = self.plans[plan_id]
            
            # 计算进度
            total_requirements = len(plan.requirements)
            if total_requirements == 0:
                progress = 1.0
            else:
                compliant_count = 0
                for req_id in plan.requirements:
                    if req_id in self.results:
                        result = self.results[req_id]
                        if result.status == ComplianceStatus.COMPLIANT:
                            compliant_count += 1
                        elif result.status == ComplianceStatus.PARTIAL:
                            compliant_count += 0.5
                
                progress = compliant_count / total_requirements
            
            # 更新计划
            with self._lock:
                plan.progress = progress
                plan.updated_at = datetime.now()
                
                # 如果进度达到100%，标记为完成
                if progress >= 1.0:
                    plan.status = "completed"
                elif progress > 0:
                    plan.status = "in_progress"
            
            logger.info(f"更新合规计划进度: {plan_id} -> {progress:.1%}")
            return True
            
        except Exception as e:
            logger.error(f"更新合规计划进度失败: {e}")
            return False
    
    def get_compliance_report(self, framework: Optional[ComplianceFramework] = None,
                            include_details: bool = True) -> Dict[str, Any]:
        """生成合规报告"""
        try:
            # 过滤结果
            if framework:
                filtered_results = {
                    req_id: result for req_id, result in self.results.items()
                    if req_id in self.requirements and self.requirements[req_id].framework == framework
                }
                filtered_requirements = {
                    req_id: req for req_id, req in self.requirements.items()
                    if req.framework == framework
                }
            else:
                filtered_results = self.results.copy()
                filtered_requirements = self.requirements.copy()
            
            # 生成报告
            report = {
                "report_id": str(uuid.uuid4()),
                "generated_at": datetime.now().isoformat(),
                "framework": framework.value if framework else "all",
                "summary": self._generate_compliance_summary(filtered_results, filtered_requirements),
                "statistics": self._generate_compliance_statistics(filtered_results),
                "risk_analysis": self._generate_risk_analysis(filtered_results, filtered_requirements),
                "recommendations": self._generate_overall_recommendations(filtered_results, filtered_requirements)
            }
            
            if include_details:
                report["detailed_results"] = {
                    req_id: asdict(result) for req_id, result in filtered_results.items()
                }
                report["requirements"] = {
                    req_id: asdict(req) for req_id, req in filtered_requirements.items()
                }
            
            logger.info(f"生成合规报告: {report['report_id']}")
            return report
            
        except Exception as e:
            logger.error(f"生成合规报告失败: {e}")
            return {}
    
    def _generate_compliance_summary(self, results: Dict[str, ComplianceResult],
                                   requirements: Dict[str, ComplianceRequirement]) -> Dict[str, Any]:
        """生成合规摘要"""
        if not results:
            return {"message": "无合规检查结果"}
        
        # 统计状态
        status_counts = {}
        for result in results.values():
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # 计算合规率
        total = len(results)
        compliant = status_counts.get(ComplianceStatus.COMPLIANT.value, 0)
        partial = status_counts.get(ComplianceStatus.PARTIAL.value, 0)
        compliance_rate = (compliant + partial * 0.5) / total if total > 0 else 0
        
        # 统计框架分布
        framework_counts = {}
        for req in requirements.values():
            framework = req.framework.value
            framework_counts[framework] = framework_counts.get(framework, 0) + 1
        
        return {
            "total_requirements": total,
            "compliance_rate": round(compliance_rate * 100, 1),
            "status_distribution": status_counts,
            "framework_distribution": framework_counts,
            "last_check": max(result.check_time for result in results.values()).isoformat() if results else None
        }
    
    def _generate_compliance_statistics(self, results: Dict[str, ComplianceResult]) -> Dict[str, Any]:
        """生成合规统计信息"""
        if not results:
            return {}
        
        scores = [result.score for result in results.values()]
        
        return {
            "average_score": round(sum(scores) / len(scores), 3),
            "min_score": round(min(scores), 3),
            "max_score": round(max(scores), 3),
            "score_distribution": {
                "excellent": len([s for s in scores if s >= 0.9]),
                "good": len([s for s in scores if 0.7 <= s < 0.9]),
                "fair": len([s for s in scores if 0.5 <= s < 0.7]),
                "poor": len([s for s in scores if s < 0.5])
            }
        }
    
    def _generate_risk_analysis(self, results: Dict[str, ComplianceResult],
                              requirements: Dict[str, ComplianceRequirement]) -> Dict[str, Any]:
        """生成风险分析"""
        risk_analysis = {
            "critical_issues": [],
            "high_risk_areas": [],
            "improvement_opportunities": []
        }
        
        for req_id, result in results.items():
            if req_id not in requirements:
                continue
                
            req = requirements[req_id]
            
            # 严重问题
            if (result.status == ComplianceStatus.NON_COMPLIANT and 
                req.severity in [ComplianceSeverity.CRITICAL, ComplianceSeverity.HIGH]):
                risk_analysis["critical_issues"].append({
                    "requirement_id": req_id,
                    "title": req.title,
                    "framework": req.framework.value,
                    "severity": req.severity.value,
                    "score": result.score
                })
            
            # 高风险区域
            elif result.status == ComplianceStatus.PARTIAL and req.severity == ComplianceSeverity.HIGH:
                risk_analysis["high_risk_areas"].append({
                    "requirement_id": req_id,
                    "title": req.title,
                    "framework": req.framework.value,
                    "score": result.score
                })
            
            # 改进机会
            elif result.status == ComplianceStatus.COMPLIANT and result.score < 0.8:
                risk_analysis["improvement_opportunities"].append({
                    "requirement_id": req_id,
                    "title": req.title,
                    "score": result.score,
                    "potential_improvement": round((0.9 - result.score) * 100, 1)
                })
        
        return risk_analysis
    
    def _generate_overall_recommendations(self, results: Dict[str, ComplianceResult],
                                        requirements: Dict[str, ComplianceRequirement]) -> List[str]:
        """生成整体建议"""
        recommendations = []
        
        if not results:
            return ["执行首次合规检查"]
        
        # 分析合规状态
        non_compliant = sum(1 for r in results.values() if r.status == ComplianceStatus.NON_COMPLIANT)
        partial = sum(1 for r in results.values() if r.status == ComplianceStatus.PARTIAL)
        total = len(results)
        
        if non_compliant > total * 0.2:
            recommendations.append("优先处理不合规项目，建议成立专项工作组")
        
        if partial > total * 0.3:
            recommendations.append("制定部分合规项目的改进计划")
        
        # 分析严重程度
        critical_issues = sum(1 for req_id, result in results.items()
                            if (req_id in requirements and 
                                requirements[req_id].severity == ComplianceSeverity.CRITICAL and
                                result.status != ComplianceStatus.COMPLIANT))
        
        if critical_issues > 0:
            recommendations.append(f"立即处理 {critical_issues} 个严重合规问题")
        
        # 自动化建议
        manual_checks = sum(1 for req_id in results.keys()
                          if req_id in requirements and not requirements[req_id].automated)
        
        if manual_checks > 0:
            recommendations.append(f"考虑自动化 {manual_checks} 个手动检查项目")
        
        # 框架特定建议
        framework_issues = {}
        for req_id, result in results.items():
            if req_id in requirements and result.status != ComplianceStatus.COMPLIANT:
                framework = requirements[req_id].framework
                framework_issues[framework] = framework_issues.get(framework, 0) + 1
        
        for framework, count in framework_issues.items():
            if count > 1:
                recommendations.append(f"关注 {framework.value.upper()} 框架合规性，有 {count} 个待处理项目")
        
        return recommendations[:10]  # 限制建议数量
    
    def start_monitoring(self, check_interval_hours: int = 24):
        """启动合规监控"""
        if self.monitoring_enabled:
            logger.warning("合规监控已在运行")
            return
        
        self.monitoring_enabled = True
        
        def monitor_loop():
            while self.monitoring_enabled:
                try:
                    # 查找需要检查的要求
                    current_time = datetime.now()
                    requirements_to_check = []
                    
                    for req_id, req in self.requirements.items():
                        if req_id in self.results:
                            result = self.results[req_id]
                            if current_time >= result.next_check_time:
                                requirements_to_check.append(req_id)
                        else:
                            # 从未检查过的要求
                            requirements_to_check.append(req_id)
                    
                    if requirements_to_check:
                        logger.info(f"定期合规检查: {len(requirements_to_check)} 个要求")
                        for req_id in requirements_to_check:
                            self.run_compliance_check(req_id)
                            # 更新相关计划进度
                            for plan in self.plans.values():
                                if req_id in plan.requirements:
                                    self.update_plan_progress(plan.id)
                    
                    # 等待下次检查
                    time.sleep(check_interval_hours * 3600)
                    
                except Exception as e:
                    logger.error(f"合规监控错误: {e}")
                    time.sleep(300)  # 错误时等待5分钟
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info(f"启动合规监控，检查间隔: {check_interval_hours} 小时")
    
    def stop_monitoring(self):
        """停止合规监控"""
        self.monitoring_enabled = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        logger.info("停止合规监控")
    
    def get_status(self) -> Dict[str, Any]:
        """获取合规管理器状态"""
        try:
            # 统计基本信息
            total_requirements = len(self.requirements)
            total_results = len(self.results)
            total_plans = len(self.plans)
            
            # 统计合规状态
            if self.results:
                status_counts = {}
                for result in self.results.values():
                    status = result.status.value
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                compliance_rate = status_counts.get(ComplianceStatus.COMPLIANT.value, 0) / total_results
            else:
                status_counts = {}
                compliance_rate = 0.0
            
            # 统计计划状态
            active_plans = sum(1 for plan in self.plans.values() if plan.status == "active")
            
            return {
                "requirements": {
                    "total": total_requirements,
                    "by_framework": {
                        framework.value: sum(1 for req in self.requirements.values() 
                                           if req.framework == framework)
                        for framework in ComplianceFramework
                    }
                },
                "results": {
                    "total": total_results,
                    "status_distribution": status_counts,
                    "compliance_rate": round(compliance_rate * 100, 1)
                },
                "plans": {
                    "total": total_plans,
                    "active": active_plans
                },
                "monitoring": {
                    "enabled": self.monitoring_enabled,
                    "history_count": len(self.compliance_history)
                },
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """清理资源"""
        try:
            self.stop_monitoring()
            self.executor.shutdown(wait=True)
            logger.info("ComplianceManager 清理完成")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

if __name__ == "__main__":
    # 演示用法
    manager = ComplianceManager()
    
    try:
        # 运行合规检查
        print("运行合规检查...")
        results = manager.run_compliance_check()
        print(f"检查了 {len(results)} 个合规要求")
        
        # 创建合规计划
        print("\n创建合规计划...")
        plan_id = manager.create_compliance_plan(
            name="GDPR合规计划",
            framework=ComplianceFramework.GDPR,
            requirement_ids=["gdpr-001"],
            responsible_team="安全团队"
        )
        print(f"创建合规计划: {plan_id}")
        
        # 生成合规报告
        print("\n生成合规报告...")
        report = manager.get_compliance_report(include_details=False)
        print(f"合规率: {report['summary']['compliance_rate']}%")
        
        # 获取状态
        print("\n系统状态:")
        status = manager.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
        
    finally:
        manager.cleanup()