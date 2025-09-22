#!/bin/bash
# MarketPrism 完整系统部署脚本
# 🔄 Docker部署简化改造版本 (2025-08-02)

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
    
    # 检查Docker Compose v2 插件
    if ! docker compose version >/dev/null 2>&1; then
        log_error "Docker Compose v2 未安装，请先安装 docker-compose-v2 或启用 docker compose 插件"
        exit 1
    fi
    
    # 检查Python3
    if ! command -v python3 &> /dev/null; then
        log_error "Python3未安装，请先安装Python3"
        exit 1
    fi
    
    log_success "系统依赖检查通过"
}

# 优化系统配置
optimize_system() {
    log_info "优化系统配置..."
    
    # 增加inotify watches限制
    if ! grep -q "fs.inotify.max_user_watches" /etc/sysctl.conf; then
        echo "fs.inotify.max_user_watches=524288" | sudo tee -a /etc/sysctl.conf
        sudo sysctl -p
        log_success "inotify watches限制已优化"
    else
        log_info "inotify watches限制已存在"
    fi
    
    # 优化网络配置
    if ! grep -q "net.core.somaxconn" /etc/sysctl.conf; then
        echo "net.core.somaxconn = 65535" | sudo tee -a /etc/sysctl.conf
        echo "net.ipv4.tcp_max_syn_backlog = 65535" | sudo tee -a /etc/sysctl.conf
        sudo sysctl -p
        log_success "网络配置已优化"
    else
        log_info "网络配置已存在"
    fi
}

# 部署NATS消息队列
deploy_nats() {
    log_info "部署NATS消息队列..."
    
    cd ../message-broker/unified-nats
    
    # 停止现有容器
    sudo docker compose -f docker-compose.unified.yml down 2>/dev/null || true
    
    # 启动NATS
    sudo docker compose -f docker-compose.unified.yml up -d
    
    # 等待NATS启动
    log_info "等待NATS启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8222/varz > /dev/null 2>&1; then
            log_success "NATS启动成功"
            break
        fi
        sleep 2
        if [ $i -eq 30 ]; then
            log_error "NATS启动超时"
            exit 1
        fi
    done
    
    cd - > /dev/null
}

# 部署Data Collector
deploy_data_collector() {
    log_info "部署Data Collector..."
    
    cd ../data-collector
    
    # 停止现有容器
    sudo docker compose -f docker-compose.unified.yml down 2>/dev/null || true
    
    # 启动Data Collector
    sudo docker compose -f docker-compose.unified.yml up -d
    
    # 等待Data Collector启动
    log_info "等待Data Collector启动..."
    sleep 30
    
    # 检查容器状态
    if sudo docker ps | grep -q "marketprism-data-collector"; then
        log_success "Data Collector启动成功"
    else
        log_error "Data Collector启动失败"
        sudo docker logs marketprism-data-collector --tail 20
        exit 1
    fi
    
    cd - > /dev/null
}

# 部署ClickHouse热存储
deploy_clickhouse() {
    log_info "部署ClickHouse热存储..."
    
    # 停止现有容器
    sudo docker compose -f docker-compose.hot-storage.yml down 2>/dev/null || true
    
    # 启动ClickHouse
    sudo docker compose -f docker-compose.hot-storage.yml up -d clickhouse-hot
    
    # 等待ClickHouse启动
    log_info "等待ClickHouse启动..."
    for i in {1..60}; do
        if curl -s http://localhost:8123/ping > /dev/null 2>&1; then
            log_success "ClickHouse启动成功"
            break
        fi
        sleep 2
        if [ $i -eq 60 ]; then
            log_error "ClickHouse启动超时"
            exit 1
        fi
    done
    
    # 创建表结构
    log_info "创建ClickHouse表结构..."
    if [ -f "scripts/create_all_tables.sh" ]; then
        chmod +x scripts/create_all_tables.sh
        ./scripts/create_all_tables.sh
        log_success "表结构创建完成"
    else
        log_error "建表脚本不存在"
        exit 1
    fi
}

