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

    # 完整的依赖列表，包含所有必需的包
    local deps=(
        "nats-py"
        "aiohttp"
        "requests"
        "clickhouse-driver"
        "PyYAML"
        "python-dateutil"
        "structlog"
        "aiochclient"
        "sqlparse"
        "prometheus_client"
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

    # 启动 ClickHouse
    if ! pgrep -x "clickhouse-server" > /dev/null; then
        log_info "启动 ClickHouse..."
        sudo clickhouse start
        sleep 5

        # 等待ClickHouse完全启动
        local retry_count=0
        while ! clickhouse-client --query "SELECT 1" >/dev/null 2>&1; do
            if [ $retry_count -ge 30 ]; then
                log_error "ClickHouse启动超时"
                return 1
            fi
            log_info "等待ClickHouse启动... ($((retry_count + 1))/30)"
            sleep 2
            ((retry_count++))
        done
        log_info "ClickHouse启动成功"
    else
        log_info "ClickHouse已在运行"
    fi

    # 初始化数据库
    if [ -f "$DB_SCHEMA_FILE" ]; then
        log_info "检查数据库表状态..."
        local existing_tables=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" 2>/dev/null | wc -l || echo "0")

        if [ "$existing_tables" -lt 8 ]; then
            log_info "初始化数据库表..."
            clickhouse-client --multiquery < "$DB_SCHEMA_FILE" || {
                log_error "数据库初始化失败"
                return 1
            }
            local table_count=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" | wc -l)
            log_info "创建了 $table_count 个表"
        else
            log_info "数据库表已存在 ($existing_tables 个表)"
        fi
    else
        log_warn "数据库schema文件不存在: $DB_SCHEMA_FILE"
    fi

    log_info "初始化完成"
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
    if ! pgrep -x "clickhouse-server" > /dev/null; then
        log_info "启动 ClickHouse..."
        sudo clickhouse start
        sleep 5

        # 等待ClickHouse完全启动
        local retry_count=0
        while ! clickhouse-client --query "SELECT 1" >/dev/null 2>&1; do
            if [ $retry_count -ge 30 ]; then
                log_error "ClickHouse启动超时"
                return 1
            fi
            log_info "等待ClickHouse启动... ($((retry_count + 1))/30)"
            sleep 2
            ((retry_count++))
        done
        log_info "ClickHouse启动成功"
    else
        log_info "ClickHouse已在运行"
    fi

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
            if ! pip list | grep -q "^${dep} "; then
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

    # 确保 ClickHouse 正在运行（冷端可能也使用本机 ClickHouse）
    if ! pgrep -x "clickhouse-server" > /dev/null; then
        log_info "启动 ClickHouse..."
        sudo clickhouse start
        sleep 5
    fi

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
    if pgrep -x "clickhouse-server" > /dev/null; then
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
    log_step "健康检查"

    # ClickHouse
    if curl -s "http://localhost:8123/" --data "SELECT 1" | grep -q "1"; then
        log_info "ClickHouse: healthy"
    else
        log_error "ClickHouse: unhealthy"
        return 1
    fi

    # 热端
    if curl -s "http://localhost:$HOT_STORAGE_PORT/health" | grep -q "healthy"; then
        log_info "热端存储: healthy"
    else
        log_warn "热端存储: 健康检查未通过"
    fi

    # 冷端
    if curl -s "http://localhost:$COLD_STORAGE_PORT/health" | grep -q "\"status\": \"healthy\""; then
        log_info "冷端存储: healthy"
    else
        log_warn "冷端存储: 健康检查未通过"
    fi

    # 数据检查（热端示例）
    local count=$(clickhouse-client --query "SELECT count(*) FROM $DB_NAME_HOT.trades" 2>/dev/null || echo "0")
    log_info "热端数据记录数: $count"
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

show_help() {
    cat << EOF
${CYAN}MarketPrism Data Storage Service 管理脚本${NC}

用法: $0 [命令] [hot|cold]

命令:
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

示例:
  $0 install-deps && $0 init && $0 start
  $0 start cold
  $0 logs cold
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
        help|--help|-h) show_help ;;
        *) log_error "未知命令: $cmd"; show_help; exit 1 ;;
    esac
}

main "$@"
