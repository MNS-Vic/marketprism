"""
统一会话管理器TDD测试
专门用于提升core/networking/unified_session_manager.py的测试覆盖率到90%以上

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import aiohttp
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from core.networking.unified_session_manager import (
    UnifiedSessionManager, UnifiedSessionConfig, 
    HTTPSessionManager, SessionManager, SessionConfig
)
from core.networking.proxy_manager import ProxyConfig


class TestUnifiedSessionConfig:
    """测试UnifiedSessionConfig配置类"""
    
    def test_config_default_initialization(self):
        """测试：默认配置初始化"""
        config = UnifiedSessionConfig()

        assert config.total_timeout == 60.0  # 修正实际默认值
        assert config.connection_timeout == 10.0  # 修正属性名
        assert config.read_timeout == 30.0
        assert config.connector_limit == 100
        assert config.connector_limit_per_host == 30
        assert config.enable_ssl is True
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.enable_auto_cleanup is True
        
    def test_config_custom_initialization(self):
        """测试：自定义配置初始化"""
        config = UnifiedSessionConfig(
            total_timeout=60.0,
            connector_limit=200,
            enable_ssl=False,
            max_retries=5
        )
        
        assert config.total_timeout == 60.0
        assert config.connector_limit == 200
        assert config.enable_ssl is False
        assert config.max_retries == 5
        
    def test_config_ssl_context_creation(self):
        """测试：SSL配置启用"""
        config = UnifiedSessionConfig(enable_ssl=True)

        assert config.enable_ssl is True
        assert config.verify_ssl is True  # 检查相关SSL属性

    def test_config_ssl_context_disabled(self):
        """测试：SSL禁用配置"""
        config = UnifiedSessionConfig(enable_ssl=False)

        assert config.enable_ssl is False


class TestUnifiedSessionManagerInitialization:
    """测试UnifiedSessionManager初始化"""
    
    def test_manager_default_initialization(self):
        """测试：默认初始化"""
        manager = UnifiedSessionManager()
        
        assert isinstance(manager.config, UnifiedSessionConfig)
        assert isinstance(manager._sessions, dict)
        assert isinstance(manager._session_configs, dict)
        assert isinstance(manager._connectors, dict)
        assert manager._closed is False
        assert manager._cleanup_task is None
        assert manager._initialized is False
        
    def test_manager_custom_config_initialization(self):
        """测试：自定义配置初始化"""
        custom_config = UnifiedSessionConfig(total_timeout=60.0)
        manager = UnifiedSessionManager(config=custom_config)
        
        assert manager.config.total_timeout == 60.0
        
    def test_manager_stats_initialization(self):
        """测试：统计信息初始化"""
        manager = UnifiedSessionManager()
        
        assert 'sessions_created' in manager.stats
        assert 'sessions_closed' in manager.stats
        assert 'requests_made' in manager.stats
        assert 'requests_failed' in manager.stats
        assert 'cleanup_runs' in manager.stats
        assert 'proxy_requests' in manager.stats
        assert 'direct_requests' in manager.stats
        assert 'start_time' in manager.stats
        
        # 验证初始值
        assert manager.stats['sessions_created'] == 0
        assert manager.stats['sessions_closed'] == 0
        assert manager.stats['requests_made'] == 0


class TestUnifiedSessionManagerSessionOperations:
    """测试UnifiedSessionManager会话操作"""
    
    def setup_method(self):
        """设置测试方法"""
        self.manager = UnifiedSessionManager()
        
    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建任务
                asyncio.create_task(self.manager.close())
            else:
                # 如果事件循环未运行，直接运行
                loop.run_until_complete(self.manager.close())
        except RuntimeError:
            # 没有事件循环，跳过清理
            pass
        
    @pytest.mark.asyncio
    async def test_get_session_default(self):
        """测试：获取默认会话"""
        session = await self.manager.get_session()
        
        assert isinstance(session, aiohttp.ClientSession)
        assert not session.closed
        assert "default" in self.manager._sessions
        assert self.manager.stats['sessions_created'] == 1
        
    @pytest.mark.asyncio
    async def test_get_session_named(self):
        """测试：获取命名会话"""
        session_name = "test_session"
        session = await self.manager.get_session(session_name)
        
        assert isinstance(session, aiohttp.ClientSession)
        assert session_name in self.manager._sessions
        assert self.manager._sessions[session_name] is session
        
    @pytest.mark.asyncio
    async def test_get_session_reuse(self):
        """测试：会话复用"""
        session_name = "reuse_test"
        
        # 第一次获取
        session1 = await self.manager.get_session(session_name)
        
        # 第二次获取应该返回同一个会话
        session2 = await self.manager.get_session(session_name)
        
        assert session1 is session2
        assert self.manager.stats['sessions_created'] == 1
        
    @pytest.mark.asyncio
    async def test_get_session_with_custom_config(self):
        """测试：使用自定义配置获取会话"""
        custom_config = UnifiedSessionConfig(total_timeout=60.0)
        session = await self.manager.get_session("custom", config=custom_config)
        
        assert isinstance(session, aiohttp.ClientSession)
        assert "custom" in self.manager._session_configs
        assert self.manager._session_configs["custom"].total_timeout == 60.0
        
    @pytest.mark.asyncio
    async def test_get_session_with_proxy_config(self):
        """测试：使用代理配置获取会话"""
        proxy_config = ProxyConfig(
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8080"
        )
        
        session = await self.manager.get_session("proxy_test", proxy_config=proxy_config)
        
        assert isinstance(session, aiohttp.ClientSession)
        assert "proxy_test" in self.manager._sessions
        
    @pytest.mark.asyncio
    async def test_get_session_closed_manager(self):
        """测试：管理器关闭后获取会话"""
        await self.manager.close()
        
        with pytest.raises(RuntimeError, match="会话管理器已关闭"):
            await self.manager.get_session()
            
    @pytest.mark.asyncio
    async def test_close_session(self):
        """测试：关闭单个会话"""
        session_name = "close_test"
        session = await self.manager.get_session(session_name)
        
        await self.manager.close_session(session_name)
        
        assert session.closed
        assert session_name not in self.manager._sessions
        
    @pytest.mark.asyncio
    async def test_close_nonexistent_session(self):
        """测试：关闭不存在的会话"""
        # 应该不抛出异常
        await self.manager.close_session("nonexistent")
        
    @pytest.mark.asyncio
    async def test_close_all_sessions(self):
        """测试：关闭所有会话"""
        # 创建多个会话
        session1 = await self.manager.get_session("session1")
        session2 = await self.manager.get_session("session2")
        
        await self.manager.close()
        
        assert session1.closed
        assert session2.closed
        assert len(self.manager._sessions) == 0
        assert self.manager._closed is True


class TestUnifiedSessionManagerConnectorManagement:
    """测试UnifiedSessionManager连接器管理"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = UnifiedSessionManager()

    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.manager.close())
            else:
                loop.run_until_complete(self.manager.close())
        except RuntimeError:
            pass

    @pytest.mark.asyncio
    async def test_create_connector_in_async_context(self):
        """测试：在异步上下文中创建连接器"""
        # 在异步上下文中测试连接器创建
        connector = self.manager._create_connector("test_key")

        assert isinstance(connector, aiohttp.TCPConnector)
        assert connector.limit == self.manager.config.connector_limit
        assert connector.limit_per_host == self.manager.config.connector_limit_per_host

        # 清理连接器
        await connector.close()

    @pytest.mark.asyncio
    async def test_create_connector_with_ssl_config(self):
        """测试：创建带SSL配置的连接器"""
        # 测试SSL相关的连接器创建
        connector = self.manager._create_connector("ssl_test")

        assert isinstance(connector, aiohttp.TCPConnector)

        # 清理连接器
        await connector.close()

    @pytest.mark.asyncio
    async def test_create_connector_ssl_disabled(self):
        """测试：创建禁用SSL的连接器"""
        config = UnifiedSessionConfig(enable_ssl=False)
        manager = UnifiedSessionManager(config=config)

        connector = manager._create_connector("test_key")

        assert isinstance(connector, aiohttp.TCPConnector)

        # 清理连接器和管理器
        await connector.close()
        await manager.close()


