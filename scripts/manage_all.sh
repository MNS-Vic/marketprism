#!/bin/bash
# MarketPrism 系统统一管理脚本
# 用于统一管理所有模块（NATS、数据存储、数据采集器）

# 统一NATS环境注入（最小改动面）
export_nats_env() {
  local host="${NATS_HOST:-127.0.0.1}"
  local port="${NATS_PORT:-4222}"
  export NATS_URL="nats://${host}:${port}"
  export MARKETPRISM_NATS_URL="$NATS_URL"
  export MP_NATS_URL="$NATS_URL"
}

# 轻量 NATS 配置一致性预检（只告警不阻断）
verify_nats_consistency() {
  local target_host_port
  target_host_port="$(printf "%s" "${NATS_URL:-nats://127.0.0.1:4222}" | sed -E 's|^nats://([^:/]+):([0-9]+).*|\1:\2|')"
  log_step "NATS 配置一致性预检（目标: $target_host_port）"

  _check_file() {
    local file_path="$1"; local name="$2"
    if [ ! -f "$file_path" ]; then
      log_warn "$name 配置文件不存在: $file_path"
      return
    fi
    local urls
    urls=$(grep -Eo 'nats://[^"'\'' ]+' "$file_path" | sed -E 's|^nats://([^:/]+):([0-9]+).*|\1:\2|' | sort -u || true)
    if [ -z "$urls" ]; then
      log_warn "$name 未在配置中发现 nats://... URL，跳过"
      return
    fi
    local mismatch=0
    while IFS= read -r hp; do
      [ -z "$hp" ] && continue
      if [ "$hp" != "$target_host_port" ]; then
        log_warn "$name NATS 地址不一致: 配置=$hp, 期望=$target_host_port ($file_path)"
        mismatch=1
      fi
    done <<< "$urls"
    if [ $mismatch -eq 0 ]; then
      log_info "$name NATS 地址一致"
    else
      log_warn "建议：可选修复 1) 设置 NATS_HOST/NATS_PORT 并重新运行；2) 更新 $file_path 中的 nats://... 为 host:port=$target_host_port"
    fi
  }

  _check_file "$PROJECT_ROOT/services/data-collector/config/collector/unified_data_collection.yaml" "Collector"
  _check_file "$PROJECT_ROOT/services/hot-storage-service/config/hot_storage_config.yaml" "Storage"
}

set -euo pipefail

# ============================================================================
# 配置常量
# ============================================================================
# ClickHouse 部署架构（已完成容器化迁移 - 2025-10-18）
#
# 【Hot Storage】- 容器化部署 ✅
#   - 容器名: marketprism-clickhouse-hot
#   - 镜像: clickhouse/clickhouse-server:23.8-alpine
#   - HTTP 端口: localhost:8123 (映射 8123:8123)
#   - TCP 端口: localhost:9000 (映射 9000:9000)
#   - 内存限制: 3GB (mem_limit: 3G)
#   - CPU 限制: 2核 (cpus: 2.0)
#   - 数据保留: 7天 TTL (自动清理)
#   - 配置文件: services/hot-storage-service/config/clickhouse-memory.xml
#   - 数据卷: clickhouse_hot_data
#
# 【Cold Storage】- 容器化部署 ✅
#   - 容器名: mp-clickhouse-cold
#   - HTTP 端口: localhost:8124 (映射 8124:8123)
#   - TCP 端口: localhost:9001 (映射 9001:9000)
#   - 内存限制: 1.5GB
#   - 数据保留: 永久存储
#   - 数据卷: clickhouse_cold_data
#
# 【迁移记录】
#   - 迁移日期: 2025-10-18
#   - 迁移方式: CSV 格式导出/导入（跨版本兼容）
#   - 数据完整性: 100% (99,974 orderbooks + 9,228 trades)
#   - 停机时间: ~30 分钟 (NATS 缓存数据)
#   - 原宿主机 ClickHouse: 已停用 (systemctl stop clickhouse-server)
#
# 环境变量覆盖（优先级更高）：
#   - HOT_CH_HTTP_PORT / COLD_CH_HTTP_PORT    指定宿主机侧端口（如 8123/8124）
#   - HOT_CH_HTTP_URL / COLD_CH_HTTP_URL      直接指定完整 URL（如 http://127.0.0.1:8123）
# 说明：manage_all 的 ClickHouse 统计查询使用 HTTP 接口，无需宿主机安装 clickhouse-client


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 模块脚本路径

NATS_SCRIPT="$PROJECT_ROOT/services/message-broker/scripts/manage.sh"

STORAGE_SCRIPT="$PROJECT_ROOT/services/hot-storage-service/scripts/manage.sh"
COLLECTOR_SCRIPT="$PROJECT_ROOT/services/data-collector/scripts/manage.sh"
MONITORING_SCRIPT="$PROJECT_ROOT/services/monitoring-alerting/scripts/manage.sh"


COLD_SCRIPT="$PROJECT_ROOT/services/cold-storage-service/scripts/manage.sh"

# 颜色和符号
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 载入全局管理配置（若存在）
CONF_FILE="$PROJECT_ROOT/scripts/manage.conf"
if [ -f "$CONF_FILE" ]; then
  # shellcheck disable=SC1090
  . "$CONF_FILE"
fi

# 将 Prometheus/Grafana 中的目标按冷热端分别替换：
# - 热端/采集器/NATS 使用 PUBLIC_IP
# - 冷端使用 COLD_REMOTE_IP（未配置时回落到 PUBLIC_IP）
apply_prometheus_ip_from_config() {
  if [ "${APPLY_PROMETHEUS_IP_FROM_CONFIG:-false}" != "true" ]; then return 0; fi

  local local_ip="${PUBLIC_IP:-}"
  if [ -z "$local_ip" ] && [ -n "${COLD_REMOTE_IP:-}" ]; then
    local_ip="$COLD_REMOTE_IP"
  fi
  [ -z "$local_ip" ] && return 0
  local cold_ip="${COLD_REMOTE_IP:-$local_ip}"

  local prom_file="$PROJECT_ROOT/services/monitoring-alerting/config/prometheus/prometheus.yml"
  [ -f "$prom_file" ] || return 0

  # 1) Prometheus 普通 scrape 目标（端口区分冷热端）
  sed -i -E \
    -e "s#(['\"])((host\\.docker\\.internal)|([0-9]{1,3}(\\.[0-9]{1,3}){3})):9092(['\"])#\\1${local_ip}:9092\\6#g" \
    -e "s#(['\"])((host\\.docker\\.internal)|([0-9]{1,3}(\\.[0-9]{1,3}){3})):9094(['\"])#\\1${local_ip}:9094\\6#g" \
    -e "s#(['\"])((host\\.docker\\.internal)|([0-9]{1,3}(\\.[0-9]{1,3}){3})):9095(['\"])#\\1${cold_ip}:9095\\6#g" \
    "$prom_file" || true

  # 2) Blackbox HTTP 探测目标（按端口分流）
  sed -i -E \
    -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8087/health#http://${local_ip}:8087/health#g" \
    -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8085/health#http://${local_ip}:8085/health#g" \
    -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8086/health#http://${cold_ip}:8086/health#g" \
    -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8123/ping#http://${local_ip}:8123/ping#g" \
    -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8124/ping#http://${cold_ip}:8124/ping#g" \
    -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8222/healthz#http://${local_ip}:8222/healthz#g" \
    "$prom_file" || true

  # 3) Grafana 仪表盘中使用到的 instance 文本（与 Blackbox 目标保持一致）
  local grafana_dir="$PROJECT_ROOT/services/monitoring-alerting/config/grafana/dashboards"
  if [ -d "$grafana_dir" ]; then
    for f in "$grafana_dir"/*.json; do
      [ -f "$f" ] || continue
      sed -i -E \
        -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8087/health#http://${local_ip}:8087/health#g" \
        -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8085/health#http://${local_ip}:8085/health#g" \
        -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8086/health#http://${cold_ip}:8086/health#g" \
        -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8123/ping#http://${local_ip}:8123/ping#g" \
        -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8124/ping#http://${cold_ip}:8124/ping#g" \
        -e "s#http://(host\\.docker\\.internal|[0-9]{1,3}(\\.[0-9]{1,3}){3}):8222/healthz#http://${local_ip}:8222/healthz#g" \
        "$f" || true
    done
  fi
}

# 自动检测本机IP并（交互式）写入 scripts/manage.conf，避免跨机部署硬编码
# - 检测顺序：公网IP(api.ipify) -> 默认路由src -> hostname -I
# - 写入内容：PUBLIC_IP、同步更新 COLD_STORAGE_HEALTH_URL/COLD_CH_HTTP_URL、将IP加入 WHITELIST_IPS、更新 FULLMESH_IPS 的第一个IP
# - 同步刷新当前进程内的环境变量以便后续 apply_prometheus_ip_from_config 生效
detect_best_ip() {
  local ip=""
  ip=$(curl -s --max-time 2 https://api.ipify.org || true)
  if ! echo "$ip" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')
  fi
  if ! echo "$ip" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  fi
  echo "$ip"
}

ensure_public_ip_in_config() {
  local conf="$CONF_FILE"
  [ -f "$conf" ] || return 0
  local detected="${1:-}"
  if [ -z "$detected" ]; then
    detected=$(detect_best_ip)
  fi
  if ! echo "$detected" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    log_warn "未能自动探测到有效IP，跳过自动写入配置"
    return 0
  fi
  # 若已有相同IP，则跳过
  if grep -Eq "^\s*PUBLIC_IP\s*=\s*${detected}\s*$" "$conf"; then
    # 同步环境变量，防止旧值残留
    export PUBLIC_IP="$detected"
    export COLD_STORAGE_HEALTH_URL="http://${detected}:8086/health"
    export COLD_CH_HTTP_URL="http://${detected}:8124"
    return 0
  fi
  echo ""
  log_step "检测到本机 IP: ${detected}"
  if [ -t 0 ]; then
    read -r -p "是否将该 IP 写入 scripts/manage.conf 的 PUBLIC_IP，并用于 Prometheus/Grafana 配置？[Y/n] " ans || true
  else
    ans="Y"
  fi
  ans="${ans:-Y}"
  if echo "$ans" | grep -Eiq '^(y|yes)$'; then
    # 计算新值（基于已加载的配置变量）
    local wl="${WHITELIST_IPS:-}"
    if [ -z "$wl" ]; then wl="127.0.0.1 172.16.0.0/12"; fi
    if ! echo " $wl " | grep -q " ${detected} "; then wl="$wl ${detected}"; fi
    local fm="${FULLMESH_IPS:-}"
    local second="$(echo "$fm" | awk -F'[ ,]+' '{print $2}')"
    [ -z "$second" ] && second="$detected"
    local new_fm="${detected},${second}"

    # 写入配置（幂等替换）
    sed -i -E "s#^\s*PUBLIC_IP\s*=.*#PUBLIC_IP=${detected}#g" "$conf"
    sed -i -E "s#^\s*COLD_STORAGE_HEALTH_URL\s*=.*#COLD_STORAGE_HEALTH_URL=http://${detected}:8086/health#g" "$conf"
    sed -i -E "s#^\s*COLD_CH_HTTP_URL\s*=.*#COLD_CH_HTTP_URL=http://${detected}:8124#g" "$conf"
    if grep -Eq '^\s*WHITELIST_IPS\s*=' "$conf"; then
      sed -i -E "s#^\s*WHITELIST_IPS\s*=.*#WHITELIST_IPS=\"${wl}\"#g" "$conf"
    else
      printf '\nWHITELIST_IPS="%s"\n' "$wl" >> "$conf"
    fi
    if grep -Eq '^\s*FULLMESH_IPS\s*=' "$conf"; then
      sed -i -E "s#^\s*FULLMESH_IPS\s*=.*#FULLMESH_IPS=\"${new_fm}\"#g" "$conf"
    else
      printf '\nFULLMESH_IPS="%s"\n' "$new_fm" >> "$conf"
    fi

    # 同步当前进程内变量
    export PUBLIC_IP="$detected"
    export WHITELIST_IPS="$wl"
    export FULLMESH_IPS="$new_fm"
    export COLD_STORAGE_HEALTH_URL="http://${detected}:8086/health"
    export COLD_CH_HTTP_URL="http://${detected}:8124"

    log_info "已写入 PUBLIC_IP=${detected}（并同步更新 whitelist/fullmesh/冷端URL）"
  else
    log_info "已跳过写入 PUBLIC_IP"
  fi
}


# ============================================================================
# 工具函数
# ============================================================================

log_info() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "${BLUE}🔹 $1${NC}"
}

# 读取阻断策略(配置化)：项目根 scripts/manage.conf 中设置 BLOCK_ON_CONFLICT=true 生效
block_on_conflict_enabled() {
  local conf="$PROJECT_ROOT/scripts/manage.conf"
  local val=""
  if [ -f "$conf" ]; then
    val=$(grep -E '^\s*BLOCK_ON_CONFLICT\s*=' "$conf" | tail -n1 | sed -E 's/.*=\s*//')
  fi
  case "$val" in
    true|1|TRUE|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}


log_section() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}


