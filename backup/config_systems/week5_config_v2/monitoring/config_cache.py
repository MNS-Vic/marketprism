#!/usr/bin/env python3
"""
MarketPrism 智能配置缓存系统
配置管理系统 2.0 - Week 5 Day 5

高性能多层配置缓存系统，提供智能缓存策略、自动预加载、
缓存一致性管理和性能优化功能。

Author: MarketPrism团队
Created: 2025-01-29
Version: 1.0.0
"""

import time
import threading
import hashlib
import pickle
import json
import gzip
import os
import weakref
from typing import Dict, Any, List, Optional, Callable, Union, Tuple, TypeVar, Generic
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict, deque, OrderedDict
import asyncio
import concurrent.futures
from abc import ABC, abstractmethod
import uuid
import psutil
from pathlib import Path

# 导入性能监控器
from .config_performance_monitor import (
    ConfigPerformanceMonitor, 
    MetricType, 
    get_performance_monitor,
    monitor_performance
)

T = TypeVar('T')


class CacheStrategy(Enum):
    """缓存策略"""
    LRU = auto()          # 最近最少使用
    LFU = auto()          # 最少频率使用
    TTL = auto()          # 生存时间
    ADAPTIVE = auto()     # 自适应策略
    WRITE_THROUGH = auto() # 写透策略
    WRITE_BACK = auto()   # 写回策略
    WRITE_AROUND = auto() # 写绕过策略


class CacheLevel(Enum):
    """缓存级别"""
    L1_MEMORY = auto()    # L1 内存缓存
    L2_COMPRESSED = auto() # L2 压缩缓存
    L3_DISK = auto()      # L3 磁盘缓存
    L4_DISTRIBUTED = auto() # L4 分布式缓存


class CacheConsistencyMode(Enum):
    """缓存一致性模式"""
    STRONG = auto()       # 强一致性
    EVENTUAL = auto()     # 最终一致性
    WEAK = auto()         # 弱一致性


class CachePriority(Enum):
    """缓存优先级"""
    CRITICAL = 1          # 关键配置
    HIGH = 2             # 高优先级
    NORMAL = 3           # 普通优先级
    LOW = 4              # 低优先级


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    ttl: Optional[float] = None  # 秒
    priority: CachePriority = CachePriority.NORMAL
    size_bytes: int = 0
    checksum: str = ""
    tags: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.checksum:
            self.checksum = self._calculate_checksum()
        if not self.size_bytes:
            self.size_bytes = self._calculate_size()
            
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl is None:
            return False
        return (datetime.now() - self.created_at).total_seconds() > self.ttl
        
    def touch(self):
        """更新访问时间和计数"""
        self.last_accessed = datetime.now()
        self.access_count += 1
        
    def _calculate_checksum(self) -> str:
        """计算校验和"""
        try:
            data = pickle.dumps(self.value)
            return hashlib.md5(data).hexdigest()
        except Exception:
            return ""
            
    def _calculate_size(self) -> int:
        """计算大小"""
        try:
            return len(pickle.dumps(self.value))
        except Exception:
            return 0
            
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "key": self.key,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "ttl": self.ttl,
            "priority": self.priority.name,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "tags": self.tags,
            "is_expired": self.is_expired()
        }


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    memory_usage: int = 0
    entry_count: int = 0
    avg_access_time_ms: float = 0.0
    hit_rate: float = 0.0
    
    def calculate_hit_rate(self):
        """计算命中率"""
        total = self.hits + self.misses
        self.hit_rate = self.hits / total if total > 0 else 0.0
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class CacheProvider(ABC, Generic[T]):
    """缓存提供者抽象基类"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[T]:
        """获取缓存值"""
        pass
        
    @abstractmethod
    def put(self, key: str, value: T, ttl: Optional[float] = None) -> bool:
        """设置缓存值"""
        pass
        
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存项"""
        pass
        
    @abstractmethod
    def clear(self):
        """清空缓存"""
        pass
        
    @abstractmethod
    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        pass


