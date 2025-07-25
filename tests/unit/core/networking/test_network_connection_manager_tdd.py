"""
网络连接管理器TDD测试
专门用于提升core/networking/connection_manager.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过

目标：将connection_manager.py覆盖率从25%提升到40%+
重点测试：网络连接管理、WebSocket连接、HTTP会话、健康监控、统计管理
"""

import pytest
import asyncio
import aiohttp
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

# 导入网络连接管理器模块
from core.networking.connection_manager import (
    NetworkConnectionManager, NetworkConfig, network_manager
)


class TestNetworkConfig:
    """测试网络配置"""

    def test_network_config_initialization(self):
        """测试：网络配置初始化"""
        config = NetworkConfig()
        
        # 验证默认值
        assert config.timeout == 30
        assert config.enable_proxy is True
        assert config.enable_ssl is True
        assert config.ws_ping_interval is None
        assert config.ws_ping_timeout is None
        assert config.ws_max_size is None
        assert config.http_connector_limit == 100
        assert config.http_connector_limit_per_host == 30
        assert config.http_retry_attempts == 3
        assert config.health_check_interval == 60
        assert config.connection_timeout_threshold == 300
        assert config.exchange_name is None
        assert config.disable_ssl_for_exchanges is None

    def test_network_config_custom_initialization(self):
        """测试：自定义网络配置初始化"""
        config = NetworkConfig(
            timeout=60,
            enable_proxy=False,
            enable_ssl=False,
            ws_ping_interval=30,
            ws_ping_timeout=10,
            ws_max_size=1024*1024,
            http_connector_limit=200,
            http_connector_limit_per_host=50,
            http_retry_attempts=5,
            health_check_interval=120,
            connection_timeout_threshold=600,
            exchange_name="binance",
            disable_ssl_for_exchanges=["testnet"]
        )
        
        # 验证自定义值
        assert config.timeout == 60
        assert config.enable_proxy is False
        assert config.enable_ssl is False
        assert config.ws_ping_interval == 30
        assert config.ws_ping_timeout == 10
        assert config.ws_max_size == 1024*1024
        assert config.http_connector_limit == 200
        assert config.http_connector_limit_per_host == 50
        assert config.http_retry_attempts == 5
        assert config.health_check_interval == 120
        assert config.connection_timeout_threshold == 600
        assert config.exchange_name == "binance"
        assert config.disable_ssl_for_exchanges == ["testnet"]


