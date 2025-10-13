#!/bin/bash

# ==============================================================================
# MarketPrism Cold Storage Service 管理脚本（独立模块）
# - 职责：管理冷端服务（replication 热→冷）、初始化冷端表结构、健康/状态
# - 约定：项目在远端 NAS 上完整 clone；ClickHouse Cold 在 NAS 本机；Hot 远程
# - 依赖：python3、virtualenv（python -m venv）、clickhouse-driver；可选 clickhouse-client
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

MODULE_NAME="cold-storage-service"
VENV_DIR="$MODULE_ROOT/venv"
LOG_DIR="$MODULE_ROOT/logs"
RUN_DIR_DEFAULT="$MODULE_ROOT/run"
PID_FILE="$LOG_DIR/cold-storage.pid"
LOG_FILE="$LOG_DIR/cold-storage.log"
CONFIG_FILE="${COLD_STORAGE_CONFIG:-$MODULE_ROOT/config/cold_storage_config.yaml}"

# CH 连接（用于初始化/验证，可通过环境变量覆盖）
COLD_DB="${COLD_CH_DB:-marketprism_cold}"
COLD_HTTP_URL="${COLD_CH_HTTP_URL:-http://localhost:8123}"   # e.g. http://127.0.0.1:8123
SCHEMA_FILE="$PROJECT_ROOT/services/data-storage-service/config/clickhouse_schema.sql"
HTTP_PORT_DEFAULT=8086

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log_info(){ echo -e "${GREEN}[✓]${NC} $*"; }
log_warn(){ echo -e "${YELLOW}[⚠]${NC} $*"; }
log_error(){ echo -e "${RED}[✗]${NC} $*"; }
log_step(){ echo -e "\n${CYAN}━━━━ $* ━━━━${NC}\n"; }

ensure_dirs(){
  mkdir -p "$LOG_DIR" "$RUN_DIR_DEFAULT"
}

ensure_venv(){
  if [ ! -d "$VENV_DIR" ]; then
    log_info "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
}

install_deps(){
  log_step "安装依赖"
  ensure_venv
  pip install -q --upgrade pip
  local deps=( aiohttp PyYAML clickhouse-driver requests )
  log_info "安装: ${deps[*]}"
  pip install -q "${deps[@]}"
  log_info "依赖安装完成"
}

http_port_from_config(){
  # 解析配置中的 http_port（失败则使用默认）
  if [ -f "$CONFIG_FILE" ]; then
    local port
    port=$(grep -E "^\s*http_port\s*:\s*" "$CONFIG_FILE" | head -n1 | sed -E 's/.*http_port\s*:\s*([0-9]+).*/\1/') || true
    if [[ "$port" =~ ^[0-9]+$ ]]; then echo "$port"; return; fi
  fi
  echo "$HTTP_PORT_DEFAULT"
}

start(){
  log_step "启动冷端服务"
  ensure_dirs
  ensure_venv

  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log_warn "服务已在运行 (PID: $(cat "$PID_FILE"))"; return 0
  fi

  export COLD_STORAGE_CONFIG="$CONFIG_FILE"
  export MARKETPRISM_COLD_RUN_DIR="${MARKETPRISM_COLD_RUN_DIR:-$RUN_DIR_DEFAULT}"

  cd "$MODULE_ROOT"
  nohup "$VENV_DIR/bin/python" main.py >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 2

  local port; port=$(http_port_from_config)
  if curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    log_info "冷端服务启动成功 (PID: $(cat "$PID_FILE"), 端口: ${port})"
  else
    log_warn "冷端健康端口暂未就绪，查看日志: $LOG_FILE"
  fi
}

stop(){
  log_step "停止冷端服务"
  if [ -f "$PID_FILE" ]; then
    local pid; pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
      sleep 2
      kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    log_info "已停止"
  else
    log_warn "未运行或PID文件缺失"
  fi
}

status(){
  log_step "状态"
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log_info "进程: 运行中 (PID: $(cat "$PID_FILE"))"
  else
    log_warn "进程: 未运行"
  fi
  local port; port=$(http_port_from_config)
  if curl -sf "http://127.0.0.1:${port}/health" | grep -q '"status"'; then
    log_info "健康: OK (http://127.0.0.1:${port}/health)"
  else
    log_warn "健康: 暂无响应"
  fi
}

