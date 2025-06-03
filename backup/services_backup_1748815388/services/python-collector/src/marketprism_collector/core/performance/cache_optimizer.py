"""
🗄️ CacheOptimizer - 缓存优化器

智能缓存策略和多级缓存架构
提供自适应缓存、缓存预热、多级缓存、缓存分析等功能
"""

import asyncio
import time
import hashlib
import json
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import weakref
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class CacheStrategy(Enum):
    """缓存策略枚举"""
    LRU = "lru"                    # 最近最少使用
    LFU = "lfu"                    # 最少使用频率
    FIFO = "fifo"                  # 先进先出
    ADAPTIVE = "adaptive"          # 自适应策略
    TIME_BASED = "time_based"      # 基于时间
    SIZE_BASED = "size_based"      # 基于大小


class CacheLevel(Enum):
    """缓存级别枚举"""
    L1_MEMORY = "l1_memory"        # L1内存缓存
    L2_REDIS = "l2_redis"          # L2 Redis缓存
    L3_DISK = "l3_disk"           # L3磁盘缓存
    DISTRIBUTED = "distributed"    # 分布式缓存


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float
    accessed_at: float
    access_count: int = 0
    size: int = 0
    ttl: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl
    
    def update_access(self):
        """更新访问信息"""
        self.accessed_at = time.time()
        self.access_count += 1


@dataclass
class CacheStats:
    """缓存统计"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_size: int = 0
    entry_count: int = 0
    
    @property
    def hit_rate(self) -> float:
        """命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    @property
    def miss_rate(self) -> float:
        """未命中率"""
        return 1.0 - self.hit_rate


@dataclass
class CacheConfig:
    """缓存配置"""
    strategy: CacheStrategy = CacheStrategy.ADAPTIVE
    max_size: int = 10000
    max_memory: int = 100 * 1024 * 1024  # 100MB
    default_ttl: Optional[float] = 3600.0  # 1小时
    cleanup_interval: float = 300.0  # 5分钟
    preload_enabled: bool = True
    compression_enabled: bool = True
    encryption_enabled: bool = False


