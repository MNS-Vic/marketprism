#!/usr/bin/env python3
"""
交易所代理配置优化验证测试

验证基于TDD发现的问题所做的代理配置优化是否有效
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import os
import sys

# 添加模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.exchanges.binance import BinanceAdapter
from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType


@pytest.mark.unit
class TestProxyConfigOptimization:
    """测试代理配置优化"""
    
    def test_get_effective_proxy_config_prioritizes_config(self):
        """测试代理配置优先级：配置文件 > 环境变量"""
        # 创建带代理配置的ExchangeConfig
        config = ExchangeConfig.for_binance(
            proxy={
                'enabled': True,
                'http': 'http://config-proxy:8080',
                'https': 'https://config-proxy:8080'
            }
        )
        
        adapter = BinanceAdapter(config)
        
        # 模拟环境变量也有代理设置
        with patch.dict(os.environ, {
            'HTTP_PROXY': 'http://env-proxy:3128',
            'HTTPS_PROXY': 'https://env-proxy:3128'
        }):
            effective_config = adapter._get_effective_proxy_config()
            
            # 应该优先使用配置文件中的代理
            assert effective_config is not None
            assert effective_config['http'] == 'http://config-proxy:8080'
            assert effective_config['https'] == 'https://config-proxy:8080'
    
    def test_get_effective_proxy_config_fallback_to_env(self):
        """测试无配置文件代理时回退到环境变量"""
        # 创建无代理配置的ExchangeConfig
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        # 只有环境变量有代理设置
        with patch.dict(os.environ, {
            'HTTP_PROXY': 'http://env-proxy:3128',
            'HTTPS_PROXY': 'https://env-proxy:3128'
        }):
            effective_config = adapter._get_effective_proxy_config()
            
            # 应该使用环境变量的代理
            assert effective_config is not None
            assert effective_config['http'] == 'http://env-proxy:3128'
            assert effective_config['https'] == 'https://env-proxy:3128'
    
    def test_proxy_explicitly_disabled_in_config(self):
        """测试配置中明确禁用代理"""
        config = ExchangeConfig.for_binance(
            proxy={'enabled': False}
        )
        adapter = BinanceAdapter(config)
        
        # 即使环境变量有代理，也应该被禁用
        with patch.dict(os.environ, {
            'HTTP_PROXY': 'http://env-proxy:3128'
        }):
            effective_config = adapter._get_effective_proxy_config()
            
            # 应该返回None，表示代理被禁用
            assert effective_config is None
    
    def test_get_env_proxy_config_socks(self):
        """测试环境变量SOCKS代理配置解析"""
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        with patch.dict(os.environ, {
            'ALL_PROXY': 'socks5://127.0.0.1:1080'
        }):
            env_config = adapter._get_env_proxy_config()
            
            assert env_config is not None
            assert env_config['enabled'] is True
            assert env_config['socks5'] == 'socks5://127.0.0.1:1080'
    
    def test_get_env_proxy_config_http(self):
        """测试环境变量HTTP代理配置解析"""
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        with patch.dict(os.environ, {
            'HTTP_PROXY': 'http://proxy.example.com:8080',
            'HTTPS_PROXY': 'https://proxy.example.com:8080'
        }):
            env_config = adapter._get_env_proxy_config()
            
            assert env_config is not None
            assert env_config['enabled'] is True
            assert env_config['http'] == 'http://proxy.example.com:8080'
            assert env_config['https'] == 'https://proxy.example.com:8080'
    
    def test_no_proxy_configuration(self):
        """测试无任何代理配置的情况"""
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        with patch.dict(os.environ, {}, clear=True):
            effective_config = adapter._get_effective_proxy_config()
            env_config = adapter._get_env_proxy_config()
            
            assert effective_config is None
            assert env_config is None


@pytest.mark.unit
class TestProxyConnectionMethods:
    """测试代理连接方法"""
    
    @pytest.mark.asyncio
    async def test_connect_with_proxy_socks(self):
        """测试SOCKS代理连接选择"""
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        # Mock _connect_socks_proxy 方法
        adapter._connect_socks_proxy = AsyncMock(return_value=True)
        
        proxy_config = {
            'enabled': True,
            'socks5': 'socks5://127.0.0.1:1080'
        }
        
        result = await adapter._connect_with_proxy(proxy_config)
        
        assert result is True
        adapter._connect_socks_proxy.assert_called_once_with('socks5://127.0.0.1:1080')
    
    @pytest.mark.asyncio
    async def test_connect_with_proxy_http(self):
        """测试HTTP代理连接选择"""
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        # Mock _connect_http_proxy 方法
        adapter._connect_http_proxy = AsyncMock(return_value=True)
        
        proxy_config = {
            'enabled': True,
            'http': 'http://proxy.example.com:8080',
            'https': 'https://proxy.example.com:8080'
        }
        
        result = await adapter._connect_with_proxy(proxy_config)
        
        assert result is True
        adapter._connect_http_proxy.assert_called_once_with('https://proxy.example.com:8080')
    
    @pytest.mark.asyncio
    async def test_connect_with_proxy_unknown_fallback(self):
        """测试未知代理类型回退到直连"""
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        # Mock _connect_direct 方法
        adapter._connect_direct = AsyncMock(return_value=True)
        
        proxy_config = {
            'enabled': True,
            'unknown_proxy_type': 'some://unknown:1234'
        }
        
        result = await adapter._connect_with_proxy(proxy_config)
        
        assert result is True
        adapter._connect_direct.assert_called_once()


@pytest.mark.unit
class TestBackwardCompatibility:
    """测试向后兼容性"""
    
    def test_old_env_vars_still_work(self):
        """测试旧的环境变量代理设置仍然工作"""
        config = ExchangeConfig.for_binance()  # 无代理配置
        adapter = BinanceAdapter(config)
        
        # 使用旧式环境变量
        with patch.dict(os.environ, {
            'http_proxy': 'http://old-proxy:3128',  # 小写
            'HTTPS_PROXY': 'https://old-proxy:3128'  # 大写
        }):
            effective_config = adapter._get_effective_proxy_config()
            
            assert effective_config is not None
            assert effective_config['http'] == 'http://old-proxy:3128'
            assert effective_config['https'] == 'https://old-proxy:3128'
    
    def test_all_proxy_precedence(self):
        """测试ALL_PROXY环境变量优先级"""
        config = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config)
        
        with patch.dict(os.environ, {
            'ALL_PROXY': 'http://all-proxy:8080',
            'HTTP_PROXY': 'http://http-proxy:3128',
            'HTTPS_PROXY': 'https://https-proxy:3128'
        }):
            env_config = adapter._get_env_proxy_config()
            
            # ALL_PROXY应该优先
            assert env_config['http'] == 'http://all-proxy:8080'


@pytest.mark.unit 
class TestProxyOptimizationIntegration:
    """测试代理优化的集成效果"""
    
    def test_complete_proxy_precedence_chain(self):
        """测试完整的代理优先级链"""
        # 1. 配置文件代理 > 环境变量
        config_with_proxy = ExchangeConfig.for_binance(
            proxy={'enabled': True, 'http': 'http://config:8080'}
        )
        adapter = BinanceAdapter(config_with_proxy)
        
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://env:3128'}):
            assert adapter._get_effective_proxy_config()['http'] == 'http://config:8080'
        
        # 2. 配置禁用 > 环境变量存在
        config_disabled = ExchangeConfig.for_binance(
            proxy={'enabled': False}
        )
        adapter = BinanceAdapter(config_disabled)
        
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://env:3128'}):
            assert adapter._get_effective_proxy_config() is None
        
        # 3. 无配置 > 环境变量
        config_no_proxy = ExchangeConfig.for_binance()
        adapter = BinanceAdapter(config_no_proxy)
        
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://env:3128'}):
            assert adapter._get_effective_proxy_config()['http'] == 'http://env:3128'
        
        # 4. 无配置 > 无环境变量
        with patch.dict(os.environ, {}, clear=True):
            assert adapter._get_effective_proxy_config() is None 