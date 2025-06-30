-- MarketPrism 统一交易数据表结构
-- 用于存储Binance现货、Binance期货、OKX等多种交易类型的标准化交易数据

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS marketprism;

-- 使用数据库
USE marketprism;

-- 创建主表：统一交易数据
CREATE TABLE IF NOT EXISTS unified_trade_data
(
    -- 基础信息
    exchange_name LowCardinality(String) COMMENT '交易所名称: binance/okx',
    symbol_name String COMMENT '交易对名称 (如: BTC-USDT)',
    currency LowCardinality(String) COMMENT '币种名称 (如: BTC)',
    
    -- 核心交易数据
    trade_id String COMMENT '交易ID',
    price Decimal64(8) COMMENT '成交价格',
    quantity Decimal64(8) COMMENT '成交数量',
    quote_quantity Nullable(Decimal64(8)) COMMENT '成交金额',
    side LowCardinality(String) COMMENT '交易方向: buy/sell',
    
    -- 时间信息
    timestamp DateTime64(3, 'UTC') COMMENT '成交时间',
    event_time Nullable(DateTime64(3, 'UTC')) COMMENT '事件时间',
    
    -- 交易类型和元数据
    trade_type LowCardinality(String) COMMENT '交易类型: spot/futures/swap',
    is_maker Nullable(UInt8) COMMENT '是否为做市方 (1=是, 0=否)',
    is_best_match Nullable(UInt8) COMMENT '是否最佳匹配 (1=是, 0=否)',
    
    -- 归集交易特有字段 (Binance期货)
    agg_trade_id Nullable(String) COMMENT '归集交易ID',
    first_trade_id Nullable(String) COMMENT '首个交易ID',
    last_trade_id Nullable(String) COMMENT '末次交易ID',
    
    -- Binance API扩展字段
    transact_time Nullable(DateTime64(3, 'UTC')) COMMENT '交易时间戳(Binance)',
    order_id Nullable(String) COMMENT '订单ID',
    commission Nullable(Decimal64(8)) COMMENT '手续费',
    commission_asset Nullable(String) COMMENT '手续费资产',
    
    -- TRADE_PREVENTION特性字段
    prevented_quantity Nullable(Decimal64(8)) COMMENT '被阻止执行的数量',
    prevented_price Nullable(Decimal64(8)) COMMENT '被阻止执行的价格',
    prevented_quote_qty Nullable(Decimal64(8)) COMMENT '被阻止执行的名义金额',
    
    -- 元数据
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, trade_type, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, trade_type, timestamp, trade_id)
TTL timestamp + INTERVAL 30 DAY
SETTINGS index_granularity = 8192
COMMENT '统一交易数据表 - 存储多交易所多类型的标准化交易数据';

-- 创建索引以优化查询性能
-- 按交易所和币种查询的索引
CREATE INDEX IF NOT EXISTS idx_exchange_currency ON unified_trade_data (exchange_name, currency) TYPE minmax GRANULARITY 1;

-- 按交易类型查询的索引
CREATE INDEX IF NOT EXISTS idx_trade_type ON unified_trade_data (trade_type) TYPE set(10) GRANULARITY 1;

-- 按交易方向查询的索引
CREATE INDEX IF NOT EXISTS idx_side ON unified_trade_data (side) TYPE set(2) GRANULARITY 1;

-- 按价格范围查询的索引
CREATE INDEX IF NOT EXISTS idx_price ON unified_trade_data (price) TYPE minmax GRANULARITY 1;

-- 按交易量范围查询的索引
CREATE INDEX IF NOT EXISTS idx_quantity ON unified_trade_data (quantity) TYPE minmax GRANULARITY 1;

-- 按做市方查询的索引
CREATE INDEX IF NOT EXISTS idx_is_maker ON unified_trade_data (is_maker) TYPE set(3) GRANULARITY 1;

