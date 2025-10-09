#!/bin/bash

################################################################################
# MarketPrism Data Storage Service 管理脚本
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

# 配置
MODULE_NAME="data-storage-service"
HOT_STORAGE_PORT=8085
COLD_STORAGE_PORT=8086
DB_SCHEMA_FILE="$MODULE_ROOT/config/clickhouse_schema.sql"
DB_NAME_HOT="marketprism_hot"

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

    # 安装 ClickHouse
    if ! command -v clickhouse-server &> /dev/null; then
        log_info "安装 ClickHouse..."
        curl https://clickhouse.com/ | sh
        sudo ./clickhouse install
    else
        log_info "ClickHouse 已安装"
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

    # 🔧 智能ClickHouse启动和状态检查
    ensure_clickhouse_running

    # 🔧 智能数据库初始化和修复
    init_and_fix_database

    log_info "初始化完成"
}

# 🔧 增强：智能数据库初始化和修复函数
init_and_fix_database() {
    log_info "智能数据库初始化和修复..."

    # 检查数据库是否存在
    clickhouse-client --query "CREATE DATABASE IF NOT EXISTS $DB_NAME_HOT" 2>/dev/null || true

    # 🔧 自动检测和修复表结构
    auto_fix_table_schema

    # 检查表结构
    local existing_tables=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" 2>/dev/null | wc -l || echo "0")

    if [ "$existing_tables" -lt 8 ]; then
        log_info "初始化数据库表..."

        # 尝试使用主schema文件
        if [ -f "$DB_SCHEMA_FILE" ]; then
            clickhouse-client --multiquery < "$DB_SCHEMA_FILE" 2>&1 | grep -v "^$" || true
        fi

        # 如果主schema失败，尝试使用简化schema
        local simple_schema="$MODULE_ROOT/config/clickhouse_schema_simple.sql"
        if [ -f "$simple_schema" ]; then
            log_info "使用简化schema创建表..."
            clickhouse-client --database="$DB_NAME_HOT" --multiquery < "$simple_schema" 2>&1 | grep -v "^$" || true
        fi

        local table_count=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" | wc -l)
        log_info "创建了 $table_count 个表"
    else
        log_info "数据库表已存在 ($existing_tables 个表)"

        # 🔧 检查并修复数据类型不匹配问题
        fix_table_schema_issues

        # 🔧 再次检查LSR表结构（确保修复完成）
        check_and_fix_lsr_tables
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
        local count=$(clickhouse-client --query "SELECT COUNT(*) FROM $DB_NAME_HOT.$table" 2>/dev/null || echo "0")
        if [ "$count" -gt 0 ]; then
            tables_with_data+=("$table:$count")
            log_info "备份表 $table ($count 条记录)..."
            clickhouse-client --query "CREATE TABLE IF NOT EXISTS $DB_NAME_HOT.${table}_backup AS $DB_NAME_HOT.$table" 2>/dev/null || true
            clickhouse-client --query "INSERT INTO $DB_NAME_HOT.${table}_backup SELECT * FROM $DB_NAME_HOT.$table" 2>/dev/null || true
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
        clickhouse-client --query "DROP TABLE IF EXISTS $DB_NAME_HOT.$table" 2>/dev/null || true
    done
}

# 🔧 新增：使用统一schema创建表
create_unified_tables() {
    log_info "使用统一schema创建表..."

    local unified_schema="$MODULE_ROOT/config/clickhouse_schema_unified.sql"
    if [ -f "$unified_schema" ]; then
        clickhouse-client --database="$DB_NAME_HOT" --multiquery < "$unified_schema" 2>&1 | grep -v "^$" || true
        log_info "统一表结构创建完成"
    else
        log_warn "统一schema文件不存在: $unified_schema，使用内置创建逻辑"
        create_tables_inline
    fi
}

# 🔧 新增：确保缺失的表被创建
ensure_missing_tables() {
    log_info "检查并创建缺失的表..."

    local required_tables=("funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")
    local missing_tables=()

    for table in "${required_tables[@]}"; do
        local exists=$(clickhouse-client --query "EXISTS TABLE $DB_NAME_HOT.$table" 2>/dev/null || echo "0")
        if [ "$exists" = "0" ]; then
            missing_tables+=("$table")
        fi
    done

    if [ ${#missing_tables[@]} -gt 0 ]; then
        log_info "创建缺失的表: ${missing_tables[*]}"
        create_unified_tables
    fi
}

# 🔧 增强：自动表结构检测和修复逻辑
auto_fix_table_schema() {
    log_info "检测并修复表结构问题..."

    # 检查LSR表的列结构
    check_and_fix_lsr_tables

    # 检查其他表的DateTime64格式
    check_and_fix_datetime_columns

    log_info "表结构检测和修复完成"
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
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
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
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
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
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
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
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
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
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol, period)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
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
    created_at DateTime DEFAULT now() CODEC(Delta, ZSTD)
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), exchange)
ORDER BY (timestamp, exchange, symbol)
TTL toDateTime(timestamp) + INTERVAL 3 DAY DELETE
SETTINGS index_granularity = 8192;
EOF

    log_info "内置表创建完成"
}

