"""
风险评估引擎 - Week 5 Day 9
提供全面的风险分析、风险度量和风险管理建议
"""

import asyncio
import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import json
import random

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RiskType(Enum):
    """风险类型"""
    MARKET_RISK = "market_risk"
    LIQUIDITY_RISK = "liquidity_risk"
    CREDIT_RISK = "credit_risk"
    OPERATIONAL_RISK = "operational_risk"
    CONCENTRATION_RISK = "concentration_risk"
    VOLATILITY_RISK = "volatility_risk"
    CORRELATION_RISK = "correlation_risk"
    REGULATORY_RISK = "regulatory_risk"


class RiskLevel(Enum):
    """风险等级"""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    EXTREME = "extreme"


class RiskMetric(Enum):
    """风险指标"""
    VAR = "value_at_risk"          # 风险价值
    CVAR = "conditional_var"       # 条件风险价值
    MAX_DRAWDOWN = "max_drawdown"  # 最大回撤
    SHARPE_RATIO = "sharpe_ratio"  # 夏普比率
    SORTINO_RATIO = "sortino_ratio" # 索提诺比率
    BETA = "beta"                  # Beta系数
    VOLATILITY = "volatility"      # 波动率
    CORRELATION = "correlation"    # 相关性


@dataclass
class RiskAssessment:
    """风险评估"""
    assessment_id: str
    symbol: str
    risk_type: RiskType
    risk_level: RiskLevel
    timestamp: datetime
    risk_score: float  # 0-100
    description: str
    key_factors: List[str]
    mitigation_strategies: List[str]
    confidence: float = 0.0
    duration: Optional[timedelta] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "symbol": self.symbol,
            "risk_type": self.risk_type.value,
            "risk_level": self.risk_level.value,
            "timestamp": self.timestamp.isoformat(),
            "risk_score": self.risk_score,
            "description": self.description,
            "key_factors": self.key_factors,
            "mitigation_strategies": self.mitigation_strategies,
            "confidence": self.confidence
        }


@dataclass
class RiskMetricValue:
    """风险指标值"""
    metric_id: str
    symbol: str
    metric_type: RiskMetric
    value: float
    timestamp: datetime
    parameters: Dict[str, Any] = field(default_factory=dict)
    benchmark_value: Optional[float] = None
    interpretation: str = ""


@dataclass
class PortfolioRisk:
    """组合风险"""
    portfolio_id: str
    total_var: float
    total_risk_score: float
    diversification_ratio: float
    concentration_risk: float
    timestamp: datetime
    individual_risks: List[RiskAssessment] = field(default_factory=list)
    correlation_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class RiskAlert:
    """风险告警"""
    alert_id: str
    symbol: str
    risk_type: RiskType
    severity: RiskLevel
    message: str
    timestamp: datetime
    threshold_breached: float
    current_value: float
    recommended_actions: List[str] = field(default_factory=list)


@dataclass
class StressTestScenario:
    """压力测试场景"""
    scenario_id: str
    name: str
    description: str
    parameters: Dict[str, float]  # 如：price_shock: -0.2 (20%价格下跌)
    probability: float = 0.0


@dataclass
class StressTestResult:
    """压力测试结果"""
    test_id: str
    scenario: StressTestScenario
    symbol: str
    base_value: float
    stressed_value: float
    loss_amount: float
    loss_percentage: float
    timestamp: datetime


