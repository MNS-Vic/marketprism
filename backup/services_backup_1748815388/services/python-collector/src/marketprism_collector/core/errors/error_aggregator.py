"""
错误聚合器

提供错误数据的聚合、分析和统计功能。
支持错误模式识别、趋势分析和异常检测。
"""

import time
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

from .exceptions import MarketPrismError
from .error_categories import ErrorCategory, ErrorSeverity, ErrorType


class TimeWindow(Enum):
    """时间窗口枚举"""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"


@dataclass
class ErrorPattern:
    """错误模式"""
    pattern_id: str
    error_type: ErrorType
    category: ErrorCategory
    frequency: int
    first_seen: datetime
    last_seen: datetime
    components: List[str] = field(default_factory=list)
    common_contexts: Dict[str, Any] = field(default_factory=dict)
    severity_distribution: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "pattern_id": self.pattern_id,
            "error_type": self.error_type.name,
            "category": self.category.value,
            "frequency": self.frequency,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "components": self.components,
            "common_contexts": self.common_contexts,
            "severity_distribution": self.severity_distribution
        }


@dataclass
class ErrorStatistics:
    """错误统计信息"""
    time_window: TimeWindow
    start_time: datetime
    end_time: datetime
    total_errors: int
    by_category: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)
    by_component: Dict[str, int] = field(default_factory=dict)
    error_rate: float = 0.0
    critical_error_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "time_window": self.time_window.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "total_errors": self.total_errors,
            "by_category": self.by_category,
            "by_severity": self.by_severity,
            "by_type": self.by_type,
            "by_component": self.by_component,
            "error_rate": self.error_rate,
            "critical_error_rate": self.critical_error_rate
        }


class TimeSeriesData:
    """时间序列数据"""
    
    def __init__(self, max_points: int = 1440):  # 默认保存24小时的分钟级数据
        self.max_points = max_points
        self.timestamps: deque = deque(maxlen=max_points)
        self.values: deque = deque(maxlen=max_points)
        self._lock = threading.Lock()
    
    def add_point(self, timestamp: datetime, value: float):
        """添加数据点"""
        with self._lock:
            self.timestamps.append(timestamp)
            self.values.append(value)
    
    def get_data(self, since: Optional[datetime] = None) -> List[Tuple[datetime, float]]:
        """获取数据"""
        with self._lock:
            data = list(zip(self.timestamps, self.values))
            
            if since:
                data = [(ts, val) for ts, val in data if ts >= since]
            
            return data
    
    def get_latest_value(self) -> Optional[float]:
        """获取最新值"""
        with self._lock:
            return self.values[-1] if self.values else None
    
    def calculate_trend(self, points: int = 10) -> float:
        """计算趋势（斜率）"""
        with self._lock:
            if len(self.values) < 2:
                return 0.0
            
            recent_values = list(self.values)[-points:]
            if len(recent_values) < 2:
                return 0.0
            
            # 简单线性回归计算斜率
            n = len(recent_values)
            x = list(range(n))
            y = recent_values
            
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[i] * y[i] for i in range(n))
            sum_x2 = sum(x[i] ** 2 for i in range(n))
            
            if n * sum_x2 - sum_x ** 2 == 0:
                return 0.0
            
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
            return slope


