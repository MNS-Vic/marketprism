-- MarketPrism 生产级 ClickHouse 表结构
-- 包含压缩、分区、TTL和索引优化

-- 使用主数据库
USE marketprism;

-- ==================== 热存储表 (1天TTL) ====================

-- 热存储交易数据表
CREATE TABLE IF NOT EXISTS marketprism.hot_trades (
    timestamp DateTime64(3) CODEC(LZ4),
    symbol LowCardinality(String) CODEC(LZ4),
    exchange LowCardinality(String) CODEC(LZ4),
    price Decimal64(8) CODEC(LZ4),
    amount Decimal64(8) CODEC(LZ4),
    side LowCardinality(String) CODEC(LZ4),
    trade_id String CODEC(LZ4),
    created_at DateTime64(3) DEFAULT now64() CODEC(LZ4),
    
    -- 索引优化
    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
    INDEX idx_price price TYPE minmax GRANULARITY 8,
    INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 8
) ENGINE = MergeTree()
PARTITION BY (toYYYYMMDD(timestamp), exchange)
ORDER BY (exchange, symbol, timestamp)
TTL created_at + INTERVAL 1 DAY
SETTINGS 
    index_granularity = 8192,
    merge_with_ttl_timeout = 3600,
    ttl_only_drop_parts = 1;

-- 热存储行情数据表
CREATE TABLE IF NOT EXISTS marketprism.hot_tickers (
    timestamp DateTime64(3) CODEC(LZ4),
    symbol LowCardinality(String) CODEC(LZ4),
    exchange LowCardinality(String) CODEC(LZ4),
    last_price Decimal64(8) CODEC(LZ4),
    volume_24h Decimal64(8) CODEC(LZ4),
    price_change_24h Decimal64(8) CODEC(LZ4),
    high_24h Decimal64(8) CODEC(LZ4),
    low_24h Decimal64(8) CODEC(LZ4),
    created_at DateTime64(3) DEFAULT now64() CODEC(LZ4),
    
    -- 索引优化
    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
    INDEX idx_price last_price TYPE minmax GRANULARITY 8
) ENGINE = ReplacingMergeTree(created_at)
PARTITION BY (toYYYYMMDD(timestamp), exchange)
ORDER BY (exchange, symbol, timestamp)
TTL created_at + INTERVAL 1 DAY
SETTINGS 
    index_granularity = 8192,
    merge_with_ttl_timeout = 3600,
    ttl_only_drop_parts = 1;

-- 热存储订单簿数据表
CREATE TABLE IF NOT EXISTS marketprism.hot_orderbooks (
    timestamp DateTime64(3) CODEC(LZ4),
    symbol LowCardinality(String) CODEC(LZ4),
    exchange LowCardinality(String) CODEC(LZ4),
    best_bid Decimal64(8) CODEC(LZ4),
    best_ask Decimal64(8) CODEC(LZ4),
    spread Decimal64(8) CODEC(LZ4),
    bids_json String CODEC(LZ4),
    asks_json String CODEC(LZ4),
    created_at DateTime64(3) DEFAULT now64() CODEC(LZ4),
    
    -- 索引优化
    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
    INDEX idx_spread spread TYPE minmax GRANULARITY 8
) ENGINE = ReplacingMergeTree(created_at)
PARTITION BY (toYYYYMMDD(timestamp), exchange)
ORDER BY (exchange, symbol, timestamp)
TTL created_at + INTERVAL 1 DAY
SETTINGS 
    index_granularity = 8192,
    merge_with_ttl_timeout = 3600,
    ttl_only_drop_parts = 1;

-- ==================== 冷存储表 (30天TTL) ====================

