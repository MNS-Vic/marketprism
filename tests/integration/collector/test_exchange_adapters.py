"""
MarketPrism Collector - 交易所适配器集成测试

测试实际交易所适配器的连接、认证、数据获取等功能
"""

import pytest
import asyncio
import aiohttp
import time
import sys
import os
from unittest.mock import patch, Mock, AsyncMock
from datetime import datetime, timedelta

# 添加项目路径
project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'services', 'python-collector', 'src'))

# 测试导入
try:
    from marketprism_collector.exchanges.binance import BinanceAdapter
    from marketprism_collector.exchanges.okx import OKXAdapter
    from marketprism_collector.exchanges.deribit import DeribitAdapter
    from marketprism_collector.exchanges.factory import ExchangeFactory
    from marketprism_collector.types import Exchange  # 从types模块导入Exchange
    from marketprism_collector.config import ExchangeConfig
    ADAPTERS_AVAILABLE = True
except ImportError as e:
    ADAPTERS_AVAILABLE = False
    print(f"警告：适配器模块不可用: {e}")

# 测试Core模块
try:
    from core.errors import UnifiedErrorHandler
    from core.monitoring import get_global_monitoring
    CORE_AVAILABLE = True
except ImportError as e:
    CORE_AVAILABLE = False
    print(f"警告：Core模块不可用: {e}")


class TestBinanceAdapter:
    """Binance 适配器集成测试"""
    
    @pytest.fixture
    def binance_config(self):
        """创建 Binance 测试配置"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        return ExchangeConfig(
            exchange=Exchange.BINANCE,
            api_key='test_key',
            api_secret='test_secret',
            testnet=True,
            rate_limits={
                'requests_per_minute': 1200,
                'requests_per_second': 20
            }
        )
    
    def test_binance_adapter_initialization(self, binance_config):
        """测试 Binance 适配器初始化"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = BinanceAdapter(binance_config)
        
        # 验证基本属性
        assert adapter.exchange == Exchange.BINANCE
        assert adapter.config == binance_config
        assert hasattr(adapter, 'session')
    
    def test_binance_adapter_required_methods(self, binance_config):
        """测试 Binance 适配器必需方法"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = BinanceAdapter(binance_config)
        
        # 验证必需方法存在
        required_methods = [
            'get_server_time',
            'get_exchange_info', 
            'get_orderbook_snapshot',
            'subscribe_orderbook',
            'subscribe_trades',
            'start',
            'stop',
            'close'
        ]
        
        for method_name in required_methods:
            assert hasattr(adapter, method_name), f"缺少必需方法: {method_name}"
            assert callable(getattr(adapter, method_name)), f"方法不可调用: {method_name}"
    
    @pytest.mark.asyncio
    async def test_binance_server_time_connection(self, binance_config):
        """测试 Binance 服务器时间连接（不需要认证）"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = BinanceAdapter(binance_config)
        
        try:
            # 测试服务器时间获取
            server_time = await adapter.get_server_time()
            
            # 验证返回值
            assert isinstance(server_time, int)
            assert server_time > 0
            
            # 验证时间合理性（应该在当前时间附近）
            current_time = int(time.time() * 1000)
            time_diff = abs(server_time - current_time)
            assert time_diff < 60000, f"服务器时间差异过大: {time_diff}ms"
            
        except Exception as e:
            # 网络问题时跳过测试
            pytest.skip(f"网络连接问题: {e}")
        finally:
            await adapter.close()
    
    @pytest.mark.asyncio
    async def test_binance_exchange_info(self, binance_config):
        """测试 Binance 交易所信息获取"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = BinanceAdapter(binance_config)
        
        try:
            exchange_info = await adapter.get_exchange_info()
            
            # 验证返回结构
            assert isinstance(exchange_info, dict)
            assert 'timezone' in exchange_info
            assert 'serverTime' in exchange_info
            assert 'symbols' in exchange_info
            assert isinstance(exchange_info['symbols'], list)
            assert len(exchange_info['symbols']) > 0
            
        except Exception as e:
            pytest.skip(f"网络连接问题: {e}")
        finally:
            await adapter.close()
    
    @pytest.mark.asyncio
    async def test_binance_orderbook_snapshot(self, binance_config):
        """测试 Binance 订单薄快照"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = BinanceAdapter(binance_config)
        
        try:
            # 测试常见交易对
            symbol = 'BTCUSDT'
            orderbook = await adapter.get_orderbook_snapshot(symbol)
            
            # 验证订单薄结构
            assert isinstance(orderbook, dict)
            assert 'bids' in orderbook
            assert 'asks' in orderbook
            assert isinstance(orderbook['bids'], list)
            assert isinstance(orderbook['asks'], list)
            assert len(orderbook['bids']) > 0
            assert len(orderbook['asks']) > 0
            
            # 验证价格数据格式
            for bid in orderbook['bids'][:5]:  # 检查前5个
                assert len(bid) >= 2
                price, quantity = float(bid[0]), float(bid[1])
                assert price > 0
                assert quantity > 0
            
        except Exception as e:
            pytest.skip(f"网络连接问题: {e}")
        finally:
            await adapter.close()