class MemoryCacheProvider(CacheProvider[T]):
    """内存缓存提供者"""
    
    def __init__(self, 
                 max_size: int = 10000,
                 default_ttl: Optional[float] = None,
                 strategy: CacheStrategy = CacheStrategy.LRU):
        """初始化内存缓存
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认TTL（秒）
            strategy: 缓存策略
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy
        
        # 缓存存储
        if strategy == CacheStrategy.LRU:
            self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        else:
            self._cache: Dict[str, CacheEntry] = {}
            
        # 统计信息
        self._stats = CacheStats()
        self._lock = threading.RLock()
        
        # 性能监控
        self._monitor = get_performance_monitor()
        
    @monitor_performance("cache", "get")
    def get(self, key: str) -> Optional[T]:
        """获取缓存值"""
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats.misses += 1
                self._stats.calculate_hit_rate()
                return None
                
            # 检查过期
            if entry.is_expired():
                del self._cache[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                self._stats.calculate_hit_rate()
                return None
                
            # 更新访问信息
            entry.touch()
            
            # LRU策略：移到末尾
            if self.strategy == CacheStrategy.LRU and isinstance(self._cache, OrderedDict):
                self._cache.move_to_end(key)
                
            self._stats.hits += 1
            self._stats.calculate_hit_rate()
            
            # 记录性能指标
            self._monitor.record_metric(
                MetricType.CACHE_HIT_RATE,
                self._stats.hit_rate,
                "memory_cache",
                "get",
                "ratio"
            )
            
            return entry.value
            
    @monitor_performance("cache", "put")
    def put(self, key: str, value: T, ttl: Optional[float] = None) -> bool:
        """设置缓存值"""
        with self._lock:
            try:
                # 使用默认TTL
                if ttl is None:
                    ttl = self.default_ttl
                    
                # 创建缓存条目
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    last_accessed=datetime.now(),
                    ttl=ttl
                )
                
                # 检查是否需要淘汰
                if len(self._cache) >= self.max_size:
                    self._evict_entries()
                    
                # 存储条目
                self._cache[key] = entry
                
                # 更新统计
                self._update_memory_stats()
                
                return True
                
            except Exception as e:
                print(f"Error putting cache entry: {e}")
                return False
                
    def delete(self, key: str) -> bool:
        """删除缓存项"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._update_memory_stats()
                return True
            return False
            
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = CacheStats()
            
    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        with self._lock:
            self._update_memory_stats()
            return self._stats
            
    def _evict_entries(self):
        """淘汰缓存条目"""
        if self.strategy == CacheStrategy.LRU and isinstance(self._cache, OrderedDict):
            # LRU: 删除最老的条目
            self._cache.popitem(last=False)
        elif self.strategy == CacheStrategy.LFU:
            # LFU: 删除访问次数最少的条目
            min_key = min(self._cache.keys(), 
                         key=lambda k: self._cache[k].access_count)
            del self._cache[min_key]
        else:
            # 默认：删除最老的条目
            if self._cache:
                oldest_key = min(self._cache.keys(), 
                               key=lambda k: self._cache[k].created_at)
                del self._cache[oldest_key]
                
        self._stats.evictions += 1
        
    def _update_memory_stats(self):
        """更新内存统计"""
        self._stats.entry_count = len(self._cache)
        self._stats.memory_usage = sum(entry.size_bytes for entry in self._cache.values())


