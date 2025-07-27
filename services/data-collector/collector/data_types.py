"""
数据类型定义

定义了所有标准化的市场数据结构
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class DataType(str, Enum):
    """支持的数据类型"""
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    KLINE = "kline"

    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    LIQUIDATION = "liquidation"
    TOP_TRADER_LONG_SHORT_RATIO = "top_trader_long_short_ratio"
    MARKET_LONG_SHORT_RATIO = "market_long_short_ratio"
    VOLATILITY_INDEX = "volatility_index"

    # 新增LSR数据类型
    LSR_TOP_POSITION = "lsr_top_position"  # 顶级大户多空持仓比例（按持仓量计算）
    LSR_ALL_ACCOUNT = "lsr_all_account"    # 全市场多空持仓人数比例（按账户数计算）


class OrderBookUpdateType(str, Enum):
    """订单簿更新类型 - 用于精细化数据流"""
    SNAPSHOT = "snapshot"
    UPDATE = "update" 
    DELTA = "delta"
    FULL_REFRESH = "full_refresh"


class Exchange(str, Enum):
    """支持的交易所（基于新的市场分类架构）"""
    # 🎯 新的市场分类架构
    BINANCE_SPOT = "binance_spot"           # ✅ Binance现货
    BINANCE_DERIVATIVES = "binance_derivatives"  # ✅ Binance衍生品（永续合约、期货）
    OKX_SPOT = "okx_spot"                   # ✅ OKX现货
    OKX_DERIVATIVES = "okx_derivatives"     # ✅ OKX衍生品（永续合约、期货）
    DERIBIT_DERIVATIVES = "deribit_derivatives"  # ✅ Deribit衍生品（期权、永续合约）

    # 🔧 向后兼容（保留旧的命名）
    BINANCE = "binance"  # ⚠️ 向后兼容，建议使用BINANCE_SPOT
    OKX = "okx"          # ⚠️ 向后兼容，建议使用OKX_SPOT


class ExchangeType(str, Enum):
    """支持的交易所 (向后兼容，基于新的市场分类架构)"""
    # 🎯 新的市场分类架构
    BINANCE_SPOT = "binance_spot"           # ✅ Binance现货
    BINANCE_DERIVATIVES = "binance_derivatives"  # ✅ Binance衍生品
    OKX_SPOT = "okx_spot"                   # ✅ OKX现货
    OKX_DERIVATIVES = "okx_derivatives"     # ✅ OKX衍生品
    DERIBIT_DERIVATIVES = "deribit_derivatives"  # ✅ Deribit衍生品

    # 🔧 向后兼容
    BINANCE = "binance"  # ⚠️ 向后兼容
    OKX = "okx"          # ⚠️ 向后兼容


class MarketType(str, Enum):
    """市场类型 - 基于币安官方API文档"""
    SPOT = "spot"                    # 现货交易 (api.binance.com)
    PERPETUAL = "perpetual"          # USD本位永续合约 (fapi.binance.com)
    FUTURES = "futures"              # 交割期货 (保留向后兼容)

    # 向后兼容别名
    SWAP = "perpetual"               # 映射到PERPETUAL，保持向后兼容

    # 未来扩展
    COIN_FUTURES = "coin_futures"    # 币本位期货 (dapi.binance.com)
    OPTIONS = "options"              # 期权交易
    DERIVATIVES = "derivatives"      # 衍生品 (通用)


class PriceLevel(BaseModel):
    """价格档位"""
    price: Decimal = Field(..., description="价格")
    quantity: Decimal = Field(..., description="数量")

    model_config = ConfigDict(arbitrary_types_allowed=True)# 类型别名，用于向后兼容
OrderBookEntry = PriceLevel


class NormalizedTrade(BaseModel):
    """标准化的交易数据 - 支持现货、期货、永续合约的统一格式"""
    # 基础信息
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称 (标准格式: BTC-USDT)")
    currency: str = Field(..., description="币种名称 (如: BTC)")

    # 核心交易数据
    trade_id: str = Field(..., description="交易ID")
    price: Decimal = Field(..., description="成交价格")
    quantity: Decimal = Field(..., description="成交数量")
    quote_quantity: Optional[Decimal] = Field(None, description="成交金额")
    side: str = Field(..., description="交易方向: buy(主动买入) 或 sell(主动卖出)")

    # 时间信息
    timestamp: datetime = Field(..., description="成交时间")
    event_time: Optional[datetime] = Field(None, description="事件时间")

    # 交易类型和元数据
    trade_type: str = Field(..., description="交易类型: spot/perpetual/futures")
    is_maker: Optional[bool] = Field(None, description="买方是否为做市方(仅Binance提供,OKX为None)")
    is_best_match: Optional[bool] = Field(None, description="是否最佳匹配")

    # 归集交易特有字段 (Binance期货)
    agg_trade_id: Optional[str] = Field(None, description="归集交易ID")
    first_trade_id: Optional[str] = Field(None, description="首个交易ID")
    last_trade_id: Optional[str] = Field(None, description="末次交易ID")

    # Binance API扩展字段
    transact_time: Optional[datetime] = Field(None, description="交易时间戳(Binance)")
    order_id: Optional[str] = Field(None, description="订单ID")
    commission: Optional[Decimal] = Field(None, description="手续费")
    commission_asset: Optional[str] = Field(None, description="手续费资产")

    # TRADE_PREVENTION特性字段
    prevented_quantity: Optional[Decimal] = Field(None, description="被阻止执行的数量")
    prevented_price: Optional[Decimal] = Field(None, description="被阻止执行的价格")
    prevented_quote_qty: Optional[Decimal] = Field(None, description="被阻止执行的名义金额")

    # 元数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于存储和传输"""
        return {
            "exchange_name": self.exchange_name,
            "symbol_name": self.symbol_name,
            "currency": self.currency,
            "trade_id": self.trade_id,
            "price": float(self.price),
            "quantity": float(self.quantity),
            "quote_quantity": float(self.quote_quantity) if self.quote_quantity else None,
            "side": self.side,
            "timestamp": self.timestamp.isoformat(),
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "trade_type": self.trade_type,
            "is_maker": self.is_maker,
            "is_best_match": self.is_best_match,
            "agg_trade_id": self.agg_trade_id,
            "first_trade_id": self.first_trade_id,
            "last_trade_id": self.last_trade_id,
            "collected_at": self.collected_at.isoformat(),
            "raw_data": self.raw_data
        }


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

    model_config = ConfigDict(arbitrary_types_allowed=True)


