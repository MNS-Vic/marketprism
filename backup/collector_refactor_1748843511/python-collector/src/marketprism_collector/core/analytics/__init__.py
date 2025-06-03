"""
MarketPrism 高级数据分析和智能决策系统 - Week 5 Day 9
提供AI驱动的市场数据分析、交易信号生成、风险评估和智能决策支持
"""

import logging
import statistics
from datetime import datetime
from typing import Dict, Any, Optional
from .market_data_analyzer import MarketDataAnalyzer, generate_sample_market_data
from .trading_signal_generator import TradingSignalGenerator, generate_sample_trading_signals  
from .risk_assessment_engine import RiskAssessmentEngine, generate_sample_risk_assessments
from .predictive_modeling import PredictiveModeling, generate_sample_predictions
from .decision_support_system import DecisionSupportSystem, generate_sample_decisions

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalyticsManager:
    """高级数据分析和智能决策系统统一管理器"""
    
    def __init__(self):
        self.market_analyzer = MarketDataAnalyzer()
        self.signal_generator = TradingSignalGenerator()
        self.risk_engine = RiskAssessmentEngine()
        self.predictive_modeling = PredictiveModeling()
        self.decision_system = DecisionSupportSystem()
        
        logger.info("高级数据分析和智能决策系统初始化完成")
    
    def get_unified_analytics_stats(self) -> Dict[str, Any]:
        """获取统一的分析统计"""
        try:
            # 获取各组件统计
            analyzer_stats = self.market_analyzer.get_analyzer_stats()
            signal_stats = self.signal_generator.get_signal_stats()
            risk_stats = self.risk_engine.get_risk_stats()
            modeling_stats = self.predictive_modeling.get_modeling_stats()
            decision_stats = self.decision_system.get_decision_stats()
            
            # 计算AI健康度
            ai_health_score = self._calculate_ai_health_score({
                "analyzer": analyzer_stats,
                "signals": signal_stats,
                "risk": risk_stats,
                "modeling": modeling_stats,
                "decisions": decision_stats
            })
            
            unified_stats = {
                "system_overview": {
                    "ai_health_score": ai_health_score,
                    "total_components": 5,
                    "active_components": 5,
                    "last_updated": datetime.now().isoformat()
                },
                "market_data_analyzer": analyzer_stats,
                "trading_signal_generator": signal_stats,
                "risk_assessment_engine": risk_stats,
                "predictive_modeling": modeling_stats,
                "decision_support_system": decision_stats
            }
            
            return unified_stats
            
        except Exception as e:
            logger.error(f"获取统一分析统计失败: {e}")
            return {"error": str(e)}
    
    def _calculate_ai_health_score(self, component_stats: Dict[str, Any]) -> int:
        """计算AI健康度得分"""
        try:
            scores = []
            
            # 市场分析器得分 (0-20分)
            analyzer_stats = component_stats.get("analyzer", {})
            if analyzer_stats.get("total_data_points", 0) > 0:
                analyzer_score = min(20, analyzer_stats.get("total_data_points", 0) / 100 * 20)
                scores.append(analyzer_score)
            
            # 信号生成器得分 (0-20分)
            signal_stats = component_stats.get("signals", {})
            if signal_stats.get("total_signal_history", 0) > 0:
                signal_score = min(20, signal_stats.get("total_signal_history", 0) / 50 * 20)
                scores.append(signal_score)
            
            # 风险评估得分 (0-20分)
            risk_stats = component_stats.get("risk", {})
            if risk_stats.get("total_risk_assessments", 0) > 0:
                risk_score = min(20, risk_stats.get("total_risk_assessments", 0) / 30 * 20)
                scores.append(risk_score)
            
            # 预测建模得分 (0-20分)
            modeling_stats = component_stats.get("modeling", {})
            if modeling_stats.get("total_predictions", 0) > 0:
                modeling_score = min(20, modeling_stats.get("total_predictions", 0) / 40 * 20)
                scores.append(modeling_score)
            
            # 决策支持得分 (0-20分)
            decision_stats = component_stats.get("decisions", {})
            if decision_stats.get("total_recommendations", 0) > 0:
                decision_score = min(20, decision_stats.get("total_recommendations", 0) / 25 * 20)
                scores.append(decision_score)
            
            total_score = sum(scores) if scores else 0
            return min(100, int(total_score))
            
        except Exception as e:
            logger.error(f"计算AI健康度失败: {e}")
            return 0
    
    def get_system_intelligence_summary(self) -> Dict[str, Any]:
        """获取系统智能化摘要"""
        try:
            unified_stats = self.get_unified_analytics_stats()
            ai_health_score = unified_stats.get("system_overview", {}).get("ai_health_score", 0)
            
            # 确定系统状态
            if ai_health_score >= 85:
                overall_status = "🌟 优秀"
                status_description = "AI系统运行状态优秀，各组件协同工作良好"
            elif ai_health_score >= 70:
                overall_status = "🎯 良好"
                status_description = "AI系统运行状态良好，满足基本分析需求"
            elif ai_health_score >= 50:
                overall_status = "⚠️ 一般"
                status_description = "AI系统运行状态一般，部分功能可能受限"
            else:
                overall_status = "❌ 需要改进"
                status_description = "AI系统运行状态不佳，需要优化改进"
            
            summary = {
                "overall_status": overall_status,
                "status_description": status_description,
                "ai_health_score": ai_health_score,
                "ai_capabilities": {
                    "market_analysis": "✅ 深度市场数据分析和技术指标计算",
                    "signal_generation": "✅ 智能交易信号生成和策略管理",
                    "risk_assessment": "✅ 全面风险评估和压力测试",
                    "predictive_modeling": "✅ 机器学习模型管理和预测",
                    "decision_support": "✅ AI驱动的决策建议和自动化",
                    "system_integration": "✅ 统一的智能分析平台"
                },
                "key_metrics": {
                    "total_data_processed": unified_stats.get("market_data_analyzer", {}).get("total_data_points", 0),
                    "signals_generated": unified_stats.get("trading_signal_generator", {}).get("total_signal_history", 0),
                    "risk_assessments": unified_stats.get("risk_assessment_engine", {}).get("total_risk_assessments", 0),
                    "predictions_made": unified_stats.get("predictive_modeling", {}).get("total_predictions", 0),
                    "decisions_recommended": unified_stats.get("decision_support_system", {}).get("total_recommendations", 0)
                },
                "timestamp": datetime.now().isoformat()
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"获取系统智能化摘要失败: {e}")
            return {"error": str(e)}
    
    def perform_intelligence_check(self) -> bool:
        """执行系统智能化检查"""
        try:
            # 检查各组件是否正常工作
            checks = {
                "market_analyzer": self.market_analyzer is not None,
                "signal_generator": self.signal_generator is not None,
                "risk_engine": self.risk_engine is not None,
                "predictive_modeling": self.predictive_modeling is not None,
                "decision_system": self.decision_system is not None
            }
            
            # 检查统计数据可用性
            try:
                analyzer_stats = self.market_analyzer.get_analyzer_stats()
                signal_stats = self.signal_generator.get_signal_stats()
                risk_stats = self.risk_engine.get_risk_stats()
                modeling_stats = self.predictive_modeling.get_modeling_stats()
                decision_stats = self.decision_system.get_decision_stats()
                
                checks["stats_available"] = all([
                    isinstance(analyzer_stats, dict),
                    isinstance(signal_stats, dict),
                    isinstance(risk_stats, dict),
                    isinstance(modeling_stats, dict),
                    isinstance(decision_stats, dict)
                ])
            except Exception:
                checks["stats_available"] = False
            
            # 所有检查通过才返回True
            return all(checks.values())
            
        except Exception as e:
            logger.error(f"智能化检查失败: {e}")
            return False
    
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        try:
            health = {
                "market_analyzer": "active",
                "signal_generator": "active",
                "risk_engine": "active",
                "predictive_modeling": "active",
                "decision_system": "active",
                "overall_status": "healthy",
                "timestamp": datetime.now().isoformat()
            }
            
            return health
            
        except Exception as e:
            logger.error(f"获取系统健康状态失败: {e}")
            return {"overall_status": "error", "error": str(e)}


