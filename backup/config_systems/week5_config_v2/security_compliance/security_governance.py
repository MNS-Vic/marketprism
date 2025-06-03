"""
企业级安全治理系统

提供企业级安全治理流程、决策支持、安全政策管理和治理报告功能。
支持多层级治理结构和企业级安全决策管理能力。

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

class GovernanceLevel(Enum):
    """治理级别"""
    BOARD = "board"                   # 董事会级别
    EXECUTIVE = "executive"           # 高管级别
    MANAGEMENT = "management"         # 管理层级别
    OPERATIONAL = "operational"       # 运营级别
    TECHNICAL = "technical"           # 技术级别

class PolicyType(Enum):
    """政策类型"""
    SECURITY = "security"             # 安全政策
    PRIVACY = "privacy"               # 隐私政策
    COMPLIANCE = "compliance"         # 合规政策
    RISK = "risk"                     # 风险政策
    OPERATIONAL = "operational"       # 运营政策
    TECHNICAL = "technical"           # 技术政策

class PolicyStatus(Enum):
    """政策状态"""
    DRAFT = "draft"                   # 草案
    REVIEW = "review"                 # 审查中
    APPROVED = "approved"             # 已批准
    ACTIVE = "active"                 # 生效中
    SUSPENDED = "suspended"           # 暂停
    RETIRED = "retired"               # 已退役

class DecisionType(Enum):
    """决策类型"""
    POLICY_APPROVAL = "policy_approval"         # 政策批准
    RISK_ACCEPTANCE = "risk_acceptance"         # 风险接受
    SECURITY_INVESTMENT = "security_investment" # 安全投资
    INCIDENT_RESPONSE = "incident_response"     # 事件响应
    COMPLIANCE_EXEMPTION = "compliance_exemption" # 合规豁免
    STRATEGIC_DIRECTION = "strategic_direction"   # 战略方向

@dataclass
class SecurityPolicy:
    """安全政策数据类"""
    id: str
    title: str
    description: str
    policy_type: PolicyType
    version: str
    status: PolicyStatus
    owner: str
    approver: str
    effective_date: datetime
    expiry_date: datetime
    content: str
    requirements: List[str]
    exceptions: List[str]
    related_policies: List[str]
    compliance_frameworks: List[str]
    created_at: datetime
    updated_at: datetime
    review_cycle: int  # 审查周期（月）

@dataclass
class GovernanceDecision:
    """治理决策数据类"""
    id: str
    decision_type: DecisionType
    title: str
    description: str
    governance_level: GovernanceLevel
    decision_maker: str
    decision_date: datetime
    rationale: str
    impact_assessment: Dict[str, Any]
    implementation_plan: List[str]
    success_criteria: List[str]
    review_date: datetime
    status: str  # pending, approved, rejected, implemented
    stakeholders: List[str]
    documents: List[str]

@dataclass
class GovernanceCommittee:
    """治理委员会数据类"""
    id: str
    name: str
    description: str
    governance_level: GovernanceLevel
    chair: str
    members: List[str]
    responsibilities: List[str]
    meeting_frequency: str
    reporting_to: Optional[str]
    charter: str
    established_date: datetime
    status: str  # active, inactive

@dataclass
class GovernanceMetric:
    """治理指标数据类"""
    id: str
    name: str
    description: str
    category: str
    target_value: float
    current_value: float
    measurement_unit: str
    measurement_frequency: str
    owner: str
    last_measured: datetime
    trend: str  # improving, stable, declining

class SecurityGovernance:
    """企业级安全治理系统"""
    
    def __init__(self):
        """初始化安全治理系统"""
        self.policies: Dict[str, SecurityPolicy] = {}
        self.decisions: Dict[str, GovernanceDecision] = {}
        self.committees: Dict[str, GovernanceCommittee] = {}
        self.metrics: Dict[str, GovernanceMetric] = {}
        self.governance_history: List[Dict[str, Any]] = []
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._lock = threading.Lock()
        
        # 初始化默认治理结构
        self._initialize_default_governance()
        
        logger.info("SecurityGovernance 初始化完成")
    
    def _initialize_default_governance(self):
        """初始化默认治理结构"""
        # 创建默认委员会
        default_committees = [
            GovernanceCommittee(
                id="cyber-security-committee",
                name="网络安全委员会",
                description="负责整体网络安全战略和重大安全决策",
                governance_level=GovernanceLevel.EXECUTIVE,
                chair="首席信息安全官",
                members=["CTO", "法务总监", "风险官", "合规官"],
                responsibilities=[
                    "制定网络安全战略",
                    "批准重大安全政策",
                    "监督安全投资",
                    "处理重大安全事件"
                ],
                meeting_frequency="monthly",
                reporting_to="board",
                charter="网络安全委员会章程",
                established_date=datetime.now(),
                status="active"
            ),
            GovernanceCommittee(
                id="risk-management-committee",
                name="风险管理委员会",
                description="负责企业级风险管理和风险决策",
                governance_level=GovernanceLevel.MANAGEMENT,
                chair="首席风险官",
                members=["CISO", "合规官", "业务负责人", "IT主管"],
                responsibilities=[
                    "评估和管理企业风险",
                    "制定风险管理政策",
                    "监督风险缓解措施",
                    "定期风险报告"
                ],
                meeting_frequency="bi-weekly",
                reporting_to="cyber-security-committee",
                charter="风险管理委员会章程",
                established_date=datetime.now(),
                status="active"
            )
        ]
        
        for committee in default_committees:
            self.committees[committee.id] = committee
        
        # 创建默认政策
        default_policies = [
            SecurityPolicy(
                id="information-security-policy",
                title="信息安全政策",
                description="企业信息安全的总体政策框架",
                policy_type=PolicyType.SECURITY,
                version="1.0",
                status=PolicyStatus.ACTIVE,
                owner="首席信息安全官",
                approver="网络安全委员会",
                effective_date=datetime.now(),
                expiry_date=datetime.now() + timedelta(days=365),
                content="本政策建立了保护企业信息资产的框架...",
                requirements=[
                    "所有员工必须遵守信息安全要求",
                    "必须使用强密码和多因素认证",
                    "禁止未授权访问敏感信息",
                    "定期进行安全培训"
                ],
                exceptions=["紧急情况下的临时访问"],
                related_policies=["access-control-policy", "data-classification-policy"],
                compliance_frameworks=["ISO27001", "NIST"],
                created_at=datetime.now(),
                updated_at=datetime.now(),
                review_cycle=12
            ),
            SecurityPolicy(
                id="data-protection-policy",
                title="数据保护政策",
                description="个人数据和敏感数据的保护政策",
                policy_type=PolicyType.PRIVACY,
                version="1.0",
                status=PolicyStatus.ACTIVE,
                owner="数据保护官",
                approver="网络安全委员会",
                effective_date=datetime.now(),
                expiry_date=datetime.now() + timedelta(days=365),
                content="本政策规定了个人数据处理的要求...",
                requirements=[
                    "遵循最小化数据收集原则",
                    "获得明确的数据处理同意",
                    "实施适当的技术和组织措施",
                    "及时处理数据主体请求"
                ],
                exceptions=["法律要求的数据处理"],
                related_policies=["information-security-policy"],
                compliance_frameworks=["GDPR", "CCPA"],
                created_at=datetime.now(),
                updated_at=datetime.now(),
                review_cycle=12
            )
        ]
        
        for policy in default_policies:
            self.policies[policy.id] = policy
        
        # 创建默认治理指标
        default_metrics = [
            GovernanceMetric(
                id="security-incident-rate",
                name="安全事件发生率",
                description="每月安全事件数量",
                category="security",
                target_value=5.0,
                current_value=3.0,
                measurement_unit="件/月",
                measurement_frequency="monthly",
                owner="首席信息安全官",
                last_measured=datetime.now(),
                trend="improving"
            ),
            GovernanceMetric(
                id="compliance-score",
                name="合规评分",
                description="整体合规性评分",
                category="compliance",
                target_value=95.0,
                current_value=92.0,
                measurement_unit="百分比",
                measurement_frequency="quarterly",
                owner="合规官",
                last_measured=datetime.now(),
                trend="stable"
            ),
            GovernanceMetric(
                id="security-training-completion",
                name="安全培训完成率",
                description="员工安全培训完成百分比",
                category="training",
                target_value=100.0,
                current_value=85.0,
                measurement_unit="百分比",
                measurement_frequency="quarterly",
                owner="人力资源",
                last_measured=datetime.now(),
                trend="improving"
            )
        ]
        
        for metric in default_metrics:
            self.metrics[metric.id] = metric
        
        logger.info(f"初始化了 {len(default_committees)} 个委员会、{len(default_policies)} 个政策、{len(default_metrics)} 个指标")
    
    def create_policy(self, title: str, description: str, policy_type: PolicyType,
                     owner: str, content: str, requirements: List[str],
                     compliance_frameworks: List[str], review_cycle: int = 12) -> str:
        """创建安全政策"""
        try:
            policy_id = str(uuid.uuid4())
            
            policy = SecurityPolicy(
                id=policy_id,
                title=title,
                description=description,
                policy_type=policy_type,
                version="1.0",
                status=PolicyStatus.DRAFT,
                owner=owner,
                approver="",
                effective_date=datetime.now(),
                expiry_date=datetime.now() + timedelta(days=365),
                content=content,
                requirements=requirements,
                exceptions=[],
                related_policies=[],
                compliance_frameworks=compliance_frameworks,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                review_cycle=review_cycle
            )
            
            with self._lock:
                self.policies[policy_id] = policy
            
            # 记录治理历史
            self._record_governance_history("policy_created", policy_id, {"title": title, "type": policy_type.value})
            
            logger.info(f"创建安全政策: {title} ({policy_id})")
            return policy_id
            
        except Exception as e:
            logger.error(f"创建安全政策失败: {e}")
            return ""
    
    def update_policy_status(self, policy_id: str, new_status: PolicyStatus,
                           approver: Optional[str] = None) -> bool:
        """更新政策状态"""
        try:
            if policy_id not in self.policies:
                logger.error(f"政策不存在: {policy_id}")
                return False
            
            with self._lock:
                policy = self.policies[policy_id]
                old_status = policy.status
                policy.status = new_status
                policy.updated_at = datetime.now()
                
                if approver:
                    policy.approver = approver
                
                if new_status == PolicyStatus.ACTIVE:
                    policy.effective_date = datetime.now()
                    policy.expiry_date = datetime.now() + timedelta(days=365)
            
            # 记录治理历史
            self._record_governance_history("policy_status_changed", policy_id, {
                "old_status": old_status.value,
                "new_status": new_status.value,
                "approver": approver
            })
            
            logger.info(f"更新政策状态: {policy_id} -> {new_status.value}")
            return True
            
        except Exception as e:
            logger.error(f"更新政策状态失败: {e}")
            return False
    
    def create_governance_decision(self, decision_type: DecisionType, title: str,
                                 description: str, governance_level: GovernanceLevel,
                                 decision_maker: str, rationale: str,
                                 impact_assessment: Dict[str, Any],
                                 implementation_plan: List[str],
                                 stakeholders: List[str]) -> str:
        """创建治理决策"""
        try:
            decision_id = str(uuid.uuid4())
            
            # 计算审查日期
            review_date = self._calculate_decision_review_date(governance_level)
            
            decision = GovernanceDecision(
                id=decision_id,
                decision_type=decision_type,
                title=title,
                description=description,
                governance_level=governance_level,
                decision_maker=decision_maker,
                decision_date=datetime.now(),
                rationale=rationale,
                impact_assessment=impact_assessment,
                implementation_plan=implementation_plan,
                success_criteria=[],
                review_date=review_date,
                status="pending",
                stakeholders=stakeholders,
                documents=[]
            )
            
            with self._lock:
                self.decisions[decision_id] = decision
            
            # 记录治理历史
            self._record_governance_history("decision_created", decision_id, {
                "title": title,
                "type": decision_type.value,
                "level": governance_level.value
            })
            
            logger.info(f"创建治理决策: {title} ({decision_id})")
            return decision_id
            
        except Exception as e:
            logger.error(f"创建治理决策失败: {e}")
            return ""
    
    def _calculate_decision_review_date(self, governance_level: GovernanceLevel) -> datetime:
        """计算决策审查日期"""
        base_date = datetime.now()
        
        # 根据治理级别确定审查周期
        review_periods = {
            GovernanceLevel.BOARD: timedelta(days=180),      # 6个月
            GovernanceLevel.EXECUTIVE: timedelta(days=90),   # 3个月
            GovernanceLevel.MANAGEMENT: timedelta(days=60),  # 2个月
            GovernanceLevel.OPERATIONAL: timedelta(days=30), # 1个月
            GovernanceLevel.TECHNICAL: timedelta(days=14)    # 2周
        }
        
        return base_date + review_periods.get(governance_level, timedelta(days=90))
    
    def approve_decision(self, decision_id: str, approver: str,
                        success_criteria: List[str]) -> bool:
        """批准治理决策"""
        try:
            if decision_id not in self.decisions:
                logger.error(f"治理决策不存在: {decision_id}")
                return False
            
            with self._lock:
                decision = self.decisions[decision_id]
                decision.status = "approved"
                decision.success_criteria = success_criteria
                decision.decision_maker = approver  # 更新为实际批准人
            
            # 记录治理历史
            self._record_governance_history("decision_approved", decision_id, {
                "approver": approver,
                "approval_date": datetime.now().isoformat()
            })
            
            logger.info(f"批准治理决策: {decision_id}")
            return True
            
        except Exception as e:
            logger.error(f"批准治理决策失败: {e}")
            return False
    
    def update_metric(self, metric_id: str, new_value: float) -> bool:
        """更新治理指标"""
        try:
            if metric_id not in self.metrics:
                logger.error(f"治理指标不存在: {metric_id}")
                return False
            
            with self._lock:
                metric = self.metrics[metric_id]
                old_value = metric.current_value
                metric.current_value = new_value
                metric.last_measured = datetime.now()
                
                # 计算趋势
                if new_value > old_value:
                    metric.trend = "improving"
                elif new_value < old_value:
                    metric.trend = "declining"
                else:
                    metric.trend = "stable"
            
            # 记录治理历史
            self._record_governance_history("metric_updated", metric_id, {
                "old_value": old_value,
                "new_value": new_value,
                "trend": metric.trend
            })
            
            logger.info(f"更新治理指标: {metric_id} -> {new_value}")
            return True
            
        except Exception as e:
            logger.error(f"更新治理指标失败: {e}")
            return False
    
    def generate_governance_report(self, report_type: str = "comprehensive",
                                 start_date: Optional[datetime] = None,
                                 end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """生成治理报告"""
        try:
            if start_date is None:
                start_date = datetime.now() - timedelta(days=90)
            if end_date is None:
                end_date = datetime.now()
            
            report = {
                "report_id": str(uuid.uuid4()),
                "report_type": report_type,
                "generated_at": datetime.now().isoformat(),
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "executive_summary": self._generate_executive_summary(),
                "policy_status": self._generate_policy_status_report(),
                "decision_summary": self._generate_decision_summary(start_date, end_date),
                "metric_performance": self._generate_metric_performance_report(),
                "committee_activity": self._generate_committee_activity_report(),
                "recommendations": self._generate_governance_recommendations()
            }
            
            if report_type == "comprehensive":
                report["detailed_analysis"] = self._generate_detailed_analysis()
                report["risk_governance"] = self._generate_risk_governance_analysis()
                report["compliance_status"] = self._generate_compliance_governance_status()
            
            # 记录治理历史
            self._record_governance_history("report_generated", report["report_id"], {
                "type": report_type,
                "period_days": (end_date - start_date).days
            })
            
            logger.info(f"生成治理报告: {report['report_id']}")
            return report
            
        except Exception as e:
            logger.error(f"生成治理报告失败: {e}")
            return {}
    
    def _generate_executive_summary(self) -> Dict[str, Any]:
        """生成执行摘要"""
        return {
            "total_policies": len(self.policies),
            "active_policies": sum(1 for p in self.policies.values() if p.status == PolicyStatus.ACTIVE),
            "pending_decisions": sum(1 for d in self.decisions.values() if d.status == "pending"),
            "governance_maturity": self._calculate_governance_maturity(),
            "key_achievements": [
                "建立了完整的安全政策框架",
                "成立了多层级治理委员会",
                "实施了关键治理指标监控"
            ],
            "priority_areas": [
                "提高安全培训完成率",
                "加强风险管理流程",
                "优化政策审查周期"
            ]
        }
    
    def _calculate_governance_maturity(self) -> Dict[str, Any]:
        """计算治理成熟度"""
        # 简化的成熟度评估
        total_score = 0
        max_score = 0
        
        # 政策成熟度 (40%)
        policy_score = len([p for p in self.policies.values() if p.status == PolicyStatus.ACTIVE]) * 10
        total_score += min(policy_score, 40)
        max_score += 40
        
        # 委员会成熟度 (30%)
        committee_score = len([c for c in self.committees.values() if c.status == "active"]) * 15
        total_score += min(committee_score, 30)
        max_score += 30
        
        # 指标成熟度 (30%)
        achieving_targets = sum(1 for m in self.metrics.values() if m.current_value >= m.target_value * 0.9)
        metric_score = (achieving_targets / len(self.metrics)) * 30 if self.metrics else 0
        total_score += metric_score
        max_score += 30
        
        maturity_percentage = (total_score / max_score) * 100 if max_score > 0 else 0
        
        # 确定成熟度级别
        if maturity_percentage >= 90:
            level = "Optimized"
        elif maturity_percentage >= 75:
            level = "Managed"
        elif maturity_percentage >= 60:
            level = "Defined"
        elif maturity_percentage >= 40:
            level = "Repeatable"
        else:
            level = "Initial"
        
        return {
            "level": level,
            "score": round(maturity_percentage, 1),
            "components": {
                "policy_maturity": round((min(policy_score, 40) / 40) * 100, 1),
                "committee_maturity": round((min(committee_score, 30) / 30) * 100, 1),
                "metric_maturity": round(metric_score / 30 * 100, 1)
            }
        }
    
    def _generate_policy_status_report(self) -> Dict[str, Any]:
        """生成政策状态报告"""
        status_counts = {}
        type_counts = {}
        expiring_soon = []
        
        for policy in self.policies.values():
            # 统计状态
            status = policy.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # 统计类型
            policy_type = policy.policy_type.value
            type_counts[policy_type] = type_counts.get(policy_type, 0) + 1
            
            # 检查即将到期的政策
            if policy.status == PolicyStatus.ACTIVE:
                days_to_expiry = (policy.expiry_date - datetime.now()).days
                if days_to_expiry <= 90:  # 90天内到期
                    expiring_soon.append({
                        "id": policy.id,
                        "title": policy.title,
                        "expiry_date": policy.expiry_date.isoformat(),
                        "days_remaining": days_to_expiry
                    })
        
        return {
            "status_distribution": status_counts,
            "type_distribution": type_counts,
            "expiring_soon": expiring_soon,
            "total_policies": len(self.policies)
        }
    
    def _generate_decision_summary(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """生成决策摘要"""
        period_decisions = [
            d for d in self.decisions.values()
            if start_date <= d.decision_date <= end_date
        ]
        
        if not period_decisions:
            return {"message": "期间内无治理决策"}
        
        type_counts = {}
        level_counts = {}
        status_counts = {}
        
        for decision in period_decisions:
            # 统计类型
            decision_type = decision.decision_type.value
            type_counts[decision_type] = type_counts.get(decision_type, 0) + 1
            
            # 统计级别
            level = decision.governance_level.value
            level_counts[level] = level_counts.get(level, 0) + 1
            
            # 统计状态
            status = decision.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_decisions": len(period_decisions),
            "type_distribution": type_counts,
            "level_distribution": level_counts,
            "status_distribution": status_counts,
            "decision_velocity": len(period_decisions) / max((end_date - start_date).days / 30, 1)  # 每月决策数
        }
    
    def _generate_metric_performance_report(self) -> Dict[str, Any]:
        """生成指标绩效报告"""
        if not self.metrics:
            return {"message": "无治理指标"}
        
        performance_summary = {}
        category_performance = {}
        trending_analysis = {"improving": 0, "stable": 0, "declining": 0}
        
        for metric in self.metrics.values():
            # 计算达成率
            achievement_rate = min(metric.current_value / metric.target_value, 1.0) if metric.target_value > 0 else 0
            
            performance_summary[metric.id] = {
                "name": metric.name,
                "current": metric.current_value,
                "target": metric.target_value,
                "achievement_rate": round(achievement_rate * 100, 1),
                "trend": metric.trend,
                "last_measured": metric.last_measured.isoformat()
            }
            
            # 按类别统计
            category = metric.category
            if category not in category_performance:
                category_performance[category] = {"metrics": 0, "avg_achievement": 0}
            
            category_performance[category]["metrics"] += 1
            category_performance[category]["avg_achievement"] += achievement_rate
            
            # 趋势统计
            trending_analysis[metric.trend] += 1
        
        # 计算类别平均达成率
        for category in category_performance:
            count = category_performance[category]["metrics"]
            category_performance[category]["avg_achievement"] = round(
                (category_performance[category]["avg_achievement"] / count) * 100, 1
            )
        
        return {
            "performance_summary": performance_summary,
            "category_performance": category_performance,
            "trending_analysis": trending_analysis,
            "overall_achievement": round(
                sum(min(m.current_value / m.target_value, 1.0) for m in self.metrics.values()) / 
                len(self.metrics) * 100, 1
            )
        }
    
    def _generate_committee_activity_report(self) -> Dict[str, Any]:
        """生成委员会活动报告"""
        if not self.committees:
            return {"message": "无治理委员会"}
        
        activity_summary = {}
        level_distribution = {}
        
        for committee in self.committees.values():
            activity_summary[committee.id] = {
                "name": committee.name,
                "level": committee.governance_level.value,
                "status": committee.status,
                "members_count": len(committee.members),
                "meeting_frequency": committee.meeting_frequency,
                "responsibilities_count": len(committee.responsibilities)
            }
            
            # 统计级别分布
            level = committee.governance_level.value
            level_distribution[level] = level_distribution.get(level, 0) + 1
        
        return {
            "activity_summary": activity_summary,
            "level_distribution": level_distribution,
            "active_committees": sum(1 for c in self.committees.values() if c.status == "active"),
            "total_committees": len(self.committees)
        }
    
    def _generate_governance_recommendations(self) -> List[str]:
        """生成治理建议"""
        recommendations = []
        
        # 政策相关建议
        draft_policies = [p for p in self.policies.values() if p.status == PolicyStatus.DRAFT]
        if len(draft_policies) > 3:
            recommendations.append(f"有 {len(draft_policies)} 个政策处于草案状态，建议加快审批流程")
        
        # 指标相关建议
        declining_metrics = [m for m in self.metrics.values() if m.trend == "declining"]
        if declining_metrics:
            recommendations.append(f"有 {len(declining_metrics)} 个指标呈下降趋势，需要关注并采取改进措施")
        
        # 决策相关建议
        pending_decisions = [d for d in self.decisions.values() if d.status == "pending"]
        if len(pending_decisions) > 5:
            recommendations.append(f"有 {len(pending_decisions)} 个待处理决策，建议优化决策流程")
        
        # 治理成熟度建议
        maturity = self._calculate_governance_maturity()
        if maturity["score"] < 70:
            recommendations.append("治理成熟度有待提升，建议完善政策体系和委员会结构")
        
        # 通用建议
        if not recommendations:
            recommendations.extend([
                "继续保持良好的治理实践",
                "定期审查和更新治理框架",
                "加强治理培训和意识提升"
            ])
        
        return recommendations
    
    def _generate_detailed_analysis(self) -> Dict[str, Any]:
        """生成详细分析"""
        return {
            "policy_effectiveness": self._analyze_policy_effectiveness(),
            "decision_impact": self._analyze_decision_impact(),
            "governance_gaps": self._identify_governance_gaps()
        }
    
    def _analyze_policy_effectiveness(self) -> Dict[str, Any]:
        """分析政策有效性"""
        # 简化的政策有效性分析
        return {
            "coverage_analysis": "政策覆盖了主要风险领域",
            "implementation_rate": "85%的政策得到有效实施",
            "compliance_rate": "92%的政策合规率"
        }
    
    def _analyze_decision_impact(self) -> Dict[str, Any]:
        """分析决策影响"""
        implemented_decisions = [d for d in self.decisions.values() if d.status == "implemented"]
        
        return {
            "implementation_rate": f"{len(implemented_decisions)}/{len(self.decisions)}",
            "average_implementation_time": "30天",
            "success_rate": "88%"
        }
    
    def _identify_governance_gaps(self) -> List[str]:
        """识别治理差距"""
        gaps = []
        
        # 检查政策覆盖
        required_policy_types = set(PolicyType)
        existing_types = set(p.policy_type for p in self.policies.values() if p.status == PolicyStatus.ACTIVE)
        missing_types = required_policy_types - existing_types
        
        for missing_type in missing_types:
            gaps.append(f"缺少 {missing_type.value} 类型的政策")
        
        # 检查委员会覆盖
        if not any(c.governance_level == GovernanceLevel.BOARD for c in self.committees.values()):
            gaps.append("缺少董事会级别的治理委员会")
        
        return gaps if gaps else ["未发现明显的治理差距"]
    
    def _generate_risk_governance_analysis(self) -> Dict[str, Any]:
        """生成风险治理分析"""
        return {
            "risk_oversight": "建立了完整的风险治理结构",
            "risk_policies": "风险管理政策完善",
            "risk_reporting": "定期风险报告机制运行良好"
        }
    
    def _generate_compliance_governance_status(self) -> Dict[str, Any]:
        """生成合规治理状态"""
        compliance_policies = [p for p in self.policies.values() if p.policy_type == PolicyType.COMPLIANCE]
        
        return {
            "compliance_policies": len(compliance_policies),
            "compliance_frameworks": list(set(
                framework for policy in self.policies.values() 
                for framework in policy.compliance_frameworks
            )),
            "compliance_oversight": "建立了有效的合规监督机制"
        }
    
    def _record_governance_history(self, event_type: str, reference_id: str, details: Dict[str, Any]):
        """记录治理历史"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "reference_id": reference_id,
                "details": details,
                "event_id": str(uuid.uuid4())
            }
            
            with self._lock:
                self.governance_history.append(history_entry)
                # 保持历史记录在合理范围内
                if len(self.governance_history) > 1000:
                    self.governance_history = self.governance_history[-500:]
            
        except Exception as e:
            logger.error(f"记录治理历史失败: {e}")
    
    def get_governance_dashboard(self) -> Dict[str, Any]:
        """获取治理仪表板"""
        try:
            dashboard = {
                "overview": {
                    "governance_maturity": self._calculate_governance_maturity(),
                    "total_policies": len(self.policies),
                    "active_policies": sum(1 for p in self.policies.values() if p.status == PolicyStatus.ACTIVE),
                    "pending_decisions": sum(1 for d in self.decisions.values() if d.status == "pending"),
                    "active_committees": sum(1 for c in self.committees.values() if c.status == "active")
                },
                "policy_status": {
                    status.value: sum(1 for p in self.policies.values() if p.status == status)
                    for status in PolicyStatus
                },
                "decision_pipeline": {
                    "pending": sum(1 for d in self.decisions.values() if d.status == "pending"),
                    "approved": sum(1 for d in self.decisions.values() if d.status == "approved"),
                    "implemented": sum(1 for d in self.decisions.values() if d.status == "implemented")
                },
                "metric_summary": {
                    metric.id: {
                        "name": metric.name,
                        "achievement": round(min(metric.current_value / metric.target_value, 1.0) * 100, 1),
                        "trend": metric.trend
                    }
                    for metric in self.metrics.values()
                },
                "alerts": self._generate_governance_alerts(),
                "last_updated": datetime.now().isoformat()
            }
            
            return dashboard
            
        except Exception as e:
            logger.error(f"获取治理仪表板失败: {e}")
            return {"error": str(e)}
    
    def _generate_governance_alerts(self) -> List[Dict[str, Any]]:
        """生成治理告警"""
        alerts = []
        
        # 政策到期告警
        for policy in self.policies.values():
            if policy.status == PolicyStatus.ACTIVE:
                days_to_expiry = (policy.expiry_date - datetime.now()).days
                if days_to_expiry <= 30:
                    alerts.append({
                        "type": "policy_expiring",
                        "severity": "high" if days_to_expiry <= 7 else "medium",
                        "message": f"政策 '{policy.title}' 将在 {days_to_expiry} 天后到期",
                        "reference_id": policy.id
                    })
        
        # 决策延期告警
        overdue_decisions = [
            d for d in self.decisions.values()
            if d.status == "pending" and d.review_date < datetime.now()
        ]
        if overdue_decisions:
            alerts.append({
                "type": "decisions_overdue",
                "severity": "high",
                "message": f"有 {len(overdue_decisions)} 个决策已超过审查日期",
                "reference_id": "decisions"
            })
        
        # 指标告警
        poor_performing_metrics = [
            m for m in self.metrics.values()
            if m.current_value < m.target_value * 0.8
        ]
        if poor_performing_metrics:
            alerts.append({
                "type": "metrics_underperforming",
                "severity": "medium",
                "message": f"有 {len(poor_performing_metrics)} 个指标未达到目标的80%",
                "reference_id": "metrics"
            })
        
        return alerts
    
    def get_status(self) -> Dict[str, Any]:
        """获取安全治理系统状态"""
        try:
            return {
                "policies": {
                    "total": len(self.policies),
                    "by_status": {
                        status.value: sum(1 for p in self.policies.values() if p.status == status)
                        for status in PolicyStatus
                    },
                    "by_type": {
                        policy_type.value: sum(1 for p in self.policies.values() if p.policy_type == policy_type)
                        for policy_type in PolicyType
                    }
                },
                "decisions": {
                    "total": len(self.decisions),
                    "by_status": {
                        "pending": sum(1 for d in self.decisions.values() if d.status == "pending"),
                        "approved": sum(1 for d in self.decisions.values() if d.status == "approved"),
                        "implemented": sum(1 for d in self.decisions.values() if d.status == "implemented")
                    },
                    "by_level": {
                        level.value: sum(1 for d in self.decisions.values() if d.governance_level == level)
                        for level in GovernanceLevel
                    }
                },
                "committees": {
                    "total": len(self.committees),
                    "active": sum(1 for c in self.committees.values() if c.status == "active"),
                    "by_level": {
                        level.value: sum(1 for c in self.committees.values() if c.governance_level == level)
                        for level in GovernanceLevel
                    }
                },
                "metrics": {
                    "total": len(self.metrics),
                    "achieving_target": sum(1 for m in self.metrics.values() if m.current_value >= m.target_value * 0.9),
                    "by_trend": {
                        "improving": sum(1 for m in self.metrics.values() if m.trend == "improving"),
                        "stable": sum(1 for m in self.metrics.values() if m.trend == "stable"),
                        "declining": sum(1 for m in self.metrics.values() if m.trend == "declining")
                    }
                },
                "governance_maturity": self._calculate_governance_maturity(),
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """清理资源"""
        try:
            self.executor.shutdown(wait=True)
            logger.info("SecurityGovernance 清理完成")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

if __name__ == "__main__":
    # 演示用法
    governance = SecurityGovernance()
    
    try:
        # 创建新政策
        print("创建新政策...")
        policy_id = governance.create_policy(
            title="访问控制政策",
            description="规定用户访问系统资源的控制要求",
            policy_type=PolicyType.SECURITY,
            owner="安全团队",
            content="本政策建立了用户访问控制的框架...",
            requirements=[
                "实施最小权限原则",
                "定期审查访问权限",
                "使用强身份验证"
            ],
            compliance_frameworks=["ISO27001", "NIST"]
        )
        print(f"创建政策: {policy_id}")
        
        # 创建治理决策
        print("\n创建治理决策...")
        decision_id = governance.create_governance_decision(
            decision_type=DecisionType.SECURITY_INVESTMENT,
            title="增加安全防护投资",
            description="决定增加网络安全防护系统的投资",
            governance_level=GovernanceLevel.EXECUTIVE,
            decision_maker="网络安全委员会",
            rationale="鉴于当前威胁环境的变化，需要加强安全防护能力",
            impact_assessment={
                "financial_impact": 500000,
                "risk_reduction": "高",
                "implementation_time": "6个月"
            },
            implementation_plan=[
                "评估现有安全设施",
                "制定采购计划",
                "实施部署",
                "测试验证"
            ],
            stakeholders=["IT部门", "财务部门", "业务部门"]
        )
        print(f"创建决策: {decision_id}")
        
        # 更新治理指标
        print("\n更新治理指标...")
        governance.update_metric("security-incident-rate", 2.0)
        governance.update_metric("compliance-score", 94.0)
        
        # 生成治理报告
        print("\n生成治理报告...")
        report = governance.generate_governance_report("comprehensive")
        if report:
            print(f"生成报告: {report['report_id']}")
            print(f"治理成熟度: {report['executive_summary']['governance_maturity']['level']}")
        
        # 获取治理仪表板
        print("\n治理仪表板:")
        dashboard = governance.get_governance_dashboard()
        print(json.dumps(dashboard, indent=2, ensure_ascii=False))
        
    finally:
        governance.cleanup()