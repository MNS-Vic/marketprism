-- MarketPrism 统一ClickHouse表初始化脚本
-- 创建所有市场数据相关的表和视图

-- 创建数据库
CREATE DATABASE IF NOT EXISTS marketprism;
USE marketprism;

-- ============================================================================
-- 0. 波动率指数数据表
-- ============================================================================

-- 执行波动率指数表创建脚本
SOURCE volatility_index_table_schema.sql;

-- ============================================================================
-- 1. 统一交易数据表
-- ============================================================================

-- 主表：统一交易数据
CREATE TABLE IF NOT EXISTS unified_trade_data
(
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    symbol_name String COMMENT '交易对名称',
    currency LowCardinality(String) COMMENT '币种名称',
    trade_id String COMMENT '交易ID',
    price Decimal64(8) COMMENT '成交价格',
    quantity Decimal64(8) COMMENT '成交数量',
    quote_quantity Nullable(Decimal64(8)) COMMENT '成交金额',
    side LowCardinality(String) COMMENT '交易方向',
    timestamp DateTime64(3, 'UTC') COMMENT '成交时间',
    trade_type LowCardinality(String) COMMENT '交易类型',
    is_maker Nullable(UInt8) COMMENT '是否为做市方',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, trade_type, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, trade_type, timestamp, trade_id)
TTL timestamp + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 2. 强平订单数据表
-- ============================================================================

-- 主表：强平订单数据
CREATE TABLE IF NOT EXISTS liquidations
(
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    symbol_name String COMMENT '交易对名称',
    currency LowCardinality(String) COMMENT '币种名称',
    liquidation_id String COMMENT '强平订单ID',
    price Decimal64(8) COMMENT '强平价格',
    quantity Decimal64(8) COMMENT '强平数量',
    side LowCardinality(String) COMMENT '强平方向',
    product_type LowCardinality(String) COMMENT '产品类型',
    timestamp DateTime64(3, 'UTC') COMMENT '强平时间',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, timestamp, liquidation_id)
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 3. 持仓量数据表
-- ============================================================================

-- 主表：持仓量数据
CREATE TABLE IF NOT EXISTS open_interest
(
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    symbol_name String COMMENT '交易对名称',
    currency LowCardinality(String) COMMENT '币种名称',
    open_interest Decimal64(8) COMMENT '持仓量',
    open_interest_value Nullable(Decimal64(8)) COMMENT '持仓价值',
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, timestamp)
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 4. 资金费率数据表
-- ============================================================================

