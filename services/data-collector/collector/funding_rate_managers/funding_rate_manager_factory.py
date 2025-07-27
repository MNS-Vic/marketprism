"""
资金费率管理器工厂

提供统一的资金费率管理器创建接口：
- 支持不同交易所的管理器创建
- 统一的配置管理
- 错误处理和验证
"""

from typing import List, Dict, Any, Optional
import structlog

from .base_funding_rate_manager import BaseFundingRateManager
from .binance_derivatives_funding_rate_manager import BinanceDerivativesFundingRateManager
from .okx_derivatives_funding_rate_manager import OKXDerivativesFundingRateManager


class FundingRateManagerFactory:
    """资金费率管理器工厂"""
    
    # 支持的交易所管理器映射
    MANAGER_CLASSES = {
        'binance_derivatives': BinanceDerivativesFundingRateManager,
        'okx_derivatives': OKXDerivativesFundingRateManager,
    }
    
    @classmethod
    def create_manager(
        cls,
        exchange: str,
        symbols: List[str],
        nats_publisher=None,
        **kwargs
    ) -> BaseFundingRateManager:
        """
        创建资金费率管理器
        
        Args:
            exchange: 交易所名称 (binance_derivatives, okx_derivatives)
            symbols: 交易对列表
            nats_publisher: NATS发布器实例
            **kwargs: 其他配置参数
            
        Returns:
            资金费率管理器实例
            
        Raises:
            ValueError: 不支持的交易所
        """
        logger = structlog.get_logger("funding_rate_factory")
        
        if exchange not in cls.MANAGER_CLASSES:
            supported_exchanges = list(cls.MANAGER_CLASSES.keys())
            raise ValueError(f"不支持的交易所: {exchange}，支持的交易所: {supported_exchanges}")
        
        if not symbols:
            raise ValueError("交易对列表不能为空")
        
        manager_class = cls.MANAGER_CLASSES[exchange]
        
        try:
            manager = manager_class(
                symbols=symbols,
                nats_publisher=nats_publisher,
                **kwargs
            )
            
            logger.info("资金费率管理器创建成功",
                       exchange=exchange,
                       symbols=symbols,
                       manager_class=manager_class.__name__)
            
            return manager
            
        except Exception as e:
            logger.error("资金费率管理器创建失败",
                        exchange=exchange,
                        error=str(e))
            raise
    
    @classmethod
    def create_managers_from_config(
        cls,
        config: Dict[str, Any],
        nats_publisher=None
    ) -> List[BaseFundingRateManager]:
        """
        从配置创建多个资金费率管理器
        
        Args:
            config: 配置字典
            nats_publisher: NATS发布器实例
            
        Returns:
            资金费率管理器列表
        """
        logger = structlog.get_logger("funding_rate_factory")
        managers = []
        
        try:
            # 解析配置
            funding_rate_config = config.get('funding_rate', {})
            if not funding_rate_config.get('enabled', False):
                logger.info("资金费率收集未启用")
                return managers
            
            exchanges_config = funding_rate_config.get('exchanges', {})
            
            for exchange, exchange_config in exchanges_config.items():
                if not exchange_config.get('enabled', False):
                    logger.info("交易所资金费率收集未启用", exchange=exchange)
                    continue
                
                symbols = exchange_config.get('symbols', [])
                if not symbols:
                    logger.warning("交易所未配置交易对", exchange=exchange)
                    continue
                
                try:
                    manager = cls.create_manager(
                        exchange=exchange,
                        symbols=symbols,
                        nats_publisher=nats_publisher
                    )
                    managers.append(manager)
                    
                except Exception as e:
                    logger.error("创建交易所资金费率管理器失败",
                               exchange=exchange,
                               error=str(e))
            
            logger.info("资金费率管理器批量创建完成",
                       total_managers=len(managers))
            
            return managers
            
        except Exception as e:
            logger.error("从配置创建资金费率管理器失败", error=str(e))
            return managers
    
    @classmethod
    def get_supported_exchanges(cls) -> List[str]:
        """获取支持的交易所列表"""
        return list(cls.MANAGER_CLASSES.keys())
    
    @classmethod
    def validate_exchange(cls, exchange: str) -> bool:
        """验证交易所是否支持"""
        return exchange in cls.MANAGER_CLASSES