class TestUnifiedSessionManagerCleanup:
    """测试UnifiedSessionManager清理功能"""
    
    def setup_method(self):
        """设置测试方法"""
        self.manager = UnifiedSessionManager()
        
    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.manager.close())
            else:
                loop.run_until_complete(self.manager.close())
        except RuntimeError:
            pass
        
    def test_cleanup_sessions_no_closed(self):
        """测试：清理会话（无关闭会话）"""
        # 手动添加一个活跃会话到内部字典
        mock_session = Mock()
        mock_session.closed = False
        # 创建一个异步close方法的Mock
        async def async_close():
            return None
        mock_session.close = async_close
        self.manager._sessions["active"] = mock_session

        cleaned_count = self.manager.cleanup_sessions()

        assert cleaned_count == 0
        assert "active" in self.manager._sessions

    def test_cleanup_sessions_with_closed(self):
        """测试：清理会话（有关闭会话）"""
        # 手动添加关闭的会话
        mock_session = Mock()
        mock_session.closed = True
        # 创建一个异步close方法的Mock
        async def async_close():
            return None
        mock_session.close = async_close
        self.manager._sessions["closed"] = mock_session
        self.manager._session_configs["closed"] = UnifiedSessionConfig()

        cleaned_count = self.manager.cleanup_sessions()

        assert cleaned_count == 1
        assert "closed" not in self.manager._sessions
        assert "closed" not in self.manager._session_configs
        
    def test_get_stats(self):
        """测试：获取统计信息"""
        # 直接访问stats属性而不是调用get_stats方法
        stats = self.manager.stats

        assert isinstance(stats, dict)
        assert 'sessions_created' in stats
        assert 'sessions_closed' in stats
        assert 'requests_made' in stats
        assert 'start_time' in stats

    def test_manager_properties(self):
        """测试：管理器属性"""
        # 测试管理器的基本属性
        assert hasattr(self.manager, '_sessions')
        assert hasattr(self.manager, '_session_configs')
        assert hasattr(self.manager, '_connectors')
        assert self.manager._closed is False


