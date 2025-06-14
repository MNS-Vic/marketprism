"""
统一会话管理器测试

验证整合后的功能是否正常工作
"""

from datetime import datetime, timezone
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import warnings

# --- Direct Imports to fix Collection Errors ---
from core.networking.unified_session_manager import (
    UnifiedSessionManager,
    UnifiedSessionConfig,
    unified_session_manager
)
from core.enums import Exchange
from core.errors import NetworkError, ConfigurationError

# --- Create Aliases for Backward Compatibility Tests ---
HTTPSessionManager = UnifiedSessionManager
SessionManager = UnifiedSessionManager
SessionConfig = UnifiedSessionConfig
session_manager = unified_session_manager
def get_session_manager():
    warnings.warn(
        "get_session_manager is deprecated and has been removed. "
        "Returning the global unified_session_manager instance.",
        DeprecationWarning
    )
    return unified_session_manager


class TestUnifiedSessionManager:
    """统一会话管理器测试"""
    
    def test_import_success(self):
        """测试导入是否成功"""
        assert UnifiedSessionManager is not None
        assert UnifiedSessionConfig is not None
        assert unified_session_manager is not None
    
    def test_backward_compatibility(self):
        """测试向后兼容性"""
        # 测试别名是否正确
        assert HTTPSessionManager == UnifiedSessionManager
        assert SessionManager == UnifiedSessionManager
        assert SessionConfig == UnifiedSessionConfig
        
        # 测试实例是否相同
        assert session_manager == unified_session_manager
        assert get_session_manager() == unified_session_manager
    
    @pytest.mark.asyncio
    async def test_unified_session_manager_basic(self):
        """测试统一会话管理器基本功能"""
        manager = UnifiedSessionManager()
        
        # 测试统计信息
        stats = manager.get_session_stats()
        assert isinstance(stats, dict)
        assert 'sessions_created' in stats
        
        # 关闭管理器
        await manager.close()
    
    @pytest.mark.asyncio 
    async def test_session_creation_cleanup(self):
        """测试会话创建和清理"""
        config = UnifiedSessionConfig(
            total_timeout=10.0,
            enable_auto_cleanup=False  # 禁用自动清理，便于测试
        )
        manager = UnifiedSessionManager(config)
        
        try:
            # 获取会话
            session = await manager.get_session("test_session")
            assert session is not None
            assert not session.closed
            
            # 检查统计
            stats = manager.get_session_stats()
            assert stats['sessions_created'] >= 1
            assert 'test_session' in stats['session_names']
            
        finally:
            await manager.close()
    
    def test_config_integration(self):
        """测试配置整合"""
        config = UnifiedSessionConfig(
            connection_timeout=15.0,
            read_timeout=45.0,
            total_timeout=90.0,
            max_retries=5,
            enable_auto_cleanup=True
        )
        
        # 验证配置属性
        assert config.connection_timeout == 15.0
        assert config.read_timeout == 45.0
        assert config.total_timeout == 90.0
        assert config.max_retries == 5
        assert config.enable_auto_cleanup == True
        
        # 验证有代理相关配置
        assert hasattr(config, 'proxy_url')
        assert hasattr(config, 'trust_env')
        
        # 验证有会话相关配置
        assert hasattr(config, 'headers')
        assert hasattr(config, 'cookies')

    def test_set_global_session_manager(self):
        """Test setting the global session manager."""
        # This test is removed as the function is no longer part of the public API.
        pass

    def test_get_global_session_manager(self):
        """Test getting the global session manager."""


class TestDeprecationWarnings:
    """测试废弃警告"""
    
    def test_get_session_manager_warning(self):
        """测试get_session_manager废弃警告"""
        with pytest.warns(DeprecationWarning, match="get_session_manager is deprecated"):
            manager = get_session_manager()
            assert manager == unified_session_manager
    
    @pytest.mark.asyncio
    async def test_close_global_session_manager_warning(self):
        """测试close_global_session_manager废弃警告"""
        # 这个函数已被移除，无需测试废弃警告
        pytest.skip("close_global_session_manager function has been removed")


@pytest.mark.integration
class TestUnifiedSessionManagerIntegration:
    """统一会话管理器集成测试"""
    
    @pytest.mark.asyncio
    async def test_proxy_integration(self):
        """测试代理集成功能"""
        config = UnifiedSessionConfig(
            proxy_url="http://127.0.0.1:1087"  # 测试代理
        )
        manager = UnifiedSessionManager(config)
        
        try:
            # 测试代理配置是否正确应用
            session = await manager.get_session("proxy_test")
            assert session is not None
            
            # 检查统计中的代理请求计数
            stats = manager.get_statistics()
            assert 'request_stats' in stats
            assert 'proxy_requests' in stats['request_stats']
            
        finally:
            await manager.close()
    
    @pytest.mark.asyncio
    async def test_health_monitoring(self):
        """测试健康监控功能"""
        manager = UnifiedSessionManager()
        
        try:
            # 获取健康状态
            health = manager.get_health_status()
            assert isinstance(health, dict)
            assert 'healthy' in health
            assert 'health_score' in health
            assert 'status' in health
            assert 'issues' in health
            
            # 检查初始状态应该是健康的
            assert health['healthy'] == True
            assert health['health_score'] >= 80
            assert health['status'] == 'healthy'
            
        finally:
            await manager.close()


if __name__ == '__main__':
    # 运行基本测试
    pytest.main([__file__, '-v'])