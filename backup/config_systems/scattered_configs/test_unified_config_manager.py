"""
统一配置管理器测试
"""

import pytest
import tempfile
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from core.config import (
    UnifiedConfigManager,
    BaseConfig,
    ConfigType,
    ConfigMetadata,
    ConfigRegistry,
    ConfigValidator,
    ValidationResult,
    ValidationSeverity
)


class TestConfig(BaseConfig):
    """测试配置类"""
    
    def __init__(self, name: str = "test", value: int = 42):
        metadata = ConfigMetadata(
            name="test_config",
            config_type=ConfigType.COLLECTOR,
            description="测试配置"
        )
        super().__init__(metadata)
        self.name = name
        self.value = value
        
    def _get_default_metadata(self) -> ConfigMetadata:
        return ConfigMetadata(
            name="test_config",
            config_type=ConfigType.COLLECTOR
        )
        
    def validate(self) -> bool:
        self._validation_errors.clear()
        if not self.name:
            self._validation_errors.append("名称不能为空")
        if self.value < 0:
            self._validation_errors.append("值不能为负数")
        return len(self._validation_errors) == 0
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestConfig':
        return cls(
            name=data.get("name", "test"),
            value=data.get("value", 42)
        )


class TestUnifiedConfigManager:
    """统一配置管理器测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录夹具"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def registry(self):
        """配置注册表夹具"""
        return ConfigRegistry()
        
    @pytest.fixture
    def config_manager(self, temp_dir, registry):
        """配置管理器夹具"""
        manager = UnifiedConfigManager(
            config_dir=temp_dir,
            registry=registry,
            enable_hot_reload=False,  # 测试时禁用热重载
            enable_env_override=False  # 测试时禁用环境变量覆盖
        )
        return manager
        
    def test_initialization(self, config_manager, temp_dir):
        """测试初始化"""
        assert config_manager.config_dir == temp_dir
        assert not config_manager._initialized
        
        # 测试初始化
        success = config_manager.initialize(auto_discover=False)
        assert success
        assert config_manager._initialized
        assert config_manager.config_dir.exists()
        
    def test_register_config_class(self, config_manager):
        """测试注册配置类"""
        config_manager.initialize(auto_discover=False)
        
        # 注册配置类
        config_name = config_manager.register_config_class(TestConfig)
        assert config_name == "test_config"
        
        # 检查注册状态
        config_class = config_manager.registry.get_config_class(config_name)
        assert config_class == TestConfig
        
        # 检查配置文件路径
        assert config_name in config_manager._config_files
        expected_file = config_manager.config_dir / "test_config.yaml"
        assert config_manager._config_files[config_name] == expected_file
        
    def test_load_config_from_data(self, config_manager):
        """测试从数据加载配置"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 从数据加载配置
        config_data = {"name": "test_load", "value": 100}
        result = config_manager.load_config(
            "test_config",
            config_data=config_data,
            from_file=False
        )
        
        assert result.success
        assert result.config_name == "test_config"
        assert len(result.errors) == 0
        
        # 检查配置
        config = config_manager.get_config("test_config")
        assert config is not None
        assert config.name == "test_load"
        assert config.value == 100
        
    def test_load_config_from_file(self, config_manager, temp_dir):
        """测试从文件加载配置"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 创建配置文件
        config_file = temp_dir / "test_config.yaml"
        config_file.write_text("""
name: test_file
value: 200
""")
        
        # 从文件加载配置
        result = config_manager.load_config("test_config", from_file=True)
        
        assert result.success
        assert len(result.errors) == 0
        
        # 检查配置
        config = config_manager.get_config("test_config")
        assert config is not None
        assert config.name == "test_file"
        assert config.value == 200
        
    def test_load_config_validation_error(self, config_manager):
        """测试配置验证错误"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 加载无效配置
        config_data = {"name": "", "value": -1}  # 无效数据
        result = config_manager.load_config(
            "test_config",
            config_data=config_data,
            from_file=False
        )
        
        assert not result.success
        assert len(result.errors) > 0
        assert "名称不能为空" in result.errors
        assert "值不能为负数" in result.errors
        
    def test_reload_config(self, config_manager, temp_dir):
        """测试重新加载配置"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 创建初始配置文件
        config_file = temp_dir / "test_config.yaml"
        config_file.write_text("""
