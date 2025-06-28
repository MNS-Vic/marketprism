#!/bin/bash

# MarketPrism生产环境部署脚本
# 解决Docker网络配置和生产监控设置

set -e

echo "🚀 MarketPrism生产环境部署脚本"
echo "================================"
echo ""

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
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
    
    log_success "系统依赖检查通过"
}

# 创建环境配置
create_env_config() {
    log_info "创建环境配置文件..."
    
    if [ ! -f .env ]; then
        cat > .env << EOF
# MarketPrism生产环境配置
GRAFANA_ADMIN_PASSWORD=marketprism_admin_2024!
REDIS_PASSWORD=marketprism_redis_2024!
MONITORING_API_KEY=mp-monitoring-key-2024
MONITORING_USERNAME=admin
MONITORING_PASSWORD=marketprism2024!
AUTH_ENABLED=true
SSL_ENABLED=false
ENVIRONMENT=production
EOF
        log_success "环境配置文件已创建"
    else
        log_warning "环境配置文件已存在，跳过创建"
    fi
}

# 创建必要目录
create_directories() {
    log_info "创建必要目录..."
    
    mkdir -p logs
    mkdir -p data/{prometheus,grafana,redis}
    mkdir -p config/prometheus/rules
    
    log_success "目录创建完成"
}

# 停止现有服务
stop_existing_services() {
    log_info "停止现有服务..."
    
    # 停止可能运行的服务
    docker-compose -f docker-compose.production.yml down 2>/dev/null || true
    docker-compose down 2>/dev/null || true
    
    # 停止单独的容器
    docker stop marketprism-monitoring marketprism-prometheus marketprism-grafana 2>/dev/null || true
    docker rm marketprism-monitoring marketprism-prometheus marketprism-grafana 2>/dev/null || true
    
    # 停止Python服务
    pkill -f "python.*monitoring" 2>/dev/null || true
    
    log_success "现有服务已停止"
}

# 构建和启动服务
start_services() {
    log_info "启动生产环境服务..."
    
    # 启动服务
    docker-compose -f docker-compose.production.yml up -d --build
    
    log_success "服务启动完成"
}

# 等待服务就绪
wait_for_services() {
    log_info "等待服务就绪..."
    
    # 等待监控服务
    log_info "等待监控服务启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8082/health > /dev/null 2>&1; then
            log_success "监控服务已就绪"
            break
        fi
        sleep 2
        echo -n "."
    done
    
    # 等待Prometheus
    log_info "等待Prometheus启动..."
    for i in {1..30}; do
        if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
            log_success "Prometheus已就绪"
            break
        fi
        sleep 2
        echo -n "."
    done
    
    # 等待Grafana
    log_info "等待Grafana启动..."
    for i in {1..60}; do
        if curl -s http://localhost:3000/api/health > /dev/null 2>&1; then
            log_success "Grafana已就绪"
            break
        fi
        sleep 2
        echo -n "."
    done
}

# 验证部署
verify_deployment() {
    log_info "验证部署状态..."
    
    echo ""
    echo "📊 服务状态检查:"
    
    # 检查监控服务
    if curl -s http://localhost:8082/health | grep -q "healthy"; then
        log_success "✅ 监控服务: 正常"
    else
        log_error "❌ 监控服务: 异常"
    fi
    
    # 检查Prometheus
    if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
        log_success "✅ Prometheus: 正常"
    else
        log_error "❌ Prometheus: 异常"
    fi
    
    # 检查Grafana
    if curl -s http://localhost:3000/api/health | grep -q "ok"; then
        log_success "✅ Grafana: 正常"
    else
        log_error "❌ Grafana: 异常"
    fi
    
    echo ""
    echo "🔗 访问地址:"
    echo "   监控服务: http://localhost:8082"
    echo "   Prometheus: http://localhost:9090"
    echo "   Grafana: http://localhost:3000 (admin/marketprism_admin_2024!)"
    echo ""
}

# 显示使用说明
show_usage() {
    echo "📚 使用说明:"
    echo ""
    echo "1. 监控服务API测试:"
    echo "   curl -H 'X-API-Key: mp-monitoring-key-2024' http://localhost:8082/api/v1/alerts"
    echo ""
    echo "2. Prometheus指标查看:"
    echo "   curl -H 'X-API-Key: mp-monitoring-key-2024' http://localhost:8082/metrics"
    echo ""
    echo "3. 查看服务日志:"
    echo "   docker-compose -f docker-compose.production.yml logs -f"
    echo ""
    echo "4. 停止服务:"
    echo "   docker-compose -f docker-compose.production.yml down"
    echo ""
}

# 主函数
main() {
    echo "开始MarketPrism生产环境部署..."
    echo ""
    
    check_dependencies
    create_env_config
    create_directories
    stop_existing_services
    start_services
    wait_for_services
    verify_deployment
    show_usage
    
    log_success "🎉 MarketPrism生产环境部署完成！"
}

# 执行主函数
main "$@"
