"""
统一会话管理器高级TDD测试
专注于提升覆盖率和测试未覆盖的功能
"""

import pytest
import asyncio
import ssl
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

try:
    import aiohttp
    from core.networking.unified_session_manager import (
        UnifiedSessionManager, UnifiedSessionConfig, unified_session_manager
    )
    from core.networking.proxy_manager import ProxyConfig
    HAS_NETWORKING_MODULES = True
except ImportError:
    HAS_NETWORKING_MODULES = False


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionConfigAdvanced:
    """测试UnifiedSessionConfig高级功能"""
    
    def test_session_config_ssl_context_creation(self):
        """测试：SSL上下文配置"""
        ssl_context = ssl.create_default_context()
        config = UnifiedSessionConfig(
            ssl_context=ssl_context,
            verify_ssl=True,
            enable_ssl=True
        )
        
        assert config.ssl_context is ssl_context
        assert config.verify_ssl is True
        assert config.enable_ssl is True
    
    def test_session_config_proxy_auth_configuration(self):
        """测试：代理认证配置"""
        proxy_auth = aiohttp.BasicAuth("user", "pass")
        config = UnifiedSessionConfig(
            proxy_url="http://proxy.example.com:8080",
            proxy_auth=proxy_auth,
            trust_env=False
        )
        
        assert config.proxy_url == "http://proxy.example.com:8080"
        assert config.proxy_auth is proxy_auth
        assert config.trust_env is False
    
    def test_session_config_headers_and_cookies(self):
        """测试：请求头和Cookie配置"""
        headers = {"Authorization": "Bearer token", "X-API-Key": "key123"}
        cookies = {"session_id": "abc123", "user_pref": "dark_mode"}
        
        config = UnifiedSessionConfig(
            headers=headers,
            cookies=cookies
        )
        
        assert config.headers == headers
        assert config.cookies == cookies
    
    def test_session_config_compression_and_redirects(self):
        """测试：压缩和重定向配置"""
        config = UnifiedSessionConfig(
            enable_compression=False,
            follow_redirects=False,
            max_field_size=16384
        )
        
        assert config.enable_compression is False
        assert config.follow_redirects is False
        assert config.max_field_size == 16384
    
    def test_session_config_cleanup_settings(self):
        """测试：清理配置"""
        config = UnifiedSessionConfig(
            cleanup_interval=60,
            enable_auto_cleanup=False
        )
        
        assert config.cleanup_interval == 60
        assert config.enable_auto_cleanup is False


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerAdvancedOperations:
    """测试UnifiedSessionManager高级操作"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的会话管理器"""
        return UnifiedSessionManager()
    
    @pytest.fixture
    def cleanup_manager(self):
        """创建测试后自动清理的会话管理器"""
        manager = UnifiedSessionManager()
        yield manager
        # 清理
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.run_until_complete(manager.close())
        except:
            pass
    
    @pytest.mark.asyncio
    async def test_create_session_with_ssl_context(self, manager):
        """测试：使用SSL上下文创建会话"""
        ssl_context = ssl.create_default_context()
        config = UnifiedSessionConfig(ssl_context=ssl_context)
        
        with patch('aiohttp.TCPConnector') as mock_connector_class:
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_connector = AsyncMock()
                mock_connector_class.return_value = mock_connector
                mock_session = AsyncMock()
                mock_session_class.return_value = mock_session
                
                session = await manager.get_session("ssl_test", config=config)
                
                assert session is mock_session
                # 验证SSL上下文被传递给连接器
                mock_connector_class.assert_called_once()
                call_kwargs = mock_connector_class.call_args.kwargs
                assert call_kwargs['ssl'] is ssl_context
    
    @pytest.mark.asyncio
    async def test_create_session_with_proxy_config(self, manager):
        """测试：使用代理配置创建会话"""
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8080"
        )
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            session = await manager.get_session("proxy_test", proxy_config=proxy_config)
            
            assert session is mock_session
            assert "proxy_test" in manager._sessions
    
    @pytest.mark.asyncio
    async def test_create_session_with_exchange_config(self, manager):
        """测试：使用交易所配置创建会话"""
        exchange_config = {
            "name": "binance",
            "api_key": "test_key",
            "secret": "test_secret",
            "timeout": 30
        }
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            session = await manager.get_session("exchange_test", exchange_config=exchange_config)
            
            assert session is mock_session
            assert "exchange_test" in manager._sessions
    
    @pytest.mark.asyncio
    async def test_create_session_with_custom_headers_and_cookies(self, manager):
        """测试：使用自定义请求头和Cookie创建会话"""
        config = UnifiedSessionConfig(
            headers={"X-Custom-Header": "test_value"},
            cookies={"session": "test_session"}
        )
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            session = await manager.get_session("custom_test", config=config)
            
            assert session is mock_session
            # 验证会话创建时使用了自定义配置
            mock_session_class.assert_called_once()
            call_kwargs = mock_session_class.call_args.kwargs
            assert "X-Custom-Header" in call_kwargs['headers']
    
    @pytest.mark.asyncio
    async def test_request_with_proxy_override(self, manager):
        """测试：使用代理覆盖发送请求"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.request.return_value = mock_response
            mock_session_class.return_value = mock_session
            
            response = await manager.request(
                "GET",
                "https://api.example.com/test",
                proxy_override="http://custom-proxy.com:8080"
            )
            
            assert response.status == 200
            assert manager.stats['proxy_requests'] == 1
            assert manager.stats['requests_made'] == 1
            
            # 验证代理被传递给请求
            mock_session.request.assert_called_once()
            call_kwargs = mock_session.request.call_args.kwargs
            assert call_kwargs['proxy'] == "http://custom-proxy.com:8080"
    
    @pytest.mark.asyncio
    async def test_request_with_retry_success_after_failure(self, manager):
        """测试：重试请求在失败后成功"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            
            # 第一次失败，第二次成功
            mock_session.request.side_effect = [
                aiohttp.ClientError("Connection failed"),
                mock_response
            ]
            mock_session_class.return_value = mock_session
            
            response = await manager.request_with_retry(
                "GET",
                "https://api.example.com/test",
                max_attempts=2
            )
            
            assert response.status == 200
            assert mock_session.request.call_count == 2
    
    @pytest.mark.asyncio
    async def test_request_with_retry_all_attempts_fail(self, manager):
        """测试：重试请求所有尝试都失败"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.request.side_effect = aiohttp.ClientError("Persistent error")
            mock_session_class.return_value = mock_session
            
            with pytest.raises(aiohttp.ClientError, match="Persistent error"):
                await manager.request_with_retry(
                    "GET",
                    "https://api.example.com/test",
                    max_attempts=3
                )
            
            assert mock_session.request.call_count == 3
    
    @pytest.mark.asyncio
    async def test_request_failure_updates_stats(self, manager):
        """测试：请求失败更新统计信息"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.request.side_effect = aiohttp.ClientError("Request failed")
            mock_session_class.return_value = mock_session
            
            with pytest.raises(aiohttp.ClientError):
                await manager.request("GET", "https://api.example.com/test")
            
            assert manager.stats['requests_failed'] == 1
    
    @pytest.mark.asyncio
    async def test_get_session_when_closed_raises_error(self, manager):
        """测试：管理器关闭后获取会话抛出错误"""
        await manager.close()
        
        with pytest.raises(RuntimeError, match="会话管理器已关闭"):
            await manager.get_session()
    
    @pytest.mark.asyncio
    async def test_cleanup_task_creation_and_management(self, cleanup_manager):
        """测试：清理任务创建和管理"""
        # 启用自动清理
        cleanup_manager.config.enable_auto_cleanup = True
        
        # 获取会话应该启动清理任务
        await cleanup_manager.get_session("test")
        
        # 验证清理任务被创建
        assert cleanup_manager._cleanup_task is not None
        assert not cleanup_manager._cleanup_task.done()
    
    @pytest.mark.asyncio
    async def test_cleanup_task_not_created_when_disabled(self, cleanup_manager):
        """测试：禁用自动清理时不创建清理任务"""
        # 禁用自动清理
        cleanup_manager.config.enable_auto_cleanup = False
        
        # 获取会话不应该启动清理任务
        await cleanup_manager.get_session("test")
        
        # 验证清理任务未被创建
        assert cleanup_manager._cleanup_task is None
    
    def test_cleanup_sessions_removes_closed_sessions(self, manager):
        """测试：清理会话移除已关闭的会话"""
        # 添加一些模拟会话
        mock_session1 = Mock()
        mock_session1.closed = False
        mock_session2 = Mock()
        mock_session2.closed = True
        mock_session3 = Mock()
        mock_session3.closed = True
        
        manager._sessions["active"] = mock_session1
        manager._sessions["closed1"] = mock_session2
        manager._sessions["closed2"] = mock_session3
        manager._session_configs["active"] = UnifiedSessionConfig()
        manager._session_configs["closed1"] = UnifiedSessionConfig()
        manager._session_configs["closed2"] = UnifiedSessionConfig()
        
        cleaned_count = manager.cleanup_sessions()
        
        assert cleaned_count == 2
        assert "active" in manager._sessions
        assert "closed1" not in manager._sessions
        assert "closed2" not in manager._sessions
        assert "active" in manager._session_configs
        assert "closed1" not in manager._session_configs
        assert "closed2" not in manager._session_configs
    
    def test_get_session_stats_returns_comprehensive_info(self, manager):
        """测试：获取会话统计返回全面信息"""
        # 设置一些统计数据
        manager.stats['sessions_created'] = 5
        manager.stats['requests_made'] = 20
        manager.stats['proxy_requests'] = 8
        manager.stats['direct_requests'] = 12

        # 添加一些会话
        manager._sessions["test1"] = Mock()
        manager._sessions["test2"] = Mock()

        stats = manager.get_session_stats()

        assert stats['sessions_created'] == 5
        assert stats['requests_made'] == 20
        assert stats['proxy_requests'] == 8
        assert stats['direct_requests'] == 12
        assert stats['total_sessions'] == 2

        # get_session_stats没有uptime，但get_statistics有
        detailed_stats = manager.get_statistics()
        assert 'uptime_seconds' in detailed_stats
        assert isinstance(detailed_stats['uptime_seconds'], float)
    
    @pytest.mark.asyncio
    async def test_close_manager_with_active_sessions(self, manager):
        """测试：关闭有活跃会话的管理器"""
        # 直接添加模拟会话到管理器
        mock_session1 = AsyncMock()
        mock_session1.closed = False
        mock_session2 = AsyncMock()
        mock_session2.closed = False

        manager._sessions["test1"] = mock_session1
        manager._sessions["test2"] = mock_session2

        # 关闭管理器
        await manager.close()

        # 验证所有会话都被关闭
        mock_session1.close.assert_called_once()
        mock_session2.close.assert_called_once()
        assert manager._closed is True
    
    @pytest.mark.asyncio
    async def test_close_manager_with_cleanup_task(self, manager):
        """测试：关闭有清理任务的管理器"""
        # 启用自动清理并创建清理任务
        manager.config.enable_auto_cleanup = True
        await manager.get_session("test")
        
        cleanup_task = manager._cleanup_task
        assert cleanup_task is not None
        
        # 关闭管理器
        await manager.close()
        
        # 验证清理任务被取消
        assert cleanup_task.cancelled() or cleanup_task.done()
        assert manager._closed is True


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerErrorHandling:
    """测试UnifiedSessionManager错误处理"""

    @pytest.fixture
    def manager(self):
        """创建测试用的会话管理器"""
        return UnifiedSessionManager()

    @pytest.mark.asyncio
    async def test_create_session_connector_creation_failure(self, manager):
        """测试：连接器创建失败的处理"""
        config = UnifiedSessionConfig()
        proxy_config = ProxyConfig(enabled=False)

        with patch('aiohttp.TCPConnector') as mock_connector_class:
            mock_connector_class.side_effect = Exception("Connector creation failed")

            with pytest.raises(Exception, match="Connector creation failed"):
                await manager._create_session(config, proxy_config)

    @pytest.mark.asyncio
    async def test_create_session_session_creation_failure(self, manager):
        """测试：会话创建失败的处理"""
        config = UnifiedSessionConfig()
        proxy_config = ProxyConfig(enabled=False)

        with patch('aiohttp.TCPConnector') as mock_connector_class:
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_connector = AsyncMock()
                mock_connector_class.return_value = mock_connector
                mock_session_class.side_effect = Exception("Session creation failed")

                with pytest.raises(Exception, match="Session creation failed"):
                    await manager._create_session(config, proxy_config)

    @pytest.mark.asyncio
    async def test_get_session_with_invalid_proxy_config(self, manager):
        """测试：使用无效代理配置获取会话"""
        # 创建一个无效的代理配置对象
        invalid_proxy_config = Mock()
        invalid_proxy_config.has_proxy.side_effect = Exception("Invalid proxy config")

        with patch('core.networking.unified_session_manager.proxy_manager') as mock_proxy_manager:
            mock_proxy_manager.get_proxy_config.return_value = invalid_proxy_config

            # 代理配置错误会导致会话创建失败
            with pytest.raises(Exception, match="Invalid proxy config"):
                await manager.get_session("error_test")

    @pytest.mark.asyncio
    async def test_request_with_session_retrieval_failure(self, manager):
        """测试：会话获取失败时的请求处理"""
        # 模拟get_session失败
        with patch.object(manager, 'get_session') as mock_get_session:
            mock_get_session.side_effect = Exception("Session retrieval failed")

            with pytest.raises(Exception, match="Session retrieval failed"):
                await manager.request("GET", "https://api.example.com/test")

            assert manager.stats['requests_failed'] == 1

    @pytest.mark.asyncio
    async def test_cleanup_loop_exception_handling(self, manager):
        """测试：清理循环异常处理"""
        # 启动清理循环
        manager.config.enable_auto_cleanup = True
        manager.config.cleanup_interval = 0.1  # 快速清理间隔

        # 模拟cleanup_sessions抛出异常
        original_cleanup = manager.cleanup_sessions
        def failing_cleanup():
            if manager.stats['cleanup_runs'] == 0:
                manager.stats['cleanup_runs'] += 1
                raise Exception("Cleanup failed")
            return original_cleanup()

        manager.cleanup_sessions = failing_cleanup

        # 启动清理任务
        await manager.get_session("test")

        # 等待一段时间让清理任务运行
        await asyncio.sleep(0.2)

        # 清理任务应该仍在运行（异常被处理）
        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        # 清理
        await manager.close()


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerProxyIntegration:
    """测试UnifiedSessionManager代理集成"""

    @pytest.fixture
    def manager(self):
        """创建测试用的会话管理器"""
        return UnifiedSessionManager()

    @pytest.mark.asyncio
    async def test_request_with_session_proxy_config(self, manager):
        """测试：使用会话代理配置发送请求"""
        # 创建会话并设置代理配置
        with patch('aiohttp.ClientSession') as mock_session_class:
            with patch('core.networking.unified_session_manager.proxy_manager') as mock_proxy_manager:
                mock_session = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_session.request.return_value = mock_response
                mock_session_class.return_value = mock_session

                # 模拟代理管理器返回有代理的配置
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = True
                mock_proxy_config.to_aiohttp_proxy.return_value = "http://proxy.example.com:8080"
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                # 获取会话（这会设置代理配置）
                await manager.get_session("proxy_session")

                # 发送请求
                response = await manager.request(
                    "GET",
                    "https://api.example.com/test",
                    session_name="proxy_session"
                )

                assert response.status == 200
                assert manager.stats['proxy_requests'] == 1

                # 验证代理被传递给请求
                mock_session.request.assert_called_once()
                call_kwargs = mock_session.request.call_args.kwargs
                assert call_kwargs['proxy'] == "http://proxy.example.com:8080"

    @pytest.mark.asyncio
    async def test_request_with_no_proxy_config(self, manager):
        """测试：无代理配置时发送请求"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            with patch('core.networking.unified_session_manager.proxy_manager') as mock_proxy_manager:
                mock_session = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_session.request.return_value = mock_response
                mock_session_class.return_value = mock_session

                # 模拟代理管理器返回无代理的配置
                mock_proxy_config = Mock()
                mock_proxy_config.has_proxy.return_value = False
                mock_proxy_manager.get_proxy_config.return_value = mock_proxy_config

                # 获取会话
                await manager.get_session("direct_session")

                # 发送请求
                response = await manager.request(
                    "GET",
                    "https://api.example.com/test",
                    session_name="direct_session"
                )

                assert response.status == 200
                assert manager.stats['direct_requests'] == 1

                # 验证没有代理被传递给请求
                mock_session.request.assert_called_once()
                call_kwargs = mock_session.request.call_args.kwargs
                assert 'proxy' not in call_kwargs


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerManualCleanup:
    """测试UnifiedSessionManager手动清理功能"""

    @pytest.fixture
    def manager(self):
        """创建测试用的会话管理器"""
        return UnifiedSessionManager()

    @pytest.mark.asyncio
    async def test_manual_cleanup_closed_sessions(self, manager):
        """测试：手动清理关闭的会话"""
        # 添加一些模拟会话
        mock_session1 = Mock()
        mock_session1.closed = False
        mock_session2 = Mock()
        mock_session2.closed = True

        manager._sessions["active"] = mock_session1
        manager._sessions["closed"] = mock_session2

        # 手动清理
        await manager.cleanup_closed_sessions()

        # 验证关闭的会话被清理
        assert "active" in manager._sessions
        assert "closed" not in manager._sessions

    @pytest.mark.asyncio
    async def test_refresh_session_functionality(self, manager):
        """测试：刷新会话功能"""
        # 添加一个模拟会话
        mock_session = AsyncMock()
        mock_session.closed = False  # 设置会话为未关闭状态
        manager._sessions["refresh_test"] = mock_session

        # 刷新会话
        await manager.refresh_session("refresh_test")

        # 验证会话被移除
        assert "refresh_test" not in manager._sessions
        mock_session.close.assert_called_once()


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerGlobalInstance:
    """测试UnifiedSessionManager全局实例"""

    def test_global_instance_exists(self):
        """测试：全局实例存在"""
        assert unified_session_manager is not None
        assert isinstance(unified_session_manager, UnifiedSessionManager)

    @pytest.mark.asyncio
    async def test_global_instance_usage(self):
        """测试：全局实例使用"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            session = await unified_session_manager.get_session("global_test")

            assert session is mock_session
            assert "global_test" in unified_session_manager._sessions

    def test_global_instance_stats(self):
        """测试：全局实例统计"""
        stats = unified_session_manager.get_session_stats()

        assert isinstance(stats, dict)
        assert 'sessions_created' in stats
        assert 'requests_made' in stats
        assert 'total_sessions' in stats


