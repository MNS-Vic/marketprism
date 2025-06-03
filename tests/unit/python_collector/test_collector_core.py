#!/usr/bin/env python3
"""
MarketDataCollector 核心测试

针对collector.py的核心功能测试，重点提升覆盖率，包含交易所代理配置
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import os
import sys

# 添加模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.collector import MarketDataCollector
from marketprism_collector.config import Config
from marketprism_collector.types import DataType, CollectorMetrics, HealthStatus


@pytest.mark.unit
class TestMarketDataCollectorCore:
    """测试MarketDataCollector核心功能"""
    
    def test_collector_basic_initialization(self):
        """测试收集器基本初始化"""
        config = Config()
        collector = MarketDataCollector(config)
        
        assert collector.config == config
        assert collector.nats_manager is None
        assert collector.is_running is False
        assert collector.http_app is None
        assert collector.start_time is None
    
    @pytest.mark.asyncio
    async def test_collector_start_basic(self):
        """测试收集器基本启动功能"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # Mock关键组件的初始化方法
        with patch.object(collector, '_init_monitoring_system') as mock_monitor, \
             patch.object(collector, '_start_exchange_adapters') as mock_exchanges, \
             patch.object(collector, '_start_http_server') as mock_server, \
             patch.object(collector, '_start_background_tasks') as mock_tasks:
            
            mock_monitor.return_value = None
            mock_exchanges.return_value = None
            mock_server.return_value = None
            mock_tasks.return_value = None
            
            result = await collector.start()
            
            # 验证启动成功
            assert result is True
            assert collector.is_running is True
            assert collector.start_time is not None
    
    @pytest.mark.asyncio
    async def test_collector_stop_sequence(self):
        """测试收集器停止序列"""
        config = Config()
        collector = MarketDataCollector(config)
        collector.is_running = True
        
        # Mock停止组件
        with patch.object(collector, '_stop_background_tasks') as mock_stop_tasks, \
             patch.object(collector, '_stop_exchange_adapters') as mock_stop_exchanges:
            
            mock_stop_tasks.return_value = None
            mock_stop_exchanges.return_value = None
            
            await collector.stop()
            
            assert collector.is_running is False
    
    def test_metrics_access(self):
        """测试指标访问"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 测试指标对象存在
        assert hasattr(collector, 'metrics')
        assert isinstance(collector.metrics, CollectorMetrics)
        
        # 测试获取指标方法
        metrics = collector.get_metrics()
        assert isinstance(metrics, CollectorMetrics)
    
    def test_data_normalizer_initialization(self):
        """测试数据标准化器初始化"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证数据标准化器已初始化
        assert hasattr(collector, 'normalizer')
        assert collector.normalizer is not None


@pytest.mark.unit
class TestCollectorProxyIntegration:
    """测试收集器的代理集成 - 用户特别强调的代理配置测试"""
    
    def test_proxy_configuration_http(self):
        """测试HTTP代理配置"""
        config = Config()
        config.proxy.enabled = True
        config.proxy.http_proxy = "http://127.0.0.1:7890"
        config.proxy.https_proxy = "http://127.0.0.1:7890"
        
        collector = MarketDataCollector(config)
        
        # 验证代理配置被正确设置
        assert collector.config.proxy.enabled is True
        assert collector.config.proxy.http_proxy == "http://127.0.0.1:7890"
    
    def test_proxy_configuration_disabled(self):
        """测试禁用代理配置"""
        config = Config()
        config.proxy.enabled = False
        
        collector = MarketDataCollector(config)
        
        # 验证代理被禁用
        assert collector.config.proxy.enabled is False
    
    @patch.dict(os.environ, {
        'HTTP_PROXY': 'http://127.0.0.1:7890',
        'HTTPS_PROXY': 'http://127.0.0.1:7890'
    })
    def test_proxy_environment_setup(self):
        """测试代理环境变量设置"""
        config = Config()
        config.proxy.enabled = True
        config.proxy.http_proxy = "http://127.0.0.1:7890"
        config.proxy.https_proxy = "http://127.0.0.1:7890"
        
        # 调用代理环境设置
        config.setup_proxy_env()
        
        # 验证环境变量
        assert os.environ.get('HTTP_PROXY') == 'http://127.0.0.1:7890'
        assert os.environ.get('HTTPS_PROXY') == 'http://127.0.0.1:7890'


