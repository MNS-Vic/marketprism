-- MarketPrism 市场多空人数比数据表结构
-- 用于存储Binance和OKX的整体市场用户多空人数比数据

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS marketprism;

-- 使用数据库
USE marketprism;

-- 创建主表：市场多空人数比数据
CREATE TABLE IF NOT EXISTS market_long_short_ratio
(
    -- 基础信息
    exchange_name LowCardinality(String) COMMENT '交易所名称: binance/okx',
    symbol_name String COMMENT '交易对名称 (如: BTC-USDT)',
    currency LowCardinality(String) COMMENT '币种名称 (如: BTC)',
    
    -- 核心人数比数据
    long_short_ratio Decimal64(8) COMMENT '多空人数比值',
    long_account_ratio Nullable(Decimal64(8)) COMMENT '多仓人数比例 (0-1)',
    short_account_ratio Nullable(Decimal64(8)) COMMENT '空仓人数比例 (0-1)',
    
    -- 元数据
    data_type LowCardinality(String) COMMENT '数据类型: account(人数)',
    period LowCardinality(String) COMMENT '时间周期: 5m,15m,30m,1h,2h,4h,6h,12h,1d',
    instrument_type LowCardinality(String) COMMENT '合约类型: futures/swap/perpetual',
    
    -- 数据质量指标
    data_quality_score Nullable(Decimal64(4)) COMMENT '数据质量评分 (0-1)',
    ratio_sum_check Nullable(UInt8) COMMENT '人数比例和检查 (1=通过, 0=失败)',
    
    -- 时间信息
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间戳',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    
    -- 原始数据 (JSON格式存储)
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, period, timestamp)
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192
COMMENT '市场多空人数比数据表 - 存储整体市场用户多空人数比例历史数据';

-- 创建索引以优化查询性能
-- 按交易所和币种查询的索引
CREATE INDEX IF NOT EXISTS idx_exchange_currency ON market_long_short_ratio (exchange_name, currency) TYPE minmax GRANULARITY 1;

-- 按数据周期查询的索引
CREATE INDEX IF NOT EXISTS idx_period ON market_long_short_ratio (period) TYPE set(10) GRANULARITY 1;

-- 按多空比值范围查询的索引 (用于情绪监控)
CREATE INDEX IF NOT EXISTS idx_long_short_ratio ON market_long_short_ratio (long_short_ratio) TYPE minmax GRANULARITY 1;

-- 按数据质量查询的索引
CREATE INDEX IF NOT EXISTS idx_data_quality ON market_long_short_ratio (data_quality_score) TYPE minmax GRANULARITY 1;

