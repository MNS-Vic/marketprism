-- MarketPrism 资金费率数据表结构
-- 用于存储OKX和Binance的永续合约资金费率数据

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS marketprism;

-- 使用数据库
USE marketprism;

-- 创建主表：资金费率数据
CREATE TABLE IF NOT EXISTS funding_rate
(
    -- 基础信息
    exchange_name LowCardinality(String) COMMENT '交易所名称: okx/binance',
    symbol_name String COMMENT '交易对名称 (标准格式: BTC-USDT)',
    product_type LowCardinality(String) COMMENT '产品类型: swap/perpetual',
    instrument_id String COMMENT '产品ID (交易所原始格式)',
    
    -- 资金费率信息
    current_funding_rate Decimal64(8) COMMENT '当前资金费率 (如 0.0001 表示 0.01%)',
    estimated_funding_rate Nullable(Decimal64(8)) COMMENT '预估下期资金费率',
    next_funding_time DateTime64(3, 'UTC') COMMENT '下次资金费率结算时间',
    funding_interval LowCardinality(String) COMMENT '资金费率间隔 (通常8h)',
    
    -- 价格信息 (主要来自Binance)
    mark_price Nullable(Decimal64(8)) COMMENT '标记价格',
    index_price Nullable(Decimal64(8)) COMMENT '指数价格',
    premium_index Nullable(Decimal64(8)) COMMENT '溢价指数 (标记价格 - 指数价格)',
    
    -- 历史统计 (可选)
    funding_rate_24h_avg Nullable(Decimal64(8)) COMMENT '24小时平均资金费率',
    funding_rate_7d_avg Nullable(Decimal64(8)) COMMENT '7天平均资金费率',
    
    -- 时间信息
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间戳',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    
    -- 原始数据 (JSON格式存储)
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, symbol_name, product_type, timestamp)
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192
COMMENT '资金费率数据表 - 存储永续合约资金费率历史数据';

-- 创建索引以优化查询性能
-- 按交易所和交易对查询的索引
CREATE INDEX IF NOT EXISTS idx_exchange_symbol ON funding_rate (exchange_name, symbol_name) TYPE minmax GRANULARITY 1;

-- 按产品类型查询的索引
CREATE INDEX IF NOT EXISTS idx_product_type ON funding_rate (product_type) TYPE set(10) GRANULARITY 1;

-- 按资金费率范围查询的索引 (用于异常费率监控)
CREATE INDEX IF NOT EXISTS idx_funding_rate ON funding_rate (current_funding_rate) TYPE minmax GRANULARITY 1;

-- 按下次结算时间查询的索引
CREATE INDEX IF NOT EXISTS idx_next_funding_time ON funding_rate (next_funding_time) TYPE minmax GRANULARITY 1;