class RiskAssessmentEngine:
    """风险评估引擎"""
    
    def __init__(self):
        self.risk_assessments: List[RiskAssessment] = []
        self.risk_metrics: Dict[str, List[RiskMetricValue]] = {}
        self.portfolio_risks: List[PortfolioRisk] = []
        self.risk_alerts: List[RiskAlert] = []
        self.stress_scenarios: Dict[str, StressTestScenario] = {}
        self.stress_test_results: List[StressTestResult] = []
        self.executor = ThreadPoolExecutor(max_workers=5)
        
        # 初始化默认配置
        self._initialize_default_configs()
        logger.info("风险评估引擎初始化完成")
    
    def _initialize_default_configs(self):
        """初始化默认配置"""
        
        # 预设压力测试场景
        scenarios = [
            StressTestScenario(
                scenario_id="market_crash",
                name="市场崩盘",
                description="模拟类似2008年金融危机的市场崩盘",
                parameters={"price_shock": -0.30, "volatility_spike": 3.0, "liquidity_dry_up": 0.5},
                probability=0.05
            ),
            StressTestScenario(
                scenario_id="flash_crash",
                name="闪电崩盘",
                description="短期内价格急剧下跌",
                parameters={"price_shock": -0.15, "duration_minutes": 10, "recovery_rate": 0.3},
                probability=0.10
            ),
            StressTestScenario(
                scenario_id="regulatory_ban",
                name="监管禁令",
                description="主要市场禁止加密货币交易",
                parameters={"price_shock": -0.50, "volume_shock": -0.80, "recovery_time_days": 90},
                probability=0.02
            ),
            StressTestScenario(
                scenario_id="exchange_hack",
                name="交易所被黑",
                description="主要交易所遭受重大安全漏洞",
                parameters={"price_shock": -0.20, "confidence_loss": 0.6, "fund_loss": 0.1},
                probability=0.03
            ),
            StressTestScenario(
                scenario_id="whale_dump",
                name="巨鲸抛售",
                description="大户集中抛售造成市场恐慌",
                parameters={"price_shock": -0.25, "volume_spike": 5.0, "panic_factor": 0.8},
                probability=0.08
            )
        ]
        
        for scenario in scenarios:
            self.stress_scenarios[scenario.scenario_id] = scenario
    
    def assess_risk(self, symbol: str, market_data: Dict[str, Any], risk_type: RiskType = None) -> Optional[RiskAssessment]:
        """评估风险"""
        try:
            if risk_type:
                return self._assess_specific_risk(symbol, market_data, risk_type)
            else:
                # 综合风险评估
                return self._assess_comprehensive_risk(symbol, market_data)
                
        except Exception as e:
            logger.error(f"风险评估失败: {e}")
            return None
    
    def _assess_comprehensive_risk(self, symbol: str, market_data: Dict[str, Any]) -> Optional[RiskAssessment]:
        """综合风险评估"""
        
        current_price = market_data.get("current_price", 100.0)
        volatility = market_data.get("volatility", 0.02)
        volume = market_data.get("volume", 1000000)
        price_change_24h = market_data.get("price_change_24h", 0.0)
        
        # 计算综合风险得分
        risk_factors = []
        risk_score = 0
        
        # 波动率风险 (0-30分)
        volatility_risk = min(volatility * 1000, 30)
        risk_score += volatility_risk
        if volatility > 0.05:
            risk_factors.append(f"高波动率: {volatility:.1%}")
        
        # 价格变动风险 (0-25分)
        price_change_risk = min(abs(price_change_24h) * 250, 25)
        risk_score += price_change_risk
        if abs(price_change_24h) > 0.1:
            risk_factors.append(f"价格大幅波动: {price_change_24h:.1%}")
        
        # 流动性风险 (0-25分)
        # 假设低交易量意味着高流动性风险
        avg_volume = market_data.get("avg_volume_30d", volume)
        liquidity_ratio = volume / max(avg_volume, 1)
        liquidity_risk = max(0, 25 * (1 - liquidity_ratio))
        risk_score += liquidity_risk
        if liquidity_ratio < 0.5:
            risk_factors.append("流动性不足")
        
        # 技术指标风险 (0-20分)
        rsi = market_data.get("rsi", 50)
        if rsi > 80 or rsi < 20:
            technical_risk = 20
            risk_factors.append(f"技术指标极端: RSI {rsi}")
        elif rsi > 70 or rsi < 30:
            technical_risk = 10
            risk_factors.append(f"技术指标偏离: RSI {rsi}")
        else:
            technical_risk = 0
        risk_score += technical_risk
        
        # 确定风险等级
        if risk_score >= 80:
            risk_level = RiskLevel.EXTREME
        elif risk_score >= 65:
            risk_level = RiskLevel.VERY_HIGH
        elif risk_score >= 50:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 35:
            risk_level = RiskLevel.MEDIUM
        elif risk_score >= 20:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.VERY_LOW
        
        # 生成缓解策略
        mitigation_strategies = self._generate_mitigation_strategies(risk_level, risk_factors)
        
        # 计算置信度
        data_quality = len([k for k in market_data.keys() if market_data[k] is not None]) / 10
        confidence = min(data_quality, 1.0)
        
        assessment = RiskAssessment(
            assessment_id=f"risk_{symbol}_{int(datetime.now().timestamp())}",
            symbol=symbol,
            risk_type=RiskType.MARKET_RISK,
            risk_level=risk_level,
            timestamp=datetime.now(),
            risk_score=round(risk_score, 1),
            description=f"{symbol} 综合市场风险评估",
            key_factors=risk_factors,
            mitigation_strategies=mitigation_strategies,
            confidence=round(confidence, 2),
            duration=timedelta(hours=24)
        )
        
        self.risk_assessments.append(assessment)
        
        # 保留最近500个评估
        if len(self.risk_assessments) > 500:
            self.risk_assessments = self.risk_assessments[-500:]
        
        # 检查是否需要发出告警
        if risk_level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH, RiskLevel.EXTREME]:
            self._generate_risk_alert(assessment)
        
        logger.info(f"风险评估完成: {symbol} - 风险等级: {risk_level.value}, 得分: {risk_score}")
        return assessment
    
    def _assess_specific_risk(self, symbol: str, market_data: Dict[str, Any], risk_type: RiskType) -> Optional[RiskAssessment]:
        """评估特定类型风险"""
        
        if risk_type == RiskType.VOLATILITY_RISK:
            return self._assess_volatility_risk(symbol, market_data)
        elif risk_type == RiskType.LIQUIDITY_RISK:
            return self._assess_liquidity_risk(symbol, market_data)
        elif risk_type == RiskType.CONCENTRATION_RISK:
            return self._assess_concentration_risk(symbol, market_data)
        # 可以添加更多特定风险类型的评估
        
        return None
    
    def _assess_volatility_risk(self, symbol: str, market_data: Dict[str, Any]) -> Optional[RiskAssessment]:
        """评估波动率风险"""
        
        volatility = market_data.get("volatility", 0.02)
        historical_volatility = market_data.get("volatility_30d", 0.02)
        
        # 计算波动率风险得分
        risk_score = min(volatility * 2000, 100)  # 归一化到0-100
        
        # 与历史波动率比较
        volatility_ratio = volatility / max(historical_volatility, 0.001)
        
        risk_factors = [f"当前波动率: {volatility:.1%}"]
        
        if volatility_ratio > 2.0:
            risk_factors.append("波动率大幅上升")
            risk_score *= 1.2
        elif volatility_ratio > 1.5:
            risk_factors.append("波动率显著上升")
            risk_score *= 1.1
        
        # 确定风险等级
        if risk_score >= 80:
            risk_level = RiskLevel.VERY_HIGH
        elif risk_score >= 60:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 40:
            risk_level = RiskLevel.MEDIUM
        elif risk_score >= 20:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.VERY_LOW
        
        mitigation_strategies = [
            "降低仓位规模",
            "使用止损单",
            "考虑期权对冲",
            "分散投资时间"
        ]
        
        assessment = RiskAssessment(
            assessment_id=f"vol_risk_{symbol}_{int(datetime.now().timestamp())}",
            symbol=symbol,
            risk_type=RiskType.VOLATILITY_RISK,
            risk_level=risk_level,
            timestamp=datetime.now(),
            risk_score=round(min(risk_score, 100), 1),
            description=f"{symbol} 波动率风险评估",
            key_factors=risk_factors,
            mitigation_strategies=mitigation_strategies,
            confidence=0.85
        )
        
        return assessment
    
    def _assess_liquidity_risk(self, symbol: str, market_data: Dict[str, Any]) -> Optional[RiskAssessment]:
        """评估流动性风险"""
        
        volume = market_data.get("volume", 1000000)
        avg_volume = market_data.get("avg_volume_30d", volume)
        bid_ask_spread = market_data.get("bid_ask_spread", 0.001)
        
        # 计算流动性风险得分
        volume_ratio = volume / max(avg_volume, 1)
        spread_score = min(bid_ask_spread * 10000, 50)  # 点差贡献
        volume_score = max(0, 50 * (1 - volume_ratio))  # 交易量贡献
        
        risk_score = spread_score + volume_score
        
        risk_factors = []
        if volume_ratio < 0.5:
            risk_factors.append("交易量低于平均水平")
        if bid_ask_spread > 0.005:
            risk_factors.append(f"买卖价差较大: {bid_ask_spread:.1%}")
        
        # 确定风险等级
        if risk_score >= 70:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 50:
            risk_level = RiskLevel.MEDIUM
        elif risk_score >= 30:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.VERY_LOW
        
        mitigation_strategies = [
            "分批交易",
            "避免大额单笔交易",
            "选择高流动性时段",
            "使用限价单"
        ]
        
        assessment = RiskAssessment(
            assessment_id=f"liq_risk_{symbol}_{int(datetime.now().timestamp())}",
            symbol=symbol,
            risk_type=RiskType.LIQUIDITY_RISK,
            risk_level=risk_level,
            timestamp=datetime.now(),
            risk_score=round(risk_score, 1),
            description=f"{symbol} 流动性风险评估",
            key_factors=risk_factors,
            mitigation_strategies=mitigation_strategies,
            confidence=0.75
        )
        
        return assessment
    
    def _assess_concentration_risk(self, symbol: str, market_data: Dict[str, Any]) -> Optional[RiskAssessment]:
        """评估集中度风险"""
        
        position_size = market_data.get("position_size", 0.1)  # 假设为组合的10%
        correlation_with_portfolio = market_data.get("portfolio_correlation", 0.3)
        
        # 计算集中度风险得分
        size_risk = min(position_size * 200, 60)  # 仓位大小贡献
        correlation_risk = correlation_with_portfolio * 40  # 相关性贡献
        
        risk_score = size_risk + correlation_risk
        
        risk_factors = []
        if position_size > 0.2:
            risk_factors.append(f"仓位过度集中: {position_size:.1%}")
        if correlation_with_portfolio > 0.7:
            risk_factors.append("与组合高度相关")
        
        # 确定风险等级
        if risk_score >= 80:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 60:
            risk_level = RiskLevel.MEDIUM
        elif risk_score >= 40:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.VERY_LOW
        
        mitigation_strategies = [
            "降低单一资产仓位",
            "增加不相关资产",
            "考虑地域分散",
            "定期再平衡"
        ]
        
        assessment = RiskAssessment(
            assessment_id=f"conc_risk_{symbol}_{int(datetime.now().timestamp())}",
            symbol=symbol,
            risk_type=RiskType.CONCENTRATION_RISK,
            risk_level=risk_level,
            timestamp=datetime.now(),
            risk_score=round(risk_score, 1),
            description=f"{symbol} 集中度风险评估",
            key_factors=risk_factors,
            mitigation_strategies=mitigation_strategies,
            confidence=0.70
        )
        
        return assessment
    
    def calculate_risk_metrics(self, symbol: str, price_history: List[float], returns: List[float] = None) -> List[RiskMetricValue]:
        """计算风险指标"""
        try:
            if len(price_history) < 10:
                return []
            
            if returns is None:
                returns = [(price_history[i] - price_history[i-1]) / price_history[i-1] 
                          for i in range(1, len(price_history))]
            
            metrics = []
            timestamp = datetime.now()
            
            # 计算VaR (95%置信度)
            var_95 = self._calculate_var(returns, 0.95)
            metrics.append(RiskMetricValue(
                metric_id=f"var_{symbol}_{int(timestamp.timestamp())}",
                symbol=symbol,
                metric_type=RiskMetric.VAR,
                value=round(var_95, 4),
                timestamp=timestamp,
                parameters={"confidence": 0.95},
                interpretation="95%置信度下的最大可能损失"
            ))
            
            # 计算条件VaR
            cvar_95 = self._calculate_cvar(returns, 0.95)
            metrics.append(RiskMetricValue(
                metric_id=f"cvar_{symbol}_{int(timestamp.timestamp())}",
                symbol=symbol,
                metric_type=RiskMetric.CVAR,
                value=round(cvar_95, 4),
                timestamp=timestamp,
                parameters={"confidence": 0.95},
                interpretation="超过VaR时的期望损失"
            ))
            
            # 计算最大回撤
            max_dd = self._calculate_max_drawdown(price_history)
            metrics.append(RiskMetricValue(
                metric_id=f"mdd_{symbol}_{int(timestamp.timestamp())}",
                symbol=symbol,
                metric_type=RiskMetric.MAX_DRAWDOWN,
                value=round(max_dd, 4),
                timestamp=timestamp,
                interpretation="历史最大回撤幅度"
            ))
            
            # 计算波动率
            volatility = statistics.stdev(returns) * math.sqrt(252)  # 年化波动率
            metrics.append(RiskMetricValue(
                metric_id=f"vol_{symbol}_{int(timestamp.timestamp())}",
                symbol=symbol,
                metric_type=RiskMetric.VOLATILITY,
                value=round(volatility, 4),
                timestamp=timestamp,
                interpretation="年化波动率"
            ))
            
            # 计算夏普比率 (假设无风险利率为3%)
            risk_free_rate = 0.03
            avg_return = statistics.mean(returns) * 252  # 年化收益率
            sharpe = (avg_return - risk_free_rate) / volatility if volatility > 0 else 0
            metrics.append(RiskMetricValue(
                metric_id=f"sharpe_{symbol}_{int(timestamp.timestamp())}",
                symbol=symbol,
                metric_type=RiskMetric.SHARPE_RATIO,
                value=round(sharpe, 4),
                timestamp=timestamp,
                parameters={"risk_free_rate": risk_free_rate},
                interpretation="风险调整后收益指标"
            ))
            
            # 存储指标
            if symbol not in self.risk_metrics:
                self.risk_metrics[symbol] = []
            
            self.risk_metrics[symbol].extend(metrics)
            
            # 保留最近100个指标
            if len(self.risk_metrics[symbol]) > 100:
                self.risk_metrics[symbol] = self.risk_metrics[symbol][-100:]
            
            logger.info(f"计算风险指标完成: {symbol} - {len(metrics)} 个指标")
            return metrics
            
        except Exception as e:
            logger.error(f"计算风险指标失败: {e}")
            return []
    
    def _calculate_var(self, returns: List[float], confidence: float) -> float:
        """计算风险价值 (VaR)"""
        if not returns:
            return 0.0
        
        sorted_returns = sorted(returns)
        index = int((1 - confidence) * len(sorted_returns))
        return abs(sorted_returns[index]) if index < len(sorted_returns) else 0.0
    
    def _calculate_cvar(self, returns: List[float], confidence: float) -> float:
        """计算条件风险价值 (CVaR)"""
        if not returns:
            return 0.0
        
        var = self._calculate_var(returns, confidence)
        tail_returns = [r for r in returns if abs(r) >= var]
        
        return statistics.mean([abs(r) for r in tail_returns]) if tail_returns else 0.0
    
    def _calculate_max_drawdown(self, prices: List[float]) -> float:
        """计算最大回撤"""
        if len(prices) < 2:
            return 0.0
        
        peak = prices[0]
        max_drawdown = 0.0
        
        for price in prices[1:]:
            if price > peak:
                peak = price
            
            drawdown = (peak - price) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown
    
    def run_stress_test(self, symbol: str, base_value: float, scenario_id: str = None) -> List[StressTestResult]:
        """运行压力测试"""
        try:
            results = []
            scenarios = [self.stress_scenarios[scenario_id]] if scenario_id else list(self.stress_scenarios.values())
            
            for scenario in scenarios:
                # 计算压力情景下的价值
                price_shock = scenario.parameters.get("price_shock", 0.0)
                volatility_spike = scenario.parameters.get("volatility_spike", 1.0)
                
                # 基本价格冲击
                stressed_value = base_value * (1 + price_shock)
                
                # 加入波动率冲击的额外影响
                if volatility_spike > 1.0:
                    additional_shock = random.uniform(-0.05, 0.0) * volatility_spike
                    stressed_value *= (1 + additional_shock)
                
                loss_amount = base_value - stressed_value
                loss_percentage = loss_amount / base_value if base_value > 0 else 0
                
                result = StressTestResult(
                    test_id=f"stress_{symbol}_{scenario.scenario_id}_{int(datetime.now().timestamp())}",
                    scenario=scenario,
                    symbol=symbol,
                    base_value=base_value,
                    stressed_value=round(stressed_value, 2),
                    loss_amount=round(loss_amount, 2),
                    loss_percentage=round(loss_percentage, 4),
                    timestamp=datetime.now()
                )
                
                results.append(result)
                self.stress_test_results.append(result)
            
            # 保留最近1000个测试结果
            if len(self.stress_test_results) > 1000:
                self.stress_test_results = self.stress_test_results[-1000:]
            
            logger.info(f"压力测试完成: {symbol} - {len(results)} 个场景")
            return results
            
        except Exception as e:
            logger.error(f"压力测试失败: {e}")
            return []
    
    def _generate_mitigation_strategies(self, risk_level: RiskLevel, risk_factors: List[str]) -> List[str]:
        """生成风险缓解策略"""
        strategies = []
        
        # 基于风险等级的通用策略
        if risk_level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH, RiskLevel.EXTREME]:
            strategies.extend([
                "立即降低仓位规模",
                "设置严格止损点",
                "增加对冲保护"
            ])
        elif risk_level == RiskLevel.MEDIUM:
            strategies.extend([
                "适度降低仓位",
                "密切监控市场动态",
                "准备应急计划"
            ])
        
        # 基于具体风险因素的策略
        for factor in risk_factors:
            if "波动率" in factor or "波动" in factor:
                strategies.append("考虑波动率对冲策略")
            if "流动性" in factor:
                strategies.append("分批交易减少市场冲击")
            if "技术指标" in factor:
                strategies.append("等待技术指标修复")
        
        return list(set(strategies))  # 去重
    
    def _generate_risk_alert(self, assessment: RiskAssessment):
        """生成风险告警"""
        
        severity_thresholds = {
            RiskLevel.HIGH: 65,
            RiskLevel.VERY_HIGH: 80,
            RiskLevel.EXTREME: 90
        }
        
        threshold = severity_thresholds.get(assessment.risk_level, 50)
        
        alert = RiskAlert(
            alert_id=f"alert_{assessment.symbol}_{int(datetime.now().timestamp())}",
            symbol=assessment.symbol,
            risk_type=assessment.risk_type,
            severity=assessment.risk_level,
            message=f"{assessment.symbol} {assessment.risk_type.value} 风险等级达到 {assessment.risk_level.value}",
            timestamp=datetime.now(),
            threshold_breached=threshold,
            current_value=assessment.risk_score,
            recommended_actions=assessment.mitigation_strategies[:3]  # 前3个建议
        )
        
        self.risk_alerts.append(alert)
        
        # 保留最近200个告警
        if len(self.risk_alerts) > 200:
            self.risk_alerts = self.risk_alerts[-200:]
        
        logger.warning(f"风险告警: {alert.message}")
    
    def get_risk_stats(self) -> Dict[str, Any]:
        """获取风险统计信息"""
        try:
            total_metrics = sum(len(metrics) for metrics in self.risk_metrics.values())
            
            # 风险等级分布
            risk_level_dist = {level.value: 0 for level in RiskLevel}
            for assessment in self.risk_assessments:
                risk_level_dist[assessment.risk_level.value] += 1
            
            # 平均风险得分
            avg_risk_score = statistics.mean([a.risk_score for a in self.risk_assessments]) if self.risk_assessments else 0
            
            stats = {
                "total_risk_assessments": len(self.risk_assessments),
                "total_risk_metrics": total_metrics,
                "portfolio_risks": len(self.portfolio_risks),
                "active_risk_alerts": len([a for a in self.risk_alerts if (datetime.now() - a.timestamp).days < 1]),
                "stress_test_scenarios": len(self.stress_scenarios),
                "stress_test_results": len(self.stress_test_results),
                "risk_level_distribution": risk_level_dist,
                "average_risk_score": round(avg_risk_score, 1),
                "risk_type_distribution": {
                    risk_type.value: len([a for a in self.risk_assessments if a.risk_type == risk_type])
                    for risk_type in RiskType
                },
                "recent_alerts": len([a for a in self.risk_alerts if (datetime.now() - a.timestamp).total_seconds() < 24 * 3600]),
                "symbols_under_monitoring": len(self.risk_metrics.keys())
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取风险统计失败: {e}")
            return {}


# 生成模拟风险评估的辅助函数
def generate_sample_risk_assessments(engine: RiskAssessmentEngine, count: int = 30):
    """生成示例风险评估"""
    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    
    for i in range(count):
        symbol = random.choice(symbols)
        
        # 生成模拟市场数据
        market_data = {
            "current_price": random.uniform(100, 50000),
            "volatility": random.uniform(0.01, 0.15),
            "volume": random.uniform(500000, 5000000),
            "avg_volume_30d": random.uniform(800000, 3000000),
            "price_change_24h": random.uniform(-0.2, 0.2),
            "rsi": random.uniform(20, 80),
            "bid_ask_spread": random.uniform(0.0005, 0.01),
            "volatility_30d": random.uniform(0.02, 0.08),
            "position_size": random.uniform(0.05, 0.3),
            "portfolio_correlation": random.uniform(0.1, 0.9)
        }
        
        # 随机选择风险类型进行评估
        risk_type = random.choice([None, RiskType.VOLATILITY_RISK, RiskType.LIQUIDITY_RISK, RiskType.CONCENTRATION_RISK])
        
        # 进行风险评估
        assessment = engine.assess_risk(symbol, market_data, risk_type)
        
        # 计算一些风险指标
        if random.random() < 0.4:  # 40%的概率计算风险指标
            price_history = [random.uniform(90, 110) * (1 + random.uniform(-0.05, 0.05)) for _ in range(30)]
            engine.calculate_risk_metrics(symbol, price_history)
        
        # 运行一些压力测试
        if random.random() < 0.3:  # 30%的概率运行压力测试
            base_value = market_data["current_price"] * 100  # 假设持有100个单位
            scenario_id = random.choice(list(engine.stress_scenarios.keys()))
            engine.run_stress_test(symbol, base_value, scenario_id)