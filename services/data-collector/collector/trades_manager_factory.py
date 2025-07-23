"""
TradesManager工厂 - 创建不同交易所的成交数据管理器
借鉴OrderBook Manager的成功架构模式
"""

import structlog
from typing import Optional, List

from collector.data_types import Exchange, MarketType
from collector.normalizer import DataNormalizer
from collector.nats_publisher import NATSPublisher
from collector.trades_managers import (
    BaseTradesManager,
    BinanceSpotTradesManager,
    BinanceDerivativesTradesManager,
    OKXSpotTradesManager,
    OKXDerivativesTradesManager
)


class TradesManagerFactory:
    """
    成交数据管理器工厂
    借鉴OrderBook Manager的成功架构模式
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
    
    def create_trades_manager(self,
                            exchange: Exchange,
                            market_type: MarketType,
                            symbols: List[str],
                            normalizer: DataNormalizer,
                            nats_publisher: NATSPublisher) -> Optional[BaseTradesManager]:
        """
        创建成交数据管理器
        
        Args:
            exchange: 交易所
            market_type: 市场类型
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            
        Returns:
            成交数据管理器实例
        """
        try:
            manager_key = f"{exchange.value}_{market_type.value}"
            
            self.logger.info(f"🏭 创建成交数据管理器: {manager_key}")
            
            # 根据交易所和市场类型创建对应的管理器
            if exchange == Exchange.BINANCE_SPOT and market_type == MarketType.SPOT:
                return BinanceSpotTradesManager(symbols, normalizer, nats_publisher)
                
            elif exchange == Exchange.BINANCE_DERIVATIVES and market_type == MarketType.PERPETUAL:
                return BinanceDerivativesTradesManager(symbols, normalizer, nats_publisher)
                
            elif exchange == Exchange.OKX_SPOT and market_type == MarketType.SPOT:
                return OKXSpotTradesManager(symbols, normalizer, nats_publisher)
                
            elif exchange == Exchange.OKX_DERIVATIVES and market_type == MarketType.PERPETUAL:
                return OKXDerivativesTradesManager(symbols, normalizer, nats_publisher)
                
            else:
                self.logger.error(f"❌ 不支持的交易所和市场类型组合: {exchange.value} + {market_type.value}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ 创建成交数据管理器失败: {e}")
            return None


# 全局工厂实例
trades_manager_factory = TradesManagerFactory()
