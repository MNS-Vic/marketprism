"""
配置管理器测试覆盖率提升
专门用于提升core/config模块的测试覆盖率到90%以上

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from core.config.unified_config_manager import (
    UnifiedConfigManager, ConfigFactory, ConfigLoadResult,
    ConfigChangeEvent, get_global_config, set_global_config,
    get_config, set_config
)
from core.config.base_config import BaseConfig, ConfigType, ConfigMetadata
from core.config.validators import ConfigValidator, ValidationResult, ValidationSeverity


class SimpleTestConfig(BaseConfig):
    """测试用配置类"""
    def __init__(self):
        super().__init__()
        self.test_value = "default"

    def _get_default_metadata(self):
        return ConfigMetadata(
            name="TestConfig",
            config_type=ConfigType.COLLECTOR,
            version="1.0",
            description="Test configuration"
        )

    @classmethod
    def from_dict(cls, data):
        instance = cls()
        instance.test_value = data.get("test_value", "default")
        return instance

    def to_dict(self):
        return {"test_value": self.test_value}

    def validate(self):
        return True


class TestConfigLoadResult:
    """测试ConfigLoadResult类"""
    
    def test_config_load_result_initialization(self):
        """测试：ConfigLoadResult初始化"""
        result = ConfigLoadResult(config_name="test", success=True)
        
        assert result.config_name == "test"
        assert result.success is True
        assert result.config is None
        assert result.errors == []
        assert result.warnings == []
        assert isinstance(result.load_time, datetime)
        
    def test_config_load_result_with_data(self):
        """测试：ConfigLoadResult带数据初始化"""
        config = Mock(spec=BaseConfig)
        errors = ["error1", "error2"]
        warnings = ["warning1"]
        load_time = datetime.now(timezone.utc)
        
        result = ConfigLoadResult(
            config_name="test",
            success=False,
            config=config,
            errors=errors,
            warnings=warnings,
            load_time=load_time
        )
        
        assert result.config_name == "test"
        assert result.success is False
        assert result.config is config
        assert result.errors == errors
        assert result.warnings == warnings
        assert result.load_time == load_time


class TestConfigChangeEvent:
    """测试ConfigChangeEvent类"""
    
    def test_config_change_event_initialization(self):
        """测试：ConfigChangeEvent初始化"""
        old_config = Mock(spec=BaseConfig)
        new_config = Mock(spec=BaseConfig)
        
        event = ConfigChangeEvent("test_config", old_config, new_config)
        
        assert event.config_name == "test_config"
        assert event.old_config is old_config
        assert event.new_config is new_config
        assert event.change_type == "update"
        assert isinstance(event.timestamp, datetime)
        
    def test_config_change_event_custom_type(self):
        """测试：ConfigChangeEvent自定义类型"""
        old_config = Mock(spec=BaseConfig)
        new_config = Mock(spec=BaseConfig)
        
        event = ConfigChangeEvent("test_config", old_config, new_config, "reload")
        
        assert event.change_type == "reload"


class TestUnifiedConfigManagerInitialization:
    """测试UnifiedConfigManager初始化"""
    
    def test_manager_default_initialization(self):
        """测试：默认初始化"""
        manager = UnifiedConfigManager()
        
        assert manager.config_dir == Path.cwd() / "config"
        assert manager.enable_hot_reload is True
        assert manager.enable_env_override is True
        assert manager._initialized is False
        assert isinstance(manager._configs, dict)
        assert isinstance(manager._config_files, dict)
        assert isinstance(manager._stats, dict)
        
    def test_manager_custom_initialization(self):
        """测试：自定义初始化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UnifiedConfigManager(
                config_dir=temp_dir,
                enable_hot_reload=False,
                enable_env_override=False
            )
            
            assert manager.config_dir == Path(temp_dir)
            assert manager.enable_hot_reload is False
            assert manager.enable_env_override is False
            assert manager._hot_reload_manager is None
            assert manager._env_override_manager is None
            
    def test_manager_initialization_success(self):
        """测试：管理器初始化成功"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UnifiedConfigManager(config_dir=temp_dir)
            
            result = manager.initialize()
            
            assert result is True
            assert manager._initialized is True
            assert manager.config_dir.exists()
            
    def test_manager_double_initialization(self):
        """测试：重复初始化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UnifiedConfigManager(config_dir=temp_dir)
            
            # 第一次初始化
            result1 = manager.initialize()
            assert result1 is True
            
            # 第二次初始化应该返回True但不重复初始化
            result2 = manager.initialize()
            assert result2 is True
            
    def test_manager_initialization_with_hot_reload_disabled(self):
        """测试：禁用热重载的初始化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = UnifiedConfigManager(
                config_dir=temp_dir,
                enable_hot_reload=False
            )

            result = manager.initialize()

            assert result is True
            assert manager._hot_reload_manager is None


class TestUnifiedConfigManagerConfigOperations:
    """测试UnifiedConfigManager配置操作"""
    
    def setup_method(self):
        """设置测试方法"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = UnifiedConfigManager(config_dir=self.temp_dir)
        self.manager.initialize()
        
    def teardown_method(self):
        """清理测试方法"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_register_config_class_basic(self):
        """测试：基本配置类注册"""
        config_name = self.manager.register_config_class(SimpleTestConfig)

        assert config_name == "TestConfig"
        assert config_name in self.manager._config_files
        assert self.manager._config_files[config_name].name == "testconfig.yaml"

    def test_register_config_class_with_custom_name(self):
        """测试：自定义名称配置类注册"""
        config_name = self.manager.register_config_class(SimpleTestConfig, name="custom_config")

        assert config_name == "custom_config"

    def test_register_config_class_with_file_and_validator(self):
        """测试：带文件和验证器的配置类注册"""
        validator = Mock(spec=ConfigValidator)
        config_file = Path(self.temp_dir) / "custom.yaml"

        config_name = self.manager.register_config_class(
            SimpleTestConfig,
            name="FileTestConfig",  # 使用不同的名称避免冲突
            config_file=config_file,
            validator=validator
        )

        assert self.manager._config_files[config_name] == config_file
        assert self.manager._config_validators[config_name] is validator
        
    def test_load_config_unregistered(self):
        """测试：加载未注册的配置"""
        result = self.manager.load_config("nonexistent")
        
        assert result.success is False
        assert "配置未注册" in result.errors[0]
        
    def test_load_config_default_creation(self):
        """测试：默认配置创建"""
        config_name = self.manager.register_config_class(SimpleTestConfig, name="DefaultTestConfig")
        result = self.manager.load_config(config_name)

        assert result.success is True
        assert result.config is not None
        assert result.config.test_value == "default"

    def test_load_config_from_data(self):
        """测试：从数据加载配置"""
        config_name = self.manager.register_config_class(SimpleTestConfig, name="DataTestConfig")
        config_data = {"test_value": "from_data"}

        result = self.manager.load_config(config_name, config_data=config_data)

        assert result.success is True
        assert result.config.test_value == "from_data"

    def test_get_config_existing(self):
        """测试：获取已存在的配置"""
        config_name = self.manager.register_config_class(SimpleTestConfig, name="ExistingTestConfig")
        self.manager.load_config(config_name)

        config = self.manager.get_config(config_name)

        assert config is not None
        assert isinstance(config, SimpleTestConfig)
        
    def test_get_config_nonexistent(self):
        """测试：获取不存在的配置"""
        config = self.manager.get_config("nonexistent")
        
        assert config is None


class TestConfigFactory:
    """测试ConfigFactory类"""
    
    def test_create_basic_config(self):
        """测试：创建基础配置"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ConfigFactory.create_basic_config(temp_dir)
            
            assert isinstance(config, UnifiedConfigManager)
            assert config.config_dir == Path(temp_dir)
            
    def test_create_enterprise_config_all_features(self):
        """测试：创建企业级配置（所有功能）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ConfigFactory.create_enterprise_config(
                temp_dir,
                enable_security=True,
                enable_caching=True,
                enable_distribution=True
            )
            
            assert isinstance(config, UnifiedConfigManager)
            assert config.config_dir == Path(temp_dir)
            
    def test_create_enterprise_config_minimal(self):
        """测试：创建企业级配置（最小功能）"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ConfigFactory.create_enterprise_config(
                temp_dir,
                enable_security=False,
                enable_caching=False,
                enable_distribution=False
            )
            
            assert isinstance(config, UnifiedConfigManager)