# 部署热存储服务
deploy_hot_storage() {
    log_info "部署热存储服务..."
    
    # 检查Python依赖
    if ! python3 -c "import nats, aiohttp" 2>/dev/null; then
        log_info "安装Python依赖..."
        pip3 install nats-py aiohttp psutil
    fi
    
    # 启动热存储服务
    log_info "启动热存储服务..."
    nohup python3 simple_hot_storage.py > logs/hot_storage.log 2>&1 &
    HOT_STORAGE_PID=$!
    echo $HOT_STORAGE_PID > hot_storage.pid
    
    # 等待服务启动
    sleep 10
    
    # 检查服务状态
    if kill -0 $HOT_STORAGE_PID 2>/dev/null; then
        log_success "热存储服务启动成功 (PID: $HOT_STORAGE_PID)"
    else
        log_error "热存储服务启动失败"
        cat logs/hot_storage.log | tail -20
        exit 1
    fi
}

# 验证部署
verify_deployment() {
    log_info "验证系统部署..."
    
    # 运行验证脚本
    if [ -f "verify_deployment.py" ]; then
        python3 verify_deployment.py
        if [ $? -eq 0 ]; then
            log_success "系统验证通过"
        else
            log_error "系统验证失败"
            exit 1
        fi
    else
        log_warning "验证脚本不存在，跳过验证"
    fi
}

# 启动监控服务
deploy_monitoring() {
    log_info "启动系统监控..."
    
    if [ -f "system_monitor.py" ]; then
        nohup python3 system_monitor.py > logs/monitor.log 2>&1 &
        MONITOR_PID=$!
        echo $MONITOR_PID > monitor.pid
        log_success "系统监控启动成功 (PID: $MONITOR_PID)"
    else
        log_warning "监控脚本不存在，跳过监控"
    fi
}

# 显示部署状态
show_deployment_status() {
    log_info "部署状态摘要:"
    echo "=================================="
    
    # 检查容器状态
    echo "Docker容器状态:"
    sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep marketprism || echo "无MarketPrism容器运行"
    
    echo ""
    echo "服务端点:"
    echo "  - NATS监控: http://localhost:8222"
    echo "  - ClickHouse: http://localhost:8123"
    echo "  - 热存储服务: http://localhost:8080"
    
    echo ""
    echo "日志文件:"
    echo "  - 热存储服务: logs/hot_storage.log"
    echo "  - 系统监控: logs/monitor.log"
    
    echo ""
    echo "管理命令:"
    echo "  - 停止热存储: kill \$(cat hot_storage.pid)"
    echo "  - 停止监控: kill \$(cat monitor.pid)"
    echo "  - 查看日志: tail -f logs/hot_storage.log"
    echo "  - 系统验证: python3 verify_deployment.py"
}

# 清理函数
cleanup() {
    log_info "清理资源..."
    
    # 停止Python服务
    if [ -f "hot_storage.pid" ]; then
        kill $(cat hot_storage.pid) 2>/dev/null || true
        rm -f hot_storage.pid
    fi
    
    if [ -f "monitor.pid" ]; then
        kill $(cat monitor.pid) 2>/dev/null || true
        rm -f monitor.pid
    fi
}

# 主函数
main() {
    log_info "🚀 开始部署MarketPrism完整系统"
    echo "=================================="
    
    # 创建日志目录
    mkdir -p logs
    
    # 检查依赖
    check_dependencies
    
    # 优化系统配置
    optimize_system
    
    # 部署各个组件
    deploy_nats
    deploy_data_collector
    deploy_clickhouse
    deploy_hot_storage
    
    # 验证部署
    verify_deployment
    
    # 启动监控
    deploy_monitoring
    
    # 显示状态
    show_deployment_status
    
    log_success "🎉 MarketPrism系统部署完成！"
    echo ""
    echo "系统现在正在运行，数据流："
    echo "Data Collector → NATS → Hot Storage → ClickHouse"
    echo ""
    echo "使用 'python3 verify_deployment.py' 验证系统状态"
    echo "使用 'Ctrl+C' 然后运行此脚本的 --stop 参数来停止系统"
}

# 停止函数
stop_system() {
    log_info "🛑 停止MarketPrism系统"
    
    cleanup
    
    # 停止Docker容器
    cd ../message-broker/unified-nats
    sudo docker compose -f docker-compose.unified.yml down
    cd - > /dev/null
    
    cd ../data-collector
    sudo docker compose -f docker-compose.unified.yml down
    cd - > /dev/null
    
    sudo docker compose -f docker-compose.hot-storage.yml down
    
    log_success "系统已停止"
}

# 参数处理
case "${1:-}" in
    --stop)
        stop_system
        ;;
    --cleanup)
        cleanup
        ;;
    *)
        # 设置信号处理
        trap cleanup EXIT
        main
        ;;
esac
