"""
订单簿管理器工厂类

根据交易所和市场类型创建对应的专用管理器
"""

from typing import List, Optional
from structlog import get_logger

from .base_orderbook_manager import BaseOrderBookManager
from .okx_spot_manager import OKXSpotOrderBookManager
from .okx_derivatives_manager import OKXDerivativesOrderBookManager
from .binance_spot_manager import BinanceSpotOrderBookManager
from .binance_derivatives_manager import BinanceDerivativesOrderBookManager
# from .okx_derivative_manager import OKXDerivativeOrderBookManager
# from .binance_spot_manager import BinanceSpotOrderBookManager  
# from .binance_derivative_manager import BinanceDerivativeOrderBookManager


class OrderBookManagerFactory:
    """订单簿管理器工厂"""
    
    def __init__(self):
        self.logger = get_logger("orderbook_manager_factory")
    
    def create_manager(self, exchange: str, market_type: str, symbols: List[str], 
                      normalizer, nats_publisher, config: dict) -> Optional[BaseOrderBookManager]:
        """
        创建对应的订单簿管理器
        
        Args:
            exchange: 交易所名称 (如 'binance_spot', 'okx_derivatives')
            market_type: 市场类型 ('spot'/'perpetual')
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
            
        Returns:
            对应的订单簿管理器实例
        """
        try:
            manager_key = f"{exchange}_{market_type}"
            
            self.logger.info(f"🏭 创建订单簿管理器: {manager_key}")
            
            # 根据交易所和市场类型创建对应的管理器
            if exchange == "okx" and market_type == "spot":
                return OKXSpotOrderBookManager(symbols, normalizer, nats_publisher, config)
            
            elif exchange == "okx_spot" and market_type == "spot":
                return OKXSpotOrderBookManager(symbols, normalizer, nats_publisher, config)

            elif exchange == "okx" and market_type == "perpetual":
                return OKXDerivativesOrderBookManager(symbols, normalizer, nats_publisher, config)

            elif exchange == "okx_derivatives" and market_type == "perpetual":
                return OKXDerivativesOrderBookManager(symbols, normalizer, nats_publisher, config)
            
            elif exchange == "binance" and market_type == "spot":
                return BinanceSpotOrderBookManager(symbols, normalizer, nats_publisher, config)

            elif exchange == "binance_spot" and market_type == "spot":
                return BinanceSpotOrderBookManager(symbols, normalizer, nats_publisher, config)

            elif exchange == "binance" and market_type == "perpetual":
                return BinanceDerivativesOrderBookManager(symbols, normalizer, nats_publisher, config)

            elif exchange == "binance_derivatives" and market_type == "perpetual":
                return BinanceDerivativesOrderBookManager(symbols, normalizer, nats_publisher, config)
            
            else:
                self.logger.error(f"❌ 不支持的交易所和市场类型组合: {exchange}_{market_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ 创建订单簿管理器失败: {exchange}_{market_type}, error={e}")
            return None
    
    def get_supported_combinations(self) -> List[tuple]:
        """获取支持的交易所和市场类型组合"""
        return [
            ("okx", "spot"),
            ("okx_spot", "spot"),
            ("okx", "perpetual"),
            ("okx_derivatives", "perpetual"),
            ("binance", "spot"),
            ("binance_spot", "spot"),
            ("binance", "perpetual"),
            ("binance_derivatives", "perpetual"),
        ]
    
    def is_supported(self, exchange: str, market_type: str) -> bool:
        """检查是否支持指定的交易所和市场类型组合"""
        return (exchange, market_type) in self.get_supported_combinations()


# 全局工厂实例
orderbook_manager_factory = OrderBookManagerFactory()