-- 创建物化视图：按小时聚合的市场情绪统计
CREATE MATERIALIZED VIEW IF NOT EXISTS market_ratio_hourly_stats
(
    exchange_name LowCardinality(String),
    currency LowCardinality(String),
    period LowCardinality(String),
    hour DateTime,
    avg_long_short_ratio Decimal64(8),
    max_long_short_ratio Decimal64(8),
    min_long_short_ratio Decimal64(8),
    avg_long_account_ratio Nullable(Decimal64(8)),
    avg_short_account_ratio Nullable(Decimal64(8)),
    avg_data_quality_score Nullable(Decimal64(4)),
    data_points UInt64,
    first_timestamp DateTime64(3, 'UTC'),
    last_timestamp DateTime64(3, 'UTC')
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (exchange_name, currency, period, hour)
TTL hour + INTERVAL 365 DAY
AS SELECT
    exchange_name,
    currency,
    period,
    toStartOfHour(timestamp) as hour,
    avg(long_short_ratio) as avg_long_short_ratio,
    max(long_short_ratio) as max_long_short_ratio,
    min(long_short_ratio) as min_long_short_ratio,
    avg(long_account_ratio) as avg_long_account_ratio,
    avg(short_account_ratio) as avg_short_account_ratio,
    avg(data_quality_score) as avg_data_quality_score,
    count() as data_points,
    min(timestamp) as first_timestamp,
    max(timestamp) as last_timestamp
FROM market_long_short_ratio
GROUP BY exchange_name, currency, period, hour;

-- 创建物化视图：按日聚合的市场情绪统计
CREATE MATERIALIZED VIEW IF NOT EXISTS market_ratio_daily_stats
(
    exchange_name LowCardinality(String),
    currency LowCardinality(String),
    period LowCardinality(String),
    date Date,
    avg_long_short_ratio Decimal64(8),
    max_long_short_ratio Decimal64(8),
    min_long_short_ratio Decimal64(8),
    ratio_at_start Decimal64(8),
    ratio_at_end Decimal64(8),
    ratio_change_absolute Decimal64(8),
    ratio_change_percent Decimal64(8),
    avg_long_account_ratio Nullable(Decimal64(8)),
    avg_short_account_ratio Nullable(Decimal64(8)),
    data_points UInt64,
    periods_covered UInt64
)
ENGINE = ReplacingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (exchange_name, currency, period, date)
TTL date + INTERVAL 730 DAY
AS SELECT
    exchange_name,
    currency,
    period,
    toDate(timestamp) as date,
    avg(long_short_ratio) as avg_long_short_ratio,
    max(long_short_ratio) as max_long_short_ratio,
    min(long_short_ratio) as min_long_short_ratio,
    argMin(long_short_ratio, timestamp) as ratio_at_start,
    argMax(long_short_ratio, timestamp) as ratio_at_end,
    argMax(long_short_ratio, timestamp) - argMin(long_short_ratio, timestamp) as ratio_change_absolute,
    (argMax(long_short_ratio, timestamp) - argMin(long_short_ratio, timestamp)) / abs(argMin(long_short_ratio, timestamp)) * 100 as ratio_change_percent,
    avg(long_account_ratio) as avg_long_account_ratio,
    avg(short_account_ratio) as avg_short_account_ratio,
    count() as data_points,
    countDistinct(toStartOfHour(timestamp)) as periods_covered
FROM market_long_short_ratio
GROUP BY exchange_name, currency, period, date;

-- 创建用于监控的视图
-- 最新市场情绪数据视图
CREATE VIEW IF NOT EXISTS latest_market_sentiment AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    period,
    long_short_ratio,
    long_account_ratio,
    short_account_ratio,
    data_quality_score,
    ratio_sum_check,
    timestamp,
    collected_at
FROM market_long_short_ratio
WHERE timestamp >= now() - INTERVAL 2 HOUR
ORDER BY exchange_name, currency, period, timestamp DESC;

-- 市场情绪排行榜视图 (按多空比值排序)
CREATE VIEW IF NOT EXISTS market_sentiment_rankings AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    period,
    long_short_ratio,
    long_account_ratio,
    short_account_ratio,
    data_quality_score,
    timestamp
FROM (
    SELECT 
        exchange_name,
        currency,
        symbol_name,
        period,
        long_short_ratio,
        long_account_ratio,
        short_account_ratio,
        data_quality_score,
        timestamp,
        ROW_NUMBER() OVER (PARTITION BY exchange_name, currency, period ORDER BY timestamp DESC) as rn
    FROM market_long_short_ratio
    WHERE timestamp >= now() - INTERVAL 2 HOUR
) ranked
WHERE rn = 1
ORDER BY long_short_ratio DESC;

-- 市场情绪异常监控视图 (极端情绪情况)
CREATE VIEW IF NOT EXISTS market_sentiment_anomalies AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    period,
    long_short_ratio,
    long_account_ratio,
    short_account_ratio,
    data_quality_score,
    timestamp,
    CASE 
        WHEN long_short_ratio > 3.0 THEN 'EXTREMELY_BULLISH'
        WHEN long_short_ratio > 2.0 THEN 'VERY_BULLISH'
        WHEN long_short_ratio > 1.5 THEN 'BULLISH'
        WHEN long_short_ratio < 0.33 THEN 'EXTREMELY_BEARISH'
        WHEN long_short_ratio < 0.5 THEN 'VERY_BEARISH'
        WHEN long_short_ratio < 0.67 THEN 'BEARISH'
        ELSE 'NEUTRAL'
    END as sentiment_level,
    CASE
        WHEN data_quality_score < 0.7 THEN 'LOW_QUALITY'
        WHEN ratio_sum_check = 0 THEN 'RATIO_ERROR'
        ELSE 'NORMAL'
    END as data_issue
FROM latest_market_sentiment
WHERE long_short_ratio > 2.0 OR long_short_ratio < 0.5 OR data_quality_score < 0.7
ORDER BY abs(long_short_ratio - 1.0) DESC;

-- 验证表创建
SELECT 
    'market_long_short_ratio' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'market_long_short_ratio'
UNION ALL
SELECT 
    'market_ratio_hourly_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'market_ratio_hourly_stats'
UNION ALL
SELECT 
    'market_ratio_daily_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'market_ratio_daily_stats';

-- 显示创建的表和视图
SHOW TABLES FROM marketprism LIKE '%market%ratio%';

-- 显示表结构
DESCRIBE TABLE market_long_short_ratio;

-- 完成提示
SELECT 'MarketPrism市场多空人数比数据表初始化完成！' as status;
