"""
TDD测试：统一配置管理器测试
目标：提升配置系统的测试覆盖率

测试策略：
1. 测试配置加载和验证
2. 测试环境变量覆盖
3. 测试热重载功能
4. 测试配置迁移
"""

import pytest
import os
import tempfile
import yaml
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# 设置Python路径
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from core.config.unified_config_manager import UnifiedConfigManager
from core.config.unified_config_system import ConfigFactory, get_global_config, set_config
from core.config.validators import ConfigValidator
from core.config.env_override import EnvironmentOverrideManager


class TestUnifiedConfigManagerInitialization:
    """测试统一配置管理器初始化"""
    
    def test_config_manager_initialization_default(self):
        """测试：默认配置管理器初始化"""
        config_manager = UnifiedConfigManager()
        
        # 验证初始化
        assert config_manager is not None
        assert hasattr(config_manager, 'config_data')
        assert hasattr(config_manager, 'watchers')
        assert isinstance(config_manager.config_data, dict)
        
    def test_config_manager_initialization_with_config_path(self):
        """测试：指定配置路径的初始化"""
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {
                'app': {
                    'name': 'test_app',
                    'version': '1.0.0'
                },
                'database': {
                    'host': 'localhost',
                    'port': 5432
                }
            }
            yaml.dump(test_config, f)
            config_path = f.name
        
        try:
            config_manager = UnifiedConfigManager(config_path=config_path)
            
            # 验证配置加载
            assert config_manager.get('app.name') == 'test_app'
            assert config_manager.get('app.version') == '1.0.0'
            assert config_manager.get('database.host') == 'localhost'
            assert config_manager.get('database.port') == 5432
            
        finally:
            os.unlink(config_path)
            
    def test_config_manager_initialization_with_invalid_path(self):
        """测试：无效配置路径的处理"""
        # 不存在的配置文件应该使用默认配置或抛出异常
        with pytest.raises((FileNotFoundError, ValueError)):
            UnifiedConfigManager(config_path="/nonexistent/config.yaml")


class TestUnifiedConfigManagerOperations:
    """测试配置管理器基本操作"""
    
    def test_config_get_operation(self):
        """测试：配置获取操作"""
        config_manager = UnifiedConfigManager()
        
        # 设置测试配置
        config_manager.config_data = {
            'app': {
                'name': 'test_app',
                'settings': {
                    'debug': True,
                    'timeout': 30
                }
            }
        }
        
        # 测试获取操作
        assert config_manager.get('app.name') == 'test_app'
        assert config_manager.get('app.settings.debug') is True
        assert config_manager.get('app.settings.timeout') == 30
        assert config_manager.get('nonexistent.key') is None
        assert config_manager.get('nonexistent.key', 'default') == 'default'
        
    def test_config_set_operation(self):
        """测试：配置设置操作"""
        config_manager = UnifiedConfigManager()
        
        # 测试设置操作
        config_manager.set('app.name', 'new_app')
        config_manager.set('app.settings.debug', False)
        config_manager.set('new.nested.key', 'value')
        
        # 验证设置结果
        assert config_manager.get('app.name') == 'new_app'
        assert config_manager.get('app.settings.debug') is False
        assert config_manager.get('new.nested.key') == 'value'
        
    def test_config_update_operation(self):
        """测试：配置更新操作"""
        config_manager = UnifiedConfigManager()
        
        # 初始配置
        config_manager.config_data = {
            'app': {
                'name': 'old_app',
                'version': '1.0.0'
            }
        }
        
        # 更新配置
        update_data = {
            'app': {
                'name': 'new_app',
                'description': 'Updated app'
            },
            'database': {
                'host': 'localhost'
            }
        }
        
        config_manager.update(update_data)
        
        # 验证更新结果
        assert config_manager.get('app.name') == 'new_app'
        assert config_manager.get('app.version') == '1.0.0'  # 保持原值
        assert config_manager.get('app.description') == 'Updated app'
        assert config_manager.get('database.host') == 'localhost'
        
    def test_config_delete_operation(self):
        """测试：配置删除操作"""
        config_manager = UnifiedConfigManager()
        
        # 设置测试配置
        config_manager.config_data = {
            'app': {
                'name': 'test_app',
                'settings': {
                    'debug': True,
                    'timeout': 30
                }
            }
        }
        
        # 删除配置
        config_manager.delete('app.settings.debug')
        config_manager.delete('app.settings')
        
        # 验证删除结果
        assert config_manager.get('app.settings.debug') is None
        assert config_manager.get('app.settings') is None
        assert config_manager.get('app.name') == 'test_app'  # 其他配置保持


