-- MarketPrism 强平订单表初始化脚本
-- 执行此脚本来创建强平订单相关的所有表和视图

-- 1. 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS marketprism;

-- 2. 使用数据库
USE marketprism;

-- 3. 创建主表：强平订单数据
CREATE TABLE IF NOT EXISTS liquidations
(
    -- 基础信息
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    symbol_name String COMMENT '交易对名称 (标准格式: BTC-USDT)',
    product_type LowCardinality(String) COMMENT '产品类型: margin/swap/futures',
    instrument_id String COMMENT '产品ID',
    
    -- 强平订单信息
    liquidation_id String COMMENT '强平订单ID',
    side LowCardinality(String) COMMENT '强平方向: buy/sell',
    status LowCardinality(String) COMMENT '强平状态: filled/partially_filled/cancelled/pending',
    
    -- 价格和数量信息 (使用Decimal64保持精度)
    price Decimal64(8) COMMENT '强平价格',
    quantity Decimal64(8) COMMENT '强平数量',
    filled_quantity Decimal64(8) COMMENT '已成交数量',
    average_price Nullable(Decimal64(8)) COMMENT '平均成交价格',
    
    -- 金额信息
    notional_value Decimal64(8) COMMENT '名义价值 (价格 × 数量)',
    
    -- 时间信息
    liquidation_time DateTime64(3, 'UTC') COMMENT '强平时间',
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间戳',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    
    -- 扩展信息
    margin_ratio Nullable(Decimal64(8)) COMMENT '保证金率 (仅OKX提供)',
    bankruptcy_price Nullable(Decimal64(8)) COMMENT '破产价格',
    
    -- 原始数据 (JSON格式存储)
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(liquidation_time))
ORDER BY (exchange_name, symbol_name, liquidation_time, liquidation_id)
TTL liquidation_time + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
COMMENT '强平订单数据表 - 存储OKX和Binance的强平订单信息';

-- 4. 创建索引以优化查询性能
-- 按交易所和交易对查询的索引
CREATE INDEX IF NOT EXISTS idx_exchange_symbol ON liquidations (exchange_name, symbol_name) TYPE minmax GRANULARITY 1;

-- 按产品类型查询的索引
CREATE INDEX IF NOT EXISTS idx_product_type ON liquidations (product_type) TYPE set(10) GRANULARITY 1;

-- 按强平方向查询的索引
CREATE INDEX IF NOT EXISTS idx_side ON liquidations (side) TYPE set(2) GRANULARITY 1;

-- 按名义价值范围查询的索引 (用于大额强平监控)
CREATE INDEX IF NOT EXISTS idx_notional_value ON liquidations (notional_value) TYPE minmax GRANULARITY 1;

-- 5. 创建物化视图：按小时聚合的强平统计
CREATE MATERIALIZED VIEW IF NOT EXISTS liquidations_hourly_stats
(
    exchange_name LowCardinality(String),
    symbol_name String,
    product_type LowCardinality(String),
    hour DateTime,
    liquidation_count UInt64,
    total_volume Decimal64(8),
    total_notional Decimal64(8),
    avg_price Decimal64(8),
    buy_count UInt64,
    sell_count UInt64,
    buy_volume Decimal64(8),
    sell_volume Decimal64(8)
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (exchange_name, symbol_name, product_type, hour)
TTL hour + INTERVAL 180 DAY
AS SELECT
    exchange_name,
    symbol_name,
    product_type,
    toStartOfHour(liquidation_time) as hour,
    count() as liquidation_count,
    sum(quantity) as total_volume,
    sum(notional_value) as total_notional,
    avg(price) as avg_price,
    countIf(side = 'buy') as buy_count,
    countIf(side = 'sell') as sell_count,
    sumIf(quantity, side = 'buy') as buy_volume,
    sumIf(quantity, side = 'sell') as sell_volume
FROM liquidations
GROUP BY exchange_name, symbol_name, product_type, hour;

-- 6. 创建物化视图：大额强平监控 (名义价值 > 100,000 USD)
CREATE MATERIALIZED VIEW IF NOT EXISTS large_liquidations
(
    exchange_name LowCardinality(String),
    symbol_name String,
    product_type LowCardinality(String),
    liquidation_id String,
    side LowCardinality(String),
    price Decimal64(8),
    quantity Decimal64(8),
    notional_value Decimal64(8),
    liquidation_time DateTime64(3, 'UTC'),
    margin_ratio Nullable(Decimal64(8))
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(liquidation_time)
ORDER BY (liquidation_time, notional_value)
TTL liquidation_time + INTERVAL 365 DAY
AS SELECT
    exchange_name,
    symbol_name,
    product_type,
    liquidation_id,
    side,
    price,
    quantity,
    notional_value,
    liquidation_time,
    margin_ratio
FROM liquidations
WHERE notional_value >= 100000;

-- 7. 创建用于监控的视图
-- 实时强平监控视图 (最近1小时)
CREATE VIEW IF NOT EXISTS recent_liquidations AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    side,
    price,
    quantity,
    notional_value,
    liquidation_time,
    margin_ratio
FROM liquidations
WHERE liquidation_time >= now() - INTERVAL 1 HOUR
ORDER BY liquidation_time DESC;

-- 强平统计概览视图 (最近24小时)
CREATE VIEW IF NOT EXISTS liquidation_summary_24h AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    count() as liquidation_count,
    sum(notional_value) as total_notional,
    avg(price) as avg_price,
    countIf(side = 'buy') as buy_count,
    countIf(side = 'sell') as sell_count,
    max(notional_value) as max_liquidation,
    min(liquidation_time) as first_liquidation,
    max(liquidation_time) as last_liquidation
FROM liquidations
WHERE liquidation_time >= now() - INTERVAL 24 HOUR
GROUP BY exchange_name, symbol_name, product_type
ORDER BY total_notional DESC;

-- 杠杆交易强平专用视图 (仅OKX数据)
CREATE VIEW IF NOT EXISTS margin_liquidations AS
SELECT 
    exchange_name,
    symbol_name,
    liquidation_id,
    side,
    price,
    quantity,
    notional_value,
    margin_ratio,
    liquidation_time
FROM liquidations
WHERE product_type = 'margin'
  AND exchange_name = 'okx'  -- 仅OKX支持杠杆交易强平订单
ORDER BY liquidation_time DESC;

-- 8. 验证表创建
SELECT 
    'liquidations' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'liquidations'
UNION ALL
SELECT 
    'liquidations_hourly_stats' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'liquidations_hourly_stats'
UNION ALL
SELECT 
    'large_liquidations' as table_name,
    count() as row_count,
    formatReadableSize(sum(data_compressed_bytes)) as compressed_size,
    formatReadableSize(sum(data_uncompressed_bytes)) as uncompressed_size
FROM system.parts 
WHERE database = 'marketprism' AND table = 'large_liquidations';

-- 9. 显示创建的表和视图
SHOW TABLES FROM marketprism LIKE '%liquidation%';

-- 10. 显示表结构
DESCRIBE TABLE liquidations;

-- 完成提示
SELECT 'MarketPrism强平订单表初始化完成！' as status;
