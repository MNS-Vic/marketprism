"""
配置标签管理系统

Git风格的配置版本标签和发布管理。
"""

import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config_commit import ConfigCommit


class TagType(Enum):
    """标签类型"""
    LIGHTWEIGHT = "lightweight"    # 轻量级标签
    ANNOTATED = "annotated"        # 带注释的标签
    RELEASE = "release"            # 发布标签


class VersionType(Enum):
    """版本类型"""
    MAJOR = "major"     # 主版本 (x.0.0)
    MINOR = "minor"     # 次版本 (1.x.0)
    PATCH = "patch"     # 补丁版本 (1.1.x)
    PRERELEASE = "prerelease"  # 预发布版本 (1.1.1-alpha.1)


@dataclass
class SemanticVersion:
    """语义化版本"""
    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: Optional[str] = None
    build: Optional[str] = None
    
    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version += f"-{self.prerelease}"
        if self.build:
            version += f"+{self.build}"
        return version
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return False
        return (self.major == other.major and
                self.minor == other.minor and
                self.patch == other.patch and
                self.prerelease == other.prerelease)
    
    def __lt__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        
        # 比较主版本号
        if self.major != other.major:
            return self.major < other.major
        
        # 比较次版本号
        if self.minor != other.minor:
            return self.minor < other.minor
        
        # 比较补丁版本号
        if self.patch != other.patch:
            return self.patch < other.patch
        
        # 比较预发布版本
        if self.prerelease is None and other.prerelease is None:
            return False
        if self.prerelease is None:
            return False  # 正式版本大于预发布版本
        if other.prerelease is None:
            return True   # 预发布版本小于正式版本
        
        return self.prerelease < other.prerelease
    
    def __le__(self, other) -> bool:
        return self == other or self < other
    
    def __gt__(self, other) -> bool:
        return not self <= other
    
    def __ge__(self, other) -> bool:
        return not self < other
    
    def bump(self, version_type: VersionType, prerelease: Optional[str] = None) -> 'SemanticVersion':
        """升级版本号"""
        if version_type == VersionType.MAJOR:
            return SemanticVersion(self.major + 1, 0, 0, prerelease)
        elif version_type == VersionType.MINOR:
            return SemanticVersion(self.major, self.minor + 1, 0, prerelease)
        elif version_type == VersionType.PATCH:
            return SemanticVersion(self.major, self.minor, self.patch + 1, prerelease)
        elif version_type == VersionType.PRERELEASE:
            if self.prerelease:
                # 升级预发布版本号
                parts = self.prerelease.split('.')
                if len(parts) >= 2 and parts[-1].isdigit():
                    parts[-1] = str(int(parts[-1]) + 1)
                    new_prerelease = '.'.join(parts)
                else:
                    new_prerelease = f"{self.prerelease}.1"
            else:
                new_prerelease = prerelease or "alpha.1"
            
            return SemanticVersion(self.major, self.minor, self.patch, new_prerelease)
        
        return self
    
    @classmethod
    def parse(cls, version_str: str) -> 'SemanticVersion':
        """解析版本字符串"""
        # 移除前缀 'v'
        if version_str.startswith('v'):
            version_str = version_str[1:]
        
        # 正则表达式匹配语义化版本
        pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-(\S+?))?(?:\+(\S+?))?$'
        match = re.match(pattern, version_str)
        
        if not match:
            raise ValueError(f"Invalid semantic version: {version_str}")
        
        major, minor, patch, prerelease, build = match.groups()
        
        return cls(
            major=int(major),
            minor=int(minor),
            patch=int(patch),
            prerelease=prerelease,
            build=build
        )


@dataclass
class ReleaseNotes:
    """发布说明"""
    version: str
    title: str = ""
    description: str = ""
    features: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)
    breaking_changes: List[str] = field(default_factory=list)
    deprecated: List[str] = field(default_factory=list)
    security: List[str] = field(default_factory=list)
    migration_notes: str = ""
    
    def to_markdown(self) -> str:
        """转换为Markdown格式"""
        lines = []
        
        # 标题
        if self.title:
            lines.append(f"# {self.title}")
        else:
            lines.append(f"# Release {self.version}")
        
        lines.append("")
        
        # 描述
        if self.description:
            lines.append(self.description)
            lines.append("")
        
        # 新功能
        if self.features:
            lines.append("## ✨ New Features")
            for feature in self.features:
                lines.append(f"- {feature}")
            lines.append("")
        
        # 修复
        if self.fixes:
            lines.append("## 🐛 Bug Fixes")
            for fix in self.fixes:
                lines.append(f"- {fix}")
            lines.append("")
        
        # 破坏性变更
        if self.breaking_changes:
            lines.append("## ⚠️ Breaking Changes")
            for change in self.breaking_changes:
                lines.append(f"- {change}")
            lines.append("")
        
        # 废弃功能
        if self.deprecated:
            lines.append("## 📌 Deprecated")
            for dep in self.deprecated:
                lines.append(f"- {dep}")
            lines.append("")
        
        # 安全更新
        if self.security:
            lines.append("## 🔒 Security")
            for sec in self.security:
                lines.append(f"- {sec}")
            lines.append("")
        
        # 迁移说明
        if self.migration_notes:
            lines.append("## 🔄 Migration Notes")
            lines.append(self.migration_notes)
            lines.append("")
        
        return "\\n".join(lines)