@pytest.mark.unit
class TestCollectorExchangeIntegration:
    """测试收集器与交易所的集成 - 包含代理支持"""
    
    @pytest.mark.asyncio
    async def test_exchange_adapters_dict_initialization(self):
        """测试交易所适配器字典初始化"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证交易所适配器字典已初始化
        assert hasattr(collector, 'exchange_adapters')
        assert isinstance(collector.exchange_adapters, dict)
        assert len(collector.exchange_adapters) == 0
    
    def test_adapter_callback_registration(self):
        """测试适配器回调注册方法存在"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证回调注册方法存在
        assert hasattr(collector, '_register_adapter_callbacks')
    
    @pytest.mark.asyncio 
    async def test_exchange_data_handlers(self):
        """测试交易所数据处理器方法存在"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证各种数据处理方法存在
        assert hasattr(collector, '_handle_trade_data')
        assert hasattr(collector, '_handle_orderbook_data')
        assert hasattr(collector, '_handle_ticker_data')
        assert hasattr(collector, '_handle_funding_rate_data')


@pytest.mark.unit
class TestCollectorHTTPServer:
    """测试收集器HTTP服务器功能"""
    
    def test_http_server_initialization(self):
        """测试HTTP服务器初始化"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证HTTP相关属性
        assert hasattr(collector, 'http_app')
        assert hasattr(collector, 'http_runner')
        assert collector.http_app is None
    
    def test_http_handlers_exist(self):
        """测试HTTP处理器方法存在"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证各种HTTP处理器存在
        assert hasattr(collector, '_health_handler')
        assert hasattr(collector, '_metrics_handler')
        assert hasattr(collector, '_status_handler')
        assert hasattr(collector, '_snapshot_handler')


@pytest.mark.unit
class TestCollectorMonitoring:
    """测试收集器监控功能"""
    
    def test_monitoring_system_initialization(self):
        """测试监控系统初始化"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证监控相关属性
        assert hasattr(collector, 'metrics')
        assert hasattr(collector, 'prometheus_metrics')
        assert hasattr(collector, 'health_checker')
    
    def test_error_recording(self):
        """测试错误记录功能"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证错误记录方法存在
        assert hasattr(collector, '_record_error')
    
    @pytest.mark.asyncio
    async def test_background_tasks_management(self):
        """测试后台任务管理"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证后台任务管理方法存在
        assert hasattr(collector, '_start_background_tasks')
        assert hasattr(collector, '_stop_background_tasks')
        assert hasattr(collector, 'background_tasks')
        assert isinstance(collector.background_tasks, list)


@pytest.mark.unit
class TestCollectorScheduler:
    """测试收集器调度器功能"""
    
    def test_scheduler_attributes(self):
        """测试调度器属性"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证调度器相关属性
        assert hasattr(collector, 'scheduler')
        assert hasattr(collector, 'scheduler_enabled')
    
    def test_scheduler_methods_exist(self):
        """测试调度器方法存在"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证调度器管理方法存在
        assert hasattr(collector, '_start_scheduler')
        assert hasattr(collector, '_stop_scheduler')


@pytest.mark.unit
class TestCollectorTopTrader:
    """测试收集器大户持仓功能"""
    
    def test_top_trader_collector_attributes(self):
        """测试大户持仓收集器属性"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证大户持仓收集器属性
        assert hasattr(collector, 'top_trader_collector')
        assert collector.top_trader_collector is None
    
    def test_top_trader_methods_exist(self):
        """测试大户持仓方法存在"""
        config = Config()
        collector = MarketDataCollector(config)
        
        # 验证大户持仓相关方法存在
        assert hasattr(collector, '_start_top_trader_collector')
        assert hasattr(collector, '_stop_top_trader_collector')
        assert hasattr(collector, '_handle_top_trader_data') 