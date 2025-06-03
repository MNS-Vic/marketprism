#!/usr/bin/env python3
"""
MarketPrism 服务发现引擎

这个模块实现了企业级服务发现引擎，提供：
- 多策略服务发现
- 智能缓存机制
- 实时服务监听
- 服务解析优化
- 故障转移支持

Week 6 Day 2: 微服务服务发现系统 - 服务发现引擎
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Union
import threading
from collections import defaultdict
import random

from .service_registry import (
    ServiceRegistry, ServiceInstance, ServiceQuery, ServiceFilter,
    ServiceStatus, RegistryEvent, RegistryEventType
)

logger = logging.getLogger(__name__)

class ResolutionStrategy(Enum):
    """服务解析策略"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_RANDOM = "weighted_random"
    HEALTH_AWARE = "health_aware"
    LOCALITY_AWARE = "locality_aware"
    LOAD_AWARE = "load_aware"

class WatchEventType(Enum):
    """监听事件类型"""
    SERVICE_ADDED = "service_added"
    SERVICE_REMOVED = "service_removed"
    SERVICE_UPDATED = "service_updated"
    SERVICE_HEALTHY = "service_healthy"
    SERVICE_UNHEALTHY = "service_unhealthy"

@dataclass
class DiscoveryRequest:
    """服务发现请求"""
    service_name: str
    strategy: ResolutionStrategy = ResolutionStrategy.HEALTH_AWARE
    max_instances: int = 5
    include_unhealthy: bool = False
    timeout: int = 5
    filters: Optional[ServiceFilter] = None
    cache_ttl: Optional[int] = None
    locality: Optional[str] = None

@dataclass
class ServiceResolution:
    """服务解析结果"""
    service_name: str
    instances: List[ServiceInstance]
    selected_instance: Optional[ServiceInstance]
    strategy_used: ResolutionStrategy
    resolution_time: datetime
    cache_hit: bool = False
    
    @property
    def is_available(self) -> bool:
        return len(self.instances) > 0 and self.selected_instance is not None

@dataclass
class DiscoveryResponse:
    """服务发现响应"""
    success: bool
    resolution: Optional[ServiceResolution]
    error_message: Optional[str] = None
    total_time_ms: int = 0

@dataclass
class WatchEvent:
    """监听事件"""
    event_type: WatchEventType
    service_name: str
    service_instance: Optional[ServiceInstance]
    timestamp: datetime

@dataclass
class DiscoveryCacheConfig:
    """服务发现缓存配置"""
    enable_cache: bool = True
    default_ttl: int = 60  # 默认TTL（秒）
    max_cache_size: int = 1000
    cleanup_interval: int = 30
    cache_stats: bool = True

@dataclass
class DiscoveryCache:
    """服务发现缓存"""
    def __init__(self, config: DiscoveryCacheConfig):
        self.config = config
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, datetime] = {}
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_requests": 0
        }
    
    def get(self, key: str) -> Optional[ServiceResolution]:
        """获取缓存项"""
        if not self.config.enable_cache:
            return None
        
        with self._lock:
            self._stats["total_requests"] += 1
            
            if key not in self._cache:
                self._stats["misses"] += 1
                return None
            
            cache_item = self._cache[key]
            
            # 检查是否过期
            if datetime.now() > cache_item["expires_at"]:
                del self._cache[key]
                self._access_times.pop(key, None)
                self._stats["misses"] += 1
                return None
            
            # 更新访问时间
            self._access_times[key] = datetime.now()
            self._stats["hits"] += 1
            
            # 标记为缓存命中
            resolution = cache_item["resolution"]
            resolution.cache_hit = True
            
            return resolution
    
    def put(self, key: str, resolution: ServiceResolution, ttl: Optional[int] = None):
        """存储缓存项"""
        if not self.config.enable_cache:
            return
        
        with self._lock:
            # 检查缓存大小限制
            if len(self._cache) >= self.config.max_cache_size:
                self._evict_oldest()
            
            # 计算过期时间
            cache_ttl = ttl or self.config.default_ttl
            expires_at = datetime.now() + timedelta(seconds=cache_ttl)
            
            # 存储缓存项
            self._cache[key] = {
                "resolution": resolution,
                "expires_at": expires_at,
                "created_at": datetime.now()
            }
            self._access_times[key] = datetime.now()
    
    def invalidate(self, key: str):
        """使缓存项失效"""
        with self._lock:
            self._cache.pop(key, None)
            self._access_times.pop(key, None)
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            hit_rate = 0
            if self._stats["total_requests"] > 0:
                hit_rate = self._stats["hits"] / self._stats["total_requests"]
            
            return {
                **self._stats,
                "hit_rate": hit_rate,
                "cache_size": len(self._cache)
            }
    
    def _evict_oldest(self):
        """驱逐最旧的缓存项"""
        if not self._access_times:
            return
        
        oldest_key = min(self._access_times.keys(), 
                        key=lambda k: self._access_times[k])
        
        self._cache.pop(oldest_key, None)
        self._access_times.pop(oldest_key, None)
        self._stats["evictions"] += 1

