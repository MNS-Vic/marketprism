"""
配置分支管理系统

Git风格的配置分支管理，支持分支创建、切换、合并等操作。
"""

from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re

from .config_commit import ConfigCommit, ConfigDiff, create_diff_between_configs


class BranchProtectionLevel(Enum):
    """分支保护级别"""
    NONE = "none"           # 无保护
    BASIC = "basic"         # 基础保护
    STRICT = "strict"       # 严格保护
    LOCKED = "locked"       # 锁定分支


class MergeStrategy(Enum):
    """合并策略"""
    FAST_FORWARD = "fast_forward"       # 快进合并
    MERGE_COMMIT = "merge_commit"       # 合并提交
    SQUASH = "squash"                   # 压缩合并
    REBASE = "rebase"                   # 变基合并


@dataclass
class BranchProtection:
    """分支保护规则"""
    level: BranchProtectionLevel = BranchProtectionLevel.NONE
    require_review: bool = False
    require_status_checks: bool = False
    restrict_pushes: bool = False
    allowed_users: Set[str] = field(default_factory=set)
    required_reviewers: int = 0
    dismiss_stale_reviews: bool = False
    
    def can_push(self, user: str) -> bool:
        """检查用户是否可以推送"""
        if self.level == BranchProtectionLevel.LOCKED:
            return False
        if self.level == BranchProtectionLevel.STRICT or self.restrict_pushes:
            return user in self.allowed_users
        if self.level == BranchProtectionLevel.BASIC:
            # 基础保护需要验证用户权限
            return len(self.allowed_users) == 0 or user in self.allowed_users
        return True
    
    def can_merge(self, user: str, review_count: int = 0) -> bool:
        """检查用户是否可以合并"""
        if self.level == BranchProtectionLevel.LOCKED:
            return False
        if self.require_review and review_count < self.required_reviewers:
            return False
        if self.restrict_pushes:
            return user in self.allowed_users
        return True


