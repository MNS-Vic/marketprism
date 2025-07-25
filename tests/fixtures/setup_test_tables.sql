-- MarketPrism测试表结构初始化脚本

-- 创建测试数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS market_test;

-- 切换到测试数据库
USE market_test;

-- 创建交易数据测试表
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
ORDER BY (symbol, exchange, timestamp);

-- 创建订单簿数据测试表
CREATE TABLE IF NOT EXISTS market_orderbooks (
    symbol String,
    timestamp UInt64,
    exchange String,
    bids String,  -- JSON格式的订单簿买单数据
    asks String,  -- JSON格式的订单簿卖单数据
    received_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (symbol, exchange, timestamp);

-- 创建市场概况测试表
CREATE TABLE IF NOT EXISTS market_summary (
    symbol String,
    exchange String,
    avg_price Float64,
    volume_24h Float64,
    high_24h Float64,
    low_24h Float64,
    last_update UInt64,
    update_time DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (symbol, exchange, last_update);

-- 创建测试分区表
CREATE TABLE IF NOT EXISTS market_trades_partitioned (
    symbol String,
    price Float64,
    volume Float64,
    timestamp UInt64,
    exchange String,
    trade_id String,
    side String,
    date Date DEFAULT toDate(timestamp / 1000),
    received_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (symbol, exchange, timestamp);

-- 创建测试用户
CREATE USER IF NOT EXISTS test_user IDENTIFIED BY 'test_password';

-- 授权
GRANT SELECT, INSERT, CREATE, DROP ON market_test.* TO test_user;

-- 创建一些测试数据
INSERT INTO market_trades (symbol, price, volume, timestamp, exchange, trade_id, side) VALUES
('BTC-USDT', 45000.50, 1.234, 1620000000000, 'binance', 'test_trade_1', 'buy'),
('ETH-USDT', 3200.75, 5.678, 1620000010000, 'okex', 'test_trade_2', 'sell'),
('SOL-USDT', 120.25, 100.0, 1620000020000, 'deribit', 'test_trade_3', 'buy');

-- 创建测试订单簿数据
INSERT INTO market_orderbooks (symbol, timestamp, exchange, bids, asks) VALUES
('BTC-USDT', 1620000000000, 'binance', 
 '[[45000.0, 1.0], [44999.0, 2.0]]', 
 '[[45001.0, 1.0], [45002.0, 2.0]]'),
('ETH-USDT', 1620000010000, 'okex', 
 '[[3200.0, 5.0], [3199.0, 10.0]]', 
 '[[3201.0, 5.0], [3202.0, 10.0]]');

-- 创建测试市场概况数据
INSERT INTO market_summary (symbol, exchange, avg_price, volume_24h, high_24h, low_24h, last_update) VALUES
('BTC-USDT', 'binance', 45000.0, 1000.0, 46000.0, 44000.0, 1620000000000),
('ETH-USDT', 'okex', 3200.0, 2000.0, 3300.0, 3100.0, 1620000010000);