class ServiceWatcher:
    """服务监听器"""
    
    def __init__(self, service_name: str, callback: Callable[[WatchEvent], None]):
        self.service_name = service_name
        self.callback = callback
        self.active = True
        self.created_at = datetime.now()
    
    async def notify(self, event: WatchEvent):
        """通知事件"""
        if not self.active:
            return
        
        try:
            if asyncio.iscoroutinefunction(self.callback):
                await self.callback(event)
            else:
                self.callback(event)
        except Exception as e:
            logger.error(f"服务监听器回调异常: {e}")

# 异常类
class ServiceDiscoveryError(Exception):
    """服务发现基础异常"""
    pass

class ServiceResolutionError(ServiceDiscoveryError):
    """服务解析异常"""
    pass

class DiscoveryTimeoutError(ServiceDiscoveryError):
    """发现超时异常"""
    pass

@dataclass
class ServiceDiscoveryConfig:
    """服务发现配置"""
    # 基本配置
    default_strategy: ResolutionStrategy = ResolutionStrategy.HEALTH_AWARE
    default_timeout: int = 5
    max_concurrent_discoveries: int = 100
    
    # 缓存配置
    cache_config: DiscoveryCacheConfig = field(default_factory=DiscoveryCacheConfig)
    
    # 重试配置
    max_retries: int = 3
    retry_delay: float = 0.1
    backoff_multiplier: float = 2.0
    
    # 健康检查配置
    health_check_enabled: bool = True
    health_check_timeout: int = 2
    
    # 性能配置
    enable_metrics: bool = True
    enable_tracing: bool = False
    
    # 策略配置
    locality_zones: List[str] = field(default_factory=list)
    load_balance_weights: Dict[str, int] = field(default_factory=dict)

