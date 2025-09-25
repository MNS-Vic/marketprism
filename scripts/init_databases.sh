#!/bin/bash
# MarketPrism数据库初始化脚本
# 逐个执行SQL语句避免多语句语法错误

set -euo pipefail

WORKSPACE_ROOT="/home/ubuntu/marketprism"

echo "=== MarketPrism数据库初始化 ==="

cd "$WORKSPACE_ROOT"
source venv/bin/activate

# 1. 创建数据库
echo "1. 创建数据库:"
curl -s "http://127.0.0.1:8123/" -d "CREATE DATABASE IF NOT EXISTS marketprism_hot"
curl -s "http://127.0.0.1:8123/" -d "CREATE DATABASE IF NOT EXISTS marketprism_cold"
echo "  ✅ 数据库创建完成"

# 2. 创建热端表
echo -e "\n2. 创建热端表:"

# 2.1 orderbooks表
echo "  创建orderbooks表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.orderbooks (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    last_update_id UInt64 CODEC(Delta, ZSTD),
    bids_count UInt32 CODEC(Delta, ZSTD),
    asks_count UInt32 CODEC(Delta, ZSTD),
    best_bid_price Decimal64(8) CODEC(ZSTD),
    best_ask_price Decimal64(8) CODEC(ZSTD),
    best_bid_quantity Decimal64(8) CODEC(ZSTD),
    best_ask_quantity Decimal64(8) CODEC(ZSTD),
    bids String CODEC(ZSTD),
    asks String CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, last_update_id)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

# 2.2 trades表
echo "  创建trades表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.trades (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    trade_id String CODEC(ZSTD),
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    is_maker Bool DEFAULT false CODEC(ZSTD),
    trade_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, trade_id)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

# 2.3 funding_rates表
echo "  创建funding_rates表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.funding_rates (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    funding_rate Decimal64(8) CODEC(ZSTD),
    funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

# 2.4 open_interests表
echo "  创建open_interests表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.open_interests (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    open_interest Decimal64(8) CODEC(ZSTD),
    open_interest_value Decimal64(8) CODEC(ZSTD),
    count UInt64 CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

# 2.5 liquidations表
echo "  创建liquidations表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.liquidations (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    liquidation_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

# 2.6 lsr_top_positions表
echo "  创建lsr_top_positions表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.lsr_top_positions (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    long_position_ratio Decimal64(8) CODEC(ZSTD),
    short_position_ratio Decimal64(8) CODEC(ZSTD),
    period LowCardinality(String) DEFAULT '5m' CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

# 2.7 lsr_all_accounts表
echo "  创建lsr_all_accounts表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.lsr_all_accounts (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    long_account_ratio Decimal64(8) CODEC(ZSTD),
    short_account_ratio Decimal64(8) CODEC(ZSTD),
    period LowCardinality(String) DEFAULT '5m' CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

# 2.8 volatility_indices表
echo "  创建volatility_indices表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_hot.volatility_indices (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    index_value Decimal64(8) CODEC(ZSTD),
    underlying_asset LowCardinality(String) CODEC(ZSTD),
    maturity_date Date CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192
"

echo "  ✅ 热端表创建完成"

# 3. 创建冷端表
echo -e "\n3. 创建冷端表:"

# 3.1 orderbooks表
echo "  创建冷端orderbooks表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.orderbooks (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    last_update_id UInt64,
    bids_count UInt32,
    asks_count UInt32,
    best_bid_price Decimal64(8),
    best_ask_price Decimal64(8),
    best_bid_quantity Decimal64(8),
    best_ask_quantity Decimal64(8),
    bids String,
    asks String,
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

# 3.2 trades表
echo "  创建冷端trades表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.trades (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    trade_id String,
    price Decimal64(8),
    quantity Decimal64(8),
    side LowCardinality(String),
    is_maker Bool DEFAULT false,
    trade_time DateTime64(3, 'UTC'),
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

# 3.3 funding_rates表
echo "  创建冷端funding_rates表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.funding_rates (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    funding_rate Decimal64(8),
    funding_time DateTime64(3, 'UTC'),
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

# 3.4 open_interests表
echo "  创建冷端open_interests表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.open_interests (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    open_interest Decimal64(8),
    open_interest_value Decimal64(8),
    count UInt64,
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

# 3.5 liquidations表
echo "  创建冷端liquidations表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.liquidations (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    side LowCardinality(String),
    price Decimal64(8),
    quantity Decimal64(8),
    liquidation_time DateTime64(3, 'UTC'),
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

# 3.6 lsr_top_positions表
echo "  创建冷端lsr_top_positions表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_top_positions (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    long_position_ratio Decimal64(8),
    short_position_ratio Decimal64(8),
    period LowCardinality(String) DEFAULT '5m',
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

# 3.7 lsr_all_accounts表
echo "  创建冷端lsr_all_accounts表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.lsr_all_accounts (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    long_account_ratio Decimal64(8),
    short_account_ratio Decimal64(8),
    period LowCardinality(String) DEFAULT '5m',
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

# 3.8 volatility_indices表
echo "  创建冷端volatility_indices表..."
curl -s "http://127.0.0.1:8123/" -d "
CREATE TABLE IF NOT EXISTS marketprism_cold.volatility_indices (
    timestamp DateTime64(3, 'UTC'),
    exchange LowCardinality(String),
    market_type LowCardinality(String),
    symbol LowCardinality(String),
    index_value Decimal64(8),
    underlying_asset LowCardinality(String),
    maturity_date Date,
    data_source LowCardinality(String) DEFAULT 'marketprism',
    created_at DateTime64(3) DEFAULT now64()
) ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (exchange, symbol, timestamp)
TTL toDateTime(timestamp) + INTERVAL 365 DAY
"

echo "  ✅ 冷端表创建完成"

# 4. 验证表结构
echo -e "\n4. 验证表结构:"
echo "  热端表:"
curl -s "http://127.0.0.1:8123/?query=SHOW%20TABLES%20FROM%20marketprism_hot" | while read table; do
    echo "    ✅ $table"
done

echo "  冷端表:"
curl -s "http://127.0.0.1:8123/?query=SHOW%20TABLES%20FROM%20marketprism_cold" | while read table; do
    echo "    ✅ $table"
done

# 5. 验证DateTime64精度
echo -e "\n5. 验证DateTime64精度:"
for table in funding_rates liquidations open_interests lsr_top_positions lsr_all_accounts volatility_indices; do
    created_at_type=$(curl -s "http://127.0.0.1:8123/?query=SELECT%20type%20FROM%20system.columns%20WHERE%20database%3D%27marketprism_cold%27%20AND%20table%3D%27$table%27%20AND%20name%3D%27created_at%27" 2>/dev/null || echo "N/A")
    if [[ "$created_at_type" == *"DateTime64(3)"* ]]; then
        echo "  ✅ $table: $created_at_type"
    else
        echo "  ❌ $table: $created_at_type (应为DateTime64(3))"
    fi
done

echo -e "\n=== ✅ 数据库初始化完成 ==="
