"""
数据类型定义

定义了所有标准化的市场数据结构
"""

from datetime import datetime
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
    
    # 元数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")
    processed_at: datetime = Field(default_factory=datetime.utcnow, description="处理时间")
    
    # 深度学习特征 (可选)
    ml_features: Optional[Dict[str, Any]] = Field(None, description="机器学习特征")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        }


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        }


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        }


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")


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
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        }


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
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        }


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
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        }


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
        """便利方法：创建Binance配置"""
        return cls(
            exchange=Exchange.BINANCE,
            market_type=market_type,
            base_url="https://api.binance.com" if market_type == MarketType.SPOT else "https://fapi.binance.com",
            ws_url="wss://stream.binance.com:9443" if market_type == MarketType.SPOT else "wss://fstream.binance.com/ws",
            api_key=api_key,
            api_secret=api_secret,
            proxy=proxy,
            symbols=symbols or ["BTCUSDT", "ETHUSDT"],
            data_types=data_types or [DataType.TRADE, DataType.ORDERBOOK],
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
        """便利方法：创建OKX配置"""
        return cls(
            exchange=Exchange.OKX,
            market_type=market_type,
            base_url="https://www.okx.com",
            ws_url="wss://ws.okx.com:8443/ws/v5/public",
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            proxy=proxy,
            symbols=symbols or ["BTC-USDT", "ETH-USDT"],
            data_types=data_types or [DataType.TRADE, DataType.ORDERBOOK],
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
        """便利方法：创建Deribit配置"""
        return cls(
            exchange=Exchange.DERIBIT,
            market_type=market_type,
            base_url="https://www.deribit.com",
            ws_url="wss://www.deribit.com/ws/api/v2",
            api_key=api_key,
            api_secret=api_secret,
            proxy=proxy,
            symbols=symbols or ["BTC-PERPETUAL", "ETH-PERPETUAL"],
            data_types=data_types or [DataType.TRADE, DataType.TICKER],
            ping_interval=30,  # Deribit建议30秒心跳
            reconnect_attempts=5,
            reconnect_delay=5,
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


class HealthStatus(BaseModel):
    """健康状态"""
    status: str = Field(..., description="状态: healthy, degraded, unhealthy")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="检查时间")
    version: str = Field(..., description="版本号")
    uptime_seconds: float = Field(..., description="运行时间")
    
    # 组件状态
    nats_connected: bool = Field(..., description="NATS连接状态")
    exchanges_connected: Dict[str, bool] = Field(..., description="交易所连接状态")
    
    # 指标
    metrics: CollectorMetrics = Field(..., description="收集器指标") 


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        } 


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
    collected_at: datetime = Field(default_factory=datetime.utcnow, description="采集时间")
    
    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z',
            Decimal: lambda v: str(v)
        } 