#!/bin/bash
# 简化的修复验证脚本
set -euo pipefail

echo "=== MarketPrism 修复验证脚本 ==="

# 启动基础服务
echo "[1] 启动基础服务..."
cd services/message-broker
docker-compose -f docker-compose.nats.yml up -d >/dev/null 2>&1
cd ../data-storage-service
docker-compose -f docker-compose.hot-storage.yml up -d >/dev/null 2>&1
cd ../..

# 等待服务就绪
echo "[2] 等待服务就绪..."
for i in {1..15}; do
  if curl -s "http://localhost:8123/ping" >/dev/null 2>&1; then
    echo "✅ ClickHouse 就绪"
    break
  fi
  echo "等待 ClickHouse ($i/15)..."
  sleep 2
done

# 启动数据收集
echo "[3] 启动数据收集服务..."
cd services/data-storage-service
python simple_hot_storage.py > production.log 2>&1 &
STORAGE_PID=$!
cd ../data-collector
python unified_collector_main.py > collector.log 2>&1 &
COLLECTOR_PID=$!
cd ../..

echo "[4] 等待数据收集（30秒）..."
sleep 30

# 验证数据质量
echo "[5] 验证修复效果..."
ch() {
  curl -s "http://localhost:8123/" --data-binary "$1" 2>/dev/null || echo "connection_failed"
}

echo "5.1 funding_rates 修复验证："
ch "SELECT 
    count() as total_records,
    countIf(funding_rate > 0) as valid_records,
    countIf(funding_rate = 0) as zero_records,
    round(max(funding_rate), 8) as max_rate
FROM marketprism_hot.funding_rates 
WHERE timestamp > now() - INTERVAL 1 HOUR"

echo -e "\n5.2 liquidations 修复验证："
ch "SELECT 
    count() as total_records,
    countIf(price > 0 AND quantity > 0) as valid_records,
    countIf(price <= 0 OR quantity <= 0) as invalid_records,
    round(max(price), 2) as max_price
FROM marketprism_hot.liquidations 
WHERE timestamp > now() - INTERVAL 1 HOUR"

echo -e "\n[6] 清理服务..."
kill $COLLECTOR_PID $STORAGE_PID 2>/dev/null || true
sleep 2

cd services/message-broker
docker-compose -f docker-compose.nats.yml down >/dev/null 2>&1
cd ../data-storage-service
docker-compose -f docker-compose.hot-storage.yml down >/dev/null 2>&1
cd ../..

echo "✅ 验证完成"
