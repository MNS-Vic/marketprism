"""
💾 MemoryOptimizer - 内存优化器

内存监控和垃圾回收优化
提供内存泄漏检测、GC优化、对象池管理、内存分析等功能
"""

import asyncio
import gc
import time
import sys
import weakref
import psutil
import threading
from typing import Dict, Any, Optional, List, Callable, Set, Type, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import tracemalloc

logger = logging.getLogger(__name__)


class MemoryStrategy(Enum):
    """内存策略枚举"""
    AGGRESSIVE = "aggressive"      # 激进回收
    BALANCED = "balanced"          # 平衡模式
    CONSERVATIVE = "conservative"  # 保守模式
    ADAPTIVE = "adaptive"          # 自适应


class ObjectPoolType(Enum):
    """对象池类型枚举"""
    FIXED_SIZE = "fixed_size"      # 固定大小
    DYNAMIC = "dynamic"            # 动态大小
    LAZY = "lazy"                  # 懒加载
    THREAD_LOCAL = "thread_local"  # 线程本地


@dataclass
class MemoryConfig:
    """内存配置"""
    strategy: MemoryStrategy = MemoryStrategy.ADAPTIVE
    gc_threshold_0: int = 700      # GC阈值0
    gc_threshold_1: int = 10       # GC阈值1
    gc_threshold_2: int = 10       # GC阈值2
    max_memory_usage: float = 0.8  # 最大内存使用比例
    memory_check_interval: float = 30.0  # 内存检查间隔
    leak_detection_enabled: bool = True
    object_tracking_enabled: bool = True
    enable_tracemalloc: bool = True
    profiling_interval: float = 300.0  # 5分钟


@dataclass
class MemoryStats:
    """内存统计"""
    total_memory: int = 0
    available_memory: int = 0
    used_memory: int = 0
    process_memory: int = 0
    gc_collections: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    object_counts: Dict[str, int] = field(default_factory=dict)
    memory_usage_history: deque = field(default_factory=lambda: deque(maxlen=100))
    
    @property
    def memory_usage_percent(self) -> float:
        """内存使用百分比"""
        if self.total_memory == 0:
            return 0.0
        return (self.used_memory / self.total_memory) * 100
    
    @property
    def process_memory_mb(self) -> float:
        """进程内存使用(MB)"""
        return self.process_memory / (1024 * 1024)


class ObjectPool:
    """对象池"""
    
    def __init__(self, factory: Callable, pool_type: ObjectPoolType = ObjectPoolType.DYNAMIC,
                 initial_size: int = 10, max_size: int = 100):
        self.factory = factory
        self.pool_type = pool_type
        self.initial_size = initial_size
        self.max_size = max_size
        self.pool: deque = deque()
        self.created_count = 0
        self.acquired_count = 0
        self.returned_count = 0
        self.lock = threading.RLock()
        
        # 预创建对象
        if pool_type in [ObjectPoolType.FIXED_SIZE, ObjectPoolType.DYNAMIC]:
            for _ in range(initial_size):
                try:
                    obj = self.factory()
                    self.pool.append(obj)
                    self.created_count += 1
                except Exception as e:
                    logger.error(f"对象池预创建失败: {e}")
    
    def acquire(self) -> Any:
        """获取对象"""
        with self.lock:
            if self.pool:
                obj = self.pool.popleft()
                self.acquired_count += 1
                return obj
            
            # 如果池为空且未达到最大大小，创建新对象
            if self.created_count < self.max_size:
                try:
                    obj = self.factory()
                    self.created_count += 1
                    self.acquired_count += 1
                    return obj
                except Exception as e:
                    logger.error(f"对象池创建对象失败: {e}")
                    raise
            
            # 如果达到最大大小，创建临时对象
            return self.factory()
    
    def release(self, obj: Any):
        """释放对象"""
        with self.lock:
            if len(self.pool) < self.max_size:
                # 重置对象状态
                if hasattr(obj, 'reset'):
                    try:
                        obj.reset()
                    except Exception as e:
                        logger.warning(f"对象重置失败: {e}")
                        return
                
                self.pool.append(obj)
                self.returned_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            return {
                "pool_size": len(self.pool),
                "created_count": self.created_count,
                "acquired_count": self.acquired_count,
                "returned_count": self.returned_count,
                "hit_rate": self.returned_count / max(self.acquired_count, 1)
            }


