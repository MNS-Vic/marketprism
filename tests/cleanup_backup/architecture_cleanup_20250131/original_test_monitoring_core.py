#!/usr/bin/env python3
"""
Monitoring模块核心功能TDD测试

基于验证成功的TDD方法论，通过测试发现monitoring模块的设计问题并驱动改进
覆盖：metrics.py, health.py, memory_profiler.py等核心组件
"""
import pytest
import asyncio
import sys
import os
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# 添加模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))


@pytest.mark.unit
class TestHealthChecker:
    """测试健康检查器核心功能"""
    
    def test_health_checker_import(self):
        """TDD发现问题: 健康检查器是否能正确导入"""
        try:
            from core.monitoring.health import HealthChecker
            assert HealthChecker is not None
        except ImportError as e:
            pytest.fail(f"TDD发现问题: 无法导入HealthChecker - {e}")
    
    def test_health_checker_initialization(self):
        """测试健康检查器初始化"""
        try:
            from core.monitoring.health import HealthChecker
            
            checker = HealthChecker()
            assert hasattr(checker, 'checks')
            assert hasattr(checker, 'status')
            
        except Exception as e:
            pytest.fail(f"TDD发现问题: HealthChecker初始化失败 - {e}")
    
    @pytest.mark.asyncio
    async def test_health_checker_basic_functionality(self):
        """测试健康检查器基础功能"""
        try:
            from core.monitoring.health import HealthChecker
            
            checker = HealthChecker()
            
            # 检查是否有基础方法
            required_methods = ['add_check', 'remove_check', 'run_checks', 'get_status']
            for method in required_methods:
                if not hasattr(checker, method):
                    pytest.fail(f"TDD发现设计问题: HealthChecker缺少方法 {method}")
            
            # 测试基础功能
            if hasattr(checker, 'get_status'):
                status = checker.get_status()
                assert isinstance(status, dict)
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: HealthChecker基础功能失败 - {e}")
    
    def test_health_check_registration(self):
        """TDD发现问题: 健康检查注册机制"""
        try:
            from core.monitoring.health import HealthChecker
            
            checker = HealthChecker()
            
            def dummy_check():
                return {"status": "healthy"}
            
            # 测试添加检查
            if hasattr(checker, 'add_check'):
                checker.add_check("dummy", dummy_check)
                
                # 检查是否存储了检查
                if hasattr(checker, 'checks'):
                    assert 'dummy' in checker.checks or len(checker.checks) > 0
                
        except Exception as e:
            pytest.fail(f"TDD发现设计问题: 健康检查注册失败 - {e}")


@pytest.mark.unit
class TestMetricsCollector:
    """测试指标收集器核心功能"""
    
    def test_metrics_collector_import(self):
        """TDD发现问题: 指标收集器是否能正确导入"""
        try:
            from core.monitoring.metrics import MetricsCollector
            assert MetricsCollector is not None
        except ImportError as e:
            pytest.fail(f"TDD发现问题: 无法导入MetricsCollector - {e}")
    
    def test_metrics_collector_initialization(self):
        """测试指标收集器初始化"""
        try:
            from core.monitoring.metrics import MetricsCollector
            
            collector = MetricsCollector()
            
            # 检查基础属性
            basic_attrs = ['counters', 'gauges', 'histograms', 'timers']
            for attr in basic_attrs:
                if not hasattr(collector, attr):
                    pytest.fail(f"TDD发现设计问题: MetricsCollector缺少属性 {attr}")
                    
        except Exception as e:
            pytest.fail(f"TDD发现问题: MetricsCollector初始化失败 - {e}")
    
    def test_metrics_basic_operations(self):
        """测试指标基础操作"""
        try:
            from core.monitoring.metrics import MetricsCollector
            
            collector = MetricsCollector()
            
            # 检查基础方法
            required_methods = [
                'increment_counter', 'set_gauge', 'record_histogram', 
                'start_timer', 'stop_timer', 'get_metrics'
            ]
            
            missing_methods = []
            for method in required_methods:
                if not hasattr(collector, method):
                    missing_methods.append(method)
            
            if missing_methods:
                pytest.fail(f"TDD发现设计问题: MetricsCollector缺少方法: {missing_methods}")
            
            # 测试基础操作
            if hasattr(collector, 'increment_counter'):
                collector.increment_counter('test_counter')
                
            if hasattr(collector, 'set_gauge'):
                collector.set_gauge('test_gauge', 42)
                
            if hasattr(collector, 'get_metrics'):
                metrics = collector.get_metrics()
                assert isinstance(metrics, dict)
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: MetricsCollector基础操作失败 - {e}")
    
    def test_counter_functionality(self):
        """TDD发现问题: 计数器功能测试"""
        try:
            from core.monitoring.metrics import MetricsCollector
            
            collector = MetricsCollector()
            
            if hasattr(collector, 'increment_counter'):
                # 测试计数器增加
                collector.increment_counter('requests')
                collector.increment_counter('requests', 5)
                
                # 检查计数器值
                if hasattr(collector, 'get_counter'):
                    count = collector.get_counter('requests')
                    assert count >= 6  # 1 + 5
                elif hasattr(collector, 'get_metrics'):
                    metrics = collector.get_metrics()
                    # 应该包含计数器数据
                    assert 'requests' in str(metrics) or 'counters' in metrics
                    
        except Exception as e:
            pytest.fail(f"TDD发现问题: 计数器功能失败 - {e}")