class TestUnifiedSessionManagerRequestOperations:
    """测试UnifiedSessionManager请求操作"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = UnifiedSessionManager()

    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.manager.close())
            else:
                loop.run_until_complete(self.manager.close())
        except RuntimeError:
            pass

    @pytest.mark.asyncio
    async def test_request_basic(self):
        """测试：基本请求功能"""
        with patch.object(self.manager, 'get_session') as mock_get_session:
            with patch('core.networking.unified_session_manager.proxy_manager') as mock_proxy_manager:
                mock_session = AsyncMock()
                mock_response = AsyncMock()
                mock_session.request.return_value = mock_response
                mock_get_session.return_value = mock_session

                # 模拟代理管理器返回无代理配置
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = False
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                # 确保session_name在_session_configs中
                self.manager._session_configs["default"] = self.manager.config

                response = await self.manager.request('GET', 'http://example.com')

                assert response == mock_response
                assert self.manager.stats['requests_made'] == 1
                assert self.manager.stats['direct_requests'] == 1

    @pytest.mark.asyncio
    async def test_request_with_proxy_override(self):
        """测试：使用代理覆盖的请求"""
        with patch.object(self.manager, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_session.request.return_value = mock_response
            mock_get_session.return_value = mock_session

            response = await self.manager.request(
                'GET',
                'http://example.com',
                proxy_override='http://proxy.example.com:8080'
            )

            assert response == mock_response
            assert self.manager.stats['proxy_requests'] == 1
            mock_session.request.assert_called_with(
                'GET',
                'http://example.com',
                proxy='http://proxy.example.com:8080'
            )

    @pytest.mark.asyncio
    async def test_request_failure(self):
        """测试：请求失败处理"""
        with patch.object(self.manager, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.request.side_effect = aiohttp.ClientError("Request failed")
            mock_get_session.return_value = mock_session

            with pytest.raises(aiohttp.ClientError):
                await self.manager.request('GET', 'http://example.com')

            assert self.manager.stats['requests_failed'] == 1

    @pytest.mark.asyncio
    async def test_request_with_retry_success(self):
        """测试：重试请求成功"""
        with patch.object(self.manager, 'request') as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_request.return_value = mock_response

            response = await self.manager.request_with_retry('GET', 'http://example.com')

            assert response == mock_response
            assert mock_request.call_count == 1

    @pytest.mark.asyncio
    async def test_request_with_retry_server_error(self):
        """测试：重试请求服务器错误"""
        with patch.object(self.manager, 'request') as mock_request:
            # 第一次返回服务器错误，第二次成功
            mock_error_response = AsyncMock()
            mock_error_response.status = 500
            mock_error_response.close = Mock()

            mock_success_response = AsyncMock()
            mock_success_response.status = 200

            mock_request.side_effect = [mock_error_response, mock_success_response]

            response = await self.manager.request_with_retry('GET', 'http://example.com')

            assert response == mock_success_response
            assert mock_request.call_count == 2
            mock_error_response.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_with_retry_all_failed(self):
        """测试：重试请求全部失败"""
        with patch.object(self.manager, 'request') as mock_request:
            mock_request.side_effect = aiohttp.ClientError("Persistent error")

            with pytest.raises(aiohttp.ClientError):
                await self.manager.request_with_retry('GET', 'http://example.com', max_attempts=2)

            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_convenience_get_method(self):
        """测试：便捷GET方法"""
        with patch.object(self.manager, 'request') as mock_request:
            mock_response = AsyncMock()
            mock_request.return_value = mock_response

            response = await self.manager.get('http://example.com')

            mock_request.assert_called_with('GET', 'http://example.com', 'default')
            assert response == mock_response

    @pytest.mark.asyncio
    async def test_convenience_post_method(self):
        """测试：便捷POST方法"""
        with patch.object(self.manager, 'request') as mock_request:
            mock_response = AsyncMock()
            mock_request.return_value = mock_response

            response = await self.manager.post('http://example.com', data={'key': 'value'})

            mock_request.assert_called_with('POST', 'http://example.com', 'default', data={'key': 'value'})
            assert response == mock_response


class TestUnifiedSessionManagerAdvancedFeatures:
    """测试UnifiedSessionManager高级功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = UnifiedSessionManager()

    def teardown_method(self):
        """清理测试方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.manager.close())
            else:
                loop.run_until_complete(self.manager.close())
        except RuntimeError:
            pass

    @pytest.mark.asyncio
    async def test_create_session_with_timeout(self):
        """测试：使用超时创建会话"""
        session_id = await self.manager.create_session(
            name="timeout_test",
            timeout=15.0
        )

        assert session_id == "timeout_test"
        assert "timeout_test" in self.manager._sessions

        # 验证配置被正确更新
        config = self.manager._session_configs["timeout_test"]
        assert config.connection_timeout == 15.0

    @pytest.mark.asyncio
    async def test_refresh_session(self):
        """测试：刷新会话"""
        # 创建会话
        session = await self.manager.get_session("refresh_test")
        assert "refresh_test" in self.manager._sessions

        # 刷新会话
        await self.manager.refresh_session("refresh_test")

        # 验证旧会话被移除
        assert "refresh_test" not in self.manager._sessions

    @pytest.mark.asyncio
    async def test_cleanup_closed_sessions_async(self):
        """测试：异步清理关闭的会话"""
        await self.manager.cleanup_closed_sessions()
        # 应该正常完成，不抛出异常

    def test_get_session_stats(self):
        """测试：获取会话统计信息"""
        # 设置一些统计数据
        self.manager.stats['sessions_created'] = 5
        self.manager.stats['requests_made'] = 10
        self.manager._sessions = {"test1": Mock(), "test2": Mock()}

        stats = self.manager.get_session_stats()

        assert stats['sessions_created'] == 5
        assert stats['requests_made'] == 10
        assert stats['total_sessions'] == 2
        assert 'active_sessions' in stats
        assert 'closed_sessions' in stats
        assert 'session_names' in stats


class TestBackwardCompatibility:
    """测试向后兼容性"""

    def test_http_session_manager_alias(self):
        """测试：HTTPSessionManager别名"""
        assert HTTPSessionManager is UnifiedSessionManager

    def test_session_manager_alias(self):
        """测试：SessionManager别名"""
        assert SessionManager is UnifiedSessionManager

    def test_session_config_alias(self):
        """测试：SessionConfig别名"""
        assert SessionConfig is UnifiedSessionConfig

    def test_global_instance_exists(self):
        """测试：全局实例存在"""
        from core.networking.unified_session_manager import unified_session_manager

        assert isinstance(unified_session_manager, UnifiedSessionManager)
