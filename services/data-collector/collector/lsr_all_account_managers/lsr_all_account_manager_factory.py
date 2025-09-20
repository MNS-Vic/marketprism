"""
全市场多空持仓人数比例数据管理器工厂（按账户数计算）

使用工厂模式创建不同交易所的全市场多空持仓人数比例管理器实例
"""

from typing import Dict, Any, List, Optional
import structlog

from collector.data_types import Exchange, MarketType
from collector.normalizer import DataNormalizer
from .base_lsr_all_account_manager import BaseLSRAllAccountManager
from .okx_derivatives_lsr_all_account_manager import OKXDerivativesLSRAllAccountManager
from .binance_derivatives_lsr_all_account_manager import BinanceDerivativesLSRAllAccountManager


class LSRAllAccountManagerFactory:
    """
    全市场多空持仓人数比例数据管理器工厂类（按账户数计算）

    负责根据配置创建相应的管理器实例
    专门处理全市场按账户数计算的多空比例数据
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        
        # 注册支持的管理器类型 - 按交易所组织
        self._manager_registry = {
            (Exchange.OKX_DERIVATIVES, MarketType.DERIVATIVES): OKXDerivativesLSRAllAccountManager,
            (Exchange.BINANCE_DERIVATIVES, MarketType.DERIVATIVES): BinanceDerivativesLSRAllAccountManager,
        }

    def create_manager(self,
                      exchange: Exchange,
                      market_type: MarketType,
                      symbols: List[str],
                      normalizer: DataNormalizer,
                      nats_publisher: Any,
                      config: Dict[str, Any]) -> Optional[BaseLSRAllAccountManager]:
        """
        创建全市场多空持仓人数比例数据管理器

        Args:
            exchange: 交易所枚举
            market_type: 市场类型枚举
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息

        Returns:
            管理器实例或None
        """
        try:
            # 查找对应的管理器类
            manager_key = (exchange, market_type)
            manager_class = self._manager_registry.get(manager_key)
            
            if not manager_class:
                self.logger.error(
                    "不支持的交易所和市场类型组合",
                    exchange=exchange.value,
                    market_type=market_type.value,
                    supported_combinations=[
                        f"{k[0].value}-{k[1].value}" for k in self._manager_registry.keys()
                    ]
                )
                return None
            
            # 验证配置
            if not self._validate_config(exchange, market_type, config):
                return None

            # 验证交易对格式
            validated_symbols = self._validate_symbols(exchange, market_type, symbols)
            if not validated_symbols:
                self.logger.error(
                    "没有有效的交易对",
                    exchange=exchange.value,
                    market_type=market_type.value,
                    symbols=symbols
                )
                return None
            
            # 创建管理器实例
            manager = manager_class(
                symbols=validated_symbols,
                normalizer=normalizer,
                nats_publisher=nats_publisher,
                config=config
            )
            
            self.logger.info(
                "全市场多空持仓人数比例数据管理器创建成功",
                manager_type=manager_class.__name__,
                data_type='lsr_all_account',
                exchange=exchange.value,
                market_type=market_type.value,
                symbols=validated_symbols
            )
            
            return manager
            
        except Exception as e:
            self.logger.error(
                "创建全市场多空持仓人数比例数据管理器失败",
                error=e,
                exchange=exchange.value,
                market_type=market_type.value
            )
            return None

    def _validate_config(self, exchange: Exchange, market_type: MarketType, config: Dict[str, Any]) -> bool:
        """
        验证配置信息

        Args:
            exchange: 交易所枚举
            market_type: 市场类型枚举
            config: 配置信息

        Returns:
            配置是否有效
        """
        try:
            # 检查必需的配置项
            required_fields = ['fetch_interval', 'period', 'limit']
            for field in required_fields:
                if field not in config:
                    self.logger.error(f"配置缺少必需字段: {field}")
                    return False
            
            # 验证数值范围
            if config['fetch_interval'] < 10:
                self.logger.error("fetch_interval不能小于10秒")
                return False
            
            if config['limit'] < 1 or config['limit'] > 500:
                self.logger.error("limit必须在1-500之间")
                return False
            
            # 验证周期格式
            valid_periods = ['5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
            if config['period'] not in valid_periods:
                self.logger.error(
                    f"不支持的数据周期: {config['period']}",
                    valid_periods=valid_periods
                )
                return False
            
            return True
            
        except Exception as e:
            self.logger.error("配置验证异常", error=e)
            return False

    def _validate_symbols(self, exchange: Exchange, market_type: MarketType, symbols: List[str]) -> List[str]:
        """
        验证和转换交易对格式
        
        Args:
            exchange: 交易所枚举
            market_type: 市场类型枚举
            symbols: 原始交易对列表
            
        Returns:
            验证后的交易对列表
        """
        try:
            validated_symbols = []
            
            for symbol in symbols:
                # 根据交易所转换格式
                if exchange == Exchange.OKX_DERIVATIVES:
                    # OKX格式: BTC-USDT-SWAP
                    if not symbol.endswith('-SWAP'):
                        if '-' in symbol:
                            symbol = f"{symbol}-SWAP"
                        else:
                            self.logger.warning(f"无效的OKX交易对格式: {symbol}")
                            continue
                    validated_symbols.append(symbol)
                    
                elif exchange == Exchange.BINANCE_DERIVATIVES:
                    # Binance格式: BTCUSDT
                    if '-' in symbol:
                        symbol = symbol.replace('-', '')
                    validated_symbols.append(symbol)
                    
                else:
                    self.logger.warning(f"不支持的交易所: {exchange.value}")
                    continue
            
            return validated_symbols
            
        except Exception as e:
            self.logger.error("交易对验证异常", error=e)
            return []

    def get_supported_exchanges(self) -> List[str]:
        """
        获取支持的交易所列表
        
        Returns:
            支持的交易所列表
        """
        exchanges = set()
        for exchange, _ in self._manager_registry.keys():
            exchanges.add(exchange.value)
        return list(exchanges)

    def get_supported_market_types(self, exchange: Exchange) -> List[str]:
        """
        获取指定交易所支持的市场类型列表
        
        Args:
            exchange: 交易所枚举
            
        Returns:
            支持的市场类型列表
        """
        market_types = []
        for (ex, mt) in self._manager_registry.keys():
            if ex == exchange:
                market_types.append(mt.value)
        return market_types

    def get_manager_info(self) -> Dict[str, Any]:
        """
        获取工厂信息
        
        Returns:
            工厂信息字典
        """
        return {
            'factory_type': 'LSRAllAccountManagerFactory',
            'data_type': 'lsr_all_account',
            'supported_combinations': [
                {
                    'exchange': k[0].value,
                    'market_type': k[1].value,
                    'manager_class': v.__name__
                }
                for k, v in self._manager_registry.items()
            ],
            'supported_exchanges': self.get_supported_exchanges()
        }
