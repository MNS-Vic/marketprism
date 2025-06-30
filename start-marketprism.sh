#!/bin/bash

# MarketPrism 统一启动脚本
# 支持开发、测试、生产环境的一键启动

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

# 显示帮助信息
show_help() {
    cat << EOF
MarketPrism 统一启动脚本

用法: $0 [选项] [环境]

环境:
  dev         开发环境 (默认)
  test        测试环境
  prod        生产环境

选项:
  -h, --help     显示此帮助信息
  -c, --check    仅检查环境，不启动服务
  -s, --stop     停止所有服务
  -r, --restart  重启所有服务
  -v, --verbose  详细输出
  --no-deps      跳过依赖检查
  --core-only    仅启动核心服务

示例:
  $0 dev              # 启动开发环境
  $0 prod --check     # 检查生产环境
  $0 --stop           # 停止所有服务
  $0 --restart prod   # 重启生产环境

EOF
}

# 默认参数
ENVIRONMENT="dev"
CHECK_ONLY=false
STOP_SERVICES=false
RESTART_SERVICES=false
VERBOSE=false
SKIP_DEPS=false
CORE_ONLY=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--check)
            CHECK_ONLY=true
            shift
            ;;
        -s|--stop)
            STOP_SERVICES=true
            shift
            ;;
        -r|--restart)
            RESTART_SERVICES=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --no-deps)
            SKIP_DEPS=true
            shift
            ;;
        --core-only)
            CORE_ONLY=true
            shift
            ;;
        dev|test|prod)
            ENVIRONMENT=$1
            shift
            ;;
        *)
            log_error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 检查Docker和Docker Compose
check_dependencies() {
    if [[ "$SKIP_DEPS" == "true" ]]; then
        log_info "跳过依赖检查"
        return 0
    fi

    log_info "检查系统依赖..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装或不在PATH中"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose 未安装或不在PATH中"
        exit 1
    fi
    
    # 检查Docker服务状态
    if ! docker info &> /dev/null; then
        log_error "Docker 服务未运行"
        exit 1
    fi
    
    log_success "系统依赖检查通过"
}

# 检查配置文件
check_config() {
    log_info "检查配置文件..."
    
    local config_files=(
        "config/nats_unified_streams.yaml"
        "config/exchanges.yaml"
        "config/services.yaml"
        "docker-compose.yml"
    )
    
    for config_file in "${config_files[@]}"; do
        if [[ ! -f "$config_file" ]]; then
            log_error "配置文件不存在: $config_file"
            exit 1
        fi
    done
    
    log_success "配置文件检查通过"
}

# 检查端口占用
check_ports() {
    log_info "检查端口占用..."
    
    local ports=(4222 6379 8080 8081 8084 8086 8087 9000 9090 3000)
    local occupied_ports=()
    
    for port in "${ports[@]}"; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            occupied_ports+=($port)
        fi
    done
    
    if [[ ${#occupied_ports[@]} -gt 0 ]]; then
        log_warning "以下端口已被占用: ${occupied_ports[*]}"
        log_warning "这可能导致服务启动失败"
    else
        log_success "端口检查通过"
    fi
}

# 停止服务
stop_services() {
    log_info "停止MarketPrism服务..."
    
    if [[ -f "docker-compose.yml" ]]; then
        docker-compose down --remove-orphans
        log_success "服务已停止"
    else
        log_error "docker-compose.yml 文件不存在"
        exit 1
    fi
}

# 启动核心服务
start_core_services() {
    log_info "启动核心基础设施服务..."
    
    # 启动基础设施
    docker-compose up -d redis nats clickhouse
    
    # 等待服务就绪
    log_info "等待基础设施服务启动..."
    sleep 10
    
    # 检查服务健康状态
    check_service_health "redis" 6379
    check_service_health "nats" 4222
    check_service_health "clickhouse" 9000
    
    log_success "核心基础设施服务启动完成"
}

# 启动应用服务
start_app_services() {
    if [[ "$CORE_ONLY" == "true" ]]; then
        log_info "仅启动核心服务，跳过应用服务"
        return 0
    fi

    log_info "启动应用服务..."
    
    # 启动数据收集器
    docker-compose up -d data-collector
    sleep 5
    check_service_health "data-collector" 8081
    
    # 启动支持服务
    docker-compose up -d message-broker monitoring-alerting task-worker
    sleep 5
    
    # 启动API网关
    docker-compose up -d api-gateway
    sleep 3
    check_service_health "api-gateway" 8080
    
    log_success "应用服务启动完成"
}

# 启动监控服务
start_monitoring() {
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        log_info "启动监控服务..."
        docker-compose up -d prometheus grafana
        sleep 5
        log_success "监控服务启动完成"
    fi
}

# 检查服务健康状态
check_service_health() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=1
    
    log_info "检查 $service_name 服务健康状态..."
    
    while [[ $attempt -le $max_attempts ]]; do
        if nc -z localhost $port 2>/dev/null; then
            log_success "$service_name 服务已就绪"
            return 0
        fi
        
        if [[ "$VERBOSE" == "true" ]]; then
            log_info "等待 $service_name 服务启动... (尝试 $attempt/$max_attempts)"
        fi
        
        sleep 2
        ((attempt++))
    done
    
    log_error "$service_name 服务启动失败或超时"
    return 1
}

# 显示服务状态
show_status() {
    log_info "MarketPrism 服务状态:"
    echo
    docker-compose ps
    echo
    
    log_info "服务访问地址:"
    echo "  🌐 API Gateway:     http://localhost:8080"
    echo "  📊 Data Collector:  http://localhost:8081"
    echo "  📈 Prometheus:      http://localhost:9090"
    echo "  📊 Grafana:         http://localhost:3000"
    echo "  🔧 Task Worker:     http://localhost:8087"
    echo
}

# 主函数
main() {
    echo "🚀 MarketPrism 统一启动脚本"
    echo "环境: $ENVIRONMENT"
    echo "================================"
    
    # 检查依赖
    check_dependencies
    check_config
    
    if [[ "$CHECK_ONLY" == "true" ]]; then
        check_ports
        log_success "环境检查完成"
        exit 0
    fi
    
    if [[ "$STOP_SERVICES" == "true" ]]; then
        stop_services
        exit 0
    fi
    
    if [[ "$RESTART_SERVICES" == "true" ]]; then
        stop_services
        sleep 3
    fi
    
    # 检查端口
    check_ports
    
    # 启动服务
    start_core_services
    start_app_services
    start_monitoring
    
    # 显示状态
    show_status
    
    log_success "MarketPrism 启动完成!"
    log_info "使用 '$0 --stop' 停止所有服务"
}

# 执行主函数
main "$@"
