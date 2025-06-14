"""
Data Collector 配置管理 TDD 测试

测试覆盖：
- 配置文件加载
- 环境变量覆盖
- 配置验证
- 默认值处理
- 错误处理
"""

from datetime import datetime, timezone
import os
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, mock_open

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "data-collector" / "src"))

from marketprism_collector.config import Config, CollectorConfig, NATSConfig, ProxyConfig, ConfigPathManager
from marketprism_collector.data_types import ExchangeConfig, Exchange, MarketType, DataType


class TestConfig:
    """配置基本功能测试"""
    
    def test_create_default_config(self):
        """测试：创建默认配置"""
        config = Config()
        
        assert config.collector is not None
        assert config.nats is not None
        assert config.proxy is not None
        assert config.exchanges == []
        assert config.environment == "development"
        assert config.debug is False
    
    def test_collector_config_defaults(self):
        """测试：收集器配置默认值"""
        collector_config = CollectorConfig()
        
        assert collector_config.use_real_exchanges is True
        assert collector_config.log_level == "INFO"
        assert collector_config.http_port == 8080
        assert collector_config.metrics_port == 9090
        assert collector_config.max_reconnect_attempts == 5
        assert collector_config.reconnect_delay == 5
        assert collector_config.enable_orderbook_manager is False
        assert collector_config.enable_scheduler is True
    
    def test_nats_config_defaults(self):
        """测试：NATS配置默认值"""
        nats_config = NATSConfig()
        
        assert nats_config.url == "nats://localhost:4222"
        assert nats_config.client_name == "marketprism-collector"
        assert "MARKET_DATA" in nats_config.streams
        assert nats_config.streams["MARKET_DATA"]["name"] == "MARKET_DATA"
    
    def test_proxy_config_defaults(self):
        """测试：代理配置默认值"""
        proxy_config = ProxyConfig()
        
        assert proxy_config.enabled is False
        assert proxy_config.http_proxy is None
        assert proxy_config.https_proxy is None
        assert proxy_config.no_proxy is None
    
    def test_config_serialization(self):
        """测试：配置序列化"""
        config = Config()
        
        # 测试 model_dump
        data = config.model_dump()
        assert isinstance(data, dict)
        assert "collector" in data
        assert "nats" in data
        assert "proxy" in data
        
        # 测试 model_dump_json
        json_str = config.model_dump_json()
        assert isinstance(json_str, str)
        assert "collector" in json_str
    
    def test_log_level_validation(self):
        """测试：日志级别验证"""
        # 测试有效的日志级别
        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            config = CollectorConfig(log_level=level)
            assert config.log_level == level
        
        # 测试小写也应该可以工作
        config = CollectorConfig(log_level='debug')
        assert config.log_level == 'DEBUG'
        
        # 测试无效的日志级别
        with pytest.raises(ValueError, match="日志级别必须是以下之一"):
            CollectorConfig(log_level='INVALID')


class TestConfigPathManager:
    """配置路径管理器测试"""
    
    def test_default_config_root(self):
        """测试：默认配置根目录"""
        manager = ConfigPathManager()
        
        assert manager.config_root is not None
        assert manager.config_root.name == "config"
    
    def test_custom_config_root(self):
        """测试：自定义配置根目录"""
        custom_path = Path("/tmp/test_config")
        manager = ConfigPathManager(custom_path)
        
        assert manager.config_root == custom_path
    
    def test_get_config_path(self):
        """测试：获取配置文件路径"""
        manager = ConfigPathManager()
        
        # 测试有效的类别
        path = manager.get_config_path('exchanges', 'binance.yaml')
        assert path.name == 'binance.yaml'
        assert 'exchanges' in str(path)
        
        # 测试无效的类别
        with pytest.raises(ValueError, match="未知配置类别"):
            manager.get_config_path('invalid', 'test.yaml')
    
    def test_get_exchange_config_path(self):
        """测试：获取交易所配置文件路径"""
        manager = ConfigPathManager()
        
        path = manager.get_exchange_config_path('binance')
        assert path.name == 'binance.yaml'
        assert 'exchanges' in str(path)
    
    def test_get_collector_config_path(self):
        """测试：获取收集器配置文件路径"""
        manager = ConfigPathManager()
        
        path = manager.get_collector_config_path('test')
        assert path.name == 'test.yaml'
        assert 'collector' in str(path)
    
    def test_list_config_files(self):
        """测试：列出配置文件"""
        manager = ConfigPathManager()
        
        # 测试不存在的目录
        files = manager.list_config_files('exchanges')
        assert isinstance(files, list)  # 应该返回空列表而不是报错


