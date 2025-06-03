#!/usr/bin/env python3
"""
Unified Configuration Path Manager Tests

测试新的统一配置路径管理器，确保所有配置路径正确解析到项目根目录
"""
import pytest
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.config import config_path_manager, ConfigPathManager


@pytest.mark.unit
class TestConfigPathManager:
    """测试配置路径管理器"""
    
    def test_config_path_manager_initialization(self):
        """测试配置路径管理器初始化"""
        manager = ConfigPathManager()
        
        # 检查基本属性
        assert hasattr(manager, 'config_root')
        assert hasattr(manager, 'CONFIG_PATHS')
        assert isinstance(manager.CONFIG_PATHS, dict)
    
    def test_automatic_root_resolution(self):
        """测试自动根目录解析"""
        manager = ConfigPathManager()
        
        # 配置根目录应该指向项目根目录的config文件夹
        config_root = manager.config_root
        assert config_root.name == 'config'
        
        # 检查路径是否正确解析
        assert 'marketprism' in str(config_root)
    
    def test_exchange_config_paths(self):
        """测试交易所配置路径"""
        # 测试各种交易所配置路径
        exchanges = ['binance', 'okx', 'deribit']
        
        for exchange in exchanges:
            config_path = config_path_manager.get_exchange_config_path(exchange)
            
            # 检查路径格式
            assert f'exchanges/{exchange}.yaml' in str(config_path)
            assert config_path.suffix == '.yaml'
    
    def test_collector_config_paths(self):
        """测试收集器配置路径"""
        config_names = ['main', 'production', 'development']
        
        for config_name in config_names:
            config_path = config_path_manager.get_collector_config_path(config_name)
            
            # 检查路径格式
            assert f'collector/{config_name}.yaml' in str(config_path)
            assert config_path.suffix == '.yaml'
    
    def test_generic_config_paths(self):
        """测试通用配置路径"""
        # 测试所有配置类别
        categories = ['exchanges', 'monitoring', 'infrastructure', 'environments', 'collector', 'test']
        
        for category in categories:
            config_path = config_path_manager.get_config_path(category, 'test.yaml')
            
            # 检查路径包含正确的类别
            assert category in str(config_path)
            assert 'test.yaml' in str(config_path)
    
    def test_invalid_category_handling(self):
        """测试无效配置类别处理"""
        with pytest.raises(ValueError) as excinfo:
            config_path_manager.get_config_path('invalid_category', 'test.yaml')
        
        assert '未知配置类别' in str(excinfo.value)
    
    def test_config_files_listing(self):
        """测试配置文件列表功能"""
        # 测试每个类别的文件列表
        for category in config_path_manager.CONFIG_PATHS:
            file_list = config_path_manager.list_config_files(category)
            assert isinstance(file_list, list)
            
            # 所有文件应该是YAML格式
            for filename in file_list:
                assert filename.endswith('.yaml') or filename.endswith('.yml')


@pytest.mark.unit
class TestGlobalConfigManager:
    """测试全局配置管理器实例"""
    
    def test_global_instance_availability(self):
        """测试全局实例可用性"""
        from marketprism_collector.config_paths import config_path_manager
        
        assert config_path_manager is not None
        assert isinstance(config_path_manager, ConfigPathManager)
    
    def test_consistent_path_resolution(self):
        """测试路径解析一致性"""
        # 多次调用应该返回相同结果
        path1 = config_path_manager.get_exchange_config_path('binance')
        path2 = config_path_manager.get_exchange_config_path('binance')
        
        assert path1 == path2
        assert str(path1) == str(path2)
    
    def test_path_categories_completeness(self):
        """测试路径类别完整性"""
        expected_categories = {
            'exchanges', 'monitoring', 'infrastructure', 
            'environments', 'collector', 'test'
        }
        
        actual_categories = set(config_path_manager.CONFIG_PATHS.keys())
        assert expected_categories.issubset(actual_categories)


@pytest.mark.integration
class TestConfigIntegrationWithCollector:
    """测试配置与收集器的集成"""
    
    def test_collector_config_integration(self):
        """测试收集器配置集成"""
        try:
            from marketprism_collector.config import Config
            from marketprism_collector.config_paths import config_path_manager
            
            # 测试配置路径是否被正确使用
            # 这里可能需要根据实际的Config类实现来调整
            
        except ImportError:
            # 如果Config类不可用，跳过测试
            pytest.skip("Config class not available for integration test")
    
    def test_exchange_config_resolution(self):
        """测试交易所配置解析"""
        # 测试常用交易所的配置路径解析
        exchanges = ['binance', 'okx', 'deribit']
        
        for exchange in exchanges:
            path = config_path_manager.get_exchange_config_path(exchange)
            
            # 路径应该存在于项目结构中
            assert path.parent.name == 'exchanges'
            assert 'config' in str(path)


@pytest.mark.unit
class TestConfigPathArchitecture:
    """测试配置路径架构合规性"""
    
    def test_no_hardcoded_paths(self):
        """确保没有硬编码路径"""
        manager = ConfigPathManager()
        
        # 配置根目录应该动态解析
        config_root = manager.config_root
        assert config_root.is_absolute()
        
        # 检查是否使用了相对路径映射
        for category, path in manager.CONFIG_PATHS.items():
            assert not os.path.isabs(path), f"类别 {category} 使用了绝对路径: {path}"
    
    def test_project_root_detection(self):
        """测试项目根目录检测"""
        manager = ConfigPathManager()
        
        # 配置根目录应该在marketprism项目下
        config_root_str = str(manager.config_root)
        assert 'marketprism' in config_root_str
        assert config_root_str.endswith('config')
    
    def test_config_structure_compliance(self):
        """测试配置结构合规性"""
        # 验证配置结构符合项目标准
        required_categories = ['exchanges', 'collector', 'monitoring']
        
        for category in required_categories:
            assert category in config_path_manager.CONFIG_PATHS
            
            # 测试路径解析
            test_path = config_path_manager.get_config_path(category, 'test.yaml')
            assert test_path.parent.name == category


if __name__ == "__main__":
    pytest.main([__file__, "-v"])