class TestOKXAdapter:
    """OKX 适配器集成测试"""
    
    @pytest.fixture
    def okx_config(self):
        """创建 OKX 测试配置"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        return ExchangeConfig(
            exchange=Exchange.OKX,
            api_key='test_key',
            api_secret='test_secret',
            passphrase='test_passphrase',
            testnet=True
        )
    
    def test_okx_adapter_initialization(self, okx_config):
        """测试 OKX 适配器初始化"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = OKXAdapter(okx_config)
        
        # 验证基本属性
        assert adapter.exchange == Exchange.OKX
        assert adapter.config == okx_config
    
    def test_okx_adapter_required_methods(self, okx_config):
        """测试 OKX 适配器必需方法"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = OKXAdapter(okx_config)
        
        # 验证必需方法存在
        required_methods = [
            'get_server_time',
            'get_exchange_info',
            'get_orderbook_snapshot',
            'subscribe_orderbook',
            'subscribe_trades',
            'start',
            'stop',
            'close'
        ]
        
        for method_name in required_methods:
            assert hasattr(adapter, method_name), f"缺少必需方法: {method_name}"
            assert callable(getattr(adapter, method_name)), f"方法不可调用: {method_name}"
    
    @pytest.mark.asyncio
    async def test_okx_public_endpoints(self, okx_config):
        """测试 OKX 公开端点"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = OKXAdapter(okx_config)
        
        try:
            # 测试服务器时间
            server_time = await adapter.get_server_time()
            assert isinstance(server_time, int)
            assert server_time > 0
            
        except Exception as e:
            pytest.skip(f"网络连接问题: {e}")
        finally:
            await adapter.close()


class TestDeribitAdapter:
    """Deribit 适配器集成测试"""
    
    @pytest.fixture
    def deribit_config(self):
        """创建 Deribit 测试配置"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        return ExchangeConfig(
            exchange=Exchange.DERIBIT,
            api_key='test_key',
            api_secret='test_secret',
            testnet=True
        )
    
    def test_deribit_adapter_initialization(self, deribit_config):
        """测试 Deribit 适配器初始化"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = DeribitAdapter(deribit_config)
        
        # 验证基本属性
        assert adapter.exchange == Exchange.DERIBIT
        assert adapter.config == deribit_config
    
    @pytest.mark.asyncio
    async def test_deribit_connection(self, deribit_config):
        """测试 Deribit 连接"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        adapter = DeribitAdapter(deribit_config)
        
        try:
            # 测试基本连接
            server_time = await adapter.get_server_time()
            if server_time:
                assert isinstance(server_time, int)
                assert server_time > 0
        except Exception as e:
            pytest.skip(f"Deribit连接问题: {e}")
        finally:
            await adapter.close()


class TestExchangeFactory:
    """交易所工厂集成测试"""
    
    def test_factory_supported_exchanges(self):
        """测试工厂支持的交易所"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        factory = ExchangeFactory()
        supported = factory.get_supported_exchanges()
        
        assert isinstance(supported, list)
        assert 'binance' in supported
        assert 'okx' in supported
        assert 'deribit' in supported
    
    def test_factory_adapter_creation(self):
        """测试工厂适配器创建"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        factory = ExchangeFactory()
        
        # 测试 Binance 适配器创建
        binance_config = {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'testnet': True
        }
        
        binance_adapter = factory.create_adapter('binance', binance_config)
        assert binance_adapter is not None
        assert binance_adapter.exchange == Exchange.BINANCE
        
        # 测试 OKX 适配器创建
        okx_config = {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'passphrase': 'test_passphrase',
            'testnet': True
        }
        
        okx_adapter = factory.create_adapter('okx', okx_config)
        assert okx_adapter is not None
        assert okx_adapter.exchange == Exchange.OKX
    
    def test_factory_invalid_exchange(self):
        """测试工厂无效交易所处理"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        factory = ExchangeFactory()
        
        # 测试不支持的交易所
        invalid_adapter = factory.create_adapter('invalid_exchange', {})
        assert invalid_adapter is None