-- 创建物化视图：按分钟聚合的交易统计
CREATE MATERIALIZED VIEW IF NOT EXISTS trade_minute_stats
(
    exchange_name LowCardinality(String),
    currency LowCardinality(String),
    symbol_name String,
    trade_type LowCardinality(String),
    minute DateTime,
    
    -- 价格统计
    open_price Decimal64(8),
    close_price Decimal64(8),
    high_price Decimal64(8),
    low_price Decimal64(8),
    vwap Decimal64(8),
    
    -- 交易量统计
    total_volume Decimal64(8),
    total_quote_volume Decimal64(8),
    buy_volume Decimal64(8),
    sell_volume Decimal64(8),
    buy_quote_volume Decimal64(8),
    sell_quote_volume Decimal64(8),
    
    -- 交易次数统计
    trade_count UInt64,
    buy_count UInt64,
    sell_count UInt64,
    maker_count UInt64,
    taker_count UInt64,
    
    -- 时间范围
    first_timestamp DateTime64(3, 'UTC'),
    last_timestamp DateTime64(3, 'UTC')
)
ENGINE = SummingMergeTree()
PARTITION BY (exchange_name, trade_type, toYYYYMM(minute))
ORDER BY (exchange_name, currency, symbol_name, trade_type, minute)
TTL minute + INTERVAL 90 DAY
AS SELECT
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    toStartOfMinute(timestamp) as minute,
    
    -- 价格统计 (使用argMin/argMax获取开盘/收盘价)
    argMin(price, timestamp) as open_price,
    argMax(price, timestamp) as close_price,
    max(price) as high_price,
    min(price) as low_price,
    sum(price * quantity) / sum(quantity) as vwap,
    
    -- 交易量统计
    sum(quantity) as total_volume,
    sum(quote_quantity) as total_quote_volume,
    sumIf(quantity, side = 'buy') as buy_volume,
    sumIf(quantity, side = 'sell') as sell_volume,
    sumIf(quote_quantity, side = 'buy') as buy_quote_volume,
    sumIf(quote_quantity, side = 'sell') as sell_quote_volume,
    
    -- 交易次数统计
    count() as trade_count,
    countIf(side = 'buy') as buy_count,
    countIf(side = 'sell') as sell_count,
    countIf(is_maker = 1) as maker_count,
    countIf(is_maker = 0) as taker_count,
    
    -- 时间范围
    min(timestamp) as first_timestamp,
    max(timestamp) as last_timestamp
FROM unified_trade_data
GROUP BY exchange_name, currency, symbol_name, trade_type, minute;

-- 创建物化视图：按小时聚合的交易统计
CREATE MATERIALIZED VIEW IF NOT EXISTS trade_hourly_stats
(
    exchange_name LowCardinality(String),
    currency LowCardinality(String),
    symbol_name String,
    trade_type LowCardinality(String),
    hour DateTime,
    
    -- 价格统计
    open_price Decimal64(8),
    close_price Decimal64(8),
    high_price Decimal64(8),
    low_price Decimal64(8),
    vwap Decimal64(8),
    price_change Decimal64(8),
    price_change_percent Decimal64(4),
    
    -- 交易量统计
    total_volume Decimal64(8),
    total_quote_volume Decimal64(8),
    volume_change_percent Decimal64(4),
    
    -- 买卖比例
    buy_sell_ratio Decimal64(4),
    maker_taker_ratio Decimal64(4),
    
    -- 交易次数
    trade_count UInt64,
    avg_trade_size Decimal64(8),
    
    -- 时间范围
    periods_covered UInt64
)
ENGINE = ReplacingMergeTree()
PARTITION BY (exchange_name, trade_type, toYYYYMM(hour))
ORDER BY (exchange_name, currency, symbol_name, trade_type, hour)
TTL hour + INTERVAL 365 DAY
AS SELECT
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    toStartOfHour(timestamp) as hour,
    
    -- 价格统计
    argMin(price, timestamp) as open_price,
    argMax(price, timestamp) as close_price,
    max(price) as high_price,
    min(price) as low_price,
    sum(price * quantity) / sum(quantity) as vwap,
    argMax(price, timestamp) - argMin(price, timestamp) as price_change,
    (argMax(price, timestamp) - argMin(price, timestamp)) / argMin(price, timestamp) * 100 as price_change_percent,
    
    -- 交易量统计
    sum(quantity) as total_volume,
    sum(quote_quantity) as total_quote_volume,
    (sum(quantity) - lag(sum(quantity), 1) OVER (PARTITION BY exchange_name, currency, symbol_name, trade_type ORDER BY hour)) / lag(sum(quantity), 1) OVER (PARTITION BY exchange_name, currency, symbol_name, trade_type ORDER BY hour) * 100 as volume_change_percent,
    
    -- 买卖比例
    sumIf(quantity, side = 'buy') / sumIf(quantity, side = 'sell') as buy_sell_ratio,
    countIf(is_maker = 1) / countIf(is_maker = 0) as maker_taker_ratio,
    
    -- 交易次数
    count() as trade_count,
    sum(quantity) / count() as avg_trade_size,
    
    -- 时间范围
    countDistinct(toStartOfMinute(timestamp)) as periods_covered
