#!/usr/bin/env python3
"""
交易所配置改进验证测试

验证基于TDD发现的设计问题所做的改进是否解决了实际问题
"""
import pytest
import os
import sys

# 添加模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType


@pytest.mark.unit
class TestExchangeConfigImprovements:
    """测试ExchangeConfig的改进"""
    
    def test_proxy_field_added(self):
        """测试代理字段已经添加"""
        config = ExchangeConfig.for_binance(
            proxy={
                'enabled': True,
                'http': 'http://127.0.0.1:7890',
                'https': 'https://127.0.0.1:7890'
            }
        )
        
        # 验证代理字段存在且工作正常
        assert hasattr(config, 'proxy')
        assert config.proxy is not None
        assert config.proxy['enabled'] is True
        assert config.proxy['http'] == 'http://127.0.0.1:7890'
    
    def test_convenience_method_binance(self):
        """测试Binance便利构造方法"""
        # 最简配置
        config1 = ExchangeConfig.for_binance()
        assert config1.exchange == Exchange.BINANCE
        assert config1.market_type == MarketType.SPOT
        assert len(config1.symbols) == 2  # 默认BTC和ETH
        
        # 带代理配置
        config2 = ExchangeConfig.for_binance(
            api_key="test_key",
            api_secret="test_secret",
            proxy={'enabled': True, 'http': 'http://127.0.0.1:7890'}
        )
        assert config2.api_key == "test_key"
        assert config2.proxy['enabled'] is True
    
    def test_convenience_method_okx(self):
        """测试OKX便利构造方法"""
        # 最简配置
        config1 = ExchangeConfig.for_okx()
        assert config1.exchange == Exchange.OKX
        assert config1.market_type == MarketType.SPOT
        assert len(config1.symbols) == 2  # 默认BTC和ETH
        
        # 带完整配置
        config2 = ExchangeConfig.for_okx(
            api_key="test_key",
            api_secret="test_secret", 
            passphrase="test_passphrase",
            proxy={'enabled': True, 'socks5': 'socks5://127.0.0.1:1080'}
        )
        assert config2.api_key == "test_key"
        assert config2.passphrase == "test_passphrase"
        assert config2.proxy['enabled'] is True
        assert config2.proxy['socks5'] == 'socks5://127.0.0.1:1080'
    
    def test_proxy_disabled_case(self):
        """测试代理禁用情况"""
        config = ExchangeConfig.for_binance(
            proxy={'enabled': False}
        )
        
        assert config.proxy is not None
        assert config.proxy['enabled'] is False
    
    def test_no_proxy_case(self):
        """测试无代理配置情况"""
        config = ExchangeConfig.for_binance()
        
        # 无代理配置时，proxy字段应该为None
        assert config.proxy is None
    
    def test_custom_symbols_and_data_types(self):
        """测试自定义交易对和数据类型"""
        config = ExchangeConfig.for_binance(
            symbols=['BTCUSDT', 'ETHUSDT', 'ADAUSDT'],
            data_types=[DataType.TRADE, DataType.ORDERBOOK, DataType.TICKER]
        )
        
        assert len(config.symbols) == 3
        assert 'ADAUSDT' in config.symbols
        assert len(config.data_types) == 3
        assert DataType.TICKER in config.data_types


@pytest.mark.unit
class TestConfigUsabilityImprovements:
    """测试配置易用性改进"""
    
    def test_reduced_boilerplate_code(self):
        """测试减少的样板代码"""
        # 之前需要手动指定所有字段
        # 现在只需要指定必要的字段
        config = ExchangeConfig.for_binance(
            api_key="my_key",
            proxy={'enabled': True, 'http': 'http://127.0.0.1:7890'}
        )
        
        # 验证默认值自动填充
        assert config.base_url == "https://api.binance.com"
        assert config.ws_url == "wss://stream.binance.com:9443"
        assert config.enabled is True
        assert len(config.symbols) > 0
        assert len(config.data_types) > 0
    
    def test_different_market_types(self):
        """测试不同市场类型支持"""
        spot_config = ExchangeConfig.for_binance(market_type=MarketType.SPOT)
        futures_config = ExchangeConfig.for_binance(market_type=MarketType.FUTURES)
        
        assert spot_config.market_type == MarketType.SPOT
        assert futures_config.market_type == MarketType.FUTURES
        # 其他配置应该相同
        assert spot_config.exchange == futures_config.exchange


@pytest.mark.unit
class TestBackwardCompatibility:
    """测试向后兼容性"""
    
    def test_direct_construction_still_works(self):
        """测试直接构造方式仍然有效"""
        # 确保原有的直接构造方式仍然工作
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            market_type=MarketType.SPOT,
            base_url="https://api.binance.com",
            ws_url="wss://stream.binance.com:9443",
            data_types=[DataType.TRADE],
            symbols=["BTCUSDT"],
            proxy={'enabled': True, 'http': 'http://127.0.0.1:7890'}
        )
        
        assert config.exchange == Exchange.BINANCE
        assert config.proxy['enabled'] is True 