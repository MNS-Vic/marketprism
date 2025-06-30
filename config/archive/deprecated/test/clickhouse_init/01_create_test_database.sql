-- 创建数据库
CREATE DATABASE IF NOT EXISTS marketprism;
CREATE DATABASE IF NOT EXISTS marketprism_test;
CREATE DATABASE IF NOT EXISTS marketprism_cold;

-- 使用主数据库
USE marketprism;

-- 创建交易数据表
CREATE TABLE IF NOT EXISTS trades (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    trade_id String,
    price Float64,
    quantity Float64,
    side LowCardinality(String),
    trade_time DateTime,
    receive_time DateTime,
    is_best_match Bool DEFAULT true
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, trade_time);

-- 创建深度数据表
CREATE TABLE IF NOT EXISTS depth (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    update_id UInt64,
    bids String,
    asks String,
    time DateTime,
    receive_time DateTime
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, time);

-- 创建资金费率表
CREATE TABLE IF NOT EXISTS funding_rate (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    rate Float64,
    time DateTime,
    receive_time DateTime
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, time);

-- 创建未平仓合约表
CREATE TABLE IF NOT EXISTS open_interest (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    open_interest Float64,
    time DateTime,
    receive_time DateTime
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, time);

-- 创建交易聚合表
CREATE TABLE IF NOT EXISTS trade_aggregations (
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    interval_type LowCardinality(String),
    interval_start DateTime,
    open_price Float64,
    high_price Float64,
    low_price Float64,
    close_price Float64,
    volume Float64,
    vwap Float64,
    trade_count UInt32,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, interval_type, interval_start);

-- 在冷存储中创建相同的表
USE marketprism_cold;

CREATE TABLE IF NOT EXISTS trades (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    trade_id String,
    price Float64,
    quantity Float64,
    side LowCardinality(String),
    trade_time DateTime,
    receive_time DateTime,
    is_best_match Bool DEFAULT true
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, trade_time);

CREATE TABLE IF NOT EXISTS depth (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    update_id UInt64,
    bids String,
    asks String,
    time DateTime,
    receive_time DateTime
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, time);

-- 使用测试数据库
USE marketprism_test;

-- 创建交易数据表
CREATE TABLE IF NOT EXISTS trades (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    trade_id String,
    price Float64,
    quantity Float64,
    side LowCardinality(String),
    trade_time DateTime,
    receive_time DateTime,
    is_best_match Bool DEFAULT true
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, trade_time);

-- 创建深度数据表
CREATE TABLE IF NOT EXISTS depth (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    update_id UInt64,
    bids String,
    asks String,
    time DateTime,
    receive_time DateTime
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, time); 