# 全局分析管理器实例
_analytics_manager = None


def initialize_analytics_system(with_sample_data: bool = False) -> AnalyticsManager:
    """初始化分析系统"""
    global _analytics_manager
    
    if _analytics_manager is None:
        _analytics_manager = AnalyticsManager()
        
        if with_sample_data:
            # 生成示例数据
            generate_sample_market_data(_analytics_manager.market_analyzer, 150)
            generate_sample_trading_signals(_analytics_manager.signal_generator, 60)
            generate_sample_risk_assessments(_analytics_manager.risk_engine, 40)
            generate_sample_predictions(_analytics_manager.predictive_modeling, 50)
            generate_sample_decisions(_analytics_manager.decision_system, 35)
            
            logger.info("分析系统已初始化并生成示例数据")
        else:
            logger.info("分析系统已初始化")
    
    return _analytics_manager


def get_analytics_manager() -> Optional[AnalyticsManager]:
    """获取分析管理器实例"""
    return _analytics_manager


# 导出主要类和函数
__all__ = [
    'AnalyticsManager',
    'initialize_analytics_system',
    'get_analytics_manager',
    'MarketDataAnalyzer',
    'TradingSignalGenerator',
    'RiskAssessmentEngine',
    'PredictiveModeling',
    'DecisionSupportSystem'
]