@pytest.mark.unit
class TestMemoryProfiler:
    """测试内存分析器核心功能"""
    
    def test_memory_profiler_import(self):
        """TDD发现问题: 内存分析器是否能正确导入"""
        try:
            from core.monitoring.memory_profiler import MemoryProfiler
            assert MemoryProfiler is not None
        except ImportError as e:
            pytest.fail(f"TDD发现问题: 无法导入MemoryProfiler - {e}")
    
    def test_memory_profiler_initialization(self):
        """测试内存分析器初始化"""
        try:
            from core.monitoring.memory_profiler import MemoryProfiler
            
            profiler = MemoryProfiler()
            
            # 检查基础属性
            if not hasattr(profiler, 'enabled'):
                pytest.fail("TDD发现设计问题: MemoryProfiler缺少enabled属性")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: MemoryProfiler初始化失败 - {e}")
    
    def test_memory_profiler_basic_functionality(self):
        """测试内存分析器基础功能"""
        try:
            from core.monitoring.memory_profiler import MemoryProfiler
            
            profiler = MemoryProfiler()
            
            # 检查基础方法
            required_methods = ['start_profiling', 'stop_profiling', 'get_memory_usage', 'get_stats']
            missing_methods = []
            
            for method in required_methods:
                if not hasattr(profiler, method):
                    missing_methods.append(method)
            
            if missing_methods:
                pytest.fail(f"TDD发现设计问题: MemoryProfiler缺少方法: {missing_methods}")
            
            # 测试基础功能
            if hasattr(profiler, 'get_memory_usage'):
                usage = profiler.get_memory_usage()
                assert isinstance(usage, (int, float, dict))
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: MemoryProfiler基础功能失败 - {e}")


@pytest.mark.unit
class TestMonitoringIntegration:
    """测试监控模块集成功能"""
    
    def test_monitoring_module_structure(self):
        """TDD发现问题: 监控模块结构完整性"""
        try:
            from marketprism_collector import monitoring
            
            # 检查核心组件是否可导入
            core_components = ['HealthChecker', 'MetricsCollector', 'MemoryProfiler']
            missing_components = []
            
            for component in core_components:
                try:
                    getattr(monitoring, component)
                except AttributeError:
                    missing_components.append(component)
            
            if missing_components:
                pytest.fail(f"TDD发现设计问题: monitoring模块缺少组件: {missing_components}")
                
        except ImportError as e:
            pytest.fail(f"TDD发现问题: monitoring模块导入失败 - {e}")
    
    def test_monitoring_manager_exists(self):
        """TDD发现问题: 是否存在统一的监控管理器"""
        try:
            # 尝试导入监控管理器
            possible_managers = [
                'MonitoringManager', 
                'MonitoringService', 
                'Monitor',
                'SystemMonitor'
            ]
            
            manager_found = False
            for manager_name in possible_managers:
                try:
                    import marketprism_collector.monitoring as monitoring_module
                    if hasattr(monitoring_module, manager_name):
                        manager_found = True
                        break
                except:
                    pass
            
            if not manager_found:
                pytest.fail("TDD发现设计问题: monitoring模块缺少统一管理器")
                
        except Exception as e:
            # 这可能表明需要创建统一管理器
            pytest.fail(f"TDD发现设计问题: monitoring模块缺少统一接口 - {e}")


@pytest.mark.unit
class TestMonitoringDesignIssues:
    """TDD专门测试监控模块设计问题的测试类"""
    
    def test_prometheus_integration(self):
        """TDD发现问题: 是否支持Prometheus指标导出"""
        try:
            from core.monitoring.metrics import MetricsCollector
            
            collector = MetricsCollector()
            
            # 检查Prometheus支持
            prometheus_methods = ['get_prometheus_metrics', 'export_prometheus', 'register_prometheus']
            
            missing_prometheus = []
            for method in prometheus_methods:
                if not hasattr(collector, method):
                    missing_prometheus.append(method)
            
            if missing_prometheus:
                pytest.fail(f"TDD发现设计问题: MetricsCollector缺少Prometheus支持: {missing_prometheus}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: Prometheus集成测试失败 - {e}")
    
    def test_async_monitoring_support(self):
        """TDD发现问题: 是否支持异步监控"""
        try:
            from core.monitoring.health import HealthChecker
            
            checker = HealthChecker()
            
            # 检查异步支持
            if hasattr(checker, 'run_checks'):
                import inspect
                if not inspect.iscoroutinefunction(checker.run_checks):
                    pytest.fail("TDD发现设计问题: HealthChecker.run_checks应该支持异步")
                    
        except Exception as e:
            pytest.fail(f"TDD发现问题: 异步监控支持测试失败 - {e}")
    
    def test_monitoring_configuration(self):
        """TDD发现问题: 监控配置支持"""
        try:
            from core.monitoring.metrics import MetricsCollector
            
            # 测试配置支持
            try:
                collector = MetricsCollector(config={'enabled': True, 'interval': 30})
            except TypeError:
                # 可能不支持配置参数
                pytest.fail("TDD发现设计问题: MetricsCollector不支持配置参数")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 监控配置测试失败 - {e}")
    
    def test_monitoring_lifecycle(self):
        """TDD发现问题: 监控生命周期管理"""
        try:
            from core.monitoring.health import HealthChecker
            
            checker = HealthChecker()
            
            # 检查生命周期方法
            lifecycle_methods = ['start', 'stop', 'restart', 'is_running']
            missing_lifecycle = []
            
            for method in lifecycle_methods:
                if not hasattr(checker, method):
                    missing_lifecycle.append(method)
            
            if missing_lifecycle:
                pytest.fail(f"TDD发现设计问题: HealthChecker缺少生命周期方法: {missing_lifecycle}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 生命周期管理测试失败 - {e}") 