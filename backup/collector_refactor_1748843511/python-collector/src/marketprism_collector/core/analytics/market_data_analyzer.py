"""
市场数据智能分析引擎 - Week 5 Day 9
提供深度市场数据分析、趋势识别、模式检测等功能
"""

import asyncio
import logging
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


class MarketTrend(Enum):
    """市场趋势类型"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    BREAKOUT = "breakout"
    CONSOLIDATION = "consolidation"


class AnalysisType(Enum):
    """分析类型"""
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    VOLUME = "volume"
    CORRELATION = "correlation"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    PATTERN = "pattern"


class PatternType(Enum):
    """图表模式类型"""
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIANGLE = "triangle"
    FLAG = "flag"
    WEDGE = "wedge"
    CHANNEL = "channel"
    SUPPORT_RESISTANCE = "support_resistance"


@dataclass
class MarketDataPoint:
    """市场数据点"""
    symbol: str
    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    exchange: str = ""
    timeframe: str = "1h"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "volume": self.volume,
            "exchange": self.exchange,
            "timeframe": self.timeframe
        }


@dataclass
class TechnicalIndicator:
    """技术指标"""
    indicator_name: str
    symbol: str
    value: float
    timestamp: datetime
    parameters: Dict[str, Any] = field(default_factory=dict)
    signal: str = ""  # BUY, SELL, NEUTRAL
    confidence: float = 0.0


@dataclass
class MarketPattern:
    """市场模式"""
    pattern_id: str
    pattern_type: PatternType
    symbol: str
    start_time: datetime
    end_time: datetime
    confidence: float
    description: str
    price_target: Optional[float] = None
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)


@dataclass
class MarketAnalysis:
    """市场分析结果"""
    analysis_id: str
    symbol: str
    analysis_type: AnalysisType
    timestamp: datetime
    trend: MarketTrend
    confidence: float
    key_insights: List[str]
    technical_indicators: List[TechnicalIndicator]
    patterns: List[MarketPattern]
    recommendations: List[str]
    risk_level: str = "MEDIUM"


@dataclass
class CorrelationAnalysis:
    """相关性分析"""
    correlation_id: str
    symbol_pair: tuple
    correlation_coefficient: float
    timeframe: str
    timestamp: datetime
    p_value: float
    significance: str


class MarketDataAnalyzer:
    """市场数据智能分析引擎"""
    
    def __init__(self):
        self.market_data: Dict[str, List[MarketDataPoint]] = {}
        self.technical_indicators: Dict[str, List[TechnicalIndicator]] = {}
        self.market_patterns: Dict[str, List[MarketPattern]] = {}
        self.market_analyses: List[MarketAnalysis] = []
        self.correlation_analyses: List[CorrelationAnalysis] = []
        self.executor = ThreadPoolExecutor(max_workers=6)
        
        # 初始化默认配置
        self._initialize_default_configs()
        logger.info("市场数据智能分析引擎初始化完成")
    
    def _initialize_default_configs(self):
        """初始化默认配置"""
        
        # 预设一些主要交易对
        major_symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
        for symbol in major_symbols:
            self.market_data[symbol] = []
            self.technical_indicators[symbol] = []
            self.market_patterns[symbol] = []
    
    def add_market_data(self, data_point: MarketDataPoint) -> bool:
        """添加市场数据"""
        try:
            if data_point.symbol not in self.market_data:
                self.market_data[data_point.symbol] = []
            
            self.market_data[data_point.symbol].append(data_point)
            
            # 保留最近1000个数据点
            if len(self.market_data[data_point.symbol]) > 1000:
                self.market_data[data_point.symbol] = self.market_data[data_point.symbol][-1000:]
            
            # 异步进行技术分析
            self.executor.submit(self._analyze_technical_indicators, data_point.symbol)
            
            logger.debug(f"添加市场数据: {data_point.symbol} @ {data_point.close_price}")
            return True
            
        except Exception as e:
            logger.error(f"添加市场数据失败: {e}")
            return False
    
    def _analyze_technical_indicators(self, symbol: str):
        """分析技术指标"""
        try:
            data_points = self.market_data.get(symbol, [])
            if len(data_points) < 20:  # 需要足够的数据点
                return
            
            # 计算各种技术指标
            closes = [dp.close_price for dp in data_points[-50:]]  # 最近50个收盘价
            volumes = [dp.volume for dp in data_points[-50:]]
            highs = [dp.high_price for dp in data_points[-50:]]
            lows = [dp.low_price for dp in data_points[-50:]]
            
            # SMA (简单移动平均)
            if len(closes) >= 20:
                sma_20 = statistics.mean(closes[-20:])
                sma_indicator = TechnicalIndicator(
                    indicator_name="SMA_20",
                    symbol=symbol,
                    value=sma_20,
                    timestamp=datetime.now(),
                    parameters={"period": 20},
                    signal="BUY" if closes[-1] > sma_20 else "SELL",
                    confidence=0.7
                )
                
                if symbol not in self.technical_indicators:
                    self.technical_indicators[symbol] = []
                self.technical_indicators[symbol].append(sma_indicator)
            
            # RSI (相对强弱指数)
            if len(closes) >= 14:
                rsi_value = self._calculate_rsi(closes, 14)
                rsi_signal = "SELL" if rsi_value > 70 else "BUY" if rsi_value < 30 else "NEUTRAL"
                
                rsi_indicator = TechnicalIndicator(
                    indicator_name="RSI_14",
                    symbol=symbol,
                    value=rsi_value,
                    timestamp=datetime.now(),
                    parameters={"period": 14},
                    signal=rsi_signal,
                    confidence=0.8
                )
                self.technical_indicators[symbol].append(rsi_indicator)
            
            # MACD
            if len(closes) >= 26:
                macd_line, signal_line = self._calculate_macd(closes)
                macd_signal = "BUY" if macd_line > signal_line else "SELL"
                
                macd_indicator = TechnicalIndicator(
                    indicator_name="MACD",
                    symbol=symbol,
                    value=macd_line,
                    timestamp=datetime.now(),
                    parameters={"fast": 12, "slow": 26, "signal": 9},
                    signal=macd_signal,
                    confidence=0.75
                )
                self.technical_indicators[symbol].append(macd_indicator)
            
            # 布林带
            if len(closes) >= 20:
                bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(closes, 20)
                current_price = closes[-1]
                
                if current_price > bb_upper:
                    bb_signal = "SELL"
                elif current_price < bb_lower:
                    bb_signal = "BUY"
                else:
                    bb_signal = "NEUTRAL"
                
                bb_indicator = TechnicalIndicator(
                    indicator_name="BOLLINGER_BANDS",
                    symbol=symbol,
                    value=current_price,
                    timestamp=datetime.now(),
                    parameters={"period": 20, "std_dev": 2, "upper": bb_upper, "lower": bb_lower},
                    signal=bb_signal,
                    confidence=0.6
                )
                self.technical_indicators[symbol].append(bb_indicator)
            
            # 保留最近50个指标
            if len(self.technical_indicators[symbol]) > 50:
                self.technical_indicators[symbol] = self.technical_indicators[symbol][-50:]
            
        except Exception as e:
            logger.error(f"技术指标分析失败: {e}")
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """计算RSI"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        
        avg_gain = statistics.mean(gains[-period:])
        avg_loss = statistics.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    
    def _calculate_macd(self, prices: List[float]) -> tuple:
        """计算MACD"""
        if len(prices) < 26:
            return 0.0, 0.0
        
        # 简化的MACD计算
        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)
        macd_line = ema_12 - ema_26
        
        # 信号线（MACD的9期EMA）
        signal_line = macd_line * 0.9  # 简化计算
        
        return round(macd_line, 4), round(signal_line, 4)
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """计算指数移动平均"""
        if len(prices) < period:
            return statistics.mean(prices)
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _calculate_bollinger_bands(self, prices: List[float], period: int = 20) -> tuple:
        """计算布林带"""
        if len(prices) < period:
            mean_price = statistics.mean(prices)
            return mean_price, mean_price, mean_price
        
        recent_prices = prices[-period:]
        middle_band = statistics.mean(recent_prices)
        std_dev = statistics.stdev(recent_prices)
        
        upper_band = middle_band + (2 * std_dev)
        lower_band = middle_band - (2 * std_dev)
        
        return round(upper_band, 2), round(middle_band, 2), round(lower_band, 2)
    
    def perform_comprehensive_analysis(self, symbol: str) -> Optional[MarketAnalysis]:
        """执行综合市场分析"""
        try:
            if symbol not in self.market_data or len(self.market_data[symbol]) < 20:
                logger.warning(f"数据不足，无法进行分析: {symbol}")
                return None
            
            data_points = self.market_data[symbol]
            recent_data = data_points[-50:]  # 最近50个数据点
            
            # 趋势分析
            trend = self._analyze_trend(recent_data)
            
            # 获取技术指标
            indicators = self.technical_indicators.get(symbol, [])[-10:]  # 最近10个指标
            
            # 模式识别
            patterns = self._detect_patterns(recent_data, symbol)
            
            # 生成洞察和建议
            insights = self._generate_insights(recent_data, indicators, patterns)
            recommendations = self._generate_recommendations(trend, indicators)
            
            # 计算置信度
            confidence = self._calculate_analysis_confidence(indicators, patterns)
            
            analysis = MarketAnalysis(
                analysis_id=f"analysis_{symbol}_{int(datetime.now().timestamp())}",
                symbol=symbol,
                analysis_type=AnalysisType.TECHNICAL,
                timestamp=datetime.now(),
                trend=trend,
                confidence=confidence,
                key_insights=insights,
                technical_indicators=indicators,
                patterns=patterns,
                recommendations=recommendations,
                risk_level=self._assess_risk_level(trend, indicators)
            )
            
            self.market_analyses.append(analysis)
            
            # 保留最近100个分析
            if len(self.market_analyses) > 100:
                self.market_analyses = self.market_analyses[-100:]
            
            logger.info(f"完成综合分析: {symbol} - 趋势: {trend.value}, 置信度: {confidence}")
            return analysis
            
        except Exception as e:
            logger.error(f"综合分析失败: {e}")
            return None
    
    def _analyze_trend(self, data_points: List[MarketDataPoint]) -> MarketTrend:
        """分析趋势"""
        if len(data_points) < 10:
            return MarketTrend.SIDEWAYS
        
        prices = [dp.close_price for dp in data_points]
        
        # 计算价格变化
        price_changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        positive_changes = [change for change in price_changes if change > 0]
        negative_changes = [change for change in price_changes if change < 0]
        
        # 计算波动率
        volatility = statistics.stdev(price_changes) if len(price_changes) > 1 else 0
        avg_price = statistics.mean(prices)
        volatility_ratio = volatility / avg_price * 100
        
        # 计算趋势强度
        if len(positive_changes) > len(negative_changes) * 1.5:
            if volatility_ratio > 5:
                return MarketTrend.VOLATILE
            return MarketTrend.BULLISH
        elif len(negative_changes) > len(positive_changes) * 1.5:
            if volatility_ratio > 5:
                return MarketTrend.VOLATILE
            return MarketTrend.BEARISH
        elif volatility_ratio > 8:
            return MarketTrend.VOLATILE
        elif abs(prices[-1] - prices[0]) / prices[0] * 100 > 10:
            return MarketTrend.BREAKOUT
        else:
            return MarketTrend.SIDEWAYS
    
    def _detect_patterns(self, data_points: List[MarketDataPoint], symbol: str) -> List[MarketPattern]:
        """检测图表模式"""
        patterns = []
        
        if len(data_points) < 20:
            return patterns
        
        prices = [dp.close_price for dp in data_points]
        highs = [dp.high_price for dp in data_points]
        lows = [dp.low_price for dp in data_points]
        
        # 支撑阻力位检测
        support_level = min(lows[-10:])
        resistance_level = max(highs[-10:])
        
        if abs(resistance_level - support_level) / support_level > 0.05:  # 5%以上差距
            pattern = MarketPattern(
                pattern_id=f"sr_{symbol}_{int(datetime.now().timestamp())}",
                pattern_type=PatternType.SUPPORT_RESISTANCE,
                symbol=symbol,
                start_time=data_points[-20].timestamp,
                end_time=data_points[-1].timestamp,
                confidence=0.7,
                description=f"支撑位: {support_level}, 阻力位: {resistance_level}",
                support_levels=[support_level],
                resistance_levels=[resistance_level]
            )
            patterns.append(pattern)
        
        # 双顶/双底模式检测
        if len(highs) >= 20:
            recent_highs = highs[-20:]
            max_high = max(recent_highs)
            max_indices = [i for i, h in enumerate(recent_highs) if h >= max_high * 0.98]
            
            if len(max_indices) >= 2 and max_indices[-1] - max_indices[0] > 5:
                pattern = MarketPattern(
                    pattern_id=f"double_top_{symbol}_{int(datetime.now().timestamp())}",
                    pattern_type=PatternType.DOUBLE_TOP,
                    symbol=symbol,
                    start_time=data_points[-20].timestamp,
                    end_time=data_points[-1].timestamp,
                    confidence=0.6,
                    description="检测到潜在双顶形态",
                    resistance_levels=[max_high]
                )
                patterns.append(pattern)
        
        # 存储到模式库
        if symbol not in self.market_patterns:
            self.market_patterns[symbol] = []
        
        self.market_patterns[symbol].extend(patterns)
        
        # 保留最近20个模式
        if len(self.market_patterns[symbol]) > 20:
            self.market_patterns[symbol] = self.market_patterns[symbol][-20:]
        
        return patterns
    
    def _generate_insights(self, data_points: List[MarketDataPoint], indicators: List[TechnicalIndicator], patterns: List[MarketPattern]) -> List[str]:
        """生成分析洞察"""
        insights = []
        
        if len(data_points) >= 2:
            price_change = (data_points[-1].close_price - data_points[0].close_price) / data_points[0].close_price * 100
            insights.append(f"价格变化: {price_change:.2f}%")
        
        if len(data_points) >= 10:
            volumes = [dp.volume for dp in data_points[-10:]]
            avg_volume = statistics.mean(volumes)
            if data_points[-1].volume > avg_volume * 1.5:
                insights.append("交易量显著放大，市场活跃度高")
            elif data_points[-1].volume < avg_volume * 0.5:
                insights.append("交易量萎缩，市场参与度低")
        
        # 技术指标洞察
        buy_signals = [ind for ind in indicators if ind.signal == "BUY"]
        sell_signals = [ind for ind in indicators if ind.signal == "SELL"]
        
        if len(buy_signals) > len(sell_signals):
            insights.append(f"技术指标偏向看涨 ({len(buy_signals)} 买入信号 vs {len(sell_signals)} 卖出信号)")
        elif len(sell_signals) > len(buy_signals):
            insights.append(f"技术指标偏向看跌 ({len(sell_signals)} 卖出信号 vs {len(buy_signals)} 买入信号)")
        
        # 模式洞察
        if patterns:
            insights.append(f"检测到 {len(patterns)} 个图表模式")
        
        return insights
    
    def _generate_recommendations(self, trend: MarketTrend, indicators: List[TechnicalIndicator]) -> List[str]:
        """生成交易建议"""
        recommendations = []
        
        if trend == MarketTrend.BULLISH:
            recommendations.append("趋势向上，考虑逢低买入")
        elif trend == MarketTrend.BEARISH:
            recommendations.append("趋势向下，建议减仓或观望")
        elif trend == MarketTrend.VOLATILE:
            recommendations.append("市场波动剧烈，建议降低仓位，设置止损")
        elif trend == MarketTrend.BREAKOUT:
            recommendations.append("价格突破，关注方向确认")
        else:
            recommendations.append("横盘整理，等待明确方向")
        
        # 基于技术指标的建议
        buy_signals = [ind for ind in indicators if ind.signal == "BUY"]
        sell_signals = [ind for ind in indicators if ind.signal == "SELL"]
        
        if len(buy_signals) >= 2:
            recommendations.append("多个技术指标显示买入信号")
        elif len(sell_signals) >= 2:
            recommendations.append("多个技术指标显示卖出信号")
        
        return recommendations
    
    def _calculate_analysis_confidence(self, indicators: List[TechnicalIndicator], patterns: List[MarketPattern]) -> float:
        """计算分析置信度"""
        if not indicators and not patterns:
            return 0.5
        
        # 基于指标一致性
        buy_signals = [ind for ind in indicators if ind.signal == "BUY"]
        sell_signals = [ind for ind in indicators if ind.signal == "SELL"]
        neutral_signals = [ind for ind in indicators if ind.signal == "NEUTRAL"]
        
        total_signals = len(indicators)
        if total_signals == 0:
            signal_consistency = 0.5
        else:
            max_signals = max(len(buy_signals), len(sell_signals), len(neutral_signals))
            signal_consistency = max_signals / total_signals
        
        # 基于模式置信度
        if patterns:
            pattern_confidence = statistics.mean([p.confidence for p in patterns])
        else:
            pattern_confidence = 0.5
        
        # 综合置信度
        confidence = (signal_consistency * 0.6 + pattern_confidence * 0.4)
        return round(confidence, 2)
    
    def _assess_risk_level(self, trend: MarketTrend, indicators: List[TechnicalIndicator]) -> str:
        """评估风险级别"""
        if trend in [MarketTrend.VOLATILE, MarketTrend.BREAKOUT]:
            return "HIGH"
        elif trend in [MarketTrend.BULLISH, MarketTrend.BEARISH]:
            return "MEDIUM"
        else:
            return "LOW"
    
    def get_analyzer_stats(self) -> Dict[str, Any]:
        """获取分析器统计信息"""
        try:
            total_data_points = sum(len(data) for data in self.market_data.values())
            total_indicators = sum(len(indicators) for indicators in self.technical_indicators.values())
            total_patterns = sum(len(patterns) for patterns in self.market_patterns.values())
            
            stats = {
                "total_symbols": len(self.market_data),
                "total_data_points": total_data_points,
                "total_technical_indicators": total_indicators,
                "total_patterns": total_patterns,
                "total_analyses": len(self.market_analyses),
                "total_correlations": len(self.correlation_analyses),
                "symbol_coverage": list(self.market_data.keys()),
                "analysis_types": [analysis.analysis_type.value for analysis in self.market_analyses[-10:]],
                "recent_trends": [analysis.trend.value for analysis in self.market_analyses[-10:]],
                "average_confidence": round(statistics.mean([a.confidence for a in self.market_analyses]) if self.market_analyses else 0, 2)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取分析器统计失败: {e}")
            return {}


# 生成模拟市场数据的辅助函数
def generate_sample_market_data(analyzer: MarketDataAnalyzer, count: int = 100):
    """生成示例市场数据"""
    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"]
    exchanges = ["binance", "okx", "coinbase", "kraken"]
    
    base_time = datetime.now() - timedelta(hours=count)
    
    # 为每个交易对生成基础价格
    base_prices = {
        "BTC/USDT": 45000,
        "ETH/USDT": 2800,
        "BNB/USDT": 320,
        "SOL/USDT": 110,
        "XRP/USDT": 0.52,
        "ADA/USDT": 0.45,
        "DOGE/USDT": 0.08
    }
    
    for i in range(count):
        for symbol in symbols:
            timestamp = base_time + timedelta(hours=i)
            base_price = base_prices[symbol]
            
            # 生成随机价格波动
            price_change = random.uniform(-0.05, 0.05)  # ±5%波动
            current_price = base_price * (1 + price_change)
            
            # 生成OHLC数据
            volatility = random.uniform(0.01, 0.03)
            high_price = current_price * (1 + volatility)
            low_price = current_price * (1 - volatility)
            open_price = random.uniform(low_price, high_price)
            close_price = current_price
            
            # 生成交易量
            base_volume = random.uniform(1000, 10000)
            volume = base_volume * random.uniform(0.5, 2.0)
            
            data_point = MarketDataPoint(
                symbol=symbol,
                timestamp=timestamp,
                open_price=round(open_price, 2),
                high_price=round(high_price, 2),
                low_price=round(low_price, 2),
                close_price=round(close_price, 2),
                volume=round(volume, 2),
                exchange=random.choice(exchanges),
                timeframe="1h"
            )
            
            analyzer.add_market_data(data_point)
            
            # 更新基础价格（模拟价格演变）
            base_prices[symbol] = close_price
    
    # 执行一些综合分析
    for symbol in symbols[:3]:  # 对前3个交易对进行分析
        analyzer.perform_comprehensive_analysis(symbol)