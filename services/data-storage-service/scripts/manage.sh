#!/bin/bash
# MarketPrism 数据存储服务统一管理脚本
# 支持热端存储和冷端存储的启动、停止、重启、健康检查等操作

set -euo pipefail

# ============================================================================
# 配置常量
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

# 服务配置
MODULE_NAME="data-storage-service"
CONFIG_FILE="$MODULE_ROOT/config/tiered_storage_config.yaml"
MAIN_SCRIPT="$MODULE_ROOT/main.py"

# 热端存储配置
HOT_LOCK_FILE="${MARKETPRISM_HOT_STORAGE_LOCK:-/tmp/marketprism_hot_storage.lock}"
HOT_LOG_FILE="$PROJECT_ROOT/logs/hot_storage.log"
HOT_PID_FILE="$PROJECT_ROOT/logs/hot_storage.pid"
HOT_HEALTH_PORT=8085

# 冷端存储配置
COLD_LOCK_FILE="${MARKETPRISM_COLD_STORAGE_LOCK:-/tmp/marketprism_cold_storage.lock}"
COLD_LOG_FILE="$PROJECT_ROOT/logs/cold_storage.log"
COLD_PID_FILE="$PROJECT_ROOT/logs/cold_storage.pid"
COLD_HEALTH_PORT=8086

# ClickHouse配置
CLICKHOUSE_HOST="localhost"
CLICKHOUSE_HTTP_PORT=8123
CLICKHOUSE_CONTAINER_NAME="marketprism-clickhouse"

# 颜色和符号
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# 检查命令是否存在
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "命令 '$1' 未找到，请先安装"
        return 1
    fi
}

# 检查虚拟环境
check_venv() {
    if [ ! -d "$PROJECT_ROOT/venv" ]; then
        log_error "虚拟环境不存在，请先运行: python -m venv venv"
        return 1
    fi
}

# 激活虚拟环境
activate_venv() {
    source "$PROJECT_ROOT/venv/bin/activate"
}

# ============================================================================
# 依赖检查函数
# ============================================================================

check_dependencies() {
    log_step "检查依赖..."
    
    check_command python3 || return 1
    check_command curl || return 1
    check_command docker || return 1
    check_venv || return 1
    
    log_info "所有依赖检查通过"
}

