#!/usr/bin/env bash
set -euo pipefail

# MarketPrism: 检查各类数据入库情况
# 用途：验证 8 种数据类型在 ClickHouse 中的入库状态

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "=== MarketPrism 数据入库检查 ==="
echo "时间: $(date)"
echo

# 定义 8 种数据类型
declare -a data_types=("trades" "orderbooks" "funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")

echo "1. 各数据类型入库行数统计:"
echo "=============================="
total_rows=0

for table in "${data_types[@]}"; do
    count=$(docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT count() FROM marketprism_hot.$table" 2>/dev/null || echo "0")
    printf "%-20s: %'d 行\n" "$table" "$count"
    total_rows=$((total_rows + count))
done

echo "=============================="
printf "%-20s: %'d 行\n" "总计" "$total_rows"
echo

echo "2. 各数据类型最新数据时间:"
echo "=============================="
for table in "${data_types[@]}"; do
    latest=$(docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT max(timestamp) FROM marketprism_hot.$table" 2>/dev/null || echo "无数据")
    printf "%-20s: %s\n" "$table" "$latest"
done
echo

echo "3. 各交易所数据分布:"
echo "===================="
for table in "${data_types[@]}"; do
    echo "--- $table ---"
    docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT exchange, count() as cnt FROM marketprism_hot.$table GROUP BY exchange ORDER BY cnt DESC" 2>/dev/null || echo "查询失败"
    echo
done

echo "4. 各交易对数据分布 (前10):"
echo "=========================="
for table in "${data_types[@]}"; do
    echo "--- $table ---"
    docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT symbol, count() as cnt FROM marketprism_hot.$table GROUP BY symbol ORDER BY cnt DESC LIMIT 10" 2>/dev/null || echo "查询失败"
    echo
done

echo "5. 数据时间分布 (最近24小时):"
echo "============================"
for table in "${data_types[@]}"; do
    echo "--- $table ---"
    docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT toHour(timestamp) as hour, count() as cnt FROM marketprism_hot.$table WHERE timestamp >= now() - INTERVAL 24 HOUR GROUP BY hour ORDER BY hour" 2>/dev/null || echo "查询失败"
    echo
done

echo "检查完成！详细结果已保存到控制台输出。"
