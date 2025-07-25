#!/bin/bash

# MarketPrism 微服务停止脚本

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
echo -e "${PURPLE}🛑 MarketPrism 微服务停止器${NC}"
echo "=================================================="

# 服务列表和端口
declare -A SERVICES
SERVICES[api-gateway-service]=8080
SERVICES[market-data-collector]=8081
SERVICES[data-storage-service]=8082
SERVICES[monitoring-service]=8083
SERVICES[scheduler-service]=8084
SERVICES[message-broker-service]=8085

# 停止顺序（与启动相反）
STOP_ORDER=(
    "api-gateway-service"
    "scheduler-service"
    "market-data-collector"
    "monitoring-service"
    "data-storage-service"
    "message-broker-service"
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

# 停止服务函数
stop_service() {
    local service_name=$1
    local port=${SERVICES[$service_name]}
    local pid_file="data/pids/${service_name}.pid"
    
    log_info "停止 $service_name (端口: $port)..."
    
    local stopped=false
    
    # 方法1: 使用PID文件
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            log_info "使用PID文件停止进程 $pid"
            kill $pid 2>/dev/null
            
            # 等待进程终止
            local count=0
            while [ $count -lt 10 ] && ps -p $pid > /dev/null 2>&1; do
                sleep 1
                count=$((count + 1))
            done
            
            if ! ps -p $pid > /dev/null 2>&1; then
                log_success "$service_name 已停止"
                rm -f "$pid_file"
                stopped=true
            else
                log_warning "进程 $pid 未响应TERM信号，尝试强制终止"
                kill -9 $pid 2>/dev/null
                rm -f "$pid_file"
                stopped=true
            fi
        else
            log_warning "PID文件存在但进程已不存在"
            rm -f "$pid_file"
        fi
    fi
    
    # 方法2: 通过进程名查找
    if [ "$stopped" = false ]; then
        local pids=$(pgrep -f "$service_name" 2>/dev/null)
        if [ -n "$pids" ]; then
            log_info "通过进程名停止 $service_name"
            echo "$pids" | xargs kill 2>/dev/null
            sleep 2
            
            # 检查是否还有进程
            local remaining_pids=$(pgrep -f "$service_name" 2>/dev/null)
            if [ -n "$remaining_pids" ]; then
                log_warning "强制终止剩余进程"
                echo "$remaining_pids" | xargs kill -9 2>/dev/null
            fi
            stopped=true
        fi
    fi
    
    # 方法3: 通过端口查找进程
    if [ "$stopped" = false ] && check_port $port; then
        local port_pid=$(lsof -ti:$port 2>/dev/null)
        if [ -n "$port_pid" ]; then
            log_info "通过端口停止进程 $port_pid"
            kill $port_pid 2>/dev/null
            sleep 2
            
            if check_port $port; then
                kill -9 $port_pid 2>/dev/null
            fi
            stopped=true
        fi
    fi
    
    # 验证服务是否已停止
    if ! check_port $port; then
        log_success "$service_name 已完全停止"
        return 0
    else
        log_error "$service_name 停止失败"
        return 1
    fi
}

# 检查是否有服务在运行
running_services=()
for service in "${!SERVICES[@]}"; do
    port=${SERVICES[$service]}
    if check_port $port; then
        running_services+=("$service")
    fi
done

if [ ${#running_services[@]} -eq 0 ]; then
    log_info "没有检测到运行中的MarketPrism服务"
    echo ""
    echo "=================================================="
    exit 0
fi

log_info "检测到 ${#running_services[@]} 个运行中的服务"
echo ""

# 按顺序停止服务
stopped_count=0
failed_services=()

for service in "${STOP_ORDER[@]}"; do
    port=${SERVICES[$service]}
    if check_port $port; then
        if stop_service "$service"; then
            stopped_count=$((stopped_count + 1))
            # 服务间停止间隔
            sleep 1
        else
            failed_services+=("$service")
        fi
        echo ""
    fi
done

# 停止结果汇总
echo "=================================================="
echo -e "${PURPLE}📊 停止结果汇总${NC}"
echo "=================================================="

total_running=${#running_services[@]}
echo -e "${BLUE}需要停止的服务: $total_running${NC}"
echo -e "${GREEN}成功停止的服务: $stopped_count${NC}"

if [ ${#failed_services[@]} -gt 0 ]; then
    echo -e "${RED}停止失败的服务: ${failed_services[*]}${NC}"
else
    echo -e "${GREEN}🎉 所有服务已成功停止！${NC}"
fi

echo ""

# 清理工作
log_info "清理残留文件..."

# 清理PID文件
if [ -d "data/pids" ]; then
    for pid_file in data/pids/*.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file" 2>/dev/null)
            if [ -n "$pid" ] && ! ps -p $pid > /dev/null 2>&1; then
                rm -f "$pid_file"
                log_info "清理无效PID文件: $(basename $pid_file)"
            fi
        fi
    done
fi

# 最终状态检查
echo ""
echo "=================================================="
echo -e "${CYAN}🔍 最终状态检查${NC}"
echo "=================================================="

any_still_running=false
for service in "${!SERVICES[@]}"; do
    port=${SERVICES[$service]}
    if check_port $port; then
        echo -e "${RED}❌ $service${NC} - 仍在运行 (端口: $port)"
        any_still_running=true
    else
        echo -e "${GREEN}✅ $service${NC} - 已停止"
    fi
done

echo ""
if [ "$any_still_running" = false ]; then
    echo -e "${GREEN}🎉 所有MarketPrism服务已完全停止！${NC}"
else
    echo -e "${YELLOW}⚠️  部分服务可能需要手动处理${NC}"
    echo ""
    echo -e "${CYAN}💡 手动清理命令:${NC}"
    echo "  pkill -f marketprism"
    echo "  pkill -f 'python.*main.py'"
fi

echo ""
echo "=================================================="