-- 创建物化视图：按小时聚合的资金费率统计
CREATE MATERIALIZED VIEW IF NOT EXISTS funding_rate_hourly_stats
(
    exchange_name LowCardinality(String),
    symbol_name String,
    product_type LowCardinality(String),
    hour DateTime,
    avg_funding_rate Decimal64(8),
    max_funding_rate Decimal64(8),
    min_funding_rate Decimal64(8),
    avg_mark_price Nullable(Decimal64(8)),
    avg_premium_index Nullable(Decimal64(8)),
    data_points UInt64,
    first_timestamp DateTime64(3, 'UTC'),
    last_timestamp DateTime64(3, 'UTC')
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (exchange_name, symbol_name, product_type, hour)
TTL hour + INTERVAL 365 DAY
AS SELECT
    exchange_name,
    symbol_name,
    product_type,
    toStartOfHour(timestamp) as hour,
    avg(current_funding_rate) as avg_funding_rate,
    max(current_funding_rate) as max_funding_rate,
    min(current_funding_rate) as min_funding_rate,
    avg(mark_price) as avg_mark_price,
    avg(premium_index) as avg_premium_index,
    count() as data_points,
    min(timestamp) as first_timestamp,
    max(timestamp) as last_timestamp
FROM funding_rate
GROUP BY exchange_name, symbol_name, product_type, hour;

-- 创建物化视图：按日聚合的资金费率统计
CREATE MATERIALIZED VIEW IF NOT EXISTS funding_rate_daily_stats
(
    exchange_name LowCardinality(String),
    symbol_name String,
    product_type LowCardinality(String),
    date Date,
    avg_funding_rate Decimal64(8),
    max_funding_rate Decimal64(8),
    min_funding_rate Decimal64(8),
    funding_rate_at_start Decimal64(8),
    funding_rate_at_end Decimal64(8),
    rate_change_absolute Decimal64(8),
    rate_change_percent Decimal64(8),
    avg_mark_price Nullable(Decimal64(8)),
    avg_premium_index Nullable(Decimal64(8)),
    data_points UInt64,
    funding_cycles UInt64
)
ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (exchange_name, symbol_name, product_type, date)
TTL date + INTERVAL 730 DAY
AS SELECT
    exchange_name,
    symbol_name,
    product_type,
    toDate(timestamp) as date,
    avg(current_funding_rate) as avg_funding_rate,
    max(current_funding_rate) as max_funding_rate,
    min(current_funding_rate) as min_funding_rate,
    argMin(current_funding_rate, timestamp) as funding_rate_at_start,
    argMax(current_funding_rate, timestamp) as funding_rate_at_end,
    argMax(current_funding_rate, timestamp) - argMin(current_funding_rate, timestamp) as rate_change_absolute,
    (argMax(current_funding_rate, timestamp) - argMin(current_funding_rate, timestamp)) / abs(argMin(current_funding_rate, timestamp)) * 100 as rate_change_percent,
    avg(mark_price) as avg_mark_price,
    avg(premium_index) as avg_premium_index,
    count() as data_points,
    countDistinct(toStartOfHour(timestamp)) as funding_cycles
FROM funding_rate
GROUP BY exchange_name, symbol_name, product_type, date;

-- 创建用于监控的视图
-- 最新资金费率数据视图
CREATE VIEW IF NOT EXISTS latest_funding_rate AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    instrument_id,
    current_funding_rate,
    estimated_funding_rate,
    next_funding_time,
    funding_interval,
    mark_price,
    premium_index,
    timestamp,
    collected_at
FROM funding_rate
WHERE timestamp >= now() - INTERVAL 2 HOUR
ORDER BY exchange_name, symbol_name, timestamp DESC;

-- 资金费率排行榜视图 (按费率绝对值排序)
CREATE VIEW IF NOT EXISTS funding_rate_rankings AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    current_funding_rate,
    abs(current_funding_rate) as abs_funding_rate,
    mark_price,
    premium_index,
    next_funding_time,
    timestamp
FROM (
    SELECT 
        exchange_name,
        symbol_name,
        product_type,
        current_funding_rate,
        mark_price,
        premium_index,
        next_funding_time,
        timestamp,
        ROW_NUMBER() OVER (PARTITION BY exchange_name, symbol_name, product_type ORDER BY timestamp DESC) as rn
    FROM funding_rate
    WHERE timestamp >= now() - INTERVAL 2 HOUR
) ranked
WHERE rn = 1
ORDER BY abs(current_funding_rate) DESC;

-- 资金费率异常监控视图 (费率超过±0.1%的情况)
CREATE VIEW IF NOT EXISTS funding_rate_anomalies AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    current_funding_rate,
    current_funding_rate * 100 as funding_rate_percent,
    mark_price,
    premium_index,
    next_funding_time,
    timestamp,
    CASE 
        WHEN current_funding_rate > 0.005 THEN 'EXTREMELY_HIGH_POSITIVE'
        WHEN current_funding_rate > 0.001 THEN 'HIGH_POSITIVE'
        WHEN current_funding_rate < -0.005 THEN 'EXTREMELY_HIGH_NEGATIVE'
        WHEN current_funding_rate < -0.001 THEN 'HIGH_NEGATIVE'
        ELSE 'NORMAL'
    END as anomaly_level
FROM latest_funding_rate
WHERE abs(current_funding_rate) > 0.001  -- 超过±0.1%
ORDER BY abs(current_funding_rate) DESC;

-- 验证表创建
SELECT 
    'funding_rate' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'funding_rate'
UNION ALL
SELECT 
    'funding_rate_hourly_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'funding_rate_hourly_stats'
UNION ALL
SELECT 
    'funding_rate_daily_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'funding_rate_daily_stats';

-- 显示创建的表和视图
SHOW TABLES FROM marketprism LIKE '%funding_rate%';

-- 显示表结构
DESCRIBE TABLE funding_rate;

-- 完成提示
SELECT 'MarketPrism资金费率数据表初始化完成！' as status;