FROM unified_trade_data
GROUP BY exchange_name, currency, symbol_name, trade_type, hour;

-- 创建用于监控的视图
-- 最新交易数据视图
CREATE VIEW IF NOT EXISTS latest_trades AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    trade_id,
    price,
    quantity,
    quote_quantity,
    side,
    is_maker,
    timestamp,
    collected_at
FROM unified_trade_data
WHERE timestamp >= now() - INTERVAL 1 HOUR
ORDER BY exchange_name, currency, symbol_name, trade_type, timestamp DESC;

-- 大额交易监控视图
CREATE VIEW IF NOT EXISTS large_trades AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    trade_id,
    price,
    quantity,
    quote_quantity,
    side,
    timestamp,
    quote_quantity / (
        SELECT avg(quote_quantity) 
        FROM unified_trade_data t2 
        WHERE t2.exchange_name = t1.exchange_name 
        AND t2.currency = t1.currency 
        AND t2.timestamp >= now() - INTERVAL 1 HOUR
    ) as size_ratio
FROM unified_trade_data t1
WHERE timestamp >= now() - INTERVAL 1 HOUR
AND quote_quantity > (
    SELECT percentile(0.95)(quote_quantity) 
    FROM unified_trade_data t3 
    WHERE t3.exchange_name = t1.exchange_name 
    AND t3.currency = t1.currency 
    AND t3.timestamp >= now() - INTERVAL 1 HOUR
)
ORDER BY quote_quantity DESC;

-- 交易活跃度排行榜视图
CREATE VIEW IF NOT EXISTS trade_activity_rankings AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    count() as trade_count,
    sum(quantity) as total_volume,
    sum(quote_quantity) as total_quote_volume,
    avg(price) as avg_price,
    max(timestamp) as last_trade_time
FROM unified_trade_data
WHERE timestamp >= now() - INTERVAL 1 HOUR
GROUP BY exchange_name, currency, symbol_name, trade_type
ORDER BY total_quote_volume DESC;

-- 跨交易所价格对比视图
CREATE VIEW IF NOT EXISTS cross_exchange_price_comparison AS
SELECT 
    currency,
    symbol_name,
    trade_type,
    exchange_name,
    argMax(price, timestamp) as latest_price,
    max(timestamp) as latest_time,
    count() as trade_count_1h
FROM unified_trade_data
WHERE timestamp >= now() - INTERVAL 1 HOUR
GROUP BY currency, symbol_name, trade_type, exchange_name
ORDER BY currency, symbol_name, trade_type, latest_price DESC;

-- 验证表创建
SELECT 
    'unified_trade_data' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'unified_trade_data'
UNION ALL
SELECT 
    'trade_minute_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'trade_minute_stats'
UNION ALL
SELECT 
    'trade_hourly_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'trade_hourly_stats';

-- 显示创建的表和视图
SHOW TABLES FROM marketprism LIKE '%trade%';

-- 显示表结构
DESCRIBE TABLE unified_trade_data;

