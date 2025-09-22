#!/usr/bin/env bash
# MarketPrism 一键 10 分钟长跑验证脚本（统一存储路径）
# 功能：
# - 启用 venv
# - 启动 NATS(JS) 与 ClickHouse 容器
# - 初始化 ClickHouse schema 与 JetStream stream（8类数据，无 kline）
# - 后台启动 unified_storage_main 与 unified_collector_main
# - 10 分钟（20 次）每 30 秒采样 8 张表计数；必要时注入 1 条 liquidation 测试消息
# - 打印日志尾部与最终计数
# - 完成后彻底清理（进程、容器、临时日志）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -d venv ]; then
  # shellcheck disable=SC1091
  . venv/bin/activate
fi

# 进程与容器清理（容错）
(pkill -f services/data-collector/unified_collector_main.py || true)
(pkill -f services/data-storage-service/unified_storage_main.py || true) # 兼容清理（已废弃入口）
(pkill -f services/data-storage-service/simple_hot_storage.py || true)

# 启动 NATS & ClickHouse
export COMPOSE_PROJECT_NAME=marketprism_nats
cd "$ROOT_DIR/services/message-broker"
(docker-compose -f docker-compose.nats.yml ps | grep -q Up) || docker-compose -f docker-compose.nats.yml up -d

export COMPOSE_PROJECT_NAME=marketprism_storage
cd "$ROOT_DIR/services/data-storage-service"
(docker-compose -f docker-compose.hot-storage.yml ps | grep -q clickhouse-hot | grep -q Up) || docker-compose -f docker-compose.hot-storage.yml up -d clickhouse-hot

cd "$ROOT_DIR"

# 等待 ClickHouse 就绪
for i in {1..40}; do
  if curl -sS http://127.0.0.1:8123/ -m 2 >/dev/null; then break; fi
  sleep 2
  echo "等待 ClickHouse (${i})..."
done

# 初始化 ClickHouse 数据库与表（简化 schema + 冷端 schema）
python services/data-storage-service/scripts/init_clickhouse_db.py || true

# 初始化 JetStream（8 subjects，无 kline）
python services/data-storage-service/scripts/init_nats_stream.py \
  --config services/data-storage-service/config/production_tiered_storage_config.yaml || true

# 环境变量（统一规范）
export MARKETPRISM_NATS_SERVERS="nats://127.0.0.1:4222"
export MARKETPRISM_CLICKHOUSE_HOST="127.0.0.1"
export MARKETPRISM_CLICKHOUSE_PORT="8123"
export MARKETPRISM_CLICKHOUSE_DATABASE="marketprism_hot"

# 启动 unified storage 与 collector（后台）
TS="$(date +%s)"
STORAGE_LOG="/tmp/storage_unified_longrun_${TS}.log"
COLLECT_LOG="/tmp/collector_unified_longrun_${TS}.log"

nohup python services/data-storage-service/simple_hot_storage.py >"$STORAGE_LOG" 2>&1 &
echo $! > /tmp/storage_unified_longrun.pid
sleep 6

nohup python services/data-collector/unified_collector_main.py --mode launcher >"$COLLECT_LOG" 2>&1 &
echo $! > /tmp/collector_unified_longrun.pid
sleep 8

# 退出时清理
echo "注册清理钩子..."
cleanup() {
  echo "\n[清理] 停止进程与容器..."
  (pkill -f services/data-collector/unified_collector_main.py || true)
  (pkill -f services/data-storage-service/unified_storage_main.py || true) # 兼容清理（已废弃入口）
  (pkill -f services/data-storage-service/simple_hot_storage.py || true)

  export COMPOSE_PROJECT_NAME=marketprism_storage
  (cd "$ROOT_DIR/services/data-storage-service" && docker-compose -f docker-compose.hot-storage.yml down -v || true)
  export COMPOSE_PROJECT_NAME=marketprism_nats
  (cd "$ROOT_DIR/services/message-broker" && docker-compose -f docker-compose.nats.yml down -v || true)
  rm -f /tmp/storage_unified_longrun.pid /tmp/collector_unified_longrun.pid || true
  rm -f /tmp/storage_unified_longrun_*.log /tmp/collector_unified_longrun_*.log || true
}
trap cleanup EXIT

# 10 分钟采样（20 次，每次间隔 30s）
publish_liq_done=0
for i in $(seq 1 20); do
  echo "--- 采样 #$i @ $(date +"%F %T") ---"
  LIQ_CNT=0
  for T in trades orderbooks funding_rates open_interests liquidations lsr_top_positions lsr_all_accounts volatility_indices; do
    CNT=$(curl -sS "http://127.0.0.1:8123/?query=SELECT%20count()%20FROM%20marketprism_hot.%60$T%60" | tr -d "\n" || true)
    echo "$T: ${CNT:-0}"
    if [ "$T" = "liquidations" ]; then LIQ_CNT=${CNT:-0}; fi
  done

  # 若第4次仍无 liquidation，则注入一条测试消息
  if [ "$i" -eq 4 ] && [ "$publish_liq_done" -eq 0 ] && [ "${LIQ_CNT}" = "0" ]; then
    echo "[动作] 注入 1 条 liquidation 测试消息用于打通链路..."
    python - <<'PY'
import asyncio, json, os
from datetime import datetime, timezone
import nats
async def main():
    servers = os.getenv('MARKETPRISM_NATS_SERVERS','nats://127.0.0.1:4222').split(',')
    nc = await nats.connect(servers=servers)
    js = nc.jetstream()
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    payload = {
        'timestamp': now,
        'exchange': 'binance',
        'market_type': 'derivatives',
        'symbol': 'BTCUSDT',
        'side': 'sell',
        'price': 60000.0,
        'quantity': 0.01,
        'liquidation_time': now,
        'data_source': 'unified_longrun_test'
    }
    subj = 'liquidation.binance.derivatives.BTCUSDT'
    await js.publish(subj, json.dumps(payload).encode('utf-8'))
    await nc.close()
asyncio.run(main())
PY
    publish_liq_done=1
  fi

  sleep 30
done

# 打印日志尾部与最终计数
echo "\n--- Storage log tail ---"; tail -n 200 "$STORAGE_LOG" || true
echo "\n--- Collector log tail ---"; tail -n 120 "$COLLECT_LOG" || true

echo "\n--- Final counts ---"
for T in trades orderbooks funding_rates open_interests liquidations lsr_top_positions lsr_all_accounts volatility_indices; do
  CNT=$(curl -sS "http://127.0.0.1:8123/?query=SELECT%20count()%20FROM%20marketprism_hot.%60$T%60" | tr -d "\n" || true)
  echo "$T: ${CNT:-0}"
done

echo "\n[完成] 长跑结束，开始自动清理..."
exit 0

