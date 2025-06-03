"""
智能决策支持系统 - Week 5 Day 9
整合分析结果，提供综合决策建议和自动化决策支持
"""

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
import json
import random

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """决策类型"""
    TRADING_DECISION = "trading_decision"
    RISK_MANAGEMENT = "risk_management"
    PORTFOLIO_ALLOCATION = "portfolio_allocation"
    POSITION_SIZING = "position_sizing"
    MARKET_TIMING = "market_timing"
    ASSET_SELECTION = "asset_selection"
    HEDGE_STRATEGY = "hedge_strategy"
    REBALANCING = "rebalancing"


class DecisionUrgency(Enum):
    """决策紧急程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(Enum):
    """置信度级别"""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ActionType(Enum):
    """行动类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    REDUCE_POSITION = "reduce_position"
    INCREASE_POSITION = "increase_position"
    SET_STOP_LOSS = "set_stop_loss"
    TAKE_PROFIT = "take_profit"
    HEDGE = "hedge"
    REBALANCE = "rebalance"
    MONITOR = "monitor"


@dataclass
class DecisionContext:
    """决策上下文"""
    symbol: str
    current_price: float
    position_size: float
    market_conditions: Dict[str, Any]
    risk_metrics: Dict[str, float]
    technical_signals: List[Dict[str, Any]]
    fundamental_data: Dict[str, Any] = field(default_factory=dict)
    time_horizon: timedelta = timedelta(hours=24)


@dataclass
class DecisionRecommendation:
    """决策建议"""
    recommendation_id: str
    decision_type: DecisionType
    action_type: ActionType
    symbol: str
    timestamp: datetime
    confidence: float
    urgency: DecisionUrgency
    reasoning: List[str]
    supporting_evidence: Dict[str, Any]
    risk_assessment: str
    expected_outcome: str
    alternative_actions: List[ActionType] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "decision_type": self.decision_type.value,
            "action_type": self.action_type.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "urgency": self.urgency.value,
            "reasoning": self.reasoning,
            "supporting_evidence": self.supporting_evidence,
            "risk_assessment": self.risk_assessment,
            "expected_outcome": self.expected_outcome,
            "alternative_actions": [action.value for action in self.alternative_actions]
        }


@dataclass
class DecisionRule:
    """决策规则"""
    rule_id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    action: ActionType
    priority: int = 1
    enabled: bool = True


@dataclass
class DecisionOutcome:
    """决策结果"""
    recommendation_id: str
    executed_action: ActionType
    execution_timestamp: datetime
    execution_price: Optional[float] = None
    actual_outcome: Optional[str] = None
    success: Optional[bool] = None
    lessons_learned: List[str] = field(default_factory=list)


@dataclass
class PortfolioDecision:
    """组合决策"""
    portfolio_id: str
    total_value: float
    target_allocation: Dict[str, float]  # symbol -> allocation percentage
    rebalancing_suggestions: List[DecisionRecommendation]
    risk_budget: Dict[str, float]
    timestamp: datetime


@dataclass
class DecisionPerformance:
    """决策表现"""
    decision_type: DecisionType
    total_recommendations: int
    executed_recommendations: int
    successful_outcomes: int
    average_confidence: float
    success_rate: float
    performance_metrics: Dict[str, float] = field(default_factory=dict)