class TestConfigValidation:
    """测试配置验证功能"""
    
    def test_config_validation_success(self):
        """测试：配置验证成功"""
        validator = ConfigValidator()
        
        # 有效配置
        valid_config = {
            'app': {
                'name': 'test_app',
                'version': '1.0.0',
                'port': 8080
            },
            'database': {
                'host': 'localhost',
                'port': 5432,
                'name': 'test_db'
            }
        }
        
        # 验证应该成功
        is_valid, errors = validator.validate(valid_config)
        
        assert is_valid is True
        assert len(errors) == 0
        
    def test_config_validation_failure(self):
        """测试：配置验证失败"""
        validator = ConfigValidator()
        
        # 无效配置
        invalid_config = {
            'app': {
                'name': '',  # 空名称
                'port': 'invalid_port'  # 无效端口
            },
            'database': {
                # 缺少必要字段
            }
        }
        
        # 验证应该失败
        is_valid, errors = validator.validate(invalid_config)
        
        assert is_valid is False
        assert len(errors) > 0
        
    def test_config_schema_validation(self):
        """测试：配置模式验证"""
        validator = ConfigValidator()
        
        # 定义配置模式
        schema = {
            'type': 'object',
            'properties': {
                'app': {
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string', 'minLength': 1},
                        'port': {'type': 'integer', 'minimum': 1, 'maximum': 65535}
                    },
                    'required': ['name', 'port']
                }
            },
            'required': ['app']
        }
        
        # 测试配置
        config = {
            'app': {
                'name': 'test_app',
                'port': 8080
            }
        }
        
        # 验证模式
        is_valid = validator.validate_schema(config, schema)
        
        assert is_valid is True


class TestEnvironmentOverride:
    """测试环境变量覆盖功能"""
    
    def test_environment_override_basic(self):
        """测试：基本环境变量覆盖"""
        override_manager = EnvironmentOverrideManager()
        
        # 设置环境变量
        with patch.dict(os.environ, {
            'APP_NAME': 'env_app',
            'APP_PORT': '9090',
            'DATABASE_HOST': 'env_host'
        }):
            # 原始配置
            config = {
                'app': {
                    'name': 'original_app',
                    'port': 8080
                },
                'database': {
                    'host': 'localhost'
                }
            }
            
            # 应用环境变量覆盖
            overridden_config = override_manager.apply_overrides(config)
            
            # 验证覆盖结果
            assert overridden_config['app']['name'] == 'env_app'
            assert overridden_config['app']['port'] == 9090  # 应该转换为整数
            assert overridden_config['database']['host'] == 'env_host'
            
    def test_environment_override_with_prefix(self):
        """测试：带前缀的环境变量覆盖"""
        override_manager = EnvironmentOverrideManager(prefix='MYAPP_')
        
        # 设置环境变量
        with patch.dict(os.environ, {
            'MYAPP_APP_NAME': 'prefixed_app',
            'MYAPP_DATABASE_PORT': '5433',
            'OTHER_VAR': 'should_be_ignored'
        }):
            # 原始配置
            config = {
                'app': {
                    'name': 'original_app'
                },
                'database': {
                    'port': 5432
                }
            }
            
            # 应用环境变量覆盖
            overridden_config = override_manager.apply_overrides(config)
            
            # 验证覆盖结果
            assert overridden_config['app']['name'] == 'prefixed_app'
            assert overridden_config['database']['port'] == 5433
            
    def test_environment_override_type_conversion(self):
        """测试：环境变量类型转换"""
        override_manager = EnvironmentOverrideManager()
        
        # 设置不同类型的环境变量
        with patch.dict(os.environ, {
            'APP_DEBUG': 'true',
            'APP_TIMEOUT': '30',
            'APP_RATE': '1.5',
            'APP_FEATURES': 'feature1,feature2,feature3'
        }):
            # 原始配置
            config = {
                'app': {
                    'debug': False,
                    'timeout': 10,
                    'rate': 1.0,
                    'features': []
                }
            }
            
            # 应用环境变量覆盖
            overridden_config = override_manager.apply_overrides(config)
            
            # 验证类型转换
            assert overridden_config['app']['debug'] is True
            assert overridden_config['app']['timeout'] == 30
            assert overridden_config['app']['rate'] == 1.5
            assert overridden_config['app']['features'] == ['feature1', 'feature2', 'feature3']


