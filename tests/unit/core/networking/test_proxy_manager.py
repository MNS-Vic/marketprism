"""
代理配置管理器测试
测试ProxyConfigManager的核心功能
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, Optional

# 导入被测试的模块
try:
    from core.networking.proxy_manager import (
        ProxyConfigManager,
        ProxyConfig,
        proxy_manager
    )
    HAS_PROXY_MODULES = True
except ImportError as e:
    HAS_PROXY_MODULES = False
    pytest.skip(f"代理模块导入失败: {e}", allow_module_level=True)


@pytest.mark.skipif(not HAS_PROXY_MODULES, reason="代理模块不可用")
class TestProxyConfig:
    """代理配置数据类测试"""
    
    def test_proxy_config_default_values(self):
        """测试代理配置默认值"""
        config = ProxyConfig()
        
        assert config.enabled is False
        assert config.http_proxy is None
        assert config.https_proxy is None
        assert config.socks4_proxy is None
        assert config.socks5_proxy is None
        assert config.no_proxy is None
        
    def test_proxy_config_custom_values(self):
        """测试代理配置自定义值"""
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8443",
            socks5_proxy="socks5://proxy.example.com:1080",
            no_proxy="localhost,127.0.0.1"
        )
        
        assert config.enabled is True
        assert config.http_proxy == "http://proxy.example.com:8080"
        assert config.https_proxy == "https://proxy.example.com:8443"
        assert config.socks5_proxy == "socks5://proxy.example.com:1080"
        assert config.no_proxy == "localhost,127.0.0.1"
        
    def test_proxy_config_get_http_proxy(self):
        """测试获取HTTP代理"""
        # 只有HTTP代理
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080"
        )
        assert config.get_http_proxy() == "http://proxy.example.com:8080"
        
        # 只有HTTPS代理
        config = ProxyConfig(
            enabled=True,
            https_proxy="https://proxy.example.com:8443"
        )
        assert config.get_http_proxy() == "https://proxy.example.com:8443"
        
        # 两者都有，优先HTTPS
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8443"
        )
        assert config.get_http_proxy() == "https://proxy.example.com:8443"
        
        # 都没有
        config = ProxyConfig(enabled=True)
        assert config.get_http_proxy() is None
        
    def test_proxy_config_get_socks_proxy(self):
        """测试获取SOCKS代理"""
        # 只有SOCKS4代理
        config = ProxyConfig(
            enabled=True,
            socks4_proxy="socks4://proxy.example.com:1080"
        )
        assert config.get_socks_proxy() == "socks4://proxy.example.com:1080"
        
        # 只有SOCKS5代理
        config = ProxyConfig(
            enabled=True,
            socks5_proxy="socks5://proxy.example.com:1080"
        )
        assert config.get_socks_proxy() == "socks5://proxy.example.com:1080"
        
        # 两者都有，优先SOCKS5
        config = ProxyConfig(
            enabled=True,
            socks4_proxy="socks4://proxy.example.com:1080",
            socks5_proxy="socks5://proxy.example.com:1080"
        )
        assert config.get_socks_proxy() == "socks5://proxy.example.com:1080"
        
    def test_proxy_config_has_proxy(self):
        """测试检查是否配置了代理"""
        # 未启用
        config = ProxyConfig(
            enabled=False,
            http_proxy="http://proxy.example.com:8080"
        )
        assert config.has_proxy() is False
        
        # 启用但无代理配置
        config = ProxyConfig(enabled=True)
        assert config.has_proxy() is False
        
        # 启用且有HTTP代理
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080"
        )
        assert config.has_proxy() is True
        
        # 启用且有SOCKS代理
        config = ProxyConfig(
            enabled=True,
            socks5_proxy="socks5://proxy.example.com:1080"
        )
        assert config.has_proxy() is True
        
    def test_proxy_config_to_aiohttp_proxy(self):
        """测试转换为aiohttp代理格式"""
        # 无代理
        config = ProxyConfig()
        assert config.to_aiohttp_proxy() is None
        
        # HTTP代理
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080"
        )
        assert config.to_aiohttp_proxy() == "http://proxy.example.com:8080"
        
        # SOCKS代理
        config = ProxyConfig(
            enabled=True,
            socks5_proxy="socks5://proxy.example.com:1080"
        )
        assert config.to_aiohttp_proxy() == "socks5://proxy.example.com:1080"
        
        # HTTP优先于SOCKS
        config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            socks5_proxy="socks5://proxy.example.com:1080"
        )
        assert config.to_aiohttp_proxy() == "http://proxy.example.com:8080"


@pytest.mark.skipif(not HAS_PROXY_MODULES, reason="代理模块不可用")
class TestProxyConfigManager:
    """代理配置管理器测试"""
    
    def test_proxy_manager_initialization(self):
        """测试代理管理器初始化"""
        manager = ProxyConfigManager()
        
        assert manager is not None
        assert hasattr(manager, 'logger')
        assert hasattr(manager, '_cache')
        assert isinstance(manager._cache, dict)
        
    def test_proxy_manager_get_proxy_config_no_config(self):
        """测试无配置时获取代理配置"""
        manager = ProxyConfigManager()
        
        with patch.dict(os.environ, {}, clear=True):
            config = manager.get_proxy_config()
            
            assert isinstance(config, ProxyConfig)
            assert config.enabled is False
            assert config.has_proxy() is False
            
    def test_proxy_manager_get_proxy_config_from_exchange(self):
        """测试从交易所配置获取代理配置"""
        manager = ProxyConfigManager()
        
        exchange_config = {
            "proxy": {
                "enabled": True,
                "http_proxy": "http://exchange-proxy.com:8080",
                "https_proxy": "https://exchange-proxy.com:8443"
            }
        }
        
        config = manager.get_proxy_config(exchange_config)
        
        assert config.enabled is True
        assert config.http_proxy == "http://exchange-proxy.com:8080"
        assert config.https_proxy == "https://exchange-proxy.com:8443"
        assert config.has_proxy() is True
        
    def test_proxy_manager_get_proxy_config_from_service(self):
        """测试从服务配置获取代理配置"""
        manager = ProxyConfigManager()
        
        service_config = {
            "proxy": {
                "enabled": True,
                "socks5_proxy": "socks5://service-proxy.com:1080"
            }
        }
        
        config = manager.get_proxy_config(service_config=service_config)
        
        assert config.enabled is True
        assert config.socks5_proxy == "socks5://service-proxy.com:1080"
        assert config.has_proxy() is True
        
    @patch.dict(os.environ, {
        'HTTP_PROXY': 'http://env-proxy.com:8080',
        'HTTPS_PROXY': 'https://env-proxy.com:8443',
        'NO_PROXY': 'localhost,127.0.0.1'
    })
    def test_proxy_manager_get_proxy_config_from_env(self):
        """测试从环境变量获取代理配置"""
        manager = ProxyConfigManager()
        
        config = manager.get_proxy_config()
        
        assert config.enabled is True
        assert config.http_proxy == "http://env-proxy.com:8080"
        assert config.https_proxy == "https://env-proxy.com:8443"
        assert config.no_proxy == "localhost,127.0.0.1"
        assert config.has_proxy() is True
        
    def test_proxy_manager_config_priority(self):
        """测试配置优先级：交易所 > 服务 > 环境变量"""
        manager = ProxyConfigManager()
        
        # 设置环境变量
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://env-proxy.com:8080'}):
            exchange_config = {
                "proxy": {
                    "enabled": True,
                    "http_proxy": "http://exchange-proxy.com:8080"
                }
            }
            
            service_config = {
                "proxy": {
                    "enabled": True,
                    "http_proxy": "http://service-proxy.com:8080"
                }
            }
            
            # 交易所配置优先
            config = manager.get_proxy_config(exchange_config, service_config)
            assert config.http_proxy == "http://exchange-proxy.com:8080"
            
            # 服务配置次优先
            config = manager.get_proxy_config(service_config=service_config)
            assert config.http_proxy == "http://service-proxy.com:8080"
            
            # 环境变量最后
            config = manager.get_proxy_config()
            assert config.http_proxy == "http://env-proxy.com:8080"
            
    def test_proxy_manager_cache_functionality(self):
        """测试代理配置缓存功能"""
        manager = ProxyConfigManager()
        
        exchange_config = {
            "proxy": {
                "enabled": True,
                "http_proxy": "http://cached-proxy.com:8080"
            }
        }
        
        # 第一次调用
        config1 = manager.get_proxy_config(exchange_config)
        
        # 第二次调用应该使用缓存
        config2 = manager.get_proxy_config(exchange_config)
        
        assert config1 is config2  # 应该是同一个对象（缓存）
        assert len(manager._cache) == 1
        
    def test_proxy_manager_clear_cache(self):
        """测试清除代理配置缓存"""
        manager = ProxyConfigManager()
        
        exchange_config = {
            "proxy": {
                "enabled": True,
                "http_proxy": "http://test-proxy.com:8080"
            }
        }
        
        # 创建缓存
        manager.get_proxy_config(exchange_config)
        assert len(manager._cache) == 1
        
        # 清除缓存
        manager.clear_cache()
        assert len(manager._cache) == 0
        
    def test_proxy_manager_get_proxy_dict_for_requests(self):
        """测试获取requests库格式的代理字典"""
        manager = ProxyConfigManager()
        
        proxy_config = ProxyConfig(
            enabled=True,
            http_proxy="http://proxy.example.com:8080",
            https_proxy="https://proxy.example.com:8443"
        )
        
        proxy_dict = manager.get_proxy_dict_for_requests(proxy_config)
        
        expected = {
            'http': 'http://proxy.example.com:8080',
            'https': 'https://proxy.example.com:8443'
        }
        
        assert proxy_dict == expected
        
    def test_proxy_manager_get_proxy_dict_for_requests_no_proxy(self):
        """测试无代理时获取requests格式字典"""
        manager = ProxyConfigManager()
        
        proxy_config = ProxyConfig(enabled=False)
        proxy_dict = manager.get_proxy_dict_for_requests(proxy_config)
        
        assert proxy_dict == {}
        
    def test_proxy_manager_validate_proxy_url(self):
        """测试代理URL验证"""
        manager = ProxyConfigManager()
        
        # 有效的HTTP代理
        assert manager._validate_proxy_url("http://proxy.example.com:8080") is True
        
        # 有效的HTTPS代理
        assert manager._validate_proxy_url("https://proxy.example.com:8443") is True
        
        # 有效的SOCKS5代理
        assert manager._validate_proxy_url("socks5://proxy.example.com:1080") is True
        
        # 无效的URL
        assert manager._validate_proxy_url("invalid-url") is False
        
        # 空URL
        assert manager._validate_proxy_url("") is False
        assert manager._validate_proxy_url(None) is False


@pytest.mark.skipif(not HAS_PROXY_MODULES, reason="代理模块不可用")
class TestProxyManagerErrorHandling:
    """代理管理器错误处理测试"""
    
    def test_proxy_manager_invalid_exchange_config(self):
        """测试无效交易所配置处理"""
        manager = ProxyConfigManager()
        
        # 无效的配置格式
        invalid_configs = [
            {"proxy": "not_a_dict"},
            {"proxy": {"enabled": "not_boolean"}},
            {"proxy": {"http_proxy": 123}},  # 非字符串
        ]
        
        for invalid_config in invalid_configs:
            # 应该回退到默认配置，不抛出异常
            config = manager.get_proxy_config(invalid_config)
            assert isinstance(config, ProxyConfig)
            
    def test_proxy_manager_malformed_env_vars(self):
        """测试格式错误的环境变量处理"""
        manager = ProxyConfigManager()
        
        with patch.dict(os.environ, {
            'HTTP_PROXY': 'invalid-proxy-url',
            'HTTPS_PROXY': 'also-invalid'
        }):
            # 应该处理无效的环境变量，返回禁用的配置
            config = manager.get_proxy_config()
            
            # 由于URL无效，应该禁用代理
            assert config.enabled is False or not config.has_proxy()
            
    def test_proxy_manager_missing_proxy_section(self):
        """测试缺少代理配置段的处理"""
        manager = ProxyConfigManager()
        
        # 配置中没有proxy段
        config_without_proxy = {
            "name": "test_exchange",
            "api_key": "test_key"
        }
        
        config = manager.get_proxy_config(config_without_proxy)
        
        assert isinstance(config, ProxyConfig)
        assert config.enabled is False


@pytest.mark.skipif(not HAS_PROXY_MODULES, reason="代理模块不可用")
class TestProxyManagerGlobalInstance:
    """代理管理器全局实例测试"""
    
    def test_global_proxy_manager_exists(self):
        """测试全局代理管理器存在"""
        assert proxy_manager is not None
        assert isinstance(proxy_manager, ProxyConfigManager)
        
    def test_global_proxy_manager_usage(self):
        """测试使用全局代理管理器"""
        exchange_config = {
            "proxy": {
                "enabled": True,
                "http_proxy": "http://global-test.com:8080"
            }
        }
        
        config = proxy_manager.get_proxy_config(exchange_config)
        
        assert config.enabled is True
        assert config.http_proxy == "http://global-test.com:8080"


@pytest.mark.integration
@pytest.mark.skipif(not HAS_PROXY_MODULES, reason="代理模块不可用")
class TestProxyManagerIntegration:
    """代理管理器集成测试"""
    
    def test_proxy_manager_real_world_scenario(self):
        """测试真实世界场景"""
        manager = ProxyConfigManager()
        
        # 模拟真实的交易所配置
        binance_config = {
            "name": "binance",
            "api_key": "test_key",
            "proxy": {
                "enabled": True,
                "http_proxy": "http://binance-proxy.com:8080",
                "https_proxy": "https://binance-proxy.com:8443"
            }
        }
        
        okx_config = {
            "name": "okx",
            "api_key": "test_key"
            # 没有代理配置
        }
        
        # 获取Binance代理配置
        binance_proxy = manager.get_proxy_config(binance_config)
        assert binance_proxy.enabled is True
        assert binance_proxy.has_proxy() is True
        
        # 获取OKX代理配置（应该使用环境变量或默认）
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://default-proxy.com:8080'}):
            okx_proxy = manager.get_proxy_config(okx_config)
            assert okx_proxy.enabled is True
            assert okx_proxy.http_proxy == "http://default-proxy.com:8080"
            
        # 转换为不同格式
        binance_requests_proxy = manager.get_proxy_dict_for_requests(binance_proxy)
        assert 'http' in binance_requests_proxy
        assert 'https' in binance_requests_proxy
        
        binance_aiohttp_proxy = binance_proxy.to_aiohttp_proxy()
        assert binance_aiohttp_proxy is not None
        
    def test_proxy_manager_cache_performance(self):
        """测试代理管理器缓存性能"""
        manager = ProxyConfigManager()
        
        exchange_config = {
            "proxy": {
                "enabled": True,
                "http_proxy": "http://performance-test.com:8080"
            }
        }
        
        # 多次调用应该使用缓存
        configs = []
        for _ in range(10):
            config = manager.get_proxy_config(exchange_config)
            configs.append(config)
            
        # 所有配置应该是同一个对象（缓存生效）
        for config in configs[1:]:
            assert config is configs[0]
            
        # 缓存中应该只有一个条目
        assert len(manager._cache) == 1