class DecisionSupportSystem:
    """智能决策支持系统"""
    
    def __init__(self):
        self.decision_recommendations: List[DecisionRecommendation] = []
        self.decision_rules: Dict[str, DecisionRule] = {}
        self.decision_outcomes: List[DecisionOutcome] = []
        self.portfolio_decisions: List[PortfolioDecision] = []
        self.performance_tracker: Dict[DecisionType, DecisionPerformance] = {}
        self.learning_feedback: List[Dict[str, Any]] = []
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 初始化默认决策规则
        self._initialize_default_rules()
        logger.info("智能决策支持系统初始化完成")
    
    def _initialize_default_rules(self):
        """初始化默认决策规则"""
        
        # 强势突破买入规则
        breakout_buy_rule = DecisionRule(
            rule_id="breakout_buy",
            name="突破买入规则",
            description="价格突破阻力位且成交量放大时买入",
            conditions={
                "price_above_resistance": True,
                "volume_ratio_min": 2.0,
                "rsi_max": 75,
                "trend_strength_min": 0.7
            },
            action=ActionType.BUY,
            priority=8
        )
        
        # 超买卖出规则
        overbought_sell_rule = DecisionRule(
            rule_id="overbought_sell",
            name="超买卖出规则",
            description="技术指标显示超买时卖出",
            conditions={
                "rsi_min": 80,
                "bb_position": "upper",  # 价格在布林带上轨附近
                "macd_divergence": True
            },
            action=ActionType.SELL,
            priority=7
        )
        
        # 止损规则
        stop_loss_rule = DecisionRule(
            rule_id="stop_loss",
            name="止损规则",
            description="当损失超过阈值时执行止损",
            conditions={
                "loss_percentage_max": -0.05,  # 5%止损
                "volume_confirmation": True
            },
            action=ActionType.SET_STOP_LOSS,
            priority=10  # 最高优先级
        )
        
        # 获利了结规则
        take_profit_rule = DecisionRule(
            rule_id="take_profit",
            name="获利了结规则",
            description="达到目标收益时获利了结",
            conditions={
                "profit_percentage_min": 0.15,  # 15%获利
                "trend_weakening": True,
                "volume_declining": True
            },
            action=ActionType.TAKE_PROFIT,
            priority=6
        )
        
        # 风险降低规则
        risk_reduction_rule = DecisionRule(
            rule_id="risk_reduction",
            name="风险降低规则",
            description="当整体风险过高时降低仓位",
            conditions={
                "portfolio_risk_max": 0.25,  # 组合风险超过25%
                "volatility_spike": True,
                "correlation_increase": True
            },
            action=ActionType.REDUCE_POSITION,
            priority=9
        )
        
        # 均值回归买入规则
        mean_reversion_buy_rule = DecisionRule(
            rule_id="mean_reversion_buy",
            name="均值回归买入规则",
            description="价格过度偏离均值时买入",
            conditions={
                "bb_position": "lower",  # 价格在布林带下轨
                "rsi_max": 30,
                "price_vs_ma_ratio_max": 0.95
            },
            action=ActionType.BUY,
            priority=5
        )
        
        rules = [
            breakout_buy_rule, overbought_sell_rule, stop_loss_rule,
            take_profit_rule, risk_reduction_rule, mean_reversion_buy_rule
        ]
        
        for rule in rules:
            self.decision_rules[rule.rule_id] = rule
        
        # 初始化性能跟踪器
        for decision_type in DecisionType:
            self.performance_tracker[decision_type] = DecisionPerformance(
                decision_type=decision_type,
                total_recommendations=0,
                executed_recommendations=0,
                successful_outcomes=0,
                average_confidence=0.0,
                success_rate=0.0
            )
    
    def analyze_and_recommend(self, context: DecisionContext) -> List[DecisionRecommendation]:
        """分析并生成决策建议"""
        try:
            recommendations = []
            
            # 应用所有启用的决策规则
            applicable_rules = self._find_applicable_rules(context)
            
            for rule in applicable_rules:
                recommendation = self._create_recommendation_from_rule(rule, context)
                if recommendation:
                    recommendations.append(recommendation)
            
            # 生成综合分析建议
            if not recommendations:
                comprehensive_recommendation = self._generate_comprehensive_recommendation(context)
                if comprehensive_recommendation:
                    recommendations.append(comprehensive_recommendation)
            
            # 对建议按优先级和置信度排序
            recommendations.sort(key=lambda r: (r.urgency.value, -r.confidence), reverse=True)
            
            # 存储建议
            self.decision_recommendations.extend(recommendations)
            
            # 保留最近1000个建议
            if len(self.decision_recommendations) > 1000:
                self.decision_recommendations = self.decision_recommendations[-1000:]
            
            logger.info(f"生成决策建议: {context.symbol} - {len(recommendations)} 个建议")
            return recommendations
            
        except Exception as e:
            logger.error(f"分析和建议生成失败: {e}")
            return []
    
    def _find_applicable_rules(self, context: DecisionContext) -> List[DecisionRule]:
        """找到适用的决策规则"""
        applicable_rules = []
        
        for rule in self.decision_rules.values():
            if not rule.enabled:
                continue
            
            if self._evaluate_rule_conditions(rule, context):
                applicable_rules.append(rule)
        
        # 按优先级排序
        applicable_rules.sort(key=lambda r: r.priority, reverse=True)
        return applicable_rules
    
    def _evaluate_rule_conditions(self, rule: DecisionRule, context: DecisionContext) -> bool:
        """评估规则条件是否满足"""
        try:
            conditions = rule.conditions
            
            for condition, expected_value in conditions.items():
                actual_value = self._get_context_value(condition, context)
                
                if isinstance(expected_value, bool):
                    if actual_value != expected_value:
                        return False
                elif isinstance(expected_value, (int, float)):
                    if condition.endswith("_min") and actual_value < expected_value:
                        return False
                    elif condition.endswith("_max") and actual_value > expected_value:
                        return False
                elif isinstance(expected_value, str):
                    if actual_value != expected_value:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"评估规则条件失败: {e}")
            return False
    
    def _get_context_value(self, condition: str, context: DecisionContext) -> Any:
        """从上下文中获取条件值"""
        
        if condition == "price_above_resistance":
            resistance = context.market_conditions.get("resistance_level", context.current_price * 1.05)
            return context.current_price > resistance
        
        elif condition == "volume_ratio_min" or condition == "volume_ratio":
            return context.market_conditions.get("volume_ratio", 1.0)
        
        elif condition == "rsi_min" or condition == "rsi_max" or condition == "rsi":
            return context.market_conditions.get("rsi", 50)
        
        elif condition == "trend_strength_min":
            return context.market_conditions.get("trend_strength", 0.5)
        
        elif condition == "bb_position":
            # 布林带位置："upper", "middle", "lower"
            bb_upper = context.market_conditions.get("bb_upper", context.current_price * 1.02)
            bb_lower = context.market_conditions.get("bb_lower", context.current_price * 0.98)
            
            if context.current_price >= bb_upper * 0.98:
                return "upper"
            elif context.current_price <= bb_lower * 1.02:
                return "lower"
            else:
                return "middle"
        
        elif condition == "macd_divergence":
            return context.market_conditions.get("macd_divergence", False)
        
        elif condition == "loss_percentage_max":
            entry_price = context.market_conditions.get("entry_price", context.current_price)
            return (context.current_price - entry_price) / entry_price if entry_price > 0 else 0
        
        elif condition == "profit_percentage_min":
            entry_price = context.market_conditions.get("entry_price", context.current_price)
            return (context.current_price - entry_price) / entry_price if entry_price > 0 else 0
        
        elif condition == "portfolio_risk_max":
            return context.risk_metrics.get("portfolio_risk", 0.1)
        
        elif condition == "volatility_spike":
            current_vol = context.market_conditions.get("volatility", 0.02)
            historical_vol = context.market_conditions.get("historical_volatility", 0.02)
            return current_vol > historical_vol * 1.5
        
        elif condition == "price_vs_ma_ratio_max":
            ma_20 = context.market_conditions.get("ma_20", context.current_price)
            return context.current_price / ma_20 if ma_20 > 0 else 1.0
        
        else:
            return context.market_conditions.get(condition, False)
    
    def _create_recommendation_from_rule(self, rule: DecisionRule, context: DecisionContext) -> Optional[DecisionRecommendation]:
        """根据规则创建建议"""
        try:
            # 确定紧急程度
            if rule.priority >= 9:
                urgency = DecisionUrgency.CRITICAL
            elif rule.priority >= 7:
                urgency = DecisionUrgency.HIGH
            elif rule.priority >= 5:
                urgency = DecisionUrgency.MEDIUM
            else:
                urgency = DecisionUrgency.LOW
            
            # 计算置信度
            confidence = self._calculate_rule_confidence(rule, context)
            
            # 生成推理说明
            reasoning = self._generate_rule_reasoning(rule, context)
            
            # 生成支持证据
            supporting_evidence = self._collect_supporting_evidence(rule, context)
            
            # 风险评估
            risk_assessment = self._assess_action_risk(rule.action, context)
            
            # 预期结果
            expected_outcome = self._predict_action_outcome(rule.action, context)
            
            recommendation = DecisionRecommendation(
                recommendation_id=f"rec_{rule.rule_id}_{context.symbol}_{int(datetime.now().timestamp())}",
                decision_type=DecisionType.TRADING_DECISION,
                action_type=rule.action,
                symbol=context.symbol,
                timestamp=datetime.now(),
                confidence=confidence,
                urgency=urgency,
                reasoning=reasoning,
                supporting_evidence=supporting_evidence,
                risk_assessment=risk_assessment,
                expected_outcome=expected_outcome
            )
            
            return recommendation
            
        except Exception as e:
            logger.error(f"创建规则建议失败: {e}")
            return None
    
    def _calculate_rule_confidence(self, rule: DecisionRule, context: DecisionContext) -> float:
        """计算规则置信度"""
        base_confidence = 0.7  # 基础置信度
        
        # 根据满足条件的程度调整置信度
        condition_strength = 0.0
        total_conditions = len(rule.conditions)
        
        for condition, expected_value in rule.conditions.items():
            actual_value = self._get_context_value(condition, context)
            
            # 根据条件满足程度给分
            if isinstance(expected_value, bool) and actual_value == expected_value:
                condition_strength += 1.0
            elif isinstance(expected_value, (int, float)):
                # 数值条件的满足程度
                if condition.endswith("_min"):
                    ratio = min(1.0, actual_value / max(expected_value, 0.01))
                    condition_strength += min(1.0, ratio)
                elif condition.endswith("_max"):
                    ratio = min(1.0, expected_value / max(actual_value, 0.01))
                    condition_strength += min(1.0, ratio)
                else:
                    condition_strength += 0.8  # 默认满足度
            else:
                condition_strength += 0.8
        
        avg_condition_strength = condition_strength / max(total_conditions, 1)
        confidence = base_confidence * avg_condition_strength
        
        # 根据规则优先级调整
        priority_bonus = min(0.2, rule.priority * 0.02)
        confidence += priority_bonus
        
        return round(min(confidence, 0.95), 3)
    
    def _generate_rule_reasoning(self, rule: DecisionRule, context: DecisionContext) -> List[str]:
        """生成规则推理"""
        reasoning = [f"应用规则: {rule.name}"]
        
        for condition, expected_value in rule.conditions.items():
            actual_value = self._get_context_value(condition, context)
            
            if condition == "price_above_resistance":
                reasoning.append(f"价格突破阻力位 (当前: {context.current_price})")
            elif condition == "volume_ratio_min":
                reasoning.append(f"成交量放大 (当前倍数: {actual_value:.1f})")
            elif condition == "rsi" and isinstance(expected_value, (int, float)):
                if condition.endswith("_min"):
                    reasoning.append(f"RSI超买 (当前: {actual_value})")
                else:
                    reasoning.append(f"RSI超卖 (当前: {actual_value})")
            elif condition == "bb_position":
                reasoning.append(f"价格位于布林带{actual_value}轨")
            elif "loss_percentage" in condition:
                reasoning.append(f"当前亏损: {actual_value:.1%}")
            elif "profit_percentage" in condition:
                reasoning.append(f"当前盈利: {actual_value:.1%}")
        
        return reasoning
    
    def _collect_supporting_evidence(self, rule: DecisionRule, context: DecisionContext) -> Dict[str, Any]:
        """收集支持证据"""
        evidence = {
            "rule_priority": rule.priority,
            "market_conditions": context.market_conditions,
            "technical_signals": context.technical_signals,
            "risk_metrics": context.risk_metrics
        }
        
        return evidence
    
    def _assess_action_risk(self, action: ActionType, context: DecisionContext) -> str:
        """评估行动风险"""
        
        volatility = context.market_conditions.get("volatility", 0.02)
        position_size = context.position_size
        
        if action in [ActionType.BUY, ActionType.INCREASE_POSITION]:
            if volatility > 0.05:
                risk = "高风险：市场波动性较大"
            elif position_size > 0.2:
                risk = "中等风险：仓位已较重"
            else:
                risk = "低风险：市场条件相对稳定"
        
        elif action in [ActionType.SELL, ActionType.REDUCE_POSITION]:
            if position_size < 0.05:
                risk = "低风险：仓位较轻"
            else:
                risk = "低风险：降低风险暴露"
        
        elif action in [ActionType.SET_STOP_LOSS, ActionType.TAKE_PROFIT]:
            risk = "低风险：风险管理操作"
        
        else:
            risk = "中等风险：需要密切监控"
        
        return risk
    
    def _predict_action_outcome(self, action: ActionType, context: DecisionContext) -> str:
        """预测行动结果"""
        
        trend_strength = context.market_conditions.get("trend_strength", 0.5)
        
        if action == ActionType.BUY:
            if trend_strength > 0.7:
                return "预期正面：强势上涨趋势，买入时机良好"
            else:
                return "预期中性：市场方向不明确，建议小仓位试探"
        
        elif action == ActionType.SELL:
            if trend_strength < 0.3:
                return "预期正面：下跌趋势明确，及时离场"
            else:
                return "预期中性：可能错过进一步上涨"
        
        elif action == ActionType.SET_STOP_LOSS:
            return "预期正面：有效控制下行风险"
        
        elif action == ActionType.TAKE_PROFIT:
            return "预期正面：锁定已有收益"
        
        else:
            return "预期中性：需要根据市场反应调整"
    
    def _generate_comprehensive_recommendation(self, context: DecisionContext) -> Optional[DecisionRecommendation]:
        """生成综合分析建议"""
        try:
            # 综合分析各种因素
            technical_score = self._calculate_technical_score(context)
            risk_score = self._calculate_risk_score(context)
            momentum_score = self._calculate_momentum_score(context)
            
            overall_score = (technical_score + risk_score + momentum_score) / 3
            
            # 根据综合得分确定行动
            if overall_score > 0.7:
                action = ActionType.BUY
                urgency = DecisionUrgency.MEDIUM
            elif overall_score < 0.3:
                action = ActionType.SELL
                urgency = DecisionUrgency.MEDIUM
            else:
                action = ActionType.HOLD
                urgency = DecisionUrgency.LOW
            
            reasoning = [
                f"综合技术分析得分: {technical_score:.2f}",
                f"风险评估得分: {risk_score:.2f}",
                f"动量分析得分: {momentum_score:.2f}",
                f"综合得分: {overall_score:.2f}"
            ]
            
            recommendation = DecisionRecommendation(
                recommendation_id=f"comp_{context.symbol}_{int(datetime.now().timestamp())}",
                decision_type=DecisionType.TRADING_DECISION,
                action_type=action,
                symbol=context.symbol,
                timestamp=datetime.now(),
                confidence=round(abs(overall_score - 0.5) * 2, 3),
                urgency=urgency,
                reasoning=reasoning,
                supporting_evidence={
                    "technical_score": technical_score,
                    "risk_score": risk_score,
                    "momentum_score": momentum_score,
                    "overall_score": overall_score
                },
                risk_assessment=f"基于综合分析的{action.value}建议",
                expected_outcome=f"预期综合得分反映的{action.value}结果"
            )
            
            return recommendation
            
        except Exception as e:
            logger.error(f"生成综合建议失败: {e}")
            return None
    
    def _calculate_technical_score(self, context: DecisionContext) -> float:
        """计算技术分析得分"""
        rsi = context.market_conditions.get("rsi", 50)
        ma_signal = context.market_conditions.get("ma_signal", 0)  # 1=bullish, -1=bearish, 0=neutral
        volume_ratio = context.market_conditions.get("volume_ratio", 1.0)
        
        # RSI得分 (0-1)
        if rsi > 70:
            rsi_score = 0.2  # 超买
        elif rsi < 30:
            rsi_score = 0.8  # 超卖，买入机会
        else:
            rsi_score = 0.5 + (50 - rsi) / 100  # 中性偏向
        
        # 移动平均得分
        ma_score = 0.5 + ma_signal * 0.3
        
        # 成交量得分
        volume_score = min(1.0, volume_ratio / 2.0)  # 成交量越大越好
        
        return statistics.mean([rsi_score, ma_score, volume_score])
    
    def _calculate_risk_score(self, context: DecisionContext) -> float:
        """计算风险得分"""
        volatility = context.market_conditions.get("volatility", 0.02)
        position_size = context.position_size
        
        # 波动率得分 (低波动率高分)
        vol_score = max(0, 1 - volatility * 20)
        
        # 仓位得分 (适中仓位高分)
        if position_size < 0.1:
            pos_score = 0.8  # 低仓位，可以加仓
        elif position_size < 0.3:
            pos_score = 1.0  # 适中仓位
        else:
            pos_score = 0.4  # 高仓位，风险较大
        
        return statistics.mean([vol_score, pos_score])
    
    def _calculate_momentum_score(self, context: DecisionContext) -> float:
        """计算动量得分"""
        price_change_24h = context.market_conditions.get("price_change_24h", 0.0)
        trend_strength = context.market_conditions.get("trend_strength", 0.5)
        
        # 价格变动得分
        momentum_score = 0.5 + price_change_24h * 5  # 假设日变动±20%为满分
        momentum_score = max(0, min(1, momentum_score))
        
        return statistics.mean([momentum_score, trend_strength])
    
    def execute_recommendation(self, recommendation_id: str, executed_action: ActionType, 
                             execution_price: float = None) -> bool:
        """执行建议"""
        try:
            recommendation = next((r for r in self.decision_recommendations if r.recommendation_id == recommendation_id), None)
            if not recommendation:
                logger.warning(f"建议不存在: {recommendation_id}")
                return False
            
            outcome = DecisionOutcome(
                recommendation_id=recommendation_id,
                executed_action=executed_action,
                execution_timestamp=datetime.now(),
                execution_price=execution_price
            )
            
            self.decision_outcomes.append(outcome)
            
            # 更新性能跟踪
            self._update_decision_performance(recommendation, True)
            
            logger.info(f"执行决策建议: {recommendation_id} - {executed_action.value}")
            return True
            
        except Exception as e:
            logger.error(f"执行建议失败: {e}")
            return False
    
    def _update_decision_performance(self, recommendation: DecisionRecommendation, executed: bool):
        """更新决策性能"""
        try:
            decision_type = recommendation.decision_type
            performance = self.performance_tracker[decision_type]
            
            performance.total_recommendations += 1
            
            if executed:
                performance.executed_recommendations += 1
            
            # 更新平均置信度
            total_confidence = performance.average_confidence * (performance.total_recommendations - 1) + recommendation.confidence
            performance.average_confidence = total_confidence / performance.total_recommendations
            
            # 更新执行率
            if performance.total_recommendations > 0:
                execution_rate = performance.executed_recommendations / performance.total_recommendations
                performance.performance_metrics["execution_rate"] = execution_rate
            
        except Exception as e:
            logger.error(f"更新决策性能失败: {e}")
    
    def generate_portfolio_decision(self, portfolio_data: Dict[str, Any]) -> Optional[PortfolioDecision]:
        """生成组合决策"""
        try:
            portfolio_id = portfolio_data.get("portfolio_id", "default")
            total_value = portfolio_data.get("total_value", 100000)
            current_allocation = portfolio_data.get("current_allocation", {})
            target_allocation = portfolio_data.get("target_allocation", {})
            
            rebalancing_suggestions = []
            
            # 检查每个资产的配置偏差
            for symbol, target_pct in target_allocation.items():
                current_pct = current_allocation.get(symbol, 0.0)
                deviation = abs(current_pct - target_pct)
                
                if deviation > 0.05:  # 偏差超过5%需要再平衡
                    if current_pct < target_pct:
                        action = ActionType.INCREASE_POSITION
                        urgency = DecisionUrgency.MEDIUM if deviation > 0.1 else DecisionUrgency.LOW
                    else:
                        action = ActionType.REDUCE_POSITION
                        urgency = DecisionUrgency.MEDIUM if deviation > 0.1 else DecisionUrgency.LOW
                    
                    suggestion = DecisionRecommendation(
                        recommendation_id=f"rebal_{portfolio_id}_{symbol}_{int(datetime.now().timestamp())}",
                        decision_type=DecisionType.REBALANCING,
                        action_type=action,
                        symbol=symbol,
                        timestamp=datetime.now(),
                        confidence=0.8,
                        urgency=urgency,
                        reasoning=[f"配置偏差: {deviation:.1%}", f"当前: {current_pct:.1%}, 目标: {target_pct:.1%}"],
                        supporting_evidence={"deviation": deviation, "current": current_pct, "target": target_pct},
                        risk_assessment="低风险：再平衡操作",
                        expected_outcome="恢复目标配置，优化风险收益"
                    )
                    
                    rebalancing_suggestions.append(suggestion)
            
            # 计算风险预算
            risk_budget = {}
            for symbol in target_allocation.keys():
                risk_budget[symbol] = target_allocation[symbol] * 0.02  # 假设每个资产2%的风险预算
            
            portfolio_decision = PortfolioDecision(
                portfolio_id=portfolio_id,
                total_value=total_value,
                target_allocation=target_allocation,
                rebalancing_suggestions=rebalancing_suggestions,
                risk_budget=risk_budget,
                timestamp=datetime.now()
            )
            
            self.portfolio_decisions.append(portfolio_decision)
            
            # 保留最近100个组合决策
            if len(self.portfolio_decisions) > 100:
                self.portfolio_decisions = self.portfolio_decisions[-100:]
            
            logger.info(f"生成组合决策: {portfolio_id} - {len(rebalancing_suggestions)} 个建议")
            return portfolio_decision
            
        except Exception as e:
            logger.error(f"生成组合决策失败: {e}")
            return None
    
    def get_decision_stats(self) -> Dict[str, Any]:
        """获取决策统计信息"""
        try:
            # 决策类型分布
            decision_type_dist = {}
            for decision_type in DecisionType:
                decision_type_dist[decision_type.value] = len([r for r in self.decision_recommendations if r.decision_type == decision_type])
            
            # 行动类型分布
            action_type_dist = {}
            for action_type in ActionType:
                action_type_dist[action_type.value] = len([r for r in self.decision_recommendations if r.action_type == action_type])
            
            # 紧急程度分布
            urgency_dist = {}
            for urgency in DecisionUrgency:
                urgency_dist[urgency.value] = len([r for r in self.decision_recommendations if r.urgency == urgency])
            
            # 平均置信度
            avg_confidence = statistics.mean([r.confidence for r in self.decision_recommendations]) if self.decision_recommendations else 0
            
            # 执行率
            execution_rate = len(self.decision_outcomes) / len(self.decision_recommendations) if self.decision_recommendations else 0
            
            stats = {
                "total_recommendations": len(self.decision_recommendations),
                "total_decision_rules": len(self.decision_rules),
                "executed_decisions": len(self.decision_outcomes),
                "portfolio_decisions": len(self.portfolio_decisions),
                "execution_rate": round(execution_rate, 3),
                "average_confidence": round(avg_confidence, 3),
                "decision_type_distribution": decision_type_dist,
                "action_type_distribution": action_type_dist,
                "urgency_distribution": urgency_dist,
                "recent_recommendations": len([r for r in self.decision_recommendations if (datetime.now() - r.timestamp).total_seconds() < 24 * 3600]),
                "performance_by_type": {
                    decision_type.value: {
                        "total": perf.total_recommendations,
                        "executed": perf.executed_recommendations,
                        "avg_confidence": round(perf.average_confidence, 3)
                    }
                    for decision_type, perf in self.performance_tracker.items()
                }
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取决策统计失败: {e}")
            return {}


# 生成模拟决策的辅助函数
def generate_sample_decisions(decision_system: DecisionSupportSystem, count: int = 25):
    """生成示例决策"""
    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    
    for i in range(count):
        symbol = random.choice(symbols)
        
        # 生成模拟决策上下文
        context = DecisionContext(
            symbol=symbol,
            current_price=random.uniform(100, 50000),
            position_size=random.uniform(0.05, 0.3),
            market_conditions={
                "rsi": random.uniform(20, 80),
                "volume_ratio": random.uniform(0.5, 3.0),
                "volatility": random.uniform(0.01, 0.1),
                "trend_strength": random.uniform(0.2, 0.9),
                "price_change_24h": random.uniform(-0.15, 0.15),
                "ma_signal": random.choice([-1, 0, 1]),
                "resistance_level": random.uniform(105, 52000),
                "support_level": random.uniform(95, 48000),
                "bb_upper": random.uniform(105, 52000),
                "bb_lower": random.uniform(95, 48000),
                "entry_price": random.uniform(90, 45000),
                "historical_volatility": random.uniform(0.015, 0.06)
            },
            risk_metrics={
                "portfolio_risk": random.uniform(0.1, 0.4),
                "var_95": random.uniform(0.02, 0.1),
                "max_drawdown": random.uniform(0.05, 0.2)
            },
            technical_signals=[
                {"signal": "bullish", "confidence": random.uniform(0.5, 0.9)},
                {"signal": "volume_spike", "confidence": random.uniform(0.6, 0.95)}
            ]
        )
        
        # 生成决策建议
        recommendations = decision_system.analyze_and_recommend(context)
        
        # 模拟一些建议的执行
        for recommendation in recommendations[:1]:  # 只执行第一个建议
            if random.random() < 0.6:  # 60%的概率执行
                execution_price = context.current_price * random.uniform(0.99, 1.01)
                decision_system.execute_recommendation(
                    recommendation.recommendation_id, 
                    recommendation.action_type, 
                    execution_price
                )
    
    # 生成一些组合决策
    for _ in range(3):
        portfolio_data = {
            "portfolio_id": f"portfolio_{random.randint(1, 5)}",
            "total_value": random.uniform(50000, 500000),
            "current_allocation": {
                "BTC/USDT": random.uniform(0.2, 0.5),
                "ETH/USDT": random.uniform(0.15, 0.4),
                "BNB/USDT": random.uniform(0.05, 0.2),
                "SOL/USDT": random.uniform(0.05, 0.15)
            },
            "target_allocation": {
                "BTC/USDT": 0.4,
                "ETH/USDT": 0.3,
                "BNB/USDT": 0.2,
                "SOL/USDT": 0.1
            }
        }
        
        decision_system.generate_portfolio_decision(portfolio_data)