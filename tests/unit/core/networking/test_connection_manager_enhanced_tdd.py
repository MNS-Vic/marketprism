"""
网络连接管理器增强TDD测试
专注于提升覆盖率到45%+，测试未覆盖的边缘情况和错误处理
"""

import pytest
import asyncio
import aiohttp
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

try:
    from core.networking.connection_manager import (
        NetworkConfig, NetworkConnectionManager, network_manager
    )
    from core.networking.websocket_manager import WebSocketConfig
    from core.networking.unified_session_manager import SessionConfig
    from core.networking.proxy_manager import ProxyConfig
    HAS_CONNECTION_MODULES = True
except ImportError:
    HAS_CONNECTION_MODULES = False


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConfigEdgeCases:
    """测试网络配置边缘情况"""
    
    def test_network_config_from_base_config_method(self):
        """测试：从基础配置创建网络配置"""
        # 测试有交易所名称的情况
        config = NetworkConfig.from_base_config("binance")

        assert config.exchange_name == "binance"
        assert config.timeout > 0
        assert isinstance(config.enable_proxy, bool)
        assert isinstance(config.http_retry_attempts, int)

    def test_network_config_from_base_config_none(self):
        """测试：从None交易所名称创建网络配置"""
        config = NetworkConfig.from_base_config(None)

        assert config.exchange_name is None
        assert config.timeout > 0
        assert isinstance(config.enable_proxy, bool)
        assert isinstance(config.http_retry_attempts, int)

    def test_network_config_from_base_config_empty_string(self):
        """测试：从空字符串交易所名称创建网络配置"""
        config = NetworkConfig.from_base_config("")

        assert config.exchange_name == ""
        assert config.timeout > 0


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerExceptionHandling:
    """测试网络连接管理器异常处理"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()
    
    @pytest.mark.asyncio
    async def test_create_websocket_connection_exception_handling(self, manager):
        """测试：WebSocket连接创建异常处理"""
        url = "wss://api.example.com/ws"
        exchange_name = "test_exchange"
        
        # 模拟websocket_manager.connect抛出异常
        with patch.object(manager.websocket_manager, 'connect', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                await manager.create_websocket_connection(url, exchange_name)
            
            # 验证失败统计被更新
            assert manager.connection_stats['failed_connections'] == 1
    
    @pytest.mark.asyncio
    async def test_create_websocket_connection_returns_none(self, manager):
        """测试：WebSocket连接创建返回None"""
        url = "wss://api.example.com/ws"
        exchange_name = "test_exchange"
        
        # 模拟websocket_manager.connect返回None
        with patch.object(manager.websocket_manager, 'connect', return_value=None):
            result = await manager.create_websocket_connection(url, exchange_name)
            
            assert result is None
            # 验证失败统计被更新
            assert manager.connection_stats['failed_connections'] == 1
    
    @pytest.mark.asyncio
    async def test_create_http_session_exception_handling(self, manager):
        """测试：HTTP会话创建异常处理"""
        session_name = "test_session"
        exchange_name = "test_exchange"
        
        # 模拟session_manager.get_session抛出异常
        with patch.object(manager.session_manager, 'get_session', side_effect=Exception("Session creation failed")):
            with pytest.raises(Exception, match="Session creation failed"):
                await manager.create_http_session(session_name, exchange_name)
            
            # 验证失败统计被更新
            assert manager.connection_stats['failed_connections'] == 1
    
    @pytest.mark.asyncio
    async def test_create_http_session_returns_none(self, manager):
        """测试：HTTP会话创建返回None"""
        session_name = "test_session"
        exchange_name = "test_exchange"
        
        # 模拟session_manager.get_session返回None
        with patch.object(manager.session_manager, 'get_session', return_value=None):
            result = await manager.create_http_session(session_name, exchange_name)
            
            assert result is None
            # 验证失败统计被更新
            assert manager.connection_stats['failed_connections'] == 1
    
    @pytest.mark.asyncio
    async def test_close_connection_exception_handling(self, manager):
        """测试：关闭连接异常处理"""
        # 添加一个WebSocket连接
        connection_id = "test_connection"
        mock_connection = AsyncMock()
        mock_connection.close.side_effect = Exception("Close failed")
        
        manager.connections[connection_id] = {
            'type': 'websocket',
            'connection': mock_connection
        }
        
        # 关闭连接应该捕获异常
        await manager.close_connection(connection_id)
        
        # 验证连接仍然存在（因为关闭失败）
        assert connection_id in manager.connections
    
    @pytest.mark.asyncio
    async def test_close_connection_http_session_exception(self, manager):
        """测试：关闭HTTP会话异常处理"""
        # 添加一个HTTP会话
        connection_id = "test_session"
        session_name = "test_session_name"
        
        manager.connections[connection_id] = {
            'type': 'http_session',
            'session_name': session_name
        }
        
        # 模拟session_manager.close_session抛出异常
        with patch.object(manager.session_manager, 'close_session', side_effect=Exception("Close session failed")):
            await manager.close_connection(connection_id)
            
            # 验证连接仍然存在（因为关闭失败）
            assert connection_id in manager.connections
    
    @pytest.mark.asyncio
    async def test_close_all_connections_exception_handling(self, manager):
        """测试：关闭所有连接异常处理"""
        # 模拟websocket_manager.close_all_connections抛出异常
        with patch.object(manager.websocket_manager, 'close_all_connections', side_effect=Exception("Close WS failed")):
            # 应该捕获异常，不抛出
            await manager.close_all_connections()
            
            # 验证连接记录被清理
            assert len(manager.connections) == 0
            assert manager.connection_stats['active_connections'] == 0


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerMonitoring:
    """测试网络连接管理器监控功能"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()
    
    @pytest.mark.asyncio
    async def test_start_monitoring_already_monitoring(self, manager):
        """测试：已经在监控时启动监控"""
        manager.is_monitoring = True
        
        # 启动监控应该直接返回
        await manager.start_monitoring()
        
        # 验证没有创建新的任务
        assert manager.health_check_task is None
    
    @pytest.mark.asyncio
    async def test_start_monitoring_success(self, manager):
        """测试：成功启动监控"""
        assert manager.is_monitoring is False
        
        # 启动监控
        await manager.start_monitoring(interval=1)
        
        # 验证监控状态
        assert manager.is_monitoring is True
        assert manager.health_check_task is not None
        assert isinstance(manager.health_check_task, asyncio.Task)
        
        # 清理
        await manager.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_stop_monitoring_no_task(self, manager):
        """测试：停止监控但没有任务"""
        manager.is_monitoring = True
        manager.health_check_task = None
        
        # 停止监控应该成功
        await manager.stop_monitoring()
        
        assert manager.is_monitoring is False
    
    @pytest.mark.asyncio
    async def test_stop_monitoring_task_already_done(self, manager):
        """测试：停止监控但任务已完成"""
        manager.is_monitoring = True
        
        # 创建一个已完成的任务
        async def dummy_task():
            return "done"
        
        task = asyncio.create_task(dummy_task())
        await task  # 等待任务完成
        manager.health_check_task = task
        
        # 停止监控应该成功
        await manager.stop_monitoring()
        
        assert manager.is_monitoring is False
    
    @pytest.mark.asyncio
    async def test_stop_monitoring_cancel_task(self, manager):
        """测试：停止监控并取消任务"""
        # 启动监控
        await manager.start_monitoring(interval=60)
        
        assert manager.is_monitoring is True
        assert manager.health_check_task is not None
        
        # 停止监控
        await manager.stop_monitoring()
        
        assert manager.is_monitoring is False
        assert manager.health_check_task.cancelled()
    
    @pytest.mark.asyncio
    async def test_health_check_loop_exception_handling(self, manager):
        """测试：健康检查循环异常处理"""
        manager.is_monitoring = True
        
        # 模拟_perform_health_check抛出异常
        with patch.object(manager, '_perform_health_check', side_effect=Exception("Health check failed")):
            # 创建健康检查任务
            task = asyncio.create_task(manager._health_check_loop(0.1))
            
            # 等待一小段时间让异常发生
            await asyncio.sleep(0.2)
            
            # 停止监控
            manager.is_monitoring = False
            
            # 等待任务完成
            await task
            
            # 验证任务正常结束
            assert task.done()
    
    @pytest.mark.asyncio
    async def test_health_check_loop_cancelled(self, manager):
        """测试：健康检查循环被取消"""
        manager.is_monitoring = True

        # 创建健康检查任务
        task = asyncio.create_task(manager._health_check_loop(60))

        # 等待一小段时间
        await asyncio.sleep(0.1)

        # 停止监控（这会设置is_monitoring为False，导致循环退出）
        manager.is_monitoring = False

        # 等待任务完成
        await task

        # 验证任务正常完成
        assert task.done()
        assert not task.cancelled()


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerHealthCheck:
    """测试网络连接管理器健康检查功能"""
    
    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()
    
    @pytest.mark.asyncio
    async def test_perform_health_check_websocket_closed(self, manager):
        """测试：健康检查发现已关闭的WebSocket连接"""
        # 添加一个已关闭的WebSocket连接
        connection_id = "ws_test_closed"
        mock_connection = AsyncMock()
        mock_connection.closed = True
        
        manager.connections[connection_id] = {
            'type': 'websocket',
            'connection': mock_connection,
            'created_at': datetime.now(timezone.utc)
        }
        
        # 执行健康检查
        await manager._perform_health_check()
        
        # 验证已关闭的连接被清理
        assert connection_id not in manager.connections
    
    @pytest.mark.asyncio
    async def test_perform_health_check_http_session_closed(self, manager):
        """测试：健康检查发现已关闭的HTTP会话"""
        # 添加一个已关闭的HTTP会话
        connection_id = "http_test_closed"
        mock_session = AsyncMock()
        mock_session.closed = True
        
        manager.connections[connection_id] = {
            'type': 'http_session',
            'session': mock_session,
            'session_name': 'test_session',
            'created_at': datetime.now(timezone.utc)
        }
        
        # 执行健康检查
        await manager._perform_health_check()
        
        # 验证已关闭的会话被清理
        assert connection_id not in manager.connections
    
    @pytest.mark.asyncio
    async def test_perform_health_check_active_connections(self, manager):
        """测试：健康检查保留活跃连接"""
        # 添加一个活跃的WebSocket连接
        connection_id = "ws_test_active"
        mock_connection = AsyncMock()
        mock_connection.closed = False
        
        manager.connections[connection_id] = {
            'type': 'websocket',
            'connection': mock_connection,
            'created_at': datetime.now(timezone.utc)
        }
        
        # 执行健康检查
        await manager._perform_health_check()
        
        # 验证活跃连接被保留
        assert connection_id in manager.connections
    
    @pytest.mark.asyncio
    async def test_perform_health_check_update_stats(self, manager):
        """测试：健康检查更新统计信息"""
        # 添加多个已关闭的连接
        for i in range(3):
            connection_id = f"ws_test_closed_{i}"
            mock_connection = AsyncMock()
            mock_connection.closed = True
            
            manager.connections[connection_id] = {
                'type': 'websocket',
                'connection': mock_connection,
                'created_at': datetime.now(timezone.utc)
            }
        
        # 设置初始统计
        manager.connection_stats['active_connections'] = 3
        
        # 执行健康检查
        await manager._perform_health_check()
        
        # 验证统计被更新
        assert len(manager.connections) == 0
        assert manager.connection_stats['active_connections'] == 0


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerConnectivityTesting:
    """测试网络连接管理器连接性测试功能"""

    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()

    @pytest.mark.asyncio
    async def test_test_connectivity_websocket_success(self, manager):
        """测试：WebSocket连接性测试成功"""
        url = "wss://api.example.com/ws"
        exchange_name = "test_exchange"

        # 模拟成功的WebSocket连接
        mock_connection = AsyncMock()
        mock_proxy_config = Mock()
        mock_proxy_config.has_proxy.return_value = True

        with patch.object(manager.websocket_manager, 'connect', return_value=mock_connection):
            with patch.object(manager.proxy_manager, 'get_proxy_config', return_value=mock_proxy_config):
                result = await manager.test_connectivity(url, "websocket", exchange_name, timeout=5)

                assert result['success'] is True
                assert result['url'] == url
                assert result['type'] == "websocket"
                assert result['exchange'] == exchange_name
                assert result['proxy_used'] is True
                assert result['response_time'] is not None
                assert result['error'] is None

                # 验证连接被关闭
                mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connectivity_websocket_failure(self, manager):
        """测试：WebSocket连接性测试失败"""
        url = "wss://api.example.com/ws"
        exchange_name = "test_exchange"

        # 模拟WebSocket连接返回None
        with patch.object(manager.websocket_manager, 'connect', return_value=None):
            result = await manager.test_connectivity(url, "websocket", exchange_name, timeout=5)

            assert result['success'] is False
            assert result['url'] == url
            assert result['type'] == "websocket"
            assert result['exchange'] == exchange_name
            assert result['response_time'] is not None
            assert result['error'] is None

    @pytest.mark.asyncio
    async def test_test_connectivity_websocket_exception(self, manager):
        """测试：WebSocket连接性测试异常"""
        url = "wss://api.example.com/ws"
        exchange_name = "test_exchange"

        # 模拟WebSocket连接抛出异常
        with patch.object(manager.websocket_manager, 'connect', side_effect=Exception("Connection error")):
            result = await manager.test_connectivity(url, "websocket", exchange_name, timeout=5)

            assert result['success'] is False
            assert result['url'] == url
            assert result['type'] == "websocket"
            assert result['exchange'] == exchange_name
            assert result['error'] == "Connection error"
            assert result['response_time'] is not None

    @pytest.mark.asyncio
    async def test_test_connectivity_http_success(self, manager):
        """测试：HTTP连接性测试成功"""
        url = "https://api.example.com/test"
        exchange_name = "test_exchange"

        # 模拟成功的HTTP响应
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value = mock_response

        with patch.object(manager, 'create_http_session', return_value=mock_session):
            with patch.object(manager.session_manager, 'close_session'):
                result = await manager.test_connectivity(url, "http", exchange_name, timeout=5)

                assert result['success'] is True
                assert result['url'] == url
                assert result['type'] == "http"
                assert result['exchange'] == exchange_name
                assert result['status_code'] == 200
                assert result['response_time'] is not None
                assert result['error'] is None

    @pytest.mark.asyncio
    async def test_test_connectivity_http_client_error(self, manager):
        """测试：HTTP连接性测试客户端错误"""
        url = "https://api.example.com/test"
        exchange_name = "test_exchange"

        # 模拟HTTP 4xx响应
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_session.get.return_value = mock_response

        with patch.object(manager, 'create_http_session', return_value=mock_session):
            with patch.object(manager.session_manager, 'close_session'):
                result = await manager.test_connectivity(url, "http", exchange_name, timeout=5)

                assert result['success'] is False
                assert result['status_code'] == 404
                assert result['response_time'] is not None

    @pytest.mark.asyncio
    async def test_test_connectivity_http_exception(self, manager):
        """测试：HTTP连接性测试异常"""
        url = "https://api.example.com/test"
        exchange_name = "test_exchange"

        # 模拟HTTP请求抛出异常
        with patch.object(manager, 'create_http_session', side_effect=Exception("HTTP error")):
            result = await manager.test_connectivity(url, "http", exchange_name, timeout=5)

            assert result['success'] is False
            assert result['url'] == url
            assert result['type'] == "http"
            assert result['exchange'] == exchange_name
            assert result['error'] == "HTTP error"
            assert result['response_time'] is not None


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerStatisticsUpdate:
    """测试网络连接管理器统计更新功能"""

    @pytest.fixture
    def manager(self):
        """创建测试用的连接管理器"""
        return NetworkConnectionManager()

    def test_update_connection_stats_closed_action(self, manager):
        """测试：更新连接统计 - 关闭动作"""
        # 设置初始统计
        manager.connection_stats['active_connections'] = 5

        # 更新统计 - 关闭动作
        manager._update_connection_stats('websocket', 'closed', None)

        # 验证活跃连接数减少
        assert manager.connection_stats['active_connections'] == 4

    def test_update_connection_stats_closed_action_zero_minimum(self, manager):
        """测试：更新连接统计 - 关闭动作不会低于0"""
        # 设置初始统计为0
        manager.connection_stats['active_connections'] = 0

        # 更新统计 - 关闭动作
        manager._update_connection_stats('websocket', 'closed', None)

        # 验证活跃连接数不会低于0
        assert manager.connection_stats['active_connections'] == 0

    def test_update_connection_stats_created_with_proxy(self, manager):
        """测试：更新连接统计 - 使用代理创建"""
        mock_proxy_config = Mock()
        mock_proxy_config.has_proxy.return_value = True

        # 更新统计 - 创建WebSocket连接
        manager._update_connection_stats('websocket', 'created', mock_proxy_config)

        # 验证统计更新
        assert manager.connection_stats['total_connections'] == 1
        assert manager.connection_stats['active_connections'] == 1
        assert manager.connection_stats['websocket_connections'] == 1
        assert manager.connection_stats['proxy_connections'] == 1
        assert manager.connection_stats['direct_connections'] == 0

    def test_update_connection_stats_created_without_proxy(self, manager):
        """测试：更新连接统计 - 不使用代理创建"""
        mock_proxy_config = Mock()
        mock_proxy_config.has_proxy.return_value = False

        # 更新统计 - 创建HTTP会话
        manager._update_connection_stats('http', 'created', mock_proxy_config)

        # 验证统计更新
        assert manager.connection_stats['total_connections'] == 1
        assert manager.connection_stats['active_connections'] == 1
        assert manager.connection_stats['http_sessions'] == 1
        assert manager.connection_stats['proxy_connections'] == 0
        assert manager.connection_stats['direct_connections'] == 1

    def test_update_connection_stats_created_no_proxy_config(self, manager):
        """测试：更新连接统计 - 无代理配置创建"""
        # 更新统计 - 创建连接，无代理配置
        manager._update_connection_stats('websocket', 'created', None)

        # 验证统计更新
        assert manager.connection_stats['total_connections'] == 1
        assert manager.connection_stats['active_connections'] == 1
        assert manager.connection_stats['websocket_connections'] == 1
        assert manager.connection_stats['proxy_connections'] == 0
        assert manager.connection_stats['direct_connections'] == 1

    def test_update_connection_stats_failed_action(self, manager):
        """测试：更新连接统计 - 失败动作"""
        # 更新统计 - 失败动作
        manager._update_connection_stats('websocket', 'failed', None)

        # 验证失败统计更新
        assert manager.connection_stats['failed_connections'] == 1
        assert manager.connection_stats['total_connections'] == 0
        assert manager.connection_stats['active_connections'] == 0


@pytest.mark.skipif(not HAS_CONNECTION_MODULES, reason="连接管理器模块不可用")
class TestNetworkConnectionManagerGlobalInstance:
    """测试全局网络连接管理器实例"""

    def test_global_network_manager_exists(self):
        """测试：全局网络管理器实例存在"""
        assert network_manager is not None
        assert isinstance(network_manager, NetworkConnectionManager)

    @pytest.mark.asyncio
    async def test_global_network_manager_usage(self):
        """测试：全局网络管理器实例使用"""
        # 测试获取统计信息
        stats = network_manager.get_network_stats()

        assert 'overview' in stats
        assert 'websocket' in stats
        assert 'http_sessions' in stats
        assert 'monitoring' in stats
        assert 'connections' in stats

    def test_global_network_manager_isolation(self):
        """测试：全局网络管理器与本地实例隔离"""
        # 创建本地管理器
        local_manager = NetworkConnectionManager()

        # 修改本地管理器统计
        local_manager.connection_stats['total_connections'] = 999

        # 验证全局管理器不受影响
        global_stats = network_manager.get_network_stats()
        assert global_stats['overview']['total_connections'] != 999
