"""
Exchanges Factory - 企业级交易所适配器工厂模式

基于TDD发现的设计问题，提供统一的适配器创建和管理机制
支持：配置管理、错误处理、实例缓存、扩展性设计
"""

from typing import Dict, Optional, Type, Any, List
import logging
from .base import ExchangeAdapter
from .binance import BinanceAdapter
from .okx import OKXAdapter 
from .deribit import DeribitAdapter
from ..types import ExchangeConfig, Exchange, MarketType, DataType


class ExchangeFactory:
    """
    交易所适配器工厂类 - TDD驱动的企业级设计
    
    功能特性：
    - 统一适配器创建接口
    - 配置验证和管理
    - 实例缓存和复用
    - 错误处理和日志记录
    - 支持插件式扩展
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._adapter_classes: Dict[str, Type[ExchangeAdapter]] = {
            'binance': BinanceAdapter,
            'okx': OKXAdapter,
            'deribit': DeribitAdapter
        }
        self._adapter_cache: Dict[str, ExchangeAdapter] = {}
        self._default_configs: Dict[str, Dict[str, Any]] = {
            'binance': {
                'base_url': 'https://api.binance.com',
                'ws_url': 'wss://stream.binance.com:9443',
                'timeout': 30,
                'retries': 3
            },
            'okx': {
                'base_url': 'https://www.okx.com',
                'ws_url': 'wss://ws.okx.com:8443',
                'timeout': 30,
                'retries': 3
            },
            'deribit': {
                'base_url': 'https://www.deribit.com',
                'ws_url': 'wss://www.deribit.com/ws/api/v2',
                'timeout': 30,
                'retries': 3
            }
        }
        
        self.logger.info("交易所工厂已初始化，支持的交易所: %s", list(self._adapter_classes.keys()))
    
    def create_adapter(self, exchange_name: str, config: Optional[Dict[str, Any]] = None, 
                      use_cache: bool = True) -> Optional[ExchangeAdapter]:
        """
        创建交易所适配器
        
        Args:
            exchange_name: 交易所名称
            config: 配置字典
            use_cache: 是否使用缓存
            
        Returns:
            交易所适配器实例
        """
        try:
            if exchange_name not in self._adapter_classes:
                self.logger.error("不支持的交易所: %s", exchange_name)
                return None
            
            # 生成缓存键
            cache_key = f"{exchange_name}_{hash(str(config))}"
            
            # 检查缓存
            if use_cache and cache_key in self._adapter_cache:
                self.logger.debug("从缓存获取适配器: %s", exchange_name)
                return self._adapter_cache[cache_key]
            
            # 获取适配器类
            adapter_class = self._adapter_classes[exchange_name]
            
            # 处理配置
            final_config = self._prepare_config(exchange_name, config)
            
            # 创建实例
            adapter = adapter_class(final_config)
            
            # 缓存实例
            if use_cache:
                self._adapter_cache[cache_key] = adapter
            
            self.logger.info("成功创建适配器: %s", exchange_name)
            return adapter
            
        except Exception as e:
            self.logger.error("创建 %s 适配器失败: %s", exchange_name, str(e))
            return None
    
    def create_adapter_from_config(self, exchange_name: str, 
                                  exchange_config: ExchangeConfig) -> Optional[ExchangeAdapter]:
        """
        从ExchangeConfig对象创建适配器
        
        Args:
            exchange_name: 交易所名称
            exchange_config: ExchangeConfig对象
            
        Returns:
            交易所适配器实例
        """
        try:
            if exchange_name not in self._adapter_classes:
                self.logger.error("不支持的交易所: %s", exchange_name)
                return None
            
            adapter_class = self._adapter_classes[exchange_name]
            adapter = adapter_class(exchange_config)
            
            self.logger.info("成功从ExchangeConfig创建适配器: %s", exchange_name)
            return adapter
            
        except Exception as e:
            self.logger.error("从ExchangeConfig创建 %s 适配器失败: %s", exchange_name, str(e))
            return None
    
    def create_exchange_config(self, exchange_name: str, 
                              config_dict: Dict[str, Any]) -> Optional[ExchangeConfig]:
        """
        将字典配置转换为ExchangeConfig对象
        
        Args:
            exchange_name: 交易所名称
            config_dict: 配置字典
            
        Returns:
            ExchangeConfig对象
        """
        try:
            # 获取默认配置
            default_config = self._default_configs.get(exchange_name, {})
            
            # 合并配置
            merged_config = {**default_config, **config_dict}
            
            # 设置必需字段的默认值
            if exchange_name == 'binance':
                return ExchangeConfig.for_binance(
                    market_type=MarketType.FUTURES,
                    api_key=merged_config.get('api_key'),
                    api_secret=merged_config.get('secret'),
                    symbols=merged_config.get('symbols', ['BTCUSDT']),
                    data_types=merged_config.get('data_types', [DataType.TRADE])
                )
            elif exchange_name == 'okx':
                return ExchangeConfig.for_okx(
                    market_type=MarketType.FUTURES,
                    api_key=merged_config.get('api_key'),
                    api_secret=merged_config.get('secret'),
                    passphrase=merged_config.get('passphrase'),
                    symbols=merged_config.get('symbols', ['BTC-USDT']),
                    data_types=merged_config.get('data_types', [DataType.TRADE])
                )
            else:
                # 通用配置创建
                return ExchangeConfig(
                    exchange=Exchange(exchange_name),
                    market_type=MarketType.FUTURES,
                    base_url=merged_config.get('base_url', f'https://api.{exchange_name}.com'),
                    ws_url=merged_config.get('ws_url', f'wss://ws.{exchange_name}.com'),
                    api_key=merged_config.get('api_key'),
                    api_secret=merged_config.get('secret'),
                    symbols=merged_config.get('symbols', ['BTC-USDT']),
                    data_types=merged_config.get('data_types', [DataType.TRADE])
                )
                
        except Exception as e:
            self.logger.error("创建ExchangeConfig失败 %s: %s", exchange_name, str(e))
            return None
    
    def _prepare_config(self, exchange_name: str, config: Optional[Dict[str, Any]]) -> ExchangeConfig:
        """
        准备适配器配置
        
        Args:
            exchange_name: 交易所名称
            config: 原始配置
            
        Returns:
            准备好的ExchangeConfig对象
        """
        # 如果已经是ExchangeConfig对象，直接返回
        if isinstance(config, ExchangeConfig):
            return config
        
        # 如果是字典，转换为ExchangeConfig
        if isinstance(config, dict):
            exchange_config = self.create_exchange_config(exchange_name, config)
            if exchange_config:
                return exchange_config
        
        # 创建默认配置
        return self._create_default_config(exchange_name)
    
    def _create_default_config(self, exchange_name: str) -> ExchangeConfig:
        """创建默认配置"""
        if exchange_name == 'binance':
            return ExchangeConfig.for_binance()
        elif exchange_name == 'okx':
            return ExchangeConfig.for_okx()
        else:
            # 通用默认配置
            return ExchangeConfig(
                exchange=Exchange(exchange_name),
                market_type=MarketType.FUTURES,
                base_url=f'https://api.{exchange_name}.com',
                ws_url=f'wss://ws.{exchange_name}.com',
                symbols=['BTC-USDT'],
                data_types=[DataType.TRADE]
            )
    
    def create_binance_adapter(self, config: Optional[Dict[str, Any]] = None) -> Optional[BinanceAdapter]:
        """便利方法：创建Binance适配器"""
        return self.create_adapter('binance', config)
    
    def create_okx_adapter(self, config: Optional[Dict[str, Any]] = None) -> Optional[OKXAdapter]:
        """便利方法：创建OKX适配器"""
        return self.create_adapter('okx', config)
    
    def create_deribit_adapter(self, config: Optional[Dict[str, Any]] = None) -> Optional[DeribitAdapter]:
        """便利方法：创建Deribit适配器"""
        return self.create_adapter('deribit', config)
    
    def register_adapter(self, exchange_name: str, adapter_class: Type[ExchangeAdapter]):
        """注册新的适配器类"""
        self._adapter_classes[exchange_name] = adapter_class
        self.logger.info("已注册新适配器: %s", exchange_name)
    
    def get_supported_exchanges(self) -> List[str]:
        """获取支持的交易所列表"""
        return list(self._adapter_classes.keys())
    
    def clear_cache(self):
        """清除适配器缓存"""
        self._adapter_cache.clear()
        self.logger.info("适配器缓存已清除")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            'cached_adapters': len(self._adapter_cache),
            'supported_exchanges': len(self._adapter_classes),
            'cache_keys': list(self._adapter_cache.keys())
        }


# 便利函数
def get_factory() -> ExchangeFactory:
    """获取全局工厂实例"""
    if not hasattr(get_factory, '_instance'):
        get_factory._instance = ExchangeFactory()
    return get_factory._instance


def create_adapter(exchange_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[ExchangeAdapter]:
    """便利函数：创建适配器"""
    factory = get_factory()
    return factory.create_adapter(exchange_name, config)


def get_supported_exchanges() -> List[str]:
    """便利函数：获取支持的交易所"""
    factory = get_factory()
    return factory.get_supported_exchanges()