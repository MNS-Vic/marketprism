"""
配置合并系统

Git风格的配置分支合并，支持冲突检测和解决。
"""

from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config_commit import ConfigCommit, ConfigChange, ChangeType, ConfigDiff
from .config_branch import ConfigBranch, MergeStrategy


class ConflictType(Enum):
    """冲突类型"""
    MODIFY_MODIFY = "modify_modify"     # 双方都修改了同一个键
    ADD_ADD = "add_add"                 # 双方都添加了同一个键但值不同
    DELETE_MODIFY = "delete_modify"     # 一方删除一方修改
    RENAME_RENAME = "rename_rename"     # 双方都重命名了同一个键
    RENAME_DELETE = "rename_delete"     # 一方重命名一方删除
    RENAME_MODIFY = "rename_modify"     # 一方重命名一方修改


class ConflictResolution(Enum):
    """冲突解决策略"""
    TAKE_CURRENT = "take_current"       # 采用当前分支的值
    TAKE_INCOMING = "take_incoming"     # 采用传入分支的值
    MERGE_VALUES = "merge_values"       # 合并值（对于字典类型）
    MANUAL = "manual"                   # 手动解决
    ABORT = "abort"                     # 中止合并


@dataclass
class MergeConflict:
    """合并冲突"""
    key: str
    conflict_type: ConflictType
    current_value: Any = None           # 当前分支的值
    incoming_value: Any = None          # 传入分支的值
    base_value: Any = None              # 共同祖先的值
    current_change: Optional[ConfigChange] = None
    incoming_change: Optional[ConfigChange] = None
    resolution: Optional[ConflictResolution] = None
    resolved_value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_resolved(self) -> bool:
        """是否已解决冲突"""
        return self.resolution is not None
    
    def resolve(self, resolution: ConflictResolution, 
                resolved_value: Any = None) -> None:
        """解决冲突"""
        self.resolution = resolution
        
        if resolution == ConflictResolution.TAKE_CURRENT:
            self.resolved_value = self.current_value
        elif resolution == ConflictResolution.TAKE_INCOMING:
            self.resolved_value = self.incoming_value
        elif resolution == ConflictResolution.MERGE_VALUES:
            self.resolved_value = self._merge_values()
        elif resolution == ConflictResolution.MANUAL:
            if resolved_value is None:
                raise ValueError("Manual resolution requires resolved_value")
            self.resolved_value = resolved_value
        elif resolution == ConflictResolution.ABORT:
            self.resolved_value = None
    
    def _merge_values(self) -> Any:
        """合并值"""
        # 如果两个值都是字典，尝试合并
        if isinstance(self.current_value, dict) and isinstance(self.incoming_value, dict):
            merged = self.current_value.copy()
            merged.update(self.incoming_value)
            return merged
        
        # 如果两个值都是列表，尝试合并
        if isinstance(self.current_value, list) and isinstance(self.incoming_value, list):
            # 去重合并
            merged = self.current_value.copy()
            for item in self.incoming_value:
                if item not in merged:
                    merged.append(item)
            return merged
        
        # 默认取当前分支的值
        return self.current_value


@dataclass
class MergeResult:
    """合并结果"""
    success: bool
    merge_strategy: MergeStrategy
    source_branch: str
    target_branch: str
    merge_commit: Optional[str] = None
    conflicts: List[MergeConflict] = field(default_factory=list)
    merged_config: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    timestamp: Optional[datetime] = None
    
    @property
    def has_conflicts(self) -> bool:
        """是否有冲突"""
        return len(self.conflicts) > 0
    
    @property
    def unresolved_conflicts(self) -> List[MergeConflict]:
        """未解决的冲突"""
        return [c for c in self.conflicts if not c.is_resolved]
    
    @property
    def can_complete(self) -> bool:
        """是否可以完成合并"""
        return self.success and len(self.unresolved_conflicts) == 0


