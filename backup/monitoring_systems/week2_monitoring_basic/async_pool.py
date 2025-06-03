#!/usr/bin/env python3
"""
MarketPrism 异步处理优化系统 - 第二阶段优化第四天实施

企业级异步处理管理，支持协程池管理、事件循环优化和异步性能监控。
"""

import asyncio
import time
import threading
import weakref
import sys
from abc import ABC, abstractmethod
from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, TypeVar, Generic, Callable, Union, Coroutine, Awaitable
from concurrent.futures import ThreadPoolExecutor
import logging

# 尝试导入uvloop，如果不可用则使用标准事件循环
try:
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

# 设置日志
logger = logging.getLogger(__name__)

# 泛型类型定义
T = TypeVar('T')
R = TypeVar('R')


class CoroutineState(Enum):
    """协程状态枚举"""
    PENDING = "pending"         # 等待执行
    RUNNING = "running"         # 正在执行
    COMPLETED = "completed"     # 执行完成
    FAILED = "failed"          # 执行失败
    CANCELLED = "cancelled"     # 已取消


class EventLoopPolicy(Enum):
    """事件循环策略枚举"""
    DEFAULT = "default"         # 默认策略
    UVLOOP = "uvloop"          # uvloop策略
    OPTIMIZED = "optimized"     # 优化策略