class ServiceDiscovery:
    """
    企业级服务发现引擎
    
    提供完整的服务发现、解析、缓存和监听功能
    """
    
    def __init__(self, registry: ServiceRegistry, config: ServiceDiscoveryConfig = None):
        self.registry = registry
        self.config = config or ServiceDiscoveryConfig()
        self.cache = DiscoveryCache(self.config.cache_config)
        
        self._watchers: Dict[str, List[ServiceWatcher]] = defaultdict(list)
        self._strategy_counters: Dict[ResolutionStrategy, int] = defaultdict(int)
        self._running = False
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            "total_discoveries": 0,
            "successful_discoveries": 0,
            "failed_discoveries": 0,
            "cache_hits": 0,
            "average_resolution_time": 0.0,
            "active_watchers": 0
        }
        
        # 注册注册表事件监听器
        self.registry.add_event_listener(self._handle_registry_event)
        
        logger.info("服务发现引擎初始化完成")
    
    async def start(self):
        """启动服务发现引擎"""
        if self._running:
            return
        
        logger.info("启动服务发现引擎")
        self._running = True
        
        # 启动缓存清理任务
        if self.config.cache_config.enable_cache:
            asyncio.create_task(self._cache_cleanup_loop())
        
        logger.info("服务发现引擎启动完成")
    
    async def stop(self):
        """停止服务发现引擎"""
        if not self._running:
            return
        
        logger.info("停止服务发现引擎")
        self._running = False
        
        # 清理监听器
        with self._lock:
            for watchers in self._watchers.values():
                for watcher in watchers:
                    watcher.active = False
            self._watchers.clear()
        
        logger.info("服务发现引擎已停止")
    
    async def discover_service(self, request: DiscoveryRequest) -> DiscoveryResponse:
        """发现服务"""
        start_time = time.time()
        
        try:
            with self._lock:
                self._stats["total_discoveries"] += 1
            
            # 检查缓存
            cache_key = self._build_cache_key(request)
            cached_resolution = self.cache.get(cache_key)
            
            if cached_resolution:
                self._stats["cache_hits"] += 1
                return DiscoveryResponse(
                    success=True,
                    resolution=cached_resolution,
                    total_time_ms=int((time.time() - start_time) * 1000)
                )
            
            # 查询服务
            query = ServiceQuery(
                service_name=request.service_name,
                filters=request.filters,
                limit=request.max_instances,
                include_unhealthy=request.include_unhealthy
            )
            
            services = await asyncio.wait_for(
                self.registry.query_services(query),
                timeout=request.timeout
            )
            
            if not services:
                raise ServiceResolutionError(f"没有找到服务: {request.service_name}")
            
            # 应用解析策略
            selected_instance = await self._apply_resolution_strategy(
                services, request.strategy, request
            )
            
            # 创建解析结果
            resolution = ServiceResolution(
                service_name=request.service_name,
                instances=services,
                selected_instance=selected_instance,
                strategy_used=request.strategy,
                resolution_time=datetime.now()
            )
            
            # 缓存结果
            self.cache.put(cache_key, resolution, request.cache_ttl)
            
            # 更新统计
            with self._lock:
                self._stats["successful_discoveries"] += 1
                self._strategy_counters[request.strategy] += 1
            
            total_time = int((time.time() - start_time) * 1000)
            
            return DiscoveryResponse(
                success=True,
                resolution=resolution,
                total_time_ms=total_time
            )
            
        except asyncio.TimeoutError:
            self._stats["failed_discoveries"] += 1
            return DiscoveryResponse(
                success=False,
                resolution=None,
                error_message=f"服务发现超时: {request.timeout}秒",
                total_time_ms=int((time.time() - start_time) * 1000)
            )
        except Exception as e:
            self._stats["failed_discoveries"] += 1
            logger.error(f"服务发现失败: {e}")
            return DiscoveryResponse(
                success=False,
                resolution=None,
                error_message=str(e),
                total_time_ms=int((time.time() - start_time) * 1000)
            )
    
    async def discover_all_instances(self, service_name: str, 
                                   filters: Optional[ServiceFilter] = None) -> List[ServiceInstance]:
        """发现所有服务实例"""
        query = ServiceQuery(
            service_name=service_name,
            filters=filters,
            limit=0,  # 不限制数量
            include_unhealthy=False
        )
        
        return await self.registry.query_services(query)
    
    def watch_service(self, service_name: str, 
                     callback: Callable[[WatchEvent], None]) -> ServiceWatcher:
        """监听服务变化"""
        watcher = ServiceWatcher(service_name, callback)
        
        with self._lock:
            self._watchers[service_name].append(watcher)
            self._stats["active_watchers"] = sum(len(watchers) for watchers in self._watchers.values())
        
        logger.info(f"添加服务监听器: {service_name}")
        return watcher
    
    def unwatch_service(self, watcher: ServiceWatcher):
        """取消监听服务"""
        watcher.active = False
        
        with self._lock:
            watchers = self._watchers.get(watcher.service_name, [])
            if watcher in watchers:
                watchers.remove(watcher)
            
            # 清理空的监听器列表
            if not watchers and watcher.service_name in self._watchers:
                del self._watchers[watcher.service_name]
            
            self._stats["active_watchers"] = sum(len(watchers) for watchers in self._watchers.values())
        
        logger.info(f"移除服务监听器: {watcher.service_name}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            cache_stats = self.cache.get_stats()
            
            # 计算平均解析时间
            success_rate = 0
            if self._stats["total_discoveries"] > 0:
                success_rate = self._stats["successful_discoveries"] / self._stats["total_discoveries"]
            
            return {
                **self._stats,
                "success_rate": success_rate,
                "cache_stats": cache_stats,
                "strategy_usage": dict(self._strategy_counters)
            }
    
    def invalidate_cache(self, service_name: Optional[str] = None):
        """使缓存失效"""
        if service_name:
            # 使特定服务的缓存失效
            keys_to_remove = [key for key in self.cache._cache.keys() 
                            if service_name in key]
            for key in keys_to_remove:
                self.cache.invalidate(key)
        else:
            # 清空所有缓存
            self.cache.clear()
    
    # 私有方法
    def _build_cache_key(self, request: DiscoveryRequest) -> str:
        """构建缓存键"""
        key_parts = [
            request.service_name,
            request.strategy.value,
            str(request.max_instances),
            str(request.include_unhealthy)
        ]
        
        if request.filters:
            if request.filters.environment:
                key_parts.append(f"env:{request.filters.environment}")
            if request.filters.tags:
                key_parts.append(f"tags:{':'.join(sorted(request.filters.tags))}")
            if request.filters.status:
                key_parts.append(f"status:{request.filters.status.value}")
        
        if request.locality:
            key_parts.append(f"locality:{request.locality}")
        
        return "|".join(key_parts)
    
    async def _apply_resolution_strategy(self, services: List[ServiceInstance], 
                                       strategy: ResolutionStrategy,
                                       request: DiscoveryRequest) -> Optional[ServiceInstance]:
        """应用解析策略"""
        if not services:
            return None
        
        # 过滤健康的服务
        healthy_services = [s for s in services if s.status == ServiceStatus.HEALTHY]
        
        # 如果没有健康服务且允许不健康服务，使用所有服务
        available_services = healthy_services if healthy_services else (
            services if request.include_unhealthy else []
        )
        
        if not available_services:
            return None
        
        if strategy == ResolutionStrategy.RANDOM:
            return random.choice(available_services)
        
        elif strategy == ResolutionStrategy.ROUND_ROBIN:
            # 简单的轮询实现
            current_time = int(time.time())
            index = current_time % len(available_services)
            return available_services[index]
        
        elif strategy == ResolutionStrategy.WEIGHTED_RANDOM:
            return self._weighted_random_selection(available_services)
        
        elif strategy == ResolutionStrategy.HEALTH_AWARE:
            # 优先选择健康的服务
            if healthy_services:
                return random.choice(healthy_services)
            return random.choice(available_services)
        
        elif strategy == ResolutionStrategy.LOCALITY_AWARE:
            return self._locality_aware_selection(available_services, request.locality)
        
        elif strategy == ResolutionStrategy.LEAST_CONNECTIONS:
            # 选择连接数最少的服务（简化实现）
            return min(available_services, key=lambda s: hash(s.id) % 100)
        
        elif strategy == ResolutionStrategy.LOAD_AWARE:
            return self._load_aware_selection(available_services)
        
        else:
            return random.choice(available_services)
    
    def _weighted_random_selection(self, services: List[ServiceInstance]) -> ServiceInstance:
        """加权随机选择"""
        weights = []
        for service in services:
            weight = 100  # 默认权重
            if service.primary_endpoint:
                weight = service.primary_endpoint.weight
            weights.append(weight)
        
        total_weight = sum(weights)
        if total_weight == 0:
            return random.choice(services)
        
        r = random.uniform(0, total_weight)
        current_weight = 0
        
        for i, weight in enumerate(weights):
            current_weight += weight
            if r <= current_weight:
                return services[i]
        
        return services[-1]
    
    def _locality_aware_selection(self, services: List[ServiceInstance], 
                                locality: Optional[str]) -> ServiceInstance:
        """地域感知选择"""
        if not locality:
            return random.choice(services)
        
        # 查找同地域服务
        local_services = [
            s for s in services 
            if s.metadata.get_attribute("locality") == locality
        ]
        
        if local_services:
            return random.choice(local_services)
        
        # 如果没有同地域服务，选择任意服务
        return random.choice(services)
    
    def _load_aware_selection(self, services: List[ServiceInstance]) -> ServiceInstance:
        """负载感知选择"""
        # 简化实现：根据服务实例ID的哈希值模拟负载
        loads = []
        for service in services:
            load = hash(service.id) % 100  # 模拟负载 0-99
            loads.append(load)
        
        # 选择负载最低的服务
        min_load_index = loads.index(min(loads))
        return services[min_load_index]
    
    async def _handle_registry_event(self, event: RegistryEvent):
        """处理注册表事件"""
        try:
            if not event.service_name:
                return
            
            # 使相关缓存失效
            self.invalidate_cache(event.service_name)
            
            # 确定监听事件类型
            watch_event_type = None
            
            if event.event_type == RegistryEventType.SERVICE_REGISTERED:
                watch_event_type = WatchEventType.SERVICE_ADDED
            elif event.event_type == RegistryEventType.SERVICE_DEREGISTERED:
                watch_event_type = WatchEventType.SERVICE_REMOVED
            elif event.event_type == RegistryEventType.SERVICE_UPDATED:
                watch_event_type = WatchEventType.SERVICE_UPDATED
            elif event.event_type == RegistryEventType.SERVICE_STATUS_CHANGED:
                new_status = event.data.get("new_status")
                if new_status == ServiceStatus.HEALTHY.value:
                    watch_event_type = WatchEventType.SERVICE_HEALTHY
                elif new_status in [ServiceStatus.UNHEALTHY.value, ServiceStatus.CRITICAL.value]:
                    watch_event_type = WatchEventType.SERVICE_UNHEALTHY
            
            if watch_event_type:
                # 获取服务实例
                service_instance = None
                if event.service_id:
                    service_instance = await self.registry.get_service(event.service_id)
                
                # 创建监听事件
                watch_event = WatchEvent(
                    event_type=watch_event_type,
                    service_name=event.service_name,
                    service_instance=service_instance,
                    timestamp=event.timestamp
                )
                
                # 通知监听器
                await self._notify_watchers(event.service_name, watch_event)
                
        except Exception as e:
            logger.error(f"处理注册表事件失败: {e}")
    
    async def _notify_watchers(self, service_name: str, event: WatchEvent):
        """通知监听器"""
        watchers = self._watchers.get(service_name, [])
        
        for watcher in watchers[:]:  # 创建副本以避免并发修改
            if watcher.active:
                await watcher.notify(event)
            else:
                # 移除非活跃监听器
                watchers.remove(watcher)
    
    async def _cache_cleanup_loop(self):
        """缓存清理循环"""
        while self._running:
            try:
                # 清理过期缓存项
                current_time = datetime.now()
                expired_keys = []
                
                with self.cache._lock:
                    for key, cache_item in self.cache._cache.items():
                        if current_time > cache_item["expires_at"]:
                            expired_keys.append(key)
                
                for key in expired_keys:
                    self.cache.invalidate(key)
                
                if expired_keys:
                    logger.debug(f"清理过期缓存项: {len(expired_keys)}")
                
                await asyncio.sleep(self.config.cache_config.cleanup_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"缓存清理任务异常: {e}")
                await asyncio.sleep(5)