#   
conflict_scan_preflight() {
  local has=0
  local dc_main="$PROJECT_ROOT/services/data-collector/main.py"
  local hs_main="$PROJECT_ROOT/services/hot-storage-service/main.py"

  #       
  if pgrep -af "$dc_main" >/dev/null 2>&1; then
    log_warn "   Data Collector       :"; pgrep -af "$dc_main" | sed 's/^/    - /'; has=1
  fi
  if pgrep -af "$hs_main" >/dev/null 2>&1; then
    log_warn "   Hot/Cold Storage       :"; pgrep -af "$hs_main" | sed 's/^/    - /'; has=1
  fi
  if pgrep -x nats-server >/dev/null 2>&1; then
    log_warn "   nats-server       :"; pgrep -af nats-server | sed 's/^/    - /'; has=1
  fi

  #       
  if command -v docker >/dev/null 2>&1; then
    local names
    names=$(docker ps --format '{{.Names}}' | egrep '^(marketprism-data-collector|marketprism-hot-storage-service|marketprism-nats|marketprism-clickhouse-hot|mp-cold-storage)$' || true)
    if [ -n "$names" ]; then
      log_warn "      :"; echo "$names" | sed 's/^/    - /'; has=1
    fi
  fi

  #       
  local ports_conflict=""
  for p in 4222 8222 8085 8086 8087 8123 8124 9000 9001; do
    if ss -ltnp 2>/dev/null | grep -q ":$p "; then ports_conflict+=" $p"; fi
  done
  if [ -n "$ports_conflict" ]; then
    log_warn "       ->${ports_conflict}"; has=1
  fi

  if [ $has -eq 0 ]; then
    log_info "                                                    ✅"
  else
    log_warn "  :                                                  scripts/manage_all.sh diagnose           ."
  fi
}

# 启动前的统一冲突扫描（只告警不阻断）— 修正定义覆盖上方异常编码的版本
conflict_scan_preflight() {
  local has=0
  local dc_main="$PROJECT_ROOT/services/data-collector/main.py"
  local hs_main="$PROJECT_ROOT/services/hot-storage-service/main.py"
  local cold_main="$PROJECT_ROOT/services/cold-storage-service/main.py"

  # 宿主机直跑进程
  if pgrep -af "$dc_main" >/dev/null 2>&1; then
    log_warn "发现宿主机 Data Collector 进程："
    pgrep -af "$dc_main" | sed 's/^/    - /'
    has=1
  fi
  if pgrep -af "$hs_main" >/dev/null 2>&1; then
    log_warn "发现宿主机 Hot/Cold Storage 进程："
    pgrep -af "$hs_main" | sed 's/^/    - /'
    has=1
  fi
  if pgrep -af "$cold_main" >/dev/null 2>&1; then
    log_warn "发现宿主机 Cold Storage 进程："
    pgrep -af "$cold_main" | sed 's/^/    - /'
    has=1
  fi
  if pgrep -x nats-server >/dev/null 2>&1; then
    log_warn "发现宿主机 nats-server 进程："
    pgrep -af nats-server | sed 's/^/    - /'
    has=1
  fi

  # 容器运行检测
  if command -v docker >/dev/null 2>&1; then
    local names
    names=$(docker ps --format '{{.Names}}' | egrep '^(marketprism-data-collector|marketprism-hot-storage-service|marketprism-nats|marketprism-clickhouse-hot|mp-cold-storage)$' || true)
    if [ -n "$names" ]; then
      log_warn "检测到相关容器正在运行："
      echo "$names" | sed 's/^/    - /'
      has=1
    fi
  fi

  # 端口占用检测
  local ports_conflict=""
  for p in 4222 8222 8085 8086 8087 8123 8124 9000 9001; do
    if ss -ltnp 2>/dev/null | grep -q ":$p "; then ports_conflict+=" $p"; fi
  done
  if [ -n "$ports_conflict" ]; then
    log_warn "端口占用检测：以下端口已被占用 ->${ports_conflict}"
    has=1
  fi

  if [ $has -eq 0 ]; then
    log_info "冲突扫描：未发现潜在进程/容器/端口冲突 ✅"
  else
    if block_on_conflict_enabled; then
      log_error "配置: BLOCK_ON_CONFLICT=true 生效：检测到冲突，已阻断启动。"
      echo "建议处理步骤："
      echo "  - 终止宿主机进程或停止容器，释放占用端口"
      echo "  - 快速诊断：./scripts/manage_all.sh diagnose"
      echo "  - 查看状态：./scripts/manage_all.sh status"
      exit 1
    else
      log_warn "建议：避免同时运行宿主机进程与容器；如需切换运行方式，请先停止另一方。端口冲突请 kill 占用，切勿改端口。可运行: scripts/manage_all.sh diagnose"
    fi
  fi
}


