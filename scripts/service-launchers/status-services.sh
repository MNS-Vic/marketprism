#!/bin/bash

# MarketPrism 微服务状态检查脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 脚本信息
echo "=================================================="
echo -e "${PURPLE}📊 MarketPrism 微服务状态检查${NC}"
echo "=================================================="

# 服务列表和端口
declare -A SERVICES
SERVICES[api-gateway-service]=8080
SERVICES[market-data-collector]=8081
SERVICES[data-storage-service]=8082
SERVICES[monitoring-service]=8083
SERVICES[scheduler-service]=8084
SERVICES[message-broker-service]=8085

# 检查端口函数
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # 端口被占用
    else
        return 1  # 端口空闲
    fi
}

# 检查健康状态
check_health() {
    local port=$1
    local health_url="http://localhost:$port/health"
    
    if command -v curl >/dev/null 2>&1; then
        local status_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$health_url" 2>/dev/null)
        if [ "$status_code" = "200" ]; then
            return 0  # 健康
        else
            return 1  # 不健康
        fi
    else
        return 2  # 无法检查
    fi
}

# 获取进程信息
get_process_info() {
    local service_name=$1
    local pid_file="data/pids/${service_name}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo "$pid"
        else
            echo "stopped"
        fi
    else
        echo "unknown"
    fi
}

# 获取内存使用情况
get_memory_usage() {
    local pid=$1
    if [ "$pid" != "stopped" ] && [ "$pid" != "unknown" ] && ps -p $pid > /dev/null 2>&1; then
        local memory=$(ps -o rss= -p $pid 2>/dev/null | awk '{print $1/1024}')
        printf "%.1f MB" $memory
    else
        echo "N/A"
    fi
}

# 获取运行时间
get_uptime() {
    local pid=$1
    if [ "$pid" != "stopped" ] && [ "$pid" != "unknown" ] && ps -p $pid > /dev/null 2>&1; then
        local uptime=$(ps -o etime= -p $pid 2>/dev/null | xargs)
        echo "$uptime"
    else
        echo "N/A"
    fi
}

echo ""
printf "%-25s %-8s %-8s %-12s %-12s %-12s %-12s\n" "服务名称" "端口" "状态" "健康检查" "PID" "内存使用" "运行时间"
echo "=================================================================================================================="

running_count=0
total_count=0

for service in api-gateway-service market-data-collector data-storage-service monitoring-service scheduler-service message-broker-service; do
    port=${SERVICES[$service]}
    total_count=$((total_count + 1))
    
    # 检查端口状态
    if check_port $port; then
        status="${GREEN}运行中${NC}"
        running_count=$((running_count + 1))
        
        # 检查健康状态
        check_health $port
        health_status=$?
        case $health_status in
            0) health="${GREEN}健康${NC}" ;;
            1) health="${YELLOW}异常${NC}" ;;
            2) health="${BLUE}未知${NC}" ;;
        esac
    else
        status="${RED}停止${NC}"
        health="${RED}N/A${NC}"
    fi
    
    # 获取进程信息
    pid=$(get_process_info "$service")
    memory=$(get_memory_usage "$pid")
    uptime=$(get_uptime "$pid")
    
    printf "%-25s %-8s %-8s %-12s %-12s %-12s %-12s\n" \
        "$service" \
        "$port" \
        "$(echo -e $status)" \
        "$(echo -e $health)" \
        "$pid" \
        "$memory" \
        "$uptime"
done

echo ""
echo "=================================================="
echo -e "${BLUE}运行统计: $running_count/$total_count 服务运行中${NC}"

if [ $running_count -eq $total_count ]; then
    echo -e "${GREEN}🎉 所有服务运行正常！${NC}"
elif [ $running_count -eq 0 ]; then
    echo -e "${RED}❌ 所有服务都已停止${NC}"
else
    echo -e "${YELLOW}⚠️  部分服务未运行${NC}"
fi

echo ""
echo -e "${CYAN}💡 管理命令:${NC}"
echo "  启动所有服务: ./scripts/service-launchers/start-all-services.sh"
echo "  停止所有服务: ./scripts/service-launchers/stop-services.sh"
echo "  启动单个服务: ./scripts/service-launchers/start-service.sh"
echo "  查看服务日志: tail -f logs/[service-name]-*.log"
echo ""

# 如果有服务运行，显示访问信息
if [ $running_count -gt 0 ]; then
    echo -e "${CYAN}🌐 访问端点:${NC}"
    for service in api-gateway-service market-data-collector data-storage-service monitoring-service scheduler-service message-broker-service; do
        port=${SERVICES[$service]}
        if check_port $port; then
            echo "  $service: http://localhost:$port"
        fi
    done
    echo ""
fi

echo "=================================================="