class TestConfigLoading:
    """配置加载测试"""
    
    def test_from_dict_basic(self):
        """测试：从字典创建配置"""
        config_dict = {
            "collector": {
                "log_level": "DEBUG",
                "http_port": 8081
            },
            "environment": "test"
        }
        
        config = Config.from_dict(config_dict)
        
        assert config.collector.log_level == "DEBUG"
        assert config.collector.http_port == 8081
        assert config.environment == "test"
    
    def test_from_dict_with_exchanges_dict(self):
        """测试：从字典格式的交易所配置创建"""
        config_dict = {
            "exchanges": {
                "binance_spot": {
                    "exchange": "binance",
                    "market_type": "spot",
                    "enabled": True,
                    "symbols": ["BTCUSDT"]
                }
            }
        }
        
        config = Config.from_dict(config_dict)
        
        assert len(config.exchanges) == 1
        assert config.exchanges[0].name == "binance"
        assert config.exchanges[0].exchange == Exchange.BINANCE
        assert config.exchanges[0].market_type == MarketType.SPOT
    
    def test_from_dict_with_exchanges_list(self):
        """测试：从列表格式的交易所配置创建"""
        config_dict = {
            "exchanges": [
                {
                    "name": "binance_futures",
                    "exchange": "binance",
                    "market_type": "futures",
                    "enabled": True
                }
            ]
        }
        
        config = Config.from_dict(config_dict)
        
        assert len(config.exchanges) == 1
        assert config.exchanges[0].name == "binance"
        assert config.exchanges[0].exchange == Exchange.BINANCE
        assert config.exchanges[0].market_type == MarketType.FUTURES
    
    def test_load_from_file_not_exists(self):
        """测试：加载不存在的配置文件"""
        with pytest.raises(FileNotFoundError, match="配置文件不存在"):
            Config.load_from_file("/nonexistent/path.yaml")
    
    @patch("builtins.open", new_callable=mock_open)
    @patch("yaml.safe_load")
    @patch("pathlib.Path.exists")
    def test_load_from_file_basic(self, mock_exists, mock_yaml_load, mock_file):
        """测试：加载基本配置文件"""
        # Mock 文件存在
        mock_exists.return_value = True
        
        # Mock YAML内容
        yaml_content = {
            "collector": {
                "log_level": "DEBUG"
            },
            "environment": "test"
        }
        mock_yaml_load.return_value = yaml_content
        
        config = Config.load_from_file("/test/config.yaml")
        
        assert config.collector.log_level == "DEBUG"
        assert config.environment == "test"
        mock_file.assert_called_once()
        mock_yaml_load.assert_called_once()


class TestEnvironmentOverrides:
    """环境变量覆盖测试"""
    
    def test_apply_env_overrides_nats(self):
        """测试：NATS环境变量覆盖"""
        config_data = {"nats": {"url": "nats://localhost:4222"}}
        
        with patch.dict(os.environ, {"NATS_URL": "nats://remote:4222"}):
            result = Config._apply_env_overrides(config_data)
        
        assert result["nats"]["url"] == "nats://remote:4222"
    
    def test_apply_env_overrides_collector(self):
        """测试：收集器环境变量覆盖"""
        config_data = {"collector": {"log_level": "INFO", "http_port": 8080}}
        
        env_vars = {
            "LOG_LEVEL": "DEBUG",
            "HTTP_PORT": "8081"
        }
        
        with patch.dict(os.environ, env_vars):
            result = Config._apply_env_overrides(config_data)
        
        assert result["collector"]["log_level"] == "DEBUG"
        assert result["collector"]["http_port"] == 8081
    
    def test_apply_env_overrides_proxy(self):
        """测试：代理环境变量覆盖"""
        config_data = {}
        
        env_vars = {
            "HTTP_PROXY": "http://proxy:8080",
            "HTTPS_PROXY": "https://proxy:8080",
            "NO_PROXY": "localhost,127.0.0.1"
        }
        
        with patch.dict(os.environ, env_vars):
            result = Config._apply_env_overrides(config_data)
        
        assert result["proxy"]["enabled"] is True
        assert result["proxy"]["http_proxy"] == "http://proxy:8080"
        assert result["proxy"]["https_proxy"] == "https://proxy:8080"
        assert result["proxy"]["no_proxy"] == "localhost,127.0.0.1"
    
    def test_apply_env_overrides_environment(self):
        """测试：环境配置覆盖"""
        config_data = {}
        
        env_vars = {
            "ENVIRONMENT": "production",
            "DEBUG": "true"
        }
        
        with patch.dict(os.environ, env_vars):
            result = Config._apply_env_overrides(config_data)
        
        assert result["environment"] == "production"
        assert result["debug"] is True
    
    def test_apply_env_overrides_debug_false(self):
        """测试：DEBUG环境变量为false"""
        config_data = {}
        
        for false_value in ["false", "0", "no", "False"]:
            with patch.dict(os.environ, {"DEBUG": false_value}):
                result = Config._apply_env_overrides(config_data)
                assert result["debug"] is False


