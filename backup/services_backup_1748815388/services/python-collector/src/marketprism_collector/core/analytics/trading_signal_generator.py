"""
交易信号生成器 - Week 5 Day 9
基于市场分析生成智能交易信号和建议
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import json
import random
import statistics

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    ENTRY = "entry"
    EXIT = "exit"


class SignalStrength(Enum):
    """信号强度"""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class SignalSource(Enum):
    """信号来源"""
    TECHNICAL_ANALYSIS = "technical_analysis"
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    AI_MODEL = "ai_model"
    PATTERN_RECOGNITION = "pattern_recognition"
    VOLUME_ANALYSIS = "volume_analysis"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"


class TimeFrame(Enum):
    """时间框架"""
    SCALPING = "1m"
    SHORT_TERM = "5m"
    INTRADAY = "15m"
    SWING = "1h"
    DAILY = "1d"
    WEEKLY = "1w"


@dataclass
class TradingSignal:
    """交易信号"""
    signal_id: str
    symbol: str
    signal_type: SignalType
    signal_strength: SignalStrength
    signal_source: SignalSource
    timestamp: datetime
    price: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    confidence: float = 0.0
    timeframe: TimeFrame = TimeFrame.SWING
    description: str = ""
    reasoning: List[str] = field(default_factory=list)
    risk_reward_ratio: float = 0.0
    expected_duration: Optional[timedelta] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "signal_strength": self.signal_strength.value,
            "signal_source": self.signal_source.value,
            "timestamp": self.timestamp.isoformat(),
            "price": self.price,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "confidence": self.confidence,
            "timeframe": self.timeframe.value,
            "description": self.description,
            "reasoning": self.reasoning,
            "risk_reward_ratio": self.risk_reward_ratio
        }


@dataclass
class SignalStrategy:
    """信号策略"""
    strategy_id: str
    name: str
    description: str
    parameters: Dict[str, Any]
    timeframes: List[TimeFrame]
    signal_sources: List[SignalSource]
    min_confidence: float = 0.6
    max_risk: float = 0.02  # 2%
    enabled: bool = True


@dataclass
class SignalPerformance:
    """信号表现"""
    signal_id: str
    entry_price: float
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    max_drawdown: float = 0.0
    duration: Optional[timedelta] = None
    success: Optional[bool] = None
    closed_at: Optional[datetime] = None


@dataclass
class PortfolioSignal:
    """组合信号"""
    portfolio_id: str
    signals: List[TradingSignal]
    total_exposure: float
    risk_level: str
    diversification_score: float
    timestamp: datetime


class TradingSignalGenerator:
    """交易信号生成器"""
    
    def __init__(self):
        self.active_signals: Dict[str, TradingSignal] = {}
        self.signal_history: List[TradingSignal] = []
        self.signal_strategies: Dict[str, SignalStrategy] = {}
        self.signal_performance: Dict[str, SignalPerformance] = {}
        self.portfolio_signals: List[PortfolioSignal] = []
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 初始化默认策略
        self._initialize_default_strategies()
        logger.info("交易信号生成器初始化完成")
    
    def _initialize_default_strategies(self):
        """初始化默认策略"""
        
        # 趋势跟随策略
        trend_strategy = SignalStrategy(
            strategy_id="trend_following",
            name="趋势跟随策略",
            description="基于移动平均线和趋势指标的趋势跟随策略",
            parameters={
                "ma_short": 20,
                "ma_long": 50,
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70
            },
            timeframes=[TimeFrame.SWING, TimeFrame.DAILY],
            signal_sources=[SignalSource.TECHNICAL_ANALYSIS, SignalSource.MOMENTUM],
            min_confidence=0.7,
            max_risk=0.02
        )
        
        # 均值回归策略
        mean_reversion_strategy = SignalStrategy(
            strategy_id="mean_reversion",
            name="均值回归策略",
            description="基于布林带和RSI的均值回归策略",
            parameters={
                "bb_period": 20,
                "bb_std": 2,
                "rsi_period": 14,
                "volume_threshold": 1.5
            },
            timeframes=[TimeFrame.INTRADAY, TimeFrame.SWING],
            signal_sources=[SignalSource.TECHNICAL_ANALYSIS, SignalSource.MEAN_REVERSION],
            min_confidence=0.6,
            max_risk=0.015
        )
        
        # 突破策略
        breakout_strategy = SignalStrategy(
            strategy_id="breakout",
            name="突破策略",
            description="基于价格突破和成交量确认的突破策略",
            parameters={
                "lookback_period": 20,
                "volume_multiplier": 2.0,
                "breakout_threshold": 0.02
            },
            timeframes=[TimeFrame.SWING, TimeFrame.DAILY],
            signal_sources=[SignalSource.PATTERN_RECOGNITION, SignalSource.VOLUME_ANALYSIS],
            min_confidence=0.75,
            max_risk=0.025
        )
        
        # AI模型策略
        ai_strategy = SignalStrategy(
            strategy_id="ai_model",
            name="AI智能策略",
            description="基于机器学习模型的智能交易策略",
            parameters={
                "model_confidence_threshold": 0.8,
                "feature_importance_threshold": 0.1,
                "ensemble_models": 3
            },
            timeframes=[TimeFrame.INTRADAY, TimeFrame.SWING, TimeFrame.DAILY],
            signal_sources=[SignalSource.AI_MODEL, SignalSource.SENTIMENT_ANALYSIS],
            min_confidence=0.8,
            max_risk=0.02
        )
        
        strategies = [trend_strategy, mean_reversion_strategy, breakout_strategy, ai_strategy]
        for strategy in strategies:
            self.signal_strategies[strategy.strategy_id] = strategy
    
    def generate_signal(self, symbol: str, market_data: Dict[str, Any], strategy_id: str = None) -> Optional[TradingSignal]:
        """生成交易信号"""
        try:
            if strategy_id and strategy_id not in self.signal_strategies:
                logger.warning(f"策略不存在: {strategy_id}")
                return None
            
            # 如果没有指定策略，选择最适合的策略
            if not strategy_id:
                strategy_id = self._select_best_strategy(market_data)
            
            strategy = self.signal_strategies[strategy_id]
            if not strategy.enabled:
                return None
            
            # 根据策略生成信号
            signal = self._generate_signal_by_strategy(symbol, market_data, strategy)
            
            if signal and signal.confidence >= strategy.min_confidence:
                # 计算风险收益比
                signal.risk_reward_ratio = self._calculate_risk_reward_ratio(signal)
                
                # 添加到活跃信号
                self.active_signals[signal.signal_id] = signal
                self.signal_history.append(signal)
                
                # 保留最近1000个历史信号
                if len(self.signal_history) > 1000:
                    self.signal_history = self.signal_history[-1000:]
                
                logger.info(f"生成交易信号: {signal.symbol} {signal.signal_type.value} - 置信度: {signal.confidence}")
                return signal
            
            return None
            
        except Exception as e:
            logger.error(f"生成交易信号失败: {e}")
            return None
    
    def _select_best_strategy(self, market_data: Dict[str, Any]) -> str:
        """选择最佳策略"""
        # 简化的策略选择逻辑
        volatility = market_data.get("volatility", 0.02)
        trend_strength = market_data.get("trend_strength", 0.5)
        volume_ratio = market_data.get("volume_ratio", 1.0)
        
        if trend_strength > 0.7:
            return "trend_following"
        elif volatility > 0.05:
            return "breakout"
        elif volume_ratio < 0.8:
            return "mean_reversion"
        else:
            return "ai_model"
    
    def _generate_signal_by_strategy(self, symbol: str, market_data: Dict[str, Any], strategy: SignalStrategy) -> Optional[TradingSignal]:
        """根据策略生成信号"""
        
        current_price = market_data.get("current_price", 100.0)
        
        if strategy.strategy_id == "trend_following":
            return self._generate_trend_signal(symbol, market_data, strategy, current_price)
        elif strategy.strategy_id == "mean_reversion":
            return self._generate_mean_reversion_signal(symbol, market_data, strategy, current_price)
        elif strategy.strategy_id == "breakout":
            return self._generate_breakout_signal(symbol, market_data, strategy, current_price)
        elif strategy.strategy_id == "ai_model":
            return self._generate_ai_signal(symbol, market_data, strategy, current_price)
        
        return None
    
    def _generate_trend_signal(self, symbol: str, market_data: Dict[str, Any], strategy: SignalStrategy, current_price: float) -> Optional[TradingSignal]:
        """生成趋势跟随信号"""
        
        ma_short = market_data.get("ma_20", current_price)
        ma_long = market_data.get("ma_50", current_price)
        rsi = market_data.get("rsi", 50)
        
        signal_type = None
        confidence = 0.5
        reasoning = []
        
        if current_price > ma_short > ma_long and rsi < 70:
            signal_type = SignalType.BUY
            confidence = 0.75
            reasoning = ["价格在短期均线上方", "短期均线在长期均线上方", "RSI未超买"]
        elif current_price < ma_short < ma_long and rsi > 30:
            signal_type = SignalType.SELL
            confidence = 0.75
            reasoning = ["价格在短期均线下方", "短期均线在长期均线下方", "RSI未超卖"]
        
        if signal_type:
            # 计算目标价位和止损价位
            if signal_type == SignalType.BUY:
                target_price = current_price * 1.05  # 5%目标
                stop_loss = current_price * 0.97   # 3%止损
            else:
                target_price = current_price * 0.95  # 5%目标
                stop_loss = current_price * 1.03   # 3%止损
            
            signal = TradingSignal(
                signal_id=f"trend_{symbol}_{int(datetime.now().timestamp())}",
                symbol=symbol,
                signal_type=signal_type,
                signal_strength=SignalStrength.MODERATE if confidence > 0.7 else SignalStrength.WEAK,
                signal_source=SignalSource.TECHNICAL_ANALYSIS,
                timestamp=datetime.now(),
                price=current_price,
                target_price=target_price,
                stop_loss=stop_loss,
                confidence=confidence,
                timeframe=TimeFrame.SWING,
                description=f"趋势跟随策略 - {signal_type.value.upper()}信号",
                reasoning=reasoning
            )
            
            return signal
        
        return None
    
    def _generate_mean_reversion_signal(self, symbol: str, market_data: Dict[str, Any], strategy: SignalStrategy, current_price: float) -> Optional[TradingSignal]:
        """生成均值回归信号"""
        
        bb_upper = market_data.get("bb_upper", current_price * 1.02)
        bb_lower = market_data.get("bb_lower", current_price * 0.98)
        bb_middle = market_data.get("bb_middle", current_price)
        rsi = market_data.get("rsi", 50)
        volume_ratio = market_data.get("volume_ratio", 1.0)
        
        signal_type = None
        confidence = 0.5
        reasoning = []
        
        if current_price <= bb_lower and rsi < 30 and volume_ratio > 1.2:
            signal_type = SignalType.BUY
            confidence = 0.8
            reasoning = ["价格触及布林带下轨", "RSI超卖", "成交量放大"]
        elif current_price >= bb_upper and rsi > 70 and volume_ratio > 1.2:
            signal_type = SignalType.SELL
            confidence = 0.8
            reasoning = ["价格触及布林带上轨", "RSI超买", "成交量放大"]
        
        if signal_type:
            # 均值回归目标是回到中轨
            if signal_type == SignalType.BUY:
                target_price = bb_middle
                stop_loss = current_price * 0.98
            else:
                target_price = bb_middle
                stop_loss = current_price * 1.02
            
            signal = TradingSignal(
                signal_id=f"meanrev_{symbol}_{int(datetime.now().timestamp())}",
                symbol=symbol,
                signal_type=signal_type,
                signal_strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
                signal_source=SignalSource.MEAN_REVERSION,
                timestamp=datetime.now(),
                price=current_price,
                target_price=target_price,
                stop_loss=stop_loss,
                confidence=confidence,
                timeframe=TimeFrame.INTRADAY,
                description=f"均值回归策略 - {signal_type.value.upper()}信号",
                reasoning=reasoning,
                expected_duration=timedelta(hours=4)
            )
            
            return signal
        
        return None
    
    def _generate_breakout_signal(self, symbol: str, market_data: Dict[str, Any], strategy: SignalStrategy, current_price: float) -> Optional[TradingSignal]:
        """生成突破信号"""
        
        resistance_level = market_data.get("resistance", current_price * 1.05)
        support_level = market_data.get("support", current_price * 0.95)
        volume_ratio = market_data.get("volume_ratio", 1.0)
        price_change_24h = market_data.get("price_change_24h", 0.0)
        
        signal_type = None
        confidence = 0.5
        reasoning = []
        
        # 向上突破
        if current_price > resistance_level and volume_ratio > 2.0 and price_change_24h > 0.02:
            signal_type = SignalType.BUY
            confidence = 0.85
            reasoning = ["价格突破阻力位", "成交量大幅放大", "24小时涨幅显著"]
        # 向下突破
        elif current_price < support_level and volume_ratio > 2.0 and price_change_24h < -0.02:
            signal_type = SignalType.SELL
            confidence = 0.85
            reasoning = ["价格跌破支撑位", "成交量大幅放大", "24小时跌幅显著"]
        
        if signal_type:
            if signal_type == SignalType.BUY:
                target_price = current_price * 1.08  # 8%目标
                stop_loss = resistance_level * 0.98  # 回到突破点下方
            else:
                target_price = current_price * 0.92  # 8%目标
                stop_loss = support_level * 1.02   # 回到突破点上方
            
            signal = TradingSignal(
                signal_id=f"breakout_{symbol}_{int(datetime.now().timestamp())}",
                symbol=symbol,
                signal_type=signal_type,
                signal_strength=SignalStrength.STRONG,
                signal_source=SignalSource.PATTERN_RECOGNITION,
                timestamp=datetime.now(),
                price=current_price,
                target_price=target_price,
                stop_loss=stop_loss,
                confidence=confidence,
                timeframe=TimeFrame.SWING,
                description=f"突破策略 - {signal_type.value.upper()}信号",
                reasoning=reasoning,
                expected_duration=timedelta(days=2)
            )
            
            return signal
        
        return None
    
    def _generate_ai_signal(self, symbol: str, market_data: Dict[str, Any], strategy: SignalStrategy, current_price: float) -> Optional[TradingSignal]:
        """生成AI模型信号"""
        
        # 模拟AI模型输出
        ai_prediction = random.uniform(0.3, 0.9)  # 模拟置信度
        ai_direction = random.choice(["buy", "sell", "hold"])
        sentiment_score = market_data.get("sentiment", 0.5)
        
        if ai_prediction < 0.6:
            return None
        
        signal_type = None
        if ai_direction == "buy" and sentiment_score > 0.6:
            signal_type = SignalType.BUY
        elif ai_direction == "sell" and sentiment_score < 0.4:
            signal_type = SignalType.SELL
        
        if signal_type:
            confidence = min(ai_prediction, 0.9)
            
            # AI模型通常提供更保守的目标
            if signal_type == SignalType.BUY:
                target_price = current_price * 1.03
                stop_loss = current_price * 0.985
            else:
                target_price = current_price * 0.97
                stop_loss = current_price * 1.015
            
            signal = TradingSignal(
                signal_id=f"ai_{symbol}_{int(datetime.now().timestamp())}",
                symbol=symbol,
                signal_type=signal_type,
                signal_strength=SignalStrength.STRONG if confidence > 0.8 else SignalStrength.MODERATE,
                signal_source=SignalSource.AI_MODEL,
                timestamp=datetime.now(),
                price=current_price,
                target_price=target_price,
                stop_loss=stop_loss,
                confidence=confidence,
                timeframe=TimeFrame.DAILY,
                description=f"AI智能策略 - {signal_type.value.upper()}信号",
                reasoning=[f"AI模型预测置信度: {ai_prediction:.2f}", f"市场情绪: {sentiment_score:.2f}"],
                expected_duration=timedelta(days=1)
            )
            
            return signal
        
        return None
    
    def _calculate_risk_reward_ratio(self, signal: TradingSignal) -> float:
        """计算风险收益比"""
        if not signal.target_price or not signal.stop_loss:
            return 0.0
        
        if signal.signal_type == SignalType.BUY:
            potential_profit = signal.target_price - signal.price
            potential_loss = signal.price - signal.stop_loss
        else:
            potential_profit = signal.price - signal.target_price
            potential_loss = signal.stop_loss - signal.price
        
        if potential_loss <= 0:
            return 0.0
        
        return round(potential_profit / potential_loss, 2)
    
    def update_signal_performance(self, signal_id: str, current_price: float) -> bool:
        """更新信号表现"""
        try:
            if signal_id not in self.active_signals:
                return False
            
            signal = self.active_signals[signal_id]
            
            if signal_id not in self.signal_performance:
                self.signal_performance[signal_id] = SignalPerformance(
                    signal_id=signal_id,
                    entry_price=signal.price
                )
            
            performance = self.signal_performance[signal_id]
            
            # 计算当前盈亏
            if signal.signal_type == SignalType.BUY:
                unrealized_pnl = (current_price - signal.price) / signal.price
            else:
                unrealized_pnl = (signal.price - current_price) / signal.price
            
            # 更新最大回撤
            if unrealized_pnl < performance.max_drawdown:
                performance.max_drawdown = unrealized_pnl
            
            # 检查是否触及目标或止损
            signal_closed = False
            if signal.signal_type == SignalType.BUY:
                if current_price >= signal.target_price or current_price <= signal.stop_loss:
                    signal_closed = True
            else:
                if current_price <= signal.target_price or current_price >= signal.stop_loss:
                    signal_closed = True
            
            if signal_closed:
                performance.exit_price = current_price
                performance.realized_pnl = unrealized_pnl
                performance.success = unrealized_pnl > 0
                performance.closed_at = datetime.now()
                performance.duration = performance.closed_at - signal.timestamp
                
                # 从活跃信号中移除
                del self.active_signals[signal_id]
                
                logger.info(f"信号关闭: {signal_id} - 盈亏: {unrealized_pnl:.2%}")
            
            return True
            
        except Exception as e:
            logger.error(f"更新信号表现失败: {e}")
            return False
    
    def generate_portfolio_signals(self, symbols: List[str], market_data: Dict[str, Dict[str, Any]]) -> Optional[PortfolioSignal]:
        """生成组合信号"""
        try:
            portfolio_signals = []
            total_exposure = 0.0
            
            for symbol in symbols:
                if symbol in market_data:
                    signal = self.generate_signal(symbol, market_data[symbol])
                    if signal:
                        portfolio_signals.append(signal)
                        total_exposure += abs(signal.confidence * 0.1)  # 假设每个信号最大10%仓位
            
            if not portfolio_signals:
                return None
            
            # 计算分散化得分
            signal_types = [s.signal_type for s in portfolio_signals]
            unique_types = len(set(signal_types))
            diversification_score = unique_types / len(portfolio_signals)
            
            # 评估风险级别
            avg_confidence = statistics.mean([s.confidence for s in portfolio_signals])
            if avg_confidence > 0.8 and total_exposure < 0.5:
                risk_level = "LOW"
            elif avg_confidence > 0.6 and total_exposure < 0.8:
                risk_level = "MEDIUM"
            else:
                risk_level = "HIGH"
            
            portfolio_signal = PortfolioSignal(
                portfolio_id=f"portfolio_{int(datetime.now().timestamp())}",
                signals=portfolio_signals,
                total_exposure=round(total_exposure, 2),
                risk_level=risk_level,
                diversification_score=round(diversification_score, 2),
                timestamp=datetime.now()
            )
            
            self.portfolio_signals.append(portfolio_signal)
            
            # 保留最近50个组合信号
            if len(self.portfolio_signals) > 50:
                self.portfolio_signals = self.portfolio_signals[-50:]
            
            logger.info(f"生成组合信号: {len(portfolio_signals)} 个信号, 风险级别: {risk_level}")
            return portfolio_signal
            
        except Exception as e:
            logger.error(f"生成组合信号失败: {e}")
            return None
    
    def get_signal_stats(self) -> Dict[str, Any]:
        """获取信号统计信息"""
        try:
            # 计算成功率
            closed_performances = [p for p in self.signal_performance.values() if p.success is not None]
            success_rate = statistics.mean([1 if p.success else 0 for p in closed_performances]) if closed_performances else 0
            
            # 计算平均盈亏
            realized_pnls = [p.realized_pnl for p in closed_performances if p.realized_pnl is not None]
            avg_pnl = statistics.mean(realized_pnls) if realized_pnls else 0
            
            stats = {
                "active_signals": len(self.active_signals),
                "total_signal_history": len(self.signal_history),
                "signal_strategies": len(self.signal_strategies),
                "signal_performance_records": len(self.signal_performance),
                "portfolio_signals": len(self.portfolio_signals),
                "success_rate": round(success_rate, 3),
                "average_pnl": round(avg_pnl, 4),
                "strategy_distribution": {
                    strategy_id: len([s for s in self.signal_history if strategy_id in s.signal_id])
                    for strategy_id in self.signal_strategies.keys()
                },
                "signal_type_distribution": {
                    signal_type.value: len([s for s in self.signal_history if s.signal_type == signal_type])
                    for signal_type in SignalType
                },
                "average_confidence": round(statistics.mean([s.confidence for s in self.signal_history]) if self.signal_history else 0, 2),
                "signal_strength_distribution": {
                    strength.value: len([s for s in self.signal_history if s.signal_strength == strength])
                    for strength in SignalStrength
                }
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取信号统计失败: {e}")
            return {}


# 生成模拟交易信号的辅助函数
def generate_sample_trading_signals(generator: TradingSignalGenerator, count: int = 50):
    """生成示例交易信号"""
    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    
    for i in range(count):
        symbol = random.choice(symbols)
        
        # 生成模拟市场数据
        market_data = {
            "current_price": random.uniform(100, 50000),
            "ma_20": random.uniform(100, 50000),
            "ma_50": random.uniform(100, 50000),
            "rsi": random.uniform(20, 80),
            "bb_upper": random.uniform(105, 52000),
            "bb_middle": random.uniform(100, 50000),
            "bb_lower": random.uniform(95, 48000),
            "volume_ratio": random.uniform(0.5, 3.0),
            "volatility": random.uniform(0.01, 0.1),
            "trend_strength": random.uniform(0.2, 0.9),
            "price_change_24h": random.uniform(-0.1, 0.1),
            "resistance": random.uniform(105, 52000),
            "support": random.uniform(95, 48000),
            "sentiment": random.uniform(0.2, 0.8)
        }
        
        # 随机选择策略
        strategy_id = random.choice(list(generator.signal_strategies.keys()))
        
        # 生成信号
        signal = generator.generate_signal(symbol, market_data, strategy_id)
        
        # 模拟一些信号的表现更新
        if signal and random.random() < 0.3:  # 30%的信号会有表现更新
            new_price = market_data["current_price"] * random.uniform(0.95, 1.05)
            generator.update_signal_performance(signal.signal_id, new_price)
    
    # 生成一些组合信号
    for _ in range(5):
        portfolio_symbols = random.sample(symbols, 3)
        portfolio_market_data = {
            symbol: {
                "current_price": random.uniform(100, 50000),
                "ma_20": random.uniform(100, 50000),
                "ma_50": random.uniform(100, 50000),
                "rsi": random.uniform(20, 80),
                "volume_ratio": random.uniform(0.5, 3.0),
                "volatility": random.uniform(0.01, 0.1),
                "trend_strength": random.uniform(0.2, 0.9)
            }
            for symbol in portfolio_symbols
        }
        
        generator.generate_portfolio_signals(portfolio_symbols, portfolio_market_data)