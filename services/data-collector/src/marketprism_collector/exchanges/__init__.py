"""
MarketPrism 交易所适配器模块 - 统一架构

基于用户反馈完全简化架构：
- 统一适配器：所有适配器都继承ExchangeAdapter，支持完整ping/pong
- 统一工厂：整合基础工厂、智能工厂、管理器为一个文件
- 移除enhanced/standard分离，简化为单一适配器模式
- 保持所有企业级功能：智能选择、健康监控、性能统计、事件回调

架构优势：
- 单一文件管理：factory.py包含所有工厂和管理功能
- 统一接口：一个ExchangeFactory类处理所有需求
- 完整功能：保留ping/pong、会话管理、动态订阅等所有功能
- 简单明了：符合"别搞复杂了"的哲学
"""

# 统一适配器导入
from datetime import datetime, timezone
from .base import ExchangeAdapter
from .binance import BinanceAdapter
from .okx import OKXAdapter
from .deribit import DeribitAdapter

# 统一工厂导入（包含所有功能）
from .factory import (
    ExchangeFactory,
    ExchangeHealth,
    AdapterCapability,
    ExchangeRequirements,
    # 全局工厂实例和便利函数
    get_factory,
    create_adapter,
    get_supported_exchanges,
    get_architecture_info,
    # 多交易所管理便利函数
    create_exchange_manager,
    add_managed_adapter,
    get_health_status,
    get_performance_stats,
    # 向后兼容性别名
    intelligent_factory,
    ExchangeManager
)

# 公开接口
__all__ = [
    # 适配器类
    'ExchangeAdapter',
    'BinanceAdapter', 
    'OKXAdapter',
    'DeribitAdapter',
    
    # 统一工厂（包含所有功能）
    'ExchangeFactory',
    'ExchangeHealth',
    'AdapterCapability',
    'ExchangeRequirements',
    
    # 便利函数
    'get_factory',
    'create_adapter',
    'get_supported_exchanges', 
    'get_architecture_info',
    'create_exchange_manager',
    'add_managed_adapter',
    'get_health_status',
    'get_performance_stats',
    
    # 向后兼容性
    'intelligent_factory',
    'ExchangeManager'
]

# 版本信息
__version__ = "2.0.0"
__architecture__ = "unified_intelligent_factory_with_management"