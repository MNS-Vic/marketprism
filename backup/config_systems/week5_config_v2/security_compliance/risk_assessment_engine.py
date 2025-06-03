"""
企业级风险评估引擎

提供智能风险识别、风险评估、风险量化和风险缓解建议功能。
支持多维度风险分析和企业级风险管理能力。

Author: MarketPrism Team
Date: 2025-01-28
"""

import time
import json
import uuid
import math
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from enum import Enum
from dataclasses import dataclass, asdict
import logging
from concurrent.futures import ThreadPoolExecutor
import threading

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RiskCategory(Enum):
    """风险类别"""
    SECURITY = "security"             # 安全风险
    OPERATIONAL = "operational"       # 运营风险
    COMPLIANCE = "compliance"         # 合规风险
    FINANCIAL = "financial"           # 财务风险
    REPUTATIONAL = "reputational"     # 声誉风险
    TECHNICAL = "technical"           # 技术风险
    STRATEGIC = "strategic"           # 战略风险
    LEGAL = "legal"                   # 法律风险

class RiskLevel(Enum):
    """风险级别"""
    CRITICAL = "critical"             # 极高风险
    HIGH = "high"                     # 高风险
    MEDIUM = "medium"                 # 中等风险
    LOW = "low"                       # 低风险
    MINIMAL = "minimal"               # 极低风险

class RiskLikelihood(Enum):
    """风险可能性"""
    VERY_HIGH = "very_high"          # 非常高 (>80%)
    HIGH = "high"                    # 高 (60-80%)
    MEDIUM = "medium"                # 中等 (40-60%)
    LOW = "low"                      # 低 (20-40%)
    VERY_LOW = "very_low"            # 非常低 (<20%)

class RiskImpact(Enum):
    """风险影响"""
    CATASTROPHIC = "catastrophic"     # 灾难性
    MAJOR = "major"                   # 重大
    MODERATE = "moderate"             # 中等
    MINOR = "minor"                   # 轻微
    NEGLIGIBLE = "negligible"         # 可忽略

@dataclass
class RiskFactor:
    """风险因子数据类"""
    id: str
    name: str
    category: RiskCategory
    description: str
    weight: float  # 0.0-1.0
    current_value: float  # 当前值
    threshold_values: Dict[str, float]  # 阈值
    measurement_unit: str
    data_source: str
    last_updated: datetime

@dataclass
class RiskAssessment:
    """风险评估数据类"""
    id: str
    title: str
    description: str
    category: RiskCategory
    likelihood: RiskLikelihood
    impact: RiskImpact
    risk_level: RiskLevel
    risk_score: float  # 0.0-1.0
    factors: List[str]  # risk factor IDs
    mitigation_strategies: List[str]
    owner: str
    assessed_by: str
    assessment_date: datetime
    review_date: datetime
    status: str  # active, mitigated, accepted, transferred
    cost_of_mitigation: Optional[float] = None

@dataclass
class RiskScenario:
    """风险场景数据类"""
    id: str
    name: str
    description: str
    category: RiskCategory
    trigger_conditions: List[str]
    potential_impacts: List[str]
    likelihood_factors: List[str]
    estimated_probability: float
    estimated_impact_cost: float
    timeframe: str
    related_assessments: List[str]

