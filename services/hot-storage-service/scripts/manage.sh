#!/bin/bash

################################################################################
# MarketPrism Data Storage Service 管理脚本
################################################################################

set -euo pipefail
# 兜底：直接运行子 manage.sh 时也有一致的 NATS 环境
export NATS_URL="${NATS_URL:-nats://127.0.0.1:4222}"
export MARKETPRISM_NATS_URL="${MARKETPRISM_NATS_URL:-$NATS_URL}"


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

# 配置
MODULE_NAME="hot-storage-service"
HOT_STORAGE_PORT=8085
COLD_STORAGE_PORT=8086
# 统一权威schema（热端/冷端共用，确保列结构完全一致）
DB_SCHEMA_FILE="$MODULE_ROOT/config/clickhouse_schema.sql"
DB_SCHEMA_COLD_FILE="$MODULE_ROOT/config/clickhouse_schema.sql"
DB_NAME_HOT="marketprism_hot"
DB_NAME_COLD="marketprism_cold"

# 日志和PID
LOG_DIR="$MODULE_ROOT/logs"
LOG_FILE_HOT="$LOG_DIR/storage-hot.log"
PID_FILE_HOT="$LOG_DIR/storage-hot.pid"
LOG_FILE_COLD="$LOG_DIR/storage-cold.log"
PID_FILE_COLD="$LOG_DIR/storage-cold.pid"
VENV_DIR="$MODULE_ROOT/venv"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $@"; }
log_warn() { echo -e "${YELLOW}[⚠]${NC} $@"; }
log_error() { echo -e "${RED}[✗]${NC} $@"; }
log_step() { echo -e "\n${CYAN}━━━━ $@ ━━━━${NC}\n"; }


# 进程/容器冲突扫描（仅告警不阻断）
conflict_scan() {
  local has_conflict=0
  local proc_pat="$MODULE_ROOT/main.py"

  # 宿主机直跑（hot/cold）进程：可能与容器并存
  if pgrep -af "$proc_pat" >/dev/null 2>&1; then
    log_warn "发现宿主机存储服务进程（可能是 --mode hot 或 --mode cold）："
    pgrep -af "$proc_pat" | sed 's/^/    - /'
    has_conflict=1
  fi

  # 容器：应用容器与 ClickHouse 容器
  if command -v docker >/dev/null 2>&1; then
    local running_containers
    running_containers=$(docker ps --format '{{.Names}}' | egrep '^(marketprism-hot-storage-service|marketprism-clickhouse-hot|mp-cold-storage)$' || true)
    if [ -n "$running_containers" ]; then
      log_warn "检测到相关容器正在运行："
      echo "$running_containers" | sed 's/^/    - /'
      has_conflict=1
    fi
  fi

  if [ $has_conflict -eq 0 ]; then
    log_info "冲突扫描：未发现潜在进程/容器冲突 ✅"
  else
    if [[ "${BLOCK_ON_CONFLICT:-}" == "true" || "${BLOCK_ON_CONFLICT:-}" == "1" || "${BLOCK_ON_CONFLICT:-}" == "TRUE" || "${BLOCK_ON_CONFLICT:-}" == "yes" || "${BLOCK_ON_CONFLICT:-}" == "YES" ]]; then
      log_error "BLOCK_ON_CONFLICT=true 生效：检测到冲突，已阻断启动。"
      echo "建议处理步骤："
      echo "  - 终止宿主机进程或停止容器，释放占用端口"
      echo "  - 快速诊断：./scripts/manage_all.sh diagnose"
      echo "  - 查看状态：./scripts/manage_all.sh status"
      exit 1
    else
      log_warn "建议：避免同时运行宿主机进程与容器；按需选择容器化或直跑，并先停止另一方。"
    fi
  fi
}

# 🆕 容器化部署检测（基于 docker-compose 文件存在性）
is_containerized() {
    if [ -f "$PROJECT_ROOT/services/hot-storage-service/docker-compose.hot-storage.yml" ] || \
       [ -f "$PROJECT_ROOT/services/cold-storage-service/docker-compose.cold-test.yml" ]; then
        return 0
    fi
    return 1
}

detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        [ -f /etc/os-release ] && . /etc/os-release && OS=$ID || OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    else
        log_error "不支持的操作系统"; exit 1
    fi
}

# 🔧 新增：智能ClickHouse启动和状态检查
ensure_clickhouse_running() {
    log_info "检查ClickHouse状态..."

    # 容器化优先：检测到容器化则跳过宿主机 ClickHouse 启动与连接等待
    if is_containerized; then
        log_info "检测到容器化部署：跳过宿主机 ClickHouse 启动与连接等待"
        return 0
    fi

    # 检查进程是否运行（支持多种进程名）
    local clickhouse_running=false
    if pgrep -f "clickhouse-server" > /dev/null; then
        clickhouse_running=true
    fi

    if [ "$clickhouse_running" = false ]; then
        log_info "启动ClickHouse..."
        # 尝试启动ClickHouse，忽略已运行的错误
        if sudo clickhouse start 2>/dev/null; then
            log_info "ClickHouse启动命令执行成功"
        else
            log_warn "ClickHouse启动命令返回错误，但可能已在运行"
        fi
        sleep 3
    else
        log_info "ClickHouse进程已在运行"
    fi

    # 🔧 等待ClickHouse服务完全可用（无论是新启动还是已运行）
    log_info "验证ClickHouse连接..."
    local retry_count=0
    while ! clickhouse-client --query "SELECT 1" >/dev/null 2>&1; do
        if [ $retry_count -ge 30 ]; then
            log_error "ClickHouse连接超时"
            return 1
        fi

        if [ $((retry_count % 5)) -eq 0 ]; then
            log_info "等待ClickHouse可用... ($((retry_count + 1))/30)"
        fi

        sleep 2
        ((retry_count++))
    done

    log_info "ClickHouse连接成功"
    return 0
}

install_deps() {
    log_step "安装依赖"
    detect_os

    # 安装 ClickHouse（容器化优先：容器化时跳过宿主机安装）
    if is_containerized; then
        log_info "检测到容器化部署：跳过宿主机 ClickHouse 安装"
    else
        if ! command -v clickhouse-server &> /dev/null; then
            log_info "安装 ClickHouse..."
            curl https://clickhouse.com/ | sh
            sudo ./clickhouse install
        else
            log_info "ClickHouse 已安装"
        fi
    fi

    # 创建虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi

    # 安装 Python 依赖
    log_info "安装 Python 依赖..."
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q

    # 🔧 完整的依赖列表，包含验证过程中发现的所有必需包
    local deps=(
        "nats-py"
        "aiohttp"
        "requests"
        "clickhouse-driver"
        "clickhouse-connect"
        "PyYAML"
        "python-dateutil"
        "structlog"
        "aiochclient"
        "sqlparse"
        "prometheus_client"
        "asyncio-mqtt"
        "uvloop"
        "orjson"
    )

    log_info "安装依赖包: ${deps[*]}"
    pip install -q "${deps[@]}" || {
        log_error "依赖安装失败"
        return 1
    }

    log_info "依赖安装完成"
}