class TestNetworkConnectionManagerInitialization:
    """测试网络连接管理器初始化"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    def test_manager_initialization(self):
        """测试：管理器初始化"""
        assert self.manager.logger is not None
        assert self.manager.websocket_manager is not None
        assert self.manager.session_manager is not None
        assert self.manager.proxy_manager is not None
        assert isinstance(self.manager.connections, dict)
        assert isinstance(self.manager.connection_stats, dict)
        assert self.manager.health_check_task is None
        assert self.manager.is_monitoring is False

    def test_connection_stats_initialization(self):
        """测试：连接统计初始化"""
        stats = self.manager.connection_stats
        
        # 验证统计项
        assert stats['total_connections'] == 0
        assert stats['active_connections'] == 0
        assert stats['failed_connections'] == 0
        assert stats['websocket_connections'] == 0
        assert stats['http_sessions'] == 0
        assert stats['proxy_connections'] == 0
        assert stats['direct_connections'] == 0

    def test_global_network_manager_instance(self):
        """测试：全局网络管理器实例"""
        assert network_manager is not None
        assert isinstance(network_manager, NetworkConnectionManager)


class TestNetworkConnectionManagerWebSocket:
    """测试网络连接管理器WebSocket功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    @pytest.mark.asyncio
    async def test_create_websocket_connection_with_mocks(self):
        """测试：创建WebSocket连接（使用模拟）"""
        # 模拟WebSocket连接
        mock_connection = Mock()
        mock_connection.closed = False
        
        # 模拟WebSocket管理器
        with patch.object(self.manager.websocket_manager, 'connect',
                         return_value=mock_connection) as mock_create:
            with patch.object(self.manager.proxy_manager, 'get_proxy_config', 
                             return_value=None) as mock_proxy:
                
                # 创建WebSocket连接
                result = await self.manager.create_websocket_connection(
                    url="wss://api.binance.com/ws/btcusdt@ticker",
                    exchange_name="binance"
                )
                
                # 验证结果
                assert result == mock_connection
                mock_create.assert_called_once()
                mock_proxy.assert_called_once()
                
                # 验证连接被记录
                assert len(self.manager.connections) == 1
                connection_id = list(self.manager.connections.keys())[0]
                conn_info = self.manager.connections[connection_id]
                
                assert conn_info['type'] == 'websocket'
                assert conn_info['url'] == "wss://api.binance.com/ws/btcusdt@ticker"
                assert conn_info['exchange'] == "binance"
                assert 'created_at' in conn_info
                assert conn_info['connection'] == mock_connection

    @pytest.mark.asyncio
    async def test_create_websocket_connection_failure(self):
        """测试：WebSocket连接创建失败"""
        # 模拟WebSocket管理器抛出异常
        with patch.object(self.manager.websocket_manager, 'connect',
                         side_effect=Exception("Connection failed")) as mock_create:
            with patch.object(self.manager.proxy_manager, 'get_proxy_config', 
                             return_value=None):
                
                # 创建WebSocket连接应该抛出异常
                with pytest.raises(Exception, match="Connection failed"):
                    await self.manager.create_websocket_connection(
                        url="wss://invalid.url",
                        exchange_name="test"
                    )
                
                # 验证失败统计被更新
                assert self.manager.connection_stats['failed_connections'] == 1
                assert len(self.manager.connections) == 0

    @pytest.mark.asyncio
    async def test_create_websocket_connection_with_custom_config(self):
        """测试：使用自定义配置创建WebSocket连接"""
        # 模拟WebSocket连接
        mock_connection = Mock()
        mock_connection.closed = False
        
        # 自定义网络配置
        custom_config = NetworkConfig(
            timeout=60,
            enable_ssl=False,
            ws_ping_interval=30,
            exchange_name="okx"
        )
        
        with patch.object(self.manager.websocket_manager, 'connect',
                         return_value=mock_connection) as mock_create:
            with patch.object(self.manager.proxy_manager, 'get_proxy_config', 
                             return_value=None):
                
                # 创建WebSocket连接
                result = await self.manager.create_websocket_connection(
                    url="wss://ws.okx.com:8443/ws/v5/public",
                    exchange_name="okx",
                    network_config=custom_config
                )
                
                # 验证结果
                assert result == mock_connection
                mock_create.assert_called_once()
                
                # 验证配置被正确传递
                call_args = mock_create.call_args
                ws_config = call_args[0][0]  # 第一个参数是WebSocket配置
                assert ws_config.timeout == 60
                assert ws_config.ssl_verify is False
                assert ws_config.ping_interval == 30

    @pytest.mark.asyncio
    async def test_create_websocket_connection_with_proxy(self):
        """测试：使用代理创建WebSocket连接"""
        # 模拟WebSocket连接和代理配置
        mock_connection = Mock()
        mock_connection.closed = False
        
        mock_proxy_config = Mock()
        mock_proxy_config.has_proxy.return_value = True
        
        with patch.object(self.manager.websocket_manager, 'connect',
                         return_value=mock_connection):
            with patch.object(self.manager.proxy_manager, 'get_proxy_config', 
                             return_value=mock_proxy_config):
                
                # 创建WebSocket连接
                result = await self.manager.create_websocket_connection(
                    url="wss://api.binance.com/ws/btcusdt@ticker",
                    exchange_name="binance"
                )
                
                # 验证结果
                assert result == mock_connection
                
                # 验证代理统计被更新
                assert self.manager.connection_stats['proxy_connections'] == 1
                assert self.manager.connection_stats['direct_connections'] == 0