class MemoryTracker:
    """内存跟踪器"""
    
    def __init__(self):
        self.tracked_objects: Dict[int, weakref.ref] = {}
        self.object_counts: Dict[str, int] = defaultdict(int)
        self.creation_times: Dict[int, float] = {}
        self.lock = threading.RLock()
    
    def track_object(self, obj: Any):
        """跟踪对象"""
        with self.lock:
            obj_id = id(obj)
            obj_type = type(obj).__name__
            
            # 创建弱引用
            def cleanup_callback(ref):
                with self.lock:
                    if obj_id in self.tracked_objects:
                        del self.tracked_objects[obj_id]
                    if obj_id in self.creation_times:
                        del self.creation_times[obj_id]
                    self.object_counts[obj_type] -= 1
            
            weak_ref = weakref.ref(obj, cleanup_callback)
            self.tracked_objects[obj_id] = weak_ref
            self.object_counts[obj_type] += 1
            self.creation_times[obj_id] = time.time()
    
    def get_object_counts(self) -> Dict[str, int]:
        """获取对象计数"""
        with self.lock:
            return dict(self.object_counts)
    
    def get_long_lived_objects(self, min_age: float = 300.0) -> List[Dict[str, Any]]:
        """获取长期存活对象"""
        current_time = time.time()
        long_lived = []
        
        with self.lock:
            for obj_id, creation_time in self.creation_times.items():
                if current_time - creation_time > min_age:
                    if obj_id in self.tracked_objects:
                        weak_ref = self.tracked_objects[obj_id]
                        obj = weak_ref()
                        if obj is not None:
                            long_lived.append({
                                "id": obj_id,
                                "type": type(obj).__name__,
                                "age": current_time - creation_time,
                                "size": sys.getsizeof(obj)
                            })
        
        return sorted(long_lived, key=lambda x: x["age"], reverse=True)


