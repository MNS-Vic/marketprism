#!/bin/bash
# MarketPrism 热端 -> 冷端 定时批量复制脚本
# 设计原则：
# - 表结构热端与冷端完全一致（复制使用 SELECT *）
# - 定时批量复制，避免实时高频同步压力
# - 复制成功后推进水位，失败不推进，保证幂等
# - 支持未来跨机房部署（使用 ClickHouse remote()）
# - 可由 cron 或外部调度器定时执行

set -euo pipefail

# --------------------------- 可配置参数（环境变量） ---------------------------
# 源（热端） ClickHouse TCP
HOT_HOST=${HOT_HOST:-127.0.0.1}
HOT_PORT=${HOT_PORT:-9000}
HOT_USER=${HOT_USER:-default}
HOT_PASSWORD=${HOT_PASSWORD:-}

# 目标（冷端） ClickHouse TCP（本脚本通过 cold 端连接并 remote() hot）
COLD_HOST=${COLD_HOST:-127.0.0.1}
COLD_PORT=${COLD_PORT:-9000}
COLD_USER=${COLD_USER:-default}
COLD_PASSWORD=${COLD_PASSWORD:-}

# 初始回溯窗口（无状态时第一次复制回溯的分钟数）
INIT_LOOKBACK_MIN=${INIT_LOOKBACK_MIN:-60}
# 安全延迟（避免复制正在写入的数据，单位分钟）
SAFETY_LAG_MIN=${SAFETY_LAG_MIN:-2}

# 每类表的复制窗口（分钟）
TRADES_WINDOW_MIN=${TRADES_WINDOW_MIN:-1}
ORDERBOOKS_WINDOW_MIN=${ORDERBOOKS_WINDOW_MIN:-1}
LOWFREQ_WINDOW_MIN=${LOWFREQ_WINDOW_MIN:-1}
EVENTS_WINDOW_MIN=${EVENTS_WINDOW_MIN:-1}

# 状态文件（记录每张表已复制到的时间水位，UTC 毫秒）
STATE_DIR="services/data-storage-service/run"
STATE_FILE="$STATE_DIR/sync_state.json"
mkdir -p "$STATE_DIR"

# --------------------------- 工具函数 ---------------------------
log() { echo "[$(date -u +%FT%TZ)] $*"; }
ch_cold() {
  clickhouse-client --host "$COLD_HOST" --port "$COLD_PORT" \
    --user "$COLD_USER" ${COLD_PASSWORD:+--password "$COLD_PASSWORD"} \
    --query "$1"
}
remote_expr() {
  local tbl="$1"
  # remote(host:port, db, table, user, password)
  echo "remote('${HOT_HOST}:${HOT_PORT}', 'marketprism_hot', '${tbl}', '${HOT_USER}', '${HOT_PASSWORD}')"
}

# JSON 读写（水位）
get_state_ts_ms() {
  local table="$1"
  if [ -f "$STATE_FILE" ]; then
    python3 - "$table" "$STATE_FILE" << 'PY'
import json,sys
name=sys.argv[1]; p=sys.argv[2]
try:
  d=json.load(open(p))
  v=d.get(name)
  if isinstance(v,int):
    print(v)
  else:
    print(0)
except Exception:
  print(0)
PY
  else
    echo 0
  fi
}

set_state_ts_ms() {
  local table="$1"; local tsms="$2"
  python3 - "$table" "$tsms" "$STATE_FILE" << 'PY'
import json,sys,os
name=sys.argv[1]; ts=int(sys.argv[2]); p=sys.argv[3]
try:
  d=json.load(open(p))
except Exception:
  d={}
d[name]=ts
open(p,'w').write(json.dumps(d))
PY
}

