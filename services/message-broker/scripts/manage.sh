#!/bin/bash
# MarketPrism NATS消息代理统一管理脚本
# 支持NATS JetStream的启动、停止、重启、健康检查等操作

set -euo pipefail

# ============================================================================
# 配置常量
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

# 服务配置
MODULE_NAME="message-broker"
DOCKER_COMPOSE_FILE="$MODULE_ROOT/docker-compose.nats.yml"

# NATS配置
NATS_HOST="localhost"
NATS_CLIENT_PORT=4222
NATS_MONITOR_PORT=8222
NATS_CONTAINER_NAME="marketprism-nats"

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

# ============================================================================
# 依赖检查函数
# ============================================================================

check_dependencies() {
    log_step "检查依赖..."
    
    check_command docker || return 1
    check_command docker-compose || return 1
    check_command curl || return 1
    
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

# 检查容器是否运行
check_container() {
    if docker ps --format '{{.Names}}' | grep -q "^${NATS_CONTAINER_NAME}$"; then
        return 0
    else
        return 1
    fi
}

# ============================================================================
# 服务启动函数
# ============================================================================

start() {
    log_step "启动NATS JetStream..."
    
    # 检查是否已运行
    if check_container; then
        log_warn "NATS容器已在运行"
        if check_nats; then
            log_info "NATS服务正常"
            return 0
        fi
    fi
    
    # 启动容器
    cd "$MODULE_ROOT"
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d
    
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

# ============================================================================
# 服务停止函数
# ============================================================================

stop() {
    log_step "停止NATS JetStream..."
    
    if ! check_container; then
        log_warn "NATS容器未运行"
        return 0
    fi
    
    cd "$MODULE_ROOT"
    docker-compose stop
    
    log_info "NATS已停止"
}

# 完全清理（停止并删除容器）
clean() {
    log_step "清理NATS容器和数据..."

    cd "$MODULE_ROOT"
    docker-compose -f "$DOCKER_COMPOSE_FILE" down -v

    log_info "NATS容器和数据已清理"
}

# ============================================================================
# 状态检查函数
# ============================================================================

status() {
    echo "=== MarketPrism NATS消息代理状态 ==="
    
    echo ""
    echo "=== 容器状态 ==="
    if check_container; then
        log_info "容器状态: 运行中"
        
        # 显示容器详情
        docker ps --filter "name=$NATS_CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    else
        log_warn "容器状态: 未运行"
    fi
    
    echo ""
    echo "=== 服务状态 ==="
    
    # 检查客户端端口
    if ss -ltn | grep -q ":$NATS_CLIENT_PORT "; then
        log_info "客户端端口: $NATS_CLIENT_PORT 正在监听"
    else
        log_warn "客户端端口: $NATS_CLIENT_PORT 未监听"
    fi
    
    # 检查监控端口
    if ss -ltn | grep -q ":$NATS_MONITOR_PORT "; then
        log_info "监控端口: $NATS_MONITOR_PORT 正在监听"
    else
        log_warn "监控端口: $NATS_MONITOR_PORT 未监听"
    fi
    
    # 健康检查
    if check_nats; then
        log_info "健康状态: healthy"
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
    
    echo "=== MarketPrism NATS消息代理健康检查 ==="
    
    echo ""
    log_step "检查NATS容器..."
    if check_container; then
        log_info "NATS容器: 运行中"
    else
        log_error "NATS容器: 未运行"
        exit_code=1
    fi
    
    echo ""
    log_step "检查NATS服务..."
    if check_nats; then
        local health_response=$(curl -s "http://$NATS_HOST:$NATS_MONITOR_PORT/healthz")
        log_info "NATS服务: $health_response"
    else
        log_error "NATS服务: 无响应"
        exit_code=1
    fi
    
    echo ""
    log_step "检查JetStream状态..."
    if curl -s "http://$NATS_HOST:$NATS_MONITOR_PORT/jsz" > /dev/null 2>&1; then
        log_info "JetStream: 正常"
    else
        log_error "JetStream: 异常"
        exit_code=1
    fi
    
    echo ""
    if [ $exit_code -eq 0 ]; then
        log_info "所有健康检查通过"
    else
        log_error "部分健康检查失败"
    fi
    
    return $exit_code
}

# ============================================================================
# 日志查看函数
# ============================================================================

logs() {
    local follow="${1:-}"

    cd "$MODULE_ROOT"

    if [ "$follow" == "-f" ] || [ "$follow" == "--follow" ]; then
        docker-compose -f "$DOCKER_COMPOSE_FILE" logs -f
    else
        docker-compose -f "$DOCKER_COMPOSE_FILE" logs --tail=100
    fi
}

# ============================================================================
# 初始化函数
# ============================================================================

init() {
    echo "=== MarketPrism NATS消息代理初始化 ==="
    
    # 检查依赖
    check_dependencies || return 1
    
    # 启动NATS
    start || return 1
    
    log_info "NATS消息代理初始化完成"
}

# ============================================================================
# 主函数
# ============================================================================

show_usage() {
    cat << EOF
MarketPrism NATS消息代理管理脚本

用法: $0 <command> [options]

命令:
    init        初始化服务（启动NATS）
    start       启动NATS容器
    stop        停止NATS容器
    restart     重启NATS容器
    status      查看服务状态
    health      执行健康检查
    logs        查看日志（-f 持续跟踪）
    clean       清理容器和数据

选项:
    -f, --follow    持续跟踪日志（用于logs命令）

示例:
    $0 init         # 初始化服务
    $0 start        # 启动NATS
    $0 stop         # 停止NATS
    $0 restart      # 重启NATS
    $0 status       # 查看状态
    $0 health       # 健康检查
    $0 logs         # 查看日志
    $0 logs -f      # 持续跟踪日志
    $0 clean        # 清理容器和数据

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
        logs)
            logs "${2:-}"
            ;;
        clean)
            clean
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
