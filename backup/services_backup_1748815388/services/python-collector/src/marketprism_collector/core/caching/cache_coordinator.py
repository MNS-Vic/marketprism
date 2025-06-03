"""
缓存协调器

实现多层缓存的统一管理、路由、同步和故障转移。
"""

import asyncio
import time
from typing import Any, Optional, Dict, List, Union, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import logging

from .cache_interface import (
    Cache, CacheKey, CacheValue, CacheConfig, CacheLevel, 
    CacheStatistics
)
from .memory_cache import MemoryCache, MemoryCacheConfig
from .redis_cache import RedisCache, RedisCacheConfig, REDIS_AVAILABLE
from .disk_cache import DiskCache, DiskCacheConfig


class CacheRoutingPolicy(Enum):
    """缓存路由策略"""
    READ_THROUGH = "read_through"  # 读穿透：按层级顺序读取
    WRITE_THROUGH = "write_through"  # 写穿透：写入所有层
    WRITE_AROUND = "write_around"  # 写绕过：只写入最慢层
    WRITE_BACK = "write_back"  # 写回：延迟写入
    CACHE_ASIDE = "cache_aside"  # 缓存旁路：应用管理一致性


class CacheSyncStrategy(Enum):
    """缓存同步策略"""
    IMMEDIATE = "immediate"  # 立即同步
    PERIODIC = "periodic"  # 定期同步
    ON_EVICTION = "on_eviction"  # 淘汰时同步
    LAZY = "lazy"  # 懒同步


@dataclass
class CacheCoordinatorConfig:
    """缓存协调器配置"""
    name: str = "cache_coordinator"
    
    # 路由策略
    read_policy: CacheRoutingPolicy = CacheRoutingPolicy.READ_THROUGH
    write_policy: CacheRoutingPolicy = CacheRoutingPolicy.WRITE_THROUGH
    
    # 同步策略
    sync_strategy: CacheSyncStrategy = CacheSyncStrategy.PERIODIC
    sync_interval: int = 300  # 同步间隔（秒）
    
    # 故障转移
    enable_failover: bool = True
    health_check_interval: int = 30  # 健康检查间隔（秒）
    max_failures: int = 3  # 最大失败次数
    
    # 性能优化
    enable_promotion: bool = True  # 启用数据提升
    promotion_threshold: int = 3  # 提升阈值（访问次数）
    enable_preload: bool = True  # 启用预加载
    
    # 监控配置
    enable_metrics: bool = True
    detailed_logging: bool = False


class CacheInstance:
    """缓存实例封装"""
    
    def __init__(self, cache: Cache, level: CacheLevel, priority: int = 0):
        self.cache = cache
        self.level = level
        self.priority = priority  # 优先级，数字越小优先级越高
        self.is_healthy = True
        self.failure_count = 0
        self.last_health_check = datetime.now(timezone.utc)
        self.stats = CacheStatistics()
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            result = await self.cache.health_check()
            self.is_healthy = result.get('healthy', False)
            if self.is_healthy:
                self.failure_count = 0
            else:
                self.failure_count += 1
            self.last_health_check = datetime.now(timezone.utc)
            return self.is_healthy
        except Exception:
            self.failure_count += 1
            self.is_healthy = False
            return False


