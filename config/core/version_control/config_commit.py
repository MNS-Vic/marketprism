"""
配置提交系统

Git风格的配置变更提交和版本记录。
"""

import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json


class ChangeType(Enum):
    """配置变更类型"""
    ADDED = "added"        # 新增配置
    MODIFIED = "modified"  # 修改配置
    DELETED = "deleted"    # 删除配置
    RENAMED = "renamed"    # 重命名配置


@dataclass
class ConfigChange:
    """配置变更记录"""
    key: str
    change_type: ChangeType
    old_value: Any = None
    new_value: Any = None
    old_key: Optional[str] = None  # 用于重命名操作
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.change_type == ChangeType.ADDED and self.old_value is not None:
            raise ValueError("ADDED change should not have old_value")
        if self.change_type == ChangeType.DELETED and self.new_value is not None:
            raise ValueError("DELETED change should not have new_value")
        if self.change_type == ChangeType.RENAMED and self.old_key is None:
            raise ValueError("RENAMED change must have old_key")


@dataclass
class ConfigDiff:
    """配置差异分析结果"""
    added: Dict[str, Any] = field(default_factory=dict)
    modified: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # key -> {old, new}
    deleted: Dict[str, Any] = field(default_factory=dict)
    renamed: Dict[str, str] = field(default_factory=dict)  # old_key -> new_key
    
    @property
    def has_changes(self) -> bool:
        """是否有变更"""
        return bool(self.added or self.modified or self.deleted or self.renamed)
    
    @property
    def change_count(self) -> int:
        """变更总数"""
        return len(self.added) + len(self.modified) + len(self.deleted) + len(self.renamed)
    
    def to_changes(self) -> List[ConfigChange]:
        """转换为ConfigChange列表"""
        changes = []
        
        # 新增的配置
        for key, value in self.added.items():
            changes.append(ConfigChange(
                key=key,
                change_type=ChangeType.ADDED,
                new_value=value
            ))
        
        # 修改的配置
        for key, values in self.modified.items():
            changes.append(ConfigChange(
                key=key,
                change_type=ChangeType.MODIFIED,
                old_value=values['old'],
                new_value=values['new']
            ))
        
        # 删除的配置
        for key, value in self.deleted.items():
            changes.append(ConfigChange(
                key=key,
                change_type=ChangeType.DELETED,
                old_value=value
            ))
        
        # 重命名的配置
        for old_key, new_key in self.renamed.items():
            changes.append(ConfigChange(
                key=new_key,
                change_type=ChangeType.RENAMED,
                old_key=old_key
            ))
        
        return changes


