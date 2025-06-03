"""
内存缓存实现

提供高性能的内存级缓存，支持多种淘汰策略和线程安全。
"""

import time
import threading
import asyncio
from typing import Any, Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from .cache_interface import Cache, CacheKey, CacheValue, CacheConfig, CacheLevel, CacheStatistics
from .cache_strategies import CacheStrategy, create_strategy


@dataclass 
class MemoryCacheConfig(CacheConfig):
    """内存缓存配置"""
    level: CacheLevel = CacheLevel.MEMORY
    
    # 内存特定配置
    thread_safe: bool = True
    auto_cleanup_interval: int = 60  # 自动清理间隔（秒）
    enable_warmup: bool = False
    warmup_data: Optional[Dict[str, Any]] = None


class MemoryCache(Cache):
    """高性能内存缓存
    
    特性：
    - 线程安全的并发访问
    - 多种淘汰策略支持
    - 自动过期清理
    - 内存使用监控
    - 异步操作支持
    """
    
    def __init__(self, config: MemoryCacheConfig):
        super().__init__(config)
        self.config: MemoryCacheConfig = config
        
        # 存储
        self._storage: Dict[str, CacheValue] = {}
        
        # 线程安全
        self._lock = threading.RLock() if config.thread_safe else None
        
        # 策略
        self.strategy = create_strategy(
            config.eviction_policy,
            config.max_size,
            default_ttl=config.default_ttl
        )
        
        # 清理相关
        self._cleanup_task = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache-cleanup")
        
        # 统计
        self.stats.max_memory_bytes = (config.max_memory_mb or 100) * 1024 * 1024
        
        # 启动清理任务
        if config.background_cleanup:
            self._start_cleanup_task()
        
        # 预热
        if config.enable_warmup and config.warmup_data:
            asyncio.create_task(self._warmup())
    
    async def get(self, key: CacheKey) -> Optional[CacheValue]:
        """获取缓存值"""
        start_time = time.time()
        
        try:
            with self._acquire_lock():
                key_str = str(key)
                
                if key_str not in self._storage:
                    self.stats.misses += 1
                    return None
                
                value = self._storage[key_str]
                
                # 检查过期
                if value.is_expired():
                    del self._storage[key_str]
                    self.strategy.on_remove(key, value)
                    self.stats.misses += 1
                    self.stats.evictions += 1
                    return None
                
                # 更新策略
                self.strategy.on_access(key, value)
                
                # 更新统计
                self.stats.hits += 1
                return value
                
        except Exception as e:
            self.stats.errors += 1
            raise
        finally:
            self.stats.total_get_time += time.time() - start_time
    
    async def set(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """设置缓存值"""
        start_time = time.time()
        
        try:
            # 设置TTL
            if ttl is not None:
                value.expires_at = datetime.now(timezone.utc) + ttl
            elif self.config.default_ttl and value.expires_at is None:
                value.expires_at = datetime.now(timezone.utc) + self.config.default_ttl
            
            with self._acquire_lock():
                key_str = str(key)
                
                # 检查是否需要淘汰
                await self._maybe_evict()
                
                # 检查是否已存在
                is_update = key_str in self._storage
                old_value = self._storage.get(key_str)
                
                # 存储新值
                self._storage[key_str] = value
                
                # 更新策略
                if is_update:
                    self.strategy.on_update(key, old_value, value)
                else:
                    self.strategy.on_insert(key, value)
                
                # 更新统计
                self.stats.sets += 1
                self.stats.current_size = len(self._storage)
                self.stats.current_memory_bytes = self._calculate_memory_usage()
                
                return True
                
        except Exception as e:
            self.stats.errors += 1
            raise
        finally:
            self.stats.total_set_time += time.time() - start_time
    
    async def delete(self, key: CacheKey) -> bool:
        """删除缓存值"""
        start_time = time.time()
        
        try:
            with self._acquire_lock():
                key_str = str(key)
                
                if key_str not in self._storage:
                    return False
                
                value = self._storage.pop(key_str)
                self.strategy.on_remove(key, value)
                
                # 更新统计
                self.stats.deletes += 1
                self.stats.current_size = len(self._storage)
                self.stats.current_memory_bytes = self._calculate_memory_usage()
                
                return True
                
        except Exception as e:
            self.stats.errors += 1
            raise
        finally:
            self.stats.total_delete_time += time.time() - start_time
    
    async def exists(self, key: CacheKey) -> bool:
        """检查键是否存在"""
        with self._acquire_lock():
            key_str = str(key)
            if key_str not in self._storage:
                return False
            
            value = self._storage[key_str]
            if value.is_expired():
                del self._storage[key_str]
                self.strategy.on_remove(key, value)
                return False
            
            return True
    
    async def clear(self) -> bool:
        """清空缓存"""
        try:
            with self._acquire_lock():
                self._storage.clear()
                self.strategy.clear()
                
                # 重置统计
                self.stats.current_size = 0
                self.stats.current_memory_bytes = 0
                
                return True
        except Exception:
            return False
    
    async def size(self) -> int:
        """获取缓存大小"""
        with self._acquire_lock():
            return len(self._storage)
    
    async def keys(self, pattern: Optional[str] = None) -> List[CacheKey]:
        """获取所有键"""
        with self._acquire_lock():
            result = []
            for key_str in self._storage.keys():
                try:
                    # 简单解析键（假设使用冒号分隔）
                    parts = key_str.split(':')
                    if len(parts) >= 2:
                        cache_key = CacheKey(namespace=parts[0], key=':'.join(parts[1:]))
                        if pattern is None or cache_key.matches_pattern(pattern):
                            result.append(cache_key)
                except Exception:
                    continue
            return result
    
    # 批量操作优化
    async def get_many(self, keys: List[CacheKey]) -> Dict[CacheKey, Optional[CacheValue]]:
        """批量获取（优化版本）"""
        result = {}
        
        with self._acquire_lock():
            for key in keys:
                key_str = str(key)
                
                if key_str not in self._storage:
                    result[key] = None
                    self.stats.misses += 1
                    continue
                
                value = self._storage[key_str]
                
                if value.is_expired():
                    del self._storage[key_str]
                    self.strategy.on_remove(key, value)
                    result[key] = None
                    self.stats.misses += 1
                    self.stats.evictions += 1
                    continue
                
                self.strategy.on_access(key, value)
                result[key] = value
                self.stats.hits += 1
        
        return result
    
    async def set_many(self, items: Dict[CacheKey, CacheValue], ttl: Optional[timedelta] = None) -> Dict[CacheKey, bool]:
        """批量设置（优化版本）"""
        result = {}
        
        # 预处理TTL
        if ttl is not None:
            for value in items.values():
                value.expires_at = datetime.now(timezone.utc) + ttl
        elif self.config.default_ttl:
            for value in items.values():
                if value.expires_at is None:
                    value.expires_at = datetime.now(timezone.utc) + self.config.default_ttl
        
        with self._acquire_lock():
            for key, value in items.items():
                try:
                    key_str = str(key)
                    
                    # 检查是否需要淘汰
                    if len(self._storage) >= self.config.max_size:
                        await self._evict_one()
                    
                    # 设置值
                    is_update = key_str in self._storage
                    old_value = self._storage.get(key_str)
                    
                    self._storage[key_str] = value
                    
                    if is_update:
                        self.strategy.on_update(key, old_value, value)
                    else:
                        self.strategy.on_insert(key, value)
                    
                    result[key] = True
                    self.stats.sets += 1
                    
                except Exception:
                    result[key] = False
                    self.stats.errors += 1
            
            # 更新统计
            self.stats.current_size = len(self._storage)
            self.stats.current_memory_bytes = self._calculate_memory_usage()
        
        return result
    
    # 内部方法
    def _acquire_lock(self):
        """获取锁的上下文管理器"""
        if self._lock:
            return self._lock
        else:
            # 返回一个空的上下文管理器
            from contextlib import nullcontext
            return nullcontext()
    
    async def _maybe_evict(self):
        """可能进行淘汰"""
        current_size = len(self._storage)
        
        if self.strategy.should_evict(current_size):
            await self._evict_one()
    
    async def _evict_one(self):
        """淘汰一个项目"""
        victim_key = self.strategy.select_victim()
        if victim_key:
            key_str = str(victim_key)
            if key_str in self._storage:
                value = self._storage.pop(key_str)
                self.strategy.on_remove(victim_key, value)
                self.stats.evictions += 1
    
    def _calculate_memory_usage(self) -> int:
        """计算内存使用量（估算）"""
        total_size = 0
        for value in self._storage.values():
            total_size += value.size_bytes or 0
        return total_size
    
    async def _cleanup_expired(self):
        """清理过期项"""
        expired_keys = []
        now = datetime.now(timezone.utc)
        
        with self._acquire_lock():
            for key_str, value in self._storage.items():
                if value.is_expired():
                    expired_keys.append(key_str)
            
            # 删除过期项
            for key_str in expired_keys:
                value = self._storage.pop(key_str, None)
                if value:
                    # 解析键
                    parts = key_str.split(':')
                    if len(parts) >= 2:
                        cache_key = CacheKey(namespace=parts[0], key=':'.join(parts[1:]))
                        self.strategy.on_remove(cache_key, value)
                    self.stats.evictions += 1
        
        return len(expired_keys)
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        async def cleanup_loop():
            while self._enabled:
                try:
                    await asyncio.sleep(self.config.auto_cleanup_interval)
                    await self._cleanup_expired()
                except Exception:
                    pass
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
    
    async def _warmup(self):
        """缓存预热"""
        if not self.config.warmup_data:
            return
        
        items = {}
        for key_str, data in self.config.warmup_data.items():
            parts = key_str.split(':', 1)
            if len(parts) == 2:
                cache_key = CacheKey(namespace=parts[0], key=parts[1])
                cache_value = CacheValue(data=data)
                items[cache_key] = cache_value
        
        if items:
            await self.set_many(items)
    
    # 生命周期管理
    async def start(self):
        """启动缓存"""
        await super().start()
        if self.config.background_cleanup and not self._cleanup_task:
            self._start_cleanup_task()
    
    async def stop(self):
        """停止缓存"""
        await super().stop()
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        if self._executor:
            self._executor.shutdown(wait=False)
    
    # 高级功能
    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存统计"""
        with self._acquire_lock():
            total_size = 0
            total_count = len(self._storage)
            size_distribution = {'small': 0, 'medium': 0, 'large': 0}
            
            for value in self._storage.values():
                size = value.size_bytes or 0
                total_size += size
                
                if size < 1024:  # < 1KB
                    size_distribution['small'] += 1
                elif size < 1024 * 1024:  # < 1MB
                    size_distribution['medium'] += 1
                else:
                    size_distribution['large'] += 1
            
            return {
                'total_items': total_count,
                'total_size_bytes': total_size,
                'average_size_bytes': total_size / total_count if total_count > 0 else 0,
                'size_distribution': size_distribution,
                'memory_utilization': total_size / self.stats.max_memory_bytes if self.stats.max_memory_bytes > 0 else 0
            }
    
    async def compact(self) -> int:
        """压缩缓存（清理过期项和碎片）"""
        expired_count = await self._cleanup_expired()
        
        # 这里可以添加其他压缩逻辑，比如重新组织内存布局
        
        return expired_count
    
    async def export_data(self) -> Dict[str, Any]:
        """导出缓存数据"""
        with self._acquire_lock():
            data = {}
            for key_str, value in self._storage.items():
                if not value.is_expired():
                    data[key_str] = {
                        'data': value.data,
                        'created_at': value.created_at.isoformat(),
                        'expires_at': value.expires_at.isoformat() if value.expires_at else None,
                        'access_count': value.access_count,
                        'metadata': value.metadata
                    }
            return data
    
    async def import_data(self, data: Dict[str, Any]) -> int:
        """导入缓存数据"""
        imported_count = 0
        
        for key_str, value_data in data.items():
            try:
                parts = key_str.split(':', 1)
                if len(parts) == 2:
                    cache_key = CacheKey(namespace=parts[0], key=parts[1])
                    
                    cache_value = CacheValue(
                        data=value_data['data'],
                        created_at=datetime.fromisoformat(value_data['created_at']),
                        expires_at=datetime.fromisoformat(value_data['expires_at']) if value_data['expires_at'] else None,
                        access_count=value_data.get('access_count', 0),
                        metadata=value_data.get('metadata', {})
                    )
                    
                    if await self.set(cache_key, cache_value):
                        imported_count += 1
                        
            except Exception:
                continue
        
        return imported_count 