"""
配置源管理器

统一管理多个配置源，支持优先级、合并策略和故障转移。
"""

import asyncio
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging

from .config_repository import (
    ConfigRepository, ConfigSource, ConfigEntry, ConfigSourceType,
    ConfigRepositoryError
)
from .file_repository import FileConfigRepository


class MergeStrategy(Enum):
    """配置合并策略"""
    OVERRIDE = "override"  # 高优先级覆盖低优先级
    MERGE = "merge"  # 合并配置（字典合并）
    FIRST_WINS = "first_wins"  # 第一个找到的值获胜
    LAST_WINS = "last_wins"  # 最后一个值获胜


class FallbackStrategy(Enum):
    """故障转移策略"""
    FAIL_FAST = "fail_fast"  # 快速失败
    SKIP_FAILED = "skip_failed"  # 跳过失败的源
    USE_CACHE = "use_cache"  # 使用缓存值
    USE_DEFAULT = "use_default"  # 使用默认值


@dataclass
class ConfigMergeResult:
    """配置合并结果"""
    key: str
    value: Any
    sources: List[str]  # 贡献该值的配置源
    merge_strategy: MergeStrategy
    timestamp: datetime
    conflicts: List[Dict[str, Any]] = None  # 合并冲突信息
    
    def __post_init__(self):
        if self.conflicts is None:
            self.conflicts = []


@dataclass
class SourceHealth:
    """配置源健康状态"""
    source_name: str
    healthy: bool
    last_check: datetime
    error_count: int = 0
    last_error: Optional[str] = None
    response_time: Optional[float] = None