class ConfigTag:
    """配置标签
    
    Git风格的配置版本标签，支持语义化版本和发布管理。
    """
    
    def __init__(self, tag_name: str, commit_id: str, tag_type: TagType = TagType.LIGHTWEIGHT,
                 message: str = "", author: str = "system"):
        self.tag_name = self._validate_tag_name(tag_name)
        self.commit_id = commit_id
        self.tag_type = tag_type
        self.message = message
        self.author = author
        self.created_at = datetime.utcnow()
        
        # 尝试解析语义化版本
        self.semantic_version: Optional[SemanticVersion] = None
        try:
            self.semantic_version = SemanticVersion.parse(tag_name)
        except ValueError:
            pass  # 不是标准的语义化版本
        
        # 发布说明
        self.release_notes: Optional[ReleaseNotes] = None
        
        # 元数据
        self.metadata: Dict[str, Any] = {}
        
        # 签名信息（用于验证）
        self.signature: Optional[str] = None
        self.verified: bool = False
    
    def _validate_tag_name(self, name: str) -> str:
        """验证标签名称"""
        if not name:
            raise ValueError("Tag name cannot be empty")
        
        # Git标签命名规则
        invalid_chars = ['~', '^', ':', '?', '*', '[', '\\', ' ', '\\t', '\\n']
        for char in invalid_chars:
            if char in name:
                raise ValueError(f"Tag name cannot contain '{char}'")
        
        # 不能以 / 开头或结尾
        if name.startswith('/') or name.endswith('/'):
            raise ValueError("Tag name cannot start or end with '/'")
        
        # 不能包含连续的 //
        if '//' in name:
            raise ValueError("Tag name cannot contain '//'")
        
        return name
    
    def set_release_notes(self, release_notes: ReleaseNotes) -> None:
        """设置发布说明"""
        self.release_notes = release_notes
    
    def is_semantic_version(self) -> bool:
        """是否为语义化版本"""
        return self.semantic_version is not None
    
    def is_prerelease(self) -> bool:
        """是否为预发布版本"""
        return (self.semantic_version is not None and 
                self.semantic_version.prerelease is not None)
    
    def get_version_info(self) -> Dict[str, Any]:
        """获取版本信息"""
        info = {
            "tag_name": self.tag_name,
            "tag_type": self.tag_type.value,
            "commit_id": self.commit_id,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "is_semantic_version": self.is_semantic_version(),
            "is_prerelease": self.is_prerelease()
        }
        
        if self.semantic_version:
            info["semantic_version"] = {
                "major": self.semantic_version.major,
                "minor": self.semantic_version.minor,
                "patch": self.semantic_version.patch,
                "prerelease": self.semantic_version.prerelease,
                "build": self.semantic_version.build,
                "version_string": str(self.semantic_version)
            }
        
        return info
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            "tag_name": self.tag_name,
            "commit_id": self.commit_id,
            "tag_type": self.tag_type.value,
            "message": self.message,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "signature": self.signature,
            "verified": self.verified
        }
        
        if self.semantic_version:
            data["semantic_version"] = {
                "major": self.semantic_version.major,
                "minor": self.semantic_version.minor,
                "patch": self.semantic_version.patch,
                "prerelease": self.semantic_version.prerelease,
                "build": self.semantic_version.build
            }
        
        if self.release_notes:
            data["release_notes"] = {
                "version": self.release_notes.version,
                "title": self.release_notes.title,
                "description": self.release_notes.description,
                "features": self.release_notes.features,
                "fixes": self.release_notes.fixes,
                "breaking_changes": self.release_notes.breaking_changes,
                "deprecated": self.release_notes.deprecated,
                "security": self.release_notes.security,
                "migration_notes": self.release_notes.migration_notes
            }
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigTag':
        """从字典创建标签对象"""
        tag = cls(
            tag_name=data["tag_name"],
            commit_id=data["commit_id"],
            tag_type=TagType(data.get("tag_type", "lightweight")),
            message=data.get("message", ""),
            author=data.get("author", "system")
        )
        
        tag.created_at = datetime.fromisoformat(data.get("created_at"))
        tag.metadata = data.get("metadata", {})
        tag.signature = data.get("signature")
        tag.verified = data.get("verified", False)
        
        # 恢复语义化版本
        if "semantic_version" in data:
            sv_data = data["semantic_version"]
            tag.semantic_version = SemanticVersion(
                major=sv_data["major"],
                minor=sv_data["minor"],
                patch=sv_data["patch"],
                prerelease=sv_data.get("prerelease"),
                build=sv_data.get("build")
            )
        
        # 恢复发布说明
        if "release_notes" in data:
            rn_data = data["release_notes"]
            tag.release_notes = ReleaseNotes(
                version=rn_data["version"],
                title=rn_data.get("title", ""),
                description=rn_data.get("description", ""),
                features=rn_data.get("features", []),
                fixes=rn_data.get("fixes", []),
                breaking_changes=rn_data.get("breaking_changes", []),
                deprecated=rn_data.get("deprecated", []),
                security=rn_data.get("security", []),
                migration_notes=rn_data.get("migration_notes", "")
            )
        
        return tag
    
    def __str__(self) -> str:
        return f"ConfigTag({self.tag_name})"
    
    def __repr__(self) -> str:
        return (f"ConfigTag(name='{self.tag_name}', "
                f"commit='{self.commit_id[:8]}', type={self.tag_type.value})")


