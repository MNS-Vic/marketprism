"""
MarketPrism 授权中间件

这个模块实现了企业级授权中间件，支持基于角色的访问控制(RBAC)、
访问控制列表(ACL)和灵活的策略引擎。

核心功能:
1. RBAC支持：基于角色的访问控制
2. ACL支持：访问控制列表
3. 策略引擎：灵活的授权策略评估
4. 权限管理：细粒度权限控制
5. 动态授权：运行时授权决策
6. 授权上下文：完整的授权上下文管理
"""

import asyncio
import time
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Set
import threading
from datetime import datetime, timezone

from .middleware_framework import (
    BaseMiddleware, MiddlewareConfig, MiddlewareContext, MiddlewareResult,
    MiddlewareType, MiddlewarePriority
)
from .authentication_middleware import AuthenticationContext


class AuthorizationAction(Enum):
    """授权动作枚举"""
    READ = "read"                         # 读取
    WRITE = "write"                       # 写入
    DELETE = "delete"                     # 删除
    CREATE = "create"                     # 创建
    UPDATE = "update"                     # 更新
    ADMIN = "admin"                       # 管理
    EXECUTE = "execute"                   # 执行


class ResourceType(Enum):
    """资源类型枚举"""
    API = "api"                           # API资源
    DATA = "data"                         # 数据资源
    SERVICE = "service"                   # 服务资源
    SYSTEM = "system"                     # 系统资源
    USER = "user"                         # 用户资源
    ROLE = "role"                         # 角色资源
    PERMISSION = "permission"             # 权限资源


@dataclass
class Permission:
    """权限定义"""
    permission_id: str
    name: str
    description: str = ""
    resource_type: ResourceType = ResourceType.API
    actions: List[AuthorizationAction] = field(default_factory=list)
    resource_pattern: str = "*"
    conditions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches_resource(self, resource: str) -> bool:
        """检查权限是否匹配资源"""
        if self.resource_pattern == "*":
            return True

        # 支持通配符匹配
        pattern = self.resource_pattern.replace("*", ".*")
        # 如果模式不以.*结尾，添加$确保精确匹配
        if not pattern.endswith(".*"):
            pattern += "$"
        return bool(re.match(pattern, resource))
    
    def allows_action(self, action: AuthorizationAction) -> bool:
        """检查权限是否允许指定动作"""
        return action in self.actions or AuthorizationAction.ADMIN in self.actions


@dataclass
class Role:
    """角色定义"""
    role_id: str
    name: str
    description: str = ""
    permissions: List[str] = field(default_factory=list)  # 权限ID列表
    parent_roles: List[str] = field(default_factory=list)  # 父角色ID列表
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    
    def add_permission(self, permission_id: str) -> None:
        """添加权限"""
        if permission_id not in self.permissions:
            self.permissions.append(permission_id)
    
    def remove_permission(self, permission_id: str) -> bool:
        """移除权限"""
        if permission_id in self.permissions:
            self.permissions.remove(permission_id)
            return True
        return False
    
    def has_permission(self, permission_id: str) -> bool:
        """检查是否有指定权限"""
        return permission_id in self.permissions


class PermissionManager:
    """权限管理器"""
    
    def __init__(self):
        self.permissions: Dict[str, Permission] = {}
        self._lock = threading.Lock()
    
    def register_permission(self, permission: Permission) -> bool:
        """注册权限"""
        try:
            with self._lock:
                self.permissions[permission.permission_id] = permission
                return True
        except Exception:
            return False
    
    def unregister_permission(self, permission_id: str) -> bool:
        """注销权限"""
        try:
            with self._lock:
                if permission_id in self.permissions:
                    del self.permissions[permission_id]
                    return True
                return False
        except Exception:
            return False
    
    def get_permission(self, permission_id: str) -> Optional[Permission]:
        """获取权限"""
        return self.permissions.get(permission_id)
    
    def find_permissions_for_resource(self, resource: str) -> List[Permission]:
        """查找资源的权限"""
        with self._lock:
            matching_permissions = []
            for permission in self.permissions.values():
                if permission.matches_resource(resource):
                    matching_permissions.append(permission)
            return matching_permissions
    
    def list_permissions(self) -> List[Permission]:
        """列出所有权限"""
        with self._lock:
            return list(self.permissions.values())


