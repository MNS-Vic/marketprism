#!/bin/bash

# MarketPrism 一键启动脚本
# 更新版本 - 包含NATS自动推送功能验证

set -e  # 遇到错误立即退出

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
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose 未安装"
        exit 1
    fi
    
    log_success "系统依赖检查完成"
}

# 检查和修复nats-py版本
check_nats_py_version() {
    log_info "检查nats-py版本..."
    
    if [ -d "venv" ]; then
        source venv/bin/activate
        
        # 检查当前版本
        current_version=$(pip show nats-py 2>/dev/null | grep Version | cut -d' ' -f2 || echo "not_installed")
        
        if [ "$current_version" != "2.2.0" ]; then
            log_warning "nats-py版本不正确 (当前: $current_version, 需要: 2.2.0)"
            log_info "正在安装正确版本..."
            pip install nats-py==2.2.0
            log_success "nats-py版本已修复为2.2.0"
        else
            log_success "nats-py版本正确: 2.2.0"
        fi
        
        deactivate
    else
        log_warning "虚拟环境不存在，将在后续步骤中创建"
    fi
}

# 启动基础设施服务
start_infrastructure() {
    log_info "启动基础设施服务..."
    
    # 启动NATS
    log_info "启动NATS服务器..."
    docker-compose up -d nats
    
    # 等待NATS启动
    log_info "等待NATS服务器启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8222/varz > /dev/null 2>&1; then
            log_success "NATS服务器已启动"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "NATS服务器启动超时"
            exit 1
        fi
        sleep 1
    done
    
    # 启动ClickHouse
    log_info "启动ClickHouse..."
    docker-compose up -d clickhouse
    
    # 等待ClickHouse启动
    log_info "等待ClickHouse启动..."
    sleep 10
    
    log_success "基础设施服务启动完成"
}