class EnhancedOrderBook(BaseModel):
    """增强的订单簿数据结构 - 扩展现有NormalizedOrderBook"""
    # 继承现有字段
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称")
    market_type: str = Field(default='spot', description="市场类型 (spot/perpetual)")  # 🔧 添加市场类型字段
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
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


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
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


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
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


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

    model_config = ConfigDict(arbitrary_types_allowed=True)





class NormalizedFundingRate(BaseModel):
    """标准化的资金费率数据 - 永续合约资金费率信息"""

    # 基础信息
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称 (标准格式: BTC-USDT)")
    product_type: str = Field(default="swap", description="产品类型: swap/perpetual")
    instrument_id: str = Field(..., description="产品ID (交易所原始格式)")

    # 资金费率信息
    current_funding_rate: Decimal = Field(..., description="当前资金费率 (如 0.0001 表示 0.01%)")
    estimated_funding_rate: Optional[Decimal] = Field(None, description="预估下期资金费率")
    next_funding_time: datetime = Field(..., description="下次资金费率结算时间")
    funding_interval: str = Field(default="8h", description="资金费率间隔 (通常8小时)")

    # 价格信息
    mark_price: Optional[Decimal] = Field(None, description="标记价格")
    index_price: Optional[Decimal] = Field(None, description="指数价格")
    premium_index: Optional[Decimal] = Field(None, description="溢价指数 (标记价格 - 指数价格)")

    # 历史统计 (可选)
    funding_rate_24h_avg: Optional[Decimal] = Field(None, description="24小时平均资金费率")
    funding_rate_7d_avg: Optional[Decimal] = Field(None, description="7天平均资金费率")

    # 时间信息
    timestamp: datetime = Field(..., description="数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __post_init__(self):
        """数据验证和计算"""
        # 计算溢价指数
        if self.mark_price and self.index_price and not self.premium_index:
            self.premium_index = self.mark_price - self.index_price

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "exchange_name": self.exchange_name,
            "symbol_name": self.symbol_name,
            "product_type": self.product_type,
            "instrument_id": self.instrument_id,
            "current_funding_rate": float(self.current_funding_rate),
            "estimated_funding_rate": float(self.estimated_funding_rate) if self.estimated_funding_rate else None,
            "next_funding_time": self.next_funding_time.isoformat(),
            "funding_interval": self.funding_interval,
            "mark_price": float(self.mark_price) if self.mark_price else None,
            "index_price": float(self.index_price) if self.index_price else None,
            "premium_index": float(self.premium_index) if self.premium_index else None,
            "funding_rate_24h_avg": float(self.funding_rate_24h_avg) if self.funding_rate_24h_avg else None,
            "funding_rate_7d_avg": float(self.funding_rate_7d_avg) if self.funding_rate_7d_avg else None,
            "timestamp": self.timestamp.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "raw_data": self.raw_data
        }



