-- MarketPrism 统一ClickHouse Schema
-- 所有timestamp字段统一为DateTime64(3, 'UTC')格式

-- 未平仓量数据表
CREATE TABLE IF NOT EXISTS open_interests (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    open_interest Float64 CODEC(ZSTD),
    open_interest_value Float64 CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- 资金费率数据表
CREATE TABLE IF NOT EXISTS funding_rates (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    funding_rate Float64 CODEC(ZSTD),
    funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    next_funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- 清算数据表
CREATE TABLE IF NOT EXISTS liquidations (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    price Float64 CODEC(ZSTD),
    quantity Float64 CODEC(ZSTD),
    liquidation_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- LSR大户持仓比例数据表
CREATE TABLE IF NOT EXISTS lsr_top_positions (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    period LowCardinality(String) CODEC(ZSTD),
    long_ratio Float64 CODEC(ZSTD),
    short_ratio Float64 CODEC(ZSTD),
    -- 🔧 修复：添加LSR Top Position必需的列
    long_position_ratio Float64 CODEC(ZSTD),
    short_position_ratio Float64 CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- LSR全账户持仓比例数据表
CREATE TABLE IF NOT EXISTS lsr_all_accounts (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    period LowCardinality(String) CODEC(ZSTD),
    long_ratio Float64 CODEC(ZSTD),
    short_ratio Float64 CODEC(ZSTD),
    -- 🔧 修复：添加LSR All Account必需的列
    long_account_ratio Float64 CODEC(ZSTD),
    short_account_ratio Float64 CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- 波动率指数数据表
CREATE TABLE IF NOT EXISTS volatility_indices (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    volatility_index Float64 CODEC(ZSTD),
    index_value Float64 CODEC(ZSTD),
    underlying_asset LowCardinality(String) CODEC(ZSTD),
    maturity_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;