class TestConfigHotReload:
    """测试配置热重载功能"""
    
    def test_config_hot_reload_setup(self):
        """测试：配置热重载设置"""
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {'app': {'name': 'test_app'}}
            yaml.dump(test_config, f)
            config_path = f.name
        
        try:
            config_manager = UnifiedConfigManager(config_path=config_path)
            
            # 设置热重载
            callback_called = False
            
            def reload_callback(new_config):
                nonlocal callback_called
                callback_called = True
            
            config_manager.enable_hot_reload(callback=reload_callback)
            
            # 验证热重载设置
            assert hasattr(config_manager, 'file_watcher')
            assert config_manager.hot_reload_enabled is True
            
        finally:
            os.unlink(config_path)
            
    @patch('core.config.hot_reload.Observer')
    def test_config_hot_reload_trigger(self, mock_observer):
        """测试：配置热重载触发"""
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {'app': {'name': 'original_app'}}
            yaml.dump(test_config, f)
            config_path = f.name
        
        try:
            config_manager = UnifiedConfigManager(config_path=config_path)
            
            # 设置重载回调
            reload_called = False
            new_config_data = None
            
            def reload_callback(new_config):
                nonlocal reload_called, new_config_data
                reload_called = True
                new_config_data = new_config
            
            config_manager.enable_hot_reload(callback=reload_callback)
            
            # 模拟文件变更
            updated_config = {'app': {'name': 'updated_app'}}
            with open(config_path, 'w') as f:
                yaml.dump(updated_config, f)
            
            # 手动触发重载（在实际环境中由文件监视器触发）
            config_manager._reload_config()
            
            # 验证重载结果
            assert config_manager.get('app.name') == 'updated_app'
            
        finally:
            os.unlink(config_path)


class TestConfigFactory:
    """测试配置工厂功能"""
    
    def test_config_factory_create_default(self):
        """测试：配置工厂创建默认配置"""
        config = ConfigFactory.create_default()
        
        # 验证默认配置
        assert config is not None
        assert isinstance(config, dict)
        
    def test_config_factory_create_from_file(self):
        """测试：配置工厂从文件创建配置"""
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            test_config = {
                'app': {'name': 'factory_app'},
                'database': {'host': 'localhost'}
            }
            yaml.dump(test_config, f)
            config_path = f.name
        
        try:
            config = ConfigFactory.create_from_file(config_path)
            
            # 验证配置
            assert config['app']['name'] == 'factory_app'
            assert config['database']['host'] == 'localhost'
            
        finally:
            os.unlink(config_path)
            
    def test_config_factory_create_from_dict(self):
        """测试：配置工厂从字典创建配置"""
        config_dict = {
            'app': {'name': 'dict_app'},
            'settings': {'debug': True}
        }
        
        config = ConfigFactory.create_from_dict(config_dict)
        
        # 验证配置
        assert config['app']['name'] == 'dict_app'
        assert config['settings']['debug'] is True


class TestGlobalConfigManagement:
    """测试全局配置管理"""
    
    def test_global_config_set_and_get(self):
        """测试：全局配置设置和获取"""
        # 设置全局配置
        test_config = {
            'app': {'name': 'global_app'},
            'version': '2.0.0'
        }
        
        set_config(test_config)
        
        # 获取全局配置
        global_config = get_global_config()
        
        # 验证全局配置
        assert global_config['app']['name'] == 'global_app'
        assert global_config['version'] == '2.0.0'
        
    def test_global_config_isolation(self):
        """测试：全局配置隔离"""
        # 设置第一个配置
        config1 = {'app': {'name': 'app1'}}
        set_config(config1)
        
        retrieved_config1 = get_global_config()
        assert retrieved_config1['app']['name'] == 'app1'
        
        # 设置第二个配置
        config2 = {'app': {'name': 'app2'}}
        set_config(config2)
        
        retrieved_config2 = get_global_config()
        assert retrieved_config2['app']['name'] == 'app2'
        
        # 验证配置已更新
        assert retrieved_config2['app']['name'] != retrieved_config1['app']['name']
