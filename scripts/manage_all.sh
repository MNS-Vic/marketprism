#!/bin/bash
# MarketPrism 系统统一管理脚本
# 用于统一管理所有模块（NATS、数据存储、数据采集器）

set -euo pipefail

# ============================================================================
# 配置常量
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 模块脚本路径
NATS_SCRIPT="$PROJECT_ROOT/services/message-broker/scripts/manage.sh"
STORAGE_SCRIPT="$PROJECT_ROOT/services/data-storage-service/scripts/manage.sh"
COLLECTOR_SCRIPT="$PROJECT_ROOT/services/data-collector/scripts/manage.sh"

# 颜色和符号
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

log_section() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 🔧 新增：等待服务启动的函数
wait_for_service() {
    local service_name="$1"
    local endpoint="$2"
    local timeout="$3"
    local count=0

    log_info "等待 $service_name 启动..."

    while [ $count -lt $timeout ]; do
        if curl -s "$endpoint" >/dev/null 2>&1; then
            log_info "$service_name 启动成功"
            return 0
        fi

        if [ $((count % 5)) -eq 0 ]; then
            log_info "等待 $service_name 启动... ($count/$timeout 秒)"
        fi

        sleep 1
        ((count++))
    done

    log_warn "$service_name 启动超时，但继续执行..."
    return 1
}

