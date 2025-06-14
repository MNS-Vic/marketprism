"""
访问控制系统

提供基于角色和权限的配置访问控制功能。
支持用户管理、角色定义、权限控制和审计日志。
"""

import uuid
import hashlib
import secrets
import logging
from typing import Dict, List, Set, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
import json

logger = logging.getLogger(__name__)


class Permission(Enum):
    """权限类型"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    AUDIT = "audit"


class ResourceType(Enum):
    """资源类型"""
    CONFIG = "config"
    NAMESPACE = "namespace"
    SYSTEM = "system"
    SECURITY = "security"


@dataclass
class User:
    """用户信息"""
    user_id: str
    username: str
    email: str
    password_hash: str
    salt: str
    roles: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    last_login: Optional[datetime] = None
    is_active: bool = True
    is_locked: bool = False
    failed_login_attempts: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Role:
    """角色定义"""
    role_id: str
    name: str
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    resource_patterns: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    created_by: str = ""
    is_system_role: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessRequest:
    """访问请求"""
    user_id: str
    resource: str
    resource_type: ResourceType
    permission: Permission
    timestamp: datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditLog:
    """审计日志"""
    log_id: str
    user_id: str
    action: str
    resource: str
    resource_type: ResourceType
    permission: Permission
    result: bool
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


class AccessDeniedError(Exception):
    """访问被拒绝错误"""
    pass


class AuthenticationError(Exception):
    """认证错误"""
    pass


class AuthorizationError(Exception):
    """授权错误"""
    pass


class AccessControl:
    """
    访问控制系统
    
    提供基于角色和权限的配置访问控制功能。
    支持用户管理、角色定义、权限控制和审计日志。
    """
    
    def __init__(
        self,
        admin_user: Optional[str] = None,
        admin_password: Optional[str] = None,
        session_timeout: int = 3600,  # 1小时
        max_failed_attempts: int = 5
    ):
        # 存储
        self.users: Dict[str, User] = {}
        self.roles: Dict[str, Role] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.audit_logs: List[AuditLog] = []
        
        # 配置
        self.session_timeout = session_timeout
        self.max_failed_attempts = max_failed_attempts
        
        # 统计
        self.total_requests = 0
        self.granted_requests = 0
        self.denied_requests = 0
        self.failed_authentications = 0
        
        # 线程安全
        self._lock = Lock()
        
        # 初始化
        self._initialize()
        
        # 创建管理员用户
        if admin_user and admin_password:
            self._create_admin_user(admin_user, admin_password)
    
    def _initialize(self):
        """初始化访问控制系统"""
        try:
            # 创建系统角色
            self._create_system_roles()
            
            logger.info("AccessControl initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AccessControl: {e}")
            raise AuthorizationError(f"Initialization failed: {e}")
    
    def _create_system_roles(self):
        """创建系统角色"""
        # 超级管理员角色
        super_admin = Role(
            role_id="super_admin",
            name="Super Administrator",
            description="Full system access",
            permissions={
                Permission.READ, Permission.WRITE, Permission.DELETE,
                Permission.ADMIN, Permission.ENCRYPT, Permission.DECRYPT,
                Permission.MANAGE_USERS, Permission.MANAGE_ROLES, Permission.AUDIT
            },
            resource_patterns={"*"},
            is_system_role=True
        )
        self.roles["super_admin"] = super_admin
        
        # 配置管理员角色
        config_admin = Role(
            role_id="config_admin",
            name="Configuration Administrator",
            description="Configuration management access",
            permissions={Permission.READ, Permission.WRITE, Permission.DELETE, Permission.ENCRYPT, Permission.DECRYPT},
            resource_patterns={"config.*", "namespace.*"},
            is_system_role=True
        )
        self.roles["config_admin"] = config_admin
        
        # 只读用户角色
        read_only = Role(
            role_id="read_only",
            name="Read Only User",
            description="Read-only access",
            permissions={Permission.READ},
            resource_patterns={"config.*"},
            is_system_role=True
        )
        self.roles["read_only"] = read_only
        
        # 审计员角色
        auditor = Role(
            role_id="auditor",
            name="Auditor",
            description="Audit log access",
            permissions={Permission.READ, Permission.AUDIT},
            resource_patterns={"audit.*", "system.*"},
            is_system_role=True
        )
        self.roles["auditor"] = auditor
    
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        roles: Optional[List[str]] = None,
        created_by: str = "system"
    ) -> str:
        """
        创建用户
        
        Args:
            username: 用户名
            email: 邮箱
            password: 密码
            roles: 角色列表
            created_by: 创建者
            
        Returns:
            str: 用户ID
        """
        with self._lock:
            try:
                # 检查用户名是否已存在
                for user in self.users.values():
                    if user.username == username:
                        raise AuthorizationError(f"Username already exists: {username}")
                    if user.email == email:
                        raise AuthorizationError(f"Email already exists: {email}")
                
                # 生成用户ID和密码哈希
                user_id = str(uuid.uuid4())
                salt = secrets.token_hex(16)
                password_hash = self._hash_password(password, salt)
                
                # 创建用户
                user = User(
                    user_id=user_id,
                    username=username,
                    email=email,
                    password_hash=password_hash,
                    salt=salt,
                    roles=set(roles) if roles else set()
                )
                
                # 验证角色存在
                for role_id in user.roles:
                    if role_id not in self.roles:
                        raise AuthorizationError(f"Role not found: {role_id}")
                
                self.users[user_id] = user
                
                # 记录审计日志
                self._log_audit(
                    user_id=created_by,
                    action="create_user",
                    resource=f"user:{user_id}",
                    resource_type=ResourceType.SYSTEM,
                    permission=Permission.MANAGE_USERS,
                    result=True
                )
                
                logger.info(f"User created: {username} ({user_id})")
                return user_id
                
            except Exception as e:
                logger.error(f"User creation failed: {e}")
                raise AuthorizationError(f"User creation failed: {e}")
    
    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
            ip_address: IP地址
            user_agent: 用户代理
            
        Returns:
            str: 会话令牌
        """
        with self._lock:
            try:
                # 查找用户
                user = None
                for u in self.users.values():
                    if u.username == username:
                        user = u
                        break
                
                if not user:
                    self.failed_authentications += 1
                    raise AuthenticationError("Invalid username or password")
                
                # 检查用户状态
                if not user.is_active:
                    raise AuthenticationError("User account is disabled")
                
                if user.is_locked:
                    raise AuthenticationError("User account is locked")
                
                # 验证密码
                if not self._verify_password(password, user.password_hash, user.salt):
                    user.failed_login_attempts += 1
                    
                    # 锁定账户
                    if user.failed_login_attempts >= self.max_failed_attempts:
                        user.is_locked = True
                        logger.warning(f"User account locked: {username}")
                    
                    self.failed_authentications += 1
                    raise AuthenticationError("Invalid username or password")
                
                # 重置失败次数
                user.failed_login_attempts = 0
                user.last_login = datetime.datetime.now(datetime.timezone.utc)
                
                # 创建会话
                session_token = self._create_session(user.user_id, ip_address, user_agent)
                
                # 记录审计日志
                self._log_audit(
                    user_id=user.user_id,
                    action="authenticate",
                    resource=f"session:{session_token}",
                    resource_type=ResourceType.SYSTEM,
                    permission=Permission.READ,
                    result=True,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                
                logger.info(f"User authenticated: {username}")
                return session_token
                
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                raise AuthenticationError(f"Authentication failed: {e}")
    
    def authorize(
        self,
        session_token: str,
        resource: str,
        permission: Permission,
        resource_type: ResourceType = ResourceType.CONFIG
    ) -> bool:
        """
        授权检查
        
        Args:
            session_token: 会话令牌
            resource: 资源
            permission: 权限
            resource_type: 资源类型
            
        Returns:
            bool: 是否授权
        """
        with self._lock:
            try:
                self.total_requests += 1
                
                # 验证会话
                session = self._validate_session(session_token)
                user_id = session['user_id']
                user = self.users[user_id]
                
                # 检查用户权限
                has_permission = self._check_permission(user, resource, permission, resource_type)
                
                if has_permission:
                    self.granted_requests += 1
                else:
                    self.denied_requests += 1
                
                # 记录审计日志
                self._log_audit(
                    user_id=user_id,
                    action="authorize",
                    resource=resource,
                    resource_type=resource_type,
                    permission=permission,
                    result=has_permission
                )
                
                return has_permission
                
            except Exception as e:
                self.denied_requests += 1
                logger.error(f"Authorization failed: {e}")
                
                # 记录审计日志
                self._log_audit(
                    user_id="unknown",
                    action="authorize",
                    resource=resource,
                    resource_type=resource_type,
                    permission=permission,
                    result=False
                )
                
                return False
    
    def check_access(
        self,
        session_token: str,
        resource: str,
        permission: Permission,
        resource_type: ResourceType = ResourceType.CONFIG
    ) -> bool:
        """
        检查访问权限（抛出异常）
        
        Args:
            session_token: 会话令牌
            resource: 资源
            permission: 权限
            resource_type: 资源类型
            
        Returns:
            bool: 是否有权限
            
        Raises:
            AccessDeniedError: 访问被拒绝
        """
        if not self.authorize(session_token, resource, permission, resource_type):
            raise AccessDeniedError(f"Access denied: {permission.value} on {resource}")
        return True
    
    def create_role(
        self,
        name: str,
        description: str,
        permissions: List[Permission],
        resource_patterns: List[str],
        created_by: str
    ) -> str:
        """
        创建角色
        
        Args:
            name: 角色名称
            description: 角色描述
            permissions: 权限列表
            resource_patterns: 资源模式列表
            created_by: 创建者
            
        Returns:
            str: 角色ID
        """
        with self._lock:
            try:
                # 检查角色名是否已存在
                for role in self.roles.values():
                    if role.name == name:
                        raise AuthorizationError(f"Role name already exists: {name}")
                
                # 生成角色ID
                role_id = str(uuid.uuid4())
                
                # 创建角色
                role = Role(
                    role_id=role_id,
                    name=name,
                    description=description,
                    permissions=set(permissions),
                    resource_patterns=set(resource_patterns),
                    created_by=created_by
                )
                
                self.roles[role_id] = role
                
                # 记录审计日志
                self._log_audit(
                    user_id=created_by,
                    action="create_role",
                    resource=f"role:{role_id}",
                    resource_type=ResourceType.SYSTEM,
                    permission=Permission.MANAGE_ROLES,
                    result=True
                )
                
                logger.info(f"Role created: {name} ({role_id})")
                return role_id
                
            except Exception as e:
                logger.error(f"Role creation failed: {e}")
                raise AuthorizationError(f"Role creation failed: {e}")
    
    def assign_role(self, user_id: str, role_id: str, assigned_by: str) -> bool:
        """分配角色给用户"""
        with self._lock:
            try:
                if user_id not in self.users:
                    raise AuthorizationError(f"User not found: {user_id}")
                
                if role_id not in self.roles:
                    raise AuthorizationError(f"Role not found: {role_id}")
                
                user = self.users[user_id]
                user.roles.add(role_id)
                
                # 记录审计日志
                self._log_audit(
                    user_id=assigned_by,
                    action="assign_role",
                    resource=f"user:{user_id}",
                    resource_type=ResourceType.SYSTEM,
                    permission=Permission.MANAGE_USERS,
                    result=True,
                    context={"role_id": role_id}
                )
                
                logger.info(f"Role {role_id} assigned to user {user_id}")
                return True
                
            except Exception as e:
                logger.error(f"Role assignment failed: {e}")
                return False
    
    def revoke_role(self, user_id: str, role_id: str, revoked_by: str) -> bool:
        """撤销用户角色"""
        with self._lock:
            try:
                if user_id not in self.users:
                    return False
                
                user = self.users[user_id]
                if role_id in user.roles:
                    user.roles.remove(role_id)
                    
                    # 记录审计日志
                    self._log_audit(
                        user_id=revoked_by,
                        action="revoke_role",
                        resource=f"user:{user_id}",
                        resource_type=ResourceType.SYSTEM,
                        permission=Permission.MANAGE_USERS,
                        result=True,
                        context={"role_id": role_id}
                    )
                    
                    logger.info(f"Role {role_id} revoked from user {user_id}")
                    return True
                
                return False
                
            except Exception as e:
                logger.error(f"Role revocation failed: {e}")
                return False
    
    def logout(self, session_token: str) -> bool:
        """用户登出"""
        with self._lock:
            try:
                if session_token in self.sessions:
                    session = self.sessions[session_token]
                    user_id = session['user_id']
                    
                    # 删除会话
                    del self.sessions[session_token]
                    
                    # 记录审计日志
                    self._log_audit(
                        user_id=user_id,
                        action="logout",
                        resource=f"session:{session_token}",
                        resource_type=ResourceType.SYSTEM,
                        permission=Permission.READ,
                        result=True
                    )
                    
                    logger.info(f"User logged out: {user_id}")
                    return True
                
                return False
                
            except Exception as e:
                logger.error(f"Logout failed: {e}")
                return False
    
    def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        with self._lock:
            if user_id not in self.users:
                return None
            
            user = self.users[user_id]
            return {
                'user_id': user.user_id,
                'username': user.username,
                'email': user.email,
                'roles': list(user.roles),
                'created_at': user.created_at.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
                'is_active': user.is_active,
                'is_locked': user.is_locked,
                'failed_login_attempts': user.failed_login_attempts,
                'metadata': user.metadata
            }
    
    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户"""
        with self._lock:
            users_info = []
            for user_id in self.users:
                user_info = self.get_user_info(user_id)
                if user_info:
                    users_info.append(user_info)
            return users_info
    
    def list_roles(self) -> List[Dict[str, Any]]:
        """列出所有角色"""
        with self._lock:
            roles_info = []
            for role in self.roles.values():
                roles_info.append({
                    'role_id': role.role_id,
                    'name': role.name,
                    'description': role.description,
                    'permissions': [p.value for p in role.permissions],
                    'resource_patterns': list(role.resource_patterns),
                    'created_at': role.created_at.isoformat(),
                    'created_by': role.created_by,
                    'is_system_role': role.is_system_role,
                    'metadata': role.metadata
                })
            return roles_info
    
    def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取审计日志"""
        with self._lock:
            logs = []
            
            for log in self.audit_logs:
                # 过滤条件
                if user_id and log.user_id != user_id:
                    continue
                
                if start_time and log.timestamp < start_time:
                    continue
                
                if end_time and log.timestamp > end_time:
                    continue
                
                logs.append({
                    'log_id': log.log_id,
                    'user_id': log.user_id,
                    'action': log.action,
                    'resource': log.resource,
                    'resource_type': log.resource_type.value,
                    'permission': log.permission.value,
                    'result': log.result,
                    'timestamp': log.timestamp.isoformat(),
                    'ip_address': log.ip_address,
                    'user_agent': log.user_agent,
                    'context': log.context
                })
                
                if len(logs) >= limit:
                    break
            
            return logs
    
    def get_access_stats(self) -> Dict[str, Any]:
        """获取访问统计"""
        with self._lock:
            return {
                'total_users': len(self.users),
                'active_users': len([u for u in self.users.values() if u.is_active]),
                'locked_users': len([u for u in self.users.values() if u.is_locked]),
                'total_roles': len(self.roles),
                'active_sessions': len(self.sessions),
                'total_requests': self.total_requests,
                'granted_requests': self.granted_requests,
                'denied_requests': self.denied_requests,
                'failed_authentications': self.failed_authentications,
                'success_rate': self.granted_requests / self.total_requests if self.total_requests > 0 else 0,
                'total_audit_logs': len(self.audit_logs)
            }
    
    def _create_admin_user(self, username: str, password: str):
        """创建管理员用户"""
        try:
            admin_user_id = self.create_user(
                username=username,
                email=f"{username}@admin.local",
                password=password,
                roles=["super_admin"],
                created_by="system"
            )
            logger.info(f"Admin user created: {username}")
            
        except Exception as e:
            logger.error(f"Failed to create admin user: {e}")
    
    def _hash_password(self, password: str, salt: str) -> str:
        """哈希密码"""
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    
    def _verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """验证密码"""
        return self._hash_password(password, salt) == password_hash
    
    def _create_session(self, user_id: str, ip_address: Optional[str], user_agent: Optional[str]) -> str:
        """创建会话"""
        session_token = secrets.token_urlsafe(32)
        
        session = {
            'user_id': user_id,
            'created_at': datetime.datetime.now(datetime.timezone.utc),
            'expires_at': datetime.datetime.now(datetime.timezone.utc) + timedelta(seconds=self.session_timeout),
            'ip_address': ip_address,
            'user_agent': user_agent
        }
        
        self.sessions[session_token] = session
        return session_token
    
    def _validate_session(self, session_token: str) -> Dict[str, Any]:
        """验证会话"""
        if session_token not in self.sessions:
            raise AuthenticationError("Invalid session token")
        
        session = self.sessions[session_token]
        
        # 检查会话是否过期
        if datetime.datetime.now(datetime.timezone.utc) > session['expires_at']:
            del self.sessions[session_token]
            raise AuthenticationError("Session expired")
        
        return session
    
    def _check_permission(
        self,
        user: User,
        resource: str,
        permission: Permission,
        resource_type: ResourceType
    ) -> bool:
        """检查用户权限"""
        # 检查用户状态
        if not user.is_active or user.is_locked:
            return False
        
        # 检查用户角色权限
        for role_id in user.roles:
            if role_id in self.roles:
                role = self.roles[role_id]
                
                # 检查权限
                if permission in role.permissions:
                    # 检查资源模式
                    if self._match_resource_pattern(resource, role.resource_patterns):
                        return True
        
        return False
    
    def _match_resource_pattern(self, resource: str, patterns: Set[str]) -> bool:
        """匹配资源模式"""
        for pattern in patterns:
            if pattern == "*":  # 全局权限
                return True
            elif pattern.endswith("*"):  # 前缀匹配
                if resource.startswith(pattern[:-1]):
                    return True
            elif pattern == resource:  # 精确匹配
                return True
        
        return False
    
    def _log_audit(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_type: ResourceType,
        permission: Permission,
        result: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """记录审计日志"""
        log = AuditLog(
            log_id=str(uuid.uuid4()),
            user_id=user_id,
            action=action,
            resource=resource,
            resource_type=resource_type,
            permission=permission,
            result=result,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            ip_address=ip_address,
            user_agent=user_agent,
            context=context or {}
        )
        
        self.audit_logs.append(log)
        
        # 限制日志数量，保留最近的10000条
        if len(self.audit_logs) > 10000:
            self.audit_logs = self.audit_logs[-10000:]


# 装饰器支持
def require_permission(permission: Permission, resource_type: ResourceType = ResourceType.CONFIG):
    """权限检查装饰器"""
    def decorator(func):
        def wrapper(self, session_token: str, resource: str, *args, **kwargs):
            # 假设 self 有 access_control 属性
            if hasattr(self, 'access_control'):
                self.access_control.check_access(session_token, resource, permission, resource_type)
            return func(self, session_token, resource, *args, **kwargs)
        return wrapper
    return decorator


# 便利函数
def create_access_control(
    admin_username: str = "admin",
    admin_password: str = "admin123",
    session_timeout: int = 3600
) -> AccessControl:
    """
    创建访问控制系统实例
    
    Args:
        admin_username: 管理员用户名
        admin_password: 管理员密码
        session_timeout: 会话超时时间（秒）
        
    Returns:
        AccessControl: 访问控制系统实例
    """
    return AccessControl(
        admin_user=admin_username,
        admin_password=admin_password,
        session_timeout=session_timeout
    )