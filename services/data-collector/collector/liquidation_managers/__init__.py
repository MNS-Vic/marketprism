"""
LiquidationManagers - 强平订单数据管理器模块

本模块负责收集和处理各交易所的强平订单数据，遵循MarketPrism的企业级架构标准。

🏗️ 架构设计：
- 基于现有trades_managers和orderbook_managers的成功模式
- 统一的基类设计和工厂模式
- 完整的WebSocket连接管理和重连机制
- 统一的数据标准化和NATS发布

📊 支持的交易所：
- OKX衍生品：永续合约强平数据
- Binance衍生品：永续合约强平数据

🔄 数据流程：
WebSocket订阅 → 数据解析 → 标准化处理 → NATS发布

📈 NATS主题格式：
liquidation-data.{exchange}.{market_type}.{symbol}

🛡️ 企业级特性：
- 统一日志系统集成
- 完整的错误处理和监控
- 内存管理和性能优化
- 配置驱动的灵活架构
"""

from .base_liquidation_manager import BaseLiquidationManager
from .okx_derivatives_liquidation_manager import OKXDerivativesLiquidationManager
from .binance_derivatives_liquidation_manager import BinanceDerivativesLiquidationManager
from .liquidation_manager_factory import LiquidationManagerFactory, liquidation_manager_factory

__all__ = [
    'BaseLiquidationManager',
    'OKXDerivativesLiquidationManager',
    'BinanceDerivativesLiquidationManager',
    'LiquidationManagerFactory',
    'liquidation_manager_factory'
]

# 版本信息
__version__ = "1.0.0"
__author__ = "MarketPrism Team"
__description__ = "强平订单数据管理器模块"