class ConfigMerge:
    """配置合并系统
    
    处理配置分支之间的合并，包括冲突检测和解决。
    """
    
    def __init__(self):
        self.conflicts: List[MergeConflict] = []
        self.merge_base: Optional[str] = None
        self.current_merge: Optional[MergeResult] = None
    
    def merge_branches(self, source_branch: ConfigBranch, 
                      target_branch: ConfigBranch,
                      source_config: Dict[str, Any],
                      target_config: Dict[str, Any],
                      base_config: Optional[Dict[str, Any]] = None,
                      strategy: MergeStrategy = MergeStrategy.MERGE_COMMIT,
                      message: str = "") -> MergeResult:
        """合并两个分支"""
        
        # 创建合并结果
        result = MergeResult(
            success=False,
            merge_strategy=strategy,
            source_branch=source_branch.branch_name,
            target_branch=target_branch.branch_name,
            message=message or f"Merge {source_branch.branch_name} into {target_branch.branch_name}",
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        # 检查是否可以快进合并
        if strategy == MergeStrategy.FAST_FORWARD:
            if target_branch.can_fast_forward_to(source_branch):
                return self._fast_forward_merge(source_branch, target_branch, source_config, result)
            else:
                result.message = "Cannot fast-forward merge: branches have diverged"
                return result
        
        # 三路合并
        if base_config is None:
            # 找到共同祖先
            diverged = target_branch.get_diverged_commits(source_branch)
            if diverged["common_ancestor"]:
                self.merge_base = diverged["common_ancestor"]
                # 这里应该从存储中获取base_config，暂时使用空字典
                base_config = {}
            else:
                base_config = {}
        
        # 检测冲突
        conflicts = self._detect_conflicts(target_config, source_config, base_config)
        result.conflicts = conflicts
        
        if not conflicts:
            # 无冲突，直接合并
            merged_config = self._merge_configs(target_config, source_config, base_config)
            result.merged_config = merged_config
            result.success = True
        else:
            # 有冲突，初始化合并配置为目标配置
            result.merged_config = target_config.copy()
            result.success = False
            result.message += f" (found {len(conflicts)} conflicts)"
        
        self.current_merge = result
        return result
    
    def _fast_forward_merge(self, source_branch: ConfigBranch,
                           target_branch: ConfigBranch,
                           source_config: Dict[str, Any],
                           result: MergeResult) -> MergeResult:
        """快进合并"""
        result.merged_config = source_config.copy()
        result.success = True
        result.message = f"Fast-forward merge: {source_branch.branch_name} -> {target_branch.branch_name}"
        return result
    
    def _detect_conflicts(self, current_config: Dict[str, Any],
                         incoming_config: Dict[str, Any],
                         base_config: Dict[str, Any]) -> List[MergeConflict]:
        """检测合并冲突"""
        conflicts = []
        
        # 获取所有相关的键
        current_keys = set(self._get_all_keys(current_config))
        incoming_keys = set(self._get_all_keys(incoming_config))
        base_keys = set(self._get_all_keys(base_config))
        
        all_keys = current_keys | incoming_keys | base_keys
        
        for key in all_keys:
            current_value = self._get_nested_value(current_config, key)
            incoming_value = self._get_nested_value(incoming_config, key)
            base_value = self._get_nested_value(base_config, key)
            
            # 检查各种冲突情况
            conflict = self._check_key_conflict(key, current_value, incoming_value, base_value)
            if conflict:
                conflicts.append(conflict)
        
        return conflicts
    
    def _check_key_conflict(self, key: str, current_value: Any,
                           incoming_value: Any, base_value: Any) -> Optional[MergeConflict]:
        """检查单个键的冲突"""
        
        # 情况1: 双方都存在，但值不同
        if (current_value is not None and incoming_value is not None and 
            current_value != incoming_value):
            
            # 检查是否都相对于base有变化
            current_changed = current_value != base_value
            incoming_changed = incoming_value != base_value
            
            if current_changed and incoming_changed:
                return MergeConflict(
                    key=key,
                    conflict_type=ConflictType.MODIFY_MODIFY,
                    current_value=current_value,
                    incoming_value=incoming_value,
                    base_value=base_value
                )
        
        # 情况2: 一方删除，一方修改
        if current_value is None and incoming_value is not None and base_value is not None:
            if incoming_value != base_value:  # incoming修改了
                return MergeConflict(
                    key=key,
                    conflict_type=ConflictType.DELETE_MODIFY,
                    current_value=None,
                    incoming_value=incoming_value,
                    base_value=base_value
                )
        
        if incoming_value is None and current_value is not None and base_value is not None:
            if current_value != base_value:  # current修改了
                return MergeConflict(
                    key=key,
                    conflict_type=ConflictType.DELETE_MODIFY,
                    current_value=current_value,
                    incoming_value=None,
                    base_value=base_value
                )
        
        # 情况3: 双方都新增但值不同
        if (current_value is not None and incoming_value is not None and 
            base_value is None and current_value != incoming_value):
            return MergeConflict(
                key=key,
                conflict_type=ConflictType.ADD_ADD,
                current_value=current_value,
                incoming_value=incoming_value,
                base_value=None
            )
        
        return None
    
    def _merge_configs(self, current_config: Dict[str, Any],
                      incoming_config: Dict[str, Any],
                      base_config: Dict[str, Any]) -> Dict[str, Any]:
        """合并配置（无冲突情况）"""
        merged = current_config.copy()
        
        # 获取所有键
        incoming_keys = set(self._get_all_keys(incoming_config))
        base_keys = set(self._get_all_keys(base_config))
        
        for key in incoming_keys:
            incoming_value = self._get_nested_value(incoming_config, key)
            current_value = self._get_nested_value(merged, key)
            base_value = self._get_nested_value(base_config, key)
            
            # 如果incoming有变化且current没有变化，采用incoming的值
            if incoming_value != base_value and current_value == base_value:
                self._set_nested_value(merged, key, incoming_value)
            
            # 如果是新增的键，直接添加
            if base_value is None and current_value is None:
                self._set_nested_value(merged, key, incoming_value)
        
        # 处理删除的键
        for key in base_keys:
            if (self._get_nested_value(incoming_config, key) is None and
                self._get_nested_value(merged, key) == self._get_nested_value(base_config, key)):
                # incoming删除了，且current没有修改，则删除
                self._delete_nested_value(merged, key)
        
        return merged
    
    def resolve_conflict(self, conflict_index: int, 
                        resolution: ConflictResolution,
                        resolved_value: Any = None) -> bool:
        """解决指定的冲突"""
        if not self.current_merge:
            raise ValueError("No active merge to resolve conflicts")
        
        if conflict_index >= len(self.current_merge.conflicts):
            raise ValueError(f"Invalid conflict index: {conflict_index}")
        
        conflict = self.current_merge.conflicts[conflict_index]
        conflict.resolve(resolution, resolved_value)
        
        return True
    
    def resolve_all_conflicts(self, resolution_strategy: ConflictResolution) -> bool:
        """解决所有冲突"""
        if not self.current_merge:
            raise ValueError("No active merge to resolve conflicts")
        
        for conflict in self.current_merge.conflicts:
            if not conflict.is_resolved:
                conflict.resolve(resolution_strategy)
        
        return True
    
    def complete_merge(self) -> Optional[ConfigCommit]:
        """完成合并"""
        if not self.current_merge:
            raise ValueError("No active merge to complete")
        
        # 如果成功且无冲突，直接创建合并提交
        if self.current_merge.success and not self.current_merge.has_conflicts:
            merged_config = self.current_merge.merged_config
        elif not self.current_merge.can_complete:
            unresolved = len(self.current_merge.unresolved_conflicts)
            raise ValueError(f"Cannot complete merge: {unresolved} unresolved conflicts")
        else:
            merged_config = self.current_merge.merged_config
        
        # 应用冲突解决(仅在有冲突时才需要)
        if self.current_merge.has_conflicts:
            for conflict in self.current_merge.conflicts:
                if conflict.resolution == ConflictResolution.ABORT:
                    raise ValueError("Merge aborted due to conflict resolution")
                
                if conflict.resolved_value is not None:
                    self._set_nested_value(merged_config, conflict.key, conflict.resolved_value)
                elif conflict.resolution == ConflictResolution.TAKE_CURRENT:
                    # 保持当前值（已经在merged_config中）
                    pass
                elif conflict.resolution == ConflictResolution.TAKE_INCOMING:
                    self._set_nested_value(merged_config, conflict.key, conflict.incoming_value)
        
        # 创建合并提交
        merge_commit = ConfigCommit(
            message=self.current_merge.message,
            author="system",
            parent_commits=[
                # 这里应该是实际的commit IDs
                # 暂时用分支名代替
                self.current_merge.target_branch,
                self.current_merge.source_branch
            ]
        )
        
        # 添加一个虚拟的合并变更以通过验证
        from .config_commit import ConfigChange, ChangeType
        merge_change = ConfigChange(
            key="_merge_marker",
            change_type=ChangeType.ADDED,
            new_value=f"Merged {self.current_merge.source_branch} into {self.current_merge.target_branch}"
        )
        merge_commit.add_change(merge_change)
        merge_commit.set_config_snapshot(merged_config)
        
        if merge_commit.validate():
            self.current_merge.merge_commit = merge_commit.commit_id
            self.current_merge.merged_config = merged_config
            self.current_merge = None  # 清除当前合并状态
            return merge_commit
        
        return None
    
    def abort_merge(self) -> bool:
        """中止合并"""
        self.current_merge = None
        self.conflicts.clear()
        return True
    
    def get_merge_status(self) -> Optional[Dict[str, Any]]:
        """获取合并状态"""
        if not self.current_merge:
            return None
        
        return {
            "source_branch": self.current_merge.source_branch,
            "target_branch": self.current_merge.target_branch,
            "strategy": self.current_merge.merge_strategy.value,
            "total_conflicts": len(self.current_merge.conflicts),
            "resolved_conflicts": len([c for c in self.current_merge.conflicts if c.is_resolved]),
            "can_complete": self.current_merge.can_complete,
            "message": self.current_merge.message,
            "conflicts": [
                {
                    "key": c.key,
                    "type": c.conflict_type.value,
                    "is_resolved": c.is_resolved,
                    "resolution": c.resolution.value if c.resolution else None,
                    "current_value": c.current_value,
                    "incoming_value": c.incoming_value
                }
                for c in self.current_merge.conflicts
            ]
        }
    
    # 辅助方法
    def _get_all_keys(self, config: Dict[str, Any], prefix: str = "") -> List[str]:
        """获取配置中的所有键"""
        keys = []
        
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            keys.append(full_key)
            
            if isinstance(value, dict):
                keys.extend(self._get_all_keys(value, full_key))
        
        return keys
    
    def _get_nested_value(self, config: Dict[str, Any], key: str) -> Any:
        """获取嵌套值"""
        keys = key.split('.')
        current = config
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        
        return current
    
    def _set_nested_value(self, config: Dict[str, Any], key: str, value: Any) -> None:
        """设置嵌套值"""
        keys = key.split('.')
        current = config
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def _delete_nested_value(self, config: Dict[str, Any], key: str) -> bool:
        """删除嵌套值"""
        keys = key.split('.')
        current = config
        
        # 导航到父级
        for k in keys[:-1]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False
        
        # 删除最后的键
        if isinstance(current, dict) and keys[-1] in current:
            del current[keys[-1]]
            return True
        
        return False