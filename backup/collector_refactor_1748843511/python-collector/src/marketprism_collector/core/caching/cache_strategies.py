"""
缓存策略系统

实现各种缓存淘汰和管理策略。
"""

import time
import heapq
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from collections import OrderedDict, defaultdict

from .cache_interface import CacheKey, CacheValue, CacheEvictionPolicy


@dataclass
class StrategyMetrics:
    """策略指标"""
    access_count: int = 0
    hit_count: int = 0
    miss_count: int = 0
    eviction_count: int = 0
    last_access_time: Optional[datetime] = None
    
    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0


class CacheStrategy(ABC):
    """缓存策略抽象基类"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.metrics = StrategyMetrics()
    
    @abstractmethod
    def should_evict(self, current_size: int) -> bool:
        """判断是否应该淘汰"""
        pass
    
    @abstractmethod
    def select_victim(self) -> Optional[CacheKey]:
        """选择被淘汰的键"""
        pass
    
    @abstractmethod
    def on_access(self, key: CacheKey, value: CacheValue) -> None:
        """访问时调用"""
        pass
    
    @abstractmethod
    def on_insert(self, key: CacheKey, value: CacheValue) -> None:
        """插入时调用"""
        pass
    
    @abstractmethod
    def on_update(self, key: CacheKey, old_value: CacheValue, new_value: CacheValue) -> None:
        """更新时调用"""
        pass
    
    @abstractmethod
    def on_remove(self, key: CacheKey, value: CacheValue) -> None:
        """移除时调用"""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空策略状态"""
        pass
    
    def get_metrics(self) -> StrategyMetrics:
        """获取策略指标"""
        return self.metrics


class LRUStrategy(CacheStrategy):
    """最近最少使用策略"""
    
    def __init__(self, max_size: int = 1000):
        super().__init__(max_size)
        self.access_order = OrderedDict()  # key -> timestamp
    
    def should_evict(self, current_size: int) -> bool:
        """当前大小超过最大值时需要淘汰"""
        return current_size >= self.max_size
    
    def select_victim(self) -> Optional[CacheKey]:
        """选择最久未访问的键"""
        if not self.access_order:
            return None
        
        # 获取最旧的键（OrderedDict保证了插入顺序）
        oldest_key = next(iter(self.access_order))
        return oldest_key
    
    def on_access(self, key: CacheKey, value: CacheValue) -> None:
        """更新访问顺序"""
        now = datetime.now(timezone.utc)
        self.access_order[key] = now
        self.access_order.move_to_end(key)  # 移到末尾
        
        self.metrics.access_count += 1
        self.metrics.hit_count += 1
        self.metrics.last_access_time = now
    
    def on_insert(self, key: CacheKey, value: CacheValue) -> None:
        """记录新插入的键"""
        now = datetime.now(timezone.utc)
        self.access_order[key] = now
        self.metrics.access_count += 1
    
    def on_update(self, key: CacheKey, old_value: CacheValue, new_value: CacheValue) -> None:
        """更新时刷新访问时间"""
        self.on_access(key, new_value)
    
    def on_remove(self, key: CacheKey, value: CacheValue) -> None:
        """移除键时清理状态"""
        self.access_order.pop(key, None)
        self.metrics.eviction_count += 1
    
    def clear(self) -> None:
        """清空所有状态"""
        self.access_order.clear()


class LFUStrategy(CacheStrategy):
    """最少频率使用策略"""
    
    def __init__(self, max_size: int = 1000):
        super().__init__(max_size)
        self.frequencies = defaultdict(int)  # key -> frequency
        self.frequency_groups = defaultdict(list)  # frequency -> [keys]
        self.min_frequency = 0
    
    def should_evict(self, current_size: int) -> bool:
        """当前大小超过最大值时需要淘汰"""
        return current_size >= self.max_size
    
    def select_victim(self) -> Optional[CacheKey]:
        """选择频率最低的键"""
        if not self.frequency_groups[self.min_frequency]:
            return None
        
        # 获取最低频率组中的第一个键
        victim_key = self.frequency_groups[self.min_frequency].pop(0)
        
        # 如果最低频率组为空，增加最小频率
        if not self.frequency_groups[self.min_frequency]:
            self.min_frequency += 1
        
        return victim_key
    
    def on_access(self, key: CacheKey, value: CacheValue) -> None:
        """增加访问频率"""
        old_freq = self.frequencies[key]
        new_freq = old_freq + 1
        
        self.frequencies[key] = new_freq
        
        # 从旧频率组移除
        if key in self.frequency_groups[old_freq]:
            self.frequency_groups[old_freq].remove(key)
        
        # 添加到新频率组
        self.frequency_groups[new_freq].append(key)
        
        # 如果旧频率是最小频率且该组为空，更新最小频率
        if old_freq == self.min_frequency and not self.frequency_groups[old_freq]:
            self.min_frequency = new_freq
        
        self.metrics.access_count += 1
        self.metrics.hit_count += 1
        self.metrics.last_access_time = datetime.now(timezone.utc)
    
    def on_insert(self, key: CacheKey, value: CacheValue) -> None:
        """新插入的键频率为1"""
        self.frequencies[key] = 1
        self.frequency_groups[1].append(key)
        self.min_frequency = 1
        self.metrics.access_count += 1
    
    def on_update(self, key: CacheKey, old_value: CacheValue, new_value: CacheValue) -> None:
        """更新时增加频率"""
        self.on_access(key, new_value)
    
    def on_remove(self, key: CacheKey, value: CacheValue) -> None:
        """移除键时清理状态"""
        freq = self.frequencies.pop(key, 0)
        if key in self.frequency_groups[freq]:
            self.frequency_groups[freq].remove(key)
        
        self.metrics.eviction_count += 1
    
    def clear(self) -> None:
        """清空所有状态"""
        self.frequencies.clear()
        self.frequency_groups.clear()
        self.min_frequency = 0