class TestNetworkConnectionManagerHTTP:
    """测试网络连接管理器HTTP功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    @pytest.mark.asyncio
    async def test_create_http_session_with_mocks(self):
        """测试：创建HTTP会话（使用模拟）"""
        # 模拟HTTP会话
        mock_session = Mock()
        mock_session.closed = False
        
        with patch.object(self.manager.session_manager, 'get_session', 
                         return_value=mock_session) as mock_get_session:
            with patch.object(self.manager.proxy_manager, 'get_proxy_config', 
                             return_value=None):
                
                # 创建HTTP会话
                result = await self.manager.create_http_session(
                    session_name="binance_api",
                    exchange_name="binance"
                )
                
                # 验证结果
                assert result == mock_session
                mock_get_session.assert_called_once()
                
                # 验证会话被记录
                assert len(self.manager.connections) == 1
                session_id = list(self.manager.connections.keys())[0]
                conn_info = self.manager.connections[session_id]
                
                assert conn_info['type'] == 'http_session'
                assert conn_info['session_name'] == "binance_api"
                assert conn_info['exchange'] == "binance"
                assert 'created_at' in conn_info
                assert conn_info['session'] == mock_session

    @pytest.mark.asyncio
    async def test_create_http_session_failure(self):
        """测试：HTTP会话创建失败"""
        with patch.object(self.manager.session_manager, 'get_session', 
                         side_effect=Exception("Session creation failed")):
            with patch.object(self.manager.proxy_manager, 'get_proxy_config', 
                             return_value=None):
                
                # 创建HTTP会话应该抛出异常
                with pytest.raises(Exception, match="Session creation failed"):
                    await self.manager.create_http_session(
                        session_name="test_session",
                        exchange_name="test"
                    )
                
                # 验证失败统计被更新
                assert self.manager.connection_stats['failed_connections'] == 1
                assert len(self.manager.connections) == 0

    @pytest.mark.asyncio
    async def test_create_http_session_with_custom_config(self):
        """测试：使用自定义配置创建HTTP会话"""
        # 模拟HTTP会话
        mock_session = Mock()
        mock_session.closed = False
        
        # 自定义网络配置
        custom_config = NetworkConfig(
            timeout=120,
            http_connector_limit=50,
            http_connector_limit_per_host=10,
            http_retry_attempts=5
        )
        
        with patch.object(self.manager.session_manager, 'get_session', 
                         return_value=mock_session) as mock_get_session:
            with patch.object(self.manager.proxy_manager, 'get_proxy_config', 
                             return_value=None):
                
                # 创建HTTP会话
                result = await self.manager.create_http_session(
                    session_name="custom_session",
                    exchange_name="custom",
                    network_config=custom_config
                )
                
                # 验证结果
                assert result == mock_session
                mock_get_session.assert_called_once()
                
                # 验证配置被正确传递
                call_args = mock_get_session.call_args
                session_config = call_args[0][1]  # 第二个参数是会话配置
                assert session_config.total_timeout == 120
                assert session_config.connector_limit == 50
                assert session_config.connector_limit_per_host == 10
                assert session_config.max_retries == 5


class TestNetworkConnectionManagerConnectionManagement:
    """测试网络连接管理器连接管理功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    @pytest.mark.asyncio
    async def test_close_websocket_connection(self):
        """测试：关闭WebSocket连接"""
        # 模拟WebSocket连接
        mock_connection = Mock()
        mock_connection.close = AsyncMock()
        
        # 添加连接到管理器
        connection_id = "ws_test_1"
        self.manager.connections[connection_id] = {
            'type': 'websocket',
            'connection': mock_connection
        }
        
        # 关闭连接
        await self.manager.close_connection(connection_id)
        
        # 验证连接被关闭和移除
        mock_connection.close.assert_called_once()
        assert connection_id not in self.manager.connections

    @pytest.mark.asyncio
    async def test_close_http_session(self):
        """测试：关闭HTTP会话"""
        # 模拟HTTP会话
        mock_session = Mock()
        
        # 添加会话到管理器
        session_id = "http_test_session_test"
        self.manager.connections[session_id] = {
            'type': 'http_session',
            'session_name': 'test_session',
            'session': mock_session
        }
        
        with patch.object(self.manager.session_manager, 'close_session') as mock_close:
            # 关闭会话
            await self.manager.close_connection(session_id)
            
            # 验证会话被关闭和移除
            mock_close.assert_called_once_with('test_session')
            assert session_id not in self.manager.connections

    @pytest.mark.asyncio
    async def test_close_nonexistent_connection(self):
        """测试：关闭不存在的连接"""
        # 关闭不存在的连接不应该抛出异常
        await self.manager.close_connection("nonexistent_connection")
        
        # 验证没有连接被影响
        assert len(self.manager.connections) == 0

    @pytest.mark.asyncio
    async def test_close_connection_with_exception(self):
        """测试：关闭连接时发生异常"""
        # 模拟WebSocket连接，关闭时抛出异常
        mock_connection = Mock()
        mock_connection.close = AsyncMock(side_effect=Exception("Close failed"))

        # 添加连接到管理器
        connection_id = "ws_test_1"
        self.manager.connections[connection_id] = {
            'type': 'websocket',
            'connection': mock_connection
        }

        # 关闭连接不应该抛出异常（异常被捕获和记录）
        await self.manager.close_connection(connection_id)

        # 验证连接记录仍然存在（因为关闭失败，实际实现不会删除连接记录）
        assert connection_id in self.manager.connections

    @pytest.mark.asyncio
    async def test_close_all_connections(self):
        """测试：关闭所有连接"""
        # 添加一些模拟连接
        mock_ws_connection = Mock()
        mock_http_session = Mock()

        self.manager.connections["ws_1"] = {
            'type': 'websocket',
            'connection': mock_ws_connection
        }
        self.manager.connections["http_1"] = {
            'type': 'http_session',
            'session': mock_http_session
        }

        # 设置一些统计数据
        self.manager.connection_stats['total_connections'] = 5
        self.manager.connection_stats['active_connections'] = 2

        with patch.object(self.manager.websocket_manager, 'close_all_connections') as mock_close_ws:
            with patch.object(self.manager.session_manager, 'close_all_sessions') as mock_close_http:

                # 关闭所有连接
                await self.manager.close_all_connections()

                # 验证所有管理器的关闭方法被调用
                mock_close_ws.assert_called_once()
                mock_close_http.assert_called_once()

                # 验证连接记录被清空
                assert len(self.manager.connections) == 0

                # 验证统计被重置
                for key in self.manager.connection_stats:
                    assert self.manager.connection_stats[key] == 0

    @pytest.mark.asyncio
    async def test_close_all_connections_with_exception(self):
        """测试：关闭所有连接时发生异常"""
        with patch.object(self.manager.websocket_manager, 'close_all_connections',
                         side_effect=Exception("Close failed")):
            with patch.object(self.manager.session_manager, 'close_all_sessions'):

                # 关闭所有连接不应该抛出异常（异常被捕获和记录）
                await self.manager.close_all_connections()

                # 验证连接记录仍然被清空
                assert len(self.manager.connections) == 0