-- 冷存储交易数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.cold_trades (
    timestamp DateTime64(3) CODEC(ZSTD(3)),
    symbol LowCardinality(String) CODEC(ZSTD(3)),
    exchange LowCardinality(String) CODEC(ZSTD(3)),
    price Decimal64(8) CODEC(ZSTD(3)),
    amount Decimal64(8) CODEC(ZSTD(3)),
    side LowCardinality(String) CODEC(ZSTD(3)),
    trade_id String CODEC(ZSTD(3)),
    created_at DateTime64(3) DEFAULT now64() CODEC(ZSTD(3)),
    archived_at DateTime64(3) DEFAULT now64() CODEC(ZSTD(3)),

    -- 索引优化
    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
    INDEX idx_price price TYPE minmax GRANULARITY 8
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (exchange, symbol, timestamp)
TTL archived_at + INTERVAL 30 DAY
SETTINGS
    index_granularity = 8192,
    merge_with_ttl_timeout = 21600,
    ttl_only_drop_parts = 1;

-- 冷存储行情数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.cold_tickers (
    timestamp DateTime64(3) CODEC(ZSTD(3)),
    symbol LowCardinality(String) CODEC(ZSTD(3)),
    exchange LowCardinality(String) CODEC(ZSTD(3)),
    last_price Decimal64(8) CODEC(ZSTD(3)),
    volume_24h Decimal64(8) CODEC(ZSTD(3)),
    price_change_24h Decimal64(8) CODEC(ZSTD(3)),
    high_24h Decimal64(8) CODEC(ZSTD(3)),
    low_24h Decimal64(8) CODEC(ZSTD(3)),
    created_at DateTime64(3) DEFAULT now64() CODEC(ZSTD(3)),
    archived_at DateTime64(3) DEFAULT now64() CODEC(ZSTD(3)),

    -- 索引优化
    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
    INDEX idx_price last_price TYPE minmax GRANULARITY 8
) ENGINE = ReplacingMergeTree(archived_at)
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (exchange, symbol, timestamp)
TTL archived_at + INTERVAL 30 DAY
SETTINGS
    index_granularity = 8192,
    merge_with_ttl_timeout = 21600,
    ttl_only_drop_parts = 1;

-- 冷存储订单簿数据表
CREATE TABLE IF NOT EXISTS marketprism_cold.cold_orderbooks (
    timestamp DateTime64(3) CODEC(ZSTD(3)),
    symbol LowCardinality(String) CODEC(ZSTD(3)),
    exchange LowCardinality(String) CODEC(ZSTD(3)),
    best_bid Decimal64(8) CODEC(ZSTD(3)),
    best_ask Decimal64(8) CODEC(ZSTD(3)),
    spread Decimal64(8) CODEC(ZSTD(3)),
    bids_json String CODEC(ZSTD(3)),
    asks_json String CODEC(ZSTD(3)),
    created_at DateTime64(3) DEFAULT now64() CODEC(ZSTD(3)),
    archived_at DateTime64(3) DEFAULT now64() CODEC(ZSTD(3)),

    -- 索引优化
    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
    INDEX idx_spread spread TYPE minmax GRANULARITY 8
) ENGINE = ReplacingMergeTree(archived_at)
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (exchange, symbol, timestamp)
TTL archived_at + INTERVAL 30 DAY
SETTINGS
    index_granularity = 8192,
    merge_with_ttl_timeout = 21600,
    ttl_only_drop_parts = 1;

-- ==================== 归档状态表 ====================

-- 归档状态跟踪表
CREATE TABLE IF NOT EXISTS marketprism_cold.archive_status (
    archive_date Date CODEC(ZSTD(3)),
    data_type LowCardinality(String) CODEC(ZSTD(3)),
    exchange LowCardinality(String) CODEC(ZSTD(3)),
    records_archived UInt64 CODEC(ZSTD(3)),
    archive_size_bytes UInt64 CODEC(ZSTD(3)),
    archive_duration_seconds Float64 CODEC(ZSTD(3)),
    created_at DateTime64(3) DEFAULT now64() CODEC(ZSTD(3))
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(archive_date)
ORDER BY (archive_date, data_type, exchange)
TTL created_at + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