class CompressedCacheProvider(CacheProvider[T]):
    """压缩缓存提供者"""
    
    def __init__(self, 
                 max_size: int = 5000,
                 compression_level: int = 6):
        """初始化压缩缓存
        
        Args:
            max_size: 最大缓存条目数
            compression_level: 压缩级别 (1-9)
        """
        self.max_size = max_size
        self.compression_level = compression_level
        
        self._cache: Dict[str, bytes] = {}
        self._metadata: Dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        self._lock = threading.RLock()
        
        # 性能监控
        self._monitor = get_performance_monitor()
        
    @monitor_performance("compressed_cache", "get")
    def get(self, key: str) -> Optional[T]:
        """获取缓存值"""
        with self._lock:
            if key not in self._cache:
                self._stats.misses += 1
                self._stats.calculate_hit_rate()
                return None
                
            try:
                # 解压缩和反序列化
                compressed_data = self._cache[key]
                decompressed_data = gzip.decompress(compressed_data)
                value = pickle.loads(decompressed_data)
                
                # 更新元数据
                if key in self._metadata:
                    self._metadata[key].touch()
                    
                self._stats.hits += 1
                self._stats.calculate_hit_rate()
                
                return value
                
            except Exception as e:
                print(f"Error decompressing cache entry: {e}")
                # 删除损坏的条目
                self.delete(key)
                self._stats.misses += 1
                self._stats.calculate_hit_rate()
                return None
                
    @monitor_performance("compressed_cache", "put")
    def put(self, key: str, value: T, ttl: Optional[float] = None) -> bool:
        """设置缓存值"""
        with self._lock:
            try:
                # 序列化和压缩
                serialized_data = pickle.dumps(value)
                compressed_data = gzip.compress(serialized_data, self.compression_level)
                
                # 检查大小限制
                if len(self._cache) >= self.max_size:
                    self._evict_oldest()
                    
                # 存储压缩数据
                self._cache[key] = compressed_data
                
                # 存储元数据
                self._metadata[key] = CacheEntry(
                    key=key,
                    value=None,  # 不存储原始值
                    created_at=datetime.now(),
                    last_accessed=datetime.now(),
                    ttl=ttl,
                    size_bytes=len(compressed_data)
                )
                
                self._update_stats()
                return True
                
            except Exception as e:
                print(f"Error compressing cache entry: {e}")
                return False
                
    def delete(self, key: str) -> bool:
        """删除缓存项"""
        with self._lock:
            deleted = False
            if key in self._cache:
                del self._cache[key]
                deleted = True
            if key in self._metadata:
                del self._metadata[key]
                deleted = True
            
            if deleted:
                self._update_stats()
            return deleted
            
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._metadata.clear()
            self._stats = CacheStats()
            
    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        with self._lock:
            self._update_stats()
            return self._stats
            
    def _evict_oldest(self):
        """淘汰最旧的条目"""
        if not self._metadata:
            return
            
        oldest_key = min(self._metadata.keys(), 
                        key=lambda k: self._metadata[k].created_at)
        self.delete(oldest_key)
        self._stats.evictions += 1
        
    def _update_stats(self):
        """更新统计信息"""
        self._stats.entry_count = len(self._cache)
        self._stats.memory_usage = sum(len(data) for data in self._cache.values())