# 🔧 新增：端到端数据流验证函数
validate_end_to_end_data_flow() {
    log_info "验证端到端数据流..."

    # 检查NATS JetStream流状态
    local nats_streams=$(curl -s http://localhost:8222/jsz 2>/dev/null | grep -o '"messages":[0-9]*' | wc -l || echo "0")
    if [ "$nats_streams" -gt 0 ]; then
        log_info "NATS JetStream: 流正常 ($nats_streams 个流)"
    else
        log_warn "NATS JetStream: 流状态异常"
    fi

    # 检查ClickHouse数据
    if command -v clickhouse-client &> /dev/null; then
        local trades_count=$(clickhouse-client --query "SELECT COUNT(*) FROM marketprism_hot.trades" 2>/dev/null || echo "0")
        local orderbooks_count=$(clickhouse-client --query "SELECT COUNT(*) FROM marketprism_hot.orderbooks" 2>/dev/null || echo "0")

        log_info "ClickHouse数据统计:"
        log_info "  - Trades: $trades_count 条"
        log_info "  - Orderbooks: $orderbooks_count 条"

        if [ "$trades_count" -gt 0 ] || [ "$orderbooks_count" -gt 0 ]; then
            log_info "端到端数据流: 正常 ✅"
        else
            log_warn "端到端数据流: 暂无数据，可能仍在初始化"
        fi
    else
        log_warn "ClickHouse客户端未安装，跳过数据验证"
    fi
}

# ============================================================================
# 初始化函数
# ============================================================================

init_all() {
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
    log_step "1. 初始化NATS消息代理..."
    bash "$NATS_SCRIPT" init || { log_error "NATS初始化失败"; return 1; }

    echo ""
    log_step "2. 初始化数据存储服务..."
    bash "$STORAGE_SCRIPT" init || { log_error "数据存储服务初始化失败"; return 1; }

    echo ""
    log_step "3. 初始化数据采集器..."
    bash "$COLLECTOR_SCRIPT" init || { log_error "数据采集器初始化失败"; return 1; }

    echo ""
    log_info "MarketPrism 系统初始化完成"
}

# ============================================================================
# 启动函数
# ============================================================================

start_all() {
    log_section "MarketPrism 系统启动"

    echo ""
    log_step "1. 启动NATS消息代理..."
    bash "$NATS_SCRIPT" start || { log_error "NATS启动失败"; return 1; }

    # 🔧 等待NATS完全启动
    echo ""
    log_step "等待NATS完全启动..."
    wait_for_service "NATS" "http://localhost:8222/healthz" 30

    echo ""
    log_step "2. 启动热端存储服务..."
    bash "$STORAGE_SCRIPT" start hot || { log_error "热端存储启动失败"; return 1; }

    # 🔧 等待热端存储完全启动
    echo ""
    log_step "等待热端存储完全启动..."
    wait_for_service "热端存储" "http://localhost:8085/health" 30

    echo ""
    log_step "3. 启动数据采集器..."
    bash "$COLLECTOR_SCRIPT" start || { log_error "数据采集器启动失败"; return 1; }

    # 🔧 等待数据采集器完全启动（允许超时，因为健康检查端点可能未实现）
    echo ""
    log_step "等待数据采集器完全启动..."
    wait_for_service "数据采集器" "http://localhost:8087/health" 15 || log_warn "数据采集器健康检查超时，但继续启动冷端存储"

    echo ""
    log_step "4. 启动冷端存储服务..."
    bash "$STORAGE_SCRIPT" start cold || { log_error "冷端存储启动失败"; return 1; }

    # 🔧 等待冷端存储完全启动
    echo ""
    log_step "等待冷端存储完全启动..."
    wait_for_service "冷端存储" "http://localhost:8086/health" 30

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
    log_step "1. 停止数据采集器..."
    bash "$COLLECTOR_SCRIPT" stop || log_warn "数据采集器停止失败"
    
    echo ""
    log_step "2. 停止冷端存储服务..."
    bash "$STORAGE_SCRIPT" stop cold || log_warn "冷端存储停止失败"
    
    echo ""
    log_step "3. 停止热端存储服务..."
    bash "$STORAGE_SCRIPT" stop hot || log_warn "热端存储停止失败"
    
    echo ""
    log_step "4. 停止NATS消息代理..."
    bash "$NATS_SCRIPT" stop || log_warn "NATS停止失败"
    
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
    log_step "NATS消息代理状态:"
    bash "$NATS_SCRIPT" status
    
    echo ""
    log_step "数据存储服务状态:"
    bash "$STORAGE_SCRIPT" status
    
    echo ""
    log_step "数据采集器状态:"
    bash "$COLLECTOR_SCRIPT" status
}

# ============================================================================
# 健康检查函数
# ============================================================================

health_all() {
    log_section "MarketPrism 系统健康检查"

    local exit_code=0

    echo ""
    log_step "检查NATS消息代理..."
    if ! bash "$NATS_SCRIPT" health; then
        exit_code=1
    fi

    echo ""
    log_step "检查数据存储服务..."
    if ! bash "$STORAGE_SCRIPT" health; then
        exit_code=1
    fi

    echo ""
    log_step "检查数据采集器..."
    if ! bash "$COLLECTOR_SCRIPT" health; then
        exit_code=1
    fi

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
    log_step "清理数据采集器..."
    bash "$COLLECTOR_SCRIPT" clean
    
    echo ""
    log_step "清理数据存储服务..."
    bash "$STORAGE_SCRIPT" clean --force
    
    echo ""
    log_info "系统清理完成"
}

# ============================================================================
# 快速诊断函数
# ============================================================================

diagnose() {
    log_section "MarketPrism 系统快速诊断"
    
    echo ""
    log_step "1. 检查端口占用..."
    echo "关键端口监听状态:"
    ss -ltnp | grep -E ':(4222|8222|8123|8085|8086|8087)' || echo "  无相关端口监听"
    
    echo ""
    log_step "2. 检查进程状态..."
    echo "MarketPrism进程:"
    ps aux | grep -E '(nats-server|main.py|unified_collector_main.py)' | grep -v grep || echo "  无相关进程"
    
    echo ""
    log_step "3. 检查锁文件..."
    echo "实例锁文件:"
    ls -l /tmp/marketprism_*.lock 2>/dev/null || echo "  无锁文件"
    
    echo ""
    log_step "4. 检查Docker容器..."
    echo "MarketPrism容器:"
    docker ps --filter "name=marketprism" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" || echo "  无相关容器"
    
    echo ""
    log_step "5. 执行健康检查..."
    health_all
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

命令:
    init        初始化整个系统（首次部署使用）
    start       启动所有服务（按正确顺序）
    stop        停止所有服务（按正确顺序）
    restart     重启所有服务
    status      查看所有服务状态
    health      执行完整健康检查
    diagnose    快速诊断系统问题
    clean       清理锁文件和临时数据

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
    $0 health       # 健康检查
    $0 diagnose     # 快速诊断
    $0 clean        # 清理系统

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
        health)
            health_all
            ;;
        diagnose)
            diagnose
            ;;
        clean)
            clean_all
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
