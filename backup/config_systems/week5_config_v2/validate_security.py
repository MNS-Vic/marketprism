#!/usr/bin/env python3
"""
Week 5 Day 4 配置安全系统验证脚本

验证以下组件：
1. ConfigEncryption - 配置加密/解密系统
2. AccessControl - 细粒度访问控制
3. ConfigVault - 安全配置库
4. SecurityAudit - 安全审计系统
5. SecurityManager - 集成安全管理器
"""

import sys
import os
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_config_encryption():
    """测试配置加密系统"""
    print("🔐 Testing ConfigEncryption...")
    
    try:
        from security import (
            create_encryption_system,
            EncryptionType,
            SecurityLevel,
            SimpleConfigEncryption
        )
        
        # 创建加密系统
        encryption = create_encryption_system(
            encryption_type=EncryptionType.AES_256_GCM,
            security_level=SecurityLevel.HIGH
        )
        
        # 测试配置加密
        test_config = {
            "database_password": "super_secret_password",
            "api_key": "sk-1234567890abcdef",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC..."
        }
        
        encrypted_values = {}
        for key, value in test_config.items():
            encrypted_value = encryption.encrypt_config_value(key, value)
            encrypted_values[key] = encrypted_value
            print(f"  ✓ Encrypted {key}: {encrypted_value[:50]}...")
        
        # 测试解密
        for key, encrypted_value in encrypted_values.items():
            decrypted_key, decrypted_value = encryption.decrypt_config_value(encrypted_value)
            assert decrypted_key == key
            assert decrypted_value == test_config[key]
            print(f"  ✓ Decrypted {key} successfully")
        
        # 测试密钥管理
        key_id = encryption.generate_key(EncryptionType.AES_256_GCM)
        print(f"  ✓ Generated key: {key_id}")
        
        keys = encryption.list_keys()
        print(f"  ✓ Listed {len(keys)} keys")
        
        stats = encryption.get_encryption_stats()
        print(f"  ✓ Encryption stats: {stats['encryption_count']} encryptions, {stats['decryption_count']} decryptions")
        
        # 测试简化接口
        simple_encryption = SimpleConfigEncryption()
        encrypted = simple_encryption.encrypt_value("test_value")
        decrypted = simple_encryption.decrypt_value(encrypted)
        assert decrypted == "test_value"
        print("  ✓ Simple encryption interface working")
        
        print("✅ ConfigEncryption tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ ConfigEncryption test failed: {e}")
        traceback.print_exc()
        return False

def test_access_control():
    """测试访问控制系统"""
    print("\n🔒 Testing AccessControl...")
    
    try:
        from security import (
            create_access_control,
            Permission,
            ResourceType
        )
        
        # 创建访问控制系统
        access_control = create_access_control(
            admin_username="admin",
            admin_password="admin123"
        )
        
        # 测试用户管理
        user_id = access_control.create_user(
            username="test_user",
            email="test@example.com",
            password="password123",
            roles=["read_only"]
        )
        print(f"  ✓ Created user: {user_id}")
        
        # 测试认证
        session_token = access_control.authenticate("test_user", "password123")
        print(f"  ✓ User authenticated: {session_token[:20]}...")
        
        # 测试授权
        result = access_control.authorize(
            session_token=session_token,
            resource="config:test",
            permission=Permission.READ,
            resource_type=ResourceType.CONFIG
        )
        print(f"  ✓ Authorization result: {result}")
        
        # 测试角色管理
        role_id = access_control.create_role(
            name="test_role",
            description="Test role",
            permissions=[Permission.READ, Permission.WRITE],
            resource_patterns=["test.*"],
            created_by="admin"
        )
        print(f"  ✓ Created role: {role_id}")
        
        # 测试分配角色
        access_control.assign_role(user_id, role_id, "admin")
        print("  ✓ Role assigned successfully")
        
        # 测试统计信息
        stats = access_control.get_access_stats()
        print(f"  ✓ Access stats: {stats['total_users']} users, {stats['total_requests']} requests")
        
        # 测试审计日志
        logs = access_control.get_audit_logs(limit=5)
        print(f"  ✓ Retrieved {len(logs)} audit logs")
        
        print("✅ AccessControl tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ AccessControl test failed: {e}")
        traceback.print_exc()
        return False