class ConfigSourceManager:
    """配置源管理器
    
    统一管理多个配置源，提供配置合并、故障转移、
    健康检查和性能监控等功能。
    """
    
    def __init__(self, merge_strategy: MergeStrategy = MergeStrategy.OVERRIDE,
                 fallback_strategy: FallbackStrategy = FallbackStrategy.SKIP_FAILED):
        self.repositories: Dict[str, ConfigRepository] = {}
        self.source_priorities: Dict[str, int] = {}
        self.merge_strategy = merge_strategy
        self.fallback_strategy = fallback_strategy
        self.health_status: Dict[str, SourceHealth] = {}
        self.logger = logging.getLogger(__name__)
        
        # 性能统计
        self.request_counts: Dict[str, int] = {}
        self.error_counts: Dict[str, int] = {}
        self.response_times: Dict[str, List[float]] = {}
        
        # 缓存设置
        self.merged_cache: Dict[str, ConfigMergeResult] = {}
        self.cache_enabled = True
        self.cache_ttl = 300  # 5分钟
    
    async def add_repository(self, repository: ConfigRepository) -> bool:
        """添加配置仓库"""
        try:
            source_name = repository.source.name
            
            # 连接仓库
            await repository.connect()
            
            # 添加到管理器
            self.repositories[source_name] = repository
            self.source_priorities[source_name] = repository.source.priority
            
            # 初始化健康状态
            self.health_status[source_name] = SourceHealth(
                source_name=source_name,
                healthy=True,
                last_check=datetime.datetime.now(datetime.timezone.utc)
            )
            
            # 初始化统计
            self.request_counts[source_name] = 0
            self.error_counts[source_name] = 0
            self.response_times[source_name] = []
            
            self.logger.info(f"Added config repository: {source_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add repository {repository.source.name}: {e}")
            return False
    
    async def remove_repository(self, source_name: str) -> bool:
        """移除配置仓库"""
        try:
            if source_name in self.repositories:
                repository = self.repositories[source_name]
                await repository.disconnect()
                
                # 清理所有相关数据
                del self.repositories[source_name]
                self.source_priorities.pop(source_name, None)
                self.health_status.pop(source_name, None)
                self.request_counts.pop(source_name, None)
                self.error_counts.pop(source_name, None)
                self.response_times.pop(source_name, None)
                
                # 清理缓存中相关的条目
                self._cleanup_cache_for_source(source_name)
                
                self.logger.info(f"Removed config repository: {source_name}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to remove repository {source_name}: {e}")
            return False
    
    async def get(self, key: str, default: Any = None) -> Any:
        """从所有配置源获取配置值"""
        # 检查缓存
        if self.cache_enabled and key in self.merged_cache:
            cached_result = self.merged_cache[key]
            if self._is_cache_valid(cached_result):
                return cached_result.value
        
        # 从所有源获取配置
        results = await self._get_from_all_sources(key)
        
        if not results:
            return default
        
        # 合并配置值
        merged_result = self._merge_config_values(key, results)
        
        # 更新缓存
        if self.cache_enabled:
            self.merged_cache[key] = merged_result
        
        return merged_result.value
    
    async def set(self, key: str, value: Any, target_source: Optional[str] = None) -> bool:
        """设置配置值"""
        if target_source:
            # 设置到指定源
            if target_source not in self.repositories:
                raise ConfigRepositoryError(f"Source not found: {target_source}")
            
            repository = self.repositories[target_source]
            if repository.source.readonly:
                raise ConfigRepositoryError(f"Source is readonly: {target_source}")
            
            result = await repository.set(key, value)
            
            # 清除缓存
            self.merged_cache.pop(key, None)
            
            return result
        else:
            # 设置到第一个可写的源
            for source_name, repository in self._get_sorted_repositories():
                if not repository.source.readonly:
                    result = await repository.set(key, value)
                    
                    # 清除缓存
                    self.merged_cache.pop(key, None)
                    
                    return result
            
            raise ConfigRepositoryError("No writable source available")
    
    async def delete(self, key: str, target_source: Optional[str] = None) -> bool:
        """删除配置值"""
        if target_source:
            # 从指定源删除
            if target_source not in self.repositories:
                raise ConfigRepositoryError(f"Source not found: {target_source}")
            
            repository = self.repositories[target_source]
            if repository.source.readonly:
                raise ConfigRepositoryError(f"Source is readonly: {target_source}")
            
            result = await repository.delete(key)
            
            # 清除缓存
            self.merged_cache.pop(key, None)
            
            return result
        else:
            # 从所有可写源删除
            success_count = 0
            for source_name, repository in self._get_sorted_repositories():
                if not repository.source.readonly:
                    try:
                        if await repository.delete(key):
                            success_count += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete from {source_name}: {e}")
            
            # 清除缓存
            self.merged_cache.pop(key, None)
            
            return success_count > 0
    
    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """列出所有配置键"""
        all_keys = set()
        
        for source_name, repository in self.repositories.items():
            try:
                keys = await repository.list_keys(prefix)
                all_keys.update(keys)
                
                self._record_request(source_name, True)
                
            except Exception as e:
                self._record_request(source_name, False)
                self.logger.warning(f"Failed to list keys from {source_name}: {e}")
                
                if self.fallback_strategy == FallbackStrategy.FAIL_FAST:
                    raise
        
        return sorted(list(all_keys))
    
    async def exists(self, key: str) -> bool:
        """检查配置键是否存在"""
        for source_name, repository in self._get_sorted_repositories():
            try:
                if await repository.exists(key):
                    self._record_request(source_name, True)
                    return True
                
                self._record_request(source_name, True)
                
            except Exception as e:
                self._record_request(source_name, False)
                self.logger.warning(f"Failed to check existence in {source_name}: {e}")
                
                if self.fallback_strategy == FallbackStrategy.FAIL_FAST:
                    raise
        
        return False
    
    async def get_all_configs(self, prefix: Optional[str] = None) -> Dict[str, Any]:
        """获取所有配置"""
        keys = await self.list_keys(prefix)
        configs = {}
        
        for key in keys:
            try:
                value = await self.get(key)
                if value is not None:
                    configs[key] = value
            except Exception as e:
                self.logger.warning(f"Failed to get config {key}: {e}")
        
        return configs
    
    async def _get_from_all_sources(self, key: str) -> List[ConfigEntry]:
        """从所有配置源获取配置值"""
        results = []
        
        for source_name, repository in self._get_sorted_repositories():
            try:
                start_time = datetime.datetime.now(datetime.timezone.utc)
                entry = await repository.get(key)
                end_time = datetime.datetime.now(datetime.timezone.utc)
                
                response_time = (end_time - start_time).total_seconds()
                self._record_response_time(source_name, response_time)
                self._record_request(source_name, True)
                
                if entry:
                    results.append(entry)
                
            except Exception as e:
                self._record_request(source_name, False)
                self._update_health_status(source_name, False, str(e))
                
                self.logger.warning(f"Failed to get config from {source_name}: {e}")
                
                if self.fallback_strategy == FallbackStrategy.FAIL_FAST:
                    raise
                elif self.fallback_strategy == FallbackStrategy.USE_CACHE:
                    # 尝试从该源的缓存获取
                    if hasattr(repository, 'cache') and key in repository.cache:
                        results.append(repository.cache[key])
        
        return results
    
    def _merge_config_values(self, key: str, results: List[ConfigEntry]) -> ConfigMergeResult:
        """合并配置值"""
        if not results:
            raise ConfigRepositoryError(f"No config found for key: {key}")
        
        if len(results) == 1:
            # 只有一个结果，直接返回
            entry = results[0]
            return ConfigMergeResult(
                key=key,
                value=entry.value,
                sources=[entry.source],
                merge_strategy=self.merge_strategy,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
        
        # 多个结果需要合并
        sources = [entry.source for entry in results]
        conflicts = []
        
        if self.merge_strategy == MergeStrategy.OVERRIDE:
            # 按优先级排序，使用最高优先级的值
            sorted_results = sorted(results, key=lambda r: self.source_priorities.get(r.source, 999))
            merged_value = sorted_results[0].value
            
            # 记录冲突
            if len(set(str(r.value) for r in results)) > 1:
                conflicts = [{"source": r.source, "value": r.value} for r in results]
        
        elif self.merge_strategy == MergeStrategy.MERGE:
            # 尝试合并字典值
            merged_value = self._merge_dict_values([r.value for r in results])
        
        elif self.merge_strategy == MergeStrategy.FIRST_WINS:
            merged_value = results[0].value
        
        elif self.merge_strategy == MergeStrategy.LAST_WINS:
            merged_value = results[-1].value
        
        else:
            # 默认使用第一个值
            merged_value = results[0].value
        
        return ConfigMergeResult(
            key=key,
            value=merged_value,
            sources=sources,
            merge_strategy=self.merge_strategy,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            conflicts=conflicts
        )
    
    def _merge_dict_values(self, values: List[Any]) -> Any:
        """合并字典值"""
        if not values:
            return None
        
        # 如果所有值都是字典，则合并它们
        if all(isinstance(v, dict) for v in values):
            merged = {}
            for value in values:
                merged.update(value)
            return merged
        
        # 否则返回第一个值
        return values[0]
    
    def _get_sorted_repositories(self) -> List[tuple]:
        """获取按优先级排序的仓库列表"""
        items = list(self.repositories.items())
        return sorted(items, key=lambda x: self.source_priorities.get(x[0], 999))
    
    def _is_cache_valid(self, cached_result: ConfigMergeResult) -> bool:
        """检查缓存是否有效"""
        if not self.cache_enabled:
            return False
        
        age = (datetime.datetime.now(datetime.timezone.utc) - cached_result.timestamp).total_seconds()
        return age < self.cache_ttl
    
    def _cleanup_cache_for_source(self, source_name: str):
        """清理特定源的缓存条目"""
        keys_to_remove = []
        for key, result in self.merged_cache.items():
            if source_name in result.sources:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.merged_cache[key]
    
    def _record_request(self, source_name: str, success: bool):
        """记录请求统计"""
        self.request_counts[source_name] = self.request_counts.get(source_name, 0) + 1
        
        if not success:
            self.error_counts[source_name] = self.error_counts.get(source_name, 0) + 1
        
        # 更新健康状态
        self._update_health_status(source_name, success)
    
    def _record_response_time(self, source_name: str, response_time: float):
        """记录响应时间"""
        if source_name not in self.response_times:
            self.response_times[source_name] = []
        
        times = self.response_times[source_name]
        times.append(response_time)
        
        # 保留最近100个记录
        if len(times) > 100:
            times.pop(0)
    
    def _update_health_status(self, source_name: str, healthy: bool, error: Optional[str] = None):
        """更新健康状态"""
        if source_name not in self.health_status:
            self.health_status[source_name] = SourceHealth(
                source_name=source_name,
                healthy=healthy,
                last_check=datetime.datetime.now(datetime.timezone.utc)
            )
        else:
            health = self.health_status[source_name]
            health.healthy = healthy
            health.last_check = datetime.datetime.now(datetime.timezone.utc)
            
            if not healthy:
                health.error_count += 1
                health.last_error = error
    
    # 管理和监控方法
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        overall_healthy = True
        source_health = {}
        
        for source_name, repository in self.repositories.items():
            try:
                health_info = await repository.health_check()
                source_health[source_name] = health_info
                
                if not health_info.get('healthy', False):
                    overall_healthy = False
                    
            except Exception as e:
                source_health[source_name] = {
                    "healthy": False,
                    "error": str(e)
                }
                overall_healthy = False
        
        return {
            "healthy": overall_healthy,
            "total_sources": len(self.repositories),
            "healthy_sources": sum(1 for h in source_health.values() if h.get('healthy', False)),
            "sources": source_health,
            "merge_strategy": self.merge_strategy.value,
            "fallback_strategy": self.fallback_strategy.value,
            "cache_enabled": self.cache_enabled,
            "cache_size": len(self.merged_cache)
        }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        metrics = {
            "total_sources": len(self.repositories),
            "active_sources": sum(1 for h in self.health_status.values() if h.healthy),
            "total_requests": sum(self.request_counts.values()),
            "total_errors": sum(self.error_counts.values()),
            "cache_enabled": self.cache_enabled,
            "cache_size": len(self.merged_cache),
            "cache_hit_rate": self._calculate_cache_hit_rate(),
            "sources": {}
        }
        
        for source_name, repository in self.repositories.items():
            source_metrics = await repository.get_metrics()
            
            # 添加管理器级别的统计
            source_metrics.update({
                "requests": self.request_counts.get(source_name, 0),
                "errors": self.error_counts.get(source_name, 0),
                "error_rate": self._calculate_error_rate(source_name),
                "avg_response_time": self._calculate_avg_response_time(source_name),
                "healthy": self.health_status.get(source_name, SourceHealth("", False, datetime.datetime.now(datetime.timezone.utc))).healthy
            })
            
            metrics["sources"][source_name] = source_metrics
        
        return metrics
    
    def _calculate_cache_hit_rate(self) -> float:
        """计算缓存命中率"""
        # 简化实现，实际应该跟踪命中和未命中次数
        return 0.75  # 示例值
    
    def _calculate_error_rate(self, source_name: str) -> float:
        """计算错误率"""
        total_requests = self.request_counts.get(source_name, 0)
        total_errors = self.error_counts.get(source_name, 0)
        
        if total_requests == 0:
            return 0.0
        
        return total_errors / total_requests
    
    def _calculate_avg_response_time(self, source_name: str) -> float:
        """计算平均响应时间"""
        times = self.response_times.get(source_name, [])
        if not times:
            return 0.0
        
        return sum(times) / len(times)
    
    def clear_cache(self):
        """清空缓存"""
        self.merged_cache.clear()
    
    def set_merge_strategy(self, strategy: MergeStrategy):
        """设置合并策略"""
        self.merge_strategy = strategy
        # 清空缓存，因为合并策略改变了
        self.clear_cache()
    
    def set_fallback_strategy(self, strategy: FallbackStrategy):
        """设置故障转移策略"""
        self.fallback_strategy = strategy
    
    def enable_cache(self, ttl: int = 300):
        """启用缓存"""
        self.cache_enabled = True
        self.cache_ttl = ttl
    
    def disable_cache(self):
        """禁用缓存"""
        self.cache_enabled = False
        self.clear_cache()
    
    async def reload_all(self):
        """重新加载所有配置源"""
        self.clear_cache()
        
        for source_name, repository in self.repositories.items():
            try:
                if hasattr(repository, 'refresh_cache'):
                    await repository.refresh_cache()
                self.logger.info(f"Reloaded config source: {source_name}")
            except Exception as e:
                self.logger.error(f"Failed to reload {source_name}: {e}")
    
    def get_source_priorities(self) -> Dict[str, int]:
        """获取配置源优先级"""
        return self.source_priorities.copy()
    
    def set_source_priority(self, source_name: str, priority: int):
        """设置配置源优先级"""
        if source_name in self.repositories:
            self.source_priorities[source_name] = priority
            self.repositories[source_name].source.priority = priority
            # 清空缓存，因为优先级改变了
            self.clear_cache()
    
    def __str__(self) -> str:
        return f"ConfigSourceManager(sources={len(self.repositories)}, strategy={self.merge_strategy.value})"
    
    def __repr__(self) -> str:
        return (f"ConfigSourceManager(sources={list(self.repositories.keys())}, "
                f"merge_strategy={self.merge_strategy.value}, "
                f"fallback_strategy={self.fallback_strategy.value})")