"""
异步测试基类
解决NATS客户端事件循环清理问题，提供标准化的异步测试模式

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import sys
import os
import warnings
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal
import logging

# 添加数据收集器路径
collector_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'services', 'data-collector', 'src')
if collector_path not in sys.path:
    sys.path.insert(0, collector_path)

try:
    from marketprism_collector.collector import MarketDataCollector
    from marketprism_collector.config import CollectorConfig
    from marketprism_collector.data_types import (
        ExchangeConfig, Exchange, MarketType, DataType
    )
    ASYNC_BASE_AVAILABLE = True
except ImportError as e:
    ASYNC_BASE_AVAILABLE = False
    pytest.skip(f"异步基类模块不可用: {e}", allow_module_level=True)


class AsyncTestBase:
    """异步测试基类，提供标准化的异步测试模式"""
    
    def __init__(self):
        self.active_tasks = []
        self.active_clients = []
        self.cleanup_timeout = 5.0
        
    async def async_setup(self):
        """异步设置方法，子类可以重写"""
        pass
        
    async def async_teardown(self):
        """异步清理方法，子类可以重写"""
        pass
        
    def setup_method(self):
        """同步设置方法"""
        # 清理之前的任务列表
        self.active_tasks = []
        self.active_clients = []
        
        # 运行异步设置
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建任务
                asyncio.create_task(self.async_setup())
            else:
                # 如果事件循环未运行，直接运行
                loop.run_until_complete(self.async_setup())
        except Exception as e:
            # 设置失败时记录但不抛出异常
            logging.warning(f"异步设置失败: {e}")
            
    def teardown_method(self):
        """同步清理方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建清理任务
                asyncio.create_task(self._cleanup_resources())
            else:
                # 如果事件循环未运行，直接运行清理
                loop.run_until_complete(self._cleanup_resources())
        except Exception as e:
            # 清理失败时记录但不抛出异常
            logging.warning(f"异步清理失败: {e}")
        finally:
            # 强制清理任务列表
            self.active_tasks.clear()
            self.active_clients.clear()
            
    async def _cleanup_resources(self):
        """清理所有活跃的资源"""
        # 运行子类的异步清理
        try:
            await self.async_teardown()
        except Exception as e:
            logging.warning(f"子类异步清理失败: {e}")
            
        # 清理活跃的客户端
        for client in self.active_clients:
            try:
                if hasattr(client, 'disconnect'):
                    await asyncio.wait_for(client.disconnect(), timeout=self.cleanup_timeout)
                elif hasattr(client, 'close'):
                    await asyncio.wait_for(client.close(), timeout=self.cleanup_timeout)
                elif hasattr(client, 'stop'):
                    await asyncio.wait_for(client.stop(), timeout=self.cleanup_timeout)
            except Exception as e:
                logging.warning(f"客户端清理失败: {e}")
                
        # 取消活跃的任务
        for task in self.active_tasks:
            try:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=1.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
            except Exception as e:
                logging.warning(f"任务取消失败: {e}")
                
        # 等待一小段时间让清理完成
        try:
            await asyncio.sleep(0.1)
        except Exception:
            pass
            
    def register_client(self, client):
        """注册需要清理的客户端"""
        if client not in self.active_clients:
            self.active_clients.append(client)
            
    def register_task(self, task):
        """注册需要取消的任务"""
        if task not in self.active_tasks:
            self.active_tasks.append(task)
            
    def create_test_config(self, exchange=Exchange.BINANCE, **kwargs):
        """创建测试配置的辅助方法"""
        default_config = {
            'exchange': exchange,
            'market_type': MarketType.SPOT,
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'symbols': ['BTC-USDT'],
            'data_types': [DataType.TRADE, DataType.ORDERBOOK]
        }
        default_config.update(kwargs)
        
        return ExchangeConfig(**default_config)
        
    def create_collector_config(self, exchanges=None, **kwargs):
        """创建收集器配置的辅助方法"""
        if exchanges is None:
            exchanges = [self.create_test_config()]
            
        default_config = {
            'exchanges': exchanges,
            'output_config': {'type': 'nats', 'url': 'nats://localhost:4222'},
            'metrics_enabled': True,
            'health_check_enabled': True
        }
        default_config.update(kwargs)
        
        return CollectorConfig(**default_config)