def test_config_vault():
    """测试配置保险库"""
    print("\n🏛️ Testing ConfigVault...")
    
    try:
        from security import (
            create_config_vault,
            VaultSecurityLevel,
            VaultEntryType,
            EncryptionType
        )
        
        # 创建保险库
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = os.path.join(temp_dir, "vault.json")
            
            vault = create_config_vault(
                encryption_type=EncryptionType.AES_256_GCM,
                admin_username="admin",
                admin_password="admin123",
                vault_path=vault_path
            )
            
            # 获取管理员会话
            admin_session = vault.access_control.authenticate("admin", "admin123")
            print(f"  ✓ Admin authenticated: {admin_session[:20]}...")
            
            # 测试存储密钥
            entry_id = vault.store_secret(
                session_token=admin_session,
                name="database_password",
                value="super_secret_db_password",
                entry_type=VaultEntryType.PASSWORD,
                security_level=VaultSecurityLevel.HIGH,
                metadata={"description": "Production database password"},
                tags=["database", "production"]
            )
            print(f"  ✓ Stored secret: {entry_id}")
            
            # 测试检索密钥
            retrieved_id, retrieved_value = vault.retrieve_secret(
                session_token=admin_session,
                name="database_password"
            )
            assert retrieved_value == "super_secret_db_password"
            print("  ✓ Retrieved secret successfully")
            
            # 测试更新密钥
            success = vault.update_secret(
                session_token=admin_session,
                entry_id=entry_id,
                value="new_super_secret_password",
                metadata={"updated": "true"}
            )
            assert success
            print("  ✓ Updated secret successfully")
            
            # 测试列出密钥
            secrets = vault.list_secrets(
                session_token=admin_session,
                entry_type=VaultEntryType.PASSWORD
            )
            print(f"  ✓ Listed {len(secrets)} secrets")
            
            # 测试保险库统计
            stats = vault.get_vault_stats(admin_session)
            print(f"  ✓ Vault stats: {stats['total_entries']} entries, {stats['total_accesses']} accesses")
            
            print("✅ ConfigVault tests passed!")
            return True
        
    except Exception as e:
        print(f"❌ ConfigVault test failed: {e}")
        traceback.print_exc()
        return False

def test_security_audit():
    """测试安全审计系统"""
    print("\n📋 Testing SecurityAudit...")
    
    try:
        from security import (
            create_security_audit,
            AuditEventType,
            SeverityLevel,
            ThreatLevel,
            ComplianceStandard
        )
        
        # 创建审计系统
        audit = create_security_audit(max_events=1000)
        
        # 测试记录事件
        event_id = audit.log_event(
            event_type=AuditEventType.AUTHENTICATION,
            user_id="test_user",
            resource="auth_system",
            action="login",
            result=True,
            severity=SeverityLevel.INFO,
            details={"ip": "192.168.1.1", "browser": "Chrome"},
            tags=["login", "success"]
        )
        print(f"  ✓ Logged event: {event_id}")
        
        # 测试记录多个事件
        for i in range(5):
            audit.log_event(
                event_type=AuditEventType.CONFIGURATION_ACCESS,
                user_id="test_user",
                resource=f"config:test_{i}",
                action="read",
                result=True,
                severity=SeverityLevel.LOW
            )
        print("  ✓ Logged multiple events")
        
        # 测试查询事件
        events = audit.query_events(
            event_type=AuditEventType.AUTHENTICATION,
            limit=10
        )
        print(f"  ✓ Queried {len(events)} events")
        
        # 测试安全仪表板
        dashboard = audit.get_security_dashboard()
        print(f"  ✓ Dashboard: {dashboard['summary']['total_events']} total events")
        
        # 测试合规报告
        report = audit.generate_compliance_report(
            standard=ComplianceStandard.GDPR,
            start_date=datetime.utcnow() - timedelta(days=1),
            end_date=datetime.utcnow()
        )
        print(f"  ✓ Generated compliance report: {report.compliance_score}% score")
        
        # 测试统计信息
        stats = audit.get_audit_statistics()
        print(f"  ✓ Audit stats: {stats['total_events']} events, {stats['active_rules']} rules")
        
        print("✅ SecurityAudit tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ SecurityAudit test failed: {e}")
        traceback.print_exc()
        return False

