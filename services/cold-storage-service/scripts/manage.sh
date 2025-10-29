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

# # 载入全局配置（如存在）
CONF_FILE="$PROJECT_ROOT/scripts/manage.conf"
if [ -f "$CONF_FILE" ]; then
  # shellcheck disable=SC1090
  . "$CONF_FILE"
fi

#  IP 
print_whitelist_cmds(){
  local ips="${WHITELIST_IPS:-}"
  local ports="${WHITELIST_PORTS:-}"
  local mesh_ips="${FULLMESH_IPS:-}"
  [ -z "$ips" ] && [ -z "$mesh_ips" ] && return 0
  echo "# === 建议的 IP 白名单规则（基于 ufw） ==="
  echo "sudo ufw enable || true"
  # 先处理 FULLMESH（两个IP之间全端口互通：对这些来源IP放开任意端口）
  if [ -n "$mesh_ips" ]; then
    local IFS=', ';
    for ip in $mesh_ips; do
      [ -z "$ip" ] && continue
      echo "sudo ufw insert 1 allow from $ip to any"
    done
  fi
  # 再针对普通白名单IP放行必要端口（插到规则顶部，保证优先级）
  if [ -n "$ips" ] && [ -n "$ports" ]; then
    local IFS=', ';
    for p in $ports; do
      for ip in $ips; do
        [ -z "$ip" ] && continue
        echo "sudo ufw insert 1 allow from $ip to any port $p proto tcp"
      done
    done
    # 再默认拒绝这些端口来自任何来源（保底拒绝，未命中白名单则拒绝）
    for p in $ports; do
      echo "sudo ufw deny $p/tcp || true"
    done
  fi
}

apply_ip_whitelist(){
  if [ "${APPLY_IP_WHITELIST:-false}" != "true" ]; then
    log_info "未启用自动应用 IP 白名单（APPLY_IP_WHITELIST!=true），以下为建议命令："
    print_whitelist_cmds
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    log_warn "未找到 sudo，输出建议命令："; print_whitelist_cmds; return 0
  fi
  if command -v ufw >/dev/null 2>&1; then
    # 真正执行（幂等，失败不阻断）
    while IFS= read -r cmd; do
      [ -z "$cmd" ] && continue
      echo "+ $cmd"; eval "$cmd" || true
    done < <(print_whitelist_cmds)
    log_info "已尝试应用 ufw 白名单规则（如需回滚请手动 ufw status numbered && ufw delete <n>）"
  else
    log_warn "未检测到 ufw，尝试使用 iptables 自动应用规则"
    # FULLMESH：对这些IP放开全部端口（插入到INPUT链前部）
    if [ -n "${FULLMESH_IPS:-}" ]; then
      local IFS=', '
      for ip in $FULLMESH_IPS; do
        [ -z "$ip" ] && continue
        sudo iptables -C INPUT -s "$ip" -j ACCEPT 2>/dev/null || \
        sudo iptables -I INPUT -s "$ip" -j ACCEPT || true
      done
    fi
    # 兼容逗号/空格分隔：针对普通白名单按端口放行
    local IFS=', '
    for p in $WHITELIST_PORTS; do
      for ip in $WHITELIST_IPS; do
        [ -z "$ip" ] && continue
        sudo iptables -C INPUT -p tcp --dport "$p" -s "$ip" -j ACCEPT 2>/dev/null || \
        sudo iptables -A INPUT -p tcp --dport "$p" -s "$ip" -j ACCEPT || true
      done
      sudo iptables -C INPUT -p tcp --dport "$p" -j DROP 2>/dev/null || \
      sudo iptables -A INPUT -p tcp --dport "$p" -j DROP || true
    done
    log_info "iptables 白名单规则已尝试应用（临时生效；可用 sudo iptables-save 持久化）"
  fi
}

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
  log_info "启动冷端容器（优先复用已创建的容器）(:${PORT})"
  # 在启动容器前按配置应用 IP 白名单（需要 sudo；失败不阻断）
  apply_ip_whitelist || true
  # 统一使用 up -d（不 --build），既能启动已存在容器，也能在不存在时创建容器
  ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" up -d )
  log_info "启动完成：$(docker ps --format '{{.Names}}' | grep -E "($COLD_CONTAINER|$COLD_CH_CONTAINER)" || true)"
}

stop_service(){
  require_docker
  if [ -f "$COMPOSE_FILE" ]; then
    log_info "停止冷端容器（保留容器与卷）"
    ( cd "$COMPOSE_DIR" && docker compose -f "$COMPOSE_FILE" stop ) || true
  fi
}

down_service(){
  require_docker
  if [ -f "$COMPOSE_FILE" ]; then
    log_info "下线冷端容器编排（移除容器；保留卷）"
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
  start               启动冷端容器（优先 compose start，必要时 up -d）
  stop                停止冷端容器（保留容器与卷）
  down                下线冷端容器编排（移除容器；保留卷）
  restart             重启冷端容器编排
  status              显示容器状态
  health              健康检查（HTTP :${PORT}/health）
  logs                查看服务容器日志（docker logs -f）
  diagnose            快速诊断并输出一键命令
  clean               清理运行状态与日志
  whitelist:print     仅打印根据 scripts/manage.conf 生成的 IP 白名单命令（不执行）
  whitelist:apply     实际应用 IP 白名单（需要 sudo；仅在安装了 ufw 时尝试）
  help                显示本帮助
EOF
}

main(){
  local cmd=${1:-help}
  case "$cmd" in
    start) start_service ;;
    stop) stop_service ;;
    down) down_service ;;
    restart) stop_service || true; start_service ;;
    status) service_status ;;
    health) service_health ;;
    logs) show_logs ;;
    diagnose) diagnose ;;
    clean) clean_artifacts ;;
    whitelist:print) print_whitelist_cmds ;;
    whitelist:apply) APPLY_IP_WHITELIST=true; apply_ip_whitelist ;;
    help|*) show_help ;;
  esac
}

main "$@"
