-- MarketPrism 强平订单数据表结构
-- 用于存储来自OKX和Binance的强平订单数据
-- 
-- 重要说明：
-- 1. 杠杆交易强平订单：仅OKX支持按symbol订阅
-- 2. 永续合约强平订单：OKX和Binance都支持
-- 3. 期货合约强平订单：OKX和Binance都支持

-- 主表：强平订单数据
CREATE TABLE IF NOT EXISTS marketprism.liquidations
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

-- 创建索引以优化查询性能
-- 1. 按交易所和交易对查询的索引
CREATE INDEX IF NOT EXISTS idx_exchange_symbol ON marketprism.liquidations (exchange_name, symbol_name) TYPE minmax GRANULARITY 1;

-- 2. 按产品类型查询的索引
CREATE INDEX IF NOT EXISTS idx_product_type ON marketprism.liquidations (product_type) TYPE set(10) GRANULARITY 1;

-- 3. 按强平方向查询的索引
CREATE INDEX IF NOT EXISTS idx_side ON marketprism.liquidations (side) TYPE set(2) GRANULARITY 1;

-- 4. 按名义价值范围查询的索引 (用于大额强平监控)
CREATE INDEX IF NOT EXISTS idx_notional_value ON marketprism.liquidations (notional_value) TYPE minmax GRANULARITY 1;

-- 分布式表 (如果使用ClickHouse集群)
CREATE TABLE IF NOT EXISTS marketprism.liquidations_distributed AS marketprism.liquidations
ENGINE = Distributed('marketprism_cluster', 'marketprism', 'liquidations', rand());

-- 物化视图：按小时聚合的强平统计
CREATE MATERIALIZED VIEW IF NOT EXISTS marketprism.liquidations_hourly_stats
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
FROM marketprism.liquidations
GROUP BY exchange_name, symbol_name, product_type, hour;

-- 物化视图：大额强平监控 (名义价值 > 100,000 USD)
CREATE MATERIALIZED VIEW IF NOT EXISTS marketprism.large_liquidations
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
FROM marketprism.liquidations
WHERE notional_value >= 100000;

-- 创建用于监控的视图
-- 1. 实时强平监控视图 (最近1小时)
CREATE VIEW IF NOT EXISTS marketprism.recent_liquidations AS
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
FROM marketprism.liquidations
WHERE liquidation_time >= now() - INTERVAL 1 HOUR
ORDER BY liquidation_time DESC;

-- 2. 强平统计概览视图 (最近24小时)
CREATE VIEW IF NOT EXISTS marketprism.liquidation_summary_24h AS
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
FROM marketprism.liquidations
WHERE liquidation_time >= now() - INTERVAL 24 HOUR
GROUP BY exchange_name, symbol_name, product_type
ORDER BY total_notional DESC;

-- 3. 杠杆交易强平专用视图 (仅OKX数据)
CREATE VIEW IF NOT EXISTS marketprism.margin_liquidations AS
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
FROM marketprism.liquidations
WHERE product_type = 'margin'
  AND exchange_name = 'okx'  -- 仅OKX支持杠杆交易强平订单
ORDER BY liquidation_time DESC;

-- 插入示例数据 (用于测试)
-- INSERT INTO marketprism.liquidations VALUES
-- (
--     'okx',                              -- exchange_name
--     'BTC-USDT',                        -- symbol_name
--     'margin',                          -- product_type
--     'BTC-USDT',                        -- instrument_id
--     '123456789',                       -- liquidation_id
--     'sell',                            -- side
--     'filled',                          -- status
--     45000.5,                           -- price
--     0.1,                               -- quantity
--     0.1,                               -- filled_quantity
--     45000.5,                           -- average_price
--     4500.05,                           -- notional_value
--     '2023-01-01 00:00:00',            -- liquidation_time
--     '2023-01-01 00:00:00',            -- timestamp
--     now(),                             -- collected_at
--     0.02,                              -- margin_ratio
--     45000.5,                           -- bankruptcy_price
--     '{"raw": "data"}'                  -- raw_data
-- );

-- 授权语句 (根据实际用户调整)
-- GRANT SELECT ON marketprism.liquidations TO readonly_user;
-- GRANT INSERT ON marketprism.liquidations TO data_collector;
-- GRANT ALL ON marketprism.liquidations TO admin_user;
