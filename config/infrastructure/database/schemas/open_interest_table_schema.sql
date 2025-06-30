-- MarketPrism 持仓量数据表结构
-- 用于存储OKX和Binance的永续合约和期货持仓量数据

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS marketprism;

-- 使用数据库
USE marketprism;

-- 创建主表：持仓量数据
CREATE TABLE IF NOT EXISTS open_interest
(
    -- 基础信息
    exchange_name LowCardinality(String) COMMENT '交易所名称: okx/binance',
    symbol_name String COMMENT '交易对名称 (标准格式: BTC-USDT)',
    product_type LowCardinality(String) COMMENT '产品类型: swap/futures',
    instrument_id String COMMENT '产品ID (交易所原始格式)',
    
    -- 持仓量信息
    open_interest_value Decimal64(8) COMMENT '持仓量数值 (合约张数或币数)',
    open_interest_usd Nullable(Decimal64(8)) COMMENT '持仓量USD价值',
    open_interest_unit LowCardinality(String) COMMENT '持仓量单位: contracts/coins/usd',
    
    -- 价格信息
    mark_price Nullable(Decimal64(8)) COMMENT '标记价格',
    index_price Nullable(Decimal64(8)) COMMENT '指数价格',
    
    -- 时间信息
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间戳',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    
    -- 统计信息
    change_24h Nullable(Decimal64(8)) COMMENT '24小时变化量',
    change_24h_percent Nullable(Decimal64(8)) COMMENT '24小时变化百分比',
    
    -- 原始数据 (JSON格式存储)
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, symbol_name, product_type, timestamp)
TTL timestamp + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
COMMENT '持仓量数据表 - 存储永续合约和期货的未平仓合约数量';

-- 创建索引以优化查询性能
-- 按交易所和交易对查询的索引
CREATE INDEX IF NOT EXISTS idx_exchange_symbol ON open_interest (exchange_name, symbol_name) TYPE minmax GRANULARITY 1;

-- 按产品类型查询的索引
CREATE INDEX IF NOT EXISTS idx_product_type ON open_interest (product_type) TYPE set(10) GRANULARITY 1;

-- 按持仓量USD价值范围查询的索引 (用于大额持仓监控)
CREATE INDEX IF NOT EXISTS idx_open_interest_usd ON open_interest (open_interest_usd) TYPE minmax GRANULARITY 1;

-- 按持仓量数值范围查询的索引
CREATE INDEX IF NOT EXISTS idx_open_interest_value ON open_interest (open_interest_value) TYPE minmax GRANULARITY 1;

