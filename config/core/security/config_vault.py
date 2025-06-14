"""
安全配置库

提供敏感配置的安全存储、管理和访问功能。
支持配置分级、加密存储、访问控制和安全审计。
"""

import os
import json
import uuid
import logging
from typing import Dict, List, Optional, Any, Union, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import Lock
import secrets

from .config_encryption import ConfigEncryption, EncryptionType, SecurityLevel, create_encryption_system
from .access_control import AccessControl, Permission, ResourceType, User

logger = logging.getLogger(__name__)


class VaultSecurityLevel(Enum):
    """保险库安全级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    TOP_SECRET = "top_secret"


class VaultEntryType(Enum):
    """保险库条目类型"""
    SECRET = "secret"
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    CONFIG = "config"


@dataclass
class VaultEntry:
    """保险库条目"""
    entry_id: str
    name: str
    entry_type: VaultEntryType
    security_level: VaultSecurityLevel
    encrypted_value: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    created_by: str = ""
    updated_at: Optional[datetime] = None
    updated_by: str = ""
    accessed_at: Optional[datetime] = None
    accessed_by: str = ""
    access_count: int = 0
    expires_at: Optional[datetime] = None
    is_active: bool = True
    version: int = 1


@dataclass
class VaultPolicy:
    """保险库策略"""
    policy_id: str
    name: str
    description: str
    security_level: VaultSecurityLevel
    max_access_count: Optional[int] = None
    access_time_window: Optional[int] = None  # 秒
    required_permissions: Set[Permission] = field(default_factory=set)
    allowed_users: Set[str] = field(default_factory=set)
    allowed_roles: Set[str] = field(default_factory=set)
    ip_whitelist: Set[str] = field(default_factory=set)
    time_restrictions: Dict[str, Any] = field(default_factory=dict)
    audit_required: bool = True
    encryption_required: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


@dataclass
class VaultAccess:
    """保险库访问记录"""
    access_id: str
    entry_id: str
    user_id: str
    action: str
    success: bool
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


class VaultError(Exception):
    """保险库错误"""
    pass


class VaultAccessDeniedError(VaultError):
    """保险库访问被拒绝错误"""
    pass


class VaultSecurityError(VaultError):
    """保险库安全错误"""
    pass


class ConfigVault:
    """
    安全配置库
    
    提供敏感配置的安全存储、管理和访问功能。
    支持配置分级、加密存储、访问控制和安全审计。
    """
    
    def __init__(
        self,
        encryption: Optional[ConfigEncryption] = None,
        access_control: Optional[AccessControl] = None,
        vault_path: Optional[str] = None,
        default_security_level: VaultSecurityLevel = VaultSecurityLevel.HIGH
    ):
        # 核心组件
        self.encryption = encryption or create_encryption_system(
            encryption_type=EncryptionType.AES_256_GCM,
            security_level=SecurityLevel.HIGH
        )
        self.access_control = access_control or AccessControl()
        
        # 存储
        self.entries: Dict[str, VaultEntry] = {}
        self.policies: Dict[str, VaultPolicy] = {}
        self.access_logs: List[VaultAccess] = []
        
        # 配置
        self.vault_path = Path(vault_path) if vault_path else None
        self.default_security_level = default_security_level
        
        # 统计
        self.total_entries = 0
        self.total_accesses = 0
        self.failed_accesses = 0
        self.security_violations = 0
        
        # 线程安全
        self._lock = Lock()
        
        # 初始化
        self._initialize()
    
    def _initialize(self):
        """初始化保险库"""
        try:
            # 创建默认策略
            self._create_default_policies()
            
            # 加载保险库数据
            if self.vault_path and self.vault_path.exists():
                self._load_vault()
            
            logger.info("ConfigVault initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ConfigVault: {e}")
            raise VaultError(f"Initialization failed: {e}")
    
    def store_secret(
        self,
        session_token: str,
        name: str,
        value: Any,
        entry_type: VaultEntryType = VaultEntryType.SECRET,
        security_level: Optional[VaultSecurityLevel] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        expires_in: Optional[int] = None  # 秒
    ) -> str:
        """
        存储密钥
        
        Args:
            session_token: 会话令牌
            name: 密钥名称
            value: 密钥值
            entry_type: 条目类型
            security_level: 安全级别
            metadata: 元数据
            tags: 标签
            expires_in: 过期时间（秒）
            
        Returns:
            str: 条目ID
        """
        with self._lock:
            try:
                # 验证访问权限
                self._check_vault_access(session_token, "store", ResourceType.SECURITY)
                
                # 获取用户信息
                user_id = self._get_user_from_session(session_token)
                
                # 设置默认值
                security_level = security_level or self.default_security_level
                metadata = metadata or {}
                tags = set(tags) if tags else set()
                
                # 检查名称是否已存在
                for entry in self.entries.values():
                    if entry.name == name and entry.is_active:
                        raise VaultError(f"Entry name already exists: {name}")
                
                # 加密值
                encrypted_value = self.encryption.encrypt_config_value(name, value)
                
                # 创建条目
                entry_id = str(uuid.uuid4())
                expires_at = datetime.datetime.now(datetime.timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
                
                entry = VaultEntry(
                    entry_id=entry_id,
                    name=name,
                    entry_type=entry_type,
                    security_level=security_level,
                    encrypted_value=encrypted_value,
                    metadata=metadata,
                    tags=tags,
                    created_by=user_id,
                    expires_at=expires_at
                )
                
                self.entries[entry_id] = entry
                self.total_entries += 1
                
                # 记录访问日志
                self._log_vault_access(
                    entry_id=entry_id,
                    user_id=user_id,
                    action="store",
                    success=True
                )
                
                # 保存保险库
                if self.vault_path:
                    self._save_vault()
                
                logger.info(f"Secret stored: {name} ({entry_id})")
                return entry_id
                
            except Exception as e:
                logger.error(f"Failed to store secret: {e}")
                
                # 记录失败访问
                try:
                    user_id = self._get_user_from_session(session_token)
                    self._log_vault_access(
                        entry_id="unknown",
                        user_id=user_id,
                        action="store",
                        success=False,
                        context={"error": str(e)}
                    )
                except:
                    pass
                
                raise VaultError(f"Failed to store secret: {e}")
    
    def retrieve_secret(
        self,
        session_token: str,
        entry_id: Optional[str] = None,
        name: Optional[str] = None
    ) -> Tuple[str, Any]:
        """
        检索密钥
        
        Args:
            session_token: 会话令牌
            entry_id: 条目ID
            name: 密钥名称
            
        Returns:
            Tuple[str, Any]: (条目ID, 密钥值)
        """
        with self._lock:
            try:
                # 验证访问权限
                self._check_vault_access(session_token, "retrieve", ResourceType.SECURITY)
                
                # 获取用户信息
                user_id = self._get_user_from_session(session_token)
                
                # 查找条目
                entry = None
                if entry_id:
                    entry = self.entries.get(entry_id)
                elif name:
                    for e in self.entries.values():
                        if e.name == name and e.is_active:
                            entry = e
                            entry_id = e.entry_id
                            break
                
                if not entry:
                    raise VaultError("Entry not found")
                
                # 检查条目状态
                if not entry.is_active:
                    raise VaultError("Entry is inactive")
                
                # 检查过期时间
                if entry.expires_at and entry.expires_at < datetime.datetime.now(datetime.timezone.utc):
                    raise VaultError("Entry has expired")
                
                # 检查安全策略
                self._check_security_policy(entry, user_id, "retrieve")
                
                # 解密值
                _, value = self.encryption.decrypt_config_value(entry.encrypted_value)
                
                # 更新访问信息
                entry.accessed_at = datetime.datetime.now(datetime.timezone.utc)
                entry.accessed_by = user_id
                entry.access_count += 1
                
                self.total_accesses += 1
                
                # 记录访问日志
                self._log_vault_access(
                    entry_id=entry_id,
                    user_id=user_id,
                    action="retrieve",
                    success=True
                )
                
                logger.debug(f"Secret retrieved: {entry.name} ({entry_id})")
                return entry_id, value
                
            except Exception as e:
                self.failed_accesses += 1
                logger.error(f"Failed to retrieve secret: {e}")
                
                # 记录失败访问
                try:
                    user_id = self._get_user_from_session(session_token)
                    self._log_vault_access(
                        entry_id=entry_id or "unknown",
                        user_id=user_id,
                        action="retrieve",
                        success=False,
                        context={"error": str(e)}
                    )
                except:
                    pass
                
                raise VaultAccessDeniedError(f"Failed to retrieve secret: {e}")
    
    def update_secret(
        self,
        session_token: str,
        entry_id: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        更新密钥
        
        Args:
            session_token: 会话令牌
            entry_id: 条目ID
            value: 新的密钥值
            metadata: 新的元数据
            
        Returns:
            bool: 更新是否成功
        """
        with self._lock:
            try:
                # 验证访问权限
                self._check_vault_access(session_token, "update", ResourceType.SECURITY)
                
                # 获取用户信息
                user_id = self._get_user_from_session(session_token)
                
                # 查找条目
                if entry_id not in self.entries:
                    raise VaultError("Entry not found")
                
                entry = self.entries[entry_id]
                
                # 检查条目状态
                if not entry.is_active:
                    raise VaultError("Entry is inactive")
                
                # 检查安全策略
                self._check_security_policy(entry, user_id, "update")
                
                # 加密新值
                encrypted_value = self.encryption.encrypt_config_value(entry.name, value)
                
                # 更新条目
                entry.encrypted_value = encrypted_value
                entry.updated_at = datetime.datetime.now(datetime.timezone.utc)
                entry.updated_by = user_id
                entry.version += 1
                
                if metadata:
                    entry.metadata.update(metadata)
                
                # 记录访问日志
                self._log_vault_access(
                    entry_id=entry_id,
                    user_id=user_id,
                    action="update",
                    success=True
                )
                
                # 保存保险库
                if self.vault_path:
                    self._save_vault()
                
                logger.info(f"Secret updated: {entry.name} ({entry_id})")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update secret: {e}")
                
                # 记录失败访问
                try:
                    user_id = self._get_user_from_session(session_token)
                    self._log_vault_access(
                        entry_id=entry_id,
                        user_id=user_id,
                        action="update",
                        success=False,
                        context={"error": str(e)}
                    )
                except:
                    pass
                
                raise VaultError(f"Failed to update secret: {e}")
    
    def delete_secret(
        self,
        session_token: str,
        entry_id: str,
        permanent: bool = False
    ) -> bool:
        """
        删除密钥
        
        Args:
            session_token: 会话令牌
            entry_id: 条目ID
            permanent: 是否永久删除
            
        Returns:
            bool: 删除是否成功
        """
        with self._lock:
            try:
                # 验证访问权限
                permission = Permission.DELETE if not permanent else Permission.ADMIN
                self.access_control.check_access(session_token, f"vault:{entry_id}", permission, ResourceType.SECURITY)
                
                # 获取用户信息
                user_id = self._get_user_from_session(session_token)
                
                # 查找条目
                if entry_id not in self.entries:
                    raise VaultError("Entry not found")
                
                entry = self.entries[entry_id]
                
                if permanent:
                    # 永久删除
                    del self.entries[entry_id]
                    logger.info(f"Secret permanently deleted: {entry.name} ({entry_id})")
                else:
                    # 软删除
                    entry.is_active = False
                    entry.updated_at = datetime.datetime.now(datetime.timezone.utc)
                    entry.updated_by = user_id
                    logger.info(f"Secret deactivated: {entry.name} ({entry_id})")
                
                # 记录访问日志
                self._log_vault_access(
                    entry_id=entry_id,
                    user_id=user_id,
                    action="delete" if permanent else "deactivate",
                    success=True
                )
                
                # 保存保险库
                if self.vault_path:
                    self._save_vault()
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to delete secret: {e}")
                
                # 记录失败访问
                try:
                    user_id = self._get_user_from_session(session_token)
                    self._log_vault_access(
                        entry_id=entry_id,
                        user_id=user_id,
                        action="delete",
                        success=False,
                        context={"error": str(e)}
                    )
                except:
                    pass
                
                raise VaultError(f"Failed to delete secret: {e}")
    
    def list_secrets(
        self,
        session_token: str,
        entry_type: Optional[VaultEntryType] = None,
        security_level: Optional[VaultSecurityLevel] = None,
        tags: Optional[List[str]] = None,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        列出密钥
        
        Args:
            session_token: 会话令牌
            entry_type: 条目类型过滤
            security_level: 安全级别过滤
            tags: 标签过滤
            include_inactive: 是否包含非活跃条目
            
        Returns:
            List[Dict[str, Any]]: 密钥列表
        """
        with self._lock:
            try:
                # 验证访问权限
                self._check_vault_access(session_token, "list", ResourceType.SECURITY)
                
                # 获取用户信息
                user_id = self._get_user_from_session(session_token)
                
                entries_info = []
                
                for entry in self.entries.values():
                    # 状态过滤
                    if not include_inactive and not entry.is_active:
                        continue
                    
                    # 过期检查
                    is_expired = entry.expires_at and entry.expires_at < datetime.datetime.now(datetime.timezone.utc)
                    
                    # 类型过滤
                    if entry_type and entry.entry_type != entry_type:
                        continue
                    
                    # 安全级别过滤
                    if security_level and entry.security_level != security_level:
                        continue
                    
                    # 标签过滤
                    if tags and not any(tag in entry.tags for tag in tags):
                        continue
                    
                    # 检查访问权限
                    try:
                        self._check_security_policy(entry, user_id, "list")
                    except:
                        continue  # 跳过无权限的条目
                    
                    entry_info = {
                        'entry_id': entry.entry_id,
                        'name': entry.name,
                        'entry_type': entry.entry_type.value,
                        'security_level': entry.security_level.value,
                        'tags': list(entry.tags),
                        'created_at': entry.created_at.isoformat(),
                        'created_by': entry.created_by,
                        'updated_at': entry.updated_at.isoformat() if entry.updated_at else None,
                        'updated_by': entry.updated_by,
                        'accessed_at': entry.accessed_at.isoformat() if entry.accessed_at else None,
                        'access_count': entry.access_count,
                        'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
                        'is_active': entry.is_active,
                        'is_expired': is_expired,
                        'version': entry.version,
                        'metadata': entry.metadata
                    }
                    
                    entries_info.append(entry_info)
                
                # 记录访问日志
                self._log_vault_access(
                    entry_id="list",
                    user_id=user_id,
                    action="list",
                    success=True,
                    context={"count": len(entries_info)}
                )
                
                return entries_info
                
            except Exception as e:
                logger.error(f"Failed to list secrets: {e}")
                raise VaultError(f"Failed to list secrets: {e}")
    
    def create_policy(
        self,
        session_token: str,
        name: str,
        description: str,
        security_level: VaultSecurityLevel,
        **policy_params
    ) -> str:
        """创建保险库策略"""
        with self._lock:
            try:
                # 验证管理权限
                self.access_control.check_access(session_token, "vault:policy", Permission.ADMIN, ResourceType.SECURITY)
                
                # 获取用户信息
                user_id = self._get_user_from_session(session_token)
                
                # 检查策略名是否已存在
                for policy in self.policies.values():
                    if policy.name == name:
                        raise VaultError(f"Policy name already exists: {name}")
                
                # 创建策略
                policy_id = str(uuid.uuid4())
                policy = VaultPolicy(
                    policy_id=policy_id,
                    name=name,
                    description=description,
                    security_level=security_level,
                    **policy_params
                )
                
                self.policies[policy_id] = policy
                
                logger.info(f"Vault policy created: {name} ({policy_id})")
                return policy_id
                
            except Exception as e:
                logger.error(f"Failed to create policy: {e}")
                raise VaultError(f"Failed to create policy: {e}")
    
    def get_vault_stats(self, session_token: str) -> Dict[str, Any]:
        """获取保险库统计信息"""
        with self._lock:
            try:
                # 验证访问权限
                self._check_vault_access(session_token, "stats", ResourceType.SECURITY)
                
                # 统计各类型条目
                type_stats = {}
                level_stats = {}
                
                for entry in self.entries.values():
                    if entry.is_active:
                        # 类型统计
                        entry_type = entry.entry_type.value
                        type_stats[entry_type] = type_stats.get(entry_type, 0) + 1
                        
                        # 安全级别统计
                        security_level = entry.security_level.value
                        level_stats[security_level] = level_stats.get(security_level, 0) + 1
                
                # 过期统计
                expired_count = 0
                expiring_soon_count = 0  # 7天内过期
                cutoff_time = datetime.datetime.now(datetime.timezone.utc) + timedelta(days=7)
                
                for entry in self.entries.values():
                    if entry.is_active and entry.expires_at:
                        if entry.expires_at < datetime.datetime.now(datetime.timezone.utc):
                            expired_count += 1
                        elif entry.expires_at < cutoff_time:
                            expiring_soon_count += 1
                
                return {
                    'total_entries': self.total_entries,
                    'active_entries': len([e for e in self.entries.values() if e.is_active]),
                    'inactive_entries': len([e for e in self.entries.values() if not e.is_active]),
                    'expired_entries': expired_count,
                    'expiring_soon_entries': expiring_soon_count,
                    'total_accesses': self.total_accesses,
                    'failed_accesses': self.failed_accesses,
                    'security_violations': self.security_violations,
                    'success_rate': (self.total_accesses - self.failed_accesses) / self.total_accesses if self.total_accesses > 0 else 1.0,
                    'entry_types': type_stats,
                    'security_levels': level_stats,
                    'total_policies': len(self.policies),
                    'total_access_logs': len(self.access_logs)
                }
                
            except Exception as e:
                logger.error(f"Failed to get vault stats: {e}")
                raise VaultError(f"Failed to get vault stats: {e}")
    
    def _create_default_policies(self):
        """创建默认策略"""
        # 低安全级别策略
        low_policy = VaultPolicy(
            policy_id="default_low",
            name="Default Low Security",
            description="Default policy for low security entries",
            security_level=VaultSecurityLevel.LOW,
            required_permissions={Permission.READ},
            audit_required=False,
            encryption_required=True
        )
        self.policies["default_low"] = low_policy
        
        # 高安全级别策略
        high_policy = VaultPolicy(
            policy_id="default_high",
            name="Default High Security",
            description="Default policy for high security entries",
            security_level=VaultSecurityLevel.HIGH,
            required_permissions={Permission.READ, Permission.DECRYPT},
            max_access_count=100,
            access_time_window=3600,  # 1小时
            audit_required=True,
            encryption_required=True
        )
        self.policies["default_high"] = high_policy
        
        # 绝密级别策略
        top_secret_policy = VaultPolicy(
            policy_id="default_top_secret",
            name="Default Top Secret",
            description="Default policy for top secret entries",
            security_level=VaultSecurityLevel.TOP_SECRET,
            required_permissions={Permission.ADMIN, Permission.DECRYPT},
            max_access_count=10,
            access_time_window=3600,
            audit_required=True,
            encryption_required=True
        )
        self.policies["default_top_secret"] = top_secret_policy
    
    def _check_vault_access(self, session_token: str, action: str, resource_type: ResourceType):
        """检查保险库访问权限"""
        permission_map = {
            "store": Permission.WRITE,
            "retrieve": Permission.READ,
            "update": Permission.WRITE,
            "delete": Permission.DELETE,
            "list": Permission.READ,
            "stats": Permission.READ
        }
        
        permission = permission_map.get(action, Permission.READ)
        self.access_control.check_access(session_token, "vault", permission, resource_type)
    
    def _check_security_policy(self, entry: VaultEntry, user_id: str, action: str):
        """检查安全策略"""
        # 查找适用的策略
        policy_id = f"default_{entry.security_level.value}"
        if policy_id not in self.policies:
            return  # 没有策略则允许
        
        policy = self.policies[policy_id]
        
        # 检查访问次数限制
        if policy.max_access_count and entry.access_count >= policy.max_access_count:
            raise VaultSecurityError("Access count limit exceeded")
        
        # 检查时间窗口限制
        if policy.access_time_window and entry.accessed_at:
            time_diff = (datetime.datetime.now(datetime.timezone.utc) - entry.accessed_at).total_seconds()
            if time_diff < policy.access_time_window:
                raise VaultSecurityError("Access time window restriction")
        
        # 检查用户限制
        if policy.allowed_users and user_id not in policy.allowed_users:
            raise VaultSecurityError("User not allowed by policy")
    
    def _get_user_from_session(self, session_token: str) -> str:
        """从会话获取用户ID"""
        # 这里应该从access_control中获取会话信息
        # 为了简化，假设可以访问session信息
        if hasattr(self.access_control, 'sessions') and session_token in self.access_control.sessions:
            return self.access_control.sessions[session_token]['user_id']
        raise VaultError("Invalid session token")
    
    def _log_vault_access(
        self,
        entry_id: str,
        user_id: str,
        action: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ):
        """记录保险库访问日志"""
        access = VaultAccess(
            access_id=str(uuid.uuid4()),
            entry_id=entry_id,
            user_id=user_id,
            action=action,
            success=success,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            context=context or {}
        )
        
        self.access_logs.append(access)
        
        # 限制日志数量
        if len(self.access_logs) > 10000:
            self.access_logs = self.access_logs[-10000:]
        
        if not success:
            self.security_violations += 1
    
    def _save_vault(self):
        """保存保险库到文件"""
        if not self.vault_path:
            return
        
        try:
            # 确保目录存在
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 序列化数据
            vault_data = {
                'entries': {},
                'policies': {},
                'version': '1.0'
            }
            
            # 序列化条目
            for entry_id, entry in self.entries.items():
                vault_data['entries'][entry_id] = {
                    'entry_id': entry.entry_id,
                    'name': entry.name,
                    'entry_type': entry.entry_type.value,
                    'security_level': entry.security_level.value,
                    'encrypted_value': entry.encrypted_value,
                    'metadata': entry.metadata,
                    'tags': list(entry.tags),
                    'created_at': entry.created_at.isoformat(),
                    'created_by': entry.created_by,
                    'updated_at': entry.updated_at.isoformat() if entry.updated_at else None,
                    'updated_by': entry.updated_by,
                    'accessed_at': entry.accessed_at.isoformat() if entry.accessed_at else None,
                    'accessed_by': entry.accessed_by,
                    'access_count': entry.access_count,
                    'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
                    'is_active': entry.is_active,
                    'version': entry.version
                }
            
            # 序列化策略
            for policy_id, policy in self.policies.items():
                if not policy.is_system_role:  # 只保存非系统策略
                    vault_data['policies'][policy_id] = {
                        'policy_id': policy.policy_id,
                        'name': policy.name,
                        'description': policy.description,
                        'security_level': policy.security_level.value,
                        'max_access_count': policy.max_access_count,
                        'access_time_window': policy.access_time_window,
                        'required_permissions': [p.value for p in policy.required_permissions],
                        'allowed_users': list(policy.allowed_users),
                        'allowed_roles': list(policy.allowed_roles),
                        'ip_whitelist': list(policy.ip_whitelist),
                        'time_restrictions': policy.time_restrictions,
                        'audit_required': policy.audit_required,
                        'encryption_required': policy.encryption_required,
                        'created_at': policy.created_at.isoformat()
                    }
            
            # 写入文件
            with open(self.vault_path, 'w') as f:
                json.dump(vault_data, f, indent=2)
            
            logger.debug(f"Vault saved to {self.vault_path}")
            
        except Exception as e:
            logger.error(f"Failed to save vault: {e}")
            raise VaultError(f"Failed to save vault: {e}")
    
    def _load_vault(self):
        """从文件加载保险库"""
        try:
            with open(self.vault_path, 'r') as f:
                vault_data = json.load(f)
            
            # 加载条目
            for entry_id, entry_data in vault_data.get('entries', {}).items():
                entry = VaultEntry(
                    entry_id=entry_data['entry_id'],
                    name=entry_data['name'],
                    entry_type=VaultEntryType(entry_data['entry_type']),
                    security_level=VaultSecurityLevel(entry_data['security_level']),
                    encrypted_value=entry_data['encrypted_value'],
                    metadata=entry_data['metadata'],
                    tags=set(entry_data['tags']),
                    created_at=datetime.fromisoformat(entry_data['created_at']),
                    created_by=entry_data['created_by'],
                    updated_at=datetime.fromisoformat(entry_data['updated_at']) if entry_data['updated_at'] else None,
                    updated_by=entry_data['updated_by'],
                    accessed_at=datetime.fromisoformat(entry_data['accessed_at']) if entry_data['accessed_at'] else None,
                    accessed_by=entry_data['accessed_by'],
                    access_count=entry_data['access_count'],
                    expires_at=datetime.fromisoformat(entry_data['expires_at']) if entry_data['expires_at'] else None,
                    is_active=entry_data['is_active'],
                    version=entry_data['version']
                )
                self.entries[entry_id] = entry
            
            self.total_entries = len(self.entries)
            
            logger.debug(f"Loaded {len(self.entries)} entries from {self.vault_path}")
            
        except Exception as e:
            logger.error(f"Failed to load vault: {e}")
            raise VaultError(f"Failed to load vault: {e}")


# 便利函数
def create_config_vault(
    encryption_type: EncryptionType = EncryptionType.AES_256_GCM,
    admin_username: str = "admin",
    admin_password: str = "admin123",
    vault_path: Optional[str] = None
) -> ConfigVault:
    """
    创建配置保险库实例
    
    Args:
        encryption_type: 加密类型
        admin_username: 管理员用户名
        admin_password: 管理员密码
        vault_path: 保险库存储路径
        
    Returns:
        ConfigVault: 配置保险库实例
    """
    # 创建加密系统
    encryption = create_encryption_system(
        encryption_type=encryption_type,
        security_level=SecurityLevel.HIGH
    )
    
    # 创建访问控制
    access_control = AccessControl(
        admin_user=admin_username,
        admin_password=admin_password
    )
    
    return ConfigVault(
        encryption=encryption,
        access_control=access_control,
        vault_path=vault_path
    )