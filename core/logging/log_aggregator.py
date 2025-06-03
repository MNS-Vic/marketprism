"""
日志聚合器

提供日志数据的聚合、分析和统计功能。
"""

import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import defaultdict, deque

from .log_config import LogLevel


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: datetime
    level: LogLevel
    logger: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level.value,
            'logger': self.logger,
            'message': self.message,
            'context': self.context
        }


@dataclass
class LogPattern:
    """日志模式"""
    pattern_id: str
    level: LogLevel
    logger: str
    frequency: int
    first_seen: datetime
    last_seen: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'pattern_id': self.pattern_id,
            'level': self.level.value,
            'logger': self.logger,
            'frequency': self.frequency,
            'first_seen': self.first_seen.isoformat(),
            'last_seen': self.last_seen.isoformat()
        }


class LogAggregator:
    """日志聚合器"""
    
    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        self.entries: deque = deque(maxlen=max_entries)
        self.patterns: Dict[str, LogPattern] = {}
        self._lock = threading.Lock()
    
    def add_entry(self, entry: LogEntry):
        """添加日志条目"""
        with self._lock:
            self.entries.append(entry)
            self._update_patterns(entry)
    
    def _update_patterns(self, entry: LogEntry):
        """更新日志模式"""
        pattern_key = f"{entry.level.value}_{entry.logger}"
        
        if pattern_key in self.patterns:
            pattern = self.patterns[pattern_key]
            pattern.frequency += 1
            pattern.last_seen = entry.timestamp
        else:
            pattern = LogPattern(
                pattern_id=pattern_key,
                level=entry.level,
                logger=entry.logger,
                frequency=1,
                first_seen=entry.timestamp,
                last_seen=entry.timestamp
            )
            self.patterns[pattern_key] = pattern
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            total_entries = len(self.entries)
            by_level = defaultdict(int)
            by_logger = defaultdict(int)
            
            for entry in self.entries:
                by_level[entry.level.value] += 1
                by_logger[entry.logger] += 1
            
            return {
                'total_entries': total_entries,
                'by_level': dict(by_level),
                'by_logger': dict(by_logger),
                'patterns': len(self.patterns)
            }
    
    def get_recent_entries(self, limit: int = 100) -> List[LogEntry]:
        """获取最近的日志条目"""
        with self._lock:
            return list(self.entries)[-limit:]