class DiskCacheProvider(CacheProvider[T]):
    """磁盘缓存提供者"""
    
    def __init__(self, 
                 cache_dir: str = "./cache",
                 max_size_mb: int = 1000):
        """初始化磁盘缓存
        
        Args:
            cache_dir: 缓存目录
            max_size_mb: 最大缓存大小（MB）
        """
        self.cache_dir = Path(cache_dir)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        
        # 创建缓存目录
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._metadata: Dict[str, CacheEntry] = {}
        self._stats = CacheStats()
        self._lock = threading.RLock()
        
        # 加载现有缓存
        self._load_existing_cache()
        
        # 性能监控
        self._monitor = get_performance_monitor()
        
    @monitor_performance("disk_cache", "get")
    def get(self, key: str) -> Optional[T]:
        """获取缓存值"""
        with self._lock:
            if key not in self._metadata:
                self._stats.misses += 1
                self._stats.calculate_hit_rate()
                return None
                
            entry = self._metadata[key]
            
            # 检查过期
            if entry.is_expired():
                self.delete(key)
                self._stats.misses += 1
                self._stats.calculate_hit_rate()
                return None
                
            try:
                # 从文件读取
                file_path = self._get_file_path(key)
                with open(file_path, 'rb') as f:
                    value = pickle.load(f)
                    
                # 更新访问信息
                entry.touch()
                
                self._stats.hits += 1
                self._stats.calculate_hit_rate()
                
                return value
                
            except Exception as e:
                print(f"Error reading from disk cache: {e}")
                self.delete(key)
                self._stats.misses += 1
                self._stats.calculate_hit_rate()
                return None
                
    @monitor_performance("disk_cache", "put")
    def put(self, key: str, value: T, ttl: Optional[float] = None) -> bool:
        """设置缓存值"""
        with self._lock:
            try:
                # 检查磁盘空间
                if self._get_total_size() >= self.max_size_bytes:
                    self._cleanup_space()
                    
                # 写入文件
                file_path = self._get_file_path(key)
                with open(file_path, 'wb') as f:
                    pickle.dump(value, f)
                    
                # 更新元数据
                file_size = file_path.stat().st_size
                self._metadata[key] = CacheEntry(
                    key=key,
                    value=None,  # 不在内存中存储值
                    created_at=datetime.now(),
                    last_accessed=datetime.now(),
                    ttl=ttl,
                    size_bytes=file_size
                )
                
                self._update_stats()
                return True
                
            except Exception as e:
                print(f"Error writing to disk cache: {e}")
                return False
                
    def delete(self, key: str) -> bool:
        """删除缓存项"""
        with self._lock:
            if key not in self._metadata:
                return False
                
            try:
                file_path = self._get_file_path(key)
                if file_path.exists():
                    file_path.unlink()
                    
                del self._metadata[key]
                self._update_stats()
                return True
                
            except Exception as e:
                print(f"Error deleting from disk cache: {e}")
                return False
                
    def clear(self):
        """清空缓存"""
        with self._lock:
            try:
                # 删除所有缓存文件
                for file_path in self.cache_dir.glob("*.cache"):
                    file_path.unlink()
                    
                self._metadata.clear()
                self._stats = CacheStats()
                
            except Exception as e:
                print(f"Error clearing disk cache: {e}")
                
    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        with self._lock:
            self._update_stats()
            return self._stats
            
    def _get_file_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用MD5哈希避免文件名冲突
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"
        
    def _load_existing_cache(self):
        """加载现有缓存"""
        try:
            for file_path in self.cache_dir.glob("*.cache"):
                try:
                    stat = file_path.stat()
                    # 从文件名反推key可能不现实，这里只记录文件信息
                    # 实际应用中可能需要额外的元数据文件
                    pass
                except Exception:
                    continue
        except Exception as e:
            print(f"Error loading existing cache: {e}")
            
    def _get_total_size(self) -> int:
        """获取总缓存大小"""
        return sum(entry.size_bytes for entry in self._metadata.values())
        
    def _cleanup_space(self):
        """清理空间"""
        # 删除最旧的文件直到有足够空间
        sorted_entries = sorted(
            self._metadata.items(),
            key=lambda x: x[1].last_accessed
        )
        
        total_size = self._get_total_size()
        target_size = self.max_size_bytes * 0.8  # 清理到80%
        
        for key, entry in sorted_entries:
            if total_size <= target_size:
                break
                
            self.delete(key)
            total_size -= entry.size_bytes
            self._stats.evictions += 1
            
    def _update_stats(self):
        """更新统计信息"""
        self._stats.entry_count = len(self._metadata)
        self._stats.memory_usage = self._get_total_size()


