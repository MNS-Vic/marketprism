"""
交易所适配器模块 - 企业级TDD驱动设计

提供各种交易所的数据收集适配器和企业级管理功能
基于TDD发现的设计问题，重构为完整的企业级架构
"""

from .base import ExchangeAdapter
from .binance import BinanceAdapter
from .okx import OKXAdapter
from .deribit import DeribitAdapter
from .factory import ExchangeFactory, get_factory, create_adapter, get_supported_exchanges
from .manager import ExchangeManager, ExchangeHealth
from .mock_adapter import MockExchangeAdapter, MockConfig
from ..types import ExchangeConfig, Exchange


class ExchangeAdapterFactory:
    """
    传统交易所适配器工厂（向后兼容）
    
    注意：推荐使用新的ExchangeFactory类获得更多企业级功能
    """
    
    _adapters = {
        Exchange.BINANCE: BinanceAdapter,
        Exchange.OKX: OKXAdapter,
        Exchange.DERIBIT: DeribitAdapter,
    }
    
    @classmethod
    def create_adapter(cls, config: ExchangeConfig) -> ExchangeAdapter:
        """创建交易所适配器实例"""
        adapter_class = cls._adapters.get(config.exchange)
        if not adapter_class:
            raise ValueError(f"不支持的交易所: {config.exchange}")
        
        # 转换为新格式配置
        config_dict = {
            'api_key': getattr(config, 'api_key', None),
            'secret': getattr(config, 'secret', None),
            'passphrase': getattr(config, 'passphrase', None),
            'sandbox': getattr(config, 'sandbox', False),
            'timeout': getattr(config, 'timeout', 30),
        }
        
        return adapter_class(config_dict)
    
    @classmethod
    def get_supported_exchanges(cls):
        """获取支持的交易所列表"""
        return list(cls._adapters.keys())


# 企业级便利函数
def create_exchange_manager(factory: ExchangeFactory = None) -> ExchangeManager:
    """创建交易所管理器"""
    return ExchangeManager(factory)

def create_mock_adapter(config: dict = None) -> MockExchangeAdapter:
    """创建模拟适配器（测试用）"""
    return MockExchangeAdapter(config)


__all__ = [
    # 核心适配器类
    'ExchangeAdapter',
    'BinanceAdapter', 
    'OKXAdapter',
    'DeribitAdapter',
    
    # 企业级管理组件
    'ExchangeFactory',
    'ExchangeManager',
    'ExchangeHealth',
    
    # 测试支持
    'MockExchangeAdapter',
    'MockConfig',
    
    # 向后兼容
    'ExchangeAdapterFactory',
    
    # 便利函数
    'get_factory',
    'create_adapter',
    'get_supported_exchanges',
    'create_exchange_manager',
    'create_mock_adapter',
]