class ConfigBranch:
    """配置分支管理
    
    Git风格的配置分支，支持分支创建、切换、合并等操作。
    """
    
    def __init__(self, branch_name: str, base_commit: Optional[str] = None,
                 protection: Optional[BranchProtection] = None):
        self.branch_name = self._validate_branch_name(branch_name)
        self.base_commit = base_commit
        self.current_commit = base_commit
        self.commits: List[str] = []
        if base_commit:
            self.commits.append(base_commit)
        
        self.protection = protection or BranchProtection()
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.created_by = "system"
        self.metadata: Dict[str, Any] = {}
        
        # 分支状态
        self.is_active = True
        self.is_merged = False
        self.merged_into: Optional[str] = None
        self.merge_commit: Optional[str] = None
    
    def _validate_branch_name(self, name: str) -> str:
        """验证分支名称"""
        # Git分支命名规则
        if not name:
            raise ValueError("Branch name cannot be empty")
        
        # 不能以 / 开头或结尾
        if name.startswith('/') or name.endswith('/'):
            raise ValueError("Branch name cannot start or end with '/'")
        
        # 不能包含连续的 //
        if '//' in name:
            raise ValueError("Branch name cannot contain '//'")
        
        # 不能包含特殊字符
        invalid_chars = ['~', '^', ':', '?', '*', '[', '\\', ' ', '\t', '\n']
        for char in invalid_chars:
            if char in name:
                raise ValueError(f"Branch name cannot contain '{char}'")
        
        # 不能是特殊保留名
        reserved_names = ['HEAD', 'FETCH_HEAD', 'ORIG_HEAD', 'MERGE_HEAD']
        if name.upper() in reserved_names:
            raise ValueError(f"Branch name '{name}' is reserved")
        
        return name
    
    def add_commit(self, commit_id: str) -> None:
        """添加提交到分支"""
        if not self.is_active:
            raise ValueError(f"Cannot add commit to inactive branch '{self.branch_name}'")
        
        if commit_id not in self.commits:
            self.commits.append(commit_id)
            self.current_commit = commit_id
            self.updated_at = datetime.utcnow()
    
    def get_commit_history(self, limit: Optional[int] = None) -> List[str]:
        """获取提交历史"""
        commits = self.commits.copy()
        if limit:
            commits = commits[-limit:]
        return list(reversed(commits))  # 最新的在前
    
    def get_commits_since(self, commit_id: str) -> List[str]:
        """获取某个提交之后的所有提交"""
        try:
            index = self.commits.index(commit_id)
            return self.commits[index + 1:]
        except ValueError:
            return []
    
    def get_commits_between(self, start_commit: str, end_commit: str) -> List[str]:
        """获取两个提交之间的提交"""
        try:
            start_index = self.commits.index(start_commit)
            end_index = self.commits.index(end_commit)
            
            if start_index > end_index:
                start_index, end_index = end_index, start_index
            
            return self.commits[start_index:end_index + 1]
        except ValueError:
            return []
    
    def has_commit(self, commit_id: str) -> bool:
        """检查分支是否包含指定提交"""
        return commit_id in self.commits
    
    def is_ahead_of(self, other_branch: 'ConfigBranch') -> bool:
        """检查当前分支是否领先于另一个分支"""
        if not other_branch.current_commit:
            return len(self.commits) > 0
        
        # 检查另一个分支的最新提交是否在当前分支中
        return (other_branch.current_commit in self.commits and 
                self.commits.index(other_branch.current_commit) < len(self.commits) - 1)
    
    def is_behind(self, other_branch: 'ConfigBranch') -> bool:
        """检查当前分支是否落后于另一个分支"""
        return other_branch.is_ahead_of(self)
    
    def can_fast_forward_to(self, other_branch: 'ConfigBranch') -> bool:
        """检查是否可以快进合并到另一个分支"""
        if not self.current_commit or not other_branch.current_commit:
            return False
        
        # 如果当前分支的最新提交在目标分支中，且目标分支有更新的提交
        return (self.current_commit in other_branch.commits and
                other_branch.commits.index(self.current_commit) < len(other_branch.commits) - 1)
    
    def get_diverged_commits(self, other_branch: 'ConfigBranch') -> Dict[str, List[str]]:
        """获取与另一个分支的分歧提交"""
        # 找到共同的祖先提交
        common_commits = set(self.commits) & set(other_branch.commits)
        if not common_commits:
            # 没有共同提交
            return {
                "current": self.commits.copy(),
                "other": other_branch.commits.copy(),
                "common_ancestor": None
            }
        
        # 找到最新的共同祖先
        common_ancestor = None
        for commit in reversed(self.commits):
            if commit in common_commits:
                common_ancestor = commit
                break
        
        # 获取分歧的提交
        current_diverged = self.get_commits_since(common_ancestor) if common_ancestor else self.commits
        other_diverged = other_branch.get_commits_since(common_ancestor) if common_ancestor else other_branch.commits
        
        return {
            "current": current_diverged,
            "other": other_diverged,
            "common_ancestor": common_ancestor
        }
    
    def set_protection(self, protection: BranchProtection) -> None:
        """设置分支保护规则"""
        self.protection = protection
        self.updated_at = datetime.utcnow()
    
    def can_push(self, user: str) -> bool:
        """检查用户是否可以推送到分支"""
        return self.protection.can_push(user) and self.is_active
    
    def can_merge(self, user: str, review_count: int = 0) -> bool:
        """检查用户是否可以合并分支"""
        return self.protection.can_merge(user, review_count) and self.is_active
    
    def mark_as_merged(self, target_branch: str, merge_commit: str) -> None:
        """标记分支为已合并"""
        self.is_merged = True
        self.merged_into = target_branch
        self.merge_commit = merge_commit
        self.updated_at = datetime.utcnow()
    
    def delete(self, force: bool = False) -> bool:
        """删除分支"""
        if not force and not self.is_merged:
            raise ValueError(f"Branch '{self.branch_name}' is not merged and force=False")
        
        if self.protection.level == BranchProtectionLevel.LOCKED:
            raise ValueError(f"Branch '{self.branch_name}' is locked and cannot be deleted")
        
        self.is_active = False
        self.updated_at = datetime.utcnow()
        return True
    
    def get_branch_info(self) -> Dict[str, Any]:
        """获取分支信息"""
        return {
            "branch_name": self.branch_name,
            "base_commit": self.base_commit,
            "current_commit": self.current_commit,
            "commit_count": len(self.commits),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "is_active": self.is_active,
            "is_merged": self.is_merged,
            "merged_into": self.merged_into,
            "merge_commit": self.merge_commit,
            "protection_level": self.protection.level.value,
            "metadata": self.metadata
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "branch_name": self.branch_name,
            "base_commit": self.base_commit,
            "current_commit": self.current_commit,
            "commits": self.commits.copy(),
            "protection": {
                "level": self.protection.level.value,
                "require_review": self.protection.require_review,
                "require_status_checks": self.protection.require_status_checks,
                "restrict_pushes": self.protection.restrict_pushes,
                "allowed_users": list(self.protection.allowed_users),
                "required_reviewers": self.protection.required_reviewers,
                "dismiss_stale_reviews": self.protection.dismiss_stale_reviews
            },
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "is_active": self.is_active,
            "is_merged": self.is_merged,
            "merged_into": self.merged_into,
            "merge_commit": self.merge_commit,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigBranch':
        """从字典创建分支对象"""
        # 创建保护规则
        protection_data = data.get("protection", {})
        protection = BranchProtection(
            level=BranchProtectionLevel(protection_data.get("level", "none")),
            require_review=protection_data.get("require_review", False),
            require_status_checks=protection_data.get("require_status_checks", False),
            restrict_pushes=protection_data.get("restrict_pushes", False),
            allowed_users=set(protection_data.get("allowed_users", [])),
            required_reviewers=protection_data.get("required_reviewers", 0),
            dismiss_stale_reviews=protection_data.get("dismiss_stale_reviews", False)
        )
        
        # 创建分支对象
        branch = cls(
            branch_name=data["branch_name"],
            base_commit=data.get("base_commit"),
            protection=protection
        )
        
        # 恢复属性
        branch.current_commit = data.get("current_commit")
        branch.commits = data.get("commits", [])
        branch.created_at = datetime.fromisoformat(data.get("created_at"))
        branch.updated_at = datetime.fromisoformat(data.get("updated_at"))
        branch.created_by = data.get("created_by", "system")
        branch.is_active = data.get("is_active", True)
        branch.is_merged = data.get("is_merged", False)
        branch.merged_into = data.get("merged_into")
        branch.merge_commit = data.get("merge_commit")
        branch.metadata = data.get("metadata", {})
        
        return branch
    
    def __str__(self) -> str:
        return f"ConfigBranch({self.branch_name})"
    
    def __repr__(self) -> str:
        return (f"ConfigBranch(name='{self.branch_name}', "
                f"commits={len(self.commits)}, active={self.is_active})")


class BranchManager:
    """分支管理器
    
    管理所有配置分支的创建、切换、合并等操作。
    """
    
    def __init__(self):
        self.branches: Dict[str, ConfigBranch] = {}
        self.current_branch: Optional[str] = None
        self.default_branch = "main"
        
        # 创建默认主分支
        self._create_default_branch()
    
    def _create_default_branch(self) -> None:
        """创建默认主分支"""
        main_protection = BranchProtection(
            level=BranchProtectionLevel.BASIC,
            require_review=True,
            required_reviewers=1
        )
        
        main_branch = ConfigBranch(
            branch_name=self.default_branch,
            protection=main_protection
        )
        
        self.branches[self.default_branch] = main_branch
        self.current_branch = self.default_branch
    
    def create_branch(self, branch_name: str, base_branch: Optional[str] = None,
                     protection: Optional[BranchProtection] = None) -> ConfigBranch:
        """创建新分支"""
        if branch_name in self.branches:
            raise ValueError(f"Branch '{branch_name}' already exists")
        
        # 确定基础分支
        if base_branch is None:
            base_branch = self.current_branch or self.default_branch
        
        if base_branch not in self.branches:
            raise ValueError(f"Base branch '{base_branch}' does not exist")
        
        base = self.branches[base_branch]
        
        # 创建新分支
        new_branch = ConfigBranch(
            branch_name=branch_name,
            base_commit=base.current_commit,
            protection=protection
        )
        
        # 复制基础分支的提交历史
        new_branch.commits = base.commits.copy()
        new_branch.current_commit = base.current_commit
        
        self.branches[branch_name] = new_branch
        return new_branch
    
    def checkout_branch(self, branch_name: str) -> bool:
        """切换分支"""
        if branch_name not in self.branches:
            raise ValueError(f"Branch '{branch_name}' does not exist")
        
        branch = self.branches[branch_name]
        if not branch.is_active:
            raise ValueError(f"Branch '{branch_name}' is not active")
        
        self.current_branch = branch_name
        return True
    
    def delete_branch(self, branch_name: str, force: bool = False) -> bool:
        """删除分支"""
        if branch_name not in self.branches:
            raise ValueError(f"Branch '{branch_name}' does not exist")
        
        if branch_name == self.default_branch:
            raise ValueError(f"Cannot delete default branch '{self.default_branch}'")
        
        if branch_name == self.current_branch:
            raise ValueError(f"Cannot delete current branch '{branch_name}'")
        
        branch = self.branches[branch_name]
        branch.delete(force=force)
        
        # 如果强制删除或已合并，从字典中移除
        if force or branch.is_merged:
            del self.branches[branch_name]
        
        return True
    
    def list_branches(self, active_only: bool = True) -> List[str]:
        """列出所有分支"""
        if active_only:
            return [name for name, branch in self.branches.items() if branch.is_active]
        else:
            return list(self.branches.keys())
    
    def get_branch(self, branch_name: str) -> Optional[ConfigBranch]:
        """获取分支对象"""
        return self.branches.get(branch_name)
    
    def get_current_branch(self) -> Optional[ConfigBranch]:
        """获取当前分支对象"""
        if self.current_branch:
            return self.branches.get(self.current_branch)
        return None
    
    def set_default_branch(self, branch_name: str) -> bool:
        """设置默认分支"""
        if branch_name not in self.branches:
            raise ValueError(f"Branch '{branch_name}' does not exist")
        
        self.default_branch = branch_name
        return True
    
    def get_branch_status(self) -> Dict[str, Any]:
        """获取分支状态"""
        current = self.get_current_branch()
        
        return {
            "current_branch": self.current_branch,
            "default_branch": self.default_branch,
            "total_branches": len(self.branches),
            "active_branches": len([b for b in self.branches.values() if b.is_active]),
            "current_commit": current.current_commit if current else None,
            "branches": [
                {
                    "name": name,
                    "is_current": name == self.current_branch,
                    "is_default": name == self.default_branch,
                    "is_active": branch.is_active,
                    "commit_count": len(branch.commits),
                    "protection_level": branch.protection.level.value
                }
                for name, branch in self.branches.items()
            ]
        }
    
    def __str__(self) -> str:
        return f"BranchManager(branches={len(self.branches)}, current={self.current_branch})"
    
    def __repr__(self) -> str:
        return (f"BranchManager(branches={list(self.branches.keys())}, "
                f"current='{self.current_branch}')")