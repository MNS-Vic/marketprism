"""
配置热重载测试
"""

import pytest
import tempfile
import shutil
import time
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# 添加项目路径到sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from config.core import (
    UnifiedConfigManager,
    BaseConfig,
    ConfigType,
    ConfigMetadata,
    ConfigRegistry
)
from core.config.hot_reload import (
    ConfigHotReloadManager
)


class SimpleTestConfig(BaseConfig):
    """简单测试配置类"""
    
    def __init__(self, name: str = "test", value: int = 42):
        metadata = ConfigMetadata(
            name="simple_test",
            config_type=ConfigType.COLLECTOR
        )
        super().__init__(metadata)
        self.name = name
        self.value = value
        
    def _get_default_metadata(self) -> ConfigMetadata:
        return ConfigMetadata(
            name="simple_test",
            config_type=ConfigType.COLLECTOR
        )
        
    def validate(self) -> bool:
        return True
        
    def to_dict(self):
        return {"name": self.name, "value": self.value}
        
    @classmethod
    def from_dict(cls, data):
        return cls(data.get("name", "test"), data.get("value", 42))


class TestConfigHotReloadManager:
    """配置热重载管理器测试"""
    
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
            enable_hot_reload=True,
            enable_env_override=False
        )
        manager.initialize(auto_discover=False)
        return manager
        
    @pytest.fixture
    def hot_reload_manager(self, config_manager):
        """热重载管理器夹具"""
        return config_manager._hot_reload_manager
        
    def test_initialization(self, hot_reload_manager, config_manager):
        """测试初始化"""
        assert hot_reload_manager.config_manager == config_manager
        assert hot_reload_manager.observer is None
        assert hot_reload_manager.reload_delay == 1.0
        
    def test_start_stop(self, hot_reload_manager):
        """测试启动和停止"""
        # 启动热重载
        hot_reload_manager.start()
        assert hot_reload_manager.observer is not None
        assert hot_reload_manager.observer.is_alive()
        assert hot_reload_manager.reload_thread is not None
        assert hot_reload_manager.reload_thread.is_alive()
        
        # 停止热重载
        hot_reload_manager.stop()
        assert hot_reload_manager.observer is None
        assert hot_reload_manager.reload_thread is None
        
    def test_is_config_file(self, hot_reload_manager, temp_dir):
        """测试配置文件检测"""
        # 创建测试文件
        yaml_file = temp_dir / "test.yaml"
        yaml_file.touch()
        
        json_file = temp_dir / "test.json"
        json_file.touch()
        
        txt_file = temp_dir / "test.txt"
        txt_file.touch()
        
        outside_file = Path("/tmp/test.yaml")
        
        # 测试
        assert hot_reload_manager._is_config_file(yaml_file)
        assert hot_reload_manager._is_config_file(json_file)
        assert not hot_reload_manager._is_config_file(txt_file)
        assert not hot_reload_manager._is_config_file(outside_file)
        
    def test_get_config_name_from_file(self, hot_reload_manager, config_manager, temp_dir):
        """测试从文件路径获取配置名称"""
        # 注册配置
        config_manager.register_config_class(SimpleTestConfig, name="test_config")
        
        # 获取配置文件路径
        config_file = config_manager._config_files["test_config"]
        
        # 测试
        config_name = hot_reload_manager._get_config_name_from_file(config_file)
        assert config_name == "test_config"
        
        # 测试不存在的文件
        unknown_file = temp_dir / "unknown.yaml"
        config_name = hot_reload_manager._get_config_name_from_file(unknown_file)
        assert config_name is None
        
    def test_handle_file_change(self, hot_reload_manager, config_manager, temp_dir):
        """测试文件变更处理"""
        # 注册配置
        config_manager.register_config_class(SimpleTestConfig, name="test_config")
        config_file = config_manager._config_files["test_config"]
        
        # 创建配置文件
        config_file.write_text("name: initial\nvalue: 100")
        
        # 模拟文件变更
        hot_reload_manager.handle_file_change(config_file)
        
        # 检查待重载列表
        assert "test_config" in hot_reload_manager.pending_reloads
        assert hot_reload_manager.reload_stats["file_changes_detected"] == 1
        
    def test_force_reload(self, hot_reload_manager, config_manager, temp_dir):
        """测试强制重载"""
        # 注册并加载配置
        config_manager.register_config_class(SimpleTestConfig, name="test_config")
        config_file = config_manager._config_files["test_config"]
        
        # 创建初始配置
        config_file.write_text("name: initial\nvalue: 100")
        config_manager.load_config("test_config")
        
        # 修改配置文件
        config_file.write_text("name: updated\nvalue: 200")
        
        # 强制重载
        success = hot_reload_manager.force_reload("test_config")
        assert success
        
        # 检查配置是否更新
        config = config_manager.get_config("test_config")
        assert config.name == "updated"
        assert config.value == 200
        
        # 检查统计信息
        assert hot_reload_manager.reload_stats["reload_attempts"] == 1
        assert hot_reload_manager.reload_stats["successful_reloads"] == 1
        assert hot_reload_manager.reload_stats["failed_reloads"] == 0
        
    def test_force_reload_failure(self, hot_reload_manager, config_manager, temp_dir):
        """测试强制重载失败"""
        # 注册配置但不加载
        config_manager.register_config_class(SimpleTestConfig, name="test_config")
        config_file = config_manager._config_files["test_config"]
        
        # 创建无效配置文件
        config_file.write_text("invalid: yaml: content:")
        
        # 强制重载
        success = hot_reload_manager.force_reload("test_config")
        assert not success
        
        # 检查统计信息
        assert hot_reload_manager.reload_stats["reload_attempts"] == 1
        assert hot_reload_manager.reload_stats["successful_reloads"] == 0
        assert hot_reload_manager.reload_stats["failed_reloads"] == 1
        
    def test_reload_worker_integration(self, hot_reload_manager, config_manager, temp_dir):
        """测试重载工作线程集成"""
        # 注册并加载配置
        config_manager.register_config_class(SimpleTestConfig, name="test_config")
        config_file = config_manager._config_files["test_config"]
        
        config_file.write_text("name: initial\nvalue: 100")
        config_manager.load_config("test_config")
        
        # 启动热重载
        hot_reload_manager.start()
        
        try:
            # 修改配置文件
            config_file.write_text("name: auto_updated\nvalue: 300")
            
            # 模拟文件变更事件
            hot_reload_manager.handle_file_change(config_file)
            
            # 等待重载完成（重载延迟 + 处理时间）
            time.sleep(hot_reload_manager.reload_delay + 1.0)
            
            # 检查配置是否自动更新
            config = config_manager.get_config("test_config")
            assert config.name == "auto_updated"
            assert config.value == 300
            
        finally:
            hot_reload_manager.stop()
            
    def test_get_stats(self, hot_reload_manager):
        """测试获取统计信息"""
        stats = hot_reload_manager.get_stats()
        
        assert "file_changes_detected" in stats
        assert "reload_attempts" in stats
        assert "successful_reloads" in stats
        assert "failed_reloads" in stats
        assert "pending_reloads" in stats
        assert "is_monitoring" in stats
        assert "last_reload_time" in stats
        
        # 初始状态
        assert stats["file_changes_detected"] == 0
        assert stats["pending_reloads"] == 0
        assert not stats["is_monitoring"]
        
    @patch('services.python_collector.src.marketprism_collector.core.config.hot_reload.Observer')
    def test_start_failure_handling(self, mock_observer_class, hot_reload_manager):
        """测试启动失败处理"""
        # 模拟Observer启动失败
        mock_observer = Mock()
        mock_observer.start.side_effect = Exception("启动失败")
        mock_observer_class.return_value = mock_observer
        
        # 尝试启动
        hot_reload_manager.start()
        
        # 验证清理
        assert hot_reload_manager.observer is None
        
    def test_multiple_file_changes(self, hot_reload_manager, config_manager, temp_dir):
        """测试多个文件变更"""
        # 注册多个配置
        config_manager.register_config_class(SimpleTestConfig, name="config1")
        config_manager.register_config_class(SimpleTestConfig, name="config2")
        
        config_file1 = config_manager._config_files["config1"]
        config_file2 = config_manager._config_files["config2"]
        
        config_file1.write_text("name: config1\nvalue: 1")
        config_file2.write_text("name: config2\nvalue: 2")
        
        # 模拟多个文件变更
        hot_reload_manager.handle_file_change(config_file1)
        hot_reload_manager.handle_file_change(config_file2)
        hot_reload_manager.handle_file_change(config_file1)  # 重复变更
        
        # 检查待重载列表
        assert len(hot_reload_manager.pending_reloads) == 2  # 去重
        assert "config1" in hot_reload_manager.pending_reloads
        assert "config2" in hot_reload_manager.pending_reloads
        
    def test_reload_delay_behavior(self, hot_reload_manager, config_manager, temp_dir):
        """测试重载延迟行为"""
        # 设置较短的重载延迟用于测试
        hot_reload_manager.reload_delay = 0.1
        
        config_manager.register_config_class(SimpleTestConfig, name="test_config")
        config_file = config_manager._config_files["test_config"]
        config_file.write_text("name: test\nvalue: 1")
        
        # 添加到待重载列表
        hot_reload_manager.handle_file_change(config_file)
        
        # 立即检查 - 应该还没有重载
        with hot_reload_manager.reload_lock:
            assert "test_config" in hot_reload_manager.pending_reloads
            
        # 等待延迟时间后检查 - 在实际的工作线程中会被处理
        # 这里我们手动模拟工作线程的逻辑
        time.sleep(0.2)  # 等待超过延迟时间
        
        # 模拟工作线程处理
        import datetime
        with hot_reload_manager.reload_lock:
            now = datetime.datetime.utcnow()
            ready_configs = []
            for config_name, change_time in list(hot_reload_manager.pending_reloads.items()):
                if (now - change_time).total_seconds() >= hot_reload_manager.reload_delay:
                    ready_configs.append(config_name)
                    del hot_reload_manager.pending_reloads[config_name]
                    
        assert "test_config" in ready_configs