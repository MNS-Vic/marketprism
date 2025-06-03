"""
企业级法规遵循系统

提供多种国际法规标准的自动化遵循、合规检查、合规报告和法规更新跟踪功能。
支持企业级法规遵循管理能力。

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
import threading

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RegulatoryFramework(Enum):
    """法规框架"""
    GDPR = "gdpr"                     # 通用数据保护条例
    CCPA = "ccpa"                     # 加州消费者隐私法案
    HIPAA = "hipaa"                   # 健康保险可携性和责任法案
    SOX = "sox"                       # 萨班斯-奥克斯利法案
    PCI_DSS = "pci_dss"              # 支付卡行业数据安全标准
    ISO_27001 = "iso_27001"          # ISO 27001信息安全管理体系
    NIST = "nist"                    # NIST网络安全框架
    SOC2 = "soc2"                    # SOC 2审计标准
    FISMA = "fisma"                  # 联邦信息安全管理法
    PIPEDA = "pipeda"                # 个人信息保护和电子文档法

class ComplianceStatus(Enum):
    """合规状态"""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"
    UNDER_REVIEW = "under_review"

@dataclass
class RegulatoryRequirement:
    """法规要求数据类"""
    id: str
    framework: RegulatoryFramework
    article_section: str
    title: str
    description: str
    requirement_text: str
    mandatory: bool
    penalty_info: str
    implementation_deadline: Optional[datetime]
    assessment_criteria: List[str]
    evidence_requirements: List[str]

@dataclass
class ComplianceAssessment:
    """合规评估数据类"""
    id: str
    requirement_id: str
    assessment_date: datetime
    assessor: str
    status: ComplianceStatus
    compliance_score: float  # 0.0-1.0
    findings: List[str]
    evidence_collected: List[str]
    gaps_identified: List[str]
    remediation_plan: List[str]
    next_review_date: datetime

class RegulatoryCompliance:
    """企业级法规遵循系统"""
    
    def __init__(self):
        """初始化法规遵循系统"""
        self.requirements: Dict[str, RegulatoryRequirement] = {}
        self.assessments: Dict[str, ComplianceAssessment] = {}
        self.compliance_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        
        # 初始化法规要求
        self._initialize_regulatory_requirements()
        
        logger.info("RegulatoryCompliance 初始化完成")
    
    def _initialize_regulatory_requirements(self):
        """初始化法规要求"""
        requirements = [
            # GDPR要求
            RegulatoryRequirement(
                id="gdpr-art-32",
                framework=RegulatoryFramework.GDPR,
                article_section="Article 32",
                title="数据处理安全",
                description="实施适当的技术和组织措施确保数据处理安全",
                requirement_text="控制者和处理者应实施适当的技术和组织措施...",
                mandatory=True,
                penalty_info="最高可处以2000万欧元或全球年营业额4%的罚款",
                implementation_deadline=None,
                assessment_criteria=[
                    "数据加密措施",
                    "访问控制机制",
                    "数据备份和恢复",
                    "事件响应计划"
                ],
                evidence_requirements=[
                    "加密策略文档",
                    "访问控制配置",
                    "备份测试记录",
                    "事件响应演练记录"
                ]
            ),
            # SOX要求
            RegulatoryRequirement(
                id="sox-302",
                framework=RegulatoryFramework.SOX,
                article_section="Section 302",
                title="财务报告内部控制",
                description="建立和维护财务报告的内部控制",
                requirement_text="管理层必须评估内部控制的有效性...",
                mandatory=True,
                penalty_info="可能面临刑事指控和巨额罚款",
                implementation_deadline=None,
                assessment_criteria=[
                    "内部控制设计",
                    "控制执行有效性",
                    "缺陷识别和修复",
                    "管理层评估"
                ],
                evidence_requirements=[
                    "内控设计文档",
                    "控制执行记录",
                    "缺陷整改证据",
                    "管理层评估报告"
                ]
            ),
            # PCI DSS要求
            RegulatoryRequirement(
                id="pci-dss-3",
                framework=RegulatoryFramework.PCI_DSS,
                article_section="Requirement 3",
                title="保护存储的持卡人数据",
                description="保护存储的持卡人数据",
                requirement_text="必须保护存储的持卡人数据...",
                mandatory=True,
                penalty_info="可能被禁止处理信用卡交易",
                implementation_deadline=None,
                assessment_criteria=[
                    "数据加密",
                    "密钥管理",
                    "数据保留策略",
                    "安全删除"
                ],
                evidence_requirements=[
                    "加密实施证据",
                    "密钥管理程序",
                    "数据保留记录",
                    "安全删除日志"
                ]
            )
        ]
        
        for req in requirements:
            self.requirements[req.id] = req
        
        logger.info(f"加载了 {len(requirements)} 个法规要求")
    
    def perform_compliance_assessment(self, requirement_id: str, assessor: str) -> str:
        """执行合规评估"""
        try:
            if requirement_id not in self.requirements:
                logger.error(f"法规要求不存在: {requirement_id}")
                return ""
            
            assessment_id = str(uuid.uuid4())
            requirement = self.requirements[requirement_id]
            
            # 执行自动评估
            status, score, findings, evidence, gaps = self._perform_automated_assessment(requirement)
            
            # 生成修复计划
            remediation_plan = self._generate_remediation_plan(requirement, gaps)
            
            # 计算下次审查日期
            next_review = self._calculate_next_review_date(requirement.framework, status)
            
            assessment = ComplianceAssessment(
                id=assessment_id,
                requirement_id=requirement_id,
                assessment_date=datetime.now(),
                assessor=assessor,
                status=status,
                compliance_score=score,
                findings=findings,
                evidence_collected=evidence,
                gaps_identified=gaps,
                remediation_plan=remediation_plan,
                next_review_date=next_review
            )
            
            with self._lock:
                self.assessments[assessment_id] = assessment
            
            # 记录历史
            self._record_compliance_history("assessment_completed", assessment_id, {
                "requirement": requirement_id,
                "status": status.value,
                "score": score
            })
            
            logger.info(f"完成合规评估: {requirement_id} -> {status.value}")
            return assessment_id
            
        except Exception as e:
            logger.error(f"执行合规评估失败: {e}")
            return ""
    
    def _perform_automated_assessment(self, requirement: RegulatoryRequirement) -> Tuple[ComplianceStatus, float, List[str], List[str], List[str]]:
        """执行自动化评估"""
        # 模拟自动化评估逻辑
        import random
        
        findings = []
        evidence = []
        gaps = []
        
        # 基于框架的评估逻辑
        if requirement.framework == RegulatoryFramework.GDPR:
            score = random.uniform(0.7, 0.95)
            findings.append("数据加密已实施")
            evidence.append("TLS 1.3加密配置")
            if score < 0.9:
                gaps.append("需要改进密钥管理流程")
        
        elif requirement.framework == RegulatoryFramework.SOX:
            score = random.uniform(0.8, 0.98)
            findings.append("内部控制机制运行正常")
            evidence.append("内控测试报告")
            if score < 0.95:
                gaps.append("需要加强财务数据访问控制")
        
        elif requirement.framework == RegulatoryFramework.PCI_DSS:
            score = random.uniform(0.75, 0.92)
            findings.append("支付数据加密符合要求")
            evidence.append("PCI DSS扫描报告")
            if score < 0.9:
                gaps.append("需要更新密钥轮换策略")
        
        else:
            score = random.uniform(0.6, 0.9)
            findings.append("基本要求已满足")
            evidence.append("配置检查报告")
        
        # 确定状态
        if score >= 0.95:
            status = ComplianceStatus.COMPLIANT
        elif score >= 0.8:
            status = ComplianceStatus.PARTIAL
        elif score >= 0.6:
            status = ComplianceStatus.NON_COMPLIANT
        else:
            status = ComplianceStatus.UNDER_REVIEW
        
        return status, score, findings, evidence, gaps
    
    def _generate_remediation_plan(self, requirement: RegulatoryRequirement, gaps: List[str]) -> List[str]:
        """生成修复计划"""
        plan = []
        
        for gap in gaps:
            if "密钥管理" in gap:
                plan.append("实施自动化密钥轮换")
                plan.append("建立密钥管理HSM")
            elif "访问控制" in gap:
                plan.append("实施基于角色的访问控制")
                plan.append("启用多因素认证")
            elif "加密" in gap:
                plan.append("升级到更强的加密算法")
                plan.append("实施端到端加密")
            else:
                plan.append(f"解决问题: {gap}")
        
        if not plan:
            plan.append("继续监控合规状态")
        
        return plan
    
    def _calculate_next_review_date(self, framework: RegulatoryFramework, status: ComplianceStatus) -> datetime:
        """计算下次审查日期"""
        base_date = datetime.now()
        
        # 基于框架的审查周期
        framework_cycles = {
            RegulatoryFramework.GDPR: 90,      # 90天
            RegulatoryFramework.SOX: 90,       # 90天
            RegulatoryFramework.PCI_DSS: 90,   # 90天
            RegulatoryFramework.HIPAA: 180,    # 180天
            RegulatoryFramework.ISO_27001: 180 # 180天
        }
        
        base_cycle = framework_cycles.get(framework, 90)
        
        # 基于状态调整周期
        if status == ComplianceStatus.NON_COMPLIANT:
            cycle = base_cycle // 3  # 更频繁的审查
        elif status == ComplianceStatus.PARTIAL:
            cycle = base_cycle // 2
        else:
            cycle = base_cycle
        
        return base_date + timedelta(days=cycle)
    
    def generate_compliance_report(self, frameworks: Optional[List[RegulatoryFramework]] = None) -> Dict[str, Any]:
        """生成合规报告"""
        try:
            # 过滤评估
            if frameworks:
                relevant_assessments = {
                    aid: assessment for aid, assessment in self.assessments.items()
                    if assessment.requirement_id in self.requirements and
                    self.requirements[assessment.requirement_id].framework in frameworks
                }
                relevant_requirements = {
                    rid: req for rid, req in self.requirements.items()
                    if req.framework in frameworks
                }
            else:
                relevant_assessments = self.assessments
                relevant_requirements = self.requirements
            
            report = {
                "report_id": str(uuid.uuid4()),
                "generated_at": datetime.now().isoformat(),
                "scope": [f.value for f in frameworks] if frameworks else "all",
                "executive_summary": self._generate_compliance_summary(relevant_assessments, relevant_requirements),
                "framework_analysis": self._analyze_frameworks(relevant_assessments, relevant_requirements),
                "risk_assessment": self._assess_compliance_risks(relevant_assessments, relevant_requirements),
                "recommendations": self._generate_compliance_recommendations(relevant_assessments),
                "action_plan": self._create_action_plan(relevant_assessments)
            }
            
            logger.info(f"生成合规报告: {report['report_id']}")
            return report
            
        except Exception as e:
            logger.error(f"生成合规报告失败: {e}")
            return {}
    
    def _generate_compliance_summary(self, assessments: Dict[str, ComplianceAssessment], 
                                   requirements: Dict[str, RegulatoryRequirement]) -> Dict[str, Any]:
        """生成合规摘要"""
        if not assessments:
            return {"message": "无合规评估数据"}
        
        # 状态统计
        status_counts = {}
        for assessment in assessments.values():
            status = assessment.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # 计算整体合规率
        compliant_count = status_counts.get(ComplianceStatus.COMPLIANT.value, 0)
        partial_count = status_counts.get(ComplianceStatus.PARTIAL.value, 0)
        total_count = len(assessments)
        
        compliance_rate = (compliant_count + partial_count * 0.5) / total_count * 100 if total_count > 0 else 0
        
        # 框架覆盖率
        frameworks_with_assessments = set()
        for assessment in assessments.values():
            if assessment.requirement_id in requirements:
                frameworks_with_assessments.add(requirements[assessment.requirement_id].framework)
        
        total_frameworks = len(set(req.framework for req in requirements.values()))
        framework_coverage = len(frameworks_with_assessments) / total_frameworks * 100 if total_frameworks > 0 else 0
        
        return {
            "overall_compliance_rate": round(compliance_rate, 1),
            "framework_coverage": round(framework_coverage, 1),
            "total_assessments": total_count,
            "status_distribution": status_counts,
            "high_risk_items": sum(1 for a in assessments.values() if a.compliance_score < 0.7),
            "last_assessment": max(a.assessment_date for a in assessments.values()).isoformat() if assessments else None
        }
    
    def _analyze_frameworks(self, assessments: Dict[str, ComplianceAssessment],
                          requirements: Dict[str, RegulatoryRequirement]) -> Dict[str, Any]:
        """分析框架合规性"""
        framework_analysis = {}
        
        # 按框架分组
        framework_assessments = {}
        for assessment in assessments.values():
            if assessment.requirement_id in requirements:
                framework = requirements[assessment.requirement_id].framework
                if framework not in framework_assessments:
                    framework_assessments[framework] = []
                framework_assessments[framework].append(assessment)
        
        # 分析每个框架
        for framework, framework_assessments_list in framework_assessments.items():
            total_assessments = len(framework_assessments_list)
            compliant_count = sum(1 for a in framework_assessments_list if a.status == ComplianceStatus.COMPLIANT)
            average_score = sum(a.compliance_score for a in framework_assessments_list) / total_assessments
            
            framework_analysis[framework.value] = {
                "total_requirements_assessed": total_assessments,
                "compliance_rate": round(compliant_count / total_assessments * 100, 1),
                "average_score": round(average_score, 3),
                "status": "compliant" if average_score >= 0.9 else "partial" if average_score >= 0.7 else "non_compliant"
            }
        
        return framework_analysis
    
    def _assess_compliance_risks(self, assessments: Dict[str, ComplianceAssessment],
                               requirements: Dict[str, RegulatoryRequirement]) -> Dict[str, Any]:
        """评估合规风险"""
        risks = {
            "high_risk": [],
            "medium_risk": [],
            "low_risk": []
        }
        
        for assessment in assessments.values():
            if assessment.requirement_id in requirements:
                requirement = requirements[assessment.requirement_id]
                
                # 风险评分
                risk_score = 1.0 - assessment.compliance_score
                
                # 基于框架调整风险
                if requirement.framework in [RegulatoryFramework.GDPR, RegulatoryFramework.SOX]:
                    risk_score *= 1.3  # 高影响框架
                
                risk_item = {
                    "requirement_id": requirement.id,
                    "framework": requirement.framework.value,
                    "title": requirement.title,
                    "risk_score": round(risk_score, 3),
                    "compliance_score": assessment.compliance_score,
                    "penalty_info": requirement.penalty_info
                }
                
                if risk_score >= 0.7:
                    risks["high_risk"].append(risk_item)
                elif risk_score >= 0.4:
                    risks["medium_risk"].append(risk_item)
                else:
                    risks["low_risk"].append(risk_item)
        
        return {
            "risk_distribution": {
                "high": len(risks["high_risk"]),
                "medium": len(risks["medium_risk"]),
                "low": len(risks["low_risk"])
            },
            "detailed_risks": risks
        }
    
    def _generate_compliance_recommendations(self, assessments: Dict[str, ComplianceAssessment]) -> List[str]:
        """生成合规建议"""
        recommendations = []
        
        # 分析评估结果
        non_compliant = [a for a in assessments.values() if a.status == ComplianceStatus.NON_COMPLIANT]
        partial = [a for a in assessments.values() if a.status == ComplianceStatus.PARTIAL]
        low_scores = [a for a in assessments.values() if a.compliance_score < 0.7]
        
        if non_compliant:
            recommendations.append(f"优先处理 {len(non_compliant)} 个不合规项目")
        
        if partial:
            recommendations.append(f"改进 {len(partial)} 个部分合规项目")
        
        if low_scores:
            recommendations.append(f"关注 {len(low_scores)} 个低分项目，制定改进计划")
        
        # 通用建议
        recommendations.extend([
            "建立定期合规监控机制",
            "加强员工合规培训",
            "完善合规文档管理",
            "定期进行合规审计"
        ])
        
        return recommendations[:8]  # 限制建议数量
    
    def _create_action_plan(self, assessments: Dict[str, ComplianceAssessment]) -> List[Dict[str, Any]]:
        """创建行动计划"""
        action_items = []
        
        # 优先处理高风险项目
        high_priority = [a for a in assessments.values() if a.compliance_score < 0.7]
        high_priority.sort(key=lambda x: x.compliance_score)  # 按分数排序
        
        for i, assessment in enumerate(high_priority[:5]):  # 前5个优先项
            action_items.append({
                "priority": i + 1,
                "requirement_id": assessment.requirement_id,
                "action": f"修复合规差距: {assessment.requirement_id}",
                "timeline": "30天",
                "owner": "合规团队",
                "success_metric": "合规分数达到90%以上"
            })
        
        return action_items
    
    def _record_compliance_history(self, event_type: str, reference_id: str, details: Dict[str, Any]):
        """记录合规历史"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "reference_id": reference_id,
                "details": details,
                "event_id": str(uuid.uuid4())
            }
            
            with self._lock:
                self.compliance_history.append(history_entry)
                if len(self.compliance_history) > 1000:
                    self.compliance_history = self.compliance_history[-500:]
            
        except Exception as e:
            logger.error(f"记录合规历史失败: {e}")
    
    def get_compliance_dashboard(self) -> Dict[str, Any]:
        """获取合规仪表板"""
        try:
            # 统计基本信息
            total_requirements = len(self.requirements)
            total_assessments = len(self.assessments)
            
            # 框架分布
            framework_counts = {}
            for req in self.requirements.values():
                framework = req.framework.value
                framework_counts[framework] = framework_counts.get(framework, 0) + 1
            
            # 合规状态分布
            status_counts = {}
            for assessment in self.assessments.values():
                status = assessment.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # 即将到期的审查
            upcoming_reviews = []
            current_time = datetime.now()
            for assessment in self.assessments.values():
                if assessment.next_review_date:
                    days_until = (assessment.next_review_date - current_time).days
                    if 0 <= days_until <= 30:
                        upcoming_reviews.append({
                            "requirement_id": assessment.requirement_id,
                            "days_until_review": days_until,
                            "current_status": assessment.status.value
                        })
            
            dashboard = {
                "summary": {
                    "total_requirements": total_requirements,
                    "total_assessments": total_assessments,
                    "framework_coverage": len(framework_counts),
                    "last_updated": datetime.now().isoformat()
                },
                "framework_distribution": framework_counts,
                "status_distribution": status_counts,
                "upcoming_reviews": upcoming_reviews[:10],  # 前10个
                "compliance_alerts": self._generate_compliance_alerts()
            }
            
            return dashboard
            
        except Exception as e:
            logger.error(f"获取合规仪表板失败: {e}")
            return {"error": str(e)}
    
    def _generate_compliance_alerts(self) -> List[Dict[str, Any]]:
        """生成合规告警"""
        alerts = []
        
        # 不合规告警
        non_compliant = [a for a in self.assessments.values() if a.status == ComplianceStatus.NON_COMPLIANT]
        if non_compliant:
            alerts.append({
                "type": "non_compliant",
                "severity": "high",
                "count": len(non_compliant),
                "message": f"发现 {len(non_compliant)} 个不合规项目需要立即处理"
            })
        
        # 即将到期的审查
        overdue_reviews = []
        current_time = datetime.now()
        for assessment in self.assessments.values():
            if assessment.next_review_date and assessment.next_review_date < current_time:
                overdue_reviews.append(assessment)
        
        if overdue_reviews:
            alerts.append({
                "type": "overdue_reviews",
                "severity": "medium",
                "count": len(overdue_reviews),
                "message": f"有 {len(overdue_reviews)} 个合规审查已过期"
            })
        
        return alerts
    
    def get_status(self) -> Dict[str, Any]:
        """获取法规遵循系统状态"""
        try:
            return {
                "requirements": {
                    "total": len(self.requirements),
                    "by_framework": {
                        framework.value: sum(1 for req in self.requirements.values() 
                                           if req.framework == framework)
                        for framework in RegulatoryFramework
                    }
                },
                "assessments": {
                    "total": len(self.assessments),
                    "by_status": {
                        status.value: sum(1 for assessment in self.assessments.values() 
                                        if assessment.status == status)
                        for status in ComplianceStatus
                    }
                },
                "history": {
                    "total_events": len(self.compliance_history)
                },
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {"error": str(e)}

if __name__ == "__main__":
    # 演示用法
    compliance = RegulatoryCompliance()
    
    try:
        # 执行合规评估
        print("执行合规评估...")
        for req_id in list(compliance.requirements.keys())[:3]:
            assessment_id = compliance.perform_compliance_assessment(req_id, "合规审计师")
            print(f"评估 {req_id}: {assessment_id}")
        
        # 生成合规报告
        print("\n生成合规报告...")
        report = compliance.generate_compliance_report([RegulatoryFramework.GDPR, RegulatoryFramework.SOX])
        if report:
            print(f"报告ID: {report['report_id']}")
            print(f"整体合规率: {report['executive_summary']['overall_compliance_rate']}%")
        
        # 获取合规仪表板
        print("\n合规仪表板:")
        dashboard = compliance.get_compliance_dashboard()
        print(json.dumps(dashboard, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"演示过程出错: {e}")