class TestNetworkConnectionManagerStatistics:
    """测试网络连接管理器统计功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    def test_update_connection_stats_websocket_created(self):
        """测试：更新WebSocket连接创建统计"""
        # 模拟代理配置
        mock_proxy_config = Mock()
        mock_proxy_config.has_proxy.return_value = True

        # 更新统计
        self.manager._update_connection_stats('websocket', 'created', mock_proxy_config)

        # 验证统计更新
        stats = self.manager.connection_stats
        assert stats['total_connections'] == 1
        assert stats['active_connections'] == 1
        assert stats['websocket_connections'] == 1
        assert stats['proxy_connections'] == 1
        assert stats['direct_connections'] == 0
        assert stats['failed_connections'] == 0

    def test_update_connection_stats_http_created_direct(self):
        """测试：更新HTTP连接创建统计（直连）"""
        # 更新统计（无代理）
        self.manager._update_connection_stats('http', 'created', None)

        # 验证统计更新
        stats = self.manager.connection_stats
        assert stats['total_connections'] == 1
        assert stats['active_connections'] == 1
        assert stats['http_sessions'] == 1
        assert stats['proxy_connections'] == 0
        assert stats['direct_connections'] == 1
        assert stats['failed_connections'] == 0

    def test_update_connection_stats_failed(self):
        """测试：更新连接失败统计"""
        # 更新失败统计
        self.manager._update_connection_stats('websocket', 'failed', None)

        # 验证统计更新
        stats = self.manager.connection_stats
        assert stats['total_connections'] == 0
        assert stats['active_connections'] == 0
        assert stats['failed_connections'] == 1

    def test_update_connection_stats_closed(self):
        """测试：更新连接关闭统计"""
        # 先创建一些连接
        self.manager.connection_stats['active_connections'] = 3

        # 更新关闭统计
        self.manager._update_connection_stats('websocket', 'closed', None)

        # 验证统计更新
        assert self.manager.connection_stats['active_connections'] == 2

    def test_update_connection_stats_closed_zero_minimum(self):
        """测试：更新连接关闭统计（确保不会低于0）"""
        # 活跃连接数为0
        self.manager.connection_stats['active_connections'] = 0

        # 更新关闭统计
        self.manager._update_connection_stats('websocket', 'closed', None)

        # 验证统计不会低于0
        assert self.manager.connection_stats['active_connections'] == 0

    def test_get_network_stats(self):
        """测试：获取网络统计"""
        # 设置一些统计数据
        self.manager.connection_stats['total_connections'] = 10
        self.manager.connection_stats['active_connections'] = 5
        self.manager.connection_stats['failed_connections'] = 2

        # 模拟子管理器统计
        with patch.object(self.manager.websocket_manager, 'get_connection_stats',
                         return_value={'total': 3}):
            with patch.object(self.manager.session_manager, 'get_session_stats',
                             return_value={'total': 2}):

                # 获取统计
                stats = self.manager.get_network_stats()

                # 验证统计数据
                assert isinstance(stats, dict)
                assert 'overview' in stats
                assert 'websocket' in stats
                assert 'http_sessions' in stats
                assert 'monitoring' in stats
                assert 'connections' in stats

                # 验证概览统计
                overview = stats['overview']
                assert overview['total_connections'] == 10
                assert overview['active_connections'] == 5
                assert overview['failed_connections'] == 2


class TestNetworkConnectionManagerHealthMonitoring:
    """测试网络连接管理器健康监控功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        """测试：启动健康监控"""
        # 启动健康监控
        await self.manager.start_monitoring(interval=1)

        # 验证监控状态
        assert self.manager.is_monitoring is True
        assert self.manager.health_check_task is not None
        assert not self.manager.health_check_task.done()

        # 停止监控
        await self.manager.stop_monitoring()

    @pytest.mark.asyncio
    async def test_start_monitoring_already_running(self):
        """测试：启动已经运行的健康监控"""
        # 启动健康监控
        await self.manager.start_monitoring(interval=1)
        first_task = self.manager.health_check_task

        # 再次启动应该不会创建新任务
        await self.manager.start_monitoring(interval=1)

        # 验证任务没有改变
        assert self.manager.health_check_task == first_task

        # 停止监控
        await self.manager.stop_monitoring()

    @pytest.mark.asyncio
    async def test_stop_monitoring(self):
        """测试：停止健康监控"""
        # 启动健康监控
        await self.manager.start_monitoring(interval=1)
        assert self.manager.is_monitoring is True

        # 停止健康监控
        await self.manager.stop_monitoring()

        # 验证监控状态
        assert self.manager.is_monitoring is False
        # 注意：实际实现中，health_check_task在停止后仍然存在（已取消状态），不会设置为None
        assert self.manager.health_check_task is not None
        assert self.manager.health_check_task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_monitoring_not_running(self):
        """测试：停止未运行的健康监控"""
        # 停止未运行的监控不应该抛出异常
        await self.manager.stop_monitoring()

        # 验证状态
        assert self.manager.is_monitoring is False
        assert self.manager.health_check_task is None

    @pytest.mark.asyncio
    async def test_perform_health_check_with_stale_connections(self):
        """测试：执行健康检查（包含过期连接）"""
        # 添加一些模拟连接
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)

        # WebSocket连接（已关闭）
        mock_ws_connection = Mock()
        mock_ws_connection.closed = True
        mock_ws_connection.close = AsyncMock()  # 添加close方法

        self.manager.connections["ws_stale"] = {
            'type': 'websocket',
            'connection': mock_ws_connection,
            'created_at': old_time
        }

        # HTTP会话（已关闭）
        mock_http_session = Mock()
        mock_http_session.closed = True

        self.manager.connections["http_stale"] = {
            'type': 'http_session',
            'session': mock_http_session,
            'session_name': 'test_session',  # 添加session_name
            'created_at': old_time
        }

        # 模拟session_manager的close_session方法
        with patch.object(self.manager.session_manager, 'close_session', new_callable=AsyncMock):
            # 执行健康检查
            await self.manager._perform_health_check()

            # 验证过期连接被移除
            assert "ws_stale" not in self.manager.connections
            assert "http_stale" not in self.manager.connections

    @pytest.mark.asyncio
    async def test_perform_health_check_with_healthy_connections(self):
        """测试：执行健康检查（健康连接）"""
        # 添加健康的连接
        mock_ws_connection = Mock()
        mock_ws_connection.closed = False

        self.manager.connections["ws_healthy"] = {
            'type': 'websocket',
            'connection': mock_ws_connection,
            'created_at': datetime.now(timezone.utc)
        }

        # 执行健康检查
        await self.manager._perform_health_check()

        # 验证健康连接保持
        assert "ws_healthy" in self.manager.connections