class RoleManager:
    """角色管理器"""
    
    def __init__(self, permission_manager: PermissionManager):
        self.roles: Dict[str, Role] = {}
        self.permission_manager = permission_manager
        self._lock = threading.Lock()
    
    def register_role(self, role: Role) -> bool:
        """注册角色"""
        try:
            with self._lock:
                self.roles[role.role_id] = role
                return True
        except Exception:
            return False
    
    def unregister_role(self, role_id: str) -> bool:
        """注销角色"""
        try:
            with self._lock:
                if role_id in self.roles:
                    del self.roles[role_id]
                    return True
                return False
        except Exception:
            return False
    
    def get_role(self, role_id: str) -> Optional[Role]:
        """获取角色"""
        return self.roles.get(role_id)
    
    def get_role_permissions(self, role_id: str) -> List[Permission]:
        """获取角色的所有权限（包括继承的权限）"""
        permissions = []
        visited_roles = set()
        
        def collect_permissions(current_role_id: str):
            if current_role_id in visited_roles:
                return  # 避免循环依赖
            
            visited_roles.add(current_role_id)
            role = self.get_role(current_role_id)
            if not role:
                return
            
            # 添加直接权限
            for permission_id in role.permissions:
                permission = self.permission_manager.get_permission(permission_id)
                if permission:
                    permissions.append(permission)
            
            # 递归处理父角色
            for parent_role_id in role.parent_roles:
                collect_permissions(parent_role_id)
        
        collect_permissions(role_id)
        return permissions
    
    def list_roles(self) -> List[Role]:
        """列出所有角色"""
        with self._lock:
            return list(self.roles.values())


@dataclass
class ACLEntry:
    """访问控制列表条目"""
    subject: str                          # 主体（用户ID、角色等）
    resource: str                         # 资源
    action: AuthorizationAction           # 动作
    effect: str = "allow"                 # 效果：allow/deny
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, subject: str, resource: str, action: AuthorizationAction) -> bool:
        """检查ACL条目是否匹配"""
        return (self.subject == subject and 
                self.resource == resource and 
                self.action == action)


@dataclass
class ACLConfig:
    """访问控制列表配置"""
    default_effect: str = "deny"         # 默认效果
    explicit_deny: bool = True           # 显式拒绝优先
    evaluation_order: str = "deny_first" # 评估顺序


class AccessControlList:
    """访问控制列表"""
    
    def __init__(self, config: ACLConfig):
        self.config = config
        self.entries: List[ACLEntry] = []
        self._lock = threading.Lock()
    
    def add_entry(self, entry: ACLEntry) -> bool:
        """添加ACL条目"""
        try:
            with self._lock:
                self.entries.append(entry)
                return True
        except Exception:
            return False
    
    def remove_entry(self, subject: str, resource: str, action: AuthorizationAction) -> bool:
        """移除ACL条目"""
        try:
            with self._lock:
                for entry in self.entries[:]:
                    if entry.matches(subject, resource, action):
                        self.entries.remove(entry)
                        return True
                return False
        except Exception:
            return False
    
    def evaluate(self, subject: str, resource: str, action: AuthorizationAction) -> bool:
        """评估访问控制"""
        with self._lock:
            allow_entries = []
            deny_entries = []
            
            # 分类匹配的条目
            for entry in self.entries:
                if entry.matches(subject, resource, action):
                    if entry.effect == "allow":
                        allow_entries.append(entry)
                    elif entry.effect == "deny":
                        deny_entries.append(entry)
            
            # 根据配置评估
            if self.config.evaluation_order == "deny_first":
                # 拒绝优先
                if deny_entries:
                    return False
                if allow_entries:
                    return True
            else:
                # 允许优先
                if allow_entries:
                    return True
                if deny_entries:
                    return False
            
            # 使用默认效果
            return self.config.default_effect == "allow"


