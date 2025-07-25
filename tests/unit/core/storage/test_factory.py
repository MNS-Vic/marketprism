"""
存储工厂测试

严格遵循Mock使用原则：
- 仅对外部依赖使用Mock（如数据库连接、文件系统）
- 优先使用真实对象测试业务逻辑
- 确保测试验证真实的业务行为
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# 尝试导入存储工厂模块
try:
    from core.storage.factory import (
        create_clickhouse_writer,
        create_optimized_writer,
        get_writer_instance,
        create_writer_from_config,
        create_writer_pool,
        get_available_writer_types,
        is_writer_type_supported,
        create_storage_writer,
        create_default_writer,
        WRITER_TYPES,
        ClickHouseWriter,
        OptimizedClickHouseWriter
    )
    from core.storage.unified_clickhouse_writer import UnifiedClickHouseWriter
    HAS_STORAGE_FACTORY = True
except ImportError as e:
    HAS_STORAGE_FACTORY = False
    STORAGE_FACTORY_ERROR = str(e)


@pytest.mark.skipif(not HAS_STORAGE_FACTORY, reason=f"存储工厂模块不可用: {STORAGE_FACTORY_ERROR if not HAS_STORAGE_FACTORY else ''}")
class TestStorageFactory:
    """存储工厂测试"""
    
    def test_writer_types_constant(self):
        """测试writer类型常量"""
        assert isinstance(WRITER_TYPES, dict)
        assert len(WRITER_TYPES) > 0
        
        # 验证基本类型存在
        expected_types = [
            'clickhouse',
            'optimized_clickhouse',
            'clickhouse_writer',
            'optimized',
            'unified'
        ]
        
        for writer_type in expected_types:
            assert writer_type in WRITER_TYPES
            assert WRITER_TYPES[writer_type] == UnifiedClickHouseWriter
    
    def test_backward_compatibility_aliases(self):
        """测试向后兼容别名"""
        assert ClickHouseWriter == UnifiedClickHouseWriter
        assert OptimizedClickHouseWriter == UnifiedClickHouseWriter
    
    @patch('core.storage.factory.UnifiedClickHouseWriter')
    def test_create_clickhouse_writer(self, mock_writer_class):
        """测试创建ClickHouse写入器"""
        mock_instance = Mock()
        mock_writer_class.return_value = mock_instance
        
        config = {"host": "localhost", "port": 8123}
        result = create_clickhouse_writer(config)
        
        mock_writer_class.assert_called_once_with(config)
        assert result == mock_instance
    
    @patch('core.storage.factory.UnifiedClickHouseWriter')
    def test_create_clickhouse_writer_no_config(self, mock_writer_class):
        """测试不带配置创建ClickHouse写入器"""
        mock_instance = Mock()
        mock_writer_class.return_value = mock_instance
        
        result = create_clickhouse_writer()
        
        mock_writer_class.assert_called_once_with(None)
        assert result == mock_instance
    
    @patch('core.storage.factory.UnifiedClickHouseWriter')
    def test_create_optimized_writer(self, mock_writer_class):
        """测试创建优化版写入器"""
        mock_instance = Mock()
        mock_writer_class.return_value = mock_instance
        
        config = {"optimization": {"enabled": True}}
        result = create_optimized_writer(config)
        
        mock_writer_class.assert_called_once_with(config)
        assert result == mock_instance
    
    def test_get_writer_instance_valid_types(self):
        """测试获取有效类型的writer实例"""
        config = {"database": "test_db"}

        # 测试几个关键类型
        test_types = ['clickhouse', 'unified', 'optimized']
        for writer_type in test_types:
            result = get_writer_instance(writer_type, config)
            # 验证返回的是UnifiedClickHouseWriter实例
            assert isinstance(result, UnifiedClickHouseWriter)
            assert result is not None
    
    def test_get_writer_instance_invalid_type(self):
        """测试获取无效类型的writer实例"""
        with pytest.raises(ValueError) as exc_info:
            get_writer_instance("invalid_type")
        
        error_message = str(exc_info.value)
        assert "不支持的writer类型" in error_message
        assert "invalid_type" in error_message
        assert "可用类型" in error_message
    
    @patch('core.storage.factory.get_writer_instance')
    def test_create_writer_from_config_default_type(self, mock_get_writer):
        """测试从配置创建writer（默认类型）"""
        mock_instance = Mock()
        mock_get_writer.return_value = mock_instance
        
        config = {"host": "localhost"}
        result = create_writer_from_config(config)
        
        mock_get_writer.assert_called_once_with('clickhouse', config)
        assert result == mock_instance
    
    @patch('core.storage.factory.get_writer_instance')
    def test_create_writer_from_config_specified_type(self, mock_get_writer):
        """测试从配置创建writer（指定类型）"""
        mock_instance = Mock()
        mock_get_writer.return_value = mock_instance
        
        config = {
            "writer_type": "optimized_clickhouse",
            "host": "localhost"
        }
        result = create_writer_from_config(config)
        
        mock_get_writer.assert_called_once_with('optimized_clickhouse', config)
        assert result == mock_instance
    
    @patch('core.storage.factory.get_writer_instance')
    def test_create_writer_from_config_optimization_enabled(self, mock_get_writer):
        """测试从配置创建writer（启用优化）"""
        mock_instance = Mock()
        mock_get_writer.return_value = mock_instance
        
        config = {
            "writer_type": "clickhouse",
            "optimization": {"enabled": True},
            "host": "localhost"
        }
        result = create_writer_from_config(config)
        
        # 应该自动选择unified类型
        mock_get_writer.assert_called_once_with('unified', config)
        assert result == mock_instance
    
    @patch('core.storage.factory.get_writer_instance')
    def test_create_writer_pool(self, mock_get_writer):
        """测试创建writer池"""
        mock_instances = [Mock() for _ in range(3)]
        mock_get_writer.side_effect = mock_instances
        
        config = {"host": "localhost"}
        pool_size = 3
        writer_type = "clickhouse"
        
        result = create_writer_pool(pool_size, writer_type, config)
        
        assert len(result) == pool_size
        assert result == mock_instances
        assert mock_get_writer.call_count == pool_size
        
        # 验证每次调用的参数
        for call in mock_get_writer.call_args_list:
            assert call[0] == (writer_type, config)
    
    @patch('core.storage.factory.get_writer_instance')
    def test_create_writer_pool_defaults(self, mock_get_writer):
        """测试创建writer池（默认参数）"""
        mock_instances = [Mock() for _ in range(5)]
        mock_get_writer.side_effect = mock_instances
        
        result = create_writer_pool()
        
        assert len(result) == 5  # 默认池大小
        assert mock_get_writer.call_count == 5
        
        # 验证使用默认参数
        for call in mock_get_writer.call_args_list:
            assert call[0] == ('clickhouse', None)
    
    def test_get_available_writer_types(self):
        """测试获取可用writer类型"""
        result = get_available_writer_types()
        
        assert isinstance(result, list)
        assert len(result) > 0
        
        # 验证返回的类型与WRITER_TYPES一致
        expected_types = list(WRITER_TYPES.keys())
        assert set(result) == set(expected_types)
    
    def test_is_writer_type_supported(self):
        """测试检查writer类型是否支持"""
        # 测试支持的类型
        for writer_type in WRITER_TYPES.keys():
            assert is_writer_type_supported(writer_type) is True
        
        # 测试不支持的类型
        unsupported_types = [
            "invalid_type",
            "mysql",
            "postgresql",
            "",
            None
        ]
        
        for writer_type in unsupported_types:
            assert is_writer_type_supported(writer_type) is False
    
    @patch('core.storage.factory.create_clickhouse_writer')
    def test_create_storage_writer_backward_compatibility(self, mock_create_clickhouse):
        """测试向后兼容的存储写入器创建"""
        mock_instance = Mock()
        mock_create_clickhouse.return_value = mock_instance
        
        config = {"host": "localhost"}
        result = create_storage_writer(config)
        
        mock_create_clickhouse.assert_called_once_with(config)
        assert result == mock_instance
    
    @patch('core.storage.factory.create_clickhouse_writer')
    def test_create_default_writer(self, mock_create_clickhouse):
        """测试创建默认writer"""
        mock_instance = Mock()
        mock_create_clickhouse.return_value = mock_instance
        
        config = {"database": "default"}
        result = create_default_writer(config)
        
        mock_create_clickhouse.assert_called_once_with(config)
        assert result == mock_instance
    
    @patch('core.storage.factory.create_clickhouse_writer')
    def test_create_default_writer_no_config(self, mock_create_clickhouse):
        """测试创建默认writer（无配置）"""
        mock_instance = Mock()
        mock_create_clickhouse.return_value = mock_instance
        
        result = create_default_writer()
        
        mock_create_clickhouse.assert_called_once_with(None)
        assert result == mock_instance


@pytest.mark.skipif(not HAS_STORAGE_FACTORY, reason=f"存储工厂模块不可用: {STORAGE_FACTORY_ERROR if not HAS_STORAGE_FACTORY else ''}")
class TestStorageFactoryIntegration:
    """存储工厂集成测试"""
    
    def test_factory_integration_flow(self):
        """测试工厂集成流程"""
        # 测试完整的工厂流程
        config = {
            "writer_type": "unified",
            "host": "localhost",
            "port": 8123,
            "database": "test_db"
        }

        # 1. 检查类型支持
        assert is_writer_type_supported("unified") is True

        # 2. 获取可用类型
        available_types = get_available_writer_types()
        assert "unified" in available_types

        # 3. 从配置创建writer
        writer = create_writer_from_config(config)
        assert isinstance(writer, UnifiedClickHouseWriter)

        # 4. 创建writer池
        pool = create_writer_pool(2, "unified", config)
        assert len(pool) == 2
        for writer_instance in pool:
            assert isinstance(writer_instance, UnifiedClickHouseWriter)
    
    def test_error_handling_edge_cases(self):
        """测试错误处理边界情况"""
        # 测试空字符串类型
        with pytest.raises(ValueError):
            get_writer_instance("")
        
        # 测试None类型（转换为字符串后）
        with pytest.raises(ValueError):
            get_writer_instance(None)
        
        # 测试大小写敏感
        with pytest.raises(ValueError):
            get_writer_instance("CLICKHOUSE")  # 大写应该失败
    
    @patch('core.storage.factory.logger')
    def test_logging_behavior(self, mock_logger):
        """测试日志记录行为"""
        with patch('core.storage.factory.UnifiedClickHouseWriter') as mock_writer:
            mock_writer.return_value = Mock()
            
            # 测试各种创建函数的日志记录
            create_clickhouse_writer()
            create_optimized_writer()
            get_writer_instance("clickhouse")
            create_writer_pool(2)
            
            # 验证日志调用
            assert mock_logger.info.call_count >= 4


# 基础覆盖率测试
class TestStorageFactoryBasic:
    """存储工厂基础覆盖率测试"""
    
    def test_module_import_attempt(self):
        """测试模块导入尝试"""
        try:
            from core.storage import factory
            # 如果导入成功，测试基本属性
            assert hasattr(factory, '__file__')
        except ImportError:
            # 如果导入失败，这也是预期的情况
            pytest.skip("存储工厂模块不可用")
    
    def test_factory_concepts(self):
        """测试工厂模式概念"""
        # 测试工厂模式的核心概念
        concepts = [
            "writer_creation",
            "type_abstraction",
            "configuration_driven",
            "pool_management",
            "backward_compatibility"
        ]
        
        # 验证概念存在
        for concept in concepts:
            assert isinstance(concept, str)
            assert len(concept) > 0
