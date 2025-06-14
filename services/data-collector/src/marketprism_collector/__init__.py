"""
MarketPrism Python Collector

一个高性能的加密货币市场数据收集器，支持多个交易所的实时数据采集、
数据标准化和通过NATS进行数据分发。

主要功能：
- 支持多个主流加密货币交易所 (Binance, OKX, Deribit等)
- 实时WebSocket数据流
- 数据标准化和清洗
- NATS消息队列集成
- 高性能异步处理
- 完善的监控和日志记录
"""

__version__ = "1.0.0"
__author__ = "MarketPrism Team"
__email__ = "team@marketprism.com"

# 首先尝试导入基础组件
from datetime import datetime, timezone
from .config import Config
from .data_types import *

# 尝试导入Core集成
try:
    from .core_integration import (
        get_core_integration,
        get_metrics_service,
        get_security_service,
        get_storage_service,
        get_reliability_service
    )
    CORE_INTEGRATION_AVAILABLE = True
except ImportError as e:
    # Core集成不可用时的降级处理
    CORE_INTEGRATION_AVAILABLE = False
    print(f"警告: Core集成不可用 - {e}")
    
    # 提供降级实现
    def get_core_integration():
        return None
    
    def get_metrics_service():
        return None
    
    def get_security_service():
        return None
    
    def get_storage_service():
        return None
    
    def get_reliability_service():
        return None

# 最后导入收集器（确保其他依赖项已准备就绪）
try:
    from .collector import MarketDataCollector
    COLLECTOR_AVAILABLE = True
except ImportError as e:
    COLLECTOR_AVAILABLE = False
    print(f"警告: MarketDataCollector不可用 - {e}")
    MarketDataCollector = None

__all__ = [
    "MarketDataCollector",
    "Config",
    "NormalizedTrade",
    "NormalizedOrderBook", 
    "NormalizedKline",
    "NormalizedTicker",
    "get_core_integration",
    "get_metrics_service",
    "get_security_service",
    "get_storage_service",
    "get_reliability_service"
] 