-- 创建物化视图：按小时聚合的持仓量统计
CREATE MATERIALIZED VIEW IF NOT EXISTS open_interest_hourly_stats
(
    exchange_name LowCardinality(String),
    symbol_name String,
    product_type LowCardinality(String),
    hour DateTime,
    avg_open_interest Decimal64(8),
    max_open_interest Decimal64(8),
    min_open_interest Decimal64(8),
    avg_open_interest_usd Nullable(Decimal64(8)),
    max_open_interest_usd Nullable(Decimal64(8)),
    min_open_interest_usd Nullable(Decimal64(8)),
    data_points UInt64,
    first_timestamp DateTime64(3, 'UTC'),
    last_timestamp DateTime64(3, 'UTC')
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (exchange_name, symbol_name, product_type, hour)
TTL hour + INTERVAL 180 DAY
AS SELECT
    exchange_name,
    symbol_name,
    product_type,
    toStartOfHour(timestamp) as hour,
    avg(open_interest_value) as avg_open_interest,
    max(open_interest_value) as max_open_interest,
    min(open_interest_value) as min_open_interest,
    avg(open_interest_usd) as avg_open_interest_usd,
    max(open_interest_usd) as max_open_interest_usd,
    min(open_interest_usd) as min_open_interest_usd,
    count() as data_points,
    min(timestamp) as first_timestamp,
    max(timestamp) as last_timestamp
FROM open_interest
GROUP BY exchange_name, symbol_name, product_type, hour;

-- 创建物化视图：按日聚合的持仓量统计
CREATE MATERIALIZED VIEW IF NOT EXISTS open_interest_daily_stats
(
    exchange_name LowCardinality(String),
    symbol_name String,
    product_type LowCardinality(String),
    date Date,
    avg_open_interest Decimal64(8),
    max_open_interest Decimal64(8),
    min_open_interest Decimal64(8),
    open_interest_at_start Decimal64(8),
    open_interest_at_end Decimal64(8),
    change_absolute Decimal64(8),
    change_percent Decimal64(8),
    avg_open_interest_usd Nullable(Decimal64(8)),
    max_open_interest_usd Nullable(Decimal64(8)),
    min_open_interest_usd Nullable(Decimal64(8)),
    data_points UInt64
)
ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (exchange_name, symbol_name, product_type, date)
TTL date + INTERVAL 365 DAY
AS SELECT
    exchange_name,
    symbol_name,
    product_type,
    toDate(timestamp) as date,
    avg(open_interest_value) as avg_open_interest,
    max(open_interest_value) as max_open_interest,
    min(open_interest_value) as min_open_interest,
    argMin(open_interest_value, timestamp) as open_interest_at_start,
    argMax(open_interest_value, timestamp) as open_interest_at_end,
    argMax(open_interest_value, timestamp) - argMin(open_interest_value, timestamp) as change_absolute,
    (argMax(open_interest_value, timestamp) - argMin(open_interest_value, timestamp)) / argMin(open_interest_value, timestamp) * 100 as change_percent,
    avg(open_interest_usd) as avg_open_interest_usd,
    max(open_interest_usd) as max_open_interest_usd,
    min(open_interest_usd) as min_open_interest_usd,
    count() as data_points
FROM open_interest
GROUP BY exchange_name, symbol_name, product_type, date;

-- 创建用于监控的视图
-- 最新持仓量数据视图
CREATE VIEW IF NOT EXISTS latest_open_interest AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    instrument_id,
    open_interest_value,
    open_interest_usd,
    open_interest_unit,
    mark_price,
    change_24h,
    change_24h_percent,
    timestamp,
    collected_at
FROM open_interest
WHERE timestamp >= now() - INTERVAL 1 HOUR
ORDER BY exchange_name, symbol_name, timestamp DESC;

-- 持仓量排行榜视图 (按USD价值)
CREATE VIEW IF NOT EXISTS open_interest_rankings AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    open_interest_value,
    open_interest_usd,
    mark_price,
    change_24h_percent,
    timestamp
FROM (
    SELECT 
        exchange_name,
        symbol_name,
        product_type,
        open_interest_value,
        open_interest_usd,
        mark_price,
        change_24h_percent,
        timestamp,
        ROW_NUMBER() OVER (PARTITION BY exchange_name, symbol_name, product_type ORDER BY timestamp DESC) as rn
    FROM open_interest
    WHERE timestamp >= now() - INTERVAL 2 HOUR
      AND open_interest_usd IS NOT NULL
) ranked
WHERE rn = 1
ORDER BY open_interest_usd DESC;

-- 持仓量异常变化监控视图 (24小时变化超过20%)
CREATE VIEW IF NOT EXISTS open_interest_anomalies AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    open_interest_value,
    open_interest_usd,
    change_24h,
    change_24h_percent,
    timestamp,
    CASE 
        WHEN change_24h_percent > 50 THEN 'CRITICAL_INCREASE'
        WHEN change_24h_percent > 20 THEN 'HIGH_INCREASE'
        WHEN change_24h_percent < -50 THEN 'CRITICAL_DECREASE'
        WHEN change_24h_percent < -20 THEN 'HIGH_DECREASE'
        ELSE 'NORMAL'
    END as anomaly_level
FROM latest_open_interest
WHERE abs(change_24h_percent) > 20
ORDER BY abs(change_24h_percent) DESC;

-- 验证表创建
SELECT 
    'open_interest' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'open_interest'
UNION ALL
SELECT 
    'open_interest_hourly_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'open_interest_hourly_stats'
UNION ALL
SELECT 
    'open_interest_daily_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'open_interest_daily_stats';

-- 显示创建的表和视图
SHOW TABLES FROM marketprism LIKE '%open_interest%';

-- 显示表结构
DESCRIBE TABLE open_interest;

-- 完成提示
SELECT 'MarketPrism持仓量数据表初始化完成！' as status;