class TagManager:
    """标签管理器
    
    管理所有配置标签的创建、删除、查询等操作。
    """
    
    def __init__(self):
        self.tags: Dict[str, ConfigTag] = {}
        self.commit_tags: Dict[str, List[str]] = {}  # commit_id -> tag_names
    
    def create_tag(self, tag_name: str, commit_id: str, 
                   tag_type: TagType = TagType.LIGHTWEIGHT,
                   message: str = "", author: str = "system",
                   release_notes: Optional[ReleaseNotes] = None) -> ConfigTag:
        """创建标签"""
        if tag_name in self.tags:
            raise ValueError(f"Tag '{tag_name}' already exists")
        
        tag = ConfigTag(
            tag_name=tag_name,
            commit_id=commit_id,
            tag_type=tag_type,
            message=message,
            author=author
        )
        
        if release_notes:
            tag.set_release_notes(release_notes)
        
        self.tags[tag_name] = tag
        
        # 更新提交->标签映射
        if commit_id not in self.commit_tags:
            self.commit_tags[commit_id] = []
        self.commit_tags[commit_id].append(tag_name)
        
        return tag
    
    def delete_tag(self, tag_name: str) -> bool:
        """删除标签"""
        if tag_name not in self.tags:
            return False
        
        tag = self.tags[tag_name]
        commit_id = tag.commit_id
        
        # 从映射中移除
        if commit_id in self.commit_tags:
            self.commit_tags[commit_id].remove(tag_name)
            if not self.commit_tags[commit_id]:
                del self.commit_tags[commit_id]
        
        del self.tags[tag_name]
        return True
    
    def get_tag(self, tag_name: str) -> Optional[ConfigTag]:
        """获取标签"""
        return self.tags.get(tag_name)
    
    def list_tags(self, pattern: Optional[str] = None, 
                  semantic_only: bool = False,
                  sort_by_version: bool = False) -> List[ConfigTag]:
        """列出标签"""
        tags = list(self.tags.values())
        
        # 过滤语义化版本
        if semantic_only:
            tags = [tag for tag in tags if tag.is_semantic_version()]
        
        # 模式匹配
        if pattern:
            import fnmatch
            tags = [tag for tag in tags if fnmatch.fnmatch(tag.tag_name, pattern)]
        
        # 排序
        if sort_by_version and tags:
            # 分离语义化版本和非语义化版本
            semantic_tags = [tag for tag in tags if tag.is_semantic_version()]
            non_semantic_tags = [tag for tag in tags if not tag.is_semantic_version()]
            
            # 语义化版本按版本号排序
            semantic_tags.sort(key=lambda t: t.semantic_version, reverse=True)
            
            # 非语义化版本按创建时间排序
            non_semantic_tags.sort(key=lambda t: t.created_at, reverse=True)
            
            tags = semantic_tags + non_semantic_tags
        else:
            # 按创建时间排序
            tags.sort(key=lambda t: t.created_at, reverse=True)
        
        return tags
    
    def get_tags_for_commit(self, commit_id: str) -> List[ConfigTag]:
        """获取指定提交的所有标签"""
        tag_names = self.commit_tags.get(commit_id, [])
        return [self.tags[name] for name in tag_names if name in self.tags]
    
    def get_latest_version(self, prerelease: bool = False) -> Optional[ConfigTag]:
        """获取最新版本标签"""
        semantic_tags = [tag for tag in self.tags.values() if tag.is_semantic_version()]
        
        if not prerelease:
            # 过滤掉预发布版本
            semantic_tags = [tag for tag in semantic_tags if not tag.is_prerelease()]
        
        if not semantic_tags:
            return None
        
        # 按版本号排序，返回最新的
        semantic_tags.sort(key=lambda t: t.semantic_version, reverse=True)
        return semantic_tags[0]
    
    def get_next_version(self, version_type: VersionType, 
                        prerelease: Optional[str] = None) -> str:
        """获取下一个版本号"""
        latest = self.get_latest_version(prerelease=False)
        
        if not latest or not latest.semantic_version:
            # 如果没有现有版本，从1.0.0开始
            if version_type == VersionType.PRERELEASE:
                return f"1.0.0-{prerelease or 'alpha.1'}"
            else:
                return "1.0.0"
        
        next_version = latest.semantic_version.bump(version_type, prerelease)
        return str(next_version)
    
    def create_release(self, version_type: VersionType, commit_id: str,
                      title: str = "", description: str = "",
                      features: Optional[List[str]] = None,
                      fixes: Optional[List[str]] = None,
                      breaking_changes: Optional[List[str]] = None,
                      prerelease: Optional[str] = None,
                      author: str = "system") -> ConfigTag:
        """创建发布版本"""
        # 生成下一个版本号
        version_str = self.get_next_version(version_type, prerelease)
        
        # 创建发布说明
        release_notes = ReleaseNotes(
            version=version_str,
            title=title or f"Release {version_str}",
            description=description,
            features=features or [],
            fixes=fixes or [],
            breaking_changes=breaking_changes or []
        )
        
        # 创建标签
        tag = self.create_tag(
            tag_name=f"v{version_str}",
            commit_id=commit_id,
            tag_type=TagType.RELEASE,
            message=f"Release {version_str}",
            author=author,
            release_notes=release_notes
        )
        
        return tag
    
    def get_version_history(self, limit: Optional[int] = None) -> List[ConfigTag]:
        """获取版本历史"""
        semantic_tags = [tag for tag in self.tags.values() if tag.is_semantic_version()]
        semantic_tags.sort(key=lambda t: t.semantic_version, reverse=True)
        
        if limit:
            semantic_tags = semantic_tags[:limit]
        
        return semantic_tags
    
    def export_changelog(self, since_version: Optional[str] = None) -> str:
        """导出变更日志"""
        versions = self.get_version_history()
        
        if since_version:
            # 找到起始版本的索引
            start_index = 0
            for i, tag in enumerate(versions):
                if tag.tag_name == since_version or str(tag.semantic_version) == since_version:
                    start_index = i
                    break
            versions = versions[:start_index]
        
        lines = ["# Changelog", ""]
        
        for tag in versions:
            if tag.release_notes:
                lines.append(tag.release_notes.to_markdown())
                lines.append("")
        
        return "\\n".join(lines)
    
    def get_tag_statistics(self) -> Dict[str, Any]:
        """获取标签统计"""
        total_tags = len(self.tags)
        semantic_tags = [tag for tag in self.tags.values() if tag.is_semantic_version()]
        prerelease_tags = [tag for tag in semantic_tags if tag.is_prerelease()]
        release_tags = [tag for tag in self.tags.values() if tag.tag_type == TagType.RELEASE]
        
        # 按类型统计
        type_stats = {}
        for tag in self.tags.values():
            tag_type = tag.tag_type.value
            type_stats[tag_type] = type_stats.get(tag_type, 0) + 1
        
        # 按作者统计
        author_stats = {}
        for tag in self.tags.values():
            author_stats[tag.author] = author_stats.get(tag.author, 0) + 1
        
        return {
            "total_tags": total_tags,
            "semantic_versions": len(semantic_tags),
            "prerelease_versions": len(prerelease_tags),
            "release_tags": len(release_tags),
            "latest_version": str(self.get_latest_version().semantic_version) if self.get_latest_version() else None,
            "type_distribution": type_stats,
            "author_distribution": author_stats
        }
    
    def __len__(self) -> int:
        return len(self.tags)
    
    def __contains__(self, tag_name: str) -> bool:
        return tag_name in self.tags