-- MarketPrism 冷端数据库表结构（与热端完全匹配）
-- 用于长期存储，TTL=365天，高压缩比

-- 创建冷端数据库
CREATE DATABASE IF NOT EXISTS marketprism_cold;

-- 订单簿数据
CREATE TABLE IF NOT EXISTS marketprism_cold.orderbooks (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    last_update_id     UInt64,
    bids_count         UInt32,
    asks_count         UInt32,
    best_bid_price     Float64,
    best_ask_price     Float64,
    best_bid_quantity  Float64,
    best_ask_quantity  Float64,
    bids               String,
    asks               String,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- 交易数据
CREATE TABLE IF NOT EXISTS marketprism_cold.trades (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    trade_id           String,
    price              Float64,
    quantity           Float64,
    side               String,
    is_buyer_maker     UInt8,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- 资金费率
CREATE TABLE IF NOT EXISTS marketprism_cold.funding_rates (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    funding_rate       Float64,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- 未平仓量
CREATE TABLE IF NOT EXISTS marketprism_cold.open_interests (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    open_interest      Float64,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- 强平数据
CREATE TABLE IF NOT EXISTS marketprism_cold.liquidations (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    side               String,
    quantity           Float64,
    price              Float64,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- LSR顶级持仓
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_top_positions (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    long_short_ratio   Float64,
    long_account       Float64,
    short_account      Float64,
    long_position_ratio Float64,
    short_position_ratio Float64,
    period             String,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- LSR全账户
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_all_accounts (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    long_short_ratio   Float64,
    long_account       Float64,
    short_account      Float64,
    long_account_ratio Float64,
    short_account_ratio Float64,
    period             String,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- 波动率指数
CREATE TABLE IF NOT EXISTS marketprism_cold.volatility_indices (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    volatility_index   Float64,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;
