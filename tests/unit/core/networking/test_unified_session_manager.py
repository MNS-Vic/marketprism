"""
统一会话管理器测试
测试UnifiedSessionManager的核心功能
"""

import pytest
import asyncio
import aiohttp
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

# 导入被测试的模块
try:
    from core.networking.unified_session_manager import (
        UnifiedSessionManager,
        UnifiedSessionConfig
    )
    from core.networking.proxy_manager import ProxyConfig
    HAS_NETWORKING_MODULES = True
except ImportError as e:
    HAS_NETWORKING_MODULES = False
    pytest.skip(f"网络模块导入失败: {e}", allow_module_level=True)


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerInitialization:
    """统一会话管理器初始化测试"""
    
    def test_session_manager_initialization_default(self):
        """测试使用默认配置初始化会话管理器"""
        session_manager = UnifiedSessionManager()
        
        assert session_manager is not None
        assert hasattr(session_manager, 'config')
        assert hasattr(session_manager, '_sessions')
        assert hasattr(session_manager, '_session_configs')
        assert hasattr(session_manager, 'stats')
        assert session_manager._closed is False
        
    def test_session_manager_initialization_with_config(self):
        """测试使用自定义配置初始化会话管理器"""
        config = UnifiedSessionConfig(
            connector_limit=200,
            connector_limit_per_host=50,
            total_timeout=60.0,
            connection_timeout=15.0
        )
        
        session_manager = UnifiedSessionManager(config)
        
        assert session_manager.config == config
        assert session_manager.config.connector_limit == 200
        assert session_manager.config.connector_limit_per_host == 50
        assert session_manager.config.total_timeout == 60.0
        
    def test_session_manager_has_required_attributes(self):
        """测试会话管理器具有必需的属性"""
        session_manager = UnifiedSessionManager()
        
        required_attributes = [
            'config', '_sessions', '_session_configs', 'stats',
            '_closed', '_cleanup_task', '_last_cleanup'
        ]
        
        for attr in required_attributes:
            assert hasattr(session_manager, attr), f"缺少必需属性: {attr}"
            
    def test_session_manager_stats_initialization(self):
        """测试统计信息初始化"""
        session_manager = UnifiedSessionManager()
        
        expected_stats = [
            'sessions_created', 'sessions_closed', 'requests_made',
            'proxy_requests', 'direct_requests', 'cleanup_runs'
        ]
        
        for stat in expected_stats:
            assert stat in session_manager.stats
            assert session_manager.stats[stat] == 0


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerSessionManagement:
    """统一会话管理器会话管理测试"""
    
    @pytest.fixture
    def session_manager(self):
        """创建测试用的会话管理器"""
        return UnifiedSessionManager()
        
    async def test_session_manager_get_session_default(self, session_manager):
        """测试获取默认会话"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            session = await session_manager.get_session()
            
            assert session is not None
            assert "default" in session_manager._sessions
            assert session_manager.stats['sessions_created'] == 1
            
    async def test_session_manager_get_session_named(self, session_manager):
        """测试获取命名会话"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            session = await session_manager.get_session("test_session")
            
            assert session is not None
            assert "test_session" in session_manager._sessions
            assert session_manager.stats['sessions_created'] == 1
            
    async def test_session_manager_session_reuse(self, session_manager):
        """测试会话复用"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            # 第一次获取
            session1 = await session_manager.get_session("reuse_test")
            
            # 第二次获取同名会话
            session2 = await session_manager.get_session("reuse_test")
            
            assert session1 is session2
            assert session_manager.stats['sessions_created'] == 1  # 只创建一次
            
    async def test_session_manager_with_custom_config(self, session_manager):
        """测试使用自定义配置创建会话"""
        custom_config = UnifiedSessionConfig(
            connector_limit=100,
            total_timeout=30.0
        )
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            session = await session_manager.get_session(
                "custom_config_session",
                config=custom_config
            )
            
            assert session is not None
            assert "custom_config_session" in session_manager._session_configs
            
    async def test_session_manager_with_proxy_config(self, session_manager):
        """测试使用代理配置创建会话"""
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080"
        )
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            session = await session_manager.get_session(
                "proxy_session",
                proxy_config=proxy_config
            )
            
            assert session is not None
            assert "proxy_session" in session_manager._sessions


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerRequests:
    """统一会话管理器请求测试"""
    
    @pytest.fixture
    def session_manager_with_mock_session(self):
        """创建带模拟会话的会话管理器"""
        session_manager = UnifiedSessionManager()
        
        # 创建模拟会话
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"success": true}')
        mock_session.request.return_value = mock_response
        
        session_manager._sessions["test"] = mock_session
        
        return session_manager, mock_session, mock_response
        
    async def test_session_manager_request_basic(self, session_manager_with_mock_session):
        """测试基本HTTP请求"""
        session_manager, mock_session, mock_response = session_manager_with_mock_session
        
        response = await session_manager.request(
            "GET",
            "https://api.example.com/data",
            session_name="test"
        )
        
        assert response is not None
        assert response.status == 200
        mock_session.request.assert_called_once_with(
            "GET", 
            "https://api.example.com/data"
        )
        assert session_manager.stats['requests_made'] == 1
        
    async def test_session_manager_request_with_proxy_override(self, session_manager_with_mock_session):
        """测试带代理覆盖的请求"""
        session_manager, mock_session, mock_response = session_manager_with_mock_session
        
        response = await session_manager.request(
            "GET",
            "https://api.example.com/data",
            session_name="test",
            proxy_override="http://custom-proxy.com:8080"
        )
        
        assert response is not None
        mock_session.request.assert_called_once()
        
        # 检查代理参数
        call_args = mock_session.request.call_args
        assert 'proxy' in call_args.kwargs
        assert call_args.kwargs['proxy'] == "http://custom-proxy.com:8080"
        assert session_manager.stats['proxy_requests'] == 1
        
    async def test_session_manager_request_with_retry(self, session_manager):
        """测试带重试的请求"""
        with patch.object(session_manager, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            
            # 第一次失败，第二次成功
            mock_response_fail = AsyncMock()
            mock_response_fail.status = 500
            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            
            mock_session.request.side_effect = [
                aiohttp.ClientError("Connection failed"),
                mock_response_success
            ]
            mock_get_session.return_value = mock_session
            
            response = await session_manager.request_with_retry(
                "GET",
                "https://api.example.com/data",
                max_retries=2,
                retry_delay=0.1
            )
            
            assert response is not None
            assert response.status == 200
            assert mock_session.request.call_count == 2
            
    async def test_session_manager_request_error_handling(self, session_manager):
        """测试请求错误处理"""
        with patch.object(session_manager, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.request.side_effect = aiohttp.ClientError("Network error")
            mock_get_session.return_value = mock_session
            
            with pytest.raises(aiohttp.ClientError):
                await session_manager.request(
                    "GET",
                    "https://api.example.com/data"
                )


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerLifecycle:
    """统一会话管理器生命周期测试"""
    
    @pytest.fixture
    def session_manager_with_sessions(self):
        """创建带会话的会话管理器"""
        session_manager = UnifiedSessionManager()
        
        # 添加模拟会话
        mock_sessions = {}
        for i in range(3):
            mock_session = AsyncMock()
            mock_session.closed = False
            mock_session.close = AsyncMock()
            session_name = f"session_{i}"
            mock_sessions[session_name] = mock_session
            session_manager._sessions[session_name] = mock_session
            
        return session_manager, mock_sessions
        
    async def test_session_manager_close_session(self, session_manager_with_sessions):
        """测试关闭单个会话"""
        session_manager, mock_sessions = session_manager_with_sessions
        
        await session_manager.close_session("session_0")
        
        # 验证会话被关闭和移除
        mock_sessions["session_0"].close.assert_called_once()
        assert "session_0" not in session_manager._sessions
        assert session_manager.stats['sessions_closed'] == 1
        
    async def test_session_manager_close_all_sessions(self, session_manager_with_sessions):
        """测试关闭所有会话"""
        session_manager, mock_sessions = session_manager_with_sessions
        
        await session_manager.close_all_sessions()
        
        # 验证所有会话被关闭
        for mock_session in mock_sessions.values():
            mock_session.close.assert_called_once()
            
        assert len(session_manager._sessions) == 0
        assert session_manager.stats['sessions_closed'] == 3
        
    async def test_session_manager_cleanup_expired_sessions(self, session_manager):
        """测试清理过期会话"""
        # 创建过期会话
        mock_session = AsyncMock()
        mock_session.closed = True
        mock_session.close = AsyncMock()
        
        session_manager._sessions["expired_session"] = mock_session
        session_manager._last_cleanup = 0  # 强制清理
        
        await session_manager._cleanup_expired_sessions()
        
        # 验证过期会话被移除
        assert "expired_session" not in session_manager._sessions
        assert session_manager.stats['cleanup_runs'] == 1
        
    async def test_session_manager_shutdown(self, session_manager_with_sessions):
        """测试会话管理器关闭"""
        session_manager, mock_sessions = session_manager_with_sessions
        
        await session_manager.shutdown()
        
        # 验证所有会话被关闭，管理器标记为关闭
        for mock_session in mock_sessions.values():
            mock_session.close.assert_called_once()
            
        assert session_manager._closed is True
        assert len(session_manager._sessions) == 0
        
    async def test_session_manager_context_manager(self):
        """测试会话管理器作为上下文管理器"""
        async with UnifiedSessionManager() as session_manager:
            assert session_manager is not None
            assert session_manager._closed is False
            
        # 退出上下文后应该被关闭
        assert session_manager._closed is True


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerConfiguration:
    """统一会话管理器配置测试"""
    
    def test_session_config_default_values(self):
        """测试会话配置默认值"""
        config = UnifiedSessionConfig()
        
        assert config.connector_limit == 100
        assert config.connector_limit_per_host == 30
        assert config.total_timeout == 30.0
        assert config.connection_timeout == 10.0
        assert config.read_timeout == 30.0
        assert config.keepalive_timeout == 30.0
        assert config.verify_ssl is True
        assert config.enable_auto_cleanup is True
        
    def test_session_config_custom_values(self):
        """测试会话配置自定义值"""
        config = UnifiedSessionConfig(
            connector_limit=200,
            connector_limit_per_host=50,
            total_timeout=60.0,
            connection_timeout=15.0,
            verify_ssl=False
        )
        
        assert config.connector_limit == 200
        assert config.connector_limit_per_host == 50
        assert config.total_timeout == 60.0
        assert config.connection_timeout == 15.0
        assert config.verify_ssl is False
        
    def test_session_manager_get_stats(self):
        """测试获取统计信息"""
        session_manager = UnifiedSessionManager()
        
        stats = session_manager.get_stats()
        
        assert isinstance(stats, dict)
        assert 'sessions_created' in stats
        assert 'sessions_closed' in stats
        assert 'requests_made' in stats
        assert 'proxy_requests' in stats
        assert 'direct_requests' in stats
        assert 'cleanup_runs' in stats
        
    def test_session_manager_reset_stats(self):
        """测试重置统计信息"""
        session_manager = UnifiedSessionManager()
        
        # 修改一些统计值
        session_manager.stats['sessions_created'] = 5
        session_manager.stats['requests_made'] = 10
        
        session_manager.reset_stats()
        
        # 验证统计信息被重置
        assert session_manager.stats['sessions_created'] == 0
        assert session_manager.stats['requests_made'] == 0


@pytest.mark.integration
@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerIntegration:
    """统一会话管理器集成测试"""
    
    async def test_session_manager_full_workflow(self):
        """测试会话管理器完整工作流"""
        session_manager = UnifiedSessionManager()
        
        try:
            # 创建会话
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_session.request.return_value = mock_response
                mock_session_class.return_value = mock_session
                
                # 获取会话
                session = await session_manager.get_session("integration_test")
                assert session is not None
                
                # 发送请求
                response = await session_manager.request(
                    "GET",
                    "https://api.example.com/test",
                    session_name="integration_test"
                )
                assert response.status == 200
                
                # 检查统计信息
                stats = session_manager.get_stats()
                assert stats['sessions_created'] == 1
                assert stats['requests_made'] == 1
                
        finally:
            # 清理
            await session_manager.shutdown()
            assert session_manager._closed is True
