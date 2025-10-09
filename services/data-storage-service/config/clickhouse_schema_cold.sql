-- MarketPrism 冷端 ClickHouse 表结构
-- 冷端用于长期存储，采取更激进的压缩与更长TTL

CREATE DATABASE IF NOT EXISTS marketprism_cold;

-- 通用引擎参数
-- 使用 ZSTD 压缩，固定分区按天，主键与排序键与热端一致，TTL 更长（365 天）

-- 1. 订单簿数据表（结构与热端一致，仅 TTL 调整为 365 天）
CREATE TABLE IF NOT EXISTS marketprism_cold.orderbooks (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- 2. 交易数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.trades (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- 3. 资金费率数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.funding_rates (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- 4. 未平仓量数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.open_interests (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- 5. 强平数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.liquidations (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- 6. LSR顶级持仓比例数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_top_positions (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- 7. LSR全账户比例数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_all_accounts (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- 8. 波动率指数数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.volatility_indices (
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
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