-- 创建套利机会检测视图
CREATE VIEW IF NOT EXISTS arbitrage_opportunities AS
WITH price_comparison AS (
    SELECT
        currency,
        symbol_name,
        trade_type,
        exchange_name,
        argMax(price, timestamp) as latest_price,
        max(timestamp) as latest_time
    FROM unified_trade_data
    WHERE timestamp >= now() - INTERVAL 5 MINUTE
    GROUP BY currency, symbol_name, trade_type, exchange_name
),
price_spread AS (
    SELECT
        currency,
        symbol_name,
        trade_type,
        max(latest_price) as max_price,
        min(latest_price) as min_price,
        (max(latest_price) - min(latest_price)) / min(latest_price) * 100 as spread_percent,
        argMax(exchange_name, latest_price) as high_exchange,
        argMin(exchange_name, latest_price) as low_exchange
    FROM price_comparison
    GROUP BY currency, symbol_name, trade_type
    HAVING count(DISTINCT exchange_name) >= 2
)
SELECT
    currency,
    symbol_name,
    trade_type,
    spread_percent,
    max_price,
    min_price,
    high_exchange,
    low_exchange,
    now() as detected_at
FROM price_spread
WHERE spread_percent > 0.5  -- 套利机会阈值：价差超过0.5%
ORDER BY spread_percent DESC;

-- 创建交易异常检测视图
CREATE VIEW IF NOT EXISTS trade_anomalies AS
WITH trade_stats AS (
    SELECT
        exchange_name,
        currency,
        symbol_name,
        trade_type,
        avg(quantity) as avg_quantity,
        stddevPop(quantity) as stddev_quantity,
        avg(quote_quantity) as avg_quote_quantity,
        stddevPop(quote_quantity) as stddev_quote_quantity,
        percentile(0.95)(quantity) as p95_quantity,
        percentile(0.99)(quote_quantity) as p99_quote_quantity
    FROM unified_trade_data
    WHERE timestamp >= now() - INTERVAL 1 HOUR
    GROUP BY exchange_name, currency, symbol_name, trade_type
)
SELECT
    t.exchange_name,
    t.currency,
    t.symbol_name,
    t.trade_type,
    t.trade_id,
    t.price,
    t.quantity,
    t.quote_quantity,
    t.side,
    t.timestamp,
    CASE
        WHEN t.quantity > s.avg_quantity + 3 * s.stddev_quantity THEN 'LARGE_QUANTITY'
        WHEN t.quote_quantity > s.p99_quote_quantity THEN 'LARGE_VALUE'
        WHEN t.quantity < s.avg_quantity / 10 THEN 'MICRO_TRADE'
        ELSE 'NORMAL'
    END as anomaly_type,
    t.quantity / s.avg_quantity as quantity_ratio,
    t.quote_quantity / s.avg_quote_quantity as value_ratio
FROM unified_trade_data t
JOIN trade_stats s ON
    t.exchange_name = s.exchange_name
    AND t.currency = s.currency
    AND t.symbol_name = s.symbol_name
    AND t.trade_type = s.trade_type
WHERE t.timestamp >= now() - INTERVAL 10 MINUTE
AND (
    t.quantity > s.avg_quantity + 3 * s.stddev_quantity OR
    t.quote_quantity > s.p99_quote_quantity OR
    t.quantity < s.avg_quantity / 10
)
ORDER BY t.timestamp DESC;

-- 创建市场深度分析视图
CREATE VIEW IF NOT EXISTS market_depth_analysis AS
SELECT
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    toStartOfMinute(timestamp) as minute,

    -- 买卖压力分析
    sumIf(quantity, side = 'buy') / sum(quantity) * 100 as buy_pressure_percent,
    sumIf(quantity, side = 'sell') / sum(quantity) * 100 as sell_pressure_percent,

    -- 做市商活动分析
    countIf(is_maker = 1) / count() * 100 as maker_percent,
    countIf(is_maker = 0) / count() * 100 as taker_percent,

    -- 价格波动分析
    max(price) - min(price) as price_range,
    (max(price) - min(price)) / avg(price) * 100 as volatility_percent,

    -- 交易频率分析
    count() as trades_per_minute,
    sum(quantity) as volume_per_minute,
    sum(quote_quantity) as quote_volume_per_minute,

    -- 平均交易规模
    avg(quantity) as avg_trade_size,
    avg(quote_quantity) as avg_trade_value
