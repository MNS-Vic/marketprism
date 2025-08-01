-- MarketPrism ClickHouse 优化表结构
-- 为7种金融数据类型设计的高性能表结构

-- 创建数据库
CREATE DATABASE IF NOT EXISTS marketprism_hot;
CREATE DATABASE IF NOT EXISTS marketprism_cold;

-- 使用热端数据库
USE marketprism_hot;

-- ==================== 1. 订单簿数据表 ====================
CREATE TABLE IF NOT EXISTS orderbooks (
    -- 基础字段
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    
    -- 订单簿特定字段
    last_update_id UInt64 CODEC(Delta, ZSTD),
    bids_count UInt32 CODEC(Delta, ZSTD),
    asks_count UInt32 CODEC(Delta, ZSTD),
    
    -- 最优买卖价（用于快速查询）
    best_bid_price Decimal64(8) CODEC(ZSTD),
    best_ask_price Decimal64(8) CODEC(ZSTD),
    best_bid_quantity Decimal64(8) CODEC(ZSTD),
    best_ask_quantity Decimal64(8) CODEC(ZSTD),
    
    -- 深度数据（JSON格式存储完整深度）
    bids String CODEC(ZSTD),
    asks String CODEC(ZSTD),
    
    -- 元数据
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, last_update_id)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 2. 交易数据表 ====================
CREATE TABLE IF NOT EXISTS trades (
    -- 基础字段
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    
    -- 交易特定字段
    trade_id String CODEC(ZSTD),
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD), -- 'buy' or 'sell'
    
    -- 扩展字段
    is_maker Bool DEFAULT false CODEC(ZSTD),
    trade_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    
    -- 元数据
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, trade_id)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 3. 资金费率数据表 ====================
CREATE TABLE IF NOT EXISTS funding_rates (
    -- 基础字段
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    
    -- 资金费率特定字段
    funding_rate Decimal64(8) CODEC(ZSTD),
    funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    next_funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    
    -- 扩展字段
    mark_price Decimal64(8) CODEC(ZSTD),
    index_price Decimal64(8) CODEC(ZSTD),
    
    -- 元数据
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 4. 未平仓量数据表 ====================
CREATE TABLE IF NOT EXISTS open_interests (
    -- 基础字段
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    
    -- 未平仓量特定字段
    open_interest Decimal64(8) CODEC(ZSTD),
    open_interest_value Decimal64(8) CODEC(ZSTD),
    
    -- 扩展字段
    count UInt64 CODEC(Delta, ZSTD),
    
    -- 元数据
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 5. 强平数据表 ====================
CREATE TABLE IF NOT EXISTS liquidations (
    -- 基础字段
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    
    -- 强平特定字段
    side LowCardinality(String) CODEC(ZSTD), -- 'buy' or 'sell'
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    
    -- 扩展字段
    liquidation_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    
    -- 元数据
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 6. 多空持仓比例数据表 ====================
CREATE TABLE IF NOT EXISTS lsrs (
    -- 基础字段
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    
    -- LSR特定字段
    long_short_ratio Decimal64(8) CODEC(ZSTD),
    long_account Decimal64(8) CODEC(ZSTD),
    short_account Decimal64(8) CODEC(ZSTD),
    
    -- 扩展字段
    period LowCardinality(String) CODEC(ZSTD), -- '5m', '15m', '30m', '1h', '4h', '1d'
    
    -- 元数据
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 7. 波动率指数数据表 ====================
CREATE TABLE IF NOT EXISTS volatility_indices (
    -- 基础字段
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),

    -- 波动率指数特定字段
    index_value Decimal64(8) CODEC(ZSTD),

    -- 扩展字段
    underlying_asset LowCardinality(String) CODEC(ZSTD),
    maturity_date Date CODEC(ZSTD),

    -- 元数据
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 创建冷端数据库表结构 ====================
-- 切换到冷端数据库
USE marketprism_cold;

-- 冷端表结构与热端相同，但TTL更长
CREATE TABLE IF NOT EXISTS orderbooks AS marketprism_hot.orderbooks
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, last_update_id)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS trades AS marketprism_hot.trades
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, trade_id)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS funding_rates AS marketprism_hot.funding_rates
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS open_interests AS marketprism_hot.open_interests
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS liquidations AS marketprism_hot.liquidations
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS lsrs AS marketprism_hot.lsrs
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS volatility_indices AS marketprism_hot.volatility_indices
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 365 DAY DELETE
SETTINGS index_granularity = 8192;

-- ==================== 创建查询优化索引 ====================
-- 为热端数据库创建跳数索引以优化查询性能

USE marketprism_hot;

-- 为订单簿表创建价格范围索引
ALTER TABLE orderbooks ADD INDEX idx_price_range (best_bid_price, best_ask_price) TYPE minmax GRANULARITY 4;

-- 为交易表创建价格和数量索引
ALTER TABLE trades ADD INDEX idx_price_quantity (price, quantity) TYPE minmax GRANULARITY 4;
ALTER TABLE trades ADD INDEX idx_trade_time (trade_time) TYPE minmax GRANULARITY 4;

-- 为资金费率表创建费率索引
ALTER TABLE funding_rates ADD INDEX idx_funding_rate (funding_rate) TYPE minmax GRANULARITY 4;

-- 为未平仓量表创建数量索引
ALTER TABLE open_interests ADD INDEX idx_open_interest (open_interest) TYPE minmax GRANULARITY 4;

-- 为强平表创建价格索引
ALTER TABLE liquidations ADD INDEX idx_liquidation_price (price) TYPE minmax GRANULARITY 4;

-- 为LSR表创建比例索引
ALTER TABLE lsrs ADD INDEX idx_lsr_ratio (long_short_ratio) TYPE minmax GRANULARITY 4;

-- 为波动率指数表创建指数值索引
ALTER TABLE volatility_indices ADD INDEX idx_volatility_value (index_value) TYPE minmax GRANULARITY 4;