@dataclass
class CoroutineInfo:
    """协程信息"""
    coroutine_id: str
    name: str
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    state: CoroutineState = CoroutineState.PENDING
    execution_count: int = 0
    error_count: int = 0
    total_execution_time: float = 0.0
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def age_seconds(self) -> float:
        """协程年龄（秒）"""
        return time.time() - self.created_at
    
    @property
    def execution_time_seconds(self) -> Optional[float]:
        """执行时间（秒）"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def average_execution_time(self) -> float:
        """平均执行时间"""
        return self.total_execution_time / self.execution_count if self.execution_count > 0 else 0.0
    
    def mark_started(self):
        """标记协程开始执行"""
        self.started_at = time.time()
        self.state = CoroutineState.RUNNING
        self.execution_count += 1
    
    def mark_completed(self):
        """标记协程执行完成"""
        self.completed_at = time.time()
        self.state = CoroutineState.COMPLETED
        if self.started_at:
            execution_time = self.completed_at - self.started_at
            self.total_execution_time += execution_time
    
    def mark_failed(self, error: str):
        """标记协程执行失败"""
        self.completed_at = time.time()
        self.state = CoroutineState.FAILED
        self.error_count += 1
        self.last_error = error
        if self.started_at:
            execution_time = self.completed_at - self.started_at
            self.total_execution_time += execution_time


@dataclass
class AsyncPoolStatistics:
    """异步池统计信息"""
    pool_name: str
    max_size: int
    current_size: int
    active_coroutines: int
    pending_coroutines: int
    completed_coroutines: int
    failed_coroutines: int
    total_created: int = 0
    total_executed: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    total_execution_time: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total_finished = self.total_completed + self.total_failed
        return self.total_completed / total_finished if total_finished > 0 else 0.0
    
    @property
    def utilization_rate(self) -> float:
        """池利用率"""
        return self.active_coroutines / self.max_size if self.max_size > 0 else 0.0
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0
    
    @property
    def average_execution_time(self) -> float:
        """平均执行时间"""
        return self.total_execution_time / self.total_executed if self.total_executed > 0 else 0.0
    
    @property
    def throughput_per_second(self) -> float:
        """每秒吞吐量"""
        if self.total_execution_time > 0:
            return self.total_completed / self.total_execution_time
        return 0.0


class CoroutinePool(Generic[T]):
    """协程池管理器"""
    
    def __init__(
        self,
        name: str,
        max_size: int = 100,
        min_size: int = 10,
        max_idle_time: float = 300.0,  # 5分钟
        max_lifetime: float = 3600.0,  # 1小时
        cleanup_interval: float = 60.0,  # 1分钟
        enable_reuse: bool = True
    ):
        self.name = name
        self.max_size = max_size
        self.min_size = min_size
        self.max_idle_time = max_idle_time
        self.max_lifetime = max_lifetime
        self.cleanup_interval = cleanup_interval
        self.enable_reuse = enable_reuse
        
        # 协程存储
        self._pending_queue: asyncio.Queue = asyncio.Queue()
        self._active_coroutines: Dict[str, asyncio.Task] = {}
        self._coroutine_info: Dict[str, CoroutineInfo] = {}
        self._completed_pool: deque = deque(maxlen=max_size)
        
        # 线程安全
        self._lock = asyncio.Lock()
        self._thread_lock = threading.RLock()
        
        # 统计信息
        self.stats = AsyncPoolStatistics(
            pool_name=name,
            max_size=max_size,
            current_size=0,
            active_coroutines=0,
            pending_coroutines=0,
            completed_coroutines=0,
            failed_coroutines=0
        )
        
        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"✅ 创建协程池: {name} (最大: {max_size})")
    
    async def start(self):
        """启动协程池"""
        if self._running:
            return
        
        self._running = True
        
        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info(f"🚀 协程池 {self.name} 已启动")
    
    async def stop(self):
        """停止协程池"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # 取消所有活跃协程
        await self._cancel_all_coroutines()
        
        logger.info(f"⏹️ 协程池 {self.name} 已停止")
    
    async def submit(self, coro: Coroutine[Any, Any, T], name: str = None) -> T:
        """提交协程到池中执行"""
        if not self._running:
            raise RuntimeError(f"协程池 {self.name} 未启动")
        
        async with self._lock:
            # 检查池容量
            if len(self._active_coroutines) >= self.max_size:
                raise RuntimeError(f"协程池 {self.name} 已达到最大容量")
            
            # 创建协程信息
            coroutine_id = f"{self.name}_{id(coro)}_{time.time()}"
            coro_name = name or f"coro_{len(self._coroutine_info)}"
            
            info = CoroutineInfo(
                coroutine_id=coroutine_id,
                name=coro_name,
                created_at=time.time()
            )
            
            self._coroutine_info[coroutine_id] = info
            
            # 创建任务
            task = asyncio.create_task(self._execute_coroutine(coro, info))
            self._active_coroutines[coroutine_id] = task
            
            # 更新统计
            self.stats.total_created += 1
            self._update_stats()
            
            logger.debug(f"✅ 提交协程: {coro_name} ({coroutine_id})")
            
            try:
                result = await task
                return result
            finally:
                # 清理完成的协程
                if coroutine_id in self._active_coroutines:
                    del self._active_coroutines[coroutine_id]
                self._update_stats()
    
    async def submit_batch(self, coros: List[Coroutine[Any, Any, T]], names: List[str] = None) -> List[T]:
        """批量提交协程"""
        if names and len(names) != len(coros):
            raise ValueError("协程数量与名称数量不匹配")
        
        tasks = []
        for i, coro in enumerate(coros):
            name = names[i] if names else f"batch_coro_{i}"
            task = asyncio.create_task(self.submit(coro, name))
            tasks.append(task)
        
        return await asyncio.gather(*tasks)
    
    async def _execute_coroutine(self, coro: Coroutine[Any, Any, T], info: CoroutineInfo) -> T:
        """执行协程"""
        try:
            info.mark_started()
            self.stats.total_executed += 1
            
            result = await coro
            
            info.mark_completed()
            self.stats.total_completed += 1
            self.stats.total_execution_time += info.execution_time_seconds or 0
            
            # 如果启用复用，将协程信息加入完成池
            if self.enable_reuse:
                self._completed_pool.append(info)
            
            return result
            
        except asyncio.CancelledError:
            info.state = CoroutineState.CANCELLED
            self.stats.total_cancelled += 1
            raise
        except Exception as e:
            error_msg = str(e)
            info.mark_failed(error_msg)
            self.stats.total_failed += 1
            logger.error(f"❌ 协程执行失败 {info.name}: {error_msg}")
            raise
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired_coroutines()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 清理循环错误: {e}")
    
    async def _cleanup_expired_coroutines(self):
        """清理过期协程"""
        async with self._lock:
            current_time = time.time()
            expired_ids = []
            
            # 检查协程信息
            for coroutine_id, info in self._coroutine_info.items():
                if (info.age_seconds > self.max_lifetime or 
                    (info.state == CoroutineState.COMPLETED and 
                     info.completed_at and 
                     current_time - info.completed_at > self.max_idle_time)):
                    expired_ids.append(coroutine_id)
            
            # 清理过期协程
            for coroutine_id in expired_ids:
                if coroutine_id in self._coroutine_info:
                    del self._coroutine_info[coroutine_id]
                if coroutine_id in self._active_coroutines:
                    task = self._active_coroutines[coroutine_id]
                    if not task.done():
                        task.cancel()
                    del self._active_coroutines[coroutine_id]
            
            self._update_stats()
    
    async def _cancel_all_coroutines(self):
        """取消所有协程"""
        for task in self._active_coroutines.values():
            if not task.done():
                task.cancel()
        
        # 等待所有任务完成
        if self._active_coroutines:
            await asyncio.gather(*self._active_coroutines.values(), return_exceptions=True)
        
        self._active_coroutines.clear()
        self._coroutine_info.clear()
    
    def _update_stats(self):
        """更新统计信息"""
        self.stats.current_size = len(self._active_coroutines) + len(self._coroutine_info)
        self.stats.active_coroutines = len(self._active_coroutines)
        self.stats.pending_coroutines = self._pending_queue.qsize()
        
        # 计算完成和失败的协程数
        completed_count = 0
        failed_count = 0
        for info in self._coroutine_info.values():
            if info.state == CoroutineState.COMPLETED:
                completed_count += 1
            elif info.state == CoroutineState.FAILED:
                failed_count += 1
        
        self.stats.completed_coroutines = completed_count
        self.stats.failed_coroutines = failed_count
    
    def get_statistics(self) -> AsyncPoolStatistics:
        """获取池统计信息"""
        with self._thread_lock:
            self._update_stats()
            return self.stats
    
    def get_coroutine_details(self) -> List[Dict[str, Any]]:
        """获取协程详细信息"""
        details = []
        for coroutine_id, info in self._coroutine_info.items():
            details.append({
                'coroutine_id': coroutine_id,
                'name': info.name,
                'state': info.state.value,
                'age_seconds': info.age_seconds,
                'execution_count': info.execution_count,
                'error_count': info.error_count,
                'average_execution_time': info.average_execution_time,
                'last_error': info.last_error,
                'metadata': info.metadata
            })
        return details