class TTLStrategy(CacheStrategy):
    """生存时间策略"""
    
    def __init__(self, max_size: int = 1000, default_ttl: Optional[timedelta] = None):
        super().__init__(max_size)
        self.default_ttl = default_ttl or timedelta(hours=1)
        self.expiration_heap = []  # (expiration_time, key)
        self.key_expiration = {}  # key -> expiration_time
    
    def should_evict(self, current_size: int) -> bool:
        """需要清理过期键或大小超限"""
        self._cleanup_expired()
        return current_size >= self.max_size
    
    def select_victim(self) -> Optional[CacheKey]:
        """选择最早过期的键"""
        self._cleanup_expired()
        
        if not self.expiration_heap:
            return None
        
        # 获取最早过期的键
        _, victim_key = heapq.heappop(self.expiration_heap)
        self.key_expiration.pop(victim_key, None)
        
        return victim_key
    
    def _cleanup_expired(self) -> List[CacheKey]:
        """清理已过期的键"""
        now = datetime.now(timezone.utc)
        expired_keys = []
        
        while self.expiration_heap:
            expiration_time, key = self.expiration_heap[0]
            if expiration_time <= now:
                heapq.heappop(self.expiration_heap)
                if key in self.key_expiration:
                    del self.key_expiration[key]
                    expired_keys.append(key)
            else:
                break
        
        return expired_keys
    
    def on_access(self, key: CacheKey, value: CacheValue) -> None:
        """访问时记录"""
        self.metrics.access_count += 1
        self.metrics.hit_count += 1
        self.metrics.last_access_time = datetime.now(timezone.utc)
    
    def on_insert(self, key: CacheKey, value: CacheValue) -> None:
        """插入时设置过期时间"""
        expiration_time = value.expires_at
        if expiration_time is None:
            expiration_time = datetime.now(timezone.utc) + self.default_ttl
        
        self.key_expiration[key] = expiration_time
        heapq.heappush(self.expiration_heap, (expiration_time, key))
        self.metrics.access_count += 1
    
    def on_update(self, key: CacheKey, old_value: CacheValue, new_value: CacheValue) -> None:
        """更新时可能更新过期时间"""
        # 移除旧的过期时间
        if key in self.key_expiration:
            old_expiration = self.key_expiration[key]
            # 注意：我们不从堆中移除，而是在cleanup时忽略无效项
        
        # 设置新的过期时间
        expiration_time = new_value.expires_at
        if expiration_time is None:
            expiration_time = datetime.now(timezone.utc) + self.default_ttl
        
        self.key_expiration[key] = expiration_time
        heapq.heappush(self.expiration_heap, (expiration_time, key))
        
        self.on_access(key, new_value)
    
    def on_remove(self, key: CacheKey, value: CacheValue) -> None:
        """移除键时清理状态"""
        self.key_expiration.pop(key, None)
        # 注意：我们不从堆中移除，会在cleanup时处理
        self.metrics.eviction_count += 1
    
    def clear(self) -> None:
        """清空所有状态"""
        self.expiration_heap.clear()
        self.key_expiration.clear()
    
    def get_expired_keys(self) -> List[CacheKey]:
        """获取已过期的键"""
        return self._cleanup_expired()


