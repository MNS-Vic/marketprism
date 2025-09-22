#!/usr/bin/env bash
set -euo pipefail

# 启用虚拟环境（如存在）
if [ -d "venv" ]; then
  source venv/bin/activate
elif [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# 进入脚本所在目录（services/data-storage-service）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 仓库根目录（上上上级）
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

MODE="${1:-hot}"  # 可选: hot | simple
export PYTHONUNBUFFERED=1

if [ "$MODE" = "hot" ]; then
  export PYTHONPATH="$REPO_ROOT"
  echo "[run_hot_local] Using hot_storage_service.py with PYTHONPATH=$PYTHONPATH"
  exec python3 hot_storage_service.py
else
  echo "[run_hot_local] Using main.py"
  # 变量统一：优先 MARKETPRISM_NATS_URL，其次 NATS_URL，最后默认值
  exec env \
    NATS_URL="${MARKETPRISM_NATS_URL:-${NATS_URL:-nats://localhost:4222}}" \
    CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-localhost}" \
    CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}" \
    CLICKHOUSE_DATABASE="${CLICKHOUSE_DATABASE:-marketprism_hot}" \
    python3 -u main.py
fi

