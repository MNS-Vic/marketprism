#!/bin/bash
# 启动热->冷迁移循环（开发模式默认每5分钟执行一次）
# 用法：
#   ./scripts/start_hot_to_cold_migrator.sh [interval_seconds] [window_hours]
# 示例：
#   ./scripts/start_hot_to_cold_migrator.sh        # 间隔=300s，窗口=8h
#   ./scripts/start_hot_to_cold_migrator.sh 120 4  # 间隔=120s，窗口=4h

set -euo pipefail

PROJECT_ROOT="/home/ubuntu/marketprism"
VENV_PATH="$PROJECT_ROOT/venv"
LOG_DIR="$PROJECT_ROOT/logs"
INTERVAL_SECONDS=${1:-300}
WINDOW_HOURS=${2:-8}

mkdir -p "$LOG_DIR"

if [ -d "$VENV_PATH" ]; then
  source "$VENV_PATH/bin/activate"
fi

# 后台循环执行
(
  echo "[migrator] 启动循环：interval=${INTERVAL_SECONDS}s, window=${WINDOW_HOURS}h"
  while true; do
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[migrator] ${TS} 开始迁移..."
    CLICKHOUSE_HTTP_URL="http://localhost:8123/" \
    CLICKHOUSE_HOT_DB="marketprism_hot" \
    CLICKHOUSE_COLD_DB="marketprism_cold" \
    MIGRATION_WINDOW_HOURS="$WINDOW_HOURS" \
      python3 services/data-storage-service/scripts/hot_to_cold_migrator.py \
      >> "$LOG_DIR/migrator.log" 2>&1 || true
    echo "[migrator] ${TS} 一次迁移结束，休眠${INTERVAL_SECONDS}s"
    sleep "$INTERVAL_SECONDS"
  done
) &

PID=$!
echo $PID > "$LOG_DIR/migrator.pid"
echo "✅ 迁移循环已启动 (PID=$PID)，日志：$LOG_DIR/migrator.log"

