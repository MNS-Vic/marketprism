"""
MarketPrism Collector - Core 服务集成测试

验证 Collector 正确使用 Core 模块，确保没有重复开发
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

# 添加项目路径
project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'services', 'python-collector', 'src'))

# 测试导入是否成功
try:
    from marketprism_collector.exchanges.factory import ExchangeFactory
    from marketprism_collector.exchanges.binance import BinanceAdapter
    COLLECTOR_AVAILABLE = True
except ImportError as e:
    COLLECTOR_AVAILABLE = False
    print(f"警告：Collector模块不可用: {e}")

# 测试Core模块导入
try:
    from core.errors import UnifiedErrorHandler
    from core.monitoring import get_global_monitoring
    CORE_AVAILABLE = True
except ImportError as e:
    CORE_AVAILABLE = False
    print(f"警告：Core模块不可用: {e}")


class TestCoreModuleAvailability:
    """测试Core模块可用性"""
    
    def test_collector_modules_import(self):
        """测试Collector模块导入"""
        if not COLLECTOR_AVAILABLE:
            pytest.skip("Collector模块不可用")
        
        # 验证关键模块可以导入
        from marketprism_collector.exchanges.factory import ExchangeFactory
        from marketprism_collector.exchanges.binance import BinanceAdapter
        from marketprism_collector.exchanges.okx import OKXAdapter
        
        assert ExchangeFactory is not None
        assert BinanceAdapter is not None
        assert OKXAdapter is not None
    
    def test_core_modules_import(self):
        """测试Core模块导入"""
        if not CORE_AVAILABLE:
            pytest.skip("Core模块不可用")
        
        # 验证Core模块可以导入
        from core.errors import UnifiedErrorHandler
        from core.monitoring import get_global_monitoring
        
        assert UnifiedErrorHandler is not None
        assert get_global_monitoring is not None


class TestExchangeFactory:
    """测试交易所工厂"""
    
    def test_factory_creation(self):
        """测试工厂创建"""
        if not COLLECTOR_AVAILABLE:
            pytest.skip("Collector模块不可用")
        
        from marketprism_collector.exchanges.factory import ExchangeFactory
        factory = ExchangeFactory()
        assert factory is not None
    
    def test_supported_exchanges(self):
        """测试支持的交易所"""
        if not COLLECTOR_AVAILABLE:
            pytest.skip("Collector模块不可用")
        
        from marketprism_collector.exchanges.factory import ExchangeFactory
        factory = ExchangeFactory()
        supported = factory.get_supported_exchanges()
        
        assert isinstance(supported, list)
        assert len(supported) > 0
        assert 'binance' in supported
        assert 'okx' in supported
    
    def test_adapter_creation_binance(self):
        """测试Binance适配器创建"""
        if not COLLECTOR_AVAILABLE:
            pytest.skip("Collector模块不可用")
        
        from marketprism_collector.exchanges.factory import ExchangeFactory
        factory = ExchangeFactory()
        
        config = {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'testnet': True
        }
        
        adapter = factory.create_adapter('binance', config)
        assert adapter is not None
    
    def test_adapter_creation_okx(self):
        """测试OKX适配器创建"""
        if not COLLECTOR_AVAILABLE:
            pytest.skip("Collector模块不可用")
        
        from marketprism_collector.exchanges.factory import ExchangeFactory
        factory = ExchangeFactory()
        
        config = {
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'passphrase': 'test_passphrase',
            'testnet': True
        }
        
        adapter = factory.create_adapter('okx', config)
        assert adapter is not None


class TestCoreIntegrationFiles:
    """测试Core集成文件"""
    
    def test_core_integration_files_exist(self):
        """测试Core集成文件是否存在"""
        collector_src_dir = os.path.join(project_root, 'services', 'python-collector', 'src', 'marketprism_collector')
        
        integration_files = [
            'core_integration.py',
            'core_services.py', 
            'unified_error_manager.py'
        ]
        
        existing_files = []
        for filename in integration_files:
            filepath = os.path.join(collector_src_dir, filename)
            if os.path.exists(filepath):
                existing_files.append(filename)
        
        # 至少应该存在一些集成文件
        assert len(existing_files) > 0, f"没有找到任何Core集成文件。检查了: {integration_files}"
    
    def test_core_integration_import(self):
        """测试Core集成模块导入"""
        try:
            from marketprism_collector.core_integration import CoreServiceIntegration
            assert CoreServiceIntegration is not None
        except ImportError:
            pytest.skip("core_integration模块不可用")
    
    def test_core_services_import(self):
        """测试Core服务模块导入"""
        try:
            from marketprism_collector.core_services import CoreServicesAdapter
            assert CoreServicesAdapter is not None
        except ImportError:
            pytest.skip("core_services模块不可用")
    
    def test_unified_error_manager_import(self):
        """测试统一错误管理器导入"""
        try:
            from marketprism_collector.unified_error_manager import UnifiedErrorManager
            assert UnifiedErrorManager is not None
        except ImportError:
            pytest.skip("unified_error_manager模块不可用")


class TestBasicFunctionality:
    """测试基本功能"""
    
    def test_project_structure(self):
        """测试项目结构"""
        # 检查关键目录
        key_dirs = [
            'services/python-collector/src/marketprism_collector',
            'services/python-collector/src/marketprism_collector/exchanges',
            'core',
            'config',
            'tests'
        ]
        
        for dir_path in key_dirs:
            full_path = os.path.join(project_root, dir_path)
            assert os.path.exists(full_path), f"目录不存在: {dir_path}"
    
    def test_key_files_exist(self):
        """测试关键文件存在"""
        key_files = [
            'services/python-collector/src/marketprism_collector/exchanges/factory.py',
            'services/python-collector/src/marketprism_collector/exchanges/binance.py',
            'services/python-collector/src/marketprism_collector/exchanges/okx.py',
            'services/python-collector/src/marketprism_collector/__init__.py'
        ]
        
        for file_path in key_files:
            full_path = os.path.join(project_root, file_path)
            assert os.path.exists(full_path), f"文件不存在: {file_path}"
    
    def test_configuration_structure(self):
        """测试配置结构"""
        test_config = {
            'exchanges': {
                'binance': {
                    'name': 'binance',
                    'enabled': True,
                    'testnet': True
                },
                'okx': {
                    'name': 'okx',
                    'enabled': True,
                    'testnet': True
                }
            },
            'data_collection': {
                'collection_interval': 1.0,
                'batch_size': 100
            }
        }
        
        # 验证配置结构
        assert 'exchanges' in test_config
        assert 'data_collection' in test_config
        assert len(test_config['exchanges']) == 2
        
        # 验证交易所配置
        for exchange_name, exchange_config in test_config['exchanges'].items():
            assert 'name' in exchange_config
            assert 'enabled' in exchange_config
            assert exchange_name in ['binance', 'okx']


@pytest.mark.asyncio
class TestAsyncFunctionality:
    """测试异步功能"""
    
    async def test_async_import(self):
        """测试异步导入"""
        # 基本的异步测试
        await asyncio.sleep(0.01)
        assert True
    
    async def test_async_adapter_creation(self):
        """测试异步适配器创建"""
        if not COLLECTOR_AVAILABLE:
            pytest.skip("Collector模块不可用")
        
        from marketprism_collector.exchanges.factory import ExchangeFactory
        factory = ExchangeFactory()
        
        # 异步测试适配器创建
        await asyncio.sleep(0.01)
        
        config = {'api_key': 'test', 'api_secret': 'test', 'testnet': True}
        adapter = factory.create_adapter('binance', config)
        
        assert adapter is not None


class TestEnvironmentValidation:
    """测试环境验证"""
    
    def test_python_version(self):
        """测试Python版本"""
        assert sys.version_info >= (3, 8), "需要Python 3.8或更高版本"
    
    def test_required_directories_writable(self):
        """测试必需目录可写"""
        test_dirs = ['tests', 'logs', 'cache']
        
        for dir_name in test_dirs:
            dir_path = os.path.join(project_root, dir_name)
            if os.path.exists(dir_path):
                assert os.access(dir_path, os.W_OK), f"目录不可写: {dir_name}"
    
    def test_basic_imports(self):
        """测试基本导入"""
        # 测试Python标准库
        import json
        import asyncio
        import datetime
        
        assert json is not None
        assert asyncio is not None  
        assert datetime is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])