class AdaptiveStrategy(CacheStrategy):
    """自适应策略
    
    根据访问模式动态选择最优策略。
    """
    
    def __init__(self, max_size: int = 1000, evaluation_interval: int = 1000):
        super().__init__(max_size)
        self.evaluation_interval = evaluation_interval
        self.operation_count = 0
        
        # 维护多个策略
        self.strategies = {
            'lru': LRUStrategy(max_size),
            'lfu': LFUStrategy(max_size),
            'ttl': TTLStrategy(max_size)
        }
        
        # 当前使用的策略
        self.current_strategy_name = 'lru'
        self.current_strategy = self.strategies[self.current_strategy_name]
        
        # 性能追踪
        self.strategy_performance = {name: [] for name in self.strategies.keys()}
        self.performance_window = 10  # 保留最近10次评估结果
    
    def should_evict(self, current_size: int) -> bool:
        """委托给当前策略"""
        self._maybe_evaluate_strategies()
        return self.current_strategy.should_evict(current_size)
    
    def select_victim(self) -> Optional[CacheKey]:
        """委托给当前策略"""
        return self.current_strategy.select_victim()
    
    def on_access(self, key: CacheKey, value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies.values():
            strategy.on_access(key, value)
        
        self.metrics.access_count += 1
        self.metrics.hit_count += 1
        self.metrics.last_access_time = datetime.now(timezone.utc)
        self.operation_count += 1
    
    def on_insert(self, key: CacheKey, value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies.values():
            strategy.on_insert(key, value)
        
        self.metrics.access_count += 1
        self.operation_count += 1
    
    def on_update(self, key: CacheKey, old_value: CacheValue, new_value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies.values():
            strategy.on_update(key, old_value, new_value)
        
        self.operation_count += 1
    
    def on_remove(self, key: CacheKey, value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies.values():
            strategy.on_remove(key, value)
        
        self.metrics.eviction_count += 1
        self.operation_count += 1
    
    def clear(self) -> None:
        """清空所有策略状态"""
        for strategy in self.strategies.values():
            strategy.clear()
        self.operation_count = 0
    
    def _maybe_evaluate_strategies(self) -> None:
        """可能评估策略性能"""
        if self.operation_count % self.evaluation_interval == 0:
            self._evaluate_strategies()
    
    def _evaluate_strategies(self) -> None:
        """评估策略性能并选择最优策略"""
        # 计算每个策略的性能分数
        scores = {}
        for name, strategy in self.strategies.items():
            metrics = strategy.get_metrics()
            
            # 综合评分：命中率权重80%，访问频率权重20%
            hit_rate_score = metrics.hit_rate * 0.8
            access_frequency_score = min(metrics.access_count / self.evaluation_interval, 1.0) * 0.2
            
            total_score = hit_rate_score + access_frequency_score
            scores[name] = total_score
            
            # 记录性能历史
            self.strategy_performance[name].append(total_score)
            if len(self.strategy_performance[name]) > self.performance_window:
                self.strategy_performance[name].pop(0)
        
        # 选择得分最高的策略
        best_strategy_name = max(scores.keys(), key=lambda k: scores[k])
        
        # 如果最优策略发生变化，切换策略
        if best_strategy_name != self.current_strategy_name:
            self.current_strategy_name = best_strategy_name
            self.current_strategy = self.strategies[best_strategy_name]
    
    def get_strategy_performance(self) -> Dict[str, List[float]]:
        """获取策略性能历史"""
        return self.strategy_performance.copy()
    
    def get_current_strategy(self) -> str:
        """获取当前策略名称"""
        return self.current_strategy_name


def create_strategy(policy: CacheEvictionPolicy, max_size: int = 1000, **kwargs) -> CacheStrategy:
    """策略工厂函数"""
    if policy == CacheEvictionPolicy.LRU:
        return LRUStrategy(max_size)
    elif policy == CacheEvictionPolicy.LFU:
        return LFUStrategy(max_size)
    elif policy == CacheEvictionPolicy.TTL:
        default_ttl = kwargs.get('default_ttl', timedelta(hours=1))
        return TTLStrategy(max_size, default_ttl)
    elif policy == CacheEvictionPolicy.ADAPTIVE:
        evaluation_interval = kwargs.get('evaluation_interval', 1000)
        return AdaptiveStrategy(max_size, evaluation_interval)
    else:
        raise ValueError(f"不支持的策略: {policy}")


# 策略组合器
class CombinedStrategy(CacheStrategy):
    """组合策略
    
    可以组合多个策略，例如先按TTL清理过期项，再按LRU清理空间。
    """
    
    def __init__(self, strategies: List[CacheStrategy], max_size: int = 1000):
        super().__init__(max_size)
        self.strategies = strategies
    
    def should_evict(self, current_size: int) -> bool:
        """任何一个策略认为需要淘汰就淘汰"""
        return any(strategy.should_evict(current_size) for strategy in self.strategies)
    
    def select_victim(self) -> Optional[CacheKey]:
        """按策略顺序选择受害者"""
        for strategy in self.strategies:
            victim = strategy.select_victim()
            if victim is not None:
                return victim
        return None
    
    def on_access(self, key: CacheKey, value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies:
            strategy.on_access(key, value)
        
        self.metrics.access_count += 1
        self.metrics.hit_count += 1
        self.metrics.last_access_time = datetime.now(timezone.utc)
    
    def on_insert(self, key: CacheKey, value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies:
            strategy.on_insert(key, value)
        
        self.metrics.access_count += 1
    
    def on_update(self, key: CacheKey, old_value: CacheValue, new_value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies:
            strategy.on_update(key, old_value, new_value)
    
    def on_remove(self, key: CacheKey, value: CacheValue) -> None:
        """通知所有策略"""
        for strategy in self.strategies:
            strategy.on_remove(key, value)
        
        self.metrics.eviction_count += 1
    
    def clear(self) -> None:
        """清空所有策略状态"""
        for strategy in self.strategies:
            strategy.clear() 