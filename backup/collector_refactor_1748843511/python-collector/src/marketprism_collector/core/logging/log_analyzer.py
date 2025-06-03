"""
日志分析器

提供日志数据的分析和异常检测功能。
"""

from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timezone

from .log_aggregator import LogAggregator, LogEntry


@dataclass
class LogAnalysisResult:
    """日志分析结果"""
    analysis_time: datetime
    total_entries: int
    error_rate: float
    warning_rate: float
    anomalies: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'analysis_time': self.analysis_time.isoformat(),
            'total_entries': self.total_entries,
            'error_rate': self.error_rate,
            'warning_rate': self.warning_rate,
            'anomalies': self.anomalies
        }


class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, aggregator: LogAggregator):
        self.aggregator = aggregator
    
    def analyze(self) -> LogAnalysisResult:
        """分析日志数据"""
        entries = self.aggregator.get_recent_entries(1000)
        total_entries = len(entries)
        
        if total_entries == 0:
            return LogAnalysisResult(
                analysis_time=datetime.now(timezone.utc),
                total_entries=0,
                error_rate=0.0,
                warning_rate=0.0,
                anomalies=[]
            )
        
        error_count = sum(1 for entry in entries if entry.level.value == 'ERROR')
        warning_count = sum(1 for entry in entries if entry.level.value == 'WARNING')
        
        error_rate = error_count / total_entries
        warning_rate = warning_count / total_entries
        
        anomalies = self._detect_anomalies(entries)
        
        return LogAnalysisResult(
            analysis_time=datetime.now(timezone.utc),
            total_entries=total_entries,
            error_rate=error_rate,
            warning_rate=warning_rate,
            anomalies=anomalies
        )
    
    def _detect_anomalies(self, entries: List[LogEntry]) -> List[Dict[str, Any]]:
        """检测异常"""
        anomalies = []
        
        # 简单的异常检测：错误率过高
        error_count = sum(1 for entry in entries if entry.level.value == 'ERROR')
        if error_count > len(entries) * 0.1:  # 错误率超过10%
            anomalies.append({
                'type': 'high_error_rate',
                'description': f'错误率过高: {error_count}/{len(entries)}',
                'severity': 'high'
            })
        
        return anomalies