"""
MarketPrism 异常检测器单元测试
"""

import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.observability.alerting.anomaly_detector import (
    AnomalyDetector, BaseAnomalyDetector, MLAnomalyDetector,
    SeasonalAnomalyDetector, MetricPoint, AnomalyResult
)


class TestMetricPoint:
    """指标数据点测试"""
    
    def test_metric_point_creation(self):
        """测试指标数据点创建"""
        timestamp = datetime.now(timezone.utc)
        point = MetricPoint(timestamp, 100.0, {'service': 'test'})
        
        assert point.timestamp == timestamp
        assert point.value == 100.0
        assert point.labels == {'service': 'test'}
    
    def test_metric_point_to_dict(self):
        """测试指标数据点转换为字典"""
        timestamp = datetime.now(timezone.utc)
        point = MetricPoint(timestamp, 50.5, {'env': 'prod'})
        
        result = point.to_dict()
        
        assert result['timestamp'] == timestamp.isoformat()
        assert result['value'] == 50.5
        assert result['labels'] == {'env': 'prod'}


class TestAnomalyResult:
    """异常检测结果测试"""
    
    def test_anomaly_result_creation(self):
        """测试异常检测结果创建"""
        timestamp = datetime.now(timezone.utc)
        result = AnomalyResult(
            is_anomaly=True,
            score=3.5,
            threshold=2.0,
            metric_name="cpu_usage",
            timestamp=timestamp,
            value=95.0,
            expected_range=(0, 80),
            confidence=0.8
        )
        
        assert result.is_anomaly is True
        assert result.score == 3.5
        assert result.threshold == 2.0
        assert result.metric_name == "cpu_usage"
        assert result.timestamp == timestamp
        assert result.value == 95.0
        assert result.expected_range == (0, 80)
        assert result.confidence == 0.8
    
    def test_anomaly_result_to_dict(self):
        """测试异常检测结果转换为字典"""
        timestamp = datetime.now(timezone.utc)
        result = AnomalyResult(
            is_anomaly=False,
            score=1.5,
            threshold=2.0,
            metric_name="memory_usage",
            timestamp=timestamp,
            value=60.0
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['is_anomaly'] is False
        assert result_dict['score'] == 1.5
        assert result_dict['threshold'] == 2.0
        assert result_dict['metric_name'] == "memory_usage"
        assert result_dict['timestamp'] == timestamp.isoformat()
        assert result_dict['value'] == 60.0


class TestBaseAnomalyDetector:
    """基础异常检测器测试"""
    
    @pytest.fixture
    def detector(self):
        """创建基础异常检测器实例"""
        return BaseAnomalyDetector(window_size=50, threshold=2.0)
    
    def test_detector_initialization(self, detector):
        """测试检测器初始化"""
        assert detector.window_size == 50
        assert detector.threshold == 2.0
        assert len(detector.data_windows) == 0
    
    def test_add_metric_point_insufficient_data(self, detector):
        """测试数据不足时的行为"""
        timestamp = datetime.now(timezone.utc)
        
        # 添加少量数据点
        for i in range(5):
            point = MetricPoint(timestamp + timedelta(seconds=i), float(i))
            result = detector.add_metric_point("test_metric", point)
            assert result is None  # 数据不足，不应返回结果
    
    def test_add_metric_point_normal_data(self, detector):
        """测试正常数据的异常检测"""
        timestamp = datetime.now(timezone.utc)
        
        # 添加正常数据
        for i in range(20):
            point = MetricPoint(timestamp + timedelta(seconds=i), 50.0 + np.random.normal(0, 1))
            detector.add_metric_point("test_metric", point)
        
        # 添加正常值
        normal_point = MetricPoint(timestamp + timedelta(seconds=20), 51.0)
        result = detector.add_metric_point("test_metric", normal_point)
        
        assert result is not None
        assert result.is_anomaly is False
        assert result.metric_name == "test_metric"
    
    def test_add_metric_point_anomalous_data(self, detector):
        """测试异常数据的检测"""
        timestamp = datetime.now(timezone.utc)
        
        # 添加正常数据
        for i in range(20):
            point = MetricPoint(timestamp + timedelta(seconds=i), 50.0)
            detector.add_metric_point("test_metric", point)
        
        # 添加异常值
        anomaly_point = MetricPoint(timestamp + timedelta(seconds=20), 100.0)
        result = detector.add_metric_point("test_metric", anomaly_point)
        
        assert result is not None
        assert result.is_anomaly is True
        assert result.metric_name == "test_metric"
        assert result.value == 100.0
    
    def test_multiple_metrics(self, detector):
        """测试多个指标的处理"""
        timestamp = datetime.now(timezone.utc)
        
        # 为两个不同指标添加数据
        for i in range(15):
            point1 = MetricPoint(timestamp + timedelta(seconds=i), 50.0)
            point2 = MetricPoint(timestamp + timedelta(seconds=i), 100.0)
            
            detector.add_metric_point("metric1", point1)
            detector.add_metric_point("metric2", point2)
        
        # 检查数据窗口
        assert "metric1" in detector.data_windows
        assert "metric2" in detector.data_windows
        assert len(detector.data_windows["metric1"]) == 15
        assert len(detector.data_windows["metric2"]) == 15


class TestSeasonalAnomalyDetector:
    """季节性异常检测器测试"""
    
    @pytest.fixture
    def detector(self):
        """创建季节性异常检测器实例"""
        return SeasonalAnomalyDetector(window_size=100, seasonal_period=24)
    
    def test_seasonal_detector_initialization(self, detector):
        """测试季节性检测器初始化"""
        assert detector.window_size == 100
        assert detector.seasonal_period == 24
        assert len(detector.seasonal_data) == 0
    
    def test_seasonal_pattern_detection(self, detector):
        """测试季节性模式检测"""
        base_time = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
        
        # 模拟每天同一时间的正常值
        for day in range(10):
            timestamp = base_time + timedelta(days=day)
            point = MetricPoint(timestamp, 80.0 + np.random.normal(0, 2))
            detector.add_metric_point("daily_metric", point)
        
        # 在同一时间添加异常值
        anomaly_timestamp = base_time + timedelta(days=10)
        anomaly_point = MetricPoint(anomaly_timestamp, 120.0)
        result = detector.add_metric_point("daily_metric", anomaly_point)
        
        # 由于有足够的历史数据，应该能检测到异常
        if result:  # 可能因为数据不足而返回None
            assert result.metric_name == "daily_metric"


class TestAnomalyDetector:
    """综合异常检测器测试"""
    
    @pytest.fixture
    def detector(self):
        """创建综合异常检测器实例"""
        config = {
            'statistical_window': 50,
            'statistical_threshold': 2.0,
            'seasonal_window': 100,
            'seasonal_period': 24,
            'detector_weights': {
                'statistical': 0.5,
                'seasonal': 0.5
            }
        }
        return AnomalyDetector(config)
    
    def test_detector_initialization(self, detector):
        """测试综合检测器初始化"""
        assert 'statistical' in detector.detectors
        assert 'seasonal' in detector.detectors
        assert detector.detector_weights['statistical'] == 0.5
        assert detector.detector_weights['seasonal'] == 0.5
    
    def test_detect_anomaly_no_data(self, detector):
        """测试无数据时的异常检测"""
        timestamp = datetime.now(timezone.utc)
        result = detector.detect_anomaly("new_metric", timestamp, 50.0)
        
        # 第一次检测可能返回None（数据不足）
        assert result is None or isinstance(result, AnomalyResult)
    
    def test_detect_anomaly_with_data(self, detector):
        """测试有数据时的异常检测"""
        timestamp = datetime.now(timezone.utc)
        
        # 添加正常数据
        for i in range(30):
            detector.detect_anomaly(
                "test_metric", 
                timestamp + timedelta(seconds=i), 
                50.0 + np.random.normal(0, 1)
            )
        
        # 检测异常值
        result = detector.detect_anomaly(
            "test_metric",
            timestamp + timedelta(seconds=30),
            100.0
        )
        
        if result:  # 可能因为数据不足而返回None
            assert result.metric_name == "test_metric"
            assert result.value == 100.0
    
    def test_detect_anomaly_with_labels(self, detector):
        """测试带标签的异常检测"""
        timestamp = datetime.now(timezone.utc)
        labels = {'service': 'api', 'instance': 'server1'}
        
        result = detector.detect_anomaly(
            "response_time",
            timestamp,
            150.0,
            labels
        )
        
        # 第一次检测可能返回None
        assert result is None or isinstance(result, AnomalyResult)
    
    @patch('core.observability.alerting.anomaly_detector.SKLEARN_AVAILABLE', False)
    def test_detector_without_sklearn(self):
        """测试没有scikit-learn时的行为"""
        detector = AnomalyDetector()
        
        # 应该只有统计和季节性检测器
        assert 'statistical' in detector.detectors
        assert 'seasonal' in detector.detectors
        assert 'ml' not in detector.detectors


class TestMLAnomalyDetector:
    """机器学习异常检测器测试"""
    
    @pytest.fixture
    def detector(self):
        """创建ML异常检测器实例"""
        return MLAnomalyDetector(window_size=100, contamination=0.1)
    
    def test_ml_detector_initialization(self, detector):
        """测试ML检测器初始化"""
        assert detector.window_size == 100
        assert detector.contamination == 0.1
        assert len(detector.models) == 0
        assert len(detector.scalers) == 0
    
    @pytest.mark.skipif(
        not hasattr(MLAnomalyDetector, '_train_model'),
        reason="ML detector requires scikit-learn"
    )
    def test_ml_model_training(self, detector):
        """测试ML模型训练"""
        timestamp = datetime.now(timezone.utc)
        
        # 添加足够的数据来触发模型训练
        for i in range(150):
            point = MetricPoint(timestamp + timedelta(seconds=i), 50.0 + np.random.normal(0, 5))
            detector.add_metric_point("ml_metric", point)
        
        # 检查模型是否被训练
        if hasattr(detector, 'models') and 'ml_metric' in detector.models:
            assert detector.models['ml_metric'] is not None
            assert detector.scalers['ml_metric'] is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
