#!/bin/bash

# MarketPrism Docker容器化系统综合验证测试脚本
# 完整的错误分析、数据流验证和系统稳定性测试

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# 测试结果统计
TESTS_PASSED=0
TESTS_FAILED=0
TOTAL_TESTS=0
ERRORS_FOUND=()
FIXES_APPLIED=()

echo -e "${BLUE}🔍 MarketPrism Docker容器化系统综合验证测试${NC}"
echo "=================================================================="
echo "测试时间: $(date)"
echo ""

# 测试函数
run_test() {
    local test_name="$1"
    local test_command="$2"
    local is_critical="${3:-false}"
    
    echo -e "\n${BLUE}🔍 测试: $test_name${NC}"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if eval "$test_command"; then
        echo -e "${GREEN}✅ 通过: $test_name${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        if [ "$is_critical" = "true" ]; then
            echo -e "${RED}❌ 关键失败: $test_name${NC}"
        else
            echo -e "${YELLOW}⚠️  警告: $test_name${NC}"
        fi
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# 记录错误函数
record_error() {
    local error_msg="$1"
    ERRORS_FOUND+=("$error_msg")
    echo -e "${RED}🚨 发现错误: $error_msg${NC}"
}

# 记录修复函数
record_fix() {
    local fix_msg="$1"
    FIXES_APPLIED+=("$fix_msg")
    echo -e "${GREEN}🔧 应用修复: $fix_msg${NC}"
}

# 1. 容器状态检查
echo -e "\n${YELLOW}📋 第1阶段: 容器状态检查${NC}"
echo "================================================"

CONTAINERS=("marketprism-clickhouse" "marketprism-nats" "marketprism-data-storage" "marketprism-data-collector")

for container in "${CONTAINERS[@]}"; do
    run_test "${container}容器运行状态" "docker ps | grep -q $container" true
done

# 2. 详细错误日志分析
echo -e "\n${YELLOW}🔍 第2阶段: 详细错误日志分析${NC}"
echo "================================================"

echo -e "\n${PURPLE}📋 ClickHouse容器日志分析:${NC}"
CLICKHOUSE_ERRORS=$(docker logs marketprism-clickhouse 2>&1 | grep -i "error\|exception\|failed" | wc -l)
echo "错误数量: $CLICKHOUSE_ERRORS"
if [ $CLICKHOUSE_ERRORS -gt 0 ]; then
    echo "最近错误:"
    docker logs marketprism-clickhouse 2>&1 | grep -i "error\|exception\|failed" | tail -3
    record_error "ClickHouse有 $CLICKHOUSE_ERRORS 个错误"
fi

echo -e "\n${PURPLE}📋 NATS容器日志分析:${NC}"
NATS_ERRORS=$(docker logs marketprism-nats 2>&1 | grep -i "error\|exception\|failed" | wc -l)
echo "错误数量: $NATS_ERRORS"
if [ $NATS_ERRORS -gt 0 ]; then
    echo "最近错误:"
    docker logs marketprism-nats 2>&1 | grep -i "error\|exception\|failed" | tail -3
    record_error "NATS有 $NATS_ERRORS 个错误"
fi

echo -e "\n${PURPLE}📋 数据存储服务日志分析:${NC}"
STORAGE_ERRORS=$(docker logs marketprism-data-storage 2>&1 | grep -i "error\|exception\|failed" | wc -l)
echo "错误数量: $STORAGE_ERRORS"
if [ $STORAGE_ERRORS -gt 0 ]; then
    echo "最近错误:"
    docker logs marketprism-data-storage 2>&1 | grep -i "error\|exception\|failed" | tail -5
    record_error "数据存储服务有 $STORAGE_ERRORS 个错误"
fi

echo -e "\n${PURPLE}📋 数据收集器日志分析:${NC}"
COLLECTOR_ERRORS=$(docker logs marketprism-data-collector 2>&1 | grep -i "error\|exception\|failed" | wc -l)
echo "错误数量: $COLLECTOR_ERRORS"
if [ $COLLECTOR_ERRORS -gt 0 ]; then
    echo "最近错误:"
    docker logs marketprism-data-collector 2>&1 | grep -i "error\|exception\|failed" | tail -5
    record_error "数据收集器有 $COLLECTOR_ERRORS 个错误"
fi

# 3. 服务连通性检查
echo -e "\n${YELLOW}🔗 第3阶段: 服务连通性检查${NC}"
echo "================================================"

run_test "ClickHouse健康检查" "curl -s http://localhost:8123/ping | grep -q 'Ok'" true
run_test "NATS健康检查" "curl -s http://localhost:8222/healthz >/dev/null 2>&1" true
run_test "数据存储服务健康检查" "curl -s http://localhost:8080/health >/dev/null 2>&1"
run_test "数据收集器健康检查" "curl -s http://localhost:8084/health >/dev/null 2>&1"

# 4. NATS JetStream状态检查
echo -e "\n${YELLOW}📊 第4阶段: NATS JetStream状态检查${NC}"
echo "================================================"

NATS_STATS=$(curl -s http://localhost:8222/jsz 2>/dev/null || echo '{}')
STREAMS=$(echo "$NATS_STATS" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('streams', 0))" 2>/dev/null || echo "0")
MESSAGES_INITIAL=$(echo "$NATS_STATS" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('messages', 0))" 2>/dev/null || echo "0")

echo "初始NATS统计:"
echo "  - Streams: $STREAMS"
echo "  - Messages: $MESSAGES_INITIAL"

run_test "JetStream可访问性" "curl -s http://localhost:8222/jsz >/dev/null 2>&1" true
run_test "JetStream Streams存在" "[ '$STREAMS' -gt 0 ]" true

# 5. ClickHouse数据库验证
echo -e "\n${YELLOW}💾 第5阶段: ClickHouse数据库验证${NC}"
echo "================================================"

run_test "ClickHouse数据库连接" "curl -s 'http://localhost:8123/?database=marketprism_hot' --data 'SELECT 1' >/dev/null 2>&1" true

# 检查表结构
echo "检查数据表结构:"
TABLES=$(curl -s "http://localhost:8123/?database=marketprism_hot" --data "SHOW TABLES" 2>/dev/null || echo "")
echo "现有表: $TABLES"

TRADES_EXISTS=$(echo "$TABLES" | grep -q "trades" && echo "1" || echo "0")
ORDERBOOKS_EXISTS=$(echo "$TABLES" | grep -q "orderbooks" && echo "1" || echo "0")

echo "  - Trades表: $([ '$TRADES_EXISTS' = '1' ] && echo '存在' || echo '不存在')"
echo "  - Orderbooks表: $([ '$ORDERBOOKS_EXISTS' = '1' ] && echo '存在' || echo '不存在')"

run_test "Trades表存在" "[ '$TRADES_EXISTS' = '1' ]"
run_test "Orderbooks表存在" "[ '$ORDERBOOKS_EXISTS' = '1' ]"

# 6. 等待数据流并进行验证
echo -e "\n${YELLOW}⏱️  第6阶段: 数据流验证 (等待3分钟)${NC}"
echo "================================================"

echo "等待系统稳定运行并收集数据..."
for i in {1..18}; do
    echo -n "."
    sleep 10
done
echo ""

# 检查NATS消息增长
NATS_STATS_AFTER=$(curl -s http://localhost:8222/jsz 2>/dev/null || echo '{}')
MESSAGES_AFTER=$(echo "$NATS_STATS_AFTER" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('messages', 0))" 2>/dev/null || echo "0")

echo "3分钟后NATS统计:"
echo "  - Messages: $MESSAGES_AFTER (增长: $((MESSAGES_AFTER - MESSAGES_INITIAL)))"

run_test "NATS消息数量增长" "[ '$MESSAGES_AFTER' -gt '$MESSAGES_INITIAL' ]"

# 检查ClickHouse数据
if [ "$TRADES_EXISTS" = "1" ]; then
    TRADES_COUNT=$(curl -s "http://localhost:8123/?database=marketprism_hot" --data "SELECT count() FROM trades WHERE timestamp >= now() - INTERVAL 5 MINUTE" 2>/dev/null || echo "0")
    echo "最近5分钟Trades数据: $TRADES_COUNT 条"
    run_test "Trades数据存在" "[ '$TRADES_COUNT' -gt 0 ]"
fi

if [ "$ORDERBOOKS_EXISTS" = "1" ]; then
    ORDERBOOKS_COUNT=$(curl -s "http://localhost:8123/?database=marketprism_hot" --data "SELECT count() FROM orderbooks WHERE timestamp >= now() - INTERVAL 5 MINUTE" 2>/dev/null || echo "0")
    echo "最近5分钟Orderbooks数据: $ORDERBOOKS_COUNT 条"
    run_test "Orderbooks数据存在" "[ '$ORDERBOOKS_COUNT' -gt 0 ]"
fi

# 7. 系统稳定性检查
echo -e "\n${YELLOW}🔄 第7阶段: 系统稳定性检查${NC}"
echo "================================================"

# 检查容器是否重启
for container in "${CONTAINERS[@]}"; do
    RESTART_COUNT=$(docker inspect $container --format='{{.RestartCount}}' 2>/dev/null || echo "unknown")
    echo "$container 重启次数: $RESTART_COUNT"
    if [ "$RESTART_COUNT" != "0" ] && [ "$RESTART_COUNT" != "unknown" ]; then
        record_error "$container 已重启 $RESTART_COUNT 次"
    fi
done

# 最终容器状态检查
echo "最终容器状态检查:"
for container in "${CONTAINERS[@]}"; do
    run_test "${container}最终状态检查" "docker ps | grep -q $container"
done

# 8. 性能指标收集
echo -e "\n${YELLOW}📊 第8阶段: 性能指标收集${NC}"
echo "================================================"

echo "容器资源使用情况:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep marketprism

# 9. 最终验证报告
echo -e "\n${YELLOW}📋 第9阶段: 最终验证报告${NC}"
echo "=================================================================="

echo -e "\n${BLUE}📊 测试结果统计:${NC}"
echo "总测试数: $TOTAL_TESTS"
echo -e "通过测试: ${GREEN}$TESTS_PASSED${NC}"
echo -e "失败测试: ${RED}$TESTS_FAILED${NC}"
echo "成功率: $(( TESTS_PASSED * 100 / TOTAL_TESTS ))%"

echo -e "\n${BLUE}🚨 发现的错误列表:${NC}"
if [ ${#ERRORS_FOUND[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ 未发现严重错误${NC}"
else
    for error in "${ERRORS_FOUND[@]}"; do
        echo -e "${RED}- $error${NC}"
    done
fi

echo -e "\n${BLUE}🔧 应用的修复列表:${NC}"
if [ ${#FIXES_APPLIED[@]} -eq 0 ]; then
    echo "无修复应用"
else
    for fix in "${FIXES_APPLIED[@]}"; do
        echo -e "${GREEN}- $fix${NC}"
    done
fi

echo -e "\n${BLUE}📈 数据流验证结果:${NC}"
echo "- NATS消息增长: $((MESSAGES_AFTER - MESSAGES_INITIAL)) 条"
if [ "$TRADES_EXISTS" = "1" ]; then
    echo "- Trades数据: ${TRADES_COUNT:-0} 条"
fi
if [ "$ORDERBOOKS_EXISTS" = "1" ]; then
    echo "- Orderbooks数据: ${ORDERBOOKS_COUNT:-0} 条"
fi

echo -e "\n${BLUE}🎯 系统状态总结:${NC}"
if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 系统验证完全成功！${NC}"
    echo -e "${GREEN}✅ MarketPrism Docker容器化系统运行正常${NC}"
    echo -e "${GREEN}✅ 数据流端到端验证通过${NC}"
    echo -e "${GREEN}✅ 系统稳定性测试通过${NC}"
else
    echo -e "${YELLOW}⚠️  系统存在 $TESTS_FAILED 个问题需要关注${NC}"
fi

echo -e "\n${BLUE}📋 快速访问命令:${NC}"
echo "curl http://localhost:8123/ping      # ClickHouse健康检查"
echo "curl http://localhost:8222/healthz   # NATS健康检查"
echo "curl http://localhost:8080/health    # 数据存储健康检查"
echo "curl http://localhost:8084/health    # 数据收集器健康检查"

echo -e "\n${BLUE}📋 数据查询示例:${NC}"
echo "# 查询最近交易数据"
echo "curl -s 'http://localhost:8123/?database=marketprism_hot' --data 'SELECT * FROM trades ORDER BY timestamp DESC LIMIT 5'"
echo "# 查询最近订单簿数据"
echo "curl -s 'http://localhost:8123/?database=marketprism_hot' --data 'SELECT * FROM orderbooks ORDER BY timestamp DESC LIMIT 5'"

echo ""
echo "=================================================================="
echo "验证测试完成时间: $(date)"

# 返回适当的退出码
if [ $TESTS_FAILED -eq 0 ]; then
    exit 0
else
    exit 1
fi
