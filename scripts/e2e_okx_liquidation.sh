#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/e2e_logs"
JS_INIT_CFG="$ROOT_DIR/scripts/js_init_market_data.yaml"

mkdir -p "$LOG_DIR"

log() { echo "[$(date +'%F %T')] $*" | tee -a "$LOG_DIR/summary.log"; }

cleanup() {
  log "开始清理容器..."
  (cd "$ROOT_DIR" && docker-compose -f services/data-collector/docker-compose.unified.yml down) || true
  (cd "$ROOT_DIR" && docker-compose -f services/data-storage-service/docker-compose.hot-storage.yml down) || true
  (cd "$ROOT_DIR" && docker-compose -f services/message-broker/docker-compose.nats.yml down) || true
  log "清理完成"
}
trap cleanup EXIT

log "1) 启动 NATS (JetStream) ..."
(cd "$ROOT_DIR" && docker-compose -f services/message-broker/docker-compose.nats.yml up -d) | tee "$LOG_DIR/nats_up.log"

log "等待 NATS 监控端口 8222 ..."
for i in {1..30}; do
  if curl -sf http://localhost:8222/ >/dev/null; then log "NATS 已就绪"; break; fi
  sleep 2
  if [ "$i" = "30" ]; then log "NATS 等待超时"; exit 1; fi
done

log "2) 初始化 JetStream 流 (MARKET_DATA) ..."
. "$ROOT_DIR/.venv/bin/activate" || true
python "$ROOT_DIR/services/message-broker/init_jetstream.py" --wait --config "$JS_INIT_CFG" | tee "$LOG_DIR/js_init.log"

log "3) 启动 ClickHouse + 热存储服务 ..."
(cd "$ROOT_DIR" && docker-compose -f services/data-storage-service/docker-compose.hot-storage.yml up -d --build) | tee "$LOG_DIR/storage_up.log"

log "等待 ClickHouse 8123 ..."
for i in {1..60}; do
  if curl -sf "http://localhost:8123/?query=SELECT%201" >/dev/null; then log "ClickHouse 就绪"; break; fi
  sleep 2
  if [ "$i" = "60" ]; then log "ClickHouse 等待超时"; exit 1; fi
done

log "4) 启动 Data Collector (launcher, host 网络) ..."
(cd "$ROOT_DIR" && docker-compose -f services/data-collector/docker-compose.unified.yml up -d --build) | tee "$LOG_DIR/collector_up.log"

log "观察 JetStream liquidation.> 订阅 45 秒 ..."
. "$ROOT_DIR/.venv/bin/activate" || true
python "$ROOT_DIR/services/message-broker/scripts/js_subscribe_validate.py" \
  --nats-url nats://127.0.0.1:4222 \
  --stream MARKET_DATA \
  --subjects liquidation.> --json \
  > "$LOG_DIR/js_subscribe_liq.log" 2>&1 &
SUB_PID=$!
log "订阅进程 PID=$SUB_PID"
sleep 45
kill -INT "$SUB_PID" || true
sleep 2

log "5) ClickHouse 查询最近10条 OKX 强平 ..."
curl -s "http://localhost:8123/?query=SELECT%20timestamp,liquidation_time,exchange,market_type,symbol,side,price,quantity%20FROM%20marketprism_hot.liquidations%20WHERE%20exchange='okx_derivatives'%20ORDER%20BY%20timestamp%20DESC%20LIMIT%2010%20FORMAT%20TabSeparated" \
  | tee "$LOG_DIR/clickhouse_recent.tsv"

log "6) 重启 Collector 制造重连，检验去重 ..."
(cd "$ROOT_DIR" && docker-compose -f services/data-collector/docker-compose.unified.yml restart data-collector) | tee "$LOG_DIR/collector_restart.log"
sleep 10

log "7) 去重聚合检查（10分钟窗口） ..."
curl -s "http://localhost:8123/?query=SELECT%20symbol,side,liquidation_time,COUNT()%20cnt,any(price)%20price%2Cany(quantity)%20qty%20FROM%20marketprism_hot.liquidations%20WHERE%20exchange='okx_derivatives'%20AND%20timestamp%20%3E%20now()-INTERVAL%2010%20MINUTE%20GROUP%20BY%201,2,3%20HAVING%20cnt%20%3E%201%20ORDER%20BY%203%20DESC%20LIMIT%2010%20FORMAT%20Pretty" \
  | tee "$LOG_DIR/dedup_agg.txt"

log "全部步骤执行完成。日志见 $LOG_DIR"

