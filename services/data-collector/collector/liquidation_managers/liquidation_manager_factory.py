"""
LiquidationManagerFactory - 强平订单数据管理器工厂类

基于现有orderbook_managers和trades_managers的工厂模式，
根据交易所和市场类型创建对应的强平数据管理器。
"""

from typing import List, Optional, Dict, Any

# 🔧 统一日志系统集成
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    ComponentType
)

from .base_liquidation_manager import BaseLiquidationManager
from .okx_derivatives_liquidation_manager import OKXDerivativesLiquidationManager
from .binance_derivatives_liquidation_manager import BinanceDerivativesLiquidationManager


class LiquidationManagerFactory:
    """强平订单数据管理器工厂类"""
    
    def __init__(self):
        """初始化工厂"""
        self.logger = get_managed_logger(
            ComponentType.FACTORY
        )
        
        # 支持的交易所和市场类型组合
        self.supported_combinations = {
            ("okx_derivatives", "perpetual"): OKXDerivativesLiquidationManager,
            ("binance_derivatives", "perpetual"): BinanceDerivativesLiquidationManager,
            # 为了兼容性，也支持简化的名称
            ("okx", "perpetual"): OKXDerivativesLiquidationManager,
            ("binance", "perpetual"): BinanceDerivativesLiquidationManager,
        }
        
        self.logger.startup(
            "强平管理器工厂初始化完成",
            supported_combinations=list(self.supported_combinations.keys())
        )
    
    def create_manager(self, 
                      exchange: str, 
                      market_type: str, 
                      symbols: List[str], 
                      normalizer, 
                      nats_publisher, 
                      config: dict) -> Optional[BaseLiquidationManager]:
        """
        创建对应的强平数据管理器
        
        Args:
            exchange: 交易所名称 (如 'okx_derivatives', 'binance_derivatives')
            market_type: 市场类型 ('perpetual')
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
            
        Returns:
            对应的强平数据管理器实例，如果不支持则返回None
        """
        try:
            manager_key = (exchange, market_type)
            
            self.logger.info(
                "创建强平数据管理器",
                exchange=exchange,
                market_type=market_type,
                symbols=symbols,
                manager_key=manager_key
            )
            
            # 查找对应的管理器类
            manager_class = self.supported_combinations.get(manager_key)
            
            if manager_class is None:
                self.logger.error(
                    "不支持的交易所和市场类型组合",
                    exchange=exchange,
                    market_type=market_type,
                    supported_combinations=list(self.supported_combinations.keys())
                )
                return None
            
            # 创建管理器实例
            manager = manager_class(
                symbols=symbols,
                normalizer=normalizer,
                nats_publisher=nats_publisher,
                config=config
            )
            
            self.logger.startup(
                "强平数据管理器创建成功",
                exchange=exchange,
                market_type=market_type,
                manager_class=manager_class.__name__,
                symbols_count=len(symbols)
            )
            
            return manager
            
        except Exception as e:
            self.logger.error(
                "创建强平数据管理器失败",
                error=e,
                exchange=exchange,
                market_type=market_type,
                symbols=symbols
            )
            return None
    
    def get_supported_combinations(self) -> List[tuple]:
        """获取支持的交易所和市场类型组合"""
        return list(self.supported_combinations.keys())
    
    def is_supported(self, exchange: str, market_type: str) -> bool:
        """
        检查是否支持指定的交易所和市场类型组合
        
        Args:
            exchange: 交易所名称
            market_type: 市场类型
            
        Returns:
            bool: 是否支持
        """
        return (exchange, market_type) in self.supported_combinations
    
    def get_supported_exchanges(self) -> List[str]:
        """获取支持的交易所列表"""
        exchanges = set()
        for exchange, _ in self.supported_combinations.keys():
            exchanges.add(exchange)
        return list(exchanges)
    
    def get_supported_market_types(self, exchange: str = None) -> List[str]:
        """
        获取支持的市场类型列表
        
        Args:
            exchange: 可选，指定交易所名称
            
        Returns:
            List[str]: 市场类型列表
        """
        market_types = set()
        
        for ex, mt in self.supported_combinations.keys():
            if exchange is None or ex == exchange:
                market_types.add(mt)
                
        return list(market_types)
    
    def validate_configuration(self, exchange: str, market_type: str, config: dict) -> Dict[str, Any]:
        """
        验证配置信息
        
        Args:
            exchange: 交易所名称
            market_type: 市场类型
            config: 配置信息
            
        Returns:
            Dict[str, Any]: 验证结果，包含is_valid和errors字段
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            # 检查是否支持该组合
            if not self.is_supported(exchange, market_type):
                result['is_valid'] = False
                result['errors'].append(
                    f"不支持的交易所和市场类型组合: {exchange}_{market_type}"
                )
                return result
            
            # 检查必要的配置项
            required_configs = ['ws_url']
            for key in required_configs:
                if key not in config:
                    result['errors'].append(f"缺少必要配置项: {key}")
            
            # 检查可选但推荐的配置项
            recommended_configs = ['heartbeat_interval', 'connection_timeout', 'max_reconnect_attempts']
            for key in recommended_configs:
                if key not in config:
                    result['warnings'].append(f"建议添加配置项: {key}")
            
            # 如果有错误，标记为无效
            if result['errors']:
                result['is_valid'] = False
            
            self.logger.info(
                "配置验证完成",
                exchange=exchange,
                market_type=market_type,
                is_valid=result['is_valid'],
                errors_count=len(result['errors']),
                warnings_count=len(result['warnings'])
            )
            
        except Exception as e:
            result['is_valid'] = False
            result['errors'].append(f"配置验证异常: {str(e)}")
            
            self.logger.error(
                "配置验证失败",
                error=e,
                exchange=exchange,
                market_type=market_type
            )
        
        return result
    
    def get_factory_stats(self) -> Dict[str, Any]:
        """获取工厂统计信息"""
        return {
            'supported_combinations_count': len(self.supported_combinations),
            'supported_combinations': list(self.supported_combinations.keys()),
            'supported_exchanges': self.get_supported_exchanges(),
            'supported_market_types': self.get_supported_market_types(),
            'factory_type': 'liquidation_manager'
        }


# 全局工厂实例
liquidation_manager_factory = LiquidationManagerFactory()


def create_liquidation_manager(exchange: str, 
                             market_type: str, 
                             symbols: List[str], 
                             normalizer, 
                             nats_publisher, 
                             config: dict) -> Optional[BaseLiquidationManager]:
    """
    便捷函数：创建强平数据管理器
    
    Args:
        exchange: 交易所名称
        market_type: 市场类型
        symbols: 交易对列表
        normalizer: 数据标准化器
        nats_publisher: NATS发布器
        config: 配置信息
        
    Returns:
        强平数据管理器实例或None
    """
    return liquidation_manager_factory.create_manager(
        exchange=exchange,
        market_type=market_type,
        symbols=symbols,
        normalizer=normalizer,
        nats_publisher=nats_publisher,
        config=config
    )


def is_liquidation_supported(exchange: str, market_type: str) -> bool:
    """
    便捷函数：检查是否支持强平数据收集
    
    Args:
        exchange: 交易所名称
        market_type: 市场类型
        
    Returns:
        bool: 是否支持
    """
    return liquidation_manager_factory.is_supported(exchange, market_type)


def get_liquidation_supported_combinations() -> List[tuple]:
    """
    便捷函数：获取支持的强平数据收集组合
    
    Returns:
        List[tuple]: 支持的(exchange, market_type)组合列表
    """
    return liquidation_manager_factory.get_supported_combinations()
