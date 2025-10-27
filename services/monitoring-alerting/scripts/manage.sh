#!/bin/bash

################################################################################
# MarketPrism Monitoring & Alerting 管理脚本
# 统一风格：install-deps | init | start | stop | restart | status | health | logs | clean
# 额外：stack-up | stack-down | stack-status （Prometheus/Grafana/Alertmanager/Blackbox/DingTalk 编排）
################################################################################

set -euo pipefail

# 兜底：NATS 对本模块不是必需，仅为风格一致保留（不使用）
export NATS_URL="${NATS_URL:-nats://127.0.0.1:4222}"
export MARKETPRISM_NATS_URL="${MARKETPRISM_NATS_URL:-$NATS_URL}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

MODULE_NAME="monitoring-alerting"
SERVICE_PORT=${SERVICE_PORT:-8082}
HEALTH_URL="http://localhost:${SERVICE_PORT}/health"

LOG_DIR="$MODULE_ROOT/logs"
LOG_FILE="$LOG_DIR/${MODULE_NAME}.log"
PID_FILE="$LOG_DIR/${MODULE_NAME}.pid"
VENV_DIR="$MODULE_ROOT/venv"
REQUIREMENTS_FILE="$MODULE_ROOT/requirements.txt"
DOCKER_COMPOSE_FILE="$MODULE_ROOT/docker-compose.yml"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $@"; }
log_warn() { echo -e "${YELLOW}[⚠]${NC} $@"; }
log_error(){ echo -e "${RED}[✗]${NC} $@"; }
log_step() { echo -e "\n${CYAN}━━━━ $@ ━━━━${NC}\n"; }

ensure_dirs() { mkdir -p "$LOG_DIR"; }

create_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    log_info "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
  fi
}

install_python_deps() {
  if [ ! -f "$REQUIREMENTS_FILE" ]; then
    log_warn "未找到 requirements.txt，跳过依赖安装"
    return 0
  fi
  # 始终使用本模块 venv 安装
  source "$VENV_DIR/bin/activate"
  pip install -q --upgrade pip
  pip install -q -r "$REQUIREMENTS_FILE"
  log_info "依赖安装完成"
}

install_deps() {
  log_step "安装 ${MODULE_NAME} 依赖"
  ensure_dirs
  create_venv
  install_python_deps
}

init_service() {
  log_step "初始化 ${MODULE_NAME} 服务"
  ensure_dirs
  # 若需要额外初始化逻辑，可在此添加（当前无）
  log_info "初始化完成"
}

