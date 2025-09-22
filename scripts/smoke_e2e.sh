#!/usr/bin/env bash
# MarketPrism 一键端到端烟测脚本（测试环境）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$ROOT_DIR"

# 启用虚拟环境（如存在）
if [ -d "venv" ]; then
  source venv/bin/activate
elif [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# 选择 docker compose 命令（兼容 docker-compose 与 docker compose）
DC="docker-compose"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DC="docker compose"
fi

cleanup() {
  echo "\n[cleanup] 开始清理..."
  set +e
  pkill -f "services/data-storage-service/main.py" 2>/dev/null
  pkill -f "services/data-collector/unified_collector_main.py" 2>/dev/null
  if [ "${KEEP_RUNNING:-0}" != "1" ]; then
    $DC -f services/message-broker/docker-compose.nats.yml down -v || true
    # ClickHouse 如果不希望停止，请设置 KEEP_CH=1
    if [ "${KEEP_CH:-0}" != "1" ]; then
      $DC -f services/data-storage-service/docker-compose.hot-storage.yml down || true
    fi
  fi
  set -e
  echo "[cleanup] 完成"
}
trap cleanup EXIT
# 0) 预清理可能存在的同名容器，避免 container_name 冲突
(docker rm -f marketprism-nats >/dev/null 2>&1) || true



# 1) 启动 NATS
$DC -f services/message-broker/docker-compose.nats.yml up -d
# 等待 NATS 就绪
for i in {1..30}; do
  if curl -sf http://localhost:8222/healthz >/dev/null; then
    echo "[nats] healthz ok"
    break
  fi
  echo "[nats] waiting ($i) ..."; sleep 1
  if [ "$i" = "30" ]; then echo "[nats] health check timeout"; exit 1; fi
done

# 2) 启动 ClickHouse（仅热点库）
$DC -f services/data-storage-service/docker-compose.hot-storage.yml up -d clickhouse-hot

# 3) 启动 Collector（launcher）
nohup python3 services/data-collector/unified_collector_main.py --mode launcher \
  > services/data-collector/collector.log 2>&1 &
# 给 Collector 3 秒创建 JetStream 流
sleep 3

# 4) 启动简化热存储（simple_hot_storage）
nohup env NATS_URL="${NATS_URL:-nats://localhost:4222}" \
  CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-localhost}" \
  CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}" \
  CLICKHOUSE_DATABASE="${CLICKHOUSE_DATABASE:-marketprism_hot}" \
  python3 services/data-storage-service/main.py \
  > services/data-storage-service/production.log 2>&1 &

# 5) 等待 60s 让数据流转
sleep 60

# 6) 计数校验（1分钟内）
QUERY="SELECT \
 (SELECT count() FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 1 MINUTE) AS trades_1m, \
 (SELECT count() FROM marketprism_hot.orderbooks WHERE timestamp > now() - INTERVAL 1 MINUTE) AS orderbooks_1m, \
 (SELECT count() FROM marketprism_hot.open_interests WHERE timestamp > now() - INTERVAL 10 MINUTE) AS open_interests_10m"
RESULT=$(curl -s "http://localhost:8123/" --data "$QUERY")

echo "[result] $RESULT"
TRADES=$(echo "$RESULT" | cut -f1)
ORDERBOOKS=$(echo "$RESULT" | cut -f2)

if [ "${TRADES:-0}" -gt 0 ] && [ "${ORDERBOOKS:-0}" -gt 0 ]; then
  echo "\n✅ 烟测通过：trades_1m=$TRADES orderbooks_1m=$ORDERBOOKS"
  exit 0
else
  echo "\n❌ 烟测失败：计数结果异常：$RESULT"
  exit 1
fi

