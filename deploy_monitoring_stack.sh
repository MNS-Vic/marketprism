#!/bin/bash

# MarketPrism 监控告警服务一键部署脚本
# 基于Grafana和Prometheus官方文档的最佳实践

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
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3未安装，请先安装Python3"
        exit 1
    fi
    
    # 检查虚拟环境
    if [ ! -d "venv_monitoring" ]; then
        log_error "虚拟环境不存在，请先创建虚拟环境"
        exit 1
    fi
    
    log_success "依赖检查完成"
}

# 清理现有容器
cleanup_containers() {
    log_info "清理现有容器..."
    
    containers=("prometheus-marketprism" "grafana-marketprism")
    for container in "${containers[@]}"; do
        if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
            log_info "停止并删除容器: $container"
            docker stop "$container" >/dev/null 2>&1 || true
            docker rm "$container" >/dev/null 2>&1 || true
        fi
    done
    
    log_success "容器清理完成"
}

# 创建Prometheus配置
create_prometheus_config() {
    log_info "创建Prometheus配置文件..."
    
    cat > prometheus-marketprism.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: 'marketprism-monitor'

scrape_configs:
  # Prometheus自身监控
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
    scrape_interval: 15s

  # MarketPrism监控告警服务
  - job_name: 'monitoring-alerting'
    static_configs:
      - targets: ['host.docker.internal:8082']
    metrics_path: /metrics
    scrape_interval: 10s
    scrape_timeout: 5s
EOF
    
    log_success "Prometheus配置文件创建完成"
}

# 启动监控告警服务
start_monitoring_service() {
    log_info "启动MarketPrism监控告警服务..."
    
    # 检查服务是否已经运行
    if curl -s http://localhost:8082/health >/dev/null 2>&1; then
        log_warning "监控告警服务已在运行"
        return 0
    fi
    
    # 激活虚拟环境并启动服务
    source venv_monitoring/bin/activate
    nohup python3 services/monitoring-alerting-service/start_service.py > logs/monitoring-service.log 2>&1 &
    
    # 等待服务启动
    log_info "等待服务启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8082/health >/dev/null 2>&1; then
            log_success "监控告警服务启动成功"
            return 0
        fi
        sleep 1
    done
    
    log_error "监控告警服务启动失败"
    exit 1
}

# 启动Prometheus
start_prometheus() {
    log_info "启动Prometheus..."
    
    docker run -d --name prometheus-marketprism \
        --add-host=host.docker.internal:host-gateway \
        -p 9090:9090 \
        -v "$(pwd)/prometheus-marketprism.yml:/etc/prometheus/prometheus.yml:ro" \
        prom/prometheus:latest \
        --config.file=/etc/prometheus/prometheus.yml \
        --storage.tsdb.path=/prometheus \
        --web.console.libraries=/etc/prometheus/console_libraries \
        --web.console.templates=/etc/prometheus/consoles \
        --storage.tsdb.retention.time=200h \
        --web.enable-lifecycle
    
    # 等待Prometheus启动
    log_info "等待Prometheus启动..."
    for i in {1..30}; do
        if curl -s http://localhost:9090/-/healthy >/dev/null 2>&1; then
            log_success "Prometheus启动成功"
            return 0
        fi
        sleep 1
    done
    
    log_error "Prometheus启动失败"
    exit 1
}

# 启动Grafana
start_grafana() {
    log_info "启动Grafana..."
    
    docker run -d --name grafana-marketprism \
        --add-host=host.docker.internal:host-gateway \
        -p 3000:3000 \
        -e GF_SECURITY_ADMIN_PASSWORD=admin123 \
        -e GF_SECURITY_ADMIN_USER=admin \
        -e GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource \
        grafana/grafana:latest
    
    # 等待Grafana启动
    log_info "等待Grafana启动..."
    for i in {1..60}; do
        if curl -s http://localhost:3000/api/health >/dev/null 2>&1; then
            log_success "Grafana启动成功"
            return 0
        fi
        sleep 1
    done
    
    log_error "Grafana启动失败"
    exit 1
}

# 配置Grafana数据源
configure_grafana() {
    log_info "配置Grafana数据源..."
    
    # 等待额外时间确保Grafana完全就绪
    sleep 5
    
    if [ -f "setup_grafana_datasource.py" ]; then
        source venv_monitoring/bin/activate
        python3 setup_grafana_datasource.py
        log_success "Grafana数据源配置完成"
    else
        log_warning "Grafana数据源配置脚本不存在，跳过自动配置"
    fi
}

# 验证部署
verify_deployment() {
    log_info "验证部署状态..."
    
    # 检查服务状态
    services=(
        "监控告警服务:http://localhost:8082/health"
        "Prometheus:http://localhost:9090/-/healthy"
        "Grafana:http://localhost:3000/api/health"
    )
    
    all_healthy=true
    for service in "${services[@]}"; do
        name="${service%%:*}"
        url="${service##*:}"
        
        if curl -s "$url" >/dev/null 2>&1; then
            log_success "$name: 运行正常"
        else
            log_error "$name: 运行异常"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        log_success "所有服务运行正常"
        return 0
    else
        log_error "部分服务运行异常"
        return 1
    fi
}

# 运行集成测试
run_tests() {
    log_info "运行集成测试..."
    
    source venv_monitoring/bin/activate
    
    # 运行API测试
    if [ -f "comprehensive_api_test.py" ]; then
        log_info "运行API完整性测试..."
        if python3 comprehensive_api_test.py; then
            log_success "API测试通过"
        else
            log_warning "API测试失败"
        fi
    fi
    
    # 运行Grafana集成测试
    if [ -f "grafana_integration_test.py" ]; then
        log_info "运行Grafana集成测试..."
        if python3 grafana_integration_test.py; then
            log_success "Grafana集成测试通过"
        else
            log_warning "Grafana集成测试失败"
        fi
    fi
}

# 显示访问信息
show_access_info() {
    log_info "部署完成！访问信息："
    echo ""
    echo "🎯 MarketPrism监控告警服务:"
    echo "   URL: http://localhost:8082"
    echo "   健康检查: http://localhost:8082/health"
    echo "   API文档: http://localhost:8082/"
    echo ""
    echo "📊 Prometheus:"
    echo "   URL: http://localhost:9090"
    echo "   目标状态: http://localhost:9090/targets"
    echo ""
    echo "🎨 Grafana:"
    echo "   URL: http://localhost:3000"
    echo "   用户名: admin"
    echo "   密码: admin123"
    echo ""
    echo "📋 管理命令:"
    echo "   停止所有服务: docker stop prometheus-marketprism grafana-marketprism"
    echo "   查看日志: tail -f logs/monitoring-service.log"
    echo "   重启脚本: $0"
}

# 主函数
main() {
    echo "🚀 MarketPrism监控告警服务部署脚本"
    echo "基于Grafana和Prometheus官方文档"
    echo "========================================"
    
    # 创建日志目录
    mkdir -p logs
    
    # 执行部署步骤
    check_dependencies
    cleanup_containers
    create_prometheus_config
    start_monitoring_service
    start_prometheus
    start_grafana
    configure_grafana
    
    # 验证和测试
    if verify_deployment; then
        run_tests
        show_access_info
        log_success "🎉 部署完成！"
    else
        log_error "❌ 部署失败，请检查日志"
        exit 1
    fi
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
