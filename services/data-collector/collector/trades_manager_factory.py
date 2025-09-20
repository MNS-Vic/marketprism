"""
TradesManager工厂 - 创建不同交易所的成交数据管理器
借鉴OrderBook Manager的成功架构模式
"""

from typing import Optional, List

# 🔧 迁移到统一日志系统
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    ComponentType
)

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
        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(ComponentType.TRADES_MANAGER, exchange="factory")
    
    def create_trades_manager(self,
                            exchange: Exchange,
                            market_type: MarketType,
                            symbols: List[str],
                            normalizer: DataNormalizer,
                            nats_publisher: NATSPublisher,
                            config: dict) -> Optional[BaseTradesManager]:
        """
        创建成交数据管理器

        Args:
            exchange: 交易所
            market_type: 市场类型
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置字典

        Returns:
            成交数据管理器实例
        """
        try:
            manager_key = f"{exchange.value}_{market_type.value}"

            # 🔧 迁移到统一日志系统 - 标准化启动日志
            self.logger.startup(
                "Creating trades data manager",
                manager_key=manager_key,
                exchange=exchange.value,
                market_type=market_type.value
            )

            # 根据交易所和市场类型创建对应的管理器
            if exchange == Exchange.BINANCE_SPOT and market_type == MarketType.SPOT:
                self.logger.info("🔧 开始创建BinanceSpotTradesManager", symbols=symbols)
                try:
                    manager = BinanceSpotTradesManager(symbols, normalizer, nats_publisher, config)
                    self.logger.info("✅ BinanceSpotTradesManager创建成功")
                    return manager
                except Exception as e:
                    self.logger.error("❌ BinanceSpotTradesManager创建失败", error=str(e), exc_info=True)
                    raise

            elif exchange == Exchange.BINANCE_DERIVATIVES and market_type == MarketType.PERPETUAL:
                # 修正拼写：PERPETUAL
                return BinanceDerivativesTradesManager(symbols, normalizer, nats_publisher, config)

            elif exchange == Exchange.OKX_SPOT and market_type == MarketType.SPOT:
                return OKXSpotTradesManager(symbols, normalizer, nats_publisher, config)

            elif exchange == Exchange.OKX_DERIVATIVES and market_type == MarketType.PERPETUAL:
                # 修正拼写：PERPETUAL
                return OKXDerivativesTradesManager(symbols, normalizer, nats_publisher, config)

            else:
                # 🔧 迁移到统一日志系统 - 标准化错误处理
                self.logger.error(
                    "Unsupported exchange and market type combination",
                    error=ValueError(f"Unsupported combination: {exchange.value} + {market_type.value}"),
                    exchange=exchange.value,
                    market_type=market_type.value
                )
                return None
                
        except Exception as e:
            # 🔧 迁移到统一日志系统 - 标准化错误处理
            self.logger.error(
                "Failed to create trades data manager",
                error=e,
                exchange=exchange.value,
                market_type=market_type.value,
                exc_info=True
            )
            return None


# 全局工厂实例
trades_manager_factory = TradesManagerFactory()
