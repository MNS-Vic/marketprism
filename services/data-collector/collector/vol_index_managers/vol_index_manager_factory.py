"""
波动率指数管理器工厂

根据交易所类型创建相应的波动率指数管理器实例：
- Deribit衍生品波动率指数管理器
- 支持扩展其他交易所
"""

from typing import List, Optional
import structlog

from .base_vol_index_manager import BaseVolIndexManager
from .deribit_derivatives_vol_index_manager import DeribitDerivativesVolIndexManager


class VolIndexManagerFactory:
    """波动率指数管理器工厂类"""
    
    # 支持的交易所映射
    SUPPORTED_EXCHANGES = {
        'deribit_derivatives': DeribitDerivativesVolIndexManager,
    }
    
    @classmethod
    def create_manager(
        cls, 
        exchange: str, 
        symbols: List[str], 
        nats_publisher=None
    ) -> Optional[BaseVolIndexManager]:
        """
        创建波动率指数管理器实例
        
        Args:
            exchange: 交易所名称 (deribit_derivatives)
            symbols: 交易对列表
            nats_publisher: NATS发布器实例
            
        Returns:
            波动率指数管理器实例，失败返回None
        """
        logger = structlog.get_logger("vol_index_manager_factory")
        
        if not exchange:
            logger.error("交易所名称不能为空")
            return None
        
        if not symbols:
            logger.error("交易对列表不能为空", exchange=exchange)
            return None
        
        # 检查交易所是否支持
        if exchange not in cls.SUPPORTED_EXCHANGES:
            logger.error("不支持的交易所", 
                        exchange=exchange,
                        supported_exchanges=list(cls.SUPPORTED_EXCHANGES.keys()))
            return None
        
        try:
            # 获取管理器类
            manager_class = cls.SUPPORTED_EXCHANGES[exchange]
            
            # 创建管理器实例
            manager = manager_class(
                symbols=symbols,
                nats_publisher=nats_publisher
            )
            
            logger.info("波动率指数管理器创建成功", 
                       exchange=exchange,
                       manager_class=manager_class.__name__,
                       symbols=symbols)
            
            return manager
            
        except Exception as e:
            logger.error("创建波动率指数管理器失败", 
                        exchange=exchange,
                        symbols=symbols,
                        error=str(e))
            return None
    
    @classmethod
    def get_supported_exchanges(cls) -> List[str]:
        """
        获取支持的交易所列表
        
        Returns:
            支持的交易所名称列表
        """
        return list(cls.SUPPORTED_EXCHANGES.keys())
    
    @classmethod
    def is_exchange_supported(cls, exchange: str) -> bool:
        """
        检查交易所是否支持
        
        Args:
            exchange: 交易所名称
            
        Returns:
            是否支持该交易所
        """
        return exchange in cls.SUPPORTED_EXCHANGES
