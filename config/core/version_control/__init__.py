"""
配置版本控制模块

Git风格的配置版本管理系统，包含提交、分支、合并、历史、标签等完整功能。
"""

from .config_commit import (
    ConfigCommit, ConfigChange, ConfigDiff, ChangeType,
    create_diff_between_configs
)

from .config_branch import (
    ConfigBranch, BranchManager, BranchProtection, 
    BranchProtectionLevel, MergeStrategy
)

from .config_merge import (
    ConfigMerge, MergeResult, MergeConflict, 
    ConflictType, ConflictResolution
)

from .config_history import (
    ConfigHistory, HistoryQuery, FileHistory, 
    CommitStats, HistorySearchType
)

from .config_tag import (
    ConfigTag, TagManager, SemanticVersion, ReleaseNotes,
    TagType, VersionType
)

from .config_version_control import ConfigVersionControl

__all__ = [
    # 提交相关
    'ConfigCommit', 'ConfigChange', 'ConfigDiff', 'ChangeType',
    'create_diff_between_configs',
    
    # 分支相关
    'ConfigBranch', 'BranchManager', 'BranchProtection',
    'BranchProtectionLevel', 'MergeStrategy',
    
    # 合并相关
    'ConfigMerge', 'MergeResult', 'MergeConflict',
    'ConflictType', 'ConflictResolution',
    
    # 历史相关
    'ConfigHistory', 'HistoryQuery', 'FileHistory',
    'CommitStats', 'HistorySearchType',
    
    # 标签相关
    'ConfigTag', 'TagManager', 'SemanticVersion', 'ReleaseNotes',
    'TagType', 'VersionType',
    
    # 主管理器
    'ConfigVersionControl'
]