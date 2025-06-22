"""
数据收集器增强TDD测试
专注于提升覆盖率到25%+，测试未覆盖的核心功能和边缘情况
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from typing import Dict, Any, Optional, List

try:
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../services/data-collector/src'))
    
    from marketprism_collector.collector import (
        EnterpriseMonitoringService, HealthChecker, CORE_MONITORING_AVAILABLE
    )
    from marketprism_collector.core_services import core_services
    HAS_COLLECTOR_MODULES = True
except ImportError as e:
    print(f"Import error: {e}")
    HAS_COLLECTOR_MODULES = False


@pytest.mark.skipif(not HAS_COLLECTOR_MODULES, reason="数据收集器模块不可用")
class TestHealthCheckerFallback:
    """测试降级版本的HealthChecker"""
    
    def test_health_checker_init(self):
        """测试：HealthChecker初始化"""
        health_checker = HealthChecker()
        
        # 验证初始化状态
        assert hasattr(health_checker, 'checks')
        assert isinstance(health_checker.checks, dict)
        assert len(health_checker.checks) == 0
    
    def test_register_check_basic(self):
        """测试：注册基本健康检查"""
        health_checker = HealthChecker()
        
        def dummy_check():
            return "healthy"
        
        health_checker.register_check("test_check", dummy_check)
        
        # 验证检查被注册
        assert "test_check" in health_checker.checks
        assert health_checker.checks["test_check"]["func"] is dummy_check
        assert health_checker.checks["test_check"]["timeout"] == 5.0
    
    def test_register_check_with_timeout(self):
        """测试：注册带超时的健康检查"""
        health_checker = HealthChecker()
        
        def dummy_check():
            return "healthy"
        
        health_checker.register_check("test_check", dummy_check, timeout=10.0)
        
        # 验证超时设置
        assert health_checker.checks["test_check"]["timeout"] == 10.0
    
    @pytest.mark.asyncio
    async def test_check_health_all_healthy(self):
        """测试：所有检查都健康的情况"""
        health_checker = HealthChecker()
        
        def check1():
            return "service1_ok"
        
        def check2():
            return "service2_ok"
        
        health_checker.register_check("service1", check1)
        health_checker.register_check("service2", check2)
        
        result = await health_checker.check_health()
        
        # 验证整体状态
        assert result.status == "healthy"
        assert isinstance(result.timestamp, datetime)
        assert result.uptime_seconds == 0
        
        # 验证各项检查结果
        assert "service1" in result.checks
        assert "service2" in result.checks
        assert result.checks["service1"]["status"] == "healthy"
        assert result.checks["service1"]["result"] == "service1_ok"
        assert result.checks["service2"]["status"] == "healthy"
        assert result.checks["service2"]["result"] == "service2_ok"
    
    @pytest.mark.asyncio
    async def test_check_health_with_failure(self):
        """测试：有检查失败的情况"""
        health_checker = HealthChecker()
        
        def healthy_check():
            return "ok"
        
        def failing_check():
            raise Exception("Service unavailable")
        
        health_checker.register_check("healthy_service", healthy_check)
        health_checker.register_check("failing_service", failing_check)
        
        result = await health_checker.check_health()
        
        # 验证整体状态为不健康
        assert result.status == "unhealthy"
        
        # 验证健康检查结果
        assert result.checks["healthy_service"]["status"] == "healthy"
        assert result.checks["healthy_service"]["result"] == "ok"
        
        # 验证失败检查结果
        assert result.checks["failing_service"]["status"] == "unhealthy"
        assert "Service unavailable" in result.checks["failing_service"]["error"]
    
    @pytest.mark.asyncio
    async def test_check_health_with_coroutine(self):
        """测试：异步检查函数"""
        health_checker = HealthChecker()
        
        async def async_check():
            await asyncio.sleep(0.01)  # 模拟异步操作
            return "async_ok"
        
        health_checker.register_check("async_service", async_check)
        
        result = await health_checker.check_health()
        
        # 验证异步检查结果
        assert result.status == "healthy"
        assert result.checks["async_service"]["status"] == "healthy"
        assert result.checks["async_service"]["result"] == "async_ok"
    
    @pytest.mark.asyncio
    async def test_check_health_empty_checks(self):
        """测试：没有注册任何检查的情况"""
        health_checker = HealthChecker()
        
        result = await health_checker.check_health()
        
        # 验证空检查列表的结果
        assert result.status == "healthy"  # 没有失败的检查，所以是健康的
        assert len(result.checks) == 0


@pytest.mark.skipif(not HAS_COLLECTOR_MODULES, reason="数据收集器模块不可用")
class TestEnterpriseMonitoringServiceNATS:
    """测试企业级监控服务的NATS功能"""
    
    def test_check_nats_connection_healthy(self):
        """测试：NATS连接健康检查"""
        # 创建模拟的发布器
        mock_publisher = Mock()
        mock_publisher.is_connected = True
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_nats_connection(mock_publisher)
            
            # 验证返回结果
            assert result is True
            
            # 验证指标记录
            mock_record.assert_called_once_with("nats_connection_status", 1)
    
    def test_check_nats_connection_unhealthy(self):
        """测试：NATS连接不健康检查"""
        # 创建模拟的发布器
        mock_publisher = Mock()
        mock_publisher.is_connected = False
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_nats_connection(mock_publisher)
            
            # 验证返回结果
            assert result is False
            
            # 验证指标记录
            mock_record.assert_called_once_with("nats_connection_status", 0)
    
    def test_check_nats_connection_no_publisher(self):
        """测试：没有发布器的情况"""
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_nats_connection(None)
            
            # 验证返回结果
            assert result is False
            
            # 验证指标记录
            mock_record.assert_called_once_with("nats_connection_status", 0)
    
    def test_check_nats_connection_no_attribute(self):
        """测试：发布器没有is_connected属性的情况"""
        # 创建没有is_connected属性的发布器
        mock_publisher = Mock(spec=[])  # 空spec，没有任何属性
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_nats_connection(mock_publisher)
            
            # 验证返回结果
            assert result is False
            
            # 验证指标记录
            mock_record.assert_called_once_with("nats_connection_status", 0)
    
    def test_check_nats_connection_exception(self):
        """测试：NATS连接检查异常处理"""
        # 创建会抛出异常的发布器
        mock_publisher = Mock()
        # 设置is_connected属性为异常
        type(mock_publisher).is_connected = PropertyMock(side_effect=Exception("Connection error"))

        with patch.object(core_services, 'handle_error') as mock_handle_error:
            result = EnterpriseMonitoringService.check_nats_connection(mock_publisher)

            # 验证返回结果
            assert result is False

            # 验证错误处理
            mock_handle_error.assert_called_once()
            args = mock_handle_error.call_args[0]
            assert isinstance(args[0], Exception)


@pytest.mark.skipif(not HAS_COLLECTOR_MODULES, reason="数据收集器模块不可用")
class TestEnterpriseMonitoringServiceExchange:
    """测试企业级监控服务的交易所功能"""
    
    def test_check_exchange_connections_all_connected(self):
        """测试：所有交易所都连接的情况"""
        # 创建模拟的适配器
        mock_adapter1 = Mock()
        mock_adapter1.is_connected = True
        mock_adapter2 = Mock()
        mock_adapter2.is_connected = True
        
        adapters = {
            "binance": mock_adapter1,
            "okx": mock_adapter2
        }
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            # 验证返回结果
            assert result is True
            
            # 验证指标记录
            assert mock_record.call_count == 2
            mock_record.assert_any_call("exchange_connections_active", 2)
            mock_record.assert_any_call("exchange_connections_total", 2)
    
    def test_check_exchange_connections_partial_connected(self):
        """测试：部分交易所连接的情况"""
        # 创建模拟的适配器
        mock_adapter1 = Mock()
        mock_adapter1.is_connected = True
        mock_adapter2 = Mock()
        mock_adapter2.is_connected = False
        
        adapters = {
            "binance": mock_adapter1,
            "okx": mock_adapter2
        }
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            # 验证返回结果
            assert result is True  # 只要有一个连接就返回True
            
            # 验证指标记录
            mock_record.assert_any_call("exchange_connections_active", 1)
            mock_record.assert_any_call("exchange_connections_total", 2)
    
    def test_check_exchange_connections_none_connected(self):
        """测试：没有交易所连接的情况"""
        # 创建模拟的适配器
        mock_adapter1 = Mock()
        mock_adapter1.is_connected = False
        mock_adapter2 = Mock()
        mock_adapter2.is_connected = False
        
        adapters = {
            "binance": mock_adapter1,
            "okx": mock_adapter2
        }
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            # 验证返回结果
            assert result is False
            
            # 验证指标记录
            mock_record.assert_any_call("exchange_connections_active", 0)
            mock_record.assert_any_call("exchange_connections_total", 2)
    
    def test_check_exchange_connections_no_attribute(self):
        """测试：适配器没有is_connected属性的情况"""
        # 创建没有is_connected属性的适配器
        mock_adapter1 = Mock(spec=[])  # 空spec
        mock_adapter2 = Mock()
        mock_adapter2.is_connected = True
        
        adapters = {
            "binance": mock_adapter1,
            "okx": mock_adapter2
        }
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            # 验证返回结果
            assert result is True  # 有一个连接
            
            # 验证指标记录
            mock_record.assert_any_call("exchange_connections_active", 1)
            mock_record.assert_any_call("exchange_connections_total", 2)
    
    def test_check_exchange_connections_empty_adapters(self):
        """测试：没有适配器的情况"""
        adapters = {}
        
        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)
            
            # 验证返回结果
            assert result is False
            
            # 验证指标记录
            mock_record.assert_any_call("exchange_connections_active", 0)
            mock_record.assert_any_call("exchange_connections_total", 0)
    
    def test_check_exchange_connections_exception(self):
        """测试：交易所连接检查异常处理"""
        # 创建会抛出异常的适配器
        mock_adapter = Mock()
        type(mock_adapter).is_connected = PropertyMock(side_effect=Exception("Connection error"))

        adapters = {"binance": mock_adapter}

        with patch.object(core_services, 'handle_error') as mock_handle_error:
            result = EnterpriseMonitoringService.check_exchange_connections(adapters)

            # 验证返回结果（异常时返回len(adapters) > 0）
            assert result is True

            # 验证错误处理
            mock_handle_error.assert_called_once()
            args = mock_handle_error.call_args[0]
            assert isinstance(args[0], Exception)


@pytest.mark.skipif(not HAS_COLLECTOR_MODULES, reason="数据收集器模块不可用")
class TestEnterpriseMonitoringServiceMemory:
    """测试企业级监控服务的内存功能"""

    @patch('psutil.Process')
    def test_check_memory_usage_healthy(self, mock_process_class):
        """测试：内存使用健康检查"""
        # 模拟psutil.Process
        mock_process = Mock()
        mock_process.memory_percent.return_value = 50.0
        mock_process_class.return_value = mock_process

        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_memory_usage()

            # 验证返回结果
            assert result is True

            # 验证指标记录
            assert mock_record.call_count == 2
            mock_record.assert_any_call("process_memory_percent", 50.0)
            mock_record.assert_any_call("memory_health_status", 1)

    @patch('psutil.Process')
    def test_check_memory_usage_unhealthy(self, mock_process_class):
        """测试：内存使用不健康检查"""
        # 模拟高内存使用
        mock_process = Mock()
        mock_process.memory_percent.return_value = 85.0
        mock_process_class.return_value = mock_process

        with patch.object(core_services, 'record_metric') as mock_record:
            result = EnterpriseMonitoringService.check_memory_usage()

            # 验证返回结果
            assert result is False

            # 验证指标记录
            mock_record.assert_any_call("process_memory_percent", 85.0)
            mock_record.assert_any_call("memory_health_status", 0)

    def test_check_memory_usage_no_psutil(self):
        """测试：psutil不可用时的降级处理"""
        with patch('builtins.__import__', side_effect=ImportError("No module named 'psutil'")):
            with patch.object(core_services, 'record_metric') as mock_record:
                result = EnterpriseMonitoringService.check_memory_usage()

                # 验证返回结果（降级时假设健康）
                assert result is True

                # 验证指标记录
                mock_record.assert_called_once_with("memory_health_status", 1)

    @patch('psutil.Process')
    def test_check_memory_usage_exception(self, mock_process_class):
        """测试：内存检查异常处理"""
        # 模拟psutil异常
        mock_process_class.side_effect = Exception("Process error")

        with patch.object(core_services, 'handle_error') as mock_handle_error:
            result = EnterpriseMonitoringService.check_memory_usage()

            # 验证返回结果（异常时假设健康）
            assert result is True

            # 验证错误处理
            mock_handle_error.assert_called_once()
            args = mock_handle_error.call_args[0]
            assert isinstance(args[0], Exception)


@pytest.mark.skipif(not HAS_COLLECTOR_MODULES, reason="数据收集器模块不可用")
class TestEnterpriseMonitoringServiceQueueMonitoring:
    """测试企业级监控服务的队列监控功能"""

    @pytest.mark.asyncio
    async def test_monitor_queue_sizes_basic(self):
        """测试：基本队列大小监控"""
        # 创建模拟适配器
        mock_adapter1 = Mock()
        mock_adapter1.get_queue_size.return_value = 10
        mock_adapter1.is_connected = True

        mock_adapter2 = Mock()
        mock_adapter2.get_queue_size.return_value = 5
        mock_adapter2.is_connected = False

        adapters = {
            "binance": mock_adapter1,
            "okx": mock_adapter2
        }

        # 模拟短暂运行后取消
        async def cancel_after_delay(duration):
            await asyncio.sleep(0.05)
            # 通过抛出CancelledError来停止监控循环
            raise asyncio.CancelledError()

        with patch.object(core_services, 'record_metric') as mock_record:
            with patch('asyncio.sleep', side_effect=cancel_after_delay):
                await EnterpriseMonitoringService.monitor_queue_sizes(adapters, interval=0.01)

                # 验证指标记录
                # 应该记录每个适配器的队列大小和连接状态，以及总队列大小
                mock_record.assert_any_call("adapter_queue_size", 10, {"adapter": "binance"})
                mock_record.assert_any_call("adapter_queue_size", 5, {"adapter": "okx"})
                mock_record.assert_any_call("adapter_connection_status", 1, {"adapter": "binance"})
                mock_record.assert_any_call("adapter_connection_status", 0, {"adapter": "okx"})
                mock_record.assert_any_call("total_queue_size", 15)

    @pytest.mark.asyncio
    async def test_monitor_queue_sizes_no_queue_method(self):
        """测试：适配器没有get_queue_size方法的情况"""
        # 创建没有get_queue_size方法的适配器
        mock_adapter = Mock(spec=['is_connected'])
        mock_adapter.is_connected = True

        adapters = {"binance": mock_adapter}

        # 模拟短暂运行后取消
        async def cancel_after_delay(duration):
            await asyncio.sleep(0.05)
            raise asyncio.CancelledError()

        with patch.object(core_services, 'record_metric') as mock_record:
            with patch('asyncio.sleep', side_effect=cancel_after_delay):
                await EnterpriseMonitoringService.monitor_queue_sizes(adapters, interval=0.01)

                # 验证只记录连接状态，不记录队列大小
                mock_record.assert_any_call("adapter_connection_status", 1, {"adapter": "binance"})
                mock_record.assert_any_call("total_queue_size", 0)

    @pytest.mark.asyncio
    async def test_monitor_queue_sizes_adapter_exception(self):
        """测试：适配器异常处理"""
        # 创建会抛出异常的适配器
        mock_adapter = Mock()
        mock_adapter.get_queue_size.side_effect = Exception("Queue error")
        mock_adapter.is_connected = True

        adapters = {"binance": mock_adapter}

        # 模拟短暂运行后取消
        async def cancel_after_delay(duration):
            await asyncio.sleep(0.05)
            raise asyncio.CancelledError()

        with patch.object(core_services, 'handle_error') as mock_handle_error:
            with patch('asyncio.sleep', side_effect=cancel_after_delay):
                await EnterpriseMonitoringService.monitor_queue_sizes(adapters, interval=0.01)

                # 验证错误处理
                mock_handle_error.assert_called()
                args = mock_handle_error.call_args[0]
                assert isinstance(args[0], Exception)

    @pytest.mark.asyncio
    async def test_monitor_queue_sizes_general_exception(self):
        """测试：队列监控一般异常处理"""
        adapters = {"binance": Mock()}

        # 模拟第一次正常，第二次异常，第三次取消
        call_count = 0
        async def sleep_with_exception(_duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次正常
                pass
            elif call_count == 2:
                # 第二次抛出一般异常
                raise Exception("General monitoring error")
            else:
                # 第三次取消
                raise asyncio.CancelledError()

        with patch.object(core_services, 'handle_error') as mock_handle_error:
            with patch('asyncio.sleep', side_effect=sleep_with_exception):
                await EnterpriseMonitoringService.monitor_queue_sizes(adapters, interval=0.01)

                # 验证错误处理
                mock_handle_error.assert_called()
                args = mock_handle_error.call_args[0]
                assert isinstance(args[0], Exception)


@pytest.mark.skipif(not HAS_COLLECTOR_MODULES, reason="数据收集器模块不可用")
class TestEnterpriseMonitoringServiceSystemMetrics:
    """测试企业级监控服务的系统指标功能"""

    @pytest.mark.asyncio
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    @patch('psutil.net_io_counters')
    @patch('psutil.Process')
    @patch('psutil.getloadavg')
    async def test_update_system_metrics_full_psutil(self, mock_getloadavg, mock_process_class,
                                                   mock_net_io, mock_disk_usage,
                                                   mock_virtual_memory, mock_cpu_percent):
        """测试：完整的psutil系统指标更新"""
        # 模拟psutil返回值
        mock_cpu_percent.return_value = 45.5

        mock_memory = Mock()
        mock_memory.percent = 60.2
        mock_memory.available = 8 * 1024**3  # 8GB
        mock_virtual_memory.return_value = mock_memory

        mock_disk = Mock()
        mock_disk.percent = 35.8
        mock_disk.free = 100 * 1024**3  # 100GB
        mock_disk_usage.return_value = mock_disk

        mock_net = Mock()
        mock_net.bytes_sent = 1024 * 1024 * 100  # 100MB
        mock_net.bytes_recv = 1024 * 1024 * 200  # 200MB
        mock_net_io.return_value = mock_net

        mock_process = Mock()
        mock_process.cpu_percent.return_value = 25.3
        mock_process.memory_info.return_value = Mock(rss=512 * 1024 * 1024)  # 512MB
        mock_process.num_fds.return_value = 150
        mock_process_class.return_value = mock_process

        mock_getloadavg.return_value = (1.2, 1.5, 1.8)

        # 模拟短暂运行后取消
        async def cancel_after_delay(duration):
            await asyncio.sleep(0.05)
            raise asyncio.CancelledError()

        with patch.object(core_services, 'record_metric') as mock_record:
            with patch('asyncio.sleep', side_effect=cancel_after_delay):
                await EnterpriseMonitoringService.update_system_metrics(interval=0.01)

                # 验证系统指标记录
                mock_record.assert_any_call("system_cpu_percent", 45.5)
                mock_record.assert_any_call("system_memory_percent", 60.2)
                mock_record.assert_any_call("system_memory_available_gb", 8.0)
                mock_record.assert_any_call("system_disk_percent", 35.8)
                mock_record.assert_any_call("system_disk_free_gb", 100.0)
                mock_record.assert_any_call("system_network_bytes_sent", 1024 * 1024 * 100)
                mock_record.assert_any_call("system_network_bytes_recv", 1024 * 1024 * 200)

                # 验证进程指标记录
                mock_record.assert_any_call("process_cpu_percent", 25.3)
                mock_record.assert_any_call("process_memory_mb", 512.0)
                mock_record.assert_any_call("process_open_files", 150)

                # 验证系统负载记录
                mock_record.assert_any_call("system_load_1min", 1.2)
                mock_record.assert_any_call("system_load_5min", 1.5)
                mock_record.assert_any_call("system_load_15min", 1.8)

    @pytest.mark.asyncio
    @patch('psutil.Process')
    async def test_update_system_metrics_no_getloadavg(self, mock_process_class):
        """测试：没有getloadavg的系统指标更新"""
        # 模拟没有getloadavg的psutil
        mock_process = Mock()
        mock_process.cpu_percent.return_value = 25.0
        mock_process.memory_info.return_value = Mock(rss=256 * 1024 * 1024)
        mock_process.num_fds = Mock(side_effect=AttributeError("No num_fds"))
        mock_process_class.return_value = mock_process

        # 模拟短暂运行后取消
        async def cancel_after_delay(duration):
            await asyncio.sleep(0.05)
            raise asyncio.CancelledError()

        with patch('psutil.cpu_percent', return_value=30.0):
            with patch('psutil.virtual_memory', return_value=Mock(percent=50.0, available=4*1024**3)):
                with patch('psutil.disk_usage', return_value=Mock(percent=40.0, free=50*1024**3)):
                    with patch('psutil.net_io_counters', return_value=Mock(bytes_sent=1000, bytes_recv=2000)):
                        with patch('psutil.getloadavg', side_effect=AttributeError("No getloadavg")):
                            with patch.object(core_services, 'record_metric') as mock_record:
                                with patch('asyncio.sleep', side_effect=cancel_after_delay):
                                    await EnterpriseMonitoringService.update_system_metrics(interval=0.01)

                                    # 验证基本指标记录
                                    mock_record.assert_any_call("system_cpu_percent", 30.0)
                                    mock_record.assert_any_call("process_open_files", 0)  # 降级值

    @pytest.mark.asyncio
    async def test_update_system_metrics_no_psutil(self):
        """测试：psutil不可用时的降级处理"""
        # 模拟短暂运行后取消
        async def cancel_after_delay(duration):
            await asyncio.sleep(0.05)
            raise asyncio.CancelledError()

        with patch('builtins.__import__', side_effect=ImportError("No module named 'psutil'")):
            with patch('os.getpid', return_value=12345):
                with patch.object(core_services, 'record_metric') as mock_record:
                    with patch('asyncio.sleep', side_effect=cancel_after_delay):
                        await EnterpriseMonitoringService.update_system_metrics(interval=0.01)

                        # 验证降级指标记录
                        mock_record.assert_any_call("system_process_id", 12345)

    @pytest.mark.asyncio
    async def test_update_system_metrics_exception(self):
        """测试：系统指标更新异常处理"""
        # 模拟第一次正常，第二次异常，第三次取消
        call_count = 0
        async def sleep_with_exception(duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次正常
                pass
            elif call_count == 2:
                # 第二次抛出异常
                raise Exception("System metrics error")
            else:
                # 第三次取消
                raise asyncio.CancelledError()

        with patch.object(core_services, 'handle_error') as mock_handle_error:
            with patch('asyncio.sleep', side_effect=sleep_with_exception):
                await EnterpriseMonitoringService.update_system_metrics(interval=0.01)

                # 验证错误处理
                mock_handle_error.assert_called()
                args = mock_handle_error.call_args[0]
                assert isinstance(args[0], Exception)