@dataclass
class AuthorizationPolicy:
    """授权策略"""
    policy_id: str
    name: str
    description: str = ""
    rules: List[Dict[str, Any]] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)
    effect: str = "allow"
    priority: int = 0
    
    def evaluate_conditions(self, context: Dict[str, Any]) -> bool:
        """评估策略条件"""
        for key, expected_value in self.conditions.items():
            actual_value = context.get(key)
            if actual_value != expected_value:
                return False
        return True


class PolicyEngine:
    """策略引擎"""
    
    def __init__(self):
        self.policies: Dict[str, AuthorizationPolicy] = {}
        self._lock = threading.Lock()
    
    def register_policy(self, policy: AuthorizationPolicy) -> bool:
        """注册策略"""
        try:
            with self._lock:
                self.policies[policy.policy_id] = policy
                return True
        except Exception:
            return False
    
    def unregister_policy(self, policy_id: str) -> bool:
        """注销策略"""
        try:
            with self._lock:
                if policy_id in self.policies:
                    del self.policies[policy_id]
                    return True
                return False
        except Exception:
            return False
    
    def evaluate_policies(self, context: Dict[str, Any]) -> bool:
        """评估所有策略"""
        with self._lock:
            # 按优先级排序
            sorted_policies = sorted(self.policies.values(), key=lambda p: p.priority, reverse=True)
            
            for policy in sorted_policies:
                if policy.evaluate_conditions(context):
                    return policy.effect == "allow"
            
            return False  # 默认拒绝


class PolicyEvaluator:
    """策略评估器"""
    
    def __init__(self, policy_engine: PolicyEngine):
        self.policy_engine = policy_engine
    
    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """异步评估策略"""
        return self.policy_engine.evaluate_policies(context)


@dataclass
class AuthorizationContext:
    """授权上下文"""
    user_id: str
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    resource: str = ""
    action: AuthorizationAction = AuthorizationAction.READ
    request_context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)


@dataclass
class AuthorizationResult:
    """授权结果"""
    allowed: bool
    reason: str = ""
    applied_policies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def allow(cls, reason: str = "", **kwargs) -> 'AuthorizationResult':
        """创建允许结果"""
        return cls(allowed=True, reason=reason, **kwargs)
    
    @classmethod
    def deny(cls, reason: str = "", **kwargs) -> 'AuthorizationResult':
        """创建拒绝结果"""
        return cls(allowed=False, reason=reason, **kwargs)


@dataclass
class RBACConfig:
    """RBAC配置"""
    strict_mode: bool = True              # 严格模式
    inheritance_enabled: bool = True      # 权限继承
    cache_enabled: bool = True            # 缓存启用
    cache_ttl: int = 300                  # 缓存TTL（秒）


