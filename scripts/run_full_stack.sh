#!/usr/bin/env bash
set -euo pipefail

# MarketPrism: 一键容器化满配置运行与验证
# 用途：启动 NATS(含JetStream) → ClickHouse+Hot Storage → Data Collector（满配置）
# 先决条件：已安装 Docker 与 docker compose plugin（docker compose）
# 端口：NATS(4222/8222), ClickHouse(8123/9000), Storage(18080->8080), Collector(8086/9093或ENV覆盖)

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

# 可配置参数
NATS_HTTP="http://localhost:8222"
CLICKHOUSE_HTTP="http://localhost:8123"
STORAGE_HEALTH="http://localhost:18080/health"
COLLECTOR_HEALTH="http://localhost:8086/health"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "[FATAL] 缺少命令: $1"; exit 1; }
}

retry() {
  local tries=$1; shift
  local delay=$1; shift
  local i
  for ((i=1;i<=tries;i++)); do
    if "$@"; then return 0; fi
    echo "[WARN] 第 $i 次尝试失败，$delay 秒后重试: $*"
    sleep "$delay"
  done
  return 1
}

http_ok() {
  local url=$1
  if command -v curl >/dev/null 2>&1; then
    curl -sf "$url" >/dev/null
  else
    wget -qO- "$url" >/dev/null
  fi
}

# 0) 依赖检查
need_cmd docker
if ! docker compose version >/dev/null 2>&1; then
  echo "[FATAL] 缺少 docker compose 插件。请安装 docker-compose-plugin 后重试。"
  exit 1
fi

# 1) 端口冲突检查（存在则尝试清理占用）
if [ -x ./scripts/check-port-conflicts.sh ]; then
  bash ./scripts/check-port-conflicts.sh 4222 8222 9000 8123 8080 8085 8086 8087 9093 9094 18080 || true
fi

# 2) 启动 NATS + 初始化 JetStream
pushd services/message-broker >/dev/null
  echo "[INFO] 启动 NATS 容器..."
  docker compose -f docker-compose.nats.yml up -d | tee "$LOG_DIR/_nats_up.out"

  echo "[INFO] 等待 NATS 健康... $NATS_HTTP/healthz"
  retry 30 2 http_ok "$NATS_HTTP/healthz"

  echo "[INFO] NATS 健康检查通过"
  # 可选：记录 JetStream 状态
  (curl -sf "$NATS_HTTP/varz" || true) > "$LOG_DIR/_varz.json" || true
  (curl -sf "$NATS_HTTP/jsz?streams=1" || true) > "$LOG_DIR/_jsz.json" || true
popd >/dev/null

# 3) 启动 ClickHouse + Hot Storage
pushd services/data-storage-service >/dev/null
  echo "[INFO] 启动 ClickHouse 与 Hot Storage..."
  docker compose -f docker-compose.hot-storage.yml up -d | tee "$LOG_DIR/_storage_up.out"

  echo "[INFO] 等待 ClickHouse 健康... $CLICKHOUSE_HTTP/ping"
  retry 60 2 http_ok "$CLICKHOUSE_HTTP/ping"

  echo "[INFO] 等待 Storage 健康... $STORAGE_HEALTH"
  retry 60 2 http_ok "$STORAGE_HEALTH"

  echo "[INFO] 存储侧已就绪"
popd >/dev/null

# 4) 启动 Data Collector（满配置）
pushd services/data-collector >/dev/null
  echo "[INFO] 启动 Data Collector（满配置）..."
  docker compose -f docker-compose.unified.yml up -d | tee "$LOG_DIR/_collector_up.out"

  echo "[INFO] 等待 Collector 健康 (若使用 8087 请调整 COLLECTOR_HEALTH 变量)..."
  # 尝试 8087 与 8086 两个端口
  if ! retry 60 2 http_ok "$COLLECTOR_HEALTH"; then
    COLLECTOR_HEALTH_ALT="http://localhost:8087/health"
    retry 60 2 http_ok "$COLLECTOR_HEALTH_ALT"
  fi
  echo "[INFO] Collector 健康检查通过"
popd >/dev/null

# 5) 运行期验证：检查 JetStream 流与消息
echo "[INFO] 拉取 JetStream 流信息..."
(curl -sf "$NATS_HTTP/jsz?streams=1" || true) | tee "$LOG_DIR/_jsz_after_start.json" >/dev/null || true

# 6) 提示下一步
cat <<EOF
=== 全链路已启动（预期） ===
- NATS:                 $NATS_HTTP (healthz/varz/jsz)
- ClickHouse:           $CLICKHOUSE_HTTP (ping)
- Storage Service:      $STORAGE_HEALTH
- Data Collector:       $COLLECTOR_HEALTH 或 http://localhost:8087/health

查看日志：
- docker compose logs -f  （在各服务目录）
- $LOG_DIR/_jsz_after_start.json  查看 JetStream 流/主题/消息计数

停止并清理：
- (cd services/data-collector && docker compose -f docker-compose.unified.yml down)
- (cd services/data-storage-service && docker compose -f docker-compose.hot-storage.yml down)
- (cd services/message-broker && docker compose -f docker-compose.nats.yml down -v)
EOF

