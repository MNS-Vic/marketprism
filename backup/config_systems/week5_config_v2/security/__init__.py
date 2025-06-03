"""
配置安全系统模块

提供企业级配置安全功能，包括：
- 配置加密/解密系统
- 细粒度访问控制
- 安全配置库
- 安全审计和威胁检测

Week 5 Day 4 实现
"""

from .config_encryption import (
    ConfigEncryption,
    EncryptionType,
    SecurityLevel,
    EncryptionConfig,
    EncryptedData,
    EncryptionKey,
    EncryptionError,
    DecryptionError,
    KeyManagementError,
    create_encryption_system,
    SimpleConfigEncryption
)

from .access_control import (
    AccessControl,
    Permission,
    ResourceType,
    User,
    Role,
    AccessRequest,
    AuditLog,
    AccessDeniedError,
    AuthenticationError,
    AuthorizationError,
    require_permission,
    create_access_control
)

from .config_vault import (
    ConfigVault,
    VaultSecurityLevel,
    VaultEntryType,
    VaultEntry,
    VaultPolicy,
    VaultAccess,
    VaultError,
    VaultAccessDeniedError,
    VaultSecurityError,
    create_config_vault
)

from .security_audit import (
    SecurityAudit,
    AuditEventType,
    SeverityLevel,
    ThreatLevel,
    ComplianceStandard,
    AuditEvent,
    SecurityRule,
    ThreatPattern,
    SecurityAlert,
    ComplianceReport,
    SecurityAuditError,
    create_security_audit
)

__all__ = [
    # 加密系统
    'ConfigEncryption',
    'EncryptionType',
    'SecurityLevel',
    'EncryptionConfig',
    'EncryptedData',
    'EncryptionKey',
    'EncryptionError',
    'DecryptionError',
    'KeyManagementError',
    'create_encryption_system',
    'SimpleConfigEncryption',
    
    # 访问控制
    'AccessControl',
    'Permission',
    'ResourceType',
    'User',
    'Role',
    'AccessRequest',
    'AuditLog',
    'AccessDeniedError',
    'AuthenticationError',
    'AuthorizationError',
    'require_permission',
    'create_access_control',
    
    # 配置保险库
    'ConfigVault',
    'VaultSecurityLevel',
    'VaultEntryType',
    'VaultEntry',
    'VaultPolicy',
    'VaultAccess',
    'VaultError',
    'VaultAccessDeniedError',
    'VaultSecurityError',
    'create_config_vault',
    
    # 安全审计
    'SecurityAudit',
    'AuditEventType',
    'SeverityLevel',
    'ThreatLevel',
    'ComplianceStandard',
    'AuditEvent',
    'SecurityRule',
    'ThreatPattern',
    'SecurityAlert',
    'ComplianceReport',
    'SecurityAuditError',
    'create_security_audit',
    
    # 集成类
    'SecurityManager'
]


class SecurityManager:
    """
    安全管理器
    
    集成所有安全组件，提供统一的安全管理接口。
    """
    
    def __init__(
        self,
        encryption_type: EncryptionType = EncryptionType.AES_256_GCM,
        admin_username: str = "admin",
        admin_password: str = "admin123",
        vault_path: str = None,
        audit_path: str = None
    ):
        # 初始化核心组件
        self.encryption = create_encryption_system(
            encryption_type=encryption_type,
            security_level=SecurityLevel.HIGH
        )
        
        self.access_control = create_access_control(
            admin_username=admin_username,
            admin_password=admin_password
        )
        
        self.vault = create_config_vault(
            encryption_type=encryption_type,
            admin_username=admin_username,
            admin_password=admin_password,
            vault_path=vault_path
        )
        
        self.audit = create_security_audit(
            storage_path=audit_path
        )
        
        # 集成审计
        self._integrate_audit_logging()
    
    def _integrate_audit_logging(self):
        """集成审计日志"""
        # 这里可以添加自动审计日志记录的逻辑
        pass
    
    def authenticate_user(self, username: str, password: str) -> str:
        """用户认证"""
        session_token = self.access_control.authenticate(username, password)
        
        # 记录审计日志
        self.audit.log_event(
            event_type=AuditEventType.AUTHENTICATION,
            user_id=username,
            resource="auth_system",
            action="login",
            result=True,
            severity=SeverityLevel.INFO
        )
        
        return session_token
    
    def store_secure_config(
        self,
        session_token: str,
        name: str,
        value: any,
        security_level: VaultSecurityLevel = VaultSecurityLevel.HIGH
    ) -> str:
        """存储安全配置"""
        # 检查权限
        self.access_control.check_access(
            session_token,
            f"vault:{name}",
            Permission.WRITE,
            ResourceType.SECURITY
        )
        
        # 存储到保险库
        entry_id = self.vault.store_secret(
            session_token=session_token,
            name=name,
            value=value,
            security_level=security_level
        )
        
        # 记录审计日志
        user_id = self.vault._get_user_from_session(session_token)
        self.audit.log_event(
            event_type=AuditEventType.VAULT_ACCESS,
            user_id=user_id,
            resource=f"vault:{name}",
            action="store",
            result=True,
            severity=SeverityLevel.MEDIUM
        )
        
        return entry_id
    
    def retrieve_secure_config(
        self,
        session_token: str,
        name: str
    ) -> any:
        """检索安全配置"""
        # 检查权限
        self.access_control.check_access(
            session_token,
            f"vault:{name}",
            Permission.READ,
            ResourceType.SECURITY
        )
        
        # 从保险库检索
        _, value = self.vault.retrieve_secret(
            session_token=session_token,
            name=name
        )
        
        # 记录审计日志
        user_id = self.vault._get_user_from_session(session_token)
        self.audit.log_event(
            event_type=AuditEventType.VAULT_ACCESS,
            user_id=user_id,
            resource=f"vault:{name}",
            action="retrieve",
            result=True,
            severity=SeverityLevel.INFO
        )
        
        return value
    
    def get_security_dashboard(self) -> dict:
        """获取安全仪表板"""
        return {
            'access_control': self.access_control.get_access_stats(),
            'vault': self.vault.get_vault_stats("system"),  # 系统级别访问
            'audit': self.audit.get_security_dashboard(),
            'encryption': self.encryption.get_encryption_stats()
        }
    
    def generate_security_report(
        self,
        standard: ComplianceStandard,
        start_date,
        end_date
    ):
        """生成安全报告"""
        return self.audit.generate_compliance_report(
            standard=standard,
            start_date=start_date,
            end_date=end_date
        )


# 便利函数
def create_security_manager(
    encryption_type: EncryptionType = EncryptionType.AES_256_GCM,
    admin_username: str = "admin",
    admin_password: str = "admin123",
    vault_path: str = None,
    audit_path: str = None
) -> SecurityManager:
    """
    创建安全管理器实例
    
    Args:
        encryption_type: 加密类型
        admin_username: 管理员用户名
        admin_password: 管理员密码
        vault_path: 保险库路径
        audit_path: 审计路径
        
    Returns:
        SecurityManager: 安全管理器实例
    """
    return SecurityManager(
        encryption_type=encryption_type,
        admin_username=admin_username,
        admin_password=admin_password,
        vault_path=vault_path,
        audit_path=audit_path
    )


# 版本信息
__version__ = "1.0.0"
__author__ = "MarketPrism Security Team"
__description__ = "Enterprise configuration security system"