class TestGlobalConfigFunctions:
    """测试全局配置函数"""
    
    def setup_method(self):
        """设置测试方法"""
        # 保存原始全局配置
        from core.config import unified_config_manager
        self._original_global = getattr(unified_config_manager, '_global_config', None)
        
    def teardown_method(self):
        """清理测试方法"""
        # 恢复原始全局配置
        from core.config import unified_config_manager
        unified_config_manager._global_config = self._original_global
        
    def test_get_global_config_first_time(self):
        """测试：首次获取全局配置"""
        # 清除全局配置
        from core.config import unified_config_manager
        unified_config_manager._global_config = None
        
        config = get_global_config()
        
        assert isinstance(config, UnifiedConfigManager)
        
    def test_set_and_get_global_config(self):
        """测试：设置和获取全局配置"""
        custom_config = UnifiedConfigManager()
        
        set_global_config(custom_config)
        retrieved_config = get_global_config()
        
        assert retrieved_config is custom_config
        
    def test_convenience_functions(self):
        """测试：便捷函数"""
        # 设置配置
        set_config("test_key", "test_value")
        
        # 获取配置
        value = get_config("test_key")
        assert value == "test_value"
        
        # 获取不存在的配置
        value = get_config("nonexistent", "default")
        assert value == "default"