class MultiLevelConfigCache:
    """多层配置缓存系统
    
    提供L1内存缓存、L2压缩缓存、L3磁盘缓存的多层架构，
    自动在不同层级间进行数据迁移和优化。
    """
    
    def __init__(self,
                 l1_size: int = 1000,
                 l2_size: int = 5000,
                 l3_size_mb: int = 1000,
                 cache_dir: str = "./cache"):
        """初始化多层缓存
        
        Args:
            l1_size: L1缓存大小（条目数）
            l2_size: L2缓存大小（条目数）
            l3_size_mb: L3缓存大小（MB）
            cache_dir: 磁盘缓存目录
        """
        # 初始化各层缓存
        self.l1_cache = MemoryCacheProvider[Any](
            max_size=l1_size,
            strategy=CacheStrategy.LRU
        )
        
        self.l2_cache = CompressedCacheProvider[Any](
            max_size=l2_size,
            compression_level=6
        )
        
        self.l3_cache = DiskCacheProvider[Any](
            cache_dir=cache_dir,
            max_size_mb=l3_size_mb
        )
        
        # 预加载配置
        self._preload_keys: set = set()
        self._preload_patterns: List[str] = []
        
        # 统计信息
        self._global_stats = CacheStats()
        self._lock = threading.RLock()
        
        # 性能监控
        self._monitor = get_performance_monitor()
        
        # 后台任务
        self._background_tasks_enabled = True
        self._background_thread: Optional[threading.Thread] = None
        self._start_background_tasks()
        
    @monitor_performance("multi_level_cache", "get")
    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        start_time = time.perf_counter()
        
        try:
            # L1缓存查找
            value = self.l1_cache.get(key)
            if value is not None:
                self._record_cache_hit("L1", start_time)
                return value
                
            # L2缓存查找
            value = self.l2_cache.get(key)
            if value is not None:
                # 提升到L1
                self.l1_cache.put(key, value)
                self._record_cache_hit("L2", start_time)
                return value
                
            # L3缓存查找
            value = self.l3_cache.get(key)
            if value is not None:
                # 提升到L2和L1
                self.l2_cache.put(key, value)
                self.l1_cache.put(key, value)
                self._record_cache_hit("L3", start_time)
                return value
                
            # 缓存未命中
            self._record_cache_miss(start_time)
            return default
            
        except Exception as e:
            print(f"Error getting from multi-level cache: {e}")
            return default
            
    @monitor_performance("multi_level_cache", "put")
    def put(self, 
           key: str, 
           value: T, 
           ttl: Optional[float] = None,
           priority: CachePriority = CachePriority.NORMAL) -> bool:
        """设置配置值
        
        Args:
            key: 配置键
            value: 配置值
            ttl: 生存时间（秒）
            priority: 缓存优先级
            
        Returns:
            是否成功
        """
        try:
            success = True
            
            # 根据优先级决定存储层级
            if priority in [CachePriority.CRITICAL, CachePriority.HIGH]:
                # 高优先级：存储到所有层级
                success &= self.l1_cache.put(key, value, ttl)
                success &= self.l2_cache.put(key, value, ttl)
                success &= self.l3_cache.put(key, value, ttl)
            elif priority == CachePriority.NORMAL:
                # 普通优先级：存储到L1和L2
                success &= self.l1_cache.put(key, value, ttl)
                success &= self.l2_cache.put(key, value, ttl)
            else:
                # 低优先级：只存储到L2
                success &= self.l2_cache.put(key, value, ttl)
                
            return success
            
        except Exception as e:
            print(f"Error putting to multi-level cache: {e}")
            return False
            
    def delete(self, key: str) -> bool:
        """删除配置项"""
        success = True
        success &= self.l1_cache.delete(key)
        success &= self.l2_cache.delete(key)
        success &= self.l3_cache.delete(key)
        return success
        
    def clear(self):
        """清空所有缓存"""
        self.l1_cache.clear()
        self.l2_cache.clear()
        self.l3_cache.clear()
        
    def preload(self, keys: List[str]):
        """预加载配置键"""
        with self._lock:
            self._preload_keys.update(keys)
            
    def add_preload_pattern(self, pattern: str):
        """添加预加载模式"""
        with self._lock:
            self._preload_patterns.append(pattern)
            
    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        l1_stats = self.l1_cache.get_stats()
        l2_stats = self.l2_cache.get_stats()
        l3_stats = self.l3_cache.get_stats()
        
        total_hits = l1_stats.hits + l2_stats.hits + l3_stats.hits
        total_misses = l1_stats.misses + l2_stats.misses + l3_stats.misses
        total_requests = total_hits + total_misses
        
        return {
            "total_requests": total_requests,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "global_hit_rate": total_hits / total_requests if total_requests > 0 else 0,
            "l1_stats": l1_stats.to_dict(),
            "l2_stats": l2_stats.to_dict(),
            "l3_stats": l3_stats.to_dict(),
            "cache_distribution": {
                "l1_entries": l1_stats.entry_count,
                "l2_entries": l2_stats.entry_count,
                "l3_entries": l3_stats.entry_count
            },
            "memory_usage": {
                "l1_bytes": l1_stats.memory_usage,
                "l2_bytes": l2_stats.memory_usage,
                "l3_bytes": l3_stats.memory_usage,
                "total_bytes": l1_stats.memory_usage + l2_stats.memory_usage + l3_stats.memory_usage
            }
        }
        
    def optimize_cache(self):
        """优化缓存"""
        # 获取统计信息
        stats = self.get_global_stats()
        
        # 如果L1命中率太低，考虑调整策略
        if stats["l1_stats"]["hit_rate"] < 0.5:
            print("Warning: L1 cache hit rate is low, consider adjusting cache size or strategy")
            
        # 如果内存使用过高，触发清理
        process = psutil.Process()
        memory_percent = process.memory_percent()
        if memory_percent > 80:
            print("Warning: High memory usage, triggering cache cleanup")
            self._cleanup_low_priority_items()
            
    def _record_cache_hit(self, level: str, start_time: float):
        """记录缓存命中"""
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # 记录性能指标
        self._monitor.record_metric(
            MetricType.LATENCY,
            duration_ms,
            f"{level.lower()}_cache",
            "get",
            "ms",
            {"result": "hit"}
        )
        
    def _record_cache_miss(self, start_time: float):
        """记录缓存未命中"""
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # 记录性能指标
        self._monitor.record_metric(
            MetricType.LATENCY,
            duration_ms,
            "multi_level_cache",
            "get",
            "ms",
            {"result": "miss"}
        )
        
    def _start_background_tasks(self):
        """启动后台任务"""
        self._background_thread = threading.Thread(
            target=self._background_worker,
            daemon=True,
            name="CacheBackgroundWorker"
        )
        self._background_thread.start()
        
    def _background_worker(self):
        """后台工作线程"""
        while self._background_tasks_enabled:
            try:
                # 定期优化缓存
                self.optimize_cache()
                
                # 清理过期项
                self._cleanup_expired_items()
                
                # 执行预加载
                self._execute_preload()
                
                time.sleep(60)  # 每分钟执行一次
                
            except Exception as e:
                print(f"Error in background worker: {e}")
                time.sleep(60)
                
    def _cleanup_expired_items(self):
        """清理过期项"""
        # 注意：这里只是示例，实际需要根据具体缓存实现来清理
        pass
        
    def _cleanup_low_priority_items(self):
        """清理低优先级项"""
        # 注意：这里只是示例，实际需要根据具体缓存实现来清理
        pass
        
    def _execute_preload(self):
        """执行预加载"""
        # 注意：这里只是示例，实际需要从配置源加载数据
        pass
        
    def stop(self):
        """停止缓存系统"""
        self._background_tasks_enabled = False
        if self._background_thread:
            self._background_thread.join(timeout=5.0)