@pytest.mark.skipif(not HAS_NETWORKING_MODULES, reason="网络模块不可用")
class TestUnifiedSessionManagerEdgeCases:
    """测试UnifiedSessionManager边界情况"""

    @pytest.fixture
    def manager(self):
        """创建测试用的会话管理器"""
        return UnifiedSessionManager()

    @pytest.mark.asyncio
    async def test_get_session_with_empty_name(self, manager):
        """测试：使用空名称获取会话"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            session = await manager.get_session("")

            assert session is mock_session
            assert "" in manager._sessions

    @pytest.mark.asyncio
    async def test_get_session_with_none_config(self, manager):
        """测试：使用None配置获取会话"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            session = await manager.get_session("none_config_test", config=None)

            assert session is mock_session
            assert "none_config_test" in manager._sessions

    @pytest.mark.asyncio
    async def test_request_with_empty_url(self, manager):
        """测试：使用空URL发送请求"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.request.side_effect = aiohttp.InvalidURL("Empty URL")
            mock_session_class.return_value = mock_session

            with pytest.raises(aiohttp.InvalidURL):
                await manager.request("GET", "")

            assert manager.stats['requests_failed'] == 1

    @pytest.mark.asyncio
    async def test_request_with_retry_zero_attempts(self, manager):
        """测试：重试请求零次尝试"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.request.return_value = mock_response
            mock_session_class.return_value = mock_session

            response = await manager.request_with_retry(
                "GET",
                "https://api.example.com/test",
                max_attempts=0
            )

            assert response.status == 200
            assert mock_session.request.call_count == 1  # 至少尝试一次

    def test_cleanup_sessions_with_empty_sessions(self, manager):
        """测试：清理空会话列表"""
        cleaned_count = manager.cleanup_sessions()

        assert cleaned_count == 0
        assert len(manager._sessions) == 0

    @pytest.mark.asyncio
    async def test_close_already_closed_manager(self, manager):
        """测试：关闭已关闭的管理器"""
        # 第一次关闭
        await manager.close()
        assert manager._closed is True

        # 第二次关闭应该不抛出异常
        await manager.close()
        assert manager._closed is True