class TestNetworkConnectionManagerConnectivityTesting:
    """测试网络连接管理器连接测试功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    @pytest.mark.asyncio
    async def test_test_websocket_connectivity_success(self):
        """测试：WebSocket连接测试成功"""
        # 模拟成功的WebSocket连接
        mock_connection = Mock()
        mock_connection.close = AsyncMock()

        # 模拟代理配置
        mock_proxy_config = Mock()
        mock_proxy_config.has_proxy.return_value = False

        with patch.object(self.manager.websocket_manager, 'connect',
                         return_value=mock_connection) as mock_create:
            with patch.object(self.manager.proxy_manager, 'get_proxy_config',
                             return_value=mock_proxy_config):

                # 测试WebSocket连接
                result = await self.manager.test_connectivity(
                    url="wss://api.binance.com/ws/btcusdt@ticker",
                    connection_type="websocket",
                    exchange_name="binance",
                    timeout=10
                )

                # 验证结果
                assert result['success'] is True
                assert result['url'] == "wss://api.binance.com/ws/btcusdt@ticker"
                assert result['type'] == "websocket"
                assert result['exchange'] == "binance"
                assert result['error'] is None
                assert result['response_time'] is not None
                assert result['response_time'] >= 0
                assert 'timestamp' in result

                # 验证连接被创建和关闭
                mock_create.assert_called_once()
                mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_websocket_connectivity_failure(self):
        """测试：WebSocket连接测试失败"""
        with patch.object(self.manager.websocket_manager, 'connect',
                         side_effect=Exception("Connection failed")):
            with patch.object(self.manager.proxy_manager, 'get_proxy_config',
                             return_value=None):

                # 测试WebSocket连接
                result = await self.manager.test_connectivity(
                    url="wss://invalid.url",
                    connection_type="websocket",
                    exchange_name="test",
                    timeout=5
                )

                # 验证结果
                assert result['success'] is False
                assert result['url'] == "wss://invalid.url"
                assert result['type'] == "websocket"
                assert result['exchange'] == "test"
                assert result['error'] == "Connection failed"
                assert result['response_time'] is not None
                assert result['response_time'] >= 0

    @pytest.mark.asyncio
    async def test_test_http_connectivity_success(self):
        """测试：HTTP连接测试成功"""
        # 模拟成功的HTTP响应
        mock_response = Mock()
        mock_response.status = 200

        mock_session = Mock()
        mock_session.get = AsyncMock(return_value=mock_response)

        # 模拟aiohttp.ClientTimeout
        with patch('aiohttp.ClientTimeout') as mock_timeout:
            with patch.object(self.manager, 'create_http_session',
                             return_value=mock_session) as mock_create:
                with patch.object(self.manager.session_manager, 'close_session', new_callable=AsyncMock) as mock_close:

                    # 测试HTTP连接
                    result = await self.manager.test_connectivity(
                        url="https://api.binance.com/api/v3/ping",
                        connection_type="http",
                        exchange_name="binance",
                        timeout=10
                    )

                    # 验证结果
                    assert result['success'] is True
                    assert result['url'] == "https://api.binance.com/api/v3/ping"
                    assert result['type'] == "http"
                    assert result['exchange'] == "binance"
                    assert result['error'] is None
                    assert result['status_code'] == 200
                    assert result['response_time'] is not None
                    assert result['response_time'] >= 0

                    # 验证会话被创建和关闭
                    mock_create.assert_called_once()
                    mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_http_connectivity_client_error(self):
        """测试：HTTP连接测试客户端错误"""
        # 模拟HTTP客户端错误响应
        mock_response = Mock()
        mock_response.status = 404

        mock_session = Mock()
        mock_session.get = AsyncMock(return_value=mock_response)

        # 模拟aiohttp.ClientTimeout
        with patch('aiohttp.ClientTimeout') as mock_timeout:
            with patch.object(self.manager, 'create_http_session',
                             return_value=mock_session):
                with patch.object(self.manager.session_manager, 'close_session', new_callable=AsyncMock):

                    # 测试HTTP连接
                    result = await self.manager.test_connectivity(
                        url="https://api.binance.com/api/v3/invalid",
                        connection_type="http",
                        exchange_name="binance",
                        timeout=10
                    )

                    # 验证结果
                    assert result['success'] is False
                    assert result['status_code'] == 404
                    assert result['error'] is None

    @pytest.mark.asyncio
    async def test_test_http_connectivity_failure(self):
        """测试：HTTP连接测试失败"""
        with patch.object(self.manager, 'create_http_session',
                         side_effect=Exception("Session creation failed")):

            # 测试HTTP连接
            result = await self.manager.test_connectivity(
                url="https://invalid.url",
                connection_type="http",
                exchange_name="test",
                timeout=5
            )

            # 验证结果
            assert result['success'] is False
            assert result['url'] == "https://invalid.url"
            assert result['type'] == "http"
            assert result['exchange'] == "test"
            assert result['error'] == "Session creation failed"
            assert result['response_time'] is not None
            assert result['response_time'] >= 0

    @pytest.mark.asyncio
    async def test_test_connectivity_invalid_type(self):
        """测试：无效连接类型测试"""
        # 测试无效连接类型
        result = await self.manager.test_connectivity(
            url="tcp://example.com:8080",
            connection_type="tcp",
            exchange_name="test",
            timeout=5
        )

        # 验证结果
        assert result['success'] is False
        assert result['type'] == "tcp"
        # 实际实现中，无效类型不会设置error，而是直接返回success=False
        # 因为代码中没有else分支来处理无效类型
        assert result['response_time'] is not None

    @pytest.mark.asyncio
    async def test_test_connectivity_default_parameters(self):
        """测试：使用默认参数的连接测试"""
        with patch.object(self.manager.websocket_manager, 'connect',
                         side_effect=Exception("Connection failed")):
            with patch.object(self.manager.proxy_manager, 'get_proxy_config',
                             return_value=None):

                # 测试连接（使用默认参数）
                result = await self.manager.test_connectivity(
                    url="wss://test.url"
                )

                # 验证默认参数
                assert result['type'] == "websocket"  # 默认类型
                assert result['exchange'] is None  # 默认交易所
                assert result['success'] is False


class TestNetworkConnectionManagerIntegration:
    """测试网络连接管理器集成功能"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = NetworkConnectionManager()

    @pytest.mark.asyncio
    async def test_full_websocket_lifecycle(self):
        """测试：完整的WebSocket生命周期"""
        # 模拟WebSocket连接
        mock_connection = Mock()
        mock_connection.closed = False
        mock_connection.close = AsyncMock()

        with patch.object(self.manager.websocket_manager, 'connect',
                         return_value=mock_connection):
            with patch.object(self.manager.proxy_manager, 'get_proxy_config',
                             return_value=None):

                # 1. 创建WebSocket连接
                connection = await self.manager.create_websocket_connection(
                    url="wss://api.binance.com/ws/btcusdt@ticker",
                    exchange_name="binance"
                )

                assert connection == mock_connection
                assert len(self.manager.connections) == 1
                assert self.manager.connection_stats['websocket_connections'] == 1

                # 2. 获取连接ID
                connection_id = list(self.manager.connections.keys())[0]

                # 3. 关闭特定连接
                await self.manager.close_connection(connection_id)

                assert len(self.manager.connections) == 0
                mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_http_lifecycle(self):
        """测试：完整的HTTP会话生命周期"""
        # 模拟HTTP会话
        mock_session = Mock()
        mock_session.closed = False

        with patch.object(self.manager.session_manager, 'get_session',
                         return_value=mock_session):
            with patch.object(self.manager.proxy_manager, 'get_proxy_config',
                             return_value=None):
                with patch.object(self.manager.session_manager, 'close_session') as mock_close:

                    # 1. 创建HTTP会话
                    session = await self.manager.create_http_session(
                        session_name="binance_api",
                        exchange_name="binance"
                    )

                    assert session == mock_session
                    assert len(self.manager.connections) == 1
                    assert self.manager.connection_stats['http_sessions'] == 1

                    # 2. 获取会话ID
                    session_id = list(self.manager.connections.keys())[0]

                    # 3. 关闭特定会话
                    await self.manager.close_connection(session_id)

                    assert len(self.manager.connections) == 0
                    mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_connections_management(self):
        """测试：混合连接管理"""
        # 模拟WebSocket连接和HTTP会话
        mock_ws_connection = Mock()
        mock_ws_connection.closed = False
        mock_http_session = Mock()
        mock_http_session.closed = False

        with patch.object(self.manager.websocket_manager, 'connect',
                         return_value=mock_ws_connection):
            with patch.object(self.manager.session_manager, 'get_session',
                             return_value=mock_http_session):
                with patch.object(self.manager.proxy_manager, 'get_proxy_config',
                                 return_value=None):

                    # 创建WebSocket连接
                    await self.manager.create_websocket_connection(
                        url="wss://api.binance.com/ws/btcusdt@ticker",
                        exchange_name="binance"
                    )

                    # 创建HTTP会话
                    await self.manager.create_http_session(
                        session_name="binance_api",
                        exchange_name="binance"
                    )

                    # 验证连接统计
                    assert len(self.manager.connections) == 2
                    assert self.manager.connection_stats['websocket_connections'] == 1
                    assert self.manager.connection_stats['http_sessions'] == 1
                    assert self.manager.connection_stats['total_connections'] == 2
                    assert self.manager.connection_stats['active_connections'] == 2

                    # 关闭所有连接
                    with patch.object(self.manager.websocket_manager, 'close_all_connections'):
                        with patch.object(self.manager.session_manager, 'close_all_sessions'):
                            await self.manager.close_all_connections()

                    # 验证所有连接被清理
                    assert len(self.manager.connections) == 0
                    for key in self.manager.connection_stats:
                        assert self.manager.connection_stats[key] == 0
