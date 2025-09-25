#!/usr/bin/env bash
set -euo pipefail

# MarketPrism: 验证容器化全链路状态
# 用途：检查 NATS、ClickHouse、Storage、Collector 的健康状态与数据流

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "=== MarketPrism 全链路状态验证 ==="
echo "时间: $(date)"
echo

# 1) 容器状态
echo "1. 容器运行状态:"
echo "----------------"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" > "$LOG_DIR/_containers.out" 2>&1 || true
cat "$LOG_DIR/_containers.out" || echo "无法获取容器状态"
echo

# 2) NATS 健康与流状态
echo "2. NATS JetStream 状态:"
echo "------------------------"
if curl -sf http://localhost:8222/healthz >/dev/null 2>&1; then
    echo "✅ NATS 健康检查通过"
    curl -s http://localhost:8222/jsz?streams=1 > "$LOG_DIR/_jsz_current.json" 2>&1 || true
    if [ -f "$LOG_DIR/_jsz_current.json" ]; then
        echo "流统计:"
        grep -E '"name"|"messages"|"consumer_count"' "$LOG_DIR/_jsz_current.json" | head -20 || true
    fi
else
    echo "❌ NATS 健康检查失败"
fi
echo

# 3) ClickHouse 健康与表状态
echo "3. ClickHouse 状态:"
echo "-------------------"
if curl -sf http://localhost:8123/ping >/dev/null 2>&1; then
    echo "✅ ClickHouse 健康检查通过"
    
    # 检查数据库
    echo "数据库列表:"
    docker exec marketprism-clickhouse-hot clickhouse-client --query "SHOW DATABASES" > "$LOG_DIR/_databases.out" 2>&1 || true
    cat "$LOG_DIR/_databases.out" | grep -E "marketprism|default" || echo "无法获取数据库列表"
    
    # 检查表
    echo "热存储表列表:"
    docker exec marketprism-clickhouse-hot clickhouse-client --query "SHOW TABLES FROM marketprism_hot" > "$LOG_DIR/_tables.out" 2>&1 || true
    cat "$LOG_DIR/_tables.out" || echo "无法获取表列表"
    
    # 简单计数检查（避免复杂查询）
    echo "表行数检查:"
    for table in trades orderbooks funding_rates open_interests liquidations lsr_top_positions lsr_all_accounts volatility_indices; do
        count=$(docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT count() FROM marketprism_hot.$table" 2>/dev/null || echo "0")
        printf "  %-20s: %s\n" "$table" "$count"
    done
else
    echo "❌ ClickHouse 健康检查失败"
fi
echo

# 4) Storage 服务健康
echo "4. Storage 服务状态:"
echo "--------------------"
if curl -sf http://localhost:18080/health >/dev/null 2>&1; then
    echo "✅ Storage 服务健康检查通过"
    curl -s http://localhost:18080/health > "$LOG_DIR/_storage_health.json" 2>&1 || true
    if [ -f "$LOG_DIR/_storage_health.json" ]; then
        echo "健康详情:"
        cat "$LOG_DIR/_storage_health.json" | head -10 || true
    fi
else
    echo "❌ Storage 服务健康检查失败"
fi
echo

# 5) Collector 健康
echo "5. Data Collector 状态:"
echo "-----------------------"
if curl -sf http://localhost:8086/health >/dev/null 2>&1; then
    echo "✅ Collector 健康检查通过 (8086)"
    curl -s http://localhost:8086/health > "$LOG_DIR/_collector_health.json" 2>&1 || true
elif curl -sf http://localhost:8087/health >/dev/null 2>&1; then
    echo "✅ Collector 健康检查通过 (8087)"
    curl -s http://localhost:8087/health > "$LOG_DIR/_collector_health.json" 2>&1 || true
else
    echo "❌ Collector 健康检查失败"
fi

if [ -f "$LOG_DIR/_collector_health.json" ]; then
    echo "健康详情:"
    cat "$LOG_DIR/_collector_health.json" | head -10 || true
fi
echo

# 6) 总结
echo "6. 验证总结:"
echo "------------"
nats_ok=$(curl -sf http://localhost:8222/healthz >/dev/null 2>&1 && echo "✅" || echo "❌")
clickhouse_ok=$(curl -sf http://localhost:8123/ping >/dev/null 2>&1 && echo "✅" || echo "❌")
storage_ok=$(curl -sf http://localhost:18080/health >/dev/null 2>&1 && echo "✅" || echo "❌")
collector_ok=$((curl -sf http://localhost:8086/health >/dev/null 2>&1 || curl -sf http://localhost:8087/health >/dev/null 2>&1) && echo "✅" || echo "❌")

echo "NATS JetStream:     $nats_ok"
echo "ClickHouse:         $clickhouse_ok"
echo "Storage Service:    $storage_ok"
echo "Data Collector:     $collector_ok"
echo
echo "详细日志保存在: $LOG_DIR/"
echo "- _containers.out: 容器状态"
echo "- _jsz_current.json: NATS 流状态"
echo "- _databases.out, _tables.out: ClickHouse 结构"
echo "- _storage_health.json, _collector_health.json: 服务健康详情"
