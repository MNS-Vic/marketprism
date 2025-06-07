"""
MarketPrism 资源管理器

解决以下问题：
1. 内存泄漏检测和防护
2. 连接池管理
3. 资源自动清理
4. 性能监控
5. 资源使用优化
"""

import asyncio
import gc
import logging
import psutil
import time
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Callable
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ResourceConfig:
    """资源管理配置"""
    # 内存管理
    max_memory_usage: int = 2 * 1024 * 1024 * 1024  # 2GB
    memory_check_interval: int = 60  # 秒
    gc_threshold_mb: int = 100  # MB
    
    # 连接管理
    max_connections: int = 100
    connection_timeout: int = 300  # 5分钟
    cleanup_interval: int = 30  # 秒
    
    # 资源监控
    enable_monitoring: bool = True
    monitoring_interval: int = 10  # 秒
    
    # 告警配置
    memory_warning_threshold: float = 0.8  # 80%
    cpu_warning_threshold: float = 0.9  # 90%
    connection_warning_threshold: float = 0.8  # 80%


@dataclass
class ResourceMetrics:
    """资源使用指标"""
    timestamp: float
    memory_usage: int
    memory_percent: float
    cpu_percent: float
    connections_count: int
    gc_collections: int
    open_files: int
    threads_count: int


