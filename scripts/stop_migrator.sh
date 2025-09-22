#!/bin/bash
# 停止热->冷迁移循环
set -euo pipefail

PROJECT_ROOT="/home/ubuntu/marketprism"
LOG_DIR="$PROJECT_ROOT/logs"

if [ -f "$LOG_DIR/migrator.pid" ]; then
  PID=$(cat "$LOG_DIR/migrator.pid")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$LOG_DIR/migrator.pid"
  echo "✅ 迁移循环已停止"
else
  echo "[WARN] 未找到 PID 文件：$LOG_DIR/migrator.pid"
fi

