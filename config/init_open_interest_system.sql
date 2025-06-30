-- MarketPrism 持仓量系统完整初始化脚本
-- 包含强平订单和持仓量数据的所有表结构

-- 1. 创建数据库
CREATE DATABASE IF NOT EXISTS marketprism;
USE marketprism;

-- 2. 创建强平订单表 (如果不存在)
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
    
    -- 价格和数量信息
    price Decimal64(8) COMMENT '强平价格',
    quantity Decimal64(8) COMMENT '强平数量',
    filled_quantity Decimal64(8) COMMENT '已成交数量',
    average_price Nullable(Decimal64(8)) COMMENT '平均成交价格',
    notional_value Decimal64(8) COMMENT '名义价值',
    
    -- 时间信息
    liquidation_time DateTime64(3, 'UTC') COMMENT '强平时间',
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间戳',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    
    -- 扩展信息
    margin_ratio Nullable(Decimal64(8)) COMMENT '保证金率',
    bankruptcy_price Nullable(Decimal64(8)) COMMENT '破产价格',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(liquidation_time))
ORDER BY (exchange_name, symbol_name, liquidation_time, liquidation_id)
TTL liquidation_time + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
COMMENT '强平订单数据表';

-- 3. 创建持仓量数据表
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
    
    -- 原始数据
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, symbol_name, product_type, timestamp)
TTL timestamp + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
COMMENT '持仓量数据表';

-- 4. 创建索引
-- 强平订单索引
CREATE INDEX IF NOT EXISTS idx_liquidation_exchange_symbol ON liquidations (exchange_name, symbol_name) TYPE minmax GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_liquidation_product_type ON liquidations (product_type) TYPE set(10) GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_liquidation_notional_value ON liquidations (notional_value) TYPE minmax GRANULARITY 1;

-- 持仓量索引
CREATE INDEX IF NOT EXISTS idx_open_interest_exchange_symbol ON open_interest (exchange_name, symbol_name) TYPE minmax GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_open_interest_product_type ON open_interest (product_type) TYPE set(10) GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_open_interest_value ON open_interest (open_interest_value) TYPE minmax GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_open_interest_usd ON open_interest (open_interest_usd) TYPE minmax GRANULARITY 1;

-- 5. 创建物化视图
-- 强平订单小时统计
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
    sell_count UInt64
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
    countIf(side = 'sell') as sell_count
FROM liquidations
GROUP BY exchange_name, symbol_name, product_type, hour;

-- 持仓量小时统计
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
    data_points UInt64
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
    count() as data_points
FROM open_interest
GROUP BY exchange_name, symbol_name, product_type, hour;

-- 6. 创建监控视图
-- 最新强平订单
CREATE VIEW IF NOT EXISTS recent_liquidations AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    side,
    price,
    quantity,
    notional_value,
    liquidation_time
FROM liquidations
WHERE liquidation_time >= now() - INTERVAL 1 HOUR
ORDER BY liquidation_time DESC;

-- 最新持仓量
CREATE VIEW IF NOT EXISTS latest_open_interest AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    open_interest_value,
    open_interest_usd,
    change_24h_percent,
    timestamp
FROM open_interest
WHERE timestamp >= now() - INTERVAL 1 HOUR
ORDER BY exchange_name, symbol_name, timestamp DESC;

-- 持仓量排行榜
CREATE VIEW IF NOT EXISTS open_interest_rankings AS
SELECT 
    exchange_name,
    symbol_name,
    product_type,
    open_interest_value,
    open_interest_usd,
    change_24h_percent,
    timestamp
FROM (
    SELECT 
        exchange_name,
        symbol_name,
        product_type,
        open_interest_value,
        open_interest_usd,
        change_24h_percent,
        timestamp,
        ROW_NUMBER() OVER (PARTITION BY exchange_name, symbol_name, product_type ORDER BY timestamp DESC) as rn
    FROM open_interest
    WHERE timestamp >= now() - INTERVAL 2 HOUR
) ranked
WHERE rn = 1
ORDER BY open_interest_usd DESC NULLS LAST;

-- 7. 验证表创建
SELECT 
    'Tables Created' as status,
    count() as table_count
FROM system.tables 
WHERE database = 'marketprism' 
  AND name IN ('liquidations', 'open_interest', 'liquidations_hourly_stats', 'open_interest_hourly_stats');

-- 8. 显示所有相关表
SHOW TABLES FROM marketprism;

-- 完成提示
SELECT 'MarketPrism持仓量系统初始化完成！包含强平订单和持仓量数据处理功能。' as status;
