"""
📊 MarketPrism 异常检测管理器
整合自 Week 7 Day 4 SLO异常管理器

创建时间: 2025-06-01 23:11:02
来源: week7_day4_slo_anomaly_manager.py
整合到: core/monitoring/observability/
"""

from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
import statistics

# 异常类型
class AnomalyType(Enum):
    SPIKE = "spike"              # 尖峰异常
    DROP = "drop"                # 下降异常
    TREND = "trend"              # 趋势异常
    SEASONAL = "seasonal"        # 季节性异常

@dataclass
class AnomalyDetection:
    """异常检测结果"""
    metric_name: str
    anomaly_type: AnomalyType
    severity: float
    timestamp: datetime
    details: Dict[str, Any]

class AnomalyDetectionManager:
    """
    📊 异常检测管理器
    
    整合自Week 7 Day 4的SLO异常管理系统，
    提供智能的异常检测和分析能力。
    """
    
    def __init__(self):
        self.metric_history = {}
        self.anomaly_history = []
        self.detection_rules = {}
        self.thresholds = {}
    
    def add_metric_data(self, metric_name: str, value: float, timestamp: datetime = None) -> None:
        """添加指标数据"""
        if timestamp is None:
            timestamp = datetime.now()
        
        if metric_name not in self.metric_history:
            self.metric_history[metric_name] = []
        
        self.metric_history[metric_name].append((timestamp, value))
        
        # 保持最近1000个数据点
        if len(self.metric_history[metric_name]) > 1000:
            self.metric_history[metric_name] = self.metric_history[metric_name][-1000:]
        
        # 检测异常
        self._detect_anomalies(metric_name, value, timestamp)
    
    def _detect_anomalies(self, metric_name: str, current_value: float, timestamp: datetime) -> None:
        """检测异常"""
        if metric_name not in self.metric_history:
            return
        
        history = self.metric_history[metric_name]
        if len(history) < 10:  # 需要足够的历史数据
            return
        
        # 简单的统计异常检测
        recent_values = [v for t, v in history[-20:]]  # 最近20个值
        mean_value = statistics.mean(recent_values)
        std_value = statistics.stdev(recent_values) if len(recent_values) > 1 else 0
        
        # Z-score异常检测
        if std_value > 0:
            z_score = abs(current_value - mean_value) / std_value
            
            if z_score > 3:  # 3σ规则
                anomaly_type = AnomalyType.SPIKE if current_value > mean_value else AnomalyType.DROP
                
                anomaly = AnomalyDetection(
                    metric_name=metric_name,
                    anomaly_type=anomaly_type,
                    severity=min(z_score / 3, 1.0),  # 标准化严重程度
                    timestamp=timestamp,
                    details={
                        "current_value": current_value,
                        "mean_value": mean_value,
                        "std_value": std_value,
                        "z_score": z_score
                    }
                )
                
                self.anomaly_history.append(anomaly)
                self._trigger_anomaly_alert(anomaly)
    
    def _trigger_anomaly_alert(self, anomaly: AnomalyDetection) -> None:
        """触发异常告警"""
        # 与告警系统集成
        try:
            from ..alerting.enhanced_alerting_engine import get_alerting_engine
            
            alerting_engine = get_alerting_engine()
            message = f"异常检测: {anomaly.metric_name} 发现{anomaly.anomaly_type.value}异常"
            
            alerting_engine.trigger_alert(
                rule_name=f"anomaly_{anomaly.metric_name}",
                message=message,
                metadata={
                    "anomaly_type": anomaly.anomaly_type.value,
                    "severity": anomaly.severity,
                    "details": anomaly.details
                }
            )
        except ImportError:
            print(f"⚠️ 告警系统未可用，异常信息: {message}")
    
    def get_anomalies(self, metric_name: str = None, hours: int = 24) -> List[AnomalyDetection]:
        """获取异常记录"""
        since = datetime.now() - timedelta(hours=hours)
        
        anomalies = [a for a in self.anomaly_history if a.timestamp >= since]
        
        if metric_name:
            anomalies = [a for a in anomalies if a.metric_name == metric_name]
        
        return anomalies
    
    def set_detection_threshold(self, metric_name: str, threshold: float) -> None:
        """设置检测阈值"""
        self.thresholds[metric_name] = threshold

# 全局异常检测管理器
_global_anomaly_manager = None

def get_anomaly_manager() -> AnomalyDetectionManager:
    """获取全局异常检测管理器"""
    global _global_anomaly_manager
    if _global_anomaly_manager is None:
        _global_anomaly_manager = AnomalyDetectionManager()
    return _global_anomaly_manager

def detect_anomaly(metric_name: str, value: float) -> None:
    """便捷异常检测函数"""
    get_anomaly_manager().add_metric_data(metric_name, value)