class ConfigCommit:
    """配置提交系统
    
    Git风格的配置变更提交，记录每次配置变更的完整信息。
    """
    
    def __init__(self, commit_id: Optional[str] = None, message: str = "",
                 author: str = "system", timestamp: Optional[datetime] = None,
                 parent_commits: Optional[List[str]] = None):
        self.commit_id = commit_id or self._generate_commit_id()
        self.message = message
        self.author = author
        self.timestamp = timestamp or datetime.utcnow()
        self.parent_commits = parent_commits or []
        self.changes: List[ConfigChange] = []
        self.metadata: Dict[str, Any] = {}
        
        # 配置快照 (提交时的完整配置状态)
        self.config_snapshot: Dict[str, Any] = {}
        
        # 提交验证状态
        self.is_validated = False
        self.validation_errors: List[str] = []
    
    def _generate_commit_id(self) -> str:
        """生成唯一的提交ID"""
        return str(uuid.uuid4())
    
    def add_change(self, change: ConfigChange) -> None:
        """添加配置变更"""
        if self.is_validated:
            raise ValueError("Cannot add changes to a validated commit")
        
        # 检查是否已存在相同键的变更
        existing_change = self._find_change_by_key(change.key)
        if existing_change:
            # 合并变更
            self._merge_changes(existing_change, change)
        else:
            self.changes.append(change)
    
    def add_changes(self, changes: List[ConfigChange]) -> None:
        """批量添加配置变更"""
        for change in changes:
            self.add_change(change)
    
    def _find_change_by_key(self, key: str) -> Optional[ConfigChange]:
        """根据键查找变更"""
        for change in self.changes:
            if change.key == key:
                return change
        return None
    
    def _merge_changes(self, existing: ConfigChange, new: ConfigChange) -> None:
        """合并相同键的变更"""
        if existing.change_type == ChangeType.ADDED and new.change_type == ChangeType.MODIFIED:
            # 新增后修改 = 新增最终值
            existing.new_value = new.new_value
        elif existing.change_type == ChangeType.ADDED and new.change_type == ChangeType.DELETED:
            # 新增后删除 = 无变更
            self.changes.remove(existing)
        elif existing.change_type == ChangeType.MODIFIED and new.change_type == ChangeType.MODIFIED:
            # 多次修改 = 保留原始值，更新最终值
            existing.new_value = new.new_value
        elif existing.change_type == ChangeType.MODIFIED and new.change_type == ChangeType.DELETED:
            # 修改后删除 = 删除原始值
            existing.change_type = ChangeType.DELETED
            existing.new_value = None
        else:
            # 其他情况直接替换
            existing.change_type = new.change_type
            existing.old_value = new.old_value
            existing.new_value = new.new_value
            existing.old_key = new.old_key
    
    def set_config_snapshot(self, config: Dict[str, Any]) -> None:
        """设置配置快照"""
        self.config_snapshot = config.copy()
    
    def validate(self) -> bool:
        """验证提交的有效性"""
        self.validation_errors.clear()
        
        # 检查提交信息
        if not self.message.strip():
            self.validation_errors.append("Commit message cannot be empty")
        
        # 检查作者信息
        if not self.author.strip():
            self.validation_errors.append("Author cannot be empty")
        
        # 检查是否有变更
        if not self.changes:
            self.validation_errors.append("Commit must have at least one change")
        
        # 验证变更的一致性
        for change in self.changes:
            if change.change_type == ChangeType.ADDED and change.old_value is not None:
                self.validation_errors.append(f"Added change for {change.key} should not have old_value")
            elif change.change_type == ChangeType.DELETED and change.new_value is not None:
                self.validation_errors.append(f"Deleted change for {change.key} should not have new_value")
            elif change.change_type == ChangeType.RENAMED and change.old_key is None:
                self.validation_errors.append(f"Renamed change for {change.key} must have old_key")
        
        self.is_validated = len(self.validation_errors) == 0
        return self.is_validated
    
    def get_commit_info(self) -> Dict[str, Any]:
        """获取提交信息"""
        return {
            "commit_id": self.commit_id,
            "message": self.message,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "parent_commits": self.parent_commits,
            "change_count": len(self.changes),
            "is_validated": self.is_validated,
            "validation_errors": self.validation_errors,
            "metadata": self.metadata
        }
    
    def get_changes(self) -> List[ConfigChange]:
        """获取所有变更"""
        return self.changes.copy()
    
    def get_changes_by_type(self, change_type: ChangeType) -> List[ConfigChange]:
        """根据类型获取变更"""
        return [change for change in self.changes if change.change_type == change_type]
    
    def get_affected_keys(self) -> List[str]:
        """获取受影响的配置键"""
        keys = set()
        for change in self.changes:
            keys.add(change.key)
            if change.old_key:  # 重命名的情况
                keys.add(change.old_key)
        return sorted(list(keys))
    
    def calculate_checksum(self) -> str:
        """计算提交的校验和"""
        # 创建用于校验和的数据
        checksum_data = {
            "commit_id": self.commit_id,
            "message": self.message,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "parent_commits": sorted(self.parent_commits),
            "changes": [
                {
                    "key": change.key,
                    "type": change.change_type.value,
                    "old_value": change.old_value,
                    "new_value": change.new_value,
                    "old_key": change.old_key
                }
                for change in sorted(self.changes, key=lambda c: c.key)
            ]
        }
        
        # 计算SHA-256校验和
        data_str = json.dumps(checksum_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()
    
    def create_diff(self, base_config: Dict[str, Any]) -> ConfigDiff:
        """基于变更创建差异分析"""
        diff = ConfigDiff()
        
        for change in self.changes:
            if change.change_type == ChangeType.ADDED:
                diff.added[change.key] = change.new_value
            elif change.change_type == ChangeType.MODIFIED:
                diff.modified[change.key] = {
                    "old": change.old_value,
                    "new": change.new_value
                }
            elif change.change_type == ChangeType.DELETED:
                diff.deleted[change.key] = change.old_value
            elif change.change_type == ChangeType.RENAMED:
                diff.renamed[change.old_key] = change.key
        
        return diff
    
    def apply_to_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """将提交的变更应用到配置"""
        result = config.copy()
        
        for change in self.changes:
            if change.change_type == ChangeType.ADDED:
                self._set_nested_value(result, change.key, change.new_value)
            elif change.change_type == ChangeType.MODIFIED:
                self._set_nested_value(result, change.key, change.new_value)
            elif change.change_type == ChangeType.DELETED:
                self._delete_nested_value(result, change.key)
            elif change.change_type == ChangeType.RENAMED:
                # 重命名：先获取旧值，删除旧键，设置新键
                old_value = self._get_nested_value(result, change.old_key)
                if old_value is not None:
                    self._delete_nested_value(result, change.old_key)
                    self._set_nested_value(result, change.key, old_value)
        
        return result
    
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
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "commit_id": self.commit_id,
            "message": self.message,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "parent_commits": self.parent_commits,
            "changes": [
                {
                    "key": change.key,
                    "change_type": change.change_type.value,
                    "old_value": change.old_value,
                    "new_value": change.new_value,
                    "old_key": change.old_key,
                    "metadata": change.metadata
                }
                for change in self.changes
            ],
            "config_snapshot": self.config_snapshot,
            "metadata": self.metadata,
            "is_validated": self.is_validated,
            "validation_errors": self.validation_errors,
            "checksum": self.calculate_checksum()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigCommit':
        """从字典创建提交对象"""
        commit = cls(
            commit_id=data.get("commit_id"),
            message=data.get("message", ""),
            author=data.get("author", "system"),
            timestamp=datetime.fromisoformat(data.get("timestamp")),
            parent_commits=data.get("parent_commits", [])
        )
        
        # 恢复变更
        for change_data in data.get("changes", []):
            change = ConfigChange(
                key=change_data["key"],
                change_type=ChangeType(change_data["change_type"]),
                old_value=change_data.get("old_value"),
                new_value=change_data.get("new_value"),
                old_key=change_data.get("old_key"),
                metadata=change_data.get("metadata", {})
            )
            commit.changes.append(change)
        
        # 恢复其他属性
        commit.config_snapshot = data.get("config_snapshot", {})
        commit.metadata = data.get("metadata", {})
        commit.is_validated = data.get("is_validated", False)
        commit.validation_errors = data.get("validation_errors", [])
        
        return commit
    
    def __str__(self) -> str:
        return f"ConfigCommit({self.commit_id[:8]}: {self.message})"
    
    def __repr__(self) -> str:
        return (f"ConfigCommit(commit_id='{self.commit_id}', "
                f"message='{self.message}', author='{self.author}', "
                f"changes={len(self.changes)})")


# 工具函数
def create_diff_between_configs(old_config: Dict[str, Any], 
                               new_config: Dict[str, Any]) -> ConfigDiff:
    """创建两个配置之间的差异分析"""
    diff = ConfigDiff()
    
    # 获取所有键
    old_keys = set(_get_all_keys(old_config))
    new_keys = set(_get_all_keys(new_config))
    
    # 新增的键
    added_keys = new_keys - old_keys
    for key in added_keys:
        diff.added[key] = _get_nested_value(new_config, key)
    
    # 删除的键
    deleted_keys = old_keys - new_keys
    for key in deleted_keys:
        diff.deleted[key] = _get_nested_value(old_config, key)
    
    # 修改的键
    common_keys = old_keys & new_keys
    for key in common_keys:
        old_value = _get_nested_value(old_config, key)
        new_value = _get_nested_value(new_config, key)
        
        if old_value != new_value:
            diff.modified[key] = {"old": old_value, "new": new_value}
    
    return diff


def _get_all_keys(config: Dict[str, Any], prefix: str = "") -> List[str]:
    """获取配置中的所有键"""
    keys = []
    
    for key, value in config.items():
        full_key = f"{prefix}.{key}" if prefix else key
        keys.append(full_key)
        
        if isinstance(value, dict):
            keys.extend(_get_all_keys(value, full_key))
    
    return keys


def _get_nested_value(config: Dict[str, Any], key: str) -> Any:
    """获取嵌套值"""
    keys = key.split('.')
    current = config
    
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    
    return current