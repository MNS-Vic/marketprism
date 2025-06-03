"""
MarketPrism 配置同步机制
实现分布式配置的同步算法，支持增量同步和冲突解决
"""

import asyncio
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..version_control.config_version_control import ConfigVersionControl
from ..repositories.config_repository import ConfigRepository


class SyncStatus(Enum):
    """同步状态枚举"""
    IDLE = "idle"
    SYNCING = "syncing"
    CONFLICT = "conflict"
    ERROR = "error"
    COMPLETED = "completed"


class SyncStrategy(Enum):
    """同步策略枚举"""
    FULL_SYNC = "full_sync"
    INCREMENTAL_SYNC = "incremental_sync"
    SELECTIVE_SYNC = "selective_sync"
    CONFLICT_RESOLUTION = "conflict_resolution"


class ConflictResolution(Enum):
    """冲突解决策略枚举"""
    SERVER_WINS = "server_wins"
    CLIENT_WINS = "client_wins"
    MERGE_VALUES = "merge_values"
    MANUAL_RESOLUTION = "manual_resolution"
    ABORT_SYNC = "abort_sync"


@dataclass
class SyncConflict:
    """同步冲突"""
    key: str
    server_value: Any
    client_value: Any
    server_version: Optional[str]
    client_version: Optional[str]
    server_timestamp: datetime
    client_timestamp: datetime
    conflict_type: str  # 'value_conflict', 'version_conflict', 'timestamp_conflict'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'key': self.key,
            'server_value': self.server_value,
            'client_value': self.client_value,
            'server_version': self.server_version,
            'client_version': self.client_version,
            'server_timestamp': self.server_timestamp.isoformat(),
            'client_timestamp': self.client_timestamp.isoformat(),
            'conflict_type': self.conflict_type
        }


@dataclass
class SyncResult:
    """同步结果"""
    status: SyncStatus
    strategy: SyncStrategy
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: float
    synced_keys: List[str]
    conflicts: List[SyncConflict]
    errors: List[str]
    total_keys: int
    successful_keys: int
    failed_keys: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'status': self.status.value,
            'strategy': self.strategy.value,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration_seconds,
            'synced_keys': self.synced_keys,
            'conflicts': [c.to_dict() for c in self.conflicts],
            'errors': self.errors,
            'total_keys': self.total_keys,
            'successful_keys': self.successful_keys,
            'failed_keys': self.failed_keys
        }


@dataclass
class SyncMetrics:
    """同步指标"""
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    total_conflicts: int = 0
    resolved_conflicts: int = 0
    average_sync_time: float = 0.0
    last_sync_time: Optional[datetime] = None
    last_full_sync_time: Optional[datetime] = None
    data_transferred_bytes: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        if self.last_sync_time:
            result['last_sync_time'] = self.last_sync_time.isoformat()
        if self.last_full_sync_time:
            result['last_full_sync_time'] = self.last_full_sync_time.isoformat()
        return result