class CacheCoordinator(Cache):
    """缓存协调器
    
    特性：
    - 多层缓存统一管理
    - 智能路由策略
    - 自动故障转移
    - 数据同步和提升
    - 统一监控和指标
    """
    
    def __init__(self, config: CacheCoordinatorConfig):
        # 创建一个虚拟的CacheConfig
        dummy_config = CacheConfig(
            name=config.name,
            level=CacheLevel.MEMORY,  # 虚拟层级
            max_size=0
        )
        super().__init__(dummy_config)
        
        self.config = config
        self.instances: List[CacheInstance] = []
        self.level_mapping: Dict[CacheLevel, List[CacheInstance]] = {}
        
        # 同步任务
        self._sync_task = None
        self._health_check_task = None
        
        # 预加载缓存（记录哪些数据需要预加载到更快层）
        self._promotion_candidates: Dict[str, int] = {}  # key -> access_count
        
        self._logger = logging.getLogger(__name__)
    
    def add_cache(self, cache: Cache, priority: int = 0) -> None:
        """添加缓存实例"""
        instance = CacheInstance(cache, cache.config.level, priority)
        self.instances.append(instance)
        
        # 按优先级排序
        self.instances.sort(key=lambda x: x.priority)
        
        # 更新层级映射
        level = cache.config.level
        if level not in self.level_mapping:
            self.level_mapping[level] = []
        self.level_mapping[level].append(instance)
        
        self._logger.info(f"添加缓存实例: {level.value}, 优先级: {priority}")
    
    def remove_cache(self, cache: Cache) -> bool:
        """移除缓存实例"""
        for i, instance in enumerate(self.instances):
            if instance.cache == cache:
                del self.instances[i]
                
                # 更新层级映射
                level = cache.config.level
                if level in self.level_mapping:
                    self.level_mapping[level] = [
                        inst for inst in self.level_mapping[level] 
                        if inst.cache != cache
                    ]
                
                self._logger.info(f"移除缓存实例: {level.value}")
                return True
        
        return False
    
    def get_healthy_instances(self) -> List[CacheInstance]:
        """获取健康的缓存实例"""
        return [inst for inst in self.instances if inst.is_healthy]
    
    def get_fastest_instance(self) -> Optional[CacheInstance]:
        """获取最快的健康实例"""
        healthy_instances = self.get_healthy_instances()
        return healthy_instances[0] if healthy_instances else None
    
    def get_slowest_instance(self) -> Optional[CacheInstance]:
        """获取最慢的健康实例"""
        healthy_instances = self.get_healthy_instances()
        return healthy_instances[-1] if healthy_instances else None
    
    async def get(self, key: CacheKey) -> Optional[CacheValue]:
        """获取缓存值（读穿透策略）"""
        start_time = time.time()
        
        try:
            if self.config.read_policy == CacheRoutingPolicy.READ_THROUGH:
                return await self._read_through(key)
            elif self.config.read_policy == CacheRoutingPolicy.CACHE_ASIDE:
                return await self._cache_aside_read(key)
            else:
                # 默认从最快的缓存读取
                fastest = self.get_fastest_instance()
                if fastest:
                    return await fastest.cache.get(key)
                return None
                
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Coordinator get失败: {e}")
            raise
        finally:
            self.stats.total_get_time += time.time() - start_time
    
    async def _read_through(self, key: CacheKey) -> Optional[CacheValue]:
        """读穿透实现"""
        # 按优先级从快到慢查找
        for instance in self.get_healthy_instances():
            try:
                value = await instance.cache.get(key)
                if value is not None:
                    instance.stats.hits += 1
                    self.stats.hits += 1
                    
                    # 数据提升：将数据提升到更快的层
                    if self.config.enable_promotion:
                        await self._promote_data(key, value, instance)
                    
                    # 记录访问统计用于提升决策
                    key_str = str(key)
                    self._promotion_candidates[key_str] = self._promotion_candidates.get(key_str, 0) + 1
                    
                    return value
                else:
                    instance.stats.misses += 1
                    
            except Exception as e:
                instance.failure_count += 1
                self._logger.warning(f"读取失败 {instance.level.value}: {e}")
        
        self.stats.misses += 1
        return None
    
    async def _cache_aside_read(self, key: CacheKey) -> Optional[CacheValue]:
        """缓存旁路读取"""
        # 只从最快的缓存读取
        fastest = self.get_fastest_instance()
        if fastest:
            try:
                value = await fastest.cache.get(key)
                if value is not None:
                    fastest.stats.hits += 1
                    self.stats.hits += 1
                    return value
                else:
                    fastest.stats.misses += 1
                    self.stats.misses += 1
            except Exception as e:
                fastest.failure_count += 1
                self._logger.warning(f"Cache aside读取失败: {e}")
        
        return None
    
    async def set(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """设置缓存值"""
        start_time = time.time()
        
        try:
            if self.config.write_policy == CacheRoutingPolicy.WRITE_THROUGH:
                return await self._write_through(key, value, ttl)
            elif self.config.write_policy == CacheRoutingPolicy.WRITE_AROUND:
                return await self._write_around(key, value, ttl)
            elif self.config.write_policy == CacheRoutingPolicy.WRITE_BACK:
                return await self._write_back(key, value, ttl)
            elif self.config.write_policy == CacheRoutingPolicy.CACHE_ASIDE:
                return await self._cache_aside_write(key, value, ttl)
            else:
                # 默认写入所有层
                return await self._write_through(key, value, ttl)
                
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Coordinator set失败: {e}")
            raise
        finally:
            self.stats.total_set_time += time.time() - start_time
    
    async def _write_through(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """写穿透实现"""
        success_count = 0
        
        for instance in self.get_healthy_instances():
            try:
                result = await instance.cache.set(key, value, ttl)
                if result:
                    success_count += 1
                    instance.stats.sets += 1
                else:
                    instance.stats.errors += 1
            except Exception as e:
                instance.failure_count += 1
                instance.stats.errors += 1
                self._logger.warning(f"写入失败 {instance.level.value}: {e}")
        
        if success_count > 0:
            self.stats.sets += 1
            return True
        else:
            self.stats.errors += 1
            return False
    
    async def _write_around(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """写绕过实现（只写最慢层）"""
        slowest = self.get_slowest_instance()
        if slowest:
            try:
                result = await slowest.cache.set(key, value, ttl)
                if result:
                    slowest.stats.sets += 1
                    self.stats.sets += 1
                    return True
                else:
                    slowest.stats.errors += 1
                    self.stats.errors += 1
            except Exception as e:
                slowest.failure_count += 1
                self._logger.warning(f"写绕过失败: {e}")
        
        return False
    
    async def _write_back(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """写回实现（先写快层，延迟写慢层）"""
        # 先写入最快的层
        fastest = self.get_fastest_instance()
        if fastest:
            try:
                result = await fastest.cache.set(key, value, ttl)
                if result:
                    fastest.stats.sets += 1
                    self.stats.sets += 1
                    
                    # 标记为需要同步到慢层
                    # TODO: 实现延迟写入机制
                    
                    return True
                else:
                    fastest.stats.errors += 1
            except Exception as e:
                fastest.failure_count += 1
                self._logger.warning(f"写回失败: {e}")
        
        return False
    
    async def _cache_aside_write(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """缓存旁路写入（只写最快层）"""
        fastest = self.get_fastest_instance()
        if fastest:
            try:
                result = await fastest.cache.set(key, value, ttl)
                if result:
                    fastest.stats.sets += 1
                    self.stats.sets += 1
                    return True
                else:
                    fastest.stats.errors += 1
                    self.stats.errors += 1
            except Exception as e:
                fastest.failure_count += 1
                self._logger.warning(f"Cache aside写入失败: {e}")
        
        return False
    
    async def _promote_data(self, key: CacheKey, value: CacheValue, current_instance: CacheInstance):
        """数据提升到更快的层"""
        # 找到比当前实例更快的实例
        faster_instances = [
            inst for inst in self.get_healthy_instances()
            if inst.priority < current_instance.priority
        ]
        
        if not faster_instances:
            return
        
        # 检查是否满足提升条件
        key_str = str(key)
        access_count = self._promotion_candidates.get(key_str, 0)
        
        if access_count >= self.config.promotion_threshold:
            # 提升到最快的层
            fastest = faster_instances[0]
            try:
                await fastest.cache.set(key, value)
                self._logger.debug(f"数据提升: {key_str} -> {fastest.level.value}")
            except Exception as e:
                self._logger.warning(f"数据提升失败: {e}")
    
    async def delete(self, key: CacheKey) -> bool:
        """删除缓存值"""
        start_time = time.time()
        success_count = 0
        
        try:
            # 从所有层删除
            for instance in self.get_healthy_instances():
                try:
                    result = await instance.cache.delete(key)
                    if result:
                        success_count += 1
                        instance.stats.deletes += 1
                except Exception as e:
                    instance.failure_count += 1
                    self._logger.warning(f"删除失败 {instance.level.value}: {e}")
            
            # 清理提升候选
            key_str = str(key)
            self._promotion_candidates.pop(key_str, None)
            
            if success_count > 0:
                self.stats.deletes += 1
                return True
            else:
                self.stats.errors += 1
                return False
                
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Coordinator delete失败: {e}")
            raise
        finally:
            self.stats.total_delete_time += time.time() - start_time
    
    async def exists(self, key: CacheKey) -> bool:
        """检查键是否存在"""
        # 在任何一层存在即为存在
        for instance in self.get_healthy_instances():
            try:
                if await instance.cache.exists(key):
                    return True
            except Exception as e:
                instance.failure_count += 1
                self._logger.warning(f"存在性检查失败 {instance.level.value}: {e}")
        
        return False
    
    async def clear(self) -> bool:
        """清空所有缓存层"""
        success_count = 0
        
        for instance in self.get_healthy_instances():
            try:
                if await instance.cache.clear():
                    success_count += 1
            except Exception as e:
                instance.failure_count += 1
                self._logger.warning(f"清空失败 {instance.level.value}: {e}")
        
        # 清空提升候选
        self._promotion_candidates.clear()
        
        return success_count > 0
    
    async def size(self) -> int:
        """获取缓存大小（返回最大层的大小）"""
        max_size = 0
        
        for instance in self.get_healthy_instances():
            try:
                size = await instance.cache.size()
                max_size = max(max_size, size)
            except Exception as e:
                instance.failure_count += 1
                self._logger.warning(f"大小查询失败 {instance.level.value}: {e}")
        
        return max_size
    
    async def keys(self, pattern: Optional[str] = None) -> List[CacheKey]:
        """获取所有键（合并所有层的键）"""
        all_keys: Set[str] = set()
        
        for instance in self.get_healthy_instances():
            try:
                keys = await instance.cache.keys(pattern)
                all_keys.update(str(key) for key in keys)
            except Exception as e:
                instance.failure_count += 1
                self._logger.warning(f"键查询失败 {instance.level.value}: {e}")
        
        # 转换回CacheKey对象
        result = []
        for key_str in all_keys:
            try:
                parts = key_str.split(':', 1)
                if len(parts) >= 2:
                    result.append(CacheKey(namespace=parts[0], key=parts[1]))
            except Exception:
                continue
        
        return result
    
    async def _sync_caches(self):
        """同步缓存层"""
        if self.config.sync_strategy == CacheSyncStrategy.IMMEDIATE:
            return  # 立即同步在写入时处理
        
        # 实现定期同步等策略
        # TODO: 实现更复杂的同步逻辑
        pass
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self._enabled:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                for instance in self.instances:
                    await instance.health_check()
                    
                    if not instance.is_healthy and instance.failure_count >= self.config.max_failures:
                        self._logger.warning(f"缓存实例不健康: {instance.level.value}, 失败次数: {instance.failure_count}")
                
            except Exception as e:
                self._logger.error(f"健康检查失败: {e}")
    
    async def _sync_loop(self):
        """同步循环"""
        while self._enabled:
            try:
                await asyncio.sleep(self.config.sync_interval)
                await self._sync_caches()
            except Exception as e:
                self._logger.error(f"同步失败: {e}")
    
    # 生命周期管理
    async def start(self):
        """启动协调器"""
        await super().start()
        
        # 启动所有缓存实例
        for instance in self.instances:
            try:
                await instance.cache.start()
            except Exception as e:
                self._logger.error(f"启动缓存实例失败 {instance.level.value}: {e}")
        
        # 启动后台任务
        if self.config.enable_failover:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        if self.config.sync_strategy in [CacheSyncStrategy.PERIODIC]:
            self._sync_task = asyncio.create_task(self._sync_loop())
    
    async def stop(self):
        """停止协调器"""
        await super().stop()
        
        # 取消后台任务
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._sync_task:
            self._sync_task.cancel()
        
        # 停止所有缓存实例
        for instance in self.instances:
            try:
                await instance.cache.stop()
            except Exception as e:
                self._logger.error(f"停止缓存实例失败 {instance.level.value}: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        instance_healths = []
        healthy_count = 0
        
        for instance in self.instances:
            health = await instance.health_check()
            instance_healths.append({
                "level": instance.level.value,
                "healthy": health,
                "failure_count": instance.failure_count,
                "priority": instance.priority
            })
            if health:
                healthy_count += 1
        
        return {
            "healthy": healthy_count > 0,
            "total_instances": len(self.instances),
            "healthy_instances": healthy_count,
            "instances": instance_healths,
            "statistics": self.stats.to_dict()
        }
    
    def get_coordinator_stats(self) -> Dict[str, Any]:
        """获取协调器统计"""
        instance_stats = []
        for instance in self.instances:
            instance_stats.append({
                "level": instance.level.value,
                "healthy": instance.is_healthy,
                "failure_count": instance.failure_count,
                "statistics": instance.stats.to_dict()
            })
        
        return {
            "coordinator_stats": self.stats.to_dict(),
            "instance_stats": instance_stats,
            "promotion_candidates": len(self._promotion_candidates),
            "config": {
                "read_policy": self.config.read_policy.value,
                "write_policy": self.config.write_policy.value,
                "sync_strategy": self.config.sync_strategy.value,
                "enable_failover": self.config.enable_failover,
                "enable_promotion": self.config.enable_promotion
            }
        }


# 便利函数
def create_multi_level_cache(
    memory_config: Optional[MemoryCacheConfig] = None,
    redis_config: Optional[RedisCacheConfig] = None,
    disk_config: Optional[DiskCacheConfig] = None,
    coordinator_config: Optional[CacheCoordinatorConfig] = None
) -> CacheCoordinator:
    """创建多层缓存的便利函数"""
    
    if coordinator_config is None:
        coordinator_config = CacheCoordinatorConfig()
    
    coordinator = CacheCoordinator(coordinator_config)
    
    # 添加内存缓存（优先级0 - 最快）
    if memory_config:
        memory_cache = MemoryCache(memory_config)
        coordinator.add_cache(memory_cache, priority=0)
    
    # 添加Redis缓存（优先级1 - 中等）
    if redis_config and REDIS_AVAILABLE:
        redis_cache = RedisCache(redis_config)
        coordinator.add_cache(redis_cache, priority=1)
    
    # 添加磁盘缓存（优先级2 - 最慢）
    if disk_config:
        disk_cache = DiskCache(disk_config)
        coordinator.add_cache(disk_cache, priority=2)
    
    return coordinator 