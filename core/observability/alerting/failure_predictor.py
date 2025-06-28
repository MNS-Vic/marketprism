"""
MarketPrism 故障预测机制

基于历史数据和趋势分析的智能故障预测系统
"""

import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, NamedTuple
from dataclasses import dataclass
from enum import Enum
import structlog

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.metrics import mean_squared_error
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


logger = structlog.get_logger(__name__)


class PredictionType(str, Enum):
    """预测类型"""
    MEMORY_LEAK = "memory_leak"
    DISK_FULL = "disk_full"
    CONNECTION_EXHAUSTION = "connection_exhaustion"
    CPU_OVERLOAD = "cpu_overload"
    RESPONSE_TIME_DEGRADATION = "response_time_degradation"
    ERROR_RATE_INCREASE = "error_rate_increase"
    THROUGHPUT_DECLINE = "throughput_decline"


class PredictionSeverity(str, Enum):
    """预测严重程度"""
    LOW = "low"          # 7天内可能发生
    MEDIUM = "medium"    # 3天内可能发生
    HIGH = "high"        # 1天内可能发生
    CRITICAL = "critical" # 6小时内可能发生


@dataclass
class TrendPoint:
    """趋势数据点"""
    timestamp: datetime
    value: float
    metric_name: str
    labels: Dict[str, str] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = {}


@dataclass
class PredictionResult:
    """预测结果"""
    prediction_type: PredictionType
    severity: PredictionSeverity
    confidence: float  # 0-1之间的置信度
    time_to_failure: timedelta  # 预计故障时间
    current_value: float
    predicted_value: float
    threshold: float
    metric_name: str
    description: str
    recommendations: List[str]
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'prediction_type': self.prediction_type.value,
            'severity': self.severity.value,
            'confidence': self.confidence,
            'time_to_failure_hours': self.time_to_failure.total_seconds() / 3600,
            'current_value': self.current_value,
            'predicted_value': self.predicted_value,
            'threshold': self.threshold,
            'metric_name': self.metric_name,
            'description': self.description,
            'recommendations': self.recommendations,
            'created_at': self.created_at.isoformat()
        }