class ConfigSync:
    """
    配置同步机制
    实现分布式配置的同步算法，支持增量同步和冲突解决
    """
    
    def __init__(
        self,
        local_repository: ConfigRepository,
        remote_repository: ConfigRepository,
        version_control: Optional[ConfigVersionControl] = None,
        default_conflict_resolution: ConflictResolution = ConflictResolution.SERVER_WINS,
        sync_interval: int = 300,  # 5分钟
        max_concurrent_syncs: int = 10,
        enable_auto_sync: bool = True
    ):
        """
        初始化配置同步器
        
        Args:
            local_repository: 本地配置仓库
            remote_repository: 远程配置仓库
            version_control: 版本控制系统
            default_conflict_resolution: 默认冲突解决策略
            sync_interval: 自动同步间隔（秒）
            max_concurrent_syncs: 最大并发同步数
            enable_auto_sync: 是否启用自动同步
        """
        self.local_repository = local_repository
        self.remote_repository = remote_repository
        self.version_control = version_control
        self.default_conflict_resolution = default_conflict_resolution
        self.sync_interval = sync_interval
        self.max_concurrent_syncs = max_concurrent_syncs
        self.enable_auto_sync = enable_auto_sync
        
        # 状态管理
        self.status = SyncStatus.IDLE
        self.current_sync_result: Optional[SyncResult] = None
        self.sync_history: List[SyncResult] = []
        self.metrics = SyncMetrics()
        
        # 冲突管理
        self.pending_conflicts: List[SyncConflict] = []
        self.conflict_resolvers: Dict[str, ConflictResolution] = {}
        
        # 线程管理
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_syncs)
        self.auto_sync_thread = None
        self.sync_lock = threading.RLock()
        
        # 同步状态
        self.last_sync_checksums: Dict[str, str] = {}
        self.sync_filters: Set[str] = set()  # 同步过滤器
        
        self.logger = logging.getLogger(__name__)
        
        # 启动自动同步
        if self.enable_auto_sync:
            self._start_auto_sync()
    
    def full_sync(
        self,
        direction: str = "bidirectional",  # "pull", "push", "bidirectional"
        conflict_resolution: Optional[ConflictResolution] = None
    ) -> SyncResult:
        """
        执行完整同步
        
        Args:
            direction: 同步方向
            conflict_resolution: 冲突解决策略
            
        Returns:
            同步结果
        """
        with self.sync_lock:
            if self.status == SyncStatus.SYNCING:
                raise RuntimeError("Sync already in progress")
            
            self.status = SyncStatus.SYNCING
            start_time = datetime.now()
            
            sync_result = SyncResult(
                status=SyncStatus.SYNCING,
                strategy=SyncStrategy.FULL_SYNC,
                start_time=start_time,
                end_time=None,
                duration_seconds=0.0,
                synced_keys=[],
                conflicts=[],
                errors=[],
                total_keys=0,
                successful_keys=0,
                failed_keys=0
            )
            
            self.current_sync_result = sync_result
        
        try:
            self.logger.info(f"Starting full sync (direction: {direction})")
            
            if direction in ["pull", "bidirectional"]:
                # 从远程拉取到本地
                self._sync_from_remote_to_local(sync_result, conflict_resolution)
            
            if direction in ["push", "bidirectional"]:
                # 从本地推送到远程
                self._sync_from_local_to_remote(sync_result, conflict_resolution)
            
            # 更新同步状态
            end_time = datetime.now()
            sync_result.end_time = end_time
            sync_result.duration_seconds = (end_time - start_time).total_seconds()
            
            if sync_result.conflicts:
                sync_result.status = SyncStatus.CONFLICT
            else:
                sync_result.status = SyncStatus.COMPLETED
            
            self._update_metrics(sync_result)
            self.metrics.last_full_sync_time = end_time
            
            self.logger.info(f"Full sync completed: {sync_result.successful_keys}/{sync_result.total_keys} keys synced")
            
        except Exception as e:
            sync_result.status = SyncStatus.ERROR
            sync_result.errors.append(str(e))
            self.logger.error(f"Full sync failed: {e}")
        
        finally:
            with self.sync_lock:
                self.status = SyncStatus.IDLE
                self.sync_history.append(sync_result)
                # 保留最近100次同步历史
                if len(self.sync_history) > 100:
                    self.sync_history = self.sync_history[-100:]
        
        return sync_result
    
    def incremental_sync(
        self,
        since: Optional[datetime] = None,
        conflict_resolution: Optional[ConflictResolution] = None
    ) -> SyncResult:
        """
        执行增量同步
        
        Args:
            since: 同步起始时间
            conflict_resolution: 冲突解决策略
            
        Returns:
            同步结果
        """
        with self.sync_lock:
            if self.status == SyncStatus.SYNCING:
                raise RuntimeError("Sync already in progress")
            
            self.status = SyncStatus.SYNCING
            start_time = datetime.now()
            
            # 如果没有指定起始时间，使用上次同步时间
            if since is None:
                since = self.metrics.last_sync_time or (start_time - timedelta(hours=1))
            
            sync_result = SyncResult(
                status=SyncStatus.SYNCING,
                strategy=SyncStrategy.INCREMENTAL_SYNC,
                start_time=start_time,
                end_time=None,
                duration_seconds=0.0,
                synced_keys=[],
                conflicts=[],
                errors=[],
                total_keys=0,
                successful_keys=0,
                failed_keys=0
            )
            
            self.current_sync_result = sync_result
        
        try:
            self.logger.info(f"Starting incremental sync since {since.isoformat()}")
            
            # 获取变更的配置
            changed_keys = self._get_changed_keys_since(since)
            sync_result.total_keys = len(changed_keys)
            
            if not changed_keys:
                self.logger.info("No changes detected, skipping sync")
                sync_result.status = SyncStatus.COMPLETED
                return sync_result
            
            # 同步变更的配置
            for key in changed_keys:
                try:
                    self._sync_single_key(key, sync_result, conflict_resolution)
                    sync_result.successful_keys += 1
                    sync_result.synced_keys.append(key)
                except Exception as e:
                    sync_result.failed_keys += 1
                    sync_result.errors.append(f"Failed to sync {key}: {e}")
                    self.logger.error(f"Failed to sync key {key}: {e}")
            
            # 更新同步状态
            end_time = datetime.now()
            sync_result.end_time = end_time
            sync_result.duration_seconds = (end_time - start_time).total_seconds()
            
            if sync_result.conflicts:
                sync_result.status = SyncStatus.CONFLICT
            else:
                sync_result.status = SyncStatus.COMPLETED
            
            self._update_metrics(sync_result)
            
            self.logger.info(f"Incremental sync completed: {sync_result.successful_keys}/{sync_result.total_keys} keys synced")
            
        except Exception as e:
            sync_result.status = SyncStatus.ERROR
            sync_result.errors.append(str(e))
            self.logger.error(f"Incremental sync failed: {e}")
        
        finally:
            with self.sync_lock:
                self.status = SyncStatus.IDLE
                self.sync_history.append(sync_result)
                if len(self.sync_history) > 100:
                    self.sync_history = self.sync_history[-100:]
        
        return sync_result
    
    def selective_sync(
        self,
        namespaces: List[str],
        conflict_resolution: Optional[ConflictResolution] = None
    ) -> SyncResult:
        """
        执行选择性同步
        
        Args:
            namespaces: 要同步的命名空间列表
            conflict_resolution: 冲突解决策略
            
        Returns:
            同步结果
        """
        with self.sync_lock:
            if self.status == SyncStatus.SYNCING:
                raise RuntimeError("Sync already in progress")
            
            self.status = SyncStatus.SYNCING
            start_time = datetime.now()
            
            sync_result = SyncResult(
                status=SyncStatus.SYNCING,
                strategy=SyncStrategy.SELECTIVE_SYNC,
                start_time=start_time,
                end_time=None,
                duration_seconds=0.0,
                synced_keys=[],
                conflicts=[],
                errors=[],
                total_keys=0,
                successful_keys=0,
                failed_keys=0
            )
            
            self.current_sync_result = sync_result
        
        try:
            self.logger.info(f"Starting selective sync for namespaces: {namespaces}")
            
            # 获取指定命名空间的所有配置键
            all_keys = set()
            for namespace in namespaces:
                try:
                    local_keys = self.local_repository.list_keys(f"{namespace}.*")
                    remote_keys = self.remote_repository.list_keys(f"{namespace}.*")
                    all_keys.update(local_keys)
                    all_keys.update(remote_keys)
                except Exception as e:
                    sync_result.errors.append(f"Failed to list keys for namespace {namespace}: {e}")
                    self.logger.error(f"Failed to list keys for namespace {namespace}: {e}")
            
            sync_result.total_keys = len(all_keys)
            
            # 同步所有键
            for key in all_keys:
                try:
                    self._sync_single_key(key, sync_result, conflict_resolution)
                    sync_result.successful_keys += 1
                    sync_result.synced_keys.append(key)
                except Exception as e:
                    sync_result.failed_keys += 1
                    sync_result.errors.append(f"Failed to sync {key}: {e}")
                    self.logger.error(f"Failed to sync key {key}: {e}")
            
            # 更新同步状态
            end_time = datetime.now()
            sync_result.end_time = end_time
            sync_result.duration_seconds = (end_time - start_time).total_seconds()
            
            if sync_result.conflicts:
                sync_result.status = SyncStatus.CONFLICT
            else:
                sync_result.status = SyncStatus.COMPLETED
            
            self._update_metrics(sync_result)
            
            self.logger.info(f"Selective sync completed: {sync_result.successful_keys}/{sync_result.total_keys} keys synced")
            
        except Exception as e:
            sync_result.status = SyncStatus.ERROR
            sync_result.errors.append(str(e))
            self.logger.error(f"Selective sync failed: {e}")
        
        finally:
            with self.sync_lock:
                self.status = SyncStatus.IDLE
                self.sync_history.append(sync_result)
                if len(self.sync_history) > 100:
                    self.sync_history = self.sync_history[-100:]
        
        return sync_result
    
    def resolve_conflicts(
        self,
        conflicts: List[SyncConflict],
        resolution_strategy: ConflictResolution
    ) -> SyncResult:
        """
        解决同步冲突
        
        Args:
            conflicts: 冲突列表
            resolution_strategy: 解决策略
            
        Returns:
            同步结果
        """
        start_time = datetime.now()
        
        sync_result = SyncResult(
            status=SyncStatus.SYNCING,
            strategy=SyncStrategy.CONFLICT_RESOLUTION,
            start_time=start_time,
            end_time=None,
            duration_seconds=0.0,
            synced_keys=[],
            conflicts=[],
            errors=[],
            total_keys=len(conflicts),
            successful_keys=0,
            failed_keys=0
        )
        
        try:
            self.logger.info(f"Resolving {len(conflicts)} conflicts with strategy: {resolution_strategy.value}")
            
            for conflict in conflicts:
                try:
                    resolved = self._resolve_single_conflict(conflict, resolution_strategy)
                    if resolved:
                        sync_result.successful_keys += 1
                        sync_result.synced_keys.append(conflict.key)
                        self.metrics.resolved_conflicts += 1
                    else:
                        sync_result.conflicts.append(conflict)
                except Exception as e:
                    sync_result.failed_keys += 1
                    sync_result.errors.append(f"Failed to resolve conflict for {conflict.key}: {e}")
                    self.logger.error(f"Failed to resolve conflict for {conflict.key}: {e}")
            
            # 更新同步状态
            end_time = datetime.now()
            sync_result.end_time = end_time
            sync_result.duration_seconds = (end_time - start_time).total_seconds()
            
            if sync_result.conflicts:
                sync_result.status = SyncStatus.CONFLICT
            else:
                sync_result.status = SyncStatus.COMPLETED
            
            # 清理已解决的冲突
            self.pending_conflicts = [c for c in self.pending_conflicts if c.key not in sync_result.synced_keys]
            
            self.logger.info(f"Conflict resolution completed: {sync_result.successful_keys}/{sync_result.total_keys} conflicts resolved")
            
        except Exception as e:
            sync_result.status = SyncStatus.ERROR
            sync_result.errors.append(str(e))
            self.logger.error(f"Conflict resolution failed: {e}")
        
        return sync_result
    
    def _sync_from_remote_to_local(
        self,
        sync_result: SyncResult,
        conflict_resolution: Optional[ConflictResolution]
    ):
        """从远程同步到本地"""
        try:
            remote_keys = self.remote_repository.list_keys()
            
            for key in remote_keys:
                try:
                    remote_value = self.remote_repository.get(key)
                    local_value = None
                    
                    try:
                        local_value = self.local_repository.get(key)
                    except:
                        # 本地不存在该配置
                        pass
                    
                    if local_value is None:
                        # 新配置，直接添加
                        self.local_repository.set(key, remote_value)
                        sync_result.synced_keys.append(key)
                        sync_result.successful_keys += 1
                    elif local_value != remote_value:
                        # 配置冲突，需要解决
                        conflict = self._create_conflict(key, remote_value, local_value, "pull")
                        if self._resolve_single_conflict(conflict, conflict_resolution):
                            sync_result.synced_keys.append(key)
                            sync_result.successful_keys += 1
                        else:
                            sync_result.conflicts.append(conflict)
                    
                    sync_result.total_keys += 1
                    
                except Exception as e:
                    sync_result.failed_keys += 1
                    sync_result.errors.append(f"Failed to sync {key} from remote: {e}")
                    
        except Exception as e:
            sync_result.errors.append(f"Failed to list remote keys: {e}")
    
    def _sync_from_local_to_remote(
        self,
        sync_result: SyncResult,
        conflict_resolution: Optional[ConflictResolution]
    ):
        """从本地同步到远程"""
        try:
            local_keys = self.local_repository.list_keys()
            
            for key in local_keys:
                try:
                    local_value = self.local_repository.get(key)
                    remote_value = None
                    
                    try:
                        remote_value = self.remote_repository.get(key)
                    except:
                        # 远程不存在该配置
                        pass
                    
                    if remote_value is None:
                        # 新配置，直接添加
                        self.remote_repository.set(key, local_value)
                        if key not in sync_result.synced_keys:
                            sync_result.synced_keys.append(key)
                            sync_result.successful_keys += 1
                    elif remote_value != local_value:
                        # 配置冲突，需要解决
                        conflict = self._create_conflict(key, remote_value, local_value, "push")
                        if self._resolve_single_conflict(conflict, conflict_resolution):
                            if key not in sync_result.synced_keys:
                                sync_result.synced_keys.append(key)
                                sync_result.successful_keys += 1
                        else:
                            # 避免重复添加冲突
                            if not any(c.key == key for c in sync_result.conflicts):
                                sync_result.conflicts.append(conflict)
                    
                    if key not in [k for k in sync_result.synced_keys]:
                        sync_result.total_keys += 1
                    
                except Exception as e:
                    sync_result.failed_keys += 1
                    sync_result.errors.append(f"Failed to sync {key} to remote: {e}")
                    
        except Exception as e:
            sync_result.errors.append(f"Failed to list local keys: {e}")
    
    def _sync_single_key(
        self,
        key: str,
        sync_result: SyncResult,
        conflict_resolution: Optional[ConflictResolution]
    ):
        """同步单个配置键"""
        local_value = None
        remote_value = None
        
        try:
            local_value = self.local_repository.get(key)
        except:
            pass
        
        try:
            remote_value = self.remote_repository.get(key)
        except:
            pass
        
        if local_value is None and remote_value is None:
            # 两边都不存在，跳过
            return
        elif local_value is None:
            # 只有远程存在，拉取到本地
            self.local_repository.set(key, remote_value)
        elif remote_value is None:
            # 只有本地存在，推送到远程
            self.remote_repository.set(key, local_value)
        elif local_value != remote_value:
            # 两边都存在但不同，产生冲突
            conflict = self._create_conflict(key, remote_value, local_value, "bidirectional")
            if not self._resolve_single_conflict(conflict, conflict_resolution):
                sync_result.conflicts.append(conflict)
                raise Exception(f"Unresolved conflict for key {key}")
    
    def _create_conflict(
        self,
        key: str,
        server_value: Any,
        client_value: Any,
        sync_direction: str
    ) -> SyncConflict:
        """创建同步冲突"""
        return SyncConflict(
            key=key,
            server_value=server_value,
            client_value=client_value,
            server_version=None,  # 可以从版本控制系统获取
            client_version=None,
            server_timestamp=datetime.now(),
            client_timestamp=datetime.now(),
            conflict_type="value_conflict"
        )
    
    def _resolve_single_conflict(
        self,
        conflict: SyncConflict,
        resolution_strategy: Optional[ConflictResolution]
    ) -> bool:
        """解决单个冲突"""
        strategy = resolution_strategy or self.default_conflict_resolution
        
        try:
            if strategy == ConflictResolution.SERVER_WINS:
                # 服务器值获胜
                self.local_repository.set(conflict.key, conflict.server_value)
                return True
            
            elif strategy == ConflictResolution.CLIENT_WINS:
                # 客户端值获胜
                self.remote_repository.set(conflict.key, conflict.client_value)
                return True
            
            elif strategy == ConflictResolution.MERGE_VALUES:
                # 尝试合并值
                merged_value = self._merge_values(conflict.server_value, conflict.client_value)
                if merged_value is not None:
                    self.local_repository.set(conflict.key, merged_value)
                    self.remote_repository.set(conflict.key, merged_value)
                    return True
                else:
                    # 无法合并，添加到待处理冲突
                    self.pending_conflicts.append(conflict)
                    return False
            
            elif strategy == ConflictResolution.MANUAL_RESOLUTION:
                # 手动解决，添加到待处理冲突
                self.pending_conflicts.append(conflict)
                return False
            
            elif strategy == ConflictResolution.ABORT_SYNC:
                # 中止同步
                raise Exception(f"Sync aborted due to conflict in key {conflict.key}")
            
            else:
                self.logger.warning(f"Unknown conflict resolution strategy: {strategy}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to resolve conflict for {conflict.key}: {e}")
            return False
    
    def _merge_values(self, server_value: Any, client_value: Any) -> Optional[Any]:
        """尝试合并两个值"""
        # 如果类型相同，尝试合并
        if type(server_value) == type(client_value):
            if isinstance(server_value, dict) and isinstance(client_value, dict):
                # 合并字典
                merged = server_value.copy()
                merged.update(client_value)
                return merged
            elif isinstance(server_value, list) and isinstance(client_value, list):
                # 合并列表（去重）
                merged = list(set(server_value + client_value))
                return merged
            elif isinstance(server_value, (int, float)) and isinstance(client_value, (int, float)):
                # 数值取平均
                return (server_value + client_value) / 2
        
        # 无法合并
        return None
    
    def _get_changed_keys_since(self, since: datetime) -> List[str]:
        """获取自指定时间以来变更的配置键"""
        changed_keys = set()
        
        # 如果有版本控制系统，使用版本历史
        if self.version_control:
            try:
                commits = self.version_control.get_commit_history(
                    since=since,
                    limit=1000
                )
                
                for commit in commits:
                    for change in commit.changes:
                        changed_keys.add(change.file_path)
                        
            except Exception as e:
                self.logger.warning(f"Failed to get changes from version control: {e}")
        
        # 如果没有版本控制，比较校验和
        if not changed_keys:
            try:
                all_keys = set()
                all_keys.update(self.local_repository.list_keys())
                all_keys.update(self.remote_repository.list_keys())
                
                for key in all_keys:
                    current_checksum = self._calculate_key_checksum(key)
                    last_checksum = self.last_sync_checksums.get(key)
                    
                    if current_checksum != last_checksum:
                        changed_keys.add(key)
                        self.last_sync_checksums[key] = current_checksum
                        
            except Exception as e:
                self.logger.warning(f"Failed to detect changes by checksum: {e}")
                # 如果无法检测变更，返回所有键
                try:
                    all_keys = set()
                    all_keys.update(self.local_repository.list_keys())
                    all_keys.update(self.remote_repository.list_keys())
                    changed_keys = all_keys
                except:
                    pass
        
        return list(changed_keys)
    
    def _calculate_key_checksum(self, key: str) -> str:
        """计算配置键的校验和"""
        try:
            local_value = self.local_repository.get(key)
            remote_value = self.remote_repository.get(key)
            
            combined_value = {
                'local': local_value,
                'remote': remote_value
            }
            
            value_str = json.dumps(combined_value, sort_keys=True, default=str)
            return hashlib.md5(value_str.encode()).hexdigest()
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate checksum for {key}: {e}")
            return ""
    
    def _update_metrics(self, sync_result: SyncResult):
        """更新同步指标"""
        self.metrics.total_syncs += 1
        
        if sync_result.status == SyncStatus.COMPLETED:
            self.metrics.successful_syncs += 1
        else:
            self.metrics.failed_syncs += 1
        
        self.metrics.total_conflicts += len(sync_result.conflicts)
        self.metrics.last_sync_time = sync_result.end_time or datetime.now()
        
        # 更新平均同步时间
        if self.metrics.successful_syncs > 0:
            total_time = self.metrics.average_sync_time * (self.metrics.successful_syncs - 1)
            self.metrics.average_sync_time = (total_time + sync_result.duration_seconds) / self.metrics.successful_syncs
        else:
            self.metrics.average_sync_time = sync_result.duration_seconds
        
        # 估算传输数据量
        estimated_bytes = len(sync_result.synced_keys) * 100  # 粗略估算
        self.metrics.data_transferred_bytes += estimated_bytes
    
    def _start_auto_sync(self):
        """启动自动同步"""
        def auto_sync_worker():
            while self.enable_auto_sync:
                try:
                    time.sleep(self.sync_interval)
                    
                    if self.status == SyncStatus.IDLE:
                        self.logger.debug("Starting automatic incremental sync")
                        result = self.incremental_sync()
                        
                        if result.status == SyncStatus.ERROR:
                            self.logger.warning(f"Auto sync failed: {result.errors}")
                        elif result.conflicts:
                            self.logger.info(f"Auto sync completed with {len(result.conflicts)} conflicts")
                        else:
                            self.logger.debug(f"Auto sync completed successfully: {result.successful_keys} keys synced")
                    
                except Exception as e:
                    self.logger.error(f"Auto sync error: {e}")
        
        self.auto_sync_thread = threading.Thread(target=auto_sync_worker, daemon=True)
        self.auto_sync_thread.start()
    
    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        return {
            'status': self.status.value,
            'current_sync': self.current_sync_result.to_dict() if self.current_sync_result else None,
            'pending_conflicts': len(self.pending_conflicts),
            'metrics': self.metrics.to_dict(),
            'auto_sync_enabled': self.enable_auto_sync,
            'sync_interval': self.sync_interval
        }
    
    def get_sync_metrics(self) -> Dict[str, Any]:
        """获取同步指标"""
        return self.metrics.to_dict()
    
    def get_sync_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取同步历史"""
        return [result.to_dict() for result in self.sync_history[-limit:]]
    
    def get_pending_conflicts(self) -> List[Dict[str, Any]]:
        """获取待处理冲突"""
        return [conflict.to_dict() for conflict in self.pending_conflicts]
    
    def stop(self):
        """停止同步服务"""
        self.enable_auto_sync = False
        
        # 等待当前同步完成
        while self.status == SyncStatus.SYNCING:
            time.sleep(0.1)
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        self.logger.info("ConfigSync stopped")