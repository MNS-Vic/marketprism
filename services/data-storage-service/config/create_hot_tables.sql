-- MarketPrism ClickHouse 热存储表结构
-- 🔄 Docker部署简化改造 (2025-08-02)
-- 支持8种数据类型的优化表结构

-- 1. 订单簿数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.orderbooks (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    last_update_id UInt64 CODEC(Delta, ZSTD),
    bids_count UInt32 CODEC(Delta, ZSTD),
    asks_count UInt32 CODEC(Delta, ZSTD),
    best_bid_price Decimal64(8) CODEC(ZSTD),
    best_ask_price Decimal64(8) CODEC(ZSTD),
    best_bid_quantity Decimal64(8) CODEC(ZSTD),
    best_ask_quantity Decimal64(8) CODEC(ZSTD),
    bids String CODEC(ZSTD),
    asks String CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, last_update_id)
SETTINGS index_granularity = 8192;

-- 2. 交易数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.trades (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    trade_id String CODEC(ZSTD),
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    is_maker Bool DEFAULT false CODEC(ZSTD),
    trade_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, trade_id)
SETTINGS index_granularity = 8192;

-- 3. 资金费率数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.funding_rates (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    funding_rate Decimal64(8) CODEC(ZSTD),
    funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    next_funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    mark_price Decimal64(8) CODEC(ZSTD),
    index_price Decimal64(8) CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192;

-- 4. 未平仓量数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.open_interests (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    open_interest Decimal64(8) CODEC(ZSTD),
    open_interest_value Decimal64(8) CODEC(ZSTD),
    count UInt64 CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192;

-- 5. 强平数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.liquidations (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    liquidation_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192;

-- 6. LSR顶级持仓比例数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.lsr_top_positions (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    long_position_ratio Decimal64(8) CODEC(ZSTD),
    short_position_ratio Decimal64(8) CODEC(ZSTD),
    period LowCardinality(String) DEFAULT '5m' CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
SETTINGS index_granularity = 8192;

-- 7. LSR全账户比例数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.lsr_all_accounts (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    long_account_ratio Decimal64(8) CODEC(ZSTD),
    short_account_ratio Decimal64(8) CODEC(ZSTD),
    period LowCardinality(String) DEFAULT '5m' CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
SETTINGS index_granularity = 8192;

-- 8. 波动率指数数据表
CREATE TABLE IF NOT EXISTS marketprism_hot.volatility_indices (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    index_value Decimal64(8) CODEC(ZSTD),
    underlying_asset LowCardinality(String) CODEC(ZSTD),
    maturity_date Date CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192
