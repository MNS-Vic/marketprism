#!/usr/bin/env bash

# MarketPrism 快速启动测试脚本
# 快速检测：1.启动正确性 2.功能性 3.冗余检测

# 确保使用bash 4.0+
if [ "${BASH_VERSION%%.*}" -lt 4 ]; then
    echo "需要 bash 4.0 或更高版本"
    exit 1
fi

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo "=================================================="
echo -e "${PURPLE}🧪 MarketPrism 快速启动测试${NC}"
echo "=================================================="

# 获取项目根目录
PROJECT_ROOT=$(pwd)
TOTAL_SERVICES=6
STARTED_SERVICES=0
HEALTHY_SERVICES=0

# 服务配置
declare -A SERVICES
SERVICES[api-gateway]=8080
SERVICES[data-collector]=8081
SERVICES[data-storage]=8082
SERVICES[monitoring]=8083
SERVICES[scheduler]=8084
SERVICES[message-broker]=8085

# 临时存储PID
PIDS=()

# 清理函数
cleanup() {
    echo -e "\n${YELLOW}🧹 清理测试进程...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 $pid 2>/dev/null; then
            kill $pid 2>/dev/null || true
            echo "  停止进程 $pid"
        fi
    done
    
    # 额外清理
    pkill -f "start-.*\.sh" 2>/dev/null || true
    sleep 2
}

# 设置信号处理
trap cleanup EXIT INT TERM

# 检查端口是否被占用
is_port_occupied() {
    lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1
}

# 等待服务启动
wait_for_service() {
    local port=$1
    local timeout=${2:-15}
    local count=0
    
    while [ $count -lt $timeout ]; do
        if is_port_occupied $port; then
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    return 1
}

# 测试API端点
test_endpoint() {
    local url=$1
    curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null
}

echo -e "${BLUE}📋 第一阶段: 启动正确性测试${NC}"
echo ""

# 清理现有进程
for service in "${!SERVICES[@]}"; do
    port=${SERVICES[$service]}
    if is_port_occupied $port; then
        echo -e "${YELLOW}  清理端口 $port 上的现有进程${NC}"
        pkill -f "$service" 2>/dev/null || true
    fi
done

sleep 2

# 启动所有服务
for service in "${!SERVICES[@]}"; do
    port=${SERVICES[$service]}
    script="start-$service.sh"
    
    if [ ! -f "$script" ]; then
        echo -e "${RED}  ❌ $service: 启动脚本不存在${NC}"
        continue
    fi
    
    echo -e "${BLUE}  🚀 启动 $service (端口: $port)...${NC}"
    
    # 后台启动服务
    ./$script > /dev/null 2>&1 &
    local pid=$!
    PIDS+=($pid)
    
    # 等待服务启动
    if wait_for_service $port 15; then
        echo -e "${GREEN}    ✅ $service 启动成功${NC}"
        STARTED_SERVICES=$((STARTED_SERVICES + 1))
    else
        echo -e "${RED}    ❌ $service 启动失败${NC}"
    fi
done

echo ""
echo -e "${BLUE}📋 第二阶段: 功能正常性测试${NC}"
echo ""

# 测试服务功能
for service in "${!SERVICES[@]}"; do
    port=${SERVICES[$service]}
    
    if ! is_port_occupied $port; then
        echo -e "${RED}  ❌ $service: 服务未运行${NC}"
        continue
    fi
    
    echo -e "${BLUE}  🔍 测试 $service 功能...${NC}"
    
    # 测试健康检查
    health_status=$(test_endpoint "http://localhost:$port/health")
    if [ "$health_status" = "200" ]; then
        echo -e "${GREEN}    ✅ 健康检查: 正常${NC}"
        HEALTHY_SERVICES=$((HEALTHY_SERVICES + 1))
        
        # 测试Prometheus指标
        metrics_status=$(test_endpoint "http://localhost:$port/metrics")
        if [ "$metrics_status" = "200" ]; then
            echo -e "${GREEN}    ✅ Prometheus指标: 正常${NC}"
        else
            echo -e "${YELLOW}    ⚠️  Prometheus指标: 异常${NC}"
        fi
        
    else
        echo -e "${RED}    ❌ 健康检查: 失败 (状态码: $health_status)${NC}"
    fi
done

echo ""
echo -e "${BLUE}📋 第三阶段: 冗余检测测试${NC}"
echo ""

# 检查重复的启动脚本
echo -e "${BLUE}  🔍 检查脚本冗余...${NC}"

duplicate_scripts=0
if [ -f "scripts/service-launchers/start-api-gateway.sh" ] && [ -f "start-api-gateway.sh" ]; then
    echo -e "${YELLOW}    ⚠️  发现重复的API Gateway启动脚本${NC}"
    duplicate_scripts=$((duplicate_scripts + 1))