class TestConfigMethods:
    """配置方法测试"""
    
    def test_get_enabled_exchanges(self):
        """测试：获取启用的交易所"""
        exchanges = [
            ExchangeConfig(exchange=Exchange.BINANCE, enabled=True),
            ExchangeConfig(exchange=Exchange.OKX, enabled=False),
            ExchangeConfig(exchange=Exchange.DERIBIT, enabled=True)
        ]
        
        config = Config(exchanges=exchanges)
        enabled = config.get_enabled_exchanges()
        
        assert len(enabled) == 2
        assert enabled[0].exchange == Exchange.BINANCE
        assert enabled[1].exchange == Exchange.DERIBIT
    
    def test_get_exchange_by_name(self):
        """测试：通过名称获取交易所配置"""
        exchanges = [
            ExchangeConfig(exchange=Exchange.BINANCE),
            ExchangeConfig(exchange=Exchange.OKX)
        ]
        
        config = Config(exchanges=exchanges)
        
        # 测试找到的情况
        binance_config = config.get_exchange_by_name("binance")
        assert binance_config is not None
        assert binance_config.exchange == Exchange.BINANCE
        
        # 测试未找到的情况
        missing_config = config.get_exchange_by_name("nonexistent")
        assert missing_config is None
    
    @patch.dict(os.environ, {}, clear=True)
    def test_setup_proxy_env_disabled(self):
        """测试：代理未启用时不设置环境变量"""
        proxy_config = ProxyConfig(enabled=False)
        config = Config(proxy=proxy_config)
        
        config.setup_proxy_env()
        
        assert "HTTP_PROXY" not in os.environ
        assert "HTTPS_PROXY" not in os.environ
        assert "NO_PROXY" not in os.environ
    
    def test_setup_proxy_env_enabled(self):
        """测试：代理启用时设置环境变量"""
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy:8080",
            https_proxy="https://proxy:8080",
            no_proxy="localhost"
        )
        config = Config(proxy=proxy_config)
        
        with patch.dict(os.environ, {}, clear=True):
            config.setup_proxy_env()
            
            assert os.environ["HTTP_PROXY"] == "http://proxy:8080"
            assert os.environ["HTTPS_PROXY"] == "https://proxy:8080"
            assert os.environ["NO_PROXY"] == "localhost"


class TestConfigEdgeCases:
    """配置边缘情况测试"""
    
    def test_config_with_invalid_exchange_name(self):
        """测试：无效交易所名称的处理"""
        config_dict = {
            "exchanges": {
                "invalid_exchange": {
                    "market_type": "spot",
                    "enabled": True
                }
            }
        }
        
        # 应该使用默认值而不是抛出异常
        config = Config.from_dict(config_dict)
        
        assert len(config.exchanges) == 1
        assert config.exchanges[0].exchange == Exchange.BINANCE  # 默认值
    
    def test_config_without_exchange_field(self):
        """测试：没有exchange字段的配置"""
        config_dict = {
            "exchanges": [
                {
                    "name": "test_exchange",
                    "market_type": "spot",
                    "enabled": True
                }
            ]
        }
        
        config = Config.from_dict(config_dict)
        
        assert len(config.exchanges) == 1
        assert config.exchanges[0].exchange == Exchange.BINANCE  # 默认值
    
    def test_empty_config_dict(self):
        """测试：空配置字典"""
        config = Config.from_dict({})
        
        assert config.collector is not None
        assert config.nats is not None
        assert config.proxy is not None
        assert config.exchanges == []
    
    def test_path_manager_with_none_config_root(self):
        """测试：配置根目录为None的路径管理器"""
        manager = ConfigPathManager(None)
        
        # 应该自动解析到项目根目录的config文件夹
        assert manager.config_root is not None
        assert manager.config_root.name == "config"


@pytest.mark.asyncio
class TestConfigAsync:
    """配置异步操作测试"""
    
    async def test_config_can_be_used_in_async_context(self):
        """测试：配置可以在异步上下文中使用"""
        config = Config()
        
        # 模拟异步操作
        import asyncio
        await asyncio.sleep(0.001)
        
        assert config.collector is not None
        assert config.environment == "development"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])