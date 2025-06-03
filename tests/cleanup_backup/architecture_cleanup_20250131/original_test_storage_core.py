"""
Storage模块核心功能TDD测试

基于验证成功的TDD方法论，通过测试发现storage模块的设计问题并驱动改进
覆盖：clickhouse_writer.py, optimized_clickhouse_writer.py等核心组件
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
class TestClickHouseWriter:
    """测试ClickHouse写入器核心功能"""
    
    def test_clickhouse_writer_import(self):
        """TDD发现问题: ClickHouse写入器是否能正确导入"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            assert ClickHouseWriter is not None
        except ImportError as e:
            pytest.fail(f"TDD发现问题: 无法导入ClickHouseWriter - {e}")
    
    def test_clickhouse_writer_initialization(self):
        """测试ClickHouse写入器初始化"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            # 测试基础初始化
            writer = ClickHouseWriter()
            
            # 检查基础属性
            required_attrs = ['client', 'enabled', 'config', 'logger']
            for attr in required_attrs:
                if not hasattr(writer, attr):
                    pytest.fail(f"TDD发现设计问题: ClickHouseWriter缺少属性 {attr}")
                    
        except Exception as e:
            pytest.fail(f"TDD发现问题: ClickHouseWriter初始化失败 - {e}")
    
    def test_clickhouse_writer_configuration_support(self):
        """TDD发现问题: 配置支持测试"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            # 测试配置参数支持
            config = {
                'host': 'localhost',
                'port': 9000,
                'database': 'test_db',
                'enabled': True
            }
            
            try:
                writer = ClickHouseWriter(config=config)
                assert hasattr(writer, 'config')
            except TypeError:
                pytest.fail("TDD发现设计问题: ClickHouseWriter不支持配置参数")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: ClickHouseWriter配置测试失败 - {e}")
    
    def test_clickhouse_writer_basic_methods(self):
        """测试ClickHouse写入器基础方法"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            writer = ClickHouseWriter()
            
            # 检查基础方法
            required_methods = [
                'connect', 'disconnect', 'write_data', 'write_batch',
                'create_table', 'get_status', 'is_connected'
            ]
            
            missing_methods = []
            for method in required_methods:
                if not hasattr(writer, method):
                    missing_methods.append(method)
            
            if missing_methods:
                pytest.fail(f"TDD发现设计问题: ClickHouseWriter缺少方法: {missing_methods}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: ClickHouseWriter方法测试失败 - {e}")
    
    @pytest.mark.asyncio
    async def test_clickhouse_writer_async_support(self):
        """TDD发现问题: 异步操作支持"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            writer = ClickHouseWriter()
            
            # 检查异步方法
            async_methods = ['write_data_async', 'write_batch_async', 'connect_async']
            
            missing_async = []
            for method in async_methods:
                if not hasattr(writer, method):
                    missing_async.append(method)
            
            if missing_async:
                pytest.fail(f"TDD发现设计问题: ClickHouseWriter缺少异步方法: {missing_async}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: ClickHouseWriter异步支持测试失败 - {e}")