class EventLoopOptimizer:
    """事件循环优化器"""
    
    def __init__(
        self,
        policy: EventLoopPolicy = EventLoopPolicy.OPTIMIZED,
        enable_debug: bool = False,
        thread_pool_size: int = None
    ):
        self.policy = policy
        self.enable_debug = enable_debug
        self.thread_pool_size = thread_pool_size or min(32, (os.cpu_count() or 1) + 4)
        
        self._original_policy = None
        self._thread_pool_executor = None
        self._loop = None
        
        logger.info(f"✅ 创建事件循环优化器: {policy.value}")
    
    def setup_event_loop(self) -> asyncio.AbstractEventLoop:
        """设置优化的事件循环"""
        # 保存原始策略
        self._original_policy = asyncio.get_event_loop_policy()
        
        if self.policy == EventLoopPolicy.UVLOOP and UVLOOP_AVAILABLE:
            # 使用uvloop
            uvloop.install()
            logger.info("🚀 已安装uvloop事件循环策略")
        elif self.policy == EventLoopPolicy.OPTIMIZED:
            # 使用优化的默认策略
            if sys.platform == 'win32':
                # Windows使用ProactorEventLoop
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            else:
                # Unix使用默认策略
                pass
            logger.info("🚀 已设置优化事件循环策略")
        
        # 获取或创建事件循环
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 配置事件循环
        if self.enable_debug:
            loop.set_debug(True)
        
        # 设置线程池执行器
        if self.thread_pool_size:
            self._thread_pool_executor = ThreadPoolExecutor(
                max_workers=self.thread_pool_size,
                thread_name_prefix="AsyncOptimizer"
            )
            loop.set_default_executor(self._thread_pool_executor)
        
        self._loop = loop
        return loop
    
    def restore_event_loop(self):
        """恢复原始事件循环策略"""
        if self._original_policy:
            asyncio.set_event_loop_policy(self._original_policy)
        
        if self._thread_pool_executor:
            self._thread_pool_executor.shutdown(wait=True)
        
        logger.info("🔄 已恢复原始事件循环策略")
    
    def get_loop_info(self) -> Dict[str, Any]:
        """获取事件循环信息"""
        if not self._loop:
            return {}
        
        return {
            'policy': self.policy.value,
            'debug_enabled': self._loop.get_debug(),
            'is_running': self._loop.is_running(),
            'is_closed': self._loop.is_closed(),
            'thread_pool_size': self.thread_pool_size,
            'uvloop_available': UVLOOP_AVAILABLE,
            'platform': sys.platform
        }


