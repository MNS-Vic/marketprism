#!/usr/bin/env bash
set -Eeuo pipefail

# Cold Storage Service manage script (Docker-only)
# 仅负责冷端容器编排：启动/停止/状态/健康/日志/清理

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

COMPOSE_DIR="$MODULE_ROOT"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.cold-test.yml"
COLD_CONTAINER="mp-cold-storage"
COLD_CH_CONTAINER="mp-clickhouse-cold"
PORT=${PORT:-8086}

log_info(){ echo -e "\033[0;32m[INFO]\033[0m $*"; }
log_warn(){ echo -e "\033[1;33m[WARN]\033[0m $*"; }
log_error(){ echo -e "\033[0;31m[ERROR]\033[0m $*"; }

require_docker(){
  if ! command -v docker >/dev/null 2>&1; then
    log_error "未检测到 docker，请先安装 docker"; exit 1;
  fi
}

start_service(){
  require_docker
  if [ ! -f "$COMPOSE_FILE" ]; then
    log_error "未找到 compose 文件: $COMPOSE_FILE"; exit 1;
  fi
  log_info "启动冷端容器编排（:${PORT}）"
  ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" up -d --build )
  log_info "启动完成：$(docker ps --format '{{.Names}}' | grep -E "($COLD_CONTAINER|$COLD_CH_CONTAINER)" || true)"
}

stop_service(){
  require_docker
  if [ -f "$COMPOSE_FILE" ]; then
    log_info "停止冷端容器编排"
    ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" down ) || true
  fi
}

service_status(){
  require_docker
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | awk 'NR==1 || $1 ~ /^(mp-cold-storage|mp-clickhouse-cold)/'
}

service_health(){
  local url="http://127.0.0.1:${PORT}/health"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "$url" || { log_warn "健康检查失败：$url"; return 1; }
  else
    log_warn "curl 不存在，跳过健康检查：$url"
  fi
}

show_logs(){
  require_docker
  docker logs -f "$COLD_CONTAINER"
}

clean_artifacts(){
  require_docker
  log_info "清理冷端运行与日志卷(容器保留)"
  docker exec "$COLD_CONTAINER" bash -lc 'rm -f /app/run/sync_state.json /app/logs/*.log 2>/dev/null || true' || true
}

# [36m[1m [0m
diagnose(){
  require_docker
  echo "\n==== 冷端快速诊断（Docker-only）===="
  echo "[1] 容器状态"
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' |
    awk 'NR==1 || $1 ~ /^(mp-cold-storage|mp-clickhouse-cold)/'

  echo "\n[2] 端口占用情况"
  local ports="8086 9095 8124 9001"
  local any=0
  for p in $ports; do
    if ss -ltnp 2>/dev/null | grep -q ":$p "; then
      echo "  - 占用: $p"
      any=1
    else
      echo "  - 空闲: $p"
    fi
  done
  if [ $any -eq 0 ]; then echo "  => 端口无冲突 ✅"; else echo "  => 存在端口冲突 ⚠"; fi

  echo "\n[3] 建议一键处理命令（复制即用，不自动执行）"
  cat <<EOS
# 停止冷端相关容器（不存在会忽略错误）
docker stop $COLD_CONTAINER $COLD_CH_CONTAINER 2>/dev/null || true

# 通过 compose 下线冷端编排（若存在 compose 文件）
[ -f "$COMPOSE_FILE" ] && (cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" down) || true

# 强制释放端口（有 fuser 优先使用；否则使用 lsof）
if command -v fuser >/dev/null 2>&1; then
  sudo fuser -k 8086/tcp 9095/tcp 8124/tcp 9001/tcp || true
else
  for p in 8086 9095 8124 9001; do
    PIDS=$(lsof -ti -i :$p 2>/dev/null || true); [ -n "$PIDS" ] && sudo kill -9 $PIDS || true
  done
fi
EOS
}


show_help(){
  cat <<EOF
Cold Storage Service 管理脚本（Docker-only）

用法：
  $(basename "$0") <command>

命令：
  start         启动冷端容器编排（:${PORT}）
  stop          停止冷端容器编排
  restart       重启冷端容器编排
  status        显示容器状态
  health        健康检查（HTTP :${PORT}/health）
  logs          查看服务容器日志（docker logs -f）
  diagnose      快速诊断并输出一键命令
  clean         清理运行状态与日志
  help          显示本帮助
EOF
}

main(){
  local cmd=${1:-help}
  case "$cmd" in
    start) start_service ;;
    stop) stop_service ;;
    restart) stop_service || true; start_service ;;
    status) service_status ;;
    health) service_health ;;
    logs) show_logs ;;
    diagnose) diagnose ;;
    clean) clean_artifacts ;;
    help|*) show_help ;;
  esac
}

main "$@"