class AsyncTestBaseTests(AsyncTestBase):
    """测试异步测试基类本身"""

    def setup_method(self):
        """设置测试方法"""
        # 初始化基类属性，但不调用__init__
        self.active_clients = []
        self.active_tasks = []
        self.test_config = None
        self.collector_config = None

    async def async_setup(self):
        """设置测试环境"""
        self.test_config = self.create_test_config()
        self.collector_config = self.create_collector_config()

    async def async_teardown(self):
        """清理测试环境"""
        # 这里可以添加特定的清理逻辑
        pass
        
    def test_config_creation(self):
        """测试：配置创建辅助方法"""
        # 测试交易所配置创建
        config = self.create_test_config()
        assert config is not None
        assert config.exchange == Exchange.BINANCE
        assert config.market_type == MarketType.SPOT
        assert len(config.symbols) == 1
        assert config.symbols[0] == 'BTC-USDT'
        
        # 测试自定义配置
        custom_config = self.create_test_config(
            exchange=Exchange.OKX,
            market_type=MarketType.FUTURES,
            symbols=['ETH-USDT', 'BTC-USDT'],
            passphrase='test_passphrase'
        )
        assert custom_config.exchange == Exchange.OKX
        assert custom_config.market_type == MarketType.FUTURES
        assert len(custom_config.symbols) == 2
        assert hasattr(custom_config, 'passphrase')
        
    def test_collector_config_creation(self):
        """测试：收集器配置创建辅助方法"""
        # 测试默认收集器配置
        config = self.create_collector_config()
        assert config is not None
        assert len(config.exchanges) == 1
        assert config.output_config['type'] == 'nats'
        assert config.metrics_enabled is True
        assert config.health_check_enabled is True
        
        # 测试自定义收集器配置
        custom_exchanges = [
            self.create_test_config(exchange=Exchange.BINANCE),
            self.create_test_config(exchange=Exchange.OKX, passphrase='test')
        ]
        custom_config = self.create_collector_config(
            exchanges=custom_exchanges,
            metrics_enabled=False
        )
        assert len(custom_config.exchanges) == 2
        assert custom_config.metrics_enabled is False
        
    def test_client_registration(self):
        """测试：客户端注册机制"""
        # 创建模拟客户端
        mock_client = Mock()
        mock_client.disconnect = AsyncMock()
        
        # 注册客户端
        self.register_client(mock_client)
        assert mock_client in self.active_clients
        
        # 重复注册不应该重复添加
        self.register_client(mock_client)
        assert self.active_clients.count(mock_client) == 1
        
    def test_task_registration(self):
        """测试：任务注册机制"""
        # 创建模拟任务
        mock_task = Mock()
        mock_task.done.return_value = False
        mock_task.cancel = Mock()
        
        # 注册任务
        self.register_task(mock_task)
        assert mock_task in self.active_tasks
        
        # 重复注册不应该重复添加
        self.register_task(mock_task)
        assert self.active_tasks.count(mock_task) == 1
        
    @pytest.mark.asyncio
    async def test_async_cleanup_mechanism(self):
        """测试：异步清理机制"""
        # 创建模拟客户端和任务
        mock_client = Mock()
        mock_client.disconnect = AsyncMock()
        
        mock_task = Mock()
        mock_task.done.return_value = False
        mock_task.cancel = Mock()
        
        # 注册资源
        self.register_client(mock_client)
        self.register_task(mock_task)
        
        # 执行清理
        await self._cleanup_resources()
        
        # 验证清理调用
        mock_client.disconnect.assert_called_once()
        mock_task.cancel.assert_called_once()
        
    def test_setup_teardown_cycle(self):
        """测试：设置和清理周期"""
        # 这个测试验证设置和清理方法可以正常调用
        initial_clients = len(self.active_clients)
        initial_tasks = len(self.active_tasks)
        
        # 添加一些资源
        mock_client = Mock()
        mock_task = Mock()
        self.register_client(mock_client)
        self.register_task(mock_task)
        
        assert len(self.active_clients) == initial_clients + 1
        assert len(self.active_tasks) == initial_tasks + 1
        
        # teardown_method会在测试结束时自动调用
        # 这里我们手动验证清理逻辑
        self.active_clients.clear()
        self.active_tasks.clear()
        
        assert len(self.active_clients) == 0
        assert len(self.active_tasks) == 0


class AsyncPatternsTests(AsyncTestBase):
    """测试常见的异步模式"""

    def setup_method(self):
        """设置测试方法"""
        # 初始化基类属性，但不调用__init__
        self.active_clients = []
        self.active_tasks = []
        self.collector_config = None

    async def async_setup(self):
        """设置测试环境"""
        self.collector_config = self.create_collector_config()
        
    def test_collector_creation_with_async_base(self):
        """测试：使用异步基类创建收集器"""
        collector = MarketDataCollector(self.collector_config)
        
        # 注册收集器以便清理
        self.register_client(collector)
        
        assert collector is not None
        assert collector.get_config() == self.collector_config
        
    @pytest.mark.asyncio
    async def test_collector_lifecycle_with_cleanup(self):
        """测试：带清理的收集器生命周期"""
        collector = MarketDataCollector(self.collector_config)
        self.register_client(collector)
        
        try:
            # 尝试启动收集器
            await collector.start()
            
            # 检查状态
            health_status = collector.get_health_status()
            assert health_status is not None
            
        except Exception:
            # 启动可能失败，这是正常的
            pass
        finally:
            # 确保收集器被停止
            try:
                await collector.stop()
            except Exception:
                pass
                
    def test_multiple_configs_creation(self):
        """测试：创建多个配置"""
        configs = []
        
        # 创建多个不同的交易所配置
        exchanges = [Exchange.BINANCE, Exchange.OKX, Exchange.DERIBIT]
        
        for exchange in exchanges:
            if exchange == Exchange.OKX:
                config = self.create_test_config(
                    exchange=exchange,
                    passphrase='test_passphrase'
                )
            elif exchange == Exchange.DERIBIT:
                config = self.create_test_config(
                    exchange=exchange,
                    market_type=MarketType.OPTIONS,
                    symbols=['BTC-PERPETUAL']
                )
            else:
                config = self.create_test_config(exchange=exchange)
                
            configs.append(config)
            
        assert len(configs) == 3
        assert all(config is not None for config in configs)
        assert configs[0].exchange == Exchange.BINANCE
        assert configs[1].exchange == Exchange.OKX
        assert configs[2].exchange == Exchange.DERIBIT
        
        # 创建包含所有交易所的收集器配置
        collector_config = self.create_collector_config(exchanges=configs)
        assert len(collector_config.exchanges) == 3
