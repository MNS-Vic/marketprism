#!/bin/bash

# MarketPrism 快速健康检查脚本
# 验证最近测试中发现的问题是否已修复

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=================================================="
echo -e "${BLUE}🔍 MarketPrism 快速健康检查${NC}"
echo "=================================================="

PROJECT_ROOT=$(pwd)
ISSUES_FOUND=0
ISSUES_FIXED=0

# 检查函数
check_issue() {
    local description="$1"
    local check_command="$2"
    local expected_result="$3"
    
    echo -e "${YELLOW}检查: $description${NC}"
    
    if eval "$check_command"; then
        if [ "$expected_result" = "success" ]; then
            echo -e "${GREEN}✅ 已修复${NC}"
            ISSUES_FIXED=$((ISSUES_FIXED + 1))
        else
            echo -e "${RED}❌ 仍存在问题${NC}"
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        fi
    else
        if [ "$expected_result" = "fail" ]; then
            echo -e "${GREEN}✅ 已修复${NC}"
            ISSUES_FIXED=$((ISSUES_FIXED + 1))
        else
            echo -e "${RED}❌ 仍存在问题${NC}"
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        fi
    fi
    echo ""
}

echo -e "${BLUE}📋 检查已知问题修复状态...${NC}"
echo ""

# 1. 检查调度器服务的metrics.counter问题
check_issue "调度器服务 metrics.counter 方法修复" \
    "grep -q 'self.metrics.increment' services/scheduler-service/main.py" \
    "success"

# 2. 检查调度器服务的ServiceRegistry.register_service API兼容性
check_issue "调度器服务 ServiceRegistry API 兼容性" \
    "grep -q 'service_info=' services/scheduler-service/main.py" \
    "success"

# 3. 检查市场数据收集器启动脚本路径检测
check_issue "市场数据收集器启动脚本路径检测增强" \
    "grep -q '../../../services/data-collector/main.py' scripts/service-launchers/start-market-data-collector.sh" \
    "success"

# 4. 检查UnifiedMetricsManager的counter方法是否存在
check_issue "UnifiedMetricsManager increment 方法可用性" \
    "grep -q 'def increment' core/observability/metrics/unified_metrics_manager.py" \
    "success"

# 5. 检查服务注册表的register_service方法签名
check_issue "ServiceRegistry register_service 方法签名" \
    "grep -A5 'def register_service' services/service_registry.py | grep -q 'service_info'" \
    "success"

# 6. 检查配置文件存在性
check_issue "核心配置文件存在性" \
    "[ -f config/services.yaml ] && [ -f config/collector.yaml ]" \
    "success"

# 7. 检查Python虚拟环境
check_issue "Python虚拟环境可用性" \
    "[ -d venv ] && [ -f venv/bin/activate ]" \
    "success"

# 8. 检查核心服务框架
check_issue "核心服务框架完整性" \
    "[ -f core/service_framework.py ] && [ -f core/service_discovery/registry.py ]" \
    "success"

echo "=================================================="
echo -e "${BLUE}📊 检查结果汇总${NC}"
echo "=================================================="
echo -e "${GREEN}✅ 已修复问题: $ISSUES_FIXED${NC}"
echo -e "${RED}❌ 仍存在问题: $ISSUES_FOUND${NC}"

if [ $ISSUES_FOUND -eq 0 ]; then
    echo ""
    echo -e "${GREEN}🎉 所有已知问题都已修复！${NC}"
    echo -e "${BLUE}💡 建议运行完整的服务启动测试验证修复效果${NC}"
    exit 0
else
    echo ""
    echo -e "${YELLOW}⚠️  仍有 $ISSUES_FOUND 个问题需要解决${NC}"
    exit 1
fi