class MemoryOptimizer:
    """
    💾 内存优化器
    
    提供内存监控、垃圾回收优化、对象池管理、内存泄漏检测等功能
    """
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()
        self.stats = MemoryStats()
        self.object_pools: Dict[str, ObjectPool] = {}
        self.memory_tracker = MemoryTracker()
        self.monitoring_task: Optional[asyncio.Task] = None
        self.profiling_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.process = psutil.Process()
        
        # 配置垃圾回收
        self._configure_gc()
        
        # 启用内存跟踪
        if self.config.enable_tracemalloc:
            if not tracemalloc.is_tracing():
                tracemalloc.start()
        
        logger.info(f"MemoryOptimizer初始化: strategy={self.config.strategy.value}")
    
    async def start(self):
        """启动内存优化器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动监控任务
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # 启动性能分析
        self.profiling_task = asyncio.create_task(self._profiling_loop())
        
        logger.info("MemoryOptimizer已启动")
    
    async def stop(self):
        """停止内存优化器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消任务
        if self.monitoring_task:
            self.monitoring_task.cancel()
        if self.profiling_task:
            self.profiling_task.cancel()
        
        # 停止内存跟踪
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        
        logger.info("MemoryOptimizer已停止")
    
    def create_object_pool(self, name: str, factory: Callable, 
                          pool_type: ObjectPoolType = ObjectPoolType.DYNAMIC,
                          initial_size: int = 10, max_size: int = 100) -> ObjectPool:
        """创建对象池"""
        if name in self.object_pools:
            raise ValueError(f"对象池已存在: {name}")
        
        pool = ObjectPool(factory, pool_type, initial_size, max_size)
        self.object_pools[name] = pool
        
        logger.info(f"创建对象池: {name}, type={pool_type.value}")
        return pool
    
    def get_object_pool(self, name: str) -> Optional[ObjectPool]:
        """获取对象池"""
        return self.object_pools.get(name)
    
    def remove_object_pool(self, name: str):
        """移除对象池"""
        if name in self.object_pools:
            del self.object_pools[name]
            logger.info(f"移除对象池: {name}")
    
    def track_object(self, obj: Any):
        """跟踪对象"""
        if self.config.object_tracking_enabled:
            self.memory_tracker.track_object(obj)
    
    def force_gc(self, generation: Optional[int] = None) -> Dict[str, int]:
        """强制垃圾回收"""
        if generation is not None:
            collected = gc.collect(generation)
            self.stats.gc_collections[generation] += 1
            return {f"generation_{generation}": collected}
        else:
            collected = {
                "generation_0": gc.collect(0),
                "generation_1": gc.collect(1),
                "generation_2": gc.collect(2)
            }
            for gen in [0, 1, 2]:
                self.stats.gc_collections[gen] += 1
            return collected
    
    def optimize_memory(self) -> Dict[str, Any]:
        """优化内存"""
        optimization_result = {
            "gc_collected": {},
            "memory_before": self._get_memory_usage(),
            "memory_after": 0,
            "optimization_actions": []
        }
        
        # 根据策略执行优化
        if self.config.strategy == MemoryStrategy.AGGRESSIVE:
            optimization_result["gc_collected"] = self.force_gc()
            optimization_result["optimization_actions"].append("强制垃圾回收")
        
        elif self.config.strategy == MemoryStrategy.BALANCED:
            # 检查内存使用情况
            if self.stats.memory_usage_percent > 70:
                optimization_result["gc_collected"] = self.force_gc()
                optimization_result["optimization_actions"].append("条件垃圾回收")
        
        elif self.config.strategy == MemoryStrategy.ADAPTIVE:
            # 自适应策略
            if self.stats.memory_usage_percent > 80:
                optimization_result["gc_collected"] = self.force_gc()
                optimization_result["optimization_actions"].append("高内存使用垃圾回收")
            elif len(gc.garbage) > 100:
                optimization_result["gc_collected"] = self.force_gc(2)
                optimization_result["optimization_actions"].append("清理循环引用")
        
        # 清理无效的弱引用
        self._cleanup_weak_references()
        optimization_result["optimization_actions"].append("清理弱引用")
        
        optimization_result["memory_after"] = self._get_memory_usage()
        optimization_result["memory_saved"] = (
            optimization_result["memory_before"] - optimization_result["memory_after"]
        )
        
        return optimization_result
    
    def detect_memory_leaks(self) -> Dict[str, Any]:
        """检测内存泄漏"""
        if not self.config.leak_detection_enabled:
            return {"enabled": False}
        
        leaks = {
            "long_lived_objects": self.memory_tracker.get_long_lived_objects(),
            "gc_garbage": len(gc.garbage),
            "uncollectable_objects": [],
            "suspicious_growth": []
        }
        
        # 检查不可回收对象
        if gc.garbage:
            for obj in gc.garbage[:10]:  # 只取前10个避免输出过多
                leaks["uncollectable_objects"].append({
                    "type": type(obj).__name__,
                    "repr": repr(obj)[:100],
                    "referrers_count": len(gc.get_referrers(obj))
                })
        
        # 检查对象计数异常增长
        object_counts = self.memory_tracker.get_object_counts()
        for obj_type, count in object_counts.items():
            if count > 1000:  # 阈值可配置
                leaks["suspicious_growth"].append({
                    "type": obj_type,
                    "count": count
                })
        
        return leaks
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取内存统计"""
        self._update_memory_stats()
        
        return {
            "system_memory": {
                "total": self.stats.total_memory,
                "available": self.stats.available_memory,
                "used": self.stats.used_memory,
                "percent": self.stats.memory_usage_percent
            },
            "process_memory": {
                "rss": self.stats.process_memory,
                "rss_mb": self.stats.process_memory_mb
            },
            "gc_stats": {
                "collections": dict(self.stats.gc_collections),
                "garbage_count": len(gc.garbage),
                "thresholds": gc.get_threshold()
            },
            "object_counts": self.memory_tracker.get_object_counts(),
            "pool_stats": {
                name: pool.get_stats() 
                for name, pool in self.object_pools.items()
            }
        }
    
    def get_memory_analysis(self) -> Dict[str, Any]:
        """获取内存分析"""
        stats = self.get_memory_stats()
        leaks = self.detect_memory_leaks()
        
        analysis = {
            "stats": stats,
            "leaks": leaks,
            "recommendations": []
        }
        
        # 生成建议
        if stats["system_memory"]["percent"] > 80:
            analysis["recommendations"].append("系统内存使用率过高，建议释放不必要的对象")
        
        if stats["gc_stats"]["garbage_count"] > 100:
            analysis["recommendations"].append("存在较多垃圾对象，建议检查循环引用")
        
        if leaks["long_lived_objects"]:
            analysis["recommendations"].append("存在长期存活对象，可能存在内存泄漏")
        
        if any(count > 1000 for count in stats["object_counts"].values()):
            analysis["recommendations"].append("某些对象类型数量过多，建议使用对象池")
        
        return analysis
    
    def _configure_gc(self):
        """配置垃圾回收"""
        gc.set_threshold(
            self.config.gc_threshold_0,
            self.config.gc_threshold_1,
            self.config.gc_threshold_2
        )
        
        # 启用垃圾回收调试
        if logger.isEnabledFor(logging.DEBUG):
            gc.set_debug(gc.DEBUG_STATS)
    
    def _get_memory_usage(self) -> int:
        """获取当前内存使用"""
        try:
            return self.process.memory_info().rss
        except:
            return 0
    
    def _update_memory_stats(self):
        """更新内存统计"""
        try:
            # 系统内存
            memory = psutil.virtual_memory()
            self.stats.total_memory = memory.total
            self.stats.available_memory = memory.available
            self.stats.used_memory = memory.used
            
            # 进程内存
            process_memory = self.process.memory_info()
            self.stats.process_memory = process_memory.rss
            
            # 添加到历史记录
            self.stats.memory_usage_history.append({
                "timestamp": time.time(),
                "system_percent": memory.percent,
                "process_mb": process_memory.rss / (1024 * 1024)
            })
            
            # 对象计数
            self.stats.object_counts = self.memory_tracker.get_object_counts()
            
        except Exception as e:
            logger.error(f"更新内存统计失败: {e}")
    
    def _cleanup_weak_references(self):
        """清理无效的弱引用"""
        # 触发弱引用清理
        gc.collect()
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.memory_check_interval)
                await self._check_memory_usage()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"内存监控失败: {e}")
    
    async def _check_memory_usage(self):
        """检查内存使用"""
        self._update_memory_stats()
        
        # 检查是否需要优化
        if self.stats.memory_usage_percent > self.config.max_memory_usage * 100:
            logger.warning(f"内存使用率过高: {self.stats.memory_usage_percent:.1f}%")
            optimization_result = self.optimize_memory()
            logger.info(f"内存优化完成: {optimization_result}")
        
        # 检查内存泄漏
        if self.config.leak_detection_enabled:
            leaks = self.detect_memory_leaks()
            if leaks.get("long_lived_objects") or leaks.get("gc_garbage", 0) > 100:
                logger.warning(f"检测到潜在内存泄漏: {leaks}")
    
    async def _profiling_loop(self):
        """性能分析循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.profiling_interval)
                await self._memory_profiling()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"内存分析失败: {e}")
    
    async def _memory_profiling(self):
        """内存性能分析"""
        if not tracemalloc.is_tracing():
            return
        
        try:
            # 获取内存快照
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            
            # 记录前10个内存使用最多的位置
            logger.debug("内存使用热点:")
            for index, stat in enumerate(top_stats[:10], 1):
                logger.debug(f"{index}. {stat}")
        
        except Exception as e:
            logger.error(f"内存分析快照失败: {e}")


# 工具函数和装饰器

def memory_tracked(func):
    """内存跟踪装饰器"""
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # 这里需要获取全局的MemoryOptimizer实例
        # optimizer.track_object(result)
        return result
    return wrapper


def with_object_pool(pool_name: str):
    """对象池装饰器"""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # 这里需要获取对象池
            pool = self.memory_optimizer.get_object_pool(pool_name)
            if pool:
                obj = pool.acquire()
                try:
                    return func(self, obj, *args, **kwargs)
                finally:
                    pool.release(obj)
            else:
                return func(self, *args, **kwargs)
        return wrapper
    return decorator


class MemoryPoolManager:
    """内存池管理器"""
    
    def __init__(self, optimizer: MemoryOptimizer):
        self.optimizer = optimizer
        self.pools = {}
    
    def get_or_create_pool(self, name: str, factory: Callable, **kwargs) -> ObjectPool:
        """获取或创建对象池"""
        if name not in self.pools:
            pool = self.optimizer.create_object_pool(name, factory, **kwargs)
            self.pools[name] = pool
        return self.pools[name]
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 清理所有池
        for name in list(self.pools.keys()):
            self.optimizer.remove_object_pool(name)
        self.pools.clear()