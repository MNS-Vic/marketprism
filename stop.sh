#!/bin/bash

# MarketPrism订单簿管理系统停止脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 停止服务
stop_services() {
    log_info "停止MarketPrism订单簿管理系统..."
    
    # 优雅停止应用服务
    log_info "停止订单簿管理系统..."
    docker-compose stop orderbook-manager || true
    
    # 停止监控服务
    log_info "停止监控服务..."
    docker-compose stop grafana prometheus || true
    
    # 停止基础服务
    log_info "停止基础服务..."
    docker-compose stop nats clickhouse redis || true
    
    # 完全停止所有服务
    log_info "完全停止所有服务..."
    docker-compose down --remove-orphans
    
    log_info "所有服务已停止"
}

# 清理资源
cleanup_resources() {
    local cleanup_type=${1:-basic}
    
    if [ "$cleanup_type" = "full" ]; then
        log_warn "执行完全清理（包括数据卷）..."
        docker-compose down -v --remove-orphans
        docker system prune -f
        log_warn "完全清理完成"
    else
        log_info "执行基础清理..."
        docker-compose down --remove-orphans
        log_info "基础清理完成"
    fi
}

# 显示帮助信息
show_help() {
    echo "🛑 MarketPrism订单簿管理系统停止脚本"
    echo "========================================"
    echo ""
    echo "用法:"
    echo "  ./stop.sh [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示此帮助信息"
    echo "  -f, --full     完全清理（包括数据卷和镜像）"
    echo "  -q, --quick    快速停止（跳过优雅停止）"
    echo ""
    echo "停止模式:"
    echo "  正常停止:"
    echo "    • 优雅停止订单簿管理器"
    echo "    • 停止监控服务 (Grafana, Prometheus)"
    echo "    • 停止基础服务 (NATS, ClickHouse, Redis)"
    echo "    • 移除容器但保留数据卷"
    echo ""
    echo "  完全清理 (--full):"
    echo "    • 执行正常停止流程"
    echo "    • 删除所有数据卷"
    echo "    • 清理Docker镜像"
    echo "    • ⚠️  警告：将丢失所有数据"
    echo ""
    echo "  快速停止 (--quick):"
    echo "    • 立即停止所有容器"
    echo "    • 跳过优雅停止流程"
    echo "    • 适用于紧急情况"
    echo ""
    echo "示例:"
    echo "  ./stop.sh              # 正常停止，保留数据"
    echo "  ./stop.sh --full       # 停止并清理所有数据"
    echo "  ./stop.sh --quick      # 紧急快速停止"
    echo ""
    echo "注意事项:"
    echo "  • 正常停止会保留所有数据和配置"
    echo "  • 完全清理会删除所有数据，请谨慎使用"
    echo "  • 停止后可以使用 ./start.sh 重新启动"
    echo ""
}

# 主函数
main() {
    local cleanup_type="basic"
    local quick_mode=false
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -f|--full)
                cleanup_type="full"
                shift
                ;;
            -q|--quick)
                quick_mode=true
                shift
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    echo "🛑 MarketPrism订单簿管理系统停止脚本"
    echo "========================================"
    
    if [ "$quick_mode" = true ]; then
        log_info "快速停止模式"
        docker-compose down
    else
        stop_services
        cleanup_resources "$cleanup_type"
    fi
    
    log_info "MarketPrism订单簿管理系统已停止"
    
    if [ "$cleanup_type" = "full" ]; then
        log_warn "注意：所有数据已被清理"
    fi
}

# 执行主函数
main "$@"
