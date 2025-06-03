"""
Python Collector 配置管理单元测试

测试配置加载、验证、环境变量覆盖等功能
"""

import pytest
import os
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, mock_open

# 导入被测试的模块
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.config import (
    NATSConfig, ProxyConfig, CollectorConfig, Config, create_default_config
)
from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType


class TestNATSConfig:
    """测试NATS配置"""
    
    def test_default_nats_config(self):
        """测试默认NATS配置"""
        config = NATSConfig()
        
        assert config.url == "nats://localhost:4222"
        assert config.client_name == "marketprism-collector"
        assert "MARKET_DATA" in config.streams
        
        # 验证默认流配置
        market_data_stream = config.streams["MARKET_DATA"]
        assert market_data_stream["name"] == "MARKET_DATA"
        assert market_data_stream["subjects"] == ["market.>"]
        assert market_data_stream["retention"] == "limits"
        assert market_data_stream["max_msgs"] == 1000000
        assert market_data_stream["max_bytes"] == 1073741824
        assert market_data_stream["max_age"] == 86400
        assert market_data_stream["max_consumers"] == 10
        assert market_data_stream["replicas"] == 1
    
    def test_custom_nats_config(self):
        """测试自定义NATS配置"""
        custom_streams = {
            "CUSTOM_STREAM": {
                "name": "CUSTOM_STREAM",
                "subjects": ["custom.>"],
                "retention": "workqueue",
                "max_msgs": 500000,
                "max_bytes": 536870912,  # 512MB
                "max_age": 43200,  # 12 hours
                "max_consumers": 5,
                "replicas": 3
            }
        }
        
        config = NATSConfig(
            url="nats://remote-server:4222",
            client_name="custom-collector",
            streams=custom_streams
        )
        
        assert config.url == "nats://remote-server:4222"
        assert config.client_name == "custom-collector"
        assert config.streams == custom_streams
    
    def test_nats_config_serialization(self):
        """测试NATS配置序列化"""
        config = NATSConfig()
        
        # 测试序列化
        config_dict = config.model_dump()
        assert isinstance(config_dict, dict)
        assert config_dict["url"] == "nats://localhost:4222"
        assert "streams" in config_dict
        
        # 测试JSON序列化
        json_str = config.model_dump_json()
        assert isinstance(json_str, str)


class TestProxyConfig:
    """测试代理配置"""
    
    def test_default_proxy_config(self):
        """测试默认代理配置"""
        config = ProxyConfig()
        
        assert config.enabled is False
        assert config.http_proxy is None
        assert config.https_proxy is None
        assert config.no_proxy is None
    
    def test_enabled_proxy_config(self):
        """测试启用的代理配置"""
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8443",
            no_proxy="localhost,127.0.0.1"
        )
        
        assert config.enabled is True
        assert config.http_proxy == "http://proxy.example.com:8080"
        assert config.https_proxy == "https://proxy.example.com:8443"
        assert config.no_proxy == "localhost,127.0.0.1"
    
    def test_partial_proxy_config(self):
        """测试部分代理配置"""
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080"
            # https_proxy 和 no_proxy 保持默认值 None
        )
        
        assert config.enabled is True
        assert config.http_proxy == "http://proxy.example.com:8080"
        assert config.https_proxy is None
        assert config.no_proxy is None


class TestCollectorConfig:
    """测试收集器配置"""
    
    def test_default_collector_config(self):
        """测试默认收集器配置"""
        config = CollectorConfig()
        
        assert config.use_real_exchanges is True
        assert config.log_level == "INFO"
        assert config.http_port == 8080
        assert config.metrics_port == 9090
        assert config.max_reconnect_attempts == 5
        assert config.reconnect_delay == 5
        assert config.max_concurrent_connections == 10
        assert config.message_buffer_size == 1000
    
    def test_custom_collector_config(self):
        """测试自定义收集器配置"""
        config = CollectorConfig(
            use_real_exchanges=False,
            log_level="DEBUG",
            http_port=9080,
            metrics_port=9091,
            max_reconnect_attempts=10,
            reconnect_delay=10,
            max_concurrent_connections=20,
            message_buffer_size=2000
        )
        
        assert config.use_real_exchanges is False
        assert config.log_level == "DEBUG"
        assert config.http_port == 9080
        assert config.metrics_port == 9091
        assert config.max_reconnect_attempts == 10
        assert config.reconnect_delay == 10
        assert config.max_concurrent_connections == 20
        assert config.message_buffer_size == 2000
    
    def test_log_level_validation(self):
        """测试日志级别验证"""
        # 测试有效的日志级别
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        for level in valid_levels:
            config = CollectorConfig(log_level=level)
            assert config.log_level == level
            
            # 测试小写也能正常工作
            config_lower = CollectorConfig(log_level=level.lower())
            assert config_lower.log_level == level
    
    def test_invalid_log_level(self):
        """测试无效的日志级别"""
        with pytest.raises(ValueError, match="日志级别必须是以下之一"):
            CollectorConfig(log_level="INVALID")
        
        with pytest.raises(ValueError, match="日志级别必须是以下之一"):
            CollectorConfig(log_level="TRACE")


