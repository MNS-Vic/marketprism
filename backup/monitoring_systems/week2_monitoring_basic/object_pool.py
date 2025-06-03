"""
对象池管理系统 - 第二阶段性能优化第二天实施

提供企业级对象池管理功能，包括泛型对象池和消息对象池
符合MarketPrism性能调优方案 v2.0
"""

import threading
import time
import weakref
from typing import TypeVar, Generic, Callable, Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
import structlog
from abc import ABC, abstractmethod

# 导入内存分析器用于监控
from .memory_profiler import get_memory_profiler, take_memory_snapshot

T = TypeVar('T')


@dataclass
class PoolStatistics:
    """对象池统计信息"""
    pool_name: str
    max_size: int
    current_size: int
    active_objects: int
    total_created: int = 0
    total_acquired: int = 0
    total_returned: int = 0
    total_reused: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    creation_time_total: float = 0.0
    last_reset_time: float = field(default_factory=time.time)
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0
    
    @property
    def utilization_rate(self) -> float:
        """池利用率"""
        return self.active_objects / self.max_size if self.max_size > 0 else 0.0
    
    @property
    def reuse_rate(self) -> float:
        """对象复用率"""
        return self.total_reused / self.total_created if self.total_created > 0 else 0.0
    
    @property
    def average_creation_time(self) -> float:
        """平均对象创建时间"""
        return self.creation_time_total / self.total_created if self.total_created > 0 else 0.0


class PoolableObject(ABC):
    """可池化对象接口"""
    
    @abstractmethod
    def reset(self) -> None:
        """重置对象状态，准备复用"""
        pass
    
    @abstractmethod
    def is_valid(self) -> bool:
        """检查对象是否有效"""
        pass


class ObjectPool(Generic[T]):
    """泛型对象池 - 企业级对象管理"""
    
    def __init__(
        self,
        name: str,
        factory: Callable[[], T],
        max_size: int = 100,
        reset_func: Optional[Callable[[T], None]] = None,
        validator: Optional[Callable[[T], bool]] = None,
        enable_monitoring: bool = True
    ):
        self.name = name
        self.factory = factory
        self.max_size = max_size
        self.reset_func = reset_func
        self.validator = validator or (lambda obj: True)
        self.enable_monitoring = enable_monitoring
        
        # 对象存储
        self._pool: deque[T] = deque()
        self._active_objects: weakref.WeakSet[T] = weakref.WeakSet()
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 统计信息
        self.stats = PoolStatistics(
            pool_name=name,
            max_size=max_size,
            current_size=0,
            active_objects=0
        )
        
        # 日志
        self.logger = structlog.get_logger(__name__)
        
        # 内存监控
        if self.enable_monitoring:
            self._memory_profiler = get_memory_profiler()
        
        self.logger.info(
            "对象池已创建",
            pool_name=name,
            max_size=max_size,
            monitoring_enabled=enable_monitoring
        )
    
    def acquire(self) -> T:
        """获取对象"""
        start_time = time.time()
        
        with self._lock:
            # 尝试从池中获取对象
            if self._pool:
                obj = self._pool.popleft()
                self.stats.current_size -= 1
                self.stats.cache_hits += 1
                self.stats.total_reused += 1
                
                # 验证对象有效性
                if self.validator(obj):
                    self._active_objects.add(obj)
                    self.stats.active_objects = len(self._active_objects)
                    self.stats.total_acquired += 1
                    
                    self.logger.debug(
                        "从池中获取对象",
                        pool_name=self.name,
                        cache_hit=True,
                        pool_size=self.stats.current_size
                    )
                    
                    return obj
                else:
                    # 对象无效，丢弃并创建新对象
                    self.logger.warning(
                        "池中对象无效，丢弃",
                        pool_name=self.name
                    )
            
            # 池为空或对象无效，创建新对象
            self.stats.cache_misses += 1
            obj = self._create_new_object(start_time)
            
            self._active_objects.add(obj)
            self.stats.active_objects = len(self._active_objects)
            self.stats.total_acquired += 1
            
            return obj
    
    def release(self, obj: T) -> bool:
        """归还对象到池"""
        if obj is None:
            return False
        
        with self._lock:
            # 检查对象是否来自此池
            if obj not in self._active_objects:
                self.logger.warning(
                    "尝试归还不属于此池的对象",
                    pool_name=self.name
                )
                return False
            
            # 从活跃对象中移除
            self._active_objects.discard(obj)
            self.stats.active_objects = len(self._active_objects)
            
            # 检查池是否已满
            if self.stats.current_size >= self.max_size:
                self.logger.debug(
                    "对象池已满，丢弃对象",
                    pool_name=self.name,
                    pool_size=self.stats.current_size
                )
                return False
            
            # 重置对象状态
            try:
                if hasattr(obj, 'reset') and callable(obj.reset):
                    obj.reset()
                elif self.reset_func:
                    self.reset_func(obj)
                
                # 验证重置后的对象
                if self.validator(obj):
                    self._pool.append(obj)
                    self.stats.current_size += 1
                    self.stats.total_returned += 1
                    
                    self.logger.debug(
                        "对象已归还到池",
                        pool_name=self.name,
                        pool_size=self.stats.current_size
                    )
                    
                    return True
                else:
                    self.logger.warning(
                        "重置后对象无效，丢弃",
                        pool_name=self.name
                    )
                    return False
                    
            except Exception as e:
                self.logger.error(
                    "重置对象失败",
                    pool_name=self.name,
                    error=str(e)
                )
                return False
    
    def _create_new_object(self, start_time: float) -> T:
        """创建新对象"""
        try:
            obj = self.factory()
            creation_time = time.time() - start_time
            
            self.stats.total_created += 1
            self.stats.creation_time_total += creation_time
            
            self.logger.debug(
                "创建新对象",
                pool_name=self.name,
                creation_time_ms=creation_time * 1000,
                total_created=self.stats.total_created
            )
            
            return obj
            
        except Exception as e:
            self.logger.error(
                "创建对象失败",
                pool_name=self.name,
                error=str(e)
            )
            raise
    
    def clear(self) -> int:
        """清空对象池"""
        with self._lock:
            cleared_count = len(self._pool)
            self._pool.clear()
            self.stats.current_size = 0
            
            self.logger.info(
                "对象池已清空",
                pool_name=self.name,
                cleared_objects=cleared_count
            )
            
            return cleared_count
    
    def get_statistics(self) -> PoolStatistics:
        """获取池统计信息"""
        with self._lock:
            # 更新当前活跃对象数
            self.stats.active_objects = len(self._active_objects)
            return self.stats
    
    def take_memory_snapshot(self, label: str = "") -> None:
        """拍摄内存快照"""
        if self.enable_monitoring and self._memory_profiler:
            snapshot_label = f"{self.name}_{label}" if label else self.name
            take_memory_snapshot(snapshot_label)
    
    def __len__(self) -> int:
        """返回池中对象数量"""
        return self.stats.current_size
    
    def __repr__(self) -> str:
        return (
            f"ObjectPool(name='{self.name}', "
            f"size={self.stats.current_size}/{self.max_size}, "
            f"active={self.stats.active_objects}, "
            f"hit_rate={self.stats.hit_rate:.2%})"
        )


