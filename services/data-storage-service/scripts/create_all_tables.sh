#!/bin/bash
# MarketPrism ClickHouse 所有表创建脚本 - 简化版
# 🔄 Docker部署简化改造 (2025-08-02)

set -e

CLICKHOUSE_HOST=${CLICKHOUSE_HOST:-localhost}
CLICKHOUSE_PORT=${CLICKHOUSE_PORT:-8123}
DATABASE=${CLICKHOUSE_DATABASE:-marketprism_hot}

echo "🔧 创建MarketPrism ClickHouse热存储表 (8种数据类型)..."
echo "主机: $CLICKHOUSE_HOST:$CLICKHOUSE_PORT"
echo "数据库: $DATABASE"

# 创建数据库
echo "📋 创建数据库: $DATABASE"
curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_PORT/" \
    --data "CREATE DATABASE IF NOT EXISTS $DATABASE"

# 创建表的函数
create_table() {
    local table_name=$1
    local sql=$2
    
    echo "📋 创建表: $table_name"
    curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_PORT/" --data "$sql"
    
    if [ $? -eq 0 ]; then
        echo "✅ 表创建成功: $table_name"
    else
        echo "❌ 表创建失败: $table_name"
        return 1
    fi
}

# 1. 订单簿数据表
create_table "orderbooks" "
CREATE TABLE IF NOT EXISTS $DATABASE.orderbooks (
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    last_update_id UInt64 CODEC(Delta, ZSTD),
    best_bid_price Decimal64(8) CODEC(ZSTD),
    best_ask_price Decimal64(8) CODEC(ZSTD),
    bids String CODEC(ZSTD),
    asks String CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, last_update_id)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

# 2. 交易数据表
create_table "trades" "
CREATE TABLE IF NOT EXISTS $DATABASE.trades (
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    trade_id String CODEC(ZSTD),
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, trade_id)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

# 3. 资金费率数据表
create_table "funding_rates" "
CREATE TABLE IF NOT EXISTS $DATABASE.funding_rates (
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    funding_rate Decimal64(8) CODEC(ZSTD),
    funding_time DateTime CODEC(Delta, ZSTD),
    next_funding_time DateTime CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

# 4. 未平仓量数据表
create_table "open_interests" "
CREATE TABLE IF NOT EXISTS $DATABASE.open_interests (
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    open_interest Decimal64(8) CODEC(ZSTD),
    open_interest_value Decimal64(8) CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

# 5. 强平数据表
create_table "liquidations" "
CREATE TABLE IF NOT EXISTS $DATABASE.liquidations (
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    price Decimal64(8) CODEC(ZSTD),
    quantity Decimal64(8) CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

# 6. LSR顶级持仓比例数据表
create_table "lsr_top_positions" "
CREATE TABLE IF NOT EXISTS $DATABASE.lsr_top_positions (
    timestamp DateTime CODEC(Delta, ZSTD),
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
ORDER BY (timestamp, exchange, symbol, period)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

# 7. LSR全账户比例数据表
create_table "lsr_all_accounts" "
CREATE TABLE IF NOT EXISTS $DATABASE.lsr_all_accounts (
    timestamp DateTime CODEC(Delta, ZSTD),
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
ORDER BY (timestamp, exchange, symbol, period)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

# 8. 波动率指数数据表
create_table "volatility_indices" "
CREATE TABLE IF NOT EXISTS $DATABASE.volatility_indices (
    timestamp DateTime CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    index_value Decimal64(8) CODEC(ZSTD),
    underlying_asset LowCardinality(String) CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
)
ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL timestamp + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192"

echo "🎉 所有8个表创建完成！"
echo "📊 验证表结构..."

# 验证表是否创建成功
echo "数据库中的表:"
curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_PORT/" \
    --data "SELECT name FROM system.tables WHERE database = '$DATABASE' ORDER BY name"

echo ""
echo "✅ MarketPrism热存储表创建完成！支持8种数据类型："
echo "  1. orderbooks (订单簿)"
echo "  2. trades (交易)"
echo "  3. funding_rates (资金费率)"
echo "  4. open_interests (未平仓量)"
echo "  5. liquidations (强平)"
echo "  6. lsr_top_positions (LSR顶级持仓)"
echo "  7. lsr_all_accounts (LSR全账户)"
echo "  8. volatility_indices (波动率指数)"