class ResourceTracker:
    """资源追踪器"""
    
    def __init__(self):
        self.tracked_objects = weakref.WeakSet()
        self.object_counts = defaultdict(int)
        self.creation_times = {}
        self.cleanup_callbacks = {}
    
    def track(self, obj: Any, cleanup_callback: Optional[Callable] = None):
        """追踪对象"""
        obj_id = id(obj)
        obj_type = type(obj).__name__
        
        self.tracked_objects.add(obj)
        self.object_counts[obj_type] += 1
        self.creation_times[obj_id] = time.time()
        
        if cleanup_callback:
            self.cleanup_callbacks[obj_id] = cleanup_callback
        
        logger.debug(f"开始追踪对象: {obj_type} (ID: {obj_id})")
    
    def untrack(self, obj: Any):
        """取消追踪对象"""
        obj_id = id(obj)
        obj_type = type(obj).__name__
        
        if obj_id in self.creation_times:
            lifetime = time.time() - self.creation_times.pop(obj_id)
            logger.debug(f"对象生命周期结束: {obj_type} (ID: {obj_id}, 生存时间: {lifetime:.2f}秒)")
        
        self.object_counts[obj_type] = max(0, self.object_counts[obj_type] - 1)
        
        # 执行清理回调
        cleanup_callback = self.cleanup_callbacks.pop(obj_id, None)
        if cleanup_callback:
            try:
                cleanup_callback()
            except Exception as e:
                logger.error(f"清理回调执行失败: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取追踪统计"""
        return {
            'total_objects': len(self.tracked_objects),
            'object_counts': dict(self.object_counts),
            'oldest_object_age': time.time() - min(self.creation_times.values()) if self.creation_times else 0
        }


class ConnectionPool:
    """连接池管理器"""
    
    def __init__(self, max_connections: int = 100, timeout: int = 300):
        self.max_connections = max_connections
        self.timeout = timeout
        self.connections = {}
        self.last_used = {}
        self.lock = asyncio.Lock()
    
    async def get_connection(self, key: str, factory: Callable):
        """获取连接"""
        async with self.lock:
            now = time.time()
            
            # 检查现有连接
            if key in self.connections:
                connection = self.connections[key]
                
                # 检查连接是否仍然有效
                if hasattr(connection, 'closed') and connection.closed:
                    del self.connections[key]
                    del self.last_used[key]
                else:
                    self.last_used[key] = now
                    return connection
            
            # 检查连接数限制
            if len(self.connections) >= self.max_connections:
                await self._cleanup_expired_connections()
                
                if len(self.connections) >= self.max_connections:
                    raise RuntimeError(f"连接池已满，最大连接数: {self.max_connections}")
            
            # 创建新连接
            connection = await factory()
            self.connections[key] = connection
            self.last_used[key] = now
            
            return connection
    
    async def _cleanup_expired_connections(self):
        """清理过期连接"""
        now = time.time()
        expired_keys = []
        
        for key, last_used_time in self.last_used.items():
            if now - last_used_time > self.timeout:
                expired_keys.append(key)
        
        for key in expired_keys:
            connection = self.connections.pop(key, None)
            self.last_used.pop(key, None)
            
            if connection and hasattr(connection, 'close'):
                try:
                    await connection.close()
                except Exception as e:
                    logger.warning(f"关闭过期连接失败: {e}")
        
        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期连接")
    
    async def close_all(self):
        """关闭所有连接"""
        async with self.lock:
            for connection in self.connections.values():
                if hasattr(connection, 'close'):
                    try:
                        await connection.close()
                    except Exception as e:
                        logger.warning(f"关闭连接失败: {e}")
            
            self.connections.clear()
            self.last_used.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取连接池统计"""
        now = time.time()
        active_connections = sum(
            1 for last_used in self.last_used.values()
            if now - last_used < self.timeout
        )
        
        return {
            'total_connections': len(self.connections),
            'active_connections': active_connections,
            'max_connections': self.max_connections,
            'utilization': len(self.connections) / self.max_connections
        }


class MemoryManager:
    """内存管理器"""
    
    def __init__(self, config: ResourceConfig):
        self.config = config
        self.last_gc_time = 0
        self.gc_stats = {
            'collections': 0,
            'collected_objects': 0,
            'freed_memory': 0
        }
    
    def get_memory_info(self) -> Dict[str, Any]:
        """获取内存信息"""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            'rss': memory_info.rss,  # 物理内存
            'vms': memory_info.vms,  # 虚拟内存
            'percent': process.memory_percent(),
            'available': psutil.virtual_memory().available,
            'total': psutil.virtual_memory().total
        }
    
    def check_memory_pressure(self) -> bool:
        """检查内存压力"""
        memory_info = self.get_memory_info()
        
        # 检查是否超过限制
        if memory_info['rss'] > self.config.max_memory_usage:
            return True
        
        # 检查系统内存使用率
        if memory_info['percent'] > self.config.memory_warning_threshold * 100:
            return True
        
        return False
    
    def force_garbage_collection(self) -> Dict[str, int]:
        """强制垃圾回收"""
        now = time.time()
        
        # 避免频繁GC
        if now - self.last_gc_time < 10:
            return self.gc_stats
        
        # 获取GC前的内存
        before_memory = self.get_memory_info()['rss']
        
        # 执行垃圾回收
        collected = gc.collect()
        
        # 获取GC后的内存
        after_memory = self.get_memory_info()['rss']
        freed_memory = max(0, before_memory - after_memory)
        
        # 更新统计
        self.gc_stats['collections'] += 1
        self.gc_stats['collected_objects'] += collected
        self.gc_stats['freed_memory'] += freed_memory
        
        self.last_gc_time = now
        
        logger.info(f"垃圾回收完成: 回收对象 {collected}, 释放内存 {freed_memory / 1024 / 1024:.2f}MB")
        
        return {
            'collected_objects': collected,
            'freed_memory': freed_memory,
            'total_collections': self.gc_stats['collections']
        }


class ResourceManager:
    """资源管理器
    
    功能：
    1. 内存使用监控和管理
    2. 连接池管理
    3. 对象生命周期追踪
    4. 自动资源清理
    5. 性能监控和告警
    """
    
    def __init__(self, config: Optional[ResourceConfig] = None):
        self.config = config or ResourceConfig()
        
        # 组件初始化
        self.tracker = ResourceTracker()
        self.connection_pool = ConnectionPool(
            self.config.max_connections,
            self.config.connection_timeout
        )
        self.memory_manager = MemoryManager(self.config)
        
        # 运行状态
        self.running = False
        self.monitoring_task = None
        self.cleanup_task = None
        
        # 监控数据
        self.metrics_history: List[ResourceMetrics] = []
        self.alerts: List[Dict[str, Any]] = []
        
        # 回调函数
        self.alert_callbacks: List[Callable] = []
        
        logger.info("资源管理器已初始化")
    
    async def start(self):
        """启动资源管理器"""
        if self.running:
            return
        
        self.running = True
        
        # 启动监控任务
        if self.config.enable_monitoring:
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # 启动清理任务
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("资源管理器已启动")
    
    async def stop(self):
        """停止资源管理器"""
        if not self.running:
            return
        
        self.running = False
        
        # 停止任务
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 清理资源
        await self.connection_pool.close_all()
        
        logger.info("资源管理器已停止")
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.config.monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(self.config.monitoring_interval)
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self.running:
            try:
                await self._perform_cleanup()
                await asyncio.sleep(self.config.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理循环异常: {e}")
                await asyncio.sleep(self.config.cleanup_interval)
    
    async def _collect_metrics(self):
        """收集指标"""
        try:
            # 获取系统信息
            process = psutil.Process()
            memory_info = self.memory_manager.get_memory_info()
            
            # 创建指标
            metrics = ResourceMetrics(
                timestamp=time.time(),
                memory_usage=memory_info['rss'],
                memory_percent=memory_info['percent'],
                cpu_percent=process.cpu_percent(),
                connections_count=len(self.connection_pool.connections),
                gc_collections=self.memory_manager.gc_stats['collections'],
                open_files=len(process.open_files()),
                threads_count=process.num_threads()
            )
            
            # 存储指标
            self.metrics_history.append(metrics)
            
            # 保持历史记录大小
            if len(self.metrics_history) > 1000:
                self.metrics_history = self.metrics_history[-500:]
            
            # 检查告警条件
            await self._check_alerts(metrics)
            
        except Exception as e:
            logger.error(f"收集指标失败: {e}")
    
    async def _check_alerts(self, metrics: ResourceMetrics):
        """检查告警条件"""
        alerts = []
        
        # 内存告警
        if metrics.memory_percent > self.config.memory_warning_threshold * 100:
            alerts.append({
                'type': 'memory_high',
                'level': 'warning',
                'message': f'内存使用率过高: {metrics.memory_percent:.1f}%',
                'timestamp': metrics.timestamp,
                'value': metrics.memory_percent
            })
        
        # CPU告警
        if metrics.cpu_percent > self.config.cpu_warning_threshold * 100:
            alerts.append({
                'type': 'cpu_high',
                'level': 'warning',
                'message': f'CPU使用率过高: {metrics.cpu_percent:.1f}%',
                'timestamp': metrics.timestamp,
                'value': metrics.cpu_percent
            })
        
        # 连接池告警
        utilization = metrics.connections_count / self.config.max_connections
        if utilization > self.config.connection_warning_threshold:
            alerts.append({
                'type': 'connections_high',
                'level': 'warning',
                'message': f'连接池使用率过高: {utilization:.1%}',
                'timestamp': metrics.timestamp,
                'value': utilization
            })
        
        # 触发告警回调
        for alert in alerts:
            self.alerts.append(alert)
            for callback in self.alert_callbacks:
                try:
                    await callback(alert)
                except Exception as e:
                    logger.error(f"告警回调执行失败: {e}")
        
        # 保持告警历史大小
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-50:]
    
    async def _perform_cleanup(self):
        """执行清理"""
        try:
            # 清理过期连接
            await self.connection_pool._cleanup_expired_connections()
            
            # 检查内存压力
            if self.memory_manager.check_memory_pressure():
                self.memory_manager.force_garbage_collection()
            
            # 清理追踪器
            tracker_stats = self.tracker.get_statistics()
            if tracker_stats['total_objects'] > 10000:
                logger.warning(f"追踪对象过多: {tracker_stats['total_objects']}")
            
        except Exception as e:
            logger.error(f"资源清理失败: {e}")
    
    # 公共接口
    def track_object(self, obj: Any, cleanup_callback: Optional[Callable] = None):
        """追踪对象"""
        self.tracker.track(obj, cleanup_callback)
    
    def untrack_object(self, obj: Any):
        """取消追踪对象"""
        self.tracker.untrack(obj)
    
    @asynccontextmanager
    async def managed_object(self, obj: Any, cleanup_callback: Optional[Callable] = None):
        """管理对象上下文管理器"""
        self.track_object(obj, cleanup_callback)
        try:
            yield obj
        finally:
            self.untrack_object(obj)
    
    async def get_connection(self, key: str, factory: Callable):
        """获取连接"""
        return await self.connection_pool.get_connection(key, factory)
    
    def add_alert_callback(self, callback: Callable):
        """添加告警回调"""
        self.alert_callbacks.append(callback)
    
    def force_gc(self) -> Dict[str, int]:
        """强制垃圾回收"""
        return self.memory_manager.force_garbage_collection()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        latest_metrics = self.metrics_history[-1] if self.metrics_history else None
        
        return {
            'running': self.running,
            'uptime': time.time() - (self.metrics_history[0].timestamp if self.metrics_history else time.time()),
            'current_metrics': {
                'memory_usage_mb': latest_metrics.memory_usage / 1024 / 1024 if latest_metrics else 0,
                'memory_percent': latest_metrics.memory_percent if latest_metrics else 0,
                'cpu_percent': latest_metrics.cpu_percent if latest_metrics else 0,
                'connections_count': latest_metrics.connections_count if latest_metrics else 0,
                'threads_count': latest_metrics.threads_count if latest_metrics else 0
            },
            'tracker_stats': self.tracker.get_statistics(),
            'connection_pool_stats': self.connection_pool.get_statistics(),
            'gc_stats': self.memory_manager.gc_stats,
            'recent_alerts': self.alerts[-5:],
            'metrics_collected': len(self.metrics_history)
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        stats = self.get_statistics()
        current = stats['current_metrics']
        
        issues = []
        healthy = True
        
        # 检查内存使用
        if current['memory_percent'] > 90:
            issues.append("内存使用率过高")
            healthy = False
        
        # 检查CPU使用
        if current['cpu_percent'] > 95:
            issues.append("CPU使用率过高")
            healthy = False
        
        # 检查连接池
        pool_stats = stats['connection_pool_stats']
        if pool_stats['utilization'] > 0.9:
            issues.append("连接池使用率过高")
        
        # 检查对象追踪
        if stats['tracker_stats']['total_objects'] > 50000:
            issues.append("追踪对象过多，可能存在内存泄漏")
            healthy = False
        
        return {
            'healthy': healthy,
            'issues': issues,
            'last_check': time.time()
        }


# 全局资源管理器实例
_global_resource_manager: Optional[ResourceManager] = None


def get_resource_manager(config: Optional[ResourceConfig] = None) -> ResourceManager:
    """获取全局资源管理器"""
    global _global_resource_manager
    if _global_resource_manager is None:
        _global_resource_manager = ResourceManager(config)
    return _global_resource_manager


async def initialize_resource_manager(config: Optional[ResourceConfig] = None) -> ResourceManager:
    """初始化资源管理器"""
    manager = get_resource_manager(config)
    await manager.start()
    return manager


async def cleanup_resource_manager():
    """清理资源管理器"""
    global _global_resource_manager
    if _global_resource_manager:
        await _global_resource_manager.stop()
        _global_resource_manager = None