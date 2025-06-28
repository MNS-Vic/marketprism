#!/bin/bash

# MarketPrism 部署验证脚本
# 验证所有服务的运行状态和数据流完整性

echo "🚀 MarketPrism 部署验证开始..."
echo "=================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 验证函数
check_service() {
    local service_name=$1
    local port=$2
    local endpoint=${3:-"/health"}
    
    echo -n "检查 $service_name ($port): "
    
    if curl -s -f "http://localhost:$port$endpoint" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 正常${NC}"
        return 0
    else
        echo -e "${RED}❌ 异常${NC}"
        return 1
    fi
}

# 验证数据库连接
check_database() {
    local db_name=$1
    local port=$2
    local endpoint=${3:-"/ping"}
    
    echo -n "检查 $db_name ($port): "
    
    if curl -s -f "http://localhost:$port$endpoint" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 正常${NC}"
        return 0
    else
        echo -e "${RED}❌ 异常${NC}"
        return 1
    fi
}

# 验证容器状态
check_containers() {
    echo ""
    echo "📦 Docker容器状态检查:"
    echo "------------------------"
    
    containers=(
        "marketprism-api-gateway"
        "marketprism-monitoring-alerting"
        "marketprism-data-storage"
        "marketprism-market-data-collector"
        "marketprism-scheduler"
        "marketprism-message-broker"
        "marketprism-clickhouse"
        "marketprism-postgres"
        "marketprism-redis"
        "marketprism-nats"
        "marketprism-prometheus"
    )
    
    for container in "${containers[@]}"; do
        if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$container.*healthy\|$container.*Up"; then
            echo -e "$container: ${GREEN}✅ 运行中${NC}"
        else
            echo -e "$container: ${RED}❌ 异常${NC}"
        fi
    done
}

# 验证核心服务
echo ""
echo "🔧 核心服务健康检查:"
echo "--------------------"

services_ok=0
total_services=6

check_service "API网关" "8080" && ((services_ok++))
check_service "监控告警" "8082" && ((services_ok++))
check_service "数据存储" "8083" && ((services_ok++))
check_service "数据收集器" "8084" && ((services_ok++))
check_service "调度器" "8085" && ((services_ok++))
check_service "消息代理" "8086" && ((services_ok++))

# 验证基础设施
echo ""
echo "🏗️ 基础设施检查:"
echo "----------------"

infra_ok=0
total_infra=4

check_database "ClickHouse" "8123" "/ping" && ((infra_ok++))
check_database "Prometheus" "9090" "/-/healthy" && ((infra_ok++))

# PostgreSQL检查
echo -n "检查 PostgreSQL (5432): "
if docker exec marketprism-postgres pg_isready -U marketprism > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 正常${NC}"
    ((infra_ok++))
else
    echo -e "${RED}❌ 异常${NC}"
fi

# Redis检查
echo -n "检查 Redis (6379): "
if docker exec marketprism-redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 正常${NC}"
    ((infra_ok++))
else
    echo -e "${RED}❌ 异常${NC}"
fi

# 验证UI仪表板
echo ""
echo "🎨 UI仪表板检查:"
echo "---------------"
check_service "UI仪表板" "3000" "/"

# 验证数据流
echo ""
echo "📊 数据流验证:"
echo "-------------"

# 检查数据收集器统计
echo -n "数据收集器统计: "
if collector_stats=$(curl -s "http://localhost:8084/api/v1/collector/stats" 2>/dev/null); then
    echo -e "${GREEN}✅ 可访问${NC}"
    echo "  - REST请求: $(echo "$collector_stats" | jq -r '.rest_requests // "N/A"')"
    echo "  - WebSocket消息: $(echo "$collector_stats" | jq -r '.websocket_messages // "N/A"')"
    echo "  - 错误数: $(echo "$collector_stats" | jq -r '.errors // "N/A"')"
else
    echo -e "${RED}❌ 无法访问${NC}"
fi

# 检查ClickHouse表
echo -n "ClickHouse表结构: "
if tables=$(curl -s "http://localhost:8123/" --data-binary "SHOW TABLES FROM marketprism" 2>/dev/null); then
    echo -e "${GREEN}✅ 正常${NC}"
    echo "  表列表: $tables"
else
    echo -e "${RED}❌ 异常${NC}"
fi

# 容器状态检查
check_containers

# 生成报告
echo ""
echo "📋 验证报告:"
echo "============"
echo "核心服务: $services_ok/$total_services 正常"
echo "基础设施: $infra_ok/$total_infra 正常"

if [ $services_ok -eq $total_services ] && [ $infra_ok -eq $total_infra ]; then
    echo -e "${GREEN}🎉 系统部署验证通过！所有服务正常运行。${NC}"
    exit 0
elif [ $services_ok -ge 4 ] && [ $infra_ok -ge 2 ]; then
    echo -e "${YELLOW}⚠️  系统基本可用，但有部分服务异常，建议检查。${NC}"
    exit 1
else
    echo -e "${RED}❌ 系统部署验证失败，多个关键服务异常。${NC}"
    exit 2
fi
