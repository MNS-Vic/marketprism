"""
MarketPrism 异常检测模块

基于机器学习的智能异常检测系统
"""

import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import deque
import structlog

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import DBSCAN
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    structlog.get_logger(__name__).warning("scikit-learn不可用，将使用基础异常检测")


logger = structlog.get_logger(__name__)


class MetricPoint:
    """指标数据点"""
    
    def __init__(self, timestamp: datetime, value: float, labels: Dict[str, str] = None):
        self.timestamp = timestamp
        self.value = value
        self.labels = labels or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'value': self.value,
            'labels': self.labels
        }


class AnomalyResult:
    """异常检测结果"""
    
    def __init__(
        self,
        is_anomaly: bool,
        score: float,
        threshold: float,
        metric_name: str,
        timestamp: datetime,
        value: float,
        expected_range: Optional[Tuple[float, float]] = None,
        confidence: float = 0.0
    ):
        self.is_anomaly = is_anomaly
        self.score = score
        self.threshold = threshold
        self.metric_name = metric_name
        self.timestamp = timestamp
        self.value = value
        self.expected_range = expected_range
        self.confidence = confidence
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'is_anomaly': self.is_anomaly,
            'score': self.score,
            'threshold': self.threshold,
            'metric_name': self.metric_name,
            'timestamp': self.timestamp.isoformat(),
            'value': self.value,
            'expected_range': self.expected_range,
            'confidence': self.confidence
        }


class BaseAnomalyDetector:
    """基础异常检测器"""
    
    def __init__(self, window_size: int = 100, threshold: float = 2.0):
        self.window_size = window_size
        self.threshold = threshold
        self.data_windows: Dict[str, deque] = {}
        
    def add_metric_point(self, metric_name: str, point: MetricPoint) -> Optional[AnomalyResult]:
        """添加指标数据点并检测异常"""
        if metric_name not in self.data_windows:
            self.data_windows[metric_name] = deque(maxlen=self.window_size)
        
        window = self.data_windows[metric_name]
        window.append(point)
        
        # 需要足够的历史数据才能检测异常
        if len(window) < 10:
            return None
        
        return self._detect_anomaly(metric_name, point, window)
    
    def _detect_anomaly(self, metric_name: str, point: MetricPoint, window: deque) -> AnomalyResult:
        """检测异常（基于统计方法）"""
        values = [p.value for p in window]
        
        # 计算统计指标
        mean = np.mean(values[:-1])  # 排除当前点
        std = np.std(values[:-1])
        
        # Z-score异常检测
        if std > 0:
            z_score = abs(point.value - mean) / std
            is_anomaly = z_score > self.threshold
            expected_range = (mean - self.threshold * std, mean + self.threshold * std)
        else:
            z_score = 0
            is_anomaly = False
            expected_range = (mean, mean)
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=z_score,
            threshold=self.threshold,
            metric_name=metric_name,
            timestamp=point.timestamp,
            value=point.value,
            expected_range=expected_range,
            confidence=min(z_score / self.threshold, 1.0) if is_anomaly else 0.0
        )


class MLAnomalyDetector(BaseAnomalyDetector):
    """基于机器学习的异常检测器"""
    
    def __init__(self, window_size: int = 200, contamination: float = 0.1):
        super().__init__(window_size)
        self.contamination = contamination
        self.models: Dict[str, IsolationForest] = {}
        self.scalers: Dict[str, StandardScaler] = {}
        self.retrain_interval = 100  # 每100个数据点重新训练
        self.point_counts: Dict[str, int] = {}
        
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn不可用，回退到基础异常检测")
    
    def _detect_anomaly(self, metric_name: str, point: MetricPoint, window: deque) -> AnomalyResult:
        """使用机器学习检测异常"""
        if not SKLEARN_AVAILABLE:
            return super()._detect_anomaly(metric_name, point, window)
        
        # 准备训练数据
        values = np.array([p.value for p in window]).reshape(-1, 1)
        
        # 检查是否需要重新训练模型
        if (metric_name not in self.models or 
            self.point_counts.get(metric_name, 0) % self.retrain_interval == 0):
            self._train_model(metric_name, values)
        
        self.point_counts[metric_name] = self.point_counts.get(metric_name, 0) + 1
        
        # 预测异常
        model = self.models.get(metric_name)
        scaler = self.scalers.get(metric_name)
        
        if model is None or scaler is None:
            return super()._detect_anomaly(metric_name, point, window)
        
        # 标准化当前值
        current_value = np.array([[point.value]])
        scaled_value = scaler.transform(current_value)
        
        # 预测
        prediction = model.predict(scaled_value)[0]
        anomaly_score = model.decision_function(scaled_value)[0]
        
        is_anomaly = prediction == -1
        
        # 计算期望范围（基于历史数据）
        historical_values = values[:-1]
        mean = np.mean(historical_values)
        std = np.std(historical_values)
        expected_range = (mean - 2 * std, mean + 2 * std)
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=abs(anomaly_score),
            threshold=0.0,  # Isolation Forest没有固定阈值
            metric_name=metric_name,
            timestamp=point.timestamp,
            value=point.value,
            expected_range=expected_range,
            confidence=abs(anomaly_score) if is_anomaly else 0.0
        )
    
    def _train_model(self, metric_name: str, values: np.ndarray) -> None:
        """训练异常检测模型"""
        try:
            # 标准化数据
            scaler = StandardScaler()
            scaled_values = scaler.fit_transform(values)
            
            # 训练Isolation Forest模型
            model = IsolationForest(
                contamination=self.contamination,
                random_state=42,
                n_estimators=100
            )
            model.fit(scaled_values)
            
            # 保存模型和标准化器
            self.models[metric_name] = model
            self.scalers[metric_name] = scaler
            
            logger.debug("异常检测模型训练完成", metric_name=metric_name, samples=len(values))
            
        except Exception as e:
            logger.error("异常检测模型训练失败", error=str(e), metric_name=metric_name)