start_service() {
    log_step "启动服务"

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

    # 🔧 自动初始化数据库表
    if [ -f "$DB_SCHEMA_FILE" ]; then
        log_info "检查并初始化数据库表..."
        local table_count=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" 2>/dev/null | wc -l || echo "0")
        if [ "$table_count" -lt 8 ]; then
            log_info "初始化数据库表..."
            clickhouse-client --multiquery < "$DB_SCHEMA_FILE" 2>&1 | grep -v "^$" || true
            table_count=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" | wc -l)
            log_info "创建了 $table_count 个表"
        else
            log_info "数据库表已存在 ($table_count 个表)"
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
    nohup "$VENV_DIR/bin/python" main.py --mode hot > "$LOG_FILE_HOT" 2>&1 &
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
    nohup "$VENV_DIR/bin/python" main.py --mode cold >> "$LOG_FILE_COLD" 2>&1 &
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

    log_info "数据记录统计:"
    log_info "  - Trades: $trades_count 条"
    log_info "  - Orderbooks: $orderbooks_count 条"

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

    if [ "$recent_trades" -gt 0 ]; then
        log_info "数据流状态: 活跃 (最近5分钟有 $recent_trades 条新trades)"
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
    if ! clickhouse-client --query "SELECT 1 FROM system.databases WHERE name = 'marketprism_cold'" | grep -q "1"; then
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
    if ! clickhouse-client --query "SELECT 1 FROM system.databases WHERE name = 'marketprism_cold'" | grep -q "1"; then
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

    local integrity_score=0
    local total_tables=8
    local tables_with_data=0

    # 检查热端数据
    log_info "检查热端数据..."
    local hot_tables=("trades" "orderbooks" "funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")

    for table in "${hot_tables[@]}"; do
        local count=$(clickhouse-client --query "SELECT COUNT(*) FROM marketprism_hot.$table" 2>/dev/null || echo "0")
        if [ "$count" -gt 0 ]; then
            log_info "热端 $table: $count 条记录"
        else
            log_warn "热端 $table: 无数据"
        fi
    done

    # 检查冷端数据
    if clickhouse-client --query "SELECT 1 FROM system.databases WHERE name = 'marketprism_cold'" | grep -q "1"; then
        log_info "检查冷端数据..."

        for table in "${hot_tables[@]}"; do
            local count=$(clickhouse-client --query "SELECT COUNT(*) FROM marketprism_cold.$table" 2>/dev/null || echo "0")
            if [ "$count" -gt 0 ]; then
                log_info "冷端 $table: $count 条记录"
                ((tables_with_data++))
            else
                log_warn "冷端 $table: 无数据"
            fi
        done

        integrity_score=$((tables_with_data * 100 / total_tables))
        log_info "数据完整性评分: $integrity_score% ($tables_with_data/$total_tables)"

        if [ $integrity_score -eq 100 ]; then
            log_info "所有数据类型都有数据，数据完整性良好"
            return 0
        elif [ $integrity_score -ge 50 ]; then
            log_warn "部分数据类型缺失，建议运行修复: $0 repair"
            return 1
        else
            log_error "大部分数据类型缺失，请检查系统配置"
            return 2
        fi
    else
        log_warn "冷端数据库不存在，跳过冷端检查"
        return 1
    fi
}

show_help() {
    cat << EOF
${CYAN}MarketPrism Data Storage Service 管理脚本 (增强版)${NC}

用法: $0 [命令] [hot|cold]

基础命令:
  install-deps           安装依赖
  init                   初始化服务
  start [hot|cold]       启动服务（默认hot）
  stop  [hot|cold]       停止服务（默认hot）
  restart                重启服务（hot）
  status                 检查状态
  health                 健康检查
  logs [hot|cold]        查看日志
  clean                  清理
  help                   显示帮助

🔧 数据迁移命令:
  verify                 验证数据迁移状态
  repair                 一键修复数据迁移问题
  integrity              检查数据完整性

示例:
  $0 install-deps && $0 init && $0 start
  $0 start cold
  $0 logs cold
  $0 verify              # 验证数据迁移
  $0 repair              # 修复数据迁移问题
  $0 integrity           # 检查数据完整性
EOF
}

main() {
    cmd="${1:-help}"
    sub="${2:-}"
    case "$cmd" in
        install-deps) install_deps ;;
        init) init_service ;;
        start)
            if [ "$sub" = "cold" ]; then start_cold; else start_service; fi ;;
        stop)
            if [ "$sub" = "cold" ]; then stop_cold; else stop_service; fi ;;
        restart) restart_service ;;
        status) check_status ;;
        health) check_health ;;
        logs) show_logs "$@" ;;
        clean) clean_service ;;
        verify) verify_migration ;;
        repair) repair_migration ;;
        integrity) check_data_integrity ;;
        help|--help|-h) show_help ;;
        *) log_error "未知命令: $cmd"; show_help; exit 1 ;;
    esac
}

main "$@"
