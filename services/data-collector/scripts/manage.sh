#!/bin/bash
# MarketPrism 数据采集器统一管理脚本
# 支持数据采集器的启动、停止、重启、健康检查等操作

set -euo pipefail

# ============================================================================
# 配置常量
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

# 服务配置
MODULE_NAME="data-collector"
CONFIG_FILE="$MODULE_ROOT/config/collector/unified_data_collection.yaml"
MAIN_SCRIPT="$MODULE_ROOT/unified_collector_main.py"

# 采集器配置
LOCK_FILE="${MARKETPRISM_COLLECTOR_LOCK:-/tmp/marketprism_collector.lock}"
LOG_FILE="$PROJECT_ROOT/logs/collector.log"
PID_FILE="$PROJECT_ROOT/logs/collector.pid"
HEALTH_PORT="${HEALTH_CHECK_PORT:-8087}"

# NATS配置
NATS_HOST="localhost"
NATS_PORT=4222
NATS_MONITOR_PORT=8222

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
    check_venv || return 1
    
    log_info "所有依赖检查通过"
}

# 检查NATS是否运行
check_nats() {
    if curl -s "http://$NATS_HOST:$NATS_MONITOR_PORT/healthz" > /dev/null 2>&1; then
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
    if [ -f "$LOCK_FILE" ]; then
        local pid=$(cat "$LOCK_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_warn "数据采集器已在运行 (PID: $pid)"
            return 1
        else
            log_warn "发现僵尸锁文件 (PID: $pid 已不存在)，清理中..."
            rm -f "$LOCK_FILE"
        fi
    fi
    return 0
}

# 清理锁文件
clean_lock() {
    if [ -f "$LOCK_FILE" ]; then
        log_step "清理锁文件..."
        rm -f "$LOCK_FILE"
        log_info "锁文件已清理"
    fi
}

# ============================================================================
# 进程管理函数
# ============================================================================

# 获取进程PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

# 检查进程是否运行
is_running() {
    local pid=$(get_pid)
    
    if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 停止进程
stop_process() {
    local pid=$(get_pid)
    
    if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
        log_step "停止数据采集器 (PID: $pid)..."
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
        
        log_info "数据采集器已停止"
    else
        log_warn "数据采集器未运行"
    fi
}

# ============================================================================
# NATS管理函数
# ============================================================================

start_nats() {
    log_step "检查NATS状态..."
    
    if check_nats; then
        log_info "NATS已在运行"
        return 0
    fi
    
    log_step "启动NATS容器..."
    cd "$PROJECT_ROOT/services/message-broker"
    docker-compose up -d
    
    # 等待NATS启动
    log_step "等待NATS启动..."
    local count=0
    while ! check_nats && [ $count -lt 30 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    if check_nats; then
        log_info "NATS启动成功"
    else
        log_error "NATS启动超时"
        return 1
    fi
}

stop_nats() {
    log_step "停止NATS容器..."
    cd "$PROJECT_ROOT/services/message-broker"
    docker-compose stop
    log_info "NATS已停止"
}

# ============================================================================
# 服务启动函数
# ============================================================================

start() {
    log_step "启动数据采集器..."
    
    # 检查锁文件
    if ! check_lock; then
        return 1
    fi
    
    # 确保NATS运行
    start_nats || return 1
    
    # 激活虚拟环境
    activate_venv
    
    # 设置环境变量
    export COLLECTOR_ENABLE_HTTP=1
    export HEALTH_CHECK_PORT=$HEALTH_PORT
    
    # 启动服务
    cd "$MODULE_ROOT"
    nohup python unified_collector_main.py --config "$CONFIG_FILE" \
        > "$LOG_FILE" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$PID_FILE"
    
    # 等待服务启动
    log_step "等待数据采集器启动..."
    sleep 15
    
    # 健康检查
    if curl -s "http://localhost:$HEALTH_PORT/health" > /dev/null 2>&1; then
        log_info "数据采集器启动成功 (PID: $pid, Port: $HEALTH_PORT)"
    else
        log_error "数据采集器启动失败，请检查日志: $LOG_FILE"
        return 1
    fi
}

# ============================================================================
# 服务停止函数
# ============================================================================

stop() {
    stop_process
    clean_lock
    rm -f "$PID_FILE"
}

# ============================================================================
# 状态检查函数
# ============================================================================

status() {
    echo "=== MarketPrism 数据采集器状态 ==="
    
    # NATS状态
    echo ""
    echo "=== NATS 状态 ==="
    if check_nats; then
        log_info "NATS: 运行中"
    else
        log_warn "NATS: 未运行"
    fi
    
    # 采集器状态
    echo ""
    echo "=== 数据采集器状态 ==="
    
    # 检查进程
    if is_running; then
        local pid=$(get_pid)
        log_info "进程状态: 运行中 (PID: $pid)"
    else
        log_warn "进程状态: 未运行"
    fi
    
    # 检查端口
    if ss -ltn | grep -q ":$HEALTH_PORT "; then
        log_info "端口状态: $HEALTH_PORT 正在监听"
    else
        log_warn "端口状态: $HEALTH_PORT 未监听"
    fi
    
    # 检查锁文件
    if [ -f "$LOCK_FILE" ]; then
        local lock_pid=$(cat "$LOCK_FILE")
        log_info "锁文件: 存在 (PID: $lock_pid)"
    else
        log_warn "锁文件: 不存在"
    fi
    
    # 健康检查
    if curl -s "http://localhost:$HEALTH_PORT/health" > /dev/null 2>&1; then
        local health_status=$(curl -s "http://localhost:$HEALTH_PORT/health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        log_info "健康状态: $health_status"
    else
        log_warn "健康状态: 无响应"
    fi
    
    echo ""
}

# ============================================================================
# 健康检查函数
# ============================================================================

health_check() {
    local exit_code=0

    echo "=== MarketPrism 数据采集器健康检查 ==="

    # NATS健康检查
    echo ""
    log_step "检查NATS..."
    if check_nats; then
        log_info "NATS: healthy"
    else
        log_error "NATS: unhealthy"
        exit_code=1
    fi

    # 采集器健康检查
    echo ""
    log_step "检查数据采集器..."
    if curl -s "http://localhost:$HEALTH_PORT/health" > /dev/null 2>&1; then
        local status=$(curl -s "http://localhost:$HEALTH_PORT/health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$status" == "healthy" ]; then
            log_info "数据采集器: healthy"
        else
            log_error "数据采集器: $status"
            exit_code=1
        fi
    else
        log_error "数据采集器: 无响应"
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
    echo "=== MarketPrism 数据采集器初始化 ==="

    # 检查依赖
    check_dependencies || return 1

    # 创建必要目录
    log_step "创建必要目录..."
    mkdir -p "$PROJECT_ROOT/logs"
    log_info "目录创建完成"

    # 启动NATS
    start_nats || return 1

    log_info "数据采集器初始化完成"
}

# ============================================================================
# 主函数
# ============================================================================

show_usage() {
    cat << EOF
MarketPrism 数据采集器管理脚本

用法: $0 <command> [options]

命令:
    init        初始化服务（创建目录、启动NATS）
    start       启动数据采集器
    stop        停止数据采集器
    restart     重启数据采集器
    status      查看服务状态
    health      执行健康检查
    clean       清理锁文件和PID文件

选项:
    --force     强制执行（清理僵尸锁）
    --verbose   显示详细输出

示例:
    $0 init         # 初始化服务
    $0 start        # 启动采集器
    $0 stop         # 停止采集器
    $0 restart      # 重启采集器
    $0 status       # 查看状态
    $0 health       # 健康检查
    $0 clean        # 清理锁文件

EOF
}

main() {
    local command="${1:-}"

    case "$command" in
        init)
            init
            ;;
        start)
            start
            ;;
        stop)
            stop
            ;;
        restart)
            stop && start
            ;;
        status)
            status
            ;;
        health)
            health_check
            ;;
        clean)
            clean_lock
            rm -f "$PID_FILE"
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"