class TestConfig:
    """测试主配置类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = Config()
        
        assert isinstance(config.collector, CollectorConfig)
        assert isinstance(config.nats, NATSConfig)
        assert isinstance(config.proxy, ProxyConfig)
        assert isinstance(config.exchanges, list)
        assert len(config.exchanges) == 0
        assert config.environment == "development"
        assert config.debug is False
    
    def test_custom_config(self):
        """测试自定义配置"""
        collector_config = CollectorConfig(log_level="DEBUG")
        nats_config = NATSConfig(url="nats://custom:4222")
        proxy_config = ProxyConfig(enabled=True)
        
        config = Config(
            collector=collector_config,
            nats=nats_config,
            proxy=proxy_config,
            environment="production",
            debug=True
        )
        
        assert config.collector.log_level == "DEBUG"
        assert config.nats.url == "nats://custom:4222"
        assert config.proxy.enabled is True
        assert config.environment == "production"
        assert config.debug is True
    
    def test_get_enabled_exchanges(self):
        """测试获取启用的交易所"""
        exchange1 = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            enabled=True,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443",
            data_types=[DataType.TRADE],
            symbols=["BTC/USDT"]
        )
        
        exchange2 = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.FUTURES,
            enabled=False,  # 禁用
            base_url="https://www.okx.com",
            ws_url="wss://ws.okx.com:8443",
            data_types=[DataType.ORDERBOOK],
            symbols=["BTC-USDT-SWAP"]
        )
        
        exchange3 = ExchangeConfig(
            exchange=Exchange.DERIBIT,
            market_type=MarketType.OPTIONS,
            enabled=True,
            base_url="https://www.deribit.com",
            ws_url="wss://www.deribit.com/ws/api/v2",
            data_types=[DataType.TICKER],
            symbols=["BTC-PERPETUAL"]
        )
        
        config = Config(exchanges=[exchange1, exchange2, exchange3])
        enabled_exchanges = config.get_enabled_exchanges()
        
        assert len(enabled_exchanges) == 2
        assert exchange1 in enabled_exchanges
        assert exchange2 not in enabled_exchanges
        assert exchange3 in enabled_exchanges
    
    def test_get_exchange_by_name(self):
        """测试通过名称获取交易所配置"""
        exchange1 = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443",
            data_types=[DataType.TRADE],
            symbols=["BTC/USDT"]
        )
        
        exchange2 = ExchangeConfig(
            exchange=Exchange.OKX,
            market_type=MarketType.FUTURES,
            base_url="https://www.okx.com",
            ws_url="wss://ws.okx.com:8443",
            data_types=[DataType.ORDERBOOK],
            symbols=["BTC-USDT-SWAP"]
        )
        
        config = Config(exchanges=[exchange1, exchange2])
        
        # 测试找到交易所
        binance_config = config.get_exchange_by_name("binance")
        assert binance_config is not None
        assert binance_config.exchange == Exchange.BINANCE
        
        okx_config = config.get_exchange_by_name("okx")
        assert okx_config is not None
        assert okx_config.exchange == Exchange.OKX
        
        # 测试找不到交易所
        not_found = config.get_exchange_by_name("nonexistent")
        assert not_found is None
    
    def test_setup_proxy_env(self):
        """测试设置代理环境变量"""
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8443",
            no_proxy="localhost,127.0.0.1"
        )
        
        config = Config(proxy=proxy_config)
        
        # 清除现有的代理环境变量
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
            if key in os.environ:
                del os.environ[key]
        
        # 设置代理环境变量
        config.setup_proxy_env()
        
        assert os.environ.get('HTTP_PROXY') == "http://proxy.example.com:8080"
        assert os.environ.get('HTTPS_PROXY') == "https://proxy.example.com:8443"
        assert os.environ.get('NO_PROXY') == "localhost,127.0.0.1"
        
        # 清理环境变量
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
            if key in os.environ:
                del os.environ[key]
    
    def test_setup_proxy_env_disabled(self):
        """测试禁用代理时不设置环境变量"""
        proxy_config = ProxyConfig(enabled=False)
        config = Config(proxy=proxy_config)
        
        # 清除现有的代理环境变量
        for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']:
            if key in os.environ:
                del os.environ[key]
        
        # 尝试设置代理环境变量（应该不会设置）
        config.setup_proxy_env()
        
        assert os.environ.get('HTTP_PROXY') is None
        assert os.environ.get('HTTPS_PROXY') is None
        assert os.environ.get('NO_PROXY') is None


class TestConfigFileLoading:
    """测试配置文件加载"""
    
    def test_load_from_nonexistent_file(self):
        """测试加载不存在的配置文件"""
        with pytest.raises(FileNotFoundError, match="配置文件不存在"):
            Config.load_from_file("/nonexistent/config.yaml")
    
    def test_load_basic_config_file(self):
        """测试加载基本配置文件"""
        config_data = {
            'collector': {
                'log_level': 'DEBUG',
                'http_port': 9080
            },
            'nats': {
                'url': 'nats://test:4222'
            },
            'environment': 'test',
            'debug': True
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file_path = f.name
        
        try:
            config = Config.load_from_file(config_file_path)
            
            assert config.collector.log_level == 'DEBUG'
            assert config.collector.http_port == 9080
            assert config.nats.url == 'nats://test:4222'
            assert config.environment == 'test'
            assert config.debug is True
            
        finally:
            os.unlink(config_file_path)
    
    def test_load_config_with_exchanges(self):
        """测试加载包含交易所配置的文件"""
        # 创建交易所配置文件
        exchange_config_data = {
            'exchange': 'binance',
            'market_type': 'spot',
            'enabled': True,
            'base_url': 'https://api.binance.com',
            'ws_url': 'wss://stream.binance.com:9443',
            'data_types': ['trade', 'orderbook'],
            'symbols': ['BTC/USDT', 'ETH/USDT']
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(exchange_config_data, f)
            exchange_config_path = f.name
        
        # 创建主配置文件
        main_config_data = {
            'collector': {
                'log_level': 'INFO'
            },
            'exchanges': {
                'configs': [exchange_config_path]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(main_config_data, f)
            main_config_path = f.name
        
        try:
            config = Config.load_from_file(main_config_path)
            
            assert len(config.exchanges) == 1
            exchange = config.exchanges[0]
            assert exchange.exchange == Exchange.BINANCE
            assert exchange.market_type == MarketType.SPOT
            assert exchange.enabled is True
            assert DataType.TRADE in exchange.data_types
            assert DataType.ORDERBOOK in exchange.data_types
            assert "BTC/USDT" in exchange.symbols
            
        finally:
            os.unlink(exchange_config_path)
            os.unlink(main_config_path)
    
    @patch.dict(os.environ, {
        'NATS_URL': 'nats://env-server:4222',
        'LOG_LEVEL': 'WARNING',
        'HTTP_PORT': '9999',
        'HTTP_PROXY': 'http://env-proxy:8080',
        'ENVIRONMENT': 'production',
        'DEBUG': 'true'
    })
    def test_env_overrides(self):
        """测试环境变量覆盖"""
        config_data = {
            'collector': {
                'log_level': 'INFO',
                'http_port': 8080
            },
            'nats': {
                'url': 'nats://localhost:4222'
            },
            'environment': 'development',
            'debug': False
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file_path = f.name
        
        try:
            config = Config.load_from_file(config_file_path)
            
            # 验证环境变量覆盖生效
            assert config.nats.url == 'nats://env-server:4222'
            assert config.collector.log_level == 'WARNING'
            assert config.collector.http_port == 9999
            assert config.proxy.enabled is True
            assert config.proxy.http_proxy == 'http://env-proxy:8080'
            assert config.environment == 'production'
            assert config.debug is True
            
        finally:
            os.unlink(config_file_path)
    
    @patch.dict(os.environ, {
        'BINANCE_SPOT_API_KEY': 'test_api_key',
        'BINANCE_SPOT_API_SECRET': 'test_api_secret'
    })
    def test_exchange_api_credentials_from_env(self):
        """测试从环境变量加载交易所API凭证"""
        # 创建交易所配置文件（不包含API凭证）
        exchange_config_data = {
            'exchange': 'binance',
            'market_type': 'spot',
            'enabled': True,
            'base_url': 'https://api.binance.com',
            'ws_url': 'wss://stream.binance.com:9443',
            'data_types': ['trade'],
            'symbols': ['BTC/USDT']
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(exchange_config_data, f)
            exchange_config_path = f.name
        
        # 创建主配置文件
        main_config_data = {
            'exchanges': {
                'configs': [exchange_config_path]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(main_config_data, f)
            main_config_path = f.name
        
        try:
            config = Config.load_from_file(main_config_path)
            
            assert len(config.exchanges) == 1
            exchange = config.exchanges[0]
            assert exchange.api_key == 'test_api_key'
            assert exchange.api_secret == 'test_api_secret'
            
        finally:
            os.unlink(exchange_config_path)
            os.unlink(main_config_path)


class TestCreateDefaultConfig:
    """测试创建默认配置"""
    
    def test_create_default_config(self):
        """测试创建默认配置"""
        config = create_default_config()
        
        assert isinstance(config, Config)
        assert isinstance(config.collector, CollectorConfig)
        assert isinstance(config.nats, NATSConfig)
        assert isinstance(config.proxy, ProxyConfig)
        assert isinstance(config.exchanges, list)
        
        # 验证默认值
        assert config.collector.log_level == "INFO"
        assert config.nats.url == "nats://localhost:4222"
        assert config.proxy.enabled is False
        assert len(config.exchanges) == 1  # 包含默认的Binance配置
        assert config.environment == "development"
        assert config.debug is False
        
        # 验证默认的Binance配置
        default_exchange = config.exchanges[0]
        assert default_exchange.exchange == Exchange.BINANCE
        assert default_exchange.market_type == MarketType.SPOT
        assert default_exchange.enabled is True
        assert DataType.TRADE in default_exchange.data_types
        assert DataType.ORDERBOOK in default_exchange.data_types
        assert DataType.TICKER in default_exchange.data_types
        assert "BTCUSDT" in default_exchange.symbols


class TestConfigIntegration:
    """测试配置集成"""
    
    def test_complete_config_workflow(self):
        """测试完整的配置工作流"""
        # 创建完整的配置
        collector_config = CollectorConfig(
            log_level="DEBUG",
            http_port=9080,
            use_real_exchanges=True
        )
        
        nats_config = NATSConfig(
            url="nats://production:4222",
            client_name="prod-collector"
        )
        
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy:8080"
        )
        
        exchange_config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            enabled=True,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443",
            data_types=[DataType.TRADE, DataType.ORDERBOOK],
            symbols=["BTC/USDT", "ETH/USDT"]
        )
        
        config = Config(
            collector=collector_config,
            nats=nats_config,
            proxy=proxy_config,
            exchanges=[exchange_config],
            environment="production",
            debug=False
        )
        
        # 验证配置完整性
        assert config.collector.log_level == "DEBUG"
        assert config.nats.url == "nats://production:4222"
        assert config.proxy.enabled is True
        assert len(config.exchanges) == 1
        assert config.environment == "production"
        
        # 验证交易所配置
        enabled_exchanges = config.get_enabled_exchanges()
        assert len(enabled_exchanges) == 1
        assert enabled_exchanges[0].exchange == Exchange.BINANCE
        
        # 验证通过名称查找交易所
        binance_config = config.get_exchange_by_name("binance")
        assert binance_config is not None
        assert binance_config.market_type == MarketType.SPOT
    
    def test_config_serialization_roundtrip(self):
        """测试配置序列化往返"""
        original_config = create_default_config()
        
        # 序列化
        config_dict = original_config.model_dump()
        
        # 反序列化
        restored_config = Config(**config_dict)
        
        # 验证配置一致性
        assert restored_config.collector.log_level == original_config.collector.log_level
        assert restored_config.nats.url == original_config.nats.url
        assert restored_config.proxy.enabled == original_config.proxy.enabled
        assert restored_config.environment == original_config.environment
        assert restored_config.debug == original_config.debug


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 