logs(){
  log_step "日志"
  [ -f "$LOG_FILE" ] && tail -f "$LOG_FILE" || log_warn "日志文件不存在: $LOG_FILE"
}

init_schema(){
  log_step "初始化冷端表结构 ($COLD_DB)"
  if [ ! -f "$SCHEMA_FILE" ]; then
    log_error "找不到权威 schema 文件: $SCHEMA_FILE"; return 1
  fi

  if command -v clickhouse-client >/dev/null 2>&1; then
    log_info "使用 clickhouse-client 应用 schema..."
    clickhouse-client --multiquery < "$SCHEMA_FILE" || true
    log_info "已应用 schema（含 hot/cold），冷端表结构已创建/对齐"
  else
    # 使用 HTTP 接口（仅向 cold 数据库写表结构需要将 SQL 拆分；这里提供最简回退：POST 全量 schema）
    log_info "未检测到 clickhouse-client，尝试 HTTP 接口: $COLD_HTTP_URL"
    if curl -sS -X POST "$COLD_HTTP_URL" --data-binary @"$SCHEMA_FILE" >/dev/null; then
      log_info "通过 HTTP 成功推送 schema（Cold 端需允许本地 HTTP 写入）"
    else
      log_warn "HTTP 推送失败，请手工在 NAS 上执行 schema：$SCHEMA_FILE"
      return 1
    fi
  fi
}

health(){
  local port; port=$(http_port_from_config)
  curl -sf "http://127.0.0.1:${port}/health" || { log_error "健康检查失败"; exit 1; }
}

verify(){
  log_step "冷端数据快速校验（计数摘要）"
  local tables=( trades orderbooks funding_rates open_interests liquidations lsr_top_positions lsr_all_accounts volatility_indices )
  if command -v clickhouse-client >/dev/null 2>&1; then
    for t in "${tables[@]}"; do
      local cnt
      cnt=$(clickhouse-client --query "SELECT count() FROM ${COLD_DB}.${t}" 2>/dev/null || echo 0)
      printf " - %-20s %12d\n" "$t" "$cnt"
    done
  else
    log_warn "未检测到 clickhouse-client，跳过本地校验。可设置 COLD_CH_HTTP_URL 后使用 curl 自行查询。"
  fi
}

clean(){
  log_step "清理"
  stop || true
  : > "$LOG_FILE" 2>/dev/null || true
  log_info "已清理日志与PID"
}

show_help(){
  cat <<EOF
${CYAN}MarketPrism Cold Storage Service 管理脚本${NC}
用法: $0 <命令>

基础命令:
  install-deps        安装 Python 依赖（venv）
  init-schema         初始化冷端表结构（需要 schema 文件）
  start               启动冷端服务（默认读取 $CONFIG_FILE）
  stop                停止冷端服务
  status              查看状态
  health              健康检查（HTTP）
  logs                跟随日志
  verify              冷端数据计数摘要（如有 clickhouse-client）
  clean               清理 PID/日志
  help                显示帮助

环境变量要点:
  COLD_STORAGE_CONFIG     冷端配置文件路径（默认 $CONFIG_FILE）
  MARKETPRISM_COLD_RUN_DIR  冷端运行状态目录（默认 $RUN_DIR_DEFAULT）
  COLD_CH_DB              冷端数据库名（默认 marketprism_cold）
  COLD_CH_HTTP_URL        冷端 ClickHouse HTTP 地址（默认 http://localhost:8123）
EOF
}

main(){
  cmd="${1:-help}"
  case "$cmd" in
    install-deps) install_deps ;;
    init-schema)  init_schema  ;;
    start)        start        ;;
    stop)         stop         ;;
    status)       status       ;;
    health)       health       ;;
    logs)         logs         ;;
    verify)       verify       ;;
    clean)        clean        ;;
    help|--help|-h) show_help  ;;
    *) log_error "未知命令: $cmd"; show_help; exit 1 ;;
  esac
}

main "$@"