@pytest.mark.unit
class TestOptimizedClickHouseWriter:
    """测试优化版ClickHouse写入器"""
    
    def test_optimized_writer_import(self):
        """TDD发现问题: 优化版写入器导入测试"""
        try:
            from marketprism_collector.storage.optimized_clickhouse_writer import OptimizedClickHouseWriter
            assert OptimizedClickHouseWriter is not None
        except ImportError as e:
            pytest.fail(f"TDD发现问题: 无法导入OptimizedClickHouseWriter - {e}")
    
    def test_optimized_writer_initialization(self):
        """测试优化版写入器初始化"""
        try:
            from marketprism_collector.storage.optimized_clickhouse_writer import OptimizedClickHouseWriter
            
            writer = OptimizedClickHouseWriter()
            
            # 检查优化特性
            optimization_attrs = [
                'batch_size', 'flush_interval', 'buffer', 'connection_pool',
                'retry_config', 'performance_metrics'
            ]
            
            missing_attrs = []
            for attr in optimization_attrs:
                if not hasattr(writer, attr):
                    missing_attrs.append(attr)
            
            if missing_attrs:
                pytest.fail(f"TDD发现设计问题: OptimizedClickHouseWriter缺少优化属性: {missing_attrs}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: OptimizedClickHouseWriter初始化失败 - {e}")
    
    def test_optimized_writer_performance_features(self):
        """TDD发现问题: 性能优化特性测试"""
        try:
            from marketprism_collector.storage.optimized_clickhouse_writer import OptimizedClickHouseWriter
            
            writer = OptimizedClickHouseWriter()
            
            # 检查性能优化方法
            performance_methods = [
                'flush_buffer', 'get_buffer_size', 'get_performance_stats',
                'optimize_batch_size', 'enable_compression', 'set_retry_policy'
            ]
            
            missing_performance = []
            for method in performance_methods:
                if not hasattr(writer, method):
                    missing_performance.append(method)
            
            if missing_performance:
                pytest.fail(f"TDD发现设计问题: OptimizedClickHouseWriter缺少性能方法: {missing_performance}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: OptimizedClickHouseWriter性能特性测试失败 - {e}")
    
    def test_optimized_writer_backward_compatibility(self):
        """TDD发现问题: 向后兼容性测试"""
        try:
            from marketprism_collector.storage.optimized_clickhouse_writer import OptimizedClickHouseWriter
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            optimized_writer = OptimizedClickHouseWriter()
            basic_writer = ClickHouseWriter()
            
            # 检查基础接口兼容性
            basic_methods = ['connect', 'disconnect', 'write_data']
            
            for method in basic_methods:
                if hasattr(basic_writer, method) and not hasattr(optimized_writer, method):
                    pytest.fail(f"TDD发现设计问题: OptimizedClickHouseWriter缺少兼容方法 {method}")
                    
        except Exception as e:
            pytest.fail(f"TDD发现问题: OptimizedClickHouseWriter兼容性测试失败 - {e}")


@pytest.mark.unit
class TestStorageIntegration:
    """测试存储模块集成功能"""
    
    def test_storage_module_structure(self):
        """TDD发现问题: 存储模块结构完整性"""
        try:
            from marketprism_collector import storage
            
            # 检查核心组件导出
            core_components = ['ClickHouseWriter', 'OptimizedClickHouseWriter']
            missing_components = []
            
            for component in core_components:
                try:
                    getattr(storage, component)
                except AttributeError:
                    missing_components.append(component)
            
            if missing_components:
                pytest.fail(f"TDD发现设计问题: storage模块缺少组件: {missing_components}")
                
        except ImportError as e:
            pytest.fail(f"TDD发现问题: storage模块导入失败 - {e}")
    
    def test_storage_factory_pattern(self):
        """TDD发现问题: 工厂模式支持"""
        try:
            # 检查是否有工厂方法
            factory_functions = [
                'create_clickhouse_writer',
                'create_optimized_writer', 
                'get_writer_instance',
                'create_writer_from_config'
            ]
            
            factory_found = False
            for func_name in factory_functions:
                try:
                    import marketprism_collector.storage as storage_module
                    if hasattr(storage_module, func_name):
                        factory_found = True
                        break
                except:
                    pass
            
            if not factory_found:
                pytest.fail("TDD发现设计问题: storage模块缺少工厂模式支持")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: storage工厂模式测试失败 - {e}")
    
    def test_storage_manager_exists(self):
        """TDD发现问题: 存储管理器存在性"""
        try:
            possible_managers = [
                'StorageManager',
                'ClickHouseManager', 
                'DatabaseManager',
                'WriterManager'
            ]
            
            manager_found = False
            for manager_name in possible_managers:
                try:
                    import marketprism_collector.storage as storage_module
                    if hasattr(storage_module, manager_name):
                        manager_found = True
                        break
                except:
                    pass
            
            if not manager_found:
                pytest.fail("TDD发现设计问题: storage模块缺少统一管理器")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: storage管理器测试失败 - {e}")


