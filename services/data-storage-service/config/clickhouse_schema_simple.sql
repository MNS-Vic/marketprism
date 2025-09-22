-- MarketPrism ClickHouse 简化表结构 (兼容版本)
-- 为8种金融数据类型设计的基础表结构

-- ==================== 1. 订单簿数据表 ====================
CREATE TABLE IF NOT EXISTS orderbooks (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    last_update_id UInt64,
    bids_count UInt32,
    asks_count UInt32,
    best_bid_price Float64,
    best_ask_price Float64,
    best_bid_quantity Float64,
    best_ask_quantity Float64,
    bids String,
    asks String,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY;

-- ==================== 2. 交易数据表 ====================
CREATE TABLE IF NOT EXISTS trades (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    trade_id String,
    price Float64,
    quantity Float64,
    side String,
    is_maker UInt8,
    trade_time DateTime,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY;

-- ==================== 3. 资金费率数据表 ====================
CREATE TABLE IF NOT EXISTS funding_rates (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    funding_rate Float64,
    funding_time DateTime,
    next_funding_time DateTime,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 7 DAY;

-- ==================== 4. 未平仓量数据表 ====================
CREATE TABLE IF NOT EXISTS open_interests (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    open_interest Float64,
    open_interest_value Float64,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 7 DAY;

-- ==================== 5. 强平数据表 ====================
CREATE TABLE IF NOT EXISTS liquidations (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    side String,
    price Float64,
    quantity Float64,
    liquidation_time DateTime,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 7 DAY;

-- ==================== 6. 顶级大户多空持仓比例数据表 ====================
CREATE TABLE IF NOT EXISTS lsr_top_positions (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    long_short_ratio Float64,
    long_account Float64,
    short_account Float64,
    long_position_ratio Float64,
    short_position_ratio Float64,
    period String,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 30 DAY;

-- ==================== 7. 全市场多空持仓人数比例数据表 ====================
CREATE TABLE IF NOT EXISTS lsr_all_accounts (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    long_short_ratio Float64,
    long_account Float64,
    short_account Float64,
    long_account_ratio Float64,
    short_account_ratio Float64,
    period String,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 30 DAY;

-- ==================== 8. 波动率指数数据表 ====================
CREATE TABLE IF NOT EXISTS volatility_indices (
    timestamp DateTime,
    exchange String,
    market_type String,
    symbol String,
    volatility_index Float64,
    data_source String DEFAULT 'marketprism',
    created_at DateTime DEFAULT now()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 30 DAY;