-- 主表：资金费率数据
CREATE TABLE IF NOT EXISTS funding_rates
(
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    symbol_name String COMMENT '交易对名称',
    currency LowCardinality(String) COMMENT '币种名称',
    funding_rate Decimal64(8) COMMENT '资金费率',
    funding_time DateTime64(3, 'UTC') COMMENT '资金费率时间',
    next_funding_time Nullable(DateTime64(3, 'UTC')) COMMENT '下次资金费率时间',
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 5. 大户持仓比数据表
-- ============================================================================

-- 主表：大户持仓比数据
CREATE TABLE IF NOT EXISTS top_trader_long_short_ratio
(
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    symbol_name String COMMENT '交易对名称',
    currency LowCardinality(String) COMMENT '币种名称',
    long_short_ratio Decimal64(8) COMMENT '多空持仓比',
    long_position_ratio Nullable(Decimal64(8)) COMMENT '多仓持仓比例',
    short_position_ratio Nullable(Decimal64(8)) COMMENT '空仓持仓比例',
    period LowCardinality(String) COMMENT '时间周期',
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, period, timestamp)
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 6. 市场多空人数比数据表
-- ============================================================================

-- 主表：市场多空人数比数据
CREATE TABLE IF NOT EXISTS market_long_short_ratio
(
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    symbol_name String COMMENT '交易对名称',
    currency LowCardinality(String) COMMENT '币种名称',
    long_short_ratio Decimal64(8) COMMENT '多空人数比',
    long_account_ratio Nullable(Decimal64(8)) COMMENT '多仓人数比例',
    short_account_ratio Nullable(Decimal64(8)) COMMENT '空仓人数比例',
    period LowCardinality(String) COMMENT '时间周期',
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, period, timestamp)
TTL timestamp + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 7. 创建索引
-- ============================================================================

-- 交易数据索引
CREATE INDEX IF NOT EXISTS idx_trade_exchange_currency ON unified_trade_data (exchange_name, currency) TYPE minmax GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_trade_price ON unified_trade_data (price) TYPE minmax GRANULARITY 1;

-- 强平订单索引
CREATE INDEX IF NOT EXISTS idx_liquidation_exchange_currency ON liquidations (exchange_name, currency) TYPE minmax GRANULARITY 1;
CREATE INDEX IF NOT EXISTS idx_liquidation_price ON liquidations (price) TYPE minmax GRANULARITY 1;

-- 持仓量索引
CREATE INDEX IF NOT EXISTS idx_oi_exchange_currency ON open_interest (exchange_name, currency) TYPE minmax GRANULARITY 1;

-- 资金费率索引
CREATE INDEX IF NOT EXISTS idx_funding_exchange_currency ON funding_rates (exchange_name, currency) TYPE minmax GRANULARITY 1;

-- 大户持仓比索引
CREATE INDEX IF NOT EXISTS idx_top_trader_exchange_currency ON top_trader_long_short_ratio (exchange_name, currency) TYPE minmax GRANULARITY 1;

-- 市场人数比索引
CREATE INDEX IF NOT EXISTS idx_market_ratio_exchange_currency ON market_long_short_ratio (exchange_name, currency) TYPE minmax GRANULARITY 1;

-- ============================================================================
-- 8. 创建物化视图
-- ============================================================================

-- 交易数据分钟级聚合
CREATE MATERIALIZED VIEW IF NOT EXISTS trade_minute_stats
ENGINE = SummingMergeTree()
PARTITION BY (exchange_name, trade_type, toYYYYMM(minute))
ORDER BY (exchange_name, currency, symbol_name, trade_type, minute)
AS SELECT
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    toStartOfMinute(timestamp) as minute,
    argMin(price, timestamp) as open_price,
    argMax(price, timestamp) as close_price,
    max(price) as high_price,
    min(price) as low_price,
    sum(quantity) as total_volume,
    sum(quote_quantity) as total_quote_volume,
    count() as trade_count
FROM unified_trade_data
GROUP BY exchange_name, currency, symbol_name, trade_type, minute;

-- 强平订单小时级聚合
CREATE MATERIALIZED VIEW IF NOT EXISTS liquidation_hourly_stats
ENGINE = SummingMergeTree()
PARTITION BY (exchange_name, toYYYYMM(hour))
ORDER BY (exchange_name, currency, symbol_name, hour)
AS SELECT
    exchange_name,
    currency,
    symbol_name,
    toStartOfHour(timestamp) as hour,
    sum(quantity) as total_liquidated_volume,
    sumIf(quantity, side = 'long') as long_liquidated_volume,
    sumIf(quantity, side = 'short') as short_liquidated_volume,
    count() as liquidation_count
FROM liquidations
GROUP BY exchange_name, currency, symbol_name, hour;

-- ============================================================================
-- 9. 创建监控视图
-- ============================================================================

-- 最新交易数据
CREATE VIEW IF NOT EXISTS latest_trades AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    trade_type,
    price,
    quantity,
    side,
    timestamp
FROM unified_trade_data
WHERE timestamp >= now() - INTERVAL 1 HOUR
ORDER BY timestamp DESC
LIMIT 1000;

-- 最新强平订单
CREATE VIEW IF NOT EXISTS latest_liquidations AS
SELECT 
    exchange_name,
    currency,
    symbol_name,
    price,
    quantity,
    side,
    timestamp
FROM liquidations
WHERE timestamp >= now() - INTERVAL 1 HOUR
ORDER BY timestamp DESC
LIMIT 100;

-- 套利机会检测
CREATE VIEW IF NOT EXISTS arbitrage_opportunities AS
WITH price_comparison AS (
    SELECT 
        currency,
        symbol_name,
        trade_type,
        exchange_name,
        argMax(price, timestamp) as latest_price
    FROM unified_trade_data
    WHERE timestamp >= now() - INTERVAL 5 MINUTE
    GROUP BY currency, symbol_name, trade_type, exchange_name
)
SELECT 
    currency,
    symbol_name,
    trade_type,
    max(latest_price) as max_price,
    min(latest_price) as min_price,
    (max(latest_price) - min(latest_price)) / min(latest_price) * 100 as spread_percent
FROM price_comparison
GROUP BY currency, symbol_name, trade_type
HAVING count(DISTINCT exchange_name) >= 2 AND spread_percent > 0.5
ORDER BY spread_percent DESC;

-- ============================================================================
-- 10. 验证表创建
-- ============================================================================

-- 显示所有表
SHOW TABLES FROM marketprism;

-- 显示表大小统计
SELECT 
    table as table_name,
    formatReadableSize(total_bytes) as size,
    total_rows as rows
FROM system.tables 
WHERE database = 'marketprism'
ORDER BY table;

-- 完成提示
SELECT 'MarketPrism所有数据表初始化完成！' as status;
