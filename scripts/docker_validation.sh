#!/bin/bash
set -e

# MarketPrism Docker容器化验证脚本

echo "🚀 MarketPrism Docker容器化验证"
echo "时间: $(date)"
echo "=" * 60

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

# 检查Docker和Docker Compose
check_prerequisites() {
    log_info "检查前置条件..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose未安装"
        exit 1
    fi
    
    log_success "前置条件检查通过"
}

# 构建所有镜像
build_images() {
    log_info "构建Docker镜像..."
    
    # 构建message-broker镜像
    log_info "构建message-broker镜像..."
    docker build -f services/message-broker/Dockerfile.nats -t marketprism-message-broker services/message-broker/
    
    # 构建data-storage镜像
    log_info "构建data-storage镜像..."
    docker build -f services/data-storage-service/Dockerfile.production -t marketprism-data-storage services/data-storage-service/
    
    # 构建data-collector镜像
    log_info "构建data-collector镜像..."
    docker build -f services/data-collector/Dockerfile -t marketprism-data-collector .
    
    log_success "所有镜像构建完成"
}

# 启动服务
start_services() {
    log_info "启动MarketPrism服务..."
    
    # 使用生产配置启动
    docker-compose -f docker-compose.production.yml --env-file .env.production up -d
    
    log_success "服务启动命令已执行"
}

# 等待服务就绪
wait_for_services() {
    log_info "等待服务就绪..."
    
    local services=("clickhouse:8123/ping" "message-broker:8222/healthz")
    local max_attempts=60
    
    for service in "${services[@]}"; do
        local service_name=$(echo $service | cut -d':' -f1)
        local endpoint="http://localhost:$(echo $service | cut -d':' -f2-)"
        
        log_info "等待 $service_name 服务..."
        
        local attempt=1
        while [ $attempt -le $max_attempts ]; do
            if curl -s --connect-timeout 2 "$endpoint" > /dev/null 2>&1; then
                log_success "$service_name 已就绪"
                break
            fi
            
            if [ $attempt -eq $max_attempts ]; then
                log_error "$service_name 启动超时"
                return 1
            fi
            
            sleep 2
            attempt=$((attempt + 1))
        done
    done
    
    log_success "所有核心服务已就绪"
}

# 验证数据流
verify_data_flow() {
    log_info "验证数据流..."
    
    # 等待数据收集器启动
    sleep 30
    
    # 检查NATS消息
    log_info "检查NATS消息统计..."
    local nats_stats=$(curl -s http://localhost:8222/jsz)
    local message_count=$(echo $nats_stats | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('messages', 0))")
    
    if [ "$message_count" -gt 0 ]; then
        log_success "NATS消息流正常: $message_count 条消息"
    else
        log_warning "NATS暂无消息，可能需要更多时间"
    fi
    
    # 检查ClickHouse数据
    log_info "检查ClickHouse数据..."
    sleep 10
    
    local trade_count=$(curl -s "http://localhost:8123/?database=marketprism_hot" --data "SELECT count() FROM trades WHERE timestamp >= now() - INTERVAL 5 MINUTE" 2>/dev/null || echo "0")
    
    if [ "$trade_count" -gt 0 ]; then
        log_success "ClickHouse数据写入正常: $trade_count 条交易记录"
    else
        log_warning "ClickHouse暂无最新数据，可能需要更多时间"
    fi
}

# 健康检查
health_check() {
    log_info "执行健康检查..."
    
    local services=("data-storage:8081" "collector-binance-spot:8082" "collector-binance-derivatives:8083")
    
    for service in "${services[@]}"; do
        local service_name=$(echo $service | cut -d':' -f1)
        local port=$(echo $service | cut -d':' -f2)
        local endpoint="http://localhost:$port/health"
        
        if curl -s --connect-timeout 5 "$endpoint" > /dev/null 2>&1; then
            log_success "$service_name 健康检查通过"
        else
            log_warning "$service_name 健康检查失败"
        fi
    done
}

# 显示服务状态
show_status() {
    log_info "服务状态概览..."
    
    echo ""
    echo "📊 容器状态:"
    docker-compose -f docker-compose.production.yml ps
    
    echo ""
    echo "🔗 服务端点:"
    echo "  - ClickHouse HTTP: http://localhost:8123"
    echo "  - NATS监控: http://localhost:8222"
    echo "  - 数据存储服务: http://localhost:8081/health"
    echo "  - Binance现货收集器: http://localhost:8082/health"
    echo "  - Binance衍生品收集器: http://localhost:8083/health"
    
    echo ""
    echo "📋 验证命令:"
    echo "  - 查看NATS统计: curl http://localhost:8222/jsz"
    echo "  - 查看交易数据: curl 'http://localhost:8123/?database=marketprism_hot' --data 'SELECT count() FROM trades'"
    echo "  - 查看容器日志: docker-compose -f docker-compose.production.yml logs -f [service_name]"
}

# 清理函数
cleanup() {
    log_info "清理资源..."
    docker-compose -f docker-compose.production.yml down
    log_success "清理完成"
}

# 主函数
main() {
    case "${1:-start}" in
        "build")
            check_prerequisites
            build_images
            ;;
        "start")
            check_prerequisites
            build_images
            start_services
            wait_for_services
            verify_data_flow
            health_check
            show_status
            ;;
        "stop")
            cleanup
            ;;
        "status")
            show_status
            ;;
        *)
            echo "用法: $0 {build|start|stop|status}"
            echo "  build  - 仅构建镜像"
            echo "  start  - 构建并启动所有服务（默认）"
            echo "  stop   - 停止所有服务"
            echo "  status - 显示服务状态"
            exit 1
            ;;
    esac
}

# 信号处理
trap cleanup SIGINT SIGTERM

# 执行主函数
main "$@"