class RiskAssessmentEngine:
    """企业级风险评估引擎"""
    
    def __init__(self):
        """初始化风险评估引擎"""
        self.risk_factors: Dict[str, RiskFactor] = {}
        self.assessments: Dict[str, RiskAssessment] = {}
        self.scenarios: Dict[str, RiskScenario] = {}
        self.risk_history: List[Dict[str, Any]] = []
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._lock = threading.Lock()
        
        # 初始化默认风险因子
        self._initialize_default_factors()
        
        logger.info("RiskAssessmentEngine 初始化完成")
    
    def _initialize_default_factors(self):
        """初始化默认风险因子"""
        default_factors = [
            # 安全风险因子
            RiskFactor(
                id="security-auth-failures",
                name="认证失败次数",
                category=RiskCategory.SECURITY,
                description="系统认证失败的频率",
                weight=0.8,
                current_value=0.0,
                threshold_values={"low": 10, "medium": 50, "high": 100, "critical": 200},
                measurement_unit="次/小时",
                data_source="authentication_system",
                last_updated=datetime.now()
            ),
            RiskFactor(
                id="security-vuln-count",
                name="安全漏洞数量",
                category=RiskCategory.SECURITY,
                description="系统中发现的安全漏洞数量",
                weight=0.9,
                current_value=0.0,
                threshold_values={"low": 1, "medium": 3, "high": 5, "critical": 10},
                measurement_unit="个",
                data_source="vulnerability_scanner",
                last_updated=datetime.now()
            ),
            # 运营风险因子
            RiskFactor(
                id="ops-system-downtime",
                name="系统停机时间",
                category=RiskCategory.OPERATIONAL,
                description="系统不可用时间百分比",
                weight=0.85,
                current_value=0.0,
                threshold_values={"low": 0.1, "medium": 0.5, "high": 1.0, "critical": 2.0},
                measurement_unit="百分比",
                data_source="monitoring_system",
                last_updated=datetime.now()
            ),
            RiskFactor(
                id="ops-error-rate",
                name="系统错误率",
                category=RiskCategory.OPERATIONAL,
                description="系统错误发生的频率",
                weight=0.7,
                current_value=0.0,
                threshold_values={"low": 1.0, "medium": 3.0, "high": 5.0, "critical": 10.0},
                measurement_unit="百分比",
                data_source="application_logs",
                last_updated=datetime.now()
            ),
            # 合规风险因子
            RiskFactor(
                id="compliance-violations",
                name="合规违规数量",
                category=RiskCategory.COMPLIANCE,
                description="发现的合规违规事件数量",
                weight=0.95,
                current_value=0.0,
                threshold_values={"low": 1, "medium": 3, "high": 5, "critical": 10},
                measurement_unit="个",
                data_source="compliance_system",
                last_updated=datetime.now()
            ),
            # 技术风险因子
            RiskFactor(
                id="tech-performance-degradation",
                name="性能下降程度",
                category=RiskCategory.TECHNICAL,
                description="系统性能相对基准的下降程度",
                weight=0.6,
                current_value=0.0,
                threshold_values={"low": 10.0, "medium": 25.0, "high": 50.0, "critical": 75.0},
                measurement_unit="百分比",
                data_source="performance_monitor",
                last_updated=datetime.now()
            )
        ]
        
        for factor in default_factors:
            self.risk_factors[factor.id] = factor
        
        logger.info(f"加载了 {len(default_factors)} 个默认风险因子")
    
    def add_risk_factor(self, factor: RiskFactor) -> bool:
        """添加风险因子"""
        try:
            with self._lock:
                self.risk_factors[factor.id] = factor
            
            logger.info(f"添加风险因子: {factor.id} - {factor.name}")
            return True
        except Exception as e:
            logger.error(f"添加风险因子失败: {e}")
            return False
    
    def update_factor_value(self, factor_id: str, new_value: float) -> bool:
        """更新风险因子值"""
        try:
            if factor_id not in self.risk_factors:
                logger.error(f"风险因子不存在: {factor_id}")
                return False
            
            with self._lock:
                self.risk_factors[factor_id].current_value = new_value
                self.risk_factors[factor_id].last_updated = datetime.now()
            
            logger.debug(f"更新风险因子 {factor_id} 值为: {new_value}")
            return True
        except Exception as e:
            logger.error(f"更新风险因子值失败: {e}")
            return False
    
    def calculate_factor_risk_level(self, factor_id: str) -> Tuple[RiskLevel, float]:
        """计算单个风险因子的风险级别"""
        try:
            if factor_id not in self.risk_factors:
                return RiskLevel.MINIMAL, 0.0
            
            factor = self.risk_factors[factor_id]
            current_value = factor.current_value
            thresholds = factor.threshold_values
            
            # 根据阈值确定风险级别
            if current_value >= thresholds.get("critical", float('inf')):
                risk_level = RiskLevel.CRITICAL
                risk_score = 1.0
            elif current_value >= thresholds.get("high", float('inf')):
                risk_level = RiskLevel.HIGH
                risk_score = 0.8
            elif current_value >= thresholds.get("medium", float('inf')):
                risk_level = RiskLevel.MEDIUM
                risk_score = 0.6
            elif current_value >= thresholds.get("low", float('inf')):
                risk_level = RiskLevel.LOW
                risk_score = 0.4
            else:
                risk_level = RiskLevel.MINIMAL
                risk_score = 0.2
            
            # 应用权重
            weighted_score = risk_score * factor.weight
            
            return risk_level, weighted_score
            
        except Exception as e:
            logger.error(f"计算风险因子级别失败: {e}")
            return RiskLevel.MINIMAL, 0.0
    
    def perform_risk_assessment(self, title: str, description: str,
                              category: RiskCategory, factor_ids: List[str],
                              owner: str, assessed_by: str) -> str:
        """执行风险评估"""
        try:
            assessment_id = str(uuid.uuid4())
            
            # 计算综合风险分数
            total_weighted_score = 0.0
            total_weight = 0.0
            risk_levels = []
            
            for factor_id in factor_ids:
                if factor_id in self.risk_factors:
                    factor = self.risk_factors[factor_id]
                    risk_level, weighted_score = self.calculate_factor_risk_level(factor_id)
                    
                    total_weighted_score += weighted_score
                    total_weight += factor.weight
                    risk_levels.append(risk_level)
            
            # 计算平均风险分数
            if total_weight > 0:
                average_risk_score = total_weighted_score / total_weight
            else:
                average_risk_score = 0.0
            
            # 确定整体风险级别
            overall_risk_level = self._determine_overall_risk_level(risk_levels, average_risk_score)
            
            # 估算可能性和影响
            likelihood = self._estimate_likelihood(category, risk_levels)
            impact = self._estimate_impact(category, average_risk_score)
            
            # 生成缓解策略
            mitigation_strategies = self._generate_mitigation_strategies(category, overall_risk_level, factor_ids)
            
            # 计算审查日期
            review_date = self._calculate_review_date(overall_risk_level)
            
            assessment = RiskAssessment(
                id=assessment_id,
                title=title,
                description=description,
                category=category,
                likelihood=likelihood,
                impact=impact,
                risk_level=overall_risk_level,
                risk_score=average_risk_score,
                factors=factor_ids,
                mitigation_strategies=mitigation_strategies,
                owner=owner,
                assessed_by=assessed_by,
                assessment_date=datetime.now(),
                review_date=review_date,
                status="active"
            )
            
            with self._lock:
                self.assessments[assessment_id] = assessment
            
            # 记录风险历史
            self._record_risk_history("assessment_created", assessment_id, average_risk_score)
            
            logger.info(f"完成风险评估: {title} ({assessment_id}), 风险级别: {overall_risk_level.value}")
            return assessment_id
            
        except Exception as e:
            logger.error(f"执行风险评估失败: {e}")
            return ""
    
    def _determine_overall_risk_level(self, risk_levels: List[RiskLevel], average_score: float) -> RiskLevel:
        """确定整体风险级别"""
        if not risk_levels:
            return RiskLevel.MINIMAL
        
        # 检查是否有极高风险
        if RiskLevel.CRITICAL in risk_levels:
            return RiskLevel.CRITICAL
        
        # 检查高风险因子数量
        high_risk_count = sum(1 for level in risk_levels if level in [RiskLevel.HIGH, RiskLevel.CRITICAL])
        if high_risk_count >= len(risk_levels) * 0.5:  # 50%以上高风险
            return RiskLevel.HIGH
        
        # 基于平均分数
        if average_score >= 0.8:
            return RiskLevel.HIGH
        elif average_score >= 0.6:
            return RiskLevel.MEDIUM
        elif average_score >= 0.4:
            return RiskLevel.LOW
        else:
            return RiskLevel.MINIMAL
    
    def _estimate_likelihood(self, category: RiskCategory, risk_levels: List[RiskLevel]) -> RiskLikelihood:
        """估算风险可能性"""
        # 基于风险类别和当前风险级别估算
        high_risk_ratio = sum(1 for level in risk_levels if level in [RiskLevel.HIGH, RiskLevel.CRITICAL]) / len(risk_levels) if risk_levels else 0
        
        if high_risk_ratio >= 0.7:
            return RiskLikelihood.VERY_HIGH
        elif high_risk_ratio >= 0.5:
            return RiskLikelihood.HIGH
        elif high_risk_ratio >= 0.3:
            return RiskLikelihood.MEDIUM
        elif high_risk_ratio >= 0.1:
            return RiskLikelihood.LOW
        else:
            return RiskLikelihood.VERY_LOW
    
    def _estimate_impact(self, category: RiskCategory, risk_score: float) -> RiskImpact:
        """估算风险影响"""
        # 基于风险类别调整影响评估
        category_multiplier = {
            RiskCategory.SECURITY: 1.2,
            RiskCategory.COMPLIANCE: 1.1,
            RiskCategory.FINANCIAL: 1.3,
            RiskCategory.REPUTATIONAL: 1.0,
            RiskCategory.OPERATIONAL: 0.9,
            RiskCategory.TECHNICAL: 0.8,
            RiskCategory.STRATEGIC: 1.1,
            RiskCategory.LEGAL: 1.2
        }.get(category, 1.0)
        
        adjusted_score = risk_score * category_multiplier
        
        if adjusted_score >= 0.9:
            return RiskImpact.CATASTROPHIC
        elif adjusted_score >= 0.7:
            return RiskImpact.MAJOR
        elif adjusted_score >= 0.5:
            return RiskImpact.MODERATE
        elif adjusted_score >= 0.3:
            return RiskImpact.MINOR
        else:
            return RiskImpact.NEGLIGIBLE
    
    def _generate_mitigation_strategies(self, category: RiskCategory, risk_level: RiskLevel, factor_ids: List[str]) -> List[str]:
        """生成缓解策略"""
        strategies = []
        
        # 基于风险类别的通用策略
        category_strategies = {
            RiskCategory.SECURITY: [
                "实施多因素认证",
                "加强访问控制",
                "定期安全扫描",
                "员工安全培训",
                "部署入侵检测系统"
            ],
            RiskCategory.OPERATIONAL: [
                "建立冗余系统",
                "制定业务连续性计划",
                "改进监控和告警",
                "定期备份验证",
                "流程自动化"
            ],
            RiskCategory.COMPLIANCE: [
                "建立合规管理体系",
                "定期合规培训",
                "实施合规监控",
                "建立举报机制",
                "定期合规审计"
            ],
            RiskCategory.TECHNICAL: [
                "系统性能优化",
                "代码质量改进",
                "技术债务清理",
                "容量规划",
                "灾难恢复测试"
            ],
            RiskCategory.FINANCIAL: [
                "建立财务控制",
                "风险分散投资",
                "现金流管理",
                "保险覆盖",
                "财务监控"
            ]
        }
        
        base_strategies = category_strategies.get(category, ["制定风险缓解计划"])
        
        # 基于风险级别选择策略数量
        if risk_level == RiskLevel.CRITICAL:
            strategies.extend(base_strategies[:4])
            strategies.append("立即启动应急响应")
        elif risk_level == RiskLevel.HIGH:
            strategies.extend(base_strategies[:3])
        elif risk_level == RiskLevel.MEDIUM:
            strategies.extend(base_strategies[:2])
        else:
            strategies.append(base_strategies[0])
        
        # 基于具体风险因子的定制策略
        for factor_id in factor_ids:
            if factor_id in self.risk_factors:
                factor = self.risk_factors[factor_id]
                if "auth" in factor.id:
                    strategies.append("加强身份验证机制")
                elif "vuln" in factor.id:
                    strategies.append("修复已知漏洞")
                elif "downtime" in factor.id:
                    strategies.append("提高系统可用性")
                elif "error" in factor.id:
                    strategies.append("改进错误处理机制")
        
        return list(set(strategies))  # 去重
    
    def _calculate_review_date(self, risk_level: RiskLevel) -> datetime:
        """计算审查日期"""
        base_date = datetime.now()
        
        # 根据风险级别确定审查频率
        if risk_level == RiskLevel.CRITICAL:
            return base_date + timedelta(weeks=2)
        elif risk_level == RiskLevel.HIGH:
            return base_date + timedelta(weeks=4)
        elif risk_level == RiskLevel.MEDIUM:
            return base_date + timedelta(weeks=12)
        else:
            return base_date + timedelta(weeks=26)
    
    def create_risk_scenario(self, name: str, description: str, category: RiskCategory,
                           trigger_conditions: List[str], potential_impacts: List[str],
                           estimated_probability: float, estimated_impact_cost: float,
                           timeframe: str) -> str:
        """创建风险场景"""
        try:
            scenario_id = str(uuid.uuid4())
            
            scenario = RiskScenario(
                id=scenario_id,
                name=name,
                description=description,
                category=category,
                trigger_conditions=trigger_conditions,
                potential_impacts=potential_impacts,
                likelihood_factors=[],
                estimated_probability=estimated_probability,
                estimated_impact_cost=estimated_impact_cost,
                timeframe=timeframe,
                related_assessments=[]
            )
            
            with self._lock:
                self.scenarios[scenario_id] = scenario
            
            logger.info(f"创建风险场景: {name} ({scenario_id})")
            return scenario_id
            
        except Exception as e:
            logger.error(f"创建风险场景失败: {e}")
            return ""
    
    def run_scenario_analysis(self, scenario_id: str) -> Dict[str, Any]:
        """运行场景分析"""
        try:
            if scenario_id not in self.scenarios:
                logger.error(f"风险场景不存在: {scenario_id}")
                return {}
            
            scenario = self.scenarios[scenario_id]
            
            # 分析当前系统状态
            current_risk_factors = self._analyze_current_state(scenario.category)
            
            # 计算场景实现概率
            actual_probability = self._calculate_scenario_probability(scenario, current_risk_factors)
            
            # 估算潜在损失
            potential_loss = self._estimate_potential_loss(scenario, actual_probability)
            
            # 生成应对措施
            response_measures = self._generate_response_measures(scenario)
            
            analysis_result = {
                "scenario_id": scenario_id,
                "scenario_name": scenario.name,
                "analysis_timestamp": datetime.now().isoformat(),
                "current_probability": actual_probability,
                "estimated_probability": scenario.estimated_probability,
                "probability_change": actual_probability - scenario.estimated_probability,
                "potential_loss": potential_loss,
                "risk_factors": current_risk_factors,
                "response_measures": response_measures,
                "risk_exposure": actual_probability * potential_loss,
                "recommendations": self._generate_scenario_recommendations(scenario, actual_probability)
            }
            
            # 记录分析历史
            self._record_risk_history("scenario_analysis", scenario_id, actual_probability)
            
            logger.info(f"完成场景分析: {scenario.name}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"场景分析失败: {e}")
            return {}
    
    def _analyze_current_state(self, category: RiskCategory) -> Dict[str, Any]:
        """分析当前状态"""
        relevant_factors = {
            factor_id: factor for factor_id, factor in self.risk_factors.items()
            if factor.category == category
        }
        
        current_state = {}
        for factor_id, factor in relevant_factors.items():
            risk_level, risk_score = self.calculate_factor_risk_level(factor_id)
            current_state[factor_id] = {
                "name": factor.name,
                "current_value": factor.current_value,
                "risk_level": risk_level.value,
                "risk_score": risk_score,
                "last_updated": factor.last_updated.isoformat()
            }
        
        return current_state
    
    def _calculate_scenario_probability(self, scenario: RiskScenario, current_factors: Dict[str, Any]) -> float:
        """计算场景实现概率"""
        if not current_factors:
            return scenario.estimated_probability
        
        # 基于当前风险因子状态调整概率
        risk_scores = [factor["risk_score"] for factor in current_factors.values()]
        average_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0
        
        # 概率调整因子
        adjustment_factor = 1.0 + (average_risk - 0.5)  # 基准0.5
        adjusted_probability = scenario.estimated_probability * adjustment_factor
        
        return min(max(adjusted_probability, 0.0), 1.0)  # 限制在0-1范围
    
    def _estimate_potential_loss(self, scenario: RiskScenario, probability: float) -> float:
        """估算潜在损失"""
        # 基础损失
        base_loss = scenario.estimated_impact_cost
        
        # 基于概率调整
        probability_multiplier = 1.0 + (probability - 0.5) * 0.5
        
        return base_loss * probability_multiplier
    
    def _generate_response_measures(self, scenario: RiskScenario) -> List[str]:
        """生成应对措施"""
        measures = []
        
        # 基于风险类别的应对措施
        category_measures = {
            RiskCategory.SECURITY: [
                "启动安全事件响应计划",
                "隔离受影响系统",
                "进行法务取证",
                "通知相关监管机构"
            ],
            RiskCategory.OPERATIONAL: [
                "启动业务连续性计划",
                "切换到备用系统",
                "通知客户和合作伙伴",
                "评估影响范围"
            ],
            RiskCategory.COMPLIANCE: [
                "启动合规事件响应",
                "进行内部调查",
                "准备监管报告",
                "实施纠正措施"
            ]
        }
        
        measures.extend(category_measures.get(scenario.category, ["启动通用应急响应"]))
        
        # 基于影响程度的措施
        if scenario.estimated_impact_cost > 1000000:  # 100万以上
            measures.extend([
                "召集危机管理委员会",
                "启动媒体沟通计划",
                "考虑启动保险理赔"
            ])
        
        return measures
    
    def _generate_scenario_recommendations(self, scenario: RiskScenario, current_probability: float) -> List[str]:
        """生成场景建议"""
        recommendations = []
        
        if current_probability > scenario.estimated_probability * 1.2:
            recommendations.append("当前风险水平显著高于预期，建议立即采取预防措施")
        
        if current_probability > 0.7:
            recommendations.append("风险实现概率较高，建议准备应急响应计划")
        
        if scenario.estimated_impact_cost > 500000:
            recommendations.append("潜在损失较大，建议考虑风险转移或保险")
        
        recommendations.extend([
            "定期监控相关风险因子",
            "更新风险应对计划",
            "进行定期演练和测试"
        ])
        
        return recommendations
    
    def _record_risk_history(self, event_type: str, reference_id: str, risk_value: float):
        """记录风险历史"""
        try:
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "reference_id": reference_id,
                "risk_value": risk_value,
                "event_id": str(uuid.uuid4())
            }
            
            with self._lock:
                self.risk_history.append(history_entry)
                # 保持历史记录在合理范围内
                if len(self.risk_history) > 1000:
                    self.risk_history = self.risk_history[-500:]
            
        except Exception as e:
            logger.error(f"记录风险历史失败: {e}")
    
    def get_risk_dashboard(self) -> Dict[str, Any]:
        """获取风险仪表板数据"""
        try:
            dashboard = {
                "summary": {
                    "total_factors": len(self.risk_factors),
                    "total_assessments": len(self.assessments),
                    "total_scenarios": len(self.scenarios),
                    "last_updated": datetime.now().isoformat()
                },
                "risk_distribution": {},
                "top_risks": [],
                "factor_status": {},
                "recent_assessments": []
            }
            
            # 风险分布统计
            risk_levels = [assessment.risk_level for assessment in self.assessments.values()]
            for level in RiskLevel:
                dashboard["risk_distribution"][level.value] = risk_levels.count(level)
            
            # 最高风险评估
            sorted_assessments = sorted(
                self.assessments.values(),
                key=lambda x: x.risk_score,
                reverse=True
            )
            dashboard["top_risks"] = [
                {
                    "id": assessment.id,
                    "title": assessment.title,
                    "category": assessment.category.value,
                    "risk_level": assessment.risk_level.value,
                    "risk_score": round(assessment.risk_score, 3)
                }
                for assessment in sorted_assessments[:5]
            ]
            
            # 风险因子状态
            for factor_id, factor in self.risk_factors.items():
                risk_level, risk_score = self.calculate_factor_risk_level(factor_id)
                dashboard["factor_status"][factor_id] = {
                    "name": factor.name,
                    "category": factor.category.value,
                    "risk_level": risk_level.value,
                    "risk_score": round(risk_score, 3),
                    "current_value": factor.current_value
                }
            
            # 最近评估
            recent_assessments = sorted(
                self.assessments.values(),
                key=lambda x: x.assessment_date,
                reverse=True
            )
            dashboard["recent_assessments"] = [
                {
                    "id": assessment.id,
                    "title": assessment.title,
                    "date": assessment.assessment_date.isoformat(),
                    "risk_level": assessment.risk_level.value,
                    "status": assessment.status
                }
                for assessment in recent_assessments[:10]
            ]
            
            return dashboard
            
        except Exception as e:
            logger.error(f"获取风险仪表板失败: {e}")
            return {"error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """获取风险评估引擎状态"""
        try:
            return {
                "factors": {
                    "total": len(self.risk_factors),
                    "by_category": {
                        category.value: sum(1 for factor in self.risk_factors.values() 
                                          if factor.category == category)
                        for category in RiskCategory
                    }
                },
                "assessments": {
                    "total": len(self.assessments),
                    "active": sum(1 for assessment in self.assessments.values() 
                                if assessment.status == "active"),
                    "by_risk_level": {
                        level.value: sum(1 for assessment in self.assessments.values() 
                                       if assessment.risk_level == level)
                        for level in RiskLevel
                    }
                },
                "scenarios": {
                    "total": len(self.scenarios),
                    "by_category": {
                        category.value: sum(1 for scenario in self.scenarios.values() 
                                          if scenario.category == category)
                        for category in RiskCategory
                    }
                },
                "history": {
                    "total_events": len(self.risk_history)
                },
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """清理资源"""
        try:
            self.executor.shutdown(wait=True)
            logger.info("RiskAssessmentEngine 清理完成")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

if __name__ == "__main__":
    # 演示用法
    engine = RiskAssessmentEngine()
    
    try:
        # 更新风险因子值
        print("更新风险因子值...")
        engine.update_factor_value("security-auth-failures", 75)
        engine.update_factor_value("security-vuln-count", 3)
        engine.update_factor_value("ops-system-downtime", 0.8)
        
        # 执行风险评估
        print("\n执行风险评估...")
        assessment_id = engine.perform_risk_assessment(
            title="系统安全风险评估",
            description="对当前系统的安全风险进行评估",
            category=RiskCategory.SECURITY,
            factor_ids=["security-auth-failures", "security-vuln-count"],
            owner="安全团队",
            assessed_by="风险分析师"
        )
        print(f"风险评估ID: {assessment_id}")
        
        # 创建风险场景
        print("\n创建风险场景...")
        scenario_id = engine.create_risk_scenario(
            name="大规模网络攻击",
            description="针对核心系统的大规模网络攻击",
            category=RiskCategory.SECURITY,
            trigger_conditions=["多个安全漏洞", "外部威胁增加", "内部控制薄弱"],
            potential_impacts=["系统瘫痪", "数据泄露", "声誉损失"],
            estimated_probability=0.3,
            estimated_impact_cost=2000000,
            timeframe="1年内"
        )
        print(f"风险场景ID: {scenario_id}")
        
        # 运行场景分析
        print("\n运行场景分析...")
        analysis = engine.run_scenario_analysis(scenario_id)
        if analysis:
            print(f"场景实现概率: {analysis['current_probability']:.1%}")
            print(f"风险暴露: ${analysis['risk_exposure']:,.0f}")
        
        # 获取风险仪表板
        print("\n风险仪表板:")
        dashboard = engine.get_risk_dashboard()
        print(json.dumps(dashboard, indent=2, ensure_ascii=False))
        
    finally:
        engine.cleanup()