init_service() {
    log_step "初始化服务"
    mkdir -p "$LOG_DIR"

    # 🔧 确保虚拟环境和依赖
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip -q

        # 安装关键依赖
        local deps=(
            "nats-py" "aiohttp" "requests" "clickhouse-driver" "clickhouse-connect"
            "PyYAML" "python-dateutil" "structlog" "aiochclient" "sqlparse" "prometheus_client"
        )
        pip install -q "${deps[@]}"
    else
        source "$VENV_DIR/bin/activate"
    fi

    # 🔧 智能ClickHouse启动和状态检查 / 容器化优先：init 阶段不启动宿主机 ClickHouse
    if is_containerized; then
        log_info "容器化部署：跳过宿主机 ClickHouse 启动与本地 schema 初始化（将由容器在 start 阶段完成）"
    else
        ensure_clickhouse_running
        # 🔧 智能数据库初始化和修复
        init_and_fix_database
    fi

    log_info "初始化完成"
}

# 🔧 增强：智能数据库初始化和修复函数
init_and_fix_database() {
    log_info "智能数据库初始化和修复..."

    # 检查数据库是否存在
    clickhouse-client --query "CREATE DATABASE IF NOT EXISTS $DB_NAME_HOT" 2>/dev/null || true
    clickhouse-client --query "CREATE DATABASE IF NOT EXISTS $DB_NAME_COLD" 2>/dev/null || true

    # 🔧 自动检测和修复表结构
    auto_fix_table_schema

    # 检查表结构 (hot)
    local existing_tables_hot=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" 2>/dev/null | wc -l | tr -dc '0-9')
    [ -z "$existing_tables_hot" ] && existing_tables_hot=0

    if [ "$existing_tables_hot" -lt 8 ]; then
        log_info "初始化热端数据库表..."
        # 尝试使用主schema文件
        if [ -f "$DB_SCHEMA_FILE" ]; then
            clickhouse-client --multiquery < "$DB_SCHEMA_FILE" 2>&1 | grep -v "^$" || true
        fi
        # 统一权威schema：不再使用简化schema回退，确保热/冷端结构严格一致
        : # no-op
        local table_count_hot=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" | wc -l | tr -dc '0-9')
        log_info "热端已创建 $table_count_hot 个表"
    else
        log_info "热端数据库表已存在 ($existing_tables_hot 个表)"
        # 🔧 检查并修复数据类型不匹配问题
        fix_table_schema_issues
        # 🔧 再次检查LSR表结构（确保修复完成）
        check_and_fix_lsr_tables
    fi

    # 检查冷端表结构 (cold)
    local existing_tables_cold=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_COLD" 2>/dev/null | wc -l | tr -dc '0-9')
    [ -z "$existing_tables_cold" ] && existing_tables_cold=0

    if [ "$existing_tables_cold" -lt 8 ]; then
        log_info "初始化冷端数据库表..."
        if [ -f "$DB_SCHEMA_COLD_FILE" ]; then
            clickhouse-client --multiquery < "$DB_SCHEMA_COLD_FILE" 2>&1 | grep -v "^$" || true
        fi
        local table_count_cold=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_COLD" | wc -l | tr -dc '0-9')
        log_info "冷端已创建 $table_count_cold 个表"
    else
        log_info "冷端数据库表已存在 ($existing_tables_cold 个表)"
    fi
}

