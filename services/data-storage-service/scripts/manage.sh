#\!/bin/bash

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
    if \! command -v clickhouse-server &> /dev/null; then
        log_info "安装 ClickHouse..."
        curl https://clickhouse.com/ | sh
        sudo ./clickhouse install
    else
        log_info "ClickHouse 已安装"
    fi
    
    # 创建虚拟环境
    if [ \! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi
    
    # 安装 Python 依赖
    log_info "安装 Python 依赖..."
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install -q nats-py aiohttp requests clickhouse-driver PyYAML python-dateutil structlog
    
    log_info "依赖安装完成"
}

init_service() {
    log_step "初始化服务"
    mkdir -p "$LOG_DIR"
    
    # 启动 ClickHouse
    if \! pgrep -x "clickhouse-server" > /dev/null; then
        log_info "启动 ClickHouse..."
        sudo clickhouse start
        sleep 5
    fi
    
    # 初始化数据库
    if [ -f "$DB_SCHEMA_FILE" ]; then
        log_info "初始化数据库表..."
        clickhouse-client --multiquery < "$DB_SCHEMA_FILE"
        local table_count=$(clickhouse-client --query "SHOW TABLES FROM $DB_NAME_HOT" | wc -l)
        log_info "创建了 $table_count 个表"
    fi
    
    log_info "初始化完成"
}

start_service() {
    log_step "启动服务"
    
    # 确保 ClickHouse 运行
    if \! pgrep -x "clickhouse-server" > /dev/null; then
        sudo clickhouse start
        sleep 5
    fi
    
    # 启动热端存储
    if [ -f "$PID_FILE_HOT" ] && kill -0 $(cat "$PID_FILE_HOT") 2>/dev/null; then
        log_warn "热端存储服务已在运行"
        return 0
    fi
    
    source "$VENV_DIR/bin/activate"
    cd "$MODULE_ROOT"
    nohup python main.py --mode hot > "$LOG_FILE_HOT" 2>&1 &
    echo $\! > "$PID_FILE_HOT"
    sleep 10
    
    if [ -f "$PID_FILE_HOT" ] && kill -0 $(cat "$PID_FILE_HOT") 2>/dev/null; then
        log_info "热端存储服务启动成功 (PID: $(cat $PID_FILE_HOT))"
    else
        log_error "启动失败"
        exit 1
    fi
}

stop_service() {
    log_step "停止服务"
    
    if [ -f "$PID_FILE_HOT" ]; then
        local pid=$(cat "$PID_FILE_HOT")
        if kill -0 $pid 2>/dev/null; then
            log_info "停止热端存储服务..."
            kill $pid
            sleep 2
            kill -0 $pid 2>/dev/null && kill -9 $pid 2>/dev/null || true
            rm -f "$PID_FILE_HOT"
        fi
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
    
    # 存储服务
    if curl -s "http://localhost:$HOT_STORAGE_PORT/health" | grep -q "healthy"; then
        log_info "热端存储: healthy"
    else
        log_warn "热端存储: 健康检查未通过"
    fi
    
    # 数据检查
    local count=$(clickhouse-client --query "SELECT count(*) FROM $DB_NAME_HOT.trades" 2>/dev/null || echo "0")
    log_info "数据记录数: $count"
}

show_logs() {
    log_step "查看日志"
    [ -f "$LOG_FILE_HOT" ] && tail -f "$LOG_FILE_HOT" || log_warn "日志文件不存在"
}

clean_service() {
    log_step "清理"
    stop_service
    rm -f "$PID_FILE_HOT"
    [ -f "$LOG_FILE_HOT" ] && > "$LOG_FILE_HOT"
    log_info "清理完成"
}

show_help() {
    cat << EOF
${CYAN}MarketPrism Data Storage Service 管理脚本${NC}

用法: $0 [命令]

命令:
  install-deps  安装依赖
  init          初始化服务
  start         启动服务
  stop          停止服务
  restart       重启服务
  status        检查状态
  health        健康检查
  logs          查看日志
  clean         清理
  help          显示帮助

示例:
  $0 install-deps && $0 init && $0 start
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
        clean) clean_service ;;
        help|--help|-h) show_help ;;
        *) log_error "未知命令: $1"; show_help; exit 1 ;;
    esac
}

main "$@"