@pytest.mark.unit
class TestStorageDesignIssues:
    """TDD专门测试存储模块设计问题的测试类"""
    
    def test_connection_pooling_support(self):
        """TDD发现问题: 连接池支持"""
        try:
            from marketprism_collector.storage.optimized_clickhouse_writer import OptimizedClickHouseWriter
            
            writer = OptimizedClickHouseWriter()
            
            # 检查连接池相关方法
            pool_methods = [
                'get_connection_pool', 'set_pool_size', 'get_pool_stats',
                'close_pool', 'reset_pool'
            ]
            
            missing_pool = []
            for method in pool_methods:
                if not hasattr(writer, method):
                    missing_pool.append(method)
            
            if missing_pool:
                pytest.fail(f"TDD发现设计问题: OptimizedClickHouseWriter缺少连接池方法: {missing_pool}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 连接池支持测试失败 - {e}")
    
    def test_transaction_support(self):
        """TDD发现问题: 事务支持"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            writer = ClickHouseWriter()
            
            # 检查事务相关方法
            transaction_methods = [
                'begin_transaction', 'commit_transaction', 'rollback_transaction',
                'execute_in_transaction'
            ]
            
            missing_transaction = []
            for method in transaction_methods:
                if not hasattr(writer, method):
                    missing_transaction.append(method)
            
            if missing_transaction:
                pytest.fail(f"TDD发现设计问题: ClickHouseWriter缺少事务方法: {missing_transaction}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 事务支持测试失败 - {e}")
    
    def test_data_validation_support(self):
        """TDD发现问题: 数据验证支持"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            writer = ClickHouseWriter()
            
            # 检查数据验证方法
            validation_methods = [
                'validate_data', 'validate_schema', 'sanitize_data',
                'check_data_types', 'validate_batch'
            ]
            
            missing_validation = []
            for method in validation_methods:
                if not hasattr(writer, method):
                    missing_validation.append(method)
            
            if missing_validation:
                pytest.fail(f"TDD发现设计问题: ClickHouseWriter缺少数据验证方法: {missing_validation}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 数据验证支持测试失败 - {e}")
    
    def test_error_handling_and_retry(self):
        """TDD发现问题: 错误处理和重试机制"""
        try:
            from marketprism_collector.storage.optimized_clickhouse_writer import OptimizedClickHouseWriter
            
            writer = OptimizedClickHouseWriter()
            
            # 检查错误处理方法
            error_methods = [
                'handle_connection_error', 'handle_write_error', 'retry_operation',
                'get_error_stats', 'reset_error_counters'
            ]
            
            missing_error = []
            for method in error_methods:
                if not hasattr(writer, method):
                    missing_error.append(method)
            
            if missing_error:
                pytest.fail(f"TDD发现设计问题: OptimizedClickHouseWriter缺少错误处理方法: {missing_error}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 错误处理测试失败 - {e}")
    
    def test_monitoring_and_metrics(self):
        """TDD发现问题: 监控和指标支持"""
        try:
            from marketprism_collector.storage.optimized_clickhouse_writer import OptimizedClickHouseWriter
            
            writer = OptimizedClickHouseWriter()
            
            # 检查监控方法
            monitoring_methods = [
                'get_write_metrics', 'get_connection_metrics', 'get_performance_metrics',
                'export_metrics', 'reset_metrics'
            ]
            
            missing_monitoring = []
            for method in monitoring_methods:
                if not hasattr(writer, method):
                    missing_monitoring.append(method)
            
            if missing_monitoring:
                pytest.fail(f"TDD发现设计问题: OptimizedClickHouseWriter缺少监控方法: {missing_monitoring}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 监控指标测试失败 - {e}")
    
    def test_configuration_management(self):
        """TDD发现问题: 配置管理"""
        try:
            from marketprism_collector.storage.clickhouse_writer import ClickHouseWriter
            
            # 测试配置管理方法
            config_methods = [
                'load_config', 'save_config', 'update_config',
                'get_config', 'validate_config'
            ]
            
            writer = ClickHouseWriter()
            missing_config = []
            
            for method in config_methods:
                if not hasattr(writer, method):
                    missing_config.append(method)
            
            if missing_config:
                pytest.fail(f"TDD发现设计问题: ClickHouseWriter缺少配置管理方法: {missing_config}")
                
        except Exception as e:
            pytest.fail(f"TDD发现问题: 配置管理测试失败 - {e}") 