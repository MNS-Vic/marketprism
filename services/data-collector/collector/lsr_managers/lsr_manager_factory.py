"""
顶级交易者多空持仓比例数据管理器工厂

使用工厂模式创建不同交易所和数据类型的管理器实例
支持按持仓量(lsr_position)和按账户数(lsr_account)两种计算方式
"""

from typing import Dict, Any, List, Optional
import structlog

from collector.data_types import Exchange, MarketType
from collector.normalizer import DataNormalizer
from .base_lsr_manager import BaseLSRManager
from .okx_derivatives_lsr_top_position_manager import OKXDerivativesLSRTopPositionManager
from .binance_derivatives_lsr_top_position_manager import BinanceDerivativesLSRTopPositionManager
from .okx_derivatives_lsr_all_account_manager import OKXDerivativesLSRAllAccountManager
from .binance_derivatives_lsr_all_account_manager import BinanceDerivativesLSRAllAccountManager


class LSRManagerFactory:
    """
    多空持仓比例数据管理器工厂类（按持仓量计算）

    负责根据配置创建相应的管理器实例
    支持按持仓量(lsr_position)和按账户数(lsr_account)两种计算方式
    """
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        
        # 注册支持的管理器类型 - 按数据类型和交易所组织
        self._manager_registry = {
            # lsr_top_position 类型（顶级大户按持仓量计算）
            ('lsr_top_position', Exchange.OKX_DERIVATIVES, MarketType.DERIVATIVES): OKXDerivativesLSRTopPositionManager,
            ('lsr_top_position', Exchange.BINANCE_DERIVATIVES, MarketType.DERIVATIVES): BinanceDerivativesLSRTopPositionManager,

            # lsr_all_account 类型（全市场按账户数计算）
            ('lsr_all_account', Exchange.OKX_DERIVATIVES, MarketType.DERIVATIVES): OKXDerivativesLSRAllAccountManager,
            ('lsr_all_account', Exchange.BINANCE_DERIVATIVES, MarketType.DERIVATIVES): BinanceDerivativesLSRAllAccountManager,
        }

    def create_manager(self,
                      data_type: str,  # 'lsr_top_position' 或 'lsr_all_account'
                      exchange: Exchange,
                      market_type: MarketType,
                      symbols: List[str],
                      normalizer: DataNormalizer,
                      nats_publisher: Any,
                      config: Dict[str, Any]) -> Optional[BaseLSRManager]:
        """
        创建多空持仓比例数据管理器

        Args:
            data_type: 数据类型 ('lsr_top_position' 或 'lsr_all_account')
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
            manager_key = (data_type, exchange, market_type)
            manager_class = self._manager_registry.get(manager_key)
            
            if not manager_class:
                self.logger.error(
                    "不支持的数据类型、交易所和市场类型组合",
                    data_type=data_type,
                    exchange=exchange.value,
                    market_type=market_type.value,
                    supported_combinations=[
                        f"{k[0]}-{k[1].value}-{k[2].value}" for k in self._manager_registry.keys()
                    ]
                )
                return None
            
            # 验证配置
            if not self._validate_config(data_type, exchange, market_type, config):
                return None

            # 验证交易对格式
            validated_symbols = self._validate_symbols(exchange, market_type, symbols)
            if not validated_symbols:
                self.logger.error(
                    "没有有效的交易对",
                    data_type=data_type,
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
                "顶级交易者多空持仓比例数据管理器创建成功",
                manager_type=manager_class.__name__,
                data_type=data_type,
                exchange=exchange.value,
                market_type=market_type.value,
                symbols=validated_symbols
            )
            
            return manager
            
        except Exception as e:
            self.logger.error(
                "创建顶级交易者多空持仓比例数据管理器失败",
                error=e,
                exchange=exchange.value,
                market_type=market_type.value
            )
            return None

    def _validate_config(self, data_type: str, exchange: Exchange, market_type: MarketType, config: Dict[str, Any]) -> bool:
        """
        验证配置信息

        Args:
            data_type: 数据类型
            exchange: 交易所枚举
            market_type: 市场类型枚举
            config: 配置信息

        Returns:
            配置是否有效
        """
        try:
            # 验证数据类型
            valid_data_types = ['lsr_top_position', 'lsr_all_account']
            if data_type not in valid_data_types:
                self.logger.error(f"不支持的数据类型: {data_type}", valid_types=valid_data_types)
                return False

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
            'factory_type': 'LSRManagerFactory',
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