@dataclass
class AuthorizationConfig:
    """授权中间件配置"""
    enabled: bool = True
    enforcement_mode: str = "strict"      # strict/permissive
    default_action: str = "deny"          # allow/deny
    rbac_config: Optional[RBACConfig] = None
    acl_config: Optional[ACLConfig] = None
    skip_paths: List[str] = field(default_factory=list)
    admin_paths: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuthorizationMiddleware(BaseMiddleware):
    """授权中间件"""
    
    def __init__(self, config: MiddlewareConfig, auth_config: AuthorizationConfig):
        super().__init__(config)
        self.auth_config = auth_config
        self.permission_manager = PermissionManager()
        self.role_manager = RoleManager(self.permission_manager)
        self.policy_engine = PolicyEngine()
        self.policy_evaluator = PolicyEvaluator(self.policy_engine)
        self.acl = AccessControlList(auth_config.acl_config or ACLConfig())
        self._setup_default_permissions()
    
    def _setup_default_permissions(self) -> None:
        """设置默认权限"""
        # 默认API权限
        read_permission = Permission(
            permission_id="api_read",
            name="API Read",
            description="Read access to API resources",
            resource_type=ResourceType.API,
            actions=[AuthorizationAction.READ],
            resource_pattern="/api/*"
        )
        
        write_permission = Permission(
            permission_id="api_write",
            name="API Write",
            description="Write access to API resources",
            resource_type=ResourceType.API,
            actions=[AuthorizationAction.WRITE, AuthorizationAction.CREATE, AuthorizationAction.UPDATE],
            resource_pattern="/api/*"
        )
        
        admin_permission = Permission(
            permission_id="api_admin",
            name="API Admin",
            description="Full access to API resources",
            resource_type=ResourceType.API,
            actions=[AuthorizationAction.ADMIN],
            resource_pattern="*"
        )
        
        self.permission_manager.register_permission(read_permission)
        self.permission_manager.register_permission(write_permission)
        self.permission_manager.register_permission(admin_permission)
        
        # 默认角色
        user_role = Role(
            role_id="user",
            name="User",
            description="Standard user role",
            permissions=["api_read"]
        )
        
        admin_role = Role(
            role_id="admin",
            name="Administrator",
            description="Administrator role",
            permissions=["api_admin"]
        )
        
        self.role_manager.register_role(user_role)
        self.role_manager.register_role(admin_role)
    
    def _should_skip_authorization(self, path: str) -> bool:
        """检查是否应该跳过授权"""
        for skip_path in self.auth_config.skip_paths:
            if path.startswith(skip_path):
                return True
        return False
    
    def _requires_admin(self, path: str) -> bool:
        """检查是否需要管理员权限"""
        for admin_path in self.auth_config.admin_paths:
            if path.startswith(admin_path):
                return True
        return False
    
    def _extract_action_from_method(self, method: str) -> AuthorizationAction:
        """从HTTP方法提取动作"""
        method_map = {
            'GET': AuthorizationAction.READ,
            'POST': AuthorizationAction.CREATE,
            'PUT': AuthorizationAction.UPDATE,
            'PATCH': AuthorizationAction.UPDATE,
            'DELETE': AuthorizationAction.DELETE,
        }
        return method_map.get(method.upper(), AuthorizationAction.READ)
    
    async def _evaluate_rbac(self, auth_context: AuthorizationContext) -> AuthorizationResult:
        """评估RBAC授权"""
        try:
            # 检查管理员权限
            if "admin" in auth_context.roles:
                return AuthorizationResult.allow("Administrator access")
            
            # 收集用户的所有权限
            user_permissions = set()
            for role_id in auth_context.roles:
                role_permissions = self.role_manager.get_role_permissions(role_id)
                for permission in role_permissions:
                    if permission.matches_resource(auth_context.resource):
                        if permission.allows_action(auth_context.action):
                            user_permissions.add(permission.permission_id)
            
            # 检查是否有匹配的权限
            if user_permissions:
                return AuthorizationResult.allow(
                    f"RBAC access granted via permissions: {', '.join(user_permissions)}",
                    applied_policies=list(user_permissions)
                )
            
            return AuthorizationResult.deny("No matching RBAC permissions found")
            
        except Exception as e:
            return AuthorizationResult.deny(f"RBAC evaluation error: {str(e)}")
    
    async def _evaluate_acl(self, auth_context: AuthorizationContext) -> AuthorizationResult:
        """评估ACL授权"""
        try:
            # 评估用户ID
            if self.acl.evaluate(auth_context.user_id, auth_context.resource, auth_context.action):
                return AuthorizationResult.allow("ACL access granted for user")
            
            # 评估角色
            for role in auth_context.roles:
                if self.acl.evaluate(role, auth_context.resource, auth_context.action):
                    return AuthorizationResult.allow(f"ACL access granted for role: {role}")
            
            return AuthorizationResult.deny("ACL access denied")
            
        except Exception as e:
            return AuthorizationResult.deny(f"ACL evaluation error: {str(e)}")
    
    async def _evaluate_policies(self, auth_context: AuthorizationContext) -> AuthorizationResult:
        """评估策略授权"""
        try:
            policy_context = {
                'user_id': auth_context.user_id,
                'roles': auth_context.roles,
                'resource': auth_context.resource,
                'action': auth_context.action.value,
                **auth_context.request_context
            }
            
            allowed = await self.policy_evaluator.evaluate(policy_context)
            if allowed:
                return AuthorizationResult.allow("Policy access granted")
            else:
                return AuthorizationResult.deny("Policy access denied")
                
        except Exception as e:
            return AuthorizationResult.deny(f"Policy evaluation error: {str(e)}")
    
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理授权请求"""
        try:
            # 检查是否跳过授权
            if self._should_skip_authorization(context.request.path):
                context.set_data('authorization_skipped', True)
                return MiddlewareResult.success_result()
            
            # 获取认证上下文
            auth_context_data = context.get_data('authentication_context')
            if not auth_context_data or not auth_context_data.is_authenticated:
                if self.auth_config.default_action == "allow":
                    return MiddlewareResult.success_result()
                else:
                    return MiddlewareResult.stop_result(
                        status_code=401,
                        body=b'{"error": "Authentication required for authorization"}'
                    )
            
            # 创建授权上下文
            action = self._extract_action_from_method(context.request.method)
            auth_context = AuthorizationContext(
                user_id=auth_context_data.user_id,
                roles=auth_context_data.roles,
                permissions=auth_context_data.permissions,
                resource=context.request.path,
                action=action,
                request_context={
                    'method': context.request.method,
                    'headers': context.request.headers.to_dict(),
                    'remote_addr': context.request.remote_addr,
                    'user_agent': context.request.user_agent,
                }
            )
            
            # 检查管理员路径
            if self._requires_admin(context.request.path):
                if "admin" not in auth_context.roles:
                    return MiddlewareResult.stop_result(
                        status_code=403,
                        body=b'{"error": "Administrator access required"}'
                    )
            
            # 评估授权
            auth_result = None
            
            # 1. 评估RBAC
            if self.auth_config.rbac_config:
                auth_result = await self._evaluate_rbac(auth_context)
                if auth_result.allowed:
                    context.set_data('authorization_result', auth_result)
                    context.set_data('authorization_method', 'rbac')
                    return MiddlewareResult.success_result()
            
            # 2. 评估ACL
            if self.auth_config.acl_config:
                auth_result = await self._evaluate_acl(auth_context)
                if auth_result.allowed:
                    context.set_data('authorization_result', auth_result)
                    context.set_data('authorization_method', 'acl')
                    return MiddlewareResult.success_result()
            
            # 3. 评估策略
            auth_result = await self._evaluate_policies(auth_context)
            if auth_result.allowed:
                context.set_data('authorization_result', auth_result)
                context.set_data('authorization_method', 'policy')
                return MiddlewareResult.success_result()
            
            # 授权失败
            context.set_data('authorization_result', auth_result)
            
            if self.auth_config.enforcement_mode == "permissive":
                # 宽松模式，记录但不阻止
                context.add_error(Exception(f"Authorization denied (permissive): {auth_result.reason}"))
                return MiddlewareResult.success_result()
            else:
                # 严格模式，阻止访问
                return MiddlewareResult.stop_result(
                    status_code=403,
                    body=f'{{"error": "Access denied", "reason": "{auth_result.reason}"}}'.encode()
                )
            
        except Exception as e:
            context.add_error(e)
            if self.auth_config.enforcement_mode == "permissive":
                return MiddlewareResult.success_result()
            else:
                return MiddlewareResult.error_result(e)
    
    def get_permission_manager(self) -> PermissionManager:
        """获取权限管理器"""
        return self.permission_manager
    
    def get_role_manager(self) -> RoleManager:
        """获取角色管理器"""
        return self.role_manager
    
    def get_policy_engine(self) -> PolicyEngine:
        """获取策略引擎"""
        return self.policy_engine
    
    def get_acl(self) -> AccessControlList:
        """获取访问控制列表"""
        return self.acl
    
    def get_authorization_result(self, context: MiddlewareContext) -> Optional[AuthorizationResult]:
        """获取授权结果"""
        return context.get_data('authorization_result')
    
    def is_authorized(self, context: MiddlewareContext) -> bool:
        """检查是否已授权"""
        result = self.get_authorization_result(context)
        return result is not None and result.allowed


# 授权异常类
class AuthorizationError(Exception):
    """授权基础异常"""
    pass


class InsufficientPermissionsError(AuthorizationError):
    """权限不足异常"""
    pass


class RoleNotFoundError(AuthorizationError):
    """角色未找到异常"""
    pass


class PolicyViolationError(AuthorizationError):
    """策略违反异常"""
    pass