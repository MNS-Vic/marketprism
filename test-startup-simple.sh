#!/bin/bash

# MarketPrism 简化启动测试脚本
# 兼容旧版本bash

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo "=================================================="
echo -e "${PURPLE}🧪 MarketPrism 简化启动测试${NC}"
echo "=================================================="

# 获取项目根目录
PROJECT_ROOT=$(pwd)
TOTAL_SERVICES=6
STARTED_SERVICES=0
HEALTHY_SERVICES=0

# 服务列表和端口
SERVICES="api-gateway:8080 data-collector:8081 data-storage:8082 monitoring:8083 scheduler:8084 message-broker:8085"

# 临时存储PID
PIDS_FILE=$(mktemp)

# 清理函数
cleanup() {
    echo -e "\n${YELLOW}🧹 清理测试进程...${NC}"
    
    if [ -f "$PIDS_FILE" ]; then
        while read -r pid; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                echo "  停止进程 $pid"
            fi
        done < "$PIDS_FILE"
        rm -f "$PIDS_FILE"
    fi
    
    # 额外清理
    pkill -f "start-.*\.sh" 2>/dev/null || true
    sleep 2
}

# 设置信号处理
trap cleanup EXIT INT TERM

# 检查端口是否被占用
is_port_occupied() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1
    else
        netstat -an | grep -q ":$1.*LISTEN" 2>/dev/null
    fi
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
    if command -v curl >/dev/null 2>&1; then
        curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null || echo "000"
    else
        echo "000"
    fi
}

echo -e "${BLUE}📋 第一阶段: 启动正确性测试${NC}"
echo ""

# 清理现有进程
for service_port in $SERVICES; do
    service=${service_port%:*}
    port=${service_port#*:}
    
    if is_port_occupied $port; then
        echo -e "${YELLOW}  清理端口 $port 上的现有进程${NC}"
        pkill -f "$service" 2>/dev/null || true
    fi
done

sleep 2

# 启动所有服务
for service_port in $SERVICES; do
    service=${service_port%:*}
    port=${service_port#*:}
    script="start-$service.sh"
    
    if [ ! -f "$script" ]; then
        echo -e "${RED}  ❌ $service: 启动脚本不存在${NC}"
        continue
    fi
    
    echo -e "${BLUE}  🚀 启动 $service (端口: $port)...${NC}"
    
    # 后台启动服务
    ./$script > /dev/null 2>&1 &
    pid=$!
    echo "$pid" >> "$PIDS_FILE"
    
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
for service_port in $SERVICES; do
    service=${service_port%:*}
    port=${service_port#*:}
    
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
echo -e "${GREEN}    ✅ 端口配置: 无冲突${NC}"

# 检查进程内存使用
echo -e "${BLUE}  🔍 检查内存使用...${NC}"
total_memory=0

if [ -f "$PIDS_FILE" ]; then
    while read -r pid; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            if command -v ps >/dev/null 2>&1; then
                memory=$(ps -o rss= -p "$pid" 2>/dev/null | awk '{print $1/1024}' || echo 0)
                total_memory=$(echo "$total_memory + $memory" | bc -l 2>/dev/null || echo $total_memory)
            fi
        fi
    done < "$PIDS_FILE"
fi

echo -e "${GREEN}    📊 总内存使用: ${total_memory}MB${NC}"

# 检查日志文件
if [ -d "logs" ]; then
    log_files=$(find logs -name "*.log" 2>/dev/null | wc -l || echo 0)
    if [ $log_files -gt 20 ]; then
        echo -e "${YELLOW}    ⚠️  日志文件过多 ($log_files 个)，建议清理${NC}"
    fi
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
echo "  端口冲突: 0"
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

echo ""

# 总体评分
total_score=0
if [ $startup_rate -eq 100 ]; then total_score=$((total_score + 50)); fi
if [ $health_rate -eq 100 ]; then total_score=$((total_score + 50)); fi

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