# 🔧 增强：等待服务启动并校验健康内容
wait_for_service() {
    local service_name="$1"
    local endpoint="$2"
    local timeout="$3"
    local expect_substr="${4:-}"
    local count=0

    log_info "等待 $service_name 启动..."

    while [ $count -lt $timeout ]; do
        local body
        if body=$(curl -sf "$endpoint" 2>/dev/null); then
            if [ -z "$expect_substr" ] || echo "$body" | grep -q "$expect_substr"; then
                log_info "$service_name 启动成功"
                return 0
            fi
        fi

        if [ $((count % 5)) -eq 0 ]; then
            log_info "等待 $service_name 启动... ($count/$timeout 秒)"
        fi

        sleep 1
        ((count++))
    done

    log_error "$service_name 启动超时"
    return 1
}

# 🔧 ClickHouse HTTP 查询辅助（移除宿主机 clickhouse-client 依赖）
# 默认热端HTTP映射端口: 8123；冷端HTTP映射端口: 8124（见 cold docker-compose）
init_ch_http() {
  HOT_CH_HTTP_URL="${HOT_CH_HTTP_URL:-http://127.0.0.1:${HOT_CH_HTTP_PORT:-8123}}"
  COLD_CH_HTTP_URL="${COLD_CH_HTTP_URL:-http://127.0.0.1:${COLD_CH_HTTP_PORT:-8124}}"
}

# 原始HTTP执行，返回文本结果，失败返回空字符串
ch_http_post() {
  local url="$1"; shift
  local sql="$*"
  curl -sf --max-time 15 -H "Content-Type: text/plain; charset=UTF-8" \
       --data-binary "$sql" "$url" 2>/dev/null || true
}

# 标量查询（返回第一行第一列），TabSeparated，失败返回0
ch_scalar_hot() {
  init_ch_http
  local out
  out=$(ch_http_post "$HOT_CH_HTTP_URL" "$* FORMAT TabSeparated")
  printf "%s" "$out" | head -n1 | cut -f1 | tr -d '\r' | sed 's/^$/0/'
}
ch_scalar_cold() {
  init_ch_http
  local out
  out=$(ch_http_post "$COLD_CH_HTTP_URL" "$* FORMAT TabSeparated")
  printf "%s" "$out" | head -n1 | cut -f1 | tr -d '\r' | sed 's/^$/0/'
}

# 返回CSVWithNames文本（用于覆盖报告）
ch_csv_hot() {
  init_ch_http
  ch_http_post "$HOT_CH_HTTP_URL" "$* FORMAT CSVWithNames"
}
ch_csv_cold() {
  init_ch_http
  ch_http_post "$COLD_CH_HTTP_URL" "$* FORMAT CSVWithNames"
}