name: initial
value: 100
""")
        
        # 首次加载
        result1 = config_manager.load_config("test_config")
        assert result1.success
        config1 = config_manager.get_config("test_config")
        assert config1.name == "initial"
        
        # 修改配置文件
        config_file.write_text("""
name: updated
value: 200
""")
        
        # 重新加载
        result2 = config_manager.reload_config("test_config")
        assert result2.success
        config2 = config_manager.get_config("test_config")
        assert config2.name == "updated"
        assert config2.value == 200
        
    def test_save_config(self, config_manager, temp_dir):
        """测试保存配置"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 加载配置
        config_data = {"name": "test_save", "value": 300}
        result = config_manager.load_config(
            "test_config",
            config_data=config_data,
            from_file=False
        )
        assert result.success
        
        # 保存配置
        success = config_manager.save_config("test_config")
        assert success
        
        # 检查文件是否存在
        config_file = temp_dir / "test_config.yaml"
        assert config_file.exists()
        
        # 验证文件内容
        content = config_file.read_text()
        assert "test_save" in content
        assert "300" in content
        
    def test_list_configs(self, config_manager):
        """测试列出配置"""
        config_manager.initialize(auto_discover=False)
        
        # 注册多个配置
        config_manager.register_config_class(TestConfig, name="config1")
        config_manager.register_config_class(TestConfig, name="config2")
        
        # 列出所有配置
        configs = config_manager.list_configs()
        assert "config1" in configs
        assert "config2" in configs
        
        # 列出已加载的配置
        loaded_configs = config_manager.list_configs(loaded_only=True)
        assert len(loaded_configs) == 0  # 还没有加载任何配置
        
        # 加载一个配置
        config_manager.load_config("config1", config_data={"name": "test", "value": 1})
        loaded_configs = config_manager.list_configs(loaded_only=True)
        assert len(loaded_configs) == 1
        assert "config1" in loaded_configs
        
    def test_change_listener(self, config_manager):
        """测试配置变更监听器"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 添加监听器
        change_events = []
        def change_listener(event):
            change_events.append(event)
            
        config_manager.add_change_listener(change_listener)
        
        # 首次加载（不会触发变更事件）
        config_manager.load_config("test_config", config_data={"name": "first", "value": 1})
        assert len(change_events) == 0
        
        # 重新加载（会触发变更事件）
        config_manager.load_config("test_config", config_data={"name": "second", "value": 2})
        assert len(change_events) == 1
        
        event = change_events[0]
        assert event.config_name == "test_config"
        assert event.old_config.name == "first"
        assert event.new_config.name == "second"
        
    def test_load_listener(self, config_manager):
        """测试配置加载监听器"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 添加监听器
        load_results = []
        def load_listener(result):
            load_results.append(result)
            
        config_manager.add_load_listener(load_listener)
        
        # 加载配置
        config_manager.load_config("test_config", config_data={"name": "test", "value": 1})
        assert len(load_results) == 1
        
        result = load_results[0]
        assert result.config_name == "test_config"
        assert result.success
        
    def test_get_service_config(self, config_manager):
        """测试获取服务配置"""
        config_manager.initialize(auto_discover=False)
        
        # 注册并加载配置
        config_manager.register_config_class(TestConfig, name="collector_service")
        config_manager.load_config(
            "collector_service",
            config_data={"name": "service_test", "value": 42}
        )
        
        # 按服务名称获取
        config = config_manager.get_service_config("collector_service")
        assert config is not None
        assert config.name == "service_test"
        
        # 按配置类型获取
        config = config_manager.get_service_config("unknown", config_type=ConfigType.COLLECTOR)
        assert config is not None  # 应该返回collector类型的配置
        
    def test_stats(self, config_manager):
        """测试统计信息"""
        config_manager.initialize(auto_discover=False)
        config_manager.register_config_class(TestConfig)
        
        # 获取初始统计
        stats = config_manager.get_stats()
        assert stats["initialized"] == True
        assert stats["loaded_configs"] == 0
        assert stats["configs_loaded"] == 0
        
        # 加载配置
        config_manager.load_config("test_config", config_data={"name": "test", "value": 1})
        
        # 获取更新后统计
        stats = config_manager.get_stats()
        assert stats["loaded_configs"] == 1
        assert stats["configs_loaded"] == 1
        
    def test_shutdown(self, config_manager):
        """测试关闭配置管理器"""
        config_manager.initialize(auto_discover=False)
        assert config_manager._initialized
        
        config_manager.shutdown()
        assert not config_manager._initialized