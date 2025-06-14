#!/bin/bash

# MarketPrism 微服务后台批量启动脚本
# 适用于生产环境部署，所有服务后台运行

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
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

# 脚本信息
echo "=================================================="
echo -e "${PURPLE}🚀 MarketPrism 微服务批量启动器 (后台模式)${NC}"
echo "=================================================="

# 检测项目根目录
if [ ! -f "config/services.yaml" ]; then
    log_error "请在项目根目录中运行此脚本"
    exit 1
fi

PROJECT_ROOT=$(pwd)
log_info "项目根目录: $PROJECT_ROOT"

# 创建PID文件目录
mkdir -p data/pids
mkdir -p logs

# 服务列表和端口
declare -A SERVICES
SERVICES[api-gateway-service]=8080
SERVICES[market-data-collector]=8081
SERVICES[data-storage-service]=8082
SERVICES[monitoring-service]=8083
SERVICES[scheduler-service]=8084
SERVICES[message-broker-service]=8085

# 启动顺序（按依赖关系）
START_ORDER=(
    "message-broker-service"
    "data-storage-service"
    "monitoring-service"
    "market-data-collector"
    "scheduler-service"
    "api-gateway-service"
)

# 检查端口函数
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # 端口被占用
    else
        return 1  # 端口空闲
    fi
}

# 停止现有服务
log_info "检查并停止现有服务..."
for service in "${!SERVICES[@]}"; do
    port=${SERVICES[$service]}
    if check_port $port; then
        log_warning "端口 $port 已被占用，停止相关进程..."
        pkill -f "$service" || true
        sleep 1
    fi
done

# 等待端口释放
sleep 3

# 启动服务函数
start_service() {
    local service_name=$1
    local port=${SERVICES[$service_name]}
    
    log_info "启动 $service_name (端口: $port)..."
    
    # 检查服务目录是否存在
    if [ ! -d "services/$service_name" ]; then
        log_error "服务目录不存在: services/$service_name"
        return 1
    fi
    
    # 检查main.py是否存在
    if [ ! -f "services/$service_name/main.py" ]; then
        log_error "服务主文件不存在: services/$service_name/main.py"
        return 1
    fi
    
    # 启动服务（后台）
    cd "services/$service_name"
    nohup python3 main.py > "../../logs/${service_name}-$(date +%Y%m%d_%H%M%S).log" 2>&1 &
    local pid=$!
    
    # 保存PID
    echo $pid > "../../data/pids/${service_name}.pid"
    
    cd "$PROJECT_ROOT"
    
    # 等待服务启动
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if check_port $port; then
            log_success "$service_name 启动成功 (PID: $pid, 端口: $port)"
            return 0
        fi
        
        attempt=$((attempt + 1))
        sleep 1
    done
    
    log_error "$service_name 启动失败"
    return 1
}

# 检查虚拟环境
if [ ! -d "venv" ]; then
    log_info "创建 Python 虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate
log_success "虚拟环境已激活"

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export MARKETPRISM_ENV="${MARKETPRISM_ENV:-production}"
export MARKETPRISM_LOG_LEVEL="${MARKETPRISM_LOG_LEVEL:-INFO}"

log_info "环境变量设置："
log_info "  MARKETPRISM_ENV: $MARKETPRISM_ENV"
log_info "  MARKETPRISM_LOG_LEVEL: $MARKETPRISM_LOG_LEVEL"

# 按顺序启动服务
log_info "开始启动微服务..."
echo ""

failed_services=()

for service in "${START_ORDER[@]}"; do
    if start_service "$service"; then
        # 服务间启动间隔
        sleep 2
    else
        failed_services+=("$service")
    fi
    echo ""
done

# 启动结果汇总
echo "=================================================="
echo -e "${PURPLE}📊 启动结果汇总${NC}"
echo "=================================================="

successful_services=0
for service in "${START_ORDER[@]}"; do
    port=${SERVICES[$service]}
    if check_port $port; then
        echo -e "${GREEN}✅ $service${NC} - 运行中 (端口: $port)"
        successful_services=$((successful_services + 1))
    else
        echo -e "${RED}❌ $service${NC} - 启动失败"
    fi
done

echo ""
echo -e "${BLUE}成功启动服务: $successful_services/${#START_ORDER[@]}${NC}"

if [ ${#failed_services[@]} -gt 0 ]; then
    echo -e "${RED}失败服务: ${failed_services[*]}${NC}"
else
    echo -e "${GREEN}🎉 所有服务启动成功！${NC}"
fi

echo ""
echo "=================================================="
echo -e "${CYAN}🌟 服务访问信息${NC}"
echo "=================================================="
echo ""
echo -e "${BLUE}主要端点:${NC}"
echo "  API Gateway:     http://localhost:8080"
echo "  Data Collector:  http://localhost:8081"
echo "  Data Storage:    http://localhost:8082"
echo "  Monitoring:      http://localhost:8083"
echo "  Scheduler:       http://localhost:8084"
echo "  Message Broker:  http://localhost:8085"
echo ""
echo -e "${BLUE}健康检查:${NC}"
for service in "${START_ORDER[@]}"; do
    port=${SERVICES[$service]}
    echo "  $service: http://localhost:$port/health"
done
echo ""
echo -e "${BLUE}管理命令:${NC}"
echo "  查看状态: ./scripts/service-launchers/status-services.sh"
echo "  停止服务: ./scripts/service-launchers/stop-services.sh"
echo "  查看日志: tail -f logs/[service-name]-*.log"
echo ""
echo -e "${YELLOW}💡 提示: 服务已在后台运行，使用上述命令进行管理${NC}"
echo "=================================================="