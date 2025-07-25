-- MarketPrism 多交易所数据表扩展

-- 1. 期权隐含波动率表
CREATE TABLE IF NOT EXISTS marketprism.implied_volatility (
    symbol String,
    expiry_date DateTime,
    strike_price Float64,
    call_iv Float64,
    put_iv Float64,
    timestamp DateTime,
    source String,
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (symbol, expiry_date, strike_price, timestamp);

-- 2. 精英交易员持仓表
CREATE TABLE IF NOT EXISTS marketprism.okex_elite_traders (
    symbol String,
    long_account_num UInt32,
    short_account_num UInt32,
    long_short_ratio Float64,
    long_account Float64,
    short_account Float64,
    timestamp DateTime,
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (symbol, timestamp);

-- 3. 多空持仓比率表 (所有交易所统一)
CREATE TABLE IF NOT EXISTS marketprism.long_short_ratio (
    symbol String,
    long_ratio Float64,
    short_ratio Float64,
    timestamp DateTime,
    source String,
    period String DEFAULT '1h',
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (symbol, source, timestamp);

-- 4. 强平订单表 (所有交易所统一)
CREATE TABLE IF NOT EXISTS marketprism.liquidations (
    symbol String,
    price Float64,
    quantity Float64,
    side String,
    timestamp DateTime,
    source String,
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (symbol, timestamp);

-- 5. 标记价格和资金费率表
CREATE TABLE IF NOT EXISTS marketprism.mark_price (
    symbol String,
    mark_price Float64,
    index_price Float64,
    funding_rate Float64,
    next_funding_time DateTime,
    timestamp DateTime,
    source String,
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY date
ORDER BY (symbol, timestamp);

-- 创建跨交易所查询视图

-- 1. 交易所间价格差异视图
CREATE VIEW IF NOT EXISTS marketprism.exchange_price_diff AS
SELECT 
    a.timestamp,
    a.symbol,
    a.price as binance_price,
    b.price as okex_price,
    ((a.price - b.price) / a.price) * 100 as price_diff_percent,
    toDate(a.timestamp) as date
FROM 
    (SELECT timestamp, symbol, price 
     FROM marketprism.trades 
     WHERE source = 'binance') a
JOIN 
    (SELECT timestamp, symbol, price 
     FROM marketprism.trades 
     WHERE source = 'okex') b
ON 
    a.symbol = b.symbol
    AND abs(a.timestamp - b.timestamp) < 1 -- 1秒内的交易
ORDER BY 
    a.timestamp DESC;

-- 2. 交易所间多空比对比视图  
CREATE VIEW IF NOT EXISTS marketprism.exchange_ls_ratio_compare AS
SELECT 
    a.timestamp,
    a.symbol,
    a.long_ratio as binance_long_ratio,
    a.short_ratio as binance_short_ratio,
    b.long_ratio as okex_long_ratio,
    b.short_ratio as okex_short_ratio,
    a.long_ratio - b.long_ratio as long_ratio_diff,
    toDate(a.timestamp) as date
FROM 
    (SELECT timestamp, symbol, long_ratio, short_ratio
     FROM marketprism.long_short_ratio 
     WHERE source = 'binance') a
JOIN 
    (SELECT timestamp, symbol, long_ratio, short_ratio
     FROM marketprism.long_short_ratio 
     WHERE source = 'okex') b
ON 
    a.symbol = b.symbol
    AND abs(a.timestamp - b.timestamp) < 3600 -- 1小时内的数据
ORDER BY 
    a.timestamp DESC; 