# 全局缓存实例
_global_cache: Optional[MultiLevelConfigCache] = None


def get_config_cache() -> MultiLevelConfigCache:
    """获取全局配置缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = MultiLevelConfigCache()
    return _global_cache


def cache_config(key: str, ttl: Optional[float] = None, priority: CachePriority = CachePriority.NORMAL):
    """配置缓存装饰器
    
    Args:
        key: 缓存键
        ttl: 生存时间
        priority: 缓存优先级
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache = get_config_cache()
            
            # 尝试从缓存获取
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value
                
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache.put(key, result, ttl, priority)
            return result
            
        return wrapper
    return decorator


# 使用示例
if __name__ == "__main__":
    import random
    
    # 创建多层缓存
    cache = MultiLevelConfigCache(
        l1_size=100,
        l2_size=500,
        l3_size_mb=100
    )
    
    # 测试缓存操作
    print("=== 配置缓存测试 ===")
    
    # 存储一些配置
    config_data = {
        "database.host": "localhost",
        "database.port": 5432,
        "api.timeout": 30,
        "cache.ttl": 3600
    }
    
    for key, value in config_data.items():
        cache.put(key, value, ttl=300, priority=CachePriority.HIGH)
        print(f"✓ 存储配置: {key} = {value}")
        
    # 测试读取
    print("\n=== 缓存读取测试 ===")
    for key in config_data.keys():
        value = cache.get(key)
        print(f"✓ 读取配置: {key} = {value}")
        
    # 测试缓存装饰器
    @cache_config("expensive_operation", ttl=60)
    def expensive_operation():
        print("执行耗时操作...")
        time.sleep(0.1)
        return random.randint(1, 1000)
        
    print("\n=== 缓存装饰器测试 ===")
    for i in range(3):
        result = expensive_operation()
        print(f"第{i+1}次调用结果: {result}")
        
    # 显示统计信息
    print("\n=== 缓存统计信息 ===")
    stats = cache.get_global_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    # 停止缓存
    cache.stop()
    
    print("\n✅ 智能配置缓存系统演示完成")