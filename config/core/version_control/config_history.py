"""
配置历史管理系统

Git风格的配置历史追踪和查询。
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import re

from .config_commit import ConfigCommit, ConfigChange, ChangeType, ConfigDiff
from .config_branch import ConfigBranch


class HistorySearchType(Enum):
    """历史搜索类型"""
    COMMIT_MESSAGE = "commit_message"   # 按提交信息搜索
    AUTHOR = "author"                   # 按作者搜索
    FILE_PATH = "file_path"            # 按文件路径搜索
    DATE_RANGE = "date_range"          # 按日期范围搜索
    CHANGE_TYPE = "change_type"        # 按变更类型搜索


@dataclass
class HistoryQuery:
    """历史查询条件"""
    search_type: HistorySearchType
    value: Any
    limit: Optional[int] = None
    offset: int = 0
    
    # 日期范围查询专用
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # 高级选项
    case_sensitive: bool = False
    regex_mode: bool = False


@dataclass
class FileHistory:
    """文件历史记录"""
    file_key: str
    commits: List[str] = field(default_factory=list)
    total_changes: int = 0
    first_commit: Optional[str] = None
    last_commit: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None


@dataclass
class CommitStats:
    """提交统计信息"""
    total_commits: int = 0
    total_changes: int = 0
    additions: int = 0
    modifications: int = 0
    deletions: int = 0
    renames: int = 0
    authors: Dict[str, int] = field(default_factory=dict)
    daily_commits: Dict[str, int] = field(default_factory=dict)


class ConfigHistory:
    """配置历史管理
    
    管理配置的完整历史记录，提供历史查询和分析功能。
    """
    
    def __init__(self):
        # 存储所有提交
        self.commits: Dict[str, ConfigCommit] = {}
        
        # 存储分支信息
        self.branches: Dict[str, ConfigBranch] = {}
        
        # 文件历史索引
        self.file_histories: Dict[str, FileHistory] = {}
        
        # 快速查询索引
        self.author_index: Dict[str, List[str]] = {}  # author -> commit_ids
        self.date_index: Dict[str, List[str]] = {}    # date -> commit_ids
        self.message_index: Dict[str, List[str]] = {} # keyword -> commit_ids
        
        # 统计信息
        self.stats = CommitStats()
    
    def add_commit(self, commit: ConfigCommit) -> None:
        """添加提交到历史"""
        if commit.commit_id in self.commits:
            return  # 已存在
        
        self.commits[commit.commit_id] = commit
        self._update_indexes(commit)
        self._update_file_histories(commit)
        self._update_stats(commit)
    
    def add_branch(self, branch: ConfigBranch) -> None:
        """添加分支到历史"""
        self.branches[branch.branch_name] = branch
    
    def get_commit(self, commit_id: str) -> Optional[ConfigCommit]:
        """获取指定提交"""
        return self.commits.get(commit_id)
    
    def get_commit_history(self, branch_name: Optional[str] = None,
                          limit: Optional[int] = None,
                          offset: int = 0) -> List[ConfigCommit]:
        """获取提交历史"""
        if branch_name and branch_name in self.branches:
            # 获取特定分支的历史
            branch = self.branches[branch_name]
            commit_ids = branch.get_commit_history(limit)
            commits = [self.commits[cid] for cid in commit_ids if cid in self.commits]
        else:
            # 获取所有提交历史，按时间排序
            commits = sorted(self.commits.values(), 
                           key=lambda c: c.timestamp, reverse=True)
        
        # 应用分页
        if offset > 0:
            commits = commits[offset:]
        if limit:
            commits = commits[:limit]
        
        return commits
    
    def get_file_history(self, file_key: str) -> Optional[FileHistory]:
        """获取文件历史"""
        return self.file_histories.get(file_key)
    
    def get_file_commits(self, file_key: str, limit: Optional[int] = None) -> List[ConfigCommit]:
        """获取影响特定文件的提交"""
        commits = []
        
        for commit in self.commits.values():
            # 检查是否有影响该文件的变更
            for change in commit.changes:
                if change.key == file_key or (change.old_key and change.old_key == file_key):
                    commits.append(commit)
                    break
        
        # 按时间排序
        commits.sort(key=lambda c: c.timestamp, reverse=True)
        
        if limit:
            commits = commits[:limit]
        
        return commits
    
    def search_commits(self, query: HistoryQuery) -> List[ConfigCommit]:
        """搜索提交"""
        if query.search_type == HistorySearchType.COMMIT_MESSAGE:
            return self._search_by_message(query.value, query.case_sensitive, 
                                         query.regex_mode, query.limit, query.offset)
        
        elif query.search_type == HistorySearchType.AUTHOR:
            return self._search_by_author(query.value, query.limit, query.offset)
        
        elif query.search_type == HistorySearchType.FILE_PATH:
            return self._search_by_file_path(query.value, query.case_sensitive,
                                           query.regex_mode, query.limit, query.offset)
        
        elif query.search_type == HistorySearchType.DATE_RANGE:
            return self._search_by_date_range(query.start_date, query.end_date,
                                            query.limit, query.offset)
        
        elif query.search_type == HistorySearchType.CHANGE_TYPE:
            return self._search_by_change_type(ChangeType(query.value),
                                             query.limit, query.offset)
        
        return []
    
    def get_diff_between_commits(self, commit1_id: str, commit2_id: str) -> Optional[ConfigDiff]:
        """获取两个提交之间的差异"""
        commit1 = self.commits.get(commit1_id)
        commit2 = self.commits.get(commit2_id)
        
        if not commit1 or not commit2:
            return None
        
        # 比较两个提交的配置快照
        config1 = commit1.config_snapshot
        config2 = commit2.config_snapshot
        
        from .config_commit import create_diff_between_configs
        return create_diff_between_configs(config1, config2)
    
    def get_commit_path(self, from_commit: str, to_commit: str,
                       branch_name: Optional[str] = None) -> List[str]:
        """获取两个提交之间的路径"""
        if branch_name and branch_name in self.branches:
            branch = self.branches[branch_name]
            commits = branch.commits
            
            try:
                from_idx = commits.index(from_commit)
                to_idx = commits.index(to_commit)
                
                if from_idx <= to_idx:
                    return commits[from_idx:to_idx + 1]
                else:
                    return list(reversed(commits[to_idx:from_idx + 1]))
            except ValueError:
                return []
        
        # 如果没有指定分支，尝试简单的时间序列路径
        from_commit_obj = self.commits.get(from_commit)
        to_commit_obj = self.commits.get(to_commit)
        
        if not from_commit_obj or not to_commit_obj:
            return []
        
        # 简化实现：返回时间范围内的所有提交
        start_time = min(from_commit_obj.timestamp, to_commit_obj.timestamp)
        end_time = max(from_commit_obj.timestamp, to_commit_obj.timestamp)
        
        path_commits = []
        for commit in sorted(self.commits.values(), key=lambda c: c.timestamp):
            if start_time <= commit.timestamp <= end_time:
                path_commits.append(commit.commit_id)
        
        return path_commits
    
    def get_statistics(self, branch_name: Optional[str] = None,
                      days: int = 30) -> CommitStats:
        """获取统计信息"""
        if branch_name:
            # 特定分支的统计
            if branch_name not in self.branches:
                return CommitStats()
            
            branch = self.branches[branch_name]
            commit_ids = set(branch.commits)
            commits = [c for c in self.commits.values() if c.commit_id in commit_ids]
        else:
            # 全局统计
            commits = list(self.commits.values())
        
        # 应用时间过滤
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - timedelta(days=days)
        commits = [c for c in commits if c.timestamp >= cutoff_date]
        
        # 计算统计信息
        stats = CommitStats()
        stats.total_commits = len(commits)
        
        for commit in commits:
            stats.total_changes += len(commit.changes)
            
            for change in commit.changes:
                if change.change_type == ChangeType.ADDED:
                    stats.additions += 1
                elif change.change_type == ChangeType.MODIFIED:
                    stats.modifications += 1
                elif change.change_type == ChangeType.DELETED:
                    stats.deletions += 1
                elif change.change_type == ChangeType.RENAMED:
                    stats.renames += 1
            
            # 作者统计
            stats.authors[commit.author] = stats.authors.get(commit.author, 0) + 1
            
            # 日期统计
            date_str = commit.timestamp.strftime('%Y-%m-%d')
            stats.daily_commits[date_str] = stats.daily_commits.get(date_str, 0) + 1
        
        return stats
    
    def get_blame_info(self, file_key: str) -> Dict[str, Dict[str, Any]]:
        """获取文件的blame信息（谁最后修改了每个部分）"""
        file_commits = self.get_file_commits(file_key)
        
        if not file_commits:
            return {}
        
        # 简化实现：返回最后一次修改的信息
        last_commit = file_commits[0]
        
        blame_info = {}
        for change in last_commit.changes:
            if change.key == file_key or (change.old_key and change.old_key == file_key):
                blame_info[change.key] = {
                    "commit_id": last_commit.commit_id,
                    "author": last_commit.author,
                    "timestamp": last_commit.timestamp.isoformat(),
                    "message": last_commit.message,
                    "change_type": change.change_type.value
                }
        
        return blame_info
    
    # 私有方法
    def _update_indexes(self, commit: ConfigCommit) -> None:
        """更新查询索引"""
        # 作者索引
        if commit.author not in self.author_index:
            self.author_index[commit.author] = []
        self.author_index[commit.author].append(commit.commit_id)
        
        # 日期索引
        date_str = commit.timestamp.strftime('%Y-%m-%d')
        if date_str not in self.date_index:
            self.date_index[date_str] = []
        self.date_index[date_str].append(commit.commit_id)
        
        # 消息关键词索引
        words = re.findall(r'\\b\\w+\\b', commit.message.lower())
        for word in words:
            if word not in self.message_index:
                self.message_index[word] = []
            self.message_index[word].append(commit.commit_id)
    
    def _update_file_histories(self, commit: ConfigCommit) -> None:
        """更新文件历史"""
        for change in commit.changes:
            key = change.key
            
            if key not in self.file_histories:
                self.file_histories[key] = FileHistory(
                    file_key=key,
                    first_commit=commit.commit_id,
                    created_at=commit.timestamp
                )
            
            history = self.file_histories[key]
            history.commits.append(commit.commit_id)
            history.total_changes += 1
            history.last_commit = commit.commit_id
            history.last_modified = commit.timestamp
            
            # 处理重命名
            if change.change_type == ChangeType.RENAMED and change.old_key:
                if change.old_key in self.file_histories:
                    old_history = self.file_histories[change.old_key]
                    # 合并历史
                    history.commits = old_history.commits + history.commits
                    history.total_changes += old_history.total_changes
                    history.first_commit = old_history.first_commit
                    history.created_at = old_history.created_at
                    
                    # 删除旧的历史记录
                    del self.file_histories[change.old_key]
    
    def _update_stats(self, commit: ConfigCommit) -> None:
        """更新统计信息"""
        self.stats.total_commits += 1
        self.stats.total_changes += len(commit.changes)
        
        for change in commit.changes:
            if change.change_type == ChangeType.ADDED:
                self.stats.additions += 1
            elif change.change_type == ChangeType.MODIFIED:
                self.stats.modifications += 1
            elif change.change_type == ChangeType.DELETED:
                self.stats.deletions += 1
            elif change.change_type == ChangeType.RENAMED:
                self.stats.renames += 1
        
        self.stats.authors[commit.author] = self.stats.authors.get(commit.author, 0) + 1
        
        date_str = commit.timestamp.strftime('%Y-%m-%d')
        self.stats.daily_commits[date_str] = self.stats.daily_commits.get(date_str, 0) + 1
    
    def _search_by_message(self, pattern: str, case_sensitive: bool,
                          regex_mode: bool, limit: Optional[int], offset: int) -> List[ConfigCommit]:
        """按提交信息搜索"""
        results = []
        
        if regex_mode:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex = re.compile(pattern, flags)
            except re.error:
                return []
            
            for commit in self.commits.values():
                if regex.search(commit.message):
                    results.append(commit)
        else:
            search_pattern = pattern if case_sensitive else pattern.lower()
            
            for commit in self.commits.values():
                message = commit.message if case_sensitive else commit.message.lower()
                if search_pattern in message:
                    results.append(commit)
        
        # 按时间排序
        results.sort(key=lambda c: c.timestamp, reverse=True)
        
        # 应用分页
        if offset > 0:
            results = results[offset:]
        if limit:
            results = results[:limit]
        
        return results
    
    def _search_by_author(self, author: str, limit: Optional[int], offset: int) -> List[ConfigCommit]:
        """按作者搜索"""
        commit_ids = self.author_index.get(author, [])
        commits = [self.commits[cid] for cid in commit_ids if cid in self.commits]
        
        # 按时间排序
        commits.sort(key=lambda c: c.timestamp, reverse=True)
        
        # 应用分页
        if offset > 0:
            commits = commits[offset:]
        if limit:
            commits = commits[:limit]
        
        return commits
    
    def _search_by_file_path(self, pattern: str, case_sensitive: bool,
                           regex_mode: bool, limit: Optional[int], offset: int) -> List[ConfigCommit]:
        """按文件路径搜索"""
        results = []
        
        if regex_mode:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex = re.compile(pattern, flags)
            except re.error:
                return []
            
            for commit in self.commits.values():
                for change in commit.changes:
                    if regex.search(change.key) or (change.old_key and regex.search(change.old_key)):
                        results.append(commit)
                        break
        else:
            search_pattern = pattern if case_sensitive else pattern.lower()
            
            for commit in self.commits.values():
                for change in commit.changes:
                    key = change.key if case_sensitive else change.key.lower()
                    old_key = change.old_key if not change.old_key else (
                        change.old_key if case_sensitive else change.old_key.lower())
                    
                    if (search_pattern in key or 
                        (old_key and search_pattern in old_key)):
                        results.append(commit)
                        break
        
        # 按时间排序
        results.sort(key=lambda c: c.timestamp, reverse=True)
        
        # 应用分页
        if offset > 0:
            results = results[offset:]
        if limit:
            results = results[:limit]
        
        return results
    
    def _search_by_date_range(self, start_date: Optional[datetime],
                            end_date: Optional[datetime],
                            limit: Optional[int], offset: int) -> List[ConfigCommit]:
        """按日期范围搜索"""
        results = []
        
        for commit in self.commits.values():
            if start_date and commit.timestamp < start_date:
                continue
            if end_date and commit.timestamp > end_date:
                continue
            results.append(commit)
        
        # 按时间排序
        results.sort(key=lambda c: c.timestamp, reverse=True)
        
        # 应用分页
        if offset > 0:
            results = results[offset:]
        if limit:
            results = results[:limit]
        
        return results
    
    def _search_by_change_type(self, change_type: ChangeType,
                             limit: Optional[int], offset: int) -> List[ConfigCommit]:
        """按变更类型搜索"""
        results = []
        
        for commit in self.commits.values():
            for change in commit.changes:
                if change.change_type == change_type:
                    results.append(commit)
                    break
        
        # 按时间排序
        results.sort(key=lambda c: c.timestamp, reverse=True)
        
        # 应用分页
        if offset > 0:
            results = results[offset:]
        if limit:
            results = results[:limit]
        
        return results
    
    def clear_history(self, before_date: Optional[datetime] = None) -> int:
        """清理历史记录"""
        if not before_date:
            # 清理所有历史
            count = len(self.commits)
            self.commits.clear()
            self.file_histories.clear()
            self.author_index.clear()
            self.date_index.clear()
            self.message_index.clear()
            self.stats = CommitStats()
            return count
        
        # 清理指定日期之前的历史
        to_remove = []
        for commit_id, commit in self.commits.items():
            if commit.timestamp < before_date:
                to_remove.append(commit_id)
        
        for commit_id in to_remove:
            del self.commits[commit_id]
        
        # 重建索引
        self._rebuild_indexes()
        
        return len(to_remove)
    
    def _rebuild_indexes(self) -> None:
        """重建所有索引"""
        self.author_index.clear()
        self.date_index.clear()
        self.message_index.clear()
        self.file_histories.clear()
        self.stats = CommitStats()
        
        for commit in self.commits.values():
            self._update_indexes(commit)
            self._update_file_histories(commit)
            self._update_stats(commit)
    
    def export_history(self, format: str = "json") -> str:
        """导出历史记录"""
        if format == "json":
            import json
            data = {
                "commits": [commit.to_dict() for commit in self.commits.values()],
                "branches": [branch.to_dict() for branch in self.branches.values()],
                "statistics": {
                    "total_commits": self.stats.total_commits,
                    "total_changes": self.stats.total_changes,
                    "additions": self.stats.additions,
                    "modifications": self.stats.modifications,
                    "deletions": self.stats.deletions,
                    "renames": self.stats.renames,
                    "authors": self.stats.authors,
                    "daily_commits": self.stats.daily_commits
                }
            }
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        raise ValueError(f"Unsupported export format: {format}")
    
    def __len__(self) -> int:
        return len(self.commits)
    
    def __contains__(self, commit_id: str) -> bool:
        return commit_id in self.commits