class TrendAnalyzer:
    """趋势分析器"""
    
    def __init__(self, window_size: int = 1440):  # 24小时窗口
        self.window_size = window_size
        self.data_windows: Dict[str, List[TrendPoint]] = {}
    
    def add_data_point(self, metric_name: str, timestamp: datetime, value: float, 
                      labels: Dict[str, str] = None) -> None:
        """添加数据点"""
        point = TrendPoint(timestamp, value, metric_name, labels)
        
        if metric_name not in self.data_windows:
            self.data_windows[metric_name] = []
        
        self.data_windows[metric_name].append(point)
        
        # 保持窗口大小
        if len(self.data_windows[metric_name]) > self.window_size:
            self.data_windows[metric_name] = self.data_windows[metric_name][-self.window_size:]
    
    def calculate_trend(self, metric_name: str, hours: int = 24) -> Optional[Dict[str, float]]:
        """计算趋势"""
        if metric_name not in self.data_windows:
            return None
        
        data = self.data_windows[metric_name]
        if len(data) < 10:  # 需要足够的数据点
            return None
        
        # 获取指定时间范围内的数据
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_data = [p for p in data if p.timestamp > cutoff_time]
        
        if len(recent_data) < 5:
            return None
        
        # 计算趋势
        timestamps = np.array([(p.timestamp - recent_data[0].timestamp).total_seconds() 
                              for p in recent_data])
        values = np.array([p.value for p in recent_data])
        
        # 线性回归
        if SKLEARN_AVAILABLE:
            model = LinearRegression()
            X = timestamps.reshape(-1, 1)
            model.fit(X, values)
            
            slope = model.coef_[0]
            intercept = model.intercept_
            r_squared = model.score(X, values)
        else:
            # 简单线性回归
            n = len(timestamps)
            sum_x = np.sum(timestamps)
            sum_y = np.sum(values)
            sum_xy = np.sum(timestamps * values)
            sum_x2 = np.sum(timestamps ** 2)
            
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
            intercept = (sum_y - slope * sum_x) / n
            
            # 计算R²
            y_pred = slope * timestamps + intercept
            ss_res = np.sum((values - y_pred) ** 2)
            ss_tot = np.sum((values - np.mean(values)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        
        return {
            'slope': slope,
            'intercept': intercept,
            'r_squared': r_squared,
            'current_value': recent_data[-1].value,
            'trend_direction': 'increasing' if slope > 0 else 'decreasing' if slope < 0 else 'stable'
        }
    
    def predict_future_value(self, metric_name: str, hours_ahead: int) -> Optional[float]:
        """预测未来值"""
        trend = self.calculate_trend(metric_name)
        if not trend:
            return None
        
        # 预测未来值
        seconds_ahead = hours_ahead * 3600
        predicted_value = trend['current_value'] + trend['slope'] * seconds_ahead
        
        return predicted_value


class FailurePredictor:
    """故障预测器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.trend_analyzer = TrendAnalyzer(
            window_size=self.config.get('window_size', 1440)
        )
        
        # 预测规则配置
        self.prediction_rules = self._load_prediction_rules()
        
        # 历史预测结果
        self.prediction_history: List[PredictionResult] = []
        
        logger.info("故障预测器初始化完成")
    
    def _load_prediction_rules(self) -> Dict[str, Dict[str, Any]]:
        """加载预测规则"""
        return {
            'memory_usage': {
                'type': PredictionType.MEMORY_LEAK,
                'threshold': 0.9,  # 90%内存使用率
                'trend_threshold': 0.01,  # 每小时增长1%
                'min_confidence': 0.7,
                'description': '内存使用率持续增长，可能存在内存泄漏',
                'recommendations': [
                    '检查应用程序内存使用情况',
                    '分析内存泄漏点',
                    '考虑重启服务释放内存',
                    '增加内存监控告警'
                ]
            },
            'disk_usage': {
                'type': PredictionType.DISK_FULL,
                'threshold': 0.95,  # 95%磁盘使用率
                'trend_threshold': 0.02,  # 每小时增长2%
                'min_confidence': 0.8,
                'description': '磁盘使用率快速增长，可能导致磁盘空间耗尽',
                'recommendations': [
                    '清理临时文件和日志',
                    '检查大文件占用',
                    '配置日志轮转',
                    '考虑扩容磁盘空间'
                ]
            },
            'connection_count': {
                'type': PredictionType.CONNECTION_EXHAUSTION,
                'threshold': 0.85,  # 85%连接池使用率
                'trend_threshold': 0.05,  # 每小时增长5%
                'min_confidence': 0.6,
                'description': '连接数持续增长，可能导致连接池耗尽',
                'recommendations': [
                    '检查连接泄漏',
                    '优化连接池配置',
                    '增加连接池大小',
                    '实施连接限流'
                ]
            },
            'cpu_usage': {
                'type': PredictionType.CPU_OVERLOAD,
                'threshold': 0.8,  # 80%CPU使用率
                'trend_threshold': 0.03,  # 每小时增长3%
                'min_confidence': 0.7,
                'description': 'CPU使用率持续上升，可能导致性能问题',
                'recommendations': [
                    '分析CPU密集型任务',
                    '优化算法和代码',
                    '考虑水平扩展',
                    '实施负载均衡'
                ]
            },
            'response_time': {
                'type': PredictionType.RESPONSE_TIME_DEGRADATION,
                'threshold': 5000,  # 5秒响应时间
                'trend_threshold': 100,  # 每小时增长100ms
                'min_confidence': 0.6,
                'description': '响应时间持续增长，服务性能下降',
                'recommendations': [
                    '检查数据库查询性能',
                    '优化缓存策略',
                    '分析慢请求',
                    '考虑服务拆分'
                ]
            },
            'error_rate': {
                'type': PredictionType.ERROR_RATE_INCREASE,
                'threshold': 0.05,  # 5%错误率
                'trend_threshold': 0.001,  # 每小时增长0.1%
                'min_confidence': 0.8,
                'description': '错误率持续上升，服务稳定性下降',
                'recommendations': [
                    '分析错误日志',
                    '检查依赖服务状态',
                    '实施熔断机制',
                    '增加重试逻辑'
                ]
            }
        }
    
    def add_metric_data(self, metric_name: str, timestamp: datetime, value: float,
                       labels: Dict[str, str] = None) -> None:
        """添加指标数据"""
        self.trend_analyzer.add_data_point(metric_name, timestamp, value, labels)
    
    def predict_failures(self) -> List[PredictionResult]:
        """预测故障"""
        predictions = []
        
        for metric_name, rule in self.prediction_rules.items():
            try:
                prediction = self._predict_single_metric(metric_name, rule)
                if prediction:
                    predictions.append(prediction)
            except Exception as e:
                logger.error("故障预测失败", metric_name=metric_name, error=str(e))
        
        # 保存预测历史
        self.prediction_history.extend(predictions)
        
        # 清理旧的预测历史
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
        self.prediction_history = [
            p for p in self.prediction_history if p.created_at > cutoff_time
        ]
        
        return predictions
    
    def _predict_single_metric(self, metric_name: str, rule: Dict[str, Any]) -> Optional[PredictionResult]:
        """预测单个指标的故障"""
        # 计算趋势
        trend = self.trend_analyzer.calculate_trend(metric_name)
        if not trend:
            return None
        
        current_value = trend['current_value']
        slope = trend['slope']
        r_squared = trend['r_squared']
        
        # 检查趋势是否显著
        if abs(slope) < rule['trend_threshold'] or r_squared < rule['min_confidence']:
            return None
        
        # 预测何时达到阈值
        threshold = rule['threshold']
        if slope <= 0:
            return None  # 趋势不是向阈值方向发展
        
        # 计算到达阈值的时间
        time_to_threshold = (threshold - current_value) / slope  # 秒
        if time_to_threshold <= 0:
            time_to_threshold = 0  # 已经超过阈值
        
        time_to_failure = timedelta(seconds=time_to_threshold)
        
        # 只预测未来7天内的故障
        if time_to_failure > timedelta(days=7):
            return None
        
        # 确定严重程度
        if time_to_failure <= timedelta(hours=6):
            severity = PredictionSeverity.CRITICAL
        elif time_to_failure <= timedelta(days=1):
            severity = PredictionSeverity.HIGH
        elif time_to_failure <= timedelta(days=3):
            severity = PredictionSeverity.MEDIUM
        else:
            severity = PredictionSeverity.LOW
        
        # 预测未来值
        hours_ahead = min(time_to_failure.total_seconds() / 3600, 168)  # 最多预测7天
        predicted_value = self.trend_analyzer.predict_future_value(metric_name, int(hours_ahead))
        
        return PredictionResult(
            prediction_type=rule['type'],
            severity=severity,
            confidence=r_squared,
            time_to_failure=time_to_failure,
            current_value=current_value,
            predicted_value=predicted_value or threshold,
            threshold=threshold,
            metric_name=metric_name,
            description=rule['description'],
            recommendations=rule['recommendations']
        )
    
    def get_capacity_planning_recommendations(self) -> List[Dict[str, Any]]:
        """获取容量规划建议"""
        recommendations = []
        
        # 分析各个指标的增长趋势
        for metric_name in ['memory_usage', 'disk_usage', 'cpu_usage', 'connection_count']:
            trend = self.trend_analyzer.calculate_trend(metric_name, hours=168)  # 7天趋势
            if not trend:
                continue
            
            if trend['slope'] > 0 and trend['r_squared'] > 0.5:
                # 计算未来30天的预测值
                future_value = self.trend_analyzer.predict_future_value(metric_name, 24 * 30)
                if future_value:
                    growth_rate = (future_value - trend['current_value']) / trend['current_value']
                    
                    if growth_rate > 0.5:  # 30天内增长超过50%
                        recommendations.append({
                            'metric': metric_name,
                            'current_value': trend['current_value'],
                            'predicted_value': future_value,
                            'growth_rate': growth_rate,
                            'recommendation': f'{metric_name}在未来30天内预计增长{growth_rate:.1%}，建议提前规划容量扩展',
                            'priority': 'high' if growth_rate > 1.0 else 'medium'
                        })
        
        return recommendations
    
    def get_prediction_accuracy(self) -> Dict[str, float]:
        """获取预测准确性统计"""
        if not self.prediction_history:
            return {}
        
        # 分析历史预测的准确性
        accuracy_stats = {}
        
        for prediction_type in PredictionType:
            type_predictions = [
                p for p in self.prediction_history 
                if p.prediction_type == prediction_type
            ]
            
            if type_predictions:
                # 简单的准确性计算（这里可以根据实际情况完善）
                avg_confidence = np.mean([p.confidence for p in type_predictions])
                accuracy_stats[prediction_type.value] = avg_confidence
        
        return accuracy_stats