fi

# 检查端口冲突
echo -e "${BLUE}  🔍 检查端口配置...${NC}"
port_conflicts=0
used_ports=()
for port in "${SERVICES[@]}"; do
    if [[ " ${used_ports[@]} " =~ " ${port} " ]]; then
        echo -e "${RED}    ❌ 端口冲突: $port${NC}"
        port_conflicts=$((port_conflicts + 1))
    else
        used_ports+=($port)
    fi
done

if [ $port_conflicts -eq 0 ]; then
    echo -e "${GREEN}    ✅ 端口配置: 无冲突${NC}"
fi

# 检查进程内存使用
echo -e "${BLUE}  🔍 检查内存使用...${NC}"
total_memory=0
for pid in "${PIDS[@]}"; do
    if kill -0 $pid 2>/dev/null; then
        memory=$(ps -o rss= -p $pid 2>/dev/null | awk '{print $1/1024}' || echo 0)
        total_memory=$(echo "$total_memory + $memory" | bc -l 2>/dev/null || echo $total_memory)
    fi
done

echo -e "${GREEN}    📊 总内存使用: ${total_memory}MB${NC}"

# 检查未使用的配置文件
echo -e "${BLUE}  🔍 检查配置文件...${NC}"
unused_configs=0

if [ -f "config/unused_config.yaml" ]; then
    echo -e "${YELLOW}    ⚠️  发现未使用的配置文件${NC}"
    unused_configs=$((unused_configs + 1))
fi

# 检查日志文件
log_files=$(find logs -name "*.log" 2>/dev/null | wc -l || echo 0)
if [ $log_files -gt 20 ]; then
    echo -e "${YELLOW}    ⚠️  日志文件过多 ($log_files 个)，建议清理${NC}"
fi

echo ""
echo "=================================================="
echo -e "${PURPLE}🎯 测试结果汇总${NC}"
echo "=================================================="

# 启动成功率
startup_rate=$((STARTED_SERVICES * 100 / TOTAL_SERVICES))
health_rate=$((HEALTHY_SERVICES * 100 / TOTAL_SERVICES))

echo -e "${BLUE}📊 启动测试:${NC}"
echo "  总服务数: $TOTAL_SERVICES"
echo "  启动成功: $STARTED_SERVICES ($startup_rate%)"
echo ""

echo -e "${BLUE}🔧 功能测试:${NC}"
echo "  健康检查通过: $HEALTHY_SERVICES ($health_rate%)"
echo ""

echo -e "${BLUE}🔍 冗余检测:${NC}"
echo "  重复脚本: $duplicate_scripts"
echo "  端口冲突: $port_conflicts"
echo "  未使用配置: $unused_configs"
echo "  总内存使用: ${total_memory}MB"
echo ""

# 生成建议
echo -e "${BLUE}💡 建议:${NC}"
if [ $startup_rate -lt 100 ]; then
    echo "  • 有服务启动失败，检查依赖和配置"
fi

if [ $health_rate -lt 100 ]; then
    echo "  • 有服务功能异常，检查API端点"
fi

if [ $duplicate_scripts -gt 0 ]; then
    echo "  • 清理重复的启动脚本"
fi

if [ $port_conflicts -gt 0 ]; then
    echo "  • 解决端口冲突配置"
fi

if [ $log_files -gt 20 ]; then
    echo "  • 定期清理日志文件"
fi

if [[ $(echo "$total_memory > 500" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
    echo "  • 监控内存使用，考虑优化"
fi

echo ""

# 总体评分
total_score=0
if [ $startup_rate -eq 100 ]; then total_score=$((total_score + 40)); fi
if [ $health_rate -eq 100 ]; then total_score=$((total_score + 40)); fi
if [ $duplicate_scripts -eq 0 ]; then total_score=$((total_score + 5)); fi
if [ $port_conflicts -eq 0 ]; then total_score=$((total_score + 5)); fi
if [ $unused_configs -eq 0 ]; then total_score=$((total_score + 5)); fi
if [[ $(echo "$total_memory < 300" | bc -l 2>/dev/null || echo 1) -eq 1 ]]; then total_score=$((total_score + 5)); fi

echo -e "${PURPLE}🏆 总体评分: $total_score/100${NC}"

if [ $total_score -ge 90 ]; then
    echo -e "${GREEN}🎉 优秀！系统运行状态良好${NC}"
elif [ $total_score -ge 70 ]; then
    echo -e "${YELLOW}⚠️  良好，有少量问题需要处理${NC}"
else
    echo -e "${RED}❌ 需要改进，存在多个问题${NC}"
fi

echo "=================================================="

# 返回适当的退出码
if [ $startup_rate -eq 100 ] && [ $health_rate -eq 100 ]; then
    exit 0
else
    exit 1
fi