class MessageObjectPool:
    """消息对象专用池管理器"""
    
    def __init__(self, enable_monitoring: bool = True):
        self.enable_monitoring = enable_monitoring
        self.logger = structlog.get_logger(__name__)
        
        # 各类型消息对象池
        self._pools: Dict[str, ObjectPool] = {}
        
        # 初始化各种消息对象池
        self._init_message_pools()
        
        self.logger.info(
            "消息对象池管理器已初始化",
            pools_count=len(self._pools),
            monitoring_enabled=enable_monitoring
        )
    
    def _init_message_pools(self):
        """初始化各种消息对象池"""
        # 由于我们无法直接导入具体的消息类型，我们使用字典来模拟
        # 在实际使用中，这里会导入真实的消息类型
        
        # 交易数据对象池
        self._pools['trade'] = ObjectPool(
            name='trade_pool',
            factory=lambda: self._create_trade_object(),
            max_size=200,
            reset_func=self._reset_trade_object,
            validator=self._validate_trade_object,
            enable_monitoring=self.enable_monitoring
        )
        
        # 订单簿对象池
        self._pools['orderbook'] = ObjectPool(
            name='orderbook_pool',
            factory=lambda: self._create_orderbook_object(),
            max_size=100,
            reset_func=self._reset_orderbook_object,
            validator=self._validate_orderbook_object,
            enable_monitoring=self.enable_monitoring
        )
        
        # K线数据对象池
        self._pools['kline'] = ObjectPool(
            name='kline_pool',
            factory=lambda: self._create_kline_object(),
            max_size=150,
            reset_func=self._reset_kline_object,
            validator=self._validate_kline_object,
            enable_monitoring=self.enable_monitoring
        )
        
        # 行情数据对象池
        self._pools['ticker'] = ObjectPool(
            name='ticker_pool',
            factory=lambda: self._create_ticker_object(),
            max_size=100,
            reset_func=self._reset_ticker_object,
            validator=self._validate_ticker_object,
            enable_monitoring=self.enable_monitoring
        )
    
    def _create_trade_object(self) -> Dict[str, Any]:
        """创建交易对象（模拟）"""
        return {
            'type': 'trade',
            'exchange_name': '',
            'symbol_name': '',
            'price': 0.0,
            'quantity': 0.0,
            'timestamp': 0,
            'side': '',
            'trade_id': '',
            'created_at': time.time()
        }
    
    def _reset_trade_object(self, obj: Dict[str, Any]) -> None:
        """重置交易对象"""
        obj.update({
            'exchange_name': '',
            'symbol_name': '',
            'price': 0.0,
            'quantity': 0.0,
            'timestamp': 0,
            'side': '',
            'trade_id': '',
            'created_at': time.time()
        })
    
    def _validate_trade_object(self, obj: Dict[str, Any]) -> bool:
        """验证交易对象"""
        return isinstance(obj, dict) and obj.get('type') == 'trade'
    
    def _create_orderbook_object(self) -> Dict[str, Any]:
        """创建订单簿对象（模拟）"""
        return {
            'type': 'orderbook',
            'exchange_name': '',
            'symbol_name': '',
            'bids': [],
            'asks': [],
            'timestamp': 0,
            'created_at': time.time()
        }
    
    def _reset_orderbook_object(self, obj: Dict[str, Any]) -> None:
        """重置订单簿对象"""
        obj.update({
            'exchange_name': '',
            'symbol_name': '',
            'bids': [],
            'asks': [],
            'timestamp': 0,
            'created_at': time.time()
        })
    
    def _validate_orderbook_object(self, obj: Dict[str, Any]) -> bool:
        """验证订单簿对象"""
        return isinstance(obj, dict) and obj.get('type') == 'orderbook'
    
    def _create_kline_object(self) -> Dict[str, Any]:
        """创建K线对象（模拟）"""
        return {
            'type': 'kline',
            'exchange_name': '',
            'symbol_name': '',
            'interval': '',
            'open_price': 0.0,
            'high_price': 0.0,
            'low_price': 0.0,
            'close_price': 0.0,
            'volume': 0.0,
            'timestamp': 0,
            'created_at': time.time()
        }
    
    def _reset_kline_object(self, obj: Dict[str, Any]) -> None:
        """重置K线对象"""
        obj.update({
            'exchange_name': '',
            'symbol_name': '',
            'interval': '',
            'open_price': 0.0,
            'high_price': 0.0,
            'low_price': 0.0,
            'close_price': 0.0,
            'volume': 0.0,
            'timestamp': 0,
            'created_at': time.time()
        })
    
    def _validate_kline_object(self, obj: Dict[str, Any]) -> bool:
        """验证K线对象"""
        return isinstance(obj, dict) and obj.get('type') == 'kline'
    
    def _create_ticker_object(self) -> Dict[str, Any]:
        """创建行情对象（模拟）"""
        return {
            'type': 'ticker',
            'exchange_name': '',
            'symbol_name': '',
            'last_price': 0.0,
            'volume': 0.0,
            'price_change': 0.0,
            'price_change_percent': 0.0,
            'timestamp': 0,
            'created_at': time.time()
        }
    
    def _reset_ticker_object(self, obj: Dict[str, Any]) -> None:
        """重置行情对象"""
        obj.update({
            'exchange_name': '',
            'symbol_name': '',
            'last_price': 0.0,
            'volume': 0.0,
            'price_change': 0.0,
            'price_change_percent': 0.0,
            'timestamp': 0,
            'created_at': time.time()
        })
    
    def _validate_ticker_object(self, obj: Dict[str, Any]) -> bool:
        """验证行情对象"""
        return isinstance(obj, dict) and obj.get('type') == 'ticker'
    
    def acquire_trade(self) -> Dict[str, Any]:
        """获取交易对象"""
        return self._pools['trade'].acquire()
    
    def release_trade(self, obj: Dict[str, Any]) -> bool:
        """归还交易对象"""
        return self._pools['trade'].release(obj)
    
    def acquire_orderbook(self) -> Dict[str, Any]:
        """获取订单簿对象"""
        return self._pools['orderbook'].acquire()
    
    def release_orderbook(self, obj: Dict[str, Any]) -> bool:
        """归还订单簿对象"""
        return self._pools['orderbook'].release(obj)
    
    def acquire_kline(self) -> Dict[str, Any]:
        """获取K线对象"""
        return self._pools['kline'].acquire()
    
    def release_kline(self, obj: Dict[str, Any]) -> bool:
        """归还K线对象"""
        return self._pools['kline'].release(obj)
    
    def acquire_ticker(self) -> Dict[str, Any]:
        """获取行情对象"""
        return self._pools['ticker'].acquire()
    
    def release_ticker(self, obj: Dict[str, Any]) -> bool:
        """归还行情对象"""
        return self._pools['ticker'].release(obj)
    
    def get_pool_statistics(self) -> Dict[str, PoolStatistics]:
        """获取所有池的统计信息"""
        return {name: pool.get_statistics() for name, pool in self._pools.items()}
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """获取汇总统计信息"""
        all_stats = self.get_pool_statistics()
        
        total_objects = sum(stats.current_size for stats in all_stats.values())
        total_active = sum(stats.active_objects for stats in all_stats.values())
        total_created = sum(stats.total_created for stats in all_stats.values())
        total_reused = sum(stats.total_reused for stats in all_stats.values())
        
        avg_hit_rate = sum(stats.hit_rate for stats in all_stats.values()) / len(all_stats) if all_stats else 0
        avg_utilization = sum(stats.utilization_rate for stats in all_stats.values()) / len(all_stats) if all_stats else 0
        
        return {
            'pools_count': len(self._pools),
            'total_objects_in_pools': total_objects,
            'total_active_objects': total_active,
            'total_objects_created': total_created,
            'total_objects_reused': total_reused,
            'overall_reuse_rate': total_reused / total_created if total_created > 0 else 0,
            'average_hit_rate': avg_hit_rate,
            'average_utilization_rate': avg_utilization,
            'memory_savings_estimate': self._estimate_memory_savings()
        }
    
    def _estimate_memory_savings(self) -> Dict[str, float]:
        """估算内存节省"""
        all_stats = self.get_pool_statistics()
        
        # 估算每种对象的平均大小（字节）
        object_sizes = {
            'trade': 200,      # 交易对象约200字节
            'orderbook': 1000, # 订单簿对象约1KB
            'kline': 300,      # K线对象约300字节
            'ticker': 250      # 行情对象约250字节
        }
        
        total_saved_bytes = 0
        for pool_name, stats in all_stats.items():
            pool_type = pool_name.replace('_pool', '')
            if pool_type in object_sizes:
                saved_objects = stats.total_reused
                saved_bytes = saved_objects * object_sizes[pool_type]
                total_saved_bytes += saved_bytes
        
        return {
            'total_saved_bytes': total_saved_bytes,
            'total_saved_mb': total_saved_bytes / (1024 * 1024),
            'estimated_gc_pressure_reduction': min(total_saved_bytes / (1024 * 1024) * 0.1, 50.0)  # 估算GC压力减少
        }
    
    def clear_all_pools(self) -> Dict[str, int]:
        """清空所有对象池"""
        results = {}
        for name, pool in self._pools.items():
            results[name] = pool.clear()
        
        self.logger.info(
            "所有对象池已清空",
            cleared_counts=results
        )
        
        return results
    
    def take_memory_snapshot(self, label: str = "") -> None:
        """拍摄内存快照"""
        if self.enable_monitoring:
            snapshot_label = f"message_pools_{label}" if label else "message_pools"
            take_memory_snapshot(snapshot_label)
    
    def __repr__(self) -> str:
        stats = self.get_summary_statistics()
        return (
            f"MessageObjectPool("
            f"pools={stats['pools_count']}, "
            f"total_objects={stats['total_objects_in_pools']}, "
            f"reuse_rate={stats['overall_reuse_rate']:.2%}, "
            f"saved_mb={stats['memory_savings_estimate']['total_saved_mb']:.2f})"
        )


# 全局消息对象池实例
_message_pool_instance = None

def get_message_pool() -> MessageObjectPool:
    """获取全局消息对象池实例"""
    global _message_pool_instance
    if _message_pool_instance is None:
        _message_pool_instance = MessageObjectPool()
    return _message_pool_instance


# 便捷函数
def acquire_trade_object() -> Dict[str, Any]:
    """获取交易对象"""
    return get_message_pool().acquire_trade()


def release_trade_object(obj: Dict[str, Any]) -> bool:
    """归还交易对象"""
    return get_message_pool().release_trade(obj)


def acquire_orderbook_object() -> Dict[str, Any]:
    """获取订单簿对象"""
    return get_message_pool().acquire_orderbook()


def release_orderbook_object(obj: Dict[str, Any]) -> bool:
    """归还订单簿对象"""
    return get_message_pool().release_orderbook(obj)


def get_pool_summary() -> Dict[str, Any]:
    """获取对象池汇总信息"""
    return get_message_pool().get_summary_statistics()