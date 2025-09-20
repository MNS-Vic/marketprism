#!/bin/bash
# MarketPrism 停止脚本 - 完全固化版本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 停止所有服务
stop_services() {
    log_info "停止 MarketPrism 所有服务..."
    
    # 按相反顺序停止服务
    log_info "停止热存储服务..."
    docker compose -f services/data-storage-service/docker-compose.hot-storage.yml down || true
    
    log_info "停止数据收集器..."
    docker compose -f services/data-collector/docker-compose.unified.yml down || true
    
    log_info "停止 NATS..."
    docker compose -f services/message-broker/docker-compose.nats.yml down || true
    
    log_success "所有服务已停止"
}

# 清理资源（可选）
cleanup_resources() {
    if [ "$1" = "--cleanup" ]; then
        log_info "清理所有相关资源..."
        
        # 强制删除所有 marketprism 容器
        for container in $(docker ps -aq --filter name=marketprism- 2>/dev/null || true); do
            docker rm -f $container || true
        done
        
        # 清理网络
        for network in marketprism-storage-network message-broker_default; do
            docker network rm $network 2>/dev/null || true
        done
        
        # 清理未使用的镜像（可选）
        if [ "$2" = "--prune" ]; then
            log_info "清理未使用的 Docker 镜像..."
            docker image prune -f || true
        fi
        
        log_success "资源清理完成"
    fi
}

# 显示状态
show_status() {
    echo ""
    log_info "当前容器状态:"
    docker ps --format 'table {{.Names}}\t{{.Status}}' | grep marketprism || log_info "没有运行中的 MarketPrism 容器"
    echo ""
}

# 主函数
main() {
    echo "========================================"
    echo "    MarketPrism 停止脚本 v2.0"
    echo "========================================"
    echo ""
    
    # 检查是否在正确的目录
    if [ ! -f "services/message-broker/docker-compose.nats.yml" ]; then
        log_error "请在 MarketPrism 项目根目录下运行此脚本"
        exit 1
    fi
    
    stop_services
    cleanup_resources "$1" "$2"
    show_status
    
    echo "=== 使用说明 ==="
    echo "• 重新启动: ./start_marketprism.sh"
    echo "• 停止并清理: ./stop_marketprism.sh --cleanup"
    echo "• 停止并清理所有镜像: ./stop_marketprism.sh --cleanup --prune"
    echo ""
    
    log_success "MarketPrism 已停止"
}

# 执行主函数
main "$@"