class AsyncPerformanceMonitor:
    """异步性能监控器"""
    
    def __init__(self, name: str = "async_monitor"):
        self.name = name
        self._metrics: Dict[str, List[float]] = defaultdict(list)
        self._operation_counts: Dict[str, int] = defaultdict(int)
        self._start_times: Dict[str, float] = {}
        self._lock = threading.RLock()
        
        logger.info(f"✅ 创建异步性能监控器: {name}")
    
    def start_operation(self, operation_id: str, operation_type: str = "default"):
        """开始监控操作"""
        with self._lock:
            self._start_times[operation_id] = time.time()
            self._operation_counts[operation_type] += 1
    
    def end_operation(self, operation_id: str, operation_type: str = "default"):
        """结束监控操作"""
        with self._lock:
            if operation_id in self._start_times:
                duration = time.time() - self._start_times[operation_id]
                self._metrics[operation_type].append(duration)
                del self._start_times[operation_id]
                return duration
        return None
    
    def record_metric(self, metric_name: str, value: float):
        """记录指标"""
        with self._lock:
            self._metrics[metric_name].append(value)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            stats = {}
            
            for metric_name, values in self._metrics.items():
                if values:
                    stats[metric_name] = {
                        'count': len(values),
                        'total': sum(values),
                        'average': sum(values) / len(values),
                        'min': min(values),
                        'max': max(values),
                        'recent_average': sum(values[-10:]) / min(len(values), 10)
                    }
            
            stats['operation_counts'] = dict(self._operation_counts)
            stats['active_operations'] = len(self._start_times)
            
            return stats
    
    def reset_metrics(self):
        """重置指标"""
        with self._lock:
            self._metrics.clear()
            self._operation_counts.clear()
            self._start_times.clear()


