#!/bin/bash

# MarketPrism 配置验证脚本
# 用途：验证环境变量配置是否符合规范

set -e

echo "🔍 === MarketPrism 配置验证 ==="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 验证结果统计
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# 检查函数
check_var() {
    local var_name=$1
    local var_value="${!var_name}"
    local is_required=${2:-true}
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if [ -z "$var_value" ]; then
        if [ "$is_required" = true ]; then
            echo -e "${RED}❌ 缺少必需环境变量: $var_name${NC}"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
            return 1
        else
            echo -e "${YELLOW}⚠️  可选环境变量未设置: $var_name${NC}"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
            return 0
        fi
    else
        echo -e "${GREEN}✅ $var_name = $var_value${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    fi
}

# 检查MP_前缀规范
check_mp_prefix() {
    echo "📋 检查MP_前缀规范..."
    
    # 检查是否存在非MP_前缀的MarketPrism相关变量
    non_mp_vars=$(env | grep -E '^(NATS_URL|CLICKHOUSE_|API_PORT|DEV_MODE|ENVIRONMENT)=' | cut -d'=' -f1 || true)
    
    if [ -n "$non_mp_vars" ]; then
        echo -e "${YELLOW}⚠️  发现未使用MP_前缀的变量:${NC}"
        echo "$non_mp_vars" | while read -r var; do
            echo -e "${YELLOW}   - $var (建议重命名为 MP_${var})${NC}"
        done
        echo ""
    fi
}

# 核心系统配置检查
echo "🔧 检查核心系统配置..."
check_var "MP_ENVIRONMENT" true
check_var "MP_DEBUG" false
check_var "MP_LOG_LEVEL" false

# 服务端口配置检查
echo ""
echo "🌐 检查服务端口配置..."
check_var "MP_API_PORT" true
check_var "MP_METRICS_PORT" false
check_var "MP_HEALTH_PORT" false

# 基础设施配置检查
echo ""
echo "🏗️ 检查基础设施配置..."
check_var "MP_NATS_URL" true
check_var "MP_CLICKHOUSE_HOST" true
check_var "MP_CLICKHOUSE_PORT" false
check_var "MP_CLICKHOUSE_DATABASE" false

# 交易所API配置检查（可选）
echo ""
echo "💱 检查交易所API配置..."
check_var "MP_BINANCE_API_KEY" false
check_var "MP_BINANCE_SECRET" false
check_var "MP_OKX_API_KEY" false
check_var "MP_OKX_SECRET" false
check_var "MP_DERIBIT_API_KEY" false
check_var "MP_DERIBIT_SECRET" false

# 网络代理配置检查（可选）
echo ""
echo "🌍 检查网络代理配置..."
check_var "MP_HTTP_PROXY" false
check_var "MP_HTTPS_PROXY" false
check_var "MP_ALL_PROXY" false

# 检查MP_前缀规范
echo ""
check_mp_prefix

# 配置文件存在性检查
echo ""
echo "📁 检查配置文件..."
config_files=(
    "config/collector/collector.yaml"
    "config/nats_base.yaml"
    "docker/docker-compose.yml"
)

for file in "${config_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅ 配置文件存在: $file${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "${RED}❌ 配置文件缺失: $file${NC}"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
done

# 验证结果汇总
echo ""
echo "📊 === 验证结果汇总 ==="
echo -e "总检查项: $TOTAL_CHECKS"
echo -e "${GREEN}通过: $PASSED_CHECKS${NC}"
echo -e "${RED}失败: $FAILED_CHECKS${NC}"

# 计算通过率
if [ $TOTAL_CHECKS -gt 0 ]; then
    PASS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
    echo -e "通过率: ${PASS_RATE}%"
    
    if [ $PASS_RATE -ge 80 ]; then
        echo -e "${GREEN}🎉 配置验证通过！${NC}"
        exit 0
    elif [ $PASS_RATE -ge 60 ]; then
        echo -e "${YELLOW}⚠️  配置基本合格，建议优化${NC}"
        exit 0
    else
        echo -e "${RED}❌ 配置验证失败，需要修复${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ 没有进行任何检查${NC}"
    exit 1
fi 