start_service() {
  log_step "启动 ${MODULE_NAME}"

  # 自动创建 venv 并确保依赖（与其他模块风格保持一致）
  if [ ! -d "$VENV_DIR" ]; then
    create_venv
    install_python_deps || { log_error "依赖安装失败"; return 1; }
  else
    source "$VENV_DIR/bin/activate"
    # 幂等性：若核心依赖缺失则补装（aiohttp/structlog/pydantic）
    local missing=()
    for dep in aiohttp structlog pydantic; do
      pip show "$dep" >/dev/null 2>&1 || missing+=("$dep")
    done
    if [ ${#missing[@]} -gt 0 ]; then
      log_info "安装缺失依赖: ${missing[*]}"
      pip install -q "${missing[@]}"
    fi
  fi

  if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    log_warn "${MODULE_NAME} 已在运行 (PID: $(cat "$PID_FILE"))"
    return 0
  fi

  ensure_dirs
  cd "$MODULE_ROOT"

  # 可通过环境变量开启中间件
  # export MARKETPRISM_ENABLE_AUTH=true
  # export MARKETPRISM_ENABLE_VALIDATION=true

  nohup python "$MODULE_ROOT/main.py" > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"

  # 等待健康端点
  log_info "等待健康端点就绪..."
  local waited=0; local timeout=60
  while [ $waited -lt $timeout ]; do
    if curl -sf "$HEALTH_URL" 2>/dev/null | grep -q '"status"\s*:\s*"healthy"'; then
      log_info "${MODULE_NAME} 启动成功 (PID: $(cat "$PID_FILE"))"
      log_info "健康端点: $HEALTH_URL"
      return 0
    fi
    [ $((waited % 5)) -eq 0 ] && log_info "等待健康端点... ($waited/$timeout 秒)"
    sleep 1; waited=$((waited+1))
  done

  log_warn "健康端点未在 ${timeout}s 内返回 healthy；打印最近日志以供排查"
  tail -50 "$LOG_FILE" || true
}

stop_service() {
  log_step "停止 ${MODULE_NAME}"
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    if kill -0 $pid 2>/dev/null; then
      kill $pid 2>/dev/null || true
      local count=0
      while kill -0 $pid 2>/dev/null && [ $count -lt 10 ]; do
        sleep 1; count=$((count+1))
      done
      kill -9 $pid 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    log_info "${MODULE_NAME} 已停止"
  else
    # 尝试通过进程名停止
    if pgrep -f "$MODULE_ROOT/main.py" >/dev/null; then
      pkill -f "$MODULE_ROOT/main.py" || true
      sleep 1
      log_info "${MODULE_NAME} 已停止"
    else
      log_warn "${MODULE_NAME} 未运行"
    fi
  fi
}

restart_service() { stop_service; sleep 2; start_service; }

check_status() {
  log_step "检查状态"
  if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    local pid=$(cat "$PID_FILE")
    log_info "${MODULE_NAME}: 运行中 (PID: $pid)"
  else
    log_warn "${MODULE_NAME}: 未运行"
  fi
  if ss -ltn | grep -q ":${SERVICE_PORT} "; then
    log_info "端口 ${SERVICE_PORT}: 监听中"
  else
    log_warn "端口 ${SERVICE_PORT}: 未监听"
  fi
}

check_health() {
  log_step "健康检查"
  if curl -s "$HEALTH_URL" 2>/dev/null | grep -q 'healthy'; then
    log_info "健康状态: healthy"
  else
    log_warn "健康端点未返回 healthy 或未就绪"
    if [ -f "$LOG_FILE" ]; then
      echo "—— 最近日志 ——"; tail -50 "$LOG_FILE" || true
    fi
    return 1
  fi
}

show_logs() {
  log_step "查看日志"
  if [ -f "$LOG_FILE" ]; then
    tail -f "$LOG_FILE"
  else
    log_warn "日志文件不存在: $LOG_FILE"
  fi
}

clean_service() {
  log_step "清理"
  if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    log_warn "服务正在运行，将先停止"
    stop_service || true
  fi
  rm -f "$PID_FILE"
  if [ -f "$LOG_FILE" ]; then
    > "$LOG_FILE"
    log_info "已清空日志文件"
  fi
  log_info "清理完成"
}

stack_up() {
  log_step "启动监控栈 (Prometheus/Grafana/Alertmanager/Blackbox/DingTalk)"
  if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    log_error "未找到 docker-compose.yml"; return 1
  fi
  ( cd "$MODULE_ROOT" && docker compose up -d )
}

stack_down() {
  log_step "停止监控栈"
  if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    log_error "未找到 docker-compose.yml"; return 1
  fi
  ( cd "$MODULE_ROOT" && docker compose down )
}

stack_status() {
  log_step "监控栈状态"
  if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    log_error "未找到 docker-compose.yml"; return 1
  fi
  ( cd "$MODULE_ROOT" && docker compose ps ) || true
}


all_up() {
  log_step "统一启动：NATS、监控栈、Collector、Hot Storage、Cold Storage"

  # 1) 启动 NATS（JetStream）
  if [ -f "$PROJECT_ROOT/services/message-broker/docker-compose.nats.yml" ]; then
    ( cd "$PROJECT_ROOT/services/message-broker" && docker compose -f docker-compose.nats.yml up -d )
    log_info "NATS/JetStream 启动完成 (4222/8222)"
  else
    log_warn "未找到 message-broker/docker-compose.nats.yml，跳过 NATS 启动"
  fi

  # 2) 启动监控栈（Grafana/Prometheus/NATS Exporter/Blackbox/Alertmanager）
  ( cd "$MODULE_ROOT" && docker compose up -d grafana prometheus nats-exporter blackbox alertmanager || docker compose up -d )
  log_info "监控栈已启动 (Grafana:3000, Prometheus:9090)"

  # 3) 启动 Hot Storage（自动拉起 ClickHouse & init schema）
  if [ -f "$PROJECT_ROOT/services/hot-storage-service/docker-compose.hot-storage.yml" ]; then
    docker compose -f "$PROJECT_ROOT/services/hot-storage-service/docker-compose.hot-storage.yml" up -d hot-storage-service
    log_info "Hot Storage 启动完成 (8085/9094)"
  else
    log_warn "未找到 hot-storage-service/docker-compose.hot-storage.yml，跳过 Hot 启动"
  fi

  # 4) 启动 Data Collector
  if [ -f "$PROJECT_ROOT/services/data-collector/docker-compose.unified.yml" ]; then
    docker compose -f "$PROJECT_ROOT/services/data-collector/docker-compose.unified.yml" up -d data-collector
    log_info "Data Collector 启动完成 (8087/9092)"
  else
    log_warn "未找到 data-collector/docker-compose.unified.yml，跳过 Collector 启动"
  fi

  # 5) 启动 Cold Storage（自动拉起 ClickHouse Cold & init schema）
  if [ -f "$PROJECT_ROOT/services/cold-storage-service/docker-compose.cold-test.yml" ]; then
    docker compose -f "$PROJECT_ROOT/services/cold-storage-service/docker-compose.cold-test.yml" up -d cold-storage
    log_info "Cold Storage 启动完成 (8086/9095)"
  else
    log_warn "未找到 cold-storage-service/docker-compose.cold-test.yml，跳过 Cold 启动"
  fi

  # 6) 健康探测（尽力而为，不阻塞）
  curl -sS -m 3 http://127.0.0.1:3000/api/health >/dev/null 2>&1 && log_info "Grafana 健康: OK" || log_warn "Grafana 健康检查失败（稍后再试）"
}

all_status() {
  log_step "统一状态"
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | egrep 'marketprism|clickhouse|nats' || true
}

all_down() {
  log_step "统一停止（不移除数据卷）"
  # 先停应用，再停监控，最后停NATS
  [ -f "$PROJECT_ROOT/services/cold-storage-service/docker-compose.cold-test.yml" ] && \
    docker compose -f "$PROJECT_ROOT/services/cold-storage-service/docker-compose.cold-test.yml" down || true
  [ -f "$PROJECT_ROOT/services/hot-storage-service/docker-compose.hot-storage.yml" ] && \
    docker compose -f "$PROJECT_ROOT/services/hot-storage-service/docker-compose.hot-storage.yml" down || true
  [ -f "$PROJECT_ROOT/services/data-collector/docker-compose.unified.yml" ] && \
    docker compose -f "$PROJECT_ROOT/services/data-collector/docker-compose.unified.yml" down || true
  ( cd "$MODULE_ROOT" && docker compose down ) || true
  [ -f "$PROJECT_ROOT/services/message-broker/docker-compose.nats.yml" ] && \
    ( cd "$PROJECT_ROOT/services/message-broker" && docker compose -f docker-compose.nats.yml down ) || true
}

# —— 统一重建/刷新 ——
collector_rebuild() {
  log_step "重建并重启 Data Collector"
  if [ -f "$PROJECT_ROOT/services/data-collector/docker-compose.unified.yml" ]; then
    docker compose -f "$PROJECT_ROOT/services/data-collector/docker-compose.unified.yml" up -d --build --force-recreate data-collector
    log_info "Collector 已重建并启动 (8087/9092)"
  else
    log_warn "未找到 data-collector/docker-compose.unified.yml，跳过 Collector 重建"
  fi
}

hot_rebuild() {
  log_step "重建并重启 Hot Storage"
  if [ -f "$PROJECT_ROOT/services/hot-storage-service/docker-compose.hot-storage.yml" ]; then
    docker compose -f "$PROJECT_ROOT/services/hot-storage-service/docker-compose.hot-storage.yml" up -d --build --force-recreate hot-storage-service
    log_info "Hot Storage 已重建并启动 (8085/9094)"
  else
    log_warn "未找到 hot-storage-service/docker-compose.hot-storage.yml，跳过 Hot 重建"
  fi
}

all_refresh() {
  log_step "统一重建并重启关键服务：Collector + Hot Storage"
  hot_rebuild || true
  collector_rebuild || true
  # 冷端通常仅复制热端数据，默认不重建；如需可在此追加 cold 重建
}


show_help() {
  cat << EOF
${CYAN}MarketPrism Monitoring & Alerting 管理脚本${NC}

用法: $0 [命令]

命令:
  install-deps    安装依赖（创建venv并pip install -r requirements.txt）
  init            初始化服务
  start           启动服务（main.py，端口: ${SERVICE_PORT}）
  stop            停止服务
  restart         重启服务
  status          查看状态（PID/端口）
  health          健康检查（/health）
  logs            跟随查看日志
  clean           清理PID及日志

  stack-up        启动监控栈（Prometheus/Grafana/Alertmanager/Blackbox/DingTalk）
  stack-down      停止监控栈
  stack-status    查看监控栈状态


  all-up          统一启动：NATS + 监控栈 + Collector + Hot + Cold
  all-status      统一状态汇总
  all-down        统一停止（按依赖顺序）


  all-refresh    统一重建并重启关键服务（Collector + Hot）
  hot-rebuild    仅重建并重启 Hot Storage
  collector-rebuild  仅重建并重启 Data Collector

EOF
}

main() {
  case "${1:-help}" in
    install-deps) install_deps ;;
    init) init_service ;;
    start) start_service ;;
    stop) stop_service ;;
    restart) restart_service ;;
    status) check_status ;;
    health) check_health ;;
    logs) show_logs ;;
    all-refresh) all_refresh ;;
    hot-rebuild) hot_rebuild ;;
    collector-rebuild) collector_rebuild ;;

    clean) clean_service ;;
    stack-up) stack_up ;;
    stack-down) stack_down ;;
    stack-status) stack_status ;;
    all-up) all_up ;;
    all-status) all_status ;;
    all-down) all_down ;;

    help|--help|-h) show_help ;;
    *) log_error "未知命令: $1"; show_help; exit 1 ;;
  esac
}

main "$@"

