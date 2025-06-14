"""
数据类型定义

定义了所有标准化的市场数据结构
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from enum import Enum


class DataType(str, Enum):
    """支持的数据类型"""
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    KLINE = "kline"
    TICKER = "ticker"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    LIQUIDATION = "liquidation"
    TOP_TRADER_LONG_SHORT_RATIO = "top_trader_long_short_ratio"
    MARKET_LONG_SHORT_RATIO = "market_long_short_ratio"


class OrderBookUpdateType(str, Enum):
    """订单簿更新类型 - 用于精细化数据流"""
    SNAPSHOT = "snapshot"
    UPDATE = "update" 
    DELTA = "delta"
    FULL_REFRESH = "full_refresh"


class Exchange(str, Enum):
    """支持的交易所"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"
    BYBIT = "bybit"
    HUOBI = "huobi"


class ExchangeType(str, Enum):
    """支持的交易所 (向后兼容)"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"
    BYBIT = "bybit"
    HUOBI = "huobi"


class MarketType(str, Enum):
    """市场类型"""
    SPOT = "spot"
    FUTURES = "futures"
    PERPETUAL = "perpetual"
    OPTIONS = "options"
    DERIVATIVES = "derivatives"


class PriceLevel(BaseModel):
    """价格档位"""
    price: Decimal = Field(..., description="价格")
    quantity: Decimal = Field(..., description="数量")

    class Config:
        json_encoders = {
            Decimal: str
        }
        arbitrary_types_allowed = True


# 类型别名，用于向后兼容
OrderBookEntry = PriceLevel


class NormalizedTrade(BaseModel):
    """标准化的交易数据"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    trade_id: str = Field(..., description="交易ID")
    price: Decimal = Field(..., description="成交价格")
    quantity: Decimal = Field(..., description="成交数量")
    quote_quantity: Decimal = Field(..., description="成交金额")
    timestamp: datetime = Field(..., description="成交时间")
    side: str = Field(..., description="交易方向: buy 或 sell")
    is_best_match: Optional[bool] = Field(None, description="是否最佳匹配")
    
    # Binance API新增字段 (基于2023-07-11和2023-12-04更新)
    transact_time: Optional[datetime] = Field(None, description="交易时间戳(Binance新增)")
    order_id: Optional[str] = Field(None, description="订单ID")
    commission: Optional[Decimal] = Field(None, description="手续费")
    commission_asset: Optional[str] = Field(None, description="手续费资产")
    
    # TRADE_PREVENTION特性字段 (2023-12-04 User Data Streams更新)
    prevented_quantity: Optional[Decimal] = Field(None, description="被阻止执行的数量(pl字段)")
    prevented_price: Optional[Decimal] = Field(None, description="被阻止执行的价格(pL字段)")  
    prevented_quote_qty: Optional[Decimal] = Field(None, description="被阻止执行的名义金额(pY字段)")
    
    # 元数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedOrderBook(BaseModel):
    """标准化的订单簿数据"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    last_update_id: Optional[int] = Field(None, description="最后更新ID")
    bids: List[PriceLevel] = Field(..., description="买单列表")
    asks: List[PriceLevel] = Field(..., description="卖单列表")
    timestamp: datetime = Field(..., description="时间戳")
    
    # 元数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class EnhancedOrderBook(BaseModel):
    """增强的订单簿数据结构 - 扩展现有NormalizedOrderBook"""
    # 继承现有字段
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    last_update_id: Optional[int] = Field(None, description="最后更新ID")
    bids: List[PriceLevel] = Field(..., description="买单列表")
    asks: List[PriceLevel] = Field(..., description="卖单列表")
    timestamp: datetime = Field(..., description="时间戳")
    
    # 新增字段
    update_type: OrderBookUpdateType = Field(OrderBookUpdateType.UPDATE, description="更新类型")
    first_update_id: Optional[int] = Field(None, description="首次更新ID")
    prev_update_id: Optional[int] = Field(None, description="前一个更新ID")
    sequence_id: Optional[int] = Field(None, description="序列ID")
    depth_levels: int = Field(0, description="深度档位数")
    
    # 增量数据字段
    bid_changes: Optional[List[PriceLevel]] = Field(None, description="买单变化")
    ask_changes: Optional[List[PriceLevel]] = Field(None, description="卖单变化")
    removed_bids: Optional[List[Decimal]] = Field(None, description="移除的买单价格")
    removed_asks: Optional[List[Decimal]] = Field(None, description="移除的卖单价格")
    
    # 质量控制
    checksum: Optional[int] = Field(None, description="校验和")
    is_valid: bool = Field(True, description="数据是否有效")
    validation_errors: List[str] = Field(default_factory=list, description="验证错误")
    
    # 时间戳
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="处理时间")
    
    # 深度学习特征 (可选)
    ml_features: Optional[Dict[str, Any]] = Field(None, description="机器学习特征")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class EnhancedOrderBookUpdate(BaseModel):
    """标准化的增量深度更新"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    
    # 更新ID信息
    first_update_id: Optional[int] = Field(None, description="首次更新ID")
    last_update_id: int = Field(..., description="最后更新ID")
    prev_update_id: Optional[int] = Field(None, description="前一个更新ID")
    
    # 增量数据
    bid_updates: List[PriceLevel] = Field(default_factory=list, description="买单更新")
    ask_updates: List[PriceLevel] = Field(default_factory=list, description="卖单更新")
    
    # 统计信息
    total_bid_changes: int = Field(0, description="买单变化总数")
    total_ask_changes: int = Field(0, description="卖单变化总数")
    
    # 质量控制
    checksum: Optional[int] = Field(None, description="校验和")
    is_valid: bool = Field(True, description="数据是否有效")
    
    # 时间戳
    timestamp: datetime = Field(..., description="时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class OrderBookDelta(BaseModel):
    """纯增量订单簿变化"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    update_id: int = Field(..., description="更新ID")
    prev_update_id: Optional[int] = Field(None, description="前一个更新ID")
    
    bid_updates: List[PriceLevel] = Field(default_factory=list, description="买单更新")
    ask_updates: List[PriceLevel] = Field(default_factory=list, description="卖单更新")
    
    total_bid_changes: int = Field(0, description="买单变化总数")
    total_ask_changes: int = Field(0, description="卖单变化总数")
    
    timestamp: datetime = Field(..., description="时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedKline(BaseModel):
    """标准化的K线数据"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    open_time: datetime = Field(..., description="开始时间")
    close_time: datetime = Field(..., description="结束时间")
    interval: str = Field(..., description="时间间隔")
    open_price: Decimal = Field(..., description="开盘价")
    high_price: Decimal = Field(..., description="最高价")
    low_price: Decimal = Field(..., description="最低价")
    close_price: Decimal = Field(..., description="收盘价")
    volume: Decimal = Field(..., description="成交量")
    quote_volume: Decimal = Field(..., description="成交额")
    trade_count: int = Field(..., description="成交笔数")
    taker_buy_volume: Decimal = Field(..., description="主动买入成交量")
    taker_buy_quote_volume: Decimal = Field(..., description="主动买入成交额")
    
    # 元数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedTicker(BaseModel):
    """标准化的行情数据"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    last_price: Decimal = Field(..., description="最新价格")
    open_price: Decimal = Field(..., description="开盘价")
    high_price: Decimal = Field(..., description="最高价")
    low_price: Decimal = Field(..., description="最低价")
    volume: Decimal = Field(..., description="成交量")
    quote_volume: Decimal = Field(..., description="成交额")
    price_change: Decimal = Field(..., description="价格变动")
    price_change_percent: Decimal = Field(..., description="价格变动百分比")
    weighted_avg_price: Decimal = Field(..., description="加权平均价")
    last_quantity: Decimal = Field(..., description="最新成交量")
    best_bid_price: Decimal = Field(..., description="最佳买价")
    best_bid_quantity: Decimal = Field(..., description="最佳买量")
    best_ask_price: Decimal = Field(..., description="最佳卖价")
    best_ask_quantity: Decimal = Field(..., description="最佳卖量")
    open_time: datetime = Field(..., description="开盘时间")
    close_time: datetime = Field(..., description="收盘时间")
    first_trade_id: Optional[int] = Field(None, description="首笔交易ID")
    last_trade_id: Optional[int] = Field(None, description="末笔交易ID")
    trade_count: int = Field(..., description="交易数量")
    timestamp: datetime = Field(..., description="时间戳")
    
    # 元数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedFundingRate(BaseModel):
    """资金费率数据 - 期货合约资金费率信息"""
    exchange_name: str
    symbol_name: str  # 例如: BTC-USDT, ETH-USDT
    funding_rate: Decimal  # 当前资金费率 (如 0.0001 表示 0.01%)
    estimated_rate: Optional[Decimal] = None  # 预测费率
    next_funding_time: datetime  # 下次资金费率结算时间
    mark_price: Decimal  # 标记价格
    index_price: Decimal  # 指数价格
    premium_index: Decimal  # 溢价指数 (标记价格 - 指数价格)
    funding_interval: Optional[str] = "8h"  # 资金费率间隔 (通常8小时)
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedOpenInterest(BaseModel):
    """持仓量数据 - 期货合约未平仓合约数量"""
    exchange_name: str
    symbol_name: str  # 例如: BTC-USDT, ETH-USDT
    open_interest: Decimal  # 持仓量 (合约数量)
    open_interest_value: Decimal  # 持仓量价值 (以USDT计算)
    open_interest_value_usd: Optional[Decimal] = None  # 持仓量价值 (以USD计算)
    change_24h: Optional[Decimal] = None  # 24小时变化量
    change_24h_percent: Optional[Decimal] = None  # 24小时变化百分比
    instrument_type: str = "futures"  # 合约类型: futures, swap, perpetual
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedLiquidation(BaseModel):
    """强平数据 - 强制平仓事件信息"""
    exchange_name: str
    symbol_name: str  # 例如: BTC-USDT, ETH-USDT
    liquidation_id: Optional[str] = None  # 强平ID (如果交易所提供)
    side: str  # 强平方向: "buy" 或 "sell"
    price: Decimal  # 强平价格
    quantity: Decimal  # 强平数量
    value: Optional[Decimal] = None  # 强平价值 (价格 * 数量)
    leverage: Optional[Decimal] = None  # 杠杆倍数
    margin_type: Optional[str] = None  # 保证金类型: "isolated", "cross"
    liquidation_fee: Optional[Decimal] = None  # 强平手续费
    instrument_type: str = "futures"  # 合约类型: futures, swap, spot
    user_id: Optional[str] = None  # 用户ID (通常隐藏或匿名)
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class ExchangeConfig(BaseModel):
    """交易所配置 - TDD优化：提供合理的默认值"""
    exchange: Exchange = Field(..., description="交易所类型")
    market_type: MarketType = Field(MarketType.SPOT, description="市场类型")
    enabled: bool = Field(True, description="是否启用")
    
    # API配置 - TDD优化：提供默认URL
    base_url: str = Field("", description="REST API基础URL")
    ws_url: str = Field("", description="WebSocket URL")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_secret: Optional[str] = Field(None, description="API密钥")
    passphrase: Optional[str] = Field(None, description="API通行短语")
    
    # 代理配置 - TDD发现的设计缺陷修复
    proxy: Optional[Dict[str, Any]] = Field(None, description="代理配置")
    
    # 数据配置 - TDD优化：提供默认值
    data_types: List[DataType] = Field([DataType.TRADE], description="要收集的数据类型")
    symbols: List[str] = Field(["BTCUSDT"], description="要监听的交易对")
    
    # 限制配置
    max_requests_per_minute: int = Field(1200, description="每分钟最大请求数")
    
    # WebSocket配置
    ping_interval: int = Field(30, description="心跳间隔(秒)")
    reconnect_attempts: int = Field(5, description="重连尝试次数")
    reconnect_delay: int = Field(5, description="重连延迟(秒)")
    
    # 订单簿配置
    snapshot_interval: int = Field(10, description="快照间隔(秒)")
    depth_limit: int = Field(20, description="深度限制")
    
    # 新增：networking相关字段 (从core ExchangeConfig迁移)
    # 精度配置（基于Binance最新变更）
    price_precision: int = Field(8, description="价格精度")
    quantity_precision: int = Field(8, description="数量精度")
    
    # 时间戳配置
    timestamp_tolerance: int = Field(5000, description="时间戳容忍度(毫秒)")
    server_time_offset: int = Field(0, description="服务器时间偏移(毫秒)")
    
    # 连接配置
    request_timeout: float = Field(30.0, description="请求超时时间(秒)")
    ws_ping_interval: int = Field(30, description="WebSocket ping间隔(秒)")
    ws_ping_timeout: int = Field(10, description="WebSocket ping超时(秒)")
    
    # 重试配置
    max_retries: int = Field(3, description="最大重试次数")
    retry_backoff: float = Field(1.0, description="重试退避时间(秒)")
    
    # 限流配置（向后兼容）
    rate_limit_requests: int = Field(1200, description="每分钟请求数（rate limiter）")
    rate_limit_window: int = Field(60, description="限流窗口时间(秒)")
    
    # 代理配置（向后兼容）
    http_proxy: Optional[str] = Field(None, description="HTTP代理")
    ws_proxy: Optional[str] = Field(None, description="WebSocket代理")
    
    # 错误处理配置
    ignore_errors: List[str] = Field(default_factory=list, description="忽略的错误码")
    critical_errors: List[str] = Field(default_factory=list, description="关键错误码")
    
    # 向后兼容属性
    @property
    def name(self) -> str:
        """向后兼容：返回交易所名称字符串"""
        return self.exchange.value

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True
    
    @classmethod
    def for_binance(
        cls,
        market_type: MarketType = MarketType.SPOT,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        data_types: Optional[List[DataType]] = None,
        proxy: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> "ExchangeConfig":
        base_urls = {
            MarketType.SPOT: "https://api.binance.com",
            MarketType.FUTURES: "https://fapi.binance.com",
        }
        ws_urls = {
            MarketType.SPOT: "wss://stream.binance.com:9443/ws",
            MarketType.FUTURES: "wss://fstream.binance.com/ws",
        }
        return cls(
            exchange=Exchange.BINANCE,
            market_type=market_type,
            base_url=base_urls.get(market_type, ""),
            ws_url=ws_urls.get(market_type, ""),
            api_key=api_key,
            api_secret=api_secret,
            symbols=symbols or ["BTCUSDT", "ETHUSDT"],
            data_types=data_types or [DataType.TRADE],
            proxy=proxy,
            **kwargs
        )

    @classmethod
    def for_okx(
        cls,
        market_type: MarketType = MarketType.SPOT,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        data_types: Optional[List[DataType]] = None,
        proxy: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> "ExchangeConfig":
        return cls(
            exchange=Exchange.OKX,
            market_type=market_type,
            base_url="https://www.okx.com",
            ws_url="wss://ws.okx.com:8443/ws/v5/public",
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            symbols=symbols or ["BTC-USDT", "ETH-USDT"],
            data_types=data_types or [DataType.TRADE],
            proxy=proxy,
            **kwargs
        )

    @classmethod
    def for_deribit(
        cls,
        market_type: MarketType = MarketType.DERIVATIVES,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        data_types: Optional[List[DataType]] = None,
        proxy: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> "ExchangeConfig":
        return cls(
            exchange=Exchange.DERIBIT,
            market_type=market_type,
            base_url="https://www.deribit.com",
            ws_url="wss://www.deribit.com/ws/api/v2",
            api_key=api_key,
            api_secret=api_secret,
            symbols=symbols or ["BTC-PERPETUAL"],
            data_types=data_types or [DataType.TRADE],
            proxy=proxy,
            **kwargs
        )


class CollectorMetrics(BaseModel):
    """收集器指标"""
    messages_received: int = Field(0, description="接收消息数")
    messages_processed: int = Field(0, description="处理消息数")
    messages_published: int = Field(0, description="发布消息数")
    errors_count: int = Field(0, description="错误数量")
    last_message_time: Optional[datetime] = Field(None, description="最后消息时间")
    uptime_seconds: float = Field(0.0, description="运行时间(秒)")
    
    # 按交易所统计
    exchange_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict, description="交易所统计")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class HealthStatus(BaseModel):
    """健康状态"""
    status: str = Field(..., description="状态: healthy, degraded, unhealthy")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="检查时间")
    version: str = Field(..., description="版本号")
    uptime_seconds: float = Field(..., description="运行时间")
    
    # 组件状态
    nats_connected: bool = Field(..., description="NATS连接状态")
    exchanges_connected: Dict[str, bool] = Field(..., description="交易所连接状态")
    
    # 指标
    metrics: CollectorMetrics = Field(..., description="收集器指标") 

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedTopTraderLongShortRatio(BaseModel):
    """大户持仓比数据 - 标准化的大户多空持仓比例信息"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称，如 BTC-USDT")
    
    # 核心数据
    long_short_ratio: Decimal = Field(..., description="多空比值 (多仓比例/空仓比例)")
    long_position_ratio: Decimal = Field(..., description="多仓持仓比例 (0-1之间)")
    short_position_ratio: Decimal = Field(..., description="空仓持仓比例 (0-1之间)")
    
    # 账户数据 (如果可用)
    long_account_ratio: Optional[Decimal] = Field(None, description="多仓账户比例 (0-1之间)")
    short_account_ratio: Optional[Decimal] = Field(None, description="空仓账户比例 (0-1之间)")
    long_short_account_ratio: Optional[Decimal] = Field(None, description="多空账户数比值")
    
    # 元数据
    data_type: str = Field("position", description="数据类型: position(持仓) 或 account(账户)")
    period: Optional[str] = Field(None, description="时间周期，如 5m, 15m, 1h")
    instrument_type: str = Field("futures", description="合约类型: futures, swap, perpetual")
    
    # 时间戳
    timestamp: datetime = Field(..., description="数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True
    
    def __hash__(self):
        return hash((self.exchange_name, self.symbol_name, self.timestamp))


class NormalizedMarketLongShortRatio(BaseModel):
    """整个市场多空仓人数比数据 - 标准化的市场多空仓人数比例信息"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称，如 BTC-USDT")
    
    # 核心数据 - 人数比例
    long_short_ratio: Decimal = Field(..., description="多空人数比值 (多仓人数/空仓人数)")
    long_account_ratio: Decimal = Field(..., description="多仓账户比例 (0-1之间)")
    short_account_ratio: Decimal = Field(..., description="空仓账户比例 (0-1之间)")
    
    # 可选的持仓量数据 (如果API提供)
    long_position_ratio: Optional[Decimal] = Field(None, description="多仓持仓量比例 (0-1之间)")
    short_position_ratio: Optional[Decimal] = Field(None, description="空仓持仓量比例 (0-1之间)")
    long_short_position_ratio: Optional[Decimal] = Field(None, description="多空持仓量比值")
    
    # 元数据
    data_type: str = Field("account", description="数据类型: account(账户人数) 或 position(持仓量)")
    period: Optional[str] = Field(None, description="时间周期，如 5m, 15m, 1h")
    instrument_type: str = Field("futures", description="合约类型: futures, swap, perpetual")
    
    # 时间戳
    timestamp: datetime = Field(..., description="数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True

    def __hash__(self):
        return hash((self.exchange_name, self.symbol_name, self.timestamp))


class NormalizedAccountInfo(BaseModel):
    """标准化的账户信息 - 支持Binance API新字段"""
    exchange_name: str = Field(..., description="交易所名称")
    account_type: str = Field(..., description="账户类型: spot, futures, margin")
    
    # 账户基本信息
    maker_commission: Decimal = Field(..., description="Maker手续费率")
    taker_commission: Decimal = Field(..., description="Taker手续费率")
    buyer_commission: Decimal = Field(..., description="买方手续费率") 
    seller_commission: Decimal = Field(..., description="卖方手续费率")
    
    # 账户权限
    can_trade: bool = Field(..., description="是否可以交易")
    can_withdraw: bool = Field(..., description="是否可以提现")
    can_deposit: bool = Field(..., description="是否可以充值")
    
    # Binance API新增字段 (2023-07-11更新)
    prevent_sor: Optional[bool] = Field(None, description="SOR防护设置")
    uid: Optional[str] = Field(None, description="用户ID")
    
    # 资产信息
    balances: List[Dict[str, Any]] = Field(default_factory=list, description="账户余额")
    
    # 时间戳
    update_time: datetime = Field(..., description="更新时间")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedOrderResponse(BaseModel):
    """标准化的订单响应 - 支持Binance API新字段"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol: str = Field(..., description="交易对")
    order_id: str = Field(..., description="订单ID")
    client_order_id: str = Field(..., description="客户端订单ID")
    
    # 订单信息
    price: Decimal = Field(..., description="价格")
    orig_qty: Decimal = Field(..., description="原始数量")
    executed_qty: Decimal = Field(..., description="已执行数量")
    cumulative_quote_qty: Decimal = Field(..., description="累计成交金额")
    status: str = Field(..., description="订单状态")
    time_in_force: str = Field(..., description="有效时间")
    order_type: str = Field(..., description="订单类型")
    side: str = Field(..., description="买卖方向")
    
    # Binance API新增字段 (2023-07-11和2023-12-04更新)
    transact_time: Optional[datetime] = Field(None, description="交易时间(新增)")
    working_time: Optional[datetime] = Field(None, description="订单开始工作时间")
    self_trade_prevention_mode: Optional[str] = Field(None, description="自成交防护模式")
    
    # 手续费信息
    fills: List[Dict[str, Any]] = Field(default_factory=list, description="成交明细")
    
    # 时间戳
    timestamp: datetime = Field(..., description="时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedAccountCommission(BaseModel):
    """标准化的账户佣金信息 - Binance API 2023-12-04新增"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol: str = Field(..., description="交易对")
    
    # 标准佣金费率
    standard_commission: Dict[str, Decimal] = Field(..., description="标准佣金费率")
    tax_commission: Dict[str, Decimal] = Field(..., description="税费佣金费率")
    discount: Dict[str, Decimal] = Field(..., description="佣金折扣")
    
    # 实际费率
    maker_commission: Decimal = Field(..., description="Maker费率")
    taker_commission: Decimal = Field(..., description="Taker费率")
    
    # 时间戳
    timestamp: datetime = Field(..., description="时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedTradingDayTicker(BaseModel):
    """标准化的交易日行情数据 - Binance API 2023-12-04新增"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol: str = Field(..., description="交易对")
    
    # 价格信息
    price_change: Decimal = Field(..., description="价格变化")
    price_change_percent: Decimal = Field(..., description="价格变化百分比")
    weighted_avg_price: Decimal = Field(..., description="加权平均价")
    open_price: Decimal = Field(..., description="开盘价")
    high_price: Decimal = Field(..., description="最高价")
    low_price: Decimal = Field(..., description="最低价")
    last_price: Decimal = Field(..., description="最新价")
    
    # 成交量信息
    volume: Decimal = Field(..., description="成交量")
    quote_volume: Decimal = Field(..., description="成交额")
    
    # 时间信息 - 交易日特定
    open_time: datetime = Field(..., description="开盘时间")
    close_time: datetime = Field(..., description="收盘时间")
    first_id: int = Field(..., description="首成交ID")
    last_id: int = Field(..., description="末成交ID")
    count: int = Field(..., description="成交笔数")
    
    # 时间戳
    timestamp: datetime = Field(..., description="时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedAvgPrice(BaseModel):
    """标准化的平均价格数据 - 支持Binance API 2023-12-04新增closeTime字段"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol: str = Field(..., description="交易对")
    
    # 价格信息
    price: Decimal = Field(..., description="平均价格")
    
    # 时间信息
    close_time: Optional[datetime] = Field(None, description="最后交易时间(2023-12-04新增)")
    
    # 时间戳
    timestamp: datetime = Field(..., description="时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True


class NormalizedSessionInfo(BaseModel):
    """标准化的会话信息 - 支持Binance API 2023-12-04新增Ed25519会话认证"""
    exchange_name: str = Field(..., description="交易所名称")
    
    # 会话状态
    session_id: str = Field(..., description="会话ID")
    status: str = Field(..., description="会话状态: AUTHENTICATED, EXPIRED, etc.")
    
    # 认证信息
    auth_method: str = Field(..., description="认证方法: Ed25519, RSA, etc.")
    permissions: List[str] = Field(default_factory=list, description="权限列表")
    
    # 时间信息
    login_time: datetime = Field(..., description="登录时间")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    
    # 时间戳
    timestamp: datetime = Field(..., description="时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat().replace('+00:00', 'Z'),
            Decimal: str
        }
        arbitrary_types_allowed = True
