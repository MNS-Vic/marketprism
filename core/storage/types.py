"""
MarketPrism Core 数据类型定义

提供统一的数据结构定义，确保系统各组件间数据交换的一致性
"""

from typing import List, Optional, Any, Dict, Union
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

class StorageType(Enum):
    """存储类型枚举"""
    CLICKHOUSE = 'clickhouse'
    REDIS = 'redis'
    FILE = 'file'
    MEMORY = 'memory'
    POSTGRESQL = 'postgresql'
    MYSQL = 'mysql'

class DataFormat(Enum):
    """数据格式枚举"""
    JSON = 'json'
    CSV = 'csv'
    PARQUET = 'parquet'
    BINARY = 'binary'
    AVRO = 'avro'
    PROTOBUF = 'protobuf'

@dataclass
class NormalizedTrade:
    """标准化交易数据"""
    exchange_name: str
    symbol_name: str
    trade_id: str
    price: Union[float, Decimal, str]
    quantity: Union[float, Decimal, str]
    timestamp: datetime
    is_buyer_maker: bool
    trade_time: Optional[datetime] = None
    
    def __post_init__(self):
        if self.trade_time is None:
            self.trade_time = self.timestamp

@dataclass 
class BookLevel:
    """订单簿价格档位"""
    price: Union[float, Decimal, str]
    quantity: Union[float, Decimal, str]

@dataclass
class NormalizedOrderBook:
    """标准化订单簿数据"""
    exchange_name: str
    symbol_name: str
    timestamp: datetime
    bids: List[BookLevel]
    asks: List[BookLevel]
    last_update_id: Optional[str] = None

@dataclass
class NormalizedTicker:
    """标准化行情数据"""
    exchange_name: str
    symbol_name: str
    open_price: Union[float, Decimal, str]
    high_price: Union[float, Decimal, str]
    low_price: Union[float, Decimal, str]
    close_price: Union[float, Decimal, str]
    volume: Union[float, Decimal, str]
    quote_volume: Union[float, Decimal, str]
    price_change: Union[float, Decimal, str]
    price_change_percent: Union[float, Decimal, str]
    weighted_avg_price: Union[float, Decimal, str]
    prev_close_price: Union[float, Decimal, str]
    last_price: Union[float, Decimal, str]
    last_quantity: Union[float, Decimal, str]
    bid_price: Union[float, Decimal, str]
    ask_price: Union[float, Decimal, str]
    open_time: datetime
    close_time: datetime
    timestamp: datetime

# 其他常用类型定义
MarketData = Union[NormalizedTrade, NormalizedOrderBook, NormalizedTicker]

# 使用统一的ExchangeConfig - 向后兼容的简化版本
@dataclass
class ExchangeConfig:
    """交易所配置 - 向后兼容的简化版本"""
    name: str
    enabled: bool
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    sandbox: bool = False
    rate_limit: int = 1200
    timeout: int = 30
    
    @classmethod
    def from_unified_config(cls, unified_config):
        """从统一的ExchangeConfig创建简化版本"""
        try:
            return cls(
                name=unified_config.exchange.value,
                enabled=unified_config.enabled,
                api_key=unified_config.api_key,
                api_secret=unified_config.api_secret,
                rate_limit=unified_config.max_requests_per_minute,
                timeout=int(unified_config.request_timeout)
            )
        except AttributeError:
            # 如果unified_config不是预期的格式，返回默认配置
            return cls(name="unknown", enabled=True)

@dataclass
class SymbolConfig:
    """交易对配置"""
    symbol: str
    base_asset: str
    quote_asset: str
    enabled: bool
    min_quantity: Optional[float] = None
    tick_size: Optional[float] = None

@dataclass
class ErrorInfo:
    """错误信息"""
    error_type: str
    error_message: str
    timestamp: datetime
    context: Optional[Dict[str, Any]] = None
    exchange: Optional[str] = None
    symbol: Optional[str] = None

@dataclass
class PerformanceMetric:
    """性能指标"""
    name: str
    value: Union[float, int]
    unit: str
    timestamp: datetime
    labels: Optional[Dict[str, str]] = None

@dataclass
class MonitoringAlert:
    """监控告警"""
    alert_id: str
    alert_type: str
    severity: str
    message: str
    timestamp: datetime
    resolved: bool = False
    context: Optional[Dict[str, Any]] = None

# 导出所有公共类型
__all__ = [
    'StorageType',
    'DataFormat',
    'NormalizedTrade',
    'BookLevel', 
    'NormalizedOrderBook',
    'NormalizedTicker',
    'MarketData',
    'ExchangeConfig',
    'SymbolConfig',
    'ErrorInfo',
    'PerformanceMetric',
    'MonitoringAlert'
]