class AsyncOptimizationManager:
    """异步优化管理器"""
    
    def __init__(self, name: str = "async_optimization_manager"):
        self.name = name
        self._coroutine_pools: Dict[str, CoroutinePool] = {}
        self._event_loop_optimizer: Optional[EventLoopOptimizer] = None
        self._performance_monitor: Optional[AsyncPerformanceMonitor] = None
        self._lock = threading.RLock()
        
        logger.info(f"✅ 创建异步优化管理器: {name}")
    
    def create_coroutine_pool(
        self,
        name: str,
        max_size: int = 100,
        **kwargs
    ) -> CoroutinePool:
        """创建协程池"""
        with self._lock:
            if name in self._coroutine_pools:
                raise ValueError(f"协程池 {name} 已存在")
            
            pool = CoroutinePool(name=name, max_size=max_size, **kwargs)
            self._coroutine_pools[name] = pool
            return pool
    
    def get_coroutine_pool(self, name: str) -> Optional[CoroutinePool]:
        """获取协程池"""
        with self._lock:
            return self._coroutine_pools.get(name)
    
    def setup_event_loop_optimizer(
        self,
        policy: EventLoopPolicy = EventLoopPolicy.OPTIMIZED,
        **kwargs
    ) -> EventLoopOptimizer:
        """设置事件循环优化器"""
        self._event_loop_optimizer = EventLoopOptimizer(policy=policy, **kwargs)
        return self._event_loop_optimizer
    
    def setup_performance_monitor(self, name: str = None) -> AsyncPerformanceMonitor:
        """设置性能监控器"""
        monitor_name = name or f"{self.name}_monitor"
        self._performance_monitor = AsyncPerformanceMonitor(monitor_name)
        return self._performance_monitor
    
    async def start_all_pools(self):
        """启动所有协程池"""
        for pool in self._coroutine_pools.values():
            await pool.start()
        
        logger.info(f"🚀 已启动 {len(self._coroutine_pools)} 个协程池")
    
    async def stop_all_pools(self):
        """停止所有协程池"""
        for pool in self._coroutine_pools.values():
            await pool.stop()
        
        logger.info(f"⏹️ 已停止 {len(self._coroutine_pools)} 个协程池")
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """获取汇总统计信息"""
        with self._lock:
            pool_stats = {}
            total_active = 0
            total_completed = 0
            total_failed = 0
            
            for name, pool in self._coroutine_pools.items():
                stats = pool.get_statistics()
                pool_stats[name] = {
                    'active_coroutines': stats.active_coroutines,
                    'completed_coroutines': stats.completed_coroutines,
                    'failed_coroutines': stats.failed_coroutines,
                    'success_rate': stats.success_rate,
                    'utilization_rate': stats.utilization_rate,
                    'average_execution_time': stats.average_execution_time,
                    'throughput_per_second': stats.throughput_per_second
                }
                
                total_active += stats.active_coroutines
                total_completed += stats.completed_coroutines
                total_failed += stats.failed_coroutines
            
            summary = {
                'pools_count': len(self._coroutine_pools),
                'total_active_coroutines': total_active,
                'total_completed_coroutines': total_completed,
                'total_failed_coroutines': total_failed,
                'overall_success_rate': total_completed / (total_completed + total_failed) if (total_completed + total_failed) > 0 else 0,
                'pool_statistics': pool_stats
            }
            
            # 添加事件循环信息
            if self._event_loop_optimizer:
                summary['event_loop_info'] = self._event_loop_optimizer.get_loop_info()
            
            # 添加性能监控信息
            if self._performance_monitor:
                summary['performance_metrics'] = self._performance_monitor.get_statistics()
            
            return summary


# 全局异步优化管理器实例
_async_optimization_manager: Optional[AsyncOptimizationManager] = None


def get_async_optimization_manager() -> AsyncOptimizationManager:
    """获取全局异步优化管理器"""
    global _async_optimization_manager
    if _async_optimization_manager is None:
        _async_optimization_manager = AsyncOptimizationManager()
    return _async_optimization_manager


# 便捷函数
async def create_coroutine_pool(name: str, max_size: int = 100, **kwargs) -> CoroutinePool:
    """创建协程池的便捷函数"""
    manager = get_async_optimization_manager()
    return manager.create_coroutine_pool(name, max_size, **kwargs)


def setup_event_loop_optimizer(policy: EventLoopPolicy = EventLoopPolicy.OPTIMIZED, **kwargs) -> EventLoopOptimizer:
    """设置事件循环优化器的便捷函数"""
    manager = get_async_optimization_manager()
    return manager.setup_event_loop_optimizer(policy, **kwargs)


def setup_performance_monitor(name: str = None) -> AsyncPerformanceMonitor:
    """设置性能监控器的便捷函数"""
    manager = get_async_optimization_manager()
    return manager.setup_performance_monitor(name)


async def submit_coroutine(pool_name: str, coro: Coroutine[Any, Any, T], name: str = None) -> T:
    """提交协程到指定池的便捷函数"""
    manager = get_async_optimization_manager()
    pool = manager.get_coroutine_pool(pool_name)
    if pool:
        return await pool.submit(coro, name)
    raise ValueError(f"协程池 {pool_name} 不存在")


def get_async_optimization_summary() -> Dict[str, Any]:
    """获取异步优化汇总信息的便捷函数"""
    manager = get_async_optimization_manager()
    return manager.get_summary_statistics()


# 导入os模块
import os