class ExchangeConfig(BaseModel):
    """交易所配置 - 支持配置文件和代码默认值"""
    exchange: Exchange = Field(..., description="交易所类型")
    market_type: MarketType = Field(MarketType.SPOT, description="市场类型")
    enabled: bool = Field(True, description="是否启用")

    # 配置来源标识
    _config_source: str = "code_defaults"  # code_defaults, config_file, environment
    
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
    
    # 订单簿配置 - 确保增量订阅和快照一致性
    snapshot_interval: int = Field(10, description="快照间隔(秒)")
    snapshot_depth: int = Field(400, description="快照获取档位")
    websocket_depth: int = Field(20, description="WebSocket订阅档位")

    # 策略配置
    strategy_name: str = Field("default", description="交易策略名称")
    strategy_priority: str = Field("medium", description="策略优先级")

    # 向后兼容
    @property
    def depth_limit(self) -> int:
        """向后兼容的depth_limit属性"""
        return self.snapshot_depth

    def get_optimal_depths(self) -> tuple[int, int]:
        """
        获取最优的快照和WebSocket深度配置

        Returns:
            (snapshot_depth, websocket_depth)
        """
        # 🎯 根据交易所调整默认配置（支持新的市场分类架构）
        if self.exchange in [Exchange.BINANCE, Exchange.BINANCE_SPOT, Exchange.BINANCE_DERIVATIVES]:
            # Binance: 400档快照 + 20档WebSocket
            snapshot = min(self.snapshot_depth, 1000)  # Binance最大1000档
            websocket = 20 if self.websocket_depth > 20 else self.websocket_depth
        elif self.exchange in [Exchange.OKX, Exchange.OKX_SPOT, Exchange.OKX_DERIVATIVES]:
            # OKX: 400档快照 + 400档WebSocket
            snapshot = min(self.snapshot_depth, 400)  # OKX最大400档
            websocket = min(self.websocket_depth, 400)
        else:
            # 其他交易所使用配置值
            snapshot = self.snapshot_depth
            websocket = self.websocket_depth

        return snapshot, websocket

    def validate_depth_config(self) -> tuple[bool, str]:
        """
        验证深度配置的有效性

        Returns:
            (is_valid, message)
        """
        snapshot, websocket = self.get_optimal_depths()

        # 基本验证
        if snapshot <= 0 or websocket <= 0:
            return False, "深度档位必须大于0"

        # 🎯 交易所特定验证（支持新的市场分类架构）
        if self.exchange in [Exchange.BINANCE, Exchange.BINANCE_SPOT, Exchange.BINANCE_DERIVATIVES]:
            if snapshot > 5000:
                return False, "Binance快照深度不能超过5000档"
            if websocket not in [5, 10, 20] and websocket != snapshot:
                return False, f"Binance WebSocket深度建议使用5/10/20档，当前: {websocket}"

        elif self.exchange in [Exchange.OKX, Exchange.OKX_SPOT, Exchange.OKX_DERIVATIVES]:
            if snapshot > 400:
                return False, "OKX快照深度不能超过400档"
            if websocket > 400:
                return False, "OKX WebSocket深度不能超过400档"

        return True, "深度配置有效"

    @classmethod
    def from_config_file(cls, exchange: Exchange, market_type: MarketType = MarketType.SPOT,
                        **overrides) -> "ExchangeConfig":
        """
        从配置文件创建ExchangeConfig实例

        Args:
            exchange: 交易所
            market_type: 市场类型
            **overrides: 覆盖配置

        Returns:
            ExchangeConfig实例
        """
        try:
            from .exchange_config_loader import get_exchange_config_loader

            loader = get_exchange_config_loader()
            defaults = loader.get_exchange_defaults(exchange, market_type)

            # 合并默认配置和覆盖配置
            config_data = {
                'exchange': exchange,
                'market_type': market_type,
                '_config_source': 'config_file'
            }
            config_data.update(defaults)
            config_data.update(overrides)

            # 创建实例
            instance = cls(**config_data)

            # 验证配置
            is_valid, message = loader.validate_config(config_data)
            if not is_valid:
                import structlog
                logger = structlog.get_logger(__name__)
                logger.warning("配置文件验证失败", message=message, exchange=exchange.value)

            return instance

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error("从配置文件加载失败，使用代码默认值", error=str(e))

            # 降级到代码默认值
            return cls(exchange=exchange, market_type=market_type, **overrides)

    @classmethod
    def from_environment(cls, exchange: Exchange, market_type: MarketType = MarketType.SPOT,
                        environment: str = "production", **overrides) -> "ExchangeConfig":
        """
        从环境配置创建ExchangeConfig实例

        Args:
            exchange: 交易所
            market_type: 市场类型
            environment: 环境名称
            **overrides: 覆盖配置

        Returns:
            ExchangeConfig实例
        """
        try:
            from .exchange_config_loader import get_exchange_config_loader

            loader = get_exchange_config_loader()

            # 获取基础配置
            defaults = loader.get_exchange_defaults(exchange, market_type)

            # 获取环境特定配置
            env_config = loader.get_environment_config(environment)

            # 合并配置（优先级：overrides > environment > defaults）
            config_data = {
                'exchange': exchange,
                'market_type': market_type,
                '_config_source': f'environment_{environment}'
            }
            config_data.update(defaults)
            config_data.update(env_config)
            config_data.update(overrides)

            return cls(**config_data)

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error("从环境配置加载失败，使用配置文件默认值", error=str(e))

            # 降级到配置文件
            return cls.from_config_file(exchange, market_type, **overrides)

    @classmethod
    def from_strategy(cls, exchange: Exchange, market_type: MarketType = MarketType.SPOT,
                     strategy_name: str = "default", **overrides) -> "ExchangeConfig":
        """
        从策略配置创建ExchangeConfig实例

        Args:
            exchange: 交易所
            market_type: 市场类型
            strategy_name: 策略名称
            **overrides: 覆盖配置

        Returns:
            ExchangeConfig实例
        """
        try:
            from .strategy_config_manager import get_strategy_config_manager

            strategy_manager = get_strategy_config_manager()

            # 获取策略深度配置
            depth_config = strategy_manager.get_strategy_depth_config(
                strategy_name, exchange, market_type
            )

            # 获取策略性能配置
            performance_config = strategy_manager.get_strategy_performance_config(strategy_name)

            # 构建配置数据
            config_data = {
                'exchange': exchange,
                'market_type': market_type,
                'strategy_name': strategy_name,
                'strategy_priority': depth_config.priority.value,
                'snapshot_depth': depth_config.snapshot_depth,
                'websocket_depth': depth_config.websocket_depth,
                'snapshot_interval': performance_config.snapshot_interval,
                '_config_source': f'strategy_{strategy_name}'
            }
            config_data.update(overrides)

            # 验证策略配置
            is_valid, message = strategy_manager.validate_strategy_config(
                strategy_name, exchange, market_type
            )
            if not is_valid:
                import structlog
                logger = structlog.get_logger(__name__)
                logger.warning("策略配置验证失败", message=message, strategy=strategy_name)

            return cls(**config_data)

        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error("从策略配置加载失败，使用默认配置", error=str(e))

            # 降级到默认策略
            return cls.from_config_file(exchange, market_type, strategy_name="default", **overrides)

    def get_strategy_optimal_depths(self) -> tuple[int, int]:
        """
        获取策略优化的深度配置

        Returns:
            (snapshot_depth, websocket_depth)
        """
        try:
            from .strategy_config_manager import get_strategy_config_manager

            strategy_manager = get_strategy_config_manager()
            depth_config = strategy_manager.get_strategy_depth_config(
                self.strategy_name, self.exchange, self.market_type
            )

            return depth_config.snapshot_depth, depth_config.websocket_depth

        except Exception:
            # 降级到基础优化方法
            return self.get_optimal_depths()

    def validate_strategy_consistency(self) -> tuple[bool, str]:
        """
        验证策略配置的一致性

        Returns:
            (is_valid, message)
        """
        try:
            from .strategy_config_manager import get_strategy_config_manager

            strategy_manager = get_strategy_config_manager()
            return strategy_manager.validate_strategy_config(
                self.strategy_name, self.exchange, self.market_type
            )

        except Exception as e:
            return False, f"策略一致性验证失败: {str(e)}"
    
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

    model_config = ConfigDict(arbitrary_types_allowed=True)
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
        # 🎯 根据市场类型选择正确的Exchange枚举值
        if market_type == MarketType.SPOT:
            exchange_enum = Exchange.BINANCE_SPOT
        else:
            exchange_enum = Exchange.BINANCE_DERIVATIVES

        return cls(
            exchange=exchange_enum,
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
        # 🎯 根据市场类型选择正确的Exchange枚举值
        if market_type == MarketType.SPOT:
            exchange_enum = Exchange.OKX_SPOT
        else:
            exchange_enum = Exchange.OKX_DERIVATIVES

        return cls(
            exchange=exchange_enum,
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
            exchange=Exchange.DERIBIT_DERIVATIVES,
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
    data_points_processed: int = Field(0, description="处理数据点数")
    errors_count: int = Field(0, description="错误数量")
    last_message_time: Optional[datetime] = Field(None, description="最后消息时间")
    uptime_seconds: float = Field(0.0, description="运行时间(秒)")
    
    # 按交易所统计
    exchange_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict, description="交易所统计")

    model_config = ConfigDict(arbitrary_types_allowed=True)


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

    model_config = ConfigDict(arbitrary_types_allowed=True)


class NormalizedTopTraderLongShortRatio(BaseModel):
    """大户持仓比数据 - 标准化的大户多空持仓比例信息"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称，如 BTC-USDT")
    currency: str = Field(..., description="币种名称，如 BTC")

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

    # 数据质量指标
    data_quality_score: Optional[Decimal] = Field(None, description="数据质量评分 (0-1)")
    ratio_sum_check: Optional[bool] = Field(None, description="多空比例和检查 (应约等于1)")

    # 时间戳
    timestamp: datetime = Field(..., description="数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __hash__(self):
        return hash((self.exchange_name, self.symbol_name, self.timestamp))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于存储和传输"""
        return {
            "exchange_name": self.exchange_name,
            "symbol_name": self.symbol_name,
            "currency": self.currency,
            "long_short_ratio": float(self.long_short_ratio),
            "long_position_ratio": float(self.long_position_ratio),
            "short_position_ratio": float(self.short_position_ratio),
            "long_account_ratio": float(self.long_account_ratio) if self.long_account_ratio else None,
            "short_account_ratio": float(self.short_account_ratio) if self.short_account_ratio else None,
            "long_short_account_ratio": float(self.long_short_account_ratio) if self.long_short_account_ratio else None,
            "data_type": self.data_type,
            "period": self.period,
            "instrument_type": self.instrument_type,
            "data_quality_score": float(self.data_quality_score) if self.data_quality_score else None,
            "ratio_sum_check": self.ratio_sum_check,
            "timestamp": self.timestamp.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "raw_data": self.raw_data
        }


class NormalizedMarketLongShortRatio(BaseModel):
    """市场多空人数比数据 - 标准化的整体市场用户多空人数比例信息"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称，如 BTC-USDT")
    currency: str = Field(..., description="币种名称，如 BTC")

    # 核心人数比数据
    long_short_ratio: Decimal = Field(..., description="多空人数比值")
    long_account_ratio: Optional[Decimal] = Field(None, description="多仓人数比例 (0-1之间)")
    short_account_ratio: Optional[Decimal] = Field(None, description="空仓人数比例 (0-1之间)")

    # 元数据
    data_type: str = Field("account", description="数据类型: account(人数)")
    period: Optional[str] = Field(None, description="时间周期，如 5m, 15m, 1h")
    instrument_type: str = Field("futures", description="合约类型: futures, swap, perpetual")

    # 数据质量指标
    data_quality_score: Optional[Decimal] = Field(None, description="数据质量评分 (0-1)")
    ratio_sum_check: Optional[bool] = Field(None, description="多空比例和检查 (应约等于1)")

    # 时间戳
    timestamp: datetime = Field(..., description="数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __hash__(self):
        return hash((self.exchange_name, self.symbol_name, self.timestamp))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于存储和传输"""
        return {
            "exchange_name": self.exchange_name,
            "symbol_name": self.symbol_name,
            "currency": self.currency,
            "long_short_ratio": float(self.long_short_ratio),
            "long_account_ratio": float(self.long_account_ratio) if self.long_account_ratio else None,
            "short_account_ratio": float(self.short_account_ratio) if self.short_account_ratio else None,
            "data_type": self.data_type,
            "period": self.period,
            "instrument_type": self.instrument_type,
            "data_quality_score": float(self.data_quality_score) if self.data_quality_score else None,
            "ratio_sum_check": self.ratio_sum_check,
            "timestamp": self.timestamp.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "raw_data": self.raw_data
        }





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

    model_config = ConfigDict(arbitrary_types_allowed=True)


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

    model_config = ConfigDict(arbitrary_types_allowed=True)


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

    model_config = ConfigDict(arbitrary_types_allowed=True)





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

    model_config = ConfigDict(arbitrary_types_allowed=True)


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

    model_config = ConfigDict(arbitrary_types_allowed=True)


class LiquidationSide(str, Enum):
    """强平订单方向"""
    BUY = "buy"
    SELL = "sell"


class LiquidationStatus(str, Enum):
    """强平订单状态"""
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    PENDING = "pending"


class ProductType(str, Enum):
    """产品类型 - 用于区分不同的交易产品"""
    SPOT = "spot"              # 现货
    MARGIN = "margin"          # 杠杆交易
    PERPETUAL = "perpetual"    # 永续合约
    FUTURES = "futures"        # 交割合约
    OPTION = "option"          # 期权

    # 向后兼容别名
    SWAP = "perpetual"         # 映射到PERPETUAL，保持向后兼容


class NormalizedLiquidation(BaseModel):
    """标准化的强平订单数据"""
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称 (标准格式: BTC-USDT)")

    # 产品信息
    product_type: ProductType = Field(..., description="产品类型")
    instrument_id: str = Field(..., description="产品ID")

    # 强平订单信息
    liquidation_id: str = Field(..., description="强平订单ID")
    side: LiquidationSide = Field(..., description="强平方向")
    status: LiquidationStatus = Field(..., description="强平状态")

    # 价格和数量信息
    price: Decimal = Field(..., description="强平价格")
    quantity: Decimal = Field(..., description="强平数量")
    filled_quantity: Decimal = Field(default=Decimal("0"), description="已成交数量")
    average_price: Optional[Decimal] = Field(None, description="平均成交价格")

    # 金额信息
    notional_value: Decimal = Field(..., description="名义价值 (价格 × 数量)")

    # 时间信息
    liquidation_time: datetime = Field(..., description="强平时间")
    timestamp: datetime = Field(..., description="数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    # 扩展信息
    margin_ratio: Optional[Decimal] = Field(None, description="保证金率")
    bankruptcy_price: Optional[Decimal] = Field(None, description="破产价格")

    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __post_init__(self):
        """数据验证和计算"""
        # 计算名义价值
        if self.notional_value is None:
            self.notional_value = self.price * self.quantity


class NormalizedOpenInterest(BaseModel):
    """持仓量数据 - 永续合约和期货的未平仓合约数量"""

    # 基础信息
    exchange_name: str = Field(..., description="交易所名称")
    symbol_name: str = Field(..., description="交易对名称 (标准格式: BTC-USDT)")
    product_type: str = Field(..., description="产品类型: swap/futures")
    instrument_id: str = Field(..., description="产品ID")

    # 持仓量信息
    open_interest_value: Decimal = Field(..., description="持仓量数值 (合约张数或币数)")
    open_interest_usd: Optional[Decimal] = Field(None, description="持仓量USD价值")
    open_interest_unit: str = Field(default="contracts", description="持仓量单位: contracts/coins/usd")

    # 价格信息 (用于计算USD价值)
    mark_price: Optional[Decimal] = Field(None, description="标记价格")
    index_price: Optional[Decimal] = Field(None, description="指数价格")

    # 时间信息
    timestamp: datetime = Field(..., description="数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")

    # 统计信息
    change_24h: Optional[Decimal] = Field(None, description="24小时变化量")
    change_24h_percent: Optional[Decimal] = Field(None, description="24小时变化百分比")

    # 原始数据
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __post_init__(self):
        """数据验证和计算"""
        # 如果有标记价格但没有USD价值，尝试计算
        if self.mark_price and not self.open_interest_usd and self.open_interest_unit == "contracts":
            # 对于合约，通常需要合约规格来计算，这里做简化处理
            # 实际实现中需要根据具体交易所的合约规格来计算
            pass

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "exchange_name": self.exchange_name,
            "symbol_name": self.symbol_name,
            "product_type": self.product_type,
            "instrument_id": self.instrument_id,
            "open_interest_value": float(self.open_interest_value),
            "open_interest_usd": float(self.open_interest_usd) if self.open_interest_usd else None,
            "open_interest_unit": self.open_interest_unit,
            "mark_price": float(self.mark_price) if self.mark_price else None,
            "index_price": float(self.index_price) if self.index_price else None,
            "timestamp": self.timestamp.isoformat(),
            "collected_at": self.collected_at.isoformat(),
            "change_24h": float(self.change_24h) if self.change_24h else None,
            "change_24h_percent": float(self.change_24h_percent) if self.change_24h_percent else None,
            "raw_data": self.raw_data
        }


class NormalizedVolatilityIndex(BaseModel):
    """标准化的波动率指数数据"""
    # 基础信息
    exchange_name: str = Field(..., description="交易所名称")
    currency: str = Field(..., description="基础货币 (BTC, ETH)")
    symbol_name: str = Field(..., description="交易对符号 (如: BTC-USDC, ETH-USDC)")
    index_name: str = Field(..., description="指数名称 (如: BTCDVOL_USDC-DERIBIT-INDEX)")
    market_type: str = Field(..., description="市场类型 (options, perpetual, futures, spot)")

    # 核心数据
    volatility_value: Decimal = Field(..., description="波动率指数值 (小数形式, 0.85 = 85%)")
    timestamp: datetime = Field(..., description="数据时间戳")

    # 扩展信息
    resolution: Optional[str] = Field(None, description="数据分辨率 (1m, 5m, 1h, 1d)")
    market_session: Optional[str] = Field(None, description="市场时段")
    data_quality_score: Optional[Decimal] = Field(None, description="数据质量评分 (0-1)")

    # 元数据
    source_timestamp: Optional[datetime] = Field(None, description="原始数据时间戳")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="采集时间")
    raw_data: Optional[Dict[str, Any]] = Field(None, description="原始数据")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于存储和传输"""
        return {
            "exchange_name": self.exchange_name,
            "currency": self.currency,
            "index_name": self.index_name,
            "volatility_value": float(self.volatility_value),
            "timestamp": self.timestamp.isoformat(),
            "resolution": self.resolution,
            "market_session": self.market_session,
            "data_quality_score": float(self.data_quality_score) if self.data_quality_score else None,
            "source_timestamp": self.source_timestamp.isoformat() if self.source_timestamp else None,
            "collected_at": self.collected_at.isoformat(),
            "raw_data": self.raw_data
        }


# 订单簿状态管理类
from dataclasses import dataclass, field
from collections import deque


@dataclass
class OrderBookSnapshot:
    """订单簿快照"""
    symbol: str
    exchange: str
    last_update_id: int
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: datetime
    checksum: Optional[int] = None


@dataclass
class OrderBookUpdate:
    """订单簿增量更新"""
    symbol: str
    exchange: str
    first_update_id: int
    last_update_id: int
    bids: List[PriceLevel]
    asks: List[PriceLevel]
    timestamp: datetime
    prev_update_id: Optional[int] = None


@dataclass
class OrderBookState:
    """订单簿状态管理"""
    symbol: str
    exchange: str
    local_orderbook: Optional['EnhancedOrderBook'] = None
    update_buffer: deque = field(default_factory=deque)
    last_update_id: int = 0
    last_snapshot_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_update_time: Optional[datetime] = None  # 最后更新时间，用于内存清理
    is_synced: bool = False
    error_count: int = 0
    total_updates: int = 0

    # 新增：Binance官方同步算法需要的字段
    first_update_id: Optional[int] = None  # 第一个收到的更新的U值
    snapshot_last_update_id: Optional[int] = None  # 快照的lastUpdateId
    sync_in_progress: bool = False  # 是否正在同步中

    def __post_init__(self):
        if not self.update_buffer:
            self.update_buffer = deque(maxlen=1000)  # 限制缓冲区大小


@dataclass
class NormalizedLSRTopPosition:
    """标准化顶级大户多空持仓比例数据（按持仓量计算）"""
    exchange_name: str                    # 交易所名称 (okx_derivatives / binance_derivatives)
    symbol_name: str                     # 统一格式交易对名称 (BTC-USDT)
    product_type: ProductType            # 产品类型 (perpetual)
    instrument_id: str                   # 原始交易对ID
    timestamp: datetime                  # 数据时间戳
    long_short_ratio: Decimal           # 多空持仓比例 (多仓/空仓)
    long_position_ratio: Decimal        # 多仓持仓比例 (多仓/总持仓)
    short_position_ratio: Decimal       # 空仓持仓比例 (空仓/总持仓)
    period: str                         # 数据周期 (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
    raw_data: Dict[str, Any]            # 原始数据


@dataclass
class NormalizedLSRAllAccount:
    """标准化全市场多空持仓人数比例数据（按账户数计算）"""
    exchange_name: str                    # 交易所名称 (okx_derivatives / binance_derivatives)
    symbol_name: str                     # 统一格式交易对名称 (BTC-USDT)
    product_type: ProductType            # 产品类型 (perpetual)
    instrument_id: str                   # 原始交易对ID
    timestamp: datetime                  # 数据时间戳
    long_short_ratio: Decimal           # 多空账户比例 (多仓账户/空仓账户)
    long_account_ratio: Decimal         # 多仓账户比例 (多仓账户/总账户)
    short_account_ratio: Decimal        # 空仓账户比例 (空仓账户/总账户)
    period: str                         # 数据周期 (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)
    raw_data: Dict[str, Any]            # 原始数据