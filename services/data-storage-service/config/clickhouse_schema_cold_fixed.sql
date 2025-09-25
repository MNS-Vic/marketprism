-- 冷端表结构（毫秒精度，统一与写入代码一致）
CREATE DATABASE IF NOT EXISTS marketprism_cold;

-- orderbooks
CREATE TABLE IF NOT EXISTS marketprism_cold.orderbooks (
    timestamp          DateTime64(3, 'UTC'),
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
    created_at         DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;

-- trades（与迁移SQL列一致）
CREATE TABLE IF NOT EXISTS marketprism_cold.trades (
    timestamp          DateTime64(3, 'UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    trade_id           String,
    price              Float64,
    quantity           Float64,
    side               String,
    is_maker           UInt8,
    trade_time         DateTime64(3, 'UTC'),
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;

-- funding_rates
CREATE TABLE IF NOT EXISTS marketprism_cold.funding_rates (
    timestamp          DateTime64(3, 'UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    funding_rate       Float64,
    funding_time       DateTime64(3, 'UTC'),
    next_funding_time  DateTime64(3, 'UTC'),
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;

-- open_interests
CREATE TABLE IF NOT EXISTS marketprism_cold.open_interests (
    timestamp          DateTime64(3, 'UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    open_interest      Float64,
    open_interest_value Float64,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;

-- liquidations
CREATE TABLE IF NOT EXISTS marketprism_cold.liquidations (
    timestamp          DateTime64(3, 'UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    side               String,
    price              Float64,
    quantity           Float64,
    liquidation_time   DateTime64(3, 'UTC'),
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;

-- lsr_top_positions
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_top_positions (
    timestamp              DateTime64(3, 'UTC'),
    exchange               String,
    market_type            String,
    symbol                 String,
    long_position_ratio    Float64,
    short_position_ratio   Float64,
    period                 String,
    data_source            String DEFAULT 'marketprism',
    created_at             DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;

-- lsr_all_accounts
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_all_accounts (
    timestamp              DateTime64(3, 'UTC'),
    exchange               String,
    market_type            String,
    symbol                 String,
    long_account_ratio     Float64,
    short_account_ratio    Float64,
    period                 String,
    data_source            String DEFAULT 'marketprism',
    created_at             DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;

-- volatility_indices
CREATE TABLE IF NOT EXISTS marketprism_cold.volatility_indices (
    timestamp          DateTime64(3, 'UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    volatility_index   Float64,
    underlying_asset   String,
    reserved           Nullable(String),
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY;
