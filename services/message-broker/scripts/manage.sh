#!/usr/bin/env bash
# MarketPrism - Message Broker manage script (NATS + js-init)
# 统一接口：install-deps | init | start | stop | restart | status | logs | down | health

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/services/message-broker"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.nats.yml"
NATS_CONTAINER="marketprism-nats"

# ---------- utils ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info(){ echo -e "${GREEN}✅ $1${NC}"; }
log_warn(){ echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error(){ echo -e "${RED}❌ $1${NC}"; }
log_step(){ echo -e "${BLUE}🔹 $1${NC}"; }

need_compose(){ [ -f "$COMPOSE_FILE" ] || { log_error "缺少 compose 文件: $COMPOSE_FILE"; exit 1; }; }

is_container_present(){ docker ps -a --format '{{.Names}}' | grep -q "^${NATS_CONTAINER}$"; }

# ---------- commands ----------
install_deps(){
  log_step "NATS 无需额外依赖（js-init 使用项目根镜像构建）"
  return 0
}

init(){
  need_compose
  log_step "初始化 NATS + JetStream（js-init）..."
  # 1) 确保 NATS 存在并运行（允许首次创建容器）
  ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" up -d --build nats )
  # 2) 运行一次 js-init（附着等待完成；不重启依赖）
  ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" up --build --no-deps js-init )
  log_info "NATS 初始化完成（JetStream 已按 scripts/js_init_market_data.yaml 配置）"
}

start(){
  need_compose
  log_step "启动 NATS（尽量复用已存在容器，不重建）..."
  set +e
  ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" start nats )
  rc=$?
  set -e
  if [ $rc -ne 0 ]; then
    log_warn "compose start 未找到已创建容器，回退为 up -d（不 build）"
    ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" up -d nats )
  fi
  log_info "NATS 已启动/保持运行"
}

stop(){
  need_compose
  log_step "停止 NATS（保留容器与卷，便于下次 start 直接复用）..."
  ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" stop nats ) || log_warn "NATS stop 返回非零"
  log_info "NATS 已停止（容器仍保留）"
}

down(){
  need_compose
  log_step "下线 NATS（移除容器；保留卷）..."
  ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" down ) || true
  log_info "NATS 容器已下线"
}

restart(){
  stop || true
  sleep 1
  start
}

status(){
  if curl -sf "http://127.0.0.1:8222/healthz" | grep -q "ok"; then
    log_info "NATS: 运行中 (http://127.0.0.1:8222)"
  else
    if is_container_present; then
      state=$(docker inspect -f '{{.State.Status}}' "$NATS_CONTAINER" 2>/dev/null || echo "unknown")
      log_warn "NATS: $state（可能未运行或健康检查失败）"
    else
      log_warn "NATS: 未创建容器"
    fi
  fi
}

logs(){
  if is_container_present; then
    docker logs --tail=200 "$NATS_CONTAINER" || true
  else
    log_warn "未发现容器: $NATS_CONTAINER"
  fi
}

health(){
  if curl -sf "http://127.0.0.1:8222/healthz" | grep -q "ok"; then
    echo '{"status":"ok"}'
    exit 0
  else
    echo '{"status":"unhealthy"}'
    exit 1
  fi
}

usage(){
  cat <<EOF
用法: $0 <command>
  install-deps   NATS 无需依赖（占位）
  init           初始化 NATS 并运行一次 js-init（创建或复用容器）
  start          启动 NATS（优先 compose start，必要时 up -d；不 build）
  stop           停止 NATS（保留容器）
  restart        重启 NATS
  status         显示 NATS 状态（基于 8222/healthz）
  logs           查看 NATS 日志（最近200行）
  down           下线（移除）NATS 容器（保留卷）
  health         返回 JSON 健康状态
EOF
}

main(){
  cmd=${1:-}
  case "$cmd" in
    install-deps) install_deps;;
    init) init;;
    start) start;;
    stop) stop;;
    restart) restart;;
    status) status;;
    logs) logs;;
    down) down;;
    health) health;;
    *) usage; exit 1;;
  esac
}

main "$@"

