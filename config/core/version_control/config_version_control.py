"""
配置版本控制主管理器

整合提交、分支、合并、历史、标签等所有版本控制功能。
"""

from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pathlib import Path
import json

from .config_commit import ConfigCommit, ConfigChange, ChangeType, ConfigDiff, create_diff_between_configs
from .config_branch import ConfigBranch, BranchManager, BranchProtection, MergeStrategy
from .config_merge import ConfigMerge, MergeResult, ConflictResolution
from .config_history import ConfigHistory, HistoryQuery
from .config_tag import ConfigTag, TagManager, TagType, VersionType, ReleaseNotes


class ConfigVersionControl:
    """配置版本控制主管理器
    
    Git风格的配置版本控制系统，提供完整的版本管理功能。
    """
    
    def __init__(self, repository_path: Optional[str] = None):
        self.repository_path = repository_path or ".config_vcs"
        
        # 初始化各个组件
        self.branch_manager = BranchManager()
        self.merge_manager = ConfigMerge()
        self.history = ConfigHistory()
        self.tag_manager = TagManager()
        
        # 当前状态
        self.current_config: Dict[str, Any] = {}
        self.working_changes: List[ConfigChange] = []
        self.staged_changes: List[ConfigChange] = []
        
        # 配置存储
        self.configs_storage: Dict[str, Dict[str, Any]] = {}  # commit_id -> config
        
        # 元数据
        self.repository_info = {
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "version": "1.0.0",
            "description": "MarketPrism Configuration Version Control"
        }
    
    # 基本配置操作
    def init_repository(self, initial_config: Optional[Dict[str, Any]] = None) -> bool:
        """初始化配置仓库"""
        if initial_config is None:
            initial_config = {}
        
        self.current_config = initial_config.copy()
        
        # 创建初始提交
        initial_commit = ConfigCommit(
            message="Initial commit",
            author="system"
        )
        
        # 添加初始配置作为新增变更
        for key, value in initial_config.items():
            change = ConfigChange(
                key=key,
                change_type=ChangeType.ADDED,
                new_value=value
            )
            initial_commit.add_change(change)
        
        initial_commit.set_config_snapshot(initial_config)
        
        if initial_commit.validate():
            # 添加到历史
            self.history.add_commit(initial_commit)
            self.configs_storage[initial_commit.commit_id] = initial_config.copy()
            
            # 更新主分支
            main_branch = self.branch_manager.get_branch("main")
            if main_branch:
                main_branch.add_commit(initial_commit.commit_id)
            
            return True
        
        return False
    
    def set_config_value(self, key: str, value: Any) -> None:
        """设置配置值（添加到工作区变更）"""
        old_value = self._get_nested_value(self.current_config, key)
        
        if old_value == value:
            return  # 没有变更
        
        # 确定变更类型
        if old_value is None:
            change_type = ChangeType.ADDED
        else:
            change_type = ChangeType.MODIFIED
        
        change = ConfigChange(
            key=key,
            change_type=change_type,
            old_value=old_value,
            new_value=value
        )
        
        # 检查是否已有相同键的变更
        self._update_working_change(change)
        
        # 更新当前配置
        self._set_nested_value(self.current_config, key, value)
    
    def delete_config_value(self, key: str) -> bool:
        """删除配置值"""
        old_value = self._get_nested_value(self.current_config, key)
        
        if old_value is None:
            return False  # 键不存在
        
        change = ConfigChange(
            key=key,
            change_type=ChangeType.DELETED,
            old_value=old_value
        )
        
        self._update_working_change(change)
        
        # 从当前配置中删除
        self._delete_nested_value(self.current_config, key)
        return True
    
    def rename_config_key(self, old_key: str, new_key: str) -> bool:
        """重命名配置键"""
        old_value = self._get_nested_value(self.current_config, old_key)
        
        if old_value is None:
            return False  # 旧键不存在
        
        if self._get_nested_value(self.current_config, new_key) is not None:
            raise ValueError(f"New key '{new_key}' already exists")
        
        change = ConfigChange(
            key=new_key,
            change_type=ChangeType.RENAMED,
            new_value=old_value,
            old_key=old_key
        )
        
        self._update_working_change(change)
        
        # 更新当前配置
        self._delete_nested_value(self.current_config, old_key)
        self._set_nested_value(self.current_config, new_key, old_value)
        
        return True
    
    # 暂存区操作
    def stage_changes(self, keys: Optional[List[str]] = None) -> int:
        """暂存变更"""
        if keys is None:
            # 暂存所有工作区变更
            self.staged_changes.extend(self.working_changes)
            count = len(self.working_changes)
            self.working_changes.clear()
            return count
        
        # 暂存指定键的变更
        staged_count = 0
        remaining_changes = []
        
        for change in self.working_changes:
            if change.key in keys or (change.old_key and change.old_key in keys):
                self.staged_changes.append(change)
                staged_count += 1
            else:
                remaining_changes.append(change)
        
        self.working_changes = remaining_changes
        return staged_count
    
    def unstage_changes(self, keys: Optional[List[str]] = None) -> int:
        """取消暂存变更"""
        if keys is None:
            # 取消暂存所有变更
            self.working_changes.extend(self.staged_changes)
            count = len(self.staged_changes)
            self.staged_changes.clear()
            return count
        
        # 取消暂存指定键的变更
        unstaged_count = 0
        remaining_staged = []
        
        for change in self.staged_changes:
            if change.key in keys or (change.old_key and change.old_key in keys):
                self.working_changes.append(change)
                unstaged_count += 1
            else:
                remaining_staged.append(change)
        
        self.staged_changes = remaining_staged
        return unstaged_count
    
    def reset_working_changes(self) -> int:
        """重置工作区变更"""
        count = len(self.working_changes)
        self.working_changes.clear()
        
        # 重新加载当前分支的配置
        current_branch = self.branch_manager.get_current_branch()
        if current_branch and current_branch.current_commit:
            self.current_config = self.configs_storage.get(
                current_branch.current_commit, {}
            ).copy()
        
        return count
    
    def get_status(self) -> Dict[str, Any]:
        """获取仓库状态"""
        current_branch = self.branch_manager.get_current_branch()
        
        return {
            "current_branch": current_branch.branch_name if current_branch else None,
            "current_commit": current_branch.current_commit if current_branch else None,
            "working_changes": len(self.working_changes),
            "staged_changes": len(self.staged_changes),
            "total_commits": len(self.history.commits),
            "total_branches": len(self.branch_manager.branches),
            "total_tags": len(self.tag_manager.tags),
            "repository_path": self.repository_path,
            "changes": {
                "working": [
                    {
                        "key": change.key,
                        "type": change.change_type.value,
                        "old_value": change.old_value,
                        "new_value": change.new_value
                    }
                    for change in self.working_changes
                ],
                "staged": [
                    {
                        "key": change.key,
                        "type": change.change_type.value,
                        "old_value": change.old_value,
                        "new_value": change.new_value
                    }
                    for change in self.staged_changes
                ]
            }
        }
    
    # 提交操作
    def commit(self, message: str, author: str = "system") -> Optional[ConfigCommit]:
        """提交暂存的变更"""
        if not self.staged_changes:
            raise ValueError("No staged changes to commit")
        
        if not message.strip():
            raise ValueError("Commit message cannot be empty")
        
        # 获取当前分支
        current_branch = self.branch_manager.get_current_branch()
        if not current_branch:
            raise ValueError("No current branch")
        
        # 创建提交
        commit = ConfigCommit(
            message=message,
            author=author,
            parent_commits=[current_branch.current_commit] if current_branch.current_commit else []
        )
        
        # 添加所有暂存的变更
        commit.add_changes(self.staged_changes.copy())
        commit.set_config_snapshot(self.current_config.copy())
        
        if commit.validate():
            # 添加到历史
            self.history.add_commit(commit)
            self.configs_storage[commit.commit_id] = self.current_config.copy()
            
            # 更新当前分支
            current_branch.add_commit(commit.commit_id)
            
            # 清空暂存区
            self.staged_changes.clear()
            
            return commit
        
        return None
    
    # 分支操作
    def create_branch(self, branch_name: str, base_branch: Optional[str] = None) -> ConfigBranch:
        """创建分支"""
        branch = self.branch_manager.create_branch(branch_name, base_branch)
        self.history.add_branch(branch)
        return branch
    
    def checkout_branch(self, branch_name: str) -> bool:
        """切换分支"""
        if self.working_changes or self.staged_changes:
            raise ValueError("Cannot checkout with uncommitted changes")
        
        success = self.branch_manager.checkout_branch(branch_name)
        
        if success:
            # 加载分支的当前配置
            branch = self.branch_manager.get_branch(branch_name)
            if branch and branch.current_commit:
                self.current_config = self.configs_storage.get(
                    branch.current_commit, {}
                ).copy()
            else:
                self.current_config = {}
        
        return success
    
    def delete_branch(self, branch_name: str, force: bool = False) -> bool:
        """删除分支"""
        return self.branch_manager.delete_branch(branch_name, force)
    
    def list_branches(self) -> List[str]:
        """列出所有分支"""
        return self.branch_manager.list_branches()
    
    # 合并操作
    def merge_branch(self, source_branch: str, 
                    strategy: MergeStrategy = MergeStrategy.MERGE_COMMIT,
                    message: str = "") -> MergeResult:
        """合并分支"""
        if self.working_changes or self.staged_changes:
            raise ValueError("Cannot merge with uncommitted changes")
        
        # 获取分支对象
        source = self.branch_manager.get_branch(source_branch)
        current = self.branch_manager.get_current_branch()
        
        if not source or not current:
            raise ValueError("Invalid source or current branch")
        
        # 获取配置
        source_config = self.configs_storage.get(source.current_commit, {})
        target_config = self.configs_storage.get(current.current_commit, {})
        
        # 执行合并
        result = self.merge_manager.merge_branches(
            source, current, source_config, target_config, 
            strategy=strategy, message=message
        )
        
        return result
    
    def resolve_conflict(self, conflict_index: int, resolution: ConflictResolution,
                        resolved_value: Any = None) -> bool:
        """解决合并冲突"""
        return self.merge_manager.resolve_conflict(conflict_index, resolution, resolved_value)
    
    def complete_merge(self, author: str = "system") -> Optional[ConfigCommit]:
        """完成合并"""
        merge_commit = self.merge_manager.complete_merge()
        
        if merge_commit:
            # 设置作者
            merge_commit.author = author
            
            # 添加到历史
            self.history.add_commit(merge_commit)
            self.configs_storage[merge_commit.commit_id] = merge_commit.config_snapshot.copy()
            
            # 更新当前分支
            current_branch = self.branch_manager.get_current_branch()
            if current_branch:
                current_branch.add_commit(merge_commit.commit_id)
            
            # 更新当前配置
            self.current_config = merge_commit.config_snapshot.copy()
        
        return merge_commit
    
    def abort_merge(self) -> bool:
        """中止合并"""
        return self.merge_manager.abort_merge()
    
    # 标签操作
    def create_tag(self, tag_name: str, commit_id: Optional[str] = None,
                  message: str = "", author: str = "system") -> ConfigTag:
        """创建标签"""
        if commit_id is None:
            current_branch = self.branch_manager.get_current_branch()
            if not current_branch or not current_branch.current_commit:
                raise ValueError("No current commit to tag")
            commit_id = current_branch.current_commit
        
        return self.tag_manager.create_tag(tag_name, commit_id, message=message, author=author)
    
    def create_release(self, version_type: VersionType, 
                      title: str = "", description: str = "",
                      features: Optional[List[str]] = None,
                      fixes: Optional[List[str]] = None,
                      breaking_changes: Optional[List[str]] = None,
                      author: str = "system") -> ConfigTag:
        """创建发布版本"""
        current_branch = self.branch_manager.get_current_branch()
        if not current_branch or not current_branch.current_commit:
            raise ValueError("No current commit to release")
        
        return self.tag_manager.create_release(
            version_type=version_type,
            commit_id=current_branch.current_commit,
            title=title,
            description=description,
            features=features,
            fixes=fixes,
            breaking_changes=breaking_changes,
            author=author
        )
    
    def delete_tag(self, tag_name: str) -> bool:
        """删除标签"""
        return self.tag_manager.delete_tag(tag_name)
    
    def list_tags(self, pattern: Optional[str] = None) -> List[ConfigTag]:
        """列出标签"""
        return self.tag_manager.list_tags(pattern)
    
    # 历史查询
    def get_commit_history(self, branch_name: Optional[str] = None, 
                          limit: Optional[int] = None) -> List[ConfigCommit]:
        """获取提交历史"""
        return self.history.get_commit_history(branch_name, limit)
    
    def search_commits(self, query: HistoryQuery) -> List[ConfigCommit]:
        """搜索提交"""
        return self.history.search_commits(query)
    
    def get_diff(self, commit1: str, commit2: str) -> Optional[ConfigDiff]:
        """获取两个提交之间的差异"""
        return self.history.get_diff_between_commits(commit1, commit2)
    
    # 配置查询
    def get_config_at_commit(self, commit_id: str) -> Optional[Dict[str, Any]]:
        """获取指定提交时的配置"""
        return self.configs_storage.get(commit_id)
    
    def get_current_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return self.current_config.copy()
    
    def get_file_history(self, file_key: str) -> List[ConfigCommit]:
        """获取文件历史"""
        return self.history.get_file_commits(file_key)
    
    # 导入导出
    def export_repository(self, export_path: str) -> bool:
        """导出仓库"""
        try:
            export_data = {
                "repository_info": self.repository_info,
                "commits": [commit.to_dict() for commit in self.history.commits.values()],
                "branches": [branch.to_dict() for branch in self.branch_manager.branches.values()],
                "tags": [tag.to_dict() for tag in self.tag_manager.tags.values()],
                "configs_storage": self.configs_storage,
                "branch_status": self.branch_manager.get_branch_status()
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
            
            return True
        except Exception:
            return False
    
    def import_repository(self, import_path: str) -> bool:
        """导入仓库"""
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # 恢复提交
            for commit_data in import_data.get("commits", []):
                commit = ConfigCommit.from_dict(commit_data)
                self.history.add_commit(commit)
            
            # 恢复分支
            for branch_data in import_data.get("branches", []):
                branch = ConfigBranch.from_dict(branch_data)
                self.branch_manager.branches[branch.branch_name] = branch
                self.history.add_branch(branch)
            
            # 恢复标签
            for tag_data in import_data.get("tags", []):
                tag = ConfigTag.from_dict(tag_data)
                self.tag_manager.tags[tag.tag_name] = tag
            
            # 恢复配置存储
            self.configs_storage = import_data.get("configs_storage", {})
            
            # 恢复仓库信息
            self.repository_info = import_data.get("repository_info", self.repository_info)
            
            # 恢复分支状态
            branch_status = import_data.get("branch_status", {})
            self.branch_manager.current_branch = branch_status.get("current_branch")
            
            return True
        except Exception:
            return False
    
    # 辅助方法
    def _update_working_change(self, new_change: ConfigChange) -> None:
        """更新工作区变更"""
        # 查找是否已有相同键的变更
        existing_index = None
        for i, change in enumerate(self.working_changes):
            if change.key == new_change.key:
                existing_index = i
                break
        
        if existing_index is not None:
            # 合并变更
            existing = self.working_changes[existing_index]
            if existing.change_type == ChangeType.ADDED and new_change.change_type == ChangeType.MODIFIED:
                # 新增后修改 = 新增最终值
                existing.new_value = new_change.new_value
            elif existing.change_type == ChangeType.ADDED and new_change.change_type == ChangeType.DELETED:
                # 新增后删除 = 移除变更
                self.working_changes.pop(existing_index)
            else:
                # 替换变更
                self.working_changes[existing_index] = new_change
        else:
            # 添加新变更
            self.working_changes.append(new_change)
    
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
            elif not isinstance(current[k], dict):
                # 如果存在的值不是字典，替换为字典
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
    
    def __str__(self) -> str:
        return f"ConfigVersionControl(path='{self.repository_path}')"
    
    def __repr__(self) -> str:
        status = self.get_status()
        return (f"ConfigVersionControl(branch='{status['current_branch']}', "
                f"commits={status['total_commits']}, "
                f"changes={status['working_changes']}+{status['staged_changes']})")