class SeasonalAnomalyDetector(BaseAnomalyDetector):
    """季节性异常检测器"""
    
    def __init__(self, window_size: int = 1440, seasonal_period: int = 1440):  # 默认24小时周期
        super().__init__(window_size)
        self.seasonal_period = seasonal_period
        self.seasonal_data: Dict[str, Dict[int, List[float]]] = {}
    
    def _detect_anomaly(self, metric_name: str, point: MetricPoint, window: deque) -> AnomalyResult:
        """基于季节性模式检测异常"""
        # 获取当前时间在周期中的位置
        hour_of_day = point.timestamp.hour
        minute_of_hour = point.timestamp.minute
        time_index = hour_of_day * 60 + minute_of_hour  # 一天中的分钟数
        
        # 初始化季节性数据
        if metric_name not in self.seasonal_data:
            self.seasonal_data[metric_name] = {}
        
        seasonal_data = self.seasonal_data[metric_name]
        
        # 收集同一时间点的历史数据
        if time_index not in seasonal_data:
            seasonal_data[time_index] = []
        
        seasonal_data[time_index].append(point.value)
        
        # 保持数据窗口大小
        if len(seasonal_data[time_index]) > 30:  # 保留最近30天的数据
            seasonal_data[time_index] = seasonal_data[time_index][-30:]
        
        # 需要足够的历史数据
        if len(seasonal_data[time_index]) < 7:  # 至少7天数据
            return super()._detect_anomaly(metric_name, point, window)
        
        # 计算季节性期望值
        historical_values = seasonal_data[time_index][:-1]  # 排除当前值
        mean = np.mean(historical_values)
        std = np.std(historical_values)
        
        # 季节性异常检测
        if std > 0:
            z_score = abs(point.value - mean) / std
            is_anomaly = z_score > self.threshold
            expected_range = (mean - self.threshold * std, mean + self.threshold * std)
        else:
            z_score = 0
            is_anomaly = False
            expected_range = (mean, mean)
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=z_score,
            threshold=self.threshold,
            metric_name=metric_name,
            timestamp=point.timestamp,
            value=point.value,
            expected_range=expected_range,
            confidence=min(z_score / self.threshold, 1.0) if is_anomaly else 0.0
        )


class AnomalyDetector:
    """综合异常检测器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # 初始化不同类型的检测器
        self.detectors = {
            'statistical': BaseAnomalyDetector(
                window_size=self.config.get('statistical_window', 100),
                threshold=self.config.get('statistical_threshold', 2.0)
            ),
            'seasonal': SeasonalAnomalyDetector(
                window_size=self.config.get('seasonal_window', 1440),
                seasonal_period=self.config.get('seasonal_period', 1440)
            )
        }
        
        # 如果可用，添加ML检测器
        if SKLEARN_AVAILABLE:
            self.detectors['ml'] = MLAnomalyDetector(
                window_size=self.config.get('ml_window', 200),
                contamination=self.config.get('ml_contamination', 0.1)
            )
        
        # 检测器权重
        self.detector_weights = self.config.get('detector_weights', {
            'statistical': 0.3,
            'seasonal': 0.4,
            'ml': 0.3
        })
        
        logger.info("异常检测器初始化完成", detectors=list(self.detectors.keys()))
    
    def detect_anomaly(self, metric_name: str, timestamp: datetime, value: float, 
                      labels: Dict[str, str] = None) -> Optional[AnomalyResult]:
        """综合异常检测"""
        point = MetricPoint(timestamp, value, labels)
        
        # 使用所有检测器
        results = []
        for detector_name, detector in self.detectors.items():
            try:
                result = detector.add_metric_point(metric_name, point)
                if result:
                    results.append((detector_name, result))
            except Exception as e:
                logger.error("异常检测器执行失败", 
                           detector=detector_name, 
                           error=str(e), 
                           metric_name=metric_name)
        
        if not results:
            return None
        
        # 综合多个检测器的结果
        return self._combine_results(results, metric_name, timestamp, value)
    
    def _combine_results(self, results: List[Tuple[str, AnomalyResult]], 
                        metric_name: str, timestamp: datetime, value: float) -> AnomalyResult:
        """综合多个检测器的结果"""
        if len(results) == 1:
            return results[0][1]
        
        # 加权投票
        weighted_score = 0.0
        total_weight = 0.0
        anomaly_votes = 0
        confidence_sum = 0.0
        
        for detector_name, result in results:
            weight = self.detector_weights.get(detector_name, 1.0)
            weighted_score += result.score * weight
            total_weight += weight
            
            if result.is_anomaly:
                anomaly_votes += weight
            
            confidence_sum += result.confidence * weight
        
        # 计算综合结果
        avg_score = weighted_score / total_weight if total_weight > 0 else 0.0
        avg_confidence = confidence_sum / total_weight if total_weight > 0 else 0.0
        is_anomaly = anomaly_votes > (total_weight / 2)  # 超过一半权重认为是异常
        
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=avg_score,
            threshold=2.0,  # 综合阈值
            metric_name=metric_name,
            timestamp=timestamp,
            value=value,
            confidence=avg_confidence
        )
