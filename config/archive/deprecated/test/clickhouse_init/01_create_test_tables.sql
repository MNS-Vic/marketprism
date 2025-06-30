-- 创建测试数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS marketprism_test;

-- 使用测试数据库
USE marketprism_test;

-- 创建交易数据表
CREATE TABLE IF NOT EXISTS market_trades (
    symbol String,
    price Float64,
    volume Float64,
    timestamp UInt64,
    exchange String,
    trade_id String,
    side String,
    received_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp);

-- 创建订单簿数据表
CREATE TABLE IF NOT EXISTS market_orderbooks (
    symbol String,
    timestamp UInt64,
    exchange String,
    asks String,  -- JSON格式的卖单数据
    bids String,  -- JSON格式的买单数据
    received_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp);

-- 创建K线数据表
CREATE TABLE IF NOT EXISTS market_klines (
    symbol String,
    timeframe String,  -- 1m, 5m, 15m, 1h, 4h, 1d
    timestamp UInt64,
    exchange String,
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume Float64,
    received_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timeframe, timestamp);

-- 创建资金费率数据表
CREATE TABLE IF NOT EXISTS market_funding_rates (
    symbol String,
    timestamp UInt64,
    exchange String,
    funding_rate Float64,
    next_funding_time UInt64,
    received_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp); 