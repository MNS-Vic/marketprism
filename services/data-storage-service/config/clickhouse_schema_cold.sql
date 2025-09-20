-- MarketPrism 冷端 ClickHouse 表结构
-- 冷端用于长期存储，采取更激进的压缩与更长TTL

CREATE DATABASE IF NOT EXISTS marketprism_cold;

-- 通用引擎参数
-- 使用 ZSTD 压缩，固定分区按天，主键与排序键与热端一致，TTL 更长（365 天）

-- 订单簿（快照+关键字段）
CREATE TABLE IF NOT EXISTS marketprism_cold.orderbooks (
    timestamp          DateTime('UTC'),
    exchange           String,
    market_type        String,
    symbol             String,
    last_update_id     UInt64,
    bids_count         UInt32,
    asks_count         UInt32,
    best_bid_price     Float64,
    best_ask_price     Float64,
    best_bid_quantity  Float64,
    best_ask_quantity  Float64,
    bids               String,
    asks               String,
    data_source        String DEFAULT 'marketprism',
    created_at         DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
;

-- 交易
CREATE TABLE IF NOT EXISTS marketprism_cold.trades
(
    timestamp  DateTime('UTC'),
    exchange   String,
    symbol     String,
    price      Float64,
    quantity   Float64,
    side       String,
    trade_id   String
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
;

-- 资金费率
CREATE TABLE IF NOT EXISTS marketprism_cold.funding_rates
(
    timestamp     DateTime('UTC'),
    exchange      String,
    symbol        String,
    funding_rate  Float64
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
;

-- 未平仓量
CREATE TABLE IF NOT EXISTS marketprism_cold.open_interests
(
    timestamp    DateTime('UTC'),
    exchange     String,
    symbol       String,
    open_interest Float64
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
;

-- 强平
CREATE TABLE IF NOT EXISTS marketprism_cold.liquidations
(
    timestamp DateTime('UTC'),
    exchange  String,
    symbol    String,
    price     Float64,
    quantity  Float64,
    side      String
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
;

-- LSR 顶级持仓比例
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_top_positions
(
    timestamp DateTime('UTC'),
    exchange  String,
    symbol    String,
    long_ratio Float64,
    short_ratio Float64
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
;

-- LSR 全市场多空人数比例
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_all_accounts
(
    timestamp DateTime('UTC'),
    exchange  String,
    symbol    String,
    long_accounts Float64,
    short_accounts Float64
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
;

-- 波动率指数
CREATE TABLE IF NOT EXISTS marketprism_cold.volatility_indices
(
    timestamp DateTime('UTC'),
    exchange  String,
    symbol    String,
    value     Float64
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192
;

