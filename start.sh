#!/bin/bash

# MarketPrism订单簿管理系统启动脚本
# 用于生产环境快速启动和管理

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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_info "检查系统依赖..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
    
    # 检查环境变量文件
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            log_warn ".env文件不存在，从.env.example复制..."
            cp .env.example .env
            log_warn "请编辑.env文件并填入正确的配置值"
        else
            log_error ".env.example文件不存在，无法创建配置"
            exit 1
        fi
    fi
    
    log_info "依赖检查完成"
}

# 创建必要目录
create_directories() {
    log_info "创建必要目录..."
    
    mkdir -p logs
    mkdir -p data
    mkdir -p test_reports
    mkdir -p monitoring/prometheus/data
    mkdir -p monitoring/grafana/data
    
    log_info "目录创建完成"
}

# 检查端口占用
check_ports() {
    log_info "检查端口占用..."
    
    local ports=(4222 8080 8081 8123 9000 9090 3000 6379)
    local occupied_ports=()
    
    for port in "${ports[@]}"; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            occupied_ports+=($port)
        fi
    done
    
    if [ ${#occupied_ports[@]} -gt 0 ]; then
        log_warn "以下端口已被占用: ${occupied_ports[*]}"
        log_warn "请确保这些端口可用或修改配置"
    else
        log_info "端口检查完成，所有端口可用"
    fi
}

# 启动服务
start_services() {
    log_info "启动MarketPrism订单簿管理系统..."
    
    # 拉取最新镜像
    log_info "拉取Docker镜像..."
    docker-compose pull
    
    # 构建自定义镜像
    log_info "构建应用镜像..."
    docker-compose build
    
    # 启动基础服务
    log_info "启动基础服务（NATS, ClickHouse, Redis）..."
    docker-compose up -d nats clickhouse redis
    
    # 等待基础服务启动
    log_info "等待基础服务启动..."
    sleep 10
    
    # 启动监控服务
    log_info "启动监控服务（Prometheus, Grafana）..."
    docker-compose up -d prometheus grafana
    
    # 等待监控服务启动
    log_info "等待监控服务启动..."
    sleep 5
    
    # 启动订单簿管理系统
    log_info "启动订单簿管理系统..."
    docker-compose up -d orderbook-manager
    
    log_info "所有服务启动完成"
}

# 检查服务状态
check_services() {
    log_info "检查服务状态..."
    
    local services=(
        "nats:4222"
        "clickhouse:8123"
        "redis:6379"
        "prometheus:9090"
        "grafana:3000"
        "orderbook-manager:8080"
    )
    
    for service in "${services[@]}"; do
        local name=$(echo $service | cut -d: -f1)
        local port=$(echo $service | cut -d: -f2)
        
        if curl -f -s "http://localhost:$port/health" >/dev/null 2>&1 || \
           curl -f -s "http://localhost:$port/ping" >/dev/null 2>&1 || \
           curl -f -s "http://localhost:$port" >/dev/null 2>&1; then
            log_info "$name: ✅ 运行正常"
        else
            log_warn "$name: ⚠️ 可能未就绪"
        fi
    done
}

# 显示访问信息
show_access_info() {
    log_info "服务访问信息:"
    echo ""
    echo "🔍 监控面板:"
    echo "  Grafana:    http://localhost:3000 (admin/admin123)"
    echo "  Prometheus: http://localhost:9090"
    echo ""
    echo "📊 系统状态:"
    echo "  健康检查:   http://localhost:8080/health"
    echo "  指标监控:   http://localhost:8081/metrics"
    echo ""
    echo "💾 数据库:"
    echo "  ClickHouse: http://localhost:8123"
    echo "  Redis:      localhost:6379"
    echo ""
    echo "📡 消息队列:"
    echo "  NATS:       http://localhost:8222"
    echo ""
    echo "📋 日志查看:"
    echo "  docker-compose logs -f orderbook-manager"
    echo ""
}

# 显示帮助信息
show_help() {
    echo "🚀 MarketPrism订单簿管理系统启动脚本"
    echo "========================================"
    echo ""
    echo "用法:"
    echo "  ./start.sh [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示此帮助信息"
    echo "  -q, --quiet    静默模式，减少输出"
    echo "  -v, --verbose  详细模式，显示更多信息"
    echo "  --no-check     跳过端口检查"
    echo "  --force        强制启动，忽略警告"
    echo ""
    echo "功能:"
    echo "  • 检查系统依赖（Docker, Docker Compose）"
    echo "  • 创建必要目录"
    echo "  • 检查端口占用情况"
    echo "  • 启动所有服务（NATS, ClickHouse, Redis, Prometheus, Grafana, 订单簿管理器）"
    echo "  • 验证服务状态"
    echo "  • 显示访问信息"
    echo ""
    echo "服务端口:"
    echo "  • 订单簿管理器: 8080 (健康检查), 8081 (指标)"
    echo "  • NATS: 4222 (客户端), 8222 (监控)"
    echo "  • ClickHouse: 8123 (HTTP), 9000 (Native)"
    echo "  • Prometheus: 9090"
    echo "  • Grafana: 3000"
    echo "  • Redis: 6379"
    echo ""
    echo "示例:"
    echo "  ./start.sh              # 正常启动"
    echo "  ./start.sh --quiet      # 静默启动"
    echo "  ./start.sh --no-check   # 跳过端口检查"
    echo ""
    echo "注意事项:"
    echo "  • 确保.env文件已正确配置"
    echo "  • 确保Docker服务正在运行"
    echo "  • 首次启动可能需要较长时间下载镜像"
    echo ""
}

# 主函数
main() {
    local quiet_mode=false
    local verbose_mode=false
    local skip_port_check=false
    local force_mode=false

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -q|--quiet)
                quiet_mode=true
                shift
                ;;
            -v|--verbose)
                verbose_mode=true
                shift
                ;;
            --no-check)
                skip_port_check=true
                shift
                ;;
            --force)
                force_mode=true
                shift
                ;;
            *)
                log_error "未知选项: $1"
                echo "使用 --help 查看帮助信息"
                exit 1
                ;;
        esac
    done

    if [ "$quiet_mode" = false ]; then
        echo "🚀 MarketPrism订单簿管理系统启动脚本"
        echo "========================================"
    fi

    check_dependencies
    create_directories

    if [ "$skip_port_check" = false ]; then
        check_ports
    fi

    start_services

    # 等待服务完全启动
    if [ "$quiet_mode" = false ]; then
        log_info "等待服务完全启动..."
    fi
    sleep 15

    check_services

    if [ "$quiet_mode" = false ]; then
        show_access_info
    fi

    log_info "MarketPrism订单簿管理系统启动完成！"
    if [ "$quiet_mode" = false ]; then
        log_info "使用 'docker-compose logs -f' 查看日志"
        log_info "使用 './stop.sh' 停止服务"
    fi
}

# 执行主函数
main "$@"