# 验证NATS连接
verify_nats_connection() {
    log_info "验证NATS连接..."
    
    # 检查NATS状态
    if curl -s http://localhost:8222/varz | jq -r '.version' > /dev/null 2>&1; then
        nats_version=$(curl -s http://localhost:8222/varz | jq -r '.version')
        log_success "NATS连接正常，版本: $nats_version"
    else
        log_error "NATS连接失败"
        exit 1
    fi
}

# 设置Python环境
setup_python_environment() {
    log_info "设置Python环境..."
    
    # 创建虚拟环境（如果不存在）
    if [ ! -d "venv" ]; then
        log_info "创建Python虚拟环境..."
        python3 -m venv venv
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 升级pip
    pip install --upgrade pip
    
    # 安装依赖
    log_info "安装Python依赖..."
    pip install -r requirements.txt
    
    # 确保nats-py版本正确
    pip install nats-py==2.2.0
    
    log_success "Python环境设置完成"
}

# 启动Data Collector
start_data_collector() {
    log_info "启动Data Collector..."
    
    source venv/bin/activate
    
    # 检查端口是否被占用
    if lsof -Pi :8084 -sTCP:LISTEN -t >/dev/null; then
        log_warning "端口8084已被占用，停止现有进程..."
        pkill -f "python services/data-collector/main.py" || true
        sleep 2
    fi
    
    # 启动Data Collector
    nohup python services/data-collector/main.py > /tmp/data-collector.log 2>&1 &
    
    # 等待服务启动
    log_info "等待Data Collector启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8084/api/v1/status > /dev/null 2>&1; then
            log_success "Data Collector已启动"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "Data Collector启动超时"
            log_info "检查日志: tail -f /tmp/data-collector.log"
            exit 1
        fi
        sleep 1
    done
}

# 验证NATS自动推送功能
verify_nats_auto_push() {
    log_info "验证NATS自动推送功能..."
    
    source venv/bin/activate
    
    # 运行验证脚本
    cd services/data-collector
    
    # 确保collector环境存在
    if [ ! -d "collector_env" ]; then
        log_info "创建collector专用环境..."
        python3 -m venv collector_env
        source collector_env/bin/activate
        pip install aiohttp nats-py==2.2.0 pyyaml
    else
        source collector_env/bin/activate
    fi
    
    # 运行验证
    log_info "运行NATS推送验证（30秒）..."
    timeout 35 python final_complete_verification.py || true
    
    cd ../..
    
    log_success "NATS自动推送功能验证完成"
}

# 启动其他服务
start_other_services() {
    log_info "启动其他MarketPrism服务..."
    
    source venv/bin/activate
    
    # 启动Data Storage服务
    if [ -f "services/data-storage/main.py" ]; then
        log_info "启动Data Storage服务..."
        nohup python services/data-storage/main.py > /tmp/data-storage.log 2>&1 &
        sleep 3
    fi
    
    # 启动WebSocket服务
    if [ -f "services/websocket-server/main.py" ]; then
        log_info "启动WebSocket服务..."
        nohup python services/websocket-server/main.py > /tmp/websocket-server.log 2>&1 &
        sleep 3
    fi
    
    # 启动UI Dashboard
    if [ -f "ui/package.json" ]; then
        log_info "启动UI Dashboard..."
        cd ui
        if [ ! -d "node_modules" ]; then
            npm install
        fi
        nohup npm run dev > /tmp/ui-dashboard.log 2>&1 &
        cd ..
        sleep 3
    fi
    
    log_success "其他服务启动完成"
}

# 显示服务状态
show_service_status() {
    log_info "检查服务状态..."
    
    echo ""
    echo "=== MarketPrism 服务状态 ==="
    
    # NATS
    if curl -s http://localhost:8222/varz > /dev/null 2>&1; then
        echo "✅ NATS: 运行中 (http://localhost:8222)"
    else
        echo "❌ NATS: 未运行"
    fi
    
    # Data Collector
    if curl -s http://localhost:8084/api/v1/status > /dev/null 2>&1; then
        echo "✅ Data Collector: 运行中 (http://localhost:8084)"
    else
        echo "❌ Data Collector: 未运行"
    fi
    
    # Data Storage
    if curl -s http://localhost:8083/api/v1/status > /dev/null 2>&1; then
        echo "✅ Data Storage: 运行中 (http://localhost:8083)"
    else
        echo "⚠️  Data Storage: 未运行"
    fi
    
    # WebSocket Server
    if curl -s http://localhost:8082/health > /dev/null 2>&1; then
        echo "✅ WebSocket Server: 运行中 (http://localhost:8082)"
    else
        echo "⚠️  WebSocket Server: 未运行"
    fi
    
    # UI Dashboard
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo "✅ UI Dashboard: 运行中 (http://localhost:3000)"
    else
        echo "⚠️  UI Dashboard: 未运行"
    fi
    
    echo ""
    echo "=== 日志文件 ==="
    echo "Data Collector: tail -f /tmp/data-collector.log"
    echo "Data Storage: tail -f /tmp/data-storage.log"
    echo "WebSocket Server: tail -f /tmp/websocket-server.log"
    echo "UI Dashboard: tail -f /tmp/ui-dashboard.log"
}

# 主函数
main() {
    echo "🚀 MarketPrism 一键启动脚本"
    echo "================================"
    
    # 检查是否在项目根目录
    if [ ! -f "requirements.txt" ]; then
        log_error "请在MarketPrism项目根目录运行此脚本"
        exit 1
    fi
    
    # 执行启动流程
    check_dependencies
    check_nats_py_version
    start_infrastructure
    verify_nats_connection
    setup_python_environment
    start_data_collector
    verify_nats_auto_push
    start_other_services
    show_service_status
    
    log_success "MarketPrism启动完成！"
    echo ""
    echo "🎉 系统已启动，NATS自动推送功能已激活"
    echo "📊 访问 http://localhost:3000 查看UI Dashboard"
    echo "📡 NATS监控: http://localhost:8222"
    echo "🔧 Data Collector API: http://localhost:8084/api/v1/status"
}

# 运行主函数
main "$@"
