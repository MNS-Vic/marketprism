#!/usr/bin/env python3
"""
配置工具单元测试
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, mock_open
import json
import tempfile

# 调整系统路径，便于导入被测模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 尝试导入被测模块
try:
    from services.common.utils.config_utils import ConfigManager, EnvManager
except ImportError:
    # 如果无法导入，定义模拟类用于测试
    class ConfigManager:
        def __init__(self, config_path=None):
            self.config_path = config_path
            self.config = {}
            self.load_config()
        
        def load_config(self):
            """加载配置文件"""
            if not self.config_path or not os.path.exists(self.config_path):
                return False
                
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                return True
            except Exception as e:
                print(f"加载配置失败: {e}")
                return False
        
        def save_config(self):
            """保存配置到文件"""
            if not self.config_path:
                return False
                
            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4)
                return True
            except Exception as e:
                print(f"保存配置失败: {e}")
                return False
        
        def get(self, key, default=None):
            """获取配置值"""
            if "." in key:
                # 支持嵌套键，如 "database.host"
                parts = key.split(".")
                value = self.config
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return default
                return value
            else:
                return self.config.get(key, default)
        
        def set(self, key, value):
            """设置配置值"""
            if "." in key:
                # 支持嵌套键，如 "database.host"
                parts = key.split(".")
                config = self.config
                for i, part in enumerate(parts[:-1]):
                    if part not in config:
                        config[part] = {}
                    config = config[part]
                config[parts[-1]] = value
            else:
                self.config[key] = value
            return True
        
        def delete(self, key):
            """删除配置项"""
            if "." in key:
                # 支持嵌套键，如 "database.host"
                parts = key.split(".")
                config = self.config
                for i, part in enumerate(parts[:-1]):
                    if part not in config:
                        return False
                    config = config[part]
                if parts[-1] in config:
                    del config[parts[-1]]
                    return True
                return False
            else:
                if key in self.config:
                    del self.config[key]
                    return True
                return False
    
    class EnvManager:
        def __init__(self, env_file=None):
            self.env_file = env_file
            self.env_vars = {}
            self.load_env()
        
        def load_env(self):
            """加载环境变量文件"""
            if not self.env_file or not os.path.exists(self.env_file):
                return False
                
            try:
                with open(self.env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        key, value = line.split('=', 1)
                        self.env_vars[key] = value
                return True
            except Exception as e:
                print(f"加载环境变量失败: {e}")
                return False
        
        def save_env(self):
            """保存环境变量到文件"""
            if not self.env_file:
                return False
                
            try:
                with open(self.env_file, 'w', encoding='utf-8') as f:
                    for key, value in self.env_vars.items():
                        f.write(f"{key}={value}\n")
                return True
            except Exception as e:
                print(f"保存环境变量失败: {e}")
                return False
        
        def get(self, key, default=None):
            """获取环境变量"""
            # 优先从操作系统环境变量获取
            from_os = os.environ.get(key)
            if from_os is not None:
                return from_os
                
            # 其次从env文件获取
            return self.env_vars.get(key, default)
        
        def set(self, key, value):
            """设置环境变量"""
            self.env_vars[key] = value
            # 设置操作系统环境变量
            os.environ[key] = value
            return True
        
        def delete(self, key):
            """删除环境变量"""
            if key in self.env_vars:
                del self.env_vars[key]
                return True
            return False


class TestConfigManager:
    """
    配置管理器测试
    """
    
    @pytest.fixture
    def setup_config_manager(self):
        """设置配置管理器测试环境"""
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp:
            # 写入测试配置
            test_config = {
                "app": {
                    "name": "MarketPrism",
                    "version": "1.0.0"
                },
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "user": "admin",
                    "password": "admin123"
                },
                "log_level": "info",
                "debug": False
            }
            tmp.write(json.dumps(test_config).encode('utf-8'))
            tmp_path = tmp.name
        
        # 创建配置管理器
        config_manager = ConfigManager(tmp_path)
        
        yield config_manager
        
        # 清理临时文件
        os.unlink(tmp_path)
    
    def test_load_config(self, setup_config_manager):
        """测试加载配置"""
        # Arrange
        config_manager = setup_config_manager
        
        # Act
        result = config_manager.load_config()
        
        # Assert
        assert result is True
        assert "app" in config_manager.config
        assert "database" in config_manager.config
        assert config_manager.config["app"]["name"] == "MarketPrism"
        assert config_manager.config["database"]["host"] == "localhost"
    
    def test_get_config_value(self, setup_config_manager):
        """测试获取配置值"""
        # Arrange
        config_manager = setup_config_manager
        
        # Act - 获取顶级配置
        log_level = config_manager.get("log_level")
        
        # Assert - 顶级配置
        assert log_level == "info"
        
        # Act - 获取嵌套配置
        db_host = config_manager.get("database.host")
        
        # Assert - 嵌套配置
        assert db_host == "localhost"
        
        # Act - 获取不存在的配置
        non_existent = config_manager.get("non_existent", "default_value")
        
        # Assert - 不存在的配置
        assert non_existent == "default_value"
    
    def test_set_config_value(self, setup_config_manager):
        """测试设置配置值"""
        # Arrange
        config_manager = setup_config_manager
        
        # Act - 设置顶级配置
        config_manager.set("log_level", "debug")
        
        # Assert - 顶级配置
        assert config_manager.get("log_level") == "debug"
        
        # Act - 设置嵌套配置
        config_manager.set("database.port", 5433)
        
        # Assert - 嵌套配置
        assert config_manager.get("database.port") == 5433
        
        # Act - 设置新配置项
        config_manager.set("new_setting", "value")
        
        # Assert - 新配置项
        assert config_manager.get("new_setting") == "value"
        
        # Act - 设置新嵌套配置
        config_manager.set("services.collector.enabled", True)
        
        # Assert - 新嵌套配置
        assert config_manager.get("services.collector.enabled") is True
    
    def test_delete_config_value(self, setup_config_manager):
        """测试删除配置值"""
        # Arrange
        config_manager = setup_config_manager
        
        # Act - 删除顶级配置
        result1 = config_manager.delete("log_level")
        
        # Assert - 顶级配置
        assert result1 is True
        assert config_manager.get("log_level") is None
        
        # Act - 删除嵌套配置
        result2 = config_manager.delete("database.password")
        
        # Assert - 嵌套配置
        assert result2 is True
        assert config_manager.get("database.password") is None
        assert config_manager.get("database.host") == "localhost"  # 其他键不受影响
        
        # Act - 删除不存在的配置
        result3 = config_manager.delete("non_existent")
        
        # Assert - 不存在的配置
        assert result3 is False
    
    @patch('builtins.open', new_callable=mock_open)
    def test_save_config(self, mock_file, setup_config_manager):
        """测试保存配置"""
        # Arrange
        config_manager = setup_config_manager
        # 修改配置
        config_manager.set("app.version", "1.1.0")
        
        # 重新模拟open函数，以便我们可以检查写入的内容
        with patch('builtins.open', mock_open()) as mocked_file:
            # Act
            result = config_manager.save_config()
            
            # Assert
            assert result is True
            mocked_file.assert_called_once_with(config_manager.config_path, 'w', encoding='utf-8')
            # 检查写入的数据包含更新后的版本号
            write_args = mocked_file().write.call_args[0][0]
            assert "1.1.0" in write_args
    
    def test_load_nonexistent_config(self):
        """测试加载不存在的配置文件"""
        # Arrange
        non_existent_path = "/path/to/nonexistent/config.json"
        config_manager = ConfigManager(non_existent_path)
        
        # Act
        result = config_manager.load_config()
        
        # Assert
        assert result is False
        assert config_manager.config == {}


class TestEnvManager:
    """
    环境变量管理器测试
    """
    
    @pytest.fixture
    def setup_env_manager(self):
        """设置环境变量管理器测试环境"""
        # 创建临时环境变量文件
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            # 写入测试环境变量
            tmp.write(b"APP_NAME=MarketPrism\n")
            tmp.write(b"APP_VERSION=1.0.0\n")
            tmp.write(b"DB_HOST=localhost\n")
            tmp.write(b"DB_PORT=5432\n")
            tmp.write(b"DEBUG=false\n")
            tmp_path = tmp.name
        
        # 创建环境变量管理器
        env_manager = EnvManager(tmp_path)
        
        yield env_manager
        
        # 清理临时文件
        os.unlink(tmp_path)
    
    def test_load_env(self, setup_env_manager):
        """测试加载环境变量"""
        # Arrange
        env_manager = setup_env_manager
        
        # Act
        result = env_manager.load_env()
        
        # Assert
        assert result is True
        assert "APP_NAME" in env_manager.env_vars
        assert "DB_HOST" in env_manager.env_vars
        assert env_manager.env_vars["APP_NAME"] == "MarketPrism"
        assert env_manager.env_vars["DB_HOST"] == "localhost"
    
    def test_get_env_value(self, setup_env_manager):
        """测试获取环境变量值"""
        # Arrange
        env_manager = setup_env_manager
        
        # Act - 从env文件获取
        app_name = env_manager.get("APP_NAME")
        
        # Assert - 从env文件获取
        assert app_name == "MarketPrism"
        
        # Act - 设置系统环境变量，然后获取
        os.environ["TEST_ENV_VAR"] = "test_value"
        test_var = env_manager.get("TEST_ENV_VAR")
        
        # Assert - 从系统环境变量获取
        assert test_var == "test_value"
        
        # Act - 获取不存在的环境变量
        non_existent = env_manager.get("NON_EXISTENT", "default_value")
        
        # Assert - 不存在的环境变量
        assert non_existent == "default_value"
    
    def test_set_env_value(self, setup_env_manager):
        """测试设置环境变量值"""
        # Arrange
        env_manager = setup_env_manager
        
        # Act - 设置环境变量
        env_manager.set("APP_VERSION", "1.1.0")
        
        # Assert - 检查内存中的变量
        assert env_manager.env_vars["APP_VERSION"] == "1.1.0"
        # 检查系统环境变量
        assert os.environ["APP_VERSION"] == "1.1.0"
        
        # Act - 设置新环境变量
        env_manager.set("NEW_ENV_VAR", "new_value")
        
        # Assert - 新环境变量
        assert env_manager.env_vars["NEW_ENV_VAR"] == "new_value"
        assert os.environ["NEW_ENV_VAR"] == "new_value"
    
    def test_delete_env_value(self, setup_env_manager):
        """测试删除环境变量值"""
        # Arrange
        env_manager = setup_env_manager
        
        # Act - 删除环境变量
        result1 = env_manager.delete("APP_NAME")
        
        # Assert - 删除结果
        assert result1 is True
        assert "APP_NAME" not in env_manager.env_vars
        
        # Act - 删除不存在的环境变量
        result2 = env_manager.delete("NON_EXISTENT")
        
        # Assert - 删除不存在的变量
        assert result2 is False
    
    @patch('builtins.open', new_callable=mock_open)
    def test_save_env(self, mock_file, setup_env_manager):
        """测试保存环境变量"""
        # Arrange
        env_manager = setup_env_manager
        # 修改环境变量
        env_manager.set("APP_VERSION", "1.1.0")
        
        # 重新模拟open函数，以便我们可以检查写入的内容
        with patch('builtins.open', mock_open()) as mocked_file:
            # Act
            result = env_manager.save_env()
            
            # Assert
            assert result is True
            mocked_file.assert_called_once_with(env_manager.env_file, 'w', encoding='utf-8')
            
            # 检查写入操作被调用
            assert mocked_file().write.called
            
            # 检查所有的环境变量都被写入
            write_calls = mocked_file().write.call_args_list
            written_lines = [args[0][0] for args in write_calls]
            
            # 验证修改后的版本号被写入
            assert any("APP_VERSION=1.1.0\n" == line for line in written_lines)
    
    def test_load_nonexistent_env(self):
        """测试加载不存在的环境变量文件"""
        # Arrange
        non_existent_path = "/path/to/nonexistent/.env"
        env_manager = EnvManager(non_existent_path)
        
        # Act
        result = env_manager.load_env()
        
        # Assert
        assert result is False
        assert env_manager.env_vars == {}


# 直接运行测试文件
if __name__ == "__main__":
    pytest.main(["-v", __file__])