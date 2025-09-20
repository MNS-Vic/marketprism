#!/bin/bash
# MarketPrism 一键启动脚本 - 完全固化版本
# 确保后人无障碍运行，包含所有必要的检查和修复

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

# 检查依赖
check_dependencies() {
    log_info "检查系统依赖..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose v2 未安装，请升级到 Docker Compose v2"
        exit 1
    fi
    
    log_success "系统依赖检查通过"
}

# 清理旧容器和网络
cleanup_old_resources() {
    log_info "清理旧容器和网络..."
    
    # 停止所有相关容器
    docker compose -f services/data-storage-service/docker-compose.hot-storage.yml down || true
    docker compose -f services/data-collector/docker-compose.unified.yml down || true  
    docker compose -f services/message-broker/docker-compose.nats.yml down || true
    
    # 强制删除所有 marketprism 容器
    for container in $(docker ps -aq --filter name=marketprism- 2>/dev/null || true); do
        docker rm -f $container || true
    done
    
    # 清理遗留网络
    for network in marketprism-storage-network message-broker_default; do
        docker network rm $network 2>/dev/null || true
    done
    
    log_success "旧资源清理完成"
}

# 启动服务
start_services() {
    log_info "按依赖顺序启动服务..."
    
    # 1. 启动 NATS + JetStream
    log_info "启动 NATS JetStream..."
    docker compose -f services/message-broker/docker-compose.nats.yml up -d
    
    # 等待 NATS 健康
    log_info "等待 NATS 健康检查..."
    for i in $(seq 1 30); do
        if curl -fsS http://localhost:8222/healthz >/dev/null 2>&1; then
            log_success "NATS 启动成功"
            break
        fi
        sleep 2
        if [ "$i" = "30" ]; then
            log_error "NATS 健康检查超时"
            exit 1
        fi
    done
    
    # 2. 启动数据收集器
    log_info "启动数据收集器..."
    docker compose -f services/data-collector/docker-compose.unified.yml up -d
    
    # 3. 启动 ClickHouse
    log_info "启动 ClickHouse..."
    docker compose -f services/data-storage-service/docker-compose.hot-storage.yml up -d clickhouse-hot
    
    # 等待 ClickHouse 健康
    log_info "等待 ClickHouse 健康检查..."
    for i in $(seq 1 60); do
        if curl -fsS http://localhost:8123/ping >/dev/null 2>&1; then
            log_success "ClickHouse 启动成功"
            break
        fi
        sleep 2
        if [ "$i" = "60" ]; then
            log_error "ClickHouse 健康检查超时"
            exit 1
        fi
    done
    
    # 4. 启动热存储服务
    log_info "启动热存储服务..."
    docker compose -f services/data-storage-service/docker-compose.hot-storage.yml up -d hot-storage-service
    
    # 等待热存储服务健康
    log_info "等待热存储服务健康检查..."
    for i in $(seq 1 60); do
        if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
            log_success "热存储服务启动成功"
            break
        fi
        sleep 2
        if [ "$i" = "60" ]; then
            log_warning "热存储服务健康检查超时，但可能仍在启动中"
            break
        fi
    done
}

# 验证系统状态
verify_system() {
    log_info "验证系统状态..."
    
    echo ""
    echo "=== 容器状态 ==="
    docker ps --format 'table {{.Names}}\t{{.Status}}' | grep marketprism || true
    
    echo ""
    echo "=== 服务健康检查 ==="
    
    # NATS 健康检查
    if curl -fsS http://localhost:8222/healthz >/dev/null 2>&1; then
        log_success "NATS: 健康"
    else
        log_error "NATS: 不健康"
    fi
    
    # ClickHouse 健康检查
    if curl -fsS http://localhost:8123/ping >/dev/null 2>&1; then
        log_success "ClickHouse: 健康"
    else
        log_error "ClickHouse: 不健康"
    fi
    
    # 热存储服务健康检查
    if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
        log_success "热存储服务: 健康"
    else
        log_warning "热存储服务: 可能仍在启动中"
    fi
    
    echo ""
    echo "=== Compose 状态 ==="
    echo "NATS:"
    docker compose -f services/message-broker/docker-compose.nats.yml ps || true
    echo ""
    echo "数据收集器:"
    docker compose -f services/data-collector/docker-compose.unified.yml ps || true
    echo ""
    echo "数据存储:"
    docker compose -f services/data-storage-service/docker-compose.hot-storage.yml ps || true
}

# 显示使用说明
show_usage() {
    echo ""
    log_info "MarketPrism 启动完成！"
    echo ""
    echo "=== 服务访问地址 ==="
    echo "• NATS 管理界面: http://localhost:8222"
    echo "• ClickHouse HTTP: http://localhost:8123"
    echo "• 热存储服务健康检查: http://localhost:8080/health"
    echo ""
    echo "=== 常用命令 ==="
    echo "• 查看所有容器状态: docker ps"
    echo "• 查看服务日志: docker compose -f services/xxx/docker-compose.yml logs -f"
    echo "• 停止所有服务: ./stop_marketprism.sh"
    echo "• 重启服务: ./start_marketprism.sh"
    echo ""
    echo "=== 数据验证 ==="
    echo "• 查看数据统计: docker exec marketprism-clickhouse-hot clickhouse-client --query=\"SELECT count() FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 10 MINUTE\""
    echo ""
}

# 主函数
main() {
    echo "========================================"
    echo "    MarketPrism 一键启动脚本 v2.0"
    echo "========================================"
    echo ""
    
    # 检查是否在正确的目录
    if [ ! -f "services/message-broker/docker-compose.nats.yml" ]; then
        log_error "请在 MarketPrism 项目根目录下运行此脚本"
        exit 1
    fi
    
    check_dependencies
    cleanup_old_resources
    start_services
    
    # 等待服务完全启动
    log_info "等待服务完全启动..."
    sleep 10
    
    verify_system
    show_usage
    
    log_success "MarketPrism 启动完成！"
}

# 执行主函数
main "$@"
