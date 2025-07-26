"""
MarketPrism日志去重系统

提供智能的日志去重、聚合和批量处理功能，有效减少日志洪水问题。
"""

import time
import hashlib
from typing import Dict, Any, Optional, List, Tuple, Set
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
import threading


class DeduplicationStrategy(Enum):
    """去重策略"""
    EXACT_MATCH = "exact_match"           # 精确匹配
    CONTENT_HASH = "content_hash"         # 内容哈希
    PATTERN_MATCH = "pattern_match"       # 模式匹配
    TIME_WINDOW = "time_window"           # 时间窗口
    FREQUENCY_LIMIT = "frequency_limit"   # 频率限制


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: float
    level: str
    component: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    hash_key: Optional[str] = None
    
    def __post_init__(self):
        if self.hash_key is None:
            self.hash_key = self._generate_hash()
    
    def _generate_hash(self) -> str:
        """生成内容哈希"""
        # 排除时间戳和动态值，只对核心内容生成哈希
        content = f"{self.level}:{self.component}:{self._normalize_message()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _normalize_message(self) -> str:
        """标准化消息内容，移除动态部分"""
        import re
        
        # 移除时间戳
        message = re.sub(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', '[TIMESTAMP]', self.message)
        
        # 移除数字ID
        message = re.sub(r'\b\d{10,}\b', '[ID]', message)
        
        # 移除价格和数量
        message = re.sub(r'\b\d+\.\d+\b', '[NUMBER]', message)
        
        # 移除符号名称（保留模式）
        message = re.sub(r'\b[A-Z]{3,10}USDT?\b', '[SYMBOL]', message)
        
        # 移除emoji
        message = re.sub(r'[🔍🚀✅❌⚠️💓🔧📊🎯🏭📋🔄🛑]', '', message)
        
        return message.strip()


@dataclass
class DeduplicationRule:
    """去重规则"""
    pattern: str
    strategy: DeduplicationStrategy
    time_window: int = 60  # 秒
    max_occurrences: int = 5
    batch_size: int = 10
    enabled: bool = True


class LogDeduplicator:
    """日志去重器"""
    
    def __init__(self, max_cache_size: int = 10000):
        self.max_cache_size = max_cache_size
        self._cache: Dict[str, List[LogEntry]] = defaultdict(list)
        self._suppressed_counts: Dict[str, int] = defaultdict(int)
        self._last_logged: Dict[str, float] = {}
        self._lock = threading.Lock()
        
        # 预定义去重规则
        self.rules = self._initialize_default_rules()
    
    def _initialize_default_rules(self) -> Dict[str, DeduplicationRule]:
        """初始化默认去重规则"""
        return {
            "websocket_connection": DeduplicationRule(
                pattern=r"WebSocket.*连接.*成功",
                strategy=DeduplicationStrategy.PATTERN_MATCH,
                time_window=300,  # 5分钟
                max_occurrences=1
            ),
            
            "data_processing_success": DeduplicationRule(
                pattern=r".*更新应用成功",
                strategy=DeduplicationStrategy.FREQUENCY_LIMIT,
                time_window=60,   # 1分钟
                max_occurrences=10,
                batch_size=100
            ),
            
            "message_queue": DeduplicationRule(
                pattern=r"消息入队.*队列大小",
                strategy=DeduplicationStrategy.FREQUENCY_LIMIT,
                time_window=30,   # 30秒
                max_occurrences=5,
                batch_size=50
            ),
            
            "heartbeat": DeduplicationRule(
                pattern=r"心跳.*检查",
                strategy=DeduplicationStrategy.TIME_WINDOW,
                time_window=120,  # 2分钟
                max_occurrences=1
            ),
            
            "performance_stats": DeduplicationRule(
                pattern=r"性能.*统计|Performance.*metric",
                strategy=DeduplicationStrategy.TIME_WINDOW,
                time_window=60,   # 1分钟
                max_occurrences=3
            )
        }
    
    def should_log(self, entry: LogEntry) -> Tuple[bool, Optional[str]]:
        """判断是否应该记录日志
        
        Returns:
            (should_log, aggregation_message)
        """
        with self._lock:
            # 查找匹配的规则
            matching_rule = self._find_matching_rule(entry)
            
            if not matching_rule or not matching_rule.enabled:
                return True, None
            
            # 应用去重策略
            return self._apply_deduplication_strategy(entry, matching_rule)
    
    def _find_matching_rule(self, entry: LogEntry) -> Optional[DeduplicationRule]:
        """查找匹配的去重规则"""
        import re
        
        for rule_name, rule in self.rules.items():
            if re.search(rule.pattern, entry.message, re.IGNORECASE):
                return rule
        
        return None
    
    def _apply_deduplication_strategy(self, 
                                    entry: LogEntry, 
                                    rule: DeduplicationRule) -> Tuple[bool, Optional[str]]:
        """应用去重策略"""
        
        if rule.strategy == DeduplicationStrategy.EXACT_MATCH:
            return self._apply_exact_match(entry, rule)
        
        elif rule.strategy == DeduplicationStrategy.CONTENT_HASH:
            return self._apply_content_hash(entry, rule)
        
        elif rule.strategy == DeduplicationStrategy.PATTERN_MATCH:
            return self._apply_pattern_match(entry, rule)
        
        elif rule.strategy == DeduplicationStrategy.TIME_WINDOW:
            return self._apply_time_window(entry, rule)
        
        elif rule.strategy == DeduplicationStrategy.FREQUENCY_LIMIT:
            return self._apply_frequency_limit(entry, rule)
        
        return True, None
    
    def _apply_exact_match(self, entry: LogEntry, rule: DeduplicationRule) -> Tuple[bool, Optional[str]]:
        """精确匹配去重"""
        exact_key = f"{entry.component}:{entry.message}"
        
        if exact_key in self._last_logged:
            time_since_last = entry.timestamp - self._last_logged[exact_key]
            if time_since_last < rule.time_window:
                self._suppressed_counts[exact_key] += 1
                return False, None
        
        self._last_logged[exact_key] = entry.timestamp
        
        # 添加抑制信息
        suppressed = self._suppressed_counts.get(exact_key, 0)
        if suppressed > 0:
            self._suppressed_counts[exact_key] = 0
            return True, f"(suppressed {suppressed} identical messages)"
        
        return True, None
    
    def _apply_content_hash(self, entry: LogEntry, rule: DeduplicationRule) -> Tuple[bool, Optional[str]]:
        """内容哈希去重"""
        hash_key = entry.hash_key
        
        # 清理过期缓存
        self._cleanup_cache(hash_key, rule.time_window)
        
        # 检查是否超过限制
        if len(self._cache[hash_key]) >= rule.max_occurrences:
            self._suppressed_counts[hash_key] += 1
            return False, None
        
        # 添加到缓存
        self._cache[hash_key].append(entry)
        
        # 检查是否需要批量报告
        if len(self._cache[hash_key]) == rule.max_occurrences:
            suppressed = self._suppressed_counts.get(hash_key, 0)
            if suppressed > 0:
                return True, f"(last occurrence, suppressed {suppressed} similar messages)"
        
        return True, None
    
    def _apply_pattern_match(self, entry: LogEntry, rule: DeduplicationRule) -> Tuple[bool, Optional[str]]:
        """模式匹配去重"""
        pattern_key = f"{entry.component}:{rule.pattern}"
        
        if pattern_key in self._last_logged:
            time_since_last = entry.timestamp - self._last_logged[pattern_key]
            if time_since_last < rule.time_window:
                self._suppressed_counts[pattern_key] += 1
                return False, None
        
        self._last_logged[pattern_key] = entry.timestamp
        
        suppressed = self._suppressed_counts.get(pattern_key, 0)
        if suppressed > 0:
            self._suppressed_counts[pattern_key] = 0
            return True, f"(suppressed {suppressed} similar pattern messages)"
        
        return True, None
    
    def _apply_time_window(self, entry: LogEntry, rule: DeduplicationRule) -> Tuple[bool, Optional[str]]:
        """时间窗口去重"""
        window_key = f"{entry.component}:{entry.hash_key}"
        
        # 清理过期记录
        self._cleanup_cache(window_key, rule.time_window)
        
        # 检查窗口内的记录数
        if len(self._cache[window_key]) >= rule.max_occurrences:
            self._suppressed_counts[window_key] += 1
            return False, None
        
        self._cache[window_key].append(entry)
        return True, None
    
    def _apply_frequency_limit(self, entry: LogEntry, rule: DeduplicationRule) -> Tuple[bool, Optional[str]]:
        """频率限制去重"""
        freq_key = f"{entry.component}:{entry.hash_key}"
        
        # 清理过期记录
        self._cleanup_cache(freq_key, rule.time_window)
        
        # 添加当前记录
        self._cache[freq_key].append(entry)
        
        # 检查是否达到批量大小
        if len(self._cache[freq_key]) >= rule.batch_size:
            # 批量报告
            batch_count = len(self._cache[freq_key])
            self._cache[freq_key].clear()
            return True, f"(batch report: {batch_count} similar operations)"
        
        # 检查是否超过频率限制
        if len(self._cache[freq_key]) > rule.max_occurrences:
            self._suppressed_counts[freq_key] += 1
            return False, None
        
        return True, None
    
    def _cleanup_cache(self, key: str, time_window: int):
        """清理过期缓存"""
        if key not in self._cache:
            return
        
        cutoff_time = time.time() - time_window
        self._cache[key] = [
            entry for entry in self._cache[key] 
            if entry.timestamp > cutoff_time
        ]
        
        # 如果缓存为空，删除键
        if not self._cache[key]:
            del self._cache[key]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取去重统计信息"""
        total_suppressed = sum(self._suppressed_counts.values())
        active_patterns = len([k for k, v in self._cache.items() if v])
        
        return {
            "total_suppressed_logs": total_suppressed,
            "active_deduplication_patterns": active_patterns,
            "cache_size": sum(len(entries) for entries in self._cache.values()),
            "suppression_by_pattern": dict(self._suppressed_counts),
            "rules_count": len(self.rules),
            "enabled_rules": len([r for r in self.rules.values() if r.enabled])
        }
    
    def add_rule(self, name: str, rule: DeduplicationRule):
        """添加自定义去重规则"""
        self.rules[name] = rule
    
    def disable_rule(self, name: str):
        """禁用去重规则"""
        if name in self.rules:
            self.rules[name].enabled = False
    
    def enable_rule(self, name: str):
        """启用去重规则"""
        if name in self.rules:
            self.rules[name].enabled = True


class LogAggregator:
    """日志聚合器"""
    
    def __init__(self, flush_interval: int = 60):
        self.flush_interval = flush_interval
        self._aggregated_logs: Dict[str, List[LogEntry]] = defaultdict(list)
        self._counters: Dict[str, int] = defaultdict(int)
        self._last_flush = time.time()
        self._lock = threading.Lock()
    
    def aggregate(self, entry: LogEntry, aggregation_key: str):
        """聚合日志条目"""
        with self._lock:
            self._aggregated_logs[aggregation_key].append(entry)
            self._counters[aggregation_key] += 1
    
    def should_flush(self) -> bool:
        """检查是否应该刷新"""
        return time.time() - self._last_flush >= self.flush_interval
    
    def flush_aggregated_logs(self) -> List[Tuple[str, int, List[LogEntry]]]:
        """刷新聚合的日志"""
        with self._lock:
            if not self.should_flush():
                return []
            
            result = []
            for key, entries in self._aggregated_logs.items():
                if entries:
                    result.append((key, self._counters[key], entries.copy()))
            
            # 清理
            self._aggregated_logs.clear()
            self._counters.clear()
            self._last_flush = time.time()
            
            return result


class SmartLogBatcher:
    """智能日志批处理器"""
    
    def __init__(self, 
                 batch_size: int = 50,
                 flush_interval: int = 30,
                 max_memory_mb: int = 10):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        
        self._batches: Dict[str, List[LogEntry]] = defaultdict(list)
        self._batch_sizes: Dict[str, int] = defaultdict(int)
        self._last_flush = time.time()
        self._lock = threading.Lock()
    
    def add_to_batch(self, entry: LogEntry, batch_key: str) -> Optional[List[LogEntry]]:
        """添加到批处理，返回需要刷新的批次"""
        with self._lock:
            self._batches[batch_key].append(entry)
            self._batch_sizes[batch_key] += len(entry.message.encode('utf-8'))
            
            # 检查是否需要刷新
            if (len(self._batches[batch_key]) >= self.batch_size or
                self._batch_sizes[batch_key] >= self.max_memory_bytes or
                self._should_flush_by_time()):
                
                return self._flush_batch(batch_key)
        
        return None
    
    def _should_flush_by_time(self) -> bool:
        """检查是否应该按时间刷新"""
        return time.time() - self._last_flush >= self.flush_interval
    
    def _flush_batch(self, batch_key: str) -> List[LogEntry]:
        """刷新指定批次"""
        batch = self._batches[batch_key].copy()
        self._batches[batch_key].clear()
        self._batch_sizes[batch_key] = 0
        self._last_flush = time.time()
        return batch
    
    def flush_all_batches(self) -> Dict[str, List[LogEntry]]:
        """刷新所有批次"""
        with self._lock:
            result = {}
            for batch_key in list(self._batches.keys()):
                if self._batches[batch_key]:
                    result[batch_key] = self._flush_batch(batch_key)
            return result


# 全局实例
log_deduplicator = LogDeduplicator()
log_aggregator = LogAggregator()
log_batcher = SmartLogBatcher()


def with_deduplication(component: str):
    """日志去重装饰器"""
    def decorator(log_func):
        def wrapper(message: str, level: str = "INFO", **kwargs):
            entry = LogEntry(
                timestamp=time.time(),
                level=level,
                component=component,
                message=message,
                context=kwargs
            )
            
            should_log, aggregation_msg = log_deduplicator.should_log(entry)
            
            if should_log:
                final_message = message
                if aggregation_msg:
                    final_message += f" {aggregation_msg}"
                
                return log_func(final_message, level=level, **kwargs)
        
        return wrapper
    return decorator