# 🔧 增强：修复表结构问题和DateTime64统一
fix_table_schema_issues() {
    log_info "检查并修复表结构问题..."

    # 🔧 检查所有表的timestamp字段类型
    local tables_to_check=("trades" "orderbooks" "funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")
    local need_fix=false

    for table in "${tables_to_check[@]}"; do
        local timestamp_type=$(clickhouse-client --query "
            SELECT type FROM system.columns
            WHERE database = '$DB_NAME_HOT' AND table = '$table' AND name = 'timestamp'
        " 2>/dev/null || echo "")

        if [[ "$timestamp_type" == "DateTime" ]] || [[ -z "$timestamp_type" ]]; then
            log_warn "表 $table 的timestamp字段类型需要修复: $timestamp_type"
            need_fix=true
        fi
    done

    if [ "$need_fix" = true ]; then
        log_warn "检测到数据类型不匹配问题，执行统一修复..."

        # 🔧 备份现有数据（如果有）
        backup_existing_data

        # 🔧 删除有问题的表
        drop_incompatible_tables

        # 🔧 使用统一schema重建
        create_unified_tables

        log_info "表结构统一修复完成"
    else
        log_info "表结构检查通过，所有timestamp字段已统一为DateTime64(3, 'UTC')"

        # 🔧 确保缺失的表被创建
        ensure_missing_tables
    fi
}

# 🔧 新增：备份现有数据
backup_existing_data() {
    log_info "备份现有数据..."

    local tables_with_data=()
    for table in "trades" "orderbooks" "funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices"; do
        local count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.${table}" 2>/dev/null || echo "0")
        if [ "$count" -gt 0 ]; then
            tables_with_data+=("$table:$count")
            log_info "备份表 $table ($count 条记录)..."
            clickhouse-client --query "CREATE TABLE IF NOT EXISTS $DB_NAME_HOT.${table}_backup AS $DB_NAME_HOT.${table}" 2>/dev/null || true
            clickhouse-client --query "INSERT INTO $DB_NAME_HOT.${table}_backup SELECT * FROM $DB_NAME_HOT.${table}" 2>/dev/null || true
        fi
    done

    if [ ${#tables_with_data[@]} -gt 0 ]; then
        log_info "已备份 ${#tables_with_data[@]} 个表的数据"
    fi
}

# 🔧 新增：删除不兼容的表
drop_incompatible_tables() {
    log_info "删除不兼容的表..."

    local tables_to_drop=("funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")
    for table in "${tables_to_drop[@]}"; do
        clickhouse-client --query "DROP TABLE IF EXISTS $DB_NAME_HOT.${table}" 2>/dev/null || true
    done
}

# 🔧 新增：使用统一schema创建表
create_unified_tables() {
    log_info "使用统一schema创建表..."

    local unified_schema="$MODULE_ROOT/config/clickhouse_schema.sql"
    if [ -f "$unified_schema" ]; then
        # 该schema同时覆盖hot/cold两端，确保结构一致
        clickhouse-client --multiquery < "$unified_schema" 2>&1 | grep -v "^$" || true
        log_info "统一表结构创建完成"
    else
        log_warn "权威schema文件不存在: $unified_schema，使用内置创建逻辑"
        create_tables_inline
    fi
}

# 🔧 新增：确保缺失的表被创建
ensure_missing_tables() {
    log_info "检查并创建缺失的表..."

    local required_tables=("funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")
    local missing_tables=()

    for table in "${required_tables[@]}"; do
        local exists=$(clickhouse-client --query "EXISTS TABLE $DB_NAME_HOT.${table}" 2>/dev/null || echo "0")
        if [ "$exists" = "0" ]; then
            missing_tables+=("$table")
        fi
    done

    if [ ${#missing_tables[@]} -gt 0 ]; then
        log_info "创建缺失的表: ${missing_tables[*]}"
        create_unified_tables
    fi
}

# 🔧 新增：统一修复 created_at 默认值为 now64(3)
ensure_created_at_default() {
    log_info "修复 created_at 默认值（now64(3)）..."
    local dbs=("$DB_NAME_HOT" "$DB_NAME_COLD")
    local tables=("orderbooks" "trades" "funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")
    for db in "${dbs[@]}"; do
        for t in "${tables[@]}"; do
            local defv=$(clickhouse-client --query "SELECT default_expression FROM system.columns WHERE database='${db}' AND table='${t}' AND name='created_at'" 2>/dev/null || echo "")
            defv=$(echo "$defv" | tr -d ' ' | tr 'A-Z' 'a-z')
            if [ -n "$defv" ] && [[ "$defv" != *"now64(3)"* ]]; then
                log_warn "修复 ${db}.${t}.created_at 默认值: $defv -> now64(3)"
                clickhouse-client --query "ALTER TABLE ${db}.${t} MODIFY COLUMN created_at DateTime64(3, 'UTC') DEFAULT now64(3)" 2>/dev/null || true
            fi
        done
    done
}

# 🔧 增强：自动表结构检测和修复逻辑
auto_fix_table_schema() {

    log_info "检测并修复表结构问题..."

    # 检查LSR表的列结构
    check_and_fix_lsr_tables

    # 检查其他表的DateTime64格式
    check_and_fix_datetime_columns

    log_info "表结构检测和修复完成"

    # 确保 created_at 默认值一致
    ensure_created_at_default

}

# 🔧 新增：检查和修复LSR表结构
check_and_fix_lsr_tables() {
    log_info "检查LSR表结构..."

    # 检查lsr_top_positions表
    local top_pos_missing=$(clickhouse-client --query "
        SELECT COUNT(*) FROM system.columns
        WHERE database = '$DB_NAME_HOT' AND table = 'lsr_top_positions'
        AND name IN ('long_position_ratio', 'short_position_ratio')
    " 2>/dev/null || echo "0")

    if [ "$top_pos_missing" -lt 2 ]; then
        log_info "修复lsr_top_positions表结构..."
        clickhouse-client --query "
            ALTER TABLE $DB_NAME_HOT.lsr_top_positions
            ADD COLUMN IF NOT EXISTS long_position_ratio Float64 CODEC(ZSTD),
            ADD COLUMN IF NOT EXISTS short_position_ratio Float64 CODEC(ZSTD)
        " 2>/dev/null || true
    fi

    # 检查lsr_all_accounts表
    local all_acc_missing=$(clickhouse-client --query "
        SELECT COUNT(*) FROM system.columns
        WHERE database = '$DB_NAME_HOT' AND table = 'lsr_all_accounts'
        AND name IN ('long_account_ratio', 'short_account_ratio')
    " 2>/dev/null || echo "0")

    if [ "$all_acc_missing" -lt 2 ]; then
        log_info "修复lsr_all_accounts表结构..."
        clickhouse-client --query "
            ALTER TABLE $DB_NAME_HOT.lsr_all_accounts
            ADD COLUMN IF NOT EXISTS long_account_ratio Float64 CODEC(ZSTD),
            ADD COLUMN IF NOT EXISTS short_account_ratio Float64 CODEC(ZSTD)
        " 2>/dev/null || true
    fi
}

# 🔧 新增：检查和修复DateTime列格式
check_and_fix_datetime_columns() {
    log_info "检查DateTime列格式..."

    local tables_to_check=("funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")

    for table in "${tables_to_check[@]}"; do
        local timestamp_type=$(clickhouse-client --query "
            SELECT type FROM system.columns
            WHERE database = '$DB_NAME_HOT' AND table = '$table' AND name = 'timestamp'
        " 2>/dev/null || echo "")

        if [[ "$timestamp_type" == "DateTime" ]]; then
            log_warn "表 $table 的timestamp字段需要重建为DateTime64(3, 'UTC')"
            # 这种情况需要重建表，在create_unified_tables中处理
        fi
    done
}

# 🔧 新增：内置表创建逻辑（完整版）
create_tables_inline() {
    log_info "使用内置逻辑创建完整表结构..."

    # 创建所有必需的表，包含正确的列结构
    clickhouse-client --database="$DB_NAME_HOT" --multiquery << 'EOF'
-- 资金费率数据表
CREATE TABLE IF NOT EXISTS funding_rates (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    funding_rate Float64 CODEC(ZSTD),
    funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    next_funding_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192;

-- 未平仓量数据表
CREATE TABLE IF NOT EXISTS open_interests (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    open_interest Float64 CODEC(ZSTD),
    open_interest_value Float64 CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192;

-- 清算数据表
CREATE TABLE IF NOT EXISTS liquidations (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    side LowCardinality(String) CODEC(ZSTD),
    price Float64 CODEC(ZSTD),
    quantity Float64 CODEC(ZSTD),
    liquidation_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192;

-- LSR大户持仓比例数据表
CREATE TABLE IF NOT EXISTS lsr_top_positions (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    period LowCardinality(String) CODEC(ZSTD),
    long_ratio Float64 CODEC(ZSTD),
    short_ratio Float64 CODEC(ZSTD),
    long_position_ratio Float64 CODEC(ZSTD),
    short_position_ratio Float64 CODEC(ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
SETTINGS index_granularity = 8192;

-- LSR全账户持仓比例数据表
CREATE TABLE IF NOT EXISTS lsr_all_accounts (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    period LowCardinality(String) CODEC(ZSTD),
    long_ratio Float64 CODEC(ZSTD),
    short_ratio Float64 CODEC(ZSTD),
    long_account_ratio Float64 CODEC(ZSTD),
    short_account_ratio Float64 CODEC(ZSTD),

    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
SETTINGS index_granularity = 8192;

-- 波动率指数数据表
CREATE TABLE IF NOT EXISTS volatility_indices (
    timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    exchange LowCardinality(String) CODEC(ZSTD),
    market_type LowCardinality(String) CODEC(ZSTD),
    symbol LowCardinality(String) CODEC(ZSTD),
    volatility_index Float64 CODEC(ZSTD),
    index_value Float64 CODEC(ZSTD),
    underlying_asset LowCardinality(String) CODEC(ZSTD),
    maturity_time DateTime64(3, 'UTC') CODEC(Delta, ZSTD),
    data_source LowCardinality(String) DEFAULT 'marketprism' CODEC(ZSTD),
    created_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
SETTINGS index_granularity = 8192;
EOF

    log_info "内置表创建完成"
}

start_service() {
    log_step "启动服务"


    # 启动前冲突扫描（仅警告，不中断）
    conflict_scan

    # 容器化优先：容器化模式下跳过宿主机 ClickHouse 安装/启动/本地 schema 初始化
    if is_containerized; then
        log_info "容器化部署：跳过宿主机 ClickHouse 安装/启动/本地 schema 初始化（由 compose:init-hot-schema 负责）"


    else
        # 🔧 自动检测并安装ClickHouse
        if ! command -v clickhouse-server &> /dev/null; then
            log_warn "ClickHouse 未安装，开始自动安装..."
            curl https://clickhouse.com/ | sh
            sudo ./clickhouse install
            log_info "ClickHouse 安装完成"
        fi

        # 🔧 确保 ClickHouse 运行
        if ! pgrep -f "clickhouse-server" > /dev/null; then
            log_info "启动 ClickHouse..."
            sudo clickhouse start || true  # 忽略已运行的错误
            sleep 5
        else
            log_info "ClickHouse已在运行"
        fi

        # 🔧 等待ClickHouse完全可用
        local retry_count=0
        while ! clickhouse-client --query "SELECT 1" >/dev/null 2>&1; do
            if [ $retry_count -ge 30 ]; then
                log_error "ClickHouse连接超时"
                return 1
            fi
            log_info "等待ClickHouse可用... ($((retry_count + 1))/30)"
            sleep 2
            ((retry_count++))
        done
        log_info "ClickHouse连接成功"

        # 🔧 自动初始化数据库表（热端和冷端）
        clickhouse-client --query "CREATE DATABASE IF NOT EXISTS $DB_NAME_HOT; CREATE DATABASE IF NOT EXISTS $DB_NAME_COLD;" >/dev/null 2>&1 || true
        if [ -f "$DB_SCHEMA_FILE" ]; then
            log_info "检查并初始化热端数据库表..."
            local table_count=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" 2>/dev/null | wc -l | tr -dc '0-9')
            [ -z "$table_count" ] && table_count=0
            if [ "$table_count" -lt 8 ]; then
                log_info "初始化热端数据库表..."
                clickhouse-client --multiquery < "$DB_SCHEMA_FILE" 2>&1 | grep -v "^$" || true
                table_count=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" | wc -l | tr -dc '0-9')
                log_info "热端已创建 $table_count 个表"
            else
                log_info "热端数据库表已存在 ($table_count 个表)"
            fi
        fi
        if [ -f "$DB_SCHEMA_COLD_FILE" ]; then
            log_info "检查并初始化冷端数据库表..."
            local table_count_cold=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_COLD" 2>/dev/null | wc -l | tr -dc '0-9')
            [ -z "$table_count_cold" ] && table_count_cold=0
            if [ "$table_count_cold" -lt 8 ]; then
                log_info "初始化冷端数据库表..."
                clickhouse-client --multiquery < "$DB_SCHEMA_COLD_FILE" 2>&1 | grep -v "^$" || true
                table_count_cold=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_COLD" | wc -l | tr -dc '0-9')
                log_info "冷端已创建 $table_count_cold 个表"
            else
                log_info "冷端数据库表已存在 ($table_count_cold 个表)"
            fi
        fi
    fi

    # 🔧 自动创建虚拟环境并安装依赖
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        log_info "安装 Python 依赖..."
        local deps=(
            "nats-py" "aiohttp" "requests" "clickhouse-driver"
            "PyYAML" "python-dateutil" "structlog" "aiochclient"
            "sqlparse" "prometheus_client"
        )
        pip install -q --upgrade pip
        pip install -q "${deps[@]}" || {
            log_error "依赖安装失败"
            return 1
        }
    else
        source "$VENV_DIR/bin/activate"
        # 确保关键依赖已安装（幂等性检查）
        local missing_deps=()
        local deps=("nats-py" "aiohttp" "requests" "clickhouse-driver" "PyYAML" "python-dateutil" "structlog" "aiochclient" "sqlparse" "prometheus_client")
        for dep in "${deps[@]}"; do
            if ! pip show "$dep" >/dev/null 2>&1; then
                missing_deps+=("$dep")
            fi
        done

        if [ ${#missing_deps[@]} -gt 0 ]; then
            log_info "安装缺失的依赖: ${missing_deps[*]}"
            pip install -q "${missing_deps[@]}" || {
                log_error "依赖安装失败"
                return 1
            }
        fi
    fi

    # 启动热端存储
    if [ -f "$PID_FILE_HOT" ] && kill -0 $(cat "$PID_FILE_HOT") 2>/dev/null; then
        log_warn "热端存储服务已在运行"
        return 0
    fi

    mkdir -p "$LOG_DIR"
    cd "$MODULE_ROOT"
    # Hot Storage 使用 --config 参数指定配置文件
    nohup "$VENV_DIR/bin/python" main.py --config "$MODULE_ROOT/config/hot_storage_config.yaml" > "$LOG_FILE_HOT" 2>&1 &
    echo $! > "$PID_FILE_HOT"
    sleep 10

    if [ -f "$PID_FILE_HOT" ] && kill -0 $(cat "$PID_FILE_HOT") 2>/dev/null; then
        log_info "热端存储服务启动成功 (PID: $(cat $PID_FILE_HOT))"
        log_info "HTTP端口: $HOT_STORAGE_PORT"
    else
        log_error "启动失败，查看日志: $LOG_FILE_HOT"
        tail -20 "$LOG_FILE_HOT"
        exit 1
    fi
}

start_cold() {
    log_step "启动冷端存储服务"


    #       
    conflict_scan

    # 🔧 智能ClickHouse启动和状态检查
    ensure_clickhouse_running

    # 创建虚拟环境并确保依赖
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate"
    # 确保所有必需依赖存在
    pip install -q --upgrade pip || true

    # 使用与install_deps相同的依赖列表确保一致性
    local deps=(
        "nats-py" "aiohttp" "requests" "clickhouse-driver"
        "PyYAML" "python-dateutil" "structlog" "aiochclient"
        "sqlparse" "prometheus_client"
    )
    pip install -q "${deps[@]}" || true

    # 启动冷端
    if [ -f "$PID_FILE_COLD" ] && kill -0 $(cat "$PID_FILE_COLD") 2>/dev/null; then
        log_warn "冷端存储服务已在运行"
        return 0
    fi

    mkdir -p "$LOG_DIR"
    cd "$MODULE_ROOT"
    echo "[diag] using python: $VENV_DIR/bin/python" >> "$LOG_FILE_COLD" 2>&1 || true
    "$VENV_DIR/bin/python" -c "import sys; print('[diag] sys.prefix=', sys.prefix)" >> "$LOG_FILE_COLD" 2>&1 || true
    "$VENV_DIR/bin/python" -c "import aiochclient,sqlparse; print('[diag] deps ok')" >> "$LOG_FILE_COLD" 2>&1 || true
    # Cold Storage 不需要 --mode 参数，使用默认配置或 --config 指定
    nohup "$VENV_DIR/bin/python" main.py >> "$LOG_FILE_COLD" 2>&1 &
    echo $! > "$PID_FILE_COLD"
    sleep 8

    if [ -f "$PID_FILE_COLD" ] && kill -0 $(cat "$PID_FILE_COLD") 2>/dev/null; then
        log_info "冷端存储服务启动成功 (PID: $(cat $PID_FILE_COLD))"
        # 尝试健康检查
        curl -sf "http://127.0.0.1:$COLD_STORAGE_PORT/health" >/dev/null 2>&1 && log_info "冷端健康: healthy" || log_warn "冷端健康检查暂未通过（可能仍在启动）"
    else
        log_error "冷端启动失败，查看日志: $LOG_FILE_COLD"
        tail -30 "$LOG_FILE_COLD" || true
        return 1
    fi
}

stop_cold() {
    log_step "停止冷端存储服务"
    if [ -f "$PID_FILE_COLD" ]; then
        local pid=$(cat "$PID_FILE_COLD")
        if kill -0 $pid 2>/dev/null; then
            kill $pid
            sleep 2
            kill -0 $pid 2>/dev/null && kill -9 $pid 2>/dev/null || true
        fi
        rm -f "$PID_FILE_COLD"
    else
        log_warn "冷端存储: 未运行或PID文件缺失"
    fi
}

stop_service() {
    log_step "停止服务"

    # 停止热端
    if [ -f "$PID_FILE_HOT" ]; then
        local pid=$(cat "$PID_FILE_HOT")
        if kill -0 $pid 2>/dev/null; then
            log_info "停止热端存储服务..."
            kill $pid
            sleep 2
            kill -0 $pid 2>/dev/null && kill -9 $pid 2>/dev/null || true
        fi
        rm -f "$PID_FILE_HOT"
    fi

    # 停止冷端
    if [ -f "$PID_FILE_COLD" ]; then
        local pidc=$(cat "$PID_FILE_COLD")
        if kill -0 $pidc 2>/dev/null; then
            log_info "停止冷端存储服务..."
            kill $pidc
            sleep 2
            kill -0 $pidc 2>/dev/null && kill -9 $pidc 2>/dev/null || true
        fi
        rm -f "$PID_FILE_COLD"
    fi

    log_info "服务已停止"
}

restart_service() {
    stop_service
    sleep 2
    start_service
}

check_status() {
    log_step "检查状态"

    # ClickHouse
    if pgrep -f "clickhouse-server" > /dev/null; then
        log_info "ClickHouse: 运行中"
    else
        log_warn "ClickHouse: 未运行"
    fi

    # 热端存储
    if [ -f "$PID_FILE_HOT" ] && kill -0 $(cat "$PID_FILE_HOT") 2>/dev/null; then
        log_info "热端存储: 运行中 (PID: $(cat $PID_FILE_HOT))"
        ss -ltn | grep -q ":$HOT_STORAGE_PORT " && log_info "  端口 $HOT_STORAGE_PORT: 监听中" || log_warn "  端口未监听"
    else
        log_warn "热端存储: 未运行"
    fi

    # 冷端存储
    if [ -f "$PID_FILE_COLD" ] && kill -0 $(cat "$PID_FILE_COLD") 2>/dev/null; then
        log_info "冷端存储: 运行中 (PID: $(cat $PID_FILE_COLD))"
        ss -ltn | grep -q ":$COLD_STORAGE_PORT " && log_info "  端口 $COLD_STORAGE_PORT: 监听中" || log_warn "  端口未监听"
    else
        log_warn "冷端存储: 未运行"
    fi
}

check_health() {
    log_step "增强健康检查"
    local health_status=0

    # ClickHouse基础检查
    if curl -s "http://localhost:8123/" --data "SELECT 1" | grep -q "1"; then
        log_info "ClickHouse: healthy"
    else
        log_error "ClickHouse: unhealthy"
        health_status=1
    fi

    # 热端服务检查
    if curl -s "http://localhost:$HOT_STORAGE_PORT/health" | grep -q "healthy"; then
        log_info "热端存储: healthy"
    else
        log_warn "热端存储: 健康检查未通过"
        health_status=1
    fi

    # 冷端服务检查
    if curl -s "http://localhost:$COLD_STORAGE_PORT/health" | grep -q "\"status\": \"healthy\""; then
        log_info "冷端存储: healthy"
    else
        log_warn "冷端存储: 健康检查未通过"
    fi

    # 🔧 数据流验证
    validate_data_flow

    return $health_status
}

# 🔧 新增：数据流验证函数
validate_data_flow() {
    log_info "验证数据流..."

    # 检查表记录数
    local trades_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.trades" 2>/dev/null || echo "0")
    local orderbooks_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.orderbooks" 2>/dev/null || echo "0")
    local funding_rates_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.funding_rates" 2>/dev/null || echo "0")
    local open_interests_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.open_interests" 2>/dev/null || echo "0")
    local liquidations_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.liquidations" 2>/dev/null || echo "0")
    local lsr_top_positions_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.lsr_top_positions" 2>/dev/null || echo "0")
    local lsr_all_accounts_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.lsr_all_accounts" 2>/dev/null || echo "0")
    local volatility_indices_count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.volatility_indices" 2>/dev/null || echo "0")


    log_info "数据记录统计:"
    log_info "  - Trades: $trades_count 条"
    log_info "  - Orderbooks: $orderbooks_count 条"
    log_info "  - Funding_rates: $funding_rates_count 条"
    log_info "  - Open_interests: $open_interests_count 条"
    log_info "  - Liquidations: $liquidations_count 条"
    log_info "  - LSR Top Positions: $lsr_top_positions_count 条"
    log_info "  - LSR All Accounts: $lsr_all_accounts_count 条"
    log_info "  - Volatility_indices: $volatility_indices_count 条"

    # 冷端各表计数（用于健康检查视图整合）
    local cold_host="${COLD_CH_HOST:-127.0.0.1}"
    local cold_port=$([ "${COLD_MODE:-local}" = "docker" ] && echo "${COLD_CH_TCP_PORT:-9001}" || echo "${COLD_CH_TCP_PORT:-9000}")
    # 自适应探测冷端端口（未显式设置 COLD_MODE 时，优先尝试 9001 再回退 9000）
    if ! clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" >/dev/null 2>&1; then
        if clickhouse-client --host "$cold_host" --port "9001" --query "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" >/dev/null 2>&1; then
            cold_port="9001"
        elif clickhouse-client --host "$cold_host" --port "9000" --query "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" >/dev/null 2>&1; then
            cold_port="9000"
        fi
    fi


    # 优先使用冷端HTTP接口统计，失败时再回退到TCP客户端
    local cold_http_port="${COLD_CH_HTTP_PORT:-}"
    if [ -z "$cold_http_port" ]; then
        if curl -s "http://$cold_host:8124/" --data "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" | grep -q "1"; then
            cold_http_port=8124
        elif curl -s "http://$cold_host:8123/" --data "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" | grep -q "1"; then
            cold_http_port=8123
        else
            cold_http_port=$([ "${COLD_MODE:-local}" = "docker" ] && echo 8124 || echo 8123)
        fi
    fi

    local cold_trades_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.trades" 2>/dev/null || true)
    [[ "$cold_trades_count" =~ ^[0-9]+$ ]] || cold_trades_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.trades" 2>/dev/null || echo "0")

    local cold_orderbooks_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.orderbooks" 2>/dev/null || true)
    [[ "$cold_orderbooks_count" =~ ^[0-9]+$ ]] || cold_orderbooks_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.orderbooks" 2>/dev/null || echo "0")

    local cold_funding_rates_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.funding_rates" 2>/dev/null || true)
    [[ "$cold_funding_rates_count" =~ ^[0-9]+$ ]] || cold_funding_rates_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.funding_rates" 2>/dev/null || echo "0")

    local cold_open_interests_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.open_interests" 2>/dev/null || true)
    [[ "$cold_open_interests_count" =~ ^[0-9]+$ ]] || cold_open_interests_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.open_interests" 2>/dev/null || echo "0")

    local cold_liquidations_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.liquidations" 2>/dev/null || true)
    [[ "$cold_liquidations_count" =~ ^[0-9]+$ ]] || cold_liquidations_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.liquidations" 2>/dev/null || echo "0")

    local cold_lsr_top_positions_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.lsr_top_positions" 2>/dev/null || true)
    [[ "$cold_lsr_top_positions_count" =~ ^[0-9]+$ ]] || cold_lsr_top_positions_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.lsr_top_positions" 2>/dev/null || echo "0")

    local cold_lsr_all_accounts_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.lsr_all_accounts" 2>/dev/null || true)
    [[ "$cold_lsr_all_accounts_count" =~ ^[0-9]+$ ]] || cold_lsr_all_accounts_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.lsr_all_accounts" 2>/dev/null || echo "0")

    local cold_volatility_indices_count=$(curl -s "http://$cold_host:$cold_http_port/" --data "SELECT COUNT(*) FROM $DB_NAME_COLD.volatility_indices" 2>/dev/null || true)
    [[ "$cold_volatility_indices_count" =~ ^[0-9]+$ ]] || cold_volatility_indices_count=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM $DB_NAME_COLD.volatility_indices" 2>/dev/null || echo "0")

    log_info "冷端数据统计:"
    log_info "  - Trades: $cold_trades_count 条"
    log_info "  - Orderbooks: $cold_orderbooks_count 条"
    log_info "  - Funding_rates: $cold_funding_rates_count 条"
    log_info "  - Open_interests: $cold_open_interests_count 条"
    log_info "  - Liquidations: $cold_liquidations_count 条"
    log_info "  - LSR Top Positions: $cold_lsr_top_positions_count 条"
    log_info "  - LSR All Accounts: $cold_lsr_all_accounts_count 条"
    log_info "  - Volatility_indices: $cold_volatility_indices_count 条"



    # 检查数据质量（按交易所和市场类型）
    if [ "$trades_count" -gt 0 ]; then
        log_info "Trades数据分布:"
        clickhouse-client --query "
            SELECT
                exchange,
                market_type,
                COUNT(*) as count,
                COUNT(DISTINCT symbol) as symbols
            FROM $DB_NAME_HOT.trades
            GROUP BY exchange, market_type
            ORDER BY exchange, market_type
        " 2>/dev/null | while read line; do
            log_info "  - $line"
        done
    fi

    if [ "$orderbooks_count" -gt 0 ]; then
        log_info "Orderbooks数据分布:"
        clickhouse-client --query "
            SELECT
                exchange,
                market_type,
                COUNT(*) as count,
                COUNT(DISTINCT symbol) as symbols
            FROM $DB_NAME_HOT.orderbooks
            GROUP BY exchange, market_type
            ORDER BY exchange, market_type
        " 2>/dev/null | while read line; do
            log_info "  - $line"
        done
    fi

    # 检查数据新鲜度（最近5分钟是否有新数据）
    local recent_trades=$(clickhouse-client --query "
        SELECT COUNT(*) FROM $DB_NAME_HOT.trades
        WHERE timestamp > now() - INTERVAL 5 MINUTE
    " 2>/dev/null || echo "0")
    local recent_orderbooks=$(clickhouse-client --query "
        SELECT COUNT(*) FROM $DB_NAME_HOT.orderbooks
        WHERE timestamp > now() - INTERVAL 5 MINUTE
    " 2>/dev/null || echo "0")

    if [ "$recent_trades" -gt 0 ] || [ "$recent_orderbooks" -gt 0 ]; then
        log_info "数据流状态: 活跃 (最近5分钟 trades=$recent_trades, orderbooks=$recent_orderbooks)"
    else
        log_warn "数据流状态: 可能停滞 (最近5分钟无新数据)"
    fi
}

show_logs() {
    log_step "查看日志"
    if [ "$2" = "cold" ]; then
        [ -f "$LOG_FILE_COLD" ] && tail -f "$LOG_FILE_COLD" || log_warn "冷端日志文件不存在"
    else
        [ -f "$LOG_FILE_HOT" ] && tail -f "$LOG_FILE_HOT" || log_warn "热端日志文件不存在"
    fi
}

clean_service() {
    log_step "清理"
    stop_service
    rm -f "$PID_FILE_HOT" "$PID_FILE_COLD"
    [ -f "$LOG_FILE_HOT" ] && > "$LOG_FILE_HOT"
    [ -f "$LOG_FILE_COLD" ] && > "$LOG_FILE_COLD"
    log_info "清理完成"
}

# 🔧 新增：数据迁移验证功能
verify_migration() {
    log_step "验证数据迁移状态"

    # 检查冷端数据库是否存在
    if ! clickhouse-client --host "${COLD_CH_HOST:-127.0.0.1}" --port $([ "${COLD_MODE:-local}" = "docker" ] && echo "${COLD_CH_TCP_PORT:-9001}" || echo "${COLD_CH_TCP_PORT:-9000}") --query "SELECT 1 FROM system.databases WHERE name = 'marketprism_cold'" | grep -q "1"; then
        log_error "冷端数据库不存在，请先初始化冷端存储服务"
        return 1
    fi

    # 使用Python脚本进行详细验证
    local migrator_script="$SCRIPT_DIR/hot_to_cold_migrator.py"
    if [ -f "$migrator_script" ]; then
        log_info "使用增强迁移脚本进行验证..."
        cd "$SCRIPT_DIR"

        # 激活虚拟环境
        if [ -d "$VENV_DIR" ]; then
            source "$VENV_DIR/bin/activate"
        fi

        # 运行验证（干跑模式）
        MIGRATION_DRY_RUN=1 python3 "$migrator_script"
        local exit_code=$?

        if [ $exit_code -eq 0 ]; then
            log_info "数据迁移验证通过"
        else
            log_warn "数据迁移验证发现问题，建议运行修复"
        fi

        return $exit_code
    else
        log_error "迁移脚本不存在: $migrator_script"
        return 1
    fi
}

# 🔧 新增：一键修复数据迁移问题
repair_migration() {
    log_step "一键修复数据迁移问题"

    # 检查冷端数据库是否存在
    if ! clickhouse-client --host "${COLD_CH_HOST:-127.0.0.1}" --port $([ "${COLD_MODE:-local}" = "docker" ] && echo "${COLD_CH_TCP_PORT:-9001}" || echo "${COLD_CH_TCP_PORT:-9000}") --query "SELECT 1 FROM system.databases WHERE name = 'marketprism_cold'" | grep -q "1"; then
        log_error "冷端数据库不存在，请先初始化冷端存储服务"
        return 1
    fi

    # 使用Python脚本进行修复
    local migrator_script="$SCRIPT_DIR/hot_to_cold_migrator.py"
    if [ -f "$migrator_script" ]; then
        log_info "使用增强迁移脚本进行修复..."
        cd "$SCRIPT_DIR"

        # 激活虚拟环境
        if [ -d "$VENV_DIR" ]; then
            source "$VENV_DIR/bin/activate"
        fi

        # 运行强制修复模式
        MIGRATION_FORCE_REPAIR=1 python3 "$migrator_script"
        local exit_code=$?
    # ensure created_at default normalized to now64(3)
    ensure_created_at_default


        if [ $exit_code -eq 0 ]; then
            log_info "数据迁移修复成功"
        else
            log_error "数据迁移修复失败"
        fi

        return $exit_code
    else
        log_error "迁移脚本不存在: $migrator_script"
        return 1
    fi
}

# 🔧 新增：完整的数据完整性检查
check_data_integrity() {
    log_step "检查数据完整性"


    # 先行修复 created_at 默认值，保证校验通过
    ensure_created_at_default

    # Schema 一致性检查（忽略 TTL）
    if command -v python3 >/dev/null 2>&1; then
        python3 "$SCRIPT_DIR/validate_schema_consistency.py"
        rc=$?
        if [ $rc -ne 0 ]; then
            log_error "Schema 一致性检查失败 (rc=$rc)"
            return $rc
        else
            log_info "Schema 一致性检查通过"
        fi
    else
        log_warn "python3 不可用，跳过 Schema 一致性检查"
    fi

    # 统一表集合
    local tables=(
        "trades" "orderbooks"
        "funding_rates" "open_interests" "liquidations"
        "lsr_top_positions" "lsr_all_accounts" "volatility_indices"
    )

    # 每种数据类型的“最近窗口”定义（高频5m，低频8h，事件1h）
    declare -A window_hot=(
        [trades]="5 MINUTE" [orderbooks]="5 MINUTE" \
        [funding_rates]="8 HOUR" [open_interests]="8 HOUR" \
        [lsr_top_positions]="8 HOUR" [lsr_all_accounts]="8 HOUR" \
        [volatility_indices]="8 HOUR" [liquidations]="1 HOUR"
    )
    declare -A hot_recent




    # 事件型表放宽标志（仅 liquidations 暂缺且采集器健康时为 1）
    local LIQ_EVENT_OK=0

    # 统计热端数据
    log_info "检查热端数据..."
    declare -A hot_counts
    local hot_total=0
    for t in "${tables[@]}"; do
        local cnt=$(clickhouse-client --query "SELECT COUNT(*) FROM marketprism_hot.${t}" 2>/dev/null || echo "0")
        hot_counts[$t]=$cnt
        hot_total=$((hot_total + cnt))
        # 计算最近窗口内的热端数据量
        local recent_win=${window_hot[$t]}
        local rcnt=$(clickhouse-client --query "SELECT COUNT() FROM marketprism_hot.${t} WHERE timestamp > now() - INTERVAL ${recent_win}" 2>/dev/null || echo "0")
        hot_recent[$t]=$rcnt
        if [ "$cnt" -gt 0 ]; then
            log_info "热端 $t: $cnt 条记录"
        else
            log_warn "热端 $t: 无数据"
        fi
    done

    # 基本失败条件：热端无高频数据或总数据为0
    if [ "$hot_total" -eq 0 ] || { [ "${hot_counts[trades]:-0}" -eq 0 ] && [ "${hot_counts[orderbooks]:-0}" -eq 0 ]; }; then
        log_error "数据完整性失败：热端无高频数据（trades/orderbooks）或总数据为0"
        return 2
    fi

    # 冷端连接探测（HTTP 优先，TCP 回退）
    local cold_host="${COLD_CH_HOST:-127.0.0.1}"
    local cold_port=$([ "${COLD_MODE:-local}" = "docker" ] && echo "${COLD_CH_TCP_PORT:-9001}" || echo "${COLD_CH_TCP_PORT:-9000}")
    local cold_http_port="${COLD_CH_HTTP_PORT:-}"
    local cold_db_ok=0

    # 优先通过 HTTP 探测数据库存在
    if curl -s "http://$cold_host:8124/" --data "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" | grep -q "1"; then
        cold_http_port=8124; cold_db_ok=1
    elif curl -s "http://$cold_host:8123/" --data "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" | grep -q "1"; then
        cold_http_port=8123; cold_db_ok=1
    else
        # 回退到 TCP 探测（优先已配置端口，其次 9001 再 9000）
        if clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" >/dev/null 2>&1; then
            cold_db_ok=1
        elif clickhouse-client --host "$cold_host" --port 9001 --query "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" >/dev/null 2>&1; then
            cold_port=9001; cold_db_ok=1
        elif clickhouse-client --host "$cold_host" --port 9000 --query "SELECT 1 FROM system.databases WHERE name='marketprism_cold'" >/dev/null 2>&1; then
            cold_port=9000; cold_db_ok=1
        fi
    fi

    if [ "$cold_db_ok" -ne 1 ]; then
        log_warn "冷端数据库不存在，跳过冷端检查"
        return 1
    fi

    # 若未确定 HTTP 端口，做一次兜底探测
    if [ -z "$cold_http_port" ]; then
        if curl -s "http://$cold_host:8124/" --data "SELECT 1" | grep -q "1"; then
            cold_http_port=8124
        elif curl -s "http://$cold_host:8123/" --data "SELECT 1" | grep -q "1"; then
            cold_http_port=8123
        fi
    fi

    # 统计冷端数据
    log_info "检查冷端数据..."
    declare -A cold_counts
    local cold_total=0
    declare -A cold_recent

    for t in "${tables[@]}"; do
        # 优先用 HTTP 统计，失败回退到 TCP
        local cnt
        cnt=$(curl -s "http://$cold_host:${cold_http_port:-8124}/" --data "SELECT COUNT(*) FROM marketprism_cold.${t}" 2>/dev/null || true)
        [[ "$cnt" =~ ^[0-9]+$ ]] || cnt=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT(*) FROM marketprism_cold.${t}" 2>/dev/null || echo "0")
        cold_counts[$t]=$cnt
        cold_total=$((cold_total + cnt))

        # 最近窗口
        local recent_win=${window_hot[$t]}
        local rcnt
        rcnt=$(curl -s "http://$cold_host:${cold_http_port:-8124}/" --data "SELECT COUNT() FROM marketprism_cold.${t} WHERE timestamp > now() - INTERVAL ${recent_win}" 2>/dev/null || true)
        [[ "$rcnt" =~ ^[0-9]+$ ]] || rcnt=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT COUNT() FROM marketprism_cold.${t} WHERE timestamp > now() - INTERVAL ${recent_win}" 2>/dev/null || echo "0")
        cold_recent[$t]=$rcnt

        if [ "$cnt" -gt 0 ]; then
            log_info "冷端 $t: $cnt 条记录"
        else
            log_warn "冷端 $t: 无数据"
        fi
    done

    # 事件型低频表：liquidations 特殊处理（短期无数据不视为故障）
    local liq_hot_cnt="${hot_counts[liquidations]:-0}"
    local liq_cold_cnt="${cold_counts[liquidations]:-0}"
    if [ "$liq_hot_cnt" -eq 0 ] && [ "$liq_cold_cnt" -eq 0 ]; then
        local COLLECTOR_HEALTH_URL="${COLLECTOR_HEALTH_URL:-http://localhost:8087/health}"
        local ch_body
        if ch_body=$(curl -sf "$COLLECTOR_HEALTH_URL" 2>/dev/null); then
            if echo "$ch_body" | grep -qi '"status"[[:space:]]*:[[:space:]]*"healthy"'; then
                log_info "liquidations 暂无数据，但采集器健康（WS 连接可能处于空闲），视为正常"
                LIQ_EVENT_OK=1
            else
                log_warn "liquidations 暂无数据，且采集器健康状态非 healthy：请关注采集器WS连接"
            fi
        else
            log_warn "liquidations 暂无数据，且无法访问采集器健康端点：$COLLECTOR_HEALTH_URL"
        fi
    fi


    # 读取热端清理策略状态（决定冷>热时的严重性等级）
    local cleanup_enabled="unknown"
    # 容错提取 cleanup_enabled（优先 Python 直连 /health；先冷端8086，后热端8085；仍不可得则默认true 以避免误报）
    set +e
    if command -v python3 >/dev/null 2>&1; then
        cleanup_enabled=$(python3 - <<'PY'
import json, urllib.request
for url in ("http://localhost:8086/health", "http://localhost:8085/health"):
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.load(resp)
        v = data.get("replication", {}).get("cleanup_enabled", None)
        if v is not None:
            print(str(bool(v)).lower())
            break
    except Exception:
        pass
else:
    print("true")
PY
)
    else
        cleanup_enabled=$(curl -sf http://localhost:8086/health 2>/dev/null | sed -n 's/.*"cleanup_enabled"[[:space:]]*:[[:space:]]*\(true\|false\).*/\1/p' | head -n1)
        if [ -z "$cleanup_enabled" ]; then
            cleanup_enabled=$(curl -sf http://localhost:8085/health 2>/dev/null | sed -n 's/.*"cleanup_enabled"[[:space:]]*:[[:space:]]*\(true\|false\).*/\1/p' | head -n1)
        fi
        [ -z "$cleanup_enabled" ] && cleanup_enabled="true"
    fi
    set -e
    if [ "$cleanup_enabled" = "true" ]; then cleanup_enabled="true"; else cleanup_enabled="false"; fi

    # 检查冷端>热端一致性
    local inconsistent_tables=()
    for t in "${tables[@]}"; do
        if [ "${cold_counts[$t]:-0}" -gt "${hot_counts[$t]:-0}" ]; then
            inconsistent_tables+=("$t")
        fi
    done

    if [ ${#inconsistent_tables[@]} -gt 0 ]; then
        if [ "$cleanup_enabled" = "true" ]; then
            log_info "信息提示：热端已启用清理策略，冷端保留历史更久；以下表冷端>热端属正常：${inconsistent_tables[*]}"
        else
            log_warn "数据一致性警告：未启用清理策略时出现冷端>热端：${inconsistent_tables[*]}"
            return 1
        fi
    fi


    # 基于“最近窗口”校验各类数据的时效性与热->冷复制可见性（liquidations 特殊放宽）
    local hf_recent_bad=0
    for t in "${tables[@]}"; do
        local rc_hot=${hot_recent[$t]:-0}
        local rc_cold=${cold_recent[$t]:-0}
        local win=${window_hot[$t]}
        if [ "$t" = "trades" ] || [ "$t" = "orderbooks" ]; then
            if [ "$rc_hot" -eq 0 ]; then
                log_warn "热端 $t: 最近 ${win} 内无数据"
                hf_recent_bad=1
            fi
            if [ "$rc_hot" -gt 0 ] && [ "$rc_cold" -eq 0 ]; then
                log_warn "冷端 $t: 热端最近有数据，但冷端最近窗口无数据（复制延迟/未覆盖）"
            fi
        else
            # 低频/事件型：仅给出提示，不作为失败条件
            if [ "$rc_hot" -eq 0 ]; then
                log_warn "热端 $t: 最近 ${win} 内无数据（低频/事件型提示）"
            fi
        fi
        # 复制滞后分钟数（>60min 警告）
        local hot_max=$(clickhouse-client --query "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.${t}" 2>/dev/null || echo "0")
        local cold_max
        cold_max=$(curl -s "http://$cold_host:${cold_http_port:-8124}/" --data "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.${t}" 2>/dev/null || true)
        [[ "$cold_max" =~ ^[0-9]+$ ]] || cold_max=$(clickhouse-client --host "$cold_host" --port "$cold_port" --query "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.${t}" 2>/dev/null || echo "0")
        [ -z "$hot_max" ] && hot_max=0; [ -z "$cold_max" ] && cold_max=0
        if [ "$hot_max" -gt 0 ]; then
            local lag_min
            if [ "$cold_max" -gt 0 ]; then
                lag_min=$(( (hot_max - cold_max) / 60000 ))
                [ "$lag_min" -lt 0 ] && lag_min=0
            else
                lag_min=999999
            fi
            if [ "$lag_min" -gt 60 ]; then
                log_warn "表 $t: 冷端相对热端的复制滞后 ${lag_min} 分钟 (>60min)"
            fi
        fi
    done

    # 高频数据在冷端的可用性（放宽要求，不因低频/事件为0而失败）
    local hf_ok=0
    if [ "${cold_counts[trades]:-0}" -gt 0 ]; then
        hf_ok=$((hf_ok+1))
    fi
    if [ "${cold_counts[orderbooks]:-0}" -gt 0 ]; then
        hf_ok=$((hf_ok+1))
    fi

    # 依据高频数据可用性给出初步判定
    local ret=0
    if [ "$hf_ok" -ge 1 ]; then
        ret=0
    else
        ret=1
    fi


    # 若高频最近窗口无数据，则将判定置为不通过（避免冷启动误报由上层总控负责重试）
    if [ $ret -eq 0 ] && [ "$hf_recent_bad" -eq 1 ]; then
        ret=1
    fi

    # 仅事件型缺失（且采集器健康）则放宽为通过
    if [ $ret -ne 0 ] && [ "${LIQ_EVENT_OK:-0}" -eq 1 ]; then
        log_info "仅事件型表(liquidations)暂缺且采集器健康：放宽为通过"
        ret=0
    fi

    log_info "DEBUG hf_ok=$hf_ok liq_ok=${LIQ_EVENT_OK:-0} cleanup_enabled=$cleanup_enabled cold_trades=${cold_counts[trades]:-0} cold_orderbooks=${cold_counts[orderbooks]:-0}"

    if [ $ret -eq 0 ]; then
        log_info "数据完整性判定：通过（高频在冷端可见；事件型暂缺可接受）"
    else
        log_warn "数据完整性提示：冷端暂缺高频数据，请稍后再检查"
    fi
    return $ret
}

diagnose() {
    log_step "快速诊断（Hot Storage）"

    echo "1) 关键端口监听 (8085/8123/9000)"
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp | grep -E ":(8085|8123|9000) " || echo "  - 未发现监听"
    elif command -v netstat >/dev/null 2>&1; then
        netstat -ltnp | grep -E ":(8085|8123|9000) " || echo "  - 未发现监听"
    else
        echo "  - 无 ss/netstat，跳过端口检查"
    fi

    echo "\n2) 宿主机进程"
    if pgrep -af "$PROJECT_ROOT/services/hot-storage-service/main.py" >/dev/null 2>&1; then
        pgrep -af "$PROJECT_ROOT/services/hot-storage-service/main.py" | sed 's/^/  - /'
    else
        echo "  - 未发现直跑进程"
    fi

    echo "\n3) 相关容器"
    if command -v docker >/dev/null 2>&1; then
        docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | egrep '^(marketprism-hot-storage-service|marketprism-clickhouse-hot|mp-cold-storage)' || echo "  - 未发现相关容器"
    else
        echo "  - 未安装 docker，跳过容器检查"
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
}

show_help() {
    cat << EOF
${CYAN}MarketPrism Hot Storage Service 管理脚本${NC}

用法: $0 [命令]

基础命令:
  install-deps           安装依赖
  init                   初始化服务（仅热端）
  start                  启动热端服务
  stop                   停止热端服务
  restart                重启热端服务
  status                 检查状态
  health                 健康检查
  logs                   查看热端日志
  clean                  清理
  integrity              检查数据完整性（热端）
  help                   显示帮助

示例:
  $0 install-deps && $0 init && $0 start
EOF
}

main() {
    cmd="${1:-help}"
    sub="${2:-}"
    case "$cmd" in
        install-deps) install_deps ;;
        init) init_service ;;
        start)
            start_service ;;
        stop)
            stop_service ;;
        restart) restart_service ;;
        status) check_status ;;
        health) check_health ;;
        diagnose) diagnose ;;
        logs) show_logs "$@" ;;
        clean) clean_service ;;
        integrity) check_data_integrity ;;
        help|--help|-h) show_help ;;
        *) log_error "未知命令: $cmd"; show_help; exit 1 ;;
    esac
}

main "$@"