# 🔧 增强：端到端数据流验证（覆盖8种数据 + 热端/冷端 + 迁移状态）
validate_end_to_end_data_flow() {
    log_info "验证端到端数据流..."

    local validation_passed=1

    # 检测系统运行时间（通过 NATS 进程启动时间判断）
    local system_uptime_minutes=0
    if pgrep -f "nats-server" >/dev/null 2>&1; then
        local nats_pid=$(pgrep -f "nats-server" | head -n1)
        if [ -n "$nats_pid" ]; then
            local start_time=$(ps -p "$nats_pid" -o lstart= 2>/dev/null)
            if [ -n "$start_time" ]; then
                local start_epoch=$(date -d "$start_time" +%s 2>/dev/null || echo "0")
                local now_epoch=$(date +%s)
                system_uptime_minutes=$(( (now_epoch - start_epoch) / 60 ))
            fi
        fi
    fi
    local is_fresh_start=0
    if [ "$system_uptime_minutes" -lt 10 ]; then
        is_fresh_start=1
    fi

    # NATS JetStream 概要
    local js_summary=$(curl -s http://localhost:8222/jsz 2>/dev/null)
    local stream_count=$(echo "$js_summary" | sed -n 's/.*"streams"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)
    local consumer_count=$(echo "$js_summary" | sed -n 's/.*"consumers"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)
    local message_count=$(echo "$js_summary" | sed -n 's/.*"messages"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)
    if [ -z "$stream_count" ] || [ "$stream_count" = "0" ]; then
        local js_detail=$(curl -s 'http://localhost:8222/jsz?streams=true' 2>/dev/null)
        stream_count=$(awk 'BEGIN{c=0}/"name":"MARKET_DATA"|"name":"ORDERBOOK_SNAP"/{c++} END{print c+0}' <<<"$js_detail")
    fi

    echo ""
    if [ -n "$stream_count" ] && [ "$stream_count" -ge 1 ] 2>/dev/null; then
        log_info "JetStream: 正常"
        log_info "  - 流数量: $stream_count"
        log_info "  - 消费者数量: ${consumer_count:-0}"
        log_info "  - 消息数量: ${message_count:-0}"
        # 展示期望的 subjects 数
        if [ -f "$PROJECT_ROOT/scripts/js_init_market_data.yaml" ]; then
            local md_subjects=$(awk '/MARKET_DATA:/{f=1;next}/ORDERBOOK_SNAP:/{f=0} f && $1 ~ /^-/{c++} END{print c+0}' "$PROJECT_ROOT/scripts/js_init_market_data.yaml")
            local ob_subjects=$(awk '/ORDERBOOK_SNAP:/{f=1;next} f && $1 ~ /^-/{c++} END{print c+0}' "$PROJECT_ROOT/scripts/js_init_market_data.yaml")
            log_info "  - MARKET_DATA subjects(期望): ${md_subjects:-7}"
            log_info "  - ORDERBOOK_SNAP subjects(期望): ${ob_subjects:-1}"
        fi
    else
        log_warn "JetStream: 无法获取流信息"
        validation_passed=0
    fi

    # ClickHouse 数据验证（HTTP接口，无需宿主机 clickhouse-client）
    if ! command -v curl >/dev/null 2>&1; then
        log_warn "未安装 curl，跳过 ClickHouse 数据验证"
        return 1
    fi
    init_ch_http

    # 定义数据类型标签
    declare -A table_labels=(
        [trades]="trades(高频)" [orderbooks]="orderbooks(高频)" \
        [funding_rates]="funding_rates(低频)" [open_interests]="open_interests(低频)" \
        [liquidations]="liquidations(事件)" [lsr_top_positions]="lsr_top_positions(低频)" \
        [lsr_all_accounts]="lsr_all_accounts(低频)" [volatility_indices]="volatility_indices(低频)"
    )
    local tables=(trades orderbooks funding_rates open_interests liquidations lsr_top_positions lsr_all_accounts volatility_indices)

    # 热端数据统计
    echo ""
    log_info "ClickHouse 热端数据统计 (marketprism_hot):"
    declare -A hot_counts
    local hot_total=0
    local hot_high_freq_count=0
    local hot_low_freq_count=0

    for t in "${tables[@]}"; do
        local cnt=$(ch_scalar_hot "SELECT COUNT(*) FROM marketprism_hot.${t}" 2>/dev/null || echo "0")
        [ -z "$cnt" ] && cnt=0
        hot_counts[$t]=$cnt
        hot_total=$((hot_total + cnt))

        if [ "$cnt" -gt 0 ]; then
            log_info "  - ${table_labels[$t]}: $cnt 条"
            case "$t" in
                trades|orderbooks) hot_high_freq_count=$((hot_high_freq_count + 1)) ;;
                funding_rates|open_interests|lsr_top_positions|lsr_all_accounts) hot_low_freq_count=$((hot_low_freq_count + 1)) ;;
            esac
        else
            case "$t" in
                trades|orderbooks)
                    if [ "$is_fresh_start" -eq 1 ]; then
                        log_info "  - ${table_labels[$t]}: 0 条 (系统刚启动，等待中)"
                    else
                        log_warn "  - ${table_labels[$t]}: 0 条 (高频数据，应该有数据)"
                        validation_passed=0
                    fi
                    ;;
                liquidations|volatility_indices)
                    log_info "  - ${table_labels[$t]}: 0 条 (事件驱动，取决于市场活动)" ;;
                *)
                    log_info "  - ${table_labels[$t]}: 0 条 (低频数据，等待中)" ;;
            esac
        fi
    done

    # 冷端数据统计
    echo ""
    log_info "ClickHouse 冷端数据统计 (marketprism_cold):"
    declare -A cold_counts
    local cold_total=0
    local cold_high_freq_count=0

    for t in "${tables[@]}"; do
        local cnt=$(ch_scalar_cold "SELECT COUNT(*) FROM marketprism_cold.${t}" 2>/dev/null || echo "0")
        [ -z "$cnt" ] && cnt=0
        cold_counts[$t]=$cnt
        cold_total=$((cold_total + cnt))

        if [ "$cnt" -gt 0 ]; then
            log_info "  - ${table_labels[$t]}: $cnt 条"
            case "$t" in
                trades|orderbooks) cold_high_freq_count=$((cold_high_freq_count + 1)) ;;
            esac
        else
            case "$t" in
                trades|orderbooks)
                    if [ "$is_fresh_start" -eq 1 ]; then
                        log_info "  - ${table_labels[$t]}: 0 条 (系统刚启动，批量复制尚未执行)"
                    elif [ "${hot_counts[$t]}" -gt 0 ]; then
                        log_info "  - ${table_labels[$t]}: 0 条 (热端有数据，等待批量复制)"
                    else
                        log_info "  - ${table_labels[$t]}: 0 条 (热端也无数据)"
                    fi
                    ;;
                *)
                    log_info "  - ${table_labels[$t]}: 0 条" ;;
            esac
        fi
    done

    # 数据迁移状态分析
    echo ""
    if [ "$cold_total" -eq 0 ]; then
        if [ "$is_fresh_start" -eq 1 ]; then
            log_info "数据迁移状态: 系统刚启动（运行 ${system_uptime_minutes} 分钟），冷端为空是正常的"
            log_info "  提示: 采用‘定时批量复制’（默认每 1 分钟），请稍后再检查"
        elif [ "$hot_total" -gt 0 ]; then
            log_warn "数据迁移状态: 热端有 $hot_total 条数据，但冷端为空"
            log_warn "  可能原因: 1) 批量复制延时或未执行 2) 冷端不可用/复制失败"
            # 检查冷端服务是否运行
            if ! curl -sf http://localhost:8086/health >/dev/null 2>&1; then
                log_warn "  检测到冷端存储服务未运行，请启动冷端服务"
                validation_passed=0
            fi
        else
            log_info "数据迁移状态: 热端和冷端都无数据（系统可能刚启动或数据采集异常）"
        fi
    else
        # 计算迁移比例
        local migration_percentage=0
        if [ "$hot_total" -gt 0 ]; then
            migration_percentage=$((cold_total * 100 / hot_total))
        fi

        if [ "$migration_percentage" -gt 0 ]; then
            log_info "数据迁移状态: 正常（冷端数据量为热端的 ${migration_percentage}%）"
        else
            log_info "数据迁移状态: 正常（冷端有 $cold_total 条数据）"
        fi

        # 读取热端清理策略状态（用于调整冷>热提示等级），兼容未安装jq的环境
        local cleanup_enabled="unknown"
        if command -v jq >/dev/null 2>&1; then
            # 优先从冷端读取（复制与清理更贴近冷端语义）；若无则回退热端；再无则默认启用以避免误报
            cleanup_enabled=$(curl -sf http://localhost:8086/health 2>/dev/null | jq -r '.replication.cleanup_enabled // empty' 2>/dev/null)
            if [ -z "$cleanup_enabled" ] || [ "$cleanup_enabled" = "null" ]; then
                cleanup_enabled=$(curl -sf http://localhost:8085/health 2>/dev/null | jq -r '.replication.cleanup_enabled // empty' 2>/dev/null)
            fi
            if [ -z "$cleanup_enabled" ] || [ "$cleanup_enabled" = "null" ]; then
                cleanup_enabled="true"
            fi
        else
            # 若无 jq，则默认视为启用清理策略，避免因解析失败导致误判
            cleanup_enabled="true"
        fi
        if [ "$cleanup_enabled" = "true" ]; then cleanup_enabled="true"; else cleanup_enabled="false"; fi

        # 验证数据一致性：冷端数据量应该 <= 热端数据量
        local inconsistent_tables=()
        for t in "${tables[@]}"; do
            if [ "${cold_counts[$t]}" -gt "${hot_counts[$t]}" ]; then
                inconsistent_tables+=("$t")
            fi
        done

        if [ ${#inconsistent_tables[@]} -gt 0 ]; then
            if [ "$cleanup_enabled" = "true" ]; then
                log_info "信息提示：热端已启用清理策略，冷端保留完整历史数据；以下表出现冷端>热端属正常："
                for t in "${inconsistent_tables[@]}"; do
                    log_info "  - $t: 热端=${hot_counts[$t]}, 冷端=${cold_counts[$t]}"
                done
                # 启用清理策略时，不将此视为健康检查失败
            else
                log_warn "数据一致性警告: 以下表的冷端数据量大于热端（异常）:"
                for t in "${inconsistent_tables[@]}"; do
                    log_warn "  - $t: 热端=${hot_counts[$t]}, 冷端=${cold_counts[$t]}"
                done
                validation_passed=0
            fi
        fi
    fi

    # 低频数据采集状态提示
    if [ "$hot_low_freq_count" -eq 0 ] && [ "$is_fresh_start" -eq 0 ]; then
        echo ""
        log_warn "低频数据提示: 所有低频数据类型都为 0，可能需要等待更长时间"
        log_warn "  低频数据包括: funding_rates, open_interests, lsr_top_positions, lsr_all_accounts"
        log_warn "  这些数据通常每分钟或每小时更新一次"
    fi

    # 复制延迟检测（热端与冷端最大时间戳差异）
    echo ""
    if [ "$is_fresh_start" -eq 1 ]; then
        log_info "复制延迟检测: 系统刚启动，暂不评估复制延迟"
    else
        log_info "复制延迟检测:"
        local REPL_LAG_WARN_MIN=${REPL_LAG_WARN_MIN:-60}
        for t in "${tables[@]}"; do
            local hot_max=$(ch_scalar_hot "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.${t}" 2>/dev/null || echo "0")
            local cold_max=$(ch_scalar_cold "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.${t}" 2>/dev/null || echo "0")
            [ -z "$hot_max" ] && hot_max=0
            [ -z "$cold_max" ] && cold_max=0
            if [ "$hot_max" -gt 0 ]; then
                local lag_min
                if [ "$cold_max" -gt 0 ]; then
                    lag_min=$(( (hot_max - cold_max) / 60000 ))
                    [ "$lag_min" -lt 0 ] && lag_min=0
                else
                    lag_min=999999
                fi
                log_info "  - $t: 冷端落后 ${lag_min} 分钟"
                if [ "$lag_min" -gt "$REPL_LAG_WARN_MIN" ]; then
                    log_warn "  - $t: 复制延迟超过阈值(${REPL_LAG_WARN_MIN}分钟)"
                    validation_passed=0
                fi
            fi
        done
    fi

    # 最终验证结果
    echo ""
    if [ "$validation_passed" -eq 1 ] && [ "$hot_total" -gt 0 ]; then
        log_info "端到端数据流: 完整验证通过 ✅"
        log_info "  - JetStream: $stream_count 个流，${message_count:-0} 条消息"
        log_info "  - 热端数据: $hot_total 条（高频: $hot_high_freq_count/2 类型有数据）"
        log_info "  - 冷端数据: $cold_total 条（高频: $cold_high_freq_count/2 类型有数据）"
        return 0
    elif [ "$hot_total" -gt 0 ]; then
        log_warn "端到端数据流: 部分验证通过（有数据但存在警告）⚠️"
        return 0
    else
        log_warn "端到端数据流: 暂无数据，系统可能仍在初始化"
        return 1
    fi
}

# 🔧 统一入口：系统级数据完整性与端到端验证
check_system_data_integrity() {
    log_section "MarketPrism 系统数据完整性检查"

    log_info "权威 Schema 文件: $PROJECT_ROOT/services/hot-storage-service/config/clickhouse_schema.sql（仅无前缀表）"

    local overall_exit_code=0

    # 统一Python解释器（优先使用统一虚拟环境）
    local PY_BIN="$PROJECT_ROOT/venv-unified/bin/python"
    if [ ! -x "$PY_BIN" ]; then
        PY_BIN="python3"
    fi

    # 1) 系统健康检查
    echo ""
    log_step "1. 系统健康检查 (health) ..."
    set +e
    bash "$0" health
    health_exit=$?
    set -e
    if [ $health_exit -eq 0 ]; then
        log_info "系统健康检查：通过"
    else
        log_error "系统健康检查：失败 (exit=$health_exit)"
        overall_exit_code=1
    fi

    # 2) Schema 一致性检查（专用脚本）
    echo ""
    log_step "2. Schema 一致性检查 ..."
    if $PY_BIN "$PROJECT_ROOT/services/hot-storage-service/scripts/validate_schema_consistency.py"; then
        log_info "Schema 一致性检查：通过"
        schema_exit=0
    else
        schema_exit=$?
        log_error "Schema 一致性检查：失败 (exit=$schema_exit)"
        overall_exit_code=1
    fi

    # 3) 数据完整性检查（热端/冷端数据量、复制状态等）
    echo ""
    log_step "3. 数据完整性检查（热端/冷端） ..."
    set +e
    bash "$STORAGE_SCRIPT" integrity
    storage_exit=$?
    set -e
    if [ $storage_exit -eq 0 ]; then
        log_info "数据完整性检查：通过"
    elif [ $storage_exit -eq 1 ]; then
        log_error "数据完整性检查：存在告警 (exit=$storage_exit)"
        overall_exit_code=1
    else
        log_error "数据完整性检查：失败 (exit=$storage_exit)"
        overall_exit_code=1
    fi


    # 3.5) 采集覆盖检查（按交易所×市场×数据类型，最近5分钟/8小时）
    echo ""
    log_step "3.5. 采集覆盖检查（exchange × market_type × data_type）..."
    set +e
    CHOT=$(ch_csv_hot "SELECT 'marketprism_hot' AS db, 'trades' AS table, exchange, market_type, count() AS total, sum(timestamp > now() - INTERVAL 5 MINUTE) AS recent, toString(max(timestamp)) AS max_ts FROM marketprism_hot.trades GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_hot','orderbooks', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 5 MINUTE), toString(max(timestamp)) FROM marketprism_hot.orderbooks GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_hot','funding_rates', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_hot.funding_rates GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_hot','open_interests', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_hot.open_interests GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_hot','liquidations', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_hot.liquidations GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_hot','lsr_top_positions', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_hot.lsr_top_positions GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_hot','lsr_all_accounts', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_hot.lsr_all_accounts GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_hot','volatility_indices', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_hot.volatility_indices GROUP BY exchange, market_type")
    CCOLD=$(ch_csv_cold "SELECT 'marketprism_cold' AS db, 'trades' AS table, exchange, market_type, count() AS total, sum(timestamp > now() - INTERVAL 5 MINUTE) AS recent, toString(max(timestamp)) AS max_ts FROM marketprism_cold.trades GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_cold','orderbooks', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 5 MINUTE), toString(max(timestamp)) FROM marketprism_cold.orderbooks GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_cold','funding_rates', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_cold.funding_rates GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_cold','open_interests', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_cold.open_interests GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_cold','liquidations', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_cold.liquidations GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_cold','lsr_top_positions', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_cold.lsr_top_positions GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_cold','lsr_all_accounts', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_cold.lsr_all_accounts GROUP BY exchange, market_type UNION ALL SELECT 'marketprism_cold','volatility_indices', exchange, market_type, count(), sum(timestamp > now() - INTERVAL 8 HOUR), toString(max(timestamp)) FROM marketprism_cold.volatility_indices GROUP BY exchange, market_type")
    set -e

    echo "—— 热端覆盖（最近=5m或8h）——"
    echo "$CHOT" | sed -n '1,200p'
    echo ""
    echo "—— 冷端覆盖（最近=5m或8h）——"
    echo "$CCOLD" | sed -n '1,200p'

    # 根据最近窗口为0输出 WARNING（不影响 overall_exit_code）
    echo ""
    log_warn "以下为覆盖预警（recent=0）："
    echo "$CHOT" | awk -F, 'NR>1 {if ($6==0) printf "[WARN] %s.%s exchange=%s market=%s recent=0, max_ts=%s\n", $1,$2,$3,$4,$7}'
    # 特别提示 Binance 可能的IP限制
    echo "$CHOT" | awk -F, 'NR>1 {if (tolower($3)~"binance" && $6==0) printf "[WARN] Binance %s.%s 近窗为0，可能受IP/地区限制，请更换服务器或配合合规代理\n", $1,$2}'

    # 4) E2E（数据质量/重复率/延迟/连续性）
    echo ""
    log_step "4. E2E 数据质量验证 (scripts/e2e_validate.py) ..."
    if $PY_BIN "$PROJECT_ROOT/scripts/e2e_validate.py"; then
        log_info "E2E 数据质量验证：通过"
        e2e_py_exit=0
    else
        e2e_py_exit=$?
        log_error "E2E 数据质量验证：失败 (exit=$e2e_py_exit)"
        overall_exit_code=1
    fi

    # 5) 生产环境端到端数据流验证
    echo ""
    log_step "5. 生产环境端到端验证 (scripts/production_e2e_validate.py) ..."
    if $PY_BIN "$PROJECT_ROOT/scripts/production_e2e_validate.py"; then
        log_info "生产环境端到端验证：通过"
        e2e_prod_exit=0
    else
        e2e_prod_exit=$?
        log_error "生产环境端到端验证：失败 (exit=$e2e_prod_exit)"
        overall_exit_code=1
    fi

    # 6) 补充：端到端数据流（内置快速检查）
    echo ""
    log_step "6. 内置端到端数据流快速检查 ..."
    set +e
    validate_end_to_end_data_flow
    quick_e2e_exit=$?

    # 启动前冲突扫描（仅告警不阻断）
    conflict_scan_preflight

    set -e
    if [ $quick_e2e_exit -eq 0 ]; then
        log_info "内置端到端数据流：通过"
    else
        log_error "内置端到端数据流：失败 (exit=$quick_e2e_exit)"
        overall_exit_code=1
    fi

    echo ""
    if [ $overall_exit_code -eq 0 ]; then
        log_info "统一完整性检查：全部通过 ✅"
        return 0
    else
        log_warn "统一完整性检查：发现问题 ❌"
        echo "—— 摘要 ——"
        echo "health:       $health_exit"
        echo "schema:       ${schema_exit:-1}"
        echo "storage:      $storage_exit"
        echo "e2e_quality:  ${e2e_py_exit:-1}"
        echo "e2e_prod:     ${e2e_prod_exit:-1}"
        echo "quick_e2e:    $quick_e2e_exit"
        log_warn "💡 建议先运行: $0 diagnose；如需修复迁移问题可运行: $0 repair"
        return 1
    fi
}

# 🔧 新增：系统级一键修复
repair_system() {
    log_info "权威 Schema 文件: $PROJECT_ROOT/services/hot-storage-service/config/clickhouse_schema.sql（仅无前缀表）"

    log_section "MarketPrism 系统一键修复"

    local overall_exit_code=0

    echo ""
    log_step "1. 修复数据存储服务数据迁移问题..."
    if bash "$STORAGE_SCRIPT" repair; then
        log_info "数据存储服务修复成功"
    else
        log_error "数据存储服务修复失败"
        overall_exit_code=1
    fi

    echo ""
    log_step "2. 重新验证系统数据完整性..."
    if check_system_data_integrity; then
        log_info "修复后验证通过"
    else
        log_warn "修复后仍有问题，可能需要手动处理"
        overall_exit_code=1
    fi

    return $overall_exit_code
}

# ============================================================================
# 初始化函数
# ============================================================================

init_all() {
    # 启动前冲突扫描（支持 BLOCK_ON_CONFLICT 阻断）
    conflict_scan_preflight
    ensure_public_ip_in_config || true

    export_nats_env
    verify_nats_consistency
    log_section "MarketPrism 系统初始化"

    # 🔧 运行增强初始化脚本
    echo ""
    log_step "0. 运行增强初始化（依赖检查、环境准备、配置修复）..."
    if [ -f "$PROJECT_ROOT/scripts/enhanced_init.sh" ]; then
        bash "$PROJECT_ROOT/scripts/enhanced_init.sh" || { log_error "增强初始化失败"; return 1; }
    else
        log_warn "增强初始化脚本不存在，跳过"
    fi

    echo ""
    log_step "1. 安装并初始化NATS消息代理..."
    bash "$NATS_SCRIPT" install-deps || log_warn "NATS依赖安装返回非零，继续尝试初始化"
    bash "$NATS_SCRIPT" init || { log_error "NATS初始化失败"; return 1; }

    echo ""
    log_step "2. 安装并初始化数据存储服务..."
    bash "$STORAGE_SCRIPT" install-deps || log_warn "存储服务依赖安装返回非零，继续尝试初始化"
    bash "$STORAGE_SCRIPT" init || { log_error "数据存储服务初始化失败"; return 1; }

    echo ""
    log_step "3. 安装并初始化数据采集器..."
    bash "$COLLECTOR_SCRIPT" install-deps || log_warn "采集器依赖安装返回非零，继续尝试初始化"
    bash "$COLLECTOR_SCRIPT" init || { log_error "数据采集器初始化失败"; return 1; }

    echo ""
    log_info "MarketPrism 系统初始化完成"
}

# ============================================================================
# 启动函数
# ============================================================================

start_all() {
    export_nats_env
    verify_nats_consistency
    log_section "MarketPrism 系统启动"

    # 启动前冲突扫描（仅告警不阻断）
    conflict_scan_preflight
    ensure_public_ip_in_config || true



    # : 
    # Pre-flight: verify unified virtualenv health and auto-repair if needed
    if ! "$PROJECT_ROOT/venv-unified/bin/python3" --version >/dev/null 2>&1; then
        log_warn "统一虚拟环境异常，尝试自动重建..."
        if [ -f "$PROJECT_ROOT/scripts/enhanced_init.sh" ]; then
            bash "$PROJECT_ROOT/scripts/enhanced_init.sh" || { log_error "增强初始化失败"; return 1; }
        fi
    fi

    echo ""
    log_step "1. 启动NATS（容器）..."
    bash "$NATS_SCRIPT" start \
      || { log_error "NATS 容器启动失败"; return 1; }

    # 🔧 等待NATS完全启动
    echo ""
    log_step "等待NATS完全启动..."
    wait_for_service "NATS" "http://localhost:8222/healthz" 60 "ok"

    echo ""
    log_step "2. 启动 Hot ClickHouse 与热端存储（模块脚本）..."
    bash "$STORAGE_SCRIPT" container:start \
      || { log_error "Hot ClickHouse/热端容器启动失败"; return 1; }

    # 🔧 等待 Hot ClickHouse 完全启动（HTTP 8123）
    echo ""
    log_step "等待 Hot ClickHouse 完全启动..."
    wait_for_service "Hot ClickHouse" "http://127.0.0.1:8123/?query=SELECT%201" 120 "1"

    # 🔧 等待热端存储完全启动
    echo ""
    log_step "等待热端存储完全启动..."
    wait_for_service "热端存储" "http://localhost:8085/health" 120 "healthy"

    echo ""
    log_step "3. 启动数据采集器（模块脚本）..."
    bash "$COLLECTOR_SCRIPT" container:start \
      || { log_error "数据采集器启动失败"; return 1; }

    # 🔧 等待数据采集器完全启动
    echo ""
    log_step "等待数据采集器完全启动..."
    wait_for_service "数据采集器" "http://localhost:8087/health" 180 '"status": "healthy"'

    echo ""
    log_step "4. 冷端存储（根据 SKIP_COLD_LOCAL 控制本地启动）..."
    if [ "${SKIP_COLD_LOCAL:-false}" = "true" ]; then
        log_info "跳过本地冷端启动（SKIP_COLD_LOCAL=true），请确保远端冷端已就绪"
    else
        bash "$COLD_SCRIPT" start \
          || { log_error "冷端存储启动失败"; return 1; }
    fi

    # 🔧 等待冷端存储健康（可指向远端）
    echo ""
    log_step "等待冷端存储健康..."
    COLD_HEALTH_URL="${COLD_STORAGE_HEALTH_URL:-http://localhost:8086/health}"
    wait_for_service "冷端存储" "$COLD_HEALTH_URL" 120 '"status": "healthy"'

    # 5) 启动监控告警栈（容器）（可通过环境变量关闭）
    if [ "${START_MONITORING_STACK:-true}" = "true" ]; then
        echo ""
        log_step "5. 启动监控告警栈（容器）..."
        apply_prometheus_ip_from_config || true
        ( cd "$PROJECT_ROOT/services/monitoring-alerting" && docker compose up -d ) \
          || { log_warn "监控告警栈启动失败（可稍后通过 manage_all.sh monitor:stack-up 单独启动）"; }
    else
        log_info "跳过监控告警栈启动（START_MONITORING_STACK=false）"
    fi


    echo ""
    log_info "MarketPrism 系统启动完成"

    # 🔧 增强的服务状态检查
    echo ""
    log_step "等待10秒后进行完整健康检查..."
    sleep 10
    health_all
}

# ============================================================================
# 停止函数
# ============================================================================

stop_all() {
    log_section "MarketPrism 系统停止"

    echo ""
    log_step "1. 停止数据采集器（模块脚本）..."
    bash "$COLLECTOR_SCRIPT" container:stop || log_warn "数据采集器停止失败"

    echo ""
    log_step "2. 停止冷端存储服务（模块脚本）..."
    bash "$COLD_SCRIPT" stop || log_warn "冷端存储停止失败"

    echo ""
    log_step "3. 停止热端存储与 Hot ClickHouse（模块脚本）..."
    bash "$STORAGE_SCRIPT" container:stop || log_warn "热端存储/Hot ClickHouse 停止失败"

    echo ""
    log_step "4. 停止NATS（容器）..."
    bash "$NATS_SCRIPT" stop || log_warn "NATS 停止失败"

    echo ""
    log_info "MarketPrism 系统停止完成"
}

# ============================================================================
# 重启函数
# ============================================================================

restart_all() {
    log_section "MarketPrism 系统重启"

    stop_all

    echo ""
    log_step "等待5秒后重新启动..."
    sleep 5

    start_all
}

# ============================================================================
# 状态检查函数
# ============================================================================

status_all() {
    log_section "MarketPrism 系统状态"

    echo ""
    log_step "NATS消息代理状态（容器）:"
    if curl -sf "http://localhost:8222/healthz" | grep -q "ok"; then
        log_info "NATS: 运行中"
    else
        log_warn "NATS: 未运行或不健康"
    fi

    echo ""
    log_step "热端存储服务状态（容器）:"
    if curl -sf "http://localhost:8085/health" | grep -q "healthy"; then
        log_info "热端存储: 运行中"
    else
        log_warn "热端存储: 未运行或不健康"
    fi

    echo ""
    log_step "冷端存储服务状态（容器）:"
    if curl -sf "http://localhost:8086/health" | grep -q '"status": "healthy"'; then
        log_info "冷端存储: 运行中"
    else
        log_warn "冷端存储: 未运行或不健康"
    fi

    echo ""
    log_step "数据采集器状态（容器）:"
    if curl -sf "http://localhost:8087/health" | grep -q '"status": "healthy"'; then
        log_info "数据采集器: 运行中"
    else
        log_warn "数据采集器: 未运行或不健康"
    fi
}

# ============================================================================
# 表集合一致性检查：只允许无前缀表（hot_/cold_ 前缀视为混用）
check_clickhouse_table_set_consistency() {
  local ok=1
  local ch_url="http://127.0.0.1:8123/"

  # 读取表名
  local hot_tables cold_tables
  hot_tables=$(curl -sf "${ch_url}?query=SHOW%20TABLES%20FROM%20marketprism_hot%20FORMAT%20TabSeparated" | sed '/^$/d' | sort || true)
  cold_tables=$(curl -sf "${ch_url}?query=SHOW%20TABLES%20FROM%20marketprism_cold%20FORMAT%20TabSeparated" | sed '/^$/d' | sort || true)

  # 检测前缀表是否存在
  local has_prefixed=0
  if echo "$hot_tables" | grep -E '^(hot_|cold_)' >/dev/null 2>&1; then has_prefixed=1; fi
  if echo "$cold_tables" | grep -E '^(hot_|cold_)' >/dev/null 2>&1; then has_prefixed=1; fi

  # 规范化目标集合（仅无前缀）
  local canonical=(
    "orderbooks" "trades" "funding_rates" "open_interests"
    "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices"


  )
  local allowed_extra_cold=()

  # 计算非标准表（热端）
  local non_standard_hot=""
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    # 允许 canonical 中的
    local matched=0
    for c in "${canonical[@]}"; do
      if [ "$t" = "$c" ]; then matched=1; break; fi
    done
    # 忽略前缀表（单独告警）
    if echo "$t" | grep -E '^(hot_|cold_)' >/dev/null 2>&1; then matched=1; fi
    if [ $matched -eq 0 ]; then
      non_standard_hot+="$t "
    fi
  done <<< "$hot_tables"

  # 计算非标准表（冷端）
  local non_standard_cold=""
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    local matched=0
    for c in "${canonical[@]}"; do
      if [ "$t" = "$c" ]; then matched=1; break; fi
    done
    for ex in "${allowed_extra_cold[@]}"; do
      if [ "$t" = "$ex" ]; then matched=1; break; fi
    done
    if echo "$t" | grep -E '^(hot_|cold_)' >/dev/null 2>&1; then matched=1; fi
    if [ $matched -eq 0 ]; then
      non_standard_cold+="$t "
    fi
  done <<< "$cold_tables"

  # 汇总输出
  if [ $has_prefixed -eq 1 ]; then
    log_warn "表集合命名混用：检测到 hot_/cold_ 前缀表"
    log_warn "  提示：当前规范仅允许无前缀表；请考虑清理前缀表或迁移数据后删除"
    ok=0
  fi

  if [ -n "$non_standard_hot" ]; then
    log_warn "热端存在非标准表（无前缀集合之外）：$non_standard_hot"
    ok=0
  fi
  if [ -n "$non_standard_cold" ]; then
    log_warn "冷端存在非标准表（无前缀集合之外）：$non_standard_cold"
    ok=0
  fi

  if [ $ok -eq 1 ]; then
    log_info "表集合命名一致：仅无前缀表 ✅"
    return 0
  else
    return 1
  fi
}

# 健康检查函数
# ============================================================================

health_all() {
    log_section "MarketPrism 系统健康检查"

    local exit_code=0

    echo ""
    log_step "检查NATS消息代理（容器）..."
    if curl -sf "http://localhost:8222/healthz" | grep -q "ok"; then
        log_info "NATS: healthy"
    else
        log_error "NATS: unhealthy"
        exit_code=1
    fi

    echo ""
    log_step "检查热端 ClickHouse 与热端存储（容器）..."
    if curl -sf "http://127.0.0.1:8123/" --data "SELECT 1" | grep -q "1"; then
        log_info "Hot ClickHouse: healthy"
    else
        log_error "Hot ClickHouse: unhealthy"
        exit_code=1
    fi
    if curl -sf "http://localhost:8085/health" | grep -q "healthy"; then
        log_info "热端存储: healthy"
    else
        log_error "热端存储: unhealthy"
        exit_code=1
    fi

    echo ""
    log_step "检查冷端 ClickHouse（容器）..."
    if curl -sf "http://127.0.0.1:8124/" --data "SELECT 1" | grep -q "1"; then
        log_info "Cold ClickHouse: healthy"
    else
        log_error "Cold ClickHouse: unhealthy"
        exit_code=1
    fi


    echo ""
    log_step "检查冷端存储（容器）..."
    if curl -sf "http://localhost:8086/health" | grep -q '"status": "healthy"'; then
        log_info "冷端存储: healthy"
    else
        log_error "冷端存储: unhealthy"
        exit_code=1
    fi

    echo ""
    log_step "检查数据采集器（容器）..."
    if curl -sf "http://localhost:8087/health" | grep -q '"status": "healthy"'; then
        log_info "数据采集器: healthy"
    else
        log_error "数据采集器: unhealthy"
        exit_code=1
    fi

    echo ""
    log_step "表集合一致性检查..."
    check_clickhouse_table_set_consistency || true

    # 🔧 端到端数据流验证
    echo ""
    log_step "端到端数据流验证..."
    validate_end_to_end_data_flow

    echo ""
    if [ $exit_code -eq 0 ]; then
        log_info "所有服务健康检查通过 ✅"
    else
        log_error "部分服务健康检查失败 ❌"
    fi

    return $exit_code
}

# ============================================================================
# 清理函数
# ============================================================================

clean_all() {
    log_section "MarketPrism 系统清理"

    echo ""
    log_step "1. 停止所有服务（容器）..."

    # 停止 Collector（容器）
    ( cd "$PROJECT_ROOT/services/data-collector" && docker compose -f docker-compose.unified.yml down ) || true

    # 停止 Hot Storage 与 Hot ClickHouse（容器）
    ( cd "$PROJECT_ROOT/services/hot-storage-service" && docker compose -f docker-compose.hot-storage.yml down ) || true

    # 停止 Cold Storage（容器）
    ( cd "$PROJECT_ROOT/services/cold-storage-service" && docker compose -f docker-compose.cold-test.yml down ) || true

    # 停止 NATS（容器）
    ( cd "$PROJECT_ROOT/services/message-broker" && docker compose -f docker-compose.nats.yml down ) || true


    # 额外保障：停止宿主机 ClickHouse（释放 8123/9000 端口）
    if pgrep -f "clickhouse-server" >/dev/null 2>&1; then
        log_warn "检测到宿主机 ClickHouse 仍在运行，尝试停止..."
        sudo systemctl stop clickhouse-server 2>/dev/null || true
        sudo clickhouse stop 2>/dev/null || true
        pkill -9 -f clickhouse-server 2>/dev/null || true
        sleep 1
        if pgrep -f "clickhouse-server" >/dev/null 2>&1; then
            log_warn "宿主机 ClickHouse 未完全停止，请手动检查进程占用（8123/9000）"
        else
            log_info "宿主机 ClickHouse 已停止"
        fi
    fi

    echo ""
    log_step "2. 清理 Docker 容器..."

    # 停止并删除 MarketPrism 相关容器
    docker ps -a --filter "name=marketprism" --format "{{.Names}}" | while read container; do
        if [ -n "$container" ]; then
            log_info "停止容器: $container"
            docker stop "$container" 2>/dev/null || true
            docker rm "$container" 2>/dev/null || true
        fi
    done

    # 停止并删除 Cold Storage 容器
    docker ps -a --filter "name=mp-" --format "{{.Names}}" | while read container; do
        if [ -n "$container" ]; then
            log_info "停止容器: $container"
            docker stop "$container" 2>/dev/null || true
            docker rm "$container" 2>/dev/null || true
        fi
    done

    echo ""
    log_step "3. 清理数据和日志..."
    bash "$COLLECTOR_SCRIPT" clean 2>/dev/null || true
    bash "$STORAGE_SCRIPT" clean --force 2>/dev/null || true

    echo ""
    log_step "4. 验证清理结果..."

    # 检查残留容器
    remaining_containers=$(docker ps -a --filter "name=marketprism" --filter "name=mp-" --format "{{.Names}}" | wc -l)
    if [ "$remaining_containers" -eq 0 ]; then
        log_info "✅ 所有容器已清理"
    else
        log_warn "⚠️  仍有 $remaining_containers 个容器残留"
        docker ps -a --filter "name=marketprism" --filter "name=mp-" --format "{{.Names}}: {{.Status}}"
    fi

    # 检查端口占用
    occupied_ports=$(netstat -tlnp 2>/dev/null | grep -E ":(4222|8085|8086|8087|8123|8124|9000|9001)" | wc -l)
    if [ "$occupied_ports" -eq 0 ]; then
        log_info "✅ 所有端口已释放"
    else
        log_warn "⚠️  仍有 $occupied_ports 个端口被占用"
    fi

    echo ""
    log_info "系统清理完成"
    echo ""
    log_warn "注意: Docker 卷未删除（保留数据），如需完全清理请手动执行:"
    log_warn "  docker volume rm marketprism-clickhouse-hot-data"
    log_warn "  docker volume rm clickhouse_cold_data"
}

# ============================================================================
# 快速诊断函数
# ============================================================================

diagnose() {
    log_section "MarketPrism 系统快速诊断"

    echo ""
    log_step "1. 检查端口占用..."
    echo "关键端口监听状态:"
    ss -ltnp | grep -E ':(4222|8222|8123|8085|8086|8087|9092)' || echo "  无相关端口监听"

    echo ""
    log_step "2. 检查进程状态..."
    echo "MarketPrism进程:"
    ps aux | grep -E '(nats-server|main.py)' | grep -v grep || echo "  无相关进程"

    echo ""
    log_step "3. 检查锁文件..."
    echo "实例锁文件:"
    ls -l /tmp/marketprism_*.lock 2>/dev/null || echo "  无锁文件"

    echo ""
    log_step "4. 检查Docker容器..."
    echo "MarketPrism容器:"
    if command -v docker >/dev/null 2>&1; then
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | awk 'NR==1 || $1 ~ /^(mp-|marketprism)/'
    else
        echo "  无相关容器"
    fi


    echo ""
    log_step "6. 建议一键处理命令（复制即用）..."
    cat <<EOS
# 宿主机进程清理（不存在会忽略错误）
pkill -f "$PROJECT_ROOT/services/data-collector/main.py" || true
pkill -f "$PROJECT_ROOT/services/hot-storage-service/main.py" || true
pkill -f "$PROJECT_ROOT/services/cold-storage-service/main.py" || true
pkill -x nats-server || true

# 容器停止（存在则停止）
if command -v docker >/dev/null 2>&1; then
  docker stop marketprism-data-collector marketprism-hot-storage-service marketprism-nats marketprism-clickhouse-hot mp-cold-storage 2>/dev/null || true
fi

# 容器编排下线（按需执行）
if command -v docker >/dev/null 2>&1; then
  ( cd "$PROJECT_ROOT/services/data-collector"        && docker compose -f docker-compose.unified.yml down )
  ( cd "$PROJECT_ROOT/services/hot-storage-service"    && docker compose -f docker-compose.hot-storage.yml down )
  ( cd "$PROJECT_ROOT/services/message-broker"         && docker compose -f docker-compose.nats.yml down )
  ( cd "$PROJECT_ROOT/services/cold-storage-service"   && docker compose -f docker-compose.cold-test.yml down )
fi

# 端口强制释放（如已安装 fuser）
sudo fuser -k 4222/tcp 8222/tcp 8085/tcp 8086/tcp 8087/tcp 8123/tcp 8124/tcp 9000/tcp 9001/tcp || true
EOS

    echo ""
    log_step "5. 执行健康检查..."
    health_all
}

# =========================================================================
# 冷端：重置引导并触发全历史回填
# =========================================================================

cold_full_backfill() {
    log_section "冷端全历史回填（重置引导）"

    # docker-only 模式：不再支持本地进程分支
    if true; then
        local compose_dir="$PROJECT_ROOT/services/cold-storage-service"
        local compose_file="$compose_dir/docker-compose.cold-test.yml"
        local container_name="mp-cold-storage"
        local service_name="cold-storage"

        if ! command -v docker >/dev/null 2>&1; then
            log_error "未检测到 docker，请先安装 docker"
            return 1
        fi
        if [ ! -f "$compose_file" ]; then
            log_error "未找到 compose 文件: $compose_file"
            return 1
        fi

        echo ""
        log_step "1) 重置冷端引导状态（清理 /app/run/sync_state.json）..."
        if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
            docker exec "$container_name" bash -lc 'rm -f /app/run/sync_state.json && echo reset_done' || true


























































































































        else
            log_warn "未发现容器 ${container_name}，稍后将直接重启 compose 服务"
        fi

        echo ""
        log_step "2) 重启冷端服务（compose service=${service_name}）以触发全历史回填..."
        ( cd "$compose_dir" && docker compose -f "$compose_file" restart "$service_name" ) || {
            log_warn "compose restart 失败，尝试 up -d --build 替代"
            ( cd "$compose_dir" && docker compose -f "$compose_file" up -d --build ) || {
                log_error "重启冷端服务失败"; return 1; }
        }

        echo ""
        log_step "3) 等待冷端健康..."
        COLD_HEALTH_URL="${COLD_STORAGE_HEALTH_URL:-http://localhost:8086/health}"
        wait_for_service "冷端存储" "$COLD_HEALTH_URL" 120 '"status": "healthy"'

        echo ""
        log_info "已触发全历史回填（引导阶段将从热端最早时间起连续分窗插入至安全滞后尾）"
        if command -v jq >/dev/null 2>&1; then
            curl -fsS http://127.0.0.1:8086/stats | jq . || true
        else
            curl -fsS http://127.0.0.1:8086/stats || true
        fi
        fi

        return 0

}


# ============================================================================
# 主函数
# ============================================================================

show_usage() {
    cat << EOF
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${CYAN}  MarketPrism 系统统一管理脚本${NC}
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

用法: $0 <command>

基础命令:
    init        初始化整个系统（首次部署使用）
    start       启动所有服务（按正确顺序）
    stop        停止所有服务（按正确顺序）
    restart     重启所有服务
    status      查看所有服务状态
    health      执行完整健康检查
    diagnose    快速诊断系统问题
    clean       清理锁文件和临时数据


重要说明:
    - 仅使用 services/hot-storage-service/config/clickhouse_schema.sql 作为唯一表定义

🔧 数据完整性命令:
    integrity   检查系统数据完整性
    repair      一键修复数据迁移问题


监控告警服务命令:
    monitor:start           启动 monitoring-alerting 服务（main.py，端口: 8082）
    monitor:stop            停止 monitoring-alerting 服务
    monitor:restart         重启 monitoring-alerting 服务
    monitor:status          查看 monitoring-alerting 服务状态
    monitor:health          健康检查（/health）
    monitor:logs            查看 monitoring-alerting 日志
    monitor:clean           清理 PID 和日志

    monitor:stack-up        启动监控栈（Prometheus/Grafana/Alertmanager/Blackbox/DingTalk/NATS Exporter）
    monitor:stack-down      停止监控栈
    monitor:stack-status    查看监控栈状态
    monitor:stack-reload    让 Prometheus 热加载配置（POST /-/reload）
    monitor:targets         查看 Prometheus 活跃 targets（/api/v1/targets）

    cold:full-backfill   重置引导并触发冷端全历史回填（docker-only）

服务启动顺序:
    1. NATS消息代理 (4222, 8222)
    2. 热端存储服务 (8085)
    3. 数据采集器 (8087)
    4. 冷端存储服务 (8086)

示例:
    $0 init         # 首次部署初始化
    $0 start        # 启动所有服务
    $0 stop         # 停止所有服务
    $0 restart      # 重启所有服务
    $0 status       # 查看状态
    $0 integrity    # 检查数据完整性
    $0 repair       # 修复数据迁移问题
    $0 health       # 健康检查
    $0 diagnose     # 快速诊断
    $0 clean        # 清理系统

环境变量:
  - NATS_HOST: 覆盖 NATS 主机（默认 127.0.0.1）
  - START_MONITORING_STACK: 是否在 start_all 自动启动监控告警栈（默认 true；设为 false 可跳过）
  - SKIP_COLD_LOCAL: 跳过本地冷端启动，配合远端冷端部署（默认 false）
  - COLD_STORAGE_HEALTH_URL: 冷端健康检查URL（默认 http://localhost:8086/health）

  - NATS_PORT: 覆盖 NATS 端口（默认 4222）
  - NATS_URL / MARKETPRISM_NATS_URL: 由 manage_all 根据上述变量自动导出，子服务启动时继承
  - COLD_CH_HOST: 冷端 ClickHouse 主机（宿主机访问容器，默认 127.0.0.1）
  - COLD_CH_TCP_PORT: 冷端 ClickHouse 端口（宿主机访问容器，默认 9001；compose 暴露 9001->9000）
  - COLD_CH_HTTP_URL: 冷端 ClickHouse HTTP URL（默认 http://127.0.0.1:8124，可改为 http://43.156.224.10:8124）

说明:
  - 冷端仅支持 Docker 模式，manage_all 将自动使用 docker-compose 启动/停止冷端组件（clickhouse-cold 与 cold-storage）。

${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
EOF
}

main() {
    local command="${1:-}"

    case "$command" in
        init)
            init_all
            ;;
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            restart_all
            ;;
        status)
            status_all
            ;;
        monitor:start)
            bash "$MONITORING_SCRIPT" start
            ;;
        monitor:stop)
            bash "$MONITORING_SCRIPT" stop
            ;;
        monitor:restart)
            bash "$MONITORING_SCRIPT" restart
            ;;
        monitor:status)
            bash "$MONITORING_SCRIPT" status
            ;;
        monitor:health)
            bash "$MONITORING_SCRIPT" health
            ;;
        monitor:logs)
            bash "$MONITORING_SCRIPT" logs
            ;;
        monitor:clean)
            bash "$MONITORING_SCRIPT" clean
            ;;
        monitor:stack-up)
            ( cd "$PROJECT_ROOT/services/monitoring-alerting" && docker compose up -d )
            ;;
        monitor:stack-down)
            ( cd "$PROJECT_ROOT/services/monitoring-alerting" && docker compose down )
            ;;
        monitor:stack-status)
            ( cd "$PROJECT_ROOT/services/monitoring-alerting" && docker compose ps )
            ;;
        monitor:stack-reload)
            ( curl -sS -X POST http://localhost:9090/-/reload >/dev/null && echo "Prometheus reloaded." ) || echo "Reload failed"
            ;;
        monitor:targets)
            ( curl -sS "http://localhost:9090/api/v1/targets?state=any" ) || true
            ;;

        health)
            health_all
            ;;
        diagnose)
            diagnose
            ;;
        clean)
            clean_all
            ;;
        integrity)
            check_system_data_integrity
            ;;
        cold:full-backfill)
            cold_full_backfill
            ;;

        repair)
            repair_system
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