class CacheOptimizer:
    """
    🗄️ 缓存优化器
    
    提供智能缓存策略、多级缓存架构、缓存预热、性能分析等功能
    """
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.caches: Dict[CacheLevel, Dict[str, CacheEntry]] = {
            level: {} for level in CacheLevel
        }
        self.stats: Dict[CacheLevel, CacheStats] = {
            level: CacheStats() for level in CacheLevel
        }
        self.preload_rules: List[Callable] = []
        self.cleanup_tasks: Dict[CacheLevel, Optional[asyncio.Task]] = {
            level: None for level in CacheLevel
        }
        self.access_patterns: Dict[str, List[float]] = defaultdict(list)
        self.is_running = False
        
        logger.info(f"CacheOptimizer初始化完成: strategy={self.config.strategy.value}")
    
    async def start(self):
        """启动缓存优化器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动各级缓存的清理任务
        for level in CacheLevel:
            self.cleanup_tasks[level] = asyncio.create_task(
                self._cleanup_loop(level)
            )
        
        # 启动预热任务
        if self.config.preload_enabled:
            asyncio.create_task(self._preload_cache())
        
        logger.info("CacheOptimizer已启动")
    
    async def stop(self):
        """停止缓存优化器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消清理任务
        for task in self.cleanup_tasks.values():
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("CacheOptimizer已停止")
    
    async def get(self, key: str, level: CacheLevel = CacheLevel.L1_MEMORY) -> Optional[Any]:
        """从缓存获取数据"""
        cache = self.caches[level]
        stats = self.stats[level]
        
        if key in cache:
            entry = cache[key]
            if not entry.is_expired():
                entry.update_access()
                stats.hits += 1
                self._record_access_pattern(key)
                return entry.value
            else:
                # 清理过期条目
                del cache[key]
                stats.entry_count -= 1
                stats.total_size -= entry.size
        
        stats.misses += 1
        
        # 尝试从更高级别的缓存获取
        if level != CacheLevel.L3_DISK:
            next_level = self._get_next_level(level)
            if next_level:
                value = await self.get(key, next_level)
                if value is not None:
                    # 写入当前级别缓存
                    await self.set(key, value, level)
                    return value
        
        return None
    
    async def set(self, key: str, value: Any, level: CacheLevel = CacheLevel.L1_MEMORY, 
                  ttl: Optional[float] = None, tags: Optional[List[str]] = None):
        """设置缓存数据"""
        cache = self.caches[level]
        stats = self.stats[level]
        
        # 计算数据大小
        size = self._calculate_size(value)
        
        # 检查容量限制
        await self._ensure_capacity(level, size)
        
        # 创建缓存条目
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            accessed_at=time.time(),
            size=size,
            ttl=ttl or self.config.default_ttl,
            tags=tags or []
        )
        
        # 移除旧条目
        if key in cache:
            old_entry = cache[key]
            stats.total_size -= old_entry.size
        else:
            stats.entry_count += 1
        
        cache[key] = entry
        stats.total_size += size
        
        self._record_access_pattern(key)
        logger.debug(f"缓存设置: key={key}, level={level.value}, size={size}")
    
    async def delete(self, key: str, level: Optional[CacheLevel] = None):
        """删除缓存数据"""
        if level:
            levels = [level]
        else:
            levels = list(CacheLevel)
        
        for cache_level in levels:
            cache = self.caches[cache_level]
            stats = self.stats[cache_level]
            
            if key in cache:
                entry = cache[key]
                del cache[key]
                stats.entry_count -= 1
                stats.total_size -= entry.size
                logger.debug(f"缓存删除: key={key}, level={cache_level.value}")
    
    async def invalidate_by_tags(self, tags: List[str]):
        """根据标签失效缓存"""
        for level in CacheLevel:
            cache = self.caches[level]
            keys_to_delete = []
            
            for key, entry in cache.items():
                if any(tag in entry.tags for tag in tags):
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                await self.delete(key, level)
        
        logger.info(f"根据标签失效缓存: tags={tags}")
    
    async def clear(self, level: Optional[CacheLevel] = None):
        """清空缓存"""
        if level:
            levels = [level]
        else:
            levels = list(CacheLevel)
        
        for cache_level in levels:
            self.caches[cache_level].clear()
            self.stats[cache_level] = CacheStats()
        
        logger.info(f"缓存已清空: levels={[l.value for l in levels]}")
    
    def get_stats(self, level: Optional[CacheLevel] = None) -> Dict[str, Any]:
        """获取缓存统计"""
        if level:
            stats = self.stats[level]
            return {
                "level": level.value,
                "hits": stats.hits,
                "misses": stats.misses,
                "hit_rate": stats.hit_rate,
                "miss_rate": stats.miss_rate,
                "evictions": stats.evictions,
                "entry_count": stats.entry_count,
                "total_size": stats.total_size
            }
        else:
            return {
                level.value: {
                    "hits": stats.hits,
                    "misses": stats.misses,
                    "hit_rate": stats.hit_rate,
                    "miss_rate": stats.miss_rate,
                    "evictions": stats.evictions,
                    "entry_count": stats.entry_count,
                    "total_size": stats.total_size
                }
                for level, stats in self.stats.items()
            }
    
    def get_analysis(self) -> Dict[str, Any]:
        """获取缓存分析"""
        analysis = {
            "overall_stats": self.get_stats(),
            "hot_keys": self._get_hot_keys(),
            "optimization_suggestions": self._get_optimization_suggestions(),
            "access_patterns": self._analyze_access_patterns()
        }
        
        return analysis
    
    def add_preload_rule(self, rule: Callable):
        """添加预加载规则"""
        self.preload_rules.append(rule)
        logger.info("添加预加载规则")
    
    def _get_next_level(self, level: CacheLevel) -> Optional[CacheLevel]:
        """获取下一级缓存"""
        level_order = [
            CacheLevel.L1_MEMORY,
            CacheLevel.L2_REDIS,
            CacheLevel.L3_DISK,
            CacheLevel.DISTRIBUTED
        ]
        
        try:
            current_index = level_order.index(level)
            if current_index < len(level_order) - 1:
                return level_order[current_index + 1]
        except ValueError:
            pass
        
        return None
    
    def _calculate_size(self, value: Any) -> int:
        """计算数据大小"""
        try:
            if isinstance(value, (str, bytes)):
                return len(value)
            elif isinstance(value, (int, float)):
                return 8
            elif isinstance(value, dict):
                return len(json.dumps(value, default=str))
            else:
                return len(str(value))
        except:
            return 1024  # 默认大小
    
    async def _ensure_capacity(self, level: CacheLevel, new_size: int):
        """确保缓存容量"""
        cache = self.caches[level]
        stats = self.stats[level]
        
        # 检查条目数量限制
        if stats.entry_count >= self.config.max_size:
            await self._evict_entries(level, 1)
        
        # 检查内存大小限制
        if stats.total_size + new_size > self.config.max_memory:
            needed = stats.total_size + new_size - self.config.max_memory
            await self._evict_by_size(level, needed)
    
    async def _evict_entries(self, level: CacheLevel, count: int):
        """淘汰缓存条目"""
        cache = self.caches[level]
        stats = self.stats[level]
        
        if self.config.strategy == CacheStrategy.LRU:
            # 最近最少使用
            entries = sorted(cache.items(), key=lambda x: x[1].accessed_at)
        elif self.config.strategy == CacheStrategy.LFU:
            # 最少使用频率
            entries = sorted(cache.items(), key=lambda x: x[1].access_count)
        elif self.config.strategy == CacheStrategy.FIFO:
            # 先进先出
            entries = sorted(cache.items(), key=lambda x: x[1].created_at)
        else:
            # 自适应策略
            entries = sorted(cache.items(), 
                           key=lambda x: x[1].access_count / (time.time() - x[1].created_at + 1))
        
        # 淘汰指定数量的条目
        for i in range(min(count, len(entries))):
            key, entry = entries[i]
            del cache[key]
            stats.entry_count -= 1
            stats.total_size -= entry.size
            stats.evictions += 1
    
    async def _evict_by_size(self, level: CacheLevel, target_size: int):
        """按大小淘汰缓存"""
        cache = self.caches[level]
        stats = self.stats[level]
        freed_size = 0
        
        # 按访问频率排序
        entries = sorted(cache.items(), 
                        key=lambda x: x[1].access_count / (time.time() - x[1].created_at + 1))
        
        for key, entry in entries:
            if freed_size >= target_size:
                break
            
            del cache[key]
            stats.entry_count -= 1
            stats.total_size -= entry.size
            stats.evictions += 1
            freed_size += entry.size
    
    async def _cleanup_loop(self, level: CacheLevel):
        """清理循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                await self._cleanup_expired(level)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"缓存清理失败: {e}")
    
    async def _cleanup_expired(self, level: CacheLevel):
        """清理过期条目"""
        cache = self.caches[level]
        stats = self.stats[level]
        expired_keys = []
        
        for key, entry in cache.items():
            if entry.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            entry = cache[key]
            del cache[key]
            stats.entry_count -= 1
            stats.total_size -= entry.size
        
        if expired_keys:
            logger.debug(f"清理过期缓存: level={level.value}, count={len(expired_keys)}")
    
    async def _preload_cache(self):
        """预加载缓存"""
        for rule in self.preload_rules:
            try:
                await rule(self)
            except Exception as e:
                logger.error(f"预加载规则执行失败: {e}")
        
        logger.info("缓存预加载完成")
    
    def _record_access_pattern(self, key: str):
        """记录访问模式"""
        current_time = time.time()
        pattern = self.access_patterns[key]
        pattern.append(current_time)
        
        # 只保留最近1小时的访问记录
        cutoff = current_time - 3600
        self.access_patterns[key] = [t for t in pattern if t > cutoff]
    
    def _get_hot_keys(self, limit: int = 10) -> List[Tuple[str, int]]:
        """获取热点键"""
        key_frequencies = {}
        
        for level in CacheLevel:
            cache = self.caches[level]
            for key, entry in cache.items():
                if key not in key_frequencies:
                    key_frequencies[key] = 0
                key_frequencies[key] += entry.access_count
        
        sorted_keys = sorted(key_frequencies.items(), key=lambda x: x[1], reverse=True)
        return sorted_keys[:limit]
    
    def _get_optimization_suggestions(self) -> List[str]:
        """获取优化建议"""
        suggestions = []
        
        # 分析整体命中率
        total_hits = sum(stats.hits for stats in self.stats.values())
        total_requests = sum(stats.hits + stats.misses for stats in self.stats.values())
        overall_hit_rate = total_hits / total_requests if total_requests > 0 else 0
        
        if overall_hit_rate < 0.7:
            suggestions.append("整体缓存命中率偏低，建议增加缓存容量或调整TTL")
        
        if overall_hit_rate < 0.5:
            suggestions.append("缓存命中率严重偏低，建议检查缓存策略和预加载规则")
        
        # 分析内存使用
        l1_stats = self.stats[CacheLevel.L1_MEMORY]
        if l1_stats.total_size > self.config.max_memory * 0.9:
            suggestions.append("L1缓存内存使用接近上限，建议增加内存或优化淘汰策略")
        
        # 分析淘汰率
        total_evictions = sum(stats.evictions for stats in self.stats.values())
        if total_evictions > total_requests * 0.1:
            suggestions.append("缓存淘汰率过高，建议增加缓存容量")
        
        return suggestions
    
    def _analyze_access_patterns(self) -> Dict[str, Any]:
        """分析访问模式"""
        patterns = {}
        current_time = time.time()
        
        for key, access_times in self.access_patterns.items():
            if len(access_times) < 2:
                continue
            
            # 计算访问频率
            frequency = len(access_times) / 3600  # 每小时访问次数
            
            # 计算访问间隔
            intervals = [access_times[i] - access_times[i-1] 
                        for i in range(1, len(access_times))]
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
            
            patterns[key] = {
                "frequency": frequency,
                "avg_interval": avg_interval,
                "last_access": access_times[-1] if access_times else 0,
                "access_count": len(access_times)
            }
        
        return patterns


# 辅助函数

def create_cache_key(*args) -> str:
    """创建缓存键"""
    key_data = ":".join(str(arg) for arg in args)
    return hashlib.md5(key_data.encode()).hexdigest()


async def cache_decorator(cache_optimizer: CacheOptimizer, 
                         ttl: Optional[float] = None,
                         tags: Optional[List[str]] = None):
    """缓存装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = create_cache_key(func.__name__, args, kwargs)
            
            # 尝试从缓存获取
            cached_result = await cache_optimizer.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数
            result = await func(*args, **kwargs)
            
            # 存入缓存
            await cache_optimizer.set(cache_key, result, ttl=ttl, tags=tags)
            
            return result
        
        return wrapper
    return decorator