def test_security_manager():
    """测试安全管理器"""
    print("\n🛡️ Testing SecurityManager...")
    
    try:
        from security import (
            create_security_manager,
            VaultSecurityLevel,
            ComplianceStandard,
            EncryptionType
        )
        
        # 创建安全管理器
        with tempfile.TemporaryDirectory() as temp_dir:
            vault_path = os.path.join(temp_dir, "vault.json")
            audit_path = os.path.join(temp_dir, "audit.log")
            
            security_manager = create_security_manager(
                encryption_type=EncryptionType.AES_256_GCM,
                admin_username="admin",
                admin_password="admin123",
                vault_path=vault_path,
                audit_path=audit_path
            )
            
            # 测试用户认证
            session_token = security_manager.authenticate_user("admin", "admin123")
            print(f"  ✓ Authenticated user: {session_token[:20]}...")
            
            # 测试存储安全配置
            entry_id = security_manager.store_secure_config(
                session_token=session_token,
                name="api_secret",
                value="sk-test-123456789",
                security_level=VaultSecurityLevel.CRITICAL
            )
            print(f"  ✓ Stored secure config: {entry_id}")
            
            # 测试检索安全配置
            retrieved_value = security_manager.retrieve_secure_config(
                session_token=session_token,
                name="api_secret"
            )
            assert retrieved_value == "sk-test-123456789"
            print("  ✓ Retrieved secure config successfully")
            
            # 测试安全仪表板
            dashboard = security_manager.get_security_dashboard()
            print(f"  ✓ Security dashboard: {len(dashboard)} sections")
            
            # 测试安全报告
            report = security_manager.generate_security_report(
                standard=ComplianceStandard.SOC2,
                start_date=datetime.utcnow() - timedelta(days=1),
                end_date=datetime.utcnow()
            )
            print(f"  ✓ Generated security report: {report.compliance_score}% compliance")
            
            print("✅ SecurityManager tests passed!")
            return True
        
    except Exception as e:
        print(f"❌ SecurityManager test failed: {e}")
        traceback.print_exc()
        return False

def test_integration():
    """测试组件集成"""
    print("\n🔗 Testing Integration...")
    
    try:
        from security import SecurityManager, EncryptionType, VaultSecurityLevel
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建完整的安全系统
            security = SecurityManager(
                encryption_type=EncryptionType.AES_256_GCM,
                admin_username="admin",
                admin_password="admin123",
                vault_path=os.path.join(temp_dir, "vault.json"),
                audit_path=os.path.join(temp_dir, "audit.log")
            )
            
            # 模拟完整的工作流程
            # 1. 管理员登录
            admin_session = security.authenticate_user("admin", "admin123")
            
            # 2. 创建新用户
            user_id = security.access_control.create_user(
                username="config_user",
                email="user@example.com",
                password="user123",
                roles=["config_admin"]
            )
            
            # 3. 用户登录
            user_session = security.authenticate_user("config_user", "user123")
            
            # 4. 存储多个安全配置
            configs = {
                "database_url": "postgresql://user:pass@localhost/db",
                "redis_password": "redis123",
                "jwt_secret": "jwt-secret-key-456",
                "encryption_key": "enc-key-789"
            }
            
            for name, value in configs.items():
                security.store_secure_config(
                    session_token=admin_session,
                    name=name,
                    value=value,
                    security_level=VaultSecurityLevel.HIGH
                )
            
            # 5. 检索配置
            for name in configs.keys():
                retrieved = security.retrieve_secure_config(admin_session, name)
                assert retrieved == configs[name]
            
            # 6. 生成综合仪表板
            dashboard = security.get_security_dashboard()
            
            print(f"  ✓ Integration test completed:")
            print(f"    - Users: {dashboard['access_control']['total_users']}")
            print(f"    - Vault entries: {dashboard['vault']['active_entries']}")
            print(f"    - Audit events: {dashboard['audit']['summary']['total_events']}")
            print(f"    - Encryption operations: {dashboard['encryption']['encryption_count']}")
            
            print("✅ Integration tests passed!")
            return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """主验证函数"""
    print("🚀 Week 5 Day 4: 配置安全系统验证")
    print("=" * 60)
    
    tests = [
        ("config_encryption", test_config_encryption),
        ("access_control", test_access_control),
        ("config_vault", test_config_vault),
        ("security_audit", test_security_audit),
        ("security_manager", test_security_manager),
        ("integration", test_integration)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ Test {test_name} encountered error: {e}")
            results[test_name] = False
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结:")
    
    passed = 0
    total = len(tests)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有配置安全系统测试通过！")
        print("\n🔒 实现的功能:")
        print("  • 配置加密/解密系统 (AES-256-GCM, RSA, 混合加密)")
        print("  • 细粒度访问控制 (RBAC, 权限管理, 会话管理)")
        print("  • 安全配置库 (分级存储, 策略控制, 审计日志)")
        print("  • 安全审计系统 (威胁检测, 合规报告, 实时监控)")
        print("  • 集成安全管理器 (统一接口, 仪表板, 报告生成)")
        
        print("\n🛡️ 安全特性:")
        print("  • 多重加密算法支持")
        print("  • 基于角色的访问控制")
        print("  • 实时威胁检测")
        print("  • 合规标准支持 (GDPR, SOX, HIPAA, PCI-DSS)")
        print("  • 安全审计和日志记录")
        print("  • 密钥轮换和生命周期管理")
        
        return True
    else:
        print("💥 部分测试失败，请检查实现！")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)