# 检查ClickHouse是否运行
check_clickhouse() {
    if curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT/ping" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# ============================================================================
# 锁文件管理函数
# ============================================================================

# 检查锁文件
check_lock() {
    local lock_file=$1
    local service_name=$2
    
    if [ -f "$lock_file" ]; then
        local pid=$(cat "$lock_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_warn "$service_name 已在运行 (PID: $pid)"
            return 1
        else
            log_warn "发现僵尸锁文件 (PID: $pid 已不存在)，清理中..."
            rm -f "$lock_file"
        fi
    fi
    return 0
}

# 清理锁文件
clean_lock() {
    local lock_file=$1
    local service_name=$2
    
    if [ -f "$lock_file" ]; then
        log_step "清理 $service_name 锁文件..."
        rm -f "$lock_file"
        log_info "锁文件已清理"
    fi
}

# 强制清理所有锁文件
force_clean_locks() {
    log_step "强制清理所有锁文件..."
    rm -f "$HOT_LOCK_FILE" "$COLD_LOCK_FILE"
    log_info "所有锁文件已清理"
}

# ============================================================================
# 进程管理函数
# ============================================================================

# 获取进程PID
get_pid() {
    local mode=$1
    local pid_file=""
    
    if [ "$mode" == "hot" ]; then
        pid_file="$HOT_PID_FILE"
    else
        pid_file="$COLD_PID_FILE"
    fi
    
    if [ -f "$pid_file" ]; then
        cat "$pid_file"
    else
        echo ""
    fi
}

# 检查进程是否运行
is_running() {
    local mode=$1
    local pid=$(get_pid "$mode")
    
    if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 停止进程
stop_process() {
    local mode=$1
    local service_name=$2
    local pid=$(get_pid "$mode")
    
    if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
        log_step "停止 $service_name (PID: $pid)..."
        kill -TERM "$pid" 2>/dev/null || true
        
        # 等待进程优雅退出
        local count=0
        while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 30 ]; do
            sleep 1
            count=$((count + 1))
        done
        
        # 如果还在运行，强制杀死
        if ps -p "$pid" > /dev/null 2>&1; then
            log_warn "进程未响应，强制终止..."
            kill -9 "$pid" 2>/dev/null || true
        fi
        
        log_info "$service_name 已停止"
    else
        log_warn "$service_name 未运行"
    fi
}

# ============================================================================
# ClickHouse管理函数
# ============================================================================

start_clickhouse() {
    log_step "检查ClickHouse状态..."
    
    if check_clickhouse; then
        log_info "ClickHouse已在运行"
        return 0
    fi
    
    log_step "启动ClickHouse容器..."
    cd "$PROJECT_ROOT/services/data-storage-service"
    docker-compose -f docker-compose.tiered-storage.yml up -d clickhouse
    
    # 等待ClickHouse启动
    log_step "等待ClickHouse启动..."
    local count=0
    while ! check_clickhouse && [ $count -lt 30 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    if check_clickhouse; then
        log_info "ClickHouse启动成功"
    else
        log_error "ClickHouse启动超时"
        return 1
    fi
}

stop_clickhouse() {
    log_step "停止ClickHouse容器..."
    cd "$PROJECT_ROOT/services/data-storage-service"
    docker-compose -f docker-compose.tiered-storage.yml stop clickhouse
    log_info "ClickHouse已停止"
}

# ============================================================================
# 数据库初始化函数
# ============================================================================

init_database() {
    log_step "初始化数据库schema..."
    
    # 确保ClickHouse运行
    if ! check_clickhouse; then
        log_error "ClickHouse未运行，请先启动"
        return 1
    fi
    
    # 创建热端数据库和表
    log_step "创建热端数据库和表..."
    if [ -f "$MODULE_ROOT/config/create_hot_tables.sql" ]; then
        curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT/" \
            --data-binary @"$MODULE_ROOT/config/create_hot_tables.sql" > /dev/null
        log_info "热端数据库初始化完成"
    fi
    
    # 创建冷端数据库和表
    log_step "创建冷端数据库和表..."
    if [ -f "$MODULE_ROOT/config/clickhouse_schema_cold.sql" ]; then
        curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT/" \
            --data-binary @"$MODULE_ROOT/config/clickhouse_schema_cold.sql" > /dev/null
        log_info "冷端数据库初始化完成"
    fi
}

# ============================================================================
# 服务启动函数
# ============================================================================

start_hot() {
    log_step "启动热端存储服务..."
    
    # 检查锁文件
    if ! check_lock "$HOT_LOCK_FILE" "热端存储服务"; then
        return 1
    fi
    
    # 确保ClickHouse运行
    start_clickhouse || return 1
    
    # 激活虚拟环境
    activate_venv
    
    # 启动服务
    cd "$MODULE_ROOT"
    nohup python main.py --mode hot --config "$CONFIG_FILE" \
        > "$HOT_LOG_FILE" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$HOT_PID_FILE"
    
    # 等待服务启动
    log_step "等待热端存储服务启动..."
    sleep 10
    
    # 健康检查
    if curl -s "http://localhost:$HOT_HEALTH_PORT/health" > /dev/null 2>&1; then
        log_info "热端存储服务启动成功 (PID: $pid, Port: $HOT_HEALTH_PORT)"
    else
        log_error "热端存储服务启动失败，请检查日志: $HOT_LOG_FILE"
        return 1
    fi
}

start_cold() {
    log_step "启动冷端存储服务..."

    # 检查锁文件
    if ! check_lock "$COLD_LOCK_FILE" "冷端存储服务"; then
        return 1
    fi

    # 确保ClickHouse运行
    start_clickhouse || return 1

    # 激活虚拟环境
    activate_venv

    # 启动服务
    cd "$MODULE_ROOT"
    nohup python main.py --mode cold --config "$CONFIG_FILE" \
        > "$COLD_LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$COLD_PID_FILE"

    # 等待服务启动
    log_step "等待冷端存储服务启动..."
    sleep 10

    # 健康检查
    if curl -s "http://localhost:$COLD_HEALTH_PORT/health" > /dev/null 2>&1; then
        log_info "冷端存储服务启动成功 (PID: $pid, Port: $COLD_HEALTH_PORT)"
    else
        log_error "冷端存储服务启动失败，请检查日志: $COLD_LOG_FILE"
        return 1
    fi
}

# ============================================================================
# 服务停止函数
# ============================================================================

stop_hot() {
    stop_process "hot" "热端存储服务"
    clean_lock "$HOT_LOCK_FILE" "热端存储服务"
    rm -f "$HOT_PID_FILE"
}

stop_cold() {
    stop_process "cold" "冷端存储服务"
    clean_lock "$COLD_LOCK_FILE" "冷端存储服务"
    rm -f "$COLD_PID_FILE"
}

# ============================================================================
# 状态检查函数
# ============================================================================

status_service() {
    local mode=$1
    local service_name=$2
    local health_port=$3
    local lock_file=$4

    echo ""
    echo "=== $service_name 状态 ==="

    # 检查进程
    if is_running "$mode"; then
        local pid=$(get_pid "$mode")
        log_info "进程状态: 运行中 (PID: $pid)"
    else
        log_warn "进程状态: 未运行"
    fi

    # 检查端口
    if ss -ltn | grep -q ":$health_port "; then
        log_info "端口状态: $health_port 正在监听"
    else
        log_warn "端口状态: $health_port 未监听"
    fi

    # 检查锁文件
    if [ -f "$lock_file" ]; then
        local lock_pid=$(cat "$lock_file")
        log_info "锁文件: 存在 (PID: $lock_pid)"
    else
        log_warn "锁文件: 不存在"
    fi

    # 健康检查
    if curl -s "http://localhost:$health_port/health" > /dev/null 2>&1; then
        local health_status=$(curl -s "http://localhost:$health_port/health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        log_info "健康状态: $health_status"
    else
        log_warn "健康状态: 无响应"
    fi
}

status() {
    echo "=== MarketPrism 数据存储服务状态 ==="

    # ClickHouse状态
    echo ""
    echo "=== ClickHouse 状态 ==="
    if check_clickhouse; then
        log_info "ClickHouse: 运行中"
    else
        log_warn "ClickHouse: 未运行"
    fi

    # 热端存储状态
    status_service "hot" "热端存储服务" "$HOT_HEALTH_PORT" "$HOT_LOCK_FILE"

    # 冷端存储状态
    status_service "cold" "冷端存储服务" "$COLD_HEALTH_PORT" "$COLD_LOCK_FILE"

    echo ""
}

# ============================================================================
# 健康检查函数
# ============================================================================

health_check() {
    local exit_code=0

    echo "=== MarketPrism 数据存储服务健康检查 ==="

    # ClickHouse健康检查
    echo ""
    log_step "检查ClickHouse..."
    if check_clickhouse; then
        log_info "ClickHouse: healthy"
    else
        log_error "ClickHouse: unhealthy"
        exit_code=1
    fi

    # 热端存储健康检查
    echo ""
    log_step "检查热端存储服务..."
    if curl -s "http://localhost:$HOT_HEALTH_PORT/health" > /dev/null 2>&1; then
        local status=$(curl -s "http://localhost:$HOT_HEALTH_PORT/health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$status" == "healthy" ]; then
            log_info "热端存储服务: healthy"
        else
            log_error "热端存储服务: $status"
            exit_code=1
        fi
    else
        log_error "热端存储服务: 无响应"
        exit_code=1
    fi

    # 冷端存储健康检查
    echo ""
    log_step "检查冷端存储服务..."
    if curl -s "http://localhost:$COLD_HEALTH_PORT/health" > /dev/null 2>&1; then
        local status=$(curl -s "http://localhost:$COLD_HEALTH_PORT/health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$status" == "healthy" ]; then
            log_info "冷端存储服务: healthy"
        else
            log_error "冷端存储服务: $status"
            exit_code=1
        fi
    else
        log_error "冷端存储服务: 无响应"
        exit_code=1
    fi

    echo ""
    if [ $exit_code -eq 0 ]; then
        log_info "所有服务健康检查通过"
    else
        log_error "部分服务健康检查失败"
    fi

    return $exit_code
}

# ============================================================================
# 初始化函数
# ============================================================================

init() {
    echo "=== MarketPrism 数据存储服务初始化 ==="

    # 检查依赖
    check_dependencies || return 1

    # 创建必要目录
    log_step "创建必要目录..."
    mkdir -p "$PROJECT_ROOT/logs"
    log_info "目录创建完成"

    # 启动ClickHouse
    start_clickhouse || return 1

    # 初始化数据库
    init_database || return 1

    log_info "数据存储服务初始化完成"
}

# ============================================================================
# 主函数
# ============================================================================

show_usage() {
    cat << EOF
MarketPrism 数据存储服务管理脚本

用法: $0 <command> [options]

命令:
    init                初始化服务（创建目录、初始化数据库）
    start [hot|cold]    启动服务（不指定则启动全部）
    stop [hot|cold]     停止服务（不指定则停止全部）
    restart [hot|cold]  重启服务（不指定则重启全部）
    status              查看服务状态
    health              执行健康检查
    clean               清理锁文件和PID文件

选项:
    --force             强制执行（清理僵尸锁）
    --verbose           显示详细输出

示例:
    $0 init                 # 初始化服务
    $0 start hot            # 启动热端存储
    $0 stop cold            # 停止冷端存储
    $0 restart              # 重启所有服务
    $0 status               # 查看状态
    $0 health               # 健康检查
    $0 clean --force        # 强制清理锁文件

EOF
}

main() {
    local command="${1:-}"
    local target="${2:-all}"

    case "$command" in
        init)
            init
            ;;
        start)
            if [ "$target" == "hot" ]; then
                start_hot
            elif [ "$target" == "cold" ]; then
                start_cold
            else
                start_hot && start_cold
            fi
            ;;
        stop)
            if [ "$target" == "hot" ]; then
                stop_hot
            elif [ "$target" == "cold" ]; then
                stop_cold
            else
                stop_cold && stop_hot
            fi
            ;;
        restart)
            if [ "$target" == "hot" ]; then
                stop_hot && start_hot
            elif [ "$target" == "cold" ]; then
                stop_cold && start_cold
            else
                stop_cold && stop_hot && start_hot && start_cold
            fi
            ;;
        status)
            status
            ;;
        health)
            health_check
            ;;
        clean)
            if [ "$target" == "--force" ] || [ "${2:-}" == "--force" ]; then
                force_clean_locks
            else
                clean_lock "$HOT_LOCK_FILE" "热端存储服务"
                clean_lock "$COLD_LOCK_FILE" "冷端存储服务"
            fi
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"