class ErrorAggregator:
    """错误聚合器
    
    收集、聚合和分析错误数据，提供统计信息和模式识别。
    """
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self.error_history: List[MarketPrismError] = []
        self.error_patterns: Dict[str, ErrorPattern] = {}
        
        # 时间序列数据
        self.error_rate_series = TimeSeriesData()
        self.critical_error_series = TimeSeriesData()
        self.category_series: Dict[str, TimeSeriesData] = {}
        
        # 统计数据
        self.current_statistics: Dict[TimeWindow, ErrorStatistics] = {}
        
        # 线程安全
        self._lock = threading.Lock()
        
        # 初始化时间窗口统计
        self._initialize_statistics()
    
    def _initialize_statistics(self):
        """初始化统计数据"""
        now = datetime.now(timezone.utc)
        
        for window in TimeWindow:
            if window == TimeWindow.MINUTE:
                start_time = now.replace(second=0, microsecond=0)
            elif window == TimeWindow.HOUR:
                start_time = now.replace(minute=0, second=0, microsecond=0)
            elif window == TimeWindow.DAY:
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            else:  # WEEK
                days_since_monday = now.weekday()
                start_time = (now - timedelta(days=days_since_monday)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            
            self.current_statistics[window] = ErrorStatistics(
                time_window=window,
                start_time=start_time,
                end_time=now,
                total_errors=0
            )
    
    def add_error(self, error: MarketPrismError):
        """添加错误到聚合器"""
        with self._lock:
            # 添加到历史记录
            self.error_history.append(error)
            
            # 限制历史记录大小
            if len(self.error_history) > self.max_history:
                self.error_history = self.error_history[-self.max_history:]
            
            # 更新统计
            self._update_statistics(error)
            
            # 更新时间序列
            self._update_time_series(error)
            
            # 更新错误模式
            self._update_patterns(error)
    
    def _update_statistics(self, error: MarketPrismError):
        """更新统计信息"""
        now = datetime.now(timezone.utc)
        
        for window, stats in self.current_statistics.items():
            # 检查是否需要重置统计窗口
            if self._should_reset_window(stats, now):
                self._reset_statistics_window(window, now)
                stats = self.current_statistics[window]
            
            # 更新统计数据
            stats.total_errors += 1
            stats.end_time = now
            
            # 按分类统计
            category = error.category.value
            stats.by_category[category] = stats.by_category.get(category, 0) + 1
            
            # 按严重程度统计
            severity = error.severity.value
            stats.by_severity[severity] = stats.by_severity.get(severity, 0) + 1
            
            # 按错误类型统计
            error_type = error.error_type.name
            stats.by_type[error_type] = stats.by_type.get(error_type, 0) + 1
            
            # 按组件统计（从上下文获取）
            component = error.get_context_value('component', 'unknown')
            stats.by_component[component] = stats.by_component.get(component, 0) + 1
            
            # 计算错误率
            duration = (stats.end_time - stats.start_time).total_seconds()
            if duration > 0:
                stats.error_rate = stats.total_errors / duration * 60  # 每分钟错误数
                critical_errors = stats.by_severity.get('critical', 0)
                stats.critical_error_rate = critical_errors / duration * 60
    
    def _should_reset_window(self, stats: ErrorStatistics, now: datetime) -> bool:
        """判断是否应该重置统计窗口"""
        if stats.time_window == TimeWindow.MINUTE:
            return now.minute != stats.start_time.minute
        elif stats.time_window == TimeWindow.HOUR:
            return now.hour != stats.start_time.hour
        elif stats.time_window == TimeWindow.DAY:
            return now.date() != stats.start_time.date()
        else:  # WEEK
            return now.isocalendar()[1] != stats.start_time.isocalendar()[1]
    
    def _reset_statistics_window(self, window: TimeWindow, now: datetime):
        """重置统计窗口"""
        if window == TimeWindow.MINUTE:
            start_time = now.replace(second=0, microsecond=0)
        elif window == TimeWindow.HOUR:
            start_time = now.replace(minute=0, second=0, microsecond=0)
        elif window == TimeWindow.DAY:
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # WEEK
            days_since_monday = now.weekday()
            start_time = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        
        self.current_statistics[window] = ErrorStatistics(
            time_window=window,
            start_time=start_time,
            end_time=now,
            total_errors=0
        )
    
    def _update_time_series(self, error: MarketPrismError):
        """更新时间序列数据"""
        now = datetime.now(timezone.utc)
        
        # 更新错误率时间序列（每分钟采样）
        minute_key = now.replace(second=0, microsecond=0)
        
        # 计算当前分钟的错误数
        minute_errors = len([
            e for e in self.error_history
            if e.timestamp >= minute_key and e.timestamp < minute_key + timedelta(minutes=1)
        ])
        
        self.error_rate_series.add_point(minute_key, minute_errors)
        
        # 更新严重错误时间序列
        critical_errors = len([
            e for e in self.error_history
            if (e.timestamp >= minute_key and 
                e.timestamp < minute_key + timedelta(minutes=1) and
                e.severity == ErrorSeverity.CRITICAL)
        ])
        
        self.critical_error_series.add_point(minute_key, critical_errors)
        
        # 更新分类时间序列
        category = error.category.value
        if category not in self.category_series:
            self.category_series[category] = TimeSeriesData()
        
        category_errors = len([
            e for e in self.error_history
            if (e.timestamp >= minute_key and
                e.timestamp < minute_key + timedelta(minutes=1) and
                e.category == error.category)
        ])
        
        self.category_series[category].add_point(minute_key, category_errors)
    
    def _update_patterns(self, error: MarketPrismError):
        """更新错误模式"""
        pattern_key = f"{error.error_type.name}_{error.category.value}"
        
        if pattern_key in self.error_patterns:
            pattern = self.error_patterns[pattern_key]
            pattern.frequency += 1
            pattern.last_seen = error.timestamp
            
            # 更新严重程度分布
            severity = error.severity.value
            pattern.severity_distribution[severity] = pattern.severity_distribution.get(severity, 0) + 1
            
            # 更新组件信息
            component = error.get_context_value('component')
            if component and component not in pattern.components:
                pattern.components.append(component)
        
        else:
            # 创建新模式
            component = error.get_context_value('component')
            components = [component] if component else []
            
            pattern = ErrorPattern(
                pattern_id=pattern_key,
                error_type=error.error_type,
                category=error.category,
                frequency=1,
                first_seen=error.timestamp,
                last_seen=error.timestamp,
                components=components,
                severity_distribution={error.severity.value: 1}
            )
            
            self.error_patterns[pattern_key] = pattern
    
    def get_statistics(self, window: TimeWindow = TimeWindow.HOUR) -> ErrorStatistics:
        """获取指定时间窗口的统计信息"""
        with self._lock:
            return self.current_statistics.get(window, ErrorStatistics(
                time_window=window,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                total_errors=0
            ))
    
    def get_all_statistics(self) -> Dict[str, ErrorStatistics]:
        """获取所有时间窗口的统计信息"""
        with self._lock:
            return {
                window.value: stats 
                for window, stats in self.current_statistics.items()
            }
    
    def get_error_patterns(self, 
                          min_frequency: int = 2,
                          since: Optional[datetime] = None) -> List[ErrorPattern]:
        """获取错误模式"""
        with self._lock:
            patterns = []
            
            for pattern in self.error_patterns.values():
                if pattern.frequency >= min_frequency:
                    if since is None or pattern.last_seen >= since:
                        patterns.append(pattern)
            
            # 按频率排序
            patterns.sort(key=lambda p: p.frequency, reverse=True)
            return patterns
    
    def get_trending_errors(self, points: int = 10) -> List[Dict[str, Any]]:
        """获取趋势错误"""
        trends = []
        
        # 分析总体错误趋势
        overall_trend = self.error_rate_series.calculate_trend(points)
        trends.append({
            "type": "overall",
            "trend": overall_trend,
            "current_rate": self.error_rate_series.get_latest_value() or 0
        })
        
        # 分析各分类的趋势
        for category, series in self.category_series.items():
            trend = series.calculate_trend(points)
            trends.append({
                "type": "category",
                "category": category,
                "trend": trend,
                "current_rate": series.get_latest_value() or 0
            })
        
        return trends
    
    def detect_anomalies(self, threshold: float = 2.0) -> List[Dict[str, Any]]:
        """检测异常"""
        anomalies = []
        
        # 检测错误率异常
        recent_data = self.error_rate_series.get_data(
            since=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        
        if len(recent_data) >= 10:
            values = [val for _, val in recent_data]
            mean_rate = sum(values) / len(values)
            variance = sum((val - mean_rate) ** 2 for val in values) / len(values)
            std_dev = variance ** 0.5
            
            current_rate = values[-1]
            if current_rate > mean_rate + threshold * std_dev:
                anomalies.append({
                    "type": "high_error_rate",
                    "current_value": current_rate,
                    "expected_range": [mean_rate - std_dev, mean_rate + std_dev],
                    "severity": "high" if current_rate > mean_rate + 3 * std_dev else "medium"
                })
        
        # 检测严重错误异常
        critical_data = self.critical_error_series.get_data(
            since=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        
        if critical_data:
            current_critical = critical_data[-1][1]
            if current_critical > 0:
                anomalies.append({
                    "type": "critical_errors_detected",
                    "current_value": current_critical,
                    "severity": "critical"
                })
        
        return anomalies
    
    def get_summary_report(self) -> Dict[str, Any]:
        """获取汇总报告"""
        with self._lock:
            now = datetime.now(timezone.utc)
            
            # 基本统计
            total_errors = len(self.error_history)
            recent_errors = len([
                e for e in self.error_history
                if e.timestamp >= now - timedelta(hours=1)
            ])
            
            # 错误模式统计
            top_patterns = sorted(
                self.error_patterns.values(),
                key=lambda p: p.frequency,
                reverse=True
            )[:5]
            
            # 趋势分析
            trends = self.get_trending_errors()
            
            # 异常检测
            anomalies = self.detect_anomalies()
            
            return {
                "summary": {
                    "total_errors": total_errors,
                    "recent_errors": recent_errors,
                    "error_patterns": len(self.error_patterns),
                    "anomalies_detected": len(anomalies)
                },
                "statistics": {
                    window.value: stats.to_dict()
                    for window, stats in self.current_statistics.items()
                },
                "top_patterns": [pattern.to_dict() for pattern in top_patterns],
                "trends": trends,
                "anomalies": anomalies,
                "generated_at": now.isoformat()
            }
    
    def clear_data(self):
        """清除所有数据"""
        with self._lock:
            self.error_history.clear()
            self.error_patterns.clear()
            self.category_series.clear()
            
            # 重新初始化
            self._initialize_statistics()
            self.error_rate_series = TimeSeriesData()
            self.critical_error_series = TimeSeriesData()