FROM unified_trade_data
WHERE timestamp >= now() - INTERVAL 2 HOUR
GROUP BY exchange_name, currency, symbol_name, trade_type, minute
ORDER BY exchange_name, currency, symbol_name, trade_type, minute DESC;

-- 创建性能监控视图
CREATE VIEW IF NOT EXISTS trade_data_performance AS
SELECT
    exchange_name,
    trade_type,
    toStartOfHour(collected_at) as hour,
    count() as records_processed,
    avg(toUnixTimestamp(collected_at) - toUnixTimestamp(timestamp)) as avg_latency_seconds,
    max(toUnixTimestamp(collected_at) - toUnixTimestamp(timestamp)) as max_latency_seconds,
    countIf(toUnixTimestamp(collected_at) - toUnixTimestamp(timestamp) > 1) as delayed_records,
    countIf(toUnixTimestamp(collected_at) - toUnixTimestamp(timestamp) > 5) as severely_delayed_records
FROM unified_trade_data
WHERE collected_at >= now() - INTERVAL 24 HOUR
GROUP BY exchange_name, trade_type, hour
ORDER BY hour DESC;

-- 创建数据质量监控视图
CREATE VIEW IF NOT EXISTS trade_data_quality AS
SELECT
    exchange_name,
    trade_type,
    toStartOfHour(timestamp) as hour,
    count() as total_records,
    countIf(price <= 0) as invalid_price_records,
    countIf(quantity <= 0) as invalid_quantity_records,
    countIf(quote_quantity <= 0) as invalid_quote_quantity_records,
    countIf(trade_id = '') as missing_trade_id_records,
    countIf(side NOT IN ('buy', 'sell')) as invalid_side_records,
    (count() - countIf(price <= 0 OR quantity <= 0 OR quote_quantity <= 0 OR trade_id = '' OR side NOT IN ('buy', 'sell'))) / count() * 100 as data_quality_percent
FROM unified_trade_data
WHERE timestamp >= now() - INTERVAL 24 HOUR
GROUP BY exchange_name, trade_type, hour
ORDER BY hour DESC;

-- 创建分区管理函数
-- 注意：这些是管理查询，需要定期执行
/*
-- 清理过期分区 (保留30天数据)
ALTER TABLE unified_trade_data DROP PARTITION WHERE toYYYYMM(timestamp) < toYYYYMM(now() - INTERVAL 30 DAY);

-- 优化表性能
OPTIMIZE TABLE unified_trade_data FINAL;

-- 检查表大小和分区信息
SELECT
    partition,
    count() as rows,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size,
    compression_ratio
FROM system.parts
WHERE database = 'marketprism' AND table = 'unified_trade_data' AND active = 1
GROUP BY partition
ORDER BY partition DESC;
*/

-- 创建常用查询的物化视图索引
-- 按币种和时间范围的快速查询
CREATE INDEX IF NOT EXISTS idx_currency_time ON unified_trade_data (currency, timestamp) TYPE minmax GRANULARITY 1;

-- 按交易金额范围的查询
CREATE INDEX IF NOT EXISTS idx_quote_quantity ON unified_trade_data (quote_quantity) TYPE minmax GRANULARITY 1;

-- 按交易ID的精确查询
CREATE INDEX IF NOT EXISTS idx_trade_id ON unified_trade_data (trade_id) TYPE bloom_filter GRANULARITY 1;

-- 完成提示
SELECT 'MarketPrism统一交易数据表初始化完成！' as status;

-- 显示所有相关的表和视图
SELECT
    name,
    engine,
    total_rows,
    formatReadableSize(total_bytes) as size
FROM system.tables
WHERE database = 'marketprism'
AND (name LIKE '%trade%' OR name LIKE '%arbitrage%' OR name LIKE '%anomal%')
ORDER BY name;