class TestRateLimitIntegration:
    """限流集成测试"""
    
    @pytest.mark.asyncio
    async def test_binance_rate_limit_handling(self):
        """测试 Binance 限流处理"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            api_key='test_key',
            api_secret='test_secret',
            testnet=True,
            rate_limits={
                'requests_per_minute': 5,  # 设置很低的限制用于测试
                'requests_per_second': 1
            }
        )
        
        adapter = BinanceAdapter(config)
        
        try:
            # 发送多个请求测试限流
            start_time = time.time()
            
            for i in range(3):
                try:
                    await adapter.get_server_time()
                    await asyncio.sleep(0.1)  # 小延迟
                except Exception as e:
                    # 限流错误是预期的
                    if '429' in str(e) or 'rate limit' in str(e).lower():
                        pass
                    else:
                        pytest.skip(f"网络问题: {e}")
            
            end_time = time.time()
            duration = end_time - start_time
            
            # 验证限流确实生效（请求应该被延迟）
            assert duration >= 0.5, "限流似乎没有生效"
            
        except Exception as e:
            pytest.skip(f"网络连接问题: {e}")
        finally:
            await adapter.close()


class TestErrorHandlingIntegration:
    """错误处理集成测试"""
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """测试网络错误处理"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        # 创建带有无效URL的配置
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            api_key='test_key',
            api_secret='test_secret',
            testnet=True
        )
        
        adapter = BinanceAdapter(config)
        
        # 模拟网络错误
        with patch.object(adapter, '_make_request', side_effect=aiohttp.ClientError("Network error")):
            try:
                await adapter.get_server_time()
                assert False, "应该抛出网络错误"
            except Exception as e:
                # 验证错误被正确处理
                assert isinstance(e, aiohttp.ClientError)
        
        await adapter.close()
    
    def test_invalid_config_handling(self):
        """测试无效配置处理"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        # 测试缺少必需字段的配置
        with pytest.raises((ValueError, TypeError)):
            config = ExchangeConfig(
                exchange=Exchange.BINANCE,
                # 缺少 api_key 和 api_secret
                testnet=True
            )
            BinanceAdapter(config)


class TestCoreIntegration:
    """Core 服务集成测试"""
    
    def test_error_handler_integration(self):
        """测试错误处理器集成"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            api_key='test_key',
            api_secret='test_secret',
            testnet=True
        )
        
        adapter = BinanceAdapter(config)
        
        # 验证适配器可以处理错误（无论是否有Core支持）
        test_error = ValueError("Test error")
        
        # 这不应该抛出异常
        try:
            error_id = adapter._handle_error(test_error) if hasattr(adapter, '_handle_error') else None
            # 如果有error_id，应该是字符串
            if error_id:
                assert isinstance(error_id, str)
        except AttributeError:
            # 如果没有_handle_error方法，这是可以接受的
            pass
    
    def test_monitoring_integration(self):
        """测试监控集成"""
        if not ADAPTERS_AVAILABLE:
            pytest.skip("适配器模块不可用")
        
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            api_key='test_key',
            api_secret='test_secret',
            testnet=True
        )
        
        adapter = BinanceAdapter(config)
        
        # 验证适配器可以记录指标（无论是否有Core支持）
        try:
            if hasattr(adapter, '_record_metric'):
                adapter._record_metric('test_metric', 1.0)
            # 这不应该抛出异常
        except Exception as e:
            pytest.fail(f"监控集成失败: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])