# 复制单表（按窗口推进）
sync_table() {
  local table="$1"; local window_min="$2"
  local now_ms=$(date -u +%s000)
  local safety_end_ms=$(( now_ms - SAFETY_LAG_MIN*60*1000 ))
  if [ "$safety_end_ms" -le 0 ]; then
    log "skip: safety_end_ms <= 0"
    return 0
  fi

  local last_ms=$(get_state_ts_ms "$table")
  if [ "$last_ms" -le 0 ]; then
    last_ms=$(( safety_end_ms - INIT_LOOKBACK_MIN*60*1000 ))
  fi

  local end_ms=$(( last_ms + window_min*60*1000 ))
  if [ "$end_ms" -gt "$safety_end_ms" ]; then
    end_ms=$safety_end_ms
  fi

  if [ "$end_ms" -le "$last_ms" ]; then
    log "[$table] no window to sync (last=${last_ms}, safety_end=${safety_end_ms})"
    return 0
  fi

  # 复制 SQL（精确到毫秒）
  local start_dt="toDateTime64(${last_ms}/1000.0, 3, 'UTC')"
  local end_dt="toDateTime64(${end_ms}/1000.0, 3, 'UTC')"
  local remote_src=$(remote_expr "$table")

  local sql="INSERT INTO marketprism_cold.${table} SELECT * FROM ${remote_src} WHERE timestamp >= ${start_dt} AND timestamp < ${end_dt}"

  log "[$table] syncing window: $(date -u -d @$((${last_ms}/1000))) .. $(date -u -d @$((${end_ms}/1000))) (UTC)"
  ch_cold "$sql"
  log "[$table] synced ok, advance watermark to ${end_ms}"
  set_state_ts_ms "$table" "$end_ms"
}

# 状态/延迟打印
status_table() {
  local table="$1"
  local hot_max=$(clickhouse-client --host "$HOT_HOST" --port "$HOT_PORT" --user "$HOT_USER" ${HOT_PASSWORD:+--password "$HOT_PASSWORD"} \
    --query "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.${table}")
  local cold_max=$(clickhouse-client --host "$COLD_HOST" --port "$COLD_PORT" --user "$COLD_USER" ${COLD_PASSWORD:+--password "$COLD_PASSWORD"} \
    --query "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.${table}")
  [ -z "$hot_max" ] && hot_max=0; [ -z "$cold_max" ] && cold_max=0
  local lag_min=0
  if [ "$hot_max" -gt 0 ]; then
    if [ "$cold_max" -gt 0 ]; then lag_min=$(( (hot_max-cold_max)/60000 )); else lag_min=999999; fi
  fi
  log "[$table] max_hot=$(date -u -d @$((${hot_max}/1000)) +%F%T) max_cold=$(date -u -d @$((${cold_max}/1000)) +%F%T) lag_min=${lag_min}"
}

usage() {
  cat << EOF
Usage: $0 [run|status]
  run      执行一次批量复制（按各表窗口）
  status   打印各表复制延迟

环境变量：
  HOT_HOST/HOT_PORT/HOT_USER/HOT_PASSWORD
  COLD_HOST/COLD_PORT/COLD_USER/COLD_PASSWORD
  INIT_LOOKBACK_MIN（默认60） SAFETY_LAG_MIN（默认2）
  TRADES_WINDOW_MIN/ORDERBOOKS_WINDOW_MIN（默认10）
  LOWFREQ_WINDOW_MIN/EVENTS_WINDOW_MIN（默认60）
  状态文件：$STATE_FILE
EOF
}

main() {
  local cmd="${1:-run}"
  case "$cmd" in
    run)
      # 高频
      sync_table trades "$TRADES_WINDOW_MIN"
      sync_table orderbooks "$ORDERBOOKS_WINDOW_MIN"
      # 低频
      sync_table funding_rates "$LOWFREQ_WINDOW_MIN"
      sync_table open_interests "$LOWFREQ_WINDOW_MIN"
      sync_table lsr_top_positions "$LOWFREQ_WINDOW_MIN"
      sync_table lsr_all_accounts "$LOWFREQ_WINDOW_MIN"
      # 事件
      sync_table liquidations "$EVENTS_WINDOW_MIN"
      sync_table volatility_indices "$EVENTS_WINDOW_MIN"
      ;;
    status)
      for t in trades orderbooks funding_rates open_interests lsr_top_positions lsr_all_accounts liquidations volatility_indices; do
        status_table "$t"
      done
      ;;
    *) usage; exit 1;;
  esac
}

main "$@"

